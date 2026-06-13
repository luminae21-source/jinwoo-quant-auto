#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""maury_kospi_test.py — Maury "수급=확인신호" KOSPI 검증 (VQ×flow 상호작용).
가설(Maury 2017): 수급/소유 집중을 value+quality(QARP) 위에 얹으면 (조건부) 개선.
방법: KOSPI top-200, VQ 상위 중 수급(외국인+기관 3M누적/시총) 高/低 비교 + IC + EW벤치.
판정: VQ_hiFlow가 VQ_loFlow·VQ단독보다 유의↑ AND flow IC>0 이면 한국서 성립.
데이터: kospi_flow_monthly.csv(= fetch_kospi_flow_pykrx.py로 PC 생성) + 로컬 가격·재무·시총.
실행: python maury_kospi_test.py        (데이터 있으면 실검증)
      python maury_kospi_test.py --selftest   (합성 신호주입 = 엔진 양성대조)
⚠️ 투자자문 아님."""
import sys, argparse
from pathlib import Path
import numpy as np, pandas as pd
BASE=Path(__file__).parent.resolve(); COST=0.0035

def rd(n,**k): return pd.read_csv(BASE/n,encoding='utf-8-sig',**k)
def z(s): s=s.astype(float); sd=s.std(ddof=0); return (s-s.mean())/sd if sd else s*0
def met(a,bench):
    a=np.asarray([x for x in a if x==x],float)
    if len(a)==0: return 0,0,0
    cum=np.prod(1+a)-1; ann=(1+cum)**(12/len(a))-1; vol=a.std()*np.sqrt(12)
    b=np.asarray(bench[:len(a)],float); ac=a-b
    return ann*100,(ann/vol if vol else 0),((ac.mean()*12)/(ac.std()*np.sqrt(12)) if ac.std() else 0)

def core_test(px,fund,mc,flp, label='KOSPI 실데이터'):
    pxnow=px.iloc[-1].to_dict(); rebal=[m for m in px.index if m>=pd.Timestamp('2021-05-31')]
    S={'VQ':[],'Flow':[],'VQ_hiFlow':[],'VQ_loFlow':[]}; EW=[]; prev={k:{} for k in S}; ics=[]
    for i in range(len(rebal)-1):
        a,b=rebal[i],rebal[i+1]
        fa=fund[fund['avail']<=a].sort_values('fiscal_year').groupby('code').tail(1).set_index('code')
        if fa.empty: continue
        fdt=[d for d in flp.index if d<=a]
        if not fdt: continue
        frow=flp.loc[fdt[-1]]; hist=px.loc[:a]
        cand=[c for c in px.columns if c in fa.index and c in mc and pd.notna(mc[c]) and hist[c].notna().sum()>=13 and pd.notna(px.loc[a,c]) and pd.notna(px.loc[b,c]) and pxnow.get(c)]
        cand=sorted(cand,key=lambda x:-mc[x])[:200]
        if len(cand)<30: continue
        rows={}
        for c in cand:
            r=fa.loc[c]; mct=mc[c]*(px.loc[a,c]/pxnow[c]); ass=r['assets']
            if not ass or ass<=0 or mct<=0: continue
            ni,eq,cfo=r['net_income'],r['equity'],r['cfo']
            rows[c]=dict(EP=ni/mct if pd.notna(ni) else np.nan,BM=r['book']/mct if pd.notna(r['book']) else np.nan,
                GPA=r['gp']/ass if pd.notna(r['gp']) else np.nan,ROE=ni/eq if (pd.notna(ni) and eq and eq>0) else np.nan,
                ACC=-((ni-cfo)/ass) if (pd.notna(ni) and pd.notna(cfo)) else np.nan,
                AG=-((ass-r['assets_prev'])/r['assets_prev']) if (pd.notna(r['assets_prev']) and r['assets_prev']>0) else np.nan,
                flow=frow.get(c,np.nan)/mct if pd.notna(frow.get(c,np.nan)) else np.nan)
        fr=pd.DataFrame(rows).T
        if len(fr)<30: continue
        V=(z(fr['EP'])+z(fr['BM']))/2; Q=(z(fr['GPA'])+z(fr['ROE'])+z(fr['ACC'])+z(fr['AG']))/4; VQ=(z(V)+z(Q))/2; FL=z(fr['flow'])
        fwd={c:float(px.loc[b,c]/px.loc[a,c]-1) for c in fr.index}; EW.append(np.mean([fwd[c] for c in fr.index]))
        f_v=FL.dropna(); r_v=pd.Series({c:fwd[c] for c in f_v.index})
        if len(f_v)>=10 and f_v.std()>0: ics.append(np.corrcoef(f_v,r_v)[0,1])
        vqtop=VQ.dropna().sort_values(ascending=False).head(max(20,len(VQ.dropna())//2)).index
        flsub=FL.reindex(vqtop).dropna()
        sl={'VQ':VQ.dropna().sort_values(ascending=False).head(15).index.tolist(),
            'Flow':FL.dropna().sort_values(ascending=False).head(15).index.tolist(),
            'VQ_hiFlow':flsub.sort_values(ascending=False).head(15).index.tolist(),
            'VQ_loFlow':flsub.sort_values().head(15).index.tolist()}
        for k,p in sl.items():
            if not p: S[k].append(np.nan); continue
            w={c:1/len(p) for c in p}; r=sum(w[c]*fwd[c] for c in p)
            to=sum(abs(w.get(c,0)-prev[k].get(c,0)) for c in set(w)|set(prev[k]))/2
            S[k].append(r-to*COST); prev[k]=w
    n=len([x for x in S['VQ'] if x==x])
    print('='*74); print('Maury KOSPI 검증 — 수급×VQ 상호작용  (%s, %d개월)'%(label,n)); print('='*74)
    print('%-12s%9s%8s%8s'%('슬리브','CAGR%','Sharpe','IR_EW')); print('-'*74)
    for k in ['VQ','Flow','VQ_hiFlow','VQ_loFlow']:
        c,s,ir=met(S[k],EW); print('%-12s%9.1f%8.2f%8.2f'%(k,c,s,ir))
    c,s,_=met(EW,EW); print('%-12s%9.1f%8.2f%8s'%('KOSPI EW',c,s,'–'))
    hi=met(S['VQ_hiFlow'],EW)[0]; lo=met(S['VQ_loFlow'],EW)[0]; vq=met(S['VQ'],EW)[0]
    ic=np.nanmean(ics) if ics else float('nan')
    print('-'*74)
    print('flow IC(평균 %d월) = %.3f  | VQ_hiFlow %.1f vs VQ_loFlow %.1f (차 %+.1f%%p) vs VQ단독 %.1f'%(len(ics),ic,hi,lo,hi-lo,vq))
    ok = (ic>0.02) and (hi-lo>2.0) and (hi>=vq-0.5)
    print('판정: %s'%('✅ Maury 성립(수급 확인신호 유효)' if ok else '❌ 미성립/미확인 → 채택 안 함'))
    return ok

def selftest():
    # 합성: flow가 익월수익을 예측(IC↑) → hiFlow>loFlow 검출되는지 양성대조
    rng=np.random.default_rng(3); n=60; codes=['%06d'%k for k in range(120)]
    idx=pd.date_range('2021-05-31',periods=n,freq='ME')
    # 가격: flow신호 + 노이즈. flow_t가 r_{t+1}을 끌어올림
    flow=pd.DataFrame(rng.normal(0,1,(n,120)),index=idx,columns=codes)
    ret=0.04*flow.shift(1).fillna(0)+rng.normal(0,0.06,(n,120))  # flow→다음달 수익(신호 주입)
    px=(1+ret).cumprod()*1000
    mc={c:1e12 for c in codes}
    # 펀더멘털(VQ가 무작위라 flow효과 격리)
    fund=pd.DataFrame({'code':codes*2,'fiscal_year':[2020]*120+[2021]*120})
    for col in ['revenue','cogs','net_income','assets','equity','cfo']:
        fund[col]=rng.uniform(1e10,1e11,240)
    fund['book']=fund['equity']; fund['gp']=fund['revenue']-fund['cogs']
    fund['avail']=pd.to_datetime((fund['fiscal_year']+1).astype(str)+'-04-01')
    fund=fund.sort_values(['code','fiscal_year']); fund['assets_prev']=fund.groupby('code')['assets'].shift(1)
    flp=(flow*1e10)  # 수급=flow×시총규모
    ok=core_test(px,fund,mc,flp,label='SELFTEST(합성 신호주입)')
    print('\n[%s] 합성 신호 주입 시 Maury 엔진이 hiFlow>loFlow를 검출 → 실데이터 FAIL은 진짜 무신호 의미'%('OK' if ok else '점검필요'))
    return ok

def main():
    ap=argparse.ArgumentParser(); ap.add_argument('--selftest',action='store_true'); a=ap.parse_args()
    if a.selftest: sys.exit(0 if selftest() else 1)
    fpath=BASE/'kospi_flow_monthly.csv'
    if not fpath.exists():
        print('⛔ kospi_flow_monthly.csv 없음 → 먼저 PC에서:\n   pip install pykrx pandas\n   python fetch_kospi_flow_pykrx.py --top 200 --start 2019-01-02\n그 후 이 스크립트 재실행. (지금은 --selftest로 엔진만 검증 가능)')
        return
    def lpx(f):
        d=rd(f); d=d.rename(columns={d.columns[0]:'Date'}); d['Date']=pd.to_datetime(d['Date']); d=d.set_index('Date').sort_index()
        d.columns=[str(c).zfill(6) for c in d.columns]; d=d.apply(pd.to_numeric,errors='coerce'); return d[[c for c in d.columns if d[c].notna().sum()>=13]]
    px=lpx('kospi_monthly_prices.csv')
    F=rd('fundamentals_pit.csv',dtype={'code':str}); F['code']=F['code'].str.zfill(6)
    be=rd('book_equity.csv',dtype={'code':str}); be['code']=be['code'].str.zfill(6)
    F=F.merge(be,on=['code','fiscal_year'],how='left'); F['book']=F['book_equity'].fillna(F['equity'])
    F['gp']=F['revenue']-F['cogs']; F['avail']=pd.to_datetime((F['fiscal_year']+1).astype(str)+'-04-01')
    F=F.sort_values(['code','fiscal_year']); F['assets_prev']=F.groupby('code')['assets'].shift(1)
    liq=rd('liquidity_sector.csv',dtype={'code':str}); liq['code']=liq['code'].str.zfill(6); mc=dict(zip(liq['code'],pd.to_numeric(liq['mcap'],errors='coerce')))
    fl=rd('kospi_flow_monthly.csv',dtype={'code':str}); fl['code']=fl['code'].str.zfill(6); fl['date']=pd.to_datetime(fl['date'])
    fl['net']=fl['foreign_net'].fillna(0)+fl['inst_net'].fillna(0)
    flp=fl.pivot_table(index='date',columns='code',values='net',aggfunc='sum').sort_index().rolling(3).sum()
    core_test(px,F,mc,flp)

if __name__=='__main__':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass
    main()
