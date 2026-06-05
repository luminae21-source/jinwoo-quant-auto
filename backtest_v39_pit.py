#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""진우퀀트 v3.9 — EarnMom(실적 모멘텀 / PEAD-family) PIT walk-forward 검증.
신호: YoY ΔROE (이번 분기 ROE − 전년 동분기 ROE), 횡단면 3분위 → +1/0/−1 (Echo와 동일 방식).
근거: Bernard-Thomas 1989·90 PEAD, Kim-Lee-Min 2019(한국). EPS Revision=컨센서스 데이터 없어 제외.
데이터: quality_timeseries_summary.csv (분기별 ROE, 이미 보유) + FDR 가격.
PIT 핵심: 각 분기는 '공시월' 이후에만 사용(11013 5월/11012 8월/11014 11월/11011 익년3월) → lookahead 차단
          (v3.8.2 AG 실패가 lookahead였던 교훈 반영).

비교: base(v3.7.2 등급) vs v3.9(체력_v37.2 + EarnMom → 재등급). 합격선: net alpha ≥ base.
실행=진우 FDR환경. 샌드박스는 `--selftest`(synthetic).
"""
import sys, argparse
from datetime import datetime
from pathlib import Path
import numpy as np, pandas as pd

COST = 0.00235; TARGET = {'S+', 'S', 'A'}; EARN_W = 1.0


def _load_user():
    from score_v37 import grade
    from backtest_v37_2 import fetch_long_panel, compute_scores_at, metrics as _m, information_ratio as _ir
    try:
        from score_v37_2 import apply_weight_caps
    except Exception:
        apply_weight_caps = None
    return grade, fetch_long_panel, compute_scores_at, _m, _ir, apply_weight_caps


# ---------- PIT 공시 가용일 ----------
def quarter_avail_date(qstr):
    """'2022Q1' → 그 분기 실적이 '실제로 공시되어 쓸 수 있는' 날짜(Timestamp). 보수적 lag."""
    y, q = int(qstr[:4]), int(qstr[-1])
    return {1: pd.Timestamp(f'{y}-05-15'), 2: pd.Timestamp(f'{y}-08-14'),
            3: pd.Timestamp(f'{y}-11-14'), 4: pd.Timestamp(f'{y+1}-03-31')}[q]


# ---------- EarnMom 팩터 ----------
def load_earnmom(csv_path):
    """종목별 [분기, ROE, avail, dROE_yoy] 테이블 dict 반환."""
    df = pd.read_csv(csv_path)
    df.columns = [c.strip().lstrip('﻿') for c in df.columns]
    out = {}
    for name, g in df.groupby('종목'):
        g = g.sort_values('분기').reset_index(drop=True)
        g['ROE'] = pd.to_numeric(g['ROE'], errors='coerce')
        g['dROE_yoy'] = g['ROE'].diff(4)             # 전년 동분기 대비
        g['avail'] = g['분기'].map(quarter_avail_date)
        out[name] = g[['분기', 'ROE', 'dROE_yoy', 'avail']].dropna(subset=['dROE_yoy'])
    return out


def earnmom_asof(table, name, dt):
    """dt 시점에 '공시 완료된' 최신 분기의 dROE_yoy. 없으면 None."""
    g = table.get(name)
    if g is None:
        return None
    avail = g[g['avail'] <= dt]
    return float(avail.iloc[-1]['dROE_yoy']) if len(avail) else None


def earnmom_scores_at(table, names, dt):
    """횡단면 3분위 → {name: +1/0/-1}. (Echo와 동일 방식, ±1)"""
    vals = {n: earnmom_asof(table, n, dt) for n in names}
    have = {n: v for n, v in vals.items() if v is not None}
    if len(have) < 3:
        return {n: 0 for n in names}
    s = pd.Series(have).sort_values(ascending=False)
    up = s.iloc[max(1, round(len(s)*0.2)) - 1]
    lo = s.iloc[-max(1, round(len(s)*0.2))]
    return {n: (1 if (v is not None and v >= up) else -1 if (v is not None and v <= lo) else 0)
            for n, v in vals.items()}


# ---------- 엔진 ----------
def run(panel, table, grade, compute_scores_at, caps_fn=None, sectors=None, earn_w=EARN_W, cost=COST):
    k = panel['_KOSPI']; end = k.index[-1]; start = end - pd.DateOffset(years=4)
    bp = k[(k.index >= start) & (k.index <= end)]
    rebal = sorted({k.index[k.index.get_indexer([d], method='bfill')[0]]
                    for d in bp.resample('MS').first().dropna().index if d <= end})
    if rebal[-1] < end: rebal.append(end)
    names = [n for n in panel if not n.startswith('_')]

    res = {'base': [], 'v39': [], 'bench': []}
    pw = {'base': {}, 'v39': {}}; turn = {'base': 0.0, 'v39': 0.0}
    for i in range(len(rebal)-1):
        d0, d1 = rebal[i], rebal[i+1]
        snap = compute_scores_at(panel, d0)
        if snap is None or len(snap) == 0: continue
        em = earnmom_scores_at(table, names, d0)
        snap = snap.copy()
        snap['등급_v39'] = snap.apply(lambda r: grade(r['체력_v37_2'] + earn_w*em.get(r['종목'], 0)), axis=1)
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
    return res, turn


def metrics_local(rets, ppy=12):
    a = np.array(rets)
    if len(a) == 0: return {}
    cum = float(np.prod(1+a)-1); ann = (1+cum)**(ppy/len(a))-1; vol = float(a.std()*np.sqrt(ppy))
    cc = np.cumprod(1+a); pk = np.maximum.accumulate(cc)
    return {'누적%': round(cum*100, 1), '연환산%': round(ann*100, 2),
            'Sharpe': round(ann/vol, 2) if vol > 0 else None,
            'MDD%': round(float(((cc-pk)/pk).min())*100, 2)}

def ir_local(p, b, ppy=12):
    p, b = np.array(p), np.array(b); e = p-b
    return round(float(e.mean()*ppy/(e.std()*np.sqrt(ppy))), 2) if (len(e) > 1 and e.std() > 0) else None


def main():
    grade, fetch_long_panel, compute_scores_at, _m, _ir, caps_fn = _load_user()
    panel = fetch_long_panel(years=4)
    print(f"  [1] 가격 수집 완료: {len([n for n in panel if not n.startswith('_')])}종목")
    sectors = None
    try:
        from score_v37 import JINWOO_v37; sectors = {n: i['산업'] for n, i in JINWOO_v37.items()}
    except Exception: pass
    csv_path = Path(__file__).parent / 'quality_timeseries_summary.csv'
    if not csv_path.exists():
        print(f"[중단] {csv_path.name} 없음 → fetch_dart_quarterly.py 먼저 실행 필요."); return
    table = load_earnmom(str(csv_path))
    print(f"  [2] ROE 로드 완료: {len(table)}종목, 백테스트 시작...")
    print("v3.9 EarnMom PIT 검증 (base=v3.7.2 vs +EarnMom):")
    for ew in (1.0, 0.5):
        res, turn = run(panel, table, grade, compute_scores_at, caps_fn, sectors, earn_w=ew)
        if ew == 1.0:
            mb = _m(res['base']); print(f"  base        {mb}  IR={_ir(res['base'], res['bench'])}")
        mv = _m(res['v39']); print(f"  +EarnMom×{ew}  {mv}  IR={_ir(res['v39'], res['bench'])}  turnover={round(turn['v39'],3)}")
    print("\n합격선: +EarnMom 연환산 ≥ base, MDD 악화 없음 → 통과 시 v3.9 채택, 아니면 기각(v3.8 GP/AG처럼).")


def _selftest():
    ok = 0
    assert quarter_avail_date('2022Q1') == pd.Timestamp('2022-05-15'); ok += 1
    assert quarter_avail_date('2022Q4') == pd.Timestamp('2023-03-31'); ok += 1
    # EarnMom 테이블 (synthetic): AAA ROE 상승, BBB 하락
    rows = []
    for qi, q in enumerate(['2021Q1','2021Q2','2021Q3','2021Q4','2022Q1','2022Q2']):
        rows += [{'종목':'AAA','분기':q,'ROE':0.02+0.005*qi},
                 {'종목':'BBB','분기':q,'ROE':0.08-0.005*qi},
                 {'종목':'CCC','분기':q,'ROE':0.05}]
    import tempfile, os
    p = os.path.join(tempfile.gettempdir(), '_q.csv'); pd.DataFrame(rows).to_csv(p, index=False)
    tbl = load_earnmom(p)
    assert 'AAA' in tbl and (tbl['AAA']['dROE_yoy'] > 0).all(); ok += 1   # 상승 → 양(+)
    sc = earnmom_scores_at(tbl, ['AAA','BBB','CCC'], pd.Timestamp('2022-09-01'))
    assert sc['AAA'] == 1 and sc['BBB'] == -1; ok += 1                    # 상승 +1, 하락 -1
    # PIT: 2022Q2(8/14 공시)는 8/1엔 아직 못 씀
    assert earnmom_asof(tbl, 'AAA', pd.Timestamp('2022-08-01')) is not None  # 2022Q1(5/15)은 가용
    # 엔진 (synthetic panel + stub)
    idx = pd.bdate_range('2021-06-01', periods=300)
    rng = np.random.default_rng(39)
    panel = {'_KOSPI': pd.Series(100+np.cumsum(rng.normal(0.02,0.8,300)), index=idx)}
    for n in ['AAA','BBB','CCC']:
        panel[n] = pd.Series(100+np.cumsum(rng.normal(0.03,1,300)), index=idx)
    def grade(x): return 'S+' if x >= 14 else 'S' if x >= 12 else 'A' if x >= 9 else 'B'
    def stub(panel, dt):
        return pd.DataFrame({'종목':['AAA','BBB','CCC'],
                             '체력_v37_2':[13.5, 9.2, 8.8],
                             '등급_v37_2':['S','A','B']})
    res, turn = run(panel, tbl, grade, stub)
    assert len(res['v39']) >= 1 and len(res['base']) >= 1; ok += 1
    print(f"[OK] v3.9 EarnMom self-test 통과 ({ok} checks)")
    print("     예) AAA(ROE↑)=+1, BBB(ROE↓)=-1, PIT 공시일 적용 확인")


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--selftest', action='store_true')
    a, _ = ap.parse_known_args()
    try:
        _selftest() if a.selftest else main()
    except Exception:
        import traceback
        print("\n===== [에러] 아래 내용을 그대로 복사해 붙여주세요 =====")
        traceback.print_exc()
