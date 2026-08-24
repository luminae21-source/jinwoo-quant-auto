# -*- coding: utf-8 -*-
r"""검정_고점매도신호.py — "고점 대량매도" 신호 검정 (2026-07-29)

[가설 — 진우 인사이트]
  "고점에서 대량 매도가 나오는 장대음봉이 나오면 위험하다. 주봉이 중요하다."
  2026-07 삼성전자·SK하이닉스가 실제 사례.

[관찰에서 얻은 정제 — 두 가지를 나눠서 검정한다]
  실제 데이터를 보니 7월의 장대음봉(−6.5%·−10.9%·−10.5%)은 **이미 빠진 뒤**였다.
  거래량 급증은 그 **이전**에 나왔다 — 하이닉스 05-15(1.73x)·06-26(1.52x), 삼성 06-26(1.33x).
  그 주들은 몸통은 작은데 **위꼬리가 길었다**(고가에서 밀림) = 전형적 분산(distribution).

  ▸ 신호 A (원안·확인형) : 고점권 + 대량 + 장대음봉        → "이미 무너졌다"의 확인
  ▸ 신호 B (선행형)      : 고점권 + 대량 + 긴 위꼬리       → "무너지기 직전"의 경고
  둘 다 재고, **어느 쪽이 실제로 미래를 맞히는지** 본다.

[검정 설계]
  · 데이터: 주봉 수정 OHLCV (2013-01~2026-07 · KOSPI)
  · 비교군: **같은 고점권에 있으나 신호가 없는 종목-주** (고점권 자체의 효과를 제거)
  · 측정: 신호 후 4·8·13·26주 수익률 · 하락확률 · −20% 이상 급락 확률
  · 미래참조 없음: 신호는 t주 종가 확정 후 판정, 수익은 t+1주부터

⚠️ 과거통계. 투자자문 아님.
"""
import os, sys, argparse, warnings
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

# ── 파라미터 (사전 고정 — 스윕하지 않는다)
NEAR_HIGH = 0.90     # 종가 ≥ 52주 고점 × 90% → '고점권'
VOL_MULT  = 1.50     # 거래량 ≥ 20주 평균 × 1.5 → '대량'
BODY_DOWN = -0.05    # 몸통 ≤ −5% → '장대음봉'
WICK_MIN  = 0.04     # 위꼬리 ≥ 고가의 4% → '긴 위꼬리'
BODY_SMALL= 0.03     # 몸통 ≤ +3% (작거나 음) → 분산형
HORIZONS  = [4, 8, 13, 26]
PX_FLOOR  = 1000     # 종가 하한(원) — 주봉 CA 잔여물 차단 (실측: 1원 종가가 366만% 수익률 생성)
AMT_FLOOR = 1e8      # 주간 거래대금 하한(원) — 실제 거래 가능 종목만
CLIP      = 1.0      # 수익률 윈저화 ±100%

print("=" * 96)
print(" 고점 대량매도 신호 검정 — 주봉 (2013~2026 · KOSPI)")
print("=" * 96)

frames = []
for mkt in ("KOSPI", "KOSDAQ"):
    try:
        d = pd.read_csv(_find(f"_주봉OHLCV_{mkt}_adj.csv"), dtype={"code": str})
        d["mkt"] = mkt; frames.append(d)
        print(f"  {mkt}: {len(d):,}행 · {d['code'].nunique():,}종목")
    except FileNotFoundError:
        print(f"  {mkt}: 파일 없음 — 생략")
W = pd.concat(frames)
W["code"] = W["code"].str.zfill(6)
W = W.sort_values(["code", "date"]).reset_index(drop=True)
print(f"  합계: {len(W):,}행 · {W['code'].nunique():,}종목 · {W['date'].min()} ~ {W['date'].max()}")

g = W.groupby("code")
W["hi52"]   = g["high"].transform(lambda s: s.rolling(52, min_periods=30).max())
W["volma"]  = g["volume"].transform(lambda s: s.rolling(20, min_periods=12).mean())
W["body"]   = W["close"] / W["open"] - 1
W["wick"]   = (W["high"] - W[["open", "close"]].max(axis=1)) / W["high"]
W["nearhi"] = W["close"] >= W["hi52"] * NEAR_HIGH
W["bigvol"] = W["volume"] >= W["volma"] * VOL_MULT

for h in HORIZONS:
    W[f"fwd{h}"] = g["close"].transform(lambda s: s.shift(-h) / s - 1)

# ── 데이터 위생 (2026-07-29 추가): 저가 CA 잔여물·비유동 제거
W["amt"] = W["close"] * W["volume"]
W["clean"] = (W["close"] >= PX_FLOOR) & (W["amt"] >= AMT_FLOOR)
for h in HORIZONS:
    W[f"fwd{h}"] = W[f"fwd{h}"].clip(-CLIP, CLIP)

W["sigA"] = W["nearhi"] & W["bigvol"] & (W["body"] <= BODY_DOWN)
W["sigB"] = W["nearhi"] & W["bigvol"] & (W["wick"] >= WICK_MIN) & (W["body"] <= BODY_SMALL)

