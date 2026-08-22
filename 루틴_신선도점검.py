# -*- coding: utf-8 -*-
"""루틴 신선도 점검 — 자동화가 실제로 돌고 있는지 감시 (2026-08-22)
사고: 엔진02 멀티팩터 월초 루틴이 2026-06 이후 2개월 중단됐는데 아무도 몰랐다.
     "기억해서 돌리기"는 실패했다. → 산출물 나이를 기계가 본다.
실행: py 루틴_신선도점검.py          (사람이 볼 때)
      py 루틴_신선도점검.py --json   (주간 자동화가 읽을 때)
반환코드: 0 정상 / 1 경고(하나라도 stale)
"""
import argparse, json, os, sys
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
# (파일, 허용 나이(일), 설명, 복구 명령)
WATCH = [
    ("v37_2_scores_latest.csv", 35, "엔진02 멀티팩터 월초 점수", "py score_v37_2.py"),
    ("가상매매_원장.csv",        10, "가상매매 전진검증 원장",     "py 가상매매.py"),
    ("서킷상태.json",            10, "서킷브레이커 점검",         "py 서킷브레이커_점검.py"),
    ("eps_sue_cache.json",      100, "DART 실적 캐시(분기)",      "py fetch_dart_eps.py"),
]

def check():
    now = datetime.now(); out = []
    for fn, max_age, desc, cmd in WATCH:
        p = os.path.join(HERE, fn)
        if not os.path.exists(p):
            out.append({"file": fn, "desc": desc, "status": "MISSING", "age_days": None, "fix": cmd}); continue
        age = (now - datetime.fromtimestamp(os.path.getmtime(p))).days
        st = "STALE" if age > max_age else "OK"
        out.append({"file": fn, "desc": desc, "status": st, "age_days": age,
                    "max_age": max_age, "fix": cmd})
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--json", action="store_true")
    a = ap.parse_args(); rows = check()
    bad = [r for r in rows if r["status"] != "OK"]
    if a.json:
        print(json.dumps({"checked": datetime.now().isoformat(), "rows": rows,
                          "alert": bool(bad)}, ensure_ascii=False))
    else:
        print("=== 루틴 신선도 점검 ===")
        for r in rows:
            mark = "OK " if r["status"] == "OK" else "!! "
            age = "없음" if r["age_days"] is None else f"{r['age_days']}일"
            print(f" {mark}{r['desc']:24s} {age:>6s} (허용 {r.get('max_age','-')}일)  {r['file']}")
        if bad:
            print("\n[조치 필요]")
            for r in bad: print(f"  {r['desc']}: {r['fix']}")
        else:
            print("\n전부 정상 — 자동화가 돌고 있다.")
    sys.exit(1 if bad else 0)

if __name__ == "__main__":
    main()
