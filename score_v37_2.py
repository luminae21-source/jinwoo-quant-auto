#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
진우퀀트 v3.7.2 — v3.7.1 + Echo Momentum 단독

v3.8 단계 (GP·AG 추가)가 한국 18종목 universe에서 부적합 판정됨에 따른
대안 — Echo Momentum만 v3.7.1에 추가.

학술 근거:
  - S3 Novy-Marx (2012) JFE 103: Echo (t-12~t-7) > recent past
  - S6 장지원 (2017) 재무연구 30(3): 한국 1999-2015 월 1.51%
  - A5 엄철준 (2024): tail risk 동반 모니터링

GPT 검증 (2026-05-28):
  - 대형주 universe 약화 가능 → ±0.5 저가중치 (또는 ±1 실험)
  - 보조 실험군 분리 권장
  - 현재 결과: 6-way 백테스트에서 +1.32%p (Echo가 양의 신호 확인)

실증 결과 (2026-05-28 PIT 분석):
  - v3.8.2 PIT (GP+AG) vs v3.6: -3.56%p (alpha 손실)
  - v3.8.3 PIT (GP+AG+Echo) vs v3.6: -4.11%p (Echo가 GP·AG와 충돌)
  - 가설: v3.7.1 + Echo만이 깨끗한 alpha 회복 가능

v3.7.1 회귀:
  USE_ECHO_FACTOR = False → v3.7.1 동작
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
from score_v38_3 import compute_echo

# ============================================
# v3.7.2 토글
# ============================================
USE_ECHO_FACTOR = True

# GPT 권장: ±0.5 저가중치 (대형주 보수적)
# 또는 ±1.0 (단일 시점 결과에서 +1.32%p로 검증되었으므로)
ECHO_WEIGHT = 1.0

# 섹터 cap (2026-05-29 추가, 옵션 C)
# 섹터별 검증 결과: Cap 35% 시 CAGR -0.17%p (무영향),
# 자연 분산 효과 + 반도체 33% 한계 근접 위험 완화
SECTOR_CAP = 0.35  # 섹터별 최대 35%
STOCK_CAP = 0.15   # 종목별 최대 15% (GPT Q7 권장)


def apply_weight_caps(picks, sectors_map,
                      stock_cap=STOCK_CAP, sector_cap=SECTOR_CAP):
    """
    종목·섹터 비중 cap 적용.

    학술/검증 근거:
      - GPT Q7: 종목 15%, 섹터 35% 권장
      - validate_v37_2_sector.py: Cap 35% 시 alpha 손실 -0.17%p

    반환: {종목: 비중} 정규화된 dict
    """
    if not picks:
        return {}
    n = len(picks)
    raw_weight = 1.0 / n
    weights = {p: min(raw_weight, stock_cap) for p in picks}

    sector_totals = {}
    for p in picks:
        s = sectors_map.get(p, 'Other')
        sector_totals[s] = sector_totals.get(s, 0) + weights[p]

    for sec, total in sector_totals.items():
        if total > sector_cap:
            scale = sector_cap / total
            for p in picks:
                if sectors_map.get(p) == sec:
                    weights[p] *= scale

    total = sum(weights.values())
    if total > 0:
        weights = {k: v/total for k, v in weights.items()}
    return weights


def compute_echo_scores(panel):
    """18종목 Echo 3분위 점수"""
    echo_values = {}
    for name in JINWOO_v37:
        series = panel.get(name)
        v = compute_echo(series)
        if v is not None:
            echo_values[name] = v

    if not echo_values:
        return {name: 0 for name in JINWOO_v37}, {}

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


