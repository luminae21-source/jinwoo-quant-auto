#!/usr/bin/env python3
"""
진우퀀트 v3.7 자동 점수 산출 + 대시보드 생성

v3.6 위에 신규 3팩터 추가:
  - Mom12: 12M Momentum (Jegadeesh-Titman 1993, 1M skip)
  - BAB:   Betting Against Beta (Frazzini-Pedersen 2014, 60d β)
  - NOA:   Net Operating Assets (Hirshleifer 2004, 분기 갱신)

v3.6 회귀: USE_V37_FACTORS = False 로 세팅 시 v3.6 동작.

실행: 매일 4:30 PM (Cowork bash + scheduled task)
실행 시간: ~6~12분 (FDR 12M 데이터 수집 포함)
"""

import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np

BASE = Path(__file__).parent.resolve()

# ============================================
# v3.7 토글
# ============================================
USE_V37_FACTORS = True   # False 시 v3.6 동작 (Mom12·BAB·NOA = 0)

# ============================================
# v3.7 18종목 — production 점수
# v3.6 항목 + Mom12·BAB·NOA 추가 (초기 0, 백테스트·DART 분기 입력 후 갱신)
# ============================================
JINWOO_v37 = {
    # 기존 13종목 (v3.5 production)
    '삼성전자':       {'코드':'005930','F_korean':6.21,'ModF':+2,'Sloan': 0,'NOA':0,'산업':'반도체','신규':False},
    'SK하이닉스':     {'코드':'000660','F_korean':7.28,'ModF':+3,'Sloan':+1,'NOA':0,'산업':'반도체','신규':False},
    '한미반도체':     {'코드':'042700','F_korean':7.15,'ModF':+3,'Sloan': 0,'NOA':0,'산업':'반도체','신규':False},
    '알테오젠':       {'코드':'196170','F_korean':7.53,'ModF':+3,'Sloan':-1,'NOA':0,'산업':'바이오','신규':False},
    '기아':           {'코드':'000270','F_korean':3.95,'ModF': 0,'Sloan': 0,'NOA':0,'산업':'자동차','신규':False},
    'NAVER':          {'코드':'035420','F_korean':5.63,'ModF':+3,'Sloan': 0,'NOA':0,'산업':'인터넷','신규':False},
    '카카오':         {'코드':'035720','F_korean':2.99,'ModF': 0,'Sloan': 0,'NOA':0,'산업':'인터넷','신규':False},
    '한화에어로':     {'코드':'012450','F_korean':7.53,'ModF':+1,'Sloan': 0,'NOA':0,'산업':'방산','신규':False},
    'LIG넥스원':      {'코드':'079550','F_korean':2.13,'ModF':-3,'Sloan': 0,'NOA':0,'산업':'방산','신규':False},
    'KB금융':         {'코드':'105560','F_korean':3.42,'ModF': 0,'Sloan': 0,'NOA':0,'산업':'금융','신규':False},
    'KT&G':           {'코드':'033780','F_korean':5.56,'ModF': 0,'Sloan': 0,'NOA':0,'산업':'필수소비재','신규':False},
    '삼성SDI':        {'코드':'006400','F_korean':3.22,'ModF':+1,'Sloan':-2,'NOA':0,'산업':'2차전지','신규':False},
    '아모레퍼시픽':   {'코드':'090430','F_korean':6.46,'ModF': 0,'Sloan':-1,'NOA':0,'산업':'화장품','신규':False},
    # v3.6 신규 5종목
    '삼성물산':       {'코드':'028260','F_korean':7.28,'ModF':+3,'Sloan': 0,'NOA':0,'산업':'종합상사','신규':True},
    '삼양식품':       {'코드':'003230','F_korean':8.17,'ModF':+3,'Sloan': 0,'NOA':0,'산업':'식품','신규':True},
    'ISC':            {'코드':'095340','F_korean':8.11,'ModF':+2,'Sloan': 0,'NOA':0,'산업':'반도체','신규':True},
    '두산에너빌리티': {'코드':'034020','F_korean':7.50,'ModF':+2,'Sloan': 0,'NOA':0,'산업':'원전','신규':True},
    'NH투자증권':     {'코드':'005940','F_korean':8.17,'ModF':+2,'Sloan': 0,'NOA':0,'산업':'금융','신규':True},
}

KOSPI_CODE = 'KS11'   # FDR KOSPI 종합지수


