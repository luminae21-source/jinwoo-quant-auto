#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest_buy_screen.py — ON테마 관찰후보(구 매수후보) 스크린 PIT 백테스트 (검증)
==============================================================================
질문: "ON 테마 주도주를 사면 정말 수익이 났나? 아니면 모멘텀 함정인가?"
방법(PIT, 월간 리밸): 각 리밸월 i에서 데이터 ≤ i만으로
  ON 테마 감지 → 멤버 중 12M 시장초과>0 & F(PIT, 연도 Y-1)≥3 → 테마별 top-N(12M초과 순)
  → EW 보유, i→i+1 수익, 턴오버 비용. 동시점 4-arm 병행:
    screen         : 위 스크린 (전 ON 테마 주도주)
    screen_nodecel : 감속 테마(최근3M초과<0) 제외 후 스크린
    on_all         : ON 테마 참여멤버 전체 EW (리더선별 가치 격리용)
    market_EW      : 시장 동일가중
정직 한계: ① 반도체 수퍼사이클이 데이터 끝단(forward 짧음) ② survivorship(현 구성) ③ 인샘플
  ④ ADTV 유동성필터는 현재 스냅샷이라 PIT 백테스트선 제외(라이브 스크린만 적용) ⑤ 모멘텀=반전위험.
사용: python backtest_buy_screen.py [--topn 5]   /   --selftest
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

import argparse, os, sys, json, datetime
import numpy as np, pandas as pd
import theme_classify as TC
import supercycle_overlay as E

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

F_MIN = 3
TOPN = 5
MIN_MEMBERS = 5
COST = _jq_cost(0.0030)          # 왕복, Σ|Δw|/2에 적용 (모멘텀 고회전 가정)  # §8-3: 종전 0.300% → 실측 0.559% (+0.259%p)
START = 14             # 12M 모멘텀 + 3M 지속 확보


def _theme_baskets(cols, fine, name):
    cur_by, _ = TC.load_theme_universe()
    cm, groups = TC.coarse_map(fine, name)
    baskets, covered = {}, set()
    for th, mem in cur_by.items():
        b = [c for c in mem if c in cols]
        if b: baskets[th] = b; covered |= set(b)
    for g, codes in groups.items():
        if g in ("기타", "미분류(섹터없음)"): continue
        b = [c for c in codes if c in cols and c not in covered]
        if len(b) >= MIN_MEMBERS: baskets[g] = b
    return baskets


def _exc(prices, mkt_cum, i, k):
    out = {}
    base = prices.iloc[i - k]; cur = prices.iloc[i]
    for c in prices.columns:
        if pd.notna(cur[c]) and pd.notna(base[c]) and base[c] > 0:
            out[c] = (cur[c] / base[c] - 1) - mkt_cum
    return out


def select_at(i, months, prices, ret, mkt, baskets, F_by_year, topn, skip_decel):
    mkt_cum12 = float((1 + mkt.iloc[i - 11:i + 1]).prod() - 1)
    ex12 = _exc(prices, mkt_cum12, i, 12)
    year = months[i].year
    Fy = {}
    for y in range(year - 1, 2018, -1):
        if y in F_by_year:
            Fy = F_by_year[y]; break
    sel, on_all = [], []
    for th, b in baskets.items():
        if E._excess_breadth(ret, b, mkt, i)[0] is np.nan: continue
        on = bool(E.detect_supercycle(ret, {"_": b}, mkt, i)["_"])
        if not on: continue
        if skip_decel:
            w3 = slice(i - 2, i + 1)
            ex3 = float((1 + ret[b].mean(axis=1).iloc[w3]).prod() - 1) - float((1 + mkt.iloc[w3]).prod() - 1)
            if ex3 < 0: continue
        parts = [c for c in b if ex12.get(c, -9) > 0 and (Fy.get(c, 9) >= F_MIN)]
        on_all += parts
        parts.sort(key=lambda c: -ex12.get(c, -9))
        sel += parts[:topn]
    return list(dict.fromkeys(sel)), list(dict.fromkeys(on_all))


def _ew_cost(weights_prev, codes, ret_next):
    if not codes:
        return 0.0, weights_prev, sum(weights_prev.values()) / 2 if weights_prev else 0.0
    w = {c: 1.0 / len(codes) for c in codes}
    alln = set(w) | set(weights_prev)
    turn = sum(abs(w.get(c, 0) - weights_prev.get(c, 0)) for c in alln) / 2
    gross = sum(w[c] * ret_next.get(c, 0.0) for c in w)
    return gross - turn * COST, w, turn


