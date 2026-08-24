#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
entry_signals.py — 진입(매수 타이밍) 상태머신 (설계메모 2026-06-14 정통 기본값)
==============================================================================
정체성: "오를 종목 찾기" 아님(돌파=종목선택 백테스트 FAIL). 재량이 보는 종목에 대해
        '어디서 사고(pivot) · 어디서 틀렸나(손절·무효화)'를 규율하는 진입·리스크 층.
        결정은 사람. 측정은 Track W. 발굴≠매수≠검증.

입력: 주봉 OHLC(+거래량 옵션) · 26주 시장초과 RS · v40 regime state.
판정(최신 주):
  · SEPA 풀 트렌드템플릿 8조건(주봉 10/30/40주선·52주 고저·RS) → 8/8 = 셋업 적합.
  · 베이스(직전 K=10주, 깊이≤25%) 고점 = pivot(매수선).
  · 상태: WATCH→SETUP→NEAR(pivot−3%이내)→BREAKOUT(종가>pivot, 거래량×1.3 확인).
  · 손절: −8%(시황악화 RISK_OFF/NEUTRAL −5.5%) vs 베이스저점 중 타이트. R=(목표−진입)/(진입−손절).
  · regime: RISK_OFF=⛔진입보류 / NEUTRAL=⚠️신중 / RISK_ON=✅ (손절도 타이트화).
