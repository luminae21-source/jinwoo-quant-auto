#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우_모의매매.py — 모의매매(페이퍼 트레이딩) 추적 + 검증규칙 신호

목적: 검증된 규칙을 실제 돈 없이 연습. 매매를 기록하면 현재가로 평가손익·포트폴리오 현황 + 규칙 신호.
기록: 진우_모의매매장.csv  (헤더: 날짜,코드,종목명,구분,가격,수량,메모)  구분=매수 또는 매도
      · 없으면 예시 템플릿 자동 생성. 진우님이 여기에 매매를 적으면 됨.
평가: 30년 일봉 최신 종가 · MA200(이격도) · 최신 PBR · 보유일.
검증규칙 신호(딥밸류 기준, 매도규칙서 §9):
  · 익절검토(강함에 판다): 이격≥1.5 or 수익≥+100% or PBR≥1.0
  · 재난백스톱: 수익≤−40% (넓은 백스톱만 · 타이트 스톱은 휩쏘라 금지)
  · 장기재평가: 보유 3년(1095일) 근접
  · 분산: 종목수 10~15 권장 · 한 종목 비중 과대 경고
산출: 콘솔 + 진우_모의매매_현황.html · 투자자문 아님·결정 본인.
사용: py 진우_모의매매.py [--capital 10000000] [--self-test]
"""
import os, sys, csv, argparse, io, datetime
BASE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(BASE, "진우_모의매매장.csv")
OUT = os.path.join(BASE, "진우_모의매매_현황.html")
RECENT = 600000
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def _rr(pd, path, n, cols):
    with open(path, "rb") as f:
        h = f.readline(); f.seek(0, 2); pos = f.tell(); data = b""; nl = 0; blk = 1 << 20
        while pos > 0 and nl <= n:
            s = min(blk, pos); pos -= s; f.seek(pos); data = f.read(s)+data; nl = data.count(b"\n")
    lines = [l for l in data.split(b"\n") if l.strip()]
    return pd.read_csv(io.BytesIO(h+b"\n".join(lines[-n:])), usecols=cols, dtype={"code": str}, encoding="utf-8-sig")

def load_pbr_latest():
    P = {}
    for mk in ("KOSPI", "KOSDAQ"):
        p = os.path.join(BASE, f"종목재무_KRX_{mk}.csv")
        if not os.path.exists(p): continue
        rows = []
        with open(p, encoding="utf-8-sig", newline="") as f:
            rd = csv.reader(f); next(rd, None)
            for r in rd:
                if len(r) >= 5: rows.append((r[0].strip(), r[1], r[4]))
        if not rows: continue
        last = max(d for d, _, _ in rows)
        for d, code, pbr in rows:
            if d == last:
                try: v = float(pbr)
                except ValueError: v = 0
                if v > 0: P[code.zfill(6)] = v
    return P

def market_regime():
    p = os.path.join(BASE, "kospi_index_daily.csv")
    if not os.path.exists(p): return None
    cl = []
    with open(p, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            r = {k.lstrip("﻿").lower(): v for k, v in r.items()}
            try: cl.append(float(r["close"]))
            except (ValueError, KeyError): pass
    if len(cl) < 200: return None
    return ("하락장" if cl[-1] < sum(cl[-200:])/200 else "강세장", cl[-1], sum(cl[-200:])/200)

def ensure_template():
    if os.path.exists(LEDGER): return False
    with open(LEDGER, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["날짜", "코드", "종목명", "구분", "가격", "수량", "메모"])
        w.writerow(["2026-07-15", "", "현금", "입금", "10000000", "", "초기 시드(예시 — 금액은 가격칸)"])
        w.writerow(["2026-07-16", "247540", "에코프로비엠", "매수", "180000", "5", "예시 — 지우고 실제 매매 기록"])
    return True

def read_ledger():
    """매매(매수/매도) + 현금흐름(입금/출금) 분리 반환."""
    trades = []; cash = []
    with open(LEDGER, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            r = {k.lstrip("﻿"): (v or "").strip() for k, v in r.items()}
            side = r.get("구분", "매수") or "매수"
            raw = r.get("코드", ""); date = r.get("날짜", ""); memo = r.get("메모", "")
            try: price = float(r.get("가격") or 0); qty = float(r.get("수량") or 0)
            except ValueError: continue
            if side in ("입금", "출금"):
                cash.append(dict(date=date, side=side, amount=price*(qty if qty > 0 else 1), memo=memo)); continue
            if not raw or qty <= 0: continue
            trades.append(dict(date=date, code=raw.zfill(6), name=r.get("종목명", ""),
                               side=side, price=price, qty=qty, memo=memo))
    return trades, cash

def positions(trades):
    """평균원가법: 보유수량·평단·실현손익."""
    pos = {}
    realized = 0.0
    for t in sorted(trades, key=lambda x: x["date"]):
        p = pos.setdefault(t["code"], dict(name=t["name"], qty=0.0, cost=0.0, first=t["date"]))
        if t["name"]: p["name"] = t["name"]
        if t["side"] == "매수":
            p["cost"] += t["price"]*t["qty"]; p["qty"] += t["qty"]
        else:  # 매도
            if p["qty"] > 0:
                avg = p["cost"]/p["qty"]
                sell_q = min(t["qty"], p["qty"])
                realized += (t["price"]-avg)*sell_q
                p["cost"] -= avg*sell_q; p["qty"] -= sell_q
    return pos, realized

def prices(pd, codes):
    frames = []
    for mk in ("KOSPI", "KOSDAQ"):
        p = os.path.join(BASE, f"종목일봉_30년_{mk}.csv")
        if os.path.exists(p):
            d = _rr(pd, p, RECENT, ["date", "code", "close"])
            d["code"] = d["code"].str.zfill(6); d = d[d["code"].isin(codes)]
            frames.append(d)
    if not frames: return {}
    d = pd.concat(frames, ignore_index=True)
    d["close"] = pd.to_numeric(d["close"], errors="coerce"); d = d.dropna(subset=["close"])
    d = d.sort_values(["code", "date"])
    out = {}
    for code, g in d.groupby("code"):
        cl = g["close"]
        if len(cl) < 1: continue
        ma200 = cl.rolling(200).mean().iloc[-1] if len(cl) >= 200 else float("nan")
        out[code] = dict(last=float(cl.iloc[-1]), ma200=float(ma200) if ma200 == ma200 else None,
                         asof=str(g["date"].iloc[-1]))
    return out

def signals(ret, ext, hold_days, pbr):
    s = []
    # PBR 익절은 '딥밸류→적정가 회귀'에만 유효 → 적정가치권(1.0~2.5)일 때만. 고PBR 성장주엔 무의미.
    pbr_fair = pbr is not None and 1.0 <= pbr <= 2.5
    if (ext is not None and ext >= 1.5) or ret >= 1.0 or pbr_fair:
        why = []
        if ext is not None and ext >= 1.5: why.append(f"이격{ext:.2f}")
        if ret >= 1.0: why.append("수익+100%")
        if pbr_fair: why.append(f"PBR{pbr:.2f} 적정권(딥밸류였다면)")
        s.append("익절검토(강함에 판다: "+"·".join(why)+")")
    if ret <= -0.40: s.append("재난백스톱 검토(−40%↓)")
    if hold_days is not None and hold_days >= 1095: s.append("장기재평가(3년 도달)")
    return s or ["보유 유지"]

def build(rows, tot, regime, trades, cashflows):
    def won(n): return f"{n:,.0f}"
    gen = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    rn = regime[0] if regime else "-"
    body = []
    for r in rows:
        col = "#3fb37a" if r["ret"] >= 0 else "#e2606a"
        sig = " · ".join(r["sig"]); sc = "#ffca3a" if "익절" in sig or "백스톱" in sig or "재평가" in sig else "#9aa0aa"
        body.append(f"<tr><td class=l><b>{r['name']}</b> <span class=s>{r['code']}</span></td>"
                    f"<td>{won(r['qty'])}</td><td>{won(r['avg'])}</td><td>{won(r['last'])}</td>"
                    f"<td style='color:{col}'>{r['ret']*100:+.1f}%</td><td style='color:{col}'>{won(r['pl'])}</td>"
                    f"<td>{r['ext']:.2f}" + ("" if r['ext'] else "-") + f"</td><td>{r['pbr'] or '-'}</td>"
                    f"<td>{r['days']}일</td><td style='color:{sc}'>{sig}</td></tr>")
    # 매매내역 표 (매매+현금흐름, 날짜순)
    allrows = [dict(date=t["date"], side=t["side"], name=t["name"] or t["code"], qty=t["qty"], price=t["price"], memo=t.get("memo","")) for t in trades]
    allrows += [dict(date=c["date"], side=c["side"], name="현금", qty="", price=c["amount"], memo=c.get("memo","")) for c in cashflows]
    allrows.sort(key=lambda x: x["date"])
    scol = {"매수":"#3fb37a","매도":"#e2606a","입금":"#5aa0f0","출금":"#c77dff"}
    hist = "".join(f"<tr><td class=l>{a['date']}</td><td class=l style='color:{scol.get(a['side'],'#9aa0aa')}'>{a['side']}</td>"
                   f"<td class=l>{a['name']}</td><td>{won(a['qty']) if a['qty']!='' else '-'}</td><td>{won(a['price'])}</td>"
                   f"<td class=l s>{a['memo']}</td></tr>" for a in allrows)
    tr = tot["asset"]-tot["seed"]; trc = "#3fb37a" if tr >= 0 else "#e2606a"
    ndiv = len(rows)
    dwarn = "" if 10 <= ndiv <= 20 else (f" ⚠️ {ndiv}종 (권장 10~15)" if ndiv else "")
    return f"""<!DOCTYPE html><html lang=ko><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>진우 모의매매 현황</title><style>
