# -*- coding: utf-8 -*-
"""
jq_backtest_core.py — 백테스트 엔진 (규칙은 jq_paper_core 에서 import. 재구현 금지)

★ 편향 방지 (이게 백테스트의 전부다) ★
  1) look-ahead 금지
     · 시점 t의 신호는 **t 종가까지의 데이터만** 사용.
     · 체결은 **t+1 시가**. (당일 종가 신호 → 당일 종가 체결은 금지)
     · 주봉 MA는 '그 날까지 확정된 주봉'만 사용 (미완성 주봉 금지).
     · 국면/커플링 지표는 전부 롤링(과거만).
  2) 생존편향 — 제거 불가. **측정해서 명시한다.** 은폐 금지.
  3) 거래비용 — 매수수수료·매도수수료·증권거래세·슬리피지. 비용 유/무 둘 다 산출.
  4) IS/OOS 분리 — 앞 70% / 뒤 30%. **최종 판정은 OOS 기준.**

투자자문 아님. 결정·책임은 본인.
"""
import os, sys, math
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jq_paper_core as C
from jq_paper_core import (CFG, PriceStore, passes_L, passes_S, check_exit_core,
                           size_position, atr_series, ma_slope_series,
                           weekly_ma_slope_daily, isnan)

TRADE_COLS = ["track", "code", "name", "market", "entry_date", "entry_price", "qty",
              "init_stop", "exit_date", "exit_price", "exit_rule", "days_held",
              "gross_pnl", "cost", "net_pnl", "r_multiple", "ret_pct",
              "phase_trend", "phase_vol", "phase_dd", "coupling_state", "score"]


# ═══════════════════════════════════════════════════════════════════════════
# 지표 사전계산 — 종목별 전체 시계열 (벡터화). 값은 스칼라 함수와 동치(셀프테스트 확인).
# ═══════════════════════════════════════════════════════════════════════════
_PC = {}   # 지표 캐시 (동일 파라미터 재계산 방지 — 격자/워크포워드에서 수십 번 호출됨)
# 지표 캐시는 임시폴더에 둔다 (대용량 · 재생성 가능 · 산출물 아님).
import tempfile
_IND_CACHE = os.path.join(tempfile.gettempdir(), "jq_ind_cache.pkl")


def load_ind_cache():
    """지표 캐시를 디스크에서 복원 (긴 백테스트를 나눠 돌릴 때 재계산 방지).
    원본 패널이 바뀌면 무효화된다."""
    import pickle
    global _PC
    try:
        src = os.path.join(C.BASE, "kospi_pit_daily.csv")
        sig = os.path.getmtime(src)
        if os.path.exists(_IND_CACHE):
            with open(_IND_CACHE, "rb") as f:
                d = pickle.load(f)
            if d.get("sig") == sig:
                _PC.update(d["pc"])
                return True
    except Exception:
        pass
    return False


def save_ind_cache():
    import pickle
    try:
        src = os.path.join(C.BASE, "kospi_pit_daily.csv")
        with open(_IND_CACHE, "wb") as f:
            pickle.dump(dict(sig=os.path.getmtime(src), pc=_PC), f, protocol=4)
    except Exception:
        pass


