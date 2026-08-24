#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""entry_timing_test.py — 스타일 점수 × 추세전환 진입필터 효력 검정 (이벤트스터디)

질문: 각 트랙(가치/성장) '점수 상위'에 추세 필터를 더하면 향후 수익이 좋아지나?
버킷별 전방수익(3·6개월) 비교:
  ① 점수상위(트랙 상위20%)  ② +추세위(close≥MA10)  ③ +추세아래  ④ +방금 MA200회복(전환)
추세: 월봉 close vs 10개월MA(≈일봉 MA200). 전환=전월 아래→당월 위 돌파.
30년 상폐포함 월봉·재무 2003~·top200·룩어헤드X. ⚠️정보용·미래보장 아님·투자자문 아님·책임 본인.
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
WV={"배당":0.046,"E/P":0.033,"B/P":0.027}; WG={"배당":0.038,"ROE":0.025,"EPS성장":0.023}
def zrow(df):  # cross-sectional z per row
    return df.sub(df.mean(axis=1),axis=0).div(df.std(axis=1).replace(0,np.nan),axis=0)

def build():
    px=load_px(); mcap=load_mcap()
    EPS=load_fin("EPS");PER=load_fin("PER");PBR=load_fin("PBR");BPS=load_fin("BPS");DIV=load_fin("DIV")
    idx=[m for m in EPS.index if m in px.index and m in mcap.index and m>="2003-01"]
    cols=px.columns; al=lambda d:d.reindex(index=idx,columns=cols)
    EPS,PER,PBR,BPS,DIV=al(EPS),al(PER),al(PBR),al(BPS),al(DIV)
    PX=px.reindex(index=idx,columns=cols); MC=mcap.reindex(index=idx,columns=cols)
    univ=MC.rank(axis=1,ascending=False)<=200
    ep=1.0/PER.where(PER>0); bp=1.0/PBR.where(PBR>0); dy=DIV.where(DIV>=0)
    roe=(EPS/BPS).where(BPS>0); g1=(EPS/EPS.shift(12)-1).where(EPS.shift(12)>0).clip(-1,3)
    med=PBR.where(univ).median(axis=1)
    growth=univ&PBR.ge(med,axis=0); value=univ&PBR.lt(med,axis=0)
    def score(mask,W,f):
        s=None; cnt=None
        for k,w in W.items():
            zz=zrow(f[k].where(mask)); s=(w*zz.fillna(0)) if s is None else s.add(w*zz.fillna(0))
            cnt=(zz.notna().astype(int)) if cnt is None else cnt.add(zz.notna().astype(int))
        return s.where(mask&(cnt>=2))
    VS=score(value,WV,{"배당":dy,"E/P":ep,"B/P":bp})
    GS=score(growth,WG,{"배당":dy,"ROE":roe,"EPS성장":g1})
    MA10=PX.rolling(10).mean(); MA3=PX.rolling(3).mean()
    up=(PX>=MA10)&MA10.notna()
    prev_up=up.shift(1,fill_value=False).astype(bool)
    recov=up&(~prev_up)                                            # MA200회복(전월아래→당월위)
    gc=(MA3>=MA10)&(MA3.shift(1)<MA10.shift(1))&MA10.notna()       # 골든크로스
    fwd3=PX.shift(-3)/PX-1; fwd6=PX.shift(-6)/PX-1
    return dict(idx=idx,cols=cols,VS=VS,GS=GS,up=up,recov=recov,gc=gc,fwd3=fwd3,fwd6=fwd6,value=value,growth=growth)

def stat(mask, fwd):
    v=fwd.where(mask).stack().dropna()
    if len(v)<50: return None
    return dict(n=int(len(v)),mean=round(v.mean()*100,1),med=round(v.median()*100,1),win=round((v>0).mean()*100,0))

def track(D, S, name):
    idx=D["idx"]
    topq = S.rank(axis=1,pct=True,ascending=True)>=0.8    # 트랙 내 상위20%
    buckets={
        "① 점수상위(전체)":topq,
        "② +추세위(≥MA10)":topq&D["up"],
        "③ +추세아래(<MA10)":topq&(~D["up"]),
        "④ +MA200회복(전환)":topq&D["recov"],
        "⑤ +골든크로스(전환)":topq&D["gc"],
    }
    print(f"\n  《{name} 트랙》 진입버킷별 전방수익")
    print(f"    {'버킷':<20}{'표본':>7}{'3M평균':>8}{'3M승률':>8}{'6M평균':>8}{'6M승률':>8}")
    res={}
    for b,m in buckets.items():
        s3=stat(m,D["fwd3"]); s6=stat(m,D["fwd6"])
        if not s3:
            print(f"    {b:<20}{'표본부족':>7}"); continue
        print(f"    {b:<20}{s3['n']:>7}{s3['mean']:>+7.1f}%{s3['win']:>7.0f}%{(s6['mean'] if s6 else 0):>+7.1f}%{(s6['win'] if s6 else 0):>7.0f}%")
        res[b]=dict(n3=s3['n'],r3=s3['mean'],w3=s3['win'],r6=(s6['mean'] if s6 else None),w6=(s6['win'] if s6 else None))
    return res

def main():
    D=build()
    print("="*84); print(f"진입 타이밍 검정 — 스타일점수 × 추세전환 (2003~ · top200 · 룩어헤드X)"); print("="*84)
    out={"value":track(D,D["VS"],"가치"),"growth":track(D,D["GS"],"성장")}
    print("\n  · ②>①이면 '추세 필터가 도움'. ④⑤(전환직후)가 높으면 '아래→위 전환점 진입'이 유효.")
    print("  ⚠️ 3·6M 전방 단순수익(비용전). 과거통계·미래보장 아님. 투자자문 아님·책임 본인.")
    json.dump(out,open(os.path.join(BASE,"entry_timing_result.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2,default=str)
    print("  저장: entry_timing_result.json")

if __name__=="__main__":
    main()
