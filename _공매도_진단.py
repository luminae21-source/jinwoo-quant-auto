#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""_공매도_진단.py — 어떤 공매도 함수가 이 환경/pykrx버전에서 실제로 되는지 확인(PC).
   삼성전자(005930)로 2024-01 한 달치 시도 → OK/실패·컬럼 출력."""
import sys
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
from pykrx import stock
FS, FE, TK = "20240102", "20240131", "005930"
fns = ["get_shorting_balance_by_date", "get_shorting_status_by_date",
       "get_shorting_volume_by_date", "get_shorting_value_by_date"]
for f in fns:
    try:
        df = getattr(stock, f)(FS, FE, TK)
        if df is None or len(df) == 0:
            print(f"{f:38} EMPTY (df 비어있음)")
        else:
            print(f"{f:38} OK  행{len(df)} 컬럼={list(df.columns)}")
    except Exception as e:
        print(f"{f:38} FAIL {type(e).__name__}: {str(e)[:70]}")
print("\n→ OK 뜬 함수 중 '잔고'(수량/금액/비중) 주는 걸로 공매도잔고를 대체 수집하면 됨.")
