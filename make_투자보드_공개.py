#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""진우퀀트 투자보드 (공개용) — 실보유·섹터집중도·TrackW(개인 포지션) 제외.
모델픽(검증 바스켓)·테마 Heat·관찰후보·카탈리스트 보드만. make_투자보드.py 블록 재사용(로직 단일화).
공개·공유 안전: 개인 보유/매매기록 미포함. 매수신호·투자권유 아님."""
import importlib.util, pathlib, datetime
BASE = pathlib.Path(__file__).parent.resolve()
_spec = importlib.util.spec_from_file_location("_mb", BASE / "make_투자보드.py")
mb = importlib.util.module_from_spec(_spec); _spec.loader.exec_module(mb)
mb.BASE = BASE  # 블록들이 이 폴더 CSV를 읽도록
load = mb.load; picks_block = mb.picks_block; heat_block = mb.heat_block
watch_block = mb.watch_block; catalyst_board = mb.catalyst_board; attribution_card = mb.attribution_card

OUT = BASE / "진우퀀트_투자보드_공개.html"
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

def main():
    sc = load("v37_2_scores_latest.csv"); ht = load("theme_heat_latest.csv")
    wl = load("kosdaq_theme_watchlist_진우기입.csv")
    if wl is None: wl = load("kosdaq_theme_watchlist.csv")
    today = datetime.date.today().isoformat()
    picks, chips = picks_block(sc)
    heat, on_txt = heat_block(ht)
    watch, nwatch, nfill = watch_block(wl)
    catb = catalyst_board()
    acts = []
    if nfill < nwatch: acts.append("관찰후보 thesis " + str(nwatch - nfill) + "/" + str(nwatch) + " 미기입")
    acts.append("모델픽 갱신")
    action = " · ".join(acts)
    H = []
    H.append("<!DOCTYPE html><html lang='ko'><head><meta charset='UTF-8'>")
    H.append("<meta name='viewport' content='width=device-width,initial-scale=1.0,maximum-scale=1.0'>")
    H.append("<title>진우퀀트 투자보드 (공개)</title><style>" + C + "</style></head><body><div class='app'>")
    H.append("<div class='top'><h1>진우퀀트 <span style='font-size:.7rem;color:var(--mut);font-weight:400'>투자보드 (공개)</span></h1><div class='dt'>" + today + " · production v3.7.2</div></div>")
    H.append("<div class='disc'>공개용 — 실보유·개인 포지션 제외 · 모델·연구 정보 · 매수신호/투자권유 아님</div>")
    H.append("<div class='scr'>")
    H.append("<div class='pane on'><div class='card act'><div class='ttl'>📌 이번 달 포커스</div><div style='font-size:.82rem;color:#dde'>" + action + "</div></div>")
    H.append(attribution_card())
    H.append("<div class='card'><div class='ttl'>🔥 환경</div><div style='font-size:.84rem'>ON 테마 = " + on_txt + "</div></div>")
    H.append("<div class='card'><div class='ttl'>🔔 원칙</div><div style='font-size:.8rem;line-height:1.7;color:#c9d3de'>· 관찰후보 = 매수신호 아님<br>· 모델픽 = 검증 바스켓(실주문 아님)<br>· 백테 ≠ forward(현실 20%대)</div></div></div>")
    H.append("<div class='pane'><div class='card'><div class='ttl'>📊 모델픽 — v3.7.2 <span class='b g-gray'>검증 바스켓</span></div>" + picks + "<div class='note'>EW + 종목15%/섹터35% cap · 검증용 바스켓 · 실주문 아님</div></div></div>")
    H.append("<div class='pane'><div class='card'><div class='ttl'>🔥 테마 Heat</div>" + heat + "<div class='note'>ON = detect_supercycle 단일정의</div></div>")
    H.append("<div class='card'><div class='ttl'>🔭 관찰후보 <span class='b g-blu'>매수신호 아님</span></div>" + watch + "<div class='note'>가드레일 PASS = '고려 가능'일 뿐. thesis 미기입 후보는 매수 전 촉매·무효화·손절 채워야 '검토 가능' 승격.</div></div>")
    H.append("<div class='card'><div class='ttl'>🗓️ 카탈리스트 보드 <span class='b g-gray'>진입신호 아님</span></div>" + catb + "<div class='note'>색=신뢰도(녹 확정·황 추정·회 미확인) · 공시=DART 자동(90일내) · 카탈리스트≠진입(셋업+RISK_ON 필요)</div></div></div>")
    H.append("</div>")
    H.append("""<div class='nav'>
<a class='on' onclick="t(0,this)"><span class='ic'>🏠</span>홈</a>
<a onclick="t(1,this)"><span class='ic'>📊</span>모델픽</a>
<a onclick="t(2,this)"><span class='ic'>🔥</span>발굴</a></div>""")
    H.append("<script>function t(n,e){var p=document.querySelectorAll('.pane'),a=document.querySelectorAll('.nav a');for(var i=0;i<p.length;i++){p[i].classList.toggle('on',i===n);a[i].classList.remove('on');}e.classList.add('on');window.scrollTo(0,0);}</script>")
    H.append("</div></body></html>")
    OUT.write_text("".join(H), encoding="utf-8")
    print("생성(공개):", OUT, "(%d bytes)" % OUT.stat().st_size, "| 관찰후보:", nwatch, "| 모델픽:", "OK" if sc is not None else "X")

if __name__ == "__main__":
    main()
