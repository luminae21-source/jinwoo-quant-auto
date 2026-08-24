#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우_전진기록.py — 라이브/모의 전진 기록 트래킹 (로드맵 §3-2)

목적: 주문 엔진이 낸 '제안'을 실제로 그대로 집행했는지, 그리고 그 전진 기록이 이기고 있는지를
     3~6개월 앞으로 밀고 나가며 추적한다. §3-3(비용·유동성 검증)과 §3-4(API)로 넘어갈 자격을 만드는 관문.

두 축:
  (A) 규율   — 제안 대비 실제 체결. 체결률(제안이 실제로 실행됐나)·슬리피지(제안가 vs 체결가 불리편차).
              "제안대로 손으로 체결"이 지켜지는지, 슬리피지가 엣지를 갉아먹는지 숫자로 본다.
  (B) 성과   — 장부 기준 누적 성과(실현+평가), 시드 대비 수익률, (있으면) KOSPI 매수후보유 대비.

데이터:
  · 진우_제안기록.csv  — snapshot으로 매일의 엔진 제안을 append(코드·구분·제안가·수량). 이 파일이 전진기록의 씨앗.
  · 진우_모의매매장.csv — 실제 체결 장부(진우_모의매매.py의 read_ledger 재사용, 단일 진실원천).
  · 종목일봉/지수 CSV   — 있으면 평가·벤치마크. 없으면 실현손익만으로 안전 폴백(감사 교훈: 결측을 조용히 0으로 두지 않음).

⚠️ 기록·검증 도구다. 주문/집행 안 한다. 투자자문 아님·책임 본인.

사용:
  py 진우_전진기록.py --self-test
  py 진우_전진기록.py                       # 제안기록 vs 장부 정산 + 성과 리포트(HTML)
  py 진우_전진기록.py --snapshot            # 오늘 엔진 제안을 진우_제안기록.csv에 적재(중복 방지)
  py 진우_전진기록.py --snapshot --include-bounce --sizing risk
