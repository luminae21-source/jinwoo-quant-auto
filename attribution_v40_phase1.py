#!/usr/bin/env python3
"""
진우퀀트 v4.0 — 영역 4 Phase 1: CAPM β 분해 (시장 vs 종목 고유)

목적:
  종목 X가 ±N% 변동했을 때, 그 중 얼마가 (a) 시장 동조 / (b) 종목 고유인지 분해.
  영역 4의 4 Phase 중 첫 단계. Phase 2~4는 후속 (산업 → 펀더멘털 → 이벤트).

핵심 출력:
  r_i,t = α_i + β_i × r_KOSPI,t + ε_i,t
  → "시장 기여" = β_i × r_KOSPI,t
  → "종목 고유" = r_i,t - β_i × r_KOSPI,t  (= α_i + ε_i,t)

진우 매매 의사결정에 주는 가치:
  - "삼성전자 -5%였는데 그 중 -4%p가 시장 동조" → 안심하고 보유
  - "기아 -5%였는데 시장은 +0.5%였고 산업도 -1%인데 종목만 -4.5%p" → 진짜 약세 → 조사
  - "단일일 idiosyncratic z-score < -3" → 이벤트 감지 (실적·공시·뉴스 충격)

학술 근거:
  - Sharpe (1964) CAPM
  - Fama & MacBeth (1973) cross-sectional regression
  - 한국 시장: Kim & Park (2010~) — 단일 β도 한국에서 유의

기술 스택:
  - FDR (가격 데이터)
  - numpy / pandas (rolling regression)
  - statsmodels.OLS는 사용하지 않음 (의존성 최소화, rolling β는 cov/var로 충분)

실행:
  python3 attribution_v40_phase1.py
  python3 attribution_v40_phase1.py --days 90       # 최근 90일만 분해
  python3 attribution_v40_phase1.py --beta-win 120  # β 추정 window 120일
  python3 attribution_v40_phase1.py --save-html     # 대시보드 패널 생성
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# v3.7 universe를 그대로 가져오기 (DRY)
try:
    from score_v37 import JINWOO_v37, KOSPI_CODE, _ensure_fdr
except ImportError:
    print("❌ score_v37.py가 같은 폴더에 있어야 합니다.")
    sys.exit(1)

BASE = Path(__file__).parent.resolve()


# ============================================
# 인자
# ============================================
def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--days', type=int, default=20,
                   help='최근 N 영업일 attribution 출력 (기본 20)')
    p.add_argument('--beta-win', type=int, default=60,
                   help='β 추정 rolling window 영업일 (기본 60)')
    p.add_argument('--fetch-days', type=int, default=400,
                   help='FDR로 가져올 캘린더 일수 (기본 400 ≈ 1.5년)')
    p.add_argument('--save-html', action='store_true',
                   help='attribution_panel.html 생성')
    p.add_argument('--save-json', action='store_true', default=True,
                   help='attribution_v40_YYYYMMDD.json 저장')
    p.add_argument('--z-threshold', type=float, default=3.0,
                   help='이벤트 trigger의 idiosyncratic z-score 절대값 (기본 3.0)')
    return p.parse_args()


# ============================================
# 데이터 수집
# ============================================
def fetch_returns_panel(days: int) -> pd.DataFrame:
    """
    KOSPI + 18종목의 일별 로그 수익률 DataFrame 반환.
    columns: ['_KOSPI', '삼성전자', ...]
    """
    fdr = _ensure_fdr()
    end = datetime.now()
    start = end - timedelta(days=days)

    print(f"\n📊 가격 패널 수집 ({start:%Y-%m-%d} → {end:%Y-%m-%d})")
    prices: dict[str, pd.Series] = {}

    # KOSPI
    try:
        df = fdr.DataReader(KOSPI_CODE,
                            start.strftime('%Y-%m-%d'),
                            end.strftime('%Y-%m-%d'))
        if len(df) > 60:
            prices['_KOSPI'] = df['Close']
            print(f"  {'KOSPI':14s} {len(df)} 영업일")
        else:
            print(f"  {'KOSPI':14s} 데이터 부족 — 중단")
            return pd.DataFrame()
    except Exception as e:
        print(f"  {'KOSPI':14s} 실패: {e}")
        return pd.DataFrame()

    # 18종목
    for name, info in JINWOO_v37.items():
        try:
            df = fdr.DataReader(info['코드'],
                                start.strftime('%Y-%m-%d'),
                                end.strftime('%Y-%m-%d'))
            if len(df) > 60:
                prices[name] = df['Close']
                print(f"  {name:14s} {len(df)} 영업일")
            else:
                print(f"  {name:14s} 데이터 부족 ({len(df)})")
        except Exception as e:
            print(f"  {name:14s} 실패: {e}")

    # 정렬 + pct_change
    px = pd.DataFrame(prices).sort_index()
    rets = np.log(px / px.shift(1)).dropna(how='all')
    print(f"\n✅ 수익률 패널: {len(rets)} 영업일 × {rets.shape[1]} 종목")
    return rets


# ============================================
# Phase 1 — CAPM 분해
# ============================================
def rolling_beta(stock_ret: pd.Series,
                 market_ret: pd.Series,
                 window: int) -> pd.Series:
    """
    β_t = Cov_{t-W:t}(r_i, r_m) / Var_{t-W:t}(r_m)
    NaN-safe. 충분한 관측치 없으면 NaN.
    """
    aligned = pd.concat([stock_ret, market_ret], axis=1, join='inner').dropna()
    aligned.columns = ['s', 'm']
    cov = aligned['s'].rolling(window).cov(aligned['m'])
    var = aligned['m'].rolling(window).var()
    beta = cov / var.replace(0, np.nan)
    return beta.reindex(stock_ret.index)


def decompose_one(stock_ret: pd.Series,
                  market_ret: pd.Series,
                  window: int) -> pd.DataFrame:
    """
    종목 한 개에 대한 일별 분해:
      market_contrib_t = β_{t-1} × r_market_t      (look-ahead 방지: β는 lag 1)
      idiosyncratic_t  = r_stock_t - market_contrib_t
      idio_z_t         = (idio_t - μ_W) / σ_W      (rolling z-score)
    """
    beta = rolling_beta(stock_ret, market_ret, window).shift(1)
    aligned = pd.DataFrame({
        'r_stock': stock_ret,
        'r_market': market_ret,
        'beta': beta,
    }).dropna()
    aligned['market_contrib'] = aligned['beta'] * aligned['r_market']
    aligned['idio'] = aligned['r_stock'] - aligned['market_contrib']
    # rolling z-score (현재 시점의 idio 충격을 standardize)
    mu = aligned['idio'].rolling(window).mean()
    sd = aligned['idio'].rolling(window).std()
    aligned['idio_z'] = (aligned['idio'] - mu) / sd.replace(0, np.nan)
    # market share = market_contrib² / r_stock² (∈ [0, ∞), 거의 1 이하)
    # 부호 무시한 분산 분해 — 큰 움직임에서만 의미 있음
    r2 = aligned['r_stock'] ** 2
    aligned['market_share'] = np.where(
        r2 > 1e-8,
        (aligned['market_contrib'] ** 2) / r2,
        np.nan
    )
    return aligned


def decompose_all(returns: pd.DataFrame, window: int) -> dict[str, pd.DataFrame]:
    """모든 종목에 대해 decompose_one 적용. dict[name] = DataFrame."""
    market = returns['_KOSPI']
    out = {}
    for name in returns.columns:
        if name == '_KOSPI':
            continue
        s = returns[name].dropna()
        if len(s) < window + 5:
            print(f"  ⚠️ {name}: 데이터 부족, skip")
            continue
        out[name] = decompose_one(s, market, window)
    return out


# ============================================
# 교체룰 v0 — Phase 1 단순 트리거
# ============================================
REPLACEMENT_RULES_V0 = """
교체룰 v0 (Phase 1 단독 적용 가능 — 시장 vs 종목 고유만 사용):

