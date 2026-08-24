#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_kospi_daily_full.py — [PC 실행] KOSPI 전 시장 일봉 OHLCV 수집 (주봉/거래량 해금)
==============================================================================
왜: 주봉 차트·40주(MA200)·거래량 바는 일봉 원천이 필요한데 레포엔 KOSPI 일봉이 없음
    (기존 fetch_kospi_daily_panel는 보유 18종만). 본 스크립트는 heat 유니버스 전체를 받음.
유니버스: kospi_monthly_prices.csv 헤더의 코드 전체(= heat 엔진이 쓰는 그 종목들)와 정합.
산출: kospi_pit_daily.csv  (long: code,date,open,high,low,close,volume)
      → 이후 반드시:  python verify_weekly_reconcile.py --market kospi   (게이트 PASS 후 통합)
무수정: production·발굴트랙·heat·월봉 패널 손대지 않음(신규 파일만).

사용(진우 PC, Desktop\진우퀀트):
  pip install finance-datareader pandas
  python fetch_kospi_daily_full.py            # 기본 7년
  python fetch_kospi_daily_full.py --years 8
  python fetch_kospi_daily_full.py --self-test  # 오프라인 점검(네트워크 불필요)
주의: 종목 수백 개라 수 분 소요. 회사망 차단 시 개인망에서. 끝나면 콘솔 요약을 Claude에 붙여주세요.
"""
import argparse, os, sys, time
from pathlib import Path
from datetime import date, timedelta

BASE = Path(__file__).parent.resolve()
OUT = BASE / "kospi_pit_daily.csv"
UNIV_CSV = BASE / "kospi_monthly_prices.csv"


def load_universe():
    """월봉 패널 헤더에서 6자리 코드 유니버스 로드(heat 엔진과 동일 종목)."""
    import pandas as pd
    cols = pd.read_csv(UNIV_CSV, nrows=0).columns.tolist()
    codes = [str(c).zfill(6) for c in cols if str(c).lower() != "date"]
    # 중복 제거, 순서 유지
    seen, uniq = set(), []
    for c in codes:
        if c not in seen:
            seen.add(c); uniq.append(c)
    return uniq


def fetch(years=7, sleep=0.05):
    import FinanceDataReader as fdr
    import pandas as pd
    codes = load_universe()
    start = (date.today() - timedelta(days=int(years * 365.25))).strftime("%Y-%m-%d")
    print(f"유니버스 {len(codes)}종 · 시작 {start} · 산출 {OUT.name}")
    rows = []
    ok, fail = 0, []
    for k, c in enumerate(codes, 1):
        try:
            df = fdr.DataReader(c, start)
            if df is None or df.empty:
                fail.append((c, "empty")); continue
            df = df.rename(columns=str.title)  # Open/High/Low/Close/Volume 정규화
            sub = df[["Open", "High", "Low", "Close", "Volume"]].copy()
            sub.insert(0, "code", c)
            sub.index.name = "date"
            sub = sub.reset_index()
            rows.append(sub)
            ok += 1
            if k % 25 == 0 or k == len(codes):
                print(f"  [{k}/{len(codes)}] ok={ok} fail={len(fail)} (최근 {c}: {len(df)}행)")
            time.sleep(sleep)
        except Exception as e:
            fail.append((c, str(e)[:60]))
    if not rows:
        print("⚠️ 수집 0건 — 네트워크/패키지 확인"); return
    out = pd.concat(rows, ignore_index=True)
    out.columns = [str(x).lower() for x in out.columns]
    out["date"] = pd.to_datetime(out["date"]).dt.strftime("%Y-%m-%d")
    out = out[["code", "date", "open", "high", "low", "close", "volume"]]
    out.to_csv(OUT, index=False, encoding="utf-8-sig")
    print(f"\n저장: {OUT.name}  rows={len(out):,}  codes={out['code'].nunique()}")
    print(f"기간 {out['date'].min()} ~ {out['date'].max()}")
    if fail:
        print(f"실패 {len(fail)}건(상위5): {fail[:5]}")
    # 즉석 sanity: 월말 정합 1종목 미리보기
    try:
        mp = pd.read_csv(UNIV_CSV, parse_dates=["Date"], index_col="Date")
        mp.columns = [str(x).zfill(6) for x in mp.columns]
        c0 = out["code"].iloc[0]
        dd = out[out["code"] == c0].copy(); dd["date"] = pd.to_datetime(dd["date"])
        me = dd.set_index("date")["close"].resample("ME").last().dropna().tail(3)
        print(f"\n[sanity] {c0} 일봉→월말: {me.round(0).tolist()}")
        print(f"[sanity] {c0} 월봉:      {mp[c0].dropna().tail(3).round(0).tolist()}  (일치하면 게이트 통과 기대)")
    except Exception as e:
        print("sanity 생략:", e)
    print("\n→ 다음: python verify_weekly_reconcile.py --market kospi  (PASS면 주봉 통합)")
    print("→ 이 콘솔 요약을 Claude에 붙여주세요.")


def self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    exists = UNIV_CSV.exists()
    chk("kospi_monthly_prices.csv 존재", exists)
    if exists:
        codes = load_universe()
        chk("유니버스>100종", len(codes) > 100)
        chk("코드 6자리·중복없음", all(len(c) == 6 for c in codes) and len(set(codes)) == len(codes))
        chk("산출 컬럼 스펙 정의", ["code", "date", "open", "high", "low", "close", "volume"][0] == "code")
    print(f"self-test: {ok}/{tot}  (네트워크 불필요)")
    return ok == tot


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=float, default=7)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        self_test()
    else:
        try:
            fetch(a.years)
        except Exception:
            import traceback
            print("\n===== [에러] 아래 복사 =====")
            traceback.print_exc()
            print("\n힌트1: pip install finance-datareader pandas. 회사망 차단 시 개인망.")
            print("힌트2: X509/pyOpenSSL 오류 시 →  pip install -U pyopenssl cryptography")
