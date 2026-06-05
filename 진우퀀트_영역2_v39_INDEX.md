# 진우퀀트 — 영역 2 + v3.9 작업 INDEX (2026-06-03)

이번 작업으로 추가된 파일 한눈에. (코드는 모두 repo 루트에 둠 — import 경로 때문)

## ✅ 결정 완료 — 영역 2 매매룰
- `진우퀀트_v37_2_매매룰.md` — 매매룰 정의 + **§13 백테스트 판정(오버레이 기각, v3.7.2 base 유지)**
- `진우퀀트_영역2_백테스트_쉬운정리.md` — 결정 근거를 쉽게 풀어쓴 글
- `backtest_v372_rules.py` — 매매룰 백테스트(기각 근거 산출). 더 돌릴 필요 없음.
- `진우퀀트_백테스트_실행가이드.md` — 위 백테스트 실행법(참고용, 역할 종료)

## ▶ 지금 할 것 — 수익 레버 2개
- `진우퀀트_수익레버_gradecut_v39_가이드.md` — **여기부터 읽기**
  - **A. grade-cut S+/S** (검증완료, 즉시 가능): `score_v37_2.py` 한 줄. 진우 결정.
  - **B. v3.9 EarnMom** (검증 필요): 아래 실행.
- `backtest_v39_pit.py` — **실행: `python backtest_v39_pit.py`** → base vs +EarnMom PIT 검증. (분기 ROE CSV + FDR 사용)

## 🔮 보류 (v4.0 / 영역 3)
- `regime_detector_v40.py` + `진우퀀트_v40_regime_detector_설계.md` — 5요소 regime detector(매매룰 백테스트에선 미채택, v4.0용 보존)
- 영역 3(universe 확장, 반도체 집중) — "리스크가 더 걱정될 때" 카드

## 실행 환경
- 모두 repo 루트(`C:\Users\긍정적인_삶의자세\Desktop\진우퀀트`)에서 실행.
- `python <파일>.py --selftest` → 네트워크 없이 로직만 점검(있는 파일: backtest_v372_rules, regime_detector_v40, backtest_v39_pit).
- 실데이터 실행은 FDR(+v3.9는 quality_timeseries_summary.csv) 필요.
