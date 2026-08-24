"""
진우퀀트 v3.7 영역 1 — 팩터 자기진단 하니스 (skeleton)
======================================================
신규 팩터 후보가 score 에 편입될 자격이 있는지 게이트(G1~G6)로 판정.
초안(진우퀀트_v37_영역1_팩터_초안.md) §4 게이트를 코드화.

핵심:
  - Rank IC (Spearman) / IC_IR
  - 팩터 간 cross-sectional rank 상관
  - 순차 잔차화(residualize): 신규 팩터에서 기존 팩터로 설명되는 부분 제거 → '추가 정보'만
  - 분위 스프레드(top-bottom tertile)
  - 후보 팩터 계산기: 52주 신고가 근접도 / gross profitability / SUE(seasonal-RW)

<<PLUG>> 실데이터: build_factor_panel_fdr_dart() 에 FDR(가격)+DART(재무) 연결.
실행:  python3 factor_diagnosis.py    (합성 데이터 스모크 — 게이트 동작 검증)
"""
from __future__ import annotations
import warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

# ============================ 0. 게이트 기준 ================================
GATES = dict(IC_MIN=0.03, ICIR_MIN=0.30, CORR_MAX=0.60, RESID_IC_MIN=0.02)


# ====================== 1. 후보 팩터 계산기 ================================

def f_52w_high_proximity(close: pd.DataFrame, window: int = 252) -> pd.DataFrame:
    """현재가 / 52주 종가 최고 (1에 가까울수록 신고가 부근). George & Hwang."""
    return close / close.rolling(window, min_periods=60).max()


def f_gross_profitability(sales: pd.DataFrame, cogs: pd.DataFrame,
                          total_assets: pd.DataFrame) -> pd.DataFrame:
    """(매출 − 매출원가) / 총자산. Novy-Marx. (분기 재무 → 일별로 ffill 해서 사용)"""
    return (sales - cogs) / total_assets.replace(0, np.nan)


def f_sue_seasonal_rw(eps_q: pd.DataFrame, lag: int = 4, win: int = 8) -> pd.DataFrame:
    """SUE = (EPS_t − EPS_{t-4}) / σ(서프라이즈). 컨센서스 없이 seasonal-RW 자가계산.
    eps_q: 분기 EPS 패널 [분기 x 종목]. 컨센서스가 있으면 그걸로 대체 권장."""
    surprise = eps_q - eps_q.shift(lag)
    sd = surprise.rolling(win, min_periods=4).std()
    return surprise / sd.replace(0, np.nan)


# ====================== 2. 진단 지표 =======================================

def forward_return(close: pd.DataFrame, horizon: int = 21) -> pd.DataFrame:
    """horizon 거래일 선행수익률 (look-ahead 없음: t 시점 팩터 ↔ t→t+h 수익)."""
    return close.pct_change(horizon).shift(-horizon)


def rank_ic(factor: pd.DataFrame, fwd: pd.DataFrame, min_names: int = 5) -> pd.Series:
    """일별 cross-sectional Spearman IC (= rank 들의 Pearson)."""
    idx = factor.index.intersection(fwd.index)
    out = {}
    for d in idx:
        f, r = factor.loc[d], fwd.loc[d]
        m = f.notna() & r.notna()
        if m.sum() < min_names:
            continue
        fr, rr = f[m].rank(), r[m].rank()
        if fr.std() == 0 or rr.std() == 0:
            continue
        out[d] = fr.corr(rr)
    return pd.Series(out)


def ic_summary(ic: pd.Series) -> dict:
    mean = ic.mean()
    sd = ic.std()
    icir = mean / sd * np.sqrt(252 / 21) if sd > 0 else np.nan   # 월간(h=21) 기준 연율화
    return {"mean_IC": mean, "IC_std": sd, "IC_IR": icir, "n": int(ic.notna().sum())}


def factor_corr(factors: dict, min_names: int = 5) -> pd.DataFrame:
    """팩터 쌍별 평균 cross-sectional rank 상관."""
    names = list(factors)
    dates = None
    for df in factors.values():
        dates = df.index if dates is None else dates.intersection(df.index)
    M = pd.DataFrame(np.eye(len(names)), index=names, columns=names)
    for i in range(len(names)):
        for j in range(i + 1, len(names)):
            cs = []
            for d in dates:
                a, b = factors[names[i]].loc[d], factors[names[j]].loc[d]
                m = a.notna() & b.notna()
                if m.sum() < min_names:
                    continue
                ar, br = a[m].rank(), b[m].rank()
                if ar.std() and br.std():
                    cs.append(ar.corr(br))
            r = np.nanmean(cs) if cs else np.nan
            M.iloc[i, j] = M.iloc[j, i] = r
    return M


def residualize(target: pd.DataFrame, bases: list, min_names: int = 6) -> pd.DataFrame:
    """매 시점 target 을 base 팩터들에 cross-sectional OLS → 잔차(직교 성분) 반환."""
    if not bases:
        return target.copy()                      # 직교화할 기존 팩터 없음 → 원본
    idx = target.index
    for b in bases:
        idx = idx.intersection(b.index)
    res = pd.DataFrame(index=idx, columns=target.columns, dtype=float)
    for d in idx:
        y = target.loc[d]
        X = pd.concat([b.loc[d] for b in bases], axis=1)
        m = y.notna() & X.notna().all(axis=1)
        if m.sum() < min_names:
            continue
        Xn = np.column_stack([np.ones(m.sum())] + [X.loc[m].iloc[:, k].values
                                                   for k in range(X.shape[1])])
        yn = y[m].values
        beta, *_ = np.linalg.lstsq(Xn, yn, rcond=None)
        res.loc[d, m.values] = yn - Xn @ beta
    return res


