# -*- coding: utf-8 -*-
r"""
검증_회귀.py — "스크립트를 고쳤는데 예전 숫자가 그대로인가?" 를 PASS/FAIL 로 답한다.
(2026-08-08)

왜 이게 필요한가
---------------
2026-08-08 하루에 `운용사양_백테.py` 를 네 번 고쳤다:
  ① --price / --mask 추가   ② 짝지은 초과수익 검정 추가
  ③ --panel 추가            ④ 결과파일에 출처 도장 추가
전부 "덧붙이는" 변경이라고 주장했지만, **주장은 증거가 아니다.**
이 스크립트는 저장된 결과와 같은 명령을 지금 코드로 다시 돌려서
**표 안의 숫자가 하나도 안 바뀌었는지** 확인한다.

바이트 비교가 아니라 **숫자 비교**를 한다. 헤더·도장·경로 같은 겉모습은 바뀌어도 되고,
바뀌면 안 되는 건 숫자다.

쓰는 법 (진우퀀트 폴더에서)
    py 검증_회귀.py --only 2008_kis_masked     # 한 칸만 (빠름)
    py 검증_회귀.py                            # 6칸 전부 (시간 걸림)
    py 검증_회귀.py --selftest
"""
import argparse, glob, io, os, re, subprocess, sys

ROOT = os.path.dirname(os.path.abspath(__file__))
MASKS = ["--mask", r"데이터수리\_패널마스크_v1.csv", "--mask", r"데이터수리\_출처불일치_v1.csv"]

CELLS = [
    dict(tag="2008_full",       start="2008-01", price="full", mask=False, panel="panel_cache.csv"),
    dict(tag="2008_kis",        start="2008-01", price="kis",  mask=False, panel="panel_kis.csv"),
    dict(tag="2008_kis_masked", start="2008-01", price="kis",  mask=True,  panel="panel_kis_masked.csv"),
    dict(tag="2010_full",       start="2010-01", price="full", mask=False, panel="panel_cache.csv"),
    dict(tag="2010_kis",        start="2010-01", price="kis",  mask=False, panel="panel_kis.csv"),
    dict(tag="2010_kis_masked", start="2010-01", price="kis",  mask=True,  panel="panel_kis_masked.csv"),
]

NUM = re.compile(r"-?\d+\.\d+")


def numbers(text):
    """표 행(| 로 시작)에서만 숫자를 뽑는다. 헤더·도장·산문은 무시."""
    out = []
    for line in text.splitlines():
        s = line.strip()
        if s.startswith("|") and not set(s) <= set("|-: "):
            out.extend(NUM.findall(s))
    return out


def latest_dir():
    ds = [d for d in glob.glob(os.path.join(ROOT, "이중창_*"))
          if os.path.isdir(d) and re.match(r"^이중창_\d{8}_\d{4}$", os.path.basename(d))]
    return sorted(ds)[-1] if ds else None


