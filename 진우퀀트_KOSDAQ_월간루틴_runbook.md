# 진우퀀트 — KOSDAQ 테마 lane 월간 루틴 (runbook)

> 진우 PC(Desktop\진우퀀트)에서 **매달 1회**. 전부 로컬 데이터(FDR 불필요). 매수신호 아님 — thesis·매수는 진우.

## 월초 (5분)

```powershell
cd "C:\Users\긍정적인_삶의자세\Desktop\진우퀀트"

# 1) 통합 스캔 — 전 테마 landscape + 선반영% + 전월대비 신규부상 + 소외(역발상) 후보
python kosdaq_monthly_scan.py
#   → kosdaq_monthly_scan_YYYYMM.csv 생성. 콘솔에서:
#     · '신규부상' = 이번 달 새로 올라온 후보(= 발굴 신호, 주목)
#     · '선반영%' 높은 테마(예: 2차전지)는 이미 늦었을 수 있음 → 카탈리스트 남았나 점검
#     · '소외/역발상' = 테마 견인주 중 깊은 조정(진우 thesis로 선별)

# 2) 관심 테마 상세 표
python kosdaq_theme_discover.py --theme 로봇      # 또는 반도체소부장/바이오/2차전지…
python kosdaq_theme_discover.py --list-themes      # 테마 목록
python kosdaq_theme_discover.py --kw 반도체,전자부품  # 커스텀(키워드 정밀)
```

## 후보 → 매수 판단 (진우)

1. 후보 중 **forward thesis(카탈리스트)** 있는 것만 골라 **`진우퀀트_KOSDAQ_워치리스트_active.md`**(영구 파일, 스크립트가 안 덮어씀)에 한 줄 추가:
   - 카탈리스트 / **무효화 트리거(필수)** / 진입비중(cap≤10%) / 가드레일 상태
   - ⚠️ `kosdaq_theme_watchlist.csv`(스크립트 생성)엔 적지 말 것 — 재실행 시 덮어써짐
2. 단건 가드레일 재확인 필요 시: `python kosdaq_theme_guardrail.py` (또는 watchlist 갱신)
3. **선반영(급등·고점근접)** 종목은 "카탈리스트가 *남았는지*"가 핵심 — 보편화된 뉴스면 패스
4. 매수는 진우 직접. **위성(W) cap 전계좌 ≤10%, 1~2슬롯**. production(S 트랙)·KOSDAQ 체계배분 0 불변

## 월말 (측정 — 이게 핵심)

`진우퀀트_v37_2_실전기록.md` §3-1에 기입:
- Track W 평가액·월수익
- **Track W 반사실**: 같은 돈으로 v3.7.2 시스템 픽 들었으면? → **W − 반사실 = 재량 기여 %p**
- 6~12개월 누적이 **양수 지속 → 재량 lane 유지/확대 / 음수 → 축소** (데이터가 결정)

## 분기 / 9월

- 분기: 보유 thesis 재심사 — 무효화 트리거 닿았나? 아니면 정리
- **2026-09**: v4.1 gw0.5 관찰 재점검 + v3.7.2 옵션B + v3.9 PEAD 통합 판정

## 원칙 (냉장고 카드)
1. 시스템 영역(KOSPI 대형 quality)은 안 건드림
2. 테마는 내가 고르되 가드레일+thesis+무효화+cap≤10%
3. 사기 전 선반영·무효화 적기 / 매달 반사실로 측정
4. 백테스트≠미래, 발굴툴=후보 surfacing이지 매수신호 아님

> 참조: 발굴 방법론 `진우퀀트_KOSDAQ_테마발굴_시스템.md` · 전략 `진우퀀트_종목선정_강점플레이북.md` · 현황 `진우퀀트_KOSDAQ_세션핸드오프_2026-06-06.md`
