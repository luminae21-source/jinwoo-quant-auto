# 진우퀀트 모듈 D — v4.0 영역2 한국식 5요소 regime detector 결정메모

> 작성: 2026-06-05 (Opus 4.8 세션) / 상태: **종결 — 공식 기각 (§8)**, KOSDAQ 확장 데이터는 영역 3 인계 (§10)
> 목적: **drawdown 축소** — regime(국면)별 v3.7.2 팩터 가중치 동적 조정
> production(v3.7.2)·모듈 C(v3.9 PEAD 병행관찰) 무수정. D 산출물은 전부 `v40_regime` 신규 파일.

---

## 1. 핵심 구분 — 1차 기각(06-03)과 무엇이 다른가

| | 1차 시도 (기각) | 이번 D (미시험) |
|---|---|---|
| 메커니즘 | regime → **총 익스포저(현금 60~100%) + 인버스 헤지** | regime → **팩터 가중치 조정 (100% 투자 유지)** |
| 결과 | +regime 29.20% vs base 73.18% → 기각 | 검증 대상 |
| 기각 원인 | 한국 reversal에서 디리스킹이 반등 놓침 | 현금화 없음 → 같은 실패 모드 아님 |

기존 `regime_detector_v40.py`(5요소 신호·hysteresis, self-test 16)는 **재사용**. 기각된 것은 `regime_to_exposure` 응용부였고, detector 신호부는 무죄. D는 응용부만 교체: exposure 대신 **score 컴포넌트 multiplier**.

## 2. 사전 합격선 (2026-06-05 진우 승인 — 이후 변경 금지)

공식 엔진(backtest_v39_pit 컨벤션) + base 재현(공식 73.18% 대비 ±1%p) 성립 전제, **셋 다 충족 시에만 PASS**:

1. **MDD: base 대비 ≥ +2.0%p 개선** (예: −12.34% → −10.34% 이상)
2. **CAGR: base 대비 ≥ −1.0%p** (비용 0.235%×turnover 차감 후)
3. **Sharpe·IR: base 이상** (−0.01 허용 오차, C 전례)

하나라도 미달 → **즉시 기각, v3.7.2 유지** (매매룰 오버레이·GP·AG·EarnMom·Value 기각 전례와 동일 처리).

## 3. 사전 등록 변형 — 2개만, 임계값 튜닝 금지

조정은 **RISK_OFF 국면에서만** 발동. NEUTRAL·RISK_ON = base와 완전 동일 (평상시 수익 무손상 — 수익우선 철학 정합. 4년 중 RISK_OFF 달이 적을 것이므로 CAGR 이탈 최소화, MDD 표적).

| 컴포넌트 | regime_w (약) | regime_s (강) | 근거 |
|---|---|---|---|
| Mom12 (mom_s) | ×0.5 | ×0.0 | 약세장 모멘텀 OFF (손삼호·윤보현 국면전환 프레임) |
| Echo (echo_s) | ×0.5 | ×0.0 | 〃 (모멘텀 계열 동반) |
| BAB (bab_s) | ×1.5 | ×2.0 | 약세장 저β 강화 (backtest_v37_2 PATCH②가 BAB을 "regime 후보"로 지목) |
| base(F·ModF·FAR·Sloan)·NOA | ×1.0 | ×1.0 | 무변경 |

- detector의 가중치·hysteresis(on +0.30 / off −0.20 / exit +0.10)·VKOSPI 임계 — **기존 MVP 값 그대로, 튜닝 금지** (overfitting 가드)
- 변형 추가·multiplier 재조정 후 재시험 금지. 2변형 모두 미달 → D 종료.

## 4. 아키텍처 (산출물 4개 + 재사용 1개)