n_all = int((W["nearhi"] & W["hi52"].notna() & W["volma"].notna()).sum())
base = W[W["nearhi"] & W["hi52"].notna() & W["volma"].notna() & W["clean"]].copy()
print(f"\n  위생 필터: 종가≥{PX_FLOOR:,}원 & 주간거래대금≥{AMT_FLOOR/1e8:.0f}억 · 수익률 ±{CLIP*100:.0f}% 윈저")
print(f"    고점권 {n_all:,}건 → 정제 후 {len(base):,}건 ({len(base)/max(n_all,1)*100:.1f}% 유지)")
print(f"\n  고점권(52주고점 90%+) 종목-주: {len(base):,}건")
print(f"  신호 A (대량 장대음봉)      : {int(base['sigA'].sum()):,}건 ({base['sigA'].mean()*100:.2f}%)")
print(f"  신호 B (대량 긴위꼬리·분산) : {int(base['sigB'].sum()):,}건 ({base['sigB'].mean()*100:.2f}%)")

def report(col, label, sub=None):
    B = base if sub is None else base[sub]
    print(f"\n{'─'*96}\n【{label}】" + ("" if sub is None else f"  (n={len(B):,})"))
    print(f"  {'기간':<7}{'신호 중앙':>10}{'비교 중앙':>10}{'차이':>9}"
          f"{'신호 평균':>10}{'비교 평균':>10}{'t':>7}"
          f"{'하락확률':>10}{'비교':>8}{'−20%급락':>10}{'비교':>8}{'z':>7}")
    out = []
    for h in HORIZONS:
        s = B[B[col]][f"fwd{h}"].dropna()
        o = B[~B[col]][f"fwd{h}"].dropna()
        if len(s) < 30: continue
        t = stats.ttest_ind(s, o, equal_var=False).statistic
        p1 = (s <= -0.20).mean(); p0 = (o <= -0.20).mean()
        pp = (len(s)*p1 + len(o)*p0) / (len(s)+len(o))
        se = np.sqrt(max(pp*(1-pp)*(1/len(s)+1/len(o)), 1e-18))
        z = (p1 - p0) / se
        print(f"  {h:>3}주{s.median()*100:>9.2f}%{o.median()*100:>9.2f}%{(s.median()-o.median())*100:>8.2f}%p"
              f"{s.mean()*100:>9.2f}%{o.mean()*100:>9.2f}%{t:>7.2f}"
              f"{(s<0).mean()*100:>9.1f}%{(o<0).mean()*100:>7.1f}%{p1*100:>9.1f}%{p0*100:>7.1f}%{z:>7.2f}")
        out.append((h, s.median(), o.median(), t, len(s), z, p1, p0))
    return out

rA = report("sigA", "신호 A — 고점권 + 대량 + 장대음봉 (원안·확인형)")
rB = report("sigB", "신호 B — 고점권 + 대량 + 긴 위꼬리 (선행형)")

# 결합: A 또는 B
base["sigAB"] = base["sigA"] | base["sigB"]
rAB = report("sigAB", "신호 A∪B (둘 중 하나라도)")

# 대형주 한정 (진우 관심: 삼성전자·하이닉스급)
big = base["amt"] >= 500e8      # 주간 거래대금 500억+ = 대형·거래활발
if big.sum() > 500:
    report("sigAB", "신호 A∪B — 대형주 한정 (주간 거래대금 500억+)", sub=big)

print("\n" + "=" * 96)
print(" 판정")
print("=" * 96)
for nm, r in (("A 장대음봉", rA), ("B 위꼬리분산", rB), ("A∪B", rAB)):
    if not r: continue
    n_med = sum(1 for x in r if x[3] <= -2 and x[1] < x[2])       # 수익률이 유의하게 낮음
    n_crash = sum(1 for x in r if x[5] >= 2)                       # 급락확률이 유의하게 높음
    verdict = ("✅ 급락 경보로 유효 (수익률 예측은 별개)" if n_crash >= 3 and n_med < 2
               else ("✅ 수익률·급락 양쪽 유효" if n_med >= 2 and n_crash >= 2
                     else ("△ 급락확률만 부분 유효" if n_crash >= 2 else "❌ 예측력 없음")))
    print(f"  신호 {nm:<12}: 수익률 열위 {n_med}/{len(r)} · 급락확률 상승 {n_crash}/{len(r)}  → {verdict}")

# ── 연속 신호 (2주 이상 연속 대량매도)
base = base.sort_values(["code", "date"])
base["sigAB_prev"] = base.groupby("code")["sigAB"].shift(1).fillna(False)
base["연속"] = base["sigAB"] & base["sigAB_prev"]
if base["연속"].sum() >= 30:
    print(f"\n  [연속 신호] 2주 연속 발생 {int(base['연속'].sum()):,}건")
    for h in HORIZONS:
        s = base[base["연속"]][f"fwd{h}"].dropna()
        o = base[~base["sigAB"]][f"fwd{h}"].dropna()
        if len(s) < 30: continue
        t = stats.ttest_ind(s, o, equal_var=False).statistic
        print(f"     {h:>3}주: {s.mean()*100:+6.2f}% vs {o.mean()*100:+6.2f}% "
              f"(차 {(s.mean()-o.mean())*100:+5.2f}%p · t {t:+5.2f} · n {len(s):,})"
              f" {'🔴' if abs(t)>=2 and s.mean()<o.mean() else ''}")
print("=" * 96)
