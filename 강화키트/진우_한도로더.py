#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우_한도로더.py — 통합 한도 단일 로더 · 개선안 C

진우_통합한도.json 을 읽어 각 계층에 뿌리는 단일 진실원천 로더.
기존 코드 호환: RiskGuard용 Limits dict, 비용모델용 CostModel dict를 그대로 뽑아준다.
값을 코드 여기저기 흩지 말고 여기로 모은다.

사용:
  from 진우_한도로더 import load, riskguard_limits, cost_model, sizing, killswitch
  L=load(); print(riskguard_limits(L))
  py 진우_한도로더.py --show
  py 진우_한도로더.py --self-test
⚠️ 투자자문 아님·책임 본인.
"""

# ── 경로 자립화 (2026-07-27) — 샌드박스 하드코딩 제거 ──────────────
import os as _os, glob as _glob
_JQ_HERE = _os.path.dirname(_os.path.abspath(__file__))


def _jqroot():
    d = _JQ_HERE
    for _ in range(5):
        if _os.path.exists(_os.path.join(d, "종목시총_30년.csv")):
            return d
        d = _os.path.dirname(d)
    return _os.path.dirname(_JQ_HERE)


BASE = _os.environ.get("JQ_BASE", _jqroot())


def _jqfind(name):
    """이름으로 파일 자동탐색 (백업/보관 폴더 제외)."""
    for b in (BASE, _JQ_HERE, _os.getcwd()):
        hits = [h for h in _glob.glob(_os.path.join(b, "**", name), recursive=True)
                if not any(s in h for s in ("_백업", "_보관", "_archive", "__pycache__"))]
        if hits:
            return sorted(hits, key=len)[0]
    raise FileNotFoundError(f"{name} 를 못 찾음 (루트={BASE})")
# ────────────────────────────────────────────────────────────────

import os, sys, json, argparse
BASE=os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def _find(fn):
    for d in (BASE, os.path.dirname(BASE), os.getcwd()):
        p=os.path.join(d,fn)
        if os.path.exists(p): return p
    return None

def load(path=None):
    p=path or _find("진우_통합한도.json")
    if not p: raise FileNotFoundError("진우_통합한도.json 없음")
    return json.load(open(p,encoding="utf-8"))

def riskguard_limits(L):
    """진우_리스크차단기.Limits 로 바로 넣을 dict."""
    r=L["집행_riskguard"]
    return {k:v for k,v in r.items() if not k.startswith("_")}

def cost_model(L):
    c=L["비용"]
    return dict(tax_kospi=c["tax_kospi"], tax_kosdaq=c["tax_kosdaq"], commission=c["commission"])

def sizing(L):
    return L["재량_사이징"]

def concentration(L):
    return L["재량_집중한도"]

def killswitch(L):
    return L["재량_킬스위치"]

def exit_rules(L):
    return L["재량_매도_v3"]

def validate(L):
    """한도 정합성 점검 → (ok, 경고리스트)."""
    warns=[]
    s=L["재량_사이징"]; c=L["재량_집중한도"]
    if s["risk_per_trade_pct"]>s["risk_per_trade_max_pct"]:
        warns.append("risk_per_trade > max")
    if c["1종목_lane_cap_pct"]>100: warns.append("1종목 lane cap >100%")
    if c["동일테마_lane_cap_pct"]<c["1종목_lane_cap_pct"]:
        warns.append("동일테마 cap < 1종목 cap (모순)")
    rg=L["집행_riskguard"]
    if rg["max_weight_pct"]<=0 or rg["price_band_pct"]<=0: warns.append("RiskGuard 한도 0 이하")
    k=L["재량_킬스위치"]
    if not (k["일_pct"]>k["주_pct"]>k["월_pct"]): warns.append("킬스위치 일>주>월 순서 아님")
    return (len(warns)==0, warns)

def _self_test():
    ok=tot=0
    def chk(n,c):
        nonlocal ok,tot; tot+=1; ok+=1 if c else 0; print(f"  [{'OK' if c else 'FAIL'}] {n}")
    L=load()
    chk("로드 성공", isinstance(L,dict) and "집행_riskguard" in L)
    rl=riskguard_limits(L)
    chk("RiskGuard dict 추출(밴드10)", rl["price_band_pct"]==10.0 and "_설명" not in rl)
    cm=cost_model(L); chk("비용 dict(세금0.2%)", cm["tax_kospi"]==0.0020)
    chk("사이징 risk 1%(최신 정본)", sizing(L)["risk_per_trade_pct"]==1.0)
    chk("매도 momentum 3.5ATR", exit_rules(L)["momentum_트레일_atr"]==3.5)
    chk("매도 deepvalue 타이트 없음", exit_rules(L)["deepvalue_타이트스톱"]==False)
    okv,warns=validate(L); chk("정합성 검증 통과", okv)
    if warns: print("   경고:",warns)
    print(f"\n셀프테스트: {ok}/{tot}"); return ok==tot

def show():
    L=load()
    print("="*70); print("진우 통합 한도 — 현재값"); print("="*70)
    print(f"  [집행 RiskGuard] 밴드±{L['집행_riskguard']['price_band_pct']:.0f}% · 비중≤{L['집행_riskguard']['max_weight_pct']:.0f}% · 최대{L['집행_riskguard']['max_positions']}종 · 일손실{L['집행_riskguard']['daily_loss_limit_pct']:.0f}%")
    print(f"  [비용] 매도세 {L['비용']['tax_kospi']*100:.2f}% · 수수료 {L['비용']['commission']*100:.3f}% · 손익분기 +{L['비용']['breakeven_move_pct']:.2f}%")
    s=L['재량_사이징']; print(f"  [재량 사이징] risk {s['risk_per_trade_pct']:.0f}%(최대{s['risk_per_trade_max_pct']:.0f}) · 돌파 {s['돌파_risk_per_trade_pct']:.1f}% · heat≤{s['portfolio_heat_cap_pct']:.0f}%")
    c=L['재량_집중한도']; print(f"  [재량 집중] lane≤{c['lane_총비중_cap_pct']:.0f}% · 동일테마≤{c['동일테마_최대종목']}종&{c['동일테마_lane_cap_pct']:.0f}% · 동시{c['동시보유_권장']}~{c['동시보유_최대']}")
    e=L['재량_매도_v3']; print(f"  [매도 v3] core=MA200+등급 · momentum={e['momentum_트레일_atr']}ATR/−{e['momentum_트레일_pct']:.0f}% · deepvalue=재난{e['deepvalue_재난백스톱_pct']:.0f}%·가치익절")
    k=L['재량_킬스위치']; print(f"  [킬스위치] 일{k['일_pct']:.0f}/주{k['주_pct']:.0f}/월{k['월_pct']:.0f}/분기{k['분기_pct']:.0f}% · 연속손실 {k['연속손실_half_at']}½/{k['연속손실_stop_at']}중단")
    print(f"  [수익코어] 본체=v3.7.2(총+43.1%p vs KOSPI) · 재량=무코어(안 D) · 계절틸트=기각")
    okv,warns=validate(L); print(f"\n  정합성: {'✅ 통과' if okv else '⚠️ '+str(warns)}")

def main():
    ap=argparse.ArgumentParser(description="통합 한도 로더")
    ap.add_argument("--show",action="store_true"); ap.add_argument("--self-test",action="store_true")
    a=ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    show(); return 0

if __name__=="__main__": sys.exit(main())
