#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""검정_고변동성_청산_30년.py — ① 고변동성 매매를 하드 스톱으로 살릴 수 있나

사전등록서: 가상매매\검증\고변동성_청산_상호작용_사전등록.md (데이터 보기 전)

질문: C에서 저변동성이 이겼다. 고변동성 롱온리는 소형에서 마이너스였다.
      그런데 진우님은 고변동성 성장주(반도체 장비주)를 매매한다.
      B에서 하드 스톱은 파국을 크게 줄였다.
      → **고변동성 종목에 스톱을 붙이면 살아나는가?**

방법:
  · 매월 말 60일 변동성으로 5분위. Q5=고변동성(진우 구간), Q1=저변동성.
  · 고변동성 Q5 종목을 월 보유하되, 청산 규칙을 바꿔 비교:
      무청산 / 트레일-15 / 고정-8 / 샹들리에3ATR   (B에서 채택된 것만)
  · 상폐 base·비용 0.45% 내장. IN 1996-2012 / OOS 2013-2026 봉인. 시총 소·중·대.
  · 비교 기준: Q5 무청산, 그리고 저변동성 Q1 무청산.

지표: 복리(기하)·최악5%·파국률(≤-50%)·승률.  (B와 동일 관점)

산출: 가상매매\검증\고변동성_청산_결과_{scenario}.md
사용:
  py 검정_고변동성_청산_30년.py --self-test
  py 검정_고변동성_청산_30년.py [--sample N] [--delisting conservative] [--cost 0.70]
