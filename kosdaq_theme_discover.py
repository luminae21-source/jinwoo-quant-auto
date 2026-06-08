#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kosdaq_theme_discover.py — KOSDAQ 테마 발굴 (theme→종목 매핑 스크리너, 선정 아님)
방법론(thematic investing): 테마=value-chain로 산업 가로지름 → 산업 키워드로 KOSDAQ 후보 surfacing
      → 가드레일(생존/실행) 통과만 → 모멘텀·성장·선반영(crowding) 지표 표기. 매수신호 아님·thesis는 진우.
근거: BlackRock/Alpha Architect 테마투자(가치사슬+crowding), 2026 KR 라이브테마(2차전지·로봇·반도체소부장·바이오·AI).
입력: liquidity_kosdaq · fundamentals_kosdaq · kosdaq_industry · kosdaq_monthly_prices  (전부 로컬)
사용: python kosdaq_theme_discover.py --list-themes
      python kosdaq_theme_discover.py                 # 전 테마 요약
      python kosdaq_theme_discover.py --theme 로봇     # 테마 후보 표
      python kosdaq_theme_discover.py --kw 반도체,전자부품   # 커스텀 산업 키워드
      python kosdaq_theme_discover.py --self-test
"""
import csv, sys, argparse
from kosdaq_theme_guardrail import load, latest_fund, check

# 테마 = 가치사슬을 가로지르는 산업 키워드 묶음 (substring 매칭)
THEME_MAP = {
    "로봇":        ["로봇", "특수 목적용 기계"],
    "2차전지":     ["전지", "축전지", "이차전지"],
    "반도체소부장": ["반도체", "전자부품", "특수 목적용 기계"],
    "바이오":      ["의약", "의료", "바이오", "생물"],
    "AI소프트웨어": ["소프트웨어", "자연과학", "정보서비스", "컴퓨터 프로그"],
    "에너지ESS":   ["전기", "에너지", "발전", "전력"],
    "우주방산":    ["항공", "우주", "무기", "방위"],
}


def ff(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def rev_yoy_map(fund_rows):
    by = {}
    for r in fund_rows:
        c = r["code"]
        try:
            y = int(float(r["fiscal_year"]))
        except (TypeError, ValueError):
            continue
        by.setdefault(c, {})[y] = ff(r.get("revenue"))
    out = {}
    for c, d in by.items():
        ys = sorted(d)
        if len(ys) >= 2 and d[ys[-2]] and d[ys[-2]] > 0 and d[ys[-1]] is not None:
            out[c] = d[ys[-1]] / d[ys[-2]] - 1
    return out


def price_metrics(price_rows):
    header = price_rows[0]; codes = header[1:]
    series = {c: [] for c in codes}
    for r in price_rows[1:]:
        for j, c in enumerate(codes, start=1):
            series[c].append(ff(r[j]) if j < len(r) else None)
    out = {}
    for c, s in series.items():
        if len(s) >= 13 and s[-2] and s[-13] and s[-13] > 0:
            mom = s[-2] / s[-13] - 1.0
            last12 = [x for x in s[-13:] if x]
            hi = max(last12) if last12 else None
            dist = (s[-1] / hi - 1.0) if (hi and s[-1]) else None
            out[c] = (mom, dist)
    return out


def crowding_flag(mom, dist):
    """선반영/crowding 주의: 12-1 급등(>+100%) 또는 12m 고점 근접(>-5%) = 늦었을 수 있음."""
    flags = []
    if mom is not None and mom > 1.0:
        flags.append("급등")
    if dist is not None and dist > -0.05:
        flags.append("고점근접")
    if mom is not None and dist is not None and mom < 0 and dist < -0.3:
        flags.append("소외(역발상?)")
    return "/".join(flags) or "-"


def candidates(kw_list, liq_by, ind_by, fund_by, ry, pm):
    out = []
    for code, sector in ind_by.items():
        if not sector or not any(k in sector for k in kw_list):
            continue
        g = check(code, liq_by, {} if code not in fund_by else {code: fund_by[code]})
        # check needs fund_by dict; pass full below instead
        out.append(code)
    return out


def run_theme(name, kw_list, data):
    liq_by, ind_by, fund_by, ry, pm = data
    rows = []
    for code, sector in ind_by.items():
        if not sector or not any(k in sector for k in kw_list):
            continue
        g = check(code, liq_by, fund_by)
        if not g["status"].startswith("PASS"):
            continue
        mom, dist = pm.get(code, (None, None))
        rows.append({"code": code, "name": liq_by.get(code, {}).get("name", code), "industry": sector,
                     "mcap": g["mcap_억"], "adtv": g["adtv_억"], "rev_yoy": ry.get(code),
                     "mom": mom, "dist": dist, "flag": crowding_flag(mom, dist), "gr": g["status"]})
    rows.sort(key=lambda r: (r["mom"] is not None, r["mom"] if r["mom"] is not None else -9), reverse=True)
    return rows


def fmt_pct(x):
    return "%+.0f%%" % (x * 100) if x is not None else "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--theme")
    ap.add_argument("--kw")
    ap.add_argument("--list-themes", action="store_true")
    ap.add_argument("--top", type=int, default=20)
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        sys.exit(0 if self_test() else 1)
    if args.list_themes:
        print("테마 → 산업 키워드(value-chain):")
        for k, v in THEME_MAP.items():
            print("  %-12s %s" % (k, v))
        return
    liq_by = {r["code"]: r for r in load("liquidity_kosdaq.csv")}
    ind_by = {r["code"]: r.get("sector") for r in load("kosdaq_industry.csv")}
    fund_by = latest_fund(load("fundamentals_kosdaq.csv"))
    ry = rev_yoy_map(load("fundamentals_kosdaq.csv"))
    pm = price_metrics(list(csv.reader(open("kosdaq_monthly_prices.csv", encoding="utf-8-sig"))))
    data = (liq_by, ind_by, fund_by, ry, pm)

    print("=== KOSDAQ 테마 발굴 (가드레일 통과 후보 surfacing · 매수신호 아님) ===")
    if args.kw:
        kw = [k.strip() for k in args.kw.split(",")]
        themes = [("커스텀:" + args.kw, kw)]
    elif args.theme:
        if args.theme not in THEME_MAP:
            print("테마 없음. --list-themes 참고."); return
        themes = [(args.theme, THEME_MAP[args.theme])]
    else:
        # 전 테마 요약
        print("[전 테마 요약] 가드레일 통과 후보 수 + 모멘텀 상위 3")
        for nm, kw in THEME_MAP.items():
            rows = run_theme(nm, kw, data)
            top3 = ", ".join("%s(%s)" % (r["name"][:8], fmt_pct(r["mom"])) for r in rows[:3])
            print("  %-12s 후보 %2d  | 모멘텀상위: %s" % (nm, len(rows), top3))
        print("\n특정 테마 표: --theme <이름> (예: --theme 로봇)")
        return
    for nm, kw in themes:
        rows = run_theme(nm, kw, data)
        print("\n[%s] 키워드 %s — 가드레일 통과 %d종 (상위 %d, 모멘텀순)" % (nm, kw, len(rows), min(args.top, len(rows))))
        print("  %-11s %-16s %7s %6s %7s %7s  %s" % ("종목", "산업", "시총억", "성장", "모멘텀", "고점대비", "선반영플래그"))
        for r in rows[:args.top]:
            print("  %-11s %-16s %7s %6s %7s %7s  %s" %
                  (r["name"][:11], (r["industry"] or "")[:16], r["mcap"], fmt_pct(r["rev_yoy"]),
                   fmt_pct(r["mom"]), fmt_pct(r["dist"]), r["flag"]))
        # csv 저장
        out = "kosdaq_theme_discover_%s.csv" % nm.replace(":", "_").replace(",", "_")
        with open(out, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.writer(fh)
            w.writerow(["code", "name", "industry", "mcap_억", "adtv_억", "rev_yoy", "mom_12_1", "dist_from_12mhigh", "선반영플래그", "guardrail", "thesis", "무효화트리거"])
            for r in rows:
                w.writerow([r["code"], r["name"], r["industry"], r["mcap"], r["adtv"],
                            round(r["rev_yoy"], 4) if r["rev_yoy"] is not None else "",
                            round(r["mom"], 4) if r["mom"] is not None else "",
                            round(r["dist"], 4) if r["dist"] is not None else "", r["flag"], r["gr"], "", ""])
        print("  → %s (thesis·무효화 빈칸=진우 기입). 모멘텀·선반영은 참고지표, 매수신호 아님." % out)


def self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1
        print("  [%s] %s" % ("OK" if c else "FAIL", n)); ok += 1 if c else 0
    chk("crowding 급등 플래그", "급등" in crowding_flag(1.5, -0.2))
    chk("crowding 고점근접 플래그", "고점근접" in crowding_flag(0.3, -0.01))
    chk("crowding 소외 플래그", "소외" in crowding_flag(-0.4, -0.5))
    chk("crowding 무난 -", crowding_flag(0.2, -0.4) == "-")
    chk("THEME_MAP 7개", len(THEME_MAP) == 7)
    chk("rev_yoy 계산", abs(rev_yoy_map([{"code": "A", "fiscal_year": "2023", "revenue": "100"}, {"code": "A", "fiscal_year": "2024", "revenue": "130"}])["A"] - 0.3) < 1e-9)
    print("\nself-test: %d/%d pass" % (ok, tot))
    return ok == tot


if __name__ == "__main__":
    main()
