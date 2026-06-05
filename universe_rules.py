#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
universe_rules.py — #2 universe 규칙화: 편입/제외 룰 엔진 (반-체계, propose-not-replace)
==============================================================================
PIT 점수 + Piotroski + 재무악화 + 지속성 + (실)시총·거래대금·섹터로 현재 보유 종목을
유지/제외후보/관찰(편향 hold)로 분류하고, 룰 기반 편입후보(거래 잘 되는 대형·분산 종목)를
제시 + 점진 전환 플랜. 룰은 후보 생성기/가드레일, 최종 결정은 사람.

입력: fundamentals_pit.csv + kospi_monthly_prices.csv (+ liquidity_sector.csv 있으면 정밀화)
사용: python universe_rules.py   /   --selftest
의존성: numpy, pandas, pit_universe_backtest.py (이름·섹터는 liquidity_sector.csv / score_v37)
"""
import argparse, os, sys
import numpy as np, pandas as pd
import pit_universe_backtest as PB

# ---- 디폴트 임계값 (튜닝 가능) ----
PIOTROSKI_MIN = 6        # 편입/유지 품질 하한
KEEP_TOP_PCT = 0.33      # '유지' 인정: PIT 점수 상위 1/3
SCORE_BOTTOM_PCT = 0.30  # 하위 30% = 제외 신호
SIZE_TOP = 200           # 시총 상위 N (실 mcap 있으면 그것으로, 없으면 총자산 proxy)
LIQ_KEEP_PCT = 0.60      # 편입후보 유동성: 거래대금 상위 60% 이상
SECTOR_CAP = 3           # 섹터당 편입후보 최대 (분산)
MIN_MONTHS = 12          # 후보군 최소 지속
MAX_SWAP_Q = 2           # 분기당 최대 교체


def _load_names():
    try:
        import score_v37 as S
        best = {}
        for v in vars(S).values():
            if isinstance(v, dict):
                m = {str(val["코드"]).zfill(6): str(k) for k, val in v.items()
                     if isinstance(val, dict) and "코드" in val}
                if len(m) > len(best): best = m
        return best
    except Exception:
        return {}


def _load_liq(path):
    if not os.path.exists(path): return None
    d = pd.read_csv(path, dtype={"code": str}); d["code"] = d["code"].str.zfill(6)
    return d.drop_duplicates("code").set_index("code")


def _latest_two(fund):
    out = {}
    for c, g in fund.sort_values(["code", "fiscal_year"]).groupby("code"):
        b = g.iloc[-1]
        roa_b = b.net_income / b.assets if b.assets else np.nan
        det = bool((b.net_income < 0) or (b.get("cfo", 0) < 0))
        if len(g) >= 2:
            a = g.iloc[-2]; roa_a = a.net_income / a.assets if a.assets else np.nan
            if pd.notna(roa_a) and pd.notna(roa_b) and roa_b < roa_a - 0.02: det = True
        out[c] = {"deteriorated": det, "assets": float(b.assets) if b.assets else np.nan}
    return out


def screen(fund_csv, prices_csv, fixed=None, sectors=None, names=None, liq_csv="liquidity_sector.csv"):
    fixed = fixed or PB.FIXED18
    liq = _load_liq(liq_csv)
    nm = dict(names) if names is not None else _load_names()
    if liq is not None and "name" in liq:
        for c, v in liq["name"].dropna().items(): nm.setdefault(c, str(v))
    sec_map = dict(sectors) if sectors else {}
    if liq is not None and "sector" in liq:
        for c, v in liq["sector"].dropna().items(): sec_map[c] = str(v)

    def lbl(c): return f"{c}({nm[c]})" if nm.get(c) else c
    def sec_of(c): return sec_map.get(c)

    fund = pd.read_csv(fund_csv, dtype={"code": str}); fund["code"] = fund["code"].str.zfill(6)
    prices = pd.read_csv(prices_csv, index_col=0, parse_dates=True)
    prices.columns = [str(c).zfill(6) for c in prices.columns]
    pf = PB.piotroski(fund); months = prices.index; idx = len(months) - 1; yr = months[idx].year
    mkt = prices.pct_change().mean(axis=1)
    sc = PB.score_at(idx, list(months), prices, mkt, list(prices.columns), pf, yr)
    if sc.empty:
        print("점수 산출 실패"); return None
    rank = {c: i + 1 for i, c in enumerate(sc.index)}; N = len(sc)
    F = pf[pf.fiscal_year == yr - 1].set_index("code")["F"] if (pf.fiscal_year == yr - 1).any() else pf.groupby("code")["F"].last()
    det = _latest_two(fund)
    persist = prices.notna().sum()

    if liq is not None and liq["mcap"].notna().any():
        size_rank = liq["mcap"].rank(ascending=False)
        adtv_pct = liq["adtv"].rank(pct=True)              # 1=거래대금 최상
        def liq_ok(c): return bool(adtv_pct.get(c, 0) >= (1 - LIQ_KEEP_PCT))
        size_src = "실 시총·거래대금·섹터"
    else:
        size_rank = pd.Series({c: det[c]["assets"] for c in det if pd.notna(det[c]["assets"])}).rank(ascending=False)
        def liq_ok(c): return True
        size_src = "총자산 proxy (liquidity_sector.csv 없음 → 유동성·섹터 생략)"

    keep_band = N * KEEP_TOP_PCT; bottom = N * (1 - SCORE_BOTTOM_PCT)
    keep, excl, watch, nodata = [], [], [], []
    for c in fixed:
        if c not in rank: nodata.append(c); continue
        f_ok = float(F.get(c, 0)) >= PIOTROSKI_MIN
        det_c = det.get(c, {}).get("deteriorated", True); r = rank[c]
        if det_c or r > bottom: excl.append(c)
        elif f_ok and r <= keep_band: keep.append(c)
        else: watch.append(c)

    base = [c for c in sc.index if c not in set(fixed)
            and float(F.get(c, 0)) >= PIOTROSKI_MIN
            and not det.get(c, {}).get("deteriorated", True)
            and (size_rank.get(c, 9e9) <= SIZE_TOP)
            and persist.get(c, 0) >= MIN_MONTHS
            and liq_ok(c)]
    # 섹터 cap (현재 보유 섹터를 먼저 점유 → 분산)
    sec_count = {}
    for c in fixed:
        s = sec_of(c)
        if s: sec_count[s] = sec_count.get(s, 0) + 1
    cand = []
    for c in base:
        s = sec_of(c)
        if s and sec_count.get(s, 0) >= SECTOR_CAP: continue
        cand.append(c)
        if s: sec_count[s] = sec_count.get(s, 0) + 1

    def clab(c):
        s = sec_of(c); return f"{lbl(c)} r{rank[c]}" + (f" [{s}]" if s else "")

    print(f"=== universe 규칙화 ({months[idx].date()}, 후보 {N}종목) — 반-체계, 사람 검토 ===")
    print(f"데이터: {size_src}")
    print(f"임계값: 유지=상위{KEEP_TOP_PCT:.0%}(r≤{keep_band:.0f})&F≥{PIOTROSKI_MIN}&비악화 | 제외=하위{SCORE_BOTTOM_PCT:.0%}(r>{bottom:.0f})/재무악화 | 편입=시총상위{SIZE_TOP}∩거래대금상위{LIQ_KEEP_PCT:.0%}∩섹터≤{SECTOR_CAP}")
    print(f"현재 {len(fixed)}종목: 유지 {len(keep)} · 제외후보 {len(excl)} · 관찰(편향 hold) {len(watch)} · 데이터없음 {len(nodata)}")
    if excl: print("\n[제외후보] " + ", ".join(clab(c) for c in sorted(excl, key=lambda x: -rank.get(x, 0))))
    if watch: print("[관찰=재량 hold] " + ", ".join(clab(c) for c in sorted(watch, key=lambda x: rank.get(x, 9e9))))
    if keep: print("[유지] " + ", ".join(clab(c) for c in sorted(keep, key=lambda x: rank.get(x, 9e9))))
    if nodata: print("[데이터없음] (KOSPI 스크린 밖, 예: KOSDAQ) " + ", ".join(lbl(c) for c in nodata))
    print(f"\n[룰 편입후보 top10] (거래 잘 되는 대형·분산 종목)")
    print("  " + (", ".join(clab(c) for c in cand[:10]) if cand else "(없음)"))

    print(f"\n=== 점진 전환 플랜 (분기당 ≤{MAX_SWAP_Q}종목, propose-not-replace) ===")
    worst = sorted(excl, key=lambda c: -rank.get(c, 0))[:MAX_SWAP_Q]; best = cand[:MAX_SWAP_Q]
    if worst or best:
        for i in range(max(len(worst), len(best))):
            o = clab(worst[i]) if i < len(worst) else "-"; n = clab(best[i]) if i < len(best) else "-"
            print(f"  제안 {i+1}: 제외 {o} → 편입 {n}  (사람 검토 후 확정)")
    else:
        print("  교체 제안 없음")
    jr = len(keep) / max(1, len([c for c in fixed if c in rank]))
    print(f"\n규칙 정당성 {jr:.0%} | 관찰(편향) {len(watch)}종목 → 비중축소/별도추적 권장")
    if liq is None:
        print("힌트: `python fetch_liquidity_sector.py` 실행 후 다시 돌리면 유동성·섹터 필터가 적용됩니다.")
    return {"keep": keep, "excl": excl, "watch": watch, "cand": cand[:10]}


def _selftest():
    rng = np.random.default_rng(2); K, Tm = 50, 40
    idx = pd.date_range("2022-01-31", periods=Tm, freq="ME"); codes = [f"{i:06d}" for i in range(K)]
    good = set(codes[:15])
    px = pd.DataFrame(index=idx, columns=codes, dtype=float)
    for c in codes:
        dr = rng.normal(0.025 if c in good else 0.004, 0.002)
        px[c] = 1000 * np.cumprod(1 + rng.normal(dr, 0.06, Tm))
    fr = []
    for c in codes:
        for k, fy in enumerate(range(2021, 2025)):
            if c in good:
                g = 1 + 0.10 * k
                fr.append(dict(code=c, fiscal_year=fy, revenue=1e9*g, cogs=5.5e8*g*(1-0.02*k), op_income=2.4e8*g,
                    net_income=2e8*g, assets=5e9*(1+0.05*k), liabilities=5e9*(1+0.05*k)*0.4, equity=5e9*(1+0.05*k)*0.6,
                    current_assets=2e9*(1+0.04*k), current_liab=1e9*(1-0.02*k), cash=5e8, cfo=2.6e8*g,
                    noncurrent_liab=1e9*(1-0.06*k), issued_capital=1e8))
            else:
                fr.append(dict(code=c, fiscal_year=fy, revenue=1e9, cogs=6.8e8, op_income=-5e6,
                    net_income=-1e7, assets=5e9, liabilities=2.5e9, equity=2.5e9, current_assets=1.5e9,
                    current_liab=1e9, cash=5e8, cfo=-1e7, noncurrent_liab=1.2e9, issued_capital=1e8*(1+0.1*k)))
    pd.DataFrame(fr).to_csv("_ur_f.csv", index=False); px.to_csv("_ur_p.csv")
    fixed = [f"{i:06d}" for i in range(10, 28)]
    print("--- (1) liquidity_sector 없음 (자산 proxy) ---")
    r1 = screen("_ur_f.csv", "_ur_p.csv", fixed=fixed, sectors={}, names={}, liq_csv="__none__.csv")
    # (2) 유동성·섹터 csv 적용: code0 거래대금 최저(제외), 0~9 모두 반도체(섹터 cap)
    sec = ["반도체"]*10 + ["바이오"]*10 + ["금융"]*10 + ["식품"]*10 + ["기타"]*10
    adtv = [1e8] + [1e12]*9 + [5e11]*40
    pd.DataFrame({"code": codes, "name": [f"종목{i}" for i in range(K)], "sector": sec,
                  "mcap": [1e13-1e9*i for i in range(K)], "adtv": adtv}).to_csv("_ur_liq.csv", index=False)
    print("\n--- (2) liquidity_sector 적용 ---")
    r2 = screen("_ur_f.csv", "_ur_p.csv", fixed=fixed, sectors={}, names={}, liq_csv="_ur_liq.csv")
    for x in ("_ur_f.csv", "_ur_p.csv", "_ur_liq.csv"):
        try: os.remove(x)
        except OSError: pass
    assert r1 and len(r1["excl"]) >= 3 and len(r1["cand"]) >= 1
    assert r2 and "000000" not in r2["cand"], "유동성 필터가 저거래대금 종목 못 거름"
    assert sum(1 for c in r2["cand"] if c in {f"{i:06d}" for i in range(10)}) <= SECTOR_CAP, "섹터 cap 미작동"
    print("\n[OK] universe_rules selftest 통과 (proxy/유동성·섹터 양쪽 + cap·유동성 필터)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--fundamentals", default="fundamentals_pit.csv")
    ap.add_argument("--prices", default="kospi_monthly_prices.csv")
    ap.add_argument("--liquidity", default="liquidity_sector.csv")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest: return _selftest()
    if not os.path.exists(a.fundamentals): raise SystemExit(f"{a.fundamentals} 없음 → fetch_dart_fundamentals_pit.py 먼저")
    if not os.path.exists(a.prices): raise SystemExit(f"{a.prices} 없음 → build_korea_factors.py 먼저(캐시)")
    screen(a.fundamentals, a.prices, liq_csv=a.liquidity)


if __name__ == "__main__":
    sys.exit(main() or 0)
