#!/usr/bin/env python3
"""
진우퀀트 — Factor Correlation Matrix 분석 (v3.8 진단)

목적: v3.8.1 alpha 손실 원인 진단 + v3.8.2 (GP+AG) 설계 사전 검증

분석 대상 (9개 팩터):
  - F_korean (v3.6 기본 quality)
  - ModF (v3.6 산업보정)
  - FAR (v3.6 1M reversal)
  - Sloan (v3.6 accrual)
  - Mom12 (v3.7)
  - BAB (v3.7.1)
  - NOA (v3.7)
  - GP (v3.8.1)
  - AG (v3.8.2 예정 — 본 분석에서 계산)

핵심 질문 (GPT Q3):
  - GP와 AG의 상관계수가 0.6 이상이면 중복 신호 위험
  - GP와 기존 팩터(F_korean·Sloan·NOA)의 중복도 확인
  - 어떤 팩터가 LIG넥스원·삼양식품에서 충돌하는지 진단

학술 근거:
  - GPT Q1 빠진 영역 #4: factor correlation matrix
  - Cooper-Gulen-Schill 2008: AG factor 정의
  - 노지혜 외 2023: 한국 8요인 25년 robust 확인

방법론:
  - 49개 rebalance 시점 × 18종목 = 882 obs
  - 각 obs별 9 factor score 계산
  - Pearson + Spearman 상관계수
  - 시간 가변 factor만 (F_korean·ModF·Sloan·NOA·GP는 종목별 상수, 시점 무관)
  - 시간 가변: Mom12·BAB·FAR·AG (분기 갱신)

출력:
  - factor_correlation_matrix.csv (9x9 Pearson)
  - factor_correlation_spearman.csv (9x9 Spearman)
  - factor_correlation_diagnosis.json
"""

import sys
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
    far_trigger,
)
from score_v37_1 import bab_to_score as bab_to_score_v371
from score_v38_1 import load_quality_data, compute_gp_scores


# ============================================
# Asset Growth (시점별) — 본 분석에서 정의
# ============================================
def compute_ag_scores_from_cache(quality_data):
    """
    단일 시점 quality cache에서 AG_score 산출 (3분위, GPT 검증).
    상위 20% (낮은 자산성장) = +1
    중위 60% = 0
    하위 20% (높은 자산성장) = -1

    Cooper-Gulen-Schill 2008: 자산성장 낮을수록 미래 수익률 높음
    """
    ag_values = {}
    for name, q in quality_data.items():
        sector = q.get('업종')
        if sector == '제조업':
            ag_values[name] = q.get('Asset_Growth')
        # 금융주는 자산성장 의미 다름 (자산 증가가 곧 사업 확장)
        # → 중립 처리

    valid_values = {k: v for k, v in ag_values.items() if v is not None}
    if not valid_values:
        return {name: 0 for name in JINWOO_v37}

    n = len(valid_values)
    upper_n = max(1, round(n * 0.2))
    lower_n = max(1, round(n * 0.2))

    sorted_asc = pd.Series(valid_values).sort_values(ascending=True)
    # 낮은 자산성장 = 상위 (Cooper 2008 정의)
    upper_threshold = sorted_asc.iloc[upper_n - 1]
    lower_threshold = sorted_asc.iloc[-lower_n]

    scores = {}
    for name in JINWOO_v37:
        v = ag_values.get(name)
        if v is None:
            scores[name] = 0
        elif v <= upper_threshold:  # 낮은 자산성장
            scores[name] = +1
        elif v >= lower_threshold:  # 높은 자산성장
            scores[name] = -1
        else:
            scores[name] = 0
    return scores


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
    print(f"\n📊 가격 데이터 수집 ({start.date()} → {end.date()}):")

    df = fdr.DataReader(KOSPI_CODE, start.strftime('%Y-%m-%d'),
                        end.strftime('%Y-%m-%d'))
    panel['_KOSPI'] = df['Close']
    print(f"  KOSPI: {len(df)} 영업일")

    for name, info in JINWOO_v37.items():
        try:
            df = fdr.DataReader(info['코드'], start.strftime('%Y-%m-%d'),
                                end.strftime('%Y-%m-%d'))
            panel[name] = df['Close']
        except Exception as e:
            panel[name] = None
    return panel


