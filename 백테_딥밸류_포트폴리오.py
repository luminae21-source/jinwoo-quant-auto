#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""백테_딥밸류_포트폴리오.py — 공백 #2: 딥밸류바닥 분산 포트폴리오 (체결형 근사)

신호효능(백테_딥밸류_전기간검증)을 '실제로 굴리면?'으로: 상폐반영(−50%)+유동성필터+실체결비용.
핵심 검증: ①분산 종목수(N)를 늘리면 낙폭이 줄어드나 ②장기보유(승자 미절단)가 포트폴리오에서도 이기나.
결과(사냥터_기획/진우_딥밸류_포트폴리오검증.md): 1~3종=파산(MDD−97~100%), 10종+생존. N10·36M보유=CAGR+47%·Sharpe0.50(시장+7%·0.37).
[데이터 준비] LC_ALL=C awk로 월말 close·거래대금 추출(마운트 쓰기 느려 /tmp 권장):
  awk 'NR>1&&($6+0)>0{k=$2"|"substr($1,1,7);d[k]=$1;c[k]=$6;v[k]=$6*$7}END{for(k in c){split(k,a,"|");print a[1]","d[k]","c[k]","v[k]}}' 종목일봉_30년_{KOSPI,KOSDAQ}.csv
  → /tmp/_mq_all.csv (code,date,close,liq)
사용: py 백테_딥밸류_포트폴리오.py   (기본 /tmp/_mq_all.csv + 마운트 PBR)
투자자문 아님·결정 본인.
"""
import os,sys,numpy as np,pandas as pd
MNT=os.path.dirname(os.path.abspath(__file__)); MQ=os.environ.get("MQ","/tmp/_mq_all.csv")
CB,CS=0.0015,0.0033; HC=0.5; LIQMIN=5e8; DEEP=0.2; EXT=0.85
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def metrics(rets):
    e=np.cumprod(1+np.array(rets)); n=len(rets)
    if n<2: return None
    cagr=e[-1]**(12/n)-1; mdd=float((e/np.maximum.accumulate(e)-1).min())
    sh=float(np.mean(rets)/(np.std(rets)+1e-9)*np.sqrt(12))
    roll=(1+pd.Series(rets)).rolling(12).apply(np.prod,raw=True)-1
    return dict(CAGR=cagr,MDD=mdd,Sharpe=sh,worst12=float(roll.min()) if roll.notna().any() else float('nan'))

def load():
    d=pd.read_csv(MQ,header=None,names=["code","date","close","liq"],dtype={"code":str})
    d["m"]=pd.to_datetime(d["date"],errors="coerce").dt.to_period("M")
    d["close"]=pd.to_numeric(d["close"],errors="coerce"); d["liq"]=pd.to_numeric(d["liq"],errors="coerce")
    d=d.dropna(subset=["m","close"])
    px=d.pivot_table(index="m",columns="code",values="close",aggfunc="last").sort_index()
    liq=d.pivot_table(index="m",columns="code",values="liq",aggfunc="last").reindex_like(px)
    fr=[]
    for mk in ("KOSPI","KOSDAQ"):
        x=pd.read_csv(f"{MNT}/종목재무_KRX_{mk}.csv",dtype={"code":str},encoding="utf-8-sig"); x.columns=[c.lstrip("﻿") for c in x.columns]
        fr.append(x[["date","code","PBR"]])
    p=pd.concat(fr,ignore_index=True); p["code"]=p["code"].str.zfill(6)
    p["m"]=pd.to_datetime(p["date"],errors="coerce").dt.to_period("M"); p["PBR"]=pd.to_numeric(p["PBR"],errors="coerce")
    p=p.dropna(subset=["m"])
    pbr=p.pivot_table(index="m",columns="code",values="PBR",aggfunc="last").reindex(px.index).reindex(columns=px.columns)
    return px,liq,pbr

def run(px,liq,pbr,N,H):
    ma10=px.rolling(10).mean(); disp=px/ma10; ret1=px.pct_change()
    valid=px.notna()&(px>=1000)&ma10.notna()&(pbr>0)&pbr.notna()&(liq>=LIQMIN)
    pr=pbr.where(valid).rank(axis=1,pct=True)
    REB=(valid&(pr<=DEEP)&(disp<EXT)&(ret1>0)).values
    V=px.values; R1=ret1.values; T=len(px.index); ncol=px.shape[1]
    hold={}; rets=[]
    for t in range(12,T):
        s=0.0; dead=[]
        for c,et in hold.items():
            p1=V[t,c]
            if p1==p1 and p1>0: s+=(V[t,c]/V[t-1,c]-1)
            else: s+=(-HC); dead.append(c)
        port=s/N; exits=0
        for c in list(hold.keys()):
            if c in dead or (t-hold[c]>=H): del hold[c]; exits+=1
        entries=0
        if len(hold)<N:
            cand=[j for j in range(ncol) if REB[t,j] and j not in hold]
            cand.sort(key=lambda j: R1[t,j] if R1[t,j]==R1[t,j] else -9, reverse=True)
            for j in cand:
                if len(hold)>=N: break
                hold[j]=t; entries+=1
        port-=(entries*CB+exits*CS)/N; rets.append(port)
    return metrics(rets)

def main():
    if not os.path.exists(MQ): print(f"[없음] {MQ} — docstring 데이터 준비 먼저"); return 2
    px,liq,pbr=load()
    print(f"딥밸류바닥 분산 포트폴리오 · {px.index.min()}~{px.index.max()} · 거래대금≥{LIQMIN/1e8:.0f}억·비용15/33bp·상폐−50%")
    print("① 분산효과(보유12M):"); print(f"  {'N':<6}{'CAGR':>8}{'MDD':>9}{'최악12M':>9}{'Sharpe':>8}")
    for N in (1,3,5,10,20,40):
        m=run(px,liq,pbr,N,12); print(f"  {N:<6}{m['CAGR']*100:>+7.1f}%{m['MDD']*100:>+8.1f}%{m['worst12']*100:>+8.1f}%{m['Sharpe']:>8.2f}")
    print("② 보유기간효과(10종):"); print(f"  {'H(월)':<6}{'CAGR':>8}{'MDD':>9}{'Sharpe':>8}")
    for H in (12,24,36):
        m=run(px,liq,pbr,10,H); print(f"  {H:<6}{m['CAGR']*100:>+7.1f}%{m['MDD']*100:>+8.1f}%{m['Sharpe']:>8.2f}")
    print("\n결론: 분산 필수(1종−100%→10종생존) · 장기보유가 이긴다(N10·36M CAGR+47%·Sharpe0.50 vs 시장+7%/0.37).")
    print("한계: 선택면 PBR 생존편향 잔존·슬리피지/세금 별도·MDD−74% 감내 전제.")
    return 0
if __name__=="__main__": sys.exit(main())
