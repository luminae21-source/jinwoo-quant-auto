#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""급등종목스캔.py — [PC 실행] 직전 거래일 KRX 전 종목 등락률 스캔 (pykrx / 권위 데이터)

목적: 매일 장 마감 후 재사용. 직전 거래일 기준 KOSPI+KOSDAQ 전 종목을 조회해
      ① 상승 종목 전체(등락률>0, 내림차순)  ② +15%↑ 급등 종목(상한가 별도 표기)
      을 CSV(UTF-8)로 저장. 급등 종목엔 거래대금·구분(동전주/실체급등)을 붙인다.

데이터: pykrx.stock.get_market_ohlcv(날짜, market)  = 그날 거래된 전 종목의
        시가/고가/저가/종가/거래량/거래대금/등락률(전일 종가 대비, 권위값).
        종목명은 get_market_price_change_by_ticker, 시가총액은 get_market_cap_by_ticker 로 보강.

원칙: 실데이터만. 숫자 변환 실패 종목은 절대 깨진 문자열로 쓰지 않고 "데이터부족"으로
      별도 파일(데이터부족_YYYYMMDD.csv)에 분리 표기하며 상승/급등 집계에서 제외한다.

사용:  py 급등종목스캔.py                 (직전 거래일 자동)
       py 급등종목스캔.py 20260717        (특정일 지정)
       py 급등종목스캔.py --self-test      (네트워크 없이 로직 점검)

산출(진우퀀트 루트, 날짜별 누적):
       상승종목_YYYYMMDD.csv · 급등종목_YYYYMMDD.csv · (필요시) 데이터부족_YYYYMMDD.csv
