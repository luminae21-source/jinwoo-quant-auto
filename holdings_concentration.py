#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
holdings_concentration.py — 보유 18종 집중도 정기 모니터 (+ 시계열 추이)
==============================================================================
목적: 보유가 '겉 분산 속 집중'인지 정기 점검 + 전월 대비 추이. 수익이 소수 종목/테마/
      고베타에 쏠리는 정도를 수치·플래그·시계열로 가시화.
      ⚠️ 디리스킹 권고 아님 — 베팅의 실체. 결정·책임은 진우(수익 우선 철학 존중).

입력(같은 폴더): kospi_monthly_prices.csv · kosdaq_monthly_prices.csv · theme_classify.py
산출: holdings_concentration_latest.csv · holdings_concentration_history.csv ·
      보유집중도_모니터_YYYY-MM-DD.html · 콘솔
추이: 월간 패널로 과거 시점별 집중도 재계산(백필). **현재 보유 18종을 과거에 적용**
      (보유 변경 미반영) → 이 바스켓의 집중도가 어떻게 변해왔나. 매월 자동 연장.
사용: python holdings_concentration.py [--selftest] [--hist N]
무수정: production·heat·발굴트랙. theme_classify는 읽기(소스 직접 컴파일).
"""
import argparse, os, sys, types
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
HIST_MONTHS = 24

HOLD = [('삼양식품','003230'),('두산에너빌리티','034020'),('NH투자증권','005940'),('ISC','095340'),
        ('알테오젠','196170'),('한화에어로','012450'),('한미반도체','042700'),('SK하이닉스','000660'),
        ('삼성물산','028260'),('삼성전자','005930'),('NAVER','035420'),('아모레퍼시픽','090430'),
        ('KT&G','033780'),('KB금융','105560'),('삼성SDI','006400'),('기아','000270'),
        ('카카오','035720'),('LIG넥스원','079550')]

FLAG_TOP2, FLAG_THEME, FLAG_BETA, FLAG_EFFN = 0.50, 0.60, 1.30, 6


def _load_src(fname, modname):
    path = os.path.join(HERE, fname); src = open(path, encoding="utf-8").read()
    m = types.ModuleType(modname); m.__file__ = path; sys.modules[modname] = m
    sys.dont_write_bytecode = True; exec(compile(src, path, "exec"), m.__dict__); return m


def load_panel():
    frames = []
    for f in ("kospi_monthly_prices.csv", "kosdaq_monthly_prices.csv"):
        p = os.path.join(HERE, f)
        if os.path.exists(p):
            d = pd.read_csv(p, parse_dates=["Date"], index_col="Date")
            d.columns = [str(c).zfill(6) for c in d.columns]; frames.append(d)
    panel = pd.concat(frames, axis=1).sort_index()
    return panel.loc[:, ~panel.columns.duplicated()]


def themes_for(codes):
    TC = _load_src("theme_classify.py", "theme_classify")
    fine, name = TC.load_fine_map()
    return {c: TC.coarse_sector(name.get(c, ""), fine.get(c, "")) for c in codes}


def analyze_at(panel, i, theme_map, hold=HOLD, beta_win=36):
    """as-of 월 index i 의 집중도(데이터 ≤ i). theme_map = {code: theme}."""
    ret = panel.pct_change(); mkt = ret.mean(axis=1)
    if i < 12:
        return None
    mkt12 = float((1 + mkt.iloc[i - 11:i + 1]).prod() - 1)
    b0 = max(0, i - beta_win + 1); bm = mkt.iloc[b0:i + 1]
    rows = []
    for nm, c in hold:
        if c not in panel.columns:
            continue
        s = panel[c].iloc[:i + 1].dropna()
        if len(s) < 13:
            continue
        r12 = float(s.iloc[-1] / s.iloc[-13] - 1)
        rr = ret[c].iloc[b0:i + 1].fillna(0)
        beta = float(np.cov(rr, bm)[0, 1] / np.var(bm)) if np.var(bm) > 0 else np.nan
        rows.append({"name": nm, "code": c, "theme": theme_map.get(c, "기타"),
                     "ret12m": r12, "ex12": r12 - mkt12, "beta": beta})
    df = pd.DataFrame(rows); n = len(df)
    if n == 0:
        return None
    df["contrib_pp"] = df["ret12m"] / n * 100
    port_ret = float(df["ret12m"].mean()); port_beta = float(df["beta"].mean())
    pos = df["contrib_pp"].clip(lower=0)
    w = pos / pos.sum() if pos.sum() > 0 else pd.Series(np.repeat(1 / n, n))
    hhi = float((w ** 2).sum()); effn = float(1 / hhi) if hhi > 0 else n
    df = df.sort_values("contrib_pp", ascending=False).reset_index(drop=True)
    top2_share = float(df["contrib_pp"].head(2).sum() / (port_ret * 100)) if port_ret != 0 else np.nan
    th_ag = df.groupby("theme").agg(n=("code","size"), ret_mean=("ret12m","mean"),
                                    contrib_pp=("contrib_pp","sum"), beta=("beta","mean")
                                    ).sort_values("contrib_pp", ascending=False)
    top_theme = th_ag.index[0]
    top_theme_share = float(th_ag["contrib_pp"].iloc[0] / (port_ret * 100)) if port_ret != 0 else np.nan
    shock = df.apply(lambda r: -0.30 if r["theme"] == top_theme else 0.0, axis=1)
    scen_top = float(shock.mean() * 100)
    flags = []
    if pd.notna(top2_share) and top2_share > FLAG_TOP2: flags.append(f"🔴 상위2종이 수익의 {top2_share*100:.0f}%")
    if pd.notna(top_theme_share) and top_theme_share > FLAG_THEME: flags.append(f"🔴 '{top_theme}' 한 테마가 {top_theme_share*100:.0f}%")
    if pd.notna(port_beta) and port_beta > FLAG_BETA: flags.append(f"⚠️ 포트 베타 {port_beta:.2f}")
    if effn < FLAG_EFFN: flags.append(f"🔴 유효 종목수 {effn:.1f} (총 {n})")
    return {"df": df, "th_ag": th_ag, "n": n, "mkt12": mkt12, "port_ret": port_ret,
            "port_beta": port_beta, "hhi": hhi, "effn": effn, "top2_share": top2_share,
            "top_theme": top_theme, "top_theme_share": top_theme_share, "scen_top": scen_top,
            "flags": flags, "asof": panel.index[i], "month": panel.index[i].strftime("%Y-%m")}


def build_history(panel, theme_map, months=HIST_MONTHS):
    rows = []
    start = max(12, len(panel) - months)
    for i in range(start, len(panel)):
        r = analyze_at(panel, i, theme_map)
        if r:
            rows.append({"month": r["month"], "port_ret": round(r["port_ret"]*100,1),
                         "mkt12": round(r["mkt12"]*100,1), "top2_share": round(r["top2_share"]*100,1),
                         "top_theme": r["top_theme"], "top_theme_share": round(r["top_theme_share"]*100,1),
                         "effn": round(r["effn"],1), "port_beta": round(r["port_beta"],2),
                         "flags_n": len(r["flags"])})
    return pd.DataFrame(rows)


def _spark(vals, w=520, h=70, color="#ff7a45", pad=4):
    vals = [v for v in vals if v is not None and not (isinstance(v,float) and np.isnan(v))]
    if len(vals) < 2:
        return ""
    mn, mx = min(vals), max(vals); rng = (mx - mn) or 1
    pts = " ".join(f"{pad+(w-2*pad)*k/(len(vals)-1):.1f},{pad+(h-2*pad)*(1-(v-mn)/rng):.1f}" for k,v in enumerate(vals))
    return f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{pts}"/>'


def write_outputs(res, hist):
    df = res["df"]; datestr = res["asof"].strftime("%Y-%m-%d")
    out = df.copy()
    for col in ("ret12m","ex12","contrib_pp","beta"): out[col] = out[col].round(4)
    out.to_csv(os.path.join(HERE, "holdings_concentration_latest.csv"), index=False, encoding="utf-8-sig")
    hist.to_csv(os.path.join(HERE, "holdings_concentration_history.csv"), index=False, encoding="utf-8-sig")

    # 전월 대비 Δ
    delta = {}
    if len(hist) >= 2:
        cur, prev = hist.iloc[-1], hist.iloc[-2]
        for k in ("top2_share","top_theme_share","effn","port_beta"):
            delta[k] = cur[k] - prev[k]

    def pp(x): return "n/a" if pd.isna(x) else f"{x*100:+.0f}%"
    def dlt(k, suf="%p"):
        if k not in delta: return ""
        d = delta[k]; c = "var(--bad)" if (d>0 and k!="effn") or (d<0 and k=="effn") else "var(--ok)"
        return f' <span style="color:{c};font-size:11px">(전월 {d:+.1f}{suf})</span>'

    rows = "".join(
        f"<tr><td>{r['name']} <span class='c'>{r['code']}</span></td><td>{r['theme']}</td>"
        f"<td class='num'>{pp(r['ret12m'])}</td><td class='num'>{pp(r['ex12'])}</td>"
        f"<td class='num'>{r['contrib_pp']:+.0f}%p</td><td class='num'>{r['beta']:.2f}</td></tr>"
        for _, r in df.iterrows())
    throws = "".join(
        f"<tr><td>{idx}</td><td class='num'>{int(r['n'])}</td><td class='num'>{r['ret_mean']*100:+.0f}%</td>"
        f"<td class='num'>{r['contrib_pp']:+.0f}%p</td><td class='num'>{r['beta']:.2f}</td></tr>"
        for idx, r in res["th_ag"].iterrows())
    flags = "".join(f"<li>{f}</li>" for f in res["flags"]) or "<li>특이 집중 플래그 없음</li>"

    # 추이 차트 (상위2종·테마 비중)
    months = hist["month"].tolist()
    sp2 = _spark(hist["top2_share"].tolist(), color="#ff7a45")
    spt = _spark(hist["top_theme_share"].tolist(), color="#6b9bd1")
    spe = _spark(hist["effn"].tolist(), color="#7ee0ad")
    lab = f"{months[0]} → {months[-1]}" if months else ""
    hrows = "".join(
        f"<tr><td>{r['month']}</td><td class='num'>{r['port_ret']:+.0f}%</td><td class='num'>{r['top2_share']:.0f}%</td>"
        f"<td class='num'>{r['top_theme_share']:.0f}%</td><td class='num'>{r['effn']:.1f}</td><td class='num'>{r['port_beta']:.2f}</td></tr>"
        for _, r in hist.tail(8).iterrows())

    html = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>보유 집중도 모니터 — {datestr}</title>
<style>
:root{{--bg:#0f1115;--card:#181b22;--ink:#e8eaed;--mut:#9aa0aa;--line:#262a33;--acc:#ff7a45;--ok:#3fb37a;--bad:#e2606a}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,'Segoe UI','Malgun Gothic',sans-serif;padding:20px;line-height:1.5}}
h1{{font-size:19px;margin:0 0 2px}}h2{{font-size:14px;color:#fff;border-left:3px solid var(--acc);padding-left:8px;margin:20px 0 8px}}
.sub{{color:var(--mut);font-size:12px;margin-bottom:8px}}
.kpis{{display:flex;gap:9px;flex-wrap:wrap;margin:8px 0}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:9px 13px;min-width:120px}}
.kpi b{{display:block;font-size:18px;color:var(--acc)}}.kpi span{{font-size:11px;color:var(--mut)}}
.risk{{background:#2c1416;border:1px solid #5e2a2e;color:#ffb9bd;border-radius:9px;padding:10px 13px;font-size:12.5px;margin:8px 0}}
.risk ul{{margin:5px 0 0;padding-left:18px}}.risk li{{margin:2px 0}}
.trend{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px}}
.tleg{{display:flex;gap:14px;font-size:11.5px;color:var(--mut);margin-bottom:6px;flex-wrap:wrap}}
.tleg i{{display:inline-block;width:12px;height:3px;vertical-align:middle;margin-right:4px}}
table{{width:100%;border-collapse:collapse;font-size:12px;margin-top:5px}}
th,td{{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left}}th{{color:var(--mut);font-size:11px}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}.c{{color:var(--mut);font-family:monospace;font-size:10.5px}}
.foot{{margin-top:18px;color:#5a6068;font-size:11px;line-height:1.6;border-top:1px solid var(--line);padding-top:10px}}
svg{{width:100%;height:auto;background:#11141a;border-radius:6px}}
</style></head><body>
<h1>📊 선별 18 집중도 모니터 (모델 픽)</h1>
<div class="sub">선별 18종(모델 픽·동일가중) · 기준 {res['asof'].strftime('%Y-%m')} · 시장 12M {res['mkt12']*100:+.0f}%</div>
<div class="kpis">
  <div class="kpi"><b>{res['port_ret']*100:+.0f}%</b><span>포트 12M(EW)</span></div>
  <div class="kpi"><b>{res['top2_share']*100:.0f}%</b><span>상위2종 비중{dlt('top2_share')}</span></div>
  <div class="kpi"><b>{res['top_theme_share']*100:.0f}%</b><span>{res['top_theme']}{dlt('top_theme_share')}</span></div>
  <div class="kpi"><b>{res['effn']:.1f}</b><span>유효N/{res['n']}{dlt('effn','')}</span></div>
  <div class="kpi"><b>{res['port_beta']:.2f}</b><span>포트 베타{dlt('port_beta','')}</span></div>
</div>
<div class="risk"><b>리스크 플래그</b><ul>{flags}</ul>
시나리오: 상위테마({res['top_theme']}) −30%·나머지 0% → 다음 구간 EW 포트 ≈ <b>{res['scen_top']:+.0f}%</b>.</div>

<h2>집중도 추이 ({lab})</h2>
<div class="trend">
  <div class="tleg"><span><i style="background:#ff7a45"></i>상위2종 비중(%)</span><span><i style="background:#6b9bd1"></i>{res['top_theme']} 비중(%)</span><span><i style="background:#7ee0ad"></i>유효 종목수</span></div>
  <svg viewBox="0 0 520 70" preserveAspectRatio="none">{sp2}{spt}{spe}</svg>
  <table><thead><tr><th>월</th><th class="num">포트12M</th><th class="num">상위2종</th><th class="num">{res['top_theme'][:6]}</th><th class="num">유효N</th><th class="num">베타</th></tr></thead><tbody>{hrows}</tbody></table>
</div>

<h2>테마별 기여</h2>
<table><thead><tr><th>테마</th><th class="num">종목</th><th class="num">평균 12M</th><th class="num">EW 기여</th><th class="num">베타</th></tr></thead><tbody>{throws}</tbody></table>
<h2>종목별 (기여순)</h2>
<table><thead><tr><th>종목</th><th>테마</th><th class="num">12M수익</th><th class="num">12M초과</th><th class="num">EW기여</th><th class="num">베타</th></tr></thead><tbody>{rows}</tbody></table>
<div class="foot">EW기여=종목12M÷종목수(%p,합=포트). 12M초과=종목−시장EW. 베타=최근36M 회귀. 추이=현재 보유 바스켓을 과거 시점에 적용(보유 변경 미반영)·매월 연장.<br>
⚠️ 디리스킹 권고 아님 — 베팅 실체 가시화. 백테스트·과거수익을 forward로 쓰지 않음. 결정·책임은 진우.</div>
</body></html>"""
    hp = os.path.join(HERE, f"보유집중도_모니터_{datestr}.html")
    open(hp, "w", encoding="utf-8").write(html)
    return hp, delta


