"""
regime_overlay.py  —  진우퀀트 ① C1 regime 오버레이 + ② 단순화 attribution
==========================================================================
모두 point-in-time(룩어헤드 금지). 월말 t 시점 정보로 t+1월 비중 결정.

C1(①): compute_regime() — KOSPI 추세 AND 변동성 비극단 → risk-ON/OFF 단일 플래그
        Daniel-Moskowitz(2016): 크래시는 '하락 후·고변동성·반등'에 몰림 → 변동성 필터 필수.
        장지원(2017): Echo 알파는 상승장 집중 → ON시 Echo 가중↑.
②: leave_one_out_spec() / ols_attribution() — Mom12·BAB 한계기여 측정.

의존성: numpy, pandas.
"""
import numpy as np
import pandas as pd


# ============ ① C1 regime 시그널 ============
def compute_regime(close, vol=None, L=12, trend_mode="sma",
                   vol_thresh_q=0.75, hysteresis=0.0, min_hold=1):
    """
    월간 시계열로 risk-ON(1)/OFF(0) 플래그 생성. 모두 t 시점까지의 정보만 사용.

    close : pd.Series  KOSPI 월말 종가 (DatetimeIndex)
    vol   : pd.Series  VKOSPI(또는 60일 실현변동성) 월말값. None이면 변동성 필터 생략.
    L     : 추세 lookback (개월). trend_mode='sma' → close>SMA(L); 'ret' → L개월 수익률>0
    vol_thresh_q : 변동성 임계 분위수 (expanding, 룩어헤드 방지). vol<=임계 → 통과
    hysteresis   : SMA 대비 이탈 완충 (예 0.03 = SMA의 3% 아래로 내려가야 OFF). whipsaw 억제
    min_hold     : 전환 후 최소 유지 개월 수
    반환: pd.Series(0/1), index=close.index
    """
    close = close.astype(float)
    if trend_mode == "sma":
        sma = close.rolling(L, min_periods=L).mean()
        enter = close > sma                      # ON 진입 조건
        exit_ = close < sma * (1 - hysteresis)   # OFF 이탈 조건(히스테리시스)
    elif trend_mode == "ret":
        past = close.shift(L)
        trend_up = (close / past - 1) > 0
        enter = trend_up
        exit_ = ~trend_up
    else:
        raise ValueError("trend_mode must be 'sma' or 'ret'")

    if vol is not None:
        vol = vol.reindex(close.index).astype(float)
        # expanding 분위수(과거값만) → 룩어헤드 없음
        thr = vol.expanding(min_periods=12).quantile(vol_thresh_q)
        vol_ok = vol <= thr
    else:
        vol_ok = pd.Series(True, index=close.index)

    # 상태기계: enter & vol_ok 면 ON, exit_ 면 OFF, min_hold 강제
    state = 0; hold = 0; out = []
    for i in range(len(close)):
        e = bool(enter.iloc[i]) and bool(vol_ok.iloc[i]) if not (
            pd.isna(enter.iloc[i]) or (vol is not None and pd.isna(vol_ok.iloc[i]))) else False
        x = bool(exit_.iloc[i]) if not pd.isna(exit_.iloc[i]) else True
        if hold < min_hold and len(out) > 0:
            state = out[-1]; hold += 1
        else:
            if state == 0 and e:
                state = 1; hold = 1
            elif state == 1 and (x or not (vol_ok.iloc[i] if vol is not None else True)):
                state = 0; hold = 1
        out.append(state)
    return pd.Series(out, index=close.index, name="regime_on")


def echo_weight_schedule(regime, w_on=1.2, w_off=1.0):
    """ON/OFF에 따른 Echo 가중치 시계열. (1차 레버: 장지원 상승장 근거)"""
    return regime.map({1: w_on, 0: w_off}).rename("echo_weight")


def bab_weight_schedule(regime, k_on=0.0, k_off=1.0):
    """ON시 BAB 가중 축소(상승 참여↑), OFF시 유지(방어). (2차 레버: Novy-Marx-Velikov)"""
    return regime.map({1: k_on, 0: k_off}).rename("bab_weight")


