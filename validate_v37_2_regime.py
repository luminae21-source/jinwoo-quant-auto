#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
진우퀀트 v3.7.2 시장상태 분리 검증 (Tier 1 #3)

GPT Q4 권장:
  Echo를 추가할 때는 상승장/하락장 분리 성과 동시 확인 필수.
  엄철준 2024 tail risk 우려가 환경별로 어떻게 발현되는지 측정.

시장 상태 분류:
  - Up State: KOSPI 직전 6개월 누적 수익률 > 0
  - Down State: KOSPI 직전 6개월 누적 수익률 ≤ 0
  - 추가: VKOSPI 또는 시장 변동성 기반 분류 (선택)

각 상태별 측정:
  - 평균 월수익률
  - 변동성
  - Sharpe (annualized 추정)
  - 최악 월
  - 승률
"""

import sys
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np

BASE = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE))

from score_v37 import (
    JINWOO_v37, KOSPI_CODE,
    compute_mom12, compute_beta60,
    mom12_to_score, noa_to_score,
    far_trigger, grade,
)
from score_v37_1 import bab_to_score as bab_to_score_v371
from score_v37_2 import compute_echo_scores, ECHO_WEIGHT


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--years', type=int, default=4)
    p.add_argument('--top-grades', type=str, default='S+,S,A')
    return p.parse_args()


def fetch_long_panel(years=4):
    try:
        import FinanceDataReader as fdr
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, '-m', 'pip', 'install',
                               '-q', 'finance-datareader'])
        import FinanceDataReader as fdr
    end = datetime.now()
    start = end - timedelta(days=int(365 * (years + 1.2)))
    panel = {}
    df = fdr.DataReader(KOSPI_CODE, start.strftime('%Y-%m-%d'),
                        end.strftime('%Y-%m-%d'))
    panel['_KOSPI'] = df['Close']
    for name, info in JINWOO_v37.items():
        try:
            df = fdr.DataReader(info['코드'], start.strftime('%Y-%m-%d'),
                                end.strftime('%Y-%m-%d'))
            panel[name] = df['Close']
        except Exception:
            panel[name] = None
    return panel


def compute_v37_2_picks_at(panel, dt, target_grades, with_echo=True):
    kospi = panel.get('_KOSPI')
    if with_echo:
        echo_values = {}
        for name in JINWOO_v37:
            s = panel.get(name)
            if s is None: continue
            s_cut = s[s.index <= dt]
            if len(s_cut) < 13 * 21: continue
            p_t12 = s_cut.iloc[-12*21]
            p_t7 = s_cut.iloc[-7*21]
            if p_t12 == 0: continue
            echo_values[name] = float(p_t7 / p_t12 - 1)
        if echo_values:
            n = len(echo_values)
            upper_n = max(1, round(n * 0.2))
            lower_n = max(1, round(n * 0.2))
            sd = pd.Series(echo_values).sort_values(ascending=False)
            upper = sd.iloc[upper_n - 1]
            lower = sd.iloc[-lower_n]
            echo_scores = {n: 0 for n in JINWOO_v37}
            for name in JINWOO_v37:
                v = echo_values.get(name)
                if v is None: continue
                elif v >= upper: echo_scores[name] = +1
                elif v <= lower: echo_scores[name] = -1
                else: echo_scores[name] = 0
        else:
            echo_scores = {n: 0 for n in JINWOO_v37}
    else:
        echo_scores = {n: 0 for n in JINWOO_v37}

    picks = []
    for name, info in JINWOO_v37.items():
        s = panel.get(name)
        if s is None: continue
        s_cut = s[s.index <= dt]
        k_cut = kospi[kospi.index <= dt]
        if len(s_cut) < 253: continue
        체력_12점 = info['F_korean'] * (12 / 9.001)
        r_1m = s_cut.iloc[-1] / s_cut.iloc[-21] - 1 if len(s_cut) >= 22 else None
        far_val, _ = far_trigger(체력_12점, r_1m)
        r_mom12 = compute_mom12(s_cut)
        beta60 = compute_beta60(s_cut, k_cut)
        total = (체력_12점 + info['ModF'] + far_val + info['Sloan']
                + mom12_to_score(r_mom12) + bab_to_score_v371(beta60)
                + noa_to_score(info.get('NOA', 0))
                + echo_scores.get(name, 0) * ECHO_WEIGHT)
        if grade(total) in target_grades:
            picks.append(name)
    return picks


def avg_return(picks, panel, dt_start, dt_end):
    if len(picks) == 0: return 0.0
    rets = []
    for name in picks:
        s = panel.get(name)
        if s is None: continue
        sw = s[(s.index > dt_start) & (s.index <= dt_end)]
        if len(sw) < 2: continue
        rets.append(float(sw.iloc[-1] / sw.iloc[0] - 1))
    return float(np.mean(rets)) if rets else 0.0


def kospi_return(panel, dt_start, dt_end):
    k = panel.get('_KOSPI')
    kw = k[(k.index > dt_start) & (k.index <= dt_end)]
    if len(kw) < 2: return 0.0
    return float(kw.iloc[-1] / kw.iloc[0] - 1)


def classify_market_state(kospi, dt, lookback_months=6):
    """직전 lookback_months 개월 KOSPI 수익률 부호로 상태 분류"""
    days = lookback_months * 21
    if len(kospi) < days: return 'Unknown'
    k_at = kospi[kospi.index <= dt]
    if len(k_at) < days: return 'Unknown'
    r = float(k_at.iloc[-1] / k_at.iloc[-days] - 1)
    return 'Up' if r > 0 else 'Down'


def get_rebal_dates(panel, years):
    k = panel.get('_KOSPI')
    end_dt = k.index[-1]
    start_dt = end_dt - pd.DateOffset(years=years)
    bp = k[(k.index >= start_dt) & (k.index <= end_dt)]
    rebal = bp.resample('MS').first().dropna().index
    rebal = [k.index[k.index.get_indexer([d], method='bfill')[0]]
             for d in rebal if d <= end_dt]
    rebal = sorted(set(rebal))
    if rebal and rebal[-1] < end_dt: rebal.append(end_dt)
    return rebal


def main():
    args = parse_args()
    print("=" * 90)
    print("진우퀀트 v3.7.2 시장상태 분리 검증")
    print(f"시간: {datetime.now()}")
    print("=" * 90)

    print("\n📊 데이터 수집...")
    panel = fetch_long_panel(args.years)
    print(f"  완료")

    target = set(args.top_grades.split(','))
    rebal_dates = get_rebal_dates(panel, args.years)
    kospi = panel.get('_KOSPI')

    # 각 rebalance 시점 분류 + v3.7.2 / v3.7.1 / KOSPI 수익률 수집
    print("\n📋 시장상태 분류 + 성과 측정...")
    records = []
    for i in range(len(rebal_dates) - 1):
        d0, d1 = rebal_dates[i], rebal_dates[i + 1]
        state = classify_market_state(kospi, d0, 6)
        picks_v372 = compute_v37_2_picks_at(panel, d0, target, with_echo=True)
        picks_v371 = compute_v37_2_picks_at(panel, d0, target, with_echo=False)
        r_v372 = avg_return(picks_v372, panel, d0, d1)
        r_v371 = avg_return(picks_v371, panel, d0, d1)
        r_kospi = kospi_return(panel, d0, d1)
        records.append({
            'date': d0.strftime('%Y-%m-%d'),
            'state': state,
            'r_v37_2': r_v372,
            'r_v37_1': r_v371,
            'r_kospi': r_kospi,
        })

    df = pd.DataFrame(records)

    # 각 상태별 통계
    print("\n" + "=" * 90)
    print("시장상태별 v3.7.2 / v3.7.1 / KOSPI 성과")
    print("=" * 90)

    for state in ['Up', 'Down']:
        sub = df[df['state'] == state]
        n = len(sub)
        if n == 0:
            print(f"\n[{state} State] 데이터 없음")
            continue

        r372 = np.array(sub['r_v37_2'])
        r371 = np.array(sub['r_v37_1'])
        rk = np.array(sub['r_kospi'])

        def stats(arr):
            if len(arr) == 0: return {}
            mean = float(np.mean(arr)) * 100
            std = float(np.std(arr)) * 100
            sharpe_ann = float(np.mean(arr) / np.std(arr) * np.sqrt(12)) if np.std(arr) > 0 else None
            return {
                '평균월수익_%': round(mean, 2),
                '변동성월_%': round(std, 2),
                'Sharpe_연환산': round(sharpe_ann, 2) if sharpe_ann else None,
                '최악월_%': round(float(np.min(arr)) * 100, 2),
                '승률_%': round(float((arr > 0).mean()) * 100, 1),
                '월수': n,
            }

        s372 = stats(r372)
        s371 = stats(r371)
        sk = stats(rk)

        print(f"\n[{state} State] ({n}개월, KOSPI 직전 6M {state.lower()})")
        print(f"  v3.7.2  : 평균월 {s372.get('평균월수익_%',0):>5.2f}%  "
              f"변동성 {s372.get('변동성월_%',0):>5.2f}%  "
              f"Sharpe(연) {str(s372.get('Sharpe_연환산','-')):>5s}  "
              f"최악월 {s372.get('최악월_%',0):>6.2f}%  승률 {s372.get('승률_%',0):>5.1f}%")
        print(f"  v3.7.1  : 평균월 {s371.get('평균월수익_%',0):>5.2f}%  "
              f"변동성 {s371.get('변동성월_%',0):>5.2f}%  "
              f"Sharpe(연) {str(s371.get('Sharpe_연환산','-')):>5s}  "
              f"최악월 {s371.get('최악월_%',0):>6.2f}%  승률 {s371.get('승률_%',0):>5.1f}%")
        print(f"  KOSPI   : 평균월 {sk.get('평균월수익_%',0):>5.2f}%  "
              f"변동성 {sk.get('변동성월_%',0):>5.2f}%  "
              f"Sharpe(연) {str(sk.get('Sharpe_연환산','-')):>5s}  "
              f"최악월 {sk.get('최악월_%',0):>6.2f}%  승률 {sk.get('승률_%',0):>5.1f}%")
        delta = s372.get('평균월수익_%', 0) - s371.get('평균월수익_%', 0)
        print(f"  → Echo 효과 ({state}): {delta:+.2f}%p/월")

    # 검증 결과 판정
    print("\n" + "=" * 90)
    print("판정")
    print("=" * 90)
    up_sub = df[df['state'] == 'Up']
    down_sub = df[df['state'] == 'Down']
    if len(up_sub) > 0:
        up_372 = float(np.mean(up_sub['r_v37_2'])) * 100
        up_371 = float(np.mean(up_sub['r_v37_1'])) * 100
        print(f"  상승장 Echo 효과: {up_372 - up_371:+.2f}%p/월")
    if len(down_sub) > 0:
        down_372 = float(np.mean(down_sub['r_v37_2'])) * 100
        down_371 = float(np.mean(down_sub['r_v37_1'])) * 100
        print(f"  하락장 Echo 효과: {down_372 - down_371:+.2f}%p/월")
        if down_372 >= down_371:
            print(f"  ✅ Echo가 하락장에서도 v3.7.1 유지 — 견고")
        else:
            print(f"  ⚠️ Echo가 하락장에서 v3.7.1 하회 — tail risk 가능성")

    out = BASE / f'validate_regime_{datetime.now().strftime("%Y%m%d_%H%M")}.json'
    out.write_text(json.dumps({
        'timestamp': datetime.now().isoformat(),
        'records': records,
        'up_count': int(len(up_sub)),
        'down_count': int(len(down_sub)),
    }, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(f"\n💾 저장: {out}")


if __name__ == '__main__':
    main()
