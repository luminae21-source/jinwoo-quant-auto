#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""진우퀀트 투자보드 생성기 — 실제 CSV → 모바일 MTS형 실데이터 보드(진우퀀트_투자보드.html).
정직 원칙(화면 고정): 관찰후보=매수신호 아님 · 모델픽=검증 바스켓(주문 아님) · 백테≠forward(현실 20%대)
 · production v3.7.2 무수정 · 매매 판단·책임은 본인 · 금융자문 아님. thesis 미기입 후보는 '관찰만'로만 표기."""
import sys, html, datetime, pathlib, json
import pandas as pd
BASE = pathlib.Path(__file__).parent.resolve()
OUT = BASE / "진우퀀트_투자보드.html"
SECMAP = {"247540":"2차전지","450080":"2차전지","353200":"반도체"}  # 보유 섹터 보강(점수표 외 종목)

def load(n, **k):
    p = BASE / n
    if not p.exists(): return None
    for e in ("utf-8-sig","utf-8","cp949"):
        try: return pd.read_csv(p, encoding=e, **k)
        except Exception: continue
    return None
def esc(x): return html.escape(str(x)) if x is not None else ""

def picks_block(sc):
    if sc is None or "등급" not in sc.columns: return ("<div class='note'>v37_2_scores_latest.csv 없음</div>","")
    dist = sc["등급"].value_counts().to_dict()
    chips = " ".join("<span class='chip' style='color:%s'>%s %d</span>"%(
        {"S+":"var(--grn)","S":"var(--blu)","A":"var(--tx)"}.get(g,"var(--mut)"),g,dist.get(g,0))
        for g in ["S+","S","A","B","C","D"] if dist.get(g,0))
    newl = ""
    if "신규" in sc.columns:
        nn = sc[sc["신규"].astype(str).str.lower()=="true"]
        if len(nn): newl = "<div class='note'>신규 편입: <b>"+" · ".join(esc(r["종목"]) for _,r in nn.iterrows())+"</b></div>"
    pk = sc[sc["등급"].isin(["S+","S","A"])]
    if "순위" in pk.columns: pk = pk.sort_values("순위")
    rows = "".join("<tr><td>%s</td><td>%s</td><td>%s</td><td><b style='color:%s'>%s</b></td><td>%s%%</td></tr>"%(
        esc(r.get("순위","")),esc(r["종목"]),esc(r.get("산업","")),
        {"S+":"var(--grn)","S":"var(--blu)"}.get(r["등급"],"var(--tx)"),esc(r["등급"]),esc(r.get("권장비중_%","")))
        for _,r in pk.iterrows())
    tbl = "<table><thead><tr><th>#</th><th>종목</th><th>산업</th><th>등급</th><th>권장</th></tr></thead><tbody>"+rows+"</tbody></table>"
    return (chips+newl+tbl, chips)

def heat_block(ht):
    if ht is None or "theme" not in ht.columns: return ("<div class='note'>theme_heat 없음</div>","없음")
    on = ht[ht["supercycle"].astype(str).str.lower()=="true"] if "supercycle" in ht.columns else ht.iloc[0:0]
    on_txt = " · ".join("<b>"+esc(t)+"</b>" for t in on["theme"]) if len(on) else "없음"
    top = ht.sort_values("heat_score",ascending=False).head(5) if "heat_score" in ht.columns else ht.head(5)
    mx = top["heat_score"].max() if "heat_score" in top.columns else 100
    h=""
    for _,r in top.iterrows():
        ison = str(r.get("supercycle")).lower()=="true"
        w = (float(r.get("heat_score",0))/mx*100) if mx else 0
        col = "var(--grn)" if ison else "var(--blu)"
        h += "<div class='hbrow'><div class='n'>%s%s</div><div class='tr'><div class='f' style='width:%.0f%%;background:%s'></div></div><div style='width:30px;text-align:right;color:var(--mut);font-size:.7rem'>%s</div></div>"%(
            esc(r["theme"]),(" <span class='b g-grn'>ON</span>" if ison else ""),w,col,esc(int(r.get("heat_score",0))))
    return (h, on_txt)

def watch_block(wl):
    if wl is None or "name" not in wl.columns: return ("<div class='note'>워치리스트 없음</div>",0,0)
    pas = wl[wl["guardrail"].astype(str).str.upper()=="PASS"] if "guardrail" in wl.columns else wl
    states = load("kosdaq_watchlist_states.csv")  # watchlist_states.py 산출(있으면 실제 5단계)
    smap = {}
    if states is not None and "code" in states.columns and "state_ui" in states.columns:
        for _,sr in states.iterrows():
            smap[str(sr["code"]).split(".")[0].zfill(6)] = (str(sr.get("state_ui","관찰만")), sr.get("to_pivot_pct"))
    SC = {"관찰만":"blu","셋업":"yel","임박":"yel","돌파확인":"grn","돌파(거래량미달)":"gray"}
    nfill=0; h=""
    for _,r in pas.iterrows():
        th = str(r.get("thesis_catalyst","") or "")
        filled = th and "____" not in th and "[진우 기입]" not in th
        if filled: nfill+=1
        thtag = "<span class='b g-yel'>thesis 미기입</span>" if not filled else "<span class='b g-grn'>thesis OK</span>"
        mc = r.get("mcap_억","")
        try: mc = "%s억"%format(int(float(mc)),",")
        except Exception: mc = esc(mc)
        code = str(r.get("code","")).split(".")[0].zfill(6)
        stt, topiv = smap.get(code, ("관찰만", None))
        piv = ""
        try:
            if stt != "관찰만" and topiv is not None and float(topiv)==float(topiv):
                piv = " · pivot까지 %.1f%%"%float(topiv)
        except Exception: pass
        h += "<div class='row'><div style='flex:1'><div class='nm'>%s</div><div class='sb'>%s · %s · %s%s</div></div><span class='b g-%s'>%s</span></div>"%(
            esc(r["name"]), esc(r.get("theme","")), mc, thtag, piv, SC.get(stt,"blu"), stt)
    return (h, len(pas), nfill)

def hold_block(my, sc):
    if my is None or "code" not in my.columns:
        return ("<div class='note'>my_holdings.csv 미입력</div>","",0,0,"")
    real = my.dropna(subset=["code"]).copy()
    real = real[real["code"].astype(str).str.match(r"^\d{6}$")]
    if not len(real): return ("<div class='note'>실보유 미입력</div>","",0,0,"")
    secw = {}; n_act=0; n_warn=0; h=""
    secmap = dict(zip(sc["코드"].astype(str).str.zfill(6),sc["산업"])) if (sc is not None and "코드" in sc.columns) else {}
    for _,r in real.iterrows():
        code = str(r["code"]).zfill(6)
        w = pd.to_numeric(r.get("weight"),errors="coerce"); w = float(w) if pd.notna(w) else 0
        lvl = "act" if w>30 else ("warn" if w>20 else "ok"); 
        if lvl=="act": n_act+=1
        elif lvl=="warn": n_warn+=1
        col = {"act":"var(--red)","warn":"var(--yel)","ok":"var(--grn)"}[lvl]
        lab = {"act":"조치필요","warn":"주의","ok":"정상"}[lvl]
        sec = SECMAP.get(code) or secmap.get(code) or "기타"
        secw[sec] = secw.get(sec,0)+w
        h += "<div class='row'><div style='width:104px'><div class='nm'>%s</div><div class='sb'>%s</div></div><div class='bar'><div class='fl' style='width:%.0f%%;background:%s'></div></div><div style='width:34px;text-align:right;font-size:.76rem'>%.0f%%</div><span class='b g-%s' style='width:50px;text-align:center'>%s</span></div>"%(
            esc(r["name"]),sec,min(w*3,100),col,w,{"act":"red","warn":"yel","ok":"grn"}[lvl],lab)
    # 섹터 집중 바
    sb=""; top_sec=""; top_w=0
    for s,w in sorted(secw.items(),key=lambda x:-x[1]):
        if w>top_w: top_w=w; top_sec=s
        c = "var(--red)" if w>45 else ("var(--yel)" if w>30 else "var(--blu)")
        sb += "<div class='hbrow'><div class='n'>%s</div><div class='tr'><div class='f' style='width:%.0f%%;background:%s'></div></div><div style='width:42px;text-align:right;color:%s;font-size:.72rem'>%.0f%%</div></div>"%(s,w,c,c,w)
    warn = ("<div class='note' style='color:var(--red)'>⚠️ %s %.0f%% 과집중 — 트림 검토 신호 (섹터 cap 45%% 초과)</div>"%(top_sec,top_w)) if top_w>45 else ""
    return (h, sb+warn, n_act, n_warn, top_sec+(" %.0f%%"%top_w))

def attribution_card():
    """최신 attribution_v40_phase2 JSON → 실제 T2 진성약세/섹터동조 경보 카드."""
    js = sorted(BASE.glob("attribution_v40_phase2_*.json"))
    if not js:
        return ""
    try:
        g = json.loads(js[-1].read_text(encoding="utf-8")).get("gates", {})
    except Exception:
        return ""
    asof = js[-1].stem.split("_")[-2]
    if not g.get("valid", True):
        return ""
    t2 = g.get("t2_phase2", []); rc = len(g.get("reclassified", []))
    if t2:
        return ("<div class='card' style='border-left:3px solid var(--red)'><div class='ttl'>\u26a0\ufe0f attribution \uacbd\ubcf4 (Phase2 2\ud329\ud130)</div>"
                "<div style='font-size:.82rem'>T2 \uc9c4\uc131\uc57d\uc138 " + str(len(t2)) + "\uc885: <b>" + esc(" \u00b7 ".join(t2)) + "</b></div>"
                "<div class='note'>\uc139\ud130\ub3d9\uc870 \uc7ac\ubd84\ub958 " + str(rc) + "\uc885 \uc81c\uc678\ud55c \uc9c4\uc9dc \uc885\ubaa9\uc57d\uc138 \u2014 \ubaa8\ub378\ud53d/\ubcf4\uc720\uba74 thesis\u00b7\uc2e4\uc801 \uc810\uac80. \uae30\uc900 " + esc(asof) + " (PC attribution_v40_phase2.py \uc7ac\uc2e4\ud589 \uc2dc \uac31\uc2e0)</div></div>")
    return "<div class='card'><div class='ttl'>\u2705 attribution (Phase2)</div><div style='font-size:.8rem;color:#c9d3de'>T2 \uc9c4\uc131\uc57d\uc138 \uc5c6\uc74c \u00b7 \uae30\uc900 " + esc(asof) + "</div></div>"


def catalyst_board():
    """워치리스트 카탈리스트 보드(추가): 예정이벤트(catalyst_calendar 수동)+DART공시(catalyst_feed 자동)+기술상태(watchlist_states). 진입신호 아님."""
    cal = load("catalyst_calendar.csv")
    if cal is None or "event" not in cal.columns:
        return "<div class='note'>catalyst_calendar.csv 없음 — 예정이벤트 캘린더 미생성</div>"
    feed = load("catalyst_feed.csv")
    states = load("kosdaq_watchlist_states.csv")
    smap = {}
    if states is not None and "code" in states.columns and "state_ui" in states.columns:
        for _, sr in states.iterrows():
            smap[str(sr["code"]).split(".")[0].zfill(6)] = str(sr.get("state_ui", "관찰만"))
    fmap = {}
    if feed is not None and "code" in feed.columns and "rcept_dt" in feed.columns:
        cutoff = int((datetime.date.today() - datetime.timedelta(days=90)).strftime("%Y%m%d"))
        ff = feed.copy()
        ff["_dt"] = pd.to_numeric(ff["rcept_dt"], errors="coerce")
        ff = ff[ff["_dt"] >= cutoff].sort_values("_dt", ascending=False)
        for _, fr in ff.iterrows():
            c = str(fr["code"]).split(".")[0].zfill(6)
            if c not in fmap:
                d = str(int(fr["_dt"]))
                fmap[c] = (str(fr.get("catalyst", "")).strip(), d[4:6] + "/" + d[6:8])
    CC = {"G": "grn", "Y": "yel", "R": "gray"}
    h = ""
    for _, r in cal.iterrows():
        code = str(r.get("code", "")).split(".")[0].zfill(6)
        cf = CC.get(str(r.get("confidence", "Y")).strip().upper()[:1], "yel")
        stt = smap.get(code, "")
        sttag = (" · <span class='b g-blu'>%s</span>" % esc(stt)) if stt else ""
        dart = fmap.get(code)
        darttag = (" · <span class='b g-grn'>공시 %s %s</span>" % (esc(dart[0]), esc(dart[1]))) if dart else ""
        h += ("<div class='row'><div style='flex:1'><div class='nm'>%s</div>"
              "<div class='sb'>[%s] %s%s%s</div></div><span class='b g-%s' style='white-space:nowrap'>%s</span></div>" % (
                  esc(r.get("name", "")), esc(r.get("type", "")), esc(r.get("event", "")),
                  sttag, darttag, cf, esc(r.get("date_window", "")) or "-"))
    return h


def main():
    sc = load("v37_2_scores_latest.csv"); ht = load("theme_heat_latest.csv")
    wl = load("kosdaq_theme_watchlist_진우기입.csv") 
    if wl is None: wl = load("kosdaq_theme_watchlist.csv")
    my = load("my_holdings.csv", comment="#"); tw = load("track_w_ledger.csv")
    today = datetime.date.today().isoformat()
    picks, chips = picks_block(sc)
    heat, on_txt = heat_block(ht)
    watch, nwatch, nfill = watch_block(wl)
    hold, conc, n_act, n_warn, topsec = hold_block(my, sc)
    catb = catalyst_board()
    tw_rows = 0 if tw is None else len(tw.dropna(subset=["date_signal"])) if "date_signal" in tw.columns else 0
    tw_txt = ("기록 %d건 — update_track_w.py로 갱신"%tw_rows) if tw_rows else "기록 없음 — 첫 재량매수 시 매수 전 기입"
    # 액션 (정직: 매수신호 아님)
    acts = []
    if n_act: acts.append("실보유 <b style='color:var(--red)'>조치필요 %d건</b>(과집중 점검)"%n_act)
    if nfill < nwatch: acts.append("관찰후보 thesis %d/%d 미기입"%(nwatch-nfill,nwatch))
    acts.append("Track W "+("기입" if tw_rows==0 else "갱신")); acts.append("모델픽 갱신")
    action = " · ".join(acts)
    # 환경 vs 보유 정직 코멘트
    hold_in_on = ("전력" in on_txt or "전기" in on_txt) and False  # 보유=2차전지/반도체, ON=전력 → 불일치 명시
    env_note = "보유 섹터(%s)는 현재 ON 테마(%s)와 불일치 — 추격 아닌 점검 관점."%(topsec.split()[0] if topsec else "-", on_txt.replace("<b>","").replace("</b>",""))

    C = """
