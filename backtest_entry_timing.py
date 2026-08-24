#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest_entry_timing.py — 진입 타이밍 검증: 추격 vs 눌림목 vs 반등확인
==============================================================================
진우 가설: "싸게 사고 다시 오를 때 산다" = 눌림목 매수 + 추세재개. (꼭대기 추격의 반대)
배경: 한국 단기 reversal 엣지(production FAR·Echo와 정합). backtest_buy_screen에서 추격은 기각됨.
방법(PIT 월간, ON 테마 참여종목 universe, EW, 비용 0.30%):
  market_EW : 시장 동일가중 (벤치)
  chase     : ex12(12M 시장초과) 상위 top-N  ← 꼭대기 추격 (기각된 것)
  dip       : ex12>0(추세유지) 중 1M수익 하위 top-N  ← 강한 종목의 눌림목
  dip_turn  : ex12>0 & 3M수익<0(눌림) & 1M수익>0(반전) 전부  ← 다시 오를 때
정직 한계: 인샘플·survivorship·반도체 사이클 끝단·월간 빈도. 진입 timing 효과의 방향성 확인용.
사용: python backtest_entry_timing.py [--topn 5]   /   --selftest
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
COST = _jq_cost(0.0030)  # §8-3: 종전 0.300% → 실측 0.559% (+0.259%p)
START = 14


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


def _metrics(r, ppy=12):
    r = r.dropna().values
    if len(r) < 6: return {}
    cagr = float(np.prod(1 + r) ** (ppy / len(r)) - 1)
    eq = np.cumprod(1 + r); mdd = float((eq / np.maximum.accumulate(eq) - 1).min())
    sh = float(r.mean() / r.std(ddof=1) * np.sqrt(ppy)) if r.std() > 0 else 0
    return {"CAGR": cagr, "Sharpe": sh, "MDD": mdd, "n": len(r)}


def select(i, months, prices, ret, mkt, baskets, F_by_year, topn):
    """리밸 i에서 진입 변형별 종목 집합 (PIT). returns dict variant→[codes]."""
    mc12 = float((1 + mkt.iloc[i - 11:i + 1]).prod() - 1)
    mc3 = float((1 + mkt.iloc[i - 2:i + 1]).prod() - 1)
    year = months[i].year
    Fy = {}
    for y in range(year - 1, 2018, -1):
        if y in F_by_year: Fy = F_by_year[y]; break
    p_now = prices.iloc[i]; p1 = prices.iloc[i - 1]; p3 = prices.iloc[i - 3]; p12 = prices.iloc[i - 12]
    chase, dip, dip_turn = [], [], []
    for th, b in baskets.items():
        if not bool(E.detect_supercycle(ret, {"_": b}, mkt, i)["_"]):
            continue
        rows = []
        for c in b:
            if pd.isna(p_now[c]) or pd.isna(p12[c]) or p12[c] <= 0: continue
            if Fy.get(c, 9) < F_MIN: continue
            ex12 = (p_now[c] / p12[c] - 1) - mc12
            if ex12 <= 0: continue                       # 추세 유지(상승참여)
            r1 = (p_now[c] / p1[c] - 1) if (pd.notna(p1[c]) and p1[c] > 0) else np.nan
            ex3 = ((p_now[c] / p3[c] - 1) - mc3) if (pd.notna(p3[c]) and p3[c] > 0) else np.nan
            rows.append((c, ex12, r1, ex3))
        if not rows: continue
        # chase: ex12 상위
        chase += [c for c, *_ in sorted(rows, key=lambda x: -x[1])[:topn]]
        # dip: 1M 하위(가장 눌린) — r1 오름차순
        dd = [r for r in rows if pd.notna(r[2])]
        dip += [c for c, *_ in sorted(dd, key=lambda x: x[2])[:topn]]
        # dip_turn: 3M 눌림(ex3<0) & 1M 반전(r1>0)
        dt = [r for r in rows if pd.notna(r[3]) and r[3] < 0 and pd.notna(r[2]) and r[2] > 0]
        dip_turn += [c for c, *_ in sorted(dt, key=lambda x: -x[1])[:topn]]
    return {"chase": list(dict.fromkeys(chase)), "dip": list(dict.fromkeys(dip)),
            "dip_turn": list(dict.fromkeys(dip_turn))}


def _ew_cost(prevw, codes, ret_next):
    if not codes:
        return 0.0, {}, 0.0
    w = {c: 1.0 / len(codes) for c in codes}
    alln = set(w) | set(prevw)
    turn = sum(abs(w.get(c, 0) - prevw.get(c, 0)) for c in alln) / 2
    gross = sum(w[c] * ret_next.get(c, 0.0) for c in w)
    return gross - turn * COST, w, turn


