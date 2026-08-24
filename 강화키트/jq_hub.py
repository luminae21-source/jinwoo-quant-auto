#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""jq_hub.py — 진우퀀트 통합 허브 (한 화면에서 다 보기)

강화키트의 모든 리포트를 한 페이지로 모으고, jq_history.db의 최신 지표·추세를 요약해
'진우퀀트_허브.html'을 만들어 연다. 흩어진 파일을 찾아다닐 필요 없는 중심 화면.
사용: py jq_hub.py   (recommend_pipeline / recommend_verify 마지막에 자동 호출)
⚠️ 정보·검증용·투자자문 아님·책임 본인.
"""
import os, sys, sqlite3, glob, webbrowser
BASE=os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
DB=os.path.join(BASE,"jq_history.db")

# 큐레이션: (파일명, 라벨, 카테고리)
CURATED=[
 ("추천대시보드.html","오늘의 추천 종목","daily"),
 ("risk_manager.html","집행 시트(손절·비중)","daily"),
 ("entry_screener.html","진입 스크리너(A/B등급)","daily"),
 ("style_screener.html","두 갈래 스크리너","daily"),
 ("진우퀀트_빠른사용법.html","빠른 사용법","doc"),
 ("진우퀀트_시스템요약.html","시스템 종합 요약","doc"),
 ("factor_efficacy.html","팩터 효력 검정","verify"),
 ("style_conditional_factor.html","스타일별 조건부 팩터","verify"),
 ("entry_timing_test.html","진입 타이밍 검정","verify"),
 ("exit_routing_backtest.html","매도 라우팅 백테","verify"),
 ("ev_fcf_factor_test.html","EV/FCF 팩터 검정","verify"),
 ("multifactor_screen.html","멀티팩터 스크리너","verify"),
 ("해외상관.html","한국↔미국·홍콩 상관","verify"),
 ("종합스캔_현재.html","종합 스캔(기술적)","scan"),
 ("반등신호_현재.html","반등 신호","scan"),
 ("트레이딩구간_현재.html","트레이딩 구간","scan"),
 ("성장관심주.html","성장 관심주","scan"),
 ("셀프테스트_현황.html","셀프테스트 현황(전 모듈 통과/실패)","sys"),
 # ── 연구 (2026-08-20 추가) · 연구뷰_생성.py 가 만든다
 ("연구_현황.html","현재 상태 한 장 ★","research"),
 ("연구_무기목록.html","질문·무기 대장","research"),
 ("연구_백서.html","진우퀀트 백서 (1,909줄)","research"),
 ("연구_런북.html","수정주가 런북","research"),
 ("연구_리빌딩.html","v5 리빌딩 마스터플랜","research"),
 ("연구_재조명.html","재조명 리포트","research"),
 ("연구_인수인계.html","휩쏘 인수인계 3판","research"),
 ("연구_프로토콜.html","Claude 분석 프로토콜","research"),
]
CATS=[("daily","🎯 매주 보는 것 (추천·집행)"),("research","🧭 연구 — 지금 무엇을 묻고 있나"),("verify","🔬 검증 리포트 (근거)"),
      ("scan","🔎 스캔"),("doc","📄 문서"),("sys","🛡 시스템 상태 (안전판)")]

def q(cx,sql,args=()):
    try: return cx.execute(sql,args).fetchall()
    except Exception: return []

def build():
    have={f for f in os.listdir(BASE) if f.endswith(".html")} if os.path.isdir(BASE) else set()
    cx=sqlite3.connect(DB) if os.path.exists(DB) else None
    # 최신 날짜
    rd=None
    if cx:
        r=q(cx,"SELECT MAX(run_date) FROM metrics"); rd=r[0][0] if r and r[0][0] else None
    def latest(source,metric):
        if not cx or not rd: return None
        r=q(cx,"SELECT value FROM metrics WHERE run_date=? AND source=? AND metric=?",(rd,source,metric))
        return r[0][0] if r else None
    # KPI
    div_ic=latest("factor","배당수익률"); mf_sh=latest("multifactor","ls_sharpe")
    nA=latest("reco","nA")
    nsell=0
    if cx and rd:
        r=q(cx,"SELECT COUNT(*) FROM holds WHERE run_date=? AND sev>=2",(rd,)); nsell=r[0][0] if r else 0
    def kpi(v,lab,fmt="{:+.3f}"):
        s="-" if v is None else (fmt.format(v) if isinstance(v,float) else str(int(v)))
        return f'<div class=kpi><div class=v>{s}</div><div class=k>{lab}</div></div>'
    KPI=(kpi(div_ic,"배당 IC(최신)")+kpi(mf_sh,"멀티팩터 Sharpe","{:.2f}")+
         kpi(nA,"추천 A진입","{:.0f}")+kpi(float(nsell),"보유 매도신호","{:.0f}"))
    # 추세: 배당·E/P·B/P IC 히스토리
    trend=""
    if cx:
        dates=[r[0] for r in q(cx,"SELECT DISTINCT run_date FROM metrics ORDER BY run_date")][-6:]
        facs=[("배당수익률","배당"),("가치 E/P(이익수익률)","E/P"),("가치 B/P(순자산)","B/P")]
        if dates:
            head="<tr><th>팩터 IC</th>"+"".join(f"<th class=r>{d[5:]}</th>" for d in dates)+"</tr>"
            body=""
            for src,lab in facs:
                cells=""
                for d in dates:
                    r=q(cx,"SELECT value FROM metrics WHERE run_date=? AND source='factor' AND metric=?",(d,src))
                    v=r[0][0] if r else None
                    cells+=f"<td class=r>{('%+.3f'%v) if v is not None else '-'}</td>"
                body+=f"<tr><td class=nm>{lab}</td>{cells}</tr>"
            trend=f"<table>{head}{body}</table><div class=note>월별 재검증마다 한 칸씩 늘어납니다. IC가 크게 꺾이면 그때만 점검.</div>"
    if cx: cx.close()
    # 링크 그리드
    linked=set(); sections=""
    for cat,title in CATS:
        items=[(f,lab) for (f,lab,c) in CURATED if c==cat and f in have]
        if not items: continue
        cards="".join(f'<a class=lk href="{f}">{lab}<span>{f}</span></a>' for f,lab in items)
        for f,_ in items: linked.add(f)
        sections+=f'<div class=card><h3>{title}</h3><div class=grid>{cards}</div></div>'
    others=sorted(f for f in have if f not in linked and f!="진우퀀트_허브.html")
    if others:
        cards="".join(f'<a class=lk sub href="{f}">{f}</a>' for f in others[:30])
        sections+=f'<div class=card><h3>🗂 기타 리포트</h3><div class=grid>{cards}</div></div>'
    # 🌀 휩쏘 재진입 시스템 — 채택/검증중 분리 (파일은 상위 폴더 = 진우퀀트 루트)
    ROOT=os.path.dirname(BASE)
    def wlinks(items):
        out=""
        for rel,lab,st in items:
            if os.path.exists(os.path.join(ROOT,rel)):
                out+=f'<a class=lk href="../{rel}">{lab}<span>{st}</span></a>'
        return out
    wadopt=[
      ("휩쏘_시스템.html","휩쏘 시스템 개요","시스템 문서"),
      ("휩쏘_역사검정_리포트.html","30년 역사검정","2,801건·재현 100%"),
      ("휩쏘_역사원장.html","30년 역사원장","전 종목 도장"),
      ("휩쏘_2단청산_리포트.html","2단청산 판정","조건부 채택"),
      ("휩쏘_S2_리포트.html","S2 근접미달형","채택·3등급"),
      ("휩쏘_고점사이클_리포트.html","고점·사이클","검정 완료"),
      ("휩쏘_재무검정_리포트.html","재무팩터 검정","가점용·통과"),
      ("휩쏘_케이스집.html","케이스집 1~8","해설"),
      ("휩쏘_종합보고서.html","종합 보고서","통합"),
    ]
    wverify=[
      ("휩쏘_MA240_사전등록.md","MA240 완화(A′)","사전등록·40건 대기"),
      ("휩쏘_1월앵커_리포트.html","1월 앵커 청산","보류·전진검증"),
      ("휩쏘_관찰_현황.html","2026 전진판정","617건 관찰 중"),
    ]
    wa=wlinks(wadopt); wv=wlinks(wverify)
    if wa or wv:
        ws='<div class=card><h3>🌀 휩쏘 재진입 시스템</h3>'
        if wa:
            ws+='<div class=note><b>✅ 채택 — 30년 검정 통과(재현검증 100%).</b> 핵심 A/B형 신호 + 국면 게이트가 확정 코어. 단 in-sample+전진추적 단계로, 봉인 5종급 사전등록 OOS 통과는 아니며 생존편향·이벤트 클러스터 한계가 원문에 명시돼 있다.</div>'
            ws+=f'<div class=grid>{wa}</div>'
        if wv:
            ws+='<div class=note style="margin-top:10px"><b>⏳ 검증 중 — 추가검증 필요(전진검증 대기).</b> 아래는 아직 채택 아님: 사전등록만 됐거나 보류 상태다.</div>'
            ws+=f'<div class=grid>{wv}</div>'
        ws+='<div class=warn>휩쏘 신호는 매수신호가 아니라 관찰 후보다. 국면 🔴관찰만에서는 떠도 사지 않는다.</div></div>'
        sections=ws+sections
    # ── 🗓 오늘 보는 것 (2026-08-20 추가) — 매일 덮어써지는 이름고정 산출물.
    #    신선도를 같이 표시한다: 자동화가 멈추면 여기서 바로 드러난다.
    import time as _t
    TODAY=[("시장브리핑_최신.html","시장 브리핑"),
           ("익일예측_최신.html","익일예측 KOSPI"),
           ("익일예측_최신_kosdaq.html","익일예측 KOSDAQ"),
           ("진우사냥터_현황판.html","사냥터 현황판"),
           ("진우_타점발굴_표.html","타점 발굴"),
           ("진우_모의매매_현황.html","모의매매 현황"),
           ("진우_주문생성_현황.html","주문 생성"),
           ("가상매매_현황.html","가상매매 현황"),
           ("보유점검_최신.html","보유 점검"),
           ("종목군_월별현황.html","종목군 월별")]
    tcards=""; stale=0
    for rel,lab in TODAY:
        fp=os.path.join(ROOT,rel)
        if not os.path.exists(fp): continue
        age=int((_t.time()-os.path.getmtime(fp))/86400)
        if age<=1: note="오늘" if age==0 else "어제"
        elif age<=7: note=f"{age}일 전"
        else: note=f"⚠️ {age}일 전"; stale+=1
        tcards+=f'<a class=lk href="../{rel}">{lab}<span>{note}</span></a>'
    if tcards:
        warn=f'<div class=warn>⚠️ {stale}개가 7일 넘게 안 갱신됐다 — 해당 자동화가 멈췄는지 확인.</div>' if stale else ''
        sections=('<div class=card><h3>🗓 오늘 보는 것</h3>'
                  '<div class=note>매일 덮어써지는 산출물. 날짜 붙은 사본은 <b>산출물\\</b> 로 수거된다.</div>'
                  f'<div class=grid>{tcards}</div>{warn}</div>')+sections
    # ── 🔗 월간 운용 사슬 (2026-08-20) — 어디서 막혔는지 매번 보여준다.
    #    2026-08 발견: 원장이 6월에 멈췄는데 아무도 몰랐다. 사슬 첫 칸(재무)이 끊겨서였다.
    #    실패해도 허브 자체는 떠야 하므로 통째로 감싼다.
    try:
        import 운용사슬 as _chain
        sections = _chain.card_html() + sections
    except Exception as _e:
        sections = ('<div class=card><h3>🔗 월간 운용 사슬</h3>'
                    f'<div class=warn>사슬 점검 실패: {_e}</div></div>') + sections
    asof=rd or "데이터 없음"
    html=f"""<!doctype html><html lang=ko><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>진우퀀트 허브</title><style>
