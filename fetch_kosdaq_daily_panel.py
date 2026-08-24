#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_kosdaq_daily_panel.py — [PC 실행] 테마 lane universe 일별 시세 자동 수집(FDR)
대상 = kosdaq_theme_chain_map.csv(KOSDAQ peer) + kosdaq_theme_watchlist.csv 종목 + KOSPI/KOSDAQ 지수.
산출 = kosdaq_theme_daily.csv (long: code,date,open,high,low,close) — 선반영 스캐너가 자동으로 읽음.
무수정: production·기존 산출물 안 건드림. 더블클릭(.bat)으로 자동 실행됨.

사용: python fetch_kosdaq_daily_panel.py [--years 2] | --self-test
"""
import csv, sys
from pathlib import Path
from datetime import date, timedelta
BASE = Path(__file__).parent.resolve()


def load_codes():
    u = {}
    p = BASE / "kosdaq_theme_chain_map.csv"
    if p.exists():
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            if r.get("market") == "KOSDAQ":
                u[str(r["ticker"]).zfill(6)] = r["name"]
    p = BASE / "kosdaq_theme_watchlist.csv"
    if p.exists():
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            c = str(r.get("code", "")).zfill(6)
            if c.strip("0"):
                u.setdefault(c, r.get("name", c))
    return u


def fetch(years=2):
    import FinanceDataReader as fdr
    start = (date.today() - timedelta(days=int(years * 365.25))).strftime("%Y-%m-%d")
    codes = load_codes()
    idx = {"KS11": "KOSPI", "KQ11": "KOSDAQ"}
    out = BASE / "kosdaq_theme_daily.csv"
    w = csv.writer(open(out, "w", encoding="utf-8-sig", newline=""))
    w.writerow(["code", "date", "open", "high", "low", "close"])
    ok = 0; fail = []
    for code in list(idx) + list(codes):
        name = idx.get(code) or codes.get(code, code)
        try:
            df = fdr.DataReader(code, start)
            for d, row in df.iterrows():
                w.writerow([code, str(d.date()),
                            row.get("Open", ""), row.get("High", ""), row.get("Low", ""), row.get("Close", "")])
            ok += 1; print("  fetched %-10s %s (%d행)" % (name, code, len(df)))
        except Exception as e:
            fail.append(name); print("  [FAIL] %-10s %s -> %s" % (name, code, e))
    print("\n저장: kosdaq_theme_daily.csv | 성공 %d종%s" % (ok, ("" if not fail else " · 실패 %s" % fail)))
    print("→ 이어서 선반영 스캔이 이 파일을 자동으로 읽습니다.")


def self_test():
    c = load_codes()
    ok = len(c) > 0 and all(len(k) == 6 for k in c)
    print("  [%s] universe 코드 %d종 로드·6자리" % ("OK" if ok else "FAIL", len(c)))
    print("self-test: %d/1" % (1 if ok else 0)); return ok


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        yrs = 2
        if "--years" in sys.argv:
            try: yrs = float(sys.argv[sys.argv.index("--years") + 1])
            except (ValueError, IndexError): pass
        try:
            fetch(yrs)
        except Exception:
            import traceback; print("\n[에러]"); traceback.print_exc()
            print("\n힌트: pip install finance-datareader pandas 먼저. 회사망 막히면 개인망에서.")
