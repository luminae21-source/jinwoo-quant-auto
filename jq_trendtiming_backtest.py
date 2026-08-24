# -*- coding: utf-8 -*-
"""
jq_trendtiming_backtest.py — 후보 A(검증형): 추세 타이밍이 buy&hold에 값을 더하나.
근거: Faber(2007) 10개월 SMA(월종가>SMA 매수 / <SMA 현금). MA200 daily 변형=production 규칙 등가.

성격: **검증**(production MA200 행동규칙을 데이터로 정당화/반증). 새 팩터 발명 아님·오버핏 회피.
수익 우선: "수익 유지하며 낙폭 회피"가 Faber 주장 → 게이트=CAGR 비열위 + MDD 유의 감소 + Sharpe↑.
무수정: production·L1 불변. 데이터=korea_factors_monthly(MKT·RF)·kospi_index_daily(KS11).
실행(폴더에서): py jq_trendtiming_backtest.py --selftest | --run | --judge
"""
import os, sys, json, argparse, warnings, importlib.util
import numpy as np, pandas as pd
warnings.simplefilter("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
def _load(f, m):
    s = importlib.util.spec_from_file_location(m, os.path.join(HERE, f))
    x = importlib.util.module_from_spec(s); s.loader.exec_module(x); return x
S1 = _load("stats_v1.py", "stats_v1")

CFG = dict(MODE="monthly", SMA_MONTHS=10, MA_DAYS=200, COST_ONEWAY=0.0030)

def load_market():
    f = pd.read_csv(os.path.join(HERE, "korea_factors_monthly.csv"), parse_dates=["date"]).set_index("date")
    rf = f["RF"].fillna(0.0); r = f["MKT"].fillna(0.0) + rf
    return r, rf

def load_kospi():
    """KS11 종가: 월말 시리즈(월간 SMA용) + 일간(MA200용)."""
    p = os.path.join(HERE, "kospi_index_daily.csv")
    if not os.path.exists(p): return None, None
    d = pd.read_csv(p, parse_dates=["Date"]).set_index("Date")["Close"]
    return d.resample("ME").last(), d

def trend_signal(cfg=None):
    """추세 in/out 신호(월말 기준, 1=시장 0=현금). look-ahead 없음(월말 신호→익월 적용은 백테서 shift)."""
    c = cfg or CFG; m_close, d_close = load_kospi()
    if m_close is None: return None
    if c["MODE"] == "monthly":
        sma = m_close.rolling(c["SMA_MONTHS"]).mean()
        sig = (m_close > sma).astype(float)
    else:  # daily MA200 → 월말 샘플
        ma = d_close.rolling(c["MA_DAYS"]).mean()
        sig = (d_close > ma).astype(float).resample("ME").last()
    return sig

def backtest(cfg=None):
    c = cfg or CFG; r, rf = load_market(); sig = trend_signal(c)
    if sig is None: return None, None
    sig = sig.reindex(r.index).ffill().shift(1)                 # 월말 신호 → 익월 포지션(look-ahead 0)
    idx = sig.dropna().index
    sig = sig.reindex(idx); rr = r.reindex(idx); rff = rf.reindex(idx)
    strat = sig*rr + (1-sig)*rff                                # 시장 or 현금
    switch = sig.diff().abs().fillna(0)                         # 매매전환
    strat = strat - switch*c["COST_ONEWAY"]
    return strat.dropna(), rr.reindex(strat.dropna().index)

def perf(x):
    x = x.dropna(); n = len(x)
    cum = (1+x).cumprod()
    return dict(CAGR=round(float((1+x).prod()**(12/max(n,1))-1),4),
                Sharpe=round(float(x.mean()/x.std()*np.sqrt(12)) if x.std()>0 else np.nan,3),
                MDD=round(float((cum/cum.cummax()-1).min()),4), n=n)

def judge():
    strat, bench = backtest()
    if strat is None: return {"err": "kospi_index_daily.csv 없음 → fetch_kospi_index_daily.py 먼저"}
    ps, pb = perf(strat), perf(bench)
    a = ps["Sharpe"] > pb["Sharpe"]                              # 위험조정 우위
    b = ps["CAGR"] >= pb["CAGR"] - 0.01                          # 수익 비열위
    cc = abs(ps["MDD"]) <= abs(pb["MDD"])*0.80                   # 낙폭 20%+ 감소(추세타이밍 목적)
    # 격자(SMA/MA 길이)로 robustness
    import itertools as it
    cols = {}
    for mode, L in [("monthly",8),("monthly",10),("monthly",12),("daily",150),("daily",200),("daily",250)]:
        s,_ = backtest(dict(**{**CFG, "MODE":mode, ("SMA_MONTHS" if mode=="monthly" else "MA_DAYS"):L}))
        if s is not None: cols[(mode,L)] = s
    mat = pd.DataFrame(cols).dropna(); common = mat.index.intersection(bench.index)
    try:
        srt = [float(mat[k].mean()/mat[k].std()) for k in mat.columns if mat[k].std()>0]
        dsr,_,_ = S1.deflated_sharpe_ratio(strat.reindex(common).values, n_trials=max(len(srt),2), sr_trials=srt)
        pbo,_ = S1.pbo_cscv(mat.reindex(common).values, S=min(16,max(4,(len(common)//2)*2)))
        rc = S1.reality_check_spa(mat.reindex(common).values, benchmark=bench.reindex(common).values)
        rob = dict(DSR=float(dsr), PBO=float(pbo), p_white_rc=rc["p_white_rc"], spa_reliable=rc["spa_reliable"])
        e = (dsr>0.95) and (pbo<0.5)
    except Exception as ex:
        rob = {"err": str(ex)}; e = False
    calmar = lambda p: p["CAGR"]/abs(p["MDD"]) if p["MDD"]<0 else np.inf
    verdict = "검증됨(값 있음)" if (a and b and cc) else ("낙폭만 개선(수익 일부희생)" if (cc and not b) else "검증 실패")
    return dict(strat=ps, benchmark=pb, calmar_strat=round(calmar(ps),3), calmar_bench=round(calmar(pb),3),
                a_sharpe=bool(a), b_cagr_ok=bool(b), c_mdd_cut=bool(cc), robust=rob,
                VERDICT=verdict, note="검증형: production MA200 추세타이밍이 값 더하나. 수익 비열위+낙폭 감소가 핵심. 집행 전 Track.")

def selftest():
    r, rf = load_market(); sig = trend_signal()
    if sig is None: print("[selftest] kospi_index_daily.csv 없음 → fetch 먼저"); return
    s, b = backtest()
    print(f"[selftest] 신호 {int(sig.sum())}/{len(sig)}개월 in-market ({CFG['MODE']} SMA{CFG['SMA_MONTHS']})")
    print(f"  · 전략 {perf(s)}\n  · 벤치 {perf(b)}")
    print("[selftest] OK — 판정은 --judge.")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true"); ap.add_argument("--run", action="store_true"); ap.add_argument("--judge", action="store_true")
    a = ap.parse_args()
    if a.selftest: selftest()
    elif a.run:
        s,b = backtest(); print(json.dumps({"strat":perf(s),"bench":perf(b)}, ensure_ascii=False, indent=2))
    elif a.judge: print(json.dumps(judge(), ensure_ascii=False, indent=2))
    else: print("사용: --selftest | --run | --judge")
