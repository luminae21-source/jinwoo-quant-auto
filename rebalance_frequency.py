#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rebalance_frequency.py — "교체 주기 ↔ 수익률" 상관관계 측정 (거래비용 반영)
==============================================================================
같은 PIT 선별을 월간/분기/반기/연간으로 리밸런스했을 때 총수익·순수익(비용차감)·
연회전율·비용드래그를 비교. "자주 갈아타면 더 버나, 비용에 먹히나?"를 데이터로 답한다.

핵심: 회전율↑ → 신호 빨리 반영(총수익 약간↑) BUT 거래비용·세금↑ → 순수익은 깎임.
      대개 어느 지점 넘으면 더 자주 갈아탈수록 순수익이 낮아진다(최적 주기 존재).

입력: fundamentals_pit.csv + kospi_monthly_prices.csv (기존 PIT 캐시 그대로)
사용: python rebalance_frequency.py                 (기본 K=18, 비용 30bp 왕복)
      python rebalance_frequency.py --k 30 --cost-bps 50
      python rebalance_frequency.py --selftest
의존성: numpy, pandas, pit_universe_backtest.py
"""
import argparse, os, sys
import numpy as np, pandas as pd
import pit_universe_backtest as PB

FREQS = [(1, "월간"), (3, "분기"), (6, "반기"), (12, "연간")]


def _hold_for_step(months, prices, mkt_ret, fcols, pf, k, step):
    """step개월마다 PIT top-k 리밸런스. 보유맵 + {리밸런스월idx: 교체비율}."""
    hold = {}; cur = []; turns = {}
    for i, dt in enumerate(months):
        if i >= 12 and (i - 12) % step == 0:
            sc = PB.score_at(i, list(months), prices, mkt_ret, fcols, pf, dt.year)
            if len(sc) >= k:
                new = list(sc.head(k).index)
                if cur:
                    turns[i] = len(set(new) ^ set(cur)) / (2.0 * k)
                cur = new
        hold[i] = cur
    return hold, turns


def run(fund_csv, prices_csv, k=18, cost_bps=30.0, freqs=None, fixed=None):
    freqs = freqs or FREQS
    fund = pd.read_csv(fund_csv, dtype={"code": str}); fund["code"] = fund["code"].str.zfill(6)
    prices = pd.read_csv(prices_csv, index_col=0, parse_dates=True)
    prices.columns = [str(c).zfill(6) for c in prices.columns]
    pf = PB.piotroski(fund); months = prices.index
    mkt_ret = prices.pct_change().mean(axis=1); fcols = list(prices.columns)
    years = max(1e-9, len(months) / 12.0)

    rows = []
    for step, lab in freqs:
        if len(fcols) < k:
            continue
        hold, turns = _hold_for_step(months, prices, mkt_ret, fcols, pf, k, step)
        gross = PB.ew_returns(prices, hold)
        net = gross.copy()
        for i, t in turns.items():
            dt = months[i]
            if dt in net.index:
                net.loc[dt] = net.loc[dt] - t * (cost_bps / 10000.0)   # 교체분에 왕복비용
        mg, mn = PB.metrics(gross), PB.metrics(net)
        ann_turn = sum(turns.values()) / years
        rows.append((lab, step, mg.get("CAGR", 0), mn.get("CAGR", 0), mn.get("Sharpe", 0),
                     ann_turn, mg.get("CAGR", 0) - mn.get("CAGR", 0)))

    print(f"=== 교체 주기 ↔ 수익률 (K={k}, 거래비용 왕복 {cost_bps:.0f}bp, {len(months)}개월) ===")
    hdr = f"{'주기':6}{'총CAGR':>9}{'순CAGR':>9}{'순Sharpe':>9}{'연회전율':>9}{'비용드래그':>10}"
    print(hdr); print("-" * len(hdr))
    for lab, step, g, n, sh, tn, drag in rows:
        print(f"{lab:6}{g:>8.1%}{n:>9.1%}{sh:>9.2f}{tn:>8.0%}{drag:>9.1%}")
    print("-" * len(hdr))

    if len(rows) >= 2:
        best = max(rows, key=lambda x: x[3])          # 순CAGR 최고
        gross_gain = rows[0][2] - rows[-1][2]          # 월간 - 연간 (총수익 차)
        net_gain = rows[0][3] - rows[-1][3]            # 월간 - 연간 (순수익 차)
        print(f"\n해석:")
        print(f"  · 순수익 최고 주기: {best[0]} (순CAGR {best[3]:.1%}, 연회전율 {best[5]:.0%})")
        print(f"  · 자주 갈아탈수록(월간) 총수익은 {'+' if gross_gain>=0 else ''}{gross_gain:.1%}p 변하지만, "
              f"비용 반영 순수익은 {'+' if net_gain>=0 else ''}{net_gain:.1%}p (연간 대비).")
        if net_gain <= 0.005:
            print(f"  → 결론: 더 자주 갈아타도 순수익 이득 거의 없음(또는 손해). 비용·세금이 먹음 → 저빈도가 유리.")
        else:
            print(f"  → 결론: 잦은 교체가 비용 빼고도 이득. 단 cost-bps를 실제(한국 세금+슬리피지 ~0.3~0.5%)로 올려 재확인 권장.")
        print(f"  주의: 비용 {cost_bps:.0f}bp는 가정값. 한국은 매도세+수수료+슬리피지로 왕복 30~60bp가 현실적 → --cost-bps로 조정.")
    return rows


def _selftest():
    rng = np.random.default_rng(1); K, Tm = 60, 66
    idx = pd.date_range("2020-01-31", periods=Tm, freq="ME"); codes = [f"{i:06d}" for i in range(K)]
    good = set(codes[:20])
    px = pd.DataFrame(index=idx, columns=codes, dtype=float)
    for c in codes:
        dr = rng.normal(0.022 if c in good else 0.004, 0.002)
        px[c] = 1000 * np.cumprod(1 + rng.normal(dr, 0.07, Tm))
    fr = []
    for c in codes:
        for kk, fy in enumerate(range(2019, 2025)):
            if c in good:
                g = 1 + 0.10 * kk
                fr.append(dict(code=c, fiscal_year=fy, revenue=1e9*g, cogs=5.5e8*g*(1-0.02*kk), op_income=2.4e8*g,
                    net_income=2e8*g, assets=5e9*(1+0.05*kk), liabilities=5e9*(1+0.05*kk)*0.4, equity=5e9*(1+0.05*kk)*0.6,
                    current_assets=2e9*(1+0.04*kk), current_liab=1e9*(1-0.02*kk), cash=5e8, cfo=2.6e8*g,
                    noncurrent_liab=1e9*(1-0.06*kk), issued_capital=1e8))
            else:
                fr.append(dict(code=c, fiscal_year=fy, revenue=1e9, cogs=6.8e8, op_income=-5e6,
                    net_income=-1e7, assets=5e9, liabilities=2.5e9, equity=2.5e9, current_assets=1.5e9,
                    current_liab=1e9, cash=5e8, cfo=-1e7, noncurrent_liab=1.2e9, issued_capital=1e8))
    pd.DataFrame(fr).to_csv("_rf_f.csv", index=False); px.to_csv("_rf_p.csv")
    rows = run("_rf_f.csv", "_rf_p.csv", k=15, cost_bps=40)
    for x in ("_rf_f.csv", "_rf_p.csv"):
        try: os.remove(x)
        except OSError: pass
    assert len(rows) >= 3, "주기 행 부족"
    turns = {r[0]: r[5] for r in rows}
    assert turns.get("월간", 0) >= turns.get("연간", 0), "월간 회전율이 연간보다 낮음 — 비정상"
    assert all(r[2] >= r[3] - 1e-9 for r in rows), "순수익이 총수익보다 큼 — 비용 적용 오류"
    print("\n[OK] rebalance_frequency selftest 통과 (회전율 단조·비용드래그 방향 확인)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fundamentals", default="fundamentals_pit.csv")
    ap.add_argument("--prices", default="kospi_monthly_prices.csv")
    ap.add_argument("--k", type=int, default=18)
    ap.add_argument("--cost-bps", type=float, default=30.0)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest: return _selftest()
    if not os.path.exists(a.fundamentals): raise SystemExit(f"{a.fundamentals} 없음 → fetch_dart_fundamentals_pit.py 먼저")
    if not os.path.exists(a.prices): raise SystemExit(f"{a.prices} 없음 → build_korea_factors.py 먼저(캐시)")
    run(a.fundamentals, a.prices, k=a.k, cost_bps=a.cost_bps)


if __name__ == "__main__":
    sys.exit(main() or 0)
