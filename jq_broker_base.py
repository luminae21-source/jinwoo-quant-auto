#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""jq_broker_base.py — 증권사 비종속 브로커 인터페이스 (계약)

주문 엔진(진우_주문생성.py)과 집행 러너(jq_execute.py)는 이 인터페이스만 안다.
각 증권사 구현체(jq_broker_kis.py 등)는 이 계약을 지킨다. → 한 증권사에 종속되지 않음.
⚠️ 자동 체결 아님. send()는 사람 승인을 통과한 주문만 호출된다(jq_execute.py). 투자자문 아님·책임 본인.
"""
from dataclasses import dataclass, field


@dataclass
class OrderReq:
    """주문 1건. 진우_주문생성.py 산출을 이 형태로 변환해 넘긴다."""
    code: str                    # 6자리 종목코드
    side: str                    # "buy" | "sell"
    qty: int                     # 주문수량
    price: int = 0               # 지정가. ordtype="market"이면 무시(0)
    ordtype: str = "limit"       # "limit"(지정가) | "market"(시장가)
    reason: str = ""             # 사유(익절검토/딥밸류 등) — 로그·승인 화면용
    name: str = ""               # 종목명(표시용)

    def __post_init__(self):
        self.code = str(self.code).zfill(6)
        if self.side not in ("buy", "sell"):
            raise ValueError(f"side must be buy/sell, got {self.side!r}")
        if self.ordtype not in ("limit", "market"):
            raise ValueError(f"ordtype must be limit/market, got {self.ordtype!r}")
        self.qty = int(self.qty)
        self.price = int(self.price)
        if self.qty <= 0:
            raise ValueError("qty must be > 0")
        if self.ordtype == "limit" and self.price <= 0:
            raise ValueError("limit order needs price > 0")


@dataclass
class OrderAck:
    """주문 전송 결과."""
    ok: bool
    order_no: str = ""
    filled_qty: int = 0
    avg_price: float = 0.0
    msg: str = ""
    raw: dict = field(default_factory=dict)


class Broker:
    """모든 증권사 구현이 지켜야 할 계약. 기본은 모의투자(paper=True)."""

    name = "base"

    def __init__(self, paper: bool = True):
        self.paper = paper          # ★ 기본이 모의투자 — 실계좌는 명시적으로만

    # ── 아래는 각 구현체가 채운다 ──
    def auth(self) -> None:
        """토큰 발급/갱신."""
        raise NotImplementedError

    def cash(self) -> int:
        """주문가능(예수금) 현금."""
        raise NotImplementedError

    def positions(self) -> dict:
        """{code: {'qty': int, 'avg': float}}"""
        raise NotImplementedError

    def price(self, code: str) -> int:
        """현재가."""
        raise NotImplementedError

    def send(self, o: OrderReq) -> OrderAck:
        """주문 전송. ★ 사람 승인을 통과한 주문만 호출할 것."""
        raise NotImplementedError

    def status(self, order_no: str) -> OrderAck:
        """주문 체결 상태 조회."""
        raise NotImplementedError


class DryRunBroker(Broker):
    """네트워크 없이 '쐈다면 이랬을 것'만 기록. 어댑터 배선·러너 검증용.
    cash/positions/price는 주입값(seed)으로 답한다."""
    name = "dryrun"

    def __init__(self, paper=True, seed_cash=10_000_000, seed_pos=None, seed_price=None):
        super().__init__(paper=paper)
        self._cash = int(seed_cash)
        self._pos = dict(seed_pos or {})
        self._price = dict(seed_price or {})
        self.sent = []             # 전송(시뮬)된 주문 로그

    def auth(self): pass
    def cash(self): return self._cash
    def positions(self): return self._pos
    def price(self, code): return int(self._price.get(str(code).zfill(6), 0))

    def send(self, o: OrderReq) -> OrderAck:
        self.sent.append(o)
        return OrderAck(ok=True, order_no=f"DRY{len(self.sent):04d}",
                        filled_qty=o.qty, avg_price=o.price,
                        msg="[DRY-RUN] 전송 안 함", raw=dict(dry=True))

    def status(self, order_no):
        return OrderAck(ok=True, order_no=order_no, msg="[DRY-RUN]")


def _self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")

    o = OrderReq(code="5930", side="buy", qty=10, price=70000)
    chk("code zero-fill '5930'→'005930'", o.code == "005930")
    chk("정상 지정가 생성", o.qty == 10 and o.price == 70000)
    try: OrderReq(code="005930", side="buy", qty=0, price=1); bad = False
    except ValueError: bad = True
    chk("수량 0 → 거부", bad)
    try: OrderReq(code="005930", side="buy", qty=1, price=0, ordtype="limit"); bad2 = False
    except ValueError: bad2 = True
    chk("지정가 가격0 → 거부", bad2)
    m = OrderReq(code="005930", side="sell", qty=1, ordtype="market")
    chk("시장가 가격0 허용", m.ordtype == "market")
    try: OrderReq(code="005930", side="hold", qty=1, price=1); bad3 = False
    except ValueError: bad3 = True
    chk("잘못된 side → 거부", bad3)

    db = DryRunBroker(seed_cash=5_000_000, seed_price={"005930": 71000})
    chk("DryRun 기본 paper=True", db.paper is True)
    chk("DryRun cash 주입", db.cash() == 5_000_000)
    chk("DryRun price 주입", db.price("5930") == 71000)
    ack = db.send(o)
    chk("DryRun send ok·전송기록", ack.ok and len(db.sent) == 1 and "DRY" in ack.order_no)

    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot


if __name__ == "__main__":
    import sys
    sys.exit(0 if _self_test() else 1)
