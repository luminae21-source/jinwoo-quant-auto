#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""발굴데이터_갱신.py — 발굴툴(jq_discover) 일봉을 30년 패널에서 최신으로 재생성

문제: jq_discover가 쓰는 kospi_pit_daily.csv / kosdaq_pit_daily.csv 가 낡음
      (특히 KOSDAQ가 2024-10에서 멈춰 반도체 장비주 현재 타점을 못 봄) + KOSDAQ에 volume 없음.
해법: 이미 최신인 30년 패널(종목일봉_30년_*.csv, 2026까지·volume 포함)에서
      **현재 거래 중 종목**의 **최근 구간**만 뽑아 pit_daily를 갈아끼운다. 수집·네트워크 불필요.

동작:
  · CUT(기본 2023-01-01) 이후 · 마지막 거래일 >= STILL(기본 2026-07-01, =현재 상장) 종목만
  · 컬럼 date,code,open,high,low,close,volume (jq_discover는 컬럼명으로 읽어 순서 무관)
  · 기존 파일은 .bak_YYYYMMDD 백업

사용:  py 발굴데이터_갱신.py            (재생성)
       py 발굴데이터_갱신.py --self-test
그다음:  py jq_discover.py             (안정)  /  py jq_discover.py --breakout  (진우 스타일)
"""
import os, sys, argparse, shutil
from datetime import date
import pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

CUT_DEFAULT = "2023-01-01"      # 지표(MA200·52주고가·60일변동) 충분
STILL_DEFAULT = "2026-07-01"    # 이 날 이후 거래 = 현재 상장(상폐·중단 제외)
JOBS = [("KOSPI", "종목일봉_30년_KOSPI.csv", "kospi_pit_daily.csv"),
        ("KOSDAQ", "종목일봉_30년_KOSDAQ.csv", "kosdaq_pit_daily.csv")]
OUT_COLS = ["date", "code", "open", "high", "low", "close", "volume"]


def regen_one(market, src, out, cut, still):
    sp = os.path.join(HERE, src)
    if not os.path.exists(sp):
        print(f"  [건너뜀] {src} 없음"); return None
    # 큰 파일 → 청크로 읽어 메모리 절약, 문자열 날짜 비교(빠름)
    keep = []
    for ch in pd.read_csv(sp, dtype={"code": str}, encoding="utf-8-sig",
                          usecols=OUT_COLS, chunksize=1_000_000):
        ch = ch[(ch["date"] >= cut) & (ch["close"] > 0)]
        if len(ch): keep.append(ch)
    if not keep:
        print(f"  [{market}] 최근 데이터 없음"); return None
    d = pd.concat(keep, ignore_index=True)
    last = d.groupby("code")["date"].transform("max")
    d = d[last >= still]                                  # 현재 상장만
    d = d.sort_values(["code", "date"])[OUT_COLS]
    op = os.path.join(HERE, out)
    if os.path.exists(op):
        shutil.copy2(op, op + ".bak_" + date.today().strftime("%Y%m%d"))
    d.to_csv(op, index=False, encoding="utf-8-sig")
    print(f"  [{market}] {out}: {len(d):,}행 · {d['code'].nunique()}종목 · "
          f"{d['date'].min()}~{d['date'].max()} ({d['date'].nunique()}거래일)")
    return d


def _self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    # 문자열 날짜 비교가 정렬과 일치하는지
    chk("문자열 날짜 비교 정합", "2023-01-01" < "2026-07-13" and "2024-10-04" < "2026-07-01")
    # 청크 로직 축소판
    df = pd.DataFrame({"date": ["2022-05-01", "2023-06-01", "2026-07-13", "2026-07-13"],
                       "code": ["A", "A", "A", "B"], "open": 1, "high": 1, "low": 1,
                       "close": [10, 10, 10, 10], "volume": [5, 5, 5, 5]})
    d = df[(df["date"] >= "2023-01-01") & (df["close"] > 0)]
    last = d.groupby("code")["date"].transform("max")
    d2 = d[last >= "2026-07-01"]
    chk("옛날행(2022) 제외", (d2["date"] >= "2023-01-01").all())
    chk("현재상장 A(마지막 2026-07-13) 포함", "A" in set(d2["code"]))
    chk("B도 포함(2026-07-13)", "B" in set(d2["code"]))
    chk("출력 컬럼 정합", list(d2.columns) == OUT_COLS)
    # 상폐 시나리오: 마지막이 2024면 제외
    df2 = pd.DataFrame({"date": ["2023-06-01", "2024-10-04"], "code": ["X", "X"],
                        "open": 1, "high": 1, "low": 1, "close": [9, 9], "volume": [1, 1]})
    last2 = df2.groupby("code")["date"].transform("max")
    chk("2024에 멈춘 종목(상폐) 제외", len(df2[last2 >= "2026-07-01"]) == 0)
    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cut", default=CUT_DEFAULT)
    ap.add_argument("--still", default=STILL_DEFAULT)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return 0 if _self_test() else 1
    print("=" * 68)
    print("발굴 일봉 갱신 — 30년 패널 → pit_daily (현재상장·최근구간·volume포함)")
    print("=" * 68)
    checks = {"089030": "테크윙", "036930": "주성엔지니어링", "247540": "에코프로비엠"}
    got = {}
    for market, src, out in JOBS:
        d = regen_one(market, src, out, a.cut, a.still)
        if d is not None:
            for c in checks:
                sub = d[d["code"] == c]
                if len(sub): got[c] = sub["date"].max()
    print("\n진우 관심종목 최신 데이터:")
    for c, nm in checks.items():
        print(f"  {nm}({c}): {got.get(c, '없음(유니버스 밖이거나 상폐)')}")
    print("\n다음: py jq_discover.py            (안정 모드)")
    print("      py jq_discover.py --breakout  (진우 스타일 고변동)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
