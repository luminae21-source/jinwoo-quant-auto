#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
진우퀀트 v3.7.2 섹터별 검증 (영역 3 종목 확장 결정용)

검증 항목 (6가지):
  1. 섹터별 contribution (4년 누적 alpha 기여도)
  2. 반도체 제외 시뮬 (4종목 제외하고 14종목으로 백테스트)
  3. 섹터 cap 단계별 (35%, 25%, 20%, 15%)
  4. 섹터 다양성 측정 (매월 픽되는 섹터 수)
  5. 섹터별 MDD 기여
  6. 섹터 cycle 상관관계

답하는 질문:
  - 반도체 4종목 (33%)이 v3.7.2 alpha의 핵심인가, 위험인가?
  - 종목 확장이 시급한가, 비중 cap만으로 충분한가?
  - 섹터 다양성이 alpha의 source인가 stability의 source인가?
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
from score_v37_2 import ECHO_WEIGHT


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


def compute_v37_2_at(panel, dt, target_grades, universe=None):
    """v3.7.2 점수로 picks + 점수 매트릭스. universe로 제외 가능"""
    if universe is None:
        universe = list(JINWOO_v37.keys())
    kospi = panel.get('_KOSPI')

    # Echo
    echo_values = {}
    for name in universe:
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
        echo_scores = {n: 0 for n in universe}
        for name in universe:
            v = echo_values.get(name)
            if v is None: continue
            elif v >= upper: echo_scores[name] = +1
            elif v <= lower: echo_scores[name] = -1
            else: echo_scores[name] = 0
    else:
        echo_scores = {n: 0 for n in universe}

    rows = []
    for name in universe:
        if name not in JINWOO_v37: continue
        info = JINWOO_v37[name]
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
        rows.append({
            '종목': name, '산업': info['산업'],
            '체력': round(total, 2), '등급': grade(total),
        })

    df = pd.DataFrame(rows)
    if len(df) == 0:
        return [], {}, {}
    picks = df[df['등급'].isin(target_grades)]['종목'].tolist()
    pick_sectors = dict(zip(df[df['등급'].isin(target_grades)]['종목'],
                            df[df['등급'].isin(target_grades)]['산업']))
    scores_map = dict(zip(df['종목'], df['체력']))
    return picks, pick_sectors, scores_map


def get_stock_return(panel, name, dt_start, dt_end):
    s = panel.get(name)
    if s is None: return 0.0
    sw = s[(s.index > dt_start) & (s.index <= dt_end)]
    if len(sw) < 2: return 0.0
    return float(sw.iloc[-1] / sw.iloc[0] - 1)


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


def metrics(rets, ppy=12):
    arr = np.array(rets)
    if len(arr) == 0: return {}
    cum = float(np.prod(1 + arr) - 1)
    ann = (1 + cum) ** (ppy / len(arr)) - 1
    vol = float(arr.std() * np.sqrt(ppy))
    sharpe = float(ann / vol) if vol > 0 else None
    cc = np.cumprod(1 + arr)
    peak = np.maximum.accumulate(cc)
    return {
        '누적': round(cum * 100, 2), '연환산': round(ann * 100, 2),
        '변동성': round(vol * 100, 2),
        'Sharpe': round(sharpe, 2) if sharpe else None,
        'MDD': round(float(((cc - peak) / peak).min()) * 100, 2),
    }


