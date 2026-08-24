#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
롱온리_재산출.py — 세션정리 §8-1

30년 롱온리 백테를 **정상 시차 · 상폐포함 · EW 대조군**으로 재산출한다.
룩어헤드판(mcap 미시차)을 나란히 찍어서 편향 크기를 매 전략마다 보인다.

── 왜 미조정 월봉인가 (2026-07-27 확인) ─────────────────────────────
조정본(`데이터수리\_월봉종가캐시_*_adj.csv`)은 과거 커버리지가 무너져 있다:
    1996-01  0.1%  ·  2000-01  8.2%  ·  2005-01 25.2%  ·  2010-01 26.6%  ·  2015-01+ 100%
    중도소멸 비율 조정본 26.8% vs 미조정 45.0%
즉 조정본으로 30년을 돌리면 **룩어헤드를 고치면서 생존편향을 새로 들인다.**
→ 30년 전구간은 미조정(상폐포함) 사용. CA(액면분할·배당락) 영향은 ±100% 클리핑으로 방어.
→ 조정본은 2015년 이후 구간 대조에만 쓴다(`--adj-recent`).

── 시차 규약 ────────────────────────────────────────────────────────
    rets[t] = P[t]/P[t-1] - 1        (t월 중에 벌어진 수익)
    이 수익을 벌려면 t-1월말에 이미 들고 있어야 한다
    → 선택 변수는 전부 **t-1월말 시점** 값: mcap.shift(1) · 모멘텀 P[t-13:t-1]
  룩어헤드판은 mcap.loc[t](= t월말 스냅샷)를 그대로 써서 사후 승자를 고른다.

사용:
    py 롱온리_재산출.py
    py 롱온리_재산출.py --start 2006-01 --out 재산출_2006.md

