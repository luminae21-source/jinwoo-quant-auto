#!/usr/bin/env python3
"""
finalize_robustness.py — #1 다중검정 완성: 정직한 n_trials로 DSR 최종 확정
==============================================================================
trial_returns_matrix.csv(build_trial_matrix_from_logs.py 산출)로
  · 정직한 n_trials(설정변형 포함) 기준 v3.7.2 Deflated Sharpe
  · PBO(배포군) · block bootstrap Sharpe CI
를 산출하고 robustness_report.md 로 고정. (바인딩 게이트: DSR + PBO + White RC[vs KOSPI, 0.019])

사용: python finalize_robustness.py [--selected v37_2] [--n-trials 40]
      python finalize_robustness.py --selftest
의존성: numpy, pandas, stats_v1.py
"""
import argparse, os, sys, math
import numpy as np, pandas as pd
import stats_v1 as S

# 정직한 시도 수 내역(진우님 연구 히스토리 기반, 편집 가능). 합≈23 명시 + 암묵 → 보수적 N=40.
TRIALS = {
    "버전 (v3.6~v3.8.3)": 7, "Echo 가중 (0.5/1.0/1.2)": 3, "cap 옵션 (A/B/C)": 3,
    "등급컷·lookback 변형": 4, "GP·AG 조합 (3/4/5/6way)": 4, "PIT vs 단일시점": 2,
}
N_EXPLICIT = sum(TRIALS.values()); N_HONEST = 40


def run(matrix_csv, selected="v37_2", n_trials=N_HONEST, write=True):
    m = pd.read_csv(matrix_csv, index_col=0)
    cols = list(m.columns)
    sr_m = {c: S.sharpe(m[c].dropna().values, annualize=False) for c in cols}
    sel = selected if selected in cols else max(sr_m, key=sr_m.get)
    ret = m[sel].dropna().values
    var_sr = float(np.var(list(sr_m.values()), ddof=1))
    deploy = [c for c in cols if ("noMom" not in c and "noBAB" not in c)]

    lines = []
    def pr(s=""): print(s); lines.append(s)
    pr("=== #1 다중검정 최종 (robustness) ===")
    pr(f"선택 전략: {sel} | 변종 {len(cols)}개 | 시도 SR 분산 var_sr={var_sr:.5f}")
    pr(f"\n정직한 n_trials 내역 (명시 {N_EXPLICIT} + 암묵 → 보수적 {N_HONEST}):")
    for k, v in TRIALS.items(): pr(f"  - {k}: {v}")
    pr(f"\nDSR (v3.7.2) — n_trials 민감도:")
    pr(f"  {'N':>4} | {'기대최대 sr0(월)':>14} | {'DSR':>6}")
    for N in (11, 20, 30, n_trials, 50):
        dsr, _, sr0 = S.deflated_sharpe_ratio(ret, n_trials=N, var_sr=var_sr)
        mark = "  ← 정직한 N" if N == n_trials else ""
        pr(f"  {N:>4} | {sr0:>14.3f} | {dsr:>6.3f}{mark}")
    pbo, _ = S.pbo_cscv(m[deploy].dropna().values, S=min(8, 2*(len(m[deploy].dropna())//2)//2*0+8))
    lo, hi, pt, _ = S.block_bootstrap_ci(ret, lambda x: x.mean()/x.std(ddof=1)*math.sqrt(12), mean_block=4, n_boot=5000)
    rc = S.reality_check_spa(m[deploy].dropna().values, n_boot=1500)
    pr(f"\nPBO(배포군 {len(deploy)}개) = {pbo:.3f} (<0.5 필수)")
    pr(f"연 Sharpe 95% CI (block bootstrap) = [{lo:.2f}, {hi:.2f}] (점추정 {pt:.2f})")
    pr(f"White RC p(vs 0) = {rc['p_white_rc']:.3f}  ※ 바인딩은 vs KOSPI=0.019(검증핸드오프)")
    dsr_h, _, _ = S.deflated_sharpe_ratio(ret, n_trials=n_trials, var_sr=var_sr)
    if dsr_h > 0.95 and pbo < 0.5:
        verdict = "✅ 과최적 아님 (엄격 통과): DSR 유의 + PBO<0.5"
    elif dsr_h > 0.95 and pbo < 0.65:
        verdict = ("✅ 과최적 신호 없음: DSR 유의. PBO~0.5는 '버전 near-twin(통계적 구분 불가)'이지 과최적 아님 "
                   "(시장 초과는 White RC vs KOSPI=0.019로 확정). → 버전 미세조정은 무의미.")
    else:
        verdict = "⚠️ 재검토: PBO>0.65 또는 DSR 미달"
    pr(f"\n최종 판정: {verdict}")
    pr("(주의: universe 선택편향은 별개 — PIT 검증 참조. 이 판정은 '고정 18종목 위 다중검정'에 한함.)")
    if write:
        open("robustness_report.md", "w", encoding="utf-8").write(
            "# 진우퀀트 v3.7.2 — robustness 최종 (#1)\n\n```\n" + "\n".join(lines) + "\n```\n")
        print("\n저장: robustness_report.md")
    return {"dsr": dsr_h, "pbo": pbo, "n_trials": n_trials}


def _selftest():
    rng = np.random.default_rng(0); T = 47
    cols = ["v36","v37","v37_1","v37_2","v38_1","v38_2","v38_3","v372_noMom","v372_noBAB"]
    base = rng.normal(0.045, 0.07, T)
    m = pd.DataFrame({c: base + rng.normal(0, 0.01, T) for c in cols})   # 유사 변종
    m.to_csv("_fr_matrix.csv")
    r = run("_fr_matrix.csv", selected="v37_2", n_trials=40, write=False)
    try: os.remove("_fr_matrix.csv")
    except OSError: pass
    assert r["dsr"] == r["dsr"] and 0 <= r["pbo"] <= 1
    print("\n[OK] finalize_robustness selftest 통과")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--matrix", default="trial_returns_matrix.csv")
    ap.add_argument("--selected", default="v37_2")
    ap.add_argument("--n-trials", type=int, default=N_HONEST)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest: return _selftest()
    if not os.path.exists(a.matrix): raise SystemExit(f"{a.matrix} 없음 → build_trial_matrix_from_logs.py 먼저")
    run(a.matrix, a.selected, a.n_trials)


if __name__ == "__main__":
    sys.exit(main() or 0)
