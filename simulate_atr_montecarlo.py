#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
simulate_atr_montecarlo.py — 테마 ATR(k) 손절 몬테카를로 검증 (2026-06-07)

배경: 샌드박스는 KRX/Yahoo 네트워크 차단 → 실제 일봉 미수집(검증결과 문서 §2 참조).
   그래서 '지금 가능한 최대치'로, 워치리스트 12종목의 **월봉에서 일별 변동성을 캘리브레이션**해
   현실적인 코스닥-테마 일봉 경로를 시뮬레이션하고, k 그리드의 강건성을 본다.

⚠ 이것은 실데이터 검증이 아니라 **캘리브레이션 시뮬레이션**이다(프로젝트 §0 정직성).
   실측은 PC에서 fetch_theme_daily.py로 일봉 받은 뒤 validate_atr_stop.py로. 본 스크립트는
   "k 선택이 변동성 가정 전반에서 강건한가"를 미리 점검해 k=3 seed를 덜 임의적으로 만든다.

가정(모두 --인자로 조정): drift 0(노이즈로만 손절 판정·보수적) · t분포(df=4) 두꺼운 꼬리 ·
   overnight 갭(확률 0.2, 2×σ) · 일중 H/L(±1×σ) · 한국 ±30% 상하한 클램프 · 비용 40bp왕복.
엔진: validate_atr_stop.simulate_trade 재사용(동일 손절 로직 → 일봉 생기면 같은 코드로 실측).

사용:
  python simulate_atr_montecarlo.py                 # 월봉 캘리브 + MC
  python simulate_atr_montecarlo.py --paths 800 --horizon 60 --drift 0.0
  python simulate_atr_montecarlo.py --self-test
