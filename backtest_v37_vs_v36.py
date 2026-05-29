#!/usr/bin/env python3
"""
진우퀀트 v3.7 vs v3.6 백테스트

목적: Mom12 + BAB + NOA 추가 시 추가 alpha 검증
방법: 4년 OOS, 월간 rebalance, S+/S/A 등급 동일가중 포트폴리오 비교

⚠️ 알려진 한계 (look-ahead bias):
  - F_korean, ModF, Sloan, NOA 값은 현재(2026-05) 기준 정적 사용
  - 즉 "현재 시스템을 4년 전부터 적용했다면" 시뮬레이션
  - 시점별 F-score history가 있으면 정식 walk-forward 가능 (영역 4 attribution 단계에서)
  - Mom12와 BAB는 시점별 시계열로 계산하므로 OOS 신호

실행:
  python3 backtest_v37_vs_v36.py
  python3 backtest_v37_vs_v36.py --years 4 --top-grades S+,S,A
  python3 backtest_v37_vs_v36.py --weights equal       # 또는 score (체력 가중)
"""

import sys
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np

BASE = Path(__file__).parent.resolve()

# v3.7 종목 dict 재사용
sys.path.insert(0, str(BASE))
from score_v37 import (
    JINWOO_v37, KOSPI_CODE,
    compute_mom12, compute_beta60,
    mom12_to_score, bab_to_score, noa_to_score,
    far_trigger, grade,
)


# ============================================
# 인자 파싱
# ============================================
def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--years', type=int, default=4)
    p.add_argument('--top-grades', type=str, default='S+,S,A',
                   help='보유할 등급 (쉼표 구분)')
    p.add_argument('--weights', choices=['equal', 'score'], default='equal')
    p.add_argument('--rebalance', choices=['M', 'Q'], default='M',
                   help='M=월별, Q=분기별')
    return p.parse_args()


# ============================================
# 데이터 수집
# ============================================
def fetch_long_panel(years=4):
    """4년치 18종목 + KOSPI 일별 종가"""
    try:
        import FinanceDataReader as fdr
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, '-m', 'pip', 'install',
                               '-q', 'finance-datareader'])
        import FinanceDataReader as fdr

    end = datetime.now()
    # 12M lookback 필요하므로 years + 1 buffer
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
# 시점별 점수 계산
# ============================================
def compute_scores_at(panel, dt, use_v37=True):
    """
    특정 시점(dt)에서 18종목 점수 산출.
    panel은 일별 series dict. dt 이하 데이터만 사용.
    """
    kospi = panel.get('_KOSPI')
    if kospi is None:
        return None

    rows = []
    for name, info in JINWOO_v37.items():
        series = panel.get(name)
        if series is None or len(series) == 0:
            continue

        # dt 이하로 잘라서 사용 (no look-ahead on price)
        s_cut = series[series.index <= dt]
        k_cut = kospi[kospi.index <= dt]
        if len(s_cut) < 253:
            continue

        # v3.6 핵심
        체력_12점 = info['F_korean'] * (12 / 9.001)
        # 1M return
        if len(s_cut) >= 22:
            r_1m = s_cut.iloc[-1] / s_cut.iloc[-21] - 1
        else:
            r_1m = None
        far_val, _ = far_trigger(체력_12점, r_1m)

        # v3.7 신규
        if use_v37:
            r_mom12 = compute_mom12(s_cut)
            beta60 = compute_beta60(s_cut, k_cut)
            mom_s = mom12_to_score(r_mom12)
            bab_s = bab_to_score(beta60)
            noa_s = noa_to_score(info.get('NOA', 0))
        else:
            mom_s = bab_s = noa_s = 0

        base = 체력_12점 + info['ModF'] + far_val + info['Sloan']
        total = base + mom_s + bab_s + noa_s

        rows.append({
            '종목': name,
            '체력_v36': round(base, 2),
            '등급_v36': grade(base),
            '체력_v37': round(total, 2),
            '등급_v37': grade(total),
            'Mom12': mom_s, 'BAB': bab_s, 'NOA': noa_s,
        })
    return pd.DataFrame(rows)


