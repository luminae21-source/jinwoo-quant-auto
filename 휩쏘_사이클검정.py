# -*- coding: utf-8 -*-
r"""휩쏘_사이클검정.py — 형 사이클 가설의 정밀 검정 (창 보정판)
   가설: 9~10월 저점 → 이듬해 4~5월 고점.
   보정: 6개월 창은 10월 진입이 5월에 못 닿는다 → 9~10월 진입분은 '이듬해 5월말까지' 창 확장.
   추가: (a) 지수 자체의 월별 계절성 30년  (b) '4월말 보유 청산' vs 카드청산 실현수익 비교.
"""
import os, sys, gc, importlib.util, warnings, json
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass


def _load_mod(fn, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fn))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def index_seasonality():
    p = os.path.join(HERE, "kospi_index_daily.csv")
    ix = pd.read_csv(p); ix.columns = [c.strip().lstrip("﻿") for c in ix.columns]
    ix["Date"] = pd.to_datetime(ix["Date"]); ix = ix.sort_values("Date")
    mo = ix.set_index("Date")["Close"].astype(float).resample("ME").last()
    r = mo.pct_change().dropna()
    tab = r.groupby(r.index.month).agg(["mean", "median", lambda x: (x > 0).mean()])
    tab.columns = ["평균", "중앙", "플러스율"]
    return (tab * 100).round(2)


