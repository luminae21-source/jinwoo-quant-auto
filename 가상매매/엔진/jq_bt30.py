# -*- coding: utf-8 -*-
r"""jq_bt30.py — Phase 1 을 30년 패널 + PIT 유니버스로 재백테스트

  py jq_bt30.py 1   데이터 적재 + 지표 사전계산 (캐시)
  py jq_bt30.py 2   백테스트 3종 (원스펙 / 하순필터 / 확장유니버스)
  py jq_bt30.py 3   국면·구간 분해 + 문서 생성

★ 무엇이 달라졌나 (기존 6.5년 백테스트 대비)
  ① 유니버스 선택편향 : 정적 스냅샷 -> **월별 PIT 시총**
  ② 생존편향        : 상폐 299종목 유니버스에 포함
  ③ 표본           : 6.5년 -> **30년**
  ④ 국면           : 강세장만 -> IMF·닷컴·금융위기·코로나 포함
  규칙(진입·청산·사이징)은 jq_paper_core 그대로. 바뀐 건 **데이터와 유니버스뿐이다.**
"""
import os, sys, math, pickle, tempfile
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jq_paper_core as C
import jq_backtest_core as B
import jq_panel30 as P30
from jq_paper_core import CFG, DIR_BT, DIR_VERIFY, isnan

ST = os.path.join(tempfile.gettempdir(), "jq_bt30_state.pkl")
IND = os.path.join(tempfile.gettempdir(), "jq_bt30_ind.pkl")
START = "1997-01-01"      # 지표 워밍업 후


def pf(v, sp="{:+.2f}%", pct=True):
    if v is None or isnan(v):
        return "—"
    return sp.format(v * 100 if pct else v)


class Store30:
    """PriceStore 인터페이스 호환 (백테스트가 그대로 쓴다)."""
    def __init__(self, bars, members, names=None):
        self.panels, self.by_code, self.names = {}, {}, names or {}
        for mk in ("KOSPI", "KOSDAQ"):
            d = bars[bars["market"] == mk]
            if len(d):
                self.panels[mk] = d
        for (mk, code), g in bars.groupby(["market", "code"]):
            self.by_code[(mk, code)] = g[["date", "open", "high", "low", "close"]] \
                .reset_index(drop=True)
        self._codes = {}

    def full(self, market, code):
        return self.by_code.get((market, code))

    def bars(self, market, code, asof, window=None):
        g = self.by_code.get((market, code))
        if g is None:
            return None
        i = int(g["date"].searchsorted(pd.Timestamp(asof), side="right"))
        if i < CFG["MIN_BARS"]:
            return None
        return g.iloc[max(0, i - (window or CFG["BARS_WINDOW"])):i]

    def name(self, code):
        return self.names.get(code, code)

    def codes(self, market):
        if market not in self._codes:
            p = self.panels.get(market)
            self._codes[market] = set(p["code"].unique()) if p is not None else set()
        return self._codes[market]

    def trading_days(self, market="KOSPI"):
        p = self.panels.get(market)
        return sorted(pd.to_datetime(p["date"].unique())) if p is not None else []

    def universe(self, market, top_n):
        return sorted(self.codes(market))[:top_n]

    def last_date(self):
        return max(p["date"].max() for p in self.panels.values())


