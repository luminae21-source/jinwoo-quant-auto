#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""검정_팩터결합_저변동성_저PBR.py — 저변동성 × 저PBR 교집합 검정 (STANDALONE)

사전등록서: 가상매매\검증\팩터결합_저변동성_저PBR_사전등록.md (데이터 보기 전 확정)

질문: "싸고 안정적인 소·중형"(저변동 하위3분위 ∩ 저PBR 하위3분위, LL)이
      각 팩터 단독보다 더 강한가? — 핵심은 증분(시너지).

방법: 월별 독립 이중정렬(3분위). LL=롱, HH(고변동∩고PBR)=숏.
      EW·월리밸런스. 비용 0.45%×회전. 상폐 base 내장. IN 2002~2012 / OOS 2013~2026.
      팩터 정의·로더는 C단계(검정_진입엣지_30년)와 동일 로직을 **자체 내장**(외부 import 의존 없음).

관문(사전): (A)IN LS NW-t>2 (B)LL>유니버스 (C)OOS LS NW-t>1.5 부호유지
            (D)롱온리 net>0 ★(E)OOS LL net > max(저변동단독, 저PBR단독) net

사용:
  py 검정_팩터결합_저변동성_저PBR.py --self-test
  py 검정_팩터결합_저변동성_저PBR.py --sample 1500   (예비)
  py 검정_팩터결합_저변동성_저PBR.py                  (전체)
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

# ── 상수 (C단계와 동일) ──
IN_END, OOS_START = 2012, 2013
MIN_PRICE = 1000
MIN_ADV = 5e8                # 20일 평균 거래대금 5억
FIN_LAG_M = 4                # 재무 공시 지연(개월)
COST_RT_DEFAULT = 0.45
DELISTING = {"base": (0.0, -0.30, -0.50),
             "conservative": (0.0, -0.50, -0.70),
             "optimistic": (0.0, -0.30, -0.30),
             "worst": (0.0, -1.00, -1.00)}

# ── 결합 전용 파라미터 ──
NT = 3                    # 3분위(교집합 표본 확보용)
MIN_NAMES = 10           # LL 최소 종목 수


# ═══════════════ 내장 유틸 (C단계 로직 복제, 외부 의존 제거) ═══════════════
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


def load_krx_fund(pd):
    """KRX 날짜별 재무(밸류) 패널 → 월말 (code, ym, PBR, PER). 생존편향·룩어헤드 없음."""
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
    d = d.groupby(["code", "ym"]).last().reset_index()
    return d[["code", "ym", "PBR", "PER"]]


def load_fundamentals(pd, np):
    """수익성(GP)용 재무제표. 없으면 None(밸류 검정엔 불필요)."""
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
    d = d.sort_values("fiscal_year").groupby(["code", "fiscal_year"]).last().reset_index()
    keep = ["code", "fiscal_year", "gp"]
    return d[keep]


