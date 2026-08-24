#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""검정_상폐처리_무결성.py — (A) 데이터 무결성 + 상장폐지 수익률 실측

목적 두 개.

  1) 무결성 — 30년 패널이 실제 역사를 담고 있는가.
     알려진 사건(1997 IMF · 2000 닷컴 · 2008 리먼 · 2020 코로나)으로 눈금을 맞춘다.
     패널로 만든 지수가 실제 KOSPI 지수를 따라가지 못하면, 그 패널로 만든 어떤
     결론도 못 믿는다.

  2) 상장폐지 수익률 — **추정하지 않는다. 패널에서 직접 측정한다.**

     문제: 상폐 종목의 데이터는 어느 날 그냥 끊긴다. "마지막 가격에 팔았다"고
     가정하면, 실제로는 정리매매에서 반토막 난 종목을 깨끗하게 처분한 걸로
     계산하게 된다. 생존편향을 잡으려고 상폐 종목을 넣었는데 처리 방식 때문에
     편향이 뒷문으로 다시 들어온다.

     ⚠️ 함정: 한국 상폐는 보통 [거래정지 → 실질심사(수개월) → 정리매매(7일)] 순.
        거래정지 구간이 데이터에 어떻게 남는지(행 자체가 없는지, 거래량 0인지)에
        따라 우리가 보는 "마지막 가격"의 의미가 완전히 달라진다. **이것부터 본다.**