# ============================================
# 포트폴리오 수익률
# ============================================
def avg_return(picks, panel, dt_start, dt_end, weights='equal', scores=None,
               return_detail=False):
    """선택된 종목들의 dt_start → dt_end 평균 수익률

    return_detail=True 시 (총수익률, [(종목, r, weight, contribution)...]) 반환.
    contribution = (r * w) / sum(w) — 포트폴리오 수익에 기여한 %p.
    """
    if len(picks) == 0:
        return (0.0, []) if return_detail else 0.0
    rets, ws, names = [], [], []
    for name in picks:
        s = panel.get(name)
        if s is None:
            continue
        s_window = s[(s.index > dt_start) & (s.index <= dt_end)]
        if len(s_window) < 2:
            continue
        r = s_window.iloc[-1] / s_window.iloc[0] - 1
        rets.append(r)
        names.append(name)
        if weights == 'score' and scores is not None and name in scores:
            ws.append(max(scores[name], 0.1))
        else:
            ws.append(1.0)
    if not rets:
        return (0.0, []) if return_detail else 0.0
    rets_a, ws_a = np.array(rets), np.array(ws)
    total_w = float(np.sum(ws_a))
    port_r = float(np.sum(rets_a * ws_a) / total_w)
    if return_detail:
        detail = [
            {
                'name': names[i],
                'r_pct': round(float(rets_a[i]) * 100, 2),
                'weight': round(float(ws_a[i]) / total_w, 4),
                'contrib_pct': round(float(rets_a[i]) * float(ws_a[i]) / total_w * 100, 2),
            }
            for i in range(len(names))
        ]
        return port_r, detail
    return port_r


def kospi_return(panel, dt_start, dt_end):
    k = panel.get('_KOSPI')
    if k is None:
        return 0.0
    k_window = k[(k.index > dt_start) & (k.index <= dt_end)]
    if len(k_window) < 2:
        return 0.0
    return float(k_window.iloc[-1] / k_window.iloc[0] - 1)


# ============================================
# 메트릭
# ============================================
def metrics(monthly_rets, periods_per_year=12):
    """월간 수익률 → 연환산 지표"""
    arr = np.array(monthly_rets)
    if len(arr) == 0:
        return {}
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
    if len(excess) < 2:
        return None
    ann_excess = excess.mean() * periods_per_year
    te = excess.std() * np.sqrt(periods_per_year)
    if te == 0:
        return None
    return round(float(ann_excess / te), 2)