def compute_scores(panel):
    kospi = panel.get('_KOSPI')
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

        echo_score = echo_scores.get(name, 0) * ECHO_WEIGHT if USE_ECHO_FACTOR else 0

        체력_최종 = (체력_12점 + info['ModF'] + far_val + info['Sloan']
                    + mom12_score + bab_score + noa_score
                    + echo_score)

        echo_val = echo_values.get(name)

        rows.append({
            '종목': name, '코드': info['코드'], '산업': info['산업'],
            'F_korean': info['F_korean'],
            '체력_12점': round(체력_12점, 2),
            'ModF': info['ModF'], 'FAR': far_val, 'FAR_신호': far_signal,
            'Sloan': info['Sloan'],
            'Mom12': mom12_score, 'BAB': bab_score, 'NOA': noa_score,
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

    # 비중 cap 적용 (S+/S/A 등급에만)
    target_grades = {'S+', 'S', 'A'}
    picks = df[df['등급'].isin(target_grades)]['종목'].tolist()
    sectors_map = dict(zip(df['종목'], df['산업']))
    weights = apply_weight_caps(picks, sectors_map)
    df['권장비중_%'] = df['종목'].apply(
        lambda n: round(weights.get(n, 0) * 100, 2) if n in weights else 0
    )

    return df


_STATUS_BANNER = '<div style="background:#15241a;border-left:4px solid #ffb74d;padding:12px 14px;border-radius:8px;margin-bottom:14px;font-size:13px;line-height:1.65;color:#cdd6e0;">\n<b style="color:#ffd54f;">⚠ forward 기대치(정직)</b> — 백테스트 CAGR 76%는 forward가 아님. 검증 결과 <b style="color:#81c784;">시장 +약5~10%p/년 · CAGR 17~25%대 · Sharpe 0.8~1.3</b> (White RC p=0.019: 엣지 실재).<br>\n종목선택(hindsight)이 백테스트 초과수익의 ~3/4 — PIT 룰 기반은 시장+약5%p 수준.<br>\n<b style="color:#4fc3f7;">universe 규칙화(2026-06)</b>: 룰 정당성 25% · 유지 4 / 제외후보 8 / 관찰 4 / KOSDAQ 2 · <a href="status.html" style="color:#4fc3f7;font-weight:bold;">→ 검증·현황 상세</a>\n</div>\n'


def main():
    print("=" * 80)
    print(f"진우퀀트 v3.7.2 자동 실행  (v3.7.1 + Echo Momentum 단독)")
    print(f"Echo 가중치: ×{ECHO_WEIGHT}")
    print(f"시간: {datetime.now()}")
    print("=" * 80)

    panel = fetch_price_panel()
    df = compute_scores(panel)

    prev_csv = BASE / 'v37_2_scores_latest.csv'
    changes = detect_changes(df, prev_csv)

    far_signals = []
    for _, r in df.iterrows():
        if r['FAR_신호'] in ['FAR_BUY', 'FAR_AVOID']:
            far_signals.append({
                'name': r['종목'], 'signal': r['FAR_신호'], 'r_1m': r['r_1m_%']
            })

    print("\n" + "=" * 80)
    print("v3.7.2 18종목 점수표")
    print("=" * 80)
    print(df[['순위', '종목', '체력_최종', '등급',
              'Mom12', 'BAB', 'NOA', 'Echo',
              'Echo값_%', '권장비중_%']].to_string(index=False))

    print("\nEcho 분포:")
    for score, group in df.groupby('Echo'):
        print(f"  Echo={score:+}: {', '.join(group['종목'].tolist())}")

    df.to_csv(BASE / 'v37_2_scores_latest.csv', index=False)
    html = _generate_html_v37(df, changes, far_signals)
    html = html.replace('진우퀀트 v3.7 (Mom12·BAB·NOA)',
                        '진우퀀트 v3.7.2 (Echo 추가)')
    html = html.replace('<div class="summary">', _STATUS_BANNER + '<div class="summary">', 1)
    (BASE / 'dashboard_v37_2.html').write_text(html, encoding='utf-8')

    summary = {
        'version': 'v3.7.2',
        'factors': 'v3.7.1 + Echo Momentum (Novy-Marx 2012)',
        'echo_weight': ECHO_WEIGHT,
        'timestamp': datetime.now().isoformat(),
        '등급_분포': df['등급'].value_counts().to_dict(),
        'Echo_분포': df['Echo'].value_counts().to_dict(),
        '변동': changes,
        'top3': df.head(3)[['종목', '체력_최종', '등급', 'Echo']].to_dict('records'),
    }
    (BASE / 'v37_2_summary_latest.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str),
        encoding='utf-8')

    print(f"\n✅ 저장: v37_2_scores_latest.csv, dashboard_v37_2.html, v37_2_summary_latest.json")


if __name__ == '__main__':
    main()
