#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""진우퀀트 모듈 E (v4.0) — 밸류·피크 오버레이 레이어 (production 무수정, 가산 레이어).

설계 근거(가치투자 피드백 §6~10, PIT 검증):
  · 밸류는 '수익 엔진'이 아니라 '선택 도구' → 저가중 ±1 팩터로만 반영 (VAL_W=0.5).
  · 퀄리티는 이미 체력_12점(F-score)에 반영 → 그대로 둠. 모멘텀은 v37_2/v40가 담당.
  · 핵심 신규 가치: '비싸고(밸류 하위) + 과열된(SMA 대비 급등)' 경기민감주에 PEAK 트림 신호.
    (MA200 방어가 +100% 과열 구간에선 너무 늦게 작동 → 트림이 실질 방어, §10)

레이어 방식(v40 regime와 동일 철학): score_v37_2/score_v40 산출 df에 컬럼만 추가.
  추가 컬럼: 밸류(±1), B/M, 이격_SMA%, 피크플래그, 트림권고, 체력_밸류조정
  체력_밸류조정 = score_col + VAL_W*밸류 − PEAK_PENALTY*피크플래그   (등급 재계산은 호출측 선택)

검증결과(PIT 백테스트): 기계적 트림(피크명 제외)은 v40 합격선 미달(CAGR −9~12%p) → 2021-26엔
  비싼+과열=승자(반도체)였기 때문. 따라서 본 오버레이는 '자동 등급변경'이 아니라 **경보(트림권고 flag)**
  용도. 체력_밸류조정은 진단/참고용이며 production 등급·비중에 자동 반영하지 말 것.
  섹터별 임계값: 반도체·2차전지 등 경기민감은 더 일찍 경고(낮은 과열 임계).
