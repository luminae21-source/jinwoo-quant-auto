#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
universe_market_relative.py — §7-3 KOSPI/KOSDAQ 시장-상대 분리 스크린 + 판정 백테스트
==============================================================================
(OPUS48 핸드오프 06-03 §7-3 설계 구현. 진우 인사이트: 시총분포가 다른 두 시장을
pool해 단일 랭크로 보면 KOSDAQ가 통째로 밀림 → 시장별 분리 랭크 + KOSDAQ carve-in)

1) 시장별 분리 스크리닝 — PB.score_at을 시장별 부분집합(가격·자기시장 EW·시장 내
   분위수)으로 각각 실행 (kosdaq_relative_screen의 '다음 단계' = 진짜 시장-상대 점수)
2) KOSDAQ carve-in — KOSDAQ 내 시총 top-50 ∩ ADTV 상위 50%만 후보 (마이크로캡 배제)
3) 결합 — 최종 universe 30 = KOSPI 룰셋 (30−q) + carve-in KOSDAQ q (변형: q=2, q=4)

모드:
  screen   (기본) 최신월 제안 리스트 — 가드레일(시총·유동성·F·비악화·섹터cap) 적용
  --validate  판정 백테스트 — pooled top-30 vs MR 28+2 vs MR 26+4 (연1회 5월 PIT 로테이션)
              ※ 동시점 병행 실행 비교 (D의 교훈: 절대값 참조 게이트 금지).
              ※ 시총·ADTV 가드레일은 '현재' 스냅샷 → 백테스트 미적용 (look-ahead 방지).
                백테스트는 점수 + 정적 시장라벨만 사용. 가드레일은 운용(제안) 단계 전용.
  --selftest

입력: fundamentals_pit.csv + kospi_monthly_prices.csv(합본 584종목)
      + liquidity_sector.csv(KOSPI) + liquidity_kosdaq.csv
market_map.csv 없으면 liquidity 파일로 자동 생성 (FDR 불필요 — 샌드박스 실행 가능)
원칙: production·기존 산출물 무수정(신규 파일). 합격선은 결정메모 사전 등록 후 변경 금지.
의존성: numpy, pandas, pit_universe_backtest.py, sweep_universe_size.py(_ir 재사용),
        universe_rules.py(_latest_two 재사용)
