# -*- coding: utf-8 -*-
"""적립 포함 복리 시뮬 + 시퀀스 리스크 (단위: 만원, 예시 가정)"""
import numpy as np
rng = np.random.default_rng(2026)
N, YRS = 20000, 10
INIT, MONTHLY = 1000, 100      # 예시: 초기 1,000만 · 월 100만

def sim(cagr, vol=0.18, yrs=YRS, init=INIT, monthly=MONTHLY):
    m = np.log(1+cagr)/12; s = vol/np.sqrt(12)
    w = np.full(N, float(init))
    for _ in range(yrs*12):
        w = w * np.exp(rng.normal(m, s, N)) + monthly
    return w

print("="*66)
print(f" [E] 적립 복리 분포  (초기 {INIT:,}만 · 월 {MONTHLY}만 · {YRS}년 · vol 18%)")
print("="*66)
paid = INIT + MONTHLY*12*YRS
print(f" 총 납입원금: {paid:,}만원\n")
print(f"{'시나리오':>18} | {'10%':>8} {'25%':>8} {'50%':>8} {'75%':>8} {'90%':>8} | 원금미달")
print("-"*80)
for name, c in (("보수 3.1%",0.031),("중립 6.6%",0.066),
                ("중립+재량2% 8.6%",0.086),("낙관 12.1%",0.121)):
    w = sim(c)
    ps = [np.percentile(w,p) for p in (10,25,50,75,90)]
    print(f"{name:>18} | " + " ".join(f"{v:7,.0f}" for v in ps) + f" | {(w<paid).mean():6.1%}")

print("\n" + "="*66)
print(" [F] 레버 비교 — 10년 중앙값, 무엇이 더 크게 움직이나 (중립 6.6% 기준)")
print("="*66)
base = np.median(sim(0.066))
cases = [("기준 (월 100만)", 0.066, 100),
         ("수익률 +2%p (월 100만)", 0.086, 100),
         ("납입 +50% (월 150만)", 0.066, 150),
         ("납입 2배 (월 200만)", 0.066, 200),
         ("비용절감 +0.24%p", 0.0684, 100)]
for n_, c, mo in cases:
    v = np.median(sim(c, monthly=mo))
    print(f"  {n_:<26} {v:8,.0f}만  ({(v/base-1):+6.1%})")

print("\n" + "="*66)
print(" [G] 시퀀스 리스크 — 같은 수익률, 순서만 다를 때 (적립 중)")
print("="*66)
# 동일한 연수익 집합, 나쁜해 먼저 vs 좋은해 먼저
yrs_ret = np.array([-0.30,-0.15,-0.05,0.02,0.05,0.08,0.12,0.18,0.25,0.36])
def path(rets):
    w = float(INIT)
    for r in rets:
        for _ in range(12): w = w*(1+r)**(1/12) + MONTHLY
    return w
bad_first = path(yrs_ret)
good_first = path(yrs_ret[::-1])
print(f"  연수익 집합 동일(기하평균 {(np.prod(1+yrs_ret)**(1/10)-1):.1%})")
print(f"  나쁜 해 먼저: {bad_first:8,.0f}만")
print(f"  좋은 해 먼저: {good_first:8,.0f}만")
print(f"  차이: {abs(bad_first-good_first):,.0f}만 ({abs(bad_first/good_first-1):.0%})")
print("  → 적립 중에는 초반 하락이 오히려 유리하다(싸게 산다). 은퇴·인출기엔 정반대.")
