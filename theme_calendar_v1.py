#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
theme_calendar_v1.py — 테마 카탈리스트 캘린더 (v1, forward 신호 'A 촉매' 일정 레이어)
"다가오는 일정에 미리 자리잡기" — 실적시즌·美 빅테크 실적·월간 매크로를 계산해
오늘부터 N일 내 카탈리스트 + 영향 테마를 표시. production·C·D·영역3·v41 무수정. 매수신호 아님.

계산형(자동): 한국 분기실적 시즌 / 美 빅테크 실적 시즌 / 美 CPI·고용 / 한국 수출지표.
고정일형(web/수기): FOMC·금통위·확정 실적일 → theme_calendar_fixed.csv 있으면 병합.

사용:
  python theme_calendar_v1.py --self-test
  python theme_calendar_v1.py            # 오늘부터 75일 카탈리스트
  python theme_calendar_v1.py --days 120
"""
import sys, datetime as dt

HORIZON = 75


def kr_earnings(y):
    out = []
    for q in [dt.date(y, 3, 31), dt.date(y, 6, 30), dt.date(y, 9, 30), dt.date(y, 12, 31)]:
        c = q + dt.timedelta(days=35)            # 분기말 +35일 중심
        out.append((c - dt.timedelta(days=12), c + dt.timedelta(days=12),
                    "한국 분기실적 시즌", "반도체·2차전지·로봇 등 실적 모멘텀 구간"))
    return out


def us_tech_earnings(y):
    out = []
    for q in [dt.date(y, 3, 31), dt.date(y, 6, 30), dt.date(y, 9, 30), dt.date(y, 12, 31)]:
        c = q + dt.timedelta(days=27)            # 美 빅테크 ~3~4주
        out.append((c - dt.timedelta(days=10), c + dt.timedelta(days=18),
                    "美 빅테크 실적(엔비디아·테슬라·마이크론)", "밤사이 갭 → 한국 반도체·AI·로봇·2차전지 직격"))
    return out


def monthly(y):
    out = []
    for mo in range(1, 13):
        out.append((dt.date(y, mo, 1), dt.date(y, mo, 1), "한국 수출지표(월초)", "반도체·수출주 업황 바로미터"))
        out.append((dt.date(y, mo, 12), dt.date(y, mo, 12), "美 CPI(물가)", "성장주 전반(금리 민감)"))
        d1 = dt.date(y, mo, 1)
        fri = d1 + dt.timedelta(days=(4 - d1.weekday()) % 7)   # 첫 금요일
        out.append((fri, fri, "美 고용(NFP)", "성장주 전반"))
    return out


def fixed_csv(path="theme_calendar_fixed.csv"):
    import os, csv
    if not os.path.exists(path):
        return []
    out = []
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        try:
            d = dt.date.fromisoformat(r["date"][:10])
            out.append((d, d, r.get("event", ""), r.get("theme", "")))
        except (ValueError, KeyError):
            continue
    return out


def all_events(today):
    ev = []
    for y in (today.year, today.year + 1):
        ev += kr_earnings(y) + us_tech_earnings(y) + monthly(y)
    ev += fixed_csv()
    return ev


def upcoming(today, horizon=HORIZON):
    end = today + dt.timedelta(days=horizon)
    win = [e for e in all_events(today) if e[1] >= today and e[0] <= end]
    win.sort(key=lambda e: e[0])
    return win


def main():
    today = dt.date.today()
    horizon = HORIZON
    if "--days" in sys.argv:
        try:
            horizon = int(sys.argv[sys.argv.index("--days") + 1])
        except (ValueError, IndexError):
            pass
    win = upcoming(today, horizon)
    print("=== 테마 카탈리스트 캘린더 (오늘 %s ~ +%d일) ===" % (today, horizon))
    print("'미리 자리잡기' 참고 — 매수신호 아님. 일정 = 계산형(자동) + 고정일(web/수기)\n")
    for s, e, ev, th in win:
        when = s.isoformat() if s == e else "%s~%s" % (s, e)
        d2 = (s - today).days
        print("  %-23s (D%+d) %-32s | %s" % (when, d2, ev, th))
    print("\n총 %d건. 고정일(FOMC·금통위·확정 실적일)은 theme_calendar_fixed.csv에 추가하면 병합." % len(win))


def self_test():
    today = dt.date(2026, 6, 7)
    win = upcoming(today, 90)
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot
        tot += 1; ok += 1 if c else 0
        print("  [%s] %s" % ("OK" if c else "FAIL", n))
    chk("이벤트 존재", len(win) > 0)
    chk("한국 Q2 실적시즌 포함(7~8월)", any("한국 분기실적" in e[2] and e[0].month in (7, 8) for e in win))
    chk("美 빅테크 실적 포함", any("빅테크" in e[2] for e in win))
    chk("정렬(오름차순)", all(win[i][0] <= win[i + 1][0] for i in range(len(win) - 1)))
    chk("과거 이벤트 제외", all(e[1] >= today for e in win))
    print("self-test: %d/%d" % (ok, tot))
    return ok == tot


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        main()
