# -*- coding: utf-8 -*-
"""재무검정 결과 → 자체완결 HTML."""
import os, json
HERE = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(os.path.join(HERE, "재무검정_요약.json"), encoding="utf-8"))

def tbl(scope, key):
    base = R[scope][key]["기준"]; rows = R[scope][key]["표"]
    out = (f"<table><tr><th>{key} 군</th><th>표본</th><th>40일 평균</th><th>Δ기준</th>"
           "<th>승률</th><th>카드</th><th>6M고점 중앙</th></tr>")
    for s in rows:
        d = s["Δ40"]
        hero = " class=hero" if d >= 2.0 else ""
        dc = "good" if d > 0 else "bad"
        out += (f"<tr{hero}><td>{s['군']}</td><td class=n>{s['n']:,}</td>"
                f"<td class=n><b>{s['f40']:+.1f}%</b></td><td class='n {dc}'>{d:+.1f}%p</td>"
                f"<td class=n>{s['w40']*100:.0f}%</td><td class=n>{s['ex']:+.1f}%</td>"
                f"<td class=n>{s['peak']:+.1f}%</td></tr>")
    out += (f"<tr><td style='color:var(--mut)'>기준(전 표본)</td><td class=n>{base['n']:,}</td>"
            f"<td class=n>{base['f40']:+.1f}%</td><td class=n>—</td><td class=n>{base['w40']*100:.0f}%</td>"
            f"<td class=n>{base['ex']:+.1f}%</td><td class=n>{base['peak']:+.1f}%</td></tr></table>")
    return out

doc = f"""<!DOCTYPE html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>휩쏘 재무 팩터 전량 검정</title><style>
:root{{color-scheme:light;--bg:#f6f6f4;--sf:#fcfcfb;--bd:#e3e2dd;--ink:#0f0f0e;--ink2:#54534e;--mut:#8a877e;--a:#2a78d6;--b:#eb6834;--good:#1a7f4b;--bad:#c0342f}}
@media(prefers-color-scheme:dark){{:root{{color-scheme:dark;--bg:#111110;--sf:#1a1a19;--bd:#33322f;--ink:#fafaf7;--ink2:#c3c2b7;--mut:#8f8e85;--a:#3987e5;--b:#d95926;--good:#4bb87c;--bad:#e0655a}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Malgun Gothic","Apple SD Gothic Neo",sans-serif;font-size:14.5px;line-height:1.62}}
.w{{max-width:840px;margin:0 auto;padding:38px 20px 80px}}
h1{{font-size:24px;margin:0 0 6px}}h2{{font-size:18px;margin:30px 0 8px;padding-top:14px;border-top:2px solid var(--bd)}}
h3{{font-size:15px;margin:18px 0 6px;color:var(--ink2)}}
.sub{{color:var(--ink2);margin:0}}
.verdict{{background:var(--sf);border:1px solid var(--bd);border-left:4px solid var(--b);border-radius:10px;padding:15px 18px;margin:16px 0}}
.verdict b{{color:var(--b)}}
table{{width:100%;border-collapse:collapse;margin:8px 0 14px;font-size:13px}}
th,td{{text-align:left;padding:7px 9px;border-bottom:1px solid var(--bd)}}
th{{color:var(--ink2);font-size:11.5px;font-weight:650}}
td.n{{text-align:right;font-variant-numeric:tabular-nums}}
tr.hero td{{background:color-mix(in srgb,var(--good) 12%,transparent)}}
.good{{color:var(--good)}}.bad{{color:var(--bad)}}
.warn{{color:var(--mut);font-size:12.5px;margin-top:8px}}
ol{{padding-left:20px}}li{{margin:6px 0}}
</style></head><body><div class=w>

<h1>휩쏘 재무 팩터 — 전량 검정</h1>
<p class=sub>역사원장 × KRX 월별 재무(2002-02~) 결합 {R['표본']:,}건(40일 확정) · 진입 시점 PER·PBR·배당 기준</p>

<div class=verdict>
<b>국면을 통제하고도 살아남은 팩터: 저PBR(&lt;0.8) · 저PER(&lt;8) · 배당 2%+.</b><br>
실행 국면 안에서 저PBR은 40일 +12.1%(기준 +8.2% 대비 <b>+3.8%p</b>·승률 64%·카드 +4.5%), 저PER +2.5%p(승 67%), 고배당은 승률 68%.<br>
반대로 <b>'적자 전환기가 세다'·'고PER 주도주 눌림이 세다' 가설은 기각</b> — 국면 통제 후 Δ≈0, 더 세지도 약하지도 않다.
</div>

<h2>1. 원시 비교 (국면 무시) — 착시 포함</h2>
<h3>PER</h3>{tbl('전체','PER')}
<h3>PBR</h3>{tbl('전체','PBR')}
<h3>배당</h3>{tbl('전체','배당')}
<p class=warn>원시 비교에서 저PBR +5.3%p·고배당 +4.1%p로 커 보이지만, 밸류주는 위기 국면(실행)에 잘 걸리는 편향이 섞여 있다 — 그래서 아래 국면 통제가 본검정.</p>

<h2>2. 실행 국면만 (국면 통제) — 진짜 리프트</h2>
<h3>PER</h3>{tbl('실행국면만','PER')}
<h3>PBR</h3>{tbl('실행국면만','PBR')}
<h3>배당</h3>{tbl('실행국면만','배당')}
<p class=warn>통제 후에도 저PBR +3.8%p·저PER +2.5%p·배당2%+ 승률 68%가 남는다. 고배당의 원시 +4.1%p는 통제 후 +1.2%p로 줄었다(상당 부분 국면 착시였다는 뜻) — 승률 개선은 실재.</p>

<h2>3. 판정과 적용</h2>
<ol>
<li><b>밸류 가점, 필터 아님.</b> 저PBR·저PER·고배당은 후보가 많을 때의 <b>우선순위</b>로 쓴다. 필터로 걸면 표본의 2/3를 버리게 된다.</li>
<li><b>적자·고PER 감점 금지.</b> 국면 통제 후 중립 — 셀트리온 2008(고PER)·하이닉스 2024(적자)처럼 큰 승리가 여기서도 나온다.</li>
<li><b>본체와의 일관성.</b> 진우퀀트 본체(가치·배당 엔진)는 검정을 통과했고 성장 스크리닝은 기각됐었다 — 휩쏘에서도 같은 방향. <b>검증된 두 엣지(국면 게이트 × 밸류)가 겹치는 자리</b>가 최상급.</li>
<li><b>탐색기에 '밸류' 태그 추가</b> — 탐지 결과에 저PBR/저PER/배당2%+ 표시(가점 표기용, 등급 아님).</li>
</ol>

<h2>한계 (정직 고지)</h2>
<p class=warn>① 이벤트가 시간적으로 뭉쳐 있어(위기해 클러스터) 독립 표본 가정이 약함 — Δ+3.8%p는 시사이지 확정이 아니다. ② KRX PER/PBR은 월말 스냅숏(진입일과 최대 1개월 시차). ③ 2002년 이전 333건 제외. ④ PER 0 처리(적자/무실적 혼재)는 KRX 관행을 따름.</p>

<p class=warn style="margin-top:24px;border-top:1px solid var(--bd);padding-top:12px">⚠️ 검정·기록용. 매매 추천 아님. 재현: py 휩쏘_재무검정.py → py 휩쏘_재무검정_리포트_빌더.py</p>
</div></body></html>"""
open(os.path.join(HERE, "휩쏘_재무검정_리포트.html"), "w", encoding="utf-8").write(doc)
print("저장: 휩쏘_재무검정_리포트.html")
