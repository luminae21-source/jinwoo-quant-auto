# 진우퀀트 v4.0 영역 2 — 한국식 5요소 regime detector 설계 (MVP)

> 작성: 2026-06-03
> 짝 코드: `regime_detector_v40.py` (self-test 16 checks 통과)
> 프레임워크: 손삼호·윤보현 2019(5요소 결합) + 이정환 외 2023(VKOSPI 비대칭)

---

## 0. regime detector란 (한 줄)

"지금 시장이 RISK_ON / NEUTRAL / RISK_OFF 중 어디인가"를 5개 지표로 자동 판별하는 스위치.
판별 결과가 매매룰의 **투자 비중(invest_frac)과 헤지 ON/OFF**를 자동으로 정한다.
→ 매매룰의 단순 VKOSPI 버전(Layer 3/5)을 **5요소로 흡수·고도화**한 것.

논문 효과(손삼호·윤보현 2019): 연수익 10.26%→20.69%, MDD −46%→−12.5%. **주로 큰 손실 회피에서 옴.**

---

## 1. 5요소 (각 −1=위험 ~ +1=안전)

| # | 요소 | 신호 정의 | 데이터 | 지금 가동? |
|---|---|---|---|---|
| 1 | **지수추세** | KOSPI가 60/120/200일 MA 위에 몇 개 (3개=+1, 0개=−1) | FDR(KS11) | ✅ |
| 2 | **VKOSPI(비대칭)** | 수준(<18 +1 … ≥32 −1) + **급등 시 추가 페널티**(하락엔 보너스 X) | KRX VKOSPI / 실현변동성 대체 | ✅(proxy) |
| 3 | **수급** | 외국인+기관 20일 순매수 누적 z → tanh | pykrx | ⏳ 데이터 연결 후 |
| 4 | **섹터집중** | picks의 top 섹터 비중 (≤25% +1, ≥45% −1) | JINWOO 산업맵 | ✅ |
| 5 | **팩터 ON/OFF** | 전략 트레일링 초과수익(최근 3M vs KOSPI) 부호 | 자체 백테스트 | ⏳ 연결 후 |

**비대칭(이정환 2023 개념)**: VKOSPI 급등엔 **빠르게** 위험회피, 하락엔 **천천히** 복귀. `vol_signal`의 급등 페널티 + `classify_regime`의 비대칭 hysteresis로 구현.

**graceful degradation**: 데이터 없는 요소(수급·팩터)는 None → 종합에서 빼고 가중치 재정규화. **지금은 FDR만으로 1·2·4(3요소) 가동**, 수급(pykrx)·팩터(백테스트) 붙이면 5요소 완성.

---

## 2. 종합 → regime → 익스포저

```
score = Σ wᵢ·signalᵢ / Σ wᵢ   (None 제외 재정규화)
가중치(기본): trend .30 / vol .25 / flow .20 / concentration .10 / factor .15  ← 백테스트 튜닝

비대칭 hysteresis:
  RISK_OFF 진입: score ≤ −0.20  (빠르게)
  RISK_OFF 이탈: score > +0.10 필요 (천천히)
  RISK_ON: score ≥ +0.30, 그 외 NEUTRAL

regime → (invest_frac, hedge):
  RISK_ON  → (1.00, OFF)
  NEUTRAL  → (0.90, OFF)
  RISK_OFF → (0.60, ON)   # KODEX 인버스 1X, 매매룰 §6
```

⚠️ 가중치·임계값·hysteresis는 **본 구현(our implementation)**이다. 논문의 정확한 결합식이 아니라 5요소 프레임워크를 따른 합리적 MVP. 백테스트로 검증·튜닝 대상.

---

## 3. 매매룰과의 통합

매매룰(`진우퀀트_v37_2_매매룰.md`)의:
- **Layer 3 VKOSPI 익스포저** → `detect(...)['invest_frac']`로 대체
- **Layer 5 헤지 ON/OFF** → `detect(...)['hedge_on']`로 대체

즉 `backtest_v372_rules.py`의 `vkospi_invest_frac()` / `market_regime()`를 `regime_detector_v40.detect()` 출력으로 교체하면 5요소 버전 백테스트가 된다. (다음 iteration)

---

## 4. ⚠️ 정직한 prior (진우 철학과 정합)

이 detector도 **"위험 줄이기" 오버레이**다. 진우 님 시스템은 (a) 초저 turnover, (b) 한국 reversal을 타는 게 엣지였다. 따라서:
- regime de-risking은 **수익을 깎고 MDD를 줄이는** trade-off일 가능성이 큼. v3.7.2 MDD가 이미 −12%라 개선 여지가 작다.
- **가장 큰 가치는 "공포장 큰 손실 회피"**(논문도 그 효과). 평상시엔 거의 RISK_ON이라 영향 적게 설계(NEUTRAL도 90%).
- 백테스트에서 **regime이 base를 못 이기면 끄는 게 맞다**(단순함 우선). 이건 가설 검증이지 채택 전제 아님.

진짜 우선순위였던 **반도체 44% 집중**은 요소 4(섹터집중)가 *신호*로는 잡지만, *근본 해결*은 **영역 3 universe 확장**이다.

---

## 5. 다음 단계
1. ✅ 5요소 detector MVP (`regime_detector_v40.py`) — 3요소 가동, self-test 통과
2. ⏳ 수급(pykrx)·팩터 ON/OFF 데이터 연결 → 5요소 완성
3. ⏳ `backtest_v372_rules.py`의 sizing/헤지를 `detect()`로 교체 → regime 백테스트
4. ⏳ 합격(net alpha ≥ base, MDD↓) 시 매매룰에 반영, 아니면 보류
5. ⏳ 영역 3(universe)로 반도체 집중 근본 해결

---

## 6. 소스
- [손삼호·윤보현 (2019) 스마트베타 위험요인 결합 투자전략, KJFS 48(3)](https://www.e-kjfs.org/upload/pdf/kjfs-2019-48-3-257.pdf)
- 이정환 외 (2023) VKOSPI 비대칭 (한국 변동성 국면) — 개념 적용
