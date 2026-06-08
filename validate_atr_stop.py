#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_atr_stop.py — 테마 lane ATR(k) 손절 그리드 검증 도구 (2026-06-07)

목적: [진우퀀트_손절사이징_룰_파라미터.md §2~3] 의 손절폭 k(=stop_dist/ATR)와
      트레일링 여부를 실데이터로 검증. 일봉 OHLC가 주어지면 진입 후 k×ATR 손절(정적/트레일링)을
      시뮬레이션해 k 그리드별 [평균손익 · 워스트 · 5%꼬리 · 승률 · 손절률 · ≤-20%비율] 비교.

데이터: fetch_theme_daily.py(PC)로 받은 일봉 long CSV. 0가격(거래정지일)·결함행은 로더가 제외.
정직성(§0): 인샘플. 슬리피지/세금 cost_bps 왕복 반영. 갭하락은 '시가<손절선이면 시가체결' 보수처리.

입력 CSV(long): code,date,open,high,low,close
진입신호(선택):  code,entry_date[,horizon_days]   없으면 종목별 첫 거래일 진입·끝까지 보유

사용:
  python validate_atr_stop.py --self-test
  python validate_atr_stop.py --daily theme_daily.csv --signals theme_entries.csv
  python validate_atr_stop.py --daily theme_daily.csv --signals theme_entries.csv --trailing