# ============================================
# 각 rebalance 시점 × 18종목별 factor scores 수집
# ============================================
def collect_factor_panel(panel, gp_scores, ag_scores, years=4):
    """49개 시점 × 18종목 × 9 factor 데이터 수집"""
    kospi = panel.get('_KOSPI')
    end_dt = kospi.index[-1]
    start_dt = end_dt - pd.DateOffset(years=years)
    backtest_period = kospi[(kospi.index >= start_dt) &
                            (kospi.index <= end_dt)]
    rebal_dates = backtest_period.resample('MS').first().dropna().index
    rebal_dates = [kospi.index[kospi.index.get_indexer([d], method='bfill')[0]]
                   for d in rebal_dates if d <= end_dt]
    rebal_dates = sorted(set(rebal_dates))

    records = []
    for dt in rebal_dates:
        for name, info in JINWOO_v37.items():
            series = panel.get(name)
            if series is None or len(series) == 0:
                continue
            s_cut = series[series.index <= dt]
            k_cut = kospi[kospi.index <= dt]
            if len(s_cut) < 253:
                continue

            # 시점 무관 (상수)
            f_korean = info['F_korean']
            mod_f = info['ModF']
            sloan = info['Sloan']
            noa = info.get('NOA', 0)
            gp = gp_scores.get(name, 0)
            ag = ag_scores.get(name, 0)

            # 시점 가변
            체력_12점 = f_korean * (12 / 9.001)
            if len(s_cut) >= 22:
                r_1m = s_cut.iloc[-1] / s_cut.iloc[-21] - 1
            else:
                r_1m = None
            far_val, _ = far_trigger(체력_12점, r_1m)

            r_mom12 = compute_mom12(s_cut)
            beta60 = compute_beta60(s_cut, k_cut)
            mom12_s = mom12_to_score(r_mom12)
            bab_s = bab_to_score_v371(beta60)
            noa_s = noa_to_score(noa)

            records.append({
                'date': dt.strftime('%Y-%m-%d'),
                'name': name,
                'F_korean': f_korean,
                'ModF': mod_f,
                'FAR': far_val,
                'Sloan': sloan,
                'Mom12': mom12_s,
                'BAB': bab_s,
                'NOA': noa_s,
                'GP': gp,
                'AG': ag,
            })

    return pd.DataFrame(records)


# ============================================
# Correlation 분석
# ============================================
def analyze_correlations(df):
    factor_cols = ['F_korean', 'ModF', 'FAR', 'Sloan',
                   'Mom12', 'BAB', 'NOA', 'GP', 'AG']
    sub = df[factor_cols]

    pearson = sub.corr(method='pearson')
    spearman = sub.corr(method='spearman')

    pearson.to_csv(BASE / 'factor_correlation_pearson.csv', encoding='utf-8-sig')
    spearman.to_csv(BASE / 'factor_correlation_spearman.csv', encoding='utf-8-sig')

    return pearson, spearman


def diagnose(pearson, spearman, df):
    """주요 진단 항목 추출"""
    diagnosis = {}

    # 1. 강한 상관 (절대값 ≥ 0.6) — GPT 임계값
    strong_pairs = []
    factors = pearson.columns.tolist()
    for i in range(len(factors)):
        for j in range(i + 1, len(factors)):
            r = pearson.iloc[i, j]
            if abs(r) >= 0.6:
                strong_pairs.append({
                    'pair': f"{factors[i]} vs {factors[j]}",
                    'pearson': round(r, 3),
                    'spearman': round(spearman.iloc[i, j], 3),
                    'warning': 'GP·AG 중복 신호 위험' if {factors[i], factors[j]} == {'GP', 'AG'} else
                               '중복 신호 (가중치 축소 권장)',
                })
    diagnosis['강한_상관_0.6이상'] = strong_pairs

    # 2. GP vs 다른 quality 팩터
    gp_corr = pearson['GP'].drop('GP').sort_values(ascending=False)
    diagnosis['GP_vs_others'] = {
        k: round(v, 3) for k, v in gp_corr.items()
    }

    # 3. AG vs 다른 팩터
    ag_corr = pearson['AG'].drop('AG').sort_values(ascending=False)
    diagnosis['AG_vs_others'] = {
        k: round(v, 3) for k, v in ag_corr.items()
    }

    # 4. GP·AG 결합 안전성 판단
    gp_ag = pearson.loc['GP', 'AG']
    if abs(gp_ag) < 0.3:
        verdict = "GP+AG 결합 안전 (독립 신호) — v3.8.2 진입 권장"
    elif abs(gp_ag) < 0.6:
        verdict = f"GP+AG 결합 주의 (상관 {gp_ag:.2f}) — 가중치 축소 권장 (±0.7)"
    else:
        verdict = f"GP+AG 결합 위험 (상관 {gp_ag:.2f}) — 한 팩터만 선택 필요"
    diagnosis['GP_AG_결합_판단'] = {
        '상관계수': round(gp_ag, 3),
        '판정': verdict,
    }

    # 5. 종목별 GP·AG 점수 분포
    summary_by_stock = df.groupby('name')[['GP', 'AG']].first()
    summary_by_stock['GP+AG'] = summary_by_stock['GP'] + summary_by_stock['AG']
    diagnosis['종목별_점수'] = summary_by_stock.to_dict('index')

    return diagnosis


