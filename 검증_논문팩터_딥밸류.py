#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""검증_논문팩터_딥밸류.py — 미검증 논문 아이디어를 딥밸류에 엄격 검증(월봉 IN/OOS + 포트CAGR).

대상: (1)E/P 이익수익률 게이트  (2)비유동성 프리미엄 역검증  (3)에코 모멘텀(t-12~t-7)  (4)52주 신저가 근접도
기준: 개별 12M(상폐-100%) + 포트폴리오 CAGR IN(2002-13)/OOS(2014-25). 신호효능 근사·투자자문 아님.
의존: /tmp/mats.npz (없으면 진우_전략백테스트.py 캐시 후 생성) · 종목재무_KRX_*(PER/EPS).
사용: py 검증_논문팩터_딥밸류.py
"""
import os,sys,numpy as np,pandas as pd
BASE=os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except: pass
d=np.load("/tmp/mats.npz",allow_pickle=True) if os.path.exists("/tmp/mats.npz") else np.load(os.path.join(BASE,"_mats.npz"),allow_pickle=True)
CL,PBR,MC=d["CL"],d["PBR"],d["MC"];months=list(d["months"]);codes=list(d["codes"]);C,T=CL.shape
mi={m:i for i,m in enumerate(months)};ci={c:i for i,c in enumerate(codes)}
lastv=np.full(C,-1)
for i in range(C):
    w=np.where(~np.isnan(CL[i]))[0]
    if len(w): lastv[i]=w[-1]
# PER→E/P
PER=np.full((C,T),np.nan)
for m in ("KOSPI","KOSDAQ"):
    p=os.path.join(BASE,f"종목재무_KRX_{m}.csv")
    if os.path.exists(p):
        x=pd.read_csv(p,dtype={"code":str});x["code"]=x["code"].str.zfill(6);x["ym"]=x["date"].str[:7]
        x["PER"]=pd.to_numeric(x["PER"],errors="coerce")
        for c,y,v in zip(x["code"],x["ym"],x["PER"]):
            if c in ci and y in mi and v==v and v>0: PER[ci[c],mi[y]]=v
EP=np.where(PER>0,1.0/PER,np.nan)
# 파생
ma=np.full((C,T),np.nan)
for m in range(9,T):
    w=CL[:,m-9:m+1];ma[:,m]=np.where((~np.isnan(w)).sum(1)==10,np.nanmean(w,1),np.nan)
disp=CL/ma;ret1=np.full((C,T),np.nan);ret1[:,1:]=CL[:,1:]/CL[:,:-1]-1
# 에코 t-12~t-7
echo=np.full((C,T),np.nan)
for m in range(12,T): echo[:,m]=CL[:,m-7]/CL[:,m-12]-1
# 52주(12M) 최저 근접도 = 현재/최근12M최저
low12=np.full((C,T),np.nan)
for m in range(12,T):
    w=CL[:,m-12:m+1];low12[:,m]=np.where((~np.isnan(w)).sum(1)>=10,np.nanmin(w,1),np.nan)
prox=CL/low12
def prank(A):
    R=np.full((C,T),np.nan)
    for m in range(T):
        col=A[:,m];v=~np.isnan(col)
        if v.sum()>10: R[np.where(v)[0],m]=np.argsort(np.argsort(col[v]))/(v.sum()-1)
    return R
PR=prank(PBR);EPR=prank(EP);MCR=prank(MC)
LIQ=np.zeros((C,T),bool)
for m in range(T):
    mc=MC[:,m];vv=mc[~np.isnan(mc)]
    if len(vv)>10: LIQ[:,m]=mc>=np.nanpercentile(mc,30)
# forward 12M, 상폐 -100%
f12=np.full((C,T),np.nan)
for m in range(T-1):
    tgt=m+12
    if tgt>=T: continue
    al=np.where(~np.isnan(CL[:,m]))[0]
    ok=~np.isnan(CL[al,tgt])
    f12[al[ok],m]=CL[al[ok],tgt]/CL[al[ok],m]-1
    for i in al[~ok]:
        if m<=lastv[i]<tgt: f12[i,m]=-1.0
# 월간 수익(포트CAGR용)
mret=np.full((C,T),np.nan)
for m in range(1,T):
    al=np.where(~np.isnan(CL[:,m-1]))[0]
    ok=~np.isnan(CL[al,m]);mret[al[ok],m]=CL[al[ok],m]/CL[al[ok],m-1]-1
    for i in al[~ok]:
        if m-1==lastv[i]: mret[i,m]=-1.0
yr=np.array([int(m[:4]) for m in months])
def stat(mask):
    v=f12[mask&(~np.isnan(f12))]
    if len(v)<20: return "n<20"
    return f"n={len(v):>5} 중{np.median(v)*100:>+4.0f}% 평{np.mean(v)*100:>+4.0f}% 승{(v>0).mean()*100:>3.0f}% 대박{(v>=1).mean()*100:>3.0f}%"
def inoos(mask):
    out=[]
    for lab,y0,y1 in [("ALL",2002,2025),("IN",2002,2013),("OOS",2014,2025)]:
        sg=np.zeros((C,T),bool);sg[:,(yr>=y0)&(yr<=y1)]=True
        out.append(f"{lab} {stat(mask&sg)}")
    return out
def portcagr(sigfn,hold=12):
    sig=sigfn()
    active=[];w=1.0;peak=1.0;mdd=0.0;wl={}
    logs=[]
    for m in range(T):
        rets=[];keep=[]
        for(em,i,h) in active:
            r=mret[i,m] if not np.isnan(mret[i,m]) else 0.0;rets.append(r)
            if h+1<hold and m!=lastv[i]: keep.append((em,i,h+1))
        active=keep
        pr=np.mean(rets) if rets else 0.0;w*=(1+pr)
        for i in np.where(sig[:,m])[0]: active.append((m,i,0))
        peak=max(peak,w);mdd=min(mdd,w/peak-1);logs.append((months[m],pr))
    def seg(y0,y1):
        ww=1.0;n=0
        for ym,pr in logs:
            if y0<=int(ym[:4])<=y1: ww*=(1+pr);n+=1
        return (ww**(12/n)-1)*100 if n else float("nan")
    avgn=np.mean([sig[:,m].sum() for m in range(T)])
    return seg(2002,2025),seg(2002,2013),seg(2014,2025),mdd*100,avgn
base=(PR<=0.20)&(disp<0.85)&(ret1>0)&LIQ
print("="*70);print("기준 딥밸류(저PBR20%∩이격<0.85∩턴∩유동성)");
for s in inoos(base): print("  "+s)
a,i,o,md,n=portcagr(lambda:base);print(f"  포트CAGR ALL{a:+.1f}% IN{i:+.1f}% OOS{o:+.1f}% MDD{md:.0f}% 월신호{n:.1f}")

print("\n[1] E/P 이익수익률 게이트")
for lab,extra in [("저PBR만(기준)",base),("저E/P만(저PER20%)",(EPR>=0.80)&(disp<0.85)&(ret1>0)&LIQ),
                  ("저PBR∩저E/P",base&(EPR>=0.80)),("저PBR∪저E/P",((PR<=0.20)|(EPR>=0.80))&(disp<0.85)&(ret1>0)&LIQ)]:
    a,i,o,md,n=portcagr(lambda e=extra:e)
    print(f"  {lab:<16} 포트CAGR IN{i:+.1f}%/OOS{o:+.1f}% MDD{md:.0f}% 월{n:.1f} | 개별 "+inoos(extra)[2])

print("\n[2] 비유동성 프리미엄 (유동성 필터 역검증)")
deep_nofilter=(PR<=0.20)&(disp<0.85)&(ret1>0)
for lab,extra in [("유동성필터有(기준)",base),("필터無(전종목)",deep_nofilter)]:
    a,i,o,md,n=portcagr(lambda e=extra:e)
    print(f"  {lab:<16} 포트CAGR IN{i:+.1f}%/OOS{o:+.1f}% MDD{md:.0f}% 월{n:.1f}")
# 딥밸류 내 시총 3분위(작을수록 비유동)
di,dm=np.where(base&(~np.isnan(f12)))
mcr=np.array([MCR[a,b] for a,b in zip(di,dm)]);fv=np.array([f12[a,b] for a,b in zip(di,dm)])
q=np.nanpercentile(mcr,[33,67]);g=np.digitize(mcr,q)
for k,gl in enumerate(["소형(비유동)","중형","대형(유동)"]):
    mk=g==k
    if mk.sum()>20: print(f"    {gl:<12} 12M 중{np.median(fv[mk])*100:>+4.0f}% 평{np.mean(fv[mk])*100:>+4.0f}% 승{(fv[mk]>0).mean()*100:>3.0f}%")

print("\n[3] 에코 모멘텀 t-12~t-7 (딥밸류 내)")
di,dm=np.where(base&(~np.isnan(echo))&(~np.isnan(f12)))
ec=np.array([echo[a,b] for a,b in zip(di,dm)]);fv=np.array([f12[a,b] for a,b in zip(di,dm)])
for lab,mk in [("에코+(추세생존)",ec>0),("에코-(추세죽음)",ec<=0)]:
    print(f"  {lab:<14} 12M 중{np.median(fv[mk])*100:>+4.0f}% 평{np.mean(fv[mk])*100:>+4.0f}% 승{(fv[mk]>0).mean()*100:>3.0f}% 대박{(fv[mk]>=1).mean()*100:>3.0f}% n={mk.sum()}")
a,i,o,md,n=portcagr(lambda:base&(echo>0));print(f"  포트[딥∩에코+] IN{i:+.1f}%/OOS{o:+.1f}% MDD{md:.0f}% 월{n:.1f}")

print("\n[4] 52주 신저가 근접도 (딥밸류 내, prox=현재/12M최저)")
di,dm=np.where(base&(~np.isnan(prox))&(~np.isnan(f12)))
px=np.array([prox[a,b] for a,b in zip(di,dm)]);fv=np.array([f12[a,b] for a,b in zip(di,dm)])
q=np.nanpercentile(px,[33,67]);g=np.digitize(px,q)
for k,gl in enumerate(["신저가근접(하)","중","저점서멀다(상)"]):
    mk=g==k
    if mk.sum()>20: print(f"  {gl:<14} 12M 중{np.median(fv[mk])*100:>+4.0f}% 평{np.mean(fv[mk])*100:>+4.0f}% 승{(fv[mk]>0).mean()*100:>3.0f}% 대박{(fv[mk]>=1).mean()*100:>3.0f}%")
print("\n판정기준: 다른 오버레이처럼 OOS 부호유지+CAGR 유지해야 채택. IN만 좋으면 기각.")
