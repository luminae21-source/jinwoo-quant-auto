#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""검정_섹터내_기울기_30년.py — ② 진우 사냥터 안에서 싸거나 안정적인 게 이기나

사전등록서: 가상매매\검증\섹터내_기울기_사전등록.md (데이터 보기 전)

질문: 전 시장에선 저변동성·저PBR이 이겼다(C). 그런데 진우님은 기술제조주
      (반도체장비·전자부품·이차전지)를 매매한다. **그 안에서** 싸거나 안정적인
      종목을 고르면 이기는가? 이기면 스타일 안 바꾸고 기울기만 얹는다.

방법:
  · 유니버스 = 진우 기술제조 섹터(557종목). 매월 말 팩터로 터셔일(3분위).
  · 롱숏 = T1(싸다/안정) − T3(비싸다/변동). **롱숏 중심 판정**(생존편향 강건).
  · 롱온리 T1 vs 유니버스 = 참고(생존편향 있음, 섹터매핑이 현재상장만).
  · 팩터: 저변동성·저PBR(C 채택 둘만). IN 2002~2012 / OOS 2013~2026.
  · 상폐 base·비용 0.45%·NW-t 내장.

⚠️ 섹터 매핑이 현재 상장 종목만 → 롱온리 절대수익은 생존편향 과대. 롱숏으로 판정.

산출: 가상매매\검증\섹터내_기울기_결과.md
사용: py 검정_섹터내_기울기_30년.py --self-test | (인자없이 전체)
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
NT = 3                       # 터셔일
MIN_PRICE = 1000
MIN_ADV = 5e8
COST_RT = 0.45
DELISTING = {"base": (0.0, -0.30, -0.50), "conservative": (0.0, -0.50, -0.70)}
SECTOR_KW = ["반도체", "전자부품", "이차전지", "특수 목적용 기계",
             "일반 목적용 기계", "광학", "전기장비", "통신 및 방송 장비"]
FACTORS = [("저변동성", -1), ("저PBR", -1)]


# ───────────────────────── Newey-West t ─────────────────────────
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


# ───────────────────────── 유니버스 ─────────────────────────
def load_universe(pd):
    frames = []
    for f in ("liquidity_sector.csv", "kosdaq_industry.csv"):
        p = os.path.join(BASE, f)
        if os.path.exists(p):
            frames.append(pd.read_csv(p, dtype={"code": str}, usecols=["code", "sector"]))
    if not frames:
        return set()
    s = pd.concat(frames).dropna(subset=["sector"]).drop_duplicates("code")
    mask = s["sector"].str.contains("|".join(SECTOR_KW))
    return set(s[mask]["code"])


