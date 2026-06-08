#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
track_w_v1.py — Track W 반사실 측정 (테마 lane forward 합격선 계산기)
재량(테마 픽)이 '같은 돈으로 시스템 픽' 들었을 때보다 나은가 = 재량 기여.
동결 합격선(시작prompt §9): 6개월 누적 반사실 ≥0 → lane 유지 / 음수 지속 → 축소·중단.
production·C·D·영역3·v41 무수정. 측정만 — 매수신호 아님.

입력: track_w_record.csv  (month, theme_pick_ret, system_pick_ret, theme_ew_ret, memo)
       *_ret = 그 달 수익률 %(예: 3.2 = +3.2%). 빈칸 = 미기입(스킵).
사용:
  python track_w_v1.py --self-test
  python track_w_v1.py            # 누적 반사실 + 판정 신호
"""
import csv, sys
from pathlib import Path

BASE = Path(__file__).parent.resolve()
REC = BASE / "track_w_record.csv"


def load():
    if not REC.exists():
        return []
    out = []
    for r in csv.DictReader(open(REC, encoding="utf-8-sig")):
        def f(k):
            try:
                return float(r.get(k, ""))
            except (ValueError, TypeError):
                return None
        out.append({"month": r.get("month", ""), "tp": f("theme_pick_ret"),
                    "sp": f("system_pick_ret"), "ew": f("theme_ew_ret"), "memo": r.get("memo", "")})
    return out


def cum(series):
    c = 1.0
    for x in series:
        if x is not None:
            c *= (1 + x / 100)
    return (c - 1) * 100


def analyze(rows):
    valid = [r for r in rows if r["tp"] is not None and r["sp"] is not None]
    contrib = [r["tp"] - r["sp"] for r in valid]
    ct = cum([r["tp"] for r in valid])
    cs = cum([r["sp"] for r in valid])
    cc = ct - cs
    cew = cum([r["ew"] for r in valid if r["ew"] is not None]) if any(r["ew"] is not None for r in valid) else None
    return valid, contrib, ct, cs, cc, cew


def main():
    rows = load()
    valid, contrib, ct, cs, cc, cew = analyze(rows)
    print("=== Track W 반사실 측정 (재량 기여) ===")
    if not valid:
        print("  기록 없음 — track_w_record.csv에 월별 수익률을 채우면 계산됩니다. (첫 기록 예정 2026-06말)")
        return
    print("월       | 테마픽% | 시스템픽% | 재량기여%p | 메모")
    for r in valid:
        print("  %-8s %+7.1f %+9.1f %+9.1f  %s" % (r["month"], r["tp"], r["sp"], r["tp"] - r["sp"], r["memo"]))
    print("-" * 50)
    print("누적: 테마픽 %+.1f%% / 시스템픽 %+.1f%% → 재량 누적기여 %+.1f%%p (%d개월)" % (ct, cs, cc, len(valid)))
    if cew is not None:
        print("     테마EW 누적 %+.1f%% — 픽이 테마EW도 이기나: %s" % (cew, "예" if ct > cew else "아니오(종목선택 기여 의문)"))
    n = len(valid)
    verdict = "유지/확대" if cc >= 0 else "축소·중단 검토"
    flag = "본판정(6개월↑)" if n >= 6 else ("중간 누적 %d개월" % n)
    print("\n★ %s: 재량 누적기여 %+.1f%%p → %s  (동결 합격선: 6개월 누적 ≥0)" % (flag, cc, verdict))


def self_test():
    rows = [{"month": "2026-06", "tp": 5.0, "sp": 2.0, "ew": 4.0, "memo": ""},
            {"month": "2026-07", "tp": -3.0, "sp": -1.0, "ew": -2.0, "memo": ""}]
    valid, contrib, ct, cs, cc, cew = analyze(rows)
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot
        tot += 1; ok += 1 if c else 0
        print("  [%s] %s" % ("OK" if c else "FAIL", n))
    chk("2개월 valid", len(valid) == 2)
    chk("월기여 6월=+3%p", abs(contrib[0] - 3.0) < 1e-9)
    chk("누적 테마(1.85%)>시스템(0.98%)", ct > cs)
    chk("누적기여 부호 +", cc > 0)
    chk("테마EW 누적 계산됨", cew is not None)
    print("self-test: %d/%d" % (ok, tot))
    return ok == tot


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        main()
