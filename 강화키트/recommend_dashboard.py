#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""추천대시보드.py — 유니버스 자동 검색 + 추천 종목 한 장 (원클릭)

지금까지 검증한 규칙을 하나가 자동 계산해서 '추천대시보드.html'로 띄운다:
  · 주도주 유니버스: 시총 상위100 → 12-1 모멘텀 상위(동적 리더십)
  · 가치 트랙 추천: 저PBR · 통합 멀티팩터 점수(배당·B/P·E/P·성장·ROE·모멘텀15%·트랙내 z) · 추세위(A진입)
  · 성장 트랙 추천: 고PBR · 동일 통합 점수(트랙 내 z) · 추세위(A진입)
  · 각 추천에 손절가·비중(리스크 1%÷1R)·매도규칙 자동 표기 (진우_통합한도.json)
실행: py 추천대시보드.py   (또는 추천_실행.bat 더블클릭) → HTML 자동 오픈.
⚠️ 정보·검증용·미래보장 아님. 투자자문 아님·책임 본인.
"""
import os as _os2
def _jqroot2():
    """프로젝트 루트 자동탐색 (2026-07-27 §5b)."""
    d=_os2.path.dirname(_os2.path.abspath(__file__))
    for _ in range(5):
        if _os2.path.exists(_os2.path.join(d,"종목시총_30년.csv")): return d
        d=_os2.path.dirname(d)
    return _os2.path.dirname(_os2.path.abspath(__file__))


# ── 경로 자립화 (2026-07-27) — 샌드박스 하드코딩 제거 ──────────────
import os as _os, glob as _glob
_JQ_HERE = _os.path.dirname(_os.path.abspath(__file__))


def _jqroot():
    d = _JQ_HERE
    for _ in range(5):
        if _os.path.exists(_os.path.join(d, "종목시총_30년.csv")):
            return d
        d = _os.path.dirname(d)
    return _os.path.dirname(_JQ_HERE)


BASE = _os.environ.get("JQ_BASE", _jqroot())


def _jqfind(name):
    """이름으로 파일 자동탐색 (백업/보관 폴더 제외)."""
    for b in (BASE, _JQ_HERE, _os.getcwd()):
        hits = [h for h in _glob.glob(_os.path.join(b, "**", name), recursive=True)
                if not any(s in h for s in ("_백업", "_보관", "_archive", "__pycache__"))]
        if hits:
            return sorted(hits, key=len)[0]
    raise FileNotFoundError(f"{name} 를 못 찾음 (루트={BASE})")
# ────────────────────────────────────────────────────────────────

import os, sys, io, json, webbrowser, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
BASE=os.path.dirname(os.path.abspath(__file__)); UP= _jqroot2()
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
def _find(fn):
    for d in (BASE,os.path.dirname(BASE),UP,os.path.join(UP,"강화키트")):
        p=os.path.join(d,fn)
        if os.path.exists(p): return p
    return None
def load_px():
    fr=[]
    for f in ("_월봉종가캐시_KOSPI.csv","_월봉종가캐시_KOSDAQ.csv"):
        p=_find(f)
        if p: d=pd.read_csv(p,dtype={"code":str}); d["code"]=d["code"].str.zfill(6); fr.append(d)
    return pd.concat(fr).pivot_table(index="ym",columns="code",values="close",aggfunc="last").sort_index()
def load_fin(field):
    fr=[]
    for f in ("종목재무_KRX_KOSPI.csv","종목재무_KRX_KOSDAQ.csv"):
        p=_find(f)
        if p:
            d=pd.read_csv(p,dtype={"code":str}); d["code"]=d["code"].str.zfill(6)
            d["ym"]=pd.to_datetime(d["date"]).dt.strftime("%Y-%m"); fr.append(d[["ym","code",field]])
    return pd.concat(fr).pivot_table(index="ym",columns="code",values=field,aggfunc="last").sort_index()
def load_mcap():
    d=pd.read_csv(_find("종목시총_30년.csv"),dtype={"code":str}); d["code"]=d["code"].str.zfill(6)
    d["ym"]=pd.to_datetime(d["date"]).dt.strftime("%Y-%m")
    return d.pivot_table(index="ym",columns="code",values="mcap",aggfunc="last").sort_index()
def load_names():
    p=_find("종목명_맵.csv"); m={}
    if p:
        try:
            for _,r in pd.read_csv(p,dtype=str).iterrows(): m[str(r["code"]).zfill(6)]=r["name"]
        except Exception: pass
    return m
def load_params():
    p=_find("진우_통합한도.json"); s={}
    if p:
        try:
            j=json.load(open(p,encoding="utf-8")); s=j.get("재량_사이징",{}); rg=j.get("집행_riskguard",{})
        except Exception: rg={}
    else: rg={}
    g=lambda k,dv: s.get(k,dv)
    return dict(risk=g("risk_per_trade_pct",1.0),heat=g("portfolio_heat_cap_pct",6.0),
        trail=g("momentum_트레일_pct",25.0),disaster=abs(g("deepvalue_재난백스톱_pct",-40.0)),
        stock_cap=rg.get("max_weight_pct",15.0),maxpos=rg.get("max_positions",15))
# 개편(2026-07 완전통합): 2트랙 개별 가중(WV/WG) → 검증된 통합 멀티팩터 가중(모멘텀15%)으로 교체.
#   가치·성장 트랙 구조(매도규칙·사이징)는 유지하되 '점수'는 두 트랙 모두 동일 통합가중으로 산출
#   (각 트랙 유니버스 내 z-score → 성장주가 B/P로 억울하게 안 깎임). 근거: 밸류축_확정·가중개편안·비용반영_백테.
#   이전값: WV={배당0.046,E/P0.033,B/P0.027}, WG={배당0.038,ROE0.025,EPS성장0.023}.
WUNI={"배당":0.270,"B/P":0.204,"E/P":0.166,"성장":0.110,"ROE":0.100,"모멘텀":0.150}
def z(s):
    m=s.mean(); sd=s.std(); return (s-m)/sd if sd>0 else s*0

def load_holdings():
    """보유 종목 로드 — 단일 진실원천 정리(2026-07-28).
    우선순위 ① my_holdings.csv (진우님이 실제 잔고를 직접 유지하는 원본)
             ② 진우_보유.csv  (보조/수동 입력용)
    my_holdings.csv 스키마: code,name,weight,entry_price,qty,entry_date,credit,stop,target
      · '#'로 시작하는 주석줄 허용   · entry_date 비어도 됨(그 경우 최근 12개월 고점으로 트레일 계산)
    """
    import csv
    def _rows(path, kc, km, ke, kn):
        out=[]
        try:
            lines=[l for l in io.open(path,encoding="utf-8-sig") if not l.lstrip().startswith("#")]
            for r in csv.DictReader(lines):
                r={(k or "").lstrip("﻿"):v for k,v in r.items()}
                c=(r.get(kc) or "").strip()
                if not c or not c.isdigit(): continue
                d=(r.get(km) or "").strip()
                out.append(dict(code=c.zfill(6), month=(d[:7] if len(d)>=7 else ""),
                                entry=(r.get(ke) or "").strip(),
                                name=(r.get(kn) or "").strip() if kn else ""))
        except Exception: pass
        return out
    p=_find("my_holdings.csv")
    if p:
        rows=_rows(p,"code","entry_date","entry_price","name")
        if rows: return rows
    p=_find("진우_보유.csv")
    if p:
        return _rows(p,"code","진입월","진입가",None)
    return []

def holdings_signals(px, pbr, med, last, MA10, nm, pym, P):
    """보유 종목별 트랙 라우팅 매도판정."""
    out=[]
    for h in load_holdings():
        c=h["code"]
        if c not in px.columns:
            out.append(dict(code=c,name=nm.get(c) or h.get("name") or c,signal="데이터없음")); continue
        cur=last.get(c)
        if pd.isna(cur): out.append(dict(code=c,name=nm.get(c) or h.get("name") or c,signal="가격없음")); continue
        # 진입가
        em=h["month"]
        try: entry=float(h["entry"]) if h["entry"] else (float(px.loc[em,c]) if em in px.index and pd.notna(px.loc[em,c]) else float(cur))
        except Exception: entry=float(cur)
        # 진입월~현재 고점
        try:
            seg=px.loc[em:pym,c] if (em in px.index) else px[c].tail(12)
            peak=float(pd.to_numeric(seg,errors="coerce").max())
        except Exception: peak=float(cur)
        pb=pbr.get(c); is_val = (pd.notna(pb) and pd.notna(med) and pb<med)
        track="가치" if is_val else "성장"
        ret=(cur/entry-1)*100 if entry>0 else 0
        ma=MA10.get(c); below=(pd.notna(ma) and cur<ma)
        sig="보유 유지"; sev=0
        if is_val:  # 딥밸류: 재난 −40% · 가치회귀
            if cur<=entry*(1-P["disaster"]/100): sig=f"재난손절(-{P['disaster']:.0f}%)"; sev=3
            elif pd.notna(pb) and pb>=1.0: sig="가치회귀 익절(PBR≥1.0)"; sev=2
            elif cur>=entry*2.0: sig="+100% 익절"; sev=2
        else:       # 모멘텀: 트레일 · 재난
            if cur<=entry*(1-P["disaster"]/100): sig=f"재난손절(-{P['disaster']:.0f}%)"; sev=3
            elif peak>0 and cur<=peak*(1-P["trail"]/100): sig=f"트레일 이탈(고점-{P['trail']:.0f}%)"; sev=3
            elif below: sig="추세이탈(MA10↓) 주의"; sev=1
        stop = entry*(1-P["disaster"]/100) if is_val else max(peak*(1-P["trail"]/100), entry*(1-P["disaster"]/100))
        out.append(dict(code=c,name=nm.get(c) or h.get("name") or c,track=track,entry=round(entry),cur=round(float(cur)),
                        ret=round(ret,1),peak=round(peak),stop=round(stop),pbr=(round(float(pb),2) if pd.notna(pb) else None),
                        signal=sig,sev=sev))
    out.sort(key=lambda r:-r.get("sev",0))
    return out

def compute():
    P=load_params(); px=load_px(); mcap=load_mcap(); nm=load_names()
    EPS=load_fin("EPS");PER=load_fin("PER");PBR=load_fin("PBR");BPS=load_fin("BPS");DIV=load_fin("DIV")
    cols=px.columns
    # 달 분리: 재무는 최신 재무월(fym) · 가격/추세/시총은 최신 가격월(pym)
    pym=[m for m in px.index if m in mcap.index][-1]      # 최신 가격·시총 달
    fym=[m for m in EPS.index if m in px.index][-1]       # 최신 재무 달
    MC=mcap.loc[pym].reindex(cols); univ=MC.rank(ascending=False)<=200
    # 재무(fym): 점수·밸류 지표
    per=PER.loc[fym].reindex(cols); pbr=PBR.loc[fym].reindex(cols).where(univ); bps=BPS.loc[fym].reindex(cols)
    div=DIV.loc[fym].reindex(cols); eps=EPS.loc[fym].reindex(cols); eps12=EPS.shift(12).loc[fym].reindex(cols)
    ep=1.0/per.where(per>0); bp=1.0/pbr.where(pbr>0); dy=div.where(div>=0)
    roe=(eps/bps).where(bps>0); g1=(eps/eps12-1).where(eps12>0).clip(-1,3)
    # 가격/추세(pym): 현재가·MA10 추세·진입 판단
    MA10=px.rolling(10).mean().loc[pym].reindex(cols); last=px.loc[pym].reindex(cols); up=(last>=MA10)
    med=pbr.median(); growth=(pbr>=med)&pbr.notna(); value=(pbr<med)&pbr.notna()
    ym=pym
    # 1) 주도주 유니버스: 시총 top100 → 12-1 모멘텀 상위(최신 가격월)
    top100=MC.rank(ascending=False)<=100
    mom_all=(px.shift(1).loc[pym]/px.shift(12).loc[pym]-1).reindex(cols)  # 통합점수용(전 유니버스)
    mom=mom_all.where(top100)                                              # 리더 표기용(top100)
    lead=mom.dropna().sort_values(ascending=False).head(15)
    leaders=[dict(name=nm.get(c,c),mom=round(float(mom[c])*100,0),rank=int(MC.rank(ascending=False)[c])) for c in lead.index]
    # 2) 두 트랙 점수 + A진입
    def score(mask,W,f):
        sc=pd.Series(0.0,index=cols); cnt=pd.Series(0,index=cols)
        for k,w in W.items():
            zz=z(f[k].where(mask)); sc=sc.add(w*zz.fillna(0)); cnt=cnt.add(zz.notna().astype(int))
        return sc.where(mask&(cnt>=2))
    FUNI={"배당":dy,"B/P":bp,"E/P":ep,"성장":g1,"ROE":roe,"모멘텀":mom_all}   # 통합 팩터셋(양 트랙 공통)
    VS=score(value,WUNI,FUNI); GS=score(growth,WUNI,FUNI)
    def track(S,kind,n=10):
        s=S.where(up).dropna().sort_values(ascending=False)   # A진입=점수&추세위
        out=[]
        for c in s.index[:n]:
            p=last.get(c)
            if pd.isna(p) or p<=0: continue
            onR=(P["trail"] if kind=="growth" else P["disaster"])/100.0
            stop=p*(1-onR); w=min(P["risk"]/(onR*100),P["stock_cap"]/100.0)
            out.append(dict(name=nm.get(c,c),price=float(p),stop=float(stop),R=onR*100,weight=w*100,
                div=(float(dy.get(c)) if pd.notna(dy.get(c)) else None),per=(float(per.get(c)) if pd.notna(per.get(c)) else None),
                pbr=(float(pbr.get(c)) if pd.notna(pbr.get(c)) else None),roe=(float(roe.get(c))*100 if pd.notna(roe.get(c)) else None),
                g1=(float(g1.get(c))*100 if pd.notna(g1.get(c)) else None)))
        return out
    val=track(VS,"value"); grw=track(GS,"growth")
    nA=len([1 for _ in val])+len([1 for _ in grw])
    # 보유 종목 매도판정
    holds=holdings_signals(px, pbr, med, last, MA10, nm, pym, P)
    return dict(ym=ym,pym=pym,fym=fym,P=P,leaders=leaders,value=val,growth=grw,nA=nA,holds=holds)

def html(D):
    ym=D["ym"]; P=D["P"]
    def led(r): return f"<tr><td class=nm>{r['name']}</td><td class=r>#{r['rank']}</td><td class=r style='color:var(--grw);font-weight:700'>+{r['mom']:.0f}%</td></tr>"
    def vr(r):
        f=lambda x,s='':'-' if x is None else f'{x:,.1f}{s}' if isinstance(x,float) else f'{x}{s}'
        return f"<tr><td class=nm>{r['name']}</td><td class=r>{('%.1f%%'%r['div']) if r['div'] is not None else '-'}</td><td class=r>{('%.1f'%r['per']) if r['per'] is not None else '-'}</td><td class=r>{('%.1f'%r['pbr']) if r['pbr'] is not None else '-'}</td><td class=r>{r['price']:,.0f}</td><td class=r style='color:#ef4444'>{r['stop']:,.0f}</td><td class=r><b>{r['weight']:.1f}%</b></td></tr>"
    def gr(r):
        return f"<tr><td class=nm>{r['name']}</td><td class=r>{('%.0f%%'%r['roe']) if r['roe'] is not None else '-'}</td><td class=r>{('%+.0f%%'%r['g1']) if r['g1'] is not None else '-'}</td><td class=r>{('%.1f'%r['pbr']) if r['pbr'] is not None else '-'}</td><td class=r>{r['price']:,.0f}</td><td class=r style='color:#ef4444'>{r['stop']:,.0f}</td><td class=r><b>{r['weight']:.1f}%</b></td></tr>"
    L="".join(led(r) for r in D["leaders"])
    V="".join(vr(r) for r in D["value"]) or "<tr><td colspan=7 style='color:var(--sub)'>추세위 가치 종목 없음 — 관망</td></tr>"
    G="".join(gr(r) for r in D["growth"]) or "<tr><td colspan=7 style='color:var(--sub)'>추세위 성장 종목 없음 — 관망</td></tr>"
    def hr(r):
        sev=r.get("sev",0); clr={3:"#ef4444",2:"#16a34a",1:"#e0a32e"}.get(sev,"#9fb0c9")
        rc="#16a34a" if r.get("ret",0)>=0 else "#ef4444"
        if "signal" in r and r.get("track") is None:
            return f"<tr><td class=nm>{r['name']}</td><td colspan=6 style='color:var(--sub)'>{r['signal']}</td></tr>"
        return (f"<tr><td class=nm>{r['name']}</td><td class=r>{r.get('track','')}</td>"
                f"<td class=r>{r['entry']:,}</td><td class=r>{r['cur']:,}</td>"
                f"<td class=r style='color:{rc}'>{r['ret']:+.1f}%</td><td class=r>{r['stop']:,}</td>"
                f"<td style='color:{clr};font-weight:700'>{r['signal']}</td></tr>")
    holds=D.get("holds",[])
    H="".join(hr(r) for r in holds)
    HOLD_CARD=(f"""<div class=card style="border-color:#ef4444">
