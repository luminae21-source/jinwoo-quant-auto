# -*- coding: utf-8 -*-
"""
jq_dipbuy_backtest.py — 후보 D: 추세 내 눌림목 매수(한국 V자반등 역이용).
아이디어: B(변동성 축소)가 반등을 놓쳐 실패 → **뒤집어서** 추세가 살아있는데 단기 급락이 오면
  비중을 더 담아 반등을 먹는다. 칼날 회피=추세필터(추세 깨지면 A가 현금).
근거: 단기반전(Jegadeesh1990·FAR 1M reversal) + Nagel(2012) 반전수익이 고변동성서 커짐 + 한국 V자 실측.

벤치마크 = **A(추세 단독)**. 질문: 눌림목 오버레이가 A에 **증분**을 주나? (+buy&hold 참고)
집행: 더담기는 레버리지 필요 → 연구판(w>1). 무레버리지 소매판=평상시 현금여유(BASE_W)→눌림에 1.0 투입.
무수정: production·L1 불변. 데이터=korea_factors_monthly·kospi_index_daily(KS11). 성과=골격·미검증.
실행(폴더): py jq_dipbuy_backtest.py --selftest | --run | --judge
"""
import os, sys, json, argparse, warnings, importlib.util
import numpy as np, pandas as pd
warnings.simplefilter("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
def _load(f, m):
    s = importlib.util.spec_from_file_location(m, os.path.join(HERE, f)); x = importlib.util.module_from_spec(s); s.loader.exec_module(x); return x
S1 = _load("stats_v1.py", "stats_v1")

CFG = dict(
    SMA_MONTHS = 10,      # 추세(A)
    DIP_THRESH = -0.03,   # 눌림 정의: 직전월 시장수익 < -3%
    ADD        = 0.5,     # 눌림 시 추가 비중(연구판 → w=1.5)
    BASE_W     = 0.8,     # 무레버리지 소매판 평상시 비중(눌림엔 1.0)
    COST_ONEWAY= 0.0030,
    RETAIL     = False,   # True=무레버리지(현금여유) 판
)

def load_market():
    f = pd.read_csv(os.path.join(HERE, "korea_factors_monthly.csv"), parse_dates=["date"]).set_index("date")
    rf = f["RF"].fillna(0.0); return f["MKT"].fillna(0.0)+rf, rf

def load_kospi_m():
    p = os.path.join(HERE, "kospi_index_daily.csv")
    if not os.path.exists(p): return None
    d = pd.read_csv(p, parse_dates=["Date"]).set_index("Date")["Close"]
    return d.resample("ME").last()

def weights(cfg=None):
    """월별 목표비중 w: 하락추세=0, 상승추세 평상시=1(or BASE_W), 상승+눌림=1+ADD(or 1.0)."""
    c = cfg or CFG; r, rf = load_market(); m = load_kospi_m()
    if m is None: return None, None, None
    trend = (m > m.rolling(c["SMA_MONTHS"]).mean())            # 추세 위?
    lagret = r.shift(1)                                        # 직전월 시장수익
    trend = trend.reindex(r.index).ffill(); dip = (lagret < c["DIP_THRESH"])
    if c["RETAIL"]:
        base, hot = c["BASE_W"], 1.0                           # 무레버리지: 0.8→1.0
    else:
        base, hot = 1.0, 1.0 + c["ADD"]                        # 연구: 1.0→1.5
    w = pd.Series(0.0, index=r.index)
    w[trend] = base
    w[trend & dip] = hot
    return w.shift(1).dropna(), r, rf                          # 신호→익월(look-ahead 0)

def strat_ret(cfg=None):
    w, r, rf = weights(cfg)
    if w is None: return None
    idx = w.index; rr = r.reindex(idx); rff = rf.reindex(idx)
    s = w*rr + (1-w).clip(lower=0)*rff                         # 시장 w + 현금(1-w). w>1이면 현금분 0
    s = s - w.diff().abs().fillna(w.abs())*cfg["COST_ONEWAY"] if cfg else s - w.diff().abs().fillna(w.abs())*CFG["COST_ONEWAY"]
    return s.dropna()

def trend_only(cfg=None):
    """A 벤치(추세 단독, w=1/0)."""
    c = cfg or CFG; r, rf = load_market(); m = load_kospi_m()
    trend = (m > m.rolling(c["SMA_MONTHS"]).mean()).reindex(r.index).ffill().astype(float).shift(1).dropna()
    idx = trend.index; s = trend*r.reindex(idx) + (1-trend)*rf.reindex(idx)
    s = s - trend.diff().abs().fillna(0)*c["COST_ONEWAY"]
    return s.dropna()

def perf(x):
    x = x.dropna(); n=len(x); cum=(1+x).cumprod()
    return dict(CAGR=round(float((1+x).prod()**(12/max(n,1))-1),4), Sharpe=round(float(x.mean()/x.std()*np.sqrt(12)) if x.std()>0 else np.nan,3),
                MDD=round(float((cum/cum.cummax()-1).min()),4), n=n)

def judge():
    d = strat_ret(CFG)
    if d is None: return {"err":"kospi_index_daily.csv 없음 → fetch 먼저"}
    a = trend_only(CFG); bh,_ = load_market()
    idx = d.index.intersection(a.index); pd_, pa, pbh = perf(d.reindex(idx)), perf(a.reindex(idx)), perf(bh.reindex(idx))
    d_ret = strat_ret(dict(**{**CFG,"RETAIL":True}))
    p_ret = perf(d_ret.reindex(idx)) if d_ret is not None else {}
    # 증분: D가 A를 이기나(수익·Sharpe), 낙폭 안 나빠짐
    gA = (pd_["Sharpe"]>pa["Sharpe"]) and (pd_["CAGR"]>=pa["CAGR"]-0.005) and (abs(pd_["MDD"])<=abs(pa["MDD"])*1.05)
    # robustness 격자(DIP_THRESH·ADD)
    import itertools as it; cols={}
    for th,ad in it.product([-0.02,-0.03,-0.05],[0.5,1.0]):
        s=strat_ret(dict(**{**CFG,"DIP_THRESH":th,"ADD":ad}))
        if s is not None: cols[(th,ad)]=s
    mat=pd.DataFrame(cols).dropna(); common=mat.index.intersection(a.index)
    try:
        srt=[float(mat[k].mean()/mat[k].std()) for k in mat.columns if mat[k].std()>0]
        dsr,_,_=S1.deflated_sharpe_ratio(d.reindex(common).values,n_trials=max(len(srt),2),sr_trials=srt)
        pbo,_=S1.pbo_cscv(mat.reindex(common).values,S=min(16,max(4,(len(common)//2)*2)))
        rc=S1.reality_check_spa(mat.reindex(common).values,benchmark=a.reindex(common).values)  # 벤치=A
        rob=dict(DSR=float(dsr),PBO=float(pbo),p_white_rc_vsA=rc["p_white_rc"],spa_reliable=rc["spa_reliable"])
    except Exception as ex: rob={"err":str(ex)}
    verdict = "A에 증분 있음" if gA else "A 대비 증분 없음(기각)"
    return dict(D_research=pd_, D_retail_noLev=p_ret, A_trendonly=pa, buyhold=pbh, beats_A=bool(gA), robust=rob,
                VERDICT=verdict, note="벤치=A(추세단독). 질문=눌림목 오버레이가 A에 증분? 집행=레버리지(연구)/현금여유(소매). Track 전 절대치 신뢰금지.")

def selftest():
    w,r,rf = weights(CFG)
    if w is None: print("[selftest] kospi_index_daily.csv 없음 → fetch 먼저"); return
    print(f"[selftest] w 분포: 현금0 {int((w==0).sum())} · 평상 {int((w==1.0).sum())} · 눌림가산 {int((w>1.0).sum())} (총 {len(w)}개월)")
    d=strat_ret(CFG); a=trend_only(CFG)
    print(f"  · D(연구) {perf(d)}\n  · A(추세단독) {perf(a)}")
    print("[selftest] OK — 판정은 --judge.")

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--selftest",action="store_true"); ap.add_argument("--run",action="store_true"); ap.add_argument("--judge",action="store_true")
    a=ap.parse_args()
    if a.selftest: selftest()
    elif a.run: print(json.dumps({"D":perf(strat_ret(CFG)),"A":perf(trend_only(CFG))},ensure_ascii=False,indent=2))
    elif a.judge: print(json.dumps(judge(),ensure_ascii=False,indent=2))
    else: print("사용: --selftest | --run | --judge")
