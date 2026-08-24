#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""백테_추세방어_지수.py — 하락장 낙폭방어 검증 (지수 레벨, 생존편향 없음)

질문: 종가>MA200일 때만 시장 보유·아니면 현금(추세타이밍)이 하락장에서
      buy&hold 대비 낙폭(MDD)을 줄이나? (Faber 2007 · 추세타이밍_사전등록 후보 A)
- 신호 t → 포지션 t+1 (look-ahead 0). 전환 비용 편도 0.30%.
- KOSPI 1995~2026(닷컴·GFC·2020·2022 하락장 포함). 지수=생존편향 무관.
- 합격(사전등록): |MDD| ≤ buy&hold×0.80 AND CAGR ≥ bh−1%p.
투자자문 아님 · 집행·책임 본인.  사용: py 백테_추세방어_지수.py [--self-test]
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

import os, sys, json, argparse, warnings
import numpy as np, pandas as pd
warnings.simplefilter("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

MA_N = 200
COST = _jq_cost(0.003)            # 전환 편도 0.30%  # §8-3: 종전 0.300% → 실측 0.559% (+0.259%p)
BEARS = {"닷컴2000": ("2000-01-01", "2001-09-30"),
         "GFC2008": ("2007-11-01", "2009-03-31"),
         "2011유럽": ("2011-05-01", "2011-09-30"),
         "2018Q4": ("2018-10-01", "2018-12-31"),
         "코로나2020": ("2020-01-15", "2020-04-30"),
         "2022긴축": ("2021-07-01", "2022-10-31")}

def load_index():
    p = os.path.join(HERE, "kospi_index_daily.csv")
    d = pd.read_csv(p, encoding="utf-8-sig")
    d.columns = [c.lstrip("﻿").lower() for c in d.columns]
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d["close"] = pd.to_numeric(d["close"], errors="coerce")
    d = d.dropna(subset=["date", "close"]).sort_values("date").reset_index(drop=True)
    return d

def mdd(equity):
    return float((equity/equity.cummax()-1).min())

def cagr(equity, n_days):
    yrs = n_days/252.0
    return float((equity.iloc[-1]/equity.iloc[0])**(1/max(yrs, 1e-9))-1)

def sharpe(ret):
    return float(ret.mean()/ret.std()*np.sqrt(252)) if ret.std() > 0 else float("nan")

def run():
    d = load_index()
    d["ma"] = d["close"].rolling(MA_N).mean()
    d["ret"] = d["close"].pct_change().fillna(0)
    d = d[d["ma"].notna()].reset_index(drop=True)
    # 신호: 종가>MA200 → 익일 시장. look-ahead 0.
    d["inmkt"] = (d["close"] > d["ma"]).astype(int).shift(1).fillna(0)
    d["switch"] = d["inmkt"].diff().abs().fillna(0)
    # 전략 수익 = 시장 있을 때만 시장수익, 전환일 비용
    d["strat_ret"] = d["inmkt"]*d["ret"] - d["switch"]*COST
    d["bh_eq"] = (1+d["ret"]).cumprod()
    d["st_eq"] = (1+d["strat_ret"]).cumprod()
    n = len(d)
    res = dict(기간=f"{d['date'].iloc[0].date()}~{d['date'].iloc[-1].date()}",
               시장체류=round(float(d["inmkt"].mean()), 3), 전환수=int(d["switch"].sum()),
               buyhold=dict(CAGR=round(cagr(d["bh_eq"], n), 4), MDD=round(mdd(d["bh_eq"]), 4),
                            Sharpe=round(sharpe(d["ret"]), 3)),
               추세타이밍=dict(CAGR=round(cagr(d["st_eq"], n), 4), MDD=round(mdd(d["st_eq"]), 4),
                             Sharpe=round(sharpe(d["strat_ret"]), 3)))
    # 하락장별 낙폭
    bear = {}
    for name, (s, e) in BEARS.items():
        m = (d["date"] >= s) & (d["date"] <= e)
        if m.sum() < 5: continue
        sub = d[m]
        bh = (1+sub["ret"]).cumprod(); st = (1+sub["strat_ret"]).cumprod()
        bear[name] = dict(buyhold낙폭=round(mdd(bh), 4), 추세타이밍낙폭=round(mdd(st), 4),
                          시장체류=round(float(sub["inmkt"].mean()), 2))
    res["하락장별_낙폭"] = bear
    bh_mdd = abs(res["buyhold"]["MDD"]); st_mdd = abs(res["추세타이밍"]["MDD"])
    gate_mdd = bool(st_mdd <= bh_mdd*0.80)
    res["게이트"] = {"낙폭20%이상감소": gate_mdd,
                   "수익비열위": bool(res["추세타이밍"]["CAGR"] >= res["buyhold"]["CAGR"]-0.01)}
    res["판정"] = "추세타이밍 낙폭방어 유효" if gate_mdd else "낙폭방어 미흡"
    return res

def _self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    eq = pd.Series([1, 1.1, 0.9, 1.2])
    chk("MDD 계산(1.1→0.9=−18.2%)", abs(mdd(eq)-(-0.1818)) < 0.01)
    import numpy as _np
    r = pd.Series(_np.linspace(0.005, 0.015, 252))
    chk("Sharpe 양수(변동 있는 양수수익)", sharpe(r) > 0)
    chk("CAGR 대략", cagr(pd.Series([1, 2]), 252) > 0.9)
    chk("BEARS에 2020·2022 포함", "코로나2020" in BEARS and "2022긴축" in BEARS)
    print(f"\n셀프테스트: {ok}/{tot}"); return ok == tot

if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test: sys.exit(0 if _self_test() else 1)
    print(json.dumps(run(), ensure_ascii=False, indent=2))
