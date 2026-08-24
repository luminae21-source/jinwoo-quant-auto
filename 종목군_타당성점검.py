# -*- coding: utf-8 -*-
r"""종목군_타당성점검.py — "이 세 종목군만으로 판단할 수 있는가"를 먼저 센다.

검정을 설계하기 전에, 칸(cell)마다 표본이 몇 건이나 남는지부터 확인한다.
표본이 없으면 어떤 통계도 의미가 없고, 그걸 모른 채 36칸을 뽑으면 노이즈를 발견으로 착각한다.
"""
import os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
HERE = "/home/claude/jq"; UP = "/mnt/user-data/uploads/진우퀀트"

CHAIN = ["반도체", "특수 목적용 기계", "전자부품", "측정, 시험", "광학",
         "그외 기타 전문, 과학", "통신 및 방송 장비", "일반 목적용 기계", "전지"]

S = pd.read_csv(f"{HERE}/휩쏘_밸류교집합_이벤트.csv", dtype={"code": str})
S["code"] = S["code"].str.zfill(6)
S["월"] = S["date"].str[5:7].astype(int)
S["연"] = S["date"].str[:4].astype(int)

# ── 섹터 맵 (현재 시점 스냅숏)
sec = {}
for f in ("liquidity_sector.csv", "kosdaq_industry.csv"):
    d = pd.read_csv(os.path.join(UP, f), dtype=str)
    d.columns = [c.strip().lstrip("﻿") for c in d.columns]
    if {"code", "sector"}.issubset(d.columns):
        sec.update(dict(zip(d["code"].str.zfill(6), d["sector"].astype(str))))
S["섹터"] = S["code"].map(sec)
S["섹터있음"] = S["섹터"].notna()
S["체인"] = S["섹터"].fillna("").apply(lambda x: any(k in x for k in CHAIN))

C = S[S["fwd40"].notna()].copy()          # 40봉 창완결 = 성과 판정 가능
G = C[C["국면"] == "실행"].copy()          # 실전 조건

print("=" * 84)
print("[0] 출발점 — 어디까지 줄어드는가")
print("=" * 84)
for nm, n in (("전체 신호(A+S2)", len(S)),
              ("40봉 창완결(성과 판정 가능)", len(C)),
              ("🟢실행 국면만", len(G)),
              ("  + 재무 판정 가능(2002~)", int((G["태그가능"] == True).sum()))):
    print(f"  {nm:<32} {n:>6,}건")

