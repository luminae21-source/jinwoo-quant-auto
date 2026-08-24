#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""백테_익절지점.py — 공백 #3: 적정가치 회귀 익절 정량화 (딥밸류바닥)

딥밸류는 평균회귀 전략 → "싸서 샀으니 안 싸지면 판다". 밸류/과열 익절이 3년 순수보유보다 나은지 검증.
결과(사냥터_기획/진우_익절지점_검증.md): 밸류익절은 스톱과 정반대(강함에 판다)라 유효.
  이격≥1.5·+100%·PBR≥1.0 익절 = 총수익 거의 유지 + 중앙 4배·대박포착 40~43%·자본효율 개선.
[데이터] /tmp/_m_all.csv (code,date,close 월말; awk로 추출) + 마운트 종목재무_KRX PBR.
사용: py 백테_익절지점.py   투자자문 아님·결정 본인.
"""
import numpy as np, pandas as pd
MNT="/sessions/upbeat-epic-bohr/mnt/진우퀀트"; MAXH=36; HC=0.5
d=pd.read_csv("/tmp/_m_all.csv",header=None,names=["code","date","close"],dtype={"code":str})
d["m"]=pd.to_datetime(d["date"],errors="coerce").dt.to_period("M"); d["close"]=pd.to_numeric(d["close"],errors="coerce")
d=d.dropna(subset=["m","close"])
px=d.pivot_table(index="m",columns="code",values="close",aggfunc="last").sort_index()
fr=[]
for mk in ("KOSPI","KOSDAQ"):
    x=pd.read_csv(f"{MNT}/종목재무_KRX_{mk}.csv",dtype={"code":str},encoding="utf-8-sig"); x.columns=[c.lstrip("﻿") for c in x.columns]
    fr.append(x[["date","code","PBR"]])
p=pd.concat(fr,ignore_index=True); p["code"]=p["code"].str.zfill(6)
p["m"]=pd.to_datetime(p["date"],errors="coerce").dt.to_period("M"); p["PBR"]=pd.to_numeric(p["PBR"],errors="coerce")
p=p.dropna(subset=["m"])
pbr=p.pivot_table(index="m",columns="code",values="PBR",aggfunc="last").reindex(px.index).reindex(columns=px.columns)
ma10=px.rolling(10).mean(); disp=px/ma10; ret1=px.pct_change()
valid=px.notna()&(px>=1000)&ma10.notna()&(pbr>0)&pbr.notna()
pr=pbr.where(valid).rank(axis=1,pct=True)
entry=(valid&(pr<=0.2)&(disp<0.85)&(ret1>0))
pbr_med=pbr.where(valid).median(axis=1)  # 그 달 시장 중앙 PBR
V=px.values; PB=pbr.values; DI=disp.values; MED=pbr_med.values
cols=list(px.columns); T=len(px.index)
en=entry.stack(); en=en[en].reset_index(); en.columns=["m","code","f"]
mi={m:i for i,m in enumerate(px.index)}; cimap={c:i for i,c in enumerate(cols)}
RULES=["보유36M","PBR≥1.0","PBR≥1.5","PBR≥2배","PBR≥시장중앙","이격≥1.3","이격≥1.5","목표+100%"]
acc={r:[] for r in RULES}; hold={r:[] for r in RULES}
for _,row in en.iterrows():
    t0=mi[row["m"]]; j=cimap[row["code"]]
    E=V[t0,j]; pbr0=PB[t0,j]
    if E!=E or E<=0 or pbr0!=pbr0: continue
    end=min(t0+MAXH,T-1); res={r:None for r in RULES}
    for t in range(t0+1,end+1):
        P=V[t,j]; last=(t==end); hh=t-t0
        if P!=P:  # 상폐
            lv=V[t-1,j]
            for r in RULES:
                if res[r] is None: res[r]=(lv*(1-HC)/E-1,hh)
            break
        pb=PB[t,j]; di=DI[t,j]; ret=P/E-1
        if res["보유36M"] is None and last: res["보유36M"]=(ret,hh)
        for lab,cond in (("PBR≥1.0",pb==pb and pb>=1.0),("PBR≥1.5",pb==pb and pb>=1.5),
                         ("PBR≥2배",pb==pb and pb>=2*pbr0),("PBR≥시장중앙",pb==pb and MED[t]==MED[t] and pb>=MED[t]),
                         ("이격≥1.3",di==di and di>=1.3),("이격≥1.5",di==di and di>=1.5),
                         ("목표+100%",P>=2*E)):
            if res[lab] is None:
                if cond: res[lab]=(ret,hh)
                elif last: res[lab]=(ret,hh)
    for k,v in res.items():
        if v is not None: acc[k].append(v[0]); hold[k].append(v[1])
print(f"익절 지점 검증 · 진입=딥밸류바닥 {len(acc['보유36M']):,}건 · 최대36M·상폐반영")
print(f"  {'익절규칙':<14}{'평균':>8}{'중앙':>8}{'승률':>7}{'대박50':>8}{'보유월':>7}{'연율화':>8}")
for r in RULES:
    a=np.array(acc[r]); h=np.array(hold[r])
    if len(a)==0: continue
    mean=a.mean(); ann=(1+mean)**(12/max(h.mean(),1))-1
    print(f"  {r:<14}{mean*100:>+7.1f}%{np.median(a)*100:>+7.1f}%{(a>0).mean()*100:>6.0f}%{(a>=0.5).mean()*100:>7.0f}%{h.mean():>7.1f}{ann*100:>+7.1f}%")
print("\n※ 평균=총수익 관점 · 연율화=자본효율(보유기간 환산) · 신호효능·결정 본인")
