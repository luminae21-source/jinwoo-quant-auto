#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""style_screener.py — 두 갈래(가치/성장) 스타일 스크리너

조건부 팩터 검정(style_conditional_factor.py) 결과를 그대로 반영:
  · 유니버스 top200을 PBR 중앙값으로 분리 → 저PBR=가치트랙 / 고PBR=성장트랙 (표준·최강통계)
  · 가치트랙 점수 = IC가중 z(배당 .046 + E/P .033 + B/P .027)
  · 성장트랙 점수 = IC가중 z(배당 .038 + ROE .025 + EPS성장 .023)
각 트랙 상위 랭킹 + 추세(월봉≥6개월MA) 동반 → '점수상위 & 추세전환'을 진입 후보로.
⚠️ 정보용·과거통계 기반·미래보장 아님. 투자자문 아님·책임 본인.
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
BASE=os.path.dirname(os.path.abspath(__file__))
UP= _jqroot2()
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
def _find(fn):
    for d in (BASE, os.path.dirname(BASE), UP, os.path.join(UP,"강화키트")):
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
WV={"배당":0.046,"E/P":0.033,"B/P":0.027}
WG={"배당":0.038,"ROE":0.025,"EPS성장":0.023}
def z(s):
    m=s.mean(); sd=s.std(); return (s-m)/sd if sd>0 else s*0

def run(topn=25):
    px=load_px(); mcap=load_mcap()
    EPS=load_fin("EPS");PER=load_fin("PER");PBR=load_fin("PBR");BPS=load_fin("BPS");DIV=load_fin("DIV")
    ym=[m for m in EPS.index if m in px.index and m in mcap.index][-1]
    cols=px.columns
    MC=mcap.loc[ym].reindex(cols); univ=MC.rank(ascending=False)<=200
    pbr=PBR.loc[ym].reindex(cols).where(univ)
    per=PER.loc[ym].reindex(cols); bps=BPS.loc[ym].reindex(cols); div=DIV.loc[ym].reindex(cols); eps=EPS.loc[ym].reindex(cols)
    eps12=EPS.shift(12).loc[ym].reindex(cols)
    ep=(1.0/per.where(per>0)); bp=(1.0/pbr.where(pbr>0)); dy=div.where(div>=0)
    roe=(eps/bps).where(bps>0); g1=(eps/eps12-1).where(eps12>0).clip(-1,3)
    med=pbr.median(); growth=(pbr>=med)&pbr.notna(); value=(pbr<med)&pbr.notna()
    ma6=px.rolling(6).mean().loc[ym].reindex(cols); last=px.loc[ym].reindex(cols)
    trend=(last>=ma6)
    nm=load_names()
    def score(mask,W,facs):
        sc=pd.Series(0.0,index=cols); cnt=pd.Series(0,index=cols)
        for k,w in W.items():
            zz=z(facs[k].where(mask)); sc=sc.add(w*zz.fillna(0)); cnt=cnt.add(zz.notna().astype(int))
        return sc.where(mask & (cnt>=2))
    vs=score(value,WV,{"배당":dy,"E/P":ep,"B/P":bp}).dropna().sort_values(ascending=False)
    gs=score(growth,WG,{"배당":dy,"ROE":roe,"EPS성장":g1}).dropna().sort_values(ascending=False)
    def show(title,s,extra):
        print(f"\n  《{title}》 상위 {min(topn,len(s))}종  (점수 = IC가중 합성)")
        print(f"    {'종목':<14}{'배당':>6}{'PER':>7}{'PBR':>6}"+("".join(f"{e:>8}" for e in extra))+f"{'추세':>7}")
        rows=[]
        for c in s.index[:topn]:
            tv='추세위' if bool(trend.get(c)) else '추세아래'
            ex=""
            if "ROE" in extra:
                ex=f"{(roe.get(c)*100 if pd.notna(roe.get(c)) else 0):>7.0f}%"+f"{(g1.get(c)*100 if pd.notna(g1.get(c)) else 0):>+7.0f}%"
            print(f"    {nm.get(c,c):<14}{(dy.get(c) if pd.notna(dy.get(c)) else 0):>5.1f}%{(per.get(c) if pd.notna(per.get(c)) else 0):>7.1f}{(pbr.get(c) if pd.notna(pbr.get(c)) else 0):>6.1f}{ex}{tv:>8}")
            rows.append(dict(code=c,name=nm.get(c,c),div=_r(dy.get(c)),per=_r(per.get(c)),pbr=_r(pbr.get(c)),
                             roe=_r(roe.get(c),1,100),g1=_r(g1.get(c),0,100),trend=bool(trend.get(c))))
        return rows
    print("="*88); print(f"두 갈래 스타일 스크리너 — {ym} (top200 · PBR중앙값 분리)"); print("="*88)
    print(f"  가치트랙(저PBR<{med:.1f}) 배당+E/P+B/P  |  성장트랙(고PBR≥{med:.1f}) 배당+ROE+EPS성장")
    vrows=show("가치 트랙",vs,[]); grows=show("성장 트랙",gs,["ROE","EPS성장"])
    print("\n  · 각 트랙 '점수상위 + 추세위(또는 아래→위 전환)' 조합이 진입 후보. 점수만으론 밸류트랩 위험.")
    print("  ⚠️ 과거통계 기반·미래보장 아님. 투자자문 아님·책임 본인.")
    json.dump(dict(asof=ym,pbr_median=round(float(med),2),value=vrows,growth=grows),
              open(os.path.join(BASE,"style_screener_result.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2,default=str)
    print("  저장: style_screener_result.json")
    return ym,med,vrows,grows
def _r(x,nd=1,mul=1):
    return round(float(x)*mul,nd) if pd.notna(x) else None
if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--topn",type=int,default=25); a=ap.parse_args()
    run(a.topn)
