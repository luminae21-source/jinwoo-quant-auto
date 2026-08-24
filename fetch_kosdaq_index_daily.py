#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_kosdaq_index_daily.py — [PC 실행] KOSDAQ 종합지수(KQ11) 일봉 수집(FDR)
목적: 휩쏘 게이트 시장분리 확정 판정 (휩쏘_게이트감사_판정문.md §2 · 열린 과제 §10-2).
      컨테이너에서는 KRX·야후 차단이라 형 PC에서만 받을 수 있다.
산출: kosdaq_index_daily.csv (Date, Close)  ← 휩쏘_게이트감사_검정.py 가 자동으로 문다.
사용:
  pip install finance-datareader pandas
  py fetch_kosdaq_index_daily.py                 # 1996~ (기본)
  py fetch_kosdaq_index_daily.py --start 1996
  py fetch_kosdaq_index_daily.py --self-test     # 오프라인 로직 점검
"""
import sys, os, argparse
BASE = os.path.dirname(os.path.abspath(__file__))


def fetch(start="1996-01-01"):
    import FinanceDataReader as fdr
    import pandas as pd
    s = fdr.DataReader("KQ11", start)["Close"].rename("Close")
    s.index.name = "Date"
    s = s.dropna()
    out = os.path.join(BASE, "kosdaq_index_daily.csv")
    s.to_csv(out, encoding="utf-8-sig")
    print(f"저장: kosdaq_index_daily.csv  {len(s)}행  ({s.index.min().date()}~{s.index.max().date()})")
    print(f"KOSDAQ 최근 종가: {s.iloc[-1]:.1f}")
    # 커버리지 경고: 게이트 특징(252일 고점·min120)은 시작 후 약 6개월부터 유효
    if str(s.index.min().date()) > "1997-06-30":
        print("⚠️ 시작일이 늦다 — 1997~ 초기 이벤트 일부는 시장분리 비교에서 제외된다(스크립트가 자동 처리).")


def self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    chk("BASE 경로 존재", os.path.isdir(BASE))
    chk("출력 파일명", "kosdaq_index_daily.csv".endswith(".csv"))
    print(f"self-test: {ok}/{tot} (KRX 미접속)")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--start", default="1996-01-01")
    a = ap.parse_args()
    if a.self_test: self_test()
    else:
        try: fetch(a.start if len(a.start) > 4 else a.start + "-01-01")
        except Exception:
            import traceback; print("\n===== [에러] 아래 복사 ====="); traceback.print_exc()
            print("\n힌트: pip install finance-datareader pandas")