<h3>📕 보유 종목 매도판정 <span style="font-weight:400;color:var(--sub);font-size:12px">— 진우_보유.csv · 트랙별 매도규칙</span></h3>
<table><thead><tr><th>종목</th><th class=r>트랙</th><th class=r>진입가</th><th class=r>현재가</th><th class=r>수익률</th><th class=r>손절선</th><th>신호</th></tr></thead>
<tbody>{H}</tbody></table>
<div class=note style="margin-top:8px">빨강=매도(재난·트레일 이탈) · 초록=익절(가치회귀·+100%) · 노랑=주의(추세이탈). 성장=고점−25% 트레일, 가치=재난−40%·PBR≥1.0/+100% 익절.</div></div>""" if holds else "")
    return f"""<!doctype html><html lang=ko><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>진우퀀트 추천 대시보드</title><style>
:root{{--bg:#0b1020;--card:#141b2e;--ink:#e8edf6;--sub:#9fb0c9;--line:#243149;--acc:#5b9dff;--val:#5b9dff;--grw:#a06bff}}
@media(prefers-color-scheme:light){{:root{{--bg:#f4f6fb;--card:#fff;--ink:#0f1830;--sub:#5a6a86;--line:#e3e9f4;--acc:#2563eb;--val:#2563eb;--grw:#7c3aed}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,'Segoe UI',Roboto,'Malgun Gothic',sans-serif;padding:22px;line-height:1.5}}
.wrap{{max-width:960px;margin:0 auto}}h1{{font-size:21px;margin:0 0 2px}}.sub{{color:var(--sub);font-size:12.5px;margin-bottom:16px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:15px 16px;margin-bottom:13px}}
h3{{font-size:14.5px;margin:0 0 4px}}.vh{{color:var(--val)}}.gh{{color:var(--grw)}}.cap{{color:var(--sub);font-size:11.5px;margin-bottom:9px}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}th,td{{padding:6px 6px;border-bottom:1px solid var(--line);text-align:left}}
th{{color:var(--sub);font-weight:600;font-size:10.5px}}td.r,th.r{{text-align:right;font-variant-numeric:tabular-nums}}.nm{{font-weight:600}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:13px}}@media(max-width:760px){{.two{{grid-template-columns:1fr}}}}
.note{{color:var(--sub);font-size:12px;line-height:1.6}}.warn{{color:#e0a32e;font-size:11.5px;margin-top:8px}}
.pill{{display:inline-block;background:rgba(91,157,255,.14);color:var(--acc);border-radius:999px;padding:3px 12px;font-size:12px;font-weight:600}}
</style></head><body><div class=wrap>
<h1>진우퀀트 — 오늘의 추천 종목</h1>
<div class=sub>가격·추세·시총 <b>{D['pym']}</b> 최신 · 재무(배당·PER·PBR·성장) <b>{D['fym']}</b> 기준 · 시총상위 유니버스 자동검색 · 손절·비중 자동</div>
<div style="margin-bottom:14px"><span class=pill>추천(A진입) {D['nA']}종</span> &nbsp;<span class=note>추세 위 & 점수 상위만 추천. 적으면 관망이 정상(방어).</span></div>
{HOLD_CARD}

<div class=card><h3>🔵 주도주 유니버스 <span style="font-weight:400;color:var(--sub);font-size:12px">— 시총 top100 중 12-1 모멘텀 상위</span></h3>
<div class=cap>지금 시장을 이끄는 종목(참고용 리더 목록). 매수는 아래 두 트랙 추천에서.</div>
<table><thead><tr><th>종목</th><th class=r>시총순위</th><th class=r>12-1 모멘텀</th></tr></thead><tbody>{L}</tbody></table></div>

<div class=two>
<div class=card><h3 class=vh>가치 트랙 추천</h3><div class=cap>저PBR · 통합점수(배당·B/P·E/P·성장·ROE·모멘텀15%) · 추세위 | 매도=재난−40%·가치회귀</div>
<table><thead><tr><th>종목</th><th class=r>배당</th><th class=r>PER</th><th class=r>PBR</th><th class=r>현재가</th><th class=r>손절</th><th class=r>비중</th></tr></thead><tbody>{V}</tbody></table></div>
<div class=card><h3 class=gh>성장 트랙 추천</h3><div class=cap>고PBR · 동일 통합점수(트랙 내 z) · 추세위 | 매도=고점−25% 트레일</div>
<table><thead><tr><th>종목</th><th class=r>ROE</th><th class=r>성장</th><th class=r>PBR</th><th class=r>현재가</th><th class=r>손절</th><th class=r>비중</th></tr></thead><tbody>{G}</tbody></table></div>
</div>

<div class=card><div class=note>
<b>보는 법.</b> 위 두 트랙의 종목을 <b>적힌 비중</b>만큼 사고 <b>손절가</b>에 스톱을 걸면 끝. 비중은 종목당 손실이 자본의 1%가 되도록 자동 계산됨(가치=넓은 스톱→작게, 성장=좁은 스톱→크게). 총합이 낮으면 나머지는 현금(방어).<br>
성장=고점 갱신 시 트레일 상향 · 가치=PBR≥1.0/+100% 도달 시 익절, 스톱은 재난용만.
</div><div class=warn>⚠️ 자동 산출·과거통계 기반·미래보장 아님. 슬리피지·유동성·뉴스는 별도 확인. 투자자문 아님 · 최종 판단·책임 본인.</div></div>
</div></body></html>"""

def rebuild_monthly_cache():
    """종목일봉_30년_{market}.csv → _월봉종가캐시_{market}.csv 재생성(최신 반영)."""
    for market in ("KOSPI","KOSDAQ"):
        daily=_find(f"종목일봉_30년_{market}.csv")
        if not daily:
            print(f"  [건너뜀] 종목일봉_30년_{market}.csv 없음"); continue
        keep={}
        for ch in pd.read_csv(daily,usecols=["date","code","close"],dtype={"code":str},
                              encoding="utf-8-sig",chunksize=2_000_000):
            ch=ch[pd.to_numeric(ch["close"],errors="coerce")>0]; ch["ym"]=ch["date"].str[:7]
            for dte,c,cl,ym in zip(ch["date"],ch["code"],ch["close"],ch["ym"]):
                k=(str(c).zfill(6),ym); cur=keep.get(k)
                if cur is None or dte>cur[0]: keep[k]=(dte,float(cl))
        out=pd.DataFrame([(c,ym,v[1]) for (c,ym),v in keep.items()],columns=["code","ym","close"])
        outp=os.path.join(os.path.dirname(daily),f"_월봉종가캐시_{market}.csv")
        out.to_csv(outp,index=False,encoding="utf-8-sig")
        print(f"  월봉캐시 재생성: {market} {len(out):,}행 (최신월 {out['ym'].max()})")

def main():
    if "--refresh-cache" in sys.argv:
        print("월봉캐시 재생성 중(최신 일봉 반영)...")
        rebuild_monthly_cache()
    D=compute(); h=html(D)
    out=os.path.join(BASE,"추천대시보드.html"); open(out,"w",encoding="utf-8").write(h)
    json.dump(D,open(os.path.join(BASE,"추천대시보드_결과.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2,default=str)
    print(f"추천 {D['nA']}종 · 저장: 추천대시보드.html")
    try: webbrowser.open("file://"+out.replace("\\","/"))
    except Exception: pass

if __name__=="__main__":
    main()
