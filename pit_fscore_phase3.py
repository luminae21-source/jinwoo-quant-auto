#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""영역4 Phase3 — 시계열(PIT) Piotroski F-score로 lookahead 제거 검증 (자립, FDR 불필요).
질문: v3.7.2의 정적 F-score(오늘값을 과거 전체에 적용 = lookahead)를 PIT로 바꾸면 알파가 살아남나?
방법: fundamentals_pit.csv로 9요소 F-score를 회계연도별 산출(익년 4월 가용) →
      (A) PIT-F: 매 시점 가용 F로 선택  vs  (B) static-F: 최신값 전구간 적용(lookahead).
      두 백테스트 IR/CAGR 차이 = 정적 F의 lookahead 거품.
실행: python pit_fscore_phase3.py   |  입력: fundamentals_pit.csv, kospi_monthly_prices.csv, liquidity_sector.csv
"""
import numpy as np, pandas as pd
from pathlib import Path
BASE=Path(__file__).parent.resolve()
COST=0.00235; TOP=20

def rd(n,**k): return pd.read_csv(BASE/n, encoding='utf-8-sig', **k)
def load_px(f):
    d=rd(f); d=d.rename(columns={d.columns[0]:'Date'}); d['Date']=pd.to_datetime(d['Date'])
    d=d.set_index('Date').sort_index(); d.columns=[str(c).zfill(6) for c in d.columns]
    d=d.apply(pd.to_numeric,errors='coerce'); return d[[c for c in d.columns if d[c].notna().sum()>=13]]
def load_mcap():
    l=rd('liquidity_sector.csv',dtype={'code':str}); l['code']=l['code'].str.zfill(6)
    return dict(zip(l['code'],pd.to_numeric(l['mcap'],errors='coerce')))

F=rd('fundamentals_pit.csv',dtype={'code':str}); F['code']=F['code'].str.zfill(6); F=F.sort_values(['code','fiscal_year'])
g=F.groupby('code')
for c in ['net_income','assets','cfo','noncurrent_liab','current_assets','current_liab','revenue','cogs','issued_capital']:
    F[c+'_p']=g[c].shift(1)
def fscore(r):
    a,ap=r['assets'],r['assets_p']
    if not a or a<=0 or pd.isna(ap) or ap<=0: return np.nan
    roa=r['net_income']/a; roa_p=r['net_income_p']/ap if pd.notna(r['net_income_p']) else np.nan
    s=0
    s+=1 if roa>0 else 0
    s+=1 if (pd.notna(r['cfo']) and r['cfo']>0) else 0
    s+=1 if (pd.notna(roa_p) and roa>roa_p) else 0
    s+=1 if (pd.notna(r['cfo']) and r['cfo']>r['net_income']) else 0
    lev=r['noncurrent_liab']/a if pd.notna(r['noncurrent_liab']) else np.nan
    lev_p=r['noncurrent_liab_p']/ap if pd.notna(r['noncurrent_liab_p']) else np.nan
    s+=1 if (pd.notna(lev) and pd.notna(lev_p) and lev<lev_p) else 0
    cr=r['current_assets']/r['current_liab'] if (pd.notna(r['current_liab']) and r['current_liab']>0) else np.nan
    cr_p=r['current_assets_p']/r['current_liab_p'] if (pd.notna(r['current_liab_p']) and r['current_liab_p']>0) else np.nan
    s+=1 if (pd.notna(cr) and pd.notna(cr_p) and cr>cr_p) else 0
    s+=1 if (pd.notna(r['issued_capital_p']) and r['issued_capital']<=r['issued_capital_p']*1.001) else 0
    gm=(r['revenue']-r['cogs'])/r['revenue'] if (pd.notna(r['cogs']) and r['revenue']>0) else np.nan
    gm_p=(r['revenue_p']-r['cogs_p'])/r['revenue_p'] if (pd.notna(r['cogs_p']) and pd.notna(r['revenue_p']) and r['revenue_p']>0) else np.nan
    s+=1 if (pd.notna(gm) and pd.notna(gm_p) and gm>gm_p) else 0
    at=r['revenue']/a; at_p=r['revenue_p']/ap if pd.notna(r['revenue_p']) else np.nan
    s+=1 if (pd.notna(at_p) and at>at_p) else 0
    return s
F['Fpit']=F.apply(fscore,axis=1); F['avail']=pd.to_datetime((F['fiscal_year']+1).astype(str)+'-04-01')
latest=F.dropna(subset=['Fpit']).sort_values('fiscal_year').groupby('code').tail(1).set_index('code')['Fpit']

px=load_px('kospi_monthly_prices.csv'); mcN=load_mcap(); pxnow=px.iloc[-1].to_dict()
rebal=[m for m in px.index if m>=pd.Timestamp('2021-05-31')]
def f_asof(dt):
    av=F[(F['avail']<=dt)&F['Fpit'].notna()]
    return av.sort_values('fiscal_year').groupby('code').tail(1).set_index('code')['Fpit'] if len(av) else None
rets={'PIT_F':[],'static_F':[]}; CW=[]; prev={k:{} for k in rets}
for i in range(len(rebal)-1):
    a,b=rebal[i],rebal[i+1]; fp=f_asof(a)
    if fp is None: continue
    hist=px.loc[:a]; valid=[c for c in px.columns if hist[c].notna().sum()>=13 and pd.notna(px.loc[a,c]) and pd.notna(px.loc[b,c]) and c in mcN and pxnow.get(c)]
    mc_t={c:mcN[c]*(px.loc[a,c]/pxnow[c]) for c in valid}
    univ=sorted(mc_t,key=lambda x:-mc_t[x])[:200]
    fwd={c:float(px.loc[b,c]/px.loc[a,c]-1) for c in univ}; ws=sum(mc_t[c] for c in univ)
    CW.append(sum(mc_t[c]/ws*fwd[c] for c in univ))
    for key,src in [('PIT_F',fp),('static_F',latest)]:
        sc=pd.Series({c:src.get(c,np.nan) for c in univ}).dropna()
        if len(sc)<TOP: rets[key].append(np.nan); continue
        picks=sc.sort_values(ascending=False).head(TOP).index.tolist()
        w={c:1/len(picks) for c in picks}; r=sum(w[c]*fwd[c] for c in picks)
        to=sum(abs(w.get(c,0)-prev[key].get(c,0)) for c in set(w)|set(prev[key]))/2
        rets[key].append(r-to*COST); prev[key]=w
def met(a):
    a=np.asarray([x for x in a if x==x],float); cum=np.prod(1+a)-1; ann=(1+cum)**(12/len(a))-1; vol=a.std()*np.sqrt(12)
    cc=np.cumprod(1+a); pk=np.maximum.accumulate(cc); return ann*100,ann/vol,((cc-pk)/pk).min()*100
def ir(a):
    p=[(x,c) for x,c in zip(a,CW) if x==x]; ac=np.array([x-c for x,c in p]); return (ac.mean()*12)/(ac.std()*np.sqrt(12))
n=len([x for x in rets['PIT_F'] if x==x])
print('='*72); print('Phase3 — PIT F-score vs static F (lookahead) · top-200 고F %d종, %d개월'%(TOP,n)); print('='*72)
print('%-12s%9s%8s%9s%8s'%('구성','CAGR%','Sharpe','MDD%','IR')); print('-'*72)
for k in ['PIT_F','static_F']:
    c,s,m=met(rets[k]); print('%-12s%9.1f%8.2f%9.1f%8.2f'%(k,c,s,m,ir(rets[k])))
c,s,m=met(CW); print('%-12s%9.1f%8.2f%9.1f%8s'%('CW(벤치)',c,s,m,'–'))
print('-'*72)
dc=met(rets['static_F'])[0]-met(rets['PIT_F'])[0]
print('lookahead 거품 = static − PIT = %+.1f%%p CAGR, IR %+.2f → %s'%(dc, ir(rets['static_F'])-ir(rets['PIT_F']),
      '무시할 수준(F-score lookahead 거품 없음)' if abs(dc)<2 else '유의'))