# ============================================
# 검증 1: 섹터별 contribution
# ============================================
def validate_sector_contribution(panel, args):
    print("\n" + "=" * 90)
    print("검증 #1: 섹터별 contribution (4년 누적 alpha 기여도)")
    print("=" * 90)

    target = set(args.top_grades.split(','))
    rebal = get_rebal_dates(panel, args.years)

    # 섹터별 각 시점 contribution 누적
    sector_cumret = {}     # 섹터별 누적 수익 (개별 종목 평균)
    sector_pick_months = {}  # 섹터별 등장 횟수

    for i in range(len(rebal) - 1):
        d0, d1 = rebal[i], rebal[i + 1]
        picks, pick_sectors, _ = compute_v37_2_at(panel, d0, target)
        if not picks: continue

        n_picks = len(picks)
        for name in picks:
            sector = pick_sectors.get(name, 'Other')
            r = get_stock_return(panel, name, d0, d1)
            weight = 1.0 / n_picks  # equal weight
            if sector not in sector_cumret:
                sector_cumret[sector] = 0
                sector_pick_months[sector] = 0
            sector_cumret[sector] += r * weight
            sector_pick_months[sector] += 1

    # 정렬
    total_cum = sum(sector_cumret.values())
    sorted_sectors = sorted(sector_cumret.items(), key=lambda x: -x[1])

    print(f"  4년 누적 contribution 합계: {total_cum*100:.2f}%p")
    print(f"  {'섹터':14s} {'누적기여_%p':>12s} {'비중_%':>8s} {'평균월수':>8s}")
    sector_share = {}
    for sec, ret in sorted_sectors:
        share = ret / total_cum * 100 if total_cum > 0 else 0
        sector_share[sec] = share
        avg_months = sector_pick_months[sec] / 49 * 100  # 49 rebalance
        print(f"  {sec:14s} {ret*100:>11.2f}%p {share:>7.1f}% {avg_months:>7.1f}%")

    # 진단
    top_sec, top_ret = sorted_sectors[0]
    top_share = top_ret / total_cum * 100 if total_cum > 0 else 0
    print(f"\n  → Top 섹터: {top_sec} ({top_share:.1f}% contribution)")
    if top_share > 50:
        print(f"  ⚠️ Top 섹터 contribution > 50% — 의존도 큼")
    else:
        print(f"  ✅ Top 섹터 contribution ≤ 50% — 분산 OK")

    return {
        'sector_contribution_%p': {k: round(v*100, 2) for k, v in sector_cumret.items()},
        'sector_share_%': {k: round(v, 1) for k, v in sector_share.items()},
        'top_sector': top_sec, 'top_share_%': round(top_share, 1),
    }


# ============================================
# 검증 2: 반도체 제외 시뮬
# ============================================
def validate_sector_exclusion(panel, args):
    print("\n" + "=" * 90)
    print("검증 #2: 섹터 제외 시뮬 (반도체·방산·금융 각각 제외)")
    print("=" * 90)

    target = set(args.top_grades.split(','))
    all_universe = list(JINWOO_v37.keys())

    # 섹터별 종목
    sectors_to_test = ['반도체', '방산', '금융', '인터넷']
    excl_results = {}

    # 베이스라인 (포함)
    rebal = get_rebal_dates(panel, args.years)
    rets = []
    for i in range(len(rebal) - 1):
        d0, d1 = rebal[i], rebal[i + 1]
        picks, _, _ = compute_v37_2_at(panel, d0, target)
        if not picks: rets.append(0); continue
        r = np.mean([get_stock_return(panel, n, d0, d1) for n in picks])
        rets.append(r)
    m_base = metrics(rets)
    print(f"\n  [Baseline 18종목]: CAGR {m_base.get('연환산',0):>6.2f}%  "
          f"Sharpe {m_base.get('Sharpe','-')}  MDD {m_base.get('MDD',0):>6.2f}%")

    excl_results['baseline'] = m_base

    for sec_to_excl in sectors_to_test:
        # 해당 섹터 제외 universe
        universe = [n for n in all_universe
                   if JINWOO_v37[n]['산업'] != sec_to_excl]
        excl_count = len(all_universe) - len(universe)
        rets = []
        for i in range(len(rebal) - 1):
            d0, d1 = rebal[i], rebal[i + 1]
            picks, _, _ = compute_v37_2_at(panel, d0, target, universe)
            if not picks: rets.append(0); continue
            r = np.mean([get_stock_return(panel, n, d0, d1) for n in picks])
            rets.append(r)
        m = metrics(rets)
        excl_results[f'excl_{sec_to_excl}'] = m
        delta = m.get('연환산', 0) - m_base.get('연환산', 0)
        print(f"  [{sec_to_excl} {excl_count}종목 제외]: CAGR {m.get('연환산',0):>6.2f}%  "
              f"Sharpe {m.get('Sharpe','-')}  MDD {m.get('MDD',0):>6.2f}%  "
              f"Δ vs base: {delta:+.2f}%p")

    # 반도체 제외 진단
    semi_delta = excl_results.get('excl_반도체', {}).get('연환산', 0) - m_base.get('연환산', 0)
    print(f"\n  → 반도체 제외 시 alpha 손실: {semi_delta:+.2f}%p")
    if abs(semi_delta) < 1:
        print(f"  ✅ 반도체 의존도 낮음 (-1%p 이내) — universe 확장 시급도 낮음")
    elif abs(semi_delta) < 3:
        print(f"  △ 반도체 의존도 중간 (-1~-3%p) — 비중 cap 권장")
    else:
        print(f"  ⚠️ 반도체 의존도 큼 (>-3%p) — 종목 확장 검토 권장")

    return excl_results


