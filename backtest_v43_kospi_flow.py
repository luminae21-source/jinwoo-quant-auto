#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""backtest_v43_kospi_flow.py — KOSPI 수급팩터 1회 판정 (사전등록 동결 2026-06-14).
합격선(v42 동일·4중 AND): ①EW비열위 ②MKT알파≥+3%p ③IR_MKT≥0.30 AND Sharpe≥MKT−0.01 ④MDD비악화.
변형 3종: 외국인/기관/합산. 3M누적/시총, top-20 EW 월리밸, 35bp. ⚠️ 생존편향 잔존(현 구성종목).
실행: python backtest_v43_kospi_flow.py   | 입력: kospi_monthly_prices.csv, liquidity_sector.csv, kospi_flow_monthly.csv"""
import sys
from pathlib import Path
import numpy as np, pandas as pd
BASE=Path(__file__).parent.resolve(); COST=0.0035; N=20
def rd(n,**k): return pd.read_csv(BASE/n,encoding='utf-8-sig',**k)
def lpx(f):
    d=rd(f); d=d.rename(columns={d.columns[0]:'Date'}); d['Date']=pd.to_datetime(d['Date']); d=d.set_index('Date').sort_index()
    d.columns=[str(c).zfill(6) for c in d.columns]; d=d.apply(pd.to_numeric,errors='coerce'); return d[[c for c in d.columns if d[c].notna().sum()>=6]]
def metrics(r):
    r=np.asarray([x for x in r if x==x],float)
    if len(r)==0: return dict(CAGR=np.nan,Sharpe=np.nan,MDD=np.nan,n=0)
    cum=np.prod(1+r)-1; ann=(1+cum)**(12/len(r))-1; vol=r.std()*np.sqrt(12)
    cc=np.cumprod(1+r); mdd=((cc-np.maximum.accumulate(cc))/np.maximum.accumulate(cc)).min()
    return dict(CAGR=ann*100,Sharpe=(ann/vol if vol else 0),MDD=mdd*100,n=len(r))
def ir(a,b):
    a=np.asarray(a,float); b=np.asarray(b,float); ac=a-b; return (ac.mean()*12)/(ac.std()*np.sqrt(12)) if ac.std() else 0

px=lpx('kospi_monthly_prices.csv')
liq=rd('liquidity_sector.csv',dtype={'code':str}); liq['code']=liq['code'].str.zfill(6); mc=dict(zip(liq['code'],pd.to_numeric(liq['mcap'],errors='coerce')))
fl=rd('kospi_flow_monthly.csv',dtype={'code':str}); fl['code']=fl['code'].str.zfill(6); fl['date']=pd.to_datetime(fl['date'])
def flpanel(col): return fl.pivot_table(index='date',columns='code',values=col,aggfunc='sum').sort_index().rolling(3).sum()
FOR=flpanel('foreign_net'); INS=flpanel('inst_net'); fl['comb']=fl['foreign_net'].fillna(0)+fl['inst_net'].fillna(0); COMB=flpanel('comb')
pxnow=px.iloc[-1].to_dict(); rebal=[m for m in px.index if m>=pd.Timestamp('2021-05-31')]
variants={'외국인':FOR,'기관':INS,'합산':COMB}
RET={k:[] for k in variants}; EW=[]; CW=[]; IC={k:[] for k in variants}; prev={k:{} for k in variants}
for i in range(len(rebal)-1):
    a,b=rebal[i],rebal[i+1]
    fdt=[d for d in FOR.index if d<=a]
    if not fdt: continue
    fd=fdt[-1]; hist=px.loc[:a]
    u=[c for c in px.columns if c in mc and pd.notna(mc[c]) and pd.notna(px.loc[a,c]) and pd.notna(px.loc[b,c]) and pxnow.get(c)]
    u=sorted(u,key=lambda x:-mc[x])[:200]
    if len(u)<50: continue
    fwd={c:float(px.loc[b,c]/px.loc[a,c]-1) for c in u}
    EW.append(np.mean([fwd[c] for c in u]))
    mct={c:mc[c]*(px.loc[a,c]/pxnow[c]) for c in u}; ws=sum(mct.values()); CW.append(sum(mct[c]/ws*fwd[c] for c in u))
    for k,P in variants.items():
        if fd not in P.index: RET[k].append(np.nan); continue
        row=P.loc[fd]
        sig=pd.Series({c:(row.get(c,np.nan)/mct[c]) for c in u if pd.notna(row.get(c,np.nan)) and mct[c]>0}).dropna()
        if len(sig)<30: RET[k].append(np.nan); continue
        rr=pd.Series({c:fwd[c] for c in sig.index})
        IC[k].append(sig.rank().corr(rr.rank()))
        picks=sig.sort_values(ascending=False).head(N).index.tolist()
        w={c:1/len(picks) for c in picks}; r=sum(w[c]*fwd[c] for c in picks)
        to=sum(abs(w.get(c,0)-prev[k].get(c,0)) for c in set(w)|set(prev[k]))/2
        RET[k].append(r-to*COST); prev[k]=w
mEW=metrics(EW); mMKT=metrics(CW)
print('='*86); print('v4.3 KOSPI 수급팩터 1회 판정 (사전등록 동결 2026-06-14, %d개월)'%mEW['n']); print('='*86)
print('base: EW CAGR %.1f%%·MDD %.1f%% | MKT(CW) CAGR %.1f%%·Sharpe %.2f·MDD %.1f%%'%(mEW['CAGR'],mEW['MDD'],mMKT['CAGR'],mMKT['Sharpe'],mMKT['MDD']))
print('-'*86)
print('%-8s%8s%8s%8s%9s%9s%8s%9s  %s'%('변형','CAGR%','Sharpe','MDD%','IR_EW','αMKT%p','IR_MKT','IC','판정'))
res={}
for k in variants:
    m=metrics(RET[k]); rl=[x for x in RET[k] if x==x]; el=[EW[j] for j,x in enumerate(RET[k]) if x==x]; cl=[CW[j] for j,x in enumerate(RET[k]) if x==x]
    ire=ir(rl,el); irm=ir(rl,cl); alpha=m['CAGR']-metrics(cl)['CAGR']; icm=np.nanmean(IC[k]) if IC[k] else np.nan
    g1=(m['CAGR']>=metrics(el)['CAGR']) and (ire>=0); g2=(alpha>=3.0); g3=(irm>=0.30) and (m['Sharpe']>=metrics(cl)['Sharpe']-0.01); g4=(m['MDD']>=metrics(cl)['MDD'])
    PASS=g1 and g2 and g3 and g4; res[k]=PASS
    print('%-8s%8.1f%8.2f%8.1f%9.2f%+9.1f%8.2f%9.3f  %s [%s%s%s%s]'%(k,m['CAGR'],m['Sharpe'],m['MDD'],ire,alpha,irm,icm,
        '✅PASS' if PASS else '❌FAIL','①' if g1 else '·','②' if g2 else '·','③' if g3 else '·','④' if g4 else '·'))
print('-'*86)
anypass=any(res.values())
print('종합: %s'%('✅ PASS 변형 있음 → KOSPI 후보 팩터(조건부, 생존편향 재확인 필요)' if anypass else '❌ 전 변형 FAIL → 포트효과뿐, 종목선정 알파 아님'))
print('⚠️ 생존편향: 현 구성종목 패널(상폐 미포함). PASS는 상향편의 가능 → fetch_kospi_daily_panel.py(PC)로 PIT 재확인. FAIL이면 결론 견고.')
