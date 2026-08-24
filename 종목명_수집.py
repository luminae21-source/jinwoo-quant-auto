# -*- coding: utf-8 -*-
r"""종목명_수집.py — 전 종목 이름 일괄 수집·캐시 (2026-07-30 신설)

[문제] 도구마다 종목명이 코드로만 나온다. 매번 몇십 건씩 조회하니 캐시가 파편화된다.
[해결] **한 번에 전 종목**을 받아 `종목명_맵.csv` 에 통째로 저장한다. 이후 모든 도구가 즉시 읽는다.

[수집 경로 — 빠른 순으로 시도, 실패하면 다음]
  ① get_market_price_change_by_ticker  : 1콜로 전 종목 '종목명' 컬럼 확보 (가장 빠름)
  ② get_market_ticker_list + get_market_ticker_name : 종목당 1콜 (느리지만 확실)
  ③ 기존 캐시 유지 (수집 실패해도 기존 이름은 안 잃는다)

[상장폐지 종목] pykrx는 현재 상장분만 준다. 과거 소멸 종목은 코드로 남는다 —
  분석에는 지장 없고(코드가 키), 화면 표시만 코드로 뜬다.

사용: py 종목명_수집.py              (증분 — 캐시에 없는 것만)
      py 종목명_수집.py --full       (전량 재수집)
출력: 종목명_맵.csv  (code,name)
"""
import os, sys, argparse, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "종목명_맵.csv")
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass


def load_cache():
    if not os.path.exists(OUT): return {}
    try:
        import pandas as pd
        d = pd.read_csv(OUT, dtype=str)
        return {str(c).zfill(6): str(n) for c, n in zip(d.iloc[:, 0], d.iloc[:, 1])
                if str(n).strip() and str(n) != "nan"}
    except Exception:
        return {}


def save(names):
    import pandas as pd
    pd.DataFrame({"code": list(names), "name": [names[c] for c in names]}) \
      .sort_values("code").to_csv(OUT, index=False, encoding="utf-8-sig")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--full", action="store_true", help="캐시 무시하고 전량 재수집")
    ap.add_argument("--date", default=None, help="기준일 YYYYMMDD (기본: 오늘)")
    a = ap.parse_args()

    names = {} if a.full else load_cache()
    print(f"기존 캐시: {len(names):,}건")

    try:
        from pykrx import stock
    except Exception:
        print("❌ pykrx 없음 —  pip install pykrx  후 다시 실행")
        return 2

    d = a.date or datetime.date.today().strftime("%Y%m%d")
    got_before = len(names)

    # ── ① 1콜로 전 종목 (가장 빠름)
    for mkt in ("KOSPI", "KOSDAQ"):
        try:
            df = stock.get_market_price_change_by_ticker(d, d, market=mkt)
            col = next((c for c in df.columns if "종목명" in str(c) or "name" in str(c).lower()), None)
            if col is None:
                # 인덱스가 티커, 종목명 컬럼이 없으면 ②로
                raise ValueError("종목명 컬럼 없음")
            n = 0
            for t, nm in zip(df.index.astype(str), df[col].astype(str)):
                t = t.zfill(6)
                if nm and nm != "nan" and (a.full or t not in names):
                    names[t] = nm; n += 1
            print(f"  [{mkt}] ① 일괄 조회 → {n:,}건")
        except Exception as e:
            print(f"  [{mkt}] ① 실패({str(e)[:40]}) → ② 개별 조회로 전환")
            try:
                ts = stock.get_market_ticker_list(d, market=mkt)
            except Exception as e2:
                print(f"  [{mkt}] ② 티커 목록도 실패: {str(e2)[:60]}")
                continue
            n = 0
            todo = [t for t in ts if a.full or str(t).zfill(6) not in names]
            for i, t in enumerate(todo, 1):
                try:
                    nm = stock.get_market_ticker_name(t)
                    if nm: names[str(t).zfill(6)] = nm; n += 1
                except Exception:
                    continue
                if i % 200 == 0:
                    print(f"    {i:,}/{len(todo):,} …", flush=True)
            print(f"  [{mkt}] ② 개별 조회 → {n:,}건")

    if len(names) == got_before and got_before:
        print("\n새로 받은 이름 없음 — 캐시 유지")
    save(names)
    print(f"\n✅ 저장: 종목명_맵.csv · 총 {len(names):,}건 (신규 {len(names)-got_before:,})")
    samp = list(names.items())[:5]
    print("  샘플: " + " · ".join(f"{c}={n}" for c, n in samp))
    return 0


if __name__ == "__main__":
    sys.exit(main())
