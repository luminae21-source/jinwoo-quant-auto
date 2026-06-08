# 진우퀀트 — KOSDAQ 전용 종목선정 모듈 (v4.1) 시작 prompt / 스코핑 노트

> 작성: 2026-06-06 (Cowork, Desktop 재연결 후 실자산 확인 반영) | 모듈코드 **v4.1 KOSDAQ-Selection (`kosdaq_sel`)** | 상태: Stage 0 진입 전 (미착수)
> 성격: 새 세션이 **이 파일 1개만 읽어도** 컨텍스트 복원 + Stage 0부터 착수 가능한 시작 prompt
> 정본 위치: `C:\Users\긍정적인_삶의자세\Desktop\진우퀀트\` (canonical). OneDrive 사본은 stale — 사용 금지.

---

## 1. 모듈 정체성 (혼동방지 — 먼저 읽을 것)

| 구분 | 이 모듈 (v4.1 kosdaq_sel) | 헷갈리는 기존 작업 |
|---|---|---|
| 하는 일 | **KOSDAQ 종목을 점수화해 고르는 '종목선정' 슬리브** | — |
| ≠ | — | **모듈 D = v4.0 영역2 regime (종결·기각)**: KOSPI/KOSDAQ '마켓타이밍·팩터가중치 조정' |
| ≠ | — | **영역3 universe 확장 (종결·기각)**: KOSPI-앵커 top-30에 KOSDAQ carve-in → drag로 기각, KOSDAQ 0 |
| ≠ | — | production v3.7.2 = KOSPI 18종목 점수엔진 (무수정) |

- **핵심 정당성**: 영역3은 *KOSPI 기준 풀 안에서* KOSDAQ를 끼워넣는 것을 기각했다(carve-in이 IR drag). 이 모듈은 질문이 다르다 — **KOSDAQ-네이티브 기준으로 자체적으로 서는 슬리브가 가능한가.** 별개 시험.
- "영역2"라는 말 이중 사용 주의: ① 구 로드맵 영역2=매매기법(모듈 F) ② v4.0 재편 영역2=regime(모듈 D). **이 모듈은 둘 다 아님 — KOSDAQ 종목선정.**

### 무수정 원칙 (절대 준수)
- production(`score_v37_2.py` 등)·모듈 C(`*_v39_pead*`)·모듈 D(`*_v40_regime*`)·영역3(`universe_*`, `*_univ30*`) 파일 **일절 손대지 않음.**
- 신규 파일만 생성, 이름에 반드시 **`kosdaq_sel`** 또는 **`v41_kosdaq`** 포함 → 검색·구분 용이.

---

## 2. 왜 필요한가 (KOSPI 자산을 그대로 못 쓰는 2가지 실측 근거)

**① 종목선정 자체가 불가** — 영역3 universe30 룰의 유동성·시총 가드레일이 **KOSPI 분포 기준**으로 캘리브레이션됨(시총 top-200 ∩ ADTV 상위 60%, 섹터 KRX 세분류). KOSDAQ 종목을 그 컷오프에 넣으면 사이즈 티어가 통째로 밀려 **사실상 전량 탈락** → KOSDAQ는 점수표에 오르지도 못함. (실측: 알테오젠 pool r99/229, ISC r86/229 — 교차시장 왜곡 확인됨)

**② 마켓타이밍도 공유 불가** — 모듈 D 실측: KOSPI regime과 KOSDAQ regime이 **49개월 중 14개월(29%) 국면 어긋남** (일치 35/49=71%). 2022-12·2024-02·2024-08 KOSPI ON / KOSDAQ OFF, **현재 2026-06도 KOSPI NEUTRAL / KOSDAQ RISK_OFF.** KOSPI 타이밍을 KOSDAQ에 그대로 쓰면 오신호.

→ **선정 룰도, 타이밍도 KOSPI에서 못 빌림. KOSDAQ는 별도 종목선정 모듈이 필요하다는 게 데이터로 확정.**

---

## 3. 재사용 자산 (Desktop\진우퀀트에 실재 확인 완료 — 2026-06-06)

| 자산 (실파일명) | 내용 | 용도 |
|---|---|---|
| `fetch_regime_kosdaq_v40.py` | KOSDAQ regime detector (self-test 6) | 선정 후 국면 필터/타이밍 보조 |
| `regime_market_cache_v40_kosdaq.json` + `regime_history_v40_kosdaq.csv` | KOSDAQ 49개월 국면 이력 (어긋남 14/49 실측) | PIT regime 입력 |
| `liquidity_kosdaq.csv` | `code,name,시장부,mcap,adtv` (시총·거래대금 RAW) | **유동성/시총 컷오프 캘리브레이션 원천** |
| `fundamentals_kosdaq.csv` (347KB) | DART 재무 | 퀄리티/성장 팩터 원천 |
| `kosdaq_industry.csv` | KRX **121개** 산업분류 (`fetch_kosdaq_sector.py` 생성) | 섹터중립·산업집중 cap |
| `kosdaq_factors.csv` | 코스닥 FF 팩터수익률 (MKT·SMB·HML·WML·RF) | 팩터 적합성·상관 prune 레퍼런스 |
| `kosdaq_monthly_prices.csv` · `kosdaq_relative_screen.py` | 월간가격 · 시장상대 스크린 프로토 | 백테스트 가격패널·스크린 출발점 |

> ⚠️ Stage 0 첫 작업 = 위 8개 존재·스키마·기간(2020~) 재확인. `kosdaq_industry.csv`는 `liquidity_kosdaq.csv`의 '시장부'(중견기업부 등)와 다른 **산업** 분류임 — 섹터 cap은 industry 기준으로.
> 📌 실측 데이터 플래그(결정메모 §2 기준): 재무 가용 **297종이 천장**(유효 N 게이트 ≥40) · 재무 **연간만**(성장=YoY, 공시지연 PIT) · `kosdaq_factors.csv` **HML 결측** · **KOSDAQ150 지수 파일 없음**(판정 base = MKT + 등가중 보조).

---

## 4. 빠진 것 (이번 모듈이 새로 만들어야 하는 것)

1. **선정용 컷오프 캘리브레이션** — 유동성/시총/거래대금 RAW는 `liquidity_kosdaq.csv`로 *이미 존재*. 빠진 건 **KOSDAQ 분포에 맞춘 컷 임계**(동전주·저유동·초소형 배제선). KOSPI 컷 직이식 금지.
2. **코스닥 회계특성에 맞는 재무 적합성 검증** — 코스닥은 **성장주·적자기업 多·소형·회계 변동성↑**. 한상욱 F_korean·ModF·Sloan이 같은 부호로 작동하는지 *재검증* + **성장성 축**(매출/이익 성장)을 선정의 핵심 기준으로 명시. KOSPI 대형주 가중치 그대로 이식 금지.
3. **코스닥 전용 비용모델** — 스프레드 넓음. 왕복 prior **0.5~0.7%**(D §10 ③) 이상 보수 설정, 백테스트에 반영(현행 KOSPI 0.235%의 2~3배).

---

## 5. 단계 계획 Stage 0~5 (C·D 패턴 그대로)

> 패턴: **결정메모+사전 합격선 → 데이터 → 팩터검증 → score 코드(신규) → PIT 백테스트 자동판정 → PASS시 관찰모드.** 각 단계 self-test 필수, production 무수정. **FAIL시 즉시 종료(재튜닝·그리드 금지).**

| Stage | 내용 | 산출물(신규: kosdaq_sel/v41_kosdaq) | 게이트 |
|---|---|---|---|
| **0** | 결정메모 + **사전 합격선·변형 등록(변경 금지)** + 단순함 4문 자기진단 + 재사용 8자산 확인 | `진우퀀트_v41_KOSDAQ선정_결정메모.md` | 합격선·변형 등록 완료 |
| **1** | KOSDAQ universe 데이터: 컷오프 캘리브레이션 + 성장성·재무 적재 | `build_kosdaq_sel_universe.py` → `kosdaq_sel_universe_cache.json` | self-test + 후보 N 확보 |
| **2** | **팩터 적합성 + 상관 prune** — 후보 팩터 부호/IC 점검 + **상관행렬로 중복신호 제거**(아래 §6-나) | `validate_kosdaq_sel_factors.py` + 진단 csv/json | 채택 팩터셋 확정 (prune 후) |
| **3** | score 코드 (KOSDAQ 전용 가중치 = 성장성+회계적합 quality, production import 레이어) | `score_v41_kosdaq_sel.py` → `v41_kosdaq_sel_scores_latest.csv` | self-test + 등급표 sanity |
| **4** | **PIT 백테스트 자동판정** (거래일 정렬, 비용 0.5~0.7% 차감, **동시점 공식엔진 병행**) | `backtest_v41_kosdaq_sel_pit.py` + 결과 json | 사전 합격선 자동 PASS/FAIL |
| **5** | PASS시에만 **병행 관찰모드** (production·GitHub Actions 무변경, 월 루틴 1줄) | `진우퀀트_v41_kosdaq_관찰기록.md` + 종료기준 사전등록 | 관찰 후 통합 재검토 |

---

## 6. 진우 방향 반영 — 설계 3원칙 (Stage 0 결정메모에 명문화)

**가. 선정 기준 = 성장성 + 코스닥 회계특성 재무 적합성**
KOSDAQ는 성장주 universe → 가치/대형주 quality 그대로 쓰면 부적합. **성장성(매출·이익 모멘텀)을 1차 축**으로, 재무 건전성은 *코스닥 회계 변동성에 맞게* 적합성 검증된 팩터만 채택.

**나. 팩터 상관관계 = 중복 신호 prune 용도 (적재 X)**
상관 높은 지표를 둘 다 싣지 않는다. **Stage 2에서 후보 팩터 상관행렬을 먼저 그리고, |ρ| 높은 쌍은 하나만 남긴다.** 근거 = v3.8 전례(F_korean·GP 상관 **+0.644** 중복이 alpha 손실의 한 원인). 상관은 "추가"가 아니라 **"쳐내는"** 도구. `kosdaq_factors.csv`로 코스닥 자체 팩터 상관 레퍼런스 확보 가능.

**다. 사전 합격선 먼저 등록 → 그 다음에만 fitting**
점수·가중치 fitting은 **합격선·변형을 등록한 뒤에만** 한다. 결과 보고 합격선·팩터셋 바꾸기 금지. 근거 = 진우퀀트 **사전등록 기각 누적 9건**(GP·AG·EarnMom·Value·매매룰regime·D가중치regime·MR carve-in·universe확장·regime재시험; 그중 18종목 팩터 6연속) — "그럴듯한 아이디어"가 게이트에서 걸러지는 시스템이 정상이라는 증거. KOSDAQ도 이 규율을 그대로 적용.

---

## 7. 사전 합격선 틀 (Stage 0에서 확정 — 높게)

**왜 높게**: ① 영역3 확장 universe가 **−3.46%p로 기각**(룰30 CAGR 26.09% vs KOSPI 29.55%, 게이트 A). ② KOSPI-only 정책에서 이미 **KOSDAQ 룰 시장초과 −1.5~−2.2%p(체계적 알파 0)** 실측 — **이 모듈은 음(−)의 prior에서 출발.** 어설픈 +는 불합격.

제안 틀 (Stage 0 확정 전 기본값):

- **벤치마크**: KOSDAQ-only 슬리브 시장초과 = vs **KOSDAQ(또는 KOSDAQ150) 지수**, 다년 OOS PIT.
- **합격 = (코스닥 비용 0.5~0.7% 차감 후) 시장초과 ≥ +3.0%p AND Sharpe·IR 비열위 AND MDD 비열위.** (음의 prior·−3.46%p 교훈 반영, +1%p보다 훨씬 높게)
- **변형 2개만** 사전 등록 (예: 팩터셋 A/B 또는 성장가중 ×0.5/×1.0). 그리드 금지.
- **D 핵심 교훈**: 재현게이트는 *절대값 비교 금지* → **base를 동시점 공식엔진 병행 실행**해 delta로 판정. (참조 CAGR은 시장국면 종속 — 2026-06 KOSPI 급락이 base 수치 흔든 전례)

---

## 8. 혼동방지 체크리스트 (착수 전 재확인)

- [ ] production / C(`*_v39_pead*`) / D(`*_v40_regime*`) / 영역3(`universe_*`,`*_univ30*`) **0건 수정**
- [ ] 신규 파일명 전부 `kosdaq_sel` 또는 `v41_kosdaq` 포함
- [ ] 이 모듈 = **종목선정**. regime(D, 종결)·매매기법(F)·KOSPI universe확장(영역3, 종결)과 별개임을 결정메모 §1에 명시
- [ ] 작업 폴더 = **Desktop\진우퀀트** (OneDrive 사본 금지)
- [ ] §6 3원칙(성장성+회계적합 / 상관 prune / 합격선-먼저-then-fitting) 결정메모에 명문화
- [ ] 사전 합격선·변형은 결과 보기 전 등록, 이후 변경·재튜닝 금지

---

## 9. 실행법 (한 줄)

> 새 대화창 → Cowork 폴더 **Desktop\진우퀀트** 연결 → 이 파일 첨부(또는 전문 복붙) → **"이 시작 prompt 따라 KOSDAQ 선정 모듈 Stage 0부터 진행해줘. 재사용 8자산 확인부터, §6 3원칙·§7 합격선 등록까지."**
