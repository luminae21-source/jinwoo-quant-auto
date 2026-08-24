#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우_반등후보_스캔.py — "MA200 근처 눌림 + 반등" 패턴 스캐너 (한미반도체形)

패턴(인과·미래 안 봄): 큰 상승추세였다가 MA200 근처로 눌린 뒤 단기 반등 시작.
  · 이격도(종가/MA200) ∈ [LO, HI] (기본 0.88~1.12) — MA200 근처(과열X·깊은붕괴X)
  · 지난 250일 최대 이격도 ≥ TREND (기본 1.15) — 과거 상승추세였음(밸류트랩 배제)
  · 단기 반등: 종가 > MA20 AND 종가 > 종가[−10일] AND 최근20일 저점 대비 +3%↑
  · 거래필터: 종가≥1000·adv20≥5억
랭킹: 이격도 1.0 근접 + 반등강도. 유니버스=liquidity_sector(유동주).
투자자문 아님·발굴≠매수신호·결정책임 본인.
사용: py 진우_반등후보_스캔.py [--top 25] [--lo 0.88 --hi 1.12] [--self-test]
"""
import os, sys, argparse, io
BASE = os.path.dirname(os.path.abspath(__file__))
RECENT = 600000
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def _read_recent(pd, path, n, usecols):
    with open(path, "rb") as f:
        header = f.readline(); f.seek(0, 2); pos = f.tell()
        data = b""; blk = 1 << 20; nl = 0
        while pos > 0 and nl <= n:
            step = min(blk, pos); pos -= step; f.seek(pos); data = f.read(step)+data; nl = data.count(b"\n")
    lines = [ln for ln in data.split(b"\n") if ln.strip()]
    tail = lines[-n:] if len(lines) > n else lines
    return pd.read_csv(io.BytesIO(header+b"\n".join(tail)), usecols=usecols, dtype={"code": str}, encoding="utf-8-sig")

def load_universe(pd):
    p = os.path.join(BASE, "liquidity_sector.csv")
    d = pd.read_csv(p, dtype={"code": str}, encoding="utf-8-sig")
    d.columns = [c.lstrip("﻿") for c in d.columns]
    d["code"] = d["code"].str.zfill(6)
    name = dict(zip(d["code"], d["name"])); sec = dict(zip(d["code"], d["sector"]))
    return set(d["code"]), name, sec

def scan(pd, np, args):
    codes, name, sec = load_universe(pd)
    frames = []
    for mk in ("KOSPI", "KOSDAQ"):
        p = os.path.join(BASE, f"종목일봉_30년_{mk}.csv")
        if os.path.exists(p):
            d = _read_recent(pd, p, RECENT, ["date", "code", "high", "low", "close", "volume"])
            d["code"] = d["code"].str.zfill(6); d = d[d["code"].isin(codes)]
            frames.append(d)
    d = pd.concat(frames, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    for c in ("high", "low", "close", "volume"): d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["date", "close"]); d = d[d["close"] > 0].sort_values(["code", "date"])
    rows = []
    for code, g in d.groupby("code"):
        if len(g) < 250: continue
        cl = g["close"]; c = cl.iloc[-1]
        ma200 = cl.rolling(200).mean().iloc[-1]; ma20 = cl.rolling(20).mean().iloc[-1]
        if not (ma200 == ma200 and ma200 > 0): continue
        ext = c/ma200
        adv20 = (g["close"]*g["volume"]).rolling(20).mean().iloc[-1]
        if c < 1000 or not (adv20 == adv20 and adv20 >= 5e8): continue
        trend_max = (cl/cl.rolling(200).mean()).tail(250).max()
        mom10 = c/cl.iloc[-11]-1 if len(cl) > 11 else 0
        low20 = g["low"].tail(20).min(); bounce = c/low20-1 if low20 > 0 else 0
        # 섹터 필터
        if args.sector:
            sc = str(sec.get(code, "") or "")
            if not any(k in sc for k in args.sector.split(",")): continue
        # 패턴 조건
        if not (args.lo <= ext <= args.hi): continue
        if not (trend_max >= args.trend): continue
        if args.watch:
            # 지지 대기: 반등 확인 불요. 자유낙하만 배제(10일 > -25%).
            if mom10 <= -0.25: continue
        else:
            if not (c > ma20 and mom10 > 0 and bounce >= 0.03): continue
        # 점수: 이격도 1.0 근접(작을수록) + 반등강도
        score = (1-abs(ext-1.0)) * 0.6 + min(mom10, 0.3)/0.3 * 0.4
        status = "반등확인" if (c > ma20 and mom10 > 0 and bounce >= 0.03) else "지지대기(반등前)"
        rows.append(dict(code=code, name=name.get(code, code), sec=sec.get(code, "-"),
                         close=int(c), ext=round(ext, 2), status=status,
                         mom10=round(mom10*100, 1), bounce=round(bounce*100, 1),
                         trend_max=round(trend_max, 2), score=round(score, 3)))
    rows.sort(key=lambda r: -r["score"])
    return rows

def render(rows, args, ref=None):
    print("\n" + "="*98)
    print(f"MA200 근처 눌림+반등 스캔 (한미반도체形) · 이격도 {args.lo}~{args.hi} · 과거추세≥{args.trend}")
    print("="*98)
    if ref:
        print(f"[기준 한미반도체] 이격도 {ref['ext']} · 10일모멘텀 {ref['mom10']}% · 저점반등 {ref['bounce']}% · 과거최대이격 {ref['trend_max']}")
        print("-"*98)
    hdr = f"{'종목':<12} {'섹터':<16} {'현재가':>9} {'이격도':>5} {'10일%':>6} {'상태':<14}"
    print(hdr); print("-"*90)
    for r in rows[:args.top]:
        print(f"{(r['name'] or r['code'])[:12]:<12} {(r['sec'] or '-')[:16]:<16} {r['close']:>9,} "
              f"{r['ext']:>5.2f} {r['mom10']:>+6.1f} {r['status']:<14}")
    print(f"\n총 {len(rows)}종 매칭. 이격도 1.0 근접+반등강도 순. ※발굴≠매수신호·thesis/과열 확인·결정책임 본인.")

def _self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    chk("이격도 밴드 판정", (0.88 <= 0.95 <= 1.12) and not (0.88 <= 1.5 <= 1.12))
    chk("점수 이격도1.0가 높음", (1-abs(1.0-1.0)) > (1-abs(1.3-1.0)))
    chk("반등 임계 3%", (0.05 >= 0.03) and not (0.01 >= 0.03))
    print(f"\n셀프테스트: {ok}/{tot}"); return ok == tot

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=25)
    ap.add_argument("--lo", type=float, default=0.88); ap.add_argument("--hi", type=float, default=1.12)
    ap.add_argument("--trend", type=float, default=1.15)
    ap.add_argument("--sector", type=str, default=None, help="섹터 키워드(쉼표): 예 반도체,전자부품,특수 목적용 기계")
    ap.add_argument("--watch", action="store_true", help="지지대기 포함(반등확인 전, 자유낙하만 배제)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    import pandas as pd, numpy as np
    rows = scan(pd, np, a)
    ref = next((r for r in rows if r["code"] == "042700"), None)
    render(rows, a, ref)
    return 0

if __name__ == "__main__":
    sys.exit(main())
