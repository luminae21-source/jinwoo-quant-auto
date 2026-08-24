# -*- coding: utf-8 -*-
"""#74 3축 표 검증 — stats() 최악월과 방어의 손실 절반 효과."""
import sys, importlib.util
import numpy as np, pandas as pd
sys.argv=[sys.argv[0]]
spec=importlib.util.spec_from_file_location("bt","운용사양_백테.py")
bt=importlib.util.module_from_spec(spec); spec.loader.exec_module(bt)
ok=[]
def t(n,c): ok.append((n,bool(c)))

# ① stats 최악월
s=bt.stats([0.01]*23+[-0.05])
t("① 최악월 정확", abs(s["worst"]-(-5.0))<1e-9)
t("② 기존 키 유지", all(k in s for k in ("cagr","sharpe","mdd")))
t("③ 짧은 시계열도 worst 키", "worst" in bt.stats([0.01]*5) and np.isnan(bt.stats([0.01]*5)["worst"]))

# ④ 방어가 손실 달을 절반으로 — 합성 백테
cols=["%06d"%i for i in range(1,61)]
ym=["2020-10","2020-11","2020-12","2021-01"]
R=pd.DataFrame(0.0,index=ym,columns=cols); R.loc["2020-12","000001"]=-0.10
M=pd.DataFrame(100.0,index=ym,columns=cols)
MOM=pd.DataFrame(1.0,index=ym,columns=cols); MOM["000001"]=2.0
DEFS=pd.Series({"2020-11":True,"2020-12":False,"2021-01":True})
nd=bt.backtest(R,M,MOM,1,60,0.0)
wd=bt.backtest(R,M,MOM,1,60,0.0,defense=DEFS)
t("④ 무방어 최악월 −10%", abs(min(nd["rets"])-(-0.10))<1e-12)
t("⑤ 방어 최악월 −5%", abs(min(wd["rets"])-(-0.05))<1e-12)
t("⑥ 손실 없는 달은 동일", nd["rets"][0]==wd["rets"][0]==0.0)

n=sum(1 for _,b in ok if b)
for name,b in ok: print(("  ✓ " if b else "  ✗ ")+name)
print("검증 %d/%d %s"%(n,len(ok),"PASS" if n==len(ok) else "FAIL"))
sys.exit(0 if n==len(ok) else 1)
