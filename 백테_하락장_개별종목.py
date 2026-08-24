#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""백테_하락장_개별종목.py — ③ 하락장 포함 개별종목 검증 심화

기존(백테_추세청산_개별종목)은 강세장 1국면(2023~26 PIT)이었다. 여기선
2018Q4·2020코로나·2022긴축 **하락장을 포함한 2016~2026**을 128종(관심+테마+사냥터top) 등가중으로.
3안: A 순수보유 · B 개별MA200이탈청산 · C 시장regime오버레이(KOSPI<MA200 전량현금).
⚠️ 30년 데이터=현재상장만 → 생존편향(절대수익 과대). 상대비교(C vs A 낙폭)가 결론.
사용: py 백테_하락장_개별종목.py [--self-test]
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

import os, sys, json, argparse
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
COST = _jq_cost(0.0015)  # §8-3: 종전 0.150% → 실측 0.559% (+0.409%p)
BEARS = {"2018Q4": ("2018-10-01", "2018-12-31"), "코로나2020": ("2020-01-15", "2020-04-30"),
         "2022긴축": ("2021-07-01", "2022-10-31")}

def mdd(e): return float((e/e.cummax()-1).min())
def cagr(e, n): return float((e.iloc[-1]/e.iloc[0])**(1/max(n/252, 1e-9))-1)
def sharpe(r): return float(r.mean()/r.std()*np.sqrt(252)) if r.std() > 0 else float("nan")

def portfolio(panel, pos):
    ret = panel.pct_change()
    active = panel.notna() & panel.shift(1).notna()
    switch = pos.astype(float).fillna(0).diff().abs()
    contrib = (ret.where(pos & active) - switch*COST).where(active)
    wk = contrib.mean(axis=1, skipna=True).fillna(0)
    return (1+wk).cumprod()

def run():
    p = os.path.join(HERE, "_bear_daily.csv")
    if not os.path.exists(p): return {"err": "_bear_daily.csv 없음(추출 필요)"}
    d = pd.read_csv(p, dtype={"code": str})
    d["date"] = pd.to_datetime(d["date"], errors="coerce"); d["close"] = pd.to_numeric(d["close"], errors="coerce")
    d = d.dropna(subset=["date", "close"])
    panel = d.pivot_table(index="date", columns="code", values="close", aggfunc="last").sort_index()
    ma = panel.rolling(200).mean()
    pos_hold = panel.notna()
    pos_ma = (panel > ma).shift(1).fillna(False) & panel.notna()
    # KOSPI regime
    kp = os.path.join(HERE, "kospi_index_daily.csv")
    k = pd.read_csv(kp, encoding="utf-8-sig"); k.columns = [c.lstrip("﻿").lower() for c in k.columns]
    k["date"] = pd.to_datetime(k["date"], errors="coerce"); k["close"] = pd.to_numeric(k["close"], errors="coerce")
    k = k.dropna(subset=["date"]).set_index("date")["close"]
    kma = k.rolling(200).mean(); kon = (k > kma).shift(1).fillna(False)
    kon = kon.reindex(panel.index).ffill().fillna(False)
    pos_reg = pd.DataFrame(np.repeat(kon.values[:, None], panel.shape[1], axis=1), index=panel.index, columns=panel.columns) & panel.notna()
    res = {"기간": f"{panel.index[0].date()}~{panel.index[-1].date()}", "종목수": panel.shape[1]}
    curves = {}
    for lab, pos in (("A_순수보유", pos_hold), ("B_개별MA200청산", pos_ma), ("C_regime오버레이", pos_reg)):
        e = portfolio(panel, pos); curves[lab] = e; r = e.pct_change().dropna()
        res[lab] = dict(CAGR=round(cagr(e, len(r)), 4), MDD=round(mdd(e), 4), Sharpe=round(sharpe(r), 3))
    # 벤치 KOSPI
    kk = k.reindex(panel.index).ffill(); kk = (kk/kk.iloc[0]).dropna()
    res["벤치_KOSPI"] = dict(CAGR=round(cagr(kk, len(kk)), 4), MDD=round(mdd(kk), 4), Sharpe=round(sharpe(kk.pct_change().dropna()), 3))
    # 하락장별 낙폭
    bear = {}
    for name, (s, e0) in BEARS.items():
        m = (panel.index >= s) & (panel.index <= e0)
        if m.sum() < 5: continue
        sub = {lab: curves[lab][m] for lab in curves}
        bear[name] = {lab: round(mdd(c/c.iloc[0]), 4) for lab, c in sub.items()}
        kb = kk[m]; bear[name]["KOSPI"] = round(mdd(kb/kb.iloc[0]), 4)
    res["하락장별_낙폭"] = bear
    return res

def _self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    e = pd.Series([1, 1.2, 0.8, 1.0])
    chk("MDD(1.2→0.8=-33%)", abs(mdd(e)-(-1/3)) < 0.01)
    idx = pd.date_range("2020-01-03", periods=60, freq="B")
    pan = pd.DataFrame({"A": np.linspace(100, 200, 60)}, index=idx)
    eq = portfolio(pan, pan.notna())
    chk("순수보유 상승", eq.iloc[-1] > eq.iloc[0])
    chk("BEARS 3구간", len(BEARS) == 3)
    print(f"\n셀프테스트: {ok}/{tot}"); return ok == tot

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    print(json.dumps(run(), ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
