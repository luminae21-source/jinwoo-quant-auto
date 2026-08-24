#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
주봉_원자료조회.py — 도지 판정 근거(주봉 OHLC 원자료) 확인용 [조회 전용]
==============================================================================
목적: 삼성전자·SK하이닉스의 최근 6주 주봉 OHLC를 그대로 출력.
      몸통=|종가−시가| · 전체범위=고가−저가 · 몸통/범위% → 도지 기준(≤10%)과 숫자로 비교.
      + 진행 중(미완결) 이번 주 봉도 별도 표기(시/고/저/현재가).
⚠️ 조회 전용 — 주봉분석.py 무수정. 실데이터(pykrx)만, 추정 금지.
사용: python 주봉_원자료조회.py
"""
import sys
from datetime import date, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

TARGETS = [("삼성전자", "005930"), ("SK하이닉스", "000660")]
DOJI_TH = 10.0   # 몸통/범위 ≤10% = 도지


def get_daily(code, days=140):
    from pykrx import stock
    end = date.today().strftime("%Y%m%d")
    start = (date.today() - timedelta(days=days)).strftime("%Y%m%d")
    df = stock.get_market_ohlcv(start, end, code)
    df = df.rename(columns={"시가": "O", "고가": "H", "저가": "L", "종가": "C"})
    return df[["O", "H", "L", "C"]].dropna()


def weekly(df):
    w = df.resample("W-FRI").agg(O=("O", "first"), H=("H", "max"), L=("L", "min"), C=("C", "last")).dropna()
    return w


def row(dt, o, h, l, c, ongoing=False):
    body = abs(c - o); rng = h - l
    pct = (body / rng * 100) if rng > 0 else 0.0
    kind = "양봉" if c > o else ("음봉" if c < o else "보합")
    doji = "✅도지" if (rng > 0 and pct <= DOJI_TH) else "❌아님"
    tag = " (진행중)" if ongoing else ""
    return (f"| {dt}{tag} | {o:,.0f} | {h:,.0f} | {l:,.0f} | {c:,.0f} | {kind} | "
            f"{body:,.0f} | {rng:,.0f} | **{pct:.1f}%** | {doji} |")


def main():
    print(f"# 주봉 OHLC 원자료 (도지 판정 근거) — {date.today()}")
    print(f"> 도지 기준: 몸통/전체범위 ≤ {DOJI_TH:.0f}%  ·  몸통=|종가−시가| · 범위=고−저  ·  실데이터(pykrx)\n")
    for name, code in TARGETS:
        try:
            d = get_daily(code)
        except Exception as e:
            print(f"## {name}({code})\n- ❌ 데이터부족: {str(e)[:80]}\n"); continue
        w = weekly(d)
        dlast = d.index[-1]
        complete_last = (dlast.weekday() == 4)          # 금요일이면 마지막 주 완결
        wc = w if complete_last else w.iloc[:-1]        # 완결주만
        print(f"## {name}({code})")
        print(f"- 일봉 마지막: {dlast.date()} ({'금요일=주 완결' if complete_last else '주중 → 이번 주 진행중'})")
        print("\n| 주(종료일) | 시가 | 고가 | 저가 | 종가 | 음/양 | 몸통 | 전체범위 | 몸통/범위 % | 도지? |")
        print("|---|---|---|---|---|---|---|---|---|---|")
        for dt, r in wc.tail(6).iterrows():
            print(row(dt.date(), r["O"], r["H"], r["L"], r["C"]))
        # 진행 중 주(미완결)
        if not complete_last and len(w) > 0:
            cur = w.iloc[-1]
            print(row(w.index[-1].date(), cur["O"], cur["H"], cur["L"], cur["C"], ongoing=True))
        # 직전 완결 주 강조
        last = wc.iloc[-1]
        body = abs(last["C"] - last["O"]); rng = last["H"] - last["L"]
        pct = (body / rng * 100) if rng > 0 else 0
        print(f"\n**→ 직전 완결 주({wc.index[-1].date()}): 몸통 {body:,.0f} / 범위 {rng:,.0f} = **{pct:.1f}%** "
              f"→ 도지 기준 {DOJI_TH:.0f}% {'이하 → 도지 ✅' if pct <= DOJI_TH else '초과 → 도지 아님 ❌'}**\n")


if __name__ == "__main__":
    main()
