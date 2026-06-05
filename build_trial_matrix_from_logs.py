"""
build_trial_matrix_from_logs.py — 과거 백테스트 JSON에서 trial 월수익 T×N 행렬 복원 → ③ 통계
각 backtest_*.json 의 history[].r_<variant>_% 를 모아 변종별 월수익 시계열로 합치고,
stats_v1 로 DSR/PBO/White RC 산출. (production v37_2는 history 미저장 → 별도 재실행 필요로 표시)
"""
import json, glob, os, math
import numpy as np, pandas as pd
import stats_v1 as S

series, src = {}, {}
for f in sorted(glob.glob("backtest_*.json")):
    try: o = json.load(open(f, encoding="utf-8"))
    except Exception: continue
    h = o.get("history") or []
    if not h or "date" not in h[0]: continue
    dates = pd.to_datetime([e.get("date") for e in h])
    for k in h[0]:
        if k.startswith("r_") and k.endswith("_%"):
            var = k[2:-2]
            if var in series: continue           # 변종별 1회만(파일 간 동일)
            series[var] = pd.Series([(e.get(k) or 0)/100.0 for e in h], index=dates)
            src[var] = f

mat = pd.DataFrame(series).sort_index()
bench = mat.pop("kospi") if "kospi" in mat.columns else None
mat = mat.dropna(how="any")
print(f"복원된 trial 행렬: {mat.shape[0]}개월 × {mat.shape[1]}개 변종")
print("변종:", list(mat.columns))

print("\n=== 무결성: 복원 CAGR / 연Sharpe (월수익 기반) ===")
sr_m = []
for c in mat.columns:
    r = mat[c].values
    cagr = np.prod(1+r)**(12/len(r)) - 1
    shp = S.sharpe(r)                 # 연 Sharpe
    sr_m.append(S.sharpe(r, annualize=False))
    print(f"  {c:10s} CAGR={cagr:7.1%}  연Sharpe={shp:5.2f}")

best = int(np.argmax(sr_m))
print(f"\n최고 변종: {mat.columns[best]}")
N = mat.shape[1]
dsr, srx, sr0 = S.deflated_sharpe_ratio(mat.iloc[:, best].values, n_trials=N, sr_trials=sr_m)
pbo, _ = S.pbo_cscv(mat.values, S=8)
rc = S.reality_check_spa(mat.values, benchmark=(bench.reindex(mat.index).values if bench is not None else None),
                         n_boot=2000, seed=1)
print(f"=== ③ 실제 결과 (N={N} 변종; 설정변형 미포함 → 하한) ===")
print(f"  DSR(best)   = {dsr:.3f}   (>0.95 통과)")
print(f"  PBO         = {pbo:.3f}   (<0.5 필수)")
print(f"  White RC p  = {rc['p_white_rc']:.3f} (vs KOSPI; <0.05면 우연 아님)")
mat.to_csv("trial_returns_matrix.csv")
print("\n저장: trial_returns_matrix.csv")
print("주의: production v37_2 월수익은 history 미저장 → backtest_v37_2.py에 history 로깅 추가 후 재실행 권장.")
print("주의: n_trials는 변종 수만 반영(설정변형·Echo가중·cap 옵션 미포함) → 실제 N=30~50로 상향해 DSR 재계산 필요.")