데이터(로컬): book_equity.csv, liquidity_sector.csv(+kosdaq), kospi/kosdaq_monthly_prices.csv
실행 데모: python value_peak_overlay.py          (v39 점수에 오버레이 적용 출력)
self-test: python value_peak_overlay.py --selftest
"""
import sys, argparse
import numpy as np, pandas as pd
from pathlib import Path
BASE = Path(__file__).parent.resolve()

VAL_W = 0.5          # 밸류 가중 (저가중 — 선택 도구지 엔진 아님)
PEAK_PENALTY = 1.5   # 비쌈+과열 시 체력 차감
PEAK_STRETCH = 0.40  # 기본 과열 임계 (현재가 > 10M_SMA × 1.40)
WATCH_STRETCH = 0.20
# 섹터별 차등(경기민감은 더 민감하게 = 낮은 임계로 일찍 경고)
SECTOR_STRETCH = {'반도체':0.25,'2차전지':0.25,'배터리':0.25,'원전':0.30,'방산':0.30,
                  '종합상사':0.30,'상사':0.30,'자동차':0.30,'조선':0.30,'화학':0.30,'철강':0.30,'건설':0.30}

def stretch_thresh(sector):
    if isinstance(sector,str):
        for k,v in SECTOR_STRETCH.items():
            if k in sector: return v
    return PEAK_STRETCH
SMA_N = 10
TERCILE = 1/3


def _read(n, **kw):
    return pd.read_csv(BASE / n, encoding='utf-8-sig', **kw)


def load_book():
    be = _read('book_equity.csv', dtype={'code': str}); be['code'] = be['code'].str.zfill(6)
    return be.sort_values('fiscal_year').groupby('code').tail(1).set_index('code')['book_equity']


def load_mcap():
    mc = {}
    for f in ['liquidity_sector.csv', 'liquidity_kosdaq.csv']:
        p = BASE / f
        if p.exists():
            d = pd.read_csv(p, encoding='utf-8-sig', dtype={'code': str}); d['code'] = d['code'].str.zfill(6)
            mc.update(dict(zip(d['code'], pd.to_numeric(d['mcap'], errors='coerce'))))
    return mc


def load_prices():
    def lp(f):
        p = BASE / f
        if not p.exists():
            return None
        d = pd.read_csv(p, encoding='utf-8-sig'); d = d.rename(columns={d.columns[0]: 'Date'})
        d['Date'] = pd.to_datetime(d['Date']); d = d.set_index('Date').sort_index()
        d.columns = [str(c).zfill(6) for c in d.columns]; return d.apply(pd.to_numeric, errors='coerce')
    a = lp('kospi_monthly_prices.csv'); b = lp('kosdaq_monthly_prices.csv')
    if a is None:
        return b
    if b is None:
        return a
    return a.join(b[[c for c in b.columns if c not in a.columns]], how='outer').sort_index()


def sma_stretch(px, code, asof=None):
    if px is None or code not in px.columns:
        return np.nan
    s = (px[code] if asof is None else px.loc[:asof, code]).dropna()
    if len(s) < SMA_N:
        return np.nan
    return float(s.iloc[-1] / s.iloc[-SMA_N:].mean() - 1)


def apply_overlay(df, code_col='코드', score_col='체력_최종', name_to_code=None, asof=None):
    """점수 df에 밸류·피크 컬럼 추가. df는 code_col 또는 name_to_code(dict)로 코드 매핑."""
    df = df.copy()
    if code_col not in df.columns and name_to_code:
        df[code_col] = df['종목'].map(name_to_code)
    df[code_col] = df[code_col].astype(str).str.zfill(6)
    book, mcap, px = load_book(), load_mcap(), load_prices()
    bm = {}
    for c in df[code_col]:
        b, m = book.get(c), mcap.get(c)
        bm[c] = (b / m) if (b is not None and m and m > 0) else np.nan
    df['B/M'] = df[code_col].map(bm)
    s = df['B/M'].dropna()
    hi = s.quantile(1 - TERCILE) if len(s) >= 3 else np.inf   # 고 B/M = 쌈
    lo = s.quantile(TERCILE) if len(s) >= 3 else -np.inf
    df['밸류'] = df['B/M'].apply(lambda v: 1 if (v == v and v >= hi) else (-1 if (v == v and v <= lo) else 0))
    df['이격_SMA%'] = df[code_col].apply(lambda c: round(sma_stretch(px, c, asof) * 100, 1) if sma_stretch(px, c, asof) == sma_stretch(px, c, asof) else np.nan)
    sec_col = '산업' if '산업' in df.columns else ('sector' if 'sector' in df.columns else None)
    df['_thr'] = df[sec_col].apply(stretch_thresh) if sec_col else PEAK_STRETCH
    def peak(r):
        st = r['이격_SMA%']
        return bool(r['밸류'] == -1 and st == st and st / 100 > r['_thr'])
    df['피크플래그'] = df.apply(peak, axis=1)
    def trim(r):
        st = r['이격_SMA%']
        if r['피크플래그']:
            return 'TRIM(비쌈+과열)'
        if r['밸류'] == -1 and st == st and st / 100 > WATCH_STRETCH:
            return 'WATCH(비쌈)'
        return ''
    df['트림권고'] = df.apply(trim, axis=1)
    df['체력_밸류조정'] = df[score_col] + VAL_W * df['밸류'] - PEAK_PENALTY * df['피크플래그'].astype(float)
    if '_thr' in df.columns:
        df = df.drop(columns=['_thr'])
    return df


def _demo():
    f = BASE / 'v39_pead_scores_latest.csv'
    if not f.exists():
        print('데모 입력(v39_pead_scores_latest.csv) 없음'); return
    df = _read('v39_pead_scores_latest.csv')
    sc = '체력_v39' if '체력_v39' in df.columns else ('체력_최종' if '체력_최종' in df.columns else df.columns[-1])
    out = apply_overlay(df, code_col='코드', score_col=sc)
    cols = ['종목', sc, 'B/M', '밸류', '이격_SMA%', '피크플래그', '트림권고', '체력_밸류조정']
    show = out[cols].copy(); show['B/M'] = show['B/M'].round(3); show['체력_밸류조정'] = show['체력_밸류조정'].round(2)
    print('=== 밸류·피크 오버레이 적용 (v39 점수, 기준=최신가) ===')
    print(show.sort_values('체력_밸류조정', ascending=False).to_string(index=False))
    print('\nVAL_W=%.1f, PEAK_PENALTY=%.1f, PEAK_STRETCH=%d%%' % (VAL_W, PEAK_PENALTY, int(PEAK_STRETCH * 100)))
    print('트림권고 종목:', ', '.join(out[out['트림권고'] != '']['종목'].tolist()) or '없음')


def _selftest():
    df = pd.DataFrame({'종목': ['A', 'B', 'C', 'D'], '코드': ['000001', '000002', '000003', '000004'], '체력_최종': [12.0, 11.0, 10.0, 9.0]})
    # 가짜 데이터 주입
    import types
    g = globals()
    g['load_book'] = lambda: pd.Series({'000001': 100, '000002': 50, '000003': 10, '000004': 80}, name='book_equity')
    g['load_mcap'] = lambda: {'000001': 100, '000002': 50, '000003': 1000, '000004': 100}  # C 매우 비쌈(B/M 0.01)
    idx = pd.date_range('2024-01-31', periods=14, freq='ME')
    pxd = pd.DataFrame({'000001': np.linspace(100, 110, 14), '000002': np.linspace(100, 105, 14),
                        '000003': np.array([100.]*10+[120,140,170,220]), '000004': np.linspace(100, 102, 14)}, index=idx)
    g['load_prices'] = lambda: pxd
    out = apply_overlay(df, code_col='코드', score_col='체력_최종')
    assert out.loc[out['종목'] == 'C', '밸류'].iloc[0] == -1, 'C는 비쌈(-1)'
    assert bool(out.loc[out['종목'] == 'C', '피크플래그'].iloc[0]) == True, 'C는 비쌈+과열 → 피크'
    assert out.loc[out['종목'] == 'C', '체력_밸류조정'].iloc[0] == 10.0 + 0.5 * (-1) - 1.5, '체력 조정 확인'
    print('[OK] value_peak_overlay self-test 통과 (밸류 ±1 / 피크플래그 / 체력_밸류조정)')


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    ap = argparse.ArgumentParser(); ap.add_argument('--selftest', action='store_true')
    a, _ = ap.parse_known_args()
    _selftest() if a.selftest else _demo()
