#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우_섹터스캔.py — 일봉 기반 섹터 전반 스캔 (딥밸류 바닥이 어느 섹터에 군집하나).

목적(정직): 섹터로 '상승폭 예측'은 불가(검증: IN/OOS 순위상관 ρ≈0, 진우_가바닥매수_섹터_검증.md).
따라서 이 스캔은 **모니터링용** — 지금 어느 섹터에 딥밸류 바닥 후보·과매도가 군집하는지(자금 배치 인식용),
'그 섹터가 더 오른다'는 예측이 아님. 분산·집중회피(동일섹터 2~3종 상한)와 함께 사용.

산출: 섹터별 유니버스수·딥밸류후보수·과매도%(이격<0.85)·턴%(20일>0)·중앙이격·52주저가근접%.
      진우_섹터스캔.csv + 콘솔(후보 군집 상위 섹터).
의존: 종목일봉_30년_*(또는 /tmp/dpx_*), 종목재무_KRX_*(PBR), 종목시총_30년.csv, liquidity_sector·kosdaq_industry.
사용: py 진우_섹터스캔.py    ※4시간봉 데이터 생기면 동일 로직을 4H 종가로 교체(설계 재사용).
"""
import os,sys,csv,glob
import numpy as np, pandas as pd
BASE=os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except: pass

def sector_map():
    sec={}
    for f in ("liquidity_sector.csv","kosdaq_industry.csv"):
        p=os.path.join(BASE,f)
        if not os.path.exists(p): continue
        for r in csv.DictReader(open(p,encoding="utf-8-sig")):
            r={k.lstrip("﻿"):v for k,v in r.items()}
            if r.get("code") and r.get("sector"): sec.setdefault(r["code"].zfill(6),r["sector"])
    return sec
def simplify(s):
    for k in ["이차전지","반도체","자동차","제지","철강","건설","증권","보험","은행","화학","섬유","조선","기계",
              "디스플레이","바이오","의약","식품","유통","운송","부동산","지주","전자부품","통신","소프트","게임",
              "화장품","의류","금속","기타 금융","상품 종합","전기","기계장비","금융 지원","의료","우주"]:
        if k in s: return k
    return s[:10]

def daily_closes():
    """최근 일봉 종가 딕셔너리 {code: np.array(close)} — dpx 캐시 우선, 없으면 원천."""
    frames=[]
    for mk in ("KOSPI","KOSDAQ"):
        c=f"/tmp/dpx_{mk}.csv"
        if os.path.exists(c):
            frames.append(pd.read_csv(c,header=None,names=["code","date","close"],dtype={"code":str}))
        else:
            for ch in pd.read_csv(os.path.join(BASE,f"종목일봉_30년_{mk}.csv"),usecols=["date","code","close"],
                                  dtype={"code":str},encoding="utf-8-sig",chunksize=2_000_000):
                ch=ch[ch["date"]>="2018-01-01"];frames.append(ch[["code","date","close"]])
    df=pd.concat(frames);df["code"]=df["code"].str.zfill(6)
    df["close"]=pd.to_numeric(df["close"],errors="coerce");df=df.dropna()
    # 최근 ~420거래일만(MA200 충분) → 대폭 경량화
    cutoff=sorted(df["date"].unique())[-420] if df["date"].nunique()>420 else df["date"].min()
    df=df[df["date"]>=cutoff].sort_values(["code","date"])
    asof=df["date"].max()
    out={}
    for c,v in df.groupby("code")["close"]:
        a=v.values
        if len(a)>=200: out[c]=a[-260:]
    return out,asof

def latest_pbr():
    fr=[]
    for mk in ("KOSPI","KOSDAQ"):
        d=pd.read_csv(os.path.join(BASE,f"종목재무_KRX_{mk}.csv"),dtype={"code":str})
        d["code"]=d["code"].str.zfill(6);d["PBR"]=pd.to_numeric(d["PBR"],errors="coerce")
        d=d[d["PBR"]>0];fr.append(d)
    d=pd.concat(fr);d=d.sort_values("date").groupby("code").tail(1)
    return dict(zip(d["code"],d["PBR"]))

def latest_mcap():
    m=pd.read_csv(os.path.join(BASE,"종목시총_30년.csv"),dtype={"code":str})
    m["code"]=m["code"].str.zfill(6);m["mcap"]=pd.to_numeric(m["mcap"],errors="coerce")
    m=m.dropna().sort_values("date").groupby("code").tail(1)
    return dict(zip(m["code"],m["mcap"]))

def main():
    sec=sector_map(); px,asof=daily_closes(); pbr=latest_pbr(); mc=latest_mcap()
    codes=[c for c in px if c in pbr]
    # PBR 백분위(하위=싸다)·유동성
    pv=np.array([pbr[c] for c in codes]); prank={c:r for c,r in zip(codes,np.argsort(np.argsort(pv))/(len(pv)-1))}
    mcv=np.array([mc.get(c,np.nan) for c in codes]); liqthr=np.nanpercentile(mcv[~np.isnan(mcv)],30)
    rows=[]
    for c in codes:
        v=px[c]; cur=v[-1]; ma200=v[-200:].mean(); ext=cur/ma200
        r20=cur/v[-21]-1 if len(v)>21 else np.nan
        prox=cur/v[-250:].min()
        liq=(not np.isnan(mc.get(c,np.nan))) and mc[c]>=liqthr
        deep=(prank[c]<=0.20) and (ext<0.85) and (r20>0) and liq
        rows.append((c,simplify(sec.get(c,"미분류")),prank[c],ext,r20,prox,liq,deep))
    df=pd.DataFrame(rows,columns=["code","sector","pbrpct","ext","r20","prox","liq","deep"])
    df=df[df["sector"]!="미분류"]
    agg=[]
    for s,g in df.groupby("sector"):
        gl=g[g["liq"]]
        if len(gl)<8: continue
        agg.append(dict(sector=s,n=len(gl),deep=int(gl["deep"].sum()),
            oversold=(gl["ext"]<0.85).mean()*100, turn=(gl["r20"]>0).mean()*100,
            medext=gl["ext"].median(), nearlow=(gl["prox"]<1.10).mean()*100,
            cheap=(gl["pbrpct"]<=0.20).mean()*100))
    a=pd.DataFrame(agg)
    # 바닥 군집 점수 = 딥후보밀도 + 과매도브레드스 (모니터링 지표, 예측 아님)
    a["bottom_score"]=(a["deep"]/a["n"]*100)*0.5 + a["oversold"]*0.3 + a["cheap"]*0.2
    a=a.sort_values("bottom_score",ascending=False)
    a.to_csv(os.path.join(BASE,"진우_섹터스캔.csv"),index=False,encoding="utf-8-sig")
    print(f"■ 진우 섹터 전반 스캔 (일봉 as-of {asof}) — 딥밸류 바닥이 군집하는 섹터")
    print("  ※예측 아님(섹터 IN/OOS 순위상관 ρ≈0). 자금배치·분산 인식용. 동일섹터 2~3종 상한 병행.")
    print(f"  {'섹터':<12}{'유동종목':>6}{'딥후보':>6}{'과매도%':>7}{'턴%':>6}{'중앙이격':>8}{'52wk저가근접%':>11}")
    for _,r in a.head(15).iterrows():
        print(f"  {r['sector']:<12}{int(r['n']):>6}{int(r['deep']):>6}{r['oversold']:>6.0f}%{r['turn']:>5.0f}%"
              f"{r['medext']:>8.2f}{r['nearlow']:>10.0f}%")
    tot_deep=int(df[df['liq']]['deep'].sum())
    print(f"\n  전체 딥밸류 바닥 후보 {tot_deep}종 · 강세장이면 소수(현 국면 확인). 상세: 진우_섹터스캔.csv")
    print("  → 후보가 여러 섹터에 흩어지면 분산 용이, 한 섹터 쏠리면 그 섹터 사이클 리스크(집중 주의).")

if __name__=="__main__": main()
