#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
jq_breadth.py — 시장 폭/쏠림 지표 생성기 (객관 수치·측정용, 예측신호 아님)
입력: kosdaq_theme_daily.csv (테마 34종 + 지수). 지수(KS11/KQ11)는 제외, 개별종목으로 계산.
지표: ①분산도(횡단면 σ) ②평균 페어와이즈 상관(롤링) ③Breadth(MA20/MA60 위 비율·상승비율) ④집중도(상위5 기여)
→ 장세 분류: 🎯쏠림(테마) / 🌊광범위 상승 / 🐻약세 + 함의 1줄.
연결: 진우퀀트_시장스냅샷.md(월1행 append) · 의사결정 보드 F섹션(compute_breadth import).
원칙: 측정·맥락 인지용. 예측 채택은 백테스트 후. production·기존 무수정.
선행: fetch_kosdaq_daily_panel.py  사용: python jq_breadth.py | --selftest
"""
import csv, sys
from datetime import date
from pathlib import Path
BASE = Path(__file__).parent.resolve()
INDEX = {"KS11", "KQ11"}


def _d(s):
    y, m, dd = str(s)[:10].split("-"); return date(int(y), int(m), int(dd))


def load_closes(path="kosdaq_theme_daily.csv"):
    px = {}
    p = BASE / path
    if not p.exists():
        return px
    for r in csv.DictReader(open(p, encoding="utf-8-sig")):
        c = str(r.get("code"))
        if c in INDEX:
            continue
        try:
            px.setdefault(c, []).append((_d(r["date"]), float(r["close"])))
        except (ValueError, KeyError):
            pass
    return {c: [v for _, v in sorted(s)] for c, s in px.items() if len(s) >= 61}


def _ret(series, n):
    if len(series) < n + 1 or series[-n-1] <= 0:
        return None
    return series[-1] / series[-n-1] - 1


def _std(xs):
    xs = [x for x in xs if x is not None]
    if len(xs) < 2:
        return None
    m = sum(xs) / len(xs)
    return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5


def _corr(a, b):
    n = min(len(a), len(b))
    a, b = a[-n:], b[-n:]
    ma, mb = sum(a)/n, sum(b)/n
    va = sum((x-ma)**2 for x in a); vb = sum((x-mb)**2 for x in b)
    if va <= 0 or vb <= 0:
        return None
    cov = sum((a[i]-ma)*(b[i]-mb) for i in range(n))
    return cov / (va**0.5 * vb**0.5)


def compute(px):
    codes = list(px)
    # 횡단면 수익률 분산도(20일·월간≈20)
    r20 = {c: _ret(px[c], 20) for c in codes}
    disp20 = _std(list(r20.values()))
    r60 = {c: _ret(px[c], 60) for c in codes}
    disp60 = _std(list(r60.values()))
    # 평균 페어와이즈 상관(최근 60일 일수익)
    dret = {}
    for c in codes:
        s = px[c]
        dret[c] = [s[i]/s[i-1]-1 for i in range(len(s)-60, len(s))]
    cs, vals = list(dret), []
    for i in range(len(cs)):
        for j in range(i+1, len(cs)):
            cc = _corr(dret[cs[i]], dret[cs[j]])
            if cc is not None:
                vals.append(cc)
    avg_corr = sum(vals)/len(vals) if vals else None
    # breadth
    def above_ma(n):
        cnt = tot = 0
        for c in codes:
            s = px[c]
            if len(s) >= n:
                tot += 1; cnt += 1 if s[-1] > sum(s[-n:])/n else 0
        return cnt/tot*100 if tot else None
    ma20 = above_ma(20); ma60 = above_ma(60)
    up20 = sum(1 for c in codes if (r20[c] or 0) > 0) / len(codes) * 100
    # 집중도: 상위5 20일수익 평균 vs 전체 평균
    rr = sorted((v for v in r20.values() if v is not None), reverse=True)
    top5 = sum(rr[:5])/min(5, len(rr)) if rr else None
    allm = sum(rr)/len(rr) if rr else None
    spread = (top5 - allm) * 100 if (top5 is not None and allm is not None) else None
    return {"n": len(codes), "disp20": disp20, "disp60": disp60, "avg_corr": avg_corr,
            "ma20": ma20, "ma60": ma60, "up20": up20, "top5_ret": top5, "spread_top5": spread,
            "all_ret": allm}


def classify(m):
    """객관 임계(a-priori, 튜닝 X). 분산↑·상관↓·breadth↓=쏠림 / 분산↓·상관↑·breadth↑=광범위 / breadth매우낮음=약세."""
    ma20, ac, dp = m["ma20"], m["avg_corr"], m["disp20"]
    if ma20 is not None and ma20 < 30:
        return "🐻", "약세", "방어적 환경 — 테마 신규 진입 보류·손절선 우선. 시스템은 MA200 룰대로."
    score_theme = 0
    if dp is not None and dp > 0.25: score_theme += 1          # 횡단면 분산 큼
    if ac is not None and ac < 0.35: score_theme += 1          # 상관 낮음(각자 따로)
    if ma20 is not None and ma20 < 55: score_theme += 1        # breadth 중하
    if score_theme >= 2:
        return "🎯", "쏠림(테마)", "테마 lane 우호 — 특정 테마만 가는 장. 선반영 게이트로 안 추격 + 촉매 종목만."
    return "🌊", "광범위 상승", "시스템(분산) 우호 — 대부분 같이 감. 굳이 테마 집중보다 본체 분산이 유리."


def fmt(m):
    def p(x, suf="%"):
        return ("%.1f%s" % (x*100 if suf=="%" and abs(x)<3 else x, suf)) if x is not None else "N/A"
    emoji, name, imp = classify(m)
    L = []
    L.append("- 분산도(20일 횡단면σ) **%s** · (60일) %s" % (
        ("%.1f%%" % (m["disp20"]*100)) if m["disp20"] is not None else "N/A",
        ("%.1f%%" % (m["disp60"]*100)) if m["disp60"] is not None else "N/A"))
    L.append("- 평균 페어 상관(60일) **%s**" % (("%.2f" % m["avg_corr"]) if m["avg_corr"] is not None else "N/A"))
    L.append("- Breadth: MA20 위 **%s** · MA60 위 %s · 20일 상승 %s" % (
        ("%.0f%%" % m["ma20"]) if m["ma20"] is not None else "N/A",
        ("%.0f%%" % m["ma60"]) if m["ma60"] is not None else "N/A",
        ("%.0f%%" % m["up20"]) if m["up20"] is not None else "N/A"))
    L.append("- 집중도: 상위5 평균수익 %s vs 전체 %s (격차 %s)" % (
        ("%+.0f%%" % (m["top5_ret"]*100)) if m["top5_ret"] is not None else "N/A",
        ("%+.0f%%" % (m["all_ret"]*100)) if m["all_ret"] is not None else "N/A",
        ("%+.0f%%p" % m["spread_top5"]) if m["spread_top5"] is not None else "N/A"))
    L.append("- **장세: %s %s** — %s" % (emoji, name, imp))
    return emoji, name, L


def append_snapshot(m):
    """시장스냅샷 보조 feature CSV에 1행 append (md 본문은 사람용 유지)."""
    f = BASE / "breadth_features.csv"
    new = not f.exists()
    today = date.today()
    emoji, name, _ = fmt(m)
    cols = ["date", "n", "disp20", "disp60", "avg_corr", "ma20", "ma60", "up20", "spread_top5", "regime"]
    row = [str(today), m["n"],
           round(m["disp20"], 4) if m["disp20"] else "", round(m["disp60"], 4) if m["disp60"] else "",
           round(m["avg_corr"], 3) if m["avg_corr"] is not None else "",
           round(m["ma20"], 1) if m["ma20"] is not None else "", round(m["ma60"], 1) if m["ma60"] is not None else "",
           round(m["up20"], 1), round(m["spread_top5"], 2) if m["spread_top5"] is not None else "", name]
    if not new:
        seen = [r["date"] for r in csv.DictReader(open(f, encoding="utf-8-sig"))]
        if str(today) in seen:
            return
    w = csv.writer(open(f, "a", encoding="utf-8-sig", newline=""))
    if new: w.writerow(cols)
    w.writerow(row)


def main():
    px = load_closes()
    if len(px) < 5:
        print("  [중단] 종목 시세 부족 — fetch_kosdaq_daily_panel.py 먼저."); return
    m = compute(px)
    emoji, name, L = fmt(m)
    print("=== 시장 폭/쏠림 지표 (테마 %d종, 측정용·예측 아님) ===" % m["n"])
    print("\n".join(L))
    append_snapshot(m)
    print("\n  [기록] breadth_features.csv 에 1행 추가(월 누적 feature)")
    return m


def selftest():
    import random
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print("  [%s] %s" % ("OK" if c else "FAIL", n))
    random.seed(1)
    # 광범위 상승(공통 시장요인 + 소량 노이즈): 상관↑ breadth↑
    days = 80
    mkt = [random.gauss(0.006, 0.012) for _ in range(days)]
    px_up = {}
    for i in range(10):
        ser = [100.0]
        for t in range(days):
            ser.append(ser[-1] * (1 + mkt[t] + random.gauss(0, 0.002)))
        px_up["c%d" % i] = ser
    m1 = compute(px_up)
    chk("광범위: breadth MA20 높음", m1["ma20"] is not None and m1["ma20"] > 60)
    chk("광범위: 평균상관 높음", m1["avg_corr"] is not None and m1["avg_corr"] > 0.5)
    chk("광범위 분류=🌊", classify(m1)[0] == "🌊")
    # 약세: 대부분 하락
    px_dn = {("c%d" % i): [100.0*(1-0.005*j) for j in range(81)] for i in range(10)}
    m2 = compute(px_dn)
    chk("약세: breadth MA20 매우낮음", m2["ma20"] is not None and m2["ma20"] < 30)
    chk("약세 분류=🐻", classify(m2)[0] == "🐻")
    chk("지표 키 존재", all(k in m1 for k in ("disp20","avg_corr","ma20","spread_top5")))
    print("self-test: %d/%d" % (ok, tot)); return ok == tot


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        try: main()
        except Exception:
            import traceback; print("\n[에러]"); traceback.print_exc()
