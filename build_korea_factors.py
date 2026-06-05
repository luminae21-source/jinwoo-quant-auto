#!/usr/bin/env python3
"""
build_korea_factors.py — 한국 FF/Carhart 팩터(MKT·SMB·HML·WML) 월별 구축 (강건화판)
================================================================================
KOSPI(+옵션) FF 2×3(value-weighted), point-in-time. ols_attribution 입력용.

[강건화 v2] — 손상 가격/극단 수익으로 팩터가 부풀려지는 문제 방지:
  · 상장주식수 = 시총 / (최근 6개월 가격 중앙값)   ← 단일 틱 오류 방지
  · 종목 월수익 winsorize [-0.5, +1.0], |수익|>1.5 는 제외
  · 단일종목 시총가중 상한 10%(leg 내) 후 재정규화
  · 종목당 최소 24개월 데이터 요구
  · 가격 패널 캐싱(kospi_monthly_prices.csv) → 재실행 즉시
  · 마지막에 팩터 분포(describe) + 극단수익 건수 출력(진단)

장부가(HML): fetch_dart_book_equity.py → book_equity.csv. PIT 매칭(공시 시차).
사용:
  python build_korea_factors.py --market KOSPI --top-n 500 --book-csv book_equity.csv --rf-annual 3.5
  python build_korea_factors.py --synthetic
"""
import argparse, sys, os
import numpy as np, pandas as pd

CACHE = "kospi_monthly_prices.csv"


def load_universe(market="KOSPI", top_n=None):
    import FinanceDataReader as fdr
    parts = []
    for mk in [m.strip() for m in str(market).split(',') if m.strip()]:
        try: parts.append(fdr.StockListing(mk))
        except Exception as e: print(f'  ({mk} 실패: {e})')
    lst = pd.concat(parts, ignore_index=True) if len(parts) > 1 else parts[0]
    code_col = next(c for c in lst.columns if c.lower() in ("code", "symbol"))
    mcap_col = next((c for c in lst.columns if c.lower() in ("marcap", "marketcap")), None)
    lst = lst.rename(columns={code_col: "code"})
    if mcap_col: lst = lst.rename(columns={mcap_col: "mcap"})
    lst = lst.dropna(subset=["code"]); lst["code"] = lst["code"].astype(str).str.zfill(6)
    if "mcap" in lst and top_n: lst = lst.sort_values("mcap", ascending=False).head(top_n)
    return lst[["code"] + (["mcap"] if "mcap" in lst else [])].reset_index(drop=True)


def fetch_monthly_prices(codes, years=5, use_cache=True):
    if use_cache and os.path.exists(CACHE):
        px = pd.read_csv(CACHE, index_col=0, parse_dates=True)
        px.columns = [str(c).zfill(6) for c in px.columns]
        print(f"가격 캐시 로드: {CACHE} ({px.shape[1]}종목 × {px.shape[0]}개월)")
        return px
    import FinanceDataReader as fdr
    from datetime import datetime, timedelta
    end = datetime.now(); start = end - timedelta(days=int(365 * (years + 1.5)))
    out = {}
    for i, c in enumerate(codes):
        try:
            s = fdr.DataReader(str(c), start.strftime("%Y-%m-%d"), end.strftime("%Y-%m-%d"))["Close"]
            if len(s) > 200: out[str(c).zfill(6)] = s
        except Exception:
            pass
        if (i + 1) % 100 == 0: print(f"  ...{i+1}/{len(codes)} 수집")
    px = pd.DataFrame(out).resample("ME").last()
    px.to_csv(CACHE); print(f"가격 캐시 저장: {CACHE}")
    return px


def robust_shares(prices_m, mcap):
    """시총/최근6개월 가격중앙값 → 단일 틱 오류 방지. 반환 Series(code->shares)."""
    last_robust = prices_m.ffill().tail(6).median()
    sh = (mcap.reindex(prices_m.columns) / last_robust).replace([np.inf, -np.inf], np.nan)
    return sh