"""
import os, sys, argparse, warnings
from datetime import date
warnings.filterwarnings("ignore")

BASE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(BASE, "가상매매", "검증")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

IN_END, OOS_START = 2012, 2013
NQ = 5
ATR_N = 14
MIN_PRICE = 1000
MIN_ADV = 5e8
COST_RT_DEFAULT = 0.45
DELISTING = {"base": (0.0, -0.30, -0.50), "conservative": (0.0, -0.50, -0.70),
             "optimistic": (0.0, -0.30, -0.30), "worst": (0.0, -1.00, -1.00)}
# 청산 규칙 — B에서 채택된 것만. (이름, kind, param)
STOPS = [("무청산", "hold", None), ("트레일-15", "trail", 0.15),
         ("고정-8", "fixed", 0.08), ("샹들리에3ATR", "chand", 3.0)]


# ───────── B에서 검증된 함수들 (인라인, 마운트 불안정 대비) ─────────
def _atr(np, high, low, close, n):
    m = len(close)
    if m < 2:
        return None
    tr = np.empty(m); tr[0] = high[0] - low[0]
    for i in range(1, m):
        tr[i] = max(high[i] - low[i], abs(high[i] - close[i - 1]),
                    abs(low[i] - close[i - 1]))
    atr = np.full(m, np.nan)
    if m >= n:
        atr[n - 1] = np.mean(tr[:n])
        for i in range(n, m):
            atr[i] = (atr[i - 1] * (n - 1) + tr[i]) / n
    return atr


def simulate_one(np, closes, highs, lows, atr, kind, param, max_hold):
    """진입일(0)부터 규칙에 따라 청산. (상대idx, 수익%)."""
    entry = closes[0]; n = len(closes); hh = highs[0]
    for i in range(1, n):
        c = closes[i]; hh = max(hh, highs[i]); stop = None
        if kind == "fixed":
            stop = entry * (1 - param)
        elif kind == "trail":
            stop = hh * (1 - param)
        elif kind == "chand":
            a = atr[i] if atr is not None and not np.isnan(atr[i]) else np.nan
            if not np.isnan(a):
                stop = hh - param * a
        elif kind == "hold":
            stop = None
        if stop is not None and lows[i] <= stop:
            fill = stop if lows[i] <= stop <= highs[i] else c
            return i, (fill / entry - 1) * 100
        if i >= max_hold:
            return i, (closes[i] / entry - 1) * 100
    return n - 1, (closes[-1] / entry - 1) * 100


def delist_type_ret(np, closes_traded, delist_ret):
    if len(closes_traded) < 21:
        r20 = 0.0
    else:
        r20 = (closes_traded[-1] / closes_traded[-21] - 1) * 100
    normal, crash, mild = delist_ret
    return normal if r20 >= 10 else (crash if r20 <= -50 else mild)


def metrics(np, rets, cost_rt):
    if not len(rets):
        return None
    r = np.array(rets, float) - cost_rt
    rc = np.clip(r, -99.9, None)
    geo = (np.exp(np.log1p(rc / 100).mean()) - 1) * 100
    return {"n": len(r), "기하%": geo, "산술%": float(r.mean()),
            "최악5%": float(np.percentile(r, 5)),
            "파국%": float((r <= -50).mean()) * 100,
            "승률%": float((r > 0).mean()) * 100}


# ───────────────────── 데이터 로드 (B의 OHLC 평탄화 포함) ─────────────────────
def _load_daily(pd, np):
    frames = []
    for m in ("KOSPI", "KOSDAQ"):
        p = os.path.join(BASE, f"종목일봉_30년_{m}.csv")
        if not os.path.exists(p):
            print(f"  [없음] {os.path.basename(p)}"); return None
        d = pd.read_csv(p, usecols=["date", "code", "high", "low", "close", "volume"],
                        dtype={"code": str}, encoding="utf-8-sig")
        frames.append(d)
    d = pd.concat(frames, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    for c in ("high", "low", "close", "volume"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["date", "close"])
    d = d[d["close"] > 0]
    for c in ("high", "low"):        # high/low=0 바 → 종가 평탄화 (B 발견)
        bad = ~(d[c] > 0)
        d.loc[bad, c] = d.loc[bad, "close"]
    d["high"] = d[["high", "close"]].max(axis=1)
    d["low"] = d[["low", "close"]].min(axis=1)
    return d.sort_values(["code", "date"])


# ───────────────────── 월별 변동성 분위 배정 ─────────────────────
def assign_quintiles(pd, np, d, tier_map):
    """일봉 → 각 (code, 월말)에 변동성 분위(전체/시총별). vol60·거래필터 반영.
    반환: DataFrame[code, ym, me_idx(그 종목 일봉 내 인덱스), q_전체, q_소, q_중, q_대]"""
    d = d.copy()
    d["ret"] = d.groupby("code", sort=False)["close"].pct_change()
    d["val"] = d["close"] * d["volume"]
    g = d.groupby("code", sort=False)
    d["vol60"] = g["ret"].transform(lambda s: s.rolling(60, min_periods=40).std())
    d["adv20"] = g["val"].transform(lambda s: s.rolling(20, min_periods=10).mean())
    d["ym"] = d["date"].dt.year * 12 + (d["date"].dt.month - 1)
    d["ipos"] = g.cumcount()                    # 종목 내 일봉 인덱스

    # 월말 스냅샷
    me = d.groupby(["code", "ym"]).tail(1).copy()
    me = me[(me["close"] >= MIN_PRICE) & (me["adv20"] >= MIN_ADV)]
    me = me.dropna(subset=["vol60"])
    me["tier"] = me["code"].map(tier_map).fillna("중")

    # 분위: 전체 및 시총별로, 각 월 안에서
    def q_within(sub):
        try:
            return pd.qcut(sub.rank(method="first"), NQ, labels=list(range(1, NQ + 1)))
        except Exception:
            return pd.Series(np.nan, index=sub.index)
    me["q_all"] = me.groupby("ym")["vol60"].transform(q_within)
    me["q_seg"] = me.groupby(["ym", "tier"])["vol60"].transform(q_within)
    return me[["code", "ym", "ipos", "tier", "q_all", "q_seg"]]


# ───────────────────── 홀딩 시뮬 (월말 진입 → 다음 월말/스톱) ─────────────────────
def run_holds(pd, np, d, qmap, delist_ret, cost_rt):
    """Q5(고변동)·Q1(저변동) 종목을 월 보유, 청산 규칙별 실현수익 수집."""
    from collections import defaultdict
    # bucket[(seg, group, rule, period)] = [ret...]   group∈{"고Q5","저Q1"}
    bucket = defaultdict(list)
    d = d.sort_values(["code", "date"]).reset_index(drop=True)
    # 종목별 일봉 배열 준비
    end = d["date"].max()
    qmap = qmap.sort_values(["code", "ym"])
    q_by_code = {c: sub for c, sub in qmap.groupby("code", sort=False)}

    for code, sub in d.groupby("code", sort=False):
        qq = q_by_code.get(code)
        if qq is None or len(sub) < 80:
            continue
        closes = sub["close"].values.astype(float)
        highs = sub["high"].values.astype(float)
        lows = sub["low"].values.astype(float)
        vols = sub["volume"].values.astype(float)
        atr = _atr(np, highs, lows, closes, ATR_N)
        n = len(closes)
        gone = sub["date"].max() < end - pd.Timedelta(days=15)
        closes_traded = closes[vols > 0]
        # 월말 인덱스 리스트 (종목 내 위치)
        me_rows = qq.to_dict("records")
        # 각 월말 → 다음 월말까지 보유
        ipos_list = [r["ipos"] for r in me_rows]
        for k, r in enumerate(me_rows):
            i0 = int(r["ipos"])
            if i0 >= n - 1:
                continue
            i1 = int(ipos_list[k + 1]) if k + 1 < len(ipos_list) else min(i0 + 23, n - 1)
            i1 = min(i1, n - 1)
            if i1 <= i0:
                continue
            seg = r["tier"]
            for qcol, scope in (("q_all", "전체"), ("q_seg", seg)):
                qv = r[qcol]
                if pd.isna(qv):
                    continue
                qv = int(qv)
                if qv == NQ:
                    group = "고Q5"
                elif qv == 1:
                    group = "저Q1"
                else:
                    continue
                win = slice(i0, i1 + 1)
                cW, hW, lW = closes[win], highs[win], lows[win]
                aW = atr[win] if atr is not None else None
                mh = i1 - i0
                period = "IN" if (sub["date"].iloc[i0].year <= IN_END) else "OOS"
                for rname, kind, param in STOPS:
                    rel, ret = simulate_one(np, cW, hW, lW, aW, kind, param, mh)
                    is_last = (i0 + rel) >= n - 1
                    if gone and is_last:
                        dl = delist_type_ret(np, closes_traded, delist_ret)
                        ret = ((1 + ret / 100) * (1 + dl / 100) - 1) * 100
                    bucket[(scope, group, rname, period)].append(ret)
    return bucket


def _tier_map(pd, np):
    mp = os.path.join(BASE, "종목시총_30년.csv")
    if not os.path.exists(mp):
        return {}
    mc = pd.read_csv(mp, dtype={"code": str}, encoding="utf-8-sig")
    mc["mcap"] = pd.to_numeric(mc["mcap"], errors="coerce")
    last = mc.dropna().groupby("code")["mcap"].last()
    if not len(last):
        return {}
    q = last.quantile([1/3, 2/3])
    return {c: ("소" if v <= q.iloc[0] else ("중" if v <= q.iloc[1] else "대"))
            for c, v in last.items()}


# ───────────────────────── 셀프테스트 ─────────────────────────
def _self_test():
    import numpy as np, pandas as pd
    ok = tot = 0

    def chk(n, c):
        nonlocal ok, tot
        tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")

    # simulate_one: 트레일-15
    tr = np.array([100, 120, 150, 140, 130, 118, 110.])
    rel, ret = simulate_one(np, tr, tr, tr, None, "trail", 0.20, 60)
    chk("트레일-20%: 고점150→120 부근", 15 < ret < 25)
    # 고정-8
    seq = np.array([100, 98, 95, 90, 88.])
    rel2, ret2 = simulate_one(np, seq, seq*1.01, seq*0.99, None, "fixed", 0.08, 60)
    chk("고정-8%: -8% 부근 청산", -12 < ret2 < -6)
    # 무청산
    rel3, ret3 = simulate_one(np, seq, seq, seq, None, "hold", None, 60)
    chk("무청산: 끝까지", rel3 == len(seq)-1)

    # metrics 파국률
    m = metrics(np, [-60, -100, 20, 5], 0.0)
    chk("파국률 50%", abs(m["파국%"] - 50) < 1e-9)
    chk("총손실 있어도 기하 유한", np.isfinite(m["기하%"]))

    # 상폐 곱셈
    combined = ((1 + (-40)/100) * (1 + (-50)/100) - 1) * 100
    chk("상폐 곱셈 -40%x-50%=-70%", abs(combined - (-70)) < 1e-9)

    # 분위 배정 로직: 100종목, vol 오름차순 → Q5=고변동
    d = pd.DataFrame({"vol60": np.arange(100.0)})
    q = pd.qcut(d["vol60"].rank(method="first"), 5, labels=list(range(1,6)))
    chk("최고 변동성 → Q5", q.iloc[-1] == 5)
    chk("최저 변동성 → Q1", q.iloc[0] == 1)

    # ATR
    hh = np.arange(10, 30.0); ll = hh-1; cc = hh-0.5
    a = _atr(np, hh, ll, cc, 14)
    chk("ATR 14번째부터", not np.isnan(a[13]) and np.isnan(a[12]))

    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot


# ───────────────────────── 메인 ─────────────────────────
def run(sample, scenario, cost_rt):
    import pandas as pd, numpy as np
    print(f"데이터 적재... (상폐={scenario}, 비용={cost_rt}%"
          f"{', 표본 '+str(sample) if sample else ''})")
    d = _load_daily(pd, np)
    if d is None:
        return 2
    if sample and sample > 0:
        keep = (pd.Series(d["code"].unique())
                .sample(min(sample, d["code"].nunique()), random_state=42).tolist())
        d = d[d["code"].isin(set(keep))]
        print(f"  ★ 예비: {len(keep)}종목")
    print(f"  일봉 {len(d):,}행 · {d['code'].nunique():,}종목")

    tier_map = _tier_map(pd, np)
    print("변동성 분위 배정 중...")
    qmap = assign_quintiles(pd, np, d, tier_map)
    print(f"  월말 분위 {len(qmap):,}건")

    print("홀딩 시뮬 중... (월말 진입 → 스톱/다음월말)")
    bucket = run_holds(pd, np, d, qmap, DELISTING[scenario], cost_rt)

    L = ["# 고변동성 × 청산 상호작용 — ① 결과\n",
         f"\n*{date.today()} · 30년 패널 · 상폐 {scenario} · 비용 {cost_rt}%*\n",
         "\n사전등록: `고변동성_청산_상호작용_사전등록.md`. Q5=고변동성 · Q1=저변동성.\n",
         "\n질문: 고변동성 매매를 하드 스톱으로 살릴 수 있나. 복리+파국률로 판정.\n",
         "\n*투자자문 아님. 결정·책임은 본인.*\n"]

    for scope in ("전체", "소", "중", "대"):
        L.append(f"\n---\n\n## 시총 {scope}\n\n")
        L.append("| 그룹·청산 | 구간 | n | 기하% | 최악5% | 파국% | 승률% |\n")
        L.append("|---|---|---|---|---|---|---|\n")
        # 저변동성 Q1 무청산(비교 기준)
        for period in ("IN", "OOS"):
            for group, rname in [("저Q1", "무청산"),
                                 ("고Q5", "무청산"), ("고Q5", "트레일-15"),
                                 ("고Q5", "고정-8"), ("고Q5", "샹들리에3ATR")]:
                rets = bucket.get((scope, group, rname, period), [])
                m = metrics(np, rets, cost_rt)
                if not m:
                    continue
                tag = f"{'저변동Q1' if group=='저Q1' else '고변동Q5'}·{rname}"
                L.append(f"| {tag} | {period} | {m['n']:,} | {m['기하%']:.3f} | "
                         f"{m['최악5%']:.1f} | {m['파국%']:.1f} | {m['승률%']:.1f} |\n")

    L.append("\n---\n\n## 판정 (사전등록 관문)\n\n")
    L.append("(A) 고Q5에서 스톱이 무청산 대비 복리/파국 개선 · "
             "(B) 고Q5+최선스톱 절대 복리>0 · "
             "(C) 저Q1(무청산)을 이기는가 · (D) OOS 유지.\n")
    L.append("**(C)에서 저변동성을 못 이겨도 '고변동성이 낫다'고 재해석하지 않는다(사전 고정).**\n")

    outpath = os.path.join(OUTDIR, f"고변동성_청산_결과_{scenario}.md")
    os.makedirs(OUTDIR, exist_ok=True)
    open(outpath, "w", encoding="utf-8").write("".join(L))
    print(f"\n저장: 가상매매\\검증\\{os.path.basename(outpath)}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--delisting", choices=list(DELISTING), default="base")
    ap.add_argument("--cost", type=float, default=COST_RT_DEFAULT)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return 0 if _self_test() else 1
    return run(a.sample, a.delisting, a.cost)


if __name__ == "__main__":
    sys.exit(main())
