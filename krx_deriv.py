#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
krx_deriv.py — KRX 파생 탐색 (견고화판: 타임아웃·증분기록·전구간 예외·OTP경로)
원칙: 공식 실데이터만. 실패=데이터부족. 가짜·추정 절대 금지.
견고화: ①모든 requests timeout=8 ②결과 즉시 write+flush(몰아쓰기 금지) ③각 블록 try/except + main 최상위 try
        ④콘솔 print(flush)·시작/끝 마커 ⑤세션 헤더 + OTP(generate.cmd) 1회 경로 ⑥pykrx 호출 스레드 타임아웃(행 방지).
참고: KRX가 MDC 스크레이핑을 LOGOUT으로 막음 → 본 파일은 ❌가 정상일 수 있음. 정식경로=krx_openapi.py(인증키).
"""
import sys, json, traceback, threading
from datetime import date, timedelta
from pathlib import Path
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
BASE = Path(__file__).parent.resolve()
TIMEOUT = 8
MDC = "http://data.krx.co.kr/comm/bldAttendant/getJsonData.cmd"
OTPGEN = "http://data.krx.co.kr/comm/fileDn/GenerateOTP/generate.cmd"
HDR = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
       "Referer": "http://data.krx.co.kr/", "X-Requested-With": "XMLHttpRequest"}

_LOG = None
def emit(s=""):
    print(s, flush=True)
    global _LOG
    if _LOG is not None:
        _LOG.write(s + "\n"); _LOG.flush()    # ← 증분 기록


def with_timeout(fn, secs=10, label=""):
    """pykrx 등 무한대기 위험 호출을 스레드로 감싸 secs 초과 시 끊음(행 방지)."""
    box = {}
    def run():
        try: box["r"] = fn()
        except Exception as e: box["e"] = e
    t = threading.Thread(target=run, daemon=True); t.start(); t.join(secs)
    if t.is_alive():
        return None, "TIMEOUT(%ds)" % secs
    if "e" in box:
        return None, "%s: %s" % (type(box["e"]).__name__, str(box["e"])[:160])
    return box.get("r"), None


def http_post(sess, bld, params):
    p = dict(params); p["bld"] = bld
    try:
        r = sess.post(MDC, data=p, headers=HDR, timeout=TIMEOUT)   # ← timeout
        try: j = r.json()
        except Exception: j = None
        return r.status_code, j, r.text[:160]
    except Exception as e:
        return None, None, "%s: %s" % (type(e).__name__, str(e)[:140])


def rows_of(j):
    if isinstance(j, dict):
        for k in ("OutBlock_1", "OutBlock", "output", "block1"):
            if isinstance(j.get(k), list):
                return j[k]
        for v in j.values():
            if isinstance(v, list) and v:
                return v
    return None


def nbd():
    def _f():
        from pykrx import stock
        return stock.get_nearest_business_day_in_a_week(date.today().strftime("%Y%m%d"))
    v, err = with_timeout(_f, 10, "nbd")
    if v: return v
    d = date.today()
    while d.weekday() >= 5: d -= timedelta(days=1)
    return d.strftime("%Y%m%d")


def block(name, fn):
    """통계 블록을 try로 감싸 어떤 예외도 파일에 남기고 계속."""
    emit("\n[%s]" % name)
    try:
        fn()
    except Exception as e:
        emit("  ❌ 예외: %r" % e)


def main():
    bd = nbd()
    emit("=== KRX 탐색 시작 (기준일 %s) ===" % bd)
    emit("원칙: 공식 실데이터만. 실패=데이터부족. 가짜 금지. (MDC는 KRX 차단으로 ❌ 정상 가능)")

    import requests
    sess = requests.Session(); sess.headers.update(HDR)
    # 세션 쿠키 부트스트랩(타임아웃)
    try:
        sess.get("http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd",
                 params={"menuId": "MDC0201020101"}, timeout=TIMEOUT)
    except Exception as e:
        emit("  (세션 부트스트랩 경고: %s)" % str(e)[:100])
    emit("  세션 쿠키: %s" % (list(sess.cookies.keys()) or "없음"))

    tried = [0]
    spot = [None]; futc = [None]

    def b_vkospi():
        from pykrx import stock
        found = []
        for mkt in ["KOSPI", "KOSDAQ", "KRX", "테마"]:
            tried[0] += 1
            res, err = with_timeout(lambda m=mkt: [(c, stock.get_index_ticker_name(c))
                                                   for c in stock.get_index_ticker_list(bd, m)], 12)
            if err:
                emit("  %s 목록: ❌ %s" % (mkt, err)); continue
            for c, nm in (res or []):
                if "변동성" in nm or "VKOSPI" in nm.upper():
                    found.append((mkt, c, nm))
        emit("  변동성 지수: %s" % (found if found else "없음(pykrx 목록에 부재 → 정식 idx/drvprod_dd_trd)"))
    block("① VKOSPI (pykrx)", b_vkospi)

    def b_fut():
        from pykrx import stock
        fl, err = with_timeout(lambda: list(stock.get_future_ticker_list()), 12)
        tried[0] += 1
        if err: emit("  선물목록 ❌ %s" % err); return
        emit("  선물 티커 %d개: %s" % (len(fl or []), (fl or [])[:8]))
        if fl:
            df, err2 = with_timeout(lambda: stock.get_future_ohlcv(bd, bd, fl[0]), 12)
            if err2:
                emit("  get_future_ohlcv ❌ %s (pykrx 선물시세 미구현 알려짐)" % err2); return
            emit("  컬럼: %s · 행: %s" % (list(df.columns), df.tail(1).to_dict()))
            if "종가" in df.columns: futc[0] = float(df["종가"].iloc[-1])
    block("② 선물 (pykrx)", b_fut)

    def b_spot():
        from pykrx import stock
        df, err = with_timeout(lambda: stock.get_index_ohlcv(bd, bd, "1028"), 12)
        tried[0] += 1
        if err: emit("  현물 ❌ %s" % err); return
        spot[0] = float(df["종가"].iloc[-1]); emit("  KOSPI200 현물 종가 %.2f" % spot[0])
    block("③ KOSPI200 현물 (pykrx)", b_spot)

    def b_mdc():
        # OTP 1회 시도(필요한 bld 대비) — 받아지면 code 동봉, 아니면 그냥 진행
        otp = None
        try:
            r = sess.get(OTPGEN, params={"name": "fileDown", "filetype": "json"}, headers=HDR, timeout=TIMEOUT)
            otp = r.text.strip() if r.status_code == 200 and len(r.text) < 600 else None
            emit("  OTP: %s" % ("획득(%d자)" % len(otp) if otp else "미획득(getJsonData는 보통 OTP 불요)"))
        except Exception as e:
            emit("  OTP 시도 실패: %s" % str(e)[:80])
        for bld in ["dbms/MDC/STAT/standard/MDCSTAT12701", "dbms/MDC/STAT/standard/MDCSTAT12502"]:
            tried[0] += 1
            params = {"locale": "ko_KR", "trdDd": bd, "prodId": "KRDRVFUK2I", "csvxls_isNo": "false"}
            if otp: params["code"] = otp
            st, j, raw = http_post(sess, bld, params)
            rows = rows_of(j)
            emit("  bld=%s HTTP=%s raw=%s → %s" % (bld[-11:], st, raw[:50],
                  ("✅ rows=%d 컬럼=%s" % (len(rows), list(rows[0].keys())[:8])) if rows else "❌ 데이터부족"))
    block("④ MDC 투자자/옵션 (세션+OTP)", b_mdc)

    def b_basis():
        if spot[0] is not None and futc[0] is not None:
            emit("  ✅ 베이시스 %+.2f (현물 %.2f / 선물 %.2f)" % (futc[0]-spot[0], spot[0], futc[0]))
        else:
            emit("  ❌ 데이터부족(현물=%s 선물=%s)" % (spot[0], futc[0]))
    block("⑤ 베이시스", b_basis)

    emit("\n=== 끝, %d개 시도 ===" % tried[0])
    emit("권고: MDC 막힘 확정. 정식 경로 krx_openapi.py(인증키 승인 후)가 안정적.")


def selftest():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print("  [%s] %s" % ("OK" if c else "FAIL", n))
    v, err = with_timeout(lambda: 1 + 1, 5); chk("with_timeout 정상", v == 2 and err is None)
    v2, err2 = with_timeout(lambda: __import__("time").sleep(3), 1); chk("with_timeout 끊김", err2 and "TIMEOUT" in err2)
    chk("rows_of OutBlock", rows_of({"OutBlock_1": [{"a": 1}]}) == [{"a": 1}])
    chk("rows_of None", rows_of({"x": 1}) is None)
    print("self-test: %d/%d" % (ok, tot)); return ok == tot


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        try:
            _LOG = open(BASE / "krx_deriv_결과.txt", "w", encoding="utf-8")   # ← 시작 시 열기
        except Exception as e:
            print("로그 열기 실패:", e); _LOG = None
        try:
            main()
        except Exception:
            emit("\n[치명 에러]")
            emit(traceback.format_exc())
        finally:
            if _LOG:
                _LOG.flush(); _LOG.close()
