# -*- coding: utf-8 -*-
r"""검정_일봉정밀_분산.py — 분산 신호 일봉 정밀화 · 시장별 (2026-07-30 KOSDAQ 추가)

[왜] 주봉은 5거래일을 뭉친다. 금요일까지 기다려야 신호가 뜨고, 주 안에서
     '어느 날' 분산이 났는지 모른다. 일봉이면 **최대 4일 빨리** 잡을 수 있다.

[검정할 것]
  ① 일봉 분산일(고점권 + 대량 + 긴 위꼬리)이 주봉 신호와 같은 예측력을 갖는가
  ② **연속/누적 분산일**(최근 10거래일 중 분산일 수)이 더 강한가
  ③ 일봉 신호가 주봉보다 **며칠 빠른가** (선행 일수 실측)

[정의 — 주봉과 동일 논리, 일 단위로]
  고점권 : 종가 ≥ 252일 고가 × 0.90
  대량   : 거래량 ≥ 60일 평균 × 2.0   (일봉은 변동이 크므로 2.0배 · 주봉 1.5와 구분)
  위꼬리 : (고가 − max(시가,종가)) / 고가 ≥ 0.03
  몸통   : 종가/시가 − 1 ≤ +0.02
  위생   : 종가 ≥ 1,000원 · 일 거래대금 ≥ 10억

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
    return None

NEAR_HIGH, VOL_MULT, WICK_MIN, BODY_SMALL = 0.90, 2.0, 0.03, 0.02
PX_FLOOR, AMT_FLOOR, CLIP = 1000, 10e8, 1.0
HZ = [20, 40, 65, 130]     # 거래일 ≈ 4·8·13·26주

print("=" * 100)
print(" 분산 신호 일봉 정밀화 — KOSPI")
print("=" * 100)

_fr = []
for _m in ("KOSPI", "KOSDAQ"):
    _p = _find(f"_일봉OHLCV_{_m}_adj.csv")
    if _p:
        _d = pd.read_csv(_p, dtype={"code": str}); _d["mkt"] = _m; _fr.append(_d)
        print(f"  {_m}: {len(_d):,}행 · {_d['code'].nunique():,}종목")
    else:
        print(f"  {_m}: 파일 없음 — 생략")
D = pd.concat(_fr, ignore_index=True)
D["code"] = D["code"].str.zfill(6)
D = D.sort_values(["code", "date"]).reset_index(drop=True)
print(f"  합계 {len(D):,}행 · {D['code'].nunique():,}종목 · {D['date'].min()}~{D['date'].max()}")

g = D.groupby("code")
D["hi252"] = g["high"].transform(lambda s: s.rolling(252, min_periods=120).max())
D["volma"] = g["volume"].transform(lambda s: s.rolling(60, min_periods=40).mean())
D["body"]  = D["close"] / D["open"] - 1
D["wick"]  = (D["high"] - D[["open", "close"]].max(axis=1)) / D["high"]
D["amt"]   = D["close"] * D["volume"]
D["clean"] = (D["close"] >= PX_FLOOR) & (D["amt"] >= AMT_FLOOR)
D["nearhi"] = (D["close"] >= D["hi252"] * NEAR_HIGH) & D["clean"] & D["hi252"].notna() & D["volma"].notna()
D["sig"] = D["nearhi"] & (D["volume"] >= D["volma"] * VOL_MULT) & \
           (D["wick"] >= WICK_MIN) & (D["body"] <= BODY_SMALL)
D["sig10"] = g["sig"].transform(lambda s: s.rolling(10, min_periods=10).sum())
for h in HZ:
    D[f"f{h}"] = g["close"].transform(lambda s: s.shift(-h) / s - 1).clip(-CLIP, CLIP)

ALLBASE = D[D["nearhi"]].copy()
RESULTS = {}

def ev(mask, label, ref=None):
    B = base[mask]; O = base[ref] if ref is not None else base[~base["sig"]]
    if len(B) < 40: print(f"  {label:<32} (표본 {len(B)} 부족)"); return None
    line = f"  {label:<32}n={len(B):>6,} "
    out = []
    for h in HZ:
        s = B[f"f{h}"].dropna(); o = O[f"f{h}"].dropna()
        if len(s) < 30: continue
        p1 = (s <= -0.20).mean(); p0 = (o <= -0.20).mean()
        pp = (len(s)*p1 + len(o)*p0)/(len(s)+len(o))
        se = np.sqrt(max(pp*(1-pp)*(1/len(s)+1/len(o)), 1e-18))
        z = (p1-p0)/se
        line += f"│{h:>3}일 {p1*100:>5.1f}%(×{p1/max(p0,1e-9):>4.2f} z{z:>5.2f})"
        out.append((h, p1, p0, z, len(s)))
    print(line); return out

for _MKT in ("전체", "KOSPI", "KOSDAQ"):
    base = ALLBASE if _MKT == "전체" else ALLBASE[ALLBASE["mkt"] == _MKT]
    if len(base) < 5000: continue
    print(f"\n{'='*100}\n【{_MKT}】 고점권 종목-일 {len(base):,} · "
          f"분산일 {int(base['sig'].sum()):,} ({base['sig'].mean()*100:.2f}%)")
    o0 = base[~base["sig"]]
    bl = f"  {'▸ 비교군(기준선)':<32}n={len(o0):>7,} "
    for h in HZ: bl += f"│{h:>3}일 {(o0[f'f{h}'].dropna()<=-0.20).mean()*100:>5.1f}%             "
    print(bl)
    r1 = ev(base["sig"], "① 분산일 1회")
    r2 = ev(base["sig10"] >= 2, "② 최근10일 분산 2회+")
    r3 = ev(base["sig10"] >= 3, "③ 최근10일 분산 3회+")
    RESULTS[_MKT] = (r1, r2, r3)
base = ALLBASE

# ── 선행성: 일봉 신호가 주봉보다 며칠 빠른가
print(f"\n{'─'*100}\n  [선행성] 일봉 분산일 → 그 주 주봉 신호까지의 거리")
b = base[base["sig"]].copy()
b["dow"] = pd.to_datetime(b["date"]).dt.dayofweek     # 0=월
cnt = b["dow"].value_counts().sort_index()
names = ["월", "화", "수", "목", "금"]
tot = cnt.sum()
print(f"  분산일이 발생한 요일 분포 (n={tot:,})")
for i in range(5):
    c = int(cnt.get(i, 0))
    lead = 4 - i
    print(f"    {names[i]}요일 {c:>6,}건 ({c/tot*100:>5.1f}%)  → 주봉(금 마감) 대비 **{lead}일 선행**")
wavg = sum((4 - i) * int(cnt.get(i, 0)) for i in range(5)) / max(tot, 1)
print(f"  ▶ 평균 선행 {wavg:.2f} 거래일 — 주봉을 기다리면 그만큼 늦게 안다")

print(f"\n{'='*100}\n 시장별 판정\n{'='*100}")
for hz, lbl in ((20, "20일 ≈ 4주"), (40, "40일 ≈ 8주")):
    print(f"\n  ▸ {lbl}  −20% 급락 배수")
    print(f"    {'시장':<10}{'① 분산일 1회':>24}{'② 10일내 2회+':>24}{'③ 10일내 3회+':>24}")
    for mk, rs in RESULTS.items():
        row = f"    {mk:<10}"
        for r in rs:
            m = [x for x in r if x[0] == hz] if r else []
            if m:
                _, p1, p0, z, n = m[0]
                tag = "OK" if z >= 2 else ("~" if z >= 1.5 else "x")
                row += f"{f'x{p1/max(p0,1e-9):.2f} z{z:.1f} n{n:,} {tag}':>24}"
            else: row += f"{'-':>24}"
        print(row)
import json
json.dump({k: [[list(map(float, x)) for x in r] if r else [] for r in v] for k, v in RESULTS.items()},
          open("_일봉분산_시장별결과.json", "w"), ensure_ascii=False)
print("\n  저장: _일봉분산_시장별결과.json")
print("=" * 100)