"""
import argparse, os, sys, json, datetime
import numpy as np, pandas as pd
import pit_universe_backtest as PB
import sweep_universe_size as SW
import universe_rules as UR

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MAP = "market_map.csv"
LIQ_KOSPI, LIQ_KOSDAQ = "liquidity_sector.csv", "liquidity_kosdaq.csv"

# ---- 사전 등록 파라미터 (영역3 universe확정 결정메모 — 등록 후 변경 금지) ----
K_TOTAL = 30
VARIANTS = {"MR_28+2": 2, "MR_26+4": 4}      # KOSDAQ 슬롯 q (변형 2개만, 추가 금지)
PIOTROSKI_MIN = 6                             # universe_rules와 동일
KOSPI_SIZE_TOP, KOSPI_LIQ_PCT = 200, 0.60     # KOSPI 내 시총 top-200 ∩ ADTV 상위 60%
KOSDAQ_SIZE_TOP, KOSDAQ_LIQ_PCT = 50, 0.50    # KOSDAQ carve-in: 시총 top-50 ∩ ADTV 상위 50%
SECTOR_CAP_KOSPI, SECTOR_CAP_KOSDAQ = 3, 2
MIN_MONTHS = 12
GATE_IR_TOL = 0.02    # 채택: MR IR ≥ pooled30 IR − 0.02 (동시점 병행 실행 기준)
GATE_MDD_TOL = 0.02   # AND MR MDD 악화 ≤ +2.0%p


# ---------- market map (FDR 불필요) ----------
def build_market_map(liq_kospi=LIQ_KOSPI, liq_kosdaq=LIQ_KOSDAQ, out=MAP, force=False):
    if os.path.exists(out) and not force:
        m = pd.read_csv(out, dtype=str)
        return dict(zip(m["code"].str.zfill(6), m["market"]))
    mp = {}
    if os.path.exists(liq_kosdaq):
        d = pd.read_csv(liq_kosdaq, dtype={"code": str})
        for c in d["code"].dropna():
            mp[str(c).zfill(6)] = "KOSDAQ"
    if os.path.exists(liq_kospi):
        d = pd.read_csv(liq_kospi, dtype={"code": str})
        for c in d["code"].dropna():
            mp[str(c).zfill(6)] = "KOSPI"        # 겹치면 KOSPI 우선 (kosdaq_relative_screen 컨벤션)
    pd.DataFrame(sorted(mp.items()), columns=["code", "market"]).to_csv(out, index=False, encoding="utf-8-sig")
    nK = sum(1 for v in mp.values() if v == "KOSPI"); nQ = len(mp) - nK
    print(f"{out} 생성: {len(mp)}종목 (KOSPI {nK} / KOSDAQ {nQ}) — liquidity 파일 기반")
    return mp


def _load_liq_table(path):
    if not os.path.exists(path):
        return None
    d = pd.read_csv(path, dtype={"code": str})
    d["code"] = d["code"].str.zfill(6)
    d = d.drop_duplicates("code").set_index("code")
    d["size_rank"] = d["mcap"].rank(ascending=False)
    d["adtv_pct"] = d["adtv"].rank(pct=True)     # 1 = 거래대금 최상
    return d


def _market_scores(idx, months, prices, pf, year, cols):
    """시장-상대 점수: 가격·EW시장·분위수 전부 해당 시장 부분집합 기준."""
    if not cols:
        return pd.Series(dtype=float)
    sub = prices[cols]
    mret = sub.pct_change().mean(axis=1)
    return PB.score_at(idx, list(months), sub, mret, list(cols), pf, year)


def _load_inputs(fund_csv, prices_csv, mp):
    fund = pd.read_csv(fund_csv, dtype={"code": str}); fund["code"] = fund["code"].str.zfill(6)
    prices = pd.read_csv(prices_csv, index_col=0, parse_dates=True)
    prices.columns = [str(c).zfill(6) for c in prices.columns]
    cols_by_mkt = {m: [c for c in prices.columns if mp.get(c) == m] for m in ("KOSPI", "KOSDAQ")}
    unknown = [c for c in prices.columns if mp.get(c) not in ("KOSPI", "KOSDAQ")]
    return fund, prices, cols_by_mkt, unknown


# ---------- screen (최신월 제안 — 가드레일 적용) ----------
def screen(fund_csv="fundamentals_pit.csv", prices_csv="kospi_monthly_prices.csv",
           liq_kospi=LIQ_KOSPI, liq_kosdaq=LIQ_KOSDAQ, map_csv=MAP, save=True):
    mp = build_market_map(liq_kospi, liq_kosdaq, map_csv)
    fund, prices, cols_by_mkt, unknown = _load_inputs(fund_csv, prices_csv, mp)
    pf = PB.piotroski(fund)
    months = prices.index; idx = len(months) - 1; yr = months[idx].year
    F = (pf[pf.fiscal_year == yr - 1].set_index("code")["F"]
         if (pf.fiscal_year == yr - 1).any() else pf.groupby("code")["F"].last())
    det = UR._latest_two(fund)
    persist = prices.notna().sum()
    liq = {"KOSPI": _load_liq_table(liq_kospi), "KOSDAQ": _load_liq_table(liq_kosdaq)}
    size_top = {"KOSPI": KOSPI_SIZE_TOP, "KOSDAQ": KOSDAQ_SIZE_TOP}
    liq_pct = {"KOSPI": KOSPI_LIQ_PCT, "KOSDAQ": KOSDAQ_LIQ_PCT}
    cap = {"KOSPI": SECTOR_CAP_KOSPI, "KOSDAQ": SECTOR_CAP_KOSDAQ}

    nm, sec = {}, {}
    for m in ("KOSPI", "KOSDAQ"):
        t = liq[m]
        if t is not None:
            if "name" in t: nm.update(t["name"].dropna().to_dict())
            if "sector" in t: sec.update(t["sector"].dropna().to_dict())
    def lbl(c): return f"{c}({nm.get(c, '?')})"

    scores, ok_pool = {}, {}
    for m in ("KOSPI", "KOSDAQ"):
        sc = _market_scores(idx, months, prices, pf, yr, cols_by_mkt[m])
        scores[m] = sc
        t = liq[m]
        pool, sec_cnt = [], {}
        for c in sc.index:
            if float(F.get(c, 0)) < PIOTROSKI_MIN: continue
            if det.get(c, {}).get("deteriorated", True): continue
            if persist.get(c, 0) < MIN_MONTHS: continue
            if t is not None:
                if not (t["size_rank"].get(c, 9e9) <= size_top[m]): continue
                if not (t["adtv_pct"].get(c, 0) >= 1 - liq_pct[m]): continue
            s = sec.get(c)
            if s and sec_cnt.get(s, 0) >= cap[m]: continue
            pool.append(c)
            if s: sec_cnt[s] = sec_cnt.get(s, 0) + 1
        ok_pool[m] = pool

    print("=" * 74)
    print(f"시장-상대 분리 스크린 — 제안 ({months[idx].date()}) | 후보 KOSPI {len(scores['KOSPI'])} / "
          f"KOSDAQ {len(scores['KOSDAQ'])} / 라벨없음 {len(unknown)}")
    print(f"가드레일: F≥{PIOTROSKI_MIN}·비악화·{MIN_MONTHS}개월↑ | KOSPI 시총top{KOSPI_SIZE_TOP}∩ADTV상위{KOSPI_LIQ_PCT:.0%}·섹터≤{SECTOR_CAP_KOSPI} "
          f"| KOSDAQ 시총top{KOSDAQ_SIZE_TOP}∩ADTV상위{KOSDAQ_LIQ_PCT:.0%}·섹터≤{SECTOR_CAP_KOSDAQ}")
    print("=" * 74)

    rows = []
    proposals = {}
    for vname, q in VARIANTS.items():
        nQ = min(q, len(ok_pool["KOSDAQ"])); nK = K_TOTAL - nQ
        picks = [("KOSPI", c) for c in ok_pool["KOSPI"][:nK]] + [("KOSDAQ", c) for c in ok_pool["KOSDAQ"][:nQ]]
        proposals[vname] = [c for _, c in picks]
        print(f"\n[{vname}] KOSPI {nK} + KOSDAQ {nQ}")
        for m, c in picks:
            r = int(scores[m].index.get_loc(c)) + 1
            rows.append(dict(variant=vname, market=m, code=c, name=nm.get(c, ""),
                             sector=sec.get(c, ""), mkt_rank=r, F=float(F.get(c, np.nan))))
            print(f"  {m:6} r{r:<4} F{F.get(c, np.nan):>3.0f}  {lbl(c)}  [{sec.get(c, '?')}]")

    print("\n[현 18종목 — 시장-상대 위치] (pool 랭크 왜곡 교정 후)")
    for c in PB.FIXED18:
        m = mp.get(c, "?")
        sc = scores.get(m, pd.Series(dtype=float))
        if c in getattr(sc, "index", []):
            r = int(sc.index.get_loc(c)) + 1
            inn = "←제안권" if c in set(proposals.get("MR_26+4", [])) else ""
            print(f"  {m:6} r{r}/{len(sc)}  {lbl(c)} {inn}")
        else:
            print(f"  {m:6} 점수없음  {lbl(c)}")

    if save and rows:
        ts = datetime.datetime.now().strftime("%Y%m%d")
        out = f"universe_mr_proposal_{ts}.csv"
        pd.DataFrame(rows).to_csv(out, index=False, encoding="utf-8-sig")
        print(f"\n저장: {out}")
    return proposals, scores


# ---------- validate (판정 백테스트 — 동시점 병행 실행) ----------
def _mr_hold(months, prices, pf, cols_by_mkt, q, k_total=K_TOTAL):
    """연 1회(5월) 시장-상대 로테이션. KOSDAQ 후보 부족 시 부족분은 KOSPI 차순위로 충원(K 고정)."""
    subK = prices[cols_by_mkt["KOSPI"]]; mretK = subK.pct_change().mean(axis=1)
    subQ = prices[cols_by_mkt["KOSDAQ"]]; mretQ = subQ.pct_change().mean(axis=1)
    hold, cur, turns, qfill = {}, [], [], []
    for i, dt in enumerate(months):
        if dt.month == 5 and i >= 12:
            scK = PB.score_at(i, list(months), subK, mretK, list(subK.columns), pf, dt.year)
            scQ = PB.score_at(i, list(months), subQ, mretQ, list(subQ.columns), pf, dt.year)
            nQ = min(q, len(scQ)); nK = min(k_total - nQ, len(scK))
            if nK + nQ >= max(10, k_total // 2):
                new = list(scK.head(nK).index) + list(scQ.head(nQ).index)
                if cur: turns.append(len(set(new) ^ set(cur)) / (2.0 * k_total))
                cur = new; qfill.append(nQ)
        hold[i] = cur
    return hold, (float(np.mean(turns)) if turns else 0.0), qfill


def validate(fund_csv="fundamentals_pit.csv", prices_csv="kospi_monthly_prices.csv",
             liq_kospi=LIQ_KOSPI, liq_kosdaq=LIQ_KOSDAQ, map_csv=MAP, save=True):
    mp = build_market_map(liq_kospi, liq_kosdaq, map_csv)
    fund, prices, cols_by_mkt, unknown = _load_inputs(fund_csv, prices_csv, mp)
    pf = PB.piotroski(fund)
    months = prices.index
    pool_cols = cols_by_mkt["KOSPI"] + cols_by_mkt["KOSDAQ"]
    pool_px = prices[pool_cols]
    mkt_ret = pool_px.pct_change().mean(axis=1)

    holds, turns, extra = {}, {}, {}
    h, t = SW._pit_hold_for_k(months, pool_px, mkt_ret, pool_cols, pf, K_TOTAL)
    holds["pooled_top30"], turns["pooled_top30"] = h, t
    for vname, q in VARIANTS.items():
        h, t, qfill = _mr_hold(months, prices, pf, cols_by_mkt, q)
        holds[vname], turns[vname] = h, t
        extra[vname] = {"kosdaq_slots_filled": qfill}
    fixed = [c for c in PB.FIXED18 if c in prices.columns]
    if fixed:                       # selftest(합성 코드)에선 생략
        holds["fixed18"] = {i: fixed for i in range(len(months))}
        turns["fixed18"] = 0.0

    rets = {k: PB.ew_returns(prices, h) for k, h in holds.items()}
    common = mkt_ret.dropna().index
    for r in rets.values():
        common = common.intersection(r.index)
    res = {}
    for k, r in rets.items():
        rr = r.reindex(common)
        m = PB.metrics(rr)
        m["IR"] = SW._ir(rr, mkt_ret.reindex(common))
        m["turnover_yr"] = turns[k]
        res[k] = m
    mm = PB.metrics(mkt_ret.reindex(common)); mm["IR"] = 0.0; mm["turnover_yr"] = np.nan
    res["market_EW"] = mm

    print("=" * 74)
    print(f"판정 백테스트 (동시점 병행 실행) | {common[0].date()}~{common[-1].date()} {len(common)}개월 | "
          f"후보 KOSPI {len(cols_by_mkt['KOSPI'])}/KOSDAQ {len(cols_by_mkt['KOSDAQ'])}/제외(라벨없음) {len(unknown)}")
    print("=" * 74)
    print(f"{'전략':16}{'CAGR':>9}{'Sharpe':>8}{'MDD':>9}{'IR':>7}{'연회전율':>9}")
    order = ["pooled_top30"] + list(VARIANTS) + (["fixed18"] if "fixed18" in res else []) + ["market_EW"]
    for k in order:
        m = res[k]
        print(f"{k:16}{m.get('CAGR', 0):>8.1%}{m.get('Sharpe', 0):>8.2f}{m.get('MDD', 0):>8.1%}"
              f"{m.get('IR', 0):>7.2f}{(m.get('turnover_yr') if m.get('turnover_yr') == m.get('turnover_yr') else 0):>9.0%}")
    for vname in VARIANTS:
        qf = extra[vname]["kosdaq_slots_filled"]
        print(f"  {vname}: KOSDAQ 슬롯 충원 이력 {qf} (리밸 {len(qf)}회)")

    # ---- 사전 등록 게이트 (동시점 비교) ----
    base = res["pooled_top30"]
    verdict = {}
    print(f"\n[사전 등록 게이트] MR IR ≥ pooled IR−{GATE_IR_TOL} AND MDD 악화 ≤ +{GATE_MDD_TOL:.0%}p")
    for vname in VARIANTS:
        m = res[vname]
        ok_ir = m["IR"] >= base["IR"] - GATE_IR_TOL
        ok_mdd = m["MDD"] >= base["MDD"] - GATE_MDD_TOL
        verdict[vname] = bool(ok_ir and ok_mdd)
        print(f"  {vname}: IR {m['IR']:.2f} vs {base['IR']:.2f} ({'✅' if ok_ir else '❌'}) | "
              f"MDD {m['MDD']:.1%} vs {base['MDD']:.1%} ({'✅' if ok_mdd else '❌'}) → "
              f"{'PASS' if verdict[vname] else 'FAIL'}")
    passed = [v for v in VARIANTS if verdict[v]]
    if passed:
        pick = max(passed, key=lambda v: res[v]["IR"])
        print(f"→ 채택 후보: {pick} (통과 변형 중 IR 최대; 동률 시 단순함 우선=28+2)")
    else:
        print("→ 두 변형 모두 FAIL → pooled top-30 유지, KOSDAQ는 관찰 트랙 (재시험·슬롯 튜닝 금지)")

    if save:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        out = f"universe_mr_validate_{ts}.json"
        with open(out, "w", encoding="utf-8") as fh:
            json.dump({"ts": ts, "window": [str(common[0].date()), str(common[-1].date()), len(common)],
                       "params": {"K_TOTAL": K_TOTAL, "variants": VARIANTS,
                                  "gate_ir_tol": GATE_IR_TOL, "gate_mdd_tol": GATE_MDD_TOL},
                       "results": {k: {kk: (None if vv != vv else vv) for kk, vv in m.items()}
                                   for k, m in res.items()},
                       "kosdaq_slots": {v: extra[v]["kosdaq_slots_filled"] for v in VARIANTS},
                       "verdict": verdict}, fh, ensure_ascii=False, indent=2)
        print(f"저장: {out}")
    return res, verdict


# ---------- selftest ----------
def _selftest():
    rng = np.random.default_rng(7)
    Tm = 54; idx = pd.date_range("2021-01-31", periods=Tm, freq="ME")
    kospi = [f"1{i:05d}" for i in range(36)]; kosdaq = [f"2{i:05d}" for i in range(18)]
    goodK = set(kospi[:8]); goodQ = set(kosdaq[:4])
    px = pd.DataFrame(index=idx, columns=kospi + kosdaq, dtype=float)
    for c in kospi + kosdaq:
        dr = 0.030 if c in goodK else 0.020 if c in goodQ else 0.003
        px[c] = 1000 * np.cumprod(1 + rng.normal(dr, 0.06, Tm))
    fr = []
    for c in kospi + kosdaq:
        good = c in (goodK | goodQ)
        for k, fy in enumerate(range(2019, 2026)):
            g = (1 + 0.08 * k) if good else 1.0
            fr.append(dict(code=c, fiscal_year=fy,
                           revenue=1e9 * g, cogs=(5.5e8 * g * (1 - 0.02 * k)) if good else 6.9e8,
                           op_income=2e8 * g if good else -4e6,
                           net_income=2e8 * g if good else -1e7,
                           assets=5e9 * (1 + 0.04 * k), liabilities=2e9, equity=3e9,
                           current_assets=2e9 * (1 + 0.03 * k), current_liab=1e9 * (1 - 0.01 * k) if good else 1e9,
                           cash=5e8, cfo=2.6e8 * g if good else -5e6,
                           noncurrent_liab=(1e9 * (1 - 0.05 * k)) if good else 1.2e9,
                           issued_capital=1e8 if good else 1e8 * (1 + 0.05 * k)))
    pd.DataFrame(fr).to_csv("_umr_f.csv", index=False); px.to_csv("_umr_p.csv")
    # 유동성: KOSDAQ good 중 1개(트랩)는 ADTV 바닥 → carve-in에서 걸러져야 함
    trap = kosdaq[3]
    lk = pd.DataFrame({"code": kospi, "name": [f"코{i}" for i in range(36)],
                       "sector": (["반도체"] * 6 + ["금융"] * 6 + ["기타"] * 24),
                       "mcap": [1e13 - 1e9 * i for i in range(36)], "adtv": [5e11] * 36})
    lq = pd.DataFrame({"code": kosdaq, "name": [f"닥{i}" for i in range(18)],
                       "sector": ["바이오", "게임"] * 9,    # 섹터 cap(2)이 우량 3개를 막지 않도록 분산
                       "mcap": [1e12 - 1e9 * i for i in range(18)],
                       "adtv": [3e10 if c != trap else 1e6 for c in kosdaq]})
    lk.to_csv("_umr_lk.csv", index=False); lq.to_csv("_umr_lq.csv", index=False)
    try:
        mp = build_market_map("_umr_lk.csv", "_umr_lq.csv", "_umr_map.csv", force=True)
        assert mp[kospi[0]] == "KOSPI" and mp[kosdaq[0]] == "KOSDAQ", "market map 분류 오류"
        props, scores = screen("_umr_f.csv", "_umr_p.csv", "_umr_lk.csv", "_umr_lq.csv", "_umr_map.csv", save=False)
        for vname, q in VARIANTS.items():
            picks = props[vname]
            qq = [c for c in picks if c.startswith("2")]
            assert len(qq) == min(q, 3), f"{vname}: KOSDAQ 슬롯 {len(qq)} ≠ {q} (트랩 제외 후 3개 한도)"
            assert all(c in goodQ for c in qq), f"{vname}: KOSDAQ 비우량 편입 {qq}"
            assert trap not in picks, "ADTV 트랩이 carve-in을 통과함 (유동성 필터 미작동)"
        # 섹터 cap: KOSPI 반도체 6 우량 → cap 3 작동
        semi = [c for c in props["MR_28+2"] if c in set(kospi[:6])]
        assert len(semi) <= SECTOR_CAP_KOSPI, "KOSPI 섹터 cap 미작동"
        res, verdict = validate("_umr_f.csv", "_umr_p.csv", "_umr_lk.csv", "_umr_lq.csv", "_umr_map.csv", save=False)
        for v in VARIANTS:
            assert res[v].get("n", 0) >= 24, "백테스트 표본 부족"
            assert res[v]["CAGR"] > res["market_EW"]["CAGR"], "MR이 우량 로테이션인데 시장EW 미달"
        print("\n[OK] universe_market_relative selftest 통과 "
              "(map·시장상대점수·carve-in 유동성트랩·섹터cap·슬롯충원·병행 백테스트)")
        return 0
    finally:
        for x in ("_umr_f.csv", "_umr_p.csv", "_umr_lk.csv", "_umr_lq.csv", "_umr_map.csv"):
            try: os.remove(x)
            except OSError: pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fundamentals", default="fundamentals_pit.csv")
    ap.add_argument("--prices", default="kospi_monthly_prices.csv")
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    for f in (a.fundamentals, a.prices):
        if not os.path.exists(f):
            raise SystemExit(f"{f} 없음 — RUN 가이드 참조 (fetch는 PC 전용)")
    if a.validate:
        validate(a.fundamentals, a.prices)
    else:
        screen(a.fundamentals, a.prices)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
