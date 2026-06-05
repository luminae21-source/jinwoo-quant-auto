#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""진우퀀트 모듈 D 확장 (조건 1) — KOSDAQ 별도 regime 데이터 레이어.

목적: 코스닥 종목용 regime은 KOSPI 신호로 판단하면 부정확 → KOSDAQ 지수(KQ11)·
KOSDAQ 수급으로 **별도 detector 입력**을 만들고, KOSPI regime과 실제로 얼마나
어긋나는지 데이터로 확인한다. (영역 3 universe 확장 시 그대로 재사용)

⚠️ 범위: 데이터 레이어 + 국면 비교 리포트까지만. 백테스트·판정 없음 —
   코스닥 종목 적용(전 종목 F_korean = DART 자동화)은 영역 3 본체.

산출물:
  1. regime_market_cache_v40_kosdaq.json — KOSDAQ 실현변동성 + 외인·기관 수급
     (KOSDAQ 변동성지수는 KRX에 없음 → 처음부터 실현변동성 proxy)
  2. regime_history_v40_kosdaq.csv — 4년 월별 KOSDAQ 시장 regime
  3. 콘솔: KOSPI(regime_history_v40.csv)와의 월별 국면 일치/어긋남 표

기존 KOSPI 파일(fetch_regime_market_v40.py, 캐시, CSV)은 무수정 — import만.

실행 = 진우 PC: python fetch_regime_kosdaq_v40.py
  (선행: python fetch_regime_market_v40.py 가 만든 regime_history_v40.csv 있으면 비교까지 출력)