def precompute(store, market, code, p=None):
    """
    반환 DataFrame[date, open, high, low, close, atr, ma_s, slope_s, ma_w, slope_w]
    전부 t 시점까지의 정보만 사용 (rolling/shift). look-ahead 없음.
    """
    p = p or {}
    key = (market, code, p.get("MA_SHORT", CFG["S"]["MA_SHORT"]),
           p.get("SLOPE_DAYS", CFG["S"]["SLOPE_DAYS"]),
           p.get("MA_WEEK", CFG["L"]["MA_WEEK"]),
           p.get("SLOPE_WEEKS", CFG["L"]["SLOPE_WEEKS"]))
    if key in _PC:
        return _PC[key]
    g = store.full(market, code)
    if g is None or len(g) < CFG["MIN_BARS"]:
        _PC[key] = None
        return None
    ma_short = p.get("MA_SHORT", CFG["S"]["MA_SHORT"])
    slope_days = p.get("SLOPE_DAYS", CFG["S"]["SLOPE_DAYS"])
    ma_week = p.get("MA_WEEK", CFG["L"]["MA_WEEK"])
    slope_wk = p.get("SLOPE_WEEKS", CFG["L"]["SLOPE_WEEKS"])

    d = g.copy().reset_index(drop=True)
    d["atr"] = atr_series(d["high"], d["low"], d["close"], CFG["ATR_N"]).values
    ma_s, sl_s = ma_slope_series(d["close"], ma_short, slope_days)
    d["ma_s"], d["slope_s"] = ma_s.values, sl_s.values
    mw, sw = weekly_ma_slope_daily(d["date"], d["close"], ma_week, slope_wk)
    d["ma_w"], d["slope_w"] = mw.values, sw.values

    # ★ 진입 판정을 봉 단위로 미리 계산해 둔다 (성능).
    #   규칙을 재구현하지 않는다 — jq_paper_core 의 passes_L / passes_S 를 그대로 호출한다.
    #   (일 x 종목) 루프 안에서 반복 호출하던 것을 종목별 1회 선계산으로 옮긴 것뿐.
    #   값은 완전히 동일하며, Single Source of Truth 는 유지된다.
    cl = d["close"].to_numpy(float)
    maw = d["ma_w"].to_numpy(float)
    slw = d["slope_w"].to_numpy(float)
    mas = d["ma_s"].to_numpy(float)
    sls = d["slope_s"].to_numpy(float)
    n = len(d)
    pL = np.zeros(n, bool)
    sL = np.full(n, np.nan)
    pS = np.zeros(n, bool)
    sS = np.full(n, np.nan)
    htf = CFG["S"]["REQUIRE_HTF"]
    for i in range(n):
        ok, _, sc = passes_L(cl[i], maw[i], slw[i])
        pL[i] = ok
        if not isnan(sc):
            sL[i] = sc
        aw = None if isnan(maw[i]) else (cl[i] > maw[i])
        ok2, _, sc2 = passes_S(cl[i], mas[i], sls[i], aw, htf)
        pS[i] = ok2
        if not isnan(sc2):
            sS[i] = sc2
    d["pass_L"], d["score_L"] = pL, sL
    d["pass_S"], d["score_S"] = pS, sS

    _PC[key] = d
    return d


# ═══════════════════════════════════════════════════════════════════════════
# 거래비용
# ═══════════════════════════════════════════════════════════════════════════
def buy_cost(price, qty, cost=None):
    c = cost or CFG["COST"]
    amt = price * qty
    return amt * (c["BUY_FEE"] + c["SLIPPAGE"])


def sell_cost(price, qty, cost=None):
    c = cost or CFG["COST"]
    amt = price * qty
    return amt * (c["SELL_FEE"] + c["TAX"] + c["SLIPPAGE"])


# ═══════════════════════════════════════════════════════════════════════════
# 백테스트 본체
# ═══════════════════════════════════════════════════════════════════════════
_INDC = {}   # (universe, params) -> (ind, lack)  구축 비용이 커서 캐시한다


def _build_ind(store, universe, P):
    ind, lack = {}, []
    for code, mkt in universe.items():
        d = precompute(store, mkt, code, P)
        if d is None:
            lack.append(code)
            continue
        ind[code] = dict(
            mkt=mkt,
            pos={np.datetime64(x, "ns"): i for i, x in enumerate(d["date"].values)},
            o=d["open"].to_numpy(float), c=d["close"].to_numpy(float),
            atr=d["atr"].to_numpy(float), ma_s=d["ma_s"].to_numpy(float),
            slope_s=d["slope_s"].to_numpy(float), ma_w=d["ma_w"].to_numpy(float),
            slope_w=d["slope_w"].to_numpy(float),
            pass_L=d["pass_L"].to_numpy(bool), score_L=d["score_L"].to_numpy(float),
            pass_S=d["pass_S"].to_numpy(bool), score_S=d["score_S"].to_numpy(float),
            last_dt=pd.Timestamp(d["date"].iloc[-1]))   # 마지막 거래일 = 상폐 판정용
    return ind, lack