def run(panel, fine, name, F_by_year, topn=TOPN, save=True):
    cols = list(panel.columns)
    ret = panel.pct_change(); mkt = ret.mean(axis=1)
    months = list(panel.index)
    baskets = _theme_baskets(cols, fine, name)
    arms = ["screen", "screen_nodecel", "on_all", "market_EW"]
    rets = {a: {} for a in arms}; prevw = {a: {} for a in arms}; turns = {a: [] for a in arms}
    for i in range(START, len(months) - 1):
        ret_next = ret.iloc[i + 1]
        sel, on_all = select_at(i, months, prices=panel, ret=ret, mkt=mkt,
                                baskets=baskets, F_by_year=F_by_year, topn=topn, skip_decel=False)
        sel_nd, _ = select_at(i, months, prices=panel, ret=ret, mkt=mkt,
                              baskets=baskets, F_by_year=F_by_year, topn=topn, skip_decel=True)
        for a, codes in [("screen", sel), ("screen_nodecel", sel_nd), ("on_all", on_all)]:
            r, w, t = _ew_cost(prevw[a], codes, ret_next)
            rets[a][months[i + 1]] = r; prevw[a] = w; turns[a].append(t)
        rets["market_EW"][months[i + 1]] = float(ret_next.mean())
    # metrics
    common = None
    ser = {a: pd.Series(rets[a]).dropna() for a in arms}
    for a in arms:
        common = ser[a].index if common is None else common.intersection(ser[a].index)
    res = {}
    mkt_c = ser["market_EW"].reindex(common)
    for a in arms:
        r = ser[a].reindex(common); m = E.PB.metrics(r) if hasattr(E, "PB") else _metrics(r)
        ex = (r - mkt_c).dropna()
        m["IR"] = float(ex.mean() / ex.std(ddof=1) * np.sqrt(12)) if ex.std(ddof=1) > 0 else 0.0
        m["turn_yr"] = float(np.mean(turns[a])) * 12 if turns[a] else 0.0
        res[a] = m

    print("=" * 70)
    print(f"관찰후보 스크린 백테스트 (PIT 월간) | {common[0].date()}~{common[-1].date()} {len(common)}개월 | top{topn}/테마")
    print("=" * 70)
    print(f"{'arm':16}{'CAGR':>9}{'Sharpe':>8}{'MDD':>9}{'IR':>7}{'연회전율':>9}")
    for a in arms:
        m = res[a]
        print(f"{a:16}{m.get('CAGR',0):>8.1%}{m.get('Sharpe',0):>8.2f}{m.get('MDD',0):>8.1%}{m.get('IR',0):>7.2f}{m.get('turn_yr',0):>9.0%}")
    b = res["market_EW"]
    print(f"\n[해석] 시장EW 대비:")
    for a in ("screen", "screen_nodecel", "on_all"):
        d = res[a]["CAGR"] - b["CAGR"]
        print(f"  {a}: ΔCAGR {d:+.1%}p · IR {res[a]['IR']:+.2f} · {'시장초과 O' if d>0 else '시장미달 X'}")
    sc, on = res["screen"]["CAGR"], res["on_all"]["CAGR"]
    print(f"  리더선별 가치(screen − on_all): {sc-on:+.1%}p "
          f"({'주도주 선별이 도움' if sc>on else '주도주 선별 무익/해'})")
    if save:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        json.dump({"ts": ts, "window": [str(common[0].date()), str(common[-1].date()), len(common)],
                   "topn": topn, "cost": COST, "results": res},
                  open(f"backtest_buy_screen_{ts}.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2, default=float)
        print(f"\n저장: backtest_buy_screen_{ts}.json")
    return res


def _metrics(r, ppy=12):
    r = r.dropna().values
    if len(r) < 6: return {}
    cagr = float(np.prod(1 + r) ** (ppy / len(r)) - 1)
    eq = np.cumprod(1 + r); mdd = float((eq / np.maximum.accumulate(eq) - 1).min())
    sh = float(r.mean() / r.std(ddof=1) * np.sqrt(ppy)) if r.std() > 0 else 0
    return {"CAGR": cagr, "Sharpe": sh, "MDD": mdd, "n": len(r)}


def _load_F(inputs_csv):
    if not os.path.exists(inputs_csv): return {}
    fi = pd.read_csv(inputs_csv, dtype={"code": str}); fi["code"] = fi["code"].str.zfill(6)
    out = {}
    for y, g in fi.groupby("fiscal_year"):
        out[int(y)] = dict(zip(g["code"], g["F"]))
    return out


def _selftest():
    ok = 0
    rng = np.random.default_rng(4); Tm = 40
    idx = pd.date_range("2021-01-31", periods=Tm, freq="ME")
    semi = [f"E{i:05d}" for i in range(8)]; other = [f"X{i:05d}" for i in range(14)]
    cols = semi + other
    px = pd.DataFrame(index=idx, columns=cols, dtype=float)
    for c in cols: px[c] = 1000.0
    # SEMI 수퍼사이클 + 주도주(앞 3개)는 더 강하게 → 리더선별이 이득이어야
    lead = set(semi[:3])
    for t in range(1, Tm):
        for c in cols:
            if c in semi and 16 <= t <= 38:
                base = 0.16 if c in lead else 0.09
                dr = rng.normal(base, 0.05)
            else:
                dr = rng.normal(0.004, 0.02)
            px.loc[idx[t], c] = px.loc[idx[t-1], c] * (1 + dr)
    fine = {**{c: "반도체 제조업" for c in semi}, **{c: "기타 금융업" for c in other}}
    name = {c: c for c in cols}
    F_by_year = {y: {c: 7 for c in cols} for y in range(2019, 2026)}
    res = run(px, fine, name, F_by_year, topn=3, save=False)
    assert res["screen"]["CAGR"] > res["market_EW"]["CAGR"], "스크린이 시장도 못 이김(합성 강추세인데)"; ok += 1
    assert res["screen"]["CAGR"] >= res["on_all"]["CAGR"] - 1e-6, "리더선별이 전체보유보다 못함(합성 리더강세인데)"; ok += 1
    print(f"\n[OK] backtest_buy_screen selftest 통과 ({ok} checks)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices", default="kospi_monthly_prices.csv")
    ap.add_argument("--kosdaq-sector", default="kosdaq_industry.csv")
    ap.add_argument("--inputs", default="score_inputs_univ.csv")
    ap.add_argument("--topn", type=int, default=TOPN)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    panel = pd.read_csv(a.prices, index_col=0, parse_dates=True)
    panel.columns = [str(c).zfill(6) for c in panel.columns]
    fine, name = TC.load_fine_map("liquidity_sector.csv", a.kosdaq_sector)
    F_by_year = _load_F(a.inputs)
    run(panel, fine, name, F_by_year, topn=a.topn)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
