#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""유니버스_비교.py — "18 대형주 고정이 맞나? 주도주를 매번 확인해야 하나?" 검정

진우 의문: 대형주만 고정하는 게 정답은 아니고, 매번 테마·주도주를 확인해야 한다.
검정: 유니버스 설계를 바꿔가며 30년 패널·다올 비용으로 순수익 비교.
  · TOP30        : 시총 상위 30 (순수 대형주 고정형)
  · TOP30_주도주 : 상위100 중 12-1 모멘텀 상위30 (대형주 '주도주' 추종)
  · TOP100       : 상위100 (넓은 대형·중대형)
  · 중형_100_300 : 시총 100~300위 (중형주)
각 월 EW·리밸런스, 다올 비용(수수료0·세금0.2%+슬리피지). 벤치=KOSPI 지수.

사용: py 유니버스_비교.py [--slippage 0.0005]
⚠️ 상폐포함 패널·검증용. 실현손익 아님. 투자자문 아님·책임 본인.
"""
# §8-3(2026-07-27): tax 0.002→0.0015(실제 증권거래세) · slip 0.0005→0.002045(CS 실측 편도) → 왕복 0.300%→0.559%


# ── 경로 자립화 (2026-07-27) — 샌드박스 하드코딩 제거 ──────────────
import os as _os, glob as _glob
_JQ_HERE = _os.path.dirname(_os.path.abspath(__file__))


def _jqroot():
    d = _JQ_HERE
    for _ in range(5):
        if _os.path.exists(_os.path.join(d, "종목시총_30년.csv")):
            return d
        d = _os.path.dirname(d)
    return _os.path.dirname(_JQ_HERE)


BASE = _os.environ.get("JQ_BASE", _jqroot())


def _jqfind(name):
    """이름으로 파일 자동탐색 (백업/보관 폴더 제외)."""
    for b in (BASE, _JQ_HERE, _os.getcwd()):
        hits = [h for h in _glob.glob(_os.path.join(b, "**", name), recursive=True)
                if not any(s in h for s in ("_백업", "_보관", "_archive", "__pycache__"))]
        if hits:
            return sorted(hits, key=len)[0]
    raise FileNotFoundError(f"{name} 를 못 찾음 (루트={BASE})")
# ────────────────────────────────────────────────────────────────

import os, sys, argparse, json
import numpy as np, pandas as pd
BASE=os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def _find(fn):
    for d in (BASE, os.path.dirname(BASE), os.getcwd()):
        p=os.path.join(d,fn)
        if os.path.exists(p): return p
    return None

def load_panel():
    frames=[]
    for fn in ("_월봉종가캐시_KOSPI.csv","_월봉종가캐시_KOSDAQ.csv"):
        p=_find(fn)
        if p:
            d=pd.read_csv(p,dtype={"code":str}); d["code"]=d["code"].str.zfill(6); frames.append(d)
    allc=pd.concat(frames,ignore_index=True)
    px=allc.pivot_table(index="ym",columns="code",values="close",aggfunc="last").sort_index()
    return px, px.pct_change().mask(lambda x:x.abs()>1.0)

def load_mcap():
    p=_find("종목시총_30년.csv"); d=pd.read_csv(p,dtype={"code":str}); d["code"]=d["code"].str.zfill(6)
    d["ym"]=pd.to_datetime(d["date"]).dt.strftime("%Y-%m")
    return d.pivot_table(index="ym",columns="code",values="mcap",aggfunc="last")

def load_kospi():
    p=_find("kospi_index_daily.csv")
    if not p: return None
    d=pd.read_csv(p,parse_dates=["Date"]).set_index("Date")["Close"]
    m=d.resample("ME").last(); r=m.pct_change(); r.index=r.index.strftime("%Y-%m"); return r

def stats(x,ann=12):
    x=pd.Series(x).dropna()
    if len(x)<12: return None
    c=(1+x).cumprod()
    return dict(CAGR=(1+x).prod()**(ann/len(x))-1, Sharpe=x.mean()/x.std()*np.sqrt(ann) if x.std()>0 else np.nan,
               MDD=(c/c.cummax()-1).min(), n=len(x))

def universe_bt(px, rets, mcap, kind, tax=0.0015, slippage=0.002045):
    months=[m for m in rets.index if m in mcap.index]
    held=set(); out=[]; kept=[]; turns=[]
    for k,t in enumerate(months):
        i=list(rets.index).index(t)
        mc=mcap.loc[t].dropna().sort_values(ascending=False)
        ranked=list(mc.index)
        if kind=="TOP30": sel=ranked[:30]
        elif kind=="TOP100": sel=ranked[:100]
        elif kind=="중형_100_300": sel=ranked[100:300]
        elif kind=="TOP30_주도주":
            pool=ranked[:100]
            if i>=13:
                w=px.iloc[i-13:i-1]; mom=(w.iloc[-1]/w.iloc[0]-1)
                mom=mom[[c for c in pool if c in mom.index]].dropna()
                sel=list(mom.sort_values(ascending=False).index[:30])
            else: sel=pool[:30]
        else: sel=ranked[:30]
        cur=rets.loc[t]; names=[c for c in sel if pd.notna(cur.get(c))]
        if len(names)<10: continue
        newset=set(names); f=1-len(newset&held)/len(newset) if held else 1.0
        turns.append(f); held=newset
        out.append(cur[names].mean() - f*(tax+2*slippage)); kept.append(t)
    return pd.Series(out,index=kept), (np.mean(turns) if turns else 0)*12

def run(slippage=0.002045):
    px,rets=load_panel(); mcap=load_mcap(); ksp=load_kospi()
    print("="*84)
    print(f"유니버스 비교 — 대형주 고정 vs 주도주 추종 vs 중형 (다올 비용후, 슬리피지 {slippage*100:.2f}%/편도)")
    print("="*84)
    print(f"  {'유니버스':<16}{'회전/년':>8}{'순 CAGR':>10}{'순Sharpe':>10}{'MDD':>9}{'개월':>6}")
    res={}
    for kind in ["TOP30","TOP30_주도주","TOP100","중형_100_300"]:
        s,turn=universe_bt(px,rets,mcap,kind,slippage=slippage)
        st=stats(s)
        if st:
            res[kind]=dict(cagr=round(st['CAGR']*100,1),sharpe=round(st['Sharpe'],2),mdd=round(st['MDD']*100,1),turn=round(turn,1),n=st['n'])
            print(f"  {kind:<16}{turn:>7.1f}x{st['CAGR']*100:>9.1f}%{st['Sharpe']:>10.2f}{st['MDD']*100:>8.1f}%{st['n']:>6}")
    if ksp is not None:
        ks=stats(ksp.reindex(list(s.index)))
        if ks:
            res["KOSPI"]=dict(cagr=round(ks['CAGR']*100,1),sharpe=round(ks['Sharpe'],2),mdd=round(ks['MDD']*100,1))
            print(f"  {'KOSPI(벤치)':<16}{'—':>8}{ks['CAGR']*100:>9.1f}%{ks['Sharpe']:>10.2f}{ks['MDD']*100:>8.1f}%")
    print("\n"+"-"*84)
    # 해석
    a=res.get("TOP30",{}); b=res.get("TOP30_주도주",{}); c=res.get("중형_100_300",{})
    if a and b:
        d=b['cagr']-a['cagr']
        print(f"  · 주도주 추종(모멘텀) − 대형주 고정 = {d:+.1f}%p CAGR " + ("→ 주도주 확인이 유리(진우 직관 지지)" if d>0 else "→ 회전비용 감안 시 고정이 나음"))
    if a and c:
        print(f"  · 중형주 CAGR {c.get('cagr')}% vs 대형주 {a.get('cagr')}% (회전 {c.get('turn')}x vs {a.get('turn')}x) — 수익·비용·유동성 trade-off")
    print("  ⚠️ EW·단순 모멘텀 근사. 정식 판정은 사전등록·OOS봉인 필요. 실현손익 아님. 투자자문 아님.")
    json.dump(res,open(os.path.join(BASE,"유니버스_비교_결과.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2)
    print("  저장: 유니버스_비교_결과.json")
    return res

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--slippage",type=float,default=0.0005); a=ap.parse_args()
    run(a.slippage)

if __name__=="__main__": main()
