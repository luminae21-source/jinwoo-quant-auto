# -*- coding: utf-8 -*-
"""휩쏘 · §10-B 규칙 분리 — 2단계 판정 (사전등록 v1.1 그대로)
  훈련 = 짝수년 / 검증 = 홀수년 (강건성: 방향 교체 · 시간순 ~2011/2012~)
  훈련 선택지표 = 연도가중 상한(10%) 평균 · 검증 판정 = 풀드 평균 + 연도블록 부트 95% CI
  비교 = 축당 1회 (S_k* vs U*) → Bonferroni α=0.05/3
"""
import os, sys, json, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
HERE = os.path.dirname(os.path.abspath(__file__))
NB = 4000; SEED = 11; COSTS = [0.0, 0.003, 0.005]
Z1_THR = 0.0864   # 사전등록 v1.1 고정값

R = pd.read_csv(os.path.join(HERE, "휩쏘_규칙분리_이벤트.csv"), dtype={"code": str})
RULES = [c for c in R.columns if c.startswith("R_") and not c.endswith("_봉")]
QS = [c for c in R.columns if c.startswith("Q_")]
P = R[(R["유형"] != "B") & R["창완결_40"]].copy()
P["훈련"] = P["연"] % 2 == 0
print(f"PRIMARY 창완결 {len(P)} · 훈련 {P['훈련'].sum()} · 검증 {(~P['훈련']).sum()}")

# ── 분류축 경계 (Z2는 여기서 1회 산출·기록) ─────────────────────────
Z2_THR = float(P.loc[P["훈련"], "atr_pct"].median())
print(f"[경계 고정] Z1 목표거리 {Z1_THR:.4f} · Z2 ATR% {Z2_THR:.4f} (훈련 중앙값) · Z3 gap240 0")
AXES = {
    "Z1_목표거리": (P["목표거리"] > Z1_THR).map({False: "얕음(짧게)", True: "깊음(길게)"}),
    "Z2_변동성":   (P["atr_pct"] > Z2_THR).map({False: "저변동", True: "고변동"}),
    "Z3_구조위치": (P["gap240"] > 0).map({False: "선아래", True: "선위"}),
}
for k, v in AXES.items(): P[k] = v


def wmean_capped(df, col, cap=0.10):
    """연도 총가중 ≤ cap 인 가중평균."""
    n = len(df); w = np.ones(n)
    for y, idx in df.groupby("연").indices.items():
        if len(idx) / n > cap: w[idx] = cap * n / len(idx)
    return float(np.average(df[col].values, weights=w))


def boot_ci(df, col, nb=NB, seed=SEED):
    """연도블록 부트스트랩 — 평균의 95% CI."""
    rng = np.random.default_rng(seed)
    yrs = df["연"].unique(); groups = {y: df.loc[df["연"] == y, col].values for y in yrs}
    out = np.empty(nb)
    for i in range(nb):
        pick = rng.choice(yrs, len(yrs), replace=True)
        v = np.concatenate([groups[y] for y in pick]); out[i] = v.mean()
    return float(np.percentile(out, 2.5)), float(np.percentile(out, 97.5))


def stats(x):
    x = np.asarray(x)
    return dict(n=int(len(x)), 평균=float(x.mean() * 100), 중앙=float(np.median(x) * 100),
                승률=float((x > 0).mean() * 100), 최대손실=float(x.min() * 100),
                m20=float((x <= -0.20).mean() * 100), 표준편차=float(x.std() * 100))


def select(df, rules):
    sc = {r: wmean_capped(df, r) for r in rules}
    return max(sc, key=sc.get), sc


def composite(df, axis, pair):
    """그룹별 규칙을 적용한 합성 수익 열."""
    out = np.empty(len(df))
    for g, rule in pair.items():
        m = (df[axis] == g).values; out[m] = df.loc[m, rule].values
    return out


