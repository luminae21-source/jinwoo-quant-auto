#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
시총_결측월_보수.py — `종목시총_30년.csv` 의 빠진 달을 메운다 (2026-07-27 발견)

── 무엇이 잘못됐나 ────────────────────────────────────────────────
`종목시총_30년.csv` 는 367개월 중 **330개월만** 갖고 있다. 빠진 37개월 중 **30개가 12월**이다.
    1996-12 · 1997-12 · 1998-12 · … · 2025-12   (거의 매년)
    그 밖에 2003-01 · 2006-05 · 2020-04 · 2020-09 · 2022-xx · 2023-xx …

가격 캐시(`_월봉종가캐시_*.csv`)는 **367/367 완전**하다. 시총만 빠졌다.
원인: 최초 30년 백필이 월말을 `12/31`로 잡았는데 KRX는 **연말 휴장**이라 응답이 없고,
그 달을 통째로 건너뛰었다. (현행 `mcap_update.py` 는 `last_trading_on_or_before` 로
8일 역방향 탐색을 하므로 이 문제가 없다 — 다만 **과거 구멍은 메우지 않는다.**)

── 왜 중요한가 ────────────────────────────────────────────────────
시총은 **모든 백테의 유니버스 선택 변수**다. 그 달이 없으면 백테가 그 달을 통째로 건너뛴다.
전종목 동일가중으로 측정한 영향:

    전월(365개월) 사용        CAGR  −4.03%
    시총보유월(328개월)만     CAGR  −2.39%     → **+1.64%p 위로 뜬다**
    누락된 12월 30개 평균 수익 −1.42% (전체 평균 −0.07%)  → 12월은 평균보다 1.35%p 나쁜 달

**즉 30년 백테는 매년 가장 나쁜 달을 빼고 계산돼 왔다.** 룩어헤드와 같은 방향(위로)의 편향이며,
크기는 약 +1.6%p. "30년"이라 부르지만 실제로는 27.5년이다.

── 사용 ───────────────────────────────────────────────────────────
    py 시총_결측월_보수.py --dry      # 네트워크 없이 빠진 달만 출력
    py 시총_결측월_보수.py            # pykrx로 실제 수집 후 append
    py 시총_결측월_보수.py --from 2015-01   # 특정 시점 이후만

안전장치: **append 전용**(기존 이력 불변) · 헤더 검증 · 이미 있는 날짜는 건너뜀 ·
수집 전 `종목시총_30년.csv.bak_보수_<날짜>` 자동 백업.

