#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
진우퀀트 v3.7.2 학술 robustness 검증 (Tier 2 + Tier 3)

검증 항목 (6가지):
  Tier 2:
    4. Deflated Sharpe Ratio (Bailey-Lopez de Prado 2014)
    5. ECHO_WEIGHT sensitivity (0.5, 0.7, 1.0, 1.2, 1.5)
    6. Echo look-back 변형 (t-11~t-6, t-12~t-7, t-13~t-8)

  Tier 3:
    7. 표본 기간 변형 (3년·4년·5년 OOS)
    8. 등급 컷 변형 (S+ only, S+/S, S+/S/A, S+/S/A/B)
    9. Bootstrap 신뢰구간 (1000회)

학술 근거:
  - Bailey, D., & López de Prado, M. (2014). "The Deflated Sharpe Ratio"
  - White, H. (2000). "A Reality Check for Data Snooping"
"""

import sys
import json
import argparse
from datetime import datetime, timedelta
from pathlib import Path
import math

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


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--years', type=int, default=4)
    p.add_argument('--top-grades', type=str, default='S+,S,A')
    p.add_argument('--bootstrap-n', type=int, default=1000)
    return p.parse_args()


def fetch_long_panel(years=5):
    """최대 5년 + 데이터 수집"""
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


def compute_echo_at(s_cut, t_start, t_end, dpm=21):
    """Echo = t_end ~ t_start 누적수익률 (t_start, t_end는 월 단위, t_start > t_end)"""
    if s_cut is None or len(s_cut) < (t_start + 1) * dpm:
        return None
    p_start = s_cut.iloc[-t_start * dpm]
    p_end = s_cut.iloc[-t_end * dpm]
    if p_start == 0: return None
    return float(p_end / p_start - 1)


def compute_echo_scores(panel, dt, t_start=12, t_end=7):
    """시점 dt에서 Echo 3분위 점수 (look-back 가변)"""
    echo_values = {}
    for name in JINWOO_v37:
        s = panel.get(name)
        if s is None: continue
        s_cut = s[s.index <= dt]
        v = compute_echo_at(s_cut, t_start, t_end)
        if v is not None:
            echo_values[name] = v
    if not echo_values:
        return {n: 0 for n in JINWOO_v37}

    n = len(echo_values)
    upper_n = max(1, round(n * 0.2))
    lower_n = max(1, round(n * 0.2))
    sorted_desc = pd.Series(echo_values).sort_values(ascending=False)
    upper = sorted_desc.iloc[upper_n - 1]
    lower = sorted_desc.iloc[-lower_n]
    scores = {}
    for name in JINWOO_v37:
        v = echo_values.get(name)
        if v is None: scores[name] = 0
        elif v >= upper: scores[name] = +1
        elif v <= lower: scores[name] = -1
        else: scores[name] = 0
    return scores


def compute_v37_2_picks_at(panel, dt, target_grades, echo_weight=1.0,
                           echo_t_start=12, echo_t_end=7):
    """v3.7.2 점수로 picks 계산 (echo_weight, look-back 가변)"""
    kospi = panel.get('_KOSPI')
    echo_scores = compute_echo_scores(panel, dt, echo_t_start, echo_t_end)

    picks = []
    scores_map = {}
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
        echo_s = echo_scores.get(name, 0) * echo_weight

        total = (체력_12점 + info['ModF'] + far_val + info['Sloan']
                + mom_s + bab_s + noa_s + echo_s)
        g = grade(total)
        scores_map[name] = total
        if g in target_grades:
            picks.append(name)
    return picks, scores_map


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


def run_v37_2_backtest(panel, years, top_grades, echo_weight=1.0,
                      echo_t_start=12, echo_t_end=7):
    target = set(top_grades.split(',')) if isinstance(top_grades, str) else set(top_grades)
    rebal = get_rebal_dates(panel, years)
    rets = []
    for i in range(len(rebal) - 1):
        d0, d1 = rebal[i], rebal[i + 1]
        picks, _ = compute_v37_2_picks_at(panel, d0, target,
                                          echo_weight, echo_t_start, echo_t_end)
        rets.append(avg_return(picks, panel, d0, d1))
    return rets


# ============================================
# 검증 4: Deflated Sharpe Ratio
# ============================================
def deflated_sharpe(sharpe, T, n_trials, skew=0, kurt=3):
    """
    Bailey & López de Prado (2014) Deflated Sharpe Ratio.

    sharpe: observed Sharpe
    T: number of returns (months)
    n_trials: number of strategies/configurations tested
    skew, kurt: return distribution moments (default normal: 0, 3)

    반환: probabilistic Sharpe ratio (PSR), passes threshold (0.95)
    """
    if T < 2: return None, False

    # Expected max Sharpe under null
    emc = 0.5772156649  # Euler-Mascheroni constant
    expected_max = math.sqrt(2 * math.log(max(n_trials, 2))) - \
                   emc / math.sqrt(2 * math.log(max(n_trials, 2)))

    # Adjusted variance of Sharpe estimate
    var = (1 - skew * sharpe + (kurt - 1) / 4 * sharpe ** 2) / (T - 1)

    # PSR
    z = (sharpe - expected_max) / math.sqrt(var) if var > 0 else 0
    # Normal CDF approximation
    psr = 0.5 * (1 + math.erf(z / math.sqrt(2)))
    return round(psr, 4), psr > 0.95


def validate_deflated_sharpe(panel, args):
    print("\n" + "=" * 90)
    print("검증 #4: Deflated Sharpe Ratio (Bailey & López de Prado 2014)")
    print("=" * 90)

    rets = run_v37_2_backtest(panel, args.years, args.top_grades, 1.0)
    m = metrics(rets)
    sharpe = m.get('Sharpe', 0)
    T = m.get('기간', 0)

    arr = np.array(rets) * 12
    if len(arr) >= 4:
        skew = float(pd.Series(arr).skew())
        kurt = float(pd.Series(arr).kurtosis()) + 3
    else:
        skew, kurt = 0, 3

    # n_trials: 우리가 시도한 변형 수
    # v3.6 / v3.7 / v3.7.1 / v3.8.1 / v3.8.2 / v3.8.3
    # v3.8.1 PIT / v3.8.2 PIT / v3.8.3 PIT
    # v3.7.2 (×0.5) / v3.7.2 (×1.0)
    # = 11개
    n_trials = 11

    psr, passed = deflated_sharpe(sharpe, T, n_trials, skew, kurt)
    print(f"  v3.7.2 (×1.0) Sharpe: {sharpe:.2f}")
    print(f"  표본 크기 T: {T}, n_trials: {n_trials}")
    print(f"  Skew: {skew:.3f}, Kurtosis: {kurt:.3f}")
    print(f"  Deflated Sharpe (PSR): {psr}")
    if passed:
        print(f"  ✅ PSR > 0.95 — 다중 비교 보정 후에도 유의 (Bailey-LdP)")
    else:
        print(f"  ⚠️ PSR ≤ 0.95 — 다중 비교 후 통계적 유의성 약함")

    return {'sharpe': sharpe, 'PSR': psr, 'passed_0.95': passed,
            'n_trials': n_trials, 'T': T,
            'skew': round(skew, 3), 'kurt': round(kurt, 3)}


# ============================================
# 검증 5: ECHO_WEIGHT sensitivity
# ============================================
def validate_echo_weight_sensitivity(panel, args):
    print("\n" + "=" * 90)
    print("검증 #5: ECHO_WEIGHT sensitivity (0.3, 0.5, 0.7, 1.0, 1.2, 1.5)")
    print("=" * 90)

    results = {}
    for w in [0.3, 0.5, 0.7, 1.0, 1.2, 1.5]:
        rets = run_v37_2_backtest(panel, args.years, args.top_grades,
                                  echo_weight=w)
        m = metrics(rets)
        results[f'w_{w}'] = m
        print(f"  w={w:.1f}: CAGR {m.get('연환산',0):>6.2f}%  "
              f"Sharpe {str(m.get('Sharpe','-')):>5s}  "
              f"MDD {m.get('MDD',0):>6.2f}%  IR(implicit) {m.get('Sharpe',0)}")

    # 최적 가중치 추정
    best_w = max(results.keys(), key=lambda k: results[k].get('연환산', 0) or 0)
    print(f"\n  → CAGR 최대 가중치: {best_w}")
    return results


# ============================================
# 검증 6: Echo look-back 변형
# ============================================
def validate_echo_lookback(panel, args):
    print("\n" + "=" * 90)
    print("검증 #6: Echo look-back 기간 변형")
    print("=" * 90)

    configs = [
        (11, 6),   # t-11 ~ t-6 (1개월 앞당김)
        (12, 7),   # t-12 ~ t-7 (Novy-Marx 2012 표준)
        (13, 8),   # t-13 ~ t-8 (1개월 늦춤)
        (14, 8),   # t-14 ~ t-8 (좀더 긴 기간)
        (12, 6),   # t-12 ~ t-6 (Echo + 최근 1개월)
    ]
    results = {}
    for t_start, t_end in configs:
        rets = run_v37_2_backtest(panel, args.years, args.top_grades,
                                  echo_t_start=t_start, echo_t_end=t_end)
        m = metrics(rets)
        results[f't-{t_start}~t-{t_end}'] = m
        marker = " ⭐" if (t_start, t_end) == (12, 7) else ""
        print(f"  t-{t_start} ~ t-{t_end}: CAGR {m.get('연환산',0):>6.2f}%  "
              f"Sharpe {str(m.get('Sharpe','-')):>5s}  "
              f"MDD {m.get('MDD',0):>6.2f}%{marker}")

    best = max(results.keys(), key=lambda k: results[k].get('연환산', 0) or 0)
    print(f"\n  → CAGR 최대 look-back: {best}")
    return results


# ============================================
# 검증 7: 표본 기간 변형
# ============================================
def validate_sample_period(panel, args):
    print("\n" + "=" * 90)
    print("검증 #7: 표본 기간 변형 (3년·4년·5년 OOS)")
    print("=" * 90)

    results = {}
    for yr in [3, 4, 5]:
        rets = run_v37_2_backtest(panel, yr, args.top_grades)
        m = metrics(rets)
        results[f'{yr}년'] = m
        print(f"  {yr}년: CAGR {m.get('연환산',0):>6.2f}%  "
              f"Sharpe {str(m.get('Sharpe','-')):>5s}  "
              f"MDD {m.get('MDD',0):>6.2f}%  기간 {m.get('기간',0)}")

    return results


# ============================================
# 검증 8: 등급 컷 변형
# ============================================
def validate_grade_cut(panel, args):
    print("\n" + "=" * 90)
    print("검증 #8: 등급 컷 변형")
    print("=" * 90)

    cuts = ['S+', 'S+,S', 'S+,S,A', 'S+,S,A,B']
    results = {}
    for cut in cuts:
        rets = run_v37_2_backtest(panel, args.years, cut)
        m = metrics(rets)
        results[cut] = m
        marker = " ⭐" if cut == 'S+,S,A' else ""
        print(f"  {cut:14s}: CAGR {m.get('연환산',0):>6.2f}%  "
              f"Sharpe {str(m.get('Sharpe','-')):>5s}  "
              f"MDD {m.get('MDD',0):>6.2f}%{marker}")

    return results


# ============================================
# 검증 9: Bootstrap 신뢰구간
# ============================================
def validate_bootstrap(panel, args):
    print("\n" + "=" * 90)
    print(f"검증 #9: Bootstrap 신뢰구간 ({args.bootstrap_n}회)")
    print("=" * 90)

    rets = np.array(run_v37_2_backtest(panel, args.years, args.top_grades))
    if len(rets) == 0:
        print("  데이터 없음")
        return {}

    boot_sharpes, boot_cagrs = [], []
    np.random.seed(42)
    for _ in range(args.bootstrap_n):
        idx = np.random.choice(len(rets), len(rets), replace=True)
        boot = rets[idx]
        if boot.std() > 0:
            ann = (1 + boot.mean()) ** 12 - 1
            vol = boot.std() * np.sqrt(12)
            boot_sharpes.append(ann / vol)
            cum = float(np.prod(1 + boot) - 1)
            boot_cagrs.append((1 + cum) ** (12 / len(boot)) - 1)

    boot_sharpes = np.array(boot_sharpes)
    boot_cagrs = np.array(boot_cagrs) * 100

    sharpe_5 = float(np.percentile(boot_sharpes, 5))
    sharpe_50 = float(np.percentile(boot_sharpes, 50))
    sharpe_95 = float(np.percentile(boot_sharpes, 95))
    cagr_5 = float(np.percentile(boot_cagrs, 5))
    cagr_50 = float(np.percentile(boot_cagrs, 50))
    cagr_95 = float(np.percentile(boot_cagrs, 95))

    print(f"  Sharpe 90% CI: [{sharpe_5:.2f}, {sharpe_95:.2f}]  median {sharpe_50:.2f}")
    print(f"  CAGR   90% CI: [{cagr_5:.2f}%, {cagr_95:.2f}%]  median {cagr_50:.2f}%")
    print(f"  KOSPI CAGR: 29.43% — v3.7.2 CAGR 하위 5% {cagr_5:.2f}%도 KOSPI 능가? "
          f"{'✅' if cagr_5 > 29.43 else '⚠️'}")
    print(f"  v3.6 CAGR: 69.51% — v3.7.2 CAGR 중위 {cagr_50:.2f}%가 v3.6 능가? "
          f"{'✅' if cagr_50 > 69.51 else '⚠️'}")

    return {
        'sharpe_ci_90': [round(sharpe_5, 3), round(sharpe_95, 3)],
        'sharpe_median': round(sharpe_50, 3),
        'cagr_ci_90_%': [round(cagr_5, 2), round(cagr_95, 2)],
        'cagr_median_%': round(cagr_50, 2),
        'n_bootstrap': args.bootstrap_n,
    }


def main():
    args = parse_args()
    print("=" * 90)
    print("진우퀀트 v3.7.2 학술 robustness 검증 (Tier 2 + Tier 3)")
    print(f"시간: {datetime.now()}")
    print("=" * 90)

    print("\n📊 데이터 수집 (5년)...")
    panel = fetch_long_panel(5)
    print(f"  18종목 + KOSPI 완료")

    results = {}
    results['deflated_sharpe'] = validate_deflated_sharpe(panel, args)
    results['echo_weight_sens'] = validate_echo_weight_sensitivity(panel, args)
    results['echo_lookback'] = validate_echo_lookback(panel, args)
    results['sample_period'] = validate_sample_period(panel, args)
    results['grade_cut'] = validate_grade_cut(panel, args)
    results['bootstrap'] = validate_bootstrap(panel, args)

    out = BASE / f'validate_robustness_{datetime.now().strftime("%Y%m%d_%H%M")}.json'
    out.write_text(json.dumps(results, ensure_ascii=False, indent=2, default=str),
                   encoding='utf-8')
    print(f"\n💾 저장: {out}")
    print("\n" + "=" * 90)
    print("✅ Robustness 검증 완료")
    print("=" * 90)


if __name__ == '__main__':
    main()
