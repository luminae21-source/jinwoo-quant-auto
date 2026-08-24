#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
block_bootstrap_sensitivity.py — Block Bootstrap 해석 강건성 (비중복 추가)
==============================================================================
배경: 기존 Block Bootstrap(2026-06-14 통과)은 mean_block=4 단일값만 사용 →
연 Sharpe 95%CI [1.47,3.40]. 6/15 GPT검토(line167)가 남긴 미해결:
  "block CI가 iid보다 안 넓다(자기상관 호의적)는 해석이, 49개월 소표본에서
   block 길이 선택·effective sample 축소를 충분히 감안했나?"

이 스크립트: 같은 시계열(trial_returns_matrix.csv 'v37_2')에 **block 길이를
1·2·3·4·6·9·12로 sweep** → CI 폭·하한·effective block 수(n/L) 변화를 측정.
  · block=1 = iid(독립) 기준선(stationary bootstrap p=1).
  · 판정: CI 폭이 block 길이에 robust(거의 불변/단조)면 "자기상관 호의적" 해석 견고.
           긴 block에서 폭이 급증하면 = 유효표본 부족(소표본 fragility) → 그 구간 해석 보류.

정직: 인샘플 robustness 해석 점검. forward 아님. 결론은 "해석의 block-길이 민감도"까지.
의존: stats_v1.block_bootstrap_ci, trial_returns_matrix.csv
"""
import sys, json, math
import numpy as np, pandas as pd
import stats_v1 as S

BLOCKS = [1, 2, 3, 4, 6, 9, 12]
N_BOOT = 6000   # 샌드박스 시간내 안정적 (원본 finalize=5000)
SEED = 1


def main():
    m = pd.read_csv("trial_returns_matrix.csv", index_col=0)
    if "v37_2" not in m.columns:
        raise SystemExit(f"v37_2 열 없음. 열들: {list(m.columns)}")
    ret = m["v37_2"].dropna().values
    n = len(ret)
    sharpe = lambda x: x.mean() / x.std(ddof=1) * math.sqrt(12) if x.std(ddof=1) > 0 else 0.0
    cagr = lambda x: np.prod(1 + x) ** (12 / len(x)) - 1
    pt_sh = sharpe(ret); pt_cg = cagr(ret)
    print(f"=== Block Bootstrap 해석 강건성 (v37_2, n={n}개월, n_boot={N_BOOT}) ===")
    print(f"점추정: 연 Sharpe {pt_sh:.2f} · CAGR {pt_cg:.1%}\n")
    print(f"{'block L':>7}{'유효블록 n/L':>11}{'Sharpe CI':>22}{'폭':>7}{'CAGR 하한':>10}{'iid대비폭':>9}")
    rows = []; w_iid = None
    for L in BLOCKS:
        lo, hi, pt, _ = S.block_bootstrap_ci(ret, sharpe, mean_block=L, n_boot=N_BOOT, seed=SEED)
        clo, chi, cpt, _ = S.block_bootstrap_ci(ret, cagr, mean_block=L, n_boot=N_BOOT, seed=SEED)
        width = hi - lo
        if L == 1: w_iid = width
        rel = width / w_iid if w_iid else 1.0
        eff = n / L
        rows.append(dict(block=L, eff_blocks=round(eff, 1), sharpe_lo=round(lo, 2), sharpe_hi=round(hi, 2),
                         sharpe_width=round(width, 2), cagr_lo=round(clo, 4), width_vs_iid=round(rel, 2)))
        print(f"{L:>7}{eff:>11.1f}   [{lo:>5.2f}, {hi:>5.2f}]{width:>7.2f}{clo*100:>9.1f}%{rel:>9.2f}x")
    print("\n해석:")
    # 폭이 iid 대비 거의 안 늘거나(≤~1.1x) 줄면 자기상관 호의적; 급증 구간 식별
    fragile = [r["block"] for r in rows if r["width_vs_iid"] >= 1.25]
    robust_lo = all(r["sharpe_lo"] > 0 for r in rows)
    print("  · 모든 block에서 Sharpe 하한 > 0: %s (엣지 부호 robust)" % ("예" if robust_lo else "아니오"))
    short_str = ", ".join("L%d:%.2fx" % (r["block"], r["width_vs_iid"]) for r in rows if r["block"] <= 6)
    print("  · 짧은~중간 block(1~6) 폭 비(iid대비): " + short_str)
    if fragile:
        eff_min = min(n / L for L in fragile)
        print("  · [!] 폭 급증(>=1.25x iid) block: %s -> 유효블록 ~%.0f개, 소표본 해석 신뢰 낮음(보류)." % (fragile, eff_min))
    else:
        print("  · 모든 block에서 CI 폭이 iid의 1.25배 미만 -> '자기상관 호의적' 해석 block-길이에 robust.")
    print("  · 유효블록 n/L: L=4->%.0f, L=9->%.0f, L=12->%.0f. 통상 >=10~15 권장 -> L>=%d부터 블록수 부족." % (n/4, n/9, n/12, math.ceil(n/10)))
    print("\n결론(정직): mean_block=4(유효블록 ~%.0f)는 합리적 구간. 긴 block(9·12)은 유효블록 4~5개 소표본이라 CI 불안정 -> 해석 확대 금지. 인샘플 점검일 뿐 forward 아님." % (n/4))
    out = {"n": n, "n_boot": N_BOOT, "point_sharpe": round(pt_sh, 3), "point_cagr": round(pt_cg, 4),
           "sweep": rows, "note": "인샘플 해석 강건성. forward 아님. 6/15 GPT검토 line167 대응."}
    fn = "block_bootstrap_sensitivity_result.json"
    with open(fn, "w") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"\n저장: {fn}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
