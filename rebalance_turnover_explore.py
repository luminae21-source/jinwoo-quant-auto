"""
rebalance_turnover_explore.py — 회전율(리밸런스 주기) ↔ 순수익 탐색 (2026-06-06)

목적: 핸드오프 C모듈이 남긴 미해결 — "월간 우위가 ① 비선형 집행비용 ② 세밀 주기 그리드
       ③ 진우 계좌(소액·대형주) 현실비용에서도 살아남는가" 를 실측해 "회전율을 어디까지
       높이는 게 이득인지"의 손익분기를 찾는다. production·기존 산출물 무수정, 신규 파일만.

핵심 설계:
- 월별 PIT 점수를 1회만 계산·캐시 → 모든 (주기 × 비용) 조합을 그 위에서 쓸어 45s 제한 회피
  (rebalance_frequency.py의 score_at 재계산을 제거한 가속판 — 출력값 동일, self-test로 검증)
- 비용 모델 2종:
  (A) 선형: cost = turnover × bps_roundtrip  (소액·대형 유동주에 정확 — 슬리피지 평탄·세금 지배)
  (B) 볼록(시장충격): cost = turnover × [bps + impact_k × sqrt(참여율)]  (대형 AUM 스트레스용)
- 산출: 주기별 순CAGR·Sharpe·연회전율 / 비용 스윕에서 월간이 분기에 추월당하는 손익분기 cost
        / 진우 계좌 실참여율 기반 충격 bp(거의 0 입증) / OOS 3분할

정직성: 인샘플 백테스트. forward 기대치 아님(프로젝트 §0). 월간 우위는 모멘텀 포착이라
        반전 시 크래시 위험(Daniel-Moskowitz). OOS 3분할 동봉하되 그래도 in-sample.
"""
import argparse, os, sys
import numpy as np, pandas as pd
import pit_universe_backtest as PB

FREQS = [(1, "월간"), (2, "격월"), (3, "분기"), (4, "4개월"), (6, "반기"), (12, "연간")]
COST_SWEEP_BPS = [20, 25, 30, 40, 50, 75, 100, 150, 200, 300, 500]


def precompute_scores(prices, pf, warmup=12):
    """각 월 i에서 PB.score_at 1회 → {i: 정렬된 점수 Series}. 모든 주기가 공유."""
    months = prices.index
    mkt_ret = prices.pct_change().mean(axis=1)
    fcols = list(prices.columns)
    cache = {}
    for i, dt in enumerate(months):
        if i >= warmup:
            cache[i] = PB.score_at(i, list(months), prices, mkt_ret, fcols, pf, dt.year)
    return cache, months


def hold_and_turns(months, score_cache, k, step, warmup=12):
    hold, cur, turns = {}, [], {}
    for i, dt in enumerate(months):
        if i >= warmup and (i - warmup) % step == 0:
            sc = score_cache.get(i)
            if sc is not None and len(sc) >= k:
                new = list(sc.head(k).index)
                if cur:
                    turns[i] = len(set(new) ^ set(cur)) / (2.0 * k)
                cur = new
        hold[i] = cur
    return hold, turns


def net_metrics(prices, hold, turns, months, bps, impact_k=0.0, aum=0.0, adtv=None, k=18):
    """gross에서 리밸월 비용 차감. impact_k>0이면 볼록(시장충격) 항 추가."""
    gross = PB.ew_returns(prices, hold)
    net = gross.copy()
    for i, t in turns.items():
        dt = months[i]
        if dt not in net.index:
            continue
        eff_bps = bps
        if impact_k > 0 and aum > 0 and adtv is not None:
            traded_per_name = (aum * t) / max(1, k)
            adv_med = float(np.nanmedian(adtv)) if len(adtv) else 1e12
            part = traded_per_name / max(1.0, adv_med)
            eff_bps = bps + impact_k * np.sqrt(max(0.0, part)) * 1e4
        net.loc[dt] = net.loc[dt] - t * (eff_bps / 10000.0)
    mg, mn = PB.metrics(gross), PB.metrics(net)
    return mg, mn


