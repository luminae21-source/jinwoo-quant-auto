import numpy as np

def mult(r, n): return (1+r)**n

scen = {
 "보수": dict(mkt=0.040, factor=0.000, disc=0.000, cost=-0.0048, tax=-0.0046),
 "중립": dict(mkt=0.060, factor=0.015, disc=0.000, cost=-0.0048, tax=-0.0046),
 "낙관": dict(mkt=0.080, factor=0.030, disc=0.020, cost=-0.0048, tax=-0.0046),
}
print("=== CAGR 조립 ===")
res={}
for k,v in scen.items():
    tot = sum(v.values())
    res[k]=tot
    print(f"{k}: 시장{v['mkt']:.1%} + 팩터{v['factor']:.1%} + 재량{v['disc']:.1%} + 비용{v['cost']:.2%} + 세금{v['tax']:.2%} = {tot:.2%}")

print("\n=== 누적배수 (명목 / 실질 인플2.3%) ===")
infl=0.023
for k,r in res.items():
    for n in (5,10,20):
        print(f"{k} {n}년: {mult(r,n):.2f}x  (실질 {mult((1+r)/(1+infl)-1,n):.2f}x)")

print("\n=== 몬테카를로 (중립 drift 6.56%, vol 18%, 10년, 20000경로) ===")
rng=np.random.default_rng(42)
mu, sig, N, T = res["중립"], 0.18, 20000, 10
# 로그정규: 연복리 drift가 기하평균이 되도록
m = np.log(1+mu) - 0.0  # 기하 drift
paths = np.exp(rng.normal(m - 0*sig**2/2, sig, size=(N,T))).cumprod(axis=1)
fin = paths[:,-1]
for p in (5,10,25,50,75,90,95):
    print(f"  {p:>2}%tile: {np.percentile(fin,p):.2f}x")
print(f"  원금손실(<1.0x) 확률: {(fin<1.0).mean():.1%}")
# 경로 최대낙폭
run=np.maximum.accumulate(paths,axis=1)
mdd=((paths/run)-1).min(axis=1)
print(f"  경로 MDD 중앙값: {np.median(mdd):.1%} / 최악10%: {np.percentile(mdd,10):.1%}")
print(f"  -30% 이상 낙폭 경험 확률: {(mdd<=-0.30).mean():.1%}")
