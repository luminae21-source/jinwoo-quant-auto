#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""백테_기존규칙_재검증.py — 공백#6: §1손절·§2익절목표 단조성 재검증. §2는 모멘텀 한정(딥밸류 예외). 데이터 /tmp/_q_all.csv. 사냥터_기획/진우_기존규칙_재검증.md"""
import numpy as np, pandas as pd
MAXH=36; HC=0.5; LIQMIN=5e8
d=pd.read_csv("/tmp/_q_all.csv",header=None,names=["code","date","close","liq"],dtype={"code":str})
d["m"]=pd.to_datetime(d["date"],errors="coerce").dt.to_period("M")
d["close"]=pd.to_numeric(d["close"],errors="coerce"); d["liq"]=pd.to_numeric(d["liq"],errors="coerce")
d=d.dropna(subset=["m","close"])
px=d.pivot_table(index="m",columns="code",values="close",aggfunc="last").sort_index()
liq=d.pivot_table(index="m",columns="code",values="liq",aggfunc="last").reindex_like(px)
ma10=px.rolling(10).mean()
valid=px.notna()&(px>=1000)&ma10.notna()&(liq>=LIQMIN)&(px>ma10)  # 상승추세 유동종목 = 일반 스윙매수
V=px.values; T,N=V.shape
lastobs=np.array([np.where(~np.isnan(V[:,j]))[0][-1] if np.any(~np.isnan(V[:,j])) else -1 for j in range(N)])
ent=valid.stack(); ent=ent[ent].reset_index(); ent.columns=["m","code","f"]
ent=ent.iloc[::5].reset_index(drop=True)  # 1/5 샘플
mi={m:i for i,m in enumerate(px.index)}; cimap={c:j for j,c in enumerate(px.columns)}
RULES=["보유36M","손절20%","손절30%","목표+30%","목표+50%","목표+100%","트레일30%"]
acc={r:[] for r in RULES}; hold={r:[] for r in RULES}
for _,row in ent.iterrows():
    t0=mi[row["m"]]; j=cimap[row["code"]]; E=V[t0,j]
    if E!=E or E<=0: continue
    end=min(t0+MAXH,T-1); peak=E; res={r:None for r in RULES}
    for t in range(t0+1,end+1):
        P=V[t,j]; last=(t==end); hh=t-t0
        if P!=P:
            lv=V[t-1,j]
            for r in RULES:
                if res[r] is None: res[r]=(lv*(1-HC)/E-1,hh)
            break
        if P>peak: peak=P
        ret=P/E-1
        if res["보유36M"] is None and last: res["보유36M"]=(ret,hh)
        for lab,x in (("손절20%",.20),("손절30%",.30)):
            if res[lab] is None:
                if P<=E*(1-x): res[lab]=(-x,hh)
                elif last: res[lab]=(ret,hh)
        for lab,x in (("목표+30%",.30),("목표+50%",.50),("목표+100%",1.0)):
            if res[lab] is None:
                if P>=E*(1+x): res[lab]=(x,hh)
                elif last: res[lab]=(ret,hh)
        if res["트레일30%"] is None:
            if P<=peak*0.70: res["트레일30%"]=(peak*0.70/E-1,hh)
            elif last: res["트레일30%"]=(ret,hh)
    for k,v in res.items():
        if v is not None: acc[k].append(v[0]); hold[k].append(v[1])
print(f"§1·§2 재검증 · 일반진입(상승추세 유동종목) {len(acc['보유36M']):,}건(1/5) · 30년·상폐반영 · 최대36M")
print(f"  {'매도규칙':<12}{'평균':>8}{'중앙':>8}{'승률':>7}{'대박50':>8}{'보유월':>7}{'연율화':>8}")
for r in RULES:
    a=np.array(acc[r]); h=np.array(hold[r])
    if len(a)==0: continue
    mean=a.mean(); ann=(1+mean)**(12/max(h.mean(),1))-1
    print(f"  {r:<12}{mean*100:>+7.1f}%{np.median(a)*100:>+7.1f}%{(a>0).mean()*100:>6.0f}%{(a>=0.5).mean()*100:>7.0f}%{h.mean():>7.1f}{ann*100:>+7.1f}%")
print("\n※ 월봉 종가기준(intraday 미반영) · 신호효능 · 결정 본인")