def load_my_holdings():
    """my_holdings.csv → ([(name,code),...], {code:weight%}). 주석(#)·헤더·빈줄 무시. 없으면 (None,None)."""
    p = os.path.join(HERE, "my_holdings.csv")
    if not os.path.exists(p):
        return None, None
    hold = []; wt = {}
    for line in open(p, encoding="utf-8-sig"):
        line = line.strip()
        if not line or line.startswith("#") or line.lower().startswith("code,"):
            continue
        parts = [x.strip() for x in line.split(",")]
        c = parts[0].zfill(6)
        if not c.isdigit():
            continue
        nm = parts[1] if len(parts) > 1 and parts[1] else c
        try:
            w = float(parts[2]) if len(parts) > 2 and parts[2] else np.nan
        except ValueError:
            w = np.nan
        hold.append((nm, c)); wt[c] = w
    return (hold, wt) if hold else (None, None)


def analyze_mine(panel, i, theme_map, hold, weights, beta_win=36):
    """실보유 집중도 = 자본 '비중' 기반(EW 아님). weights={code:비중%}. 결측 비중은 균등.
    HHI·상위2·테마비중을 자본배분으로 산출 → 실제 쏠림(예: 2차전지 79%)을 정확히 가시화."""
    ret = panel.pct_change(); mkt = ret.mean(axis=1)
    if i < 12:
        return None
    mkt12 = float((1 + mkt.iloc[i - 11:i + 1]).prod() - 1)
    b0 = max(0, i - beta_win + 1); bm = mkt.iloc[b0:i + 1]
    rows = []
    for nm, c in hold:
        if c not in panel.columns:
            continue
        s = panel[c].iloc[:i + 1].dropna()
        if len(s) < 13:
            continue
        r12 = float(s.iloc[-1] / s.iloc[-13] - 1)
        rr = ret[c].iloc[b0:i + 1].fillna(0)
        beta = float(np.cov(rr, bm)[0, 1] / np.var(bm)) if np.var(bm) > 0 else np.nan
        rows.append({"name": nm, "code": c, "theme": theme_map.get(c, "기타"),
                     "ret12m": r12, "ex12": r12 - mkt12, "beta": beta, "weight": weights.get(c, np.nan)})
    df = pd.DataFrame(rows); n = len(df)
    if n == 0:
        return None
    # 비중 정규화(합→1). 전부 결측이면 균등.
    df["w"] = df["weight"].fillna(0.0)
    if df["w"].sum() <= 0:
        df["w"] = 1.0
    df["w"] = df["w"] / df["w"].sum()
    df["contrib_pp"] = df["ret12m"] * df["w"] * 100      # 합 = 가중 포트 12M
    port_ret = float((df["ret12m"] * df["w"]).sum())
    port_beta = float((df["beta"].fillna(0) * df["w"]).sum())
    hhi = float((df["w"] ** 2).sum()); effn = float(1 / hhi) if hhi > 0 else n
    df = df.sort_values("w", ascending=False).reset_index(drop=True)
    top2_share = float(df["w"].head(2).sum())
    th_ag = df.groupby("theme").agg(n=("code", "size"), w=("w", "sum"),
                                    ret_mean=("ret12m", "mean"), beta=("beta", "mean")
                                    ).sort_values("w", ascending=False)
    top_theme = th_ag.index[0]; top_theme_share = float(th_ag["w"].iloc[0])
    scen_top = float((df["w"] * df["theme"].apply(lambda t: -0.30 if t == top_theme else 0.0)).sum() * 100)
    flags = []
    if top2_share > FLAG_TOP2: flags.append(f"🔴 상위2종이 자본의 {top2_share*100:.0f}%")
    if top_theme_share > FLAG_THEME: flags.append(f"🔴 '{top_theme}' 한 테마에 자본 {top_theme_share*100:.0f}%")
    if pd.notna(port_beta) and port_beta > FLAG_BETA: flags.append(f"⚠️ 포트 베타 {port_beta:.2f}")
    if effn < 3: flags.append(f"🔴 유효 종목수 {effn:.1f} (총 {n}) — 분산 부족")
    return {"df": df, "th_ag": th_ag, "n": n, "mkt12": mkt12, "port_ret": port_ret,
            "port_beta": port_beta, "hhi": hhi, "effn": effn, "top2_share": top2_share,
            "top_theme": top_theme, "top_theme_share": top_theme_share, "scen_top": scen_top,
            "flags": flags, "asof": panel.index[i], "month": panel.index[i].strftime("%Y-%m")}