def stage1(mode="top"):
    print(f"[1/3] 30년 패널 적재 + PIT 유니버스  (mode={mode})")
    mcap = P30.load_mcap()
    mkc = P30.market_codes()
    pit, mem = P30.build_pit_universe("top", mcap, mkc)
    if mode == "smid":
        pit_s, mem_s = P30.build_pit_universe("smid", mcap, mkc)
        allmem = dict(mem_s); allmem.update(mem)
    else:
        pit_s, mem_s = None, {}
        allmem = dict(mem)
    print(f"  PIT(원스펙)   : {len(pit)}개월 · 연인원 {len(mem):,}종목")
    if mem_s:
        print(f"  PIT(확장)     : 연인원 {len(mem_s):,}종목")
    print(f"  봉 로드 대상  : {len(allmem):,}종목")

    # 봉 로드 — 30년 패널(675MB)은 파싱이 무거워 pickle 캐시를 쓴다.
    # (jq_bt30_prep.py 가 만든다. 없으면 CSV에서 직접 읽는다.)
    parts = []
    _ck = {"top": ("/tmp/kb.pkl", "/tmp/qb_top.pkl")}.get(mode, ("/tmp/kb.pkl", "/tmp/qb.pkl"))
    for mk, f, cache in (("KOSPI", P30.F_KOSPI, _ck[0]),
                         ("KOSDAQ", P30.F_KOSDAQ, _ck[1])):
        want = {c for c, m in allmem.items() if m == mk}
        if os.path.exists(cache):
            d = pd.read_pickle(cache)
            d = d[d["code"].isin(want)].copy()
        else:
            d = pd.read_csv(os.path.join(P30.ROOT, f), encoding="utf-8-sig",
                            dtype={"code": str},
                            usecols=["date", "code", "open", "high", "low", "close"])
            d = d[d["code"].isin(want)].copy()
            d["date"] = pd.to_datetime(d["date"], errors="coerce")
            for c in ("open", "high", "low", "close"):
                d[c] = pd.to_numeric(d[c], errors="coerce", downcast="float")
            d = d.dropna(subset=["date", "high", "low", "close"])
            d = d[d["close"] > 0]
        d["market"] = mk
        d = d.sort_values(["code", "date"]).reset_index(drop=True)
        parts.append(d)
        print(f"  {mk}: {len(d):,}행 / {d.code.nunique():,}종목")
    bars = pd.concat(parts, ignore_index=True)
    print(f"  일봉 합계 {len(bars):,}행 · {bars.code.nunique():,}종목 "
          f"· {bars.date.min().date()}~{bars.date.max().date()}")

    # 생존편향 실측
    last = bars["date"].max()
    lastper = bars.groupby("code")["date"].max()
    dead = int((lastper < last - pd.Timedelta(days=90)).sum())
    print(f"  중도소멸(상폐/거래정지) {dead:,}종목 포함 -> 생존편향 차단")

    days = sorted(pd.to_datetime(bars[bars["market"] == "KOSPI"]["date"].unique()))
    days = [d for d in days if d >= pd.Timestamp(START)]
    print(f"  거래일 {len(days):,}일 ({days[0].date()}~{days[-1].date()})")

    with open(IND + "." + mode, "wb") as f:
        pickle.dump(dict(bars=bars, pit=pit, pit_s=pit_s, mem=mem, mem_s=mem_s,
                         allmem=allmem, days=days, dead=dead, mode=mode), f, protocol=4)
    print(f"  캐시 저장 완료 ({mode})")


def _setup(mode="top"):
    with open(IND + "." + mode, "rb") as f:
        D = pickle.load(f)
    store = Store30(D["bars"], D["allmem"])
    idx, _ = C.load_kospi_index()
    phase = C.phase_series(idx)
    cp, _, _ = C.load_coupling_panel()
    coup = C.coupling_series(cp)
    return D, store, phase, coup


def _late_fn():
    """하순 필터 (종목별 tier). 대형주는 OOS 기각 -> 적용 안 함."""
    from jq_calendar_filter import LATE_START, LATE_END
    from jq_mcap_tier import tier_map
    tm_cache = {}

    def f(code, day):
        d = pd.Timestamp(day)
        key = (d.year, d.month)
        if key not in tm_cache:
            tm_cache[key] = P30._rdom_month(d) if hasattr(P30, "_rdom_month") else None
        return False
    return f


