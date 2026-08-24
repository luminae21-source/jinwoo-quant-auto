# -*- coding: utf-8 -*-
"""paired_test 검증 — 특히 '짝을 유지하면 구간이 좁아진다'는 주장 자체를 시험한다."""
import sys, importlib.util
import numpy as np
sys.argv=[sys.argv[0]]
spec=importlib.util.spec_from_file_location("bt","운용사양_백테.py")
bt=importlib.util.module_from_spec(spec); spec.loader.exec_module(bt)
ok=[]
def t(n,c): ok.append((n,bool(c)))

rng=np.random.default_rng(7)
T=240
mkt=rng.normal(0.008,0.055,T)          # 시장 (월 0.8%, 변동성 5.5%)

# ① 전략 = 시장 + 일정한 알파. 격차는 확실해야 하고 구간은 좁아야 한다.
alpha=0.002
strat=mkt+alpha
p=bt.paired_test(strat,mkt,boot=300,seed=1)
t("① 알파 있으면 초과>0 확률 100%", p["beat"]==1.0)
t("② 실측 격차가 알파 근처(연 2.4%p)", 2.0 < p["act_gap"] < 3.0)
t("③ 짝지은 구간이 기존방식보다 좁다", p["width"] < p["naive_width"])
t("④ 좁은 정도가 확실하다(1/3 이하)", p["width"] < p["naive_width"]/3)

# ⑤ 알파 0 이면 초과>0 확률이 50% 근처
p0=bt.paired_test(mkt,mkt.copy(),boot=300,seed=2)
t("⑤ 동일 시계열이면 격차 0", abs(p0["act_gap"])<1e-9)
t("⑥ 동일 시계열이면 구간 폭 0", p0["width"]<1e-9)

# ⑦ 베타가 다르면(전략이 시장의 1.3배) 짝지어도 구간이 넓어진다 — 상쇄가 부분적
lev=mkt*1.3
pl=bt.paired_test(lev,mkt,boot=300,seed=3)
t("⑦ 레버리지는 구간을 넓힌다", pl["width"] > p["width"])

# ⑧ 독립 시계열이면 짝지어도 안 좁아진다 (상쇄할 공통성분이 없음)
ind=rng.normal(0.008,0.055,T)
pi=bt.paired_test(ind,mkt,boot=300,seed=4)
t("⑧ 무상관이면 이득 없음", pi["width"] > p["naive_width"]*0.7)

# ⑨ 월승률
up=np.where(np.arange(T)%2==0, mkt+0.01, mkt-0.01)
pu=bt.paired_test(up,mkt,boot=100,seed=5)
t("⑨ 월승률 50%", abs(pu["hit"]-50.0)<1.0)

# ⑩ 표본 수 보고
t("⑩ n 정확", p["n"]==T)

# ⑪ 블록 인덱스가 범위를 안 벗어남
r=np.random.default_rng(9)
ix=bt._block_idx(r,50,12)
t("⑪ 인덱스 길이·범위", len(ix)==50 and ix.min()>=0 and ix.max()<50)

# ⑫ 재현성 (같은 seed → 같은 결과)
t("⑫ 재현성", bt.paired_test(strat,mkt,boot=50,seed=11)["p50"]
              == bt.paired_test(strat,mkt,boot=50,seed=11)["p50"])

n=sum(1 for _,b in ok if b)
for name,b in ok: print(("  ✓ " if b else "  ✗ ")+name)
print("검증 %d/%d %s" % (n,len(ok),"PASS" if n==len(ok) else "FAIL"))
print("\n[참고] 알파 0.2%%/월 시나리오: 짝지은 폭 %.2f%%p vs 기존방식 폭 %.2f%%p"
      % (p["width"], p["naive_width"]))
sys.exit(0 if n==len(ok) else 1)
