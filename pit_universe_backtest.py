#!/usr/bin/env python3
"""
pit_universe_backtest.py — 풀 시스템 PIT universe 검증 (Phase B)
==============================================================================
매년(5월) PIT 점수로 광범위 KOSPI에서 top-N 선별·로테이션 → PIT-systematic universe.
PIT-systematic vs fixed-18(v3.7.2) vs 시장(EW proxy) 3곡선 비교.
점수: F(Piotroski, F_korean 대용)×(12/9) + Sloan + NOA + Mom12 + BAB + Echo
      (ModF·FAR는 PIT 근사에서 생략 — 보조 항, 설계문서 §5 참조)
입력: fundamentals_pit.csv (fetch_dart_fundamentals_pit.py) + kospi_monthly_prices.csv (build_korea_factors.py 캐시)
사용: python pit_universe_backtest.py --top-k 15   /   --selftest
의존성: numpy, pandas, stats_v1.py
"""
import argparse, sys, os, math
import numpy as np, pandas as pd

# v3.7.2 고정 18종목 (score_v37 JINWOO_v37)
FIXED18 = ["005930","000660","042700","196170","000270","035420","035720","012450",
           "079550","105560","033780","006400","090430","028260","003230","095340","034020","005940"]


# ---------- 점수 헬퍼 ----------
def _qscore(s, good_low=True):
    """5분위 → +2..-2 (good_low=True면 낮을수록 +2)."""
    r = s.rank(pct=True, method="first")
    labels = [2, 1, 0, -1, -2] if good_low else [-2, -1, 0, 1, 2]
    out = pd.cut(r, [0, .2, .4, .6, .8, 1.0001], labels=labels, include_lowest=True)
    return out.astype(float).fillna(0.0)

def _mom_score(x):
    if pd.isna(x): return 0.0
    return 2 if x >= .6 else 1 if x >= .3 else 0 if x >= -.1 else -1 if x >= -.3 else -2

def _bab_score(b):
    if pd.isna(b): return 0.0
    return 2 if b < .7 else 1 if b < .9 else 0 if b < 1.1 else -1 if b < 1.3 else -2


def piotroski(fund):
    """fundamentals_pit → 코드·회계연도별 Piotroski F(0~9) + accrual + noa_ratio."""
    f = fund.sort_values(["code", "fiscal_year"]).copy()
    f["roa"] = f.net_income / f.assets
    f["cfo_a"] = f.cfo / f.assets
    f["gm"] = (f.revenue - f.cogs) / f.revenue
    f["turn"] = f.revenue / f.assets
    f["lev"] = f.noncurrent_liab / f.assets
    f["cr"] = f.current_assets / f.current_liab
    g = f.groupby("code")
    for c in ["roa", "gm", "turn", "lev", "cr", "assets", "issued_capital"]:
        f[c + "_p"] = g[c].shift(1) if c in ("roa","gm","turn","lev","cr") else g[c].shift(1)
    f["assets_p"] = g["assets"].shift(1)
    P = pd.DataFrame(index=f.index)
    P[1] = f.roa > 0
    P[2] = f.cfo_a > 0
    P[3] = f.roa > f.roa_p
    P[4] = f.cfo_a > f.roa                       # accrual: CFO > 순이익
    P[5] = f.lev < f.lev_p                        # 레버리지 감소
    P[6] = f.cr > f.cr_p                          # 유동성 개선
    P[7] = f.issued_capital <= f.issued_capital_p # 신주 미발행
    P[8] = f.gm > f.gm_p
    P[9] = f.turn > f.turn_p
    f["F"] = P.fillna(False).astype(int).sum(axis=1)
    f["accrual"] = (f.net_income - f.cfo) / f.assets
    f["noa_ratio"] = (f.assets - f.cash - (f.liabilities - f.noncurrent_liab)) / f.assets_p
    return f[["code", "fiscal_year", "F", "accrual", "noa_ratio"]]


