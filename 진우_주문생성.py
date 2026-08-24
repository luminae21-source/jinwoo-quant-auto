#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우_주문생성.py — 신호→주문 생성 엔진 (반자동 트레이딩의 핵심)

발굴 후보(진우_타점발굴.csv) + 자본 + 보유현황(진우_모의매매장.csv) → **오늘의 정확한 주문**.
  · 매수: 딥밸류바닥을 N종 분산(기본 12) · 사이징(등가중/1%리스크/확신도가중) · 현금 한도 · 섹터·그룹 캡.
  · 매도: 보유 종목 익절검토(이격≥1.5·+100%·PBR 적정권) → 매도 주문, 재난백스톱(−40%) → 손절 주문.
         (진우_모의매매.py의 signals() 로직 재사용 — 단일 진실원천)
⚠️ 이건 '제안'이다. 자동 체결 아님 — 검증(라이브 실적·비용)이 끝나기 전엔 사람이 확인 후 집행. 투자자문 아님·책임 본인.

사용:
  py 진우_주문생성.py                          # 등가중 12종, 캡 강제, 매도제안 포함
  py 진우_주문생성.py --capital 10000000 --n 12
  py 진우_주문생성.py --sizing risk --risk-pct 1.0   # 1%리스크 사이징(1R=매수가−손절)
  py 진우_주문생성.py --sizing equal --conf            # 확신도(★) 가중
  py 진우_주문생성.py --sector-cap 2 --group-cap 1     # 분산 캡(기본값)
  py 진우_주문생성.py --no-caps --no-sell --include-bounce
  py 진우_주문생성.py --self-test
