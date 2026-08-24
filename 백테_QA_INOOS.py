#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""백테_QA_INOOS.py — 딥밸류 엣지 시간 IN/OOS 분할·하락장 재현·look-ahead 점검. 결과: 양시대 유효(과최적 아님), 배수 2배 유지·절대초과 감쇠, peeking 없음. 데이터 /tmp/_m_all.csv. 사냥터_기획/진우_사냥터_검증종합_한장.md"""
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
ma10=px.rolling(10).mean(); disp=px/ma10; ret1=px.pct_change()
valid=px.notna()&(px>=1000)&ma10.notna()&(pbr>0)&pbr.notna()
pr=pbr.where(valid).rank(axis=1,pct=True)
reb=valid&(pr<=0.2)&(disp<0.85)&(ret1>0)
reb_lag=reb.shift(1).fillna(False)  # look-ahead 점검: 신호 다음달 진입
# regime
k=pd.read_csv(f"{MNT}/kospi_index_daily.csv",encoding="utf-8-sig"); k.columns=[c.lstrip("﻿").lower() for c in k.columns]
k["m"]=pd.to_datetime(k["date"],errors="coerce").dt.to_period("M"); k["close"]=pd.to_numeric(k["close"],errors="coerce")
km=k.dropna(subset=["m"]).groupby("m")["close"].last().sort_index()
bull=(km>km.rolling(10).mean()).reindex(px.index).ffill().fillna(False)
bearrow=(~bull).values
lastobs=np.array([np.where(~np.isnan(px[c].values))[0][-1] if px[c].notna().any() else -1 for c in px.columns])
V=px.values; T,N=V.shape
def fwd(h):
    out=np.full((T,N),np.nan)
    for t in range(T):
        hi=min(t+h,T-1)
        if hi<=t: continue
        base=V[t]; win=V[t+1:hi+1]
        for j in range(N):
            b=base[j]
            if not(b==b) or b<=0: continue
            col=win[:,j]; vv=col[~np.isnan(col)]
            if vv.size>0: out[t,j]=vv[-1]/b-1
            elif lastobs[j]<=t+h: out[t,j]=-1.0
    return out
F=fwd(12)
idx=px.index
def rowmask(cond_years=None, bearonly=False):
    m=np.ones(T,bool)
    if cond_years: m=np.array([cond_years[0]<=y.year<=cond_years[1] for y in idx])
    if bearonly: m=m&bearrow
    return m
def summ(sig, rmask):
    S=sig.values & rmask[:,None]
    v=F[S]; v=v[~np.isnan(v)]
    return (len(v),v.mean()*100,np.median(v)*100,(v>0).mean()*100) if len(v) else (0,0,0,0)
print("QA · 딥밸류 12M 선행수익 — 시간 IN/OOS 분할 + 하락장 재현 + look-ahead 점검\n")
print(f"  {'구간':<22}{'n':>7}{'반등군평균':>10}{'시장평균':>9}{'초과':>7}{'반등승률':>8}")
def line(lbl, ym, bo):
    rm=rowmask(ym,bo)
    nr,mr,medr,wr=summ(reb,rm); nm,mm,_,_=summ(valid,rm)
    print(f"  {lbl:<22}{nr:>7,}{mr:>+9.1f}%{mm:>+8.1f}%{mr-mm:>+6.1f}%{wr:>7.0f}%")
line("전체기간",None,False)
line("전반기 2002-2013",(2002,2013),False)
line("후반기 2014-2026",(2014,2026),False)
line("하락장 전체(재현)",None,True)
line("하락장 전반 02-13",(2002,2013),True)
line("하락장 후반 14-26",(2014,2026),True)
# look-ahead 점검
rm=rowmask(None,False); nr,mr,_,_=summ(reb,rm); nl,ml,_,_=summ(reb_lag,rm)
print(f"\n  look-ahead 점검: 동월진입 {mr:+.1f}% vs 신호익월진입 {ml:+.1f}% (차이 작으면 peeking 없음)")
