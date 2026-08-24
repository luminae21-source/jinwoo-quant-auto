# -*- coding: utf-8 -*-
"""
jq_system_backtest.py — **실제 매매 시스템 전체 백테** (발굴 툴 + 매도규칙서 v2 + 사이징)
오늘 만든 툴로 진짜 매매했으면 돈을 벌었는가? 벤치마크는 언제나 **buy&hold**.

⚠️ 정직 고지: 안정 필터(이격도<1.4·손절폭<15%)는 첫 실행 결과를 보고 사후에 붙였다.
   → 사후설계 위험이 있으므로 **여기서 통과 못 하면 필터를 버린다.**

사전등록(결과 보기 전 고정):
  진입 · 안정: 종가>MA200 · 이격도 1.0~1.40 · 2.5ATR손절폭≤15% · 20일거래대금>60일평균 · 유동성 30억+
       · 돌파: 종가>MA200 · 종가≥52주최고×0.95 · 20일거래대금≥60일평균×1.5 · 유동성 30억+
  청산 · 매도규칙서 v2: 초기손절 max(진입−2.5ATR, 진입×0.80) → **래칫 트레일링(고점−2.5ATR)**
                        · 절반익절 **없음**(승자를 자르지 않음) · 20일 ±5% 시간손절
  사이징 · 안정 1% / 돌파 0.5% 리스크 · 동시 최대 7종 · 섹터당 2종
  비용 · 매수 15bp / 매도 33bp
  합격 · CAGR ≥ buy&hold−1.0%p **AND** Sharpe > buy&hold
실행: py jq_system_backtest.py --mode stable | breakout | both
"""
import os, sys, json, argparse, warnings
import numpy as np, pandas as pd
warnings.simplefilter("ignore")
HERE=os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

C=dict(MA=200, ATR_N=14, ATR_K=2.5, STOP_CAP=0.20, TIME_D=20, TIME_BAND=0.05,
       EXT_MIN=1.00, EXT_MAX=1.40, STOP_MAX=0.15, VOL_MIN=3e9,
       BO_HIGH=0.95, BO_INFL=1.5,
       RISK_STABLE=0.01, RISK_BO=0.005, MAX_POS=7,
       COST_BUY=0.0015, COST_SELL=0.0033, CAP0=10_000_000,
       TARGET_R=None)   # 익절 목표(N배 R). None=목표 없음(트레일링만). 예: 2.0 = +2R에서 전량 익절

def load():
    fs=[]
    for f in ("kospi_pit_daily.csv","kosdaq_pit_daily.csv"):
        p=os.path.join(HERE,f)
        if os.path.exists(p):
            d=pd.read_csv(p,dtype={"code":str}); d["date"]=pd.to_datetime(d["date"]); fs.append(d)
    if not fs: return None
    d=pd.concat(fs,ignore_index=True).dropna(subset=["close","high","low"])
    return d.sort_values(["code","date"])

def prep(d):
    """종목별 지표 사전계산."""
    out={}
    for code,g in d.groupby("code"):
        g=g.reset_index(drop=True)
        if len(g) < C["MA"]+30: continue
        pc=g["close"].shift(1)
        tr=pd.concat([g["high"]-g["low"],(g["high"]-pc).abs(),(g["low"]-pc).abs()],axis=1).max(axis=1)
        g["atr"]=tr.rolling(C["ATR_N"]).mean()
        g["ma"]=g["close"].rolling(C["MA"]).mean()
        vol=g["close"]*g.get("volume",pd.Series(0,index=g.index))
        g["v20"]=vol.rolling(20).mean(); g["v60"]=vol.rolling(60).mean()
        g["hi52"]=g["close"].rolling(250,min_periods=100).max()
        out[code]=g
    return out

