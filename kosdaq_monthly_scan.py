#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kosdaq_monthly_scan.py — KOSDAQ 테마 월간 통합 스캔 (turnkey, 매달 1커맨드)
전 테마 발굴 1회 실행 → ① 통합 CSV ② 전월 대비 '신규 부상' 종목(발굴 신호) ③ '소외(역발상)' 후보.
선정/매수신호 아님. thesis·매수는 진우. 정의는 kosdaq_theme_discover/guardrail import(단일화). 무수정 원칙.
사용: python kosdaq_monthly_scan.py        (PC 1회) / --self-test
출력: kosdaq_monthly_scan_<YYYYMM>.csv
"""
import csv, sys, glob, argparse
from kosdaq_theme_discover import THEME_MAP, run_theme, rev_yoy_map, price_metrics
from kosdaq_theme_guardrail import load, latest_fund


def build_data():
    liq_by = {r["code"]: r for r in load("liquidity_kosdaq.csv")}
    ind_by = {r["code"]: r.get("sector") for r in load("kosdaq_industry.csv")}
    fund_by = latest_fund(load("fundamentals_kosdaq.csv"))
    ry = rev_yoy_map(load("fundamentals_kosdaq.csv"))
    pm = price_metrics(list(csv.reader(open("kosdaq_monthly_prices.csv", encoding="utf-8-sig"))))
    return (liq_by, ind_by, fund_by, ry, pm)


def month_label():
    rows = list(csv.reader(open("kosdaq_monthly_prices.csv", encoding="utf-8-sig")))
    return rows[-1][0][:7].replace("-", "")   # 데이터 as-of 월 (예: 202606)


def prev_codes(current_out=None):
    files = [f for f in sorted(glob.glob("kosdaq_monthly_scan_*.csv")) if f != current_out]
    if not files:
        return None, None
    prev = {}
    for r in csv.DictReader(open(files[-1], encoding="utf-8-sig")):
        prev.setdefault(r["theme"], set()).add(r["code"])
    return prev, files[-1]


def is_crowded(flag):
    return ("급등" in flag) or ("고점근접" in flag)


def fmtp(x):
    return "%+.0f%%" % (x * 100) if x is not None else "-"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    args = ap.parse_args()
    if args.self_test:
        ok = tot = 0
        def chk(n, c):
            nonlocal ok, tot; tot += 1
            print("  [%s] %s" % ("OK" if c else "FAIL", n)); ok += 1 if c else 0
        chk("THEME_MAP import", len(THEME_MAP) == 7)
        chk("is_crowded 급등", is_crowded("급등/고점근접") is True)
        chk("is_crowded 소외 False", is_crowded("소외(역발상?)") is False)
        chk("fmtp", fmtp(0.5) == "+50%")
        print("\nself-test: %d/%d pass" % (ok, tot))
        sys.exit(0 if ok == tot else 1)

    data = build_data()
    liq_by = data[0]
    ym = month_label()
    out = "kosdaq_monthly_scan_%s.csv" % ym
    prev, prev_file = prev_codes(out)  # 같은 달 자기파일 제외
    allrows = []; seen = set()
    print("=== KOSDAQ 테마 월간 통합 스캔 (%s) — 매수신호 아님 ===" % ym)
    if prev:
        print("전월 대비: %s" % prev_file)
    print("%-12s %4s %5s  %-28s %s" % ("테마", "후보", "선반영", "모멘텀 상위3", "신규부상"))
    for nm, kw in THEME_MAP.items():
        rows = run_theme(nm, kw, data)
        crowded = sum(1 for r in rows if is_crowded(r["flag"]))
        top3 = ", ".join("%s%s" % (r["name"][:7], fmtp(r["mom"])) for r in rows[:3])
        new = ""
        if prev is not None:
            pcodes = prev.get(nm, set())
            news = [r["name"][:7] for r in rows[:25] if r["code"] not in pcodes]
            new = ("신규:" + ",".join(news[:4])) if news else "-"
        print("%-12s %4d %4d%%  %-28s %s" % (nm, len(rows), round(100 * crowded / max(1, len(rows))), top3[:28], new))
        for r in rows:
            r2 = dict(r); r2["theme"] = nm; allrows.append(r2)
            seen.add(r["code"])
    # 소외(역발상) 후보 — early/beaten-down (테마 내 비선반영 + 음의 모멘텀 깊음)
    contr = sorted([r for r in allrows if "소외" in r["flag"]], key=lambda r: (r["dist"] if r["dist"] is not None else 0))
    print("\n[소외/역발상 후보] (테마 견인주 중 깊은 조정 — 진우 thesis로 선별, 매수신호 아님):")
    seen_c = set()
    for r in contr[:10]:
        if r["code"] in seen_c:
            continue
        seen_c.add(r["code"])
        print("  %-11s %-9s 고점대비%s 모멘텀%s" % (r["name"][:11], r["theme"], fmtp(r["dist"]), fmtp(r["mom"])))

    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["theme", "code", "name", "industry", "mcap_억", "adtv_억", "rev_yoy", "mom_12_1",
                    "dist_from_12mhigh", "선반영플래그", "guardrail", "thesis", "무효화트리거"])
        for r in allrows:
            w.writerow([r["theme"], r["code"], r["name"], r["industry"], r["mcap"], r["adtv"],
                        round(r["rev_yoy"], 4) if r["rev_yoy"] is not None else "",
                        round(r["mom"], 4) if r["mom"] is not None else "",
                        round(r["dist"], 4) if r["dist"] is not None else "", r["flag"], r["gr"], "", ""])
    print("\n총 후보(중복포함) %d행 · 고유종목 %d · 출력 %s" % (len(allrows), len(seen), out))
    print("→ thesis·무효화 빈칸=진우 기입. 선반영 높은 테마는 '카탈리스트 남았나'가 관건. 다음: watchlist 반영 + Track W 기록.")


if __name__ == "__main__":
    main()
