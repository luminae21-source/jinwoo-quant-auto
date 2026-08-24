#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
경로자립화.py — 샌드박스 경로 하드코딩 제거 (§8-5b)

`/mnt/user-data/uploads/진우퀀트` · `/home/claude/...` 가 박힌 스크립트는 PC에서 못 돈다.
2026-07-27 기준 그런 파일이 64개. 백서의 핵심 검증 수치(배당 +3.4% · IC HAC t 4.10)를
만든 `mini_factor_adj.py`도 여기 포함 — **검증 근거를 재현할 수 없는 상태**였다.

하는 일 (파일당):
  1. `BASE=_jqroot2()` → 프로젝트 루트 자동탐색
  2. `_jqfind("<이름>.csv")` 리터럴 → `_jqfind("<이름>.csv")` (루트 재귀 탐색)
  3. 위 둘이 하나라도 있으면 파일 맨 앞(docstring 뒤)에 `_jqfind` 프리앰블 삽입
  4. 원본은 `<파일>.bak_경로자립화` 로 보존

사용:
    py 경로자립화.py --dry                 # 무엇이 바뀌는지만 출력
    py 경로자립화.py --dir 감사/미니샘플2      # 특정 폴더만
    py 경로자립화.py --all                 # 전체 (백업/패키지 폴더는 제외)

⚠️ 수정 후 반드시 `py 진우퀀트_게이트.py` 로 확인할 것.
"""
import os as _os2
def _jqroot2():
    """프로젝트 루트 자동탐색 (2026-07-27 §5b)."""
    d=_os2.path.dirname(_os2.path.abspath(__file__))
    for _ in range(5):
        if _os2.path.exists(_os2.path.join(d,"종목시총_30년.csv")): return d
        d=_os2.path.dirname(d)
    return _os2.path.dirname(_os2.path.abspath(__file__))


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

try:  # 윈도 파이프(cp949)에서 이모지 출력 시 UnicodeEncodeError 방지 (2026-07-27)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse
import os
import re
import shutil
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
SKIP_DIRS = {"_백업", "_보관", "_archive", "__pycache__", ".git", "_cowork_run",
             "_to_delete", "_bat_encoding_backup_2026-07-09"}

PREAMBLE = '''
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
'''

RE_BASE = re.compile(r'^BASE\s*=\s*["\']/mnt/user-data/uploads/[^"\']*["\'].*$', re.M)
RE_SANDBOX_LIT = re.compile(r'["\'](/(?:home/claude|mnt/user-data)/[^"\']*?/([^/"\']+\.(?:csv|json|txt|md)))["\']')
RE_ANY_SANDBOX = re.compile(r'["\']/(?:home/claude|mnt/user-data)')


def split_header(src):
    """모듈 docstring / 인코딩선언 뒤 삽입 위치를 찾는다."""
    lines = src.split("\n")
    i = 0
    while i < len(lines) and (lines[i].startswith("#!") or "coding" in lines[i][:30]):
        i += 1
    rest = "\n".join(lines[i:]).lstrip()
    for q in ('r"""', "r'''", '"""', "'''"):
        if rest.startswith(q):
            qq = q[-3:]
            end = rest.find(qq, len(q))
            if end != -1:
                consumed = rest[:end + 3]
                pos = src.find(consumed) + len(consumed)
                return src[:pos], src[pos:]
    pos = sum(len(l) + 1 for l in lines[:i])
    return src[:pos], src[pos:]


def patch(path, dry=False):
    src = open(path, encoding="utf-8", errors="replace").read()
    if not RE_ANY_SANDBOX.search(src):
        return None
    body = src
    notes = []

    n_base = len(RE_BASE.findall(body))
    if n_base:
        body = RE_BASE.sub("# BASE는 아래 프리앰블에서 자동 결정 (경로자립화 2026-07-27)", body)
        notes.append(f"BASE {n_base}건")

    lits = RE_SANDBOX_LIT.findall(body)
    if lits:
        body = RE_SANDBOX_LIT.sub(lambda m: f'_jqfind("{m.group(2)}")', body)
        notes.append("리터럴 " + ", ".join(sorted({b for _, b in lits})))

    head, tail = split_header(body)
    body = head + "\n" + PREAMBLE + tail

    left = RE_ANY_SANDBOX.findall(body)
    if left:
        notes.append(f"⚠️ 잔존 {len(left)}건 — 수동 확인 필요")

    if not dry:
        shutil.copy2(path, path + ".bak_경로자립화")
        open(path, "w", encoding="utf-8").write(body)
    return " · ".join(notes) or "프리앰블만"


def collect(target):
    out = []
    for dp, dn, fn in os.walk(target):
        dn[:] = [d for d in dn if d not in SKIP_DIRS]
        out += [os.path.join(dp, f) for f in fn if f.endswith(".py")]
    return sorted(out)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", default=None, help="대상 폴더 (기본: 미니샘플 계열)")
    ap.add_argument("--all", action="store_true", help="루트 전체")
    ap.add_argument("--dry", action="store_true")
    a = ap.parse_args()

    if a.all:
        targets = collect(ROOT)
    elif a.dir:
        targets = collect(os.path.join(ROOT, a.dir))
    else:
        targets = (collect(os.path.join(ROOT, "감사", "미니샘플"))
                   + collect(os.path.join(ROOT, "감사", "미니샘플2"))
                   + collect(os.path.join(ROOT, "강화키트", "미니샘플")))

    print("=" * 74)
    print(f" 경로 자립화{' [DRY RUN]' if a.dry else ''} · 대상 {len(targets)}개")
    print("=" * 74)
    n = 0
    for p in targets:
        if ".bak" in p:
            continue
        r = patch(p, dry=a.dry)
        if r:
            n += 1
            print(f"  {'확인' if a.dry else '수정'}: {os.path.relpath(p, ROOT)}")
            print(f"        {r}")
    print("-" * 74)
    print(f"  {'대상' if a.dry else '수정 완료'} {n}개" + ("" if a.dry else " (원본 .bak_경로자립화 보존)"))
    if not a.dry and n:
        print("  → 반드시 `py 진우퀀트_게이트.py` 로 확인할 것.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
