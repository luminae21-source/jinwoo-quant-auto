#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
만기효과_백테스트.py — 과거 5~10년 정규 만기(둘째 목) 전후 지수 움직임 통계 검증
==============================================================================
목적: "만기 전 약세 · 만기일 변동성↑ · 만기 후 되돌림"이 통계적으로 실재하는가?
      과거 모든 둘째목 만기를 거래일 기준으로 채점 → 평균·표준편차·되돌림빈도·t값.
      동시만기(분기 3·6·9·12월=네 마녀) vs 월물 분리. ⚠️ forward 예측 아님, 과거 측정.
데이터: pykrx 지수(1001 코스피·2001 코스닥) 우선 → yfinance(^KS11/^KQ11) 백업. 실데이터만.
정의(거래일 기준): 만기주=만기−5거래일→만기 / 만기일=당일등락 / 만기후=만기→+3거래일.
산출: 만기효과_백테스트_결과.md · 만기효과_백테스트_raw.csv · 콘솔
사용: python 만기효과_백테스트.py [--years 10] [--selftest]
무수정: production·기존 산출물. 신규(측정·통계 검증용).
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


def all_expiries(years, today=None):
    """오늘 기준 과거 years년(일수 기준)의 매월 둘째목 만기일 리스트(과거만)."""
    today = today or date.today()
    cutoff = today - timedelta(days=365 * years)
    out = []
    for y in range(cutoff.year, today.year + 1):
        for m in range(1, 13):
            e = second_thursday(y, m)
            if cutoff <= e <= today:
                out.append(e)
    return out


def get_index_hist(symbol, years):
    """지수 일별 종가 → 정렬 [(date, close)]. pykrx 우선, yfinance 백업. 실패=[]."""
    # pykrx
    try:
        from pykrx import stock
        code = {"^KS11": "1001", "^KQ11": "2001"}.get(symbol)
        if code:
            end = date.today().strftime("%Y%m%d")
            start = (date.today() - timedelta(days=365 * years + 40)).strftime("%Y%m%d")
            df = stock.get_index_ohlcv(start, end, code)
            if df is not None and len(df) > 0:
                return sorted((idx.date(), float(c)) for idx, c in df["종가"].items())
    except Exception:
        pass
    # yfinance
    try:
        import yfinance as yf
        h = yf.Ticker(symbol).history(period=f"{years}y")
        if h is not None and len(h) > 0:
            return sorted((d.date(), float(c)) for d, c in h["Close"].items())
    except Exception:
        pass
    return []


def _idx_on_or_before(od, d):
    """정렬 [(date,close)]에서 d 이하 마지막 위치 인덱스. 없으면 None."""
    lo, hi, ans = 0, len(od) - 1, None
    while lo <= hi:
        mid = (lo + hi) // 2
        if od[mid][0] <= d:
            ans = mid; lo = mid + 1
        else:
            hi = mid - 1
    return ans


def score_expiry(od, expiry):
    """거래일 기준 만기주(−5)·만기일·만기후(+3) 수익률%. → dict or None."""
    i = _idx_on_or_before(od, expiry)
    if i is None or i < 5 or i + 3 >= len(od):
        return None
    c = lambda k: od[k][1]
    if c(i - 5) <= 0 or c(i - 1) <= 0 or c(i) <= 0:
        return None
    return {
        "week": (c(i) / c(i - 5) - 1) * 100,        # 만기주(직전 5거래일→만기)
        "day": (c(i) / c(i - 1) - 1) * 100,          # 만기 당일
        "post": (c(i + 3) / c(i) - 1) * 100,         # 만기 후 3거래일
    }


def _mean(xs): return sum(xs) / len(xs) if xs else None
def _std(xs):
    if len(xs) < 2: return None
    m = _mean(xs); return (sum((x - m) ** 2 for x in xs) / (len(xs) - 1)) ** 0.5
def _tstat(xs):
    """평균이 0과 다른지 t = mean/(std/√n)."""
    if len(xs) < 2: return None
    m, s = _mean(xs), _std(xs)
    return m / (s / len(xs) ** 0.5) if s and s > 0 else None


def summarize(rows, label):
    """rows=[dict(week,day,post)] → 통계 dict."""
    if not rows:
        return None
    wk = [r["week"] for r in rows]; dy = [r["day"] for r in rows]; po = [r["post"] for r in rows]
    rev = sum(1 for r in rows if r["week"] * r["post"] < 0) / len(rows) * 100   # 되돌림 비율
    return {"label": label, "n": len(rows),
            "week_mean": _mean(wk), "week_t": _tstat(wk), "week_neg": sum(1 for x in wk if x < 0) / len(wk) * 100,
            "day_absmean": _mean([abs(x) for x in dy]), "day_mean": _mean(dy),
            "post_mean": _mean(po), "post_t": _tstat(po), "reversal_pct": rev}


def run(years=10):
    today = date.today()
    exps = all_expiries(years, today)
    out = {}
    for sym, name in (("^KS11", "코스피"), ("^KQ11", "코스닥")):
        od = get_index_hist(sym, years)
        if not od:
            out[name] = None; continue
        baseline = []  # 평상시 일변동(만기일 변동성 비교용)
        for k in range(1, len(od)):
            if od[k - 1][1] > 0:
                baseline.append(abs(od[k][1] / od[k - 1][1] - 1) * 100)
        rows, quad, monthly, raw = [], [], [], []
        for e in exps:
            sc = score_expiry(od, e)
            if sc is None:
                continue
            sc2 = dict(sc); sc2["expiry"] = e; sc2["quad"] = e.month in (3, 6, 9, 12)
            rows.append(sc); raw.append((name, e, sc, sc2["quad"]))
            (quad if sc2["quad"] else monthly).append(sc)
        out[name] = {"all": summarize(rows, "전체"), "quad": summarize(quad, "동시만기(네마녀)"),
                     "monthly": summarize(monthly, "월물"), "baseline_abs": _mean(baseline), "raw": raw}
    _write(out, years, today, exps)
    return out


