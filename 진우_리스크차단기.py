#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우_리스크차단기.py — RiskGuard (주문 집행 전 강제 검사 · 반자동 안전핀 #5)

주문안(진우_주문생성.py 산출) → [RiskGuard] → 사람 승인 → API 집행.
이 모듈은 **집행 직전 마지막 방어선**이다. 사람 승인(approver)조차 실수할 수 있으니,
기계가 먼저 명백한 사고(오타 단가·현금 초과·과집중·당일 중복·손실 폭주)를 막는다.
증권사 API 없이도 동작·검증되는 순수 판정 계층 — 로드맵 §3-4에서 브로커 어댑터에 이 게이트를 끼운다.

검사 순서(하나라도 걸리면 그 주문 차단, 사유 반환):
  1. 킬스위치      — 한 번 내려가면(일일손실한도 도달·수동) 이후 주문 전면 차단.
  2. 일일손실한도   — 당일 실현손실이 자본×한도% 도달 시 킬스위치를 내린다.
  3. 당일 중복      — 같은 종목 당일 재주문 방지(연타·중복승인 사고).
  4. 가격 밴드      — 주문단가가 기준가(현재가) ±X% 벗어나면 차단(0 하나 더 친 오타 방어). 시장가(0)는 면제.
  5. 현금           — 매수 금액이 주문가능현금 초과 시 차단.
  6. 종목 비중      — (기존보유평가액+신규금액)/자본 이 종목당 최대비중 초과 시 차단.
  7. 최대 포지션    — 신규 종목 진입이 최대 보유종목수 초과 시 차단.

⚠️ 이건 '차단'만 한다 — 자동 '집행'은 하지 않는다. 통과해도 사람 승인이 남는다. 투자자문 아님·책임 본인.

사용:
  py 진우_리스크차단기.py --self-test              # 순수 판정 전수 검증
  py 진우_리스크차단기.py                            # 오늘 주문안에 드라이런(전송 없음, API 없음)
  py 진우_리스크차단기.py --band 8 --max-weight 15 --max-pos 15 --daily-loss 3
