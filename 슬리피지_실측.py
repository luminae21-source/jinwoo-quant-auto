#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
슬리피지_실측.py — 왕복 거래비용 실측 (§8-3)

── 문제 ──────────────────────────────────────────────────────────
진우퀀트 코드베이스에 **거래비용 상수가 최소 7종 병존**한다 (2026-07-27 전수조사):

    tax=0.002 + slippage=0.0005   17회 · 11회   ← 다올 모델 (백테 주력)
    COST = _jq_cost(0.00235)                15회          ← v3.7.2 계열  # §8-3: 종전 0.235% → 실측 0.559% (+0.324%p)
    COST = _jq_cost(0.0048)                  2회          ← 복리 시나리오  # §8-3: 종전 0.480% → 실측 0.559% (+0.079%p)
    COST = _jq_cost(0.0015) / 0.0030 / 0.0035 / 0.006      ← 산발  # §8-3: 종전 0.150% → 실측 0.559% (+0.409%p)
    COST = 40.0                    1회          ← 정액 수수료(원) 혼입 추정

같은 전략을 어느 스크립트로 돌리느냐에 따라 **연 0.3%p 이상** 결과가 달라진다.
비용 상수는 **가정**인데 지금까지 **실측된 적이 없다.**

── 방법 ──────────────────────────────────────────────────────────
Corwin–Schultz (2012) 고저가 스프레드 추정량. 연속 2거래일의 고가·저가만으로
유효 스프레드를 추정한다 — 호가 데이터 없이 일봉만으로 계산 가능한 표준 방법.

    beta = [ln(H_t/L_t)]^2 + [ln(H_{t+1}/L_{t+1})]^2
    gamma = [ln(max(H_t,H_{t+1}) / min(L_t,L_{t+1}))]^2
    alpha = (sqrt(2*beta) - sqrt(beta)) / (3 - 2*sqrt(2)) - sqrt(gamma / (3 - 2*sqrt(2)))
    S = 2*(exp(alpha) - 1) / (1 + exp(alpha))        # 상대 스프레드

편도 슬리피지 ≈ S/2 (중간가 대비 반스프레드). 음수 추정치는 0으로 절단(표준 처리).
시총 상위 pool 안에서만 측정한다 — 실제로 그 안에서만 거래하므로.

── 사용 ──────────────────────────────────────────────────────────
    py 슬리피지_실측.py                 # 최근 5년 · top300
    py 슬리피지_실측.py --years 10 --top 100
    py 슬리피지_실측.py --out 비용_실측.md

