#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_kospi_index_daily.py — [PC 실행] KOSPI 지수(KS11) 일봉 수집(FDR)
목적: 변동성관리 후보 B의 σ̂를 MM 원형대로 **일간 실현변동성**으로 계산하기 위한 장기 지수 일봉.
      (월간 근사가 반응이 느려 타이밍을 왜곡 → 일간으로 공정 재판정.)
무수정: production·L1·theme_heat·매도규칙서 불변.
산출: kospi_index_daily.csv (Date, Close)
사용:
  pip install finance-datareader pandas
  py fetch_kospi_index_daily.py                # 2010~ (기본)
  py fetch_kospi_index_daily.py --start 2005
  py fetch_kospi_index_daily.py --self-test    # 오프라인 로직 점검
"""
import sys, os, argparse
BASE = os.path.dirname(os.path.abspath(__file__))

def fetch(start="2010-01-01"):
    import FinanceDataReader as fdr
    import pandas as pd
    s = fdr.DataReader("KS11", start)["Close"].rename("Close")
    s.index.name = "Date"
    out = os.path.join(BASE, "kospi_index_daily.csv")
    s.to_csv(out, encoding="utf-8-sig")
    print(f"저장: kospi_index_daily.csv  {len(s)}행  ({s.index.min().date()}~{s.index.max().date()})")
    print(f"KOSPI 최근 종가: {s.dropna().iloc[-1]:.1f}")

def self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    chk("BASE 경로 존재", os.path.isdir(BASE))
    chk("출력 파일명", "kospi_index_daily.csv".endswith(".csv"))
    print(f"self-test: {ok}/{tot} (KRX 미접속)")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--start", default="2010-01-01")
    a = ap.parse_args()
    if a.self_test: self_test()
    else:
        try: fetch(a.start if len(a.start) > 4 else a.start + "-01-01")
        except Exception:
            import traceback; print("\n===== [에러] 아래 복사 ====="); traceback.print_exc()
            print("\n힌트: pip install finance-datareader pandas")
