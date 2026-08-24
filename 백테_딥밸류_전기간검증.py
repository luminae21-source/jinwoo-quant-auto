#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""백테_딥밸류_전기간검증.py — 딥밸류 논지 최종검증 (30년 전기간·상폐 손실반영)

배경: 30년 패널은 상폐 2,283종 포함(무결성 통과: IMF·리먼·코로나 실제지수와 방향·폭 일치, 상관0.704).
     앞 30년 백테스트의 결함은 데이터가 아니라 '상폐를 NaN으로 버린 계산'이었다. 이번엔 손실로 반영.
방법: 선행수익 계산 시 종목이 창 안에서 상폐되면 마지막가로 청산 + **정리매매 추가하락 가정(haircut)**.
      상폐실측(소멸직전20일 평균 −26.5%, 42.6%가 −50%↓, 37% 거래정지로 붕괴 미관측) → haircut 0/−30/−50/−100% 민감도.
코호트: 딥밸류(PBR하위20%) · 반등군(딥밸류∩이격<0.85∩1M수익>0) · 트랩군(딥밸류∩역배열) · 시장.
검증창: 2002~2026 하락장 전체 + 2008 리먼 별도. 투자자문 아님·결정 본인.
사용: py 백테_딥밸류_전기간검증.py [--self-test]
"""
import os, sys, argparse
import numpy as np, pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
BEAR2008=("2008-05","2009-03")

def load_price():
    d=pd.read_csv(os.path.join(HERE,"_m_all.csv"),header=None,names=["code","date","close"],dtype={"code":str})
    d["code"]=d["code"].str.zfill(6); d["m"]=pd.to_datetime(d["date"],errors="coerce").dt.to_period("M")
    d["close"]=pd.to_numeric(d["close"],errors="coerce"); d=d.dropna(subset=["m","close"])
    return d.pivot_table(index="m",columns="code",values="close",aggfunc="last").sort_index()

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

def fwd_delist(px, h, haircut):
    """h개월 선행수익. 창 안에서 상폐(마지막관측<t+h)면 마지막가에 haircut 적용해 청산."""
    V=px.values; T,N=V.shape; out=np.full((T,N),np.nan)
    lastobs=np.full(N,-1)
    for j in range(N):
        nz=np.where(~np.isnan(V[:,j]))[0]
        lastobs[j]=nz[-1] if nz.size else -1
    for ti in range(T):
        base=V[ti]; hi=min(ti+h,T-1)
        if hi<=ti: continue
        win=V[ti+1:hi+1]
        for j in range(N):
            b=base[j]
            if not(b==b) or b<=0: continue
            col=win[:,j]; val=col[~np.isnan(col)]
            delisted = lastobs[j] <= ti+h    # 창 종료 전에 데이터 소멸 = 상폐로 강제청산
            if val.size>0:
                exitp=val[-1]*(1+haircut) if delisted else val[-1]
                out[ti,j]=exitp/b-1
            else:
                out[ti,j]=haircut if delisted else np.nan
    return pd.DataFrame(out,index=px.index,columns=px.columns)

def regime(idx):
    k=pd.read_csv(os.path.join(HERE,"kospi_index_daily.csv"),encoding="utf-8-sig"); k.columns=[c.lstrip("﻿").lower() for c in k.columns]
    k["m"]=pd.to_datetime(k["date"],errors="coerce").dt.to_period("M"); k["close"]=pd.to_numeric(k["close"],errors="coerce")
    km=k.dropna(subset=["m"]).groupby("m")["close"].last().sort_index()
    return (km>km.rolling(10).mean()).reindex(idx).ffill().fillna(False)

def mean_hit(fwd,mask):
    v=fwd.where(mask).values.ravel(); v=v[~np.isnan(v)]
    if len(v)==0: return (np.nan,np.nan,0)
    return (float(np.mean(v)),float((v>0).mean()),int(len(v)))

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
    b08=pd.Series([(BEAR2008[0]<=str(m)<=BEAR2008[1]) for m in idx],index=idx)
    b08m=pd.DataFrame(np.repeat(b08.values[:,None],px.shape[1],axis=1),index=idx,columns=cols)
    coh={"시장":valid,"딥밸류":deep,"반등군":reb,"트랩군":trap}
    res={"기간":f"{idx.min()}~{idx.max()}","종목수":px.shape[1]}
    for hc in (0.0,-0.30,-0.50,-1.0):
        f12=fwd_delist(px,12,hc)
        res[f"haircut{int(hc*100)}"]={c:mean_hit(f12,m&bear) for c,m in coh.items()}
        res[f"haircut{int(hc*100)}_2008"]={c:mean_hit(f12,m&b08m) for c,m in coh.items()}
    return res

def _fmt(o):
    print(f"\n{'='*80}\n딥밸류 최종검증 · 30년 전기간·상폐 손실반영 · {o['기간']} ({o['종목수']}종)\n12개월 선행수익 · 하락장 · haircut=상폐 추가하락 가정\n{'='*80}")
    print(f"\n  {'haircut':<10}{'시장':>16}{'딥밸류':>16}{'반등군':>16}{'트랩군':>16}")
    for hc in (0,-30,-50,-100):
        r=o[f"haircut{hc}"]
        def cell(c):
            m,h,n=r[c]; return f"{m*100:+.1f}%/{h*100:.0f}%" if m==m else "-"
        print(f"  {str(hc)+'%':<10}{cell('시장'):>16}{cell('딥밸류'):>16}{cell('반등군'):>16}{cell('트랩군'):>16}")
    print("  (평균수익/승률 · n은 아래)")
    m,h,n=o["haircut0"]["반등군"]; print(f"  · 반등군 표본 n={n} · 딥밸류 n={o['haircut0']['딥밸류'][2]} · 시장 n={o['haircut0']['시장'][2]}")
    print(f"\n── 2008 리먼 단독 ({BEAR2008[0]}~{BEAR2008[1]}) · 12M선행 ──")
    print(f"  {'haircut':<10}{'시장':>16}{'딥밸류':>16}{'반등군':>16}{'트랩군':>16}")
    for hc in (0,-50,-100):
        r=o[f"haircut{hc}_2008"]
        def cell(c):
            m,h,n=r[c]; return f"{m*100:+.1f}%" if m==m else "-"
        print(f"  {str(hc)+'%':<10}{cell('시장'):>16}{cell('딥밸류'):>16}{cell('반등군'):>16}{cell('트랩군'):>16}")
    m,h,n=o["haircut0_2008"]["반등군"]; print(f"  · 2008 반등군 n={n}")

def _self_test():
    ok=tot=0
    def chk(n,c):
        nonlocal ok,tot; tot+=1; ok+=1 if c else 0; print(f"  [{'OK' if c else 'FAIL'}] {n}")
    # 상폐 haircut: A가 3개월 뒤 소멸, haircut -50%
    px=pd.DataFrame({"A":[100,120,np.nan,np.nan]},index=pd.period_range("2008-01",periods=4,freq="M"))
    f=fwd_delist(px,3,-0.5)
    chk("상폐 haircut −50% 반영(120*0.5/100-1=-0.4)", abs(f.iloc[0,0]-(-0.4))<1e-9)
    f0=fwd_delist(px,3,0.0)
    chk("haircut 0이면 마지막가(120/100-1=0.2)", abs(f0.iloc[0,0]-0.2)<1e-9)
    m,h,n=mean_hit(pd.DataFrame({"A":[0.1,-0.2,0.3]}),pd.DataFrame({"A":[True,True,True]}))
    chk("mean_hit n=3", n==3)
    print(f"\n셀프테스트: {ok}/{tot}"); return ok==tot

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--self-test",action="store_true"); a=ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    _fmt(run()); return 0
if __name__=="__main__": sys.exit(main())
