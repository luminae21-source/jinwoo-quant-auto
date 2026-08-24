#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
supercycle_buy.py — 집중모드 매수 후보 선정 (의사결정 지원·자동매매 아님)
==============================================================================
진우 정의: "실제 수익 거둘 종목군을 골라서, 임의 누락 없이."
설계: 포괄 테마분류(theme_classify, 누락 0) 위에서
  ① ON 수퍼사이클 테마만 (관찰=근접 포함 옵션)
  ② 상승 참여 (12M 시장초과 > 0)
  ③ 유동성 (ADTV 상위 60%) — 직장인 체결 가능
  ④ 품질 (F-score ≥ 3) — 깡통 회피, soft
  → 12M 시장초과 순 주도주 top-N. 반전 리스크(테마 감속·종목 3M 약화) 함께 표기.
누락 0: 전 종목이 어느 테마엔 속하므로(섹터 백본), ON 테마 후보를 빠짐없이 훑음.
⚠️ 백테스트 기각(2026-06-05): 기계적 추종 시 64개월 시장 −14.7%p·MDD −40.7%(vs −23.1%) = 모멘텀 함정.
  → 매수 룰 아님. **인지·관찰용으로만**(어느 테마가 뜨거운지). 실매수는 진우 재량+별도 판단.
사용: python supercycle_buy.py [--near] [--topn 5]   /   --selftest
"""
import argparse, os, sys, html
import numpy as np, pandas as pd
import theme_classify as TC
import supercycle_overlay as E

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

ADTV_PCT_FLOOR = 0.40       # 상위 60% (universe_rules와 정합)
F_MIN = 3                   # 품질 soft 하한
TOPN = 5
MIN_MEMBERS = 5


def _load(prices, liq_files, kosdaq_sec, inputs_csv):
    panel = pd.read_csv(prices, index_col=0, parse_dates=True)
    panel.columns = [str(c).zfill(6) for c in panel.columns]
    fine, name = TC.load_fine_map("liquidity_sector.csv", kosdaq_sec)
    adtv = {}
    for f in liq_files:
        if os.path.exists(f):
            d = pd.read_csv(f, dtype={"code": str}); d["code"] = d["code"].str.zfill(6)
            for _, r in d.iterrows():
                if r["code"] not in adtv and pd.notna(r.get("adtv")):
                    adtv[r["code"]] = float(r["adtv"])
    F = {}
    if os.path.exists(inputs_csv):
        fi = pd.read_csv(inputs_csv, dtype={"code": str}); fi["code"] = fi["code"].str.zfill(6)
        fy = fi["fiscal_year"].max()
        F = fi[fi["fiscal_year"] == fy].set_index("code")["F"].to_dict()
    return panel, fine, name, adtv, F


def _theme_baskets(panel_cols, fine, name):
    """전 종목 → 테마 (큐레이션 우선 + 섹터 백본). {theme:[codes]}, {code:theme}."""
    cur_by, cur_of = TC.load_theme_universe()
    cm, groups = TC.coarse_map(fine, name)
    baskets, of = {}, {}
    covered = set()
    for th, mem in cur_by.items():
        b = [c for c in mem if c in panel_cols]
        if b:
            baskets[th] = b; covered |= set(b)
            for c in b: of[c] = th
    for g, codes in groups.items():
        if g in ("기타", "미분류(섹터없음)"):
            continue
        b = [c for c in codes if c in panel_cols and c not in covered]
        if len(b) >= MIN_MEMBERS:
            baskets[g] = b
            for c in b: of.setdefault(c, g)
    return baskets, of


def _exc(px_c, mkt_cum, i, k):
    """종목 k개월 수익 − 시장 k개월 수익 (시장초과)."""
    if i - k < 0 or pd.isna(px_c.iloc[i]) or pd.isna(px_c.iloc[i - k]):
        return np.nan
    sret = px_c.iloc[i] / px_c.iloc[i - k] - 1
    return float(sret - mkt_cum[k])


def screen(panel, fine, name, adtv, F, i=None, include_near=False, topn=TOPN):
    cols = list(panel.columns)
    ret = panel.pct_change(); mkt = ret.mean(axis=1)
    i = (len(panel) - 1) if i is None else i
    mkt_cum = {k: float((1 + mkt.iloc[i - k + 1:i + 1]).prod() - 1) for k in (3, 6, 12)}
    adtv_pct = pd.Series(adtv).rank(pct=True)
    baskets, of = _theme_baskets(cols, fine, name)

    # 테마 국면
    states = {}
    for th, b in baskets.items():
        ex, br = E._excess_breadth(ret, b, mkt, i)
        on = bool(E.detect_supercycle(ret, {"_": b}, mkt, i)["_"])
        w3 = slice(i - 2, i + 1)
        ex3 = float((1 + ret[b].mean(axis=1).iloc[w3]).prod() - 1) - mkt_cum[3]
        near = (not on) and pd.notna(ex) and ex >= E.THRESH_EXCESS * 0.5 and pd.notna(br) and br >= E.THRESH_BREADTH * 0.8
        states[th] = {"excess": ex, "breadth": br, "on": on, "near": near, "ex3": ex3, "n": len(b)}

    pick_themes = [th for th, s in states.items() if s["on"] or (include_near and s["near"])]
    pick_themes.sort(key=lambda t: -(states[t]["excess"] if pd.notna(states[t]["excess"]) else -9))

    out = []
    for th in pick_themes:
        s = states[th]
        decel = pd.notna(s["ex3"]) and s["ex3"] < 0
        cands = []
        for c in baskets[th]:
            ex12 = _exc(panel[c], mkt_cum, i, 12)
            if pd.isna(ex12) or ex12 <= 0:               # 상승 참여
                continue
            ap = float(adtv_pct.get(c, 0))
            if ap < ADTV_PCT_FLOOR:                       # 유동성
                continue
            f = F.get(c, np.nan)
            if pd.notna(f) and f < F_MIN:                 # 품질 (값 있을 때만)
                continue
            ex6 = _exc(panel[c], mkt_cum, i, 6)
            cands.append({"code": c, "name": name.get(c, c), "ex12": ex12, "ex6": ex6,
                          "adtv_ek": adtv.get(c, 0) / 1e8, "F": (None if pd.isna(f) else int(f)),
                          "fading": pd.notna(ex6) and ex6 < 0})
        cands.sort(key=lambda x: -x["ex12"])
        out.append({"theme": th, "state": s, "decel": decel, "cands": cands[:topn]})
    return out, states


def render_console_safe(res, dt):
    print("=" * 68)
    print(f"집중모드 매수 후보 — 기준 {dt}  (의사결정 지원·자동매매 아님)")
    print("=" * 68)
    if not res:
        print("\n현재 ON 수퍼사이클 테마 없음 (--near 로 근접 포함)")
    for r in res:
        s = r["state"]; warn = " ⚠️감속/반전주의(추격 자제)" if r["decel"] else ""
        ex = "—" if pd.isna(s["excess"]) else f"{s['excess']:+.0%}"
        print(f"\n[{r['theme']}] 테마 12M초과 {ex}·breadth {s['breadth']:.0%}·{s['n']}종{warn}")
        if not r["cands"]:
            print("   (필터 통과 후보 없음)")
        for k, c in enumerate(r["cands"], 1):
            ex6 = "—" if pd.isna(c["ex6"]) else f"{c['ex6']:+.0%}"
            fd = " ·6M약화" if c["fading"] else ""
            ftag = f"F{c['F']}" if c["F"] is not None else "F?"
            print(f"   {k}. {c['name']:14} 12M {c['ex12']:+.0%} · 6M {ex6} · {ftag} · ADTV {c['adtv_ek']:,.0f}억{fd}")
    print("\n※ ⚠️백테스트 기각: 기계적 추종 시 시장 −14.7%p·MDD −40%(backtest_buy_screen). 매수 룰 아닌 인지용. 실매수는 진우 재량.")


def render_html(res, dt, path="dashboard_buy.html"):
    def esc(x): return html.escape(str(x))
    def pct(x): return "—" if x is None or pd.isna(x) else f"{x:+.0%}"
    secs = ""
    for r in res:
        s = r["state"]
        hdr_col = "#d97706" if r["decel"] else "#16a34a"
        warn = " · ⚠️감속/반전주의" if r["decel"] else ""
        rows = ""
        for k, c in enumerate(r["cands"], 1):
            fd = "<span style='color:#d97706'> ·6M약화</span>" if c["fading"] else ""
            ftag = f"F{c['F']}" if c["F"] is not None else "F?"
            rows += (f"<tr><td>{k}</td><td>{esc(c['name'])}</td>"
                     f"<td style='text-align:right;color:#16a34a'>{pct(c['ex12'])}</td>"
                     f"<td style='text-align:right'>{pct(c['ex6'])}{fd}</td>"
                     f"<td style='text-align:center'>{ftag}</td>"
                     f"<td style='text-align:right'>{c['adtv_ek']:,.0f}억</td></tr>")
        if not r["cands"]:
            rows = "<tr><td colspan=6 class='mut'>필터 통과 후보 없음</td></tr>"
        secs += (f"<div class='card' style='border-left:5px solid {hdr_col}'>"
                 f"<div class='th'>{esc(r['theme'])} <span class='mut'>12M초과 {pct(s['excess'])}·breadth {pct(s['breadth'])}{warn}</span></div>"
                 f"<table><tr><td>#</td><td>종목</td><td style='text-align:right'>12M초과</td>"
                 f"<td style='text-align:right'>6M초과</td><td style='text-align:center'>F</td>"
                 f"<td style='text-align:right'>ADTV</td></tr>{rows}</table></div>")
    if not res:
        secs = "<div class='card mut'>현재 ON 수퍼사이클 테마 없음</div>"
    out = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>집중모드 ON테마 관찰후보</title><style>
*{{box-sizing:border-box;margin:0}}body{{background:#0f172a;color:#e2e8f0;font-family:-apple-system,system-ui,sans-serif;padding:14px;max-width:780px;margin:0 auto}}
h1{{font-size:17px}}.sub{{color:#94a3b8;font-size:12px;margin-bottom:14px}}
.card{{background:#1e293b;border-radius:10px;padding:12px 14px;margin-bottom:12px}}
.th{{font-size:15px;font-weight:700;margin-bottom:8px}}.mut{{color:#94a3b8;font-size:12px;font-weight:400}}
table{{width:100%;border-collapse:collapse;font-size:13px}}td{{padding:6px 6px;border-bottom:1px solid #334155}}
.note{{color:#64748b;font-size:11px;margin-top:14px;line-height:1.5}}
</style></head><body>
<h1>집중모드 매수 후보</h1>
<div class="sub">기준 {dt} · ON 수퍼사이클 테마 주도주 · 의사결정 지원(자동매매 아님)</div>
{secs}
<div class="note">필터: ON 테마 ∩ 12M 시장초과>0(상승참여) ∩ ADTV 상위60%(유동성) ∩ F≥3(품질). 12M초과 순.
⚠️ <b>백테스트 기각</b>: 이 스크린을 기계적으로 매월 추종 시 64개월 시장 대비 <b>−14.7%p·MDD −40.7%</b>(backtest_buy_screen). 모멘텀 함정. <b>매수 룰이 아니라 "어느 테마가 뜨거운지" 인지용</b>입니다. 실매수는 진우 재량+개별 판단.</div>
</body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    return path


def _selftest():
    ok = 0
    rng = np.random.default_rng(9); Tm = 40
    idx = pd.date_range("2022-01-31", periods=Tm, freq="ME")
    semi = [f"E{i:05d}" for i in range(8)]; other = [f"X{i:05d}" for i in range(12)]
    cols = semi + other
    px = pd.DataFrame(index=idx, columns=cols, dtype=float)
    for c in cols: px[c] = 1000.0
    for t in range(1, Tm):
        for c in cols:
            dr = rng.normal(0.11, 0.06) if (c in semi and 18 <= t <= 39) else rng.normal(0.003, 0.02)
            px.loc[idx[t], c] = px.loc[idx[t-1], c] * (1 + dr)
    fine = {**{c: "반도체 제조업" for c in semi}, **{c: "기타 금융업" for c in other}}
    name = {c: c for c in cols}
    adtv = {c: 1e11 for c in cols}          # 전부 유동
    F = {c: 7 for c in cols}
    res, states = screen(px, fine, name, adtv, F, i=38, topn=5)
    assert states.get("반도체/전자", {}).get("on"), f"테마 ON 실패 {states}"; ok += 1
    semi_res = [r for r in res if r["theme"] == "반도체/전자"]
    assert semi_res and semi_res[0]["cands"], "후보 없음"; ok += 1
    # 후보는 전부 SEMI·상승참여
    assert all(c["code"] in semi for c in semi_res[0]["cands"]); ok += 1
    assert all(c["ex12"] > 0 for c in semi_res[0]["cands"]); ok += 1
    # 유동성 필터: 한 종목 ADTV 0 → 제외
    adtv2 = dict(adtv); adtv2[semi[0]] = 1.0
    res2, _ = screen(px, fine, name, adtv2, F, i=38, topn=5)
    sr2 = [r for r in res2 if r["theme"] == "반도체/전자"][0]
    assert semi[0] not in [c["code"] for c in sr2["cands"]], "유동성 필터 미작동"; ok += 1
    import tempfile
    p = render_html(res, "2026-06-30", path=os.path.join(tempfile.gettempdir(), "_buy_test.html"))
    assert os.path.exists(p); ok += 1
    try: os.remove(p)
    except OSError: pass
    render_console_safe(res, "selftest")
    print(f"\n[OK] supercycle_buy selftest 통과 ({ok} checks)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices", default="kospi_monthly_prices.csv")
    ap.add_argument("--kosdaq-sector", default="kosdaq_industry.csv")
    ap.add_argument("--inputs", default="score_inputs_univ.csv")
    ap.add_argument("--near", action="store_true", help="근접(관찰) 테마도 포함")
    ap.add_argument("--topn", type=int, default=TOPN)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    panel, fine, name, adtv, F = _load(a.prices, ["liquidity_sector.csv", "liquidity_kosdaq.csv"],
                                       a.kosdaq_sector, a.inputs)
    res, states = screen(panel, fine, name, adtv, F, include_near=a.near, topn=a.topn)
    render_console_safe(res, str(panel.index[-1].date()))
    path = render_html(res, str(panel.index[-1].date()))
    print("\nHTML 저장: " + path)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
