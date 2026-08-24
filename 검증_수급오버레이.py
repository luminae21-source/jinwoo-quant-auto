import pandas as pd, numpy as np, json
BASE="/sessions/stoic-optimistic-bohr/mnt/진우퀀트/"

# ---------- 1. 월말 종가 패널 ----------
px_parts=[]
for mkt in ["KOSPI","KOSDAQ"]:
    d=pd.read_csv(f"/tmp/px_m_{mkt}.csv",header=None,names=["code","date","close"],dtype={0:str})
    d["code"]=d["code"].str.zfill(6); d["mkt"]=mkt; px_parts.append(d)
px=pd.concat(px_parts,ignore_index=True)
px["ym"]=px["date"].str[:7]
px=px.drop_duplicates(["code","ym"]).copy()

# 전체 월 그리드 (2016-01 ~ 2026-07)
months=pd.period_range("2016-01","2026-07",freq="M").astype(str).tolist()
mi={m:i for i,m in enumerate(months)}
px=px[px["ym"].isin(mi)].copy()
px["mi"]=px["ym"].map(mi)
px["close"]=pd.to_numeric(px["close"],errors="coerce")

# ---------- 2. PBR 월말 패널 ----------
fp=[]
for mkt in ["KOSPI","KOSDAQ"]:
    f=pd.read_csv(BASE+f"종목재무_KRX_{mkt}.csv",dtype={"code":str})
    f=f[["date","code","PBR"]].copy(); fp.append(f)
fund=pd.concat(fp,ignore_index=True)
fund["code"]=fund["code"].str.zfill(6)
fund["ym"]=fund["date"].str[:7]
fund["PBR"]=pd.to_numeric(fund["PBR"],errors="coerce")
fund=fund.drop_duplicates(["code","ym"])[["code","ym","PBR"]]

# ---------- 3. flow 월말 패널 ----------
flp=[]
for mkt in ["kospi","kosdaq"]:
    fl=pd.read_csv(BASE+f"{mkt}_flow_monthly.csv",dtype={"code":str})
    flp.append(fl)
flow=pd.concat(flp,ignore_index=True)
flow["code"]=flow["code"].str.zfill(6)
flow["ym"]=flow["date"].str[:7]
flow["foreign_net"]=pd.to_numeric(flow["foreign_net"],errors="coerce")
flow["inst_net"]=pd.to_numeric(flow["inst_net"],errors="coerce")
flow=flow.drop_duplicates(["code","ym"])[["code","ym","foreign_net","inst_net"]]

# ---------- 4. 코드별 완전 그리드 → ma10, ret1, 선행수익 ----------
px=px.sort_values(["code","mi"])
codes=px["code"].unique()
T=len(months)

# 각 코드 close 배열(그리드)
close_grid={}
g=px.groupby("code")
recs=[]
H=[6,9,12]
for code,sub in g:
    arr=np.full(T,np.nan)
    arr[sub["mi"].values]=sub["close"].values
    close_grid[code]=arr
    # ma10 (직전 10개월 연속), ret1
    s=pd.Series(arr)
    ma10=s.rolling(10,min_periods=10).mean().values
    ret1=(s/s.shift(1)-1).values
    # 선행수익
    fwd={h:np.full(T,np.nan) for h in H}
    for t in range(T):
        if np.isnan(arr[t]): continue
        for h in H:
            w=arr[t+1:t+1+h]
            w=w[t+1<T] if False else w
            valid=w[~np.isnan(w)]
            if len(valid)==0:
                # 진입 후 창내 가격 전무 → 상폐 -1.0 (단 미래월이 데이터범위 내일 때만)
                if t+1<T:
                    fwd[h][t]=-1.0
                # else 미래창이 데이터 밖 → nan (평가 불가)
            else:
                fwd[h][t]=valid[-1]/arr[t]-1.0
    for t in range(T):
        if np.isnan(arr[t]): continue
        recs.append((code,months[t],arr[t],ma10[t],ret1[t],fwd[6][t],fwd[9][t],fwd[12][t]))

P=pd.DataFrame(recs,columns=["code","ym","close","ma10","ret1","f6","f9","f12"])
P=P.merge(fund,on=["code","ym"],how="left").merge(flow,on=["code","ym"],how="left")
P["disp"]=P["close"]/P["ma10"]

# ---------- 5. 딥밸류바닥 신호 (2019+, flow 존재구간) ----------
P=P[(P["ym"]>="2019-01")].copy()
valid=(P["close"]>=1000)&(P["ma10"].notna())&(P["PBR"]>0)
Pv=P[valid].copy()
# PBR 하위20% (월 횡단면 랭크)
Pv["pbr_rank"]=Pv.groupby("ym")["PBR"].rank(pct=True)
Pv["deep"]=(Pv["pbr_rank"]<=0.20)&(Pv["disp"]<0.85)&(Pv["ret1"]>0)
deep=Pv[Pv["deep"]].copy()
# flow 존재행만 (수급 분류 가능)
deep["has_flow"]=deep["foreign_net"].notna()&deep["inst_net"].notna()
deep["fpos"]=deep["foreign_net"]>0
deep["ipos"]=deep["inst_net"]>0