⚠️ 검증용 · 실현손익 아님 · 투자자문 아님
"""
# ── §8-3 비용 SSOT (2026-07-27) ─────────────────────────────────
# 코드베이스에 거래비용 상수가 7종 병존했다(0.235%~0.6%). 실측 왕복 0.559%로 통일한다.
# 종전 값은 각 대입문 주석에 남겼다. import 실패 시 종전 값으로 폴백한다.
try:
    import sys as _s3, os as _o3
    _d3 = _o3.path.dirname(_o3.path.abspath(__file__))
    for _ in range(5):
        if _o3.path.exists(_o3.path.join(_d3, "비용모델.py")):
            _s3.path.insert(0, _d3); break
        _d3 = _o3.path.dirname(_d3)
    from 비용모델 import roundtrip as _jq_rt
except Exception:
    _jq_rt = None


def _jq_cost(legacy):
    """SSOT 왕복비용. 못 불러오면 종전 값 유지."""
    return _jq_rt("기준") if _jq_rt else legacy
# ────────────────────────────────────────────────────────────────

try:  # 윈도 파이프(cp949)에서 이모지 출력 시 UnicodeEncodeError 방지 (2026-07-27)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
K = 3 - 2 * np.sqrt(2)


def find(name):
    for b in (ROOT, os.getcwd()):
        h = [x for x in glob.glob(os.path.join(b, "**", name), recursive=True)
             if not any(s in x for s in ("_백업", "_보관", "_archive"))]
        if h:
            return sorted(h, key=len)[0]
    return None


def corwin_schultz(h, l):
    """h, l: (날짜 x 종목) 고가·저가. 반환: (날짜 x 종목) 상대 스프레드."""
    with np.errstate(divide="ignore", invalid="ignore"):
        hl = np.log(h / l) ** 2
        beta = hl + hl.shift(1)
        h2 = np.maximum(h, h.shift(1))
        l2 = np.minimum(l, l.shift(1))
        gamma = np.log(h2 / l2) ** 2
        alpha = (np.sqrt(2 * beta) - np.sqrt(beta)) / K - np.sqrt(gamma / K)
        S = 2 * (np.exp(alpha) - 1) / (1 + np.exp(alpha))
    return S.where(S > 0, 0.0)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=5)
    ap.add_argument("--top", type=int, default=300)
    ap.add_argument("--out", default="비용_실측_2026-07-27.md")
    a = ap.parse_args()

    print("=" * 78)
    print(" 왕복 거래비용 실측 · Corwin–Schultz 고저가 스프레드 · §8-3")
    print("=" * 78)

    fr = []
    for mkt in ("KOSPI", "KOSDAQ"):
        p = find(f"_일봉OHLCV_{mkt}_adj.csv")
        if not p:
            continue
        d = pd.read_csv(p, dtype={"code": str}, usecols=["code", "date", "high", "low"])
        d["code"] = d["code"].str.zfill(6)
        fr.append(d)
        print(f"  일봉 {mkt}: {os.path.relpath(p, ROOT)} ({len(d):,}행)")
    if not fr:
        sys.exit("일봉 OHLCV(_adj)를 못 찾음")
    d = pd.concat(fr, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"])
    cut = d["date"].max() - pd.DateOffset(years=a.years)
    d = d[d["date"] >= cut]
    d["ym"] = d["date"].dt.strftime("%Y-%m")

    mp = find("종목시총_30년.csv")
    mc = pd.read_csv(mp, dtype={"code": str})
    mc["code"] = mc["code"].str.zfill(6)
    mc["ym"] = pd.to_datetime(mc["date"]).dt.strftime("%Y-%m")
    M = mc.pivot_table(index="ym", columns="code", values="mcap", aggfunc="last")
    univ = (M.rank(axis=1, ascending=False) <= a.top).shift(1)   # 전월말 기준

    H = d.pivot_table(index="date", columns="code", values="high", aggfunc="last")
    L = d.pivot_table(index="date", columns="code", values="low", aggfunc="last")
    S = corwin_schultz(H, L)
    S = S.where(H.notna() & L.notna() & (H > L))

    ymv = pd.Series(S.index.strftime("%Y-%m"), index=S.index)
    cols = [c for c in S.columns if c in univ.columns]
    S = S[cols]
    mask = pd.DataFrame(False, index=S.index, columns=cols)
    for ym, sub in ymv.groupby(ymv):
        if ym in univ.index:
            row = univ.loc[ym, cols].fillna(False).values.astype(bool)
            mask.loc[sub.index, :] = row
    Su = S.where(mask)

    half = Su.stack().dropna() / 2                       # 편도 = 반스프레드
    q = half.quantile([.25, .50, .75, .90])
    print(f"\n  표본 {len(half):,} (종목·일) · 최근 {a.years}년 · 시총 top{a.top}")
    print(f"  편도 슬리피지 추정 — 중앙값 {q[.50]*100:.4f}% · 평균 {half.mean()*100:.4f}%")
    print(f"     25% {q[.25]*100:.4f}%  ·  75% {q[.75]*100:.4f}%  ·  90% {q[.90]*100:.4f}%")

    print("\n  [연도별 편도 중앙값]")
    yr = half.groupby(half.index.get_level_values(0).year).median()
    for y, v in yr.items():
        print(f"     {y}  {v*100:.4f}%")

    TAX = _jq_cost(0.0015)          # 증권거래세(코스피 0.15% 2026, 매도만)  # §8-3: 종전 0.150% → 실측 0.559% (+0.409%p)
    FEE = 0.0             # 다올 수수료 0
    slip1 = float(q[.50])
    rt = TAX + FEE * 2 + slip1 * 2
    print("\n" + "-" * 78)
    print("  [권고 단일 모델] 회전율 f 1회당 왕복비용")
    print(f"     세금(매도) {TAX*100:.3f}%  +  수수료 {FEE*100:.3f}%×2  +  슬리피지 {slip1*100:.4f}%×2")
    print(f"     = **{rt*100:.3f}% / 회전 1.0**")
    print(f"\n  현행 병존 상수 대비:")
    for lab, v in [("다올(tax .002 + slip .0005×2)", 0.003),
                   ("v3.7.2 COST 0.00235", 0.00235),
                   ("복리시나리오 0.0048", 0.0048)]:
        print(f"     {lab:34} {v*100:.3f}%   차이 {(v-rt)*100:+.3f}%p")

    L2 = ["# 왕복 거래비용 실측 (§8-3)", "",
          f"> Corwin–Schultz 고저가 스프레드 · 최근 {a.years}년 · 시총 top{a.top} · 표본 {len(half):,}",
          "", "| 항목 | 값 |", "|---|---|",
          f"| 편도 슬리피지 중앙값 | **{q[.50]*100:.4f}%** |",
          f"| 편도 평균 | {half.mean()*100:.4f}% |",
          f"| 편도 75%ile | {q[.75]*100:.4f}% |",
          f"| 편도 90%ile | {q[.90]*100:.4f}% |",
          f"| 증권거래세(매도) | {TAX*100:.3f}% |",
          f"| **왕복 총비용 / 회전 1.0** | **{rt*100:.3f}%** |", "",
          "## 현행 병존 상수 대비", "", "| 출처 | 상수 | 실측 대비 |", "|---|---|---|"]
    for lab, v in [("다올 모델 (tax .002 + slip .0005×2)", 0.003),
                   ("v3.7.2 계열 COST", 0.00235), ("복리 시나리오", 0.0048)]:
        L2.append(f"| {lab} | {v*100:.3f}% | {(v-rt)*100:+.3f}%p |")
    L2 += ["", "> ⚠️ Corwin–Schultz는 호가 부재 시의 **추정량**이다. 실제 체결 슬리피지는",
           "> 주문 크기·시장충격에 따라 더 클 수 있다. 보수적으로 쓰려면 75%ile을 쓸 것.",
           "> ⚠️ 검증용 · 실현손익 아님 · 투자자문 아님"]
    out = a.out if os.path.isabs(a.out) else os.path.join(ROOT, a.out)
    open(out, "w", encoding="utf-8").write("\n".join(L2))
    print(f"\n  저장: {os.path.relpath(out, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
