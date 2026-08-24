# -*- coding: utf-8 -*-
r"""급등_기저율.py — "눌린 종목이 오른다"가 정보인가, 착시인가 (2026-08-01 신설)

[문제]
  7/31 급등 122종 중 97%가 5년 고점 대비 −30% 아래였다. 강력해 보인다.
  그런데 **KOSPI가 고점 대비 −33%인 장에서는 거의 모든 종목이 그렇다.**
  기저율(base rate)을 재지 않으면 이건 "숨 쉬는 사람의 100%가 물을 마신다"와 같은 문장이다.

[재는 것]
  ① 전체 종목 중 '눌림' 비율 (기저율)
  ② P(급등 | 눌림)  vs  P(급등 | 안 눌림)   → **리프트**. 1.0이면 정보 없음.
  ③ 같은 계산을 섹터로 — 반도체 밸류체인 vs 그 외
  ④ 눌림과 섹터를 동시에 넣었을 때 무엇이 남는가 (2×2 층화)

[결론을 미리 정해두지 않는다] 리프트가 1.3 미만이면 '눌림'은 버린다.

사용: py 급등_기저율.py --date 20260731
      py 급등_기저율.py --date 20260731 --min 20
필요: 급등주_YYYYMMDD.csv (급등주_수집.py 산출) · _일봉OHLCV_*_adj.csv · liquidity_sector.csv
⚠️ 사후 관찰 통계. 매수 신호 아님.
"""
import os, sys, argparse, math, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

DD_CUT = -0.30           # '눌림' 정의: 5년 고점 대비 −30% 이하
CHAIN_KEYS = ["반도체", "특수 목적용 기계", "전자부품", "통신 및 방송 장비", "측정, 시험",
              "기초 화학물질", "전동기", "절연선", "일차전지", "기타 화학제품", "광학",
              "일반 목적용 기계", "그외 기타 전문, 과학"]


def _find(fn):
    for d in (HERE, os.path.join(HERE, "데이터수리"), os.path.dirname(HERE), os.getcwd()):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    return None


