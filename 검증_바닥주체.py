#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""검증_바닥주체.py — 바닥을 잡는 실제 주체 검증 (유형별).

질문(진우): "바닥 잡는 주체가 개인인가, 아니면 기타법인·연기금 등 특정 세력인가?
             그리고 그 주체가 '이기는 바닥'을 잡는가?"
방법: flow_detail_monthly_*(진우_수급세부_수집.py 산출)로 유형별 순매수를,
  ① 직전3M 주가국면별 순매수/시총 → 누가 하락을 받나
  ② 딥밸류바닥 진입월에 각 유형 순매수>0 여부 → 그 유형이 산 딥밸류가 더 반등하나(이기는 바닥)
데이터 없으면 기존 개인=−(기관+외국인) 역산으로 프리뷰.
사용: py 검증_바닥주체.py
"""
import os, sys, csv
import numpy as np, pandas as pd
BASE=os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def load_detail():
    dfs=[]
    for m in ("KOSPI","KOSDAQ"):
        p=os.path.join(BASE,f"flow_detail_monthly_{m}.csv")
        if os.path.exists(p):
            d=pd.read_csv(p,dtype={"code":str}); d["code"]=d["code"].str.zfill(6); d["ym"]=d["date"].str[:7]
            d["net"]=pd.to_numeric(d["net"],errors="coerce"); dfs.append(d[["code","ym","investor","net"]])
    return pd.concat(dfs,ignore_index=True) if dfs else None

def monthly_close():
    fr=[]
    for m in ("KOSPI","KOSDAQ"):
        c=os.path.join(BASE,f"_월봉종가캐시_{m}.csv")
        if os.path.exists(c): fr.append(pd.read_csv(c,dtype={"code":str}))
        elif os.path.exists(f"/tmp/px_m_{m}.csv"):
            d=pd.read_csv(f"/tmp/px_m_{m}.csv",header=None,names=["code","date","close"],dtype={0:str});d["code"]=d["code"].str.zfill(6);d["ym"]=d["date"].str[:7];fr.append(d[["code","ym","close"]])
        else: sys.exit(f"월봉 캐시 없음 → 진우_전략백테스트.py 먼저 1회 실행(캐시 생성)")
    d=pd.concat(fr);d["code"]=d["code"].str.zfill(6);d["close"]=pd.to_numeric(d["close"],errors="coerce")
    return d.drop_duplicates(["code","ym"])

def main():
    px=monthly_close()
    months=sorted(px["ym"].unique());mi={m:i for i,m in enumerate(months)}
    codes=sorted(px["code"].unique());ci={c:i for i,c in enumerate(codes)};C=len(codes);T=len(months)
    CL=np.full((C,T),np.nan)
    for c,y,v in zip(px["code"],px["ym"],px["close"]):
        if v==v: CL[ci[c],mi[y]]=v
    ret3=np.full((C,T),np.nan)
    for m in range(3,T): ret3[:,m]=CL[:,m]/CL[:,m-3]-1
    # mcap
    mc=pd.read_csv(os.path.join(BASE,"종목시총_30년.csv"),dtype={"code":str});mc["code"]=mc["code"].str.zfill(6);mc["ym"]=mc["date"].str[:7];mc["mcap"]=pd.to_numeric(mc["mcap"],errors="coerce")
    MC=np.full((C,T),np.nan)
    for c,y,v in zip(mc["code"],mc["ym"],mc["mcap"]):
        if c in ci and y in mi and v==v: MC[ci[c],mi[y]]=v
    det=load_detail()
    if det is None:
        print("⚠ flow_detail_monthly_* 없음 → 진우_수급세부_수집.py 먼저 실행(PC). 지금은 개인=−(기관+외국인) 역산 프리뷰.")
        fl=[]
        for m in ("KOSPI","KOSDAQ"):
            p=os.path.join(BASE,f"flow_ext_monthly_{m}.csv")
            if os.path.exists(p):
                d=pd.read_csv(p,dtype={"code":str});d["code"]=d["code"].str.zfill(6);d["ym"]=d["date"].str[:7]
                d["개인"]=-(pd.to_numeric(d["inst_net"],errors="coerce")+pd.to_numeric(d["foreign_net"],errors="coerce"))
                d["기관"]=pd.to_numeric(d["inst_net"],errors="coerce");d["외국인"]=pd.to_numeric(d["foreign_net"],errors="coerce")
                fl.append(d.melt(id_vars=["code","ym"],value_vars=["개인","기관","외국인"],var_name="investor",value_name="net"))
        det=pd.concat(fl,ignore_index=True)
    invs=list(det["investor"].unique())
    NET={iv:np.full((C,T),np.nan) for iv in invs}
    for c,y,iv,v in zip(det["code"],det["ym"],det["investor"],det["net"]):
        if c in ci and y in mi and v==v: NET[iv][ci[c],mi[y]]=v
    bins=[(-1,-0.2,"급락<−20%"),(-0.2,-0.05,"조정"),(-0.05,0.05,"보합"),(0.05,0.2,"상승"),(0.2,3,"급등>+20%")]
    print("\n① 직전3M 주가국면별 순매수/시총(%) · 양수=순매수(바닥 받음)")
    r=ret3[:,3:].ravel()
    for iv in invs:
        f=(NET[iv][:,3:]/np.where(MC[:,3:]>0,MC[:,3:],np.nan)).ravel()
        ok=(~np.isnan(r))&(~np.isnan(f));rr,ff=r[ok],f[ok]
        row=" ".join(f"{lab} {np.nanmean(ff[(rr>lo)&(rr<=hi)])*100:+.3f}" for lo,hi,lab in bins)
        print(f"  [{iv:<6}] {row}")
    # ② 딥밸류바닥 진입월에 각 유형 순매수>0 → 그 딥밸류가 더 반등하나
    ma10=np.full((C,T),np.nan)
    for m in range(9,T):
        w=CL[:,m-9:m+1];ma10[:,m]=np.where((~np.isnan(w)).sum(1)==10,np.nanmean(w,1),np.nan)
    disp=CL/ma10;ret1=np.full((C,T),np.nan);ret1[:,1:]=CL[:,1:]/CL[:,:-1]-1
    fr2=[]
    for m in ("KOSPI","KOSDAQ"):
        d=pd.read_csv(os.path.join(BASE,f"종목재무_KRX_{m}.csv"),dtype={"code":str});d["code"]=d["code"].str.zfill(6);d["ym"]=d["date"].str[:7];d["PBR"]=pd.to_numeric(d["PBR"],errors="coerce");fr2.append(d[["code","ym","PBR"]])
    fin=pd.concat(fr2).drop_duplicates(["code","ym"]);PBR=np.full((C,T),np.nan)
    for c,y,v in zip(fin["code"],fin["ym"],fin["PBR"]):
        if c in ci and y in mi and v==v: PBR[ci[c],mi[y]]=v
    PR=np.full((C,T),np.nan)
    for m in range(T):
        col=PBR[:,m];v=~np.isnan(col)
        if v.sum()>10: PR[np.where(v)[0],m]=np.argsort(np.argsort(col[v]))/(v.sum()-1)
    f12=np.full((C,T),np.nan)
    for m in range(T):
        if m+12<T: f12[:,m]=CL[:,m+12]/CL[:,m]-1
    deep=(PR<=0.20)&(disp<0.85)&(ret1>0)&(~np.isnan(f12))
    print("\n② 딥밸류바닥 진입월 유형별 순매수>0 여부 → 12M 반등 (이기는 바닥을 잡나)")
    di,dm=np.where(deep)
    base=np.nanmean(f12[deep])*100
    print(f"  딥밸류 전체 12M 평균 {base:+.1f}% (n={deep.sum()})")
    for iv in invs:
        buy=np.array([NET[iv][c,t]>0 for c,t in zip(di,dm)])
        fv=np.array([f12[c,t] for c,t in zip(di,dm)])
        b=fv[buy];nb=fv[~buy]
        if len(b)>20 and len(nb)>20:
            print(f"  [{iv:<6}] 순매수 종목 {np.mean(b)*100:+.1f}%(n={len(b)}) vs 순매도 {np.mean(nb)*100:+.1f}% → Δ{ (np.mean(b)-np.mean(nb))*100:+.1f}%p")
    # ③ 딥밸류 중 [유형]이 '던지는' 것 vs '사는' 것 (12M, IN/OOS) — 세력이 던지는 바닥이 더 센가
    from math import sqrt
    def segmask(y0,y1):
        idx=np.zeros((C,T),bool)
        for m in range(T):
            if y0<=months[m][:4]<=y1: idx[:,m]=True
        return idx
    def boot(a,b,n=4000):
        a=a[~np.isnan(a)];b=b[~np.isnan(b)]
        if len(a)<10 or len(b)<10: return (np.nan,np.nan)
        r=np.random.default_rng(1);z=r.choice(a,(n,len(a)),1).mean(1)-r.choice(b,(n,len(b)),1).mean(1)
        return (a.mean()-b.mean())*100,float(np.mean(z<=0))
    print("\n③ 딥밸류 중 [유형]이 던지는(순매도) vs 사는(순매수) → 12M · 던지는 바닥이 더 세면 역발상 강화신호")
    for iv in invs:
        hf=~np.isnan(NET[iv]);sellm=hf&(NET[iv]<0);buym=hf&(NET[iv]>0)
        for lab,y0,y1 in [("ALL","2002","2026"),("IN","2002","2013"),("OOS","2014","2026")]:
            sg=segmask(y0,y1)
            S=f12[deep&sellm&sg&(~np.isnan(f12))];Bu=f12[deep&buym&sg&(~np.isnan(f12))]
            if len(S)<20 or len(Bu)<20: continue
            dm,p=boot(S,Bu)
            print(f"  [{iv:<6}][{lab:<3}] 던지는딥 {np.nanmean(S)*100:+.1f}%(n{len(S)}) vs 사는딥 {np.nanmean(Bu)*100:+.1f}%(n{len(Bu)}) → 매도−매수 {dm:+.1f}p P(≤0)={p:.2f}")
        print()
    print("판정: ①급락 순매수(+)=바닥주체 · ②③ 어떤 유형이든 순매수 딥밸류가 덜 오르면 '이기는 바닥은 세력이 던지는 것'.")

if __name__=="__main__": main()
