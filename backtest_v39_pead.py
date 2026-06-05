#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
진우퀀트 v3.9 PEAD — Stage 2 PIT 백테스트  [PC 실행 전용]

⚠️ 실행 위치: C:\\Users\\긍정적인_삶의자세\\Desktop\\진우퀀트
⚠️ 선행: python fetch_dart_eps.py --start-year 2018
   (백테스트 초기 구간의 SUE σ 8분기 이력 확보 — 증분 수집이라 3~5분)
⚠️ 어제(06-03) backtest_v39_pit.py(EarnMom, 기각)와 별개 파일 — 덮어쓰지 않음.

비교 (월말 리밸런스, 4년 OOS):
  base      = v3.7.2 (Echo ×1.0)             ← production 함수 그대로 재사용
  pead_05   = v3.7.2 + PEAD ×0.5
  pead_10   = v3.7.2 + PEAD ×1.0

사전 합격선 (결정메모 §2 — 결과 보고 바꾸지 않는다):
  ΔCAGR ≥ +1.0%p (vs base, 본 스크립트 내부 base)  AND  Sharpe·IR 비열위 (−0.01 허용)
  ×0.5 / ×1.0 둘만 시험. 미달 → 즉시 종료 (2차 기각).

정합성 노트:
  - F_korean·ModF·Sloan·NOA는 현재값 정적 사용 — 기존 v3.7.2 백테스트와 동일한 한계.
    base와 PEAD 변형이 같은 정적 필드를 공유하므로 ΔCAGR(PEAD 효과)는 깨끗함.
  - PEAD만은 진짜 PIT (DART 공시일 + 60거래일 게이트, eps_sue_cache.json).
  - 거래비용 0 (기존 base 백테스트 컨벤션과 동일 — 비용은 별도 검증 단계).
  - 참조: 공식 base 4년 연환산 73.18% (진우 환경, 2026-06-03). 재현 base가 ±1%p 내면 정상.
