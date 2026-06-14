#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
진우퀀트 v3.7.2 Block Bootstrap 검증 (validate_v37_2_robustness 검증 #9 보강)

[왜 필요한가]
iid bootstrap(검증 #9)은 월별 수익을 무작위로 섞어 재표본을 만든다 → 시계열
자기상관(이번 달이 다음 달에 미치는 영향)을 무시. 모멘텀 전략은 자기상관이
있어 iid는 신뢰구간을 과신할 수 있다. Moving Block Bootstrap은 연속된 월을
"블록째" 뽑아 그 구조를 보존하므로 더 보수적·정직한 CI를 준다.

[apples-to-apples 보장]
엔진·수익률·Sharpe/CAGR 정의를 validate_v37_2_robustness 와 100% 동일하게 사용:
  - run_v37_2_backtest() : 동일한 월별 수익 시계열
  - boot_stat()          : validate_bootstrap(#9)의 Sharpe/CAGR 공식 1:1 복제
                           (ann=(1+mean)^12-1, vol=std*sqrt(12), sharpe=ann/vol,
                            cagr=(1+Π(1+r)-1)^(12/n)-1)
같은 실행에서 iid·block을 함께 산출해 직접 비교한다.

[사용법]
  python validate_v37_2_block_bootstrap.py                # 실 데이터 (PC, FDR 필요)
  python validate_v37_2_block_bootstrap.py --self-test    # 합성데이터 로직 검증 (네트워크 불필요)
  옵션: --years 4 --top-grades S+,S,A --reps 2000 --blocks 3,6,12 --seed 42
"""

import sys
import json
import argparse
from datetime import datetime
from pathlib import Path

import numpy as np

BASE = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE))

KOSPI_CAGR = 29.43   # 4년 OOS 벤치마크 (robustness #9와 동일)
V36_CAGR = 69.51


# ---- 통계: validate_bootstrap(#9)와 동일 공식 ----
def boot_stat(boot: np.ndarray):
    """재표본 1개의 (Sharpe, CAGR%) — 검증 #9와 1:1 동일 공식."""
    if boot.std() <= 0:
        return None, None
    ann = (1 + boot.mean()) ** 12 - 1
    vol = boot.std() * np.sqrt(12)
    sharpe = ann / vol
    cum = float(np.prod(1 + boot) - 1)
    cagr = (1 + cum) ** (12 / len(boot)) - 1
    return sharpe, cagr * 100


def iid_bootstrap(rets: np.ndarray, reps: int, rng) -> tuple:
    """iid resampling (= 검증 #9 재현)."""
    n = len(rets)
    S, C = [], []
    for _ in range(reps):
        idx = rng.integers(0, n, n)
        s, c = boot_stat(rets[idx])
        if s is not None:
            S.append(s); C.append(c)
    return np.array(S), np.array(C)


def moving_block_bootstrap(rets: np.ndarray, L: int, reps: int, rng) -> tuple:
    """Moving Block Bootstrap: 길이 L 연속 블록을 복원추출 → 길이 n 재구성."""
    n = len(rets)
    if L >= n:
        L = max(1, n // 2)
    starts = np.arange(0, n - L + 1)        # 겹치는(overlapping) 블록 시작점
    nb = int(np.ceil(n / L))
    S, C = [], []
    for _ in range(reps):
        chosen = rng.choice(starts, size=nb, replace=True)
        samp = np.concatenate([rets[st:st + L] for st in chosen])[:n]
        s, c = boot_stat(samp)
        if s is not None:
            S.append(s); C.append(c)
    return np.array(S), np.array(C)


def ci(arr: np.ndarray) -> tuple:
    return (round(float(np.percentile(arr, 5)), 2),
            round(float(np.percentile(arr, 50)), 2),
            round(float(np.percentile(arr, 95)), 2))


# ---- self-test (네트워크·엔진 import 불필요) ----
def self_test() -> bool:
    print("=" * 70)
    print("self-test (합성 AR(1) 데이터, 네트워크 불필요)")
    print("=" * 70)
    rng = np.random.default_rng(0)
    n, phi, mu = 49, 0.3, 0.02
    e = rng.normal(0, 0.06, n)
    x = np.zeros(n); x[0] = mu
    for i in range(1, n):
        x[i] = mu + phi * (x[i - 1] - mu) + e[i]      # 양의 자기상관
    rets = x

    checks = []
    s, c = boot_stat(rets)
    checks.append(("boot_stat 유한값", bool(np.isfinite(s) and np.isfinite(c))))

    si, ci_iid = iid_bootstrap(rets, 500, np.random.default_rng(1))
    a5, a50, a95 = ci(ci_iid)
    checks.append(("iid 표본 생성", len(si) > 400))
    checks.append(("iid CI 정렬(5≤50≤95)", a5 <= a50 <= a95))

    sb, cb = moving_block_bootstrap(rets, 6, 500, np.random.default_rng(2))
    b5, b50, b95 = ci(cb)
    checks.append(("block 표본 생성", len(sb) > 400))
    checks.append(("block CI 정렬(5≤50≤95)", b5 <= b50 <= b95))

    g = moving_block_bootstrap(rets, 100, 10, np.random.default_rng(3))  # L>=n 가드
    checks.append(("L>=n 가드 동작", len(g[0]) > 0))

    for name, ok in checks:
        print(f"  {'✅' if ok else '❌'} {name}")
    passed = all(ok for _, ok in checks)
    print(f"\nself-test: {'PASS' if passed else 'FAIL'} "
          f"({sum(ok for _, ok in checks)}/{len(checks)})")
    print(f"(참고) 합성 관측 CAGR {c:.1f}% / iid CI [{a5},{a95}] / block CI [{b5},{b95}]")
    return passed


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--years', type=int, default=4)
    ap.add_argument('--top-grades', type=str, default='S+,S,A')
    ap.add_argument('--reps', type=int, default=2000)
    ap.add_argument('--blocks', type=str, default='3,6,12')
    ap.add_argument('--seed', type=int, default=42)
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()

    if args.self_test:
        sys.exit(0 if self_test() else 1)

    # 엔진 import는 실행 시점에만 (self-test는 FDR/score 모듈 불필요)
    from validate_v37_2_robustness import (
        fetch_long_panel, run_v37_2_backtest, metrics,
    )

    print("=" * 90)
    print("진우퀀트 v3.7.2 Block Bootstrap 검증 (robustness #9 보강)")
    print(f"시간: {datetime.now()}")
    print("=" * 90)

    print("\n📊 데이터 수집 (5년)...")
    panel = fetch_long_panel(5)
    rets = np.array(run_v37_2_backtest(panel, args.years, args.top_grades))
    print(f"  월별 수익 {len(rets)}개월 확보")

    m = metrics(list(rets))
    print(f"\n[관측 점추정] CAGR {m.get('연환산')}%  Sharpe {m.get('Sharpe')}  "
          f"MDD {m.get('MDD')}%  기간 {m.get('기간')}개월")

    rng = np.random.default_rng(args.seed)
    out = {'observed': m, 'years': args.years, 'top_grades': args.top_grades,
           'reps': args.reps, 'seed': args.seed,
           'benchmark': {'KOSPI_CAGR': KOSPI_CAGR, 'v36_CAGR': V36_CAGR},
           'iid': {}, 'block': {}}

    # iid (= #9 동일 공식, 같은 수익시계열)
    s, c = iid_bootstrap(rets, args.reps, rng)
    s5, s50, s95 = ci(s); c5, c50, c95 = ci(c)
    out['iid'] = {'sharpe_ci_90': [s5, s95], 'sharpe_median': s50,
                  'cagr_ci_90_%': [c5, c95], 'cagr_median_%': c50}
    print("\n" + "-" * 90)
    print(f"[iid bootstrap {args.reps}회]  (검증 #9와 동일 공식·동일 수익시계열)")
    print(f"  CAGR 90%CI [{c5:.1f}, {c95:.1f}] med {c50:.1f}   |   "
          f"Sharpe 90%CI [{s5:.2f}, {s95:.2f}] med {s50:.2f}")

    # block (자기상관 보존)
    print("\n" + "-" * 90)
    print(f"[Moving Block bootstrap {args.reps}회]  ← 시계열 자기상관 보존")
    for L in [int(x) for x in args.blocks.split(',')]:
        s, c = moving_block_bootstrap(rets, L, args.reps, rng)
        s5, s50, s95 = ci(s); c5, c50, c95 = ci(c)
        out['block'][f'L{L}'] = {'sharpe_ci_90': [s5, s95], 'sharpe_median': s50,
                                 'cagr_ci_90_%': [c5, c95], 'cagr_median_%': c50}
        flag = '✅' if c5 > KOSPI_CAGR else '⚠️'
        print(f"  L={L:>2}개월: CAGR 90%CI [{c5:.1f}, {c95:.1f}] med {c50:.1f}  |  "
              f"Sharpe [{s5:.2f}, {s95:.2f}] med {s50:.2f}   "
              f"(하위5% {c5:.1f}% vs KOSPI {KOSPI_CAGR}% {flag})")

    # 판정
    worst = min(v['cagr_ci_90_%'][0] for v in out['block'].values())
    robust = worst > KOSPI_CAGR
    out['verdict'] = {'block_worst_cagr5_%': round(worst, 2), 'robust_vs_kospi': bool(robust)}
    print("\n" + "=" * 90)
    print("판정")
    print(f"  Block 최악(가장 보수적) 하위5% CAGR = {worst:.1f}%  vs KOSPI {KOSPI_CAGR}%  "
          f"{'✅ 여전히 시장 능가 = robust' if robust else '⚠️ 시장 하회 구간 존재'}")
    print("  → 자기상관 반영해도 하방이 시장 위면 과최적/우연 신호 아님 (DSR·White RC와 정합)")

    fn = BASE / f'validate_block_bootstrap_{datetime.now():%Y%m%d_%H%M}.json'
    fn.write_text(json.dumps(out, ensure_ascii=False, indent=2, default=str),
                  encoding='utf-8')
    print(f"\n💾 저장: {fn}")
    print("=" * 90)


if __name__ == '__main__':
    main()
