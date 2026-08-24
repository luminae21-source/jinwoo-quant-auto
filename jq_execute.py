#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""jq_execute.py — 주문 집행 러너 (RiskGuard + 사람 승인 + 장부 기록)

흐름: 진우_주문생성.generate() → 주문안(매도 먼저·매수 나중) → RiskGuard(차단기) → ★사람 승인(y/n) → 브로커 send → 진우_모의매매장.csv 기록.
안전: 기본 드라이런(전송 안 함) · 라이브는 --live(모의계좌) · 실계좌는 --live --real + 확인문구 입력. 매 주문 사람 승인. 무인 없음.
      킬스위치 파일(진우_킬스위치.flag) 존재 시 전 주문 차단.
⚠️ 자동 체결 아님 · 실API는 진우 PC 전용 · 투자자문 아님·책임 본인.

사용:
  py jq_execute.py                       # 드라이런(오프라인·키 불필요): 파이프라인 전체 리허설
  py jq_execute.py --dry-run --yes       # 드라이런 자동승인(리허설만 — 실전송 없음)
  py jq_execute.py --live                # KIS 모의투자 계좌로 실제 주문(키 필요·주문별 승인)
  py jq_execute.py --live --real         # 실계좌(확인문구 입력 필수) — 로드맵 검증 통과 후에만
  옵션 전달: --capital --n --sizing equal|risk --risk-pct --conf --no-sell --include-bounce
  py jq_execute.py --self-test
