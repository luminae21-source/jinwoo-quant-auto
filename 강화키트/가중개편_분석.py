#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""가중개편_분석.py — 멀티팩터 가중 개편 근거: 축별 상관·Sharpe → 분산 인지 가중

문제: 현 multifactor_screen 가중(배당0.049+B/P0.037+E/P0.030+성장0.020+ROE0.018)은
      밸류(배당+E/P+B/P)=0.116/0.154=75%로 편중. 밸류 3팩터는 롱숏 상관 0.65(사실상 한 베팅).
개편: 밸류를 '1블록'으로 묶어 축(밸류·성장·퀄리티·모멘텀·사이즈)으로 재구성하고,
      축별 Sharpe·상관을 근거로 분산 인지 가중 산출.
2003~2026 · top200 · 상폐포함 · 룩어헤드X. ⚠️ 정보용·투자자문 아님·책임 본인.
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
BASE = os.path.dirname(os.path.abspath(__file__)); UP = _jqroot2()
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
def _find(fn):
    for d in (BASE, os.path.dirname(BASE), UP, os.path.join(UP,"강화키트"), os.getcwd()):
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

def build():
    px,rets=load_px();mcap=load_mcap()
    EPS=load_fin("EPS");PER=load_fin("PER");PBR=load_fin("PBR");BPS=load_fin("BPS");DIV=load_fin("DIV")
    idx=[m for m in EPS.index if m in rets.index and m in mcap.index and m>="2003-01"]
    cols=px.columns; al=lambda df: df.reindex(index=idx,columns=cols)
    EPS,PER,PBR,BPS,DIV=al(EPS),al(PER),al(PBR),al(BPS),al(DIV)
    RET=rets.reindex(index=idx,columns=cols);MC=mcap.reindex(index=idx,columns=cols);PX=px.reindex(index=idx,columns=cols)
    ep=1.0/PER.where(PER>0);bp=1.0/PBR.where(PBR>0);dy=DIV.where(DIV>=0)
    roe=(EPS/BPS).where(BPS>0); g1=(EPS/EPS.shift(12)-1).where(EPS.shift(12)>0).clip(-1,3)
    mom=(PX.shift(1)/PX.shift(12)-1); size=-np.log(MC.where(MC>0))
    univ=(MC.rank(axis=1,ascending=False)<=200)
    # 밸류 블록 = 배당·E/P·B/P 등가중 z 합성
    val=pd.DataFrame(index=idx,columns=cols,dtype=float)
    for t in idx:
        u=univ.loc[t]; zs=[zc(dy.loc[t].where(u)),zc(ep.loc[t].where(u)),zc(bp.loc[t].where(u))]
        cnt=sum(z.notna().astype(int) for z in zs); s=sum(z.fillna(0) for z in zs)
        val.loc[t]=s.where(cnt>=2)
    AX={"밸류(합성)":val,"성장(EPS YoY)":g1,"퀄리티(ROE)":roe,"모멘텀(12-1)":mom,"사이즈(소형)":size}
    subval={"배당":dy,"E/P":ep,"B/P":bp}
    return dict(idx=idx,cols=cols,univ=univ,fwd=RET.shift(-1),AX=AX,subval=subval)

def ls_series(D,fac):
    fwd=D["fwd"];out={}
    for t in D["idx"][:-1]:
        u=D["univ"].loc[t];r=fwd.loc[t]
        f=fac.loc[t].where(u).dropna(); f=f[[c for c in f.index if pd.notna(r.get(c))]]
        if len(f)<40: continue
        try: q=pd.qcut(f.rank(method="first"),5,labels=False,duplicates="drop")
        except Exception: continue
        if pd.Series(q).nunique()<5: continue
        out[t]=r[f.index[q==4]].mean()-r[f.index[q==0]].mean()
    return pd.Series(out)
def ic_series(D,fac):
    out=[]
    for t in D["idx"][:-1]:
        u=D["univ"].loc[t]; ic=spearman(fac.loc[t].where(u),D["fwd"].loc[t])
        if pd.notna(ic): out.append(ic)
    return pd.Series(out)

