#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""백테_생존편향_보정.py — 공백#5: PBR 커버리지 진단 + 재무無 가격프록시(완전클린) 재검증. 결과=엣지 유지(+22.7% vs 시장+9.3%), 단 클린판 중앙 낮음(패자↑→분산 필수). 데이터 /tmp/_m_all.csv. 사냥터_기획/진우_PBR생존편향_검증.md"""
import numpy as np, pandas as pd
MNT="/sessions/upbeat-epic-bohr/mnt/진우퀀트"; HC=0.5
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
hi60=px.rolling(60,min_periods=24).max()  # 5년 고가
tradable=px.notna()&(px>=1000)&ma10.notna()
haspbr=tradable&(pbr>0)&pbr.notna()
# ── ① 커버리지 진단 (2002+ PBR 존재구간) ──
mask02=px.index>=pd.Period("2002-01")
cov=(haspbr[mask02].sum(axis=1)/tradable[mask02].sum(axis=1))
# 상폐임박(다음 12개월 내 소멸) 종목의 PBR 커버리지 vs 생존
lastobs={c: np.where(~np.isnan(px[c].values))[0][-1] if px[c].notna().any() else -1 for c in px.columns}
Tn=len(px.index)
soon=pd.DataFrame(False,index=px.index,columns=px.columns)
for j,c in enumerate(px.columns):
    lo=lastobs[c]
    if lo>=0 and lo<Tn-1:  # 데이터가 끝에 도달 안함(=상폐)
        for t in range(max(0,lo-12),lo+1): soon.iat[t,j]=True
soon=soon&tradable
cov_soon=(haspbr&soon)[mask02].sum().sum()/max((soon&tradable)[mask02].sum().sum(),1)
cov_all=haspbr[mask02].sum().sum()/max(tradable[mask02].sum().sum(),1)
print("── ① PBR 커버리지 진단 (2002~) ──")
print(f"  전체 거래종목 중 PBR 보유: {cov_all*100:.0f}% (월평균 {cov.mean()*100:.0f}%)")
print(f"  상폐임박(12M내 소멸) 종목의 PBR 보유: {cov_soon*100:.0f}%")
print(f"  → 상폐임박이 전체보다 {'낮으면 선택편향' if cov_soon<cov_all else '비슷/높으면 편향 작음'} (차이 {(cov_all-cov_soon)*100:+.0f}%p)")
# ── ② 가격기반 완전클린 프록시 재검증 ──
valid=tradable&(pbr>0)&pbr.notna()
pr=pbr.where(valid).rank(axis=1,pct=True)
reb_pbr=valid&(pr<=0.2)&(disp<0.85)&(ret1>0)
# 클린: 재무 안씀. 저평가=price/5년고 저분위, 과매도, 턴
vt=tradable&hi60.notna()
p5=(px/hi60).where(vt).rank(axis=1,pct=True)
reb_clean=vt&(p5<=0.2)&(disp<0.85)&(ret1>0)
ovsold_turn=tradable&(disp<0.85)&(ret1>0)
def fwd(h):
    V=px.values; T,N=V.shape; out=np.full((T,N),np.nan)
    lob=np.array([lastobs[c] for c in px.columns])
    for t in range(T):
        hi=min(t+h,T-1)
        if hi<=t: continue
        base=V[t]; win=V[t+1:hi+1]
        for j in range(N):
            b=base[j]
            if not(b==b) or b<=0: continue
            col=win[:,j]; vv=col[~np.isnan(col)]
            if vv.size>0: out[t,j]=vv[-1]/b-1
            elif lob[j]<=t+h: out[t,j]=-1.0
    return pd.DataFrame(out,index=px.index,columns=px.columns)
f12=fwd(12)
def summ(m):
    v=f12.where(m).values.ravel(); v=v[~np.isnan(v)]
    return (len(v),v.mean(),np.median(v),(v>0).mean(),(v>=0.5).mean()) if len(v) else None
print("\n── ② 12M 선행수익 (재무PBR vs 완전클린 가격프록시) ──")
print(f"  {'코호트':<22}{'n':>8}{'평균':>8}{'중앙':>8}{'승률':>7}{'대박50':>8}")
for nm,mask in (("시장(전체)",valid),("PBR딥밸류(재무)",reb_pbr),("가격딥밸류(클린5년고)",reb_clean),("과매도+턴(밸류無)",ovsold_turn)):
    s=summ(mask)
    if s: print(f"  {nm:<22}{s[0]:>8,}{s[1]*100:>+7.1f}%{s[2]*100:>+7.1f}%{s[3]*100:>6.0f}%{s[4]*100:>7.0f}%")
print("\n※ 가격딥밸류=재무 안 쓰고 30년 가격패널만(선택·수익 양면 완전 survivorship-clean). 신호효능·결정 본인")
