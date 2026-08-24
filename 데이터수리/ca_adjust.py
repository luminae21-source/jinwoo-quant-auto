# -*- coding: utf-8 -*-
r"""ca_adjust.py — 월봉 종가 캐시 기업행위(감자·액면병합·분할) 자동 역조정 (데이터 수리)

검증된 문제: _월봉종가캐시가 기업행위 미조정 → 정수배 상방(×N)·하방(÷N) 점프.
원리(back-adjust): 각 종목 시계열을 뒤에서 앞으로 걸으며, '영구적 정수배 점프'(=기업행위)를
  만나면 그 이전 가격에 배수를 누적 곱해 점프를 제거(조정 후 그 달 비율≈1).
  일시적 스파이크(되돌림)는 데이터오류로 보고 조정하지 않음(윈저가 처리).
사용: py ca_adjust.py KOSPI|KOSDAQ   → _월봉종가캐시_<mkt>_adj.csv + 조정로그
⚠️ 원본 미변경(새 _adj 파일). 정보·검증용.
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

import sys, pandas as pd, numpy as np
mkt=sys.argv[1] if len(sys.argv)>1 else "KOSPI"
# BASE는 아래 프리앰블에서 자동 결정 (경로자립화 2026-07-27)
px=pd.read_csv(f"{BASE}/_월봉종가캐시_{mkt}.csv",dtype={"code":str}); px.columns=[c.strip().lstrip("﻿") for c in px.columns]; px["code"]=px["code"].str.zfill(6)
px=px.sort_values(["code","ym"]).reset_index(drop=True)

def is_ca(ratio):
    if not np.isfinite(ratio) or ratio<=0: return None
    for R in range(2,51):
        if abs(ratio-R)<0.03*R: return float(R)          # 상방 ×R
        if abs(ratio-1.0/R)<0.03*(1.0/R): return 1.0/R   # 하방 ÷R
    return None

logs=[]; adj_all=[]
for code,g in px.groupby("code",sort=False):
    g=g.sort_values("ym").copy(); c=g["close"].values.astype(float); n=len(g)
    if n<5: g["close_adj"]=c; adj_all.append(g); continue
    ratio=np.r_[np.nan,c[1:]/c[:-1]]
    fac=np.ones(n)  # 각 지점에 곱할 누적배수(뒤→앞)
    cum=1.0
    for t in range(n-1,0,-1):
        R=is_ca(ratio[t])
        if R is not None:
            # 영구성: 점프 후 3개월 새 레벨 유지?
            fut=c[t:min(t+4,n)]; hold=(np.median(fut)/c[t])>0.6 if len(fut)>=2 else True
            if hold:
                cum*=R; logs.append((code,g["ym"].values[t],round(ratio[t],3),round(R,3)))
        fac[t-1]=cum   # t-1 및 그 이전에 적용
    # fac는 각 지점 '이후 CA들의 누적'을 담아야 함 → 위 루프가 fac[t-1] 갱신하며 앞으로 전파
    # 재구성: 뒤에서 앞으로 cum 누적
    cum=1.0; fac=np.ones(n)
    for t in range(n-1,0,-1):
        R=is_ca(ratio[t])
        if R is not None:
            fut=c[t:min(t+4,n)]; hold=(np.median(fut)/c[t])>0.6 if len(fut)>=2 else True
            if hold: cum*=R
        fac[t-1]=cum
    g["close_adj"]=c*fac
    adj_all.append(g)
out=pd.concat(adj_all).sort_values(["code","ym"])
out[["code","ym","close_adj"]].rename(columns={"close_adj":"close"}).to_csv(f"_월봉종가캐시_{mkt}_adj.csv",index=False,encoding="utf-8")
lg=pd.DataFrame(logs,columns=["code","ym","raw_ratio","factor"]).drop_duplicates()
lg.to_csv(f"ca_log_{mkt}.csv",index=False,encoding="utf-8")
print(f"[{mkt}] 조정 완료 · CA 이벤트 {len(lg)}건 · 영향종목 {lg['code'].nunique()}")
# 조정 후 잔여 정수배 점프
a=out.sort_values(["code","ym"]); a["r"]=a.groupby("code")["close_adj"].transform(lambda s:s/s.shift(1))
resid=a["r"].apply(lambda x: is_ca(x) is not None if pd.notna(x) else False).sum()
print(f"  조정 후 잔여 정수배 점프: {int(resid)} (조정 전 대비 감소 확인)")
