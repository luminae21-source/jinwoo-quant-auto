# -*- coding: utf-8 -*-
r"""산출물_수거.py — 날짜 붙은 생성물을 산출물\YYYY-MM\ 으로 옮긴다. (2026-08-20)

왜: 최근 45일 안에 수정된 파일 759개가 어디에도 안 걸려 있다(전체스캔 실측).
    bat 런처 123개가 매일 파일을 뱉는데 수거하는 사람이 없어서 루트가 부푼다.
    지우지 않는다. **옮기기만** 한다.

안전장치 (하나라도 걸리면 안 옮긴다):
    1) 이름에 날짜(YYYYMMDD / YYYY-MM-DD)가 있어야 한다
    2) KEEP 일수보다 오래돼야 한다 (기본 30일 — 최근 것은 아직 쓰는 중일 수 있다)
    3) 이름에 최신/현황/정본/_full 이 들어가면 제외 (덮어쓰기용 고정 이름)
    4) **코드가 glob 으로 훑는 패턴에 걸리면 제외** — 예: 진우퀀트_앱.py 가
       휩쏘탐지_*.csv 를 최신순으로 읽는다. 옮기면 앱이 깨진다
    5) 허브/앱/문서에서 이름으로 참조되면 제외

기본은 **미리보기**다. 실제로 옮기려면 --apply 를 준다.

    py 정리\산출물_수거.py              # 미리보기 (아무것도 안 옮김)
    py 정리\산출물_수거.py --apply      # 실제 이동
    py 정리\산출물_수거.py --selftest
"""
import os, re, io, sys, fnmatch, shutil, time, argparse, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEST = os.path.join(ROOT, "산출물")
SKIPDIR = ("_백업", "_to_delete", "_보관", "_archive", "__pycache__", "__jqpyc__",
           ".git", "_stage_tmp", "_stagetmp", "산출물", "감사", "정리", "docs",
           "증명된_규칙", "백서_빌더")
KEEPNAME = re.compile(r"최신|현황|정본|_full|template|example|README")
DATE = re.compile(r"(20\d{6}|20\d{2}-\d{2}-\d{2})")
EXT = {".html", ".md", ".csv", ".json", ".txt", ".tsv"}


def _walk(want_py=False):
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if d not in SKIPDIR and not d.startswith("_stagetmp")]
        for fn in fns:
            if want_py and fn.endswith(".py"):
                yield dp, fn
            elif not want_py:
                yield dp, fn


