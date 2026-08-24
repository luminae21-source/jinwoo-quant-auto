#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""ev_fcf_factor_test.py — EV/EBIT · EV/EBITDA · FCF수익률 팩터 효력 검정
재무상세_EBITDA.csv(DART) + 시총 + 월봉 결합, PIT 지연 적용, IC·분위수 롱숏.
기존 배당·B/P·E/P 와 같은 창·같은 유니버스에서 비교. ⚠️ 정보용·투자자문 아님·책임 본인.
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
BASE=os.path.dirname(os.path.abspath(__file__))
UP= _jqroot2()
def _find(fn):
    for d in (BASE, os.path.dirname(BASE), UP, os.path.join(UP,"강화키트")):
        p=os.path.join(d,fn)
        if os.path.exists(p): return p
    return None

# --- load monthly price returns ---
fr=[]
for f in ("_월봉종가캐시_KOSPI.csv","_월봉종가캐시_KOSDAQ.csv"):
    d=pd.read_csv(_find(f),dtype={"code":str}); d["code"]=d["code"].str.zfill(6); fr.append(d)
px=pd.concat(fr).pivot_table(index="ym",columns="code",values="close",aggfunc="last").sort_index()
rets=px.pct_change(fill_method=None).mask(lambda x:x.abs()>1.0)

# --- monthly mcap ---
mc=pd.read_csv(_find("종목시총_30년.csv"),dtype={"code":str}); mc["code"]=mc["code"].str.zfill(6)
mc["ym"]=pd.to_datetime(mc["date"]).dt.strftime("%Y-%m")
MC=mc.pivot_table(index="ym",columns="code",values="mcap",aggfunc="last").sort_index()

# --- market ratios (PER/PBR/DIV) monthly ---
def load_fin(field):
    fr=[]
    for f in ("종목재무_KRX_KOSPI.csv","종목재무_KRX_KOSDAQ.csv"):
        p=_find(f)
        if p:
            d=pd.read_csv(p,dtype={"code":str}); d["code"]=d["code"].str.zfill(6)
            d["ym"]=pd.to_datetime(d["date"]).dt.strftime("%Y-%m"); fr.append(d[["ym","code",field]])
    return pd.concat(fr).pivot_table(index="ym",columns="code",values=field,aggfunc="last").sort_index()
PER=load_fin("PER"); PBR=load_fin("PBR"); DIV=load_fin("DIV")

# --- DART fundamentals by fiscal year ---
fd=pd.read_csv(_find("재무상세_EBITDA.csv"),dtype={"code":str}); fd["code"]=fd["code"].str.zfill(6)
FY={}
for col in ("op_income","EBITDA","FCF","net_debt","depr"):
    FY[col]=fd.pivot_table(index="fiscal_year",columns="code",values=col,aggfunc="last")

def avail_fy(ym):
    y,m=int(ym[:4]),int(ym[5:7])
    return y-1 if m>=4 else y-2     # 사업보고서 3월말 공시 → 4월부터 반영

# --- build monthly factor panels aligned to price index ---
months=[m for m in rets.index if m>= "2021-04" and m in MC.index]
cols=px.columns
def fy_row(col, fy):
    return FY[col].loc[fy] if fy in FY[col].index else pd.Series(dtype=float)

ebit_ev={}; ebitda_ev={}; fcf_y={}; ep={}; bp={}; dy={}
for ym in months:
    fy=avail_fy(ym)
    mcap=MC.loc[ym].reindex(cols)
    oi=fy_row("op_income",fy).reindex(cols); eb=fy_row("EBITDA",fy).reindex(cols)
    fcf=fy_row("FCF",fy).reindex(cols); nd=fy_row("net_debt",fy).reindex(cols).fillna(0)
    dep=fy_row("depr",fy).reindex(cols)
    ev=mcap+nd
    ebit_ev[ym]=(oi/ev).where((ev>0)&oi.notna())
    ebitda_ev[ym]=(eb/ev).where((ev>0)&dep.notna())   # 감가상각 잡힌 종목만(진짜 EBITDA)
    fcf_y[ym]=(fcf/mcap).where((mcap>0)&fcf.notna())
    pr=PER.loc[ym].reindex(cols) if ym in PER.index else pd.Series(index=cols,dtype=float)
    pb=PBR.loc[ym].reindex(cols) if ym in PBR.index else pd.Series(index=cols,dtype=float)
    dv=DIV.loc[ym].reindex(cols) if ym in DIV.index else pd.Series(index=cols,dtype=float)
    ep[ym]=(1.0/pr.where(pr>0)); bp[ym]=(1.0/pb.where(pb>0)); dy[ym]=dv.where(dv>=0)