def _book_map(book_df):
    m = {}
    for _, r in book_df.iterrows():
        try: m.setdefault(str(r["code"]).zfill(6), {})[int(r["fiscal_year"])] = float(r["book_equity"])
        except (ValueError, TypeError): pass
    return m

def _book_at(bmap, code, dt):
    d = bmap.get(str(code).zfill(6))
    if not d: return None
    fy0 = dt.year - 1 if dt.month >= 5 else dt.year - 2
    for fy in (fy0, fy0 - 1, fy0 - 2):
        if fy in d: return d[fy]
    return None


def _vw(fwd, me, idx, wcap=0.10):
    idx = [i for i in idx if i in fwd.index and i in me.index]
    w = me.reindex(idx).astype(float); r = fwd.reindex(idx).astype(float)
    ok = w.notna() & r.notna() & (w > 0)
    if ok.sum() == 0: return np.nan
    w, r = w[ok], r[ok]; w = w / w.sum()
    w = np.minimum(w, wcap)                      # 단일종목 지배 방지
    if w.sum() == 0: return np.nan
    w = w / w.sum()
    return float((w * r).sum())


def build_factors(prices_m, shares, book_df=None, rf_annual=3.5,
                  ret_clip=(-0.5, 1.0), max_ret=1.5, min_months=24, wcap=0.10):
    valid_cols = prices_m.columns[prices_m.notna().sum() >= min_months]
    prices_m = prices_m[valid_cols]
    months = list(prices_m.index)
    mcap_m = prices_m.mul(shares.reindex(prices_m.columns), axis=1)
    rf_m = (1 + rf_annual / 100.0) ** (1 / 12) - 1
    bmap = _book_map(book_df) if book_df is not None else None
    rows, n_clip = [], 0
    for ti in range(12, len(months) - 1):
        t, tn = months[ti], months[ti + 1]
        me = mcap_m.loc[t].dropna()
        fwd = (prices_m.loc[tn] / prices_m.loc[t] - 1).reindex(me.index)
        valid = me.index[(me > 0) & fwd.notna() & (fwd.abs() <= max_ret)]
        me = me[valid]; fwd = fwd[valid]
        n_clip += int((fwd < ret_clip[0]).sum() + (fwd > ret_clip[1]).sum())
        fwd = fwd.clip(*ret_clip)                # winsorize
        if len(me) < 10: continue
        smed = me.median(); small, big = me.index[me <= smed], me.index[me > smed]
        mom = (prices_m.loc[months[ti - 1]] / prices_m.loc[months[ti - 12]] - 1).reindex(me.index)
        ml, mh = mom.quantile(0.3), mom.quantile(0.7)
        win, los = me.index[mom >= mh], me.index[mom <= ml]
        rec = {"date": tn.strftime("%Y-%m-%d")}
        rec["MKT"] = _vw(fwd, me, list(me.index), wcap) - rf_m
        rec["SMB"] = _vw(fwd, me, list(small), wcap) - _vw(fwd, me, list(big), wcap)
        rec["WML"] = (0.5*(_vw(fwd,me,[i for i in win if i in small],wcap)+_vw(fwd,me,[i for i in win if i in big],wcap))
                      - 0.5*(_vw(fwd,me,[i for i in los if i in small],wcap)+_vw(fwd,me,[i for i in los if i in big],wcap)))
        rec["HML"] = np.nan
        if bmap is not None:
            be = pd.Series({c: _book_at(bmap, c, t) for c in me.index}, dtype=float)
            bm = (be / me).dropna(); bm = bm[np.isfinite(bm) & (bm > 0)]
            if len(bm) >= 10:
                bl, bh = bm.quantile(0.3), bm.quantile(0.7)
                high, low = bm.index[bm >= bh], bm.index[bm <= bl]
                rec["HML"] = (0.5*(_vw(fwd,me,[i for i in high if i in small],wcap)+_vw(fwd,me,[i for i in high if i in big],wcap))
                              - 0.5*(_vw(fwd,me,[i for i in low if i in small],wcap)+_vw(fwd,me,[i for i in low if i in big],wcap)))
        rec["RF"] = rf_m
        rows.append(rec)
    f = pd.DataFrame(rows).set_index("date")[["MKT", "SMB", "HML", "WML", "RF"]]
    return f, n_clip