def main():
    print("=" * 80)
    print("진우퀀트 — Factor Correlation Matrix 분석")
    print(f"시간: {datetime.now()}")
    print("=" * 80)

    # 1. quality cache 로드
    quality_data = load_quality_data()
    gp_scores = compute_gp_scores(quality_data)
    ag_scores = compute_ag_scores_from_cache(quality_data)
    print(f"\n📁 Quality 캐시 로드: {len(quality_data)}종목")
    print(f"  GP +1: {[k for k,v in gp_scores.items() if v == +1]}")
    print(f"  GP -1: {[k for k,v in gp_scores.items() if v == -1]}")
    print(f"  AG +1 (낮은 성장): {[k for k,v in ag_scores.items() if v == +1]}")
    print(f"  AG -1 (높은 성장): {[k for k,v in ag_scores.items() if v == -1]}")

    # 2. 가격 데이터
    panel = fetch_long_panel(years=4)
    if panel.get('_KOSPI') is None:
        print("❌ KOSPI 데이터 실패")
        sys.exit(1)

    # 3. Factor panel 수집
    print("\n📊 Factor panel 수집 중 (49 시점 × 18 종목)...")
    df = collect_factor_panel(panel, gp_scores, ag_scores)
    print(f"  총 obs: {len(df)} (예상 ~882)")

    # 4. 상관계수
    print("\n🔍 상관계수 계산...")
    pearson, spearman = analyze_correlations(df)

    print("\n" + "=" * 80)
    print("Pearson 상관계수 (시점 × 종목 pooled)")
    print("=" * 80)
    print(pearson.round(3).to_string())

    # 5. 진단
    diagnosis = diagnose(pearson, spearman, df)

    print("\n" + "=" * 80)
    print("진단 결과")
    print("=" * 80)

    print("\n📌 강한 상관 (|r| ≥ 0.6, GPT 임계값):")
    if diagnosis['강한_상관_0.6이상']:
        for sp in diagnosis['강한_상관_0.6이상']:
            print(f"  {sp['pair']:30s} Pearson {sp['pearson']:+.3f} Spearman {sp['spearman']:+.3f}")
            print(f"    → {sp['warning']}")
    else:
        print("  없음 — 모든 팩터가 충분히 독립적")

    print(f"\n📌 GP vs 다른 팩터 상관:")
    for k, v in diagnosis['GP_vs_others'].items():
        marker = " ⚠️" if abs(v) >= 0.5 else ("" if abs(v) >= 0.3 else " ✓")
        print(f"  GP vs {k:10s}: {v:+.3f}{marker}")

    print(f"\n📌 AG vs 다른 팩터 상관:")
    for k, v in diagnosis['AG_vs_others'].items():
        marker = " ⚠️" if abs(v) >= 0.5 else ("" if abs(v) >= 0.3 else " ✓")
        print(f"  AG vs {k:10s}: {v:+.3f}{marker}")

    print(f"\n📌 GP+AG 결합 판단:")
    j = diagnosis['GP_AG_결합_판단']
    print(f"  상관계수: {j['상관계수']:+.3f}")
    print(f"  판정: {j['판정']}")

    # 6. 저장
    out_json = {
        'timestamp': datetime.now().isoformat(),
        'n_obs': len(df),
        'pearson_matrix': pearson.round(4).to_dict(),
        'spearman_matrix': spearman.round(4).to_dict(),
        'diagnosis': diagnosis,
    }
    out_path = BASE / 'factor_correlation_diagnosis.json'
    out_path.write_text(json.dumps(out_json, ensure_ascii=False, indent=2,
                                   default=str), encoding='utf-8')

    print(f"\n💾 저장:")
    print(f"  - factor_correlation_pearson.csv")
    print(f"  - factor_correlation_spearman.csv")
    print(f"  - factor_correlation_diagnosis.json")


if __name__ == '__main__':
    main()
