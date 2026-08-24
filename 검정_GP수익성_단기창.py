#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""검정_GP수익성_단기창.py — 수익성(GP) 팩터 검정 (STANDALONE, 단기창)

사전등록서: 가상매매\검증\GP수익성_검정_사전등록.md (데이터 보기 전 확정)

질문: 고수익성(GP=(매출−매출원가)/자산) 종목이 소·중형에서 순풍인가?
제약: DART 재무는 FY2015~ → IN 2015~2019 / OOS 2020~2026 (짧음·저검정력).
      애매하면 미결. OOS 나쁘면 기각.

방법: 월별 EW 5분위(얇으면 3분위). 롱숏 Q5−Q1 NW-t, 롱온리 Q5−유니버스−비용.
      재무 4개월 지연(룩어헤드 차단). 상폐 base 내장. 비용 0.45%×회전.
      로더는 자체 내장(외부 import 의존 없음).

사용:
  py 검정_GP수익성_단기창.py --self-test
  py 검정_GP수익성_단기창.py --fund fundamentals_gp_2015_2025.csv --sample 1500
  py 검정_GP수익성_단기창.py --fund fundamentals_gp_2015_2025.csv
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

# ── 상수 ──
IN_START, IN_END = 2015, 2019
OOS_START = 2020
MIN_PRICE = 1000
MIN_ADV = 5e8
FIN_LAG_M = 4
COST_RT_DEFAULT = 0.45
DELISTING = {"base": (0.0, -0.30, -0.50),
             "conservative": (0.0, -0.50, -0.70),
             "optimistic": (0.0, -0.30, -0.30),
             "worst": (0.0, -1.00, -1.00)}
MIN_NAMES_Q = 5     # 분위당 최소 종목(5분위 → 월 25+ 필요). 미달 시 3분위로.


# ═══════════════ 내장 유틸 ═══════════════
def newey_west_t(np, x, lag=None):
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    n = len(x)
    if n < 8:
        return np.nan
    if lag is None:
        lag = int(np.floor(4 * (n / 100) ** (2 / 9)))
    mu = x.mean(); e = x - mu
    var = (e @ e) / n
    for l in range(1, lag + 1):
        w = 1 - l / (lag + 1)
        var += 2 * w * (e[l:] @ e[:-l]) / n
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
    return d[d["close"] > 0].sort_values(["code", "date"])


def load_gp(pd, np, fund_files):
    """재무 CSV(들) → (code, fiscal_year, gp). gp=(revenue−cogs)/assets."""
    frames = []
    for f in fund_files:
        p = os.path.join(BASE, f)
        if os.path.exists(p):
            frames.append(pd.read_csv(p, dtype={"code": str}, encoding="utf-8-sig"))
    if not frames:
        return None
    d = pd.concat(frames, ignore_index=True)
    d = d.dropna(subset=["fiscal_year"])
    d["fiscal_year"] = pd.to_numeric(d["fiscal_year"], errors="coerce")
    for c in ("revenue", "cogs", "assets"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["revenue", "cogs", "assets"])
    d = d[d["assets"] > 0]
    d["gp"] = (d["revenue"] - d["cogs"]) / d["assets"]
    d = d.sort_values("fiscal_year").groupby(["code", "fiscal_year"]).last().reset_index()
    return d[["code", "fiscal_year", "gp"]]