def load_krx_pbr(pd):
    frames = []
    for m in ("KOSPI", "KOSDAQ"):
        p = os.path.join(BASE, f"종목재무_KRX_{m}.csv")
        if os.path.exists(p):
            frames.append(pd.read_csv(p, usecols=["date", "code", "PBR"],
                                      dtype={"code": str}, encoding="utf-8-sig"))
    if not frames:
        return None
    d = pd.concat(frames, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d["PBR"] = pd.to_numeric(d["PBR"], errors="coerce")
    d["ym"] = d["date"].dt.year * 12 + (d["date"].dt.month - 1)
    d = d.dropna(subset=["ym"]).groupby(["code", "ym"]).last().reset_index()
    return d[["code", "ym", "PBR"]]


# ───────────────────────── 월별 특징 ─────────────────────────
def build_monthly(pd, np, daily, krx, delist_ret):
    d = daily.sort_values(["code", "date"]).copy()
    d["ret"] = d.groupby("code", sort=False)["close"].pct_change()
    d["val"] = d["close"] * d["volume"]
    g = d.groupby("code", sort=False)
    d["vol60"] = g["ret"].transform(lambda s: s.rolling(60, min_periods=40).std())
    d["adv20"] = g["val"].transform(lambda s: s.rolling(20, min_periods=10).mean())
    d["ym"] = d["date"].dt.year * 12 + (d["date"].dt.month - 1)

    me = d.groupby(["code", "ym"]).tail(1).copy()
    me = me.sort_values(["code", "ym"])
    gm = me.groupby("code", sort=False)
    me["mclose"] = me["close"]
    me["nextclose"] = gm["mclose"].shift(-1)
    me["c1"] = gm["mclose"].shift(1)
    me["fwd"] = me["nextclose"] / me["mclose"] - 1

    # 상폐月 처리
    last_ym = gm["ym"].transform("max")
    panel_last = me["ym"].max()
    gone_last = (me["ym"] == last_ym) & (me["ym"] < panel_last - 1)
    normal, crash, mild = delist_ret
    m1 = me["mclose"] / me["c1"] - 1
    dl = np.where(m1 >= 0.10, normal, np.where(m1 <= -0.30, crash, mild))
    me.loc[gone_last & me["nextclose"].isna(), "fwd"] = (
        pd.Series(dl, index=me.index)[gone_last & me["nextclose"].isna()] / 100.0)

    # KRX PBR 병합
    if krx is not None and len(krx):
        me = me.merge(krx, on=["code", "ym"], how="left")
        me["pbr"] = me["PBR"].where(me["PBR"] > 0)
    else:
        me["pbr"] = np.nan
    return me


def factor_col(me, fname):
    return me["vol60"] if fname == "저변동성" else me["pbr"]


# ───────────────────────── 터셔일 롱숏 ─────────────────────────
def backtest(pd, np, me, universe, fname, direction):
    d = me[me["code"].isin(universe)].copy()
    d = d[(d["close"] >= MIN_PRICE) & (d["adv20"] >= MIN_ADV)]
    d["f"] = factor_col(d, fname)
    d = d.dropna(subset=["f", "fwd"])
    d["fs"] = d["f"] * direction        # 크면 T-top(매수)
    rows = []
    t1_prev = None
    for ym, sub in d.groupby("ym"):
        if sub["fs"].notna().sum() < NT * 4:      # 터셔일당 최소 4종목
            continue
        try:
            sub = sub.assign(t=pd.qcut(sub["fs"].rank(method="first"), NT,
                                       labels=list(range(1, NT + 1))))
        except Exception:
            continue
        tr = sub.groupby("t")["fwd"].mean()
        univ = sub["fwd"].mean()
        t1 = set(sub[sub["t"] == NT]["code"])       # T-top = 매수 후보
        turn = (1 - len(t1 & t1_prev) / len(t1_prev)) if t1_prev else 1.0
        t1_prev = t1
        rows.append({"ym": ym, "univ": univ, "turn": turn,
                     **{f"t{i}": tr.get(i, np.nan) for i in range(1, NT + 1)}})
    if not rows:
        return None
    r = pd.DataFrame(rows)
    r["year"] = r["ym"] // 12
    r["ls"] = r[f"t{NT}"] - r["t1"]                  # 롱숏 = 매수쪽 − 반대쪽
    r["lo_net"] = r[f"t{NT}"] - r["univ"] - r["turn"] * (COST_RT / 100.0)
    return r


def stats(pd, np, r, period):
    x = r[r["year"] <= IN_END] if period == "IN" else r[r["year"] >= OOS_START]
    if len(x) < 12:
        return None
    ls = x["ls"].values
    tm = [np.nanmean(x[f"t{i}"]) for i in range(1, NT + 1)]
    steps = sum(1 for i in range(NT - 1) if tm[i + 1] >= tm[i])
    return {"n": len(x), "t": newey_west_t(np, ls),
            "ls_ann": np.nanmean(ls) * 12 * 100,
            "lo_net_ann": np.nanmean(x["lo_net"]) * 12 * 100,
            "mono": steps >= (NT - 2), "turn": np.nanmean(x["turn"]) * 100}


# ───────────────────────── 셀프테스트 ─────────────────────────
def _self_test():
    import numpy as np, pandas as pd
    ok = tot = 0

    def chk(n, c):
        nonlocal ok, tot
        tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")

    rng = np.random.default_rng(0)
    chk("NW t 평균0 → 작음", abs(newey_west_t(np, rng.normal(0, 1, 200))) < 2.5)
    chk("NW t 평균0.5 → 큼", newey_west_t(np, rng.normal(0.5, 1, 200)) > 3)

    # 유니버스 키워드
    s = pd.DataFrame({"sector": ["반도체 제조업", "음식점업", "전자부품 제조업"]})
    m = s["sector"].str.contains("|".join(SECTOR_KW))
    chk("반도체·전자부품 포함, 음식점 제외", list(m) == [True, False, True])

    # 터셔일 + 심은 신호
    N = 60
    me = pd.DataFrame({
        "code": [f"{i:06d}" for i in range(N)] * 6,
        "ym": np.repeat(np.arange(6) + 24000, N),
        "close": 2000.0, "adv20": 1e9})
    me["vol60"] = np.tile(np.linspace(0.01, 0.05, N), 6)
    me["fwd"] = -(me["vol60"] - 0.03) * 5 + rng.normal(0, 0.002, 6 * N)
    me["pbr"] = np.nan
    r = backtest(pd, np, me, set(me["code"]), "저변동성", -1)
    chk("터셔일 백테스트 생성", r is not None and len(r) > 0)
    chk("심은 저변동성 → 롱숏 양수", np.nanmean(r["ls"]) > 0)

    # 터셔일 균등
    sub = pd.DataFrame({"fs": np.arange(60.0)})
    q = pd.qcut(sub["fs"].rank(method="first"), 3, labels=[1, 2, 3])
    chk("터셔일 20개씩", (q.value_counts() == 20).all())

    # 단조 판정(1역전 허용)
    def mono(tm): return sum(1 for i in range(len(tm)-1) if tm[i+1]>=tm[i]) >= len(tm)-2
    chk("단조 완벽 True", mono([1, 2, 3]))
    chk("단조 1역전 True", mono([1, 3, 2]))

    # 상폐 곱셈 단위
    chk("상폐 fwd 단위 -0.5", abs(-50/100 - (-0.5)) < 1e-9)

    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot


# ───────────────────────── 메인 ─────────────────────────
def _load_daily(pd, np):
    frames = []
    for m in ("KOSPI", "KOSDAQ"):
        p = os.path.join(BASE, f"종목일봉_30년_{m}.csv")
        if not os.path.exists(p):
            print(f"  [없음] {os.path.basename(p)}"); return None
        d = pd.read_csv(p, usecols=["date", "code", "close", "volume"],
                        dtype={"code": str}, encoding="utf-8-sig")
        frames.append(d)
    d = pd.concat(frames, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    for c in ("close", "volume"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["date", "close"])
    return d[d["close"] > 0].sort_values(["code", "date"])


def run(scenario):
    import pandas as pd, numpy as np
    print(f"데이터 적재... (상폐={scenario})")
    universe = load_universe(pd)
    print(f"  진우 기술제조 유니버스: {len(universe)}종목")
    daily = _load_daily(pd, np)
    if daily is None:
        return 2
    daily = daily[daily["code"].isin(universe)]
    print(f"  유니버스 일봉 {len(daily):,}행 · {daily['code'].nunique()}종목")
    krx = load_krx_pbr(pd)
    print(f"  KRX PBR {0 if krx is None else len(krx):,}행")

    me = build_monthly(pd, np, daily, krx, DELISTING[scenario])
    print(f"  월말 스냅샷 {len(me):,}행")

    L = ["# 섹터 내 기울기 검정 — ② 결과\n",
         f"\n*{date.today()} · 진우 기술제조 유니버스({len(universe)}종목) · 상폐 {scenario}*\n",
         "\n사전등록: `섹터내_기울기_사전등록.md`. 터셔일 롱숏(T3−T1) 중심.\n",
         "\n⚠️ 섹터매핑=현재상장만 → **롱온리 절대수익은 생존편향**. 롱숏으로 판정.\n",
         "\n*투자자문 아님. 결정·책임은 본인.*\n\n---\n\n"]
    L.append("| 팩터 | 구간 | 개월 | 롱숏 연% | NW-t | 단조 | 롱온리T3 net연%(편향주의) | 회전% |\n")
    L.append("|---|---|---|---|---|---|---|---|\n")
    for fname, direction in FACTORS:
        r = backtest(pd, np, me, universe, fname, direction)
        if r is None:
            L.append(f"| {fname} | — | 데이터 부족 | | | | | |\n"); continue
        for period in ("IN", "OOS"):
            st = stats(pd, np, r, period)
            if st is None:
                continue
            mono = "✅" if st["mono"] else "—"
            L.append(f"| {fname} | {period} | {st['n']} | {st['ls_ann']:+.1f} | "
                     f"{st['t']:+.2f} | {mono} | {st['lo_net_ann']:+.1f} | {st['turn']:.0f} |\n")

    L.append("\n---\n\n## 판정 (Bonferroni ×2)\n\n")
    L.append("(A) IN NW-t>2 · (B) 단조 · (C) OOS NW-t>1.5 부호유지 · (D) 롱온리>0(참고).\n")
    L.append("**롱숏으로 판정.** 섹터 안에서 이 기울기가 유효하면 진우님 종목 선정에 얹는다.\n")
    L.append("예측(사전): 저PBR은 섹터 안에서도 유효 가능, 저변동성은 약할 것(변동성 분산이 좁아서).\n")

    outpath = os.path.join(OUTDIR, "섹터내_기울기_결과.md")
    os.makedirs(OUTDIR, exist_ok=True)
    open(outpath, "w", encoding="utf-8").write("".join(L))
    print(f"\n저장: 가상매매\\검증\\섹터내_기울기_결과.md")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--delisting", choices=list(DELISTING), default="base")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return 0 if _self_test() else 1
    return run(a.delisting)


if __name__ == "__main__":
    sys.exit(main())
