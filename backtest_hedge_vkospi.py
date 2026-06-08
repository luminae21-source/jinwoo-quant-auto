#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""헤지 '진짜' 검증 — 실제 VKOSPI로 헤지만 단독 재검증 (별개 툴, 기존 모듈 무수정).
이전 매매룰 백테스트에선 실현변동성 proxy가 공포 임계(28)를 못 넘어 헤지가 0회 발동
→ 미검증 상태였음. 이 툴은 vkospi_daily.csv(진짜 VKOSPI, fetch_vkospi_krx.py 산출)로
base(v3.7.2) vs base+헤지만 비교한다. exit·sizing 등 다른 오버레이는 일절 없음.

헤지 룰(매매룰 §6): KOSPI<MA200×0.98 AND VKOSPI>28 → NAV 7%를 KODEX인버스(114800)로, 전환 시 해제.
선행: python fetch_vkospi_krx.py (vkospi_daily.csv 생성)
실행: python backtest_hedge_vkospi.py   /   --selftest
"""
import argparse
from pathlib import Path
import numpy as np, pandas as pd

COST = 0.00235; HEDGE_W = 0.07; TARGET = {'S+', 'S', 'A'}; INVERSE_CODE = '114800'


def _load_user():
    from backtest_v37_2 import fetch_long_panel, compute_scores_at, metrics as _m, information_ratio as _ir
    try:
        from score_v37_2 import apply_weight_caps
    except Exception:
        apply_weight_caps = None
    return fetch_long_panel, compute_scores_at, _m, _ir, apply_weight_caps


def risk_off(kospi, ma200, vk):
    return (kospi < ma200*0.98) and (vk > 28)


def inverse_return(inv, k, d0, d1):
    if inv is not None:
        iw = inv[(inv.index > d0) & (inv.index <= d1)].dropna()
        if len(iw) >= 2: return float(iw.iloc[-1]/iw.iloc[0]-1)
    kw = k[(k.index > d0) & (k.index <= d1)].dropna()
    return (-float(kw.iloc[-1]/kw.iloc[0]-1)) if len(kw) >= 2 else 0.0


def run(panel, vkospi, compute_scores_at, caps_fn=None, sectors=None, cost=COST):
    k = panel['_KOSPI']; inv = panel.get('_INVERSE')
    end = k.index[-1]; start = end - pd.DateOffset(years=4)
    bp = k[(k.index >= start) & (k.index <= end)]
    rebal = sorted({k.index[k.index.get_indexer([d], method='bfill')[0]]
                    for d in bp.resample('MS').first().dropna().index if d <= end})
    if rebal[-1] < end: rebal.append(end)
    ma200 = k.rolling(200, min_periods=1).mean()
    vk_ff = vkospi.reindex(k.index, method='ffill')
    res = {'base': [], 'hedged': [], 'bench': []}; pw = {'base': {}, 'hedged': {}}
    fired = []
    for i in range(len(rebal)-1):
        d0, d1 = rebal[i], rebal[i+1]
        snap = compute_scores_at(panel, d0)
        if snap is None or len(snap) == 0: continue
        picks = snap[snap['등급_v37_2'].isin(TARGET)]['종목'].tolist()
        w = (caps_fn(picks, sectors) if (caps_fn and sectors) else
             {p: 1/len(picks) for p in picks}) if picks else {}
        r = 0.0
        for n, wi in w.items():
            s = panel.get(n)
            if s is None: continue
            sw = s[(s.index > d0) & (s.index <= d1)].dropna()
            if len(sw) >= 2: r += wi*float(sw.iloc[-1]/sw.iloc[0]-1)
        vk = float(vk_ff.get(d0, np.nan))
        h_on = bool(np.isfinite(vk) and risk_off(float(k.get(d0, np.nan)), float(ma200.get(d0, np.nan)), vk))
        if h_on: fired.append(str(pd.Timestamp(d0).date()))
        for var in ('base', 'hedged'):
            rv = r + (HEDGE_W*inverse_return(inv, k, d0, d1) if (var == 'hedged' and h_on) else 0.0)
            alln = set(w) | set(pw[var])
            to = sum(abs(w.get(x, 0)-pw[var].get(x, 0)) for x in alln)/2
            if var == 'hedged' and h_on: to += HEDGE_W   # 헤지 진입/청산 비용 근사
            rv -= to*cost; pw[var] = dict(w); res[var].append(rv)
        kw = k[(k.index > d0) & (k.index <= d1)].dropna()
        res['bench'].append(float(kw.iloc[-1]/kw.iloc[0]-1) if len(kw) >= 2 else 0.0)
    return res, fired


def metrics_local(rets, ppy=12):
    a = np.array(rets)
    if len(a) == 0: return {}
    cum = float(np.prod(1+a)-1); ann = (1+cum)**(ppy/len(a))-1; vol = float(a.std()*np.sqrt(ppy))
    cc = np.cumprod(1+a); pk = np.maximum.accumulate(cc)
    return {'연환산%': round(ann*100, 2), 'Sharpe': round(ann/vol, 2) if vol > 0 else None,
            'MDD%': round(float(((cc-pk)/pk).min())*100, 2)}


def main():
    vk_path = Path(__file__).parent / 'vkospi_daily.csv'
    if not vk_path.exists():
        print("[중단] vkospi_daily.csv 없음 → 먼저: python fetch_vkospi_krx.py (또는 --manual)"); return
    vk = pd.read_csv(vk_path, parse_dates=['Date']).set_index('Date')['VKOSPI']
    print(f"  [1] 진짜 VKOSPI 로드: {len(vk)}일, 최근 {vk.iloc[-1]:.1f}, 28 초과일수 {(vk>28).sum()}")
    fetch_long_panel, compute_scores_at, _m, _ir, caps_fn = _load_user()
    panel = fetch_long_panel(years=4)
    try:
        import FinanceDataReader as fdr
        panel['_INVERSE'] = fdr.DataReader(INVERSE_CODE, panel['_KOSPI'].index[0].strftime('%Y-%m-%d'))['Close']
        print("  [2] KODEX 인버스 로드 OK")
    except Exception as e:
        print(f"  (인버스 skip: {e}) → -KOSPI 근사")
    sectors = None
    try:
        from score_v37 import JINWOO_v37; sectors = {n: i['산업'] for n, i in JINWOO_v37.items()}
    except Exception: pass
    res, fired = run(panel, vk, compute_scores_at, caps_fn, sectors)
    print("\n헤지 단독 검증 (진짜 VKOSPI, base=v3.7.2):")
    print(f"  base    {_m(res['base'])}  IR={_ir(res['base'], res['bench'])}")
    print(f"  +헤지   {_m(res['hedged'])}  IR={_ir(res['hedged'], res['bench'])}")
    print(f"  헤지 발동: {len(fired)}회/{len(res['base'])}개월 → {fired if fired else '(0회 — 이번에도 미발동이면 헤지는 기각 확정)'}")
    print("\n합격선: +헤지 연환산 ≥ base AND MDD 개선. 발동 0회면 임계(28)에 도달한 적 없음 = 검증 불가 아님, '필요 없었음'.")


def _selftest():
    ok = 0
    assert risk_off(95, 100, 30) and not risk_off(105, 100, 30) and not risk_off(95, 100, 20); ok += 1
    idx = pd.bdate_range('2021-06-01', periods=300); rng = np.random.default_rng(3)
    k = pd.Series(np.linspace(120, 90, 300) + rng.normal(0, 0.5, 300), index=idx)   # 하락장 → MA200 아래
    panel = {'_KOSPI': k}
    for n in ['AAA', 'BBB']:
        panel[n] = pd.Series(100+np.cumsum(rng.normal(0, 1, 300)), index=idx)
    vk = pd.Series(35.0, index=idx)                                                  # 공포 구간 강제
    def stub(panel, dt): return pd.DataFrame({'종목': ['AAA', 'BBB'], '등급_v37_2': ['S+', 'S']})
    res, fired = run(panel, vk, stub)
    assert len(fired) > 0, "공포+하락장인데 헤지 미발동이면 로직 오류"; ok += 1     # 발동 확인
    assert len(res['hedged']) == len(res['base']); ok += 1
    vk2 = pd.Series(15.0, index=idx)
    _, fired2 = run(panel, vk2, stub)
    assert len(fired2) == 0; ok += 1                                                 # 평온장 미발동
    print(f"[OK] hedge self-test 통과 ({ok} checks) — 발동/미발동 경로 모두 확인")


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--selftest', action='store_true')
    a, _ = ap.parse_known_args()
    try:
        _selftest() if a.selftest else main()
    except Exception:
        import traceback
        print("\n===== [에러] 아래 내용을 복사해 주세요 ====="); traceback.print_exc()
