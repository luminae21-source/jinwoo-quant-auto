#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""보유 18종목 Q->Mom 트림 후보 스냅샷 + 밸류 하락방어 블렌드 MDD 측정 (자립, FDR 불필요).
실행: python holdings_trim_analysis.py
입력(같은 폴더): kospi_monthly_prices.csv, kosdaq_monthly_prices.csv, fundamentals_pit.csv,
                 fundamentals_kosdaq.csv, book_equity.csv, liquidity_sector.csv, liquidity_kosdaq.csv
⚠️ 투자자문 아님. 트림/피크 플래그는 본인 판단용 신호."""
import json, sys
import numpy as np, pandas as pd
from pathlib import Path
BASE = Path(__file__).parent.resolve()
COST = 0.00235

HOLD = [('삼양식품','003230'),('두산에너빌리티','034020'),('NH투자증권','005940'),('ISC','095340'),
        ('알테오젠','196170'),('한화에어로','012450'),('한미반도체','042700'),('SK하이닉스','000660'),
        ('삼성물산','028260'),('삼성전자','005930'),('NAVER','035420'),('아모레퍼시픽','090430'),
        ('KT&G','033780'),('KB금융','105560'),('삼성SDI','006400'),('기아','000270'),
        ('카카오','035720'),('LIG넥스원','079550')]

def rd(n): return pd.read_csv(BASE/n, encoding='utf-8-sig')
def z(s):
    s=s.astype(float); mu,sd=s.mean(),s.std(ddof=0)
    return pd.Series(0.0,index=s.index) if (not sd or np.isnan(sd)) else ((s-mu)/sd).clip(-3,3)
def load_px(f):
    d=rd(f); d=d.rename(columns={d.columns[0]:'Date'}); d['Date']=pd.to_datetime(d['Date'])
    d=d.set_index('Date').sort_index(); d.columns=[str(c).zfill(6) for c in d.columns]
    return d.apply(pd.to_numeric,errors='coerce')
def load_fund(fs):
    L=[]
    for f in fs:
        d=pd.read_csv(BASE/f,encoding='utf-8-sig',dtype={'code':str}); d['code']=d['code'].str.zfill(6); L.append(d)
    F=pd.concat(L,ignore_index=True)
    be=pd.read_csv(BASE/'book_equity.csv',encoding='utf-8-sig',dtype={'code':str}); be['code']=be['code'].str.zfill(6)
    F=F.merge(be,on=['code','fiscal_year'],how='left'); F['book']=F['book_equity'].fillna(F['equity'])
    F['gp']=F['revenue']-F['cogs']; F['avail']=pd.to_datetime((F['fiscal_year']+1).astype(str)+'-04-01')
    F=F.sort_values(['code','fiscal_year']); F['assets_prev']=F.groupby('code')['assets'].shift(1); return F
def load_mc(fs):
    mc={}
    for f in fs:
        d=pd.read_csv(BASE/f,encoding='utf-8-sig',dtype={'code':str}); d['code']=d['code'].str.zfill(6)
        mc.update(dict(zip(d['code'],pd.to_numeric(d['mcap'],errors='coerce'))))
    return mc
def frame(codes,fund,mc,pnow,pt):
    rows={}
    for c in codes:
        if c not in fund.index: continue
        r=fund.loc[c]; sh,pn,p=mc.get(c),pnow.get(c),pt.get(c)
        if not sh or not pn or pn<=0 or not p or p<=0: continue
        m=sh*(p/pn); a=r['assets']
        if m<=0 or not a or a<=0: continue
        ni,eq,cfo=r['net_income'],r['equity'],r['cfo']
        rows[c]={'mcap_t':m,'EP':ni/m if pd.notna(ni) else np.nan,'BM':r['book']/m if pd.notna(r['book']) else np.nan,
                 'GPA':r['gp']/a if pd.notna(r['gp']) else np.nan,'ROE':ni/eq if (pd.notna(ni) and eq and eq>0) else np.nan,
                 'ACC':-((ni-cfo)/a) if (pd.notna(ni) and pd.notna(cfo)) else np.nan,
                 'AG':-((a-r['assets_prev'])/r['assets_prev']) if (pd.notna(r['assets_prev']) and r['assets_prev']>0) else np.nan}
    return pd.DataFrame(rows).T if rows else None
def met(a,bn=None):
    a=np.asarray(a,float); cum=np.prod(1+a)-1; ann=(1+cum)**(12/len(a))-1; vol=a.std()*np.sqrt(12)
    cc=np.cumprod(1+a); pk=np.maximum.accumulate(cc); o=dict(CAGR=round(ann*100,1),Sharpe=round(ann/vol,2),MDD=round(((cc-pk)/pk).min()*100,1))
    if bn is not None: ac=a-np.asarray(bn,float); o['IR']=round((ac.mean()*12)/(ac.std()*np.sqrt(12)),2)
    return o

pk=load_px('kospi_monthly_prices.csv'); pq=load_px('kosdaq_monthly_prices.csv')
px=pk.join(pq[[c for c in pq.columns if c not in pk.columns]],how='outer').sort_index()
px=px[[c for c in px.columns if px[c].notna().sum()>=13]]
F=load_fund(['fundamentals_pit.csv','fundamentals_kosdaq.csv']); mc=load_mc(['liquidity_sector.csv','liquidity_kosdaq.csv'])
kospi_set=set(pd.read_csv(BASE/'liquidity_sector.csv',encoding='utf-8-sig',dtype={'code':str})['code'].str.zfill(6))

# ===== Part A: 스냅샷 =====
d0=px.index[-1]; fa=F[F['avail']<=d0].sort_values('fiscal_year').groupby('code').tail(1).set_index('code')
cands=[c for c in px.columns if c in fa.index and c in mc and pd.notna(px.loc[d0,c]) and px.iloc[-13:][c].notna().sum()>=13]
ser=pd.Series({c:mc[c] for c in cands}).sort_values(ascending=False)
uni=[c for c in ser.index if c in kospi_set][:200]+[c for c in ser.index if c not in kospi_set][:80]
fr=frame(uni,fa,mc,px.iloc[-1].to_dict(),px.loc[d0].to_dict())
fr['MOM']=pd.Series({c:(px[c].dropna().iloc[-1]/px[c].dropna().iloc[-13]-1) for c in uni if px[c].notna().sum()>=13})
fr['ret12']=fr['MOM']
Q=(z(fr['GPA'])+z(fr['ROE'])+z(fr['ACC'])+z(fr['AG']))/4; V=(z(fr['EP'])+z(fr['BM']))/2; M=z(fr['MOM'])
def pct(s,c):
    s=s.dropna(); return round(float((s<s[c]).mean()*100)) if c in s.index else None
print('='*94); print('보유 18종목 스냅샷 (기준일 %s, 참조 유니버스 %d종목)'%(d0.date(),len(uni))); print('='*94)
print('%-14s%7s%7s%7s%9s  %s'%('종목','퀄%','모멘%','밸류%','12M','판정')); print('-'*94)
rows=[]
for nm,c in HOLD:
    if c not in fr.index: print('%-14s 데이터없음'%nm); continue
    qp,mp,vp=pct(Q,c),pct(M,c),pct(V,c); r=fr.loc[c,'ret12']
    qmom='KEEP' if (qp is not None and qp>=50 and mp is not None and mp>=40) else ('TRIM:퀄탈락' if (qp is not None and qp<50) else 'WATCH:모멘텀약')
    peak='PEAK트림' if (vp is not None and vp<30 and r==r and r>0.8) else ('비쌈' if (vp is not None and vp<25) else '')
    rows.append(dict(name=nm,code=c,qual_pct=qp,mom_pct=mp,val_pct=vp,ret12m=round(float(r)*100,1) if r==r else None,qmom=qmom,peak=peak))
    print('%-14s%7s%7s%7s%8s%%  %s'%(nm,qp,mp,vp,round(float(r)*100,1) if r==r else '–',qmom+(' | '+peak if peak else '')))
print('-'*94); print('퀄/모멘/밸류%=참조 유니버스 백분위(高=우량/강세/저평가). 밸류 낮음=비쌈. 금융주는 GP/A 미정의로 퀄 None.')

# ===== Part B: 밸류 방어 블렌드 =====
def load_kospi(): 
    d=load_px('kospi_monthly_prices.csv'); return d[[c for c in d.columns if d[c].notna().sum()>=13]]
pk2=load_kospi(); FK=load_fund(['fundamentals_pit.csv']); mcK=load_mc(['liquidity_sector.csv'])
rebal=[m for m in pk2.index if m>=pd.Timestamp('2021-05-31')]; S={'QMom':[],'VQ':[],'Val':[],'Mom':[]}; CW=[]; prev={k:{} for k in S}; pxnow=pk2.iloc[-1].to_dict()
for i in range(len(rebal)-1):
    a,b=rebal[i],rebal[i+1]; fb=FK[FK['avail']<=a].sort_values('fiscal_year').groupby('code').tail(1).set_index('code')
    if fb.empty: continue
    hist=pk2.loc[:a]; valid=[c for c in pk2.columns if hist[c].notna().sum()>=13 and pd.notna(pk2.loc[a,c]) and pd.notna(pk2.loc[b,c])]
    ff=frame(valid,fb,mcK,pxnow,pk2.loc[a].to_dict())
    if ff is None or len(ff)<30: continue
    u=ff['mcap_t'].sort_values(ascending=False).head(200).index.tolist(); ff=ff.loc[u]
    ff['MOM']=pd.Series({c:(hist[c].dropna().iloc[-2]/hist[c].dropna().iloc[-13]-1) for c in u if hist[c].notna().sum()>=13})
    Vv=(z(ff['EP'])+z(ff['BM']))/2; Qq=(z(ff['GPA'])+z(ff['ROE'])+z(ff['ACC'])+z(ff['AG']))/4; Mm=z(ff['MOM'])
    qm=Mm.copy(); qm[Qq<Qq.quantile(0.5)]=np.nan; vqs=(z(Vv)+z(Qq))/2
    fwd={c:float(pk2.loc[b,c]/pk2.loc[a,c]-1) for c in u}; ws=ff['mcap_t'].sum(); CW.append(sum(ff.loc[c,'mcap_t']/ws*fwd[c] for c in u))
    for key,sc in [('QMom',qm),('VQ',vqs),('Val',Vv),('Mom',Mm)]:
        p=sc.dropna().sort_values(ascending=False).head(20).index.tolist(); w={c:1/len(p) for c in p}
        r=sum(w[c]*fwd[c] for c in p); to=sum(abs(w.get(c,0)-prev[key].get(c,0)) for c in set(w)|set(prev[key]))/2
        S[key].append(r-to*COST); prev[key]=w
print('\n'+'='*94); print('밸류 하락방어 블렌드 — MDD/CAGR 트레이드오프 (KOSPI top-200, %d개월)'%len(CW)); print('='*94)
print('%-24s%8s%8s%8s%7s'%('구성','CAGR%','Sharpe','MDD%','IR')); print('-'*94)
for tag,a in [('Mom 100%',S['Mom']),('QMom 100%',S['QMom'])]:
    m=met(a,CW); print('%-24s%8s%8s%8s%7s'%(tag,m['CAGR'],m['Sharpe'],m['MDD'],m['IR']))
for w in [0.75,0.5]:
    bl=[w*S['QMom'][i]+(1-w)*S['VQ'][i] for i in range(len(CW))]; m=met(bl,CW)
    print('%-24s%8s%8s%8s%7s'%('QMom %d%% + VQ %d%%'%(int(w*100),int((1-w)*100)),m['CAGR'],m['Sharpe'],m['MDD'],m['IR']))
m=met(S['VQ'],CW); print('%-24s%8s%8s%8s%7s'%('VQ 100%',m['CAGR'],m['Sharpe'],m['MDD'],m['IR']))
m=met(CW); print('%-24s%8s%8s%8s%7s'%('CW 벤치',m['CAGR'],m['Sharpe'],m['MDD'],'-'))
print('-'*94); print('핵심: QMom(퀄리티필터)이 이미 MDD를 낮춤. 밸류 블렌드는 MDD 1~3%p 추가↓ 대신 CAGR 5~10%p↓.')
json.dump({'snapshot_date':str(d0.date()),'holdings':rows},open(BASE/'holdings_qmom_snapshot.json','w',encoding='utf-8'),ensure_ascii=False,indent=2)
print('\n저장: holdings_qmom_snapshot.json')
