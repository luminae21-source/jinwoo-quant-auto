#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_sox_daily.py — [PC 실행] 필라델피아 반도체지수(SOX) 일봉 수집(FDR).
목적: 후보 F(반도체 사이클 선행신호)용. SOX가 코스피를 선행하는지 테스트할 입력.
무수정: production·L1 불변. 산출: sox_daily.csv (Date, Close).
사용: pip install finance-datareader pandas
      py fetch_sox_daily.py            # 2010~
      py fetch_sox_daily.py --start 2005
      py fetch_sox_daily.py --self-test
"""
import sys, os, argparse
BASE = os.path.dirname(os.path.abspath(__file__))
CANDS = ["SOX", "^SOX", "SOXX"]   # SOX 지수 → 안되면 SOXX(반도체 ETF) 대용

def fetch(start="2010-01-01"):
    import FinanceDataReader as fdr, pandas as pd
    last = None
    for t in CANDS:
        try:
            s = fdr.DataReader(t, start)["Close"].rename("Close").dropna()
            if len(s) > 100:
                s.index.name = "Date"; s.to_csv(os.path.join(BASE, "sox_daily.csv"), encoding="utf-8-sig")
                print(f"저장: sox_daily.csv ({t})  {len(s)}행  ({s.index.min().date()}~{s.index.max().date()})  최근 {s.iloc[-1]:.1f}")
                return
        except Exception as e:
            last = e; print(f"  {t} 실패: {e}")
    print("모든 후보 실패:", last, "\n힌트: pip install finance-datareader")

def self_test():
    print("  [OK] BASE", os.path.isdir(BASE)); print("  [OK] 후보", CANDS); print("self-test OK(KRX 미접속)")

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--self-test", action="store_true"); ap.add_argument("--start", default="2010-01-01")
    a = ap.parse_args()
    if a.self_test: self_test()
    else:
        try: fetch(a.start if len(a.start) > 4 else a.start + "-01-01")
        except Exception:
            import traceback; traceback.print_exc(); print("힌트: pip install finance-datareader pandas")
