#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""진우퀀트 — Value(B/M) PIT walk-forward 검증. (유일하게 미검증인 직교 후보)
신호: B/M = 자기자본총계(장부가) / 시가총액. 횡단면 3분위 → 싼(고B/M) +1 / 비싼 -1 (Echo·EarnMom과 동일 방식).
근거: Fama-French value 프리미엄 + 한국 value 9편(라이브러리). 기존 배터리(quality·momentum·low-risk)와 직교.
데이터: quality_timeseries_cache.json(분기 자기자본총계, 이미 보유) + FDR 가격 + StockListing(주식수).
  · B/M은 '장부가(stock값)'이라 TTM/누적 모호성 없음 → E/P보다 깨끗.
  · 시총 = 가격(분할조정, FDR) × 주식수(현재). 분할은 조정가가 흡수, 신주발행만 근사오차(대형주 미미).
PIT: 자기자본총계는 분기 공시월 이후에만 사용(11013 5월/11012 8월/11014 11월/11011 익년3월) → lookahead 차단.
비교: base(v3.7.2) vs +Value. 합격선: 연환산 ≥ base, MDD 악화 없음 (안 되면 기각, GP/AG/EarnMom처럼).
실행=진우 FDR환경. 샌드박스는 `--selftest`.
"""
import sys, argparse, json
from pathlib import Path
import numpy as np, pandas as pd

COST = 0.00235; TARGET = {'S+', 'S', 'A'}; VAL_W = 1.0


def _load_user():
    from score_v37 import grade, JINWOO_v37
    from backtest_v37_2 import fetch_long_panel, compute_scores_at, metrics as _m, information_ratio as _ir
    try:
        from score_v37_2 import apply_weight_caps
    except Exception:
        apply_weight_caps = None
    return grade, JINWOO_v37, fetch_long_panel, compute_scores_at, _m, _ir, apply_weight_caps


def quarter_avail_date(qstr):              # 공시 가용일 (보수적 lag)
    y, q = int(qstr[:4]), int(qstr[-1])
    return {1: pd.Timestamp(f'{y}-05-15'), 2: pd.Timestamp(f'{y}-08-14'),
            3: pd.Timestamp(f'{y}-11-14'), 4: pd.Timestamp(f'{y+1}-03-31')}[q]


def load_book_equity(cache_path):
    """캐시 → {종목: DataFrame[분기, book(자기자본총계), avail]}."""
    d = json.load(open(cache_path, encoding='utf-8'))
    out = {}
    for name, s in d.get('data', {}).items():
        rows = [(q, v.get('자기자본총계')) for q, v in s.get('quarters', {}).items()
                if v.get('자기자본총계')]
        if not rows:
            continue
        df = pd.DataFrame(rows, columns=['분기', 'book']).sort_values('분기').reset_index(drop=True)
        df['avail'] = df['분기'].map(quarter_avail_date)
        out[name] = df
    return out


def book_asof(table, name, dt):
    df = table.get(name)
    if df is None:
        return None
    a = df[df['avail'] <= dt]
    return float(a.iloc[-1]['book']) if len(a) else None


def price_asof(panel, name, dt):
    s = panel.get(name)
    if s is None:
        return None
    s2 = s[s.index <= dt].dropna()
    return float(s2.iloc[-1]) if len(s2) else None


def value_scores_at(table, names, dt, panel, shares):
    """B/M = book / (price×shares). 횡단면 3분위: 싼(고 B/M)=+1, 비싼=-1."""
    bm = {}
    for n in names:
        book, px, sh = book_asof(table, n, dt), price_asof(panel, n, dt), shares.get(n)
        if book is None or px is None or not sh:
            continue
        mc = px * sh
        if mc > 0:
            bm[n] = book / mc
    if len(bm) < 3:
        return {n: 0 for n in names}
    s = pd.Series(bm).sort_values(ascending=False)     # 높은 B/M(싼) 먼저
    up = s.iloc[max(1, round(len(s)*0.2)) - 1]
    lo = s.iloc[-max(1, round(len(s)*0.2))]
    return {n: (1 if (n in bm and bm[n] >= up) else -1 if (n in bm and bm[n] <= lo) else 0)
            for n in names}


def run(panel, table, shares, grade, compute_scores_at, caps_fn=None, sectors=None, val_w=VAL_W, cost=COST):
    k = panel['_KOSPI']; end = k.index[-1]; start = end - pd.DateOffset(years=4)
    bp = k[(k.index >= start) & (k.index <= end)]
    rebal = sorted({k.index[k.index.get_indexer([d], method='bfill')[0]]
                    for d in bp.resample('MS').first().dropna().index if d <= end})
    if rebal[-1] < end: rebal.append(end)
    names = [n for n in panel if not n.startswith('_')]
    res = {'base': [], 'val': [], 'bench': []}; pw = {'base': {}, 'val': {}}; turn = {'base': 0.0, 'val': 0.0}
    for i in range(len(rebal)-1):
        d0, d1 = rebal[i], rebal[i+1]
        snap = compute_scores_at(panel, d0)
        if snap is None or len(snap) == 0: continue
        vs = value_scores_at(table, names, d0, panel, shares)
        snap = snap.copy()
        snap['등급_val'] = snap.apply(lambda r: grade(r['체력_v37_2'] + val_w*vs.get(r['종목'], 0)), axis=1)
        for var, col in [('base', '등급_v37_2'), ('val', '등급_val')]:
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
            turn[var] += to; r -= to*cost; pw[var] = dict(w); res[var].append(r)
        kw = k[(k.index > d0) & (k.index <= d1)].dropna()
        res['bench'].append(float(kw.iloc[-1]/kw.iloc[0]-1) if len(kw) >= 2 else 0.0)
    return res, turn


def load_shares(codes):
    """현재 주식수 (fdr.StockListing). Stocks 없으면 Marcap/Close로."""
    import FinanceDataReader as fdr
    lst = fdr.StockListing('KRX')
    cc = 'Code' if 'Code' in lst.columns else lst.columns[0]
    lst = lst.copy(); lst[cc] = lst[cc].astype(str).str.zfill(6); lst = lst.set_index(cc)
    sh = {}
    for name, code in codes.items():
        code = str(code).zfill(6)
        if code not in lst.index: sh[name] = None; continue
        row = lst.loc[code]
        if 'Stocks' in lst.columns and pd.notna(row.get('Stocks')) and row.get('Stocks'):
            sh[name] = float(row['Stocks'])
        elif 'Marcap' in lst.columns and 'Close' in lst.columns and row.get('Close'):
            sh[name] = float(row['Marcap'])/float(row['Close'])
        else: sh[name] = None
    return sh


def main():
    grade, JINWOO_v37, fetch_long_panel, compute_scores_at, _m, _ir, caps_fn = _load_user()
    panel = fetch_long_panel(years=4)
    print(f"  [1] 가격 수집 완료: {len([n for n in panel if not n.startswith('_')])}종목")
    sectors = {n: i['산업'] for n, i in JINWOO_v37.items()}
    codes = {n: i['코드'] for n, i in JINWOO_v37.items()}
    cache = Path(__file__).parent / 'quality_timeseries_cache.json'
    if not cache.exists():
        print("[중단] quality_timeseries_cache.json 없음 → fetch_dart_quarterly.py 먼저 실행."); return
    table = load_book_equity(str(cache))
    print(f"  [2] 장부가(자기자본총계) 로드: {len(table)}종목")
    try:
        shares = load_shares(codes)
        print(f"  [3] 주식수 로드: {sum(1 for v in shares.values() if v)}종목, 백테스트 시작...")
    except Exception as e:
        print(f"[중단] 주식수(StockListing) 실패: {e}"); return
    print("Value(B/M) PIT 검증 (base=v3.7.2 vs +Value):")
    for vw in (1.0, 0.5):
        res, turn = run(panel, table, shares, grade, compute_scores_at, caps_fn, sectors, val_w=vw)
        if vw == 1.0:
            print(f"  base       {_m(res['base'])}  IR={_ir(res['base'], res['bench'])}")
        print(f"  +Value×{vw}  {_m(res['val'])}  IR={_ir(res['val'], res['bench'])}  turnover={round(turn['val'],3)}")
    print("\n합격선: +Value 연환산 ≥ base, MDD 악화 없음 → 통과 시 채택, 아니면 기각(GP/AG/EarnMom처럼).")


def metrics_local(rets, ppy=12):
    a = np.array(rets)
    if len(a) == 0: return {}
    cum = float(np.prod(1+a)-1); ann = (1+cum)**(ppy/len(a))-1; vol = float(a.std()*np.sqrt(ppy))
    cc = np.cumprod(1+a); pk = np.maximum.accumulate(cc)
    return {'누적%': round(cum*100, 1), '연환산%': round(ann*100, 2),
            'Sharpe': round(ann/vol, 2) if vol > 0 else None, 'MDD%': round(float(((cc-pk)/pk).min())*100, 2)}


def _selftest():
    ok = 0
    assert quarter_avail_date('2022Q1') == pd.Timestamp('2022-05-15'); ok += 1
    import tempfile, os
    qs = ['2021Q1', '2021Q2', '2021Q3', '2021Q4', '2022Q1']
    cache = {'data': {
        'AAA': {'quarters': {q: {'자기자본총계': 1e12} for q in qs}},   # 장부가 큼
        'BBB': {'quarters': {q: {'자기자본총계': 1e11} for q in qs}},
        'CCC': {'quarters': {q: {'자기자본총계': 5e11} for q in qs}}}}
    p = os.path.join(tempfile.gettempdir(), '_v.json'); json.dump(cache, open(p, 'w'))
    tbl = load_book_equity(p)
    assert set(tbl) == {'AAA', 'BBB', 'CCC'} and book_asof(tbl, 'AAA', pd.Timestamp('2022-09-01')); ok += 1
    idx = pd.bdate_range('2021-06-01', periods=300); rng = np.random.default_rng(7)
    panel = {'_KOSPI': pd.Series(100+np.cumsum(rng.normal(0, 0.5, 300)), index=idx)}
    for n in ['AAA', 'BBB', 'CCC']:
        panel[n] = pd.Series(100.0, index=idx)
    shares = {'AAA': 1e6, 'BBB': 1e8, 'CCC': 1e7}     # 같은 가격 → B/M: AAA 1e4 > CCC 500 > BBB 10
    vs = value_scores_at(tbl, ['AAA', 'BBB', 'CCC'], pd.Timestamp('2022-09-01'), panel, shares)
    assert vs['AAA'] == 1 and vs['BBB'] == -1, vs; ok += 1                 # 싼=+1, 비싼=-1
    def grade(x): return 'S+' if x >= 14 else 'S' if x >= 12 else 'A' if x >= 9 else 'B'
    def stub(panel, dt): return pd.DataFrame({'종목': ['AAA', 'BBB', 'CCC'],
                                              '체력_v37_2': [13.5, 9.2, 8.8],
                                              '등급_v37_2': ['S', 'A', 'B']})
    res, turn = run(panel, tbl, shares, grade, stub)
    assert len(res['val']) >= 1 and len(res['base']) >= 1; ok += 1
    print(f"[OK] Value(B/M) self-test 통과 ({ok} checks)")
    print("     AAA(고 B/M=싼)=+1, BBB(저 B/M=비싼)=-1, PIT 공시일 적용 확인")


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--selftest', action='store_true')
    a, _ = ap.parse_known_args()
    try:
        _selftest() if a.selftest else main()
    except Exception:
        import traceback
        print("\n===== [에러] 아래 내용을 그대로 복사해 붙여주세요 =====")
        traceback.print_exc()
