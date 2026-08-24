#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
trend_monitor.py — 추세 모니터 (heat·진입 시계열)
==============================================================================
목적: 보유 집중도 추이와 같은 방식으로 **heat(주도 테마)·진입(셋업/돌파 브레드스)**의
      월별 변화를 추적. "지금 무엇이 뜨고, 살 자리가 늘고 있나/줄고 있나"를 시계열로.
      ⚠️ 매수신호 아님. 발굴·진입은 후보·규율, 결정은 진우.

산출:
  trend_history_heat.csv  — 월별 #1테마·heat·supercycle 브레드스·핵심테마 exc_3m
  trend_history_entry.csv — 월별 보유 진입상태 카운트(관망/셋업/임박/돌파)+regime
  추세모니터_YYYY-MM-DD.html — 주도테마 회전·테마/진입 브레드스 차트
재사용(무수정): theme_heat(compute_theme_heat·load_*) + entry_signals + regime_v40.
사용: python trend_monitor.py [--selftest] [--months N]
"""
import argparse, os, sys, types
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
MONTHS = 18
KEY_THEMES = ["반도체/전자", "2차전지", "바이오/제약", "우주항공/방산", "원자력/원전", "로봇/자동화"]
HOLD = [('삼양식품','003230'),('두산에너빌리티','034020'),('NH투자증권','005940'),('ISC','095340'),
        ('알테오젠','196170'),('한화에어로','012450'),('한미반도체','042700'),('SK하이닉스','000660'),
        ('삼성물산','028260'),('삼성전자','005930'),('NAVER','035420'),('아모레퍼시픽','090430'),
        ('KT&G','033780'),('KB금융','105560'),('삼성SDI','006400'),('기아','000270'),
        ('카카오','035720'),('LIG넥스원','079550')]


def _load_src(fname, modname):
    path = os.path.join(HERE, fname); src = open(path, encoding="utf-8").read()
    m = types.ModuleType(modname); m.__file__ = path; sys.modules[modname] = m
    sys.dont_write_bytecode = True; exec(compile(src, path, "exec"), m.__dict__); return m


def _engines():
    E = _load_src("supercycle_overlay.py", "supercycle_overlay")
    TC = _load_src("theme_classify.py", "theme_classify")
    TH = _load_src("theme_heat.py", "theme_heat")
    ES = _load_src("entry_signals.py", "entry_signals")
    return E, TC, TH, ES


def heat_history(panel, fine, name, E, TC, TH, months=MONTHS):
    rows = []
    start = max(13, len(panel) - months)
    for i in range(start, len(panel)):
        df, _, _ = TH.compute_theme_heat(panel, fine, name, E, TC, i=i)
        if df.empty:
            continue
        top = df.iloc[0]
        row = {"month": panel.index[i].strftime("%Y-%m"),
               "top1_theme": top["theme"], "top1_heat": round(float(top["heat_score"]), 0),
               "supercycle_on": int(df["supercycle"].sum())}
        em = df.set_index("theme")["exc_3m"]
        for t in KEY_THEMES:
            row[f"exc3_{t}"] = round(float(em[t]) * 100, 1) if t in em.index else np.nan
        rows.append(row)
    return pd.DataFrame(rows)


def entry_history(panel, regime, ES, TH, hold=HOLD, months=MONTHS):
    daily = TH.load_daily_for([c for _, c in hold])
    wk = {}
    for c in [c for _, c in hold]:
        if c in daily and len(daily[c]) >= 60:
            wk[c] = daily[c].resample("W-FRI").agg({"open":"first","high":"max","low":"min",
                                                     "close":"last","volume":"sum"}).dropna(subset=["close"])
    ret = panel.pct_change(); mkt = ret.mean(axis=1)
    last_reg = regime.get(max(regime)) if regime else ""
    rows = []
    start = max(13, len(panel) - months)
    for i in range(start, len(panel)):
        d = panel.index[i]; ym = d.strftime("%Y-%m")
        rstate = regime.get(ym, last_reg)
        mkt6 = float((1 + mkt.iloc[i - 5:i + 1]).prod() - 1)
        cnt = {"관망": 0, "셋업": 0, "트리거임박": 0, "돌파확인": 0, "돌파(거래량미달)": 0}
        for c, w in wk.items():
            ws = w[w.index <= d]
            if len(ws) < 40:
                continue
            rs = float(ws["close"].iloc[-1] / ws["close"].iloc[-27] - 1) - mkt6 if len(ws) >= 27 else 0.0
            st = ES.plan(ws, rs, rstate)["state_ko"]
            cnt[st] = cnt.get(st, 0) + 1
        buyable = cnt["셋업"] + cnt["트리거임박"] + cnt["돌파확인"] + cnt["돌파(거래량미달)"]
        rows.append({"month": ym, "regime": rstate, "관망": cnt["관망"], "셋업": cnt["셋업"],
                     "임박": cnt["트리거임박"], "돌파": cnt["돌파확인"] + cnt["돌파(거래량미달)"],
                     "buyable": buyable, "n": sum(cnt.values())})
    return pd.DataFrame(rows)


def _spark(vals, w=520, h=64, color="#ff7a45", pad=5):
    vals = [v for v in vals if v is not None and not (isinstance(v, float) and np.isnan(v))]
    if len(vals) < 2:
        return ""
    mn, mx = min(vals), max(vals); rng = (mx - mn) or 1
    pts = " ".join(f"{pad+(w-2*pad)*k/(len(vals)-1):.1f},{pad+(h-2*pad)*(1-(v-mn)/rng):.1f}" for k, v in enumerate(vals))
    return f'<polyline fill="none" stroke="{color}" stroke-width="2" points="{pts}"/>'


def write_html(hh, eh, asof):
    datestr = asof.strftime("%Y-%m-%d")
    REGC = {"RISK_ON": "#2e7d50", "NEUTRAL": "#9a7a28", "RISK_OFF": "#a3373c", "": "#444"}
    # 주도테마 회전 표
    rot = "".join(f"<tr><td>{r['month']}</td><td><b>{r['top1_theme']}</b></td>"
                  f"<td class='num'>{r['top1_heat']:.0f}</td><td class='num'>{r['supercycle_on']}</td></tr>"
                  for _, r in hh.tail(12).iterrows())
    sc_line = _spark(hh["supercycle_on"].tolist(), color="#7ee0ad")
    semi_line = _spark(hh["exc3_반도체/전자"].tolist(), color="#ff7a45")
    bio_line = _spark(hh["exc3_바이오/제약"].tolist(), color="#6b9bd1")
    # 진입 브레드스
    buy_line = _spark(eh["buyable"].tolist(), color="#ffd479")
    reg_cells = "".join(f"<span title='{r['month']} {r['regime']}' style='display:inline-block;width:{max(6,int(480/len(eh)))}px;height:12px;background:{REGC.get(r['regime'],'#444')}'></span>" for _, r in eh.iterrows())
    erows = "".join(f"<tr><td>{r['month']}</td><td>{r['regime']}</td><td class='num'>{r['돌파']}</td>"
                    f"<td class='num'>{r['임박']}</td><td class='num'>{r['셋업']}</td><td class='num'>{r['관망']}</td>"
                    f"<td class='num'><b>{r['buyable']}</b>/{r['n']}</td></tr>" for _, r in eh.tail(12).iterrows())
    lab = f"{hh['month'].iloc[0]} → {hh['month'].iloc[-1]}" if len(hh) else ""
    cur_top = hh['top1_theme'].iloc[-1] if len(hh) else "-"
    cur_buy = int(eh['buyable'].iloc[-1]) if len(eh) else 0
    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>추세 모니터 — {datestr}</title>
<style>
:root{{--bg:#0f1115;--card:#181b22;--ink:#e8eaed;--mut:#9aa0aa;--line:#262a33;--acc:#ff7a45}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,'Segoe UI','Malgun Gothic',sans-serif;padding:20px;line-height:1.5}}
h1{{font-size:19px;margin:0 0 2px}}h2{{font-size:14px;color:#fff;border-left:3px solid var(--acc);padding-left:8px;margin:20px 0 8px}}
.sub{{color:var(--mut);font-size:12px;margin-bottom:8px}}
.kpis{{display:flex;gap:9px;flex-wrap:wrap;margin:8px 0}}.kpi{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:9px 13px;min-width:130px}}
.kpi b{{display:block;font-size:16px;color:var(--acc)}}.kpi span{{font-size:11px;color:var(--mut)}}
.box{{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:12px 14px;margin:8px 0}}
.tleg{{display:flex;gap:14px;font-size:11.5px;color:var(--mut);margin-bottom:6px;flex-wrap:wrap}}.tleg i{{display:inline-block;width:12px;height:3px;vertical-align:middle;margin-right:4px}}
table{{width:100%;border-collapse:collapse;font-size:12px;margin-top:5px}}th,td{{padding:6px 8px;border-bottom:1px solid var(--line);text-align:left}}th{{color:var(--mut);font-size:11px}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}
svg{{width:100%;height:auto;background:#11141a;border-radius:6px}}
.foot{{margin-top:18px;color:#5a6068;font-size:11px;line-height:1.6;border-top:1px solid var(--line);padding-top:10px}}
</style></head><body>
<h1>📈 추세 모니터 (heat · 진입)</h1>
<div class="sub">기준 {asof.strftime('%Y-%m')} · 추이 {lab} · 보유 18종 진입 브레드스</div>
<div class="kpis">
  <div class="kpi"><b>{cur_top}</b><span>현 #1 heat 테마</span></div>
  <div class="kpi"><b>{int(hh['supercycle_on'].iloc[-1]) if len(hh) else 0}</b><span>supercycle ON 테마수</span></div>
  <div class="kpi"><b>{cur_buy}/18</b><span>보유 중 매수가능 상태</span></div>
</div>

<h2>① heat — 주도 테마 회전 & 브레드스 ({lab})</h2>
<div class="box">
  <div class="tleg"><span><i style="background:#7ee0ad"></i>supercycle ON 테마수</span><span><i style="background:#ff7a45"></i>반도체/전자 3m초과</span><span><i style="background:#6b9bd1"></i>바이오/제약 3m초과</span></div>
  <svg viewBox="0 0 520 64" preserveAspectRatio="none">{sc_line}{semi_line}{bio_line}</svg>
  <table><thead><tr><th>월</th><th>#1 테마</th><th class="num">heat</th><th class="num">SC ON</th></tr></thead><tbody>{rot}</tbody></table>
</div>

<h2>② 진입 — 보유 매수가능 브레드스 + regime ({lab})</h2>
<div class="box">
  <div class="tleg"><span><i style="background:#ffd479"></i>매수가능(셋업+임박+돌파) 종목수</span></div>
  <svg viewBox="0 0 520 64" preserveAspectRatio="none">{buy_line}</svg>
  <div class="tleg" style="margin-top:8px">regime: {reg_cells} <span style="margin-left:6px">🟩RISK_ON 🟨NEUTRAL 🟥RISK_OFF</span></div>
  <table><thead><tr><th>월</th><th>regime</th><th class="num">돌파</th><th class="num">임박</th><th class="num">셋업</th><th class="num">관망</th><th class="num">매수가능</th></tr></thead><tbody>{erows}</tbody></table>
</div>
<div class="foot">heat=compute_theme_heat as-of 월별 재계산. 진입=보유 18종 주봉 entry_signals as-of 월말. supercycle/regime=v40 엔진. 추이=현 정의를 과거 적용·매월 연장.<br>
⚠️ 매수신호 아님 — 후보·규율·측정만. 백테스트·과거치를 forward로 쓰지 않음. 결정·책임은 진우.</div>
</body></html>"""


