#!/usr/bin/env python3
"""
진우퀀트 6-way 백테스트:
  v3.6 / v3.7 / v3.7.1 / v3.8.1 / v3.8.2 / v3.8.3

목적: Echo Momentum (보조 실험) 추가 효과 측정

핵심:
  - v3.8.1·v3.8.2 (단일 시점 quality cache 사용)는 lookahead bias 한계 확인됨
  - v3.8.3 Echo는 가격 데이터만 사용 → bias 없음, 가장 정직한 검증
  - GPT 권장: ±0.5 저가중치, 보조 실험군

학술 근거:
  - S3 Novy-Marx 2012 Echo (t-12~t-7)
  - S6 장지원 2017 한국 검증 (월 1.51%)
  - A5 엄철준 2024 tail risk

실행:
  python3 backtest_6way.py
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
from score_v38_3 import compute_echo, ECHO_WEIGHT


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


def compute_echo_at(series_cut, days_per_month=21):
    """특정 시점까지의 시계열로 Echo 계산"""
    if series_cut is None or len(series_cut) < 253:
        return None
    p_t12 = series_cut.iloc[-12 * days_per_month]
    p_t7 = series_cut.iloc[-7 * days_per_month]
    if p_t12 is None or p_t12 == 0:
        return None
    return float(p_t7 / p_t12 - 1)


def compute_echo_scores_at(panel, dt):
    """시점 dt에서의 Echo 3분위 점수 (시간 가변 — bias 없음)"""
    echo_values = {}
    for name in JINWOO_v37:
        series = panel.get(name)
        if series is None:
            continue
        s_cut = series[series.index <= dt]
        v = compute_echo_at(s_cut)
        if v is not None:
            echo_values[name] = v

    if not echo_values:
        return {name: 0 for name in JINWOO_v37}

    n = len(echo_values)
    upper_n = max(1, round(n * 0.2))
    lower_n = max(1, round(n * 0.2))

    sorted_desc = pd.Series(echo_values).sort_values(ascending=False)
    upper_threshold = sorted_desc.iloc[upper_n - 1]
    lower_threshold = sorted_desc.iloc[-lower_n]

    scores = {}
    for name in JINWOO_v37:
        v = echo_values.get(name)
        if v is None:
            scores[name] = 0
        elif v >= upper_threshold:
            scores[name] = +1
        elif v <= lower_threshold:
            scores[name] = -1
        else:
            scores[name] = 0
    return scores


def compute_scores_6way_at(panel, dt, gp_scores, ag_scores):
    kospi = panel.get('_KOSPI')
    if kospi is None:
        return None

    # Echo는 시점별 동적 계산 (시간 가변, bias 없음)
    echo_scores = compute_echo_scores_at(panel, dt)

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
        echo_s = echo_scores.get(name, 0) * ECHO_WEIGHT

        total_v36 = base
        total_v37 = base + mom_s + bab_v37 + noa_s
        total_v371 = base + mom_s + bab_v371 + noa_s
        total_v381 = total_v371 + gp_s
        total_v382 = total_v371 + gp_s + ag_s
        total_v383 = total_v371 + gp_s + ag_s + echo_s

        rows.append({
            '종목': name,
            'GP': gp_s, 'AG': ag_s, 'Echo': echo_s,
            '체력_v36': round(total_v36, 2),
            '체력_v37': round(total_v37, 2),
            '체력_v37_1': round(total_v371, 2),
            '체력_v38_1': round(total_v381, 2),
            '체력_v38_2': round(total_v382, 2),
            '체력_v38_3': round(total_v383, 2),
            '등급_v36': grade(total_v36),
            '등급_v37': grade(total_v37),
            '등급_v37_1': grade(total_v371),
            '등급_v38_1': grade(total_v381),
            '등급_v38_2': grade(total_v382),
            '등급_v38_3': grade(total_v383),
        })
    return pd.DataFrame(rows)


def avg_return(picks, panel, dt_start, dt_end, weights='equal'):
    if len(picks) == 0:
        return 0.0
    rets = []
    for name in picks:
        s = panel.get(name)
        if s is None: continue
        s_window = s[(s.index > dt_start) & (s.index <= dt_end)]
        if len(s_window) < 2: continue
        r = s_window.iloc[-1] / s_window.iloc[0] - 1
        rets.append(r)
    if not rets: return 0.0
    return float(np.mean(rets))


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
    end_dt = k.index[-1]
    start_dt = end_dt - pd.DateOffset(years=args.years)
    backtest_period = k[(k.index >= start_dt) & (k.index <= end_dt)]
    rebal_dates = backtest_period.resample('MS' if args.rebalance == 'M' else 'QS').first().dropna().index
    rebal_dates = [k.index[k.index.get_indexer([d], method='bfill')[0]]
                   for d in rebal_dates if d <= end_dt]
    rebal_dates = sorted(set(rebal_dates))
    if rebal_dates[-1] < end_dt:
        rebal_dates.append(end_dt)

    print(f"\n🔁 Rebalance: {len(rebal_dates)-1}회")

    rets = {k_: [] for k_ in ['36', '37', '371', '381', '382', '383', 'b']}
    npicks = {k_: [] for k_ in ['36', '37', '371', '381', '382', '383']}
    history = []

    for i in range(len(rebal_dates) - 1):
        d0, d1 = rebal_dates[i], rebal_dates[i + 1]
        snap = compute_scores_6way_at(panel, d0, gp_scores, ag_scores)
        if snap is None or len(snap) == 0:
            continue
        for v_id, col in [('36', '등급_v36'), ('37', '등급_v37'),
                          ('371', '등급_v37_1'), ('381', '등급_v38_1'),
                          ('382', '등급_v38_2'), ('383', '등급_v38_3')]:
            picks = snap[snap[col].isin(target_grades)]['종목'].tolist()
            r = avg_return(picks, panel, d0, d1, args.weights)
            rets[v_id].append(r)
            npicks[v_id].append(len(picks))
        rets['b'].append(kospi_return(panel, d0, d1))

        history.append({
            'date': d0.strftime('%Y-%m-%d'),
            'r_v37_1_%': round(rets['371'][-1] * 100, 2),
            'r_v38_3_%': round(rets['383'][-1] * 100, 2),
        })

    ppy = 12 if args.rebalance == 'M' else 4
    m = {k_: metrics(rets[k_], ppy) for k_ in ['36', '37', '371', '381', '382', '383', 'b']}
    ir = {k_: information_ratio(rets[k_], rets['b'], ppy)
          for k_ in ['36', '37', '371', '381', '382', '383']}

    print("\n" + "=" * 90)
    print(f"6-way 백테스트  ({args.years}년 · {args.rebalance} · 등급 {args.top_grades})")
    print("=" * 90)

    def row(label, m_, ir_=None):
        print(f"{label:10s} | 누적 {m_.get('누적',0):>7.2f}%  연환산 {m_.get('연환산',0):>6.2f}%  "
              f"vol {m_.get('변동성',0):>5.2f}%  Sharpe {str(m_.get('Sharpe','-')):>5s}  "
              f"MDD {m_.get('MDD',0):>6.2f}%  IR {str(ir_ if ir_ else '-'):>5s}  "
              f"승률 {m_.get('승률',0):>5.1f}%")

    row("v3.6", m['36'], ir['36'])
    row("v3.7", m['37'], ir['37'])
    row("v3.7.1", m['371'], ir['371'])
    row("v3.8.1", m['381'], ir['381'])
    row("v3.8.2", m['382'], ir['382'])
    row("v3.8.3", m['383'], ir['383'])
    row("KOSPI", m['b'])

    print(f"\n평균 보유 종목 수:")
    for v_id, label in [('371', 'v3.7.1'), ('381', 'v3.8.1'),
                         ('382', 'v3.8.2'), ('383', 'v3.8.3')]:
        print(f"  {label}: {np.mean(npicks[v_id]):.1f}")

    print(f"\n연환산 alpha (vs v3.6):")
    for v_id, label in [('371', 'v3.7.1'), ('381', 'v3.8.1'),
                         ('382', 'v3.8.2'), ('383', 'v3.8.3')]:
        delta = m[v_id].get('연환산', 0) - m['36'].get('연환산', 0)
        mark = " ⭐" if v_id == '383' else ""
        print(f"  {label}: {delta:+.2f}%p{mark}")

    print(f"\n연환산 alpha (vs v3.7.1, Echo 단독 효과):")
    delta_echo = m['383'].get('연환산', 0) - m['382'].get('연환산', 0)
    print(f"  v3.8.3 vs v3.8.2 (Echo 추가): {delta_echo:+.2f}%p")

    # 최근 시점 Echo 분포
    last_snap = compute_scores_6way_at(panel, rebal_dates[-2], gp_scores, ag_scores)
    if last_snap is not None:
        echo_pos = last_snap[last_snap['Echo'] > 0]['종목'].tolist()
        echo_neg = last_snap[last_snap['Echo'] < 0]['종목'].tolist()
        print(f"\n📋 최근 시점 Echo 분포 (시간 가변, 매월 다름):")
        print(f"  Echo>0: {', '.join(echo_pos)}")
        print(f"  Echo<0: {', '.join(echo_neg)}")

    report = {
        'timestamp': datetime.now().isoformat(),
        'config': vars(args),
        'metrics': m,
        'ir': ir,
        'avg_picks': {k_: float(np.mean(v)) for k_, v in npicks.items()},
        'echo_note': 'Echo는 시간 가변 계산 (lookahead bias 없음)',
        'history': history,
    }
    out = BASE / f'backtest_6way_{datetime.now().strftime("%Y%m%d_%H%M")}.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str),
                   encoding='utf-8')
    print(f"\n💾 리포트 저장: {out}")
    return report


def main():
    args = parse_args()
    print("=" * 90)
    print("진우퀀트 6-way 백테스트 (v3.6 ~ v3.8.3)")
    print(f"시간: {datetime.now()}")
    print("=" * 90)

    quality_data = load_quality_data()
    gp_scores = compute_gp_scores(quality_data)
    ag_scores = compute_ag_scores(quality_data)
    print(f"\n📁 GP·AG: 단일 시점 cache (lookahead bias 한계)")
    print(f"📁 Echo: 시간 가변 (각 시점에서 계산, bias 없음)")

    panel = fetch_long_panel(args.years)
    if panel.get('_KOSPI') is None:
        sys.exit(1)
    run_backtest(panel, args, gp_scores, ag_scores)


if __name__ == '__main__':
    main()
