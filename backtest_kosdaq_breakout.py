#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest_kosdaq_breakout.py — #2 52주 신고가 breakout (George-Hwang 2004) KOSDAQ 백테스트
무수정: production·C·D·영역3·v41·v42 손대지 않음. 신규 평가 전용. 매수신호 아님.

가설: 52주 고점에 근접한 종목(momentum 지속)을 월간 매수하면 KOSDAQ EW를 이기나?
신호(PIT): proximity = close(d0) / max(close, 최근 252거래일 ≤ d0). 1.0에 가까울수록 신고가 근접.
   → 상위 분위(top quintile) 동일가중 매수, 1개월 보유, 월간 리밸. 비용 왕복 0.6%(KOSDAQ).
벤치마크: KOSDAQ EW(그달 유효종목 전체 동일가중) = v4.1이 패배한 정직 기준.
표본: kosdaq_pit_daily.csv (상폐 포함 215종, 생존편향 통제). 상폐 종목은 시계열 종료 시점까지 수익 반영.

사전등록 합격선(동결, EW 기준): alpha≥+3%p AND IR_EW≥+0.30 AND MDD 비악화, net 0.6%, OOS 3분할 부호 일치.
회의적 prior: v4.1 팩터·v4.2 수급 모두 EW에 패배. breakout도 ±30%·휩쏘로 기각 가능.

사용: python backtest_kosdaq_breakout.py [--top 0.2] [--selftest]
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

import csv, sys
from datetime import date

BASE = "/sessions/confident-jolly-brown/mnt/Desktop--진우퀀트/"
DAILY = "kosdaq_pit_daily.csv"
LOOK = 252          # 52주(거래일)
TOP_Q = 0.20        # 상위 20% 분위
COST = _jq_cost(0.006)        # 왕복 0.6% (KOSDAQ 소형 prior)  # §8-3: 종전 0.600% → 실측 0.559% (-0.041%p)


def _d(s):
    y, m, dd = str(s)[:10].split("-"); return date(int(y), int(m), int(dd))


def load_daily(path=BASE + DAILY):
    px = {}           # code -> list[(date, close)]
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        try:
            c = float(r["close"])
            if c > 0:
                px.setdefault(r["code"], []).append((_d(r["date"]), c))
        except (ValueError, KeyError):
            pass
    for c in px:
        px[c].sort()
    return px


def month_starts(all_dates):
    seen = {}
    for d in all_dates:
        key = (d.year, d.month)
        if key not in seen:
            seen[key] = d
    return [seen[k] for k in sorted(seen)]


def proximity(series, d0, look=LOOK):
    """close(≤d0 최신) / max(close, 최근 look개 ≤d0). None if 부족."""
    past = [(d, c) for d, c in series if d <= d0]
    if len(past) < look // 2:        # 최소 반년
        return None, None
    window = past[-look:]
    hi = max(c for _, c in window)
    last = past[-1][1]
    return (last / hi if hi > 0 else None), last


def ret_between(series, d0, d1):
    """d0 직후~d1 종가 수익. 상폐(시계열 조기종료)면 마지막 종가까지."""
    seg = [(d, c) for d, c in series if d0 < d <= d1]
    p0 = [c for d, c in series if d <= d0]
    if not p0:
        return None
    a = p0[-1]
    if seg:
        b = seg[-1][1]
    else:
        future = [(d, c) for d, c in series if d > d0]
        if not future:
            return None       # 이미 상폐(데이터 끝)
        b = future[0][1] if future[0][0] <= d1 else None
        if b is None:
            return None
    return b / a - 1 if a > 0 else None


def metrics(rets, bench, ppy=12):
    n = len(rets)
    cum = 1.0
    for r in rets: cum *= (1 + r)
    cagr = cum ** (ppy / n) - 1
    mean = sum(rets) / n
    vol = (sum((x - mean) ** 2 for x in rets) / (n - 1)) ** 0.5 * ppy ** 0.5
    c = pk = 1.0; mdd = 0.0
    for r in rets:
        c *= (1 + r); pk = max(pk, c); mdd = min(mdd, c / pk - 1)
    ex = [rets[i] - bench[i] for i in range(n)]
    em = sum(ex) / n
    ev = (sum((e - em) ** 2 for e in ex) / (n - 1)) ** 0.5
    ir = (em * ppy) / (ev * ppy ** 0.5) if ev > 0 else None
    return {"CAGR%": round(cagr * 100, 2), "Sharpe": round(cagr / vol, 3) if vol > 0 else None,
            "MDD%": round(mdd * 100, 2), "IR_EW": round(ir, 3) if ir is not None else None}


def mdd_of(rets):
    c = pk = 1.0; m = 0.0
    for r in rets:
        c *= (1 + r); pk = max(pk, c); m = min(m, c / pk - 1)
    return m * 100


