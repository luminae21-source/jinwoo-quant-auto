#!/usr/bin/env python3
"""
진우퀀트 v3.6 — GitHub Actions 자동 실행 스크립트
매일 07:30 UTC (16:30 KST) 자동 실행

환경 변수 필요:
  DART_API_KEY — DART OpenAPI 키 (GitHub Secrets)

출력:
  docs/dashboard.html — GitHub Pages 자동 서빙
  docs/v36_scores_latest.csv — 최신 점수 데이터
  docs/v36_summary_latest.json — 요약 JSON
"""

import os
import sys
import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np
import FinanceDataReader as fdr

# ============================================
# 경로 설정 (GitHub repo 루트 기준)
# ============================================
REPO_ROOT = Path(__file__).parent.resolve()
DOCS_DIR = REPO_ROOT / 'docs'
DOCS_DIR.mkdir(exist_ok=True)

# ============================================
# v3.6 18종목 — production 점수 (분기 갱신)
# ============================================
JINWOO_v36 = {
    '삼성전자':       {'코드':'005930','F_korean':6.21,'ModF':+2,'Sloan':0,'산업':'반도체','신규':False},
    'SK하이닉스':     {'코드':'000660','F_korean':7.28,'ModF':+3,'Sloan':+1,'산업':'반도체','신규':False},
    '한미반도체':     {'코드':'042700','F_korean':7.15,'ModF':+3,'Sloan':0,'산업':'반도체','신규':False},
    '알테오젠':       {'코드':'196170','F_korean':7.53,'ModF':+3,'Sloan':-1,'산업':'바이오','신규':False},
    '기아':           {'코드':'000270','F_korean':3.95,'ModF':0,'Sloan':0,'산업':'자동차','신규':False},
    'NAVER':          {'코드':'035420','F_korean':5.63,'ModF':+3,'Sloan':0,'산업':'인터넷','신규':False},
    '카카오':         {'코드':'035720','F_korean':2.99,'ModF':0,'Sloan':0,'산업':'인터넷','신규':False},
    '한화에어로':     {'코드':'012450','F_korean':7.53,'ModF':+1,'Sloan':0,'산업':'방산','신규':False},
    'LIG넥스원':      {'코드':'079550','F_korean':2.13,'ModF':-3,'Sloan':0,'산업':'방산','신규':False},
    'KB금융':         {'코드':'105560','F_korean':3.42,'ModF':0,'Sloan':0,'산업':'금융','신규':False},
    'KT&G':           {'코드':'033780','F_korean':5.56,'ModF':0,'Sloan':0,'산업':'필수소비재','신규':False},
    '삼성SDI':        {'코드':'006400','F_korean':3.22,'ModF':+1,'Sloan':-2,'산업':'2차전지','신규':False},
    '아모레퍼시픽':   {'코드':'090430','F_korean':6.46,'ModF':0,'Sloan':-1,'산업':'화장품','신규':False},
    '삼성물산':       {'코드':'028260','F_korean':7.28,'ModF':+3,'Sloan':0,'산업':'종합상사','신규':True},
    '삼양식품':       {'코드':'003230','F_korean':8.17,'ModF':+3,'Sloan':0,'산업':'식품','신규':True},
    'ISC':            {'코드':'095340','F_korean':8.11,'ModF':+2,'Sloan':0,'산업':'반도체','신규':True},
    '두산에너빌리티': {'코드':'034020','F_korean':7.50,'ModF':+2,'Sloan':0,'산업':'원전','신규':True},
    'NH투자증권':     {'코드':'005940','F_korean':8.17,'ModF':+2,'Sloan':0,'산업':'금융','신규':True},
}


def get_1m_returns():
    """FDR로 18종목 최근 1개월 수익률"""
    end = datetime.now()
    start = end - timedelta(days=35)
    returns = {}
    print(f"\n📊 1M 수익률 수집 ({start.strftime('%m-%d')} → {end.strftime('%m-%d')}):")
    for name, info in JINWOO_v36.items():
        try:
            df = fdr.DataReader(info['코드'],
                              start.strftime('%Y-%m-%d'),
                              end.strftime('%Y-%m-%d'))
            if len(df) > 5:
                ret = df['Close'].iloc[-1] / df['Close'].iloc[0] - 1
                returns[name] = ret
                print(f"  {name:14s} {ret*100:+7.2f}%")
        except Exception as e:
            returns[name] = None
            print(f"  {name:14s} 실패: {str(e)[:50]}")
    return returns