def build_monthly(pd, np, daily, mcap, delist_ret, krx=None):
    """일봉 → 월말 스냅샷(vol60·pbr·다음달수익 fwd·mcap·adv20)."""
    d = daily.sort_values(["code", "date"]).copy()
    d["ret"] = d.groupby("code", sort=False)["close"].pct_change()
    d["val"] = d["close"] * d["volume"]
    g = d.groupby("code", sort=False)
    d["vol60"] = g["ret"].transform(lambda s: s.rolling(60, min_periods=40).std())
    d["adv20"] = g["val"].transform(lambda s: s.rolling(20, min_periods=10).mean())
    d["ym"] = d["date"].dt.year * 12 + (d["date"].dt.month - 1)

    me = d.groupby(["code", "ym"]).last().reset_index()
    me = me.sort_values(["code", "ym"])
    gm = me.groupby("code", sort=False)
    me["mclose"] = me["close"]
    me["c1"] = gm["mclose"].shift(1)
    me["nextclose"] = gm["mclose"].shift(-1)
    me["fwd"] = me["nextclose"] / me["mclose"] - 1

    # 상폐月: 다음달 종가 없음 & 이 code의 마지막 달(현재 생존 아님) → 상폐수익
    last_ym = gm["ym"].transform("max")
    is_last = me["ym"] == last_ym
    panel_last = me["ym"].max()
    gone_last = is_last & (me["ym"] < panel_last - 1)
    normal, crash, mild = delist_ret
    m1 = me["mclose"] / me["c1"] - 1
    dl = np.where(m1 >= 0.10, normal, np.where(m1 <= -0.30, crash, mild))
    mask = gone_last & me["nextclose"].isna()
    me.loc[mask, "fwd"] = pd.Series(dl, index=me.index)[mask]

    # 시총(당월)
    mc = mcap.copy()
    mc["ym"] = mc["date"].dt.year * 12 + (mc["date"].dt.month - 1)
    mc = mc.groupby(["code", "ym"])["mcap"].last().reset_index()
    me = me.merge(mc, on=["code", "ym"], how="left")

    # 밸류(PBR) — KRX 날짜별(룩어헤드 없음)
    if krx is not None and len(krx):
        me = me.merge(krx[["code", "ym", "PBR"]], on=["code", "ym"], how="left")
        me["pbr"] = me["PBR"].where(me["PBR"] > 0)
    else:
        me["pbr"] = np.nan
    return me


# ═══════════════ 교집합 백테스트 ═══════════════
def combo_backtest(pd, np, me, seg, cost_rt):
    """월별 이중정렬 교집합. 반환: DataFrame(월별 수익·회전) 또는 None."""
    d = me.copy()
    d = d[d["adv20"] >= MIN_ADV]
    d = d[d["close"] >= MIN_PRICE]
    d = d.dropna(subset=["vol60", "pbr", "fwd"])
    if seg != "전체":
        d["tier"] = d.groupby("ym")["mcap"].transform(
            lambda s: pd.qcut(s, 3, labels=["소", "중", "대"], duplicates="drop")
            if s.notna().sum() > 30 else np.nan)
        d = d[d["tier"] == seg]
    if len(d) == 0:
        return None

    prev = {"LL": None, "V1": None, "P1": None}
    rows = []
    for ym, sub in d.groupby("ym"):
        if len(sub) < NT * 6:                # 18개 미만 월 제외
            continue
        try:
            vt = pd.qcut(sub["vol60"].rank(method="first"), NT, labels=[1, 2, 3]).astype(int)
            pt = pd.qcut(sub["pbr"].rank(method="first"), NT, labels=[1, 2, 3]).astype(int)
        except Exception:
            continue
        sub = sub.assign(vt=vt.values, pt=pt.values)
        LL = sub[(sub.vt == 1) & (sub.pt == 1)]
        HH = sub[(sub.vt == 3) & (sub.pt == 3)]
        V1 = sub[sub.vt == 1]           # 저변동 단독
        P1 = sub[sub.pt == 1]           # 저PBR 단독
        if len(LL) < MIN_NAMES or len(HH) < 3:
            continue

        univ = sub["fwd"].mean()
        ll = LL["fwd"].mean(); hh = HH["fwd"].mean()
        v1 = V1["fwd"].mean(); p1 = P1["fwd"].mean()

        def turn(cur, key):
            pr = prev[key]
            t = 1.0 if not pr else 1 - len(cur & pr) / len(pr)
            prev[key] = cur
            return t
        t_ll = turn(set(LL["code"]), "LL")
        t_v1 = turn(set(V1["code"]), "V1")
        t_p1 = turn(set(P1["code"]), "P1")

        c = cost_rt / 100.0
        rows.append({
            "ym": ym, "n_ll": len(LL), "univ": univ,
            "ll": ll, "hh": hh, "ls": ll - hh,
            "ll_net": ll - univ - t_ll * c,
            "v1_net": v1 - univ - t_v1 * c,
            "p1_net": p1 - univ - t_p1 * c,
        })
    if not rows:
        return None
    r = pd.DataFrame(rows)
    r["year"] = r["ym"] // 12
    return r


