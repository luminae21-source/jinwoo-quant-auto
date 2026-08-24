#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""fetch_fundamental_panel.py — KRX 재무(밸류) 지표 날짜별 백필

D단계 준비: 밸류(저PBR)·저PER를 30년(있는 만큼) 검정하려면 재무 이력이 필요하다.
현재 fundamentals_pit.csv는 FY2019~2025뿐 → IN 구간이 비어 판정 불가였다.

수집 방식은 가격 패널과 **동일하게 날짜별**:
    get_market_fundamental(날짜, market=)  → 그날 상장된 전 종목의 BPS·PER·PBR·EPS·DIV·DPS
날짜별이므로 **생존편향 없음**. 상폐예정 종목도 그날 값이 그대로 들어온다.

경량화: **월말(각 월 마지막 거래일)만** 수집한다. 월별 리밸런싱엔 이걸로 충분하고
API 호출이 ~720회로 준다(매일이면 수천 회).

⚠️ KRX가 PBR/PER를 몇 년치 주는지는 모른다 → --probe 로 먼저 확인(추측 금지).

산출:
    종목재무_KRX_KOSPI.csv / 종목재무_KRX_KOSDAQ.csv
    헤더: date,code,BPS,PER,PBR,EPS,DIV,DPS

사용:
    py fetch_fundamental_panel.py --probe            (가용 시작연도만 확인)
    py fetch_fundamental_panel.py                    (전체 수집, 재개 가능)
    py fetch_fundamental_panel.py --start 2001
    py fetch_fundamental_panel.py --self-test