def far_trigger(체력_12점, r_1m):
    if r_1m is None: return 0, None
    if r_1m < -0.05 and 체력_12점 >= 9:  return 2, 'FAR_BUY'
    if r_1m > 0.05 and 체력_12점 <= 4:   return -2, 'FAR_AVOID'
    if r_1m < -0.05 and 체력_12점 >= 6:  return 1, 'FAR_WEAK_BUY'
    if r_1m > 0.05 and 체력_12점 <= 6:   return -1, 'FUR_WEAK'
    return 0, None


def grade(score):
    if score >= 14: return 'S+'
    elif score >= 12: return 'S'
    elif score >= 9: return 'A'
    elif score >= 6: return 'B'
    elif score >= 3: return 'C'
    elif score >= 0: return 'D'
    else: return 'F'


def compute_scores(returns):
    rows = []
    for name, info in JINWOO_v36.items():
        체력_12점 = info['F_korean'] * (12/9.001)
        r_1m = returns.get(name)
        far_val, far_signal = far_trigger(체력_12점, r_1m)
        체력_최종 = 체력_12점 + info['ModF'] + far_val + info['Sloan']
        rows.append({
            '종목': name, '코드': info['코드'], '산업': info['산업'],
            'F_korean': info['F_korean'],
            '체력_12점': round(체력_12점, 2),
            'ModF': info['ModF'], 'FAR': far_val, 'FAR_신호': far_signal,
            'Sloan': info['Sloan'],
            '체력_최종': round(체력_최종, 2),
            '등급': grade(체력_최종),
            'r_1m_%': round(r_1m*100, 2) if r_1m is not None else None,
            '신규': info['신규'],
        })
    df = pd.DataFrame(rows).sort_values('체력_최종', ascending=False).reset_index(drop=True)
    df['순위'] = df.index + 1
    return df


def detect_changes(df_now):
    prev_path = DOCS_DIR / 'v36_scores_latest.csv'
    if not prev_path.exists(): return []
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


def generate_html(df, changes, far_signals):
    today = datetime.now().strftime('%Y-%m-%d %H:%M KST')
    grade_colors = {
        'S+': '#81c784', 'S': '#aed581', 'A': '#4fc3f7',
        'B': '#ffd54f', 'C': '#ffb74d', 'D': '#e57373', 'F': '#b71c1c'
    }

    rows_html = ""
    for _, r in df.iterrows():
        color = grade_colors.get(r['등급'], '#fff')
        new_mark = '⭐' if r['신규'] else ''
        far_mark = ''
        if r['FAR_신호'] == 'FAR_BUY':       far_mark = '<span style="color:#81c784">🎯 BUY</span>'
        elif r['FAR_신호'] == 'FAR_AVOID':   far_mark = '<span style="color:#e57373">🚨 AVOID</span>'
        elif r['FAR_신호'] == 'FAR_WEAK_BUY':far_mark = '<span style="color:#aed581">↗</span>'
        elif r['FAR_신호'] == 'FUR_WEAK':    far_mark = '<span style="color:#ffb74d">↘</span>'
        r_1m_str = f"{r['r_1m_%']:+.2f}%" if r['r_1m_%'] is not None else '-'
        rows_html += f"""
        <tr>
          <td>{r['순위']}</td><td>{r['종목']} {new_mark}</td><td>{r['산업']}</td>
          <td>{r['F_korean']:.2f}</td><td>{r['ModF']:+d}</td>
          <td>{r['FAR']:+d}</td><td>{r['Sloan']:+d}</td>
          <td><b>{r['체력_최종']:.2f}</b></td>
          <td><span style="color:{color};font-weight:bold">{r['등급']}</span></td>
          <td>{r_1m_str}</td><td>{far_mark}</td>
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

    html = f"""<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>진우퀀트 v3.6 — {today}</title>
