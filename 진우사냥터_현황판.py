#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우사냥터_현황판.py — 진우사냥터_후보.csv → 자체완결 HTML 현황판

진우사냥터_스크리너.py가 만든 CSV를 읽어, 서버 없이 브라우저에서 바로 열리는
인터랙티브 현황판(HTML)을 만든다. 데이터는 HTML 안에 JSON으로 박아 넣는다.

기능: 6종목 하이라이트 · 출처/6종목 필터 · 컬럼 정렬 · 손절/수량 표시.
사용: py 진우사냥터_현황판.py            (진우사냥터_후보.csv → 진우사냥터_현황판.html)
      py 진우사냥터_현황판.py --self-test

투자자문 아님 · 발굴 ≠ 매수신호 · 결정·책임은 본인.
"""
import os, sys, csv, json, argparse, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
CSV_IN = os.path.join(BASE, "진우사냥터_후보.csv")
HTML_OUT = os.path.join(BASE, "진우사냥터_현황판.html")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def read_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        def num(k, d=0.0):
            try:
                return float(r.get(k, "") or d)
            except ValueError:
                return d
        out.append({
            "rank": int(num("rank")),
            "code": r.get("code", ""),
            "name": r.get("name", ""),
            "sector": r.get("sector", ""),
            "src": r.get("src", ""),
            "score": round(num("score"), 3),
            "pbr": round(num("pbr"), 2),
            "pbr_rank": int(num("pbr_rank")),
            "vol": round(num("vol60") * 100, 1),
            "vol_rank": int(num("vol_rank")),
            "close": int(num("close")),
            "stop": int(num("stop")),
            "stop_pct": round(num("stop_pct"), 1),
            "qty": int(num("qty")),
            "j6": str(r.get("is_jinwoo6", "")).strip().lower() in ("true", "1"),
        })
    return out


def build_html(rows, meta):
    data_json = json.dumps(rows, ensure_ascii=False)
    n = len(rows)
    j6 = [r for r in rows if r["j6"]]
    j6_best = min((r["rank"] for r in j6), default=0)
    j6_json = json.dumps(sorted(j6, key=lambda r: r["rank"]), ensure_ascii=False)
    gen = meta.get("gen", "")
    return TEMPLATE.replace("__DATA__", data_json).replace("__J6__", j6_json) \
        .replace("__N__", str(n)).replace("__J6BEST__", str(j6_best)) \
        .replace("__J6CNT__", str(len(j6))).replace("__GEN__", gen)


TEMPLATE = r"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>진우 사냥터 현황판</title>
<style>
:root{--bg:#0f1115;--panel:#171a21;--line:#242a35;--acc:#ff7a45;--grn:#3fb37a;
--red:#e2606a;--yel:#e0b020;--txt:#e8eaed;--sub:#969ca6;--blu:#5aa0f0}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--txt);
font-family:'Malgun Gothic','맑은 고딕',system-ui,-apple-system,sans-serif;font-size:14px}
.wrap{max-width:1160px;margin:0 auto;padding:22px 18px 60px}
h1{font-size:22px;margin:0 0 4px}
.sub{color:var(--sub);font-size:13px;line-height:1.5}
.acc{color:var(--acc)}
.kpis{display:flex;gap:12px;flex-wrap:wrap;margin:18px 0}
.kpi{background:var(--panel);border:1px solid var(--line);border-radius:10px;
padding:12px 16px;min-width:150px}
.kpi .lab{color:var(--sub);font-size:12px}
.kpi .val{font-size:24px;font-weight:700;margin-top:2px}
.rule{background:var(--panel);border:1px solid var(--line);border-left:3px solid var(--acc);
border-radius:8px;padding:10px 14px;color:var(--sub);font-size:12.5px;line-height:1.6;margin:6px 0 18px}
.j6box{background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin-bottom:18px}
.j6box h2{font-size:15px;margin:0 0 10px;color:var(--acc)}
.j6row{display:flex;justify-content:space-between;gap:10px;padding:6px 0;border-bottom:1px solid var(--line);font-size:13px}
.j6row:last-child{border-bottom:none}
.j6row .nm{font-weight:600}
.j6row .rk{color:var(--acc);font-weight:700}
.bar{display:flex;gap:8px;flex-wrap:wrap;margin-bottom:10px}
.bar button{background:var(--panel);color:var(--txt);border:1px solid var(--line);
border-radius:16px;padding:6px 14px;cursor:pointer;font-size:12.5px}
.bar button.on{background:var(--acc);border-color:var(--acc);color:#181818;font-weight:700}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th,td{padding:7px 8px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--sub);font-weight:600;cursor:pointer;position:sticky;top:0;background:var(--bg);user-select:none}
th.l,td.l{text-align:left}
tr.j6{background:rgba(255,122,69,.09)}
tr.j6 td:first-child{border-left:3px solid var(--acc)}
.star{color:var(--acc)}
.src{color:var(--sub);font-size:11px}
.foot{color:var(--sub);font-size:11.5px;margin-top:16px;line-height:1.6}
.good{color:var(--grn)}.warn{color:var(--yel)}
</style></head><body><div class="wrap">
<h1>진우 사냥터 현황판 <span class="acc">· 저PBR·저변동 기울기</span></h1>
<div class="sub">진우님 스타일(대형·초고변동·고PBR 성장주) 안에서 상대적으로 더 싸고 덜 출렁이는 쪽으로 기울이는 <b>동점자 가르기</b> 랭킹.
&nbsp;생성 __GEN__</div>

<div class="kpis">
  <div class="kpi"><div class="lab">유니버스</div><div class="val">__N__<span style="font-size:13px;color:var(--sub)"> 종목</span></div></div>
  <div class="kpi"><div class="lab">진우 6종목 최상위</div><div class="val acc">#__J6BEST__</div></div>
  <div class="kpi"><div class="lab">6종목 포착</div><div class="val">__J6CNT__ / 6</div></div>
</div>

<div class="rule">
손절 = max(현재가 − 2.5×ATR14, 현재가×0.80) · 트레일 = (최고가 − 2.5×ATR14) 래칫 &nbsp;|&nbsp;
수량 = (자본×리스크%) ÷ 1R, 리스크 1% &nbsp;|&nbsp; <b>매도규칙서 v2</b>: 섹터당 2종 · 동시 5~7종 · 돌파는 리스크 0.5%<br>
⚠️ 이 툴은 절대 저평가 스크리너가 아니라 <b>진우님 후보 안에서의 상대 랭킹</b>. 발굴 ≠ 매수신호. 기울기는 조건부(2028 재판정).
</div>

<div class="j6box"><h2>★ 진우 6종목 위치</h2><div id="j6list"></div></div>

<div class="bar" id="bar">
  <button data-f="all" class="on">전체</button>
  <button data-f="j6">★ 6종목</button>
  <button data-f="섹터">섹터</button>
  <button data-f="특성">특성</button>
  <button data-f="섹터+특성">섹터+특성</button>
</div>

<table id="tbl"><thead><tr>
<th class="l" data-k="rank">순위</th>
<th class="l" data-k="name">종목</th>
<th data-k="score">점수</th>
<th data-k="pbr">PBR</th>
<th data-k="vol">변동%</th>
<th data-k="close">현재가</th>
<th data-k="stop">손절</th>
<th data-k="stop_pct">손절폭%</th>
<th data-k="qty">수량</th>
<th class="l" data-k="src">출처</th>
</tr></thead><tbody id="tb"></tbody></table>

<div class="foot">투자자문 아님 · 발굴 ≠ 매수신호 · 스톱은 타협 불가 · 결정·책임은 본인.<br>
기준: 진우사냥터_후보.csv (진우사냥터_스크리너.py 산출)</div>

<script>
const DATA=__DATA__, J6=__J6__;
let filt="all", sortK="rank", asc=true;
const won=n=>n.toLocaleString('ko-KR');
function j6render(){
  document.getElementById('j6list').innerHTML=J6.map(r=>
    `<div class="j6row"><span><span class="rk">#${r.rank}</span> <span class="nm">${r.name}</span>
     <span class="src">${r.code} · ${r.src}</span></span>
     <span>PBR ${r.pbr.toFixed(2)} · 변동 ${r.vol.toFixed(1)}% · 점수 ${r.score.toFixed(2)}</span></div>`).join('')
    || '<div class="sub">6종목이 유니버스에 없음</div>';
}
function rows(){
  let a=DATA.slice();
  if(filt==="j6")a=a.filter(r=>r.j6);
  else if(filt!=="all")a=a.filter(r=>r.src===filt);
  a.sort((x,y)=>{let v=(x[sortK]>y[sortK]?1:x[sortK]<y[sortK]?-1:0);return asc?v:-v});
  return a;
}
function draw(){
  document.getElementById('tb').innerHTML=rows().map(r=>
    `<tr class="${r.j6?'j6':''}">
     <td class="l">${r.j6?'<span class="star">★</span>':''}${r.rank}</td>
     <td class="l">${r.name}</td>
     <td>${r.score.toFixed(2)}</td>
     <td>${r.pbr.toFixed(2)} <span class="src">#${r.pbr_rank}</span></td>
     <td>${r.vol.toFixed(1)} <span class="src">#${r.vol_rank}</span></td>
     <td>${won(r.close)}</td>
     <td>${won(r.stop)}</td>
     <td>${r.stop_pct.toFixed(1)}</td>
     <td>${won(r.qty)}</td>
     <td class="l src">${r.src}</td></tr>`).join('');
}
document.getElementById('bar').addEventListener('click',e=>{
  const b=e.target.closest('button');if(!b)return;
  filt=b.dataset.f;[...document.querySelectorAll('#bar button')].forEach(x=>x.classList.toggle('on',x===b));draw();
});
document.querySelectorAll('#tbl th').forEach(th=>th.addEventListener('click',()=>{
  const k=th.dataset.k;if(sortK===k)asc=!asc;else{sortK=k;asc=(k==='rank');}draw();
}));
j6render();draw();
</script></div></body></html>"""


