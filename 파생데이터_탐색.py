#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
파생데이터_탐색.py — 파생/매크로/이벤트 데이터가 pykrx·KRX·yfinance로 실제 자동수집 되는지 PROBE.
원칙: 실재하는 데이터만. 추정·대체값 절대 금지. 각 소스가 반환하는 그대로 출력(성공값/실패에러).
출력: 콘솔 + 파생탐색_결과.txt. production·기존 산출물 무수정.
[PC 실행] 네트워크 필요(KRX/yfinance). 샌드박스선 403 → dir()탐색·날짜계산만 유효.
"""
import sys, traceback, inspect
from datetime import date, timedelta
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
from pathlib import Path
BASE = Path(__file__).parent.resolve()
OUT = []


def emit(s=""):
    print(s); OUT.append(s)


def sig(fn):
    try:
        return str(inspect.signature(fn))
    except Exception as e:
        return "(sig 확인불가: %s)" % e


def probe(label, fn):
    emit("\n[%s]" % label)
    try:
        r = fn()
        txt = repr(r)
        emit("  ✅ 반환: " + (txt[:600] + (" …(생략)" if len(txt) > 600 else "")))
    except Exception as e:
        emit("  ❌ 실패: %s: %s" % (type(e).__name__, str(e)[:300]))


def nearest_bday():
    from pykrx import stock
    return stock.get_nearest_business_day_in_a_week(date.today().strftime("%Y%m%d"))


def _bd():
    try:
        return nearest_bday()
    except Exception:
        d = date.today()
        while d.weekday() >= 5:
            d -= timedelta(days=1)
        return d.strftime("%Y%m%d")


# ---------- 이벤트(날짜계산 — 오프라인 실제 산출) ----------
def second_thursday(y, m):
    d = date(y, m, 1)
    first_thu = d + timedelta(days=(3 - d.weekday()) % 7)
    return first_thu + timedelta(days=7)


def upcoming_expiries(today, n=4):
    out = []
    y, m = today.year, today.month
    while len(out) < n:
        e = second_thursday(y, m)
        if e >= today:
            quad = m in (3, 6, 9, 12)
            out.append((str(e), "분기 동시만기(네 마녀)" if quad else "월물 옵션만기"))
        m += 1
        if m > 12:
            m = 1; y += 1
    return out


def main():
    today = date.today()
    emit("=" * 60)
    emit("파생/매크로/이벤트 데이터 실재성 탐색 — %s" % today)
    emit("원칙: 실재 데이터만. 추정·대체 금지. 반환 그대로 표기.")
    emit("=" * 60)

    # 라이브러리 가용
    try:
        import pykrx; emit("\n● pykrx import: OK (%s)" % getattr(pykrx, "__version__", "?"))
    except Exception as e:
        emit("\n● pykrx import: 실패 %s" % e)
    try:
        import yfinance; emit("● yfinance import: OK (%s)" % getattr(yfinance, "__version__", "?"))
    except Exception as e:
        emit("● yfinance import: 실패 %s" % e)

    # pykrx.stock 함수 목록(파생/지수/투자자 키워드)
    emit("\n--- pykrx.stock 사용가능 함수(키워드 매칭) ---")
    try:
        from pykrx import stock
        names = [n for n in dir(stock) if not n.startswith("_")]
        kw = ["future", "option", "deriv", "index", "investor", "trading", "oi", "open_interest"]
        hit = [n for n in names if any(k in n.lower() for k in kw)]
        emit("  파생/지수/투자자 후보 %d개:" % len(hit))
        for n in hit:
            emit("    - %s" % n)
        emit("  (전체 함수 %d개 중)" % len(names))
    except Exception as e:
        emit("  ❌ %s" % e)

    bd = _bd()
    emit("\n최근 영업일(기준일): %s" % bd)

    from pykrx import stock
    # === 파생 포지션 ===
    emit("\n========== 파생 포지션 ==========")
    # 1a. KOSPI200 현물
    probe("1a. KOSPI200 현물 get_index_ohlcv(bd,bd,'1028')",
          lambda: stock.get_index_ohlcv(bd, bd, "1028").to_dict())
    # 1b. 선물 티커 목록 — 인자 없이(시그니처 먼저)
    emit("\n[1b. 선물 티커 목록 get_future_ticker_list — 시그니처 확인 후 인자 없이 호출]")
    emit("  시그니처: get_future_ticker_list%s" % sig(stock.get_future_ticker_list))
    fut_list = None
    try:
        fut_list = stock.get_future_ticker_list()
        emit("  ✅ 반환 %d개: %s" % (len(fut_list), list(fut_list)[:20]))
    except Exception as e:
        emit("  ❌ %s: %s" % (type(e).__name__, str(e)[:200]))
    # 1c. 선물 OHLCV — 시그니처 확인 후 첫 티커
    emit("\n[1c. 선물 OHLCV get_future_ohlcv — 시그니처 확인 후 호출, 컬럼 전체 확인]")
    emit("  시그니처: get_future_ohlcv%s" % sig(stock.get_future_ohlcv))
    fut_close = None
    if fut_list:
        tk = fut_list[0]
        try:
            df = stock.get_future_ohlcv(bd, bd, tk)
            emit("  티커 %s 컬럼: %s" % (tk, list(df.columns)))
            emit("  ✅ 최근행: %s" % df.tail(1).to_dict())
            oicol = [c for c in df.columns if ("미결제" in str(c)) or ("약정" in str(c)) or ("OI" in str(c).upper())]
            emit("  → 미결제약정(OI) 컬럼: %s" % (oicol if oicol else "없음(OI는 MDC/HTS 필요)"))
            if "종가" in df.columns:
                fut_close = float(df["종가"].iloc[-1])
        except Exception as e:
            emit("  ❌ get_future_ohlcv 실패: %s: %s" % (type(e).__name__, str(e)[:200]))
            emit("  ※ 인자순서 다르면 위 시그니처대로 PC에서 조정(추정 금지).")
    else:
        emit("  (선물 목록 미확보 → 호출 생략)")
    # 1d. 베이시스 (둘 다 실측일 때만)
    emit("\n[1d. 베이시스 = 선물 − KOSPI200현물(1028)]")
    try:
        spot = float(stock.get_index_ohlcv(bd, bd, "1028")["종가"].iloc[-1])
        if fut_close is not None:
            b = fut_close - spot
            emit("  현물 %.2f / 선물 %.2f / 베이시스 %+.2f → %s" % (spot, fut_close, b, "콘탱고" if b > 0 else "백워데이션"))
        else:
            emit("  ❌ 데이터부족(선물 종가 미확보) → 계산 안 함(추정 금지)")
    except Exception as e:
        emit("  ❌ %s: %s" % (type(e).__name__, str(e)[:150]))
    # 3. 현물 투자자거래(확인됨) + 선물 투자자/OI/옵션은 MDC 섹션에서
    probe("3. 현물 투자자별 순매수 get_market_trading_value_by_investor(bd,bd,'KOSPI')",
          lambda: stock.get_market_trading_value_by_investor(bd, bd, "KOSPI").to_dict())
    emit("  ※ 선물 투자자거래·옵션 풋콜은 pykrx 함수 부재 → 아래 MDC 직접시도.")

    # 5. VKOSPI — 전 시장 지수목록 훑어 '변동성' 검색
    emit("\n[5. VKOSPI — 지수 티커목록 전 시장 '변동성/VKOSPI' 검색]")
    found = []
    for mkt in ["KOSPI", "KOSDAQ", "KRX", "테마"]:
        try:
            for c in stock.get_index_ticker_list(bd, mkt):
                nm = stock.get_index_ticker_name(c)
                if ("변동성" in nm) or ("VKOSPI" in nm.upper()):
                    found.append((mkt, c, nm))
        except Exception as e:
            emit("  (%s 목록 실패: %s)" % (mkt, str(e)[:120]))
    emit("  변동성 지수 검색결과: %s" % (found if found else "없음(→ MDC/HTS)"))
    probe("5b. yfinance ^VKOSPI(검증용)",
          lambda: __import__("yfinance").Ticker("^VKOSPI").history(period="5d")["Close"].tolist())

    # === KRX MDC 직접통계 시도 (pykrx 미지원분: VKOSPI/선물투자자/옵션 풋콜) ===
    emit("\n========== KRX MDC 직접통계 시도 (pykrx 미지원분) ==========")
    emit("  ※ data.krx.co.kr는 보통 OTP(generate.cmd) 토큰 + 정확 bld코드 필요. 아래는 1회 시도 — 반환 그대로 기록, 억지 생성 금지.")
    try:
        import requests
        u = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
        hd = {"User-Agent": "Mozilla/5.0", "Referer": "http://data.krx.co.kr/"}
        r = requests.post(u, data={"bld": "dbms/MDC/STAT/standard/MDCSTAT00101"}, headers=hd, timeout=10)
        body = r.text[:250]
        emit("  HTTP %s · 본문앞: %s" % (r.status_code, body))
        emit("  → 정상 JSON 아니면 OTP/정확 bld 필요(수동 또는 별도 구현). VKOSPI·선물투자자·옵션 풋콜은 이 경로 확정 후 자동화.")
    except Exception as e:
        emit("  ❌ MDC 시도 실패: %s: %s" % (type(e).__name__, str(e)[:200]))

    # === 금리/매크로 ===
    emit("\n========== 금리/매크로 ==========")
    for nm, tk in [("美10년물 ^TNX", "^TNX"), ("美13주 ^IRX", "^IRX"), ("美5년 ^FVX", "^FVX"), ("美30년 ^TYX", "^TYX")]:
        probe("6. %s" % nm, (lambda t=tk: __import__("yfinance").Ticker(t).history(period="5d")["Close"].tolist()))
    emit("  ※ 美2년물: yfinance 표준 티커 부재(확인됨이면 수동/FRED). 한미 금리차 = 美10년 − 한국기준금리(아래).")
    emit("\n[6b. 한국 기준금리]")
    emit("  ※ ECOS(한국은행) API 키 필요 → 키 없으면 '수동 입력'. 자동화하려면 ECOS 키 발급 후 별도 연동.")

    # === 이벤트(계산/공개일정) ===
    emit("\n========== 이벤트 ==========")
    emit("\n[7. 옵션·선물 만기일 — 날짜계산(자동 산출 가능)]")
    for dt, kind in upcoming_expiries(today):
        emit("  - %s : %s" % (dt, kind))
    emit("  → 둘째 목요일 룰로 100%% 자동 산출 가능(외부데이터 불요).")
    emit("\n[8. FOMC·금통위·CPI·고용 일정]")
    emit("  - 금통위: theme_calendar_fixed.csv에 BOK 확정일 보유(자동). FOMC: 동 파일에 2026 일정 보유.")
    emit("  - CPI(美 ~매월 중순)·고용(NFP 첫 금요일): 날짜계산 근사 가능(theme_calendar_v1.py). 확정일은 공개일정 수동확인.")
    emit("  - 자동 무료 통합 캘린더 API는 별도 부재 → 위 파일 기반 + 수동 보정.")

    emit("\n" + "=" * 60)
    emit("결론 작성용: 위 ✅/❌를 보고 (자동가능 / KRX MDC필요 / HTS수동 / ECOS키필요)로 분류.")
    (BASE / "파생탐색_결과.txt").write_text("\n".join(OUT), encoding="utf-8")
    emit("[저장] 파생탐색_결과.txt")


if __name__ == "__main__":
    try:
        main()
    except Exception:
        print("\n[치명 에러]"); traceback.print_exc()
