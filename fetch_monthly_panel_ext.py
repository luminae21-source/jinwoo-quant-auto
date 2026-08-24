#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_monthly_panel_ext.py — [PC 실행] 월간 가격 패널 **장기 확장**(생존편향 안전, pykrx)
==========================================================================================
목적: 섹터모멘텀 후보 #5 백테(jq_sector_mom_backtest_skeleton.py) 검정력↑.
      현 패널이 2019~(79개월)뿐 → 더 긴 이력 확보. **PIT 구성종목**(각 시점 상장종목)을
      받아 상장폐지 종목까지 포함 = 생존편향 회피.

무수정: production·L1·theme_heat·매도규칙서 손대지 않음. 입력 CSV만 교체(백업 후).

동작:
  1) start_year~오늘, 매월말 시점의 상장 티커를 pykrx로 조회(PIT) → 전 구간 합집합(폐지종목 포함).
  2) 각 티커의 월간 종가(pykrx 'm')를 받아 wide 패널로 병합.
  3) 기존 kospi_monthly_prices.csv / kosdaq_monthly_prices.csv 를 .bak_ext_YYYYMMDD 로 백업 후 덮어씀.
  4) theme_heat/스켈레톤이 그대로 읽음(파일명 동일). heat 캐시는 키 불일치로 자동 재빌드.

⚠️ 한계(정직): 섹터분류(liquidity_sector.csv)는 **정적 스냅샷** → 과거·폐지 종목은 섹터 라벨이
   없어 theme_heat에서 미분류(기타/드롭)될 수 있음. 즉 가격은 길어져도 **섹터 신호 품질은
   과거구간서 열화**. 완전한 장기 PIT엔 PIT 섹터맵이 추가로 필요(9월 스코프).

사용(진우 PC, Desktop\진우퀀트):
  pip install pykrx pandas
  python fetch_monthly_panel_ext.py --self-test          # 오프라인 로직 점검(KRX 미접속)
  python fetch_monthly_panel_ext.py --start 2010          # 2010~ 확장(권장 시작점)
  python fetch_monthly_panel_ext.py --start 2005 --market KOSPI
실행 후:
  python build_korea_factors.py --years 16 --market KOSPI  # 팩터도 같이 확장(WML 통제군)
  python jq_sector_mom_backtest_skeleton.py --judge        # 캐시 자동 재빌드 후 재판정
"""
import sys, os, time, argparse
from datetime import date
import pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = {"KOSPI": "kospi_monthly_prices.csv", "KOSDAQ": "kosdaq_monthly_prices.csv"}


def month_ends(start_year):
    """start_year-01 ~ 이번달까지 월말(영업일 근사) 리스트(YYYYMMDD)."""
    idx = pd.date_range(f"{start_year}-01-31", pd.Timestamp.today(), freq="ME")
    return [d.strftime("%Y%m%d") for d in idx]


def pit_tickers(mkt, mes, every=3):
    """매 every개월마다 시점 상장 티커를 조회 → 합집합(PIT·폐지종목 포함)."""
    from pykrx import stock
    seen = set()
    for i, d in enumerate(mes):
        if i % every and i != len(mes) - 1:
            continue
        try:
            seen |= set(stock.get_market_ticker_list(d, market=mkt))
        except Exception as e:
            print(f"  [ticker skip] {d}: {e}")
        time.sleep(0.15)
    return sorted(seen)


def fetch_market(mkt, start_year):
    from pykrx import stock
    mes = month_ends(start_year)
    frm, to = mes[0], mes[-1]
    print(f"[{mkt}] {frm}~{to}  월말 {len(mes)}개")
    tks = pit_tickers(mkt, mes)
    print(f"[{mkt}] PIT 합집합 티커 {len(tks)}종(폐지 포함). 월간 종가 수집…")
    cols = {}
    for j, tk in enumerate(tks):
        try:
            df = stock.get_market_ohlcv(frm, to, tk, "m")
            if df is not None and len(df) and "종가" in df.columns:
                s = df["종가"].copy(); s.index = pd.to_datetime(s.index)
                cols[tk] = s[s > 0]
        except Exception as e:
            if j < 5: print(f"  [ohlcv skip] {tk}: {e}")
        if j % 100 == 0: print(f"   … {j}/{len(tks)}")
        time.sleep(0.12)
    panel = pd.DataFrame(cols)
    panel.index = pd.to_datetime(panel.index)
    panel = panel.resample("ME").last().sort_index()
    panel.index.name = "Date"
    return panel


def save(mkt, panel):
    path = os.path.join(BASE, OUT[mkt])
    if os.path.exists(path):
        bak = path + ".bak_ext_" + date.today().strftime("%Y%m%d")
        os.replace(path, bak); print(f"[{mkt}] 기존 파일 백업 → {os.path.basename(bak)}")
    panel.to_csv(path, encoding="utf-8-sig")
    rng = f"{panel.index.min().date()}~{panel.index.max().date()}" if len(panel) else "-"
    print(f"[{mkt}] 저장 {OUT[mkt]}  {panel.shape[0]}개월 × {panel.shape[1]}종목  ({rng})")


def self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    mes = month_ends(2010)
    chk("월말 생성 2010~", len(mes) > 150 and mes[0].startswith("2010"))
    chk("월말 형식 YYYYMMDD", all(len(m) == 8 and m.isdigit() for m in mes))
    # 합성 패널 resample 로직
    import numpy as np
    dpanel = pd.DataFrame({"005930": np.arange(1, 60)}, index=pd.date_range("2020-01-01", periods=59, freq="D"))
    r = dpanel.resample("ME").last()
    chk("resample 월말 동작", len(r) >= 1)
    chk("출력 파일명 정합", OUT["KOSPI"].endswith("kospi_monthly_prices.csv"))
    print(f"self-test: {ok}/{tot}  (KRX 미접속·로직만)")
    return ok == tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--start", type=int, default=2010, help="확장 시작연도(기본 2010)")
    ap.add_argument("--market", default="both", choices=["both", "KOSPI", "KOSDAQ"])
    a = ap.parse_args()
    if a.self_test:
        self_test(); return
    mkts = ["KOSPI", "KOSDAQ"] if a.market == "both" else [a.market]
    try:
        for mkt in mkts:
            save(mkt, fetch_market(mkt, a.start))
        print("\n완료. 다음: build_korea_factors.py --years N 로 팩터 확장 → --judge 재판정.")
        print("주의(정직): 섹터분류 정적 → 과거·폐지 종목 섹터 라벨 결측 가능(섹터 신호 열화).")
    except Exception:
        import traceback; print("\n===== [에러] 아래를 복사해 주세요 ====="); traceback.print_exc()
        print("\n힌트: pip install pykrx pandas. 회사망 차단 시 개인망에서.")


if __name__ == "__main__":
    main()