# ============================================
# 검증 3: 섹터 cap 단계별
# ============================================
def validate_sector_cap_steps(panel, args):
    print("\n" + "=" * 90)
    print("검증 #3: 섹터 cap 단계별 (제한 없음, 35%, 25%, 20%, 15%)")
    print("=" * 90)

    target = set(args.top_grades.split(','))
    rebal = get_rebal_dates(panel, args.years)

    cap_results = {}
    for cap in [1.0, 0.35, 0.25, 0.20, 0.15]:
        rets = []
        cap_count = 0
        for i in range(len(rebal) - 1):
            d0, d1 = rebal[i], rebal[i + 1]
            picks, pick_sectors, _ = compute_v37_2_at(panel, d0, target)
            if not picks: rets.append(0); continue

            n = len(picks)
            raw_w = 1.0 / n
            weights = {p: raw_w for p in picks}

            # 섹터별 cap 적용
            sector_totals = {}
            for p in picks:
                s = pick_sectors.get(p, 'Other')
                sector_totals[s] = sector_totals.get(s, 0) + weights[p]
            for sec, tot in sector_totals.items():
                if tot > cap:
                    scale = cap / tot
                    for p in picks:
                        if pick_sectors.get(p) == sec:
                            weights[p] *= scale
                            cap_count += 1
            tot = sum(weights.values())
            if tot > 0:
                weights = {k: v/tot for k, v in weights.items()}

            r = sum(get_stock_return(panel, p, d0, d1) * w
                   for p, w in weights.items())
            rets.append(r)

        m = metrics(rets)
        cap_results[f'cap_{cap}'] = m
        cap_label = f'무제한' if cap >= 1 else f'{int(cap*100)}%'
        print(f"  Cap {cap_label:6s}: CAGR {m.get('연환산',0):>6.2f}%  "
              f"Sharpe {m.get('Sharpe','-')}  "
              f"MDD {m.get('MDD',0):>6.2f}%  cap적용 {cap_count}회")

    # GPT 권장 35%와 25% 비교
    baseline_cagr = cap_results['cap_1.0'].get('연환산', 0)
    cap_35_cagr = cap_results['cap_0.35'].get('연환산', 0)
    cap_25_cagr = cap_results['cap_0.25'].get('연환산', 0)
    cap_15_cagr = cap_results['cap_0.15'].get('연환산', 0)

    print(f"\n  Cap 35% vs 무제한: {cap_35_cagr - baseline_cagr:+.2f}%p")
    print(f"  Cap 25% vs 무제한: {cap_25_cagr - baseline_cagr:+.2f}%p")
    print(f"  Cap 15% vs 무제한: {cap_15_cagr - baseline_cagr:+.2f}%p")
    if abs(cap_25_cagr - baseline_cagr) < 1:
        print(f"  ✅ 25% cap도 alpha 손실 거의 없음 — cap만으로 위험 관리 충분")
    elif abs(cap_25_cagr - baseline_cagr) < 3:
        print(f"  △ 25% cap 시 약간 손실 — 35% cap 권장")
    else:
        print(f"  ⚠️ 25% cap 시 큰 손실 — 종목 확장 필요")

    return cap_results


# ============================================
# 검증 4: 섹터 다양성
# ============================================
def validate_sector_diversity(panel, args):
    print("\n" + "=" * 90)
    print("검증 #4: 섹터 다양성 (매월 픽되는 섹터 수)")
    print("=" * 90)

    target = set(args.top_grades.split(','))
    rebal = get_rebal_dates(panel, args.years)

    monthly_diversity = []
    for i in range(len(rebal) - 1):
        d0, d1 = rebal[i], rebal[i + 1]
        picks, pick_sectors, _ = compute_v37_2_at(panel, d0, target)
        sectors = set(pick_sectors.values())
        monthly_diversity.append(len(sectors))

    arr = np.array(monthly_diversity)
    print(f"  매월 평균 픽 섹터 수: {arr.mean():.1f}개")
    print(f"  최저: {int(arr.min())}개 / 최고: {int(arr.max())}개 / 표준편차: {arr.std():.2f}")
    print(f"  18종목 universe 총 산업: 12개")
    pct = arr.mean() / 12 * 100
    print(f"  → 평균 다양성: 전체 산업의 {pct:.1f}% cover")

    if arr.mean() >= 7:
        print(f"  ✅ 매월 7개 이상 섹터 — 분산 양호")
    elif arr.mean() >= 5:
        print(f"  △ 매월 5-7개 섹터 — 보통")
    else:
        print(f"  ⚠️ 매월 5개 미만 섹터 — 다양성 부족")

    return {
        '평균_섹터수': round(arr.mean(), 1),
        '최저_섹터수': int(arr.min()),
        '최고_섹터수': int(arr.max()),
        '표준편차': round(arr.std(), 2),
    }


