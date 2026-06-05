#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
sweep_universe_size.py — 적정 종목 수(K) 프론티어 측정
==============================================================================
"18종목을 30·50·100으로 늘리면 수익·안정성·운영부담이 어떻게 변하나?"를 데이터로 답한다.
PIT 엔진(pit_universe_backtest)을 K마다 돌려 CAGR·Sharpe·MDD·IR·연회전율·종목당비중 비교.
집중(소수 고확신) ↔ 분산(다수 룰기반)의 트레이드오프를 한 표로.

입력: fundamentals_pit.csv + kospi_monthly_prices.csv (기존 PIT 캐시 그대로)
사용: python sweep_universe_size.py              (기본 K=18,30,50,100)
      python sweep_universe_size.py --ks 18,30,50,100,200
      python sweep_universe_size.py --selftest
의존성: numpy, pandas, pit_universe_backtest.py
"""
import argparse, os, sys
import numpy as np, pandas as pd
import pit_universe_backtest as PB

KS_DEFAULT = [18, 30, 50, 100]


def _pit_hold_for_k(months, prices, mkt_ret, fcols, pf, k):
    """연 1회(5월) PIT top-k 로테이션 보유맵 + 평균 연회전율(교체비율)."""
    hold = {}; cur = []; turns = []
    for i, dt in enumerate(months):
        if dt.month == 5 and i >= 12:
            sc = PB.score_at(i, list(months), prices, mkt_ret, fcols, pf, dt.year)
            if len(sc) >= k:
                new = list(sc.head(k).index)
                if cur:
                    turns.append(len(set(new) ^ set(cur)) / (2.0 * k))  # 교체된 비중
                cur = new
        hold[i] = cur
    return hold, (float(np.mean(turns)) if turns else 0.0)


def _ir(r, mkt, ppy=12):
    common = r.index.intersection(mkt.index)
    ex = (r.reindex(common) - mkt.reindex(common)).dropna()
    if len(ex) < 6 or ex.std(ddof=1) == 0: return 0.0
    return float(ex.mean() / ex.std(ddof=1) * np.sqrt(ppy))


def sweep(fund_csv, prices_csv, ks=None, fixed_codes=None):
    ks = ks or KS_DEFAULT
    fund = pd.read_csv(fund_csv, dtype={"code": str}); fund["code"] = fund["code"].str.zfill(6)
    prices = pd.read_csv(prices_csv, index_col=0, parse_dates=True)
    prices.columns = [str(c).zfill(6) for c in prices.columns]
    pf = PB.piotroski(fund); months = prices.index
    mkt_ret = prices.pct_change().mean(axis=1); fcols = list(prices.columns)
    r_mkt = mkt_ret.dropna(); m_mkt = PB.metrics(r_mkt)
    fc = fixed_codes or PB.FIXED18
    fixed_hold = {i: [c for c in fc if c in prices.columns] for i in range(len(months))}
    r_fix = PB.ew_returns(prices, fixed_hold); m_fix = PB.metrics(r_fix)
    nfix = len([c for c in fc if c in prices.columns])

    rows = []  # (label, CAGR, Sharpe, MDD, IR, turn, wt, edge)
    for k in ks:
        if len(fcols) < k:
            print(f"(K={k} 건너뜀: 후보 {len(fcols)}개 < {k})"); continue
        hold, turn = _pit_hold_for_k(months, prices, mkt_ret, fcols, pf, k)
        r = PB.ew_returns(prices, hold); m = PB.metrics(r)
        if not m: continue
        common = r.index.intersection(r_mkt.index)
        edge = m["CAGR"] - PB.metrics(r_mkt.reindex(common)).get("CAGR", 0)
        rows.append((f"PIT top-{k}", m["CAGR"], m["Sharpe"], m["MDD"], _ir(r, r_mkt), turn, 1.0/k, edge))

    print(f"\n=== 종목 수(K) 프론티어 — PIT 룰 기반 (비교 {m_mkt.get('n','?')}개월) ===")
    hdr = f"{'전략':14}{'CAGR':>8}{'Sharpe':>8}{'MDD':>8}{'IR':>7}{'연회전율':>9}{'종목당':>8}{'시장초과':>9}"
    print(hdr); print("-" * len(hdr))
    for lab, cagr, sh, mdd, ir, tn, wt, ed in rows:
        print(f"{lab:14}{cagr:>7.1%}{sh:>8.2f}{mdd:>7.1%}{ir:>7.2f}{tn:>8.0%}{wt:>7.1%}{ed:>+8.1%}")
    print("-" * len(hdr))
    print(f"{'fixed-'+str(nfix)+'(재량)':14}{m_fix.get('CAGR',0):>7.1%}{m_fix.get('Sharpe',0):>8.2f}"
          f"{m_fix.get('MDD',0):>7.1%}{_ir(r_fix,r_mkt):>7.2f}{0:>8.0%}{1.0/max(nfix,1):>7.1%}"
          f"{m_fix.get('CAGR',0)-m_mkt.get('CAGR',0):>+8.1%}")
    print(f"{'시장(EW)':14}{m_mkt.get('CAGR',0):>7.1%}{m_mkt.get('Sharpe',0):>8.2f}{m_mkt.get('MDD',0):>7.1%}"
          f"{0:>7.2f}{'-':>9}{'-':>8}{0:>+8.1%}")

    if rows:
        best_sh = max(rows, key=lambda x: x[2]); best_mdd = max(rows, key=lambda x: x[3])
        print(f"\n읽는 법: K↑ → 보통 CAGR↓(집중 프리미엄 소멸)·분산↑·회전율/종목수↑(운영부담).")
        print(f"  · Sharpe 최고: {best_sh[0]} ({best_sh[2]:.2f})  · MDD 최저: {best_mdd[0]} ({best_mdd[3]:.1%})")
        print(f"  · 권장 판단: Sharpe·MDD가 평탄해지기 시작하는 '최소 K'가 sweet spot (저빈도·안정성 우선).")
        print(f"  · fixed-{nfix} CAGR이 같은 K의 PIT보다 크게 높으면 그 초과분이 §2 종목선택(hindsight).")
        pd.DataFrame(rows, columns=["strategy","CAGR","Sharpe","MDD","IR","turnover","wt_per_name","edge_vs_mkt"]).to_csv("sweep_universe_size.csv", index=False)
        print("  · 저장: sweep_universe_size.csv")
    print("주의: 종목당 비중=1/K(균등 가정) · 회전율=연 1회 리밸런스 교체비율 · 유동성/섹터 필터 미적용(다음 단계).")
    return rows


def _selftest():
    rng = np.random.default_rng(0); K, Tm = 60, 66
    idx = pd.date_range("2020-01-31", periods=Tm, freq="ME"); codes = [f"{i:06d}" for i in range(K)]
    good = set(codes[:20])
    px = pd.DataFrame(index=idx, columns=codes, dtype=float)
    for c in codes:
        dr = rng.normal(0.028 if c in good else 0.004, 0.002)
        px[c] = 1000 * np.cumprod(1 + rng.normal(dr, 0.07, Tm))
    fr = []
    for c in codes:
        for k2, fy in enumerate(range(2019, 2025)):
            if c in good:
                g = 1 + 0.10 * k2
                fr.append(dict(code=c, fiscal_year=fy, revenue=1e9*g, cogs=5.5e8*g*(1-0.02*k2), op_income=2.4e8*g,
                    net_income=2e8*g, assets=5e9*(1+0.05*k2), liabilities=5e9*(1+0.05*k2)*0.4, equity=5e9*(1+0.05*k2)*0.6,
                    current_assets=2e9*(1+0.04*k2), current_liab=1e9*(1-0.02*k2), cash=5e8, cfo=2.6e8*g,
                    noncurrent_liab=1e9*(1-0.06*k2), issued_capital=1e8))
            else:
                fr.append(dict(code=c, fiscal_year=fy, revenue=1e9, cogs=6.8e8, op_income=-5e6,
                    net_income=-1e7, assets=5e9, liabilities=2.5e9, equity=2.5e9, current_assets=1.5e9,
                    current_liab=1e9, cash=5e8, cfo=-1e7, noncurrent_liab=1.2e9, issued_capital=1e8*(1+0.1*k2)))
    pd.DataFrame(fr).to_csv("_sw_f.csv", index=False); px.to_csv("_sw_p.csv")
    rows = sweep("_sw_f.csv", "_sw_p.csv", ks=[10, 20, 40], fixed_codes=[f"{i:06d}" for i in range(5, 23)])
    for x in ("_sw_f.csv", "_sw_p.csv", "sweep_universe_size.csv"):
        try: os.remove(x)
        except OSError: pass
    assert len(rows) >= 2, "K 행 부족"
    assert all(np.isfinite([r[1] for r in rows])), "CAGR 비정상"
    assert all(0 <= r[5] <= 1 for r in rows), "회전율 범위 오류"
    assert rows[0][1] >= rows[-1][1] - 0.02, "집중(작은 K)이 분산(큰 K)보다 수익 낮음 — 트레이드오프 역전"
    print("\n[OK] sweep_universe_size selftest 통과 (K 프론티어·회전율·집중 프리미엄 방향 확인)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fundamentals", default="fundamentals_pit.csv")
    ap.add_argument("--prices", default="kospi_monthly_prices.csv")
    ap.add_argument("--ks", default=None, help="예: 18,30,50,100,200")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest: return _selftest()
    if not os.path.exists(a.fundamentals): raise SystemExit(f"{a.fundamentals} 없음 → fetch_dart_fundamentals_pit.py 먼저")
    if not os.path.exists(a.prices): raise SystemExit(f"{a.prices} 없음 → build_korea_factors.py 먼저(캐시)")
    ks = [int(x) for x in a.ks.split(",")] if a.ks else None
    sweep(a.fundamentals, a.prices, ks=ks)


if __name__ == "__main__":
    sys.exit(main() or 0)