```
fetch_regime_market_v40.py [PC 실행]
  └→ regime_market_cache_v40.json  (VKOSPI 또는 실현변동성 proxy + 외인·기관 수급, pykrx 시도→실패 시 graceful degradation)
  └→ regime_history_v40.csv        (4년 월별 시장 3요소 regime — sanity check 용)

score_v40_regime.py  (Stage 3)
  ├ import: regime_detector_v40 (신호·분류 — 재사용, 무수정)
  ├ import: score_v37_2 / score_v37 (production 무수정)
  └ REGIME_MULTS 정의 + adjusted_total() — 정의 단일화 (backtest가 import)

backtest_v40_regime.py  (Stage 4, 판정) [PC 실행]
  ├ 엔진: backtest_v39_pit_pead.py 컨벤션 1:1 (월초 리밸·비용 0.235%×턴오버·caps·metrics/IR=backtest_v37_2)
  ├ 컴포넌트 산출: backtest_v37_2의 compute 함수들 import — base(mult=1)가 공식과 동일해야 함 (재현 게이트)
  └ 변형: base / regime_w / regime_s
```

**backtest 내 regime 산출 (PIT 보장, 각 리밸일 d0에서 ≤d0 데이터만):**

| 요소 | 소스 | 비고 |
|---|---|---|
| 1 지수추세 | panel['_KOSPI'] (FDR) | 추가 데이터 불필요 |
| 2 변동성 | cache의 VKOSPI → 없으면 KOSPI 실현변동성 proxy (`vol_signal_pct`) | pykrx 실패해도 진행 |
| 3 수급 | cache의 외인+기관 20일 순매수 | 실패 시 None→재정규화 |
| 4 섹터집중 | **base picks**의 top 섹터 비중 (regime 적용 전 picks — 순환 참조 방지) | 추가 데이터 불필요 |
| 5 팩터 ON/OFF | 해당 변형 자신의 직전 3개월 초과수익 vs KOSPI | 초기 3개월 None→재정규화 |

prev_state는 변형별로 리밸 경로 따라 순차 유지 (hysteresis 경로의존).

## 5. 정직한 prior (기각 가능성 높음을 인지하고 시작)

1. 팩터 추가 4연속 기각 (GP·AG·EarnMom·Value) + regime 익스포저 기각 — 18종목 대형주에서 v3.7.2는 사실상 천장.
2. v3.7.2는 이미 하락장에서도 양호 (validate regime 05-29: 하락장 Echo +0.23%p/월) → RISK_OFF에서 모멘텀을 꺾는 게 오히려 損일 수 있음.
3. 49개월 표본에 뚜렷한 RISK_OFF 국면 1~2회뿐 → 효과가 나와도 noise 가능성, 마진 박약 시 C처럼 명시.
4. 손삼호·윤보현의 MDD −46→−12.5%는 **출발점이 나쁜 전략** 기준. 우리 base는 이미 −12.21%라 개선 폭이 구조적으로 작음.
- PASS여도 C처럼 **병행 관찰 모드**부터 (production 즉시 교체 없음).

## 6. 자기진단 4문 (단순함 우선)

1. 목적 명확? **YES** — MDD ≥ +2.0%p 개선
2. 백테스트 검증 가능? **YES** — 공식 엔진 + 사전 합격선
3. 실운용 반영 가능? **YES (조건부)** — 월 1회 리밸 시 regime 확인 1줄, 데이터는 FDR(+pykrx 선택). RISK_OFF 달만 행동 변화
4. v3.7.2보다 진짜 나아지나? **미지수 → 그래서 합격선으로 보호.** 미달 시 즉시 기각

## 7. 환경 기록

- 세션 폴더: Desktop\진우퀀트 (canonical) ✅ 재연결 완료. OneDrive 구위치 사본은 stale — 사용 금지.
- 논문 37(손삼호·윤보현)·38(이정환 외) PDF: Desktop·세션 양쪽에 없음, e-kjfs.org fetch 타임아웃 → **설계문서(06-03)에 digest된 프레임 + 인덱스 요약 기반으로 진행.** multiplier가 논문 정밀 재현이 아님을 명시 (사전 등록으로 overfitting 방어).
- pykrx: 진우 PC 미설치 가능 → fetch 스크립트가 자동 설치 시도, 실패 시 proxy 모드.