"""
import os, sys, csv, json, argparse, importlib.util
from dataclasses import dataclass, asdict, field

BASE = os.path.dirname(os.path.abspath(__file__))
GEN_PATH = os.path.join(BASE, "진우_주문생성.py")
SIM_PATH = os.path.join(BASE, "진우_모의매매.py")
CFG_PATH = os.path.join(BASE, "진우_리스크한도.json")   # 있으면 로드, 없으면 기본값
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

# ────────────────────────── 모듈 재사용 (단일 진실원천) ──────────────────────────
_MODCACHE = {}
def _load_module(path, name):
    if name in _MODCACHE: return _MODCACHE[name]
    spec = importlib.util.spec_from_file_location(name, path)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    _MODCACHE[name] = m
    return m

# ────────────────────────── 설정(한도) ──────────────────────────
@dataclass
class Limits:
    price_band_pct: float = 10.0      # 주문단가 vs 기준가 허용 편차(±%). 오타 방어.
    max_weight_pct: float = 20.0      # 종목당 최대 비중(자본 대비 %).
    max_positions: int = 15           # 최대 동시 보유 종목수.
    daily_loss_limit_pct: float = 3.0 # 당일 실현손실 한도(자본 대비 %). 도달 시 킬스위치.
    per_name_daily_once: bool = True  # 같은 종목 당일 1회만.
    killswitch: bool = False          # 수동 킬스위치(True면 전면 차단).

    @staticmethod
    def load(path=CFG_PATH):
        base = Limits()
        # ① SSOT 배선(2026-07-28): 진우_통합한도.json의 집행_riskguard 섹션을 우선 적용
        unified = os.path.join(BASE, "진우_통합한도.json")
        if os.path.exists(unified):
            try:
                with open(unified, encoding="utf-8") as f:
                    rg = json.load(f).get("집행_riskguard", {})
                if "price_band_pct" in rg: base.price_band_pct = float(rg["price_band_pct"])
                if "max_weight_pct" in rg: base.max_weight_pct = float(rg["max_weight_pct"])
                if "max_positions" in rg: base.max_positions = int(rg["max_positions"])
                if "daily_loss_kill_pct" in rg: base.daily_loss_limit_pct = abs(float(rg["daily_loss_kill_pct"]))
                if "당일_동일종목_최대주문" in rg: base.per_name_daily_once = int(rg["당일_동일종목_최대주문"]) <= 1
            except Exception:
                pass
        # ② 구 파일(진우_리스크한도.json)은 수동 오버라이드로만 유지 — 있으면 개별 항목 덮어씀
        if os.path.exists(path):
            try:
                with open(path, encoding="utf-8") as f:
                    d = json.load(f)
                for k, v in d.items():
                    if hasattr(base, k): setattr(base, k, v)
            except Exception:
                pass
        return base

    def save(self, path=CFG_PATH):
        with open(path, "w", encoding="utf-8") as f:
            json.dump(asdict(self), f, ensure_ascii=False, indent=2)

# ────────────────────────── 주문·컨텍스트 ──────────────────────────
@dataclass
class OrderReq:
    """증권사 비종속 주문안. 진우_증권사API_설계.md §3의 OrderReq와 동일 골격."""
    code: str
    side: str          # "buy" | "sell"
    qty: int
    price: int         # 지정가. 0이면 시장가.
    name: str = ""

@dataclass
class MarketCtx:
    """집행 시점 계좌·시세 스냅샷. 실집행 땐 broker에서 채우고, 검증/드라이런 땐 장부·엔진에서 채운다."""
    cash: int
    equity: int                              # 총자산(현금+평가액). 비중·손실한도 분모.
    positions: dict = field(default_factory=dict)   # {code:{qty,avg}}
    market_price: dict = field(default_factory=dict) # {code: 기준가(현재가)} — 밴드 검사용
    realized_today: int = 0                  # 당일 실현손익(음수=손실)
    ordered_today: set = field(default_factory=set)  # 오늘 이미 주문 넣은 종목코드

# ────────────────────────── 순수 판정 함수(self-test 대상) ──────────────────────────
def chk_killswitch(tripped):
    return (False, "킬스위치 ON — 전면 차단") if tripped else (True, "")

def chk_daily_loss(realized_today, equity, limit_pct):
    """당일 실현손실이 자본×limit% 도달? (도달 시 차단 + 킬스위치 트리거 신호)"""
    if equity <= 0 or limit_pct <= 0: return True, ""
    floor = -abs(equity) * (limit_pct / 100.0)
    if realized_today <= floor:
        return False, f"일일손실한도 도달({realized_today:,.0f} ≤ {floor:,.0f}) — 킬스위치"
    return True, ""

def chk_duplicate(code, ordered_today, per_name_once):
    if per_name_once and code in ordered_today:
        return False, "당일 이미 주문한 종목(중복 차단)"
    return True, ""

def chk_price_band(price, ref_price, band_pct):
    """주문단가가 기준가 ±band% 벗어나면 차단. price=0(시장가) 또는 기준가 없음 → 면제."""
    if price <= 0 or not ref_price or ref_price <= 0: return True, ""
    dev = abs(price - ref_price) / ref_price * 100.0
    if dev > band_pct:
        return False, f"가격밴드 초과(단가 {price:,} vs 기준 {ref_price:,} · {dev:.1f}% > {band_pct:.0f}%)"
    return True, ""

def chk_cash(side, cost, cash):
    if side == "buy" and cost > cash:
        return False, f"현금 초과(필요 {cost:,.0f} > 보유 {cash:,.0f})"
    return True, ""

def chk_weight(side, add_cost, held_value, equity, max_weight_pct):
    """매수 후 이 종목 평가비중이 최대치 초과? held_value=기존 보유 평가액."""
    if side != "buy" or equity <= 0 or max_weight_pct <= 0: return True, ""
    w = (held_value + add_cost) / equity * 100.0
    if w > max_weight_pct:
        return False, f"종목비중 초과(예상 {w:.1f}% > 최대 {max_weight_pct:.0f}%)"
    return True, ""

def chk_max_positions(side, code, positions, max_positions):
    """신규 종목 진입이 최대 보유종목수 초과? (이미 보유 중이면 증액이므로 통과)"""
    if side != "buy" or max_positions <= 0: return True, ""
    held = {c for c, p in positions.items() if p.get("qty", 0) > 0}
    if code not in held and len(held) >= max_positions:
        return False, f"최대포지션 초과(보유 {len(held)}종 ≥ {max_positions})"
    return True, ""

# ────────────────────────── RiskGuard (상태 있는 게이트) ──────────────────────────
@dataclass
class Verdict:
    ok: bool
    reason: str = ""

class RiskGuard:
    """집행 직전 게이트. 한 배치(오늘 주문들)를 순서대로 흘리며 검사한다.
    상태: 킬스위치(한 번 내려가면 유지), 배치 내 누적 매수금·신규종목·주문한 종목."""
    def __init__(self, limits: Limits):
        self.lim = limits
        self.tripped = bool(limits.killswitch)   # 수동 킬스위치 반영
        self._ordered = set()                    # 이 배치에서 승인/통과된 종목(중복·비중 누적)
        self._spent = 0                          # 이 배치 누적 매수금(현금 소진 반영)
        self._newpos = set()                     # 이 배치 신규 진입 종목(최대포지션 누적)

    def check(self, o: OrderReq, ctx: MarketCtx) -> Verdict:
        # 1. 킬스위치
        ok, why = chk_killswitch(self.tripped)
        if not ok: return Verdict(False, why)
        # 2. 일일손실한도 → 도달 시 킬스위치 내리고 이 주문부터 차단
        ok, why = chk_daily_loss(ctx.realized_today, ctx.equity, self.lim.daily_loss_limit_pct)
        if not ok:
            self.tripped = True
            return Verdict(False, why)
        # 3. 당일 중복 (장부상 오늘 주문 + 이 배치서 이미 통과한 것)
        seen = set(ctx.ordered_today) | self._ordered
        ok, why = chk_duplicate(o.code, seen, self.lim.per_name_daily_once)
        if not ok: return Verdict(False, why)
        # 4. 가격 밴드
        ok, why = chk_price_band(o.price, ctx.market_price.get(o.code), self.lim.price_band_pct)
        if not ok: return Verdict(False, why)
        # 5. 현금 (배치 내 이미 통과한 매수금 차감 반영)
        cost = o.price * o.qty
        ok, why = chk_cash(o.side, cost, ctx.cash - self._spent)
        if not ok: return Verdict(False, why)
        # 6. 종목 비중 (기존 보유 평가액 + 신규 매수금)
        pos = ctx.positions.get(o.code, {})
        ref = ctx.market_price.get(o.code) or o.price
        held_value = pos.get("qty", 0) * (ref or 0)
        ok, why = chk_weight(o.side, cost, held_value, ctx.equity, self.lim.max_weight_pct)
        if not ok: return Verdict(False, why)
        # 7. 최대 포지션 (기존 보유 + 이 배치 신규 진입)
        merged = dict(ctx.positions)
        for c in self._newpos: merged.setdefault(c, {"qty": 1})
        ok, why = chk_max_positions(o.side, o.code, merged, self.lim.max_positions)
        if not ok: return Verdict(False, why)
        # 통과 → 배치 상태 갱신
        if o.side == "buy":
            self._spent += cost
            if o.code not in ctx.positions: self._newpos.add(o.code)
        self._ordered.add(o.code)
        return Verdict(True, "")

# ────────────────────────── 엔진 산출 → OrderReq 어댑터 ──────────────────────────
def orders_from_engine(g):
    """진우_주문생성.generate() 산출(dict)을 OrderReq 리스트로. 매도 먼저, 매수 나중(설계 §2)."""
    out = []
    for s in g.get("sells", []):
        out.append(OrderReq(code=s["code"], side="sell", qty=int(s["shares"]),
                            price=int(s["price"]), name=s.get("name", "")))
    for o in g.get("orders", []):
        out.append(OrderReq(code=o["code"], side="buy", qty=int(o["shares"]),
                            price=int(o["buy"]), name=o.get("name", "")))
    return out

def ctx_from_engine(g):
    """드라이런용 컨텍스트. 실집행 땐 broker 스냅샷으로 대체.
    기준가는 매수단가 자기자신을 써서 밴드는 자명통과(독립 현재가는 집행 시점 broker.price가 채움)."""
    cash = int(g.get("cash", 0)); seed = int(g.get("seed", g.get("capital", 0)))
    positions, mp = {}, {}
    # 보유 평가·현재가는 엔진이 매도판단용으로 계산한 값이 있으면 그걸, 없으면 생략
    return MarketCtx(cash=cash, equity=seed, positions=positions, market_price=mp,
                     realized_today=0, ordered_today=set())

# ────────────────────────── 드라이런(전송 없음) ──────────────────────────
def dry_run(limits):
    G = _load_module(GEN_PATH, "jinwoo_gen")
    g = G.generate(capital=10_000_000, n=12, include_bounce=True, sizing="risk",
                   risk_pct=1.0, use_conf=False, sector_cap=2, group_cap=1,
                   apply_caps=True, do_sell=True)
    orders = orders_from_engine(g)
    ctx = ctx_from_engine(g)
    guard = RiskGuard(limits)
    print("\n" + "=" * 78)
    print("RiskGuard 드라이런 — 전송 없음(API 미연결) · 통과=사람 승인 대기, 차단=집행 불가")
    print("=" * 78)
    print(f"  한도: 밴드±{limits.price_band_pct:.0f}% · 종목비중≤{limits.max_weight_pct:.0f}% · "
          f"최대{limits.max_positions}종 · 일일손실{limits.daily_loss_limit_pct:.0f}% · "
          f"당일1회={limits.per_name_daily_once} · 킬스위치={limits.killswitch}")
    print(f"  현금 {ctx.cash:,} · 자본 {ctx.equity:,} · 주문안 {len(orders)}건\n")
    if not orders:
        print("  (오늘 주문안 없음 — 후보/보유 상황상 정상. --include-bounce로 매수후보 포함됨)")
    npass = 0
    for o in orders:
        v = guard.check(o, ctx)
        mark = "통과✔ 승인대기" if v.ok else "차단✖"
        npass += 1 if v.ok else 0
        detail = f" · {v.reason}" if v.reason else ""
        print(f"  [{mark}] {o.side:<4} {o.name[:12]:<12} {o.qty:>5}주 @ {o.price:>8,}{detail}")
    print(f"\n  → {npass}/{len(orders)} 통과(사람 승인 대기). 차단은 사유 확인 후 수동 판단.")
    print("※ 통과해도 자동집행 아님. 승인러너·브로커 어댑터는 §3-4(PC)에서 결합. 투자자문 아님·책임 본인.")

# ────────────────────────── self-test ──────────────────────────
def _self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")

    # 가격 밴드
    chk("밴드: 단가=기준가 통과", chk_price_band(50000, 50000, 10)[0])
    chk("밴드: +9% 통과(≤10)", chk_price_band(54500, 50000, 10)[0])
    chk("밴드: +20% 차단", not chk_price_band(60000, 50000, 10)[0])
    chk("밴드: 0 하나 더 친 오타(50만) 차단", not chk_price_band(500000, 50000, 10)[0])
    chk("밴드: 시장가(price=0) 면제", chk_price_band(0, 50000, 10)[0])
    chk("밴드: 기준가 없음 면제", chk_price_band(50000, None, 10)[0])

    # 현금
    chk("현금: 매수 금액 초과 차단", not chk_cash("buy", 1_200_000, 1_000_000)[0])
    chk("현금: 매수 여유 통과", chk_cash("buy", 800_000, 1_000_000)[0])
    chk("현금: 매도는 현금검사 면제", chk_cash("sell", 9_999_999, 0)[0])

    # 비중
    chk("비중: 신규 25% > 20 차단", not chk_weight("buy", 2_500_000, 0, 10_000_000, 20)[0])
    chk("비중: 신규 15% 통과", chk_weight("buy", 1_500_000, 0, 10_000_000, 20)[0])
    chk("비중: 기존15%+증액10%=25% 차단", not chk_weight("buy", 1_000_000, 1_500_000, 10_000_000, 20)[0])
    chk("비중: 매도 면제", chk_weight("sell", 9_999_999, 0, 10_000_000, 20)[0])

    # 최대 포지션
    pos15 = {f"{i:06d}": {"qty": 10} for i in range(15)}
    chk("최대포지션: 15종 보유+신규 차단", not chk_max_positions("buy", "999999", pos15, 15)[0])
    chk("최대포지션: 기존종목 증액은 통과", chk_max_positions("buy", "000000", pos15, 15)[0])
    pos14 = {f"{i:06d}": {"qty": 10} for i in range(14)}
    chk("최대포지션: 14종+신규 통과", chk_max_positions("buy", "999999", pos14, 15)[0])
    chk("최대포지션: 매도 면제", chk_max_positions("sell", "999999", pos15, 15)[0])

    # 중복
    chk("중복: 당일 재주문 차단", not chk_duplicate("005930", {"005930"}, True)[0])
    chk("중복: 새 종목 통과", chk_duplicate("000660", {"005930"}, True)[0])
    chk("중복: per_name_once=False면 허용", chk_duplicate("005930", {"005930"}, False)[0])

    # 일일 손실 한도
    chk("손실한도: -3.5% ≤ -3% 차단", not chk_daily_loss(-350_000, 10_000_000, 3)[0])
    chk("손실한도: -2% 통과", chk_daily_loss(-200_000, 10_000_000, 3)[0])
    chk("손실한도: 이익 통과", chk_daily_loss(+500_000, 10_000_000, 3)[0])

    # 킬스위치
    chk("킬스위치 ON → 차단", not chk_killswitch(True)[0])
    chk("킬스위치 OFF → 통과", chk_killswitch(False)[0])

    # ── RiskGuard 통합(상태·순서) ──
    lim = Limits(price_band_pct=10, max_weight_pct=20, max_positions=15,
                 daily_loss_limit_pct=3, per_name_daily_once=True)
    ctx = MarketCtx(cash=1_000_000, equity=10_000_000,
                    positions={}, market_price={"005930": 70000, "000660": 200000},
                    realized_today=0, ordered_today=set())
    g = RiskGuard(lim)
    v1 = g.check(OrderReq("005930", "buy", 10, 70000, "삼성"), ctx)   # 70만, 밴드ok, 현금ok, 비중7%
    chk("통합: 정상 매수 통과", v1.ok)
    v2 = g.check(OrderReq("005930", "buy", 1, 70000, "삼성"), ctx)    # 같은 종목 재주문
    chk("통합: 배치 내 같은종목 재주문 차단", (not v2.ok) and "중복" in v2.reason)
    v3 = g.check(OrderReq("000660", "buy", 10, 200000, "하이닉스"), ctx)  # 200만 > 남은현금30만
    chk("통합: 배치 현금소진 반영 차단", (not v3.ok) and "현금" in v3.reason)

    # 배치 현금소진: 첫 매수가 현금 대부분 소진 → 둘째 차단
    ctx2 = MarketCtx(cash=1_000_000, equity=10_000_000, positions={},
                     market_price={"A": 500000, "B": 500000}, realized_today=0, ordered_today=set())
    g2 = RiskGuard(lim)
    a = g2.check(OrderReq("A", "buy", 1, 500000, "A"), ctx2)   # 50만 통과
    b = g2.check(OrderReq("B", "buy", 2, 500000, "B"), ctx2)   # 100만 > 남은50만 차단
    chk("통합: 첫건 통과 후 둘째 현금부족 차단", a.ok and (not b.ok) and "현금" in b.reason)

    # 손실한도 도달 → 킬스위치 → 이후 전면 차단
    ctxL = MarketCtx(cash=10_000_000, equity=10_000_000, positions={},
                     market_price={"X": 1000, "Y": 1000}, realized_today=-400_000, ordered_today=set())
    gL = RiskGuard(lim)
    x = gL.check(OrderReq("X", "buy", 1, 1000, "X"), ctxL)
    y = gL.check(OrderReq("Y", "buy", 1, 1000, "Y"), ctxL)
    chk("통합: 손실한도 도달 시 첫 주문 차단", (not x.ok) and "손실" in x.reason)
    chk("통합: 킬스위치 내려가 다음도 전면차단", (not y.ok) and "킬스위치" in y.reason)

    # 어댑터
    fake = {"sells": [{"code": "111111", "name": "매도A", "shares": 3, "price": 2100}],
            "orders": [{"code": "222222", "name": "매수B", "shares": 5, "buy": 50000}]}
    reqs = orders_from_engine(fake)
    chk("어댑터: 매도 먼저·매수 나중", reqs[0].side == "sell" and reqs[1].side == "buy")
    chk("어댑터: 필드 매핑(qty/price)", reqs[1].qty == 5 and reqs[1].price == 50000)

    # 설정 저장/로드 왕복
    tmp = os.path.join(BASE, "_rg_test_cfg.json")
    try:
        Limits(price_band_pct=7, max_positions=13).save(tmp)
        L2 = Limits.load(tmp)
        chk("설정: JSON 저장→로드 왕복", L2.price_band_pct == 7 and L2.max_positions == 13)
    finally:
        if os.path.exists(tmp): os.remove(tmp)

    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot

# ────────────────────────── main ──────────────────────────
def main():
    ap = argparse.ArgumentParser(description="진우 RiskGuard — 집행 전 강제 검사(반자동 안전핀)")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--band", type=float, help="가격밴드 ±%% (기본 10)")
    ap.add_argument("--max-weight", type=float, help="종목당 최대비중 %% (기본 20)")
    ap.add_argument("--max-pos", type=int, help="최대 보유종목수 (기본 15)")
    ap.add_argument("--daily-loss", type=float, help="일일 손실 한도 %% (기본 3)")
    ap.add_argument("--killswitch", action="store_true", help="수동 킬스위치 ON(전면 차단)")
    ap.add_argument("--save-config", action="store_true", help="현재 한도를 진우_리스크한도.json에 저장")
    a = ap.parse_args()
    if a.self_test:
        return 0 if _self_test() else 1
    lim = Limits.load()
    if a.band is not None: lim.price_band_pct = a.band
    if a.max_weight is not None: lim.max_weight_pct = a.max_weight
    if a.max_pos is not None: lim.max_positions = a.max_pos
    if a.daily_loss is not None: lim.daily_loss_limit_pct = a.daily_loss
    if a.killswitch: lim.killswitch = True
    if a.save_config:
        lim.save(); print(f"저장: 진우_리스크한도.json")
    dry_run(lim)
    return 0

if __name__ == "__main__":
    sys.exit(main())
