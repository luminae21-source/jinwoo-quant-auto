#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""strategy_validation.py — 진우퀀트 전략 검증 표준 하네스 ("틀").

목적: 모든 신규 전략/슬리브/알파를 본체 v3.7.2와 **동일한 자**로 측정.
원칙(다전략분리 설계 §4): 정직 EW/지수 벤치 대비 IR · 생존편향 PIT · OOS · 결합IR.

표준 입력:
  core   : 본체 월수익 Series (소수, 예: 0.05=+5%)
  sleeve : 후보 전략 월수익 Series (동일 월그리드·동일 길이)
  bench  : 벤치마크 월수익 Series (KOSPI 등)
표준 출력: stats(연환산·변동성·Sharpe·MDD·IR) · 상관(전체/하락월) · 결합표 · PASS/FAIL

본체·KOSPI 시계열은 backtest json/history에서 로드(load_core_bench).
사용 예는 파일 하단 __main__ 참고.
"""
import json, numpy as np, pandas as pd
from pathlib import Path

# ---------- 표준 지표 ----------
def stats(r, bench=None):
    r = pd.Series(r).reset_index(drop=True); n = len(r)
    cagr = (1+r).prod()**(12/n) - 1
    vol = r.std(ddof=0)*np.sqrt(12)
    sharpe = (r.mean()*12)/vol if vol else np.nan
    eq = (1+r).cumprod(); mdd = (eq/eq.cummax()-1).min()
    out = dict(연환산=round(cagr*100,2), 변동성=round(vol*100,2), Sharpe=round(sharpe,2),
               MDD=round(mdd*100,2), 승률=round((r>0).mean()*100,1))
    if bench is not None:
        ex = r.values - pd.Series(bench).reset_index(drop=True).values
        out['IR'] = round((ex.mean()*12)/(ex.std(ddof=0)*np.sqrt(12)),2) if ex.std(ddof=0) else np.nan
    return out

def corr_profile(core, sleeve):
    core = pd.Series(core).reset_index(drop=True); sleeve = pd.Series(sleeve).reset_index(drop=True)
    down = core < 0
    return dict(전체=round(float(np.corrcoef(core,sleeve)[0,1]),3),
                하락월=round(float(np.corrcoef(core[down],sleeve[down])[0,1]),3) if down.sum()>2 else np.nan,
                하락월수=int(down.sum()))

def combine(core, sleeve, w):
    """w: 스칼라(상시) 또는 월별 Series(조건부)."""
    core = pd.Series(core).reset_index(drop=True); sleeve = pd.Series(sleeve).reset_index(drop=True)
    w = pd.Series(w, index=range(len(core))) if np.isscalar(w) else pd.Series(w).reset_index(drop=True)
    return (1-w).values*core.values + w.values*sleeve.values

def verdict(base, comb):
    """합격 = MDD 개선 & IR ≥ 본체. (헤지 슬리브엔 Sharpe 보조 병기 권장.)"""
    mdd_ok = comb['MDD'] > base['MDD']; ir_ok = comb['IR'] >= base['IR']
    return dict(판정="PASS" if (mdd_ok and ir_ok) else "FAIL", MDD개선=mdd_ok, IR유지=ir_ok)

# ---------- 본체·벤치 로더 ----------
def load_core_bench(json_path, core_key='r_v37_2_%', bench_key='r_kospi_%'):
    h = json.load(open(json_path, encoding='utf-8'))['history']
    core  = pd.Series({pd.to_datetime(x['date']): x[core_key]/100 for x in h}).sort_index().reset_index(drop=True)
    bench = pd.Series({pd.to_datetime(x['date']): x[bench_key]/100 for x in h}).sort_index().reset_index(drop=True)
    return core, bench

# ---------- 표준 리포트 ----------
def report(name, core, sleeve, bench, weights=(0.15, 0.30)):
    base = stats(core, bench)
    print('='*72); print(f'전략 검증: {name}  (n={len(core)}개월)'); print('='*72)
    print('단독:')
    print('  본체   :', stats(core, bench))
    print(f'  {name:<5}:', stats(sleeve, bench))
    print('  벤치   :', stats(bench))
    print('상관:', corr_profile(core, sleeve))
    print('결합:')
    for w in weights:
        c = stats(combine(core, sleeve, w), bench)
        v = verdict(base, c)
        print(f'  w={w*100:>4.0f}% | 연환산 {c["연환산"]:>6.2f} MDD {c["MDD"]:>7.2f} Sharpe {c["Sharpe"]:>4.2f} IR {c["IR"]:>5.2f} → {v["판정"]}')
    return base

if __name__ == '__main__':
    # 데모: 본체만 로드해 지표 출력 (슬리브는 호출측에서 주입)
    import sys
    BASE = Path(__file__).parent.resolve()
    jp = BASE/'backtest_v37_2_20260602_0158.json'
    if jp.exists():
        core, bench = load_core_bench(jp)
        print('본체 v3.7.2:', stats(core, bench))
        print('KOSPI     :', stats(bench))
