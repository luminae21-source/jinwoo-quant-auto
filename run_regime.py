#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""#4 낙폭완화 — 국면(RISK_OFF) 비중조절 프론티어.
전량현금(φ=0) vs 부분비중(φ=.25/.5/.75) vs 무방어(φ=1)의 CAGR-MDD-Calmar 트레이드오프.
1차: KOSPI 지수 30년(생존편향 無, 2008포함)  2차: 딥밸류 콤보(2019+ 상폐반영) 교차확인."""

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

def pct(x,p=1): return (f"{x*100:+.{p}f}%" if x==x else "  -")

# ---------- 1. KOSPI 지수 30년 국면 비중조절 ----------
k=pd.read_csv(f"{DATA}/kospi_index_daily.csv",encoding="utf-8-sig"); k.columns=[c.lstrip("﻿").lower() for c in k.columns]
k["m"]=pd.to_datetime(k["date"],errors="coerce").dt.to_period("M"); k["close"]=pd.to_numeric(k["close"],errors="coerce")
km=k.dropna(subset=["m"]).groupby("m")["close"].last().sort_index()
km=km[km.index>=pd.Period("2000-01")]
ret=km.pct_change().fillna(0)
ma10=km.rolling(10).mean()
risk_off=(km<ma10).reindex(km.index).fillna(False)   # RISK_OFF = 지수<10개월선
# 국면판정은 t-1 정보로 t 비중 결정(룩어헤드 방지): 진입은 전월말 신호
sig_off=risk_off.shift(1).fillna(False)

print("="*92)
print("#4-A. KOSPI 지수 국면 비중조절 (2000~2026, 30년 근사·지수라 생존편향 無, 2008 포함)")
print("="*92)
print(f"기간 {km.index.min()}~{km.index.max()} · 월 {len(ret)} · RISK_OFF 비율 {sig_off.mean()*100:.0f}%")
print(f"\n  {'RISK_OFF 비중φ':<16}{'CAGR':>9}{'MDD':>9}{'Sharpe':>8}{'Calmar':>8}{'최종배수':>9}{'수익보존%':>10}")
bh_cagr=None; rows=[]
for phi in [1.0,0.75,0.5,0.25,0.0]:
    w=np.where(sig_off.values, phi, 1.0)
    pr=ret.values*w
    e=pd.Series((1+pr).cumprod(),index=ret.index)
    c=cagr(e,len(pr)); md=mdd(e); sh=sharpe(pd.Series(pr)); cal=calmar(c,md)
    if phi==1.0: bh_cagr=c
    keep = c/bh_cagr if bh_cagr and bh_cagr>0 else float("nan")
    lab={1.0:"1.0(무방어)",0.75:"0.75",0.5:"0.50",0.25:"0.25",0.0:"0.0(전량현금)"}[phi]
    print(f"  {lab:<16}{pct(c):>9}{pct(md):>9}{sh:>8.2f}{cal:>8.2f}{e.iloc[-1]:>8.1f}x{pct(keep,0):>10}")
print("→ φ↓ 하면 MDD 크게 줄고 CAGR는 상대적으로 덜 준다면 '수익 대부분 유지하며 낙폭완화' 성립.")

# ---------- 2. 딥밸류 콤보 교차확인 (2019+ 상폐반영) ----------
print("\n"+"="*92)
print("#4-B. 딥밸류 콤보 교차확인 (2019+·상폐반영): 강세=지수, RISK_OFF=딥밸류슬리브×φ + 현금")
print("="*92)
close=load_monthly_close(); idx=close.index; cols=close.columns
pbr=load_pbr(idx,cols); bull,kret=load_regime(idx); sig=build_signals(close,pbr)
mret=monthly_return_delist_aware(close)
r=portfolio_backtest(close,sig,bull,kret,mret,qpanel=None,q_min_rank=None)
sr=r["sleeve"]; bl=r["bull"].reindex(sr.index).fillna(False); kr=r["kret"].reindex(sr.index).fillna(0)
print(f"  {'RISK_OFF 슬리브φ':<16}{'CAGR':>9}{'MDD':>9}{'Sharpe':>8}{'Calmar':>8}{'최종배수':>9}")
for phi in [1.0,0.75,0.5,0.25,0.0]:
    combo=np.where(bl.values, kr.values, sr.values*phi)   # 하락장 슬리브 비중 φ, 나머지 현금(0)
    cser=pd.Series(combo,index=sr.index); e=(1+cser).cumprod()
    c=cagr(e,len(cser)); md=mdd(e); sh=sharpe(cser); cal=calmar(c,md)
    lab={1.0:"1.0",0.75:"0.75",0.5:"0.50",0.25:"0.25",0.0:"0.0(현금)"}[phi]
    print(f"  {lab:<16}{pct(c):>9}{pct(md):>9}{sh:>8.2f}{cal:>8.2f}{e.iloc[-1]:>8.1f}x")
print("\n※ A는 지수(무편향·장기), B는 딥밸류전략(상폐반영·짧음). 둘의 φ-반응 방향이 일치하면 견고.")
print("※ 생존편향: A 지수는 없음 / 월봉주가 기반 B의 슬리브는 상폐 -100% 반영으로 부분통제.")