"""
import os, sys, csv, time, argparse, calendar
from datetime import date, datetime, timedelta

BASE = os.path.dirname(os.path.abspath(__file__))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HDR = ["date", "code", "BPS", "PER", "PBR", "EPS", "DIV", "DPS"]
MARKETS = ("KOSPI", "KOSDAQ")
# probe(2026-07-16)로 확인한 PBR/PER 실제 가용 시작연도. 그 이전은 PBR=0(미계산).
MARKET_START = {"KOSPI": 2002, "KOSDAQ": 2006}
MIN_UNIVERSE = 100           # 월말 수신 종목이 이보다 적으면 이상(휴장/오류)
CKPT = os.path.join(BASE, "_fetch_fund_ckpt.txt")


def month_ends(start_year, end_dt=None):
    """start_year 1월부터 오늘까지 각 월의 마지막 '달력일' (거래일 보정은 fetch에서)."""
    end_dt = end_dt or date.today()
    out = []
    y, m = start_year, 1
    while (y, m) <= (end_dt.year, end_dt.month):
        last = calendar.monthrange(y, m)[1]
        d = date(y, m, last)
        if d <= end_dt:
            out.append(d)
        m += 1
        if m > 12:
            m = 1; y += 1
    return out


BDAY_CACHE = os.path.join(BASE, "_bday_cache.json")


def load_bday_cache():
    """달력 월말 → 실제 거래일. 한 번 알아낸 건 다시 안 묻는다."""
    try:
        import json
        return json.load(open(BDAY_CACHE, encoding="utf-8"))
    except Exception:
        return {}


def save_bday_cache(c):
    try:
        import json
        json.dump(c, open(BDAY_CACHE, "w", encoding="utf-8"))
    except Exception:
        pass


def month_already_done(done, d, markets, starts):
    """⚠️ 2026-08-20 신설 — 네트워크를 부르기 **전에** 이 달이 끝났는지 본다.

    초판은 _nearest_bday_str(네트워크!) 를 295개 월말 전부에 대해 먼저 부르고
    그 다음에 체크포인트를 봤다. 이미 받은 달도 매번 KRX 를 두드린 셈이고,
    그래서 '자동화 수단을 통한 비정상 대량 조회'로 IP 가 차단됐다(2026-08-20).
    체크포인트 키가 'YYYYMMDD:MARKET' 이므로 앞 6자리(YYYYMM)만 봐도 판정된다.
    """
    ym = d.strftime("%Y%m")
    need = [m for m in markets if d.year >= starts[m]]
    if not need:
        return True
    have = {k.split(":")[1] for k in done if k[:6] == ym and ":" in k}
    return all(m in have for m in need)


def _nearest_bday_str(stock, d, cache=None):
    """d(달력 월말)에서 거슬러 최근 거래일 YYYYMMDD. pykrx 호출 최소화용."""
    key = d.strftime("%Y%m%d")
    if cache is not None and key in cache:
        return cache[key]
    try:
        r = stock.get_nearest_business_day_in_a_week(key, prev=True)
        if cache is not None:
            cache[key] = r
        return r
    except Exception:
        # 폴백: 하루씩 되돌리며 주말 회피(공휴일은 fetch가 빈값→상위에서 재시도)
        x = d
        while x.weekday() >= 5:
            x -= timedelta(days=1)
        return x.strftime("%Y%m%d")


def fetch_one(stock, pd, ymd, market):
    """하루치 재무. 실패/빈값이면 None."""
    try:
        df = stock.get_market_fundamental(ymd, market=market)
    except Exception:
        return None
    if df is None or len(df) == 0:
        return None
    df = df.copy()
    df["code"] = [str(c).zfill(6) for c in df.index]
    df["date"] = pd.to_datetime(ymd).strftime("%Y-%m-%d")
    for c in ("BPS", "PER", "PBR", "EPS", "DIV", "DPS"):
        if c not in df.columns:
            df[c] = float("nan")
    return df[HDR]


def _check_header(path):
    """기존 파일 헤더가 HDR과 다르면 append 거부(오염 방지)."""
    if not os.path.exists(path):
        return True
    with open(path, "r", encoding="utf-8-sig") as f:
        first = f.readline().strip()
    return first == ",".join(HDR)


def load_ckpt():
    if os.path.exists(CKPT):
        return set(open(CKPT, encoding="utf-8").read().split())
    return set()


def save_ckpt(done):
    open(CKPT, "w", encoding="utf-8").write("\n".join(sorted(done)))


def probe(stock, pd):
    """가용 시작연도 확인 — 각 시장에서 데이터가 나오는 첫 해."""
    print("탐침 — get_market_fundamental 가용 범위")
    for market in MARKETS:
        found = None
        for y in range(1995, date.today().year + 1):
            ymd = _nearest_bday_str(stock, date(y, 6, 30))
            df = fetch_one(stock, pd, ymd, market)
            n = 0 if df is None else len(df)
            if n >= MIN_UNIVERSE:
                # PBR이 실제로 채워지는지도 본다(초기엔 빈 값일 수 있음)
                pbr_ok = df["PBR"].astype(float).gt(0).sum()
                print(f"  {market} {y}: {n}종목, PBR>0 {pbr_ok}개  ← 첫 데이터" if found is None
                      else f"  {market} {y}: {n}종목")
                if found is None and pbr_ok > MIN_UNIVERSE // 2:
                    found = y
                    break
            time.sleep(0.3)
        print(f"  → {market} 가용 시작: {found}")
    return 0


def collect(start_year):
    import pandas as pd
    from pykrx import stock
    # start_year 미지정(None)이면 시장별 가용시작(MARKET_START) 사용.
    override = start_year is not None
    base_start = start_year if override else min(MARKET_START.values())
    ends = month_ends(base_start)
    done = load_ckpt()
    starts = {m: (base_start if override else MARKET_START[m]) for m in MARKETS}
    print(f"월말 {len(ends)}개 · 시장별 시작 {starts} · 이미 완료 {len(done)}건")

    paths = {m: os.path.join(BASE, f"종목재무_KRX_{m}.csv") for m in MARKETS}
    for m, p in paths.items():
        if not _check_header(p):
            print(f"  [중단] {os.path.basename(p)} 헤더 불일치 — 다른 형식 파일. 수동 확인.")
            return 2

    writers = {}; files = {}
    for m, p in paths.items():
        new = not os.path.exists(p)
        files[m] = open(p, "a", encoding="utf-8-sig", newline="")
        writers[m] = csv.writer(files[m])
        if new:
            writers[m].writerow(HDR)

    try:
        total = 0; dry = 0
        bcache = load_bday_cache()
        skipped = 0; calls = 0; failstreak = 0
        for i, d in enumerate(ends):
            # ★ 네트워크보다 먼저 판정 — 이미 끝난 달은 KRX 를 아예 안 부른다
            if month_already_done(done, d, MARKETS, starts):
                skipped += 1; dry = 0
                continue
            ymd = _nearest_bday_str(stock, d, bcache)
            calls += 1
            got_any = False
            for m in MARKETS:
                if d.year < starts[m]:      # 그 시장의 PBR 가용 전이면 건너뜀
                    continue
                key = f"{ymd}:{m}"
                if key in done:
                    got_any = True
                    continue
                df = fetch_one(stock, pd, ymd, m)
                calls += 1
                if df is None:
                    failstreak += 1
                    if failstreak >= 6:
                        print("  [중단] 연속 6회 빈 응답 — KRX 차단/점검 의심.")
                        print("         오늘은 재시도하지 마십시오(차단이 연장됩니다).")
                        save_bday_cache(bcache); save_ckpt(done)
                        return 3
                else:
                    failstreak = 0
                if df is not None and len(df) >= MIN_UNIVERSE:
                    for row in df.itertuples(index=False):
                        writers[m].writerow(row)
                    total += len(df); got_any = True
                    done.add(key)
                time.sleep(0.4)
            if got_any:
                dry = 0
            else:
                dry += 1
            if (i + 1) % 12 == 0:
                for f in files.values():
                    f.flush()
                save_ckpt(done)
                print(f"  {d.strftime('%Y-%m')} … 누적 {total:,}행")
            if dry >= 24:
                print("  연속 24개월 빈 응답 — 데이터 없는 시기로 판단, 종료")
                break
        try:
            save_bday_cache(bcache)
            print(f"  네트워크 호출 {calls}건 · 건너뛴 달 {skipped}개 (캐시·체크포인트 덕)")
        except Exception:
            pass
    finally:
        for f in files.values():
            f.close()
        save_ckpt(done)

    print(f"\n✅ 수집 종료 — 누적 {total:,}행")
    for m, p in paths.items():
        if os.path.exists(p):
            n = sum(1 for _ in open(p, encoding="utf-8-sig")) - 1
            print(f"  {os.path.basename(p)}: {n:,}행")
    return 0


def _self_test():
    ok = tot = 0

    def chk(n, c):
        nonlocal ok, tot
        tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")

    # 월말 생성 — 3/15까지면 3월말(3/31)은 아직 안 지나 제외 → 2개월
    me = month_ends(2020, date(2020, 3, 15))
    chk("3/15까지 → 월말 2개(1월·2월)", len(me) == 2)
    chk("1월말=1/31", me[0] == date(2020, 1, 31))
    chk("2월말=2/29(윤년)", me[1] == date(2020, 2, 29))
    chk("3월말은 아직 미도래 → 제외", me[-1] == date(2020, 2, 29))
    # 월말이 지난 경우 포함
    me_apr = month_ends(2020, date(2020, 3, 31))
    chk("3/31까지 → 3월말 포함(3개)", len(me_apr) == 3)

    me2 = month_ends(2019, date(2021, 12, 31))
    chk("2019~2021 = 36개월", len(me2) == 36)

    # 헤더 검사
    import tempfile
    d = tempfile.mkdtemp()
    good = os.path.join(d, "g.csv")
    open(good, "w", encoding="utf-8-sig").write(",".join(HDR) + "\n1,2\n")
    bad = os.path.join(d, "b.csv")
    open(bad, "w", encoding="utf-8-sig").write("code,date,close\n")
    global _
    # _check_header는 BASE 경로 무관, 인자 경로 사용
    chk("올바른 헤더 → append 허용", _check_header(good) is True)
    chk("다른 헤더 → append 거부", _check_header(bad) is False)
    chk("없는 파일 → 허용(신규)", _check_header(os.path.join(d, "none.csv")) is True)

    # HDR 순서 고정
    chk("헤더 = date,code,BPS,PER,PBR,EPS,DIV,DPS",
        HDR == ["date", "code", "BPS", "PER", "PBR", "EPS", "DIV", "DPS"])

    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=None,
                    help="시작연도 강제(미지정시 시장별 MARKET_START: KOSPI2002/KOSDAQ2006)")
    ap.add_argument("--probe", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return 0 if _self_test() else 1
    try:
        import pandas as pd
        from pykrx import stock
    except ImportError:
        print("pykrx/pandas 필요. pip install pykrx"); return 2
    if a.probe:
        return probe(stock, pd)
    if a.start:
        print(f"수집 시작연도(강제): {a.start}")
    else:
        print(f"수집 시작연도(시장별): {MARKET_START}")
    return collect(a.start)


if __name__ == "__main__":
    sys.exit(main())
