#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_theme_daily.py — 테마 워치리스트 일봉 OHLC 수집 (PC 실행) · 2026-06-07

[PC 실행]  샌드박스는 KRX/Yahoo 네트워크 차단이라 여기선 못 받음 → 진우 PC에서 실행.
   (requirements.txt의 finance-datareader 사용 — 기존 fetch_* 와 동일 스택)

역할: validate_atr_stop.py 가 먹는 일봉 long CSV + 진입신호 CSV 생성. 이걸로 ATR(k) 손절을
   '실데이터'로 검증해 미검증 이론(테마 손절폭)을 종결한다.

출력:
  theme_daily.csv   : code,date,open,high,low,close   (validate_atr_stop --daily)
  theme_entries.csv : code,entry_date,horizon_days     (validate_atr_stop --signals)
                      매월 첫 거래일 진입 + horizon(기본 60거래일) 보유 가정.

사용(PC):
  pip install finance-datareader pandas
  python fetch_theme_daily.py                       # 최근 5년
  python fetch_theme_daily.py --start 2020-01-01 --end 2026-06-06 --horizon 60
  # 이어서:
  python validate_atr_stop.py --daily theme_daily.csv --signals theme_entries.csv
  python validate_atr_stop.py --daily theme_daily.csv --signals theme_entries.csv --trailing
"""
import argparse, csv, datetime as dt, sys

WATCH = [
    ("247540", "에코프로비엠"), ("086520", "에코프로"), ("277810", "레인보우로보틱스"),
    ("108490", "로보티즈"), ("087010", "펩트론"), ("028300", "HLB"),
    ("196170", "알테오젠"), ("036930", "주성엔지니어링"), ("080220", "제주반도체"),
    ("043260", "성호전자"), ("083650", "비에이치아이"), ("257720", "실리콘투"),
]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=None, help="기본: 5년 전")
    ap.add_argument("--end", default=None, help="기본: 오늘")
    ap.add_argument("--horizon", type=int, default=60, help="진입 후 보유 거래일")
    ap.add_argument("--daily_out", default="theme_daily.csv")
    ap.add_argument("--entries_out", default="theme_entries.csv")
    a = ap.parse_args()
    try:
        import FinanceDataReader as fdr
    except ImportError:
        sys.exit("finance-datareader 미설치 → pip install finance-datareader")

    end = a.end or dt.date.today().isoformat()
    start = a.start or (dt.date.today() - dt.timedelta(days=365 * 5)).isoformat()
    print("수집 기간 %s ~ %s | 종목 %d" % (start, end, len(WATCH)))

    drows, erows = [], []
    for code, name in WATCH:
        try:
            df = fdr.DataReader(code, start, end)
        except Exception as e:
            print("  [실패] %s %s: %r" % (code, name, e)); continue
        if df is None or len(df) == 0:
            print("  [빈데이터] %s %s" % (code, name)); continue
        df = df.dropna(subset=["Open", "High", "Low", "Close"])
        last_month = None
        for idx, r in df.iterrows():
            d = idx.date().isoformat()
            drows.append([code, d, r["Open"], r["High"], r["Low"], r["Close"]])
            ym = d[:7]
            if ym != last_month:                       # 매월 첫 거래일 = 진입신호
                erows.append([code, d, a.horizon]); last_month = ym
        print("  [OK] %s %s: %d행" % (code, name, len(df)))

    with open(a.daily_out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh); w.writerow(["code", "date", "open", "high", "low", "close"])
        w.writerows(drows)
    with open(a.entries_out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh); w.writerow(["code", "entry_date", "horizon_days"])
        w.writerows(erows)
    print("\n저장: %s (%d행), %s (%d신호)" % (a.daily_out, len(drows), a.entries_out, len(erows)))
    print("다음: python validate_atr_stop.py --daily %s --signals %s [--trailing]"
          % (a.daily_out, a.entries_out))


if __name__ == "__main__":
    main()
