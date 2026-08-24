import pandas as pd, numpy as np
d=pd.read_csv("/tmp/deep.csv",dtype={"code":str})
segs={"ALL":(d["ym"]>="2019-01"),
      "IN":(d["ym"]>="2019-01")&(d["ym"]<="2022-12"),
      "OOS":(d["ym"]>="2023-01")}
def wtest(a,b):  # win-rate diff bootstrap, a=cohort b=base, returns diff, p(diff<=0)
    a=(a>0).astype(int).values; b=(b>0).astype(int).values
    if len(a)<2 or len(b)<2: return None
    rng=np.random.default_rng(7)
    da=rng.choice(a,(5000,len(a)),True).mean(1); db=rng.choice(b,(5000,len(b)),True).mean(1)
    dif=da-db
    return dict(diff=float((a.mean()-b.mean())*100),lo=float(np.percentile(dif,2.5)*100),
                hi=float(np.percentile(dif,97.5)*100),p=float(np.mean(dif<=0)),n=len(a))
for seg,m in segs.items():
    sub=d[m]; dfl=sub[sub["has_flow"]]
    print(f"\n[{seg}]")
    for h,col in [(6,"f6"),(9,"f9"),(12,"f12")]:
        base=sub[col].dropna()
        for name,mask in [("기관",dfl["ipos"]),("외국인",dfl["fpos"]),("둘다",dfl["fpos"]&dfl["ipos"])]:
            s=dfl[mask][col].dropna()
            r=wtest(s,base)
            if r: print(f"  {h}M {name}: 승률차{r['diff']:+5.1f}pp 95%CI[{r['lo']:+.1f},{r['hi']:+.1f}] P(≤0)={r['p']:.3f} n={r['n']}")
        print()
