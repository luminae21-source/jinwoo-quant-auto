#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
supercycle_monitor.py — 모듈 E 부속: 섹터 수퍼사이클 모니터 (의사결정 지원)
==============================================================================
검증된 감지부만 사용 (자동매매 아님). 진우 재량 판단 보조 = 하이브리드(시스템 감지 + 진우 forward).
모듈 E 자동 룰(supercycle_overlay)은 게이트 FAIL→보류. 본 모니터는 감지신호를 띄우기만 함.

테마 정의 2층:
 · 큐레이션 universe(theme_universe.csv) — 반도체=칩+장비+소재+IDM 38종(투명·편집가능). KRX 세분류가
   못 잡는 장비·소재·삼성전자 포함. 진우 검증(2026-06-05): LED/태양광 제외, 메모리/HBM 코어만.
 · 굵은 산업 자동분류(theme_classify) — 그 외 그룹은 KSIC 중분류 롤업으로 자동.
홀딩스 4-way 자동 태깅: 수퍼사이클 / 감속주의 / BAB드래그 / 정상.
출력: 콘솔 + 모바일 HTML(dashboard_supercycle.html). 데이터=캐시 패널(PC 갱신 시 자동 최신).

⚠️ 신호는 검증된 룰이 아니라 관측 보조. 매수/매도 자동 아님. 가격패널 외부검증 완료(SK하이닉스 원단위 일치).
사용: python supercycle_monitor.py   /   --selftest
"""
import argparse, os, sys, html
import numpy as np, pandas as pd
import supercycle_overlay as E
import score_univ30 as SU
import pit_universe_backtest as PB
import theme_classify as TC

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

REAL_PORTFOLIO = {"247540": "에코프로비엠", "450080": "에코프로머티", "353200": "대덕전자"}
NAME_FALLBACK = {"095340": "ISC", "196170": "알테오젠"}
AUTOSCAN_MIN_MEMBERS = 5
COARSE_MIN_MEMBERS = 5
NEAR_FRAC = 0.5
# 4-way 상태 색 (HTML)
STATUS_COLOR = {"감속주의": "#dc2626", "BAB드래그": "#d97706", "수퍼사이클": "#16a34a", "정상": "#64748b"}


def _cum(ret, win):
    return float((1 + ret.iloc[win]).prod() - 1)


def analyze_basket(ret, basket, mkt, i):
    """바스켓 현 국면 (감지부 + 감속신호). 데이터 ≤ i."""
    if i < 12 or not basket:
        return None
    ex12, br = E._excess_breadth(ret, basket, mkt, i)
    w3 = slice(i - 2, i + 1)
    ex3 = _cum(ret[basket].mean(axis=1), w3) - _cum(mkt, w3)
    ex12_prev = E._excess_breadth(ret, basket, mkt, i - 3)[0] if i >= 15 else np.nan
    accel = (ex12 - ex12_prev) if pd.notna(ex12_prev) else np.nan
    on = bool(E.detect_supercycle(ret, {"_": basket}, mkt, i)["_"])
    if on and pd.notna(ex3) and ex3 < 0:
        phase, flag = "ON·감속/반전주의", "warn"
    elif on and pd.notna(accel) and accel < 0:
        phase, flag = "ON·둔화", "warn"
    elif on:
        phase, flag = "ON·가속", "on"
    elif pd.notna(ex12) and ex12 >= E.THRESH_EXCESS * NEAR_FRAC and pd.notna(br) and br >= E.THRESH_BREADTH * 0.8:
        phase, flag = "관찰(임계 근접)", "near"
    else:
        phase, flag = "—", "off"
    return {"excess_12m": ex12, "breadth": br, "excess_3m": ex3, "accel": accel,
            "state_on": on, "phase": phase, "flag": flag, "n": len(basket)}


def autoscan(ret, mkt, sector_map, cols, i, exclude):
    """등록 외 KRX 세분류 자동스캔 → ON/근접만."""
    by_sec = {}
    for c in cols:
        s = str(sector_map.get(c, ""))
        if s and s != "nan" and s not in exclude:
            by_sec.setdefault(s, []).append(c)
    out = []
    for s, basket in by_sec.items():
        if len(basket) < AUTOSCAN_MIN_MEMBERS:
            continue
        a = analyze_basket(ret, basket, mkt, i)
        if a and a["flag"] in ("on", "warn", "near"):
            out.append((s, a))
    return sorted(out, key=lambda x: -(x[1]["excess_12m"] if pd.notna(x[1]["excess_12m"]) else -9))


def holding_status(theme_an, own_excess, bab):
    """홀딩 4-way 상태. theme_an=소속 테마 국면, own_excess=본인 12M 시장초과, bab=BAB 점수."""
    part = pd.notna(own_excess) and own_excess > 0
    if theme_an and theme_an["state_on"]:
        if theme_an["flag"] == "warn":
            return "감속주의"
        if part and bab is not None and bab < 0:
            return "BAB드래그"
        if part:
            return "수퍼사이클"
    return "정상"


def build(panel, inputs, sector_map, names, i=None, fine_map=None):
    cols = list(panel.columns)
    ret = panel.pct_change(); mkt = ret.mean(axis=1)
    i = (len(panel) - 1) if i is None else i
    dt = panel.index[i]
    cum12 = (1 + ret.iloc[i - 11:i + 1]).prod() - 1
    mkt12 = float((1 + mkt.iloc[i - 11:i + 1]).prod() - 1)

    # 1) 큐레이션 테마 (theme_universe.csv) — 반도체 등
    cur_by_theme, cur_of = TC.load_theme_universe()
    themes_an, theme_of = {}, {}        # theme_of: code→theme
    for th, members in cur_by_theme.items():
        basket = [c for c in members if c in cols]
        an = analyze_basket(ret, basket, mkt, i)
        if an:
            themes_an[th] = an
        for c in basket:
            theme_of[c] = th

    # 2) 굵은 그룹 자동분류 (큐레이션이 덮은 종목은 제외)
    fine_c = fine_map if fine_map is not None else TC.load_fine_map()[0]
    cm_c, groups = TC.coarse_map(fine_c, names)
    coarse_an = {}
    for g, gcodes in groups.items():
        if g == "기타":
            continue
        basket = [c for c in gcodes if c in cols and c not in theme_of]   # 큐레이션 우선
        if len(basket) < COARSE_MIN_MEMBERS:
            continue
        an = analyze_basket(ret, basket, mkt, i)
        if an:
            coarse_an[g] = an
        for c in basket:
            theme_of.setdefault(c, g)
    # 종목→소속 테마 국면 lookup
    def an_of(c):
        th = theme_of.get(c) or cm_c.get(c)
        return themes_an.get(th) or coarse_an.get(th), th

    # 3) 자동스캔 (등록 외 fine 섹터 — 떠오르는 것 조기 포착)
    auto = autoscan(ret, mkt, sector_map, cols, i, exclude=set())

    # 4) 홀딩스 4-way
    watch = {c: names.get(c, c) for c in PB.FIXED18}
    watch.update(REAL_PORTFOLIO)
    comp = SU.member_components_at(dt + pd.Timedelta(days=1), list(watch), panel, inputs)
    hold = []
    for c, nmv in watch.items():
        an, th = an_of(c)
        bab = comp.get(c, {}).get("bab") if comp.get(c) else None
        mom = comp.get(c, {}).get("mom") if comp.get(c) else None
        own_ex = (cum12[c] - mkt12) if (c in getattr(cum12, "index", []) and pd.notna(cum12[c])) else np.nan
        st = holding_status(an, own_ex, bab)
        hold.append({"code": c, "name": nmv, "theme": th, "status": st,
                     "bab": bab, "mom": mom, "own_excess": None if pd.isna(own_ex) else float(own_ex)})
    return {"date": dt, "curated": themes_an, "coarse": coarse_an, "auto": auto, "holdings": hold}


# ---------- 출력 ----------
def _pct(x):
    return "—" if x is None or (isinstance(x, float) and pd.isna(x)) else f"{x:+.0%}"


def render_console(snap):
    print("=" * 66)
    print(f"섹터 수퍼사이클 모니터 — 기준 {snap['date'].date()}  (의사결정 지원·자동매매 아님)")
    print("=" * 66)
    print("\n[큐레이션 테마 — theme_universe.csv]")
    for th, a in snap["curated"].items():
        print(f"  {th:10} {a['phase']:16} | 12M초과 {_pct(a['excess_12m'])} · breadth {_pct(a['breadth'])} "
              f"· 최근3M {_pct(a['excess_3m'])} ({a['n']}종)")
    print("\n[굵은 산업 그룹 — ON/근접만]")
    shown = [(g, a) for g, a in snap["coarse"].items() if a["flag"] in ("on", "warn", "near")]
    for g, a in sorted(shown, key=lambda x: -(x[1]["excess_12m"] if pd.notna(x[1]["excess_12m"]) else -9)):
        print(f"  {g:14} {a['phase']:16} | 12M초과 {_pct(a['excess_12m'])} · breadth {_pct(a['breadth'])}")
    print("\n[홀딩스 4-way 자동 태깅] (production 18 + 실보유)")
    order = {"감속주의": 0, "BAB드래그": 1, "수퍼사이클": 2, "정상": 3}
    for h in sorted(snap["holdings"], key=lambda x: order.get(x["status"], 9)):
        bab = "—" if h["bab"] is None else f"{h['bab']:+.0f}"
        print(f"  [{h['status']:6}] {h['name']:12} 테마 {str(h['theme'] or '-'):14} BAB {bab} · 12M초과 {_pct(h['own_excess'])}")
    print("\n※ 신호는 검증된 룰이 아니라 관측 보조. 매수/매도는 진우 재량. (모듈E 자동룰은 보류·결정메모 §6)")


def render_html(snap, path="dashboard_supercycle.html"):
    cmap = {"on": "#16a34a", "warn": "#d97706", "near": "#0891b2", "off": "#475569"}
    def esc(x): return html.escape(str(x))
    cards = ""
    for th, a in snap["curated"].items():
        col = cmap.get(a["flag"], "#475569")
        cards += f"""<div class="card" style="border-left:5px solid {col}">
          <div class="th">{esc(th)} <span class="ph" style="color:{col}">{esc(a['phase'])}</span></div>
          <div class="row"><span>12M 초과수익</span><b>{_pct(a['excess_12m'])}</b></div>
          <div class="row"><span>breadth</span><b>{_pct(a['breadth'])}</b></div>
          <div class="row"><span>최근 3M 초과 (반전감지)</span><b>{_pct(a['excess_3m'])}</b></div>
          <div class="row"><span>구성</span><b>{a['n']}종</b></div></div>"""
    shown = [(g, a) for g, a in snap["coarse"].items() if a["flag"] in ("on", "warn", "near")]
    crows = ""
    for g, a in sorted(shown, key=lambda x: -(x[1]["excess_12m"] if pd.notna(x[1]["excess_12m"]) else -9)):
        col = cmap.get(a["flag"], "#475569")
        crows += f"""<div class="arow"><span class="dot" style="background:{col}"></span>
          <b>{esc(a['phase'])}</b> · {esc(g)} · 12M {_pct(a['excess_12m'])} · breadth {_pct(a['breadth'])}</div>"""
    if not crows:
        crows = "<div class='arow muted'>ON/근접 굵은그룹 없음</div>"
    order = {"감속주의": 0, "BAB드래그": 1, "수퍼사이클": 2, "정상": 3}
    hrows = ""
    for h in sorted(snap["holdings"], key=lambda x: order.get(x["status"], 9)):
        sc = STATUS_COLOR.get(h["status"], "#64748b")
        bab = "—" if h["bab"] is None else f"{h['bab']:+.0f}"
        hrows += f"""<tr><td><span class="badge" style="background:{sc}">{esc(h['status'])}</span></td>
          <td>{esc(h['name'])}</td><td class="mut">{esc(h['theme'] or '-')[:12]}</td>
          <td style="text-align:center">{bab}</td><td style="text-align:right">{_pct(h['own_excess'])}</td></tr>"""
    out = f"""<!doctype html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>수퍼사이클 모니터</title><style>
