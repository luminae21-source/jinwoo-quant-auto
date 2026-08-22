# -*- coding: utf-8 -*-
r"""휩쏘_고점분석.py — 역사원장 2,801건의 진입 후 3~6개월 단기 고점을 전량 계산하고,
   형의 사이클 가설(전월 9~10월 저점 → 이듬해 4~5월 고점)을 30년 데이터로 검정한다.

[산출]
  · 휩쏘_고점_이벤트.csv : 이벤트별 3M/6M 최고수익 · 고점 도달 거래일 · 고점 달력월
  · 콘솔 요약 + (별도 빌더로) HTML 리포트

[정의] 3M = 63거래일 · 6M = 126거래일. 고점 = 진입 다음날부터 창 안의 백조정 고가 최대.
⚠️ 고점수익은 '신이 최고점에 팔았을 때' — 도달 불가능한 상한. 청산 규칙 비교의 기준선으로만.
"""
import os, sys, gc, importlib.util, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

W3, W6 = 63, 126


def _load_mod(fn, name):
    p = os.path.join(HERE, fn)
    spec = importlib.util.spec_from_file_location(name, p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def main():
    hz = _load_mod("휩쏘_역사검정.py", "hz")     # back_adjust 재사용
    E = pd.concat([pd.read_csv(os.path.join(HERE, f"역사검정_이벤트_{m}.csv"), dtype={"code": str})
                   for m in ("KOSPI", "KOSDAQ")], ignore_index=True)
    E["code"] = E["code"].str.zfill(6)
    targets = E.groupby("code")["date"].apply(set).to_dict()
    print(f"이벤트 {len(E)}건 · 대상 종목 {len(targets)}")

    dt = {"code": str, "open": "float32", "high": "float32", "low": "float32",
          "close": "float32", "volume": "float32"}
    out = []
    for mk in ("KOSPI", "KOSDAQ"):
        p = os.path.join(DATA, f"종목일봉_30년_{mk}.csv")
        print(f"{mk} 로딩…", flush=True)
        D = pd.read_csv(p, dtype=dt)
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
            n = len(c)
            for d in want:
                t = pos.get(d)
                if t is None or t + 1 >= n or not (np.isfinite(c[t]) and c[t] > 0): continue
                e6 = min(t + W6, n - 1)
                hw = h[t + 1: e6 + 1]
                if not len(hw): continue
                k = int(np.nanargmax(hw))
                peak6 = hw[k] / c[t] - 1
                d6 = k + 1                                  # 고점까지 거래일
                pdate = dts[t + 1 + k]
                e3 = min(t + W3, n - 1)
                hw3 = h[t + 1: e3 + 1]
                peak3 = (np.nanmax(hw3) / c[t] - 1) if len(hw3) else np.nan
                out.append(dict(date=d, code=code, 고점3M=round(peak3 * 100, 1),
                                고점6M=round(peak6 * 100, 1), 고점일수=d6,
                                고점일=pdate, 고점월=int(pdate[5:7]),
                                창완결=(t + W6 <= n - 1)))
        del D; gc.collect()

    P = pd.DataFrame(out)
    M = E.merge(P, on=["date", "code"], how="left")
    # 국면 도장 (역사원장과 동일 게이트)
    hj = _load_mod("휩쏘_역사원장.py", "hj")
    R = hj.regime_table()
    M["date"] = pd.to_datetime(M["date"])
    M = pd.merge_asof(M.sort_values("date"), R.sort_values("date"), on="date", direction="backward")
    M["진입월"] = M["date"].dt.month
    M["출발일"] = M["date"].dt.strftime("%Y-%m-%d")
    keep = ["출발일", "code", "name", "유형", "등급", "국면", "진입월",
            "고점3M", "고점6M", "고점일수", "고점일", "고점월", "창완결",
            "ex_ret", "ex_how", "ex_bars", "fwd40"]
    M[keep].to_csv(os.path.join(HERE, "휩쏘_고점_이벤트.csv"), index=False, encoding="utf-8-sig")
    print(f"저장: 휩쏘_고점_이벤트.csv ({len(M)}건, 고점산출 {M['고점6M'].notna().sum()}건)")

    # ── 콘솔 요약
    C = M[M["창완결"] == True].dropna(subset=["고점6M"])
    print("\n[6개월 창 완결분]", len(C), "건")
    print(f"  6M 고점 중앙 {C['고점6M'].median():+.1f}% · 평균 {C['고점6M'].mean():+.1f}%")
    print(f"  3M 고점 중앙 {C['고점3M'].median():+.1f}%")
    print(f"  고점 도달 중앙 {C['고점일수'].median():.0f}거래일 · 3M 내 고점 비율 {(C['고점일수']<=W3).mean()*100:.0f}%")
    print(f"  카드청산 평균 {C['ex_ret'].mean()*100:+.1f}% vs 6M고점 평균 {C['고점6M'].mean():+.1f}% → 잔여 {C['고점6M'].mean()-C['ex_ret'].mean()*100:+.1f}%p")
    print("\n[진입월별 6M 고점 (중앙값) · 고점월 최빈]")
    for m in range(1, 13):
        s = C[C["진입월"] == m]
        if len(s) < 10: continue
        top = s["고점월"].value_counts().head(3)
        tops = " ".join(f"{k}월{v}" for k, v in top.items())
        print(f"  {m:>2}월 진입 n={len(s):>4} · 6M고점 중앙 {s['고점6M'].median():+6.1f}% · 고점월: {tops}")
    so = C[C["진입월"].isin([9, 10])]
    if len(so):
        spring = so["고점월"].isin([3, 4, 5]).mean()
        print(f"\n[사이클 검정] 9~10월 진입 {len(so)}건 → 고점월이 3~5월(이듬해 봄) 비율 {spring*100:.0f}%")
        print("   고점월 분포:", dict(so["고점월"].value_counts().sort_index()))


if __name__ == "__main__":
    main()
