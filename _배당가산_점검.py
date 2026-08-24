# -*- coding: utf-8 -*-
"""#75 배당 가산 검증 — backtest 의 12월 세후 가산이 정확한지 합성 데이터로 잰다."""
import sys, importlib.util
import numpy as np, pandas as pd
sys.argv=[sys.argv[0]]
spec=importlib.util.spec_from_file_location("bt","운용사양_백테.py")
bt=importlib.util.module_from_spec(spec); spec.loader.exec_module(bt)
ok=[]
def t(n,c): ok.append((n,bool(c)))

cols=["%06d"%i for i in range(1,61)]           # mc>=50 문턱을 넘기 위해 60종목
ym=["2020-10","2020-11","2020-12","2021-01"]
R=pd.DataFrame(0.0,index=ym,columns=cols)      # 가격수익 0 → 배당만 남는다
M=pd.DataFrame(100.0,index=ym,columns=cols)
MOM=pd.DataFrame(1.0,index=ym,columns=cols); MOM["000001"]=2.0   # 000001 이 항상 1등
DIV=pd.DataFrame(0.0,index=ym,columns=cols); DIV["000001"]=11.54

# ① 12월에만, 세후로 가산되는가 (N=1 → 000001 만 보유, 비중 1)
r=bt.backtest(R,M,MOM,1,60,0.0,div_yield=DIV,tax=0.154)
exp=0.1154*(1-0.154)
t("① 12월 세후 가산", abs(r["rets"][1]-exp)<1e-12)
t("② 다른 달은 0", r["rets"][0]==0.0 and r["rets"][2]==0.0)
t("③ 월 라벨 일치", r["yms"]==["2020-11","2020-12","2021-01"])

# ④ 세율 0 이면 그로스
r0=bt.backtest(R,M,MOM,1,60,0.0,div_yield=DIV,tax=0.0)
t("④ 세율 0 → 그로스", abs(r0["rets"][1]-0.1154)<1e-12)

# ⑤ div_yield=None 이면 기존과 동일 (전부 0)
rn=bt.backtest(R,M,MOM,1,60,0.0)
t("⑤ OFF 시 무영향", all(x==0.0 for x in rn["rets"]))

# ⑥ 방어(현금 50%)면 배당도 절반
DEFS=pd.Series({"2020-11":True,"2020-12":False,"2021-01":True})
rd=bt.backtest(R,M,MOM,1,60,0.0,defense=DEFS,div_yield=DIV,tax=0.154)
t("⑥ 방어 시 배당 절반", abs(rd["rets"][1]-exp*0.5)<1e-12)

# ⑦ 보유하지 않은 종목의 배당은 안 들어온다 (000002 에만 배당)
DIV2=pd.DataFrame(0.0,index=ym,columns=cols); DIV2["000002"]=11.54
r2=bt.backtest(R,M,MOM,1,60,0.0,div_yield=DIV2,tax=0.154)
t("⑦ 미보유 배당 제외", r2["rets"][1]==0.0)

# ⑧ NaN DIV 는 0 취급
DIV3=DIV.copy(); DIV3.loc["2020-12","000001"]=np.nan
r3=bt.backtest(R,M,MOM,1,60,0.0,div_yield=DIV3,tax=0.154)
t("⑧ NaN → 0", r3["rets"][1]==0.0)

# ⑨ N=2 면 가중 평균 (000001 만 배당, 비중 0.5 → 절반)
MOM2=MOM.copy(); MOM2["000002"]=1.5
r4=bt.backtest(R,M,MOM2,2,60,0.0,div_yield=DIV,tax=0.154)
t("⑨ 가중 반영", abs(r4["rets"][1]-exp*0.5)<1e-12)

# ⑩ load_index_monthly — 일봉 CSV 를 월말 종가로
import tempfile, os
fd,tmp=tempfile.mkstemp(suffix=".csv"); os.close(fd)
pd.DataFrame({"date":["2020-01-02","2020-01-31","2020-02-28"],
              "close":[100.0,110.0,121.0]}).to_csv(tmp,index=False)
s=bt.load_index_monthly(tmp)
t("⑩ 월말 종가 추출", list(s.index)==["2020-01","2020-02"] and s.iloc[0]==110.0)
t("⑪ 수익률 사슬", abs(s.pct_change().iloc[1]-0.1)<1e-12)
os.remove(tmp)

n=sum(1 for _,b in ok if b)
for name,b in ok: print(("  ✓ " if b else "  ✗ ")+name)
print("검증 %d/%d %s"%(n,len(ok),"PASS" if n==len(ok) else "FAIL"))
sys.exit(0 if n==len(ok) else 1)