def run_cell(c, base, outdir, boot):
    out = os.path.join(outdir, "재현_%s.md" % c["tag"])
    args = [sys.executable, os.path.join(ROOT, "운용사양_백테.py"),
            "--start", c["start"], "--price", c["price"],
            "--signal", "multifactor", "--seed", "20260727",
            "--boot", str(boot), "--out", out,
            # --no-paired: 2026-08-10 패치부터 md 에 짝지은 표가 추가된다.
            # 옛 저장본에는 그 표가 없으므로, 재현 시 꺼야 숫자 목록이 1:1 로 맞는다.
            "--no-paired",
            "--panel", os.path.join(base, c["panel"])]
    if c["mask"]:
        args += MASKS
    # encoding 명시 (2026-08-08): Windows 콘솔(cp949)에서 자식의 UTF-8 출력을
    # 그대로 읽으면 리더 스레드가 UnicodeDecodeError 로 죽는다. 판정은 파일 비교라
    # 영향이 없었지만, 진짜 stderr 를 가릴 수 있어서 고정한다.
    r = subprocess.run(args, cwd=ROOT, capture_output=True, text=True,
                       encoding="utf-8", errors="replace")
    return out, r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--only", default=None, help="칸 태그 하나만")
    ap.add_argument("--dir", default=None, help="비교 대상 결과 폴더 (기본: 최신)")
    ap.add_argument("--boot", type=int, default=200, help="저장본과 같아야 한다 (기본 200)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())

    base = a.dir or latest_dir()
    if not base:
        sys.exit("⛔ 비교할 이중창_* 결과 폴더가 없습니다.")
    outdir = os.path.join(ROOT, "_회귀")
    os.makedirs(outdir, exist_ok=True)
    print("=" * 70)
    print(" 회귀 검증 — 저장본 vs 지금 코드")
    print(" 저장본 폴더: %s" % os.path.basename(base))
    print("=" * 70)

    cells = [c for c in CELLS if a.only is None or c["tag"] == a.only]
    if not cells:
        sys.exit("⛔ 그런 태그 없음: %s (가능: %s)" % (a.only, ", ".join(c["tag"] for c in CELLS)))

    fails = 0
    for c in cells:
        saved = os.path.join(base, "결과_%s.md" % c["tag"])
        if not os.path.exists(saved):
            print("  ⚠️ %-18s 저장본 없음 — 건너뜀" % c["tag"]); continue
        pan = os.path.join(base, c["panel"])
        if not os.path.exists(pan):
            print("  ⚠️ %-18s 신호패널 없음(%s) — 건너뜀" % (c["tag"], c["panel"])); continue

        print("  %-18s 재현 중..." % c["tag"], end="", flush=True)
        newf, r = run_cell(c, base, outdir, a.boot)
        if r.returncode != 0 or not os.path.exists(newf):
            print(" ⛔ 실행 실패")
            print("     " + (r.stderr or "").strip().splitlines()[-1:][0] if r.stderr else "")
            fails += 1; continue

        A = numbers(io.open(saved, encoding="utf-8").read())
        B = numbers(io.open(newf, encoding="utf-8").read())
        if A == B:
            print(" ✓ PASS (숫자 %d개 전부 일치)" % len(A))
        else:
            fails += 1
            print(" ✗ FAIL")
            print("     저장본 숫자 %d개 / 재현 %d개" % (len(A), len(B)))
            for i, (x, y) in enumerate(zip(A, B)):
                if x != y:
                    print("     첫 불일치 %d번째: 저장본 %s → 재현 %s" % (i + 1, x, y)); break

    print("-" * 70)
    if fails == 0:
        print("  ✅ 전부 PASS — 오늘의 코드 변경은 숫자를 바꾸지 않았습니다.")
        print("     저장된 결과와 백서 B-1q 의 숫자를 계속 믿어도 됩니다.")
    else:
        print("  ⛔ %d 칸 FAIL — 숫자가 바뀌었습니다." % fails)
        print("     백서 B-1q 를 인용하기 전에 원인을 찾아야 합니다.")
        print("     비교용 백업: 운용사양_백테.py.bak_0808_짝지은검정")
    sys.exit(1 if fails else 0)


def selftest():
    ok = []
    def t(n, c): ok.append((n, bool(c)))
    t("① 표 행에서 숫자 추출", numbers("| 30 | 8.9% | **6.8%** |") == ["8.9", "6.8"])
    t("② 산문은 무시", numbers("구간 2008-01 ~ 2026-06 (222개월) 비용 0.559%") == [])
    t("③ 구분선 무시", numbers("|---|---|---|") == [])
    t("④ 음수 처리", numbers("| 5 | -1.1% | 4.3% |") == ["-1.1", "4.3"])
    t("⑤ 도장 블록 무시", numbers("생성기 md5    884a9826b517370c361a6e24e12f37f9") == [])
    t("⑥ 정수만 있는 칸은 안 잡음(N=30)", "30" not in numbers("| 30 | 8.9% |"))
    t("⑦ 헤더행 무시", numbers("| N | 5% | 중앙 |") == [])
    t("⑧ 칸 태그 6개", len(CELLS) == 6 and len({c["tag"] for c in CELLS}) == 6)
    t("⑨ 태그별 패널 지정됨", all(c["panel"].endswith(".csv") for c in CELLS))
    ld = latest_dir()
    t("⑩ 최신 폴더 탐색", ld is None or os.path.isdir(ld))
    n = sum(1 for _, b in ok if b)
    for name, b in ok: print(("  ✓ " if b else "  ✗ ") + name)
    print("자가검사 %d/%d %s" % (n, len(ok), "PASS" if n == len(ok) else "FAIL"))
    return 0 if n == len(ok) else 1


if __name__ == "__main__":
    main()
