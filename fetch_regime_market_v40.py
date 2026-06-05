#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""진우퀀트 모듈 D (v4.0 영역2 regime) — Stage 1+2: 시장 데이터 수집 + regime 시계열.

산출물:
  1. regime_market_cache_v40.json — 변동성 시계열(VKOSPI 또는 실현변동성 proxy) + 외인·기관 수급
  2. regime_history_v40.csv       — 4년 월별 시장 regime (sanity check 용 — 판정과 무관)

데이터 전략 (graceful degradation, 결정메모 §4):
  - KOSPI: FDR (필수 — 실패 시 중단)
  - VKOSPI: pykrx 인덱스 검색('변동성') 시도 → 실패 시 KOSPI 20일 실현변동성 proxy
  - 수급(외인+기관 순매수): pykrx 시도 → 실패 시 None (요소 제외·재정규화)

실행 = 진우 PC: python fetch_regime_market_v40.py
사전 검증:        python fetch_regime_market_v40.py --selftest  (네트워크 불필요)
"""
import sys, json, argparse
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import pandas as pd

BASE = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE))

from regime_detector_v40 import (trend_signal, vol_signal, vol_signal_pct,
                                 flow_signal, composite_score, classify_regime,
                                 DEFAULT_WEIGHTS)

CACHE_FILE = BASE / 'regime_market_cache_v40.json'
HISTORY_FILE = BASE / 'regime_history_v40.csv'
YEARS_DATA = 6      # 수집 기간 (MA200 + 4년 히스토리 여유)
YEARS_HISTORY = 4   # regime 시계열 기간 (공식 백테스트와 동일)


# ============================================================
# 1) 수집
# ============================================================

def fetch_kospi(years=YEARS_DATA):
    import FinanceDataReader as fdr
    try:
        from score_v37 import KOSPI_CODE
    except Exception:
        KOSPI_CODE = 'KS11'
    end = datetime.now()
    start = end - timedelta(days=int(365 * years))
    df = fdr.DataReader(KOSPI_CODE, start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
    s = df['Close'].dropna()
    print(f"  [1] KOSPI OK: {len(s)}일 ({s.index[0].date()} ~ {s.index[-1].date()})")
    return s


def try_fetch_vkospi(start, end):
    """pykrx 인덱스 목록에서 '변동성' 포함 지수 검색 → OHLCV 종가.
    실패하면 (None, 사유) 반환 — 호출부가 실현변동성 proxy로 폴백."""
    try:
        from pykrx import stock
    except ImportError:
        return None, 'pykrx 미설치'
    try:
        found = None
        for market in ('KRX', 'KOSPI', '테마'):
            try:
                for t in stock.get_index_ticker_list(market=market):
                    name = stock.get_index_ticker_name(t)
                    if '변동성' in str(name):
                        found = (t, name, market); break
            except Exception:
                continue
            if found: break
        if not found:
            return None, "pykrx 인덱스 목록에 '변동성' 없음"
        t, name, market = found
        df = stock.get_index_ohlcv_by_date(start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), t)
        col = '종가' if '종가' in df.columns else df.columns[min(3, len(df.columns)-1)]
        s = df[col].dropna()
        if len(s) < 250:
            return None, f'{name}({t}) 데이터 부족 ({len(s)}일)'
        print(f"  [2] VKOSPI OK: {name}({t}, {market}) {len(s)}일")
        return s, None
    except Exception as e:
        return None, f'pykrx VKOSPI 오류: {e}'


def try_fetch_flows(start, end):
    """KOSPI 시장 투자자별 순매수 거래대금 → (외국인+기관) 20일 rolling 합.
    실패하면 (None, 사유)."""
    try:
        from pykrx import stock
    except ImportError:
        return None, 'pykrx 미설치'
    try:
        df = stock.get_market_trading_value_by_date(
            start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), 'KOSPI')
        fcol = [c for c in df.columns if '외국인' in str(c)]
        icol = [c for c in df.columns if str(c).startswith('기관')]
        if not fcol or not icol:
            return None, f'투자자 컬럼 인식 실패: {list(df.columns)}'
        daily = df[fcol[0]] + df[icol[0]]
        s = daily.rolling(20).sum().dropna()
        print(f"  [3] 수급 OK: 외국인({fcol[0]})+기관({icol[0]}) 20일 누적, {len(s)}일")
        return s, None
    except Exception as e:
        return None, f'pykrx 수급 오류: {e}'


def realized_vol(kospi, win=20):
    """실현변동성 proxy: 20일 수익률 std 연환산 %."""
    return (kospi.pct_change().rolling(win).std() * np.sqrt(252) * 100).dropna()


def build_cache():
    print("\n📊 시장 데이터 수집:")
    kospi = fetch_kospi()
    start, end = kospi.index[0], kospi.index[-1]

    vk, why_v = try_fetch_vkospi(start, end)
    if vk is None:
        vk = realized_vol(kospi)
        print(f"  [2] VKOSPI 실패({why_v}) → 실현변동성 proxy 사용 ({len(vk)}일)")
        vol_is_vkospi = False
    else:
        vol_is_vkospi = True

    fl, why_f = try_fetch_flows(start, end)
    if fl is None:
        print(f"  [3] 수급 실패({why_f}) → 요소 제외(재정규화)로 진행")

    def ser2dict(s):
        return {pd.Timestamp(k).strftime('%Y-%m-%d'): float(v) for k, v in s.items()}

    cache = {
        '_meta': {'created': datetime.now().isoformat(),
                  'vol_is_vkospi': vol_is_vkospi,
                  'vol_fail_reason': why_v, 'flow_fail_reason': why_f,
                  'start': str(start.date()), 'end': str(end.date())},
        'vol_series': ser2dict(vk),
        'flow_cum20': ser2dict(fl) if fl is not None else None,
    }
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding='utf-8')
    print(f"  💾 캐시 저장: {CACHE_FILE.name} "
          f"(vol={'VKOSPI' if vol_is_vkospi else 'realized_proxy'}, "
          f"flow={'OK' if fl is not None else '없음'})")
    return kospi, cache


def load_cache_series(cache):
    """캐시 dict → (vol Series, vol_is_vkospi, flow Series|None)."""
    def d2ser(d):
        if not d:
            return None
        s = pd.Series(d)
        s.index = pd.to_datetime(s.index)
        return s.sort_index()
    return (d2ser(cache.get('vol_series')),
            bool(cache.get('_meta', {}).get('vol_is_vkospi')),
            d2ser(cache.get('flow_cum20')))


# ============================================================
# 2) 시장 regime 시계열 (trend+vol+flow 3요소 — sanity 용)
# ============================================================

def market_signals_at(dt, kospi, vol_s, vol_is_vkospi, flow_s, flow_win=250):
    sig = {'trend': trend_signal(kospi, dt)}
    if vol_s is not None:
        sig['vol'] = (vol_signal(vol_s, dt) if vol_is_vkospi
                      else vol_signal_pct(vol_s, dt))
    else:
        sig['vol'] = None
    if flow_s is not None:
        cut = flow_s[flow_s.index <= dt].tail(flow_win)
        sig['flow'] = flow_signal(cut) if len(cut) >= 60 else None
    else:
        sig['flow'] = None
    return sig


def month_starts(index, years=YEARS_HISTORY):
    """공식 엔진과 동일한 월초 리밸일 산출 (resample MS → bfill 거래일)."""
    end = index[-1]
    start = end - pd.DateOffset(years=years)
    win = index[(index >= start) & (index <= end)]
    ms = pd.Series(1, index=win).resample('MS').first().dropna().index
    out = sorted({index[index.get_indexer([d], method='bfill')[0]] for d in ms if d <= end})
    return out


def build_history(kospi, cache, write=True, verbose=True):
    vol_s, vol_is_vkospi, flow_s = load_cache_series(cache)
    dates = month_starts(kospi.index)
    rows, prev = [], None
    for d0 in dates:
        # MA200 워밍업 미달 시점은 신호 왜곡 → 건너뜀 (production은 6년 수집이라 해당 없음)
        if len(kospi[kospi.index <= d0]) < 260:
            continue
        sig = market_signals_at(d0, kospi, vol_s, vol_is_vkospi, flow_s)
        score, used = composite_score(sig, DEFAULT_WEIGHTS)
        state = classify_regime(score, prev_state=prev)
        prev = state
        rows.append({'date': pd.Timestamp(d0).strftime('%Y-%m-%d'),
                     'trend': sig['trend'], 'vol': sig['vol'], 'flow': sig['flow'],
                     'score': score, 'state': state, 'n_factors': len(used)})
    df = pd.DataFrame(rows)
    if write:
        df.to_csv(HISTORY_FILE, index=False, encoding='utf-8-sig')

    if verbose:
        print(f"\n📈 시장 regime 시계열 ({len(df)}개월)"
              + (f" → {HISTORY_FILE.name}" if write else " (미저장)"))
        print("   ⚠️ 이 CSV는 시장 3요소 sanity용 — 판정은 backtest_v40_regime.py의 5요소(섹터·팩터 포함)가 권위")
        cnt = df['state'].value_counts()
        for st in ('RISK_ON', 'NEUTRAL', 'RISK_OFF'):
            print(f"   {st:9s}: {int(cnt.get(st, 0)):2d}개월")
        off = df[df['state'] == 'RISK_OFF']['date'].tolist()
        print(f"   RISK_OFF 달: {off if off else '없음'}")
        print("\n   [sanity 체크포인트] 2022년(약세장)에 RISK_OFF/NEUTRAL 몰려 있고,")
        print("   2024-08(급락) 부근 플래그, 2023~25 강세 구간은 RISK_ON 위주면 정상.")
    return df


# ============================================================
# 3) self-test (synthetic, 네트워크 불필요)
# ============================================================

def _selftest():
    ok = 0
    # 6년 데이터 (워밍업 2년 + 히스토리 4년 — production과 동일 비율)
    idx = pd.bdate_range('2020-01-01', periods=1560)
    rng = np.random.default_rng(40)
    bull = pd.Series(100 * np.cumprod(1 + rng.normal(0.0010, 0.004, 1560)), index=idx)
    # 폭락 시나리오: 후반부(히스토리 구간 내) 100일간 -33%
    path = np.ones(1560) * 0.0010
    path[1150:1250] = -0.0040
    crash = pd.Series(100 * np.cumprod(1 + path + rng.normal(0, 0.004, 1560)), index=idx)

    rv_b, rv_c = realized_vol(bull), realized_vol(crash)
    assert len(rv_b) > 1400 and rv_b.min() > 0; ok += 1

    # 캐시 직렬화 왕복
    def mk_cache(rv):
        return {'_meta': {'vol_is_vkospi': False},
                'vol_series': {pd.Timestamp(k).strftime('%Y-%m-%d'): float(v) for k, v in rv.items()},
                'flow_cum20': None}
    cache = mk_cache(rv_c)
    vol_s, isv, flow_s = load_cache_series(cache)
    assert vol_s is not None and not isv and flow_s is None and len(vol_s) == len(rv_c); ok += 1

    # 히스토리 (selftest는 미저장·조용히): 상승장 RISK_OFF 거의 없음, 폭락장엔 존재
    df_b = build_history(bull, mk_cache(rv_b), write=False, verbose=False)
    df_c = build_history(crash, cache, write=False, verbose=False)
    n_off_b = int((df_b['state'] == 'RISK_OFF').sum())
    n_off_c = int((df_c['state'] == 'RISK_OFF').sum())
    assert n_off_c >= 2, '폭락 시나리오에서 RISK_OFF 미발동'; ok += 1
    assert n_off_b <= 2, f'상승장 RISK_OFF 과다 ({n_off_b})'; ok += 1
    assert n_off_c > n_off_b; ok += 1
    assert set(df_c['n_factors'].unique()) <= {2}, 'flow=None이면 2요소(재정규화)'; ok += 1

    # 월초 리밸일: 4년 ≈ 48~50개 (워밍업 skip 후에도 유지)
    assert 45 <= len(df_c) <= 51, f'개월 수 이상: {len(df_c)}'; ok += 1

    # 폭락 구간(1150일째 이후) 부근에 RISK_OFF가 몰려 있는지
    off_dates = pd.to_datetime(df_c[df_c['state'] == 'RISK_OFF']['date'])
    crash_start = idx[1150]
    assert (off_dates >= crash_start - pd.Timedelta(days=40)).all(), \
        f'폭락 전 구간에 가짜 RISK_OFF: {off_dates.tolist()}'; ok += 1

    print(f"[OK] fetch_regime_market_v40 self-test 통과 ({ok} checks)")
    print(f"     bull RISK_OFF={n_off_b}, crash RISK_OFF={n_off_c} (방향 정상)")
    print("     실 수집은 진우님 PC에서: python fetch_regime_market_v40.py")


def main():
    print("=" * 70)
    print("진우퀀트 모듈 D — regime 시장 데이터 수집 + 시계열 (Stage 1+2)")
    print("=" * 70)
    kospi, cache = build_cache()
    build_history(kospi, cache)
    print("\n다음 단계: python backtest_v40_regime.py --selftest 후 본 실행")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--selftest', action='store_true')
    a, _ = ap.parse_known_args()
    try:
        _selftest() if a.selftest else main()
    except Exception:
        import traceback
        print("\n===== [에러] 아래 내용을 그대로 복사해 붙여주세요 =====")
        traceback.print_exc()
