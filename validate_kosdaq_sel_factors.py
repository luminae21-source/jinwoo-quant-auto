#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_kosdaq_sel_factors.py — 진우퀀트 v4.1 KOSDAQ 종목선정(kosdaq_sel) · Stage 2

역할: 후보 팩터 '적합성 점검' + '상관 prune'(중복신호 제거). 점수화·가중·백테스트 X (Stage 3·4).
      결정메모 §4-나/§5-축3 원칙: 상관은 '추가'가 아니라 '쳐내는' 도구. 부호/IC로 종목을 고르지 않음
      (= 합격선 먼저, fitting 나중. 수익 기반 팩터선택은 overfitting → 판정은 Stage4 백테스트가).

입력(로컬, PC/FDR 불필요):
  - kosdaq_sel_universe_cache.json   (Stage 1 산출: firms 스냅샷 + universe_latest 193)
  - kosdaq_monthly_prices.csv        (12-1 모멘텀 산출, 한국 F–모멘텀 상관 점검용)
출력:
  - validate_kosdaq_sel_factors.json  (Spearman 행렬 + 채택셋 + 적재금지[중복] 목록 + 사유)
  - validate_kosdaq_sel_factors_diag.csv  (팩터별 커버리지·상태)

방법:
  1) 후보 팩터를 '높을수록 좋게' orient (accrual·debt·성장변동성은 부호반전)
  2) 저베이스 폭발 방어: winsor(2.5/97.5) → 횡단면 percentile rank[0,1]
  3) Spearman(=rank Pearson, 이상치 robust)로 상관행렬
  4) 우선순위(성장 robust 1차축) 그리디 prune: |ρ|≥0.70 이면 후순위 = 적재금지(중복)
  5) 커버리지 <60% 팩터는 제외(데이터 부족)

사용:
  python validate_kosdaq_sel_factors.py --self-test
  python validate_kosdaq_sel_factors.py
