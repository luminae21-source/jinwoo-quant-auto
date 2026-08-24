#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""백테_딥밸류_PIT검증.py — 생존편향 제거 재검증 (상폐 포함 KOSPI PIT)

목적: 앞 신호연구(현재상장만·생존편향)의 반등군>트랩>시장 우위가, 상폐를 손실로 반영해도 살아남나?
데이터: kospi_pit_daily(2019~2026, 상폐 23종 포함) 월말 + 종목재무_KRX PBR. 2020코로나·2022 하락장 포함.
핵심: 선행수익 계산 시 종목이 기간 내 상장폐지되면 그 관측을 버리지 않고 **−100%(또는 마지막가)로 반영.**
      → '폭락장에 산 딥밸류가 망해서 사라진' 경우가 이제 수익에 정직하게 계산됨.
코호트: 딥밸류(PBR하위20%) · 반등군(딥밸류∩이격<0.85∩1M수익>0) · 트랩군(딥밸류∩역배열) · 시장(전체).
⚠️ KOSPI만·7년·483종(코스닥 PIT는 상폐 미포함이라 제외). 표본 작음. 투자자문 아님·결정 본인.
사용: py 백테_딥밸류_PIT검증.py [--self-test]
"""
import os, sys, argparse
import numpy as np, pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def load_price():
    d=pd.read_csv(os.path.join(HERE,"_pit_m.csv"),header=None,names=["code","date","close"],dtype={"code":str})
    d["code"]=d["code"].str.zfill(6); d["m"]=pd.to_datetime(d["date"],errors="coerce").dt.to_period("M")
    d["close"]=pd.to_numeric(d["close"],errors="coerce"); d=d.dropna(subset=["m","close"])
    return d.pivot_table(index="m",columns="code",values="close",aggfunc="last").sort_index()

def load_pbr(idx,cols):
    p=os.path.join(HERE,"종목재무_KRX_KOSPI.csv")
    x=pd.read_csv(p,dtype={"code":str},encoding="utf-8-sig"); x.columns=[c.lstrip("﻿") for c in x.columns]
    x["code"]=x["code"].str.zfill(6); x["m"]=pd.to_datetime(x["date"],errors="coerce").dt.to_period("M")
    x["PBR"]=pd.to_numeric(x["PBR"],errors="coerce"); x=x.dropna(subset=["m"])
    return x.pivot_table(index="m",columns="code",values="PBR",aggfunc="last").reindex(idx).reindex(columns=cols)

def fwd_return_delist_aware(px, h):
    """t시점 유효종목의 h개월 선행수익. 창 안에서 상폐(모두 NaN)면 -100%로 반영, 부분생존이면 마지막 유효가 사용."""
    V=px.values; T,N=V.shape; out=np.full((T,N),np.nan)
    for ti in range(T):
        base=V[ti]
        hi=min(ti+h, T-1)
        if hi<=ti: continue
        win=V[ti+1:hi+1]              # (h, N)
        for j in range(N):
            b=base[j]
            if not (b==b) or b<=0: continue
            col=win[:,j]; valid=col[~np.isnan(col)]
            if valid.size>0:
                out[ti,j]=valid[-1]/b-1        # 마지막 유효가(상폐면 상폐직전가)
            else:
                # t엔 살아있었는데 창 내내 데이터 없음 = 즉시 상폐 → 총손실 가정
                out[ti,j]=-1.0
    return pd.DataFrame(out,index=px.index,columns=px.columns)

def regime(idx):
    k=pd.read_csv(os.path.join(HERE,"kospi_index_daily.csv"),encoding="utf-8-sig"); k.columns=[c.lstrip("﻿").lower() for c in k.columns]
    k["m"]=pd.to_datetime(k["date"],errors="coerce").dt.to_period("M"); k["close"]=pd.to_numeric(k["close"],errors="coerce")
    km=k.dropna(subset=["m"]).groupby("m")["close"].last().sort_index()
    return (km>km.rolling(10).mean()).reindex(idx).ffill().fillna(False)

def summarize(fwd,mask):
    v=fwd.where(mask).values.ravel(); v=v[~np.isnan(v)]
    if len(v)==0: return dict(n=0,mean=np.nan,median=np.nan,hit=np.nan,loss=np.nan)
    return dict(n=int(len(v)),mean=round(float(np.mean(v)),4),median=round(float(np.median(v)),4),
                hit=round(float((v>0).mean()),3),loss=round(float((v<=-0.5).mean()),3))

def run():
    px=load_price(); idx=px.index; cols=px.columns
    pbr=load_pbr(idx,cols)
    ma3=px.rolling(3).mean(); ma10=px.rolling(10).mean()
    disp=px/ma10; ret1=px.pct_change(); order_dn=(px<ma3)&(ma3<ma10)
    valid=px.notna()&(px>=500)&ma10.notna()&(pbr>0)&pbr.notna()
    pr=pbr.where(valid).rank(axis=1,pct=True)
    deep=valid&(pr<=0.2); reb=deep&(disp<0.85)&(ret1>0); trap=deep&order_dn
    bull=regime(idx)
    bear=pd.DataFrame(np.repeat((~bull).values[:,None],px.shape[1],axis=1),index=idx,columns=cols)
    out={"기간":f"{idx.min()}~{idx.max()}","월수":len(idx),"종목수":px.shape[1]}
    for hz,h in (("6M",6),("12M",12)):
        fwd=fwd_return_delist_aware(px,h)
        for cn,cm in (("시장(전체)",valid),("딥밸류(전체)",deep),("반등군",reb),("트랩군",trap)):
            out[f"[{hz}·하락장] {cn}"]=summarize(fwd,cm&bear)
    return out

def _fmt(o):
    print(f"\n{'='*86}\n딥밸류 생존편향 제거 재검증(KOSPI PIT·상폐포함) · {o['기간']} ({o['월수']}M·{o['종목수']}종)\n{'='*86}")
    print("선행수익: n=표본 · mean/median · hit=플러스비율 · loss=−50%이하비율(상폐/폭락 포함)\n")
    for hz in ("6M","12M"):
        print(f"── {hz} 선행 · 하락장 ──")
        print(f"  {'코호트':<16}{'n':>7}{'평균':>9}{'중앙':>9}{'승률':>7}{'−50%↓':>8}")
        for c in ("시장(전체)","딥밸류(전체)","반등군","트랩군"):
            s=o[f"[{hz}·하락장] {c}"]
            f=lambda x,p=1: (f"{x*100:+.{p}f}%" if x==x else "-")
            print(f"  {c:<16}{s['n']:>7,}{f(s['mean']):>9}{f(s['median']):>9}{(str(round(s['hit']*100))+'%' if s['hit']==s['hit'] else '-'):>7}{(str(round(s['loss']*100))+'%' if s['loss']==s['loss'] else '-'):>8}")
        print()

def _self_test():
    ok=tot=0
    def chk(n,c):
        nonlocal ok,tot; tot+=1; ok+=1 if c else 0; print(f"  [{'OK' if c else 'FAIL'}] {n}")
    # 상폐 반영: 마지막행 NaN이면 직전가로, 완전소멸이면 -1
    px=pd.DataFrame({"A":[100,110,120,np.nan,np.nan]}, index=pd.period_range("2020-01",periods=5,freq="M"))
    f=fwd_return_delist_aware(px,3)
    chk("상폐직전가 반영(t0→마지막유효120)", abs(f.iloc[0,0]-0.2)<1e-9)
    s=summarize(pd.DataFrame({"A":[0.1,-0.6,0.2]}),pd.DataFrame({"A":[True,True,True]}))
    chk("loss(−50%↓)=1/3", abs(s["loss"]-0.333)<0.01)
    print(f"\n셀프테스트: {ok}/{tot}"); return ok==tot

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--self-test",action="store_true"); a=ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    _fmt(run()); return 0

if __name__=="__main__": sys.exit(main())
