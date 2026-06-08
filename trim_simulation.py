#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""반도체 4종목 트림 시나리오 — 집중도·실현위험·조정 스트레스테스트 (자립).
트림군: SK하이닉스·한미반도체·ISC·삼성SDI. 베이스=EW 18종목.
⚠️ 실현 수익은 사후편향(이 4종목이 과거 급등) → '위험·집중도·스트레스' 중심 해석."""
import numpy as np, pandas as pd
from pathlib import Path
BASE = Path(__file__).parent.resolve()

HOLD = {'삼양식품':'003230','두산에너빌리티':'034020','NH투자증권':'005940','ISC':'095340',
        '알테오젠':'196170','한화에어로':'012450','한미반도체':'042700','SK하이닉스':'000660',
        '삼성물산':'028260','삼성전자':'005930','NAVER':'035420','아모레퍼시픽':'090430',
        'KT&G':'033780','KB금융':'105560','삼성SDI':'006400','기아':'000270',
        '카카오':'035720','LIG넥스원':'079550'}
SECTOR = {'SK하이닉스':'반도체','한미반도체':'반도체','ISC':'반도체','삼성전자':'반도체','삼성SDI':'2차전지',
          '두산에너빌리티':'원전','한화에어로':'방산','LIG넥스원':'방산','삼성물산':'상사','기아':'자동차'}
TRIM = ['SK하이닉스','한미반도체','ISC','삼성SDI']          # 사용자 지정 4종목
SEMI = ['SK하이닉스','한미반도체','ISC','삼성전자','삼성SDI']  # 반도체+2차전지 복합
REDISTRIB = ['기아','KT&G','삼성전자','NAVER','KB금융','NH투자증권','아모레퍼시픽','삼양식품']  # 우량·저평가 KEEP

def load_px(f):
    d=pd.read_csv(BASE/f,encoding='utf-8-sig'); d=d.rename(columns={d.columns[0]:'Date'}); d['Date']=pd.to_datetime(d['Date'])
    d=d.set_index('Date').sort_index(); d.columns=[str(c).zfill(6) for c in d.columns]; return d.apply(pd.to_numeric,errors='coerce')
pk=load_px('kospi_monthly_prices.csv'); pq=load_px('kosdaq_monthly_prices.csv')
px=pk.join(pq[[c for c in pq.columns if c not in pk.columns]],how='outer').sort_index()
names=list(HOLD); ret=px[[HOLD[n] for n in names]].pct_change().rename(columns={HOLD[n]:n for n in names})
ret=ret.loc['2021-06-30':]

def weights(scn):
    base=1/18; w={n:base for n in names}
    if scn=='Baseline': pass
    else:
        f={'Trim1/3':2/3,'Trim1/2':0.5,'Exit':0.0}[scn]; freed=0.0
        for n in TRIM: freed+=w[n]*(1-f); w[n]*=f
        add=freed/len(REDISTRIB)
        for n in REDISTRIB: w[n]+=add
    s=sum(w.values()); return {n:w[n]/s for n in names}

def stats(w):
    pr=(ret*pd.Series(w)).sum(axis=1).dropna()
    cum=(1+pr).prod()-1; ann=(1+cum)**(12/len(pr))-1; vol=pr.std()*np.sqrt(12)
    cc=(1+pr).cumprod(); mdd=((cc-cc.cummax())/cc.cummax()).min()
    return ann*100, vol*100, mdd*100

print('='*86); print('반도체 트림 시나리오 — 트림군: '+', '.join(TRIM)+'  (베이스 EW 18)'); print('='*86)
print('%-10s%12s%12s%12s%10s%10s%9s'%('시나리오','트림군비중','반도체복합','실현CAGR','변동성','실현MDD','현금'))
print('-'*86)
for scn in ['Baseline','Trim1/3','Trim1/2','Exit']:
    w=weights(scn); tg=sum(w[n] for n in TRIM); sm=sum(w[n] for n in SEMI)
    ann,vol,mdd=stats(w); cash=0.0
    print('%-10s%11.1f%%%11.1f%%%11.1f%%%9.1f%%%9.1f%%%8s'%(scn,tg*100,sm*100,ann,vol,mdd,'재투자'))
# Exit→현금 변형 (트림분을 현금으로)
def stats_cash(scn):
    base=1/18; w={n:base for n in names}; cash=0.0; f={'Trim1/2':0.5,'Exit':0.0}[scn]
    for n in TRIM: cash+=w[n]*(1-f); w[n]*=f
    pr=(ret*pd.Series(w)).sum(axis=1).dropna()  # 현금=0수익
    cum=(1+pr).prod()-1; ann=(1+cum)**(12/len(pr))-1; vol=pr.std()*np.sqrt(12)
    cc=(1+pr).cumprod(); mdd=((cc-cc.cummax())/cc.cummax()).min(); return ann*100,vol*100,mdd*100,cash*100,sum(w[n] for n in TRIM)*100
for scn in ['Trim1/2','Exit']:
    ann,vol,mdd,cash,tg=stats_cash(scn)
    print('%-10s%11.1f%%%12s%11.1f%%%9.1f%%%9.1f%%%8.0f%%'%(scn+'→현금',tg,'–',ann,vol,mdd,cash))
print('-'*86)
print('주의: 실현 CAGR은 사후편향(트림군이 과거 급등) → 위에서 *변동성·MDD·집중도*가 의사결정 핵심.')

# ===== 스트레스테스트: 트림군 조정 시 즉시 손익 =====
print('\n'+'='*86); print('스트레스테스트 — 반도체 트림군 조정 시 포트폴리오 즉시 손익'); print('='*86)
print('가정: 트림군(-shock%), 삼성전자(반semi, -shock/2), 그 외 0  [상관 단순화]')
print('%-12s%14s%14s%14s'%('시나리오','트림군 -30%','트림군 -40%','트림군 -50%'))
print('-'*86)
for scn in ['Baseline','Trim1/3','Trim1/2','Exit']:
    w=weights(scn); line=[]
    for sh in [0.30,0.40,0.50]:
        pl=-sum(w[n]*sh for n in TRIM)-w['삼성전자']*(sh/2)
        line.append('%6.1f%%'%(pl*100))
    print('%-12s%14s%14s%14s'%(scn,line[0],line[1],line[2]))
print('-'*86)
b=weights('Baseline'); e=weights('Exit')
def shock(w): return (-sum(w[n] for n in TRIM)*0.4 - w['삼성전자']*0.2)*100
print(f'읽기: 트림군 -40%% 충격 시 Baseline {shock(b):.1f}%% vs Exit {shock(e):.1f}%% 손실 → 차이가 트림 방어폭.')
