#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
value_quality_pit_oos.py - 가치/퀄리티 사전선택(PIT) OOS 백테스트 (FDR 불필요, 로컬 자립)
목적: 생존편향 없는 광범위 유니버스(KOSPI 시총 top-200)에서, 매 시점 가용정보만으로
      사전선택했을 때 어떤 팩터가 시장(cap-weight) 대비 초과수익을 내는가?
      밸류/퀄리티/모멘텀 + 게이트 변형(피오트로스키 원형, 그레이엄, 퀄리티-필터 모멘텀).
방법: 시총=liquidity_sector.csv 스냅샷/현재가로 주식수 역산 후 조정가로 과거 시총 복원
      (backtest_value_pit.py와 동일 방법론). PIT: 회계연도 Y는 익년 4월부터 가용.
컨벤션: Sharpe=연환산/연변동성, IR=연환산초과/연추적오차 (기존 산출물과 동일).
입력(전부 같은 폴더): kospi_monthly_prices.csv, fundamentals_pit.csv, book_equity.csv,
                      liquidity_sector.csv
실행: python value_quality_pit_oos.py
"""
import json, sys
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

BASE = Path(__file__).parent.resolve()
COST = 0.00235
TOP_UNIV = 200
TOP_N = 20
AVAIL_MONTH = 4
START = '2021-05-31'


def _read(name, **kw):
    return pd.read_csv(BASE / name, encoding='utf-8-sig', **kw)


def load_prices(fname):
    df = _read(fname)
    df = df.rename(columns={df.columns[0]: 'Date'})
    df['Date'] = pd.to_datetime(df['Date'])
    df = df.set_index('Date').sort_index()
    df.columns = [str(c).zfill(6) for c in df.columns]
    df = df.apply(pd.to_numeric, errors='coerce')
    return df[[c for c in df.columns if df[c].notna().sum() >= 13]]


def load_shares():
    liq = _read('liquidity_sector.csv', dtype={'code': str})
    liq['code'] = liq['code'].str.zfill(6)
    return dict(zip(liq['code'], pd.to_numeric(liq['mcap'], errors='coerce')))


def load_fund():
    f = _read('fundamentals_pit.csv', dtype={'code': str})
    f['code'] = f['code'].str.zfill(6)
    be = _read('book_equity.csv', dtype={'code': str})
    be['code'] = be['code'].str.zfill(6)
    f = f.merge(be, on=['code', 'fiscal_year'], how='left')
    f['book'] = f['book_equity'].fillna(f['equity'])
    f['gp'] = f['revenue'] - f['cogs']
    f['avail'] = pd.to_datetime((f['fiscal_year'] + 1).astype(str) + '-%02d-01' % AVAIL_MONTH)
    f = f.sort_values(['code', 'fiscal_year'])
    f['assets_prev'] = f.groupby('code')['assets'].shift(1)
    return f


def fund_asof(f, dt):
    av = f[f['avail'] <= dt]
    if av.empty:
        return None
    return av.sort_values('fiscal_year').groupby('code').tail(1).set_index('code')


def z(s):
    s = s.astype(float)
    mu, sd = s.mean(), s.std(ddof=0)
    if not sd or np.isnan(sd):
        return pd.Series(0.0, index=s.index)
    return ((s - mu) / sd).clip(-3, 3)


def frame(codes, fund, mc_now, p_now, p_t):
    rows = {}
    for c in codes:
        if c not in fund.index:
            continue
        r = fund.loc[c]
        sh, pn, pt = mc_now.get(c), p_now.get(c), p_t.get(c)
        if not sh or not pn or pn <= 0 or not pt or pt <= 0:
            continue
        mc = sh * (pt / pn)
        a = r['assets']
        if mc <= 0 or not a or a <= 0:
            continue
        ni, eq, cfo = r['net_income'], r['equity'], r['cfo']
        rows[c] = {'mcap_t': mc,
                   'EP': ni / mc if pd.notna(ni) else np.nan,
                   'BM': r['book'] / mc if pd.notna(r['book']) else np.nan,
                   'GPA': r['gp'] / a if pd.notna(r['gp']) else np.nan,
                   'ROE': ni / eq if (pd.notna(ni) and eq and eq > 0) else np.nan,
                   'ACC': -((ni - cfo) / a) if (pd.notna(ni) and pd.notna(cfo)) else np.nan,
                   'AG': -((a - r['assets_prev']) / r['assets_prev']) if (pd.notna(r['assets_prev']) and r['assets_prev'] > 0) else np.nan}
    return pd.DataFrame(rows).T if rows else None


def met(rets, bench=None, ppy=12):
    a = np.asarray(rets, float)
    if len(a) == 0:
        return {}
    cum = float(np.prod(1 + a) - 1)
    ann = (1 + cum) ** (ppy / len(a)) - 1
    vol = float(a.std() * np.sqrt(ppy))
    cc = np.cumprod(1 + a)
    pk = np.maximum.accumulate(cc)
    o = {'ann': round(ann * 100, 2), 'vol': round(vol * 100, 2),
         'Sharpe': round(ann / vol, 2) if vol > 0 else None,
         'MDD': round(float(((cc - pk) / pk).min()) * 100, 2), 'n': len(a)}
    if bench is not None:
        ac = a - np.asarray(bench, float)
        o['IR'] = round((ac.mean() * ppy) / (ac.std() * np.sqrt(ppy)), 2) if ac.std() > 0 else None
        o['win'] = round(float((a > np.asarray(bench, float)).mean()) * 100, 1)
    return o


def run():
    px = load_prices('kospi_monthly_prices.csv')
    mc_now = load_shares()
    fund = load_fund()
    rebal = [m for m in px.index if m >= pd.Timestamp(START)]
    sleeves = ['Value', 'Quality', 'ValueQuality', 'Momentum',
               'Q_then_V', 'V_then_Q', 'Mom_then_Q', 'Q_then_Mom']
    label = {'Q_then_V': 'Q->V(Piotroski)', 'V_then_Q': 'V->Q(Graham)',
             'Mom_then_Q': 'Mom->Q(QualMom)', 'Q_then_Mom': 'Q->Mom'}
    rets = {s: [] for s in sleeves}
    rets['EW_univ'] = []
    rets['CW_univ'] = []
    prev = {s: {} for s in sleeves}
    turn = {s: 0.0 for s in sleeves}
    plog = {s: [] for s in sleeves}

    for i in range(len(rebal) - 1):
        d0, d1 = rebal[i], rebal[i + 1]
        fa = fund_asof(fund, d0)
        if fa is None:
            continue
        p_now = px.iloc[-1].to_dict()
        p_t = px.loc[d0].to_dict()
        hist = px.loc[:d0]
        valid = [c for c in px.columns if hist[c].notna().sum() >= 13
                 and pd.notna(px.loc[d0, c]) and pd.notna(px.loc[d1, c])]
        fr = frame(valid, fa, mc_now, p_now, p_t)
        if fr is None or len(fr) < 30:
            continue
        univ = fr['mcap_t'].sort_values(ascending=False).head(TOP_UNIV).index.tolist()
        fr = fr.loc[univ]
        mom = {}
        for c in univ:
            s = hist[c].dropna()
            if len(s) >= 13:
                mom[c] = s.iloc[-2] / s.iloc[-13] - 1
        fr['MOM'] = pd.Series(mom)
        V = (z(fr['EP']) + z(fr['BM'])) / 2
        Q = (z(fr['GPA']) + z(fr['ROE']) + z(fr['ACC']) + z(fr['AG'])) / 4
        M = z(fr['MOM'])

        def gate(p, sec, q=0.5):
            out = sec.copy()
            out[p < p.quantile(1 - q)] = np.nan
            return out

        score = {'Value': V, 'Quality': Q, 'ValueQuality': (z(V) + z(Q)) / 2, 'Momentum': M,
                 'Q_then_V': gate(Q, V), 'V_then_Q': gate(V, Q),
                 'Mom_then_Q': gate(M, Q), 'Q_then_Mom': gate(Q, M)}
        fwd = {c: float(px.loc[d1, c] / px.loc[d0, c] - 1) for c in univ}
        rets['EW_univ'].append(float(np.mean([fwd[c] for c in univ])))
        ws = fr['mcap_t'].sum()
        rets['CW_univ'].append(float(sum(fr.loc[c, 'mcap_t'] / ws * fwd[c] for c in univ)))
        for s in sleeves:
            picks = score[s].dropna().sort_values(ascending=False).head(TOP_N).index.tolist()
            if not picks:
                rets[s].append(0.0)
                continue
            w = {c: 1 / len(picks) for c in picks}
            r = sum(w[c] * fwd[c] for c in picks)
            to = sum(abs(w.get(c, 0) - prev[s].get(c, 0)) for c in set(w) | set(prev[s])) / 2
            turn[s] += to
            rets[s].append(r - to * COST)
            prev[s] = w
            plog[s].append({'date': str(d0.date()), 'picks': picks})

    n = len(rets['CW_univ'])
    yrs = n / 12
    bench = rets['CW_univ']
    ew = rets['EW_univ']
    summ = {'run_at': datetime.now().isoformat(),
            'window': [str(rebal[0].date()), str(rebal[-1].date()), n],
            'universe': 'KOSPI mcap top-%d' % TOP_UNIV, 'hold': TOP_N, 'cost': COST,
            'labels': label, 'metrics': {}, 'turnover_yr': {}}
    print('\n' + '=' * 82)
    print('Value/Quality 사전선택 PIT OOS  |  %s~%s  (%d개월)' % (summ['window'][0], summ['window'][1], n))
    print('KOSPI mcap top-%d, 보유 %d EW, 월리밸런스, 비용 %.5f' % (TOP_UNIV, TOP_N, COST))
    print('=' * 82)
    print('%-22s%8s%6s%8s%7s%7s%8s' % ('sleeve', 'ann%', 'Shrp', 'MDD%', 'IR_CW', 'IR_EW', 'turn/y'))
    print('-' * 82)
    for s in sleeves + ['EW_univ', 'CW_univ']:
        m = met(rets[s], bench if s != 'CW_univ' else None)
        mew = met(rets[s], ew) if s not in ('EW_univ', 'CW_univ') else {}
        m['IR_vs_EW'] = mew.get('IR')
        summ['metrics'][s] = m
        if s in turn:
            summ['turnover_yr'][s] = round(turn[s] / yrs, 2)
        print('%-22s%8s%6s%8s%7s%7s%8s' % (label.get(s, s), m['ann'], m['Sharpe'], m['MDD'],
              str(m.get('IR', '-')), str(m.get('IR_vs_EW', '-')),
              str(round(turn[s] / yrs, 1) if s in turn else '-')))
    print('-' * 82)
    print('IR_CW=시총가중 유니버스(KOSPI proxy) 대비 / IR_EW=동일가중 대비(순수 팩터효과)')
    summ['picks_last'] = {s: (plog[s][-1] if plog[s] else None) for s in sleeves}
    op = BASE / ('value_quality_pit_%s.json' % datetime.now().strftime('%Y%m%d_%H%M'))
    json.dump(summ, open(op, 'w', encoding='utf-8'), ensure_ascii=False, indent=2)
    print('\n저장: %s' % op.name)
    return summ


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
        pass
    run()
