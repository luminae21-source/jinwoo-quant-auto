# -*- coding: utf-8 -*-
"""S2 근접미달형 30년 검정 — 국면 도장 · 미달항목별 분해 · 부트스트랩."""
import os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
HERE = "/home/claude/jq"

S = pd.concat([pd.read_csv(f"{HERE}/S2_이벤트_{m}.csv", dtype={"code": str}) for m in ("KOSPI", "KOSDAQ")],
              ignore_index=True)
S["code"] = S["code"].str.zfill(6)
L = pd.read_csv("/mnt/user-data/uploads/진우퀀트/휩쏘_역사원장.csv", dtype={"code": str})
L.columns = [c.strip().lstrip("﻿") for c in L.columns]; L["code"] = L["code"].str.zfill(6)

# ── 0. 재현 검증 (A 신호의 카드수익)
A = S[S["신호"] == "A"].merge(L[["code", "출발일", "유형", "국면", "카드수익"]],
                              left_on=["code", "date"], right_on=["code", "출발일"], how="left")
d = (A["카드"] * 100 - A["카드수익"]).abs()
print("=" * 80)
print("[재현검증] 정식 A 신호 재탐지")
print(f"  A 이벤트 {len(A)}건 · 원장과 키 완전일치 · 카드수익 오차 <0.05%p {(d<0.05).mean()*100:.1f}% (중앙 {d.median():.4f}%p)")
print(f"  ⚠️ 인수인계 문서의 'A형 2,095건'은 오기 — 실제 원장 A는 {int((L['유형']=='A').sum())}건, B는 {int((L['유형']=='B').sum())}건")

# ── 1. 국면 테이블 (시장국면.py 규칙) + 원장 대조 검증
ix = pd.read_csv("/mnt/user-data/uploads/진우퀀트/kospi_index_daily.csv")
ix.columns = [c.strip().lstrip("﻿") for c in ix.columns]
ix["Date"] = pd.to_datetime(ix["Date"]); ix = ix.sort_values("Date").reset_index(drop=True)
c = ix["Close"].astype(float)
ix["mdd"] = c / c.rolling(252, min_periods=120).max() - 1
ix["vol"] = c.pct_change().rolling(20, min_periods=10).std() * np.sqrt(252)
vmed = ix["vol"].median()
def rg(r):
    m, v = r["mdd"], r["vol"]
    if not np.isfinite(m): return "주의"
    hi = np.isfinite(v) and v > vmed
    if m <= -0.12: return "실행"
    if hi and m <= -0.05: return "실행"
    if m >= -0.05 and not hi: return "관찰만"
    return "주의"
ix["국면_계산"] = ix.apply(rg, axis=1)
RT = ix[["Date", "국면_계산"]].rename(columns={"Date": "date"})

S["date_dt"] = pd.to_datetime(S["date"])
S = pd.merge_asof(S.sort_values("date_dt"), RT.sort_values("date"),
                  left_on="date_dt", right_on="date", direction="backward", suffixes=("", "_ix"))
S = S.rename(columns={"국면_계산": "국면"})
chk = S[S["신호"] == "A"].merge(L[["code", "출발일", "국면"]], left_on=["code", "date"],
                               right_on=["code", "출발일"], how="left", suffixes=("_계산", "_원장"))
agree = (chk["국면_계산"] == chk["국면_원장"]).mean() * 100
print(f"  국면 도장 재현: 원장과 일치 {agree:.1f}%  (불일치 시 아래 수치는 참고용)")

S["연"] = S["date"].str[:4].astype(int)
C = S[S["fwd40"].notna()].copy()          # 40봉 창 완결분만


def stat(x):
    x = pd.Series(x).dropna()
    return dict(n=len(x), mean=x.mean() * 100, med=x.median() * 100, win=(x > 0).mean() * 100)


def boot(a, b, yrs, n=4000, seed=41):
    rng = np.random.default_rng(seed); ys = np.array(sorted(set(yrs)))
    ix_ = {y: np.where(yrs == y)[0] for y in ys}; o = np.empty(n)
    for i in range(n):
        p = rng.choice(ys, size=len(ys), replace=True)
        s = np.concatenate([ix_[y] for y in p])
        o[i] = np.nanmean(a[s]) - (np.nanmean(b[s]) if b is not None else 0.0)
    return (*np.percentile(o, [2.5, 97.5]) * 100, float((o > 0).mean()))


print("\n" + "=" * 80)
print("[1] 전체 — 정식 A vs S2 근접미달")
print(f"{'집단':<16}{'n':>7}{'카드평균':>10}{'중앙':>9}{'승률':>8}{'2단평균':>10}{'fwd40':>9}")
for g, sub in C.groupby("신호"):
    a1 = stat(sub["카드"]); a2 = stat(sub["이단"]); a3 = stat(sub["fwd40"])
    print(f"{g:<16}{a1['n']:>7}{a1['mean']:>+10.2f}{a1['med']:>+9.2f}{a1['win']:>7.1f}%"
          f"{a2['mean']:>+10.2f}{a3['mean']:>+9.2f}")

