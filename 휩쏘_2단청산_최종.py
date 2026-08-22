# -*- coding: utf-8 -*-
"""최종 권고안 수치 확정 + JSON 출력(리포트 빌더용)."""
import os, sys, json, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
HERE = "/home/claude/jq"

A = pd.read_csv(f"{HERE}/휩쏘_2단청산_이벤트.csv", dtype={"code": str})
B = pd.read_csv(f"{HERE}/휩쏘_2단청산_보강.csv", dtype={"code": str})
M = A.merge(B[["출발일", "code"] + [c for c in B.columns if c.startswith("S")]],
            on=["출발일", "code"], how="left")
M["연"] = M["출발일"].str[:4].astype(int)
C = M[M["창완결_126"] == True].copy()
G = C[C["국면"] == "실행"].copy()


def boot(a, b, yrs, n=6000, seed=17):
    rng = np.random.default_rng(seed); ys = np.array(sorted(set(yrs)))
    idx = {y: np.where(yrs == y)[0] for y in ys}; out = np.empty(n)
    for i in range(n):
        p = rng.choice(ys, size=len(ys), replace=True)
        s = np.concatenate([idx[y] for y in p])
        out[i] = np.nanmean(a[s]) - np.nanmean(b[s])
    return (*np.percentile(out, [2.5, 97.5]) * 100, float((out > 0).mean()))


def line(s):
    s = pd.Series(s).dropna()
    return dict(n=int(len(s)), mean=float(s.mean() * 100), med=float(s.median() * 100),
                win=float((s > 0).mean() * 100), std=float(s.std() * 100),
                p95=float(s.quantile(.95) * 100), p05=float(s.quantile(.05) * 100))


res = {}
for nm, sub in (("전체", C), ("실행", G)):
    d = {}
    base = sub["P0_H126"].values
    d["카드_H40"] = line(sub["P0_카드"])
    d["카드_H126"] = line(sub["P0_H126"])
    for key, col in (("권고_S50T12", "S50_T12_be"), ("공격_S25T12", "S25_T12_be"),
                     ("보수_S75T12", "S75_T12_be"), ("트레일만_T12", "P2_T12_H126"),
                     ("구조청산_S50", "S50_구조")):
        st = line(sub[col]); lo, hi, pg = boot(sub[col].values, base, sub["연"].values)
        st.update(delta=st["mean"] - d["카드_H126"]["mean"], lo=lo, hi=hi, pg=pg)
        d[key] = st
    d["고점6M"] = line(sub["고점6M"])
    d["목표도달율"] = float((sub["P0_how"] == "목표").mean() * 100)
    res[nm] = d

# 회수율
for nm in ("전체", "실행"):
    d = res[nm]
    gap = d["고점6M"]["mean"] - d["카드_H126"]["mean"]
    d["간극"] = gap
    d["회수율_권고"] = d["권고_S50T12"]["delta"] / gap * 100
    d["회수율_공격"] = d["공격_S25T12"]["delta"] / gap * 100

# 연도별 안정성 (권고안)
G2 = G.dropna(subset=["S50_T12_be", "P0_H126"])
yr = G2.groupby(G2["연"] // 5 * 5).apply(
    lambda x: pd.Series({"n": len(x),
                         "카드": x["P0_H126"].mean() * 100,
                         "권고": x["S50_T12_be"].mean() * 100}))
yr["Δ"] = yr["권고"] - yr["카드"]
res["연대별"] = yr.reset_index().rename(columns={"연": "시작연"}).to_dict("records")
res["연대별_승리구간"] = int((yr["Δ"] > 0).sum()); res["연대별_전체"] = int(len(yr))

json.dump(res, open(f"{HERE}/휩쏘_2단청산_결과.json", "w"), ensure_ascii=False, indent=1)

print("=" * 74)
for nm in ("전체", "실행"):
    d = res[nm]
    print(f"\n■ {nm} (n={d['카드_H126']['n']}) · 목표도달 {d['목표도달율']:.1f}% · 6M고점 평균 {d['고점6M']['mean']:+.1f}%")
    print(f"{'':<14}{'평균':>8}{'중앙':>8}{'승률':>8}{'표준편차':>9}{'Δ평균':>8}{'   부트95%CI':>19}{'P(Δ>0)':>8}")
    for k in ("카드_H40", "카드_H126", "권고_S50T12", "공격_S25T12", "보수_S75T12", "트레일만_T12", "구조청산_S50"):
        s = d[k]
        ex = f"{s['delta']:>+8.2f}   [{s['lo']:+6.2f},{s['hi']:+6.2f}]{s['pg']:>8.1%}" if "delta" in s else ""
        print(f"{k:<14}{s['mean']:>+8.2f}{s['med']:>+8.2f}{s['win']:>7.1f}%{s['std']:>9.1f}{ex}")
    print(f"  간극(6M고점−카드) {d['간극']:+.1f}%p → 권고안 회수 {d['회수율_권고']:.1f}% / 공격안 {d['회수율_공격']:.1f}%")

print("\n[5년대별 안정성 · 🟢실행 · 권고안 vs 카드]")
print(yr.round(2).to_string())
print(f"→ {res['연대별_승리구간']}/{res['연대별_전체']} 구간에서 개선")