## 8. 판정 기록 (2026-06-05 11:01 진우 실행, 장중)

- [x] base 재현: **71.92%** vs 공식 73.18% = −1.26%p → **±1%p 게이트 미성립** (단 구조 게이트 882/882 통과 — 엔진 불일치 아님. 참조값은 06-03 기록 + 이번 실행이 장중(11:01)이라 당일 미완성 가격 포함. 내부 delta 비교는 동일 엔진·동일 윈도라 유효)
- [x] regime_w: CAGR **−1.42%p** / MDD **+1.70%p** / Sharpe 2.79 (−0.01 경계) / IR 1.44 vs 1.49 → **FAIL** (3개 기준 중 ①MDD<+2.0 ②CAGR<−1.0 ③IR 모두 미달)
- [x] regime_s: CAGR **−1.93%p** / MDD **+1.28%p** / Sharpe 2.80 / IR 1.41 vs 1.49 → **FAIL** (더 큰 폭)
- [x] RISK_OFF 발동: w 21/49, s 23/49개월 — 예상(소수 국면)보다 훨씬 잦음. 실현변동성 proxy + 비대칭 hysteresis(천천히 복귀)가 2024-09~2025-05을 9개월 연속 RISK_OFF로 묶음 → 그 구간 모멘텀 축소가 수익 drag의 주범 (§5 prior 2번 적중)
- **재실행 (19:47 장 마감 후)**: base 71.43% / regime_w ΔCAGR −1.41·ΔMDD +1.70·IR 1.42 vs 1.46 FAIL / regime_s −1.87·+1.28·1.38 FAIL — 두 윈도에서 delta 안정 재현.
- **base 게이트 격차 원인 확정 (JSON 포렌식)**: 1101 vs 1947 월별 history **48/49개월 완전 동일**, 유일한 차이 = 2026-06 마지막 stub (−2.97→−4.08%). KOSPI 6월 누적 **−7.28%** 급락 진행 중 — 참조 73.18(06-03 데이터)·73.37(06-05 06:13, C엔진 0613 json 확인)은 이 급락 반영 전 수치. 즉 **엔진 불일치가 아니라 참조 staleness** (구조 게이트 882/882 + 48/49 month-identity + C엔진과 라인 동일 수익경로로 엔진 동등성 입증). 동일 엔진·동일 윈도 내부 delta는 두 실행 모두 유효.
- **공식 판정 (2026-06-05 확정): 2변형 모두 FAIL → 모듈 D 기각. v3.7.2 무변경 유지. 재튜닝·재시험 금지 (18종목 조합 한정).**
- 해석: MDD는 실제로 줄었으나(−12.34→−10.64) 합격선(+2.0%p) 미달이고, 그 대가(CAGR −1.4~−1.9%p, IR −0.04~−0.08)가 등록 허용폭 초과. 1차 기각(익스포저)과 같은 방향, 강도만 약함 — "regime으로 한국 reversal 엣지를 건드리면 손해" 일반화가 가중치 방식에서도 성립. 기각 사유 누적: GP·AG·EarnMom·Value·regime익스포저·regime가중치 6연속 — 18종목 대형주에서 v3.7.2는 천장 재확인.

---

## 9. PC 실행 가이드 (Stage 1~4 코드 완료, 2026-06-05)

산출물 4개 (self-test 전부 통과): 결정메모 / `fetch_regime_market_v40.py`(8) / `score_v40_regime.py`(9) / `backtest_v40_regime.py`(10)

**진우 PC에서 (Desktop\진우퀀트, 순서대로):**

```bash
# (선택) 5요소 완성용 — 실패해도 proxy로 자동 진행됨
pip install pykrx

# 1. 시장 데이터 수집 + regime 시계열 (1~3분)
python fetch_regime_market_v40.py
#    → 출력의 RISK_OFF 달 목록이 상식과 맞는지 눈으로 확인 (2022 약세·2024-08 등)

# 2. 판정 백테스트 (5~10분)
python backtest_v40_regime.py
#    → 콘솔 전체 또는 backtest_v40_regime_*.json을 Claude에 공유
```

