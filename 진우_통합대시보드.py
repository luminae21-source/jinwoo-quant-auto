#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우_통합대시보드.py — 그래픽 모니터링 대시보드 (관심종목·테마·진입관찰)

읽기: 진우_관심종목.csv + kosdaq_theme_chain_map.csv + 일봉 + KOSPI지수 → 자체완결 HTML.
표시: 시장 regime · 진입관찰(지지권↑) · 관심종목 카드(스파크라인·이격도게이지·상태) · 7대 테마 레이더.
정직: 발굴≠매수신호. 진입 타이밍은 엣지 아님. 수익=선정+보유+regime방어.
사용: py 진우_통합대시보드.py [--self-test]   산출: 진우_통합대시보드.html
"""
import os, sys, csv, argparse, io, datetime
BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "진우_통합대시보드.html")
RECENT = 600000
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

COL = {"과열": "#e2606a", "추세위": "#3fb37a", "지지권": "#e0b020", "이탈": "#969ca6", "-": "#5a626e"}

def _rr(pd, path, n, cols):
    with open(path, "rb") as f:
        h = f.readline(); f.seek(0, 2); pos = f.tell(); data = b""; nl = 0; blk = 1 << 20
        while pos > 0 and nl <= n:
            s = min(blk, pos); pos -= s; f.seek(pos); data = f.read(s)+data; nl = data.count(b"\n")
    lines = [l for l in data.split(b"\n") if l.strip()]
    return pd.read_csv(io.BytesIO(h+b"\n".join(lines[-n:])), usecols=cols, dtype={"code": str}, encoding="utf-8-sig")

def base_state(ext):
    if ext is None: return "-"
    if ext > 1.40: return "과열"
    if ext >= 1.00: return "추세위"
    if ext >= 0.85: return "지지권"
    return "이탈"

def positions(pd, codes, spark_codes):
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
        rec = dict(close=int(px), ext=round(ext, 2) if ext else None, mom=round(mom*100, 1),
                   vol=int(vol*100) if vol == vol else None, base=base_state(ext),
                   date=str(g["date"].iloc[-1].date()))
        if c in spark_codes:
            rec["spark"] = [float(x) for x in cl.tail(60).tolist()]
        out[c] = rec
    return out

def regime(pd):
    p = os.path.join(BASE, "kospi_index_daily.csv")
    if not os.path.exists(p): return "N/A", None
    d = pd.read_csv(p, encoding="utf-8-sig"); d.columns = [c.lstrip("﻿").lower() for c in d.columns]
    d["close"] = pd.to_numeric(d["close"], errors="coerce"); d = d.dropna(subset=["close"])
    ma = d["close"].rolling(200).mean().iloc[-1]; cl = d["close"].iloc[-1]
    if ma != ma: return "N/A", None
    g = cl/ma-1
    return ("NEUTRAL" if abs(g) < 0.02 else ("RISK_ON" if g > 0 else "RISK_OFF")), round(g*100, 1)

def spark_svg(vals, w=150, h=38):
    if not vals or len(vals) < 2: return ""
    lo, hi = min(vals), max(vals); rng = (hi-lo) or 1; n = len(vals)
    pts = " ".join(f"{i/(n-1)*w:.1f},{h-(v-lo)/rng*h:.1f}" for i, v in enumerate(vals))
    col = "#3fb37a" if vals[-1] >= vals[0] else "#e2606a"
    return (f'<svg width="{w}" height="{h}" viewBox="0 0 {w} {h}" preserveAspectRatio="none">'
            f'<polyline fill="none" stroke="{col}" stroke-width="1.6" points="{pts}"/></svg>')

def gauge(ext, base):
    if ext is None: return '<div class="g"></div>'
    lo, hi = 0.5, 2.5
    pos = max(0, min(1, (ext-lo)/(hi-lo)))*100
    mapos = (1.0-lo)/(hi-lo)*100
    col = COL.get(base, "#5a626e")
    return (f'<div class="g"><div class="gma" style="left:{mapos:.0f}%"></div>'
            f'<div class="gmk" style="left:{pos:.0f}%;background:{col}"></div></div>')

def build(rows_wl, themes_pos, wl_names, wl_memo, reg, gap, data_date):
    def badge(base, mom):
        arrow = "▲" if mom is not None and mom > 0 else ("▼" if mom is not None and mom < 0 else "·")
        col = COL.get(base, "#5a626e")
        return f'<span class="bd" style="background:{col}22;color:{col};border:1px solid {col}55">{base}{arrow}</span>'
    # 진입관찰: 지지권 + mom>0
    watch = [(c, p) for c, p in rows_wl if p.get("base") == "지지권" and (p.get("mom") or 0) > 0]
    won = lambda n: f"{n:,}"
    # 관심종목 카드
    cards = ""
    for c, p in rows_wl:
        if not p: continue
        nm = wl_names.get(c, c); memo = wl_memo.get(c, "")
        ext = p.get("ext"); exts = f"{ext:.2f}" if ext else "-"
        mom = p.get("mom"); moms = f"{mom:+.1f}%" if mom is not None else "-"
        momcol = "#3fb37a" if (mom or 0) > 0 else "#e2606a"
        cards += f'''<div class="card">
  <div class="ct"><span class="nm">{nm}</span>{badge(p.get("base","-"), mom)}</div>
  <div class="memo">{memo}</div>
  <div class="spark">{spark_svg(p.get("spark"))}</div>
  <div class="row"><span>현재가</span><b>{won(p.get("close",0))}</b></div>
  <div class="row"><span>이격도(MA200)</span><b>{exts}</b></div>
  {gauge(ext, p.get("base","-"))}
  <div class="row"><span>10일</span><b style="color:{momcol}">{moms}</b><span>변동성</span><b>{p.get("vol","-")}%</b></div>
</div>'''
    # 테마 레이더
    radar = ""
    for theme, members in themes_pos:
        chips = ""
        for r in members:
            p = r["pos"]; ext = p.get("ext"); base = p.get("base", "-")
            col = COL.get(base, "#5a626e")
            exts = f"{ext:.2f}" if ext else "-"
            chips += f'<span class="chip" style="border-color:{col}55;color:{col}" title="{r["role"]}">{r["name"]} {exts}</span>'
        radar += f'<div class="theme"><div class="tn">▣ {theme}</div><div class="chips">{chips}</div></div>'
    # 진입관찰 배너
    if watch:
        wtxt = " · ".join(f'{wl_names.get(c,c)}({p["ext"]:.2f}, {p["mom"]:+.0f}%)' for c, p in watch)
        watch_html = f'<div class="watch on">🎯 진입 관찰(지지권↑ 반등조짐): {wtxt}</div>'
    else:
        watch_html = '<div class="watch off">진입 관찰 없음 — 관심종목 대부분 조정/이탈 국면. 지지권↑ 전환 대기.</div>'
    reg_col = {"RISK_ON": "#3fb37a", "RISK_OFF": "#e2606a", "NEUTRAL": "#e0b020"}.get(reg, "#969ca6")
    gaps = f"{gap:+.1f}%" if gap is not None else "N/A"
    gen = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    return TEMPLATE.replace("__REGCOL__", reg_col).replace("__REG__", reg).replace("__GAP__", gaps)\
        .replace("__DATE__", data_date).replace("__GEN__", gen).replace("__WATCH__", watch_html)\
        .replace("__CARDS__", cards).replace("__RADAR__", radar)

TEMPLATE = r"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1"><title>진우퀀트 통합 대시보드</title>
<style>
:root{--bg:#0f1115;--panel:#171a21;--line:#242a35;--acc:#ff7a45;--txt:#e8eaed;--sub:#969ca6}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);
font-family:'Malgun Gothic','맑은 고딕',system-ui,sans-serif;font-size:14px}
.wrap{max-width:1180px;margin:0 auto;padding:20px 16px 60px}
h1{font-size:21px;margin:0 0 3px}.sub{color:var(--sub);font-size:12.5px}
.reg{display:inline-block;padding:4px 12px;border-radius:14px;font-weight:700;font-size:13px;
background:__REGCOL__22;color:__REGCOL__;border:1px solid __REGCOL__66;margin:10px 0}
.watch{padding:11px 14px;border-radius:9px;margin:6px 0 18px;font-size:13.5px}
.watch.on{background:#ff7a4518;border:1px solid #ff7a4566;color:#ffb488}
.watch.off{background:var(--panel);border:1px solid var(--line);color:var(--sub)}
h2{font-size:15px;margin:20px 0 10px;color:var(--acc)}
.grid{display:grid;grid-template-columns:repeat(auto-fill,minmax(220px,1fr));gap:12px}
.card{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:12px 13px}
.ct{display:flex;justify-content:space-between;align-items:center;margin-bottom:2px}
.nm{font-weight:700;font-size:14.5px}.memo{color:var(--sub);font-size:11px;margin-bottom:6px;height:14px;overflow:hidden}
.bd{font-size:11px;padding:2px 7px;border-radius:10px;font-weight:700}
.spark{height:38px;margin:4px 0}
.row{display:flex;justify-content:space-between;align-items:center;font-size:12px;color:var(--sub);margin-top:3px}
.row b{color:var(--txt);font-weight:600}
.g{position:relative;height:7px;background:#0c0e12;border:1px solid var(--line);border-radius:4px;margin:6px 0 2px}
.gma{position:absolute;top:-2px;width:2px;height:11px;background:#5a8fd0}
.gmk{position:absolute;top:-2px;width:8px;height:11px;border-radius:2px;transform:translateX(-4px)}
.theme{margin-bottom:9px}.tn{font-size:13px;color:var(--txt);margin-bottom:4px;font-weight:600}
.chips{display:flex;flex-wrap:wrap;gap:5px}
.chip{font-size:11.5px;padding:3px 8px;border:1px solid;border-radius:12px;background:#0c0e12}
.tools{background:var(--panel);border:1px solid var(--line);border-radius:9px;padding:12px 14px;font-size:12.5px;color:var(--sub);line-height:1.7}
.tools b{color:var(--txt)}
.foot{color:var(--sub);font-size:11px;margin-top:18px;line-height:1.6}
.legend{font-size:11px;color:var(--sub);margin:2px 0 10px}
.lg{display:inline-block;width:9px;height:9px;border-radius:2px;margin:0 3px 0 10px;vertical-align:middle}
</style></head><body><div class="wrap">
<h1>진우퀀트 통합 대시보드 <span style="color:var(--acc)">· 발굴→관찰→보유</span></h1>
<div class="sub">데이터일 __DATE__ · 생성 __GEN__ · 발굴≠매수신호 · 결정·책임 본인</div>
<div class="reg">시장 regime: __REG__ (__GAP__ vs MA200)</div>
<button id="helpBtn" style="background:#171a21;color:#c8ccd4;border:1px solid #2a3140;border-radius:8px;padding:5px 12px;font-size:12px;cursor:pointer;margin:0 0 10px">? 도움말</button>
<div id="help" style="display:none;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin-bottom:14px;font-size:12.5px;line-height:1.7">
<b style="color:var(--acc)">이 대시보드 보는 법</b><br>
<b>시장 regime</b> — KOSPI가 200일선 <b>위=RISK_ON</b>(정상 보유), <b>아래=RISK_OFF</b>(전 종목 방어). 검증된 유일한 낙폭방어 레버.<br>
<b>🎯 진입관찰</b> — "지지권↑"(눌렸다가 반등 조짐) 종목 자동 하이라이트 = 관찰→진입 전환 후보. 없으면 관망 구간.<br>
<b>관심종목 카드 상태</b>: <span style="color:#e2606a">과열</span>(너무 올라 보류) · <span style="color:#3fb37a">추세위</span>(추세 위) · <span style="color:#e0b020">지지권</span>(MA200 근처) · <span style="color:#969ca6">이탈</span>(MA200 아래). ▲▼=10일 모멘텀.<br>
<b>스파크라인</b>=최근 60일 움직임 · <b>이격도 게이지</b>=파란선(MA200) 대비 현재 위치.<br>
<b>테마 레이더</b>=7대 테마 종목을 위 상태색으로 한눈에.<br>
<span style="color:var(--sub)">※ 진입 원칙: 과열=보류·지지권↑=관찰전환·이탈↓=밸류트랩. 발굴≠매수신호·결정 본인.</span>
</div>
__WATCH__
<div class="legend">상태:
<span class="lg" style="background:#e2606a"></span>과열
<span class="lg" style="background:#3fb37a"></span>추세위
<span class="lg" style="background:#e0b020"></span>지지권
<span class="lg" style="background:#969ca6"></span>이탈 · ▲▼=10일 모멘텀 · 게이지 파란선=MA200(이격도 1.0)</div>

<h2>★ 관심종목 모니터</h2>
<div class="grid">__CARDS__</div>

<h2>▣ 7대 테마 레이더</h2>
__RADAR__

<h2>🛠 툴</h2>
<div class="tools">
<b>발굴</b>: 진우_테마발굴.py(7대 테마) · 진우사냥터_스크리너.py(가치) · 진우_반등후보_스캔.py(지지권 반등)<br>
<b>분석</b>: 진우_매매방식_가이드.py(스타일·사이징) · 개별 메커니즘("○○ 봐줘")<br>
<b>관찰·보유</b>: 이 대시보드 · 진우_안전보유_점검.py(--codes) · 진우_관심종목.csv<br>
<b>검증근거</b>: regime오버레이=낙폭반감 · 저점매수고점매도=기각 · 승자미절단<br>
<b>정본</b>: 진우_종목발굴_매커니즘.md · 진우_안전보유매매_기획.md · 진우_툴_인덱스.md
</div>
<div class="foot">진입 원칙: 과열=보류 · 지지권↑(MA20회복+모멘텀+)=관찰→진입 · 이탈↓=밸류트랩 주의.<br>
발굴≠매수신호 · 진입타이밍은 엣지 아님(검증) · 수익=선정+보유+regime방어 · 초고변동=사이징·분산 필수 · 결정·책임 본인.</div>
<script>document.getElementById('helpBtn').addEventListener('click',function(){var h=document.getElementById('help');h.style.display=h.style.display==='none'?'block':'none';});</script>
</div></body></html>"""

