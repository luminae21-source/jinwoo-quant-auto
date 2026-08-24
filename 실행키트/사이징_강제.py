#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""사이징_강제.py — 포지션 사이징·포트폴리오 heat·킬스위치 강제 (개선안 ⑦)

"전부 이미 설계됐다 — 향상 = 지키는 것." 재량 테마(위성)에서 행동 리스크가 가장 크므로,
사람 판단 전에 기계가 사이징·집중·연속손실을 강제한다.
근거: 진우퀀트_손절사이징_룰_파라미터 · 매매기법_보강(heat 6%룰·연속손실 스로틀).

  · risk룰 + ATR: 수량 = (자본×risk%) / (k·ATR)
  · 주문 캡: 금액 ≤ ADTV×1%                            (시장충격 억제)
  · 포트폴리오 heat ≤ 6%: 미실현 리스크 합(진입−현손절)/자본
  · 동시 보유 ≤ 5 · 동일테마 ≤ 2종 & ≤ lane 40% · 1종목 ≤ lane 25%
  · 킬스위치: lane 일 −7% / 주 −12% / 월 −15% → 신규진입 정지
  · 연속손실 스로틀: 3연속 → 사이즈 ½ · 5연속 → 당주 중단

── 2026-07-28 SSOT 배선 ────────────────────────────────────────────
파라미터를 진우_통합한도.json(재량_사이징 · 킬스위치_메타룰)에서 읽는다(단일 진실원천).
파일이 없으면 종전 하드코딩과 동일한 dataclass 기본값으로 동작(하위호환).
주요 변경: 기본 risk 2%→JSON 1% · 월 킬 −20%→JSON −15%(손절사이징 룰 사전등록 값).

이 모듈은 '전략 단계' 강제(진입 규모/집중). 집행 직전 강제는 진우_리스크차단기.RiskGuard(별개).
RiskGuard와 함께 쓰면: [사이징_강제] 규모 결정 → 주문안 → [RiskGuard] 집행 전 방어 → 승인.

사용: from 사이징_강제 import size_by_atr, portfolio_heat, killswitch_check, loss_throttle, RULE
      py 사이징_강제.py --self-test    ·    py 사이징_강제.py --show (현재 적용값 확인)