"""
import argparse, csv, sys
from collections import defaultdict


# ---------- ATR ----------
def true_ranges(o, h, l, c):
    tr = []
    for i in range(len(c)):
        if i == 0:
            tr.append(h[i] - l[i])
        else:
            tr.append(max(h[i] - l[i], abs(h[i] - c[i - 1]), abs(l[i] - c[i - 1])))
    return tr


def atr_series(o, h, l, c, period=14):
    tr = true_ranges(o, h, l, c)
    out = [None] * len(tr)
    if not tr:
        return out
    run = None
    for i in range(len(tr)):
        if i < period:
            run = tr[i] if run is None else (run * i + tr[i]) / (i + 1)
            out[i] = run
        else:
            run = (out[i - 1] * (period - 1) + tr[i]) / period
            out[i] = run
    return out


# ---------- 트레이드 시뮬 ----------
def simulate_trade(bars, k, period=14, trailing=False, cost_bps=40.0):
    """bars=[(date,o,h,l,c)] 진입일~끝. 진입가=bars[0].close. 반환 dict(ret_pct, stopped, days)."""
    o = [b[1] for b in bars]; h = [b[2] for b in bars]
    l = [b[3] for b in bars]; c = [b[4] for b in bars]
    atr = atr_series(o, h, l, c, period)
    entry = c[0]
    atr0 = atr[0] or (h[0] - l[0]) or (entry * 0.03)
    stop = entry - k * atr0
    peak = c[0]
    cost = cost_bps / 1e4
    for i in range(1, len(bars)):
        if trailing:
            peak = max(peak, c[i - 1])
            a = atr[i] or atr0
            stop = max(stop, peak - k * a)
        if o[i] <= stop:                       # 갭하락 우선: 시가체결
            return dict(ret_pct=((o[i] / entry - 1) - 2 * cost) * 100, stopped=True, days=i)
        if l[i] <= stop:                       # 장중 손절선 체결
            return dict(ret_pct=((stop / entry - 1) - 2 * cost) * 100, stopped=True, days=i)
    return dict(ret_pct=((c[-1] / entry - 1) - 2 * cost) * 100, stopped=False, days=len(bars) - 1)


def hold_return(bars, cost_bps=40.0):
    entry = bars[0][4]; exitpx = bars[-1][4]; cost = cost_bps / 1e4
    return (exitpx / entry - 1 - 2 * cost) * 100


# ---------- 데이터 ----------
def load_daily(path):
    by = defaultdict(list)
    skipped = 0
    with open(path, encoding="utf-8-sig") as fh:
        for r in csv.DictReader(fh):
            o, h, l, c = float(r["open"]), float(r["high"]), float(r["low"]), float(r["close"])
            if min(o, h, l, c) <= 0:           # 거래정지일/결함(0가격) 제외 — 손절 체결 불가
                skipped += 1
                continue
            by[r["code"]].append((r["date"], o, h, l, c))
    for code in by:
        by[code].sort(key=lambda x: x[0])
    if skipped:
        print("[로더] 0이하 가격 %d행 제외(거래정지/결함)" % skipped)
    return by


def slice_trade(bars, entry_date, horizon_days):
    idx = next((i for i, b in enumerate(bars) if b[0] >= entry_date), None)
    if idx is None:
        return None
    end = len(bars) if not horizon_days else min(len(bars), idx + horizon_days + 1)
    return bars[idx:end]


# ---------- 그리드 ----------
def run_grid(daily_by, signals, trailing, cost_bps, period):
    ks = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
    print("종목 %d | 신호 %d | %s | ATR(%d) | 비용 %dbp왕복\n"
          % (len(daily_by), len(signals), "트레일링" if trailing else "정적손절", period, cost_bps))
    holds = []
    trades_by_k = {k: [] for k in ks}
    for (code, edate, hor) in signals:
        bars = daily_by.get(code)
        if not bars:
            continue
        seg = slice_trade(bars, edate, hor)
        if not seg or len(seg) < 3:
            continue
        holds.append(hold_return(seg, cost_bps))
        for k in ks:
            trades_by_k[k].append(simulate_trade(seg, k, period, trailing, cost_bps))

    def stats(rets):
        n = len(rets)
        if n == 0:
            return (0, 0, 0, 0, 0)
        s = sorted(rets)
        avg = sum(rets) / n
        worst = s[0]
        win = 100 * sum(1 for x in rets if x > 0) / n
        p5 = s[max(0, int(n * 0.05) - 1)]                 # 5%분위 꼬리손실
        bad = 100 * sum(1 for x in rets if x <= -20) / n  # ≤−20% 트레이드 비율(하한가 위험권)
        return (avg, worst, win, p5, bad)

    havg, hworst, hwin, hp5, hbad = stats(holds)
    print("%-8s | %7s %8s %8s %7s %8s %9s"
          % ("k", "평균%", "워스트%", "5%꼬리%", "승률%", "손절률%", "≤-20%비율"))
    print("-" * 66)
    print("%-8s | %7.1f %8.1f %8.1f %7.1f %8s %9.1f"
          % ("보유(無손절)", havg, hworst, hp5, hwin, "-", hbad))
    for k in ks:
        tr = trades_by_k[k]
        rets = [t["ret_pct"] for t in tr]
        sr = 100 * sum(1 for t in tr if t["stopped"]) / len(tr) if tr else 0
        avg, worst, win, p5, bad = stats(rets)
        print("%-8s | %7.1f %8.1f %8.1f %7.1f %8.1f %9.1f"
              % ("%.1f×ATR" % k, avg, worst, p5, win, sr, bad))
    print("\n해석: '5%꼬리·≤-20%비율'(하한가 위험)을 보유 대비 줄이면서 평균손익을 과도하게 깎지 "
          "않는 k 선택. 손절률이 너무 높으면(휩쏘) k↑. (워스트 −100% 부근이면 0가격행 미제거 의심)")


# ---------- self-test ----------
def self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot
        tot += 1; ok += bool(c); print(("  [%s] " % ("OK" if c else "XX")) + n)

    o = [100] * 20; h = [105] * 20; l = [95] * 20; c = [100] * 20
    a = atr_series(o, h, l, c, 14)
    chk("ATR 일정폭=10", abs(a[-1] - 10) < 1e-6)

    bars = [("d0", 100, 105, 95, 100), ("d1", 100, 105, 95, 100),
            ("d2", 100, 105, 95, 100), ("d3", 100, 102, 79, 90)]
    r = simulate_trade(bars, k=2.0, period=14, trailing=False, cost_bps=0)
    chk("정적손절 체결(stopped)", r["stopped"] is True)
    chk("손절가≈80 → ret≈-20%", abs(r["ret_pct"] - (-20)) < 1.0)

    bars2 = [("d0", 100, 105, 95, 100), ("d1", 100, 105, 95, 100),
             ("d2", 100, 105, 95, 100), ("d3", 70, 72, 65, 68)]
    r2 = simulate_trade(bars2, k=2.0, period=14, trailing=False, cost_bps=0)
    chk("갭하락 시가체결 ret≈-30%", abs(r2["ret_pct"] - (-30)) < 1.0)

    up = [("d%d" % i, 100 + i, 106 + i, 96 + i, 100 + i) for i in range(20)]
    r3 = simulate_trade(up, k=2.0, period=14, trailing=False, cost_bps=0)
    chk("상승추세 미체결", r3["stopped"] is False and r3["ret_pct"] > 0)

    seq = [("d0", 100, 100, 100, 100)] + [("d%d" % i, 100 + i * 2, 104 + i * 2, 98 + i * 2, 100 + i * 2)
                                          for i in range(1, 8)] + [("dX", 110, 110, 70, 72)]
    rs = simulate_trade(seq, 2.0, 14, False, 0)
    rt = simulate_trade(seq, 2.0, 14, True, 0)
    chk("트레일링 청산가 ≥ 정적", rt["ret_pct"] >= rs["ret_pct"] - 1e-6)

    print("\nself-test: %d/%d 통과" % (ok, tot))
    return ok == tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--daily", help="일봉 OHLC long CSV: code,date,open,high,low,close")
    ap.add_argument("--signals", help="진입신호 CSV: code,entry_date[,horizon_days]")
    ap.add_argument("--trailing", action="store_true", help="샹들리에 트레일링 손절")
    ap.add_argument("--cost_bps", type=float, default=40.0)
    ap.add_argument("--period", type=int, default=14)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(0 if self_test() else 1)
    if not a.daily:
        sys.exit("일봉 데이터(--daily) 필요. 형식: code,date,open,high,low,close. "
                 "(--self-test로 로직 검증 가능)")
    daily_by = load_daily(a.daily)
    if a.signals:
        sig = []
        with open(a.signals, encoding="utf-8-sig") as fh:
            for row in csv.DictReader(fh):
                hz = int(row["horizon_days"]) if row.get("horizon_days") else 0
                sig.append((row["code"], row["entry_date"], hz))
    else:
        sig = [(code, bars[0][0], 0) for code, bars in daily_by.items()]
    run_grid(daily_by, sig, a.trailing, a.cost_bps, a.period)


if __name__ == "__main__":
    main()
