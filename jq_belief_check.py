# -*- coding: utf-8 -*-
"""
jq_belief_check.py — **진단(전략 아님)**: 진우의 경험 2건이 데이터와 맞는가.
확증편향 점검용. 매매 규칙을 만들지 않는다. 사실만 잰다.

① "국민연금 등 기관이 9월 저점에 산다"
   → 월별 기관/외국인 순매수 집계(kospi_flow_monthly). 9월에 정말 몰리나? 그게 수익과 연결되나?
② "주도 섹터가 2~3개월 단위로 바뀐다"
   → 뜨거운 섹터(월간 상위)가 **실제 몇 개월 유지**되는지 측정(theme_heat 엔진 재사용).

무수정: production·L1 불변. 실행: py jq_belief_check.py --run
"""
import os, sys, json, argparse, warnings, importlib.util
import numpy as np, pandas as pd
warnings.simplefilter("ignore")
HERE=os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def belief1_기관9월():
    """월별 기관·외국인 순매수 + 월별 시장수익 대조."""
    p=os.path.join(HERE,"kospi_flow_monthly.csv")
    if not os.path.exists(p): return {"err":"kospi_flow_monthly.csv 없음"}
    d=pd.read_csv(p,dtype={"code":str}); d["date"]=pd.to_datetime(d["date"])
    agg=d.groupby("date")[["foreign_net","inst_net"]].sum()
    agg.index=agg.index+pd.offsets.MonthEnd(0); agg=agg[~agg.index.duplicated(keep="last")]
    agg["month"]=agg.index.month
    # 조 단위로 환산
    by=agg.groupby("month")[["foreign_net","inst_net"]].mean()/1e12
    # 시장 월수익
    ip=os.path.join(HERE,"kospi_index_daily.csv"); mret=None
    if os.path.exists(ip):
        k=pd.read_csv(ip,parse_dates=["Date"]).set_index("Date")["Close"].resample("ME").last()
        r=k.pct_change().dropna(); mret=r.groupby(r.index.month).mean()
    out={}
    for m in range(1,13):
        out[m]=dict(기관_순매수_조=round(float(by.loc[m,"inst_net"]),2) if m in by.index else None,
                    외국인_순매수_조=round(float(by.loc[m,"foreign_net"]),2) if m in by.index else None,
                    시장_평균월수익=round(float(mret.loc[m]),4) if (mret is not None and m in mret.index) else None)
    # 9월 순위
    if len(by):
        rank_inst=int(by["inst_net"].rank(ascending=False).loc[9]) if 9 in by.index else None
        out["_판정"]=dict(
            기관순매수_9월순위=f"{rank_inst}/12위 (1위=가장 많이 삼)",
            기관_9월=round(float(by.loc[9,"inst_net"]),2), 기관_최대월=int(by["inst_net"].idxmax()),
            해석="9월 순위가 1~3위면 '기관이 9월에 산다'는 사실. 하위권이면 확증편향.")
    out["_표본"]="kospi_flow_monthly (2019~2026, 200종목 집계)"
    return out

def belief2_섹터지속():
    """뜨거운 섹터(월간 heat 상위 3)가 몇 개월 연속 유지되나."""
    try:
        def _load(f,m):
            s=importlib.util.spec_from_file_location(m,os.path.join(HERE,f)); x=importlib.util.module_from_spec(s); s.loader.exec_module(x); return x
        TH=_load("theme_heat.py","theme_heat")
        E,TC=TH._engines(); panel=TH.load_panel(); fine,name=TC.load_fine_map()
    except Exception as e:
        return {"err":f"theme_heat 로드 실패: {e} (폴더에서 실행하세요)"}
    tops={}
    n=len(panel)
    for i in range(max(0,n-120), n):          # 최근 10년
        try:
            df,_,_=TH.compute_theme_heat(panel,fine,name,E,TC,min_members=5,i=i)
            if df is None or len(df)==0: continue
            tops[i]=set(df.sort_values("heat_score",ascending=False).head(3)["theme"])
        except Exception: continue
    if len(tops)<12: return {"err":"heat 계산 부족"}
    ks=sorted(tops)
    # 각 섹터가 top3에 '연속으로' 머문 기간 분포
    runs=[]; cur={}
    for i in ks:
        for s in tops[i]: cur[s]=cur.get(s,0)+1
        for s in list(cur):
            if s not in tops[i]:
                runs.append(cur.pop(s))
    runs += list(cur.values())
    runs=pd.Series(runs)
    # top3 교체율
    turn=[len(tops[ks[j]] - tops[ks[j-1]])/3 for j in range(1,len(ks))]
    return dict(
        표본_개월=len(ks),
        top3_연속유지_개월=dict(평균=round(float(runs.mean()),1), 중앙값=float(runs.median()),
                               p25=float(runs.quantile(.25)), p75=float(runs.quantile(.75)), 최장=int(runs.max())),
        월간_top3_교체율=round(float(np.mean(turn)),2),
        해석="연속유지 중앙값이 2~3개월이면 진우 경험이 맞음. 1개월이면 '너무 빨라 잡을 수 없음'. 6개월+면 '느려서 로테이션 아님'.")

def run():
    return {"①기관_9월매수설": belief1_기관9월(), "②섹터_2~3개월_로테이션설": belief2_섹터지속(),
            "note":"진단이지 전략 아님. 사실 확인용."}

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--run",action="store_true")
    a=ap.parse_args()
    if a.run: print(json.dumps(run(),ensure_ascii=False,indent=2))
    else: print("사용: --run  (반드시 Desktop\\진우퀀트 폴더에서)")