def score_at(idx, months, prices, mkt_ret, fcols, pf, year):
    """리밸런스 월 idx에서 종목별 PIT 점수. fcols=가용 코드. pf=piotroski(FY=year-1)."""
    p_t = prices.iloc[idx]
    rows = {}
    fy = pf[pf.fiscal_year == year - 1].set_index("code")
    for c in fcols:
        s = prices[c]
        if pd.isna(p_t[c]) or idx < 12: continue
        mom = (prices[c].iloc[idx-1] / prices[c].iloc[idx-12] - 1) if not pd.isna(prices[c].iloc[idx-12]) else np.nan
        echo = (prices[c].iloc[idx-7] / prices[c].iloc[idx-12] - 1) if not pd.isna(prices[c].iloc[idx-12]) else np.nan
        r = prices[c].pct_change().iloc[max(0, idx-35):idx+1]
        m = mkt_ret.iloc[max(0, idx-35):idx+1]
        df = pd.concat([r, m], axis=1).dropna()
        beta = (df.iloc[:,0].cov(df.iloc[:,1]) / df.iloc[:,1].var()) if len(df) >= 18 and df.iloc[:,1].var() > 0 else np.nan
        F = fy.loc[c, "F"] if c in fy.index else np.nan
        acc = fy.loc[c, "accrual"] if c in fy.index else np.nan
        noa = fy.loc[c, "noa_ratio"] if c in fy.index else np.nan
        rows[c] = {"F": F, "accrual": acc, "noa": noa, "mom": mom, "echo": echo, "beta": beta}
    if not rows: return pd.Series(dtype=float)
    d = pd.DataFrame(rows).T.apply(pd.to_numeric, errors="coerce")
    sc = d["F"].fillna(d["F"].median()) * (12/9)
    sc = sc + _qscore(d["accrual"], good_low=True) + _qscore(d["noa"], good_low=True)
    sc = sc + d["mom"].map(_mom_score) + d["beta"].map(_bab_score)
    er = d["echo"].rank(pct=True); sc = sc + er.map(lambda v: 1 if v >= .8 else (-1 if v <= .2 else 0)).fillna(0)
    return sc.dropna().sort_values(ascending=False)


def ew_returns(prices, codes_by_month):
    """codes_by_month: dict{month_idx: [codes]} → 월별 동일가중 수익률 시계열."""
    rets = prices.pct_change()
    out = {}
    for i in range(1, len(prices)):
        held = codes_by_month.get(i - 1, [])           # 전월말 보유 → 당월 수익
        held = [c for c in held if c in rets.columns and not pd.isna(rets[c].iloc[i])]
        if held: out[prices.index[i]] = float(rets[held].iloc[i].mean())
    return pd.Series(out)


def metrics(r, ppy=12):
    r = r.dropna().values
    if len(r) < 6: return {}
    cagr = float(np.prod(1+r)**(ppy/len(r)) - 1); vol = r.std(ddof=1)*np.sqrt(ppy)
    eq = np.cumprod(1+r); mdd = float((eq/np.maximum.accumulate(eq)-1).min())
    return {"CAGR": cagr, "Sharpe": float(r.mean()/r.std(ddof=1)*np.sqrt(ppy)) if r.std()>0 else 0, "MDD": mdd, "n": len(r)}


