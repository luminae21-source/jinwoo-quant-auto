#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우_리서치런처.py — 후보 종목 → 리서치 원클릭 조회 런처(자체완결 HTML).

용도: 딥밸류 후보의 '파산임박 배제'(생존심사) 스터디용. KIRS(중소형주 리서치·시총5천억↓)를
     최우선으로, 종목마다 KIRS·네이버·FnGuide·DART·KIND를 원클릭.
정직: 스터디 목적은 '좋은 회사 고르기'가 아니라 '역배열·계속기업 리스크만 확인'. 퀄리티 업그레이드 금지.

읽기: 진우_타점발굴.csv(딥/후보) + 진우_관심종목.csv + my_holdings.csv
산출: 진우_리서치런처.html
사용: py 진우_리서치런처.py
"""
import os, sys, csv, json, urllib.parse
BASE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def load_universe():
    U = {}
    def add(c, n, tag, extra=""):
        c = c.zfill(6); e = U.setdefault(c, [n or c, set(), ""])
        if n and (not e[0] or e[0] == c): e[0] = n
        e[1].add(tag)
        if extra and not e[2]: e[2] = extra
    p = os.path.join(BASE, "진우_타점발굴.csv")
    if os.path.exists(p):
        with open(p, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                r = {k.lstrip("﻿"): v for k, v in r.items()}
                if r.get("deep") == "1": add(r["code"], r.get("name",""), "딥밸류", f"PBR {r.get('pbr','')}·이격 {r.get('ext','')}")
                elif r.get("bounce") == "1": add(r["code"], r.get("name",""), "바닥반등")
    for fn, tag in [("진우_관심종목.csv","관심"), ("my_holdings.csv","보유")]:
        p = os.path.join(BASE, fn)
        if os.path.exists(p):
            with open(p, encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    r = {k.lstrip("﻿"): v for k, v in r.items()}
                    if r.get("code"): add(r["code"], r.get("name",""), tag, r.get("메모",""))
    return U

def main():
    U = load_universe()
    rows = []
    for c, (name, tags, note) in sorted(U.items(), key=lambda x: (0 if "딥밸류" in x[1][1] else 1, x[0])):
        qn = urllib.parse.quote(name)
        rows.append(dict(code=c, name=name, tags="·".join(sorted(tags)), note=note,
                         deep=1 if "딥밸류" in tags else 0,
                         naver=f"https://finance.naver.com/item/main.naver?code={c}",
                         report=f"https://finance.naver.com/item/news_notice.naver?code={c}",
                         fn=f"http://comp.fnguide.com/SVO2/ASP/SVD_Main.asp?pGB=1&gicode=A{c}",
                         kirs=f"https://www.google.com/search?q=site:kirs.or.kr+{qn}+리서치",
                         dart=f"https://dart.fss.or.kr/dsab007/main.do?textCrpNm={qn}",
                         kind=f"https://kind.krx.co.kr/common/searchcorpname.do?method=searchCorpNameMain&searchCorpName={qn}"))
    html = HTML.replace("__DATA__", json.dumps(rows, ensure_ascii=False)).replace("__N__", str(len(rows)))
    open(os.path.join(BASE, "진우_리서치런처.html"), "w", encoding="utf-8").write(html)
    print(f"저장: 진우_리서치런처.html ({len(rows)}종 · 딥밸류 {sum(r['deep'] for r in rows)}종)")

HTML = r"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><title>리서치 런처</title><style>
body{background:#0d1016;color:#c8ccd4;font-family:-apple-system,'Malgun Gothic',sans-serif;margin:0;padding:16px;font-size:13px}
.note{background:#12181f;border:1px solid #24303c;border-radius:10px;padding:11px 15px;margin-bottom:12px;line-height:1.6;font-size:12.5px}
.note b{color:#ffca3a}
h2{margin:0 0 4px} .sub{color:#7a828e;font-size:12px;margin-bottom:10px}
input{background:#12151c;border:1px solid #2a3140;color:#c8ccd4;border-radius:8px;padding:6px 10px;width:220px;margin-bottom:10px}
table{border-collapse:collapse;width:100%} td,th{padding:6px 8px;border-bottom:1px solid #1c2230;text-align:left;white-space:nowrap}
th{color:#9aa2ae} tr:hover td{background:#151a24}
.deep{color:#ffca3a;font-weight:700} .tag{font-size:11px;color:#7a828e} .memo{color:#6b7482;font-size:11px}
a.btn{display:inline-block;padding:3px 9px;margin:1px;border-radius:6px;text-decoration:none;font-size:11.5px;border:1px solid #2a3550;color:#bcd0ea;background:#141b28}
a.btn:hover{background:#1d2740;color:#fff} a.k{border-color:#4a6a3a;color:#a8d08a;background:#16210f}
</style></head><body>
<div class="note"><b>사용법:</b> 종목별 버튼 클릭 → <b>KIRS리서치</b>(구글로 그 종목 KIRS 보고서 검색·시총5천억↓ 중소형주 무상리서치)·<b>증권리포트/FnGuide/네이버</b>(코드 직링크·재무·컨센서스)·<b>DART/KIND</b>(공시). <b>목적 = 파산임박 배제만</b>(감사거절·계속기업·관리종목 확인), '좋은 회사 고르기' 아님(퀄리티 업그레이드=역효과 검증). 리스크 없으면 못생겨도 분산 편입.</div>
<h2>리서치 런처</h2><div class="sub" id="sub"></div>
<input id="q" placeholder="종목명 검색">
<table><thead><tr><th>종목</th><th>분류</th><th>리서치 조회</th></tr></thead><tbody id="tb"></tbody></table>
<script>
const DATA=__DATA__;
document.getElementById('sub').textContent=`대상 __N__종 · KIRS는 이름검색(페이지 열림) · 네이버/FnGuide는 직링크`;
function draw(q){
  const a=q?DATA.filter(r=>r.name.includes(q)):DATA;
  document.getElementById('tb').innerHTML=a.map(r=>`<tr>
   <td class="${r.deep?'deep':''}">${r.deep?'◆ ':''}${r.name} <span class="tag">${r.code}</span>${r.note?`<br><span class="memo">${r.note}</span>`:''}</td>
   <td class="tag">${r.tags}</td>
   <td>
     <a class="btn k" href="${r.kirs}" target="_blank">KIRS리서치</a>
     <a class="btn" href="${r.report}" target="_blank">증권리포트</a>
     <a class="btn" href="${r.fn}" target="_blank">FnGuide재무</a>
     <a class="btn" href="${r.naver}" target="_blank">네이버</a>
     <a class="btn" href="${r.dart}" target="_blank">DART공시</a>
     <a class="btn" href="${r.kind}" target="_blank">KIND</a>
   </td></tr>`).join('');
}
document.getElementById('q').addEventListener('input',e=>draw(e.target.value.trim()));
draw('');
</script></body></html>"""

if __name__ == "__main__":
    main()
