#!/usr/bin/env python3
"""
진우퀀트 4-way 백테스트: v3.6 vs v3.7 vs v3.7.1 vs v3.8.1

목적: GP/Assets 단독 추가의 한국 18종목 universe에서의 alpha 효과 측정

핵심 비교:
  - v3.6   : F + ModF + FAR + Sloan                     [production baseline]
  - v3.7   : v3.6 + Mom12 + BAB(원본) + NOA             [영역1 1차]
  - v3.7.1 : v3.6 + Mom12 + BAB(완화) + NOA             [영역1 2차, IR 최고]
  - v3.8.1 : v3.7.1 + GP/Assets (3분위, Novy-Marx 2013) [v3.8 시작점]

목표:
  - v3.8.1 연환산 alpha vs v3.6 ≥ -1.0%p (현재 v3.7.1은 -1.57%p)
  - v3.8.1 IR (vs KOSPI) ≥ v3.7.1 의 1.68
  - GP signal이 18종목 대형주 universe에서도 작동하는지 검증

⚠️ 한계:
  - quality_data_cache.json은 단일 시점 (2025 사업보고서) 스냅샷
  - 백테스트 4년 전체에서 동일 GP score 사용 → lookahead bias 발생
  - 실제 production용 시계열 quality 데이터는 v3.8.2 단계에서 보강 예정
  - 본 백테스트는 GP factor의 "현재 시점 quality"가 4년간 일관되게 작동했는지 가정 검증

학술 근거:
  - S1 Novy-Marx (2013) JFE 108
  - S4 안제욱·김규영 (2014) 한국 검증
  - S5 노지혜 외 (2023) 한국 8요인 25년
  - A3 김민기 외 (2018) GP 메커니즘
  - GPT 검증 (2026-05-28): 3분위 + 금융주 별도

실행:
  python3 backtest_4way.py
  python3 backtest_4way.py --years 4 --top-grades S+,S,A
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
# 시점별 4-way 점수
# ============================================
def compute_scores_4way_at(panel, dt, gp_scores):
    """
    각 시점 dt에서 v3.6 / v3.7 / v3.7.1 / v3.8.1 점수 모두 계산.
    gp_scores: {name: int} — 18종목 GP 점수 (단일 시점 cache 기반, 백테스트 전체 동일)
    """
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

        # v3.7·v3.7.1·v3.8.1 공통 신규
        r_mom12 = compute_mom12(s_cut)
        beta60 = compute_beta60(s_cut, k_cut)
        mom_s = mom12_to_score(r_mom12)
        noa_s = noa_to_score(info.get('NOA', 0))

        bab_v37 = bab_to_score_v37(beta60)
        bab_v371 = bab_to_score_v371(beta60)

        # v3.8.1: GP score (백테스트 전체 동일)
        gp_s = gp_scores.get(name, 0)

        total_v36 = base
        total_v37 = base + mom_s + bab_v37 + noa_s
        total_v371 = base + mom_s + bab_v371 + noa_s
        total_v381 = total_v371 + gp_s        # v3.7.1 + GP

        rows.append({
            '종목': name,
            'β_60d': round(beta60, 3) if beta60 is not None else None,
            'Mom12': mom_s,
            'BAB_v37_1': bab_v371,
            'GP': gp_s,
            '체력_v36': round(base, 2),
            '체력_v37': round(total_v37, 2),
            '체력_v37_1': round(total_v371, 2),
            '체력_v38_1': round(total_v381, 2),
            '등급_v36': grade(base),
            '등급_v37': grade(total_v37),
            '등급_v37_1': grade(total_v371),
            '등급_v38_1': grade(total_v381),
        })
    return pd.DataFrame(rows)


# ============================================
# 포트폴리오 수익률 + 메트릭
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
# 4-way 백테스트
# ============================================
def run_backtest(panel, args, gp_scores):
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

    rets_v36, rets_v37, rets_v371, rets_v381, rets_bench = [], [], [], [], []
    n36, n37, n371, n381 = [], [], [], []
    history = []

    for i in range(len(rebal_dates) - 1):
        d0, d1 = rebal_dates[i], rebal_dates[i + 1]
        snap = compute_scores_4way_at(panel, d0, gp_scores)
        if snap is None or len(snap) == 0:
            continue

        picks_v36 = snap[snap['등급_v36'].isin(target_grades)]['종목'].tolist()
        picks_v37 = snap[snap['등급_v37'].isin(target_grades)]['종목'].tolist()
        picks_v371 = snap[snap['등급_v37_1'].isin(target_grades)]['종목'].tolist()
        picks_v381 = snap[snap['등급_v38_1'].isin(target_grades)]['종목'].tolist()

        s_v37 = dict(zip(snap['종목'], snap['체력_v37']))
        s_v371 = dict(zip(snap['종목'], snap['체력_v37_1']))
        s_v381 = dict(zip(snap['종목'], snap['체력_v38_1']))

        r36 = avg_return(picks_v36, panel, d0, d1, args.weights)
        r37 = avg_return(picks_v37, panel, d0, d1, args.weights, s_v37)
        r371 = avg_return(picks_v371, panel, d0, d1, args.weights, s_v371)
        r381 = avg_return(picks_v381, panel, d0, d1, args.weights, s_v381)
        rb = kospi_return(panel, d0, d1)

        rets_v36.append(r36)
        rets_v37.append(r37)
        rets_v371.append(r371)
        rets_v381.append(r381)
        rets_bench.append(rb)
        n36.append(len(picks_v36))
        n37.append(len(picks_v37))
        n371.append(len(picks_v371))
        n381.append(len(picks_v381))

        history.append({
            'date': d0.strftime('%Y-%m-%d'),
            'n_v36': len(picks_v36),
            'n_v37_1': len(picks_v371),
            'n_v38_1': len(picks_v381),
            'r_v36_%': round(r36 * 100, 2),
            'r_v37_1_%': round(r371 * 100, 2),
            'r_v38_1_%': round(r381 * 100, 2),
            'r_kospi_%': round(rb * 100, 2),
            'picks_v37_1': picks_v371,
            'picks_v38_1': picks_v381,
            'only_v38_1_vs_v37_1': sorted(set(picks_v381) - set(picks_v371)),
            'only_v37_1_vs_v38_1': sorted(set(picks_v371) - set(picks_v381)),
        })

    periods_per_year = 12 if args.rebalance == 'M' else 4

    m36 = metrics(rets_v36, periods_per_year)
    m37 = metrics(rets_v37, periods_per_year)
    m371 = metrics(rets_v371, periods_per_year)
    m381 = metrics(rets_v381, periods_per_year)
    mbench = metrics(rets_bench, periods_per_year)

    ir36 = information_ratio(rets_v36, rets_bench, periods_per_year)
    ir37 = information_ratio(rets_v37, rets_bench, periods_per_year)
    ir371 = information_ratio(rets_v371, rets_bench, periods_per_year)
    ir381 = information_ratio(rets_v381, rets_bench, periods_per_year)

    # 출력
    print("\n" + "=" * 84)
    print(f"4-way 백테스트  ({args.years}년 · {args.rebalance} · 등급 {args.top_grades} · {args.weights})")
    print("=" * 84)

    def row(label, m, ir=None):
        print(f"{label:10s} | 누적 {m.get('누적',0):>7.2f}%  연환산 {m.get('연환산',0):>6.2f}%  "
              f"vol {m.get('변동성',0):>5.2f}%  Sharpe {str(m.get('Sharpe','-')):>5s}  "
              f"MDD {m.get('MDD',0):>6.2f}%  IR {str(ir if ir else '-'):>5s}  "
              f"승률 {m.get('승률',0):>5.1f}%")

    row("v3.6", m36, ir36)
    row("v3.7", m37, ir37)
    row("v3.7.1", m371, ir371)
    row("v3.8.1", m381, ir381)
    row("KOSPI", mbench)

    print(f"\n평균 보유 종목 수:")
    print(f"  v3.6   {np.mean(n36):.1f}")
    print(f"  v3.7   {np.mean(n37):.1f}")
    print(f"  v3.7.1 {np.mean(n371):.1f}")
    print(f"  v3.8.1 {np.mean(n381):.1f}")

    print(f"\n연환산 alpha (vs v3.6):")
    print(f"  v3.7   : {m37.get('연환산',0) - m36.get('연환산',0):+.2f}%p/년")
    print(f"  v3.7.1 : {m371.get('연환산',0) - m36.get('연환산',0):+.2f}%p/년")
    print(f"  v3.8.1 : {m381.get('연환산',0) - m36.get('연환산',0):+.2f}%p/년  ⭐")

    print(f"\n연환산 alpha vs v3.7.1 (GP 단독 효과):")
    print(f"  v3.8.1 vs v3.7.1: {m381.get('연환산',0) - m371.get('연환산',0):+.2f}%p/년")

    print(f"\n연환산 alpha (vs KOSPI):")
    print(f"  v3.6   : {m36.get('연환산',0) - mbench.get('연환산',0):+.2f}%p/년")
    print(f"  v3.7   : {m37.get('연환산',0) - mbench.get('연환산',0):+.2f}%p/년")
    print(f"  v3.7.1 : {m371.get('연환산',0) - mbench.get('연환산',0):+.2f}%p/년")
    print(f"  v3.8.1 : {m381.get('연환산',0) - mbench.get('연환산',0):+.2f}%p/년  ⭐")

    # GP factor 진단
    gp_pos = [n for n, s in gp_scores.items() if s == +1]
    gp_neg = [n for n, s in gp_scores.items() if s == -1]
    print(f"\n📋 GP 점수 분포 (단일 시점 cache):")
    print(f"  GP=+1 ({len(gp_pos)}): {', '.join(gp_pos)}")
    print(f"  GP=-1 ({len(gp_neg)}): {', '.join(gp_neg)}")

    print(f"\n⚠️ 한계: quality_data_cache.json은 단일 시점 (2025 사업보고서).")
    print(f"   백테스트 4년간 동일 GP score 적용 → lookahead bias 존재.")
    print(f"   실제 production은 v3.8.2 단계에서 시계열 quality 데이터 보강 필요.")

    # 저장
    report = {
        'timestamp': datetime.now().isoformat(),
        'config': vars(args),
        'metrics': {'v36': m36, 'v37': m37, 'v37_1': m371,
                    'v38_1': m381, 'kospi': mbench},
        'ir': {'v36': ir36, 'v37': ir37, 'v37_1': ir371, 'v38_1': ir381},
        'gp_scores': gp_scores,
        'avg_picks': {
            'v36': float(np.mean(n36)),
            'v37': float(np.mean(n37)),
            'v37_1': float(np.mean(n371)),
            'v38_1': float(np.mean(n381)),
        },
        'history': history,
        'caveat': 'GP scores are single-point (2025) snapshot used throughout backtest — lookahead bias',
    }
    out_path = BASE / f'backtest_4way_{datetime.now().strftime("%Y%m%d_%H%M")}.json'
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                   default=str),
                        encoding='utf-8')
    print(f"\n💾 리포트 저장: {out_path}")

    return report


def main():
    args = parse_args()
    print("=" * 84)
    print(f"진우퀀트 4-way 백테스트 (v3.6 vs v3.7 vs v3.7.1 vs v3.8.1)")
    print(f"시간: {datetime.now()}")
    print("=" * 84)

    # GP scores 준비 (단일 시점)
    quality_data = load_quality_data()
    gp_scores = compute_gp_scores(quality_data)
    print(f"\n📁 GP scores 로드: {sum(1 for s in gp_scores.values() if s == +1)}개 +1, "
          f"{sum(1 for s in gp_scores.values() if s == -1)}개 -1")

    panel = fetch_long_panel(args.years)
    if panel.get('_KOSPI') is None:
        print("❌ 데이터 수집 실패")
        sys.exit(1)

    run_backtest(panel, args, gp_scores)


if __name__ == '__main__':
    main()
