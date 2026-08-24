#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
patch_r2.py — `유니버스_규칙화_검정.py`에 R2 실행 옵션을 붙인다.

목적: **원 규칙을 그대로 두고 한 번에 한 변수만 바꾼다.**
      7/27 세션은 규칙·기간·데이터·대조군 네 축을 동시에 바꿔 귀속이 불가능했다.

추가 옵션:
  --start YYYY-MM   백테 시작 (기본 없음 = 전체)
  --end   YYYY-MM   백테 종료
  --adjusted PATH   조정본 월봉 디렉토리 (파일명 규칙: _월봉종가캐시_조정_KOSPI.csv 등)
  --label TEXT      결과 라벨 (출력·저장 파일명에 부착)

3단계 분해:
  R0  py 유니버스_규칙화_검정.py --label R0
      → 원 규칙·1996~2026·미조정. **20.1%가 재현되는지 = 코드 무결성**
  R1  py 유니버스_규칙화_검정.py --start 2015-01 --label R1
      → 기간만 축소. 20.1%의 얼마가 기간 효과인지
  R2  py 유니버스_규칙화_검정.py --start 2015-01 --adjusted ..\데이터수리 --label R2
      → 데이터까지 조정본. **이것이 7/27이 했어야 할 실험**

전 단계에서 대조군 TOP30_고정(동일가중)을 함께 출력한다 — KOSPI는 참고용.

사용:
  python patch_r2.py --target "강화키트\유니버스_규칙화_검정.py"
  (원본은 .bak 으로 백업)
"""
import argparse, re, shutil, sys
from pathlib import Path

PATCH_ARGS = '''
# ── R2 패치 (2026-07-27): 기간·데이터 분해 실행 ──────────────────────
import argparse as _ap
_p = _ap.ArgumentParser(add_help=False)
_p.add_argument("--start", default=None, help="YYYY-MM")
_p.add_argument("--end", default=None, help="YYYY-MM")
_p.add_argument("--adjusted", default=None, help="조정본 월봉 디렉토리")
_p.add_argument("--label", default="R0")
_R2ARGS, _ = _p.parse_known_args()


def _r2_window(df):
    """--start/--end 로 인덱스(ym) 구간 자르기"""
    if _R2ARGS.start:
        df = df[df.index >= _R2ARGS.start]
    if _R2ARGS.end:
        df = df[df.index <= _R2ARGS.end]
    return df


def _r2_adjusted_name(fn):
    """조정본 파일명 매핑: _월봉종가캐시_KOSPI.csv → _월봉종가캐시_조정_KOSPI.csv"""
    if not _R2ARGS.adjusted:
        return None
    import os
    cand = fn.replace("_월봉종가캐시_", "_월봉종가캐시_조정_")
    for name in (cand, fn):
        p = os.path.join(_R2ARGS.adjusted, name)
        if os.path.exists(p):
            return p
    return None
# ── R2 패치 끝 ──────────────────────────────────────────────────────
'''

PATCH_LOAD = '''    # R2: 조정본 우선 탐색
    _adj = _r2_adjusted_name(fn)
    if _adj:
        p = _adj
'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--target", required=True)
    a = ap.parse_args()
    t = Path(a.target)
    if not t.exists():
        sys.exit(f"대상 없음: {t}")

    src = t.read_text(encoding="utf-8")
    if "R2 패치" in src:
        sys.exit("이미 패치됨. 되돌리려면 .bak 복원.")

    shutil.copy2(t, t.with_suffix(t.suffix + ".bak"))

    # 1) 인자 블록을 import 직후에 삽입
    m = re.search(r"^import .*$", src, flags=re.M)
    if not m:
        sys.exit("import 라인을 못 찾음 — 수동 삽입 필요")
    ins = src.index("\n", m.end()) + 1
    src = src[:ins] + PATCH_ARGS + src[ins:]

    # 2) load_panel 내부 파일 탐색에 조정본 우선 적용
    src = src.replace(
        'for fn in ("_월봉종가캐시_KOSPI.csv", "_월봉종가캐시_KOSDAQ.csv"):\n        p = _find(fn)',
        'for fn in ("_월봉종가캐시_KOSPI.csv", "_월봉종가캐시_KOSDAQ.csv"):\n'
        '        p = _r2_adjusted_name(fn) or _find(fn)')

    # 3) 패널 생성 직후 구간 자르기
    src = src.replace(
        'px = allc.pivot_table(index="ym", columns="code", values="close", aggfunc="last").sort_index()',
        'px = allc.pivot_table(index="ym", columns="code", values="close", aggfunc="last").sort_index()\n'
        '    px = _r2_window(px)   # R2: --start/--end')

    # 4) 원본 파서를 관용 모드로 — R2 인자를 거부하지 않게
    src2 = re.sub(r'(\ba\s*=\s*ap)\.parse_args\(\)', r'\1.parse_known_args()[0]', src)
    if src2 == src:
        print('  ⚠️ parse_args() 자동 치환 실패 — 수동으로 parse_known_args()[0] 로 바꿀 것')
    src = src2

    # 5) 결과 저장 파일명에 라벨 부착
    src = re.sub(r'(["\'])([^"\']*?)(_결과\.json)\1',
                 r'\1\2_\3'.replace("_\\3", "") + r'"+"_"+_R2ARGS.label+"' + r'\3\1', src)

    t.write_text(src, encoding="utf-8")
    print(f"✅ 패치 완료: {t}")
    print(f"   백업: {t.with_suffix(t.suffix + '.bak')}")
    print()
    print("실행 순서:")
    print(f'  py "{t}" --label R0')
    print(f'  py "{t}" --start 2015-01 --label R1')
    print(f'  py "{t}" --start 2015-01 --adjusted "..\\데이터수리" --label R2')
    print()
    print("판정 규칙 (사전등록):")
    print("  R0에서 20.1%가 ±1%p 내로 재현 → 코드 무결성 OK")
    print("  R0 재현 실패 → 7/23 결과 자체가 재현 불가. 별도 조사")
    print("  R2에서 TOP30_고정 대비 우위가 사라짐 → 그때 비로소 강등 정당")
    print("  R2에서 우위 유지 → 20.1% 계열 가설 복권, G4 재판정으로 진행")


if __name__ == "__main__":
    main()
