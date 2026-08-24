#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_weekly_reconcile.py — 주봉 도입 전 정합 교차검증 게이트
==============================================================================
목적(진우 지시 "검증 먼저"): 주봉 차트를 붙이기 전, 새 가격 원천(일봉)이 기존 월봉
패널과 조용히 어긋나지 않는지 3게이트로 검증. 통과 못 하면 주봉 통합 보류.

게이트 A — 원천 정합(월말 종가 levels):
  일봉 → 월말 종가 ≈ 기존 *_monthly_prices.csv 종가(허용오차 tol). 완결월만(월중 절단 제외).
  → 액면분할·배당 조정 차이로 두 소스가 어긋나는지 검출(핵심).
게이트 B — 수익 환원(같은 월말 경계):
  일봉→월말 월간수익 ≈ 월봉 월간수익. 단일월 드리프트까지 잡음.
게이트 C — 주봉 무결성:
  주봉(W-FRI) 종가 = 해당 주 마지막 거래일 일봉 종가(리샘플 버그 차단).

PASS: A·B 일치율 ≥ PASS_RATE(0.98) AND C ≥ 0.999 AND 표본>0.
산출: verify_weekly_reconcile_result.json + 콘솔.
사용: python verify_weekly_reconcile.py [--market kosdaq] [--tol 0.005] [--self-test]
무수정: production·발굴트랙·heat 엔진. 통합은 본 게이트 PASS 후.
"""
import argparse, os, sys, json
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
TOL = 0.005
PASS_RATE = 0.98
MAXGAP = 7   # 완결월 판정: 마지막 일봉이 월말 ±이 영업일 이내


def load_daily(path):
    d = pd.read_csv(path, dtype={"code": str})
    d["code"] = d["code"].str.zfill(6)
    d["date"] = pd.to_datetime(d["date"])
    return d


def load_monthly(path):
    m = pd.read_csv(path, parse_dates=["Date"], index_col="Date")
    m.columns = [str(c).zfill(6) for c in m.columns]
    return m


def complete_months(daily_dates):
    s = pd.Series(1, index=pd.DatetimeIndex(sorted(set(daily_dates))))
    out = set()
    for ym, grp in s.groupby(s.index.to_period("M")):
        last = grp.index.max()
        month_end = ym.to_timestamp(how="end").normalize()
        bgap = np.busday_count(last.date(), month_end.date())
        if abs(bgap) <= MAXGAP:
            out.add(str(ym))
    return out


def gate_A(daily, monthly, tol=TOL):
    overlap = sorted(set(daily["code"]) & set(monthly.columns))
    n_ok = n_tot = 0; bad = []; comp_all = set()
    for c in overlap:
        dd = daily[daily["code"] == c].set_index("date")["close"].sort_index()
        if dd.empty:
            continue
        comp = complete_months(dd.index); comp_all |= comp
        me = dd.resample("ME").last()
        for dt, dv in me.items():
            ym = dt.strftime("%Y-%m")
            if ym not in comp or pd.isna(dv):
                continue
            mcol = monthly[c]
            mm = mcol[mcol.index.to_period("M") == dt.to_period("M")]
            if mm.empty or pd.isna(mm.iloc[0]) or mm.iloc[0] == 0:
                continue
            mv = float(mm.iloc[0]); n_tot += 1
            rel = abs(dv / mv - 1)
            if rel <= tol:
                n_ok += 1
            else:
                bad.append({"code": c, "month": ym, "daily": round(float(dv), 1),
                            "monthly": round(mv, 1), "rel_%": round(rel * 100, 2)})
    bad.sort(key=lambda x: -x["rel_%"])
    return n_ok, n_tot, bad[:15], len(comp_all)


def gate_B(daily, monthly, tol=TOL):
    overlap = sorted(set(daily["code"]) & set(monthly.columns))
    n_ok = n_tot = 0; bad = []
    for c in overlap:
        dd = daily[daily["code"] == c].set_index("date")["close"].sort_index()
        if len(dd) < 30:
            continue
        comp = complete_months(dd.index)
        me = dd.resample("ME").last().dropna(); d_ret = me.pct_change()
        mcol = monthly[c].dropna(); m_ret = mcol.pct_change()
        for dt, dr in d_ret.items():
            ym = dt.strftime("%Y-%m")
            prev = (dt.to_period("M") - 1).strftime("%Y-%m")
            if ym not in comp or prev not in comp or pd.isna(dr):
                continue
            mm = m_ret[m_ret.index.to_period("M") == dt.to_period("M")]
            if mm.empty or pd.isna(mm.iloc[0]):
                continue
            mr = float(mm.iloc[0]); n_tot += 1
            if abs(dr - mr) <= max(tol, 0.005):
                n_ok += 1
            else:
                bad.append({"code": c, "month": ym, "daily_ret_%": round(dr * 100, 2),
                            "monthly_ret_%": round(mr * 100, 2)})
    bad.sort(key=lambda x: -abs(x["daily_ret_%"] - x["monthly_ret_%"]))
    return n_ok, n_tot, bad[:15]


def gate_C(daily):
    n_ok = n_tot = 0
    for c in sorted(set(daily["code"]))[:40]:
        dd = daily[daily["code"] == c].set_index("date")["close"].sort_index()
        if len(dd) < 30:
            continue
        wk = dd.resample("W-FRI").last().dropna()
        for wdt, wv in wk.items():
            seg = dd[(dd.index > wdt - pd.Timedelta(days=7)) & (dd.index <= wdt)]
            if seg.empty:
                continue
            n_tot += 1
            if abs(float(wv) - float(seg.iloc[-1])) < 1e-6:
                n_ok += 1
    return n_ok, n_tot


def run(market="kosdaq", tol=TOL):
    daily_path = os.path.join(HERE, f"{market}_pit_daily.csv")
    monthly_path = os.path.join(HERE, f"{market}_monthly_prices.csv")
    if not os.path.exists(daily_path):
        return {"market": market, "status": "NO_DAILY", "msg": f"{os.path.basename(daily_path)} 없음 — PC fetch 후 재실행"}
    daily = load_daily(daily_path); monthly = load_monthly(monthly_path)
    overlap = sorted(set(daily["code"]) & set(monthly.columns))
    aok, atot, abad, ncomp = gate_A(daily, monthly, tol)
    bok, btot, bbad = gate_B(daily, monthly, tol)
    cok, ctot = gate_C(daily)
    arate = (aok / atot) if atot else 0.0
    brate = (bok / btot) if btot else 0.0
    crate = (cok / ctot) if ctot else 0.0
    return {
        "market": market, "tol": tol, "pass_rate_req": PASS_RATE,
        "overlap_codes": len(overlap), "complete_months": ncomp,
        "daily_range": [str(daily["date"].min().date()), str(daily["date"].max().date())],
        "gateA_monthend": {"ok": aok, "total": atot, "rate": round(arate, 4), "worst": abad},
        "gateB_ret_reconcile": {"ok": bok, "total": btot, "rate": round(brate, 4), "worst": bbad},
        "gateC_weekly_integrity": {"ok": cok, "total": ctot, "rate": round(crate, 4)},
        "status": "PASS" if (arate >= PASS_RATE and brate >= PASS_RATE and crate >= 0.999 and atot > 0) else "FAIL",
    }


def _self_test():
    rng = pd.bdate_range("2023-01-02", "2023-06-30")
    rs = np.random.default_rng(0)
    px = 1000 * np.cumprod(1 + rs.normal(0.0005, 0.01, len(rng)))
    daily = pd.DataFrame({"code": "123456", "date": pd.to_datetime(rng), "close": px})
    me = pd.Series(px, index=rng).resample("ME").last()
    monthly = pd.DataFrame({"123456": me.values}, index=me.index)
    aok, atot, abad, nc = gate_A(daily, monthly, tol=1e-9)
    assert atot > 0 and aok == atot, f"A 자기일치 실패 {aok}/{atot} {abad[:2]}"
    bok, btot, bbad = gate_B(daily, monthly, tol=1e-9)
    assert btot > 0 and bok == btot, f"B 자기일치 실패 {bok}/{btot} {bbad[:2]}"
    cok, ctot = gate_C(daily)
    assert ctot > 0 and cok == ctot, f"C 주봉무결성 실패 {cok}/{ctot}"
    monthly2 = monthly.copy(); monthly2.iloc[2, 0] *= 1.05
    aok2, atot2, abad2, _ = gate_A(daily, monthly2, tol=0.005)
    assert aok2 < atot2 and any(x["rel_%"] > 4 for x in abad2), "불일치 미검출"
    print("✅ verify 셀프테스트 통과: A/B 자기일치 + C 주봉무결성 + 불일치 검출")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", default="kosdaq")
    ap.add_argument("--tol", type=float, default=TOL)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        _self_test(); return
    res = run(a.market, a.tol)
    open(os.path.join(HERE, "verify_weekly_reconcile_result.json"), "w", encoding="utf-8").write(
        json.dumps(res, ensure_ascii=False, indent=2))
    print(f"[{res.get('market')}] status = {res.get('status')}")
    if res.get("status") == "NO_DAILY":
        print(" ", res.get("msg")); return
    print(f"  overlap codes={res['overlap_codes']} · 완결월={res['complete_months']} · 일봉범위 {res['daily_range']}")
    a_ = res["gateA_monthend"]; b_ = res["gateB_ret_reconcile"]; c_ = res["gateC_weekly_integrity"]
    print(f"  게이트A 월말종가 정합: {a_['ok']}/{a_['total']} = {a_['rate']*100:.1f}%  (합격선 {PASS_RATE*100:.0f}%)")
    if a_["worst"]:
        print("    worst:", a_["worst"][:3])
    print(f"  게이트B 수익 환원:    {b_['ok']}/{b_['total']} = {b_['rate']*100:.1f}%")
    if b_["worst"]:
        print("    worst:", b_["worst"][:3])
    print(f"  게이트C 주봉 무결성:  {c_['ok']}/{c_['total']} = {c_['rate']*100:.1f}%")


if __name__ == "__main__":
    main()
