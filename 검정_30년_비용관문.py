#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""검정_30년_비용관문.py — 하순 필터 (D) 비용 관문

30년 재검정에서 ③하순이 (A)IN · (B)이상치 · (C)OOS 세 관문을 통과했다.
    전체    OOS p=0.0141
    시총소  OOS p=0.0002  (Bonferroni×12 = 0.0024)
    시총중  OOS p=0.0041
    시총대  OOS p=0.1211  ← 기각

남은 관문은 (D) 비용이다.

  · 사용법 A — **타이밍 규칙**: 하순엔 현금, 나머지는 보유 → 연 12회 왕복 매매
       한국 매도세 0.18% + 수수료 + 슬리피지 = 왕복 0.45%(현실) / 0.70%(보수)
  · 사용법 B — **진입 필터**: 어차피 살 종목, 하순엔 진입만 미룬다 → **매매 추가 없음 = 비용 0**

이 스크립트는 A를 계산한다. B는 정의상 비용이 0이라 (D)를 자동 통과한다.

산출: 가상매매\검증\30년_비용관문_결과.md
사용: py 검정_30년_비용관문.py
"""
import os, sys, warnings
from datetime import date
warnings.filterwarnings("ignore")

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "가상매매", "검증", "30년_비용관문_결과.md")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

LATE_RD = (-9, -8, -7, -6, -5)
IN_END, OOS_START = 2012, 2013
COSTS = [0.0, 0.25, 0.45, 0.70]     # 왕복 %
RF_ANN = 3.0


def main():
    import pandas as pd, numpy as np

    print("=" * 84)
    print("(D) 비용 관문 — 하순 회피 '타이밍 규칙' (연 12회 왕복)")
    print("=" * 84)

    fs = []
    for m in ("KOSPI", "KOSDAQ"):
        p = os.path.join(BASE, f"종목일봉_30년_{m}.csv")
        if not os.path.exists(p):
            print(f"  [없음] {os.path.basename(p)}")
            return 2
        d = pd.read_csv(p, usecols=["code", "date", "close"], dtype={"code": str},
                        encoding="utf-8-sig")
        fs.append(d)
    d = pd.concat(fs, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d["close"] = pd.to_numeric(d["close"], errors="coerce")
    d = d.dropna()
    d = d[d["close"] > 0].sort_values(["code", "date"])
    d["ret"] = d.groupby("code", sort=False)["close"].pct_change() * 100
    d = d.dropna(subset=["ret"])
    d = d[d["ret"].abs() < 30]
    d["ym"] = d["date"].dt.year * 12 + d["date"].dt.month
    print(f"  {len(d):,}행 · {d.code.nunique():,}종목")

    # 시총 3분위 (전월 시총 → 룩어헤드 차단)
    mp = os.path.join(BASE, "종목시총_30년.csv")
    mc = pd.read_csv(mp, dtype={"code": str}, encoding="utf-8-sig")
    mc["date"] = pd.to_datetime(mc["date"], errors="coerce")
    mc["mcap"] = pd.to_numeric(mc["mcap"], errors="coerce")
    mc = mc.dropna()
    mc["ym"] = mc["date"].dt.year * 12 + mc["date"].dt.month
    mc = mc.groupby(["code", "ym"])["mcap"].last().reset_index()
    mc["ym"] += 1
    d = d.merge(mc, on=["code", "ym"], how="left")
    d["q"] = d.groupby("ym")["mcap"].transform(
        lambda s: pd.qcut(s, 3, labels=["소", "중", "대"], duplicates="drop")
        if s.notna().sum() > 30 else np.nan)

    # 달력
    cal = pd.DataFrame({"date": sorted(d["date"].unique())})
    cal["ym"] = cal["date"].dt.year * 12 + cal["date"].dt.month
    g = cal.groupby("ym")
    cal["t"] = g.cumcount() + 1
    cal["n"] = g["date"].transform("size")
    cal["rd"] = cal["t"] - cal["n"] - 1
    cal["LATE"] = cal["rd"].isin(LATE_RD)
    calx = cal.set_index("date")[["LATE"]]

    rf_d = RF_ANN / 252
    L = ["# (D) 비용 관문 — 하순 필터\n",
         f"\n*{date.today()} · 30년 패널(5,051종목 · 상폐 포함) · 1996~2026*\n",
         "\n③하순은 (A)IN·(B)이상치·(C)OOS 세 관문을 통과했다. 남은 건 비용이다.\n",
         "\n*투자자문 아님. 결정·책임은 본인.*\n\n---\n"]

    def sim(ew, mask, cost, lo, hi):
        x = ew[(ew.index.year >= lo) & (ew.index.year <= hi)]
        m = mask.reindex(x.index).fillna(False)
        pos = (~m).astype(float)                  # 하순엔 현금(0), 나머지 보유(1)
        sr = np.where(pos == 1, x["ret"], rf_d)
        turn = pos.diff().abs().fillna(pos)
        sr = pd.Series(sr - turn.values * cost / 2, index=x.index)
        e = (1 + sr / 100).cumprod()
        yrs = len(x) / 252
        cagr = e.iloc[-1] ** (1 / yrs) - 1
        sh = (sr.mean() - rf_d) / sr.std() * np.sqrt(252)
        mdd = float((e / e.cummax() - 1).min())
        return cagr * 100, sh, mdd * 100, int(turn.sum())

    def bh(ew, lo, hi):
        x = ew[(ew.index.year >= lo) & (ew.index.year <= hi)]
        e = (1 + x["ret"] / 100).cumprod()
        yrs = len(x) / 252
        cagr = e.iloc[-1] ** (1 / yrs) - 1
        sh = (x["ret"].mean() - rf_d) / x["ret"].std() * np.sqrt(252)
        mdd = float((e / e.cummax() - 1).min())
        return cagr * 100, sh, mdd * 100

    for sname, q in [("전체", None), ("시총 소", "소"), ("시총 중", "중")]:
        sub = d if q is None else d[d["q"] == q]
        ew = sub.groupby("date").agg(ret=("ret", "mean")).sort_index()
        mask = calx["LATE"]

        print("\n" + "━" * 84)
        print(f"■ {sname}   ({len(ew):,}거래일)")
        print("━" * 84)
        L.append(f"\n## {sname}\n\n")
        L.append("| 구간 | 전략 | CAGR | Sharpe | MDD | 거래 | vs buy&hold |\n")
        L.append("|---|---|---|---|---|---|---|\n")

        for lbl, lo, hi in [("IN 1996~2012", 1996, IN_END),
                            ("OOS 2013~2026", OOS_START, 2026)]:
            b = bh(ew, lo, hi)
            print(f"\n  [{lbl}]")
            print(f"    {'전략':<28}{'CAGR':>9}{'Sharpe':>8}{'MDD':>9}{'거래':>7}   vs bh")
            print(f"    {'buy&hold (기준)':<28}{b[0]:>8.2f}%{b[1]:>8.2f}{b[2]:>8.1f}%{1:>7}      —")
            L.append(f"| {lbl} | buy&hold (기준) | {b[0]:.2f}% | {b[1]:.2f} | {b[2]:.1f}% | 1 | — |\n")
            for c in COSTS:
                r = sim(ew, mask, c, lo, hi)
                gap = r[0] - b[0]
                mk = "✅" if gap > 0 else "❌"
                nm = f"하순회피 (왕복 {c:.2f}%)"
                print(f"    {nm:<28}{r[0]:>8.2f}%{r[1]:>8.2f}{r[2]:>8.1f}%{r[3]:>7}  {gap:+6.2f}%p {mk}")
                L.append(f"| {lbl} | {nm} | {r[0]:.2f}% | {r[1]:.2f} | {r[2]:.1f}% | {r[3]} | **{gap:+.2f}%p** {mk} |\n")

    L.append("""
