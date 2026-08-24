# -*- coding: utf-8 -*-
r"""검정_신규상장_효과.py — 신규 상장 종목을 쫓는 것이 이득인가 (2026-07-28)

[문제] "새로 상장한 회사를 내가 모르고 지나간다" → 놓치는 게 손해인가, 다행인가?
  학술 통설(Ritter 1991, IPO long-run underperformance)은 신규상장이 장기 언더퍼폼이라 말한다.
  한국 데이터에서 직접 잰다. 결과가 규칙을 정한다:
    · 신규가 초과수익 → 발굴 체계를 만들어 빨리 편입해야 한다
    · 신규가 언더퍼폼 → **모르고 지나간 것이 이득**이었고, 규칙은 '관찰 대기'가 된다

[측정] 상장 경과월(age) = 패널 최초 등장 이후 개월 수
  · age 구간별 다음달 수익률(동일가중) · 변동성 · 상폐율
  · 좌측절단 방지: 패널 시작(1996-01)에 이미 존재한 코드는 age 불명 → 제외
  · 수익률은 KIS 수정주가(상폐 포함·마스크 적용)

⚠️ 탐색·측정. 투자자문 아님.
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

P = kis.pivot_table(index="ym", columns="code", values="close", aggfunc="last").sort_index()
_i = pd.to_datetime(P.index + "-01"); MIv = (_i.year * 12 + _i.month).values
R = P.pct_change(); R[np.r_[True, np.diff(MIv) != 1]] = np.nan
fwd = R.shift(-1)

first_mi = {}
for c in P.columns:
    s = P[c].dropna()
    if len(s): first_mi[c] = MIv[list(P.index).index(s.index[0])]
PANEL_START = MIv[0]
censored = {c for c, v in first_mi.items() if v <= PANEL_START + 1}   # 좌측절단 제외
print("=" * 88)
print(" 신규 상장 효과 — 새 종목을 쫓는 것이 이득인가")
print("=" * 88)
print(f"  전체 코드 {len(P.columns):,} · 좌측절단(패널 시작 시 존재) 제외 {len(censored):,} "
      f"→ 분석대상 {len(P.columns)-len(censored):,}")

BUCKETS = [(0, 6, "0~6개월 (갓 상장)"), (6, 12, "6~12개월"), (12, 24, "12~24개월"),
           (24, 36, "24~36개월"), (36, 60, "36~60개월"), (60, 9999, "60개월+ (기성)")]

rows = []
for i, ym in enumerate(P.index):
    if ym < "2002-01" or ym > "2015-11": continue
    mi = MIv[i]
    r = fwd.loc[ym]
    for lo, hi, lbl in BUCKETS:
        cs = [c for c in P.columns if c not in censored
              and c in first_mi and lo <= (mi - first_mi[c]) < hi]
        if not cs: continue
        v = r.reindex(cs).dropna()
        if len(v) >= 5:
            rows.append((ym, lbl, v.mean(), len(v), v.std()))

df = pd.DataFrame(rows, columns=["ym", "b", "ret", "n", "sd"])
base = df[df["b"] == "60개월+ (기성)"].set_index("ym")["ret"]

print(f"\n  {'상장 경과':<22}{'월평균':>9}{'연환산':>9}{'HAC t':>8}{'기성대비':>10}{'초과 t':>8}{'평균종목수':>10}{'월변동성':>9}")
out = []
for lo, hi, lbl in BUCKETS:
    s = df[df["b"] == lbl].set_index("ym")
    if len(s) < 36: continue
    t = hac_t(s["ret"].values)
    ex = (s["ret"] - base.reindex(s.index)).dropna()
    tex = hac_t(ex.values) if len(ex) >= 36 else np.nan
    ann = ((1 + s["ret"].mean()) ** 12 - 1) * 100
    print(f"  {lbl:<22}{s['ret'].mean()*100:>8.3f}%{ann:>8.2f}%{t:>8.2f}"
          f"{ex.mean()*12*100:>9.2f}%{tex:>8.2f}{s['n'].mean():>10.0f}{s['sd'].mean()*100:>8.2f}%")
    out.append((lbl, s["ret"].mean(), ann, t, ex.mean() * 12 * 100, tex, s["n"].mean(), s["sd"].mean()))

# 상폐율 — age별
print(f"\n  [소멸률] 상장 경과별 (해당 age 구간에서 데이터가 끊긴 비율)")
try:
    dl = pd.read_csv(_find("소멸_재분류_v1.csv"), dtype={"code": str})
    dl["code"] = dl["code"].str.zfill(6)
    dl["last_mi"] = dl["last_ym"].str[:4].astype(int) * 12 + dl["last_ym"].str[5:7].astype(int)
    life = []
    for _, r0 in dl.iterrows():
        c = r0["code"]
        if c in first_mi and c not in censored:
            life.append((c, r0["last_mi"] - first_mi[c], r0["cls"]))
    L = pd.DataFrame(life, columns=["code", "months", "cls"])
    L = L[L["months"] >= 0]
    for lo, hi, lbl in BUCKETS[:-1]:
        sub = L[(L["months"] >= lo) & (L["months"] < hi)]
        bad = sub["cls"].isin(["폭락형", "동결소멸"]).mean() * 100 if len(sub) else np.nan
        print(f"    {lbl:<22}소멸 {len(sub):>5}건 · 그중 부실(폭락+동결) {bad:>5.1f}%")
    early = L[L["months"] < 60]
    print(f"    → 상장 60개월 내 소멸 {len(early):,}건 / 전체 소멸 {len(L):,}건 "
          f"({len(early)/max(len(L),1)*100:.1f}%)")
except Exception as e:
    print(f"    (소멸 테이블 없음: {e})")

print("\n" + "=" * 88)
if out:
    young = [o for o in out if o[0].startswith("0~6")]
    old = [o for o in out if o[0].startswith("60")]
    if young and old:
        d = young[0][2] - old[0][2]
        print(f" 판정: 갓 상장(0~6M) 연 {young[0][2]:.2f}% vs 기성(60M+) 연 {old[0][2]:.2f}% "
              f"→ 격차 {d:+.2f}%p")
        print(f"        {'신규가 우위 — 발굴 체계 필요' if d > 3 else ('차이 없음/열위 — 관찰 대기가 합리적' if d < 3 else '')}")
print("=" * 88)