def _self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    chk("과열 판정", base_state(1.5) == "과열")
    chk("지지권 판정", base_state(0.9) == "지지권")
    chk("이탈 판정", base_state(0.7) == "이탈")
    sv = spark_svg([1, 2, 3, 2, 4])
    chk("스파크라인 SVG", "<svg" in sv and "polyline" in sv)
    chk("게이지 마커", "gmk" in gauge(1.2, "추세위"))
    chk("빈 게이지", "class=\"g\"" in gauge(None, "-"))
    print(f"\n셀프테스트: {ok}/{tot}"); return ok == tot

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    import pandas as pd
    # 관심종목
    wl_names, wl_memo, wl = {}, {}, []
    ip = os.path.join(BASE, "진우_관심종목.csv")
    if os.path.exists(ip):
        with open(ip, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                c = r["code"].zfill(6); wl.append(c); wl_names[c] = r.get("name", ""); wl_memo[c] = r.get("메모", "")
    # 테마
    chain = []
    cp = os.path.join(BASE, "kosdaq_theme_chain_map.csv")
    with open(cp, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            r = {k.lstrip("﻿"): v for k, v in r.items()}
            if r.get("market") != "US":
                chain.append(dict(theme=r["theme"], name=r["name"], code=r["ticker"].zfill(6), role=r.get("role", "")))
    allcodes = set(wl) | {r["code"] for r in chain}
    pos = positions(pd, allcodes, set(wl))
    reg, gap = regime(pd)
    data_date = next((p["date"] for p in pos.values() if p.get("date")), "-")
    rows_wl = [(c, pos.get(c, {})) for c in wl]
    from collections import OrderedDict
    tby = OrderedDict()
    for r in chain: tby.setdefault(r["theme"], []).append(dict(name=r["name"], role=r["role"], pos=pos.get(r["code"], {})))
    themes_pos = list(tby.items())
    html = build(rows_wl, themes_pos, wl_names, wl_memo, reg, gap, data_date)
    with open(OUT, "w", encoding="utf-8") as f: f.write(html)
    print(f"저장: 진우_통합대시보드.html ({len(wl)}관심 · {len(themes_pos)}테마 · {len(html):,}바이트)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
