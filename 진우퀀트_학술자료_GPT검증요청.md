# GPT 검증 요청 패킷 — 진우퀀트 학술 자료 적절성 확인

작성일: 2026-05-26
용도: ChatGPT(또는 다른 LLM)에 가져가서 cross-verification 받기

---

## 📋 사용 방법

1. 이 파일 전체를 복사해서 ChatGPT 새 대화에 붙여넣기
2. 마지막 "검증 질문 5개"에 대한 답변 요청
3. GPT 답변을 받아서 Claude에게 다시 공유

---

## 1. 시스템 현황 (Context)

### 진우퀀트란?
한국 주식시장 18종목 long-only 퀀트 시스템. 한국인 개인투자자(직장인, 저빈도 매매)가 운영. 4년 OOS 백테스트로 v3.6 production 상태.

### 18종목 Universe
삼성전자, SK하이닉스, 한미반도체, 알테오젠, 기아, NAVER, 카카오, 한화에어로, LIG넥스원, KB금융, KT&G, 삼성SDI, 아모레퍼시픽, 삼성물산, 삼양식품, ISC, 두산에너빌리티, NH투자증권 (11개 산업)

### 버전 이력 + 검증 결과
| 버전 | 팩터 구성 | 4년 결과 (CAGR / Sharpe / MDD / IR) |
|---|---|---|
| v3.6 (production) | F_korean + ModF + FAR + Sloan | 69.82% / 2.56 / -12.50% / 1.64 |
| v3.7 | v3.6 + Mom12 + BAB + NOA | 67.71% / 2.78 / -10.64% / 1.63 (return -2.11%p) |
| v3.7.1 | v3.7 + BAB 임계값 재조정 | 68.25% / 2.77 / -10.56% / **1.68** (return -1.57%p) |
| KOSPI 벤치마크 | — | 28.11% / 1.10 / -16.45% |

### 알려진 한국시장 특성 (우리가 백테스트에서 관찰한 것)
- **한국 모멘텀이 미국과 다름**: 단순 12M momentum 추가 시 alpha 손실 (v3.7 -2.11%p)
- KT&G 같은 진정한 방어주는 BAB +2가 맞음, 그러나 β=1.2 근처 종목(삼성전자·삼성물산)은 보호하면서 분리 필요
- 반도체 trio (삼성전자·SK하이닉스·한미반도체)는 β 1.2~1.4로 BAB 페널티가 과도했음 → v3.7.1에서 완화

### 다음 단계 (v3.8) 계획
**목표**: v3.6 대비 -1.57%p alpha 손실 회복

**검토 중인 새 팩터 2개**:
1. **Quality-Profit / GP-Asset (Novy-Marx 2013)**: GP / Total Assets
2. **6M Momentum 가속 (Novy-Marx 2011 echo)**: 6M return - 12M return

**의문**:
- 18종목 대형주 universe에서 Novy-Marx GP factor가 작동할까?
- 한국시장에서 모멘텀이 약한데, 6M-12M 가속은 다를까?
- 두 팩터의 임계값을 어떻게 정해야 한국시장에 맞을까?

### 향후 (v4.0 영역 2) 계획
**목표**: Regime-aware system

**검토 중인 framework**:
- Faber 2007: KOSPI 200일 MA 위/아래
- Cooper-Gutierrez-Hameed 2004: 36개월 누적수익률 Up/Down state
- Whaley 2009: VKOSPI > 25 위기 감지

**의문**:
- 한국시장은 위 framework이 그대로 작동 안 한다는 증거 존재 (음의 모멘텀)
- 한국화된 룰 어떻게 설계해야 하나?

---

## 2. 수집한 학술 자료 (총 47편)

### A. 글로벌 원전 (13편)

