#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우_타점발굴_표.py — 진우_타점발굴.csv → 색상·필터·정렬 HTML 표

읽기: 진우_타점발굴.csv → 자체완결 HTML(브라우저). 접근유형별 색상, 필터, 컬럼 정렬, 검색.
사용: py 진우_타점발굴_표.py [--self-test]   산출: 진우_타점발굴_표.html
정직: 발굴≠매수신호 · 결정·책임 본인.
"""
import os, sys, csv, json, argparse, datetime
BASE = os.path.dirname(os.path.abspath(__file__))
IN = os.path.join(BASE, "진우_타점발굴.csv")
OUT = os.path.join(BASE, "진우_타점발굴_표.html")
OUT_CHART = os.path.join(BASE, "진우_타점발굴_표_차트.html")
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def read_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        def num(k):
            try: return float(r.get(k) or 0)
            except ValueError: return 0
        out.append(dict(star=r.get("star", ""), code=r.get("code", ""), name=r.get("name", ""),
                        ap=r.get("ap", ""), order=r.get("order", ""), pbr=num("pbr"), deep=int(num("deep")), bounce=int(num("bounce")),
                        imae=int(num("imae")), fmae=int(num("fmae")),
                        ext=num("ext"),
                        r20=num("r20"), c=int(num("c")), buy=int(num("buy")), stop=int(num("stop")),
                        resist=int(num("resist")), vflag=r.get("vflag", ""), tag=r.get("tag", "")))
    return out

def build_chart_data(codes, days=90):
    import pandas as pd, io
    RECENT = 380000
    def rr(path, n, cols):
        with open(path, "rb") as f:
            h = f.readline(); f.seek(0, 2); pos = f.tell(); data = b""; nl = 0; blk = 1 << 20
            while pos > 0 and nl <= n:
                st = min(blk, pos); pos -= st; f.seek(pos); data = f.read(st)+data; nl = data.count(b"\n")
        lines = [l for l in data.split(b"\n") if l.strip()]
        return pd.read_csv(io.BytesIO(h+b"\n".join(lines[-n:])), usecols=cols, dtype={"code": str}, encoding="utf-8-sig")
    cs = set(codes); frames = []
    for mk in ("KOSPI", "KOSDAQ"):
        fp = os.path.join(BASE, f"종목일봉_30년_{mk}.csv")
        if os.path.exists(fp):
            d = rr(fp, RECENT, ["date", "code", "open", "high", "low", "close", "volume"])
            d["code"] = d["code"].str.zfill(6); d = d[d["code"].isin(cs)]; frames.append(d)
    if not frames: return {}
    d = pd.concat(frames, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    for c in ("open", "high", "low", "close", "volume"): d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["date", "close"]).sort_values(["code", "date"])
    out = {}
    for code, g in d.groupby("code"):
        cl = g["close"]
        if len(cl) < 60: continue
        ma20 = cl.rolling(20).mean(); ma60 = cl.rolling(60).mean(); ma200 = cl.rolling(200).mean()
        gg = g.tail(days)
        bars = [[r.date.strftime("%m/%d"), int(r.open), int(r.high), int(r.low), int(r.close), int(r.volume)] for r in gg.itertuples()]
        arr = lambda sr: [None if x != x else int(x) for x in sr.tail(days)]
        out[code] = dict(bars=bars, ma20=arr(ma20), ma60=arr(ma60), ma200=arr(ma200))
    return out


def build(rows, chart=None):
    gen = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    return (TEMPLATE.replace("__DATA__", json.dumps(rows, ensure_ascii=False))
            .replace("__CHART__", json.dumps(chart or {}, ensure_ascii=False))
            .replace("__HASCHART__", "true" if chart else "false")
            .replace("__GEN__", gen).replace("__N__", str(len(rows))))

TEMPLATE = r"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>진우 타점발굴 표</title>
<style>
:root{--bg:#0f1115;--panel:#171a21;--line:#242a35;--acc:#ff7a45;--txt:#e8eaed;--sub:#969ca6}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--txt);
font-family:'Malgun Gothic',system-ui,sans-serif;font-size:13px}
.wrap{max-width:1180px;margin:0 auto;padding:16px 14px 60px}
h1{font-size:19px;margin:0 0 3px}.sub{color:var(--sub);font-size:12px;margin-bottom:12px}
.bar{display:flex;gap:6px;flex-wrap:wrap;align-items:center;margin-bottom:10px}
.bar button{background:var(--panel);color:#c8ccd4;border:1px solid #2a3140;border-radius:16px;padding:6px 13px;font-size:12.5px;cursor:pointer}
.bar button.on{background:var(--acc);border-color:var(--acc);color:#161616;font-weight:700}
.bar input{background:var(--panel);color:var(--txt);border:1px solid #2a3140;border-radius:8px;padding:6px 10px;font-size:12.5px}
.bar .sp{flex:1}.cnt{color:var(--sub);font-size:12px}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th,td{padding:6px 8px;text-align:right;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--sub);cursor:pointer;position:sticky;top:0;background:var(--bg);user-select:none;font-weight:600}
th.l,td.l{text-align:left}
.ap{font-size:11px;padding:2px 8px;border-radius:10px;font-weight:700}
tr:hover td{background:#161a22}
.tag{color:var(--sub);font-size:11px}
.foot{color:var(--sub);font-size:11px;margin-top:14px;line-height:1.6}
.hint{color:var(--sub);font-size:11.5px;margin:2px 0 6px}
th.hh{text-decoration:underline dotted #3a4252;text-underline-offset:3px}
.tip{position:fixed;z-index:999;max-width:320px;background:#1b2130;border:1px solid #3a4252;border-radius:7px;padding:8px 11px;font-size:12px;line-height:1.55;color:#e8eaed;display:none;pointer-events:none;box-shadow:0 4px 16px #000a}
.deeprow td{background:#1a2418}.deeprow:hover td{background:#20301c}
</style></head><body><div class="wrap">
<h1>진우 타점발굴 표 <span style="color:var(--acc)">· 종목별 매수/매도 접근</span></h1>
<div class="sub">생성 __GEN__ · 총 __N__종 · ★관심 ✦신규 · 발굴≠매수신호 · 결정·책임 본인</div>
<div class="bar" id="fbar">
  <button data-f="all" class="on" data-tip="모든 종목">전체</button>
  <button data-f="추세매수" data-tip="MA20 위 유지 → 지금 흐름 살아있음·상대적 강세. 눌림(20일선 근처)에 매수, 손절 2.5×ATR.">🟢 추세매수</button>
  <button data-f="반등관찰" data-tip="MA20 아래 → 눌림/급락, 반등 미확인. 20일선을 거래량 실려 상향 돌파할 때까지 관찰 후 진입(떨어지는 칼날 X).">🟡 반등관찰</button>
  <button data-f="과열보류" data-tip="이격도>1.35(200일선 +35% 이상) → 과열. 신규진입 보류, 20/60일선 눌림 대기.">🔴 과열보류</button>
  <button data-f="하락회피" data-tip="역배열(단기<중기<장기선) 또는 200일선 한참 아래 하락 → 밸류트랩. 진입 금지·회피.">⚫ 하락회피</button>
  <button data-f="★" data-tip="관심종목에 이미 등록된 종목">★관심</button>
  <button data-f="✦" data-tip="관심 밖에서 새로 발굴된 후보">✦신규</button>
  <button data-f="deep" data-tip="딥밸류바닥(검증 주력·전 시장): 저PBR(하위20%)+과매도(이격<0.85)+턴(20일수익>0). 30년·상폐반영 = 강세장 12M +17.8%·하락장 +12.9% 시장초과. 하락장은 3~6M 빠른반등, 강세장은 6~12M. 분산·손절·자동매수 아님.">◆딥밸류바닥</button>
  <button data-f="bounce" data-tip="바닥반등(밸류無·약한 보조엣지): 과매도(이격<0.85)+턴(20일수익>0), PBR 무관. 강세 +6%·하락 +8.8% 시장초과(딥밸류보다 약함). 딥밸류 빈 구간에 넓게 볼 때. 절대저점(지지반등)은 밸류트랩=금지.">△바닥반등</button>
  <button data-f="imae" data-tip="기관 순매수(중립 참고·필터 아님·긍정신호 아님): 최신월 기관 순매수>0. ★결정적 검증(수급오버레이_검증.md): 원래 top-550(대형주) 소표본에선 딥+기관 12M +34%로 좋아 보였으나, 전체 유니버스(3,865종)+일봉정밀로 엄밀검증하니 딥+기관이 딥단독보다 오히려 -3%p 낮음(IN·OOS 양쪽). +34%는 소표본 착시였음. 외국인·둘다도 우위 없음. → 초과수익과 무관한 중립 정보로만 표시.">기관순매수(중립)</button>
  <button id="helpBtn" data-tip="접근유형 설명 열기/닫기">? 도움말</button>
  <span class="sp"></span>
  <input id="q" placeholder="종목명 검색">
  <span class="cnt" id="cnt"></span>
</div>
<div id="help" style="display:none;background:var(--panel);border:1px solid var(--line);border-radius:10px;padding:14px 16px;margin-bottom:12px;font-size:12.5px;line-height:1.7">
<b style="color:var(--acc)">접근유형 (종목 상태별 접근)</b> —
<span style="color:#3fb37a;font-weight:700">🟢추세매수</span> MA20 위·눌림에 매수 ·
<span style="color:#e0b020;font-weight:700">🟡반등관찰</span> MA20 아래·거래량 돌파 확인 후 ·
<span style="color:#e2606a;font-weight:700">🔴과열보류</span> 이격도>1.35·대기 ·
<span style="color:#969ca6;font-weight:700">⚫하락회피</span> 역배열·회피.<br><br>
<div style="background:#1a2418;border:1px solid #2f4a2a;border-radius:8px;padding:10px 12px;margin-bottom:10px">
<b style="color:#ffca3a">◆ 딥밸류바닥 (검증 주력 · 전 시장)</b> — 저PBR(하위20%) + 과매도(이격<0.85) + 턴(20일수익>0).
<b>30년·상폐반영 검증(전 시장)</b>: 강세장 12M <b>+17.8%</b>·하락장 <b>+12.9%</b> 시장 초과. 하락장 전용이 아님 — 다만 <b>하락장은 3~6M 빠른 반등, 강세장은 6~12M</b>에 실현.
왜 견고 — '턴'이 죽는 종목이 아니라 <b>돌아서는 종목</b>을 걸러 밸류트랩 회피.<br>
<span style="color:#9fb89a">승률 절반+우측 대박꼬리형 → <b>10~15종 분산 + 손절 + 장기(2~3년)보유</b>. 자동매수 아님 · <b>단기(≤3M) 스윙 엣지 없음</b>. 지금 후보 적으면 강세장이라 정상.</span><br>
<b style="color:#8ab0cf">△ 바닥반등 (밸류無·약한 보조)</b> — 과매도+턴만(PBR 무관). 강세 +6%·하락 +8.8% 초과(딥밸류보다 약함). <b>딥밸류 빈 구간에 넓게 볼 때만.</b> 절대저점(지지반등) 매수는 밸류트랩=금지.
</div>
<b style="color:var(--acc)">컬럼 활용</b>
<table style="width:100%;border-collapse:collapse;margin-top:6px;font-size:12px">
<tr><td style="padding:3px 8px;color:#e0b020;white-space:nowrap"><b>배열</b></td><td style="padding:3px 8px;border-bottom:1px solid #242a35">정배열=추세 건강(반등 신뢰↑) · 역배열=하락 · 혼조</td></tr>
<tr><td style="padding:3px 8px;color:#e0b020"><b>이격도</b></td><td style="padding:3px 8px;border-bottom:1px solid #242a35">현재가/MA200. 1.0적정·1.35↑과열·0.82↓과매도. 낮을수록 부담↓</td></tr>
<tr><td style="padding:3px 8px;color:#e0b020"><b>20일%</b></td><td style="padding:3px 8px;border-bottom:1px solid #242a35">한 달 등락. 반등관찰 중 덜 빠진 게 반등 앞선 후보</td></tr>
<tr><td style="padding:3px 8px;color:#e0b020"><b>매수타점</b></td><td style="padding:3px 8px;border-bottom:1px solid #242a35">=MA20. 추세매수=여기 눌림 매수 / 반등관찰=여기 거래량 돌파시 진입</td></tr>
<tr><td style="padding:3px 8px;color:#e0b020"><b>손절</b></td><td style="padding:3px 8px;border-bottom:1px solid #242a35">깨지면 매도. <b>매수타점−손절 = 1R</b>(리스크). 자본1%÷1R=수량</td></tr>
<tr><td style="padding:3px 8px;color:#e0b020"><b>저항</b></td><td style="padding:3px 8px;border-bottom:1px solid #242a35">60일 고점. <b>저항−매수타점 = 잠재수익폭</b>(매도 참고)</td></tr>
<tr><td style="padding:3px 8px;color:#e0b020"><b>거래량</b></td><td style="padding:3px 8px;border-bottom:1px solid #242a35">소진=바닥 조짐👍 · 증가⚠=추가하락 경계</td></tr>
<tr><td style="padding:3px 8px;color:#e0b020"><b>태그</b></td><td style="padding:3px 8px">테마=테마 모멘텀 · 사냥터=저PBR 발굴 · 관심</td></tr>
</table>
<br><b style="color:var(--acc)">★ 실전 조합</b><br>
1. <b>손익비 R:R</b> = (저항−매수타점) ÷ (매수타점−손절). <b>2:1 이상 우선</b>. (예 월덱스 ≈ 1.4:1)<br>
2. <b>반등 임박</b>(반등관찰 그룹): 정배열 + 20일% 덜빠짐 + 거래량 소진, 셋 겹치면 1순위.<br>
3. <b>진입 트리거</b>: 차트뷰에서 캔들이 매수타점(MA20)을 <b>거래량 실려 상향 돌파</b>하면 진입.<br><br>
<b>언제 매수? 한 줄</b>: 🟢추세매수는 <b>매수타점(MA20)까지 눌릴 때</b> · 🟡반등관찰은 <b>캔들이 매수타점을 거래량 실려 뚫을 때</b>.<br>
<span style="color:var(--sub)">※ 발굴≠매수신호 · 소량·분산·손절 필수 · 결정·책임 본인.</span>
</div>
<div class="hint">🛈 컬럼 제목에 <b>마우스 올리면</b> 설명 · <b>클릭하면</b> 정렬 · <span id="clickHint"></span></div>
<table id="t"><thead><tr>
<th class="l hh" data-k="star" data-tip="★=관심종목 등록 / ✦=관심 밖에서 새로 발굴된 후보">표시</th>
<th class="l hh" data-k="name" data-tip="종목명·코드">종목</th>
<th class="l hh" data-k="ap" data-tip="종목 상태별 접근법. 추세매수=눌림매수 / 반등관찰=돌파확인후 / 과열보류=대기 / 하락회피=회피">접근유형</th>
<th class="l hh" data-k="order" data-tip="이평선 순서. 정배열(20>60>200)=상승추세 건강→반등 신뢰↑ / 역배열=하락 / 혼조=뒤섞임">배열</th>
<th class="hh" data-k="pbr" data-tip="주가순자산배율(PBR). 낮을수록 자산 대비 싸다. 1.0 미만=순자산보다 싸게 거래. ◆딥밸류바닥 신호의 핵심 재료(하위20%).">PBR</th>
<th class="hh" data-k="ext" data-tip="현재가÷MA200. 1.0=적정 · 1.35↑=과열(비쌈·보류) · 0.82↓=과매도. 낮을수록 진입부담↓">이격도</th>
<th class="hh" data-k="r20" data-tip="최근 한 달(20일) 등락. 반등관찰 중 덜 빠진(작은 −)게 반등 앞선 후보. +면 이미 돌아섬">20일%</th>
<th class="hh" data-k="c" data-tip="지금 가격. 매수타점·손절·저항과 비교하는 기준점">현재가</th>
<th class="hh" data-k="buy" data-tip="★핵심=MA20. 추세매수는 여기(20일선)까지 눌릴 때 매수 / 반등관찰은 캔들이 여기를 거래량 실려 뚫을 때 진입">매수타점</th>
<th class="hh" data-k="stop" data-tip="진입 후 여기 깨지면 매도. 매수타점−손절=1R(감수 리스크). 자본 1%÷1R=수량">손절</th>
<th class="hh" data-k="resist" data-tip="최근 60일 고점(반등 시 벽·익절 참고). 저항−매수타점=잠재 수익폭">저항</th>
<th class="l hh" data-k="vflag" data-tip="5일 vs 20일 거래량. 소진=매도 줄어듦(바닥 조짐 👍) / 증가⚠=하락에 매도 붙음(추가하락 경계)">거래량</th>
<th class="l hh" data-k="imae" data-tip="수급 중립참고(최신월 순매수>0·필터 아님·긍정신호 아님). 기관=기관 순매수 · 외국=외국인 순매수. 결정적 검증: 전체유니버스+일봉정밀에서 딥+기관은 딥단독 대비 초과수익 없음(약간 -). 원래 +34%는 대형주 소표본 착시.">수급(중립)</th>
<th class="l hh" data-k="tag" data-tip="출처. 테마=7대 테마 소속(테마 모멘텀 얹힘) / 사냥터=저PBR 발굴 / 관심">태그</th>
</tr></thead><tbody id="tb"></tbody></table>
<div class="foot">접근유형: 추세매수(MA20 위·눌림매수) · 반등관찰(MA20 아래·돌파확인 후) · 과열보류(이격도>1.35·대기) · 하락회피(역배열·밸류트랩).<br>
매수타점=MA20 · 손절=반등관찰은 20일저 하회/그외 2.5ATR · 저항=60일고(매도참고). 발굴≠매수신호 · 소량·분산·손절 필수 · 결정·책임 본인.</div>
<div id="modal" style="display:none;position:fixed;inset:0;background:#000c;z-index:1000;align-items:center;justify-content:center;padding:12px">
  <div style="background:#12151c;border:1px solid #2a3140;border-radius:12px;padding:14px;max-width:840px;width:96%">
    <div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:6px">
      <span id="mTitle" style="font-weight:700;font-size:15px"></span>
      <button id="mClose" style="background:#171a21;color:#c8ccd4;border:1px solid #2a3140;border-radius:8px;padding:5px 12px;cursor:pointer">✕ 닫기</button>
    </div>
    <div id="mLevels" style="font-size:12px;color:#969ca6;margin-bottom:6px"></div>
    <canvas id="mCv" style="width:100%;height:400px;background:#0d1016;border:1px solid #222836;border-radius:8px;display:block"></canvas>
    <div style="font-size:11px;color:#5a626e;margin-top:6px">MA20(노랑)·MA60(파랑)·MA200(보라) · 점선: 주황=매수타점·보라=손절·빨강=저항 · 발굴≠매수신호·결정 본인</div>
  </div>
</div>

</div>
<script>
const DATA=__DATA__;
const CHART=__CHART__;
const HASCHART=__HASCHART__;
const APC={"추세매수":"#3fb37a","반등관찰":"#e0b020","과열보류":"#e2606a","하락회피":"#969ca6"};
const APORD={"추세매수":0,"반등관찰":1,"과열보류":2,"하락회피":3};
let filt="all",q="",sortK="ap",asc=true;
const won=n=>n?n.toLocaleString('ko-KR'):'-';
function rows(){
  let a=DATA.slice();
  if(filt==="★")a=a.filter(r=>r.star==="★");
  else if(filt==="✦")a=a.filter(r=>r.star==="✦");
  else if(filt==="deep")a=a.filter(r=>r.deep===1);
  else if(filt==="bounce")a=a.filter(r=>r.bounce===1&&r.deep!==1);
  else if(filt==="imae")a=a.filter(r=>r.imae===1);
  else if(filt!=="all")a=a.filter(r=>r.ap===filt);
  if(q)a=a.filter(r=>r.name.includes(q));
  a.sort((x,y)=>{let v;
    if(sortK==="ap"){v=(APORD[x.ap]-APORD[y.ap])||(x.ext-y.ext);}
    else v=(x[sortK]>y[sortK]?1:x[sortK]<y[sortK]?-1:0);
    return asc?v:-v});
  return a;
}
function draw(){
  const a=rows();
  document.getElementById('cnt').textContent=a.length+'종';
  document.getElementById('tb').innerHTML=a.map(r=>{
    const col=APC[r.ap]||'#5a626e';
    const rc=r.r20>0?'#3fb37a':(r.r20<0?'#e2606a':'#c8ccd4');
    const buy=r.ap==='하락회피'?'<span style="color:#969ca6">회피</span>':won(r.buy);
    return `<tr class="${r.deep?'deeprow':''}" ${HASCHART?`data-code="${r.code}" style="cursor:pointer" title="클릭 → 차트 팝업"`:``}>
    <td class="l">${r.deep?'<span title="딥밸류바닥(검증 주력)" style="color:#ffca3a">◆</span>':(r.bounce?'<span title="바닥반등(약한 보조엣지)" style="color:#7aa0c0">△</span>':'')}${r.star}</td>
    <td class="l"><b>${r.name}</b> <span class="tag">${r.code}</span></td>
    <td class="l"><span class="ap" style="background:${col}22;color:${col};border:1px solid ${col}55">${r.ap}</span></td>
    <td class="l">${r.order}</td>
    <td style="color:${r.pbr>0&&r.pbr<1?'#3fb37a':'#c8ccd4'}">${r.pbr>0?r.pbr.toFixed(2):'-'}</td>
    <td>${r.ext.toFixed(2)}</td>
    <td style="color:${rc}">${r.r20>0?'+':''}${r.r20.toFixed(0)}</td>
    <td>${won(r.c)}</td>
    <td style="color:#ff7a45">${buy}</td>
    <td style="color:#c77dff">${won(r.stop)}</td>
    <td>${won(r.resist)}</td>
    <td class="l tag">${r.vflag}</td>
    <td class="l">${r.imae?'<span title="기관 순매수(중립·검증상 초과수익 없음)" style="color:#c9b06a">기관</span>':''}${r.fmae?' <span title="외국인 순매수(중립·우위 없음)" style="color:#7f8a99">외국</span>':''}</td>
    <td class="l tag">${r.tag}</td></tr>`;}).join('');
}
document.getElementById('fbar').addEventListener('click',e=>{const b=e.target.closest('button');if(!b)return;filt=b.dataset.f;[...document.querySelectorAll('#fbar button')].forEach(x=>x.classList.toggle('on',x===b));draw();});
document.getElementById('q').addEventListener('input',e=>{q=e.target.value.trim();draw();});
document.querySelectorAll('#t th').forEach(th=>th.addEventListener('click',()=>{const k=th.dataset.k;if(sortK===k)asc=!asc;else{sortK=k;asc=(k==='ap'||k==='name');}draw();}));
document.getElementById('helpBtn').addEventListener('click',function(){const h=document.getElementById('help');h.style.display=h.style.display==='none'?'block':'none';this.classList.toggle('on');});
var __tip=document.createElement('div');__tip.className='tip';document.body.appendChild(__tip);
document.addEventListener('mouseover',function(e){var t=e.target.closest('[data-tip]');if(t){__tip.textContent=t.getAttribute('data-tip');__tip.style.display='block';}});
document.addEventListener('mousemove',function(e){if(__tip.style.display==='block'){__tip.style.left=Math.min(e.clientX+14,window.innerWidth-330)+'px';__tip.style.top=Math.min(e.clientY+16,window.innerHeight-90)+'px';}});
document.addEventListener('mouseout',function(e){var t=e.target.closest('[data-tip]');if(t)__tip.style.display='none';});
draw();


function drawChart(code){
  var row=DATA.find(function(r){return r.code===code;}); if(!row)return;
  var d=CHART[code];
  document.getElementById('mTitle').textContent=row.name+' ('+code+') · '+row.ap;
  if(!d){document.getElementById('mLevels').textContent='이 버전엔 차트가 없습니다. 차트 팝업은 진우_타점발굴_표_차트.html 을 여세요.';document.getElementById('modal').style.display='flex';return;}
  document.getElementById('mLevels').innerHTML='매수타점 <b style="color:#ff7a45">'+won(row.buy)+'</b> · 손절 <b style="color:#c77dff">'+won(row.stop)+'</b> · 저항 <b style="color:#e2606a">'+won(row.resist)+'</b> · 이격도 '+row.ext.toFixed(2)+' · '+row.order;
  document.getElementById('modal').style.display='flex';
  var cv=document.getElementById('mCv');var W=cv.clientWidth,H=cv.clientHeight,dp=window.devicePixelRatio||1;
  cv.width=W*dp;cv.height=H*dp;var cx=cv.getContext('2d');cx.setTransform(dp,0,0,dp,0,0);
  var pL=6,pR=74,pT=10,gp=6,vH=58,pB=H-vH-gp,n=d.bars.length;
  var lo=1e12,hi=-1e12;d.bars.forEach(function(b){lo=Math.min(lo,b[3]);hi=Math.max(hi,b[2]);});
  [row.buy,row.stop,row.resist].forEach(function(v){if(v){lo=Math.min(lo,v);hi=Math.max(hi,v);}});
  var pad=(hi-lo)*0.05||1;lo-=pad;hi+=pad;
  function py(v){return pT+(hi-v)/(hi-lo)*(pB-pT);}function ix(i){return pL+i/(n-1)*(W-pL-pR);}
  cx.clearRect(0,0,W,H);
  for(var g=0;g<=4;g++){var y=pT+g/4*(pB-pT);cx.strokeStyle='#1a1f28';cx.beginPath();cx.moveTo(pL,y);cx.lineTo(W-pR,y);cx.stroke();cx.fillStyle='#5a626e';cx.font='9px sans-serif';cx.textBaseline='middle';cx.fillText(won(Math.round(hi-g/4*(hi-lo))),W-pR+3,y);}
  var cw=Math.max(1.2,(W-pL-pR)/n*0.64);
  d.bars.forEach(function(b,i){var x=ix(i),o=py(b[1]),h=py(b[2]),l=py(b[3]),c=py(b[4]),up=b[4]>=b[1];cx.strokeStyle=cx.fillStyle=up?'#3fb37a':'#e2606a';cx.lineWidth=1;cx.beginPath();cx.moveTo(x,h);cx.lineTo(x,l);cx.stroke();cx.fillRect(x-cw/2,Math.min(o,c),cw,Math.max(1,Math.abs(o-c)));});
  function mc(a,col){cx.strokeStyle=col;cx.lineWidth=1.3;cx.beginPath();var st=false;a.forEach(function(v,i){if(v==null)return;var x=ix(i),y=py(v);if(!st){cx.moveTo(x,y);st=true;}else cx.lineTo(x,y);});cx.stroke();}
  mc(d.ma20,'#e0b020');mc(d.ma60,'#5aa0f0');mc(d.ma200,'#b06ad0');
  function hl(v,col,lb){if(!v)return;var y=py(v);if(y<pT||y>pB)return;cx.save();cx.strokeStyle=col;cx.setLineDash([5,4]);cx.beginPath();cx.moveTo(pL,y);cx.lineTo(W-pR,y);cx.stroke();cx.setLineDash([]);cx.fillStyle=col;cx.font='10px sans-serif';cx.textBaseline='middle';cx.fillText(lb,W-pR+3,y);cx.restore();}
  hl(row.buy,'#ff7a45','매수 '+won(row.buy));hl(row.stop,'#c77dff','손절 '+won(row.stop));hl(row.resist,'#e2606a','저항 '+won(row.resist));
  var vm=1;d.bars.forEach(function(b){if(b[5]>vm)vm=b[5];});
  d.bars.forEach(function(b,i){var x=ix(i),bh=b[5]/vm*(vH-10),up=b[4]>=b[1];cx.fillStyle=up?'#2f6f52':'#7a3a41';cx.fillRect(x-cw/2,H-bh,cw,bh);});
}
if(HASCHART){document.getElementById('clickHint').innerHTML='<b style="color:#ff7a45">종목 행 클릭 → 차트 팝업</b>';}
if(HASCHART)document.getElementById('tb').addEventListener('click',function(e){var tr=e.target.closest('tr[data-code]');if(tr)drawChart(tr.getAttribute('data-code'));});
document.getElementById('mClose').addEventListener('click',function(){document.getElementById('modal').style.display='none';});
document.getElementById('modal').addEventListener('click',function(e){if(e.target===this)this.style.display='none';});

</script></body></html>"""

