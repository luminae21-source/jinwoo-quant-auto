# -*- coding: utf-8 -*-
"""미국주식 장기 지도 — 대표 성장주 2·3·5·7년 보유 수익 (기술통계·지도) 2026-08-22
한국판 성장주_장기지도.py 의 analyze() 골격을 그대로 이식. 방법 통일이 최우선.
  - 월말 전수 앵커 (resample("ME").last())
  - N년(24/36/60/84개월) shift 수익 → 종목별 승률/중앙/최악/CAGR
  - 최소 60개월
⚠️ 지도이지 전략 증명 아님. 티커 8종은 현재 시점 선택 = 전부 생존자(생존편향).

가격 기준 3가지 변형을 모두 산출한다 (리포트에서 비교 기준을 명시하기 위해):
  A  adj_full   : Yahoo adjclose(배당+분할 조정), 전체 이력        ← 미국판 표준(주 결과)
  B  adj_1996   : 같은 adjclose, 1996-01 이후만 (한국판 30년 창과 동일 기간)
  C  ko_1996    : close-only + 한국판 back_adjust(점프 중립화) 1996-01 이후
                  = 한국판과 **완전히 같은 방법** (배당 미포함). 공정 비교용.
"""
import os, glob
import pandas as pd, numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "미국_일봉")
ERA = pd.Timestamp("2015-06-15")           # 한국판 era_limit 그대로
KO_START = pd.Timestamp("1996-01-01")      # 한국판 데이터 시작
TICKERS = ["AAPL", "MSFT", "NVDA", "GOOGL", "AMZN", "META", "TSLA", "AVGO",
           "^GSPC", "^IXIC", "SPY", "QQQ"]
NAMES = {"AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "NVIDIA", "GOOGL": "Alphabet",
         "AMZN": "Amazon", "META": "Meta", "TSLA": "Tesla", "AVGO": "Broadcom",
         "^GSPC": "S&P500 지수", "^IXIC": "나스닥종합 지수", "SPY": "SPY ETF", "QQQ": "QQQ ETF"}

def load(t):
    p = os.path.join(DATA, t.replace("^", "IDX_") + ".csv")
    df = pd.read_csv(p)
    df["date"] = pd.to_datetime(df["date"])
    df = df[(df["close"] > 0) & (df["adjclose"] > 0)].sort_values("date")
    df = df[~df["date"].duplicated(keep="last")].set_index("date")
    return df

# ---- 한국판 그대로 (성장주_장기지도.py) ----
def back_adjust_monthly(g):
    c = g.values.astype(float); d = g.index
    ret = np.ones(len(c)); ret[1:] = c[1:] / c[:-1]
    lim_hi = np.where(d[1:] < ERA, 1.15 + 0.03, 1.30 + 0.03)
    lim_lo = np.where(d[1:] < ERA, 1/1.15 - 0.03, 1/1.30 - 0.03)
    bad = (ret[1:] > lim_hi) | (ret[1:] < lim_lo)
    ret[1:][bad] = 1.0
    adj = np.cumprod(ret)
    return pd.Series(adj, index=d).resample("ME").last().dropna()

def monthly_adj(g):
    """adjusted close 는 이미 연속 → 백조정·점프중립화 없이 월말 리샘플만."""
    return g.astype(float).resample("ME").last().dropna()

def stats(m, code, variant):
    if len(m) < 60:
        return None
    row = {"code": code, "name": NAMES.get(code, code), "variant": variant,
           "months": len(m), "first": str(m.index[0].date()), "last": str(m.index[-1].date())}
    total = m.iloc[-1] / m.iloc[0]
    yrs = (m.index[-1] - m.index[0]).days / 365.25
    row["total_x"] = float(total)
    row["cagr"] = total ** (1/yrs) - 1 if yrs > 1 else np.nan
    for ny, lab in [(2, "y2"), (3, "y3"), (5, "y5"), (7, "y7")]:
        k = ny * 12
        if len(m) <= k:
            row[f"{lab}_n"] = 0; continue
        r = (m.shift(-k) / m).dropna() - 1.0
        row[f"{lab}_n"] = len(r)
        row[f"{lab}_win"] = float((r > 0).mean())
        row[f"{lab}_med"] = float(r.median())
        row[f"{lab}_worst"] = float(r.min())
        row[f"{lab}_p10"] = float(r.quantile(0.10))
    return row

def main():
    rows, series = [], {}
    for t in TICKERS:
        df = load(t)
        print(f"[load] {t}: {len(df):,} days {df.index[0].date()}~{df.index[-1].date()}", flush=True)
        mA = monthly_adj(df["adjclose"])
        mB = monthly_adj(df.loc[df.index >= KO_START, "adjclose"])
        mC = back_adjust_monthly(df.loc[df.index >= KO_START, "close"])
        for v, m in [("A_adj_full", mA), ("B_adj_1996", mB), ("C_ko_1996", mC)]:
            r = stats(m, t, v)
            if r: rows.append(r)
        series[t] = mA
    res = pd.DataFrame(rows)
    res.to_csv(os.path.join(HERE, "미국주식_전수결과.csv"), index=False, encoding="utf-8-sig")
    # 월말 조정종가 시계열(A)도 보관 — 본체가 한국 시계열과 결합할 때 쓰도록
    pd.DataFrame(series).to_csv(os.path.join(HERE, "미국주식_월말조정종가.csv"), encoding="utf-8-sig")
    print(f"[done] {len(res)} rows -> 미국주식_전수결과.csv", flush=True)
    pd.set_option("display.width", 200)
    cols = ["code", "variant", "months", "cagr", "y2_win", "y3_win", "y5_win", "y7_win", "y7_med", "y7_worst"]
    print(res[cols].to_string(index=False))

if __name__ == "__main__":
    main()
