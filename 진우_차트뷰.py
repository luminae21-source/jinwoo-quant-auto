#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우_차트뷰.py — PC용 풀 인터랙티브 차트뷰 (캔들+곡선MA+거래량+드로잉+내 타점)

읽기: 진우_관심종목.csv + 일봉 → 자체완결 HTML(브라우저).
기능: 종목 선택 · 캔들 · MA20/60/200 곡선 · 거래량 · 크로스헤어 툴팁 ·
      지지/저항/진입/손절 가로선 그리기(브라우저 저장) · 내 제안 타점(진입관찰=MA20회복·손절·지지·저항).
정직: 발굴≠매수신호. 진입 타이밍은 엣지 아님(검증). 결정·책임 본인.
사용: py 진우_차트뷰.py [--days 180] [--self-test]   산출: 진우_차트뷰.html
"""
import os, sys, csv, json, argparse, io, datetime
BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "진우_차트뷰.html")
RECENT = 700000
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def _rr(pd, path, n, cols):
    with open(path, "rb") as f:
        h = f.readline(); f.seek(0, 2); pos = f.tell(); data = b""; nl = 0; blk = 1 << 20
        while pos > 0 and nl <= n:
            s = min(blk, pos); pos -= s; f.seek(pos); data = f.read(s)+data; nl = data.count(b"\n")
    lines = [l for l in data.split(b"\n") if l.strip()]
    return pd.read_csv(io.BytesIO(h+b"\n".join(lines[-n:])), usecols=cols, dtype={"code": str}, encoding="utf-8-sig")

def build_data(pd, codes_named, days):
    frames = []
    for mk in ("KOSPI", "KOSDAQ"):
        p = os.path.join(BASE, f"종목일봉_30년_{mk}.csv")
        if os.path.exists(p):
            d = _rr(pd, p, RECENT, ["date", "code", "open", "high", "low", "close", "volume"])
            d["code"] = d["code"].str.zfill(6); d = d[d["code"].isin(codes_named)]
            frames.append(d)
    d = pd.concat(frames, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    for c in ("open", "high", "low", "close", "volume"): d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["date", "close"]).sort_values(["code", "date"])
    out = {}
    for code, g in d.groupby("code"):
        if len(g) < 200: continue
        cl = g["close"]
        ma20 = cl.rolling(20).mean(); ma60 = cl.rolling(60).mean(); ma200 = cl.rolling(200).mean()
        pc = cl.shift(1)
        tr = pd.concat([g["high"]-g["low"], (g["high"]-pc).abs(), (g["low"]-pc).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14).mean().iloc[-1]
        N = days; gg = g.tail(N)
        bars = [[r.date.strftime("%y/%m/%d"), int(r.open), int(r.high), int(r.low), int(r.close), int(r.volume)]
                for r in gg.itertuples()]
        def arr(s): return [None if x != x else int(x) for x in s.tail(N)]
        px = int(cl.iloc[-1]); m200 = int(ma200.iloc[-1]); m20 = int(ma20.iloc[-1])
        out[code] = dict(name=codes_named[code], px=px,
                         bars=bars, ma20=arr(ma20), ma60=arr(ma60), ma200=arr(ma200),
                         lv={"지지 MA200": m200, "지지 저점": int(gg["low"].tail(60).min()),
                             "저항": int(gg["high"].max()), "진입관찰(MA20)": m20,
                             "손절": int(max(px-2.5*atr, px*0.80))})
    return out

def render(data):
    gen = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    return TEMPLATE.replace("__DATA__", json.dumps(data, ensure_ascii=False)).replace("__GEN__", gen)

TEMPLATE = r"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>진우 차트뷰</title>
<style>
:root{--bg:#0f1115;--panel:#12151c;--line:#242a35;--acc:#ff7a45;--txt:#e8eaed;--sub:#969ca6}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);
font-family:'Malgun Gothic',system-ui,sans-serif;font-size:14px}
.wrap{max-width:1180px;margin:0 auto;padding:16px 14px 50px}
h1{font-size:19px;margin:0 0 3px}.sub{color:var(--sub);font-size:12px;margin-bottom:12px}
.bar{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:8px}
select,.bar button{background:var(--panel);color:var(--txt);border:1px solid #2a3140;border-radius:8px;
padding:7px 11px;font-size:13px;cursor:pointer}
.bar button.on{color:#161616;font-weight:700}
.m지지.on{background:#3fb37a;border-color:#3fb37a}.m저항.on{background:#e2606a;border-color:#e2606a}
.m진입.on{background:#ff7a45;border-color:#ff7a45}.m손절.on{background:#c77dff;border-color:#c77dff}
.m지우기.on{background:#969ca6;border-color:#969ca6}
.bar .sep{flex:1}.tg{color:var(--sub)}.tg.on{color:var(--acc);font-weight:700}
.cvwrap{position:relative;width:100%;height:520px;background:#0d1016;border:1px solid #222836;border-radius:10px}
#cv{width:100%;height:100%;display:block;touch-action:none;cursor:crosshair}
.tip{position:absolute;pointer-events:none;background:#1b2130ee;border:1px solid #2a3140;border-radius:6px;
padding:6px 8px;font-size:11.5px;line-height:1.5;color:var(--txt);display:none;white-space:nowrap}
.legend{font-size:11.5px;color:var(--sub);margin-top:8px;line-height:1.8}
.dot{display:inline-block;width:9px;height:9px;border-radius:2px;margin:0 3px 0 10px;vertical-align:middle}
.foot{color:var(--sub);font-size:11px;margin-top:12px;line-height:1.6}
</style></head><body><div class="wrap">
<h1>진우 차트뷰 <span style="color:var(--acc)">· 캔들·MA·거래량 + 타점 드로잉</span></h1>
<div class="sub">생성 __GEN__ · 발굴≠매수신호 · 진입타이밍은 엣지 아님(검증) · 결정·책임 본인</div>
<div class="bar">
  <select id="sel"></select>
  <button class="m지지" data-m="지지">지지선</button>
  <button class="m저항" data-m="저항">저항선</button>
  <button class="m진입" data-m="진입">진입</button>
  <button class="m손절" data-m="손절">손절</button>
  <button class="m지우기" data-m="지우기">지우기</button>
  <button id="clr">내선 전체삭제</button>
  <span class="sep"></span>
  <button class="tg on" id="tgMine">내 타점 ●</button>
</div>
<button id="helpBtn" style="background:#171a21;color:#c8ccd4;border:1px solid #2a3140;border-radius:8px;padding:6px 11px;font-size:12px;cursor:pointer;margin:0 0 8px">? 도움말</button>
<div id="help" style="display:none;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin-bottom:10px;font-size:12.5px;line-height:1.7">
<b style="color:var(--acc)">차트 보는 법 · 타점 그리는 법</b><br>
<b>이동평균선</b>: <span style="color:#e0b020">MA20</span>(단기) · <span style="color:#5aa0f0">MA60</span>(중기) · <span style="color:#b06ad0">MA200</span>(장기 추세). 주가의 체온선.<br>
<b>점선 = 내 제안 타점</b>: <span style="color:#3fb37a">지지</span>(받쳐줄 구간) · <span style="color:#e2606a">저항</span>(부딪힐 벽·매도참고) · <span style="color:#ff7a45">진입관찰=MA20 회복선</span> · <span style="color:#c77dff">손절</span>.<br>
<b>핵심 신호</b>: 캔들이 <span style="color:#ff7a45">진입관찰선(주황=MA20)</span>을 <b>거래량 실려 위로 뚫으면</b> "반등확인" = 관찰→진입 전환점.<br>
<b>그리기</b>: 위 도구(지지/저항/진입/손절) 고르고 차트 클릭/터치 → 가로선. "지우기"로 내 선 제거. <b>내가 그은 선은 브라우저에 저장</b>(재방문 유지).<br>
<b>거래량 막대</b>(하단): 상승일 초록·하락일 빨강 · <b>크로스헤어</b>: 커서 올리면 그날 시고저종·거래량.<br>
<span style="color:var(--sub)">※ 발굴≠매수신호 · 진입타이밍은 엣지 아님(검증) · 소량·분산·손절 필수 · 결정 본인.</span>
</div>
<div class="cvwrap"><canvas id="cv"></canvas><div class="tip" id="tip"></div></div>
<div class="legend">
<span class="dot" style="background:#e0b020"></span>MA20
<span class="dot" style="background:#5aa0f0"></span>MA60
<span class="dot" style="background:#b06ad0"></span>MA200 ·
<span class="dot" style="background:#3fb37a"></span>지지
<span class="dot" style="background:#e2606a"></span>저항
<span class="dot" style="background:#ff7a45"></span>진입관찰(MA20회복=반등확인)
<span class="dot" style="background:#c77dff"></span>손절
<span id="mineTxt"></span></div>
<div class="foot">도구 선택 후 차트 클릭/터치 → 가로선. 내가 그은 선은 브라우저에 저장(재방문시 유지).
진입 원칙: 진입관찰선(주황)을 종가가 위로 뚫으면 반등확인 → 관찰→진입. 초고변동=사이징·분산 필수.</div>
</div>
<script>
const DATA=__DATA__;
const MCOL={"지지":"#3fb37a","저항":"#e2606a","진입":"#ff7a45","손절":"#c77dff"};
const LVCOL={"지지 MA200":"#3fb37a","지지 저점":"#3fb37a","저항":"#e2606a","진입관찰(MA20)":"#ff7a45","손절":"#c77dff"};
const codes=Object.keys(DATA);let cur=codes[0],mode=null,showMine=true;
const LSK="진우차트_userlines";
let userLines=JSON.parse(localStorage.getItem(LSK)||"{}");codes.forEach(c=>{if(!userLines[c])userLines[c]=[];});
const cv=document.getElementById('cv'),ctx=cv.getContext('2d'),tip=document.getElementById('tip');
const fmt=n=>Math.round(n).toLocaleString('ko-KR');
let W=1000,H=520,dpr=1;const padL=6,padR=74,padT=10,gap=8,volH=90;let priceB;
const sel=document.getElementById('sel');codes.forEach(c=>{const o=document.createElement('option');o.value=c;o.textContent=DATA[c].name;sel.appendChild(o);});
sel.onchange=()=>{cur=sel.value;draw();updMine();};
document.querySelectorAll('.bar button[data-m]').forEach(b=>b.onclick=()=>{mode=(mode===b.dataset.m?null:b.dataset.m);document.querySelectorAll('.bar button[data-m]').forEach(x=>x.classList.toggle('on',x.dataset.m===mode));});
document.getElementById('tgMine').onclick=function(){showMine=!showMine;this.classList.toggle('on',showMine);draw();};
document.getElementById('clr').onclick=()=>{userLines[cur]=[];save();draw();updMine();};
function save(){localStorage.setItem(LSK,JSON.stringify(userLines));}
function rng(d){let lo=1e12,hi=-1e12;d.bars.forEach(b=>{lo=Math.min(lo,b[3]);hi=Math.max(hi,b[2]);});
if(showMine)Object.values(d.lv).forEach(v=>{lo=Math.min(lo,v);hi=Math.max(hi,v);});
userLines[cur].forEach(l=>{lo=Math.min(lo,l.price);hi=Math.max(hi,l.price);});const p=(hi-lo)*0.05||1;return[lo-p,hi+p];}
function p2y(v,lo,hi){return padT+(hi-v)/(hi-lo)*(priceB-padT);}
function i2x(i,n){return padL+i/(n-1)*(W-padL-padR);}
function resize(){W=cv.clientWidth;H=cv.clientHeight;dpr=window.devicePixelRatio||1;cv.width=W*dpr;cv.height=H*dpr;ctx.setTransform(dpr,0,0,dpr,0,0);priceB=H-volH-gap;draw();}
function maCurve(a,lo,hi,n,col){ctx.strokeStyle=col;ctx.lineWidth=1.3;ctx.beginPath();let st=false;a.forEach((v,i)=>{if(v==null)return;const x=i2x(i,n),y=p2y(v,lo,hi);if(!st){ctx.moveTo(x,y);st=true;}else ctx.lineTo(x,y);});ctx.stroke();}
function hline(price,col,label,lo,hi,dash){const y=p2y(price,lo,hi);if(y<padT-2||y>priceB+2)return;ctx.save();ctx.strokeStyle=col;ctx.lineWidth=1;if(dash)ctx.setLineDash([5,4]);ctx.beginPath();ctx.moveTo(padL,y);ctx.lineTo(W-padR,y);ctx.stroke();ctx.setLineDash([]);ctx.fillStyle=col;ctx.font='10px sans-serif';ctx.textBaseline='middle';ctx.fillText(label,W-padR+3,y);ctx.restore();}
function draw(){const d=DATA[cur],n=d.bars.length,[lo,hi]=rng(d);ctx.clearRect(0,0,W,H);
for(let g=0;g<=4;g++){const y=padT+g/4*(priceB-padT);ctx.strokeStyle='#1a1f28';ctx.beginPath();ctx.moveTo(padL,y);ctx.lineTo(W-padR,y);ctx.stroke();ctx.fillStyle='#5a626e';ctx.font='9px sans-serif';ctx.textBaseline='middle';ctx.fillText(fmt(hi-g/4*(hi-lo)),W-padR+3,y);}
const cw=Math.max(1.2,(W-padL-padR)/n*0.64);
d.bars.forEach((b,i)=>{const x=i2x(i,n),o=p2y(b[1],lo,hi),h=p2y(b[2],lo,hi),l=p2y(b[3],lo,hi),c=p2y(b[4],lo,hi),up=b[4]>=b[1];ctx.strokeStyle=ctx.fillStyle=up?'#3fb37a':'#e2606a';ctx.lineWidth=1;ctx.beginPath();ctx.moveTo(x,h);ctx.lineTo(x,l);ctx.stroke();ctx.fillRect(x-cw/2,Math.min(o,c),cw,Math.max(1,Math.abs(o-c)));});
maCurve(d.ma20,lo,hi,n,'#e0b020');maCurve(d.ma60,lo,hi,n,'#5aa0f0');maCurve(d.ma200,lo,hi,n,'#b06ad0');
if(showMine)Object.entries(d.lv).forEach(([k,v])=>hline(v,LVCOL[k],k+' '+fmt(v),lo,hi,true));
userLines[cur].forEach(l=>hline(l.price,MCOL[l.type],'●'+l.type+' '+fmt(l.price),lo,hi,false));
// 거래량 pane
const vy0=priceB+gap,vmax=Math.max(...d.bars.map(b=>b[5]))||1;
ctx.fillStyle='#5a626e';ctx.font='9px sans-serif';ctx.fillText('거래량',padL+2,vy0+8);
d.bars.forEach((b,i)=>{const x=i2x(i,n),bh=b[5]/vmax*(volH-14),up=b[4]>=b[1];ctx.fillStyle=up?'#2f6f52':'#7a3a41';ctx.fillRect(x-cw/2,H-bh,cw,bh);});
}
function nearest(x){const d=DATA[cur],n=d.bars.length;let i=Math.round((x-padL)/(W-padL-padR)*(n-1));return Math.max(0,Math.min(n-1,i));}
cv.addEventListener('mousemove',e=>{const r=cv.getBoundingClientRect(),mx=e.clientX-r.left,my=e.clientY-r.top;const d=DATA[cur],n=d.bars.length,[lo,hi]=rng(d);draw();
const i=nearest(mx),x=i2x(i,n),b=d.bars[i];ctx.strokeStyle='#3a4252';ctx.setLineDash([2,3]);ctx.beginPath();ctx.moveTo(x,padT);ctx.lineTo(x,priceB);ctx.moveTo(padL,my);ctx.lineTo(W-padR,my);ctx.stroke();ctx.setLineDash([]);
const pr=Math.round(hi-(my-padT)/(priceB-padT)*(hi-lo));
tip.style.display='block';tip.style.left=Math.min(mx+12,W-150)+'px';tip.style.top=Math.max(my-10,4)+'px';
tip.innerHTML=`<b>${b[0]}</b><br>시 ${fmt(b[1])} 고 ${fmt(b[2])}<br>저 ${fmt(b[3])} 종 ${fmt(b[4])}<br>거래량 ${fmt(b[5])}<br><span style="color:#ff7a45">커서 ${fmt(pr)}</span>`;});
cv.addEventListener('mouseleave',()=>{tip.style.display='none';draw();});
function place(cy){const d=DATA[cur],[lo,hi]=rng(d);const price=Math.round(hi-(cy-padT)/(priceB-padT)*(hi-lo));
if(mode==='지우기'){let bi=-1,bd=1e9;userLines[cur].forEach((l,i)=>{const dd=Math.abs(p2y(l.price,lo,hi)-cy);if(dd<bd){bd=dd;bi=i;}});if(bi>=0&&bd<14)userLines[cur].splice(bi,1);}
else if(mode){userLines[cur].push({type:mode,price});}save();draw();updMine();}
cv.addEventListener('click',e=>{if(!mode)return;const r=cv.getBoundingClientRect(),cy=e.clientY-r.top;if(cy<=priceB)place(cy);});
cv.addEventListener('touchstart',e=>{if(!mode)return;e.preventDefault();const r=cv.getBoundingClientRect(),cy=e.touches[0].clientY-r.top;if(cy<=priceB)place(cy);},{passive:false});
function updMine(){const u=userLines[cur];document.getElementById('mineTxt').innerHTML=u.length?(' &nbsp;|&nbsp; 내 선: '+u.map(l=>`<span class="dot" style="background:${MCOL[l.type]}"></span>${l.type} ${fmt(l.price)}`).join('')):'';}
window.addEventListener('resize',resize);
document.getElementById('helpBtn').addEventListener('click',function(){var h=document.getElementById('help');h.style.display=h.style.display==='none'?'block':'none';});
updMine();requestAnimationFrame(resize);
</script></body></html>"""

