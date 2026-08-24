# -*- coding: utf-8 -*-
"""미국주식 장기지도 트랙 — 1단계 데이터 수집 (2026-08-22)
시작지시서 §3 기준. 대상은 사전 고정(사후 추가 금지):
  AAPL MSFT NVDA GOOGL AMZN META TSLA AVGO + 벤치마크 ^GSPC ^IXIC SPY QQQ

[실제 수집 경로 기록 — 2026-08-22]
  Cowork 컨테이너·PC 셸 모두 stooq.com / yahoo 에 프록시 403 → 1·2순위 불가.
  → 형 Chrome(Claude in Chrome)에서 Yahoo chart API v8를 직접 호출해
    일봉(OHLC, close, adjclose, volume) + 분할/배당 이벤트를 받아 zip으로 내려받고
    진우퀀트/미국_일봉/ 에 풀었다. (README.txt 에 출처 명시)
  adjclose = 배당·분할 조정 (Yahoo 표준). close = 분할만 반영된 원주가.

[재수집용 — 네트워크가 열린 PC에서 실행]
  python 미국주식_수집.py            # yfinance 경로
  python 미국주식_수집.py --stooq    # stooq 경로
산출 형식은 브라우저 수집분과 동일: date,open,high,low,close,adjclose,volume
"""
import sys, os, io
import pandas as pd

TICKERS = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO",
           "^GSPC", "^IXIC", "SPY", "QQQ"]
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "미국_일봉")

def fname(t):
    return t.replace("^", "IDX_") + ".csv"

def via_yfinance():
    import yfinance as yf
    for t in TICKERS:
        raw = yf.download(t, start="1970-01-01", auto_adjust=False, progress=False)
        if raw.empty:
            print("[skip]", t); continue
        if isinstance(raw.columns, pd.MultiIndex):
            raw.columns = raw.columns.get_level_values(0)
        df = pd.DataFrame({
            "date": raw.index.strftime("%Y-%m-%d"),
            "open": raw["Open"].values, "high": raw["High"].values,
            "low": raw["Low"].values, "close": raw["Close"].values,
            "adjclose": raw["Adj Close"].values, "volume": raw["Volume"].values})
        df.to_csv(os.path.join(OUT, fname(t)), index=False)
        print("[ok]", t, len(df), df["date"].iloc[0], df["date"].iloc[-1])

def via_stooq():
    import urllib.request
    for t in TICKERS:
        s = t.lower().replace("^gspc", "^spx").replace("^ixic", "^ndq")
        if not s.startswith("^"):
            s += ".us"
        url = f"https://stooq.com/q/d/l/?s={s}&i=d"
        raw = pd.read_csv(io.BytesIO(urllib.request.urlopen(url, timeout=30).read()))
        raw.columns = [c.lower() for c in raw.columns]
        # stooq 는 분할 조정 close 만 제공(배당 미조정) → adjclose=close 로 두고 리포트에 고지
        df = raw.rename(columns={"date": "date"})[["date", "open", "high", "low", "close", "volume"]]
        df["adjclose"] = df["close"]
        df = df[["date", "open", "high", "low", "close", "adjclose", "volume"]]
        df.to_csv(os.path.join(OUT, fname(t)), index=False)
        print("[ok]", t, len(df))

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    if "--stooq" in sys.argv:
        via_stooq()
    else:
        via_yfinance()