"""
import csv, json, sys, argparse, statistics

PRUNE_RHO = 0.70          # |Spearman| 이상이면 후순위 팩터 적재금지(중복)
WINSOR = 0.025            # 양측 2.5%
COVERAGE_MIN = 0.60       # 커버리지 게이트

# (factor, axis, snapshot_key, orient)  orient=-1 → 부호반전(낮을수록 좋음)
# 우선순위 = 이 순서 (성장 robust 매출·CFO 먼저, 그다음 핵심 quality, 모멘텀, 보조 성장)
FACTOR_SPEC = [
    ("g_rev_yoy",       "growth",  "rev_yoy",       +1),
    ("g_cfo_yoy",       "growth",  "cfo_yoy",       +1),
    ("g_rev_cagr",      "growth",  "rev_cagr",      +1),
    ("q_roa",           "quality", "roa",           +1),
    ("q_low_accrual",   "quality", "accrual_sloan", -1),   # Sloan: 낮은 accrual 우량
    ("q_op_margin",     "quality", "op_margin",     +1),
    ("q_low_debt",      "quality", "debt_ratio",    -1),
    ("q_current",       "quality", "current_ratio", +1),
    ("m_mom_12_1",      "momentum","__mom__",       +1),   # 가격패널서 산출
    ("g_op_yoy",        "growth",  "op_yoy",        +1),
    ("g_ni_yoy",        "growth",  "ni_yoy",        +1),
    ("q_gross_margin",  "quality", "gross_margin",  +1),
    ("g_rev_stability", "growth",  "rev_yoy_std",   -1),   # 변동 작을수록 안정
]


def load_json(p):
    return json.load(open(p, encoding="utf-8"))


def compute_momentum(price_path, codes):
    """12-1 모멘텀: p[-2]/p[-13]-1 (최신월=진행중 crash stub skip)."""
    try:
        with open(price_path, encoding="utf-8-sig", newline="") as f:
            rows = list(csv.reader(f))
    except FileNotFoundError:
        return {}, "price_file_missing"
    if len(rows) < 14:
        return {}, "insufficient_history"
    header = rows[0]
    col_idx = {header[j]: j for j in range(1, len(header))}
    mom = {}
    for code in codes:
        j = col_idx.get(code)
        if j is None:
            continue
        series = []
        for r in rows[1:]:
            if j < len(r):
                try:
                    series.append(float(r[j]))
                except (ValueError, TypeError):
                    series.append(None)
            else:
                series.append(None)
        if len(series) >= 13 and series[-2] and series[-13] and series[-13] > 0:
            mom[code] = series[-2] / series[-13] - 1.0
    return mom, "ok"


def winsorize(vals, p):
    s = sorted(vals)
    if len(s) < 5:
        return dict()
    lo = s[int(p * len(s))]
    hi = s[min(len(s) - 1, int((1 - p) * len(s)))]
    return lo, hi


def rank_pct(d):
    """{code:val} → {code: percentile rank[0,1]} (tie=평균순위). None 제외."""
    items = [(c, v) for c, v in d.items() if v is not None]
    if len(items) < 2:
        return {}
    items.sort(key=lambda t: t[1])
    n = len(items)
    out = {}
    i = 0
    while i < n:
        j = i
        while j + 1 < n and items[j + 1][1] == items[i][1]:
            j += 1
        avg_rank = (i + j) / 2.0
        for k in range(i, j + 1):
            out[items[k][0]] = avg_rank / (n - 1)
        i = j + 1
    return out


def pearson(xa, xb):
    common = [c for c in xa if c in xb]
    if len(common) < 10:
        return None, len(common)
    x = [xa[c] for c in common]; y = [xb[c] for c in common]
    mx, my = statistics.fmean(x), statistics.fmean(y)
    sx = sum((a - mx) ** 2 for a in x) ** 0.5
    sy = sum((b - my) ** 2 for b in y) ** 0.5
    if sx == 0 or sy == 0:
        return None, len(common)
    cov = sum((a - mx) * (b - my) for a, b in zip(x, y))
    return cov / (sx * sy), len(common)


def build_factor_ranks(firms, universe, mom):
    raw = {}
    for name, axis, key, orient in FACTOR_SPEC:
        d = {}
        for c in universe:
            snap = firms[c].get("snapshot", {})
            v = mom.get(c) if key == "__mom__" else snap.get(key)
            if v is not None:
                d[c] = orient * v
        raw[name] = d
    # winsor + rank
    ranks = {}; coverage = {}
    for name, axis, key, orient in FACTOR_SPEC:
        d = raw[name]
        coverage[name] = len(d) / len(universe) if universe else 0
        if len(d) >= 5:
            lo, hi = winsorize(list(d.values()), WINSOR)
            d = {c: min(hi, max(lo, v)) for c, v in d.items()}
        ranks[name] = rank_pct(d)
    return ranks, coverage


def prune(ranks, coverage):
    order = [s[0] for s in FACTOR_SPEC]
    low_cov = [n for n in order if coverage[n] < COVERAGE_MIN]
    cand = [n for n in order if coverage[n] >= COVERAGE_MIN]
    adopted = []; pruned = []
    corr = {}
    for n in cand:
        worst = None  # (kept, rho)
        for k in adopted:
            rho, _ = pearson(ranks[n], ranks[k])
            if rho is not None:
                corr[f"{n}~{k}"] = round(rho, 3)
                if worst is None or abs(rho) > abs(worst[1]):
                    worst = (k, rho)
        if worst is not None and abs(worst[1]) >= PRUNE_RHO:
            pruned.append({"factor": n, "redundant_with": worst[0], "rho": round(worst[1], 3)})
        else:
            adopted.append(n)
    return adopted, pruned, low_cov, corr


def full_matrix(ranks, names):
    m = {}
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            rho, n = pearson(ranks[a], ranks[b])
            if rho is not None:
                m[f"{a}~{b}"] = round(rho, 3)
    return m


def run(cache_path="kosdaq_sel_universe_cache.json",
        price_path="kosdaq_monthly_prices.csv",
        out_json="validate_kosdaq_sel_factors.json",
        out_csv="validate_kosdaq_sel_factors_diag.csv"):
    cache = load_json(cache_path)
    firms = cache["firms"]; universe = cache["universe_latest"]
    mom, mom_status = compute_momentum(price_path, universe)
    ranks, coverage = build_factor_ranks(firms, universe, mom)
    adopted, pruned, low_cov, corr = prune(ranks, coverage)
    spec = {s[0]: (s[1], s[3]) for s in FACTOR_SPEC}

    # 진단 하이라이트: 성장-모멘텀, accrual-roa
    def rho_of(a, b):
        r, _ = pearson(ranks.get(a, {}), ranks.get(b, {})); return None if r is None else round(r, 3)
    highlights = {
        "growth_momentum(g_rev_yoy~m_mom_12_1)": rho_of("g_rev_yoy", "m_mom_12_1"),
        "accrual_roa(q_low_accrual~q_roa)": rho_of("q_low_accrual", "q_roa"),
        "revYoY_cagr(g_rev_yoy~g_rev_cagr)": rho_of("g_rev_yoy", "g_rev_cagr"),
        "roa_opmargin(q_roa~q_op_margin)": rho_of("q_roa", "q_op_margin"),
    }

    result = {
        "meta": {"module": "v4.1 kosdaq_sel · Stage 2 (factor 적합성+prune)",
                 "universe_n": len(universe), "mom_status": mom_status,
                 "mom_coverage": round(len(mom) / len(universe), 3) if universe else 0,
                 "prune_rho": PRUNE_RHO, "winsor": WINSOR, "coverage_min": COVERAGE_MIN,
                 "note": "상관 prune만(부호/IC 기반 선정 X). 수익 검증은 Stage4 백테스트(등록 합격선)."},
        "adopted_factors": adopted,
        "pruned_redundant": pruned,
        "low_coverage_dropped": low_cov,
        "coverage": {k: round(v, 3) for k, v in coverage.items()},
        "spearman_highlights": highlights,
        "spearman_matrix_all": full_matrix(ranks, [s[0] for s in FACTOR_SPEC if coverage[s[0]] >= COVERAGE_MIN]),
    }
    json.dump(result, open(out_json, "w", encoding="utf-8"), ensure_ascii=False, indent=1)

    with open(out_csv, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(["factor", "axis", "orient", "coverage", "status", "redundant_with", "rho"])
        pr = {p["factor"]: p for p in pruned}
        for name, axis, key, orient in FACTOR_SPEC:
            if name in low_cov:
                st, rw, rho = "low_coverage", "", ""
            elif name in pr:
                st, rw, rho = "pruned_redundant", pr[name]["redundant_with"], pr[name]["rho"]
            else:
                st, rw, rho = "adopted", "", ""
            w.writerow([name, axis, "+" if orient > 0 else "-", round(coverage[name], 3), st, rw, rho])

    print("=== KOSDAQ 팩터 적합성 + 상관 prune (Stage 2) ===")
    print(f"universe N={len(universe)} | 모멘텀 커버리지 {result['meta']['mom_coverage']:.0%} ({mom_status})")
    print(f"\n채택 팩터셋 ({len(adopted)}): {adopted}")
    print(f"\n적재금지(중복, |ρ|≥{PRUNE_RHO}):")
    for p in pruned:
        print(f"  - {p['factor']:16s} ↔ {p['redundant_with']:16s} ρ={p['rho']}")
    if low_cov:
        print(f"\n커버리지<{COVERAGE_MIN:.0%} 제외: {low_cov}")
    print("\n주요 상관 하이라이트:")
    for k, v in highlights.items():
        print(f"  {k} = {v}")
    print(f"\n출력: {out_json} , {out_csv}")
    return result


# ----------------------- SELF TEST -----------------------
def self_test():
    ok = tot = 0
    def chk(name, cond):
        nonlocal ok, tot; tot += 1
        print(f"  [{'OK' if cond else 'FAIL'}] {name}"); ok += 1 if cond else 0

    # rank 단조성
    r = rank_pct({"a": 1, "b": 2, "c": 3, "d": 4})
    chk("rank 단조(min0 max1)", r["a"] == 0.0 and r["d"] == 1.0)
    # 완전상관 → ρ≈1
    x = {c: i for i, c in enumerate("abcdefghij")}
    y = {c: i * 2 for i, c in enumerate("abcdefghij")}
    rho, _ = pearson(rank_pct(x), rank_pct(y))
    chk("완전단조 Spearman≈1", abs(rho - 1.0) < 1e-9)
    # 역상관
    z = {c: -i for i, c in enumerate("abcdefghij")}
    rho2, _ = pearson(rank_pct(x), rank_pct(z))
    chk("역단조 Spearman≈-1", abs(rho2 + 1.0) < 1e-9)
    # 합성 prune: g_rev_yoy 와 g_cfo_yoy 동일 → 후순위(cfo) 적재금지
    firms = {}
    uni = []
    import random; random.seed(1)
    for i in range(60):
        c = f"{i:06d}"; uni.append(c)
        base = random.random()
        firms[c] = {"snapshot": {
            "rev_yoy": base, "cfo_yoy": base,           # 완전 동일 → 중복
            "rev_cagr": random.random(), "roa": random.random(),
            "accrual_sloan": random.random(), "op_margin": random.random(),
            "debt_ratio": random.random(), "current_ratio": random.random(),
            "op_yoy": random.random(), "ni_yoy": random.random(),
            "gross_margin": random.random(), "rev_yoy_std": random.random(),
        }}
    ranks, cov = build_factor_ranks(firms, uni, {})
    adopted, pruned, low_cov, corr = prune(ranks, cov)
    chk("동일팩터 g_cfo_yoy 적재금지(중복)", any(p["factor"] == "g_cfo_yoy" for p in pruned))
    chk("g_rev_yoy 채택", "g_rev_yoy" in adopted)
    chk("모멘텀 커버리지0 → low_coverage 제외", "m_mom_12_1" in low_cov)
    chk("orient 반전: q_low_accrual rank 존재", "q_low_accrual" in ranks and len(ranks["q_low_accrual"]) > 0)
    print(f"\nself-test: {ok}/{tot} pass")
    return ok == tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--cache", default="kosdaq_sel_universe_cache.json")
    ap.add_argument("--prices", default="kosdaq_monthly_prices.csv")
    args = ap.parse_args()
    if args.self_test:
        sys.exit(0 if self_test() else 1)
    run(args.cache, args.prices)


if __name__ == "__main__":
    main()
