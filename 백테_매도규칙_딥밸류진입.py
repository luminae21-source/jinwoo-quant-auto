#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""백테_매도규칙_딥밸류진입.py — 매도규칙 겨루기, 단 진입=검증된 딥밸류바닥

앞(백테_매도규칙_비교)은 광범위 추세시작 진입 → 목표익절 유리(평균회귀).
여기선 진우 검증 엣지 진입(딥밸류+과매도+턴)에 같은 매도규칙 적용 → 승자가 더 길게 달리는가?
매도규칙 6종 동일. 상폐반영. 신호효능·투자자문 아님·결정 본인.
사용: py 백테_매도규칙_딥밸류진입.py [--self-test]
"""
import os, sys, argparse
import numpy as np, pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
MAXH=24; HC=0.5
RULES=["보유24M","트레일-20%","트레일-30%","MA10이탈","목표+30%","손절+트레일"]

def simulate_entry(E, win, mawin):
    res={r:None for r in RULES}; peak=E; H=len(win)
    for h in range(H):
        p=win[h]
        if p!=p:
            lv=win[h-1] if h>0 else E
            for r in RULES:
                if res[r] is None: res[r]=(lv*(1-HC)/E-1,h)
            return res
        if p>peak: peak=p
        ma=mawin[h]; hh=h+1; last=(h==H-1)
        if res["보유24M"] is None and last: res["보유24M"]=(p/E-1,hh)
        if res["트레일-20%"] is None and (p<=peak*0.80 or last): res["트레일-20%"]=(p/E-1,hh)
        if res["트레일-30%"] is None and (p<=peak*0.70 or last): res["트레일-30%"]=(p/E-1,hh)
        if res["MA10이탈"] is None and ((ma==ma and p<ma) or last): res["MA10이탈"]=(p/E-1,hh)
        if res["목표+30%"] is None and (p>=E*1.30 or last): res["목표+30%"]=(p/E-1,hh)
        if res["손절+트레일"] is None and (p<=max(E*0.80,peak*0.70) or last): res["손절+트레일"]=(p/E-1,hh)
    return res

def load_pbr(idx,cols):
    fr=[]
    for mk in ("KOSPI","KOSDAQ"):
        p=os.path.join(HERE,f"종목재무_KRX_{mk}.csv")
        if os.path.exists(p):
            x=pd.read_csv(p,dtype={"code":str},encoding="utf-8-sig"); x.columns=[c.lstrip("﻿") for c in x.columns]
            fr.append(x[["date","code","PBR"]])
    d=pd.concat(fr,ignore_index=True); d["code"]=d["code"].str.zfill(6)
    d["m"]=pd.to_datetime(d["date"],errors="coerce").dt.to_period("M"); d["PBR"]=pd.to_numeric(d["PBR"],errors="coerce")
    d=d.dropna(subset=["m"])
    return d.pivot_table(index="m",columns="code",values="PBR",aggfunc="last").reindex(idx).reindex(columns=cols)

def run():
    d=pd.read_csv(os.path.join(HERE,"_m_all.csv"),header=None,names=["code","date","close"],dtype={"code":str})
    d["m"]=pd.to_datetime(d["date"],errors="coerce").dt.to_period("M"); d["close"]=pd.to_numeric(d["close"],errors="coerce")
    d=d.dropna(subset=["m","close"])
    px=d.pivot_table(index="m",columns="code",values="close",aggfunc="last").sort_index()
    pbr=load_pbr(px.index,px.columns)
    ma10=px.rolling(10).mean(); disp=px/ma10; ret1=px.pct_change()
    valid=px.notna()&(px>=1000)&ma10.notna()&(pbr>0)&pbr.notna()
    pr=pbr.where(valid).rank(axis=1,pct=True)
    entry=(valid&(pr<=0.2)&(disp<0.85)&(ret1>0))  # 딥밸류+과매도+턴
    V=px.values; M=ma10.values; EN=entry.values; T=len(px.index)
    acc={r:[] for r in RULES}; holds={r:[] for r in RULES}
    for j in range(V.shape[1]):
        col=V[:,j]; mc=M[:,j]; en=EN[:,j]
        for t in range(10,T-1):
            if not en[t]: continue
            E=col[t]
            hi=min(t+MAXH,T-1); win=col[t+1:hi+1]; maw=mc[t+1:hi+1]
            if len(win)==0: continue
            r=simulate_entry(E,win,maw)
            for k,v in r.items():
                if v is not None: acc[k].append(v[0]); holds[k].append(v[1])
    out={"기간":f"{px.index.min()}~{px.index.max()}","진입수":len(acc['보유24M'])}
    for r in RULES:
        a=np.array(acc[r]); h=np.array(holds[r])
        if len(a)==0: out[r]=None; continue
        mean=float(a.mean()); ann=(1+mean)**(12/max(h.mean(),1))-1
        out[r]=dict(n=len(a),mean=round(mean,4),median=round(float(np.median(a)),4),
                    win=round(float((a>0).mean()),3),big=round(float((a>=0.5).mean()),3),
                    bigloss=round(float((a<=-0.3).mean()),3),hold=round(float(h.mean()),1),ann=round(ann,4))
    return out

def _fmt(o):
    print(f"\n{'='*94}\n매도규칙 비교 · 진입=딥밸류바닥(저PBR+과매도+턴) · {o['기간']} · 진입 {o['진입수']:,}건\n{'='*94}")
    print(f"  {'매도규칙':<14}{'평균수익':>9}{'중앙':>8}{'승률':>7}{'대박+50%':>9}{'큰손실-30%':>10}{'보유월':>7}{'연율화':>8}")
    for r in ["보유24M","트레일-30%","손절+트레일","트레일-20%","MA10이탈","목표+30%"]:
        s=o.get(r)
        if not s: continue
        print(f"  {r:<14}{s['mean']*100:>+8.1f}%{s['median']*100:>+7.1f}%{s['win']*100:>6.0f}%{s['big']*100:>8.0f}%{s['bigloss']*100:>9.0f}%{s['hold']:>7.1f}{s['ann']*100:>+7.1f}%")
    print("\n※ 진우 검증 엣지(딥밸류바닥) 진입 기준. 광범위 추세시작(백테_매도규칙_비교)과 대조.")

def _self_test():
    r=simulate_entry(100.0,np.array([130,160,120,120]),np.array([100,110,120,120]))
    ok = (r["목표+30%"][0]>=0.29 and r["트레일-30%"][0] is not None)
    print(f"  [{'OK' if ok else 'FAIL'}] 딥밸류진입 시뮬"); print(f"\n셀프테스트: {1 if ok else 0}/1"); return ok

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--self-test",action="store_true"); a=ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    _fmt(run()); return 0
if __name__=="__main__": sys.exit(main())
