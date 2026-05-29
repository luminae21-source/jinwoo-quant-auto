#!/usr/bin/env python3
"""
진우퀀트 5-way 백테스트: v3.6 vs v3.7 vs v3.7.1 vs v3.8.1 vs v3.8.2

목적: GP+AG 결합의 한국 18종목 universe alpha 효과 측정

핵심:
  - v3.8.1 (GP 단독)이 -1.07%p/년 실패 → v3.8.2 (GP+AG) 검증
  - GPT 권장 production 후보: v3.8.2 (GP+AG)
  - 노지혜 외 2023 한국 25년 robust 확인: 수익성·투자 결합

⚠️ 한계 (v3.8.1과 동일):
  - quality_data_cache.json 단일 시점 → 4년 lookahead bias
  - v3.8.2 실패 시 시계열 quality 데이터 보강 필요

학술 근거:
  - S1 Novy-Marx 2013 (GP)
  - S2 Cooper-Gulen-Schill 2008 (AG)
  - S5 노지혜 외 2023 (한국 결합 효과)

실행:
  python3 backtest_5way.py
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

from score_v37 import (
    JINWOO_v37, KOSPI_CODE,
    compute_mom12, compute_beta60,
    mom12_to_score, noa_to_score,
    far_trigger, grade,
    bab_to_score as bab_to_score_v37,
)
from score_v37_1 import bab_to_score as bab_to_score_v371
from score_v38_1 import load_quality_data, compute_gp_scores
from score_v38_2 import compute_ag_scores, GP_WEIGHT, AG_WEIGHT


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--years', type=int, default=4)
    p.add_argument('--top-grades', type=str, default='S+,S,A')
    p.add_argument('--weights', choices=['equal', 'score'], default='equal')
    p.add_argument('--rebalance', choices=['M', 'Q'], default='M')
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
    print(f"\n📊 백테스트 데이터 수집 ({start.date()} → {end.date()}):")
    df = fdr.DataReader(KOSPI_CODE, start.strftime('%Y-%m-%d'),
                        end.strftime('%Y-%m-%d'))
    panel['_KOSPI'] = df['Close']
    print(f"  KOSPI: {len(df)} 영업일")
    for name, info in JINWOO_v37.items():
        try:
            df = fdr.DataReader(info['코드'], start.strftime('%Y-%m-%d'),
                                end.strftime('%Y-%m-%d'))
            panel[name] = df['Close']
        except Exception:
            panel[name] = None
    return panel


def compute_scores_5way_at(panel, dt, gp_scores, ag_scores):
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

        체력_12점 = info['F_korean'] * (12 / 9.001)
        if len(s_cut) >= 22:
            r_1m = s_cut.iloc[-1] / s_cut.iloc[-21] - 1
        else:
            r_1m = None
        far_val, _ = far_trigger(체력_12점, r_1m)
        base = 체력_12점 + info['ModF'] + far_val + info['Sloan']

        r_mom12 = compute_mom12(s_cut)
        beta60 = compute_beta60(s_cut, k_cut)
        mom_s = mom12_to_score(r_mom12)
        noa_s = noa_to_score(info.get('NOA', 0))

        bab_v37 = bab_to_score_v37(beta60)
        bab_v371 = bab_to_score_v371(beta60)

        gp_s = gp_scores.get(name, 0) * GP_WEIGHT
        ag_s = ag_scores.get(name, 0) * AG_WEIGHT

        total_v36 = base
        total_v37 = base + mom_s + bab_v37 + noa_s
        total_v371 = base + mom_s + bab_v371 + noa_s
        total_v381 = total_v371 + gp_s            # v3.8.1 = v3.7.1 + GP
        total_v382 = total_v371 + gp_s + ag_s     # v3.8.2 = v3.7.1 + GP + AG

        rows.append({
            '종목': name,
            'β_60d': round(beta60, 3) if beta60 is not None else None,
            'GP': gp_s, 'AG': ag_s,
            '체력_v36': round(total_v36, 2),
            '체력_v37': round(total_v37, 2),
            '체력_v37_1': round(total_v371, 2),
            '체력_v38_1': round(total_v381, 2),
            '체력_v38_2': round(total_v382, 2),
            '등급_v36': grade(total_v36),
            '등급_v37': grade(total_v37),
            '등급_v37_1': grade(total_v371),
            '등급_v38_1': grade(total_v381),
            '등급_v38_2': grade(total_v382),
        })
    return pd.DataFrame(rows)


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


def run_backtest(panel, args, gp_scores, ag_scores):
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

    print(f"\n🔁 Rebalance: {len(rebal_dates)-1}회 "
          f"({rebal_dates[0].date()} → {rebal_dates[-1].date()})")

    rets_36, rets_37, rets_371, rets_381, rets_382, rets_b = [], [], [], [], [], []
    n36, n37, n371, n381, n382 = [], [], [], [], []
    history = []

    for i in range(len(rebal_dates) - 1):
        d0, d1 = rebal_dates[i], rebal_dates[i + 1]
        snap = compute_scores_5way_at(panel, d0, gp_scores, ag_scores)
        if snap is None or len(snap) == 0:
            continue
        p36 = snap[snap['등급_v36'].isin(target_grades)]['종목'].tolist()
        p37 = snap[snap['등급_v37'].isin(target_grades)]['종목'].tolist()
        p371 = snap[snap['등급_v37_1'].isin(target_grades)]['종목'].tolist()
        p381 = snap[snap['등급_v38_1'].isin(target_grades)]['종목'].tolist()
        p382 = snap[snap['등급_v38_2'].isin(target_grades)]['종목'].tolist()

        r36 = avg_return(p36, panel, d0, d1, args.weights)
        r37 = avg_return(p37, panel, d0, d1, args.weights)
        r371 = avg_return(p371, panel, d0, d1, args.weights)
        r381 = avg_return(p381, panel, d0, d1, args.weights)
        r382 = avg_return(p382, panel, d0, d1, args.weights)
        rb = kospi_return(panel, d0, d1)

        rets_36.append(r36); rets_37.append(r37); rets_371.append(r371)
        rets_381.append(r381); rets_382.append(r382); rets_b.append(rb)
        n36.append(len(p36)); n37.append(len(p37)); n371.append(len(p371))
        n381.append(len(p381)); n382.append(len(p382))

        history.append({
            'date': d0.strftime('%Y-%m-%d'),
            'n_v37_1': len(p371), 'n_v38_1': len(p381), 'n_v38_2': len(p382),
            'r_v37_1_%': round(r371 * 100, 2),
            'r_v38_1_%': round(r381 * 100, 2),
            'r_v38_2_%': round(r382 * 100, 2),
            'picks_v38_2': p382,
            'only_v38_2_vs_v37_1': sorted(set(p382) - set(p371)),
            'only_v37_1_vs_v38_2': sorted(set(p371) - set(p382)),
        })

    ppy = 12 if args.rebalance == 'M' else 4
    m36 = metrics(rets_36, ppy); m37 = metrics(rets_37, ppy)
    m371 = metrics(rets_371, ppy); m381 = metrics(rets_381, ppy)
    m382 = metrics(rets_382, ppy); mb = metrics(rets_b, ppy)
    ir36 = information_ratio(rets_36, rets_b, ppy)
    ir37 = information_ratio(rets_37, rets_b, ppy)
    ir371 = information_ratio(rets_371, rets_b, ppy)
    ir381 = information_ratio(rets_381, rets_b, ppy)
    ir382 = information_ratio(rets_382, rets_b, ppy)

    print("\n" + "=" * 90)
    print(f"5-way 백테스트  ({args.years}년 · {args.rebalance} · 등급 {args.top_grades})")
    print("=" * 90)

    def row(label, m, ir=None):
        print(f"{label:10s} | 누적 {m.get('누적',0):>7.2f}%  연환산 {m.get('연환산',0):>6.2f}%  "
              f"vol {m.get('변동성',0):>5.2f}%  Sharpe {str(m.get('Sharpe','-')):>5s}  "
              f"MDD {m.get('MDD',0):>6.2f}%  IR {str(ir if ir else '-'):>5s}  "
              f"승률 {m.get('승률',0):>5.1f}%")

    row("v3.6", m36, ir36)
    row("v3.7", m37, ir37)
    row("v3.7.1", m371, ir371)
    row("v3.8.1", m381, ir381)
    row("v3.8.2", m382, ir382)
    row("KOSPI", mb)

    print(f"\n평균 보유 종목 수:")
    print(f"  v3.7.1 {np.mean(n371):.1f} | v3.8.1 {np.mean(n381):.1f} | v3.8.2 {np.mean(n382):.1f}")

    print(f"\n연환산 alpha (vs v3.6, 목표 ≥ -1.0%p):")
    print(f"  v3.7.1 : {m371.get('연환산',0) - m36.get('연환산',0):+.2f}%p")
    print(f"  v3.8.1 : {m381.get('연환산',0) - m36.get('연환산',0):+.2f}%p")
    print(f"  v3.8.2 : {m382.get('연환산',0) - m36.get('연환산',0):+.2f}%p  ⭐")

    print(f"\n연환산 alpha (vs v3.7.1, GP·AG 단일 효과):")
    print(f"  v3.8.1 (GP 단독): {m381.get('연환산',0) - m371.get('연환산',0):+.2f}%p")
    print(f"  v3.8.2 (GP+AG):   {m382.get('연환산',0) - m371.get('연환산',0):+.2f}%p")

    print(f"\n연환산 alpha (vs v3.8.1, AG 추가 효과):")
    print(f"  v3.8.2 vs v3.8.1: {m382.get('연환산',0) - m381.get('연환산',0):+.2f}%p")

    # AG 점수 분포
    ag_pos = [n for n, s in ag_scores.items() if s == +1]
    ag_neg = [n for n, s in ag_scores.items() if s == -1]
    print(f"\n📋 AG 점수 분포 (낮은 자산성장 +1, 높은 -1):")
    print(f"  AG=+1 ({len(ag_pos)}): {', '.join(ag_pos)}")
    print(f"  AG=-1 ({len(ag_neg)}): {', '.join(ag_neg)}")

    # GP+AG 결합 점수
    print(f"\n📋 GP+AG 결합 (단일 시점, lookahead bias 주의):")
    combined = {n: gp_scores.get(n, 0) + ag_scores.get(n, 0) for n in JINWOO_v37}
    for score in sorted(set(combined.values()), reverse=True):
        names = [n for n, v in combined.items() if v == score]
        print(f"  GP+AG={score:+}: {', '.join(names)}")

    report = {
        'timestamp': datetime.now().isoformat(),
        'config': vars(args),
        'metrics': {'v36': m36, 'v37': m37, 'v37_1': m371,
                    'v38_1': m381, 'v38_2': m382, 'kospi': mb},
        'ir': {'v36': ir36, 'v37': ir37, 'v37_1': ir371,
               'v38_1': ir381, 'v38_2': ir382},
        'gp_scores': gp_scores,
        'ag_scores': ag_scores,
        'avg_picks': {
            'v36': float(np.mean(n36)), 'v37_1': float(np.mean(n371)),
            'v38_1': float(np.mean(n381)), 'v38_2': float(np.mean(n382)),
        },
        'history': history,
        'caveat': 'GP·AG scores single-point — 4-year lookahead bias acknowledged',
    }
    out = BASE / f'backtest_5way_{datetime.now().strftime("%Y%m%d_%H%M")}.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str),
                   encoding='utf-8')
    print(f"\n💾 리포트 저장: {out}")
    return report


def main():
    args = parse_args()
    print("=" * 90)
    print("진우퀀트 5-way 백테스트 (v3.6 vs v3.7 vs v3.7.1 vs v3.8.1 vs v3.8.2)")
    print(f"시간: {datetime.now()}")
    print("=" * 90)

    quality_data = load_quality_data()
    gp_scores = compute_gp_scores(quality_data)
    ag_scores = compute_ag_scores(quality_data)
    print(f"\n📁 Quality: GP +1 {sum(1 for s in gp_scores.values() if s==+1)}/-1 "
          f"{sum(1 for s in gp_scores.values() if s==-1)}, "
          f"AG +1 {sum(1 for s in ag_scores.values() if s==+1)}/-1 "
          f"{sum(1 for s in ag_scores.values() if s==-1)}")

    panel = fetch_long_panel(args.years)
    if panel.get('_KOSPI') is None:
        sys.exit(1)
    run_backtest(panel, args, gp_scores, ag_scores)


if __name__ == '__main__':
    main()
