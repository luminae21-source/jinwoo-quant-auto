#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""편입확정.py — 추천 후보 → 리스크 관문 통과 → 확정 편입 책

recommend_dashboard 2트랙(가치·성장) 후보를 받아:
  ① 개편 통합 멀티팩터 스코어(모멘텀15%)로 교차 우선순위 부여
  ② 리스크 관문 적용: 포트폴리오 히트캡(종목당 1% 리스크 × N ≤ 6%) → 실 집행 종목 선별
  ③ 밸류=한 베팅 교훈 반영: 두 트랙 균형(가치3+성장3)으로 집중 회피
손절·비중은 대시보드와 동일(재량 1% 리스크 ÷ 스톱폭, 트랙별 스톱규칙).
2026 스테이징 데이터(가격월 최신·재무월 최신). ⚠️ 정보용·투자자문 아님·책임 본인.
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

import os, sys, json, numpy as np, pandas as pd, warnings
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
        if p: d=pd.read_csv(p,dtype={"code":str});d["code"]=d["code"].str.zfill(6);fr.append(d)
    return pd.concat(fr).pivot_table(index="ym",columns="code",values="close",aggfunc="last").sort_index()
def load_fin(field):
    fr=[]
    for f in ("종목재무_KRX_KOSPI.csv","종목재무_KRX_KOSDAQ.csv"):
        p=_find(f)
        if p:
            d=pd.read_csv(p,dtype={"code":str});d["code"]=d["code"].str.zfill(6)
            d["ym"]=pd.to_datetime(d["date"]).dt.strftime("%Y-%m");fr.append(d[["ym","code",field]])
    return pd.concat(fr).pivot_table(index="ym",columns="code",values=field,aggfunc="last").sort_index()
def load_mcap():
    d=pd.read_csv(_find("종목시총_30년.csv"),dtype={"code":str});d["code"]=d["code"].str.zfill(6)
    d["ym"]=pd.to_datetime(d["date"]).dt.strftime("%Y-%m")
    return d.pivot_table(index="ym",columns="code",values="mcap",aggfunc="last").sort_index()
def load_names():
    p=_find("종목명_맵.csv"); m={}
    if p:
        try:
            for _,r in pd.read_csv(p,dtype=str).iterrows(): m[str(r["code"]).zfill(6)]=r["name"]
        except Exception: pass
    return m
def z(s):
    m=s.mean();sd=s.std();return (s-m)/sd if sd>0 else s*0

# 대시보드 트랙 가중 + 개편 통합 가중
WV={"배당":0.046,"E/P":0.033,"B/P":0.027}; WG={"배당":0.038,"ROE":0.025,"EPS성장":0.023}
WREF={"배당":0.270,"B/P":0.204,"E/P":0.166,"성장":0.110,"ROE":0.100,"모멘텀":0.150}
RISK=1.0; HEAT_CAP=6.0; MAXPOS=15; STOP_CAP=20.0; DISASTER=40.0; TRAIL=25.0

