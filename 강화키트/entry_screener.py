#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""entry_screener.py — 스타일 두 트랙 + 진입 타이밍(추세 레짐) 통합 스크리너

style_screener(점수) + entry_timing_test(검증) 결과를 하나로:
  · 트랙 분리: top200을 PBR 중앙값으로 가치/성장
  · 점수: 가치=배당+E/P+B/P, 성장=배당+ROE+EPS성장 (IC가중, 검증됨)
  · 진입 게이트(검증결과 채택): 추세 '레짐'(월봉 close≥10개월MA≈MA200)이 유효.
        A진입 = 점수상위 & 추세위   (승률·6M 안정 ↑)
        B관찰 = 점수상위 & 추세아래 (레짐 전환 대기 — 싼 채 더 싸질 위험)
  · 전환 플래그(참고): 이번달 MA200회복/골든크로스 — 검증상 타이밍 이점은 약함(늦음), 정보용.
사용: py entry_screener.py [--topn 20]
⚠️ 과거통계 기반·미래보장 아님. 투자자문 아님·책임 본인.
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

import os, sys, json, argparse, numpy as np, pandas as pd, warnings
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
WV={"배당":0.046,"E/P":0.033,"B/P":0.027}; WG={"배당":0.038,"ROE":0.025,"EPS성장":0.023}
def z(s):
    m=s.mean(); sd=s.std(); return (s-m)/sd if sd>0 else s*0
def _r(x,nd=1,mul=1): return round(float(x)*mul,nd) if pd.notna(x) else None

def run(topn=20):
    px=load_px(); mcap=load_mcap()
    EPS=load_fin("EPS");PER=load_fin("PER");PBR=load_fin("PBR");BPS=load_fin("BPS");DIV=load_fin("DIV")
    ym=[m for m in EPS.index if m in px.index and m in mcap.index][-1]
    cols=px.columns
    MC=mcap.loc[ym].reindex(cols); univ=MC.rank(ascending=False)<=200
    per=PER.loc[ym].reindex(cols); pbr=PBR.loc[ym].reindex(cols).where(univ)
    bps=BPS.loc[ym].reindex(cols); div=DIV.loc[ym].reindex(cols); eps=EPS.loc[ym].reindex(cols)
    eps12=EPS.shift(12).loc[ym].reindex(cols)
    ep=1.0/per.where(per>0); bp=1.0/pbr.where(pbr>0); dy=div.where(div>=0)
    roe=(eps/bps).where(bps>0); g1=(eps/eps12-1).where(eps12>0).clip(-1,3)
    med=pbr.median(); growth=(pbr>=med)&pbr.notna(); value=(pbr<med)&pbr.notna()
    # 추세 레짐 + 전환 플래그
    MA10=px.rolling(10).mean(); MA3=px.rolling(3).mean()
    up=(px.loc[ym]>=MA10.loc[ym]); upP=(px.shift(1).loc[ym]>=MA10.shift(1).loc[ym])
    recov=up&(~upP.fillna(False))
    gc=(MA3.loc[ym]>=MA10.loc[ym])&(MA3.shift(1).loc[ym]<MA10.shift(1).loc[ym])
    def score(mask,W,f):
        sc=pd.Series(0.0,index=cols); cnt=pd.Series(0,index=cols)
        for k,w in W.items():
            zz=z(f[k].where(mask)); sc=sc.add(w*zz.fillna(0)); cnt=cnt.add(zz.notna().astype(int))
        return sc.where(mask&(cnt>=2))
    VS=score(value,WV,{"배당":dy,"E/P":ep,"B/P":bp}).dropna().sort_values(ascending=False)
    GS=score(growth,WG,{"배당":dy,"ROE":roe,"EPS성장":g1}).dropna().sort_values(ascending=False)
    nm=load_names()
    def grade(c):
        u=bool(up.get(c)); return ("A진입" if u else "B관찰"), u
    def flag(c):
        fl=[]
        if bool(recov.get(c)): fl.append("MA회복")
        if bool(gc.get(c)): fl.append("골든크로스")
        return "·".join(fl) if fl else ""
    def show(title,s,kind):
        print(f"\n  《{title}》 상위 {min(topn,len(s))}종")
        if kind=="value":
            print(f"    {'등급':<5}{'종목':<13}{'배당':>6}{'PER':>7}{'PBR':>6}{'추세':>6}  전환플래그")
        else:
            print(f"    {'등급':<5}{'종목':<13}{'ROE':>6}{'성장':>7}{'PBR':>6}{'추세':>6}  전환플래그")
        rows=[]
        for c in s.index[:topn]:
            g,u=grade(c); tl='위' if u else '아래'; fl=flag(c)
            if kind=="value":
                print(f"    {g:<5}{nm.get(c,c):<13}{(dy.get(c) if pd.notna(dy.get(c)) else 0):>5.1f}%{(per.get(c) if pd.notna(per.get(c)) else 0):>7.1f}{(pbr.get(c) if pd.notna(pbr.get(c)) else 0):>6.1f}{tl:>6}  {fl}")
            else:
                print(f"    {g:<5}{nm.get(c,c):<13}{(roe.get(c)*100 if pd.notna(roe.get(c)) else 0):>5.0f}%{(g1.get(c)*100 if pd.notna(g1.get(c)) else 0):>+6.0f}%{(pbr.get(c) if pd.notna(pbr.get(c)) else 0):>6.1f}{tl:>6}  {fl}")
            rows.append(dict(code=c,name=nm.get(c,c),grade=g,trend_up=u,flag=fl,
                             div=_r(dy.get(c)),per=_r(per.get(c)),pbr=_r(pbr.get(c)),
                             roe=_r(roe.get(c),0,100),g1=_r(g1.get(c),0,100)))
        return rows
    print("="*90); print(f"진입 스크리너 (스타일 두 트랙 + 추세 레짐 게이트) — {ym}"); print("="*90)
    print(f"  A진입=점수상위&추세위(검증상 승률·안정 ↑) · B관찰=추세아래(레짐 전환 대기)")
    vr=show("가치 트랙 (저PBR)",VS,"value"); gr=show("성장 트랙 (고PBR)",GS,"growth")
    na=sum(1 for r in vr+gr if r["grade"]=="A진입")
    print(f"\n  요약: A진입 {na}종 · B관찰 {len(vr)+len(gr)-na}종 (급락장이라 A진입 적은 게 정상)")
    print("  · A진입=바로 후보(분할·리스크예산). B관찰=추세 위로 돌 때까지 대기. 전환플래그는 참고(타이밍 이점 약함).")
    print("  ⚠️ 과거통계 기반·미래보장 아님. 투자자문 아님·책임 본인.")
    json.dump(dict(asof=ym,pbr_median=round(float(med),2),value=vr,growth=gr),
              open(os.path.join(BASE,"entry_screener_result.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2,default=str)
    print("  저장: entry_screener_result.json")
    return ym,vr,gr
if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--topn",type=int,default=20); a=ap.parse_args()
    run(a.topn)
