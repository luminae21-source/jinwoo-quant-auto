# 진우퀀트 — 투자 프레임워크 근거자료 (Evidence Base)

> 작성일: 2026-06-13 (Cowork) · 원칙: **자료 없는 투자계획 금지.** 모든 권고는 1차 출처 + 검증된 원문 발견 + 한국 적용 캐비엇과 묶는다.
> ⚠️ 투자자문 아님. 출처·근거 정리. 매매는 본인 책임.

---

## 0. 원칙

대가 "철학"을 인용할 때, **그 사람이 실제로 쓴 논문/책/메모**와 **그 원문이 검증 가능하게 말한 것**만 근거로 쓴다. 한국·진우퀀트 표본에 자동 적용되지 않는 부분은 *캐비엇*으로 명시. 검증 안 된 인용(인터뷰 전언 등)은 증거등급을 낮춰 표기.

---

## 1. 팩터 엔진의 학술 근거 (이미 production에 반영)

| 팩터 | 1차 출처 | 검증된 발견 |
|---|---|---|
| F-Score(퀄리티) | Piotroski (2000) *J. Accounting Research* 38 | 9요소 재무건전성으로 저PBR 내 승자 선별 |
| 발생액(Sloan) | Sloan (1996) *Accounting Review* 71 | 낮은 발생액 = 이익의 질↑ → 초과수익 |
| 총수익성 | Novy-Marx (2012) *JFE* 108 | 매출총이익/자산이 ROE보다 강한 퀄리티 신호 |
| 자산성장 | Cooper, Gulen, Schill (2008) *J. Finance* 63 | 낮은 자산성장 = 초과수익(과투자 회피) |
| 12M 모멘텀 | Jegadeesh & Titman (1993) *J. Finance* 48 | 3~12개월 모멘텀 지속성 |
| BAB(저베타) | Frazzini & Pedersen (2014) *JFE* 111 | 저베타 위험조정 초과수익 |
| 한국 F적용 | 한상욱 (2015) | 한국시장 F-Score 유효성 |

→ 진우퀀트 Phase3 검증: 이 정적 팩터들이 lookahead로 부풀지 않음(PIT≈static) — `pit_fscore_phase3.py`.

### 1-Q. 퀄리티 종합 — Quality Minus Junk (Asness 외)

**1차 출처:** Asness, C.S., Frazzini, A., Pedersen, L.H. **"Quality Minus Junk."** *Review of Accounting Studies* 24 (2019); draft 2017-06-05, SSRN-2312432.
**📄 원문 PDF 직접 검증** (진우 업로드, 로컬·git 제외): `QMJ_Asness2017.pdf`.

**원문 직접 인용:**
- (초록) "a quality security… an investor should be willing to pay a higher price for: **stocks that are safe, profitable, growing, and well managed**." → 퀄리티 4축(안전·수익성·성장·지배구조). 진우 Q합성(GPA·ROE·저발생액·저자산성장)이 수익성+안전축에 매핑.
- (초록) "High-quality stocks… have higher prices on average **but not by a very large margin**… high-quality stocks have **high risk-adjusted returns**." → 시장이 퀄리티에 *과소지불* = 초과수익 원천.
- (초록) "**quality at a reasonable price (QARP)**… goes back at least to **Graham and Dodd (1934)**… consider the price as well as the quality." → **QARP = 퀄리티+밸류 결합 = 진우 ValueQuality(VQ) 합성의 정확한 근거.**
- (초록) "the price of quality… **reaching a low during the internet bubble**, and **a low price of quality predicts a high future return of QMJ**." → 버블기엔 퀄리티가 싸지고(언더퍼폼), 그 후 반등.

**캐비엇 (원문 확인):** 표본 24개국 = MSCI 선진국(일본·홍콩·싱가포르·호주 포함). **한국(MSCI 신흥) 미포함.**

**→ 진우퀀트 재해석 (중요):** 제 검증의 "한국 퀄리티 단독 IR −0.29"는 *퀄리티 무용*이 아니라 **2021-26 AI/반도체 버블기의 예상된 언더퍼폼**(QMJ: 버블기 퀄리티 싸짐). QMJ는 *그 후 반등*을 예측 → **VQ를 '버블 되돌림 대비 크래시 보험'으로 보는 §2·§3 결론을 원문이 직접 뒷받침**(퀄리티 = distress기 flight-to-quality 자산). 즉 음의 IR은 반박이 아니라 *타이밍*의 문제.