def run():
    px=load_px();mcap=load_mcap();nm=load_names()
    EPS=load_fin("EPS");PER=load_fin("PER");PBR=load_fin("PBR");BPS=load_fin("BPS");DIV=load_fin("DIV")
    cols=px.columns
    pym=[m for m in px.index if m in mcap.index][-1]; fym=[m for m in EPS.index if m in px.index][-1]
    MC=mcap.loc[pym].reindex(cols); univ=MC.rank(ascending=False)<=200
    per=PER.loc[fym].reindex(cols); pbr=PBR.loc[fym].reindex(cols).where(univ); bps=BPS.loc[fym].reindex(cols)
    div=DIV.loc[fym].reindex(cols); eps=EPS.loc[fym].reindex(cols); eps12=EPS.shift(12).loc[fym].reindex(cols)
    ep=1.0/per.where(per>0); bp=1.0/pbr.where(pbr>0); dy=div.where(div>=0)
    roe=(eps/bps).where(bps>0); g1=(eps/eps12-1).where(eps12>0).clip(-1,3)
    mom=(px.shift(1).loc[pym]/px.shift(12).loc[pym]-1).reindex(cols)
    MA10=px.rolling(10).mean().loc[pym].reindex(cols); last=px.loc[pym].reindex(cols); up=(last>=MA10)
    med=pbr.median(); growth=(pbr>=med)&pbr.notna(); value=(pbr<med)&pbr.notna()
    # 개편 통합 스코어(전 유니버스 z 기준) → 교차 우선순위
    F={"배당":dy,"B/P":bp,"E/P":ep,"성장":g1,"ROE":roe,"모멘텀":mom}
    Z={k:z(v.where(univ)) for k,v in F.items()}
    refscore=sum(WREF[k]*Z[k].fillna(0) for k in WREF).where(univ)
    refpct=refscore.rank(pct=True)*100
    # 트랙 점수
    def tscore(mask,W,f):
        sc=pd.Series(0.0,index=cols);cnt=pd.Series(0,index=cols)
        for k,w in W.items():
            zz=z(f[k].where(mask));sc=sc.add(w*zz.fillna(0));cnt=cnt.add(zz.notna().astype(int))
        return sc.where(mask&(cnt>=2))
    # 통합 완료(2026-07): 후보 점수도 통합 가중(WREF·트랙 내 z)으로 — recommend_dashboard 완전통합과 일치
    FUNI={"배당":dy,"B/P":bp,"E/P":ep,"성장":g1,"ROE":roe,"모멘텀":mom}
    VS=tscore(value,WREF,FUNI); GS=tscore(growth,WREF,FUNI)
    def cands(S,kind,n=10):
        s=S.where(up).dropna().sort_values(ascending=False)  # 관문1: 추세위(A진입)
        out=[]
        for c in s.index[:n]:
            p=last.get(c)
            if pd.isna(p) or p<=0: continue
            onR=(TRAIL if kind=="growth" else DISASTER)/100.0
            w=min(RISK/(onR*100),STOP_CAP/100.0)
            out.append(dict(code=c,name=nm.get(c,c),track=("성장" if kind=="growth" else "가치"),
                price=float(p),stop=float(p*(1-onR)),Rpct=onR*100,weight=round(w*100,1),
                refpct=round(float(refpct.get(c,np.nan)),0),
                div=(round(float(dy.get(c)),1) if pd.notna(dy.get(c)) else None),
                per=(round(float(per.get(c)),1) if pd.notna(per.get(c)) else None),
                pbr=(round(float(pbr.get(c)),1) if pd.notna(pbr.get(c)) else None),
                roe=(round(float(roe.get(c))*100,0) if pd.notna(roe.get(c)) else None),
                g1=(round(float(g1.get(c))*100,0) if pd.notna(g1.get(c)) else None)))
        return out
    val=cands(VS,"value"); grw=cands(GS,"growth")
    allc=val+grw
    # 관문2: 히트캡. 종목당 리스크=1%(비중×스톱폭). 히트 Σ리스크 ≤ 6% → 약 6종.
    # 우선순위=개편 통합 스코어 %ile. 밸류=한 베팅 교훈 → 트랙 균형(가치3+성장3).
    nslot=int(HEAT_CAP/RISK)  # 6
    per_track=nslot//2
    val_sorted=sorted(val,key=lambda r:-(r["refpct"] or 0))
    grw_sorted=sorted(grw,key=lambda r:-(r["refpct"] or 0))
    book=val_sorted[:per_track]+grw_sorted[:per_track]
    book=sorted(book,key=lambda r:-(r["refpct"] or 0))
    heat=len(book)*RISK; gross=sum(r["weight"] for r in book)

    print("="*98);print(f"확정 편입 책 — 리스크 관문 통과 (가격월 {pym}·재무월 {fym}·top200)");print("="*98)
    print(f"  후보(A진입=추세위): 가치 {len(val)}종 + 성장 {len(grw)}종 = {len(allc)}종")
    print(f"  관문: 종목당 리스크 {RISK}% · 히트캡 {HEAT_CAP}%(→{nslot}종) · 최대 {MAXPOS}종 · 종목상한 {STOP_CAP}%")
    print(f"  → 확정 {len(book)}종(가치{per_track}+성장{per_track}·개편스코어 우선) · 총비중 {gross:.1f}% · 포트히트 {heat:.0f}% · 현금 {100-gross:.0f}%\n")
    print(f"  {'종목':<14}{'트랙':<5}{'개편%ile':>8}{'배당':>6}{'PER':>6}{'PBR':>6}{'ROE':>6}{'성장':>7}{'현재가':>10}{'손절':>10}{'비중':>6}")
    def fmt(x,su='',dec=1):
        return '-' if x is None else (f"{x:.{dec}f}{su}")
    for r in book:
        d=fmt(r['div'],'%'); pe=fmt(r['per']); pb=fmt(r['pbr']); ro=fmt(r['roe'],'%',0); gg=('-' if r['g1'] is None else f"{r['g1']:+.0f}%")
        print(f"  {r['name']:<14}{r['track']:<5}{r['refpct']:>7.0f}%{d:>6}{pe:>6}{pb:>6}{ro:>6}{gg:>7}{r['price']:>10,.0f}{r['stop']:>10,.0f}{r['weight']:>5.1f}%")
    excl=[r for r in allc if r["code"] not in {b["code"] for b in book}]
    print(f"\n  [제외된 후보 {len(excl)}종] — 히트캡 초과분(개편스코어 하위·다음 순번)")
    for r in sorted(excl,key=lambda r:-(r["refpct"] or 0)):
        print(f"   {r['name']:<14}{r['track']:<5} 개편%ile {r['refpct']:>3.0f}%  비중{r['weight']:.1f}% (대기)")
    print("\n  ⚠️ 스테이징 데이터 기준. 실전은 로컬 recommend_pipeline(preflight 관문+최신시세)로 확정.")
    print("     비중=자본대비·종목당 손실 1% 사이징. 손절 도달 시 청산. 투자자문 아님·책임 본인.")
    json.dump(dict(pym=pym,fym=fym,gates=dict(risk=RISK,heat_cap=HEAT_CAP,maxpos=MAXPOS,slots=nslot),
        book=book,excluded=[r["name"] for r in excl],candidates_all=allc,gross=round(gross,1),heat=heat),
        open(os.path.join(BASE,"편입확정_결과.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2,default=str)
    print("\n  저장: 편입확정_결과.json")
    return dict(pym=pym,fym=fym,book=book,val=val,grw=grw,gross=gross,heat=heat,nslot=nslot)

if __name__=="__main__":
    run()
