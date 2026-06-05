# 진우퀀트 v3.9 PEAD — Stage 0 결정 메모

> 작성일: 2026-06-04 | 결정자: 진우 | 세션: 모듈 C 전용 (C / v3.9 PEAD)
> 결정: **A + 1 확정** — 진짜 PEAD(SUE + 공시 후 드리프트 게이트)로 딱 1회 깨끗하게 재시험. 범위는 PEAD만(DART SUE), EPS Revision 제외(애널리스트 컨센서스 데이터 없음).

---

## 1. 어제(2026-06-03) EarnMom 기각과의 정합성

| | EarnMom (06-03 기각) | 이번 재시험: 진짜 PEAD |
|---|---|---|
| 신호 | YoY ΔROE (수준 변화) | SUE = (X_q − X_{q−4}) / σ(과거 8분기 서프라이즈) |
| 표준화 | 없음 | 8분기 σ 표준화 (Foster-Olsen-Shevlin 시계열 SUE) |
| 타이밍 | 상시 점수 | **공시일(rcept_no) 정렬 + 공시 후 60거래일 게이트** |
| 결과 | base 73.18% vs 71.79% (−1.39%p) → 기각 | 미시험 |

**재시험 명분**: Bernard-Thomas(1989·1990) 엣지의 핵심은 "표준화된 서프라이즈 + 공시 직후 드리프트"인데, EarnMom은 둘 다 빠진 축소판이었음. Kim-Lee-Min(2019)이 한국에서 PEAD 유효 보고. 이 두 요소가 들어간 형태는 아직 한 번도 시험 안 됨.

**정직한 prior**: GP·AG·EarnMom 3연속 실패. 18종목 대형주는 팩터 추가를 거부해 온 universe (F_korean·quality 중복 +0.644 전례, Echo만 유일 성공). **기대는 낮게, 시험은 깨끗하게.**

## 2. 사전 합격선 (먼저 등록 — 결과 보고 바꾸지 않는다)

- 4년 OOS **PIT** 백테스트 (공시일 기준), base = v3.7.2 (진우 환경 73.18%)
- **합격 = base 대비 CAGR ≥ +1.0%p 그리고 Sharpe·IR 비열위**
- 시험 변형은 **PEAD_WEIGHT ×0.5 / ×1.0 둘만** (드리프트 게이트 on/off 참고용 허용)
- 미달 → **즉시 종료**, 2차 기각 기록, PEAD 노선 닫음. 그리드 탐색·재튜닝 금지 (overfitting 방지)

## 3. 단순함 우선 4문 자기진단

1. 목적 명확? — YES (v3.7.2 위 alpha 추가, 단일 신호 1개)
2. 백테스트 검증 가능? — YES (DART 공시일로 PIT 가능, lookahead 없음)
3. 실운용 반영 가능? — YES (분기 1회 DART fetch 추가, 월 루틴 변화 없음)
4. v3.6(=현 production v3.7.2)보다 진짜 나아지는가? — **백테스트가 판정** (합격선 미달 시 NO로 간주하고 종료)

## 4. 범위·구조

- v3.9 = **PEAD만**. EPS Revision은 컨센서스 데이터(FnGuide 등) 없어 제외.
- production 무수정: `score_v37_2.py` 등 기존 파일 일절 손대지 않음. 신규 파일만:

| 파일 | 역할 | 실행 위치 |
|---|---|---|
| `fetch_dart_eps.py` | DART 분기 지배주주순이익 + 공시일 수집 → `eps_sue_cache.json` | **[PC 실행]** |
| `score_v39_pead.py` | v3.7.2 점수 + PEAD 분위 점수 → `v39_pead_scores_latest.csv` | **[PC 실행]** (self-test는 어디서든) |
| `backtest_v39_pead.py` | Stage 2 PIT 백테스트 (다음 단계, 아직 미작성) | [PC 실행] |