**→ 진우 데이터 한국 실증 (2026-06-13, 가설→증거 전환):** 직전 12M 모멘텀 누적으로 국면 분리. **버블기(모멘텀强): VQ가 모멘텀에 월 −4.5%p 언더퍼폼**(QMJ "버블기 퀄리티 싸짐" ✅). **모멘텀 최악 10개월(크래시): VQ +9.6%p 압도**(QMJ "이후 반등" ✅). 완만한 되돌림기엔 −0.58%p(거의 동등). 상관(VQ−Mom vs 12M모멘텀)=−0.30. **결론: QMJ 명제는 한국서도 성립하되 반등이 *꼬리(크래시)에 집중* = 일상우위 아닌 보험금 지급형.** (대가 선진국 가설을 진우 한국 데이터로 검증 완료.)

**보강 실증 — QARP (Maury 2017):** Maury, B. **"Quality at a Reasonable Price: The Role of Investors' Portfolio Weights."** *Nordic J. of Business* 66(1), 2017. 📄 `QARP_Maury2017.pdf`(원문 직접 검증). **핀란드** 100만+ 투자자 포트폴리오 데이터로, "value+quality at a reasonable price(QARP)" 성과에 **소유 집중도(ownership/portfolio concentration) 변화**를 신호로 더하면 (조건부) 개선됨을 확인. → ① QARP(=진우 VQ)가 학계서 다뤄지는 정식 전략임을 보강(Novy-Marx·Piotroski·Asness 계보 인용) ② **소유·수급 집중도 = 밸류/퀄리티 픽의 확인신호** 아이디어 → 진우 Track W `catalyst_scan`의 *수급(C)* 활용과 직접 연결. ⚠️ 증거등급: 단독저자·NJB·**핀란드 표본(한국 아님)** → AQR 논문보다 *보조적*.
**→ 진우 데이터 한국 검증(2026-06-13~14): 양시장 모두 미성립 → 기각. [정정]**

1차 탐색(`maury_kospi_test`, **vs EW 벤치**)에선 KOSPI가 IR_EW +0.91로 "성립"처럼 보였으나 — **v42 동급 사전등록 게이트(MKT알파+IC, `backtest_v43_kospi_flow.py`·동결 2026-06-14)로 1회 판정하니 전 변형 FAIL:**

| 시장 | IC | MKT알파 | IR_MKT | 판정 |
|---|---|---|---|---|
| KOSDAQ (v42) | ≈0 | 음수 | 음수 | ❌ |
| **KOSPI (v43)** | **≈0** (0.005~−0.027) | **음수** (−0.6~−3.7%p) | **≈0** | ❌ |

- **왜 EW에선 양성처럼 보였나:** 수급 픽이 EW를 이긴 건 **대형주 틸트**(외국인·기관=대형주 매수)일 뿐 → **시총가중 시장(MKT) 대비 알파는 0.** IR_EW +0.91 = 벤치 아티팩트. 사전등록 게이트가 *가짜 양성*을 적발.
- **결론(정정): 수급은 한국 양시장(KOSPI·KOSDAQ) 모두 종목선정 팩터 아님 → Maury(핀란드) 비전이, 기각.** v42 KOSDAQ 기각이 옳았고 KOSPI도 동일. (QMJ는 확인→채택과 대조.)
- **★ 방법론 교훈(중요):** 탐색은 *vs EW*로 가짜 양성이 나올 수 있다(대형주/저변동 틸트). **채택 판정은 반드시 *vs MKT + IC*(사전등록 동결)로** 해야 진짜 종목선정 알파를 가린다. — 이게 진우퀀트 검증규율의 핵심.

### 1-B. 저베타 — Betting Against Beta (Frazzini·Pedersen)

**1차 출처:** Frazzini, A., Pedersen, L.H. (2014). **"Betting Against Beta."** *JFE* 111; draft 2013-05-10.
**📄 원문 PDF + 실데이터 직접 검증** (진우 업로드, 로컬): `BAB_FrazziniPedersen2014.pdf`, `BAB_EquityFactors_Monthly.xlsx`(AQR 월간 BAB 팩터 실데이터).