def build_monthly(pd, np, daily, mcap, gp, delist_ret):
    d = daily.sort_values(["code", "date"]).copy()
    d["val"] = d["close"] * d["volume"]
    g = d.groupby("code", sort=False)
    d["adv20"] = g["val"].transform(lambda s: s.rolling(20, min_periods=10).mean())
    d["ym"] = d["date"].dt.year * 12 + (d["date"].dt.month - 1)

    me = d.groupby(["code", "ym"]).last().reset_index().sort_values(["code", "ym"])
    gm = me.groupby("code", sort=False)
    me["mclose"] = me["close"]
    me["c1"] = gm["mclose"].shift(1)
    me["nextclose"] = gm["mclose"].shift(-1)
    me["fwd"] = me["nextclose"] / me["mclose"] - 1

    last_ym = gm["ym"].transform("max")
    is_last = me["ym"] == last_ym
    panel_last = me["ym"].max()
    gone_last = is_last & (me["ym"] < panel_last - 1)
    normal, crash, mild = delist_ret
    m1 = me["mclose"] / me["c1"] - 1
    dl = np.where(m1 >= 0.10, normal, np.where(m1 <= -0.30, crash, mild))
    mask = gone_last & me["nextclose"].isna()
    me.loc[mask, "fwd"] = pd.Series(dl, index=me.index)[mask]

    mc = mcap.copy()
    mc["ym"] = mc["date"].dt.year * 12 + (mc["date"].dt.month - 1)
    mc = mc.groupby(["code", "ym"])["mcap"].last().reset_index()
    me = me.merge(mc, on=["code", "ym"], how="left")

    # GP 4개월 지연 병합
    if gp is not None and len(gp):
        me["applic_fy"] = ((me["ym"].astype("int64") - FIN_LAG_M) // 12 - 1)
        me = me.merge(gp, left_on=["code", "applic_fy"],
                      right_on=["code", "fiscal_year"], how="left")
    else:
        me["gp"] = np.nan
    return me


# ═══════════════ 백테스트 ═══════════════
def backtest(pd, np, me, seg, cost_rt):
    d = me.copy()
    d = d[d["adv20"] >= MIN_ADV]
    d = d[d["close"] >= MIN_PRICE]
    d = d.dropna(subset=["gp", "fwd"])
    if seg != "전체":
        d["tier"] = d.groupby("ym")["mcap"].transform(
            lambda s: pd.qcut(s, 3, labels=["소", "중", "대"], duplicates="drop")
            if s.notna().sum() > 30 else np.nan)
        d = d[d["tier"] == seg]
    if len(d) == 0:
        return None
    prev = None
    rows = []
    for ym, sub in d.groupby("ym"):
        n = sub["gp"].notna().sum()
        nq = 5 if n >= MIN_NAMES_Q * 5 else (3 if n >= 3 * 4 else 0)
        if nq == 0:
            continue
        try:
            q = pd.qcut(sub["gp"].rank(method="first"), nq, labels=list(range(1, nq + 1))).astype(int)
        except Exception:
            continue
        sub = sub.assign(q=q)
        qhi, qlo = nq, 1
        univ = sub["fwd"].mean()
        hi = sub[sub.q == qhi]["fwd"].mean()
        lo = sub[sub.q == qlo]["fwd"].mean()
        qset = set(sub[sub.q == qhi]["code"])
        turn = 1.0 if not prev else 1 - len(qset & prev) / len(prev)
        prev = qset
        qmeans = [sub[sub.q == k]["fwd"].mean() for k in range(1, nq + 1)]
        rows.append({"ym": ym, "nq": nq, "univ": univ, "hi": hi, "lo": lo,
                     "ls": hi - lo, "lo_net": hi - univ - turn * (cost_rt / 100.0),
                     "turn": turn, "qm": qmeans})
    if not rows:
        return None
    r = pd.DataFrame(rows)
    r["year"] = r["ym"] // 12
    return r


def stats(pd, np, r, period):
    x = r[(r["year"] >= IN_START) & (r["year"] <= IN_END)] if period == "IN" \
        else r[r["year"] >= OOS_START]
    if len(x) < 12:
        return None
    t = newey_west_t(np, x["ls"].values)
    # 단조성: 5분위 평균의 방향(1역전 허용). 3분위 섞이면 앞 3개로 근사.
    qms = [q for q in x["qm"] if len(q) == 5]
    mono = None
    if qms:
        avg = [np.nanmean([q[i] for q in qms]) for i in range(5)]
        steps = sum(1 for i in range(4) if avg[i + 1] >= avg[i])
        mono = steps >= 3
    ann = lambda c: float(np.nanmean(x[c]) * 12 * 100)
    return {"n": len(x), "t": t, "ls_ann": ann("ls"), "lo_net": ann("lo_net"),
            "mono": mono, "turn": float(np.nanmean(x["turn"]) * 100)}


# ═══════════════ 셀프테스트 ═══════════════
def _self_test():
    import numpy as np, pandas as pd
    ok = tot = 0

    def chk(n, c):
        nonlocal ok, tot
        tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")

    # load_gp: gp 계산
    fdf = pd.DataFrame({"code": ["A", "B"], "fiscal_year": [2018, 2018],
                        "revenue": [1000.0, 1000.0], "cogs": [400.0, 800.0],
                        "assets": [2000.0, 2000.0]})
    fp = os.path.join(BASE, "_gp_selftest_fund.csv")
    fdf.to_csv(fp, index=False, encoding="utf-8-sig")
    gp = load_gp(pd, np, ["_gp_selftest_fund.csv"])
    try:
        os.remove(fp)
    except Exception:
        pass
    chk("load_gp 계산 gp=(rev-cogs)/assets", gp is not None and
        abs(float(gp[gp.code == "A"]["gp"].iloc[0]) - 0.30) < 1e-9)
    chk("A(고GP 0.30) > B(0.10)",
        float(gp[gp.code == "A"]["gp"].iloc[0]) > float(gp[gp.code == "B"]["gp"].iloc[0]))

    # NW
    rng = np.random.default_rng(0)
    chk("NW 평균0 → |t|<2.5", abs(newey_west_t(np, rng.normal(0, 1, 200))) < 2.5)
    chk("NW 평균0.5 → t>3", newey_west_t(np, rng.normal(0.5, 1, 200)) > 3)

    # 4개월 지연 회계연도
    chk("2020-05(ym)→FY2019", ((2020 * 12 + 4) - 4) // 12 - 1 == 2019)
    chk("2020-04(ym)→FY2018(지연)", ((2020 * 12 + 3) - 4) // 12 - 1 == 2018)

    # 백테스트: 심은 GP 신호(높을수록 fwd↑), IN 구간(2016~2018)
    months, nn = 48, 150
    YM0 = 2016 * 12
    recs = []
    for mi in range(months):
        ym = YM0 + mi
        gpv = rng.uniform(0.0, 0.5, nn)
        fwd = (gpv - 0.25) * 0.5 + rng.normal(0, 0.01, nn)  # 고GP→고수익
        for j in range(nn):
            recs.append({"code": f"{j:06d}", "ym": ym, "close": 2000.0,
                         "adv20": 1e9, "mcap": 1e11, "gp": gpv[j], "fwd": fwd[j]})
    me = pd.DataFrame(recs)
    r = backtest(pd, np, me, "전체", 0.0)
    chk("백테스트 생성", r is not None and len(r) > 0)
    chk("5분위 적용(nq=5)", r is not None and (r["nq"] == 5).all())
    st = stats(pd, np, r, "IN") if r is not None else None
    chk("IN 통계 생성", st is not None)
    if st:
        chk("심은 GP신호 → 롱숏 양수", st["ls_ann"] > 0)
        chk("롱온리 net > 0", st["lo_net"] > 0)
        chk("단조 True", st["mono"] is True)
        chk("IN NW-t > 2", st["t"] > 2)

    # 얇은 표본 → 3분위 강등
    recs2 = []
    for mi in range(24):
        ym = 2016 * 12 + mi
        gpv = rng.uniform(0, 0.5, 16)
        for j in range(16):
            recs2.append({"code": f"{j:06d}", "ym": ym, "close": 2000.0,
                          "adv20": 1e9, "mcap": 1e11, "gp": gpv[j], "fwd": 0.01})
    r2 = backtest(pd, np, pd.DataFrame(recs2), "전체", 0.0)
    chk("얇은 표본 → 3분위 강등", r2 is not None and (r2["nq"] == 3).all())

    # qcut 5분위
    s = pd.Series(np.arange(100.0))
    q = pd.qcut(s.rank(method="first"), 5, labels=list(range(1, 6))).astype(int)
    chk("5분위 최대→Q5", q.iloc[-1] == 5)

    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot


# ═══════════════ 메인 ═══════════════
def run(cost_rt, scenario, fund_files, sample=0):
    import pandas as pd, numpy as np
    print(f"데이터 적재... (비용={cost_rt}%, 상폐={scenario}, 재무={fund_files}"
          f"{', 표본 '+str(sample) if sample else ''})", flush=True)
    gp = load_gp(pd, np, fund_files)
    if gp is None:
        print("  [없음] 재무 CSV 없음 → 먼저 DART 수집 필요"); return 2
    fy = sorted(gp["fiscal_year"].unique())
    print(f"  GP 재무 {len(gp):,}행 · {gp['code'].nunique():,}종목 · FY{int(fy[0])}~{int(fy[-1])}", flush=True)

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

    print("월말 특징 계산 중...", flush=True)
    me = build_monthly(pd, np, daily, mcap, gp, DELISTING[scenario])
    print(f"  월말 스냅샷 {len(me):,}행 · GP 병합 {int(me['gp'].notna().sum()):,}행", flush=True)

    L = ["# 수익성(GP) 팩터 검정 — 단기창 결과\n",
         f"\n*{date.today()} · GP FY2015~ · 비용 {cost_rt}% · 상폐 {scenario} · "
         f"IN 2015~2019 / OOS 2020~2026*\n",
         "\n사전등록: `GP수익성_검정_사전등록.md`. Q5=고GP 롱, Q1 숏. 재무 4개월 지연.\n",
         "\n*투자자문 아님. 결정·책임은 본인.*\n",
         "\n> ⚠️ **단기창(IN 5년)·저검정력.** DART 재무 2015~ 한계. 애매하면 미결·기각.\n"]

    verdict = {}
    for seg in ("전체", "소", "중", "대"):
        L.append(f"\n---\n\n## 시총 {seg}\n\n")
        r = backtest(pd, np, me, seg, cost_rt)
        if r is None:
            L.append("*표본 부족 — 판정 불가.*\n"); continue
        L.append("| 구간 | 개월 | 분위 | 롱숏 연% | NW-t | 단조 | 롱온리 net연% | 회전% |\n")
        L.append("|---|---|---|---|---|---|---|---|\n")
        segv = {}
        for period in ("IN", "OOS"):
            st = stats(pd, np, r, period)
            if st is None:
                L.append(f"| {period} | <12 | — | — | — | — | — | — |\n"); continue
            nqmode = int(r[r['year'].between(IN_START, IN_END)]['nq'].median()) if period == "IN" \
                else int(r[r['year'] >= OOS_START]['nq'].median())
            mono = "✅" if st["mono"] else ("—" if st["mono"] is not None else "n/a")
            L.append(f"| {period} | {st['n']} | {nqmode} | {st['ls_ann']:+.1f} | "
                     f"{st['t']:+.2f} | {mono} | {st['lo_net']:+.1f} | {st['turn']:.0f} |\n")
            segv[period] = st
        verdict[seg] = segv

    L.append("\n---\n\n## 판정 (사전등록 관문)\n\n")
    L.append("(A)IN LS t>2 · (B)단조 & Q5>유니버스 · (C)OOS LS t>1.5 부호유지 · (D)롱온리 net>0.\n")
    L.append("**단기창·저검정력 → 통과해도 잠정(2028 재확인). 애매하면 미결.**\n\n")
    for seg in ("소", "중", "대"):
        sv = verdict.get(seg, {})
        i, o = sv.get("IN"), sv.get("OOS")
        if not i or not o:
            L.append(f"- **{seg}**: 구간 부족 → 미결\n"); continue
        gA = i["t"] > 2
        gB = (i["lo_net"] > 0) and (o["lo_net"] > 0) and bool(i["mono"])
        gC = (o["t"] > 1.5) and (np.sign(o["ls_ann"]) == np.sign(i["ls_ann"]))
        gD = o["lo_net"] > 0
        passed = all([gA, gB, gC, gD])
        res = "잠정 채택(단기창)" if passed else ("기각" if (o["t"] < 0 or o["lo_net"] < 0) else "미결")
        mk = lambda b: "✅" if b else "❌"
        L.append(f"- **{seg}**: A{mk(gA)}(t={i['t']:+.2f}) B{mk(gB)} "
                 f"C{mk(gC)}(OOSt={o['t']:+.2f}) D{mk(gD)}(net={o['lo_net']:+.1f}) → **{res}**\n")
    L.append("\n> 저PBR이 이미 밸류를 잡는다. GP가 미결/기각이면 팩터는 저변동·저PBR 2종으로 확정.\n")

    outpath = os.path.join(OUTDIR, f"GP수익성_검정_결과_{scenario}.md")
    os.makedirs(OUTDIR, exist_ok=True)
    open(outpath, "w", encoding="utf-8").write("".join(L))
    print(f"\n저장: 가상매매\\검증\\{os.path.basename(outpath)}", flush=True)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--cost", type=float, default=COST_RT_DEFAULT)
    ap.add_argument("--delisting", default="base", choices=list(DELISTING))
    ap.add_argument("--fund", default="fundamentals_gp_2015_2025.csv",
                    help="쉼표로 복수 지정 가능")
    ap.add_argument("--sample", type=int, default=0)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return 0 if _self_test() else 1
    return run(a.cost, a.delisting, [f.strip() for f in a.fund.split(",")], a.sample)


if __name__ == "__main__":
    sys.exit(main())
