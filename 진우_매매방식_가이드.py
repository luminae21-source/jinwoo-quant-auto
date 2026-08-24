#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우_매매방식_가이드.py — 종목별 매매방식(단기/스윙/중장기) + 진입맥락 + 시장 regime

진우사냥터_후보.csv(6종목+상위후보)를 읽어, 각 종목을 객관 지표로 분류한다.
검증 반영(정직):
  · 스타일별 차등 청산 = 백테 기각(H0) → 청산은 단일 매도규칙서 v2 유지.
  · 추세타이밍(종가>MA200) = 하락장 낙폭방어에 유효 → regime을 진입맥락으로 표시.
  · 스타일 = 수익 레버 아님. 보유기간 기대·사이징·진입맥락(리스크 관리) 용도.

분류(사전등록 §1): vol60<3%&추세위&이격도정상=중장기 / 3~6%=스윙 / ≥6%=단기 / 이격도>1.4=진입보류.
진입맥락: 종가vs MA200(추세)·이격도·RS(26주 시장초과)·시장 regime(KOSPI>MA200).

사용: py 진우_매매방식_가이드.py [--self-test]   산출: 진우_매매방식_가이드.csv
투자자문 아님 · 발굴≠매수신호 · 결정·책임 본인.
"""
import os, sys, csv, json, argparse, io
BASE = os.path.dirname(os.path.abspath(__file__))
CSV_IN = os.path.join(BASE, "진우사냥터_후보.csv")
CSV_OUT = os.path.join(BASE, "진우_매매방식_가이드.csv")
RECENT_ROWS = 400000
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

VOL_HI, VOL_MID = 0.06, 0.03
EXT_HOT = 1.40
RS_WIN = 130      # ≈26주
STYLE_RULE = {   # (리스크%, 보유기간, 비고) — 청산은 단일규칙(차등 기각)
    "단기":   (0.5, "수일~2주", "초고변동: 작게·짧게(매도규칙서 §3 돌파 준함)"),
    "스윙":   (1.0, "2주~2개월", "표준 매도규칙서 v2"),
    "중장기": (1.0, "2개월+", "추세 유지 동안 보유(시간손절 없음)"),
}

def classify(vol60, ext, below_ma):
    overlay = "진입보류(과열)" if (ext is not None and ext > EXT_HOT) else ""
    if vol60 is None:
        return "스윙", overlay
    if vol60 >= VOL_HI:
        style = "단기"
    elif vol60 >= VOL_MID:
        style = "스윙"
    else:
        if (not below_ma) and (ext is not None and 1.0 <= ext <= 1.30):
            style = "중장기"
        else:
            style = "스윙"   # 저변동이나 추세이탈/이격도 벗어남 → 스윙 강등
    return style, overlay

def _read_recent(path, n_rows, usecols):
    with open(path, "rb") as f:
        header = f.readline(); f.seek(0, 2); pos = f.tell()
        data = b""; block = 1 << 20; nl = 0
        while pos > 0 and nl <= n_rows:
            step = min(block, pos); pos -= step
            f.seek(pos); data = f.read(step) + data; nl = data.count(b"\n")
    import pandas as pd
    lines = [ln for ln in data.split(b"\n") if ln.strip()]
    tail = lines[-n_rows:] if len(lines) > n_rows else lines
    return pd.read_csv(io.BytesIO(header + b"\n".join(tail)), usecols=usecols,
                       dtype={"code": str}, encoding="utf-8-sig")

def market_regime(pd):
    """KOSPI 종가 vs MA200 → (regime, 이격%)."""
    p = os.path.join(BASE, "kospi_index_daily.csv")
    if not os.path.exists(p): return "N/A", None
    d = pd.read_csv(p, encoding="utf-8-sig")
    d.columns = [c.lstrip("﻿").lower() for c in d.columns]
    d["close"] = pd.to_numeric(d["close"], errors="coerce")
    d = d.dropna(subset=["close"])
    ma = d["close"].rolling(200).mean().iloc[-1]
    cl = d["close"].iloc[-1]
    if ma != ma: return "N/A", None
    gap = cl/ma - 1
    reg = "RISK_ON" if gap > 0.0 else "RISK_OFF"
    if abs(gap) < 0.02: reg = "NEUTRAL"
    return reg, round(gap*100, 1)

def load_stock_context(pd, codes):
    """code -> {ma200, ext(이격도), below, rs}. 최근 일봉 tail + KOSPI RS 기준."""
    cols = ["date", "code", "close"]
    frames = []
    for m in ("KOSPI", "KOSDAQ"):
        p = os.path.join(BASE, f"종목일봉_30년_{m}.csv")
        if os.path.exists(p):
            d = _read_recent(p, RECENT_ROWS, cols)
            d["code"] = d["code"].str.zfill(6)
            d = d[d["code"].isin(codes)]
            frames.append(d)
    if not frames: return {}
    d = pd.concat(frames, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d["close"] = pd.to_numeric(d["close"], errors="coerce")
    d = d.dropna(subset=["date", "close"]).sort_values(["code", "date"])
    # KOSPI 지수 RS 기준
    kp = os.path.join(BASE, "kospi_index_daily.csv")
    mkt_ret = None
    if os.path.exists(kp):
        k = pd.read_csv(kp, encoding="utf-8-sig"); k.columns = [c.lstrip("﻿").lower() for c in k.columns]
        k["close"] = pd.to_numeric(k["close"], errors="coerce"); k = k.dropna(subset=["close"])
        if len(k) > RS_WIN:
            mkt_ret = k["close"].iloc[-1]/k["close"].iloc[-1-RS_WIN] - 1
    out = {}
    for code, g in d.groupby("code"):
        g = g.reset_index(drop=True)
        if len(g) < 200: 
            out[code] = {}; continue
        ma200 = g["close"].rolling(200).mean().iloc[-1]
        cl = g["close"].iloc[-1]
        ext = cl/ma200 if ma200 == ma200 and ma200 > 0 else None
        below = (cl < ma200) if (ma200 == ma200) else False
        rs = None
        if mkt_ret is not None and len(g) > RS_WIN:
            sret = g["close"].iloc[-1]/g["close"].iloc[-1-RS_WIN] - 1
            rs = round((sret - mkt_ret)*100, 1)
        out[code] = {"ma200": None if ma200 != ma200 else int(ma200),
                     "ext": None if ext is None else round(ext, 3),
                     "below": below, "rs": rs}
    return out

def read_candidates(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        def num(k):
            try: return float(r.get(k) or "nan")
            except ValueError: return float("nan")
        out.append(dict(rank=int(num("rank")), code=r["code"].zfill(6), name=r.get("name", ""),
                        vol60=num("vol60"), close=num("close"), qty=int(num("qty")),
                        j6=str(r.get("is_jinwoo6", "")).lower() in ("true", "1")))
    return out

def build(pd, top=None):
    cands = read_candidates(CSV_IN)
    if top: cands = [c for c in cands if c["j6"]] + cands[:top]
    codes = {c["code"] for c in cands}
    ctx = load_stock_context(pd, codes)
    reg, reg_gap = market_regime(pd)
    rows = []
    seen = set()
    for c in cands:
        if c["code"] in seen: continue
        seen.add(c["code"])
        cx = ctx.get(c["code"], {})
        ext = cx.get("ext"); below = cx.get("below", False)
        style, overlay = classify(c["vol60"], ext, below)
        risk, hold, note = STYLE_RULE[style]
        rows.append(dict(rank=c["rank"], code=c["code"], name=c["name"], j6=c["j6"],
                         style=style, overlay=overlay, 리스크=risk, 보유기간=hold,
                         vol60=round(c["vol60"]*100, 1) if c["vol60"] == c["vol60"] else None,
                         이격도=ext, 추세=("이탈" if below else "위"),
                         rs=cx.get("rs"), 비고=note))
    return rows, reg, reg_gap

def render(rows, reg, reg_gap):
    print("\n" + "="*92)
    print("진우 매매방식 가이드 — 보유스타일·사이징·진입맥락 (수익 레버 아님·리스크 관리)")
    gap_s = f"{reg_gap:+.1f}%" if reg_gap is not None else "N/A"
    print(f"시장 regime(KOSPI vs MA200): {reg} ({gap_s})  ·  청산=단일 매도규칙서 v2(차등 기각)")
    print("="*92)
    hdr = f"{'순':>3} {'종목':<11} {'스타일':<6} {'리스크':>5} {'보유':<9} {'변동%':>5} {'이격도':>5} {'추세':<4} {'RS':>6} {'과열':<10}"
    print(hdr); print("-"*96)
    order = {"단기": 0, "스윙": 1, "중장기": 2}
    for r in sorted(rows, key=lambda x: (not x["j6"], x["rank"]))[:40]:
        star = "*" if r["j6"] else " "
        ext = f"{r['이격도']:.2f}" if r["이격도"] is not None else "-"
        rs = f"{r['rs']:+.1f}" if r["rs"] is not None else "-"
        print(f"{star}{r['rank']:>2} {(r['name'] or r['code'])[:11]:<11} {r['style']:<6} "
              f"{r['리스크']:>4.1f}% {r['보유기간']:<9} {r['vol60']:>5.1f} {ext:>5} {r['추세']:<4} {rs:>6} {r['overlay']:<10}")
    # 스타일 분포
    from collections import Counter
    dist = Counter(r["style"] for r in rows)
    hot = sum(1 for r in rows if r["overlay"])
    print(f"\n분포: 단기 {dist.get('단기',0)} · 스윙 {dist.get('스윙',0)} · 중장기 {dist.get('중장기',0)} · 과열(진입보류) {hot}")
    print("※ 스타일=보유기간·사이징·진입맥락 안내. 발굴≠매수신호. 청산은 단일규칙. 결정·책임 본인.")

def _self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    chk("초고변동→단기", classify(0.07, 1.1, False)[0] == "단기")
    chk("중변동→스윙", classify(0.04, 1.1, False)[0] == "스윙")
    chk("저변동+추세위+이격정상→중장기", classify(0.02, 1.1, False)[0] == "중장기")
    chk("저변동+추세이탈→스윙강등", classify(0.02, 0.9, True)[0] == "스윙")
    chk("이격도>1.4→과열오버레이", classify(0.04, 1.5, False)[1] == "진입보류(과열)")
    chk("저변동+이격도과열→스윙+과열", classify(0.02, 1.5, False) == ("스윙", "진입보류(과열)"))
    print(f"\n셀프테스트: {ok}/{tot}"); return ok == tot

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--top", type=int, default=None)
    a = ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    if not os.path.exists(CSV_IN):
        print(f"[없음] {os.path.basename(CSV_IN)} — 먼저 진우사냥터_스크리너.py 실행"); return 2
    import pandas as pd
    rows, reg, reg_gap = build(pd, a.top)
    render(rows, reg, reg_gap)
    cols = ["rank", "code", "name", "j6", "style", "overlay", "리스크", "보유기간",
            "vol60", "이격도", "추세", "rs", "비고"]
    with open(CSV_OUT, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols); w.writeheader()
        for r in rows: w.writerow({k: r.get(k) for k in cols})
    print(f"\n저장: 진우_매매방식_가이드.csv ({len(rows)}행)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