def render_mine(res):
    """실보유 집중도 간단 HTML(자본배분 중심·시계열 없음 — 실보유는 수시 변동)."""
    df = res["df"]; datestr = res["asof"].strftime("%Y-%m-%d")
    out = df[["name", "code", "theme", "weight", "w", "ret12m", "ex12", "beta", "contrib_pp"]].copy()
    for col in ("w", "ret12m", "ex12", "beta", "contrib_pp"):
        out[col] = out[col].round(4)
    out.to_csv(os.path.join(HERE, "holdings_concentration_MINE_latest.csv"), index=False, encoding="utf-8-sig")
    pp = lambda x: "n/a" if pd.isna(x) else f"{x*100:+.0f}%"
    rows = "".join(
        f"<tr><td>{r['name']} <span class='c'>{r['code']}</span></td><td>{r['theme']}</td>"
        f"<td class='num'><b>{r['w']*100:.0f}%</b></td><td class='num'>{pp(r['ret12m'])}</td>"
        f"<td class='num'>{pp(r['ex12'])}</td><td class='num'>{r['beta']:.2f}</td></tr>"
        for _, r in df.iterrows())
    throws = "".join(
        f"<tr><td>{idx}</td><td class='num'>{int(r['n'])}</td><td class='num'><b>{r['w']*100:.0f}%</b></td>"
        f"<td class='num'>{r['ret_mean']*100:+.0f}%</td><td class='num'>{r['beta']:.2f}</td></tr>"
        for idx, r in res["th_ag"].iterrows())
    flags = "".join(f"<li>{f}</li>" for f in res["flags"]) or "<li>특이 집중 플래그 없음</li>"
    html = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>실보유 집중도 — {datestr}</title>
