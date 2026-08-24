#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""preflight.py — 파이프라인 실행 전 안전 게이트 (시스템 자동화 안전판)

"낡거나 깨진 데이터로 추천을 만들어 카톡으로 보내는 사고"를 원천 차단한다.
추천 파이프라인은 이걸 먼저 통과해야 하고, FAIL이면 추천·카톡을 막는다(fail-open → fail-safe).

검사:
  1) 데이터 헬스체크 (data_healthcheck.run) — 최신성·무결성·룩어헤드
  2) 핵심 모듈 셀프테스트 (있는 것만, best-effort)
결과를 preflight_status.json 에 기록 → 카톡/허브가 '상태 배지'로 쓸 수 있다.

사용: py preflight.py [--asof YYYY-MM]   (exit 0=진행OK / 1=중단)
⚠️ 정보·검증용. 투자자문 아님·책임 본인.
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

import os, sys, json, argparse, subprocess, datetime
BASE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,BASE)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

# 있으면 돌리는 셀프테스트(없으면 스킵). (스크립트, 인자)
SELFTESTS=[
 ("data_healthcheck.py", None),           # 존재 자체는 위에서 별도 실행
 ("진우_한도로더.py", "--self-test"),
 ("사이징_강제.py", "--self-test"),
 ("매도규칙_라우터.py", "--self-test"),
 ("pit_lag.py", "--self-test"),
]

def _find(fn):
    for d in (BASE, os.path.dirname(BASE), os.getcwd()):
        p=os.path.join(d,fn)
        if os.path.exists(p): return p
    return None

def run_data_check(asof):
    p=_find("data_healthcheck.py")
    if not p: return "MISSING", "data_healthcheck.py 없음"
    try:
        sys.path.insert(0, os.path.dirname(p))
        import importlib.util
        spec=importlib.util.spec_from_file_location("data_healthcheck", p)
        m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        # run()은 출력하고 verdict 반환
        v=m.run(asof=asof, as_json=False)
        return v, "ok"
    except Exception as e:
        return "ERROR", str(e)

def run_selftests():
    out={}
    for script,arg in SELFTESTS:
        if script=="data_healthcheck.py": continue
        p=_find(script)
        if not p: out[script]="SKIP(없음)"; continue
        try:
            r=subprocess.run([sys.executable,"-W","ignore",p]+([arg] if arg else []),
                             capture_output=True, text=True, timeout=120)
            txt=(r.stdout or "")+(r.stderr or "")
            ok = r.returncode==0
            # "셀프테스트: X/Y" 파싱
            mark="PASS" if ok else "FAIL"
            for line in txt.splitlines():
                if "셀프테스트" in line or "self-test" in line.lower():
                    mark=("PASS " if ok else "FAIL ")+line.strip().split(":")[-1].strip()
                    break
            out[script]=mark
        except Exception as e:
            out[script]=f"ERROR({e})"
    return out

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--asof")
    a=ap.parse_args()
    asof=a.asof or datetime.date.today().strftime("%Y-%m")
    print("="*74); print(f"프리플라이트 안전 게이트 · {datetime.datetime.now():%Y-%m-%d %H:%M} · 기준 {asof}"); print("="*74)

    print("\n[1] 데이터 헬스체크"); dv,detail=run_data_check(asof)

    # [1b] PIT 룩어헤드 감사(재무월이 가격월보다 미래면 FAIL → stale 취급)
    print("\n[1b] PIT 공시시차 감사"); pit_ok=True
    pp=_find("pit_lag.py")
    if pp:
        try:
            r=subprocess.run([sys.executable,"-W","ignore",pp,"--audit"],
                             capture_output=True,text=True,timeout=120)
            for ln in (r.stdout or "").splitlines():
                if "감사 종합" in ln or "룩어헤드" in ln or "시차" in ln: print("   "+ln.strip())
            pit_ok = (r.returncode==0)
        except Exception as e:
            print("   PIT 감사 오류(건너뜀):",e)
    else:
        print("   pit_lag.py 없음 — 스킵")

    print("\n[2] 모듈 셀프테스트"); st=run_selftests()
    for k,v in st.items(): print(f"   {k:<20} {v}")
    any_fail_test=any(str(v).startswith("FAIL") or "ERROR" in str(v) for v in st.values())

    # 종합: 데이터 FAIL 또는 PIT 룩어헤드면 중단(가장 위험). 셀프테스트 FAIL은 경고.
    stale = (dv=="FAIL" or dv=="ERROR" or dv=="MISSING" or not pit_ok)
    overall = "FAIL" if stale else ("WARN" if (dv=="WARN" or any_fail_test) else "PASS")
    icon={"PASS":"✅","WARN":"⚠️","FAIL":"❌"}.get(overall,"❓")
    print("\n"+"-"*74)
    print(f"프리플라이트 종합: {icon} {overall}  (데이터 {dv})")
    if stale: print("  ❌ 데이터 문제 → 추천·카톡 발송 중단 권고. (낡은/깨진 데이터로 매매 신호 금지)")
    elif overall=="WARN": print("  ⚠️ 진행 가능하나 경고 확인.")
    else: print("  ✅ 안전 — 파이프라인 진행 OK.")

    status=dict(ts=datetime.datetime.now().isoformat(timespec="seconds"), asof=asof,
                overall=overall, data=dv, stale=bool(stale), selftests=st)
    try:
        open(os.path.join(BASE,"preflight_status.json"),"w",encoding="utf-8").write(
            json.dumps(status,ensure_ascii=False,indent=2))
        print("  기록: preflight_status.json")
    except Exception: pass
    print("⚠️ 정보·검증용. 투자자문 아님·책임 본인.")
    sys.exit(1 if stale else 0)

if __name__=="__main__": main()
