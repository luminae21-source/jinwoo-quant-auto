# -*- coding: utf-8 -*-
"""연구보존_갱신.py — 색인·허브·백서를 한 번에 다시 만든다.

    python 연구보존_갱신.py            # 세 개 전부 갱신
    python 연구보존_갱신.py --check    # 아무것도 쓰지 않고 현황만 출력

왜 한 파일로 묶었나
    세 스크립트는 순서가 있다. 색인이 먼저 나와야 허브가 그걸 4번째 탭으로
    빨아들이고, 백서는 그 색인을 근거로 부록 B-3 을 다시 쓴다. 순서를 사람이
    기억해야 하면 결국 안 돌리게 되고, 안 돌리면 색인이 어느 날짜에 굳는다.
    굳은 색인은 없는 색인보다 나쁘다 — 최신인 척하기 때문이다.

무엇을 건드리지 않나
    연구 파일은 하나도 읽기만 한다. 옮기지도 지우지도 않는다.
    백서의 손으로 매긴 `부록 B-1 색인` 표도 손대지 않는다(대조만).
"""
import os
import subprocess
import sys
import time

# 작업스케줄러로 돌면 출력이 파일로 넘어가고, 윈도우 파이썬은 그때 cp949 를 쓴다.
# '—' 같은 글자 하나에 UnicodeEncodeError 로 죽는다. UTF-8 로 못 박는다.
for _s in (sys.stdout, sys.stderr):
    try:
        _s.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass
os.environ.setdefault("PYTHONUTF8", "1")
os.environ.setdefault("PYTHONIOENCODING", "utf-8")

HERE = os.path.dirname(os.path.abspath(__file__))
PY = sys.executable or "python"

# (표시이름, 스크립트, 추가인자, 결과물)
STEPS = [
    ("연구 색인", "연구색인_생성.py", [], "강화키트/진우퀀트_연구색인.html"),
    ("진우허브", "허브_자립형.py", [], "강화키트/진우퀀트_허브_자립형.html"),
    ("백서 부록 B-3", "백서_색인_갱신.py", [], "백서_빌더/진우퀀트_백서.md"),
]


def run(name, script, extra, out):
    path = os.path.join(HERE, script)
    if not os.path.exists(path):
        print("  ✗ %s — %s 없음" % (name, script))
        return False
    t0 = time.time()
    env = dict(os.environ, PYTHONUTF8="1", PYTHONIOENCODING="utf-8")
    r = subprocess.run([PY, path] + extra, cwd=HERE, env=env,
                       capture_output=True, text=True, encoding="utf-8",
                       errors="replace")
    body = (r.stdout or "").strip()
    for line in body.splitlines():
        print("     " + line)
    if r.returncode != 0:
        print("  ✗ %s 실패 (%.1fs)" % (name, time.time() - t0))
        err = (r.stderr or "").strip().splitlines()
        for line in err[-8:]:
            print("     ! " + line)
        return False
    op = os.path.join(HERE, out)
    size = "%.2f MB" % (os.path.getsize(op) / 1e6) if os.path.exists(op) else "결과물 없음"
    print("  ✓ %s — %s (%s · %.1fs)" % (name, out, size, time.time() - t0))
    return True


def main():
    check = "--check" in sys.argv
    print("연구보존 갱신 — %s" % time.strftime("%Y-%m-%d %H:%M"))
    print("근거: 연구는 지워져서 사라지지 않는다. 잊혀서 사라진다.")
    print("-" * 58)

    if check:
        # 쓰지 않는 경로만 골라 현황을 보여준다.
        sys.path.insert(0, HERE)
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "연구색인", os.path.join(HERE, "연구색인_생성.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        rows, nfiles = mod.collect(HERE)
        act = sum(1 for r in rows if r["state"] == "활성")
        rec = sum(1 for r in rows if r["state"] == "최근")
        dor = sum(1 for r in rows if r["state"] == "휴면")
        print("갈래 %d · 파일 %d" % (len(rows), nfiles))
        print("활성(7일내) %d · 최근(30일내) %d · 휴면(30일↑) %d" % (act, rec, dor))
        subprocess.run([PY, os.path.join(HERE, "백서_색인_갱신.py"), "--check"],
                       cwd=HERE)
        print("-" * 58)
        print("검사만 했다. 파일은 하나도 쓰지 않았다.")
        return 0

    ok = 0
    for name, script, extra, out in STEPS:
        if run(name, script, extra, out):
            ok += 1

    print("-" * 58)
    if ok == len(STEPS):
        print("✅ %d/%d 완료. 허브를 열어 '연구 색인' 탭을 확인하세요." % (ok, len(STEPS)))
        return 0
    print("⚠ %d/%d 성공. 실패한 단계는 위 로그를 보세요." % (ok, len(STEPS)))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
