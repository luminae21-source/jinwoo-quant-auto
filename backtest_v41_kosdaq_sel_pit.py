#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest_v41_kosdaq_sel_pit.py — 진우퀀트 v4.1 KOSDAQ 종목선정(kosdaq_sel) · Stage 4 (판정)
PIT 백테스트로 동결 합격선 자동판정. production·C·D·영역3 무수정. 정의는 Stage1~3 모듈 import.
합격선(net, base=MKT): 시장초과≥+3.0%p AND IR≥+0.30 AND Sharpe≥base-0.01 AND MDD비악화.
정직 보조: base=EW(eligible 등가중)도 보고 — MKT만 이기고 EW에 지면 팩터 실력 아님(영역3 교훈).
윈도: realized 월 ≤ 2026-05 (2026-06 진행중 stub 제외). 매월 top-20 EW, 비용 round-trip.
"""
import csv, json, sys, argparse
from build_kosdaq_sel_universe import compute_annual_features, snapshot, _f, NORMAL_BOARDS
from validate_kosdaq_sel_factors import build_factor_ranks
from score_v41_kosdaq_sel import score_codes

N_PICKS = 20
COST_PRIMARY = 0.006
COST_SENS = [0.005, 0.006, 0.007]
END_YM = (2026, 5)
ALPHA_GATE = 3.0
IR_GATE = 0.30
SHARPE_TOL = 0.01
GROWTH_VARIANTS = {"gw1.0": 1.0, "gw0.5": 0.5}


def load_csv(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def parse_ym(s):
    return int(s[:4]), int(s[5:7])


def usable_fy(year, month):
    return year - 1 if month >= 4 else year - 2


def ann_metrics(rets):
    if not rets:
        return None
    cum = 1.0
    for r in rets:
        cum *= (1 + r)
    yrs = len(rets) / 12.0
    cagr = cum ** (1 / yrs) - 1 if yrs > 0 and cum > 0 else None
    mean = sum(rets) / len(rets)
    sd = (sum((r - mean) ** 2 for r in rets) / len(rets)) ** 0.5
    sharpe = (mean / sd) * (12 ** 0.5) if sd > 0 else None
    peak = -1e9; eq = 1.0; mdd = 0.0
    for r in rets:
        eq *= (1 + r); peak = max(peak, eq); mdd = min(mdd, eq / peak - 1)
    return {"CAGR": cagr, "Sharpe": sharpe, "MDD": mdd}


def info_ratio(strat, base):
    ex = [s - b for s, b in zip(strat, base)]
    if not ex:
        return None
    m = sum(ex) / len(ex)
    sd = (sum((e - m) ** 2 for e in ex) / len(ex)) ** 0.5
    return (m / sd) * (12 ** 0.5) if sd > 0 else None


def build_panels(fund_rows, price_rows, factor_rows, liq_rows):
    numcols = ["revenue", "cogs", "op_income", "net_income", "assets", "liabilities",
               "equity", "current_assets", "current_liab", "cash", "cfo",
               "noncurrent_liab", "issued_capital"]
    raw = {}
    for r in fund_rows:
        c = r["code"]
        try:
            y = int(float(r["fiscal_year"]))
        except (ValueError, KeyError, TypeError):
            continue
        raw.setdefault(c, {})[y] = {k: _f(r.get(k)) for k in numcols}
    feats = {c: compute_annual_features(d) for c, d in raw.items()}
    header = price_rows[0]
    dates = [r[0] for r in price_rows[1:]]
    codes = header[1:]
    px = {code: [] for code in codes}
    for r in price_rows[1:]:
        for j, code in enumerate(codes, start=1):
            v = None
            if j < len(r):
                try:
                    v = float(r[j])
                except (ValueError, TypeError):
                    v = None
            px[code].append(v)
    mkt = {}
    for r in factor_rows:
        mkt[r.get("date")] = _f(r.get("MKT"))
    boards = {r["code"]: r.get("sector") for r in liq_rows}
    return feats, dates, px, mkt, boards


def pit_snapshot(feats_c, ufy):
    years, annual = feats_c
    yle = [y for y in years if y <= ufy]
    if ufy not in years or (ufy - 1) not in years:
        return None
    return snapshot(yle, annual)


def run_backtest(feats, dates, px, mkt, boards, adopted, n_picks=N_PICKS, cost=COST_PRIMARY):
    ym = [parse_ym(d) for d in dates]
    idxs = [i for i in range(len(dates) - 1) if i >= 13 and ym[i + 1] <= END_YM]
    series = {v: [] for v in GROWTH_VARIANTS}
    base_mkt = []; base_ew = []; dates_used = []
    prev = {v: set() for v in GROWTH_VARIANTS}
    turn = {v: [] for v in GROWTH_VARIANTS}
    for i in idxs:
        y, m = ym[i]
        ufy = usable_fy(y, m)
        eligible = []; temp = {}; mom = {}
        for c, fc in feats.items():
            if boards.get(c) not in NORMAL_BOARDS or c not in px:
                continue
            p = px[c]
            if i + 1 >= len(p):
                continue
            if None in (p[i], p[i + 1], p[i - 1], p[i - 13]) or p[i - 13] <= 0:
                continue
            snap = pit_snapshot(fc, ufy)
            if snap is None:
                continue
            temp[c] = {"snapshot": snap}
            mom[c] = p[i - 1] / p[i - 13] - 1.0
            eligible.append(c)
        if len(eligible) < n_picks + 5:
            continue
        ranks, _ = build_factor_ranks(temp, eligible, mom)
        fwd = {c: px[c][i + 1] / px[c][i] - 1.0 for c in eligible}
        d_next = dates[i + 1]
        if mkt.get(d_next) is None:
            continue
        for v, gw in GROWTH_VARIANTS.items():
            sc, _s, _a = score_codes(ranks, adopted, eligible, gw)
            top = sorted(eligible, key=lambda c: sc[c], reverse=True)[:n_picks]
            rg = sum(fwd[c] for c in top) / len(top)
            ts = set(top)
            to = len(ts - prev[v]) / n_picks if prev[v] else 1.0
            series[v].append(rg - cost * to); turn[v].append(to); prev[v] = ts
        base_mkt.append(mkt[d_next])
        base_ew.append(sum(fwd[c] for c in eligible) / len(eligible))
        dates_used.append(d_next)
    out = {"window": [dates_used[0], dates_used[-1]] if dates_used else None,
           "months": len(dates_used), "n_picks": n_picks, "cost": cost,
           "base_MKT": ann_metrics(base_mkt), "base_EW": ann_metrics(base_ew)}
    for v in GROWTH_VARIANTS:
        met = ann_metrics(series[v])
        out[v] = {**met, "IR_vs_MKT": info_ratio(series[v], base_mkt),
                  "IR_vs_EW": info_ratio(series[v], base_ew),
                  "avg_turnover": round(sum(turn[v]) / len(turn[v]), 3) if turn[v] else None}
    return out


def verdict(res):
    bm = res["base_MKT"]; be = res["base_EW"]; lines = []; any_pass = False
    for v in GROWTH_VARIANTS:
        s = res[v]
        if s["CAGR"] is None or bm["CAGR"] is None:
            lines.append((v, "N/A", {})); continue
        alpha = (s["CAGR"] - bm["CAGR"]) * 100
        ew_alpha = (s["CAGR"] - be["CAGR"]) * 100
        g1 = alpha >= ALPHA_GATE
        g2 = (s["IR_vs_MKT"] or -9) >= IR_GATE
        g3 = (s["Sharpe"] or -9) >= (bm["Sharpe"] or 0) - SHARPE_TOL
        g4 = (s["MDD"] or -9) >= (bm["MDD"] or -9)
        p = g1 and g2 and g3 and g4
        any_pass = any_pass or p
        lines.append((v, "PASS" if p else "FAIL",
                      {"alpha_vs_MKT_pp": round(alpha, 2), "alpha_vs_EW_pp": round(ew_alpha, 2),
                       "IR_MKT": round(s["IR_vs_MKT"], 3) if s["IR_vs_MKT"] else None,
                       "IR_EW": round(s["IR_vs_EW"], 3) if s["IR_vs_EW"] else None,
                       "Sharpe": round(s["Sharpe"], 3) if s["Sharpe"] else None,
                       "base_Sharpe": round(bm["Sharpe"], 3) if bm["Sharpe"] else None,
                       "MDD": round(s["MDD"], 4) if s["MDD"] else None,
                       "base_MDD": round(bm["MDD"], 4) if bm["MDD"] else None,
                       "gates": {"alpha>=3": g1, "IR>=0.3": g2, "Sharpe_ok": g3, "MDD_ok": g4},
                       "beats_EW": s["CAGR"] > be["CAGR"]}))
    return any_pass, lines


def main_run():
    adopted = json.load(open("validate_kosdaq_sel_factors.json", encoding="utf-8"))["adopted_factors"]
    feats, dates, px, mkt, boards = build_panels(
        load_csv("fundamentals_kosdaq.csv"),
        list(csv.reader(open("kosdaq_monthly_prices.csv", encoding="utf-8-sig"))),
        load_csv("kosdaq_factors.csv"), load_csv("liquidity_kosdaq.csv"))
    res = run_backtest(feats, dates, px, mkt, boards, adopted)
    sens = {}
    for cst in COST_SENS:
        r2 = run_backtest(feats, dates, px, mkt, boards, adopted, cost=cst)
        sens["cost_%.3f" % cst] = {v: {"CAGR": r2[v]["CAGR"], "IR_MKT": r2[v]["IR_vs_MKT"]} for v in GROWTH_VARIANTS}
    any_pass, lines = verdict(res)
    res["sensitivity"] = sens
    res["verdict"] = {"any_pass_vs_MKT": any_pass, "detail": lines,
                      "gate": "vs MKT: alpha>=+3.0%p AND IR>=+0.30 AND Sharpe>=base-0.01 AND MDD non-worse (net)",
                      "honesty_note": "EW base reported; if beats MKT but loses to EW => universe/EW premium, not factor skill."}
    json.dump(res, open("backtest_v41_kosdaq_sel_pit_result.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("=== KOSDAQ 선정 PIT 백테스트 (Stage 4 판정) ===")
    print("윈도 %s | %d개월 | top-%d EW | 비용 %.1f%% net" % (res["window"], res["months"], res["n_picks"], res["cost"] * 100))
    bm, be = res["base_MKT"], res["base_EW"]
    print("base MKT : CAGR %6.2f%% Sharpe %.2f MDD %.1f%%" % (bm["CAGR"] * 100, bm["Sharpe"], bm["MDD"] * 100))
    print("base EW  : CAGR %6.2f%% Sharpe %.2f MDD %.1f%%  <- eligible 등가중(정직 기준)" % (be["CAGR"] * 100, be["Sharpe"], be["MDD"] * 100))
    for v in GROWTH_VARIANTS:
        s = res[v]
        print("%-6s: CAGR %6.2f%% Sharpe %.2f MDD %6.1f%% IR_MKT %.3f IR_EW %.3f turn %s" %
              (v, s["CAGR"] * 100, s["Sharpe"], s["MDD"] * 100, s["IR_vs_MKT"], s["IR_vs_EW"], s["avg_turnover"]))
    print("\n동결 합격선: " + res["verdict"]["gate"])
    for v, vd, det in lines:
        print("  [%s] %s: %s" % (vd, v, det.get("gates", {})))
        print("        a_vs_MKT=%s%%p  a_vs_EW=%s%%p  EW이김=%s  IR_MKT=%s IR_EW=%s" %
              (det.get("alpha_vs_MKT_pp"), det.get("alpha_vs_EW_pp"), det.get("beats_EW"), det.get("IR_MKT"), det.get("IR_EW")))
    ew_win = any(l[2].get("beats_EW") for l in lines if l[2])
    print("\n★ MKT 기준: %s" % ("PASS(>=1변형)" if any_pass else "FAIL(전변형)"))
    print("★ 정직 EW 기준: %s" % ("일부 변형이 EW도 이김" if ew_win else "EW를 못 이김 → 팩터 실력 미입증(보류/기각 권고)"))
    print("출력: backtest_v41_kosdaq_sel_pit_result.json")
    return res


def self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1
        print("  [%s] %s" % ("OK" if c else "FAIL", n)); ok += 1 if c else 0
    chk("무변동 CAGR~0", abs(ann_metrics([0.0] * 12)["CAGR"]) < 1e-9)
    chk("월1% CAGR~12.68%", abs(ann_metrics([0.01] * 24)["CAGR"] - ((1.01 ** 12) - 1)) < 1e-6)
    chk("MDD 음수", ann_metrics([0.1, -0.5, 0.1])["MDD"] < 0)
    chk("usable_fy(2023,3)=2021", usable_fy(2023, 3) == 2021)
    chk("usable_fy(2023,4)=2022", usable_fy(2023, 4) == 2022)
    fake = {"base_MKT": {"CAGR": 0.10, "Sharpe": 0.8, "MDD": -0.20},
            "base_EW": {"CAGR": 0.12, "Sharpe": 0.9, "MDD": -0.18},
            "gw1.0": {"CAGR": 0.14, "Sharpe": 0.85, "MDD": -0.18, "IR_vs_MKT": 0.5, "IR_vs_EW": 0.3},
            "gw0.5": {"CAGR": 0.105, "Sharpe": 0.7, "MDD": -0.25, "IR_vs_MKT": 0.1, "IR_vs_EW": -0.2}}
    ap, ln = verdict(fake)
    chk("gw1.0 MKT-PASS", [l for l in ln if l[0] == "gw1.0"][0][1] == "PASS")
    chk("gw0.5 FAIL", [l for l in ln if l[0] == "gw0.5"][0][1] == "FAIL")
    chk("gw1.0 beats_EW=True", [l for l in ln if l[0] == "gw1.0"][0][2]["beats_EW"] is True)
    chk("any_pass=True", ap is True)
    print("\nself-test: %d/%d pass" % (ok, tot))
    return ok == tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        sys.exit(0 if self_test() else 1)
    main_run()


if __name__ == "__main__":
    main()
