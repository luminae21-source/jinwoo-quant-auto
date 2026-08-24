# 가격기반 breakout 확인 변형(거래량 대용). 검증된 backtest_kosdaq_breakout 로더 재사용.
import importlib.util, sys
from datetime import date
spec=importlib.util.spec_from_file_location("bk","/sessions/confident-jolly-brown/mnt/Desktop--진우퀀트/backtest_kosdaq_breakout.py")
bk=importlib.util.module_from_spec(spec); spec.loader.exec_module(bk)

def high_n(series,d0,n):
    past=[c for d,c in series if d<=d0]
    return max(past[-n:]) if len(past)>=n else None

def run_confirm(mode):
    px=bk.load_daily(); alld=sorted({d for s in px.values() for d,_ in s})
    ms=[d for d in bk.month_starts(alld) if d>=date(2020,1,1)]
    pr,ew=[],[]; prev=set()
    for i in range(len(ms)-1):
        d0,d1=ms[i],ms[i+1]
        prox={}
        for c,s in px.items():
            p,last=bk.proximity(s,d0)
            if p is None: continue
            ok=True
            if mode=="newhigh": ok = p>=0.999            # 종가=252일 신고가 갱신
            elif mode=="20d":   h20=high_n(s,d0,20); ok = (h20 is not None and last>=h20 and p>=0.95)
            if ok: prox[c]=p
        ewr=[bk.ret_between(px[c],d0,d1) for c in {c for c,s in px.items() if bk.proximity(s,d0)[0] is not None}]
        ewr=[r for r in ewr if r is not None]
        if not ewr or len(prox)<3: 
            if ewr: ew.append(sum(ewr)/len(ewr)); pr.append(0.0)
            continue
        ew.append(sum(ewr)/len(ewr))
        k=max(3,int(len(prox)*0.20))
        picks=[c for c,_ in sorted(prox.items(),key=lambda kv:-kv[1])[:k]]
        rs=[bk.ret_between(px[c],d0,d1) for c in picks]; rs=[r for r in rs if r is not None]
        g=sum(rs)/len(rs) if rs else 0.0
        turn=len(set(picks)^prev)/(2*max(1,len(picks))); pr.append(g-turn*bk.COST); prev=set(picks)
    n=min(len(pr),len(ew)); pr,ew=pr[:n],ew[:n]
    mp=bk.metrics(pr,ew); me=bk.metrics(ew,ew)
    print("  [%-8s] picks CAGR %+.2f%% Sharpe %s MDD %+.2f%% IR_EW %s | EW %+.2f%% | alpha %+.2f%%p (n=%d, 평균종목/월≈top20%%)"%(
        mode,mp["CAGR%"],mp["Sharpe"],mp["MDD%"],mp["IR_EW"],me["CAGR%"],mp["CAGR%"]-me["CAGR%"],n))

print("=== breakout 확인 변형 (가격기반, 거래량 대용) — EW 벤치 동일 ===")
run_confirm("none")     # = 기존 단순 breakout 재확인
run_confirm("20d")      # 20일 고점 동반 돌파
run_confirm("newhigh")  # 252일 신고가 갱신만