"""
import os, sys, csv, argparse, datetime, math, importlib.util
from collections import Counter, defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
CAND = os.path.join(BASE, "진우_타점발굴.csv")
LEDGER = os.path.join(BASE, "진우_모의매매장.csv")
OUT = os.path.join(BASE, "진우_주문생성_현황.html")
SIM_PATH = os.path.join(BASE, "진우_모의매매.py")
SAFETY_PATH = os.path.join(BASE, "진우_안전보유_점검.py")
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

# ── 그룹(계열) 폴백: 안전보유_점검.py의 GROUPS를 우선 쓰되, 로드 실패 시 이 값 사용 ──
GROUPS_FALLBACK = {"에코프로 계열": {"247540", "086520", "450080"}}

# ────────────────────────── 모듈 재사용 (단일 진실원천) ──────────────────────────
_MODCACHE = {}
def _load_module(path, name):
    if name in _MODCACHE: return _MODCACHE[name]
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)           # top-level import만 실행됨(main 가드로 부작용 없음)
    _MODCACHE[name] = m
    return m

def sim():
    return _load_module(SIM_PATH, "jinwoo_sim")      # signals/positions/prices/load_pbr_latest/read_ledger

def safety():
    return _load_module(SAFETY_PATH, "jinwoo_safety")  # GROUPS/load_sector

def get_groups():
    try: return safety().GROUPS
    except Exception: return GROUPS_FALLBACK

# ────────────────────────── 후보 읽기 ──────────────────────────
def _to_int(v, d=0):
    try: return int(float(v))
    except (TypeError, ValueError): return d

def _star_count(v):
    """star 컬럼 → 확신도 정수. 숫자면 그대로, '★★★'/'***'면 개수, 빈값 0."""
    if v is None: return 0
    v = str(v).strip()
    if not v: return 0
    try: return int(float(v))
    except ValueError: pass
    return sum(1 for ch in v if ch in "★*✦●")

def read_candidates(include_bounce):
    rows = []
    if not os.path.exists(CAND): return rows
    with open(CAND, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            r = {k.lstrip("﻿"): v for k, v in r.items()}
            deep = r.get("deep") == "1"; bounce = r.get("bounce") == "1"
            if not (deep or (include_bounce and bounce)): continue
            c = _to_int(r.get("c")); buy = _to_int(r.get("buy")); stop = _to_int(r.get("stop"))
            if c <= 0 and buy <= 0: continue
            rows.append(dict(code=(r.get("code", "") or "").zfill(6), name=r.get("name", ""),
                             kind=("딥밸류바닥" if deep else "바닥반등"),
                             price=c or buy, buy=buy or c, stop=stop,
                             tag=r.get("tag", ""), pbr=r.get("pbr", ""), star=_star_count(r.get("star"))))
    rows.sort(key=lambda x: (x["kind"] != "딥밸류바닥", -x["star"]))  # 딥밸류 먼저, 확신도 높은 순
    return rows

# ────────────────────────── 장부 상태(보유·현금·포지션) ──────────────────────────
def read_positions_and_cash(default_cap):
    """진우_모의매매장.csv 1회 읽어 포지션(평단·보유일)·현금·시드 반환. (모의매매 로직 재사용)
    반환: positions{code:{name,qty,cost,first}}, held(set), cash, seed
    자본 규칙: 입금행 있으면 그 순입금이 시드, 없으면 --capital 폴백(기존 주문생성 동작 유지)."""
    if not os.path.exists(LEDGER):
        return {}, set(), default_cap, default_cap
    S = sim()
    trades, cashflows = S.read_ledger()
    pos, _realized = S.positions(trades)
    held = {c: p for c, p in pos.items() if p["qty"] > 0.0001}
    buy = sum(t["price"] * t["qty"] for t in trades if t["side"] == "매수")
    sell = sum(t["price"] * t["qty"] for t in trades if t["side"] == "매도")
    net_dep = (sum(c["amount"] for c in cashflows if c["side"] == "입금")
               - sum(c["amount"] for c in cashflows if c["side"] == "출금"))
    seed = net_dep if net_dep else default_cap
    cash = seed - buy + sell
    return pos, set(held), cash, seed

# ────────────────────────── 사이징(순수함수, self-test 대상) ──────────────────────────
def conf_factor(star, mean_star, use_conf, lo=0.5, hi=1.5):
    """확신도(★) 가중 계수. 평균 대비 비율을 [lo,hi]로 클램프. use_conf=False면 1.0."""
    if not use_conf or not mean_star or mean_star <= 0: return 1.0
    return max(lo, min(hi, star / mean_star))

def size_shares(mode, price, buy, stop, per, avail, risk_amount, cfactor=1.0):
    """수량 산정. 반환 (shares, cost, note).
      · equal: 목표배분(per×확신도)·현금 한도 내 최대.
      · risk : 1R=매수가−손절 · 수량=자본×리스크%÷1R · 목표배분·현금으로 캡(초과 시 캡).
               손절 없으면 등가중으로 폴백.
    price=현재가(사이징·평가 기준), buy=매수타점(1R 계산), stop=손절가."""
    if price <= 0: return 0, 0.0, ""
    cap_amt = min(per * cfactor, avail)          # 목표배분(확신도 반영)과 가용현금 중 작은 값
    if cap_amt < price: return 0, 0.0, ""
    if mode == "risk":
        r1 = (buy or price) - (stop or 0)
        if r1 and r1 > 0 and (stop or 0) > 0:
            sh_risk = int(risk_amount // r1)
            sh_cap = int(cap_amt // price)
            sh = min(sh_risk, sh_cap)
            note = "" if sh_risk <= sh_cap else "리스크>목표: 목표비중 캡"
        else:
            sh = int(cap_amt // price); note = "손절없음→등가중"
    else:  # equal
        sh = int(cap_amt // price)
        note = "확신도가중" if abs(cfactor - 1.0) > 1e-9 else ""
    return sh, sh * price, note

# ────────────────────────── 분산 캡(순수함수, self-test 대상) ──────────────────────────
def code_groups(code, groups):
    return [g for g, s in groups.items() if code in s]

def passes_caps(code, sector, sel_sectors, sel_groups, groups, sector_cap, group_cap):
    """섹터당 sector_cap·그룹당 group_cap 강제. 반환 (ok, reason)."""
    for g in code_groups(code, groups):
        if sel_groups.get(g, 0) >= group_cap:
            return False, f"그룹'{g}' 캡{group_cap} 도달"
    if sector and sector != "-" and sel_sectors.get(sector, 0) >= sector_cap:
        return False, f"섹터'{sector}' 캡{sector_cap} 도달"
    return True, ""

def commit_caps(code, sector, sel_sectors, sel_groups, groups):
    if sector and sector != "-": sel_sectors[sector] += 1
    for g in code_groups(code, groups): sel_groups[g] += 1

# ────────────────────────── 매도/익절 주문(순수함수, self-test 대상) ──────────────────────────
def make_sell_orders(holdings, signals_fn):
    """holdings: [dict(code,name,qty,avg,last,ret,ext,days,pbr)], signals_fn=sim().signals.
    익절검토→매도(전량), 재난백스톱→손절(전량), 장기재평가→검토플래그(주문 아님)."""
    sells, reviews = [], []
    for h in holdings:
        sig = signals_fn(h["ret"], h["ext"], h["days"], h["pbr"])
        joined = " · ".join(sig)
        if "익절" in joined:
            sells.append(dict(kind="익절매도", **_sell_row(h, joined)))
        elif "백스톱" in joined:
            sells.append(dict(kind="재난백스톱", **_sell_row(h, joined)))
        elif "재평가" in joined:
            reviews.append(dict(**_sell_row(h, joined)))
    sells.sort(key=lambda x: (x["kind"] != "익절매도", -x["ret"]))
    return sells, reviews

def _sell_row(h, reason):
    return dict(code=h["code"], name=h["name"], shares=int(h["qty"]), price=int(round(h["last"])),
                proceeds=int(round(h["last"] * h["qty"])), ret=h["ret"], ext=h["ext"],
                pbr=h["pbr"], days=h["days"], reason=reason)

# ────────────────────────── 오케스트레이션 ──────────────────────────
def build_holdings_metrics(pos, held):
    """보유 종목의 현재가·이격도·PBR·보유일·수익률 계산(pandas+대용량 CSV 필요).
    데이터 없으면 [] + 경고. (매도 판단용)"""
    if not held: return [], None
    try:
        import pandas as pd
    except Exception:
        return [], "pandas 없음 — 매도 판단 생략"
    try:
        S = sim()
        px = S.prices(pd, set(held)); P = S.load_pbr_latest()
    except Exception as e:
        return [], f"시세/재무 데이터 로드 실패({e}) — 매도 판단 생략"
    # ★ 감사보강: 시세 CSV(종목일봉)가 없으면 prices()가 조용히 {}를 돌려준다.
    #    그대로 두면 모든 보유가 last=평단(수익률0·이격None)이 되어 '매도 신호 없음'으로
    #    찍혀 '판단 못 함'과 '팔 것 없음'이 구분되지 않는다 → 보류로 명시 표면화.
    if not px:
        return [], "시세 CSV(종목일봉_30년) 없음 — 매도 판단 보류(PC에서 실행 필요)"
    today = datetime.date.today(); out = []; nopx = []
    for code in held:
        p = pos[code]
        if p["qty"] <= 0: continue
        pr = px.get(code)
        if not pr:                       # 이 종목만 시세 결측 → 임의 평단대입 대신 판단서 제외
            nopx.append(p["name"] or code); continue
        avg = p["cost"] / p["qty"]
        last = pr.get("last", avg); ma200 = pr.get("ma200")
        ext = round(last / ma200, 2) if ma200 else None
        ret = last / avg - 1
        pbr = round(P.get(code, 0), 2) or None
        try: days = (today - datetime.date.fromisoformat(p["first"])).days
        except Exception: days = 0
        out.append(dict(code=code, name=p["name"] or code, qty=p["qty"], avg=avg, last=last,
                        ext=ext, ret=ret, pbr=pbr, days=days))
    note = ("일부 보유 시세 결측(판단 제외): " + ", ".join(nopx)) if nopx else None
    return out, note

def generate(capital, n, include_bounce, sizing, risk_pct, use_conf,
             sector_cap, group_cap, apply_caps, do_sell):
    cands = read_candidates(include_bounce)
    pos, held, cash, seed = read_positions_and_cash(capital)
    groups = get_groups()

    # 섹터맵(캡용) — 없으면 그룹 캡만 동작
    sec = {}
    if apply_caps:
        try:
            import pandas as pd
            sec = safety().load_sector(pd)
        except Exception:
            sec = {}

    # ── 매도/익절 주문 ──
    sells, reviews, sell_note = [], [], None
    if do_sell:
        holdings, sell_note = build_holdings_metrics(pos, held)
        if holdings:
            sells, reviews = make_sell_orders(holdings, sim().signals)

    # ── 매수 주문 ──
    per = capital / max(n, 1)
    risk_amount = capital * (risk_pct / 100.0)
    mean_star = (sum(c["star"] for c in cands) / len(cands)) if cands else 0
    # 캡 카운터를 보유분으로 초기화(보유 포함 캡)
    sel_sectors, sel_groups = Counter(), Counter()
    if apply_caps:
        for code in held:
            commit_caps(code, sec.get(code, "-"), sel_sectors, sel_groups, groups)

    slots = max(n - len(held), 0)
    orders = []; skipped = []; used = 0.0
    for c in cands:
        if slots <= 0: break
        if c["code"] in held:
            continue
        if apply_caps:
            ok, why = passes_caps(c["code"], sec.get(c["code"], "-"),
                                  sel_sectors, sel_groups, groups, sector_cap, group_cap)
            if not ok:
                skipped.append((c["name"] or c["code"], why)); continue
        cf = conf_factor(c["star"], mean_star, use_conf)
        sh, cost, note = size_shares(sizing, c["price"], c["buy"], c["stop"],
                                     per, cash - used, risk_amount, cf)
        if sh < 1:
            skipped.append((c["name"] or c["code"], "현금/최소단위 부족")); continue
        orders.append(dict(**c, shares=sh, cost=cost, weight=cost / capital * 100 if capital else 0,
                           note=note, cfactor=round(cf, 2)))
        if apply_caps:
            commit_caps(c["code"], sec.get(c["code"], "-"), sel_sectors, sel_groups, groups)
        used += cost; slots -= 1

    return dict(orders=orders, sells=sells, reviews=reviews, skipped=skipped,
                held=held, cash=cash, seed=seed, per=per, n=n, capital=capital, used=used,
                ncand=len(cands), sizing=sizing, risk_pct=risk_pct, use_conf=use_conf,
                sector_cap=sector_cap if apply_caps else None, group_cap=group_cap if apply_caps else None,
                sell_note=sell_note, sec_loaded=bool(sec))

# ────────────────────────── 콘솔 출력 ──────────────────────────
def render(g):
    print("\n" + "=" * 92)
    print("진우 주문 생성 — 오늘의 주문 제안 (반자동 · 확인 후 집행)")
    print("=" * 92)
    smode = {"equal": "등가중", "risk": f"1%리스크({g['risk_pct']:.1f}%)"}.get(g["sizing"], g["sizing"])
    if g["use_conf"]: smode += "+확신도가중"
    capinfo = f"섹터≤{g['sector_cap']}·그룹≤{g['group_cap']}" if g["sector_cap"] is not None else "캡 없음"
    print(f"  자본 {g['capital']:,.0f} · 현금 {g['cash']:,.0f} · 목표 {g['n']}종 · 사이징 {smode} · 분산 {capinfo}")
    print(f"  보유 {len(g['held'])}종 · 후보 {g['ncand']}종 · 종목당 목표 ~{g['per']:,.0f}")

    # 매도
    print("\n  [매도/익절 제안]")
    if g["sell_note"]:
        print(f"    (판단 보류: {g['sell_note']})")
    elif not g["sells"] and not g["reviews"]:
        print("    → 매도 신호 없음 (보유 유지).")
    else:
        for s in g["sells"]:
            print(f"    {s['kind']:<7} {s['name'][:12]:<12} {s['shares']:>6,}주 @ {s['price']:>9,} "
                  f"= {s['proceeds']:>12,} · {s['ret']*100:+.0f}% · {s['reason']}")
        for r in g["reviews"]:
            print(f"    검토    {r['name'][:12]:<12} {r['days']}일 → {r['reason']}")

    # 매수
    print("\n  [매수 제안]")
    if not g["orders"]:
        print("    → 오늘 매수 제안 없음. (딥밸류바닥 후보 0 = 강세장 정상, 사냥철 대기. --include-bounce 가능)")
    else:
        print(f"    {'종목':<12}{'유형':<9}{'수량':>7}{'매수가':>10}{'금액':>12}{'비중':>7}{'손절':>10}  비고")
        for o in g["orders"]:
            print(f"    {o['name'][:12]:<12}{o['kind']:<9}{o['shares']:>7,}{o['buy']:>10,}"
                  f"{o['cost']:>12,.0f}{o['weight']:>6.1f}%{o['stop']:>10,}  {o['note']}")
        print(f"    {'─'*74}")
        print(f"    합계 매수 {g['used']:,.0f} · 매수후 현금 {g['cash']-g['used']:,.0f} · 신규 {len(g['orders'])}종")
    if g["skipped"]:
        print("\n  [제외 — 캡/현금]")
        for nm, why in g["skipped"][:12]:
            print(f"    · {nm}: {why}")
    print("\n※ 제안일 뿐 자동체결 아님 · 딥밸류는 넓은 재난백스톱만(타이트 스톱 휩쏘) · 분산·장기보유 · 결정·책임 본인.")

# ────────────────────────── HTML ──────────────────────────
def build_html(g):
    won = lambda n: f"{n:,.0f}"
    gen = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    smode = {"equal": "등가중", "risk": f"1%리스크({g['risk_pct']:.1f}%)"}.get(g["sizing"], g["sizing"])
    if g["use_conf"]: smode += "+확신도"
    capinfo = f"섹터≤{g['sector_cap']}·그룹≤{g['group_cap']}" if g["sector_cap"] is not None else "없음"

    buy_body = "".join(
        f"<tr><td class=l><b>{o['name']}</b> <span class=s>{o['code']}</span></td><td class=l>{o['kind']}</td>"
        f"<td>{o['shares']:,}</td><td>{won(o['buy'])}</td><td>{won(o['cost'])}</td><td>{o['weight']:.1f}%</td>"
        f"<td>{won(o['stop'])}</td><td class=l s>{o['note']}</td></tr>" for o in g["orders"])
    buy_empty = "<tr><td colspan=8 class=l style=color:#9aa0aa>오늘 매수 제안 없음 (딥밸류바닥 0 = 강세장 정상, 사냥철 대기)</td></tr>"

    def scol(k): return "#ffca3a" if k == "익절매도" else "#e2606a"
    sell_rows = "".join(
        f"<tr><td class=l style='color:{scol(s['kind'])}'><b>{s['kind']}</b></td>"
        f"<td class=l><b>{s['name']}</b> <span class=s>{s['code']}</span></td><td>{s['shares']:,}</td>"
        f"<td>{won(s['price'])}</td><td>{won(s['proceeds'])}</td>"
        f"<td style='color:{'#3fb37a' if s['ret']>=0 else '#e2606a'}'>{s['ret']*100:+.1f}%</td>"
        f"<td class=l s>{s['reason']}</td></tr>" for s in g["sells"])
    review_rows = "".join(
        f"<tr><td class=l style='color:#9aa0aa'>검토</td><td class=l><b>{r['name']}</b> <span class=s>{r['code']}</span></td>"
        f"<td colspan=4 class=l s>{r['days']}일 · {r['reason']}</td><td></td></tr>" for r in g["reviews"])
    sell_body = sell_rows + review_rows
    if g["sell_note"]:
        sell_body = f"<tr><td colspan=7 class=l style=color:#9aa0aa>매도 판단 보류: {g['sell_note']}</td></tr>"
    elif not sell_body:
        sell_body = "<tr><td colspan=7 class=l style=color:#9aa0aa>매도 신호 없음 (보유 유지)</td></tr>"

    skip_body = ""
    if g["skipped"]:
        items = "".join(f"<li>{nm} — <span class=s>{why}</span></li>" for nm, why in g["skipped"][:20])
        skip_body = f"<h1 style='font-size:13px;margin:18px 0 4px'>제외 (캡/현금)</h1><ul class=sk>{items}</ul>"

    return f"""<!DOCTYPE html><html lang=ko><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>진우 주문 생성</title><style>body{{margin:0;background:#0f1115;color:#e8eaed;font-family:'Malgun Gothic',system-ui,sans-serif;font-size:13px}}
.w{{max-width:960px;margin:0 auto;padding:20px 16px 50px}}h1{{font-size:20px;margin:0 0 3px}}.s{{color:#9aa0aa;font-size:11px}}
.kpi{{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}}.k{{background:#171a21;border:1px solid #242a35;border-radius:10px;padding:10px 14px;min-width:110px}}.k b{{font-size:16px;display:block;margin-top:3px}}
table{{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:6px}}th,td{{padding:7px 9px;text-align:right;border-bottom:1px solid #242a35;white-space:nowrap}}th{{color:#9aa0aa}}.l{{text-align:left}}
ul.sk{{margin:4px 0;padding-left:18px;color:#c9ccd2;font-size:12px}}ul.sk li{{margin:2px 0}}
.foot{{color:#9aa0aa;font-size:11px;margin-top:14px;line-height:1.7}}</style></head><body><div class=w>
<h1>진우 주문 생성 <span style=color:#ff7a45>· 오늘의 주문 제안(반자동)</span></h1>
<div class=s>생성 {gen} · 사이징 {smode} · 분산캡 {capinfo} · 확인 후 집행</div>
<div class=kpi><div class=k>자본<b>{won(g['capital'])}</b></div><div class=k>현금<b>{won(g['cash'])}</b></div>
<div class=k>종목당 목표<b>{won(g['per'])}</b></div><div class=k>보유<b>{len(g['held'])}종</b></div>
<div class=k>매도제안<b>{len(g['sells'])}종</b></div><div class=k>매수제안<b>{len(g['orders'])}종</b></div></div>
<h1 style="font-size:14px;margin:16px 0 2px">매도 / 익절 제안</h1>
<table><thead><tr><th class=l>구분</th><th class=l>종목</th><th>수량</th><th>현재가</th><th>예상금액</th><th>수익률</th><th class=l>사유</th></tr></thead>
<tbody>{sell_body}</tbody></table>
<h1 style="font-size:14px;margin:20px 0 2px">매수 제안</h1>
<table><thead><tr><th class=l>종목</th><th class=l>유형</th><th>수량</th><th>매수가</th><th>금액</th><th>비중</th><th>손절</th><th class=l>비고</th></tr></thead>
<tbody>{buy_body or buy_empty}</tbody></table>
<div class=s style="margin-top:6px">합계 매수 {won(g['used'])} · 매수후 현금 {won(g['cash']-g['used'])} · 신규 {len(g['orders'])}종</div>
{skip_body}
<div class=foot>⚠️ <b>제안일 뿐 자동 체결 아님.</b> 라이브 실적·비용검증 전엔 사람이 확인 후 집행 · 딥밸류는 타이트 스톱 금지(휩쏘)·넓은 재난백스톱만 · 10~15종 분산·2~3년 보유 · 익절=강함에 판다(이격≥1.5·+100%·PBR 적정권) · 투자자문 아님·책임 본인.</div>
</div></body></html>"""

# ────────────────────────── self-test ──────────────────────────
def _self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")

    # ── 사이징: 등가중 ──
    per = 12000000 / 12  # 100만
    sh, cost, _ = size_shares("equal", 50000, 50000, 0, per, 10000000, 100000, 1.0)
    chk("등가중 100만/5만=20주", sh == 20 and cost == 1000000)
    sh2, _, _ = size_shares("equal", 50000, 50000, 0, per, 150000, 100000, 1.0)
    chk("현금 15만 → 3주로 축소", sh2 == 3)

    # ── 사이징: 1%리스크 ──
    # 자본1000만×1%=10만 리스크. buy5만·손절4.5만 → 1R=5천 → 20주. 목표100만/5만=20 캡 → 20
    shr, _, note = size_shares("risk", 50000, 50000, 45000, per, 10000000, 100000, 1.0)
    chk("1%리스크 1R=5천 → 20주", shr == 20)
    # 넓은 재난스톱 buy5만·손절3만 → 1R=2만 → 5주 (딥밸류 보수적)
    shw, _, _ = size_shares("risk", 50000, 50000, 30000, per, 10000000, 100000, 1.0)
    chk("넓은스톱 1R=2만 → 5주", shw == 5)
    # 타이트스톱 buy5만·손절4.9만 → 1R=1천 → 100주지만 목표비중 20주로 캡
    sht, _, note2 = size_shares("risk", 50000, 50000, 49000, per, 10000000, 100000, 1.0)
    chk("타이트스톱 목표비중 캡 20주", sht == 20 and "캡" in note2)
    # 손절 없음 → 등가중 폴백
    shn, _, note3 = size_shares("risk", 50000, 50000, 0, per, 10000000, 100000, 1.0)
    chk("손절없음 → 등가중 폴백 20주", shn == 20 and "등가중" in note3)

    # ── 확신도 가중 ──
    cf_hi = conf_factor(4, 2, True); cf_lo = conf_factor(1, 2, True)
    chk("확신도 4/평균2 → 1.5 클램프", abs(cf_hi - 1.5) < 1e-9)
    chk("확신도 1/평균2 → 0.5", abs(cf_lo - 0.5) < 1e-9)
    chk("확신도 off → 1.0", conf_factor(4, 2, False) == 1.0)
    shc, _, _ = size_shares("equal", 50000, 50000, 0, per, 10000000, 100000, 1.5)
    chk("확신도1.5 → 목표150만/5만=30주", shc == 30)

    # ── 분산 캡 ──
    G = {"에코프로 계열": {"247540", "086520", "450080"}}
    ss, sg = Counter({"반도체": 2}), Counter()
    ok1, why1 = passes_caps("000000", "반도체", ss, sg, G, 2, 1)
    chk("섹터 2종 도달 → 차단", (not ok1) and "섹터" in why1)
    ok2, _ = passes_caps("111111", "2차전지", ss, sg, G, 2, 1)
    chk("다른 섹터 → 통과", ok2)
    sg2 = Counter({"에코프로 계열": 1})
    ok3, why3 = passes_caps("086520", "2차전지", Counter(), sg2, G, 2, 1)
    chk("에코프로 계열 1종 보유 → 계열 차단", (not ok3) and "그룹" in why3)
    # 보유 초기화 시뮬: 247540 보유 → 086520 매수 차단
    ss0, sg0 = Counter(), Counter()
    commit_caps("247540", "2차전지", ss0, sg0, G)
    ok4, _ = passes_caps("086520", "화학", ss0, sg0, G, 2, 1)
    chk("보유 247540 → 086520 계열차단", not ok4)

    # ── 매도/익절 주문 (signals 재사용) ──
    S = sim()
    holds = [
        dict(code="000001", name="익절대상", qty=10, avg=1000, last=2100, ret=1.1, ext=1.6, days=200, pbr=1.2),
        dict(code="000002", name="백스톱대상", qty=10, avg=1000, last=550, ret=-0.45, ext=0.7, days=100, pbr=0.6),
        dict(code="000003", name="보유유지", qty=10, avg=1000, last=1100, ret=0.10, ext=1.0, days=100, pbr=0.7),
        dict(code="000004", name="장기재평가", qty=10, avg=1000, last=1200, ret=0.20, ext=1.0, days=1100, pbr=0.7),
    ]
    sells, reviews = make_sell_orders(holds, S.signals)
    kinds = {s["name"]: s["kind"] for s in sells}
    chk("익절대상 → 익절매도", kinds.get("익절대상") == "익절매도")
    chk("백스톱대상 → 재난백스톱", kinds.get("백스톱대상") == "재난백스톱")
    chk("보유유지 → 매도 없음", "보유유지" not in kinds)
    chk("장기재평가 → 검토(주문 아님)", any(r["name"] == "장기재평가" for r in reviews) and "장기재평가" not in kinds)
    chk("익절 전량수량·예상금액", sells[0]["shares"] == 10 and sells[0]["proceeds"] == 21000)

    # ── 모듈 재사용 배선 ──
    chk("sim().signals 존재", callable(getattr(S, "signals", None)))
    chk("safety().GROUPS 로드", "에코프로 계열" in get_groups())

    # ── 후보 정렬키/파싱 ──
    chk("★ 파싱: '★★★'=3", _star_count("★★★") == 3)
    chk("★ 파싱: '2'=2", _star_count("2") == 2)

    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot

# ────────────────────────── main ──────────────────────────
def main():
    ap = argparse.ArgumentParser(description="진우 주문 생성 엔진 (반자동)")
    ap.add_argument("--capital", type=float, default=10000000)
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--include-bounce", action="store_true", help="바닥반등 후보도 포함")
    ap.add_argument("--sizing", choices=["equal", "risk"], default="equal", help="등가중 / 1%%리스크")
    ap.add_argument("--risk-pct", type=float, default=1.0, help="risk 사이징 시 자본 대비 리스크%% (기본 1.0)")
    ap.add_argument("--conf", action="store_true", help="확신도(★) 가중 활성화")
    ap.add_argument("--sector-cap", type=int, default=2, help="섹터당 최대 종목수(기본 2)")
    ap.add_argument("--group-cap", type=int, default=1, help="같은 그룹(계열) 최대 종목수(기본 1)")
    ap.add_argument("--no-caps", action="store_true", help="분산 캡 강제 끄기")
    ap.add_argument("--no-sell", action="store_true", help="매도/익절 제안 끄기")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return 0 if _self_test() else 1
    g = generate(a.capital, a.n, a.include_bounce, a.sizing, a.risk_pct, a.conf,
                 a.sector_cap, a.group_cap, not a.no_caps, not a.no_sell)
    render(g)
    open(OUT, "w", encoding="utf-8").write(build_html(g))
    print(f"\n저장: 진우_주문생성_현황.html")
    return 0

if __name__ == "__main__":
    sys.exit(main())
