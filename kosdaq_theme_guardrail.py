#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kosdaq_theme_guardrail.py — KOSDAQ 하이브리드 테마 lane · 가드레일 체크 (선정 아님)
역할: 진우 테마 후보가 '사도 되는 후보군'인지(부도·동전주·관리 회피) 체크만. thesis·매수는 진우.
      퀄리티/성장 컷 없음(테마는 적자 pre-profit 多). production·v41 무수정. 신규 파일.
가드레일(b, 2026-06-06 캘리브레이션): 정상4부 · ADTV≥5억 · 시총≥500억 · equity>0 · 부채비율≤400%
      재무(297) 없으면 hard-fail 대신 '수동확인' caveat.
입력: liquidity_kosdaq.csv · fundamentals_kosdaq.csv · (선택) kosdaq_theme_watchlist_in.csv
출력: kosdaq_theme_watchlist.csv (guardrail_status 채움 + thesis 빈칸=진우 기입)
사용: python kosdaq_theme_guardrail.py --self-test
      python kosdaq_theme_guardrail.py        # seed 워치리스트 체크
"""
import csv, sys, argparse

NORMAL = {"중견기업부", "우량기업부", "벤처기업부", "기술성장기업부"}
ADTV_MIN = 5e8
MCAP_MIN = 500e8
DEBT_MAX = 4.0

# seed: size진단 EW 견인주 + 진우 보유(에코프로비엠). (code, name, theme) — 사실 분류일 뿐 매수신호 아님
SEED = [
    ("247540", "에코프로비엠", "2차전지"), ("086520", "에코프로", "2차전지"),
    ("277810", "레인보우로보틱스", "로봇"), ("108490", "로보티즈", "로봇"),
    ("087010", "펩트론", "바이오"), ("028300", "HLB", "바이오"), ("196170", "알테오젠", "바이오"),
    ("036930", "주성엔지니어링", "반도체소부장"), ("080220", "제주반도체", "반도체소부장"),
    ("043260", "성호전자", "전자부품"), ("083650", "비에이치아이", "발전설비"),
    ("257720", "실리콘투", "화장품유통"),
]


def f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def load(fn):
    with open(fn, encoding="utf-8-sig") as fh:
        return list(csv.DictReader(fh))


def latest_fund(fund_rows):
    out = {}
    for r in fund_rows:
        c = r["code"]
        try:
            y = int(float(r["fiscal_year"]))
        except (TypeError, ValueError):
            continue
        if c not in out or y > out[c][0]:
            out[c] = (y, r)
    return {c: r for c, (y, r) in out.items()}


def check(code, liq_by, fund_by):
    r = liq_by.get(code)
    if not r:
        return {"status": "FAIL", "reasons": "liquidity 없음", "board": None, "mcap_억": None, "adtv_억": None, "debt": None}
    board = r.get("sector"); mc = f(r.get("mcap")); ad = f(r.get("adtv"))
    reasons = []
    if board not in NORMAL:
        reasons.append("시장부(%s)" % board)
    if mc is None or mc < MCAP_MIN:
        reasons.append("시총<500억")
    if ad is None or ad < ADTV_MIN:
        reasons.append("ADTV<5억")
    caveat = ""
    debt = None
    fr = fund_by.get(code)
    if fr:
        eq = f(fr.get("equity")); li = f(fr.get("liabilities"))
        if eq is not None and eq <= 0:
            reasons.append("자본잠식")
        elif eq and eq > 0 and li is not None:
            debt = round(li / eq, 2)
            if debt > DEBT_MAX:
                reasons.append("부채비율>400%%")
    else:
        caveat = "재무미확인(수동)"
    status = "FAIL" if reasons else ("PASS*" if caveat else "PASS")
    return {"status": status, "reasons": ";".join(reasons) or caveat,
            "board": board, "mcap_억": round(mc / 1e8) if mc else None,
            "adtv_억": round(ad / 1e8, 1) if ad else None, "debt": debt}


def run(watch_in=None, out_csv="kosdaq_theme_watchlist.csv"):
    liq_by = {r["code"]: r for r in load("liquidity_kosdaq.csv")}
    fund_by = latest_fund(load("fundamentals_kosdaq.csv"))
    if watch_in:
        rows = [(r["code"], r.get("name", ""), r.get("theme", "")) for r in load(watch_in)]
    else:
        rows = SEED
    cols = ["code", "name", "theme", "guardrail", "사유/플래그", "board", "mcap_억", "adtv_억",
            "부채비율", "thesis_catalyst", "기간", "무효화_트리거", "선반영점검", "진입비중", "메모"]
    out = []
    print("=== KOSDAQ 테마 가드레일 체크 (선정 아님) ===")
    print("게이트: 정상4부 · ADTV>=5억 · 시총>=500억 · equity>0 · 부채비율<=400%")
    print("%-12s %-9s %-6s %s" % ("name", "theme", "판정", "사유/데이터"))
    for code, name, theme in rows:
        c = check(code, liq_by, fund_by)
        print("%-12s %-9s %-6s %s (시총%s억 ADTV%s억 부채%s)" %
              (name[:12], theme, c["status"], c["reasons"] or "-", c["mcap_억"], c["adtv_억"], c["debt"]))
        out.append({"code": code, "name": name, "theme": theme, "guardrail": c["status"],
                    "사유/플래그": c["reasons"], "board": c["board"], "mcap_억": c["mcap_억"],
                    "adtv_억": c["adtv_억"], "부채비율": c["debt"],
                    "thesis_catalyst": "", "기간": "", "무효화_트리거": "", "선반영점검": "", "진입비중": "", "메모": ""})
    with open(out_csv, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=cols); w.writeheader()
        for o in out:
            w.writerow(o)
    npass = sum(1 for o in out if o["guardrail"].startswith("PASS"))
    print("\n통과 %d/%d (PASS*=재무 수동확인). thesis/무효화/매수는 진우 기입 — 가드레일 통과=고려가능이지 매수신호 아님." % (npass, len(out)))
    print("출력:", out_csv)


def self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1
        print("  [%s] %s" % ("OK" if c else "FAIL", n)); ok += 1 if c else 0
    liq_by = {
        "N": {"code": "N", "name": "정상", "sector": "우량기업부", "mcap": "1e12", "adtv": "5e9"},
        "M": {"code": "M", "name": "관리", "sector": "관리종목(소속부없음)", "mcap": "1e12", "adtv": "5e9"},
        "P": {"code": "P", "name": "동전", "sector": "벤처기업부", "mcap": "1e10", "adtv": "1e7"},
        "D": {"code": "D", "name": "과부채", "sector": "중견기업부", "mcap": "1e12", "adtv": "5e9"},
        "X": {"code": "X", "name": "재무무", "sector": "중견기업부", "mcap": "1e12", "adtv": "5e9"},
    }
    fund_by = {
        "N": {"equity": "5e11", "liabilities": "3e11"},
        "M": {"equity": "5e11", "liabilities": "3e11"},
        "P": {"equity": "5e9", "liabilities": "1e9"},
        "D": {"equity": "1e11", "liabilities": "9e11"},  # 부채비율 9 > 4
    }
    chk("정상 PASS", check("N", liq_by, fund_by)["status"] == "PASS")
    chk("관리종목 FAIL", check("M", liq_by, fund_by)["status"] == "FAIL")
    chk("동전·저유동 FAIL", check("P", liq_by, fund_by)["status"] == "FAIL")
    chk("과부채(900%) FAIL", check("D", liq_by, fund_by)["status"] == "FAIL")
    chk("재무무 PASS*(수동)", check("X", liq_by, fund_by)["status"] == "PASS*")
    chk("없는코드 FAIL", check("ZZ", liq_by, fund_by)["status"] == "FAIL")
    print("\nself-test: %d/%d pass" % (ok, tot))
    return ok == tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--watch-in", default=None)
    args = ap.parse_args()
    if args.self_test:
        sys.exit(0 if self_test() else 1)
    run(args.watch_in)


if __name__ == "__main__":
    main()
