# -*- coding: utf-8 -*-
"""2단 청산 검정 — 결과 집계·재현검증·부트스트랩."""
import os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

HERE = "/home/claude/jq"
M = pd.read_csv(os.path.join(HERE, "휩쏘_2단청산_이벤트.csv"), dtype={"code": str})
M["연"] = M["출발일"].str[:4].astype(int)

# ── 0. 재현 검증: P0 vs 원장 카드수익 ──────────────────────────────
ok = M["카드수익"].notna() & M["P0_카드"].notna()
d = (M.loc[ok, "P0_카드"] * 100 - M.loc[ok, "카드수익"]).abs()
print("=" * 72)
print("[재현검증] P0_카드 vs 원장 카드수익")
print(f"  n={ok.sum()} · 완전일치(<0.05%p) {(d < 0.05).mean()*100:.1f}% · 중앙오차 {d.median():.4f}%p · 최대 {d.max():.3f}%p")
print(f"  원장 평균 {M.loc[ok,'카드수익'].mean():+.2f}%  vs  재현 평균 {M.loc[ok,'P0_카드'].mean()*100:+.2f}%")

C = M[M["창완결_126"] == True].copy()
print(f"\n[표본] 전체 {len(M)}건 · 126봉 창완결 {len(C)}건")
print(f"  6M 고점 평균 {C['고점6M'].mean()*100:+.1f}% · 중앙 {C['고점6M'].median()*100:+.1f}%")
print(f"  P0 카드 평균 {C['P0_카드'].mean()*100:+.1f}% · 중앙 {C['P0_카드'].median()*100:+.1f}%")
gap = C["고점6M"].mean() * 100 - C["P0_카드"].mean() * 100
print(f"  → 간극 {gap:+.1f}%p  (이 중 얼마를 2단이 회수하는가)")

hit = (C["P0_how"] == "목표")
print(f"\n[분기점] 40봉 내 목표 도달 {hit.mean()*100:.1f}% ({hit.sum()}건) — 2단이 카드와 달라지는 유일한 경우")
print("  P0 청산유형 분포:", dict(C["P0_how"].value_counts()))


def stat(s):
    s = s.dropna()
    return dict(n=len(s), mean=s.mean() * 100, med=s.median() * 100,
                win=(s > 0).mean() * 100, p25=s.quantile(.25) * 100, p75=s.quantile(.75) * 100)


def block_boot(a, b, years, n=2000, seed=7):
    """연도 블록 부트스트랩 — 이벤트가 위기해에 몰려 독립표본이 아니므로."""
    rng = np.random.default_rng(seed)
    ys = np.array(sorted(set(years)))
    idx = {y: np.where(years == y)[0] for y in ys}
    out = np.empty(n)
    for i in range(n):
        pick = rng.choice(ys, size=len(ys), replace=True)
        sel = np.concatenate([idx[y] for y in pick])
        out[i] = np.nanmean(a[sel]) - np.nanmean(b[sel])
    return np.percentile(out, [2.5, 50, 97.5]) * 100


print("\n" + "=" * 72)
print("[정책 그리드] 126봉 창완결 표본 기준 — 평균/중앙/승률 (%)")
print(f"{'정책':<22}{'n':>6}{'평균':>9}{'중앙':>9}{'승률':>8}{'p25':>9}{'p75':>9}")
base = C["P0_카드"].values
yrs = C["연"].values
rowsum = []
cands = ["P0_카드"] + [c for c in C.columns if c.startswith(("P0_H", "P1_", "P2_"))]
for col in cands:
    s = stat(C[col])
    print(f"{col:<22}{s['n']:>6}{s['mean']:>+9.2f}{s['med']:>+9.2f}{s['win']:>7.1f}%{s['p25']:>+9.2f}{s['p75']:>+9.2f}")
    rowsum.append(dict(정책=col, **s))
S = pd.DataFrame(rowsum).sort_values("mean", ascending=False)
S.to_csv(os.path.join(HERE, "휩쏘_2단청산_요약.csv"), index=False, encoding="utf-8-sig")

print("\n[상위 8 정책 · 카드 대비 Δ평균 + 연도블록 부트스트랩 95% CI]")
print(f"{'정책':<22}{'Δ평균':>9}{'   95% CI':>22}{'  중앙Δ':>9}{'승률Δ':>8}")
b0 = stat(C['P0_카드'])
for _, r in S.head(9).iterrows():
    col = r["정책"]
    if col == "P0_카드": continue
    lo, md, hi = block_boot(C[col].values, base, yrs)
    print(f"{col:<22}{r['mean']-b0['mean']:>+9.2f}   [{lo:+6.2f}, {hi:+6.2f}]{'':>4}{r['med']-b0['med']:>+9.2f}{r['win']-b0['win']:>+7.1f}p")

# ── 국면 × 유형 분해 (대표 정책) ────────────────────────────────────
REP = ["P0_카드", "P1_T20_H126_tr", "P1_T20_H126_be", "P1_T15_H126_tr", "P2_T20_H126"]
REP = [c for c in REP if c in C.columns]
print("\n" + "=" * 72)
print("[국면별] 평균 % (괄호=승률)")
hdr = f"{'국면':<8}{'n':>6}" + "".join(f"{c:>20}" for c in REP)
print(hdr)
for g, sub in C.groupby("국면"):
    line = f"{g:<8}{len(sub):>6}"
    for c in REP:
        s = stat(sub[c]); line += f"{s['mean']:>+13.2f} ({s['win']:.0f}%)"
    print(line)
print("\n[유형별]")
print(f"{'유형':<8}{'n':>6}" + "".join(f"{c:>20}" for c in REP))
for g, sub in C.groupby("유형"):
    line = f"{g:<8}{len(sub):>6}"
    for c in REP:
        s = stat(sub[c]); line += f"{s['mean']:>+13.2f} ({s['win']:.0f}%)"
    print(line)

# ── 목표도달 부분집합만 (정책이 실제로 갈리는 자리) ──────────────────
H = C[C["P0_how"] == "목표"]
print("\n" + "=" * 72)
print(f"[목표도달 부분집합 n={len(H)}] — 여기서만 2단이 카드와 다르다")
print(f"{'정책':<22}{'평균':>9}{'중앙':>9}{'승률':>8}{'Δ평균':>9}")
b = stat(H["P0_카드"])
for c in REP:
    s = stat(H[c])
    print(f"{c:<22}{s['mean']:>+9.2f}{s['med']:>+9.2f}{s['win']:>7.1f}%{s['mean']-b['mean']:>+9.2f}")
if "P1대표_잔여수익" in H.columns:
    rr = H["P1대표_잔여수익"].dropna()
    print(f"\n  잔여 50%(T20/H126/tr)의 단독 성과: 평균 {rr.mean()*100:+.2f}% · 중앙 {rr.median()*100:+.2f}% · 승률 {(rr>0).mean()*100:.0f}%")
    print(f"  잔여 보유 추가봉 중앙 {H['P1대표_잔여봉'].median():.0f}봉 · 종료유형 {dict(H['P1대표_how'].value_counts())}")

# ── 거래비용 민감도 ────────────────────────────────────────────────
print("\n[비용 민감도] 2단은 매도가 1회 늘어난다(잔여 50%에 1회분 추가)")
for cost in (0.15, 0.30, 0.50):
    add = cost * 0.5
    best = S.iloc[0]
    print(f"  편도 {cost:.2f}% 가정 → 2단 추가비용 {add:.3f}%p · {best['정책']} Δ평균 {best['mean']-b0['mean']:+.2f} → {best['mean']-b0['mean']-add:+.2f}%p")
