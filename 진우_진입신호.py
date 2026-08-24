#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우_진입신호.py — 진입 상태머신 (주봉 SEPA·pivot·상태전이·손절·R·regime)

블루프린트: 진우퀀트_진입상태머신_설계메모_2026-06-14.md §2~6 정식 구현.
정직: 이 층은 '오를 종목 찾기'가 아니라 '이미 보는 종목의 진입 시점·손절을 규율'.
      진입 타이밍은 엣지 아님(검증). 발굴≠매수신호. Track W(사후측정)로만 밥값 측정.

주봉(W-FRI) · MA 10/30/40주 · SEPA 8조건 → 상태:
  WATCH(트렌드템플릿 미충족) → SETUP(8/8+베이스) → NEAR(pivot-3% 이내) → BREAKOUT(종가>pivot).
pivot = 직전 10주 베이스 고점 · 손절 = max(pivot×0.92, 베이스 저점)[RISK_OFF −5.5%]
R = (목표=52주고 − pivot) / (pivot − 손절) · regime = KOSPI 주봉 vs 40주선.
사용: py 진우_진입신호.py [--codes 042700,..] [--self-test]   대상 기본=관심종목+테마.
"""
import os, sys, csv, argparse, io
BASE = os.path.dirname(os.path.abspath(__file__))
RECENT = 500000
BASE_K, DEPTH_MAX, NEAR_X, STOP_HARD, STOP_OFF = 10, 0.25, 0.03, 0.08, 0.055
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def _rr(pd, path, n, cols):
    with open(path, "rb") as f:
        h = f.readline(); f.seek(0, 2); pos = f.tell(); data = b""; nl = 0; blk = 1 << 20
        while pos > 0 and nl <= n:
            s = min(blk, pos); pos -= s; f.seek(pos); data = f.read(s)+data; nl = data.count(b"\n")
    lines = [l for l in data.split(b"\n") if l.strip()]
    return pd.read_csv(io.BytesIO(h+b"\n".join(lines[-n:])), usecols=cols, dtype={"code": str}, encoding="utf-8-sig")

def weekly(pd, g):
    g = g.set_index("date").sort_index()
    w = pd.DataFrame({"open": g["open"].resample("W-FRI").first(),
                      "high": g["high"].resample("W-FRI").max(),
                      "low": g["low"].resample("W-FRI").min(),
                      "close": g["close"].resample("W-FRI").last()}).dropna()
    return w

def sepa(pd, w, rs):
    """SEPA 8조건 → (n충족, dict). 마지막 주 기준."""
    c = w["close"]; ma10 = c.rolling(10).mean(); ma30 = c.rolling(30).mean(); ma40 = c.rolling(40).mean()
    lo52 = w["low"].rolling(52, min_periods=30).min(); hi52 = w["high"].rolling(52, min_periods=30).max()
    i = -1
    def v(s): return float(s.iloc[i])
    conds = {
        "1 종가>30·40주선": c.iloc[i] > v(ma30) and c.iloc[i] > v(ma40),
        "2 30>40주선": v(ma30) > v(ma40),
        "3 40주선 상승": v(ma40) > float(ma40.iloc[-6]) if len(ma40) > 6 else False,
        "4 정배열(10>30>40)": v(ma10) > v(ma30) > v(ma40),
        "5 종가>10주선": c.iloc[i] > v(ma10),
        "6 52주저 +30%↑": c.iloc[i] >= v(lo52)*1.30 if v(lo52) > 0 else False,
        "7 52주고 -25%내": c.iloc[i] >= v(hi52)*0.75 if v(hi52) > 0 else False,
        "8 RS>0(시장초과)": rs is not None and rs > 0,
    }
    n = sum(1 for x in conds.values() if x)
    return n, conds, float(v(hi52))

def analyze(pd, w, rs, regime):
    if len(w) < 52: return None
    n, conds, hi52 = sepa(pd, w, rs)
    base = w.iloc[-(BASE_K+1):-1]                 # 직전 10주(현재주 제외)
    pivot = float(base["high"].max()); base_low = float(base["low"].min())
    depth = (pivot-base_low)/pivot if pivot > 0 else 1
    close = float(w["close"].iloc[-1])
    tmpl_ok = (n == 8)
    if tmpl_ok and close > pivot: state = "BREAKOUT"
    elif tmpl_ok and close >= pivot*(1-NEAR_X): state = "NEAR"
    elif tmpl_ok and depth <= DEPTH_MAX: state = "SETUP"
    else: state = "WATCH"
    stop_pct = STOP_OFF if regime == "RISK_OFF" else STOP_HARD
    stop = int(max(pivot*(1-stop_pct), base_low))
    R = round((hi52-pivot)/(pivot-stop), 2) if pivot > stop and hi52 > pivot else None
    return dict(state=state, n=n, conds=conds, pivot=int(pivot), stop=stop,
                base_low=int(base_low), depth=round(depth*100, 1), close=int(close), R=R, hi52=int(hi52))

def kospi_weekly(pd):
    p = os.path.join(BASE, "kospi_index_daily.csv")
    if not os.path.exists(p): return None
    d = pd.read_csv(p, encoding="utf-8-sig"); d.columns = [c.lstrip("﻿").lower() for c in d.columns]
    d["date"] = pd.to_datetime(d["date"], errors="coerce"); d["close"] = pd.to_numeric(d["close"], errors="coerce")
    d = d.dropna(subset=["date", "close"]).set_index("date")["close"]
    return d.resample("W-FRI").last().dropna()

def load_targets():
    named = {}
    for f, tag in (("진우_관심종목.csv", "관심"),):
        p = os.path.join(BASE, f)
        if os.path.exists(p):
            with open(p, encoding="utf-8-sig") as fh:
                for r in csv.DictReader(fh): named.setdefault(r["code"].zfill(6), r.get("name", ""))
    p = os.path.join(BASE, "kosdaq_theme_chain_map.csv")
    if os.path.exists(p):
        with open(p, encoding="utf-8-sig") as fh:
            for r in csv.DictReader(fh):
                r = {k.lstrip("﻿"): v for k, v in r.items()}
                if r.get("market") != "US": named.setdefault(r["ticker"].zfill(6), r["name"])
    return named

STORD = {"BREAKOUT": 0, "NEAR": 1, "SETUP": 2, "WATCH": 3}

def run(pd, np, codes_named):
    kw = kospi_weekly(pd)
    kospi_rs = None
    reg = "N/A"
    if kw is not None and len(kw) > 40:
        kma40 = kw.rolling(40).mean().iloc[-1]
        reg = "RISK_ON" if kw.iloc[-1] > kma40 else "RISK_OFF"
        kospi_rs26 = kw.iloc[-1]/kw.iloc[-27]-1 if len(kw) > 27 else 0
    else:
        kospi_rs26 = 0
    codes = set(codes_named); frames = []
    for mk in ("KOSPI", "KOSDAQ"):
        p = os.path.join(BASE, f"종목일봉_30년_{mk}.csv")
        if os.path.exists(p):
            d = _rr(pd, p, RECENT, ["date", "code", "open", "high", "low", "close"])
            d["code"] = d["code"].str.zfill(6); d = d[d["code"].isin(codes)]; frames.append(d)
    d = pd.concat(frames, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    for c in ("open", "high", "low", "close"): d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["date", "close"]).sort_values(["code", "date"])
    rows = []
    for code, g in d.groupby("code"):
        w = weekly(pd, g)
        if len(w) < 52: continue
        rs = (float(w["close"].iloc[-1]/w["close"].iloc[-27]-1) - kospi_rs26) if len(w) > 27 else None
        a = analyze(pd, w, rs, reg)
        if a is None: continue
        a.update(code=code, name=codes_named.get(code, code), rs=round(rs*100, 1) if rs is not None else None)
        rows.append(a)
    rows.sort(key=lambda r: (STORD[r["state"]], -(r["n"])))
    return rows, reg

def render(rows, reg):
    print("\n" + "="*96)
    print("진우 진입 상태머신 (주봉 SEPA) — WATCH→SETUP→NEAR→BREAKOUT")
    rl = {"RISK_OFF": "⛔ RISK_OFF: BREAKOUT이어도 진입보류·손절 타이트(-5.5%)",
          "RISK_ON": "정상", "NEUTRAL": "신중"}.get(reg, "-")
    print(f"시장 regime(KOSPI 주봉 vs 40주선): {reg} — {rl}")
    print("발굴≠매수신호 · 진입 타이밍은 엣지 아님(검증) · pivot 돌파는 규율·후보, 결정 본인")
    print("="*96)
    hdr = f"{'종목':<12} {'상태':<9} {'조건':>4} {'현재가':>9} {'pivot(트리거)':>11} {'손절':>9} {'R':>4} {'RS%':>6} {'깊이%':>5}"
    print(hdr); print("-"*84)
    for r in rows:
        star = "🚀" if r["state"] == "BREAKOUT" else ("⏳" if r["state"] == "NEAR" else "")
        Rs = f"{r['R']:.1f}" if r["R"] is not None else "-"
        rs = f"{r['rs']:+.0f}" if r["rs"] is not None else "-"
        lab = r["state"]+("⛔" if (reg == "RISK_OFF" and r["state"] in ("BREAKOUT", "NEAR")) else "")
        print(f"{star}{r['name'][:11]:<11} {lab:<9} {r['n']:>2}/8 {r['close']:>9,} {r['pivot']:>11,} {r['stop']:>9,} {Rs:>4} {rs:>6} {r['depth']:>5.0f}")
    from collections import Counter
    dist = Counter(r["state"] for r in rows)
    print(f"\n분포: BREAKOUT {dist.get('BREAKOUT',0)} · NEAR {dist.get('NEAR',0)} · SETUP {dist.get('SETUP',0)} · WATCH {dist.get('WATCH',0)}")
    print("※ SETUP=살 수 있는 상태(아직 매수점 아님) · NEAR=트리거 임박 · BREAKOUT=매수후보(pivot·손절·R). Track W로 사후측정.")

def _self_test():
    import numpy as np, pandas as pd
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    # 상승추세 합성 주봉 → 상위조건 충족
    idx = pd.date_range("2024-01-05", periods=60, freq="W-FRI")
    up = np.linspace(100, 200, 60)
    w = pd.DataFrame({"open": up, "high": up*1.02, "low": up*0.98, "close": up}, index=idx)
    n, conds, hi52 = sepa(pd, w, 0.1)
    chk("상승추세 SEPA 다수 충족(≥6)", n >= 6)
    chk("52주고 계산", hi52 > 0)
    a = analyze(pd, w, 0.1, "RISK_ON")
    chk("analyze 상태 반환", a is not None and a["state"] in ("BREAKOUT", "NEAR", "SETUP", "WATCH"))
    chk("pivot>손절", a["pivot"] > a["stop"])
    # 하락추세 → WATCH
    dn = np.linspace(200, 100, 60)
    w2 = pd.DataFrame({"open": dn, "high": dn*1.02, "low": dn*0.98, "close": dn}, index=idx)
    a2 = analyze(pd, w2, -0.1, "RISK_ON")
    chk("하락추세 → WATCH", a2["state"] == "WATCH")
    chk("STORD 정렬키", STORD["BREAKOUT"] == 0)
    print(f"\n셀프테스트: {ok}/{tot}"); return ok == tot

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", default=None); ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    import pandas as pd, numpy as np
    if a.codes:
        named = {c.zfill(6): c for c in a.codes.split(",")}
    else:
        named = load_targets()
    if not named: print("대상 없음"); return 2
    rows, reg = run(pd, np, named)
    render(rows, reg)
    cols = ["code", "name", "state", "n", "close", "pivot", "stop", "R", "rs", "depth", "base_low", "hi52"]
    import csv as _c
    with open(os.path.join(BASE, "진우_진입신호.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = _c.DictWriter(f, fieldnames=cols, extrasaction="ignore"); w.writeheader()
        for r in rows: w.writerow(r)
    print(f"\n저장: 진우_진입신호.csv ({len(rows)}종)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
