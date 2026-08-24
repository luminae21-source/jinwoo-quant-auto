#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""#3 비용·유동성 완비 백테 — 슬리피지(자본연동 시장충격)·거래세·유동성필터 넣어도 시장 이기나.
데이터: kospi_pit_daily(상폐포함, close·volume) → 월 ADTV + 월말종가.
비용모형: 매수수수료 1.5bp, 매도 수수료+거래세 ~21bp, + 제곱근 시장충격 k·sqrt(주문/ADTV) 왕복.
유동성필터: 월ADTV≥LIQ, 그리고 주문≤MAXPART×(월ADTV) 아니면 진입불가(체결 못 함)."""

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
sys.path.insert(0); from qmj_engine import *
def pct(x,p=1): return (f"{x*100:+.{p}f}%" if x==x else "-")

# ---- 월 ADTV(거래대금) + 월말종가 ----
print("일봉 로딩·월 ADTV 계산...")
d=pd.read_csv(f"{DATA}/kospi_pit_daily.csv",dtype={"code":str},usecols=["code","date","close","volume"])
d["code"]=d["code"].str.zfill(6); dt=pd.to_datetime(d["date"],errors="coerce")
d["m"]=dt.dt.to_period("M"); d["close"]=pd.to_numeric(d["close"],errors="coerce"); d["volume"]=pd.to_numeric(d["volume"],errors="coerce")
d=d.dropna(subset=["m","close"]); d["tv"]=d["close"]*d["volume"]
adtv=d.groupby(["m","code"])["tv"].mean().unstack().sort_index()      # 월평균 일거래대금(원)
close=d.groupby(["m","code"])["close"].last().unstack().reindex_like(adtv)
idx=close.index; cols=close.columns
pbr=load_pbr(idx,cols); bull,kret=load_regime(idx); mret=monthly_return_delist_aware(close)
print(f"기간 {idx.min()}~{idx.max()} · 종목 {len(cols)}")
print(f"딥밸류 후보 월ADTV 중앙값 참고 → 아래 진단")

def build_signals_liq(close,pbr,adtv,liq_min_won,deep=0.20,ext=0.85):
    ma10=close.rolling(10).mean(); disp=close/ma10; ret1=close.pct_change()
    valid=close.notna()&(close>=500)&ma10.notna()&(pbr>0)&pbr.notna()&(adtv>=liq_min_won)
    pr=pbr.where(valid).rank(axis=1,pct=True)
    reb=valid&(pr<=deep)&(disp<ext)&(ret1>0)
    return dict(valid=valid,reb=reb,ret1=ret1)

CB_FEE=0.00015          # 매수 수수료
CS_FEE=0.00015+0.0018   # 매도 수수료+거래세(2024 KRX ~0.18%) = ~19.5bp
IMPACT_K=0.10           # 제곱근 시장충격 계수
def run_net(aum_won, maxpos=15, hold=12, liq_min_won=3e8, max_part=0.10, sig=None):
    if sig is None: sig=build_signals_liq(close,pbr,adtv,liq_min_won)
    reb=sig["reb"]; ret1=sig["ret1"]; ms=list(idx)
    hold_map={}; sleeve=[]; warm=12
    order_won=aum_won/maxpos
    for ti in range(warm,len(ms)-1):
        t=ms[ti]
        expired=[c for c,ei in hold_map.items() if ti-ei>=hold]
        for c in expired: hold_map.pop(c,None)
        entries=[]
        if not bool(bull.iloc[ti]):
            row=reb.iloc[ti]
            cand=[c for c in cols[row.values] if c not in hold_map]
            # 유동성: 주문이 월ADTV의 max_part 이하인 것만 체결가능
            cand=[c for c in cand if pd.notna(adtv.at[t,c]) and order_won<=max_part*adtv.at[t,c]*21]  # 월거래대금≈ADTV×21일
            cand.sort(key=lambda c: ret1.at[t,c] if pd.notna(ret1.at[t,c]) else -9, reverse=True)
            for c in cand:
                if len(hold_map)>=maxpos: break
                hold_map[c]=ti; entries.append(c)
        tn=ms[ti+1]
        held=[c for c in hold_map if pd.notna(mret.at[tn,c])]
        k=len(held)
        if k>0:
            base=float(np.nanmean([mret.at[tn,c] for c in held]))
            # 비용: 신규진입=매수수수료+충격, 만기청산=매도세+충격
            def impact(c):
                a=adtv.at[t,c]*21 if pd.notna(adtv.at[t,c]) else np.nan
                return IMPACT_K*np.sqrt(order_won/a) if a and a>0 else 0.05
            buy_cost=sum(CB_FEE+impact(c) for c in entries)
            sell_cost=sum(CS_FEE+impact(c) for c in expired if c in cols)
            cost=(buy_cost+sell_cost)/max(k,1)
            sret=base-cost
        else: sret=0.0
        for c in list(hold_map):
            if pd.isna(close.at[tn,c]): hold_map.pop(c,None)
        sleeve.append(sret)
    return pd.Series(sleeve,index=ms[warm:len(ms)-1])

# 유동성 진단
sig0=build_signals_liq(close,pbr,adtv,0)
reb_adtv=adtv.where(sig0["reb"]).stack()
print(f"\n반등군 후보 일ADTV 분포(억원): 중앙 {reb_adtv.median()/1e8:.1f} · 하위25% {reb_adtv.quantile(.25)/1e8:.1f} · 하위10% {reb_adtv.quantile(.10)/1e8:.1f}")

print("\n"+"="*88)
print("#3. 비용·유동성 완비 순수익 — AUM별 (등가중15·보유12·하락진입·유동성필터ADTV≥3억·참여율10%)")
print("="*88)
kr_bh=kret.reindex(idx).fillna(0); e_bh=(1+kr_bh[kr_bh.index>=idx[12]]).cumprod()
print(f"  참고: KOSPI 매수보유 CAGR {pct(cagr(e_bh,len(e_bh)))} · MDD {pct(mdd(e_bh))}")
print(f"\n  {'AUM':<12}{'순CAGR':>9}{'MDD':>9}{'Sharpe':>8}{'배수':>7}{'투자월비율':>10}")
sig=build_signals_liq(close,pbr,adtv,3e8)
for aum,lab in [(1e8,"1억"),(1e9,"10억"),(5e9,"50억"),(2e10,"200억"),(1e11,"1000억")]:
    sr=run_net(aum, liq_min_won=3e8, sig=sig)
    e=(1+sr).cumprod(); inv=(sr!=0).mean()
    print(f"  {lab:<12}{pct(cagr(e,len(sr))):>9}{pct(mdd(e)):>9}{sharpe(sr):>8.2f}{e.iloc[-1]:>6.1f}x{inv*100:>9.0f}%")
print("\n※ 매수1.5bp·매도~21bp(세포함)·제곱근충격 k=0.1 왕복. 유동성필터로 소액은 다수편입, 거액은 체결가능종목 감소→투자월↓.")
print("※ 한계: KOSPI PIT(대형중심)라 실제 소형딥밸류보다 유동성 낙관. 진짜 소형주는 이보다 나쁨(정직).")
