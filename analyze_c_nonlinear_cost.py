#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
analyze_c_nonlinear_cost.py — C(교체주기) 비선형 집행비용 robustness
==============================================================================
핸드오프 미해결 과제: 월간 리밸런스 우위(인샘플)가 264% 회전율의 *비선형*
슬리피지/시장충격 차감 후에도 살아남는가? (rebalance_frequency.py는 선형 bp만)

접근(정직): 비선형 비용계수는 ADV 없이 보정 불가 → 단정 대신 **breakeven**을 찾는다.
  1) 선형 모델 재현 + 비용 sweep → 월간이 연간에 추월당하는 왕복비용(breakeven bps)
  2) 볼록(시장충격) 모델: cost_event = base·t + impact·t^1.5
     (한 번에 t 비율을 체결 → 충격비용 ∝ t^1.5; 큰 단발 교체를 더 무겁게 벌점)
     → 월간(잦은 소액) vs 연간(드문 거액)의 구조 차이를 반영
  3) impact 계수 sweep → 월간 우위가 사라지는 impact breakeven

핵심 구조: 월간은 회전율 총합은 크나 *이벤트당* 교체비율은 작다. 볼록비용은
이벤트당 크기를 벌하므로, "총회전율 264%"의 순진한 선형 해석보다 월간에 유리.