def _self_test():
    import tempfile
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    tmp = tempfile.mkdtemp(); cp = os.path.join(tmp, "t.csv")
    with open(cp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["star", "code", "name", "ap", "order", "pbr", "deep", "ext", "r20", "c", "buy", "stop", "resist", "vflag", "tag"])
        w.writerow(["★", "042700", "한미반도체", "반등관찰", "혼조", 1.2, 0, 0.95, -20, 205500, 255535, 192138, 426000, "소진", "관심"])
        w.writerow(["✦", "000880", "테스트저PBR", "반등관찰", "혼조", 0.5, 1, 0.80, 3, 10000, 9800, 9000, 13000, "소진", "사냥터"])
    rows = read_rows(cp)
    chk("CSV 파싱", len(rows) == 2 and rows[0]["name"] == "한미반도체")
    chk("PBR·deep 파싱", rows[1]["pbr"] == 0.5 and rows[1]["deep"] == 1)
    html = build(rows)
    chk("HTML 골격", "<table" in html and "한미반도체" in html)
    chk("데이터 주입", "__DATA__" not in html and "__CHART__" not in html)
    chk("접근유형 색 매핑", "추세매수" in html and "APC" in html)
    chk("딥밸류바닥 UI", "딥밸류바닥" in html and "deeprow" in html)
    print(f"\n셀프테스트: {ok}/{tot}"); return ok == tot

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--chart", action="store_true", help="종목 클릭→차트 팝업 포함(무거움) → 진우_타점발굴_표_차트.html")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    if not os.path.exists(IN):
        print("[없음] 진우_타점발굴.csv — 먼저 진우_타점발굴.py 실행"); return 2
    rows = read_rows(IN)
    if a.chart:
        chart = build_chart_data([r["code"] for r in rows]); out = OUT_CHART; nm = "진우_타점발굴_표_차트.html"
    else:
        chart = {}; out = OUT; nm = "진우_타점발굴_표.html"
    html = build(rows, chart)
    with open(out, "w", encoding="utf-8") as f: f.write(html)
    nd = sum(r.get("deep", 0) for r in rows)
    print(f"저장: {nm} ({len(rows)}종 · 딥밸류바닥 {nd}종, {len(html):,}바이트, 차트={'O' if a.chart else 'X'})")
    return 0

if __name__ == "__main__":
    sys.exit(main())
