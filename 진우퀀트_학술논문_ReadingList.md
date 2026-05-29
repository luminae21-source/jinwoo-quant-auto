# 진우퀀트 학술 논문 Reading List

작성일: 2026-05-24
대상: v3.8 (Option 3) + v4.0 영역 2 (Option 2) 학술 기반 강화
독자: 진우 (직장인, 모바일 중심, 매매 빈도 낮음)

---

## 우선순위 요약

| Tier | 시점 | 논문 수 | 누적 시간 |
|---|---|---|---|
| 1 | v3.8 코딩 병행 (1-2주) | 2편 | 약 3-4시간 |
| 2 | v4.0 준비 (2-4주) | 2편 | 약 4-5시간 |
| 3 | 장기 참고 (1-2개월) | 3편 | 약 5-6시간 |

총 7편 / 약 12-15시간 (출퇴근 30분씩 1개월 분량)

---

## Tier 1 — 즉시 (v3.8 코딩 병행)

### 1. Novy-Marx (2013) — "The Other Side of Value: The Gross Profitability Premium"
- **저널**: Journal of Financial Economics 108(1), 1-28
- **SSRN**: https://ssrn.com/abstract=1598056
- **분량**: 본문 약 25페이지 + 부록
- **읽는 데 걸리는 시간**: 약 1.5시간 (수식 건너뛰기 시 1시간)

**핵심 주장**
- Gross Profit / Total Assets가 ROA·ROE보다 강력한 미래 수익률 예측 지표
- 이유: GP는 매출원가만 차감한 "raw profitability"라 회계 노이즈 적음
- US 1962-2010 데이터로 월간 alpha 0.40%~0.65% 입증

**진우퀀트에 적용할 것**
- v3.8 Quality-Profit 팩터의 직접 근거
- GP/Total Assets ≥ 동종업종 75 percentile → +1점
- DART에서 "매출액 - 매출원가" / "자산총계" 분기 계산

**읽을 때 집중할 부분**
- Section 3 "Predicting cross-sectional returns" (실증 결과)
- Section 4.1 "The interaction with value" (PBR과의 결합 효과)
- 수식은 t-stat·sharpe만 확인하고 건너뛰기 OK

---

### 2. 김민기 (2014) — "한국 주식시장에서의 모멘텀 효과와 단기-중기 가속도"
- **저널**: 재무연구 27권 4호 (한국재무학회)
- **DBpia/KCI 검색**: "김민기 모멘텀 가속 2014" 또는 "Momentum Acceleration Korea"
- **분량**: 약 30페이지
- **읽는 데 걸리는 시간**: 약 1.5시간 (한국어이므로 빠름)

**핵심 주장**
- 한국시장에서 6M momentum이 12M momentum보다 강함
- "가속(acceleration)" = 6M return - 12M return → 추세 강화 신호
- KOSPI 2001-2013 OOS에서 월 0.8% alpha 검출
- 7-12월 보유 후 약화 → 12M 단독보다 6M 비중 높여야

**진우퀀트에 적용할 것**
- v3.8 6M Momentum 가속 팩터
- (6M return - 12M return) ≥ 5%p → +1점
- 기존 Mom12와 충돌 시 6M이 신호 강도 결정

**읽을 때 집중할 부분**
- Section 2 "한국시장 모멘텀 특성" (미국과 차이)
- Section 4 "가속도 정의와 백테스트" (구현 가이드)
- Table 3-5 (Sharpe·turnover 수치)

---

## Tier 2 — v4.0 준비 (다음 2-4주)

### 3. Cooper, Gutierrez & Hameed (2004) — "Market States and Momentum"
- **저널**: Journal of Finance 59(3), 1345-1365
- **SSRN**: https://ssrn.com/abstract=299927
- **분량**: 본문 약 22페이지
- **읽는 데 걸리는 시간**: 약 1.5시간

**핵심 주장**
- 모멘텀 alpha의 거의 전부는 "Up State"에서 발생
- Up State (직전 36M 시장수익률 > 0): 모멘텀 +0.93% / 월
- Down State: 모멘텀 -0.37% / 월 (오히려 reversal)
- 결론: regime 필터 없으면 모멘텀이 시장하락기에 손실

**진우퀀트에 적용할 것**
- v4.0 영역 2의 핵심 근거 — 시장상태에 따라 Mom12 가중치 조정
- KOSPI 36개월 수익률 > 0이면 Mom12 가중 2배, 아니면 0.5배
- v3.7.1 BAB도 이 framework 안에 흡수될 수 있음

**읽을 때 집중할 부분**
- Section 2 "Methodology and data" (Up/Down state 정의)
- Section 3 Table 2 (수익률 분해)
- Section 5 결론 (실무 implications)

---

### 4. Faber (2007) — "A Quantitative Approach to Tactical Asset Allocation"
- **저널**: Journal of Wealth Management 9(4), 69-79
- **SSRN**: https://ssrn.com/abstract=962461
- **분량**: 약 15페이지 (짧음)
- **읽는 데 걸리는 시간**: 약 1시간

**핵심 주장**
- 10개월 (≈200일) 이동평균 위면 보유, 아래면 현금
- 1900-2008 미국주식 적용 시 Sharpe 0.41 → 0.78
- MDD -83% → -50%
- 매매 빈도 연 1-2회 (저빈도 적합)

**진우퀀트에 적용할 것**
- v4.0 영역 2 timing filter — KOSPI 200일 MA 기준
- KOSPI < 200d MA이면 신규 진입 중단 또는 등급 한 단계 하향
- 진우님 매매 빈도 낮은 스타일과 매우 잘 맞음
- v3.7.1과 자연스럽게 결합 가능

