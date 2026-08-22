# -*- coding: utf-8 -*-
"""엔진 05 — 장기 성장주 코어 · PIT 검정 (사전등록 2026-08-22)
규칙(사전 고정): 매년 12월 말, 그 시점까지의 데이터만으로
  자격 (a)상장≥7년 (b)시총 상위 SIZE_CUT (c)직전60일 평균거래대금≥5억
  점수 과거 7년 롤링 보유수익의 승률/중앙수익 (월말 앵커·백조정 close-only)
  선정 승률≥WIN_CUT 중 중앙수익 상위 N종, 동일가중, 1년 보유, 편입유지 종목 무매매
  비용 왕복 0.6%
격자 8조합(SIZE_CUT 300/500 × WIN_CUT .80/.90 × N 15/30)
  → 훈련 1996-2015에서 1조합 선택 → 검증 2016-2026 1회
벤치 3종: KOSPI 보유 / 같은 자격풀 EW / (참고) 사후 44종
실행: python3 엔진05_검정.py --self-test | --train | --verify --pick "500|0.90|30"
"""
import argparse, json, sys
import numpy as np, pandas as pd

UP = "/mnt/user-data/uploads/진우퀀트"
JQ = "/home/claude/jq"
ERA = pd.Timestamp("2015-06-15")
COST = 0.006            # 왕복
ADTV_MIN = 5e8          # 5억
TRAIN = (1996, 2015)    # 형성 12월 말 앵커 연도 범위
VERIFY = (2016, 2025)   # 마지막 앵커 2025-12 → 2026 보유분은 부분연도라 제외
GRID = [(sz, wc, n) for sz in (300, 500) for wc in (0.80, 0.90) for n in (15, 30)]


def back_adjust(close: pd.Series) -> pd.Series:
    """close-only 백조정: 비정상 점프(액면분할 등)를 1.0으로 중립화."""
    c = close.values.astype(float); d = close.index
    ret = np.ones(len(c)); ret[1:] = c[1:] / c[:-1]
    hi = np.where(d[1:] < ERA, 1.18, 1.33)
    lo = np.where(d[1:] < ERA, 1/1.18, 1/1.33)
    bad = (ret[1:] > hi) | (ret[1:] < lo)
    ret[1:][bad] = 1.0
    return pd.Series(np.cumprod(ret), index=d)


def load_panel():
    """양시장 일봉 → 종목별 (월말 백조정가, 월말 거래대금 60일평균) 패널."""
    frames = []
    for mk in ("KOSPI", "KOSDAQ"):
        df = pd.read_csv(f"{UP}/종목일봉_30년_{mk}.csv", encoding="utf-8-sig",
                         dtype={"code": str}, usecols=["date","code","close","volume"])
        df["date"] = pd.to_datetime(df["date"])
        df = df[df["close"] > 0]
        frames.append(df)
    df = pd.concat(frames, ignore_index=True)
    px, adtv = {}, {}
    for code, g in df.groupby("code"):
        g = g.sort_values("date").drop_duplicates("date", keep="last").set_index("date")
        if len(g) < 260: continue
        adj = back_adjust(g["close"])
        px[code] = adj.resample("ME").last()
        turn = (g["close"] * g["volume"]).rolling(60, min_periods=20).mean()
        adtv[code] = turn.resample("ME").last()
    P = pd.DataFrame(px).sort_index()
    A = pd.DataFrame(adtv).reindex_like(P)
    return P, A


def load_mcap(index):
    m = pd.read_csv(f"{UP}/종목시총_30년.csv", encoding="utf-8-sig", dtype={"code": str})
    m["date"] = pd.to_datetime(m["date"])
    M = m.pivot_table(index="date", columns="code", values="mcap", aggfunc="last")
    M = M.resample("ME").last()
    return M.reindex(index=index).ffill(limit=3)