**판정 읽는 법**: `[재현 게이트]` 2줄이 ✅인지 먼저 → 변형별 `✅ PASS / ❌ FAIL` (합격선 §2 자동 적용).
둘 다 FAIL이면 사전 등록대로 **즉시 종료** (재튜닝 금지). PASS 시 C 패턴 병행 관찰 모드 검토.

**live 한계 (기록)**: `score_v40_regime.py` 단독 실행은 (a) 전략 trailing 이력 없어 팩터 요소 제외,
(b) 직전 상태 미보유로 hysteresis 미적용 — 관찰 모드 채택 시 상태 파일로 보완 예정. 백테스트는 5요소+hysteresis 완전판.

---

## 10. 확장 적용 결정 (2026-06-05 오후) — ✅ 진우 승인 완료

진우 요청 "조건 3개 적용해 보자" → 범위 분리 제안 → **진우 승인 ("①②③을 적용하자")**. 아래 표가 확정 로드맵:

| 조건 | 처리 | 이유 |
|---|---|---|
| ① KOSDAQ 별도 detector | ✅ **이 세션에서 완료** — `fetch_regime_kosdaq_v40.py` (self-test 6) | regime 데이터 레이어 = D 범위. KQ11 + KOSDAQ 수급 + 실현변동성(VKOSDAQ 지수는 KRX에 없음), KOSPI와 월별 국면 어긋남 비교 리포트 내장 |
| ② 전 종목 DART 자동화 | ⏸ **영역 3로 이관** | universe 확장의 본체. 이미 다른 대화에서 universe 규칙화 진행 중(top-30, KOSDAQ 2 등) — 여기서 병행 착수하면 충돌. universe 확정 후 새 세션에서 |
| ③ 비용·합격선 재설계 | ⏸ **universe 확정 후** | 어떤 종목(유동성)인지 모르면 비용 가정 불가. 참고 prior만 기록: 코스닥 중소형 왕복 0.5~0.7% 가정 권장 (현행 0.235%의 2~3배), 합격선도 그만큼 보수화 필요 |

**순서 원칙 재확인**: 영역 3(universe 확정) → 그 위에 "확장 universe + regime 재시험"을 별도 모듈로 1회. 18종목 기각(§8)은 이 조합에 대한 기각이지 regime 개념 전체의 기각이 아님 — 단, 회의적 prior는 유지(코스닥도 한국 reversal 성향 강함).

**① 실측 결과 (2026-06-05 19:16 진우 실행)**: KOSPI vs KOSDAQ 국면 **일치 35/49 (71%) · 어긋남 14개월 (29%)**. 결정적 사례 — 2022-12·2024-02·2024-08 모두 KOSPI RISK_ON인데 KOSDAQ RISK_OFF (코스닥 단독 약세 정확 포착), **현재 2026-06도 KOSPI NEUTRAL / KOSDAQ RISK_OFF로 어긋남**. → "코스닥 종목엔 KOSDAQ 별도 detector 필수" 가설 데이터로 확정. 산출물: regime_market_cache_v40_kosdaq.json + regime_history_v40_kosdaq.csv (영역 3 모듈의 입력으로 보존).

**승인에 따른 실행 트리거 (확정)**:
1. **지금**: `fetch_regime_kosdaq_v40.py` PC 실행 → KOSDAQ regime 데이터 + KOSPI 어긋남 실측 확보
2. **universe 확정 시** (다른 대화의 규칙화 완료가 트리거): ② DART 전 종목 자동화 + ③ 비용(코스닥 왕복 0.5~0.7%)·합격선 재설계를 새 세션 모듈로 착수 — 이 결정메모 §10과 fetch_regime_kosdaq_v40.py가 출발점
3. regime 재시험은 그 모듈 안에서 1회 (18종목 기각과 별개 조합이므로 등록 원칙 위반 아님)