# ============================================
# 데이터 수집 (FDR)
# ============================================
def _ensure_fdr():
    try:
        import FinanceDataReader as fdr
        return fdr
    except ImportError:
        print("⚠️ FinanceDataReader 설치 중...")
        import subprocess
        subprocess.check_call([sys.executable, '-m', 'pip', 'install', '-q', 'finance-datareader'])
        import FinanceDataReader as fdr
        return fdr


def fetch_price_panel():
    """
    18종목 + KOSPI 지수의 최근 13M 일별 종가 수집.
    13M = 252 + 21 + 여유 = 약 400일 캘린더.
    반환: dict[name] = pd.Series (DatetimeIndex, close prices)
    """
    fdr = _ensure_fdr()
    end = datetime.now()
    start = end - timedelta(days=400)
    panel = {}

    print(f"\n📊 가격 데이터 수집 (13M, {start.strftime('%Y-%m-%d')} → {end.strftime('%Y-%m-%d')}):")

    # KOSPI 먼저
    try:
        df = fdr.DataReader(KOSPI_CODE,
                            start.strftime('%Y-%m-%d'),
                            end.strftime('%Y-%m-%d'))
        if len(df) > 200:
            panel['_KOSPI'] = df['Close']
            print(f"  {'KOSPI':14s} {len(df)} 영업일")
        else:
            panel['_KOSPI'] = None
            print(f"  {'KOSPI':14s} 데이터 부족 ({len(df)}일)")
    except Exception as e:
        panel['_KOSPI'] = None
        print(f"  {'KOSPI':14s} 실패: {e}")

    # 18종목
    for name, info in JINWOO_v37.items():
        try:
            df = fdr.DataReader(info['코드'],
                                start.strftime('%Y-%m-%d'),
                                end.strftime('%Y-%m-%d'))
            if len(df) > 60:
                panel[name] = df['Close']
                print(f"  {name:14s} {len(df)} 영업일")
            else:
                panel[name] = None
                print(f"  {name:14s} 데이터 부족 ({len(df)}일)")
        except Exception as e:
            panel[name] = None
            print(f"  {name:14s} 실패: {e}")

    return panel


# ============================================
# 팩터 계산
# ============================================
def compute_1m_return(series):
    """v3.6 호환: 최근 1개월 수익률"""
    if series is None or len(series) < 21:
        return None
    return series.iloc[-1] / series.iloc[-21] - 1


def compute_mom12(series):
    """
    12M Momentum (1M skip) = Jegadeesh-Titman 1993
    r_mom12 = price[t-21] / price[t-252] - 1
    """
    if series is None or len(series) < 253:
        return None
    return series.iloc[-22] / series.iloc[-253] - 1


def compute_beta60(stock_series, kospi_series):
    """
    60d rolling β vs KOSPI = BAB의 기반
    β = Cov(r_stock, r_kospi) / Var(r_kospi)
    """
    if stock_series is None or kospi_series is None:
        return None
    if len(stock_series) < 61 or len(kospi_series) < 61:
        return None

    # 마지막 60거래일 일별 수익률
    s_ret = stock_series.pct_change().tail(60).dropna()
    k_ret = kospi_series.pct_change().tail(60).dropna()

    # 인덱스 정렬
    df = pd.concat([s_ret, k_ret], axis=1, join='inner').dropna()
    if len(df) < 30:
        return None

    s, k = df.iloc[:, 0], df.iloc[:, 1]
    var_k = k.var()
    if var_k == 0 or pd.isna(var_k):
        return None

    return float(s.cov(k) / var_k)


# ============================================
# 팩터 → ±2 정수 점수 변환
# ============================================
def mom12_to_score(r_mom12):
    if r_mom12 is None: return 0
    if r_mom12 >= 0.60:  return +2
    if r_mom12 >= 0.30:  return +1
    if r_mom12 >= -0.10: return 0
    if r_mom12 >= -0.30: return -1
    return -2


def bab_to_score(beta):
    if beta is None: return 0
    if beta < 0.7:  return +2
    if beta < 0.9:  return +1
    if beta < 1.1:  return 0
    if beta < 1.3:  return -1
    return -2


def noa_to_score(noa_val):
    """
    NOA는 분기 1회 외부 입력 (JINWOO_v37 dict의 NOA 키 -2 ~ +2 정수).
    이 함수는 그냥 그 값을 통과시킴 (clip 안전망).
    """
    if noa_val is None: return 0
    return max(-2, min(+2, int(noa_val)))


