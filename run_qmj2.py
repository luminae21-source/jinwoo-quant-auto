#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""#2 QMJ 엄밀검증 (§3 스타일): IN/OOS 양분할 + 부트스트랩 + 트랩회피 실측 + 유니버스 한계 진단."""

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

import numpy as np, pandas as pd, sys
sys.path.insert(0)
from qmj_engine import *
rng=np.random.default_rng(7)

def pct(x,p=1): return (f"{x*100:+.{p}f}%" if x==x else "  -")

close=load_monthly_close(); idx=close.index; cols=close.columns
pbr=load_pbr(idx,cols); bull,kret=load_regime(idx); sig=build_signals(close,pbr); qp=quality_panel(idx,cols)
bear=pd.DataFrame(np.repeat((~bull).values[:,None],close.shape[1],axis=1),index=idx,columns=cols)
qavail=qp["Quality"].notna()
yr=pd.Series([p.year for p in idx],index=idx)

# ---- 유니버스 한계 진단: 트랩(상폐/-50%)이 이 유니버스에 존재하나? ----
print("="*92); print("0. 유니버스 한계 진단 — '밸류트랩 회피'가 이 데이터로 검증가능한가?"); print("="*92)
fwd12=fwd_return_delist_aware(close,12)
deep_bear=sig["deep"]&bear
qcov = (sig["deep"]&qavail).sum().sum() / max(sig["deep"].sum().sum(),1)
v=fwd12.where(deep_bear).values.ravel(); v=v[~np.isnan(v)]
print(f"딥밸류 관측 중 퀄리티데이터 보유 비율: {qcov*100:.0f}%  (fundamentals_pit=KOSPI top~577 대형·중형만)")
print(f"딥밸류(하락장) 12M 선행수익 분포: n={len(v)}  −50%↓(트랩)={100*(v<=-.5).mean():.1f}%  −100%(상폐)={100*(v<=-.99).mean():.1f}%")
print("→ 트랩/상폐가 극소 = 이 유니버스(대형주)엔 애초에 밸류트랩이 거의 없음. 트랩회피 효익 측정력 낮음(정직).")

def boot_diff(a,b,n=4000):
    a=np.asarray(a); b=np.asarray(b)
    d=a.mean()-b.mean(); ds=[]
    for _ in range(n):
        ds.append(rng.choice(a,len(a)).mean()-rng.choice(b,len(b)).mean())
    ds=np.array(ds); return d, float((ds<=0).mean()), (float(np.percentile(ds,2.5)),float(np.percentile(ds,97.5)))

# ---- 신호테스트: 딥밸류 내 퀄리티 3분위 (더 큰 n) ----
print("\n"+"="*92)
print("1. 신호테스트 — 딥밸류(하락장) 내 퀄리티 3분위 선행수익  [ALL / IN(~2022) / OOS(2023~)]")
print("="*92)
for hz,h in (("12M",12),("6M",6)):
    fwd=fwd_return_delist_aware(close,h)
    q_in_deep=qp["Quality"].where(deep_bear&qavail)
    r=q_in_deep.rank(axis=1,pct=True)
    terts={"Q하(정크)":deep_bear&(r<0.333),"Q중":deep_bear&(r>=0.333)&(r<0.667),"Q상(우량)":deep_bear&(r>=0.667)}
    print(f"\n── {hz} ──  (n 평균 중앙 승률 −50%↓)")
    for seg,cond in (("ALL",yr>=0),("IN(2020-22)",(yr>=2020)&(yr<=2022)),("OOS(2023-26)",yr>=2023)):
        segmask=pd.DataFrame(np.repeat(cond.values[:,None],close.shape[1],axis=1),index=idx,columns=cols)
        print(f"  [{seg}]")
        for nm,mk in terts.items():
            s=summ(fwd,mk&segmask)
            print(f"    {nm:<10}{s['n']:>6}{pct(s['mean']):>9}{pct(s['median']):>9}"
                  f"{(str(round(s['hit']*100))+'%' if s['hit']==s['hit'] else '-'):>7}"
                  f"{(str(round(s['loss']*100))+'%' if s['loss']==s['loss'] else '-'):>8}")

# ---- 퀄리티 상 vs 하 유의성 (딥밸류내, 12M, ALL/IN/OOS) ----
print("\n"+"="*92); print("2. 유의성 — 퀄리티상(우량) − 퀄리티하(정크), 딥밸류 12M 선행, 부트스트랩"); print("="*92)
fwd=fwd_return_delist_aware(close,12)
q_in_deep=qp["Quality"].where(deep_bear&qavail); r=q_in_deep.rank(axis=1,pct=True)
hi=deep_bear&(r>=0.667); lo=deep_bear&(r<0.333)
for seg,cond in (("ALL",yr>=0),("IN(2020-22)",(yr>=2020)&(yr<=2022)),("OOS(2023-26)",yr>=2023)):
    sm=pd.DataFrame(np.repeat(cond.values[:,None],close.shape[1],axis=1),index=idx,columns=cols)
    a=fwd.where(hi&sm).values.ravel(); a=a[~np.isnan(a)]
    b=fwd.where(lo&sm).values.ravel(); b=b[~np.isnan(b)]
    if len(a)<10 or len(b)<10: print(f"  {seg:<12} n부족(a={len(a)},b={len(b)})"); continue
    d,pneg,ci=boot_diff(a,b)
    print(f"  {seg:<12} Δ평균(상-하)={pct(d)}  95%CI[{pct(ci[0])},{pct(ci[1])}]  P(Δ≤0)={pneg:.3f}  na={len(a)} nb={len(b)}")

# ---- 포트폴리오 IN/OOS ----
print("\n"+"="*92); print("3. 포트폴리오 IN/OOS — 기준 vs QMJ상위50% (등가중15·보유12·하락진입)"); print("="*92)
mret=monthly_return_delist_aware(close)
def seg_stats(sr,y0,y1):
    s=sr[(pd.Series([p.year for p in sr.index],index=sr.index)>=y0)&(pd.Series([p.year for p in sr.index],index=sr.index)<=y1)]
    if len(s)<6: return None
    e=(1+s).cumprod(); return dict(CAGR=cagr(e,len(s)),MDD=mdd(e),Sharpe=sharpe(s),n=len(s))
base=portfolio_backtest(close,sig,bull,kret,mret,qpanel=None,q_min_rank=None)["sleeve"]
qmj =portfolio_backtest(close,sig,bull,kret,mret,qpanel=qp,q_min_rank=0.50)["sleeve"]
for lab,y0,y1 in (("ALL",2019,2026),("IN(2020-22)",2020,2022),("OOS(2023-26)",2023,2026)):
    sb=seg_stats(base,y0,y1); sq=seg_stats(qmj,y0,y1)
    if not sb or not sq: continue
    print(f"  [{lab}] 기준  CAGR{pct(sb['CAGR']):>8} MDD{pct(sb['MDD']):>8} Sh{sb['Sharpe']:>6.2f} (n{sb['n']})")
    print(f"  [{lab}] QMJ  CAGR{pct(sq['CAGR']):>8} MDD{pct(sq['MDD']):>8} Sh{sq['Sharpe']:>6.2f} (n{sq['n']})")
# 월수익차 부트스트랩(공통구간)
common=base.index.intersection(qmj.index)
d,pneg,ci=boot_diff(qmj.reindex(common).values, base.reindex(common).values)
print(f"\n  월수익차(QMJ-기준) 평균 {pct(d,2)}/월  P(Δ≤0)={pneg:.3f}  95%CI[{pct(ci[0],2)},{pct(ci[1],2)}]  (부호검정용)")
