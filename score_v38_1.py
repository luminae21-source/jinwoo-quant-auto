#!/usr/bin/env python3
"""
진우퀀트 v3.8.1 — GP/Assets 단독 추가

v3.7.1 위에 단일 팩터 추가:
  - GP_score: Gross Profit / Total Assets 기반 3분위 점수
    * 제조업 16종목: (매출액-매출원가)/자산총계
                    (IT서비스 등 매출원가 미분류 시 영업이익/자산총계 fallback)
    * 금융주 2종목 (KB금융·NH투자증권): ROE 별도 분위
  - 3분위 점수화 (GPT 검증 반영):
      상위 20% (16종목 중 3) = +1
      중위 60% (10) = 0
      하위 20% (3) = -1

학술 근거:
  - S1 Novy-Marx (2013) JFE 108: GP = (매출액 - 매출원가) / 자산총계
  - S4 안제욱·김규영 (2014) 한국 산업경제학회: 한국 직접 검증 (1995-2013, 431개 제조)
  - S5 노지혜 외 (2023) 대한경영학회지 36(1): 한국 8요인 25년 수익성 robust
  - A3 김민기 외 (2018) KAIST 재무관리연구: 한국 GP 메커니즘 (Hong-Stein 무관심)

GPT 검증 (2026-05-28):
  - 18종목 대형주 universe에서 alpha 약화 가능 (기관·외국인 비중 높음)
  - 금융주는 별도 quality proxy 필수
  - production 후보 v3.8.2 (GP+AG)까지로 권장 (이번 v3.8.1은 단독 효과 측정용)

v3.7.1 회귀:
  USE_V38_FACTOR = False → v3.7.1 동작 (GP_score = 0)

선행 조건:
  fetch_dart_quality.py 실행 → quality_data_cache.json 생성 완료
"""

import sys
import json
from datetime import datetime
from pathlib import Path

import pandas as pd
import numpy as np

BASE = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE))

# v3.7.1 자산 재사용 (BAB 임계값 재조정 포함)
from score_v37 import (
    JINWOO_v37, KOSPI_CODE, USE_V37_FACTORS,
    fetch_price_panel,
    compute_1m_return, compute_mom12, compute_beta60,
    mom12_to_score, noa_to_score,
    far_trigger, grade,
    detect_changes,
    generate_html as _generate_html_v37,
)
from score_v37_1 import bab_to_score  # v3.7.1 BAB

# ============================================
# v3.8.1 토글
# ============================================
USE_V38_FACTOR = True   # False 시 v3.7.1 동작 (GP_score = 0)

QUALITY_CACHE = BASE / 'quality_data_cache.json'


# ============================================
# v3.8.1: GP score 함수
# ============================================
def load_quality_data():
    """fetch_dart_quality.py가 생성한 캐시 로드"""
    if not QUALITY_CACHE.exists():
        raise RuntimeError(
            f"{QUALITY_CACHE.name} 미존재.\n"
            "먼저 fetch_dart_quality.py 실행 필요:\n"
            f"  python fetch_dart_quality.py"
        )
    payload = json.loads(QUALITY_CACHE.read_text(encoding='utf-8'))
    return payload['data']


def compute_gp_scores(quality_data):
    """
    18종목 GP-기반 3분위 점수 산출.

    제조업 16종목: GP/Assets 분위
    금융주 2종목 (KB금융·NH투자증권): ROE 분위 (별도 18종목 통합 분위에 합산)

    GPT 권장: 상위 20% / 중위 60% / 하위 20%
    18종목 기준: 약 3 / 12 / 3

    반환: {name: gp_score(int -1/0/+1)}
    """
    # 1. 제조업 종목의 GP/Assets, 금융주의 ROE를 단일 "quality_value"로 통합
    quality_values = {}
    for name, q in quality_data.items():
        sector = q.get('업종')
        if sector == '제조업':
            v = q.get('GP_Assets')
        elif sector in ['은행', '증권사']:
            # 금융주: ROE를 GP equivalent로 사용
            v = q.get('ROE_approx')
        else:
            v = None
        if v is not None:
            quality_values[name] = v

    if not quality_values:
        # 캐시는 있는데 모두 None인 경우
        return {name: 0 for name in JINWOO_v37}

    # 2. 분위 cutoff 계산
    values = pd.Series(quality_values)
    n = len(values)
    upper_n = max(1, round(n * 0.2))   # 상위 20%
    lower_n = max(1, round(n * 0.2))   # 하위 20%

    sorted_desc = values.sort_values(ascending=False)
    upper_threshold = sorted_desc.iloc[upper_n - 1]
    lower_threshold = sorted_desc.iloc[-lower_n]

    # 3. 점수 배정
    scores = {}
    for name in JINWOO_v37:
        v = quality_values.get(name)
        if v is None:
            scores[name] = 0  # 데이터 부족 시 중립
        elif v >= upper_threshold:
            scores[name] = +1
        elif v <= lower_threshold:
            scores[name] = -1
        else:
            scores[name] = 0

    return scores


