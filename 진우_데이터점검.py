#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우_데이터점검.py — 데이터 신선도 점검(패널·지수 마지막날 vs 오늘)

사용: py 진우_데이터점검.py [--self-test]
"""
import os, sys, argparse
from datetime import date, timedelta
HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
FILES = [("KOSPI 일봉", "종목일봉_30년_KOSPI.csv"), ("KOSDAQ 일봉", "종목일봉_30년_KOSDAQ.csv"),
         ("KOSPI 지수", "kospi_index_daily.csv")]

def last_date(path):
    if not os.path.exists(path): return None
    with open(path, "rb") as f:
        f.seek(0, 2); size = f.tell(); f.seek(max(0, size-4096))
        tail = f.read().decode("utf-8-sig", "ignore").strip().split("\n")
    for line in reversed(tail):
        c = line.split(",")
        if c and len(c[0]) == 10 and c[0][4] == "-": return c[0]
    return None

def biz_gap(d, today):
    """d(제외)~today 영업일 수."""
    n = 0; x = d + timedelta(days=1)
    while x <= today:
        if x.weekday() < 5: n += 1
        x += timedelta(days=1)
    return n

def run():
    today = date.today()
    print(f"데이터 신선도 점검 · 오늘 {today}\n" + "="*52)
    stale = False
    for lab, fn in FILES:
        ld = last_date(os.path.join(HERE, fn))
        if ld is None:
            print(f"  {lab:<12}: 없음 ⛔"); stale = True; continue
        gap = biz_gap(date.fromisoformat(ld), today)
        flag = "최신 ✓" if gap <= 1 else (f"⚠ {gap}영업일 지연" if gap <= 5 else f"⛔ {gap}영업일 지연(낡음)")
        if gap > 1: stale = True
        print(f"  {lab:<12}: {ld}  {flag}")
    print("="*52)
    if stale:
        print("→ 갱신 권고:  py 진우_일봉_증분수집.py  (PC·pykrx)  →  py 발굴데이터_갱신.py  →  발굴 실행")
    else:
        print("→ 전부 최신. 바로 발굴 실행 가능.")
    return 0

def _self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    chk("영업일 갭(금~화=2)", biz_gap(date(2026,7,10), date(2026,7,14)) == 2)
    chk("같은날=0", biz_gap(date(2026,7,13), date(2026,7,13)) == 0)
    print(f"\n셀프테스트: {ok}/{tot}"); return ok == tot

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    return (0 if _self_test() else 1) if a.self_test else run()

if __name__ == "__main__":
    sys.exit(main())