def stats(df,col):
    x=df[col].dropna().values
    n=len(x)
    if n==0: return dict(n=0,mean=None,med=None,win=None)
    return dict(n=int(n),mean=float(np.mean(x)*100),med=float(np.median(x)*100),
                win=float(np.mean(x>0)*100))

def cohorts(df):
    base=df
    dfl=df[df["has_flow"]]
    return {
        "deep":base,
        "deep_F":dfl[dfl["fpos"]],
        "deep_I":dfl[dfl["ipos"]],
        "deep_both":dfl[dfl["fpos"]&dfl["ipos"]],
    }

def block(df,label):
    out={}
    ch=cohorts(df)
    for h,col in [(6,"f6"),(9,"f9"),(12,"f12")]:
        out[h]={k:stats(v,col) for k,v in ch.items()}
    return out

# 전체(2019~2026) + IN/OOS
res={}
res["ALL"]=block(deep,"ALL")
IN=deep[(deep["ym"]>="2019-01")&(deep["ym"]<="2022-12")]
OOS=deep[(deep["ym"]>="2023-01")&(deep["ym"]<="2026-12")]
res["IN_2019_2022"]=block(IN,"IN")
res["OOS_2023_2026"]=block(OOS,"OOS")

# ---------- 6. 유의성: deep_I vs deep, 12M(및 6/9) Welch t + bootstrap ----------
from math import sqrt
def welch(a,b):
    a=np.asarray(a);b=np.asarray(b)
    na,nb=len(a),len(b)
    if na<2 or nb<2: return None
    va,vb=a.var(ddof=1),b.var(ddof=1)
    t=(a.mean()-b.mean())/sqrt(va/na+vb/nb)
    return float(t)
def boot_diff(a,b,n=5000,seed=42):
    rng=np.random.default_rng(seed)
    a=np.asarray(a);b=np.asarray(b)
    da=rng.choice(a,(n,len(a)),replace=True).mean(1)
    db=rng.choice(b,(n,len(b)),replace=True).mean(1)
    d=da-db
    return float(np.percentile(d,2.5)*100),float(np.percentile(d,97.5)*100),float(np.mean(d<=0))

sig={}
for tag,df in [("ALL",deep),("IN",IN),("OOS",OOS)]:
    sig[tag]={}
    dfl=df[df["has_flow"]]
    for h,col in [(6,"f6"),(9,"f9"),(12,"f12")]:
        base=df[col].dropna().values
        iset=dfl[dfl["ipos"]][col].dropna().values
        fset=dfl[dfl["fpos"]][col].dropna().values
        both=dfl[dfl["fpos"]&dfl["ipos"]][col].dropna().values
        sig[tag][h]={}
        for name,s in [("I",iset),("F",fset),("both",both)]:
            if len(s)>=2 and len(base)>=2:
                lo,hi,p=boot_diff(s,base)
                sig[tag][h][name]=dict(diff_mean=float((s.mean()-base.mean())*100),
                                       t=welch(s,base),ci_lo=lo,ci_hi=hi,p_ge0=p,n=len(s))
            else:
                sig[tag][h][name]=None

json.dump({"res":res,"sig":sig},open("/tmp/results.json","w"),ensure_ascii=False,indent=1)

# ---------- 출력 ----------
def fmt(d):
    if d["n"]==0: return "  n=0"
    return f"n={d['n']:>4} 평균{d['mean']:+6.1f}% 중앙{d['med']:+6.1f}% 승률{d['win']:4.0f}%"
lbl={"deep":"딥밸류바닥      ","deep_F":"딥+외국인매집  ","deep_I":"딥+기관매집    ","deep_both":"딥+둘다매집    "}
for seg in ["ALL","IN_2019_2022","OOS_2023_2026"]:
    print("\n=========================",seg,"=========================")
    for h in [6,9,12]:
        print(f"--- {h}M 선행 ---")
        for k in ["deep","deep_F","deep_I","deep_both"]:
            print("  ",lbl[k],fmt(res[seg][h][k]))
print("\n========================= 유의성 (기관/외국인/둘다 − 딥밸류 단독, 부트스트랩 95%CI) =========================")
for tag in ["ALL","IN","OOS"]:
    print(f"\n[{tag}]")
    for h in [6,9,12]:
        for name in ["I","F","both"]:
            s=sig[tag][h][name]
            if s: print(f"  {h}M {name:>4}: Δ평균{s['diff_mean']:+6.1f}%p  t={s['t']:+5.2f}  95%CI[{s['ci_lo']:+.1f},{s['ci_hi']:+.1f}]  P(Δ≤0)={s['p_ge0']:.3f}  n={s['n']}")
        print()
