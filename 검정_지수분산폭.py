# -*- coding: utf-8 -*-
r"""검정_지수분산폭.py — 시장 전체 분산 폭(breadth) → 지수 하락 예측 (2026-07-29)

[아이디어] 개별 종목 분산 신호를 **시장 전체로 집계**하면 레짐 경보가 된다.
  "고점권 종목 중 몇 %에서 분산(대량+긴위꼬리)이 나오는가" = 시장 폭 지표.
  한두 종목이면 개별 이슈, 시장 전체가 동시에 분산하면 **꼭지**다.

[왜 필요한가 — 코어 방어 규칙의 약점]
  현행 방어는 KOSPI 10개월 MA다. 실측: 2026-05 고점 8,476 → 07 6,756 (−20%)인데
  10개월 MA(5,908)를 아직 안 깼다 → **방어 미발동**. 월봉 MA는 느리다.
  분산 폭은 **고점에서 켜지는** 지표라 선행성이 있는지 검정한다.

[지표] 매주:  분산폭 = (분산신호 발생 종목수) / (고점권 종목수)
       + 수급판:  분산 ∩ 외국인·기관 동시매도 비율
[검정] 분산폭 상위 분위 → 이후 4·8·13·26주 KOSPI 수익률 · −10%/−20% 하락 확률

⚠️ 과거통계. 투자자문 아님.
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

NEAR_HIGH, VOL_MULT, WICK_MIN, BODY_SMALL = 0.90, 1.50, 0.04, 0.03
PX_FLOOR, AMT_FLOOR = 1000, 1e8
HORIZONS = [4, 8, 13, 26]

print("=" * 100)
print(" 시장 분산 폭(breadth) → 지수 하락 예측 검정")
print("=" * 100)

W = pd.concat([pd.read_csv(_find(f"_주봉OHLCV_{m}_adj.csv"), dtype={"code": str})
               for m in ("KOSPI", "KOSDAQ")])
W["code"] = W["code"].str.zfill(6)
W = W.sort_values(["code", "date"]).reset_index(drop=True)
g = W.groupby("code")
W["hi52"]  = g["high"].transform(lambda s: s.rolling(52, min_periods=30).max())
W["volma"] = g["volume"].transform(lambda s: s.rolling(20, min_periods=12).mean())
W["body"]  = W["close"] / W["open"] - 1
W["wick"]  = (W["high"] - W[["open", "close"]].max(axis=1)) / W["high"]
W["amt"]   = W["close"] * W["volume"]
W["clean"] = (W["close"] >= PX_FLOOR) & (W["amt"] >= AMT_FLOOR)
W["nearhi"] = (W["close"] >= W["hi52"] * NEAR_HIGH) & W["clean"] & W["hi52"].notna() & W["volma"].notna()
W["sigB"]  = W["nearhi"] & (W["volume"] >= W["volma"] * VOL_MULT) & \
             (W["wick"] >= WICK_MIN) & (W["body"] <= BODY_SMALL)

# 수급 결합판
try:
    FL = pd.concat([pd.read_csv(_find(f"flow_ext_weekly_{m}.csv"), dtype={"code": str})
                    for m in ("KOSPI", "KOSDAQ")])
    FL.columns = [c.strip().lstrip("﻿") for c in FL.columns]
    FL["code"] = FL["code"].str.zfill(6)
    FL["wk"] = pd.to_datetime(FL["date"]).dt.strftime("%G-W%V")
    FL = FL.drop(columns=["date"]).groupby(["code", "wk"], as_index=False).sum()
    W["wk"] = pd.to_datetime(W["date"]).dt.strftime("%G-W%V")
    W = W.merge(FL, on=["code", "wk"], how="left")
    W["smart_out"] = (W["foreign_net"] < 0) & (W["inst_net"] < 0)
    HAS_FLOW = True
except Exception as e:
    W["smart_out"] = False; HAS_FLOW = False
    print(f"  (수급 결합 생략: {e})")

# ── 주별 분산 폭
bw = W[W["nearhi"]].groupby("date").agg(
    n_high=("code", "size"), n_sig=("sigB", "sum"),
    n_sig_flow=("smart_out", lambda s: 0)).reset_index()
sf = W[W["sigB"] & W["smart_out"].fillna(False)].groupby("date").size().rename("n_sf")
bw = bw.merge(sf, on="date", how="left")
bw["n_sf"] = bw["n_sf"].fillna(0)
bw = bw[bw["n_high"] >= 30].copy()
bw["분산폭"] = bw["n_sig"] / bw["n_high"] * 100
bw["분산폭_수급"] = bw["n_sf"] / bw["n_high"] * 100

# ── KOSPI 주간 종가
idx = pd.read_csv(_find("kospi_index_daily.csv"))
idx["d"] = pd.to_datetime(idx["Date"])
idx["date"] = idx["d"].dt.strftime("%Y-%m-%d")
iw = idx.set_index("d")["Close"].resample("W-FRI").last().dropna()
iw.index = iw.index.strftime("%Y-%m-%d")
bw = bw[bw["date"].isin(iw.index)].copy()
bw["kospi"] = bw["date"].map(iw)
for h in HORIZONS:
    bw[f"fwd{h}"] = bw["kospi"].shift(-h) / bw["kospi"] - 1
print(f"  주 표본 {len(bw):,} ({bw['date'].min()}~{bw['date'].max()}) · "
      f"평균 고점권 {bw['n_high'].mean():.0f}종목 · 평균 분산폭 {bw['분산폭'].mean():.2f}%")

def analyze(col, label):
    d = bw[bw[col].notna()].copy()
    if len(d) < 60: print(f"  {label}: 표본 부족"); return
    d["q"] = pd.qcut(d[col].rank(method="first"), 4, labels=["Q1(낮음)", "Q2", "Q3", "Q4(높음)"])
    print(f"\n{'─'*100}\n【{label}】 분위별 이후 KOSPI 수익률")
    print(f"  {'분위':<10}{'임계':<10}", end="")
    for h in HORIZONS: print(f"{f'{h}주':>10}", end="")
    print(f"{'−10%확률(8주)':>14}{'주수':>7}")
    for q in ["Q1(낮음)", "Q2", "Q3", "Q4(높음)"]:
        s = d[d["q"] == q]
        thr = f"{s[col].min():.1f}~{s[col].max():.1f}"
        print(f"  {q:<10}{thr:<10}", end="")
        for h in HORIZONS:
            v = s[f"fwd{h}"].dropna()
            print(f"{v.mean()*100:>9.2f}%", end="")
        p10 = (s["fwd8"].dropna() <= -0.10).mean() * 100
        print(f"{p10:>13.1f}%{len(s):>7}")
    hi = d[d["q"] == "Q4(높음)"]; lo = d[d["q"] == "Q1(낮음)"]
    print(f"\n  {'기간':<8}{'Q4 평균':>10}{'Q1 평균':>10}{'차이':>10}{'t':>8}   판정")
    for h in HORIZONS:
        a = hi[f"fwd{h}"].dropna(); b = lo[f"fwd{h}"].dropna()
        if len(a) < 20: continue
        t = stats.ttest_ind(a, b, equal_var=False).statistic
        flag = "🔴 유의" if (t <= -2) else ("△" if t <= -1.5 else "·")
        print(f"  {h:>3}주  {a.mean()*100:>9.2f}%{b.mean()*100:>9.2f}%{(a.mean()-b.mean())*100:>9.2f}%p{t:>8.2f}   {flag}")

analyze("분산폭", "분산 폭 (고점권 중 분산신호 비율)")
if HAS_FLOW: analyze("분산폭_수급", "분산 폭 × 스마트머니 이탈 (분산+외인·기관 동시매도)")

# ── 현재 수준
print(f"\n{'='*100}\n 현재 수준\n{'='*100}")
cur = bw.tail(10)[["date", "n_high", "분산폭", "분산폭_수급", "kospi"]]
p80 = bw["분산폭"].quantile(0.80); p95 = bw["분산폭"].quantile(0.95)
print(f"  분산폭 임계: 80분위 {p80:.2f}% · 95분위 {p95:.2f}%")
print(f"\n  {'주':<12}{'고점권':>8}{'분산폭':>9}{'수급결합':>10}{'KOSPI':>10}  상태")
for _, r in cur.iterrows():
    st = "🔴 경보(95분위+)" if r["분산폭"] >= p95 else ("🟡 주의(80분위+)" if r["분산폭"] >= p80 else "🟢")
    print(f"  {r['date']:<12}{r['n_high']:>8.0f}{r['분산폭']:>8.2f}%{r['분산폭_수급']:>9.2f}%{r['kospi']:>10,.0f}  {st}")

bw.to_csv(os.path.join(BASE, "_지수분산폭_시계열.csv"), index=False, encoding="utf-8-sig")
print(f"\n  저장: _지수분산폭_시계열.csv")
print("=" * 100)
