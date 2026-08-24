#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
signal_efficacy.py — 신호 효력 사후측정 (Track W 보조: "이 신호가 밥값 했나")
==============================================================================
질문: heat 주도테마·진입(셋업/돌파)·품질이 **forward 수익을 예측했나**?
방법: 과거 월별로 신호를 재계산 → 그 다음 1·3개월 실제 초과수익(시장 EW 대비) 집계.
정직(필수): **in-sample 사후측정**(같은 데이터). OOS·forward 진실 아님. 2025~26 쏠림장
   특성 강함. 실전 forward 측정은 trackw_ledger.csv(진우 기입)+trackw_score.py가 정본.
   표본 작고 회전 빠름 → 방향성 참고용. 백테스트 수익을 기대치로 쓰지 말 것.
산출: signal_efficacy_latest.csv + 콘솔. 무수정: production·heat·발굴트랙.
사용: python signal_efficacy.py [--selftest] [--months N]
"""
import argparse, os, sys, types
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
HOLD = [('삼양식품','003230'),('두산에너빌리티','034020'),('NH투자증권','005940'),('ISC','095340'),
        ('알테오젠','196170'),('한화에어로','012450'),('한미반도체','042700'),('SK하이닉스','000660'),
        ('삼성물산','028260'),('삼성전자','005930'),('NAVER','035420'),('아모레퍼시픽','090430'),
        ('KT&G','033780'),('KB금융','105560'),('삼성SDI','006400'),('기아','000270'),
        ('카카오','035720'),('LIG넥스원','079550')]


def _load_src(fname, modname):
    path = os.path.join(HERE, fname); src = open(path, encoding="utf-8").read()
    m = types.ModuleType(modname); m.__file__ = path; sys.modules[modname] = m
    sys.dont_write_bytecode = True; exec(compile(src, path, "exec"), m.__dict__); return m


def fwd_excess(panel, mkt, c, t, k):
    """종목 c의 t→t+k개월 초과수익(시장 EW 대비). 데이터 없으면 nan."""
    if c not in panel.columns or t + k >= len(panel):
        return np.nan
    s = panel[c]
    p0, p1 = s.iloc[t], s.iloc[t + k]
    if pd.isna(p0) or pd.isna(p1) or p0 == 0:
        return np.nan
    mk = (1 + mkt.iloc[t + 1:t + k + 1]).prod() - 1
    return (p1 / p0 - 1) - mk


def heat_efficacy(panel, fine, name, E, TC, TH, months, topk=3):
    ret = panel.pct_change(); mkt = ret.mean(axis=1)
    rows = []
    start = max(13, len(panel) - months - 3)
    for t in range(start, len(panel) - 3):
        df, _, members = TH.compute_theme_heat(panel, fine, name, E, TC, i=t)
        if df.empty:
            continue
        top = df.head(topk)["theme"].tolist()
        for th in top:
            basket = members.get(th, [])
            ex1 = np.nanmean([fwd_excess(panel, mkt, c, t, 1) for c in basket]) if basket else np.nan
            ex3 = np.nanmean([fwd_excess(panel, mkt, c, t, 3) for c in basket]) if basket else np.nan
            rows.append({"t": panel.index[t].strftime("%Y-%m"), "theme": th, "fwd1": ex1, "fwd3": ex3})
    d = pd.DataFrame(rows)
    return d


def entry_efficacy(panel, codes, ES, TH, regime, months):
    ret = panel.pct_change(); mkt = ret.mean(axis=1)
    daily = TH.load_daily_for(codes)
    wk = {c: daily[c].resample("W-FRI").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna(subset=["close"])
          for c in codes if c in daily and len(daily[c]) >= 60}
    last_reg = regime.get(max(regime)) if regime else ""
    rows = []
    start = max(13, len(panel) - months - 3)
    for t in range(start, len(panel) - 3):
        d = panel.index[t]; ym = d.strftime("%Y-%m"); rstate = regime.get(ym, last_reg)
        mkt6 = float((1 + mkt.iloc[t-5:t+1]).prod() - 1)
        for c, w in wk.items():
            ws = w[w.index <= d]
            if len(ws) < 40:
                continue
            rs = float(ws["close"].iloc[-1]/ws["close"].iloc[-27]-1) - mkt6 if len(ws) >= 27 else 0.0
            st = ES.plan(ws, rs, rstate)["state"]
            bucket = ("돌파/셋업" if st in ("BREAKOUT","BREAKOUT_LOWVOL","SETUP")
                      else "임박" if st == "NEAR" else "관망")
            rows.append({"t": ym, "code": c, "bucket": bucket, "fwd3": fwd_excess(panel, mkt, c, t, 3)})
    return pd.DataFrame(rows)


def summarize(name, d, col):
    s = d[col].dropna()
    if len(s) == 0:
        return {"signal": name, "n": 0, "mean_fwd": np.nan, "hit%": np.nan}
    return {"signal": name, "n": int(len(s)), "mean_fwd": round(float(s.mean())*100, 1),
            "hit%": round(float((s > 0).mean())*100, 0)}


def run(months=24):
    E = _load_src("supercycle_overlay.py", "supercycle_overlay")
    TC = _load_src("theme_classify.py", "theme_classify")
    TH = _load_src("theme_heat.py", "theme_heat")
    ES = _load_src("entry_signals.py", "entry_signals")
    panel = TH.load_panel(); fine, name = TC.load_fine_map(); regime = TH.load_regime()
    he = heat_efficacy(panel, fine, name, E, TC, TH, months)
    # 진입 측정 대상 = 보유 ∪ 교집합
    pool = pd.read_csv(os.path.join(HERE, "stock_pool_latest.csv"), dtype={"code": str}); pool["code"]=pool["code"].str.zfill(6)
    heat = pd.read_csv(os.path.join(HERE, "theme_heat_latest.csv"))
    hot = set(heat.sort_values("heat_score", ascending=False).head(6)["theme"]) | {"반도체"}
    inter = pool[(pool.grade.isin(["S+","S"])) & (pool.theme.isin(hot))]["code"].tolist()
    codes = list(dict.fromkeys([c for _, c in HOLD] + inter))
    ee = entry_efficacy(panel, codes, ES, TH, regime, months)
    return he, ee, panel


def _selftest():
    # fwd_excess 수계산
    idx = pd.date_range("2024-01-31", periods=10, freq="ME")
    panel = pd.DataFrame({"A":[100,110,121,133,146,160,176,194,213,234],
                          "B":[100,100,100,100,100,100,100,100,100,100]}, index=idx).astype(float)
    ret = panel.pct_change(); mkt = ret.mean(axis=1)
    ex = fwd_excess(panel, mkt, "A", 0, 1)
    # A +10%, mkt = mean(A,B 1m ret)=mean(0.1,0)=0.05 → 초과 +5%
    assert abs(ex - 0.05) < 1e-9, ex
    assert np.isnan(fwd_excess(panel, mkt, "A", 9, 1))   # 미래없음
    s = summarize("x", pd.DataFrame({"fwd3":[0.1,-0.2,0.3]}), "fwd3")
    assert s["n"]==3 and s["hit%"]==67.0
    print("✅ signal_efficacy 셀프테스트 통과 (3/3): fwd초과 수계산·경계·요약")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--months", type=int, default=24)
    a = ap.parse_args()
    if a.selftest:
        _selftest(); return
    he, ee, panel = run(a.months)
    out = []
    # heat: 상위테마 forward vs 0
    out.append(summarize("heat 상위테마 fwd1m", he, "fwd1"))
    out.append(summarize("heat 상위테마 fwd3m", he, "fwd3"))
    # entry buckets
    for b in ("돌파/셋업", "임박", "관망"):
        out.append(summarize(f"진입:{b} fwd3m", ee[ee.bucket==b], "fwd3"))
    res = pd.DataFrame(out)
    res.to_csv(os.path.join(HERE, "signal_efficacy_latest.csv"), index=False, encoding="utf-8-sig")
    print("=== 신호 효력 사후측정 (in-sample · 시장 EW 대비 forward 초과 · 쏠림장 한계) ===")
    print(res.to_string(index=False))
    # verdict
    b = {r["signal"]: r for r in out}
    bo = b.get("진입:돌파/셋업 fwd3m", {}); gw = b.get("진입:관망 fwd3m", {})
    if bo.get("n") and gw.get("n"):
        diff = (bo["mean_fwd"] or 0) - (gw["mean_fwd"] or 0)
        print(f"\n진입 엣지(돌파/셋업 − 관망, fwd3m): {diff:+.1f}%p · 돌파/셋업 적중 {bo.get('hit%')}%")
    h3 = b.get("heat 상위테마 fwd3m", {})
    print(f"heat 상위테마 fwd3m 평균초과 {h3.get('mean_fwd')}%p · 적중 {h3.get('hit%')}%")
    print("\n⚠️ in-sample 사후측정 — forward 진실 아님. 실전 측정은 trackw_ledger(진우 기입)+trackw_score. 표본·쏠림 주의.")
    print("산출: signal_efficacy_latest.csv")


if __name__ == "__main__":
    main()
