#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
score_v41_kosdaq_sel.py — 진우퀀트 v4.1 KOSDAQ 종목선정(kosdaq_sel) · Stage 3 (점수엔진)

역할: Stage 2 채택 10팩터로 KOSDAQ 횡단면 점수·등급 산출. 가중은 '사전 등록' a-priori
      (수익에 fitting X = 합격선 먼저 원칙). 등록 변형 = 성장가중 ×0.5 / ×1.0.
      production(KOSPI score_v37_2 계열)·C·D·영역3 무수정. 팩터 정의는 Stage 2 모듈 import(단일화).

입력(로컬): kosdaq_sel_universe_cache.json (Stage1) · validate_kosdaq_sel_factors.json (Stage2 채택셋)
            · kosdaq_monthly_prices.csv (모멘텀)
출력: v41_kosdaq_sel_scores_latest.csv · v41_kosdaq_sel_summary_latest.json

설계(결정메모 §4·§5):
  · 성장 1차축. 축가중(growth_weight=1.0): growth .50 / quality .35 / momentum .15
  · 이익계열(ni_yoy)·안정성(rev_stability)은 축 내 보조가중(0.5). 매출·CFO·CAGR는 1.0
  · 결측 = 중립 rank 0.5 (페널티 금지)
  · 점수 = 축점수 가중합 ×100, 등급 = universe 내 백분위 컷
  · 변형: --growth-weight 1.0(기본) / 0.5  ← Stage4가 둘 다 백테스트해 합격선 판정

사용:
  python score_v41_kosdaq_sel.py --self-test
  python score_v41_kosdaq_sel.py                  # growth_weight=1.0
  python score_v41_kosdaq_sel.py --growth-weight 0.5
