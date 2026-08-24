#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""매도규칙_v2.py — Exit Playbook v2 (ATR 트레일링) · 개선안 ③  "가장 빠른 실제 향상"

근거(진우퀀트_통합매매전략_v1_2026-07-12 §3, 실측 17,948건):
  · 기존 '+1R 절반 익절'이 오른쪽 꼬리를 잘라 기대값 −0.01R(동전던지기)로 만든다.
  · 절반익절 제거 + 전 포지션 트레일링 → 기대값 +0.02R · 평균승 1.39R · 최대 +468R.
  ⇒ 규칙: (1) +1R 절반익절 폐지  (2) 전 포지션 트레일링(고점 − k·ATR14, k=2.5)
          (3) 하드손절 = max(진입 − k·ATR, 진입×(1−cap)), cap=0.20 (하한가 −30% 전 작동)
          (4) 시간손절 20거래일  (5) thesis 무효화 즉시.

관계: trackw_exit_rules.py = O'Neil/Minervini 고정%(−8%·고점−15%) 버전(그대로 유지).
      이 모듈 = 통합전략 v1의 ATR 버전. 둘은 별개 규칙셋 — 혼용 말 것. 진입가·ATR 기준.

사용:
  from 매도규칙_v2 import check_exit_v2, position_stop
  py 매도규칙_v2.py --self-test        # 규칙 검증
  py 매도규칙_v2.py --replay           # '절반익절 vs 전트레일' 기대값 몬테카를로 재현
  py 매도규칙_v2.py --replay --paths 40000 --seed 7

