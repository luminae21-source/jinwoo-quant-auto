#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""거래대금_2주_수집.py — 최근 12영업일 실제 거래대금 + 최근 OHLC 수집(오늘 포함)

목적:
  · KRX에서 최근 12영업일 전 종목 OHLCV+거래대금을 by-date로 받아
  · 종목별 2주(최근 10영업일) 거래대금 합/일평균/추세를 정밀 집계
  · 30년 패널(~07-13) 이후 공백(07-14·오늘)을 메울 최근 OHLC도 함께 저장
  → 샌드박스에서 726종목 캔들(오늘 봉 포함) + 갤러리 조립에 사용.

수집·영업일 보정은 오늘_상승종목_분류.py 재활용.

산출:
  가상매매\검증\_거래대금2주_YYYYMMDD.csv   (code,name,market,거래대금2주합,일평균거래대금,최근5합,이전5합,추세배수,최근일거래대금)
  가상매매\검증\_recent_ohlc_YYYYMMDD.csv   (date,code,open,high,low,close,volume,거래대금)

사용:
  py 거래대금_2주_수집.py
  py 거래대금_2주_수집.py --date 20260715
  py 거래대금_2주_수집.py --days 12
  py 거래대금_2주_수집.py --self-test
"""
import os, sys, argparse, importlib.util
from datetime import datetime
import warnings
warnings.filterwarnings("ignore")

BASE = os.path.dirname(os.path.abspath(__file__))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _load_base():
    p = os.path.join(BASE, "오늘_상승종목_분류.py")
    spec = importlib.util.spec_from_file_location("jq_today_base", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

base = _load_base()
OUTDIR = base.OUTDIR


def collect(pd, stock, days):
    """days: YYYYMMDD 리스트(오름차순). by-date OHLCV+거래대금 수집."""
    rows = []
    for d in days:
        got = 0
        for mkt in ("KOSPI", "KOSDAQ"):
            try:
                oh = stock.get_market_ohlcv(d, market=mkt)
            except Exception:
                oh = None
            if oh is None or len(oh) == 0:
                continue
            oh = oh.rename(columns={"시가": "open", "고가": "high", "저가": "low",
                                    "종가": "close", "거래량": "volume", "거래대금": "value"})
            dd = pd.to_datetime(d)
            for c in oh.index:
                r = oh.loc[c]
                try:
                    val = float(r.get("value", 0) or 0)
                    vol = float(r.get("volume", 0) or 0)
                    cl = float(r.get("close", 0) or 0)
                except Exception:
                    continue
                if cl <= 0:
                    continue
                rows.append({"date": dd, "code": str(c).zfill(6), "market": mkt,
                             "open": float(r.get("open", cl) or cl), "high": float(r.get("high", cl) or cl),
                             "low": float(r.get("low", cl) or cl), "close": cl,
                             "volume": vol, "value": val})
                got += 1
        print(f"  {d}: {got}종목")
    return pd.DataFrame(rows)


def aggregate(pd, df, last_n=10):
    """종목별 최근 last_n 영업일 거래대금 집계 + 추세."""
    out = []
    for c, sub in df.groupby("code"):
        sub = sub.sort_values("date")
        v = sub["value"].tail(last_n)
        if len(v) == 0:
            continue
        tot = float(v.sum())
        avg = float(v.mean())
        half = max(1, len(v) // 2)
        recent = float(v.tail(half).sum())
        prev = float(v.iloc[:-half].sum()) if len(v) > half else float("nan")
        trend = (recent / prev) if (prev and prev > 0) else float("nan")
        out.append({"code": c, "market": sub["market"].iloc[-1],
                    "거래대금2주합": tot, "일평균거래대금": avg,
                    "최근5합": recent, "이전5합": prev, "추세배수": trend,
                    "최근일거래대금": float(v.iloc[-1])})
    return pd.DataFrame(out).sort_values("거래대금2주합", ascending=False)


def _self_test():
    import pandas as pd, numpy as np
    ok = tot = 0

    def chk(n, c):
        nonlocal ok, tot
        tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")

    d = pd.bdate_range("2026-06-01", periods=10)
    df = pd.DataFrame({"date": list(d) * 1, "code": ["A"] * 10, "market": ["KOSPI"] * 10,
                       "open": 100, "high": 100, "low": 100, "close": 100,
                       "volume": 10, "value": [1, 1, 1, 1, 1, 2, 2, 2, 2, 2]})
    ag = aggregate(pd, df, last_n=10)
    ra = ag.iloc[0]
    chk("2주합 = 15", abs(ra["거래대금2주합"] - 15) < 1e-6)
    chk("일평균 = 1.5", abs(ra["일평균거래대금"] - 1.5) < 1e-6)
    chk("추세배수 = 최근5/이전5 = 10/5 = 2", abs(ra["추세배수"] - 2.0) < 1e-6)
    chk("base 재활용(_prev_trading_days)", hasattr(base, "_prev_trading_days"))
    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--days", type=int, default=12)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return 0 if _self_test() else 1

    import pandas as pd
    ymd = a.date or datetime.now().strftime("%Y%m%d")
    print(f"[1/3] 영업일 보정 + 최근 {a.days}영업일 산출...")
    try:
        from pykrx import stock
    except ImportError:
        print("  pykrx 없음. pip install pykrx"); return 2
    days = base._prev_trading_days(pd, stock, ymd, n=a.days)
    if not days:
        print("  영업일 산출 실패"); return 2
    print(f"  대상일: {days[0]} ~ {days[-1]} ({len(days)}일)")

    print("[2/3] by-date OHLCV+거래대금 수집...")
    df = collect(pd, stock, days)
    if df is None or len(df) == 0:
        print("  데이터 없음"); return 2
    print(f"  {len(df):,}행 · {df['code'].nunique()}종목")

    print("[3/3] 2주 거래대금 집계 + 저장...")
    ag = aggregate(pd, df, last_n=min(10, len(days)))
    names = base.load_names(pd)
    ag["name"] = ag["code"].map(lambda c: (names.get(c, {}) or {}).get("name", ""))
    os.makedirs(OUTDIR, exist_ok=True)
    ymd_out = days[-1]
    ap1 = os.path.join(OUTDIR, f"_거래대금2주_{ymd_out}.csv")
    ap2 = os.path.join(OUTDIR, f"_recent_ohlc_{ymd_out}.csv")
    ag[["code", "name", "market", "거래대금2주합", "일평균거래대금", "최근5합", "이전5합",
        "추세배수", "최근일거래대금"]].to_csv(ap1, index=False, encoding="utf-8-sig")
    df[["date", "code", "open", "high", "low", "close", "volume", "value"]].to_csv(
        ap2, index=False, encoding="utf-8-sig")
    print(f"\n  ✅ {ap1}")
    print(f"  ✅ {ap2}")
    print(f"  거래대금 상위 5:")
    for _, r in ag.head(5).iterrows():
        print(f"    {r['name']}({r['code']}) 2주 {r['거래대금2주합']/1e8:,.0f}억 · 추세 {r['추세배수']:.2f}x")
    return 0


if __name__ == "__main__":
    sys.exit(main())
# end