"""
import argparse, csv, math, sys
import numpy as np
import validate_atr_stop as V

WATCH = ["247540","086520","277810","108490","087010","028300",
         "196170","036930","080220","043260","083650","257720"]
LIMIT = 0.30  # 한국 가격제한폭 ±30%


def calibrate(prices_csv="kosdaq_monthly_prices.csv"):
    """월봉 → 종목별 일변동성(월σ/√21). 반환 {code: sigma_daily}."""
    rows = list(csv.DictReader(open(prices_csv, encoding="utf-8-sig")))
    hdr = rows[0].keys()
    out = {}
    for c in WATCH:
        if c not in hdr:
            continue
        px = []
        for r in rows:
            try: px.append(float(r[c]))
            except (TypeError, ValueError): px.append(None)
        rets = [px[i] / px[i-1] - 1 for i in range(1, len(px)) if px[i] and px[i-1]]
        if len(rets) >= 6:
            sm = float(np.std(rets))
            out[c] = sm / math.sqrt(21)
    return out


def sim_path(sigma_d, L, drift, rng, p_gap=0.2, gap_mult=2.0, hl=1.0, tdf=4):
    """일별 OHLC 경로 생성. 반환 bars=[(date,o,h,l,c)]. 진입가=100 기준."""
    c_prev = 100.0
    bars = [("d0", 100.0, 100.0, 100.0, 100.0)]
    tscale = math.sqrt(tdf / (tdf - 2))  # t분포 분산 정규화
    for i in range(1, L + 1):
        # 종가 일수익 (t분포 두꺼운 꼬리)
        z = rng.standard_t(tdf) / tscale
        ret = drift + sigma_d * z
        # overnight 갭 → 시가
        gap = 0.0
        if rng.random() < p_gap:
            gap = rng.normal(0, gap_mult * sigma_d)
        gap = max(-LIMIT, min(LIMIT, gap))
        o = c_prev * (1 + gap)
        # 종가: 시가 대비 잔여 변동 (전일종가 대비 ±30% 클램프)
        intra = ret - gap
        c = o * (1 + intra)
        lo_lim, hi_lim = c_prev * (1 - LIMIT), c_prev * (1 + LIMIT)
        c = max(lo_lim, min(hi_lim, c))
        # 일중 H/L
        rng_amp = abs(rng.normal(0, hl * sigma_d))
        hi = max(o, c) * (1 + rng_amp)
        lo = min(o, c) * (1 - rng_amp)
        hi = min(hi, hi_lim); lo = max(lo, lo_lim)
        bars.append(("d%d" % i, o, hi, lo, c))
        c_prev = c
    return bars


def run(calib, paths, horizon, drift, cost_bps, seed=7):
    ks = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
    rng = np.random.default_rng(seed)
    agg = {("static", k): [] for k in ks}
    agg.update({("trail", k): [] for k in ks})
    holds = []
    stop_cnt = {("static", k): 0 for k in ks}; stop_cnt.update({("trail", k): 0 for k in ks})
    total = 0
    for code, sig in calib.items():
        for _ in range(paths):
            bars = sim_path(sig, horizon, drift, rng)
            holds.append(V.hold_return(bars, cost_bps))
            total += 1
            for k in ks:
                rs = V.simulate_trade(bars, k, 14, False, cost_bps)
                rt = V.simulate_trade(bars, k, 14, True, cost_bps)
                agg[("static", k)].append(rs["ret_pct"]); stop_cnt[("static", k)] += rs["stopped"]
                agg[("trail", k)].append(rt["ret_pct"]); stop_cnt[("trail", k)] += rt["stopped"]

    def stat(a):
        x = np.array(a)
        return (x.mean(), np.median(x), np.percentile(x, 5), x.min(),
                100 * (x > 0).mean())

    print("캘리브레이션 종목 %d | 종목당 %d경로 | 보유기간 %d일 | drift %.3f%%/일 | 비용 %dbp"
          % (len(calib), paths, horizon, drift * 100, cost_bps))
    print("⚠ 실데이터 아님 — 월봉 캘리브 시뮬. 실측은 PC fetch 후 validate_atr_stop.py\n")
    hm, hmed, hp5, hw, hwin = stat(holds)
    print("%-14s | %7s %7s %8s %8s %7s %7s" % ("전략", "평균%", "중앙%", "5%꼬리%", "워스트%", "승률%", "손절률%"))
    print("-" * 70)
    print("%-14s | %7.1f %7.1f %8.1f %8.1f %7.1f %7s" % ("보유(無손절)", hm, hmed, hp5, hw, hwin, "-"))
    for mode in ("static", "trail"):
        for k in ks:
            m, med, p5, w, win = stat(agg[(mode, k)])
            sr = 100 * stop_cnt[(mode, k)] / total
            label = ("정적 %.1f×" % k) if mode == "static" else ("트레일 %.1f×" % k)
            print("%-14s | %7.1f %7.1f %8.1f %8.1f %7.1f %7.1f" % (label, m, med, p5, w, win, sr))
        print("-" * 70)
    print("해석: '5%꼬리·워스트'를 보유 대비 얼마나 줄이면서 '평균·중앙'을 덜 깎는 k가 강건. "
          "손절률이 과하면(휩쏘) k↑. 워스트가 −20% 부근이면 하한가 위험권.")


def self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += bool(c); print(("  [%s] " % ("OK" if c else "XX")) + n)
    rng = np.random.default_rng(1)
    bars = sim_path(0.05, 60, 0.0, rng)
    chk("경로 길이 = horizon+1", len(bars) == 61)
    chk("H≥max(O,C) 및 L≤min(O,C)", all(b[2] >= max(b[1], b[4]) - 1e-6 and b[3] <= min(b[1], b[4]) + 1e-6 for b in bars))
    # ±30% 클램프: 일간 종가변동 ≤ 30%
    okclamp = True
    for i in range(1, len(bars)):
        if abs(bars[i][4] / bars[i-1][4] - 1) > 0.3 + 1e-6: okclamp = False
    chk("일 종가변동 ≤ ±30% 클램프", okclamp)
    # 고변동일수록 손절률↑ (k 고정)
    rng2 = np.random.default_rng(2)
    calib_lo = {"a": 0.02}; calib_hi = {"a": 0.08}
    import io, contextlib
    def stoprate(calib):
        r = np.random.default_rng(3); cnt = 0; n = 0
        for _ in range(200):
            b = sim_path(list(calib.values())[0], 60, 0.0, r)
            cnt += V.simulate_trade(b, 3.0, 14, False, 0)["stopped"]; n += 1
        return cnt / n
    chk("고변동→손절률↑ (동일 k=3)", stoprate(calib_hi) > stoprate(calib_lo))
    print("\nself-test: %d/%d 통과" % (ok, tot))
    return ok == tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices", default="kosdaq_monthly_prices.csv")
    ap.add_argument("--paths", type=int, default=500)
    ap.add_argument("--horizon", type=int, default=60)
    ap.add_argument("--drift", type=float, default=0.0)
    ap.add_argument("--cost_bps", type=float, default=40.0)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(0 if self_test() else 1)
    calib = calibrate(a.prices)
    if not calib:
        sys.exit("캘리브레이션 실패 — 월봉에서 워치리스트 코드를 못 찾음.")
    run(calib, a.paths, a.horizon, a.drift, a.cost_bps)


if __name__ == "__main__":
    main()
