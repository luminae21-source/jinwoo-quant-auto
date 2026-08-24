# -*- coding: utf-8 -*-
"""
jq_volmanaged_backtest.py — 후보 B: 변동성 관리 **시장 익스포저** 백테(골격).
근거 스펙: 진우퀀트_변동성관리_사전등록_초안_2026-07-11.md

방식(Moreira-Muir 2017, 시장 한정): KOSPI 익스포저 w_t = clip(σ_target/σ̂_{t-1}, 0, W_max).
  σ̂ = 시장월수익 트레일링 실현변동성(연율). 저변동→비중↑, 고변동→비중↓. 나머지는 무위험(RF).
반론 반영(Cederburg2020·Barroso-Detzel2021): 개별팩터는 OOS/비용 후 소멸, **시장은 예외** → 시장에만 적용.
수익 우선 게이트(b): CAGR이 buy&hold−1%p보다 낮으면 기각(리스크만 줄고 수익 깎이면 탈락).

무수정: production·L1·theme_heat·매도규칙서 불변. 별도 오버레이 연구. 성과수치=골격·미검증.
데이터: korea_factors_monthly.csv(MKT=시장초과·RF). 시장총수익 = MKT+RF.
실행: 폴더에서  py jq_volmanaged_backtest.py --selftest | --run | --judge
"""
import os, sys, json, argparse, warnings, importlib.util
import numpy as np, pandas as pd
warnings.simplefilter("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
def _load(f, m):
    s = importlib.util.spec_from_file_location(m, os.path.join(HERE, f))
    x = importlib.util.module_from_spec(s); s.loader.exec_module(x); return x
S1 = _load("stats_v1.py", "stats_v1")

CFG = dict(
    SCALING      = "VAR",  # "VAR"=MM17 1/σ²(분산역수) | "VOL"=Barroso-SantaClara 1/σ(상수변동성)
    VOL_WINDOW   = 6,      # σ̂ 트레일링(개월). MM은 직전1개월 일간 실현분산(장기 일간부재→월간근사)
    W_MAX        = 3.0,    # MM원형=무조건부 변동성 매칭(레버리지 허용). 소매 무레버리지판=1.0 별도보고
    COST_ONEWAY  = 0.0030, # 편도 비용(가중 변화분)
)

def load_market():
    """시장총수익 r=MKT+RF, 무위험 RF (월간). korea_factors_monthly.csv."""
    f = pd.read_csv(os.path.join(HERE, "korea_factors_monthly.csv"), parse_dates=["date"]).set_index("date")
    rf = f["RF"].fillna(0.0); r = (f["MKT"].fillna(0.0) + rf)
    return r, rf

def load_daily_vol(window=21):
    """MM 원형: KS11 일간 21일 실현변동성(연율)→월말값. kospi_index_daily.csv 있을 때만."""
    p = os.path.join(HERE, "kospi_index_daily.csv")
    if not os.path.exists(p): return None
    d = pd.read_csv(p, parse_dates=["Date"]).set_index("Date")["Close"]
    rv = d.pct_change(fill_method=None).rolling(window).std() * np.sqrt(252)
    return rv.resample("ME").last()

def vol_managed(r, rf, cfg=None, sig_ann=None):
    """MM17: 초과수익을 직전월 실현분산 역수로 스케일. c=무조건부 변동성이 buy&hold와 같게 정규화.
    sig_ann 주면 그 월별 실현변동성(연율) 사용(일간 기반), 없으면 월간수익 근사. 반환: 전략(net)·벤치·w."""
    c = cfg or CFG; W = c["VOL_WINDOW"]
    excess = r - rf
    if sig_ann is not None:
        s = sig_ann.reindex(r.index).shift(1)              # 월말 일간실현변동성(t-1)→t 가중(look-ahead 0)
        raw = (1.0/(s**2)) if c["SCALING"] == "VAR" else (1.0/s)
    else:
        var = excess.rolling(W).var().shift(1)             # 직전 실현분산(월간 근사)
        raw = (1.0/var) if c["SCALING"] == "VAR" else (1.0/np.sqrt(var))
    raw = raw.reindex(r.index)
    idx = raw.replace([np.inf, -np.inf], np.nan).dropna().index
    raw = raw.reindex(idx); ex = excess.reindex(idx); rff = rf.reindex(idx)
    # c 정규화: 관리 초과수익의 무조건부 표준편차 = buy&hold 초과수익과 동일(MM 방식)
    k = ex.std() / (raw*ex).std() if (raw*ex).std() > 0 else 0.0
    w = (raw*k)
    if c["W_MAX"] is not None: w = w.clip(0, c["W_MAX"])    # 레버리지 캡(소매판 1.0)
    strat = w*ex + rff                                      # 시장 w + 현금(1-w)
    turn = w.diff().abs().fillna(w.abs())
    strat = strat - turn*c["COST_ONEWAY"]                   # 비용
    bench = (ex + rff)                                      # buy&hold 시장
    return strat.dropna(), bench.reindex(strat.dropna().index), w

def perf(x):
    x = x.dropna(); n = len(x)
    cagr = float((1+x).prod()**(12/max(n,1)) - 1)
    shp = float(x.mean()/x.std()*np.sqrt(12)) if x.std()>0 else np.nan
    cum = (1+x).cumprod(); mdd = float((cum/cum.cummax()-1).min())
    return dict(CAGR=cagr, Sharpe=shp, MDD=mdd, n=n)

def _grid_matrix(r, rf, sig_ann=None):
    import itertools as it
    cols = {}
    for sc, W, wm in it.product(["VAR","VOL"], [6,12], [1.0,3.0]):
        s,_,_ = vol_managed(r, rf, dict(SCALING=sc, VOL_WINDOW=W, W_MAX=wm, COST_ONEWAY=CFG["COST_ONEWAY"]), sig_ann=sig_ann)
        cols[(sc,W,wm)] = s
    return pd.DataFrame(cols).dropna()

def judge():
    r, rf = load_market()
    sig = load_daily_vol()                                              # 일간 실현변동성(있으면 MM 원형)
    vol_src = "daily(KS11 21d)" if sig is not None else "monthly-approx"
    strat, bench, w = vol_managed(r, rf, sig_ann=sig)
    ps, pb = perf(strat), perf(bench)
    # 합격선
    a = (ps["Sharpe"] > pb["Sharpe"])                                   # 위험조정 우위
    b = (ps["CAGR"] >= pb["CAGR"] - 0.01)                               # 수익 비열위(핵심)
    calmar = lambda p: (p["CAGR"]/abs(p["MDD"])) if p["MDD"]<0 else np.inf
    cc = (calmar(ps) > calmar(pb))                                      # 복리 개선(CAGR/MDD)
    # 비용 1.5x 강건
    s15,_,_ = vol_managed(r, rf, dict(**{**CFG, "COST_ONEWAY":CFG["COST_ONEWAY"]*1.5}), sig_ann=sig)
    p15 = perf(s15); d = (p15["Sharpe"]>pb["Sharpe"]) and (p15["CAGR"]>=pb["CAGR"]-0.01)
    # OOS/강건: 격자 DSR/PBO/White(벤치=buy&hold)
    mat = _grid_matrix(r, rf, sig_ann=sig); common = mat.index.intersection(bench.index)
    e = None
    try:
        srt = [float(mat[cc2].mean()/mat[cc2].std()) for cc2 in mat.columns if mat[cc2].std()>0]
        dsr,_,_ = S1.deflated_sharpe_ratio(strat.reindex(common).values, n_trials=max(len(srt),2), sr_trials=srt)
        pbo,_ = S1.pbo_cscv(mat.reindex(common).values, S=min(16,max(4,(len(common)//2)*2)))
        rc = S1.reality_check_spa(mat.reindex(common).values, benchmark=bench.reindex(common).values)
        e = (dsr>0.95) and (pbo<0.5) and (rc["p_white_rc"]<0.05)
        rob = dict(DSR=float(dsr), PBO=float(pbo), p_white_rc=rc["p_white_rc"], spa_reliable=rc["spa_reliable"])
    except Exception as ex:
        rob = {"err": str(ex)}; e = False
    # 소매 무레버리지판(W_max=1.0) 별도 보고 — 집행 가능하나 방어적(레버리지 없이 축소만)
    sr_ret, _, w_ret = vol_managed(r, rf, dict(**{**CFG, "W_MAX":1.0}), sig_ann=sig)
    p_ret = perf(sr_ret)
    verdict = "채택후보" if (a and b and cc and d and e) else "기각/연기"
    out = dict(vol_source=vol_src, primary_MM=ps, benchmark=pb, retail_noLev_Wmax1=p_ret, cost15_ok=bool(d), **rob,
               a_sharpe=bool(a), b_cagr_ok=bool(b), c_calmar=bool(cc), e_robust=bool(e),
               VERDICT=verdict, note="primary=MM원형(1/σ²·무조건부변동성정규화·레버리지허용). retail=무레버리지 집행판. 수익우선 게이트 b. 절대치 신뢰금지·집행 전 Track.")
    return out

def selftest():
    r, rf = load_market()
    sig = load_daily_vol()
    print(f"[selftest] 시장 월수익 {len(r)}개월 ({r.index.min().date()}~{r.index.max().date()})")
    print(f"  · 변동성 소스: {'daily(KS11 21d)' if sig is not None else 'monthly-approx (kospi_index_daily.csv 없음)'}")
    strat, bench, w = vol_managed(r, rf, sig_ann=sig)
    print(f"  · 익스포저 w 범위 {w.min():.2f}~{w.max():.2f} 평균 {w.mean():.2f}")
    print(f"  · 전략 {perf(strat)}")
    print(f"  · 벤치(buy&hold) {perf(bench)}")
    print("[selftest] OK — 배선 정상. 판정은 --judge.")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--judge", action="store_true")
    a = ap.parse_args()
    if a.selftest: selftest()
    elif a.run:
        r, rf = load_market(); s, b, w = vol_managed(r, rf, sig_ann=load_daily_vol())
        print(json.dumps({"strat":perf(s), "bench":perf(b)}, ensure_ascii=False, indent=2))
    elif a.judge:
        print(json.dumps(judge(), ensure_ascii=False, indent=2))
        print("⚠️ 골격: σ̂=월간 실현변동성(일간·VKOSPI 정밀화 TODO). 절대치 신뢰 금지.")
    else:
        print("사용: --selftest | --run | --judge")