"""

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

BASE = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE))

TARGET_GRADES = {'S+', 'S', 'A'}
PASS_DELTA_CAGR = 1.0          # %p — 사전 합격선
TOL = 0.01                     # Sharpe·IR 비열위 허용 오차


# ----------------------------------------------------------------------
# 순수 함수 (self-test 대상 — 외부 의존 없음)
# ----------------------------------------------------------------------
def month_end_dates(index, n_months):
    """거래일 인덱스에서 마지막 (n_months+1)개 월말 영업일 (완결 월만)."""
    idx = pd.DatetimeIndex(index)
    s = pd.Series(idx, index=idx)
    me = s.groupby([idx.year, idx.month]).max().tolist()
    return me[-(n_months + 1):]


def portfolio_month_return(weights, prices, t0, t1):
    """weights: {name: w}, prices: {name: Series}. t0→t1 보유 수익률."""
    if not weights:
        return 0.0
    r = 0.0
    for name, w in weights.items():
        s = prices.get(name)
        if s is None:
            continue
        s0 = s.loc[:t0]
        s1 = s.loc[:t1]
        if len(s0) == 0 or len(s1) == 0 or s0.iloc[-1] == 0:
            continue
        r += w * (float(s1.iloc[-1]) / float(s0.iloc[-1]) - 1.0)
    return r


def perf_metrics(monthly_returns, bench_returns=None):
    """월수익 list → 지표 dict. Sharpe·IR ×√12, MDD 월말 기준."""
    r = np.asarray(monthly_returns, dtype=float)
    n = len(r)
    if n == 0:
        return {}
    cum = float(np.prod(1 + r) - 1)
    cagr = float((1 + cum) ** (12.0 / n) - 1)
    sharpe = float(r.mean() / r.std(ddof=1) * np.sqrt(12)) if n > 1 and r.std(ddof=1) > 0 else 0.0
    nav = np.cumprod(1 + r)
    peak = np.maximum.accumulate(nav)
    mdd = float((nav / peak - 1).min())
    out = {'months': n, 'cum_%': round(cum * 100, 2), 'cagr_%': round(cagr * 100, 2),
           'sharpe': round(sharpe, 2), 'mdd_%': round(mdd * 100, 2),
           'win_rate_%': round(float((r > 0).mean()) * 100, 1)}
    if bench_returns is not None and len(bench_returns) == n:
        ex = r - np.asarray(bench_returns, dtype=float)
        ir = float(ex.mean() / ex.std(ddof=1) * np.sqrt(12)) if n > 1 and ex.std(ddof=1) > 0 else 0.0
        out['ir'] = round(ir, 2)
        out['win_vs_kospi_%'] = round(float((ex > 0).mean()) * 100, 1)
    return out


def verdict(base_m, var_m):
    """사전 합격선 판정: ΔCAGR ≥ +1.0%p AND Sharpe·IR 비열위(−0.01 허용)."""
    d_cagr = var_m['cagr_%'] - base_m['cagr_%']
    ok = (d_cagr >= PASS_DELTA_CAGR
          and var_m['sharpe'] >= base_m['sharpe'] - TOL
          and var_m.get('ir', 0) >= base_m.get('ir', 0) - TOL)
    return ok, round(d_cagr, 2)


# ----------------------------------------------------------------------
# 백테스트 본체  [PC 실행 — FDR + production 모듈 + eps_sue_cache 필요]
# ----------------------------------------------------------------------
def fetch_prices(years):
    import FinanceDataReader as fdr
    import score_v37_2 as prod
    end = datetime.now()
    start = end - timedelta(days=int(years * 365 + 460))   # Echo 13M 워밍업 여유
    prices = {}
    kospi = fdr.DataReader('KS11', start, end)['Close'].dropna()
    print(f'  KOSPI {len(kospi)} 영업일 ({kospi.index[0].date()} ~ {kospi.index[-1].date()})')
    for name, info in prod.JINWOO_v37.items():
        s = fdr.DataReader(str(info['코드']).zfill(6), start, end)['Close'].dropna()
        prices[name] = s
        print(f'  {name} {len(s)} 영업일')
    return prices, kospi


def score_base_at(t, prices, kospi):
    """리밸 시점 t의 v3.7.2 체력_최종 — production 함수 재사용 (슬라이스 패널)."""
    import score_v37_2 as prod
    sliced = {name: s.loc[:t] for name, s in prices.items()}
    sliced['_KOSPI'] = kospi.loc[:t]
    echo_scores, _ = prod.compute_echo_scores(sliced)

    out = {}
    for name, info in prod.JINWOO_v37.items():
        s = sliced.get(name)
        체력_12점 = info['F_korean'] * (12 / 9.001)
        r_1m = prod.compute_1m_return(s)
        far_val, _sig = prod.far_trigger(체력_12점, r_1m)
        mom12_score = prod.mom12_to_score(prod.compute_mom12(s))
        bab_score = prod.bab_to_score(prod.compute_beta60(s, sliced['_KOSPI']))
        noa_score = prod.noa_to_score(info.get('NOA', 0))
        echo = echo_scores.get(name, 0) * prod.ECHO_WEIGHT
        out[name] = (체력_12점 + info['ModF'] + far_val + info['Sloan']
                     + mom12_score + bab_score + noa_score + echo)
    return out


def weights_from_scores(scores):
    import score_v37_2 as prod
    graded = {name: prod.grade(v) for name, v in scores.items()}
    picks = [n for n, g in graded.items() if g in TARGET_GRADES]
    sectors = {n: prod.JINWOO_v37[n]['산업'] for n in prod.JINWOO_v37}
    return prod.apply_weight_caps(picks, sectors)


def run(years=4, no_gate=False):
    import score_v39_pead as pead_mod
    from score_v39_pead import compute_pead_scores, load_cache

    print('=' * 80)
    print(f'진우퀀트 v3.9 PEAD — Stage 2 PIT 백테스트 ({years}년, 월말 리밸런스)')
    print(f'합격선: ΔCAGR ≥ +{PASS_DELTA_CAGR}%p AND Sharpe·IR 비열위 | 비용 0 (base 컨벤션)')
    print('=' * 80)

    cache = load_cache()
    print('\n📊 가격 수집 (FDR):')
    prices, kospi = fetch_prices(years)

    rebal = month_end_dates(kospi.index, years * 12)
    print(f'\n리밸런스: {len(rebal) - 1}개월 ({rebal[0].date()} ~ {rebal[-1].date()})')

    variants = {'base': 0.0, 'pead_05': 0.5, 'pead_10': 1.0}
    if no_gate:
        variants['pead_10_nogate'] = 1.0
    rets = {k: [] for k in variants}
    bench = []
    names = list(prices.keys())
    pead_active_months = 0

    for i in range(len(rebal) - 1):
        t0, t1 = rebal[i], rebal[i + 1]
        base_scores = score_base_at(t0, prices, kospi)

        gate_idx = kospi.index
        pead_scores, sue_vals, _ann = compute_pead_scores(
            cache, names, t0.to_pydatetime(), gate_idx)
        if no_gate:
            saved = pead_mod.DRIFT_WINDOW_TD
            pead_mod.DRIFT_WINDOW_TD = 10 ** 6
            pead_ng, _, _ = compute_pead_scores(cache, names, t0.to_pydatetime(), gate_idx)
            pead_mod.DRIFT_WINDOW_TD = saved
        if sue_vals:
            pead_active_months += 1

        k0 = float(kospi.loc[:t0].iloc[-1]); k1 = float(kospi.loc[:t1].iloc[-1])
        bench.append(k1 / k0 - 1)

        for vname, w in variants.items():
            if vname == 'base':
                sc = base_scores
            elif vname == 'pead_10_nogate':
                sc = {n: base_scores[n] + w * pead_ng.get(n, 0) for n in base_scores}
            else:
                sc = {n: base_scores[n] + w * pead_scores.get(n, 0) for n in base_scores}
            rets[vname].append(
                portfolio_month_return(weights_from_scores(sc), prices, t0, t1))

    # ---- 결과 ----
    metrics = {k: perf_metrics(v, bench) for k, v in rets.items()}
    metrics['KOSPI'] = perf_metrics(bench)

    print(f'\nPEAD 신호 활성 월: {pead_active_months}/{len(rebal) - 1}')
    print('\n' + '=' * 80)
    hdr = f"{'변형':<16}{'누적%':>10}{'CAGR%':>9}{'Sharpe':>8}{'MDD%':>8}{'IR':>6}{'승률%':>7}"
    print(hdr); print('-' * len(hdr))
    for k in list(variants) + ['KOSPI']:
        m = metrics[k]
        print(f"{k:<16}{m['cum_%']:>10}{m['cagr_%']:>9}{m['sharpe']:>8}"
              f"{m['mdd_%']:>8}{m.get('ir', '—'):>6}{m['win_rate_%']:>7}")

    print('\n참조: 공식 base 4년 CAGR 73.18% (2026-06-03 진우 환경) — '
          f"재현 base {metrics['base']['cagr_%']}% (±1%p 내면 정상)")

    print('\n판정 (사전 합격선):')
    results = {}
    for k in ('pead_05', 'pead_10'):
        ok, d = verdict(metrics['base'], metrics[k])
        results[k] = {'pass': ok, 'delta_cagr_%p': d}
        print(f"  {k}: ΔCAGR {d:+.2f}%p, Sharpe {metrics[k]['sharpe']} vs {metrics['base']['sharpe']}, "
              f"IR {metrics[k].get('ir')} vs {metrics['base'].get('ir')} → {'✅ PASS' if ok else '❌ FAIL'}")
    if not any(r['pass'] for r in results.values()):
        print('\n→ 둘 다 미달: 사전 합격선에 따라 v3.9 PEAD 2차 기각, 노선 종료. v3.7.2 유지.')
    else:
        best = max((k for k in results if results[k]['pass']),
                   key=lambda k: results[k]['delta_cagr_%p'])
        print(f'\n→ {best} 합격: production 통합 검토 단계로 (Stage 3).')

    out = {'run_at': datetime.now().isoformat(), 'years': years,
           'rebalance': [str(d.date()) for d in rebal],
           'pass_rule': f'dCAGR>=+{PASS_DELTA_CAGR}%p AND Sharpe/IR>=base-{TOL}',
           'metrics': metrics, 'verdict': results,
           'monthly_returns': {k: [round(x, 6) for x in v] for k, v in rets.items()},
           'bench_monthly': [round(x, 6) for x in bench]}
    fn = BASE / f'backtest_v39_pead_{datetime.now():%Y%m%d_%H%M}.json'
    fn.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding='utf-8')
    print(f'\n✅ 저장: {fn.name}')


# ----------------------------------------------------------------------
# self-test (합성 데이터 — FDR·DART·production 모듈 불필요)
# ----------------------------------------------------------------------
def self_test():
    ok = 0
    # 1) 월말 영업일 추출
    idx = pd.bdate_range('2024-01-02', '2024-06-28')
    me = month_end_dates(idx, 3)
    assert len(me) == 4 and me[-1] == pd.Timestamp('2024-06-28')
    assert me[0] == pd.Timestamp('2024-03-29')
    ok += 1
    # 2) 포트폴리오 월수익
    s1 = pd.Series([100.0, 110.0], index=[pd.Timestamp('2024-01-31'), pd.Timestamp('2024-02-29')])
    s2 = pd.Series([50.0, 45.0], index=s1.index)
    r = portfolio_month_return({'A': 0.5, 'B': 0.5}, {'A': s1, 'B': s2},
                               s1.index[0], s1.index[1])
    assert abs(r - (0.5 * 0.10 + 0.5 * -0.10)) < 1e-12
    assert portfolio_month_return({}, {}, s1.index[0], s1.index[1]) == 0.0
    ok += 1
    # 3) 지표 — 매월 +1%, 24개월
    m = perf_metrics([0.01] * 24)
    assert abs(m['cagr_%'] - ((1.01 ** 12 - 1) * 100)) < 0.01
    assert m['mdd_%'] == 0.0 and m['win_rate_%'] == 100.0
    ok += 1
    # 4) MDD — +10% 후 −20%
    m = perf_metrics([0.10, -0.20])
    assert abs(m['mdd_%'] - (-20.0)) < 1e-9
    ok += 1
    # 5) IR — 벤치 완전 동일 → 0 (std 0 가드)
    m = perf_metrics([0.01, 0.02, 0.03], [0.01, 0.02, 0.03])
    assert m['ir'] == 0.0 and m['win_vs_kospi_%'] == 0.0
    ok += 1
    # 6) 판정 로직 경계
    b = {'cagr_%': 70.0, 'sharpe': 2.5, 'ir': 1.5}
    assert verdict(b, {'cagr_%': 71.0, 'sharpe': 2.5, 'ir': 1.5})[0] is True      # 정확히 +1.0
    assert verdict(b, {'cagr_%': 70.99, 'sharpe': 2.6, 'ir': 1.6})[0] is False    # CAGR 미달
    assert verdict(b, {'cagr_%': 72.0, 'sharpe': 2.48, 'ir': 1.5})[0] is False    # Sharpe 열위
    assert verdict(b, {'cagr_%': 72.0, 'sharpe': 2.495, 'ir': 1.495})[0] is True  # 허용 오차 내
    ok += 1

    print(f'✅ backtest_v39_pead self-test {ok}/6 통과 (합성 데이터, 외부 의존 없음)')
    print('   실제 백테스트는 진우님 PC에서: python backtest_v39_pead.py')


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--self-test', action='store_true')
    ap.add_argument('--years', type=int, default=4)
    ap.add_argument('--no-gate', action='store_true', help='참고용: 게이트 off ×1.0 변형 추가')
    args = ap.parse_args()
    if args.self_test:
        self_test()
    else:
        run(args.years, args.no_gate)
