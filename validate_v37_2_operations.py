#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
진우퀀트 v3.7.2 운영 검증 (Tier 1 + 별도)

검증 항목 (7가지):
  Tier 1:
    1. 리밸런싱 지연 시뮬 (+3·+5·+10거래일) — 직장인 필수
    2. 거래비용 + Turnover 측정
    3. (regime_split.py 별도 파일에서 처리)

  별도 운영 검증 (GPT Q7):
    4. Slippage 0.1% 차감
    5. 종목별 최대 비중 제한 (15%)
    6. 섹터별 최대 비중 제한 (35%)
    7. 월별 최악 + 연속 손실 개월
    8. 세후수익 (종합과세 시뮬 대략)

GPT 검증 (2026-05-28):
  - Q7 운영 검증 9가지 권장 (직장인 운영자 필수 리밸런싱 지연 시뮬)
  - 거래비용 0.235% (수수료 0.015% + 세금 0.2%)
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


# 한국 매매수수료 + 세금
TRADING_COST = 0.00235  # 수수료 0.015% × 2 + 세금 0.2% (총 약 0.235%/회전)
SLIPPAGE = 0.001        # Slippage 0.1%

# 비중 제한 (GPT 권장)
MAX_STOCK_WEIGHT = 0.15    # 종목별 15%
MAX_SECTOR_WEIGHT = 0.35   # 섹터별 35%


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


def compute_v37_2_picks_at(panel, dt, target_grades):
    """v3.7.2 (ECHO ×1.0) 점수로 등급 안 picks 반환"""
    kospi = panel.get('_KOSPI')

    # Echo 시간 가변
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
        sorted_desc = pd.Series(echo_values).sort_values(ascending=False)
        upper = sorted_desc.iloc[upper_n - 1]
        lower = sorted_desc.iloc[-lower_n]
        echo_scores = {}
        for name in JINWOO_v37:
            v = echo_values.get(name)
            if v is None: echo_scores[name] = 0
            elif v >= upper: echo_scores[name] = +1
            elif v <= lower: echo_scores[name] = -1
            else: echo_scores[name] = 0
    else:
        echo_scores = {n: 0 for n in JINWOO_v37}

    picks = []
    scores_map = {}
    sectors_map = {}
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
        mom_s = mom12_to_score(r_mom12)
        bab_s = bab_to_score_v371(beta60)
        noa_s = noa_to_score(info.get('NOA', 0))
        echo_s = echo_scores.get(name, 0) * ECHO_WEIGHT

        total = (체력_12점 + info['ModF'] + far_val + info['Sloan']
                + mom_s + bab_s + noa_s + echo_s)
        g = grade(total)
        scores_map[name] = total
        sectors_map[name] = info['산업']
        if g in target_grades:
            picks.append(name)
    return picks, scores_map, sectors_map


def apply_weight_caps(picks, sectors_map, max_stock=MAX_STOCK_WEIGHT,
                     max_sector=MAX_SECTOR_WEIGHT):
    """종목·섹터 비중 제한 적용"""
    if not picks:
        return {}, 0
    n = len(picks)
    raw_weight = 1.0 / n  # equal weight

    # 종목별 cap
    weights = {p: min(raw_weight, max_stock) for p in picks}

    # 섹터별 cap
    sector_totals = {}
    for p in picks:
        s = sectors_map.get(p, 'Other')
        sector_totals[s] = sector_totals.get(s, 0) + weights[p]

    # 섹터 초과 시 비례 축소
    capped_count = 0
    for sec, total in sector_totals.items():
        if total > max_sector:
            scale = max_sector / total
            for p in picks:
                if sectors_map.get(p) == sec:
                    weights[p] *= scale
                    capped_count += 1

    # 정규화
    total = sum(weights.values())
    if total > 0:
        weights = {k: v/total for k, v in weights.items()}
    return weights, capped_count


