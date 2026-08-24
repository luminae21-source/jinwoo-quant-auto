#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""fetch_stock_panel_30y.py — [PC 실행] 개별종목 일봉 30년 패널 (생존편향 차단)

★ v2 (2026-07-13) — 수집 방식을 **종목별 → 날짜별**로 완전히 바꿨다.

왜 바꿨나 — v1의 치명적 결함
────────────────────────────────────────────────────────────────────────────
v1은 "역대 종목 5,217개"를 찾아낸 뒤, 종목코드로 하나씩 일봉을 받으려 했다.
그런데 pykrx 는 종목코드로 받을 때 **ISIN(국제증권식별번호)을 먼저 조회**한다.
그리고 **ISIN 조회는 '현재 상장된 종목'만 된다.**

    Error occurred in get_stock_ticker_isin: 'NoneType' object is not subscriptable

→ 상폐된 2,500여 종목은 ISIN을 못 찾아 **일봉을 못 받는다.**
→ 예외를 잡고 넘어가니 조용히 실패하고, 결국 **현재 상장 종목만** 모인다.
→ **생존편향을 막으려다 그대로 생존편향에 걸린다.**

v2의 방식 — 날짜별 수집
────────────────────────────────────────────────────────────────────────────
    get_market_ohlcv(날짜, market="KOSPI")   ← 그날 거래된 **전 종목**을 한 번에

  · ISIN 조회가 필요 없다.
  · 그날 살아있던 종목이 그대로 나온다. **상폐 예정 종목도 포함.**
  · 각 날짜의 실제 상장 유니버스 = 진짜 point-in-time 패널.

이게 생존편향을 막는 유일하게 확실한 방법이다.

산출
────────────────────────────────────────────────────────────────────────────
  종목일봉_30년_KOSPI.csv    (date,code,open,high,low,close,volume)
  종목일봉_30년_KOSDAQ.csv
  종목시총_30년.csv           (date,code,mcap)  ← 월말만
  _fetch_30y_ckpt.json        체크포인트 (날짜 단위. 끊겨도 이어받음)

시간
────────────────────────────────────────────────────────────────────────────
  거래일 약 7,700일 × 2시장 ≈ 15,000회 호출. **2~4시간.**
  중간에 끊겨도 다시 실행하면 이어받는다. PC 켜두고 자면 된다.

사용
────────────────────────────────────────────────────────────────────────────
  py fetch_stock_panel_30y.py --start 1995
  py fetch_stock_panel_30y.py --start 2020        # 짧게 시험 (권장: 먼저 이걸로)
  py fetch_stock_panel_30y.py --self-test
  실행: 종목패널_30년_수집.bat
