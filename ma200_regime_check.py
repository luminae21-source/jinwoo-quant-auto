#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""보유 18종목 MA200(월간=10개월 SMA) 방어상태 점검 (자립, 매월 1회 실행용).
RISK-ON = 현재가 > 10개월 SMA (보유) / RISK-OFF = 아래 (룰상 현금·관망).
실행: python ma200_regime_check.py  |  입력: kospi_monthly_prices.csv, kosdaq_monthly_prices.csv, liquidity_sector.csv
⚠️ 투자자문 아님. 기존 진우퀀트 regime_detector_v40과 별개의 단순 월간 트렌드 점검."""
import sys
import numpy as np, pandas as pd
from pathlib import Path
BASE = Path(__file__).parent.resolve()
SMA_N = 10   # 월간 10개월 SMA ~= 200일 이동평균 (Faber GTAA 컨벤션)

HOLD = [('삼양식품','003230'),('두산에너빌리티','034020'),('NH투자증권','005940'),('ISC','095340'),
        ('알테오젠','196170'),('한화에어로','012450'),('한미반도체','042700'),('SK하이닉스','000660'),
        ('삼성물산','028260'),('삼성전자','005930'),('NAVER','035420'),('아모레퍼시픽','090430'),
        ('KT&G','033780'),('KB금융','105560'),('삼성SDI','006400'),('기아','000270'),
        ('카카오','035720'),('LIG넥스원','079550')]

def load_px(f):
    d = pd.read_csv(BASE/f, encoding='utf-8-sig'); d = d.rename(columns={d.columns[0]:'Date'})
    d['Date'] = pd.to_datetime(d['Date']); d = d.set_index('Date').sort_index()
    d.columns = [str(c).zfill(6) for c in d.columns]; return d.apply(pd.to_numeric, errors='coerce')

pk = load_px('kospi_monthly_prices.csv'); pq = load_px('kosdaq_monthly_prices.csv')
px = pk.join(pq[[c for c in pq.columns if c not in pk.columns]], how='outer').sort_index()
asof = px.index[-1]
print('=' * 60)
print('MA200 방어상태 (월간 %d개월 SMA, 기준 %s)' % (SMA_N, asof.date()))
print('=' * 60)
print('%-14s%10s%10s%8s  %s' % ('종목', '현재가', 'SMA', '이격%', '상태'))
print('-' * 60)
on = 0; off = []
for nm, c in HOLD:
    s = px[c].dropna()
    if len(s) < SMA_N:
        print('%-14s 데이터부족' % nm); continue
    last = s.iloc[-1]; sma = s.iloc[-SMA_N:].mean(); gap = (last/sma - 1) * 100
    st = 'RISK-ON' if last > sma else 'RISK-OFF'
    on += last > sma
    if last <= sma: off.append(nm)
    print('%-14s%10.0f%10.0f%+7.1f%%  %s' % (nm, last, sma, gap, st))
liq = pd.read_csv(BASE/'liquidity_sector.csv', encoding='utf-8-sig', dtype={'code':str}); liq['code'] = liq['code'].str.zfill(6)
top = [c for c in liq.sort_values('mcap', ascending=False)['code'].head(200) if c in pk.columns]
sub = pk[top].dropna(how='all'); idx = (sub/sub.iloc[0]).mean(axis=1)
ist = 'RISK-ON' if idx.iloc[-1] > idx.iloc[-SMA_N:].mean() else 'RISK-OFF'
print('-' * 60)
print('시장(KOSPI top200 EW): %s (이격 %+.1f%%)' % (ist, (idx.iloc[-1]/idx.iloc[-SMA_N:].mean() - 1) * 100))
print('보유 RISK-ON %d/%d  |  RISK-OFF: %s' % (on, len([h for h in HOLD]), ', '.join(off) if off else '없음'))
print('\n주의: 이격이 +100% 같은 과열은 방어선(SMA)이 현재가보다 한참 아래 → 방어가 늦게 작동.')
