#!/usr/bin/env python3
"""
진우퀀트 PIT (Point-in-Time) 백테스트

목적: 단일 시점 cache의 lookahead bias 제거하고 GP·AG factor 진위 판정

비교:
  - v3.6
  - v3.7.1
  - v3.8.1_PIT (GP, 시간 가변)
  - v3.8.2_PIT (GP + AG, 시간 가변)
  - v3.8.3_PIT (GP + AG + Echo, 모두 시간 가변)

각 시점에서:
  - quality_timeseries_cache.json에서 가용한 가장 최근 분기 quality 사용
  - DART 공시 lag 90일 반영 (보수적)
  - 18종목 동적 분위 점수

선행:
  - fetch_dart_quarterly.py 실행 → quality_timeseries_cache.json 생성

학술 근거:
  - GPT Q1 #1 (과최적화 방지): PIT 데이터 필수
  - Cooper-Gulen-Schill 2008: PIT 표준 방법론
  - 노지혜 외 2023: 한국 25년 robust 결과의 진정한 한국 18종목 검증
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
)
from score_v37_1 import bab_to_score as bab_to_score_v371
from score_v38_3 import compute_echo, ECHO_WEIGHT
from score_v38_2 import GP_WEIGHT, AG_WEIGHT

TIMESERIES_CACHE = BASE / 'quality_timeseries_cache.json'

# 업종 매핑
SECTOR_MAP = {
    '삼성전자': '제조업', 'SK하이닉스': '제조업', '한미반도체': '제조업',
    '알테오젠': '제조업', '기아': '제조업', 'NAVER': '제조업',
    '카카오': '제조업', '한화에어로': '제조업', 'LIG넥스원': '제조업',
    'KT&G': '제조업', '삼성SDI': '제조업', '아모레퍼시픽': '제조업',
    '삼성물산': '제조업', '삼양식품': '제조업', 'ISC': '제조업',
    '두산에너빌리티': '제조업',
    'KB금융': '은행', 'NH투자증권': '증권사',
}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--years', type=int, default=4)
    p.add_argument('--top-grades', type=str, default='S+,S,A')
    p.add_argument('--lag-days', type=int, default=90,
                   help='DART 공시 lag (보수적 90일)')
    return p.parse_args()


# ============================================
# 시계열 quality 로드 + PIT 조회
# ============================================
def load_timeseries():
    if not TIMESERIES_CACHE.exists():
        raise RuntimeError(
            f"{TIMESERIES_CACHE.name} 없음. fetch_dart_quarterly.py 먼저 실행"
        )
    return json.loads(TIMESERIES_CACHE.read_text(encoding='utf-8'))['data']


def quarter_end_date(q_key):
    """예: '2024Q3' → Timestamp('2024-09-30')"""
    y, q = q_key.split('Q')
    y, q = int(y), int(q)
    month = q * 3
    return pd.Timestamp(y, month, 1) + pd.offsets.MonthEnd(0)


def get_pit_quality(timeseries, name, rebalance_date, lag_days=90):
    """
    rebalance_date 시점에 가용한 가장 최근 quality 반환.
    공시 lag: 분기 종료 + lag_days 이후에 사용 가능.
    """
    qd = timeseries.get(name, {}).get('quality_by_quarter', {})
    if not qd:
        return None, None

    cutoff = rebalance_date - pd.Timedelta(days=lag_days)
    eligible = {k: v for k, v in qd.items()
                if quarter_end_date(k) <= cutoff}
    if not eligible:
        return None, None

    latest = max(eligible.keys(), key=quarter_end_date)
    return eligible[latest], latest


# ============================================
# PIT 점수 (시간 가변)
# ============================================
def three_tile_score(values, all_names, low_is_high=False):
    """
    3분위 점수: 상위 20% = +1 / 중위 60% = 0 / 하위 20% = -1
    low_is_high=True 면 낮은 값이 상위 (AG의 경우)
    """
    if not values:
        return {n: 0 for n in all_names}

    n = len(values)
    upper_n = max(1, round(n * 0.2))
    lower_n = max(1, round(n * 0.2))

    if low_is_high:
        sorted_asc = pd.Series(values).sort_values(ascending=True)
        low_thresh = sorted_asc.iloc[upper_n - 1]
        high_thresh = sorted_asc.iloc[-lower_n]
        scores = {}
        for name in all_names:
            v = values.get(name)
            if v is None:
                scores[name] = 0
            elif v <= low_thresh:
                scores[name] = +1   # 낮은 자산성장 = 상위
            elif v >= high_thresh:
                scores[name] = -1   # 높은 자산성장 = 하위
            else:
                scores[name] = 0
        return scores
    else:
        sorted_desc = pd.Series(values).sort_values(ascending=False)
        upper_thresh = sorted_desc.iloc[upper_n - 1]
        lower_thresh = sorted_desc.iloc[-lower_n]
        scores = {}
        for name in all_names:
            v = values.get(name)
            if v is None:
                scores[name] = 0
            elif v >= upper_thresh:
                scores[name] = +1
            elif v <= lower_thresh:
                scores[name] = -1
            else:
                scores[name] = 0
        return scores


def compute_pit_scores(timeseries, rebalance_date, lag_days=90):
    """시점 t에서 PIT GP·AG 동적 점수"""
    gp_values = {}
    ag_values = {}
    quality_info = {}

    for name in JINWOO_v37:
        sector = SECTOR_MAP.get(name, '제조업')
        quality, q_key = get_pit_quality(timeseries, name, rebalance_date, lag_days)
        if quality is None:
            continue
        quality_info[name] = q_key

        if sector == '제조업':
            gp = quality.get('GP_Assets')
            ag = quality.get('Asset_Growth')
            if gp is not None:
                gp_values[name] = gp
            if ag is not None:
                ag_values[name] = ag
        else:  # 금융주
            roe = quality.get('ROE')
            if roe is not None:
                gp_values[name] = roe   # ROE를 GP equivalent로 사용
            # 금융주 AG는 의미 다름 → 제외

    gp_scores = three_tile_score(gp_values, JINWOO_v37.keys(), low_is_high=False)
    ag_scores = three_tile_score(ag_values, JINWOO_v37.keys(), low_is_high=True)

    return gp_scores, ag_scores, quality_info


# ============================================
# Echo (시간 가변, bias 없음)
# ============================================
def compute_echo_scores_at(panel, dt, days_per_month=21):
    echo_values = {}
    for name in JINWOO_v37:
        series = panel.get(name)
        if series is None:
            continue
        s_cut = series[series.index <= dt]
        if len(s_cut) < 13 * days_per_month:
            continue
        p_t12 = s_cut.iloc[-12 * days_per_month]
        p_t7 = s_cut.iloc[-7 * days_per_month]
        if p_t12 == 0:
            continue
        echo_values[name] = float(p_t7 / p_t12 - 1)
    return three_tile_score(echo_values, JINWOO_v37.keys(), low_is_high=False)


# ============================================
# 가격 데이터 & 백테스트 메트릭 (재사용)
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
    print(f"  KOSPI + 18종목 OK")
    return panel


def compute_scores_pit_at(panel, dt, timeseries, lag_days=90):
    kospi = panel.get('_KOSPI')
    if kospi is None:
        return None

    # PIT 동적 점수
    gp_scores, ag_scores, quality_info = compute_pit_scores(
        timeseries, dt, lag_days)
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
        bab_s = bab_to_score_v371(beta60)
        noa_s = noa_to_score(info.get('NOA', 0))

        gp_s = gp_scores.get(name, 0) * GP_WEIGHT
        ag_s = ag_scores.get(name, 0) * AG_WEIGHT
        echo_s = echo_scores.get(name, 0) * ECHO_WEIGHT

        total_v36 = base
        total_v371 = base + mom_s + bab_s + noa_s
        total_v381_pit = total_v371 + gp_s
        total_v382_pit = total_v371 + gp_s + ag_s
        total_v383_pit = total_v371 + gp_s + ag_s + echo_s

        rows.append({
            '종목': name,
            'GP_PIT': gp_s, 'AG_PIT': ag_s, 'Echo': echo_s,
            'Q_분기': quality_info.get(name, ''),
            '체력_v36': round(total_v36, 2),
            '체력_v37_1': round(total_v371, 2),
            '체력_v38_1_PIT': round(total_v381_pit, 2),
            '체력_v38_2_PIT': round(total_v382_pit, 2),
            '체력_v38_3_PIT': round(total_v383_pit, 2),
            '등급_v36': grade(total_v36),
            '등급_v37_1': grade(total_v371),
            '등급_v38_1_PIT': grade(total_v381_pit),
            '등급_v38_2_PIT': grade(total_v382_pit),
            '등급_v38_3_PIT': grade(total_v383_pit),
        })
    return pd.DataFrame(rows)


def avg_return(picks, panel, dt_start, dt_end):
    if len(picks) == 0:
        return 0.0
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


def metrics(rets, ppy=12):
    arr = np.array(rets)
    if len(arr) == 0: return {}
    cumulative = float(np.prod(1 + arr) - 1)
    annualized = (1 + cumulative) ** (ppy / len(arr)) - 1
    vol = float(arr.std() * np.sqrt(ppy))
    sharpe = float(annualized / vol) if vol > 0 else None
    cum_curve = np.cumprod(1 + arr)
    peak = np.maximum.accumulate(cum_curve)
    drawdown = (cum_curve - peak) / peak
    return {
        '누적': round(cumulative * 100, 2),
        '연환산': round(annualized * 100, 2),
        '변동성': round(vol * 100, 2),
        'Sharpe': round(sharpe, 2) if sharpe else None,
        'MDD': round(float(drawdown.min()) * 100, 2),
        '승률': round(float((arr > 0).mean()) * 100, 1),
        '기간': len(arr),
    }


def information_ratio(p, b, ppy=12):
    p, b = np.array(p), np.array(b)
    excess = p - b
    if len(excess) < 2: return None
    te = excess.std() * np.sqrt(ppy)
    if te == 0: return None
    return round(float(excess.mean() * ppy / te), 2)


def run_backtest(panel, args, timeseries):
    target_grades = set(args.top_grades.split(','))
    k = panel.get('_KOSPI')
    end_dt = k.index[-1]
    start_dt = end_dt - pd.DateOffset(years=args.years)
    bp = k[(k.index >= start_dt) & (k.index <= end_dt)]
    rebal_dates = bp.resample('MS').first().dropna().index
    rebal_dates = [k.index[k.index.get_indexer([d], method='bfill')[0]]
                   for d in rebal_dates if d <= end_dt]
    rebal_dates = sorted(set(rebal_dates))
    if rebal_dates[-1] < end_dt:
        rebal_dates.append(end_dt)

    print(f"\n🔁 Rebalance: {len(rebal_dates)-1}회")
    print(f"📁 DART 공시 lag: {args.lag_days}일")

    rets = {k_: [] for k_ in ['36', '371', '381_pit', '382_pit', '383_pit', 'b']}
    history = []

    for i in range(len(rebal_dates) - 1):
        d0, d1 = rebal_dates[i], rebal_dates[i + 1]
        snap = compute_scores_pit_at(panel, d0, timeseries, args.lag_days)
        if snap is None or len(snap) == 0:
            continue

        for vid, col in [('36', '등급_v36'), ('371', '등급_v37_1'),
                         ('381_pit', '등급_v38_1_PIT'),
                         ('382_pit', '등급_v38_2_PIT'),
                         ('383_pit', '등급_v38_3_PIT')]:
            picks = snap[snap[col].isin(target_grades)]['종목'].tolist()
            r = avg_return(picks, panel, d0, d1)
            rets[vid].append(r)
        rets['b'].append(kospi_return(panel, d0, d1))

        # GP +1 종목 추적 (시간 가변 진단)
        gp_pos = snap[snap['GP_PIT'] > 0]['종목'].tolist()
        ag_pos = snap[snap['AG_PIT'] > 0]['종목'].tolist()
        history.append({
            'date': d0.strftime('%Y-%m-%d'),
            'gp_pos': gp_pos, 'ag_pos': ag_pos,
        })

    m = {k_: metrics(rets[k_]) for k_ in rets}
    ir = {k_: information_ratio(rets[k_], rets['b']) for k_ in rets if k_ != 'b'}

    print("\n" + "=" * 90)
    print(f"PIT 백테스트  ({args.years}년 · M · {args.top_grades})")
    print("=" * 90)

    def row(label, m_, ir_=None):
        print(f"{label:14s} | 누적 {m_.get('누적',0):>7.2f}%  연환산 {m_.get('연환산',0):>6.2f}%  "
              f"vol {m_.get('변동성',0):>5.2f}%  Sharpe {str(m_.get('Sharpe','-')):>5s}  "
              f"MDD {m_.get('MDD',0):>6.2f}%  IR {str(ir_ if ir_ else '-'):>5s}  "
              f"승률 {m_.get('승률',0):>5.1f}%")

    row("v3.6", m['36'], ir['36'])
    row("v3.7.1", m['371'], ir['371'])
    row("v3.8.1_PIT", m['381_pit'], ir['381_pit'])
    row("v3.8.2_PIT", m['382_pit'], ir['382_pit'])
    row("v3.8.3_PIT", m['383_pit'], ir['383_pit'])
    row("KOSPI", m['b'])

    print(f"\n연환산 alpha (vs v3.6, 목표 ≥ -1.0%p):")
    for v, l in [('371', 'v3.7.1'), ('381_pit', 'v3.8.1 PIT'),
                  ('382_pit', 'v3.8.2 PIT'), ('383_pit', 'v3.8.3 PIT')]:
        d = m[v].get('연환산', 0) - m['36'].get('연환산', 0)
        mark = " ⭐" if 'pit' in v else ""
        print(f"  {l}: {d:+.2f}%p{mark}")

    print(f"\nPIT vs 단일 시점 (lookahead bias 차이):")
    print(f"  v3.8.1 단일 시점: -2.69%p → PIT: {m['381_pit'].get('연환산', 0) - m['36'].get('연환산', 0):+.2f}%p")
    print(f"  v3.8.2 단일 시점: -6.28%p → PIT: {m['382_pit'].get('연환산', 0) - m['36'].get('연환산', 0):+.2f}%p")
    print(f"  v3.8.3 단일 시점: -4.96%p → PIT: {m['383_pit'].get('연환산', 0) - m['36'].get('연환산', 0):+.2f}%p")

    # GP·AG 시간 가변성 확인
    print(f"\n📋 GP+1 종목 변동성 (최근 3개월):")
    for h in history[-3:]:
        print(f"  {h['date']}: GP+1 = {', '.join(h['gp_pos'][:5])}")

    report = {
        'timestamp': datetime.now().isoformat(),
        'config': vars(args),
        'metrics': m, 'ir': ir,
        'history': history,
    }
    out = BASE / f'backtest_pit_{datetime.now().strftime("%Y%m%d_%H%M")}.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                              default=str), encoding='utf-8')
    print(f"\n💾 리포트: {out}")
    return report


def main():
    args = parse_args()
    print("=" * 90)
    print("진우퀀트 PIT 백테스트 (lookahead bias 제거)")
    print(f"시간: {datetime.now()}")
    print("=" * 90)

    timeseries = load_timeseries()
    print(f"\n📁 시계열 quality: {len(timeseries)}종목")
    for name in ['삼성전자', '삼양식품', 'LIG넥스원']:
        qd = timeseries[name].get('quality_by_quarter', {})
        print(f"  {name}: {len(qd)}분기")

    panel = fetch_long_panel(args.years)
    if panel.get('_KOSPI') is None:
        sys.exit(1)
    run_backtest(panel, args, timeseries)


if __name__ == '__main__':
    main()
