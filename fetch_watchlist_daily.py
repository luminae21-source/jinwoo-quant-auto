#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_watchlist_daily.py — 워치리스트 종목 일봉 수집 → watchlist_pit_daily.csv (커밋용).
**pykrx 사용** (이 프로젝트 표준; FDR의 KRX 소스는 진우 PC/병원망에서 차단됨 — fetch_kosdaq_pit_pykrx.py 주석 참조).
한번 수집·커밋하면 watchlist_states.py가 오프라인(sandbox/scheduled 포함)으로 5단계 산출.
PC 전용. 사용: pip install pykrx → python fetch_watchlist_daily.py [--start 2023-01-01] / --selftest"""
import sys, time, datetime, pathlib
import pandas as pd

BASE = pathlib.Path(__file__).parent.resolve()
OUT = BASE / "watchlist_pit_daily.csv"
KO = {"시가": "open", "고가": "high", "저가": "low", "종가": "close", "거래량": "volume"}


def load(n, **k):
    p = BASE / n
    if not p.exists():
        return None
    for e in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return pd.read_csv(p, encoding=e, **k)
        except Exception:
            continue
    return None


def watchlist_codes():
    wl = load("kosdaq_theme_watchlist_진우기입.csv", dtype={"code": str})
    if wl is None:
        wl = load("kosdaq_theme_watchlist.csv", dtype={"code": str})
    if wl is None or "code" not in wl.columns:
        return []
    return [str(c).split(".")[0].zfill(6) for c in wl["code"].dropna()]


def ohlcv_to_rows(df, code):
    """pykrx get_market_ohlcv 결과(df) → [(code,date,o,h,l,c,v)] (순수함수, self-test 대상)."""
    if df is None or not len(df):
        return []
    df = df.rename(columns=KO)
    if not {"open", "high", "low", "close"} <= set(df.columns):
        return []
    rows = []
    for idx, r in df.iterrows():
        try:
            o, h, l, c = float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])
        except Exception:
            continue
        if min(o, h, l, c) <= 0:
            continue
        d = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
        v = float(r["volume"]) if "volume" in df.columns and pd.notna(r.get("volume")) else 0
        rows.append((str(code).zfill(6), d, o, h, l, c, v))
    return rows


def run(start):
    codes = watchlist_codes()
    if not codes:
        print("워치리스트 없음"); return
    try:
        from pykrx import stock
    except ImportError:
        print("⚠ pykrx 미설치 → pip install pykrx (PC에서)"); return
    end = datetime.date.today().isoformat().replace("-", "")
    start_k = start.replace("-", "")
    allrows = []; ok = 0; fail = []
    for c in codes:
        try:
            df = stock.get_market_ohlcv(start_k, end, c)
            rows = ohlcv_to_rows(df, c)
            if len(rows) > 60:
                allrows.extend(rows); ok += 1
            else:
                fail.append(c)
        except Exception:
            fail.append(c)
        time.sleep(0.3)  # KRX rate-limit 예의
    if not allrows:
        print("수집 실패(전부) — pykrx/네트워크 확인"); return
    out = pd.DataFrame(allrows, columns=["code", "date", "open", "high", "low", "close", "volume"])
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    print("생성: %s (%d종 %d행, %s~%s)" % (OUT.name, ok, len(out), out["date"].min(), out["date"].max()))
    if fail:
        print("실패/부족:", fail)
    print("→ 이제 `python watchlist_states.py` 가 오프라인으로 5단계 산출 (CSV 읽음)")


def _selftest():
    idx = pd.date_range("2024-01-01", periods=300, freq="B")
    fake = pd.DataFrame({"시가": range(1, len(idx) + 1), "고가": [x + 2 for x in range(1, len(idx) + 1)],
                         "저가": [x for x in range(1, len(idx) + 1)], "종가": range(1, len(idx) + 1),
                         "거래량": [1000] * len(idx)}, index=idx)
    rows = ohlcv_to_rows(fake, "247540")
    assert len(rows) == 300 and rows[0][0] == "247540" and len(rows[0]) == 7, rows[0]
    assert rows[0][1] == "2024-01-01"
    # 0가격/결측 제거
    bad = fake.copy(); bad.iloc[0, :4] = 0
    assert len(ohlcv_to_rows(bad, "000001")) == 299
    print("✅ fetch_watchlist_daily self-test 통과 (2): ohlcv_to_rows 구조·0가격제거")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        start = "2023-01-01"
        if "--start" in sys.argv:
            start = sys.argv[sys.argv.index("--start") + 1]
        run(start)
