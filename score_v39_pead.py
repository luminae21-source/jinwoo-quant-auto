#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
진우퀀트 v3.9 PEAD — v3.7.2 + SUE(표준화 어닝 서프라이즈) 미니 모듈

⚠️ 본 실행은 PC 전용: C:\\Users\\긍정적인_삶의자세\\Desktop\\진우퀀트 에서
   python fetch_dart_eps.py  (선행, eps_sue_cache.json 생성)  →  python score_v39_pead.py
⚠️ production(score_v37_2.py) 무수정 — 이 파일은 그 위에 얹는 별도 레이어.
⚠️ --self-test 는 어디서든 실행 가능 (DART·FDR·score_v37_2 불필요).

신호 명세 (진우퀀트_v39_PEAD_결정메모.md §5와 동일):
  X_q   = 분기 지배주주 당기순이익 (fetch_dart_eps.py 수집)
  U_q   = X_q − X_{q−4}                     (계절 랜덤워크 서프라이즈)
  SUE_q = U_q / σ(직전 8개 U, ddof=1)       (최소 6개 관측, σ≈0 → 제외)
  PIT   : 공시일(announced) ≤ asof 인 데이터만 사용
  게이트 : 공시 후 60거래일 이내만 활성 (벗어나면 점수 0)
  점수   : 18종목 SUE 3분위 (상위 20% +1 / 하위 20% −1) — Echo와 동일 컨벤션
  체력_v39 = 체력_최종(v3.7.2) + PEAD_WEIGHT × 점수

학술 backbone:
  - Bernard & Thomas (1989, 1990) — PEAD 원전
  - Foster, Olsen & Shevlin (1984) — 시계열 SUE 정의
  - Kim, Lee & Min (2019) — 한국 PEAD 검증
판정 이력: 공식 엔진 (backtest_v39_pit_pead.py, 2026-06-05) — ×0.5 PASS (Δ+1.06%p net) / ×1.0 FAIL.
현재 모드: Stage 3-A 병행 관찰 (운용 기준은 v3.7.2, 본 파일은 기록용). 진우퀀트_v39_관찰기록.md 참조.
v3 (2026-06-05): 모바일 대시보드 자동 생성 추가 → dashboard_v39_pead.html
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).parent.resolve()
CACHE_FILE = BASE / 'eps_sue_cache.json'

# ============================================
# v3.9 토글
# ============================================
USE_PEAD_FACTOR = True
PEAD_WEIGHT = 0.5          # ⭐ 2026-06-05 공식 엔진 판정: ×0.5 PASS (Δ+1.06%p) / ×1.0 FAIL
                           #    Stage 3-A 병행 관찰 모드 — 운용 기준은 여전히 v3.7.2
DRIFT_WINDOW_TD = 60       # 공시 후 60거래일 (Bernard-Thomas drift 구간)
MIN_SIGMA_OBS = 6          # σ 추정 최소 관측 수 (8개 중)
CAL_FALLBACK_DAYS = 88     # 거래일 인덱스 없을 때 캘린더일 폴백 (≈60거래일)

TARGET_GRADES = {'S+', 'S', 'A'}


# ----------------------------------------------------------------------
# SUE 계산 (순수 함수 — self-test 대상, 외부 의존 없음)
# ----------------------------------------------------------------------
def _qkey(qstr):
    """'2023Q1' → (2023, 1)"""
    return int(qstr[:4]), int(qstr[-1])


def _prev_year_q(qstr):
    y, q = _qkey(qstr)
    return f'{y - 1}Q{q}'