# ============ ② 한계기여 / attribution ============
def leave_one_out_spec(base_factors, factor_to_drop):
    """
    백테스트 재실행용 스펙 생성기(하니스). 실제 백테스트 함수는 진우퀀트 측 score 엔진.
    사용 예:
        for f in ['Mom12','BAB']:
            spec = leave_one_out_spec(BASE_FACTORS, f)
            m = run_backtest(spec)         # ← 기존 백테스트 함수 연결
            delta = compare(m, baseline)   # ΔCAGR, ΔSharpe, ΔMDD, Δturnover
    """
    return [f for f in base_factors if f != factor_to_drop]


def ols_attribution(excess_ret, factors, nw_lags=6):
    """
    전략 초과수익을 팩터로 분해 (CAPM→FF3→Carhart). Newey-West(HAC) t-통계량.
    excess_ret : pd.Series (월간 초과수익)
    factors    : pd.DataFrame (열=설명 팩터: MKT, SMB, HML, WML ...)
    반환: DataFrame [coef, t_stat]  (index: 'alpha' + 팩터명).  alpha 유의(|t|>2)면 팩터로 설명 안 됨.
    """
    y = excess_ret.dropna()
    X = factors.reindex(y.index).dropna()
    y = y.reindex(X.index)
    Xm = np.column_stack([np.ones(len(X)), X.values])
    names = ["alpha"] + list(X.columns)
    beta, *_ = np.linalg.lstsq(Xm, y.values, rcond=None)
    resid = y.values - Xm @ beta
    n, k = Xm.shape
    XtX_inv = np.linalg.inv(Xm.T @ Xm)
    # Newey-West HAC
    S = (resid[:, None]**2 * Xm).T @ Xm
    for L in range(1, nw_lags + 1):
        w = 1 - L/(nw_lags + 1)
        G = np.zeros((k, k))
        for t in range(L, n):
            G += resid[t]*resid[t-L] * np.outer(Xm[t], Xm[t-L])
        S += w * (G + G.T)
    cov = XtX_inv @ S @ XtX_inv
    se = np.sqrt(np.diag(cov))
    return pd.DataFrame({"coef": beta, "t_stat": beta/se}, index=names)


# ============ self-test ============
if __name__ == "__main__":
    rng = np.random.default_rng(3)
    idx = pd.date_range("2018-01-31", periods=90, freq="ME")
    # 합성 KOSPI: 상승 추세 + 하락 충격 구간
    shocks = rng.normal(0.004, 0.05, 90)
    shocks[40:46] -= 0.06           # 하락 구간
    close = pd.Series(2000*np.cumprod(1+shocks), index=idx)
    vol = pd.Series(np.abs(rng.normal(18, 6, 90)), index=idx)
    vol.iloc[40:48] += 18           # 하락기 변동성 급등

    reg = compute_regime(close, vol, L=12, trend_mode="sma",
                         vol_thresh_q=0.75, hysteresis=0.03, min_hold=2)
    ew = echo_weight_schedule(reg, 1.2, 1.0)
    print("=== C1 regime 시그널 ===")
    print(f"ON 비율 = {reg.mean():.2%} | 전환 횟수 = {int((reg.diff().abs()==1).sum())}")
    print(f"하락구간(idx40~47) ON 비율 = {reg.iloc[40:48].mean():.2%}  (낮아야 정상)")
    print(f"Echo 가중 분포: {ew.value_counts().to_dict()}")

    print("\n=== ② OLS attribution (합성) ===")
    f = pd.DataFrame({
        "MKT": rng.normal(0.01, 0.04, 90),
        "SMB": rng.normal(0.00, 0.03, 90),
        "HML": rng.normal(0.00, 0.03, 90),
        "WML": rng.normal(0.005, 0.04, 90),
    }, index=idx)
    strat = 0.004 + 0.9*f["MKT"] + 0.5*f["WML"] + rng.normal(0, 0.02, 90)  # 진짜 alpha 0.4%/월
    print(ols_attribution(strat, f, nw_lags=6).round(3).to_string())
    print("\n[OK] regime_overlay self-test 완료")