body{{margin:0;background:#0f1115;color:#e8eaed;font-family:'Malgun Gothic',system-ui,sans-serif;font-size:13px}}
.w{{max-width:1000px;margin:0 auto;padding:20px 16px 50px}}h1{{font-size:20px;margin:0 0 3px}}.s{{color:#9aa0aa;font-size:11px}}
.kpi{{display:flex;gap:10px;flex-wrap:wrap;margin:12px 0}}.k{{background:#171a21;border:1px solid #242a35;border-radius:10px;padding:10px 14px;min-width:120px}}
.k b{{font-size:18px;display:block;margin-top:3px}}
table{{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:8px}}th,td{{padding:6px 8px;text-align:right;border-bottom:1px solid #242a35;white-space:nowrap}}
th{{color:#9aa0aa;font-weight:600}}.l,td.l{{text-align:left}}.foot{{color:#9aa0aa;font-size:11px;margin-top:14px;line-height:1.7}}</style></head>
<body><div class=w><h1>진우 모의매매 현황 <span style=color:#ff7a45>· 페이퍼 트레이딩</span></h1>
<div class=s>생성 {gen} · 시장 {rn} · 규칙: 딥밸류=스톱없이 보유·강함에 익절 (매도규칙서 §9)</div>
<div class=kpi>
<div class=k>총투입<b>{won(tot['seed'])}</b></div>
<div class=k>현금<b>{won(tot['cash'])}</b></div>
<div class=k>주식평가<b>{won(tot['eval'])}</b></div>
<div class=k>총자산<b style='color:{trc}'>{won(tot['asset'])}</b></div>
<div class=k>총수익<b style='color:{trc}'>{tr:+,.0f} ({(tot['asset']/tot['seed']-1)*100 if tot['seed'] else 0:+.1f}%)</b></div>
<div class=k>실현손익<b>{won(tot['realized'])}</b></div>
<div class=k>보유종목<b>{ndiv}종{dwarn}</b></div>
</div>
<h1 style="font-size:14px;margin:14px 0 2px">보유 현황</h1>
<table><thead><tr><th class=l>종목</th><th>수량</th><th>평단</th><th>현재가</th><th>수익률</th><th>평가손익</th><th>이격도</th><th>PBR</th><th>보유</th><th class=l>규칙 신호</th></tr></thead>
<tbody>{''.join(body) or '<tr><td colspan=10 class=l style=color:#9aa0aa>보유 없음 — 진우_모의매매장.csv에 매매를 기록하세요</td></tr>'}</tbody></table>
<h1 style="font-size:14px;margin:20px 0 2px">매매 내역</h1>
<table><thead><tr><th class=l>날짜</th><th class=l>구분</th><th class=l>종목</th><th>수량</th><th>가격/금액</th><th class=l>메모</th></tr></thead>
<tbody>{hist or '<tr><td colspan=6 class=l style=color:#9aa0aa>내역 없음</td></tr>'}</tbody></table>
<div class=foot>총투입=초기자본+순입금 · 현금=총투입−매수+매도 · 총자산=현금+주식평가 · 익절검토=강함에 판다(이격≥1.5·+100%·PBR 적정권) · 재난백스톱=−40%(타이트 스톱은 휩쏘라 금지) · 딥밸류는 2~3년 보유·10~15종 분산.<br>
장부: 구분에 <b>입금/출금</b>도 기록 가능(가격=금액). 발굴≠매수신호 · 모의매매 연습용 · 투자자문 아님 · 집행·책임 본인.</div></div></body></html>"""

def run(pd, capital):
    created = ensure_template()
    if created: print(f"[생성] {os.path.basename(LEDGER)} 템플릿 — 여기에 매매를 기록하세요(예시행 지우고).")
    trades, cashflows = read_ledger()
    pos, realized = positions(trades)
    held = {c: p for c, p in pos.items() if p["qty"] > 0.0001}
    buy_cost = sum(t["price"]*t["qty"] for t in trades if t["side"] == "매수")
    sell_proc = sum(t["price"]*t["qty"] for t in trades if t["side"] == "매도")
    net_dep = sum(c["amount"] for c in cashflows if c["side"] == "입금") - sum(c["amount"] for c in cashflows if c["side"] == "출금")
    seed = capital + net_dep                 # 총 투입원금(초기자본+순입금)
    cash_bal = seed - buy_cost + sell_proc    # 현재 현금
    px = prices(pd, set(held)) if held else {}
    P = load_pbr_latest(); regime = market_regime()
    today = datetime.date.today()
    rows = []; invest = 0.0; ev = 0.0
    for code, p in held.items():
        avg = p["cost"]/p["qty"]; pr = px.get(code, {})
        last = pr.get("last", avg); ma200 = pr.get("ma200")
        ext = round(last/ma200, 2) if ma200 else None
        ret = last/avg-1; pl = (last-avg)*p["qty"]; pbr = round(P.get(code, 0), 2) or None
        try: fd = datetime.date.fromisoformat(p["first"]); days = (today-fd).days
        except Exception: days = None
        invest += p["cost"]; ev += last*p["qty"]
        rows.append(dict(code=code, name=p["name"] or code, qty=p["qty"], avg=avg, last=last,
                         ext=ext, ret=ret, pl=pl, pbr=pbr, days=days if days is not None else 0,
                         sig=signals(ret, ext, days, pbr)))
    rows.sort(key=lambda r: r["ret"])
    total_asset = cash_bal + ev
    tot = dict(seed=seed, cash=cash_bal, eval=ev, realized=realized, asset=total_asset)
    # 콘솔
    print("\n"+"="*92); print("진우 모의매매 현황  ·  시장:", regime[0] if regime else "-")
    print("="*92)
    if not rows: print("보유 없음 — 진우_모의매매장.csv에 매매를 기록하세요(구분=매수/매도/입금/출금).")
    for r in rows:
        print(f"  {r['name'][:12]:<12} {int(r['qty'])}주 · 평단 {r['avg']:,.0f} · 현재 {r['last']:,.0f} · {r['ret']*100:+.1f}% "
              f"· 이격 {r['ext'] if r['ext'] else '-'} · {r['days']}일 → {' · '.join(r['sig'])}")
    print("-"*92)
    tar = (total_asset/seed-1)*100 if seed else 0
    print(f"  총투입 {seed:,.0f} · 현금 {cash_bal:,.0f} · 주식평가 {ev:,.0f} · 총자산 {total_asset:,.0f} · 총수익 {total_asset-seed:+,.0f}({tar:+.1f}%) · 실현 {realized:+,.0f}")
    if rows and not (10 <= len(rows) <= 20): print(f"  ⚠️ 분산 {len(rows)}종 (딥밸류 권장 10~15종)")
    # 매매내역(최근 12)
    hist = sorted(trades, key=lambda x: x["date"])
    if hist:
        print("\n  [매매내역 최근]")
        for t in hist[-12:]:
            print(f"    {t['date']} {t['side']} {t['name'][:10] or t['code']} {int(t['qty'])}주 @ {t['price']:,.0f}")
    open(OUT, "w", encoding="utf-8").write(build(rows, tot, regime, trades, cashflows))
    print(f"\n저장: 진우_모의매매_현황.html")
    return 0

def _self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0; print(f"  [{'OK' if c else 'FAIL'}] {n}")
    tr = [dict(date="2026-01-02", code="000660", name="A", side="매수", price=100, qty=10),
          dict(date="2026-02-02", code="000660", name="A", side="매수", price=200, qty=10),
          dict(date="2026-03-02", code="000660", name="A", side="매도", price=300, qty=5)]
    pos, real = positions(tr)
    chk("평단 (100*10+200*10)/20=150", abs(pos["000660"]["cost"]/pos["000660"]["qty"]-150) < 1e-6)
    chk("매도5주 실현 (300-150)*5=750", abs(real-750) < 1e-6)
    chk("잔량 15주", abs(pos["000660"]["qty"]-15) < 1e-6)
    chk("익절신호 이격1.6", "익절검토" in signals(0.2, 1.6, 100, 0.5)[0])
    chk("익절신호 +100%", "익절검토" in signals(1.1, 1.0, 100, 0.5)[0])
    chk("재난백스톱 −45%", any("백스톱" in s for s in signals(-0.45, 1.0, 100, 0.5)))
    chk("보유유지 평범", signals(0.1, 1.0, 100, 0.5) == ["보유 유지"])
    chk("장기재평가 3년", any("재평가" in s for s in signals(0.2, 1.0, 1100, 0.5)))
    chk("적정PBR 1.5 → 익절검토", "익절검토" in signals(0.2, 1.0, 100, 1.5)[0])
    chk("고PBR 8.0 → 신호無(보유유지)", signals(0.1, 1.0, 100, 8.06) == ["보유 유지"])
    chk("저PBR 0.7(아직 쌈) → 보유유지", signals(0.1, 1.0, 100, 0.7) == ["보유 유지"])
    print(f"\n셀프테스트: {ok}/{tot}"); return ok == tot

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--capital", type=float, default=10000000)
    ap.add_argument("--self-test", action="store_true"); a = ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    import pandas as pd
    return run(pd, a.capital)

if __name__ == "__main__":
    sys.exit(main())