⚠️ 검증용 · 실현손익 아님 · 투자자문 아님 · 책임 본인
"""
# §8-3(2026-07-27): tax 0.002→0.0015(실제 증권거래세) · slip 0.0005→0.002045(CS 실측 편도) → 왕복 0.300%→0.559%

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
# 2026-07-27: 비용모델.py(SSOT)로 통일. 종전 하드코딩 tax=0.002/slip=0.0005는 왕복 0.300%로
# 실측(왕복 0.559%) 대비 0.259%p 과소평가였다. --cost 로 시나리오 전환.
try:
    from 비용모델 import roundtrip as _rt, SCENARIOS as _SC
except Exception:
    _SC = ("낙관", "기준", "보수")
    _rt = lambda s="기준": {"낙관": 0.0025, "기준": 0.00559, "보수": 0.01511}[s]
ROUNDTRIP = _rt("기준")


def find(name):
    for b in (ROOT, os.getcwd()):
        h = glob.glob(os.path.join(b, "**", name), recursive=True)
        h = [x for x in h if "_백업" not in x and "_보관" not in x and "_archive" not in x]
        if h:
            return sorted(h, key=len)[0]
    return None


def load_px(adjusted=False, full=False):
    # 2026-07-27 §8-1b: _full = 시총 유도 CA 보정 복원본 (전 구간 100% · 상폐 45.0% 포함)
    pat = ("_월봉종가캐시_{}_full.csv" if full else
           "_월봉종가캐시_{}_adj.csv" if adjusted else "_월봉종가캐시_{}.csv")
    fr = []
    for mkt in ("KOSPI", "KOSDAQ"):
        p = find(pat.format(mkt))
        if p:
            d = pd.read_csv(p, dtype={"code": str})
            d["code"] = d["code"].str.zfill(6)
            fr.append(d)
    if not fr:
        sys.exit("월봉 캐시를 못 찾음")
    px = (pd.concat(fr, ignore_index=True)
          .pivot_table(index="ym", columns="code", values="close", aggfunc="last").sort_index())
    return px


def load_mcap():
    p = find("종목시총_30년.csv")
    d = pd.read_csv(p, dtype={"code": str})
    d["code"] = d["code"].str.zfill(6)
    d["ym"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m")
    return d.pivot_table(index="ym", columns="code", values="mcap", aggfunc="last")


def load_defense(index_ym):
    """KOSPI 월말종가 10개월 MA. 신호는 **전월말** 확정분을 쓴다(shift(1))."""
    p = find("kospi_index_daily.csv")
    if not p:
        return None, None
    d = pd.read_csv(p, parse_dates=["Date"]).set_index("Date").sort_index()
    me = d["Close"].resample("ME").last()
    me.index = me.index.strftime("%Y-%m")
    ma = me.rolling(10).mean()
    above = (me >= ma).shift(1)                       # ← 전월말 신호
    return above.reindex(index_ym), me.reindex(index_ym)


def stats(r):
    r = pd.Series(r).dropna()
    if len(r) < 12:
        return dict(cagr=np.nan, sharpe=np.nan, mdd=np.nan, n=len(r))
    eq = (1 + r).cumprod()
    cagr = eq.iloc[-1] ** (12 / len(r)) - 1
    sh = r.mean() / r.std() * np.sqrt(12) if r.std() > 0 else np.nan
    mdd = (eq / eq.cummax() - 1).min()
    return dict(cagr=cagr * 100, sharpe=sh, mdd=mdd * 100, n=len(r))


# ══════════════════════════════════════════════════════════════════
def backtest(R, M, MOM, strategy, lag=True, defense=None, cash=0.5, topn=30, pool=300):
    """롱온리 월간 리밸런스. lag=True면 선택변수를 전월말로 민다(정상)."""
    Msel = M.shift(1) if lag else M              # ★ 유일한 차이
    held, gross, net, turns = set(), [], [], []
    months = list(R.index)
    for k, t in enumerate(months):
        if t not in Msel.index:
            continue
        mc = Msel.loc[t].dropna()
        if len(mc) < 50:
            continue
        cur = R.loc[t]
        rank = mc.sort_values(ascending=False)

        if strategy == "TOP30_고정":
            sel = [c for c in rank.index[:topn] if pd.notna(cur.get(c))]
            w = None
        elif strategy == "동적_리더십":
            cand = [c for c in rank.index[:pool] if pd.notna(cur.get(c))]
            if t not in MOM.index:
                continue
            m = MOM.loc[t, [c for c in cand if c in MOM.columns]].dropna()
            if len(m) < topn:
                continue
            sel = list(m.sort_values(ascending=False).index[:topn])
            w = None
        elif strategy == "TOP300_EW":
            sel = [c for c in rank.index[:pool] if pd.notna(cur.get(c))]
            w = None
        elif strategy == "전종목_시총가중":
            sel = [c for c in rank.index if pd.notna(cur.get(c))]
            v = rank[sel]
            w = (v / v.sum())
        else:
            raise ValueError(strategy)

        if len(sel) < 5:
            continue

        f = 1 - len(set(sel) & held) / len(sel) if held else 1.0
        turns.append(f)
        cost = f * ROUNDTRIP
        g = float(cur[sel].mean()) if w is None else float((cur[sel] * w).sum())

        invest = 1.0
        if defense is not None:
            sig = defense.get(t)
            if pd.notna(sig) and not bool(sig):
                invest = 1.0 - cash
        gross.append(g * invest)
        net.append(g * invest - cost)
        held = set(sel)
    s_g, s_n = stats(gross), stats(net)
    s_n["gross_cagr"] = s_g["cagr"]
    s_n["turn"] = float(np.mean(turns) * 12) if turns else 0.0
    return s_n


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=None, help="예: 2006-01 (기본 전구간)")
    ap.add_argument("--out", default="재산출_롱온리_2026-07-27.md")
    ap.add_argument("--include-partial", action="store_true",
                    help="미완료 최종월 포함(기본 제외). 2026-07은 7/24까지라 -21%%가 통째로 들어간다")
    ap.add_argument("--cost", default="기준", choices=list(_SC),
                    help="비용 시나리오 (비용모델.py) — 낙관 0.250%% · 기준 0.559%% · 보수 1.511%%")
    ap.add_argument("--pool", type=int, default=100,
                    help="리더십 후보풀 크기 (원 스크립트 기본 max(100,3N)=100)")
    ap.add_argument("--full", action="store_true",
                    help="§8-1b 복원본 사용 — 30년 전구간 100%% 커버 · 상폐포함 · CA 보정")
    ap.add_argument("--adj", action="store_true", help="조정본 월봉 사용(2015+ 구간에서만 유효)")
    a = ap.parse_args()

    global ROUNDTRIP
    ROUNDTRIP = _rt(a.cost)
    PX = load_px(a.adj, a.full)
    R = PX.pct_change(fill_method=None).mask(lambda x: x.abs() > 1.0)
    M = load_mcap()
    idx = [m for m in R.index if m in M.index]
    if a.start:
        idx = [m for m in idx if m >= a.start]
    # 2026-07-27: 미완료 최종월 제외. 부분월이 30년 CAGR을 0.8%p 흔든다(KOSPI 7.7%→6.9%).
    if not a.include_partial and len(idx) > 1:
        dropped = idx[-1]
        idx = idx[:-1]
        print(f"  ⚠️ 미완료 최종월 {dropped} 제외 (--include-partial로 포함 가능)")
    R, M = R.reindex(idx), M.reindex(idx)
    # 12-1 모멘텀: t-13 → t-1 (t월 수익과 겹치지 않음)
    MOM = (PX.reindex(idx).shift(1) / PX.reindex(idx).shift(13) - 1)
    DEF, IDXPX = load_defense(idx)

    print("=" * 92)
    print(" 롱온리 30년 재산출 · §8-1 · 미조정(상폐포함) · 정상시차 · EW 대조군")
    print("=" * 92)
    print(f"  구간 {idx[0]} ~ {idx[-1]} ({len(idx)}개월) · 종목 {R.shape[1]:,} · "
          f"비용 {a.cost} 시나리오 왕복 {ROUNDTRIP*100:.3f}%/회전")
    _src = ("복원본(_full) — 상폐포함 100% + CA 보정 (§8-1b)" if a.full
            else "조정본(_adj) — CA 교정, 2014년 이전 커버리지 27%" if a.adj
            else "미조정(원본) — 상폐포함, CA 미교정")
    print(f"  가격 소스: {_src}")
    print(f"  방어 신호: {'KOSPI 10개월MA (전월말 확정)' if DEF is not None else '없음 — 지수파일 미발견'}")
    print()

    rows = []
    SPECS = [
        ("TOP30_고정", "TOP30_고정", None),
        ("동적_리더십(12-1)", "동적_리더십", None),
        ("EW 대조군(pool)", "TOP300_EW", None),
        ("전종목_시총가중(지수프록시)", "전종목_시총가중", None),
    ]
    if DEF is not None:
        SPECS += [("TOP30_고정 +방어50%", "TOP30_고정", DEF),
                  ("동적_리더십 +방어50%", "동적_리더십", DEF)]

    hdr = f"  {'전략':<26}{'룩어헤드판':>11}{'교정판':>10}{'차이':>10}{'Sharpe':>9}{'MDD':>9}{'회전/년':>8}"
    print(hdr)
    print("  " + "-" * 88)
    for label, strat, dfs in SPECS:
        bad = backtest(R, M, MOM, strat, lag=False, defense=dfs, pool=a.pool)
        good = backtest(R, M, MOM, strat, lag=True, defense=dfs, pool=a.pool)
        d = good["cagr"] - bad["cagr"]
        flag = " 🚨" if abs(d) >= 3.0 else ""
        print(f"  {label:<26}{bad['cagr']:>10.1f}%{good['cagr']:>9.1f}%{d:>+9.1f}%p"
              f"{good['sharpe']:>9.2f}{good['mdd']:>8.1f}%{good['turn']:>7.1f}x{flag}")
        rows.append((label, bad, good))
    print("  " + "-" * 88)

    # 벤치마크: KOSPI 지수 실적
    # 2026-07-27: 벤치는 idx(시총 보유월)에 맞추면 안 된다 — 결측이 있으면 벤치까지 왜곡된다.
    # 구간 [idx[0], idx[-1]] 의 **연속** 월말 시계열로 따로 계산한다.
    kospi = None
    if IDXPX is not None:
        _p = find("kospi_index_daily.csv")
        _d = pd.read_csv(_p, parse_dates=["Date"]).set_index("Date").sort_index()
        _me = _d["Close"].resample("ME").last()
        _me.index = _me.index.strftime("%Y-%m")
        _s = _me[(_me.index >= idx[0]) & (_me.index <= idx[-1])]
        ir = _s.pct_change().dropna()
        kospi = stats(ir)
        print(f"  {'KOSPI 지수(PR)':<26}{'':>10} {kospi['cagr']:>8.1f}%{'':>10}"
              f"{kospi['sharpe']:>9.2f}{kospi['mdd']:>8.1f}%")

    ew = [r for r in rows if r[0].startswith("EW 대조군")][0][2]
    print()
    print("  [해석]")
    for label, bad, good in rows:
        if label.startswith("EW 대조군"):
            continue
        vs = good["cagr"] - ew["cagr"]
        print(f"   · {label:<26} 교정 후 EW 대조군 대비 {vs:+.1f}%p")
    if kospi:
        print(f"   · EW 대조군 {ew['cagr']:.1f}% vs KOSPI(PR) {kospi['cagr']:.1f}% "
              f"→ EW 프리미엄 {ew['cagr']-kospi['cagr']:+.1f}%p")

    # ── 마크다운 저장
    L = ["# 롱온리 30년 재산출 (§8-1)", "",
         f"> 구간 {idx[0]} ~ {idx[-1]} ({len(idx)}개월) · {'복원본(§8-1b)' if a.full else '조정본' if a.adj else '미조정'} 월봉 · "
         f"비용 {a.cost} 시나리오 (왕복 {ROUNDTRIP*100:.3f}%/회전)", "",
         "**시차 규약:** 선택변수(시총·모멘텀)는 전월말 확정분. "
         "룩어헤드판은 당월말 시총으로 사후 선택.", "",
         "| 전략 | 룩어헤드판 CAGR | 교정판 CAGR | 차이 | gross | Sharpe | MDD | 회전/년 |",
         "|---|---|---|---|---|---|---|---|"]
    for label, bad, good in rows:
        L.append(f"| {label} | {bad['cagr']:.1f}% | **{good['cagr']:.1f}%** | "
                 f"{good['cagr']-bad['cagr']:+.1f}%p | {good['gross_cagr']:.1f}% | "
                 f"{good['sharpe']:.2f} | {good['mdd']:.1f}% | {good['turn']:.1f}x |")
    if kospi:
        L.append(f"| KOSPI 지수(PR) | — | {kospi['cagr']:.1f}% | — | — | "
                 f"{kospi['sharpe']:.2f} | {kospi['mdd']:.1f}% | — |")
    L += ["", "## 판정", ""]
    for label, bad, good in rows:
        if label.startswith("EW 대조군"):
            continue
        vs = good["cagr"] - ew["cagr"]
        L.append(f"- **{label}** — EW 대조군 대비 {vs:+.1f}%p "
                 f"({'초과' if vs > 0 else '미달'})")
    L += ["", "> ⚠️ 검증용 · 실현손익 아님 · 투자자문 아님 · 책임 본인"]
    out = a.out if os.path.isabs(a.out) else os.path.join(ROOT, a.out)
    open(out, "w", encoding="utf-8").write("\n".join(L))
    print(f"\n  저장: {os.path.relpath(out, ROOT)}")
    print("  ⚠️ 검증용 · 실현손익 아님 · 투자자문 아님")
    return 0


if __name__ == "__main__":
    sys.exit(main())