"""
import os, sys, csv, argparse, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(BASE, "진우_모의매매장.csv")
EXECLOG = os.path.join(BASE, "진우_주문집행_로그.csv")   # 모든 실행(드라이런 포함) 감사 로그
KILLSWITCH = os.path.join(BASE, "진우_킬스위치.flag")
LEDGER_HEADER = ["날짜", "코드", "종목명", "구분", "가격", "수량", "메모"]
sys.path.insert(0, BASE)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass


# ────────────────────────── RiskGuard (차단기) ──────────────────────────
class RiskGuard:
    """전송 전 강제 검사. 하나라도 걸리면 그 주문 차단."""
    def __init__(self, capital, cash, price_band_pct=5.0, max_pos_pct=25.0, killswitch=KILLSWITCH):
        self.capital = float(capital)
        self.cash_left = float(cash) if cash is not None else 0.0
        self.band = price_band_pct / 100.0
        self.max_pos = max_pos_pct / 100.0
        self.killswitch = killswitch
        self.seen = set()

    def armed(self):
        """킬스위치 발동 여부(파일 존재)."""
        return os.path.exists(self.killswitch)

    def check(self, o, cur_price, held_qty):
        """반환 (ok, reason). ok면 상태(cash_left/seen) 갱신."""
        if self.armed():
            return False, "킬스위치 발동 — 전 주문 차단"
        if o.code in self.seen:
            return False, "당일 중복 주문 방지"
        # 가격 밴드(지정가 오타 방어)
        px = o.price if o.ordtype == "limit" else cur_price
        if o.ordtype == "limit" and cur_price and cur_price > 0:
            if abs(o.price - cur_price) / cur_price > self.band:
                return False, f"가격밴드 초과(현재가 {cur_price:,} 대비 ±{self.band*100:.0f}%)"
        if o.side == "sell":
            if held_qty is not None and held_qty > 0 and o.qty > held_qty:
                return False, f"보유수량 초과 매도({o.qty}>{held_qty})"
            self.seen.add(o.code)
            self.cash_left += o.qty * (px or 0)
            return True, ""
        # buy
        cost = o.qty * (px or cur_price or 0)
        if cost <= 0:
            return False, "가격 불명 — 매수 보류"
        if cost > self.capital * self.max_pos + 1e-6:
            return False, f"종목 비중 초과(자본 {self.max_pos*100:.0f}% 상한)"
        if cost > self.cash_left + 1e-6:
            return False, f"현금 부족(가용 {self.cash_left:,.0f} < 필요 {cost:,.0f})"
        self.seen.add(o.code)
        self.cash_left -= cost
        return True, ""


# ────────────────────────── 승인자 ──────────────────────────
class ConsoleApprover:
    """주문별 사람 승인(y/n). 자동 승인 없음."""
    def confirm(self, o, cur_price):
        tag = "매도" if o.side == "sell" else "매수"
        kind = "지정가" if o.ordtype == "limit" else "시장가"
        px = o.price if o.ordtype == "limit" else cur_price
        print(f"\n  ▶ {tag} {o.name or o.code}({o.code}) {o.qty:,}주 · {kind} {px:,} "
              f"(현재가 {cur_price:,}) · {o.reason}")
        ans = input("    승인? [y/N] ").strip().lower()
        return ans == "y"


class AutoApprover:
    """드라이런/테스트 전용 자동 응답. 라이브 실전송엔 쓰지 않는다."""
    def __init__(self, answer=True): self.answer = answer
    def confirm(self, o, cur_price): return self.answer


# ────────────────────────── 엔진 산출 → 주문 변환 ──────────────────────────
def orders_from_engine(g):
    """generate() 결과 → [OrderReq]. 매도(익절·백스톱) 먼저, 매수 나중."""
    from jq_broker_base import OrderReq
    out = []
    for s in g.get("sells", []):
        out.append(OrderReq(code=s["code"], side="sell", qty=int(s["shares"]),
                            price=int(s["price"]), ordtype="limit",
                            reason=s.get("reason", s.get("kind", "")), name=s.get("name", "")))
    for o in g.get("orders", []):
        px = int(o.get("buy") or o.get("price") or 0)
        out.append(OrderReq(code=o["code"], side="buy", qty=int(o["shares"]),
                            price=px, ordtype="limit",
                            reason=f"{o.get('kind','')} {o.get('note','')}".strip(), name=o.get("name", "")))
    return out


# ────────────────────────── 장부 기록 ──────────────────────────
def append_ledger(ledger, date, code, name, side_ko, price, qty, memo):
    exists = os.path.exists(ledger)
    with open(ledger, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        if not exists:
            w.writerow(LEDGER_HEADER)
        w.writerow([date, code, name, side_ko, int(price), int(qty), memo])


# ────────────────────────── 러너 ──────────────────────────
def run_orders(orders, broker, guard, approver, ledger=LEDGER, dry=True, today=None, log=None):
    """주문 리스트를 차단기→승인→전송→기록. 반환 요약 dict.
    기록 규칙: log(감사)는 항상 · 실제 장부(ledger=진우_모의매매장.csv)는 라이브(not dry)만.
    ★ 드라이런은 실제 장부를 절대 건드리지 않는다(리허설이 보유현황을 오염시키면 안 됨)."""
    today = today or datetime.date.today().isoformat()
    broker.auth()
    positions = {}
    try: positions = broker.positions()
    except Exception: positions = {}
    sent, blocked, rejected = [], [], []
    for o in orders:
        try: cur = broker.price(o.code)
        except Exception: cur = o.price
        held = positions.get(o.code, {}).get("qty", 0)
        ok, reason = guard.check(o, cur, held)
        if not ok:
            blocked.append((o, reason)); print(f"  ⛔ 차단 {o.name or o.code}: {reason}"); continue
        if not approver.confirm(o, cur):
            rejected.append(o); print(f"  ✗ 사람 거부 {o.name or o.code}"); continue
        ack = broker.send(o)
        if ack.ok:
            price = o.price if o.ordtype == "limit" else cur
            side_ko = "매도" if o.side == "sell" else "매수"
            memo = f"{'[모의]' if broker.paper else '[실전]'}{'[DRY]' if dry else ''} {o.reason} {ack.order_no}".strip()
            if log:
                append_ledger(log, today, o.code, o.name, side_ko, price, o.qty, memo)   # 감사 로그(항상)
            if not dry:
                append_ledger(ledger, today, o.code, o.name, side_ko, price, o.qty, memo)  # 실제 장부(라이브만)
            sent.append((o, ack)); print(f"  ✓ 전송 {side_ko} {o.name or o.code} {o.qty:,}주 · 주문번호 {ack.order_no}")
        else:
            blocked.append((o, ack.msg)); print(f"  ⚠️ 실패 {o.name or o.code}: {ack.msg}")
    print(f"\n  요약: 전송 {len(sent)} · 차단 {len(blocked)} · 거부 {len(rejected)}"
          f" · 잔여현금 {guard.cash_left:,.0f}{' (DRY-RUN·실전송 없음)' if dry else ''}")
    return dict(sent=sent, blocked=blocked, rejected=rejected, cash_left=guard.cash_left)


def build_broker(dry, live, real, capital, orders=None):
    """드라이런=오프라인 DryRunBroker(키 불필요) · --live=KIS 모의 · --live --real=실계좌."""
    from jq_broker_base import DryRunBroker
    if not live or dry:
        # 오프라인 리허설: 주문가로 시세 시드, 매도분 보유 시드
        seed_price, seed_pos = {}, {}
        for o in (orders or []):
            seed_price[o.code] = o.price or 0
            if o.side == "sell": seed_pos[o.code] = dict(qty=o.qty, avg=o.price)
        return DryRunBroker(paper=not real, seed_cash=capital, seed_pos=seed_pos, seed_price=seed_price)
    from jq_broker_kis import KISBroker
    if real:
        phrase = input("  ⚠️ 실계좌 주문입니다. 진행하려면 '실계좌 확인' 입력: ").strip()
        if phrase != "실계좌 확인":
            print("  중단 — 확인문구 불일치."); sys.exit(2)
        return KISBroker(paper=False, allow_real=True)
    return KISBroker(paper=True)


# ────────────────────────── self-test ──────────────────────────
def _self_test():
    from jq_broker_base import OrderReq, DryRunBroker
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")

    # ── RiskGuard ──
    g = RiskGuard(capital=10_000_000, cash=5_000_000, price_band_pct=5, max_pos_pct=25,
                  killswitch="/nonexistent.flag")
    buy = OrderReq(code="005930", side="buy", qty=10, price=70000)  # 70만 < 250만·현금ok
    okc, _ = g.check(buy, 70000, 0)
    chk("정상 매수 통과·현금차감", okc and abs(g.cash_left - 4_300_000) < 1)
    okd, rd = g.check(buy, 70000, 0)
    chk("중복 주문 차단", (not okd) and "중복" in rd)

    g2 = RiskGuard(10_000_000, 5_000_000, 5, 25, "/nonexistent.flag")
    band = OrderReq(code="000660", side="buy", qty=1, price=100000)
    okb, rb = g2.check(band, 80000, 0)  # 지정가10만 vs 현재가8만 → +25% 밴드초과
    chk("가격밴드 초과 차단", (not okb) and "밴드" in rb)

    g3 = RiskGuard(10_000_000, 5_000_000, 5, 25, "/nonexistent.flag")
    big = OrderReq(code="000660", side="buy", qty=100, price=30000)  # 300만 > 자본25%(250만)
    okp, rp = g3.check(big, 30000, 0)
    chk("종목 비중(25%) 초과 차단", (not okp) and "비중" in rp)

    g4 = RiskGuard(100_000_000, 1_000_000, 5, 90, "/nonexistent.flag")
    cashy = OrderReq(code="000660", side="buy", qty=100, price=30000)  # 300만 > 현금100만
    okh, rh = g4.check(cashy, 30000, 0)
    chk("현금 부족 차단", (not okh) and "현금" in rh)

    g5 = RiskGuard(10_000_000, 5_000_000, 5, 25, "/nonexistent.flag")
    over = OrderReq(code="005930", side="sell", qty=20, price=70000)
    oko, ro = g5.check(over, 70000, 10)  # 보유10<매도20
    chk("보유수량 초과 매도 차단", (not oko) and "초과" in ro)
    oks, _ = g5.check(OrderReq(code="000660", side="sell", qty=5, price=50000), 50000, 10)
    chk("정상 매도 통과·현금증가", oks and g5.cash_left > 5_000_000)

    # 킬스위치
    import tempfile
    kf = os.path.join(tempfile.gettempdir(), "jq_kill_test.flag")
    open(kf, "w").write("x")
    gk = RiskGuard(10_000_000, 5_000_000, killswitch=kf)
    okk, rk = gk.check(buy, 70000, 0)
    chk("킬스위치 발동 → 차단", (not okk) and "킬스위치" in rk)
    os.remove(kf)

    # ── 엔진 산출 → 주문 변환 ──
    gdict = dict(sells=[dict(code="247540", name="에코프로비엠", shares=5, price=200000,
                            kind="익절매도", reason="익절검토")],
                 orders=[dict(code="005930", name="삼성전자", shares=10, buy=70000, price=70000,
                             kind="딥밸류바닥", note="")])
    orders = orders_from_engine(gdict)
    chk("매도가 매수보다 먼저", orders[0].side == "sell" and orders[1].side == "buy")
    chk("매도 종목/수량 변환", orders[0].code == "247540" and orders[0].qty == 5)

    # ── run_orders 드라이런: 실제 장부 미기록·감사로그만 ──
    tmp_ledger = os.path.join(tempfile.gettempdir(), "jq_ledger_test.csv")
    tmp_log = os.path.join(tempfile.gettempdir(), "jq_execlog_test.csv")
    for p in (tmp_ledger, tmp_log):
        if os.path.exists(p): os.remove(p)
    br = build_broker(dry=True, live=False, real=False, capital=10_000_000, orders=orders)
    guard = RiskGuard(10_000_000, br.cash(), killswitch="/nonexistent.flag")
    res = run_orders(orders, br, guard, AutoApprover(True), ledger=tmp_ledger, dry=True,
                     today="2026-07-22", log=tmp_log)
    chk("드라이런 전송(시뮬) 2건", len(res["sent"]) == 2)
    chk("실전송 안 됨(DryRunBroker.sent)", len(br.sent) == 2)
    chk("★드라이런은 실제 장부 미기록", not os.path.exists(tmp_ledger))
    with open(tmp_log, encoding="utf-8-sig") as f:
        rows = list(csv.reader(f))
    chk("감사 로그 헤더+2행 기록", len(rows) == 3 and rows[0] == LEDGER_HEADER)
    chk("로그 매도행 [DRY] 메모", "DRY" in rows[1][6] and rows[1][3] == "매도")
    os.remove(tmp_log)

    # ── 라이브(not dry)는 실제 장부에 기록 ──
    tmp_ledger2 = os.path.join(tempfile.gettempdir(), "jq_ledger_live.csv")
    if os.path.exists(tmp_ledger2): os.remove(tmp_ledger2)
    brl = build_broker(dry=False, live=False, real=False, capital=10_000_000, orders=orders)
    resl = run_orders(orders, brl, RiskGuard(10_000_000, brl.cash(), killswitch="/nonexistent.flag"),
                      AutoApprover(True), ledger=tmp_ledger2, dry=False, today="2026-07-22", log=None)
    chk("라이브 모드는 실제 장부 기록", os.path.exists(tmp_ledger2) and len(resl["sent"]) == 2)
    os.remove(tmp_ledger2)

    # 거부 경로
    tmp2 = os.path.join(tempfile.gettempdir(), "jq_ledger_test2.csv")
    if os.path.exists(tmp2): os.remove(tmp2)
    br2 = build_broker(dry=True, live=False, real=False, capital=10_000_000, orders=orders)
    res2 = run_orders(orders, br2, RiskGuard(10_000_000, br2.cash(), killswitch="/nonexistent.flag"),
                      AutoApprover(False), ledger=tmp2, dry=True)
    chk("사람 거부 시 전송 0·장부 미생성", len(res2["sent"]) == 0 and not os.path.exists(tmp2))

    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot


# ────────────────────────── main ──────────────────────────
def main():
    ap = argparse.ArgumentParser(description="주문 집행 러너 (반자동)")
    ap.add_argument("--live", action="store_true", help="실제 전송(KIS 모의계좌). 없으면 드라이런.")
    ap.add_argument("--real", action="store_true", help="실계좌(확인문구 필요). --live와 함께.")
    ap.add_argument("--dry-run", action="store_true", help="강제 드라이런(전송 안 함).")
    ap.add_argument("--yes", action="store_true", help="드라이런 자동승인(리허설 전용).")
    # 엔진 옵션 패스스루
    ap.add_argument("--capital", type=float, default=10000000)
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--sizing", choices=["equal", "risk"], default="equal")
    ap.add_argument("--risk-pct", type=float, default=1.0)
    ap.add_argument("--conf", action="store_true")
    ap.add_argument("--no-sell", action="store_true")
    ap.add_argument("--include-bounce", action="store_true")
    ap.add_argument("--no-caps", action="store_true")
    ap.add_argument("--price-band", type=float, default=5.0, help="지정가 허용 밴드%%(기본5)")
    ap.add_argument("--max-pos", type=float, default=25.0, help="종목당 자본 비중 상한%%(기본25)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return 0 if _self_test() else 1

    dry = a.dry_run or not a.live
    if a.yes and not dry:
        print("  --yes는 드라이런에서만 허용됩니다(라이브는 주문별 사람 승인)."); return 2

    import 진우_주문생성 as eng
    g = eng.generate(a.capital, a.n, a.include_bounce, a.sizing, a.risk_pct, a.conf,
                     2, 1, not a.no_caps, not a.no_sell)
    orders = orders_from_engine(g)
    print("=" * 84)
    print(f"주문 집행 러너 — {'드라이런(전송 없음)' if dry else ('실계좌' if a.real else 'KIS 모의계좌')} "
          f"· 매도 {len(g['sells'])} · 매수 {len(g['orders'])}")
    print("=" * 84)
    if not orders:
        print("  주문 없음 — 오늘은 집행할 것이 없습니다."); return 0

    broker = build_broker(dry, a.live, a.real, a.capital, orders)
    guard = RiskGuard(a.capital, None, a.price_band, a.max_pos)
    # cash는 broker에서
    broker.auth(); guard.cash_left = float(broker.cash())
    approver = AutoApprover(True) if (dry and a.yes) else ConsoleApprover()
    run_orders(orders, broker, guard, approver, ledger=LEDGER, dry=dry, log=EXECLOG)
    if dry:
        print("\n  ※ 드라이런입니다. 실제 장부(진우_모의매매장.csv)는 건드리지 않았습니다.")
        print("     기록은 진우_주문집행_로그.csv(감사용)에만 남습니다.")
        print("     실제 주문하려면 --live(모의계좌), 검증 후 --live --real(실계좌).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
