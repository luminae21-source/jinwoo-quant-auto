"""
jq_adapter.py  —  진우퀀트 데이터·백테스트 어댑터 (stats_v1 / regime_overlay 연결)
================================================================================
역할: 진우님의 실제 점수 엔진/데이터를 stats_v1(③)·regime_overlay(①②)에 물리는 '레퍼런스 하니스'.
  1) 데이터 로더 훅(FDR) — 없으면 합성 데이터로 동작(테스트용)
  2) build_scores()        — 팩터 패널 + 가중치(+ regime 오버레이)로 월별 종목점수 합성
  3) backtest_long_only()  — top_n 선택·종목/섹터 cap·turnover·CAGR/Sharpe/MDD
  4) run_backtest(spec)    — 단일 인터페이스(②·trial 행렬이 호출)
  5) build_trial_matrix()  — 여러 spec → (T×N) 월수익 행렬 → stats_v1(DSR/PBO/RC)

연결 지점(실데이터): load_prices()/load_kospi_vkospi()의 FDR 부분, 그리고 진우님 팩터 패널.
의존성: numpy, pandas. (FinanceDataReader, stats_v1, regime_overlay 는 있으면 사용)
"""
import numpy as np
import pandas as pd

UNIVERSE_18 = ["삼성전자","SK하이닉스","한미반도체","알테오젠","기아","NAVER","카카오","한화에어로",
               "LIG넥스원","KB금융","KT&G","삼성SDI","아모레퍼시픽","삼성물산","삼양식품","ISC",
               "두산에너빌리티","NH투자증권"]

# ============ 1) 데이터 로더 (실데이터 연결 지점) ============
def load_prices(tickers, start, end):
    """일별 종가 DataFrame(date×ticker). FDR 연결 — 코드/티커 매핑은 진우님 측에서."""
    try:
        import FinanceDataReader as fdr
        out = {}
        for t in tickers:
            out[t] = fdr.DataReader(t, start, end)["Close"]   # TODO: 종목명→코드 매핑
        return pd.DataFrame(out)
    except Exception as e:
        raise RuntimeError(f"가격 로드 실패(FDR 연결 필요): {e}")

def load_kospi_vkospi(start, end):
    """KOSPI 지수(추세) + VKOSPI(변동성 필터). VKOSPI 미제공 시 None→실현변동성 대용."""
    import FinanceDataReader as fdr
    kospi = fdr.DataReader("KS11", start, end)["Close"]
    try:
        vkospi = fdr.DataReader("VKOSPI", start, end)["Close"]   # 미지원일 수 있음
    except Exception:
        vkospi = None
    return kospi, vkospi

def to_monthly_returns(daily_close):
    """일별 종가 → 월말 종가 → 월간 수익률."""
    m = daily_close.resample("ME").last()
    return m.pct_change().dropna(how="all")

# ============ 2) 점수 합성 (+ regime 오버레이) ============
def build_scores(factor_panels, weights, regime=None, echo_w=(1.2, 1.0), bab_w=(0.0, 1.0)):
    """
    factor_panels: dict{factor_name: DataFrame(month×ticker, z-score화 권장)}
    weights      : dict{factor_name: float} 기본 가중
    regime       : pd.Series(0/1) 월별 ON/OFF. 주면 'Echo'·'BAB' 가중을 월별로 조정(①).
    반환: 월별 종합점수 DataFrame(month×ticker)
    """
    months = next(iter(factor_panels.values())).index
    total = None
    for f, panel in factor_panels.items():
        w = pd.Series(weights.get(f, 0.0), index=months, dtype=float)
        if regime is not None and f == "Echo":
            w = regime.reindex(months).map({1: echo_w[0], 0: echo_w[1]}).fillna(echo_w[1])
        if regime is not None and f == "BAB":
            w = regime.reindex(months).map({1: bab_w[0], 0: bab_w[1]}).fillna(bab_w[1])
        contrib = panel.mul(w, axis=0)
        total = contrib if total is None else total.add(contrib, fill_value=0.0)
    return total