def compute_sue_asof(quarters, asof):
    """PIT SUE: asof 시점에 공시된 데이터만으로 최신 분기 SUE 계산.

    quarters: [{'q','ni','announced'}, ...]  (fetch_dart_eps.py 출력)
    asof: 'YYYY-MM-DD' 또는 datetime
    반환: (sue float | None, announced str | None)
    """
    if isinstance(asof, str):
        asof = datetime.strptime(asof, '%Y-%m-%d')
    known = {}
    ann = {}
    for r in quarters:
        if r.get('ni') is None or not r.get('announced'):
            continue
        try:
            a = datetime.strptime(r['announced'], '%Y-%m-%d')
        except ValueError:
            continue
        if a <= asof:
            known[r['q']] = float(r['ni'])
            ann[r['q']] = r['announced']
    if not known:
        return None, None

    # U_q = X_q − X_{q−4} (둘 다 공시된 분기만)
    u = {q: known[q] - known[_prev_year_q(q)]
         for q in known if _prev_year_q(q) in known}
    if not u:
        return None, None

    q_star = max(u, key=_qkey)                      # 최신 서프라이즈 분기
    hist = sorted((q for q in u if _qkey(q) < _qkey(q_star)), key=_qkey)[-8:]
    if len(hist) < MIN_SIGMA_OBS:
        return None, ann.get(q_star)
    sigma = float(np.std([u[q] for q in hist], ddof=1))
    if not np.isfinite(sigma) or sigma <= 1e-9:
        return None, ann.get(q_star)
    return u[q_star] / sigma, ann.get(q_star)


def drift_gate_active(announced, asof, trading_index=None):
    """공시 후 DRIFT_WINDOW_TD 거래일 이내인가. trading_index 없으면 캘린더 폴백."""
    if announced is None:
        return False
    if isinstance(asof, str):
        asof = datetime.strptime(asof, '%Y-%m-%d')
    a = datetime.strptime(announced, '%Y-%m-%d') if isinstance(announced, str) else announced
    if a > asof:
        return False
    if trading_index is not None and len(trading_index) > 0:
        idx = pd.DatetimeIndex(trading_index)
        n_td = int(((idx > a) & (idx <= asof)).sum())
        return n_td <= DRIFT_WINDOW_TD
    return (asof - a).days <= CAL_FALLBACK_DAYS


def pead_quantile_scores(sue_values, all_names):
    """18종목 SUE 3분위 — score_v37_2.compute_echo_scores와 동일 컨벤션."""
    if not sue_values:
        return {name: 0 for name in all_names}
    n = len(sue_values)
    upper_n = max(1, round(n * 0.2))
    lower_n = max(1, round(n * 0.2))
    sorted_desc = pd.Series(sue_values).sort_values(ascending=False)
    upper_threshold = sorted_desc.iloc[upper_n - 1]
    lower_threshold = sorted_desc.iloc[-lower_n]
    scores = {}
    for name in all_names:
        v = sue_values.get(name)
        if v is None:
            scores[name] = 0
        elif v >= upper_threshold:
            scores[name] = +1
        elif v <= lower_threshold:
            scores[name] = -1
        else:
            scores[name] = 0
    return scores


def compute_pead_scores(cache, all_names, asof, trading_index=None):
    """반환: ({name: -1/0/+1}, {name: SUE}, {name: 공시일})"""
    sue_values, ann_dates = {}, {}
    for name in all_names:
        entry = cache.get(name)
        if not entry:
            continue
        sue, announced = compute_sue_asof(entry.get('quarters', []), asof)
        ann_dates[name] = announced
        if sue is None:
            continue
        if not drift_gate_active(announced, asof, trading_index):
            continue                                  # 게이트 밖 → 신호 제외(0)
        sue_values[name] = sue
    return pead_quantile_scores(sue_values, all_names), sue_values, ann_dates


def load_cache(path=CACHE_FILE):
    if not Path(path).exists():
        sys.exit(f'[오류] {Path(path).name} 없음 — 먼저 PC에서 python fetch_dart_eps.py 실행')
    d = json.loads(Path(path).read_text(encoding='utf-8'))
    return {k: v for k, v in d.items() if not k.startswith('_')}


# ----------------------------------------------------------------------
# v3.9 관찰 대시보드 (dashboard_v37_2.html과 동일 다크 테마)
# ----------------------------------------------------------------------
GRADE_COLORS = {'S+': '#81c784', 'S': '#aed581', 'A': '#4fc3f7',
                'B': '#ffd54f', 'C': '#ffb74d', 'D': '#e57373'}


def _esc(s):
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def _badge(g):
    c = GRADE_COLORS.get(g, '#e0e6ed')
    return f"<span style='color:{c};font-weight:bold'>{_esc(g)}</span>"


