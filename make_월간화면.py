#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""진우퀀트 월간 단일화면 생성기 (정적 생성형). CSV -> 진우퀀트_월간_단일화면.html
--public: 실보유[1] 비공개 처리 후 docs/monthly.html 생성 (GitHub Pages 안전 공개용).
원칙: 후보!=매수신호 / 실보유!=모델픽 / 백테!=forward(현실 20%대) / production v3.7.2 무수정."""
import sys, html, datetime, pathlib
import pandas as pd

BASE = pathlib.Path(__file__).parent.resolve()
OUT = BASE / "진우퀀트_월간_단일화면.html"
PUB = BASE / "docs" / "monthly.html"
LV = {"ok": "정상", "warn": "주의", "act": "조치필요"}


def load(name, **kw):
    p = BASE / name
    if not p.exists():
        return None
    for enc in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return pd.read_csv(p, encoding=enc, **kw)
        except Exception:
            continue
    return None


def esc(x):
    return html.escape(str(x)) if x is not None else ""


def badge(level, text):
    cls = {"ok": "b-ok", "warn": "b-warn", "act": "b-act", "info": "b-info"}.get(level, "b-info")
    return "<span class='bdg " + cls + "'>" + esc(text) + "</span>"


def sec1_holdings(my, dv, public=False):
    if public:
        return ("<div class='empty'>실보유 현황은 <b>로컬 전용(비공개)</b> — 개인 포트폴리오 보호를 위해 공개 대시보드에서는 제외됩니다. 보유 점검은 로컬 <code>진우퀀트_월간_단일화면.html</code>에서.</div>", 0, 0)
    rows = []
    src = None
    real = None
    if my is not None and "code" in my.columns:
        real = my.dropna(subset=["code"]).copy()
        real = real[real["code"].astype(str).str.match(r"^\d{6}$")]
    if real is not None and len(real):
        src = "my_holdings.csv"
        for _, r in real.iterrows():
            wi = pd.to_numeric(r.get("weight"), errors="coerce")
            lvl = "ok"
            if pd.notna(wi):
                if wi > 30:
                    lvl = "act"
                elif wi > 20:
                    lvl = "warn"
            wt = ("%.0f%%" % wi) if pd.notna(wi) else "-"
            rows.append((esc(r["name"]), wt, "비중 점검" if lvl != "ok" else "", badge(lvl, LV[lvl])))
    elif dv is not None and "held" in dv.columns:
        src = "decision_view_latest.csv (held=True)"
        for _, r in dv[dv["held"] == True].iterrows():
            verd = str(r.get("verdict", ""))
            lvl = "warn" if any(k in verd for k in ("약", "점검", "트림", "주의")) else "ok"
            rows.append((esc(r["name"]), esc(r.get("theme", "")), esc(verd), badge(lvl, LV[lvl])))
    if not rows:
        return ("<div class='empty'>실보유 미입력 — <code>my_holdings.csv</code>를 채우세요.</div>", 0, 0)
    n_act = sum(1 for x in rows if "조치필요" in x[3])
    n_warn = sum(1 for x in rows if ">주의<" in x[3])
    body = "".join("<tr><td>" + a + "</td><td>" + b + "</td><td class='vd'>" + c + "</td><td>" + d + "</td></tr>" for a, b, c, d in rows)
    extra = "" if (real is not None and len(real)) else " <b>조치필요 정확 판정은 my_holdings.csv 입력 + 가격/attribution 연동 후.</b>"
    note = "<p class='note'>조치 필요/주의 = <b>즉시 매도 뜻이 아니라 thesis/비중/손절 재확인 신호.</b> (출처: " + esc(src) + ")" + extra + "</p>"
    table = "<table><thead><tr><th>종목</th><th>비중/테마</th><th>상태/verdict</th><th>판정</th></tr></thead><tbody>" + body + "</tbody></table>"
    return (table + note, n_act, n_warn)


def sec2_model(sc):
    if sc is None or "등급" not in sc.columns:
        return "<div class='empty'>v37_2_scores_latest.csv 없음</div>"
    dist = sc["등급"].value_counts().to_dict()
    chips = " ".join("<span class='chip'>" + g + " " + str(dist.get(g, 0)) + "</span>" for g in ["S+", "S", "A", "B", "C", "D"] if dist.get(g, 0))
    new_html = ""
    if "신규" in sc.columns:
        new = sc[sc["신규"].astype(str).str.lower() == "true"]
        if len(new):
            items = " · ".join(esc(r["종목"]) + "(" + esc(r["등급"]) + ")" for _, r in new.iterrows())
            new_html = "<p class='note'>신규 편입: <b>" + items + "</b></p>"
    picks = sc[sc["등급"].isin(["S+", "S", "A"])]
    if "순위" in sc.columns:
        picks = picks.sort_values("순위")
    body = "".join("<tr><td>" + esc(r.get("순위", "")) + "</td><td>" + esc(r["종목"]) + "</td><td>" + esc(r.get("산업", "")) + "</td><td>" + esc(r["등급"]) + "</td><td>" + esc(r.get("권장비중_%", "")) + "%</td></tr>" for _, r in picks.iterrows())
    return "<div>" + chips + "</div>" + new_html + "<table><thead><tr><th>#</th><th>종목</th><th>산업</th><th>등급</th><th>권장</th></tr></thead><tbody>" + body + "</tbody></table><p class='note'>라벨: <b>모델픽(검증 바스켓)</b> — 실보유와 분리.</p>"


def sec3_heat(ht):
    if ht is None or "theme" not in ht.columns:
        return "<div class='empty'>theme_heat_latest.csv 없음</div>"
    on_txt = "없음"
    if "supercycle" in ht.columns:
        on = ht[ht["supercycle"].astype(str).str.lower() == "true"]
        if len(on):
            on_txt = " · ".join("<b>" + esc(t) + "</b>" for t in on["theme"])
    top = ht.sort_values("heat_score", ascending=False).head(6) if "heat_score" in ht.columns else ht.head(6)
    body = ""
    for _, r in top.iterrows():
        mark = "ON" if str(r.get("supercycle")).lower() == "true" else ""
        try:
            hs = "%.0f" % float(r.get("heat_score", 0))
        except Exception:
            hs = "-"
        body += "<tr><td>" + esc(r.get("rank", "")) + "</td><td>" + esc(r["theme"]) + "</td><td>" + esc(r.get("n", "")) + "</td><td>" + hs + "</td><td>" + mark + "</td></tr>"
    return "<p class='note'>ON 테마 (supercycle=True, 단일 정의): " + on_txt + "</p><table><thead><tr><th>#</th><th>테마</th><th>n</th><th>heat</th><th>ON</th></tr></thead><tbody>" + body + "</tbody></table>"


def sec4_watch(wl):
    if wl is None or "name" not in wl.columns:
        return "<div class='empty'>watchlist 없음</div>"
    pas = wl[wl["guardrail"].astype(str).str.upper() == "PASS"] if "guardrail" in wl.columns else wl
    body = ""
    for _, r in pas.iterrows():
        body += "<tr><td>" + esc(r["name"]) + "</td><td>" + esc(r.get("theme", "")) + "</td><td>" + esc(r.get("mcap_억", "")) + "</td><td>" + badge("info", "관찰만") + "</td></tr>"
    return "<p class='note'><b>관찰후보 = 매수신호 아님.</b> 기본 상태 <b>관찰만</b>. 돌파 확인 + 가드레일 + thesis/stop/비중/TrackW 사전등록 충족 시에만 사람이 '매수 검토 가능'으로 승격. (진입 상태머신 chart_timing 자동연동은 후속)</p><table><thead><tr><th>종목</th><th>테마</th><th>시총(억)</th><th>상태</th></tr></thead><tbody>" + body + "</tbody></table>"


def sec5_trackw(tw):
    if tw is None:
        return "<div class='empty'>track_w_ledger.csv 없음</div>"
    data = tw[tw["date_signal"].notna()] if "date_signal" in tw.columns else tw.dropna(how="all")
    if not len(data):
        return "<div class='empty'>기록 없음 — 첫 재량 매수/관찰 시 <code>track_w_ledger.csv</code>에 <b>매수 전 기입</b>(date_signal·reason·stop_price 선등록).</div><p class='note'>메인=재량매수-시스템벤치(판정) / 보조=패스후보-매수(경고). <b>보조 양수=패스가 더 잘됨(선별 경고). 음수=내 매수가 더 나음=정상.</b></p>"
    return "<p class='note'>기록 " + str(len(data)) + "건. 6~12개월 누적 후 메인/보조 임계 판정.</p>"


CHECK_LINES = [
    "이번 달: score_v37_2 실행·모델픽 갱신 / my_holdings 갱신·실보유 점검 / 실전기록 1줄",
    "매수 전: 관찰후보면 사지 않기 · thesis/손절/비중 기입 · 재량이면 Track W 먼저 기입",
    "보유: attribution T2 2개월연속? · 손절선 근접? · 집중도 과도?",
    "금지: production 임의수정 · 후보를 매수신호로 오해 · 백테 71.5%를 기대수익으로 · 기록없이 매수",
]

CSS = """
:root{--bg:#0d1117;--card:#161b22;--bd:#30363d;--tx:#e6edf3;--mut:#8b949e;--grn:#3fb950;--yel:#d29922;--red:#f85149;--blu:#58a6ff;--accent:#2f81f7}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);font-family:'Segoe UI','Malgun Gothic',sans-serif;font-size:16px;line-height:1.55}
.wrap{max-width:760px;margin:0 auto;padding:14px 12px 50px}
h1{font-size:1.25rem;margin:0 0 2px}
.date{color:var(--mut);font-size:.82rem;margin-bottom:14px}
.sec{background:var(--card);border:1px solid var(--bd);border-radius:12px;margin-bottom:12px;overflow:hidden}
.sec>h2{font-size:1.02rem;margin:0;padding:12px 14px;background:#1c2330}
.sec .body{padding:12px 14px}
details>summary{font-size:1rem;font-weight:700;padding:12px 14px;cursor:pointer;list-style:none;background:#1c2330}
details>summary::-webkit-details-marker{display:none}
details>summary::after{content:' [+]';color:var(--mut)}
details[open]>summary::after{content:' [-]'}
details .body{padding:12px 14px}
table{width:100%;border-collapse:collapse;font-size:.84rem;margin-top:4px}
th,td{padding:6px 8px;text-align:left;border-bottom:1px solid var(--bd);white-space:nowrap}
th{color:var(--mut);font-weight:600}
td.vd{white-space:normal;color:#c9d3de}
.bdg{font-size:.72rem;padding:1px 8px;border-radius:999px;font-weight:700;white-space:nowrap}
.b-ok{background:rgba(63,185,80,.16);color:var(--grn)}
.b-warn{background:rgba(210,153,34,.16);color:var(--yel)}
.b-act{background:rgba(248,81,73,.16);color:var(--red)}
.b-info{background:rgba(88,166,255,.16);color:var(--blu)}
.chip{display:inline-block;font-size:.78rem;background:#1c2330;border:1px solid var(--bd);border-radius:8px;padding:2px 8px;margin:2px 4px 2px 0}
.note{color:var(--mut);font-size:.8rem;margin:8px 0 0}
.empty{color:var(--mut);font-size:.86rem;padding:6px 0}
code{background:#1c2330;padding:1px 5px;border-radius:4px;font-size:.85em}
.act0{border-left:4px solid var(--accent)}
.warnbar{border-left:4px solid var(--red)}
footer{color:var(--mut);font-size:.78rem;text-align:center;margin-top:20px;border-top:1px solid var(--bd);padding-top:12px}
"""


def build_html(sc, my, ht, wl, dv, tw, public=False):
    today = datetime.date.today().isoformat()
    s1, act, warn = sec1_holdings(my, dv, public)
    s2 = sec2_model(sc)
    s3 = sec3_heat(ht)
    s4 = sec4_watch(wl)
    s5 = sec5_trackw(tw)
    parts = []
    if act:
        parts.append("<b>실보유 조치필요 " + str(act) + "건</b>")
    if warn:
        parts.append("실보유 주의 " + str(warn) + "건")
    if public:
        action = "라이브 추적 기입 · 모델픽 갱신 · (실보유 점검은 로컬 전용)"
    else:
        action = "라이브 추적 기입 · 모델픽 갱신" + (" · " + " · ".join(parts) if parts else " · 실보유 이상 없음")
    chk = "<br>".join(esc(l) for l in CHECK_LINES)
    barcls = "warnbar" if act else "act0"
    pubnote = " · <b>공개본(실보유 제외)</b>" if public else ""
    h = []
    h.append("<!DOCTYPE html><html lang='ko'><head><meta charset='UTF-8'>")
    h.append("<meta name='viewport' content='width=device-width, initial-scale=1.0'>")
    h.append("<title>진우퀀트 월간 단일화면 · " + today + "</title>")
    h.append("<style>" + CSS + "</style></head><body><div class='wrap'>")
    h.append("<h1>진우퀀트 월간 단일화면</h1>")
    h.append("<div class='date'>" + today + " · production v3.7.2(고정) · 후보!=매수신호 · 실보유!=모델픽 · 백테!=forward(현실 20%대)" + pubnote + "</div>")
    h.append("<div class='sec " + barcls + "'><h2>[0] 이번 달 액션</h2><div class='body'>" + action + "</div></div>")
    h.append("<div class='sec'><h2>[1] 실보유 위험/변경 필요</h2><div class='body'>" + s1 + "</div></div>")
    h.append("<div class='sec'><h2>[2] 모델픽 변화</h2><div class='body'>" + s2 + "</div></div>")
    h.append("<details class='sec'><summary>[3] Heat / Supercycle</summary><div class='body'>" + s3 + "</div></details>")
    h.append("<details class='sec'><summary>[4] 관찰후보 (5단계 · 매수신호 아님)</summary><div class='body'>" + s4 + "</div></details>")
    h.append("<details class='sec'><summary>[5] Track W 요약</summary><div class='body'>" + s5 + "</div></details>")
    h.append("<details class='sec'><summary>[6] 체크리스트</summary><div class='body'><div style='font-size:.84rem;color:#c9d3de'>" + chk + "</div></div></details>")
    h.append("<footer>make_월간화면.py 생성 · 백테 수치는 검증 참고값(forward 아님) · 매매 책임은 본인</footer>")
    h.append("</div></body></html>")
    return "".join(h)


def main():
    public = "--public" in sys.argv
    sc = load("v37_2_scores_latest.csv")
    my = load("my_holdings.csv", comment="#")
    ht = load("theme_heat_latest.csv")
    wl = load("kosdaq_theme_watchlist_진우기입.csv")
    if wl is None:
        wl = load("kosdaq_theme_watchlist.csv")
    dv = load("decision_view_latest.csv")
    tw = load("track_w_ledger.csv")
    out = PUB if public else OUT
    if public:
        (BASE / "docs").mkdir(exist_ok=True)
    out.write_text(build_html(sc, my, ht, wl, dv, tw, public), encoding="utf-8")
    print("생성: " + str(out) + " (" + str(out.stat().st_size) + " bytes) public=" + str(public))
    print("입력: scores=%s holdings=%s heat=%s watch=%s decision=%s trackw=%s" % (sc is not None, my is not None, ht is not None, wl is not None, dv is not None, tw is not None))


if __name__ == "__main__":
    main()
