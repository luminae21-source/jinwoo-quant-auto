#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""recommend_pipeline.py — 최신데이터 갱신 → 추천 대시보드 (원클릭 파이프라인) · 안전판 반영

순서:
  [1] 진우_일봉_증분수집.py  — 최근 빠진 날 pykrx 증분 수집
  [2] mcap_update.py         — 시총 증분 갱신
  [★] preflight.py           — 데이터 헬스체크(최신성·무결성). ★FAIL이면 추천·카톡 차단(안전판)
  [3] recommend_dashboard.py — 월봉캐시 재생성 + 추천 생성
  [4] kakao_send_recommend.py— 카톡 발송 (데이터 정상일 때만)
  [5] jq_history.py / [6] jq_hub.py — 이력·허브

★ 변경(2세대 안전판): 기존 'fail-open(실패해도 직전 데이터로 진행·카톡 발송)'을
  'fail-safe(데이터 낡음/깨짐이면 카톡 차단·STALE 표기)'로 바꿈. 낡은 신호로 매매 금지.
사용: py recommend_pipeline.py [--no-kakao] [--force(게이트 무시)]
⚠️ 정보·검증용·미래보장 아님. 투자자문 아님·책임 본인.
"""
import os, sys, subprocess, datetime
HERE=os.path.dirname(os.path.abspath(__file__)); PARENT=os.path.dirname(HERE)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def find(name):
    for d in (HERE, PARENT):
        p=os.path.join(d,name)
        if os.path.exists(p): return p
    return None

def step(title, script, args=None, cwd=None):
    p=find(script)
    print("\n"+"="*60); print(f"[{title}] {script}"); print("="*60)
    if not p: print(f"  건너뜀 — {script} 없음"); return False
    try:
        r=subprocess.run([sys.executable,"-W","ignore",p]+(args or []), cwd=cwd or os.path.dirname(p))
        ok=(r.returncode==0); print("  ->", "완료" if ok else f"경고(코드 {r.returncode})")
        return ok
    except Exception as e:
        print("  실행 오류:",e); return False

def preflight_gate(force=False):
    """데이터 헬스체크. 반환 True=안전(진행), False=STALE(카톡 차단)."""
    p=find("preflight.py")
    print("\n"+"="*60); print("[★ 안전 게이트] preflight.py"); print("="*60)
    if not p:
        print("  preflight.py 없음 — 게이트 스킵(주의)"); return True
    r=subprocess.run([sys.executable,"-W","ignore",p], cwd=os.path.dirname(p))
    if r.returncode==0:
        print("  -> ✅ 데이터 정상 — 추천·카톡 진행"); return True
    if force:
        print("  -> ❌ 데이터 문제(FAIL)이나 --force 지정 → 강제 진행(위험)"); return True
    print("  -> ❌ 데이터 문제(FAIL) → 추천은 생성하되 카톡 발송 차단·STALE 표기")
    return False

def snapshot_gate():
    """수집이 데이터를 덮어쓰기 전에 스냅샷(롤백용). best-effort."""
    p=find("data_snapshot.py")
    print("\n"+"="*60); print("[0/6 데이터 스냅샷] data_snapshot.py"); print("="*60)
    if not p: print("  data_snapshot.py 없음 — 스냅샷 스킵(주의)"); return
    try:
        subprocess.run([sys.executable,"-W","ignore",p], cwd=os.path.dirname(p))
    except Exception as e:
        print("  스냅샷 실패(무시):",e)

def main():
    force="--force" in sys.argv
    print("진우퀀트 추천 파이프라인 —", datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    snapshot_gate()  # ★ 수집 전 백업(깨지면 data_snapshot --rollback 으로 복원)
    step("1/6 최신시세 증분수집", "진우_일봉_증분수집.py")
    step("2/6 시총 증분갱신", "mcap_update.py", cwd=HERE)

    # ★ 안전 게이트: 데이터가 낡거나 깨졌으면 카톡 차단
    data_ok = preflight_gate(force=force)

    step("3/6 추천 대시보드 생성", "recommend_dashboard.py", ["--refresh-cache"], cwd=HERE)

    if "--no-kakao" not in sys.argv:
        if data_ok:
            step("4/6 카톡 요약 발송", "kakao_send_recommend.py", cwd=HERE)
        else:
            print("\n"+"="*60); print("[4/6 카톡] ⛔ 차단 — 데이터 STALE/오류로 발송 안 함")
            print("="*60)
            print("  낡은/깨진 데이터로 만든 추천을 실시간 신호로 보내지 않습니다.")
            print("  조치: 인터넷 확인 후 recommend_auto 재실행. 강제 발송은 --force(권장 안 함).")
            # ★ 놓침 방지: '차단했다'는 사실 자체를 카톡으로 알림(best-effort)
            try:
                p=find("jq_notify.py")
                if p:
                    import importlib.util
                    spec=importlib.util.spec_from_file_location("jq_notify",p)
                    m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
                    m.alert_stale("preflight FAIL")
            except Exception as e:
                print("  (알림 발송 실패 — 무시):", e)

    step("5/6 이력 DB 축적", "jq_history.py", cwd=HERE)
    step("6/6 허브 갱신", "jq_hub.py", cwd=HERE)

    banner = "⚠️ STALE(데이터 문제)" if not data_ok else "✅ 정상"
    print(f"\n완료 — 상태 {banner}. 진우퀀트_허브.html · 추천대시보드.html")

if __name__=="__main__":
    main()