사전 검증:        python fetch_regime_kosdaq_v40.py --selftest  (네트워크 불필요)
"""
import sys, json, argparse
from datetime import datetime, timedelta
from pathlib import Path
import numpy as np
import pandas as pd

BASE = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE))

from regime_detector_v40 import composite_score, classify_regime, DEFAULT_WEIGHTS
from fetch_regime_market_v40 import (realized_vol, load_cache_series,
                                     market_signals_at, month_starts,
                                     YEARS_DATA, YEARS_HISTORY)

KOSDAQ_CODE = 'KQ11'
CACHE_FILE = BASE / 'regime_market_cache_v40_kosdaq.json'
HISTORY_FILE = BASE / 'regime_history_v40_kosdaq.csv'
KOSPI_HISTORY = BASE / 'regime_history_v40.csv'


# ============================================================
# 1) 수집 (KOSDAQ 판)
# ============================================================

def fetch_kosdaq(years=YEARS_DATA):
    import FinanceDataReader as fdr
    end = datetime.now()
    start = end - timedelta(days=int(365 * years))
    df = fdr.DataReader(KOSDAQ_CODE, start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
    s = df['Close'].dropna()
    print(f"  [1] KOSDAQ OK: {len(s)}일 ({s.index[0].date()} ~ {s.index[-1].date()})")
    return s


def try_fetch_kosdaq_flows(start, end):
    """KOSDAQ 시장 투자자별 순매수 거래대금 → (외국인+기관) 20일 rolling 합."""
    try:
        from pykrx import stock
    except ImportError:
        return None, 'pykrx 미설치'
    try:
        df = stock.get_market_trading_value_by_date(
            start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), 'KOSDAQ')
        fcol = [c for c in df.columns if '외국인' in str(c)]
        icol = [c for c in df.columns if str(c).startswith('기관')]
        if not fcol or not icol:
            return None, f'투자자 컬럼 인식 실패: {list(df.columns)}'
        s = (df[fcol[0]] + df[icol[0]]).rolling(20).sum().dropna()
        print(f"  [2] KOSDAQ 수급 OK: 외국인({fcol[0]})+기관({icol[0]}) 20일 누적, {len(s)}일")
        return s, None
    except Exception as e:
        return None, f'pykrx KOSDAQ 수급 오류: {e}'


def build_kosdaq_cache():
    print("\n📊 KOSDAQ 시장 데이터 수집:")
    kq = fetch_kosdaq()
    start, end = kq.index[0], kq.index[-1]

    # KOSDAQ 변동성지수는 KRX 미제공 → 실현변동성 proxy 고정
    vk = realized_vol(kq)
    print(f"  [2] 변동성: KOSDAQ 실현변동성 proxy ({len(vk)}일) — VKOSDAQ 지수는 KRX에 없음")

    fl, why_f = try_fetch_kosdaq_flows(start, end)
    if fl is None:
        print(f"  [3] 수급 실패({why_f}) → 요소 제외(재정규화)로 진행")

    def ser2dict(s):
        return {pd.Timestamp(k).strftime('%Y-%m-%d'): float(v) for k, v in s.items()}

    cache = {
        '_meta': {'created': datetime.now().isoformat(), 'market': 'KOSDAQ',
                  'vol_is_vkospi': False, 'flow_fail_reason': why_f,
                  'start': str(start.date()), 'end': str(end.date())},
        'vol_series': ser2dict(vk),
        'flow_cum20': ser2dict(fl) if fl is not None else None,
    }
    CACHE_FILE.write_text(json.dumps(cache, ensure_ascii=False), encoding='utf-8')
    print(f"  💾 캐시 저장: {CACHE_FILE.name} (vol=realized_proxy, flow={'OK' if fl is not None else '없음'})")
    return kq, cache


# ============================================================
# 2) KOSDAQ regime 시계열 + KOSPI 비교
# ============================================================

def build_kosdaq_history(kq, cache, write=True, verbose=True):
    vol_s, _, flow_s = load_cache_series(cache)
    rows, prev = [], None
    for d0 in month_starts(kq.index):
        if len(kq[kq.index <= d0]) < 260:
            continue
        sig = market_signals_at(d0, kq, vol_s, False, flow_s)
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
        print(f"\n📈 KOSDAQ regime 시계열 ({len(df)}개월)"
              + (f" → {HISTORY_FILE.name}" if write else " (미저장)"))
        cnt = df['state'].value_counts()
        for st in ('RISK_ON', 'NEUTRAL', 'RISK_OFF'):
            print(f"   {st:9s}: {int(cnt.get(st, 0)):2d}개월")
        off = df[df['state'] == 'RISK_OFF']['date'].tolist()
        print(f"   RISK_OFF 달: {off if off else '없음'}")
    return df


def compare_with_kospi(df_kq, kospi_csv=KOSPI_HISTORY, verbose=True):
    """월(YYYY-MM) 기준으로 KOSPI/KOSDAQ regime 정렬 비교 → 어긋남 통계."""
    if not Path(kospi_csv).exists():
        if verbose:
            print(f"\n⚠️ {Path(kospi_csv).name} 없음 → KOSPI 비교 생략 "
                  f"(fetch_regime_market_v40.py 먼저 실행하면 비교 출력)")
        return None
    df_ks = pd.read_csv(kospi_csv)
    a = df_ks[['date', 'state']].copy(); a['m'] = a['date'].str[:7]
    b = df_kq[['date', 'state']].copy(); b['m'] = b['date'].str[:7]
    j = a.merge(b, on='m', suffixes=('_kospi', '_kosdaq'))
    if len(j) == 0:
        return None
    j['같음'] = j['state_kospi'] == j['state_kosdaq']
    n, same = len(j), int(j['같음'].sum())
    diff = j[~j['같음']]
    if verbose:
        print(f"\n🔀 KOSPI vs KOSDAQ 국면 비교 ({n}개월 매칭):")
        print(f"   일치 {same}/{n} ({same/n*100:.0f}%) · 어긋남 {n-same}개월")
        if len(diff):
            print("   어긋난 달 (KOSPI / KOSDAQ):")
            for _, r in diff.iterrows():
                print(f"     {r['m']}: {r['state_kospi']:8s} / {r['state_kosdaq']}")
        print("   → 어긋남이 유의미하면 '코스닥 종목엔 KOSDAQ detector 필수' 근거 확정")
    return j


# ============================================================
# 3) self-test (synthetic, 네트워크 불필요)
# ============================================================

def _selftest():
    ok = 0
    idx = pd.bdate_range('2020-01-01', periods=1560)
    rng = np.random.default_rng(42)
    # KOSPI: 완만한 상승 / KOSDAQ: 후반 폭락 — 의도적으로 어긋난 두 시장
    ks = pd.Series(100 * np.cumprod(1 + rng.normal(0.0010, 0.004, 1560)), index=idx)
    path = np.ones(1560) * 0.0010
    path[1150:1250] = -0.0045
    kq = pd.Series(100 * np.cumprod(1 + path + rng.normal(0, 0.005, 1560)), index=idx)

    def mk_cache(s):
        rv = realized_vol(s)
        return {'_meta': {'vol_is_vkospi': False},
                'vol_series': {pd.Timestamp(k).strftime('%Y-%m-%d'): float(v) for k, v in rv.items()},
                'flow_cum20': None}

    df_kq = build_kosdaq_history(kq, mk_cache(kq), write=False, verbose=False)
    assert 45 <= len(df_kq) <= 51; ok += 1
    assert int((df_kq['state'] == 'RISK_OFF').sum()) >= 2, 'KOSDAQ 폭락 미감지'; ok += 1

    # KOSPI 히스토리를 임시 CSV로 만들어 비교 로직 검증
    from fetch_regime_market_v40 import build_history
    df_ks = build_history(ks, mk_cache(ks), write=False, verbose=False)
    import tempfile, os
    tmp = Path(tempfile.gettempdir()) / '_kospi_hist_test.csv'
    df_ks.to_csv(tmp, index=False, encoding='utf-8-sig')
    j = compare_with_kospi(df_kq, kospi_csv=tmp, verbose=False)
    os.unlink(tmp)
    assert j is not None and len(j) >= 40; ok += 1
    n_diff = int((~j['같음']).sum())
    assert n_diff >= 2, f'의도적 어긋남 시나리오인데 차이 {n_diff}개월'; ok += 1
    # 폭락 구간에 'KOSDAQ만 RISK_OFF'인 어긋남이 존재해야 함 (핵심 시나리오)
    crash_m = str(idx[1150])[:7]
    core = j[(~j['같음']) & (j['m'] >= crash_m) & (j['state_kosdaq'] == 'RISK_OFF')]
    assert len(core) >= 1, 'KOSDAQ 단독 폭락이 비교에서 안 잡힘'; ok += 1

    # 비교 파일 없음 → None (안전)
    assert compare_with_kospi(df_kq, kospi_csv=BASE / '없는파일.csv', verbose=False) is None; ok += 1

    print(f"[OK] fetch_regime_kosdaq_v40 self-test 통과 ({ok} checks)")
    print(f"     synthetic: KOSDAQ RISK_OFF={int((df_kq['state']=='RISK_OFF').sum())}, "
          f"KOSPI와 어긋남={n_diff}개월 (의도된 시나리오)")
    print("     실 수집은 진우님 PC에서: python fetch_regime_kosdaq_v40.py")


def main():
    print("=" * 70)
    print("진우퀀트 모듈 D 확장 — KOSDAQ 별도 regime 데이터 레이어 (조건 1)")
    print("=" * 70)
    kq, cache = build_kosdaq_cache()
    df_kq = build_kosdaq_history(kq, cache)
    compare_with_kospi(df_kq)
    print("\n※ 여기까지가 D 범위. 코스닥 '종목' 적용(전 종목 F_korean·비용 재설계)은")
    print("   영역 3(universe 확장)에서 — universe 확정 후 regime 재시험은 별도 모듈로.")


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
