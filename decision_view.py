#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
decision_view.py — 의사결정 종합 스코어카드 (열거식 → 강·약 한 줄)
==============================================================================
목적: 흩어진 메뉴(테마·풀·매수·보유)를 종목별 한 줄로 합쳐, 4개 렌즈를 색으로 보고
      '강한가/약한가, 지금 살 자리인가'를 즉시 판단하게 한다.
      ⚠️ 매수신호 아님 — 시스템 신호 종합. 판단·책임은 진우(수익 우선 철학 존중).

4 렌즈:
  품질  = production 점수/등급 (stock_pool_latest)         S+/S🟢 · A🟡 · B↓⚪
  주도성= 종목 테마의 heat (theme_heat_latest)             ON+상위🟢 · 상위🟡 · 비주도🔴
  타이밍= 주봉 진입 상태 (entry_signals)                   돌파/셋업🟢 · 임박🟡 · 관망⚪
  리스크= 12M 시장초과(과열/부진) + 보유 쏠림기여            과열🔴 / 부진🔴 / 보통⚪
종합  = 위를 규칙으로 합친 강·약 한 줄(투명·고정 규칙).
대상  = 보유 18종 ∪ (S+/S ∩ 뜨거운 테마). 산출 CSV + HTML.
무수정: production·heat·발굴트랙. 사용: python decision_view.py [--selftest]
"""
import argparse, os, sys, types
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
HOLD = [('삼양식품','003230'),('두산에너빌리티','034020'),('NH투자증권','005940'),('ISC','095340'),
        ('알테오젠','196170'),('한화에어로','012450'),('한미반도체','042700'),('SK하이닉스','000660'),
        ('삼성물산','028260'),('삼성전자','005930'),('NAVER','035420'),('아모레퍼시픽','090430'),
        ('KT&G','033780'),('KB금융','105560'),('삼성SDI','006400'),('기아','000270'),
        ('카카오','035720'),('LIG넥스원','079550')]
SEMI_CORE = {"005930","000660","006400","095340","042700"}


def load_my_holdings():
    """실보유 (my_holdings.csv) → (set(codes), {code:name}). 주석(#)·빈 줄·헤더 무시."""
    p = os.path.join(HERE, "my_holdings.csv"); codes = set(); names = {}
    if not os.path.exists(p):
        return codes, names
    for line in open(p, encoding="utf-8-sig"):
        line = line.strip()
        if not line or line.startswith("#") or line.lower().startswith("code,"):
            continue
        parts = [x.strip() for x in line.split(",")]
        c = parts[0].zfill(6)
        if c.isdigit():
            codes.add(c)
            if len(parts) > 1 and parts[1]:
                names[c] = parts[1]
    return codes, names
OVERHEAT, LAGGARD = 1.50, -0.30   # 12M초과 과열/부진 기준


def _load_src(fname, modname):
    path = os.path.join(HERE, fname); src = open(path, encoding="utf-8").read()
    m = types.ModuleType(modname); m.__file__ = path; sys.modules[modname] = m
    sys.dont_write_bytecode = True; exec(compile(src, path, "exec"), m.__dict__); return m


def verdict(q, h, t, x, held):
    """q∈{strong,mid,weak,na} h∈{hot,warm,cold} t∈{돌파,셋업,임박,관망,na} x=ex12(float|nan)."""
    over = pd.notna(x) and x > OVERHEAT
    lag = pd.notna(x) and x < LAGGARD
    buyable = t in ("돌파확인", "돌파(거래량미달)", "셋업")
    if h == "cold" and lag:
        return "약 — thesis/트림 점검", "bad"
    if buyable and h in ("hot", "warm"):
        return "후보 — 셋업 진행(핸드오프 검토)", "good"
    if over and t == "관망":
        return "강하나 과열 — 눌림/셋업 대기", "warn"
    if q == "strong" and h in ("hot", "warm"):
        return "주도 정렬 — 관찰 유지", "good"
    if lag:
        return "부진 — 점검", "bad"
    if h == "cold":
        return "비주도 — 관찰", "mut"
    return "중립 — 관찰", "mut"


def build():
    E = _load_src("supercycle_overlay.py", "supercycle_overlay")
    TC = _load_src("theme_classify.py", "theme_classify")
    TH = _load_src("theme_heat.py", "theme_heat")
    ES = _load_src("entry_signals.py", "entry_signals")

    pool = pd.read_csv(os.path.join(HERE, "stock_pool_latest.csv"), dtype={"code": str})
    pool["code"] = pool["code"].str.zfill(6)
    heat = pd.read_csv(os.path.join(HERE, "theme_heat_latest.csv"))
    adtv_map = dict(zip(pool["code"].str.zfill(6), pd.to_numeric(pool.get("adtv_ek"), errors="coerce")))
    hot_top = set(heat.sort_values("heat_score", ascending=False).head(6)["theme"])
    sc_on = set(heat[heat["supercycle"] == True]["theme"])
    fine, name = TC.load_fine_map()
    panel = TH.load_panel(); ret = panel.pct_change(); mkt = ret.mean(axis=1); i = len(panel)-1
    mkt12 = float((1 + mkt.iloc[i-11:i+1]).prod()-1); mkt6 = float((1 + mkt.iloc[i-5:i+1]).prod()-1)
    regime = TH.load_regime(); reg_last = max(regime) if regime else ""
    rstate = (regime.get(panel.index[i].strftime("%Y-%m")) or (regime.get(reg_last) if regime else "")) + (f" · regime기준 {reg_last}" if reg_last else "")

    # 대상 = 보유 ∪ (S+/S ∩ hot)
    held_codes = {c for _, c in HOLD}
    inter = pool[(pool.grade.isin(["S+","S"])) & (pool.theme.isin(hot_top | {"반도체"}))]
    mine_codes, mine_names = load_my_holdings()
    codes = list(dict.fromkeys([c for _, c in HOLD] + inter["code"].tolist() + sorted(mine_codes)))
    nm_by = {c: n for n, c in HOLD}; nm_by.update(dict(zip(pool.code, pool.name))); nm_by.update(mine_names)
    daily = TH.load_daily_for(codes)

    def estate(c):
        if c not in daily or len(daily[c]) < 60:
            return "na"
        g = daily[c]; w = g.resample("W-FRI").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna(subset=["close"])
        if len(w) < 40:
            return "na"
        rs = float(w["close"].iloc[-1]/w["close"].iloc[-27]-1) - mkt6 if len(w) >= 27 else 0.0
        return ES.plan(w, rs, rstate)["state_ko"]

    def mgmt(c, K=2.5):
        """ATR Chandelier 트레일 손절(고점−k×ATR)+40주선 백업 → (상태, 손절선)."""
        if c not in daily or len(daily[c]) < 60:
            return "na", None
        w = daily[c].resample("W-FRI").agg({"open":"first","high":"max","low":"min","close":"last","volume":"sum"}).dropna(subset=["close"])
        if len(w) < 40:
            return "na", None
        h, l, cl = w["high"], w["low"], w["close"]; pc = cl.shift(1)
        tr = pd.concat([h-l, (h-pc).abs(), (l-pc).abs()], axis=1).max(axis=1)
        atr = tr.rolling(14, min_periods=7).mean()
        ma40 = cl.rolling(40, min_periods=20).mean()
        hh = h.rolling(22, min_periods=10).max()
        chand = float(hh.iloc[-1] - K*atr.iloc[-1]); px = float(cl.iloc[-1]); m40 = float(ma40.iloc[-1])
        rising = ma40.iloc[-1] > ma40.iloc[-5] if len(ma40) > 5 and pd.notna(ma40.iloc[-5]) else False
        if pd.isna(m40) or pd.isna(chand):
            return "na", None
        if px < m40:
            return "추세이탈→축소", round(m40, 1)
        if px < chand:
            return "손절선이탈→축소", round(chand, 1)
        return ("보유OK" if rising else "추세둔화"), round(max(chand, m40), 1)

    rows = []
    for c in codes:
        prow = pool[pool.code == c]
        grade = prow["grade"].iloc[0] if len(prow) else "na"
        score = float(prow["score"].iloc[0]) if len(prow) else np.nan
        # ex12: pool 우선, 없으면 패널
        if len(prow):
            ex12 = float(prow["ex12_pct"].iloc[0])
        else:
            s = panel[c].dropna() if c in panel.columns else pd.Series(dtype=float)
            ex12 = float(s.iloc[-1]/s.iloc[-13]-1) - mkt12 if len(s) >= 13 else np.nan
        theme_b = TC.coarse_sector(name.get(c, nm_by.get(c, "")), fine.get(c, ""))
        h = "hot" if (theme_b in hot_top and theme_b in sc_on) else ("warm" if theme_b in hot_top else "cold")
        q = "strong" if grade in ("S+","S") else ("mid" if grade == "A" else ("weak" if grade in ("B","C","D","F") else "na"))
        t = estate(c); mstate, stopline = mgmt(c)
        sel18 = c in held_codes; mine = c in mine_codes
        vtext, vcls = verdict(q, h, t, ex12, sel18)
        rows.append({"code": c, "name": nm_by.get(c, c), "theme": theme_b, "held": sel18, "mine": mine,
                     "grade": grade, "score": score, "heat": h, "entry": t,
                     "ex12_%": round(ex12*100,0) if pd.notna(ex12) else np.nan,
                     "semi_core": c in SEMI_CORE, "mgmt": mstate, "stop_line": stopline, "adtv": adtv_map.get(c), "verdict": vtext, "vcls": vcls})
    df = pd.DataFrame(rows)
    return df, panel.index[i], rstate, hot_top, sc_on


def regime_age_days(rstate, asof):
    """rstate의 'regime기준 YYYY-MM'과 asof 비교 → (경과일, 'YYYY-MM') or (None,None)."""
    import re, datetime
    ms = re.findall(r"\d{4}-\d{2}", rstate or "")
    if not ms:
        return None, None
    key = ms[-1]
    ry, rm = map(int, key.split("-"))
    reg_date = datetime.date(ry, rm, 1)
    ad = asof.date() if hasattr(asof, "date") else asof
    return (ad - reg_date).days, key


def render(df, asof, rstate):
    datestr = asof.strftime("%Y-%m-%d")
    _rage, _rkey = regime_age_days(rstate, asof)
    stale_banner = ('<div class="guard">\u26a0\ufe0f <b>regime 신선도 경고</b>: 마지막 국면판정(%s)이 %d일 경과(&gt;35일) \u2014 국면 오래됨, 수기/PC 갱신 권장.</div>' % (_rkey, _rage)) if (_rage is not None and _rage > 35) else ""
    qB = {"strong":'<span class="b g">S+/S</span>',"mid":'<span class="b y">A</span>',"weak":'<span class="b m">B↓</span>',"na":'<span class="b m">–</span>'}
    hB = {"hot":'<span class="b g">ON·주도</span>',"warm":'<span class="b y">상위</span>',"cold":'<span class="b r">비주도</span>'}
    def tB(t):
        if t in ("돌파확인","돌파(거래량미달)"): return '<span class="b g">돌파</span>'
        if t=="셋업": return '<span class="b g">셋업</span>'
        if t=="트리거임박": return '<span class="b y">임박</span>'
        if t=="관망": return '<span class="b mut">관망</span>'
        return '<span class="b m">–</span>'
    def xB(x, held):
        if pd.isna(x): return '–'
        if x>OVERHEAT*100: return f'<span class="b r">과열 +{x:.0f}%</span>'
        if x<LAGGARD*100: return f'<span class="b r">부진 {x:.0f}%</span>'
        return f'<span class="b mut">{x:+.0f}%</span>'
    # 간결화: q 재계산 헬퍼
    def _q(g): return "strong" if g in ("S+","S") else ("mid" if g=="A" else ("weak" if g in ("B","C","D","F") else "na"))
    def mB(r):
        st = r.get("mgmt", "na"); sl = r.get("stop_line")
        slt = "" if (sl is None or (isinstance(sl, float) and pd.isna(sl))) else f' {float(sl):,.0f}'
        cls = {"보유OK":"g","추세둔화":"y","손절선이탈→축소":"r","추세이탈→축소":"r"}.get(st, "m")
        lbl = {"보유OK":"보유OK","추세둔화":"추세둔화","손절선이탈→축소":"손절↓","추세이탈→축소":"추세이탈","na":"–"}.get(st, st)
        return f'<span class="b {cls}">{lbl}</span><span class="c">{slt}</span>'
    def rowhtml(r):
        return (f'<tr class="v-{r["vcls"]}"><td><b>{r["name"]}</b> <span class="c">{r["code"]}</span>'
                f'{" 🟦보유" if r.get("mine") else ""}{" 🔻쏠림" if r["semi_core"] else ""}{" 🔸저유동" if (pd.notna(r.get("adtv")) and r.get("adtv") is not None and float(r.get("adtv") or 1e9) < 50) else ""}</td><td>{r["theme"]}</td>'
                f'<td>{qB[_q(r["grade"])]}</td><td>{hB[r["heat"]]}</td><td>{tB(r["entry"])}</td>'
                f'<td>{mB(r)}</td>'
                f'<td class="num">{xB(r["ex12_%"], r["held"])}</td><td class="vd">{r["verdict"]}</td></tr>')
    mine = df[df.mine].sort_values("vcls") if "mine" in df.columns else df.iloc[0:0]
    sel = df[df.held].sort_values("vcls")
    cand = df[(~df.held) & (~df.get("mine", False))].sort_values(["vcls","score"], ascending=[True, False])
    def section(sub, title, note):
        body = "".join(rowhtml(r) for _, r in sub.iterrows())
        return (f'<h2>{title} <span class="mut">({len(sub)})</span></h2><div class="note">{note}</div>'
                f'<table><thead><tr><th>종목</th><th>테마</th><th>품질</th><th>주도성</th><th>타이밍</th><th>관리(손절선)</th>'
                f'<th class="num">12M초과</th><th>종합 판단</th></tr></thead><tbody>{body}</tbody></table>')
    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>의사결정 종합 뷰 — {datestr}</title>
<style>
:root{{--bg:#0f1115;--card:#181b22;--ink:#e8eaed;--mut:#9aa0aa;--line:#262a33;--acc:#ff7a45;--g:#3fb37a;--y:#e0b020;--r:#e2606a}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,'Segoe UI','Malgun Gothic',sans-serif;padding:18px;line-height:1.5;max-width:920px;margin:0 auto}}
h1{{font-size:19px;margin:0 0 2px}}h2{{font-size:14px;color:#fff;border-left:3px solid var(--acc);padding-left:8px;margin:20px 0 4px}}
.sub{{color:var(--mut);font-size:12px}}.note{{color:var(--mut);font-size:11.5px;margin-bottom:6px}}
.guard{{background:#2a1d12;border:1px solid #5a3a1f;color:#ffc6a3;border-radius:8px;padding:9px 12px;font-size:12.5px;margin:10px 0 4px}}
table{{width:100%;border-collapse:collapse;font-size:12px;margin-top:4px}}th,td{{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}}
th{{color:var(--mut);font-size:11px}}.num{{text-align:right;font-variant-numeric:tabular-nums}}.c{{color:var(--mut);font-family:monospace;font-size:10.5px}}
.b{{font-size:11px;border-radius:5px;padding:1px 6px;white-space:nowrap}}
.b.g{{background:#143b2a;color:#7ee0ad}}.b.y{{background:#3b3214;color:#ffd479}}.b.r{{background:#3a1618;color:#ff9aa0}}.b.m{{background:#22262f;color:#7a818c}}.b.mut{{background:#1d2129;color:#9aa0aa}}
.vd{{font-weight:600}}
.v-good .vd{{color:#7ee0ad}}.v-warn .vd{{color:#ffd479}}.v-bad .vd{{color:#ff9aa0}}.v-mut .vd{{color:#9aa0aa}}
.foot{{margin-top:18px;color:#5a6068;font-size:11px;line-height:1.6;border-top:1px solid var(--line);padding-top:10px}}
</style></head><body>
<h1>🧭 의사결정 종합 뷰</h1>
<div class="sub">기준 {datestr} · regime {rstate} · 4렌즈(품질·주도성·타이밍·리스크) 종합 · 보유 ∪ (S+/S∩뜨거운테마)</div>
<div class="guard">⚠️ <b>매수신호 아님</b> — 시스템 신호 종합. '종합 판단'은 고정 규칙으로 자동 산출. 추격매수 금지·−8% 손절. 판단·책임은 진우.</div>
{stale_banner}
{(section(mine, "① 실보유 (실제 강·약 점검)", "my_holdings.csv 기반 실제 보유. '약/부진'은 thesis·무효화 트리거 점검 1순위.") if len(mine) else '<h2>① 실보유</h2><div class="note">실보유 미입력 — <b>my_holdings.csv</b>에 실제 보유 종목을 넣으면 여기에 강·약 점검이 표시됩니다.</div>')}
{section(sel, "② production 선별 18 (모델 픽 · 실보유 아님)", "v3.7.2 엔진(가치·퀄리티·저베타) 선별 바스켓. '비주도/약'=이 레짐에서 선별 특성이지 매도신호 아님. 🟦=실보유 겹침.")}
{section(cand, "③ 신규 후보 풀 (S+/S ∩ 뜨거운 테마)", "품질+주도 둘 다 충족. '후보-셋업'만 핸드오프 검토 — 나머지는 관망(눌림 대기).")}
<div class="foot">품질=production 점수(S+≥14·S≥12·A≥9). 주도성=종목 테마 heat(ON=supercycle+상위6). 타이밍=주봉 entry_signals. 리스크=12M 시장초과(과열&gt;+150%·부진&lt;−30%)+반도체 쏠림기여.<br>
종합 규칙(고정): 비주도&부진→약 · 셋업&주도→후보 · 과열&관망→눌림대기 · 강&주도→관찰. 백테스트·과거치를 forward로 쓰지 않음. 결정·책임은 진우.</div>
</body></html>"""


def _selftest():
    ok = 0
    assert verdict("strong","hot","셋업",1.0,False)[1]=="good"; ok+=1          # 셋업+주도→후보
    assert verdict("strong","hot","관망",2.0,True)[1]=="warn"; ok+=1           # 과열+관망→대기
    assert verdict("weak","cold","관망",-0.8,True)[1]=="bad"; ok+=1            # 비주도+부진→약
    assert verdict("strong","hot","관망",0.3,True)[1]=="good"; ok+=1           # 강+주도→관찰
    assert verdict("mid","cold","관망",0.0,False)[1]=="mut"; ok+=1            # 비주도 중립
    print(f"✅ decision_view 셀프테스트 통과 ({ok}/5): verdict 규칙(후보·대기·약·관찰·중립)")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest(); return
    df, asof, rstate, hot, sc = build()
    df.drop(columns=["vcls"]).to_csv(os.path.join(HERE, "decision_view_latest.csv"), index=False, encoding="utf-8-sig")
    out = os.path.join(HERE, f"진우퀀트_의사결정뷰_{asof.strftime('%Y-%m-%d')}.html")
    open(out, "w", encoding="utf-8").write(render(df, asof, rstate))
    open(os.path.join(HERE, "진우퀀트_의사결정뷰_LATEST.html"), "w", encoding="utf-8").write(render(df, asof, rstate))
    from collections import Counter
    sel = df[df.held]; cand = df[(~df.held) & (~df.get("mine", False))]; mine = df[df.get("mine", False)]
    print(f"기준 {asof.strftime('%Y-%m-%d')} · regime {rstate} · 대상 {len(df)}종 (선별18 {len(sel)}·후보 {len(cand)}·실보유 {len(mine)})")
    _age, _rk = regime_age_days(rstate, asof)
    if _age is not None and _age > 35:
        print("\u26a0\ufe0f regime 신선도 경고: 마지막 국면(%s) %d일 경과(>35일) \u2014 갱신 권장" % (_rk, _age))
    print("선별18 종합:", dict(Counter(sel['verdict'])))
    print("후보 종합:", dict(Counter(cand['verdict'])))
    if len(mine): print("실보유 종합:", dict(Counter(mine['verdict'])))
    print(f"산출: decision_view_latest.csv · {os.path.basename(out)}")


if __name__ == "__main__":
    main()