def run(fund_csv, prices_csv, top_k=15, fixed_codes=None):
    fund = pd.read_csv(fund_csv, dtype={"code": str}); fund["code"] = fund["code"].str.zfill(6)
    prices = pd.read_csv(prices_csv, index_col=0, parse_dates=True)
    prices.columns = [str(c).zfill(6) for c in prices.columns]
    pf = piotroski(fund)
    months = prices.index
    mkt_ret = prices.pct_change().mean(axis=1)                 # 시장 proxy (EW)
    fcols = list(prices.columns)
    # 연 1회(5월) 리밸런스 → PIT universe
    pit_hold = {}; cur = []
    for i, dt in enumerate(months):
        if dt.month == 5 and i >= 12:
            sc = score_at(i, months, prices, mkt_ret, fcols, pf, dt.year)
            if len(sc) >= top_k: cur = list(sc.head(top_k).index)
        pit_hold[i] = cur
    fc = fixed_codes or FIXED18
    fixed_hold = {i: [c for c in fc if c in prices.columns] for i in range(len(months))}
    r_pit = ew_returns(prices, pit_hold)
    r_fix = ew_returns(prices, fixed_hold)
    r_mkt = mkt_ret.dropna()
    common = r_pit.index.intersection(r_fix.index).intersection(r_mkt.index)
    r_pit, r_fix, r_mkt = r_pit.reindex(common), r_fix.reindex(common), r_mkt.reindex(common)

    print(f"비교 기간: {len(common)}개월 | top-K={top_k}")
    print(f"{'전략':16} {'CAGR':>8} {'Sharpe':>7} {'MDD':>8}")
    for nm, r in [("PIT-systematic", r_pit), ("fixed-18 (v3.7.2)", r_fix), ("시장(EW proxy)", r_mkt)]:
        m = metrics(r)
        print(f"{nm:16} {m.get('CAGR',0):>7.1%} {m.get('Sharpe',0):>7.2f} {m.get('MDD',0):>7.1%}")
    # 판정
    mp, mf, mm = metrics(r_pit), metrics(r_fix), metrics(r_mkt)
    edge_pit = mp.get("CAGR",0) - mm.get("CAGR",0)
    edge_fix = mf.get("CAGR",0) - mm.get("CAGR",0)
    print(f"\nPIT-systematic 시장초과: {edge_pit:+.1%}/년 | fixed-18 시장초과: {edge_fix:+.1%}/년")
    if edge_pit > 0.5 * edge_fix and edge_pit > 0.05:
        print("→ ✅ 체계적 엣지 상당부분 유지 = universe 선택과 무관하게 반복가능 (hindsight 비중 낮음)")
    elif edge_pit < 0.25 * edge_fix:
        print("→ ⚠️ PIT 엣지 대부분 소멸 = fixed-18 초과수익은 주로 종목 재량선택(hindsight)")
    else:
        print("→ 중간: 일부 체계적 + 일부 선택편향")
    return r_pit, r_fix, r_mkt


def _selftest():
    rng = np.random.default_rng(0); K, Tm = 60, 66
    idx = pd.date_range("2020-01-31", periods=Tm, freq="ME"); codes = [f"{i:06d}" for i in range(K)]
    good = set(codes[:20])                                   # 20개 우량(높은 F + 추세)
    px = pd.DataFrame(index=idx, columns=codes, dtype=float)
    for c in codes:
        dr = rng.normal(0.025 if c in good else 0.005, 0.002)
        px[c] = 1000*np.cumprod(1+rng.normal(dr, 0.07, Tm))
    fr = []
    for c in codes:
        for fy in range(2019, 2025):
            base = 1.0 if c in good else 0.3
            fr.append({"code":c,"fiscal_year":fy,"revenue":1e9*base*(1+0.1*(fy-2019)),
                       "cogs":6e8*base,"op_income":2e8*base,"net_income":2e8*base if c in good else -1e7,
                       "assets":5e9,"liabilities":2e9,"equity":3e9,"current_assets":2e9,"current_liab":1e9,
                       "cash":5e8,"cfo":2.5e8*base if c in good else 1e7,"noncurrent_liab":1e9,"issued_capital":1e8})
    fund = pd.DataFrame(fr); fund.to_csv("_pit_fund.csv", index=False)
    px.to_csv("_pit_px.csv")
    r_pit, r_fix, r_mkt = run("_pit_fund.csv", "_pit_px.csv", top_k=15, fixed_codes=[f"{i:06d}" for i in range(5,23)])
    for x in ("_pit_fund.csv", "_pit_px.csv"):
        try: os.remove(x)
        except OSError: pass
    assert metrics(r_pit).get("CAGR",0) > metrics(r_mkt).get("CAGR",0), "PIT가 우량종목 못 잡음"
    print("\n[OK] pit_universe_backtest selftest 통과 (PIT가 우량 universe 선별→시장 초과)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fundamentals", default="fundamentals_pit.csv")
    ap.add_argument("--prices", default="kospi_monthly_prices.csv")
    ap.add_argument("--top-k", type=int, default=15)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest: return _selftest()
    if not os.path.exists(a.fundamentals): raise SystemExit(f"{a.fundamentals} 없음 → fetch_dart_fundamentals_pit.py 먼저")
    if not os.path.exists(a.prices): raise SystemExit(f"{a.prices} 없음 → build_korea_factors.py 먼저(캐시 생성)")
    run(a.fundamentals, a.prices, a.top_k)


if __name__ == "__main__":
    sys.exit(main() or 0)
