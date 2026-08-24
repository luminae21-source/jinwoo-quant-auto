#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_attribution_daily.py — attribution(영역4) 일봉 수집 → attribution_pit_daily.csv (커밋용).
**pykrx 사용** (FDR은 진우 PC/병원망 차단). KOSPI지수(1001)+v3.7.2 18종+섹터ETF 11개 종가 수집.
한번 수집·커밋하면 attribution_v40_phase1/2가 오프라인으로 분해(FDR 호출 회피).
PC 전용. 사용: pip install pykrx → python fetch_attribution_daily.py [--start 2023-06-01] / --selftest"""
import sys, time, datetime, pathlib
import numpy as np
import pandas as pd

BASE = pathlib.Path(__file__).parent.resolve()
OUT = BASE / "attribution_pit_daily.csv"
KOSPI_IDX = "1001"  # pykrx KOSPI 종합지수
SECTOR_ETFS = ["091160", "305720", "244580", "091180", "157490", "091170",
               "102970", "449450", "434730", "228790", "266410"]


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


def code_name_map():
    """v37_2_scores_latest.csv → {코드(6자리): 종목명} (18종)."""
    sc = load("v37_2_scores_latest.csv", dtype={"코드": str})
    if sc is None or "코드" not in sc.columns or "종목" not in sc.columns:
        return {}
    return {str(c).split(".")[0].zfill(6): n for c, n in zip(sc["코드"], sc["종목"]) if pd.notna(c)}


def _panel_from_df(df, c2n):
    """long(code,date,close) → fetch_returns_panel 동치: 로그수익률 df, columns=['_KOSPI', 종목명...]."""
    if df is None or not len(df):
        return None
    df = df.copy()
    df["code"] = df["code"].astype(str).str.split(".").str[0]
    px = df.pivot_table(index="date", columns="code", values="close", aggfunc="last").sort_index()
    px.index = pd.to_datetime(px.index)
    ren = {KOSPI_IDX: "_KOSPI"}
    ren.update(c2n)
    px = px.rename(columns=ren)
    keep = [c for c in (["_KOSPI"] + list(c2n.values())) if c in px.columns]
    if "_KOSPI" not in keep:
        return None
    rets = np.log(px[keep] / px[keep].shift(1)).dropna(how="all")
    return rets


def load_panel_from_csv():
    """attribution_pit_daily.csv 있으면 로그수익률 패널 반환(없으면 None → FDR 폴백)."""
    df = load("attribution_pit_daily.csv", dtype={"code": str}, low_memory=False)
    if df is None:
        return None
    df.columns = [c.strip().lower() for c in df.columns]
    if not {"code", "date", "close"} <= set(df.columns):
        return None
    return _panel_from_df(df, code_name_map())


def load_sector_from_csv(codes):
    """섹터 ETF 로그수익률 df(columns=ETF코드). 없으면 None."""
    df = load("attribution_pit_daily.csv", dtype={"code": str}, low_memory=False)
    if df is None:
        return None
    df.columns = [c.strip().lower() for c in df.columns]
    if not {"code", "date", "close"} <= set(df.columns):
        return None
    df["code"] = df["code"].astype(str).str.split(".").str[0]
    want = [c for c in set(codes) if c in set(df["code"])]
    if not want:
        return None
    px = df[df["code"].isin(want)].pivot_table(index="date", columns="code", values="close", aggfunc="last").sort_index()
    px.index = pd.to_datetime(px.index)
    return np.log(px / px.shift(1)).dropna(how="all")


def run(start):
    try:
        from pykrx import stock
    except ImportError:
        print("⚠ pykrx 미설치 → pip install pykrx (PC)"); return
    c2n = code_name_map()
    if not c2n:
        print("v37_2_scores_latest.csv 없음 — 18종 매핑 불가"); return
    end = datetime.date.today().isoformat().replace("-", "")
    sk = start.replace("-", "")
    rows = []; ok = 0; fail = []
    KO = {"시가": "open", "고가": "high", "저가": "low", "종가": "close", "거래량": "volume"}
    # KOSPI 지수
    try:
        idx = stock.get_index_ohlcv(sk, end, KOSPI_IDX).rename(columns=KO)
        for d, r in idx.iterrows():
            rows.append((KOSPI_IDX, d.strftime("%Y-%m-%d"), float(r["close"])))
        ok += 1
    except Exception as e:
        print("KOSPI 지수 실패:", e)
    # 18종 + 섹터 ETF
    for code in list(c2n.keys()) + SECTOR_ETFS:
        try:
            df = stock.get_market_ohlcv(sk, end, code).rename(columns=KO)
            if df is None or len(df) < 60 or "close" not in df.columns:
                fail.append(code); continue
            for d, r in df.iterrows():
                c = float(r["close"])
                if c > 0:
                    rows.append((str(code).zfill(6), d.strftime("%Y-%m-%d"), c))
            ok += 1
        except Exception:
            fail.append(code)
        time.sleep(0.3)
    if not rows:
        print("수집 실패(전부)"); return
    out = pd.DataFrame(rows, columns=["code", "date", "close"])
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    print("생성: %s (%d계열 %d행, %s~%s)" % (OUT.name, ok, len(out), out["date"].min(), out["date"].max()))
    if fail:
        print("실패/부족:", fail)
    print("→ 이제 `python attribution_v40_phase2.py --save-json --save-html` 가 오프라인 분해 (CSV 읽음)")


def _selftest():
    # 합성 long: KOSPI + 1종목(삼성전자 005930) 200일
    idx = pd.date_range("2024-01-01", periods=200, freq="B")
    rows = []
    for i, d in enumerate(idx):
        rows.append((KOSPI_IDX, d.strftime("%Y-%m-%d"), 2000 + i))
        rows.append(("005930", d.strftime("%Y-%m-%d"), 70000 + i * 50))
        rows.append(("091160", d.strftime("%Y-%m-%d"), 30000 + i * 20))  # 반도체 ETF
    df = pd.DataFrame(rows, columns=["code", "date", "close"])
    pan = _panel_from_df(df, {"005930": "삼성전자"})
    assert pan is not None and "_KOSPI" in pan.columns and "삼성전자" in pan.columns, pan.columns.tolist()
    assert len(pan) >= 195 and pan["삼성전자"].notna().sum() > 190
    # 섹터 로더(직접 df 경로 — _panel 아닌 pivot 로직 동일 검증)
    df["code"] = df["code"].astype(str)
    px = df[df["code"] == "091160"].pivot_table(index="date", columns="code", values="close")
    assert len(px) == 200
    print("✅ fetch_attribution_daily self-test 통과 (3): 패널변환·_KOSPI·종목명·섹터pivot")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        start = "2023-06-01"
        if "--start" in sys.argv:
            start = sys.argv[sys.argv.index("--start") + 1]
        run(start)
