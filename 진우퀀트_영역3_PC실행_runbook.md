# 영역 3 확장 모듈 — PC 실행 runbook (2026-06-05)

> **상태: §1 판정 완료 (2026-06-05 — 기각·종결, 결정메모 §11). 현행 절차는 §2(분기 재스크린 정보 트랙)만.**

> 결정메모: `진우퀀트_영역3_확장모듈_결정메모.md` (승인 완료). 추가 pip 설치 **불필요** (FDR·requests 기존 환경 그대로).
> 위치: `Desktop\진우퀀트` 에서 실행.

## 1. 판정 백테스트 (이번 1회)

```bash
# 0) 입력 캐시 재생성 (~5초, 멱등 — 세션에서 이미 생성했지만 PC에서 1회 재확인)
python make_score_inputs.py
#    기대: "universe 30 커버: 30/30 · 최신 회계연도 분포 {2025: 30}"

# 1) self-test 3종 (네트워크 불필요, ~1분)
python make_score_inputs.py --selftest
python score_univ30.py --selftest
python backtest_univ30.py --selftest

# 2) 판정 백테스트 (FDR 일별 ~150종목 수집 포함, 5~15분)
python backtest_univ30.py
```

**판정 읽는 법** (콘솔 아래쪽):

1. `[재현 게이트(구조)] fixed18 컴포넌트 일치 N건 통과` — 이 줄이 먼저 떠야 함 (에러로 중단되면 그대로 복사해서 공유)
2. `[판정 A — universe 게이트 §5A]` → ✅/❌ : u_base vs KOSPI (①ΔCAGR≥+3%p ②IR≥0.30 ③MDD 비악화)
3. `[판정 B — regime 게이트 §5B]` → u_w·u_s 각각 ✅/❌ (D §2 기준, u_base 대비)
4. 마지막 화살표 문장이 공식 결론. **`backtest_univ30_*.json`을 Claude에 공유** → 결정메모 §11 기입으로 종결.

참고: `u_ref`는 0.235% 참고 라인(판정 미사용), `fixed18`은 재현 게이트용 — u_base와 직접 비교하는 트랙이 아님 (결정메모 §10-2).

## 2. 분기 재스크린 루틴 (결정메모 §8 — 다음 분기부터)

```bash
# ⓪ 최초 1회: KOSDAQ 산업분류 보강 (시장부 → 산업 라벨, 1~2분 — 2026-06-05 추가)
python fetch_kosdaq_sector.py

# ① 신규 회계연도/누락분 DART 증분 수집 (기존 스크립트 무수정 재사용, ~수 분)
python fetch_dart_fundamentals_pit.py --codes-csv universe_rule30_latest.csv --start-year 2025 --end-year 2026 --out fundamentals_univ_increment.csv

# ② 입력 캐시 갱신 (증분 자동 병합: increment > pit > kosdaq)
python make_score_inputs.py

# ③ 월별 점수표 확인 (데이터 기준일 = 월간 패널 마지막 행)
python score_univ30.py --live
```

- 교체는 분기당 ≤2 (MAX_SWAP_Q 계승), 갱신 시 `universe_rule30_latest.csv` 교체 + 1줄 기록.
- 월간 가격 패널(`kospi_monthly_prices.csv`) 갱신이 필요해지면 `build_korea_factors.py` 재실행 (기존 스크립트).

## 3. 파일 지도 (이번 모듈 신규 4개 — production·C·D 무수정)

| 파일 | 역할 |
|---|---|
| `진우퀀트_영역3_확장모듈_결정메모.md` | Stage 0 등록본 (§2~§8 변경 금지) + §11 판정 기록 |
| `make_score_inputs.py` | fundamentals 병합 → `score_inputs_univ.csv` (636종목 F·Sloan·NOA·시장·섹터) |
| `score_univ30.py` | PIT-proxy 점수·등급·caps·시장별 비용 정의 단일화 (백테스트·live 공용) |
| `backtest_univ30.py` | 공식 엔진 6 arms 동시점 병행 + 게이트 자동 판정 → JSON |

작성: 2026-06-05 (영역 3 모듈 세션). self-test 6+20+13 checks 전부 통과 확인 후 전달.
