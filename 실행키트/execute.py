#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""execute.py — 승인 러너 (엔진 주문안 → RiskGuard → 사람 승인 → 브로커 집행) · 개선안 ⑥

진우_증권사API_설계.md §3-4의 반자동 집행 계층. **자동 승인 절대 금지.**
파이프라인:
  진우_주문생성.generate()  →  OrderReq[]  →  [진우_리스크차단기.RiskGuard] 차단검사
     →  사람이 주문마다 y/N 승인  →  broker.submit()  →  진우_모의매매장.csv 기록

기본은 MockBroker(오프라인) — 실집행은 --broker kis 로 KIS 모의계좌(진우 PC).
RiskGuard(집행 직전 방어) + 사이징_강제(전략 규모) 는 별개 계층이며 여기서 RiskGuard를 끼운다.

사용:
  py execute.py --self-test                 # 오프라인 통합 검증(Mock)
  py execute.py --demo                       # 가짜 주문안으로 승인 흐름 시연(Mock)
  py execute.py --broker kis --paper         # 진우 PC: 엔진 주문안 → KIS 모의 집행
⚠️ 통과·승인해도 실계좌 아님(기본 Mock/모의). 실전 전 §3-2·3-3 통과 필수. 투자자문 아님·책임 본인.
"""
import os, sys, csv, json, argparse, importlib.util, datetime

BASE=os.path.dirname(os.path.abspath(__file__))
ROOT=os.path.dirname(BASE)   # 프로젝트 루트(진우_* 파일 위치 가정: 실행키트 상위)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def _load(path, name):
    spec=importlib.util.spec_from_file_location(name, path)
    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m

def _find(fn):
    for d in (ROOT, BASE, os.getcwd()):
        p=os.path.join(d, fn)
        if os.path.exists(p): return p
    return None

def load_riskguard():
    """진우_리스크차단기.py 를 단일 진실원천으로 재사용(RiskGuard/Limits/OrderReq/MarketCtx)."""
    p=_find("진우_리스크차단기.py")
    if not p: raise FileNotFoundError("진우_리스크차단기.py 를 찾지 못함(프로젝트 루트에서 실행).")
    return _load(p, "jinwoo_riskguard")

def get_broker(kind, paper=True):
    if kind=="kis":
        sys.path.insert(0, BASE)
        from broker.kis import KIS
        b=KIS(paper=paper); b.auth(); return b
    from broker.base import MockBroker
    # 데모용 시세/현금
    return MockBroker(cash=3_000_000, prices={"005930":70000,"000660":200000,"042700":95000})

def log_fill(order, ack, path=None):
    path=path or _find("진우_모의매매장.csv") or os.path.join(ROOT,"진우_모의매매장.csv")
    new=not os.path.exists(path)
    with open(path,"a",newline="",encoding="utf-8") as f:
        w=csv.writer(f)
        if new: w.writerow(["ts","code","name","side","qty","price","order_no","ok","error"])
        w.writerow([datetime.datetime.now().isoformat(timespec="seconds"),
                    order.code, order.name, order.side, order.qty, order.price,
                    ack.order_no, ack.ok, ack.error])

def run(orders, broker, RG, limits=None, auto_yes=False):
    """orders: RG.OrderReq[] · broker: Broker · RG: 리스크차단기 모듈."""
    limits = limits or RG.Limits.load()
    bal=broker.balance()
    ctx=RG.MarketCtx(cash=bal["cash"], equity=bal["equity"], positions=bal["positions"],
                     market_price={o.code: broker.price(o.code) for o in orders},
                     realized_today=0, ordered_today=set())
    guard=RG.RiskGuard(limits)
    print("="*74); print(f"승인 러너 — {'모의(paper)' if getattr(broker,'paper',True) else '실전'} · 자동승인={auto_yes}")
    print("="*74)
    print(f"  현금 {ctx.cash:,} · 자본 {ctx.equity:,} · 주문안 {len(orders)}건\n")
    done=0
    for o in orders:
        v=guard.check(o, ctx)
        tag="통과✔" if v.ok else "차단✖"
        detail=f" · {v.reason}" if v.reason else ""
        print(f"  [{tag}] {o.side:<4} {o.name[:12]:<12} {o.qty:>4}주 @ {o.price:>8,}{detail}")
        if not v.ok: continue
        # 사람 승인
        if auto_yes:
            ans="y"
        else:
            try: ans=input("       승인? (y/N) ").strip().lower()
            except EOFError: ans="n"
        if ans!="y":
            print("       → 보류(미집행)"); continue
        ack=broker.submit(o)
        log_fill(o, ack)
        if ack.ok:
            done+=1; print(f"       → 집행 {ack.order_no} · {ack.filled_qty}주 @ {ack.avg_price:,.0f}")
            ctx.ordered_today.add(o.code)   # 당일 중복 방지 반영
        else:
            print(f"       → 실패: {ack.error}")
    print(f"\n  집행 {done}/{len(orders)}건. ※ 자동집행 아님 — 승인건만 전송. 투자자문 아님·책임 본인.")
    return done

def demo():
    RG=load_riskguard()
    from broker.base import MockBroker
    b=MockBroker(cash=10_000_000, prices={"005930":70000,"000660":200000,"042700":95000})
    O=RG.OrderReq
    orders=[O("005930","buy",10,70000,"삼성전자"),       # 7% · 밴드ok → 통과·집행
            O("000660","buy",100,200000,"SK하이닉스"),   # 2000만 > 현금 → 차단(현금)
            O("042700","buy",5,950000,"한미반도체")]      # 밴드 오타(95만 vs 기준 9.5만) → 차단(밴드)
    run(orders, b, RG, auto_yes=True)

def _self_test():
    ok=tot=0
    def chk(n,c):
        nonlocal ok,tot; tot+=1; ok+=1 if c else 0; print(f"  [{'OK' if c else 'FAIL'}] {n}")
    RG=load_riskguard()
    from broker.base import MockBroker
    b=MockBroker(cash=10_000_000, prices={"005930":70000,"000660":200000})
    O=RG.OrderReq
    # 정상 매수 1건(70만, 자본10M의 7% · 밴드ok) 자동승인 → 집행 1
    done=run([O("005930","buy",10,70000,"삼성전자")], b, RG, auto_yes=True)
    chk("정상 매수 집행", done==1)
    chk("현금 차감 반영", b.balance()["cash"]==9_300_000)
    # 현금부족 매수(200만) → RiskGuard 차단 → 집행 0
    b2=MockBroker(cash=1_000_000, prices={"000660":200000})
    done2=run([O("000660","buy",100,200000,"하이닉스")], b2, RG, auto_yes=True)
    chk("현금초과 RiskGuard 차단(미집행)", done2==0)
    # 가격밴드 오타(기준 7만 vs 70만) → 차단
    b3=MockBroker(cash=100_000_000, prices={"005930":70000})
    done3=run([O("005930","buy",1,700000,"삼성전자")], b3, RG, auto_yes=True)
    chk("가격밴드 오타 차단", done3==0)
    print(f"\n셀프테스트: {ok}/{tot}  (RiskGuard+MockBroker 통합)")
    return ok==tot

def main():
    ap=argparse.ArgumentParser(description="승인 러너(반자동 집행) · 개선안 ⑥")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--broker", choices=["mock","kis"], default="mock")
    ap.add_argument("--paper", action="store_true", help="모의(기본)")
    ap.add_argument("--live", action="store_true", help="실전(신중)")
    ap.add_argument("--yes", action="store_true", help="일괄 승인(테스트용, 실전 금지)")
    a=ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    if a.demo: demo(); return 0
    # 실사용: 엔진 주문안 로드 → 승인 러너
    RG=load_riskguard()
    genp=_find("진우_주문생성.py")
    if not genp: print("진우_주문생성.py 없음 — 프로젝트 루트에서 실행."); return 1
    G=_load(genp,"jinwoo_gen")
    g=G.generate(capital=10_000_000, n=12, include_bounce=True, sizing="risk",
                 risk_pct=1.0, apply_caps=True, do_sell=True)
    orders=RG.orders_from_engine(g)
    broker=get_broker(a.broker, paper=not a.live)
    run(orders, broker, RG, auto_yes=a.yes)
    return 0

if __name__=="__main__":
    sys.exit(main())
