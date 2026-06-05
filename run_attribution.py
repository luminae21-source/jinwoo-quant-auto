#!/usr/bin/env python3
"""
run_attribution.py — 진우퀀트 v3.7.2 FF/Carhart attribution (날짜 정렬 자동 보정)
==============================================================================
입력: 패치된 backtest_v37_2_*.json(history r_v37_2_%) + korea_factors_monthly.csv
처리: v37_2 월수익 − RF 를 한국 4팩터에 회귀(ols_attribution, Newey-West).
      백테스트 라벨이 월말 기준 팩터와 한 칸 어긋날 수 있어 lag −1/0/+1 중
      MKT 베타가 가장 정상(|t| 최대)인 정렬을 자동 채택 → 그 alpha가 '진짜'.
사용: python run_attribution.py    /    --lag -1|0|1 (수동)   /   --selftest
"""
import argparse, glob, json, sys, os
import numpy as np, pandas as pd


def _pm(x):
    return pd.PeriodIndex(pd.to_datetime(x), freq="M")


def load_strategy_returns(bj, variant="r_v37_2_%"):
    rep = json.load(open(bj, encoding="utf-8"))
    hist = rep.get("history") or []
    if not hist or variant not in hist[0]:
        raise SystemExit(f"history에 {variant} 없음 → 패치된 backtest_v37_2.py 재실행 필요: {bj}")
    df = pd.DataFrame(hist)
    s = pd.Series([(v or 0) / 100.0 for v in df[variant]], index=_pm(df["date"]))
    return s[~s.index.duplicated(keep="last")].sort_index()


def _attr_at_lag(strat, f, rf, cols, L, nw_lags):
    import regime_overlay as R
    s = pd.Series(strat.values, index=strat.index + L)
    common = s.index.intersection(f.index)
    ex = (s.reindex(common) - rf.reindex(common)).dropna()
    if len(ex) < 12:
        return None
    return R.ols_attribution(ex, f.loc[ex.index, cols], nw_lags=nw_lags), len(ex)


def run(bj, factors_csv, variant="r_v37_2_%", lag="auto", nw_lags=6):
    strat = load_strategy_returns(bj, variant)
    f = pd.read_csv(factors_csv, index_col=0); f.index = _pm(f.index)
    cols = [c for c in ["MKT", "SMB", "HML", "WML"] if c in f.columns and f[c].notna().mean() >= 0.5]
    rf = f["RF"] if "RF" in f.columns else pd.Series(0.0, index=f.index)
    res_by = {}
    for L in (-1, 0, 1):
        out = _attr_at_lag(strat, f, rf, cols, L, nw_lags)
        if out: res_by[L] = out
    if not res_by:
        raise SystemExit("공통 월 부족(≥12) — 날짜/기간 확인.")
    Lbest = int(lag) if lag != "auto" else max(res_by, key=lambda L: abs(res_by[L][0].loc["MKT", "t_stat"]))

    print(f"사용 팩터 {cols}" + (" (HML 제외=book 없음)" if "HML" not in cols else ""))
    print("\n날짜 정렬 후보 (long-only는 MKT 베타가 정상이어야 함 → |MKT t| 최대 채택):")
    for L in sorted(res_by):
        r, n = res_by[L]
        mark = "  ← 채택" if L == Lbest else ""
        print(f"  lag={L:+d}: MKT {r.loc['MKT','coef']:5.2f} (t{r.loc['MKT','t_stat']:5.1f}) | "
              f"alpha 월 {r.loc['alpha','coef']*100:+5.2f}% (t{r.loc['alpha','t_stat']:4.1f}){mark}")

    res, n = res_by[Lbest]
    print(f"\n=== v3.7.2 FF/Carhart attribution (lag={Lbest:+d} 자동보정, {n}개월) ===")
    print(res.round(3).to_string())
    a, at = res.loc["alpha", "coef"], res.loc["alpha", "t_stat"]
    mkt_t = res.loc["MKT", "t_stat"]
    print(f"\n진짜 alpha: 월 {a*100:+.2f}%  (연 {((1+a)**12-1)*100:+.1f}%),  t={at:.2f}")
    if Lbest != 0:
        print(f"  (백테스트 라벨이 월말 팩터와 {Lbest:+d}개월 어긋나 자동 보정함 — MKT 베타 정상화)")
    if abs(mkt_t) < 2:
        print("  ⚠️ 최선 정렬에서도 MKT t<2 → 데이터 추가 점검 권장")
    elif at >= 2:
        print("  ✅ MKT 정상 + alpha 유의 = 4팩터로 설명 안 되는 진짜 고유 alpha")
    else:
        print("  → MKT 정상화 후 alpha 유의성 약함 = 수익 상당부분이 시장/팩터로 설명됨")
    big = res.drop("alpha")["coef"].abs().idxmax()
    print(f"  최대 노출 팩터: {big} (coef {res.loc[big,'coef']:.2f}, t {res.loc[big,'t_stat']:.1f})")
    return res


def _selftest():
    rng = np.random.default_rng(0)
    months = pd.period_range("2022-01", periods=48, freq="M")
    f = pd.DataFrame({"MKT": rng.normal(0.01, 0.05, 48), "SMB": rng.normal(0, 0.03, 48),
                      "HML": rng.normal(0, 0.03, 48), "WML": rng.normal(0, 0.04, 48),
                      "RF": 0.0029}, index=months)
    aligned = 0.9 * f["MKT"] + 0.004 + f["RF"] + rng.normal(0, 0.01, 48)
    off = pd.Series(aligned.values, index=months + 1)   # +1 라벨 오프셋
    hist = [{"date": str(p.to_timestamp(how="end").date()), "r_v37_2_%": float(v) * 100}
            for p, v in zip(off.index, off.values)]
    json.dump({"history": hist}, open("_ra_bt.json", "w", encoding="utf-8"))
    f.to_csv("_ra_f.csv")
    res = run("_ra_bt.json", "_ra_f.csv")
    for x in ("_ra_bt.json", "_ra_f.csv"):
        try: os.remove(x)
        except OSError: pass
    assert abs(res.loc["MKT", "coef"] - 0.9) < 0.15, "자동보정 후 MKT~0.9 복원 실패"
    print("\n[OK] run_attribution selftest 통과 (자동 lag 보정 작동)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--backtest-json", default=None)
    ap.add_argument("--factors", default="korea_factors_monthly.csv")
    ap.add_argument("--variant", default="r_v37_2_%")
    ap.add_argument("--lag", default="auto", help="auto(기본) | -1 | 0 | 1")
    ap.add_argument("--nw-lags", type=int, default=6)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    bj = a.backtest_json
    if not bj:
        c = sorted(glob.glob("backtest_v37_2_*.json"))
        if not c: raise SystemExit("backtest_v37_2_*.json 없음 → 패치된 backtest_v37_2.py 먼저 실행.")
        bj = c[-1]; print(f"백테스트 자동 선택: {bj}")
    if not os.path.exists(a.factors):
        raise SystemExit(f"{a.factors} 없음 → build_korea_factors.py 먼저 실행.")
    run(bj, a.factors, a.variant, a.lag, a.nw_lags)


if __name__ == "__main__":
    sys.exit(main() or 0)
