#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""진우퀀트 — grade-cut 백테스트: 같은 v3.7.2 점수에서 '몇 등급까지 살지'만 비교.
S+/S/A(현행) vs S+/S(공격형) vs S+only. 오늘 데이터로 4년 PIT 재계산.
(05-29 robustness의 grade_cut 검증을 현재 하네스·오늘 시점으로 재확인하는 용도)
실행=진우 FDR환경: python backtest_gradecut.py   /   --selftest(synthetic)
"""
import argparse
import numpy as np, pandas as pd

COST = 0.00235
CUTS = [('S+/S/A(현행)', {'S+', 'S', 'A'}), ('S+/S(공격)', {'S+', 'S'}), ('S+only', {'S+'})]


def _load_user():
    from backtest_v37_2 import fetch_long_panel, compute_scores_at, metrics as _m, information_ratio as _ir
    try:
        from score_v37_2 import apply_weight_caps
    except Exception:
        apply_weight_caps = None
    return fetch_long_panel, compute_scores_at, _m, _ir, apply_weight_caps


def run(panel, compute_scores_at, caps_fn=None, sectors=None, cost=COST):
    k = panel['_KOSPI']; end = k.index[-1]; start = end - pd.DateOffset(years=4)
    bp = k[(k.index >= start) & (k.index <= end)]
    rebal = sorted({k.index[k.index.get_indexer([d], method='bfill')[0]]
                    for d in bp.resample('MS').first().dropna().index if d <= end})
    if rebal[-1] < end: rebal.append(end)
    res = {nm: [] for nm, _ in CUTS}; res['bench'] = []
    pw = {nm: {} for nm, _ in CUTS}; turn = {nm: 0.0 for nm, _ in CUTS}
    npick = {nm: [] for nm, _ in CUTS}
    for i in range(len(rebal)-1):
        d0, d1 = rebal[i], rebal[i+1]
        snap = compute_scores_at(panel, d0)
        if snap is None or len(snap) == 0: continue
        for nm, targets in CUTS:
            picks = snap[snap['등급_v37_2'].isin(targets)]['종목'].tolist()
            npick[nm].append(len(picks))
            w = (caps_fn(picks, sectors) if (caps_fn and sectors) else
                 {p: 1/len(picks) for p in picks}) if picks else {}
            r = 0.0
            for n, wi in w.items():
                s = panel.get(n)
                if s is None: continue
                sw = s[(s.index > d0) & (s.index <= d1)].dropna()
                if len(sw) >= 2: r += wi*float(sw.iloc[-1]/sw.iloc[0]-1)
            alln = set(w) | set(pw[nm])
            to = sum(abs(w.get(x, 0)-pw[nm].get(x, 0)) for x in alln)/2
            turn[nm] += to; r -= to*cost; pw[nm] = dict(w); res[nm].append(r)
        kw = k[(k.index > d0) & (k.index <= d1)].dropna()
        res['bench'].append(float(kw.iloc[-1]/kw.iloc[0]-1) if len(kw) >= 2 else 0.0)
    return res, turn, npick


def main():
    fetch_long_panel, compute_scores_at, _m, _ir, caps_fn = _load_user()
    panel = fetch_long_panel(years=4)
    print(f"  [1] 가격 수집 완료: {len([n for n in panel if not n.startswith('_')])}종목")
    sectors = None
    try:
        from score_v37 import JINWOO_v37; sectors = {n: i['산업'] for n, i in JINWOO_v37.items()}
    except Exception: pass
    res, turn, npick = run(panel, compute_scores_at, caps_fn, sectors)
    print("grade-cut 비교 (같은 점수, 매수 등급만 다름):")
    for nm, _ in CUTS:
        m = _m(res[nm]); ir = _ir(res[nm], res['bench'])
        avg_n = round(float(np.mean(npick[nm])), 1) if npick[nm] else 0
        print(f"  {nm:12s} {m}  IR={ir}  turnover={round(turn[nm],3)}  평균종목수={avg_n}")
    print("\n읽는 법: 공격형이 연환산↑이면 수익 레버 확정. 단 MDD·평균종목수(집중)도 같이 볼 것.")


def metrics_local(rets, ppy=12):
    a = np.array(rets)
    if len(a) == 0: return {}
    cum = float(np.prod(1+a)-1); ann = (1+cum)**(ppy/len(a))-1; vol = float(a.std()*np.sqrt(ppy))
    cc = np.cumprod(1+a); pk = np.maximum.accumulate(cc)
    return {'연환산%': round(ann*100, 2), 'Sharpe': round(ann/vol, 2) if vol > 0 else None,
            'MDD%': round(float(((cc-pk)/pk).min())*100, 2)}


def _selftest():
    ok = 0
    idx = pd.bdate_range('2021-06-01', periods=300); rng = np.random.default_rng(11)
    panel = {'_KOSPI': pd.Series(100+np.cumsum(rng.normal(0.02, 0.8, 300)), index=idx)}
    for n in ['AAA', 'BBB', 'CCC']:
        panel[n] = pd.Series(100+np.cumsum(rng.normal(0.03, 1.0, 300)), index=idx)
    def stub(panel, dt):
        return pd.DataFrame({'종목': ['AAA', 'BBB', 'CCC'], '등급_v37_2': ['S+', 'S', 'A']})
    res, turn, npick = run(panel, stub)
    assert len(res['S+/S/A(현행)']) >= 1; ok += 1
    assert np.mean(npick['S+/S/A(현행)']) == 3 and np.mean(npick['S+/S(공격)']) == 2 and np.mean(npick['S+only']) == 1; ok += 1
    for nm, _ in CUTS:
        assert metrics_local(res[nm]); ok += 1
    print(f"[OK] grade-cut self-test 통과 ({ok} checks) — 컷별 종목수 3/2/1 확인")


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--selftest', action='store_true')
    a, _ = ap.parse_known_args()
    try:
        _selftest() if a.selftest else main()
    except Exception:
        import traceback
        print("\n===== [에러] 아래 내용을 그대로 복사해 붙여주세요 =====")
        traceback.print_exc()