def _selftest():
    E, TC, TH, ES = _engines()
    panel = TH.load_panel(); fine, name = TC.load_fine_map()
    hh = heat_history(panel, fine, name, E, TC, TH, months=6)
    assert len(hh) >= 3 and "top1_theme" in hh.columns and hh["month"].is_monotonic_increasing
    assert hh["supercycle_on"].notna().all()
    print(f"✅ trend_monitor 셀프테스트: heat 추이 {len(hh)}개월·#1테마·SC브레드스 OK")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--months", type=int, default=MONTHS)
    a = ap.parse_args()
    if a.selftest:
        _selftest(); return
    E, TC, TH, ES = _engines()
    panel = TH.load_panel(); fine, name = TC.load_fine_map(); regime = TH.load_regime()
    hh = heat_history(panel, fine, name, E, TC, TH, months=a.months)
    eh = entry_history(panel, regime, ES, TH, months=a.months)
    hh.to_csv(os.path.join(HERE, "trend_history_heat.csv"), index=False, encoding="utf-8-sig")
    eh.to_csv(os.path.join(HERE, "trend_history_entry.csv"), index=False, encoding="utf-8-sig")
    asof = panel.index[-1]
    hp = os.path.join(HERE, f"추세모니터_{asof.strftime('%Y-%m-%d')}.html")
    open(hp, "w", encoding="utf-8").write(write_html(hh, eh, asof))
    print("=== heat 주도테마 회전(최근) ===")
    print(hh.tail(8)[["month","top1_theme","top1_heat","supercycle_on"]].to_string(index=False))
    print("\n=== 진입 브레드스(최근) ===")
    print(eh.tail(8)[["month","regime","돌파","임박","셋업","관망","buyable"]].to_string(index=False))
    print(f"\n산출: trend_history_heat.csv · trend_history_entry.csv · {os.path.basename(hp)}")


if __name__ == "__main__":
    main()
