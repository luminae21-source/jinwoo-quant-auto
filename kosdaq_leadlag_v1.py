#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kosdaq_leadlag_v1.py — 테마 리드-래그 + 미국장 거시 감지기 (v1)
테마 lane forward 신호 'B 확산' 레이어. 3계층 체인:
  Tier0 미국/거시(연료) → Tier1 한국 대장 → Tier2 한국 peer(코스닥 소부장)
신호(따라잡기 후보) = 美연료 ON + 대장 상승 + peer 아직 미반영(lagging) + peer 비-선반영.
무수정: production·C·D·영역3·v41 일절 손대지 않음. 발굴 보조툴 — 매수신호 아님.

사용:
  python kosdaq_leadlag_v1.py --self-test     # 오프라인 로직 점검(네트워크 불요)
  python kosdaq_leadlag_v1.py --fetch         # [PC] 맵 티커 일봉 수집 → leadlag_daily.csv (FDR 필요)
  python kosdaq_leadlag_v1.py                  # leadlag_daily.csv + 맵 → 후보 출력
입력: kosdaq_theme_chain_map.csv, leadlag_daily.csv(Date + 티커 일봉 종가)
"""
import csv, sys

MAP = "kosdaq_theme_chain_map.csv"
PANEL = "leadlag_daily.csv"
LOOK = 20          # 최근 거래일(≈1개월)
FUEL_MIN = 0.0     # 美 연료: 최근 LOOK 수익률 ≥0 이면 ON
LEAD_MIN = 0.10    # 대장 +10%↑ = 테마 가동
LAG_GAP = 0.15     # peer가 대장보다 15%p 이상 뒤처지면 lagging
LATE_CAP = 1.0     # peer 최근 LOOK 수익률 >100% = 이미 급등(선반영) → 제외


def load_map(p=MAP):
    themes = {}
    for r in csv.DictReader(open(p, encoding="utf-8-sig")):
        themes.setdefault(r["theme"], {"0": [], "1": [], "2": []})
        themes[r["theme"]][r["tier"][0]].append(r)
    return themes


def load_panel(p=PANEL):
    rows = list(csv.reader(open(p, encoding="utf-8-sig")))
    cols = rows[0][1:]
    series = {c: [] for c in cols}
    for r in rows[1:]:
        for j, c in enumerate(cols, 1):
            try:
                series[c].append(float(r[j]))
            except (ValueError, IndexError):
                series[c].append(None)
    return series


def ret(series, key, look=LOOK):
    s = series.get(key)
    if not s:
        return None
    s = [x for x in s if x is not None]
    if len(s) < 2:
        return None
    a = s[-look - 1] if len(s) >= look + 1 else s[0]
    b = s[-1]
    return (b / a - 1) if a and a > 0 else None


def _avg(xs):
    xs = [x for x in xs if x is not None]
    return (sum(xs) / len(xs)) if xs else None


def detect(themes, series):
    out = []
    for th, tiers in themes.items():
        fuel = _avg([ret(series, r["ticker"]) for r in tiers["0"]])
        lead = _avg([ret(series, r["ticker"]) for r in tiers["1"]])
        fuel_on = fuel is not None and fuel >= FUEL_MIN
        lead_on = lead is not None and lead >= LEAD_MIN
        for r in tiers["2"]:
            pr = ret(series, r["ticker"])
            if pr is None:
                continue
            lagging = lead is not None and (lead - pr) >= LAG_GAP
            not_late = pr <= LATE_CAP
            cand = fuel_on and lead_on and lagging and not_late
            out.append({"theme": th, "name": r["name"], "ticker": r["ticker"],
                        "fuel": fuel, "lead": lead, "peer": pr,
                        "gap": (lead - pr) if lead is not None else None,
                        "fuel_on": fuel_on, "lead_on": lead_on,
                        "lagging": lagging, "not_late": not_late, "cand": cand})
    return out


def main():
    themes = load_map()
    series = load_panel()
    res = detect(themes, series)
    res.sort(key=lambda d: (not d["cand"], d["theme"], -(d["gap"] if d["gap"] is not None else -9)))
    print("=== 테마 리드-래그 + 미국 연료 (후보 = 美연료ON·대장↑·peer 미반영·비선반영) ===")
    print("기준: 최근 %d거래일 | 연료≥%.0f%% | 대장≥%.0f%% | 갭≥%.0f%%p | 급등제외>%.0f%%"
          % (LOOK, FUEL_MIN * 100, LEAD_MIN * 100, LAG_GAP * 100, LATE_CAP * 100))
    cur = None
    for d in res:
        if d["theme"] != cur:
            cur = d["theme"]
            fs = ("%+.0f%%" % (d["fuel"] * 100)) if d["fuel"] is not None else "N/A"
            ls = ("%+.0f%%" % (d["lead"] * 100)) if d["lead"] is not None else "N/A"
            print("\n[%s] 美연료 %s %s | 대장 %s" % (cur, fs, "ON" if d["fuel_on"] else "off", ls))
        peer = ("%+.0f%%" % (d["peer"] * 100)) if d["peer"] is not None else "-"
        gap = ("%+.0f%%p" % (d["gap"] * 100)) if d["gap"] is not None else "-"
        print("  %s %-12s peer %7s (대장대비 %s)" % ("★후보" if d["cand"] else "    ", d["name"], peer, gap))
    n = sum(1 for d in res if d["cand"])
    print("\n★ 따라잡기 후보 %d건. (가드레일·thesis·무효화 별도 — 매수신호 아님)" % n)


def self_test():
    n = 20  # 21 포인트 → ret(look=20)이 전구간 수익 반영
    themes = {"테스트": {"0": [{"name": "US", "ticker": "US", "tier": "0"}],
                        "1": [{"name": "대장", "ticker": "L", "tier": "1"}],
                        "2": [{"name": "peerA", "ticker": "A", "tier": "2"},
                              {"name": "peerB", "ticker": "B", "tier": "2"}]}}
    series = {"US": [100 * (1 + 0.10 * i / n) for i in range(n + 1)],   # +10% 연료 ON
              "L":  [100 * (1 + 0.30 * i / n) for i in range(n + 1)],   # 대장 +30%
              "A":  [100 * (1 + 0.05 * i / n) for i in range(n + 1)],   # peerA +5% (lagging)
              "B":  [100 * (1 + 1.20 * i / n) for i in range(n + 1)]}   # peerB +120% (급등=제외)
    res = detect(themes, series)
    a = [d for d in res if d["name"] == "peerA"][0]
    b = [d for d in res if d["name"] == "peerB"][0]
    ok = tot = 0
    def chk(name, c):
        nonlocal ok, tot
        tot += 1; ok += 1 if c else 0
        print("  [%s] %s" % ("OK" if c else "FAIL", name))
    chk("연료 ON 감지", a["fuel_on"] is True)
    chk("대장 ON 감지", a["lead_on"] is True)
    chk("peerA(lagging)=후보", a["cand"] is True)
    chk("peerB(급등>100%)=제외", b["cand"] is False)
    chk("peerB not_late=False", b["not_late"] is False)
    print("self-test: %d/%d" % (ok, tot))
    return ok == tot


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    elif "--fetch" in sys.argv:
        import FinanceDataReader as fdr
        import pandas as pd, datetime as dt
        themes = load_map()
        tickers = sorted({r["ticker"] for t in themes.values() for k in ("0", "1", "2") for r in t[k]})
        end = dt.date.today(); start = end - dt.timedelta(days=400)
        df = pd.DataFrame()
        for tk in tickers:
            try:
                s = fdr.DataReader(tk, start, end)["Close"].rename(tk)
                df = pd.concat([df, s], axis=1); print("fetched", tk)
            except Exception as e:
                print("FAIL", tk, e)
        df.index.name = "Date"
        df.to_csv("leadlag_daily.csv", encoding="utf-8-sig")
        print("저장: leadlag_daily.csv", df.shape)
    else:
        main()