def run(top_q=TOP_Q):
    px = load_daily()
    alld = sorted({d for s in px.values() for d, _ in s})
    ms = [d for d in month_starts(alld) if d >= date(2020, 1, 1)]
    pick_rets, ew_rets = [], []
    prev_picks = set()
    n_pick_hist = []
    for i in range(len(ms) - 1):
        d0, d1 = ms[i], ms[i + 1]
        prox = {}
        for c, s in px.items():
            p, _ = proximity(s, d0)
            if p is not None:
                prox[c] = p
        if len(prox) < 20:
            continue
        # EW 벤치 = 유효 수익 종목 전체
        ew = [ret_between(px[c], d0, d1) for c in prox]
        ew = [r for r in ew if r is not None]
        if not ew:
            continue
        ew_rets.append(sum(ew) / len(ew))
        # 상위 분위 picks
        k = max(3, int(len(prox) * top_q))
        picks = [c for c, _ in sorted(prox.items(), key=lambda kv: -kv[1])[:k]]
        prs = [ret_between(px[c], d0, d1) for c in picks]
        prs = [r for r in prs if r is not None]
        if not prs:
            pick_rets.append(0.0); continue
        gross = sum(prs) / len(prs)
        # 회전 비용: picks 교체율 근사
        turn = len(set(picks) ^ prev_picks) / (2 * max(1, len(picks)))
        pick_rets.append(gross - turn * COST)
        prev_picks = set(picks); n_pick_hist.append(len(picks))
    n = min(len(pick_rets), len(ew_rets))
    pick_rets, ew_rets = pick_rets[:n], ew_rets[:n]
    mp, me = metrics(pick_rets, ew_rets), metrics(ew_rets, ew_rets)
    alpha = mp["CAGR%"] - me["CAGR%"]
    mdd_worse = mp["MDD%"] - me["MDD%"]      # 음수=악화
    # OOS 3분할 alpha 부호
    kth = n // 3
    blocks = [(0, kth), (kth, 2 * kth), (2 * kth, n)]
    oos = []
    for a, b in blocks:
        ca = (lambda xs: (([__import__('math').prod([1+x for x in xs])][0]) ** (12 / len(xs)) - 1) * 100)(pick_rets[a:b])
        ce = (lambda xs: (([__import__('math').prod([1+x for x in xs])][0]) ** (12 / len(xs)) - 1) * 100)(ew_rets[a:b])
        oos.append(round(ca - ce, 1))
    print("=== #2 52주 신고가 breakout (KOSDAQ, 상폐포함 %d종, %d개월, top %.0f%%) ===" % (len(px), n, top_q * 100))
    print("  picks  : CAGR %+.2f%% / Sharpe %s / MDD %+.2f%% / IR_EW %s" % (mp["CAGR%"], mp["Sharpe"], mp["MDD%"], mp["IR_EW"]))
    print("  EW(벤치): CAGR %+.2f%% / Sharpe %s / MDD %+.2f%%" % (me["CAGR%"], me["Sharpe"], me["MDD%"]))
    print("  alpha(vs EW) %+.2f%%p | IR_EW %s | MDD %s%.2f%%p | OOS3분할 alpha %s" %
          (alpha, mp["IR_EW"], "+" if mdd_worse >= 0 else "", mdd_worse, oos))
    c1 = alpha >= 3.0; c2 = (mp["IR_EW"] or -9) >= 0.30; c3 = mdd_worse >= 0; c4 = all(o >= 0 for o in oos)
    passed = c1 and c2 and c3 and c4
    print("\n  합격선: alpha≥+3%%p[%s] AND IR_EW≥0.30[%s] AND MDD비악화[%s] AND OOS부호일치[%s]" %
          ("O" if c1 else "X", "O" if c2 else "X", "O" if c3 else "X", "O" if c4 else "X"))
    print("  ★ 판정: %s" % ("PASS → 백테스트 후속(검증·관찰)" if passed else "FAIL → 사전등록대로 기각, KOSDAQ 체계선정 후보 추가 소진"))
    import json
    json.dump({"n": n, "picks": mp, "EW": me, "alpha_vs_EW": alpha, "MDD_worse": mdd_worse,
               "OOS3": oos, "PASS": passed}, open(BASE + "backtest_kosdaq_breakout_result.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    return passed


def selftest():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print("  [%s] %s" % ("OK" if c else "FAIL", n))
    import datetime as _dt
    rise = [(date(2021, 1, 1) + _dt.timedelta(days=i), 100.0 + i) for i in range(150)]  # 우상향=마지막이 최고
    pr, _ = proximity(rise, rise[-1][0])
    chk("신고가 근접 proximity≈1", pr is not None and pr > 0.98)
    fall = [(date(2021, 1, 1) + _dt.timedelta(days=i), 250.0 - i) for i in range(150)]  # 우하향=고점은 과거
    pf, _ = proximity(fall, fall[-1][0])
    chk("하락 종목 proximity<1", pf is not None and pf < 0.95)
    r = ret_between([(date(2021, 1, 1), 100), (date(2021, 2, 1), 110)], date(2021, 1, 15), date(2021, 2, 15))
    chk("수익 계산 +10%", abs(r - 0.10) < 1e-9)
    rd = ret_between([(date(2021, 1, 1), 100), (date(2021, 1, 20), 30)], date(2021, 1, 15), date(2021, 3, 1))
    chk("상폐(조기종료) 손실 반영", rd is not None and rd < 0)
    chk("LOOK=252", LOOK == 252)
    print("self-test: %d/%d" % (ok, tot)); return ok == tot


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        tq = TOP_Q
        if "--top" in sys.argv:
            try: tq = float(sys.argv[sys.argv.index("--top") + 1])
            except (ValueError, IndexError): pass
        try:
            run(tq)
        except Exception:
            import traceback; print("\n[에러]"); traceback.print_exc()