def run(train, valid, rules, label, tag):
    res = {"표본": dict(훈련=len(train), 검증=len(valid))}
    U, _ = select(train, rules)
    res["U*"] = U
    vU = valid[U].values
    res["검증_U*"] = stats(vU)
    res["검증_P0"] = stats(valid["P0"].values); res["검증_P1"] = stats(valid["P1"].values)
    alpha = 0.05 / 3
    for ax in AXES:
        pair = {}
        for g in train[ax].dropna().unique():
            pair[g], _ = select(train[train[ax] == g], rules)
        vS = composite(valid, ax, pair)
        d = vS - vU
        tmp = valid[["연"]].copy(); tmp["d"] = d
        lo, hi = boot_ci(tmp, "d")
        # Bonferroni: 1-α/3 양측 CI
        rng = np.random.default_rng(SEED); yrs = tmp["연"].unique()
        groups = {y: tmp.loc[tmp["연"] == y, "d"].values for y in yrs}
        bs = np.array([np.concatenate([groups[y] for y in rng.choice(yrs, len(yrs), True)]).mean() for _ in range(NB)])
        lo_b = float(np.percentile(bs, 100 * alpha / 2)); hi_b = float(np.percentile(bs, 100 * (1 - alpha / 2)))
        sS, sU = stats(vS), stats(vU)
        # 비용: 규칙별 왕복 1회 — 2단은 2회 청산이지만 1차 규칙만 비교하므로 동일 횟수 → Δ에 비용 영향 없음.
        # 단 '목표 없음' 규칙은 청산 횟수 동일(1회). 비용 Δ = 0. 절대수준만 차감 보고.
        crit = dict(
            c1_CI하한_보정후=lo_b > 0, c2_중앙=(sS["중앙"] - sU["중앙"]) >= -1.0,
            c3_승률=(sS["승률"] - sU["승률"]) >= -2.0,
            c4_하방=(sS["최대손실"] >= sU["최대손실"] - 3.0) and (sS["m20"] <= sU["m20"]),
            c5_비용후부호=(d.mean() > 0), c6_규칙상이=len(set(pair.values())) > 1)
        res[ax] = dict(경계=dict(Z1=Z1_THR, Z2=Z2_THR, Z3=0.0)[ax[:2]], 그룹규칙=pair,
                       그룹n=valid[ax].value_counts().to_dict(),
                       검증_S=sS, Δ평균=float(d.mean() * 100), Δ중앙=sS["중앙"] - sU["중앙"], Δ승률=sS["승률"] - sU["승률"],
                       CI95=[lo * 100, hi * 100], CI_Bonf=[lo_b * 100, hi_b * 100],
                       판정=crit, 채택=all(crit.values()))
        # 훈련 내 그룹별 수익(참고 · 사후)
        res[ax]["훈련_그룹별_U*평균"] = {g: float(train.loc[train[ax] == g, U].mean() * 100) for g in pair}
        res[ax]["훈련_그룹별_S평균"] = {g: float(train.loc[train[ax] == g, pair[g]].mean() * 100) for g in pair}
    return res


def main():
    out = {}
    tr, va = P[P["훈련"]], P[~P["훈련"]]
    out["주검정_짝훈련_홀검증"] = run(tr, va, RULES, "1차", "main")
    out["강건성_홀훈련_짝검증"] = run(va, tr, RULES, "1차", "swap")
    tr2, va2 = P[P["연"] <= 2011], P[P["연"] >= 2012]
    out["강건성_시간순"] = run(tr2, va2, RULES, "1차", "time")
    # 2차: 잔여 규칙 (126봉 창완결)
    P2 = P[P["창완결_126"]]
    out["2차_잔여규칙_짝훈련_홀검증"] = run(P2[P2["훈련"]], P2[~P2["훈련"]], QS, "2차", "runner")
    # 참고: 현행 카드의 축별 성과 (기술통계)
    out["참고_현행P0_축별"] = {ax: {g: stats(P.loc[P[ax] == g, "P0"].values) for g in P[ax].dropna().unique()} for ax in AXES}
    # 참고: 36 규칙 전체 검증 평균 (탐색 · 채택 불가)
    out["참고_전규칙_검증평균"] = {r: float(va[r].mean() * 100) for r in RULES}
    out["참고_전규칙_훈련평균"] = {r: float(tr[r].mean() * 100) for r in RULES}
    # 비용 민감도 (절대수준)
    out["비용_절대수준_검증"] = {f"편도{c*100:.1f}%": dict(P0=float((va['P0'] - 2 * c).mean() * 100),
                                                   U=float((va[out['주검정_짝훈련_홀검증']['U*']] - 2 * c).mean() * 100)) for c in COSTS}
    # B형 보조
    B = R[(R["유형"] == "B") & R["창완결_40"]].copy()
    out["B형_보조"] = dict(n=len(B), P0=stats(B["P0"].values), 전규칙평균={r: float(B[r].mean() * 100) for r in RULES})
    out["경계"] = dict(Z1=Z1_THR, Z2=Z2_THR, Z3=0.0)
    with open(os.path.join(HERE, "휩쏘_규칙분리_결과.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1, default=float)
    # 콘솔 요약
    for key in ["주검정_짝훈련_홀검증", "강건성_홀훈련_짝검증", "강건성_시간순", "2차_잔여규칙_짝훈련_홀검증"]:
        r = out[key]; print(f"\n=== {key} === 훈련 {r['표본']['훈련']} 검증 {r['표본']['검증']} · U* = {r['U*']}")
        print(f"  검증 U* {r['검증_U*']['평균']:+.2f}% 중앙 {r['검증_U*']['중앙']:+.2f} 승률 {r['검증_U*']['승률']:.1f} | P0 {r['검증_P0']['평균']:+.2f}% | P1 {r['검증_P1']['평균']:+.2f}%")
        for ax in AXES:
            a = r[ax]
            print(f"  {ax}: {a['그룹규칙']} Δ{a['Δ평균']:+.2f}%p CI95[{a['CI95'][0]:+.2f},{a['CI95'][1]:+.2f}] Bonf[{a['CI_Bonf'][0]:+.2f},{a['CI_Bonf'][1]:+.2f}] Δ중앙{a['Δ중앙']:+.2f} Δ승률{a['Δ승률']:+.1f} → {'채택' if a['채택'] else '기각'} {[k for k,v in a['판정'].items() if not v]}")

if __name__ == "__main__":
    main()
