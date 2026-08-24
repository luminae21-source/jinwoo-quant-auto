#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""추천비교.py — 가중 개편 전후 현재월 상위 추천 종목 비교

현행(모멘텀0%) vs 개편(모멘텀15%·채택) vs 롱숏용(30%) 세 가중으로 최신월 합성스코어를 매겨
상위 N 종목의 진입·이탈·순위변화를 비교. 실제 리스트가 얼마나 바뀌는지 확인용.
⚠️ 정보용·과거통계·미래보장 아님. 투자자문 아님·책임 본인.
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
    for d in (BASE,os.path.dirname(BASE),UP,os.path.join(UP,"강화키트"),os.getcwd()):
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
            d=pd.read_csv(p,dtype=str)
            for _,r in d.iterrows(): m[str(r["code"]).zfill(6)]=r["name"]
        except Exception: pass
    return m
def zc(row):
    m=row.mean();s=row.std();return ((row-m)/s).clip(-3,3) if s>0 else row*0

SCHEMES={
 "현행(모멘텀0)":{"배당":0.049,"B/P":0.037,"E/P":0.030,"성장":0.020,"ROE":0.018,"모멘텀":0.0},
 "개편(모멘텀15·채택)":{"배당":0.270,"B/P":0.204,"E/P":0.166,"성장":0.110,"ROE":0.100,"모멘텀":0.150},
 "롱숏용(모멘텀30)":{"배당":0.223,"B/P":0.168,"E/P":0.136,"성장":0.091,"ROE":0.082,"모멘텀":0.300},
}
N=30

def run():
    px=load_px(); mcap=load_mcap()
    EPS=load_fin("EPS");PER=load_fin("PER");PBR=load_fin("PBR");BPS=load_fin("BPS");DIV=load_fin("DIV")
    ym=[m for m in EPS.index if m in px.index and m in mcap.index][-1]
    cols=px.columns
    u=(mcap.loc[ym].reindex(cols).rank(ascending=False)<=200)
    ep=1.0/PER.loc[ym].reindex(cols).where(lambda s:s>0); bp=1.0/PBR.loc[ym].reindex(cols).where(lambda s:s>0)
    dy=DIV.loc[ym].reindex(cols).where(lambda s:s>=0); roe=(EPS.loc[ym]/BPS.loc[ym]).reindex(cols).where(BPS.loc[ym].reindex(cols)>0)
    g1=(EPS.loc[ym]/EPS.shift(12).loc[ym]-1).reindex(cols).clip(-1,3)
    mom=(px.shift(1).loc[ym]/px.shift(12).loc[ym]-1).reindex(cols)
    F={"배당":dy,"B/P":bp,"E/P":ep,"성장":g1,"ROE":roe,"모멘텀":mom}
    Z={k:zc(v.where(u)) for k,v in F.items()}
    nm=load_names()
    ranks={}
    for name,w in SCHEMES.items():
        score=sum(w[k]*Z[k].fillna(0) for k in w)
        valid=sum(Z[k].notna().astype(int) for k in w)>=3
        s=score.where(u & valid).dropna().sort_values(ascending=False)
        ranks[name]={c:i+1 for i,c in enumerate(s.index)}
    old=ranks["현행(모멘텀0)"]; new=ranks["개편(모멘텀15·채택)"]
    old_top=set([c for c,r in old.items() if r<=N]); new_top=set([c for c,r in new.items() if r<=N])
    print("="*88);print(f"추천 리스트 개편 전후 비교 — {ym} · top200 유니버스 · 상위 {N}");print("="*88)
    print(f"\n  현행 상위{N} ∩ 개편 상위{N}: {len(old_top&new_top)}종목 유지 · 교체 {len(new_top-old_top)}종목")
    print(f"\n  [개편으로 새로 진입] (현행 {N}위 밖 → 개편 {N}위 안)")
    for c in sorted(new_top-old_top,key=lambda c:new[c]):
        print(f"   {new[c]:>2}위  {nm.get(c,c):<14}({c})  모멘텀z {Z['모멘텀'].get(c,float('nan')):+.2f}  현행순위 {old.get(c,'>200')}")
    print(f"\n  [개편에서 이탈] (현행 {N}위 안 → 개편 {N}위 밖)")
    for c in sorted(old_top-new_top,key=lambda c:old[c]):
        print(f"   현행{old[c]:>2}위  {nm.get(c,c):<14}({c})  모멘텀z {Z['모멘텀'].get(c,float('nan')):+.2f}  개편순위 {new.get(c,'>200')}")
    # 상위 15 나란히
    print(f"\n  [상위 15 나란히 비교]")
    print(f"   {'순위':>3}  {'현행(모멘텀0)':<20}{'개편(모멘텀15)':<20}{'롱숏용(모멘텀30)':<20}")
    inv={name:{r:c for c,r in rk.items()} for name,rk in ranks.items()}
    for i in range(1,16):
        row=[]
        for name in SCHEMES:
            c=inv[name].get(i); row.append(f"{nm.get(c,c)}" if c else "-")
        print(f"   {i:>3}  {row[0]:<20}{row[1]:<20}{row[2]:<20}")
    # 저장
    out={"asof":ym,"kept":len(old_top&new_top),"entered":[nm.get(c,c) for c in sorted(new_top-old_top,key=lambda c:new[c])],
         "exited":[nm.get(c,c) for c in sorted(old_top-new_top,key=lambda c:old[c])],
         "top15":{name:[nm.get(inv[name].get(i),"") for i in range(1,16)] for name in SCHEMES}}
    json.dump(out,open(os.path.join(BASE,"추천비교_결과.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2,default=str)
    print(f"\n  개편으로 상위{N} 중 {len(new_top-old_top)}종목 교체({100*len(new_top-old_top)/N:.0f}%). 저장: 추천비교_결과.json")
    print("  ⚠️ 정보용·과거통계·미래보장 아님. 투자자문 아님·책임 본인.")

if __name__=="__main__":
    run()