def backtest(store, universe, days, params=None, halloween=False, half_tp=False,
             apply_cost=True, phase=None, coup=None, verbose=False,
             pit=None, late_filter=None):
    """
    universe : {code: market}
    days     : 정렬된 거래일 리스트 (신호 판정일). 체결은 그 다음 거래일 시가.
    params   : 파라미터 오버라이드 (민감도 격자용)
    pit      : {(year,month): {code: market}} — **PIT 유니버스**.
               주면 그 달에 편입된 종목만 신규 진입 가능(선택편향 차단).
               기존 보유는 유니버스에서 빠져도 규칙대로 청산될 때까지 보유(현실적).
    late_filter : (code, date) -> bool. True 면 그날 그 종목 신규진입 보류(하순 필터).
    반환 (trades DataFrame, equity DataFrame, stats dict)
    """
    P = params or {}
    cfgL = dict(CFG["L"]); cfgL.update({k: v for k, v in P.items() if k in cfgL})
    cfgS = dict(CFG["S"]); cfgS.update({k: v for k, v in P.items() if k in cfgS})
    cfgs = {"L": cfgL, "S": cfgS}
    cost = dict(CFG["COST"])
    if not apply_cost:
        cost = dict(BUY_FEE=0.0, SELL_FEE=0.0, TAX=0.0, SLIPPAGE=0.0)

    # --- 지표 사전계산 + numpy 전개 (한 번만. 동일 유니버스/파라미터면 재사용) ---
    # ind 구축(수백만 dict 엔트리)은 백테스트마다 반복하면 30년 구간에서 치명적이다.
    _ck = (id(universe), tuple(sorted(P.items())))
    if _ck in _INDC:
        ind, lack = _INDC[_ck]
    else:
        ind, lack = _build_ind(store, universe, P)
        _INDC[_ck] = (ind, lack)
    if False:
      for code, mkt in universe.items():
        d = precompute(store, mkt, code, P)
        if d is None:
            lack.append(code)
            continue
        # 성능: pandas .iloc 은 (일 x 종목) 루프에서 너무 느리다 -> numpy 배열로 전개.
        # 값은 동일하다 (셀프테스트에서 스칼라 함수와 동치 확인됨).
        ind[code] = dict(
            mkt=mkt,
            pos={np.datetime64(x, "ns"): i for i, x in enumerate(d["date"].values)},
            o=d["open"].to_numpy(float), c=d["close"].to_numpy(float),
            atr=d["atr"].to_numpy(float), ma_s=d["ma_s"].to_numpy(float),
            slope_s=d["slope_s"].to_numpy(float), ma_w=d["ma_w"].to_numpy(float),
            slope_w=d["slope_w"].to_numpy(float),
            pass_L=d["pass_L"].to_numpy(bool), score_L=d["score_L"].to_numpy(float),
            pass_S=d["pass_S"].to_numpy(bool), score_S=d["score_S"].to_numpy(float))

    day_set = [pd.Timestamp(x) for x in days]
    month_first = set()
    seen = set()
    for dd in day_set:
        k = (dd.year, dd.month)
        if k not in seen:
            seen.add(k)
            month_first.add(dd)

    cash = {t: CFG["INITIAL_CAPITAL"] * CFG["TRACK_ALLOC"][t] for t in ("L", "S")}
    open_pos = {"L": {}, "S": {}}
    trades, eq_rows = [], []
    pending_buy, pending_sell = [], []       # t 신호 → t+1 시가 체결

    # 국면/커플링 조회맵 — 7천행 iterrows 를 매 호출마다 돌리면 안 된다 (캐시).
    ph_map = _phase_map(phase)
    cp_map = _coup_map(coup)

    for di, today in enumerate(day_set):
        # ── 1) 전일 신호의 체결 (오늘 시가) — look-ahead 차단의 핵심 ──
        for od in pending_sell:
            code, track = od["code"], od["track"]
            p = open_pos[track].get(code)
            if not p:
                continue
            E = ind.get(code)
            if E is None:
                continue
            i = _ix(ind, code, today)
            if i is None:
                if od.get("rule") != "SELL_DELIST":
                    continue
                px = float(E["c"][-1])         # 상폐 -> 마지막 실거래 종가
            else:
                px = float(E["o"][i])
                if isnan(px) or px <= 0:
                    px = float(E["c"][i])      # 시가 없으면 종가 (실데이터, 추정 아님)
            qty = min(od["qty"], p["qty"])
            gross = (px - p["entry_price"]) * qty
            cst = sell_cost(px, qty, cost) + p["entry_cost_per_share"] * qty
            cash[track] += px * qty - sell_cost(px, qty, cost)
            r_unit = p["entry_price"] - p["init_stop"]
            pr = ph_map.get(today, {})
            trades.append({
                "track": track, "code": code, "name": store.name(code),
                "market": ind[code]["mkt"], "entry_date": p["entry_date"],
                "entry_price": round(p["entry_price"], 1), "qty": qty,
                "init_stop": round(p["init_stop"], 1),
                "exit_date": today.date().isoformat(), "exit_price": round(px, 1),
                "exit_rule": od["rule"], "days_held": p["days_held"],
                "gross_pnl": round(gross, 0), "cost": round(cst, 0),
                "net_pnl": round(gross - cst, 0),
                "r_multiple": round((px - p["entry_price"]) / r_unit, 3) if r_unit > 0 else "",
                "ret_pct": round((px / p["entry_price"] - 1) * 100, 2),
                "phase_trend": pr.get("trend", "데이터부족"),
                "phase_vol": pr.get("vol", "데이터부족"),
                "phase_dd": pr.get("dd", "데이터부족"),
                "coupling_state": cp_map.get(today, "데이터부족"),
                "score": p.get("score", "")})
            p["qty"] -= qty
            if p["qty"] <= 0:
                open_pos[track].pop(code, None)
            else:
                p["half_sold"] = 1
        pending_sell = []

        for od in pending_buy:
            code, track = od["code"], od["track"]
            i = _ix(ind, code, today)
            if i is None:
                continue
            E = ind[code]
            px = float(E["o"][i])
            if isnan(px) or px <= 0:
                px = float(E["c"][i])
            atr = float(E["atr"][i])
            if isnan(atr) or atr <= 0:
                continue
            # ★ 2%룰은 '현재 자산'의 2% 다 (안티-마틴게일 · fixed-fractional).
            #   초기자본 고정으로 하면 자산이 줄어도 베팅이 그대로라 죽음의 나선이 된다.
            #   (30년 실측: 초기자본 고정 시 MDD -99%. 강세장 6.5년에선 안 드러났던 버그.)
            _pv = 0.0
            for _c, _p in open_pos[track].items():
                _i = _ix(ind, _c, today)
                _E = ind.get(_c)
                if _E is None:
                    continue
                _pv += (float(_E["c"][_i]) if _i is not None
                        else float(_E["c"][-1])) * _p["qty"]
            cap = cash[track] + _pv
            qty, stop, _, _ = size_position(cap, px, atr, cfgs[track]["ATR_STOP"],
                                            od["exposure"])
            if qty <= 0:
                continue
            bc = buy_cost(px, qty, cost)
            if px * qty + bc > cash[track]:
                qty = int((cash[track] - bc) // px) if px > 0 else 0
                if qty <= 0:
                    continue
                bc = buy_cost(px, qty, cost)
            cash[track] -= px * qty + bc
            open_pos[track][code] = dict(
                code=code, track=track, entry_date=today.date().isoformat(),
                entry_price=px, qty=qty, stop=stop, init_stop=stop,
                target_1r=px + (px - stop), high_watermark=px, atr=atr,
                half_sold=0, days_held=0, score=od["score"],
                entry_cost_per_share=bc / qty if qty else 0.0)
        pending_buy = []

        # ── 2) 오늘 종가로 상태 갱신 + 청산 신호 생성 (체결은 내일 시가) ──
        for track in ("L", "S"):
            for code, p in list(open_pos[track].items()):
                i = _ix(ind, code, today)
                if i is None:
                    # ★ 상장폐지/거래정지 — 그 종목의 마지막 거래일이 지났는데 봉이 없다.
                    #   이걸 방치하면 포지션이 영원히 슬롯을 점유해 신규진입이 막힌다
                    #   (실측 사고: 2008년 이후 거래 0건). 마지막 종가로 강제 청산한다.
                    #   ⚠️ 한계: 실제 상폐는 정리매매에서 더 떨어지는 경우가 많다.
                    #      마지막 종가로 털면 **실제보다 낙관적**이다. 결과문서에 명시.
                    E = ind.get(code)
                    if E is not None and today > E["last_dt"]:
                        pending_sell.append(dict(code=code, track=track,
                                                 qty=p["qty"], rule="SELL_DELIST"))
                    continue
                E = ind[code]
                cl = float(E["c"][i])
                p["high_watermark"] = max(p["high_watermark"], cl)
                p["days_held"] += 1
                atr = float(E["atr"][i])
                ma_s = float(E["ma_s"][i])
                ex = check_exit_core(p, cl, atr, ma_s, cfgs[track], track, half_tp=half_tp)
                if ex:
                    pending_sell.append(dict(code=code, track=track,
                                             qty=ex[3], rule=ex[0]))

        # ── 3) 진입 신호 (오늘 종가 기준) → 내일 시가 체결 ──
        exposure = _exposure(today, ph_map, halloween)
        for track in ("L", "S"):
            if track == "L" and today not in month_first:
                continue
            slots = cfgs[track]["MAX_POSITIONS"] - len(open_pos[track])
            if slots <= 0:
                continue
            pit_m = None if pit is None else pit.get((today.year, today.month), {})
            # ★ 성능: PIT 가 있으면 그 달 편입 종목(<=160)만 훑는다.
            #   전체 유니버스(수백~수천)를 매일 훑으면 30년 백테스트가 안 끝난다.
            scan = ind.keys() if pit_m is None else pit_m.keys()
            cand = []
            for code in scan:
                if code not in ind:
                    continue
                if code in open_pos[track]:
                    continue
                # ★ 하순 필터 (종목별 tier). 대형주는 OOS 기각 -> 통과
                if late_filter is not None and late_filter(code, today):
                    continue
                i = _ix(ind, code, today)
                if i is None:
                    continue
                E = ind[code]
                a_ = E["atr"][i]
                if isnan(a_) or a_ <= 0:
                    continue
                if E["pass_" + track][i]:
                    sc = E["score_" + track][i]
                    if not isnan(sc):
                        cand.append((float(sc), code))
            for sc, code in sorted(cand, key=lambda x: -x[0])[:slots]:
                pending_buy.append(dict(code=code, track=track, score=sc,
                                        exposure=exposure))

        # ── 4) 자산 기록 ──
        tot = 0.0
        for track in ("L", "S"):
            pv = 0.0
            for code, p in open_pos[track].items():
                i = _ix(ind, code, today)
                E = ind.get(code)
                if i is not None:
                    _v = float(E["c"][i])
                elif E is not None:
                    _v = float(E["c"][-1])     # 거래정지/상폐 -> 마지막 실거래가
                else:
                    _v = p["entry_price"]
                pv += _v * p["qty"]
            eq = cash[track] + pv
            tot += eq
            eq_rows.append({"date": today, "track": track, "cash": cash[track],
                            "position_value": pv, "total_equity": eq,
                            "coupling_state": cp_map.get(today, "데이터부족"),
                            "phase_trend": ph_map.get(today, {}).get("trend", "데이터부족"),
                            "phase_vol": ph_map.get(today, {}).get("vol", "데이터부족"),
                            "phase_dd": ph_map.get(today, {}).get("dd", "데이터부족")})
        eq_rows.append({"date": today, "track": "TOTAL", "cash": sum(cash.values()),
                        "position_value": tot - sum(cash.values()), "total_equity": tot,
                        "coupling_state": cp_map.get(today, "데이터부족"),
                        "phase_trend": ph_map.get(today, {}).get("trend", "데이터부족"),
                        "phase_vol": ph_map.get(today, {}).get("vol", "데이터부족"),
                        "phase_dd": ph_map.get(today, {}).get("dd", "데이터부족")})

    # 종료 시점 미청산 포지션 → 마지막 종가로 평가청산 (원장에 EOD로 표기)
    last = day_set[-1]
    for track in ("L", "S"):
        for code, p in list(open_pos[track].items()):
            i = _ix(ind, code, last)
            if i is None:
                continue
            px = float(ind[code]["c"][i])
            gross = (px - p["entry_price"]) * p["qty"]
            cst = sell_cost(px, p["qty"], cost) + p["entry_cost_per_share"] * p["qty"]
            r_unit = p["entry_price"] - p["init_stop"]
            pr = ph_map.get(last, {})
            trades.append({
                "track": track, "code": code, "name": store.name(code),
                "market": ind[code]["mkt"], "entry_date": p["entry_date"],
                "entry_price": round(p["entry_price"], 1), "qty": p["qty"],
                "init_stop": round(p["init_stop"], 1),
                "exit_date": last.date().isoformat(), "exit_price": round(px, 1),
                "exit_rule": "EOD_미청산", "days_held": p["days_held"],
                "gross_pnl": round(gross, 0), "cost": round(cst, 0),
                "net_pnl": round(gross - cst, 0),
                "r_multiple": round((px - p["entry_price"]) / r_unit, 3) if r_unit > 0 else "",
                "ret_pct": round((px / p["entry_price"] - 1) * 100, 2),
                "phase_trend": pr.get("trend", "데이터부족"),
                "phase_vol": pr.get("vol", "데이터부족"),
                "phase_dd": pr.get("dd", "데이터부족"),
                "coupling_state": cp_map.get(last, "데이터부족"),
                "score": p.get("score", "")})

    td = pd.DataFrame(trades, columns=TRADE_COLS)
    ed = pd.DataFrame(eq_rows)
    return td, ed, dict(데이터부족종목=len(lack), 데이터부족리스트=lack,
                        유니버스=len(universe), 사용종목=len(ind))


def _ix(ind, code, day):
    """그 날짜의 배열 인덱스. 없으면 None."""
    e = ind.get(code)
    if e is None:
        return None
    return e["pos"].get(np.datetime64(pd.Timestamp(day), "ns"))


_PHM, _CPM = {}, {}


def _phase_map(phase):
    if phase is None:
        return {}
    k = id(phase)
    if k not in _PHM:
        _PHM[k] = {pd.Timestamp(d): dict(trend=t, vol=v, dd=dd)
                   for d, t, v, dd in zip(phase["date"], phase["trend"],
                                          phase["vol"], phase["dd"])}
    return _PHM[k]


def _coup_map(coup):
    if coup is None:
        return {}
    k = id(coup)
    if k not in _CPM:
        _CPM[k] = {pd.Timestamp(d): str(s)
                   for d, s in zip(coup["date"], coup["state"])}
    return _CPM[k]


def _exposure(today, ph_map, halloween):
    """
    백테스트 노출배수.
    ⚠️ 실전 엔진의 macro_gate는 breadth_features.csv(2026-04~) / VKOSPI를 쓰는데,
       그 데이터는 백테스트 구간(2019~) 대부분에서 **존재하지 않는다**.
       없는 데이터를 만들어 쓰면 안 되므로, 백테스트에서는 매크로 게이트를 **미적용(1.0)** 한다.
       → 이 차이는 백테스트_결과.md 에 명시한다. (실전≠백테스트인 유일한 지점)
    할로윈만 명시적 옵션으로 적용한다.
    """
    m = 1.0
    if halloween and pd.Timestamp(today).month in (5, 6, 7, 8, 9, 10):
        m *= CFG["HALLOWEEN_SUMMER_W"]
    return m


# ═══════════════════════════════════════════════════════════════════════════
# 성과 지표
# ═══════════════════════════════════════════════════════════════════════════
def perf(eq, trades, track="TOTAL", ann=252):
    e = eq[eq["track"] == track].sort_values("date")
    if len(e) < 3:
        return None
    v = e["total_equity"].values.astype(float)
    ret = pd.Series(v).pct_change().dropna()
    n = len(v)
    yrs = n / ann
    cum = v[-1] / v[0] - 1
    cagr = (v[-1] / v[0]) ** (1 / yrs) - 1 if yrs > 0 and v[0] > 0 else float("nan")
    dd = v / np.maximum.accumulate(v) - 1
    sharpe = float(ret.mean() / ret.std() * math.sqrt(ann)) if ret.std() > 0 else float("nan")

    t = trades if track == "TOTAL" else trades[trades["track"] == track]
    t = t.copy()
    net = pd.to_numeric(t["net_pnl"], errors="coerce").dropna()
    wins, losses = net[net > 0], net[net <= 0]
    r = pd.to_numeric(t["r_multiple"], errors="coerce").dropna()
    # 최대 연속손실
    streak = mx = 0
    for x in net.values:
        if x <= 0:
            streak += 1
            mx = max(mx, streak)
        else:
            streak = 0
    return dict(
        CAGR=cagr, 누적수익률=cum, MDD=float(dd.min()), Sharpe=sharpe,
        거래수=int(len(t)),
        승률=float(len(wins) / len(net)) if len(net) else float("nan"),
        손익비=float(wins.mean() / abs(losses.mean()))
        if len(wins) and len(losses) and losses.mean() != 0 else float("nan"),
        평균R=float(r.mean()) if len(r) else float("nan"),
        평균보유일=float(pd.to_numeric(t["days_held"], errors="coerce").mean())
        if len(t) else float("nan"),
        최대연속손실=int(mx),
        총손익=float(net.sum()) if len(net) else 0.0,
        총비용=float(pd.to_numeric(t["cost"], errors="coerce").sum()) if len(t) else 0.0)


def benchmark(store, market, days, ann=252):
    """벤치마크 = 해당 시장 시총상위 종목 동일가중 buy&hold (실데이터만)."""
    codes = store.universe(market, CFG["UNIVERSE_TOP_N"] if market == "KOSPI"
                           else CFG["KOSDAQ_TOP_N"])
    day_set = [pd.Timestamp(d) for d in days]
    series = []
    for c in codes:
        g = store.full(market, c)
        if g is None:
            continue
        s = g.set_index("date")["close"].reindex(day_set)
        if s.notna().sum() < len(day_set) * 0.9:
            continue
        series.append(s / s.dropna().iloc[0])
    if not series:
        return None
    m = pd.concat(series, axis=1).mean(axis=1).dropna()
    if len(m) < 3:
        return None
    v = m.values
    ret = pd.Series(v).pct_change().dropna()
    yrs = len(v) / ann
    dd = v / np.maximum.accumulate(v) - 1
    return dict(CAGR=(v[-1] / v[0]) ** (1 / yrs) - 1 if yrs > 0 else float("nan"),
                누적수익률=v[-1] / v[0] - 1, MDD=float(dd.min()),
                Sharpe=float(ret.mean() / ret.std() * math.sqrt(ann))
                if ret.std() > 0 else float("nan"),
                종목수=len(series), 곡선=m)


# ═══════════════════════════════════════════════════════════════════════════
# 통계 검정 (scipy 없이) — 검증① 통합용
# ═══════════════════════════════════════════════════════════════════════════
def ttest_1samp(x, mu=0.0):
    x = np.asarray(pd.Series(x).dropna(), float)
    n = len(x)
    if n < 3 or x.std(ddof=1) == 0:
        return float("nan"), float("nan"), n, (float("nan"), float("nan"))
    se = x.std(ddof=1) / math.sqrt(n)
    t = (x.mean() - mu) / se
    p = 2.0 * _t_sf(abs(t), n - 1)
    ci = (x.mean() - 1.96 * se, x.mean() + 1.96 * se)
    return float(t), float(p), n, ci


def _t_sf(t, df):
    x = df / (df + t * t)
    return 0.5 * _betainc(df / 2.0, 0.5, x)


def _betainc(a, b, x):
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lb = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(a * math.log(x) + b * math.log(1 - x) - lb)
    if x < (a + 1) / (a + b + 2):
        return front * _betacf(a, b, x) / a
    return 1.0 - math.exp(b * math.log(1 - x) + a * math.log(x) - lb) * _betacf(b, a, 1 - x) / b


def _betacf(a, b, x, itmax=300, eps=1e-12):
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    d = 1.0 / (d if abs(d) > 1e-30 else 1e-30)
    h = d
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > 1e-30 else 1e-30)
        c = 1.0 + aa / (c if abs(c) > 1e-30 else 1e-30)
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        d = 1.0 / (d if abs(d) > 1e-30 else 1e-30)
        c = 1.0 + aa / (c if abs(c) > 1e-30 else 1e-30)
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h



def survivorship_report(store):
    """생존편향 측정 — 제거는 못 한다. 정직하게 재본다."""
    out = {}
    for mkt in ("KOSPI", "KOSDAQ"):
        p = store.panels.get(mkt)
        if p is None:
            out[mkt] = None
            continue
        last = p["date"].max()
        lastper = p.groupby("code")["date"].max()
        firstper = p.groupby("code")["date"].min()
        dead = int((lastper < last - pd.Timedelta(days=30)).sum())
        new = int((firstper > p["date"].min() + pd.Timedelta(days=30)).sum())
        out[mkt] = dict(종목수=int(p["code"].nunique()),
                        중도소멸=dead, 중도상장=new,
                        패널종료일=str(last.date()))
    return out
