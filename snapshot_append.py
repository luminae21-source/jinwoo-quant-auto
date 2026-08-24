#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
snapshot_append.py — 시장 스냅샷 객관지표 자동 1행 추가 (feature store)
kosdaq_theme_daily.csv(KS11=KOSPI·KQ11=KOSDAQ 포함)에서 매 실행 시 그 달 지표를 계산해
snapshot_features.csv 에 append. 12개월 누적 → 사전 합격선 백테스트(시장스냅샷 §녹여내기 원칙).
production·기존 산출물 무수정. 정보용 — 매수신호 아님. (수급·VKOSPI는 별도 소스 → 빈칸, 수기/후속.)
선행: fetch_kosdaq_daily_panel.py. 사용: python snapshot_append.py | --selftest
"""
import csv, sys
from datetime import date
from pathlib import Path
BASE = Path(__file__).parent.resolve()


def _d(s):
    y, m, dd = str(s)[:10].split("-"); return date(int(y), int(m), int(dd))


def load_series(code, path="kosdaq_theme_daily.csv"):
    out = []
    p = BASE / path
    if not p.exists():
        return out
    for r in csv.DictReader(open(p, encoding="utf-8-sig")):
        if str(r.get("code")) == code:
            try: out.append((_d(r["date"]), float(r["close"])))
            except (ValueError, KeyError): pass
    return sorted(out)


def month_end_closes(series):
    """{ (y,m): 그 달 마지막 종가 }"""
    me = {}
    for d, c in series:
        me[(d.year, d.month)] = c
    return me


def metrics(series):
    if len(series) < 20:
        return None
    closes = [c for _, c in series]
    last = closes[-1]
    me = month_end_closes(series)
    keys = sorted(me)
    mom = (me[keys[-1]] / me[keys[-2]] - 1) * 100 if len(keys) >= 2 else None
    sma200 = sum(closes[-200:]) / min(200, len(closes))
    vs_ma = (last / sma200 - 1) * 100
    hi = max(closes[-252:])
    dd = (last / hi - 1) * 100
    return {"close": round(last, 2),
            "mom%": round(mom, 2) if mom is not None else None,
            "vs_ma200%": round(vs_ma, 2),
            "dd_from_high%": round(dd, 2)}


def flags(today):
    exp = mpc = ""
    p = BASE / "theme_calendar_fixed.csv"
    if p.exists():
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            try: d = _d(r["date"])
            except (ValueError, KeyError): continue
            if d.year == today.year and d.month == today.month:
                ev = r.get("event", "")
                if "마녀" in ev or "만기" in ev: exp = r["date"]
                if "금통위" in ev: mpc = r["date"]
    return exp, mpc


def append_row():
    ks, kq = load_series("KS11"), load_series("KQ11")
    mk, mq = metrics(ks), metrics(kq)
    if not mk:
        print("  [중단] KS11 시세 부족 — fetch_kosdaq_daily_panel.py 먼저."); return
    today = ks[-1][0]
    exp, mpc = flags(today)
    row = {"date": str(today),
           "kospi_close": mk["close"], "kospi_mom%": mk["mom%"], "kospi_vs_ma200%": mk["vs_ma200%"], "kospi_dd%": mk["dd_from_high%"],
           "kosdaq_close": mq["close"] if mq else "", "kosdaq_mom%": mq["mom%"] if mq else "", "kosdaq_vs_ma200%": mq["vs_ma200%"] if mq else "", "kosdaq_dd%": mq["dd_from_high%"] if mq else "",
           "foreign_net": "", "inst_net": "", "vkospi": "",     # 별도 소스(후속)
           "expiry_flag": exp, "mpc_flag": mpc}
    f = BASE / "snapshot_features.csv"
    new = not f.exists()
    cols = list(row.keys())
    existing = []
    if not new:
        existing = [r["date"] for r in csv.DictReader(open(f, encoding="utf-8-sig"))]
    if str(today) in existing:
        print("  [스킵] %s 이미 기록됨." % today); return
    w = csv.writer(open(f, "a", encoding="utf-8-sig", newline=""))
    if new: w.writerow(cols)
    w.writerow([row[c] for c in cols])
    print("  [스냅샷] %s 추가 → snapshot_features.csv" % today)
    print("    KOSPI %s (월 %s%%, MA200 %s%%, 고점대비 %s%%) | KOSDAQ %s"
          % (mk["close"], mk["mom%"], mk["vs_ma200%"], mk["dd_from_high%"], mq["close"] if mq else "-"))


def selftest():
    import datetime as dt
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print("  [%s] %s" % ("OK" if c else "FAIL", n))
    s = [(date(2025, 1, 1) + dt.timedelta(days=i), 100.0 + i * 0.1) for i in range(260)]  # 우상향
    m = metrics(s)
    chk("지표 계산됨", m is not None and m["close"] > 100)
    chk("상승추세 MA200 위(+)", m["vs_ma200%"] > 0)
    chk("신고가 부근 낙폭≈0", m["dd_from_high%"] > -1)
    chk("자료부족 None", metrics([(date(2025,1,1),100.0)]) is None)
    me = month_end_closes(s)
    chk("월말종가 추출", len(me) >= 8)
    print("self-test: %d/%d" % (ok, tot)); return ok == tot


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        try: append_row()
        except Exception:
            import traceback; print("\n[에러]"); traceback.print_exc()
