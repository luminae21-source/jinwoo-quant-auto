# -*- coding: utf-8 -*-
r"""검정_배당_순환논리_분해.py — 배당 팩터에서 '기계적 몫'과 '진짜 알파'를 가른다 (2026-07-28)

[왜 이 검정이 필요한가 — 앞선 재검정의 자기비판]
  검정_배당이왕_재검정.py는 총수익 ret_tr = ret_px + DIV/12 로 예측력을 쟀다.
  그런데 정렬 기준이 바로 그 DIV다 → **고배당 종목은 정의상 수익률을 더 받는다.**
  배당수익률 스프레드가 4%p면 그중 4%p는 '예측'이 아니라 '항등식'이다.

[가르는 질문]
  고배당주는 **가격수익률도** 저배당주만큼 나오는가?
    · 그렇다 → 배당수익률 차이만큼이 순수 이득. "배당이 왕"은 옳다.
    · 아니다(가격이 배당만큼 덜 오른다) → 총수익은 같아지고 팩터는 허상이다.
  ⇒ 결정적 지표: **가격수익률(ret_px)만으로 잰 IC와 스프레드.**

[산출] ① DIV의 IC : 가격기준 vs 총수익기준 ② 이중정렬 스프레드 분해:
       실현 총수익 스프레드 = 가격 스프레드 + 배당수익률 스프레드(기계적 몫)
⚠️ 측정 도구. 투자자문 아님.
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

kis = pd.read_csv(_find("월봉_KIS_adj_v1_2026-07-28.csv"), dtype={"code": str})
kis["code"] = kis["code"].str.zfill(6)
try:
    mk = pd.read_csv(_find("_패널마스크_v1.csv"), dtype={"code": str})
    ms = set(zip(mk["code"].str.zfill(6), mk["ym"]))
    kis = kis[[(c, y) not in ms for c, y in zip(kis["code"], kis["ym"])]]
except Exception: pass

fins = []
for mkt in ("KOSPI", "KOSDAQ"):
    fins.append(pd.read_csv(_find(f"종목재무_KRX_{mkt}.csv"), dtype={"code": str},
                            usecols=["date", "code", "BPS", "PBR", "PER", "EPS", "DIV", "DPS"]))
fin = pd.concat(fins); fin["code"] = fin["code"].str.zfill(6); fin["ym"] = fin["date"].str[:7]
for c in ("BPS", "PBR", "PER", "EPS", "DIV", "DPS"): fin[c] = pd.to_numeric(fin[c], errors="coerce")
fin["bp"] = np.where(fin["PBR"] > 0, 1 / fin["PBR"], np.nan)
fin["ep"] = np.where(fin["PER"] > 0, 1 / fin["PER"], np.nan)
fin["div"] = fin["DIV"].clip(0, 60)
fin = fin.groupby(["code", "ym"], as_index=False)[["div", "bp", "ep"]].last()

mc = pd.read_csv(_find("종목시총_30년.csv"), dtype={"code": str})
mc.columns = [c.strip().lstrip("﻿") for c in mc.columns]
mc["code"] = mc["code"].str.zfill(6); mc["ym"] = pd.to_datetime(mc["date"]).dt.strftime("%Y-%m")
mc["mcap"] = pd.to_numeric(mc["mcap"], errors="coerce")
mc = mc.groupby(["code", "ym"], as_index=False)["mcap"].last()

px = kis.sort_values(["code", "ym"]).copy()
_y = pd.to_datetime(px["ym"] + "-01"); px["_mi"] = _y.dt.year * 12 + _y.dt.month
g = px.groupby("code"); px["ret_px"] = g["close"].pct_change()
px.loc[g["_mi"].diff() != 1, "ret_px"] = np.nan

d = px[["code", "_mi", "ret_px"]].copy(); d["join_mi"] = d["_mi"] - 1
f = fin.copy(); _fy = pd.to_datetime(f["ym"] + "-01"); f["join_mi"] = _fy.dt.year * 12 + _fy.dt.month
m = d.merge(f.drop(columns=["ym"]), on=["code", "join_mi"], how="inner")
m2 = mc.copy(); _my = pd.to_datetime(m2["ym"] + "-01"); m2["join_mi"] = _my.dt.year * 12 + _my.dt.month
m = m.merge(m2[["code", "join_mi", "mcap"]], on=["code", "join_mi"], how="left")
m["ret_tr"] = m["ret_px"] + m["div"] / 100 / 12
m = m.dropna(subset=["ret_px"])
m["ymf"] = m["_mi"]
m["yy"] = (m["_mi"] // 12).astype(int)

print("=" * 86)
print(" 배당 팩터 — '기계적 몫' vs '진짜 알파' 분해")
print("=" * 86)

def block(df, label):
    print(f"\n{'─'*86}\n【{label}】 월 {df['ymf'].nunique()}개 · 관측 {len(df):,}")
    # ① IC: 가격기준 vs 총수익기준
    print("\n  ① DIV의 IC — 무엇으로 재느냐에 따라")
    for rk, rn in (("ret_px", "가격수익률만 (순수 예측)"), ("ret_tr", "총수익 (배당 포함=순환 위험)")):
        ics = []
        for _, gg in df.groupby("ymf"):
            s = gg[["div", rk]].dropna()
            if len(s) >= 30 and s["div"].nunique() > 5:
                v = stats.spearmanr(s["div"], s[rk]).statistic
                if np.isfinite(v): ics.append(v)
        if len(ics) >= 24:
            t = hac_t(ics)
            print(f"     {rn:<34}IC {np.mean(ics):+.4f}   HAC t {t:6.2f}   "
                  f"{'✅' if abs(t)>=2 else ('△' if abs(t)>=1.5 else '✗ 유의하지 않음')}")
    # ② 스프레드 분해 (B/P 통제 이중정렬)
    print("\n  ② 고배당(상위20%) − 저배당(하위20%) 스프레드 분해 · B/P 5분위 통제 · 연환산")
    rows = []
    for ym, gg in df.groupby("ymf"):
        s = gg[["div", "bp", "ret_px", "ret_tr"]].dropna()
        if len(s) < 100: continue
        s = s.copy(); s["q"] = pd.qcut(s["bp"].rank(method="first"), 5, labels=False)
        for q in range(5):
            t5 = s[s["q"] == q]
            if len(t5) < 20: continue
            hi = t5[t5["div"] >= t5["div"].quantile(0.8)]
            lo = t5[t5["div"] <= t5["div"].quantile(0.2)]
            rows.append((ym, hi["ret_px"].mean() - lo["ret_px"].mean(),
                         hi["ret_tr"].mean() - lo["ret_tr"].mean(),
                         hi["div"].mean() - lo["div"].mean()))
    if not rows:
        print("     (표본 부족)"); return
    dd = pd.DataFrame(rows, columns=["ym", "sp_px", "sp_tr", "dy_gap"]).groupby("ym").mean()
    t_px, t_tr = hac_t(dd["sp_px"].values), hac_t(dd["sp_tr"].values)
    mech = dd["dy_gap"].mean()          # 연 배당수익률 격차(%p) = 기계적 몫
    print(f"     {'배당수익률 격차 (고−저)':<34}{mech:+7.2f}%p/년   ← 기계적으로 보장되는 몫")
    print(f"     {'가격수익률 스프레드':<34}{dd['sp_px'].mean()*12*100:+7.2f}%/년    HAC t {t_px:6.2f}  "
          f"{'✅' if abs(t_px)>=2 else ('△' if abs(t_px)>=1.5 else '✗')}")
    print(f"     {'총수익 스프레드 (=위 둘의 합)':<34}{dd['sp_tr'].mean()*12*100:+7.2f}%/년    HAC t {t_tr:6.2f}  "
          f"{'✅' if abs(t_tr)>=2 else ('△' if abs(t_tr)>=1.5 else '✗')}")
    px_share = dd["sp_px"].mean() * 12 * 100
    print(f"\n     → 판정: 총수익 {dd['sp_tr'].mean()*12*100:+.2f}% 중 "
          f"기계적 몫 {mech:+.2f}%p · 가격알파 {px_share:+.2f}%p"
          f"  ({'가격도 밀리지 않음 → 배당 우위 실재' if px_share > -0.5 else '가격이 배당만큼 깎임 → 상쇄'})")

for lbl, sub in (("2008-2015 · 전 종목", m[m["_mi"] >= 2008 * 12 + 1]),
                 ("2008-2015 · 시총 top300 (코어 유니버스)",
                  m[(m["_mi"] >= 2008 * 12 + 1) &
                    (m.groupby("ymf")["mcap"].rank(ascending=False) <= 300)]),
                 ("2002-2015 · 시총 top300 (참고)",
                  m[m.groupby("ymf")["mcap"].rank(ascending=False) <= 300])):
    block(sub.copy(), lbl)

print("\n" + "=" * 86)
