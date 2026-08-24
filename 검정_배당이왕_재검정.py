# -*- coding: utf-8 -*-
r"""검정_배당이왕_재검정.py — "배당이 왕"의 근거 재검정 (2026-07-28)

[문제제기] 백서 4장 "배당이 왕"(IC +0.0487, t=5.9 · 롱숏 +3.4%/년)의 근거가 약한가?

[핵심 의심 — 대수 항등식]
    배당수익률 DIV = DPS/P
    B/P = BPS/P
    ⇒ DIV = (BPS/P) × (DPS/BPS) = **B/P × 배당성향(장부기준)**

  즉 배당수익률은 구조적으로 '가치(B/P)'를 품고 있다. 주가가 떨어지면 DIV는 기계적으로 오른다.
  따라서 "배당이 왕"은 **"가치가 왕이고 배당은 그 그림자"** 일 가능성이 있다.
  이걸 가르는 시험: **가격이 안 들어간 성분(DPS/BPS)만으로 예측력이 있는가?**

[검정 설계 — 사전 선언]
  A. 원팩터 IC (Spearman, HAC t) : DIV · B/P · E/P · ROE · DPS/BPS
  B. 직교화 IC : DIV를 B/P·E/P에 회귀한 **잔차**의 IC (가치 제거 후 배당의 순수 예측력)
  C. 이중정렬 : B/P 5분위 내부에서 DIV 상하위 스프레드 (가치 통제)
  D. 순수 성분 : DPS/BPS(가격 무관) 단독 IC — 0에 가까우면 "배당이 왕"은 반증
  E. 견고성 : 기간(2008+ vs 전체) · 유니버스(top300 vs 전체) 분할

[데이터] 월봉_KIS_adj_v1(수정주가·1996~2015) + 종목재무_KRX(2002~) + TR(배당 가산)
  · KIS 커버리지 90%+ 구간은 2008+ → **주 판정은 2008-2015**, 2002+는 참고
  · 팩터는 직전월 스냅샷(look-ahead 없음) · 수익률은 다음달 TR

사용: py 검정_배당이왕_재검정.py
⚠️ 측정 도구. 투자자문 아님.
"""
import os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd
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
    """Newey-West HAC t (평균이 0인지). 월간 IC 시계열의 자기상관 보정."""
    x = np.asarray(pd.Series(x).dropna(), float)
    n = len(x)
    if n < 12: return np.nan
    m = x.mean(); e = x - m
    g0 = (e @ e) / n
    v = g0
    for L in range(1, min(lags, n - 1) + 1):
        gl = (e[L:] @ e[:-L]) / n
        v += 2 * (1 - L / (lags + 1)) * gl
    se = np.sqrt(max(v, 1e-18) / n)
    return m / se

print("=" * 84)
print(' "배당이 왕" 재검정 — 가치(B/P)를 통제하면 배당이 남는가')
print("=" * 84)

# ── 데이터
kis = pd.read_csv(_find("월봉_KIS_adj_v1_2026-07-28.csv"), dtype={"code": str})
kis["code"] = kis["code"].str.zfill(6)
try:
    mask = pd.read_csv(_find("_패널마스크_v1.csv"), dtype={"code": str})
    mset = set(zip(mask["code"].str.zfill(6), mask["ym"]))
    kis = kis[[(c, y) not in mset for c, y in zip(kis["code"], kis["ym"])]]
except Exception:
    pass

fins = []
for mkt in ("KOSPI", "KOSDAQ"):
    f = pd.read_csv(_find(f"종목재무_KRX_{mkt}.csv"), dtype={"code": str},
                    usecols=["date", "code", "BPS", "PER", "PBR", "EPS", "DIV", "DPS"])
    fins.append(f)
fin = pd.concat(fins)
fin["code"] = fin["code"].str.zfill(6)
fin["ym"] = fin["date"].str[:7]
for c in ("BPS", "PER", "PBR", "EPS", "DIV", "DPS"):
    fin[c] = pd.to_numeric(fin[c], errors="coerce")
fin["bp"]  = np.where(fin["PBR"] > 0, 1 / fin["PBR"], np.nan)
fin["ep"]  = np.where(fin["PER"] > 0, 1 / fin["PER"], np.nan)
fin["roe"] = np.where(fin["BPS"] > 0, fin["EPS"] / fin["BPS"], np.nan)
fin["div"] = fin["DIV"].clip(0, 60)
# ★ 가격이 들어가지 않은 순수 배당 성분: 장부 대비 배당 (DPS/BPS)
fin["dps_bps"] = np.where(fin["BPS"] > 0, fin["DPS"] / fin["BPS"], np.nan)
fin = fin.groupby(["code", "ym"], as_index=False)[["div", "bp", "ep", "roe", "dps_bps"]].last()

