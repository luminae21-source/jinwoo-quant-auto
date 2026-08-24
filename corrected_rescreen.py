#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
corrected_rescreen.py — 룰 아티팩트 교정 후 재스크린 (선택편향 = 아티팩트分 vs 진짜 재량分 분리)
==============================================================================
교정 2건:
 (1) 금융주 carve-out: COGS·유동자산이 없는 기업(=은행·증권·보험)은 Piotroski를
     '적용 가능한 항목만'으로 계산해 9점 척도로 재척도(P2/P4/P6/P8 무효 처리),
     + 음수 CFO로 인한 accrual/noa 페널티 중립화(NaN).
 (2) 재무악화 기준 강화: 단년 ROA −2%p 대신 'NI<0 또는 2년 연속 ROA 하락'만 악화.
교정 piotroski로 PB를 몽키패치 → sweep(PIT top-K vs fixed-18 vs 시장) 재실행.
입력: fundamentals_pit.csv(합본) + kospi_monthly_prices.csv(합본)
"""
import sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import numpy as np, pandas as pd
import pit_universe_backtest as PB
import sweep_universe_size as SW

ORIG_PIO = PB.piotroski


def piotroski_fixed(fund):
    f = fund.sort_values(["code", "fiscal_year"]).copy()
    f["roa"] = f.net_income / f.assets
    f["cfo_a"] = f.cfo / f.assets
    f["gm"] = (f.revenue - f.cogs) / f.revenue
    f["turn"] = f.revenue / f.assets
    f["lev"] = f.noncurrent_liab / f.assets
    f["cr"] = f.current_assets / f.current_liab
    g = f.groupby("code")
    for c in ["roa", "gm", "turn", "lev", "cr"]:
        f[c + "_p"] = g[c].shift(1)
    f["assets_p"] = g["assets"].shift(1)
    f["ic_p"] = g["issued_capital"].shift(1)
    fin = f.cogs.isna() | f.current_assets.isna()          # 금융주 시그니처
    cond = {1: f.roa > 0, 2: f.cfo_a > 0, 3: f.roa > f.roa_p, 4: f.cfo_a > f.roa,
            5: f.lev < f.lev_p, 6: f.cr > f.cr_p, 7: f.issued_capital <= f.ic_p,
            8: f.gm > f.gm_p, 9: f.turn > f.turn_p}
    inp = {1: [f.roa], 2: [f.cfo_a], 3: [f.roa, f.roa_p], 4: [f.cfo_a, f.roa],
           5: [f.lev, f.lev_p], 6: [f.cr, f.cr_p], 7: [f.issued_capital, f.ic_p],
           8: [f.gm, f.gm_p], 9: [f.turn, f.turn_p]}
    passed = pd.Series(0.0, index=f.index); nvalid = pd.Series(0.0, index=f.index)
    for k in range(1, 10):
        applic = pd.Series(True, index=f.index)
        if k in (2, 4, 6, 8):
            applic = applic & (~fin)                       # 금융주는 이 4개 무효
        na = pd.Series(False, index=f.index)
        for s in inp[k]:
            na = na | s.isna()
        applic = applic & (~na)
        nvalid += applic.astype(float)
        passed += (cond[k].fillna(False) & applic).astype(float)
    f["F"] = np.where(nvalid > 0, (passed / nvalid * 9.0).round(), 0)
    f["F"] = f["F"].clip(0, 9)
    f["accrual"] = (f.net_income - f.cfo) / f.assets
    f["noa_ratio"] = (f.assets - f.cash - (f.liabilities - f.noncurrent_liab)) / f.assets_p
    f.loc[fin, "accrual"] = np.nan                          # 금융주 accrual/noa 중립화
    f.loc[fin, "noa_ratio"] = np.nan
    return f[["code", "fiscal_year", "F", "accrual", "noa_ratio"]]


def refined_deterioration(fund, code):
    g = fund[fund.code == code].sort_values("fiscal_year")
    if len(g) < 2: return False
    ni = g.net_income.iloc[-1]
    roa = (g.net_income / g.assets)
    two_yr = len(g) >= 3 and roa.iloc[-1] < roa.iloc[-2] < roa.iloc[-3]
    return bool((ni < 0) or two_yr)


def main():
    fund = pd.read_csv("fundamentals_pit.csv", dtype={"code": str}); fund["code"] = fund["code"].str.zfill(6)
    nm = {}
    import os
    if os.path.exists("liquidity_sector.csv"):
        ls = pd.read_csv("liquidity_sector.csv", dtype={"code": str}); ls["code"] = ls["code"].str.zfill(6)
        nm = dict(zip(ls["code"], ls["name"]))

    # (a) 교정 F 확인
    pf_old = ORIG_PIO(fund); pf_new = piotroski_fixed(fund)
    print("=== 교정 Piotroski F (직전 회계연도) ===", flush=True)
    for code, label in [("005940", "NH투자증권"), ("105560", "KB금융"), ("000270", "기아"), ("090430", "아모레")]:
        fo = pf_old[pf_old.code == code]["F"]; fn = pf_new[pf_new.code == code]["F"]
        o = int(fo.iloc[-1]) if len(fo) else None; n = int(fn.iloc[-1]) if len(fn) else None
        det = refined_deterioration(fund, code)
        print(f"  {label}({code}): F {o} -> {n} | 강화 악화기준 충족={det}", flush=True)

    # (b) 교정 악화기준으로 기아/아모레 재분류
    print("\n=== 재무악화 재판정(강화: NI<0 또는 2년연속 ROA하락) ===", flush=True)
    for code, label in [("000270", "기아"), ("090430", "아모레"), ("006400", "삼성SDI")]:
        print(f"  {label}({code}): 악화={refined_deterioration(fund, code)}", flush=True)

    # (c) 교정 스코어링으로 sweep 재실행
    print("\n[교정 스코어링 적용 sweep — PIT top-K vs fixed-18 vs 시장]", flush=True)
    PB.piotroski = piotroski_fixed
    SW.sweep("fundamentals_pit.csv", "kospi_monthly_prices.csv", ks=[18, 30])
    print("\n참고(교정前·동일데이터 PC sweep): PIT18 23.8% / PIT30 24.1% / fixed-18 46.0% / 시장 27.8%", flush=True)
    print("해석: 교정 PIT가 23.8%보다 오르면 그만큼이 '룰 아티팩트分', fixed-18(46%)과의 잔차가 '진짜 재량/hindsight分'.", flush=True)


if __name__ == "__main__":
    sys.exit(main() or 0)
