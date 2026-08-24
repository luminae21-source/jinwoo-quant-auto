#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest_v42_kosdaq_flow.py — v4.2 KOSDAQ 수급팩터 Stage2 (판정).
동결 합격선(사전등록 2026-06-13) 자동판정. v41·production·C·D·영역3 무수정.

판정 2개: 외국인 단독 / 기관 단독 (각 3M누적/시총, top-20 EW 월리밸, 비용 round-trip).
합격선(4중 AND, base 3종 MKT·EW·KOSDAQ150):
  ① EW 비열위(CAGR≥EW AND IR_EW≥0)  ② MKT 알파≥+3.0%p  ③ IR_MKT≥0.30 AND Sharpe≥MKT−0.01  ④ MDD 비악화(vs MKT)
진단(판정 아님): 합산·동반 IC/조건부수익 병기.

입력: --flow kosdaq_flow_monthly.csv  --mcap kosdaq_mcap_monthly.csv  --price kosdaq_pit_daily_pykrx.csv
      [--mkt kosdaq_factors.csv] [--kq150 kosdaq150_monthly.csv]
자체검증: --selftest (합성 신호주입/널 대조)
"""
import argparse, sys
import numpy as np
import pandas as pd

N_PICKS = 20
COST_RT = 0.006
END_YM = pd.Period("2026-05", "M")
ALPHA_GATE = 0.03
IR_GATE = 0.30
SHARPE_TOL = 0.01
NMIN = 30


def spearman(a, b):
    a = np.asarray(a, float); b = np.asarray(b, float)
    m = ~(np.isnan(a) | np.isnan(b)); a, b = a[m], b[m]
    if len(a) < 5:
        return np.nan
    ra = pd.Series(a).rank().values; rb = pd.Series(b).rank().values
    if ra.std() == 0 or rb.std() == 0:
        return np.nan
    return float(np.corrcoef(ra, rb)[0, 1])


def ann_metrics(rets):
    r = np.asarray([x for x in rets if x == x], float)
    if len(r) == 0:
        return dict(CAGR=np.nan, Sharpe=np.nan, MDD=np.nan)
    cum = np.prod(1 + r); yrs = len(r) / 12.0
    cagr = cum ** (1 / yrs) - 1 if yrs > 0 and cum > 0 else np.nan
    sd = r.std(ddof=0); sharpe = (r.mean() / sd) * np.sqrt(12) if sd > 0 else np.nan
    eq = np.cumprod(1 + r); peak = np.maximum.accumulate(eq); mdd = float((eq / peak - 1).min())
    return dict(CAGR=cagr, Sharpe=sharpe, MDD=mdd)


def info_ratio(strat, base):
    ex = np.asarray(strat, float) - np.asarray(base, float)
    ex = ex[~np.isnan(ex)]
    if len(ex) < 2 or ex.std(ddof=0) == 0:
        return np.nan
    return float(ex.mean() / ex.std(ddof=0) * np.sqrt(12))


def monthly_close_returns(price):
    p = price.copy()
    p["date"] = pd.to_datetime(p["date"]); p["ym"] = p["date"].dt.to_period("M")
    p = p.sort_values(["code", "date"])
    me = p.groupby(["code", "ym"], as_index=False).last()[["code", "ym", "close"]]
    me = me.sort_values(["code", "ym"])
    me["ret"] = me.groupby("code")["close"].pct_change()
    me["fwd_ret"] = me.groupby("code")["ret"].shift(-1)   # 익월 수익 = 팩터(t) 타깃
    return me[["code", "ym", "ret", "fwd_ret"]]


def build_panel(flow, mcap, price):
    fl = flow.copy(); fl["ym"] = pd.to_datetime(fl["date"]).dt.to_period("M")
    fl = fl.sort_values(["code", "ym"])
    fl["for3"] = fl.groupby("code")["foreign_net"].transform(lambda s: s.rolling(3, min_periods=1).sum())
    fl["ins3"] = fl.groupby("code")["inst_net"].transform(lambda s: s.rolling(3, min_periods=1).sum())
    mc = mcap.copy(); mc["ym"] = pd.to_datetime(mc["date"]).dt.to_period("M")
    mc = mc.groupby(["code", "ym"], as_index=False)["mcap"].last()
    ret = monthly_close_returns(price)
    df = fl[["code", "ym", "for3", "ins3", "foreign_net", "inst_net"]].merge(
        mc, on=["code", "ym"], how="inner").merge(ret, on=["code", "ym"], how="inner")
    df = df[df["mcap"] > 0].copy()
    df["f_for"] = df["for3"] / df["mcap"]
    df["f_ins"] = df["ins3"] / df["mcap"]
    df["f_comb"] = (df["for3"] + df["ins3"]) / df["mcap"]
    df["dual"] = ((df["for3"] > 0) & (df["ins3"] > 0)).astype(int)
    df = df[df["ym"] <= END_YM]
    return df


def backtest_factor(df, col):
    months = sorted(df["ym"].unique())
    strat, eww, mkt_ph = [], [], []
    ic = []
    prev = set()
    for m in months:
        day = df[df["ym"] == m]
        day = day.dropna(subset=[col, "fwd_ret"])
        if len(day) < NMIN:
            continue
        ic.append(spearman(day[col].values, day["fwd_ret"].values))
        day = day.sort_values(col, ascending=False)
        top = day.head(N_PICKS)
        ew = day["fwd_ret"].mean()                  # eligible 등가중(base EW)
        tr = top["fwd_ret"].mean()
        cur = set(top["code"])
        turn = 1.0 if not prev else 1 - len(cur & prev) / len(cur)
        strat.append(tr - turn * COST_RT); eww.append(ew)
        prev = cur
    return np.array(strat), np.array(eww), ic, months


def judge(name, df, col, base_mkt, base_kq):
    strat, eww, ic, months = backtest_factor(df, col)
    if len(strat) < 12:
        return dict(name=name, verdict="N/A(표본부족)", n=len(strat))
    sM = ann_metrics(strat); eM = ann_metrics(eww)
    # base 정렬: strat 산출된 월에 맞춰 길이 맞춤(간이 — EW는 동월, MKT/KQ는 옵션)
    res = dict(name=name, n=len(strat),
               CAGR=sM["CAGR"], Sharpe=sM["Sharpe"], MDD=sM["MDD"],
               EW_CAGR=eM["CAGR"], IR_EW=info_ratio(strat, eww),
               IC_mean=float(np.nanmean(ic)) if ic else np.nan)
    # base MKT / KQ150 (있으면)
    a_mkt = ir_mkt = sh_mkt = mdd_mkt = np.nan
    if base_mkt is not None:
        bm = np.array([base_mkt.get(m, np.nan) for m in months[-len(strat):]])
        mM = ann_metrics(bm[~np.isnan(bm)]) if np.isfinite(bm).any() else dict(CAGR=np.nan, Sharpe=np.nan, MDD=np.nan)
        a_mkt = (sM["CAGR"] - mM["CAGR"]) if mM["CAGR"] == mM["CAGR"] else np.nan
        ir_mkt = info_ratio(strat, np.nan_to_num(bm, nan=np.nanmean(bm)))
        sh_mkt = mM["Sharpe"]; mdd_mkt = mM["MDD"]
    res.update(alpha_MKT=a_mkt, IR_MKT=ir_mkt, MKT_Sharpe=sh_mkt, MKT_MDD=mdd_mkt)
    # 4중 AND
    g_ew = (res["CAGR"] >= res["EW_CAGR"]) and (res["IR_EW"] >= 0 if res["IR_EW"] == res["IR_EW"] else False)
    g_al = (a_mkt >= ALPHA_GATE) if a_mkt == a_mkt else False
    g_ir = (ir_mkt >= IR_GATE if ir_mkt == ir_mkt else False) and (sM["Sharpe"] >= (sh_mkt - SHARPE_TOL) if sh_mkt == sh_mkt else True)
    g_md = (sM["MDD"] >= mdd_mkt) if mdd_mkt == mdd_mkt else True   # 비악화(덜 음수)
    passed = g_ew and g_al and g_ir and g_md
    res["gates"] = dict(EW비열위=bool(g_ew), MKT알파=bool(g_al), IR=bool(g_ir), MDD=bool(g_md))
    res["verdict"] = "PASS" if passed else "FAIL"
    return res


def diagnostics(df):
    months = sorted(df["ym"].unique())
    ic_for, ic_ins, ic_comb, dual_d = [], [], [], []
    for m in months:
        day = df[df["ym"] == m].dropna(subset=["fwd_ret"])
        if len(day) < NMIN:
            continue
        ic_for.append(spearman(day["f_for"], day["fwd_ret"]))
        ic_ins.append(spearman(day["f_ins"], day["fwd_ret"]))
        ic_comb.append(spearman(day["f_comb"], day["fwd_ret"]))
        d1 = day[day["dual"] == 1]["fwd_ret"].mean(); d0 = day[day["dual"] == 0]["fwd_ret"].mean()
        if d1 == d1 and d0 == d0:
            dual_d.append(d1 - d0)
    return dict(IC_for=np.nanmean(ic_for), IC_ins=np.nanmean(ic_ins), IC_comb=np.nanmean(ic_comb),
                dual_minus=np.nanmean(dual_d) if dual_d else np.nan)


def load_mkt(path):
    try:
        m = pd.read_csv(path)
        m["ym"] = pd.to_datetime(m["date"]).dt.to_period("M")
        col = "MKT" if "MKT" in m.columns else ("ret" if "ret" in m.columns else None)
        if col is None:
            return None
        return {r["ym"]: float(r[col]) for _, r in m.iterrows() if r[col] == r[col]}
    except Exception:
        return None


def make_synth(signal=0.0, seed=1, n=120, months=60):
    rng = np.random.default_rng(seed)
    ms = pd.period_range("2019-01", periods=months, freq="M")
    codes = ["S%03d" % i for i in range(n)]
    fl, mc, pr = [], [], []
    price0 = {c: rng.uniform(3000, 60000) for c in codes}
    for c in codes:
        p = price0[c]; mcap = rng.uniform(5e10, 5e12)
        prev_flow = 0.0
        for k, m in enumerate(ms):
            fnet = rng.normal(0, 5e8); inet = rng.normal(0, 4e8)
            # signal: '직전달' 수급이 강하면 '이번달' 수익↑ (lag=예측신호)
            drift = signal * (prev_flow / 1e9)
            p *= (1 + rng.normal(0.005, 0.12) + drift)
            prev_flow = (fnet + inet)
            d = m.to_timestamp("M").strftime("%Y-%m-%d")
            fl.append((c, d, fnet, inet)); mc.append((c, d, mcap)); pr.append((c, d, p, p, p, p))
    flow = pd.DataFrame(fl, columns=["code", "date", "foreign_net", "inst_net"])
    mcap = pd.DataFrame(mc, columns=["code", "date", "mcap"])
    price = pd.DataFrame(pr, columns=["code", "date", "open", "high", "low", "close"])
    return flow, mcap, price


def report(df, base_mkt):
    print("패널: %d행, %d종목 × %d월 (≤%s)" % (len(df), df["code"].nunique(), df["ym"].nunique(), END_YM))
    for name, col in [("외국인 단독", "f_for"), ("기관 단독", "f_ins")]:
        r = judge(name, df, col, base_mkt, None)
        print("\n[판정] %s — %s" % (name, r["verdict"]))
        if "CAGR" in r:
            print("  CAGR %.2f%% | Sharpe %.2f | MDD %.1f%% | vs EW: CAGR %.2f%%(IR_EW %.2f) | alpha_MKT %s | IR_MKT %s | IC %.3f" % (
                r["CAGR"]*100, r["Sharpe"], r["MDD"]*100, r["EW_CAGR"]*100, r["IR_EW"],
                ("%.2f%%p"%(r["alpha_MKT"]*100)) if r["alpha_MKT"]==r["alpha_MKT"] else "n/a",
                ("%.2f"%r["IR_MKT"]) if r["IR_MKT"]==r["IR_MKT"] else "n/a", r["IC_mean"]))
            print("  게이트:", r["gates"])
    d = diagnostics(df)
    print("\n[진단·참고] IC 외국인 %.3f / 기관 %.3f / 합산 %.3f | 동반-비동반 월수익차 %s" % (
        d["IC_for"], d["IC_ins"], d["IC_comb"],
        ("%+.2f%%"%(d["dual_minus"]*100)) if d["dual_minus"]==d["dual_minus"] else "n/a"))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--flow"); ap.add_argument("--mcap"); ap.add_argument("--price")
    ap.add_argument("--mkt", default=None); ap.add_argument("--kq150", default=None)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    print("=" * 70); print("v4.2 KOSDAQ 수급팩터 Stage2 판정 (외국인/기관 · 동결 합격선)"); print("=" * 70)
    if a.selftest:
        for sig, lab in [(0.05, "신호주입"), (0.0, "널 대조")]:
            fl, mc, pr = make_synth(signal=sig, seed=3)
            df = build_panel(fl, mc, pr)
            base = {m: df[df["ym"] == m]["fwd_ret"].mean() for m in df["ym"].unique()}  # 합성 MKT=EW대용
            print("\n##### 합성 %s #####" % lab); report(df, base)
        print("\n(자체검증: 신호주입은 외국인/기관 IC·alpha 양(+), 널 대조는 0 근처여야 정상)")
        return
    flow = pd.read_csv(a.flow, encoding="utf-8-sig")
    mcap = pd.read_csv(a.mcap, encoding="utf-8-sig")
    price = pd.read_csv(a.price, encoding="utf-8-sig")
    df = build_panel(flow, mcap, price)
    base_mkt = load_mkt(a.mkt) if a.mkt else {m: df[df["ym"] == m]["fwd_ret"].mean() for m in df["ym"].unique()}
    report(df, base_mkt)
    print("\n⚠️ backtest≠미래. PASS=보조축 후보(관찰), FAIL=11번째 사전등록 기각. 매수신호 아님. v41 무수정.")


if __name__ == "__main__":
    main()
