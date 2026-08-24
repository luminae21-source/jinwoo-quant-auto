# -*- coding: utf-8 -*-
"""재량 트랙 게이트 검정력 시뮬레이션
질문: '12개월 뒤 α>0 & t>1.5' 게이트를, 실력이 0인 사람은 몇 % 통과하나?
"""
import numpy as np
rng = np.random.default_rng(7)

MKT_MU, MKT_VOL = 0.06, 0.18     # 시장
BETA = 1.1                        # 성장주 재량 포트 가정
TE = 0.18                         # 추적오차(집중포트 잔차 변동성) 연 18%
N = 20000

def ols_alpha_t(r, b):
    X = np.column_stack([np.ones(len(b)), b])
    coef, *_ = np.linalg.lstsq(X, r, rcond=None)
    resid = r - X @ coef
    dof = len(r) - 2
    s2 = (resid @ resid) / dof
    XtXinv = np.linalg.inv(X.T @ X)
    se = np.sqrt(s2 * XtXinv[0, 0])
    return coef[0], coef[0] / se

def run(alpha_yr, months, te=TE):
    passes = 0; alphas = []
    for _ in range(N):
        b = rng.normal(MKT_MU/12, MKT_VOL/np.sqrt(12), months)
        e = rng.normal(0, te/np.sqrt(12), months)
        r = alpha_yr/12 + BETA*b + e
        a, t = ols_alpha_t(r, b)
        alphas.append(a*12)
        if a > 0 and t > 1.5: passes += 1
    return passes/N, np.array(alphas)

print("="*64)
print(" [A] 게이트 검정력  (게이트: α>0 AND t>1.5, β조정)")
print(f"     가정: β={BETA}, 추적오차 {TE:.0%}/yr, 경로 {N:,}")
print("="*64)
print(f"{'실제 실력':>10} | {'12개월':>8} {'24개월':>8} {'36개월':>8} {'60개월':>8}")
print("-"*64)
for a in (0.00, 0.03, 0.06, 0.10, 0.15):
    row = [run(a, m)[0] for m in (12, 24, 36, 60)]
    tag = "실력 0 (위양성)" if a == 0 else f"연 {a:.0%}"
    print(f"{tag:>10} | " + " ".join(f"{p:7.1%}" for p in row))

print("\n[해석용] 실력 0일 때 12개월 추정 알파 분포")
_, al = run(0.0, 12)
for p in (10, 25, 50, 75, 90):
    print(f"   {p:>2}%tile: {np.percentile(al, p):+7.1%}/yr")
print(f"   실력 0인데 측정알파 +10% 넘을 확률: {(al>0.10).mean():.1%}")

print("\n" + "="*64)
print(" [B] 훔쳐보기 벌칙 — 매월 확인하다 통과하면 선언할 경우 (실력 0)")
print("="*64)
for horizon in (12, 24, 36):
    hit = 0
    for _ in range(N//4):
        b = rng.normal(MKT_MU/12, MKT_VOL/np.sqrt(12), horizon)
        e = rng.normal(0, TE/np.sqrt(12), horizon)
        r = BETA*b + e
        for m in range(6, horizon+1):     # 6개월차부터 매월 확인
            a, t = ols_alpha_t(r[:m], b[:m])
            if a > 0 and t > 1.5:
                hit += 1; break
    print(f"  {horizon}개월간 매월 확인 → 한 번이라도 통과할 확률: {hit/(N//4):.1%}"
          f"   (한 번만 판정: {run(0.0,horizon)[0]:.1%})")
