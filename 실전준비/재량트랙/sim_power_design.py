# -*- coding: utf-8 -*-
"""설계 선택이 검정력을 얼마나 바꾸나 — 추적오차(TE) × 기간"""
import numpy as np
rng = np.random.default_rng(11)
MKT_MU, MKT_VOL, BETA, N = 0.06, 0.18, 1.1, 8000

def ols_t(r, b):
    X = np.column_stack([np.ones(len(b)), b])
    c, *_ = np.linalg.lstsq(X, r, rcond=None)
    e = r - X @ c
    s2 = (e @ e) / (len(r) - 2)
    se = np.sqrt(s2 * np.linalg.inv(X.T @ X)[0, 0])
    return c[0], c[0]/se

def power(alpha, months, te):
    k = 0
    for _ in range(N):
        b = rng.normal(MKT_MU/12, MKT_VOL/np.sqrt(12), months)
        r = alpha/12 + BETA*b + rng.normal(0, te/np.sqrt(12), months)
        a, t = ols_t(r, b)
        if a > 0 and t > 1.5: k += 1
    return k/N

print("="*66)
print(" [C] 설계가 검정력을 산다 — 실제 실력 연 6% 가정 시 게이트 통과율")
print("="*66)
print(f"{'추적오차':>22} | {'12개월':>7} {'24개월':>7} {'36개월':>7} {'60개월':>7}")
print("-"*66)
for te, label in ((0.25,"25% (5~8종목 집중)"),(0.18,"18% (10종목)"),
                  (0.12,"12% (20종목)"),(0.08,"8% (30종목+섹터중립)")):
    print(f"{label:>22} | " + " ".join(f"{power(0.06,m,te):6.1%}" for m in (12,24,36,60)))

print("\n  ※ 같은 실력이어도 종목수를 늘리면 '증명 가능성'이 2배 이상 뛴다.")
print("     집중투자는 수익 기대치는 같고 측정 가능성만 파괴한다.")

print("\n" + "="*66)
print(" [D] 몇 년이 필요한가 — t>1.5 도달에 필요한 기간 (IR 기준)")
print("="*66)
print(f"{'실력/TE = IR':>14} | 필요기간(중앙값 기준, 년)")
print("-"*66)
for a, te in ((0.03,0.18),(0.06,0.18),(0.06,0.12),(0.10,0.12),(0.10,0.08),(0.15,0.08)):
    ir = a/te
    yrs = (1.5/ir)**2
    print(f"  α{a:.0%}/TE{te:.0%} = {ir:.2f} | {yrs:5.1f}년")
