# -*- coding: utf-8 -*-
"""휩쏘_고점_리포트_빌더.py — 3~6개월 고점 + 사이클 검정 결과를 자체완결 HTML로."""
import os, json
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
G = pd.read_csv(os.path.join(HERE, "휩쏘_고점_이벤트.csv"), dtype={"code": str})
R = json.load(open(os.path.join(HERE, "사이클검정_요약.json"), encoding="utf-8"))
C = G[(G["창완결"] == True)].dropna(subset=["고점6M"])
C = C.assign(진입월=pd.to_datetime(C["출발일"]).dt.month)

med6 = C["고점6M"].median(); med3 = C["고점3M"].median()
mdd_days = C["고점일수"].median(); in3m = (C["고점일수"] <= 63).mean()
card = pd.to_numeric(C["ex_ret"], errors="coerce").mean() * 100

# 진입월별 표
mrows = ""
for m in range(1, 13):
    s = C[C["진입월"] == m]
    if len(s) < 10: continue
    top = s["고점월"].value_counts().head(2)
    tops = " · ".join(f"{k}월({v})" for k, v in top.items())
    hero = " class=hero" if m == 12 else ""
    mrows += (f"<tr{hero}><td class=n>{m}월</td><td class=n>{len(s):,}</td>"
              f"<td class=n><b>{s['고점6M'].median():+.1f}%</b></td>"
              f"<td class=n>{s['고점일수'].median():.0f}일</td><td>{tops}</td></tr>")

# 지수 계절성 차트
seas = R["지수계절성"]
W = 720; bw = W / 12; mx = max(abs(v["평균"]) for v in seas.values()); mid = 62; sc = 50 / mx
sb = ""
for i in range(1, 13):
    v = seas[str(i)] if str(i) in seas else seas[i]
    x = (i - 1) * bw; hh = abs(v["평균"]) * sc
    col = "var(--good)" if v["평균"] >= 0 else "var(--bad)"
    y = mid - hh if v["평균"] >= 0 else mid
    hl = "opacity:1" if i in (4, 9, 10) else "opacity:.55"
    sb += f"<rect x='{x+6:.0f}' y='{y:.1f}' width='{bw-12:.0f}' height='{max(hh,1):.1f}' fill='{col}' style='{hl}'/>"
    sb += f"<text x='{x+bw/2:.0f}' y='128' font-size='10' fill='var(--mut)' text-anchor='middle'>{i}월</text>"
    sb += f"<text x='{x+bw/2:.0f}' y='{(y-4 if v['평균']>=0 else mid+hh+12):.0f}' font-size='9' fill='var(--ink2)' text-anchor='middle'>{v['평균']:+.1f}</text>"
seaschart = f"<svg viewBox='0 0 {W} 136' width='100%' style='max-width:{W}px'><line x1=0 y1={mid} x2={W} y2={mid} stroke='var(--bd)'/>{sb}</svg>"

# 9~10월 진입 고점월 분포 차트
pm = R["고점월분포"]; order = [9, 10, 11, 12, 1, 2, 3, 4, 5]
W2 = 620; bw2 = W2 / len(order); mx2 = max(pm.get(str(k), pm.get(k, 0)) for k in order)
pb = ""
for j, k in enumerate(order):
    n = pm.get(str(k), pm.get(k, 0)); hh = n / mx2 * 86
    col = "var(--b)" if k in (4, 5) else ("var(--a)" if k in (10, 11) else "var(--mut)")
    pb += f"<rect x='{j*bw2+8:.0f}' y='{96-hh:.1f}' width='{bw2-16:.0f}' height='{hh:.1f}' fill='{col}' rx='3'/>"
    pb += f"<text x='{j*bw2+bw2/2:.0f}' y='110' font-size='10' fill='var(--mut)' text-anchor='middle'>{k}월</text>"
    pb += f"<text x='{j*bw2+bw2/2:.0f}' y='{92-hh:.0f}' font-size='9.5' fill='var(--ink2)' text-anchor='middle'>{n}</text>"
pkchart = f"<svg viewBox='0 0 {W2} 118' width='100%' style='max-width:{W2}px'>{pb}</svg>"