def weighted_return(picks_weights, panel, dt_start, dt_end):
    if not picks_weights:
        return 0.0
    total = 0
    for name, w in picks_weights.items():
        s = panel.get(name)
        if s is None: continue
        sw = s[(s.index > dt_start) & (s.index <= dt_end)]
        if len(sw) < 2: continue
        r = float(sw.iloc[-1] / sw.iloc[0] - 1)
        total += r * w
    return total


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
        '승률': round(float((arr > 0).mean()) * 100, 1),
        '기간': len(arr),
    }


def get_rebal_dates(panel, years, lag_days=0):
    """리밸런싱 일자 + 지연 lag_days 적용"""
    k = panel.get('_KOSPI')
    end_dt = k.index[-1]
    start_dt = end_dt - pd.DateOffset(years=years)
    bp = k[(k.index >= start_dt) & (k.index <= end_dt)]
    rebal = bp.resample('MS').first().dropna().index

    # lag 적용
    if lag_days > 0:
        rebal = [d + pd.Timedelta(days=lag_days) for d in rebal]

    # 가장 가까운 영업일로 매핑
    rebal_idx = []
    for d in rebal:
        if d <= end_dt:
            idx = k.index.get_indexer([d], method='bfill')[0]
            if idx < len(k.index):
                rebal_idx.append(k.index[idx])
    rebal_idx = sorted(set(rebal_idx))
    if rebal_idx and rebal_idx[-1] < end_dt:
        rebal_idx.append(end_dt)
    return rebal_idx


# ============================================
# 검증 1: 리밸런싱 지연 시뮬
# ============================================
def validate_rebalance_delay(panel, args):
    print("\n" + "=" * 90)
    print("검증 #1: 리밸런싱 지연 시뮬 (직장인 운영자 필수, GPT Q7)")
    print("=" * 90)

    target = set(args.top_grades.split(','))
    results = {}

    for lag in [0, 3, 5, 10]:
        rebal_dates = get_rebal_dates(panel, args.years, lag_days=lag)
        rets = []
        for i in range(len(rebal_dates) - 1):
            d0, d1 = rebal_dates[i], rebal_dates[i + 1]
            picks, _, _ = compute_v37_2_picks_at(panel, d0, target)
            rets.append(avg_return(picks, panel, d0, d1))

        m = metrics(rets)
        results[f'lag_{lag}'] = m
        print(f"  지연 +{lag:2d}일: CAGR {m.get('연환산', 0):>6.2f}%  "
              f"Sharpe {str(m.get('Sharpe', '-')):>5s}  "
              f"MDD {m.get('MDD', 0):>6.2f}%  기간 {m.get('기간', 0)}")

    cagr_0 = results['lag_0'].get('연환산', 0)
    cagr_10 = results['lag_10'].get('연환산', 0)
    print(f"\n  → 지연 +10일 시 CAGR 변화: {cagr_10 - cagr_0:+.2f}%p")
    if cagr_10 >= cagr_0 - 2:
        print(f"  ✅ 견고함 — 직장인 운영 시 alpha 유지")
    else:
        print(f"  ⚠️ 민감 — 지연 시 alpha 크게 감소")
    return results