def live_globs():
    """코드가 glob 으로 훑는 패턴 — 여기 걸리는 파일은 건드리지 않는다."""
    pats = set()
    for dp, fn in _walk(want_py=True):
        try:
            s = io.open(os.path.join(dp, fn), encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        for m in re.findall(r'["\']([^"\']*\*[^"\']*\.(?:csv|html|md|json|txt|tsv))["\']', s):
            pats.add(os.path.basename(m))
    return pats


def referenced():
    """허브·앱·핵심문서가 이름으로 부르는 파일."""
    names = set()
    for rel in ("강화키트/진우퀀트_허브.html", "진우퀀트_앱.py", "jq_console.py",
                "강화키트/jq_hub.py", "백서_빌더/진우퀀트_백서.md",
                "데이터수리/수정주가_재수집_런북.md", "진우퀀트_휩쏘_인수인계.md"):
        p = os.path.join(ROOT, rel)
        if not os.path.exists(p):
            continue
        try:
            s = io.open(p, encoding="utf-8", errors="replace").read()
        except Exception:
            continue
        names |= {os.path.basename(x) for x in
                  re.findall(r"[\w가-힣._\-]+\.(?:html|md|csv|json|txt|tsv)", s)}
    return names


def plan(keep_days=30):
    pats, refs, now = live_globs(), referenced(), time.time()
    moves, held = [], collections.Counter()
    for dp, fn in _walk():
        if os.path.splitext(fn)[1].lower() not in EXT:
            continue
        m = DATE.search(fn)
        if not m:
            held["날짜 없음"] += 1; continue
        if KEEPNAME.search(fn):
            held["고정 이름"] += 1; continue
        src = os.path.join(dp, fn)
        try:
            age = (now - os.path.getmtime(src)) / 86400
        except OSError:
            continue
        if age < keep_days:
            held["최근 %d일" % keep_days] += 1; continue
        if any(fnmatch.fnmatch(fn, p) for p in pats):
            held["코드가 훑는 패턴"] += 1; continue
        if fn in refs:
            held["문서가 참조"] += 1; continue
        d = m.group(1)
        ym = (d[:4] + "-" + d[4:6]) if len(d) == 8 else d[:7]
        moves.append((src, os.path.join(DEST, ym, fn)))
    return moves, held, len(pats), len(refs)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true", help="실제로 옮긴다 (기본은 미리보기)")
    ap.add_argument("--keep-days", type=int, default=30)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())

    moves, held, npat, nref = plan(a.keep_days)
    print("=" * 60)
    print(" 산출물 수거 %s" % ("[실행]" if a.apply else "[미리보기 — 아무것도 안 옮깁니다]"))
    print("=" * 60)
    print("  보호: glob 패턴 %d개 · 문서 참조 %d개 · 최근 %d일 · 고정이름"
          % (npat, nref, a.keep_days))
    print("\n  [옮기지 않는 이유별]")
    for k, v in held.most_common():
        print("    %-18s %5d" % (k, v))
    print("\n  옮길 대상: %d개" % len(moves))
    c = collections.Counter(os.path.basename(os.path.dirname(d)) for _, d in moves)
    for k, v in sorted(c.items()):
        print("    산출물\\%s   %d개" % (k, v))
    if moves:
        print("\n  예시 10개:")
        for s, d in moves[:10]:
            print("    %s" % os.path.relpath(s, ROOT))
    if not a.apply:
        print("\n  → 실제로 옮기려면: py 정리\\산출물_수거.py --apply")
        return
    ok = fail = 0
    log = io.open(os.path.join(ROOT, "정리", "_수거로그.txt"), "a", encoding="utf-8")
    log.write("\n=== %s · %d건 시도 ===\n" % (time.strftime("%Y-%m-%d %H:%M"), len(moves)))
    for s, d in moves:
        try:
            os.makedirs(os.path.dirname(d), exist_ok=True)
            if os.path.exists(d):
                fail += 1; log.write("SKIP(중복) %s\n" % os.path.relpath(s, ROOT)); continue
            shutil.move(s, d)
            log.write("%s -> %s\n" % (os.path.relpath(s, ROOT), os.path.relpath(d, ROOT)))
            ok += 1
        except Exception as e:
            fail += 1
            log.write("FAIL %s : %s\n" % (os.path.relpath(s, ROOT), e))
    log.close()
    print("\n  옮김 %d · 실패/중복 %d · 로그: 정리\\_수거로그.txt" % (ok, fail))


def selftest():
    ok = []
    def t(n, c): ok.append((n, bool(c)))
    t("1 날짜 8자리 인식", bool(DATE.search("시장브리핑_20260820.md")))
    t("2 날짜 하이픈 인식", bool(DATE.search("주봉분석_2026-08-20.md")))
    t("3 날짜 없으면 대상 아님", not DATE.search("시장브리핑_최신.html"))
    t("4 최신 보호", bool(KEEPNAME.search("익일예측_최신.html")))
    t("5 현황 보호", bool(KEEPNAME.search("진우사냥터_현황판.html")))
    t("6 일반 파일은 통과", not KEEPNAME.search("오늘_급등_20260820.md"))
    m, h, np_, nr = plan(99999)
    t("7 keep 무한대면 0건", len(m) == 0)
    t("8 glob 패턴 수집됨", np_ > 0)
    t("9 문서 참조 수집됨", nr > 0)
    m2, _, _, _ = plan(30)
    t("10 목적지는 전부 산출물\\ 아래",
      all(os.path.abspath(d).startswith(os.path.abspath(DEST)) for _, d in m2))
    t("11 원본은 전부 ROOT 안",
      all(os.path.abspath(s).startswith(os.path.abspath(ROOT)) for s, _ in m2))
    t("12 휩쏘탐지_*(앱이 glob) 제외",
      not any(os.path.basename(s).startswith("휩쏘탐지_") for s, _ in m2))
    t("13 백서_빌더 건드리지 않음",
      not any(os.sep + "백서_빌더" + os.sep in s for s, _ in m2))
    t("14 증명된_규칙 건드리지 않음",
      not any(os.sep + "증명된_규칙" + os.sep in s for s, _ in m2))
    n = sum(1 for _, c in ok if c)
    for name, c in ok:
        print(("  ✓ " if c else "  ✗ ") + name)
    print("자가검사 %d/%d %s" % (n, len(ok), "PASS" if n == len(ok) else "FAIL"))
    return 0 if n == len(ok) else 1


if __name__ == "__main__":
    main()
