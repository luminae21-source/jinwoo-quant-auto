#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우_타점발굴.py — 종목별 매수/매도 타점 발굴 (상태별 차등 접근) + 딥밸류바닥 신호

목적: 사냥터+테마+관심 유니버스를 스캔해, 각 종목의 기술적 상태를 분류하고
      상태별로 다른 매수/매도 접근을 준다. 관심종목 밖의 좋은 셋업을 신규 발굴.
접근유형(종목별 구분):
  · 추세매수 : 정배열 · 이격도 1.0~1.35 → 눌림(MA20 지지)에 매수. 손절 2.5ATR.
  · 반등관찰 : 이격도 0.82~1.0 · 바닥/매도소진 → MA20 상향돌파(거래량↑) 확인 후 진입. 손절 20일저 하회.
  · 과열보류 : 이격도>1.35 → 신규진입 보류, MA20/MA60 눌림까지 대기.
  · 하락회피 : 역배열 or 이격도<0.82 하락중 → 밸류트랩, 진입금지.
★딥밸류바닥: 저PBR(하위20%) ∩ 과매도(이격<0.85) ∩ 턴(20일수익>0). 30년·상폐반영 검증: 하락장 12M 시장 2배(+28.6% vs +13.5%).
             → '하락장 바닥 후보'. 검증신호지만 자동매수 아님 · 분산·손절·~1년 보유 지평.
수급 참고플래그: [기관순매수]=최신월 기관 순매수>0. ★결정적 검증(수급오버레이_검증.md): 전체유니버스+
             일봉정밀에선 딥+기관이 딥단독보다 오히려 -3%p 낮음(원래 +34%는 top-550 소표본 착시).
             → 하드필터 아님·긍정신호 아님. 초과수익과 무관한 중립 정보로만 표시.