print("\n" + "=" * 84)
print("[1] 종목군 ① 테마(반도체 체인) — 섹터 매칭이 되는가")
print("=" * 84)
print(f"  섹터 맵 보유 종목수            {len(sec):>6,}종")
print(f"  전체 신호 중 섹터 매칭됨       {int(S['섹터있음'].sum()):>6,}건  ({S['섹터있음'].mean()*100:.1f}%)")
print(f"  🟢실행 중 섹터 매칭됨          {int(G['섹터있음'].sum()):>6,}건  ({G['섹터있음'].mean()*100:.1f}%)")
print(f"  🟢실행 중 반도체 체인          {int(G['체인'].sum()):>6,}건  ({G['체인'].mean()*100:.1f}%)")
print("\n  ⚠️ 섹터 미매칭분은 대부분 '지금 상장돼 있지 않은 종목'이다(상폐·합병).")
print("     즉 섹터로 나누는 순간 생존한 종목만 남는다 — 생존편향이 구조적으로 들어온다.")
yr = G.groupby(G["연"] // 10 * 10)["섹터있음"].agg(["sum", "count", "mean"])
print("\n  [연대별 섹터 매칭률] — 옛날일수록 매칭이 안 된다면 그게 생존편향의 증거다")
for d0, r in yr.iterrows():
    print(f"    {int(d0)}년대  {int(r['sum']):>5,} / {int(r['count']):>5,}건 = {r['mean']*100:>5.1f}%")

print("\n" + "=" * 84)
print("[2] 36칸 — 월 × 종목군 실제 표본 수 (🟢실행 국면)")
print("=" * 84)
G["밸류군"] = G["밸류여부"] & (G["태그가능"] == True)
G["성장가능"] = G["연"] >= 2015          # 성장 데이터가 존재하는 최소 조건
cells = []
hdr = f"{'월':<5}{'①체인':>9}{'②밸류':>9}{'③2015+':>9}{'  전체':>9}"
print(hdr)
for m in range(1, 13):
    s = G[G["월"] == m]
    a = int(s["체인"].sum()); b = int(s["밸류군"].sum()); c = int(s["성장가능"].sum())
    cells += [a, b, c]
    flag = "  ← 30건 미만 칸 있음" if min(a, b, c) < 30 else ""
    print(f"{m:<5}{a:>9,}{b:>9,}{c:>9,}{len(s):>9,}{flag}")
print(f"\n  36칸 중 30건 미만: {sum(1 for x in cells if x < 30)}칸 · 50건 미만: {sum(1 for x in cells if x < 50)}칸 · 100건 미만: {sum(1 for x in cells if x < 100)}칸")
print(f"  최소 칸 {min(cells)}건 · 중앙 {int(np.median(cells))}건 · 최대 {max(cells)}건")

print("\n" + "=" * 84)
print("[3] 이 표본으로 무엇을 탐지할 수 있는가 — 검정력(power)")
print("=" * 84)
sd = G["카드"].std() * 100
print(f"  🟢실행 카드 수익률 표준편차 σ = {sd:.1f}%p")
print(f"  {'표본 n':<10}{'탐지 가능한 최소 차이(80% 검정력)':<34}{'현실성'}")
for n in (20, 30, 50, 100, 200, 500, 1000):
    mde = 2.8 * sd / np.sqrt(n)      # 2표본 근사: ≈2.8σ/√n (80% power, α=.05)
    real = "이 시스템의 실제 효과크기(0.5~2%p)로는 절대 불가" if mde > 4 else \
           ("어려움" if mde > 2.5 else ("가능" if mde > 1.5 else "충분"))
    print(f"  {n:<10}{mde:>8.2f}%p 이상이어야 탐지됨{'':<12}{real}")

print("\n" + "=" * 84)
print("[4] 종목군 ③ 성장주 — 데이터가 있는가")
print("=" * 84)
print(f"  🟢실행 신호 중 2015년 이후    {int(G['성장가능'].sum()):>6,}건  ({G['성장가능'].mean()*100:.1f}%)")
print(f"  그중 반도체 체인              {int((G['성장가능'] & G['체인']).sum()):>6,}건")
print(f"  그중 밸류 태그                {int((G['성장가능'] & G['밸류군']).sum()):>6,}건")
print("\n  ⚠️ 성장 지표는 아직 이벤트에 붙어있지 않다. DART 재무를 시점 정확(PIT)하게 결합해야 한다.")
print("     30년 검정이 아니라 '11년 검정'이 된다 — 그것도 위기 표본(2020) 하나에 크게 의존한다.")

print("\n" + "=" * 84)
print("[5] 밸류군 vs 성장주 — 정말 배타적인가 (이게 이 과제의 핵심 대조)")
print("=" * 84)
R = G[(G["태그가능"] == True) & (G["연"] >= 2015)]
ct = pd.crosstab(R["체인"], R["밸류여부"])
print("  2015년 이후 · 🟢실행 · 재무판정가능 표본에서")
print(f"    반도체 체인 × 밸류태그 O : {int(ct.loc[True, True]) if True in ct.index and True in ct.columns else 0:>5,}건")
print(f"    반도체 체인 × 밸류태그 X : {int(ct.loc[True, False]) if True in ct.index and False in ct.columns else 0:>5,}건")
print(f"    非체인    × 밸류태그 O : {int(ct.loc[False, True]) if False in ct.index and True in ct.columns else 0:>5,}건")
print(f"    非체인    × 밸류태그 X : {int(ct.loc[False, False]) if False in ct.index and False in ct.columns else 0:>5,}건")
if True in ct.index:
    rate_chain = ct.loc[True, True] / ct.loc[True].sum() * 100
    rate_other = ct.loc[False, True] / ct.loc[False].sum() * 100
    print(f"\n  밸류 태그 비율: 반도체 체인 {rate_chain:.1f}%  vs  非체인 {rate_other:.1f}%")
    print("  → 차이가 크면 '체인=성장주=밸류 아님' 가설이 데이터로 확인되는 것이고,")
    print("     그렇다면 ①테마와 ③성장주는 사실상 같은 축을 두 번 재는 것이 된다.")