def stats(pd, np, r, period):
    x = r[r["year"] <= IN_END] if period == "IN" else r[r["year"] >= OOS_START]
    if len(x) < 12:
        return None
    t = newey_west_t(np, x["ls"].values)
    ann = lambda col: float(np.nanmean(x[col]) * 12 * 100)
    return {"n": len(x), "t": t, "ls_ann": ann("ls"),
            "ll_net": ann("ll_net"), "v1_net": ann("v1_net"),
            "p1_net": ann("p1_net"), "n_ll": float(np.nanmean(x["n_ll"]))}


# ═══════════════ 셀프테스트 ═══════════════
def _self_test():
    import numpy as np, pandas as pd
    ok = tot = 0

    def chk(n, c):
        nonlocal ok, tot
        tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")

    # ── build_monthly 단위검증(작은 실데이터형 패널) ──
    dates = pd.bdate_range("2005-01-03", periods=80)
    recs = []
    for code in ("A", "B", "C"):
        px = 2000.0
        for i, dt in enumerate(dates):
            px *= (1 + (0.001 if code == "A" else 0.0))
            recs.append({"date": dt, "code": code, "high": px*1.01, "low": px*0.99,
                         "close": px, "volume": 100000, "mkt": "KOSPI"})
    daily = pd.DataFrame(recs)
    mcap = pd.DataFrame({"date": dates[-1:].repeat(3), "code": ["A", "B", "C"],
                         "mcap": [1e11, 2e11, 3e11]})
    krx = pd.DataFrame({"code": ["A", "B", "C"],
                        "ym": [2005*12]*3, "PBR": [0.8, 1.5, 3.0], "PER": [np.nan]*3})
    me0 = build_monthly(pd, np, daily, mcap, DELISTING["base"], krx=krx)
    chk("build_monthly 컬럼(vol60/pbr/fwd/mcap/adv20)",
        all(c in me0.columns for c in ["vol60", "pbr", "fwd", "mcap", "adv20"]))
    chk("build_monthly fwd 계산됨", me0["fwd"].notna().any())

    # Newey-West
    rng = np.random.default_rng(0)
    chk("NW t: 평균0 → |t|<2.5", abs(newey_west_t(np, rng.normal(0, 1, 200))) < 2.5)
    chk("NW t: 평균0.5 → t>3", newey_west_t(np, rng.normal(0.5, 1, 200)) > 3)

    # ── 교집합/증분 (합성, IN 구간 2005~2009) ──
    rng = np.random.default_rng(7)
    months, nn = 60, 120
    YM0 = 2005 * 12
    def mkpanel(with_syn):
        rr = []
        for mi in range(months):
            ym = YM0 + mi
            vol = rng.uniform(0.01, 0.05, nn); pbr = rng.uniform(0.3, 3.0, nn)
            base_ret = -(vol - 0.03) * 3 - (pbr - 1.5) * 0.02
            syn = np.where((vol < 0.023) & (pbr < 1.1), 0.02, 0.0) if with_syn else 0.0
            fwd = base_ret + syn + rng.normal(0, 0.01, nn)
            for j in range(nn):
                rr.append({"code": f"{j:06d}", "ym": ym, "close": 2000.0,
                           "adv20": 1e9, "mcap": 1e11, "vol60": vol[j],
                           "pbr": pbr[j], "fwd": fwd[j]})
        return pd.DataFrame(rr)

    r = combo_backtest(pd, np, mkpanel(True), "전체", 0.0)
    chk("교집합 백테스트 생성", r is not None and len(r) > 0)
    chk("LL 종목 ≥ 10", r is not None and r["n_ll"].min() >= 10)
    st = stats(pd, np, r, "IN") if r is not None else None
    chk("IN 통계 생성", st is not None)
    if st:
        chk("LS 롱숏 양수(저변동∩저PBR > 고∩고)", st["ls_ann"] > 0)
        chk("LL net > 유니버스(양수)", st["ll_net"] > 0)
        chk("★증분: LL net > 저변동단독", st["ll_net"] > st["v1_net"])
        chk("★증분: LL net > 저PBR단독", st["ll_net"] > st["p1_net"])
        chk("IN NW-t > 2", st["t"] > 2)

    # 3분위 라벨
    s = pd.Series(np.arange(90.0))
    q = pd.qcut(s.rank(method="first"), 3, labels=[1, 2, 3]).astype(int)
    chk("3분위 최소값 → T1", q.iloc[0] == 1)
    chk("3분위 최대값 → T3", q.iloc[-1] == 3)

    # 회전율
    a = {"1", "2", "3"}
    chk("회전 동일 → 0", 1 - len({"1", "2", "3"} & a) / len(a) == 0)
    chk("회전 완전교체 → 1", 1 - len({"4", "5", "6"} & a) / len(a) == 1)

    # 귀무: pbr 무효과 → 증분 미미
    rng = np.random.default_rng(11)
    rr = []
    for mi in range(months):
        ym = YM0 + mi
        vol = rng.uniform(0.01, 0.05, nn); pbr = rng.uniform(0.3, 3.0, nn)
        fwd = -(vol - 0.03) * 3 + rng.normal(0, 0.01, nn)   # vol만 효과
        for j in range(nn):
            rr.append({"code": f"{j:06d}", "ym": ym, "close": 2000.0, "adv20": 1e9,
                       "mcap": 1e11, "vol60": vol[j], "pbr": pbr[j], "fwd": fwd[j]})
    st2 = stats(pd, np, combo_backtest(pd, np, pd.DataFrame(rr), "전체", 0.0), "IN")
    chk("귀무(pbr무효과): LL net − 저변동단독 < 2%p",
        st2 is not None and (st2["ll_net"] - st2["v1_net"]) < 2)

    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot


