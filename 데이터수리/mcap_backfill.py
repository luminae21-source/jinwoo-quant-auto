# -*- coding: utf-8 -*-
r"""mcap_backfill.py — 시총 원본 결측월(대부분 연말 12월) 전월캐리 백필 (안전)

검증: 종목시총_30년.csv가 26개월(2007~2025 대부분 12월 + 2006-05·2020-04 등)을 미보유.
안전성: 시총은 월간 지속성이 매우 커서(전월 상관 ~0.99) 전월캐리 대체의 왜곡이 작음 — 아래 검증 출력.
사용: py mcap_backfill.py  → 종목시총_30년_backfill.csv (+ 채운 월 로그). 원본 미변경.
⚠️ '복구'가 아니라 '결측치 대체'. imputed 플래그로 추적. 정보·검증용.
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

import pandas as pd, numpy as np
# BASE는 아래 프리앰블에서 자동 결정 (경로자립화 2026-07-27)
mc=pd.read_csv(f"{BASE}/종목시총_30년.csv",dtype={"code":str}); mc.columns=[c.strip().lstrip("﻿") for c in mc.columns]; mc["code"]=mc["code"].str.zfill(6)
mc["ym"]=pd.to_datetime(mc["date"]).dt.strftime("%Y-%m"); mc["mcap"]=pd.to_numeric(mc["mcap"],errors="coerce")
def grid(a,b):
    o=[];y,m=int(a[:4]),int(a[5:7])
    while (y,m)<=(int(b[:4]),int(b[5:7])): o.append(f"{y:04d}-{m:02d}"); m+=1; (y:=y) 
    return o
def mg(a,b):
    o=[];y,m=int(a[:4]),int(a[5:7])
    while (y,m)<=(int(b[:4]),int(b[5:7])):
        o.append(f"{y:04d}-{m:02d}"); m+=1
        if m==13:y+=1;m=1
    return o
have=sorted(mc["ym"].unique()); full=mg(have[0],have[-1]); miss=[m for m in full if m not in set(have)]
# 지속성 검증
W=mc.pivot_table(index="code",columns="ym",values="mcap",aggfunc="last")
corr=pd.Series(np.diag(W.iloc[:,1:].corrwith(W.shift(1,axis=1).iloc[:,1:])) if False else [W[c].corr(W[p]) for p,c in zip(full[:-1],full[1:]) if p in W and c in W]).mean()
print(f"결측월 {len(miss)}개: {miss}")
print(f"시총 전월 상관(지속성): {corr:.4f}  → 1에 가까울수록 전월캐리 왜곡 작음")
# 백필(안전): '살아있는 구간의 내부 결측'만 전월값으로 채움(상폐 종목 되살리지 않음)
Wr=W.reindex(columns=full)
ff=Wr.ffill(axis=1); bf=Wr.bfill(axis=1)
alive=ff.notna()&bf.notna()               # 앞뒤로 실측 존재 = 그때 상장중
Wf=Wr.where(Wr.notna(), ff.where(alive))   # 내부 결측만 전월 실측으로
long=Wf.reset_index().melt(id_vars="code",var_name="ym",value_name="mcap").dropna(subset=["mcap"])
realset=set(map(tuple,mc[["code","ym"]].values))
long["imputed"]=~long.apply(lambda r:(r["code"],r["ym"]) in realset,axis=1)
long=long.merge(mc[["code","ym","date"]],on=["code","ym"],how="left")
long.to_csv("종목시총_30년_backfill.csv",index=False,encoding="utf-8")
print(f"백필 완료: {len(long):,}행 · 대체행 {int(long['imputed'].sum()):,} ({long['imputed'].mean()*100:.2f}%) · 종목시총_30년_backfill.csv")
