#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""진우퀀트 영역 2 — 매매룰 백테스트 (v3.7.2 위 실행레이어) + regime(5요소) 통합.
backtest_v37_2 컨벤션(월리밸·동일가중+15/35cap·metrics ppy=12·KOSPI벤치).
시나리오: base / +exit(Chandelier) / +sizing(VKOSPI) / +full / +hedged / +regime(5요소).
실행=진우 FDR환경(+옵션 pykrx). 샌드박스는 `--selftest`(synthetic)만.
짝 문서: 진우퀀트_v37_2_매매룰.md, 진우퀀트_v40_regime_detector_설계.md
"""
import sys, argparse
from datetime import datetime, timedelta
import numpy as np, pandas as pd

COST = 0.00235; HEDGE_W = 0.07; TARGET_GRADES = {'S+', 'S', 'A'}; INVERSE_CODE = '114800'
try:
    import regime_detector_v40 as rg
except Exception:
    rg = None


def _load_user_modules():
    from score_v37 import grade  # noqa
    from backtest_v37_2 import fetch_long_panel, compute_scores_at, metrics as _m, information_ratio as _ir
    try:
        from score_v37_2 import apply_weight_caps
    except Exception:
        apply_weight_caps = None
    return fetch_long_panel, compute_scores_at, _m, _ir, apply_weight_caps


# ---------------- 순수 룰 함수 (self-test 대상) ----------------
def atr_wilder(high, low, close, n=14):
    pc = close.shift(1)
    tr = pd.concat([(high-low).abs(), (high-pc).abs(), (low-pc).abs()], axis=1).max(axis=1)
    return tr.ewm(alpha=1.0/n, adjust=False).mean()

def rolling_peak_close(close, lookback=22):
    return close.rolling(lookback, min_periods=1).max()

def vkospi_invest_frac(v):              # 매매룰 §4.2: <25→1.0, <32→0.85, ≥32→0.60
    return 1.0 if v < 25 else (0.85 if v < 32 else 0.60)

def market_regime(kospi, ma200, vkospi):
    if kospi > ma200*1.02 and vkospi < 22: return "RISK_ON"
    if kospi < ma200*0.98 and vkospi > 28: return "RISK_OFF"
    return "NEUTRAL"

def realized_vol(c, window=20, td=252):
    return np.log(pd.Series(c).astype(float)).diff().rolling(window).std()*np.sqrt(td)*100.0

def pick_return_with_exit(series, peak, atr, d0, d1, use_exit, mult=3.0):
    win = series[(series.index > d0) & (series.index <= d1)].dropna()
    if len(win) < 1: return 0.0, False
    entry = float(win.iloc[0])
    if entry == 0: return 0.0, False
    if not use_exit: return float(win.iloc[-1]/entry - 1), False
    for dt, px in win.items():
        st = peak.get(dt, np.nan) - mult*atr.get(dt, np.nan)
        if np.isfinite(st) and px < st: return float(px/entry - 1), True
    return float(win.iloc[-1]/entry - 1), False

def equal_weights(picks, caps_fn=None, sectors=None):
    if not picks: return {}
    if caps_fn and sectors is not None: return caps_fn(picks, sectors)
    w = 1.0/len(picks); return {p: w for p in picks}

def inverse_return(panel, k, d0, d1):    # 실제 KODEX인버스 있으면 사용, 없으면 -KOSPI
    inv = panel.get('_INVERSE')
    if inv is not None:
        iw = inv[(inv.index > d0) & (inv.index <= d1)].dropna()
        if len(iw) >= 2: return float(iw.iloc[-1]/iw.iloc[0] - 1)
    kw = k[(k.index > d0) & (k.index <= d1)].dropna()
    return (-float(kw.iloc[-1]/kw.iloc[0]-1)) if len(kw) >= 2 else 0.0


# ---------------- 엔진 ----------------
def run_rules_backtest(panel, vkospi, scenario, score_fn, grade_col='등급_v37_2',
                       caps_fn=None, sectors=None, flows=None, hl=None, cost=COST):
    use_exit = scenario in ('+exit', '+full', '+hedged', '+regime')
    use_size = scenario in ('+sizing', '+full', '+hedged')
    use_hedge = scenario == '+hedged'; use_regime = scenario == '+regime'
    k = panel['_KOSPI']; end = k.index[-1]; start = end - pd.DateOffset(years=4)
    bp = k[(k.index >= start) & (k.index <= end)]
    rebal = bp.resample('MS').first().dropna().index
    rebal = sorted({k.index[k.index.get_indexer([d], method='bfill')[0]] for d in rebal if d <= end})
    if rebal[-1] < end: rebal.append(end)
    ma200 = k.rolling(200, min_periods=1).mean()
    peak = {n: rolling_peak_close(s) for n, s in panel.items() if not n.startswith('_') and s is not None}
    atr = {}
    for _n, _s in panel.items():
        if _n.startswith('_') or _s is None:
            continue
        atr[_n] = atr_wilder(hl[_n][0], hl[_n][1], _s) if (hl and _n in hl) else atr_wilder(_s, _s, _s)
    port, bench, prev_w = [], [], {}; turn = 0.0; exits = 0; prev = 'NEUTRAL'
    for i in range(len(rebal)-1):
        d0, d1 = rebal[i], rebal[i+1]
        snap = score_fn(panel, d0)
        if snap is None or len(snap) == 0: continue
        picks = snap[snap[grade_col].isin(TARGET_GRADES)]['종목'].tolist()
        w = equal_weights(picks, caps_fn, sectors)
        vk = float(vkospi.reindex(k.index, method='ffill').get(d0, 20.0)) if vkospi is not None else 20.0
        hedge = False
        if use_regime and rg is not None:
            te = None
            if len(port) >= 3:
                te = (np.prod([1+x for x in port[-3:]])-1) - (np.prod([1+x for x in bench[-3:]])-1)
            rr = rg.detect(k, vkospi=vkospi, net_buy_cum=(flows[flows.index <= d0] if flows is not None else None),
                           picks=list(w), sector_map=sectors or {}, trailing_excess=te,
                           dt=d0, prev_state=prev, vkospi_is_realized=True)
            invest, hedge, prev = rr['invest_frac'], rr['hedge_on'], rr['state']
        else:
            invest = vkospi_invest_frac(vk) if use_size else 1.0
            if use_hedge:
                hedge = market_regime(float(k.get(d0, np.nan)), float(ma200.get(d0, np.nan)), vk) == 'RISK_OFF'
        r = 0.0
        for n, wi in w.items():
            s = panel.get(n)
            if s is None: continue
            pr, ex = pick_return_with_exit(s, peak[n], atr[n], d0, d1, use_exit); exits += int(ex); r += wi*pr
        r *= invest
        if hedge: r += HEDGE_W*inverse_return(panel, k, d0, d1)
        alln = set(w) | set(prev_w)
        to = sum(abs(w.get(x, 0)*invest - prev_w.get(x, 0)) for x in alln)/2
        turn += to; r -= to*cost; prev_w = {x: w.get(x, 0)*invest for x in w}
        kw = k[(k.index > d0) & (k.index <= d1)].dropna()
        bench.append(float(kw.iloc[-1]/kw.iloc[0]-1) if len(kw) >= 2 else 0.0); port.append(r)
    nmo = max(len(port), 1)
    return {'rets': port, 'bench': bench, 'turnover_annual': round(turn/(nmo/12), 3), 'exit_events': exits}


def metrics_local(rets, ppy=12):
    a = np.array(rets)
    if len(a) == 0: return {}
    cum = float(np.prod(1+a)-1); ann = (1+cum)**(ppy/len(a))-1; vol = float(a.std()*np.sqrt(ppy))
    cc = np.cumprod(1+a); pk = np.maximum.accumulate(cc)
    return {'누적%': round(cum*100, 2), '연환산%': round(ann*100, 2),
            'Sharpe': round(ann/vol, 2) if vol > 0 else None,
            'MDD%': round(float(((cc-pk)/pk).min())*100, 2), '기간': len(a)}

def ir_local(p, b, ppy=12):
    p, b = np.array(p), np.array(b); e = p-b
    if len(e) < 2 or e.std() == 0: return None
    return round(float(e.mean()*ppy/(e.std()*np.sqrt(ppy))), 2)

def load_flows(years=4):                # 수급(pykrx); 실패 시 None → regime 4요소
    try:
        from pykrx import stock
        end = datetime.now(); start = end - timedelta(days=int(365*(years+1.2)))
        df = stock.get_market_trading_value_by_date(start.strftime('%Y%m%d'), end.strftime('%Y%m%d'), 'KOSPI')
        return (df.get('외국인합계', 0) + df.get('기관합계', 0)).rolling(20).sum()
    except Exception as e:
        print(f"  (수급 skip: {e})"); return None


def main():
    fetch_long_panel, compute_scores_at, _m, _ir, caps_fn = _load_user_modules()
    panel = fetch_long_panel(years=4)
    try:
        import FinanceDataReader as fdr
        panel['_INVERSE'] = fdr.DataReader(INVERSE_CODE, panel['_KOSPI'].index[0].strftime('%Y-%m-%d'))['Close']
    except Exception as e:
        print(f"  (인버스 skip: {e})")
    try:
        from score_v37 import JINWOO_v37; sectors = {n: i['산업'] for n, i in JINWOO_v37.items()}
    except Exception:
        sectors = None
    hl = {}
    try:
        import FinanceDataReader as fdr
        from score_v37 import JINWOO_v37
        _s0 = panel['_KOSPI'].index[0].strftime('%Y-%m-%d')
        for _n, _i in JINWOO_v37.items():
            try:
                _df = fdr.DataReader(_i['코드'], _s0); hl[_n] = (_df['High'], _df['Low'])
            except Exception:
                pass
    except Exception as e:
        print(f"  (High/Low skip: {e}) -> ATR 종가근사")
    vkospi = realized_vol(panel['_KOSPI']); flows = load_flows()
    print("시나리오별 (월리밸·동일가중, 비용 0.235%):")
    rows = {}
    for sc in ['base', '+exit', '+sizing', '+full', '+hedged', '+regime']:
        res = run_rules_backtest(panel, vkospi, sc, compute_scores_at, caps_fn=caps_fn, sectors=sectors, flows=flows, hl=hl)
        m = _m(res['rets']); ir = _ir(res['rets'], res['bench']); rows[sc] = m
        print(f"  {sc:9s} {m}  IR={ir}  turnover={res['turnover_annual']}  exits={res['exit_events']}")
    print(f"\n합격선: +full/+regime 연환산 ≥ base({rows['base'].get('연환산')}), MDD ≤ base, turnover ≤ base×1.5")


def _selftest():
    ok = 0
    assert vkospi_invest_frac(17) == 1.0 and vkospi_invest_frac(30) == 0.85 and vkospi_invest_frac(40) == 0.60; ok += 1
    assert market_regime(103, 100, 18) == 'RISK_ON' and market_regime(96, 100, 30) == 'RISK_OFF'; ok += 1
    rng = np.random.default_rng(372); idx = pd.bdate_range('2022-01-01', periods=400)
    close = pd.Series(100+np.cumsum(rng.normal(0.05, 1, 400)), index=idx)
    pk = rolling_peak_close(close); at = atr_wilder(close, close, close)
    assert (pk >= close).all() and (at.dropna() >= 0).all(); ok += 1
    down = pd.Series(np.linspace(100, 60, 400), index=idx) + rng.normal(0, 0.5, 400)
    pk2 = rolling_peak_close(down); at2 = atr_wilder(down, down, down)
    rno, _ = pick_return_with_exit(down, pk2, at2, idx[50], idx[120], False)
    rex, e1 = pick_return_with_exit(down, pk2, at2, idx[50], idx[120], True)
    assert e1 and rex >= rno - 1e-9; ok += 1
    panel = {'_KOSPI': pd.Series(100+np.cumsum(rng.normal(0.02, 0.8, 400)), index=idx)}
    for nm in ['AAA', 'BBB', 'CCC']:
        panel[nm] = pd.Series(100+np.cumsum(rng.normal(0.03, 1.0, 400)), index=idx)
    def stub(panel, dt): return pd.DataFrame({'종목': ['AAA', 'BBB', 'CCC'], '등급_v37_2': ['S+', 'A', 'B']})
    vk = realized_vol(panel['_KOSPI']); smap = {'AAA': '반도체', 'BBB': '금융', 'CCC': '식품'}
    scs = ['base', '+exit', '+sizing', '+full', '+hedged'] + (['+regime'] if rg is not None else [])
    for sc in scs:
        assert metrics_local(run_rules_backtest(panel, vk, sc, stub, sectors=smap)['rets'])['기간'] >= 1, f"{sc} 실패"
    ok += 1
    print(f"[OK] 매매룰+regime self-test 통과 ({ok} checks). 시나리오: {scs}")
    print("     base   :", metrics_local(run_rules_backtest(panel, vk, 'base', stub, sectors=smap)['rets']))
    if rg is not None:
        rr = run_rules_backtest(panel, vk, '+regime', stub, sectors=smap)
        print("     +regime:", metrics_local(rr['rets']), "turnover=", rr['turnover_annual'])


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--selftest', action='store_true')
    a, _ = ap.parse_known_args()
    _selftest() if a.selftest else main()
