#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kosdaq_preempt_scan_v1.py — 선반영(과열) 게이트 일괄 스캐너 (테마 lane 보조)
워치리스트+체인 종목 전체에 진입 게이트를 한 번에 적용 → "지금 들어가도 되나"를 종목별 PASS/LATE로.
production·C·D·영역3·v41·v42 무수정. 매수신호 아님 — 진입 보류 필터일 뿐.

게이트(선반영 rubric, 등록표와 동일):
  ① 12개월 수익 < +100%   (급등 선반영 아님)
  ② 현재가가 52주 고점 대비 −5% 밖 (prox<0.95, 고점 미근접)
  → 둘 다 PASS = 미과열(진입 여지) / 하나라도 LATE = 보류·"카탈리스트 남았나" 재확인.

데이터(샌드박스 가용): theme_daily.csv(워치 12종 장기) + leadlag_daily.csv(체인 종목).
  [PC] kospi_daily_panel.csv 있으면 자동 병합(더 많은 종목).
사용: python kosdaq_preempt_scan_v1.py [--selftest]
"""
import csv, sys
from datetime import date
from pathlib import Path
BASE = Path(__file__).parent.resolve()
LOOK = 252


def _d(s):
    y, m, dd = str(s)[:10].split("-"); return date(int(y), int(m), int(dd))


def load_universe():
    u = {}
    p = BASE / "kosdaq_theme_chain_map.csv"
    if p.exists():
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            if r.get("market") == "KOSDAQ":
                u[str(r["ticker"]).zfill(6)] = (r["name"], r.get("theme", ""))
    p = BASE / "kosdaq_theme_watchlist.csv"
    if p.exists():
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            c = str(r.get("code", "")).zfill(6)
            if c.strip("0"):
                u.setdefault(c, (r.get("name", c), r.get("theme", "")))
    return u


def load_prices():
    """{code: [(date, close)]} — theme_daily(long) + leadlag_daily(wide) 병합."""
    px = {}
    # long: code,date,open,high,low,close
    for fn in ("kosdaq_theme_daily.csv", "theme_daily.csv", "kospi_daily_panel.csv"):
        p = BASE / fn
        if not p.exists():
            continue
        rows = list(csv.reader(open(p, encoding="utf-8-sig")))
        hdr = rows[0]
        if hdr[:2] == ["code", "date"]:        # long
            ci = {h: i for i, h in enumerate(hdr)}
            for r in rows[1:]:
                try:
                    c = str(r[ci["code"]]).zfill(6); v = float(r[ci["close"]])
                    if v > 0: px.setdefault(c, []).append((_d(r[ci["date"]]), v))
                except (ValueError, IndexError): pass
        else:                                   # wide (Date + codes)
            for j, c in enumerate(hdr):
                if j == 0: continue
                cc = str(c).zfill(6)
                for r in rows[1:]:
                    try:
                        v = float(r[j])
                        if v > 0: px.setdefault(cc, []).append((_d(r[0]), v))
                    except (ValueError, IndexError): pass
    # wide: leadlag_daily
    p = BASE / "leadlag_daily.csv"
    if p.exists():
        rows = list(csv.reader(open(p, encoding="utf-8-sig"))); hdr = rows[0]
        for j, c in enumerate(hdr):
            if j == 0 or not str(c).isdigit(): continue
            cc = str(c).zfill(6)
            if cc in px: continue               # 이미 long에서 더 긴 이력 있으면 유지
            for r in rows[1:]:
                try:
                    v = float(r[j])
                    if v > 0: px.setdefault(cc, []).append((_d(r[0]), v))
                except (ValueError, IndexError): pass
    for c in px:
        px[c] = sorted(set(px[c]))
    return px


def gate(series, look=LOOK):
    """(r12, prox, pass, note) — None if 자료부족."""
    if not series or len(series) < look // 2:
        return None
    closes = [c for _, c in series]
    last = closes[-1]
    base = closes[max(0, len(closes) - look - 1)]
    r12 = last / base - 1 if base > 0 else None
    hi = max(closes[-look:])
    prox = last / hi if hi > 0 else None
    if r12 is None or prox is None:
        return None
    g1 = r12 < 1.00
    g2 = prox < 0.95
    note = "소외(역발상)" if r12 < 0 else ("미과열" if (g1 and g2) else "과열")
    return (r12, prox, g1 and g2, g1, g2, note)


def main():
    u = load_universe()
    px = load_prices()
    rows = []
    for code, (name, theme) in u.items():
        g = gate(px.get(code))
        if g is None:
            rows.append((name, theme, None, None, None, None, None, "자료부족"))
        else:
            r12, prox, ok, g1, g2, note = g
            rows.append((name, theme, r12 * 100, (prox - 1) * 100, ok, g1, g2, note))
    # PASS 먼저 → 고점대비 낮은(여지 큰) 순
    rows.sort(key=lambda x: (x[4] is not True, (x[3] if x[3] is not None else 9e9)))
    print("=== 선반영 게이트 일괄 스캔 — 대상 %d종 (PASS=미과열·진입여지 / LATE=보류) ===" % len(u))
    print("게이트: ①12M<+100%% ②고점대비<−5%%(미근접). 둘 다=PASS. 매수신호 아님·매수일 재확인.\n")
    print("종목          | 테마        | 12M%   | 고점대비% | 게이트 | 메모")
    npass = 0
    for name, theme, r12, pd_, ok, g1, g2, note in rows:
        if r12 is None:
            print("  %-12s | %-10s | %6s | %8s | %-5s | %s" % (name[:12], theme[:10], "-", "-", "자료없음", note)); continue
        mark = "✅PASS" if ok else "❌LATE"
        npass += 1 if ok else 0
        flags = ("①%s②%s" % ("O" if g1 else "X", "O" if g2 else "X"))
        print("  %-12s | %-10s | %+5.1f | %+7.1f | %s | %s %s" % (name[:12], theme[:10], r12, pd_, mark, note, flags))
    print("\n✅ 미과열(진입 여지) %d종 / 대상 %d종. (다음: catalyst_scan·news_scan으로 '촉매 2+ 점등' 교차 → thesis 등록)" % (npass, len(u)))


def selftest():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print("  [%s] %s" % ("OK" if c else "FAIL", n))
    import datetime as dt
    rise = [(date(2025, 1, 1) + dt.timedelta(days=i), 100.0 + i * 0.3) for i in range(200)]      # +60%·신고가
    g = gate(rise)  # 튜플=(r12,prox,pass,g1,g2,note)
    chk("완만상승+신고가 → 게이트①O·②X·전체LATE", g is not None and g[3] is True and g[4] is False and g[2] is False)
    moderate = [(date(2025, 1, 1) + dt.timedelta(days=i), 100.0 + i * 0.3) for i in range(180)] + \
               [(date(2025, 1, 1) + dt.timedelta(days=180 + i), 154.0 - i * 0.7) for i in range(30)]  # 올랐다 −12% 눌림
    g2 = gate(moderate)
    chk("상승후 −12%% 눌림 → PASS(미과열)", g2 is not None and g2[2] is True)
    boom = [(date(2025, 1, 1) + dt.timedelta(days=i), 100.0 * (1 + 2.0 * i / 200)) for i in range(200)]  # +200%
    g3 = gate(boom)
    chk("급등 +200% → 게이트① LATE", g3 is not None and g3[3] is False)
    chk("자료부족 → None", gate([(date(2025, 1, 1), 100.0)]) is None)
    print("self-test: %d/%d" % (ok, tot)); return ok == tot


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        try: main()
        except Exception:
            import traceback; print("\n[에러]"); traceback.print_exc()
