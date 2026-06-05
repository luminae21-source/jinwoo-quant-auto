#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kosdaq_relative_screen.py — KOSPI/KOSDAQ 시장-상대 분리 스크린 (PC 실행, FDR 필요)
==============================================================================
진우님 인사이트 반영: 시총분포가 다른 두 시장을 pool해 단일 랭크로 보면 왜곡 →
시장 라벨(FDR StockListing)로 가른 뒤, 합본 PIT 점수를 '시장 내 상대 랭크'로 재분류.
알테오젠·ISC가 KOSDAQ 내 기준에선 어디인지 + KOSDAQ 룰 상위 후보 + 현 18종목 시장별 분류를 출력.

* 1차 컷: 기존 합본 PIT 점수를 시장별로 재랭크(점수 자체는 pool 기준). 더 엄밀히 하려면
  KOSDAQ 모멘텀/시총을 KOSDAQ 시장 기준으로 재계산해야 함(다음 단계). 분류 방향성엔 충분.
입력: fundamentals_pit.csv + kospi_monthly_prices.csv (합본) + (선택) liquidity_sector.csv
사용: python kosdaq_relative_screen.py     (market_map.csv 없으면 FDR로 자동 생성·캐시)
"""
import sys, os
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import pandas as pd, numpy as np
import pit_universe_backtest as PB

MAP = "market_map.csv"
KEEP_PCT = 0.33   # 시장-상대 상위 33% = '유지 정당'


def build_market_map():
    if os.path.exists(MAP):
        m = pd.read_csv(MAP, dtype=str)
        return dict(zip(m["code"].str.zfill(6), m["market"]))
    import FinanceDataReader as fdr
    mp = {}
    for mk in ("KOSPI", "KOSDAQ"):
        lst = fdr.StockListing(mk)
        col = next(c for c in lst.columns if c.lower() in ("code", "symbol"))
        for c in lst[col].dropna():
            mp[str(c).zfill(6)] = mk          # KOSDAQ가 뒤라 중복 시 KOSDAQ 우선 아님 → KOSPI 우선 보장 위해 아래 보정
    # KOSPI 우선(겹치면 KOSPI): 다시 KOSPI로 덮어쓰기
    lstk = fdr.StockListing("KOSPI"); colk = next(c for c in lstk.columns if c.lower() in ("code", "symbol"))
    for c in lstk[colk].dropna():
        mp[str(c).zfill(6)] = "KOSPI"
    pd.DataFrame([{"code": k, "market": v} for k, v in mp.items()]).to_csv(MAP, index=False, encoding="utf-8-sig")
    print(f"market_map.csv 저장 ({len(mp)} 종목)")
    return mp


def main():
    mkt = build_market_map()
    fund = pd.read_csv("fundamentals_pit.csv", dtype={"code": str}); fund["code"] = fund["code"].str.zfill(6)
    prices = pd.read_csv("kospi_monthly_prices.csv", index_col=0, parse_dates=True)
    prices.columns = [str(c).zfill(6) for c in prices.columns]
    pf = PB.piotroski(fund); months = prices.index; idx = len(months) - 1
    mret = prices.pct_change().mean(axis=1)
    sc = PB.score_at(idx, list(months), prices, mret, list(prices.columns), pf, months[idx].year)
    if sc is None or len(sc) == 0:
        print("점수 산출 실패"); return 1

    df = pd.DataFrame({"code": [str(c).zfill(6) for c in sc.index]})
    df["pool_rank"] = range(1, len(df) + 1)
    df["market"] = df["code"].map(lambda c: mkt.get(c, "UNKNOWN"))
    df["mkt_rank"] = df.groupby("market")["pool_rank"].rank(method="min").astype(int)
    df["mkt_n"] = df.groupby("market")["code"].transform("count")
    df["mkt_pct"] = df["mkt_rank"] / df["mkt_n"]

    nm = {}
    if os.path.exists("liquidity_sector.csv"):
        ls = pd.read_csv("liquidity_sector.csv", dtype={"code": str}); ls["code"] = ls["code"].str.zfill(6)
        nm = dict(zip(ls["code"], ls["name"]))
    def lbl(c): return f"{c}({nm.get(c,'?')})"

    nK = int((df.market == "KOSPI").sum()); nQ = int((df.market == "KOSDAQ").sum()); nU = int((df.market == "UNKNOWN").sum())
    print("=" * 70)
    print(f"시장-상대 분리 스크린 ({months[idx].date()}) | 후보 KOSPI {nK} / KOSDAQ {nQ} / UNKNOWN {nU}")
    print("=" * 70)

    print("\n[초점] 현 보유 KOSDAQ 종목 — pool 랭크 vs KOSDAQ-상대 랭크")
    for code in ("196170", "095340"):
        r = df[df.code == code]
        if len(r):
            r = r.iloc[0]
            verdict = "유지정당(상위33%)" if r.mkt_pct <= KEEP_PCT else ("관찰" if r.mkt_pct <= 0.7 else "제외권")
            print(f"  {lbl(code)} [{r.market}] : pool {r.pool_rank}/{len(df)}  ->  {r.market}-상대 {r.mkt_rank}/{r.mkt_n} (상위 {r.mkt_pct:.0%}) => {verdict}")
        else:
            print(f"  {code}: 점수 없음(데이터 부족)")

    print("\n[KOSDAQ 시장-상대 상위 12] (carve-in 후보 풀)")
    kq = df[df.market == "KOSDAQ"].sort_values("mkt_rank")
    for _, row in kq.head(12).iterrows():
        print(f"  {int(row.mkt_rank):>3}. {lbl(row.code)}   (pool {int(row.pool_rank)})")

    print("\n[현 18종목 — 시장-상대 분류]")
    fixed = [str(c).zfill(6) for c in PB.FIXED18]
    sub = df[df.code.isin(fixed)].sort_values(["market", "mkt_rank"])
    for _, row in sub.iterrows():
        tag = "유지정당" if row.mkt_pct <= KEEP_PCT else ("관찰" if row.mkt_pct <= 0.7 else "제외권")
        print(f"  {row.market:6} {lbl(row.code):24} {row.market}-상대 {int(row.mkt_rank):>3}/{int(row.mkt_n)} (상위 {row.mkt_pct:.0%}) {tag}")
    miss = [c for c in fixed if c not in set(df.code)]
    if miss: print("  (점수없음: " + ", ".join(lbl(c) for c in miss) + ")")
    print("\n주의: 점수는 합본(pool) 기준을 시장 내 재랭크한 1차 컷. KOSDAQ 모멘텀/시총을 KOSDAQ 기준으로")
    print("재계산하면 더 엄밀(다음 단계). 방향성: 큰 KOSDAQ는 pool에서 눌리던 게 시장-상대에선 올라옴.")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
