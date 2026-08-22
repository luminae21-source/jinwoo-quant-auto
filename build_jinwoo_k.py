# -*- coding: utf-8 -*-
"""진우퀀트+K exe 빌드 스크립트 — 빌드_진우퀀트K.bat 가 이 파일을 실행한다."""
import os, sys, shutil, subprocess
HERE = os.path.dirname(os.path.abspath(__file__))
os.chdir(HERE)

def run(cmd):
    print(">", " ".join(cmd), flush=True)
    return subprocess.call(cmd)

print("=" * 50)
print(" 진우퀀트+K  exe 빌드 (최초 1회, 수 분 소요)")
print("=" * 50)

# 실행 중인 진우퀀트+K 를 먼저 자동 종료 (안 그러면 파일이 잠겨 빌드 실패)
subprocess.call(["taskkill", "/F", "/IM", "진우퀀트+K.exe"],
                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
import time; time.sleep(1)

# PyInstaller 설치 확인
if subprocess.call([sys.executable, "-m", "pip", "show", "pyinstaller"],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL) != 0:
    print("PyInstaller 설치 중...")
    if run([sys.executable, "-m", "pip", "install", "pyinstaller"]) != 0:
        sys.exit("설치 실패 — 인터넷 연결을 확인하세요.")

app = os.path.join(HERE, "진우퀀트_앱.py")
ico = os.path.join(HERE, "진우퀀트아이콘.ico")
if not os.path.exists(app): sys.exit("진우퀀트_앱.py 가 이 폴더에 없습니다.")
args = [sys.executable, "-m", "PyInstaller", "--noconfirm", "--onefile",
        "--name", "진우퀀트+K", app]
if os.path.exists(ico): args[args.index(app):args.index(app)] = ["--icon", ico]

if run(args) != 0:
    sys.exit("빌드 실패 — 위 오류 메시지를 확인하세요.")

src = os.path.join(HERE, "dist", "진우퀀트+K.exe")
dst = os.path.join(HERE, "진우퀀트+K.exe")
if os.path.exists(src):
    try:
        shutil.copy2(src, dst)
    except PermissionError:
        sys.exit("\n❌ 진우퀀트+K.exe 가 실행 중이라 교체하지 못했습니다.\n"
                 "   → 실행 중인 진우퀀트+K 창을 모두 닫고, 이 빌드를 다시 실행하세요.")
    # 헷갈림 방지: 빌드 부산물(dist·build·spec)은 정리 — 진짜 exe는 폴더에 하나만 남긴다
    for junk in ("dist", "build"):
        shutil.rmtree(os.path.join(HERE, junk), ignore_errors=True)
    try: os.remove(os.path.join(HERE, "진우퀀트+K.spec"))
    except OSError: pass
    print()
    print("✅ 완료! 이 폴더의 [진우퀀트+K.exe] 를 더블클릭하면 앱이 실행됩니다.")
    print("   (dist·build 임시 폴더는 자동 정리했습니다 — exe는 이 폴더에 하나뿐)")
    print("   바탕화면에 바로가기를 만들어 두면 편합니다.")
    print("   (처음 실행 때 백신이 물어보면 '허용' — 새로 만든 exe라 그렇습니다)")
else:
    print("빌드 산출물을 찾지 못했습니다 — dist 폴더를 확인하세요.")