def z2p(a, b, c, d):
    """2x2 비율 차이 z (a=눌림&급등, b=눌림&비급등, c=안눌림&급등, d=안눌림&비급등)"""
    n1, n2 = a + b, c + d
    if n1 == 0 or n2 == 0: return np.nan
    p1, p2 = a / n1, c / n2
    p = (a + c) / (n1 + n2)
    se = math.sqrt(p * (1 - p) * (1 / n1 + 1 / n2))
    return (p1 - p2) / se if se > 0 else np.nan


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", required=True, help="기준일 YYYYMMDD")
    ap.add_argument("--min", type=float, default=20.0)
    a = ap.parse_args()
    D = a.date
    cut = f"{D[:4]}-{D[4:6]}-{D[6:]}"

    sp = _find(f"급등주_{D}.csv")
    if not sp: sys.exit(f"급등주_{D}.csv 없음 — 먼저 급등주_수집.py 실행")
    S = pd.read_csv(sp, dtype={"code": str}); S["code"] = S["code"].str.zfill(6)
    hot = set(S["code"])
    print("=" * 92)
    print(f" 기저율 검사 — {D} · 급등(≥{a.min:.0f}%) {len(hot)}종")
    print("=" * 92)

    # ── 전 종목 눌림 상태 (급등일 '이전' 데이터만)
    fr = []
    for m in ("KOSPI", "KOSDAQ"):
        p = _find(f"_일봉OHLCV_{m}_adj.csv")
        if p:
            x = pd.read_csv(p, dtype={"code": str}); x["code"] = x["code"].str.zfill(6); x["mkt"] = m
            fr.append(x)
    if not fr: sys.exit("_일봉OHLCV_*_adj.csv 없음")
    L = pd.concat(fr, ignore_index=True)
    L = L[L["date"] < cut].sort_values(["code", "date"])
    rows = []
    for c, g in L.groupby("code", sort=False):
        if len(g) < 250: continue
        px = g["close"].iloc[-1]
        if px < 500: continue
        hi5 = g["high"].tail(1250).max(); ma60 = g["close"].tail(60).mean()
        amt20 = (g["close"] * g["volume"]).tail(20).mean()
        if amt20 < 1e8: continue                     # 거래 거의 없는 종목 제외
        rows.append(dict(code=c, mkt=g["mkt"].iloc[-1], dd5=px / hi5 - 1 if hi5 else np.nan,
                         ma60=px / ma60 - 1 if ma60 else np.nan))
    U = pd.DataFrame(rows).dropna(subset=["dd5"])
    U["급등"] = U["code"].isin(hot)
    U["눌림"] = U["dd5"] <= DD_CUT
    print(f"모집단 {len(U):,}종 (250일 이상·일평균 거래대금 1억 이상) · 이 중 급등 {int(U['급등'].sum())}종")

    print(f"\n[① 기저율] 전체 종목의 5년 고점 대비")
    print(f"    중위 {U['dd5'].median():+.0%} · −30% 이하 {int(U['눌림'].sum()):,}종 "
          f"({U['눌림'].mean()*100:.1f}%)")
    print(f"    급등 종목의 중위 {U[U['급등']]['dd5'].median():+.0%} · "
          f"−30% 이하 {U[U['급등']]['눌림'].mean()*100:.1f}%")

    aa = int((U["눌림"] & U["급등"]).sum()); bb = int((U["눌림"] & ~U["급등"]).sum())
    cc = int((~U["눌림"] & U["급등"]).sum()); dd = int((~U["눌림"] & ~U["급등"]).sum())
    p1 = aa / (aa + bb) if aa + bb else np.nan
    p2 = cc / (cc + dd) if cc + dd else np.nan
    lift = p1 / p2 if p2 else np.nan
    print(f"\n[② 눌림의 리프트]")
    print(f"    P(급등 | 눌림)     = {aa}/{aa+bb} = {p1*100:5.2f}%")
    print(f"    P(급등 | 안 눌림)  = {cc}/{cc+dd} = {p2*100:5.2f}%")
    print(f"    리프트 = {lift:.2f}배   (z = {z2p(aa,bb,cc,dd):.2f})")

    # ── 섹터
    sec = {}
    for f in ("liquidity_sector.csv", "kosdaq_industry.csv"):
        p = _find(f)
        if not p: continue
        try:
            d = pd.read_csv(p, dtype=str); d.columns = [x.strip().lstrip("﻿") for x in d.columns]
            if {"code", "sector"}.issubset(d.columns):
                sec.update(dict(zip(d["code"].str.zfill(6), d["sector"].astype(str))))
        except Exception: pass
    if sec:
        U["sector"] = U["code"].map(sec).fillna("미분류")
        U["체인"] = U["sector"].apply(lambda s: any(k in s for k in CHAIN_KEYS))
        ea = int((U["체인"] & U["급등"]).sum()); eb = int((U["체인"] & ~U["급등"]).sum())
        ec = int((~U["체인"] & U["급등"]).sum()); ed = int((~U["체인"] & ~U["급등"]).sum())
        q1 = ea / (ea + eb) if ea + eb else np.nan
        q2 = ec / (ec + ed) if ec + ed else np.nan
        print(f"\n[③ 섹터의 리프트 — 반도체 밸류체인]")
        print(f"    P(급등 | 체인)     = {ea}/{ea+eb} = {q1*100:5.2f}%")
        print(f"    P(급등 | 체인 밖)  = {ec}/{ec+ed} = {q2*100:5.2f}%")
        print(f"    리프트 = {q1/q2 if q2 else float('nan'):.2f}배   (z = {z2p(ea,eb,ec,ed):.2f})")

        print(f"\n[④ 층화 — 섹터를 고정하고 눌림만 본다]")
        print(f"    {'':<12} {'눌림':>10} {'안 눌림':>10} {'리프트':>8}")
        for lab, sub in (("반도체 체인", U[U["체인"]]), ("체인 밖", U[~U["체인"]])):
            x1 = sub[sub["눌림"]]["급등"].mean() if len(sub[sub["눌림"]]) else np.nan
            x2 = sub[~sub["눌림"]]["급등"].mean() if len(sub[~sub["눌림"]]) else np.nan
            lf = x1 / x2 if (x2 and np.isfinite(x2) and x2 > 0) else np.nan
            print(f"    {lab:<12} {x1*100:>9.2f}% {x2*100:>9.2f}% {lf:>8.2f}배")

    print("\n" + "-" * 92)
    # 판정은 **층화 리프트**로 한다. raw 리프트는 섹터 교란을 그대로 안고 있다.
    strat = np.nan
    if sec:
        sub = U[U["체인"]]
        x1 = sub[sub["눌림"]]["급등"].mean() if len(sub[sub["눌림"]]) else np.nan
        x2 = sub[~sub["눌림"]]["급등"].mean() if len(sub[~sub["눌림"]]) else np.nan
        strat = x1 / x2 if (np.isfinite(x2) and x2 > 0) else np.nan
    key = strat if np.isfinite(strat) else lift
    tag = "층화(섹터 통제)" if np.isfinite(strat) else "raw"
    if key >= 1.3:
        print(f" 판정: 눌림에 정보가 남는다 — {tag} 리프트 {key:.2f}배.")
    else:
        print(f" 판정: **눌림은 정보가 아니다** — {tag} 리프트 {key:.2f}배.")
        print(f"        raw {lift:.2f}배는 거의 전부 섹터 효과의 그림자다.")
        print(f"        '눌린 게 오른다'가 아니라 '오른 섹터가 마침 눌려 있었다'가 맞다.")
    print(" ⚠️ 하루치 관찰이다. 이걸로 규칙을 만들지 말고, 며칠 모아서 사전등록하고 검정할 것.")
    print("-" * 92)
    U.to_csv(os.path.join(HERE, f"_기저율_{D}.csv"), index=False, encoding="utf-8-sig")
    print(f"저장: _기저율_{D}.csv")


if __name__ == "__main__":
    main()
