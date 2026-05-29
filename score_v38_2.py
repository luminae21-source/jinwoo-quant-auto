#!/usr/bin/env python3
"""
진우퀀트 v3.8.2 — Asset Growth 추가 (GP + AG 결합)

v3.7.1 위에 두 팩터 추가:
  - GP_score: Gross Profit / Total Assets (Novy-Marx 2013, v3.8.1)
  - AG_score: Asset Growth (Cooper-Gulen-Schill 2008, 신규)
    * 낮은 자산성장 +1 (성장 투자 적음 = quality)
    * 중위 0
    * 높은 자산성장 -1 (과잉 투자)

GPT 검증 (2026-05-28):
  - GP·AG는 다른 경제적 의미 (수익성 vs 자본 배분)
  - GP·AG 상관계수 < 0.6 → 둘 다 ±1
  - 0.6 ≤ 상관 < 0.8 → 가중치 축소
  - ≥ 0.8 → 한 팩터만
  - production 후보 우선순위 (GPT 권장)

학술 근거:
  - S2 Cooper·Gulen·Schill (2008) JF 63(4): 자산성장률 음의 예측력
  - S5 노지혜·김동순·김현도 (2023) 대한경영학회지 36(1):
    한국 1995-2020 25년 OOS, 수익성·투자·비유동성 robust 3요인
  - 손판도 (2012) 금융공학연구 11(2): 한국 자산증가 음의 유의 관계

선행:
  - fetch_dart_quality.py 실행 → quality_data_cache.json 생성
  - factor_correlation_v38.py 결과 (GP·AG 상관관계 확인)

v3.8.1 회귀:
  USE_AG_FACTOR = False → v3.8.1 (GP만)
"""

import sys
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

BASE = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE))

from score_v37 import (
    JINWOO_v37, KOSPI_CODE, USE_V37_FACTORS,
    fetch_price_panel,
    compute_1m_return, compute_mom12, compute_beta60,
    mom12_to_score, noa_to_score,
    far_trigger, grade,
    detect_changes,
    generate_html as _generate_html_v37,
)
from score_v37_1 import bab_to_score
from score_v38_1 import load_quality_data, compute_gp_scores

# ============================================
# v3.8.2 토글
# ============================================
USE_GP_FACTOR = True   # v3.8.1 GP
USE_AG_FACTOR = True   # v3.8.2 AG (신규)

# GPT 검증 권장: 상관관계 확인 후 결정
# factor_correlation_v38.py 결과로 조정
AG_WEIGHT = 1.0  # 0.6 ≤ 상관 < 0.8 시 0.7로 축소 권장
GP_WEIGHT = 1.0


# ============================================
# v3.8.2: Asset Growth score
# ============================================
def compute_ag_scores(quality_data):
    """
    18종목 Asset Growth 3분위 점수.

    Cooper-Gulen-Schill 2008:
      낮은 자산성장 → 미래 수익률 높음 (+1)
      높은 자산성장 → 미래 수익률 낮음 (-1)

    제조업 16종목만 적용 (금융주 자산성장은 사업 확장이라 의미 다름).
    """
    ag_values = {}
    for name, q in quality_data.items():
        sector = q.get('업종')
        if sector == '제조업':
            v = q.get('Asset_Growth')
            if v is not None:
                ag_values[name] = v

    if not ag_values:
        return {name: 0 for name in JINWOO_v37}

    n = len(ag_values)
    upper_n = max(1, round(n * 0.2))   # 상위 20% (낮은 성장)
    lower_n = max(1, round(n * 0.2))   # 하위 20% (높은 성장)

    sorted_asc = pd.Series(ag_values).sort_values(ascending=True)
    low_threshold = sorted_asc.iloc[upper_n - 1]   # 낮은 성장 cutoff
    high_threshold = sorted_asc.iloc[-lower_n]     # 높은 성장 cutoff

    scores = {}
    for name in JINWOO_v37:
        v = ag_values.get(name)
        if v is None:
            scores[name] = 0  # 금융주 + 데이터 부족
        elif v <= low_threshold:
            scores[name] = +1   # 낮은 자산성장 = quality
        elif v >= high_threshold:
            scores[name] = -1   # 높은 자산성장 = 과잉투자 우려
        else:
            scores[name] = 0
    return scores


