#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""trackw_exit_rules.py — Track W(재량 테마) 청산·진입 규칙 (O'Neil/Minervini 원문 근거).
근거(원문 검증, evidence_base §4·§6): O'Neil "cut losses at 8%" + Minervini "7 to 8 percent",
  SEPA Trend Template(추세) + 실적·매출·마진, pyramid into winners(자본보존 우선).
production·guardrail 무수정 — 별도 규칙 모듈. ⚠️ 매수/매도신호 아님, 진우 판단 보조.
사용: from trackw_exit_rules import check_exit, trend_template_ok
      python trackw_exit_rules.py --selftest"""
import sys, argparse
import numpy as np, pandas as pd

HARD_STOP=-0.08          # O'Neil/Minervini 무조건 손절
HARD_STOP_TIGHT=-0.055   # 시황 악화 시(Minervini)
TRAIL_FROM_HIGH=-0.15    # 큰 수익 후 고점 대비 트레일
TRAIL_ARM_GAIN=0.20      # +20% 이상부터 트레일 작동(O'Neil 승자 키움)

def check_exit(entry, current, high_since_entry=None, thesis_invalidated=False, tough_market=False):
    """포지션 1개 청산 판정 → (action, reason). 우선순위: thesis > hard stop > trail."""
    if high_since_entry is None: high_since_entry=max(entry,current)
    ret=current/entry-1; from_high=current/high_since_entry-1; gain_peak=high_since_entry/entry-1
    stop=HARD_STOP_TIGHT if tough_market else HARD_STOP
    if thesis_invalidated:
        return 'THESIS_EXIT', '논거 무효화 → 즉시 청산(사전기록 조건)'
    if ret<=stop:
        return 'STOP_LOSS', '진입가 대비 %.1f%% ≤ %.0f%% 손절(O\'Neil/Minervini)'%(ret*100,stop*100)
    if gain_peak>=TRAIL_ARM_GAIN and from_high<=TRAIL_FROM_HIGH:
        return 'TRAIL_EXIT', '고점(+%.0f%%) 대비 %.1f%% 하락 → 트레일 청산'%(gain_peak*100,from_high*100)
    return 'HOLD', '보유(손절선 위·트레일 미발동)'

def trend_template_ok(monthly_prices, sma_n=10):
    """SEPA Trend Template(간이): 현재가 > N개월 SMA AND SMA 상승추세. (월봉 근사)"""
    s=pd.Series(monthly_prices).dropna()
    if len(s)<sma_n+2: return False, '데이터부족'
    sma=s.rolling(sma_n).mean()
    up = s.iloc[-1]>sma.iloc[-1] and sma.iloc[-1]>sma.iloc[-3]
    return bool(up), ('추세적합(가격>SMA·SMA상승)' if up else '추세부적합')

def _selftest():
    ok=0
    a,r=check_exit(100,91); assert a=='STOP_LOSS'; ok+=1
    a,r=check_exit(100,95); assert a=='HOLD'; ok+=1
    a,r=check_exit(100,94.5,tough_market=True); assert a=='STOP_LOSS'; ok+=1   # -5.5% 타이트
    a,r=check_exit(100,125,high_since_entry=150); assert a=='TRAIL_EXIT'; ok+=1 # +50%고점→-17%
    a,r=check_exit(100,130,high_since_entry=132); assert a=='HOLD'; ok+=1        # 고점근처
    a,r=check_exit(100,200,thesis_invalidated=True); assert a=='THESIS_EXIT'; ok+=1
    up,_=trend_template_ok(list(np.linspace(100,140,14))); assert up; ok+=1
    dn,_=trend_template_ok(list(np.linspace(140,100,14))); assert not dn; ok+=1
    print('[OK] trackw_exit_rules self-test 통과 (%d checks)'%ok)
    print('규칙: 손절 -8%(시황악화 -5.5%) · 트레일 +20%후 고점-15% · 논거무효 즉시 · 진입 Trend Template')
    return True

if __name__=='__main__':
    try: sys.stdout.reconfigure(encoding='utf-8')
    except: pass
    ap=argparse.ArgumentParser(); ap.add_argument('--selftest',action='store_true'); a=ap.parse_args()
    if a.selftest: _selftest()
    else: print(__doc__); print('\n--selftest로 규칙 검증. import해서 check_exit()/trend_template_ok() 사용.')
