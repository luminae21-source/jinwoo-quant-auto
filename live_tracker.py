#!/usr/bin/env python3
"""
live_tracker.py — 진우퀀트 라이브 실현 alpha 추적 (#1)
==============================================================================
매월 실현 포트폴리오·KOSPI 수익을 기록하고, 실현 시장초과(alpha)가
  · 체계적 경로  : 시장 +9.7%p/년 (PIT-systematic, 반복가능 기대)
  · 백테스트 경로: 시장 +25.9%p/년 (fixed-18, hindsight 포함 — 비현실 상한)
중 어디로 가는지 판정. forward 기대치(검증핸드오프 §3) 대조용.

기록: live_record.csv  [date(YYYY-MM), port_ret_pct, kospi_ret_pct]
사용:
  python live_tracker.py --add 2026-06 4.2 1.1     # 한 달 추가
  python live_tracker.py                            # 누적 분석
  python live_tracker.py --selftest
의존성: numpy (+ stdlib csv)
"""
import argparse, csv, os, sys, math
import numpy as np

REC = "live_record.csv"
SYS_ANN, BT_ANN = 0.097, 0.259


def add_month(date, port_pct, kospi_pct, path=REC):
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8-sig") as f:
        w = csv.writer(f)
        if new: w.writerow(["date", "port_ret_pct", "kospi_ret_pct"])
        w.writerow([date, f"{float(port_pct):.4f}", f"{float(kospi_pct):.4f}"])
    print(f"기록: {date}  port {float(port_pct):+.2f}%  kospi {float(kospi_pct):+.2f}%  -> {path}")


def _load(path=REC):
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    d = [r["date"] for r in rows]
    p = np.array([float(r["port_ret_pct"]) for r in rows]) / 100.0
    k = np.array([float(r["kospi_ret_pct"]) for r in rows]) / 100.0
    return d, p, k


def analyze(path=REC):
    d, p, k = _load(path)
    n = len(p)
    if n < 1: print("기록 없음"); return None
    active = p - k
    port_cagr = float(np.prod(1+p)**(12/n) - 1); kospi_cagr = float(np.prod(1+k)**(12/n) - 1)
    excess_cagr = port_cagr - kospi_cagr
    print(f"=== 라이브 추적 ({n}개월: {d[0]}~{d[-1]}) ===")
    print(f"포트 CAGR {port_cagr:+.1%} | KOSPI {kospi_cagr:+.1%} | 실현 시장초과(CAGR) {excess_cagr:+.1%}")
    ann_alpha = None
    if n > 1:
        mean_m, sd_m = active.mean(), active.std(ddof=1)
        ann_alpha = mean_m * 12
        se_ann = sd_m * math.sqrt(12) / math.sqrt(n)
        ir = (mean_m / sd_m * math.sqrt(12)) if sd_m > 0 else float("nan")
        lo, hi = ann_alpha - 1.96*se_ann, ann_alpha + 1.96*se_ann
        print(f"연환산 alpha(산술) {ann_alpha:+.1%}  95%CI [{lo:+.1%}, {hi:+.1%}]  | IR {ir:.2f}")
        print("기준선: 체계적 +9.7%p · 백테스트 +25.9%p")
        a = ann_alpha
        if a < 0: v = "시장 하회 — 점검 필요"
        elif a < SYS_ANN*0.5: v = "체계적 기대 이하"
        elif a <= SYS_ANN*1.7: v = "체계적 경로(+10%p대) 추적 — forward 기대 일치 (정상)"
        elif a < BT_ANN*0.8: v = "체계적~백테스트 중간"
        else: v = "백테스트 수준(+26%p) — 드묾, 지속성 관찰"
        print(f"판정: {v}")
        gap = BT_ANN - SYS_ANN; avol = sd_m * math.sqrt(12)
        yrs = (avol / (gap/(2*1.96)))**2 if gap > 0 and avol > 0 else float("inf")
        print(f"\n주의: 두 경로(+9.7 vs +25.9) 통계적 구분에 ~{yrs:.0f}년치 필요(active vol {avol:.0%}). "
              "라이브만으론 느림 — PIT 검증(완료)이 더 빠른 답.")
    else:
        print("(2개월 이상부터 alpha·CI 산출)")
    return {"n": n, "excess_cagr": excess_cagr, "ann_alpha": ann_alpha}


def _selftest():
    rng = np.random.default_rng(0); p = "_live_test.csv"
    rows = [["date", "port_ret_pct", "kospi_ret_pct"]]
    for i in range(18):
        act = rng.normal(0.008, 0.04); kp = rng.normal(0.01, 0.05)
        rows.append([f"2026-{(i%12)+1:02d}", f"{(kp+act)*100:.4f}", f"{kp*100:.4f}"])
    with open(p, "w", newline="", encoding="utf-8-sig") as f:
        csv.writer(f).writerows(rows)
    r = analyze(p)
    try: os.remove(p)
    except OSError: pass
    assert r and r["n"] == 18 and r["ann_alpha"] is not None
    print("\n[OK] live_tracker selftest 통과")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--add", nargs=3, metavar=("DATE", "PORT", "KOSPI"))
    ap.add_argument("--record", default=REC)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest: return _selftest()
    if a.add: add_month(a.add[0], a.add[1], a.add[2], a.record); return 0
    if not os.path.exists(a.record):
        print(f"{a.record} 없음 → 매월 'python live_tracker.py --add YYYY-MM 포트% KOSPI%' 로 기록 시작"); return 0
    analyze(a.record)


if __name__ == "__main__":
    sys.exit(main() or 0)
