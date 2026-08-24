#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""백테_추세청산_개별종목.py — 안전 보유매매 핵심검증

기획: 진우_안전보유매매_기획.md §4
질문: 좋은 종목을 보유하되, "대형 추세이탈에서만 청산"이 순수보유의 낙폭(MDD)을
      줄이면서 수익을 지키나? (승자 미절단 유지 — 스윙/시간/목표 청산 없음)
3안 (등가중 포트폴리오, 26종목=6종목+상위 사냥터):
  A 순수보유       : 데이터 있는 동안 항상 보유.
  B MA200이탈청산  : 주봉 종가 > 40주선(≈MA200)일 때만 보유·아니면 현금(종목별 독립).
  C regime오버레이 : KOSPI 주봉 종가 > 40주선일 때만 전 종목 보유·아니면 현금(시장방어).
벤치: KOSPI buy&hold. 비용 편도 15bp(전환 시). IN/OOS(60/40).
투자자문 아님·발굴≠매수신호·결정책임 본인.  사용: py 백테_추세청산_개별종목.py [--self-test]
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

MA_W = 40          # 40주선 ≈ MA200
COST = _jq_cost(0.0015)      # 전환 편도 15bp  # §8-3: 종전 0.150% → 실측 0.559% (+0.409%p)
JINWOO6 = {"247540","086520","036930","353200","450080","089030"}

def load_weekly_panel(codes):
    """대상 코드 → 주봉 close 와이드 패널(week × code)."""
    cache = os.path.join(HERE, "_target_daily.csv")
    srcs = [cache] if os.path.exists(cache) else [
        os.path.join(HERE, f"종목일봉_30년_{m}.csv") for m in ("KOSPI", "KOSDAQ")]
    frames = []
    for p in srcs:
        if not os.path.exists(p): continue
        d = pd.read_csv(p, usecols=["date", "code", "close"], dtype={"code": str}, encoding="utf-8-sig")
        d["code"] = d["code"].str.zfill(6); d = d[d["code"].isin(codes)]
        frames.append(d)
    if not frames: return None
    d = pd.concat(frames, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d["close"] = pd.to_numeric(d["close"], errors="coerce")
    d = d.dropna(subset=["date", "close"]); d = d[d["close"] > 0]
    wk = d.set_index("date").groupby("code")["close"].resample("W-FRI").last().reset_index()
    panel = wk.pivot(index="date", columns="code", values="close").sort_index()
    return panel

def load_kospi_weekly():
    p = os.path.join(HERE, "kospi_index_daily.csv")
    if not os.path.exists(p): return None
    k = pd.read_csv(p, encoding="utf-8-sig"); k.columns = [c.lstrip("﻿").lower() for c in k.columns]
    k["date"] = pd.to_datetime(k["date"], errors="coerce"); k["close"] = pd.to_numeric(k["close"], errors="coerce")
    k = k.dropna(subset=["date", "close"]).set_index("date")["close"]
    return k.resample("W-FRI").last().dropna()

def metrics(eq):
    eq = eq.dropna()
    if len(eq) < 10: return dict(CAGR=None, MDD=None, Sharpe=None)
    r = eq.pct_change().dropna()
    yrs = len(r)/52.0
    cagr = float((eq.iloc[-1]/eq.iloc[0])**(1/max(yrs, 1e-9))-1)
    mdd = float((eq/eq.cummax()-1).min())
    sh = float(r.mean()/r.std()*np.sqrt(52)) if r.std() > 0 else float("nan")
    return dict(CAGR=round(cagr, 4), MDD=round(mdd, 4), Sharpe=round(sh, 3))

def portfolio(panel, pos):
    """등가중: 매주 활성(데이터有) & pos=1 종목 평균수익 − 전환비용."""
    ret = panel.pct_change()
    active = panel.notna() & panel.shift(1).notna()
    p = pos & active
    switch = (pos.astype(float).fillna(0).diff().abs())   # 포지션 변화
    contrib = (ret.where(p) - switch*COST).where(active)
    wk_ret = contrib.mean(axis=1, skipna=True).fillna(0)
    return (1+wk_ret).cumprod()

def signals(panel, kospi):
    ma = panel.rolling(MA_W).mean()
    pos_hold = panel.notna()
    pos_ma = (panel > ma).shift(1).fillna(False) & panel.notna()   # look-ahead 0
    # regime: KOSPI>40주선
    kma = kospi.rolling(MA_W).mean()
    kreg = (kospi > kma).shift(1).fillna(False)
    kreg = kreg.reindex(panel.index).ffill().fillna(False)
    pos_reg = pd.DataFrame(np.repeat(kreg.values[:, None], panel.shape[1], axis=1),
                           index=panel.index, columns=panel.columns) & panel.notna()
    return pos_hold, pos_ma, pos_reg

def split_eq(panel, pos, kospi, frac=0.6):
    n = len(panel); cut = int(n*frac)
    out = {}
    for lab, sl in (("IN", slice(0, cut)), ("OOS", slice(cut, n)), ("전체", slice(0, n))):
        sub = panel.iloc[sl]
        eq = portfolio(sub, pos.iloc[sl])
        out[lab] = metrics(eq)
    return out

def run(codes):
    panel = load_weekly_panel(codes)
    if panel is None: return {"err": "데이터 없음"}
    kospi = load_kospi_weekly()
    pos_hold, pos_ma, pos_reg = signals(panel, kospi)
    res = {"기간": f"{panel.index[0].date()}~{panel.index[-1].date()}", "종목수": panel.shape[1]}
    res["A_순수보유"] = split_eq(panel, pos_hold, kospi)
    res["B_MA200이탈청산"] = split_eq(panel, pos_ma, kospi)
    res["C_regime오버레이"] = split_eq(panel, pos_reg, kospi)
    if kospi is not None:
        kk = kospi.reindex(panel.index).ffill()
        res["벤치_KOSPI"] = metrics((kk/kk.iloc[0]).dropna())
    return res

def _self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    idx = pd.date_range("2020-01-03", periods=100, freq="W-FRI")
    up = pd.Series(np.linspace(100, 300, 100), index=idx)
    panel = pd.DataFrame({"AAA": up})
    m = metrics((up/up.iloc[0]))
    chk("상승시리즈 CAGR>0", m["CAGR"] > 0)
    chk("상승시리즈 MDD≈0", m["MDD"] > -0.01)
    dd = pd.Series(list(np.linspace(100, 200, 50))+list(np.linspace(200, 120, 50)), index=idx)
    chk("하락구간 MDD<−30%", metrics((dd/dd.iloc[0]))["MDD"] < -0.3)
    pos = panel.notna()
    eq = portfolio(panel, pos)
    chk("순수보유 포트 상승", eq.iloc[-1] > eq.iloc[0])
    chk("MA40 시그널 bool", ((up > up.rolling(40).mean()).dtype == bool))
    print(f"\n셀프테스트: {ok}/{tot}"); return ok == tot

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--top", type=int, default=20)
    a = ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    codes = set(JINWOO6)
    csvp = os.path.join(HERE, "진우사냥터_후보.csv")
    if os.path.exists(csvp):
        import csv as _c
        with open(csvp, encoding="utf-8-sig") as f:
            for r in list(_c.DictReader(f))[:a.top]:
                codes.add(r["code"].zfill(6))
    print(json.dumps(run(codes), ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