# ============================================
# 점수 산출 (v3.7.1 + GP + AG)
# ============================================
def compute_scores(panel, quality_data):
    kospi = panel.get('_KOSPI')
    gp_scores = compute_gp_scores(quality_data) if USE_GP_FACTOR else {}
    ag_scores = compute_ag_scores(quality_data) if USE_AG_FACTOR else {}

    rows = []
    for name, info in JINWOO_v37.items():
        series = panel.get(name)
        체력_12점 = info['F_korean'] * (12 / 9.001)
        r_1m = compute_1m_return(series)
        far_val, far_signal = far_trigger(체력_12점, r_1m)

        if USE_V37_FACTORS:
            r_mom12 = compute_mom12(series)
            beta60 = compute_beta60(series, kospi)
            mom12_score = mom12_to_score(r_mom12)
            bab_score = bab_to_score(beta60)
            noa_score = noa_to_score(info.get('NOA', 0))
        else:
            r_mom12, beta60 = None, None
            mom12_score = bab_score = noa_score = 0

        gp_score = gp_scores.get(name, 0) * GP_WEIGHT if USE_GP_FACTOR else 0
        ag_score = ag_scores.get(name, 0) * AG_WEIGHT if USE_AG_FACTOR else 0

        체력_최종 = (체력_12점 + info['ModF'] + far_val + info['Sloan']
                    + mom12_score + bab_score + noa_score
                    + gp_score + ag_score)

        q_info = quality_data.get(name, {})
        sector = q_info.get('업종', '제조업')
        if sector == '제조업':
            q_gp = q_info.get('GP_Assets')
            q_ag = q_info.get('Asset_Growth')
            q_type = 'GP/Assets'
        else:
            q_gp = q_info.get('ROE_approx')
            q_ag = None
            q_type = 'ROE'

        rows.append({
            '종목': name, '코드': info['코드'], '산업': info['산업'],
            'F_korean': info['F_korean'],
            '체력_12점': round(체력_12점, 2),
            'ModF': info['ModF'], 'FAR': far_val, 'FAR_신호': far_signal,
            'Sloan': info['Sloan'],
            'Mom12': mom12_score, 'BAB': bab_score, 'NOA': noa_score,
            'GP': round(gp_score, 1) if gp_score != int(gp_score) else int(gp_score),
            'AG': round(ag_score, 1) if ag_score != int(ag_score) else int(ag_score),
            'Q_지표': q_type,
            'GP값': round(q_gp, 4) if q_gp is not None else None,
            'AG값_%': round(q_ag * 100, 2) if q_ag is not None else None,
            'r_mom12_%': round(r_mom12 * 100, 2) if r_mom12 is not None else None,
            'β_60d': round(beta60, 3) if beta60 is not None else None,
            '체력_최종': round(체력_최종, 2),
            '등급': grade(체력_최종),
            'r_1m_%': round(r_1m * 100, 2) if r_1m is not None else None,
            '신규': info['신규'],
        })

    df = pd.DataFrame(rows).sort_values('체력_최종', ascending=False).reset_index(drop=True)
    df['순위'] = df.index + 1
    return df


def main():
    print("=" * 80)
    print(f"진우퀀트 v3.8.2 자동 실행  (GP + Asset Growth)")
    print(f"가중치: GP × {GP_WEIGHT}, AG × {AG_WEIGHT}")
    print(f"시간: {datetime.now()}")
    print("=" * 80)

    quality_data = load_quality_data()
    print(f"\n📁 Quality 캐시 로드: {len(quality_data)}종목")

    panel = fetch_price_panel()
    df = compute_scores(panel, quality_data)

    prev_csv = BASE / 'v38_2_scores_latest.csv'
    changes = detect_changes(df, prev_csv)

    far_signals = []
    for _, r in df.iterrows():
        if r['FAR_신호'] in ['FAR_BUY', 'FAR_AVOID']:
            far_signals.append({
                'name': r['종목'], 'signal': r['FAR_신호'], 'r_1m': r['r_1m_%']
            })

    print("\n" + "=" * 80)
    print("v3.8.2 18종목 점수표")
    print("=" * 80)
    print(df[['순위', '종목', '체력_최종', '등급',
              'Mom12', 'BAB', 'NOA', 'GP', 'AG',
              'GP값', 'AG값_%']].to_string(index=False))

    print("\n" + "=" * 80)
    print("GP·AG 점수 분포")
    print("=" * 80)
    print("\nGP 분포:")
    for score, group in df.groupby('GP'):
        print(f"  GP={score:+}: {len(group)}종목 → {', '.join(group['종목'].tolist())}")
    print("\nAG 분포:")
    for score, group in df.groupby('AG'):
        print(f"  AG={score:+}: {len(group)}종목 → {', '.join(group['종목'].tolist())}")

    # 결합 점수 분석
    df['GP+AG'] = df['GP'] + df['AG']
    print("\nGP+AG 결합:")
    for score, group in df.groupby('GP+AG'):
        print(f"  GP+AG={score:+}: {len(group)}종목 → {', '.join(group['종목'].tolist())}")

    df.to_csv(BASE / 'v38_2_scores_latest.csv', index=False)
    html = _generate_html_v37(df, changes, far_signals)
    html = html.replace('진우퀀트 v3.7 (Mom12·BAB·NOA)',
                        '진우퀀트 v3.8.2 (GP+AG)')
    html = html.replace('v3.7 (Mom12·BAB·NOA)', 'v3.8.2 (GP+AG)')
    (BASE / 'dashboard_v38_2.html').write_text(html, encoding='utf-8')

    summary = {
        'version': 'v3.8.2',
        'factors': 'GP + Asset Growth',
        'weights': {'GP': GP_WEIGHT, 'AG': AG_WEIGHT},
        'timestamp': datetime.now().isoformat(),
        '등급_분포': df['등급'].value_counts().to_dict(),
        'GP_분포': df['GP'].value_counts().to_dict(),
        'AG_분포': df['AG'].value_counts().to_dict(),
        '변동': changes,
        'far_신호': far_signals,
        'top3': df.head(3)[['종목', '체력_최종', '등급', 'GP', 'AG']].to_dict('records'),
        'bottom3': df.tail(3)[['종목', '체력_최종', '등급', 'GP', 'AG']].to_dict('records'),
    }
    (BASE / 'v38_2_summary_latest.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding='utf-8')

    print(f"\n✅ 저장 완료:")
    print(f"  - v38_2_scores_latest.csv")
    print(f"  - dashboard_v38_2.html")
    print(f"  - v38_2_summary_latest.json")


if __name__ == '__main__':
    main()
