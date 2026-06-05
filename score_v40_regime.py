#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""진우퀀트 모듈 D (v4.0 영역2) — regime별 가중치 조정 레이어 (Stage 3).

v3.7.2 production(score_v37_2.py) 무수정 import 레이어 — C(score_v39_pead) 패턴.
regime 신호·분류는 regime_detector_v40.py(06-03 MVP) 재사용.
기각된 1차 시도(현금화·헤지)와 달리 **100% 투자 유지, 팩터 가중치만 조정**.

사전 등록 multiplier (결정메모 §3, 변경 금지) — RISK_OFF에서만 발동:
  variant 'w'(약): Mom12 ×0.5, Echo ×0.5, BAB ×1.5
  variant 's'(강): Mom12 ×0.0, Echo ×0.0, BAB ×2.0
  NEUTRAL·RISK_ON: 전부 ×1.0 = v3.7.2와 완전 동일

정의 단일화: backtest_v40_regime.py가 이 파일의 REGIME_MULTS·adjusted_total을 import.

실행(현재 시점 비교): python score_v40_regime.py        [PC — FDR 필요]
self-test:            python score_v40_regime.py --selftest  (네트워크 불필요)
"""
import sys, json, argparse
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

BASE = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE))

from regime_detector_v40 import (trend_signal, vol_signal, vol_signal_pct,
                                 flow_signal, concentration_signal,
                                 composite_score, classify_regime, DEFAULT_WEIGHTS)

CACHE_FILE = BASE / 'regime_market_cache_v40.json'
TARGET_GRADES = {'S+', 'S', 'A'}

# ---------- 사전 등록 multiplier (결정메모 §3 — 변경 금지) ----------
REGIME_MULTS = {
    'w': {'RISK_OFF': {'mom': 0.5, 'echo': 0.5, 'bab': 1.5}},
    's': {'RISK_OFF': {'mom': 0.0, 'echo': 0.0, 'bab': 2.0}},
}
DEFAULT_MULT = {'mom': 1.0, 'echo': 1.0, 'bab': 1.0}
VARIANT_LABEL = {'w': 'regime_w(약)', 's': 'regime_s(강)'}


def mults_for(variant, state):
    """variant·state → multiplier dict. RISK_OFF 외에는 항상 기본(=base 동일)."""
    return REGIME_MULTS[variant].get(state, DEFAULT_MULT)


def adjusted_total(comp, state, variant):
    """컴포넌트 dict → regime 조정 체력 점수.
    comp: {'base': 체력12+ModF+FAR+Sloan, 'mom':, 'bab':, 'noa':, 'echo': (ECHO_WEIGHT 반영분)}"""
    m = mults_for(variant, state)
    return (comp['base'] + comp['mom'] * m['mom'] + comp['bab'] * m['bab']
            + comp['noa'] + comp['echo'] * m['echo'])


def components_from_row(row):
    """score_v37_2.compute_scores() DataFrame 행 → 컴포넌트 dict."""
    return {'base': float(row['체력_12점'] + row['ModF'] + row['FAR'] + row['Sloan']),
            'mom': float(row['Mom12']), 'bab': float(row['BAB']),
            'noa': float(row['NOA']), 'echo': float(row['Echo'])}


# ---------- 현재 시점 시장 regime (live) ----------

def load_market_cache():
    if not CACHE_FILE.exists():
        return None
    try:
        return json.loads(CACHE_FILE.read_text(encoding='utf-8'))
    except Exception:
        return None


def current_regime(kospi, picks, sectors_map, cache=None, prev_state=None):
    """live 시점 regime. factor 요소는 live에선 None(이력 필요) → 재정규화.
    cache 없으면 vol·flow도 제외 — 최소 trend+concentration 2요소로 동작."""
    vol_s = flow_s = None
    vol_is_vkospi = False
    if cache:
        from fetch_regime_market_v40 import load_cache_series
        vol_s, vol_is_vkospi, flow_s = load_cache_series(cache)
    sig = {'trend': trend_signal(kospi)}
    sig['vol'] = ((vol_signal(vol_s) if vol_is_vkospi else vol_signal_pct(vol_s))
                  if vol_s is not None else None)
    sig['flow'] = (flow_signal(flow_s.tail(250)) if flow_s is not None else None)
    sig['concentration'] = concentration_signal(picks, sectors_map)
    sig['factor'] = None  # live: 전략 trailing 이력 미보유 (백테스트에서는 산출)
    score, used = composite_score(sig, DEFAULT_WEIGHTS)
    state = classify_regime(score, prev_state=prev_state)
    return state, score, sig, used


# ---------- live main ----------

def main():
    import score_v37_2 as base

    print("=" * 80)
    print("진우퀀트 모듈 D — v4.0 regime 가중치 조정 (현재 시점 비교, production 무수정)")
    print(f"시간: {datetime.now()}")
    print("=" * 80)

    panel = base.fetch_price_panel()
    df = base.compute_scores(panel)

    picks_base = df[df['등급'].isin(TARGET_GRADES)]['종목'].tolist()
    sectors_map = dict(zip(df['종목'], df['산업']))

    cache = load_market_cache()
    if cache is None:
        print("\n⚠️ regime_market_cache_v40.json 없음 → fetch_regime_market_v40.py 먼저 실행 권장")
        print("   (trend+섹터집중 2요소만으로 임시 분류)")
    state, score, sig, used = current_regime(panel.get('_KOSPI'), picks_base, sectors_map, cache)

    print(f"\n🧭 현재 regime: {state} (score {score:+.3f}, {len(used)}요소: "
          + ", ".join(f"{k}={v:+.2f}" for k, v in used.items()) + ")")
    print("   ※ live는 단일 시점 분류(직전 상태 미보유) — 관찰 모드 도입 시 상태 파일로 hysteresis 유지 예정")

    if state != 'RISK_OFF':
        print(f"\n→ {state}: multiplier 미발동. v4.0 = v3.7.2 완전 동일 (픽 {len(picks_base)}종목 그대로)")
    out_rows = []
    for _, row in df.iterrows():
        comp = components_from_row(row)
        rec = {'종목': row['종목'], '등급_v37_2': row['등급'], '체력_v37_2': row['체력_최종']}
        for v in ('w', 's'):
            t = adjusted_total(comp, state, v)
            rec[f'체력_{v}'] = round(t, 2)
            rec[f'등급_{v}'] = base.grade(t) if hasattr(base, 'grade') else __import__('score_v37').grade(t)
        out_rows.append(rec)
    cmp_df = pd.DataFrame(out_rows)

    if state == 'RISK_OFF':
        print("\n⚠️ RISK_OFF — 변형별 등급 비교:")
        for v in ('w', 's'):
            picks_v = cmp_df[cmp_df[f'등급_{v}'].isin(TARGET_GRADES)]['종목'].tolist()
            diff_in = sorted(set(picks_v) - set(picks_base))
            diff_out = sorted(set(picks_base) - set(picks_v))
            print(f"  {VARIANT_LABEL[v]}: 픽 {len(picks_v)}종목 | 신규편입 {diff_in or '없음'} | 제외 {diff_out or '없음'}")
        chg = cmp_df[(cmp_df['등급_v37_2'] != cmp_df['등급_w']) | (cmp_df['등급_v37_2'] != cmp_df['등급_s'])]
        if len(chg):
            print("\n등급 변동 종목:")
            print(chg[['종목', '등급_v37_2', '등급_w', '등급_s']].to_string(index=False))

    print("\n※ 판정은 backtest_v40_regime.py (사전 합격선: MDD≥+2.0%p AND CAGR≥−1.0%p AND Sharpe·IR 비열위)")


# ---------- self-test (synthetic, 네트워크·production 데이터 불필요) ----------

def _selftest():
    ok = 0
    comp = {'base': 10.0, 'mom': 2.0, 'bab': -1.0, 'noa': 0.0, 'echo': 1.0}

    # 1) RISK_ON / NEUTRAL → base와 완전 동일 (핵심 불변식)
    t_base = comp['base'] + comp['mom'] + comp['bab'] + comp['noa'] + comp['echo']
    for st in ('RISK_ON', 'NEUTRAL'):
        for v in ('w', 's'):
            assert abs(adjusted_total(comp, st, v) - t_base) < 1e-12
    ok += 1

    # 2) RISK_OFF 'w': 10 + 2*0.5 + (-1)*1.5 + 0 + 1*0.5 = 10.0
    assert abs(adjusted_total(comp, 'RISK_OFF', 'w') - 10.0) < 1e-12; ok += 1
    # 3) RISK_OFF 's': 10 + 0 + (-1)*2 + 0 + 0 = 8.0
    assert abs(adjusted_total(comp, 'RISK_OFF', 's') - 8.0) < 1e-12; ok += 1

    # 4) 저β(+BAB) 종목은 RISK_OFF에서 점수 상승
    comp_lowbeta = {'base': 10.0, 'mom': 0.0, 'bab': 2.0, 'noa': 0.0, 'echo': 0.0}
    assert adjusted_total(comp_lowbeta, 'RISK_OFF', 's') > sum(comp_lowbeta.values()); ok += 1

    # 5) 모멘텀 종목 등급 강등 방향 (mom+echo=3점 소거 → 등급컷 통과 실패 사례)
    from score_v37 import grade
    hi_mom = {'base': 11.5, 'mom': 2.0, 'bab': 0.0, 'noa': 0.0, 'echo': 1.0}
    g_on = grade(adjusted_total(hi_mom, 'RISK_ON', 's'))
    g_off = grade(adjusted_total(hi_mom, 'RISK_OFF', 's'))
    assert g_on != g_off, '모멘텀 의존 종목은 RISK_OFF(s)에서 등급 하락해야'; ok += 1

    # 6) components_from_row ↔ 체력_최종 정합 (production 컬럼 구조 가정 검증)
    row = pd.Series({'체력_12점': 9.33, 'ModF': 1.0, 'FAR': 2.0, 'Sloan': -1.0,
                     'Mom12': 1.0, 'BAB': -1.0, 'NOA': 0.0, 'Echo': 1.0, '체력_최종': 12.33})
    c = components_from_row(row)
    recon = c['base'] + c['mom'] + c['bab'] + c['noa'] + c['echo']
    assert abs(recon - row['체력_최종']) < 1e-9; ok += 1

    # 7) mults_for: 미정의 state는 기본 multiplier
    assert mults_for('w', 'WEIRD_STATE') == DEFAULT_MULT; ok += 1

    # 8) current_regime: 캐시 없이도 동작 (2요소) + RISK_OFF 경로
    idx = pd.bdate_range('2023-01-02', periods=300)
    dn = pd.Series(np.linspace(140, 100, 300), index=idx)
    sm = {'A': '반도체', 'B': '반도체', 'C': '반도체'}
    st, sc, sig, used = current_regime(dn, ['A', 'B', 'C'], sm, cache=None)
    assert sig['vol'] is None and sig['factor'] is None and len(used) == 2; ok += 1
    assert st == 'RISK_OFF', f'하락추세+집중인데 {st}'; ok += 1

    print(f"[OK] score_v40_regime self-test 통과 ({ok} checks)")
    print("     변형 2개 고정: w(Mom·Echo×0.5, BAB×1.5) / s(Mom·Echo×0, BAB×2) — RISK_OFF에서만")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--selftest', action='store_true')
    a, _ = ap.parse_known_args()
    try:
        _selftest() if a.selftest else main()
    except Exception:
        import traceback
        print("\n===== [에러] 아래 내용을 그대로 복사해 붙여주세요 =====")
        traceback.print_exc()
