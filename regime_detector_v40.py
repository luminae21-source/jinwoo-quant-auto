#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
진우퀀트 v4.0 영역 2 — 한국식 5요소 regime detector (MVP)
=========================================================
작성: 2026-06-03 / 짝 문서: 진우퀀트_v40_regime_detector_설계.md

프레임워크 출처: 손삼호·윤보현 (2019) "스마트베타 위험요인 결합 투자전략"
  KJFS 48(3), 257 — 5요소 결합으로 연수익 10.26%→20.69%, MDD -46%→-12.5%.
VKOSPI 비대칭: 이정환 외 (2023) 개념 — 급등엔 빠르게 위험회피, 하락엔 천천히 복귀.
  ⚠️ 결합 가중치·임계값·hysteresis는 본 구현(our implementation)이며 백테스트로 튜닝.

이 detector는 매매룰(진우퀀트_v37_2_매매룰.md)의 Layer 3 VKOSPI 익스포저 +
Layer 5 헤지를 '5요소 종합'으로 흡수·고도화한 상위 버전이다.

5요소 → 각자 risk score [-1(위험)~+1(안전)] → 가중 종합 → RISK_ON/NEUTRAL/RISK_OFF
  1. 지수추세  : KOSPI vs 60/120/200일 MA            (FDR)
  2. VKOSPI    : 수준 + 비대칭 급등 페널티             (KRX / 실현변동성 대체)
  3. 수급      : 외국인+기관 20일 순매수 누적          (pykrx; 없으면 None)
  4. 섹터집중  : picks의 top 섹터 비중 (HHI 대체)       (JINWOO 산업맵)
  5. 팩터ON/OFF: 전략 트레일링 초과수익 부호           (자체 백테스트; 없으면 None)