| # | 저자/연도 | 제목 | 저널 |
|---|---|---|---|
| 1 | Piotroski (2000) | Value Investing: F-Score | Journal of Accounting Research 38 |
| 2 | Sloan (1996) | Accrual Anomaly | The Accounting Review 71 |
| 3 | Hirshleifer-Hou-Teoh-Zhang (2004) | NOA / Bloated Balance Sheets | JAE 38 |
| 4 | Jegadeesh-Titman (2011) | Momentum (review) | Annual Review |
| 5 | Frazzini-Pedersen (2014) | Betting Against Beta | JFE |
| 6 | Novy-Marx (2013) Main | Other Side of Value: GP Premium | JFE 108 |
| 7 | Novy-Marx (2013) Companion | Quality Dimension of Value | JPM |
| 8 | Cooper-Gutierrez-Hameed (2004) | Market States and Momentum | JF 59 |
| 9 | Faber (2007) | Tactical Asset Allocation | JWM 9 |
| 10 | Whaley (2009) | Understanding VIX | JPM 35 |
| 11 | Asness-Moskowitz-Pedersen (2013) | Value and Momentum Everywhere | JF 68 |
| 12 | Bernard-Thomas (1990) | PEAD | JAE 13 |
| 13 | Guerard (book chapter) | EPS Forecasts/Revisions/Momentum | book |

### B. 한국 적용/검증 (25편)

**가치/수익성/Quality (8편)**
- 안제욱·김규영 2014 "총수익성 프리미엄: 한국 주식시장에서의 실증분석" — Novy-Marx 한국 직접 검증 (1995-2013)
- 김민기·정진수·김동석 2018 "한국 수익성 프리미엄 발생 요인 분석" (KAIST, 2001-2017)
- 우동호·최흥식·김선웅 2023 "한국주식시장 마법공식 투자전략 성과분석" (Greenblatt 한국 적용)
- KAIST 박순영 2024 "한국 이익성장률 효과" (석사학위논문, 2단계 배당성장 모형)
- 김규형·임창우·정태규 "한국 FSCORE·GSCORE 패자추종" (중앙대)
- 이관영 2019 "국내 가치투자전략 성과·위험요인" (2009-2017)
- 장경천·김연권 2007 "가치주와 성장주 투자성과분석"
- 장옥화·최현돌 "가치주 장기투자성과 관련성"

**모멘텀 (12편)**
- 김규영·안제욱 2012, 2013 "한국 모멘텀 실증·Echo Momentum"
- 김동회·서한주 2008 "한국 스타일모멘텀전략"
- 이한재·김경욱 2004 "거래량 + 반전효과"
- 박경인 2016 "한국 투자전략 성과 요인 (Lo-MacKinlay 분해)"
- 한민연·강형구 2017 "국내 요인 수익률과 위험" (2004-2015)
- 엄철준 외 2020 "투자자관심·시장상황·모멘텀" (한국증권학회지)
- 엄철준·박종원 2021 "PCA 모멘텀"
- 엄철준 외 2022 "한국 Left-Tail Momentum" (VaR/ES)
- 엄철준·박종원 2023 "한국 단기반전·단기모멘텀"
- 외국인·기관·개인 투자자 모멘텀 거래 성향
- 한국 투자자 심리·스타일·모멘텀
- 국내 장기·단기 혼합 모멘텀 전략
- 주식수익률과 거래량 투자전략 (2004)
- 고승의 2015 "한국 융합적 모멘텀 투자전략" (Asness 한국판)

**Regime/Timing/VKOSPI (2편)**
- 손삼호·윤보현 2019 "스마트베타 위험요인 결합 — 국면전환" (연수익률 10.26% → 20.69%, MDD -46.12% → -12.52%)
- 이정환·손삼호·이건희 2023 "VKOSPI 단기 주가수익률 예측" (비대칭 룰)

**종합/Sentiment/PEAD/기타 (3편)**
- 김규영·안제욱 2010 "한국 기대수익률 결정요인"
- 노지혜·김동순·김현도 2023 "한국 8가지 요인 25년" (1995-2020) — 수익성·투자·비유동성 robust
- 한국 공매도 잔고비율 서프라이즈
- Kim-Lee-Min 2019 "PEAD: Expected Growth Risk" (고려대)
- KIFFS2024-10 (한국금융연구원 펀드비용 보고서)

### C. 글로벌 보조 (3편)
- Mo-Wang 2018 "Testing Piotroski F-Score on US" (Stockholm SE 석사논문, 2004-2015)
- Gimeno·Lobán·Vicente 2020 "Neural F-Score" (FRL)
- Kent Daniel 2004 NOA paper Discussion (NBER 슬라이드)
- Hirshleifer-Hsu-Li 2017 "Innovative Originality" (NBER WP, NOA와는 다른 주제)

---

## 3. Tier 0 reading list (이번 주 우선)

