#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""가중개편_백테.py — 합성스코어 가중 개편 전후 백테 비교

현행 vs 제안A(모델) vs 제안B(보수) 세 가중으로 합성스코어를 만들어
분위수 롱숏(상위20-하위20)의 IC·연수익·Sharpe·MDD·승률을 비교.
추가로 '밸류 부진기'(밸류 롱숏<0 월) 성과를 분리해 모멘텀 헤지 효과를 검증.
2003~2026 · top200 · 상폐포함 · 룩어헤드X(t스코어→t+1수익). ⚠️ 정보용·투자자문 아님·책임 본인.
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
    px=pd.concat(fr).pivot_table(index="ym",columns="code",values="close",aggfunc="last").sort_index()
    return px, px.pct_change(fill_method=None).mask(lambda x:x.abs()>1.0)
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
def zc(row):
    m=row.mean();s=row.std();return ((row-m)/s).clip(-3,3) if s>0 else row*0
def spearman(a,b):
    m=a.notna()&b.notna()
    if m.sum()<20: return np.nan
    return a[m].rank().corr(b[m].rank())

# 가중안 (배당·B/P·E/P·성장·ROE·모멘텀)
SCHEMES={
 "현행(모멘텀無)":{"배당":0.049,"B/P":0.037,"E/P":0.030,"성장":0.020,"ROE":0.018,"모멘텀":0.0},
 "현행+모멘텀0.15":{"배당":0.049,"B/P":0.037,"E/P":0.030,"성장":0.020,"ROE":0.018,"모멘텀":0.15},
 "균형C(밸류0.60)":{"배당":0.248,"B/P":0.194,"E/P":0.158,"성장":0.180,"ROE":0.100,"모멘텀":0.120},
 "균형D(밸류0.55)":{"배당":0.227,"B/P":0.178,"E/P":0.145,"성장":0.200,"ROE":0.100,"모멘텀":0.150},
 "제안A(밸류0.38)":{"배당":0.157,"B/P":0.123,"E/P":0.101,"성장":0.321,"ROE":0.139,"모멘텀":0.159},
 "제안B(보수)":  {"배당":0.172,"B/P":0.135,"E/P":0.110,"성장":0.351,"ROE":0.152,"모멘텀":0.080},
}

def build():
    px,rets=load_px();mcap=load_mcap()
    EPS=load_fin("EPS");PER=load_fin("PER");PBR=load_fin("PBR");BPS=load_fin("BPS");DIV=load_fin("DIV")
    idx=[m for m in EPS.index if m in rets.index and m in mcap.index and m>="2003-01"]
    cols=px.columns; al=lambda df: df.reindex(index=idx,columns=cols)
    EPS,PER,PBR,BPS,DIV=al(EPS),al(PER),al(PBR),al(BPS),al(DIV)
    RET=rets.reindex(index=idx,columns=cols);MC=mcap.reindex(index=idx,columns=cols);PX=px.reindex(index=idx,columns=cols)
    ep=1.0/PER.where(PER>0);bp=1.0/PBR.where(PBR>0);dy=DIV.where(DIV>=0)
    roe=(EPS/BPS).where(BPS>0); g1=(EPS/EPS.shift(12)-1).where(EPS.shift(12)>0).clip(-1,3)
    mom=(PX.shift(1)/PX.shift(12)-1)
    F={"배당":dy,"B/P":bp,"E/P":ep,"성장":g1,"ROE":roe,"모멘텀":mom}
    univ=(MC.rank(axis=1,ascending=False)<=200)
    return dict(idx=idx,cols=cols,univ=univ,fwd=RET.shift(-1),F=F)

def composite_ls(D,weights):
    """가중 합성스코어의 IC·롱숏 시계열."""
    idx=D["idx"];univ=D["univ"];fwd=D["fwd"]
    # 월별 z 사전계산
    Z={k:pd.DataFrame(index=idx,columns=D["cols"],dtype=float) for k in weights}
    for t in idx:
        u=univ.loc[t]
        for k in weights:
            Z[k].loc[t]=zc(D["F"][k].loc[t].where(u))
    ics={};ls={}
    for t in idx[:-1]:
        u=univ.loc[t]
        valid=sum(Z[k].loc[t].notna().astype(int) for k in weights)>=3
        score=sum(weights[k]*Z[k].loc[t].fillna(0) for k in weights).where(u & valid)
        f=score.dropna(); r=fwd.loc[t]; f=f[[c for c in f.index if pd.notna(r.get(c))]]
        if len(f)<50: continue
        ics[t]=spearman(f,r[f.index])
        q=pd.qcut(f.rank(method="first"),5,labels=False,duplicates="drop")
        if pd.Series(q).nunique()<5: continue
        ls[t]=r[f.index[q==4]].mean()-r[f.index[q==0]].mean()
    return pd.Series(ics).dropna(), pd.Series(ls).dropna()

def mdd(ls):
    """롱숏 누적수익 기준 최대낙폭(%)."""
    cum=(1+ls).cumprod(); peak=cum.cummax(); dd=cum/peak-1
    return float(dd.min()*100)

