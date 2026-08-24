# -*- coding: utf-8 -*-
r"""pykrx_진단.py — KRX 로그인 실패 원인을 찾고, 익명 모드가 되는지 시험한다. (2026-08-20)

배경: pykrx 는 `import pykrx` 시점에 KRX 로그인을 시도한다(webio.py 의 build_krx_session).
      KRX 가 JSON 대신 HTML 을 돌려주면서 **모든 pykrx 스크립트가 import 에서 죽는다.**
      로그인 없이도 get_market_fundamental 은 되므로, 로그인만 끄면 살아난다.

이 스크립트는 pykrx 를 **import 하지 않고** 소스만 읽어서 로그인 정보 출처를 찾는다.
그 다음 환경변수를 비운 상태로 import 를 시험한다.

⚠️ 비밀번호·아이디 값은 절대 출력하지 않는다. 있음/없음과 길이만 본다.

    py 정리\pykrx_진단.py
"""
import os, re, io, sys, importlib.util, subprocess

print("=" * 60)
print(" pykrx 로그인 진단")
print("=" * 60)

# ── 1. pykrx 위치 (import 하지 않는다)
spec = importlib.util.find_spec("pykrx")
if spec is None or not spec.submodule_search_locations:
    sys.exit("pykrx 를 못 찾음. py -m pip install pykrx")
pkg = list(spec.submodule_search_locations)[0]
print("\n[1] pykrx 경로")
print("   ", pkg)
try:
    v = subprocess.run([sys.executable, "-m", "pip", "show", "pykrx"],
                       capture_output=True, text=True, timeout=30).stdout
    for line in v.splitlines():
        if line.lower().startswith("version"):
            print("   ", line.strip())
except Exception as e:
    print("    버전 확인 실패:", e)

# ── 2. auth.py 에서 로그인 정보 출처 찾기 (소스만 읽음)
auth = os.path.join(pkg, "website", "comm", "auth.py")
print("\n[2] 로그인 정보를 어디서 읽나  (%s)" % ("있음" if os.path.exists(auth) else "auth.py 없음"))
src = ""
if os.path.exists(auth):
    src = io.open(auth, encoding="utf-8", errors="replace").read()
    hits = [l.strip() for l in src.splitlines()
            if re.search(r"environ|getenv|login_id\s*=|login_pw\s*=|\.pykrx|config|json\.load|open\(", l)
            and not l.strip().startswith("#")]
    for l in hits[:18]:
        print("   ", l[:110])
    if not hits:
        print("    (해당 줄 없음)")

# ── 3. 환경변수 (값은 안 찍는다)
print("\n[3] KRX 관련 환경변수")
found_env = [k for k in os.environ if "KRX" in k.upper()]
for k in found_env:
    print("    %s = (설정됨, %d자)" % (k, len(os.environ[k])))
if not found_env:
    print("    (없음)")

# ── 4. 설정 파일 후보
print("\n[4] 설정 파일 후보")
cands = [os.path.expanduser("~/.pykrx"), os.path.expanduser("~/.pykrx.json"),
         os.path.join(pkg, "krx.json"), os.path.join(pkg, "website", "comm", "krx.json"),
         os.path.expanduser("~/pykrx.json")]
for m in re.findall(r'["\']([^"\']*\.(?:json|ini|cfg|txt))["\']', src or ""):
    p = m if os.path.isabs(m) else os.path.join(pkg, "website", "comm", m)
    cands.append(p)
seen = set(); anyf = False
for c in cands:
    if c in seen:
        continue
    seen.add(c)
    if os.path.exists(c):
        print("    있음: %s (%d bytes)" % (c, os.path.getsize(c)))
        anyf = True
if not anyf:
    print("    (없음)")

# ── 5. 익명 모드 시험 — 환경변수 비우고 별도 프로세스에서 import
print("\n[5] 로그인 없이 import 되는지 시험")
env = {k: v for k, v in os.environ.items() if "KRX" not in k.upper()}
code = ("from pykrx import stock;"
        "d=stock.get_market_fundamental('20260731', market='KOSPI');"
        "print('OK rows=%d' % len(d))")
try:
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True,
                       timeout=180, env=env)
    out = (r.stdout or "").strip()
    err = (r.stderr or "").strip()
    if r.returncode == 0 and out.startswith("OK"):
        print("    ✅ 성공 —", out)
        print("    → 로그인 정보만 치우면 정상 동작한다.")
    else:
        print("    ❌ 실패 (returncode %s)" % r.returncode)
        tail = [l for l in err.splitlines() if l.strip()][-4:]
        for l in tail:
            print("      ", l[:110])
except subprocess.TimeoutExpired:
    print("    시간 초과(3분) — 네트워크 지연")
except Exception as e:
    print("    시험 실패:", e)

print("\n" + "=" * 60)
print(" 이 출력을 그대로 붙여주세요. 값(비밀번호·ID)은 안 나옵니다.")
