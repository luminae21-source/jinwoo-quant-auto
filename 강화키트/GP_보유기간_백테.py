#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""GP(수익성=총이익/총자산) 롱온리 보유기간 백테 — 재검토_보유기간.py 방법론 그대로.
top분위(상위20%) 롱온리 vs EW-유니버스, 다올 비용(세금0.20%+슬리피지0.05%/편도), 월/분기/반기/연 보유.
PIT: fiscal_year Y 재무는 Y+1년 5월부터 유효(사업보고서 3월말 제출 + 보수적 여유)."""
# §8-3(2026-07-27): tax 0.002→0.0015(실제 증권거래세) · slip 0.0005→0.002045(CS 실측 편도) → 왕복 0.300%→0.559%

import numpy as np, pandas as pd, json
import os as _os, glob as _glob
_HERE=_os.path.dirname(_os.path.abspath(__file__))
_ROOT=_os.path.dirname(_HERE)                      # 강화키트의 상위 = 진우퀀트 루트
BASE=_os.environ.get("JQ_BASE", _ROOT)             # 2026-07-27: 샌드박스 경로 하드코딩 제거
def _find(name):
    for b in (BASE,_ROOT,_HERE,_os.getcwd()):
        h=_glob.glob(_os.path.join(b,"**",name),recursive=True)
        if h: return sorted(h,key=len)[0]
    return _os.path.join(BASE,name)

def load_panel():
    frames=[]
    for fn in ("_월봉종가캐시_KOSPI.csv","_월봉종가캐시_KOSDAQ.csv"):
        d=pd.read_csv(_find(fn),dtype={"code":str}); d["code"]=d["code"].str.zfill(6); frames.append(d)
    allc=pd.concat(frames,ignore_index=True)
    px=allc.pivot_table(index="ym",columns="code",values="close",aggfunc="last").sort_index()
    rets=px.pct_change().mask(lambda x:x.abs()>1.0)
    return px, rets

def load_mcap():
    d=pd.read_csv(_find("종목시총_30년.csv"),dtype={"code":str}); d["code"]=d["code"].str.zfill(6)
    d["ym"]=pd.to_datetime(d["date"]).dt.strftime("%Y-%m")
    return d.pivot_table(index="ym",columns="code",values="mcap",aggfunc="last")

def load_gp_monthly(month_index):
    """PIT GP 패널: (code x ym). fiscal_year Y → 유효시작 (Y+1)-05, 다음 갱신 전까지 유지."""
    d=pd.read_csv(_find("fundamentals_gp_2015_2025.csv"),dtype={"code":str})
    d["code"]=d["code"].str.zfill(6)
    d=d.dropna(subset=["revenue","cogs","assets"])
    d=d[d["assets"]>0]
    d["gp"]=(d["revenue"]-d["cogs"])/d["assets"]
    d["eff"]=(d["fiscal_year"].astype(int)+1).astype(str)+"-05"   # PIT 유효시작월
    # 각 code에 대해 eff월에 gp를 두고 월 인덱스로 ffill
    piv=d.pivot_table(index="eff",columns="code",values="gp",aggfunc="last")
    full=piv.reindex(sorted(set(piv.index)|set(month_index))).sort_index().ffill()
    return full.reindex(month_index)

def stats(x,ann=12):
    x=pd.Series(x).dropna()
    if len(x)==0: return (np.nan,np.nan)
    c=float((1+x).prod()**(ann/len(x))-1)
    s=float(x.mean()/x.std()*np.sqrt(ann)) if x.std()>0 else np.nan
    return c,s

def backtest(H, rets, gp, mcap, topn=200, tax=0.0015, slippage=0.002045, lag_mcap=True):
    """2026-07-27 교정: mcap.loc[t]는 t월말 스냅샷인데 rets.loc[t]는 t-1→t 수익이라
    같은 달 시총으로 유니버스를 고르면 사후 승자 선택이 된다(유니버스_규칙화_검정.py와 동일 결함).
    실행검사 결과 월 보유 순CAGR 12.6% → -1.8% (-14.4%p). lag_mcap=False로 구버전 재현 가능."""
    if lag_mcap and mcap is not None:
        mcap=mcap.shift(1)
    months=list(rets.index)
    held=set(); gross=[]; net=[]; ew=[]; turns=[]
    for k,t in enumerate(months):
        if t not in gp.index: continue
        if mcap is not None and t in mcap.index:
            mc=mcap.loc[t].dropna(); univ=set(mc.sort_values(ascending=False).head(topn).index)
        else: univ=set(rets.columns)
        cur=rets.loc[t]; sigrow=gp.loc[t]
        rebal=(k%H==0) or (not held); cost=0.0
        if rebal:
            valid=[c for c in univ if c in sigrow.index and pd.notna(sigrow.get(c))]
            if len(valid)<max(30,topn//4):
                if not held: continue
            else:
                s=sigrow[valid]; q=pd.qcut(s.rank(method="first"),5,labels=False)
                new=set(s.index[q==4])
                f=1-len(new&held)/len(new) if held else 1.0
                turns.append(f); cost=f*(tax+2*slippage); held=new
        names=[c for c in held if pd.notna(cur.get(c))]
        if not names: continue
        g=cur[names].mean()
        uvalid=[c for c in univ if pd.notna(cur.get(c))]
        gross.append(g); net.append(g-cost); ew.append(cur[uvalid].mean())
    if len(net)<12: return None
    gC,gS=stats(gross); nC,nS=stats(net); eC,eS=stats(ew)
    turnover_yr=(np.mean(turns) if turns else 0)*(12/H)
    return dict(H=H,n=len(net),turnover_yr=round(turnover_yr,2),
                gross_cagr=round(gC*100,1),net_cagr=round(nC*100,1),net_sharpe=round(nS,2),
                ew_cagr=round(eC*100,1),vs_ew_gross=round((gC-eC)*100,1),vs_ew=round((nC-eC)*100,1))

def main():
    px,rets=load_panel(); mcap=load_mcap()
    gp=load_gp_monthly(rets.index)
    # GP 데이터 존재구간으로 제한
    have=gp.notna().sum(axis=1); first=have[have>=30].index.min()
    print(f"GP 유효 시작월: {first}  (fiscal 2015 → 2016-05 유효)")
    rets2=rets.loc[rets.index>=first]; gp2=gp.loc[gp.index>=first]
    print("="*90)
    print("GP(수익성=총이익/총자산) 롱온리 — 다올 비용(수수료0·세금0.20%·슬리피지0.05%/편도)·상폐포함·유동 top200")
    print("="*90)
    print(f"  {'보유':<6}{'회전/년':>8}{'gross':>8}{'gross-EW':>10}{'순CAGR':>9}{'순Sharpe':>9}{'EW':>7}{'순-EW':>8}")
    rows=[]
    for H,lab in [(1,"월"),(3,"분기"),(6,"반기"),(12,"연")]:
        r=backtest(H,rets2,gp2,mcap)
        if r:
            rows.append((lab,r))
            print(f"  {lab:<6}{r['turnover_yr']:>7.1f}x{r['gross_cagr']:>7.1f}%{r['vs_ew_gross']:>+9.1f}%{r['net_cagr']:>8.1f}%{r['net_sharpe']:>9.2f}{r['ew_cagr']:>6.1f}%{r['vs_ew']:>+7.1f}%")
    print("-"*90)
    bestg=max(rows,key=lambda x:x[1]['vs_ew_gross']) if rows else None
    bestn=max(rows,key=lambda x:x[1]['vs_ew']) if rows else None
    if bestg and bestg[1]['vs_ew_gross']>0:
        print(f"  관문1(gross): 🟢 '{bestg[0]}'에서 gross-EW {bestg[1]['vs_ew_gross']:+.1f}%p → 신호 존재 가능. 관문2로.")
        if bestn and bestn[1]['vs_ew']>0:
            print(f"  관문2(순): 🟢 '{bestn[0]}'에서 순-EW {bestn[1]['vs_ew']:+.1f}%p → (B) 재검토 후보!")
        else:
            print(f"  관문2(순): ⚠️ 어느 보유기간도 순-EW 양(+) 못냄 → 회전세금 사망((B) 후보지만 구제 확인 필요)")
    else:
        print(f"  관문1(gross): ⚠️ 어느 보유기간도 gross조차 EW 미달 → (A) 신호없음. 회전세금 사망 아님(비용 무관).")
    print("  ⚠️ 검증용·실현손익 아님·투자자문 아님·책임 본인.")
    json.dump({"GP_longonly":[{**r[1],"보유":r[0]} for r in rows]},
              open(_os.path.join(_ROOT,"강화키트","GP_보유기간_결과.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2)

if __name__=="__main__": main()
