# -*- coding: utf-8 -*-
"""2단 청산 — 동일지평 공정비교 + 부트스트랩(be모드 중심) + 국면 게이트 적용시."""
import os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

HERE = "/home/claude/jq"
M = pd.read_csv(os.path.join(HERE, "휩쏘_2단청산_이벤트.csv"), dtype={"code": str})
M["연"] = M["출발일"].str[:4].astype(int)
C = M[M["창완결_126"] == True].copy()


def block_boot(a, b, years, n=4000, seed=7):
    rng = np.random.default_rng(seed)
    ys = np.array(sorted(set(years)))
    idx = {y: np.where(years == y)[0] for y in ys}
    out = np.empty(n)
    for i in range(n):
        pick = rng.choice(ys, size=len(ys), replace=True)
        sel = np.concatenate([idx[y] for y in pick])
        out[i] = np.nanmean(a[sel]) - np.nanmean(b[sel])
    lo, hi = np.percentile(out, [2.5, 97.5]) * 100
    return lo, hi, (out > 0).mean()


def report(sub, title):
    print("\n" + "=" * 74)
    print(f"[{title}] n={len(sub)}")
    yrs = sub["연"].values
    print(f"{'정책':<20}{'평균':>8}{'중앙':>8}{'승률':>8}{'Δ평균':>8}{'   부트95%CI':>20}{'P(Δ>0)':>9}")
    for H in (40, 63, 126):
        base_col = "P0_카드" if H == 40 else f"P0_H{H}"
        b = sub[base_col].dropna()
        print(f"  ── 지평 {H}봉 · 기준 {base_col}: 평균 {b.mean()*100:+.2f} 중앙 {b.median()*100:+.2f} 승률 {(b>0).mean()*100:.1f}%")
        base = sub[base_col].values
        for tr in (10, 12, 15, 20, 25):
            for sm in ("be", "tr"):
                col = f"P1_T{tr}_H{H}_{sm}"
                if col not in sub.columns: continue
                s = sub[col].dropna()
                lo, hi, pg = block_boot(sub[col].values, base, yrs)
                d = s.mean() * 100 - base.mean() * 100
                mark = " ★" if lo > 0 else ""
                print(f"{col:<20}{s.mean()*100:>+8.2f}{s.median()*100:>+8.2f}{(s>0).mean()*100:>7.1f}%"
                      f"{d:>+8.2f}   [{lo:+6.2f},{hi:+6.2f}]{pg:>9.1%}{mark}")


report(C, "126봉 창완결 전체")
report(C[C["국면"] == "실행"], "🟢실행 국면만 (게이트 적용 — 실전 조건)")

# 유형 A · 실행만
sub = C[(C["국면"] == "실행") & (C["유형"] == "A")]
report(sub, "🟢실행 × A형 (본체)")

# 목표도달분에서의 잔여 분포 — 꼬리 확인
H = C[(C["국면"] == "실행") & (C["P0_how"] == "목표")]
rr = H["P1대표_잔여수익"].dropna() * 100
print("\n" + "=" * 74)
print(f"[실행국면 목표도달 {len(H)}건] 잔여 50%(T20/H126/tr) 단독 분포")
for q in (5, 25, 50, 75, 90, 95, 99):
    print(f"   p{q:<3} {np.percentile(rr, q):+8.2f}%", end="")
    if q in (50, 95, 99): print()
print(f"\n   평균 {rr.mean():+.2f}% · 승률 {(rr>0).mean()*100:.0f}% · 최대 {rr.max():+.1f}%")
print(f"   상위 5%가 평균에 기여: {rr.nlargest(max(1,int(len(rr)*.05))).sum()/len(rr):+.2f}%p / {rr.mean():+.2f}%p")