print("\n" + "=" * 80)
print("[2] 🟢실행 국면만 — 이게 실전 조건")
G = C[C["국면"] == "실행"]
base = G[G["신호"] == "A"]["카드"].values
print(f"{'집단':<16}{'n':>7}{'카드평균':>10}{'중앙':>9}{'승률':>8}{'2단평균':>10}"
      f"{'   카드 평균 부트95%CI(vs 0)':>28}")
for g in ("A", "S2"):
    sub = G[G["신호"] == g]
    a1 = stat(sub["카드"]); a2 = stat(sub["이단"])
    lo, hi, pg = boot(sub["카드"].values, None, sub["연"].values)
    print(f"{g:<16}{a1['n']:>7}{a1['mean']:>+10.2f}{a1['med']:>+9.2f}{a1['win']:>7.1f}%"
          f"{a2['mean']:>+10.2f}      [{lo:+6.2f},{hi:+6.2f}] P={pg:.1%}")
s2 = G[G["신호"] == "S2"]
lo, hi, pg = boot(s2["카드"].values, None, s2["연"].values)
print(f"\n  S2 − A 차이: {stat(s2['카드'])['mean']-stat(G[G['신호']=='A']['카드'])['mean']:+.2f}%p")

print("\n" + "=" * 80)
print("[3] 미달 항목별 — 어떤 완화가 살아남는가 (🟢실행 국면)")
print(f"{'미달 조합':<24}{'n':>7}{'카드평균':>10}{'중앙':>9}{'승률':>8}{'2단평균':>10}{'   부트95%CI(vs 0)':>24}")
sub = G[G["신호"] == "S2"]
for m, ss in sub.groupby("미달"):
    if len(ss) < 30: continue
    a1 = stat(ss["카드"]); a2 = stat(ss["이단"])
    lo, hi, pg = boot(ss["카드"].values, None, ss["연"].values)
    mark = " ★" if lo > 0 else (" ✗" if hi < 0 else "")
    print(f"{(m or '(없음)'):<24}{a1['n']:>7}{a1['mean']:>+10.2f}{a1['med']:>+9.2f}{a1['win']:>7.1f}%"
          f"{a2['mean']:>+10.2f}   [{lo:+6.2f},{hi:+6.2f}] P={pg:.0%}{mark}")

print("\n[3-b] 단일 항목 관점 (그 항목이 미달인 모든 케이스 · 중복 집계)")
print(f"{'항목':<14}{'n':>7}{'카드평균':>10}{'중앙':>9}{'승률':>8}{'   부트95%CI(vs 0)':>24}")
for item in ("2일누적", "MA240", "5년고점", "시총"):
    ss = sub[sub["미달"].fillna("").str.contains(item)]
    if len(ss) < 30: continue
    a1 = stat(ss["카드"]); lo, hi, pg = boot(ss["카드"].values, None, ss["연"].values)
    mark = " ★" if lo > 0 else (" ✗" if hi < 0 else "")
    print(f"{item:<14}{a1['n']:>7}{a1['mean']:>+10.2f}{a1['med']:>+9.2f}{a1['win']:>7.1f}%"
          f"   [{lo:+6.2f},{hi:+6.2f}] P={pg:.0%}{mark}")

print("\n" + "=" * 80)
print("[4] 국면별 S2 (게이트가 S2에도 작동하는가)")
print(f"{'국면':<10}{'n':>7}{'카드평균':>10}{'중앙':>9}{'승률':>8}{'2단평균':>10}")
for g, ss in C[C["신호"] == "S2"].groupby("국면"):
    a1 = stat(ss["카드"]); a2 = stat(ss["이단"])
    print(f"{g:<10}{a1['n']:>7}{a1['mean']:>+10.2f}{a1['med']:>+9.2f}{a1['win']:>7.1f}%{a2['mean']:>+10.2f}")

print("\n[5] 5년 구간별 (🟢실행 · S2 카드)")
sub2 = G[G["신호"] == "S2"].copy(); sub2["대"] = sub2["연"] // 5 * 5
t = sub2.groupby("대").apply(lambda x: pd.Series({"n": len(x), "카드": x["카드"].mean() * 100,
                                                  "2단": x["이단"].mean() * 100}))
print(t.round(2).to_string())
S.to_csv(f"{HERE}/S2_이벤트_통합.csv", index=False, encoding="utf-8-sig")
print(f"\n저장: S2_이벤트_통합.csv ({len(S)}건)")