# ============ 3) 레퍼런스 백테스터 ============
def _cap_stock(w, cap, n_iter=50):
    w = w.copy()
    for _ in range(n_iter):
        over = w > cap + 1e-12
        if not over.any():
            break
        excess = (w[over] - cap).sum()
        w[over] = cap
        room = (w < cap) & (w > 0)
        if not room.any():
            break
        w[room] += excess * (w[room] / w[room].sum())
    return w

def _cap_sector(w, sector_map, sector_cap, n_iter=10):
    w = w.copy()
    for _ in range(n_iter):
        sec = w.groupby(sector_map).sum()
        over = sec[sec > sector_cap + 1e-12]
        if over.empty:
            break
        for s in over.index:
            names = [t for t in w.index if sector_map.get(t) == s and w[t] > 0]
            scale = sector_cap / sec[s]
            freed = w[names].sum() * (1 - scale)
            w[names] *= scale
            others = [t for t in w.index if sector_map.get(t) != s and w[t] > 0]
            if others:
                w[others] += freed * (w[others] / w[others].sum())
    return w

def backtest_long_only(score_panel, fwd_ret, sector_map=None, top_n=12,
                       stock_cap=0.15, sector_cap=0.35, weighting="score"):
    """
    월별 long-only. 각 월 점수 상위 top_n 선택 → 가중 → 종목/섹터 cap → 다음 달 수익 실현.
    score_panel, fwd_ret : DataFrame(month×ticker) (fwd_ret[t] = t→t+1 실현수익).
    반환: dict(ret=월수익Series, turnover=Series, weights=DataFrame)
    """
    idx = score_panel.index.intersection(fwd_ret.index)
    rets, turns, wprev, wrows = [], [], None, {}
    for t in idx:
        s = score_panel.loc[t].dropna()
        if s.empty:
            continue
        sel = s.nlargest(min(top_n, len(s)))
        if weighting == "equal":
            w = pd.Series(1.0/len(sel), index=sel.index)
        else:                                   # score-proportional (음수 방지 shift)
            v = sel - sel.min() + 1e-6
            w = v / v.sum()
        w = _cap_stock(w, stock_cap)
        if sector_map is not None:
            w = _cap_sector(w, sector_map, sector_cap)
        w = w / w.sum()
        wfull = pd.Series(0.0, index=score_panel.columns)
        wfull[w.index] = w.values
        rets.append(float((wfull * fwd_ret.loc[t].reindex(wfull.index).fillna(0)).sum()))
        turns.append(0.5*float((wfull - (wprev if wprev is not None else 0)).abs().sum()))
        wrows[t] = wfull; wprev = wfull
    return {"ret": pd.Series(rets, index=list(wrows.keys())),
            "turnover": pd.Series(turns, index=list(wrows.keys())),
            "weights": pd.DataFrame(wrows).T}

def metrics(ret, ppy=12):
    r = ret.dropna().values
    if len(r) < 2:
        return {}
    cagr = float(np.prod(1+r)**(ppy/len(r)) - 1)
    sharpe = float(r.mean()/r.std(ddof=1)*np.sqrt(ppy))
    eq = np.cumprod(1+r); mdd = float((eq/np.maximum.accumulate(eq) - 1).min())
    return {"CAGR": cagr, "Sharpe": sharpe, "MDD": mdd, "vol_ann": float(r.std(ddof=1)*np.sqrt(ppy)), "n": len(r)}

# ============ 4) 단일 인터페이스 ============
def run_backtest(spec):
    """
    spec = {score_panel, fwd_ret, sector_map, top_n, stock_cap, sector_cap, weighting}
    반환: (metrics_dict, monthly_ret_series, turnover_series)
    ②(leave-one-out)·build_trial_matrix 가 이 함수를 호출.
    """
    bt = backtest_long_only(spec["score_panel"], spec["fwd_ret"],
                            spec.get("sector_map"), spec.get("top_n", 12),
                            spec.get("stock_cap", 0.15), spec.get("sector_cap", 0.35),
                            spec.get("weighting", "score"))
    return metrics(bt["ret"]), bt["ret"], bt["turnover"]

