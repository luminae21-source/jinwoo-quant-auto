# -*- coding: utf-8 -*-
"""
jq_semicycle_backtest.py — 후보 F: 반도체 사이클(SOX) 선행신호로 코스피 타이밍.
가설: SOX(필라델피아 반도체지수) 추세가 코스피를 선행 → SOX 추세 위일 때 코스피 노출.
근거: 한국=반도체/수출 경제, SOX가 미국장서 먼저 움직임(반동행·약선행). 다른 종류 정보(A=코스피 자기추세)에 증분?
벤치: buy&hold + A(코스피 추세) + 결합(A AND/OR SOX). 질문=SOX가 buy&hold 이기나·A에 증분 주나.
무수정: production·L1 불변. 데이터=korea_factors_monthly(수익)·kospi_index_daily(A)·sox_daily(F). SOX 없으면 fetch_sox_daily.py 먼저.
※ 반도체 수출 YoY(선행 실물)는 Phase2에서 합류(ECOS). 지금은 SOX만.
실행(폴더): py jq_semicycle_backtest.py --selftest | --judge
"""
import os, sys, json, argparse, warnings, importlib.util
import numpy as np, pandas as pd
warnings.simplefilter("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
def _load(f,m):
    s=importlib.util.spec_from_file_location(m,os.path.join(HERE,f)); x=importlib.util.module_from_spec(s); s.loader.exec_module(x); return x
S1=_load("stats_v1.py","stats_v1")
CFG=dict(SMA_M=10, COST_ONEWAY=0.0030)

def load_market():
    f=pd.read_csv(os.path.join(HERE,"korea_factors_monthly.csv"),parse_dates=["date"]).set_index("date")
    rf=f["RF"].fillna(0.0); return f["MKT"].fillna(0.0)+rf, rf
def _m_close(path):
    if not os.path.exists(os.path.join(HERE,path)): return None
    d=pd.read_csv(os.path.join(HERE,path),parse_dates=["Date"]).set_index("Date")["Close"]
    return d.resample("ME").last()
def trend_sig(series, W):
    return (series > series.rolling(W).mean())

def positions():
    """각 신호의 월별 in/out(1/0), 익월 적용(look-ahead 0)."""
    kospi=_m_close("kospi_index_daily.csv"); sox=_m_close("sox_daily.csv")
    if kospi is None or sox is None: return None
    A=trend_sig(kospi,CFG["SMA_M"]); F=trend_sig(sox,CFG["SMA_M"])
    idx=A.index.union(F.index)
    A=A.reindex(idx).ffill().astype(float); F=F.reindex(idx).ffill().astype(float)
    return dict(A=A, SOX=F, AND=((A>0)&(F>0)).astype(float), OR=((A>0)|(F>0)).astype(float))

def bt(sig, r, rf):
    pos=sig.reindex(r.index).ffill().shift(1); idx=pos.dropna().index
    pos=pos.reindex(idx); rr=r.reindex(idx); rff=rf.reindex(idx)
    s=pos*rr+(1-pos)*rff - pos.diff().abs().fillna(pos.abs())*CFG["COST_ONEWAY"]
    return s.dropna()

def perf(x):
    x=x.dropna(); n=len(x); cum=(1+x).cumprod()
    return dict(CAGR=round(float((1+x).prod()**(12/max(n,1))-1),4),Sharpe=round(float(x.mean()/x.std()*np.sqrt(12)) if x.std()>0 else np.nan,3),
                MDD=round(float((cum/cum.cummax()-1).min()),4),n=n)

def judge():
    P=positions()
    if P is None: return {"err":"kospi_index_daily.csv 또는 sox_daily.csv 없음 → fetch 먼저"}
    r,rf=load_market()
    out={}; series={}
    for k,sig in P.items(): series[k]=bt(sig,r,rf)
    common=None
    for s in series.values(): common=s.index if common is None else common.intersection(s.index)
    bh=r.reindex(common)
    res={k:perf(series[k].reindex(common)) for k in series}; res["buyhold"]=perf(bh)
    pA=res["A"]; pSOX=res["SOX"]; pAND=res["AND"]; pbh=res["buyhold"]
    sox_beats_bh = (pSOX["Sharpe"]>pbh["Sharpe"]) and (pSOX["CAGR"]>=pbh["CAGR"])
    combined_beats_A = (pAND["Sharpe"]>pA["Sharpe"]) and (pAND["CAGR"]>=pA["CAGR"]-0.005) and (abs(pAND["MDD"])<=abs(pA["MDD"]))
    # robustness: SMA 8/10/12 × 신호 4종
    import itertools as it; cols={}
    for W in [8,10,12]:
        old=CFG["SMA_M"]; CFG["SMA_M"]=W; PP=positions()
        for k,sig in PP.items(): cols[(k,W)]=bt(sig,r,rf)
        CFG["SMA_M"]=old
    mat=pd.DataFrame(cols).dropna(); cm=mat.index.intersection(common)
    try:
        srt=[float(mat[c].mean()/mat[c].std()) for c in mat.columns if mat[c].std()>0]
        dsr,_,_=S1.deflated_sharpe_ratio(series["AND"].reindex(cm).values,n_trials=max(len(srt),2),sr_trials=srt)
        pbo,_=S1.pbo_cscv(mat.reindex(cm).values,S=min(16,max(4,(len(cm)//2)*2)))
        rc=S1.reality_check_spa(mat.reindex(cm).values,benchmark=bh.reindex(cm).values)
        rob=dict(DSR=float(dsr),PBO=float(pbo),p_white_rc=rc["p_white_rc"],spa_reliable=rc["spa_reliable"])
    except Exception as ex: rob={"err":str(ex)}
    verdict = ("SOX 증분 있음(A+SOX>A)" if combined_beats_A else ("SOX 단독은 buy&hold 이김" if sox_beats_bh else "증분 없음(기각)"))
    return dict(perf=res, sox_beats_bh=bool(sox_beats_bh), combined_AND_beats_A=bool(combined_beats_A), robust=rob,
                VERDICT=verdict, note="SOX 선행신호. A(코스피추세)에 증분 여부 핵심. 반도체수출YoY는 Phase2. 표본·집행 전 Track.")

def selftest():
    P=positions()
    if P is None: print("[selftest] sox_daily.csv/kospi_index_daily.csv 없음 → fetch 먼저"); return
    r,rf=load_market()
    for k in ["A","SOX","AND","OR"]:
        print(f"  · {k}: {perf(bt(P[k],r,rf))}")
    print(f"  · buyhold: {perf(r)}")
    print("[selftest] OK — 판정 --judge.")

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--selftest",action="store_true"); ap.add_argument("--judge",action="store_true")
    a=ap.parse_args()
    if a.selftest: selftest()
    elif a.judge: print(json.dumps(judge(),ensure_ascii=False,indent=2))
    else: print("사용: --selftest | --judge")
