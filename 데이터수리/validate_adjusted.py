#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""validate_adjusted.py — 재수집된 조정 월봉 캐시 검증 (Phase 3)

3대 검증:
  ① 정수배 점프(기업행위 미조정 흔적)가 조정본에서 사라졌나 (조정 전/후 건수)
  ② 그라운드트루스(kospi_monthly_prices.csv, 2010+·조정본)와 월수익 큰불일치 감소했나
  ③ 옛 캐시와 'CA월에서만' 차이나고 그 외 월은 일치하나
사용: py validate_adjusted.py --market KOSPI
⚠️ 정보·검증용.
"""

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

import os, sys, argparse
import numpy as np, pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); PARENT=os.path.dirname(HERE)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def find(fn):
    for d in (PARENT,HERE,os.getcwd()):
        p=os.path.join(d,fn)
        if os.path.exists(p): return p
    return None
def is_ca(r,tol=0.03):
    if not np.isfinite(r) or r<=0: return False
    for R in range(2,21):
        if abs(r-R)<tol*R or abs(r-1.0/R)<tol*(1.0/R): return True
    return False
def rets(df):
    df=df.sort_values(["code","ym"]).copy()
    df["ratio"]=df.groupby("code")["close"].transform(lambda s:s/s.shift(1))
    df["r"]=df["ratio"]-1; return df

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--market",default="KOSPI"); a=ap.parse_args()
    mkt=a.market
    raw=pd.read_csv(find(f"_월봉종가캐시_{mkt}.csv"),dtype={"code":str}); raw.columns=[c.strip().lstrip("﻿") for c in raw.columns]; raw["code"]=raw["code"].str.zfill(6)
    adjp=find(f"_월봉종가캐시_{mkt}_adj.csv")
    if not adjp: print("조정본 없음 — 먼저 collect_adjusted_monthly.py 실행"); return
    adj=pd.read_csv(adjp,dtype={"code":str}); adj["code"]=adj["code"].str.zfill(6)
    R=rets(raw); A=rets(adj)
    n_raw=int(R["ratio"].apply(is_ca).sum()); n_adj=int(A["ratio"].apply(is_ca).sum())
    print("="*70); print(f"[{mkt}] 조정 캐시 검증"); print("="*70)
    print(f"① 정수배 점프: 원본 {n_raw} → 조정본 {n_adj}  {'✅ 감소' if n_adj<n_raw*0.3 else '⚠️ 잔여 많음'}")

    gt=find("kospi_monthly_prices.csv")
    if gt and mkt=="KOSPI":
        mp=pd.read_csv(gt,dtype=str); mp.columns=[c.strip().lstrip("﻿") for c in mp.columns]; mp=mp.rename(columns={mp.columns[0]:"Date"})
        mp["ym"]=pd.to_datetime(mp["Date"]).dt.strftime("%Y-%m")
        g=mp.melt(id_vars=["Date","ym"],var_name="code",value_name="close"); g["close"]=pd.to_numeric(g["close"],errors="coerce"); g=g.dropna(); g["code"]=g["code"].str.zfill(6)
        G=rets(g)[["code","ym","r"]].rename(columns={"r":"r_gt"})
        def big(D):
            m=G.merge(D[["code","ym","r"]],on=["code","ym"]).dropna(); m=m[m["ym"]>="2010-03"]
            return int(((m["r"]-m["r_gt"]).abs()>0.5).sum()), len(m)
        br,_=big(R); ba,tot=big(A)
        print(f"② 그라운드트루스 대비 큰불일치(>50%p): 원본 {br} → 조정본 {ba} / {tot}  {'✅ 감소' if ba<br*0.5 else '⚠️'}")
    else:
        print("② 그라운드트루스 파일 없음/코스닥 — 스킵")

    # ③ 옛 캐시와 CA월에서만 차이
    m=R[["code","ym","close"]].rename(columns={"close":"c_raw"}).merge(
        A[["code","ym","close","ratio"]].rename(columns={"close":"c_adj"}),on=["code","ym"])
    m["diff"]=(m["c_raw"]-m["c_adj"]).abs()/m["c_raw"].replace(0,np.nan)
    changed=m[m["diff"]>0.01]
    ca_share=changed["ratio"].apply(is_ca).mean() if len(changed) else np.nan
    print(f"③ 변경된 (code,ym) {len(changed):,} · 그중 CA월 비율 {ca_share*100:.0f}% {'✅ 대부분 CA월' if ca_share>0.5 else '⚠️ CA 외 변경 많음(과조정 의심)'}")
    print("\n합격 기준: ①감소 ②감소 ③변경이 대부분 CA월. 셋 다 ✅면 컷오버 진행.")

if __name__=="__main__": main()