mc = pd.read_csv(_find("종목시총_30년.csv"), dtype={"code": str})
mc.columns = [c.strip().lstrip("﻿") for c in mc.columns]
mc["code"] = mc["code"].str.zfill(6)
mc["ym"] = pd.to_datetime(mc["date"]).dt.strftime("%Y-%m")
mc["mcap"] = pd.to_numeric(mc["mcap"], errors="coerce")
mc = mc.groupby(["code", "ym"], as_index=False)["mcap"].last()

# ── 다음달 TR 수익률 (배당 가산: 직전월 DIV/12)
px = kis.sort_values(["code", "ym"]).copy()
ymi = pd.to_datetime(px["ym"] + "-01")
px["_mi"] = ymi.dt.year * 12 + ymi.dt.month
g = px.groupby("code")
px["ret"] = g["close"].pct_change()
px.loc[g["_mi"].diff() != 1, "ret"] = np.nan
px["ym_prev"] = (px["_mi"] - 1)

d = px[["code", "ym", "_mi", "ret"]].copy()
d["join_mi"] = d["_mi"] - 1                    # 팩터는 직전월
f = fin.copy()
fymi = pd.to_datetime(f["ym"] + "-01")
f["join_mi"] = fymi.dt.year * 12 + fymi.dt.month
m = d.merge(f.drop(columns=["ym"]), on=["code", "join_mi"], how="inner")
m["ret_tr"] = m["ret"] + m["div"] / 100 / 12
mc2 = mc.copy()
mymi = pd.to_datetime(mc2["ym"] + "-01")
mc2["join_mi"] = mymi.dt.year * 12 + mymi.dt.month
m = m.merge(mc2[["code", "join_mi", "mcap"]], on=["code", "join_mi"], how="left")
m["ym_fwd"] = pd.to_datetime(m["_mi"].apply(lambda x: f"{x//12}-{x%12 or 12}-01".replace("-0-", "-12-")),
                             errors="coerce").dt.strftime("%Y-%m")
m = m.dropna(subset=["ret_tr"])
m["ymf"] = m["_mi"]

FACTORS = [("div", "배당수익률 DIV"), ("bp", "가치 B/P"), ("ep", "이익수익률 E/P"),
           ("roe", "수익성 ROE"), ("dps_bps", "★순수배당 DPS/BPS(가격무관)")]