매도: 저항(최근 60일고)·트레일(고점-2.5ATR)·손절. 익절 목표 없음(승자 미절단, 검증).
정직: 발굴≠매수신호. 진입 타이밍은 엣지 아님(검증). 소량·분산·손절 필수. 결정·책임 본인.
사용: py 진우_타점발굴.py [--only 반등관찰] [--top 40] [--self-test]
"""
import os, sys, csv, argparse, io
BASE = os.path.dirname(os.path.abspath(__file__))
RECENT = 380000
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def _rr(pd, path, n, cols):
    with open(path, "rb") as f:
        h = f.readline(); f.seek(0, 2); pos = f.tell(); data = b""; nl = 0; blk = 1 << 20
        while pos > 0 and nl <= n:
            s = min(blk, pos); pos -= s; f.seek(pos); data = f.read(s)+data; nl = data.count(b"\n")
    lines = [l for l in data.split(b"\n") if l.strip()]
    return pd.read_csv(io.BytesIO(h+b"\n".join(lines[-n:])), usecols=cols, dtype={"code": str}, encoding="utf-8-sig")

def load_universe():
    """사냥터후보 ∪ 테마 ∪ 관심 → {code: (name, tag)}."""
    U = {}
    p = os.path.join(BASE, "진우사냥터_후보.csv")
    if os.path.exists(p):
        with open(p, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f): U.setdefault(r["code"].zfill(6), [r.get("name", ""), "사냥터"])
    p = os.path.join(BASE, "kosdaq_theme_chain_map.csv")
    if os.path.exists(p):
        with open(p, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                r = {k.lstrip("﻿"): v for k, v in r.items()}
                if r.get("market") != "US":
                    c = r["ticker"].zfill(6); U.setdefault(c, [r["name"], ""]); U[c][1] = (U[c][1]+"·테마").strip("·")
    interest = set()
    p = os.path.join(BASE, "진우_관심종목.csv")
    if os.path.exists(p):
        with open(p, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                c = r["code"].zfill(6); interest.add(c); U.setdefault(c, [r.get("name", ""), ""])
    return U, interest

def load_pbr_latest():
    """종목재무_KRX 최신월 PBR → {code: pbr}. (date,code,BPS,PER,PBR,...)"""
    P = {}
    for mk in ("KOSPI", "KOSDAQ"):
        p = os.path.join(BASE, f"종목재무_KRX_{mk}.csv")
        if not os.path.exists(p): continue
        rows = []
        with open(p, encoding="utf-8-sig", newline="") as f:
            rd = csv.reader(f); next(rd, None)
            for r in rd:
                if len(r) < 5: continue
                rows.append((r[0].strip(), r[1], r[4]))
        if not rows: continue
        last = max(d for d, _, _ in rows)
        for d, code, pbr in rows:
            if d == last:
                try: v = float(pbr)
                except ValueError: v = 0
                if v > 0: P[code.zfill(6)] = v
    return P

def load_flow_latest():
    """수급 최신월 순매수 → {code: (foreign_net, inst_net)}. (code,date,foreign_net,inst_net)
    ※중립 정보표시용(사냥터_기획/진우_수급오버레이_검증.md): 전체유니버스+일봉정밀 검증에서
      딥+기관매집은 딥단독 대비 초과수익 없음(약간 -). 원래 +34%는 top-550 소표본 착시.
      → 하드필터 금지·긍정신호 아님. 외국인매집·둘다매집도 우위 없음."""
    F = {}
    for mk in ("kospi", "kosdaq"):
        p = os.path.join(BASE, f"{mk}_flow_monthly.csv")
        if not os.path.exists(p): continue
        rows = []
        with open(p, encoding="utf-8-sig", newline="") as f:
            rd = csv.reader(f); next(rd, None)
            for r in rd:
                if len(r) < 4: continue
                rows.append((r[1].strip(), r[0], r[2], r[3]))
        if not rows: continue
        last = max(d for d, _, _, _ in rows)
        for d, code, fn, inn in rows:
            if d == last:
                try: fv = float(fn)
                except (ValueError, TypeError): fv = 0.0
                try: iv = float(inn)
                except (ValueError, TypeError): iv = 0.0
                F[code.zfill(6)] = (fv, iv)
    return F

def market_regime():
    """KOSPI 지수 vs MA200 → ('하락장'|'강세장', last, ma200)."""
    p = os.path.join(BASE, "kospi_index_daily.csv")
    if not os.path.exists(p): return None
    cl = []
    with open(p, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            r = {k.lstrip("﻿").lower(): v for k, v in r.items()}
            try: cl.append(float(r["close"]))
            except (ValueError, KeyError): pass
    if len(cl) < 200: return None
    ma = sum(cl[-200:]) / 200
    return ("하락장" if cl[-1] < ma else "강세장", cl[-1], ma)

def approach(ext, order, r20, close, ma20):
    if ext is None or ma20 is None: return ("-", "-")
    if order == "역배열" or (ext < 0.82 and r20 < -0.05):
        return ("하락회피", "회피(밸류트랩)·반등확인 전 금지")
    if ext > 1.35:
        return ("과열보류", "MA20/MA60 눌림까지 대기")
    if close >= ma20 * 0.98:
        return ("추세매수", "MA20 지지 눌림에 매수")
    return ("반등관찰", "MA20 상향돌파(거래량↑) 확인 후")

ORDER = {"추세매수": 0, "반등관찰": 1, "과열보류": 2, "하락회피": 3, "-": 4}

def scan(pd, np, args):
    U, interest = load_universe()
    P = load_pbr_latest()
    FL = load_flow_latest()
    codes = set(U)
    frames = []
    for mk in ("KOSPI", "KOSDAQ"):
        p = os.path.join(BASE, f"종목일봉_30년_{mk}.csv")
        if os.path.exists(p):
            d = _rr(pd, p, RECENT, ["date", "code", "high", "low", "close", "volume"])
            d["code"] = d["code"].str.zfill(6); d = d[d["code"].isin(codes)]
            frames.append(d)
    d = pd.concat(frames, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    for c in ("high", "low", "close", "volume"): d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["date", "close"]).sort_values(["code", "date"])
    rows = []
    for code, g in d.groupby("code"):
        cl = g["close"]
        if len(cl) < 200: continue
        c = cl.iloc[-1]
        if c < 1000: continue
        adv20 = (cl*g["volume"]).rolling(20).mean().iloc[-1]
        if not (adv20 == adv20 and adv20 >= 5e8): continue
        ma20 = cl.rolling(20).mean().iloc[-1]; ma60 = cl.rolling(60).mean().iloc[-1]; ma200 = cl.rolling(200).mean().iloc[-1]
        if not (ma200 == ma200 and ma200 > 0): continue
        ext = c/ma200
        order = "정배열" if ma20 > ma60 > ma200 else ("역배열" if ma20 < ma60 < ma200 else "혼조")
        pc = cl.shift(1); tr = pd.concat([g["high"]-g["low"], (g["high"]-pc).abs(), (g["low"]-pc).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        v5 = g["volume"].tail(5).mean(); v20 = g["volume"].tail(20).mean()
        vinc = v5 > v20*1.1; vdec = v5 < v20*0.9
        r20f = c/cl.iloc[-21]-1 if len(cl) > 21 else 0
        lo20 = g["low"].tail(20).min(); hi60 = g["high"].tail(60).max()
        ap, note = approach(ext, order, r20f, c, ma20)
        buy = int(ma20) if ap != "하락회피" else None
        stop = int(lo20*0.98) if ap == "반등관찰" else int(max(c-2.5*atr, c*0.80))
        rows.append(dict(code=code, name=U[code][0] or code, tag=U[code][1],
                         star=("★" if code in interest else "✦"), ap=ap, note=note, order=order,
                         ext=round(ext, 2), r20=round(r20f*100, 0), r20f=r20f, c=int(c), buy=buy, stop=stop,
                         resist=int(hi60), vflag=("증가⚠" if vinc else ("소진" if vdec else "보합")),
                         pbr=round(P.get(code, 0), 2),
                         fnet=FL.get(code, (0.0, 0.0))[0], inet=FL.get(code, (0.0, 0.0))[1]))
    # ── 딥밸류바닥 플래그: 저PBR(스캔 유니버스 하위20%) ∩ 과매도(이격<0.85) ∩ 턴(20일수익>0) ──
    pvals = sorted(r["pbr"] for r in rows if r["pbr"] > 0)
    q20 = pvals[int(len(pvals)*0.2)] if pvals else 0
    for r in rows:
        turn = r["r20f"] > 0
        r["deep"] = 1 if (r["pbr"] > 0 and r["pbr"] <= q20 and r["ext"] < 0.85 and turn) else 0
        r["bounce"] = 1 if (r["ext"] < 0.85 and turn) else 0   # 바닥반등(밸류無 보조·약한엣지)
        # 수급 참고플래그(정보표시·필터 아님): 최신월 순매수>0
        r["imae"] = 1 if r["inet"] > 0 else 0   # 기관 순매수(중립 참고·검증상 초과수익 없음)
        r["fmae"] = 1 if r["fnet"] > 0 else 0   # 외국인 순매수(중립 참고·우위 없음)
        del r["r20f"]
    rows.sort(key=lambda r: (-r["deep"], -r["bounce"], ORDER[r["ap"]], -(r["star"] == "✦"), abs(r["ext"]-1.05)))
    return rows, interest, q20

def render(rows, args, regime, q20):
    print("\n" + "="*104)
    print("진우 타점 발굴 — 종목별 매수/매도 접근 구분  (★관심 · ✦신규발굴 · ◆딥밸류바닥 · △바닥반등)")
    if regime:
        rn, last, ma = regime
        flag = "← 빠른 반등 구간(3~6M 실현). 딥밸류바닥이 특히 잘 채워짐" if rn == "하락장" else "← 느린 반등 구간(회수 6~12M). 과매도 종목 드물어 후보 적음(정상)"
        print(f"현재 시장: {rn} (KOSPI {last:,.0f} vs MA200 {ma:,.0f}) {flag}")
    print(f"◆딥밸류바닥 = 저PBR(≤{q20:.2f},하위20%)∩이격<0.85∩20일>0 · 검증(전시장): 강세12M +17.8%·하락 +12.9% 시장초과 · 보유 하락장3~6M/강세장6~12M")
    print("△바닥반등 = 이격<0.85∩20일>0 (밸류無·약한 보조엣지, 딥밸류 빈 구간용) · 지지반등(절대저점)은 밸류트랩=금지")
    print("[기관순매수]=최신월 기관 순매수>0 · 중립 참고(필터 아님·긍정신호 아님). 결정적 검증: 전체유니버스+일봉정밀에서 딥+기관은 딥단독보다 -3%p 낮음(원래 +34%는 대형주 소표본 착시).")
    print("추세매수=눌림매수 · 반등관찰=MA20돌파확인 · 과열보류=눌림대기 · 하락회피=밸류트랩")
    print("="*104)
    # 딥밸류바닥 후보 먼저
    deeps = [r for r in rows if r["deep"]]
    if deeps and not args.only:
        print(f"\n◆ 딥밸류바닥 후보 (검증 주력신호·전 시장) {len(deeps)}종")
        for r in deeps[:15]:
            bs = f"{r['buy']:,}" if r['buy'] else "-(회피)"
            sup = ("  [기관순매수·중립]" if r["imae"] else "") + ("[외국인순매수]" if r["fmae"] else "")
            print(f"  ◆ {r['star']} {r['name'][:12]:<12} PBR {r['pbr']:.2f} · 이격 {r['ext']:.2f} · 20일 {r['r20']:+.0f}% · 매수타점 {bs} · 손절 {r['stop']:,} · {r['tag']}{sup}")
    bounces = [r for r in rows if r["bounce"] and not r["deep"]]
    if bounces and not args.only:
        print(f"\n△ 바닥반등 후보 (밸류無·약한 보조엣지, 딥밸류 빈 구간용) {len(bounces)}종")
        for r in bounces[:10]:
            bs = f"{r['buy']:,}" if r['buy'] else "-(회피)"
            print(f"  △ {r['star']} {r['name'][:12]:<12} PBR {r['pbr']:.2f} · 이격 {r['ext']:.2f} · 20일 {r['r20']:+.0f}% · 매수타점 {bs} · {r['tag']}")
    cur = None; shown = 0
    for r in rows:
        if args.only and r["ap"] != args.only: continue
        if r["ap"] != cur:
            cur = r["ap"]; print(f"\n▣ {cur}")
            print(f"  {'':2}{'종목':<11} {'배열':<4} {'PBR':>5} {'이격':>4} {'20일':>4} {'현재가':>9} {'매수타점':>9} {'손절':>9} {'저항':>9} {'거래량':<6} {'태그':<8}")
        buy = f"{r['buy']:,}" if r["buy"] else "-회피"
        mk = "◆" if r["deep"] else ("△" if r["bounce"] else " ")
        print(f"  {mk}{r['star']} {r['name'][:11]:<11} {r['order']:<4} {r['pbr']:>5.2f} {r['ext']:>4.2f} {r['r20']:>+4.0f} "
              f"{r['c']:>9,} {buy:>9} {r['stop']:>9,} {r['resist']:>9,} {r['vflag']:<6} {r['tag'][:8]:<8}")
        shown += 1
        if shown >= args.top: print("  ... (--top 늘리면 더)"); break
    print("\n※ 발굴≠매수신호 · ◆딥밸류바닥=검증 주력(전 시장) · △바닥반등=약한 보조 · 자동매수 아님 · 분산·손절 필수 · 단기스윙 엣지無(6~12M 지평) · 결정 본인.")

def _self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    chk("정배열·이격1.2 → 추세매수", approach(1.2, "정배열", -0.1, 120, 110)[0] == "추세매수")
    chk("이격0.9·혼조 → 반등관찰", approach(0.9, "혼조", -0.3, 90, 100)[0] == "반등관찰")
    chk("이격1.5 → 과열보류", approach(1.5, "정배열", -0.1, 150, 140)[0] == "과열보류")
    chk("역배열 → 하락회피", approach(0.5, "역배열", -0.3, 50, 70)[0] == "하락회피")
    chk("이격0.7 하락 → 하락회피", approach(0.7, "혼조", -0.2, 70, 90)[0] == "하락회피")
    chk("MA20아래·이격1.0 → 반등관찰", approach(1.0, "혼조", -0.3, 95, 105)[0] == "반등관찰")
    chk("정렬키 존재", ORDER["반등관찰"] == 1)
    # 딥밸류바닥 로직
    deep = lambda pbr, ext, r20f, q: 1 if (pbr > 0 and pbr <= q and ext < 0.85 and r20f > 0) else 0
    bounce = lambda ext, r20f: 1 if (ext < 0.85 and r20f > 0) else 0
    chk("저PBR+과매도+턴 → 딥밸류바닥", deep(0.5, 0.8, 0.03, 0.7) == 1)
    chk("과매도 아님 → 딥밸류바닥 아님", deep(0.5, 0.95, 0.03, 0.7) == 0)
    chk("턴 없음(하락중) → 딥밸류바닥 아님", deep(0.5, 0.8, -0.02, 0.7) == 0)
    chk("과매도+턴 → 바닥반등(밸류無)", bounce(0.8, 0.03) == 1)
    chk("고PBR이어도 과매도+턴이면 바닥반등", bounce(0.8, 0.01) == 1 and deep(3.0, 0.8, 0.01, 0.7) == 0)
    # 수급 참고플래그(정보표시·필터 아님)
    imae = lambda inet: 1 if inet > 0 else 0
    chk("기관 순매수>0 → 기관매집▲", imae(1e9) == 1)
    chk("기관 순매도 → 플래그 없음", imae(-1e9) == 0)
    print(f"\n셀프테스트: {ok}/{tot}"); return ok == tot

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="한 유형만: 추세매수/반등관찰/과열보류/하락회피")
    ap.add_argument("--top", type=int, default=40); ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    import pandas as pd, numpy as np
    rows, interest, q20 = scan(pd, np, a)
    regime = market_regime()
    render(rows, a, regime, q20)
    import csv as _c
    cols = ["star", "code", "name", "ap", "order", "pbr", "deep", "bounce", "imae", "fmae", "ext", "r20", "c", "buy", "stop", "resist", "vflag", "tag"]
    with open(os.path.join(BASE, "진우_타점발굴.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = _c.DictWriter(f, fieldnames=cols); w.writeheader()
        for r in rows: w.writerow({k: r.get(k) for k in cols})
    nd = sum(r["deep"] for r in rows); nb = sum(r["bounce"] for r in rows)
    print(f"저장: 진우_타점발굴.csv ({len(rows)}종 · ◆딥밸류바닥 {nd}종 · △바닥반등 {nb}종)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
