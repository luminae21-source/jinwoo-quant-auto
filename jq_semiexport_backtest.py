# -*- coding: utf-8 -*-
"""
jq_semiexport_backtest.py — 후보 F Phase2: **반도체 수출 YoY**(비가격 실물 선행)가 코스피 타이밍에 값을 주나.
질문: 수출 YoY 신호가 (1) buy&hold를 이기나 (2) **A(코스피 추세)에 증분**을 주나.
왜 중요: SOX(주가)는 코스피와 정보가 겹쳐 기각됐음. 수출 YoY는 **비가격 실물**이라 코스피 가격과 덜 겹치는
        유일하게 남은 '다른 정보'. 근거=한국 반도체/수출 경제, 실물이 이익·지수를 선행.

⚠️ 발표시차: 수출통계는 익월 공표 → **LAG=2개월 보수 적용**(look-ahead 0). LAG 1/2/3 격자로 강건성 확인.
데이터: korea_factors_monthly(수익)·kospi_index_daily(A)·semi_export_monthly(ECOS 반도체 수출금액지수).
무수정: production·L1 불변. 실행: py jq_semiexport_backtest.py --selftest | --judge
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

CFG = dict(SMA_M=10, LAG=2, COST_ONEWAY=0.0030, LONG=False, FROM=None, DIV_ANNUAL=0.018)
# LAG=발표시차 / LONG=지수수익 장기 / FROM=시작연도(진단) / DIV_ANNUAL=배당수익률(지수는 가격수익이라 보정 필수)

def load_market():
    """기본=korea_factors(2014~,145M). LONG=코스피지수 수익률(2010~,~190M)로 표본 확장(확증용)."""
    f=pd.read_csv(os.path.join(HERE,"korea_factors_monthly.csv"),parse_dates=["date"]).set_index("date")
    rf=f["RF"].fillna(0.0)
    if not CFG["LONG"]:
        return f["MKT"].fillna(0.0)+rf, rf
    k=load_kospi_m()
    if k is None: return f["MKT"].fillna(0.0)+rf, rf
    r=k.pct_change().dropna() + CFG["DIV_ANNUAL"]/12.0   # 지수 가격수익 + 배당 보정 = 총수익 근사
    rf2=rf.reindex(r.index); rf2=rf2.fillna(rf.mean())   # 팩터 없는 구간은 평균 RF
    if CFG.get("FROM"):                              # 진단: 시작연도 제한(기간 vs 시계열 효과 분리)
        cut=pd.Timestamp(f"{CFG['FROM']}-01-01"); r=r[r.index>=cut]; rf2=rf2[rf2.index>=cut]
    return r, rf2

def load_kospi_m():
    p=os.path.join(HERE,"kospi_index_daily.csv")
    if not os.path.exists(p): return None
    d=pd.read_csv(p,parse_dates=["Date"]).set_index("Date")["Close"]
    return d.resample("ME").last()

def load_export():
    """ECOS 반도체 수출금액지수 → 월말 인덱스, YoY."""
    p=os.path.join(HERE,"semi_export_monthly.csv")
    if not os.path.exists(p): return None
    d=pd.read_csv(p,parse_dates=["date"]).set_index("date")["value"]
    d.index = d.index + pd.offsets.MonthEnd(0)
    return d.pct_change(12)                       # YoY

def signals(cfg=None):
    c=cfg or CFG
    kospi=load_kospi_m(); yoy=load_export()
    if kospi is None or yoy is None: return None
    A=(kospi > kospi.rolling(c["SMA_M"]).mean()).astype(float)
    X=(yoy.shift(c["LAG"]) > 0).astype(float)     # 발표시차 반영: 수출YoY>0이면 사이클 확장
    idx=A.index.union(X.index)
    A=A.reindex(idx).ffill(); X=X.reindex(idx).ffill()
    return dict(A=A, EXPORT=X, AND=((A>0)&(X>0)).astype(float), OR=((A>0)|(X>0)).astype(float))

def bt(sig, r, rf, c=None):
    c=c or CFG
    pos=sig.reindex(r.index).ffill().shift(1); idx=pos.dropna().index
    pos=pos.reindex(idx); rr=r.reindex(idx); rff=rf.reindex(idx)
    s=pos*rr+(1-pos)*rff - pos.diff().abs().fillna(pos.abs())*c["COST_ONEWAY"]
    return s.dropna()

def perf(x):
    x=x.dropna(); n=len(x); cum=(1+x).cumprod()
    return dict(CAGR=round(float((1+x).prod()**(12/max(n,1))-1),4),Sharpe=round(float(x.mean()/x.std()*np.sqrt(12)) if x.std()>0 else np.nan,3),
                MDD=round(float((cum/cum.cummax()-1).min()),4),n=n)

def judge():
    S=signals()
    if S is None: return {"err":"semi_export_monthly.csv 또는 kospi_index_daily.csv 없음"}
    r,rf=load_market()
    series={k:bt(v,r,rf) for k,v in S.items()}
    common=None
    for s in series.values(): common=s.index if common is None else common.intersection(s.index)
    bh=r.reindex(common)
    res={k:perf(series[k].reindex(common)) for k in series}; res["buyhold"]=perf(bh)
    pA,pX,pAND,pbh=res["A"],res["EXPORT"],res["AND"],res["buyhold"]
    x_beats_bh=(pX["Sharpe"]>pbh["Sharpe"]) and (pX["CAGR"]>=pbh["CAGR"])
    and_beats_A=(pAND["Sharpe"]>pA["Sharpe"]) and (pAND["CAGR"]>=pA["CAGR"]-0.005) and (abs(pAND["MDD"])<=abs(pA["MDD"]))
    # robustness: LAG 1/2/3 × 신호 4종
    cols={}
    for L in [1,2,3]:
        old=CFG["LAG"]; CFG["LAG"]=L; SS=signals()
        for k,v in SS.items(): cols[(k,L)]=bt(v,r,rf)
        CFG["LAG"]=old
    mat=pd.DataFrame(cols).dropna(); cm=mat.index.intersection(common)
    try:
        srt=[float(mat[c].mean()/mat[c].std()) for c in mat.columns if mat[c].std()>0]
        dsr,_,_=S1.deflated_sharpe_ratio(series["AND"].reindex(cm).values,n_trials=max(len(srt),2),sr_trials=srt)
        pbo,_=S1.pbo_cscv(mat.reindex(cm).values,S=min(16,max(4,(len(cm)//2)*2)))
        rc=S1.reality_check_spa(mat.reindex(cm).values,benchmark=bh.reindex(cm).values)
        rob=dict(DSR=float(dsr),PBO=float(pbo),p_white_rc=rc["p_white_rc"],spa_reliable=rc["spa_reliable"])
    except Exception as ex: rob={"err":str(ex)}
    # 회전율(연 스위치 횟수) — 비용·세금·행동부담의 실체
    yrs = len(common)/12.0
    turn = {k: round(float(S[k].reindex(common.union(S[k].index)).ffill().reindex(common).diff().abs().sum()/yrs), 2) for k in S}
    # 비용 민감도(편도 15/30/50bp) — AND 기준
    cost_sens = {}
    for c_ in [0.0015, 0.0030, 0.0050]:
        old=CFG["COST_ONEWAY"]; CFG["COST_ONEWAY"]=c_
        cost_sens[f"{int(c_*10000)}bp"] = perf(bt(S["AND"], r, rf).reindex(common))
        CFG["COST_ONEWAY"]=old
    # 배당 민감도 — 기각 결론이 배당 가정에 얼마나 걸려있나 (코스피 실측: 99~18 평균 1.49%, 25년 2.3%)
    div_sens = {}
    if CFG["LONG"]:
        for d_ in [0.015, 0.018, 0.022]:
            old=CFG["DIV_ANNUAL"]; CFG["DIV_ANNUAL"]=d_
            r2, rf2 = load_market(); S2 = signals()
            a2 = bt(S2["AND"], r2, rf2); b2 = r2.reindex(a2.index)
            pa2, pb2 = perf(a2), perf(b2)
            gap = round(pa2["CAGR"] - pb2["CAGR"], 4)
            div_sens[f"{d_*100:.1f}%"] = dict(AND_CAGR=pa2["CAGR"], bh_CAGR=pb2["CAGR"], gap_pp=gap,
                                              수익게이트_통과=bool(gap >= -0.01))   # CAGR ≥ bh−1.0%p
            CFG["DIV_ANNUAL"]=old
    # 시장 체류 비율(배당 민감도의 원인)
    in_mkt = {k: round(float(S[k].reindex(common).mean()), 2) for k in S}
    verdict=("수출 증분 있음(A+수출>A)" if and_beats_A else ("수출 단독 buy&hold 이김" if x_beats_bh else "증분 없음(기각)"))
    return dict(perf=res, export_beats_bh=bool(x_beats_bh), combined_AND_beats_A=bool(and_beats_A), lag_months=CFG["LAG"],
                div_annual=CFG["DIV_ANNUAL"], in_market_ratio=in_mkt, turnover_per_year=turn,
                cost_sensitivity_AND=cost_sens, dividend_sensitivity_AND_vs_bh=div_sens,
                robust=rob, VERDICT=verdict, note="배당·회전율·비용·체류비율 민감도 포함. 수익게이트=CAGR≥bh−1.0%p.")

def selftest():
    S=signals()
    if S is None: print("[selftest] semi_export_monthly.csv/kospi_index_daily.csv 없음"); return
    r,rf=load_market(); yoy=load_export()
    print(f"[selftest] 수출YoY {len(yoy.dropna())}개월 ({yoy.dropna().index.min().date()}~{yoy.dropna().index.max().date()}) · LAG={CFG['LAG']}개월")
    print(f"  · 수출 확장(YoY>0) 비율 {float((S['EXPORT']>0).mean()):.0%}")
    for k in ["A","EXPORT","AND","OR"]: print(f"  · {k}: {perf(bt(S[k],r,rf))}")
    print(f"  · buyhold: {perf(r)}")
    print("[selftest] OK — 판정 --judge.")

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--selftest",action="store_true"); ap.add_argument("--judge",action="store_true")
    ap.add_argument("--long",action="store_true",help="장기표본(코스피 지수수익 2010~, ~190M) 확증")
    ap.add_argument("--from",dest="from_y",type=int,default=None,help="시작연도 제한(진단: 기간 vs 시계열 분리)")
    a=ap.parse_args()
    if a.long: CFG["LONG"]=True
    if a.from_y: CFG["FROM"]=a.from_y
    if a.selftest: selftest()
    elif a.judge: print(json.dumps(judge(),ensure_ascii=False,indent=2))
    else: print("사용: --selftest | --judge")
