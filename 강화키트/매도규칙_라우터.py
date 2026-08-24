#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""매도규칙_라우터.py — 매도규칙 v3 통일 라우터 (진입 유형이 매도를 결정) · 개선안 B

★ 정본 = 매도규칙서.md v2 §9 (2026-07-19). 이 모듈은 그 §9를 코드로 통일한 라우터다.
   "매도는 진입이 결정한다": 진입 유형별로 완전히 다른 청산 규칙을 라우팅한다.

세 갈래:
  · core     (본체 v3.7.2, 월간 대형주) — 포지션별 ATR 스톱 없음.
             MA200 월간 방어 + 등급이탈 청산이 담당(별도 엔진). 여기선 안내만.
  · momentum (재량 모멘텀·돌파)          — 넓은 트레일(고점 − max(3.5·ATR, 25%)).
             ⚠️ 2.5ATR는 §9 검증서 13일 만에 휩쏘 → 금지. 근본이 약한 엣지라 비중 작게.
  · deepvalue(딥밸류 바닥, 저PBR+과매도+턴) — 타이트 스톱 없음(휩쏘). 재난 백스톱(−40%)만.
             익절 = 적정가치 회귀/과열(이격≥1.5 or +100% or PBR≥1.0). 분산·인내로 관리.

⚠️ 이 라우터는 지난 턴의 `매도규칙_v2.py`(균일 2.5ATR 트레일)를 **대체**한다.
   §9 일봉 검증에서 2.5ATR 균일 트레일이 모멘텀·돌파조차 휩쏘시킴이 드러났다. v2 균일 트레일 폐기.

사용:
  from 매도규칙_라우터 import check_exit
  a,why,stop = check_exit("deepvalue", entry=10000, current=9500, atr=400, high=10000,
                          days_held=5, ma200=6800, gain_peak=0.0, pbr=0.8)
  py 매도규칙_라우터.py --self-test