[T1 즉시 정밀조사] 단일일 |idio_z| ≥ 3.0
  → 이벤트 감지. 뉴스·공시·실적 확인 후 케이스별 판단.

[T2 약세 누적 — 진짜 종목 약세] 최근 20영업일 cum_idio ≤ -10%
  → 시장 빼고도 종목만으로 -10% 누적 = 펀더멘털 의심.
  → F-Score 재확인 (다음 분기 결산 우선 체크).
  → 2개월 연속 시 비중 50% 축소.

[T3 약세 누적 — 시장/산업 동조] 최근 20영업일 cum_stock ≤ -10% 인데 cum_idio > -3%
  → 시장 빠진 거지 종목 문제 아님. 보유 유지. (예: 카카오와 같이 인터넷 전체 약세)

[T4 강세 — 종목 고유 호조] 최근 20영업일 cum_idio ≥ +10%
  → 실적·공시·기대감 등 종목 모멘텀. Mom12 점수 보강 신호와 교차 확인.

[T5 β 급변] β_60d가 30일 전 대비 ±0.4 이상 변화
  → 종목 성격 변화 (예: 안정주 → 변동주). 비중 sizing 룰 재검토.

False signal 방지:
  - 단일일 idio가 비정상이어도, 그 다음 5일 이내 평균 회귀하면 잡음 (mean-reversion).
  - z-score 기준은 종목·기간별로 calibration 필요 (현재는 unified 3.0).