# ============================================
# 백테스트 메인
# ============================================
def run_backtest(panel, args):
    target_grades = set(args.top_grades.split(','))

    # rebalance dates 생성
    k = panel.get('_KOSPI')
    if k is None or len(k) == 0:
        print("❌ KOSPI 데이터 없음 — 백테스트 불가")
        return None

    end_dt = k.index[-1]
    start_dt = end_dt - pd.DateOffset(years=args.years)
    backtest_period = k[(k.index >= start_dt) & (k.index <= end_dt)]

    if args.rebalance == 'M':
        rebal_dates = backtest_period.resample('MS').first().dropna().index
    else:
        rebal_dates = backtest_period.resample('QS').first().dropna().index

    # 가장 가까운 영업일로 맞춤
    rebal_dates = [k.index[k.index.get_indexer([d], method='bfill')[0]]
                   for d in rebal_dates if d <= end_dt]
    rebal_dates = sorted(set(rebal_dates))
    if rebal_dates[-1] < end_dt:
        rebal_dates.append(end_dt)

    print(f"\n🔁 Rebalance: {len(rebal_dates)-1}회 ({rebal_dates[0].date()} → {rebal_dates[-1].date()})")

    rets_v36, rets_v37, rets_bench = [], [], []
    n_picks_v36, n_picks_v37 = [], []
    history = []

    for i in range(len(rebal_dates) - 1):
        d0, d1 = rebal_dates[i], rebal_dates[i + 1]
        snap = compute_scores_at(panel, d0, use_v37=True)
        if snap is None or len(snap) == 0:
            continue

        picks_v36 = snap[snap['등급_v36'].isin(target_grades)]['종목'].tolist()
        picks_v37 = snap[snap['등급_v37'].isin(target_grades)]['종목'].tolist()

        scores_v37 = dict(zip(snap['종목'], snap['체력_v37']))

        r36, det36 = avg_return(picks_v36, panel, d0, d1, args.weights, scores_v37,
                                return_detail=True)
        r37, det37 = avg_return(picks_v37, panel, d0, d1, args.weights, scores_v37,
                                return_detail=True)
        rb = kospi_return(panel, d0, d1)

        rets_v36.append(r36)
        rets_v37.append(r37)
        rets_bench.append(rb)
        n_picks_v36.append(len(picks_v36))
        n_picks_v37.append(len(picks_v37))

        # 종목 비교: v36 only / v37 only / both
        only_v36 = sorted(set(picks_v36) - set(picks_v37))
        only_v37 = sorted(set(picks_v37) - set(picks_v36))
        both = sorted(set(picks_v36) & set(picks_v37))

        history.append({
            'date': d0.strftime('%Y-%m-%d'),
            'n_v36': len(picks_v36),
            'n_v37': len(picks_v37),
            'r_v36_%': round(r36 * 100, 2),
            'r_v37_%': round(r37 * 100, 2),
            'r_kospi_%': round(rb * 100, 2),
            'picks_v36': picks_v36,
            'picks_v37': picks_v37,
            'only_v36': only_v36,   # v36엔 있지만 v37에서 빠진 (BAB·Mom 페널티)
            'only_v37': only_v37,   # v37에서 추가된
            'both': both,
            'detail_v36': det36,    # 종목별 r/weight/contribution
            'detail_v37': det37,
        })

    periods_per_year = 12 if args.rebalance == 'M' else 4

    m36 = metrics(rets_v36, periods_per_year)
    m37 = metrics(rets_v37, periods_per_year)
    mbench = metrics(rets_bench, periods_per_year)

    ir36 = information_ratio(rets_v36, rets_bench, periods_per_year)
    ir37 = information_ratio(rets_v37, rets_bench, periods_per_year)

    # 출력
    print("\n" + "=" * 70)
    print(f"백테스트 결과  ({args.years}년 · {args.rebalance} 리밸런스 · 등급 {args.top_grades} · {args.weights} 가중)")
    print("=" * 70)

    def row(label, m, ir=None):
        print(f"{label:10s} | 누적 {m.get('누적',0):>7.2f}%  연환산 {m.get('연환산',0):>6.2f}%  "
              f"vol {m.get('변동성',0):>5.2f}%  Sharpe {str(m.get('Sharpe','-')):>5s}  "
              f"MDD {m.get('MDD',0):>6.2f}%  IR {str(ir if ir else '-'):>5s}  "
              f"승률 {m.get('승률',0):>5.1f}%")

    row("v3.6", m36, ir36)
    row("v3.7", m37, ir37)
    row("KOSPI", mbench)

    print(f"\n평균 보유 종목 수: v3.6 {np.mean(n_picks_v36):.1f} / v3.7 {np.mean(n_picks_v37):.1f}")
    print(f"v3.7 추가 alpha (v3.6 대비): {(m37.get('연환산',0) - m36.get('연환산',0)):+.2f}%p/년")
    print(f"v3.7 추가 alpha (KOSPI 대비): {(m37.get('연환산',0) - mbench.get('연환산',0)):+.2f}%p/년")

    # 저장
    report = {
        'timestamp': datetime.now().isoformat(),
        'config': vars(args),
        'metrics': {'v36': m36, 'v37': m37, 'kospi': mbench},
        'ir': {'v36': ir36, 'v37': ir37},
        'avg_picks': {'v36': float(np.mean(n_picks_v36)),
                      'v37': float(np.mean(n_picks_v37))},
        'history': history,
    }
    out_path = BASE / f'backtest_v37_vs_v36_{datetime.now().strftime("%Y%m%d_%H%M")}.json'
    out_path.write_text(json.dumps(report, ensure_ascii=False, indent=2),
                        encoding='utf-8')
    print(f"\n💾 리포트 저장: {out_path}")

    # 가장 영향 큰 종목 분석
    last_snap = compute_scores_at(panel, rebal_dates[-2], use_v37=True)
    if last_snap is not None:
        last_snap['Δ_체력'] = last_snap['체력_v37'] - last_snap['체력_v36']
        last_snap['Δ_등급'] = last_snap.apply(
            lambda r: f"{r['등급_v36']} → {r['등급_v37']}" if r['등급_v36'] != r['등급_v37'] else '', axis=1)
        print("\n📋 최근 시점 v3.7 영향 (등급 변동 종목):")
        impact = last_snap[last_snap['Δ_등급'] != ''][
            ['종목','등급_v36','등급_v37','Δ_체력','Mom12','BAB','NOA']]
        if len(impact) > 0:
            print(impact.to_string(index=False))
        else:
            print("  (이번 시점 등급 변동 없음)")

    return report


def main():
    args = parse_args()
    print("=" * 70)
    print(f"진우퀀트 v3.7 vs v3.6 백테스트  ({args.years}년)")
    print(f"시간: {datetime.now()}")
    print("=" * 70)

    panel = fetch_long_panel(args.years)
    if panel.get('_KOSPI') is None:
        print("❌ 데이터 수집 실패 — 종료")
        sys.exit(1)

    run_backtest(panel, args)


if __name__ == '__main__':
    main()