:root{{--bg:#0b1020;--card:#141b2e;--ink:#e8edf6;--sub:#9fb0c9;--line:#243149;--acc:#5b9dff}}
@media(prefers-color-scheme:light){{:root{{--bg:#f4f6fb;--card:#fff;--ink:#0f1830;--sub:#5a6a86;--line:#e3e9f4;--acc:#2563eb}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,'Segoe UI',Roboto,'Malgun Gothic',sans-serif;padding:22px;line-height:1.5}}
.wrap{{max-width:960px;margin:0 auto}}h1{{font-size:22px;margin:0 0 2px}}.sub{{color:var(--sub);font-size:12.5px;margin-bottom:16px}}
.kpis{{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:14px}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:11px 15px;flex:1;min-width:120px}}
.kpi .v{{font-size:20px;font-weight:700}}.kpi .k{{color:var(--sub);font-size:11.5px;margin-top:2px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:15px 16px;margin-bottom:13px}}
h3{{font-size:14.5px;margin:0 0 11px;color:var(--acc)}}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:9px}}
a.lk{{display:block;background:rgba(91,157,255,.10);border:1px solid var(--line);border-radius:10px;padding:11px 13px;text-decoration:none;color:var(--ink);font-weight:600;font-size:13px}}
a.lk span{{display:block;color:var(--sub);font-weight:400;font-size:10.5px;margin-top:2px}}
a.lk:hover{{border-color:var(--acc)}}a.lk[sub]{{font-weight:400;font-size:11.5px;color:var(--sub)}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}th,td{{padding:6px 7px;border-bottom:1px solid var(--line);text-align:left}}
th{{color:var(--sub);font-weight:600;font-size:10.5px}}td.r,th.r{{text-align:right;font-variant-numeric:tabular-nums}}.nm{{font-weight:600}}
.note{{color:var(--sub);font-size:11.5px;margin-top:8px}}.warn{{color:#e0a32e;font-size:11px;margin-top:10px}}
</style></head><body><div class=wrap>
<h1>진우퀀트 허브</h1>
<div class=sub>최신 스냅샷 {asof} · 리포트·추천·검증·이력을 한 곳에서 · 파일 클릭하면 열림</div>
<div class=kpis>{KPI}</div>
{sections}
<div class=card><h3>📈 팩터 IC 이력(재검증 추세)</h3>{trend or '<div class=note>이력이 아직 없어요. 재검증(recommend_verify)이 돌면 쌓입니다.</div>'}</div>
<div class=card><div class=note>이력 DB: jq_history.db (metrics·picks·holds). recommend_auto/verify 실행마다 자동 축적·허브 갱신.</div>
<div class=warn>⚠️ 정보·검증용·과거통계. 미래·수익 보장 아님. 투자자문 아님 · 최종 판단·책임 본인.</div></div>
</div></body></html>"""
    out=os.path.join(BASE,"진우퀀트_허브.html"); open(out,"w",encoding="utf-8").write(html)
    print(f"허브 생성: 진우퀀트_허브.html (링크 {len(linked)} · 최신 {asof})")
    return out

def main():
    out=build()
    if "--no-open" not in sys.argv:
        try: webbrowser.open("file://"+out.replace("\\","/"))
        except Exception: pass

if __name__=="__main__":
    main()