"""
import os, sys, csv, argparse, datetime, importlib.util
from collections import defaultdict

BASE = os.path.dirname(os.path.abspath(__file__))
PROP_LOG = os.path.join(BASE, "진우_제안기록.csv")
GEN_PATH = os.path.join(BASE, "진우_주문생성.py")
SIM_PATH = os.path.join(BASE, "진우_모의매매.py")
COST_PATH = os.path.join(BASE, "진우_비용모델.py")
OUT = os.path.join(BASE, "진우_전진기록_현황.html")
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

_MODCACHE = {}
def _load_module(path, name):
    if name in _MODCACHE: return _MODCACHE[name]
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m); _MODCACHE[name] = m
    return m

def sim(): return _load_module(SIM_PATH, "jinwoo_sim")
def costmod():
    """진우_비용모델.py(있으면). 없으면 None → 비용검증 섹션은 안내만."""
    try: return _load_module(COST_PATH, "jinwoo_cost")
    except Exception: return None

SIDE_KO = {"buy": "매수", "sell": "매도"}
SIDE_EN = {"매수": "buy", "매도": "sell"}

# ────────────────────────── 제안 스냅샷(적재) ──────────────────────────
PROP_HDR = ["date", "code", "name", "side", "price", "qty", "kind"]

def read_proposals(path=PROP_LOG):
    rows = []
    if not os.path.exists(path): return rows
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            r = {k.lstrip("﻿"): (v or "").strip() for k, v in r.items()}
            try:
                rows.append(dict(date=r["date"], code=r["code"].zfill(6), name=r.get("name", ""),
                                 side=r["side"], price=int(float(r["price"] or 0)),
                                 qty=int(float(r["qty"] or 0)), kind=r.get("kind", "")))
            except (KeyError, ValueError):
                continue
    return rows

def proposals_from_engine(g, date):
    """엔진 산출 → 제안 레코드(매도 먼저·매수 나중)."""
    out = []
    for s in g.get("sells", []):
        out.append(dict(date=date, code=s["code"].zfill(6), name=s.get("name", ""), side="sell",
                        price=int(s["price"]), qty=int(s["shares"]), kind=s.get("kind", "매도")))
    for o in g.get("orders", []):
        out.append(dict(date=date, code=o["code"].zfill(6), name=o.get("name", ""), side="buy",
                        price=int(o["buy"]), qty=int(o["shares"]), kind=o.get("kind", "매수")))
    return out

def merge_snapshot(existing, new_rows):
    """(date,code,side) 키로 중복 제거하며 병합. 같은 날 재실행해도 두 번 안 쌓임. 반환 (merged, added)."""
    seen = {(r["date"], r["code"], r["side"]) for r in existing}
    added = [r for r in new_rows if (r["date"], r["code"], r["side"]) not in seen]
    return existing + added, added

def write_proposals(rows, path=PROP_LOG):
    with open(path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=PROP_HDR); w.writeheader()
        for r in rows: w.writerow({k: r.get(k, "") for k in PROP_HDR})

# ────────────────────────── 슬리피지·정산(순수함수) ──────────────────────────
def slippage_frac(side, proposed, filled):
    """불리편차(양수=엣지 손해). 매수는 비싸게 산 만큼, 매도는 싸게 판 만큼.
    proposed<=0이면 None(비교 불가)."""
    if not proposed or proposed <= 0 or not filled or filled <= 0: return None
    if side == "buy":  return (filled - proposed) / proposed
    if side == "sell": return (proposed - filled) / proposed
    return None

def reconcile(proposals, fills):
    """제안 각각을 이후(같은날 포함) 최초의 동일 종목·방향 체결에 1:1 매칭.
    반환: [dict(prop, fill|None, filled(bool), days, slip)]. 남은 체결은 unmatched로 별도.
    proposals/fills: [{date,code,side,price,qty,...}] (side는 'buy'/'sell')."""
    used = [False] * len(fills)
    fi = sorted(range(len(fills)), key=lambda i: fills[i]["date"])
    recs = []
    for p in sorted(proposals, key=lambda x: x["date"]):
        match = None
        for i in fi:
            if used[i]: continue
            f = fills[i]
            if f["code"] == p["code"] and f["side"] == p["side"] and f["date"] >= p["date"]:
                match = i; used[i] = True; break
        if match is None:
            recs.append(dict(prop=p, fill=None, filled=False, days=None, slip=None))
        else:
            f = fills[match]
            days = _daydiff(p["date"], f["date"])
            recs.append(dict(prop=p, fill=f, filled=True, days=days,
                             slip=slippage_frac(p["side"], p["price"], f["price"])))
    unmatched_fills = [fills[i] for i in range(len(fills)) if not used[i]]
    return recs, unmatched_fills

def _daydiff(d1, d2):
    try:
        a = datetime.date.fromisoformat(d1); b = datetime.date.fromisoformat(d2)
        return (b - a).days
    except Exception:
        return None

def fill_stats(recs):
    """정산 레코드 → 요약. 체결률·평균 슬리피지(체결분)·평균 체결소요일."""
    n = len(recs); filled = [r for r in recs if r["filled"]]
    slips = [r["slip"] for r in filled if r["slip"] is not None]
    dts = [r["days"] for r in filled if r["days"] is not None]
    return dict(n=n, n_filled=len(filled),
                fill_rate=(len(filled) / n if n else 0.0),
                avg_slip=(sum(slips) / len(slips) if slips else None),
                worst_slip=(max(slips) if slips else None),
                avg_days=(sum(dts) / len(dts) if dts else None))

# ────────────────────────── 성과 집계(순수함수) ──────────────────────────
def perf_summary(trades, cashflows, price_map):
    """장부 → 성과. price_map={code:last}(없으면 평단 폴백·평가손익 0 표시).
    반환 dict(seed,cash,realized,holdings,hold_value,unrealized,equity,ret,priced)."""
    S = sim()
    pos, realized = S.positions(trades)
    buyval = sum(t["price"] * t["qty"] for t in trades if t["side"] == "매수")
    sellval = sum(t["price"] * t["qty"] for t in trades if t["side"] == "매도")
    net_dep = (sum(c["amount"] for c in cashflows if c["side"] == "입금")
               - sum(c["amount"] for c in cashflows if c["side"] == "출금"))
    seed = net_dep if net_dep else (buyval or 0)
    cash = seed - buyval + sellval
    priced = bool(price_map)
    holdings, hv, unreal = [], 0.0, 0.0
    for code, p in pos.items():
        if p["qty"] <= 0.0001: continue
        avg = p["cost"] / p["qty"]
        last = price_map.get(code, avg)
        mval = last * p["qty"]; u = (last - avg) * p["qty"]
        hv += mval; unreal += u
        holdings.append(dict(code=code, name=p["name"] or code, qty=p["qty"], avg=avg,
                             last=last, mval=mval, unreal=u, priced=code in price_map))
    holdings.sort(key=lambda x: -x["mval"])
    equity = cash + hv
    ret = (equity / seed - 1) if seed else 0.0
    return dict(seed=seed, cash=cash, realized=realized, holdings=holdings,
                hold_value=hv, unrealized=unreal, equity=equity, ret=ret, priced=priced,
                buyval=buyval, sellval=sellval)

def benchmark_return(index_closes):
    """지수 종가 시계열(첫→끝) 매수후보유 수익률. 데이터 없으면 None."""
    cl = [c for c in index_closes if c and c > 0]
    if len(cl) < 2: return None
    return cl[-1] / cl[0] - 1

# ────────────────────────── 데이터 로드(부작용 격리) ──────────────────────────
def load_prices_safe(codes):
    """보유 종목 현재가 {code:last}. 시세 CSV 없으면 {} (감사 교훈: 조용히 평단 대입 안 함)."""
    if not codes: return {}
    try:
        import pandas as pd
    except Exception:
        return {}
    try:
        px = sim().prices(pd, set(codes))
        return {c: v["last"] for c, v in px.items() if v.get("last")}
    except Exception:
        return {}

def load_index_window(start_date):
    """kospi_index_daily.csv에서 start_date 이후 종가 리스트. 없으면 []."""
    p = os.path.join(BASE, "kospi_index_daily.csv")
    if not os.path.exists(p): return []
    out = []
    with open(p, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            r = {k.lstrip("﻿").lower(): v for k, v in r.items()}
            d = r.get("date", "");
            if start_date and d and d < start_date: continue
            try: out.append(float(r["close"]))
            except (ValueError, KeyError): pass
    return out

# ────────────────────────── 리포트 ──────────────────────────
def build_report():
    S = sim()
    trades, cashflows = S.read_ledger()
    # 제안 vs 체결
    props = read_proposals()
    fills = [dict(date=t["date"], code=t["code"], side=SIDE_EN.get(t["side"], t["side"]),
                  price=t["price"], qty=t["qty"], name=t["name"]) for t in trades]
    recs, unmatched = reconcile(props, fills)
    fs = fill_stats(recs)
    # 성과
    codes = {t["code"] for t in trades}
    pm = load_prices_safe(codes)
    perf = perf_summary(trades, cashflows, pm)
    start = min((t["date"] for t in trades), default="") or min((c["date"] for c in cashflows), default="")
    bench = benchmark_return(load_index_window(start))
    # §3-3 비용검증: 장부에 실제 발생한 세금·수수료를 반영한 순성과
    cost = None
    CM = costmod()
    if CM is not None:
        model = CM.CostModel.load()
        c = CM.ledger_costs(trades, model)
        net_equity = perf["equity"] - c["total"]
        net_ret = (net_equity / perf["seed"] - 1) if perf["seed"] else 0.0
        cost = dict(model=model, breakeven=CM.breakeven_move(model.tax_kosdaq, model.commission),
                    net_equity=net_equity, net_ret=net_ret, **c)
    return dict(recs=recs, unmatched=unmatched, fs=fs, perf=perf, bench=bench, cost=cost,
                start=start, nprops=len(props), nfills=len(fills))

def render(R):
    fs, perf = R["fs"], R["perf"]
    pct = lambda x: "—" if x is None else f"{x*100:+.2f}%"
    print("\n" + "=" * 84)
    print("진우 전진기록 — 제안 규율 & 성과 추적 (로드맵 §3-2)")
    print("=" * 84)
    print(f"  기록 시작 {R['start'] or '-'} · 제안 {R['nprops']}건 · 체결 {R['nfills']}건")
    print("\n  [A] 규율 — 제안 대비 체결")
    if fs["n"] == 0:
        print("    (제안기록 없음 — 먼저 `--snapshot`으로 오늘 제안을 적재하세요.)")
    else:
        avgdays = "—" if fs["avg_days"] is None else f"{fs['avg_days']:.1f}일"
        print(f"    체결률 {fs['fill_rate']*100:.0f}% ({fs['n_filled']}/{fs['n']}) · "
              f"평균 슬리피지 {pct(fs['avg_slip'])} · 최악 {pct(fs['worst_slip'])} · "
              f"평균 체결소요 {avgdays}")
        unfilled = [r for r in R["recs"] if not r["filled"]]
        if unfilled:
            print(f"    미체결 제안 {len(unfilled)}건: " +
                  ", ".join(f"{r['prop']['name'] or r['prop']['code']}" for r in unfilled[:8]))
    print("\n  [B] 성과 — 장부 기준")
    print(f"    시드 {perf['seed']:,.0f} · 현금 {perf['cash']:,.0f} · 평가액 {perf['hold_value']:,.0f} "
          f"· 자산 {perf['equity']:,.0f}")
    print(f"    실현손익 {perf['realized']:+,.0f} · 평가손익 {perf['unrealized']:+,.0f} "
          f"· 총수익률 {perf['ret']*100:+.2f}%" + ("" if perf["priced"] else "  (⚠ 시세 없음: 평가=평단 폴백)"))
    if R["bench"] is not None:
        print(f"    KOSPI 매수후보유 {R['bench']*100:+.2f}% · 초과수익 {(perf['ret']-R['bench'])*100:+.2f}%p")
    else:
        print("    (벤치마크: kospi_index_daily.csv 없음 — 비교 생략)")
    # [C] 비용검증 (§3-3)
    cost = R.get("cost")
    print("\n  [C] 비용검증 — 세금·수수료 반영(§3-3)")
    if not cost:
        print("    (진우_비용모델.py 없음 — 비용검증 생략)")
    else:
        m = cost["model"]
        print(f"    가정: 매도세 {m.tax_kosdaq*100:.2f}%(2026·농특세포함) · 수수료 편도 {m.commission*100:.3f}% "
              f"· 손익분기 왕복 +{cost['breakeven']*100:.2f}%")
        print(f"    발생비용: 매수수수료 {cost['buy_fee']:,.0f} · 매도세금 {cost['sell_tax']:,.0f} "
              f"· 매도수수료 {cost['sell_fee']:,.0f} · 합계 {cost['total']:,.0f}")
        print(f"    총수익률 {perf['ret']*100:+.2f}% → 비용반영 순수익률 {cost['net_ret']*100:+.2f}%")
        if R["bench"] is not None:
            edge = cost["net_ret"] - R["bench"]
            verdict = "이김 ✔" if edge > 0 else "짐 ✖"
            print(f"    §3-3 판정: 비용 반영 후에도 KOSPI 대비 {edge*100:+.2f}%p → {verdict}")
    print("\n※ 전진 기록일 뿐 · 3~6개월 누적 후 §3-3(비용·유동성) 판정 · 기준 미달 시 다음단계 안 감 · 책임 본인.")

def build_html(R):
    fs, perf = R["fs"], R["perf"]
    won = lambda n: f"{n:,.0f}"
    pct = lambda x: "—" if x is None else f"{x*100:+.2f}%"
    gen = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    col = lambda x: "#3fb37a" if (x or 0) >= 0 else "#e2606a"
    slipcol = lambda x: "#9aa0aa" if x is None else ("#e2606a" if x > 0 else "#3fb37a")

    rec_rows = ""
    for r in R["recs"]:
        p = r["prop"]; f = r["fill"]
        fillstr = f"{won(f['price'])} × {f['qty']} ({f['date']})" if f else "<span style=color:#e2606a>미체결</span>"
        slip = "—" if r["slip"] is None else f"<span style='color:{slipcol(r['slip'])}'>{r['slip']*100:+.2f}%</span>"
        sidecol = "#3fb37a" if p["side"] == "buy" else "#e2606a"
        rec_rows += (f"<tr><td class=l>{p['date']}</td>"
                     f"<td class=l><b>{p['name'] or p['code']}</b> <span class=s>{p['code']}</span></td>"
                     f"<td class=l style='color:{sidecol}'>{SIDE_KO.get(p['side'],p['side'])}</td>"
                     f"<td>{won(p['price'])} × {p['qty']}</td><td class=l>{fillstr}</td>"
                     f"<td>{'' if r['days'] is None else str(r['days'])+'일'}</td><td>{slip}</td></tr>")
    if not R["recs"]:
        rec_rows = "<tr><td colspan=7 class=l style=color:#9aa0aa>제안기록 없음 — `--snapshot`으로 적재</td></tr>"

    hold_rows = ""
    for h in perf["holdings"]:
        pflag = "" if h["priced"] else " <span class=s>(평단폴백)</span>"
        hold_rows += (f"<tr><td class=l><b>{h['name']}</b> <span class=s>{h['code']}</span></td>"
                      f"<td>{won(h['qty'])}</td><td>{won(h['avg'])}</td><td>{won(h['last'])}{pflag}</td>"
                      f"<td>{won(h['mval'])}</td><td style='color:{col(h['unreal'])}'>{won(h['unreal'])}</td></tr>")
    if not perf["holdings"]:
        hold_rows = "<tr><td colspan=6 class=l style=color:#9aa0aa>보유 없음</td></tr>"

    benchstr = ("<div class=k>KOSPI 매수후보유<b>" + pct(R["bench"]) + "</b></div>"
                "<div class=k>초과수익<b style='color:" + col(perf['ret'] - R['bench']) + "'>"
                + f"{(perf['ret']-R['bench'])*100:+.2f}%p</b></div>") if R["bench"] is not None else ""
    priced_warn = "" if perf["priced"] else "<div class=s style='color:#ffca3a;margin-top:4px'>⚠ 시세 CSV 없음 — 평가액은 평단 폴백(평가손익 0). PC에서 실행 시 실제 평가 반영.</div>"

    cost = R.get("cost")
    netkpi = ""; cost_block = ""
    if cost:
        m = cost["model"]
        netkpi = (f"<div class=k>순수익률<span class=s>(비용반영)</span><b style='color:{col(cost['net_ret'])}'>"
                  f"{pct(cost['net_ret'])}</b></div>")
        verdict = ""
        if R["bench"] is not None:
            edge = cost["net_ret"] - R["bench"]
            verdict = (f" · <b style='color:{col(edge)}'>§3-3: 비용 반영 후 KOSPI 대비 {edge*100:+.2f}%p "
                       f"({'이김' if edge>0 else '짐'})</b>")
        cost_block = (f"<h2>[C] 비용검증 — 세금·수수료 반영 (§3-3)</h2>"
                      f"<div class=s>가정: 매도세 {m.tax_kosdaq*100:.2f}%(2026·농특세 포함, 매도만) · "
                      f"위탁수수료 편도 {m.commission*100:.3f}% · 손익분기 왕복 <b>+{cost['breakeven']*100:.2f}%</b> "
                      f"(진우_비용설정.json으로 편집){verdict}</div>"
                      f"<table><thead><tr><th class=l>항목</th><th>매수수수료</th><th>매도세금</th>"
                      f"<th>매도수수료</th><th>총비용</th><th>총수익률</th><th>순수익률</th></tr></thead>"
                      f"<tbody><tr><td class=l>합계</td><td>{won(cost['buy_fee'])}</td><td>{won(cost['sell_tax'])}</td>"
                      f"<td>{won(cost['sell_fee'])}</td><td>{won(cost['total'])}</td>"
                      f"<td style='color:{col(perf['ret'])}'>{pct(perf['ret'])}</td>"
                      f"<td style='color:{col(cost['net_ret'])}'>{pct(cost['net_ret'])}</td></tr></tbody></table>")

    return f"""<!DOCTYPE html><html lang=ko><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>진우 전진기록</title><style>body{{margin:0;background:#0f1115;color:#e8eaed;font-family:'Malgun Gothic',system-ui,sans-serif;font-size:13px}}
.w{{max-width:1000px;margin:0 auto;padding:20px 16px 50px}}h1{{font-size:20px;margin:0 0 3px}}h2{{font-size:14px;margin:22px 0 4px}}.s{{color:#9aa0aa;font-size:11px}}
.kpi{{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}}.k{{background:#171a21;border:1px solid #242a35;border-radius:10px;padding:10px 14px;min-width:104px}}.k b{{font-size:16px;display:block;margin-top:3px}}
table{{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:6px}}th,td{{padding:7px 9px;text-align:right;border-bottom:1px solid #242a35;white-space:nowrap}}th{{color:#9aa0aa}}.l{{text-align:left}}
.foot{{color:#9aa0aa;font-size:11px;margin-top:16px;line-height:1.7}}</style></head><body><div class=w>
<h1>진우 전진기록 <span style=color:#ff7a45>· 제안 규율 &amp; 성과 (§3-2)</span></h1>
<div class=s>생성 {gen} · 기록시작 {R['start'] or '-'} · 제안 {R['nprops']}건 · 체결 {R['nfills']}건 · 확인 후 집행</div>
<div class=kpi>
<div class=k>체결률<b>{fs['fill_rate']*100:.0f}%</b></div>
<div class=k>평균 슬리피지<b style='color:{slipcol(fs['avg_slip'])}'>{pct(fs['avg_slip'])}</b></div>
<div class=k>시드<b>{won(perf['seed'])}</b></div>
<div class=k>자산<b>{won(perf['equity'])}</b></div>
<div class=k>총수익률<b style='color:{col(perf['ret'])}'>{pct(perf['ret'])}</b></div>
{netkpi}
<div class=k>실현손익<b style='color:{col(perf['realized'])}'>{won(perf['realized'])}</b></div>
{benchstr}</div>{priced_warn}
<h2>[A] 규율 — 제안 대비 체결 (슬리피지 양수=엣지 손해)</h2>
<table><thead><tr><th class=l>제안일</th><th class=l>종목</th><th class=l>구분</th><th>제안</th><th class=l>체결</th><th>소요</th><th>슬리피지</th></tr></thead>
<tbody>{rec_rows}</tbody></table>
<h2>[B] 보유 평가</h2>
<table><thead><tr><th class=l>종목</th><th>수량</th><th>평단</th><th>현재가</th><th>평가액</th><th>평가손익</th></tr></thead>
<tbody>{hold_rows}</tbody></table>
{cost_block}
<div class=foot>⚠️ <b>전진 기록·검증 도구</b> — 주문/집행 안 함 · 제안대로 손으로 체결했는지(규율)와 이기고 있는지(성과)를 3~6개월 밀어 확인 · 슬리피지·비용 반영해도 이기면 §3-3 통과 · 기준 미달 시 다음단계로 안 감 · 투자자문 아님·책임 본인.</div>
</div></body></html>"""

# ────────────────────────── snapshot 명령 ──────────────────────────
def do_snapshot(args):
    G = _load_module(GEN_PATH, "jinwoo_gen")
    g = G.generate(capital=args.capital, n=args.n, include_bounce=args.include_bounce,
                   sizing=args.sizing, risk_pct=args.risk_pct, use_conf=args.conf,
                   sector_cap=args.sector_cap, group_cap=args.group_cap,
                   apply_caps=not args.no_caps, do_sell=True)
    today = datetime.date.today().isoformat()
    new = proposals_from_engine(g, today)
    existing = read_proposals()
    merged, added = merge_snapshot(existing, new)
    write_proposals(merged)
    print(f"제안 스냅샷: {today} · 신규 {len(added)}건 적재 (누적 {len(merged)}건) → 진우_제안기록.csv")
    if not added:
        print("  (오늘 제안이 없거나 이미 적재됨 — 중복 방지로 재적재 안 함)")

# ────────────────────────── self-test ──────────────────────────
def _self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")

    # 슬리피지
    chk("슬리피지 매수: 비싸게=손해(+)", abs(slippage_frac("buy", 100, 102) - 0.02) < 1e-9)
    chk("슬리피지 매수: 싸게=이득(−)", slippage_frac("buy", 100, 98) < 0)
    chk("슬리피지 매도: 싸게=손해(+)", abs(slippage_frac("sell", 100, 98) - 0.02) < 1e-9)
    chk("슬리피지 매도: 비싸게=이득(−)", slippage_frac("sell", 100, 102) < 0)
    chk("슬리피지 제안가0 → None", slippage_frac("buy", 0, 100) is None)

    # 정산 매칭
    props = [dict(date="2026-07-01", code="000001", side="buy", price=1000, qty=10, name="A"),
             dict(date="2026-07-01", code="000002", side="buy", price=2000, qty=5, name="B"),
             dict(date="2026-07-02", code="000001", side="sell", price=1200, qty=10, name="A")]
    fills = [dict(date="2026-07-01", code="000001", side="buy", price=1010, qty=10),   # A 매수 체결
             dict(date="2026-07-03", code="000001", side="sell", price=1150, qty=10)]  # A 매도 체결(제안보다 낮음)
    recs, unmatched = reconcile(props, fills)
    by = {(r["prop"]["code"], r["prop"]["side"]): r for r in recs}
    chk("정산: A매수 체결 매칭", by[("000001","buy")]["filled"] and by[("000001","buy")]["fill"]["price"] == 1010)
    chk("정산: B매수 미체결", not by[("000002","buy")]["filled"])
    chk("정산: A매도 체결 소요1일(07-02→07-03)", by[("000001","sell")]["days"] == 1)
    chk("정산: A매도 슬리피지 손해(+)", by[("000001","sell")]["slip"] > 0)
    chk("정산: 남은 체결 없음", unmatched == [])

    # 체결이 제안보다 앞선 날짜면 매칭 안 됨
    p2 = [dict(date="2026-07-05", code="000001", side="buy", price=1000, qty=1, name="A")]
    f2 = [dict(date="2026-07-01", code="000001", side="buy", price=1000, qty=1)]  # 제안 전 체결
    r2, u2 = reconcile(p2, f2)
    chk("정산: 제안 이전 체결은 미매칭", (not r2[0]["filled"]) and len(u2) == 1)

    # 통계
    fs = fill_stats(recs)
    chk("통계: 체결률 2/3", abs(fs["fill_rate"] - 2/3) < 1e-9 and fs["n_filled"] == 2)
    chk("통계: 미체결 있으면 avg_slip은 체결분만", fs["avg_slip"] is not None)

    # 성과 집계
    trades = [dict(date="2026-07-01", code="000001", name="A", side="매수", price=1000, qty=10),
              dict(date="2026-07-05", code="000001", name="A", side="매도", price=1200, qty=5)]
    cash = [dict(date="2026-07-01", side="입금", amount=100000)]
    perf = perf_summary(trades, cash, {"000001": 1300})
    # 시드10만, 매수1만, 매도6천 → 현금 10만-1만+6천=9.6만. 보유 5주@평단1000, last1300 → 평가6500, 평가손익1500
    chk("성과: 현금 96,000", abs(perf["cash"] - 96000) < 1e-6)
    chk("성과: 실현손익 (1200-1000)*5=1000", abs(perf["realized"] - 1000) < 1e-6)
    chk("성과: 평가액 5*1300=6500", abs(perf["hold_value"] - 6500) < 1e-6)
    chk("성과: 평가손익 (1300-1000)*5=1500", abs(perf["unrealized"] - 1500) < 1e-6)
    chk("성과: 자산=현금+평가=102,500", abs(perf["equity"] - 102500) < 1e-6)
    chk("성과: 총수익률 +2.5%", abs(perf["ret"] - 0.025) < 1e-9)
    chk("성과: priced=True", perf["priced"])
    # 시세 없음 → 평단 폴백, 평가손익 0
    perf0 = perf_summary(trades, cash, {})
    chk("성과: 시세없음 평가손익 0", abs(perf0["unrealized"]) < 1e-6 and not perf0["priced"])

    # 벤치마크
    chk("벤치마크: 100→110 = +10%", abs(benchmark_return([100, 105, 110]) - 0.10) < 1e-9)
    chk("벤치마크: 데이터부족 None", benchmark_return([100]) is None)

    # 스냅샷 중복 방지
    ex = [dict(date="2026-07-01", code="000001", side="buy")]
    new = [dict(date="2026-07-01", code="000001", side="buy"),   # 중복
           dict(date="2026-07-01", code="000002", side="buy")]   # 신규
    merged, added = merge_snapshot(ex, new)
    chk("스냅샷: 중복 1건 제외·신규 1건만 적재", len(added) == 1 and len(merged) == 2)

    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot

# ────────────────────────── main ──────────────────────────
def main():
    ap = argparse.ArgumentParser(description="진우 전진기록 — 제안 규율 & 성과 추적(§3-2)")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--snapshot", action="store_true", help="오늘 엔진 제안을 진우_제안기록.csv에 적재")
    ap.add_argument("--capital", type=float, default=10000000)
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--include-bounce", action="store_true")
    ap.add_argument("--sizing", choices=["equal", "risk"], default="equal")
    ap.add_argument("--risk-pct", type=float, default=1.0)
    ap.add_argument("--conf", action="store_true")
    ap.add_argument("--sector-cap", type=int, default=2)
    ap.add_argument("--group-cap", type=int, default=1)
    ap.add_argument("--no-caps", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return 0 if _self_test() else 1
    if a.snapshot:
        do_snapshot(a); return 0
    R = build_report()
    render(R)
    open(OUT, "w", encoding="utf-8").write(build_html(R))
    print(f"\n저장: 진우_전진기록_현황.html")
    return 0

if __name__ == "__main__":
    sys.exit(main())