def generate_html_v39(df, asof, n_sue, n_total):
    """v3.9 병행 관찰 모바일 대시보드 HTML 문자열 생성 (외부 의존 없음)."""
    picks_base = df[df['등급'].isin(TARGET_GRADES)]['종목'].tolist()
    picks_v39 = df[df['등급_v39'].isin(TARGET_GRADES)]['종목'].tolist()
    added = [n for n in picks_v39 if n not in picks_base]
    removed = [n for n in picks_base if n not in picks_v39]
    changed = df[df['등급'] != df['등급_v39']]

    dist = df['등급_v39'].value_counts().to_dict()
    dist_html = ' '.join(
        f"<span style='color:{GRADE_COLORS.get(g, '#e0e6ed')}'><b>{_esc(g)}</b> {dist[g]}</span>"
        for g in ['S+', 'S', 'A', 'B', 'C', 'D'] if g in dist)

    if added or removed:
        pick_line = (f"<span style='color:#e57373'><b>픽 변경!</b></span> "
                     f"추가: {_esc(', '.join(added) or '—')} · 제외: {_esc(', '.join(removed) or '—')}")
    else:
        pick_line = "<span style='color:#81c784'><b>픽 동일</b></span> — v3.9가 운용 픽을 바꾸지 않음"

    if changed.empty:
        chg_html = '없음'
    else:
        chg_html = '<br>'.join(
            f"  {_esc(r['종목'])}: {_badge(r['등급'])} → {_badge(r['등급_v39'])} "
            f"(PEAD {r['PEAD']:+}, SUE {r['SUE값']})"
            + ('' if (r['등급'] in TARGET_GRADES) != (r['등급_v39'] in TARGET_GRADES)
               else " <span style='color:#6c757d'>(비편입↔비편입 또는 편입유지 — 운용 영향 없음)</span>")
            for _, r in changed.iterrows())

    rows = []
    for _, r in df.iterrows():
        hl = " style='background:#26303d'" if r['등급'] != r['등급_v39'] else ''
        pead = r['PEAD']
        pead_html = (f"<span style='color:#81c784'>+{pead}</span>" if pead > 0 else
                     f"<span style='color:#e57373'>{pead}</span>" if pead < 0 else '0')
        sue = r.get('SUE값')
        sue_html = '—' if sue is None or (isinstance(sue, float) and np.isnan(sue)) else f'{sue}'
        rows.append(
            f"<tr{hl}><td>{r['순위_v39']}</td><td>{_esc(r['종목'])}</td>"
            f"<td>{r['체력_최종']}</td><td>{_badge(r['등급'])}</td>"
            f"<td>{pead_html}</td><td>{sue_html}</td>"
            f"<td><b>{r['체력_v39']}</b></td><td>{_badge(r['등급_v39'])}</td>"
            f"<td>{r['권장비중_v39_%']}</td></tr>")

    now = datetime.now().strftime('%Y-%m-%d %H:%M')
    return f"""<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>진우퀀트 v3.9 PEAD 관찰 — {asof}</title>
<style>
  body {{ font-family: -apple-system, sans-serif; background: #0f1419; color: #e0e6ed;
         line-height: 1.5; padding: 12px; margin: 0; }}
  h1 {{ color: #4fc3f7; font-size: 20px; margin-bottom: 2px; }}
  .meta {{ font-size: 11px; color: #6c757d; margin-bottom: 16px; }}
  .summary {{ background: linear-gradient(135deg,#1e3a5f,#2e5984); padding: 14px;
              border-radius: 10px; margin-bottom: 14px; font-size: 14px; }}
  .alert {{ background: #2c1f0f; border-left: 3px solid #ffb74d;
            padding: 10px; margin: 8px 0; border-radius: 4px; font-size: 13px; }}
  .ok {{ background: #122417; border-left: 3px solid #81c784; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 11px;
           background: #1a232e; border-radius: 8px; overflow: hidden; }}
  th {{ background: #2a3441; color: #ffd54f; padding: 8px 3px; text-align: left;
        font-size: 10px; }}
  td {{ padding: 6px 3px; border-bottom: 1px solid #2a3441; }}
  tr:hover {{ background: #1e2832; }}
</style></head><body>

<h1>진우퀀트 v3.9 PEAD — 병행 관찰</h1>
<div class="meta">asof {asof} · 생성 {now} · PEAD ×{PEAD_WEIGHT} · 게이트 {DRIFT_WINDOW_TD}거래일 ·
<b style='color:#ffb74d'>운용 기준은 v3.7.2</b> (본 화면은 기록용)</div>

<div class="summary">
  <b>등급(v3.9) 분포:</b> {dist_html}<br>
  <b>픽 비교:</b> v3.7.2 {len(picks_base)}종목 → v3.9 {len(picks_v39)}종목 · {pick_line}<br>
  <b>SUE 커버리지:</b> {n_sue}/{n_total}
</div>

<div class='alert ok'>🏅 <b>공식 판정 (2026-06-05, backtest_v39_pit_pead):</b><br>
  ×0.5 <b>PASS</b> Δ연환산 +1.06%p (net) · IR 1.45→1.48 · MDD 동일 / ×1.0 FAIL<br>
  마진 박약(+0.06%p) → 병행 관찰 중 · <b>최종 판정 2026-09 초</b> (B 통합 / C 기각)</div>

<div class='alert'>📢 <b>등급 변동 (v3.7.2 → v3.9):</b><br>{chg_html}</div>

<table>
<tr><th>#</th><th>종목</th><th>체력<br>v3.7.2</th><th>등급<br>v3.7.2</th>
<th>PEAD</th><th>SUE</th><th>체력<br>v3.9</th><th>등급<br>v3.9</th><th>비중%</th></tr>
{''.join(rows)}
</table>

<div class="meta" style="margin-top:12px">
월별 기록: 진우퀀트_v39_관찰기록.md · GitHub Actions 미반영 (관찰 모드 — B 통합 시에만 반영)<br>
SUE = (분기 지배주주순이익 − 전년동분기) / σ(직전 8분기 서프라이즈) · Bernard-Thomas 1989·90 / Kim-Lee-Min 2019
</div>
</body></html>"""