*{{box-sizing:border-box;margin:0}}body{{background:#0f172a;color:#e2e8f0;font-family:-apple-system,system-ui,sans-serif;padding:14px;max-width:780px;margin:0 auto}}
h1{{font-size:17px}}.sub{{color:#94a3b8;font-size:12px;margin-bottom:14px}}
.card{{background:#1e293b;border-radius:10px;padding:12px 14px;margin-bottom:10px}}
.th{{font-size:15px;font-weight:700;margin-bottom:8px}}.ph{{font-size:12px;font-weight:600;margin-left:6px}}
.row{{display:flex;justify-content:space-between;font-size:13px;padding:2px 0;color:#cbd5e1}}.row b{{color:#f1f5f9}}
h2{{font-size:13px;color:#94a3b8;margin:16px 0 8px;text-transform:uppercase;letter-spacing:.5px}}
.arow{{background:#1e293b;border-radius:8px;padding:9px 12px;margin-bottom:6px;font-size:13px}}.arow.muted{{color:#64748b}}
.dot{{display:inline-block;width:9px;height:9px;border-radius:50%;margin-right:7px}}
table{{width:100%;border-collapse:collapse;font-size:13px;background:#1e293b;border-radius:10px;overflow:hidden}}
td{{padding:7px 9px;border-bottom:1px solid #334155}}.mut{{color:#94a3b8}}
.badge{{color:#fff;padding:2px 7px;border-radius:6px;font-size:11px;font-weight:600;white-space:nowrap}}
.note{{color:#64748b;font-size:11px;margin-top:14px;line-height:1.5}}
</style></head><body>
<h1>섹터 수퍼사이클 모니터</h1>
<div class="sub">기준 {snap['date'].date()} · 의사결정 지원 (자동매매 아님) · 모듈 E</div>
<h2>큐레이션 테마</h2>{cards}
<h2>굵은 산업 그룹 (ON/근접)</h2>{crows}
<h2>홀딩스 4-way (production 18 + 실보유)</h2>
<table><tr><td>상태</td><td>종목</td><td class="mut">테마</td><td style="text-align:center">BAB</td><td style="text-align:right">12M초과</td></tr>{hrows}</table>
<div class="note">상태: 감속주의=테마 12M↑이나 최근3M 꺾임(트림 고려) · BAB드래그=수퍼사이클 주도주인데 시스템이 베타로 감점 ·
수퍼사이클=상승 참여중 · 정상=해당없음. ⚠️ 검증된 룰 아닌 관측 보조, 모듈E 자동룰 보류(결정메모 §6). 매수/매도 진우 재량.</div>
</body></html>"""
    with open(path, "w", encoding="utf-8") as f:
        f.write(out)
    return path


def _selftest():
    ok = 0
    rng = np.random.default_rng(5); Tm = 50
    idx = pd.date_range("2021-01-31", periods=Tm, freq="ME")
    semi = [f"S{i:05d}" for i in range(6)]; other = [f"O{i:05d}" for i in range(15)]
    cols = semi + other
    px = pd.DataFrame(index=idx, columns=cols, dtype=float)
    for c in cols: px[c] = 1000.0
    for t in range(1, Tm):
        for c in cols:
            dr = rng.normal(0.12, 0.07) if (c in semi and 20 <= t <= 40) else rng.normal(0.004, 0.025)
            px.loc[idx[t], c] = px.loc[idx[t-1], c] * (1 + dr)
    sector_map = {**{c: "반도체 제조업" for c in semi}, **{c: f"기타{i%5}" for i, c in enumerate(other)}}
    names = {c: c for c in cols}
    inputs = pd.DataFrame([dict(code=c, fiscal_year=fy, F=7, accrual=0.0, noa_ratio=0.7)
                           for c in cols for fy in range(2019, 2026)])
    # 4-way 직접 검증
    an_on = {"state_on": True, "flag": "on"}
    an_warn = {"state_on": True, "flag": "warn"}
    assert holding_status(an_on, 0.5, -2.0) == "BAB드래그"; ok += 1
    assert holding_status(an_on, 0.5, 1.0) == "수퍼사이클"; ok += 1
    assert holding_status(an_warn, 0.5, -2.0) == "감속주의"; ok += 1
    assert holding_status(an_on, -0.1, -2.0) == "정상"; ok += 1     # 미참여
    assert holding_status(None, 0.5, 1.0) == "정상"; ok += 1
    snap = build(px, inputs, sector_map, names, i=34, fine_map=sector_map)
    # 합성 패널엔 실제 티커(FIXED18) 부재 → 그룹 감지 + 홀딩 status 필드만 확인 (4-way 로직은 위 직접검증)
    assert snap["coarse"].get("반도체/전자", {}).get("state_on"), "합성 SEMI 그룹 감지 실패"; ok += 1
    assert snap["holdings"] and all("status" in h for h in snap["holdings"]); ok += 1
    import tempfile
    p = render_html(snap, path=os.path.join(tempfile.gettempdir(), "_scm_test.html"))
    assert os.path.exists(p) and os.path.getsize(p) > 500; ok += 1
    try: os.remove(p)
    except OSError: pass
    print(f"[OK] supercycle_monitor selftest 통과 ({ok} checks)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices", default="kospi_monthly_prices.csv")
    ap.add_argument("--inputs", default="score_inputs_univ.csv")
    ap.add_argument("--liquidity", default="liquidity_sector.csv")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    for f in (a.prices, a.inputs, a.liquidity):
        if not os.path.exists(f):
            raise SystemExit(f"{f} 없음")
    panel = pd.read_csv(a.prices, index_col=0, parse_dates=True)
    panel.columns = [str(c).zfill(6) for c in panel.columns]
    inputs = pd.read_csv(a.inputs, dtype={"code": str}); inputs["code"] = inputs["code"].str.zfill(6)
    ls = pd.read_csv(a.liquidity, dtype={"code": str}); ls["code"] = ls["code"].str.zfill(6)
    sector_map = dict(zip(ls["code"], ls["sector"]))
    names = dict(zip(ls["code"], ls["name"]))
    if "name" in inputs.columns:
        for c, n in zip(inputs["code"], inputs["name"]):
            names.setdefault(c, n)
    names.update(NAME_FALLBACK)
    snap = build(panel, inputs, sector_map, names)
    render_console(snap)
    path = render_html(snap)
    print("\nHTML 대시보드 저장: " + path)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
