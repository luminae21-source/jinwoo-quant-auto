#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""백테_전시장확장.py — 바닥반등 신호 전 시장·스윙 검증. 딥밸류바닥=전시장유효(강세12M+17.8%), 바닥반등=약하나 유효, 지지반등=실패, 단기스윙 엣지없음. 데이터 /tmp/_m_all.csv. 사냥터_기획/진우_전시장확장_검증.md"""
import numpy as np, pandas as pd
MNT="/sessions/upbeat-epic-bohr/mnt/진우퀀트"
d=pd.read_csv("/tmp/_m_all.csv",header=None,names=["code","date","close"],dtype={"code":str})
d["m"]=pd.to_datetime(d["date"],errors="coerce").dt.to_period("M"); d["close"]=pd.to_numeric(d["close"],errors="coerce")
d=d.dropna(subset=["m","close"])
px=d.pivot_table(index="m",columns="code",values="close",aggfunc="last").sort_index()
fr=[]
for mk in ("KOSPI","KOSDAQ"):
    x=pd.read_csv(f"{MNT}/종목재무_KRX_{mk}.csv",dtype={"code":str},encoding="utf-8-sig"); x.columns=[c.lstrip("﻿") for c in x.columns]
    fr.append(x[["date","code","PBR"]])
p=pd.concat(fr,ignore_index=True); p["code"]=p["code"].str.zfill(6)
p["m"]=pd.to_datetime(p["date"],errors="coerce").dt.to_period("M"); p["PBR"]=pd.to_numeric(p["PBR"],errors="coerce")
p=p.dropna(subset=["m"])
pbr=p.pivot_table(index="m",columns="code",values="PBR",aggfunc="last").reindex(px.index).reindex(columns=px.columns)
ma10=px.rolling(10).mean(); disp=px/ma10; ret1=px.pct_change(); lo12=px.rolling(12).min()
valid=px.notna()&(px>=1000)&ma10.notna()
vpbr=valid&(pbr>0)&pbr.notna()
pr=pbr.where(vpbr).rank(axis=1,pct=True)
deep=vpbr&(pr<=0.2)&(disp<0.85)&(ret1>0)          # 하락장 딥밸류(현행)
bottom=valid&(disp<0.85)&(ret1>0)                  # 바닥반등(밸류無, regime무관)
support=valid&lo12.notna()&(px<=1.15*lo12)&(ret1>0) # 지지반등(12M저 부근+턴)
k=pd.read_csv(f"{MNT}/kospi_index_daily.csv",encoding="utf-8-sig"); k.columns=[c.lstrip("﻿").lower() for c in k.columns]
k["m"]=pd.to_datetime(k["date"],errors="coerce").dt.to_period("M"); k["close"]=pd.to_numeric(k["close"],errors="coerce")
km=k.dropna(subset=["m"]).groupby("m")["close"].last().sort_index()
bull=(km>km.rolling(10).mean()).reindex(px.index).ffill().fillna(False).values
V=px.values; T,N=V.shape
lastobs=np.array([np.where(~np.isnan(V[:,j]))[0][-1] if np.any(~np.isnan(V[:,j])) else -1 for j in range(N)])
tidx=np.arange(T)[:,None]
def fwd(h):
    fut=px.shift(-h).values; out=fut/V-1
    valid_now=~np.isnan(V); nanfut=np.isnan(fut); dw=(tidx+h)>=lastobs[None,:]
    return np.where(valid_now&nanfut&dw,-1.0,out)
def mean_of(sig,rows,F):
    S=sig.values&rows[:,None]; v=F[S]; v=v[~np.isnan(v)]
    return (v.mean()*100,len(v)) if len(v) else (np.nan,0)
print("바닥반등 확장 검증 · 코호트 평균수익 vs 시장(초과) · 강세장/하락장 × 스윙기간 · 30년·상폐반영\n")
for regnm,rows in (("강세장",bull),("하락장",~bull)):
    print(f"■ {regnm}")
    print(f"  {'신호':<18}"+"".join(f"{h+'M초과':>10}" for h in ("3","6","12")))
    Fs={h:fwd(h) for h in (3,6,12)}
    mkt={h:mean_of(valid,rows,Fs[h])[0] for h in (3,6,12)}
    for nm,sig in (("시장(기준)",valid),("딥밸류바닥",deep),("바닥반등(밸류無)",bottom),("지지반등(12M저)",support)):
        cells=[]
        for h in (3,6,12):
            mv,n=mean_of(sig,rows,Fs[h])
            cells.append("  기준" if nm=="시장(기준)" else (f"{mv-mkt[h]:>+9.1f}%" if mv==mv else "   -"))
        n12=mean_of(sig,rows,Fs[12])[1]
        print(f"  {nm:<18}"+"".join(f"{c:>10}" for c in cells)+f"   n={n12:,}")
    print()
print("※ 초과=코호트평균−시장평균(%p). 양수=시장 초과. 신호효능·결정 본인")