"""
import csv, json, sys, argparse
from validate_kosdaq_sel_factors import FACTOR_SPEC, compute_momentum, build_factor_ranks

NEUTRAL = 0.5
AXIS_BASE = {"growth": 0.50, "quality": 0.35, "momentum": 0.15}
# 축 내 팩터 가중(채택셋만 사용). 매출·CFO·CAGR robust=1.0, 이익·안정성 보조=0.5, 퀄리티 동일가중
FACTOR_W = {
    "g_rev_yoy": 1.0, "g_cfo_yoy": 1.0, "g_rev_cagr": 1.0,
    "g_ni_yoy": 0.5, "g_rev_stability": 0.5,
    "q_roa": 1.0, "q_low_accrual": 1.0, "q_low_debt": 1.0, "q_gross_margin": 1.0,
    "m_mom_12_1": 1.0,
}
AXIS_OF = {name: axis for name, axis, key, orient in FACTOR_SPEC}
GRADE_CUTS = [("S+", 0.95), ("S", 0.85), ("A", 0.70), ("B", 0.45), ("C", 0.20), ("D", 0.05), ("F", 0.0)]


def axis_weights(growth_weight, axes_present):
    w = dict(AXIS_BASE)
    w["growth"] *= growth_weight
    w = {a: v for a, v in w.items() if a in axes_present}
    s = sum(w.values()) or 1.0
    return {a: v / s for a, v in w.items()}


def score_codes(ranks, adopted, universe, growth_weight):
    """ranks: {factor:{code:rank}}. 채택 팩터만, 축별 가중평균(결측 0.5), 축가중 합성."""
    members = {}
    for f in adopted:
        members.setdefault(AXIS_OF[f], []).append(f)
    aw = axis_weights(growth_weight, set(members.keys()))
    scores = {}; subs = {}
    for c in universe:
        axis_score = {}
        for axis, fl in members.items():
            num = den = 0.0
            for f in fl:
                w = FACTOR_W.get(f, 1.0)
                r = ranks.get(f, {}).get(c, NEUTRAL)   # 결측 = 중립
                num += w * r; den += w
            axis_score[axis] = num / den if den else NEUTRAL
        comp = sum(aw[a] * axis_score[a] for a in aw)
        scores[c] = comp
        subs[c] = axis_score
    return scores, subs, aw


def assign_grades(scores):
    order = sorted(scores, key=lambda c: scores[c])  # 오름차순
    n = len(order); grade = {}
    for i, c in enumerate(order):
        pct = i / (n - 1) if n > 1 else 1.0
        for g, cut in GRADE_CUTS:
            if pct >= cut:
                grade[c] = g; break
    return grade


def run(cache_path="kosdaq_sel_universe_cache.json",
        factors_path="validate_kosdaq_sel_factors.json",
        price_path="kosdaq_monthly_prices.csv", growth_weight=1.0,
        out_csv="v41_kosdaq_sel_scores_latest.csv",
        out_json="v41_kosdaq_sel_summary_latest.json"):
    cache = json.load(open(cache_path, encoding="utf-8"))
    fac = json.load(open(factors_path, encoding="utf-8"))
    firms = cache["firms"]; universe = cache["universe_latest"]
    adopted = fac["adopted_factors"]
    mom, _ = compute_momentum(price_path, universe)
    ranks, _cov = build_factor_ranks(firms, universe, mom)   # Stage2와 동일 산출(winsor+rank)
    scores, subs, aw = score_codes(ranks, adopted, universe, growth_weight)
    grade = assign_grades(scores)

    rows = []
    for c in universe:
        s = firms[c]["snapshot"]
        rows.append({
            "code": c, "name": firms[c]["name"], "industry": firms[c]["industry"],
            "board": firms[c]["board"],
            "mcap_억": round(firms[c]["mcap"] / 1e8, 1) if firms[c].get("mcap") else None,
            "score": round(scores[c] * 100, 2), "grade": grade[c],
            "growth": round(subs[c].get("growth", NEUTRAL) * 100, 1),
            "quality": round(subs[c].get("quality", NEUTRAL) * 100, 1),
            "momentum": round(subs[c].get("momentum", NEUTRAL) * 100, 1),
            "rev_yoy": s.get("rev_yoy"), "roa": s.get("roa"),
            "mom_12_1": round(mom[c], 4) if c in mom else None,
        })
    rows.sort(key=lambda r: r["score"], reverse=True)

    cols = ["rank", "code", "name", "industry", "board", "mcap_억", "score", "grade",
            "growth", "quality", "momentum", "rev_yoy", "roa", "mom_12_1"]
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(cols)
        for i, r in enumerate(rows, 1):
            w.writerow([i] + [r.get(k) for k in cols[1:]])

    from collections import Counter
    gc = Counter(r["grade"] for r in rows)
    summary = {
        "module": "v4.1 kosdaq_sel · Stage 3 (점수엔진)",
        "growth_weight": growth_weight, "axis_weights": {a: round(v, 3) for a, v in aw.items()},
        "factor_weights": FACTOR_W, "adopted_factors": adopted,
        "universe_n": len(universe), "grade_counts": dict(gc),
        "top15": [{"code": r["code"], "name": r["name"], "score": r["score"], "grade": r["grade"],
                   "g": r["growth"], "q": r["quality"], "m": r["momentum"]} for r in rows[:15]],
        "note": "사전등록 a-priori 가중(fitting X). 선정·수익 판정은 Stage4 PIT 백테스트(등록 합격선).",
    }
    json.dump(summary, open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    print(f"=== KOSDAQ 점수엔진 (Stage 3) · growth_weight={growth_weight} ===")
    print(f"universe N={len(universe)} | 축가중 {summary['axis_weights']}")
    print(f"등급 분포: {dict(gc)}")
    print("상위 15 (sanity — 선정 아님, Stage4가 판정):")
    for i, r in enumerate(rows[:15], 1):
        print(f"  {i:2d}. {r['grade']:2s} {r['score']:5.1f}  {r['name'][:10]:10s} "
              f"[g{r['growth']:.0f}/q{r['quality']:.0f}/m{r['momentum']:.0f}] {r['industry'][:14]}")
    print(f"출력: {out_csv} , {out_json}")
    return rows, summary


# ----------------------- SELF TEST -----------------------
def self_test():
    ok = tot = 0
    def chk(name, cond):
        nonlocal ok, tot; tot += 1
        print(f"  [{'OK' if cond else 'FAIL'}] {name}"); ok += 1 if cond else 0

    adopted = ["g_rev_yoy", "g_cfo_yoy", "g_rev_cagr", "g_ni_yoy", "g_rev_stability",
               "q_roa", "q_low_accrual", "q_low_debt", "q_gross_margin", "m_mom_12_1"]
    uni = [f"{i:06d}" for i in range(20)]
    # 합성 ranks: code0 = 전팩터 최고(1.0), code19 = 전팩터 최저(0.0), 나머지 중간
    ranks = {f: {} for f in adopted}
    for f in adopted:
        for i, c in enumerate(uni):
            ranks[f][c] = 1.0 - i / 19.0
    sc, subs, aw = score_codes(ranks, adopted, uni, 1.0)
    chk("축가중 합=1", abs(sum(aw.values()) - 1.0) < 1e-9)
    chk("성장 1차축(growth>quality>momentum)", aw["growth"] > aw["quality"] > aw["momentum"])
    chk("전팩터 최고 code0 = 최고점", max(sc, key=sc.get) == "000000")
    chk("전팩터 최저 code19 = 최저점", min(sc, key=sc.get) == "000019")
    g = assign_grades(sc)
    chk("code0 S+ 등급", g["000000"] == "S+")
    chk("등급 종류 ≥4", len(set(g.values())) >= 4)
    # 결측 중립: 한 종목의 한 팩터 누락 → 0.5로 처리(에러 없이)
    r2 = {f: dict(d) for f, d in ranks.items()}
    del r2["q_roa"]["000005"]
    sc2, _, _ = score_codes(r2, adopted, uni, 1.0)
    chk("결측 팩터 중립처리(에러 없음)", "000005" in sc2)
    # growth_weight 효과: 성장만 높고 퀄리티 낮은 종목은 gw 1.0에서 더 높게
    ranks2 = {f: {c: 0.5 for c in uni} for f in adopted}
    for f in adopted:
        if AXIS_OF[f] == "growth":
            ranks2[f]["000000"] = 1.0   # code0 = 성장만 최고
    hi, _, _ = score_codes(ranks2, adopted, uni, 1.0)
    lo, _, _ = score_codes(ranks2, adopted, uni, 0.5)
    chk("성장가중↑일수록 성장종목 점수↑", hi["000000"] > lo["000000"])
    print(f"\nself-test: {ok}/{tot} pass")
    return ok == tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--growth-weight", type=float, default=1.0)
    ap.add_argument("--cache", default="kosdaq_sel_universe_cache.json")
    ap.add_argument("--factors", default="validate_kosdaq_sel_factors.json")
    ap.add_argument("--prices", default="kosdaq_monthly_prices.csv")
    args = ap.parse_args()
    if args.self_test:
        sys.exit(0 if self_test() else 1)
    run(args.cache, args.factors, args.prices, args.growth_weight)


if __name__ == "__main__":
    main()
