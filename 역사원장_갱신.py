# -*- coding: utf-8 -*-
r"""역사원장_갱신.py — 30년 역사원장 전체 재생성 래퍼 (⏱ 10~25분 소요)

순서: ① 휩쏘_역사검정.py --markets KOSPI  ② --markets KOSDAQ  ③ 휩쏘_역사원장.py
데이터가 갱신됐을 때(월 1회 정도) 실행하면 역사원장 2,801건+가 최신 데이터로 다시 만들어진다.
⚠️ 대용량 30년 CSV를 두 번 읽는다 — 실행 중 PC가 느려질 수 있음.
"""
import os, sys, time, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

STEPS = [
    ("① 30년 검정 KOSPI", ["휩쏘_역사검정.py", "--markets", "KOSPI"]),
    ("② 30년 검정 KOSDAQ", ["휩쏘_역사검정.py", "--markets", "KOSDAQ"]),
    ("③ 역사원장 재생성", ["휩쏘_역사원장.py"]),
]

def main():
    t0 = time.time()
    env = dict(os.environ, PYTHONIOENCODING="utf-8")
    for name, cmd in STEPS:
        sp = os.path.join(HERE, cmd[0])
        if not os.path.exists(sp):
            print(f"  ✗ {name}: {cmd[0]} 없음 — 중단"); return 1
        print(f"\n{'='*70}\n {name} 실행 중… (수 분 소요)\n{'='*70}", flush=True)
        r = subprocess.run([sys.executable, sp] + cmd[1:], cwd=HERE, env=env)
        if r.returncode != 0:
            print(f"  ✗ {name} 실패(코드 {r.returncode}) — 중단. 기존 역사원장은 그대로다."); return r.returncode
    print(f"\n✅ 역사원장 갱신 완료 — 총 {(time.time()-t0)/60:.1f}분. 휩쏘_역사원장.html 을 열어 확인.")
    return 0

if __name__ == "__main__":
    sys.exit(main())