<style>
  body {{ font-family: -apple-system, sans-serif; background: #0f1419; color: #e0e6ed;
         line-height: 1.5; padding: 12px; margin: 0; }}
  h1 {{ color: #4fc3f7; font-size: 20px; margin-bottom: 2px; }}
  .meta {{ font-size: 11px; color: #6c757d; margin-bottom: 16px; }}
  .summary {{ background: linear-gradient(135deg,#1e3a5f,#2e5984); padding: 14px;
              border-radius: 10px; margin-bottom: 14px; font-size: 14px; }}
  .alert {{ background: #2c1f0f; border-left: 3px solid #ffb74d;
            padding: 10px; margin: 8px 0; border-radius: 4px; font-size: 13px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 12px;
           background: #1a232e; border-radius: 8px; overflow: hidden; }}
  th {{ background: #2a3441; color: #ffd54f; padding: 8px 4px; text-align: left; }}
  td {{ padding: 6px 4px; border-bottom: 1px solid #2a3441; }}
  tr:hover {{ background: #1e2832; }}
</style></head><body>

<h1>진우퀀트 v3.6 대시보드</h1>
<div class="meta">{today} · 18종목 · GitHub Actions 자동 갱신</div>

<div class="summary">
  <b>등급 분포:</b> {grade_summary}<br>
  <b>총 종목:</b> 18 · <b>신규 5:</b> ⭐ ISC·삼양식품·NH투자증권·삼성물산·두산에너빌리티
</div>

{changes_html}
{far_html}

<table>
<tr><th>#</th><th>종목</th><th>산업</th><th>F</th><th>Mod</th><th>FAR</th><th>Sloan</th>
    <th>체력</th><th>등급</th><th>1M%</th><th>신호</th></tr>
{rows_html}
</table>

<div class="meta" style="margin-top:16px">
  ⭐ v3.6 신규 · 매일 4:30 KST 자동 갱신 · 매매 룰: 진우퀀트_v36_매매룰.md 참조
</div>

</body></html>"""
    return html


def main():
    print("="*60)
    print(f"진우퀀트 v3.6 GitHub Actions 자동 실행")
    print(f"시간: {datetime.now()}")
    print("="*60)

    returns = get_1m_returns()
    df = compute_scores(returns)
    changes = detect_changes(df)

    far_signals = []
    for _, r in df.iterrows():
        if r['FAR_신호'] in ['FAR_BUY','FAR_AVOID']:
            far_signals.append({
                'name': r['종목'], 'signal': r['FAR_신호'], 'r_1m': r['r_1m_%']
            })

    print("\n" + "="*60)
    print("v3.6 18종목 점수표")
    print("="*60)
    print(df[['순위','종목','체력_최종','등급','r_1m_%','FAR_신호']].to_string(index=False))

    if changes:
        print(f"\n📢 등급 변동: {len(changes)}개")
        for c in changes:
            print(f"  {c['종목']}: {c['전일_등급']} → {c['오늘_등급']}")

    if far_signals:
        print(f"\n🎯 FAR 신호: {len(far_signals)}개")
        for fs in far_signals:
            print(f"  {fs['name']} {fs['signal']} (1M {fs['r_1m']:+.2f}%)")

    df.to_csv(DOCS_DIR / 'v36_scores_latest.csv', index=False)
    html = generate_html(df, changes, far_signals)
    (DOCS_DIR / 'dashboard.html').write_text(html, encoding='utf-8')
    (DOCS_DIR / 'index.html').write_text(html, encoding='utf-8')  # GitHub Pages 기본

    summary = {
        'timestamp': datetime.now().isoformat(),
        '등급_분포': df['등급'].value_counts().to_dict(),
        '변동': changes, 'far_신호': far_signals,
        'top3': df.head(3)[['종목','체력_최종','등급']].to_dict('records'),
        'bottom3': df.tail(3)[['종목','체력_최종','등급']].to_dict('records'),
    }
    (DOCS_DIR / 'v36_summary_latest.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding='utf-8'
    )

    print(f"\n✅ 저장 완료:")
    print(f"  - {DOCS_DIR / 'dashboard.html'}")
    print(f"  - {DOCS_DIR / 'index.html'}")
    print(f"  - {DOCS_DIR / 'v36_scores_latest.csv'}")
    print(f"  - {DOCS_DIR / 'v36_summary_latest.json'}")


if __name__ == '__main__':
    main()