def _self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    d = {"001": dict(name="X", px=1000, bars=[["25/01/01", 1, 2, 1, 2, 100]],
                     ma20=[None], ma60=[None], ma200=[None],
                     lv={"지지 MA200": 900, "저항": 1200, "진입관찰(MA20)": 1050, "손절": 800, "지지 저점": 850})}
    html = render(d)
    chk("HTML 골격", "<html" in html and "canvas" in html)
    chk("데이터 주입", "__DATA__" not in html and '"name": "X"' in html)
    chk("localStorage 저장 로직", "localStorage" in html)
    chk("MA/거래량 요소", "거래량" in html and "maCurve" in html)
    chk("드로잉 도구", "지지선" in html and "지우기" in html)
    print(f"\n셀프테스트: {ok}/{tot}"); return ok == tot

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--days", type=int, default=180); ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    import pandas as pd
    named = {}
    ip = os.path.join(BASE, "진우_관심종목.csv")
    if os.path.exists(ip):
        with open(ip, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f): named[r["code"].zfill(6)] = r.get("name", "")
    if not named:
        print("관심종목 없음"); return 2
    data = build_data(pd, named, a.days)
    html = render(data)
    with open(OUT, "w", encoding="utf-8") as f: f.write(html)
    print(f"저장: 진우_차트뷰.html ({len(data)}종목 · {a.days}일 · {len(html):,}바이트)")
    return 0

if __name__ == "__main__":
    sys.exit(main())