# ============================================
# 검증 5: 섹터별 MDD 기여
# ============================================
def validate_sector_mdd(panel, args):
    print("\n" + "=" * 90)
    print("검증 #5: 섹터별 MDD 기여 (최악월에 어떤 섹터가 손실 만들었나)")
    print("=" * 90)

    target = set(args.top_grades.split(','))
    rebal = get_rebal_dates(panel, args.years)

    monthly_records = []
    for i in range(len(rebal) - 1):
        d0, d1 = rebal[i], rebal[i + 1]
        picks, pick_sectors, _ = compute_v37_2_at(panel, d0, target)
        if not picks:
            monthly_records.append({'date': d0, 'total': 0, 'by_sector': {}})
            continue

        n = len(picks)
        weight = 1.0 / n
        by_sector = {}
        total = 0
        for p in picks:
            sec = pick_sectors.get(p, 'Other')
            r = get_stock_return(panel, p, d0, d1)
            contrib = r * weight
            by_sector[sec] = by_sector.get(sec, 0) + contrib
            total += contrib
        monthly_records.append({'date': d0, 'total': total, 'by_sector': by_sector})

    # 최악월 5개
    sorted_records = sorted(monthly_records, key=lambda x: x['total'])
    worst5 = sorted_records[:5]

    print("  최악월 5개 분해:")
    for rec in worst5:
        print(f"\n    {rec['date'].strftime('%Y-%m')} (총수익 {rec['total']*100:.2f}%):")
        sorted_secs = sorted(rec['by_sector'].items(), key=lambda x: x[1])
        for sec, contrib in sorted_secs[:5]:
            print(f"      {sec:14s}: {contrib*100:+.2f}%p")

    # 섹터별 누적 음의 기여
    sector_neg_contrib = {}
    for rec in monthly_records:
        for sec, c in rec['by_sector'].items():
            if c < 0:
                sector_neg_contrib[sec] = sector_neg_contrib.get(sec, 0) + c

    print("\n  섹터별 누적 음의 기여 (큰 손실 만든 섹터):")
    sorted_neg = sorted(sector_neg_contrib.items(), key=lambda x: x[1])
    for sec, neg in sorted_neg[:5]:
        print(f"    {sec:14s}: {neg*100:+.2f}%p (4년 누적 음의 기여)")

    return {
        'worst5_months': [{
            'date': r['date'].strftime('%Y-%m'),
            'total_%': round(r['total']*100, 2),
            'by_sector_%p': {k: round(v*100, 2) for k, v in r['by_sector'].items()},
        } for r in worst5],
        'sector_neg_contrib_%p': {k: round(v*100, 2) for k, v in sector_neg_contrib.items()},
    }


