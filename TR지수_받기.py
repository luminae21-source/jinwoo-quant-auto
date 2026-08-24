# -*- coding: utf-8 -*-
r"""
TR지수_받기.py — KRX 의 TR(총수익) 지수를 탐색하고 월봉으로 내려받는다. (#75 선행 조건)

⚠️ PC 전용 — 네트워크가 필요하다 (pykrx). Cowork 샌드박스에서는 못 돈다.

쓰는 법 (진우퀀트 폴더에서):
    py TR지수_받기.py              # ① TR 이름 붙은 지수 전부 나열 ② '코스피 TR' 자동 수령
    py TR지수_받기.py --code 1234  # 특정 코드 수령

내려받은 파일은 데이터수리\_지수_<이름>.csv (date,close) 로 저장되고,
운용사양_백테.py 에 --tr-index 로 바로 넣을 수 있다.

⚠️ TR 지수는 기준일이 늦다 (코스피200TR 은 2010-01 기준). 시작일이 창 시작보다 늦으면
   그 앞 구간은 벤치마크가 없다 — 그때는 --div (합성 근사) 와 겹치는 구간으로 교차검증한다.
"""
import argparse, datetime, os, sys, time

try:
    from pykrx import stock
except ImportError:
    sys.exit("⛔ 먼저: pip install pykrx")
import pandas as pd

TODAY = datetime.date.today().strftime("%Y%m%d")
OUTDIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "데이터수리")


def fetch(code, name):
    print(f"\n[수령] {code} {name} — 1996-01 부터 월봉...")
    df = stock.get_index_ohlcv_by_date("19960101", TODAY, code, freq="m")
    if df is None or df.empty:
        print("  ⛔ 빈 응답")
        return
    out = df[["종가"]].rename(columns={"종가": "close"})
    out.index.name = "date"
    fn = os.path.join(OUTDIR, f"_지수_{name.replace(' ', '')}.csv")
    out.to_csv(fn, encoding="utf-8-sig")
    print(f"  저장: {fn}")
    print(f"  {len(out)}행 · {out.index.min().date()} ~ {out.index.max().date()}")
    if str(out.index.min().date()) > "2008-01-31":
        print(f"  ⚠️ 시작일이 2008 창보다 늦다 — 2008 창 TR 비교는 이 지수로 못 한다.")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", default=None)
    a = ap.parse_args()

    if a.code:
        nm = stock.get_index_ticker_name(a.code)
        fetch(a.code, nm or a.code)
        return

    print("=" * 60)
    print(" KRX 지수 중 이름에 TR 이 든 것")
    print("=" * 60)
    found = []
    # 2026-08-11: KRX 는 TR/레버리지 등 파생 지수를 '테마' 그룹에 둔다 — 탐색 범위 확장
    for mkt in ("KOSPI", "KOSDAQ", "테마"):
        try:
            tks = stock.get_index_ticker_list(market=mkt)
        except Exception as e:
            print(f"  ⚠️ {mkt} 목록 실패: {e}")
            continue
        for tk in tks:
            try:
                nm = stock.get_index_ticker_name(tk)
            except Exception:
                continue
            if "TR" in str(nm).upper():
                print(f"  {mkt}  {tk}  {nm}")
                found.append((tk, nm))
            time.sleep(0.05)
    if not found:
        print("  (없음)")
        print("")
        print("  수동 확보 경로 — KRX 정보데이터시스템 data.krx.co.kr:")
        print("   통계 → 지수 → 주가지수 → 개별지수 시세 추이 에서")
        print("   '코스피 200 TR' (또는 '코스피 TR') 검색 → 기간 최대로 → CSV 다운로드")
        print("   → 데이터수리\\_지수_코스피200TR.csv 로 저장 (날짜/종가 컬럼이면 됨)")
        print("   → 운용사양_백테.py 의 --tr-index 로 사용")
        print("")
        print("  ※ 이건 교차검증용이다. --div 근사 본실행은 이것 없이 진행 가능.")
        return
    # 코스피 전체 TR 우선, 없으면 코스피200 TR
    pick = next((f for f in found if str(f[1]).replace(" ", "") in ("코스피TR", "KOSPITR")), None)
    pick = pick or next((f for f in found if "200" in str(f[1]) and "코스피" in str(f[1])), None)
    if pick:
        fetch(*pick)
        print("\n다음: py 운용사양_백테.py ... --tr-index 데이터수리\\_지수_%s.csv"
              % str(pick[1]).replace(" ", ""))
    else:
        print("\n원하는 지수의 코드로: py TR지수_받기.py --code <코드>")


if __name__ == "__main__":
    main()
