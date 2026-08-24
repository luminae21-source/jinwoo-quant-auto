#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
trackw_score.py — Track W 반사실 스코어러 (재량이 밥값 하나 측정)
정본 규율: ① 재량기여 = W − 시스템픽(반사실)  ② 테마기여 = W − 테마EW (테마EW도 못 이기면 종목선택 기여=0)
6~12개월 누적으로 판정. backtest 아님(실전 반사실). production·C·D·영역3·v41 무수정.

입력 trackw_ledger.csv: month,W_ret,sys_ret,themeEW_ret[,note]  (수익 소수)
사용: python trackw_score.py  /  --selftest
"""
import argparse, csv, sys


def cum(rets):
    c = 1.0
    for r in rets:
        c *= (1 + r)
    return c - 1.0


def ann(rets):
    if not rets:
        return float("nan")
    c = 1.0
    for r in rets:
        c *= (1 + r)
    return c ** (12.0 / len(rets)) - 1 if c > 0 else float("nan")


def load(path):
    rows = []
    for r in csv.DictReader(open(path, encoding="utf-8-sig")):
        m = (r.get("month") or "").strip()
        if not m or m.startswith("#"):
            continue
        try:
            rows.append((m, float(r["W_ret"]), float(r["sys_ret"]), float(r["themeEW_ret"])))
        except (ValueError, KeyError, TypeError):
            continue  # 빈칸 월 skip
    return sorted(rows)


def report(rows):
    if not rows:
        print("기록된 월 없음 — trackw_ledger.csv에 월수익 채우고 다시 실행."); return
    W = [r[1] for r in rows]; S = [r[2] for r in rows]; T = [r[3] for r in rows]
    n = len(rows)
    print("Track W 반사실 — %d개월 (%s~%s)" % (n, rows[0][0], rows[-1][0]))
    print("-" * 58)
    print("  누적: W %+.2f%% | 시스템픽(반사실) %+.2f%% | 테마EW %+.2f%%" % (cum(W)*100, cum(S)*100, cum(T)*100))
    print("  연율: W %+.2f%% | 시스템 %+.2f%% | 테마EW %+.2f%%" % (ann(W)*100, ann(S)*100, ann(T)*100))
    dW_S = cum(W) - cum(S); dW_T = cum(W) - cum(T)
    print("\n  ① 재량기여(W−시스템) = %+.2f%%p" % (dW_S*100))
    print("  ② 테마초과(W−테마EW) = %+.2f%%p" % (dW_T*100))
    print("-" * 58)
    # 판정(누적 ≥6개월부터 의미)
    if n < 6:
        print("  판정: 표본 %d개월(<6) — 누적 더 쌓고 6~12개월에 판정." % n); return
    if dW_T <= 0:
        v = "종목선택 기여 ≈ 0 (테마EW도 못 이김) → 테마 ETF가 나음. 재량 축소 검토."
    elif dW_S > 0 and dW_T > 0:
        v = "재량이 시스템·테마EW 둘 다 이김 → 재량 lane 유지/확대 논의 가능."
    else:
        v = "혼조 — 재량>테마EW이나 시스템 대비 미흡. 계속 관찰."
    print("  판정:", v)
    print("  (정직: 실전 반사실 · 6~12개월 누적 · 데이터가 결정, 느낌 아님)")


def selftest():
    rows = [("2026-%02d" % m, 0.03, 0.01, 0.02) for m in range(6, 13)]  # W>sys>themeEW 7개월
    print("[selftest] W=3%/sys=1%/themeEW=2% × 7개월"); report(rows)
    assert cum([r[1] for r in rows]) > cum([r[3] for r in rows]) > cum([r[2] for r in rows]), "정렬오류"
    print("[selftest] OK")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default="trackw_ledger.csv")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest(); return
    report(load(a.ledger))


if __name__ == "__main__":
    main()