# ============================================
# 검증 2: 거래비용 + Turnover
# ============================================
def validate_trading_cost(panel, args):
    print("\n" + "=" * 90)
    print("검증 #2: 거래비용 + Turnover (수수료 + 세금 0.235% + Slippage 0.1%)")
    print("=" * 90)

    target = set(args.top_grades.split(','))
    rebal_dates = get_rebal_dates(panel, args.years)

    rets_gross, rets_net = [], []
    turnover_list = []
    prev_picks = set()

    for i in range(len(rebal_dates) - 1):
        d0, d1 = rebal_dates[i], rebal_dates[i + 1]
        picks, _, _ = compute_v37_2_picks_at(panel, d0, target)
        picks_set = set(picks)

        # turnover = (신규 + 매도) / 평균
        new_picks = picks_set - prev_picks
        sold_picks = prev_picks - picks_set
        if prev_picks or picks_set:
            denom = (len(prev_picks) + len(picks_set)) / 2
            if denom > 0:
                to = (len(new_picks) + len(sold_picks)) / 2 / denom
            else:
                to = 0
        else:
            to = 0
        turnover_list.append(to)

        r_gross = avg_return(picks, panel, d0, d1)
        # 비용 차감: turnover × (수수료+세금) + slippage
        cost = to * TRADING_COST + SLIPPAGE if picks_set else 0
        r_net = r_gross - cost

        rets_gross.append(r_gross)
        rets_net.append(r_net)
        prev_picks = picks_set

    m_gross = metrics(rets_gross)
    m_net = metrics(rets_net)
    avg_turnover = np.mean(turnover_list) * 100

    print(f"  Gross  : CAGR {m_gross.get('연환산',0):>6.2f}%  "
          f"Sharpe {str(m_gross.get('Sharpe','-')):>5s}  "
          f"MDD {m_gross.get('MDD',0):>6.2f}%")
    print(f"  Net    : CAGR {m_net.get('연환산',0):>6.2f}%  "
          f"Sharpe {str(m_net.get('Sharpe','-')):>5s}  "
          f"MDD {m_net.get('MDD',0):>6.2f}%")
    print(f"  평균 Turnover: {avg_turnover:.1f}% (월간)")
    print(f"  비용 차감 효과: {m_gross.get('연환산',0) - m_net.get('연환산',0):+.2f}%p/년")

    if m_net.get('연환산',0) >= 69.5:  # v3.6 수준 이상
        print(f"  ✅ 비용 차감 후에도 v3.6 능가")
    elif m_net.get('연환산',0) >= 67.9:  # v3.7.1 수준
        print(f"  ✅ 비용 차감 후 v3.7.1 수준 — 양호")
    else:
        print(f"  ⚠️ 비용 차감 시 v3.7.1 미만 — Turnover 너무 큼")

    if avg_turnover <= 30:
        print(f"  ✅ Turnover ≤ 30% (GPT 기준)")
    else:
        print(f"  ⚠️ Turnover > 30% — 빈번한 종목 교체")

    return {'gross': m_gross, 'net': m_net, 'turnover_%': avg_turnover}


# ============================================
# 검증 5·6: 비중 제한 (종목 15%, 섹터 35%)
# ============================================
def validate_weight_caps(panel, args):
    print("\n" + "=" * 90)
    print("검증 #5·6: 비중 제한 (종목 15% + 섹터 35%)")
    print("=" * 90)

    target = set(args.top_grades.split(','))
    rebal_dates = get_rebal_dates(panel, args.years)

    rets_equal, rets_capped = [], []
    total_capped = 0

    for i in range(len(rebal_dates) - 1):
        d0, d1 = rebal_dates[i], rebal_dates[i + 1]
        picks, _, sectors = compute_v37_2_picks_at(panel, d0, target)

        # Equal weight
        rets_equal.append(avg_return(picks, panel, d0, d1))

        # Capped weight
        weights, capped = apply_weight_caps(picks, sectors)
        rets_capped.append(weighted_return(weights, panel, d0, d1))
        total_capped += capped

    m_eq = metrics(rets_equal)
    m_cap = metrics(rets_capped)

    print(f"  Equal weight: CAGR {m_eq.get('연환산',0):>6.2f}%  "
          f"Sharpe {str(m_eq.get('Sharpe','-')):>5s}  MDD {m_eq.get('MDD',0):>6.2f}%")
    print(f"  Capped     : CAGR {m_cap.get('연환산',0):>6.2f}%  "
          f"Sharpe {str(m_cap.get('Sharpe','-')):>5s}  MDD {m_cap.get('MDD',0):>6.2f}%")
    print(f"  Cap 적용 횟수: {total_capped}")
    print(f"  차이: {m_cap.get('연환산',0) - m_eq.get('연환산',0):+.2f}%p/년")
    return {'equal': m_eq, 'capped': m_cap, 'cap_count': total_capped}


