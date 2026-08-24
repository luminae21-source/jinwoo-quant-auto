#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
비용모델.py — 거래비용 단일 진실원천 (SSOT) · §8-3

── 왜 만들었나 ────────────────────────────────────────────────────
2026-07-27 전수조사에서 코드베이스에 **거래비용 상수가 7종 병존**하는 것이 확인됐다:

    tax=0.002 + slippage=0.0005    17회 / 11회   → 왕복 0.300%   (다올 모델, 백테 주력)
    COST = 0.00235                 15회          → 왕복 0.235%   (v3.7.2 계열)
    COST = 0.0048                   2회          → 왕복 0.480%   (복리 시나리오)
    COST = 0.0015 / 0.0030 / 0.0035 / 0.006       → 산발
    COST = 40.0                     1회          → 정액(원) 혼입 추정 🚨

같은 전략을 어느 스크립트로 돌리느냐에 따라 회전 2.6x 기준 **연 0.7%p** 결과가 달라진다.

── 실측 (2026-07-27) ──────────────────────────────────────────────
Corwin–Schultz 고저가 스프레드, KOSPI 시총 top300, 최근 5년, 표본 247,454 (종목·일):

    편도 슬리피지  중앙값 0.2045%  ·  평균 0.4240%  ·  75%ile 0.6804%  ·  90%ile 1.1538%
    연도별 중앙값  2021 0.184% · 2022 0.183% · 2023 0.211% · 2024 0.232% · 2025 0.215% · 2026 0.157%

⚠️ **Corwin–Schultz는 상한 추정량이다.** 일중 고저 범위를 스프레드로 환산하므로 변동성이
큰 구간에서 과대추정된다(25%ile이 0.0000% = 음수 절단인 것도 그 방증). 대형주 실제 유효
스프레드는 이보다 작을 가능성이 높다. **점추정 하나로 못 박지 말고 시나리오로 쓴다.**

── 권고 사용법 ────────────────────────────────────────────────────
    from 비용모델 import roundtrip, SCENARIOS
    cost = roundtrip("기준")          # 회전 1.0당 왕복비용
    net  = gross - turnover * cost

    for name in SCENARIOS:            # 민감도는 항상 3종 병기
        ...

⚠️ 정보·검증용 · 투자자문 아님
"""
try:  # 윈도 파이프(cp949)에서 이모지 출력 시 UnicodeEncodeError 방지 (2026-07-27)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


# ── 확정 사실 ──────────────────────────────────────────────────────
증권거래세_매도 = 0.0015      # 코스피 0.15% (2026) · 매도 시 1회
수수료_편도 = 0.0             # 다올 온라인 0

# ── 슬리피지 시나리오 (편도) ────────────────────────────────────────
# 낙관: 대형주 실제 유효스프레드 추정 · 기준: CS 중앙값 · 보수: CS 75%ile
슬리피지 = {
    "낙관": 0.0005,      # 종전 다올 가정 (편도 0.05%)
    "기준": 0.002045,    # CS 중앙값 실측 (2021~2026, top300)
    "보수": 0.006804,    # CS 75%ile
}

SCENARIOS = ("낙관", "기준", "보수")
DEFAULT = "기준"


def slippage(scenario=DEFAULT):
    """편도 슬리피지."""
    if scenario not in 슬리피지:
        raise ValueError(f"시나리오는 {SCENARIOS} 중 하나 — 받은 값 {scenario!r}")
    return 슬리피지[scenario]


def roundtrip(scenario=DEFAULT):
    """회전율 1.0당 왕복 총비용 = 세금(매도 1회) + 수수료×2 + 슬리피지×2."""
    return 증권거래세_매도 + 수수료_편도 * 2 + slippage(scenario) * 2


def annual_cost(turnover_per_year, scenario=DEFAULT):
    """연 회전율 → 연 비용(연율 %p 아님, 소수)."""
    return turnover_per_year * roundtrip(scenario)


# ── 종전 상수 (마이그레이션 대조용 — 신규 코드에서 쓰지 말 것) ──────────
LEGACY = {
    "다올(tax .002 + slip .0005x2)": 0.0030,
    "v3.7.2 COST": 0.00235,
    "복리시나리오 COST": 0.0048,
}


def table():
    """시나리오별 왕복비용 + 종전 상수 대조표(문자열)."""
    L = ["회전 1.0당 왕복비용", "-" * 46]
    for s in SCENARIOS:
        mark = "  ← 기본" if s == DEFAULT else ""
        L.append(f"  {s:4} 슬리피지 편도 {slippage(s)*100:.4f}%  →  왕복 {roundtrip(s)*100:.3f}%{mark}")
    L += ["", "종전 병존 상수 (기준 시나리오 대비)", "-" * 46]
    base = roundtrip(DEFAULT)
    for k, v in LEGACY.items():
        L.append(f"  {k:32} {v*100:.3f}%  {(v-base)*100:+.3f}%p")
    return "\n".join(L)


if __name__ == "__main__":
    print("=" * 62)
    print(" 진우퀀트 거래비용 모델 (SSOT) · §8-3")
    print("=" * 62)
    print(table())
    print()
    print("연 회전율별 연간 비용 (기준 시나리오)")
    print("-" * 46)
    for t in (0.2, 0.6, 0.8, 2.6, 3.7):
        print(f"  회전 {t:>4.1f}x/년  →  연 {annual_cost(t)*100:.2f}%")
    print("\n⚠️ CS는 상한 추정량 — 결론은 반드시 3종 시나리오 병기로 보고할 것.")
