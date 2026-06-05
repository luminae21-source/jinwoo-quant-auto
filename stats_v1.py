"""
stats_v1.py  —  진우퀀트 ③ 다중검정/강건성 통계 모듈
신규 팩터/파라미터 채택 전 "우연이 아닌가"를 정량 판정하는 게이트.
  probabilistic_sharpe_ratio / expected_max_sharpe / deflated_sharpe_ratio
  pbo_cscv / block_bootstrap_ci / reality_check_spa
의존성: numpy 만. 단위: 월간 수익률·월 Sharpe. 연 Sharpe = 월×sqrt(12).
"""
import numpy as np
import itertools
import math

def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))

def norm_ppf(p):
    if p <= 0.0: return -np.inf
    if p >= 1.0: return np.inf
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02,
         1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02,
         6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00,
         -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    plow, phigh = 0.02425, 1 - 0.02425
    if p < plow:
        q = math.sqrt(-2*math.log(p))
        return (((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    if p > phigh:
        q = math.sqrt(-2*math.log(1-p))
        return -(((((c[0]*q+c[1])*q+c[2])*q+c[3])*q+c[4])*q+c[5])/((((d[0]*q+d[1])*q+d[2])*q+d[3])*q+1)
    q = p-0.5; r = q*q
    return (((((a[0]*r+a[1])*r+a[2])*r+a[3])*r+a[4])*r+a[5])*q/(((((b[0]*r+b[1])*r+b[2])*r+b[3])*r+b[4])*r+1)

def _moments(returns):
    r = np.asarray(returns, float)
    n = len(r); mu = r.mean(); sd = r.std(ddof=1); sr = mu/sd
    g3 = ((r-mu)**3).mean()/sd**3
    g4 = ((r-mu)**4).mean()/sd**4
    return n, sr, g3, g4

def sharpe(returns, periods_per_year=12, annualize=True):
    _, sr, _, _ = _moments(returns)
    return sr*math.sqrt(periods_per_year) if annualize else sr

def probabilistic_sharpe_ratio(returns, sr_benchmark=0.0):
    n, sr, g3, g4 = _moments(returns)
    denom = math.sqrt(max(1e-12, 1 - g3*sr + (g4-1)/4.0*sr**2))
    return norm_cdf((sr - sr_benchmark)*math.sqrt(n-1)/denom)

def expected_max_sharpe(n_trials, var_sr):
    gamma = 0.5772156649015329
    z1 = norm_ppf(1 - 1.0/n_trials)
    z2 = norm_ppf(1 - 1.0/(n_trials*math.e))
    return math.sqrt(var_sr)*((1-gamma)*z1 + gamma*z2)

def deflated_sharpe_ratio(returns, n_trials, var_sr=None, sr_trials=None):
    n, sr, g3, g4 = _moments(returns)
    if var_sr is None:
        if sr_trials is None: raise ValueError("var_sr 또는 sr_trials 필요")
        var_sr = np.var(np.asarray(sr_trials, float), ddof=1)
    sr0 = expected_max_sharpe(n_trials, var_sr)
    denom = math.sqrt(max(1e-12, 1 - g3*sr + (g4-1)/4.0*sr**2))
    return norm_cdf((sr - sr0)*math.sqrt(n-1)/denom), sr, sr0

def pbo_cscv(returns_matrix, S=16):
    M = np.asarray(returns_matrix, float); T, N = M.shape
    blocks = np.array_split(np.arange(T), S)
    def msr(x):
        sd = x.std(ddof=1); return x.mean()/sd if sd > 0 else 0.0
    logits = []
    for comb in itertools.combinations(range(S), S//2):
        isr = np.concatenate([blocks[i] for i in comb])
        oos = np.concatenate([blocks[i] for i in range(S) if i not in comb])
        ip = np.array([msr(M[isr, j]) for j in range(N)])
        op = np.array([msr(M[oos, j]) for j in range(N)])
        ns = int(np.argmax(ip))
        rank = (op <= op[ns]).sum()/(N+1.0)
        rank = min(max(rank, 1.0/(N+1)), N/(N+1.0))
        logits.append(math.log(rank/(1-rank)))
    logits = np.array(logits)
    return float((logits <= 0).mean()), logits

def _stationary_idx(T, mean_block, rng):
    p = 1.0/mean_block; idx = np.empty(T, dtype=int); idx[0] = rng.integers(0, T)
    for i in range(1, T):
        idx[i] = rng.integers(0, T) if rng.random() < p else (idx[i-1]+1) % T
    return idx

def block_bootstrap_ci(returns, stat_func, mean_block=4, n_boot=10000, alpha=0.05, seed=0):
    r = np.asarray(returns, float); T = len(r); rng = np.random.default_rng(seed)
    boot = np.empty(n_boot)
    for b in range(n_boot):
        boot[b] = stat_func(r[_stationary_idx(T, mean_block, rng)])
    lo, hi = np.quantile(boot, [alpha/2, 1-alpha/2])
    return float(lo), float(hi), float(stat_func(r)), float(boot.mean())

def reality_check_spa(trial_returns, benchmark=None, mean_block=4, n_boot=2000, seed=0):
    """White RC(2000, p_white_rc=바인딩) + Hansen SPA(2005, p_hansen_spa=소표본 정보용)."""
    D = np.asarray(trial_returns, float); T, N = D.shape
    b = 0.0 if benchmark is None else np.asarray(benchmark, float).reshape(-1, 1)
    d = D - b; dbar = d.mean(axis=0); sqrtT = math.sqrt(T)
    rng = np.random.default_rng(seed); bm = np.empty((n_boot, N))
    for bi in range(n_boot):
        bm[bi] = d[_stationary_idx(T, mean_block, rng)].mean(axis=0)
    omega = np.sqrt(np.mean((sqrtT*(bm-dbar))**2, axis=0)); omega = np.where(omega < 1e-12, 1e-12, omega)
    rc_stat = max(0.0, float(np.max(sqrtT*dbar)))
    V_rc = np.max(sqrtT*(bm-dbar), axis=1); p_rc = float(np.mean(V_rc > rc_stat))
    t_k = sqrtT*dbar/omega
    llT = math.log(math.log(T)) if T > math.e else 1e-9
    incl = t_k >= -math.sqrt(2*max(llT, 1e-9))
    spa_stat = max(0.0, float(np.max(t_k[incl]))) if incl.any() else 0.0
    Z = np.where(incl[None, :], sqrtT*(bm-dbar)/omega, -np.inf)
    Tb = np.maximum(np.max(Z, axis=1), 0.0); p_spa = float(np.mean(Tb > spa_stat))
    return {"rc_stat": rc_stat, "p_white_rc": p_rc, "spa_stat": spa_stat, "p_hansen_spa": p_spa,
            "spa_reliable": bool(T >= 120), "best_trial": int(np.argmax(dbar)),
            "note": "T<120이면 SPA 과대기각 가능 → 바인딩 게이트는 White RC + DSR + PBO."}

if __name__ == "__main__":
    rng = np.random.default_rng(7); T = 49
    ret = rng.normal(0.046, 0.0731, T)
    print("=== 단일 전략 ===")
    print(f"월 Sharpe={sharpe(ret, annualize=False):.3f} | 연 Sharpe={sharpe(ret):.3f} | PSR={probabilistic_sharpe_ratio(ret):.4f}")
    N = 40; srt = rng.normal(0.30, 0.10, N)
    dsr, srm, sr0 = deflated_sharpe_ratio(ret, n_trials=N, sr_trials=srt)
    print(f"=== DSR (N={N}) ===  sr월={srm:.3f} sr0={sr0:.3f} DSR={dsr:.4f} (>0.95 통과)")
    M = rng.normal(0, 0.0731, (T, 30)); M[:, 0] += 0.010
    pbo, lg = pbo_cscv(M, S=14)
    print(f"=== PBO ===  {pbo:.3f} (<0.5 필수)")
    lo, hi, pt, _ = block_bootstrap_ci(ret, lambda x: x.mean()/x.std(ddof=1)*math.sqrt(12), mean_block=4, n_boot=5000, seed=1)
    print(f"=== Block bootstrap ===  연 Sharpe={pt:.2f} 95%CI=[{lo:.2f},{hi:.2f}]")
    Mn = rng.normal(0, 0.0731, (T, 30)); r1 = reality_check_spa(Mn, n_boot=1500, seed=2)
    Mr = rng.normal(0, 0.0731, (T, 30)); Mr[:, 5] += 0.030; r2 = reality_check_spa(Mr, n_boot=1500, seed=2)
    print(f"=== White RC/SPA ===  노이즈 White={r1['p_white_rc']:.3f}(높아야정상) | 알파 White={r2['p_white_rc']:.3f}(낮아야정상,best=t{r2['best_trial']})")
    print("[OK] stats_v1 self-test 완료")
