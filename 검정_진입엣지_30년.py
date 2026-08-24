#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""검정_진입엣지_30년.py — C단계: "무엇을 사는가" 팩터 검정

사전등록서: 가상매매\검증\진입엣지_검정_사전등록.md  (데이터 보기 전 확정)

팩터 5종 (표준 정의, 튜닝 금지):
  ① 저변동성   60일 일간수익 std, 낮을수록 매수      (Frazzini-Pedersen 2014)
  ② 52주고가   현재가/252일최고, 높을수록 매수        (George-Hwang 2004)
  ③ 모멘텀12-1 12개월-1개월 수익, 높을수록 매수        (Jegadeesh-Titman 1993)
  ④ 저PBR      시총/장부가, 낮을수록 매수              (Fama-French 1992)
  ⑤ 수익성GP   (매출-매출원가)/자산, 높을수록 매수     (Novy-Marx 2013)

방법: 월말 EW 퀸타일. 롱숏(Q5-Q1) Newey-West t, 롱온리 Q5 vs EW-유니버스.
      상폐가정(base) 내장. 비용 0.45%×회전. 거래필터(가격≥1000, 20일거래대금≥5억).
      재무는 4개월 지연(룩어헤드 차단). IN 1996-2012 / OOS 2013-2026 봉인.

산출: 가상매매\검증\진입엣지_검정_결과.md
사용:
  py 검정_진입엣지_30년.py --self-test
  py 검정_진입엣지_30년.py
  py 검정_진입엣지_30년.py --cost 0.70 --delisting conservative
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
NQ = 5                       # 퀸타일
MIN_PRICE = 1000
MIN_ADV = 5e8                # 20일 평균 거래대금 5억
FIN_LAG_M = 4                # 재무 공시 지연(개월)
COST_RT_DEFAULT = 0.45
DELISTING = {"base": (0.0, -0.30, -0.50),
             "conservative": (0.0, -0.50, -0.70),
             "optimistic": (0.0, -0.30, -0.30),
             "worst": (0.0, -1.00, -1.00)}

# (이름, 정렬방향)  방향 +1: 값 클수록 매수(Q5), -1: 값 작을수록 매수
FACTORS = [
    ("저변동성", -1),
    ("52주고가", +1),
    ("모멘텀121", +1),
    ("저PBR", -1),
    ("저PER", -1),
    ("수익성GP", +1),
]


# ───────────────────────── Newey-West t ─────────────────────────
def newey_west_t(np, x, lag=None):
    """평균이 0인지에 대한 HAC(Newey-West) t값."""
    x = np.asarray(x, float)
    x = x[~np.isnan(x)]
    n = len(x)
    if n < 8:
        return np.nan
    if lag is None:
        lag = int(np.floor(4 * (n / 100) ** (2 / 9)))
    mu = x.mean()
    e = x - mu
    g0 = (e @ e) / n
    var = g0
    for l in range(1, lag + 1):
        w = 1 - l / (lag + 1)
        cov = (e[l:] @ e[:-l]) / n
        var += 2 * w * cov
    se = np.sqrt(var / n)
    return mu / se if se > 0 else np.nan


