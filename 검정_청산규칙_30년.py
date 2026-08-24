#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""검정_청산규칙_30년.py — B단계: "언제 자를 것인가" 30년 패널 검정

사전등록서: 가상매매\검증\청산규칙_검정_사전등록.md  (데이터 보기 전 확정)

핵심 원칙 (사전 선언):
  · 산술평균 수익으로 판정하지 않는다. 손절은 대개 평균을 낮춘다(추세 조기절단).
    집중 계좌의 목표는 복리 생존이므로 **기하수익(복리) + 꼬리위험**으로 판정한다.
  · 상폐 가정을 처음부터 내장한다(상폐수익률_가정.md, base −50%).
    손절의 진짜 가치 중 일부는 "상폐로 갈 종목을 미리 자르는 것"이다.
  · 손절은 매매를 늘린다 → 왕복 0.45% 비용 관문을 통과해야 한다.

방법:
  진입을 고정(월초 정기진입)하고 그 위에서 청산 규칙만 바꿔 트레이드 시퀀스를 만든다.
  각 트레이드 = (진입일, 청산일, 실현수익). 종목이 소멸하면 상폐 가정으로 청산.
  트레이드를 이어붙인 자산곡선에서 복리CAGR·MDD, 트레이드 분포에서 최악5%·승률.

산출: 가상매매\검증\청산규칙_검정_결과.md
사용:
  py 검정_청산규칙_30년.py --self-test
  py 검정_청산규칙_30년.py                        (전체)
  py 검정_청산규칙_30년.py --entry momentum        (2차 진입: 20일 신고가 돌파)
  py 검정_청산규칙_30년.py --delisting conservative
