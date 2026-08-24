#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""style_conditional_factor.py — 스타일(성장/가치) 분리 조건부 팩터 검정 + 스크리너

유니버스(top200)를 매월 성장/가치 두 그룹으로 나눈 뒤, 각 그룹 '안에서' 팩터
효력(IC·분위수 롱숏)을 따로 검정한다. 섞어 평균낼 때 상쇄되던 팩터가 스타일별로
드러난다. 4가지 분류법 스위치:
  --split pbr        고PBR=성장 / 저PBR=가치   (Fama-French HML 표준, 기본)
  --split growth     고EPS성장=성장 / 저성장=가치
  --split composite  z(PBR)+z(EPS성장)-z(배당) 상위=성장
  --split sector     테마 사전(반도체·2차전지·바이오·게임 등=성장 / 금융·통신·유틸=가치)
  --split all        네 가지 모두 순차 실행(비교)
검정 팩터: 배당 · E/P · B/P · EPS성장 · ROE · 모멘텀12-1 (+옵션 EV/EBIT·FCF)
30년 상폐포함 월봉 · 재무 2002~ · top200 · 룩어헤드X(t지표→t+1수익).
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
    px=pd.concat(fr).pivot_table(index="ym",columns="code",values="close",aggfunc="last").sort_index()
    return px, px.pct_change(fill_method=None).mask(lambda x:x.abs()>1.0)
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

GROWTH_SEC={"005930","000660","042700","240810","036930","058470","166090","007660","353200","402340","011070","006400","086520","247540","373220",  # 반도체·2차전지
 "196170","141080","145020","085620","328130","091990","068270","207940",  # 바이오
 "036570","251270","259960","263750","035420","035720","377300",           # 게임·인터넷
 "277810","454910","012510"}                                                # 로봇·SW
VALUE_SEC={"105560","055550","139130","138930","086790","316140","024110","105550","139120","139110","139230",  # 금융
 "001450","000810","000815","032830",                                       # 보험
 "006800","039490","071050","016360","003540",                              # 증권
 "030200","017670","032640",                                                # 통신
 "015760","036460","034020"}                                                # 유틸

def build():
    px,rets=load_px(); mcap=load_mcap()
    EPS=load_fin("EPS");PER=load_fin("PER");PBR=load_fin("PBR");BPS=load_fin("BPS");DIV=load_fin("DIV")
    idx=[m for m in EPS.index if m in rets.index and m in mcap.index and m>="2003-01"]
    cols=px.columns
    al=lambda df: df.reindex(index=idx,columns=cols)
    EPS,PER,PBR,BPS,DIV=al(EPS),al(PER),al(PBR),al(BPS),al(DIV)
    RET=rets.reindex(index=idx,columns=cols); MC=mcap.reindex(index=idx,columns=cols); PX=px.reindex(index=idx,columns=cols)
    ep=1.0/PER.where(PER>0); bp=1.0/PBR.where(PBR>0); dy=DIV.where(DIV>=0)
    roe=(EPS/BPS).where(BPS>0); g1=(EPS/EPS.shift(12)-1).where(EPS.shift(12)>0).clip(-1,3)
    mom=(PX.shift(1)/PX.shift(12)-1)
    factors={"배당":dy,"E/P":ep,"B/P":bp,"EPS성장":g1,"ROE":roe,"모멘텀12-1":mom}
    return dict(idx=idx,cols=cols,MC=MC,RET=RET,PBR=PBR,g1=g1,DIV=DIV,factors=factors)

def zc(row):
    m=row.mean(); s=row.std(); return (row-m)/s if s>0 else row*0

def split_mask(D, method, ym):
    """유니버스 내 성장(True)/가치(False) 마스크 반환."""
    cols=D["cols"]; univ=D["MC"].loc[ym].rank(ascending=False)<=200
    if method=="pbr":
        met=D["PBR"].loc[ym].where(univ)              # 고PBR=성장
    elif method=="growth":
        met=D["g1"].loc[ym].where(univ)               # 고성장=성장
    elif method=="composite":
        z=zc(D["PBR"].loc[ym].where(univ))+zc(D["g1"].loc[ym].where(univ))-zc(D["DIV"].loc[ym].where(univ))
        met=z
    elif method=="sector":
        s=pd.Series(index=cols,dtype=float)
        for c in cols:
            if c in GROWTH_SEC: s[c]=1.0
            elif c in VALUE_SEC: s[c]=0.0
        met=s.where(univ)
        gm=(met==1.0); vm=(met==0.0); return gm.fillna(False), vm.fillna(False)
    med=met.median()
    gm=(met>=med)&met.notna(); vm=(met<med)&met.notna()
    return gm, vm

