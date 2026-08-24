# -*- coding: utf-8 -*-
r"""탐색_매매기법_후보선별.py — 성장/가치 트랙 신규 기법 후보 1차 선별 (2026-07-28)

⚠️⚠️ 이것은 **판정이 아니라 탐색(screening)이다.** ⚠️⚠️
  · 구간: 2002~2015 (IN) — **2016~2026은 열지 않는다** (위성엔진 사전등록의 봉인 OOS)
  · 목적: 사전등록할 가치가 있는 후보를 고르는 것. 여기 t값은 근거가 아니라 **우선순위**다.
  · 여기서 좋아 보인 것도 사전등록 → 봉인 OOS 개봉 검정을 통과해야 채택된다.

[이미 기각된 것은 테스트하지 않는다 — 증명된_규칙 이력]
  모멘텀 12-1(t≈0, 롱온리 −9~−13%) · 52주신고가(IN 무증거) · GP수익성(단기창 음수) ·
  고변동성(저변동성에 패배) · 저PER(OOS 실패)

[테스트 후보 — 가치 트랙]
  V1 배당지속성   : 최근 36개월 중 DPS>0 비율        (배당 함정 회피)
  V2 배당성장     : DPS_t / DPS_{t-12} − 1           (레벨 아닌 변화)
  V3 가치함정회피 : 저PBR ∩ ROE>0 (교집합 더미)      (싼 게 아니라 망하는 것 배제)
  V4 배당수익률   : DIV (대조군 — 이미 아는 값)

[테스트 후보 — 성장 트랙]
  G1 EPS성장      : EPS_t / EPS_{t-12} − 1
  G2 저변동성     : 12개월 월간수익 표준편차 (역부호)  (대조군 — 검증된 값)
  G3 시계열추세   : 종가 > 12개월 이동평균 (더미)      (횡단면 모멘텀 아님 — 백서가 살려둔 것)
  G4 변동성축소   : 최근6M 변동성 / 이전6M 변동성 (역) (조용해지는 종목)
  G5 저회전       : |월수익| 평균의 역 — 유동성 대용

산출: 탐색_기법후보_결과.md
"""
import os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from scipy import stats

BASE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def _find(fn):
    for d in (BASE, os.path.join(BASE, "데이터수리"), os.path.dirname(BASE), os.getcwd(),
              os.path.join(os.getcwd(), "데이터수리")):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    raise FileNotFoundError(fn)

def hac_t(x, lags=6):
    x = np.asarray(pd.Series(x).dropna(), float); n = len(x)
    if n < 12: return np.nan
    m = x.mean(); e = x - m; v = (e @ e) / n
    for L in range(1, min(lags, n - 1) + 1):
        v += 2 * (1 - L / (lags + 1)) * ((e[L:] @ e[:-L]) / n)
    return m / np.sqrt(max(v, 1e-18) / n)

# ── 가격
kis = pd.read_csv(_find("월봉_KIS_adj_v1_2026-07-28.csv"), dtype={"code": str})
kis["code"] = kis["code"].str.zfill(6)
try:
    mk = pd.read_csv(_find("_패널마스크_v1.csv"), dtype={"code": str})
    ms = set(zip(mk["code"].str.zfill(6), mk["ym"]))
    kis = kis[[(c, y) not in ms for c, y in zip(kis["code"], kis["ym"])]]
except Exception: pass

P = kis.pivot_table(index="ym", columns="code", values="close", aggfunc="last").sort_index()
_i = pd.to_datetime(P.index + "-01"); MI = (_i.year * 12 + _i.month).values
R = P.pct_change()
R[np.r_[True, np.diff(MI) != 1]] = np.nan

vol12 = R.rolling(12, min_periods=8).std()
vol6  = R.rolling(6,  min_periods=4).std()
vol6p = vol6.shift(6)
ma12  = P.rolling(12, min_periods=8).mean()
absr  = R.abs().rolling(12, min_periods=8).mean()

# ── 재무
fins = []
for mkt in ("KOSPI", "KOSDAQ"):
    fins.append(pd.read_csv(_find(f"종목재무_KRX_{mkt}.csv"), dtype={"code": str},
                            usecols=["date", "code", "BPS", "PBR", "PER", "EPS", "DIV", "DPS"]))
fin = pd.concat(fins); fin["code"] = fin["code"].str.zfill(6); fin["ym"] = fin["date"].str[:7]
for c in ("BPS", "PBR", "PER", "EPS", "DIV", "DPS"): fin[c] = pd.to_numeric(fin[c], errors="coerce")
fin = fin.groupby(["code", "ym"], as_index=False)[["BPS", "PBR", "PER", "EPS", "DIV", "DPS"]].last()

pv = lambda col: fin.pivot_table(index="ym", columns="code", values=col, aggfunc="last").reindex(P.index)
BPS, PBR, EPS, DIV, DPS = pv("BPS"), pv("PBR"), pv("EPS"), pv("DIV"), pv("DPS")
ROE = np.where(BPS > 0, EPS / BPS, np.nan)
ROE = pd.DataFrame(ROE, index=BPS.index, columns=BPS.columns)

mc = pd.read_csv(_find("종목시총_30년.csv"), dtype={"code": str})
mc.columns = [c.strip().lstrip("﻿") for c in mc.columns]
mc["code"] = mc["code"].str.zfill(6); mc["ym"] = pd.to_datetime(mc["date"]).dt.strftime("%Y-%m")
mc["mcap"] = pd.to_numeric(mc["mcap"], errors="coerce")
MC = mc.pivot_table(index="ym", columns="code", values="mcap", aggfunc="last").reindex(P.index)