⚠️ 정보·검증용 · 투자자문 아님
"""
try:  # 윈도 파이프(cp949)에서 이모지 출력 시 UnicodeEncodeError 방지 (2026-07-27)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import csv
import os
import shutil
import sys
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
PANEL = "종목시총_30년.csv"
HEADER = ["date", "code", "mcap"]


def find_panel():
    for b in (ROOT, os.getcwd()):
        p = os.path.join(b, PANEL)
        if os.path.exists(p):
            return p
    sys.exit(f"{PANEL} 을 못 찾음")


def read_months(path):
    """보유 월(YYYY-MM) 집합과 보유 날짜 집합."""
    months, dates = set(), set()
    with open(path, encoding="utf-8-sig", newline="") as f:
        r = csv.reader(f)
        head = next(r)
        if [h.strip().lstrip("﻿") for h in head] != HEADER:
            sys.exit(f"헤더 불일치 — 기대 {HEADER}, 실제 {head}. 안전을 위해 중단.")
        for row in r:
            if not row:
                continue
            d = row[0]
            dates.add(d)
            months.add(d[:7])
    return months, dates


def all_months(first, last):
    y, m = int(first[:4]), int(first[5:7])
    ly, lm = int(last[:4]), int(last[5:7])
    out = []
    while (y, m) <= (ly, lm):
        out.append(f"{y:04d}-{m:02d}")
        m += 1
        if m > 12:
            y += 1
            m = 1
    return out


def month_last_day(ym):
    y, m = int(ym[:4]), int(ym[5:7])
    return date(y + 1, 1, 1) - timedelta(days=1) if m == 12 else date(y, m + 1, 1) - timedelta(days=1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true", help="네트워크 없이 결측월만 출력")
    ap.add_argument("--from", dest="frm", default=None, help="이 월부터만 (예: 2015-01)")
    ap.add_argument("--max-back", type=int, default=10, help="휴장일 역방향 탐색 일수")
    a = ap.parse_args()

    path = find_panel()
    months, dates = read_months(path)
    first, last = min(months), max(months)
    full = all_months(first, last)
    missing = [m for m in full if m not in months]
    if a.frm:
        missing = [m for m in missing if m >= a.frm]

    print("=" * 74)
    print(" 종목시총_30년.csv 결측월 보수")
    print("=" * 74)
    print(f"  구간 {first} ~ {last} · 전체 {len(full)}개월 · 보유 {len(months)} · "
          f"**결측 {len(full)-len(months)}**")
    dec = [m for m in missing if m.endswith("-12")]
    print(f"  대상 결측 {len(missing)}개월 (그중 12월 {len(dec)}개)")
    for i in range(0, len(missing), 12):
        print("    " + " ".join(missing[i:i + 12]))
    if not missing:
        print("\n  ✅ 결측 없음.")
        return 0

    if a.dry:
        print("\n  [DRY] 수집하지 않았다. 실제 보수는 --dry 없이 실행.")
        print("  영향: 시총 결측월은 백테에서 통째로 건너뛰어진다 (측정 +1.64%p 상방 편향).")
        return 0

    try:
        from pykrx import stock
    except ImportError:
        sys.exit("pykrx 미설치 → pip install pykrx")

    sys.path.insert(0, os.path.join(ROOT, "강화키트"))
    try:
        from mcap_update import _fetch_day          # 검증된 수집 로직 재사용
    except Exception as e:
        sys.exit(f"강화키트/mcap_update.py 를 못 불러옴: {e}")

    bak = path + f".bak_보수_{date.today():%m%d}"
    if not os.path.exists(bak):
        shutil.copy2(path, bak)
        print(f"\n  백업: {os.path.basename(bak)}")

    rows, done, failed = [], [], []
    for ym in missing:
        target = month_last_day(ym)
        got = None
        for i in range(a.max_back):
            dd = (target - timedelta(days=i)).strftime("%Y%m%d")
            df = _fetch_day(stock, dd)
            if df is not None and len(df):
                got = (dd, df)
                break
        if not got:
            failed.append(ym)
            print(f"    ❌ {ym} — {a.max_back}일 역탐색 실패")
            continue
        dd, df = got
        ds = f"{dd[:4]}-{dd[4:6]}-{dd[6:8]}"
        if ds in dates:
            print(f"    ⏭  {ym} — {ds} 는 이미 있음")
            continue
        n = 0
        for tkr, mc in zip(df.index, df["_mcap"]):
            try:
                v = float(mc)
            except Exception:
                continue
            if v > 0:
                rows.append((ds, str(tkr).zfill(6), int(v)))
                n += 1
        dates.add(ds)
        done.append(ym)
        print(f"    ✅ {ym} → {ds} · {n:,}종목")

    if not rows:
        print("\n  추가할 행 없음.")
        return 1 if failed else 0

    with open(path, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        for r in rows:
            w.writerow(r)

    print("\n" + "-" * 74)
    print(f"  추가 {len(rows):,}행 · 복구 {len(done)}개월 · 실패 {len(failed)}개월")
    if failed:
        print(f"  실패 목록: {failed}")
    print("\n  ⚠️ 다음 단계 — 시총이 바뀌었으므로 아래를 **반드시** 다시 돌린다:")
    print("     py build_style_panel.py --compare")
    print("     py 롱온리_재산출.py --pool 100")
    print("     py 진우퀀트_게이트.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