# ----------------------------------------------------------------------
# 메인  [PC 실행 — score_v37_2 / FDR 필요]
# ----------------------------------------------------------------------
def main(asof_str=None):
    import score_v37_2 as base                       # production 무수정 import

    print('=' * 80)
    print('진우퀀트 v3.9 PEAD  (v3.7.2 + SUE, Bernard-Thomas) — Stage 3-A 병행 관찰')
    print(f'PEAD 가중치: ×{PEAD_WEIGHT} | 드리프트 게이트: {DRIFT_WINDOW_TD}거래일')
    print(f'시간: {datetime.now()}')
    print('=' * 80)

    panel = base.fetch_price_panel()
    df = base.compute_scores(panel)                  # ← v3.7.2 점수 그대로

    kospi = panel.get('_KOSPI')
    trading_index = kospi.index if kospi is not None else None
    asof = asof_str or datetime.now().strftime('%Y-%m-%d')

    cache = load_cache()
    all_names = df['종목'].tolist()
    pead_scores, sue_values, ann_dates = compute_pead_scores(
        cache, all_names, asof, trading_index)

    if USE_PEAD_FACTOR:
        df['PEAD'] = df['종목'].map(lambda n: pead_scores.get(n, 0) * PEAD_WEIGHT)
    else:
        df['PEAD'] = 0
    df['SUE값'] = df['종목'].map(lambda n: round(sue_values[n], 2) if n in sue_values else None)
    df['PEAD_공시일'] = df['종목'].map(lambda n: ann_dates.get(n))
    df['체력_v39'] = (df['체력_최종'] + df['PEAD']).round(2)
    df['등급_v39'] = df['체력_v39'].apply(base.grade)

    df = df.sort_values('체력_v39', ascending=False).reset_index(drop=True)
    df['순위_v39'] = df.index + 1

    # 비중 재계산 (v3.9 등급 기준, production과 동일 cap)
    picks = df[df['등급_v39'].isin(TARGET_GRADES)]['종목'].tolist()
    sectors_map = dict(zip(df['종목'], df['산업']))
    weights = base.apply_weight_caps(picks, sectors_map)
    df['권장비중_v39_%'] = df['종목'].apply(
        lambda n: round(weights.get(n, 0) * 100, 2) if n in weights else 0)

    print('\nv3.9 PEAD 점수표 (asof %s)' % asof)
    print(df[['순위_v39', '종목', '체력_최종', '등급', 'PEAD', 'SUE값',
              '체력_v39', '등급_v39', '권장비중_v39_%']].to_string(index=False))

    changed = df[df['등급'] != df['등급_v39']]
    print('\n등급 변동 (v3.7.2 → v3.9):',
          '없음' if changed.empty else '')
    for _, r in changed.iterrows():
        print(f"  {r['종목']}: {r['등급']} → {r['등급_v39']} (PEAD {r['PEAD']:+}, SUE {r['SUE값']})")

    print('\nPEAD 분포:')
    for s, grp in df.groupby('PEAD'):
        print(f'  PEAD={s:+}: {", ".join(grp["종목"].tolist())}')
    print(f'\nSUE 산출 종목: {len(sue_values)}/{len(all_names)} '
          f'(미산출 = 데이터 부족·σ가드·게이트 밖 → 점수 0)')

    df.to_csv(BASE / 'v39_pead_scores_latest.csv', index=False)
    html = generate_html_v39(df, asof, len(sue_values), len(all_names))
    (BASE / 'dashboard_v39_pead.html').write_text(html, encoding='utf-8')
    summary = {
        'version': 'v3.9-PEAD (Stage 3-A 병행 관찰 — production 아님)',
        'base': 'v3.7.2', 'pead_weight': PEAD_WEIGHT,
        'drift_window_td': DRIFT_WINDOW_TD, 'asof': asof,
        'timestamp': datetime.now().isoformat(),
        '등급_v39_분포': df['등급_v39'].value_counts().to_dict(),
        'PEAD_분포': df['PEAD'].value_counts().to_dict(),
        '등급_변동': changed[['종목', '등급', '등급_v39']].to_dict('records'),
    }
    (BASE / 'v39_pead_summary_latest.json').write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print('\n✅ 저장: v39_pead_scores_latest.csv, dashboard_v39_pead.html, v39_pead_summary_latest.json')
    print('⚠️ 병행 관찰 모드 — 운용은 계속 v3.7.2 기준. "등급 변동·PEAD 분포·SUE 커버리지" 세 줄을')
    print('   진우퀀트_v39_관찰기록.md 월별 표에 기록할 것.')