def run(fund_csv="fundamentals_pit.csv", prices_csv="kospi_monthly_prices.csv",
        k=18, aum=19000000, liq_csv="liquidity_sector.csv", warmup=12):
    fund = pd.read_csv(fund_csv, dtype={"code": str}); fund["code"] = fund["code"].str.zfill(6)
    prices = pd.read_csv(prices_csv, index_col=0, parse_dates=True)
    prices.columns = [str(c).zfill(6) for c in prices.columns]
    pf = PB.piotroski(fund)
    years = max(1e-9, len(prices.index) / 12.0)

    adtv18 = None
    if os.path.exists(liq_csv):
        liq = pd.read_csv(liq_csv, dtype={"code": str}); liq["code"] = liq["code"].str.zfill(6)
        adtv18 = liq[liq["code"].isin([c.zfill(6) for c in PB.FIXED18])]["adtv"].dropna().values

    score_cache, months = precompute_scores(prices, pf, warmup)

    base = {}
    holds = {}
    for step, lab in FREQS:
        hold, turns = hold_and_turns(months, score_cache, k, step, warmup)
        holds[step] = (hold, turns)
        mg, mn = net_metrics(prices, hold, turns, months, 30.0, k=k)
        ann_turn = sum(turns.values()) / years
        base[step] = dict(lab=lab, grossCAGR=mg.get("CAGR", 0), netCAGR=mn.get("CAGR", 0),
                          Sharpe=mn.get("Sharpe", 0), turn=ann_turn)

    sweep = {}
    for bps in COST_SWEEP_BPS:
        row = {}
        for step, lab in FREQS:
            hold, turns = holds[step]
            _, mn = net_metrics(prices, hold, turns, months, float(bps), k=k)
            row[step] = mn.get("CAGR", 0)
        sweep[bps] = row

    impact_info = None
    if adtv18 is not None and len(adtv18):
        hold_m, turns_m = holds[1]
        avg_t = np.mean(list(turns_m.values())) if turns_m else 0.0
        traded_per_name = (aum * avg_t) / max(1, k)
        adv_med = float(np.nanmedian(adtv18))
        part = traded_per_name / max(1.0, adv_med)
        impact_bp = 0.1 * np.sqrt(max(0.0, part)) * 1e4
        impact_info = dict(avg_turn_per_rebal=avg_t, traded_per_name=traded_per_name,
                           adv_med=adv_med, participation=part, impact_bp=impact_bp)

    oos = _oos_split(prices, months, score_cache, k, warmup)

    return dict(base=base, sweep=sweep, impact=impact_info, oos=oos, years=years,
                nmonths=len(months), aum=aum)


