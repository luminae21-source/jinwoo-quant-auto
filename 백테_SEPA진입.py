#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""백테_SEPA진입.py — 공백#4: SEPA 트렌드템플릿+돌파 진입 엣지 검증. 결과=엣지없음(시장에 짐). 테마는 시점편향으로 검증불가. 데이터: /tmp/_m_all.csv. 사냥터_기획/진우_SEPA테마진입_검증.md"""
import numpy as np, pandas as pd
HC=0.5
d=pd.read_csv("/tmp/_m_all.csv",header=None,names=["code","date","close"],dtype={"code":str})
d["m"]=pd.to_datetime(d["date"],errors="coerce").dt.to_period("M"); d["close"]=pd.to_numeric(d["close"],errors="coerce")
d=d.dropna(subset=["m","close"])
px=d.pivot_table(index="m",columns="code",values="close",aggfunc="last").sort_index()
ma3=px.rolling(3).mean(); ma7=px.rolling(7).mean(); ma10=px.rolling(10).mean()
hi12=px.rolling(12).max(); lo12=px.rolling(12).min(); r6=px/px.shift(6)-1
valid=px.notna()&(px>=1000)&ma10.notna()&lo12.notna()
prr=r6.where(valid).rank(axis=1,pct=True)
newhi=(px>=hi12)&px.notna(); fresh=newhi&(~newhi.shift(1).fillna(False))
# SEPA 트렌드템플릿 + 돌파
sepa=(valid & (px>ma7)&(px>ma10)&(ma7>ma10)&(ma10>ma10.shift(3))&(ma3>ma7)&(ma7>ma10)&(px>ma3)
      &(px>=1.30*lo12)&(px>=0.75*hi12)&(prr>=0.7)&fresh)
# 일반 모멘텀 (앞 검증과 동일)
mom=(valid & fresh & (px>ma10) & (r6>0))
def fwd(h):
    V=px.values; T,N=V.shape; out=np.full((T,N),np.nan)
    lastobs=np.array([np.where(~np.isnan(V[:,j]))[0][-1] if np.any(~np.isnan(V[:,j])) else -1 for j in range(N)])
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
    return pd.DataFrame(out,index=px.index,columns=px.columns)
def summ(f,m):
    v=f.where(m).values.ravel(); v=v[~np.isnan(v)]
    if len(v)==0: return None
    return (len(v),v.mean(),np.median(v),(v>0).mean(),(v>=0.5).mean())
print(f"SEPA·모멘텀·시장 선행수익 · 30년·상폐반영 · {px.index.min()}~{px.index.max()}")
for hz,h in (("6M",6),("12M",12)):
    f=fwd(h)
    print(f"── {hz} 선행 ──")
    print(f"  {'코호트':<10}{'n':>8}{'평균':>8}{'중앙':>8}{'승률':>7}{'대박50':>8}")
    for nm,mask in (("시장",valid),("모멘텀돌파",mom),("SEPA",sepa)):
        s=summ(f,mask)
        if s: print(f"  {nm:<10}{s[0]:>8,}{s[1]*100:>+7.1f}%{s[2]*100:>+7.1f}%{s[3]*100:>6.0f}%{s[4]*100:>7.0f}%")
    print()