def _fmt(v, suf="", n=2):
    return "N/A" if v is None else f"{v:+.{n}f}{suf}" if suf == "%" else f"{v:.{n}f}{suf}"


def _write(out, years, today, exps):
    L = [f"# 만기효과 백테스트 — 과거 {years}년 ({today})", "",
         "> 정규 만기(둘째 목) 전후 지수 통계. 거래일 기준: 만기주=−5d→만기 / 만기일=당일 / 만기후=만기→+3d.",
         "> ⚠️ 과거 측정·forward 예측 아님. |t|≥2 ≈ 통계적으로 0과 구분(유의).", "",
         f"- 대상 만기 후보: {len(exps)}건 ({exps[0]} ~ {exps[-1]})", ""]
    for name in ("코스피", "코스닥"):
        o = out.get(name)
        L.append(f"## {name}")
        if not o:
            L.append("- ❌ 데이터부족(지수 시세 수신 실패)\n"); continue
        L.append(f"- 평상시 일평균 |변동|: {_fmt(o['baseline_abs'],'%')}  (만기일 변동성 비교 기준)")
        L.append("")
        L.append("| 구분 | n | 만기주 평균(t) | 만기주 음수% | 만기일 평균\\|변동\\| | 만기후 평균(t) | 되돌림% |")
        L.append("|---|---|---|---|---|---|---|")
        for key in ("all", "quad", "monthly"):
            s = o[key]
            if not s:
                continue
            L.append(f"| {s['label']} | {s['n']} | {_fmt(s['week_mean'],'%')} (t={_fmt(s['week_t'],'',1)}) "
                     f"| {s['week_neg']:.0f}% | {_fmt(s['day_absmean'],'%')} "
                     f"| {_fmt(s['post_mean'],'%')} (t={_fmt(s['post_t'],'',1)}) | {s['reversal_pct']:.0f}% |")
        L.append("")
    L += ["## 읽는 법",
          "- **만기주 평균 음수 + |t|≥2** → '만기 전 약세'가 통계적으로 실재.",
          "- **만기일 평균|변동| > 평상시 |변동|** → 만기일 변동성↑ 실재.",
          "- **되돌림% > 55~60%** → '만기주와 만기후가 반대'(되돌림)가 우연 이상.",
          "- 동시만기(네마녀) vs 월물 차이도 비교. 효과 약하면 매매규칙 보강 보류(단순성 우선).",
          "", "*실데이터(pykrx/yfinance). 수치 HTS 교차확인. 결정·책임은 진우.*"]
    open(os.path.join(HERE, "만기효과_백테스트_결과.md"), "w", encoding="utf-8").write("\n".join(L))
    # raw csv
    with open(os.path.join(HERE, "만기효과_백테스트_raw.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(["index", "expiry", "quad", "week_%", "day_%", "post_%"])
        for name in ("코스피", "코스닥"):
            o = out.get(name)
            if not o: continue
            for nm, e, sc, q in o["raw"]:
                w.writerow([nm, e, q, round(sc["week"], 2), round(sc["day"], 2), round(sc["post"], 2)])
    print("\n".join(L))
    print("\n[산출] 만기효과_백테스트_결과.md · 만기효과_백테스트_raw.csv")


def _selftest():
    ok = 0
    def chk(n, c):
        nonlocal ok; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    chk("둘째목 9/10", second_thursday(2026, 9) == date(2026, 9, 10))
    exps = all_expiries(2, date(2026, 6, 29))
    chk("2년 만기≈24건", 22 <= len(exps) <= 26)
    chk("미래 만기 제외", all(e <= date(2026, 6, 29) for e in exps))
    # 합성 지수: 만기 전 하락→만기 후 상승 심기(되돌림 패턴)
    od = []
    base = date(2024, 1, 1); price = 100.0
    from datetime import timedelta as td
    d = base
    exp_set = set(all_expiries(2, date(2026, 6, 29)))
    for i in range(700):
        d2 = base + td(days=i)
        if d2.weekday() >= 5:
            continue
        # 만기 5거래일 전부터 하락, 만기 후 반등 (간단화: 만기 주 -, 직후 +)
        near = min((abs((d2 - e).days) for e in exp_set), default=99)
        drift = -0.004 if 0 < near <= 7 and d2 < min(exp_set, key=lambda e: abs((d2-e).days)) else 0.003
        price *= (1 + drift)
        od.append((d2, price))
    od.sort()
    sc = score_expiry(od, sorted(exp_set)[5])
    chk("score 구조", sc is not None and all(k in sc for k in ("week", "day", "post")))
    s = summarize([{"week": -3, "day": 0.2, "post": 3}, {"week": -2, "day": 0.1, "post": 2}], "t")
    chk("되돌림 100%", abs(s["reversal_pct"] - 100) < 1e-9)
    chk("만기주 음수%", s["week_neg"] == 100.0)
    chk("t값 계산", s["post_t"] is not None)
    print(f"✅ 만기효과_백테스트 셀프테스트 ({ok}/7)")
    return ok == 7


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest(); return
    run(years=a.years)


if __name__ == "__main__":
    main()
