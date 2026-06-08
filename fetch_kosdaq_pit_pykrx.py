#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_kosdaq_pit_pykrx.py — pykrx 기반 생존편향-통제 KOSDAQ 표본 (상폐 포함, PC 실행) · 2026-06-07

[PC 실행]  샌드박스 네트워크 차단 → 진우 PC에서. (pip install pykrx pandas)

왜 pykrx인가: FDR의 'KRX-DELISTING'은 우선주·8자리 코드가 섞여 상폐주 다수가 'invalid'로 누락됐다
   (직전 fetch에서 320→상폐 27만 성공). pykrx는 **과거 특정일의 KOSDAQ 종목 리스트**를 그대로 주므로,
   '그 시점에 존재했던' 종목(=이후 상폐된 것 포함)을 깨끗이 얻어 생존편향을 더 두껍게 통제한다.

방식:
   1) 시작일(과거) KOSDAQ 종목 = stock.get_market_ticker_list(start, "KOSDAQ")  ← PIT 유니버스(상폐 포함)
   2) 랜덤 N 표본(시드 고정). 현재 미상장(=상폐)도 자연히 포함됨.
   3) 각 종목 일봉 = stock.get_market_ohlcv(start, end, ticker). 상폐주는 상폐시점까지만 반환.
   4) 동전주·저유동 진입 제외 후 월별 PIT 진입신호 생성.
   5) validate_atr_stop.py 입력 형식으로 저장.

출력: kosdaq_pit_daily_pykrx.csv · kosdaq_pit_entries_pykrx.csv

사용(PC):
   pip install pykrx pandas
   python fetch_kosdaq_pit_pykrx.py --n 350 --start 2019-01-02
   python validate_atr_stop.py --daily kosdaq_pit_daily_pykrx.csv --signals kosdaq_pit_entries_pykrx.csv
"""
import argparse, csv, datetime as dt, random, sys, time


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=350, help="표본 종목수(시작일 KOSDAQ에서 랜덤)")
    ap.add_argument("--start", default="2019-01-02")
    ap.add_argument("--end", default=None)
    ap.add_argument("--horizon", type=int, default=60)
    ap.add_argument("--min_price", type=float, default=1000)
    ap.add_argument("--min_adtv", type=float, default=1e8)
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--sleep", type=float, default=0.0, help="요청 간 지연(초), 차단 시 0.2~0.5")
    ap.add_argument("--daily_out", default="kosdaq_pit_daily_pykrx.csv")
    ap.add_argument("--entries_out", default="kosdaq_pit_entries_pykrx.csv")
    a = ap.parse_args()
    try:
        from pykrx import stock
    except ImportError:
        sys.exit("pykrx 미설치 → pip install pykrx")

    end = (a.end or dt.date.today().isoformat()).replace("-", "")
    start = a.start.replace("-", "")
    # 1) 시작일 KOSDAQ 유니버스(상폐 포함)
    try:
        tickers = stock.get_market_ticker_list(start, market="KOSDAQ")
    except Exception as e:
        sys.exit("종목 리스트 실패: %r (start 날짜가 영업일인지 확인)" % e)
    rng = random.Random(a.seed); rng.shuffle(tickers)
    tickers = tickers[:a.n]
    print("시작일 %s KOSDAQ 유니버스에서 랜덤 %d종목 (시드 %d)" % (a.start, len(tickers), a.seed))

    drows, erows = [], []
    ok = 0
    KO = {"시가": "Open", "고가": "High", "저가": "Low", "종가": "Close", "거래량": "Volume"}
    for i, tk in enumerate(tickers):
        try:
            df = stock.get_market_ohlcv(start, end, tk)
        except Exception:
            continue
        if df is None or len(df) < 30:
            continue
        df = df.rename(columns=KO)
        if not {"Open", "High", "Low", "Close"} <= set(df.columns):
            continue
        adtv20 = []; last_month = None; rows = []
        for idx, r in df.iterrows():
            try:
                o, h, l, c = float(r["Open"]), float(r["High"]), float(r["Low"]), float(r["Close"])
            except Exception:
                continue
            if min(o, h, l, c) <= 0:
                continue
            d = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]
            rows.append((tk, d, o, h, l, c))
            v = float(r["Volume"]) if "Volume" in df.columns else 0
            adtv20.append(c * v)
            if len(adtv20) > 20:
                adtv20.pop(0)
            ym = d[:7]
            if ym != last_month:
                adtv = sum(adtv20) / len(adtv20) if adtv20 else 0
                if c >= a.min_price and ("Volume" not in df.columns or adtv >= a.min_adtv):
                    erows.append((tk, d, a.horizon))
                last_month = ym
        if rows:
            drows.extend(rows); ok += 1
        if a.sleep:
            time.sleep(a.sleep)
        if (i + 1) % 50 == 0:
            print("  ...%d/%d (성공 %d, 일봉 %d행)" % (i + 1, len(tickers), ok, len(drows)))

    with open(a.daily_out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh); w.writerow(["code", "date", "open", "high", "low", "close"]); w.writerows(drows)
    with open(a.entries_out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh); w.writerow(["code", "entry_date", "horizon_days"]); w.writerows(erows)
    # 상폐 추정(데이터가 최근까지 안 온 종목) 카운트
    last_by = {}
    for c, d, *_ in drows:
        if d > last_by.get(c, ""):
            last_by[c] = d
    dead = sum(1 for c in last_by if last_by[c] < "2026-04-01")
    print("\n성공 %d종목 (상폐/중단 추정 %d) | 일봉 %d행 | PIT진입 %d신호"
          % (ok, dead, len(drows), len(erows)))
    print("저장: %s, %s" % (a.daily_out, a.entries_out))
    print("다음: python validate_atr_stop.py --daily %s --signals %s [--trailing]"
          % (a.daily_out, a.entries_out))


if __name__ == "__main__":
    main()
