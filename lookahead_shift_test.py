#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
lookahead_shift_test.py — 범용 룩어헤드 탐지 (실행 기반)

원리 한 줄:
  **선택 변수에 shift(1)을 넣었을 때 성과가 급락하면, 그 변수는 미래 정보를 담고 있다.**

정적 분석으로는 못 잡는다 — 실제로 오늘 확인된 버그 파일(유니버스_규칙화_검정.py)은
모멘텀 창을 정확히 시차 처리하고 있어서 패턴 검사를 통과했다. 시총만 안 밀렸을 뿐이다.
어떤 변수가 안 밀렸는지는 **하나씩 밀어보는 수밖에 없다.**

사용법 A — 기존 백테에 삽입:
    from lookahead_shift_test import shift_test
    shift_test(run_backtest, {"mcap": M, "liquidity": L, "fundamentals": F})

사용법 B — 자립 실행 (진우퀀트 데이터 기준):
    python lookahead_shift_test.py
"""
try:  # 윈도 파이프(cp949)에서 이모지 출력 시 UnicodeEncodeError 방지 (2026-07-27)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import sys
import numpy as np
import pandas as pd

ALERT_PP = 3.0   # CAGR 차이 3%p 이상이면 경보


def shift_test(run_fn, selectors: dict, alert_pp: float = ALERT_PP, verbose: bool = True):
    """
    run_fn(**selectors) -> CAGR(float)  형태의 백테 함수를 받아,
    선택 변수를 하나씩 shift(1)하며 성과 변화를 잰다.

    selectors: {"이름": DataFrame} — 시점 인덱스를 가진 선택 변수들
    """
    base = run_fn(**selectors)
    rows = []
    for name, df in selectors.items():
        mod = dict(selectors)
        mod[name] = df.shift(1)
        got = run_fn(**mod)
        delta = (got - base) * 100
        flag = "🚨 룩어헤드" if abs(delta) >= alert_pp else "✅"
        rows.append((name, base * 100, got * 100, delta, flag))

    if verbose:
        print("=" * 70)
        print(" 룩어헤드 shift 테스트")
        print("=" * 70)
        print(f"  {'선택변수':<20}{'원본':>10}{'shift(1)':>12}{'차이':>10}  판정")
        print("-" * 70)
        for n, b, g, d, f in rows:
            print(f"  {n:<20}{b:>9.1f}%{g:>11.1f}%{d:>+9.1f}%p  {f}")
        bad = [r for r in rows if "🚨" in r[4]]
        print()
        if bad:
            print(f"  🚨 {len(bad)}개 변수가 미래 정보를 담고 있다: {', '.join(r[0] for r in bad)}")
            print("     → 해당 변수를 shift(1)한 값이 정상 결과다.")
        else:
            print("  ✅ 모든 선택 변수가 시차 처리 정상")
    return rows


# ──────────────────────────────────────────────────────────────────
# 자립 실행 — 진우퀀트 30년 패널로 시연
# ──────────────────────────────────────────────────────────────────
def _demo():
    import os
    BASE = os.environ.get("JQ_BASE", ".")
    px = pd.read_csv(f"{BASE}/_월봉종가캐시_KOSPI.csv", dtype={"code": str})
    px["code"] = px.code.str.zfill(6)
    P = px.pivot_table(index="ym", columns="code", values="close", aggfunc="last").sort_index()
    R = P.pct_change().mask(lambda x: x.abs() > 1.0)

    mc = pd.read_csv(f"{BASE}/종목시총_30년.csv", dtype={"code": str})
    mc["code"] = mc.code.str.zfill(6)
    mc["ym"] = pd.to_datetime(mc.date).dt.strftime("%Y-%m")
    M = mc.pivot_table(index="ym", columns="code", values="mcap", aggfunc="last")

    TAX, SLIP = 0.002, 0.0005

    def run(mcap):
        """TOP30 동일가중 — 원본 로직 그대로"""
        held, out = set(), []
        idxs = list(R.index)
        for t in R.index:
            if t not in mcap.index or idxs.index(t) < 13:
                continue
            m = mcap.loc[t].dropna().sort_values(ascending=False)
            if len(m) < 50:
                continue
            cur = R.loc[t]
            sel = [c for c in m.index[:30] if pd.notna(cur.get(c))]
            if len(sel) < 5:
                continue
            f = 1 - len(set(sel) & held) / len(sel) if held else 1.0
            out.append(cur[sel].mean() - f * (TAX + 2 * SLIP))
            held = set(sel)
        s = pd.Series(out)
        return (1 + s).prod() ** (12 / len(s)) - 1

    print("진우퀀트 30년 TOP30 동일가중 — 시총 변수 shift 테스트\n")
    return shift_test(run, {"mcap": M})


if __name__ == "__main__":
    # 2026-07-27: 빌드 게이트용 — 룩어헤드 탐지 시 exit 1
    rows = _demo() or []
    sys.exit(1 if any("!!" in r[4] or "룩어헤드" in str(r[4]) for r in rows) else 0)