def score_at(P, t, lookback_years=7):
    """t(월말) 시점까지의 데이터만으로 각 종목의 7년 보유 승률·중앙수익."""
    k = lookback_years * 12
    hist = P.loc[:t]
    if len(hist) < k + 13: return None
    fwd = hist.shift(-k) / hist - 1.0          # 각 앵커의 7년 후 수익 (t 이전 것만 관측 가능)
    fwd = fwd.loc[:hist.index[-k-1]]           # 미래를 보지 않도록 절단
    win = (fwd > 0).mean()
    med = fwd.median()
    n = fwd.notna().sum()
    return pd.DataFrame({"win": win, "med": med, "n": n})


def eligible(P, A, M, t, size_cut):
    """t 시점 자격 종목."""
    listed = P.loc[:t].notna().sum() >= 84            # 상장 ≥ 7년(84개월)
    liq = A.loc[t] >= ADTV_MIN
    mc = M.loc[t].dropna()
    big = mc.nlargest(size_cut).index if len(mc) else []
    ok = listed & liq
    return [c for c in P.columns if ok.get(c, False) and c in set(big)]


def run(P, A, M, y0, y1, size_cut, win_cut, N):
    """연 1회 리밸런싱 백테스트. 반환: (전략 연수익 리스트, 풀EW 연수익 리스트, 선정기록)"""
    strat, poolew, picks_log, prev = [], [], [], set()
    for y in range(y0, y1 + 1):
        anchors = P.index[(P.index.year == y) & (P.index.month == 12)]
        if len(anchors) == 0: continue
        t = anchors[0]
        nxt = P.index[(P.index.year == y + 1) & (P.index.month == 12)]
        if len(nxt) == 0: continue
        t1 = nxt[0]
        sc = score_at(P, t)
        if sc is None: continue
        elig = eligible(P, A, M, t, size_cut)
        sc = sc.loc[[c for c in elig if c in sc.index]].dropna(subset=["win", "med"])
        sc = sc[sc["n"] >= 24]
        cand = sc[sc["win"] >= win_cut].sort_values("med", ascending=False)
        picks = list(cand.index[:N])
        if len(picks) < max(5, N // 3):        # 후보 부족 연도는 건너뜀(기록)
            picks_log.append({"year": y, "picks": len(picks), "skipped": True}); continue
        r = (P.loc[t1, picks] / P.loc[t, picks] - 1.0).dropna()
        if len(r) == 0: continue
        turn = len(set(picks) - prev) / len(picks)          # 신규 편입 비율만 비용
        strat.append(float(r.mean() - COST * turn))
        prev = set(picks)
        rp = (P.loc[t1, elig] / P.loc[t, elig] - 1.0).dropna()
        poolew.append(float(rp.mean()) if len(rp) else np.nan)
        picks_log.append({"year": y, "picks": len(picks), "ret": strat[-1],
                          "pool_ew": poolew[-1], "turnover": turn})
    return strat, poolew, picks_log


def kospi_annual(y0, y1):
    k = pd.read_csv(f"{UP}/kospi_index_daily.csv", encoding="utf-8-sig")
    k.columns = [c.strip().lower() for c in k.columns]
    k["date"] = pd.to_datetime(k["date"]); k = k.set_index("date")["close"]
    m = k.resample("ME").last()
    out = []
    for y in range(y0, y1 + 1):
        a = m[(m.index.year == y) & (m.index.month == 12)]
        b = m[(m.index.year == y + 1) & (m.index.month == 12)]
        if len(a) and len(b): out.append(float(b.iloc[0] / a.iloc[0] - 1.0))
    return out


def cagr(rs):
    rs = [r for r in rs if r == r]
    if not rs: return np.nan
    return float(np.prod([1 + r for r in rs]) ** (1 / len(rs)) - 1)


def mdd_from_annual(rs):
    eq = np.cumprod([1 + r for r in rs if r == r])
    peak = np.maximum.accumulate(eq)
    return float((eq / peak - 1).min()) if len(eq) else np.nan


def self_test():
    idx = pd.date_range("2000-01-31", periods=200, freq="ME")
    s = pd.Series(np.linspace(100, 400, 200), index=idx)
    adj = back_adjust(s); assert abs(adj.iloc[-1] / adj.iloc[0] - 4.0) < 0.02
    s2 = s.copy(); s2.iloc[100:] = s2.iloc[100:] / 5      # 5:1 분할
    adj2 = back_adjust(s2); assert abs(adj2.iloc[-1] / adj2.iloc[0] - 4.0) < 0.05, adj2.iloc[-1]/adj2.iloc[0]
    P = pd.DataFrame({"A": s, "B": s * 0 + 100}, index=idx)
    sc = score_at(P, idx[-1]); assert sc.loc["A", "win"] == 1.0 and sc.loc["B", "win"] == 0.0
    assert abs(cagr([0.1, 0.1]) - 0.1) < 1e-9
    assert abs(mdd_from_annual([0.5, -0.5]) - (-0.5)) < 1e-9
    assert len(GRID) == 8
    print("self-test 6/6 통과")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--train", action="store_true")
    ap.add_argument("--verify", action="store_true")
    ap.add_argument("--pick", help='"500|0.90|30"')
    a = ap.parse_args()
    if a.self_test: return self_test()

    print("[load] 패널 구성 중...", flush=True)
    P, A = load_panel(); M = load_mcap(P.index)
    print(f"  월말 {len(P)}행 × 종목 {P.shape[1]:,}", flush=True)

    if a.train:
        rows = []
        for sz, wc, n in GRID:
            s, pe, log = run(P, A, M, *TRAIN, sz, wc, n)
            rows.append({"grid": f"{sz}|{wc}|{n}", "years": len(s), "cagr": cagr(s),
                         "pool_ew": cagr(pe), "mdd": mdd_from_annual(s)})
            print(f"  {rows[-1]['grid']:>12s} n={len(s):2d} CAGR {cagr(s)*100:+6.2f}% "
                  f"풀EW {cagr(pe)*100:+6.2f}% MDD {mdd_from_annual(s)*100:+6.1f}%", flush=True)
        kp = cagr(kospi_annual(*TRAIN))
        print(f"\n  [벤치] KOSPI 보유 CAGR {kp*100:+.2f}%")
        best = max(rows, key=lambda r: (r["cagr"] - max(r["pool_ew"], kp)))
        print(f"  → 훈련 선택: {best['grid']} (풀EW·KOSPI 중 높은 쪽 대비 초과 최대)")
        json.dump({"rows": rows, "kospi": kp, "pick": best["grid"]},
                  open(f"{JQ}/엔진05_훈련결과.json", "w"), ensure_ascii=False, indent=1)

    if a.verify:
        sz, wc, n = a.pick.split("|"); sz, wc, n = int(sz), float(wc), int(n)
        s, pe, log = run(P, A, M, *VERIFY, sz, wc, n)
        kp = kospi_annual(*VERIFY)
        res = {"grid": a.pick, "years": len(s), "strat_cagr": cagr(s),
               "pool_ew_cagr": cagr(pe), "kospi_cagr": cagr(kp),
               "strat_mdd": mdd_from_annual(s), "kospi_mdd": mdd_from_annual(kp),
               "d_vs_kospi_pp": (cagr(s) - cagr(kp)) * 100,
               "d_vs_poolew_pp": (cagr(s) - cagr(pe)) * 100,
               "d_mdd_pp": (mdd_from_annual(s) - mdd_from_annual(kp)) * 100, "log": log}
        g1 = res["d_vs_kospi_pp"] >= 2.0
        g2 = res["d_vs_poolew_pp"] >= 1.0
        g3 = res["d_mdd_pp"] >= -5.0
        res["gates"] = {"vs_kospi>=+2.0pp": g1, "vs_poolEW>=+1.0pp": g2, "mdd_ok": g3}
        res["pass"] = bool(g1 and g2 and g3)
        print(json.dumps({k: v for k, v in res.items() if k != "log"}, ensure_ascii=False, indent=1))
        json.dump(res, open(f"{JQ}/엔진05_검증결과.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