def _oos_split(prices, months, score_cache, k, warmup, bps=30.0):
    n = len(months)
    bounds = [(warmup, warmup + (n - warmup) // 3),
              (warmup + (n - warmup) // 3, warmup + 2 * (n - warmup) // 3),
              (warmup + 2 * (n - warmup) // 3, n)]
    out = []
    for (a, b) in bounds:
        sub_idx = months[a:b]
        seg = {}
        for step in (1, 3, 12):
            hold, turns = hold_and_turns(months, score_cache, k, step, warmup)
            gross = PB.ew_returns(prices, hold)
            net = gross.copy()
            for i, t in turns.items():
                if months[i] in net.index:
                    net.loc[months[i]] = net.loc[months[i]] - t * (bps / 10000.0)
            idx = net.index.intersection(sub_idx)
            seg_net = net.loc[idx]
            cagr = (1 + seg_net).prod() ** (12.0 / max(1, len(seg_net))) - 1
            seg[step] = cagr
        out.append((str(sub_idx[0].date()), str(sub_idx[-1].date()), seg))
    return out


def _fmt(run_out):
    L = []
    L.append("=" * 78)
    L.append(f"회전율(리밸런스 주기) ↔ 순수익 탐색 — K=18, {run_out['nmonths']}개월, 선형비용 30bp")
    L.append("=" * 78)
    L.append(f"{'주기':<6}{'총CAGR':>9}{'순CAGR':>9}{'Sharpe':>8}{'연회전율':>9}")
    for step in (1, 2, 3, 4, 6, 12):
        r = run_out["base"][step]
        L.append(f"{r['lab']:<6}{r['grossCAGR']*100:>8.1f}%{r['netCAGR']*100:>8.1f}%"
                 f"{r['Sharpe']:>8.2f}{r['turn']*100:>8.0f}%")
    L.append("")
    L.append("[비용 스윕] 비용↑ — 월간이 분기에 추월당하는 손익분기 cost 탐색")
    L.append(f"{'cost(bp)':<9}{'월간':>8}{'격월':>8}{'분기':>8}{'반기':>8}{'연간':>8}  최적")
    best_flip = None
    for bps in COST_SWEEP_BPS:
        row = run_out["sweep"][bps]
        best_step = max(row, key=row.get)
        best_lab = {1: "월간", 2: "격월", 3: "분기", 4: "4개월", 6: "반기", 12: "연간"}[best_step]
        if best_step != 1 and best_flip is None:
            best_flip = bps
        L.append(f"{bps:<9}{row[1]*100:>7.1f}%{row[2]*100:>7.1f}%{row[3]*100:>7.1f}%"
                 f"{row[6]*100:>7.1f}%{row[12]*100:>7.1f}%  {best_lab}")
    margin = f"{best_flip/30:.1f}x" if best_flip else ">16x"
    L.append(f"  → 월간이 1위를 내주는 첫 비용 = {best_flip if best_flip else '>500'}bp "
             f"(진우 현실비용 ~30bp 대비 안전마진 {margin})")
    L.append("")
    if run_out["impact"]:
        im = run_out["impact"]
        L.append(f"[진우 계좌 시장충격] AUM {run_out['aum']:,.0f}원, 월간 평균회전 {im['avg_turn_per_rebal']*100:.0f}%/리밸")
        L.append(f"  종목당 거래 ≈ {im['traded_per_name']:,.0f}원 / 보유18 중앙 ADTV {im['adv_med']:,.0f}원")
        L.append(f"  참여율 = {im['participation']*100:.4f}%  → 제곱근충격 bp ≈ {im['impact_bp']:.3f}bp (사실상 0)")
    L.append("")
    L.append("[OOS 3분할] 구간별 순CAGR (월간/분기/연간, 30bp) — 단일기간 우연 아닌지")
    for (s, e, seg) in run_out["oos"]:
        L.append(f"  {s}~{e}: 월간 {seg[1]*100:>6.1f}% / 분기 {seg[3]*100:>6.1f}% / 연간 {seg[12]*100:>6.1f}%")
    return "\n".join(L)


def _selftest():
    np.random.seed(7)
    Tm, K = 60, 20
    idx = pd.date_range("2020-01-31", periods=Tm, freq="ME")
    codes = [f"{i:06d}" for i in range(K)]
    drift = np.linspace(0.02, 0.10, K)
    px = pd.DataFrame(index=idx, columns=codes, dtype=float)
    for j, c in enumerate(codes):
        r = np.random.normal(drift[j] / 12, 0.05, Tm)
        px[c] = 100 * np.cumprod(1 + r)
    rows = []
    for yr in range(2018, 2026):
        for j, c in enumerate(codes):
            g = 1.0 + 0.03 * (yr - 2018)
            assets = 1e9 * (1 + 0.1 * j)
            rev = 8e8 * (1 + 0.1 * j) * g
            ni = rev * (0.05 + 0.005 * (j % 5))
            rows.append(dict(code=c, fiscal_year=yr, revenue=rev, cogs=rev * 0.7,
                             op_income=ni * 1.2, net_income=ni, assets=assets,
                             liabilities=assets * 0.4, equity=assets * 0.6,
                             current_assets=assets * 0.5, current_liab=assets * 0.2,
                             cash=assets * 0.1, cfo=ni * 1.1,
                             noncurrent_liab=assets * 0.2, issued_capital=1e8))
    fund = pd.DataFrame(rows)
    px.to_csv("_rte_p.csv"); fund.to_csv("_rte_f.csv", index=False)

    fundd = pd.read_csv("_rte_f.csv", dtype={"code": str}); fundd["code"] = fundd["code"].str.zfill(6)
    pricesd = pd.read_csv("_rte_p.csv", index_col=0, parse_dates=True)
    pricesd.columns = [str(c).zfill(6) for c in pricesd.columns]
    pf = PB.piotroski(fundd)

    cache, months = precompute_scores(pricesd, pf, warmup=12)
    mkt = pricesd.pct_change().mean(axis=1); fcols = list(pricesd.columns)
    for i in (13, 20, 30):
        direct = PB.score_at(i, list(months), pricesd, mkt, fcols, pf, months[i].year)
        assert list(cache[i].index) == list(direct.index), f"캐시!=직접 @i={i}"
    print("[OK] 점수 캐시 == score_at 직접호출 (동치성)")

    turns_by = {}
    for step in (1, 3, 12):
        _, tr = hold_and_turns(months, cache, 15, step, 12)
        turns_by[step] = sum(tr.values()) / (Tm / 12.0)
    assert turns_by[1] >= turns_by[3] >= turns_by[12], f"회전율 비단조: {turns_by}"
    print(f"[OK] 회전율 단조 (월{turns_by[1]*100:.0f}>=분{turns_by[3]*100:.0f}>=연{turns_by[12]*100:.0f}%)")

    hold, turns = hold_and_turns(months, cache, 15, 1, 12)
    _, lo = net_metrics(pricesd, hold, turns, months, 20.0, k=15)
    _, hi = net_metrics(pricesd, hold, turns, months, 200.0, k=15)
    assert lo.get("CAGR", 0) >= hi.get("CAGR", 0), "비용↑인데 순CAGR↑ (역방향)"
    print(f"[OK] 비용 드래그 방향 (20bp {lo['CAGR']*100:.1f}% >= 200bp {hi['CAGR']*100:.1f}%)")

    _, conv = net_metrics(pricesd, hold, turns, months, 30.0, impact_k=0.5,
                          aum=1e12, adtv=np.array([1e9]), k=15)
    _, lin = net_metrics(pricesd, hold, turns, months, 30.0, k=15)
    assert conv.get("CAGR", 0) <= lin.get("CAGR", 0), "볼록충격인데 순CAGR↑"
    print("[OK] 볼록 충격항 방향 (대형AUM 순CAGR <= 선형)")

    for f in ("_rte_p.csv", "_rte_f.csv"):
        try: os.remove(f)
        except OSError: pass
    print("\n[OK] rebalance_turnover_explore self-test 통과 (4/4)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fundamentals", default="fundamentals_pit.csv")
    ap.add_argument("--prices", default="kospi_monthly_prices.csv")
    ap.add_argument("--k", type=int, default=18)
    ap.add_argument("--aum", type=float, default=19000000)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    if not os.path.exists(a.fundamentals):
        raise SystemExit(f"{a.fundamentals} 없음")
    if not os.path.exists(a.prices):
        raise SystemExit(f"{a.prices} 없음")
    out = run(a.fundamentals, a.prices, k=a.k, aum=a.aum)
    print(_fmt(out))
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