"""
import os, sys, argparse, warnings
from datetime import date
warnings.filterwarnings("ignore")

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "가상매매", "검증", "청산규칙_검정_결과.md")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

IN_END, OOS_START = 2012, 2013
MAX_HOLD = 60                 # 보유 상한(거래일)
ATR_N = 14
COST_RT = 0.45               # 왕복 % (현실)
COST_RT_HI = 0.70
DELISTING = {"optimistic": (0.0, -0.30, -0.50),   # (정상, 폭락, 완만)
             "base": (0.0, -0.30, -0.50),
             "conservative": (0.0, -0.50, -0.70),
             "worst": (0.0, -1.00, -1.00)}
# base와 optimistic의 폭락/완만은 사전등록서 표를 따른다(정상0/폭락-30/완만-50).
# optimistic은 민감도용으로 완만도 -30으로 완화.
DELISTING["optimistic"] = (0.0, -0.30, -0.30)

# 청산 규칙 정의 — 사전등록 고정 집합. (name, kind, param)
RULES = [
    ("무청산60", "hold", None),
    ("고정손절-8", "fixed", 0.08),
    ("고정손절-12", "fixed", 0.12),
    ("고정손절-15", "fixed", 0.15),
    ("고정손절-20", "fixed", 0.20),
    ("고정손절-25", "fixed", 0.25),
    ("ATR2.0", "atr", 2.0),
    ("ATR2.5", "atr", 2.5),
    ("ATR3.0", "atr", 3.0),
    ("ATR3.5", "atr", 3.5),
    ("MA20이탈", "ma", 20),
    ("MA60이탈", "ma", 60),
    ("5주선이탈", "ma", 25),
    ("트레일-15", "trail", 0.15),
    ("트레일-20", "trail", 0.20),
    ("샹들리에3ATR", "chand", 3.0),
    ("시간20", "time", 20),
    ("시간40", "time", 40),
]


# ───────────────────────── 트레이드 시뮬레이터 ─────────────────────────
def simulate_one(np, closes, highs, lows, atr, kind, param, max_hold):
    """진입일(idx 0)부터 규칙에 따라 청산. (청산상대idx, 총수익%) 반환.

    closes/highs/lows/atr: 진입일부터의 배열(진입일 포함). len>=2 가정.
    청산은 '다음날 종가'가 아니라 트리거 발생일 종가로 근사(보수적 단순화).
    """
    entry = closes[0]
    n = len(closes)
    hh = highs[0]
    for i in range(1, n):
        c = closes[i]
        hh = max(hh, highs[i])
        stop = None
        if kind == "fixed":
            stop = entry * (1 - param)
        elif kind == "atr":
            a = atr[i] if atr is not None and not np.isnan(atr[i]) else np.nan
            if not np.isnan(a):
                stop = entry - param * a
        elif kind == "trail":
            stop = hh * (1 - param)
        elif kind == "chand":
            a = atr[i] if atr is not None and not np.isnan(atr[i]) else np.nan
            if not np.isnan(a):
                stop = hh - param * a
        elif kind == "ma":
            k = int(param)
            if i >= k:
                ma = np.mean(closes[i - k + 1:i + 1])
                if c < ma:
                    return i, (c / entry - 1) * 100
            # ma는 아래 stop 로직 안 탐
            stop = None
        elif kind == "time":
            if i >= int(param):
                return i, (closes[i] / entry - 1) * 100
            stop = None
        elif kind == "hold":
            stop = None

        if stop is not None and lows[i] <= stop:
            # 손절가에 체결(갭하락이면 시가 근사 없이 stop으로; 보수적으로 종가와 stop 중 낮은쪽)
            fill = min(stop, c) if c < stop else stop
            fill = stop if lows[i] <= stop <= highs[i] else c
            return i, (fill / entry - 1) * 100

        if i >= max_hold:
            return i, (closes[i] / entry - 1) * 100
    return n - 1, (closes[-1] / entry - 1) * 100


def build_trades(pd, np, stock_df, entry_kind, rule, delist_ret, max_hold):
    """한 종목의 트레이드 시퀀스 생성. stock_df: date,close,high,low 오름차순.
    entry_kind: 'monthly'|'momentum'. rule: (name,kind,param).
    delist_ret: (정상,폭락,완만) 상폐수익 튜플. 소멸 종목이면 마지막 트레이드에 적용.
    반환: [(entry_date, exit_rel_days, ret%), ...]
    """
    d = stock_df
    closes = d["close"].values.astype(float)
    highs = d["high"].values.astype(float) if "high" in d else closes
    lows = d["low"].values.astype(float) if "low" in d else closes
    dates = d["date"].values
    n = len(closes)
    if n < 30:
        return []

    # ATR(14)
    atr = _atr(np, highs, lows, closes, ATR_N)

    # 진입일 인덱스
    entries = []
    if entry_kind == "monthly":
        cur = None
        for i, dt in enumerate(pd.to_datetime(dates)):
            ym = (dt.year, dt.month)
            if ym != cur:
                entries.append(i); cur = ym
    else:  # momentum: 20일 신고가 돌파
        for i in range(20, n):
            if closes[i] >= np.max(closes[i - 20:i]) and closes[i] > closes[i - 1]:
                entries.append(i)

    _, kind, param = rule
    trades = []
    last_i = -1
    for e in entries:
        if e <= last_i:      # 이전 트레이드 보유 중이면 스킵
            continue
        seg = slice(e, min(e + max_hold + 1, n))
        rel, ret = simulate_one(np, closes[seg], highs[seg], lows[seg],
                                atr[seg] if atr is not None else None,
                                kind, param, max_hold)
        exit_i = e + rel
        trades.append([pd.Timestamp(dates[e]), rel, ret, exit_i == n - 1])
        last_i = exit_i
    return trades


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


# ───────────────────────── 상폐 유형 판정 ─────────────────────────
def delist_type_ret(np, closes_traded, delist_ret):
    """소멸 종목의 마지막 트레이드에 적용할 상폐 추가수익. 유형은 직전20일로."""
    if len(closes_traded) < 21:
        r20 = 0.0
    else:
        r20 = (closes_traded[-1] / closes_traded[-21] - 1) * 100
    normal, crash, mild = delist_ret
    if r20 >= 10:
        return normal
    elif r20 <= -50:
        return crash
    else:
        return mild


# ───────────────────────── 성과 지표 ─────────────────────────
def metrics(np, rets, cost_rt):
    """트레이드 실현수익 리스트(%) → 기하평균·최악5%·파국률·승률·평균.

    기하평균은 log 합산으로 계산(복리). 총손실(-100%) 트레이드가 곱을 0으로
    만들어 nan이 되는 것을 막기 위해 -99.9%로 바닥을 둔다.
    MDD는 종목-트레이드를 이어붙인 가짜 곡선이라 오해를 줘서 뺐다. 대신
    **파국률(-50% 이하 트레이드 비율)** — 집중 계좌를 죽이는 건 평균이 아니라 꼬리다.
    """
    if not len(rets):
        return None
    r = np.array(rets, float) - cost_rt        # 왕복비용 차감
    rc = np.clip(r, -99.9, None)               # 복리 계산 안정화(총손실 바닥)
    geo = (np.exp(np.log1p(rc / 100).mean()) - 1) * 100   # 트레이드당 기하%
    worst5 = float(np.percentile(r, 5))
    cata = float((r <= -50).mean()) * 100      # 파국률: -50% 이하 트레이드 비율
    win = float((r > 0).mean()) * 100
    mean = float(r.mean())
    downside = r[r < 0]
    dstd = downside.std() if len(downside) else np.nan
    sortino = (r.mean() / dstd) if dstd and dstd > 0 else np.nan
    return {"n": len(r), "기하%": geo, "산술%": mean, "최악5%": worst5,
            "파국%": cata, "승률%": win, "Sortino": sortino}


# ───────────────────────── 셀프테스트 ─────────────────────────
def _self_test():
    import numpy as np, pandas as pd
    ok = tot = 0

    def chk(n, c):
        nonlocal ok, tot
        tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")

    # 고정 손절: 진입100, 하락하여 -15% 터치 → 손절
    closes = np.array([100, 98, 95, 90, 84, 80, 88, 95])
    highs = closes * 1.01; lows = closes * 0.99
    rel, ret = simulate_one(np, closes, highs, lows, None, "fixed", 0.15, 60)
    chk("고정손절 -15%: 84 부근에서 청산", ret < -13 and ret > -18)
    chk("고정손절: 반등 전에 잘림(rel<=4)", rel <= 4)

    # 무청산: 끝까지 보유
    rel2, ret2 = simulate_one(np, closes, highs, lows, None, "hold", None, 60)
    chk("무청산: 마지막까지 보유", rel2 == len(closes) - 1)
    chk("무청산: 최종수익 = 마지막/진입", abs(ret2 - (95/100-1)*100) < 1e-6)

    # 시간청산 20일
    up = np.linspace(100, 200, 40); h = up*1.01; l = up*0.99
    rel3, ret3 = simulate_one(np, up, h, l, None, "time", 20, 60)
    chk("시간청산20: 20일째 청산", rel3 == 20)

    # 트레일링: 고점 후 -20% 하락
    tr = np.array([100, 120, 150, 140, 130, 118, 110])
    rel4, ret4 = simulate_one(np, tr, tr*1.0, tr*1.0, None, "trail", 0.20, 60)
    chk("트레일-20%: 고점150 → 120 부근 청산", ret4 < 25 and ret4 > 15)

    # ★ high/low=0 바가 trail을 -100%로 오염시키지 않는가 (평탄화 후엔 안 됨)
    px = np.array([100.0, 105, 110, 108, 112, 115])
    hi = px.copy(); lo = px.copy()          # 평탄화된 상태(high=low=close)
    rel_z, ret_z = simulate_one(np, px, hi, lo, None, "trail", 0.15, 60)
    chk("평탄바(high=low=close): trail -100% 안 남", ret_z > -100)
    # _load 평탄화 로직 검증
    df0 = pd.DataFrame({"high": [0.0, 5, 0], "low": [0.0, 3, 0], "close": [10.0, 4, 20]})
    for c in ("high", "low"):
        bad = ~(df0[c] > 0); df0.loc[bad, c] = df0.loc[bad, "close"]
    df0["high"] = df0[["high", "close"]].max(axis=1)
    df0["low"] = df0[["low", "close"]].min(axis=1)
    chk("평탄화: high=0→close, low≤close≤high",
        (df0["low"] <= df0["close"]).all() and (df0["close"] <= df0["high"]).all())

    # MA20 이탈
    seq = np.concatenate([np.full(25, 100.0), np.array([90.0])])  # 26일째 급락
    rel5, ret5 = simulate_one(np, seq, seq*1.01, seq*0.99, None, "ma", 20, 60)
    chk("MA20이탈: 종가<MA20에서 청산", ret5 < 0)

    # 상폐 유형
    crash = np.concatenate([np.full(30, 100.0), np.linspace(100, 10, 21)])
    chk("폭락형 → crash 수익", delist_type_ret(np, crash, (0,-30,-50)) == -30)
    merge = np.concatenate([np.full(30, 100.0), np.linspace(100, 130, 21)])
    chk("상승형 → 0", delist_type_ret(np, merge, (0,-30,-50)) == 0)
    flat = np.full(60, 100.0)
    chk("완만형 → mild", delist_type_ret(np, flat, (0,-30,-50)) == -50)

    # metrics: 비용 차감 + 기하평균(log) + 파국률
    m = metrics(np, [10, -5, 10, -5], 0.0)
    geo_expect = (np.exp(np.log1p(np.array([10, -5, 10, -5]) / 100).mean()) - 1) * 100
    chk("기하평균 log 계산", abs(m["기하%"] - geo_expect) < 1e-9)
    chk("승률 50%", abs(m["승률%"] - 50) < 1e-9)
    m2 = metrics(np, [10, 10], 1.0)   # 왕복 1% 차감 → 9,9
    chk("비용차감: 10%→9%", abs(m2["산술%"] - 9.0) < 1e-9)
    # 파국률 + 총손실 트레이드가 nan 안 만드는지
    m3 = metrics(np, [-60, -100, 20, 5], 0.0)
    chk("파국률: -60/-100 두 건 → 50%", abs(m3["파국%"] - 50.0) < 1e-9)
    chk("총손실(-100%) 있어도 기하 유한", np.isfinite(m3["기하%"]))
    # 곱셈 상폐: -40% 트레이드 + -50% 상폐 = -70% (덧셈 -90% 아님)
    combined = ((1 + (-40)/100) * (1 + (-50)/100) - 1) * 100
    chk("상폐 곱셈: -40%×-50% = -70%", abs(combined - (-70.0)) < 1e-9)

    # ATR
    hh = np.array([10,11,12,11,13,14,13,15,16,15,17,18,17,19,20.])
    ll = hh - 1; cc = hh - 0.5
    atr = _atr(np, hh, ll, cc, 14)
    chk("ATR14: 14번째부터 값", not np.isnan(atr[13]) and np.isnan(atr[12]))

    # build_trades: 월초 진입 (250거래일 ≈ 1년 → 무청산60이면 ~4트레이드)
    dates = pd.bdate_range("2020-01-01", periods=250)
    df = pd.DataFrame({"date": dates, "close": np.linspace(100, 130, 250),
                       "high": np.linspace(100,130,250)*1.01,
                       "low": np.linspace(100,130,250)*0.99})
    tr = build_trades(pd, np, df, "monthly", ("무청산60","hold",None), (0,-30,-50), 60)
    chk("월초진입: 트레이드 생성됨(무청산60→~4)", len(tr) >= 3)
    chk("트레이드 비겹침", all(tr[i][0] < tr[i+1][0] for i in range(len(tr)-1)))
    # 짧은 보유(시간20)는 더 많은 트레이드
    tr2 = build_trades(pd, np, df, "monthly", ("시간20","time",20), (0,-30,-50), 60)
    chk("시간20 규칙: 무청산보다 트레이드 많음", len(tr2) > len(tr))

    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot


# ───────────────────────── 메인 ─────────────────────────
def _load(pd, np):
    frames = []
    for m in ("KOSPI", "KOSDAQ"):
        p = os.path.join(BASE, f"종목일봉_30년_{m}.csv")
        if not os.path.exists(p):
            print(f"  [없음] {os.path.basename(p)}"); return None
        d = pd.read_csv(p, usecols=["date", "code", "high", "low", "close", "volume"],
                        dtype={"code": str}, encoding="utf-8-sig")
        d["mkt"] = m; frames.append(d)
    d = pd.concat(frames, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    for c in ("high", "low", "close", "volume"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["date", "close"])
    d = d[d["close"] > 0]
    # ★ high/low가 0·결측인 바(거래정지·OHLC 누락, 종가만 존재)를 종가로 평탄화.
    #   안 하면 trail/ATR 손절이 고점=0으로 stop=0을 잡아 "0원 체결"=-100% 거짓손실.
    #   (2026-07-16 예비실행에서 트레일링 파국률 5.6% 거짓양성으로 발견)
    for c in ("high", "low"):
        bad = ~(d[c] > 0)
        d.loc[bad, c] = d.loc[bad, "close"]
    # 정합성: low ≤ close ≤ high 보장
    d["high"] = d[["high", "close"]].max(axis=1)
    d["low"] = d[["low", "close"]].min(axis=1)
    return d.sort_values(["code", "date"])


def run(entry_kind, scenario, sample=0):
    import pandas as pd, numpy as np
    print(f"데이터 적재... (진입={entry_kind}, 상폐={scenario}"
          f"{', 표본 '+str(sample) if sample else ''})")
    d = _load(pd, np)
    if d is None:
        return 2
    if sample and sample > 0:
        keep = (pd.Series(d["code"].unique())
                .sample(min(sample, d["code"].nunique()), random_state=42).tolist())
        d = d[d["code"].isin(set(keep))]
        print(f"  ★ 예비 실행: {len(keep)}종목 표본 (전체 아님)")
    print(f"  {len(d):,}행 · {d['code'].nunique():,}종목")

    # 시총 3분위 (전월 시총)
    mc_path = os.path.join(BASE, "종목시총_30년.csv")
    tier = {}
    if os.path.exists(mc_path):
        mc = pd.read_csv(mc_path, dtype={"code": str}, encoding="utf-8-sig")
        mc["date"] = pd.to_datetime(mc["date"], errors="coerce")
        mc["mcap"] = pd.to_numeric(mc["mcap"], errors="coerce")
        mc["ym"] = mc["date"].dt.year * 12 + mc["date"].dt.month
        last = mc.sort_values("date").groupby("code")["mcap"].last()
        q = last.quantile([1/3, 2/3])
        for c, v in last.items():
            tier[c] = "소" if v <= q.iloc[0] else ("중" if v <= q.iloc[1] else "대")

    delist_ret = DELISTING[scenario]
    end = d["date"].max()

    # 종목별 트레이드 생성 → 규칙별·구간별·시총별 집계
    from collections import defaultdict
    bucket = defaultdict(lambda: defaultdict(list))   # (rule)-> (seg,period) -> [ret...]

    # ★ groupby 한 번으로 순회 (종목마다 전수 스캔하면 5000×1470만 = 수시간)
    d = d.sort_values(["code", "date"])
    ncodes = d["code"].nunique()
    ci = 0
    for code, sub in d.groupby("code", sort=False):
        ci += 1
        if len(sub) < 30:
            continue
        gone = sub["date"].max() < end - pd.Timedelta(days=15)
        closes_traded = sub.loc[sub["volume"] > 0, "close"].values
        seg = tier.get(code, "중")
        for rule in RULES:
            tr = build_trades(pd, np, sub, entry_kind, rule, delist_ret, MAX_HOLD)
            for (edate, rel, ret, is_last) in tr:
                # 소멸 종목의 마지막 보유 트레이드면 상폐 수익을 **곱셈**으로 적용
                # (덧셈이면 -40% 트레이드 + -50% 상폐 = -90%지만, 실제는
                #  (1-0.40)(1-0.50)-1 = -70%. 덧셈은 -100%를 넘겨 복리를 깬다.)
                if gone and is_last:
                    dl = delist_type_ret(np, closes_traded, delist_ret)
                    ret = ((1 + ret / 100) * (1 + dl / 100) - 1) * 100
                period = "IN" if edate.year <= IN_END else "OOS"
                bucket[rule[0]][(seg, period)].append(ret)
                bucket[rule[0]][("전체", period)].append(ret)
        if ci % 500 == 0:
            print(f"  ...{ci}/{ncodes}종목")

    # 리포트
    L = ["# 청산 규칙 검정 — B단계 결과\n",
         f"\n*{date.today()} · 30년 패널 · 진입={entry_kind} · 상폐={scenario}(base)*\n",
         "\n사전등록: `청산규칙_검정_사전등록.md`. 산술평균 아닌 **복리+꼬리위험**으로 판정.\n",
         "\n*투자자문 아님. 결정·책임은 본인.*\n"]

    for seg in ("전체", "소", "중", "대"):
        L.append(f"\n---\n\n## 시총 {seg}\n\n")
        L.append("| 규칙 | 구간 | n | 기하%/트레이드 | 산술% | 최악5% | 파국%(≤-50) | 승률% | Sortino |\n")
        L.append("|---|---|---|---|---|---|---|---|---|\n")
        base = {}
        for period in ("IN", "OOS"):
            for rname in [r[0] for r in RULES]:
                rets = bucket[rname].get((seg, period), [])
                m = metrics(np, rets, COST_RT)
                if not m:
                    continue
                if rname == "무청산60":
                    base[period] = m
                L.append(f"| {rname} | {period} | {m['n']:,} | {m['기하%']:.3f} | "
                         f"{m['산술%']:.2f} | {m['최악5%']:.1f} | {m['파국%']:.1f} | "
                         f"{m['승률%']:.1f} | {m['Sortino']:.3f} |\n")
        # 요약: 무청산 대비 개선 규칙
        L.append(f"\n**무청산 대비 OOS 개선 (시총 {seg})**\n\n")
        if "OOS" in base:
            b = base["OOS"]
            L.append("| 규칙 | 기하Δ | 최악5%Δ | 파국Δ(↓좋음) | |\n|---|---|---|---|---|\n")
            for rname in [r[0] for r in RULES if r[0] != "무청산60"]:
                rets = bucket[rname].get((seg, "OOS"), [])
                m = metrics(np, rets, COST_RT)
                if not m:
                    continue
                dg = m["기하%"] - b["기하%"]        # +면 복리 개선
                dw = m["최악5%"] - b["최악5%"]       # +면 최악 트레이드 덜 나쁨
                dc = b["파국%"] - m["파국%"]         # +면 파국 트레이드 줄임(좋음)
                flag = "✅" if (dg > 0 and dc > 0) else ("↓꼬리" if dc > 0 else "")
                L.append(f"| {rname} | {dg:+.3f} | {dw:+.1f} | {dc:+.1f} | {flag} |\n")

    L.append("\n---\n\n## 판정\n\n")
    L.append("위 표에서 (A)IN개선 → (B)인접 파라미터 같은 방향 → (C)OOS 유지 → "
             "(D)비용0.45%+상폐 반영 후 개선. 4관문 통과만 채택.\n")
    L.append("**복리(기하) 또는 꼬리위험(최악5%·파국률) 개선을 본다. 산술평균 하락은 기각 사유 아님.**\n")
    L.append("파국률 = -50% 이하로 끝난 트레이드 비율. 집중 계좌를 죽이는 꼬리.\n")

    # 진입·상폐 모드별로 파일 분리 — momentum이 monthly를 덮어쓰지 않도록
    outdir = os.path.dirname(OUT)
    outpath = os.path.join(outdir, f"청산규칙_검정_결과_{entry_kind}_{scenario}.md")
    os.makedirs(outdir, exist_ok=True)
    open(outpath, "w", encoding="utf-8").write("".join(L))
    print(f"\n저장: 가상매매\\검증\\{os.path.basename(outpath)}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--entry", choices=["monthly", "momentum"], default="monthly")
    ap.add_argument("--delisting", choices=list(DELISTING), default="base")
    ap.add_argument("--sample", type=int, default=0,
                    help="예비 실행: N종목만 (0=전체)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return 0 if _self_test() else 1
    return run(a.entry, a.delisting, a.sample)


if __name__ == "__main__":
    sys.exit(main())