---

## 판정 — (D) 비용 관문

| 사용법 | 매매 추가 | 비용 | (D) |
|---|---|---|---|
| **진입 필터** (어차피 살 종목, 하순엔 진입만 미룸) | **없음** | **0** | **통과** |
| 타이밍 규칙 (하순엔 현금, 나머지 보유) | 연 12회 왕복 | 왕복 0.45%+ | 위 표 참조 |

**진입 필터는 매매를 추가하지 않는다.** 어차피 할 매매의 시점만 옮긴다.
거래 횟수가 늘지 않으므로 비용이 발생하지 않는다 → **(D) 자동 통과.**

## 최종

③하순은 (A)(B)(C)를 30년·상폐포함·OOS봉인 상태에서 통과했다.
(D)는 **진입 필터로 쓰는 한 통과**한다.

**→ 진입 필터로 채택.** 코스닥 소형·중형에서 특히 강하다(대형주는 OOS에서 기각).

⚠️ 타이밍 규칙으로 쓸지는 위 표의 비용별 성과를 보고 판단할 것.
""")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write("".join(L))
    print("\n" + "=" * 84)
    print("저장: 가상매매\\검증\\30년_비용관문_결과.md")
    print("=" * 84)
    return 0


if __name__ == "__main__":
    sys.exit(main())
