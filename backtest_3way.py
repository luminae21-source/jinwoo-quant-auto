#!/usr/bin/env python3
"""
진우퀀트 3-way 백테스트: v3.6 vs v3.7 vs v3.7.1

목적: BAB 임계값 조정(v3.7.1)이 강세장 alpha 회복에 효과적인지 검증

핵심 비교:
  - v3.6   : F + ModF + FAR + Sloan
  - v3.7   : v3.6 + Mom12 + BAB(원본 임계값) + NOA
  - v3.7.1 : v3.6 + Mom12 + BAB(완화 임계값) + NOA

기대 결과:
  - v3.7.1이 v3.7과 v3.6 사이의 절충점 (수익 회복 + 안정성 일부 유지)
  - KT&G·아모레 과편입 감소
  - 반도체 비중 회복

실행:
  python3 backtest_3way.py
  python3 backtest_3way.py --years 4 --top-grades S+,S,A
"""

import sys
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np

BASE = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE))

# v3.7 (원본)과 v3.7.1 (조정본) 모두 import
from score_v37 import (
    JINWOO_v37, KOSPI_CODE,
    compute_mom12, compute_beta60,
    mom12_to_score, noa_to_score,
    far_trigger, grade,
    bab_to_score as bab_to_score_v37,
)
from score_v37_1 import bab_to_score as bab_to_score_v371


# ============================================
# 인자
# ============================================
def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--years', type=int, default=4)
    p.add_argument('--top-grades', type=str, default='S+,S,A')
    p.add_argument('--weights', choices=['equal', 'score'], default='equal')
    p.add_argument('--rebalance', choices=['M', 'Q'], default='M')
    return p.parse_args()


# ============================================
# 데이터 수집
# ============================================
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
    print(f"\n📊 백테스트 데이터 수집 ({start.date()} → {end.date()}):")

    try:
        df = fdr.DataReader(KOSPI_CODE, start.strftime('%Y-%m-%d'),
                            end.strftime('%Y-%m-%d'))
        panel['_KOSPI'] = df['Close']
        print(f"  {'KOSPI':14s} {len(df)} 영업일")
    except Exception as e:
        panel['_KOSPI'] = None
        print(f"  ❌ KOSPI 실패: {e}")
        return panel

    for name, info in JINWOO_v37.items():
        try:
            df = fdr.DataReader(info['코드'], start.strftime('%Y-%m-%d'),
                                end.strftime('%Y-%m-%d'))
            panel[name] = df['Close']
            print(f"  {name:14s} {len(df)} 영업일")
        except Exception as e:
            panel[name] = None
            print(f"  ❌ {name} 실패: {e}")
    return panel


# ============================================
# 시점별 3-way 점수 (한 번에 세 시스템 계산)
# ============================================
def compute_scores_3way_at(panel, dt):
    kospi = panel.get('_KOSPI')
    if kospi is None:
        return None

    rows = []
    for name, info in JINWOO_v37.items():
        series = panel.get(name)
        if series is None or len(series) == 0:
            continue
        s_cut = series[series.index <= dt]
        k_cut = kospi[kospi.index <= dt]
        if len(s_cut) < 253:
            continue

        # v3.6 핵심
        체력_12점 = info['F_korean'] * (12 / 9.001)
        if len(s_cut) >= 22:
            r_1m = s_cut.iloc[-1] / s_cut.iloc[-21] - 1
        else:
            r_1m = None
        far_val, _ = far_trigger(체력_12점, r_1m)
        base = 체력_12점 + info['ModF'] + far_val + info['Sloan']

        # v3.7·v3.7.1 공통 신규 팩터
        r_mom12 = compute_mom12(s_cut)
        beta60 = compute_beta60(s_cut, k_cut)
        mom_s = mom12_to_score(r_mom12)
        noa_s = noa_to_score(info.get('NOA', 0))

        # BAB 두 버전
        bab_v37  = bab_to_score_v37(beta60)
        bab_v371 = bab_to_score_v371(beta60)

        total_v36  = base
        total_v37  = base + mom_s + bab_v37  + noa_s
        total_v371 = base + mom_s + bab_v371 + noa_s

        rows.append({
            '종목': name,
            'β_60d': round(beta60, 3) if beta60 is not None else None,
            'Mom12': mom_s,
            'BAB_v37': bab_v37,
            'BAB_v37_1': bab_v371,
            '체력_v36':   round(base, 2),
            '체력_v37':   round(total_v37, 2),
            '체력_v37_1': round(total_v371, 2),
            '등급_v36':   grade(base),
            '등급_v37':   grade(total_v37),
            '등급_v37_1': grade(total_v371),
        })
    return pd.DataFrame(rows)