def toDF(d): return pd.DataFrame(d).T.reindex(index=months,columns=cols)
FAC={"EV/EBIT (EBIT/EV)":toDF(ebit_ev),"EV/EBITDA (EBITDA/EV)":toDF(ebitda_ev),
     "FCF수익률 (FCF/시총)":toDF(fcf_y),"E/P (이익수익률)":toDF(ep),
     "B/P (순자산)":toDF(bp),"배당수익률":toDF(dy)}
fwd=rets.shift(-1)

# universe: top200 mcap AND has DART data (op_income exists that month)
def test(F):
    ics=[];ls=[];ns=[]
    for ym in months[:-1]:
        mcap=MC.loc[ym].reindex(cols)
        univ=mcap.rank(ascending=False)<=200
        f=F.loc[ym].where(univ).dropna()
        r=fwd.loc[ym]
        f=f[[c for c in f.index if pd.notna(r.get(c))]]
        if len(f)<30: continue
        ics.append(f.rank().corr(r[f.index].rank()))
        q=pd.qcut(f.rank(method="first"),5,labels=False,duplicates="drop")
        if q.nunique()<5: continue
        ls.append(r[f.index[q==4]].mean()-r[f.index[q==0]].mean()); ns.append(len(f))
    ics=pd.Series(ics).dropna(); ls=pd.Series(ls).dropna()
    if len(ics)<12: return None
    mIC=ics.mean(); t=mIC/(ics.std()/np.sqrt(len(ics)))
    return dict(meanIC=round(mIC,4),ic_t=round(t,1),ls_ann=round(ls.mean()*12*100,1),
                ls_sharpe=round(ls.mean()/ls.std()*np.sqrt(12),2) if ls.std()>0 else None,
                ls_hit=round((ls>0).mean()*100,0),months=len(ics),avg_n=int(np.mean(ns)) if ns else 0)

res={k:test(F) for k,F in FAC.items()}
res={k:v for k,v in res.items() if v}
order=sorted(res.items(),key=lambda kv:-abs(kv[1]["meanIC"]))
print("="*104)
print(f"EV/EBIT·FCF 팩터 효력 — DART 재무 결합 (PIT지연·top200·룩어헤드X · {months[0]}~{months[-1]} {len(months)}개월)")
print("="*104)
print(f"  {'팩터':<24}{'평균IC':>9}{'IC t':>7}{'롱숏 연%':>10}{'Sharpe':>9}{'승률':>7}{'개월':>6}{'종목':>6}")
for k,v in order:
    sh = f"{v['ls_sharpe']:.2f}" if v['ls_sharpe'] is not None else "  -"
    print(f"  {k:<24}{v['meanIC']:>+9.4f}{v['ic_t']:>7.1f}{v['ls_ann']:>+9.1f}%{sh:>9}{v['ls_hit']:>6.0f}%{v['months']:>6}{v['avg_n']:>6}")
print("\n  · 부호: 양(+)=지표 높을수록(=쌀수록/현금흐름 좋을수록) 다음달 수익↑. IC>0.02·t>2면 유의.")
print("  · EV/EBITDA는 감가상각 잡힌 종목만(커버리지 낮음) → 참고. EV/EBIT·FCF가 주력.")
print("  ⚠️ 5년 창(2021~)·top200. 과거통계·미래보장 아님. 투자자문 아님·책임 본인.")
json.dump(dict(window=[months[0],months[-1]],n_months=len(months),results=res),
          open(os.path.join(BASE,"ev_fcf_factor_result.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2,default=str)
print("\n  저장: ev_fcf_factor_result.json")