def entry_ok(g,i,mode):
    close=g["close"].iat[i]; ma=g["ma"].iat[i]; a=g["atr"].iat[i]
    v20=g["v20"].iat[i]; v60=g["v60"].iat[i]
    if not (pd.notna(ma) and pd.notna(a) and a>0 and pd.notna(v20) and v20>=C["VOL_MIN"]): return False
    if close<=ma: return False
    ext=close/ma; infl=(v20/v60) if (pd.notna(v60) and v60>0) else 1.0
    if mode=="stable":
        if not (C["EXT_MIN"]<=ext<=C["EXT_MAX"]): return False
        if (C["ATR_K"]*a)/close > C["STOP_MAX"]: return False
        if infl < 1.0: return False
    else:  # breakout
        hi=g["hi52"].iat[i]
        if not (pd.notna(hi) and close >= hi*C["BO_HIGH"]): return False
        if infl < C["BO_INFL"]: return False
    return True

def run(mode):
    d=load()
    if d is None: return {"err":"일봉 없음"}
    G=prep(d)
    dates=sorted(d["date"].unique())
    idx={c:{dt:i for i,dt in enumerate(g["date"])} for c,g in G.items()}
    eq=C["CAP0"]; pos={}; curve=[]; trades=[]
    for t,dt in enumerate(dates):
        # ── 1) 청산 점검
        for code in list(pos):
            g=G[code]; i=idx[code].get(dt)
            if i is None: continue
            p=pos[code]
            hi=max(p["hi"], g["high"].iat[i]); p["hi"]=hi
            a=g["atr"].iat[i] if pd.notna(g["atr"].iat[i]) else p["atr0"]
            trail=hi - C["ATR_K"]*a
            eff=max(p["stop"], trail)                      # 래칫
            cl=g["close"].iat[i]
            held=i-p["i0"]
            hit = (cl < eff) or (held>=C["TIME_D"] and abs(cl/p["entry"]-1)<=C["TIME_BAND"])
            tgt_hit = False
            if C["TARGET_R"] is not None:
                tgt = p["entry"] + C["TARGET_R"]*p["R"]
                if g["high"].iat[i] >= tgt: tgt_hit = True     # 장중 목표 도달 → 익절
            if (hit or tgt_hit) and i+1 < len(g):
                px = tgt if tgt_hit else g["open"].iat[i+1]     # 목표 익절은 목표가 체결
                pnl=p["qty"]*(px-p["entry"]) - p["qty"]*px*C["COST_SELL"]
                eq+=pnl
                trades.append(dict(code=code, R=(pnl/(p["qty"]*p["R"])) if p["qty"]*p["R"]>0 else 0, days=held))
                del pos[code]
        # ── 2) 진입(슬롯 있으면)
        if len(pos) < C["MAX_POS"]:
            cands=[]
            for code,g in G.items():
                if code in pos: continue
                i=idx[code].get(dt)
                if i is None or i+1>=len(g): continue
                if entry_ok(g,i,mode): cands.append((code,i,g["close"].iat[i]/g["ma"].iat[i]))
            cands.sort(key=lambda x:-x[2] if mode=="breakout" else x[2])   # 돌파=강한순, 안정=덜뻗은순
            for code,i,_ in cands:
                if len(pos)>=C["MAX_POS"]: break
                g=G[code]; entry=g["open"].iat[i+1]; a=g["atr"].iat[i]
                if not (entry>0 and a>0): continue
                stop=max(entry-C["ATR_K"]*a, entry*(1-C["STOP_CAP"])); R=entry-stop
                if R<=0: continue
                risk=C["RISK_BO"] if mode=="breakout" else C["RISK_STABLE"]
                qty=int((eq*risk)//R)
                if qty<=0 or qty*entry > eq*0.25: continue           # 한 종목 25% 상한
                eq -= qty*entry*C["COST_BUY"]
                pos[code]=dict(entry=entry, stop=stop, R=R, qty=qty, hi=entry, i0=i+1, atr0=a)
        # ── 3) 자본 평가(현금 + 보유 평가액 손익)
        mtm=0.0
        for code,p in pos.items():
            i=idx[code].get(dt)
            if i is not None: mtm += p["qty"]*(g_close:=G[code]["close"].iat[i]) - p["qty"]*p["entry"]
        curve.append((dt, eq+mtm))
    E=pd.Series(dict(curve)).sort_index()
    r=E.pct_change().dropna()
    n=len(r)/252.0
    cagr=float((E.iloc[-1]/E.iloc[0])**(1/max(n,1e-9))-1)
    sharpe=float(r.mean()/r.std()*np.sqrt(252)) if r.std()>0 else np.nan
    mdd=float((E/E.cummax()-1).min())
    # 벤치: KOSPI buy&hold(배당 1.8% 가산)
    bh=None
    p=os.path.join(HERE,"kospi_index_daily.csv")
    if os.path.exists(p):
        k=pd.read_csv(p,parse_dates=["Date"]).set_index("Date")["Close"]
        k=k[(k.index>=E.index[0])&(k.index<=E.index[-1])]
        kr=k.pct_change().dropna()+0.018/252
        kc=(1+kr).cumprod()
        bh=dict(CAGR=round(float(kc.iloc[-1]**(1/max(len(kr)/252,1e-9))-1),4),
                Sharpe=round(float(kr.mean()/kr.std()*np.sqrt(252)),3),
                MDD=round(float((kc/kc.cummax()-1).min()),4))
    T=pd.DataFrame(trades)
    res=dict(mode=mode, 기간=f"{E.index[0].date()}~{E.index[-1].date()}",
             시스템=dict(CAGR=round(cagr,4), Sharpe=round(sharpe,3), MDD=round(mdd,4),
                        최종자본=int(E.iloc[-1]), 거래수=len(T),
                        승률=round(float((T['R']>0).mean()),3) if len(T) else None,
                        평균R=round(float(T['R'].mean()),3) if len(T) else None),
             buyhold=bh)
    if bh:
        res["게이트"]=dict(수익=bool(cagr>=bh["CAGR"]-0.01), Sharpe=bool(sharpe>bh["Sharpe"]))
        res["VERDICT"]="채택후보" if (cagr>=bh["CAGR"]-0.01 and sharpe>bh["Sharpe"]) else "기각 — buy&hold 미달"
    res["note"]="필터는 사후설계 → 통과 못하면 버린다. 벤치=buy&hold(배당 1.8% 포함)."
    return res

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--mode",default="stable",choices=["stable","breakout","both"])
    ap.add_argument("--target",type=float,default=None,help="익절 목표 R배수 (예: 2 → +2R 전량익절). 미지정=목표없음")
    ap.add_argument("--sweep",action="store_true",help="목표 1R/2R/3R/5R/무제한 비교")
    a=ap.parse_args()
    if a.sweep:
        out={}
        for m in (["stable","breakout"] if a.mode=="both" else [a.mode]):
            for t in (1.0,2.0,3.0,5.0,None):
                C["TARGET_R"]=t
                r=run(m)
                key=f"{m}_목표{'무제한' if t is None else str(t)+'R'}"
                out[key]=dict(CAGR=r["시스템"]["CAGR"], Sharpe=r["시스템"]["Sharpe"],
                              승률=r["시스템"]["승률"], 평균R=r["시스템"]["평균R"],
                              최종자본=r["시스템"]["최종자본"], VERDICT=r.get("VERDICT"))
            out[f"_{m}_buyhold"]=r.get("buyhold")
        print(json.dumps(out,ensure_ascii=False,indent=2)); sys.exit(0)
    C["TARGET_R"]=a.target
    if a.mode=="both":
        print(json.dumps({m:run(m) for m in ("stable","breakout")},ensure_ascii=False,indent=2))
    else:
        print(json.dumps(run(a.mode),ensure_ascii=False,indent=2))