doc = f"""<!DOCTYPE html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>휩쏘 단기고점·사이클 검정</title><style>
:root{{color-scheme:light;--bg:#f6f6f4;--sf:#fcfcfb;--bd:#e3e2dd;--ink:#0f0f0e;--ink2:#54534e;--mut:#8a877e;--a:#2a78d6;--b:#eb6834;--good:#1a7f4b;--bad:#c0342f}}
@media(prefers-color-scheme:dark){{:root{{color-scheme:dark;--bg:#111110;--sf:#1a1a19;--bd:#33322f;--ink:#fafaf7;--ink2:#c3c2b7;--mut:#8f8e85;--a:#3987e5;--b:#d95926;--good:#4bb87c;--bad:#e0655a}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Malgun Gothic","Apple SD Gothic Neo",sans-serif;font-size:14.5px;line-height:1.62}}
.w{{max-width:840px;margin:0 auto;padding:38px 20px 80px}}
h1{{font-size:24px;margin:0 0 6px}}h2{{font-size:18px;margin:32px 0 8px;padding-top:14px;border-top:2px solid var(--bd)}}
.sub{{color:var(--ink2);margin:0}}
.verdict{{background:var(--sf);border:1px solid var(--bd);border-left:4px solid var(--b);border-radius:10px;padding:15px 18px;margin:16px 0}}
.verdict b{{color:var(--b)}}
.k{{display:flex;gap:12px;flex-wrap:wrap;margin:14px 0}}
.kb{{flex:1;min-width:140px;background:var(--sf);border:1px solid var(--bd);border-radius:10px;padding:11px 13px}}
.kb .v{{font-size:21px;font-weight:700}}.kb .l{{font-size:11.5px;color:var(--mut)}}
table{{width:100%;border-collapse:collapse;margin:8px 0;font-size:13px}}
th,td{{text-align:left;padding:7px 9px;border-bottom:1px solid var(--bd)}}
th{{color:var(--ink2);font-size:11.5px;font-weight:650}}
td.n{{text-align:right;font-variant-numeric:tabular-nums}}
tr.hero td{{background:color-mix(in srgb,var(--good) 12%,transparent)}}
.good{{color:var(--good)}}.bad{{color:var(--bad)}}
.warn{{color:var(--mut);font-size:12.5px;margin-top:10px}}
ol{{padding-left:20px}}li{{margin:6px 0}}
</style></head><body><div class=w>

<h1>휩쏘 단기 고점(3~6개월)·사이클 검정</h1>
<p class=sub>역사원장 2,801건 전량 · 6M 창 완결 {len(C):,}건 · 9~10월 진입 확장검정 {R['n']}건(이듬해 5월말까지)</p>

<div class=verdict>
<b>사이클(9~10월 저점 → 4월 고점)은 지수 레벨에서 사실이다.</b> 30년 평균: 8~10월이 유일한 마이너스 구간, 4월이 연중 최강(+3.5%·플러스 65%).<br>
<b>그러나 개별 휩쏘 종목을 '4월까지 보유'하는 청산은 진다</b>(중앙 −10.8%·승률 36%). 휩쏘 반등은 빠르다 —
고점의 65%가 3개월 안, 중앙 37거래일. <b>사이클은 진입 지도, 청산은 카드</b>가 맞는 조합.
</div>

<div class=k>
<div class=kb><div class=v>{med6:+.1f}%</div><div class=l>6M 고점 중앙 (3M {med3:+.1f}%)</div></div>
<div class=kb><div class=v>{mdd_days:.0f}일</div><div class=l>고점 도달 중앙 (거래일)</div></div>
<div class=kb><div class=v>{in3m*100:.0f}%</div><div class=l>고점이 3개월 내</div></div>
<div class=kb><div class=v>{card:+.1f}%</div><div class=l>카드청산 평균 (같은 표본)</div></div>
</div>

<h2>1. 고점은 언제 오나 — 빠르다</h2>
<p>진입 후 6개월 내 최고점(신의 매도가) 중앙 <b>{med6:+.1f}%</b>. 그중 <b>65%가 3개월 안</b>에 나오고 도달 중앙은 <b>37거래일(약 2개월)</b>.
3M 고점 중앙({med3:+.1f}%)과 6M({med6:+.1f}%)의 차가 크지 않다 — <b>넉 달 더 들고 있어도 고점이 별로 안 높아진다.</b></p>
<p class=warn>고점수익은 최고점 매도 가정의 상한선 — 실현 불가. 청산 규칙 평가의 기준선으로만 쓴다.</p>

<h2>2. 진입월별 — 언제 잡힌 휩쏘가 크게 가나</h2>
<table><tr><th>진입월</th><th>표본</th><th>6M 고점 중앙</th><th>도달 중앙</th><th>고점 최빈월</th></tr>
{mrows}</table>
<p class=warn>12월 진입이 최강(+36.9%) — '저점권에 잡혀 봄 상승을 타는' 형 사이클과 부합. 8월은 표본 최다(지수 최약월 = 휩쏘 다발).</p>

<h2>3. 지수 계절성 30년 — 형 사이클의 실체</h2>
{seaschart}
<p class=warn>월평균 수익률(%). <b>8·9·10월만 마이너스</b>(저점 형성 구간), <b>4월이 연중 최강 +3.5%</b>, 1월 +3.2%, 11~12월 강세.
형이 말한 '9~10월 저점 → 4~5월 고점'의 골격이 지수에 그대로 있다 (정밀히는 저점 8~10월 · 고점 1월과 4월 쌍봉).</p>

<h2>4. 9~10월 진입 휩쏘 — 고점이 실제로 봄에 오나?</h2>
{pkchart}
<p>확장 창(이듬해 5월말까지) {R['n']}건: 고점월 <b>연내(9~12월) 52%</b> vs <b>봄(3~5월) 30%</b>.
쌍봉이다 — 절반은 <b>진입 직후 1~2개월</b>(10~11월)에 고점, 셋 중 하나는 <b>봄(4~5월)</b>에 온다.</p>
<table><tr><th>청산 방식 (9~10월 진입분)</th><th>평균</th><th>중앙</th><th>승률</th></tr>
<tr><td>카드청산 (손절·목표·트레일)</td><td class=n>{R['카드_평균']:+.1f}%</td><td class=n>—</td><td class=n>{R['카드_승률']*100:.0f}%</td></tr>
<tr><td>이듬해 4월말까지 무조건 보유</td><td class='n bad'>{R['사월청산_평균']:+.1f}%</td><td class='n bad'>{R['사월청산_중앙']:+.1f}%</td><td class='n bad'>{R['사월청산_승률']*100:.0f}%</td></tr>
</table>
<p class=warn>'4월까지 보유'가 지는 이유: 휩쏘 반등은 빨리 오고 되돌아간다. 손절 없는 달력 보유는 그 되돌림을 다 맞는다.
(공정 고지: 이 비교의 보유 시나리오는 손절이 없어 실제보다 불리하게 나온 면이 있음 — 그래도 중앙 −10.8%는 방향을 못 바꾼다.)</p>

<h2>5. 그래서 — 청산 규칙</h2>
<ol>
<li><b>기본 청산은 카드 그대로</b> (목표/손절/트레일). 고점의 65%가 3개월 내 — 빠른 청산이 옳다.</li>
<li><b>사이클은 진입 지도로 쓴다</b>: 8~10월(지수 최약 구간)의 휩쏘 = 최고의 사냥터. 12월 진입이 역사상 최강(+36.9%).</li>
<li><b>2단 청산 후보</b>: 목표 도달 시 절반만 팔고 나머지는 트레일 — 고점 중앙 +26.6% vs 카드 +1.1%의 간극 일부를 꼬리로 회수. (이건 다음 검정 대상)</li>
<li><b>4~5월은 '최종 시한'</b>: 봄 고점(30%)까지 살아남은 관찰중 종목은 4월 강세를 넘기지 말 것 — 목표로 삼지 말고 데드라인으로 쓴다.</li>
</ol>

<p class=warn style="margin-top:24px;border-top:1px solid var(--bd);padding-top:12px">⚠️ 검정·기록용. 백조정 가격 기준 · 생존편향 잔존 · 합성지수 한계. 매매 추천 아님. 갱신: py 휩쏘_고점분석.py → py 휩쏘_사이클검정.py → py 휩쏘_고점_리포트_빌더.py</p>
</div></body></html>"""
out = os.path.join(HERE, "휩쏘_고점사이클_리포트.html")
open(out, "w", encoding="utf-8").write(doc)
print("저장:", out)