# ============================================
# v3.6 호환: FAR 신호
# ============================================
def far_trigger(체력_12점, r_1m):
    if r_1m is None:
        return 0, None
    if r_1m < -0.05 and 체력_12점 >= 9:
        return 2, 'FAR_BUY'
    if r_1m > 0.05 and 체력_12점 <= 4:
        return -2, 'FAR_AVOID'
    if r_1m < -0.05 and 체력_12점 >= 6:
        return 1, 'FAR_WEAK_BUY'
    if r_1m > 0.05 and 체력_12점 <= 6:
        return -1, 'FUR_WEAK'
    return 0, None


def grade(score):
    if score >= 14: return 'S+'
    elif score >= 12: return 'S'
    elif score >= 9: return 'A'
    elif score >= 6: return 'B'
    elif score >= 3: return 'C'
    elif score >= 0: return 'D'
    else: return 'F'


# ============================================
# 종합 점수
# ============================================
def compute_scores(panel):
    """v3.7 18종목 점수 산출 (v3.6 + 신규 3팩터)"""
    kospi = panel.get('_KOSPI')
    rows = []

    for name, info in JINWOO_v37.items():
        series = panel.get(name)

        # v3.6 핵심
        체력_12점 = info['F_korean'] * (12 / 9.001)
        r_1m = compute_1m_return(series)
        far_val, far_signal = far_trigger(체력_12점, r_1m)

        # v3.7 신규
        if USE_V37_FACTORS:
            r_mom12 = compute_mom12(series)
            beta60 = compute_beta60(series, kospi)
            mom12_score = mom12_to_score(r_mom12)
            bab_score = bab_to_score(beta60)
            noa_score = noa_to_score(info.get('NOA', 0))
        else:
            r_mom12, beta60 = None, None
            mom12_score = bab_score = noa_score = 0

        # 체력 최종
        체력_최종 = (체력_12점
                    + info['ModF'] + far_val + info['Sloan']
                    + mom12_score + bab_score + noa_score)

        rows.append({
            '종목': name,
            '코드': info['코드'],
            '산업': info['산업'],
            'F_korean': info['F_korean'],
            '체력_12점': round(체력_12점, 2),
            'ModF': info['ModF'],
            'FAR': far_val,
            'FAR_신호': far_signal,
            'Sloan': info['Sloan'],
            'Mom12': mom12_score,
            'BAB': bab_score,
            'NOA': noa_score,
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


def detect_changes(df_now, prev_path):
    """전일 대비 등급 변동 감지"""
    if not prev_path.exists():
        return []

    df_prev = pd.read_csv(prev_path)
    changes = []
    for _, row in df_now.iterrows():
        prev_row = df_prev[df_prev['종목'] == row['종목']]
        if len(prev_row) > 0:
            prev_grade = prev_row['등급'].iloc[0]
            prev_score = prev_row['체력_최종'].iloc[0]
            if prev_grade != row['등급']:
                changes.append({
                    '종목': row['종목'],
                    '전일_등급': prev_grade,
                    '오늘_등급': row['등급'],
                    '체력_변동': round(row['체력_최종'] - prev_score, 2)
                })
    return changes


# ============================================
# v3.7 vs v3.6 비교 (dry-run)
# ============================================
def compare_v36_v37(df_v37):
    """동일 데이터에서 v3.6 점수 재계산해서 차이 출력"""
    diffs = []
    for _, r in df_v37.iterrows():
        base = r['체력_12점'] + r['ModF'] + r['FAR'] + r['Sloan']
        delta = r['Mom12'] + r['BAB'] + r['NOA']
        diffs.append({
            '종목': r['종목'],
            'v36_점수': round(base, 2),
            'v36_등급': grade(base),
            'v37_점수': r['체력_최종'],
            'v37_등급': r['등급'],
            'Δ_체력': round(delta, 2),
            'Mom12': r['Mom12'],
            'BAB': r['BAB'],
            'NOA': r['NOA'],
        })
    return pd.DataFrame(diffs)


# ============================================
# 대시보드 HTML
# ============================================
def generate_html(df, changes, far_signals):
    today = datetime.now().strftime('%Y-%m-%d %H:%M')
    grade_colors = {
        'S+': '#81c784', 'S': '#aed581', 'A': '#4fc3f7',
        'B': '#ffd54f', 'C': '#ffb74d', 'D': '#e57373', 'F': '#b71c1c'
    }

    rows_html = ""
    for _, r in df.iterrows():
        color = grade_colors.get(r['등급'], '#fff')
        new_mark = '⭐' if r['신규'] else ''
        far_mark = ''
        if r['FAR_신호'] == 'FAR_BUY':
            far_mark = '<span style="color:#81c784">🎯 BUY</span>'
        elif r['FAR_신호'] == 'FAR_AVOID':
            far_mark = '<span style="color:#e57373">🚨 AVOID</span>'
        elif r['FAR_신호'] == 'FAR_WEAK_BUY':
            far_mark = '<span style="color:#aed581">↗</span>'
        elif r['FAR_신호'] == 'FUR_WEAK':
            far_mark = '<span style="color:#ffb74d">↘</span>'

        r_1m_str   = f"{r['r_1m_%']:+.2f}%" if r['r_1m_%'] is not None else '-'
        r_mom_str  = f"{r['r_mom12_%']:+.1f}%" if r['r_mom12_%'] is not None else '-'
        beta_str   = f"{r['β_60d']:.2f}" if r['β_60d'] is not None else '-'

        def fmt_sign(v):
            if v > 0: return f"<span style='color:#81c784'>+{v}</span>"
            if v < 0: return f"<span style='color:#e57373'>{v}</span>"
            return "0"

        rows_html += f"""
        <tr>
          <td>{r['순위']}</td>
          <td>{r['종목']} {new_mark}</td>
          <td>{r['산업']}</td>
          <td>{r['F_korean']:.2f}</td>
          <td>{r['ModF']:+d}</td>
          <td>{r['FAR']:+d}</td>
          <td>{r['Sloan']:+d}</td>
          <td>{fmt_sign(r['Mom12'])}</td>
          <td>{fmt_sign(r['BAB'])}</td>
          <td>{fmt_sign(r['NOA'])}</td>
          <td><b>{r['체력_최종']:.2f}</b></td>
          <td><span style="color:{color};font-weight:bold">{r['등급']}</span></td>
          <td>{r_1m_str}</td>
          <td>{r_mom_str}</td>
          <td>{beta_str}</td>
          <td>{far_mark}</td>
        </tr>"""

    changes_html = ""
    if changes:
        changes_html = "<div class='alert'>📢 <b>등급 변동:</b><br>"
        for c in changes:
            changes_html += f"  {c['종목']}: {c['전일_등급']} → {c['오늘_등급']} ({c['체력_변동']:+.2f})<br>"
        changes_html += "</div>"

    far_html = ""
    if far_signals:
        far_html = "<div class='alert'>🎯 <b>FAR 신호:</b><br>"
        for fs in far_signals:
            color = '#81c784' if 'BUY' in fs['signal'] else '#e57373'
            far_html += f"  <span style='color:{color}'>{fs['name']} {fs['signal']}</span> (1M {fs['r_1m']:+.2f}%)<br>"
        far_html += "</div>"

    grade_count = df['등급'].value_counts()
    grade_summary = ""
    for g in ['S+','S','A','B','C','D','F']:
        n = grade_count.get(g, 0)
        if n > 0:
            grade_summary += f"<span style='color:{grade_colors[g]}'><b>{g}</b> {n}</span> "

    version_label = "v3.7 (Mom12·BAB·NOA)" if USE_V37_FACTORS else "v3.7 [팩터 비활성=v3.6]"

    html = f"""<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>진우퀀트 {version_label} — {today}</title>
<style>
  body {{ font-family: -apple-system, sans-serif; background: #0f1419; color: #e0e6ed;
         line-height: 1.5; padding: 12px; margin: 0; }}
  h1 {{ color: #4fc3f7; font-size: 20px; margin-bottom: 2px; }}
  .meta {{ font-size: 11px; color: #6c757d; margin-bottom: 16px; }}
  .summary {{ background: linear-gradient(135deg,#1e3a5f,#2e5984); padding: 14px;
              border-radius: 10px; margin-bottom: 14px; font-size: 14px; }}
  .alert {{ background: #2c1f0f; border-left: 3px solid #ffb74d;
            padding: 10px; margin: 8px 0; border-radius: 4px; font-size: 13px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 11px;
           background: #1a232e; border-radius: 8px; overflow: hidden; }}
  th {{ background: #2a3441; color: #ffd54f; padding: 8px 3px; text-align: left;
        font-size: 10px; }}
  td {{ padding: 6px 3px; border-bottom: 1px solid #2a3441; }}
  tr:hover {{ background: #1e2832; }}
</style></head><body>

<h1>진우퀀트 {version_label}</h1>
<div class="meta">{today} · 18종목 · 자동 갱신</div>

<div class="summary">
  <b>등급 분포:</b> {grade_summary}<br>
  <b>총 종목:</b> 18 · <b>신규 5:</b> ISC·삼양식품·NH투자증권·삼성물산·두산에너빌리티
</div>

{changes_html}
{far_html}

<table>
<tr>
  <th>#</th><th>종목</th><th>산업</th>
  <th>F</th><th>Mod</th><th>FAR</th><th>Sl</th>
  <th>Mom</th><th>BAB</th><th>NOA</th>
  <th>체력</th><th>등급</th>
  <th>1M%</th><th>12M%</th><th>β</th><th>신호</th>
</tr>
{rows_html}
</table>

<div class="meta" style="margin-top:16px">
  ⭐ v3.6 신규 편입 종목 · 매일 4:30 자동 갱신 · 매매 결정은 진우퀀트_v36_매매룰.md 참조<br>
  v3.7 신규 팩터: <b>Mom</b> = 12M Momentum · <b>BAB</b> = β_60d 기반 · <b>NOA</b> = 자산효율성 (분기 갱신)
</div>

</body></html>"""
    return html


# ============================================
# 메인
# ============================================
def main():
    print("=" * 60)
    print(f"진우퀀트 v3.7 자동 실행  (USE_V37_FACTORS={USE_V37_FACTORS})")
    print(f"시간: {datetime.now()}")
    print("=" * 60)

    # 1. 가격 panel 수집
    panel = fetch_price_panel()

    # 2. 점수 산출
    df = compute_scores(panel)

    # 3. 변동 감지 (v3.7 자체 prev 파일 기준)
    prev_csv = BASE / 'v37_scores_latest.csv'
    changes = detect_changes(df, prev_csv)

    # 4. FAR 신호 추출
    far_signals = []
    for _, r in df.iterrows():
        if r['FAR_신호'] in ['FAR_BUY', 'FAR_AVOID']:
            far_signals.append({
                'name': r['종목'],
                'signal': r['FAR_신호'],
                'r_1m': r['r_1m_%']
            })

    # 5. 결과 출력
    print("\n" + "=" * 60)
    print("v3.7 18종목 점수표")
    print("=" * 60)
    print(df[['순위','종목','체력_최종','등급','Mom12','BAB','NOA',
              'r_mom12_%','β_60d']].to_string(index=False))

    # v3.7 vs v3.6 비교
    if USE_V37_FACTORS:
        print("\n" + "=" * 60)
        print("v3.7 vs v3.6 점수 차이")
        print("=" * 60)
        cmp = compare_v36_v37(df)
        print(cmp.to_string(index=False))

    if changes:
        print(f"\n📢 등급 변동: {len(changes)}개")
        for c in changes:
            print(f"  {c['종목']}: {c['전일_등급']} → {c['오늘_등급']}")

    if far_signals:
        print(f"\n🎯 FAR 신호: {len(far_signals)}개")
        for fs in far_signals:
            print(f"  {fs['name']} {fs['signal']} (1M {fs['r_1m']:+.2f}%)")

    # 6. 저장
    df.to_csv(BASE / 'v37_scores_latest.csv', index=False)

    html = generate_html(df, changes, far_signals)
    dashboard_path = BASE / 'dashboard_v37.html'
    dashboard_path.write_text(html, encoding='utf-8')

    print(f"\n✅ 저장 완료:")
    print(f"  - {BASE / 'v37_scores_latest.csv'}")
    print(f"  - {dashboard_path}")

    summary = {
        'version': 'v3.7',
        'use_v37_factors': USE_V37_FACTORS,
        'timestamp': datetime.now().isoformat(),
        '등급_분포': df['등급'].value_counts().to_dict(),
        '변동': changes,
        'far_신호': far_signals,
        'top3': df.head(3)[['종목', '체력_최종', '등급']].to_dict('records'),
        'bottom3': df.tail(3)[['종목', '체력_최종', '등급']].to_dict('records'),
        '신규팩터_요약': {
            'Mom12_분포':   df['Mom12'].value_counts().to_dict(),
            'BAB_분포':     df['BAB'].value_counts().to_dict(),
            'NOA_분포':     df['NOA'].value_counts().to_dict(),
        } if USE_V37_FACTORS else None,
    }
    (BASE / 'v37_summary_latest.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )
    print(f"  - {BASE / 'v37_summary_latest.json'}")


if __name__ == '__main__':
    main()