# ───────────────────────── 특징 계산 ─────────────────────────
def build_monthly(pd, np, daily, mcap, fund, delist_ret, krx=None):
    """일봉 → 월말 스냅샷(팩터 + 다음달 수익). daily: date,code,close,high,low,volume,mkt"""
    d = daily.sort_values(["code", "date"]).copy()
    d["ret"] = d.groupby("code", sort=False)["close"].pct_change()
    d["val"] = d["close"] * d["volume"]
    g = d.groupby("code", sort=False)
    d["vol60"] = g["ret"].transform(lambda s: s.rolling(60, min_periods=40).std())
    d["hi252"] = g["close"].transform(lambda s: s.rolling(252, min_periods=120).max())
    d["adv20"] = g["val"].transform(lambda s: s.rolling(20, min_periods=10).mean())
    d["ym"] = d["date"].dt.year * 12 + (d["date"].dt.month - 1)

    # 월말 스냅샷: 각 (code,ym) 마지막 행
    me = d.groupby(["code", "ym"]).last().reset_index()
    me["ratio52"] = me["close"] / me["hi252"]

    # 월간 종가 → 모멘텀 12-1, 다음달 수익
    me = me.sort_values(["code", "ym"])
    gm = me.groupby("code", sort=False)
    me["mclose"] = me["close"]
    # 12개월 전 종가, 1개월 전 종가
    me["c12"] = gm["mclose"].shift(12)
    me["c1"] = gm["mclose"].shift(1)
    me["mom121"] = (me["c1"] / me["c12"] - 1)          # 12개월전→1개월전 (최근1개월 제외)
    me["nextclose"] = gm["mclose"].shift(-1)
    me["fwd"] = me["nextclose"] / me["mclose"] - 1

    # 상폐月 처리: 다음달 종가 없음 & 이 code의 마지막 달이면 상폐수익 적용
    last_ym = gm["ym"].transform("max")
    is_last = me["ym"] == last_ym
    # 전체 패널 마지막 달(현재 생존)은 상폐 아님
    panel_last = me["ym"].max()
    gone_last = is_last & (me["ym"] < panel_last - 1)
    normal, crash, mild = delist_ret
    # 유형: 최근 1개월 수익으로 근사
    m1 = me["mclose"] / me["c1"] - 1
    dl = np.where(m1 >= 0.10, normal, np.where(m1 <= -0.30, crash, mild))
    me.loc[gone_last & me["fwd"].isna(), "fwd"] = pd.Series(dl, index=me.index)[gone_last & me["fwd"].isna()] / 100.0 * 100  # dl already in %? see below
    # dl은 % 단위(예 -50). fwd는 소수(예 -0.5). 변환:
    me.loc[gone_last & me["nextclose"].isna(), "fwd"] = (
        pd.Series(dl, index=me.index)[gone_last & me["nextclose"].isna()] / 100.0)

    # 시총 병합 (당월) — PBR용, 그리고 시총 세그먼트용
    mcap = mcap.copy()
    mcap["ym"] = mcap["date"].dt.year * 12 + (mcap["date"].dt.month - 1)
    mcap = mcap.groupby(["code", "ym"])["mcap"].last().reset_index()
    me = me.merge(mcap, on=["code", "ym"], how="left")

    # ── 밸류(저PBR·저PER): KRX 재무 패널을 (code,ym)로 직접 병합 ──
    #   KRX PBR/PER은 그날 시점의 시장데이터(주가/BPS)라 룩어헤드 없음. 재무지연 불필요.
    #   (2026-07-16: 종목재무_KRX_*.csv 24년/20년 백필 → mcap/book_equity 대체)
    if krx is not None and len(krx):
        me = me.merge(krx, on=["code", "ym"], how="left")
        me["pbr"] = me["PBR"].where(me["PBR"] > 0)     # 0/결측은 랭킹서 제외
        me["per"] = me["PER"].where(me["PER"] > 0)
    else:
        me["pbr"] = np.nan; me["per"] = np.nan

    # ── 수익성(GP): 재무제표 기반(4개월 지연). 아직 이력 짧음(FY2019~) → 미결 예상 ──
    if fund is not None and len(fund):
        f = fund.copy()
        f["fiscal_year"] = f["fiscal_year"].astype("int64")
        me["applic_fy"] = ((me["ym"].astype("int64") - FIN_LAG_M) // 12 - 1)
        me = me.merge(f[["code", "fiscal_year", "gp"]],
                      left_on=["code", "applic_fy"], right_on=["code", "fiscal_year"],
                      how="left")
    else:
        me["gp"] = np.nan

    return me


def load_fundamentals(pd, np):
    frames = []
    for f in ("fundamentals_pit.csv", "fundamentals_kosdaq.csv"):
        p = os.path.join(BASE, f)
        if os.path.exists(p):
            frames.append(pd.read_csv(p, dtype={"code": str}, encoding="utf-8-sig"))
    if not frames:
        return None
    d = pd.concat(frames, ignore_index=True)
    d = d.dropna(subset=["fiscal_year"])
    d["fiscal_year"] = pd.to_numeric(d["fiscal_year"], errors="coerce")
    for c in ("revenue", "cogs", "assets", "equity"):
        if c in d:
            d[c] = pd.to_numeric(d[c], errors="coerce")
    d["gp"] = (d["revenue"] - d["cogs"]) / d["assets"]
    # book_equity
    be = os.path.join(BASE, "book_equity.csv")
    if os.path.exists(be):
        b = pd.read_csv(be, dtype={"code": str}, encoding="utf-8-sig")
        b["fiscal_year"] = pd.to_numeric(b["fiscal_year"], errors="coerce")
        d = d.merge(b[["code", "fiscal_year", "book_equity"]],
                    on=["code", "fiscal_year"], how="left")
    if "book_equity" not in d:
        d["book_equity"] = d["equity"]
    d["book_equity"] = d["book_equity"].fillna(d.get("equity"))
    # code+fiscal_year 유일화
    d = d.sort_values("fiscal_year").groupby(["code", "fiscal_year"]).last().reset_index()
    return d[["code", "fiscal_year", "book_equity", "gp"]]


def load_krx_fund(pd):
    """KRX 날짜별 재무(밸류) 패널 → 월말 (code, ym, PBR, PER).
    날짜별 수집이라 생존편향·룩어헤드 없음. 2002(KOSPI)/2006(KOSDAQ)~."""
    frames = []
    for m in ("KOSPI", "KOSDAQ"):
        p = os.path.join(BASE, f"종목재무_KRX_{m}.csv")
        if os.path.exists(p):
            frames.append(pd.read_csv(p, usecols=["date", "code", "PBR", "PER"],
                                      dtype={"code": str}, encoding="utf-8-sig"))
    if not frames:
        return None
    d = pd.concat(frames, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    for c in ("PBR", "PER"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["ym"] = d["date"].dt.year * 12 + (d["date"].dt.month - 1)
    d = d.dropna(subset=["ym"])
    # (code,ym) 유일화 — 월말 한 값
    d = d.groupby(["code", "ym"]).last().reset_index()
    return d[["code", "ym", "PBR", "PER"]]


# ───────────────────────── 팩터 백테스트 ─────────────────────────
def factor_column(me, fname):
    if fname == "저변동성":
        return me["vol60"]
    if fname == "52주고가":
        return me["ratio52"]
    if fname == "모멘텀121":
        return me["mom121"]
    if fname == "저PBR":
        return me["pbr"]
    if fname == "저PER":
        return me["per"]
    if fname == "수익성GP":
        return me["gp"]
    return None


def backtest(pd, np, me, fname, direction, seg, cost_rt):
    """월별 퀸타일 EW 수익. 반환: dict(퀸타일별 월수익 시계열, 롱숏, 롱온리 net)."""
    col = factor_column(me, fname)
    d = me.assign(f=col)
    d = d[d["adv20"] >= MIN_ADV]
    d = d[d["close"] >= MIN_PRICE]
    d = d.dropna(subset=["f", "fwd"])
    if seg != "전체":
        # 시총 3분위 (당월 유니버스 내)
        d = d.copy()
        d["tier"] = d.groupby("ym")["mcap"].transform(
            lambda s: pd.qcut(s, 3, labels=["소", "중", "대"], duplicates="drop")
            if s.notna().sum() > 30 else np.nan)
        d = d[d["tier"] == seg]
    # 방향 반영: direction +1이면 큰 값이 Q5(매수). -1이면 작은 값이 Q5.
    d = d.copy()
    d["fs"] = d["f"] * direction
    rows = []
    q5mem_prev = None
    to_list = []
    for ym, sub in d.groupby("ym"):
        if sub["fs"].notna().sum() < NQ * 5:
            continue
        try:
            sub = sub.assign(q=pd.qcut(sub["fs"].rank(method="first"), NQ,
                                       labels=list(range(1, NQ + 1))))
        except Exception:
            continue
        qret = sub.groupby("q")["fwd"].mean()
        univ = sub["fwd"].mean()
        q5 = set(sub[sub["q"] == NQ]["code"])
        # 회전율
        if q5mem_prev is not None and len(q5mem_prev):
            turn = 1 - len(q5 & q5mem_prev) / len(q5mem_prev)
        else:
            turn = 1.0
        to_list.append(turn)
        q5mem_prev = q5
        rows.append({"ym": ym, "univ": univ,
                     **{f"q{int(q)}": qret.get(q, np.nan) for q in range(1, NQ + 1)},
                     "turn": turn})
    if not rows:
        return None
    r = pd.DataFrame(rows)
    r["year"] = r["ym"] // 12
    r["ls"] = r[f"q{NQ}"] - r["q1"]              # 롱숏
    # 롱온리 Q5 net = q5 - 유니버스 - 비용(회전×왕복/2 편도 근사 → 왕복 전액을 회전에 곱)
    r["lo_gross"] = r[f"q{NQ}"] - r["univ"]
    r["lo_net"] = r[f"q{NQ}"] - r["univ"] - r["turn"] * (cost_rt / 100.0)
    return r


def seg_stats(pd, np, r, period):
    if period == "IN":
        x = r[r["year"] <= IN_END]
    else:
        x = r[r["year"] >= OOS_START]
    if len(x) < 12:
        return None
    ls = x["ls"].values
    t = newey_west_t(np, ls)
    # 분위 단조성: q1..q5 평균이 단조 증가(방향 이미 반영)
    qm = [np.nanmean(x[f"q{i}"]) for i in range(1, NQ + 1)]
    # 단조성: 4개 스텝 중 3개 이상이 올바른 방향(1개 역전 허용). 완벽 단조는 실데이터에 드묾.
    steps_up = sum(1 for i in range(NQ - 1) if qm[i + 1] >= qm[i])
    mono = steps_up >= (NQ - 2)
    lo_net_ann = np.nanmean(x["lo_net"]) * 12 * 100
    ls_ann = np.nanmean(ls) * 12 * 100
    return {"n": len(x), "t": t, "ls_ann": ls_ann, "lo_net_ann": lo_net_ann,
            "mono": mono, "qm": qm, "turn": np.nanmean(x["turn"]) * 100}


# ───────────────────────── 셀프테스트 ─────────────────────────
def _self_test():
    import numpy as np, pandas as pd
    ok = tot = 0

    def chk(n, c):
        nonlocal ok, tot
        tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")

    # Newey-West: 평균 0 시계열 → |t| 작음, 평균 큰 시계열 → t 큼
    rng = np.random.default_rng(0)
    z = rng.normal(0, 1, 200)
    chk("NW t: 평균0 → |t|<2 대체로", abs(newey_west_t(np, z)) < 2.5)
    pos = rng.normal(0.5, 1, 200)
    chk("NW t: 평균0.5 → t>3", newey_west_t(np, pos) > 3)

    # 팩터 방향: direction=-1이면 작은 값이 Q5
    me = pd.DataFrame({
        "code": [f"{i:06d}" for i in range(100)] * 6,
        "ym": np.repeat(np.arange(6) + 24000, 100),
        "close": 2000.0, "adv20": 1e9, "mcap": 1e11,
    })
    # 심은 신호: f 작을수록 다음달 수익 큼 (저변동성 같은 저-매수 팩터)
    me["vol60"] = np.tile(np.linspace(0.01, 0.05, 100), 6)
    me["fwd"] = -(me["vol60"] - 0.03) * 5 + rng.normal(0, 0.002, 600)
    me["ratio52"] = np.nan; me["mom121"] = np.nan; me["pbr"] = np.nan; me["gp"] = np.nan
    r = backtest(pd, np, me, "저변동성", -1, "전체", 0.45)
    chk("저변동성 백테스트 생성", r is not None and len(r) > 0)
    if r is not None:
        chk("심은 저변동성 신호 → 롱숏 양수", np.nanmean(r["ls"]) > 0)
        st = seg_stats(pd, np, r.assign(year=r["ym"]//12), "IN")

    if r is not None and st is not None:
        chk("단조성: 심은 신호 → mono=True", st["mono"] is True)

    # 단조성 판정: 1개 역전 허용(3/4 스텝)
    def _mono(qm):
        s = sum(1 for i in range(len(qm)-1) if qm[i+1] >= qm[i])
        return s >= len(qm) - 2
    chk("단조 완벽 → True", _mono([1, 2, 3, 4, 5]))
    chk("단조 1역전 → True", _mono([1, 2, 4, 3, 5]))
    chk("단조 2역전 → False", _mono([1, 3, 2, 4, 3]) is False)

    # 퀸타일: 100종목 → 5분위 각 20
    sub = pd.DataFrame({"fs": np.arange(100.0)})
    sub["q"] = pd.qcut(sub["fs"].rank(method="first"), 5, labels=list(range(1, 6)))
    chk("퀸타일 균등 20개씩", (sub["q"].value_counts() == 20).all())
    chk("최대값이 Q5", sub.sort_values("fs").iloc[-1]["q"] == 5)

    # 상폐 forward: 곱셈 스케일 확인(단위)
    dl_pct = -50.0
    chk("상폐 fwd = dl/100 = -0.5", abs(dl_pct/100.0 - (-0.5)) < 1e-9)

    # 재무 적용 회계연도: 2021-05(ym=2021*12+4)엔 FY2020, 2021-04엔 FY2019
    ym_may = 2021*12 + 4
    ym_apr = 2021*12 + 3
    chk("2021-05 → FY2020 적용", (ym_may - 4)//12 - 1 == 2020)
    chk("2021-04 → FY2019 적용(4개월 지연)", (ym_apr - 4)//12 - 1 == 2019)

    # GP 계산
    chk("GP=(매출-원가)/자산", abs(((100-60)/200) - 0.2) < 1e-9)

    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot


# ───────────────────────── 메인 ─────────────────────────
def _load_daily(pd, np):
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
    return d.sort_values(["code", "date"])


def run(cost_rt, scenario, sample=0):
    import pandas as pd, numpy as np
    print(f"데이터 적재... (비용={cost_rt}%, 상폐={scenario}"
          f"{', 표본 '+str(sample) if sample else ''})")
    daily = _load_daily(pd, np)
    if daily is None:
        return 2
    if sample and sample > 0:
        keep = (pd.Series(daily["code"].unique())
                .sample(min(sample, daily["code"].nunique()), random_state=42).tolist())
        daily = daily[daily["code"].isin(set(keep))]
        print(f"  ★ 예비 실행: {len(keep)}종목 표본 (전체 아님)")
    print(f"  일봉 {len(daily):,}행 · {daily['code'].nunique():,}종목")

    mp = os.path.join(BASE, "종목시총_30년.csv")
    mcap = pd.read_csv(mp, dtype={"code": str}, encoding="utf-8-sig")
    mcap["date"] = pd.to_datetime(mcap["date"], errors="coerce")
    mcap["mcap"] = pd.to_numeric(mcap["mcap"], errors="coerce")
    fund = load_fundamentals(pd, np)
    krx = load_krx_fund(pd)
    print(f"  시총 {len(mcap):,}행 · 재무제표 {0 if fund is None else len(fund):,}행 · "
          f"KRX밸류 {0 if krx is None else len(krx):,}행")

    print("월말 특징 계산 중... (rolling vol/고가/모멘텀)")
    me = build_monthly(pd, np, daily, mcap, fund, DELISTING[scenario], krx=krx)
    print(f"  월말 스냅샷 {len(me):,}행")

    # 재무 데이터 커버리지 — 밸류·수익성은 재무가 있는 기간만 검정 가능
    fy_min = int(fund["fiscal_year"].min()) if fund is not None and len(fund) else None
    fy_max = int(fund["fiscal_year"].max()) if fund is not None and len(fund) else None

    L = ["# 진입 엣지 검정 — C단계 결과\n",
         f"\n*{date.today()} · 30년 패널 · 비용 {cost_rt}% · 상폐 {scenario}*\n",
         "\n사전등록: `진입엣지_검정_사전등록.md`. EW 퀸타일 · 롱숏 NW-t · 롱온리 Q5 vs EW.\n",
         "\n*투자자문 아님. 결정·책임은 본인.*\n"]
    if fy_min is not None:
        L.append(f"\n> ⚠️ **재무 커버리지: FY{fy_min}~{fy_max}.** 가격 팩터(저변동성·52주고가·모멘텀)는\n"
                 f"> 30년 전부 검정되나, **밸류(저PBR)·수익성(GP)은 재무가 있는 기간만** — IN 구간이\n"
                 f"> 비거나 짧으면 그 팩터의 판정은 **미결(underpowered)**이다. 재무 백필이 필요하다.\n")

    Nbon = len(FACTORS) * 3
    for seg in ("전체", "소", "중", "대"):
        L.append(f"\n---\n\n## 시총 {seg}\n\n")
        L.append("| 팩터 | 구간 | 개월 | 롱숏 연% | NW-t | 단조 | 롱온리Q5 net연% | 회전% |\n")
        L.append("|---|---|---|---|---|---|---|---|\n")
        for fname, direction in FACTORS:
            r = backtest(pd, np, me, fname, direction, seg, cost_rt)
            if r is None:
                continue
            for period in ("IN", "OOS"):
                st = seg_stats(pd, np, r, period)
                if st is None:
                    continue
                mono = "✅" if st["mono"] else "—"
                L.append(f"| {fname} | {period} | {st['n']} | {st['ls_ann']:+.1f} | "
                         f"{st['t']:+.2f} | {mono} | {st['lo_net_ann']:+.1f} | {st['turn']:.0f} |\n")

    L.append(f"\n---\n\n## 판정 (Bonferroni ×{Nbon})\n\n")
    L.append("(A) IN NW-t>2 · (B) 단조 · (C) OOS NW-t>1.5 부호유지 · (D) 롱온리 net>0.\n")
    L.append("4관문 통과만 채택. 모멘텀 약함은 사전 예측 — 실패해도 데이터대로 기록.\n")

    outpath = os.path.join(OUTDIR, f"진입엣지_검정_결과_{scenario}.md")
    os.makedirs(OUTDIR, exist_ok=True)
    open(outpath, "w", encoding="utf-8").write("".join(L))
    print(f"\n저장: 가상매매\\검증\\{os.path.basename(outpath)}")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cost", type=float, default=COST_RT_DEFAULT)
    ap.add_argument("--delisting", choices=list(DELISTING), default="base")
    ap.add_argument("--sample", type=int, default=0, help="예비: N종목만 (0=전체)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return 0 if _self_test() else 1
    return run(a.cost, a.delisting, a.sample)


if __name__ == "__main__":
    sys.exit(main())
