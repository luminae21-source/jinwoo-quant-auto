#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
entry_signal_backtest.py — 진입 유형(돌파/눌림목/추세필터) 가치 검증 (2026-06-07)

목적: 보강 문서 §4 '검증 후' 항목 — 진입 타이밍/패턴이 결과를 개선하는가?
   동일 종목·기간·손절(k=2.5)·보유(60일)에서 진입 규칙만 바꿔 비교:
     ALL        : 매월초(베이스라인)
     TREND_UP   : 매월초 & 종가>200일선 (Faber식 추세 상방에서만 진입)
     TREND_DN   : 매월초 & 종가<200일선 (대조)
     BREAKOUT   : 20일 신고가 돌파 (이벤트, 종목당 최소 21거래일 간격)
     PULLBACK   : 추세상방(>200MA) & 20일선 근처 눌림목
엔진: validate_atr_stop.simulate_trade(k=2.5) 재사용.
정직성: 인샘플·생존편향 통제 표본이라도 캘린더/이벤트 진입(thesis 아님). 상대비교만.

사용: python entry_signal_backtest.py --daily kosdaq_pit_daily_pykrx.csv
      python entry_signal_backtest.py --self-test
"""
import argparse, sys
import validate_atr_stop as V

K = 2.5; HORIZON = 60; COST = 40.0; MIN_GAP = 21


def sma(xs, i, n):
    if i + 1 < n:
        return None
    s = xs[i - n + 1:i + 1]
    return sum(s) / n


def gen_entries(bars, rule):
    """bars=[(date,o,h,l,c)] → 진입 인덱스 리스트."""
    c = [b[4] for b in bars]
    idxs = []
    last = -10 ** 9
    # 월초 후보: 달이 바뀌는 첫 거래일
    month_first = set()
    pm = None
    for i, b in enumerate(bars):
        ym = b[0][:7]
        if ym != pm:
            month_first.add(i); pm = ym
    for i in range(len(bars)):
        ok = False
        if rule == "ALL":
            ok = i in month_first
        elif rule == "TREND_UP":
            s = sma(c, i, 200); ok = (i in month_first) and s is not None and c[i] > s
        elif rule == "TREND_DN":
            s = sma(c, i, 200); ok = (i in month_first) and s is not None and c[i] < s
        elif rule == "BREAKOUT":
            if i >= 20 and c[i] >= max(c[i - 20:i + 1]) and i - last >= MIN_GAP:
                ok = True
        elif rule == "PULLBACK":
            s200 = sma(c, i, 200); s20 = sma(c, i, 20)
            if s200 and s20 and c[i] > s200 and c[i] <= s20 * 1.02 and i - last >= MIN_GAP:
                ok = True
        if ok:
            idxs.append(i); last = i
    return idxs


def stats(rets):
    n = len(rets)
    if n == 0:
        return None
    s = sorted(rets)
    return dict(n=n, mean=sum(rets) / n, win=100 * sum(1 for x in rets if x > 0) / n,
                p5=s[max(0, int(n * 0.05) - 1)], bad=100 * sum(1 for x in rets if x <= -20) / n)


def run(daily_by):
    rules = ["ALL", "TREND_UP", "TREND_DN", "BREAKOUT", "PULLBACK"]
    print("진입유형 검증 | 손절 k=%.1f · 보유 %d일 · 비용 %dbp · 종목 %d\n"
          % (K, HORIZON, COST, len(daily_by)))
    print("%-10s | %7s %8s %7s %8s %9s" % ("규칙", "n", "평균%", "승률%", "5%꼬리%", "≤-20%비율"))
    print("-" * 60)
    for rule in rules:
        rets = []
        for code, bars in daily_by.items():
            if len(bars) < 60:
                continue
            for i in gen_entries(bars, rule):
                seg = bars[i:min(len(bars), i + HORIZON + 1)]
                if len(seg) < 3:
                    continue
                rets.append(V.simulate_trade(seg, K, 14, False, COST)["ret_pct"])
        st = stats(rets)
        if st:
            print("%-10s | %7d %8.1f %7.1f %8.1f %9.1f"
                  % (rule, st["n"], st["mean"], st["win"], st["p5"], st["bad"]))
    print("\n해석: TREND_UP/BREAKOUT/PULLBACK가 ALL보다 평균↑·승률↑·꼬리↓면 진입타이밍이 엣지. "
          "비슷하거나 못하면 진입유형은 가치 없음(타이밍보다 thesis·손절이 중요).")


def self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += bool(c); print(("  [%s] " % ("OK" if c else "XX")) + n)
    # 상승 일변(추세 위) 20일 신고가 매일 → BREAKOUT 잡히되 MIN_GAP 간격
    up = [("2020-%02d-%02d" % (1 + i // 28, 1 + i % 28), 100 + i, 100 + i, 100 + i, 100 + i) for i in range(260)]
    bk = gen_entries(up, "BREAKOUT")
    chk("BREAKOUT 간격>=MIN_GAP", all(bk[j + 1] - bk[j] >= MIN_GAP for j in range(len(bk) - 1)))
    tu = gen_entries(up, "TREND_UP")
    chk("TREND_UP: 상승추세서 월초 진입 다수", len(tu) > 0)
    td = gen_entries(up, "TREND_DN")
    chk("TREND_DN: 상승추세선 거의 없음", len(td) == 0)
    print("\nself-test: %d/%d" % (ok, tot)); return ok == tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--daily")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(0 if self_test() else 1)
    if not a.daily:
        sys.exit("--daily 필요")
    run(V.load_daily(a.daily))


if __name__ == "__main__":
    main()
