#!/usr/bin/env python3
"""
진우퀀트 v3.7.1 — BAB 임계값 재조정

v3.7 attribution 결과 (2026-05-24):
  - KT&G 100% 포함 + 아모레퍼시픽 42.9% 포함 → 강세장 -2.11%p alpha
  - 반도체 트리오 BAB -1 ~ -2 페널티로 비중 희석 → -7.91%p 누적기여 손실
  - 그러나 NAVER 디커플링 회피 +4.56%p → BAB 자체는 유지 가치 있음

v3.7.1 조정:
  - BAB 임계값을 더 엄격하게 (저β·고β 둘 다 임계 완화)
    v3.7   : <0.7→+2, <0.9→+1, <1.1→0, <1.3→-1, >1.3→-2
    v3.7.1 : <0.4→+2, <0.7→+1, <1.2→0, <1.5→-1, >1.5→-2

  - 18종목 예상 영향 (오늘 시점 β 기준):
    * KT&G (β=0.26)        : +2 유지   ← 진정한 방어주만
    * 한화에어로 (β=0.12)   : +2 유지
    * 삼양식품 (β=0.32)     : +2 유지
    * 아모레퍼시픽 (β=0.48) : +2 → +1 ✅ (과편입 해결)
    * LIG·KB·알테·NAVER    : +1 → +1 유지 또는 +1
    * 카카오 (β=0.78)       :  0 → 0
    * 삼성물산 (β=1.22)     : -1 → 0  ✅ (페널티 제거)
    * 삼성전자 (β=1.25)     : -1 → 0  ✅
    * 한미반도체 (β=1.33)   : -2 → -1 ✅ (완화)
    * SK하이닉스 (β=1.43)   : -2 → -1 ✅

핵심: 방어주 과편입 해소 + 반도체 페널티 완화. NAVER 회피 효과는 Mom12로 유지.
"""

import sys
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

BASE = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE))

# v3.7 자산 재사용 (코드 중복 최소화)
from score_v37 import (
    JINWOO_v37, KOSPI_CODE, USE_V37_FACTORS,
    fetch_price_panel,
    compute_1m_return, compute_mom12, compute_beta60,
    mom12_to_score, noa_to_score,
    far_trigger, grade,
    detect_changes,
    generate_html as _generate_html_v37,
)


# ============================================
# v3.7.1: BAB 임계값 재조정 (이 함수만 다름)
# ============================================
def bab_to_score(beta):
    """v3.7.1: 임계값 0.4/0.7/1.2/1.5"""
    if beta is None: return 0
    if beta < 0.4:  return +2   # 진정한 방어주 (KT&G·한화에어로·삼양식품)
    if beta < 0.7:  return +1   # 일반 저β (아모레·KB·알테·NAVER)
    if beta < 1.2:  return 0    # 시장 동조 폭 넓힘
    if beta < 1.5:  return -1   # 약한 페널티
    return -2                    # 매우 고β만 강페널티


# ============================================
# 점수 산출 (v3.7과 동일, BAB 함수만 다름)
# ============================================
def compute_scores(panel):
    kospi = panel.get('_KOSPI')
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
            bab_score = bab_to_score(beta60)         # ← v3.7.1 함수
            noa_score = noa_to_score(info.get('NOA', 0))
        else:
            r_mom12, beta60 = None, None
            mom12_score = bab_score = noa_score = 0

        체력_최종 = (체력_12점 + info['ModF'] + far_val + info['Sloan']
                    + mom12_score + bab_score + noa_score)

        rows.append({
            '종목': name, '코드': info['코드'], '산업': info['산업'],
            'F_korean': info['F_korean'],
            '체력_12점': round(체력_12점, 2),
            'ModF': info['ModF'], 'FAR': far_val, 'FAR_신호': far_signal,
            'Sloan': info['Sloan'],
            'Mom12': mom12_score, 'BAB': bab_score, 'NOA': noa_score,
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
    print("=" * 60)
    print(f"진우퀀트 v3.7.1 자동 실행  (BAB 임계값 재조정)")
    print(f"시간: {datetime.now()}")
    print("=" * 60)

    panel = fetch_price_panel()
    df = compute_scores(panel)

    prev_csv = BASE / 'v37_1_scores_latest.csv'
    changes = detect_changes(df, prev_csv)

    far_signals = []
    for _, r in df.iterrows():
        if r['FAR_신호'] in ['FAR_BUY', 'FAR_AVOID']:
            far_signals.append({
                'name': r['종목'],
                'signal': r['FAR_신호'],
                'r_1m': r['r_1m_%']
            })

    print("\n" + "=" * 60)
    print("v3.7.1 18종목 점수표")
    print("=" * 60)
    print(df[['순위','종목','체력_최종','등급','Mom12','BAB','NOA',
              'r_mom12_%','β_60d']].to_string(index=False))

    # 저장
    df.to_csv(BASE / 'v37_1_scores_latest.csv', index=False)

    html = _generate_html_v37(df, changes, far_signals)
    # v3.7 → v3.7.1 라벨 변경
    html = html.replace('진우퀀트 v3.7 (Mom12·BAB·NOA)',
                        '진우퀀트 v3.7.1 (BAB 재조정)')
    html = html.replace('v3.7 (Mom12·BAB·NOA)', 'v3.7.1 (BAB 재조정)')
    (BASE / 'dashboard_v37_1.html').write_text(html, encoding='utf-8')

    summary = {
        'version': 'v3.7.1',
        'BAB_thresholds': {'+2': 0.4, '+1': 0.7, '0': 1.2, '-1': 1.5},
        'timestamp': datetime.now().isoformat(),
        '등급_분포': df['등급'].value_counts().to_dict(),
        '변동': changes,
        'far_신호': far_signals,
        'BAB_분포': df['BAB'].value_counts().to_dict(),
        'top3': df.head(3)[['종목', '체력_최종', '등급']].to_dict('records'),
    }
    (BASE / 'v37_1_summary_latest.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding='utf-8')

    print(f"\n✅ 저장 완료:")
    print(f"  - v37_1_scores_latest.csv")
    print(f"  - dashboard_v37_1.html")
    print(f"  - v37_1_summary_latest.json")


if __name__ == '__main__':
    main()
