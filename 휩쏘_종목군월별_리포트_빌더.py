# -*- coding: utf-8 -*-
"""종목군월별 결과 → 자체완결 HTML (사전등록 규율 명시판)."""
import os, json
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
R = json.load(open(os.path.join(HERE, "종목군월별_요약.json"), encoding="utf-8"))

hyp_rows = ""
for t in R["가설"]:
    v = "<span class='chip cG'>유의</span>" if t["유의"] else "<span class='chip cM'>유의 아님</span>"
    hyp_rows += (f"<tr><td>{t['가설']}</td><td class=n>{t['n']}</td><td class=n>{t['군평균']}</td>"
                 f"<td class=n><b>{t['Δ']:+.2f}%p</b></td>"
                 f"<td class=n>[{t['CI'][0]:+.2f}, {t['CI'][1]:+.2f}]</td><td>{v}</td></tr>")

mon = R["월별"]
def mrow(lab):
    row = mon[lab]; out = f"<tr><td>{lab}</td>"
    for m in range(1, 13):
        c = row[str(m)] if str(m) in row else row.get(m, {})
        n = c.get("n", 0); a = c.get("평균")
        if not n or a is None: out += "<td class='n mut'>·</td>"; continue
        cls = "mut" if n < 30 else ("good" if a > 0 else "bad")
        out += f"<td class='n {cls}'>{a:+.1f}<span class=c> {n}</span></td>"
    return out + "</tr>"
mtab = "".join(mrow(k) for k in mon.keys())

doc = f"""<!DOCTYPE html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>§10-A 종목군별 월별 매매현황</title><style>
:root{{color-scheme:light;--bg:#f6f6f4;--sf:#fcfcfb;--bd:#e3e2dd;--ink:#0f0f0e;--ink2:#54534e;--mut:#8a877e;--a:#2a78d6;--b:#eb6834;--good:#1a7f4b;--bad:#c0342f}}
@media(prefers-color-scheme:dark){{:root{{color-scheme:dark;--bg:#111110;--sf:#1a1a19;--bd:#33322f;--ink:#fafaf7;--ink2:#c3c2b7;--mut:#8f8e85;--a:#3987e5;--b:#d95926;--good:#4bb87c;--bad:#e0655a}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Malgun Gothic","Apple SD Gothic Neo",sans-serif;font-size:14.5px;line-height:1.62}}
.w{{max-width:900px;margin:0 auto;padding:38px 20px 80px}}
h1{{font-size:23px;margin:0 0 6px}}h2{{font-size:17px;margin:28px 0 8px;padding-top:12px;border-top:2px solid var(--bd)}}
.sub{{color:var(--ink2);margin:0}}
.verdict{{background:var(--sf);border:1px solid var(--bd);border-left:4px solid var(--b);border-radius:10px;padding:14px 17px;margin:16px 0}}
table{{width:100%;border-collapse:collapse;margin:8px 0;font-size:12.5px}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--bd);white-space:nowrap}}
th{{color:var(--ink2);font-size:11px;font-weight:650}}
td.n{{text-align:right;font-variant-numeric:tabular-nums}}
.good{{color:var(--good)}}.bad{{color:var(--bad)}}.mut{{color:var(--mut)}}
.c{{color:var(--mut);font-size:9.5px}}
.chip{{display:inline-block;padding:1px 9px;border-radius:20px;font-size:11px;font-weight:700;color:#fff}}
.cG{{background:var(--good)}}.cM{{background:var(--mut)}}
.warn{{color:var(--mut);font-size:12.5px;margin-top:8px}}
</style></head><body><div class=w>

<h1>§10-A 종목군별 월별 매매현황</h1>
<p class=sub>PRIMARY = 🟢실행 × (정식A ∪ S2-α) {R['PRIMARY_n']:,}건 · 사전등록 설계(가설 3건만 판정 · 월별 36칸은 기술통계) · 2026-08-16</p>

<div class=verdict>
<b>판정: 밸류(H2)만 유의. 체인(H1)은 방향은 맞지만 경계선 미달, 성장 분류축(H3)은 차이 증거 없음.</b><br>
월별 표는 참고용 — 칸별로 "이 달이 좋다"고 읽는 것은 이 프로젝트에서 기각된 방식이다.
</div>

<h2>1. 사전가설 판정 (부트스트랩 2000회 · 클러스터 미보정)</h2>
<table><tr><th>가설</th><th>표본</th><th>군 평균</th><th>Δ</th><th>95% CI</th><th>판정</th></tr>
{hyp_rows}</table>
<p class=warn>H1: Δ+0.61%p, 단측 5% 하한 −0.05 — 아깝게 0을 물었다. "체인 우위"는 방향성 시사로만 남기고 채택하지 않는다.
H2: 밸류 우위 재확인(3번째 독립 확인 — 재무검정·밸류교집합·본 검정). H3: 성장군에서 휩쏘가 다르게 작동한다는 증거 없음
— 성장 팩터 기각과 정합적("성장은 도움도 해도 안 된다"). ②↔③ 대조 결론: <b>축으로서 살아있는 건 밸류뿐.</b></p>

<h2>2. 월별 매매현황 — 기술통계 (판정 금지 · 회색=n&lt;30)</h2>
<table><tr><th>군</th>{"".join(f"<th style='text-align:right'>{m}월</th>" for m in range(1,13))}</tr>
{mtab}</table>
<p class=warn>작은 숫자 = 그 칸 표본수. 눈에 띄는 패턴(2~3월·8월 강세, 5월 약세)은 지수 계절성과 방향이 같지만
사전등록되지 않았으므로 <b>관찰로만 기록</b>한다. 쓰고 싶으면 사전등록 → 전진검증 절차를 거칠 것.</p>

<h2>3. 한계</h2>
<p class=warn>① 체인/섹터 맵은 현재 스냅숏 — look-ahead·생존편향(섹터 미상 종목 제외). ② 성장 판정은 2019-05 이후 1,078건뿐(표본 짧음).
③ 이벤트 위기해 클러스터 — CI는 미보정. ④ 밸류·체인·성장은 겹칠 수 있는 3축이지 파티션이 아님.
⑤ 성장군 결과가 어떻든 <b>선정 규칙 승격 금지</b>(성장 팩터 기각 이력).</p>

<p class=warn style="margin-top:22px;border-top:1px solid var(--bd);padding-top:11px">⚠️ 검정·기록용. 재현: py 휩쏘_종목군월별.py · 자체검증(이중계산) 통과 · 일관성감사 등록은 PC측 TODO.</p>
</div></body></html>"""
open(os.path.join(HERE, "휩쏘_종목군월별_리포트.html"), "w", encoding="utf-8").write(doc)
print("저장: 휩쏘_종목군월별_리포트.html")
