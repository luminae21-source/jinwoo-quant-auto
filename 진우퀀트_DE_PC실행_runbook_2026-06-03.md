# 진우퀀트 — D·E PC 실행 런북 (2026-06-03)

> 샌드박스에서 FDR·네트워크가 막혀 못 돌린 **D(KOSDAQ 합본 재검증)**·**E(C1 전체 백테스트)**를 진우님 PC에서 한 번에 실행하는 절차.
> 폴더: `C:\Users\긍정적인_삶의자세\Desktop\진우퀀트` (PowerShell에서 `cd`)
> 원칙: **KOSPI 원본을 절대 잃지 않게 먼저 백업.** 백테스트 수치는 forward 기대치로 쓰지 않는다.

## 0. 준비 (1회)
```powershell
cd C:\Users\긍정적인_삶의자세\Desktop\진우퀀트
pip install finance-datareader requests pandas numpy scipy statsmodels
# FDR 동작 확인
python -c "import FinanceDataReader as fdr; print(fdr.StockListing('KOSDAQ').shape)"
```
FDR import 에러가 나면: `pip install --upgrade pyopenssl urllib3` 후 재시도.

---

## D. KOSDAQ 합본 재검증

### D-1. 백업 (필수 — 덮어쓰기 전에)
```powershell
copy fundamentals_pit.csv fundamentals_pit_KOSPI.bak
copy kospi_monthly_prices.csv kospi_monthly_prices_KOSPI.bak
copy korea_factors_monthly.csv korea_factors_monthly_KOSPI.bak
copy liquidity_sector.csv liquidity_sector_KOSPI.bak
```

### D-2. 합본 데이터 페치 (KOSPI+KOSDAQ, 시총 상위 = 유동 KOSDAQ 자동 포함)
```powershell
# 재무 (DART, 5~10분 — top-n은 KOSPI+KOSDAQ 합쳐 시총상위 N)
python fetch_dart_fundamentals_pit.py --market KOSPI,KOSDAQ --top-n 600 --start-year 2019 --end-year 2025

# 월간가격 + 팩터 (FDR, --no-cache로 합본 유니버스 강제 재수집)
python build_korea_factors.py --market KOSPI,KOSDAQ --top-n 600 --no-cache

# 유동성·섹터 (KOSDAQ 포함 여부 확인; KOSPI-only로 나오면 universe_rules가 자산 proxy로 자동 폴백)
python fetch_liquidity_sector.py
```
※ `--top-n 600`이 유동성 필터 역할(시총 상위만). 알테오젠·ISC 등 대형 KOSDAQ가 포함되고 잡주는 제외됨. 더 엄격히 하려면 400, 더 넓히려면 800.

### D-3. 재검증 (코드 수정 0 — universe-agnostic)
```powershell
python universe_screen.py --top-n 18
python universe_rules.py
python sweep_universe_size.py --ks 18,30,50,100
```
**읽을 것:**
- `universe_rules` 출력에서 **알테오젠·ISC가 더 이상 "데이터없음"이 아닌지** (= 운영-검증 불일치 해소). 이제 유지/관찰/제외 중 어디로 분류되는지.
- KOSDAQ 편입으로 **규칙 정당성 비율**(현재 KOSPI-only 25%)이 바뀌는지.
- `sweep` 표에서 KOSPI-only(§12: top-18 16.3%/Sh0.70) 대비 합본 K-프론티어 변화.

### D-4. 롤백 (원래 KOSPI-only로 되돌리려면)
```powershell
copy fundamentals_pit_KOSPI.bak fundamentals_pit.csv
copy kospi_monthly_prices_KOSPI.bak kospi_monthly_prices.csv
copy korea_factors_monthly_KOSPI.bak korea_factors_monthly.csv
copy liquidity_sector_KOSPI.bak liquidity_sector.csv
```

---

## E. C1 regime 오버레이 전체 백테스트
> #1 게이트는 이미 통과(이번 세션: DSR=1.000·PBO=0.571 → `robustness_report.md`). 따라서 실행 정당.
> ⚠️ E는 production 점수파일을 **건드리지 않음**(별도 비교만). D와 독립이라 순서 무관.

```powershell
python backtest_c1.py --echo-on 1.5 --bab-on 0.0
```
**읽을 것 (채택 게이트):**
- `C1 vs v3.7.2: 연환산 +X%p · Sharpe +Y` 라인.
- **채택 조건: 연환산 ≥ +1%p AND MDD 악화 ≤ +0.5%p.** 미충족이면 채택 연기(현 방어는 §13 regime 월간 MA200 유지).
- 출력 `backtest_c1_YYYYMMDD_HHMM.json`의 history(`r_v372_regime_%`)는 `build_trial_matrix_from_logs.py`로 넘겨 DSR 재확인 가능.

---

## 끝나면
각 명령의 **콘솔 출력을 그대로 복사**해 주시면 결과 해석·다음 판단(B 전환안, C 주기 결정)을 같이 정리하겠습니다.
```