무수정: production·heat·발굴트랙. 사용: python entry_signals.py --selftest
"""
import argparse, sys
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

STOP_HARD = 0.08
STOP_TOUGH = 0.055
BASE_K = 10
BASE_DEPTH = 0.25
NEAR_PCT = 0.03
VOLX = 1.3
REGIME_LABEL = {"RISK_OFF": "⛔ 진입보류", "NEUTRAL": "⚠️ 신중", "RISK_ON": "✅"}
STATE_KO = {"WATCH": "관망", "SETUP": "셋업", "NEAR": "트리거임박",
            "BREAKOUT": "돌파확인", "BREAKOUT_LOWVOL": "돌파(거래량미달)"}


def smas(close):
    return (close.rolling(10, min_periods=5).mean(),
            close.rolling(30, min_periods=10).mean(),
            close.rolling(40, min_periods=20).mean())


def trend_template(close, ma10, ma30, ma40, i, rs):
    """Minervini 8조건(주봉). 반환: (conds[8], hi52, lo52)."""
    c = float(close.iloc[i])
    lo = max(0, i - 51)
    hi52 = float(close.iloc[lo:i + 1].max())
    lo52 = float(close.iloc[lo:i + 1].min())
    a40 = ma40.iloc[i]; a40p = ma40.iloc[i - 5] if i >= 5 else np.nan
    conds = [
        (c > ma30.iloc[i]) and (c > ma40.iloc[i]),
        ma30.iloc[i] > ma40.iloc[i],
        bool(pd.notna(a40) and pd.notna(a40p) and a40 > a40p),
        (ma10.iloc[i] > ma30.iloc[i]) and (ma30.iloc[i] > ma40.iloc[i]),
        c > ma10.iloc[i],
        c >= lo52 * 1.30,
        c >= hi52 * 0.75,
        rs > 0,
    ]
    return [bool(x) for x in conds], hi52, lo52


def base_pivot(high, low, i, K=BASE_K, depth=BASE_DEPTH):
    """직전 K주(현재 i 제외) 베이스 고점=pivot, 저점, 깊이 적합."""
    if i - K < 0:
        return None, None, False
    seg_h = high.iloc[i - K:i]; seg_l = low.iloc[i - K:i]
    ph = float(seg_h.max()); pl = float(seg_l.min())
    depth_ok = bool(((ph - pl) / ph) <= depth) if ph > 0 else False
    return ph, pl, depth_ok


def plan(weekly, rs, regime_state, i=None):
    """weekly: DataFrame[open,high,low,close,(volume)]. 반환: 진입 플랜 dict."""
    close, high, low = weekly["close"], weekly["high"], weekly["low"]
    vol = weekly["volume"] if "volume" in weekly.columns else None
    i = len(close) - 1 if i is None else i
    ma10, ma30, ma40 = smas(close)
    conds, hi52, lo52 = trend_template(close, ma10, ma30, ma40, i, rs)
    n = sum(conds)
    ph, pl, depth_ok = base_pivot(high, low, i)
    setup_ok = (n == 8) and depth_ok and ph is not None
    c = float(close.iloc[i])
    tough = regime_state in ("RISK_OFF", "NEUTRAL")
    stoppct = STOP_TOUGH if tough else STOP_HARD
    state = "WATCH"; vol_ok = None
    if setup_ok:
        if c > ph:
            if vol is not None and pd.notna(vol.iloc[i - BASE_K:i].mean()) and vol.iloc[i - BASE_K:i].mean() > 0:
                base_v = float(vol.iloc[i - BASE_K:i].mean())
                vol_ok = bool(vol.iloc[i] >= VOLX * base_v)
                state = "BREAKOUT" if vol_ok else "BREAKOUT_LOWVOL"
            else:
                state = "BREAKOUT"   # 거래량 데이터 없음 → 확인 불가(요건 면제)
        elif c >= ph * (1 - NEAR_PCT):
            state = "NEAR"
        else:
            state = "SETUP"
    actionable = state in ("SETUP", "NEAR", "BREAKOUT", "BREAKOUT_LOWVOL")
    if actionable:
        entry = ph if (state in ("SETUP", "NEAR") and ph) else c
        hard = entry * (1 - stoppct)
        stop = max(hard, pl) if (pl is not None) else hard
        target = hi52 if hi52 > entry * 1.02 else entry + (entry - stop)
        R = (target - entry) / (entry - stop) if entry > stop else np.nan
        entry_o = round(float(entry), 1); stop_o = round(float(stop), 1)
        target_o = round(float(target), 1); R_o = round(float(R), 2) if pd.notna(R) else None
    else:
        # WATCH = 매수 셋업 아님 → 손절/목표/R 미산출(오해 방지). pivot은 '돌파 기준선'으로만 표기.
        entry_o = stop_o = target_o = R_o = None
    return {
        "state": state, "state_ko": STATE_KO.get(state, state),
        "n_setup": int(n), "depth_ok": bool(depth_ok),
        "pivot": round(ph, 1) if ph else None, "base_low": round(pl, 1) if pl else None,
        "entry_ref": entry_o, "stop": stop_o, "target": target_o, "R": R_o,
        "to_pivot_pct": round((ph / c - 1) * 100, 1) if ph else None,
        "vol_ok": vol_ok, "regime": regime_state,
        "regime_label": REGIME_LABEL.get(regime_state, "·"), "stop_pct": stoppct,
    }


def _mk_weekly(closes, vols=None):
    n = len(closes)
    idx = pd.date_range("2024-01-05", periods=n, freq="W-FRI")
    df = pd.DataFrame({"open": closes, "high": [c * 1.01 for c in closes],
                       "low": [c * 0.99 for c in closes], "close": closes}, index=idx)
    df["volume"] = vols if vols is not None else [1_000_000] * n
    return df


def _selftest():
    ok = 0
    # 완만 상승 55주 + 완만 상승 베이스 5주(현재가 pivot 직하) → 셋업/임박
    rise = list(np.linspace(100, 195, 55))
    tail = [196.0, 197.0, 198.0, 199.0, 200.0]
    closes = rise + tail
    w = _mk_weekly(closes)
    p_setup = plan(w, rs=0.3, regime_state="RISK_ON")
    assert p_setup["state"] in ("SETUP", "NEAR"), f"셋업단계 기대, got {p_setup}"; ok += 1
    assert p_setup["n_setup"] == 8, f"트렌드템플릿 8/8 기대 {p_setup['n_setup']}"; ok += 1
    # 돌파 주 추가(종가 210 > pivot, 거래량 스파이크)
    vols = [1_000_000] * len(closes) + [3_000_000]
    w2 = _mk_weekly(closes + [210.0], vols)
    p_bo = plan(w2, rs=0.3, regime_state="RISK_ON")
    assert p_bo["state"] == "BREAKOUT", f"돌파 기대 {p_bo}"; ok += 1
    assert p_bo["stop"] < p_bo["entry_ref"] < p_bo["target"], "손절<진입<목표 위반"; ok += 1
    assert p_bo["R"] and p_bo["R"] > 0, "R 양수 위반"; ok += 1
    # 거래량 미달 → LOWVOL
    w3 = _mk_weekly(closes + [210.0], [1_000_000] * len(closes) + [1_000_000])
    assert plan(w3, 0.3, "RISK_ON")["state"] == "BREAKOUT_LOWVOL", "거래량미달 미검출"; ok += 1
    # 하락추세 → WATCH
    down = _mk_weekly(list(np.linspace(200, 100, 60)))
    assert plan(down, -0.2, "RISK_ON")["state"] == "WATCH", "하락=WATCH 위반"; ok += 1
    # regime: RISK_OFF → 손절 타이트(5.5%) + 라벨
    p_off = plan(w2, 0.3, "RISK_OFF")
    assert abs(p_off["stop_pct"] - 0.055) < 1e-9 and "보류" in p_off["regime_label"], "RISK_OFF 처리 오류"; ok += 1
    # 손절 수계산: max(진입*(1-stop), 베이스저점)
    e = p_bo["entry_ref"]; expect = max(e * (1 - 0.08), p_bo["base_low"])
    assert abs(p_bo["stop"] - round(expect, 1)) < 0.2, f"손절 수계산 {p_bo['stop']} vs {expect}"; ok += 1
    print(f"✅ entry_signals 셀프테스트 통과 ({ok}/9): 셋업·8조건·돌파·손익순서·R·거래량·WATCH·regime·손절수계산")


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest()
    else:
        _selftest()