# ============ 5) trial 행렬 (③ 입력) ============
def build_trial_matrix(specs):
    """
    specs: list[dict] (각 trial). 반환: (returns_df T×N, ann_sharpes list, metrics_list)
    이 행렬을 stats_v1.deflated_sharpe_ratio / pbo_cscv / reality_check_spa 에 투입.
    """
    cols, sr, ms = {}, [], []
    for i, sp in enumerate(specs):
        m, r, _ = run_backtest(sp)
        cols[sp.get("name", f"trial{i}")] = r
        sr.append(m.get("Sharpe", np.nan)/np.sqrt(12))   # 월 Sharpe
        ms.append(m)
    return pd.DataFrame(cols).dropna(how="all"), sr, ms

# ============ self-test (합성) ============
if __name__ == "__main__":
    rng = np.random.default_rng(11)
    T, K = 60, 18
    idx = pd.date_range("2019-01-31", periods=T, freq="ME")
    cols = UNIVERSE_18
    sectors = (["반도체"]*4 + ["바이오"] + ["IT"]*2 + ["방산"]*2 + ["금융"] +
               ["소비재"] + ["2차전지"] + ["화장품"] + ["지주"] + ["식품"] + ["반도체장비"] + ["에너지"] + ["증권"])
    sector_map = dict(zip(cols, sectors))

    # 합성 팩터 패널 + (Echo가 진짜 약한 예측력)
    fwd = pd.DataFrame(rng.normal(0.02, 0.09, (T, K)), index=idx, columns=cols)
    echo = pd.DataFrame(rng.normal(0, 1, (T, K)), index=idx, columns=cols)
    fwd += 0.015 * echo.shift(0)                       # Echo가 다음달 수익과 양의 관계
    panels = {"Echo": echo, "F_korean": pd.DataFrame(rng.normal(0,1,(T,K)),index=idx,columns=cols),
              "BAB": pd.DataFrame(rng.normal(0,1,(T,K)),index=idx,columns=cols)}
    weights = {"Echo":1.0, "F_korean":1.0, "BAB":1.0}
    fwd_ret = fwd  # 데모: 점수 시점 t의 다음달 수익 = fwd[t]

    base_scores = build_scores(panels, weights)
    m_base, *_ = run_backtest({"score_panel":base_scores,"fwd_ret":fwd_ret,"sector_map":sector_map})
    print("=== baseline 백테스트 ===")
    print({k:round(v,3) for k,v in m_base.items()})

    # regime 오버레이 적용 (합성 regime)
    reg = pd.Series((rng.random(T) > 0.4).astype(int), index=idx)
    ov_scores = build_scores(panels, weights, regime=reg, echo_w=(1.5,1.0), bab_w=(0.0,1.0))
    m_ov, *_ = run_backtest({"score_panel":ov_scores,"fwd_ret":fwd_ret,"sector_map":sector_map})
    print("=== regime 오버레이 ===")
    print({k:round(v,3) for k,v in m_ov.items()})

    # trial 행렬 → stats 연결(있으면)
    specs = [{"name":f"t{i}","score_panel":build_scores(panels,{"Echo":rng.uniform(0.5,1.5),
              "F_korean":1.0,"BAB":rng.uniform(0,1)}),"fwd_ret":fwd_ret,"sector_map":sector_map}
             for i in range(12)]
    R, sr, _ = build_trial_matrix(specs)
    print(f"\n=== trial 행렬 {R.shape} → stats_v1 연결 ===")
    try:
        import stats_v1 as S
        dsr,_,_ = S.deflated_sharpe_ratio(R.iloc[:,int(np.argmax(sr))], n_trials=len(specs), sr_trials=sr)
        pbo,_ = S.pbo_cscv(R.values, S=8)
        print(f"best trial DSR={dsr:.3f} | PBO={pbo:.3f}")
    except Exception as e:
        print(f"(stats_v1 미연결: {e}) — 행렬만 생성 확인")
    print("\n[OK] jq_adapter self-test 완료")