# ============================================
# 검증 6: 섹터 상관관계
# ============================================
def validate_sector_correlation(panel, args):
    print("\n" + "=" * 90)
    print("검증 #6: 섹터 cycle 상관관계 (섹터 간 동조성)")
    print("=" * 90)

    target = set(args.top_grades.split(','))
    rebal = get_rebal_dates(panel, args.years)

    sector_monthly_rets = {}  # {sector: [월수익 list]}
    for i in range(len(rebal) - 1):
        d0, d1 = rebal[i], rebal[i + 1]
        picks, pick_sectors, _ = compute_v37_2_at(panel, d0, target)
        sec_rets = {}
        for p in picks:
            sec = pick_sectors.get(p, 'Other')
            r = get_stock_return(panel, p, d0, d1)
            if sec not in sec_rets: sec_rets[sec] = []
            sec_rets[sec].append(r)
        # 섹터별 평균
        for sec, rs in sec_rets.items():
            if sec not in sector_monthly_rets:
                sector_monthly_rets[sec] = []
            sector_monthly_rets[sec].append(np.mean(rs))

    # 6개월 이상 데이터 있는 섹터만
    eligible = {k: v for k, v in sector_monthly_rets.items() if len(v) >= 12}
    if len(eligible) < 2:
        print("  ⚠️ 충분한 데이터 없음")
        return {}

    # Pad to same length (시점 정렬 안 했으므로 단순 비교)
    max_len = max(len(v) for v in eligible.values())
    aligned = {k: v[:min(len(v), max_len)] for k, v in eligible.items()}

    # 단순 평균 상관 (시점 정렬 부정확하지만 trend 파악)
    print(f"  주요 섹터 평균 월수익률 (상승/하락 횟수):")
    for sec, rs in eligible.items():
        arr = np.array(rs)
        up = int((arr > 0).sum())
        down = int((arr <= 0).sum())
        print(f"    {sec:14s}: 평균 {arr.mean()*100:+.2f}%/월  "
              f"상승 {up}개월  하락 {down}개월  변동성 {arr.std()*100:.2f}%")

    return {
        'sector_monthly_stats': {k: {
            '평균_%': round(np.mean(v)*100, 2),
            '변동성_%': round(np.std(v)*100, 2),
            '상승월': int((np.array(v) > 0).sum()),
            '하락월': int((np.array(v) <= 0).sum()),
        } for k, v in eligible.items()},
    }


def main():
    args = parse_args()
    print("=" * 90)
    print("진우퀀트 v3.7.2 섹터별 검증 (영역 3 결정용)")
    print(f"시간: {datetime.now()}")
    print("=" * 90)

    print("\n📊 데이터 수집...")
    panel = fetch_long_panel(args.years)
    print(f"  완료")

    results = {}
    results['sector_contribution'] = validate_sector_contribution(panel, args)
    results['sector_exclusion'] = validate_sector_exclusion(panel, args)
    results['sector_cap_steps'] = validate_sector_cap_steps(panel, args)
    results['sector_diversity'] = validate_sector_diversity(panel, args)
    results['sector_mdd'] = validate_sector_mdd(panel, args)
    results['sector_correlation'] = validate_sector_correlation(panel, args)

    out = BASE / f'validate_sector_{datetime.now().strftime("%Y%m%d_%H%M")}.json'
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str),
                   encoding='utf-8')
    print(f"\n💾 저장: {out}")

    # 종합 진단
    print("\n" + "=" * 90)
    print("📋 종합 진단 — 종목 확장 vs 비중 cap 결정")
    print("=" * 90)
    top_share = results['sector_contribution'].get('top_share_%', 0)
    semi_delta = results['sector_exclusion'].get('excl_반도체', {}).get('연환산', 0) - \
                 results['sector_exclusion'].get('baseline', {}).get('연환산', 0)
    cap_25_delta = results['sector_cap_steps'].get('cap_0.25', {}).get('연환산', 0) - \
                   results['sector_cap_steps'].get('cap_1.0', {}).get('연환산', 0)
    avg_div = results['sector_diversity'].get('평균_섹터수', 0)

    print(f"  Top 섹터 contribution: {top_share}% (>50% 위험)")
    print(f"  반도체 제외 시 alpha: {semi_delta:+.2f}%p (>−3%p 의존 큼)")
    print(f"  Cap 25% 적용 손실: {cap_25_delta:+.2f}%p (>−3%p 손실 크면 확장 필요)")
    print(f"  매월 섹터 다양성: {avg_div}개 (<5개 부족)")

    score_extend = 0
    if top_share > 50: score_extend += 1
    if semi_delta < -3: score_extend += 1
    if cap_25_delta < -3: score_extend += 1
    if avg_div < 5: score_extend += 1

    print(f"\n  종목 확장 필요도 점수: {score_extend}/4")
    if score_extend >= 3:
        print(f"  ⚠️ 종목 확장 시급 — 21~30종목 점진적 확장 권장")
    elif score_extend >= 2:
        print(f"  △ 비중 cap + 일부 확장 검토 (예: 반도체 외 2-3종목 추가)")
    elif score_extend >= 1:
        print(f"  ✅ 비중 cap (35% or 25%)만 적용, 확장 보류")
    else:
        print(f"  ✅ 현재 18종목 robust — 확장 불필요")


if __name__ == '__main__':
    main()