# ============================================
# 검증 7: 월별 최악 + 연속 손실
# ============================================
def validate_worst_months(panel, args):
    print("\n" + "=" * 90)
    print("검증 #7: 월별 최악 수익률 + 연속 손실 개월")
    print("=" * 90)

    target = set(args.top_grades.split(','))
    rebal_dates = get_rebal_dates(panel, args.years)

    rets = []
    for i in range(len(rebal_dates) - 1):
        d0, d1 = rebal_dates[i], rebal_dates[i + 1]
        picks, _, _ = compute_v37_2_picks_at(panel, d0, target)
        rets.append(avg_return(picks, panel, d0, d1))

    arr = np.array(rets)
    sorted_arr = np.sort(arr)
    worst5 = sorted_arr[:5] * 100

    # 연속 손실
    max_streak = 0
    cur = 0
    for r in arr:
        if r < 0:
            cur += 1
            max_streak = max(max_streak, cur)
        else:
            cur = 0

    print(f"  월별 최악 5개월 (%): {[round(x,2) for x in worst5]}")
    print(f"  음의 수익 개월 수: {int((arr < 0).sum())} / {len(arr)}")
    print(f"  최장 연속 손실: {max_streak}개월")
    if max_streak <= 3:
        print(f"  ✅ 연속 손실 3개월 이하 — 견고")
    else:
        print(f"  ⚠️ 연속 손실 {max_streak}개월 — 인내 필요")
    return {
        '최악_5개월_%': [round(x,2) for x in worst5],
        '음의_수익_개월': int((arr < 0).sum()),
        '총_개월': len(arr),
        '최장_연속_손실': max_streak,
    }


# ============================================
# 검증 8: 세후수익 (종합과세 간략 시뮬)
# ============================================
def validate_after_tax(panel, args):
    print("\n" + "=" * 90)
    print("검증 #8: 세후수익 (직장인 종합과세 간략 시뮬)")
    print("=" * 90)

    # 한국 직장인 종합과세 가정 (단순화):
    #   - 직장 근로소득과 합산 → 한계세율 약 24~38% (소득별)
    #   - 진우님 직장인 → 한계세율 24% 가정 (중간값)
    #   - 양도세 없음 (2025 기준 5천만원 이하 차익은 비과세)
    #   - 배당세 14% (분리과세) 또는 종합과세
    #
    # 가정: 매매차익 비과세 (5천만원 이하), 배당세 14% 분리과세
    # 진우퀀트는 모멘텀 전략이라 배당 비중 낮음
    # 단순화: 매매차익 100% 비과세 + 배당세 무시 → 세후 = 세전

    print("  가정:")
    print("    - 매매차익 비과세 (5천만원 이하 직장인)")
    print("    - 배당세 14% 분리과세 (배당 비중 낮은 모멘텀 전략 — 무시)")
    print("    - 종합과세 한계세율 24% (직장인 가정)")
    print()
    print("  현재 한국 개인투자자 모멘텀 전략은 매매차익 5천만원 이하 비과세.")
    print("  → 세전 = 세후 (가정상)")
    print()
    print("  ⚠️ 5천만원 초과 차익 발생 시 20% 양도세 (2025년 이후 시행 여부 확인 필요)")
    print()
    print("  실제 운영 시 진우님 종합소득 + 양도소득 합산 별도 시뮬레이션 권장")
    return {'note': '매매차익 비과세 가정 — 세전 = 세후'}


def main():
    args = parse_args()
    print("=" * 90)
    print("진우퀀트 v3.7.2 운영 검증 (Tier 1 + 별도)")
    print(f"시간: {datetime.now()}")
    print("=" * 90)

    print("\n📊 데이터 수집...")
    panel = fetch_long_panel(args.years)
    print(f"  18종목 + KOSPI 완료")

    results = {}
    results['rebalance_delay'] = validate_rebalance_delay(panel, args)
    results['trading_cost'] = validate_trading_cost(panel, args)
    results['weight_caps'] = validate_weight_caps(panel, args)
    results['worst_months'] = validate_worst_months(panel, args)
    results['after_tax'] = validate_after_tax(panel, args)

    out = BASE / f'validate_operations_{datetime.now().strftime("%Y%m%d_%H%M")}.json'
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str),
                   encoding='utf-8')
    print(f"\n💾 저장: {out}")
    print("\n" + "=" * 90)
    print("✅ 운영 검증 완료 — 다음: validate_v37_2_robustness.py")
    print("=" * 90)


if __name__ == '__main__':
    main()