def _report(f, n_clip):
    print(f"\n극단 월수익 winsorize 건수: {n_clip}")
    print("팩터 분포 (월, 정상이면 |평균|·표준편차 대략 ≤0.10):")
    print(pd.DataFrame({"월평균": f.mean(), "월std": f.std(), "월min": f.min(), "월max": f.max()}).round(4).to_string())
    bad = [c for c in ["MKT","SMB","HML","WML"] if f[c].abs().max() > 0.4]
    if bad: print(f"⚠️ 여전히 과대(|월|>40%) 팩터: {bad} — 데이터 추가 점검 필요")
    else:   print("✅ 팩터 스케일 정상 범위")


def _synthetic():
    rng = np.random.default_rng(0); K, Tm = 120, 66
    idx = pd.date_range("2021-01-31", periods=Tm, freq="ME"); codes = [f"{i:06d}" for i in range(K)]
    drift = rng.normal(0.01, 0.004, K); px = pd.DataFrame(index=idx, columns=codes, dtype=float)
    p = 1000 * (1 + rng.uniform(-0.3, 2.0, K))
    for t in range(Tm): p = p * (1 + rng.normal(drift, 0.08)); px.iloc[t] = p
    mcap = pd.Series(px.iloc[-1].values * rng.integers(1_000_000, 50_000_000, K), index=codes).astype(float)
    px.iloc[-1, 0] = 1.0   # 손상: 0번 종목 마지막가 1원 → 순진하게 shares 계산 시 ME 폭증
    sh = robust_shares(px, mcap)
    brows = [{"code": c, "fiscal_year": fy, "book_equity": float(px.iloc[0][c]*sh[c]*rng.uniform(0.2,1.5))}
             for fy in (2020,2021,2022,2023,2024) for c in codes]
    f, nc = build_factors(px, sh, pd.DataFrame(brows), 3.5)
    _report(f, nc)
    assert f[["MKT","SMB","WML"]].abs().max().max() < 0.4, "강건화 실패(팩터 과대)"
    print("\n[OK] build_korea_factors 강건화 검증 통과 (손상 종목 있어도 팩터 정상 범위)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=5); ap.add_argument("--market", default="KOSPI")
    ap.add_argument("--top-n", type=int, default=500); ap.add_argument("--book-csv", default=None)
    ap.add_argument("--rf-annual", type=float, default=3.5); ap.add_argument("--out", default="korea_factors_monthly.csv")
    ap.add_argument("--no-cache", action="store_true"); ap.add_argument("--synthetic", action="store_true")
    ap.add_argument("--cache", default=CACHE, help="가격 캐시 파일명 (KOSDAQ 트랙은 kosdaq_monthly_prices.csv 등으로 분리)")
    a = ap.parse_args()
    globals()["CACHE"] = a.cache
    if a.synthetic: return _synthetic()
    uni = load_universe(a.market, a.top_n); codes = uni["code"].tolist()
    print(f"유니버스: {a.market} 상위 {a.top_n} ({len(codes)}종목)")
    px = fetch_monthly_prices(codes, a.years, use_cache=not a.no_cache)
    mcap = uni.set_index("code")["mcap"] if "mcap" in uni else pd.Series(1.0, index=px.columns)
    sh = robust_shares(px, mcap)
    book_df = None
    if a.book_csv: book_df = pd.read_csv(a.book_csv, dtype={"code": str}); print(f"장부가: {book_df['code'].nunique()}종목 (PIT HML)")
    else: print("⚠️ --book-csv 없음 → HML 생략")
    f, nc = build_factors(px, sh, book_df, a.rf_annual)
    f.to_csv(a.out); print(f"\n✅ 저장: {a.out} ({f.shape[0]}개월)")
    _report(f, nc)
    print("\n다음: python run_attribution.py")


if __name__ == "__main__":
    sys.exit(main() if "--synthetic" in sys.argv else (main() or 0))