graceful degradation: None인 요소는 종합에서 제외하고 가중치 재정규화
→ 지금은 FDR만으로 1·2·4(3요소) 가동, 수급·팩터는 데이터 연결 후 5요소 완성.
"""
import numpy as np
import pandas as pd

DEFAULT_WEIGHTS = {'trend': 0.30, 'vol': 0.25, 'flow': 0.20,
                   'concentration': 0.10, 'factor': 0.15}


# ============================================================
# 1) 5요소 신호 (각 [-1, +1], +1=안전/위험선호, -1=위험/회피)
# ============================================================

def trend_signal(kospi_close, dt=None, mas=(60, 120, 200)):
    """지수추세: 종가가 60/120/200일 MA 위에 몇 개나 있나 → [-1,+1]."""
    s = kospi_close if dt is None else kospi_close[kospi_close.index <= dt]
    if len(s) < max(mas):
        return 0.0
    price = float(s.iloc[-1])
    above = sum(price > float(s.tail(m).mean()) for m in mas)
    return round(above / len(mas) * 2 - 1, 3)        # 3→+1, 0→-1


def vol_signal(vkospi, dt=None, asym=True, spike_win=5):
    """VKOSPI 수준 + 비대칭 급등 페널티 → [-1,+1].
    vkospi: Series(일별). 실현변동성 proxy면 임계가 다르므로 vol_signal_pct 사용 권장."""
    s = vkospi if dt is None else vkospi[vkospi.index <= dt]
    s = pd.Series(s).dropna()
    if len(s) == 0:
        return None
    v = float(s.iloc[-1])
    # 수준 신호
    if   v < 18: lvl = 1.0
    elif v < 25: lvl = 0.3
    elif v < 32: lvl = -0.4
    else:        lvl = -1.0
    # 비대칭: 최근 급등이면 추가 위험회피(빠르게), 하락엔 보너스 없음(천천히)
    if asym and len(s) > spike_win:
        chg = v - float(s.iloc[-spike_win - 1])
        if chg > 0:
            lvl -= min(0.4, chg / 10.0)              # 급등 페널티만, 하락 보너스 X
    return round(float(np.clip(lvl, -1, 1)), 3)


def vol_signal_pct(vol_series, dt=None, win=252, asym=True, spike_win=5):
    """실현변동성 등 다른 스케일용 — 트레일링 1년 분위수 기반."""
    s = vol_series if dt is None else vol_series[vol_series.index <= dt]
    s = pd.Series(s).dropna()
    if len(s) < 20:
        return None
    v = float(s.iloc[-1])
    p = (s.tail(win) < v).mean()                     # 높을수록 변동성 큼=위험
    lvl = 1 - 2 * p                                  # p=0→+1, p=1→-1
    if asym and len(s) > spike_win and v > float(s.iloc[-spike_win - 1]):
        lvl -= 0.3
    return round(float(np.clip(lvl, -1, 1)), 3)


def flow_signal(net_buy_cum):
    """수급: 외국인+기관 순매수 누적(예: 20일 합, 시계열 또는 스칼라) → [-1,+1].
    데이터 없으면 None 반환(요소 제외). pykrx get_market_net_purchases_of_equities 등."""
    if net_buy_cum is None:
        return None
    s = pd.Series(net_buy_cum).dropna()
    if len(s) < 2:
        return None
    z = (s.iloc[-1] - s.mean()) / (s.std() + 1e-9)
    return round(float(np.tanh(z)), 3)


def concentration_signal(picks, sector_map, hi=0.45, lo=0.25):
    """섹터집중: picks의 최대 섹터 비중 → 분산이면 +1, 집중이면 -1.
    (반도체 44% 같은 집중을 위험으로 신호) HHI 대체."""
    if not picks:
        return 0.0
    from collections import Counter
    cnt = Counter(sector_map.get(p, 'Other') for p in picks)
    top_share = max(cnt.values()) / len(picks)
    sig = 1 - (top_share - lo) / (hi - lo) * 2       # lo→+1, hi→-1
    return round(float(np.clip(sig, -1, 1)), 3)


def factor_signal(trailing_excess_ret, scale=0.05):
    """팩터 ON/OFF: 전략 트레일링 초과수익(예: 최근 3개월 vs KOSPI) 부호·크기 → [-1,+1].
    데이터 없으면 None."""
    if trailing_excess_ret is None:
        return None
    return round(float(np.clip(trailing_excess_ret / scale, -1, 1)), 3)


# ============================================================
# 2) 종합 + 비대칭 hysteresis
# ============================================================

def composite_score(signals, weights=None):
    """None 요소 제외 후 가중 평균. signals: {factor_key: value or None}."""
    w = weights or DEFAULT_WEIGHTS
    num = den = 0.0
    used = {}
    for k, wk in w.items():
        v = signals.get(k)
        if v is None:
            continue
        num += wk * v
        den += wk
        used[k] = v
    if den == 0:
        return 0.0, used
    return round(num / den, 4), used


def classify_regime(score, prev_state=None,
                    on=0.30, off=-0.20, exit_off=0.10):
    """비대칭 hysteresis:
       - RISK_OFF 진입: score ≤ off(-0.20)  (빠르게)
       - RISK_OFF 이탈: score > exit_off(+0.10) 필요 (천천히)
       - RISK_ON: score ≥ on(+0.30), 그 외 NEUTRAL."""
    if prev_state == 'RISK_OFF':
        if score > exit_off:
            return 'RISK_ON' if score >= on else 'NEUTRAL'
        return 'RISK_OFF'
    if score <= off:
        return 'RISK_OFF'
    if score >= on:
        return 'RISK_ON'
    return 'NEUTRAL'


def regime_to_exposure(state):
    """regime → (invest_frac, hedge_on). 매매룰 Layer 3/5를 이걸로 대체."""
    return {'RISK_ON':  (1.00, False),
            'NEUTRAL':  (0.90, False),
            'RISK_OFF': (0.60, True)}[state]


def detect(kospi_close, vkospi=None, net_buy_cum=None, picks=None,
           sector_map=None, trailing_excess=None, dt=None,
           prev_state=None, weights=None, vkospi_is_realized=False):
    """5요소 한 번에 → (state, score, signals, exposure)."""
    sig = {
        'trend': trend_signal(kospi_close, dt),
        'vol': (vol_signal_pct(vkospi, dt) if vkospi_is_realized
                else vol_signal(vkospi, dt)) if vkospi is not None else None,
        'flow': flow_signal(net_buy_cum),
        'concentration': concentration_signal(picks or [], sector_map or {}),
        'factor': factor_signal(trailing_excess),
    }
    score, used = composite_score(sig, weights)
    state = classify_regime(score, prev_state)
    invest, hedge = regime_to_exposure(state)
    return {'state': state, 'score': score, 'signals': sig, 'used': used,
            'invest_frac': invest, 'hedge_on': hedge}


# ============================================================
# 3) self-test (synthetic, 네트워크/외부데이터 불필요)
# ============================================================

def _selftest():
    ok = 0
    idx = pd.bdate_range('2022-01-01', periods=260)
    up = pd.Series(np.linspace(100, 140, 260), index=idx)     # 강한 상승
    dn = pd.Series(np.linspace(140, 100, 260), index=idx)     # 하락
    assert trend_signal(up) > 0.5; ok += 1
    assert trend_signal(dn) < -0.5; ok += 1

    # VKOSPI 수준
    vlow = pd.Series([15]*30, index=pd.bdate_range('2022-01-01', periods=30))
    vhigh = pd.Series([35]*30, index=pd.bdate_range('2022-01-01', periods=30))
    assert vol_signal(vlow) > 0.5 and vol_signal(vhigh) < -0.5; ok += 1
    # 비대칭: 같은 수준이라도 급등 직후면 더 위험
    vspike = pd.Series([20]*20 + [20, 21, 23, 26, 30, 34], index=pd.bdate_range('2022-01-01', periods=26))
    vcalm  = pd.Series([34]*26, index=pd.bdate_range('2022-01-01', periods=26))
    assert vol_signal(vspike) <= vol_signal(vcalm); ok += 1

    # 섹터집중: 분산 vs 집중
    smap = {f's{i}': sec for i, sec in enumerate(
        ['반도체','반도체','반도체','반도체','금융','식품'])}
    picks_div = ['s0','s4','s5'] ; picks_conc = ['s0','s1','s2','s3']
    sm = {'s0':'반도체','s1':'반도체','s2':'반도체','s3':'반도체','s4':'금융','s5':'식품'}
    assert concentration_signal(picks_div, sm) > concentration_signal(picks_conc, sm); ok += 1
    assert concentration_signal(picks_conc, sm) < 0; ok += 1   # 100% 반도체 → 위험

    # flow / factor 부호
    assert flow_signal(pd.Series([0,1,2,5,9])) > 0 and flow_signal(pd.Series([0,-2,-5,-9])) < 0; ok += 1
    assert factor_signal(0.08) == 1.0 and factor_signal(-0.08) == -1.0 and factor_signal(0) == 0.0; ok += 1
    assert flow_signal(None) is None and factor_signal(None) is None; ok += 1

    # 종합 + degradation (None 제외 재정규화)
    sc, used = composite_score({'trend':1, 'vol':1, 'flow':None, 'concentration':1, 'factor':None})
    assert abs(sc - 1.0) < 1e-9 and set(used) == {'trend','vol','concentration'}; ok += 1

    # 비대칭 hysteresis: 빠르게 진입, 천천히 이탈
    assert classify_regime(-0.25, prev_state='NEUTRAL') == 'RISK_OFF'; ok += 1     # 빠른 진입
    assert classify_regime(0.05, prev_state='RISK_OFF') == 'RISK_OFF'; ok += 1     # 아직 못 나감
    assert classify_regime(0.15, prev_state='RISK_OFF') in ('NEUTRAL','RISK_ON'); ok += 1  # 충분히 회복해야 이탈
    assert classify_regime(0.35, prev_state='NEUTRAL') == 'RISK_ON'; ok += 1

    # exposure 매핑
    assert regime_to_exposure('RISK_ON') == (1.0, False)
    assert regime_to_exposure('RISK_OFF') == (0.6, True); ok += 1

    # 통합 detect
    r = detect(up, vkospi=vlow, picks=picks_div, sector_map=sm)
    assert r['state'] in ('RISK_ON','NEUTRAL','RISK_OFF') and 0 < r['invest_frac'] <= 1; ok += 1

    print(f"[OK] regime detector self-test 통과 ({ok} checks)")
    print(f"     예시(상승+저VKOSPI+분산): {detect(up, vkospi=vlow, picks=picks_div, sector_map=sm)}")
    print(f"     예시(하락+고VKOSPI+집중): {detect(dn, vkospi=vhigh, picks=picks_conc, sector_map=sm, prev_state='NEUTRAL')}")


if __name__ == '__main__':
    _selftest()
