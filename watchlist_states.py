#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""watchlist_states.py — 진입 상태머신 자동연동 (chart_timing glue).
워치리스트 실종목 → 일봉(커밋 CSV 우선, 없으면 FDR) → 주봉 OHLCV → 26주 시장초과 RS + regime
→ entry_signals.plan() → 5단계(관찰만/셋업/임박/돌파확인) → kosdaq_watchlist_states.csv.
오프라인: watchlist_pit_daily.csv·kosdaq_pit_daily.csv 있으면 FDR 없이 산출(시장=kosdaq EW 프록시).
정직: 발굴≠매수. 상태=규율층, 매수신호 아님. entry_signals.plan() 무수정 호출.
사용: python watchlist_states.py [--selftest]"""
import sys, datetime, pathlib
import pandas as pd
import entry_signals as ES

BASE = pathlib.Path(__file__).parent.resolve()
OUT = BASE / "kosdaq_watchlist_states.csv"
DAILY_CSVS = ["watchlist_pit_daily.csv", "kosdaq_pit_daily.csv"]  # 커밋 일봉 소스(code,date,ohlc[,v])
STATE_UI = {"WATCH": "관찰만", "SETUP": "셋업", "NEAR": "임박",
            "BREAKOUT": "돌파확인", "BREAKOUT_LOWVOL": "돌파(거래량미달)"}


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


def load_daily_csvs():
    """커밋 일봉 CSV들 합쳐 {code: daily_df(open..close[,volume], DatetimeIndex)} 1회 로드."""
    frames = []
    for f in DAILY_CSVS:
        d = load(f, dtype={"code": str}, low_memory=False)
        if d is None:
            continue
        d.columns = [c.strip().lower() for c in d.columns]
        if "code" in d.columns and "date" in d.columns:
            d["code"] = d["code"].astype(str).str.split(".").str[0].str.zfill(6)
            d["date"] = pd.to_datetime(d["date"], errors="coerce")
            frames.append(d.dropna(subset=["date"]))
    if not frames:
        return None
    return pd.concat(frames, ignore_index=True)


def daily_from_csv(allcsv, code):
    if allcsv is None:
        return None
    s = allcsv[allcsv["code"] == code].sort_values("date").drop_duplicates("date", keep="last").set_index("date")
    cols = [c for c in ("open", "high", "low", "close", "volume") if c in s.columns]
    return s[cols] if len(s) else None


def to_weekly(daily):
    if daily is None or not len(daily):
        return None
    d = daily.rename(columns=str.lower)
    d.index = pd.to_datetime(d.index)
    for c in ("open", "high", "low", "close"):
        if c not in d.columns:
            return None
    w = pd.DataFrame({
        "open": d["open"].resample("W-FRI").first(),
        "high": d["high"].resample("W-FRI").max(),
        "low": d["low"].resample("W-FRI").min(),
        "close": d["close"].resample("W-FRI").last(),
    })
    if "volume" in d.columns:
        w["volume"] = d["volume"].resample("W-FRI").sum()
    return w.dropna(subset=["close"])


def rs26(sc, mc):
    if sc is None or mc is None or len(sc) < 27 or len(mc) < 27:
        return 0.0
    sr = float(sc.iloc[-1]) / float(sc.iloc[-27]) - 1.0
    mr = float(mc.iloc[-1]) / float(mc.iloc[-27]) - 1.0
    return sr - mr


def market_weekly(fdr):
    """시장 주봉 종가. kosdaq_pit_daily EW 프록시 우선(오프라인), 없으면 KQ11 FDR."""
    kos = load("kosdaq_pit_daily.csv", dtype={"code": str}, low_memory=False)
    if kos is not None:
        kos.columns = [c.strip().lower() for c in kos.columns]
        if "date" in kos.columns and "close" in kos.columns and "code" in kos.columns:
            kos["date"] = pd.to_datetime(kos["date"], errors="coerce")
            piv = kos.pivot_table(index="date", columns="code", values="close", aggfunc="last").sort_index()
            ew = piv.pct_change(fill_method=None).mean(axis=1).add(1).cumprod() * 100
            mw = ew.resample("W-FRI").last().dropna()
            if len(mw) >= 30:
                return mw
    if fdr is not None:
        m = to_weekly(fetch_fdr("KQ11", fdr))
        if m is not None:
            return m["close"]
    return None


def fetch_fdr(code, fdr, start="2023-06-01"):
    try:
        return fdr.DataReader(str(code).zfill(6), start)
    except Exception:
        return None


def classify(weekly, rs, regime):
    if weekly is None or len(weekly) < 30:
        return {"state": "WATCH", "state_ui": "관찰만", "n_setup": None,
                "pivot": None, "to_pivot_pct": None, "stop": None, "R": None}
    p = ES.plan(weekly, rs, regime)
    return {"state": p["state"], "state_ui": STATE_UI.get(p["state"], "관찰만"),
            "n_setup": p["n_setup"], "pivot": p["pivot"], "to_pivot_pct": p["to_pivot_pct"],
            "stop": p["stop"], "R": p["R"]}


def latest_regime():
    for f in ("regime_history_v40_kosdaq.csv", "regime_history_v40.csv"):
        r = load(f)
        if r is not None and len(r):
            col = "state" if "state" in r.columns else r.columns[-1]
            v = str(r[col].dropna().iloc[-1]).upper()
            if v in ("RISK_ON", "NEUTRAL", "RISK_OFF"):
                return v
    return "NEUTRAL"


def run():
    wl = load("kosdaq_theme_watchlist_진우기입.csv")
    if wl is None:
        wl = load("kosdaq_theme_watchlist.csv")
    if wl is None or "code" not in wl.columns:
        print("워치리스트 없음"); return
    try:
        import FinanceDataReader as fdr
    except Exception:
        fdr = None
    allcsv = load_daily_csvs()
    mc = market_weekly(fdr)
    regime = latest_regime()
    if allcsv is None and fdr is None:
        print("⚠ 일봉 CSV 없음 + FDR 없음 — 상태 산출 불가(관찰만 폴백). PC에서 fetch_watchlist_daily.py 후 재실행.")
        return
    rows = []; today = datetime.date.today().isoformat(); src_csv = 0; src_fdr = 0; src_none = 0
    for _, r in wl.iterrows():
        code = str(r["code"]).split(".")[0].zfill(6)
        dc = daily_from_csv(allcsv, code)
        if dc is not None:
            wk = to_weekly(dc); src_csv += 1
        elif fdr is not None:
            wk = to_weekly(fetch_fdr(code, fdr)); src_fdr += 1
        else:
            wk = None; src_none += 1
        rs = rs26(wk["close"] if wk is not None else None, mc)
        c = classify(wk, rs, regime)
        rows.append({"code": code, "name": r.get("name", ""), "theme": r.get("theme", ""),
                     "state": c["state"], "state_ui": c["state_ui"], "n_setup": c["n_setup"],
                     "pivot": c["pivot"], "to_pivot_pct": c["to_pivot_pct"], "stop": c["stop"],
                     "R": c["R"], "rs26_%": round(rs * 100, 1), "regime": regime, "asof": today})
    out = pd.DataFrame(rows)
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    dist = out["state_ui"].value_counts().to_dict()
    print("생성: %s (%d종) regime %s · 소스 CSV %d/FDR %d/미산출 %d" % (OUT.name, len(out), regime, src_csv, src_fdr, src_none))
    print("상태 분포:", dist)
    if src_none and not src_fdr:
        print("※ 일부 종목 일봉 없음 → PC에서 fetch_watchlist_daily.py 실행(watchlist_pit_daily.csv 생성)하면 오프라인 산출")


def _selftest():
    import numpy as np
    ok = 0
    idx = pd.date_range("2024-01-01", periods=35 * 7, freq="D")
    dd = pd.DataFrame({"open": range(len(idx)), "high": [x + 2 for x in range(len(idx))],
                       "low": [x - 1 for x in range(len(idx))], "close": range(len(idx)),
                       "volume": [100] * len(idx)}, index=idx)
    w = to_weekly(dd)
    assert w is not None and 33 <= len(w) <= 36 and list(w.columns)[:4] == ["open", "high", "low", "close"]; ok += 1
    sc = pd.Series(list(np.linspace(100, 200, 30))); mc = pd.Series(list(np.linspace(100, 110, 30)))
    assert rs26(sc, mc) > 0 and rs26(mc, sc) < 0; ok += 1
    assert classify(None, 0.1, "RISK_ON")["state_ui"] == "관찰만"; ok += 1
    closes = list(np.linspace(100, 195, 55)) + [196.0, 197, 198, 199, 200]
    assert classify(ES._mk_weekly(closes), 0.3, "RISK_ON")["state_ui"] in ("셋업", "임박", "돌파확인"); ok += 1
    assert classify(ES._mk_weekly(list(np.linspace(200, 100, 60))), -0.2, "RISK_ON")["state_ui"] == "관찰만"; ok += 1
    # CSV 경로: 합성 long-format → daily_from_csv → to_weekly
    long = pd.DataFrame({"code": ["000001"] * len(idx), "date": idx,
                         "open": range(len(idx)), "high": [x + 2 for x in range(len(idx))],
                         "low": [x - 1 for x in range(len(idx))], "close": range(len(idx))})
    dc = daily_from_csv(long, "000001")
    assert dc is not None and to_weekly(dc) is not None; ok += 1
    assert all(k in STATE_UI for k in ES.STATE_KO); ok += 1
    print("✅ watchlist_states self-test 통과 (%d/7): 주봉·RS·폴백·상승·하락·CSV경로·매핑" % ok)


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        _selftest()
    else:
        run()
