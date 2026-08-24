#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""broker/base.py — 증권사 비종속 브로커 추상 계층 (진우_증권사API_설계.md §3)

원칙: 엔진이 주문 '생성' → 사람이 '승인' → API가 '집행'. 무인 방아쇠 없음. 모의(paper) 먼저.
어댑터 패턴: 여기 추상 Broker + OrderReq/OrderAck 만 두고, 증권사별 구현(kis.py 등)이 상속.
이 파일은 순수 인터페이스 + 오프라인 MockBroker(테스트용) — 네트워크 없음.

⚠️ 실거래 API는 진우 PC 전용(클라우드 금지). 키/토큰은 로컬에만. 투자자문 아님·책임 본인.
"""
from dataclasses import dataclass, field
from abc import ABC, abstractmethod
import time

@dataclass
class OrderReq:
    """증권사 비종속 주문안 (진우_리스크차단기.OrderReq와 동일 골격)."""
    code: str
    side: str          # "buy" | "sell"
    qty: int
    price: int         # 지정가. 0이면 시장가.
    name: str = ""
    market: str = "KOSPI"   # "KOSPI" | "KOSDAQ"

@dataclass
class OrderAck:
    """집행 응답."""
    ok: bool
    order_no: str = ""     # 주문번호(ODNO)
    filled_qty: int = 0
    avg_price: float = 0.0
    raw: dict = field(default_factory=dict)
    error: str = ""

class Broker(ABC):
    """모든 증권사 어댑터의 공통 인터페이스. paper=True가 기본(모의투자)."""
    def __init__(self, paper: bool = True):
        self.paper = paper
        self._authed = False

    @abstractmethod
    def auth(self) -> bool: ...
    @abstractmethod
    def price(self, code: str) -> int:
        """현재가(원). 실패 시 0."""
    @abstractmethod
    def balance(self) -> dict:
        """{cash:int, equity:int, positions:{code:{qty,avg}}}"""
    @abstractmethod
    def submit(self, order: OrderReq) -> OrderAck: ...

    def require_paper(self):
        """실계좌 오발주 방지 안전핀: 명시적으로 paper=False 를 켜지 않으면 모의만 허용."""
        if not self.paper:
            raise RuntimeError("실계좌 모드 — 코드에서 명시적 확인 없이는 집행 금지(안전핀)")

# ────────────────────────── 오프라인 테스트용 MockBroker ──────────────────────────
class MockBroker(Broker):
    """네트워크 없이 어댑터·승인러너·RiskGuard 통합을 검증하는 가짜 브로커."""
    def __init__(self, cash=10_000_000, prices=None, positions=None):
        super().__init__(paper=True)
        self._cash=cash; self._prices=prices or {}; self._pos=positions or {}
        self._seq=0
    def auth(self): self._authed=True; return True
    def price(self, code): return int(self._prices.get(code, 0))
    def balance(self):
        equity=self._cash+sum(p["qty"]*self._prices.get(c,p.get("avg",0)) for c,p in self._pos.items())
        return dict(cash=self._cash, equity=int(equity), positions=dict(self._pos))
    def submit(self, order: OrderReq) -> OrderAck:
        self._seq+=1; px=order.price or self._prices.get(order.code,0)
        if order.side=="buy":
            cost=px*order.qty
            if cost>self._cash: return OrderAck(False, error="현금부족(mock)")
            self._cash-=cost
            p=self._pos.get(order.code, {"qty":0,"avg":0})
            newqty=p["qty"]+order.qty
            p["avg"]=(p["avg"]*p["qty"]+px*order.qty)/newqty if newqty else px
            p["qty"]=newqty; self._pos[order.code]=p
        else:
            p=self._pos.get(order.code, {"qty":0,"avg":0})
            if order.qty>p["qty"]: return OrderAck(False, error="보유수량 초과(mock)")
            p["qty"]-=order.qty; self._cash+=px*order.qty; self._pos[order.code]=p
        return OrderAck(True, order_no=f"MOCK{self._seq:06d}", filled_qty=order.qty, avg_price=px)

def _self_test():
    ok=tot=0
    def chk(n,c):
        nonlocal ok,tot; tot+=1; ok+=1 if c else 0; print(f"  [{'OK' if c else 'FAIL'}] {n}")
    b=MockBroker(cash=1_000_000, prices={"005930":70000})
    chk("auth", b.auth())
    chk("price 조회", b.price("005930")==70000)
    a=b.submit(OrderReq("005930","buy",10,70000,"삼성전자"))
    chk("매수 체결", a.ok and a.filled_qty==10)
    chk("현금 차감", b.balance()["cash"]==300000)
    chk("포지션 반영", b.balance()["positions"]["005930"]["qty"]==10)
    a2=b.submit(OrderReq("005930","buy",100,70000)); chk("현금부족 거절", not a2.ok)
    a3=b.submit(OrderReq("005930","sell",10,72000)); chk("매도 체결", a3.ok)
    chk("매도 후 현금 회수", b.balance()["cash"]==300000+720000)
    print(f"\n셀프테스트: {ok}/{tot}"); return ok==tot

if __name__=="__main__":
    import sys
    try: sys.stdout.reconfigure(encoding="utf-8")
    except Exception: pass
    sys.exit(0 if _self_test() else 1)