| 순서 | 자료 | 시간 |
|---|---|---|
| 1 | 안제욱·김규영 2014 총수익성 프리미엄 (한국 Novy-Marx 직접 검증) | 30분 |
| 2 | Novy-Marx 2013 Quality Dimension (companion, 개념) | 1h |
| 3 | 우동호 외 2023 마법공식 한국 (검증) | 30분 |
| 4 | 김민기 외 2018 수익성 프리미엄 발생 메커니즘 | 1.5h |

**총 3.5시간** — v3.8 점수 공식 1차 확정 기반

---

## 4. ⚠️ GPT에 묻고 싶은 검증 질문 5개

다음 5개 질문에 대해 **각각 명확한 의견**과 **근거**를 제시해 주세요:

### Q1. 자료 선정의 적절성
위 47편 학술 자료가 한국 18종목 long-only 퀀트 시스템(v3.6→v3.7.1→v3.8)의 학술 backbone으로 **충분하고 적절**한가? 빠진 핵심 영역이 있다면 무엇인가?

### Q2. Tier 0 reading 우선순위
v3.8 6M Mom 가속 + Quality-Profit 도입 결정을 위해 위 Tier 0 4편이 **올바른 우선순위**인가? 다른 순서·다른 자료를 추천한다면?

### Q3. 한국시장 특수성 인식
한국시장의 "음의 모멘텀" 현상이 위 자료들에서 충분히 다뤄지는가? v3.8 6M Mom 가속이 한국에서 작동할 가능성은? 위험 신호가 있다면?

### Q4. v3.8 설계 방향
GP/Assets + 6M Mom 가속 두 팩터 추가만으로 v3.6 대비 -1.57%p alpha 회복이 가능할까? 노지혜 외 2023의 "수익성·투자·비유동성" robust 발견을 고려하면, 다른 팩터(예: 투자/자산성장률)도 함께 검토해야 하는가?

### Q5. v4.0 영역 2 한국화
손삼호·윤보현 2019 (스마트베타 국면전환)이 v4.0 영역 2의 직접 template이 될 수 있는가? Cooper-Gutierrez-Hameed 2004가 한국에서 음의 모멘텀으로 나타난다는 발견(엄철준 외 2020)을 고려할 때, 한국식 regime detector는 어떻게 다르게 설계해야 하는가?

---

## 5. GPT 답변 후 진우님이 할 일

1. GPT 답변을 받아서 위 5개 질문 각각의 답변 정리
2. Claude에게 답변 공유 (이 파일에 추가하거나 새 메시지로)
3. Claude가 GPT 의견과 자체 분석을 종합하여 최종 reading 순서와 v3.8 설계 방향 확정
4. Tier 0 reading 시작

---

## 6. 부록 — 핵심 사실 요약 (GPT가 알아두면 좋음)

**우리가 백테스트에서 직접 관찰한 사실**:
- 한국 18종목 universe에서 단순 12M momentum 추가는 연 -2.11%p alpha 손실
- BAB 임계값 완화(0.7/0.9/1.1/1.3 → 0.4/0.7/1.2/1.5)로 -0.54%p 회복
- 반도체 trio(β 1.2-1.4)의 BAB 페널티가 alpha 손실 주요 원인
- KT&G β=0.26 진정한 방어주, 한미반도체 β=1.33 시장 동조 종목

**한국시장에 대한 학술적 합의 (수집 자료 기준)**:
- 한국 단순 12M momentum: 음(-) 또는 무의미 (엄철준 외 2020·2021·2023, 한민연-강형구 2017)
- 한국 1M reversal: 유의 (엄철준-박종원 2023)
- 한국 GP/Total Assets: 양(+) 작동 (안제욱-김규영 2014)
- 한국 마법공식(ROIC + EY): 작동 (우동호 외 2023)
- 한국 가치프리미엄: 작동, 하락기에 더 강화 (이관영 2019)
- 한국 8요인 25년 robust: 수익성·투자·비유동성 (노지혜 외 2023)

**제약 조건**:
- 진우님은 직장인 → 매매 빈도 낮음 (월간 리밸런싱)
- 18종목 대형주 universe → 소형주 효과 적용 어려움
- 운영: GitHub Actions 자동화 + OneDrive 동기화
- 데이터: FDR(가격) + DART API(분기 재무)
