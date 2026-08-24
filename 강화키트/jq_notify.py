#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""jq_notify.py — 파이프라인 이상 발생 시 카카오톡 '나에게' 자기알림 (시스템 자동화 안전판)

문제: 게이트가 카톡 발송을 '차단'하면 지금은 콘솔에만 뜬다 → PC를 안 보면 그 주 신호가
      조용히 스킵된 걸 모른다(놓침). 그래서 '막았다는 사실 자체'를 카톡으로 알려야 한다.

기능: alert(msg) — 기존 jq_kakao.send_text() 재사용해 짧은 경고를 발송. best-effort(절대 안 죽음).
      recommend_pipeline / preflight 어디서든 import 해서 호출 가능.
사용(단독점검): py jq_notify.py --test   (실제 발송 대신 문구만 출력: --dry-run)
⚠️ 정보·검증용·투자자문 아님·책임 본인.
"""
import os, sys, datetime
HERE=os.path.dirname(os.path.abspath(__file__)); PARENT=os.path.dirname(HERE)
for d in (PARENT, HERE):  # jq_kakao 는 보통 진우퀀트 루트에 있음
    if d not in sys.path: sys.path.insert(0, d)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

PREFIX="🚨[진우퀀트 자동감시]"

def _now(): return datetime.datetime.now().strftime("%Y-%m-%d %H:%M")

def alert(msg, dry_run=False, link_url="https://m.stock.naver.com"):
    """짧은 경고를 카톡 '나에게' 발송. 반환 True=발송성공 / False=실패·건너뜀.
    dry_run=True 면 실제 발송 안 하고 문구만 출력(테스트용)."""
    text=f"{PREFIX} {_now()}\n{msg}\n※ 정보용·투자자문 아님"
    text=text[:990]
    if dry_run or "--dry-run" in sys.argv:
        print("[jq_notify DRY-RUN] 보낼 문구:\n"+text); return False
    try:
        import jq_kakao as K
    except Exception as e:
        print(f"[jq_notify] jq_kakao 임포트 실패 — 알림 건너뜀: {e}"); return False
    try:
        tok=K.get_access_token()
        ok,res=K.send_text(tok, text, link_url=link_url)
        print("[jq_notify] 카톡 알림:", "성공" if ok else f"실패({res})")
        return bool(ok)
    except Exception as e:
        print(f"[jq_notify] 카톡 알림 오류(건너뜀): {e}"); return False

def alert_stale(detail=""):
    """데이터 STALE로 추천/카톡을 차단했을 때의 표준 알림."""
    return alert("데이터가 낡거나 깨져(STALE) 이번 추천·발송을 차단했습니다.\n"
                 "인터넷 확인 후 recommend_auto 재실행 필요."
                 + (f"\n({detail})" if detail else ""))

def alert_fail(step, detail=""):
    """특정 단계 실패 알림(수집 등)."""
    return alert(f"'{step}' 단계 실패로 파이프라인에 문제가 있습니다."
                 + (f"\n{detail}" if detail else ""))

def main():
    if "--test" in sys.argv or "--dry-run" in sys.argv:
        alert_stale("테스트 발송(단독 점검)")
    else:
        print("사용법: py jq_notify.py --test   (실제 발송) / --dry-run (문구만)")
        print("모듈로 import: from jq_notify import alert_stale, alert_fail")

if __name__=="__main__": main()