# ═══════════════ 메인 ═══════════════
def run(cost_rt, scenario, sample=0):
    import pandas as pd, numpy as np
    print(f"데이터 적재... (비용={cost_rt}%, 상폐={scenario}"
          f"{', 표본 '+str(sample) if sample else ''})", flush=True)
    daily = _load_daily(pd, np)
    if daily is None:
        return 2
    if sample and sample > 0:
        keep = (pd.Series(daily["code"].unique())
                .sample(min(sample, daily["code"].nunique()), random_state=42).tolist())
        daily = daily[daily["code"].isin(set(keep))]
        print(f"  ★ 예비: {len(keep)}종목 표본", flush=True)
    print(f"  일봉 {len(daily):,}행 · {daily['code'].nunique():,}종목", flush=True)

    mcap = pd.read_csv(os.path.join(BASE, "종목시총_30년.csv"),
                       dtype={"code": str}, encoding="utf-8-sig")
    mcap["date"] = pd.to_datetime(mcap["date"], errors="coerce")
    mcap["mcap"] = pd.to_numeric(mcap["mcap"], errors="coerce")
    krx = load_krx_fund(pd)
    print(f"  시총 {len(mcap):,}행 · KRX밸류 {0 if krx is None else len(krx):,}행", flush=True)

    print("월말 특징 계산 중...", flush=True)
    me = build_monthly(pd, np, daily, mcap, DELISTING[scenario], krx=krx)
    print(f"  월말 스냅샷 {len(me):,}행", flush=True)

    L = ["# 팩터 결합 검정 — 저변동성 × 저PBR 교집합\n",
         f"\n*{date.today()} · 30년 패널 · 비용 {cost_rt}% · 상폐 {scenario} · "
         f"IN 2002~2012 / OOS 2013~2026*\n",
         "\n사전등록: `팩터결합_저변동성_저PBR_사전등록.md`. LL=저변동T1∩저PBR·P1, HH=고∩고.\n",
         "\n*투자자문 아님. 결정·책임은 본인.*\n",
         "\n> 밸류 데이터는 2002~. IN 짧음(≤11년) → 애매하면 미결.\n"]

    verdict = {}
    for seg in ("전체", "소", "중", "대"):
        L.append(f"\n---\n\n## 시총 {seg}\n\n")
        r = combo_backtest(pd, np, me, seg, cost_rt)
        if r is None:
            L.append("*표본 부족 — 판정 불가.*\n"); continue
        L.append("| 구간 | 개월 | LL평균종목 | LS 연% | NW-t | LL net연% | 저변동단독 net | 저PBR단독 net | 증분(LL−max단독) |\n")
        L.append("|---|---|---|---|---|---|---|---|---|\n")
        segv = {}
        for period in ("IN", "OOS"):
            st = stats(pd, np, r, period)
            if st is None:
                L.append(f"| {period} | <12 | — | — | — | — | — | — | — |\n"); continue
            inc = st["ll_net"] - max(st["v1_net"], st["p1_net"])
            L.append(f"| {period} | {st['n']} | {st['n_ll']:.0f} | {st['ls_ann']:+.1f} | "
                     f"{st['t']:+.2f} | {st['ll_net']:+.1f} | {st['v1_net']:+.1f} | "
                     f"{st['p1_net']:+.1f} | {inc:+.1f} |\n")
            segv[period] = st
        verdict[seg] = segv

    L.append("\n---\n\n## 판정 (사전등록 관문)\n\n")
    L.append("(A)IN LS t>2 · (B)LL>유니버스 · (C)OOS LS t>1.5 부호유지 · "
             "(D)롱온리 net>0 · ★(E)OOS LL net > max(단독). 모두 통과만 채택.\n\n")
    for seg in ("소", "중", "대"):
        sv = verdict.get(seg, {})
        i, o = sv.get("IN"), sv.get("OOS")
        if not i or not o:
            L.append(f"- **{seg}**: 구간 부족 → 미결\n"); continue
        gA = i["t"] > 2
        gB = (i["ll_net"] > 0) and (o["ll_net"] > 0)
        gC = (o["t"] > 1.5) and (np.sign(o["ls_ann"]) == np.sign(i["ls_ann"]))
        gD = o["ll_net"] > 0
        incO = o["ll_net"] - max(o["v1_net"], o["p1_net"])
        gE = incO > 0
        passed = all([gA, gB, gC, gD, gE])
        mk = lambda b: "✅" if b else "❌"
        L.append(f"- **{seg}**: A{mk(gA)}(t={i['t']:+.2f}) B{mk(gB)} "
                 f"C{mk(gC)}(OOSt={o['t']:+.2f}) D{mk(gD)}(net={o['ll_net']:+.1f}) "
                 f"★E{mk(gE)}(증분={incO:+.1f}) → "
                 f"**{'채택' if passed else '결합 기각(단독 유지)'}**\n")
    L.append("\n> ★E(증분)가 관건. 교집합이 단독을 못 이기면 결합할 이유가 없다 → 단독으로 좁힌다.\n")

    outpath = os.path.join(OUTDIR, f"팩터결합_저변동성_저PBR_결과_{scenario}.md")
    os.makedirs(OUTDIR, exist_ok=True)
    open(outpath, "w", encoding="utf-8").write("".join(L))
    print(f"\n저장: 가상매매\\검증\\{os.path.basename(outpath)}", flush=True)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cost", type=float, default=COST_RT_DEFAULT)
    ap.add_argument("--delisting", default="base", choices=list(DELISTING))
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return 0 if _self_test() else 1
    return run(a.cost, a.delisting, a.sample)


if __name__ == "__main__":
    sys.exit(main())
