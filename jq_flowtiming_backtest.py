# -*- coding: utf-8 -*-
"""
jq_flowtiming_backtest.py — 후보 E: 수급 **타이밍**(시장 외국인/기관 플로우가 시장 방향 예측하나).
**v43 수급-선택과 구분**: v43=수급 높은 '종목' 고르기(선택)=기각. E=시장 전체 플로우로 '언제 시장에 있을까'(타이밍).
근거: 한국 외국인 수급 민감·플로우 지속성(Froot-O'Connell-Seasholes 2001). ⚠️ 되돌아 인과→**반드시 시차**.

방식: 집계 외국인(or 기관) 순매수 트레일링 K개월 합의 부호>0 → 시장 노출 / <0 → 현금. 플로우(t까지)→익월 포지션.
벤치: buy&hold(시장) + A(추세) 참고. 질문: 플로우 타이밍이 buy&hold를 이기나·A에 증분 있나.
무수정: production·L1 불변. 데이터=korea_factors_monthly(수익)·kospi_flow_monthly(집계). 표본 2019~(짧음→검정력 주의).
실행(폴더): py jq_flowtiming_backtest.py --selftest | --run | --judge
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

CFG = dict(INVESTOR="foreign", WINDOW=3, COST_ONEWAY=0.0030)  # foreign|inst|combined, 트레일링 개월

def load_market():
    f = pd.read_csv(os.path.join(HERE, "korea_factors_monthly.csv"), parse_dates=["date"]).set_index("date")
    rf = f["RF"].fillna(0.0); return f["MKT"].fillna(0.0)+rf, rf

def load_flow():
    """kospi_flow_monthly.csv 집계 → 월별 시장 외국인/기관 순매수. 월말 인덱스 정규화."""
    p = os.path.join(HERE, "kospi_flow_monthly.csv")
    if not os.path.exists(p): return None
    d = pd.read_csv(p, dtype={"code": str}); d["date"] = pd.to_datetime(d["date"])
    agg = d.groupby("date")[["foreign_net", "inst_net"]].sum()
    agg.index = agg.index + pd.offsets.MonthEnd(0)                # 월말 정규화
    agg = agg[~agg.index.duplicated(keep="last")]
    agg["combined"] = agg["foreign_net"] + agg["inst_net"]
    return agg

def flow_position(cfg=None):
    c = cfg or CFG; agg = load_flow()
    if agg is None: return None
    col = {"foreign": "foreign_net", "inst": "inst_net", "combined": "combined"}[c["INVESTOR"]]
    sig = agg[col].rolling(c["WINDOW"]).sum()                     # 트레일링 K개월 누적 플로우
    pos = (sig > 0).astype(float)                                 # 순매수면 시장, 순매도면 현금
    return pos

def backtest(cfg=None):
    c = cfg or CFG; r, rf = load_market(); pos = flow_position(c)
    if pos is None: return None, None
    pos = pos.reindex(r.index).ffill().shift(1)                  # 플로우(t)→익월(t+1) 포지션(시차·look-ahead 0)
    idx = pos.dropna().index; pos = pos.reindex(idx); rr = r.reindex(idx); rff = rf.reindex(idx)
    strat = pos*rr + (1-pos)*rff
    strat = strat - pos.diff().abs().fillna(pos.abs())*c["COST_ONEWAY"]
    return strat.dropna(), rr.reindex(strat.dropna().index)

def perf(x):
    x = x.dropna(); n=len(x); cum=(1+x).cumprod()
    return dict(CAGR=round(float((1+x).prod()**(12/max(n,1))-1),4), Sharpe=round(float(x.mean()/x.std()*np.sqrt(12)) if x.std()>0 else np.nan,3),
                MDD=round(float((cum/cum.cummax()-1).min()),4), n=n)

def judge():
    s, b = backtest(CFG)
    if s is None: return {"err": "kospi_flow_monthly.csv 없음"}
    ps, pb = perf(s), perf(b)
    a = ps["Sharpe"] > pb["Sharpe"]; bb = ps["CAGR"] >= pb["CAGR"]  # buy&hold 대비 수익·위험조정 우위
    cc = abs(ps["MDD"]) <= abs(pb["MDD"])
    import itertools as it; cols={}
    for inv,w in it.product(["foreign","inst","combined"],[1,3,6]):
        st,_ = backtest(dict(**{**CFG,"INVESTOR":inv,"WINDOW":w}))
        if st is not None: cols[(inv,w)] = st
    mat = pd.DataFrame(cols).dropna(); common = mat.index.intersection(b.index)
    try:
        srt=[float(mat[k].mean()/mat[k].std()) for k in mat.columns if mat[k].std()>0]
        dsr,_,_=S1.deflated_sharpe_ratio(s.reindex(common).values,n_trials=max(len(srt),2),sr_trials=srt)
        pbo,_=S1.pbo_cscv(mat.reindex(common).values,S=min(16,max(4,(len(common)//2)*2)))
        rc=S1.reality_check_spa(mat.reindex(common).values,benchmark=b.reindex(common).values)
        rob=dict(DSR=float(dsr),PBO=float(pbo),p_white_rc=rc["p_white_rc"],spa_reliable=rc["spa_reliable"])
    except Exception as ex: rob={"err":str(ex)}
    verdict = "buy&hold 이김(수급 타이밍 신호)" if (a and bb and cc) else "buy&hold 미달(기각)"
    return dict(strat=ps, buyhold=pb, beats_bh=bool(a and bb and cc), robust=rob,
                VERDICT=verdict, note="수급 '타이밍'(v43 선택과 구분). 시차 적용·표본 2019~(짧음). 벤치 buy&hold. A 증분은 별도.")

def selftest():
    agg = load_flow()
    if agg is None: print("[selftest] kospi_flow_monthly.csv 없음"); return
    print(f"[selftest] 집계 플로우 {len(agg)}개월 ({agg.index.min().date()}~{agg.index.max().date()})")
    s, b = backtest(CFG)
    pos = flow_position(CFG)
    print(f"  · 시장 노출 개월 {int((pos>0).sum())}/{len(pos.dropna())} ({CFG['INVESTOR']} {CFG['WINDOW']}M)")
    print(f"  · 전략 {perf(s)}\n  · buy&hold {perf(b)}")
    print("[selftest] OK — 판정 --judge.")

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--selftest",action="store_true"); ap.add_argument("--run",action="store_true"); ap.add_argument("--judge",action="store_true")
    a=ap.parse_args()
    if a.selftest: selftest()
    elif a.run: s,b=backtest(); print(json.dumps({"strat":perf(s),"buyhold":perf(b)},ensure_ascii=False,indent=2))
    elif a.judge: print(json.dumps(judge(),ensure_ascii=False,indent=2))
    else: print("사용: --selftest | --run | --judge")
