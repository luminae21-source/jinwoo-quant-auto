# -*- coding: utf-8 -*-
r"""검정_수급결합_분산신호.py — 분산 신호 + 수급(외국인·기관) 결합 검정 (2026-07-29)

[가설] "고점 대량매도"에서 **누가 팔았는지**를 알면 신호가 정밀해진다.
  분산 신호 B(고점권+대량+긴위꼬리)에 **외국인·기관 순매도**를 결합하면
  급락 확률 예측이 더 좋아지는가?

[데이터] 주간 수급 (foreign_net · inst_net) 2019-01~2026-07 · KOSPI+KOSDAQ
        주봉 수정 OHLCV 2013~2026 (겹치는 2019+ 구간에서 검정)

[비교 대상 — 전부 같은 고점권 표본 안에서]
  ① 신호 B 단독
  ② 신호 B + 외국인 순매도
  ③ 신호 B + 기관 순매도
  ④ 신호 B + 외국인·기관 동시 순매도   ← '스마트머니 이탈'
  ⑤ 수급만 (외국인·기관 동시 순매도, 분산 신호 없이)  ← 수급 단독 효과 분리

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
PX_FLOOR, AMT_FLOOR, CLIP = 1000, 1e8, 1.0
HORIZONS = [4, 8, 13, 26]

print("=" * 100)
print(" 분산 신호 + 수급 결합 검정 — 주봉 2019~2026")
print("=" * 100)

W = pd.concat([pd.read_csv(_find(f"_주봉OHLCV_{m}_adj.csv"), dtype={"code": str})
               for m in ("KOSPI", "KOSDAQ")])
W["code"] = W["code"].str.zfill(6)
W = W.sort_values(["code", "date"]).reset_index(drop=True)

F = []
for m in ("KOSPI", "KOSDAQ"):
    d = pd.read_csv(_find(f"flow_ext_weekly_{m}.csv"), dtype={"code": str})
    d.columns = [c.strip().lstrip("﻿") for c in d.columns]
    F.append(d)
FL = pd.concat(F); FL["code"] = FL["code"].str.zfill(6)
for c in ("foreign_net", "inst_net"): FL[c] = pd.to_numeric(FL[c], errors="coerce")
print(f"  주봉 {len(W):,}행 · 수급 {len(FL):,}행 ({FL['date'].min()}~{FL['date'].max()})")

g = W.groupby("code")
W["hi52"]  = g["high"].transform(lambda s: s.rolling(52, min_periods=30).max())
W["volma"] = g["volume"].transform(lambda s: s.rolling(20, min_periods=12).mean())
W["body"]  = W["close"] / W["open"] - 1
W["wick"]  = (W["high"] - W[["open", "close"]].max(axis=1)) / W["high"]
W["amt"]   = W["close"] * W["volume"]
for h in HORIZONS:
    W[f"fwd{h}"] = g["close"].transform(lambda s: s.shift(-h) / s - 1).clip(-CLIP, CLIP)
W["sigB"] = (W["close"] >= W["hi52"] * NEAR_HIGH) & (W["volume"] >= W["volma"] * VOL_MULT) & \
            (W["wick"] >= WICK_MIN) & (W["body"] <= BODY_SMALL)
W["nearhi"] = W["close"] >= W["hi52"] * NEAR_HIGH
W["clean"] = (W["close"] >= PX_FLOOR) & (W["amt"] >= AMT_FLOOR)

# 주차 정렬: 주봉=금요일 마감 · 수급=일요일 라벨 → ISO 주차로 통일
W["wk"] = pd.to_datetime(W["date"]).dt.strftime("%G-W%V")
FL["wk"] = pd.to_datetime(FL["date"]).dt.strftime("%G-W%V")
_fl = FL.drop(columns=["date"]).groupby(["code", "wk"], as_index=False).sum()
M = W.merge(_fl, on=["code", "wk"], how="inner")
base = M[M["nearhi"] & M["hi52"].notna() & M["volma"].notna() & M["clean"] &
         M["foreign_net"].notna() & M["inst_net"].notna()].copy()
# 순매도 강도: 거래대금 대비 (규모 정규화)
base["f_ratio"] = base["foreign_net"] / base["amt"]
base["i_ratio"] = base["inst_net"] / base["amt"]
base["f_sell"] = base["foreign_net"] < 0
base["i_sell"] = base["inst_net"] < 0
base["both_sell"] = base["f_sell"] & base["i_sell"]

print(f"  수급 매칭 고점권 표본: {len(base):,}건 ({base['date'].min()}~{base['date'].max()})")
print(f"    신호B {int(base['sigB'].sum()):,} · 외국인순매도 {int(base['f_sell'].sum()):,} "
      f"· 기관순매도 {int(base['i_sell'].sum()):,} · 동시순매도 {int(base['both_sell'].sum()):,}")

def ev(mask, label):
    B = base[mask]; O = base[~base["sigB"] & ~base["both_sell"]]   # 깨끗한 비교군
    if len(B) < 40:
        print(f"  {label:<34} (표본 {len(B)} — 부족)"); return None
    out = []
    line = f"  {label:<34}n={len(B):>6,} "
    for h in HORIZONS:
        s = B[f"fwd{h}"].dropna(); o = O[f"fwd{h}"].dropna()
        if len(s) < 30: continue
        p1 = (s <= -0.20).mean(); p0 = (o <= -0.20).mean()
        pp = (len(s)*p1 + len(o)*p0) / (len(s)+len(o))
        se = np.sqrt(max(pp*(1-pp)*(1/len(s)+1/len(o)), 1e-18))
        z = (p1 - p0) / se
        line += f"│{h:>2}주 {p1*100:>5.1f}%(×{p1/max(p0,1e-9):>4.2f} z{z:>5.2f})"
        out.append((h, p1, p0, z, len(s)))
    print(line)
    return out

print(f"\n{'─'*100}\n  −20% 급락 확률 (비교군 = 신호도 동시순매도도 없는 고점권)")
o0 = base[~base["sigB"] & ~base["both_sell"]]
bl = "  " + f"{'▸ 비교군(기준선)':<34}n={len(o0):>6,} "
for h in HORIZONS:
    bl += f"│{h:>2}주 {(o0[f'fwd{h}'].dropna() <= -0.20).mean()*100:>5.1f}%              "
print(bl)
print()
r1 = ev(base["sigB"], "① 신호B 단독")
r2 = ev(base["sigB"] & base["f_sell"], "② 신호B + 외국인 순매도")
r3 = ev(base["sigB"] & base["i_sell"], "③ 신호B + 기관 순매도")
r4 = ev(base["sigB"] & base["both_sell"], "④ 신호B + 외국인·기관 동시매도")
r5 = ev(base["both_sell"] & ~base["sigB"], "⑤ 동시순매도만 (신호B 없이)")

# 순매도 강도 상위
thr_f = base["f_ratio"].quantile(0.10)   # 거래대금 대비 순매도 강한 하위10%
thr_i = base["i_ratio"].quantile(0.10)
r6 = ev(base["sigB"] & (base["f_ratio"] <= thr_f), "⑥ 신호B + 외국인 강한매도(하위10%)")
r7 = ev(base["sigB"] & (base["f_ratio"] <= thr_f) & (base["i_ratio"] <= thr_i),
        "⑦ 신호B + 양쪽 강한매도(각 하위10%)")

print(f"\n{'='*100}\n 판정\n{'='*100}")
best = None
for nm, r in (("① 신호B 단독", r1), ("② +외국인매도", r2), ("③ +기관매도", r3),
              ("④ +동시매도", r4), ("⑤ 수급만", r5), ("⑥ +외인강매도", r6), ("⑦ +양쪽강매도", r7)):
    if not r: continue
    m8 = [x for x in r if x[0] == 8]
    mult = m8[0][1] / max(m8[0][2], 1e-9) if m8 else np.nan
    zz = m8[0][3] if m8 else np.nan
    n = m8[0][4] if m8 else 0
    tag = "✅" if zz >= 2 else ("△" if zz >= 1.5 else "·")
    print(f"  {nm:<20} 8주 급락배수 ×{mult:>4.2f} (z {zz:>5.2f} · n {n:>5,}) {tag}")
    if zz >= 2 and (best is None or mult > best[1]): best = (nm, mult, zz, n)
if best:
    print(f"\n  ▶ 최고 조합: {best[0]} — 급락 확률 기준선의 **×{best[1]:.2f}배** (z {best[2]:.2f}, n {best[3]:,})")
print("=" * 100)