# ============================================
# 포트폴리오 수익률
# ============================================
def avg_return(picks, panel, dt_start, dt_end, weights='equal', scores=None):
    if len(picks) == 0:
        return 0.0
    rets, ws = [], []
    for name in picks:
        s = panel.get(name)
        if s is None: continue
        s_window = s[(s.index > dt_start) & (s.index <= dt_end)]
        if len(s_window) < 2: continue
        r = s_window.iloc[-1] / s_window.iloc[0] - 1
        rets.append(r)
        if weights == 'score' and scores is not None and name in scores:
            ws.append(max(scores[name], 0.1))
        else:
            ws.append(1.0)
    if not rets: return 0.0
    rets, ws = np.array(rets), np.array(ws)
    return float(np.sum(rets * ws) / np.sum(ws))


def kospi_return(panel, dt_start, dt_end):
    k = panel.get('_KOSPI')
    if k is None: return 0.0
    k_window = k[(k.index > dt_start) & (k.index <= dt_end)]
    if len(k_window) < 2: return 0.0
    return float(k_window.iloc[-1] / k_window.iloc[0] - 1)


# ============================================
# 메트릭
# ============================================
def metrics(monthly_rets, periods_per_year=12):
    arr = np.array(monthly_rets)
    if len(arr) == 0: return {}
    cumulative = float(np.prod(1 + arr) - 1)
    annualized = (1 + cumulative) ** (periods_per_year / len(arr)) - 1
    vol = float(arr.std() * np.sqrt(periods_per_year))
    sharpe = float(annualized / vol) if vol > 0 else None
    cum_curve = np.cumprod(1 + arr)
    peak = np.maximum.accumulate(cum_curve)
    drawdown = (cum_curve - peak) / peak
    mdd = float(drawdown.min())
    win_rate = float((arr > 0).mean())
    return {
        '누적': round(cumulative * 100, 2),
        '연환산': round(annualized * 100, 2),
        '변동성': round(vol * 100, 2),
        'Sharpe': round(sharpe, 2) if sharpe else None,
        'MDD': round(mdd * 100, 2),
        '승률': round(win_rate * 100, 1),
        '기간': len(arr),
    }


def information_ratio(port_rets, bench_rets, periods_per_year=12):
    p, b = np.array(port_rets), np.array(bench_rets)
    excess = p - b
    if len(excess) < 2: return None
    ann_excess = excess.mean() * periods_per_year
    te = excess.std() * np.sqrt(periods_per_year)
    if te == 0: return None
    return round(float(ann_excess / te), 2)