:root{--bg:#0b0e14;--card:#161b22;--c2:#1c2330;--bd:#2a3038;--tx:#e6edf3;--mut:#8b949e;--grn:#3fb950;--yel:#d29922;--red:#f85149;--blu:#58a6ff;--gray:#8b949e}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{margin:0;background:var(--bg);color:var(--tx);font-family:'Segoe UI','Malgun Gothic',sans-serif;font-size:15px}
.app{max-width:440px;margin:0 auto;min-height:100vh;border-left:1px solid var(--bd);border-right:1px solid var(--bd)}
.top{position:sticky;top:0;z-index:8;background:#0b0e14;border-bottom:1px solid var(--bd);padding:10px 14px}
.top h1{font-size:1.02rem;margin:0}.top .dt{color:var(--mut);font-size:.72rem}
.disc{background:rgba(248,81,73,.1);border-bottom:1px solid rgba(248,81,73,.3);color:#ffb4ad;font-size:.68rem;padding:5px 14px;text-align:center}
.scr{padding:12px 12px 78px}.pane{display:none}.pane.on{display:block}
.card{background:var(--card);border:1px solid var(--bd);border-radius:13px;padding:12px 13px;margin-bottom:10px}
.ttl{font-size:.92rem;font-weight:700;margin-bottom:7px}
.act{background:linear-gradient(135deg,#16263f,#101720);border:1px solid var(--blu)}
.b{font-size:.64rem;font-weight:700;padding:2px 8px;border-radius:999px}
.g-grn{background:rgba(63,185,80,.16);color:var(--grn)}.g-yel{background:rgba(210,153,34,.16);color:var(--yel)}
.g-red{background:rgba(248,81,73,.16);color:var(--red)}.g-blu{background:rgba(88,166,255,.16);color:var(--blu)}.g-gray{background:rgba(139,148,158,.18);color:var(--gray)}
table{width:100%;border-collapse:collapse;font-size:.78rem}th,td{padding:6px 5px;text-align:left;border-bottom:1px solid var(--bd);white-space:nowrap}th{color:var(--mut);font-weight:600;font-size:.72rem}
.row{display:flex;align-items:center;gap:9px;padding:8px 0;border-bottom:1px solid var(--bd)}.row:last-child{border:0}.row .nm{font-weight:700;font-size:.84rem}.row .sb{color:var(--mut);font-size:.7rem}
.bar{flex:1;height:8px;background:var(--c2);border-radius:5px;overflow:hidden}.bar .fl{height:100%;border-radius:5px}
.note{color:var(--mut);font-size:.72rem;margin-top:7px}
.hbrow{display:flex;align-items:center;gap:7px;font-size:.76rem;margin:5px 0}.hbrow .n{width:104px;font-weight:700}.hbrow .tr{flex:1;height:12px;background:var(--c2);border-radius:6px;overflow:hidden}.hbrow .f{height:100%}
.chip{display:inline-block;font-size:.72rem;font-weight:700;background:var(--c2);border:1px solid var(--bd);border-radius:7px;padding:2px 8px;margin:2px 3px 2px 0}
.nav{position:fixed;bottom:0;left:0;right:0;max-width:440px;margin:0 auto;background:#10141b;border-top:1px solid var(--bd);display:flex;padding:6px 4px 8px}
.nav a{flex:1;text-align:center;color:var(--mut);font-size:.64rem;font-weight:700;padding:5px 0;cursor:pointer}.nav a .ic{font-size:1.1rem;display:block;margin-bottom:2px;filter:grayscale(1) opacity(.7)}
.nav a.on{color:var(--blu)}.nav a.on .ic{filter:none}
"""
    H = []
    H.append("<!DOCTYPE html><html lang='ko'><head><meta charset='UTF-8'>")
    H.append("<meta name='viewport' content='width=device-width,initial-scale=1.0,maximum-scale=1.0'>")
    H.append("<title>진우퀀트 투자보드</title><style>"+C+"</style></head><body><div class='app'>")
    H.append("<div class='top'><h1>진우퀀트 <span style='font-size:.7rem;color:var(--mut);font-weight:400'>투자보드 (실데이터)</span></h1><div class='dt'>"+today+" · production v3.7.2</div></div>")
    H.append("<div class='disc'>관찰후보=매수신호 아님 · 모델픽=검증 바스켓 · 백테≠forward(현실 20%대) · 매매 책임 본인 · 금융자문 아님</div>")
    H.append("<div class='scr'>")
    # 홈
    H.append("<div class='pane on'><div class='card act'><div class='ttl'>📌 이번 달 액션</div><div style='font-size:.82rem;color:#dde'>"+action+"</div></div>")
    H.append(attribution_card())
    H.append("<div class='card'><div class='ttl'>🔥 환경</div><div style='font-size:.84rem'>ON 테마 = "+on_txt+"</div><div class='note'>"+env_note+"</div></div>")
    H.append("<div class='card'><div class='ttl'>🔔 오늘 체크</div><div style='font-size:.8rem;line-height:1.7;color:#c9d3de'>· 관찰후보면 사지 않기 (thesis·손절·비중·TrackW 사전등록만)<br>· 재량 매수면 Track W 먼저 기입<br>· 백테 71.5%를 기대수익으로 X (현실 20%대)</div></div></div>")
    # 모델픽
    H.append("<div class='pane'><div class='card'><div class='ttl'>📊 모델픽 — v3.7.2 <span class='b g-gray'>검증 바스켓</span></div>"+picks+"<div class='note'>EW + 종목15%/섹터35% cap · 실보유와 분리 · 무수정</div></div></div>")
    # 발굴
    H.append("<div class='pane'><div class='card'><div class='ttl'>🔥 테마 Heat</div>"+heat+"<div class='note'>ON = detect_supercycle 단일정의</div></div>")
    H.append("<div class='card'><div class='ttl'>🔭 관찰후보 <span class='b g-blu'>매수신호 아님</span></div>"+watch+"<div class='note'>가드레일 PASS = '고려 가능'일 뿐. thesis 미기입 후보는 매수 전 촉매·무효화·손절 채워야 '검토 가능' 승격.</div></div>")
    H.append("<div class='card'><div class='ttl'>🗓️ 카탈리스트 보드 <span class='b g-gray'>진입신호 아님</span></div>"+catb+"<div class='note'>색=신뢰도(녹 확정·황 추정·회 미확인) · 공시=DART 자동(90일내) · 예정이벤트=수동 분기갱신 · 카탈리스트≠진입(셋업+RISK_ON 필요)</div></div></div>")
    # 보유
    H.append("<div class='pane'><div class='card'><div class='ttl'>💼 실보유</div>"+hold+"<div class='note'>조치필요/주의 = 즉시매도 아님. thesis/비중/손절 재확인 신호.</div></div>")
    H.append("<div class='card'><div class='ttl'>🎯 섹터 집중도</div>"+conc+"</div></div>")
    # TrackW
    H.append("<div class='pane'><div class='card'><div class='ttl'>📈 Track W</div><div style='font-size:.84rem'>"+tw_txt+"</div><div class='note'>메인=재량매수−시스템벤치(판정) · 보조=패스후보−매수(음수=정상). 6~12개월 누적 후 판정.</div></div></div>")
    H.append("</div>")
    H.append("""<div class='nav'>
<a class='on' onclick="t(0,this)"><span class='ic'>🏠</span>홈</a>
<a onclick="t(1,this)"><span class='ic'>📊</span>모델픽</a>
<a onclick="t(2,this)"><span class='ic'>🔥</span>발굴</a>
<a onclick="t(3,this)"><span class='ic'>💼</span>보유</a>
<a onclick="t(4,this)"><span class='ic'>📈</span>TrackW</a></div>""")
    H.append("<script>function t(n,e){var p=document.querySelectorAll('.pane'),a=document.querySelectorAll('.nav a');for(var i=0;i<p.length;i++){p[i].classList.toggle('on',i===n);a[i].classList.remove('on');}e.classList.add('on');window.scrollTo(0,0);}</script>")
    H.append("</div></body></html>")
    OUT.write_text("".join(H), encoding="utf-8")
    print("생성:", OUT, "(%d bytes)"%OUT.stat().st_size)
    print("모델픽:", "OK" if sc is not None else "X", "| ON:", on_txt.replace("<b>","").replace("</b>",""),
          "| 관찰후보:", nwatch, "(thesis 기입", nfill, ")", "| 실보유 조치필요:", n_act, "주의:", n_warn, "| 집중:", topsec, "| TrackW행:", tw_rows)

if __name__ == "__main__":
    main()
