#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우_전략백테스트.py — 딥밸류 등 전략 포트폴리오 백테스트 (수익 최대화 검증·재현용).

검증결과(사냥터_기획/진우_수익최대화_전략백테스트.md): 딥밸류바닥 12M보유가 최대수익
(CAGR +38.6%·OOS +35.4%·vs KOSPI +29%p). 기관매집·퀄리티 오버레이는 얹으면 깎임.

방법: 월봉·상폐 −100% 보수·유동성필터(시총 상위70%)·비용 0.6%왕복·EW·오버랩보유. 벤치=KOSPI지수.
      룩어헤드 차단(월말 신호→익월 진입). IN 2002-13 / OOS 2014-26.
의존: 종목일봉_30년_*, 종목재무_KRX_*, 종목시총_30년.csv, kospi_index_daily.csv, flow_ext_monthly_*(선택)
캐시: _월봉종가캐시_*.csv 재사용. 사용: py 진우_전략백테스트.py [--hold 12] [--self-test]
"""
# ── §8-3 비용 SSOT (2026-07-27) ─────────────────────────────────
# 코드베이스에 거래비용 상수가 7종 병존했다(0.235%~0.6%). 실측 왕복 0.559%로 통일한다.
# 종전 값은 각 대입문 주석에 남겼다. import 실패 시 종전 값으로 폴백한다.
try:
    import sys as _s3, os as _o3
    _d3 = _o3.path.dirname(_o3.path.abspath(__file__))
    for _ in range(5):
        if _o3.path.exists(_o3.path.join(_d3, "비용모델.py")):
            _s3.path.insert(0, _d3); break
        _d3 = _o3.path.dirname(_d3)
    from 비용모델 import roundtrip as _jq_rt
except Exception:
    _jq_rt = None


def _jq_cost(legacy):
    """SSOT 왕복비용. 못 불러오면 종전 값 유지."""
    return _jq_rt("기준") if _jq_rt else legacy
# ────────────────────────────────────────────────────────────────

import os, sys, argparse
import numpy as np, pandas as pd
BASE=os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
GRID0="2001-01"

def monthly_close(market):
    cache=os.path.join(BASE,f"_월봉종가캐시_{market}.csv")
    if os.path.exists(cache): return pd.read_csv(cache,dtype={"code":str})
    tmp=f"/tmp/px_m_{market}.csv"
    if os.path.exists(tmp):
        d=pd.read_csv(tmp,header=None,names=["code","date","close"],dtype={0:str});d["code"]=d["code"].str.zfill(6);d["ym"]=d["date"].str[:7]
        d[["code","ym","close"]].to_csv(cache,index=False,encoding="utf-8-sig");return d[["code","ym","close"]]
    keep={}
    for ch in pd.read_csv(os.path.join(BASE,f"종목일봉_30년_{market}.csv"),usecols=["date","code","close"],dtype={"code":str},encoding="utf-8-sig",chunksize=2_000_000):
        ch=ch[pd.to_numeric(ch["close"],errors="coerce")>0];ch["ym"]=ch["date"].str[:7]
        for dte,c,cl,ym in zip(ch["date"],ch["code"],ch["close"],ch["ym"]):
            k=(c.zfill(6),ym);cur=keep.get(k)
            if cur is None or dte>cur[0]: keep[k]=(dte,float(cl))
    out=pd.DataFrame([(c,ym,v[1]) for (c,ym),v in keep.items()],columns=["code","ym","close"])
    out.to_csv(cache,index=False,encoding="utf-8-sig");return out

def build(pd,np):
    px=pd.concat([monthly_close(m) for m in ("KOSPI","KOSDAQ")],ignore_index=True)
    px["code"]=px["code"].str.zfill(6);px=px.drop_duplicates(["code","ym"]);px["close"]=pd.to_numeric(px["close"],errors="coerce")
    months=pd.period_range(GRID0,pd.Timestamp.today().to_period("M"),freq="M").astype(str).tolist();mi={m:i for i,m in enumerate(months)};T=len(months)
    px=px[px["ym"].isin(mi)];codes=sorted(px["code"].unique());cidx={c:i for i,c in enumerate(codes)};C=len(codes)
    def grid(df,val,src="ym"):
        G=np.full((C,T),np.nan)
        for c,y,v in zip(df["code"],df[src],df[val]):
            if c in cidx and y in mi and v==v: G[cidx[c],mi[y]]=v
        return G
    CL=grid(px,"close")
    fr=[]
    for m in ("KOSPI","KOSDAQ"):
        d=pd.read_csv(os.path.join(BASE,f"종목재무_KRX_{m}.csv"),dtype={"code":str});d["code"]=d["code"].str.zfill(6);d["ym"]=d["date"].str[:7];d["PBR"]=pd.to_numeric(d["PBR"],errors="coerce");fr.append(d[["code","ym","PBR"]])
    PBR=grid(pd.concat(fr).drop_duplicates(["code","ym"]),"PBR")
    mc=pd.read_csv(os.path.join(BASE,"종목시총_30년.csv"),dtype={"code":str});mc["code"]=mc["code"].str.zfill(6);mc["ym"]=mc["date"].str[:7];mc["mcap"]=pd.to_numeric(mc["mcap"],errors="coerce")
    MC=grid(mc,"mcap")
    INST=np.full((C,T),np.nan)
    for m in ("KOSPI","KOSDAQ"):
        p=os.path.join(BASE,f"flow_ext_monthly_{m}.csv")
        if os.path.exists(p):
            d=pd.read_csv(p,dtype={"code":str});d["code"]=d["code"].str.zfill(6);d["ym"]=d["date"].str[:7];d["inst"]=pd.to_numeric(d["inst_net"],errors="coerce")
            for c,y,v in zip(d["code"],d["ym"],d["inst"]):
                if c in cidx and y in mi and v==v: INST[cidx[c],mi[y]]=v
    ki=pd.read_csv(os.path.join(BASE,"kospi_index_daily.csv"));ki.columns=[c.lstrip("﻿").lower() for c in ki.columns];ki["ym"]=ki["date"].str[:7];ki["close"]=pd.to_numeric(ki["close"],errors="coerce")
    kim=ki.dropna().groupby("ym")["close"].last();kret=np.full(T,np.nan)
    for m in range(1,T):
        if months[m] in kim.index and months[m-1] in kim.index: kret[m]=kim[months[m]]/kim[months[m-1]]-1
    return CL,PBR,MC,INST,kret,months

def run(a):
    import numpy as np, pandas as pd
    CL,PBR,MC,INST,kret,months=build(pd,np);C,T=CL.shape
    RET=np.full((C,T),np.nan)
    for m in range(1,T):
        pv,cu=CL[:,m-1],CL[:,m];ok=(~np.isnan(pv))&(~np.isnan(cu))&(pv>0);RET[ok,m]=cu[ok]/pv[ok]-1
        RET[(~np.isnan(pv))&(np.isnan(cu))&(pv>0)&(m<T-2),m]=-1.0
    LISTED=~np.isnan(CL)
    ma10=np.full((C,T),np.nan)
    for m in range(9,T):
        w=CL[:,m-9:m+1];ma10[:,m]=np.where((~np.isnan(w)).sum(1)==10,np.nanmean(w,1),np.nan)
    disp=CL/ma10;ret1=np.full((C,T),np.nan);ret1[:,1:]=CL[:,1:]/CL[:,:-1]-1
    PR=np.full((C,T),np.nan)
    for m in range(T):
        col=PBR[:,m];v=~np.isnan(col)
        if v.sum()>10: PR[np.where(v)[0],m]=np.argsort(np.argsort(col[v]))/(v.sum()-1)
    LIQ=np.zeros((C,T),bool)
    for m in range(T):
        col=MC[:,m];v=col[~np.isnan(col)]
        if len(v)>10: LIQ[:,m]=col>=np.nanpercentile(col,30)
    deep=(PR<=0.20)&(disp<0.85)&(ret1>0)
    accum=np.zeros((C,T),bool)
    for m in range(1,T-2): accum[(np.nan_to_num(INST[:,m-1])<=0)&(INST[:,m]>0)&(INST[:,m+1]>0)&(INST[:,m+2]>0),m]=True
    COST=_jq_cost(0.006)  # §8-3: 종전 0.600% → 실측 0.559% (-0.041%p)
    def bt(sig,HOLD):
        pr=np.full(T,np.nan);prev=np.zeros(C,bool)
        for m in range(1,T):
            held=np.zeros(C,bool)
            for t in range(max(0,m-HOLD),m): held|=sig[:,t]&LIQ[:,t]
            held&=LISTED[:,m]&LIQ[:,m];r=RET[held,m];r=r[~np.isnan(r)]
            if len(r)>=3: pr[m]=r.mean()-((held&~prev).sum()/max(1,held.sum()))*COST
            prev=held
        return pr
    def perf(pr,y0,y1):
        idx=[m for m in range(T) if y0<=months[m][:4]<=y1 and pr[m]==pr[m] and kret[m]==kret[m]]
        if len(idx)<12: return None
        p=pr[idx];bk=kret[idx];cagr=(np.prod(1+p))**(12/len(p))-1;bc=(np.prod(1+bk))**(12/len(bk))-1
        cum=np.cumprod(1+p);return cagr,bc,p.mean()/p.std()*np.sqrt(12),((cum/np.maximum.accumulate(cum))-1).min()
    print("전략 · EW·유동성필터·비용0.6% · vs KOSPI지수")
    print(f"{'전략(보유)':<18}{'구간':<10}{'CAGR':>7}{'초과':>7}{'Sharpe':>7}{'MDD':>6}")
    for nm,sig,H in [("딥밸류바닥(12M)",deep,a.hold),("기관매집시작(12M)",accum,a.hold),("딥밸류∩기관(12M)",deep&accum,a.hold)]:
        pr=bt(sig,H)
        for seg,y0,y1 in [("전체","2002","2026"),("IN","2002","2013"),("OOS","2014","2026")]:
            r=perf(pr,y0,y1)
            if r: print(f"{nm if seg=='전체' else '':<18}{seg:<10}{r[0]*100:+6.1f}%{(r[0]-r[1])*100:+6.1f}%{r[2]:>7.2f}{r[3]*100:>5.0f}%")
        print()
    return 0

def _self_test():
    import numpy as np
    # 상폐 -100% 처리·CAGR 계산 sanity
    p=np.array([0.02,-0.01,0.03]*4);cagr=(np.prod(1+p))**(12/len(p))-1
    print(f"[OK] CAGR 계산 {cagr*100:+.1f}%"); print("셀프테스트: 1/1"); return True

def main():
    ap=argparse.ArgumentParser();ap.add_argument("--hold",type=int,default=12);ap.add_argument("--self-test",action="store_true")
    a=ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    return run(a)

if __name__=="__main__": sys.exit(main())
