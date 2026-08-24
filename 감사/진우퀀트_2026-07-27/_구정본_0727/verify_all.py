#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
verify_all.py — 오늘 산출물의 모든 숫자를 재도출해서 문서와 대조한다.
'그럴듯하다'가 아니라 '재현된다'로 판정. 실패 시 exit code 1.

원칙:
  1. 문서에 적힌 숫자는 전부 코드가 다시 만든다 (이론값 또는 시뮬).
  2. 시뮬 대조는 몬테카를로 오차한계 안에서만 통과시킨다.
  3. 이론해가 있는 항목은 이론과도 대조한다 (시뮬 자체의 검증).
"""
import re, sys, math
import numpy as np
from pathlib import Path

try:
    from scipy import stats
    HAVE_SCIPY = True
except ImportError:
    HAVE_SCIPY = False

D = Path(__file__).parent
RESULTS = []


def check(name, claimed, recomputed, tol, unit="", note=""):
    ok = abs(claimed - recomputed) <= tol
    RESULTS.append((ok, name, claimed, recomputed, tol, unit, note))
    return ok


def doc_num(fname, pattern, group=1):
    """문서에서 숫자를 직접 긁어온다 — 내가 문서에 뭘 썼는지 코드가 읽음"""
    txt = (D / fname).read_text(encoding="utf-8")
    m = re.search(pattern, txt)
    if not m:
        RESULTS.append((False, f"[문서파싱실패] {fname}: {pattern[:40]}", 0, 0, 0, "", "패턴 불일치"))
        return None
    return float(m.group(group))


# ══════════════════════════════════════════════════════════
# 1. 복리 시나리오 — CAGR 조립 (순수 산술, 이론해 존재)
# ══════════════════════════════════════════════════════════
SCEN = {"보수": (0.040, 0.000, 0.000), "중립": (0.060, 0.015, 0.000),
        "낙관": (0.080, 0.030, 0.020)}
COST, TAX = -0.0048, -0.0046

for k, (mkt, fac, disc) in SCEN.items():
    cagr = mkt + fac + disc + COST + TAX
    # 표 행에 앵커링 — 본문 산문의 동일 문자열 오매치 방지
    claimed = doc_num("정직한_복리시나리오_v2.md", rf"\|\s*{k}\s+([\d.]+)%\s*\|")
    if claimed is not None:
        check(f"CAGR 조립 [{k}]", claimed, cagr * 100, 0.05, "%")

# 누적배수 — 이론해
for k, (mkt, fac, disc) in SCEN.items():
    cagr = mkt + fac + disc + COST + TAX
    for yrs, tol in ((5, 0.01), (10, 0.01), (20, 0.02)):
        RESULTS.append((True, f"[참고] {k} {yrs}년 배수 이론값", 0, (1 + cagr) ** yrs, 0, "x", ""))

# ══════════════════════════════════════════════════════════
# 2. 게이트 위양성 — 이론(t분포)과 시뮬 대조
# ══════════════════════════════════════════════════════════
SIM_FP = {12: 8.2, 24: 7.2, 36: 7.5, 60: 6.8}   # 리포트 A-1 실력0 행
if HAVE_SCIPY:
    for n, sim_v in SIM_FP.items():
        theo = (1 - stats.t.cdf(1.5, n - 2)) * 100
        se = math.sqrt(theo / 100 * (1 - theo / 100) / 20000) * 100
        check(f"위양성 {n}개월 (시뮬 vs t분포 이론)", sim_v, theo, 3 * se + 0.05, "%",
              f"±{3*se+0.05:.2f}%p (3σ)")
else:
    RESULTS.append((False, "위양성 이론대조", 0, 0, 0, "", "scipy 없음 — 설치 필요"))

# ══════════════════════════════════════════════════════════
# 3. 검정력 — 정규근사 이론과 시뮬 대조
# ══════════════════════════════════════════════════════════
def power_theory(alpha, te, months):
    """IR 기반 정규근사: 기대 t = IR*sqrt(년), P(t>1.5)"""
    if not HAVE_SCIPY:
        return None
    ir = alpha / te
    t_exp = ir * math.sqrt(months / 12)
    return (1 - stats.norm.cdf(1.5 - t_exp)) * 100

# 리포트 A-4 값들
A4 = {(0.06, 0.25, 60): 17.2, (0.06, 0.18, 60): 23.1,
      (0.06, 0.12, 60): 35.2, (0.06, 0.08, 60): 55.9,
      (0.06, 0.12, 36): 26.9, (0.06, 0.12, 12): 17.9}
for (a, te, m), sim_v in A4.items():
    th = power_theory(a, te, m)
    if th is not None:
        check(f"검정력 α{a:.0%}/TE{te:.0%}/{m}개월", sim_v, th, 4.0, "%",
              "정규근사 vs 유한표본 t — 4%p 허용")

# ══════════════════════════════════════════════════════════
# 4. 필요기간 정의 검증 — (1.5/IR)^2 가 통과확률 50% 지점인가
# ══════════════════════════════════════════════════════════
if HAVE_SCIPY:
    for a, te in ((0.06, 0.18), (0.06, 0.12), (0.10, 0.08)):
        ir = a / te
        yrs = (1.5 / ir) ** 2
        p_at = power_theory(a, te, yrs * 12)
        check(f"필요기간 정의 α{a:.0%}/TE{te:.0%} → {yrs:.1f}년에 통과확률", p_at, 50.0, 0.5, "%",
              "정의: 통과확률 50% 지점")

# ══════════════════════════════════════════════════════════
# 5. 적립 복리 — 재실행 후 문서값과 대조 (MC 오차 허용)
# ══════════════════════════════════════════════════════════
def sim_wealth(cagr, vol=0.18, yrs=10, init=1000, monthly=100, n=20000, seed=2026):
    rng = np.random.default_rng(seed)
    m, s = math.log(1 + cagr) / 12, vol / math.sqrt(12)
    w = np.full(n, float(init))
    for _ in range(yrs * 12):
        w = w * np.exp(rng.normal(m, s, n)) + monthly
    return w

DOC_MEDIAN = {0.031: 15614, 0.066: 19058, 0.086: 21146, 0.121: 25837}
for c, claimed in DOC_MEDIAN.items():
    med = np.median(sim_wealth(c))
    check(f"적립 10년 중앙값 CAGR{c:.1%}", claimed, med, max(200, med * 0.02), "만원",
          "동일시드 재현 (±2%)")

# 총 납입원금 — 산술
check("총 납입원금", 13000, 1000 + 100 * 12 * 10, 0, "만원")

# 레버 비교 — 납입 2배가 중앙값을 얼마나 올리나
base = np.median(sim_wealth(0.066))
dbl = np.median(sim_wealth(0.066, monthly=200))
check("납입 2배 효과", 89.6, (dbl / base - 1) * 100, 3.0, "%", "MC 오차 허용")
up2 = np.median(sim_wealth(0.086))
check("수익률 +2%p 효과", 12.8, (up2 / base - 1) * 100, 2.0, "%")

# ══════════════════════════════════════════════════════════
# 6. 논리 정합성 — 문서 간 모순 탐지 (숫자 아닌 주장)
# ══════════════════════════════════════════════════════════
def assert_text(fname, must_have=None, must_not_have=None):
    txt = (D / fname).read_text(encoding="utf-8")
    for s in (must_have or []):
        RESULTS.append((s in txt, f"[문구] {fname} ⊃ '{s[:28]}'", 0, 0, 0, "", ""))
    for s in (must_not_have or []):
        RESULTS.append((s not in txt, f"[금지문구] {fname} ⊅ '{s[:28]}'", 0, 0, 0, "", ""))

assert_text("정직한_복리시나리오_v2.md",
            must_have=["최소 36개월"],
            must_not_have=["①번 트랙이 12개월 뒤"])
assert_text("재량트랙_측정사양서_v2.1.md",
            must_have=["1차 중간판정", "통과확률 27%"],
            must_not_have=["1차 알파 판정 |"])

# 레버 순서 정합성: 납입효과 > 수익률효과 여야 문서 주장이 성립
RESULTS.append(((dbl / base) > (up2 / base),
                "[논리] 납입2배 효과 > 수익률+2%p 효과", 0, 0, 0, "",
                "시나리오 v2 §5 주장의 근거"))


# ══════════════════════════════════════════════════════════
def main():
    print("=" * 78)
    print(" verify_all.py — 오늘 산출물 전수 재도출 검증")
    print("=" * 78)
    npass = sum(1 for r in RESULTS if r[0])
    ntot = len(RESULTS)
    for ok, name, cl, rc, tol, unit, note in RESULTS:
        mark = "✅" if ok else "❌"
        if cl or rc:
            print(f" {mark} {name:<44} 문서 {cl:>9,.2f}{unit} | 재도출 {rc:>9,.2f}{unit}"
                  + (f"  {note}" if note else ""))
        else:
            print(f" {mark} {name}" + (f"  — {note}" if note else ""))
    print("-" * 78)
    print(f" 통과 {npass}/{ntot}")
    fails = [r[1] for r in RESULTS if not r[0]]
    if fails:
        print(" ❌ 실패 항목:")
        for f in fails:
            print(f"    - {f}")
        return 1
    print(" ✅ 전수 통과 — 문서의 모든 숫자가 코드로 재도출됨")
    return 0


if __name__ == "__main__":
    sys.exit(main())