def stats(ic,ls):
    icm=ic.mean(); ic_t=icm/(ic.std()/np.sqrt(len(ic)))
    sh=ls.mean()/ls.std()*np.sqrt(12) if ls.std()>0 else np.nan
    return dict(meanIC=round(float(icm),4),ic_t=round(float(ic_t),2),
                ls_ann=round(float(ls.mean()*12*100),1),ls_sharpe=round(float(sh),2),
                hit=round(float((ls>0).mean()*100),0),mdd=round(mdd(ls),1),n=len(ls))

BASEW={"배당":0.049,"B/P":0.037,"E/P":0.030,"성장":0.020,"ROE":0.018}  # 현행 비모멘텀부(밸류 앵커)
def scheme_with_mom(m):
    """현행 밸류 앵커 비중을 (1-m)로 정규화 + 모멘텀 m."""
    s=sum(BASEW.values()); w={k:v/s*(1-m) for k,v in BASEW.items()}; w["모멘텀"]=m; return w

def run():
    D=build()
    valw={"배당":1/3,"B/P":1/3,"E/P":1/3,"성장":0,"ROE":0,"모멘텀":0}
    _,val_ls=composite_ls(D,valw)
    bad=set(val_ls[val_ls<0].index)
    def line(name,s):
        print(f"  {name:<18}{s['meanIC']:>+8.4f}{s['ic_t']:>7.2f}{s['ls_ann']:>+8.1f}%{s['ls_sharpe']:>8.2f}{s['hit']:>5.0f}%{s['mdd']:>+8.1f}%{s['bad_regime_mean_pct']:>+15.3f}%")
    def evalw(w):
        ic,ls=composite_ls(D,w); s=stats(ic,ls)
        bad_m=[ls[t] for t in ls.index if t in bad]
        s["bad_regime_mean_pct"]=round(float(np.mean(bad_m))*100,3) if bad_m else float("nan")
        return s
    print("="*98);print("가중 개편 백테 — 합성스코어 분위수 롱숏 (2003~2026 · top200)");print("="*98)
    print(f"  밸류 부진기: {len(bad)}개월(밸류 롱숏<0) / 전체 {len(val_ls)}개월  ← 이때 방어가 관건\n")
    hdr=f"  {'가중안':<18}{'평균IC':>8}{'IC t':>7}{'롱숏연%':>9}{'Sharpe':>8}{'승률':>6}{'MDD':>8}{'밸류부진기월평균':>15}"
    # ── 모멘텀 투입량 스캔(밸류 앵커 유지) ──
    print("【모멘텀 투입량 스캔 · 현행 밸류믹스 유지 + 모멘텀 m】"); print(hdr)
    scan={}
    for m in [0.0,0.10,0.15,0.20,0.25,0.30,0.35,0.40]:
        s=evalw(scheme_with_mom(m)); scan[m]=s; line(f"모멘텀 {int(m*100)}%",s)
    best_m=max(scan,key=lambda k: scan[k]["ls_sharpe"])
    print(f"   → Sharpe 최대: 모멘텀 {int(best_m*100)}% (Sharpe {scan[best_m]['ls_sharpe']:.2f})")
    # ── 참고: 밸류 축소형(제안A/B) ──
    print("\n【참고 · 밸류 축소형(성장까지 크게 재배분)】"); print(hdr)
    OUTX={}
    for name,w in {"제안A(밸류0.38)":SCHEMES["제안A(밸류0.38)"],"제안B(보수)":SCHEMES["제안B(보수)"]}.items():
        s=evalw(w); OUTX[name]=s; line(name,s)

    base=scan[0.0]; bm=scan[best_m]
    print("\n  ── 개편 효과 (Sharpe최대 모멘텀안 vs 현행 모멘텀0%) ──")
    print(f"   Sharpe {base['ls_sharpe']:.2f}→{bm['ls_sharpe']:.2f} ({bm['ls_sharpe']-base['ls_sharpe']:+.2f}) · "
          f"MDD {base['mdd']:.1f}%→{bm['mdd']:.1f}% ({bm['mdd']-base['mdd']:+.1f}%p) · "
          f"밸류부진기 {base['bad_regime_mean_pct']:+.2f}%→{bm['bad_regime_mean_pct']:+.2f}%/월")
    print("\n  ⚠️ 과거통계·미래보장 아님. 비용·슬리피지 미반영(롱숏 총액). 모멘텀 단독신호 약함→헤지 목적. 투자자문 아님·책임 본인.")
    json.dump(dict(n_bad=len(bad),n_all=len(val_ls),
                   mom_scan={f"{int(k*100)}%":v for k,v in scan.items()},
                   best_mom=f"{int(best_m*100)}%",value_reduced=OUTX),
              open(os.path.join(BASE,"가중개편_백테_결과.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2,default=str)
    print("\n  저장: 가중개편_백테_결과.json")
    return dict(scan=scan,best_m=best_m,reduced=OUTX)

if __name__=="__main__":
    run()
