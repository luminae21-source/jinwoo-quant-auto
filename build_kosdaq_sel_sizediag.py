#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_kosdaq_sel_sizediag.py — v4.1 kosdaq_sel Stage4 후속 '진단 1회' (재튜닝 아님).
질문: gw0.5 선택(20.89%)이 eligible EW(31.41%)에 지는 이유가 '대형 우량 쏠림 → 중소형 랠리 놓침'인가?
방법: 매월 eligible을 mcap 3분위(소/중/대)로 나눠 ① 분위별 EW수익 ② top-20 pick의 분위분포
      ③ EW 견인 상위종목 vs pick빈도 ④ 에코프로비엠 추적. production·C·D·영역3·v41 코드 무수정.
caveat: size=현 mcap 스냅(과거 적용은 근사). 진단용이라 허용, 결론은 방향성만.
"""
import csv, json
from build_kosdaq_sel_universe import compute_annual_features, snapshot, _f, NORMAL_BOARDS
from validate_kosdaq_sel_factors import build_factor_ranks
from score_v41_kosdaq_sel import score_codes
from backtest_v41_kosdaq_sel_pit import build_panels, load_csv, parse_ym, usable_fy, pit_snapshot, ann_metrics, END_YM, N_PICKS

GW = 0.5
WATCH = {"247540": "에코프로비엠"}


def annc(series):
    m = ann_metrics(series)
    return None if not m or m["CAGR"] is None else round(m["CAGR"] * 100, 2)


def main():
    adopted = json.load(open("validate_kosdaq_sel_factors.json", encoding="utf-8"))["adopted_factors"]
    liq = load_csv("liquidity_kosdaq.csv")
    mcap = {r["code"]: _f(r["mcap"]) for r in liq}
    names = {r["code"]: r["name"] for r in liq}
    feats, dates, px, mkt, boards = build_panels(
        load_csv("fundamentals_kosdaq.csv"),
        list(csv.reader(open("kosdaq_monthly_prices.csv", encoding="utf-8-sig"))),
        load_csv("kosdaq_factors.csv"), liq)
    ym = [parse_ym(d) for d in dates]
    idxs = [i for i in range(len(dates) - 1) if i >= 13 and ym[i + 1] <= END_YM]
    ter_ret = {"small": [], "mid": [], "large": []}
    pick_ter = {"small": 0, "mid": 0, "large": 0}; pick_tot = 0
    sel_ret = []  # gw0.5 top20 EW 월수익(gross, 진단용)
    cum = {}; elig = {}; pick = {}
    wlog = {c: {"elig": 0, "pick": 0, "pct": []} for c in WATCH}
    for i in idxs:
        y, m = ym[i]; ufy = usable_fy(y, m)
        eligible = []; temp = {}; mom = {}
        for c, fc in feats.items():
            if boards.get(c) not in NORMAL_BOARDS or c not in px or mcap.get(c) is None:
                continue
            p = px[c]
            if i + 1 >= len(p) or None in (p[i], p[i + 1], p[i - 1], p[i - 13]) or p[i - 13] <= 0:
                continue
            s = pit_snapshot(fc, ufy)
            if s is None:
                continue
            temp[c] = {"snapshot": s}; mom[c] = p[i - 1] / p[i - 13] - 1.0; eligible.append(c)
        if len(eligible) < N_PICKS + 5:
            continue
        ranks, _ = build_factor_ranks(temp, eligible, mom)
        fwd = {c: px[c][i + 1] / px[c][i] - 1.0 for c in eligible}
        se = sorted(eligible, key=lambda c: mcap[c])
        n = len(se); t1 = n // 3; t2 = 2 * n // 3
        ter = {c: ("small" if k < t1 else "mid" if k < t2 else "large") for k, c in enumerate(se)}
        for t in ter_ret:
            g = [fwd[c] for c in eligible if ter[c] == t]
            if g:
                ter_ret[t].append(sum(g) / len(g))
        sc, _, _ = score_codes(ranks, adopted, eligible, GW)
        top = sorted(eligible, key=lambda c: sc[c], reverse=True)[:N_PICKS]
        sel_ret.append(sum(fwd[c] for c in top) / len(top))
        for c in top:
            pick_ter[ter[c]] += 1; pick[c] = pick.get(c, 0) + 1
        pick_tot += len(top)
        order = sorted(eligible, key=lambda c: sc[c])
        for k, c in enumerate(order):
            if c in WATCH:
                wlog[c]["pct"].append(round(k / (len(order) - 1), 2))
        for c in eligible:
            elig[c] = elig.get(c, 0) + 1; cum[c] = cum.get(c, 1.0) * (1 + fwd[c])
            if c in WATCH:
                wlog[c]["elig"] += 1
        for c in top:
            if c in WATCH:
                wlog[c]["pick"] += 1

    print("=== size 분해 진단 (gw0.5, 61개월) ===")
    print("① size tercile EW CAGR%:", {t: annc(ter_ret[t]) for t in ter_ret})
    print("   (gw0.5 선택 gross CAGR%%: %s / eligible 전체 EW는 백테스트 31.41)" % annc(sel_ret))
    print("② top-20 pick 분위분포: small %.0f%% / mid %.0f%% / large %.0f%%" %
          (100 * pick_ter["small"] / pick_tot, 100 * pick_ter["mid"] / pick_tot, 100 * pick_ter["large"] / pick_tot))
    cand = [(c, cum[c], elig[c], pick.get(c, 0), mcap[c]) for c in cum if elig[c] >= 18]
    cand.sort(key=lambda t: t[1], reverse=True)
    print("③ EW 견인 상위 12 (보유배수·picked/elig달·mcap):")
    for c, cr, ec, pc, mc in cand[:12]:
        tag = "소형" if mc < 4000e8 else ("중형" if mc < 10000e8 else "대형")
        print("   %-12s x%5.1f  pick%2d/%2d  %5.0f억(%s)" % (names.get(c, c)[:12], cr, pc, ec, mc / 1e8, tag))
    print("④ watch:", {WATCH[c]: {"elig": wlog[c]["elig"], "pick": wlog[c]["pick"],
          "score_pct_mean": round(sum(wlog[c]["pct"]) / len(wlog[c]["pct"]), 2) if wlog[c]["pct"] else None} for c in WATCH})
    json.dump({"tercile_EW_CAGR": {t: annc(ter_ret[t]) for t in ter_ret},
               "sel_gross_CAGR": annc(sel_ret),
               "pick_dist": {k: round(v / pick_tot, 3) for k, v in pick_ter.items()},
               "top_EW_winners": [{"name": names.get(c, c), "mult": round(cr, 2), "pick": pc, "elig": ec,
                                   "mcap_억": round(mc / 1e8)} for c, cr, ec, pc, mc in cand[:15]],
               "watch": {WATCH[c]: wlog[c] for c in WATCH}},
              open("kosdaq_sel_sizediag_result.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print("출력: kosdaq_sel_sizediag_result.json")


if __name__ == "__main__":
    main()