def factor_in_group(D, F, member_mask_fn):
    """그룹 마스크(월별)에서 팩터 IC·롱숏."""
    idx=D["idx"]; RET=D["RET"]; fwd=RET.shift(-1)
    ics=[];ls=[];ns=[]
    for ym in idx[:-1]:
        gm=member_mask_fn(ym)
        f=F.loc[ym].where(gm).dropna(); r=fwd.loc[ym]
        f=f[[c for c in f.index if pd.notna(r.get(c))]]
        if len(f)<20: continue
        ics.append(f.rank().corr(r[f.index].rank())); ns.append(len(f))
        try:
            q=pd.qcut(f.rank(method="first"),5,labels=False,duplicates="drop")
            if pd.Series(q).nunique()>=5:
                ls.append(r[f.index[q==4]].mean()-r[f.index[q==0]].mean())
        except Exception: pass
    ics=pd.Series(ics).dropna(); ls=pd.Series(ls).dropna()
    if len(ics)<12: return None
    mIC=ics.mean(); t=mIC/(ics.std()/np.sqrt(len(ics)))
    return dict(meanIC=round(mIC,4),ic_t=round(t,1),
                ls_ann=round(ls.mean()*12*100,1) if len(ls) else None,
                ls_sharpe=round(ls.mean()/ls.std()*np.sqrt(12),2) if len(ls)>1 and ls.std()>0 else None,
                ls_hit=round((ls>0).mean()*100,0) if len(ls) else None,
                months=len(ics),avg_n=int(np.mean(ns)))

def run_method(D, method):
    # 월별 마스크 미리 계산
    gmask={}; vmask={}
    for ym in D["idx"]:
        gm,vm=split_mask(D,method,ym); gmask[ym]=gm; vmask[ym]=vm
    out={"성장주":{}, "가치주":{}}
    for gname,mdict in (("성장주",gmask),("가치주",vmask)):
        for fname,F in D["factors"].items():
            r=factor_in_group(D,F,lambda ym: mdict[ym])
            if r: out[gname][fname]=r
    # 그룹 평균 사이즈
    gsz=int(np.mean([gmask[m].sum() for m in D["idx"]])); vsz=int(np.mean([vmask[m].sum() for m in D["idx"]]))
    return out, (gsz,vsz)

LABEL={"pbr":"PBR 기준(표준)","growth":"EPS성장 기준","composite":"복합점수","sector":"섹터/테마"}
def print_method(method, out, sizes):
    print("="*100); print(f"[ {LABEL[method]} ] 성장주 평균 {sizes[0]}종 · 가치주 평균 {sizes[1]}종"); print("="*100)
    for g in ("성장주","가치주"):
        print(f"\n  《{g}》 그룹 내 팩터 (IC순)")
        print(f"    {'팩터':<12}{'평균IC':>9}{'IC t':>7}{'롱숏연%':>9}{'Sharpe':>9}{'승률':>7}{'개월':>6}")
        rows=sorted(out[g].items(),key=lambda kv:-abs(kv[1]["meanIC"]))
        for fn,v in rows:
            sh="-" if v["ls_sharpe"] is None else f"{v['ls_sharpe']:.2f}"
            la="-" if v["ls_ann"] is None else f"{v['ls_ann']:+.1f}"
            hi="-" if v["ls_hit"] is None else f"{v['ls_hit']:.0f}"
            sig="*" if v["ic_t"]>=2.0 else " "
            print(f"   {sig}{fn:<11}{v['meanIC']:>+9.4f}{v['ic_t']:>7.1f}{la:>9}{sh:>9}{hi:>6}%{v['months']:>6}")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--split",default="all",
        choices=["pbr","growth","composite","sector","all"]); a=ap.parse_args()
    D=build()
    methods=["pbr","growth","composite","sector"] if a.split=="all" else [a.split]
    allres={}
    for m in methods:
        out,sizes=run_method(D,m); print_method(m,out,sizes)
        allres[m]=dict(sizes=sizes,result=out)
    print("\n  * = IC t≥2.0 (유의). ⚠️ 과거통계·미래보장 아님. 투자자문 아님·책임 본인.")
    json.dump(allres,open(os.path.join(BASE,"style_conditional_result.json"),"w",encoding="utf-8"),
              ensure_ascii=False,indent=2,default=str)
    print("  저장: style_conditional_result.json")

if __name__=="__main__":
    main()