def run_block(df, label, univ_note):
    print(f"\n{'─'*84}\n【{label}】 {univ_note}")
    n_m = df["ymf"].nunique()
    print(f"  월 {n_m}개 · 관측 {len(df):,}")
    if n_m < 24:
        print("  (표본 부족 — 생략)"); return None
    out = {}
    # A. 원팩터 IC
    print(f"\n  A. 원팩터 IC (Spearman, 월간 평균 · HAC t, lag6)")
    print(f"     {'팩터':<28}{'IC':>9}{'HAC t':>9}{'월수':>7}")
    for key, nm in FACTORS:
        ics = []
        for ym, gg in df.groupby("ymf"):
            s = gg[[key, "ret_tr"]].dropna()
            if len(s) >= 30 and s[key].nunique() > 5:
                _v = stats.spearmanr(s[key], s["ret_tr"]).statistic
                if np.isfinite(_v): ics.append(_v)
        if len(ics) >= 24:
            t = hac_t(ics)
            out[key] = (np.mean(ics), t, len(ics))
            flag = "✅" if abs(t) >= 2 else ("△" if abs(t) >= 1.5 else "✗")
            print(f"     {nm:<28}{np.mean(ics):+9.4f}{t:>9.2f}{len(ics):>7}  {flag}")
    # B. 직교화 — DIV에서 B/P·E/P 설명분 제거
    print(f"\n  B. 직교화 IC — DIV ⟂ (B/P, E/P) 잔차의 예측력  ← 핵심")
    ics_o, ics_bp_o = [], []
    for ym, gg in df.groupby("ymf"):
        s = gg[["div", "bp", "ep", "ret_tr"]].dropna()
        if len(s) < 30: continue
        R = s[["div", "bp", "ep"]].rank(pct=True)
        X = np.c_[np.ones(len(s)), R["bp"], R["ep"]]
        try:
            beta = np.linalg.lstsq(X, R["div"].values, rcond=None)[0]
            resid = R["div"].values - X @ beta
            ics_o.append(stats.spearmanr(resid, s["ret_tr"]).statistic)
            # 반대 방향: B/P ⟂ DIV
            X2 = np.c_[np.ones(len(s)), R["div"], R["ep"]]
            b2 = np.linalg.lstsq(X2, R["bp"].values, rcond=None)[0]
            r2 = R["bp"].values - X2 @ b2
            ics_bp_o.append(stats.spearmanr(r2, s["ret_tr"]).statistic)
        except Exception:
            pass
    if len(ics_o) >= 24:
        t_o, t_b = hac_t(ics_o), hac_t(ics_bp_o)
        print(f"     {'DIV ⟂ 가치 (배당 순수분)':<28}{np.mean(ics_o):+9.4f}{t_o:>9.2f}{len(ics_o):>7}  "
              f"{'✅' if abs(t_o)>=2 else ('△' if abs(t_o)>=1.5 else '✗')}")
        print(f"     {'B/P ⟂ 배당 (가치 순수분)':<28}{np.mean(ics_bp_o):+9.4f}{t_b:>9.2f}{len(ics_bp_o):>7}  "
              f"{'✅' if abs(t_b)>=2 else ('△' if abs(t_b)>=1.5 else '✗')}")
        out["_orth"] = (np.mean(ics_o), t_o, np.mean(ics_bp_o), t_b)
    # C. 이중정렬 — B/P 5분위 내 DIV 상·하위 스프레드
    print(f"\n  C. 이중정렬 — B/P 5분위 '내부'에서 배당 상위20% − 하위20% (월평균, %)")
    rows = []
    for ym, gg in df.groupby("ymf"):
        s = gg[["div", "bp", "ret_tr"]].dropna()
        if len(s) < 100: continue
        s = s.copy()
        s["bpq"] = pd.qcut(s["bp"].rank(method="first"), 5, labels=False)
        for q in range(5):
            t5 = s[s["bpq"] == q]
            if len(t5) < 20: continue
            hi = t5[t5["div"] >= t5["div"].quantile(0.8)]["ret_tr"].mean()
            lo = t5[t5["div"] <= t5["div"].quantile(0.2)]["ret_tr"].mean()
            rows.append((ym, q, hi - lo))
    if rows:
        dd = pd.DataFrame(rows, columns=["ym", "q", "sp"])
        print(f"     {'B/P 분위':<12}{'월평균 스프레드':>14}{'연환산':>10}{'HAC t':>9}")
        for q in range(5):
            v = dd[dd["q"] == q]["sp"]
            if len(v) >= 24:
                t = hac_t(v.values)
                lab = ["Q1(비쌈)", "Q2", "Q3", "Q4", "Q5(쌈)"][q]
                print(f"     {lab:<12}{v.mean()*100:>13.3f}%{v.mean()*12*100:>9.2f}%{t:>9.2f}  "
                      f"{'✅' if abs(t)>=2 else ('△' if abs(t)>=1.5 else '✗')}")
        allv = dd.groupby("ym")["sp"].mean()
        t = hac_t(allv.values)
        print(f"     {'── 전분위 평균':<12}{allv.mean()*100:>13.3f}%{allv.mean()*12*100:>9.2f}%{t:>9.2f}  "
              f"{'✅' if abs(t)>=2 else ('△' if abs(t)>=1.5 else '✗')}")
        out["_dsort"] = (allv.mean() * 12, t)
    return out

# ── 유니버스·기간 분할
res = {}
for lbl, sub in (("2008-2015 · 커버리지 90%+ (주 판정)", m[m["ym"] >= "2008-01"]),
                 ("2002-2015 · 전체 (참고 · 생존편향 잔존)", m)):
    for uname, f_u in (("전 종목", lambda x: x),
                       ("시총 top300 (코어 유니버스)",
                        lambda x: x[x.groupby("ymf")["mcap"].rank(ascending=False) <= 300])):
        key = f"{lbl} | {uname}"
        res[key] = run_block(f_u(sub).copy(), lbl, uname)

print("\n" + "=" * 84)
print(" 저장: 배당이왕_재검정_결과.md")
print("=" * 84)
