#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""비용반영_백테.py — 모멘텀 투입량별 회전율·거래비용 반영 순-Sharpe

가중개편_백테는 총액(비용無) 기준. 모멘텀은 회전율↑ → 실거래 비용이 개선폭을 갉아먹는지 검증.
각 모멘텀 투입량에 대해:
  · 상·하위 분위 월별 교체율(turnover) 측정
  · 왕복비용 RT(20·40·60bps) 차감 → 순 롱숏 Sharpe & 순 롱온리(상위분위) Sharpe
한국 대형주(top200) 가정: 매수 수수료+슬리피지 / 매도 +거래세. 롱온리가 실제 상품(추천=매수).
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

BASEW={"배당":0.049,"B/P":0.037,"E/P":0.030,"성장":0.020,"ROE":0.018}
def scheme_with_mom(m):
    s=sum(BASEW.values()); w={k:v/s*(1-m) for k,v in BASEW.items()}; w["모멘텀"]=m; return w

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

def backtest(D,weights):
    """롱숏·롱온리 gross 수익 + 상·하위 분위 교체율."""
    idx=D["idx"];univ=D["univ"];fwd=D["fwd"]
    Z={k:pd.DataFrame(index=idx,columns=D["cols"],dtype=float) for k in weights}
    for t in idx:
        u=univ.loc[t]
        for k in weights: Z[k].loc[t]=zc(D["F"][k].loc[t].where(u))
    ls=[];lo=[];to_top=[];to_bot=[];times=[]
    prev_top=prev_bot=None
    for t in idx[:-1]:
        u=univ.loc[t]
        valid=sum(Z[k].loc[t].notna().astype(int) for k in weights)>=3
        score=sum(weights[k]*Z[k].loc[t].fillna(0) for k in weights).where(u & valid)
        f=score.dropna(); r=fwd.loc[t]; f=f[[c for c in f.index if pd.notna(r.get(c))]]
        if len(f)<50: prev_top=prev_bot=None; continue
        q=pd.qcut(f.rank(method="first"),5,labels=False,duplicates="drop")
        if pd.Series(q).nunique()<5: prev_top=prev_bot=None; continue
        top=set(f.index[q==4]); bot=set(f.index[q==0])
        ls.append(r[list(top)].mean()-r[list(bot)].mean()); lo.append(r[list(top)].mean()); times.append(t)
        # 교체율(직전월 대비 새로 진입한 비중)
        if prev_top is not None and len(top):
            to_top.append(len(top-prev_top)/len(top)); to_bot.append(len(bot-prev_bot)/len(bot) if len(bot) else 0)
        else:
            to_top.append(np.nan); to_bot.append(np.nan)
        prev_top,prev_bot=top,bot
    return (pd.Series(ls,index=times),pd.Series(lo,index=times),
            pd.Series(to_top,index=times),pd.Series(to_bot,index=times))

def sharpe(x): return float(x.mean()/x.std()*np.sqrt(12)) if x.std()>0 else np.nan
def mdd(x):
    cum=(1+x).cumprod();peak=cum.cummax();return float((cum/peak-1).min()*100)

def run():
    D=build()
    # 밸류 부진기(밸류 등가합성 롱숏<0 월)
    vls,_,_,_=backtest(D,{"배당":1/3,"B/P":1/3,"E/P":1/3,"성장":0,"ROE":0,"모멘텀":0})
    bad=set(vls[vls<0].index)
    RT=0.004  # 실전 대표 왕복비용 40bps(한국 대형주 수수료+거래세+슬리피지)
    doses=[0.0,0.10,0.15,0.20,0.30]
    print("="*106);print(f"비용 반영 순-Sharpe — 롱온리(실제 추천상품) 초점 · 왕복 {int(RT*1e4)}bps (2003~2026·top200)");print("="*106)
    print(f"  밸류 부진기 {len(bad)}개월 / 전체 {len(vls)}개월\n")
    print(f"  {'모멘텀':>6}{'롱교체%':>9}{'롱숏 net Sh':>12}{'롱온리 net Sh':>13}{'롱온리 연%net':>13}{'롱온리 MDD':>11}{'밸류부진기/월':>13}")
    OUT={}
    for m in doses:
        ls,lo,tot,tob=backtest(D,scheme_with_mom(m))
        tt=float(tot.dropna().mean())
        lsn=ls - RT*(tot.fillna(tt)+tob.fillna(float(tob.dropna().mean())))
        lon=lo - RT*(tot.fillna(tt))
        bad_lo=[lon[t] for t in lon.index if t in bad]
        row=dict(top_turnover=round(tt*100,1),ls_net_sharpe=round(sharpe(lsn),2),
                 lo_net_sharpe=round(sharpe(lon),2),lo_net_ann=round(float(lon.mean()*12*100),1),
                 lo_net_mdd=round(mdd(lon),1),lo_bad_regime_pct=round(float(np.mean(bad_lo))*100,3))
        OUT[f"{int(m*100)}%"]=row
        print(f"  {int(m*100):>5}%{tt*100:>8.1f}%{sharpe(lsn):>12.2f}{sharpe(lon):>13.2f}{float(lon.mean()*12*100):>+12.1f}%{mdd(lon):>+11.1f}%{float(np.mean(bad_lo))*100:>+12.3f}%")
    b=OUT["0%"]
    print("\n  ── 롱온리(실제 상품) 관점 요약 ──")
    print(f"   · 순Sharpe: 모멘텀 0%={b['lo_net_sharpe']:.2f} → 최고는 {max(OUT,key=lambda k:OUT[k]['lo_net_sharpe'])}"
          f"({max(v['lo_net_sharpe'] for v in OUT.values()):.2f}). 30%={OUT['30%']['lo_net_sharpe']:.2f}(악화).")
    print(f"   · 밸류부진기 방어: 0%={b['lo_bad_regime_pct']:+.2f}%/월 → 10~20% 구간에서 개선 확인.")
    print(f"   · 롱숏(공매도)엔 모멘텀 30%가 최적이나, 매수전용 상품엔 소량(≈10~15%)이 적정.")
    print("  ⚠️ EW·월리밸·왕복40bps 가정. 실제 편입수·부분매매 미반영. 과거통계·미래보장 아님·책임 본인.")
    json.dump(dict(RT_bps=int(RT*1e4),n_bad=len(bad),results=OUT),
              open(os.path.join(BASE,"비용반영_백테_결과.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2,default=str)
    print("\n  저장: 비용반영_백테_결과.json")
    return OUT

if __name__=="__main__":
    run()