# ── 후보 팩터 구성 (전부 t 시점 정보만 — 다음 달 수익 예측)
F = {}
F["V1 배당지속성(36M DPS>0 비율)"] = (DPS > 0).rolling(36, min_periods=24).mean()
F["V2 배당성장(DPS 12M)"]         = (DPS / DPS.shift(12) - 1).where(DPS.shift(12) > 0).clip(-2, 5)
F["V3 가치함정회피(저PBR∩ROE>0)"]  = (((PBR.rank(axis=1, pct=True) <= 0.4) & (ROE > 0)).astype(float)
                                      .where(PBR.notna()))
F["V4 배당수익률 DIV (대조군)"]     = DIV.clip(0, 60)
F["G1 EPS성장(12M)"]              = (EPS / EPS.shift(12) - 1).where(EPS.shift(12) > 0).clip(-2, 5)
F["G2 저변동성(12M, 역부호·대조군)"] = -vol12
F["G3 시계열추세(종가>12M MA)"]     = (P > ma12).astype(float).where(ma12.notna())
F["G4 변동성축소(최근6M/이전6M, 역)"] = -(vol6 / vol6p).replace([np.inf, -np.inf], np.nan).clip(0, 5)
F["G5 저회전(|월수익|평균, 역)"]     = -absr

fwd = R.shift(-1)                       # 다음 달 가격수익률
divm = DIV.clip(0, 60) / 100 / 12       # 배당 월분 (총수익용)
fwd_tr = fwd + divm

print("=" * 92)
print(" 매매기법 후보 1차 선별 — ⚠️ 탐색(IN 2002-2015)이며 판정이 아님 · OOS 2016+ 봉인 유지")
print("=" * 92)

def screen(univ_mask, label):
    print(f"\n{'─'*92}\n【{label}】")
    print(f"  {'후보':<34}{'IC':>9}{'HAC t':>8}{'롱숏TR':>10}{'롱숏t':>8}{'월수':>6}  우선순위")
    out = []
    for name, X in F.items():
        ics, ls = [], []
        for i, ym in enumerate(P.index):
            if ym < "2002-07" or ym > "2015-11": continue
            x = X.loc[ym].where(univ_mask.loc[ym])
            y = fwd.loc[ym]; ytr = fwd_tr.loc[ym]
            s = pd.concat([x, y, ytr], axis=1).dropna()
            s.columns = ["x", "y", "ytr"]
            nu = s["x"].nunique()
            if len(s) < 40 or nu < 2: continue
            v = stats.spearmanr(s["x"], s["y"]).statistic
            if np.isfinite(v): ics.append(v)
            if nu == 2:            # 이진 더미: 1군 vs 0군 평균 비교
                hi = s[s["x"] == s["x"].max()]["ytr"].mean()
                lo = s[s["x"] == s["x"].min()]["ytr"].mean()
            else:
                hi = s[s["x"] >= s["x"].quantile(0.8)]["ytr"].mean()
                lo = s[s["x"] <= s["x"].quantile(0.2)]["ytr"].mean()
            if np.isfinite(hi) and np.isfinite(lo): ls.append(hi - lo)
        if len(ics) >= 36:
            t_ic, t_ls = hac_t(ics), hac_t(ls)
            ann = np.mean(ls) * 12 * 100
            score = int(abs(t_ic) >= 2) + int(abs(t_ls) >= 2) + int(ann > 3)
            mark = ["—", "△ 보류", "○ 후보", "★ 사전등록 권고"][min(score, 3)]
            print(f"  {name:<34}{np.mean(ics):+9.4f}{t_ic:>8.2f}{ann:>9.2f}%{t_ls:>8.2f}{len(ics):>6}  {mark}")
            out.append((name, np.mean(ics), t_ic, ann, t_ls, mark))
    return out

rank_mc = MC.rank(axis=1, ascending=False)
res_big = screen(rank_mc <= 300, "대형 (시총 top300) — 가치·코어 트랙 후보")
res_sml = screen((rank_mc > 300) & MC.notna(), "소·중형 (301+) — 성장·위성 트랙 후보")

print("\n" + "=" * 92)
print(" ★ = IN에서 유의(IC t≥2 & 롱숏 t≥2 & 연 3%+) → 사전등록 대상")
print(" ⚠️ 이 표는 우선순위 도구다. IN 성적은 OOS를 보장하지 않는다(IN-OOS Sharpe 상관 −0.709).")
print("=" * 92)

lines = ["# 매매기법 후보 1차 선별 — 탐색 결과 (IN 2002-2015)", "",
         "⚠️ **판정 아님.** OOS(2016~2026)는 봉인 유지. 이 표는 사전등록 우선순위용.", "",
         "## 대형(top300) — 가치/코어 트랙", "",
         "| 후보 | IC | HAC t | 롱숏 TR(연) | 롱숏 t | 판정 |", "|---|---:|---:|---:|---:|---|"]
for r in res_big: lines.append(f"| {r[0]} | {r[1]:+.4f} | {r[2]:.2f} | {r[3]:+.2f}% | {r[4]:.2f} | {r[5]} |")
lines += ["", "## 소·중형(301+) — 성장/위성 트랙", "",
          "| 후보 | IC | HAC t | 롱숏 TR(연) | 롱숏 t | 판정 |", "|---|---:|---:|---:|---:|---|"]
for r in res_sml: lines.append(f"| {r[0]} | {r[1]:+.4f} | {r[2]:.2f} | {r[3]:+.2f}% | {r[4]:.2f} | {r[5]} |")
lines += ["", "*재현: py 탐색_매매기법_후보선별.py · 투자자문 아님*"]
open(os.path.join(BASE, "탐색_기법후보_결과.md"), "w", encoding="utf-8").write("\n".join(lines) + "\n")
print(" 저장: 탐색_기법후보_결과.md")
