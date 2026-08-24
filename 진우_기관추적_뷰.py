#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우_기관추적_뷰.py — 후보/관심/보유 종목별 기관·외국인 순매수 추적 뷰(자체완결 HTML).

★모니터링용. 검증결과 기관매집은 매수 엣지가 아님(무엣지~음)·호황엔 오히려 경계 신호.
  (사냥터_기획/진우_수급오버레이_검증.md, _교차확인_로그.md) → 매수근거 금지·맥락 참고만.

읽기: flow_ext_monthly_{KOSPI,KOSDAQ}.csv + 진우_타점발굴.csv/진우_관심종목.csv/my_holdings.csv + 종목시총_30년.csv
산출: 진우_기관추적_뷰.html (브라우저)
사용: py 진우_기관추적_뷰.py [--months 12]
"""
import os, sys, csv, json, argparse
BASE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def load_flow():
    """{code: {ym: (inst, foreign)}} + 정렬된 월 목록."""
    F = {}; yms = set()
    for m in ("KOSPI", "KOSDAQ"):
        p = os.path.join(BASE, f"flow_ext_monthly_{m}.csv")
        if not os.path.exists(p): continue
        with open(p, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                r = {k.lstrip("﻿"): v for k, v in r.items()}
                c = r["code"].zfill(6); ym = r["date"][:7]
                try: inn = float(r.get("inst_net") or 0)
                except ValueError: inn = 0.0
                try: fn = float(r.get("foreign_net") or 0)
                except ValueError: fn = 0.0
                F.setdefault(c, {})[ym] = (inn, fn); yms.add(ym)
    return F, sorted(yms)

def load_universe():
    """{code: (name, tags)} — 타점발굴(딥)·관심·보유 합집합."""
    U = {}
    def add(c, n, tag):
        c = c.zfill(6); e = U.setdefault(c, [n or c, set()])
        if n and not e[0]: e[0] = n
        e[1].add(tag)
    p = os.path.join(BASE, "진우_타점발굴.csv")
    if os.path.exists(p):
        with open(p, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                r = {k.lstrip("﻿"): v for k, v in r.items()}
                add(r["code"], r.get("name",""), "딥밸류" if r.get("deep")=="1" else "후보")
    for fn, tag in [("진우_관심종목.csv","관심"), ("my_holdings.csv","보유")]:
        p = os.path.join(BASE, fn)
        if os.path.exists(p):
            with open(p, encoding="utf-8-sig", newline="") as f:
                for r in csv.DictReader(f):
                    r = {k.lstrip("﻿"): v for k, v in r.items()}
                    if r.get("code"): add(r["code"], r.get("name",""), tag)
    return U

def load_mcap():
    p = os.path.join(BASE, "종목시총_30년.csv"); M = {}
    if not os.path.exists(p): return M
    last = None; rows = []
    with open(p, encoding="utf-8-sig", newline="") as f:
        rd = csv.reader(f); next(rd, None)
        for r in rd:
            if len(r) < 3: continue
            rows.append((r[0][:7], r[1].zfill(6), r[2]))
    if not rows: return M
    last = max(x[0] for x in rows)
    for ym, c, v in rows:
        if ym == last:
            try: M[c] = float(v)
            except ValueError: pass
    return M

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--months", type=int, default=12)
    a = ap.parse_args()
    F, yms = load_flow()
    if not yms: sys.exit("flow_ext_monthly 없음 — 먼저 수급 수집 필요")
    recent = yms[-a.months:]; U = load_universe(); M = load_mcap()
    rows = []
    for c, (name, tags) in U.items():
        fm = F.get(c)
        if not fm: continue
        series = [fm.get(ym, (0.0, 0.0))[0] for ym in recent]      # 기관 월별
        fser = [fm.get(ym, (0.0, 0.0))[1] for ym in recent]        # 외국인 월별
        # 연속 개월(최신부터 순매수>0)
        streak = 0
        for v in reversed(series):
            if v > 0: streak += 1
            else: break
        cum3 = sum(series[-3:]); cum6 = sum(series[-6:]); fcum3 = sum(fser[-3:])
        mcap = M.get(c, 0); inten = (cum6 / mcap * 100) if mcap > 0 else 0
        rows.append(dict(code=c, name=name[:16], tags="·".join(sorted(tags)),
                         spark=[round(x/1e8) for x in series], streak=streak,
                         cum3=round(cum3/1e8), cum6=round(cum6/1e8),
                         inten=round(inten, 2), fcum3=round(fcum3/1e8),
                         deep=1 if "딥밸류" in tags else 0))
    rows.sort(key=lambda r: (-r["streak"], -r["inten"]))
    html = build_html(rows, recent)
    out = os.path.join(BASE, "진우_기관추적_뷰.html")
    open(out, "w", encoding="utf-8").write(html)
    print(f"저장: 진우_기관추적_뷰.html ({len(rows)}종 · {recent[0]}~{recent[-1]})")

def build_html(rows, months):
    data = json.dumps(rows, ensure_ascii=False)
    mlabels = json.dumps([m[2:] for m in months], ensure_ascii=False)
    return r"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<title>기관 매집 추적 뷰</title><style>
body{background:#0d1016;color:#c8ccd4;font-family:-apple-system,'Malgun Gothic',sans-serif;margin:0;padding:16px;font-size:13px}
.warn{background:#2a1a1a;border:1px solid #5a2a2a;border-radius:10px;padding:12px 16px;margin-bottom:14px;line-height:1.6}
.warn b{color:#e2606a}
h2{margin:0 0 4px} .sub{color:#7a828e;margin-bottom:12px;font-size:12px}
table{border-collapse:collapse;width:100%} th,td{padding:6px 8px;border-bottom:1px solid #1c2230;text-align:right;white-space:nowrap}
th{cursor:pointer;color:#9aa2ae;position:sticky;top:0;background:#12151c} th:hover{color:#fff}
td.l,th.l{text-align:left} tr:hover td{background:#151a24}
.spark{display:inline-flex;align-items:flex-end;gap:1px;height:22px}
.bar{width:5px;border-radius:1px} .up{background:#3fb37a} .dn{background:#e2606a}
.tag{font-size:11px;color:#7a828e} .deep{color:#ffca3a;font-weight:700}
.pos{color:#3fb37a} .neg{color:#e2606a} .st{color:#e0b020;font-weight:700}
</style></head><body>
<div class="warn"><b>⚠ 모니터링용 · 매수 신호 아님.</b> 검증 결과 기관 매집은 초과수익 엣지가 아니며(무엣지~음), 특히 <b>산업 호황 국면에선 오히려 경계 신호</b>다(딥밸류 안에서 기관매집·누적강도는 유의하게 음). 여기 숫자는 "돈이 어디로 쏠리나" 맥락 참고일 뿐, <b>매수 근거로 쓰지 말 것.</b> 진입은 검증된 딥밸류 바닥 + 분산으로.</div>
<h2>기관 매집 추적 뷰</h2><div class="sub" id="sub"></div>
<table id="t"><thead><tr>
<th class="l" data-k="name">종목</th>
<th class="l" data-k="tags">분류</th>
<th data-k="streak">연속(월)</th>
<th class="l">기관 최근흐름(월별 순매수, 초록=매수/빨강=매도)</th>
<th data-k="cum3">3M누적(억)</th>
<th data-k="cum6">6M누적(억)</th>
<th data-k="inten">강도(6M/시총%)</th>
<th data-k="fcum3">외국인3M(억)</th>
</tr></thead><tbody id="tb"></tbody></table>
<script>
const DATA=__DATA__, MLAB=__MLAB__;
let sortK="streak", asc=false;
document.getElementById('sub').textContent=`대상 ${DATA.length}종 · 최근 ${MLAB.length}개월(${MLAB[0]}~${MLAB[MLAB.length-1]}) · 기관 순매수 흐름`;
function spark(arr){
  const mx=Math.max(1,...arr.map(v=>Math.abs(v)));
  return '<span class="spark">'+arr.map(v=>{const h=Math.max(2,Math.round(Math.abs(v)/mx*20));return `<span class="bar ${v>=0?'up':'dn'}" style="height:${h}px" title="${v}억"></span>`}).join('')+'</span>';
}
function won(n){return (n>0?'+':'')+n.toLocaleString('ko-KR')}
function draw(){
  const a=DATA.slice().sort((x,y)=>{let v=x[sortK]>y[sortK]?1:x[sortK]<y[sortK]?-1:0;return asc?v:-v});
  document.getElementById('tb').innerHTML=a.map(r=>`<tr>
    <td class="l ${r.deep?'deep':''}">${r.deep?'◆ ':''}${r.name} <span class="tag">${r.code}</span></td>
    <td class="l tag">${r.tags}</td>
    <td class="st">${r.streak}</td>
    <td class="l">${spark(r.spark)}</td>
    <td class="${r.cum3>=0?'pos':'neg'}">${won(r.cum3)}</td>
    <td class="${r.cum6>=0?'pos':'neg'}">${won(r.cum6)}</td>
    <td class="${r.inten>=0?'pos':'neg'}">${r.inten.toFixed(2)}</td>
    <td class="${r.fcum3>=0?'pos':'neg'}">${won(r.fcum3)}</td></tr>`).join('');
}
document.querySelectorAll('#t th[data-k]').forEach(th=>th.addEventListener('click',()=>{const k=th.dataset.k;if(sortK===k)asc=!asc;else{sortK=k;asc=(k==='name'||k==='tags');}draw();}));
draw();
</script></body></html>""".replace("__DATA__", data).replace("__MLAB__", mlabels)

if __name__ == "__main__":
    main()
