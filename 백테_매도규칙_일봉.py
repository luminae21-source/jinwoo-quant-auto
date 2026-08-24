#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""백테_매도규칙_일봉.py — 매도규칙 일봉 정밀 검증 (딥밸류바닥 진입)

월봉(백테_매도규칙_딥밸류진입)은 intraday 휩쏘를 지워 트레일을 과대평가. 일봉으로 정밀화.
결론: 딥밸류바닥 진입엔 타이트 스톱=독(휩쏘), 보유(안팜)+분산이 최적. → 매도규칙서 §9.

[데이터 준비] (일봉 추출은 마운트 쓰기가 느려 /tmp 로컬 사용 권장)
  1) 진입목록: 백테_매도규칙_딥밸류진입.py의 entry 로직으로 _dv_entries.csv(code,date), _dv_codes.txt 생성
  2) 일봉추출: LC_ALL=C awk -f _extract.awk _dv_codes.txt 종목일봉_30년_{KOSPI,KOSDAQ}.csv
     (_extract.awk: NR==FNR{keep[$1]=1;next} FNR>1&&($2 in keep){print $1","$2","$4","$5","$6})
     → _dv_daily.csv (date,code,high,low,close)
  3) py 백테_매도규칙_일봉.py  (기본 /tmp/_dv_daily.csv, /tmp/_dv_entries.csv 읽음)
검증결과: 사냥터_기획/진우_매도규칙_검증.md. 신호효능·투자자문 아님·결정 본인.
"""
import os, sys, numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
DAILY=os.environ.get("DVDAILY","/tmp/_dv_daily.csv"); ENT=os.environ.get("DVENT","/tmp/_dv_entries.csv")
MAXD=504; HC=0.5
RULES=["보유(안팜)","트레일20%","트레일30%","ATR2.5","ATR3.5","고정손절25%","고정손절33%","목표+30%"]

def sim(hi,lo,cl,atr,E,s,end):
    peak=E; res={r:None for r in RULES}
    for i in range(s,end+1):
        h=hi[i]; l=lo[i]; c=cl[i]; a=atr[i]; last=(i==end); hh=i-s+1
        if h>peak: peak=h
        if res["보유(안팜)"] is None and last: res["보유(안팜)"]=(c/E-1,hh)
        for lab,x in (("트레일20%",.20),("트레일30%",.30)):
            if res[lab] is None:
                lv=peak*(1-x)
                if l<=lv: res[lab]=(lv/E-1,hh)
                elif last: res[lab]=(c/E-1,hh)
        for lab,k in (("ATR2.5",2.5),("ATR3.5",3.5)):
            if res[lab] is None:
                lv=peak-k*a
                if l<=lv and lv>0: res[lab]=(lv/E-1,hh)
                elif last: res[lab]=(c/E-1,hh)
        for lab,x in (("고정손절25%",.25),("고정손절33%",.33)):
            if res[lab] is None:
                if l<=E*(1-x): res[lab]=(-x,hh)
                elif last: res[lab]=(c/E-1,hh)
        if res["목표+30%"] is None:
            if h>=E*1.30: res["목표+30%"]=(0.30,hh)
            elif last: res["목표+30%"]=(c/E-1,hh)
    return res

def main():
    if not (os.path.exists(DAILY) and os.path.exists(ENT)):
        print(f"[없음] {DAILY} 또는 {ENT} — docstring의 데이터 준비 단계를 먼저 실행"); return 2
    d=pd.read_csv(DAILY,header=None,names=["date","code","high","low","close"],dtype={"code":str})
    d["dt"]=pd.to_datetime(d["date"],errors="coerce")
    for c in ("high","low","close"): d[c]=pd.to_numeric(d[c],errors="coerce")
    d=d.dropna(subset=["dt","close"]).sort_values(["code","dt"])
    gmax=d["dt"].max(); G={}
    for code,g in d.groupby("code",sort=False):
        hi=g["high"].values; lo=g["low"].values; cl=g["close"].values
        pc=np.concatenate([[cl[0]],cl[:-1]]); tr=np.maximum(hi-lo,np.maximum(np.abs(hi-pc),np.abs(lo-pc)))
        atr=pd.Series(tr).rolling(14,min_periods=1).mean().values
        G[code]=(g["dt"].values,hi,lo,cl,atr,g["dt"].values[-1])
    ent=pd.read_csv(ENT,dtype={"code":str}); ent["dt"]=pd.to_datetime(ent["date"],errors="coerce")
    acc={r:[] for r in RULES}; hold={r:[] for r in RULES}
    for code,ed in zip(ent["code"].tolist(),ent["dt"].values):
        if code not in G: continue
        dts,hi,lo,cl,atr,lastdt=G[code]; idx=int(np.searchsorted(dts,ed))
        if idx>=len(dts)-1: continue
        E=cl[idx]
        if E<=0: continue
        s=idx+1; end=min(s+MAXD,len(cl)-1); r=sim(hi,lo,cl,atr,E,s,end)
        recent=(lastdt>=gmax-np.timedelta64(15,'D'))
        if not recent and end==len(cl)-1:
            for k in RULES:
                if r[k] and r[k][1]==(end-s+1): r[k]=(cl[end]*(1-HC)/E-1,r[k][1])
        for k,v in r.items():
            if v is not None: acc[k].append(v[0]); hold[k].append(v[1])
    print(f"\n일봉 매도규칙 · 딥밸류바닥 {len(acc['보유(안팜)']):,}건 · 30년·상폐반영")
    print(f"  {'규칙':<14}{'평균':>8}{'중앙':>8}{'승률':>7}{'대박50':>8}{'큰손실':>8}{'보유일':>7}")
    for r in RULES:
        a=np.array(acc[r]); h=np.array(hold[r])
        if len(a)==0: continue
        print(f"  {r:<14}{a.mean()*100:>+7.1f}%{np.median(a)*100:>+7.1f}%{(a>0).mean()*100:>6.0f}%{(a>=0.5).mean()*100:>7.0f}%{(a<=-0.3).mean()*100:>7.0f}%{h.mean():>7.0f}")
    print("\n결론: 딥밸류바닥엔 타이트 스톱=휩쏘(대박포착 급감). 보유+분산이 최적. → 매도규칙서 §9.")
    return 0
if __name__=="__main__": sys.exit(main())