※ pykrx 필요. 실제 조회는 PC에서(회사망은 SSL_CERT_FILE 우회 사용).
"""
import os, sys, csv, math, argparse
from datetime import date

HERE = os.path.dirname(os.path.abspath(__file__))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 급등/구분 기준 (문서화된 임계값)
SURGE_PCT   = 15.0        # +15% 이상 = 급등
UPPER_LO    = 29.5        # 상한가 판정 하한 (가격제한폭 +30% 근사)
UPPER_HI    = 31.0        # 상한가 판정 상한 (신규상장 무제한 급등 등 제외)
PENNY_PRICE = 1000        # 종가 1,000원 미만 = 동전주
REAL_VALUE  = 5_000_000_000  # 거래대금 50억 이상 = 실체급등


# ────────────────────────── 견고한 숫자 파싱 ──────────────────────────
def parse_num(x):
    """숫자/콤마문자열/빈값/NaN/None 을 안전하게 float 또는 None 으로. 실패=None."""
    if x is None:
        return None
    if isinstance(x, bool):
        return None
    if isinstance(x, (int, float)):
        try:
            if math.isnan(float(x)):
                return None
        except Exception:
            return None
        return float(x)
    s = str(x).strip().replace(",", "").replace("%", "")
    if s == "" or s in ("-", "N/A", "n/a", "na", "nan", "NaN", "None", "null", "--"):
        return None
    try:
        return float(s)
    except Exception:
        return None


def is_upper(rate):
    """상한가(근사) 판정: 등락률이 +29.5%~+31% 구간. rate=None 이면 False."""
    return (rate is not None) and (UPPER_LO <= rate <= UPPER_HI)


def gubun(close, value):
    """급등 구분: 동전주 / 실체급등 / 저유동주의."""
    if close is not None and close < PENNY_PRICE:
        return "동전주"
    if value is not None and value >= REAL_VALUE:
        return "실체급등"
    return "저유동주의"


def classify(rate):
    """등락률 → 상승/하락/보합/데이터부족."""
    if rate is None:
        return "데이터부족"
    if rate > 0:
        return "상승"
    if rate < 0:
        return "하락"
    return "보합"


def fmt_int(x):
    return "" if x is None else str(int(round(x)))


# ────────────────────────── 데이터 수집 (PC/네트워크) ──────────────────────────
def resolve_date(arg):
    from pykrx import stock
    if arg:
        return arg
    d = stock.get_nearest_business_day_in_a_week()  # 오늘 포함 직전 영업일
    return d


def fetch_records(date_str):
    """직전 거래일 전 종목 레코드 리스트. 각 원소:
    {code,name,market,close,value,volume,rate,mcap,cat,upper}"""
    from pykrx import stock

    def zfill6(t):
        return str(t).strip().zfill(6)

    recs = []
    for mk in ("KOSPI", "KOSDAQ"):
        try:
            oh = stock.get_market_ohlcv(date_str, market=mk)
        except Exception as e:
            print(f"  [{mk}] 조회 실패: {str(e)[:60]}")
            continue
        if oh is None or len(oh) == 0:
            print(f"  [{mk}] {date_str} 데이터 없음(휴장 가능)")
            continue
        oh = oh.reset_index()
        # 종목명 맵 (1 콜)
        names = {}
        try:
            pc = stock.get_market_price_change_by_ticker(date_str, date_str, market=mk)
            for t in pc.index:
                names[zfill6(t)] = str(pc.loc[t, "종목명"])
        except Exception:
            names = {}
        # 시가총액 맵 (1 콜, 선택)
        caps = {}
        try:
            cap = stock.get_market_cap_by_ticker(date_str, market=mk)
            for t in cap.index:
                caps[zfill6(t)] = parse_num(cap.loc[t, "시가총액"])
        except Exception:
            caps = {}

        for row in oh.to_dict("records"):
            code = zfill6(row.get("티커", row.get("code", "")))
            rate = parse_num(row.get("등락률"))
            close = parse_num(row.get("종가"))
            value = parse_num(row.get("거래대금"))
            vol = parse_num(row.get("거래량"))
            name = names.get(code, "")
            if not name:
                try:
                    name = stock.get_market_ticker_name(code)
                except Exception:
                    name = ""
            recs.append({
                "code": code, "name": name, "market": mk,
                "close": close, "value": value, "volume": vol,
                "rate": rate, "mcap": caps.get(code),
                "cat": classify(rate), "upper": is_upper(rate),
            })
    return recs


# ────────────────────────── CSV 출력 ──────────────────────────
def write_rise(path, rows):
    head = ["순위", "종목코드", "종목명", "시장", "등락률(%)", "종가", "거래대금", "거래량", "시가총액", "상한가"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(head)
        for i, r in enumerate(rows, 1):
            w.writerow([i, r["code"], r["name"], r["market"], f"{r['rate']:.2f}",
                        fmt_int(r["close"]), fmt_int(r["value"]), fmt_int(r["volume"]),
                        fmt_int(r["mcap"]), "Y" if r["upper"] else ""])


def write_surge(path, rows):
    head = ["순위", "종목코드", "종목명", "시장", "등락률(%)", "종가", "거래대금", "거래량", "시가총액", "상한가", "구분"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(head)
        for i, r in enumerate(rows, 1):
            w.writerow([i, r["code"], r["name"], r["market"], f"{r['rate']:.2f}",
                        fmt_int(r["close"]), fmt_int(r["value"]), fmt_int(r["volume"]),
                        fmt_int(r["mcap"]), "Y" if r["upper"] else "", gubun(r["close"], r["value"])])


def write_missing(path, rows):
    head = ["종목코드", "종목명", "시장", "비고"]
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(head)
        for r in rows:
            w.writerow([r["code"], r["name"], r["market"], "데이터부족"])


def run(date_str):
    recs = fetch_records(date_str)
    if not recs:
        print(f"[데이터부족] {date_str} 조회 결과 없음. 날짜/네트워크 확인.")
        return 1

    total = len(recs)
    missing = [r for r in recs if r["cat"] == "데이터부족"]
    rise = sorted([r for r in recs if r["cat"] == "상승"], key=lambda r: -r["rate"])
    fall = [r for r in recs if r["cat"] == "하락"]
    flat = [r for r in recs if r["cat"] == "보합"]
    surge = [r for r in rise if r["rate"] >= SURGE_PCT]
    upper = [r for r in surge if r["upper"]]

    # 무결성: 상승+하락+보합+데이터부족 == 전체
    assert len(rise) + len(fall) + len(flat) + len(missing) == total, "집계 합계 불일치"

    rise_p = os.path.join(HERE, f"상승종목_{date_str}.csv")
    surge_p = os.path.join(HERE, f"급등종목_{date_str}.csv")
    write_rise(rise_p, rise)
    write_surge(surge_p, surge)
    if missing:
        write_missing(os.path.join(HERE, f"데이터부족_{date_str}.csv"), missing)

    print("=" * 60)
    print(f" 기준일(직전 거래일): {date_str}")
    print(f" 전체 {total} | 상승 {len(rise)} · 하락 {len(fall)} · 보합 {len(flat)} · 데이터부족 {len(missing)}")
    print(f" +{SURGE_PCT:.0f}%↑ 급등: {len(surge)}  (상한가 {len(upper)})")
    print("=" * 60)
    print(" 상위 10 (등락률 순, 거래대금 병기):")
    for i, r in enumerate(rise[:10], 1):
        val = "" if r["value"] is None else f"{r['value']/1e8:,.1f}억"
        flag = " [상한가]" if r["upper"] else ""
        print(f"  {i:2d}. {r['code']} {r['name']:<12} {r['market']:<6} +{r['rate']:.2f}%  {val}{flag}")
    print("-" * 60)
    print(f" 저장: {os.path.basename(rise_p)} ({len(rise)}행) · {os.path.basename(surge_p)} ({len(surge)}행)")
    if missing:
        print(f"       데이터부족_{date_str}.csv ({len(missing)}종목)")
    return 0


# ────────────────────────── 셀프테스트 (네트워크 불필요) ──────────────────────────
def _self_test():
    ok = tot = 0

    def chk(name, cond):
        nonlocal ok, tot
        tot += 1
        ok += 1 if cond else 0
        print(f"  [{'OK' if cond else 'FAIL'}] {name}")

    # 1) 숫자 파싱
    chk("parse '1,234' -> 1234.0", parse_num("1,234") == 1234.0)
    chk("parse '1234' -> 1234.0", parse_num("1234") == 1234.0)
    chk("parse ' 12,345.6 ' -> 12345.6", parse_num(" 12,345.6 ") == 12345.6)
    chk("parse 1234.5 (float) 유지", parse_num(1234.5) == 1234.5)
    chk("parse '' -> None", parse_num("") is None)
    chk("parse '-' -> None", parse_num("-") is None)
    chk("parse 'N/A' -> None", parse_num("N/A") is None)
    chk("parse None -> None", parse_num(None) is None)
    chk("parse NaN -> None", parse_num(float("nan")) is None)
    chk("parse '깨진문자' -> None", parse_num("3,불명") is None)

    # 2) 상한가 판정
    chk("상한가 29.9 -> True", is_upper(29.9) is True)
    chk("상한가 30.0 -> True", is_upper(30.0) is True)
    chk("상한가 15.0 -> False", is_upper(15.0) is False)
    chk("상한가 45.0(신규상장) -> False", is_upper(45.0) is False)
    chk("상한가 None -> False", is_upper(None) is False)

    # 3) 구분
    chk("구분 종가 900 -> 동전주", gubun(900, 9e9) == "동전주")
    chk("구분 거래대금 60억 -> 실체급등", gubun(2000, 6_000_000_000) == "실체급등")
    chk("구분 저유동 -> 저유동주의", gubun(2000, 100_000_000) == "저유동주의")

    # 4) 분류 + 정렬 + 합계 무결성
    sample = [
        {"rate": 30.0}, {"rate": 15.0}, {"rate": 3.2}, {"rate": 0.0},
        {"rate": -5.0}, {"rate": -30.0}, {"rate": None}, {"rate": 0.01}, {"rate": None},
    ]
    for s in sample:
        s["cat"] = classify(s["rate"])
    rise = sorted([s for s in sample if s["cat"] == "상승"], key=lambda s: -s["rate"])
    fall = [s for s in sample if s["cat"] == "하락"]
    flat = [s for s in sample if s["cat"] == "보합"]
    miss = [s for s in sample if s["cat"] == "데이터부족"]
    chk("상승 4개", len(rise) == 4)
    chk("하락 2개", len(fall) == 2)
    chk("보합 1개", len(flat) == 1)
    chk("데이터부족 2개", len(miss) == 2)
    chk("합계 == 전체(9)", len(rise) + len(fall) + len(flat) + len(miss) == len(sample))
    chk("정렬 내림차순", [s["rate"] for s in rise] == [30.0, 15.0, 3.2, 0.01])
    chk("급등(+15%↑) 2개", len([s for s in rise if s["rate"] >= SURGE_PCT]) == 2)

    # 5) fmt_int 견고성
    chk("fmt_int None -> ''", fmt_int(None) == "")
    chk("fmt_int 1234.6 -> '1235'", fmt_int(1234.6) == "1235")

    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("date", nargs="?", default=None, help="YYYYMMDD (생략 시 직전 거래일)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return 0 if _self_test() else 1
    try:
        d = resolve_date(a.date)
    except Exception as e:
        print(f"[데이터부족] 날짜 확인 실패(네트워크?): {str(e)[:60]}")
        return 1
    return run(d)


if __name__ == "__main__":
    sys.exit(main())