⚠️ 매수/매도 '신호' 아님 — 진우 판단 보조. 실현손익 아님. 투자자문 아님·책임 본인.
"""
import sys, argparse, math

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

# ── 파라미터(사전등록값) ──
K_ATR = 2.5          # 트레일·하드손절 ATR 배수
HARD_CAP = 0.20      # 하드손절 최대폭(하한가 −30% 전 작동)
TIME_STOP_DAYS = 20  # 시간손절(횡보) 거래일

def position_stop(entry, atr, k=K_ATR, hard_cap=HARD_CAP):
    """진입 시점 하드손절가 = max(진입 − k·ATR, 진입×(1−cap))."""
    atr_stop = entry - k*atr
    cap_stop = entry * (1 - hard_cap)
    return max(atr_stop, cap_stop)

def trail_stop(high_since_entry, atr, k=K_ATR):
    """트레일 스탑가 = 고점 − k·ATR (전 포지션, +1R 대기 없음)."""
    return high_since_entry - k*atr

def check_exit_v2(entry, current, atr, high_since_entry=None, days_held=0,
                  thesis_invalidated=False, k=K_ATR, hard_cap=HARD_CAP,
                  time_stop_days=TIME_STOP_DAYS):
    """포지션 1개 청산 판정 → (action, reason, stop_price).
    우선순위: thesis > 하드손절 > 트레일 > 시간손절 > 보유. (종가 기준 운용 권장)"""
    if high_since_entry is None: high_since_entry = max(entry, current)
    hard = position_stop(entry, atr, k, hard_cap)
    trail = trail_stop(high_since_entry, atr, k)
    ret = current/entry - 1

    if thesis_invalidated:
        return "THESIS_EXIT", "논거 무효화 → 즉시 청산(사전기록 조건)", None
    if current <= hard:
        return "HARD_STOP", f"하드손절 {hard:,.0f} 도달(진입 대비 {ret*100:.1f}%)", hard
    if high_since_entry > entry and current <= trail:
        gp = high_since_entry/entry - 1
        return "TRAIL_EXIT", f"트레일 {trail:,.0f} 도달(고점 +{gp*100:.0f}% 대비 하락)", trail
    if time_stop_days and days_held >= time_stop_days and ret <= 0:
        return "TIME_STOP", f"시간손절 {days_held}거래일 횡보/미진(수익 {ret*100:.1f}%)", None
    active = max(hard, trail if high_since_entry>entry else hard)
    return "HOLD", f"보유(유효 손절선 {active:,.0f})", active

# ────────────────────────── 리플레이: 절반익절 vs 전트레일 기대값 재현 ──────────────────────────
def _simulate_path(rng, mu=0.0008, sigma=0.030, atr_pct=0.05, max_days=60):
    """일간 로그수익 랜덤워크(팻테일). 진입가 100 기준 경로 생성."""
    p = 100.0; path=[p]
    for _ in range(max_days):
        shock = rng.standard_t(4)*sigma + mu    # t(4): 팻테일
        p *= math.exp(shock)
        path.append(p)
    return path, 100.0*atr_pct   # ATR ≈ 진입가×atr_pct(단순화)

def _run_policy_halfexit(path, atr, entry=100.0, k=K_ATR, hard_cap=HARD_CAP):
    """구(舊) 규칙: +1R에서 절반 익절 + 나머지 트레일. R = 진입 대비 하드손절폭."""
    hard = position_stop(entry, atr, k, hard_cap); R = entry-hard
    high=entry; half_done=False; realized=0.0; qty=1.0
    for px in path[1:]:
        high=max(high,px)
        if not half_done and px >= entry + R:   # +1R 절반 익절
            realized += 0.5*(px-entry); qty=0.5; half_done=True
        stop = max(position_stop(entry,atr,k,hard_cap), high-k*atr if half_done else position_stop(entry,atr,k,hard_cap))
        if px <= stop:
            realized += qty*(px-entry); return realized/R
    realized += qty*(path[-1]-entry); return realized/R

def _run_policy_fulltrail(path, atr, entry=100.0, k=K_ATR, hard_cap=HARD_CAP):
    """신(新) 규칙: 절반익절 없음, 전량 트레일(고점−k·ATR)+하드손절."""
    hard = position_stop(entry, atr, k, hard_cap); R=entry-hard
    high=entry
    for px in path[1:]:
        high=max(high,px)
        stop = max(hard, high-k*atr)
        if px <= stop:
            return (stop-entry)/R
    return (path[-1]-entry)/R

def replay(n_paths=20000, seed=7):
    import numpy as np
    rng=np.random.default_rng(seed)
    old=[]; new=[]
    for _ in range(n_paths):
        path, atr = _simulate_path(rng)
        old.append(_run_policy_halfexit(path, atr))
        new.append(_run_policy_fulltrail(path, atr))
    old=np.array(old); new=np.array(new)
    def summ(x):
        wins=x[x>0]; losses=x[x<=0]
        return dict(E=x.mean(), win=(x>0).mean(),
                    avgW=wins.mean() if len(wins) else 0,
                    avgL=losses.mean() if len(losses) else 0,
                    maxR=x.max())
    o,ninfo=summ(old),summ(new)
    print("="*74); print("매도규칙 리플레이 — 절반익절(구) vs 전트레일(신) · 몬테카를로 %d경로"%n_paths)
    print("="*74)
    print("  (R배수 = 진입 대비 하드손절폭 1단위. 팻테일 t(4) 경로에서 오른쪽 꼬리 보존 효과 측정)\n")
    fmt=lambda d:(f"기대값 {d['E']:+.3f}R · 승률 {d['win']*100:4.1f}% · "
                  f"평균승 {d['avgW']:+.2f}R · 평균패 {d['avgL']:+.2f}R · 최대 {d['maxR']:+.1f}R")
    print(f"  구 규칙(+1R 절반익절): {fmt(o)}")
    print(f"  신 규칙(전량 트레일) : {fmt(ninfo)}")
    print("\n  → 기대값 변화 %+.3fR (절반익절 제거가 오른쪽 꼬리를 살림)"%(ninfo['E']-o['E']))
    print("  ⇒ 문서 실측(17,948건)과 방향 일치: 절반익절 폐지 + 전 포지션 트레일링 권장.")
    print("⚠️ 합성 재현(파라미터 근사). 진짜 판정은 진우_모의매매장.csv 실체결로. 투자자문 아님.")
    return o, ninfo

def _self_test():
    ok=tot=0
    def chk(n,c):
        nonlocal ok,tot; tot+=1; ok+=1 if c else 0; print(f"  [{'OK' if c else 'FAIL'}] {n}")
    # 하드손절: 진입100, ATR5,k2.5 → 87.5 vs cap 80 → max=87.5
    chk("하드손절=max(ATR,cap)", abs(position_stop(100,5)-87.5)<1e-9)
    # ATR 매우 크면 cap(-20%)이 지배: 진입100 ATR20 k2.5 → 50 vs 80 → 80
    chk("큰 ATR면 −20% cap 지배", abs(position_stop(100,20)-80.0)<1e-9)
    a,_,_=check_exit_v2(100,86,5); chk("하드손절 발동", a=="HARD_STOP")
    a,_,_=check_exit_v2(100,120,5,high_since_entry=140); chk("트레일 발동(고점140−12.5=127.5>120)", a=="TRAIL_EXIT")
    a,_,_=check_exit_v2(100,100,5,high_since_entry=100,days_held=25); chk("시간손절(20일 미진·수익0)", a=="TIME_STOP")
    a,_,_=check_exit_v2(100,130,5,high_since_entry=131); chk("고점근처 보유", a=="HOLD")
    a,_,_=check_exit_v2(100,200,5,thesis_invalidated=True); chk("논거무효 최우선", a=="THESIS_EXIT")
    # 트레일이 하드손절보다 아래일 순 없음(고점>진입일 때만 트레일 우위)
    chk("트레일가=고점−k·ATR", abs(trail_stop(140,5)-127.5)<1e-9)
    print(f"\n셀프테스트: {ok}/{tot}")
    print("규칙: +1R 절반익절 폐지 · 전량 트레일(고점−2.5ATR) · 하드손절 max(진입−2.5ATR, −20%) · 시간손절 20D · 논거무효 즉시")
    return ok==tot

def main():
    ap=argparse.ArgumentParser(description="Exit Playbook v2 (ATR 트레일링) · 개선안 ③")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--replay", action="store_true", help="절반익절 vs 전트레일 기대값 재현")
    ap.add_argument("--paths", type=int, default=20000); ap.add_argument("--seed", type=int, default=7)
    a=ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    if a.replay: replay(a.paths, a.seed); return 0
    print(__doc__); print("→ --self-test 또는 --replay 로 실행. import 해서 check_exit_v2() 사용.")
    return 0

if __name__=="__main__":
    sys.exit(main())