**읽을 때 집중할 부분**
- Page 4-6 Figure 1-2 (200d MA 시각화)
- Table 3 (MDD 감소 효과)
- Page 9 "Implementation" (실무 적용)

---

## Tier 3 — 장기 참고 (1-2개월 내 천천히)

### 5. Asness, Moskowitz & Pedersen (2013) — "Value and Momentum Everywhere"
- **저널**: Journal of Finance 68(3), 929-985
- **SSRN**: https://ssrn.com/abstract=1363476
- **분량**: 본문 약 40페이지 (길다)
- **읽는 데 걸리는 시간**: 약 2.5시간

**핵심 주장**
- Value + Momentum 결합은 8개 자산군 모두에서 alpha 생성
- 두 팩터는 **음의 상관관계** → 결합 시 Sharpe 1.5+ 가능
- 한국주식도 포함된 글로벌 증거
- Funding liquidity가 공통 risk factor

**진우퀀트에 적용할 것**
- v3.8 이후 Value (PBR·EV/EBITDA) 추가 시 근거
- v4.0 Macro factor 확장 시 funding liquidity 변수 검토
- 현재 v3.6 F-score(Value 성격)와 v3.7 Mom12 결합이 이 논문 결론과 일치

**읽을 때 집중할 부분**
- Section 4 "Comomvement of value and momentum" (음의 상관)
- Table V (글로벌 Sharpe)
- Section 7 "Why does it work" (이론적 설명, 선택 사항)

---

### 6. Whaley (2009) — "Understanding VIX"
- **저널**: Journal of Portfolio Management 35(3), 98-105
- **SSRN**: https://ssrn.com/abstract=1296743
- **분량**: 약 8페이지 (매우 짧음)
- **읽는 데 걸리는 시간**: 약 40분

**핵심 주장**
- VIX > 30이면 "fear gauge" 발동, 30일 후 평균 +2.5% 반등
- VIX는 미래 변동성보다 "현재 공포 수준" 측정
- 매도 압력 peak 신호 → contrarian buy 타이밍

**진우퀀트에 적용할 것**
- 한국 적용 시 VKOSPI 사용 (한국거래소 발표)
- VKOSPI > 25 (김창권 2014 한국 임계값) → 신규 진입 가속
- v4.0 영역 2 "위기 감지 → 진입 강화" 룰의 근거

**읽을 때 집중할 부분**
- 전부 읽어도 짧음 (8페이지)
- Figure 1-2 (VIX vs 향후 수익률)

---

### 7. Bernard & Thomas (1989) — "Post-Earnings-Announcement Drift"
- **저널**: Journal of Accounting Research 27, 1-36
- **JSTOR**: https://www.jstor.org/stable/2491062
- **분량**: 본문 약 30페이지
- **읽는 데 걸리는 시간**: 약 2시간

**핵심 주장**
- 어닝 서프라이즈 후 주가가 60일에 걸쳐 천천히 반영
- Top SUE decile vs Bottom 60일 spread = +3.2%
- 시장 참여자의 정보 처리 지연

**진우퀀트에 적용할 것**
- v3.9 또는 v4.0 PEAD 팩터 도입 시 직접 근거
- 분기 어닝 발표 후 60일 이내 신호 활용
- 단, 한국시장 PEAD는 미국보다 약함 (적용 신중)

**읽을 때 집중할 부분**
- Table 5-6 (decile spread 수치)
- Section 4 "Interpretation" (왜 일어나는가)
- 한국 적용 가능성은 별도 한국논문 (김ㅇㅇ 등) 추가 검토 필요

---

## 출퇴근 30분 기준 추천 일정

```
주 1 (이번 주):
  월-수: Novy-Marx 2013 (Tier 1)
  목-금: 김민기 2014 (Tier 1)

주 2:
  월-수: Cooper-Gutierrez-Hameed 2004 (Tier 2)
  목-금: Faber 2007 (Tier 2, 짧음)

주 3-4 (천천히):
  Asness-Moskowitz-Pedersen 2013

주 5-6:
  Whaley 2009 (짧음) + Bernard-Thomas 1989
```

각 논문 읽은 후 진우퀀트 폴더에 한 줄 메모 권장:
- "이 논문에서 우리 시스템에 추가할 만한 것"
- "이 논문이 현재 가설을 흔드는가"

---

## 한국어 자료 보조

영어 원문이 부담스러우면 다음을 우선 참고:
- 김민기 2014 (한국어 원문)
- Faber 2007 → "Meb Faber 한국어 요약 블로그" 다수 존재
- Cooper-Gutierrez-Hameed → 한국증권학회지 후속 논문이 인용·해설
- Novy-Marx → 박종원 (2018) "수익성 팩터의 한국시장 검증" 등 후속 한국연구

---

## 읽기 후 액션

각 Tier 완료 시:
- **Tier 1 끝나면** → v3.8 점수 공식 최종 확정 (6M 가속 +1점, GP/Assets +1점 등)
- **Tier 2 끝나면** → v4.0 영역 2 regime detector 설계 시작 (KOSPI 200d MA + VKOSPI 25 룰)
- **Tier 3 끝나면** → v4.0 영역 2 종합 설계 문서 작성

---

## 비고

- 모든 SSRN 논문은 무료 다운로드
- JSTOR 일부 논문은 공공도서관 ID로 무료 접근 가능
- 모바일 PDF는 Acrobat Reader / GoodReader / 클라우드 뷰어 권장
- 출퇴근 중 음성 읽기 (TTS) 활용 시 더 빠름