입력: fundamentals_pit.csv + kospi_monthly_prices.csv (기존 PIT 캐시)
산출: analyze_c_nonlinear_cost_<ts>.json + 콘솔표.  캐시: _c_topk_cache.json(resume)
정직성: 인샘플 백테스트. forward 기대치 아님. 결론은 "비용가정에 대한 robustness"만.
"""
import argparse, os, sys, json, time
import numpy as np, pandas as pd
import pit_universe_backtest as PB

FREQS = [(1, "월간"), (3, "분기"), (6, "반기"), (12, "연간")]
CACHE = "_c_topk_cache.json"
MAXK = 30  # 캐시에 저장할 상위 종목 수(K up to 30 실험 허용)


def precompute_rankings(fund_csv, prices_csv, save_every=5):
    """모든 월 i>=12 의 top-MAXK PIT 랭킹을 1회 계산·캐시(resume 가능)."""
    fund = pd.read_csv(fund_csv, dtype={"code": str}); fund["code"] = fund["code"].str.zfill(6)
    prices = pd.read_csv(prices_csv, index_col=0, parse_dates=True)
    prices.columns = [str(c).zfill(6) for c in prices.columns]
    pf = PB.piotroski(fund); months = prices.index
    mkt_ret = prices.pct_change().mean(axis=1); fcols = list(prices.columns)

    cache = {}
    if os.path.exists(CACHE):
        with open(CACHE) as f: cache = json.load(f)
    need = [i for i in range(12, len(months)) if str(i) not in cache]
    t0 = time.time()
    for n, i in enumerate(need):
        dt = months[i]
        sc = PB.score_at(i, list(months), prices, mkt_ret, fcols, pf, dt.year)
        cache[str(i)] = list(sc.head(MAXK).index)
        if (n + 1) % save_every == 0:
            with open(CACHE, "w") as f: json.dump(cache, f)
            print(f"  precompute {n+1}/{len(need)} (i={i}, {time.time()-t0:.0f}s)", flush=True)
    with open(CACHE, "w") as f: json.dump(cache, f)
    done = len([i for i in range(12, len(months)) if str(i) in cache])
    print(f"[precompute] {done}/{len(months)-12} months cached ({time.time()-t0:.0f}s)")
    return prices, months, len(months)


def holdings_from_cache(months_len, k, step):
    """캐시 랭킹으로 step주기 보유맵 + 이벤트당 교체비율 리스트."""
    with open(CACHE) as f: cache = json.load(f)
    hold = {}; cur = []; turns = {}
    for i in range(months_len):
        if i >= 12 and (i - 12) % step == 0 and str(i) in cache:
            new = cache[str(i)][:k]
            if cur:
                turns[i] = len(set(new) ^ set(cur)) / (2.0 * k)
            cur = new
        hold[i] = cur
    return hold, turns


def cost_adjust(gross, months, turns, base_bps, imp_bps=0.0, power=1.5):
    """net = gross - (base·t + imp·t^power)/1e4 (리밸런스월에 부과)."""
    net = gross.copy()
    for i, t in turns.items():
        dt = months[i]
        if dt in net.index:
            c = (base_bps * t + imp_bps * (t ** power)) / 10000.0
            net.loc[dt] = net.loc[dt] - c
    return net


def cagr_of(prices, hold, months, turns, base_bps, imp_bps=0.0):
    gross = PB.ew_returns(prices, hold)
    net = cost_adjust(gross, months, turns, base_bps, imp_bps)
    return PB.metrics(gross), PB.metrics(net)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fundamentals", default="fundamentals_pit.csv")
    ap.add_argument("--prices", default="kospi_monthly_prices.csv")
    ap.add_argument("--k", type=int, default=18)
    ap.add_argument("--precompute-only", action="store_true")
    a = ap.parse_args()

    prices, months, mlen = precompute_rankings(a.fundamentals, a.prices)
    if a.precompute_only:
        return 0

    K = a.k
    years = mlen / 12.0
    # 주기별 보유·회전율·gross
    per = {}
    for step, lab in FREQS:
        hold, turns = holdings_from_cache(mlen, K, step)
        gross = PB.ew_returns(prices, hold)
        ev = list(turns.values())
        per[lab] = dict(step=step, hold=hold, turns=turns, gross=gross,
                        ann_turn=sum(ev) / years,
                        ev_mean=(np.mean(ev) if ev else 0.0),
                        ev_max=(max(ev) if ev else 0.0),
                        n_ev=len(ev))

    out = {"run_at": pd.Timestamp.now().isoformat(), "K": K, "months": mlen,
           "note": "인샘플 robustness. forward 아님.", "freqs": {}, "linear_sweep": {},
           "convex_sweep": {}, "breakeven": {}}

    # 1) 선형 모델: gross + net@30/60/100 + 회전율 구조
    print(f"\n=== C 비선형비용 robustness (K={K}, {mlen}개월, {years:.1f}년) ===")
    print(f"{'주기':6}{'총CAGR':>8}{'순@30':>8}{'순@60':>8}{'순@100':>9}"
          f"{'연회전':>7}{'이벤트당평균':>11}{'이벤트당최대':>11}{'#이벤트':>7}")
    for lab in ["월간", "분기", "반기", "연간"]:
        p = per[lab]
        g = PB.metrics(p["gross"]).get("CAGR", 0)
        nets = {}
        for c in (30, 60, 100):
            nets[c] = PB.metrics(cost_adjust(p["gross"], months, p["turns"], c)).get("CAGR", 0)
        out["freqs"][lab] = dict(gross_cagr=g, net30=nets[30], net60=nets[60], net100=nets[100],
                                 ann_turn=p["ann_turn"], ev_mean=p["ev_mean"], ev_max=p["ev_max"], n_ev=p["n_ev"])
        print(f"{lab:6}{g:>8.1%}{nets[30]:>8.1%}{nets[60]:>8.1%}{nets[100]:>9.1%}"
              f"{p['ann_turn']:>7.0%}{p['ev_mean']:>11.0%}{p['ev_max']:>11.0%}{p['n_ev']:>7d}")

    # 2) 선형 breakeven: 월간 net == 연간 net 되는 base_bps
    mo, an = per["월간"], per["연간"]
    def net_cagr(p, base, imp=0.0):
        return PB.metrics(cost_adjust(p["gross"], months, p["turns"], base, imp)).get("CAGR", 0)
    lin_grid = list(range(0, 1001, 25))
    be_lin = None
    for c in lin_grid:
        if net_cagr(mo, c) <= net_cagr(an, c):
            be_lin = c; break
    out["breakeven"]["linear_bps"] = be_lin
    out["linear_sweep"] = {str(c): {"월간": net_cagr(mo, c), "연간": net_cagr(an, c)} for c in (0,100,200,300,500,1000)}
    print(f"\n[선형 breakeven] 월간이 연간에 추월당하는 왕복비용 = "
          + (f"{be_lin}bp" if be_lin is not None else ">1000bp (현실범위 밖)"))
    print(f"  참고: 현실 왕복비용은 30~60bp. 월간 net@100 = {out['freqs']['월간']['net100']:.1%} "
          f"vs 연간 net@100 = {out['freqs']['연간']['net100']:.1%}")

    # 3) 볼록(시장충격) 모델: base 30bp 고정 + impact sweep
    base_fixed = 30
    print(f"\n=== 볼록 비용  cost=({base_fixed}bp)·t + (impact)·t^1.5  (이벤트당 크기 벌점) ===")
    print(f"{'impact':>8}{'월간순':>9}{'분기순':>9}{'반기순':>9}{'연간순':>9}{'월-연차':>9}")
    conv_grid = [0, 100, 200, 400, 800, 1600, 3200]
    be_conv = None
    for imp in conv_grid:
        cags = {lab: net_cagr(per[lab], base_fixed, imp) for lab in ["월간","분기","반기","연간"]}
        diff = cags["월간"] - cags["연간"]
        out["convex_sweep"][str(imp)] = cags
        print(f"{imp:>8}{cags['월간']:>9.1%}{cags['분기']:>9.1%}{cags['반기']:>9.1%}{cags['연간']:>9.1%}{diff:>9.1%}")
        if be_conv is None and diff <= 0:
            be_conv = imp
    out["breakeven"]["convex_impact_bps_at_base30"] = be_conv
    print(f"\n[볼록 breakeven] 월간이 연간에 추월당하는 impact 계수(t=1 단발 풀교체 기준) = "
          + (f"{be_conv}bp" if be_conv is not None else ">3200bp (극단)"))

    ts = pd.Timestamp.now().strftime("%Y%m%d_%H%M")
    fn = f"analyze_c_nonlinear_cost_{ts}.json"
    with open(fn, "w") as f: json.dump(out, f, ensure_ascii=False, indent=1, default=float)
    print(f"\n저장: {fn}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