**원문 직접 인용:** "constrained investors bid up high-beta assets, **high beta is associated with low alpha**" · "**BAB factor**(long leveraged low-beta, short high-beta) produces **significant positive risk-adjusted returns**" · "when funding constraints tighten, the return of the BAB factor is low." → 진우 BAB 팩터(저베타 +)의 정확한 근거(레버리지 제약 메커니즘).
**캐비엇(데이터 확인):** 표본 = 미국 + 23개 시장(컬럼 AUS·CAN·GBR·HKG·JPN·SGP…USA = 24 선진국). **한국(KOR) 없음.**

### ★ 메타 결론 (원문으로 확정 — 가장 중요)

**AQR 3대 팩터 출처가 모두 한국을 표본에서 제외한다:**

| 논문 | 표본 | 한국 포함 |
|---|---|---|
| Value & Momentum Everywhere (2013) | 미·영·유럽·일본 주식 + 자산군 4 | ✗ |
| Quality Minus Junk (2017/19) | 24 MSCI 선진국(일·홍·싱·호 등) | ✗ |
| Betting Against Beta (2014) | 미국 + 23 선진국 | ✗ |

→ **진우퀀트의 팩터(F·BAB·모멘텀·밸류·퀄리티)를 한국에 적용하는 것은 이 논문들이 직접 검증한 바가 아니다(out-of-sample).** 한국에서의 유효성 근거는 **진우 님 본인의 PIT 백테스트**다(모멘텀·Q→Mom 유효 IR +0.8~1.0 / 밸류·퀄리티는 레짐의존). **이게 "자료 없는 계획 금지" 원칙의 가장 중요한 귀결 — 대가 논문은 *방향(가설)*을 주지만, 한국 적용의 *증거*는 자체 PIT 검증이어야 한다.** (대가 인용으로 한국 결과를 정당화하면 안 됨.)

---

## 2. 밸류+모멘텀 결합 — Asness 외 (2013)

