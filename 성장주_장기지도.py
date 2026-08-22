# -*- coding: utf-8 -*-
"""성장주 장기 지도 — 테마·산업군별 2·3·5·7년 보유 수익 (기술통계·지도)
형 지시 2026-08-22: "이 작업 시작. 시간이 걸려도 모든 자료 가지고 좋은 종목으로 하면 돼"
⚠️ §10-A: 섹터 맵은 현재 스냅숏 → look-ahead + 생존편향. 지도이지 전략 증명이 아님.
방법: back_adjust(close-only, era_limit 2015-06-15 이전 ±15% 그 후 ±30%, +3%p),
      월말 전수 앵커, N년(24/36/60/84개월) shift 수익, 종목별 승률/중앙/최악/연환산.
"""
import pandas as pd, numpy as np, json, sys

JQ = "/home/claude/jq"
UP = "/mnt/user-data/uploads/진우퀀트"
ERA = pd.Timestamp("2015-06-15")

def load_market(path):
    df = pd.read_csv(path, encoding="utf-8-sig", dtype={"code": str},
                     usecols=["date", "code", "close"])
    df["date"] = pd.to_datetime(df["date"])
    df = df[df["close"] > 0]
    return df

def back_adjust_monthly(g):
    """일봉 close → 백조정 → 월말 리샘플. g: date-sorted close Series (date index)."""
    c = g.values.astype(float)
    d = g.index
    ret = np.ones(len(c))
    ret[1:] = c[1:] / c[:-1]
    # 액면분할/병합 등 비정상 점프 = 가격 단절로 간주해 중립화
    lim_hi = np.where(d[1:] < ERA, 1.15 + 0.03, 1.30 + 0.03)
    lim_lo = np.where(d[1:] < ERA, 1/1.15 - 0.03, 1/1.30 - 0.03)
    bad = (ret[1:] > lim_hi) | (ret[1:] < lim_lo)
    ret[1:][bad] = 1.0
    adj = np.cumprod(ret)
    s = pd.Series(adj, index=d)
    return s.resample("ME").last().dropna()

def analyze(df, market):
    out = []
    for code, g in df.groupby("code"):
        g = g.sort_values("date").set_index("date")["close"]
        g = g[~g.index.duplicated(keep="last")]
        if len(g) < 60:  # 최소한의 일봉
            continue
        m = back_adjust_monthly(g)
        if len(m) < 60:  # 5년 미만 상장은 제외 (형: 데이터 ≥60개월... 2·3년은 되는데 통일 기준)
            continue
        row = {"code": code, "market": market, "months": len(m),
               "first": str(m.index[0].date()), "last": str(m.index[-1].date())}
        total = m.iloc[-1] / m.iloc[0]
        yrs = (m.index[-1] - m.index[0]).days / 365.25
        row["cagr"] = total ** (1/yrs) - 1 if yrs > 1 else np.nan
        for ny, lab in [(2, "y2"), (3, "y3"), (5, "y5"), (7, "y7")]:
            k = ny * 12
            if len(m) <= k:
                row[f"{lab}_n"] = 0
                continue
            r = (m.shift(-k) / m).dropna() - 1.0
            row[f"{lab}_n"] = len(r)
            row[f"{lab}_win"] = float((r > 0).mean())
            row[f"{lab}_med"] = float(r.median())
            row[f"{lab}_worst"] = float(r.min())
        out.append(row)
    return out

def main():
    rows = []
    for market, path in [("KOSPI", f"{JQ}/종목일봉_30년_KOSPI.csv"),
                         ("KOSDAQ", f"{JQ}/종목일봉_30년_KOSDAQ.csv")]:
        print(f"[load] {market}...", flush=True)
        df = load_market(path)
        print(f"  rows={len(df):,} codes={df['code'].nunique():,}", flush=True)
        rows += analyze(df, market)
        del df
    res = pd.DataFrame(rows)
    # 섹터 결합 (현재 스냅숏 — 생존편향 고지)
    ls = pd.read_csv(f"{UP}/liquidity_sector.csv", encoding="utf-8-sig", dtype={"code": str})
    ki = pd.read_csv(f"{UP}/kosdaq_industry.csv", encoding="utf-8-sig", dtype={"code": str})
    nm = pd.read_csv(f"{UP}/종목명_맵.csv", encoding="utf-8-sig", dtype={"code": str})
    sec = pd.concat([ls[["code", "name", "sector"]], ki[["code", "name", "sector"]]]) \
            .drop_duplicates("code", keep="first")
    res = res.merge(sec, on="code", how="left")
    res = res.merge(nm.rename(columns={"name": "name2"}), on="code", how="left")
    res["name"] = res["name"].fillna(res["name2"]); res.drop(columns=["name2"], inplace=True)
    # 최근 시총 (규모 필터용)
    mc = pd.read_csv(f"{UP}/종목시총_30년.csv", encoding="utf-8-sig", dtype={"code": str})
    mc["date"] = pd.to_datetime(mc["date"])
    mc_last = mc.sort_values("date").groupby("code").tail(1)[["code", "mcap"]]
    res = res.merge(mc_last, on="code", how="left")
    res.to_csv(f"{JQ}/성장주_전수결과.csv", index=False, encoding="utf-8-sig")
    print(f"[done] {len(res)} stocks -> 성장주_전수결과.csv", flush=True)

if __name__ == "__main__":
    main()