# ============================================
# 3-way 백테스트
# ============================================
def run_backtest(panel, args):
    target_grades = set(args.top_grades.split(','))
    k = panel.get('_KOSPI')
    if k is None or len(k) == 0:
        print("❌ KOSPI 데이터 없음")
        return None

    end_dt = k.index[-1]
    start_dt = end_dt - pd.DateOffset(years=args.years)
    backtest_period = k[(k.index >= start_dt) & (k.index <= end_dt)]

    if args.rebalance == 'M':
        rebal_dates = backtest_period.resample('MS').first().dropna().index
    else:
        rebal_dates = backtest_period.resample('QS').first().dropna().index

    rebal_dates = [k.index[k.index.get_indexer([d], method='bfill')[0]]
                   for d in rebal_dates if d <= end_dt]
    rebal_dates = sorted(set(rebal_dates))
    if rebal_dates[-1] < end_dt:
        rebal_dates.append(end_dt)

    print(f"\n🔁 Rebalance: {len(rebal_dates)-1}회 ({rebal_dates[0].date()} → {rebal_dates[-1].date()})")

    rets_v36, rets_v37, rets_v371, rets_bench = [], [], [], []
    n_picks_v36, n_picks_v37, n_picks_v371 = [], [], []
    history = []

    for i in range(len(rebal_dates) - 1):
        d0, d1 = rebal_dates[i], rebal_dates[i + 1]
        snap = compute_scores_3way_at(panel, d0)
        if snap is None or len(snap) == 0:
            continue

        picks_v36  = snap[snap['등급_v36'].isin(target_grades)]['종목'].tolist()
        picks_v37  = snap[snap['등급_v37'].isin(target_grades)]['종목'].tolist()
        picks_v371 = snap[snap['등급_v37_1'].isin(target_grades)]['종목'].tolist()

        s_v37  = dict(zip(snap['종목'], snap['체력_v37']))
        s_v371 = dict(zip(snap['종목'], snap['체력_v37_1']))

        r36  = avg_return(picks_v36,  panel, d0, d1, args.weights)
        r37  = avg_return(picks_v37,  panel, d0, d1, args.weights, s_v37)
        r371 = avg_return(picks_v371, panel, d0, d1, args.weights, s_v371)
        rb = kospi_return(panel, d0, d1)

        rets_v36.append(r36)
        rets_v37.append(r37)
        rets_v371.append(r371)
        rets_bench.append(rb)
        n_picks_v36.append(len(picks_v36))
        n_picks_v37.append(len(picks_v37))
        n_picks_v371.append(len(picks_v371))

        history.append({
            'date': d0.strftime('%Y-%m-%d'),
            'n_v36': len(picks_v36),
            'n_v37': len(picks_v37),
            'n_v37_1': len(picks_v371),
            'r_v36_%': round(r36 * 100, 2),
            'r_v37_%': round(r37 * 100, 2),
            'r_v37_1_%': round(r371 * 100, 2),
            'r_kospi_%': round(rb * 100, 2),
            'picks_v36': picks_v36,
            'picks_v37': picks_v37,
            'picks_v37_1': picks_v371,
            'only_v37_1_vs_v37': sorted(set(picks_v371) - set(picks_v37)),
            'only_v37_vs_v37_1': sorted(set(picks_v37) - set(picks_v371)),
        })

    periods_per_year = 12 if args.rebalance == 'M' else 4

    m36   = metrics(rets_v36,   periods_per_year)
    m37   = metrics(rets_v37,   periods_per_year)
    m371  = metrics(rets_v371,  periods_per_year)
    mbench = metrics(rets_bench, periods_per_year)

    ir36  = information_ratio(rets_v36,  rets_bench, periods_per_year)
    ir37  = information_ratio(rets_v37,  rets_bench, periods_per_year)
    ir371 = information_ratio(rets_v371, rets_bench, periods_per_year)

    # 출력
    print("\n" + "=" * 78)
    print(f"3-way 백테스트  ({args.years}년 · {args.rebalance} · 등급 {args.top_grades} · {args.weights})")
    print("=" * 78)

    def row(label, m, ir=None):
        print(f"{label:10s} | 누적 {m.get('누적',0):>7.2f}%  연환산 {m.get('연환산',0):>6.2f}%  "
              f"vol {m.get('변동성',0):>5.2f}%  Sharpe {str(m.get('Sharpe','-')):>5s}  "
              f"MDD {m.get('MDD',0):>6.2f}%  IR {str(ir if ir else '-'):>5s}  "
              f"승률 {m.get('승률',0):>5.1f}%")

    row("v3.6",   m36,  ir36)
    row("v3.7",   m37,  ir37)
    row("v3.7.1", m371, ir371)
    row("KOSPI", mbench)

    print(f"\n평균 보유 종목 수:")
    print(f"  v3.6   {np.mean(n_picks_v36):.1f}")
    print(f"  v3.7   {np.mean(n_picks_v37):.1f}")
    print(f"  v3.7.1 {np.mean(n_picks_v371):.1f}")

    print(f"\n연환산 alpha (vs v3.6):")
    print(f"  v3.7   : {m37.get('연환산',0) - m36.get('연환산',0):+.2f}%p/년")
    print(f"  v3.7.1 : {m371.get('연환산',0) - m36.get('연환산',0):+.2f}%p/년")
    print(f"\n연환산 alpha (vs KOSPI):")
    print(f"  v3.6   : {m36.get('연환산',0) - mbench.get('연환산',0):+.2f}%p/년")
    print(f"  v3.7   : {m37.get('연환산',0) - mbench.get('연환산',0):+.2f}%p/년")
    print(f"  v3.7.1 : {m371.get('연환산',0) - mbench.get('연환산',0):+.2f}%p/년")

    # 저장
    report = {
        'timestamp': datetime.now().isoformat(),
        'config': vars(args),
        'metrics': {'v36': m36, 'v37': m37, 'v37_1': m371, 'kospi': mbench},
        'ir': {'v36': ir36, 'v37': ir37, 'v37_1': ir371},
        'avg_picks': {
            'v36': float(np.mean(n_picks_v36)),
            'v37': float(np.mean(n_picks_v37)),
            'v37_1': float(np.mean(n_picks_v371)),
        },
        'history': history,
    }
    out_path = BASE / f'backtest_3way_{datetime.now().strftime("%Y%m%d_%H%M")}.json'
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                        encoding='utf-8')
    print(f"\n💾 리포트 저장: {out_path}")

    # 최근 시점 v3.7 → v3.7.1 차이
    last_snap = compute_scores_3way_at(panel, rebal_dates[-2])
    if last_snap is not None:
        last_snap['Δ_체력'] = last_snap['체력_v37_1'] - last_snap['체력_v37']
        last_snap['Δ_등급'] = last_snap.apply(
            lambda r: f"{r['등급_v37']} → {r['등급_v37_1']}"
                      if r['등급_v37'] != r['등급_v37_1'] else '', axis=1)
        impact = last_snap[last_snap['Δ_등급'] != ''][
            ['종목','등급_v37','등급_v37_1','Δ_체력','BAB_v37','BAB_v37_1','β_60d']]
        if len(impact) > 0:
            print("\n📋 v3.7 → v3.7.1 등급 변동 종목 (BAB 조정 효과):")
            print(impact.to_string(index=False))

    return report


def main():
    args = parse_args()
    print("=" * 78)
    print(f"진우퀀트 3-way 백테스트 (v3.6 vs v3.7 vs v3.7.1)")
    print(f"시간: {datetime.now()}")
    print("=" * 78)

    panel = fetch_long_panel(args.years)
    if panel.get('_KOSPI') is None:
        print("❌ 데이터 수집 실패")
        sys.exit(1)

    run_backtest(panel, args)


if __name__ == '__main__':
    main()