def stage2(mode="top"):
    D, store, phase, coup = _setup(mode)
    days, pit, pit_s = D["days"], D["pit"], D["pit_s"]
    kw = dict(phase=phase, coup=coup)
    res = {}

    # 하순 필터 함수 (거래일 기반 rdom + tier)
    from jq_calendar_filter import LATE_START, LATE_END
    from jq_mcap_tier import tier_map
    rd = {}
    by_m = {}
    for d in days:
        by_m.setdefault((d.year, d.month), []).append(d)
    for k, ds in by_m.items():
        n = len(ds)
        for i, d in enumerate(ds):
            rd[d] = (i + 1) - n - 1
    tmc = {}

    def late(code, day):
        r = rd.get(pd.Timestamp(day))
        if r is None or not (LATE_START <= r <= LATE_END):
            return False
        k = (day.year, day.month)
        if k not in tmc:
            tmc[k] = tier_map(day) or {}
        return tmc[k].get(str(code)) in ("소", "중")

    if mode == "smid":
        runs = [("확장유니버스(소중형)", dict(pit=pit_s)),
                ("확장유니버스+하순필터", dict(pit=pit_s, late_filter=late))]
    else:
        runs = [("원스펙(PIT)", dict(pit=pit)),
                ("원스펙+하순필터", dict(pit=pit, late_filter=late))]
    # 재개 가능 — 런 하나 끝날 때마다 저장 (샌드박스 시간제한 대응)
    stp = ST + "." + mode
    if os.path.exists(stp):
        with open(stp, "rb") as f:
            D2 = pickle.load(f)
        res = D2.get("res", {})
    else:
        D2 = {}

    # 지표 캐시 (877종목 사전계산은 무겁다)
    ic = os.path.join(tempfile.gettempdir(), f"jq_bt30_pc_{mode}.pkl")
    if os.path.exists(ic):
        try:
            with open(ic, "rb") as f:
                B._PC.update(pickle.load(f))
            print(f"  지표 캐시 사용 ({len(B._PC)}종목)")
        except Exception as e:
            print(f"  [경고] 지표 캐시 손상({e}) -> py jq_bt30.py pc {mode} 재실행 필요")

    for nm, extra in runs:
        if nm in res:
            p = res[nm]["perf"]["TOTAL"]
            print(f"  [완료] {nm:<26} CAGR {pf(p['CAGR']):>9}")
            continue
        uni = D["allmem"]
        td, ed, meta = B.backtest(store, uni, days, apply_cost=True, **kw, **extra)
        res[nm] = dict(td=td, ed=ed, meta=meta,
                       perf={t: B.perf(ed, td, t) for t in ("L", "S", "TOTAL")})
        p = res[nm]["perf"]["TOTAL"]
        print(f"  {nm:<28} CAGR {pf(p['CAGR']):>9} · MDD {pf(p['MDD']):>8} · "
              f"Sharpe {pf(p['Sharpe'],'{:.2f}',False):>5} · 거래 {p['거래수']:,}")
        D2 = dict(res=res, days=days, dead=D["dead"],
                  n_mem=len(D["mem"]), n_mem_s=len(D["mem_s"]))
        with open(stp, "wb") as f:
            pickle.dump(D2, f, protocol=4)
        print("    저장")   # 지표 캐시는 stage_pc 가 관리한다(여기서 덮어쓰면 손상 위험)
    print(f"  stage2 {'완료' if len(res) == len(runs) else '진행중'} ({len(res)}/{len(runs)})")


def stage_pc(mode="top"):
    """지표 사전계산 — 배치로 나눠 캐시(중단돼도 이어서)."""
    D, store, _, _ = _setup(mode)
    ic = os.path.join(tempfile.gettempdir(), f"jq_bt30_pc_{mode}.pkl")
    if os.path.exists(ic):
        with open(ic, "rb") as f:
            B._PC.update(pickle.load(f))
    done = {k[1] for k in B._PC}
    todo = [(c, m) for c, m in D["allmem"].items() if c not in done]
    print(f"  지표 사전계산: 완료 {len(done)} / 남음 {len(todo)}")
    import time
    t0 = time.time()
    n = 0
    for code, mkt in todo:
        B.precompute(store, mkt, code)
        n += 1
        if time.time() - t0 > 28:      # 시간 안에 저장하고 빠진다
            break
    with open(ic, "wb") as f:
        pickle.dump(B._PC, f, protocol=4)
    tot = len(D["allmem"])
    cur = len({k[1] for k in B._PC})
    print(f"  이번에 {n}종목 처리 -> 누적 {cur}/{tot}  "
          f"{'★완료★' if cur >= tot else '(재실행 필요)'}")


if __name__ == "__main__":
    s = sys.argv[1] if len(sys.argv) > 1 else "1"
    md = sys.argv[2] if len(sys.argv) > 2 else "top"
    {"1": stage1, "pc": stage_pc, "2": stage2}[s](md)
