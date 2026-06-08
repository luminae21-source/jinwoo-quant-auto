#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
rejudge_v41_kosdaq_sel_kq150.py — v4.1 KOSDAQ 선정 재판정 (base에 KOSDAQ150 추가)
진우 결정 ①(2026-06-06): 판정 base를 KOSDAQ150 공식지수로.
팩터·가중치·종목선택은 backtest_v41_kosdaq_sel_pit의 함수를 그대로 import·재사용 = 무수정(fitting 아님).
base만 KOSDAQ150 추가해 3-base(MKT·KOSDAQ150·EW) 동시 비교.

입력: kosdaq150_monthly.csv (date 월말, close, ret)  ← fetch_kosdaq150_v41_kosdaq.py 산출
출력: 콘솔 3-base 표 + 동결 합격선 PASS/FAIL + rejudge_v41_kosdaq_sel_kq150_result.json
무수정: production·C·D·영역3·기존 v41 파일 손대지 않음. 신규 파일.
재현 체크: 재산출 base_MKT/base_EW가 기존 result.json(12.06%/31.41%)과 일치해야 정상.
"""
import csv, json
import backtest_v41_kosdaq_sel_pit as bt


def load_kq150(path="kosdaq150_monthly.csv"):
    d = {}
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        try:
            d[bt.parse_ym(r["date"])] = float(r["ret"])
        except (ValueError, TypeError, KeyError):
            continue
    return d


def run_with_kq(feats, dates, px, mkt, boards, adopted, kq, n_picks=bt.N_PICKS, cost=bt.COST_PRIMARY):
    """backtest_v41_kosdaq_sel_pit.run_backtest 와 동일 루프 + base_kq 정렬 추가 (함수 전부 bt.* 재사용)."""
    ym = [bt.parse_ym(x) for x in dates]
    idxs = [i for i in range(len(dates) - 1) if i >= 13 and ym[i + 1] <= bt.END_YM]
    series = {v: [] for v in bt.GROWTH_VARIANTS}
    base_mkt = []; base_ew = []; base_kq = []; dates_used = []; skipped_kq = 0
    prev = {v: set() for v in bt.GROWTH_VARIANTS}; turn = {v: [] for v in bt.GROWTH_VARIANTS}
    for i in idxs:
        y, m = ym[i]; ufy = bt.usable_fy(y, m)
        eligible = []; temp = {}; mom = {}
        for c, fc in feats.items():
            if boards.get(c) not in bt.NORMAL_BOARDS or c not in px:
                continue
            p = px[c]
            if i + 1 >= len(p):
                continue
            if None in (p[i], p[i + 1], p[i - 1], p[i - 13]) or p[i - 13] <= 0:
                continue
            snap = bt.pit_snapshot(fc, ufy)
            if snap is None:
                continue
            temp[c] = {"snapshot": snap}; mom[c] = p[i - 1] / p[i - 13] - 1.0; eligible.append(c)
        if len(eligible) < n_picks + 5:
            continue
        ranks, _ = bt.build_factor_ranks(temp, eligible, mom)
        fwd = {c: px[c][i + 1] / px[c][i] - 1.0 for c in eligible}
        d_next = dates[i + 1]
        if mkt.get(d_next) is None:
            continue
        yn, mn = ym[i + 1]
        if (yn, mn) not in kq:           # KQ150 해당 월 없으면 정렬 안전 위해 스킵(없을 일 거의 없음)
            skipped_kq += 1; continue
        for v, gw in bt.GROWTH_VARIANTS.items():
            sc, _s, _a = bt.score_codes(ranks, adopted, eligible, gw)
            top = sorted(eligible, key=lambda c: sc[c], reverse=True)[:n_picks]
            rg = sum(fwd[c] for c in top) / len(top); ts = set(top)
            to = len(ts - prev[v]) / n_picks if prev[v] else 1.0
            series[v].append(rg - cost * to); turn[v].append(to); prev[v] = ts
        base_mkt.append(mkt[d_next]); base_ew.append(sum(fwd[c] for c in eligible) / len(eligible))
        base_kq.append(kq[(yn, mn)]); dates_used.append(d_next)
    out = {"window": [dates_used[0], dates_used[-1]], "months": len(dates_used), "cost": cost,
           "skipped_kq_months": skipped_kq,
           "base_MKT": bt.ann_metrics(base_mkt), "base_EW": bt.ann_metrics(base_ew),
           "base_KQ150": bt.ann_metrics(base_kq)}
    for v in bt.GROWTH_VARIANTS:
        met = bt.ann_metrics(series[v])
        out[v] = {**met, "IR_vs_MKT": bt.info_ratio(series[v], base_mkt),
                  "IR_vs_EW": bt.info_ratio(series[v], base_ew),
                  "IR_vs_KQ150": bt.info_ratio(series[v], base_kq),
                  "avg_turnover": round(sum(turn[v]) / len(turn[v]), 3) if turn[v] else None}
    return out


def judge(s, base, ir):
    """동결 합격선: alpha>=+3.0%p AND IR>=+0.30 AND Sharpe>=base-0.01 AND MDD 비악화."""
    a = (s["CAGR"] - base["CAGR"]) * 100
    g1 = a >= bt.ALPHA_GATE
    g2 = (ir or -9) >= bt.IR_GATE
    g3 = (s["Sharpe"] or -9) >= (base["Sharpe"] or 0) - bt.SHARPE_TOL
    g4 = (s["MDD"] or -9) >= (base["MDD"] or -9)
    return a, (g1 and g2 and g3 and g4), {"alpha_pp": round(a, 2), "IR": round(ir, 3) if ir else None,
                                          "g_alpha": g1, "g_IR": g2, "g_Sharpe": g3, "g_MDD": g4}


def main():
    adopted = json.load(open("validate_kosdaq_sel_factors.json", encoding="utf-8"))["adopted_factors"]
    feats, dates, px, mkt, boards = bt.build_panels(
        bt.load_csv("fundamentals_kosdaq.csv"),
        list(csv.reader(open("kosdaq_monthly_prices.csv", encoding="utf-8-sig"))),
        bt.load_csv("kosdaq_factors.csv"), bt.load_csv("liquidity_kosdaq.csv"))
    kq = load_kq150()
    res = run_with_kq(feats, dates, px, mkt, boards, adopted, kq)
    bm, bk, be = res["base_MKT"], res["base_KQ150"], res["base_EW"]
    print("=== KOSDAQ 선정 재판정 — 3-base (KOSDAQ150 추가) ===")
    print("윈도 %s | %d개월 | top-20 EW | 비용 0.6%% net | KQ150 스킵월 %d (picks·팩터=기존 엔진 재사용·무수정)"
          % (res["window"], res["months"], res["skipped_kq_months"]))
    print("재현체크 base_MKT=%.2f%%(기존12.06) base_EW=%.2f%%(기존31.41)" % (bm["CAGR"] * 100, be["CAGR"] * 100))
    print("-" * 64)
    print("base MKT      : CAGR %6.2f%% Sharpe %5.2f MDD %6.1f%%" % (bm["CAGR"] * 100, bm["Sharpe"], bm["MDD"] * 100))
    print("base KOSDAQ150: CAGR %6.2f%% Sharpe %5.2f MDD %6.1f%%   <- 진우 결정① 공식 벤치" % (bk["CAGR"] * 100, bk["Sharpe"], bk["MDD"] * 100))
    print("base EW       : CAGR %6.2f%% Sharpe %5.2f MDD %6.1f%%   <- eligible 등가중(정직 기준)" % (be["CAGR"] * 100, be["Sharpe"], be["MDD"] * 100))
    print("-" * 64)
    res["verdict"] = {}
    for v in bt.GROWTH_VARIANTS:
        s = res[v]
        print("%-6s: CAGR %6.2f%% Sharpe %5.2f MDD %6.1f%% | IR_MKT %5.2f IR_KQ150 %5.2f IR_EW %5.2f"
              % (v, s["CAGR"] * 100, s["Sharpe"], s["MDD"] * 100, s["IR_vs_MKT"], s["IR_vs_KQ150"], s["IR_vs_EW"]))
        aK, pK, dK = judge(s, bk, s["IR_vs_KQ150"])
        aE, pE, dE = judge(s, be, s["IR_vs_EW"])
        res["verdict"][v] = {"vs_KQ150": {"pass": pK, **dK}, "vs_EW": {"pass": pE, **dE},
                             "beats_EW_cagr": s["CAGR"] > be["CAGR"]}
        print("        vs KOSDAQ150: %-4s (a=%+.1f%%p, IR=%.2f, gates a/IR/Sh/MDD=%s%s%s%s)"
              % ("PASS" if pK else "FAIL", aK, s["IR_vs_KQ150"], int(dK["g_alpha"]), int(dK["g_IR"]), int(dK["g_Sharpe"]), int(dK["g_MDD"])))
        print("        vs EW(정직) : %-4s (a=%+.1f%%p, EW이김=%s)" % ("PASS" if pE else "FAIL", aE, s["CAGR"] > be["CAGR"]))
    any_kq = any(res["verdict"][v]["vs_KQ150"]["pass"] for v in bt.GROWTH_VARIANTS)
    any_ew = any(res["verdict"][v]["beats_EW_cagr"] for v in bt.GROWTH_VARIANTS)
    res["summary"] = {"any_pass_vs_KQ150": any_kq, "any_beats_EW": any_ew,
                      "conclusion": ("팩터 실력 미입증(EW 미달) — KQ150-pass는 EW/소형 프리미엄 아티팩트"
                                     if (any_kq and not any_ew) else
                                     ("EW도 이김 — 실력 후보" if any_ew else "전부 미달"))}
    json.dump(res, open("rejudge_v41_kosdaq_sel_kq150_result.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("=" * 64)
    print("★ KOSDAQ150 기준: %s" % ("PASS(>=1변형)" if any_kq else "FAIL"))
    print("★ 정직 EW 기준 : %s" % ("일부 EW 이김" if any_ew else "EW 미달 → 팩터 실력 미입증"))
    print("→ 결론: %s" % res["summary"]["conclusion"])
    print("출력: rejudge_v41_kosdaq_sel_kq150_result.json")


if __name__ == "__main__":
    main()