def _self_test():
    import tempfile
    ok = tot = 0

    def chk(nm, c):
        nonlocal ok, tot
        tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {nm}")

    tmp = tempfile.mkdtemp()
    cp = os.path.join(tmp, "t.csv")
    with open(cp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank", "code", "name", "sector", "src", "score", "pbr", "pbr_rank",
                    "vol60", "vol_rank", "close", "mcap", "adv20", "atr14",
                    "stop", "stop_pct", "qty", "n_univ", "is_jinwoo6"])
        w.writerow([1, "000001", "테스트가", "반도체", "섹터", 0.9, 1.5, 3,
                    0.05, 10, 10000, 1e12, 1e9, 800, 8000, 20.0, 50, 2, "False"])
        w.writerow([2, "450080", "에코프로머티", "이차전지", "섹터+특성", 0.6, 2.96, 222,
                    0.051, 103, 100000, 2.6e12, 1e10, 5000, 80000, 20.0, 12, 450, "True"])
    rows = read_rows(cp)
    chk("CSV 2행 파싱", len(rows) == 2)
    chk("is_jinwoo6 불린 파싱", rows[1]["j6"] is True and rows[0]["j6"] is False)
    chk("vol60 → 변동% 환산(0.051→5.1)", rows[1]["vol"] == 5.1)
    html = build_html(rows, {"gen": "test"})
    chk("HTML 골격 포함", "<html" in html and "진우 사냥터 현황판" in html)
    chk("데이터 JSON 주입", "에코프로머티" in html and "__DATA__" not in html)
    chk("6종목 최상위 KPI 치환", "__J6BEST__" not in html)
    chk("플레이스홀더 전부 치환", "__N__" not in html and "__J6__" not in html and "__GEN__" not in html)
    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot


def main():
    ap = argparse.ArgumentParser(description="jinwoo hunting-ground dashboard")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return 0 if _self_test() else 1
    if not os.path.exists(CSV_IN):
        print(f"  [없음] {os.path.basename(CSV_IN)} — 먼저 진우사냥터_스크리너.py 실행")
        return 2
    rows = read_rows(CSV_IN)
    gen = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    html = build_html(rows, {"gen": gen})
    with open(HTML_OUT, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"저장: 진우사냥터_현황판.html ({len(rows)}행, {len(html):,}바이트)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
