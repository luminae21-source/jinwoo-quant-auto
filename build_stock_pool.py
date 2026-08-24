#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_stock_pool.py — 전 시장 스크리닝 + 점수 종목 풀 (rule30의 전 시장 확장)
==============================================================================
진우 종합: "유니버스를 쭉 스크리닝하고 종목 점수도 그대로 진행해서 종목 풀을 만들자."
배경(검증): 진입 타이밍 마법 룰은 없었고, 광범위 우량 universe + 점수가 시장초과(+11.8%p, backtest_entry_timing).
방법: 검증 엔진 `pit_universe_backtest.score_at`(F·Sloan·NOA·Mom12·BAB·Echo, production/rule30 동일)을
  **전 종목(584)**에 적용 → 테마(theme_classify 22그룹)·등급(grade)·F·12M초과·유동성(ADTV) 태깅 →
  품질(F≥6)·유동(ADTV 상위40%)·이력(≥12M) 필터 → 점수 내림차순 풀.
출력: stock_pool_latest.csv (전 항목, 엑셀 편집·정렬 가능) + dashboard_pool.html (테마별 상위) + 콘솔.
성격: rule30(KOSPI top-30)의 superset = **의사결정 보조 풀**(검증된 매수리스트 아님). production v3.7.2 무변경.
사용: python build_stock_pool.py [--fmin 6] [--liq 0.40]   /   --selftest
의존성: pit_universe_backtest, theme_classify
"""
import argparse, os, sys, html, datetime
import numpy as np, pandas as pd
import pit_universe_backtest as PB
import theme_classify as TC

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

F_MIN = 6
LIQ_PCT = 0.40
MIN_MONTHS = 12


def grade(score):
    if score >= 14: return "S+"
    if score >= 12: return "S"
    if score >= 9:  return "A"
    if score >= 6:  return "B"
    if score >= 3:  return "C"
    if score >= 0:  return "D"
    return "F"


def _load_adtv(files):
    adtv = {}
    for f in files:
        if os.path.exists(f):
            d = pd.read_csv(f, dtype={"code": str}); d["code"] = d["code"].str.zfill(6)
            for _, r in d.iterrows():
                if r["code"] not in adtv and pd.notna(r.get("adtv")):
                    adtv[r["code"]] = float(r["adtv"])
    return adtv


def build(panel, fund, fine, name, adtv, fmin=F_MIN, liq_pct=LIQ_PCT):
    prices = panel
    cols = list(prices.columns)
    months = list(prices.index); idx = len(months) - 1; yr = months[idx].year
    ret = prices.pct_change(); mkt = ret.mean(axis=1)
    pf = PB.piotroski(fund)
    sc = PB.score_at(idx, months, prices, mkt, cols, pf, yr)          # code → 종합점수
    fy = pf[pf.fiscal_year == yr - 1].set_index("code")["F"] if (pf.fiscal_year == yr - 1).any() \
        else pf.groupby("code")["F"].last()
    cm, _ = TC.coarse_map(fine, name)
    cur_by, cur_of = TC.load_theme_universe()
    adtv_pct = pd.Series(adtv).rank(pct=True)
    mc12 = float((1 + mkt.iloc[idx - 11:idx + 1]).prod() - 1)
    persist = prices.notna().sum()

    rows = []
    for c in sc.index:
        f = float(fy.get(c, np.nan))
        if pd.notna(f) and f < fmin:                 # 품질
            continue
        if adtv_pct.get(c, 0) < liq_pct:             # 유동성
            continue
        if persist.get(c, 0) < MIN_MONTHS:           # 이력
            continue
        p = prices[c]
        ex12 = (p.iloc[idx] / p.iloc[idx - 12] - 1 - mc12) if (idx >= 12 and pd.notna(p.iloc[idx - 12]) and p.iloc[idx - 12] > 0) else np.nan
        theme = cur_of[c][0] if c in cur_of else cm.get(c, "미분류")
        rows.append({"code": c, "name": name.get(c, c), "theme": theme,
                     "score": round(float(sc[c]), 2), "grade": grade(sc[c]),
                     "F": (None if pd.isna(f) else int(f)),
                     "ex12_pct": (None if pd.isna(ex12) else round(ex12, 3)),
                     "adtv_ek": round(adtv.get(c, 0) / 1e8, 0)})
    df = pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)
    df.insert(0, "rank", df.index + 1)
    return df, str(months[idx].date())


def render_html(df, dt, path="dashboard_pool.html"):
    def esc(x): return html.escape(str(x))
    gc = {"S+": "#16a34a", "S": "#22c55e", "A": "#0891b2", "B": "#64748b"}
    # 테마별 상위 카드 (ON 여부 무관, 점수 상위)
    cards = ""
    for th, g in df.groupby("theme"):
        top = g.head(6)
        rows = "".join(
            f"<tr><td>{int(r['rank'])}</td><td>{esc(r['name'])}</td>"
            f"<td style='text-align:center'><span class='b' style='background:{gc.get(r['grade'],'#475569')}'>{esc(r['grade'])}</span></td>"
            f"<td style='text-align:right'>{r['score']:.1f}</td>"
            f"<td style='text-align:center'>F{r['F'] if r['F'] is not None else '?'}</td>"
            f"<td style='text-align:right'>{('—' if r['ex12_pct'] is None else f'{r[chr(101)+chr(120)+chr(49)+chr(50)+chr(95)+chr(112)+chr(99)+chr(116)]:+.0%}')}</td></tr>"
            for _, r in top.iterrows())
        cards += (f"<div class='card'><div class='th'>{esc(th)} <span class='mut'>{len(g)}종</span></div>"
                  f"<table><tr><td>#</td><td>종목</td><td style='text-align:center'>등급</td>"
                  f"<td style='text-align:right'>점수</td><td style='text-align:center'>F</td>"
                  f"<td style='text-align:right'>12M초과</td></tr>{rows}</table></div>")
    out = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>종목 풀</title><style>
*{{box-sizing:border-box;margin:0}}body{{background:#0f172a;color:#e2e8f0;font-family:-apple-system,system-ui,sans-serif;padding:14px;max-width:820px;margin:0 auto}}
h1{{font-size:17px}}.sub{{color:#94a3b8;font-size:12px;margin-bottom:14px}}
.card{{background:#1e293b;border-radius:10px;padding:12px 14px;margin-bottom:10px}}
.th{{font-size:14px;font-weight:700;margin-bottom:6px}}.mut{{color:#94a3b8;font-size:12px;font-weight:400}}
table{{width:100%;border-collapse:collapse;font-size:13px}}td{{padding:5px 6px;border-bottom:1px solid #334155}}
.b{{color:#fff;padding:1px 6px;border-radius:5px;font-size:11px;font-weight:600}}
.note{{color:#64748b;font-size:11px;margin-top:14px;line-height:1.5}}
</style></head><body>
<h1>종목 풀 (전 시장 스크리닝 + 점수)</h1>
<div class="sub">기준 {dt} · {len(df)}종 (F≥{F_MIN}·유동상위{100-int(LIQ_PCT*100)}%) · 점수=production 엔진 · 테마별 상위 6</div>
{cards}
<div class="note">점수 = F·Sloan·NOA·Mom12·BAB·Echo (rule30/production 동일 검증 엔진). 등급 S+≥14·S≥12·A≥9.
전체·정렬은 stock_pool_latest.csv(엑셀). ⚠️ 의사결정 보조 풀이지 검증된 매수리스트 아님 — BAB가 고베타 주도주를 깎으므로 테마 모니터(supercycle_monitor)와 함께 보라. production v3.7.2 무변경.</div>
</body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    return path


def _selftest():
    ok = 0
    rng = np.random.default_rng(2); K, Tm = 40, 30
    idx = pd.date_range("2023-01-31", periods=Tm, freq="ME"); codes = [f"{i:06d}" for i in range(K)]
    good = set(codes[:15])
    px = pd.DataFrame(index=idx, columns=codes, dtype=float)
    for c in codes:
        dr = rng.normal(0.03 if c in good else 0.004, 0.002)
        px[c] = 1000 * np.cumprod(1 + rng.normal(dr, 0.05, Tm))
    fr = []
    for c in codes:
        for fy in range(2021, 2025):
            b = 1.0 if c in good else 0.3
            fr.append(dict(code=c, fiscal_year=fy, revenue=1e9*b, cogs=6e8*b, op_income=2e8*b,
                net_income=2e8*b if c in good else -1e7, assets=5e9, liabilities=2e9, equity=3e9,
                current_assets=2e9, current_liab=1e9, cash=5e8, cfo=2.5e8*b if c in good else 1e7,
                noncurrent_liab=1e9, issued_capital=1e8))
    fund = pd.DataFrame(fr)
    fine = {c: "반도체 제조업" if c in good else "기타 금융업" for c in codes}
    name = {c: f"종목{c}" for c in codes}
    adtv = {c: 1e11 for c in codes}
    df, dt = build(px, fund, fine, name, adtv, fmin=4)
    assert len(df) > 0 and "score" in df.columns; ok += 1
    assert df["score"].is_monotonic_decreasing; ok += 1            # 점수 내림차순
    assert (df["theme"].isin(["반도체/전자", "금융", "미분류"])).all(); ok += 1
    import tempfile
    p = render_html(df, dt, path=os.path.join(tempfile.gettempdir(), "_pool_test.html"))
    assert os.path.exists(p); ok += 1
    try: os.remove(p)
    except OSError: pass
    print(f"[OK] build_stock_pool selftest 통과 ({ok} checks)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices", default="kospi_monthly_prices.csv")
    ap.add_argument("--fundamentals", default="fundamentals_pit.csv")
    ap.add_argument("--kosdaq-sector", default="kosdaq_industry.csv")
    ap.add_argument("--fmin", type=int, default=F_MIN)
    ap.add_argument("--liq", type=float, default=LIQ_PCT)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    panel = pd.read_csv(a.prices, index_col=0, parse_dates=True)
    panel.columns = [str(c).zfill(6) for c in panel.columns]
    fund = pd.read_csv(a.fundamentals, dtype={"code": str}); fund["code"] = fund["code"].str.zfill(6)
    fine, name = TC.load_fine_map("liquidity_sector.csv", a.kosdaq_sector)
    adtv = _load_adtv(["liquidity_sector.csv", "liquidity_kosdaq.csv"])
    df, dt = build(panel, fund, fine, name, adtv, fmin=a.fmin, liq_pct=a.liq)
    df.to_csv("stock_pool_latest.csv", index=False, encoding="utf-8-sig")
    print(f"종목 풀 {len(df)}종 (기준 {dt}, F≥{a.fmin}·유동상위{100-int(a.liq*100)}%) → stock_pool_latest.csv")
    print(f"\n등급 분포: {df['grade'].value_counts().reindex(['S+','S','A','B','C','D','F']).dropna().to_dict()}")
    print(f"\n[전체 점수 상위 15]")
    print(f"{'#':>3} {'종목':12}{'테마':14}{'등급':>4}{'점수':>6}{'F':>3}{'12M초과':>8}")
    for _, r in df.head(15).iterrows():
        ex = "—" if (r["ex12_pct"] is None or pd.isna(r["ex12_pct"])) else f"{r['ex12_pct']:+.0%}"
        fs = "?" if (r["F"] is None or pd.isna(r["F"])) else str(int(r["F"]))
        print(f"{int(r['rank']):>3} {r['name'][:11]:12}{str(r['theme'])[:13]:14}{r['grade']:>4}{r['score']:>7.1f}  F{fs:<2}{ex:>8}")
    path = render_html(df, dt)
    print(f"\nHTML: {path}  ·  ⚠️ 의사결정 보조 풀(검증 매수리스트 아님). production 무변경.")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