# ============================================
# 점수 산출 (v3.7.1 + GP 추가)
# ============================================
def compute_scores(panel, quality_data):
    kospi = panel.get('_KOSPI')
    gp_scores = compute_gp_scores(quality_data) if USE_V38_FACTOR else {}

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
            bab_score = bab_to_score(beta60)        # v3.7.1
            noa_score = noa_to_score(info.get('NOA', 0))
        else:
            r_mom12, beta60 = None, None
            mom12_score = bab_score = noa_score = 0

        # v3.8.1: GP 추가
        gp_score = gp_scores.get(name, 0) if USE_V38_FACTOR else 0

        체력_최종 = (체력_12점 + info['ModF'] + far_val + info['Sloan']
                    + mom12_score + bab_score + noa_score
                    + gp_score)

        # quality_value (참조용, 어떤 값으로 분위 매겨졌는지)
        q_info = quality_data.get(name, {})
        sector = q_info.get('업종', '제조업')
        if sector == '제조업':
            q_value = q_info.get('GP_Assets')
            q_type = 'GP/Assets'
        else:
            q_value = q_info.get('ROE_approx')
            q_type = 'ROE'

        rows.append({
            '종목': name, '코드': info['코드'], '산업': info['산업'],
            'F_korean': info['F_korean'],
            '체력_12점': round(체력_12점, 2),
            'ModF': info['ModF'], 'FAR': far_val, 'FAR_신호': far_signal,
            'Sloan': info['Sloan'],
            'Mom12': mom12_score, 'BAB': bab_score, 'NOA': noa_score,
            'GP': gp_score,                          # v3.8.1 신규
            'Q_지표': q_type,                        # GP/Assets or ROE
            'Q_값': round(q_value, 4) if q_value is not None else None,
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


# ============================================
# main
# ============================================
def main():
    print("=" * 70)
    print(f"진우퀀트 v3.8.1 자동 실행  (GP/Assets 단독 추가)")
    print(f"시간: {datetime.now()}")
    print("=" * 70)

    # 1. quality 캐시 로드
    quality_data = load_quality_data()
    print(f"\n📁 Quality 캐시 로드: {len(quality_data)}종목")

    # 2. 가격 데이터 수집
    panel = fetch_price_panel()

    # 3. 점수 산출
    df = compute_scores(panel, quality_data)

    # 4. 이전 결과와 비교
    prev_csv = BASE / 'v38_1_scores_latest.csv'
    changes = detect_changes(df, prev_csv)

    # 5. FAR 신호 추출
    far_signals = []
    for _, r in df.iterrows():
        if r['FAR_신호'] in ['FAR_BUY', 'FAR_AVOID']:
            far_signals.append({
                'name': r['종목'],
                'signal': r['FAR_신호'],
                'r_1m': r['r_1m_%']
            })

    # 6. 출력
    print("\n" + "=" * 70)
    print("v3.8.1 18종목 점수표")
    print("=" * 70)
    print(df[['순위', '종목', '체력_최종', '등급',
              'Mom12', 'BAB', 'NOA', 'GP',
              'Q_지표', 'Q_값']].to_string(index=False))

    # 7. GP 분위 검증 출력
    print("\n" + "=" * 70)
    print("GP_score 분위 분포")
    print("=" * 70)
    gp_dist = df['GP'].value_counts().sort_index(ascending=False)
    for score, count in gp_dist.items():
        names = df[df['GP'] == score]['종목'].tolist()
        print(f"  GP={score:+d}: {count}종목  →  {', '.join(names)}")

    # 8. 저장
    df.to_csv(BASE / 'v38_1_scores_latest.csv', index=False)

    # HTML 대시보드
    html = _generate_html_v37(df, changes, far_signals)
    html = html.replace('진우퀀트 v3.7 (Mom12·BAB·NOA)',
                        '진우퀀트 v3.8.1 (GP/Assets 추가)')
    html = html.replace('v3.7 (Mom12·BAB·NOA)', 'v3.8.1 (GP/Assets)')
    (BASE / 'dashboard_v38_1.html').write_text(html, encoding='utf-8')

    # Summary JSON
    summary = {
        'version': 'v3.8.1',
        'new_factor': 'GP/Assets (Novy-Marx 2013) — 3분위',
        'fallback': 'IT서비스/금융주 → 영업이익/자산 or ROE',
        'timestamp': datetime.now().isoformat(),
        '등급_분포': df['등급'].value_counts().to_dict(),
        'GP_분포': df['GP'].value_counts().to_dict(),
        '변동': changes,
        'far_신호': far_signals,
        'top3': df.head(3)[['종목', '체력_최종', '등급', 'GP']].to_dict('records'),
        'bottom3': df.tail(3)[['종목', '체력_최종', '등급', 'GP']].to_dict('records'),
    }
    (BASE / 'v38_1_summary_latest.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding='utf-8')

    print(f"\n✅ 저장 완료:")
    print(f"  - v38_1_scores_latest.csv")
    print(f"  - dashboard_v38_1.html")
    print(f"  - v38_1_summary_latest.json")


if __name__ == '__main__':
    main()
