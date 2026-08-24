#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우_일봉_증분수집.py — [PC 실행] 30년 패널에 최근 빠진 날만 이어붙임(증분·빠름)

목적: 매일 자동 갱신용. 전체 30년 재수집(fetch_stock_panel_30y, 무거움) 대신
      패널 마지막날 다음~오늘의 영업일만 pykrx 날짜별 수집해 append.
방식(생존편향 무관): pykrx.stock.get_market_ohlcv(날짜, market) = 그날 거래된 전 종목.
산출: 종목일봉_30년_KOSPI/KOSDAQ.csv 뒤에 추가 · kospi_index_daily.csv 갱신(FDR).
사용:  py 진우_일봉_증분수집.py            (증분 수집)
       py 진우_일봉_증분수집.py --self-test (네트워크 없이 로직 점검)
※ pykrx·finance-datareader 필요. 네트워크는 PC에서. 그다음: 발굴데이터_갱신 → 발굴 실행.
"""
import os, sys, argparse, io
from datetime import date, timedelta
HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
PANELS = {"KOSPI": "종목일봉_30년_KOSPI.csv", "KOSDAQ": "종목일봉_30년_KOSDAQ.csv"}
COLS = ["date", "code", "open", "high", "low", "close", "volume"]

def last_date(path):
    """파일 끝에서 마지막 날짜(YYYY-MM-DD) 읽기."""
    if not os.path.exists(path): return None
    with open(path, "rb") as f:
        f.seek(0, 2); size = f.tell(); step = min(4096, size); f.seek(size-step)
        tail = f.read().decode("utf-8-sig", "ignore").strip().split("\n")
    for line in reversed(tail):
        c = line.split(",")
        if c and len(c[0]) == 10 and c[0][4] == "-":
            return c[0]
    return None

def biz_days(start, end):
    """start(제외)~end(포함) 영업일(월~금). 공휴일은 pykrx가 빈 결과로 처리."""
    out = []; d = start + timedelta(days=1)
    while d <= end:
        if d.weekday() < 5: out.append(d)
        d += timedelta(days=1)
    return out

def fetch_incremental():
    try:
        from pykrx import stock
    except Exception:
        print("[필요] pip install pykrx  (PC에서 실행)"); return 2
    import pandas as pd
    today = date.today()
    for mk, fn in PANELS.items():
        p = os.path.join(HERE, fn)
        ld = last_date(p)
        if ld is None:
            print(f"  [{mk}] 패널 없음 — 먼저 fetch_stock_panel_30y.py"); continue
        start = date.fromisoformat(ld)
        days = biz_days(start, today)
        if not days:
            print(f"  [{mk}] 최신({ld}) — 추가 없음"); continue
        print(f"  [{mk}] {ld} 이후 {len(days)}영업일 수집...")
        added = 0
        with open(p, "a", encoding="utf-8", newline="") as f:
            for d in days:
                ymd = d.strftime("%Y%m%d")
                try:
                    df = stock.get_market_ohlcv(ymd, market=mk)
                except Exception:
                    continue
                if df is None or len(df) == 0: continue    # 휴장일
                df = df.reset_index()
                # pykrx 컬럼: 티커, 시가,고가,저가,종가,거래량
                ren = {"티커": "code", "시가": "open", "고가": "high", "저가": "low", "종가": "close", "거래량": "volume"}
                df = df.rename(columns=ren)
                df["date"] = d.strftime("%Y-%m-%d")
                df["code"] = df["code"].astype(str).str.zfill(6)
                df = df[df["close"] > 0]
                for r in df[COLS].itertuples(index=False):
                    f.write(",".join(str(x) for x in r) + "\n")
                added += len(df)
        print(f"  [{mk}] +{added}행")
    # 지수(FDR)
    try:
        import FinanceDataReader as fdr
        ip = os.path.join(HERE, "kospi_index_daily.csv")
        ild = last_date(ip)
        if ild:
            k = fdr.DataReader("KS11", ild)
            k = k[k.index > ild] if len(k) else k
            if len(k):
                with open(ip, "a", encoding="utf-8", newline="") as f:
                    for idx, row in k.iterrows():
                        f.write(f"{idx.strftime('%Y-%m-%d')},{row['Close']}\n")
                print(f"  [KOSPI지수] +{len(k)}행")
    except Exception as e:
        print(f"  [지수] 건너뜀({str(e)[:30]})")
    print("완료. 다음: py 발굴데이터_갱신.py → 진우사냥터_발굴_실행.bat")
    return 0

def _self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    # biz_days: 금~다음주 화 → 월,화 2일
    bd = biz_days(date(2026, 7, 10), date(2026, 7, 14))  # 금~화
    chk("영업일 계산(주말 제외)", [d.day for d in bd] == [13, 14])
    chk("같은날이면 빈 리스트", biz_days(date(2026, 7, 13), date(2026, 7, 13)) == [])
    # last_date: 임시파일
    import tempfile
    tp = os.path.join(tempfile.mkdtemp(), "t.csv")
    open(tp, "w", encoding="utf-8").write("date,code,open,high,low,close,volume\n2026-07-13,005930,1,2,1,2,100\n")
    chk("마지막날 읽기", last_date(tp) == "2026-07-13")
    chk("없는 파일 None", last_date("/nope/x.csv") is None)
    print(f"\n셀프테스트: {ok}/{tot}"); return ok == tot

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    return fetch_incremental()

if __name__ == "__main__":
    sys.exit(main())
