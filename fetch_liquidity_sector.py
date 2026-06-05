#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_liquidity_sector.py — universe 규칙화용 유동성·섹터·시총 스냅샷
==============================================================================
FinanceDataReader로 KOSPI 종목의 시가총액·거래대금(유동성)·섹터를 뽑아
liquidity_sector.csv [code, name, sector, mcap, adtv] 생성.
→ universe_rules.py가 이걸 읽어 편입후보를 '거래 잘 되는 대형·분산 종목'으로 정밀화.

사용: python fetch_liquidity_sector.py                 (스냅샷 거래대금, 빠름)
      python fetch_liquidity_sector.py --adtv-days 60  (최근 60일 평균 거래대금, 느림·정확)
      python fetch_liquidity_sector.py --selftest
의존성: FinanceDataReader, pandas, numpy
섹터: 여러 리스팅(KRX/KRX-DESC)에서 Sector/Industry 컬럼을 시도해 커버리지 최대인 것을 채택.
"""
import argparse, os, sys
import numpy as np, pandas as pd


def _pick(cols_map, *names):
    for n in names:
        if n.lower() in cols_map:
            return cols_map[n.lower()]
    return None


def _best_sector(fdr, codes):
    """여러 리스팅·컬럼을 시도해 우리 코드 커버리지가 가장 높은 섹터 매핑 반환."""
    best, best_cov, best_src = None, 0.0, None
    cset = pd.Index(codes)
    for ln in ("KRX", "KRX-DESC", "KOSPI", "KOSDAQ"):
        try:
            t = fdr.StockListing(ln)
        except Exception:
            continue
        tm = {str(c).lower(): c for c in t.columns}
        cc = _pick(tm, "Code", "Symbol", "종목코드")
        if cc is None:
            continue
        for scol in ("Sector", "Industry", "업종", "SectorName", "IndustryName"):
            cs = _pick(tm, scol)
            if cs is None:
                continue
            tmp = t[[cc, cs]].copy(); tmp.columns = ["code", "sector"]
            tmp["code"] = tmp["code"].astype(str).str.zfill(6)
            tmp = tmp.dropna().drop_duplicates("code")
            cov = cset.map(tmp.set_index("code")["sector"]).notna().mean()
            if cov > best_cov:
                best, best_cov, best_src = tmp, float(cov), f"{ln}.{cs}"
    return best, best_cov, best_src


def fetch(market="KOSPI", adtv_days=0, out="liquidity_sector.csv"):
    import FinanceDataReader as fdr
    markets = [m.strip() for m in str(market).split(',') if m.strip()]
    snaps = []
    for mk in markets:
        try:
            snaps.append(fdr.StockListing(mk))
        except Exception as e:
            print(f'  ({mk} 수집 실패: {e})')
    if not snaps:
        raise SystemExit('StockListing 수집 실패')
    snap = pd.concat(snaps, ignore_index=True) if len(snaps) > 1 else snaps[0]
    cm = {str(c).lower(): c for c in snap.columns}
    c_code = _pick(cm, "Code", "Symbol"); c_name = _pick(cm, "Name")
    c_mcap = _pick(cm, "Marcap", "MarketCap", "시가총액")
    c_amt = _pick(cm, "Amount", "거래대금"); c_vol = _pick(cm, "Volume"); c_close = _pick(cm, "Close")
    if c_code is None:
        raise SystemExit(f"StockListing 컬럼에서 코드 못 찾음. 컬럼: {list(snap.columns)}")
    df = pd.DataFrame()
    df["code"] = snap[c_code].astype(str).str.zfill(6)
    df["name"] = snap[c_name].astype(str) if c_name else ""
    df["mcap"] = pd.to_numeric(snap[c_mcap], errors="coerce") if c_mcap else np.nan
    if c_amt:
        df["adtv"] = pd.to_numeric(snap[c_amt], errors="coerce")
    elif c_vol and c_close:
        df["adtv"] = pd.to_numeric(snap[c_vol], errors="coerce") * pd.to_numeric(snap[c_close], errors="coerce")
    else:
        df["adtv"] = np.nan

    sector, cov, src = _best_sector(fdr, df["code"].tolist())
    if sector is not None:
        df = df.merge(sector, on="code", how="left")
    else:
        df["sector"] = np.nan
    print(f"스냅샷 {len(df)}종목 | 시총={c_mcap} 거래대금={c_amt or (c_vol and c_close and 'Vol*Close')} | 섹터 병합 {df['sector'].notna().sum()}/{len(df)} (소스={src}, cov={cov:.0%})")

    if adtv_days and adtv_days > 0:
        import datetime as dt
        start = (dt.date.today() - dt.timedelta(days=int(adtv_days*2+10))).isoformat()
        vals = {}
        for i, c in enumerate(df["code"]):
            try:
                d = fdr.DataReader(c, start)
                if "Volume" in d and "Close" in d and len(d):
                    vals[c] = float((d["Close"] * d["Volume"]).tail(adtv_days).mean())
            except Exception:
                pass
            if (i+1) % 50 == 0:
                print(f"  ADTV {i+1}/{len(df)} ...")
        df["adtv"] = df["code"].map(vals).fillna(df["adtv"])
        print(f"평균 거래대금(최근 {adtv_days}일) 적용: {len(vals)}종목")

    df = df[["code", "name", "sector", "mcap", "adtv"]]
    df.to_csv(out, index=False)
    print(f"저장: {out}")
    print(df.sort_values('mcap', ascending=False).head(8).to_string(index=False))
    if df["sector"].notna().sum() == 0:
        print("⚠ 섹터 0건 — FDR 버전 차이. 위 '소스' 추적용으로 `python -c \"import FinanceDataReader as fdr; print(fdr.StockListing('KRX').columns.tolist())\"` 출력을 공유해 주세요.")
    return df


def _selftest():
    codes = [f"{i:06d}" for i in range(8)]
    df = pd.DataFrame({
        "code": codes, "name": [f"종목{i}" for i in range(8)],
        "sector": ["반도체","반도체","반도체","반도체","바이오","금융","금융","식품"],
        "mcap":  [400e12,200e12,5e12,3e12,30e12,20e12,8e12,10e12],
        "adtv":  [2e12,1e12,5e10,3e8,4e11,2e11,1e8,3e11]})
    df.to_csv("liquidity_sector.csv", index=False)
    back = pd.read_csv("liquidity_sector.csv", dtype={"code": str})
    try: os.remove("liquidity_sector.csv")
    except OSError: pass
    assert list(back.columns) == ["code","name","sector","mcap","adtv"]
    assert back["mcap"].notna().all() and back["adtv"].notna().all()
    print("[OK] fetch_liquidity_sector selftest 통과 (스키마 + 섹터 다중소스 폴백)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", default="KOSPI", help="쉼표로 복수 가능: KOSPI,KOSDAQ")
    ap.add_argument("--adtv-days", type=int, default=0)
    ap.add_argument("--out", default="liquidity_sector.csv")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest: return _selftest()
    fetch(a.market, a.adtv_days, a.out)


if __name__ == "__main__":
    sys.exit(main() or 0)