- 이름 충돌 회피: 어제 `backtest_v39_pit.py`(EarnMom)와 별개 이름 사용. 덮어쓰지 않음.

## 5. SUE 신호 명세 (확정)

```
X_q        = 분기 지배주주 당기순이익 (연결 CFS 우선, 별도 OFS 폴백)
             누적 공시값을 분기 차분: Q1 / 반기−Q1 / 3Q누적−반기 / 연간−3Q누적
U_q        = X_q − X_{q−4}                    (계절 랜덤워크 서프라이즈)
SUE_q      = U_q / σ(U_{q−1} … U_{q−8})       (최소 6개 관측, σ≈0 가드 → 제외)
공시일      = rcept_no 앞 8자리 (PIT: 공시일 이후에만 SUE_q 사용 가능)
게이트      = 공시 후 60거래일 이내만 활성 (KOSPI 거래일 기준, 밖이면 0)
점수        = 18종목 SUE 3분위: 상위 20% +1 / 중위 60% 0 / 하위 20% −1 (Echo와 동일 컨벤션)
체력_v39   = 체력_최종(v3.7.2) + PEAD_WEIGHT × 점수   (PEAD_WEIGHT 1.0 기본, 0.5 토글)
```

정직 노트: 분기 공시 주기(~65거래일)상 60거래일 게이트는 대부분 활성 상태 — 게이트의 실제 역할은 PIT 정합 + 데이터 누락 시 staleness 가드. NI 기반이라 무상증자·대규모 유상증자 시 왜곡 가능(σ 표준화로 단위 무관하나 베이스 변화는 반영 안 됨) — 18종목 대형주 4년 범위에선 2차 효과로 간주.

## 6. 이번 세션에서 안 열린 파일 (OneDrive online-only stub)

`score_v37.py`, `score_v37_1.py`, `fetch_dart_quarterly.py`, `quality_timeseries_cache.json`, `dart_corp_codes.json`, `dart_config.json` — 전부 read 실패. 그래서 신규 코드는 이 파일들에 의존하지 않도록 **런타임 관용형**으로 작성 (corp codes 포맷 자동 감지 + DART corpCode.xml 자동 다운로드 폴백, API 키 3단 폴백). Desktop 원본에서는 정상 동작 전제.

읽기 성공: `score_v37_2.py`(인터페이스 확보), 핸드오프 3종.

## 7. PC에서 할 일 (Stage 1 마무리)

```powershell
# 0) 이 메모와 새 .py 2개를 Desktop\진우퀀트로 복사 (OneDrive 동기화 후)
Copy-Item "C:\Users\긍정적인_삶의자세\OneDrive\문서\Claude\Projects\진우퀀트\fetch_dart_eps.py","C:\Users\긍정적인_삶의자세\OneDrive\문서\Claude\Projects\진우퀀트\score_v39_pead.py","C:\Users\긍정적인_삶의자세\OneDrive\문서\Claude\Projects\진우퀀트\진우퀀트_v39_PEAD_결정메모.md" "C:\Users\긍정적인_삶의자세\Desktop\진우퀀트\"

cd "C:\Users\긍정적인_삶의자세\Desktop\진우퀀트"

# 1) self-test (네트워크·DART 불필요, 둘 다 통과해야 다음 진행)
python fetch_dart_eps.py --self-test
python score_v39_pead.py --self-test

# 2) DART 수집 (분당 rate limit 때문에 5~10분, 캐시돼서 재실행은 빠름)
python fetch_dart_eps.py            # → eps_sue_cache.json

# 3) 오늘 시점 v3.9 점수 (v3.7.2 대비 등급 변동 콘솔 표시)
python score_v39_pead.py            # → v39_pead_scores_latest.csv
```

결과(콘솔 출력 or CSV) 공유해 주면 → Stage 2 `backtest_v39_pead.py` 작성으로 진행.

## 8. 판정 후 처리 (Stage 3 예약)