"""


def evaluate_triggers(decomp_dict: dict[str, pd.DataFrame],
                      lookback_days: int = 20,
                      z_threshold: float = 3.0) -> list[dict]:
    """각 종목에 대해 T1~T5 trigger 평가. 발동된 trigger만 반환."""
    out = []
    for name, df in decomp_dict.items():
        if len(df) < lookback_days + 5:
            continue
        recent = df.tail(lookback_days)
        cum_stock = recent['r_stock'].sum() * 100  # log → %
        cum_idio = recent['idio'].sum() * 100

        triggers = []

        # T1: 단일일 z-score 이벤트
        idio_z_last = df['idio_z'].dropna()
        if len(idio_z_last) > 0:
            max_abs_z = idio_z_last.tail(lookback_days).abs().max()
            if max_abs_z >= z_threshold:
                event_day = idio_z_last.tail(lookback_days).abs().idxmax()
                event_z = idio_z_last.loc[event_day]
                event_idio = df.loc[event_day, 'idio'] * 100
                triggers.append({
                    'code': 'T1',
                    'severity': 'high',
                    'msg': f'이벤트 의심: {event_day:%m-%d} idio_z={event_z:+.2f} '
                           f'(idio {event_idio:+.2f}%) → 뉴스/공시 확인',
                })

        # T2: 진짜 약세
        if cum_idio <= -10:
            triggers.append({
                'code': 'T2',
                'severity': 'high',
                'msg': f'20일 종목고유 누적 {cum_idio:+.1f}% (시장 제외 약세). '
                       f'F-Score 재점검 + 분기 결산 우선 체크',
            })

        # T3: 시장 약세 (보유)
        elif cum_stock <= -10 and cum_idio > -3:
            triggers.append({
                'code': 'T3',
                'severity': 'low',
                'msg': f'전체 {cum_stock:+.1f}% 약세지만 종목고유 {cum_idio:+.1f}%. '
                       f'시장 동조 → 보유 유지',
            })

        # T4: 종목 고유 호조
        if cum_idio >= +10:
            triggers.append({
                'code': 'T4',
                'severity': 'info',
                'msg': f'20일 종목고유 누적 {cum_idio:+.1f}%. Mom12와 교차 확인',
            })

        # T5: β 급변
        beta_now = df['beta'].dropna().iloc[-1] if df['beta'].dropna().size else None
        beta_30d = df['beta'].dropna()
        if len(beta_30d) > 30 and beta_now is not None:
            beta_then = beta_30d.iloc[-30]
            d_beta = beta_now - beta_then
            if abs(d_beta) >= 0.4:
                triggers.append({
                    'code': 'T5',
                    'severity': 'med',
                    'msg': f'β 변화: 30일 전 {beta_then:.2f} → 현재 {beta_now:.2f} '
                           f'(Δ{d_beta:+.2f}). Kelly sizing 재검토',
                })

        if triggers:
            out.append({
                'name': name,
                'cum_stock_20d_%': round(cum_stock, 2),
                'cum_idio_20d_%': round(cum_idio, 2),
                'beta_now': round(beta_now, 2) if beta_now is not None else None,
                'triggers': triggers,
            })
    return out


# ============================================
# 출력
# ============================================
def print_summary(decomp_dict: dict[str, pd.DataFrame],
                  triggers: list[dict],
                  days: int):
    print("\n" + "=" * 78)
    print("진우퀀트 v4.0 영역4 — Phase 1 CAPM 분해 결과")
    print(f"분석 시점: {datetime.now():%Y-%m-%d %H:%M}")
    print("=" * 78)

    # β 분포
    print(f"\n📊 종목별 현재 β (60d rolling, 최근 영업일 기준)")
    print(f"  {'종목':<14} {'β_now':>7} {'β_30d전':>9} {'Δβ':>6} {'cum_20d':>9} {'cum_idio_20d':>13} {'market_share*':>14}")
    rows = []
    for name, df in decomp_dict.items():
        if df.empty:
            continue
        beta_series = df['beta'].dropna()
        if beta_series.empty:
            continue
        beta_now = beta_series.iloc[-1]
        beta_then = beta_series.iloc[-30] if len(beta_series) >= 30 else np.nan
        cum_stock = df['r_stock'].tail(days).sum() * 100
        cum_idio = df['idio'].tail(days).sum() * 100
        # market_share 평균 (large-move 일만)
        large = df.tail(days)
        large = large[large['r_stock'].abs() > 0.005]
        ms = large['market_share'].mean() if not large.empty else np.nan
        rows.append((name, beta_now, beta_then, cum_stock, cum_idio, ms))

    # β 기준 정렬
    rows.sort(key=lambda r: r[1] if not np.isnan(r[1]) else -99, reverse=True)
    for name, b, b30, cs, ci, ms in rows:
        d_b = b - b30 if not np.isnan(b30) else np.nan
        print(f"  {name:<14} {b:>7.2f} {b30:>9.2f} {d_b:>+6.2f} "
              f"{cs:>+8.2f}% {ci:>+12.2f}% "
              f"{(ms*100):>13.1f}%" if not np.isnan(ms)
              else f"  {name:<14} {b:>7.2f} {b30:>9.2f} {d_b:>+6.2f} "
                   f"{cs:>+8.2f}% {ci:>+12.2f}% {'-':>14}")
    print(f"\n  * market_share = β²·Var(m)/Var(r) 비슷한 의미. 큰 움직임(>0.5%) 일자만 평균.")

    # 트리거 발동
    if triggers:
        print(f"\n🚨 발동된 교체룰 trigger ({len(triggers)} 종목):")
        for t in triggers:
            print(f"\n  ▶ {t['name']}  (20d: stock {t['cum_stock_20d_%']:+.1f}% / "
                  f"idio {t['cum_idio_20d_%']:+.1f}% / β {t['beta_now']})")
            for tr in t['triggers']:
                sev = {'high': '🔴', 'med': '🟡', 'low': '🟢', 'info': 'ℹ️'}[tr['severity']]
                print(f"    {sev} [{tr['code']}] {tr['msg']}")
    else:
        print(f"\n✅ 발동된 trigger 없음. 모든 종목 정상 범위.")

    print(f"\n{'-' * 78}")
    print("교체룰 v0 (참조용):")
    print(REPLACEMENT_RULES_V0)


def save_json_output(decomp_dict: dict[str, pd.DataFrame],
                     triggers: list[dict],
                     days: int) -> Path:
    """일별 attribution + trigger 결과 JSON 저장."""
    payload = {
        'generated_at': datetime.now().isoformat(timespec='minutes'),
        'phase': 1,
        'method': 'CAPM single-factor (market = KOSPI)',
        'lookback_days': days,
        'stocks': {},
        'triggers': triggers,
    }
    for name, df in decomp_dict.items():
        recent = df.tail(days)
        payload['stocks'][name] = {
            'beta_now': float(df['beta'].dropna().iloc[-1])
            if not df['beta'].dropna().empty else None,
            'cum_stock_%': round(float(recent['r_stock'].sum()) * 100, 3),
            'cum_market_contrib_%': round(float(recent['market_contrib'].sum()) * 100, 3),
            'cum_idio_%': round(float(recent['idio'].sum()) * 100, 3),
            'max_abs_idio_z': float(recent['idio_z'].abs().max())
            if not recent['idio_z'].dropna().empty else None,
            'daily_tail': [
                {
                    'date': str(d.date()),
                    'r_stock_%': round(row['r_stock'] * 100, 3),
                    'r_market_%': round(row['r_market'] * 100, 3),
                    'beta': round(row['beta'], 3) if not pd.isna(row['beta']) else None,
                    'market_contrib_%': round(row['market_contrib'] * 100, 3),
                    'idio_%': round(row['idio'] * 100, 3),
                    'idio_z': round(row['idio_z'], 2) if not pd.isna(row['idio_z']) else None,
                }
                for d, row in recent.iterrows()
            ],
        }
    out = BASE / f'attribution_v40_{datetime.now():%Y%m%d_%H%M}.json'
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                   encoding='utf-8')
    print(f"\n💾 JSON 저장: {out.name}")
    return out


def save_html_panel(decomp_dict: dict[str, pd.DataFrame],
                    triggers: list[dict],
                    days: int) -> Path:
    """모바일 친화 HTML 패널 — 기존 대시보드에 iframe 또는 통합 가능."""
    # 종목별 마지막 영업일 분해 (오늘의 "왜 X% 움직였나")
    today_rows = []
    for name, df in decomp_dict.items():
        if df.empty:
            continue
        last = df.iloc[-1]
        today_rows.append({
            'name': name,
            'date': str(df.index[-1].date()),
            'r_stock': last['r_stock'] * 100,
            'r_market': last['r_market'] * 100,
            'beta': last['beta'],
            'market_contrib': last['market_contrib'] * 100,
            'idio': last['idio'] * 100,
            'idio_z': last['idio_z'],
        })
    # |r_stock| 큰 순으로 정렬
    today_rows.sort(key=lambda r: abs(r['r_stock']), reverse=True)

    # 20일 누적
    cum_rows = []
    for name, df in decomp_dict.items():
        if df.empty:
            continue
        r = df.tail(days)
        cum_rows.append({
            'name': name,
            'cum_stock': r['r_stock'].sum() * 100,
            'cum_market': r['market_contrib'].sum() * 100,
            'cum_idio': r['idio'].sum() * 100,
        })
    cum_rows.sort(key=lambda r: r['cum_idio'])  # 종목 고유 약세 순

    def fmt_pct(v):
        if pd.isna(v):
            return '–'
        cls = 'pos' if v > 0 else ('neg' if v < 0 else '')
        return f'<span class="{cls}">{v:+.2f}%</span>'

    def fmt_z(v):
        if pd.isna(v):
            return '–'
        if abs(v) >= 3.0:
            return f'<span class="zalert">{v:+.2f}</span>'
        if abs(v) >= 2.0:
            return f'<span class="zwarn">{v:+.2f}</span>'
        return f'{v:+.2f}'

    today_html = ''.join(
        f"""<tr>
              <td>{r['name']}</td>
              <td>{fmt_pct(r['r_stock'])}</td>
              <td>{fmt_pct(r['market_contrib'])}</td>
              <td>{fmt_pct(r['idio'])}</td>
              <td>{r['beta']:.2f}</td>
              <td>{fmt_z(r['idio_z'])}</td>
            </tr>""" for r in today_rows
    )

    cum_html = ''.join(
        f"""<tr>
              <td>{r['name']}</td>
              <td>{fmt_pct(r['cum_stock'])}</td>
              <td>{fmt_pct(r['cum_market'])}</td>
              <td>{fmt_pct(r['cum_idio'])}</td>
            </tr>""" for r in cum_rows
    )

    trigger_html = ''
    if triggers:
        rows = []
        for t in triggers:
            for tr in t['triggers']:
                sev_cls = {'high': 'sev-high', 'med': 'sev-med',
                           'low': 'sev-low', 'info': 'sev-info'}[tr['severity']]
                rows.append(
                    f'<li class="{sev_cls}"><b>{t["name"]}</b> [{tr["code"]}] '
                    f'{tr["msg"]}</li>'
                )
        trigger_html = '<ul class="triggers">' + ''.join(rows) + '</ul>'
    else:
        trigger_html = '<p class="ok">✅ 발동된 trigger 없음.</p>'

    today_date = today_rows[0]['date'] if today_rows else '–'

    html = f"""<!DOCTYPE html>