"""
import os, sys, json, time, argparse, traceback
from datetime import date, datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
CKPT = os.path.join(BASE, "_fetch_30y_ckpt.json")
PATHS = {m: os.path.join(BASE, f"종목일봉_30년_{m}.csv") for m in ("KOSPI", "KOSDAQ")}
MPATH = os.path.join(BASE, "종목시총_30년.csv")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ---------------------------------------------------------------------------
def weekdays(start_year):
    """1995-01-01 ~ 오늘 의 평일 전부. 휴장일은 빈 응답이 오므로 그냥 건너뛴다."""
    d = date(start_year, 1, 1)
    end = date.today()
    out = []
    while d <= end:
        if d.weekday() < 5:
            out.append(d.strftime("%Y%m%d"))
        d += timedelta(days=1)
    return out


def load_ckpt():
    if os.path.exists(CKPT):
        try:
            c = json.load(open(CKPT, encoding="utf-8"))
            if isinstance(c, dict) and "done_dates" in c:
                return c
        except Exception:
            pass
    return {"done_dates": [], "empty": 0, "rows": 0, "started": None, "ver": 2}


def save_ckpt(c):
    json.dump(c, open(CKPT, "w", encoding="utf-8"), ensure_ascii=False)


HDR_OHLCV = "date,code,open,high,low,close,volume"
HDR_MCAP = "date,code,mcap"


def _check_header(path, expect):
    """기존 파일의 헤더가 기대와 다르면 → 덧붙이면 안 된다.

    2026-07-13 사고: v1 헤더는 `code,date,...` 였는데 v2 는 `date,code,...` 로 쓴다.
    파일이 이미 있다고 헤더를 안 고친 채 덧붙였더니 **컬럼이 통째로 뒤집혀 저장**됐다.
    (date 컬럼에 종목코드가 들어갔다.) 그래서 헤더를 반드시 검증한다.
    """
    if not os.path.exists(path):
        with open(path, "w", encoding="utf-8-sig") as f:
            f.write(expect + "\n")
        return True
    try:
        with open(path, encoding="utf-8-sig") as f:
            got = f.readline().strip()
    except Exception:
        got = ""
    if got == expect:
        return True
    print(f"\n  ⚠️ [중단] 헤더 불일치 — {os.path.basename(path)}")
    print(f"       파일: {got or '(빈 파일)'}")
    print(f"       기대: {expect}")
    print(f"     구버전(v1) 파일에 신버전(v2) 데이터를 덧붙이면 컬럼이 뒤집힙니다.")
    print(f"     → 종목패널_30년_초기화후수집.bat 으로 지우고 다시 받으세요.\n")
    return False


def ensure_headers():
    ok = True
    for p in PATHS.values():
        ok &= _check_header(p, HDR_OHLCV)
    ok &= _check_header(MPATH, HDR_MCAP)
    return ok


def is_month_end_wd(ymd, alldays):
    """그 날이 해당 월의 마지막 평일인가 (시총은 월말만 받아 호출 수를 줄인다)."""
    i = alldays.index(ymd)
    return i + 1 == len(alldays) or alldays[i + 1][:6] != ymd[:6]


# ---------------------------------------------------------------------------
def fetch_all(start_year, sleep_s, mcap_on):
    from pykrx import stock
    import pandas as pd

    ckpt = load_ckpt()
    if not ckpt["started"]:
        ckpt["started"] = datetime.now().isoformat()
    if not ensure_headers():
        return 3          # 헤더 불일치 → 덧붙이지 않고 즉시 중단

    days = weekdays(start_year)
    done = set(ckpt["done_dates"])
    todo = [d for d in days if d not in done]

    print("=" * 78)
    print("개별종목 일봉 30년 패널 — v2 날짜별 수집 (생존편향 차단)")
    print("=" * 78)
    print(f"  방식: get_market_ohlcv(날짜, market=...) → 그날 거래된 전 종목")
    print(f"        (종목코드로 받으면 ISIN 조회가 필요해 상폐 종목이 통째로 빠진다)")
    print(f"\n  전체 평일 {len(days):,}일  ·  완료 {len(done):,}일  ·  남은 {len(todo):,}일")
    if not todo:
        print("  이미 전부 수집됨.")
        return summarize(ckpt)

    t0 = time.time()
    codes = set()
    dry = 0          # 연속 빈 응답(=데이터 없는 구간) 카운터
    for i, ymd in enumerate(todo, 1):
        # ★ 연속 40일(약 2개월) 아무것도 안 오면 그 시기엔 데이터가 없는 것이다.
        #   1995년부터 무작정 긁으면 수천 일을 헛돈다(2026-07-13 확인).
        if dry >= 40:
            print(f"\n  ⚠️ {ymd} 까지 연속 {dry}일 빈 응답 — 이 시기엔 KRX 데이터가 없습니다.")
            print(f"     py fetch_stock_panel_30y.py --probe  로 시작 가능 연도를 확인하세요.")
            print(f"     (지금까지 받은 분은 저장돼 있고, --start 를 바꿔 이어받으면 됩니다)\n")
            break
        got = 0
        for mkt in ("KOSPI", "KOSDAQ"):
            df = None
            for attempt in range(2):          # 빈 응답엔 재시도 안 함 (헛돌기 방지)
                try:
                    df = stock.get_market_ohlcv(ymd, market=mkt)
                    break
                except Exception:
                    time.sleep(0.8 * (attempt + 1))
            if df is None or len(df) == 0:
                continue
            df = df.rename(columns={"시가": "open", "고가": "high", "저가": "low",
                                    "종가": "close", "거래량": "volume"})
            keep = [c for c in ("open", "high", "low", "close", "volume") if c in df.columns]
            df = df[keep].copy()
            df = df[df["close"] > 0]
            if not len(df):
                continue
            df.insert(0, "code", [str(c) for c in df.index])
            df.insert(0, "date", f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}")
            df.to_csv(PATHS[mkt], mode="a", header=False, index=False,
                      encoding="utf-8-sig")
            got += len(df)
            codes.update(df["code"])
            ckpt["rows"] += len(df)

            # 시총: 월말 평일에만 (호출 수 절감)
            if mcap_on and is_month_end_wd(ymd, days):
                for attempt in range(2):
                    try:
                        cap = stock.get_market_cap(ymd, market=mkt)
                        if cap is not None and len(cap) and "시가총액" in cap.columns:
                            c2 = cap[["시가총액"]].rename(columns={"시가총액": "mcap"})
                            c2.insert(0, "code", [str(c) for c in c2.index])
                            c2.insert(0, "date", f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}")
                            c2.to_csv(MPATH, mode="a", header=False, index=False,
                                      encoding="utf-8-sig")
                        break
                    except Exception:
                        time.sleep(1.0)
        if got == 0:
            ckpt["empty"] += 1          # 휴장일 또는 데이터 없는 시기
            dry += 1
        else:
            dry = 0
        done.add(ymd)

        if i % 50 == 0 or i == len(todo):
            ckpt["done_dates"] = sorted(done)
            save_ckpt(ckpt)
            el = time.time() - t0
            rate = i / el if el else 0
            eta = (len(todo) - i) / rate / 60 if rate else 0
            print(f"    {i:,}/{len(todo):,}  {ymd}  누적 {ckpt['rows']:,}행  "
                  f"종목 {len(codes):,}  경과 {el/60:.0f}분  남은 {eta:.0f}분")
        time.sleep(sleep_s)

    ckpt["done_dates"] = sorted(done)
    save_ckpt(ckpt)
    return summarize(ckpt)


def summarize(ckpt):
    import pandas as pd
    print("\n" + "=" * 78)
    print("  수집 완료 — 자가 검증")
    print("=" * 78)
    warn = []
    tot = 0
    ncode = 0
    for m, p in PATHS.items():
        if not os.path.exists(p):
            continue
        try:
            d = pd.read_csv(p, usecols=["date", "code"], dtype={"code": str},
                            encoding="utf-8-sig")
            tot += len(d)
            ncode += d.code.nunique()
            if len(d):
                print(f"  {os.path.basename(p)}: {len(d):,}행 · "
                      f"{d.code.nunique():,}종목 · {d.date.min()} ~ {d.date.max()}")
                if str(d.date.min())[:4] > "1996":
                    warn.append(f"{m} 시작이 {str(d.date.min())[:4]}년 — 1995년부터 안 받아졌다")
        except Exception as e:
            warn.append(f"{m} 읽기 실패: {str(e)[:40]}")
    if os.path.exists(MPATH):
        n = sum(1 for _ in open(MPATH, encoding="utf-8-sig")) - 1
        print(f"  {os.path.basename(MPATH)}: {n:,}행")

    print(f"\n  휴장일(빈 응답): {ckpt.get('empty', 0):,}일")
    # 정상치: 역대 종목 4,000~5,500 / 일봉 1,000만~1,800만 행
    if ncode < 3500:
        warn.append(f"종목 {ncode:,}개 — 너무 적다. 상폐 종목이 안 들어왔을 수 있다 (정상 4,000+)")
    if tot < 5_000_000:
        warn.append(f"일봉 {tot:,}행 — 너무 적다 (정상 1,000만+)")

    print("\n" + "=" * 78)
    if warn:
        print("  ⚠️ 이상 징후")
        for w in warn:
            print(f"     · {w}")
        print("\n  대응: _fetch_30y_ckpt.json 과 종목일봉_30년_*.csv 삭제 후 재실행")
        print("        (종목패널_30년_초기화후수집.bat)")
    else:
        print(f"  ✅ 정상 — {ncode:,}종목 · {tot:,}행 (상폐 종목 포함)")
        print(f"\n  다음: py 검정_30년_패널.py")
    print("=" * 78)
    return 0 if not warn else 1


# ---------------------------------------------------------------------------
def self_test():
    ok = tot = 0

    def chk(n, c):
        nonlocal ok, tot
        tot += 1
        ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")

    w = weekdays(1995)
    chk("평일 생성", len(w) > 7000)
    chk("주말 없음", all(datetime.strptime(x, "%Y%m%d").weekday() < 5 for x in w[:200]))
    chk("1995-01-02(월) 포함", "19950102" in w)
    chk("미래 없음", w[-1] <= date.today().strftime("%Y%m%d"))
    # 월말 평일 판정
    sample = [x for x in w if x.startswith("202606")]
    me = [x for x in sample if is_month_end_wd(x, w)]
    chk("2026-06 월말 평일 = 1일", len(me) == 1)
    chk("2026-06 월말 = 06-30", me == ["20260630"])
    import tempfile
    global CKPT
    _r = CKPT
    with tempfile.TemporaryDirectory() as td:
        CKPT = os.path.join(td, "c.json")
        save_ckpt({"done_dates": ["19950102"], "empty": 0, "rows": 10,
                   "started": None, "ver": 2})
        c = load_ckpt()
        chk("체크포인트 저장/로드", c["done_dates"] == ["19950102"])
        chk("v1 형식 거부(재구축)", load_ckpt().get("ver") == 2)
    CKPT = _r
    print(f"\n  평일 {len(w):,}일 (1995-01-02 ~ {w[-1]})")
    print(f"  ※ v2: 날짜별 수집 → ISIN 불필요 → 상폐 종목 포함")
    print(f"\n셀프테스트: {ok}/{tot} (KRX 미접속)")
    return 0 if ok == tot else 1


def probe():
    """★ KRX 전종목시세가 **몇 년부터** 데이터를 주는지 직접 확인한다.

    2026-07-13: 1995년부터 받으려 했더니 빈 응답만 왔다. 추측하지 말고 재본다.
    각 연도의 1월 중순 평일 몇 개를 찍어보고, 응답이 오는 첫 해를 찾는다.
    """
    from pykrx import stock
    print("=" * 78)
    print("탐침 — KRX 전종목시세가 몇 년부터 되는가")
    print("=" * 78)
    first = {}
    for mkt in ("KOSPI", "KOSDAQ"):
        print(f"\n  [{mkt}]")
        for y in range(1995, 2027):
            hit = 0
            for dd in ("0110", "0115", "0120", "0125"):   # 1월 중 평일 후보
                ymd = f"{y}{dd}"
                try:
                    d = datetime.strptime(ymd, "%Y%m%d").date()
                    if d.weekday() >= 5 or d > date.today():
                        continue
                    df = stock.get_market_ohlcv(ymd, market=mkt)
                    if df is not None and len(df) > 0:
                        hit = len(df)
                        break
                except Exception:
                    pass
                time.sleep(0.15)
            mark = "○" if hit else "×"
            print(f"    {y}  {mark}  {f'{hit}종목' if hit else '응답 없음'}")
            if hit and mkt not in first:
                first[mkt] = y
                # 첫 성공 연도 찾으면 그 다음 2년만 더 확인하고 종료
                if y + 2 <= 2026:
                    continue
            if mkt in first and y >= first[mkt] + 2:
                break
    print("\n" + "=" * 78)
    for mkt, y in first.items():
        print(f"  {mkt}: **{y}년부터** 데이터 있음")
    if not first:
        print("  ⚠️ 어느 해도 응답이 없다. 로그인/네트워크 확인 필요.")
        return 1
    s = max(first.values())
    print(f"\n  → 권장 시작 연도: **{s}**")
    print(f"     py fetch_stock_panel_30y.py --start {s}")
    print("=" * 78)
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=1995)
    ap.add_argument("--sleep", type=float, default=0.12)
    ap.add_argument("--no-mcap", action="store_true", help="시총 수집 생략(더 빠름)")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--probe", action="store_true",
                    help="KRX가 몇 년부터 데이터를 주는지 확인만 하고 종료")
    a = ap.parse_args()
    if a.self_test:
        return self_test()
    if a.probe:
        return probe()
    try:
        return fetch_all(a.start, a.sleep, not a.no_mcap)
    except KeyboardInterrupt:
        print("\n  [중단] 체크포인트 저장됨. 다시 실행하면 이어받습니다.")
        return 1
    except Exception:
        print("\n===== [에러] 아래 복사 =====")
        traceback.print_exc()
        print("\n힌트: pip install pykrx pandas")
        return 2


if __name__ == "__main__":
    sys.exit(main())