def main():
    hz = _load_mod("휩쏘_역사검정.py", "hz")
    G = pd.read_csv(os.path.join(HERE, "휩쏘_고점_이벤트.csv"), dtype={"code": str})
    G["code"] = G["code"].str.zfill(6)
    SO = G[pd.to_datetime(G["출발일"]).dt.month.isin([9, 10])].copy()
    SO["출발일dt"] = pd.to_datetime(SO["출발일"])
    # 이듬해 5월말 한계일
    SO["한계일"] = SO["출발일dt"].apply(lambda d: pd.Timestamp(d.year + 1, 5, 31))
    # 4월 청산 시나리오 구간: 이듬해 4/1 ~ 5/31 마지막 종가 아님, '4월 마지막 거래일 종가'
    targets = SO.groupby("code")["출발일"].apply(list).to_dict()

    dt = {"code": str, "open": "float32", "high": "float32", "low": "float32",
          "close": "float32", "volume": "float32"}
    rows = []
    for mk in ("KOSPI", "KOSDAQ"):
        D = pd.read_csv(os.path.join(DATA, f"종목일봉_30년_{mk}.csv"), dtype=dt)
        D.columns = [x.strip().lstrip("﻿") for x in D.columns]
        D["code"] = D["code"].str.zfill(6)
        D = D[D["code"].isin(targets.keys())]
        for code, g in D.groupby("code", sort=False):
            want = targets.get(code)
            if not want: continue
            g = g.sort_values("date").reset_index(drop=True)
            g = g[~((g["open"] == 0) & (g["volume"] == 0))].reset_index(drop=True)
            if len(g) < 3: continue
            dts = g["date"].values.astype(str)
            o = g["open"].values.astype(float); h = g["high"].values.astype(float)
            l = g["low"].values.astype(float); c = g["close"].values.astype(float)
            v = g["volume"].values.astype(float)
            o, h, l, c, _ = hz.back_adjust(o, h, l, c, v, dts)
            pos = {d: i for i, d in enumerate(dts)}
            for d0 in want:
                t = pos.get(d0)
                if t is None or t + 1 >= len(c) or c[t] <= 0: continue
                yr = int(d0[:4]); lim = f"{yr+1}-05-31"; apr0, apr1 = f"{yr+1}-04-01", f"{yr+1}-04-31"
                # 확장 창: 진입 다음날 ~ 이듬해 5/31
                mask = (dts > d0) & (dts <= lim)
                idx = np.where(mask)[0]
                complete = bool(len(idx)) and dts[-1] >= lim
                peak = np.nan; pk_mon = np.nan; pk_days = np.nan
                aprexit = np.nan
                if len(idx):
                    hw = h[idx]
                    k = int(np.nanargmax(hw))
                    peak = hw[k] / c[t] - 1
                    pk_mon = int(dts[idx[k]][5:7]); pk_days = int(idx[k] - t)
                    # 4월 마지막 거래일 종가 청산
                    am = (dts >= apr0) & (dts <= f"{yr+1}-04-30")
                    ai = np.where(am)[0]
                    if len(ai): aprexit = c[ai[-1]] / c[t] - 1
                rows.append(dict(출발일=d0, code=code, 확장고점=round(peak * 100, 1) if np.isfinite(peak) else np.nan,
                                 확장고점월=pk_mon, 확장고점일수=pk_days,
                                 사월청산=round(aprexit * 100, 1) if np.isfinite(aprexit) else np.nan,
                                 확장완결=complete))
        del D; gc.collect()

    X = pd.DataFrame(rows)
    SO = SO.merge(X, on=["출발일", "code"], how="left")
    SO.to_csv(os.path.join(HERE, "휩쏘_사이클_910진입.csv"), index=False, encoding="utf-8-sig")

    C = SO[(SO["확장완결"] == True) & SO["확장고점"].notna()]
    res = {}
    res["n"] = int(len(C))
    res["확장고점_중앙"] = float(C["확장고점"].median()); res["확장고점_평균"] = float(C["확장고점"].mean())
    vc = C["확장고점월"].value_counts().sort_index()
    res["고점월분포"] = {int(k): int(v) for k, v in vc.items()}
    spring = C["확장고점월"].isin([3, 4, 5]).mean()
    res["봄고점비율"] = float(spring)
    fall = C["확장고점월"].isin([9, 10, 11, 12]).mean()
    res["연내고점비율"] = float(fall)
    a = C.dropna(subset=["사월청산"])
    res["사월청산_n"] = int(len(a))
    res["사월청산_중앙"] = float(a["사월청산"].median()); res["사월청산_평균"] = float(a["사월청산"].mean())
    res["사월청산_승률"] = float((a["사월청산"] > 0).mean())
    res["카드_평균"] = float(pd.to_numeric(C["ex_ret"], errors="coerce").mean() * 100)
    res["카드_승률"] = float((pd.to_numeric(C["ex_ret"], errors="coerce") > 0).mean())
    # 국면별
    for rg in ("실행", "주의", "관찰만"):
        s = a[a["국면"] == rg]
        if len(s):
            res[f"사월청산_{rg}"] = dict(n=int(len(s)), 중앙=float(s["사월청산"].median()),
                                     평균=float(s["사월청산"].mean()), 승률=float((s["사월청산"] > 0).mean()))
    seas = index_seasonality()
    res["지수계절성"] = {int(k): dict(평균=float(seas.loc[k, "평균"]), 플러스율=float(seas.loc[k, "플러스율"]))
                    for k in seas.index}
    with open(os.path.join(HERE, "사이클검정_요약.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)

    print(f"[9~10월 진입 · 이듬해 5월말 창] 완결 {len(C)}건")
    print(f"  확장 고점 중앙 {res['확장고점_중앙']:+.1f}% · 고점월 분포 {res['고점월분포']}")
    print(f"  봄(3~5월) 고점 비율 {spring*100:.0f}% · 연내(9~12월) 고점 비율 {fall*100:.0f}%")
    print(f"  4월말 보유청산: 중앙 {res['사월청산_중앙']:+.1f}% · 평균 {res['사월청산_평균']:+.1f}% · 승률 {res['사월청산_승률']*100:.0f}% (n={res['사월청산_n']})")
    print(f"  카드청산      : 평균 {res['카드_평균']:+.1f}% · 승률 {res['카드_승률']*100:.0f}%")
    print("\n[지수 월별 계절성 · 30년]")
    print(seas.to_string())


if __name__ == "__main__":
    main()
