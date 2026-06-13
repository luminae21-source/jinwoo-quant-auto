#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""vq_insurance_sleeve.py — VQ(밸류+퀄리티) 크래시보험 슬리브 (정식 등록).
근거: QMJ(Asness외) "버블기 퀄리티 싸짐→이후 반등" + 진우 한국실증(모멘텀 크래시 시 VQ +9.6%p).
역할: 수익 엔진 아님. **모멘텀 크래시 대비 꼬리 보험.** 평시엔 보험료(언더퍼폼) 감수.
발동: 과열↑(반도체 MA200 이격↑·피크플래그↑)일수록 보험 비중↑ (gradecut RED와 연동).
실행: python vq_insurance_sleeve.py  | 입력: kospi_monthly_prices.csv, liquidity_sector.csv, fundamentals_pit.csv, book_equity.csv
⚠️ 투자자문 아님. 매수신호 아님 — 비중·집행은 진우 판단."""
import sys
from pathlib import Path
import numpy as np, pandas as pd
BASE=Path(__file__).parent.resolve()
SEMI={'반도체','2차전지'}; SMA_N=10; TOPN=15
ALLOC_BASE=15.0; ALLOC_MAX=30.0   # 보험 비중 % (base→max)

def rd(n,**k): return pd.read_csv(BASE/n,encoding='utf-8-sig',**k)
def load_px(f):
    d=rd(f); d=d.rename(columns={d.columns[0]:'Date'}); d['Date']=pd.to_datetime(d['Date']); d=d.set_index('Date').sort_index()
    d.columns=[str(c).zfill(6) for c in d.columns]; d=d.apply(pd.to_numeric,errors='coerce'); return d[[c for c in d.columns if d[c].notna().sum()>=13]]
def z(s): s=s.astype(float); sd=s.std(ddof=0); return (s-s.mean())/sd if sd else s*0
def load_fund():
    f=rd('fundamentals_pit.csv',dtype={'code':str}); f['code']=f['code'].str.zfill(6)
    be=rd('book_equity.csv',dtype={'code':str}); be['code']=be['code'].str.zfill(6)
    f=f.merge(be,on=['code','fiscal_year'],how='left'); f['book']=f['book_equity'].fillna(f['equity'])
    f['gp']=f['revenue']-f['cogs']; f['avail']=pd.to_datetime((f['fiscal_year']+1).astype(str)+'-04-01')
    f=f.sort_values(['code','fiscal_year']); f['assets_prev']=f.groupby('code')['assets'].shift(1); return f

def run():
    px=load_px('kospi_monthly_prices.csv'); fund=load_fund()
    liq=rd('liquidity_sector.csv',dtype={'code':str}); liq['code']=liq['code'].str.zfill(6)
    mc=dict(zip(liq['code'],pd.to_numeric(liq['mcap'],errors='coerce'))); nm=dict(zip(liq['code'],liq['name']))
    # 산업: v37_2 점수에서(현 보유 산업 라벨), 없으면 liquidity sector
    sec={}
    sf=BASE/'v39_pead_scores_latest.csv'
    if sf.exists():
        d=rd('v39_pead_scores_latest.csv'); sec=dict(zip(d['코드'].astype(str).str.zfill(6),d['산업']))
    d0=px.index[-1]; fa=fund[fund['avail']<=d0].sort_values('fiscal_year').groupby('code').tail(1).set_index('code')
    hist=px.loc[:d0]; pxnow=px.iloc[-1].to_dict()
    valid=[c for c in px.columns if hist[c].notna().sum()>=SMA_N and pd.notna(px.loc[d0,c]) and c in mc and pxnow.get(c)]
    rows={}
    for c in valid:
        if c not in fa.index: continue
        r=fa.loc[c]; mct=mc[c]*(px.loc[d0,c]/pxnow[c]); a=r['assets']
        if not a or a<=0 or mct<=0: continue
        ni,eq,cfo=r['net_income'],r['equity'],r['cfo']
        rows[c]=dict(mct=mct, EP=ni/mct if pd.notna(ni) else np.nan, BM=r['book']/mct if pd.notna(r['book']) else np.nan,
                     GPA=r['gp']/a if pd.notna(r['gp']) else np.nan, ROE=ni/eq if (pd.notna(ni) and eq and eq>0) else np.nan,
                     ACC=-((ni-cfo)/a) if (pd.notna(ni) and pd.notna(cfo)) else np.nan,
                     AG=-((a-r['assets_prev'])/r['assets_prev']) if (pd.notna(r['assets_prev']) and r['assets_prev']>0) else np.nan)
    fr=pd.DataFrame(rows).T
    fr=fr.loc[fr['mct'].sort_values(ascending=False).head(200).index]   # top-200
    V=(z(fr['EP'])+z(fr['BM']))/2; Q=(z(fr['GPA'])+z(fr['ROE'])+z(fr['ACC'])+z(fr['AG']))/4; VQ=(z(V)+z(Q))/2
    picks=VQ.dropna().sort_values(ascending=False).head(TOPN).index.tolist()
    # 과열 게이지: 반도체복합 평균 MA200 이격
    def stretch(c):
        s=hist[c].dropna(); return (s.iloc[-1]/s.iloc[-SMA_N:].mean()-1) if len(s)>=SMA_N else np.nan
    semi_codes=[c for c in fr.index if sec.get(c) in SEMI]
    semi_gap=np.nanmean([stretch(c) for c in semi_codes])*100 if semi_codes else np.nan
    # 보험 비중: 과열 클수록↑ (이격 0~80% → base~max 선형)
    g=0 if np.isnan(semi_gap) else max(0,min(1,semi_gap/80))
    alloc=round(ALLOC_BASE+(ALLOC_MAX-ALLOC_BASE)*g,1)
    state='RED 보험↑' if g>=0.75 else ('YELLOW' if g>=0.4 else 'GREEN 보험↓')
    print('='*80); print('VQ 크래시보험 슬리브 (기준 %s)'%d0.date()); print('='*80)
    print('역할: 모멘텀 크래시 대비 꼬리보험(QMJ+한국실증). 수익엔진 아님 — 평시 언더퍼폼=보험료.')
    print('과열 게이지: 반도체복합 평균 MA200 이격 %.1f%% → 신호 %s'%(semi_gap,state))
    print('▶ 권장 보험 비중: %.1f%% (base %.0f%% ~ max %.0f%%, 과열 연동)'%(alloc,ALLOC_BASE,ALLOC_MAX))
    print('-'*80)
    print('VQ-top %d 보험 픽 (밸류+퀄리티 상위):'%TOPN)
    for c in picks:
        print('  %-14s 밸류z%+.2f 퀄z%+.2f VQ%+.2f'%(nm.get(c,c)[:12], V.get(c,np.nan), Q.get(c,np.nan), VQ.get(c,np.nan)))
    print('-'*80)
    print('운용규칙: 평시 base %.0f%% 유지(보험료) → 과열(RED) 시 %.0f%%까지 증액. 크래시 통과 후 정상화되면 축소.'%(ALLOC_BASE,ALLOC_MAX))
    pd.DataFrame({'code':picks,'name':[nm.get(c,c) for c in picks],'VQ':[round(VQ.get(c,np.nan),3) for c in picks]}).to_csv(BASE/'vq_insurance_latest.csv',index=False,encoding='utf-8-sig')
    print('저장: vq_insurance_latest.csv  (발굴 보조 — 집행은 진우 판단)')
if __name__=='__main__':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass
    run()
