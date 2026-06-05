#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""진우퀀트 v3.9 PEAD — Stage 2.5: 공식 엔진(backtest_v39_pit.py 컨벤션) 이식 판정.

목적: backtest_v39_pead.py(자체 엔진, base 82.23%)의 PASS를 **공식 base(≈73.18%) 위에서 재확인**.
엔진: backtest_v39_pit.py(EarnMom, 06-03 기각)와 100% 동일 — 월초 리밸·비용 0.235%×턴오버·
      caps·metrics/IR은 backtest_v37_2 import. 차이는 신호뿐: EarnMom(YoY ΔROE) → PEAD SUE.
신호: score_v39_pead.compute_pead_scores (계절RW SUE, σ8Q ddof=1, 공시일 PIT, 60거래일 게이트).

사전 합격선 (결정메모 §2, 변경 금지): Δ연환산 ≥ +1.0%p AND Sharpe·IR 비열위(−0.01 허용).
×0.5 / ×1.0 둘만. 미달 → 2차 기각, PEAD 노선 종료.

실행=진우 PC (Desktop\\진우퀀트): python backtest_v39_pit_pead.py
샌드박스/사전 검증: python backtest_v39_pit_pead.py --selftest
선행 조건: eps_sue_cache.json (fetch_dart_eps.py --start-year 2018 산출물)
"""
import sys, argparse, json
from datetime import datetime
from pathlib import Path
import numpy as np, pandas as pd

BASE = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE))

COST = 0.00235; TARGET = {'S+', 'S', 'A'}
PASS_DCAGR = 1.0; TOL = 0.01


def _load_user():
    from score_v37 import grade
    from backtest_v37_2 import fetch_long_panel, compute_scores_at, metrics as _m, information_ratio as _ir
    try:
        from score_v37_2 import apply_weight_caps
    except Exception:
        apply_weight_caps = None
    return grade, fetch_long_panel, compute_scores_at, _m, _ir, apply_weight_caps


# ---------- PEAD 신호 (score_v39_pead 재사용 — 정의 단일화) ----------
def pead_scores_at(cache, names, dt, tindex):
    from score_v39_pead import compute_pead_scores
    sc, sue_vals, _ = compute_pead_scores(cache, names, pd.Timestamp(dt).to_pydatetime(), tindex)
    return sc, len(sue_vals)


# ---------- 엔진 (backtest_v39_pit.py run()과 동일 구조) ----------
def run(panel, cache, grade, compute_scores_at, caps_fn=None, sectors=None, pead_w=1.0, cost=COST):
    k = panel['_KOSPI']; end = k.index[-1]; start = end - pd.DateOffset(years=4)
    bp = k[(k.index >= start) & (k.index <= end)]
    rebal = sorted({k.index[k.index.get_indexer([d], method='bfill')[0]]
                    for d in bp.resample('MS').first().dropna().index if d <= end})
    if rebal[-1] < end: rebal.append(end)
    names = [n for n in panel if not n.startswith('_')]

    res = {'base': [], 'v39': [], 'bench': []}
    pw = {'base': {}, 'v39': {}}; turn = {'base': 0.0, 'v39': 0.0}
    active = 0
    for i in range(len(rebal)-1):
        d0, d1 = rebal[i], rebal[i+1]
        snap = compute_scores_at(panel, d0)
        if snap is None or len(snap) == 0: continue
        em, n_sue = pead_scores_at(cache, names, d0, k.index)
        if n_sue: active += 1
        snap = snap.copy()
        snap['등급_v39'] = snap.apply(lambda r: grade(r['체력_v37_2'] + pead_w*em.get(r['종목'], 0)), axis=1)
        for var, col in [('base', '등급_v37_2'), ('v39', '등급_v39')]:
            picks = snap[snap[col].isin(TARGET)]['종목'].tolist()
            w = (caps_fn(picks, sectors) if (caps_fn and sectors) else
                 {p: 1/len(picks) for p in picks}) if picks else {}
            r = 0.0
            for n, wi in w.items():
                s = panel.get(n)
                if s is None: continue
                sw = s[(s.index > d0) & (s.index <= d1)].dropna()
                if len(sw) >= 2: r += wi*float(sw.iloc[-1]/sw.iloc[0]-1)
            alln = set(w) | set(pw[var])
            to = sum(abs(w.get(x, 0)-pw[var].get(x, 0)) for x in alln)/2
            turn[var] += to; r -= to*cost; pw[var] = dict(w)
            res[var].append(r)
        kw = k[(k.index > d0) & (k.index <= d1)].dropna()
        res['bench'].append(float(kw.iloc[-1]/kw.iloc[0]-1) if len(kw) >= 2 else 0.0)
    return res, turn, active


def load_sue_cache():
    p = BASE / 'eps_sue_cache.json'
    if not p.exists():
        print('[중단] eps_sue_cache.json 없음 → python fetch_dart_eps.py --start-year 2018 먼저.'); sys.exit(1)
    d = json.loads(p.read_text(encoding='utf-8'))
    return {k: v for k, v in d.items() if not k.startswith('_')}


def main():
    grade, fetch_long_panel, compute_scores_at, _m, _ir, caps_fn = _load_user()
    cache = load_sue_cache()
    panel = fetch_long_panel(years=4)
    print(f"  [1] 가격 수집 완료: {len([n for n in panel if not n.startswith('_')])}종목")
    sectors = None
    try:
        from score_v37 import JINWOO_v37; sectors = {n: i['산업'] for n, i in JINWOO_v37.items()}
    except Exception: pass
    print(f"  [2] SUE 캐시 로드: {len(cache)}종목, 백테스트 시작...")
    print("\nv3.9 PEAD PIT 검증 — 공식 엔진 (base=v3.7.2, 비용 0.235%·caps·월초 리밸):")

    out = {'run_at': datetime.now().isoformat(), 'engine': 'backtest_v39_pit convention',
           'pass_rule': f'dCAGR>=+{PASS_DCAGR}%p AND Sharpe/IR>=base-{TOL}', 'results': {}}
    base_m = base_ir = None
    verdicts = {}
    for pw_ in (1.0, 0.5):
        res, turn, active = run(panel, cache, grade, compute_scores_at, caps_fn, sectors, pead_w=pw_)
        if base_m is None:
            base_m = _m(res['base']); base_ir = _ir(res['base'], res['bench'])
            print(f"  base        {base_m}  IR={base_ir}")
            out['results']['base'] = {**base_m, 'IR': base_ir}
            print(f"  (PEAD 활성: {active}/{len(res['v39'])}개월)")
        mv = _m(res['v39']); irv = _ir(res['v39'], res['bench'])
        print(f"  +PEAD×{pw_}   {mv}  IR={irv}  turnover={round(turn['v39'],3)}")
        d = (mv.get('연환산', 0) or 0) - (base_m.get('연환산', 0) or 0)
        ok = (d >= PASS_DCAGR
              and (mv.get('Sharpe') or 0) >= (base_m.get('Sharpe') or 0) - TOL
              and (irv or 0) >= (base_ir or 0) - TOL)
        verdicts[pw_] = (ok, round(d, 2))
        out['results'][f'pead_{pw_}'] = {**mv, 'IR': irv, 'turnover': round(turn['v39'], 3),
                                         'pass': ok, 'delta_cagr_%p': round(d, 2)}

    print("\n판정 (사전 합격선: Δ연환산 ≥ +1.0%p AND Sharpe·IR 비열위):")
    for pw_, (ok, d) in verdicts.items():
        print(f"  ×{pw_}: Δ연환산 {d:+.2f}%p → {'✅ PASS' if ok else '❌ FAIL'}")
    if any(ok for ok, _ in verdicts.values()):
        best = max((pw_ for pw_, (ok, _) in verdicts.items() if ok), key=lambda p: verdicts[p][1])
        print(f"\n→ 공식 엔진에서도 합격 (최우수 ×{best}): Stage 3 production 통합 검토 진행.")
    else:
        print("\n→ 공식 엔진 미달: 자체 엔진 PASS는 엔진 차이 산물로 판정. v3.9 PEAD 2차 기각, 노선 종료.")

    fn = BASE / f'backtest_v39_pit_pead_{datetime.now():%Y%m%d_%H%M}.json'
    fn.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    print(f"\n💾 저장: {fn.name}")


# ---------- selftest (synthetic — FDR·production 모듈 불필요) ----------
def _selftest():
    from score_v39_pead import _mk_quarters
    ok = 0
    # PEAD 신호 wiring: 양/음 서프라이즈 → +1/−1
    ni_up = {'2021Q1': 100, '2021Q2': 100, '2021Q3': 100, '2021Q4': 100,
             '2022Q1': 110, '2022Q2': 90, '2022Q3': 120, '2022Q4': 80,
             '2023Q1': 130, '2023Q2': 110, '2023Q3': 100, '2023Q4': 130,
             '2024Q1': 160}
    ni_dn = {q: -v for q, v in ni_up.items()}
    ni_md = {q: v*0 + 100 + (7*i % 13) for i, (q, v) in enumerate(ni_up.items())}  # 잡음 중간
    cache = {'UP': {'quarters': _mk_quarters(ni_up, {'2024Q1': '2024-05-10'})},
             'DN': {'quarters': _mk_quarters(ni_dn, {'2024Q1': '2024-05-10'})},
             'MD': {'quarters': _mk_quarters(ni_md, {'2024Q1': '2024-05-10'})}}
    idx = pd.bdate_range('2023-01-02', '2024-12-31')
    sc, n_sue = pead_scores_at(cache, ['UP', 'DN', 'MD'], pd.Timestamp('2024-06-01'), idx)
    assert n_sue >= 2 and sc['UP'] == 1 and sc['DN'] == -1, sc; ok += 1
    # 엔진: synthetic panel + stub (backtest_v39_pit._selftest와 동일 패턴)
    idx2 = pd.bdate_range('2021-06-01', periods=300)
    rng = np.random.default_rng(39)
    panel = {'_KOSPI': pd.Series(100+np.cumsum(rng.normal(0.02, 0.8, 300)), index=idx2)}
    for n in ['UP', 'DN', 'MD']:
        panel[n] = pd.Series(100+np.cumsum(rng.normal(0.03, 1, 300)), index=idx2)
    def grade(x): return 'S+' if x >= 14 else 'S' if x >= 12 else 'A' if x >= 9 else 'B'
    def stub(panel, dt):
        return pd.DataFrame({'종목': ['UP', 'DN', 'MD'],
                             '체력_v37_2': [13.5, 9.2, 8.8],
                             '등급_v37_2': ['S', 'A', 'B']})
    res, turn, active = run(panel, cache, grade, stub)
    assert len(res['base']) >= 1 and len(res['v39']) == len(res['base']) == len(res['bench']); ok += 1
    # 비용 차감 방향: 첫 리밸 turnover>0 → v39 첫 수익 ≤ 무비용
    assert turn['v39'] > 0; ok += 1
    print(f"[OK] backtest_v39_pit_pead selftest 통과 ({ok} checks)")
    print("     실제 판정은 진우님 PC에서: python backtest_v39_pit_pead.py")


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--selftest', action='store_true')
    a, _ = ap.parse_known_args()
    try:
        _selftest() if a.selftest else main()
    except Exception:
        import traceback
        print("\n===== [에러] 아래 내용을 그대로 복사해 붙여주세요 =====")
        traceback.print_exc()
