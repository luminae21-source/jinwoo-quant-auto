# -*- coding: utf-8 -*-
r"""jq_paths.py — 가상매매 패키지의 **단일 경로 진실원**.

문제 배경
---------
엔진은 원래 진우퀀트 루트에서 평면(flat)으로 개발됐다. 이후 코드만
`가상매매\\엔진\\` 아래로 옮겼는데, 데이터 CSV는 루트에 그대로 남았다.
그래서 `BASE = os.path.dirname(os.path.abspath(__file__))` 로 데이터를 찾던
스크립트는 `가상매매\\엔진\\kospi_index_daily.csv` 를 뒤지게 됐고, 조용히
"데이터 없음"으로 실패했다. (할로윈_검증.py가 실제로 이렇게 깨졌다.)

규칙 — 이것만 지키면 같은 사고가 안 난다
-----------------------------------------
* **데이터 CSV/JSON 원본은 진우퀀트 루트(ROOT)에 있다.**
* **코드는 `가상매매\\엔진\\`(HERE) 아래 있다.**
* **산출물은 `가상매매\\<하위폴더>`(DIR_*)에 쓴다.**
* 경로는 절대 상대경로로 쓰지 말고 **여기 상수/함수로만** 해석한다.

레이아웃::

    ROOT(진우퀀트)\                 ← 데이터 CSV 원본
        kospi_index_daily.csv
        attribution_pit_daily.csv
        my_holdings.csv ...
        가상매매\                   ← PKG
            엔진\                   ← HERE (이 파일)
            원장\ 백테스트\ 검증\ 문서\ 실행이력\

사용::

    from jq_paths import ROOT, DIR_VERIFY, data_path, require_data
    p = data_path("kospi_index_daily.csv")      # 없으면 None
    p = require_data("kospi_index_daily.csv")   # 없으면 FileNotFoundError(뒤진 경로 전부 표시)
"""
import os

HERE = os.path.dirname(os.path.abspath(__file__))   # ...\가상매매\엔진
PKG = os.path.dirname(HERE)                         # ...\가상매매
ROOT = os.path.dirname(PKG)                         # ...\진우퀀트   ← 데이터 원본

# 산출물 디렉터리
DIR_LEDGER = os.path.join(PKG, "원장")
DIR_BT = os.path.join(PKG, "백테스트")
DIR_VERIFY = os.path.join(PKG, "검증")
DIR_DOC = os.path.join(PKG, "문서")
DIR_LOG = os.path.join(PKG, "실행이력")

# 데이터 탐색 순서 — 루트 우선. (엔진 폴더는 과거 평면 배치 호환용 폴백)
SEARCH_DIRS = (ROOT, PKG, HERE)

# 엔진·검증이 참조하는 루트 데이터 파일 (한 곳에 모아둔다)
DATA_FILES = (
    "kospi_index_daily.csv",       # KOSPI 지수 일봉 (FDR KS11)
    "attribution_pit_daily.csv",   # code=1001 = KOSPI 지수 (pykrx)
    "my_holdings.csv",             # 실보유
    "liquidity_sector.csv",
    "breadth_features.csv",
    "theme_heat_latest.csv",
)


def data_path(name, dirs=SEARCH_DIRS):
    """데이터 파일의 절대경로. 못 찾으면 None."""
    for d in dirs:
        p = os.path.join(d, name)
        if os.path.exists(p):
            return p
    return None


def searched(name, dirs=SEARCH_DIRS):
    """뒤진 경로 목록 — 실패 시 그대로 보여주기 위함."""
    return [os.path.join(d, name) for d in dirs]


def require_data(name, dirs=SEARCH_DIRS):
    """데이터 파일 절대경로. 없으면 뒤진 경로를 전부 담아 FileNotFoundError."""
    p = data_path(name, dirs)
    if p:
        return p
    lines = "\n".join(f"    - {q}" for q in searched(name, dirs))
    raise FileNotFoundError(
        f"{name} 을(를) 찾지 못했습니다. 아래 경로를 모두 확인했습니다:\n{lines}\n"
        f"  데이터 CSV 원본은 진우퀀트 루트에 있어야 합니다: {ROOT}"
    )


def ensure_dirs():
    for d in (DIR_LEDGER, DIR_BT, DIR_VERIFY, DIR_DOC, DIR_LOG):
        os.makedirs(d, exist_ok=True)


def _self_test():
    ok = tot = 0

    def chk(n, c):
        nonlocal ok, tot
        tot += 1
        ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")

    chk("HERE = 엔진 폴더", os.path.basename(HERE) == "엔진")
    chk("PKG = 가상매매", os.path.basename(PKG) == "가상매매")
    chk("ROOT = 진우퀀트(엔진의 2단계 위)", os.path.basename(ROOT) == "진우퀀트")
    chk("ROOT != HERE (경로 사고 방지)", ROOT != HERE)
    found = [n for n in DATA_FILES if data_path(n)]
    chk(f"루트에서 데이터 파일 탐색 ({len(found)}/{len(DATA_FILES)})", len(found) >= 1)
    for n in DATA_FILES:
        p = data_path(n)
        print(f"      {'O' if p else 'X'} {n}" + (f"  → {p}" if p else "  (없음)"))
    print(f"\n  ROOT = {ROOT}")
    print(f"self-test: {ok}/{tot}")
    return ok == tot


if __name__ == "__main__":
    _self_test()