def quantile_spread(factor: pd.DataFrame, fwd: pd.DataFrame, q: int = 3) -> float:
    """상위 분위 − 하위 분위 평균 선행수익률 (분위 q=3: 18종목엔 tertile)."""
    idx = factor.index.intersection(fwd.index)
    diffs = []
    for d in idx:
        f, r = factor.loc[d], fwd.loc[d]
        m = f.notna() & r.notna()
        if m.sum() < q * 2:
            continue
        fr = f[m]
        lo, hi = fr.quantile(1 / q), fr.quantile(1 - 1 / q)
        top, bot = r[m][fr >= hi], r[m][fr <= lo]
        if len(top) and len(bot):
            diffs.append(top.mean() - bot.mean())
    return float(np.mean(diffs)) if diffs else np.nan


# ====================== 3. 게이트 판정 =====================================

def evaluate_candidate(name: str, factor: pd.DataFrame, fwd: pd.DataFrame,
                       existing: dict, gates: dict = GATES) -> dict:
    ic = rank_ic(factor, fwd)
    s = ic_summary(ic)
    # G3: 기존 팩터 대비 최대 상관
    corr_row = factor_corr({**existing, name: factor}).loc[name].drop(name)
    max_corr = corr_row.abs().max()
    # G4: 기존 전체에 직교화한 잔차의 IC
    resid = residualize(factor, list(existing.values()))
    resid_ic = ic_summary(rank_ic(resid, fwd))["mean_IC"]
    # G6: 전·후반 부호 일관성
    half = len(ic) // 2
    g6 = (np.sign(ic.iloc[:half].mean()) == np.sign(ic.iloc[half:].mean())) if half > 5 else None
    spread = quantile_spread(factor, fwd)

    res = {
        "factor": name, "mean_IC": s["mean_IC"], "IC_IR": s["IC_IR"],
        "max_corr_existing": max_corr, "resid_mean_IC": resid_ic,
        "tertile_spread": spread,
        "G1_IC": abs(s["mean_IC"]) >= gates["IC_MIN"],
        "G2_ICIR": abs(s["IC_IR"]) >= gates["ICIR_MIN"],
        "G3_orthogonal": (max_corr < gates["CORR_MAX"]) if pd.notna(max_corr) else None,
        "G4_resid_IC": abs(resid_ic) >= gates["RESID_IC_MIN"],
        "G6_sign_stable": g6,
    }
    res["VERDICT"] = "PASS" if all(res[g] for g in
                                   ["G1_IC", "G2_ICIR", "G3_orthogonal", "G4_resid_IC"]
                                   if res[g] is not None) else "FAIL/연기"
    return res


# ====================== 4. 실데이터 로더 (PLUG) ============================

# 실데이터 패널 구성은 factor_data_loader.py 로 이전:
#   from factor_data_loader import build_factor_panel_fdr_dart, run_factor_diagnosis
# (FDR 가격 + OpenDART 분기재무 + point-in-time + 기존팩터 병합 hook)


# ====================== 5. 합성 스모크 =====================================

def _synthetic(n_days=500, n=10, seed=3):
    """알려진 IC를 심은 합성 패널: true(예측력 O) / redundant(true와 고상관) / junk(노이즈)."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2022-01-03", periods=n_days)
    cols = [f"S{i:02d}" for i in range(n)]
    true = pd.DataFrame(rng.normal(size=(n_days, n)), index=dates, columns=cols)
    true = true.rolling(20, min_periods=1).mean()                      # 완만한 팩터
    # 선행수익률 = true 의 rank 에 비례 + 노이즈 (IC 양수가 되도록)
    fwd = pd.DataFrame(index=dates, columns=cols, dtype=float)
    for d in dates:
        rk = true.loc[d].rank() / n - 0.5
        fwd.loc[d] = 0.02 * rk.values + rng.normal(0, 0.03, n)
    redundant = true + rng.normal(0, 0.2, (n_days, n))                 # true 와 고상관
    junk = pd.DataFrame(rng.normal(size=(n_days, n)), index=dates, columns=cols)
    existing = {"F_true": true}
    return existing, fwd, {"redundant": redundant, "junk": junk}


def main():
    print("=" * 74)
    print(" 팩터 자기진단 하니스 — 합성 스모크 (게이트 동작 검증)")
    print("=" * 74)
    existing, fwd, cands = _synthetic()

    print("\n[기준 팩터 F_true 자체 IC]")
    print(" ", ic_summary(rank_ic(existing["F_true"], fwd)))

    rows = []
    # redundant: F_true 와 고상관 → G3/G4 탈락해야 정상
    rows.append(evaluate_candidate("redundant", cands["redundant"], fwd, existing))
    # junk: IC≈0 → G1/G2 탈락
    rows.append(evaluate_candidate("junk", cands["junk"], fwd, existing))
    # F_true 를 빈 기존집합에 → 통과해야 정상
    rows.append(evaluate_candidate("F_true_solo", existing["F_true"], fwd, {}))

    df = pd.DataFrame(rows)
    show = df[["factor", "mean_IC", "IC_IR", "max_corr_existing", "resid_mean_IC",
               "tertile_spread", "VERDICT"]].copy()
    for c in ["mean_IC", "IC_IR", "max_corr_existing", "resid_mean_IC", "tertile_spread"]:
        show[c] = show[c].map(lambda x: f"{x:.3f}" if pd.notna(x) else "—")
    print("\n[후보 진단]")
    print(show.to_string(index=False))
    print("\n 해석: redundant=F_true와 고상관→G3/G4 탈락 / junk=무예측력→G1·G2 탈락 /")
    print("       F_true_solo=PASS. 게이트가 '중복'과 '무력' 팩터를 정확히 걸러내면 정상.")


if __name__ == "__main__":
    main()
