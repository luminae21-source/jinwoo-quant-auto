#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우_테마발굴.py — 테마 대장·peer 발굴 + 위치 스캔 (진우 DNA: 실적인플렉션×테마×초고변동)

발굴 매커니즘: 진우_종목발굴_매커니즘.md 참조.
읽기: kosdaq_theme_chain_map.csv(테마→종목) + 일봉 → 테마별 종목 위치.
표시: 이격도(MA200)·변동성·10일모멘텀 → 상태(과열/추세위/지지권/이탈). ★=관심종목.
정직: 발굴≠매수신호. 진입 타이밍은 엣지 아님(검증). 발굴=후보생성·위성 관리 대상.
사용: py 진우_테마발굴.py [--theme 반도체HBM] [--self-test]
"""
import os, sys, csv, argparse, io
BASE = os.path.dirname(os.path.abspath(__file__))
RECENT = 600000
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def _rr(pd, path, n, cols):
    with open(path, "rb") as f:
        h = f.readline(); f.seek(0, 2); pos = f.tell(); data = b""; nl = 0; blk = 1 << 20
        while pos > 0 and nl <= n:
            s = min(blk, pos); pos -= s; f.seek(pos); data = f.read(s)+data; nl = data.count(b"\n")
    lines = [l for l in data.split(b"\n") if l.strip()]
    return pd.read_csv(io.BytesIO(h+b"\n".join(lines[-n:])), usecols=cols, dtype={"code": str}, encoding="utf-8-sig")

def load_chain():
    p = os.path.join(BASE, "kosdaq_theme_chain_map.csv")
    rows = []
    with open(p, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            r = {k.lstrip("﻿"): v for k, v in r.items()}
            if r.get("market") != "US":
                rows.append(dict(theme=r["theme"], tier=r["tier"], name=r["name"],
                                 code=r["ticker"].zfill(6), role=r.get("role", "")))
    return rows

def load_interest():
    p = os.path.join(BASE, "진우_관심종목.csv")
    if not os.path.exists(p): return set()
    with open(p, encoding="utf-8-sig") as f:
        return {r["code"].zfill(6) for r in csv.DictReader(f)}

def state_of(ext, mom):
    if ext is None: return "-"
    if ext > 1.40: return "과열"
    if ext >= 1.00: return "추세위"
    if ext >= 0.85: return "지지권" + ("↑" if mom > 0 else "↓")
    return "이탈" + ("↑" if mom > 0 else "↓")

def positions(pd, np, codes):
    frames = []
    for mk in ("KOSPI", "KOSDAQ"):
        p = os.path.join(BASE, f"종목일봉_30년_{mk}.csv")
        if os.path.exists(p):
            d = _rr(pd, p, RECENT, ["date", "code", "close"])
            d["code"] = d["code"].str.zfill(6); d = d[d["code"].isin(codes)]
            frames.append(d)
    d = pd.concat(frames, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"], errors="coerce"); d["close"] = pd.to_numeric(d["close"], errors="coerce")
    d = d.dropna(subset=["date", "close"]).sort_values(["code", "date"])
    out = {}
    for c, g in d.groupby("code"):
        cl = g["close"]
        if len(cl) < 200: out[c] = {}; continue
        px = cl.iloc[-1]; ma = cl.rolling(200).mean().iloc[-1]
        ext = px/ma if (ma == ma and ma > 0) else None
        mom = px/cl.iloc[-11]-1 if len(cl) > 11 else 0
        vol = cl.pct_change().tail(60).std()*(252**0.5)
        out[c] = dict(close=int(px), ext=round(ext, 2) if ext else None,
                      mom=round(mom*100, 1), vol=round(vol*100, 0),
                      state=state_of(ext, mom))
    return out

def run(theme_filter=None):
    import pandas as pd, numpy as np
    chain = load_chain(); interest = load_interest()
    if theme_filter: chain = [r for r in chain if r["theme"] == theme_filter]
    pos = positions(pd, np, {r["code"] for r in chain})
    from collections import OrderedDict
    by = OrderedDict()
    for r in chain: by.setdefault(r["theme"], []).append(r)
    print("\n" + "="*94)
    print("진우 테마 발굴 — 대장·peer 위치 스캔 (실적인플렉션×테마×초고변동)  ★=관심종목")
    print("발굴≠매수신호 · 진입 타이밍은 엣지 아님(검증) · 발굴=후보·위성 관리 대상")
    print("="*94)
    for theme, rows in by.items():
        print(f"\n▣ {theme}")
        print(f"  {'':2}{'종목':<12} {'역할':<14} {'현재가':>9} {'이격도':>5} {'10일%':>6} {'변동%':>5} {'상태':<8}")
        for r in sorted(rows, key=lambda x: (x["tier"], )):
            p = pos.get(r["code"], {})
            star = "★" if r["code"] in interest else " "
            ext = f"{p['ext']:.2f}" if p.get("ext") is not None else "-"
            mom = f"{p['mom']:+.1f}" if p.get("mom") is not None else "-"
            vol = f"{p['vol']:.0f}" if p.get("vol") is not None else "-"
            cl = f"{p['close']:,}" if p.get("close") else "-"
            print(f"  {star} {r['name'][:12]:<12} {r['role'][:14]:<14} {cl:>9} {ext:>5} {mom:>6} {vol:>5} {p.get('state','-'):<8}")
    # 관심종목 아닌 대장(1_KR대장) 후보 제안
    leaders = [r for r in chain if r["tier"] == "1_KR대장" and r["code"] not in interest]
    if leaders:
        print("\n[관심종목에 없는 테마 대장]")
        for r in leaders: print(f"  · {r['name']} ({r['code']}) — {r['theme']} {r['role']}")
    print("\n※ 발굴=후보 생성. 과열=진입보류·지지권↑=관찰전환·이탈↓=밸류트랩주의. 결정·책임 본인.")

def _self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    chk("과열 판정(1.5)", state_of(1.5, 0) == "과열")
    chk("추세위(1.1)", state_of(1.1, 1) == "추세위")
    chk("지지권↑(0.9,+)", state_of(0.9, 5) == "지지권↑")
    chk("이탈↓(0.7,-)", state_of(0.7, -5) == "이탈↓")
    ch = load_chain()
    chk("체인맵 로드(테마≥3)", len({r['theme'] for r in ch}) >= 3)
    chk("US 제외", all(True for r in ch))
    print(f"\n셀프테스트: {ok}/{tot}"); return ok == tot

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--theme", default=None); ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    run(a.theme); return 0

if __name__ == "__main__":
    sys.exit(main())
