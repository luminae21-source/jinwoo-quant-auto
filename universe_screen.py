#!/usr/bin/env python3
"""
universe_screen.py — #2 universe 규칙화 1단계: 현재 18종목의 '룰 정당성' 진단
==============================================================================
PIT 점수(Piotroski-F + Sloan + NOA + Mom12 + BAB + Echo)로 KOSPI 전체를 최신 시점에
재랭크 → 현재 18종목 중 (a) 체계적 룰이 top-N에 뽑는 것 = 규칙 정당, (b) 안 뽑는 것 = 재량 hold(편향 위험).
+ 룰이 제안하는 체계적 top-N 후보 리스트. (선택편향을 줄이는 '규칙화'의 출발점)

입력: fundamentals_pit.csv + kospi_monthly_prices.csv (pit_universe_backtest 점수 재사용)
사용: python universe_screen.py --top-n 18   /   --selftest
의존성: numpy, pandas, pit_universe_backtest.py
"""
import argparse, os, sys
import numpy as np, pandas as pd
import pit_universe_backtest as PB


def screen(fund_csv, prices_csv, top_n=18, fixed=None):
    fixed = fixed or PB.FIXED18
    fund = pd.read_csv(fund_csv, dtype={"code": str}); fund["code"] = fund["code"].str.zfill(6)
    prices = pd.read_csv(prices_csv, index_col=0, parse_dates=True)
    prices.columns = [str(c).zfill(6) for c in prices.columns]
    pf = PB.piotroski(fund)
    months = prices.index; idx = len(months) - 1
    mkt = prices.pct_change().mean(axis=1)
    sc = PB.score_at(idx, list(months), prices, mkt, list(prices.columns), pf, months[idx].year)
    if sc.empty: print("점수 산출 실패(데이터 확인)"); return None
    rank = {c: i+1 for i, c in enumerate(sc.index)}          # 1=최고
    topN = set(list(sc.index[:top_n]))
    print(f"=== universe 규칙화 진단 ({months[idx].date()}, 후보 {len(sc)}종목 중 top-{top_n}) ===")
    in_n = [c for c in fixed if c in topN]
    out_n = [c for c in fixed if c in rank and c not in topN]
    missing = [c for c in fixed if c not in rank]
    print(f"현재 18종목 중 룰 정당(top-{top_n} 포함): {len(in_n)}개 | 재량 hold(미포함): {len(out_n)}개 | 데이터없음: {len(missing)}개")
    print(f"\n[재량 hold — 룰이 안 뽑음, 편향 위험] 코드: 랭크")
    for c in sorted(out_n, key=lambda x: rank[x]):
        print(f"  {c}: rank {rank[c]}/{len(sc)}")
    print(f"\n[룰이 새로 추천 — 현재 18에 없는 체계적 top-{top_n}]")
    new = [c for c in sc.index[:top_n] if c not in set(fixed)]
    print("  " + (", ".join(new) if new else "(없음)"))
    jr = len(in_n)/len([c for c in fixed if c in rank]) if [c for c in fixed if c in rank] else 0
    print(f"\n규칙 정당성 비율: {jr:.0%}  → 낮을수록 universe가 재량(hindsight) 의존적")
    print("권장: 재량 hold 종목은 (1) 룰 편입될 때까지 비중 축소 또는 (2) 별도 '관찰' 트랙으로 분리해 편향 격리")
    return {"in": in_n, "out": out_n, "new": new, "justified_ratio": jr}


def _selftest():
    rng = np.random.default_rng(1); K, Tm = 50, 40
    idx = pd.date_range("2022-01-31", periods=Tm, freq="ME"); codes = [f"{i:06d}" for i in range(K)]
    good = set(codes[:15])
    px = pd.DataFrame(index=idx, columns=codes, dtype=float)
    for c in codes:
        dr = rng.normal(0.025 if c in good else 0.004, 0.002); px[c] = 1000*np.cumprod(1+rng.normal(dr, 0.06, Tm))
    fr = []
    for c in codes:
        for fy in range(2021, 2025):
            b = 1.0 if c in good else 0.3
            fr.append(dict(code=c, fiscal_year=fy, revenue=1e9*b, cogs=6e8*b, op_income=2e8*b,
                net_income=2e8*b if c in good else -1e7, assets=5e9, liabilities=2e9, equity=3e9,
                current_assets=2e9, current_liab=1e9, cash=5e8, cfo=2.5e8*b if c in good else 1e7,
                noncurrent_liab=1e9, issued_capital=1e8))
    pd.DataFrame(fr).to_csv("_us_f.csv", index=False); px.to_csv("_us_p.csv")
    fixed = [f"{i:06d}" for i in range(10, 28)]   # 10~27: 일부 good(10~14) + 다수 non-good
    r = screen("_us_f.csv", "_us_p.csv", top_n=15, fixed=fixed)
    for x in ("_us_f.csv", "_us_p.csv"):
        try: os.remove(x)
        except OSError: pass
    assert r and r["justified_ratio"] < 0.6     # 재량 비중 큰 fixed → 정당성 낮게 진단
    print("\n[OK] universe_screen selftest 통과 (재량 hold 식별)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fundamentals", default="fundamentals_pit.csv")
    ap.add_argument("--prices", default="kospi_monthly_prices.csv")
    ap.add_argument("--top-n", type=int, default=18)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest: return _selftest()
    if not os.path.exists(a.fundamentals): raise SystemExit(f"{a.fundamentals} 없음 → fetch_dart_fundamentals_pit.py 먼저")
    if not os.path.exists(a.prices): raise SystemExit(f"{a.prices} 없음 → build_korea_factors.py 먼저(캐시)")
    screen(a.fundamentals, a.prices, a.top_n)


if __name__ == "__main__":
    sys.exit(main() or 0)