<style>
:root{{--bg:#0f1115;--card:#181b22;--ink:#e8eaed;--mut:#9aa0aa;--line:#262a33;--acc:#ff7a45;--ok:#3fb37a;--bad:#e2606a}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,'Segoe UI','Malgun Gothic',sans-serif;padding:20px;line-height:1.5;max-width:620px;margin:0 auto}}
h1{{font-size:19px;margin:0 0 2px}}h2{{font-size:14px;color:#fff;border-left:3px solid var(--acc);padding-left:8px;margin:20px 0 8px}}
.sub{{color:var(--mut);font-size:12px;margin-bottom:8px}}
.kpis{{display:flex;gap:9px;flex-wrap:wrap;margin:8px 0}}
.kpi{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:9px 13px;min-width:110px}}
.kpi b{{display:block;font-size:18px;color:var(--acc)}}.kpi span{{font-size:11px;color:var(--mut)}}
.risk{{background:#2c1416;border:1px solid #5e2a2e;color:#ffb9bd;border-radius:9px;padding:10px 13px;font-size:12.5px;margin:8px 0}}
.risk ul{{margin:5px 0 0;padding-left:18px}}.risk li{{margin:2px 0}}
table{{width:100%;border-collapse:collapse;font-size:12px;margin-top:5px}}
th,td{{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left}}th{{color:var(--mut);font-size:11px}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}.c{{color:var(--mut);font-family:monospace;font-size:10.5px}}
.foot{{margin-top:18px;color:#5a6068;font-size:11px;line-height:1.6;border-top:1px solid var(--line);padding-top:10px}}
</style></head><body>
<h1>🧮 실보유 집중도 (내 실제 포트)</h1>
<div class="sub">my_holdings.csv · 자본 비중 기준 · 기준 {res['asof'].strftime('%Y-%m')} · 시장 12M {res['mkt12']*100:+.0f}%</div>
<div class="kpis">
  <div class="kpi"><b>{res['n']}종</b><span>보유 종목수</span></div>
  <div class="kpi"><b>{res['top_theme_share']*100:.0f}%</b><span>{res['top_theme']} 비중</span></div>
  <div class="kpi"><b>{res['top2_share']*100:.0f}%</b><span>상위2종 비중</span></div>
  <div class="kpi"><b>{res['effn']:.1f}</b><span>유효N/{res['n']}</span></div>
  <div class="kpi"><b>{res['port_beta']:.2f}</b><span>포트 베타</span></div>
</div>
<div class="risk"><b>리스크 플래그 (자본 집중)</b><ul>{flags}</ul>
시나리오: 최대테마({res['top_theme']}) −30%·나머지 0% → 포트 ≈ <b>{res['scen_top']:+.0f}%</b>.</div>
<h2>테마별 자본 비중</h2>
<table><thead><tr><th>테마</th><th class="num">종목</th><th class="num">비중</th><th class="num">평균 12M</th><th class="num">베타</th></tr></thead><tbody>{throws}</tbody></table>
<h2>종목별 (비중순)</h2>
<table><thead><tr><th>종목</th><th>테마</th><th class="num">비중</th><th class="num">12M수익</th><th class="num">12M초과</th><th class="num">베타</th></tr></thead><tbody>{rows}</tbody></table>
<div class="foot">비중=my_holdings.csv 자본배분(정규화). 유효N=1/HHI(자본 기준 분산도). 12M초과=종목−시장EW. 베타=최근36M.<br>
⚠️ 디리스킹 권고 아님 — 베팅 실체 가시화. 결정·책임은 진우.</div>
</body></html>"""
    hp = os.path.join(HERE, f"보유집중도_실보유_{datestr}.html")
    open(hp, "w", encoding="utf-8").write(html)
    return hp


def _selftest():
    ok = 0
    idx = pd.date_range("2021-01-31", periods=50, freq="ME")
    cols = [c for _, c in HOLD]
    px = pd.DataFrame(1000.0, index=idx, columns=cols)
    for k, c in enumerate(cols):
        g = 0.035 if k < 2 else 0.0008
        px[c] = 1000 * np.cumprod(1 + np.r_[0, np.random.default_rng(k).normal(g, 0.01, 49)])
    tm = {c: ("반도체/전자" if k < 2 else "기타") for k, (_, c) in enumerate(HOLD)}
    res = analyze_at(px, len(px)-1, tm)
    assert res and res["n"] == len(cols); ok += 1
    assert res["effn"] < res["n"] and res["top2_share"] > 0.4; ok += 1
    assert abs(res["df"]["contrib_pp"].sum()/100 - res["port_ret"]) < 1e-9; ok += 1
    hist = build_history(px, tm, months=18)
    assert len(hist) >= 12 and list(hist.columns)[:3] == ["month","port_ret","mkt12"]; ok += 1
    assert hist["month"].is_monotonic_increasing and hist["top2_share"].notna().all(); ok += 1
    # --mine: 3종 중 2종이 한 테마 79% → 테마/상위2 자본집중 잡히는지
    mhold = [("A","000001"),("B","000002"),("C","000003")]
    mwt = {"000001": 53, "000002": 26, "000003": 21}
    mpx = pd.DataFrame(1000.0, index=idx, columns=[c for _, c in mhold])
    for k, (_, c) in enumerate(mhold):
        mpx[c] = 1000 * np.cumprod(1 + np.r_[0, np.random.default_rng(k+9).normal(0.01, 0.01, 49)])
    mtm = {"000001": "2차전지", "000002": "2차전지", "000003": "반도체/전자"}
    mr = analyze_mine(mpx, len(mpx)-1, mtm, mhold, mwt)
    assert mr and abs(mr["top_theme_share"] - 0.79) < 1e-6 and mr["top_theme"] == "2차전지"; ok += 1
    assert abs(mr["top2_share"] - 0.79) < 1e-6 and mr["effn"] < 3; ok += 1
    print(f"✅ holdings_concentration 셀프테스트 통과 ({ok}/7): 종목수·집중·기여합·시계열·월정렬·실보유테마79%·상위2")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--hist", type=int, default=HIST_MONTHS)
    ap.add_argument("--mine", action="store_true", help="my_holdings.csv 실보유 자본집중도")
    a = ap.parse_args()
    if a.selftest:
        _selftest(); return
    if a.mine:
        hold, wt = load_my_holdings()
        if not hold:
            print("❌ my_holdings.csv 비어있음/없음 — code,name,weight 입력 후 재실행."); return
        panel = load_panel()
        tm = themes_for([c for _, c in hold])
        res = analyze_mine(panel, len(panel) - 1, tm, hold, wt)
        if not res:
            print("❌ 데이터부족 — 패널에 보유종목 가격이 없음(코드/상장 확인)."); return
        hp = render_mine(res)
        print(f"실보유 {res['n']}종 · 기준 {res['asof'].strftime('%Y-%m-%d')} · 가중포트 12M {res['port_ret']*100:+.0f}% (시장 {res['mkt12']*100:+.0f}%)")
        print(f"최대테마 {res['top_theme']} {res['top_theme_share']*100:.0f}% · 상위2종 {res['top2_share']*100:.0f}% · 유효N {res['effn']:.1f}/{res['n']} · 베타 {res['port_beta']:.2f}")
        if res["flags"]:
            print("플래그:", " / ".join(res["flags"]))
        print(f"시나리오({res['top_theme']} −30%): 포트 {res['scen_top']:+.0f}%")
        print(f"산출: holdings_concentration_MINE_latest.csv · {os.path.basename(hp)}")
        return
    panel = load_panel()
    tm = themes_for([c for _, c in HOLD])
    res = analyze_at(panel, len(panel)-1, tm)
    hist = build_history(panel, tm, months=a.hist)
    hp, delta = write_outputs(res, hist)
    print(f"보유 {res['n']}종 · 기준 {res['asof'].strftime('%Y-%m-%d')} · 포트 12M(EW) {res['port_ret']*100:+.0f}% (시장 {res['mkt12']*100:+.0f}%)")
    print(f"상위2종 {res['top2_share']*100:.0f}% · {res['top_theme']} {res['top_theme_share']*100:.0f}% · 유효N {res['effn']:.1f}/{res['n']} · 베타 {res['port_beta']:.2f}")
    if delta:
        print(f"전월 대비: 상위2종 {delta['top2_share']:+.1f}%p · 유효N {delta['effn']:+.1f} · 베타 {delta['port_beta']:+.2f}")
    if res["flags"]:
        print("플래그:", " / ".join(res["flags"]))
    print(f"추이 {len(hist)}개월 · 산출: holdings_concentration_latest.csv · holdings_concentration_history.csv · {os.path.basename(hp)}")


if __name__ == "__main__":
    main()