def run(panel, fine, name, F_by_year, topn=TOPN, save=True):
    cols = list(panel.columns)
    ret = panel.pct_change(); mkt = ret.mean(axis=1); months = list(panel.index)
    baskets = _theme_baskets(cols, fine, name)
    arms = ["market_EW", "chase", "dip", "dip_turn"]
    rets = {a: {} for a in arms}; prevw = {a: {} for a in arms}; turns = {a: [] for a in arms}
    for i in range(START, len(months) - 1):
        ret_next = ret.iloc[i + 1]
        sels = select(i, months, panel, ret, mkt, baskets, F_by_year, topn)
        rets["market_EW"][months[i + 1]] = float(ret_next.mean())
        for a in ("chase", "dip", "dip_turn"):
            r, w, t = _ew_cost(prevw[a], sels[a], ret_next)
            rets[a][months[i + 1]] = r; prevw[a] = w; turns[a].append(t)
    common = None
    ser = {a: pd.Series(rets[a]).dropna() for a in arms}
    for a in arms:
        common = ser[a].index if common is None else common.intersection(ser[a].index)
    mkt_c = ser["market_EW"].reindex(common)
    res = {}
    for a in arms:
        r = ser[a].reindex(common); m = _metrics(r)
        ex = (r - mkt_c).dropna()
        m["IR"] = float(ex.mean() / ex.std(ddof=1) * np.sqrt(12)) if ex.std(ddof=1) > 0 else 0.0
        m["turn_yr"] = float(np.mean(turns[a])) * 12 if turns[a] else 0.0
        res[a] = m
    print("=" * 70)
    print(f"진입 타이밍 백테스트 (PIT 월간, ON테마 참여종목) | {common[0].date()}~{common[-1].date()} {len(common)}개월 | top{topn}/테마")
    print("=" * 70)
    print(f"{'arm':12}{'CAGR':>9}{'Sharpe':>8}{'MDD':>9}{'IR':>7}{'연회전율':>9}")
    for a in arms:
        m = res[a]
        print(f"{a:12}{m.get('CAGR',0):>8.1%}{m.get('Sharpe',0):>8.2f}{m.get('MDD',0):>8.1%}{m.get('IR',0):>7.2f}{m.get('turn_yr',0):>9.0%}")
    b = res["market_EW"]["CAGR"]
    print(f"\n[해석] 시장EW({b:.1%}) 대비:")
    for a in ("chase", "dip", "dip_turn"):
        d = res[a]["CAGR"] - b
        print(f"  {a:9}: ΔCAGR {d:+.1%}p · Sharpe {res[a]['Sharpe']:.2f} · MDD {res[a]['MDD']:.1%} · {'시장초과 O' if d>0 else '미달 X'}")
    print(f"  눌림목 효과 (dip − chase): {res['dip']['CAGR']-res['chase']['CAGR']:+.1%}p")
    if save:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        json.dump({"ts": ts, "topn": topn, "results": res},
                  open(f"backtest_entry_timing_{ts}.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=2, default=float)
        print(f"\n저장: backtest_entry_timing_{ts}.json")
    return res


def _load_F(p):
    if not os.path.exists(p): return {}
    fi = pd.read_csv(p, dtype={"code": str}); fi["code"] = fi["code"].str.zfill(6)
    return {int(y): dict(zip(g["code"], g["F"])) for y, g in fi.groupby("fiscal_year")}


def _selftest():
    ok = 0
    rng = np.random.default_rng(7); Tm = 44
    idx = pd.date_range("2021-01-31", periods=Tm, freq="ME")
    semi = [f"E{i:05d}" for i in range(10)]; other = [f"X{i:05d}" for i in range(12)]
    cols = semi + other
    px = pd.DataFrame(index=idx, columns=cols, dtype=float)
    for c in cols: px[c] = 1000.0
    # SEMI 수퍼사이클 + 강한 평균회귀(눌리면 다음달 반등) → dip이 chase 이겨야
    for t in range(1, Tm):
        for c in cols:
            if c in semi and 16 <= t <= 43:
                prev2 = px[c].iloc[t-1] / px[c].iloc[t-2] - 1 if t >= 2 else 0
                mr = -0.6 * prev2                      # 평균회귀
                dr = rng.normal(0.06 + mr, 0.04)
            else:
                dr = rng.normal(0.004, 0.02)
            px.loc[idx[t], c] = px.loc[idx[t-1], c] * (1 + dr)
    fine = {**{c: "반도체 제조업" for c in semi}, **{c: "기타 금융업" for c in other}}
    name = {c: c for c in cols}
    F = {y: {c: 7 for c in cols} for y in range(2019, 2026)}
    res = run(px, fine, name, F, topn=4, save=False)
    # 코드 동작 검증(경험적 dip>chase는 데이터 의존이라 단정 안 함): 4 arm 모두 산출·유효
    assert all(a in res and "CAGR" in res[a] for a in ("market_EW","chase","dip","dip_turn")); ok += 1
    assert res["chase"]["n"] >= 12, "표본 부족"; ok += 1
    print(f"\n[OK] backtest_entry_timing selftest 통과 ({ok} checks)")
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
    run(panel, fine, name, _load_F(a.inputs), topn=a.topn)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