<html lang="ko"><head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>진우퀀트 v4.0 Attribution Phase 1</title>
<style>
  body {{ font-family: -apple-system, "Apple SD Gothic Neo", sans-serif;
          background:#0f1419; color:#e0e6ed; padding:12px; margin:0;
          font-size:13px; line-height:1.45; }}
  h1 {{ color:#4fc3f7; font-size:18px; margin:4px 0 12px; }}
  h2 {{ color:#ffd54f; font-size:14px; margin:18px 0 6px;
        border-bottom:1px solid #2c3e50; padding-bottom:4px; }}
  .sub {{ color:#9e9e9e; font-size:11px; margin-bottom:8px; }}
  table {{ width:100%; border-collapse:collapse; font-size:12px;
           background:#1a232e; border-radius:6px; overflow:hidden; }}
  th {{ background:#2c3e50; color:#bbdefb; padding:6px 4px; text-align:right;
        font-weight:600; }}
  th:first-child, td:first-child {{ text-align:left; }}
  td {{ padding:5px 4px; border-top:1px solid #2c3e50; text-align:right; }}
  .pos {{ color:#81c784; font-weight:600; }}
  .neg {{ color:#e57373; font-weight:600; }}
  .zalert {{ color:#ff5252; font-weight:700; background:#3a0f0f;
             padding:1px 4px; border-radius:3px; }}
  .zwarn {{ color:#ffb74d; font-weight:600; }}
  ul.triggers {{ list-style:none; padding:0; margin:0; }}
  ul.triggers li {{ background:#1a232e; padding:8px 10px; margin:6px 0;
                    border-radius:4px; border-left:3px solid; }}
  .sev-high {{ border-color:#ff5252; }}
  .sev-med {{ border-color:#ffb74d; }}
  .sev-low {{ border-color:#81c784; }}
  .sev-info {{ border-color:#4fc3f7; }}
  .ok {{ background:#0f2a1a; padding:10px; border-radius:6px;
         border-left:3px solid #81c784; }}
  .footnote {{ color:#7a8a99; font-size:11px; margin-top:24px;
               padding-top:12px; border-top:1px solid #2c3e50; }}
</style></head><body>

<h1>진우퀀트 v4.0 Attribution — Phase 1 (CAPM)</h1>
<div class="sub">생성: {datetime.now():%Y-%m-%d %H:%M} · β window 60d · 분해: r = β·r_KOSPI + idio</div>

<h2>🚨 교체룰 trigger 발동</h2>
{trigger_html}

<h2>📅 오늘 변동 분해 ({today_date}) — |r| 큰 순</h2>
<table>
  <thead><tr><th>종목</th><th>오늘 r</th><th>시장 기여</th><th>종목 고유</th><th>β</th><th>idio z</th></tr></thead>
  <tbody>{today_html}</tbody>
</table>

<h2>📈 최근 {days}영업일 누적 분해 (종목 고유 약세 순)</h2>
<table>
  <thead><tr><th>종목</th><th>누적 r</th><th>시장 기여</th><th>종목 고유</th></tr></thead>
  <tbody>{cum_html}</tbody>
</table>

<div class="footnote">
  <p><b>읽는 법:</b> "종목 고유" 컬럼이 종목 자체 알파. 시장 동조가 빼면 남는 값.<br>
  <b>idio z:</b> 종목 고유 수익률의 60d 표준화 점수. |z| ≥ 3 = 이벤트 의심.<br>
  <b>다음 Phase:</b> Phase 2에서 산업 ETF factor 추가 → "시장 / 산업 / 종목" 3단 분해.</p>
</div>

</body></html>"""
    out = BASE / 'attribution_panel.html'
    out.write_text(html, encoding='utf-8')
    print(f"📊 HTML 패널: {out.name}")
    return out


# ============================================
# 메인
# ============================================
def main():
    args = parse_args()

    rets = fetch_returns_panel(args.fetch_days)
    if rets.empty:
        print("\n❌ 데이터 수집 실패 — 종료")
        sys.exit(1)

    if '_KOSPI' not in rets.columns:
        print("❌ KOSPI 수익률이 없음 — 종료")
        sys.exit(1)

    decomp = decompose_all(rets, window=args.beta_win)
    triggers = evaluate_triggers(decomp,
                                 lookback_days=args.days,
                                 z_threshold=args.z_threshold)

    print_summary(decomp, triggers, days=args.days)

    if args.save_json:
        save_json_output(decomp, triggers, days=args.days)
    if args.save_html:
        save_html_panel(decomp, triggers, days=args.days)


if __name__ == '__main__':
    main()
