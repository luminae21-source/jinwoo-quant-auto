#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
만기후_체크.py — 파생 만기 '후' 사후채점 (만기효과 실측·누적)
==============================================================================
목적: 정규 만기(둘째 목) 직후, 만기 주·당일·다음날 지수가 실제로 어떻게 움직였는지
      실데이터로 기록·누적 → 파생만기_스터디.md의 "만기효과" 가설을 사후 검증.
      ⚠️ 예측 아님 — 사후 측정. 집행·판단은 진우.
실행 로직: '직전 7일 내 정규 만기가 있었을 때만' 채점(없으면 조용히 skip).
          → 작업 스케줄러에 매주 금 등록하면 둘째 금(만기 다음날)에만 실제 채점됨.
데이터: yfinance ^KS11(코스피)·^KQ11(코스닥) 우선 → pykrx 지수 백업. 실데이터만, 없으면 "데이터부족".
산출: 만기후체크_log.csv (누적 1행/만기) · 만기후체크_YYYY-MM-DD.md · 콘솔
사용: python 만기후_체크.py [--selftest] [--force YYYY-MM-DD(특정 만기 강제채점)]
무수정: production·기존 산출물. 신규.
"""
import os, sys, csv, argparse
from datetime import date, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
HERE = os.path.dirname(os.path.abspath(__file__))


def second_thursday(y, m):
    d = date(y, m, 1)
    first_thu = d + timedelta(days=(3 - d.weekday()) % 7)
    return first_thu + timedelta(days=7)


def recent_expiry(today, back=7):
    """today 기준 직전 back일 내 정규 만기(둘째 목)가 있으면 (날짜, 종류). 없으면 (None,None)."""
    for i in range(back + 1):
        d = today - timedelta(days=i)
        if d == second_thursday(d.year, d.month):
            kind = "분기 동시만기(네 마녀)" if d.month in (3, 6, 9, 12) else "옵션만기"
            return d, kind
    return None, None


def get_index(symbol):
    """지수 일별 종가 → dict{date: close}. yfinance(^KS11/^KQ11) 우선, pykrx 백업. 실패=None."""
    # 1) yfinance
    try:
        import yfinance as yf
        h = yf.Ticker(symbol).history(period="3mo")
        if h is not None and len(h) > 0:
            return {d.date(): float(c) for d, c in h["Close"].items()}
    except Exception:
        pass
    # 2) pykrx (^KS11→1001, ^KQ11→2001)
    try:
        from pykrx import stock
        code = {"^KS11": "1001", "^KQ11": "2001"}.get(symbol)
        if code:
            end = date.today().strftime("%Y%m%d")
            start = (date.today() - timedelta(days=120)).strftime("%Y%m%d")
            df = stock.get_index_ohlcv(start, end, code)
            if df is not None and len(df) > 0:
                return {idx.date(): float(c) for idx, c in df["종가"].items()}
    except Exception:
        pass
    return None


def _ordered(series):
    return sorted(series.items())  # [(date, close)] 정렬


def _ret_between(series, d_from, d_to):
    """d_from 이하 마지막 종가 → d_to 이하 마지막 종가 수익률%. 데이터 없으면 None."""
    od = _ordered(series)
    def last_on_or_before(dd):
        v = None
        for d, c in od:
            if d <= dd:
                v = c
            else:
                break
        return v
    a = last_on_or_before(d_from); b = last_on_or_before(d_to)
    if a is None or b is None or a <= 0:
        return None
    return (b / a - 1) * 100


def _day_ret(series, d):
    """d 당일 등락%(직전 거래일 대비). 없으면 None."""
    od = _ordered(series)
    prev = cur = None
    for dt, c in od:
        if dt <= d:
            prev = cur; cur = c
        else:
            break
    # cur = d 이하 마지막, prev = 그 직전
    if cur is None or prev is None or prev <= 0:
        return None
    return (cur / prev - 1) * 100


def score(expiry, ks, kq):
    """만기 주(만기−7일~만기)·당일·후2일 지수 변동. → dict."""
    wk_from = expiry - timedelta(days=7)
    post = expiry + timedelta(days=4)   # 만기+영업일 2~3 포함
    out = {}
    for label, s in (("ks", ks), ("kq", kq)):
        if not s:
            out[label] = None; continue
        out[label] = {
            "week": _ret_between(s, wk_from, expiry),   # 만기 주 누적
            "day": _day_ret(s, expiry),                 # 만기 당일
            "post": _ret_between(s, expiry, post),      # 만기 후 되돌림
        }
    return out


def interpret(sc):
    """룰 기반 한 줄(임의해석 X). 만기일 급변 + 후 되돌림 패턴 표기."""
    ks = sc.get("ks")
    if not ks or ks["day"] is None:
        return "데이터부족 — 해석 보류"
    bits = []
    bits.append("만기일 급변(±1%↑)" if abs(ks["day"]) >= 1.0 else "만기일 변동 제한적")
    wk, po = ks.get("week"), ks.get("post")
    # 만기 전(주) ↔ 만기 후 반전 = 만기효과 전형(차익청산→해소 되돌림)
    if wk is not None and po is not None and wk * po < 0 and abs(wk) >= 2 and abs(po) >= 2:
        bits.append("만기 전 급변→후 되돌림(만기효과 전형)")
    elif ks["day"] is not None and po is not None and ks["day"] * po < 0 and abs(po) >= 1.0:
        bits.append("만기 후 되돌림(반대방향)")
    elif po is not None and abs(po) >= 1.0:
        bits.append("만기 후 추세 지속")
    return " · ".join(bits)


def run(force=None):
    today = date.today()
    if force:
        exp = date.fromisoformat(force)
        kind = "분기 동시만기(네 마녀)" if exp.month in (3, 6, 9, 12) else "옵션만기"
    else:
        exp, kind = recent_expiry(today)
    if not exp:
        print("최근 7일 내 정규 만기 없음 — 사후채점 skip (만기 다음날에만 실행됨)."); return None
    ks = get_index("^KS11"); kq = get_index("^KQ11")
    if not ks and not kq:
        print("❌ 데이터부족 — 지수 시세 수신 실패(yfinance/pykrx)."); return None
    sc = score(exp, ks, kq)
    note = interpret(sc)
    def f(v): return "데이터부족" if v is None else ("%+.2f%%" % v)
    lines = [f"# 만기 후 체크 — {exp} {kind}", "",
             "> 만기효과 사후 측정(실데이터). 예측 아님. 파생만기_스터디.md 검증용.", "",
             f"- 채점 실행일: {today}",
             f"- **코스피**: 만기주 {f(sc['ks']['week']) if sc['ks'] else '데이터부족'} · 만기일 {f(sc['ks']['day']) if sc['ks'] else '데이터부족'} · 만기후 {f(sc['ks']['post']) if sc['ks'] else '데이터부족'}",
             f"- **코스닥**: 만기주 {f(sc['kq']['week']) if sc['kq'] else '데이터부족'} · 만기일 {f(sc['kq']['day']) if sc['kq'] else '데이터부족'} · 만기후 {f(sc['kq']['post']) if sc['kq'] else '데이터부족'}",
             f"- 해석(룰): **{note}**", "",
             "*만기주=만기−7일~만기 / 만기일=당일등락 / 만기후=만기~+영업일2~3. 수치 HTS 최종확인.*"]
    md = "\n".join(lines)
    open(os.path.join(HERE, f"만기후체크_{today}.md"), "w", encoding="utf-8").write(md)
    # 로그 누적(만기일당 1행, 중복 방지)
    logp = os.path.join(HERE, "만기후체크_log.csv")
    cols = ["expiry", "kind", "checked", "ks_week", "ks_day", "ks_post", "kq_week", "kq_day", "kq_post", "note"]
    seen = set()
    if os.path.exists(logp):
        for r in csv.DictReader(open(logp, encoding="utf-8-sig")):
            seen.add(r.get("expiry"))
    row = [str(exp), kind, str(today),
           sc["ks"]["week"] if sc["ks"] else "", sc["ks"]["day"] if sc["ks"] else "", sc["ks"]["post"] if sc["ks"] else "",
           sc["kq"]["week"] if sc["kq"] else "", sc["kq"]["day"] if sc["kq"] else "", sc["kq"]["post"] if sc["kq"] else "", note]
    if str(exp) not in seen:
        new = not os.path.exists(logp)
        w = csv.writer(open(logp, "a", encoding="utf-8-sig", newline=""))
        if new: w.writerow(cols)
        w.writerow(row)
    print(md)
    print(f"\n[기록] 만기후체크_log.csv · 만기후체크_{today}.md")
    return sc


def _selftest():
    ok = 0
    def chk(n, c):
        nonlocal ok; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    # 9/10 = 9월 둘째목(네마녀)
    chk("9월 둘째목=9/10", second_thursday(2026, 9) == date(2026, 9, 10))
    # 9/11(금)에 실행 → 직전 만기 9/10 잡힘
    e, k = recent_expiry(date(2026, 9, 11))
    chk("만기다음날 채점대상", e == date(2026, 9, 10) and "네 마녀" in k)
    # 평범한 날(만기 없음) → skip
    e2, _ = recent_expiry(date(2026, 9, 25))
    chk("비만기일 skip", e2 is None)
    # 수익률 계산
    s = {date(2026, 9, 3): 100.0, date(2026, 9, 10): 105.0, date(2026, 9, 11): 103.0}
    chk("만기주 +5%", abs(_ret_between(s, date(2026, 9, 3), date(2026, 9, 10)) - 5.0) < 1e-9)
    chk("만기일 당일등락", _day_ret(s, date(2026, 9, 10)) is not None)
    chk("만기후 되돌림(-)", _ret_between(s, date(2026, 9, 10), date(2026, 9, 11)) < 0)
    # 해석 룰: 만기주 급락 + 만기후 급반등 = 만기효과 되돌림 (6/11 케이스)
    sc = {"ks": {"week": -10.0, "day": 0.4, "post": 10.0}, "kq": None}
    chk("해석=만기효과 되돌림", "되돌림" in interpret(sc) and "제한적" in interpret(sc))
    print(f"✅ 만기후_체크 셀프테스트 ({ok}/7)")
    return ok == 7


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--force", help="특정 만기일 강제채점 YYYY-MM-DD")
    a = ap.parse_args()
    if a.selftest:
        _selftest(); return
    run(force=a.force)


if __name__ == "__main__":
    main()