**1차 출처:** Asness, C.S., Moskowitz, T.J., Pedersen, L.H. (2013). **"Value and Momentum Everywhere."** *The Journal of Finance* 68(3): 929-985. [AQR 무료 PDF](https://www.aqr.com/Insights/Research/Journal-Article/Value-and-Momentum-Everywhere) · [Wiley](https://onlinelibrary.wiley.com/doi/10.1111/jofi.12021)
**📄 원문 PDF 직접 검증** — `ValMomEverywhere_Asness2013.pdf`(진우 업로드, 로컬 보관·git 제외). 아래는 *검색요약이 아니라 원문에서 직접 확인*한 인용.

**원문이 말하는 것 (PDF 직접 인용):**
- (초록, p929) "We find consistent value and momentum return premia across **eight diverse markets and asset classes**… **value and momentum are negatively correlated with each other, both within and across asset classes**."
- (p930) 8개 = "individual stocks in the **United States, the United Kingdom, continental Europe, and Japan**; country equity index futures; government bonds; currencies; and commodity futures." → **주식 4개(미·영·유럽·일본) + 자산군 4개.**
- (p939) **50/50 COMBO** = `0.5·value + 0.5·momentum`. 본문: "a simple equal-weighted combination of value and momentum is **immune to liquidity risk and generates substantial abnormal returns**" → 결합의 핵심 이점.
- (초록) 논문 스스로 "기존 이론은 largely focus on **U.S. equities**"라 명시 → 비표본 시장 적용엔 주의 필요(아래 캐비엇의 근거).

**중요 캐비엇 (한국 적용) — 원문으로 확정:**
- 표본 주식시장 = 미·영·유럽·일본 4개. **한국(KOSPI/KOSDAQ) 미포함**(p930 원문 확인).
- **진우퀀트 데이터(KOSPI top-200, 2021-2026)에선 밸류·모멘텀 상관 = +0.57(양수)** — Asness의 선진국 음의상관과 *반대*. 즉 음의상관은 한국 대형주에 *자동 적용 안 됨*. (`(b) 모멘텀 크래시 스트레스 테스트`)

**그럼에도 진우퀀트에 적용되는 부분 (데이터로 확인):**
- 일상 분산효과는 약하나(+0.57), **꼬리(모멘텀 최악월)에선 밸류가 보험 작동**: 최악 6개월 평균 모멘텀 −15.4% vs 밸류 −6.8% vs ValueQuality −5.0%, 2025-11 크래시엔 VQ +9.6%.
- → **적용:** 소량 ValueQuality 슬리브를 "수익"이 아니라 **꼬리 크래시 보험**으로. 보험료 = 강세장 기회비용. (Asness의 결합논리를 한국 표본으로 *수정* 적용.)

---

## 3. 고점·사이클 리스크 — Howard Marks (Oaktree 메모)

**1차 출처:** Howard Marks, Oaktree Capital 메모. [Oaktree 'Is It a Bubble?'](https://www.oaktreecapital.com/insights/memo/is-it-a-bubble)
**📄 원문 PDF 직접 검증** (진우 업로드, 로컬 보관·git 제외): `Marks_IsItABubble.pdf`, `Marks_ImpactOfDebt_transcript.pdf`, `Marks_NoDifferentThisTime_2007.pdf`, `Marks_CompleteCollection.pdf`.

**원문 직접 인용 (PDF에서 확인):**
- ("Is It a Bubble?") 부채 3가지: "**it magnifies losses if there are losses** (just as it magnifies the hoped-for gains…), it increases the probability of a venture failing…" → 부채는 손실 증폭.
- ("Is It a Bubble?") "The **fear of missing out, or FOMO**, attracts even more participants… reinforcing this positive feedback loop." + "The AI data centre boom was never going to be financed with cash alone… the investments and **leverage have to be described as aggressive**." → AI 붐의 레버리지 경고(반도체와 직결).
- ("Is It a Bubble?") "There can be no way to **participate fully in the potential benefits… without being exposed to the losses** that will arise if the enthusiasm proves [unjustified]." → 참여=하방 노출, 공짜 없음(트림·사이징 규율의 근거).
- ("No Different This Time", 2007) "leverage doesn't make investments better; **it just magnifies the gains and losses**" + "many **reached for return**… making riskier investments or using leverage." → **'수익을 좇아(reach for return) 위험·레버리지를 키우는 것'이 위기의 원인** = 공격형 grade-cut의 정확한 경고.
- ("Impact of Debt") "Volatility + Leverage = Dynamite" + "real risk is **self-reinforcing**… on the heels of good times, people forget the possibility of negative outcomes." → 강세장에 위험을 잊는 자기강화(현 과열 구간).

**진우퀀트 적용:**
- 반도체 슈퍼사이클(HBM 2028까지, 실재) **참여 유지**하되, **레버리지·공격형 과집중으로 고점 베팅 금지** = `gradecut_tracker.py` **RED 신호**와 일치.
- 2차사고: "HBM 호황"(1차, 다 안다) vs "이미 가격 반영됐나, 지금 비대칭은?"(2차) — 한미반도체 현재가 > 애널 목표가가 답의 일부.

---

## 4. 모멘텀·테마 청산룰 — O'Neil / Minervini (Track W용)

**1차 출처:**
- O'Neil, William J. **"How to Make Money in Stocks."** (CANSLIM) — `ONeil_HowToMakeMoney.pdf` 📄 **원문 직접 검증**.
- Minervini, Mark (2013). **"Trade Like a Stock Market Wizard."** (SEPA®) — 📄 **원문 텍스트 직접 검증**(진우 제공 DOCX, 스캔 PDF는 텍스트 0이라 DOCX로 대체).

**원문이 말하는 것 (모두 원문 직접 인용):**
- **O'Neil:** "…**cut losses at 8%**… You could be wrong twice and right once and still not get [hurt]." → −8% 무조건 손절. 주도주·신고가 진입(CANSLIM).
- **Minervini (verbatim):**
  - SEPA 랭킹: "Stocks must first meet my **Trend Template**… then screened through filters based on **earnings, sales and margins**." → 진입 = 추세(기술) + 실적·매출·마진(펀더멘털) 이중 필터.
  - **VCP**(Volatility Contraction Pattern): "establishing a precise entry point at the **line of least resistance**."
  - 손절: "If you normally **cut losses at 7 to 8 percent**, cut them at 5 to 6 percent [어려운 장]." → **O'Neil 8%와 일치(이중 출처 확정).**
  - 사이징: "I may try to **pyramid my gains** by placing a larger bet size… The key… is to **preserve capital** and wait patiently." → 승자에 피라미딩하되 자본보존 우선.
  - 관점: "**value investing does not protect you**… No magic number." → Minervini는 성장·모멘텀파(밸류 회의). 진우 엔진의 모멘텀 핵심과 정합, 밸류는 보조(꼬리보험)로만.

**진우퀀트 적용 (Track W 청산룰 명문화 — 문서화된 근거 기반):**
- 진입: catalyst scan 점등 + guardrail 통과 + thesis (이미 구현).
- **청산룰(신규 명문화):** ① **하드 손절 −8%(O'Neil)** ② 승자는 트레일링으로 +20%↑ 추구 ③ 강세 지속 시 분할 피라미딩(Minervini). → §6에 운영규칙으로 등록.

> ⚠️ **증거등급 주의:** "드러켄밀러 — 패자는 빨리 자르고 승자는 태운다"는 *인터뷰 전언*(공식 논문·책 아님)이라 보조 참고로만. **명문화 근거는 문서화된 O'Neil(−8%)·Minervini(SEPA)로 대체**한다(자료 원칙).

---

## 5. 권고 ↔ 근거 매핑 (한눈에)

| 진우퀀트 권고 | 1차 근거 | 한국 적용 상태 |
|---|---|---|
| 퀄리티+모멘텀 엔진 | Piotroski/Sloan/Novy-Marx/Jegadeesh-Titman | ✅ 데이터 검증(IR +0.8~1.0) |
| 밸류 = 꼬리 크래시 보험(VQ) | Asness et al (2013) | ⚠️ 음의상관은 한국 미적용(+0.57), 꼬리 보험은 데이터 확인 |
| 반도체 참여+트림, 레버리지·과집중 금지 | Marks (Oaktree 메모) | ✅ RED 신호·거시와 합치 |
| Track W 청산룰 −8% 손절·승자 키움 | O'Neil(1988)·Minervini(2013) | ✅ 문서화 규칙으로 명문화 |
| 18 고정 탈피·신규 리더 발굴 | (절차) PIT 사전선택 검증 | ✅ `emerging_screen.py` |

---

## 6. Track W 청산룰 (명문화, O'Neil/Minervini 근거)

```
진입(SEPA, Minervini 검증): 다음 4개 동시
  - 추세: Trend Template — 주가가 상승추세(예: 200일선 위·신고가 부근)   [기술]
  - 펀더멘털: 실적·매출·마진 개선                                      [Minervini 필터]
  - catalyst 2+ 점등 (진우 기존 catalyst_scan) + guardrail PASS
  - 진우 thesis(2분 스토리) + 무효화 조건 사전기록
사이징: 종목 ≤ 전계좌 2%, Track W 합계 ≤ 10% (기존 가드레일)
청산:
  - 하드 손절 −7~8% (O'Neil "8%" + Minervini "7 to 8 percent" 이중 출처, 무조건·재량 없음)
    · 시황 악화 시 −5~6%로 타이트닝 (Minervini)
  - thesis 무효화 발생 시 즉시 청산
  - 트레일링: 큰 수익 구간에서 고점 대비 일정%(예 −15%) 트레일
가산(선택): 강세 지속·자본보존 우선 하에 분할 피라미딩 (Minervini, 평단 상승 감수)
```
> 근거 격상: 기존 catalyst+guardrail(진우)에 **Minervini SEPA의 Trend Template(추세) + 실적·매출·마진 필터**를 진입에 추가하면, 발굴이 "촉매만"이 아니라 "추세+실적 동반"으로 정밀해짐(O'Neil 주도주 논리와 동일 계보).

> 출처 링크: Asness [AQR](https://www.aqr.com/Insights/Research/Journal-Article/Value-and-Momentum-Everywhere)·[Wiley](https://onlinelibrary.wiley.com/doi/10.1111/jofi.12021) / Marks [Oaktree](https://www.oaktreecapital.com/insights/memo/is-it-a-bubble) / O'Neil·Minervini(단행본). 팩터 논문은 README 학술백본 참조.
