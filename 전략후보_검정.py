#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
전략후보_검정.py — 집중·성장·지속성 가설 사전등록 검정 (2026-07-27)

진우 가설:
  H1 집중: 검증된 신호를 소수 종목(N=10~15)에 농축하면 희석을 막는다
  H2 성장: 성장주(이익성장 g1·ROE) 축이 별도 수익원이다
  H3 지속성: "꾸준히 선호받는" 종목(리더십 지속)이 필수다

사전등록 변형 (결과 보기 전 고정 · 전부 보고 · 체리피킹 금지):
  V1 멀티팩터(div/bp/ep/roe z합성)            — 기준선 (검증 신호)
  V2 성장 단독(g1 z)                         — H2 순수형
  V3 성장블렌드(g1+roe+12-1모멘텀 z합성)       — H2 실전형
  V4 멀티팩터 + 지속성필터(최근6개월 중 ≥3개월 상위30) — H3
  V5 모멘텀 + 지속성필터                       — H3 (약신호 대조)
각 N ∈ {10, 15}. 방어 MA200 50%현금 · 기준비용 0.559% · pool=100 · 미완료월 제외.
구간: 팩터 패널 공통 2006-01~2026-06 (모든 변형 동일 — 구간 차이로 인한 착시 방지)

시차 규약(오늘 두 번 데인 그것): 시총 shift(1) · 팩터점수 shift(1) · 모멘텀 t-13~t-1 · 방어 전월말.
⚠️ 탐색적 검정 — 이 결과로 자본 배분하지 않는다. forward 게이트가 최종심.
⚠️ 검증용 · 투자자문 아님 · 책임 본인
"""
import glob, os, sys
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
try:
    from 비용모델 import roundtrip as _rt
except Exception:                     # SSOT 부재 시 동일값 폴백 (롱온리_재산출.py와 동일 관용구)
    _rt = lambda s="기준": {"낙관": 0.0025, "기준": 0.00559, "보수": 0.01511}[s]
COST = _rt("기준")
POOL, START = 100, "2006-01"


def find(name):
    for b in (ROOT, os.getcwd()):
        h = [x for x in glob.glob(os.path.join(b, "**", name), recursive=True)
             if not any(s in x for s in ("_백업", "_보관", "_archive"))]
        if h:
            return sorted(h, key=len)[0]
    return None


def stats(r):
    r = pd.Series(r).dropna()
    if len(r) < 24:
        return dict(cagr=np.nan, sharpe=np.nan, mdd=np.nan)
    eq = (1 + r).cumprod()
    return dict(cagr=(eq.iloc[-1] ** (12 / len(r)) - 1) * 100,
                sharpe=r.mean() / r.std() * np.sqrt(12) if r.std() > 0 else np.nan,
                mdd=(eq / eq.cummax() - 1).min() * 100)


# ── 데이터
PX = (pd.concat([pd.read_csv(find(f"_월봉종가캐시_{m}_full.csv"), dtype={"code": str})
                 for m in ("KOSPI", "KOSDAQ")])
      .assign(code=lambda d: d.code.str.zfill(6))
      .pivot_table(index="ym", columns="code", values="close", aggfunc="last").sort_index())
R = PX.pct_change(fill_method=None).mask(lambda x: x.abs() > 1.0)
mc = pd.read_csv(find("종목시총_30년.csv"), dtype={"code": str})
mc.columns = [c.strip().lstrip("﻿") for c in mc.columns]
mc["code"] = mc["code"].str.zfill(6)
mc["ym"] = pd.to_datetime(mc["date"]).dt.strftime("%Y-%m")
M = mc.pivot_table(index="ym", columns="code", values="mcap", aggfunc="last")

pan = pd.read_csv(find("mini_style_panel.csv"), dtype={"code": str})
pan["code"] = pan["code"].str.zfill(6)
for c in ("div", "bp", "ep", "roe", "g1"):
    g = pan.groupby("ym")[c]
    pan[c + "z"] = ((pan[c] - g.transform("mean")) / g.transform("std").replace(0, np.nan)).clip(-3, 3)

idx = [m for m in R.index if m in M.index and m >= START][:-1]
R2, M2 = R.reindex(idx), M.reindex(idx)
MOMR = (PX.reindex(idx).shift(1) / PX.reindex(idx).shift(13) - 1)   # t-13→t-1, 이미 지연

def wide(col):
    return (pan.pivot_table(index="ym", columns="code", values=col, aggfunc="last")
            .reindex(idx).shift(1))                                  # 월말값 → 익월 사용

MF = wide("divz") .add(wide("bpz"), fill_value=np.nan)
MF = (wide("divz") + wide("bpz") + wide("epz") + wide("roez")) / 4
G1 = wide("g1z")
MOMZ = MOMR.sub(MOMR.mean(axis=1), axis=0).div(MOMR.std(axis=1), axis=0).clip(-3, 3)
GB = (wide("g1z") + wide("roez") + MOMZ.reindex(idx)) / 3

ix = pd.read_csv(find("kospi_index_daily.csv"), parse_dates=["Date"]).set_index("Date").sort_index()
me = ix["Close"].resample("ME").last()
me.index = me.index.strftime("%Y-%m")
DEF = (me >= me.rolling(10).mean()).shift(1).reindex(idx)
K = stats(me.reindex(idx).pct_change().dropna())


def run(SIG, N, persist=False, plabel=""):
    Msel = M2.shift(1)
    # 지속성: 지연된 점수로 각 달 상위30 멤버십 → 직전 6개월 중 몇 번인가
    if persist:
        memb = SIG.rank(axis=1, ascending=False) <= 30
        pers = memb.rolling(6, min_periods=1).sum()
    held, net, turns = set(), [], []
    for t in idx:
        if t not in Msel.index or t not in SIG.index:
            continue
        mcv = Msel.loc[t].dropna()
        if len(mcv) < 50:
            continue
        cur = R2.loc[t]
        cand = [c for c in mcv.sort_values(ascending=False).index[:POOL] if pd.notna(cur.get(c))]
        s = SIG.loc[t, [c for c in cand if c in SIG.columns]].dropna()
        if persist:
            p = pers.loc[t, s.index]
            s = s[p >= 3]
        if len(s) < N:
            continue
        sel = list(s.sort_values(ascending=False).index[:N])
        w = np.minimum(np.full(N, 1 / N), 0.15)
        w = w / w.sum()
        f = 1 - len(set(sel) & held) / len(sel) if held else 1.0
        turns.append(f)
        g = float((cur[sel].values * w).sum())
        inv = 1.0
        sig = DEF.get(t)
        if pd.notna(sig) and not bool(sig):
            inv = 0.5
        net.append(g * inv - f * COST)
        held = set(sel)
    st = stats(net)
    st["turn"] = float(np.mean(turns) * 12) if turns else 0
    st["n"] = len(net)
    return st


VARIANTS = [
    ("V1 멀티팩터(기준선)", MF, False),
    ("V2 성장 g1 단독", G1, False),
    ("V3 성장블렌드(g1+roe+mom)", GB, False),
    ("V4 멀티팩터+지속성≥3/6", MF, True),
    ("V5 모멘텀+지속성≥3/6", MOMZ, True),
]

print("=" * 88)
print(" 집중·성장·지속성 사전등록 검정 · 2006-01~2026-06 · 방어·기준비용·pool=100")
print("=" * 88)
print(f"  {'변형':<28}{'N':>4}{'CAGR':>8}{'Sharpe':>9}{'MDD':>9}{'회전/년':>8}{'개월':>6}")
print("  " + "-" * 80)
out = []
for name, sig, ps in VARIANTS:
    for N in (10, 15):
        r = run(sig, N, persist=ps)
        out.append((name, N, r))
        print(f"  {name:<28}{N:>4}{r['cagr']:>7.1f}%{r['sharpe']:>9.2f}{r['mdd']:>8.1f}%"
              f"{r['turn']:>7.1f}x{r['n']:>6}")
print("  " + "-" * 80)
print(f"  {'KOSPI(PR) 동일구간':<28}{'':>4}{K['cagr']:>7.1f}%{K['sharpe']:>9.2f}{K['mdd']:>8.1f}%")
print("\n  ⚠️ 탐색적 — 10개 변형을 전부 보고했다. 이 중 최고를 고르는 순간 선택편향이 시작된다.")
print("     채택하려면: 사전등록 게이트(Sharpe>지수 & MDD<지수) + forward 병행관찰이 최종심.")
