#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
combine_tracks.py — 두 트랙(KOSPI / KOSDAQ) 비교·배분 계산기
==============================================================================
각 트랙의 검증 지표(CAGR·Sharpe·MDD·시장초과 %p)를 넣으면:
  ① 엣지 재현 판정 (두 시장 독립 검증 — out-of-sample)
  ② 배분 비중 제안 (Sharpe 비례 → KOSDAQ cap 적용, 안정성 우선)
  ③ 블렌드 추정 + 정직한 단서
"숫자만" 입력하는 도구 — 데이터 불필요. 콘솔 결과가 나오면 바로 결정용.

사용:
  python combine_tracks.py --kosdaq-cagr 22 --kosdaq-sharpe 0.9 --kosdaq-mdd -32 --kosdaq-excess 6
  (KOSPI는 검증된 기본값 내장 — 필요 시 --kospi-* 로 덮어쓰기)
  python combine_tracks.py --selftest
의존성: 표준 라이브러리만.
"""
import argparse, sys


def analyze(kospi, kosdaq, kosdaq_cap=0.30):
    print("=== 두 트랙 비교 (KOSPI vs KOSDAQ) ===")
    print(f"{'지표':16}{'KOSPI':>10}{'KOSDAQ':>10}")
    for k, lab in [("cagr", "CAGR %"), ("sharpe", "Sharpe"), ("mdd", "MDD %"), ("excess", "시장초과 %p")]:
        kv = kospi.get(k); dv = kosdaq.get(k)
        ks = f"{kv:+.1f}" if kv is not None else "-"
        ds = f"{dv:+.1f}" if dv is not None else "대기"
        print(f"{lab:16}{ks:>10}{ds:>10}")

    if kosdaq.get("excess") is None:
        print("\nKOSDAQ 결과 대기 — 숫자 넣으면 재현 판정·배분이 나옵니다.")
        print("  예: python combine_tracks.py --kosdaq-cagr ? --kosdaq-sharpe ? --kosdaq-mdd ? --kosdaq-excess ?")
        return None

    # ① 엣지 재현 판정
    ke, de = kospi["excess"], kosdaq["excess"]
    print("\n① 엣지 재현 (시장 독립 검증):")
    if de > 1.0 and ke > 1.0:
        rep = "강함 — 두 시장 모두 시장 초과(엣지가 시장 특화 아님)"
    elif de > 0:
        rep = "부분 — KOSDAQ도 초과하나 약함(엣지 일부 재현)"
    else:
        rep = "실패 — KOSDAQ는 시장 초과 못 함 → 엣지는 KOSPI 특화(그것도 수확)"
    print(f"  KOSPI 초과 {ke:+.1f}%p · KOSDAQ 초과 {de:+.1f}%p → {rep}")

    # ② 배분 (Sharpe 비례 → KOSDAQ cap)
    print(f"\n② 배분 제안 (Sharpe 비례 후 KOSDAQ cap {kosdaq_cap:.0%}):")
    sk, sd = max(kospi.get("sharpe", 0), 0), max(kosdaq.get("sharpe", 0), 0)
    if de <= 0 or sd <= 0:
        wk, wd = 1.0, 0.0
        note = "KOSDAQ 엣지 없음 → KOSDAQ 0% (KOSPI 전담)"
    else:
        wd_raw = sd / (sk + sd) if (sk + sd) > 0 else 0.0
        wd = min(wd_raw, kosdaq_cap); wk = 1 - wd
        note = f"Sharpe 원시 KOSDAQ {wd_raw:.0%} → cap 적용 {wd:.0%}"
    print(f"  KOSPI {wk:.0%}  ·  KOSDAQ {wd:.0%}   ({note})")

    # ③ 블렌드 추정 (상관 무시 — 보수적)
    if kospi.get("cagr") is not None and kosdaq.get("cagr") is not None:
        bc = wk * kospi["cagr"] + wd * kosdaq["cagr"]
        bs = wk * kospi.get("sharpe", 0) + wd * kosdaq.get("sharpe", 0)
        print(f"\n③ 블렌드(가중평균, 분산효과 무시): CAGR ~{bc:+.1f}% · Sharpe ~{bs:.2f}")
        print("   (실제로는 두 시장 상관<1이라 분산효과로 Sharpe가 이보다 높을 수 있음)")

    print("\n정직한 단서: KOSDAQ는 변동성·유동성·상폐 위험↑ → cap은 안정성 보호. "
          "백테스트 수치는 forward 보장 아님 · 최종 배분은 본인 위험허용도.")
    return {"w_kospi": wk, "w_kosdaq": wd, "replication": rep}


def _selftest():
    kospi = {"cagr": 17.0, "sharpe": 1.65, "mdd": -23.4, "excess": 9.7}
    # 케이스1: KOSDAQ 엣지 재현
    r1 = analyze(kospi, {"cagr": 24.0, "sharpe": 1.0, "mdd": -34.0, "excess": 6.0}, kosdaq_cap=0.30)
    assert r1 and abs(r1["w_kospi"] + r1["w_kosdaq"] - 1.0) < 1e-9
    assert r1["w_kosdaq"] <= 0.30 + 1e-9, "cap 위반"
    # 케이스2: KOSDAQ 엣지 없음 → 0%
    print("\n--- 케이스2: KOSDAQ 초과 음수 ---")
    r2 = analyze(kospi, {"cagr": 8.0, "sharpe": 0.3, "mdd": -40.0, "excess": -2.0}, kosdaq_cap=0.30)
    assert r2 and r2["w_kosdaq"] == 0.0, "엣지 없음인데 KOSDAQ 배분됨"
    print("\n[OK] combine_tracks selftest 통과 (재현 판정·cap·0배분)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    # KOSPI 기본값 = 검증된 regime 트랙(필요 시 덮어쓰기)
    ap.add_argument("--kospi-cagr", type=float, default=17.0)
    ap.add_argument("--kospi-sharpe", type=float, default=1.65)
    ap.add_argument("--kospi-mdd", type=float, default=-23.4)
    ap.add_argument("--kospi-excess", type=float, default=9.7)
    ap.add_argument("--kosdaq-cagr", type=float, default=None)
    ap.add_argument("--kosdaq-sharpe", type=float, default=None)
    ap.add_argument("--kosdaq-mdd", type=float, default=None)
    ap.add_argument("--kosdaq-excess", type=float, default=None)
    ap.add_argument("--kosdaq-cap", type=float, default=0.30)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    kospi = {"cagr": a.kospi_cagr, "sharpe": a.kospi_sharpe, "mdd": a.kospi_mdd, "excess": a.kospi_excess}
    kosdaq = {"cagr": a.kosdaq_cagr, "sharpe": a.kosdaq_sharpe, "mdd": a.kosdaq_mdd, "excess": a.kosdaq_excess}
    analyze(kospi, kosdaq, a.kosdaq_cap)


if __name__ == "__main__":
    sys.exit(main() or 0)
