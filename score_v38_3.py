#!/usr/bin/env python3
"""
진우퀀트 v3.8.3 — Echo Momentum 추가 (보조 실험군)

v3.8.2 위에 한 팩터 추가:
  - Echo_score: Novy-Marx 2012 Echo Momentum
    * 정의: t-12 ~ t-7 (중간 6개월) 누적수익률
    * NOT 6M-12M 가속 (Claude 초기 오류 수정됨)
    * NOT 단순 12M momentum (장지원 2017 한국 검증)

GPT 검증 (2026-05-28):
  - 18종목 대형주 universe에서 약화 가능 (소형주·개인 비중 효과)
  - **±0.5 저가중치**부터 시작
  - 또는 보조 실험군으로 분리 운영
  - tail risk 동반 측정 (엄철준 2024)

학술 근거:
  - S3 Novy-Marx (2012) JFE 103: Echo (t-12~t-7) > recent past
  - S6 장지원 (2017) 재무연구 30(3):
    한국 1999-2015, 중기 6M 모멘텀 월 1.51% 비정상 수익률
    효과 강한 조건: 소형주·고유동성·개인 비중↑·상승장
  - A5 엄철준 (2024) 재무관리연구 41(4):
    Echo 승자 포트폴리오 right-tail risk → 추후 reversal 위험

회귀:
  USE_ECHO_FACTOR = False → v3.8.2 동작
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
from score_v38_2 import compute_ag_scores, GP_WEIGHT, AG_WEIGHT

# ============================================
# v3.8.3 토글
# ============================================
USE_GP_FACTOR = True
USE_AG_FACTOR = True
USE_ECHO_FACTOR = True

# GPT 권장: 대형주 universe에서 ±0.5 저가중치
ECHO_WEIGHT = 0.5


# ============================================
# v3.8.3: Echo Momentum (Novy-Marx 2012)
# ============================================
def compute_echo(series, days_per_month=21):
    """
    Echo Momentum = t-12 ~ t-7 누적수익률.

    series: 일별 종가 시계열 (DatetimeIndex)
    반환: (P_{t-7} / P_{t-12}) - 1

    핵심:
      - t-12 ≈ 252일 전 (12개월)
      - t-7 ≈ 147일 전 (7개월)
      - 가까운 6개월 (t-6 ~ t-1)은 사용 안 함 (Novy-Marx 2012 핵심)
    """
    if series is None or len(series) < 253:
        return None
    p_t12 = series.iloc[-12 * days_per_month]
    p_t7 = series.iloc[-7 * days_per_month]
    if p_t12 is None or p_t12 == 0:
        return None
    return float(p_t7 / p_t12 - 1)


def compute_echo_scores(panel):
    """
    18종목 Echo 3분위 점수.

    상위 20% (Echo 강) = +1
    중위 60% = 0
    하위 20% (Echo 약) = -1
    """
    echo_values = {}
    for name in JINWOO_v37:
        series = panel.get(name)
        v = compute_echo(series)
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
    return scores, echo_values


# ============================================
# 점수 산출 (v3.7.1 + GP + AG + Echo)
# ============================================
def compute_scores(panel, quality_data):
    kospi = panel.get('_KOSPI')
    gp_scores = compute_gp_scores(quality_data) if USE_GP_FACTOR else {}
    ag_scores = compute_ag_scores(quality_data) if USE_AG_FACTOR else {}
    if USE_ECHO_FACTOR:
        echo_scores, echo_values = compute_echo_scores(panel)
    else:
        echo_scores, echo_values = {}, {}

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
        echo_score = echo_scores.get(name, 0) * ECHO_WEIGHT if USE_ECHO_FACTOR else 0

        체력_최종 = (체력_12점 + info['ModF'] + far_val + info['Sloan']
                    + mom12_score + bab_score + noa_score
                    + gp_score + ag_score + echo_score)

        echo_val = echo_values.get(name)

        rows.append({
            '종목': name, '코드': info['코드'], '산업': info['산업'],
            'F_korean': info['F_korean'],
            '체력_12점': round(체력_12점, 2),
            'ModF': info['ModF'], 'FAR': far_val, 'FAR_신호': far_signal,
            'Sloan': info['Sloan'],
            'Mom12': mom12_score, 'BAB': bab_score, 'NOA': noa_score,
            'GP': round(gp_score, 1) if gp_score != int(gp_score) else int(gp_score),
            'AG': round(ag_score, 1) if ag_score != int(ag_score) else int(ag_score),
            'Echo': round(echo_score, 1) if echo_score != int(echo_score) else int(echo_score),
            'Echo값_%': round(echo_val * 100, 2) if echo_val is not None else None,
            'r_mom12_%': round(r_mom12 * 100, 2) if r_mom12 is not None else None,
            'r_1m_%': round(r_1m * 100, 2) if r_1m is not None else None,
            'β_60d': round(beta60, 3) if beta60 is not None else None,
            '체력_최종': round(체력_최종, 2),
            '등급': grade(체력_최종),
            '신규': info['신규'],
        })

    df = pd.DataFrame(rows).sort_values('체력_최종', ascending=False).reset_index(drop=True)
    df['순위'] = df.index + 1
    return df


def main():
    print("=" * 80)
    print(f"진우퀀트 v3.8.3 자동 실행  (GP + AG + Echo 보조)")
    print(f"가중치: GP × {GP_WEIGHT}, AG × {AG_WEIGHT}, Echo × {ECHO_WEIGHT} (GPT 권장 저가중치)")
    print(f"시간: {datetime.now()}")
    print("=" * 80)

    quality_data = load_quality_data()
    print(f"\n📁 Quality 캐시: {len(quality_data)}종목")

    panel = fetch_price_panel()
    df = compute_scores(panel, quality_data)

    prev_csv = BASE / 'v38_3_scores_latest.csv'
    changes = detect_changes(df, prev_csv)

    far_signals = []
    for _, r in df.iterrows():
        if r['FAR_신호'] in ['FAR_BUY', 'FAR_AVOID']:
            far_signals.append({
                'name': r['종목'], 'signal': r['FAR_신호'],
                'r_1m': r['r_mom12_%']
            })

    print("\n" + "=" * 80)
    print("v3.8.3 18종목 점수표")
    print("=" * 80)
    print(df[['순위', '종목', '체력_최종', '등급',
              'Mom12', 'BAB', 'GP', 'AG', 'Echo',
              'Echo값_%']].to_string(index=False))

    print("\n" + "=" * 80)
    print("Echo Momentum 분포 (t-12 ~ t-7 누적, Novy-Marx 2012)")
    print("=" * 80)
    for score, group in df.groupby('Echo'):
        names = group.sort_values('Echo값_%', ascending=False)['종목'].tolist()
        print(f"  Echo={score:+}: {len(group)}종목 → {', '.join(names)}")

    df.to_csv(BASE / 'v38_3_scores_latest.csv', index=False)
    html = _generate_html_v37(df, changes, far_signals)
    html = html.replace('진우퀀트 v3.7 (Mom12·BAB·NOA)',
                        '진우퀀트 v3.8.3 (GP+AG+Echo)')
    html = html.replace('v3.7 (Mom12·BAB·NOA)', 'v3.8.3 (GP+AG+Echo)')
    (BASE / 'dashboard_v38_3.html').write_text(html, encoding='utf-8')

    summary = {
        'version': 'v3.8.3',
        'factors': 'GP + AG + Echo Momentum (t-12~t-7)',
        'weights': {'GP': GP_WEIGHT, 'AG': AG_WEIGHT, 'Echo': ECHO_WEIGHT},
        'timestamp': datetime.now().isoformat(),
        '등급_분포': df['등급'].value_counts().to_dict(),
        'Echo_분포': df['Echo'].value_counts().to_dict(),
        '변동': changes,
        'top3': df.head(3)[['종목', '체력_최종', '등급', 'Echo', 'Echo값_%']].to_dict('records'),
    }
    (BASE / 'v38_3_summary_latest.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding='utf-8')

    print(f"\n✅ 저장: v38_3_scores_latest.csv, dashboard_v38_3.html, v38_3_summary_latest.json")


if __name__ == '__main__':
    main()