# ----------------------------------------------------------------------
# self-test (합성 데이터 — DART·FDR·score_v37_2 불필요)
# ----------------------------------------------------------------------
def _mk_quarters(ni_map, ann_map=None):
    out = []
    for q, ni in ni_map.items():
        y, qn = _qkey(q)
        default_ann = f'{y}-{min(qn * 3 + 2, 12):02d}-15'   # 분기말+~45일 근사
        out.append({'q': q, 'ni': ni,
                    'announced': (ann_map or {}).get(q, default_ann)})
    return out


def self_test():
    ok = 0
    ni = {'2021Q1': 100, '2021Q2': 100, '2021Q3': 100, '2021Q4': 100,
          '2022Q1': 110, '2022Q2': 90, '2022Q3': 120, '2022Q4': 80,
          '2023Q1': 130, '2023Q2': 110, '2023Q3': 100, '2023Q4': 130,
          '2024Q1': 160}
    qs = _mk_quarters(ni, ann_map={'2024Q1': '2024-05-15', '2023Q4': '2024-03-20'})

    # 1) SUE 값 정확성 (직전 8개 U, ddof=1)
    sue, ann = compute_sue_asof(qs, '2024-06-01')
    u_hist = [10, -10, 20, -20, 20, 20, -20, 50]
    expected = 30 / np.std(u_hist, ddof=1)
    assert ann == '2024-05-15' and abs(sue - expected) < 1e-9, (sue, expected)
    ok += 1
    # 2) PIT — 공시 전 asof는 직전 분기 사용
    sue2, ann2 = compute_sue_asof(qs, '2024-05-10')      # 2024Q1 공시(05-15) 전
    assert ann2 == '2024-03-20'                          # 2023Q4가 최신
    u_hist2 = [10, -10, 20, -20, 20, 20, -20]            # 7개 (≥6 OK)
    assert abs(sue2 - 50 / np.std(u_hist2, ddof=1)) < 1e-9
    ok += 1
    # 3) 관측 부족 (<6) → None
    short = {k: ni[k] for k in list(ni)[:9]}             # U 이력 4개뿐
    s3, _ = compute_sue_asof(_mk_quarters(short), '2023-12-31')
    assert s3 is None
    ok += 1
    # 4) σ=0 가드 → None
    flat = {f'{y}Q{q}': 100 + 10 * ((y - 2021) * 4 + q) for y in (2021, 2022, 2023, 2024)
            for q in (1, 2, 3, 4)}                        # U가 전부 +40 → σ=0
    s4, _ = compute_sue_asof(_mk_quarters(flat), '2025-03-01')
    assert s4 is None
    ok += 1
    # 5) 드리프트 게이트 — 거래일 기준
    tidx = pd.bdate_range('2024-01-02', '2025-06-30')
    assert drift_gate_active('2024-05-15', '2024-06-15', tidx) is True
    far = tidx[tidx.get_loc(pd.Timestamp('2024-05-16')) + 80]  # 공시 후 81거래일
    assert drift_gate_active('2024-05-15', far.strftime('%Y-%m-%d'), tidx) is False
    ok += 1
    # 6) 게이트 캘린더 폴백
    assert drift_gate_active('2024-05-15', '2024-07-01', None) is True   # 47일
    assert drift_gate_active('2024-05-15', '2024-09-01', None) is False  # 109일
    ok += 1
    # 7) 3분위 — 18종목 중 +1/−1 각 4개 (Echo 컨벤션)
    names = [f'S{i:02d}' for i in range(18)]
    sue_map = {n: float(i) for i, n in enumerate(names)}
    sc = pead_quantile_scores(sue_map, names)
    assert sum(v == 1 for v in sc.values()) == 4
    assert sum(v == -1 for v in sc.values()) == 4
    assert sum(v == 0 for v in sc.values()) == 10
    ok += 1
    # 8) SUE 미산출 종목은 0점 + 통합 점수 산식
    sc2 = pead_quantile_scores({'A': 5.0, 'B': -5.0}, ['A', 'B', 'C'])
    assert sc2['C'] == 0 and sc2['A'] == 1 and sc2['B'] == -1
    w_demo = 2.0   # 산식 검증용 로컬 가중치 (글로벌 PEAD_WEIGHT와 무관하게 동작해야 함)
    assert abs((7.5 + w_demo * sc2['A']) - 9.5) < 1e-9
    ok += 1
    # 9) compute_pead_scores 통합 (게이트로 한 종목 제외)
    cache = {'활성': {'quarters': qs},
             '만료': {'quarters': _mk_quarters(ni, ann_map={'2024Q1': '2024-01-05'})}}
    tidx2 = pd.bdate_range('2023-01-02', '2024-12-31')
    sc3, sv3, an3 = compute_pead_scores(cache, ['활성', '만료', '무데이터'],
                                        '2024-06-01', tidx2)
    assert '활성' in sv3 and '만료' not in sv3 and sc3['무데이터'] == 0
    ok += 1
    # 10) 대시보드 생성 — HTML 이스케이프 + 등급 변동 하이라이트 + 픽 동일 판정
    dfh = pd.DataFrame([
        {'순위_v39': 1, '종목': 'KT&G', '체력_최종': 9.41, '등급': 'A',
         'PEAD': 0.5, 'SUE값': 0.95, '체력_v39': 9.91, '등급_v39': 'A', '권장비중_v39_%': 7.69},
        {'순위_v39': 2, '종목': '기아', '체력_최종': 6.27, '등급': 'B',
         'PEAD': -0.5, 'SUE값': -1.12, '체력_v39': 5.77, '등급_v39': 'C', '권장비중_v39_%': 0.0},
    ])
    h = generate_html_v39(dfh, '2026-06-05', 15, 18)
    assert 'KT&amp;G' in h and 'KT&G' not in h.replace('KT&amp;G', '')
    assert "background:#26303d" in h          # 기아 변동 행 하이라이트
    assert '픽 동일' in h and '15/18' in h    # A→A 유지·B→C 비편입 → 픽 변화 없음
    ok += 1

    print(f'✅ score_v39_pead self-test {ok}/10 통과 (합성 데이터, 외부 의존 없음)')
    print(f'   현재 설정: PEAD_WEIGHT={PEAD_WEIGHT} (Stage 3-A 관찰 모드)')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--self-test', action='store_true')
    ap.add_argument('--asof', help='YYYY-MM-DD (기본: 오늘) — 백테스트·검증용')
    args = ap.parse_args()
    if args.self_test:
        self_test()
    else:
        main(args.asof)