def run():
    D=build(); names=list(D["AX"].keys())
    LS={n:ls_series(D,D["AX"][n]) for n in names}
    stats={}
    for n in names:
        ls=LS[n]; ic=ic_series(D,D["AX"][n])
        sh=ls.mean()/ls.std()*np.sqrt(12) if ls.std()>0 else 0
        stats[n]=dict(meanIC=round(float(ic.mean()),4),ic_t=round(float(ic.mean()/(ic.std()/np.sqrt(len(ic)))),2),
                      ls_ann=round(float(ls.mean()*12*100),1),sharpe=round(float(sh),2))
    L=pd.concat(LS,axis=1).dropna(); C=L.corr()
    print("="*92);print(f"축별 효력·상관 (2003~2026 · {len(L)}개월 · top200)");print("="*92)
    print(f"\n{'축':<16}{'평균IC':>9}{'IC t':>7}{'롱숏연%':>9}{'Sharpe':>8}")
    for n in names:
        v=stats[n];print(f"{n:<16}{v['meanIC']:>+9.4f}{v['ic_t']:>7.2f}{v['ls_ann']:>+8.1f}%{v['sharpe']:>8.2f}")
    print("\n[축간 롱숏 월수익 상관]");print(C.round(2).to_string())

    # ----- 가중 산출 -----
    # 현행(implied): 밸류 0.116·성장 0.020·ROE 0.018·모멘텀 0·사이즈 0 → 정규화
    cur={"밸류(합성)":0.116,"성장(EPS YoY)":0.020,"퀄리티(ROE)":0.018,"모멘텀(12-1)":0.0,"사이즈(소형)":0.0}
    tot=sum(cur.values()); cur={k:v/tot for k,v in cur.items()}
    # 제안A: Sharpe 비례(음수0) — 밸류가 1축이라 자동 상한
    pos={n:max(stats[n]["sharpe"],0) for n in names}; sA=sum(pos.values())
    propA={n:pos[n]/sA for n in names}
    # 제안B: Sharpe/평균상관 (분산 인지 — 남과 덜 겹칠수록 가중↑)
    avgcorr={n:(C.loc[n].drop(n).clip(lower=0).mean()) for n in names}
    adj={n:max(stats[n]["sharpe"],0)/(1+avgcorr[n]) for n in names}; sB=sum(adj.values())
    propB={n:adj[n]/sB for n in names}
    print("\n[가중 비교] (정규화·합1.0)")
    print(f"  {'축':<16}{'현행':>8}{'제안A':>9}{'제안B':>9}{'평균상관':>9}")
    for n in names:
        print(f"  {n:<16}{cur[n]*100:>7.1f}%{propA[n]*100:>8.1f}%{propB[n]*100:>8.1f}%{avgcorr[n]:>9.2f}")
    print(f"  {'밸류 비중':<16}{cur['밸류(합성)']*100:>7.1f}%{propA['밸류(합성)']*100:>8.1f}%{propB['밸류(합성)']*100:>8.1f}%")

    # 밸류 내부 하위가중(IC 비례·배당 앵커)
    sv={}
    for n,f in D["subval"].items():
        ic=ic_series(D,f); sv[n]=max(ic.mean(),0)
    ssv=sum(sv.values()); subw={n:sv[n]/ssv for n in sv}
    print("\n[밸류 블록 내부 하위가중 · IC비례]")
    for n in D["subval"]: print(f"  {n:<6}{subw[n]*100:>6.1f}%")

    # 제안B를 배당/E/P/B/P 개별로 환산(멀티팩터_screen WEIGHTS 대체용)
    vb=propB["밸류(합성)"]
    final={ "배당":round(vb*subw["배당"],3),"B/P":round(vb*subw["B/P"],3),"E/P":round(vb*subw["E/P"],3),
            "성장":round(propB["성장(EPS YoY)"],3),"ROE":round(propB["퀄리티(ROE)"],3),
            "모멘텀":round(propB["모멘텀(12-1)"],3),"사이즈":round(propB["사이즈(소형)"],3)}
    print("\n[개편 WEIGHTS 제안 · 제안B 기준 · multifactor_screen 교체용]")
    print("  WEIGHTS =",json.dumps(final,ensure_ascii=False))
    json.dump(dict(stats=stats,corr=C.round(3).to_dict(),current=cur,propA=propA,propB=propB,
                   subval=subw,final_weights=final),
              open(os.path.join(BASE,"가중개편_결과.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2,default=str)
    print("\n  저장: 가중개편_결과.json")
    return dict(stats=stats,C=C,cur=cur,propA=propA,propB=propB,subw=subw,final=final,months=len(L),avgcorr=avgcorr)

if __name__=="__main__":
    run()