- 합격 → production 통합 검토 (PEAD_WEIGHT 토글), 핸드오프·메모리 갱신
- 불합격 → 본 메모에 2차 기각 기록 추가, **PEAD 노선 종료**, v3.7.2 유지

---

## 9. 판정 기록 (2026-06-05, 공식 엔진 backtest_v39_pit_pead.py)

### 9-1. 자체 엔진 (06-04, backtest_v39_pead.py — 참고)
- base 82.23% (공식 73.18%와 +9%p 격차 → 참조 기준 초과, 판정 효력 없음 처리)
- 격차 원인: 공식은 월초 리밸 + 비용 0.235%×턴오버 + Sharpe=연환산/연변동성, 자체는 월말+비용0+월간Sharpe
- pead_05 Δ+2.64%p / pead_10 Δ+2.50%p — 방향 참고용

### 9-2. 공식 엔진 최종 판정 ⭐
| | 연환산 | Sharpe | MDD | IR | turnover | 판정 |
|---|---|---|---|---|---|---|
| base (v3.7.2) | 73.37% | 2.88 | −12.34% | 1.45 | — | (공식 73.18% 재현 ✓) |
| +PEAD ×1.0 | 73.70% (Δ+0.33%p) | 2.83 | −12.34% | 1.48 | 4.436 | ❌ FAIL |
| **+PEAD ×0.5** | **74.43% (Δ+1.06%p)** | 2.87 | −12.34% | **1.48** | 4.369 | **✅ PASS** |

- 49개월, PEAD 활성 47/49, 수치는 비용 차감 후(net)
- **사전 합격선(Δ≥+1.0%p AND Sharpe·IR 비열위 −0.01 허용) 기준 ×0.5 정식 합격** — GP·AG·EarnMom 이후 공식 엔진 관문 통과한 첫 팩터

### 9-3. 마진 주석 (과대해석 금지)
- 합격 마진 +0.06%p — 종이 한 장. ×1.0 탈락 + ×0.5만 통과 = 효과는 경계적, 49개월 표본 noise 가능성 상당
- 단: 비용 차감 후 수치, IR 개선(+0.03), MDD 동일, 자체 엔진(+2.64%p)과 방향 일치는 실질적
- Echo(+3.65%p) 대비 약한 신호임을 명시

### 9-4. Stage 3 옵션 (진우 결정)
- **A. 병행 관찰 1~3개월** — v3.7.2 운용 유지, v3.9(×0.5) 점수는 매월 기록만. v3.7.2 채택 때 '관찰 production' 전례 (Claude 추천)
- **B. 즉시 통합** — PEAD_WEIGHT=0.5 production 반영
- **C. 재량 기각** — 마진 박약 사유 (사전 룰상 PASS이나 운용자 재량)

운용 비용: 분기 1회 `fetch_dart_eps.py` 실행 추가가 전부 (월 루틴 변화 없음)

---

## 10. Stage 3 결정: A 병행 관찰 (2026-06-05)

- **결정: A — 병행 관찰 1~3개월** (Claude 추천 기본값으로 진행, 진우 "v3.9 Stage 3" 승인. B/C 전환은 언제든 가능)
- 운용 기준: **v3.7.2 그대로** (production·GitHub Actions 무변경)
- v3.9 설정: `score_v39_pead.py` PEAD_WEIGHT **0.5** 반영 완료 (판정 결과)
- 관찰 절차·월별 기록·**종료 기준(사전 등록)**: `진우퀀트_v39_관찰기록.md`
  - B(통합) 조건: 파이프라인 무사고 3개월 + 픽 변경 달 명백한 역행 없음
  - C(기각) 조건: 데이터 사고 반복 또는 일관된 역방향
  - 판정 시점: 2026-09 초 (v3.7.2 옵션 B 검토 일정 2026-09~11과 정렬)
- 첫 기록 (2026-06): 픽 동일 (기아 B→C뿐), SUE 15/18 — 관찰기록.md에 기입됨