산출: 가상매매\검증\상폐처리_무결성_결과.md
사용: py 검정_상폐처리_무결성.py  [--self-test]
"""
import os, sys, warnings
from datetime import date
warnings.filterwarnings("ignore")

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "가상매매", "검증", "상폐처리_무결성_결과.md")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 알려진 사건 — 사후에 고르지 않는다. 역사가 정한 것이다.
EVENTS = [
    ("1997 IMF 외환위기",      "1997-07-01", "1998-06-30"),
    ("2000 닷컴 붕괴",         "2000-01-01", "2000-12-31"),
    ("2008 리먼 사태",         "2008-06-01", "2008-10-31"),
    ("2011 유럽 재정위기",     "2011-08-01", "2011-09-30"),
    ("2020 코로나 폭락",       "2020-01-20", "2020-03-23"),
    ("2022 긴축 약세장",       "2022-01-01", "2022-09-30"),
]

ALIVE_GAP_DAYS = 15      # 패널 마지막 날 기준 이 이내에 데이터가 있으면 '생존'
TAIL_N = 20              # 소멸 직전 관찰 구간(거래일)


def _load(pd, np):
    fs = []
    for m in ("KOSPI", "KOSDAQ"):
        p = os.path.join(BASE, f"종목일봉_30년_{m}.csv")
        if not os.path.exists(p):
            print(f"  [없음] {os.path.basename(p)}")
            return None
        d = pd.read_csv(p, usecols=["date", "code", "close", "volume"],
                        dtype={"code": str}, encoding="utf-8-sig")
        d["mkt"] = m
        fs.append(d)
    d = pd.concat(fs, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d["close"] = pd.to_numeric(d["close"], errors="coerce")
    d["volume"] = pd.to_numeric(d["volume"], errors="coerce").fillna(0)
    d = d.dropna(subset=["date", "close"])
    return d.sort_values(["code", "date"])


# ───────────────────────── 1. 무결성 ─────────────────────────
def integrity(d, pd, np, L):
    print("=" * 84)
    print("1. 무결성 — 패널이 실제 역사를 담고 있는가")
    print("=" * 84)

    L.append("\n## 1. 무결성 — 패널이 실제 역사를 담고 있는가\n\n")

    # 연도별 커버리지
    d["yr"] = d["date"].dt.year
    cov = d.groupby("yr").agg(행=("close", "size"), 종목=("code", "nunique"),
                              거래일=("date", "nunique"))
    print("\n[연도별 커버리지] (앞뒤 5년)")
    print(cov.head(5).to_string())
    print("  ...")
    print(cov.tail(5).to_string())

    L.append("### 연도별 커버리지\n\n| 연도 | 행 | 종목 | 거래일 |\n|---|---|---|---|\n")
    for y in list(cov.index[:3]) + list(cov.index[-3:]):
        r = cov.loc[y]
        L.append(f"| {y} | {r['행']:,} | {r['종목']:,} | {r['거래일']} |\n")

    # 거래일수 이상치 — 한 해 200~260일이 정상
    bad = cov[(cov["거래일"] < 180) & (cov.index > 1996) & (cov.index < 2026)]
    if len(bad):
        print(f"\n  ⚠️ 거래일 부족 연도: {list(bad.index)}")
        L.append(f"\n⚠️ 거래일 180일 미만 연도: {list(bad.index)}\n")
    else:
        print("\n  ✅ 1997~2025 전 연도 거래일 180일 이상")
        L.append("\n✅ 1997~2025 전 연도 거래일 180일 이상 — 통째로 빠진 해 없음\n")

    # 패널 EW 지수 vs 실제 KOSPI 지수
    d["ret"] = d.groupby("code", sort=False)["close"].pct_change() * 100
    r = d[(d["ret"].abs() < 40) & d["ret"].notna()]
    ew = r.groupby("date")["ret"].mean().sort_index()
    ewi = (1 + ew / 100).cumprod()

    kp = os.path.join(BASE, "kospi_index_daily.csv")
    idx = None
    if os.path.exists(kp):
        k = pd.read_csv(kp, encoding="utf-8-sig")
        k.columns = [c.strip().lower() for c in k.columns]
        k["date"] = pd.to_datetime(k["date"], errors="coerce")
        k["close"] = pd.to_numeric(k["close"], errors="coerce")
        idx = k.dropna().set_index("date")["close"].sort_index()

    print("\n[알려진 사건 — 패널 EW 지수가 실제로 무너졌는가]")
    print(f"  {'사건':<22}{'패널 EW':>12}{'실제 KOSPI':>14}   판정")
    L.append("\n### 알려진 사건으로 눈금 맞추기\n\n")
    L.append("사후에 고른 구간이 아니다. 역사가 정한 날짜다.\n\n")
    L.append("| 사건 | 패널 EW 지수 | 실제 KOSPI 지수 | 판정 |\n|---|---|---|---|\n")

    okc = 0
    for name, s, e in EVENTS:
        s, e = pd.Timestamp(s), pd.Timestamp(e)
        seg = ewi[(ewi.index >= s) & (ewi.index <= e)]
        if len(seg) < 5:
            print(f"  {name:<22}{'데이터 없음':>12}")
            L.append(f"| {name} | 데이터 없음 | — | — |\n")
            continue
        ew_dd = (seg.iloc[-1] / seg.iloc[0] - 1) * 100
        if idx is not None:
            ks = idx[(idx.index >= s) & (idx.index <= e)]
            kx = (ks.iloc[-1] / ks.iloc[0] - 1) * 100 if len(ks) > 5 else float("nan")
        else:
            kx = float("nan")
        # 판정: 둘 다 하락, 그리고 방향 일치
        good = (ew_dd < 0) and (not np.isnan(kx)) and (kx < 0)
        okc += 1 if good else 0
        mk = "✅ 일치" if good else "⚠️ 확인"
        print(f"  {name:<22}{ew_dd:>11.1f}%{kx:>13.1f}%   {mk}")
        L.append(f"| {name} | **{ew_dd:.1f}%** | {kx:.1f}% | {mk} |\n")

    # 월간 수익률 상관
    if idx is not None:
        em = ewi.resample("ME").last().pct_change().dropna()
        km = idx.resample("ME").last().pct_change().dropna()
        j = pd.concat([em, km], axis=1, join="inner").dropna()
        j.columns = ["ew", "kospi"]
        c = j["ew"].corr(j["kospi"])
        print(f"\n  월간 수익률 상관 (패널 EW vs KOSPI): {c:.3f}   ({len(j)}개월)")
        L.append(f"\n**월간 수익률 상관 (패널 EW ↔ 실제 KOSPI): {c:.3f}** ({len(j)}개월)\n\n")
        if c > 0.7:
            L.append("→ ✅ 패널이 실제 시장을 따라간다. 같은 시장을 보고 있다.\n")
            print("  ✅ 상관 0.7 초과 — 패널이 실제 시장을 따라간다")
        else:
            L.append(f"→ ⚠️ 상관 {c:.3f}. 낮다. 원인 규명 필요.\n")
            print(f"  ⚠️ 상관 {c:.3f} — 낮다")
        L.append("\n*EW(동일가중)는 소형주 비중이 커서 시총가중 KOSPI와 완전히 같을 수 없다.*\n")
        L.append("*방향과 폭이 맞는지를 본다 — 값이 똑같기를 기대하는 게 아니다.*\n")

    return ewi


# ───────────────── 2. 상폐 종목 식별 + 정리매매 실측 ─────────────────
def delisting(d, pd, np, L):
    print("\n" + "=" * 84)
    print("2. 상장폐지 — 데이터가 어떻게 끊기는가")
    print("=" * 84)

    end = d["date"].max()
    last = d.groupby("code")["date"].max()
    first = d.groupby("code")["date"].min()
    gone = last[last < end - pd.Timedelta(days=ALIVE_GAP_DAYS)]
    alive = last[last >= end - pd.Timedelta(days=ALIVE_GAP_DAYS)]

    print(f"\n  패널 마지막 날: {end.date()}")
    print(f"  전체 종목:      {len(last):,}")
    print(f"  생존(현재상장): {len(alive):,}")
    print(f"  소멸:           {len(gone):,}  ← 상폐 + 합병 + 시장이전 + 코드변경")

    L.append("\n---\n\n## 2. 상장폐지 — 데이터가 어떻게 끊기는가\n\n")
    L.append(f"| 구분 | 종목 수 |\n|---|---|\n")
    L.append(f"| 전체 | {len(last):,} |\n")
    L.append(f"| 생존 (현재 상장) | {len(alive):,} |\n")
    L.append(f"| **소멸** | **{len(gone):,}** |\n\n")
    L.append("소멸에는 상장폐지뿐 아니라 **합병·시장이전·코드변경**도 섞여 있다.\n")
    L.append("구분하지 않으면 손실률이 왜곡된다.\n\n")

    # ── ★ 핵심 질문: 거래정지 구간이 데이터에 남는가 ──
    print("\n" + "-" * 84)
    print("★ 핵심 질문 — 거래정지 구간이 데이터에 남는가")
    print("-" * 84)
    print("  한국 상폐: [거래정지 → 실질심사(수개월) → 정리매매(7일)] → 소멸")
    print("  거래정지 구간의 행이 아예 없다면, 우리가 보는 '마지막 가격'은")
    print("  정리매매 가격이 아니라 **정지 직전 가격**이다. 완전히 다른 얘기가 된다.")

    g = d[d["code"].isin(gone.index)].copy()
    # 종목별 꼬리 TAIL_N 거래일
    g["rk"] = g.groupby("code")["date"].rank(method="first", ascending=False)
    tail = g[g["rk"] <= TAIL_N].copy()

    # 꼬리에서 거래량 0인 날의 비율
    zero_rate = (tail["volume"] == 0).mean() * 100
    # 마지막 날 거래량 0인 종목 비율
    lastday = g[g["rk"] == 1]
    last_zero = (lastday["volume"] == 0).mean() * 100

    print(f"\n  소멸 직전 {TAIL_N}거래일 중 거래량 0인 날: {zero_rate:.1f}%")
    print(f"  마지막 날 거래량이 0인 종목:              {last_zero:.1f}%")

    L.append(f"### ★ 거래정지 구간이 데이터에 남는가\n\n")
    L.append(f"한국 상폐 절차: **거래정지 → 실질심사(수개월) → 정리매매(7거래일) → 소멸**\n\n")
    L.append(f"거래정지 구간의 행이 없다면, 우리가 보는 '마지막 가격'은 정리매매 가격이 아니라 ")
    L.append(f"**정지 직전 가격**이다. 완전히 다른 얘기가 된다.\n\n")
    L.append(f"| 측정 | 값 |\n|---|---|\n")
    L.append(f"| 소멸 직전 {TAIL_N}거래일 중 거래량 0인 날 | {zero_rate:.1f}% |\n")
    L.append(f"| 마지막 날 거래량이 0인 종목 | {last_zero:.1f}% |\n\n")

    # ── 정리매매 실측: 꼬리 구간 수익률 분포 ──
    print("\n" + "-" * 84)
    print("정리매매 실측 — 소멸 직전 수익률 분포 (추정 아님, 실제 데이터)")
    print("-" * 84)
    print("  ★ 거래량 0인 날은 '거래정지'다. 그날의 종가는 얼어붙은 값이다.")
    print("    수익률은 **실제 거래가 있었던 날**끼리만 계산한다.")

    rows = []
    for code, sub in g.groupby("code"):
        sub = sub.sort_values("date")
        px = sub["close"].values
        vol = sub["volume"].values
        n = len(px)
        if n < 25:
            continue

        # 마지막 행 이후로 거슬러 올라가며 거래정지(거래량 0) 꼬리 길이
        halt = 0
        for i in range(n - 1, -1, -1):
            if vol[i] > 0:
                break
            halt += 1

        # 실제 거래가 있었던 날만
        tr = px[vol > 0]
        if len(tr) < 25:
            continue
        last_tr = tr[-1]

        r20 = (last_tr / tr[-21] - 1) * 100 if tr[-21] > 0 else np.nan
        r5 = (last_tr / tr[-6] - 1) * 100 if tr[-6] > 0 else np.nan
        w = tr[-250:] if len(tr) >= 250 else tr
        rpk = (last_tr / w.max() - 1) * 100 if w.max() > 0 else np.nan

        rows.append({"code": code, "last": sub["date"].iloc[-1],
                     "px_last": px[-1], "px_last_traded": last_tr,
                     "r20": r20, "r5": r5, "r_peak": rpk,
                     "halt_tail": halt})
    D = pd.DataFrame(rows)

    # ★ 거래정지 상태로 사라진 종목 — 붕괴가 데이터에 '안 보이는' 종목
    if len(D):
        hs = (D["halt_tail"] > 0).mean() * 100
        hl = (D["halt_tail"] >= 20).mean() * 100
        print(f"\n  [거래정지 상태로 소멸]")
        print(f"    마지막에 거래정지가 있었던 종목:      {hs:.1f}%")
        print(f"    20거래일 이상 정지 후 소멸:           {hl:.1f}%   ← 붕괴가 데이터에 없다")
        L.append("### ★ 거래정지 — 붕괴가 데이터에 안 보이는 종목\n\n")
        L.append("거래량 0 = 거래정지. 그날 종가는 **얼어붙은 값**이지 시장가가 아니다.\n\n")
        L.append(f"| 측정 | 값 |\n|---|---|\n")
        L.append(f"| 마지막에 거래정지가 있었던 소멸 종목 | **{hs:.1f}%** |\n")
        L.append(f"| 20거래일 이상 정지 후 소멸 | **{hl:.1f}%** |\n\n")
        L.append("**이 종목들은 정리매매 붕괴가 패널에 아예 없다.** ")
        L.append("마지막 가격에 팔았다고 하면, 실제로는 팔 수 없었던 가격에 판 것이 된다.\n\n")
    D["yr"] = D["last"].dt.year
    # 최근 종목(시장이전 등 재상장 가능) 제외를 위해 2025년 이후 소멸은 따로 표기
    D = D.dropna(subset=["r20"])

    q = D["r20"].describe(percentiles=[.05, .25, .5, .75, .95])
    print(f"\n  [소멸 직전 20거래일 수익률]  n={len(D):,}")
    print(f"    평균   {D['r20'].mean():>8.1f}%")
    print(f"    중앙값 {D['r20'].median():>8.1f}%")
    print(f"    5%     {D['r20'].quantile(.05):>8.1f}%")
    print(f"    95%    {D['r20'].quantile(.95):>8.1f}%")
    print(f"    −50% 이하 비율 {(D['r20'] <= -50).mean()*100:>6.1f}%")
    print(f"    +10% 이상 비율 {(D['r20'] >= 10).mean()*100:>6.1f}%   ← 합병·이전상장 의심")

    print(f"\n  [소멸 직전 1년 고점 대비]")
    print(f"    중앙값 {D['r_peak'].median():>8.1f}%")
    print(f"    −80% 이하 비율 {(D['r_peak'] <= -80).mean()*100:>6.1f}%")

    L.append("### 정리매매 실측 — 소멸 직전 수익률 분포\n\n")
    L.append("**추정이 아니다. 패널에 있는 실제 가격이다.**\n\n")
    L.append(f"| 지표 | 값 (n={len(D):,}) |\n|---|---|\n")
    L.append(f"| 소멸 직전 20거래일 수익률 · 평균 | **{D['r20'].mean():.1f}%** |\n")
    L.append(f"| 소멸 직전 20거래일 수익률 · 중앙값 | **{D['r20'].median():.1f}%** |\n")
    L.append(f"| 하위 5% | {D['r20'].quantile(.05):.1f}% |\n")
    L.append(f"| 상위 5% | {D['r20'].quantile(.95):.1f}% |\n")
    L.append(f"| −50% 이하로 끝난 종목 | {(D['r20'] <= -50).mean()*100:.1f}% |\n")
    L.append(f"| +10% 이상으로 끝난 종목 | {(D['r20'] >= 10).mean()*100:.1f}% ← 합병·이전상장 의심 |\n")
    L.append(f"| 1년 고점 대비 · 중앙값 | {D['r_peak'].median():.1f}% |\n\n")

    # ── 유형 분류 — 가격 궤적으로 나눈다 ──
    D["type"] = np.where(D["r20"] <= -50, "폭락형(상폐 유력)",
                np.where(D["r20"] >= 10, "정상/상승형(합병·이전 유력)", "완만형(혼재)"))
    t = D.groupby("type").agg(n=("code", "size"), 평균=("r20", "mean"),
                              중앙=("r20", "median"))
    t["비중%"] = t["n"] / len(D) * 100
    print("\n  [가격 궤적으로 본 소멸 유형]")
    print(t.round(1).to_string())

    L.append("### 소멸 유형 — 가격 궤적으로 나눈다\n\n")
    L.append("법적 사유(감사의견 거절·합병·자진상폐)는 데이터에 없다.\n")
    L.append("**대신 가격이 말해준다.**\n\n")
    L.append("| 유형 | 종목 | 비중 | 직전 20일 평균 |\n|---|---|---|---|\n")
    for ty, r in t.iterrows():
        L.append(f"| {ty} | {int(r['n']):,} | {r['비중%']:.1f}% | {r['평균']:.1f}% |\n")
    L.append("\n")

    # ── 편향 크기 계량화 ──
    print("\n" + "-" * 84)
    print("★ 편향 크기 — '마지막 가격에 팔았다'고 하면 얼마나 좋게 나오나")
    print("-" * 84)

    # 연도별 소멸 종목 수 / 그 해 상장 종목 수
    yr_alive = d.groupby(d["date"].dt.year)["code"].nunique()
    yr_gone = D.groupby("yr")["code"].size()
    rate = (yr_gone / yr_alive * 100).dropna()

    print(f"\n  연간 소멸률: 평균 {rate.mean():.2f}%  (최대 {rate.max():.2f}% @ {rate.idxmax()})")

    # 가정별 연간 드래그: 소멸률 × (가정 손실 − 실제 마지막가 손실)
    # 마지막가 손실은 이미 데이터에 반영돼 있다. 추가 손실만 계산.
    print("\n  [상폐 후 추가 손실 가정별 · 연간 포트폴리오 드래그]")
    L.append("### ★ 편향 크기 — 이게 얼마나 결과를 바꾸나\n\n")
    L.append(f"연간 소멸률: 평균 **{rate.mean():.2f}%** (최대 {rate.max():.2f}% @ {rate.idxmax()})\n\n")
    L.append("마지막 가격까지의 하락은 **이미 데이터에 있다.** ")
    L.append("문제는 **그 이후**다 — 정리매매/청산에서 추가로 얼마를 잃는가.\n\n")
    L.append("| 상폐 후 추가 손실 가정 | 연간 드래그 (EW 포트) |\n|---|---|\n")
    # 폭락형만 상폐로 본다 (보수적으로는 완만형도 포함)
    share_crash = (D["type"] != "정상/상승형(합병·이전 유력)").mean()
    eff_rate = rate.mean() * share_crash / 100
    for extra in (0, -30, -50, -70, -100):
        drag = eff_rate * extra
        print(f"    {extra:>4}%  →  연 {drag:>6.2f}%p")
        L.append(f"| {extra}% | **{drag:.2f}%p** |\n")
    L.append(f"\n*상폐 대상 = 소멸 종목 중 정상/상승형을 뺀 {share_crash*100:.0f}%. ")
    L.append(f"연간 실효 소멸률 {eff_rate*100:.2f}%.*\n\n")

    return D, rate, eff_rate


def _self_test():
    import pandas as pd, numpy as np
    ok = tot = 0

    def chk(n, c):
        nonlocal ok, tot
        tot += 1
        ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")

    # 소멸 판정 로직
    end = pd.Timestamp("2026-07-13")
    last = pd.Series({"A": pd.Timestamp("2026-07-13"),
                      "B": pd.Timestamp("2026-07-10"),
                      "C": pd.Timestamp("2010-03-05")})
    gone = last[last < end - pd.Timedelta(days=ALIVE_GAP_DAYS)]
    chk("최근 데이터 있으면 생존", "A" not in gone.index and "B" not in gone.index)
    chk("오래 전에 끊기면 소멸", "C" in gone.index)

    # 수익률 계산
    px = np.array([100.0] * 21 + [50.0])
    r20 = (px[-1] / px[-21] - 1) * 100
    chk("20일 수익률 = −50%", abs(r20 - (-50.0)) < 1e-9)

    # 드래그 계산
    eff = 0.02          # 연 2% 소멸
    chk("추가손실 −100% → 드래그 −2%p", abs(eff * -100 - (-2.0)) < 1e-9)
    chk("추가손실 0% → 드래그 0", abs(eff * 0) < 1e-9)

    # 유형 분류
    d = pd.DataFrame({"r20": [-80, -20, 30]})
    ty = np.where(d["r20"] <= -50, "폭락", np.where(d["r20"] >= 10, "상승", "완만"))
    chk("유형 분류 3종", list(ty) == ["폭락", "완만", "상승"])

    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot


def main():
    if "--self-test" in sys.argv:
        return 0 if _self_test() else 1

    import pandas as pd, numpy as np
    print("데이터 적재 중... (1,470만 행)")
    d = _load(pd, np)
    if d is None:
        return 2
    print(f"  {len(d):,}행 · {d['code'].nunique():,}종목 · "
          f"{d['date'].min().date()} ~ {d['date'].max().date()}")

    L = ["# 상폐 처리 + 무결성 — (A) 선행 검증\n",
         f"\n*{date.today()} · 30년 패널 · 1996~2026*\n",
         "\n포트폴리오 백테스트를 하기 전에 반드시 통과해야 하는 관문.\n",
         "\n*투자자문 아님. 결정·책임은 본인.*\n"]

    integrity(d, pd, np, L)
    D, rate, eff = delisting(d, pd, np, L)

    L.append("\n---\n\n## 결론 — 앞으로 쓸 규칙\n\n")
    L.append("이 문서의 숫자를 보고 `상폐수익률_가정.md`에 가정을 못 박는다.\n")
    L.append("**모든 포트폴리오 백테스트는 그 가정을 쓴다.** 결과가 마음에 안 든다고 바꾸지 않는다.\n")

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write("".join(L))
    print("\n" + "=" * 84)
    print("저장: 가상매매\\검증\\상폐처리_무결성_결과.md")
    print("=" * 84)
    return 0


if __name__ == "__main__":
    sys.exit(main())
