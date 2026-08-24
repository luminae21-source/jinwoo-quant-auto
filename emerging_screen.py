#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""emerging_screen.py — 신규 부상 종목 스크린 (18 고정 탈피, 매월 1회).
현 보유 밖에서 ① 모멘텀-퀄리티 신규 리더(Q→Mom 상위) ② 밸류-퀄리티 신규(크래시보험·밸류업 후보)를 surfacing.
fixed-18은 지나간 리더 → 새 리더(AI전력기기·전자부품)·새 가치(밸류업 저평가)를 상시 발굴.
⚠️ 발굴 보조, 매수신호 아님. PIT 검증 + 진우 thesis 통과분만. 자립, FDR 불필요.
실행: python emerging_screen.py   |  입력: kospi_monthly_prices.csv, liquidity_sector.csv, fundamentals_pit.csv, book_equity.csv
      현 보유는 v37_2_scores_latest.csv(코드)에서 자동, 없으면 내장 18.
"""
import sys
from datetime import datetime
from pathlib import Path
import numpy as np, pandas as pd
BASE=Path(__file__).parent.resolve()
HOLD_FALLBACK={'003230','034020','005940','095340','196170','012450','042700','000660','028260','005930','035420','090430','033780','105560','006400','000270','035720','079550'}
TOP_UNIV=200; SHOW=15

def rd(n,**k): return pd.read_csv(BASE/n, encoding='utf-8-sig', **k)
def load_px(f):
    d=rd(f); d=d.rename(columns={d.columns[0]:'Date'}); d['Date']=pd.to_datetime(d['Date']); d=d.set_index('Date').sort_index()
    d.columns=[str(c).zfill(6) for c in d.columns]; d=d.apply(pd.to_numeric,errors='coerce'); return d[[c for c in d.columns if d[c].notna().sum()>=13]]
def z(s):
    s=s.astype(float); m,sd=s.mean(),s.std(ddof=0); return (s-m).clip(-3*sd,3*sd)/sd if sd else s*0
def load_fund():
    f=rd('fundamentals_pit.csv',dtype={'code':str}); f['code']=f['code'].str.zfill(6)
    be=rd('book_equity.csv',dtype={'code':str}); be['code']=be['code'].str.zfill(6)
    f=f.merge(be,on=['code','fiscal_year'],how='left'); f['book']=f['book_equity'].fillna(f['equity'])
    f['gp']=f['revenue']-f['cogs']; f['avail']=pd.to_datetime((f['fiscal_year']+1).astype(str)+'-04-01')
    f=f.sort_values(['code','fiscal_year']); f['assets_prev']=f.groupby('code')['assets'].shift(1); return f
def frame(codes,fa,mc,pnow,pt):
    rows={}
    for c in codes:
        if c not in fa.index: continue
        r=fa.loc[c]; sh,pn,p=mc.get(c),pnow.get(c),pt.get(c)
        if not sh or not pn or pn<=0 or not p or p<=0: continue
        m=sh*(p/pn); a=r['assets']
        if m<=0 or not a or a<=0: continue
        ni,eq,cfo=r['net_income'],r['equity'],r['cfo']
        rows[c]={'mcap_t':m,'EP':ni/m if pd.notna(ni) else np.nan,'BM':r['book']/m if pd.notna(r['book']) else np.nan,
                 'GPA':r['gp']/a if pd.notna(r['gp']) else np.nan,'ROE':ni/eq if (pd.notna(ni) and eq and eq>0) else np.nan,
                 'ACC':-((ni-cfo)/a) if (pd.notna(ni) and pd.notna(cfo)) else np.nan,
                 'AG':-((a-r['assets_prev'])/r['assets_prev']) if (pd.notna(r['assets_prev']) and r['assets_prev']>0) else np.nan}
    return pd.DataFrame(rows).T if rows else None

def holdings():
    f=BASE/'v37_2_scores_latest.csv'
    if f.exists():
        try:
            d=pd.read_csv(f,encoding='utf-8-sig'); return set(d['코드'].astype(str).str.zfill(6))
        except Exception: pass
    return HOLD_FALLBACK

def run():
    px=load_px('kospi_monthly_prices.csv'); fund=load_fund()
    liq=rd('liquidity_sector.csv',dtype={'code':str}); liq['code']=liq['code'].str.zfill(6)
    mc=dict(zip(liq['code'],pd.to_numeric(liq['mcap'],errors='coerce'))); nm=dict(zip(liq['code'],liq['name'])); sec=dict(zip(liq['code'],liq['sector']))
    HOLD=holdings()
    d0=px.index[-1]; fa=fund[fund['avail']<=d0].sort_values('fiscal_year').groupby('code').tail(1).set_index('code')
    hist=px.loc[:d0]; pnow=px.iloc[-1].to_dict()
    valid=[c for c in px.columns if hist[c].notna().sum()>=13 and pd.notna(px.loc[d0,c]) and c in mc]
    ff=frame(valid,fa,mc,pnow,px.loc[d0].to_dict())
    u=ff['mcap_t'].sort_values(ascending=False).head(TOP_UNIV).index.tolist(); ff=ff.loc[u]
    ff['MOM']=pd.Series({c:(hist[c].dropna().iloc[-2]/hist[c].dropna().iloc[-13]-1) for c in u if hist[c].notna().sum()>=13})
    ff['ret12']=pd.Series({c:(hist[c].dropna().iloc[-1]/hist[c].dropna().iloc[-13]-1) for c in u if hist[c].notna().sum()>=13})
    V=(z(ff['EP'])+z(ff['BM']))/2; Q=(z(ff['GPA'])+z(ff['ROE'])+z(ff['ACC'])+z(ff['AG']))/4; M=z(ff['MOM'])
    qm=M.copy(); qm[Q<Q.quantile(0.5)]=np.nan; vqs=(z(V)+z(Q))/2
    def pct(s,c): s=s.dropna(); return round(float((s<s[c]).mean()*100)) if c in s.index else None
    print('='*94); print('신규 부상 종목 스크린 (기준 %s · top-%d · 현보유 %d종 제외)'%(d0.date(),TOP_UNIV,len(HOLD&set(u)))); print('='*94)
    rows=[]
    print('[① 모멘텀-퀄리티 신규 리더]')
    print('%-15s%-20s%6s%6s%6s%8s'%('종목','섹터','Q%','모멘%','밸류%','12M'))
    for c in [x for x in qm.dropna().sort_values(ascending=False).index if x not in HOLD][:SHOW]:
        r=ff.loc[c,'ret12']*100 if ff.loc[c,'ret12']==ff.loc[c,'ret12'] else float('nan')
        print('%-15s%-20s%6s%6s%6s%7.0f%%'%(nm.get(c,c)[:13],str(sec.get(c,''))[:18],pct(Q,c),pct(M,c),pct(V,c),r))
        rows.append({'group':'MomQual','code':c,'name':nm.get(c,c),'Q':pct(Q,c),'Mom':pct(M,c),'Val':pct(V,c),'ret12':round(r,0)})
    print('\n[② 밸류-퀄리티 신규 (크래시보험·밸류업 후보)]')
    for c in [x for x in vqs.dropna().sort_values(ascending=False).index if x not in HOLD][:SHOW]:
        print('  %-14s %-18s Q%s 밸류%s 모멘%s'%(nm.get(c,c)[:12],str(sec.get(c,''))[:16],pct(Q,c),pct(V,c),pct(M,c)))
        rows.append({'group':'ValQual','code':c,'name':nm.get(c,c),'Q':pct(Q,c),'Mom':pct(M,c),'Val':pct(V,c),'ret12':None})
    out=BASE/('emerging_candidates_%s.csv'%datetime.now().strftime('%Y%m'))
    pd.DataFrame(rows).to_csv(out,index=False,encoding='utf-8-sig')
    print('\n저장: %s  (발굴 보조 — PIT검증+thesis 통과분만, 매수신호 아님)'%out.name)
if __name__=='__main__':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass
    run()
