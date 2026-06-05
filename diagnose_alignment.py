#!/usr/bin/env python3
"""
diagnose_alignment.py — attribution 날짜 정렬 진단
==================================================
전략 월수익을 lag −1/0/+1 이동하며 한국 팩터에 회귀, MKT 베타가 정상(~0.8~1.1)으로
나오는 정렬을 찾는다. long-only 주식은 MKT 베타가 0일 수 없으므로, MKT t가 가장 큰
정렬이 올바른 것이고 그 행의 alpha가 '진짜' alpha다.
사용: python diagnose_alignment.py   /   python diagnose_alignment.py --selftest
"""
import argparse, glob, json, sys, os
import numpy as np, pandas as pd


def _pm(x):
    return pd.PeriodIndex(pd.to_datetime(x), freq="M")


def load_strat(bj, variant="r_v37_2_%"):
    h = pd.DataFrame(json.load(open(bj, encoding="utf-8"))["history"])
    s = pd.Series([(v or 0) / 100.0 for v in h[variant]], index=_pm(h["date"]))
    return s[~s.index.duplicated(keep="last")].sort_index()


def run(bj, factors_csv, variant="r_v37_2_%"):
    import regime_overlay as R
    strat = load_strat(bj, variant)
    f = pd.read_csv(factors_csv, index_col=0); f.index = _pm(f.index)
    cols = [c for c in ["MKT", "SMB", "HML", "WML"] if c in f.columns and f[c].notna().mean() >= 0.5]
    rf = f["RF"] if "RF" in f.columns else pd.Series(0.0, index=f.index)
    rows = []
    for L in (-1, 0, 1):
        s = pd.Series(strat.values, index=strat.index + L)
        common = s.index.intersection(f.index)
        ex = (s.reindex(common) - rf.reindex(common)).dropna()
        if len(ex) < 12:
            rows.append((L, np.nan, np.nan, np.nan, np.nan, len(ex))); continue
        res = R.ols_attribution(ex, f.loc[ex.index, cols])
        rows.append((L, res.loc["MKT", "coef"], res.loc["MKT", "t_stat"],
                     res.loc["alpha", "coef"], res.loc["alpha", "t_stat"], len(ex)))
    print("lag |  MKT 베타 (t)   |  alpha 월%(t)   |  n")
    print("----+----------------+-----------------+----")
    for L, mc, mt, ac, at, n in rows:
        if np.isnan(mc): print(f" {L:+d} |   (데이터 부족)  |                 | {n}"); continue
        print(f" {L:+d} | {mc:6.2f} ({mt:5.1f}) | {ac*100:6.2f}% ({at:4.1f}) | {n}")
    valid = [r for r in rows if not np.isnan(r[1])]
    if not valid:
        print("진단 불가(데이터 부족)"); return None
    best = max(valid, key=lambda r: abs(r[2]))   # MKT t 절대값 최대 = 시장과 가장 잘 정렬
    print(f"\n→ 올바른 정렬: lag={best[0]:+d}  (MKT 베타 {best[1]:.2f}, t {best[2]:.1f})")
    print(f"   진짜 alpha: 월 {best[3]*100:+.2f}%  (연 {((1+best[3])**12-1)*100:+.1f}%),  t={best[4]:.1f}")
    if abs(best[2]) < 2:
        print("   ⚠️ 최선 정렬에서도 MKT t<2 → 추가 데이터 점검 필요")
    elif best[4] >= 2:
        print("   ✅ MKT 베타 정상 + alpha 유의 = 4팩터로 설명 안 되는 진짜 엣지(보정된 값)")
    else:
        print("   → MKT 정상화 후 alpha 유의성 약화 = 수익 상당부분이 시장/팩터로 설명됨")
    return best


def _selftest():
    rng = np.random.default_rng(0)
    months = pd.period_range("2022-01", periods=48, freq="M")
    f = pd.DataFrame({"MKT": rng.normal(0.01, 0.05, 48), "SMB": rng.normal(0, 0.03, 48),
                      "HML": rng.normal(0, 0.03, 48), "WML": rng.normal(0, 0.04, 48),
                      "RF": 0.0029}, index=months)
    aligned = 0.9 * f["MKT"] + 0.004 + f["RF"] + rng.normal(0, 0.01, 48)   # 진짜: 같은 달
    off = pd.Series(aligned.values, index=months + 1)                       # 백테스트 +1 라벨 오프셋 모사
    hist = [{"date": str(p.to_timestamp(how="end").date()), "r_v37_2_%": float(v) * 100}
            for p, v in zip(off.index, off.values)]
    json.dump({"history": hist}, open("_diag_bt.json", "w", encoding="utf-8"))
    f.to_csv("_diag_f.csv")
    best = run("_diag_bt.json", "_diag_f.csv")
    for x in ("_diag_bt.json", "_diag_f.csv"):
        try: os.remove(x)
        except OSError: pass
    assert best is not None and best[0] == -1, f"기대 lag=-1, got {best[0] if best else None}"
    print("\n[OK] diagnose_alignment selftest 통과 (lag=-1에서 MKT~0.9 복원)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backtest-json", default=None)
    ap.add_argument("--factors", default="korea_factors_monthly.csv")
    ap.add_argument("--variant", default="r_v37_2_%")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    bj = a.backtest_json or (sorted(glob.glob("backtest_v37_2_*.json"))[-1]
                             if glob.glob("backtest_v37_2_*.json") else None)
    if not bj:
        raise SystemExit("backtest_v37_2_*.json 없음")
    print(f"백테스트: {bj}\n팩터: {a.factors}\n")
    run(bj, a.factors, a.variant)


if __name__ == "__main__":
    sys.exit(main() or 0)