⚠️ 매수/매도 신호 아님. 투자자문 아님·책임 본인.
"""
import sys, os, json, argparse, math
from dataclasses import dataclass, field, asdict

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass


def _find_limits_json():
    here = os.path.dirname(os.path.abspath(__file__))
    for d in (here, os.path.dirname(here)):
        p = os.path.join(d, "진우_통합한도.json")
        if os.path.exists(p): return p
    return None


@dataclass
class SizingRule:
    risk_pct: float = 0.02        # 트레이드당 리스크(자본 대비) — JSON 있으면 0.01로 덮임
    k_atr: float = 2.5            # 손절폭 ATR 배수
    adtv_cap: float = 0.01        # 주문금액 ≤ ADTV×1%
    heat_cap: float = 0.06        # 포트폴리오 총 heat 상한
    max_positions: int = 5        # 동시 보유
    same_theme_max: int = 2       # 동일 테마 종목수
    same_theme_lane_cap: float = 0.40  # 동일 테마 ≤ lane 40%
    one_name_lane_cap: float = 0.25    # 1종목 ≤ lane 25%
    lane_daily_kill: float = -0.07
    lane_weekly_kill: float = -0.12
    lane_monthly_kill: float = -0.20   # JSON 있으면 -0.15로 덮임(사전등록 값)
    throttle_half_at: int = 3     # 연속손실 3 → ½
    throttle_stop_at: int = 5     # 연속손실 5 → 중단

    @classmethod
    def load(cls):
        """진우_통합한도.json(SSOT) → SizingRule. 파일 없으면 기본값."""
        r = cls()
        p = _find_limits_json()
        if not p: return r
        try:
            j = json.load(open(p, encoding="utf-8"))
        except Exception:
            return r
        s = j.get("재량_사이징", {}); k = j.get("킬스위치_메타룰", {})
        pct = lambda v: abs(float(v)) / 100.0
        if "risk_per_trade_pct" in s:      r.risk_pct = pct(s["risk_per_trade_pct"])
        if "손절_k_atr" in s:              r.k_atr = float(s["손절_k_atr"])
        if "adtv_주문캡_pct" in s:         r.adtv_cap = pct(s["adtv_주문캡_pct"])
        if "portfolio_heat_cap_pct" in s:  r.heat_cap = pct(s["portfolio_heat_cap_pct"])
        if "동시보유_최대" in s:           r.max_positions = int(s["동시보유_최대"])
        if "동일테마_최대종목" in s:       r.same_theme_max = int(s["동일테마_최대종목"])
        if "동일테마_lane캡_pct" in s:     r.same_theme_lane_cap = pct(s["동일테마_lane캡_pct"])
        if "1종목_lane캡_pct" in s:        r.one_name_lane_cap = pct(s["1종목_lane캡_pct"])
        if "lane_일손실_정지_pct" in k:    r.lane_daily_kill = -pct(k["lane_일손실_정지_pct"])
        if "lane_주손실_정지_pct" in k:    r.lane_weekly_kill = -pct(k["lane_주손실_정지_pct"])
        if "월손실_신규정지_pct" in k:     r.lane_monthly_kill = -pct(k["월손실_신규정지_pct"])
        if "연속손실_사이즈절반" in k:     r.throttle_half_at = int(k["연속손실_사이즈절반"])
        if "연속손실_당주중단" in k:       r.throttle_stop_at = int(k["연속손실_당주중단"])
        return r


RULE = SizingRule.load()   # 모듈 로드 시 1회 — import 측은 RULE 그대로 쓰면 SSOT 적용


# ── 사이징 ──
def size_by_atr(capital, price, atr, rule=None, adtv_krw=None, streak=0):
    """risk룰+ATR 수량. 하한가/큰 손절폭·ADTV캡·연속손실 스로틀 반영.
    반환 dict(qty, stop_dist, risk_krw, notes[])."""
    rule = rule or RULE
    notes=[]
    stop_dist = rule.k_atr*atr
    if stop_dist<=0: return dict(qty=0, stop_dist=0, risk_krw=0, notes=["ATR 0 → 스킵"])
    risk_krw = capital*rule.risk_pct
    # 연속손실 스로틀
    mult=1.0
    if streak>=rule.throttle_stop_at: return dict(qty=0, stop_dist=stop_dist, risk_krw=0,
        notes=[f"연속손실 {streak}회 ≥ {rule.throttle_stop_at} → 당주 신규 중단"])
    if streak>=rule.throttle_half_at: mult=0.5; notes.append(f"연속손실 {streak}회 → 사이즈 ½")
    qty = math.floor(risk_krw*mult/stop_dist)
    # ADTV 캡
    if adtv_krw:
        cap_qty = math.floor(adtv_krw*rule.adtv_cap/price)
        if qty>cap_qty: qty=cap_qty; notes.append(f"ADTV 1% 캡 적용(≤{cap_qty}주)")
    return dict(qty=max(qty,0), stop_dist=stop_dist, risk_krw=risk_krw*mult, notes=notes)

def portfolio_heat(positions, capital):
    """총 heat = Σ(진입가−현손절가)×수량 / 자본. positions:[{entry,stop,qty}]."""
    if capital<=0: return 0.0
    risk = sum(max(p["entry"]-p["stop"],0)*p["qty"] for p in positions)
    return risk/capital

def heat_ok(positions, capital, rule=None):
    rule = rule or RULE
    h=portfolio_heat(positions,capital)
    return (h<=rule.heat_cap, h)

def concentration_ok(new_theme, positions, lane_capital, new_cost, rule=None):
    """동시보유·동일테마 종목수/비중·1종목 비중 강제. positions:[{theme,cost}]."""
    rule = rule or RULE
    reasons=[]
    held=len(positions)
    if held>=rule.max_positions: reasons.append(f"동시보유 {held}≥{rule.max_positions}")
    same=[p for p in positions if p.get("theme")==new_theme]
    if len(same)>=rule.same_theme_max: reasons.append(f"동일테마 {len(same)}≥{rule.same_theme_max}종")
    if lane_capital>0:
        theme_cost=sum(p["cost"] for p in same)+new_cost
        if theme_cost>lane_capital*rule.same_theme_lane_cap:
            reasons.append(f"동일테마 비중 {theme_cost/lane_capital*100:.0f}%>lane {rule.same_theme_lane_cap*100:.0f}%")
        if new_cost>lane_capital*rule.one_name_lane_cap:
            reasons.append(f"1종목 {new_cost/lane_capital*100:.0f}%>lane {rule.one_name_lane_cap*100:.0f}%")
    return (len(reasons)==0, reasons)

def killswitch_check(lane_ret_daily, lane_ret_weekly, lane_ret_monthly, rule=None):
    """lane 누적손실 기반 신규진입 정지 판정 → (allow_new, reason)."""
    rule = rule or RULE
    if lane_ret_daily<=rule.lane_daily_kill:   return False, f"lane 일 {lane_ret_daily*100:.1f}% ≤ {rule.lane_daily_kill*100:.0f}% → 신규정지"
    if lane_ret_weekly<=rule.lane_weekly_kill: return False, f"lane 주 {lane_ret_weekly*100:.1f}% ≤ {rule.lane_weekly_kill*100:.0f}% → 신규정지"
    if lane_ret_monthly<=rule.lane_monthly_kill: return False, f"lane 월 {lane_ret_monthly*100:.1f}% ≤ {rule.lane_monthly_kill*100:.0f}% → 전량점검"
    return True, "정상"

def loss_throttle(streak, rule=None):
    rule = rule or RULE
    if streak>=rule.throttle_stop_at: return 0.0, f"{streak}연속 → 당주 중단"
    if streak>=rule.throttle_half_at: return 0.5, f"{streak}연속 → 사이즈 ½"
    return 1.0, "정상"

def _self_test():
    ok=tot=0
    def chk(n,c):
        nonlocal ok,tot; tot+=1; ok+=1 if c else 0; print(f"  [{'OK' if c else 'FAIL'}] {n}")
    R=SizingRule()   # 기존 기대값 유지를 위해 기본값 규칙으로 검사 (SSOT 적용값은 별도 검사)
    # 자본1000만, risk2%=20만, ATR 1000·k2.5 → stop2500 → 80주
    s=size_by_atr(10_000_000, 50000, 1000, rule=R); chk("2%룰 수량(80주)", s["qty"]==80)
    # ADTV 캡: ADTV 1억×1%=100만 / 5만 = 20주로 제한
    s2=size_by_atr(10_000_000, 50000, 1000, rule=R, adtv_krw=100_000_000); chk("ADTV 1% 캡(20주)", s2["qty"]==20)
    # 연속손실 3 → ½ (40주)
    s3=size_by_atr(10_000_000, 50000, 1000, rule=R, streak=3); chk("3연속→½(40주)", s3["qty"]==40)
    s4=size_by_atr(10_000_000, 50000, 1000, rule=R, streak=5); chk("5연속→중단(0주)", s4["qty"]==0)
    # heat: 2포지션 각 리스크 20만 → 40만/1000만=4% ≤6% OK
    okh,h=heat_ok([{"entry":50000,"stop":47500,"qty":80},{"entry":50000,"stop":47500,"qty":80}],10_000_000,rule=R)
    chk("heat 4%≤6% 통과", okh and abs(h-0.04)<1e-6)
    # heat 초과: 4포지션 각 2% → 8%>6% 차단
    p4=[{"entry":50000,"stop":47500,"qty":80}]*4
    chk("heat 8%>6% 차단", not heat_ok(p4,10_000_000,rule=R)[0])
    # 집중: 동일테마 2종 보유 → 3종째 차단
    okc,rs=concentration_ok("AI",[{"theme":"AI","cost":10},{"theme":"AI","cost":10}],100,10,rule=R)
    chk("동일테마 3종째 차단", not okc)
    # 1종목 lane 30%>25% 차단
    okc2,_=concentration_ok("AI",[],100,30,rule=R); chk("1종목 30%>25% 차단", not okc2)
    # 킬스위치: 일 -8% ≤ -7% → 정지
    chk("킬스위치 일-8% 정지", not killswitch_check(-0.08,0,0,rule=R)[0])
    chk("킬스위치 정상 통과", killswitch_check(-0.03,-0.05,-0.10,rule=R)[0])
    # 스로틀
    chk("스로틀 3연속=½", loss_throttle(3,R)[0]==0.5)
    chk("스로틀 5연속=0", loss_throttle(5,R)[0]==0.0)
    # ── SSOT 배선 검사 (진우_통합한도.json 있을 때만) ──
    if _find_limits_json():
        chk("SSOT: risk 1%(JSON)", abs(RULE.risk_pct-0.01)<1e-9)
        chk("SSOT: 월 킬 −15%(JSON)", abs(RULE.lane_monthly_kill-(-0.15))<1e-9)
        chk("SSOT: heat 6%", abs(RULE.heat_cap-0.06)<1e-9)
    else:
        print("  [SKIP] 진우_통합한도.json 없음 — 기본값 모드")
    print(f"\n셀프테스트: {ok}/{tot}")
    print(f"적용 중(RULE): risk {RULE.risk_pct*100:.1f}% · k_atr {RULE.k_atr} · heat≤{RULE.heat_cap*100:.0f}% · "
          f"동시≤{RULE.max_positions} · 킬 일{RULE.lane_daily_kill*100:.0f}/주{RULE.lane_weekly_kill*100:.0f}/월{RULE.lane_monthly_kill*100:.0f}%")
    return ok==tot

def main():
    ap=argparse.ArgumentParser(description="사이징·heat·킬스위치 강제(개선안 ⑦) — SSOT: 진우_통합한도.json")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--show", action="store_true", help="현재 적용 규칙값 출력(SSOT 반영)")
    a=ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    if a.show:
        src=_find_limits_json() or "(기본값 — JSON 없음)"
        print(f"SSOT: {src}"); print(json.dumps(asdict(RULE), ensure_ascii=False, indent=2))
    else:
        print(__doc__); print("→ --self-test 로 검증. import 해서 size_by_atr()/portfolio_heat()/killswitch_check() 사용.")
    return 0

if __name__=="__main__":
    sys.exit(main())