⚠️ 매수/매도 신호 아님 — 진우 판단 보조. 실현손익 아님. 투자자문 아님·책임 본인.
"""
import sys, argparse
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

# ── 파라미터(§9 정본) ──
MOM_TRAIL_ATR   = 3.5     # 모멘텀 트레일 ATR 배수(넓게)
MOM_TRAIL_PCT   = 0.25    # 또는 고점 대비 −25%(둘 중 넓은 것)
DV_DISASTER     = -0.40   # 딥밸류 재난 백스톱(−40%대)
DV_TP_GAP       = 1.5     # 익절: 이격(현재가/MA200) ≥ 1.5
DV_TP_GAIN      = 1.00    # 또는 +100%(2배)
DV_TP_PBR       = 1.0     # 또는 PBR ≥ 1.0
TIME_STOP_DAYS  = 20
TIME_STOP_BAND  = 0.05    # ±5% 횡보

def check_exit(entry_type, entry, current, atr=None, high=None, days_held=0,
               thesis_invalidated=False, ma200=None, gain_peak=None, pbr=None):
    """진입 유형별 청산 판정 → (action, reason, stop_price|None). 종가 기준 운용."""
    et=entry_type.lower()
    if high is None: high=max(entry, current)
    if gain_peak is None: gain_peak=high/entry-1
    ret=current/entry-1

    # 공통 1순위: thesis 무효화
    if thesis_invalidated:
        return "THESIS_EXIT","논거 무효화 → 즉시 청산(사전기록 조건)",None

    # ── core: 포지션별 스톱 없음 ──
    if et in ("core","본체"):
        return "CORE_MANAGED","본체는 MA200 월간 방어 + 등급이탈 청산이 담당(포지션 ATR 스톱 없음)",None

    # ── momentum/돌파: 넓은 트레일 ──
    if et in ("momentum","돌파","모멘텀","breakout"):
        if atr is None: return "HOLD","ATR 필요(넓은 트레일)",None
        trail = high - max(MOM_TRAIL_ATR*atr, MOM_TRAIL_PCT*high)   # 둘 중 더 낮은 스톱=더 넓게
        if current<=trail and high>entry:
            return "TRAIL_EXIT",f"넓은 트레일 {trail:,.0f} 도달(고점 +{gain_peak*100:.0f}% 대비)",trail
        if TIME_STOP_DAYS and days_held>=TIME_STOP_DAYS and abs(ret)<=TIME_STOP_BAND:
            return "TIME_STOP",f"시간손절 {days_held}일 ±5% 횡보",None
        return "HOLD",f"보유(넓은 트레일 {trail:,.0f}, 2.5ATR 금지·휩쏘)",trail

    # ── deepvalue: 타이트 스톱 없음, 재난 백스톱 + 가치익절 ──
    if et in ("deepvalue","딥밸류","value"):
        # 재난 백스톱만
        if ret<=DV_DISASTER:
            return "DISASTER_STOP",f"재난 백스톱 {ret*100:.0f}% ≤ {DV_DISASTER*100:.0f}%(−40%대)",entry*(1+DV_DISASTER)
        # 가치 익절(적정가치 회귀/과열): 셋 중 하나
        reasons=[]
        gap = (current/ma200) if ma200 else None
        if gap is not None and gap>=DV_TP_GAP: reasons.append(f"이격 {gap:.2f}≥{DV_TP_GAP}")
        if ret>=DV_TP_GAIN: reasons.append(f"수익 +{ret*100:.0f}%≥+100%")
        if pbr is not None and pbr>=DV_TP_PBR: reasons.append(f"PBR {pbr:.2f}≥{DV_TP_PBR}")
        if reasons:
            return "VALUE_TAKE_PROFIT","적정가치 회귀·과열 익절("+", ".join(reasons)+")",None
        return "HOLD","보유(타이트 스톱 없음·분산인내 관리, 재난 백스톱 −40%만)",entry*(1+DV_DISASTER)

    return "HOLD",f"알 수 없는 진입유형 '{entry_type}' → 기본 보유",None

def _self_test():
    ok=tot=0
    def chk(n,c):
        nonlocal ok,tot; tot+=1; ok+=1 if c else 0; print(f"  [{'OK' if c else 'FAIL'}] {n}")
    # core
    a,_,_=check_exit("core",100,80); chk("core: 포지션 스톱 없음", a=="CORE_MANAGED")
    # 공통 thesis
    a,_,_=check_exit("deepvalue",100,200,thesis_invalidated=True); chk("thesis 최우선", a=="THESIS_EXIT")
    # momentum 넓은 트레일: 고점 200, ATR 10 → trail=max(35,50)=50 → 150. current 149<150 발동
    a,_,s=check_exit("momentum",100,149,atr=10,high=200); chk("momentum 넓은 트레일 발동(150)", a=="TRAIL_EXIT" and abs(s-150)<1e-6)
    a,_,_=check_exit("momentum",100,160,atr=10,high=200); chk("momentum 트레일 위 보유", a=="HOLD")
    a,_,_=check_exit("momentum",100,101,atr=10,high=101,days_held=25); chk("momentum 시간손절", a=="TIME_STOP")
    # deepvalue: 타이트 스톱 무시(−15%도 보유)
    a,_,_=check_exit("deepvalue",100,85,atr=5,high=100); chk("deepvalue −15%도 보유(타이트 무시)", a=="HOLD")
    a,_,_=check_exit("deepvalue",100,55); chk("deepvalue 재난 백스톱(−45%)", a=="DISASTER_STOP")
    a,_,_=check_exit("deepvalue",100,210); chk("deepvalue +110% 가치익절", a=="VALUE_TAKE_PROFIT")
    a,_,_=check_exit("deepvalue",100,120,ma200=70); chk("deepvalue 이격 1.71 가치익절", a=="VALUE_TAKE_PROFIT")
    a,_,_=check_exit("deepvalue",100,120,pbr=1.2); chk("deepvalue PBR 1.2 가치익절", a=="VALUE_TAKE_PROFIT")
    a,_,_=check_exit("deepvalue",100,120,ma200=100,pbr=0.7); chk("deepvalue 조건 미달 보유", a=="HOLD")
    print(f"\n셀프테스트: {ok}/{tot}")
    print("규칙(§9): core=MA200+등급 · momentum=넓은트레일(3.5ATR/−25%, 2.5ATR금지) · deepvalue=타이트無·재난−40%·가치익절(이격1.5/+100%/PBR1.0)")
    return ok==tot

def main():
    ap=argparse.ArgumentParser(description="매도규칙 v3 통일 라우터(§9)")
    ap.add_argument("--self-test",action="store_true")
    a=ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    print(__doc__); print("→ --self-test 로 검증. import 해서 check_exit(entry_type, ...) 사용.")
    return 0

if __name__=="__main__": sys.exit(main())
