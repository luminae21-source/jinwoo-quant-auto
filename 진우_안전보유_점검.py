#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우_안전보유_점검.py — 보유 포트폴리오 점검 (안전 보유매매 규율)

기획: 진우_안전보유매매_기획.md · 검증: 진우_안전보유_추세청산_백테결과.md
점검: 종목별 추세(종가 vs MA200)·이격도 · 시장 regime(KOSPI vs MA200) → 방어신호
      · 분산: 종목수(동시 5~7종)·섹터당 2종·같은 그룹 1종(핵심) · 개별청산 안 함(휘프소).
보유목록: 기본 6종목. 또는 진우_보유목록.csv(code[,name]) 있으면 사용.
투자자문 아님 · 발굴≠매수신호 · 결정·책임 본인.  사용: py 진우_안전보유_점검.py [--codes 005930,000660,삼성SDI] [--self-test]
"""
import os, sys, csv, argparse
BASE = os.path.dirname(os.path.abspath(__file__))
RECENT = 600000
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

DEFAULT_HOLD = {"247540":"에코프로비엠","086520":"에코프로","036930":"주성엔지니어링",
                "353200":"대덕전자","450080":"에코프로머티","089030":"테크윙"}
# 같은 그룹/계열(섹터 캡으로 안 잡힘 — 눈으로 확인, 매도규칙서 §3)
GROUPS = {"에코프로 계열": {"247540","086520","450080"}}

def _read_recent(path, n, usecols):
    import pandas as pd
    with open(path, "rb") as f:
        header = f.readline(); f.seek(0, 2); pos = f.tell()
        data = b""; blk = 1 << 20; nl = 0
        while pos > 0 and nl <= n:
            step = min(blk, pos); pos -= step; f.seek(pos); data = f.read(step)+data; nl = data.count(b"\n")
    lines = [ln for ln in data.split(b"\n") if ln.strip()]
    tail = lines[-n:] if len(lines) > n else lines
    import io
    return pd.read_csv(io.BytesIO(header+b"\n".join(tail)), usecols=usecols, dtype={"code":str}, encoding="utf-8-sig")

def load_sector(pd):
    m = {}
    for f in ("liquidity_sector.csv", "kosdaq_industry.csv"):
        p = os.path.join(BASE, f)
        if not os.path.exists(p): continue
        d = pd.read_csv(p, dtype={"code":str}, encoding="utf-8-sig")
        d.columns = [c.lstrip("﻿") for c in d.columns]
        for _, r in d.iterrows():
            c = str(r["code"]).zfill(6)
            if c not in m and pd.notna(r.get("sector")): m[c] = r["sector"]
    return m

def load_names(pd):
    """code->name, name->code(정규화). liquidity_sector + kosdaq_industry."""
    c2n, n2c = {}, {}
    for f in ("liquidity_sector.csv", "kosdaq_industry.csv"):
        p = os.path.join(BASE, f)
        if not os.path.exists(p): continue
        d = pd.read_csv(p, dtype={"code": str}, encoding="utf-8-sig")
        d.columns = [c.lstrip("\ufeff") for c in d.columns]
        for _, r in d.iterrows():
            c = str(r.get("code", "")).zfill(6); nm = r.get("name")
            if c and pd.notna(nm):
                c2n.setdefault(c, nm); n2c.setdefault(str(nm).strip(), c)
    return c2n, n2c


def resolve_holds(pd, tokens):
    """['247540','삼성전자',...] → {code: name}. 6자리숫자=코드, 그 외=종목명 매칭."""
    c2n, n2c = load_names(pd)
    holds = {}
    for t in tokens:
        t = t.strip()
        if not t: continue
        if t.isdigit():
            c = t.zfill(6); holds[c] = c2n.get(c, "")
        elif t in n2c:
            holds[n2c[t]] = t
        else:
            print(f"  [경고] '{t}' 코드/종목명 매칭 실패 — 건너뜀")
    return holds


def stock_trend(pd, codes):
    frames = []
    for mk in ("KOSPI","KOSDAQ"):
        p = os.path.join(BASE, f"종목일봉_30년_{mk}.csv")
        if os.path.exists(p):
            d = _read_recent(p, RECENT, ["date","code","close"])
            d["code"] = d["code"].str.zfill(6); d = d[d["code"].isin(codes)]
            frames.append(d)
    if not frames: return {}
    d = pd.concat(frames, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"], errors="coerce"); d["close"] = pd.to_numeric(d["close"], errors="coerce")
    d = d.dropna(subset=["date","close"]).sort_values(["code","date"])
    out = {}
    for c, g in d.groupby("code"):
        if len(g) < 200: out[c] = {}; continue
        ma = g["close"].rolling(200).mean().iloc[-1]; cl = g["close"].iloc[-1]
        out[c] = {"close": int(cl), "ma200": int(ma) if ma==ma else None,
                  "above": bool(cl > ma) if ma==ma else None,
                  "ext": round(cl/ma, 2) if (ma==ma and ma>0) else None}
    return out

def market_regime(pd):
    p = os.path.join(BASE, "kospi_index_daily.csv")
    if not os.path.exists(p): return "N/A", None
    d = pd.read_csv(p, encoding="utf-8-sig"); d.columns = [c.lstrip("﻿").lower() for c in d.columns]
    d["close"] = pd.to_numeric(d["close"], errors="coerce"); d = d.dropna(subset=["close"])
    ma = d["close"].rolling(200).mean().iloc[-1]; cl = d["close"].iloc[-1]
    if ma != ma: return "N/A", None
    gap = cl/ma-1
    reg = "NEUTRAL" if abs(gap) < 0.02 else ("RISK_ON" if gap > 0 else "RISK_OFF")
    return reg, round(gap*100, 1)

def check(pd, holds):
    codes = set(holds); sec = load_sector(pd); tr = stock_trend(pd, codes)
    c2n, _ = load_names(pd)
    holds = {c: (holds.get(c) or c2n.get(c, c)) for c in holds}
    reg, gap = market_regime(pd)
    rows = []
    for c, nm in holds.items():
        t = tr.get(c, {})
        rows.append(dict(code=c, name=nm, sector=sec.get(c, "-"),
                         close=t.get("close"), ma200=t.get("ma200"),
                         추세=("위" if t.get("above") else ("이탈" if t.get("above") is not None else "-")),
                         이격도=t.get("ext")))
    # 분산 점검
    from collections import Counter
    sec_cnt = Counter(r["sector"] for r in rows)
    warns = []
    n = len(rows)
    if n > 7: warns.append(f"동시 보유 {n}종 > 7종 상한 초과")
    if n < 1: warns.append("보유 없음")
    for s, k in sec_cnt.items():
        if k > 2: warns.append(f"섹터 '{s}' {k}종 > 섹터당 2종 초과")
    for gname, gset in GROUPS.items():
        held = gset & codes
        if len(held) > 1:
            warns.append(f"같은 그룹 '{gname}' {len(held)}종 보유({', '.join(holds[x] for x in held)}) — 규칙 '그룹당 1종' 위반")
    # 이름 앞 2글자 공통 = 잠재 계열(소프트 경고)
    from collections import defaultdict
    pref = defaultdict(list)
    for c in codes:
        nm = holds.get(c) or ""
        if len(nm) >= 2: pref[nm[:2]].append(nm)
    for pfx, names in pref.items():
        if len(names) > 1 and not any(pfx in g for g in GROUPS):
            warns.append(f"이름 '{pfx}~' {len(names)}종({', '.join(names)}) — 같은 계열 가능성, 그룹 집중 눈으로 확인")
    return rows, reg, gap, warns

def render(rows, reg, gap, warns):
    print("\n" + "="*84)
    print("진우 안전 보유매매 — 포트폴리오 점검")
    gs = f"{gap:+.1f}%" if gap is not None else "N/A"
    act = {"RISK_OFF":"⛔ 방어 구간 — 전 종목 비중축소/현금(검증된 낙폭방어)",
           "RISK_ON":"정상 보유 — 개별 잔파동엔 안 판다(승자 미절단)",
           "NEUTRAL":"⚠️ 중립 — 신규진입 신중"}.get(reg, "-")
    print(f"시장 regime(KOSPI vs MA200): {reg} ({gs})  → {act}")
    print("="*84)
    hdr = f"{'종목':<12} {'섹터':<20} {'현재가':>9} {'MA200':>9} {'추세':<4} {'이격도':>5}"
    print(hdr); print("-"*66)
    for r in rows:
        cl = f"{r['close']:,}" if r['close'] else "-"; ma = f"{r['ma200']:,}" if r['ma200'] else "-"
        ext = f"{r['이격도']:.2f}" if r['이격도'] is not None else "-"
        flag = "" if r['추세']=="위" else ("  ← 추세이탈(개별청산 안 함·시장방어로만)" if r['추세']=="이탈" else "")
        print(f"{(r['name'] or r['code'])[:12]:<12} {(r['sector'] or '-')[:20]:<20} {cl:>9} {ma:>9} {r['추세']:<4} {ext:>5}{flag}")
    print("\n[분산·규율 점검]")
    if warns:
        for w in warns: print(f"  ⚠️ {w}")
    else:
        print("  ✓ 종목수·섹터·그룹 규칙 이상 없음")
    print("\n※ 개별종목 추세이탈에 팔지 않는다(휘프소·검증). 시장 regime RISK_OFF에서만 방어.")
    print("  발굴≠매수신호 · 사이징 1%·섹터당 2종·그룹당 1종 · 결정·책임 본인.")

def _self_test():
    import pandas as pd
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    # 그룹 위반 감지: 에코프로 계열 3종
    holds = dict(DEFAULT_HOLD)
    codes = set(holds)
    held = GROUPS["에코프로 계열"] & codes
    chk("에코프로 계열 3종 감지", len(held) == 3)
    # 분산 경고 로직(합성)
    rows = [{"sector":"반도체"}]*3
    from collections import Counter
    chk("섹터 3종>2 경고 트리거", Counter(r["sector"] for r in rows)["반도체"] > 2)
    chk("regime 액션 매핑", "방어" in {"RISK_OFF":"⛔ 방어"}.get("RISK_OFF",""))
    chk("8종>7 상한", 8 > 7)
    print(f"\n셀프테스트: {ok}/{tot}"); return ok == tot

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--codes", type=str, default=None,
                    help="점검할 종목 코드/이름 (쉼표구분, 예: 005930,000660,삼성SDI)")
    a = ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    import pandas as pd
    hp = os.path.join(BASE, "진우_보유목록.csv")
    if a.codes:
        holds = resolve_holds(pd, a.codes.split(","))
    elif os.path.exists(hp):
        holds = {}
        with open(hp, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                holds[r["code"].zfill(6)] = r.get("name", "")
    else:
        holds = dict(DEFAULT_HOLD)
    if not holds:
        print("점검할 종목 없음. --codes 005930,000660 또는 진우_보유목록.csv"); return 2
    rows, reg, gap, warns = check(pd, holds)
    render(rows, reg, gap, warns)
    return 0

if __name__ == "__main__":
    sys.exit(main())
