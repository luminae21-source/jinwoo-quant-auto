# -*- coding: utf-8 -*-
"""
jq_expectancy_backtest.py — 트레이딩 이론 ①: **매도규칙서의 기대값(R) 측정**.
오늘 세션 내내 "매도규칙서 청산 미구현"으로 남겨둔 부분을 **일봉으로 정확히 구현**한다.

핵심 질문: 우리 시스템의 엣지는 '예측'이 아니라 '비대칭 청산'에 있는가?
  → 거래별 R배수 분포 → **기대값 E[R] > 0 인가.** (E[R]≤0이면 사이징도 무의미)

사전등록(튜닝 금지):
  진입 = 종가가 200일선 **상향 돌파**(전일 아래→당일 위) → **익일 시가** 매수.
  청산 = 매도규칙서 그대로:
    · 손절 = max(진입가 − 2.5×ATR14, 진입가×0.80)  [종가 이탈 → 익일 시가 청산]
    · +1R(=진입가−손절가) 도달 → **절반 익절**, 나머지는 트레일링
    · 트레일링 = (진입 후 고점) − 2.5×ATR14  [종가 이탈 → 익일 청산]
    · 시간손절 = 20거래일 경과 시 ±5% 이내면 청산
  비용 = 매수 15bp, 매도 33bp(거래세 0.18%+수수료).
데이터: kospi_pit_daily.csv · kosdaq_pit_daily.csv (2019-07~). 무수정: production·L1 불변.
실행: py jq_expectancy_backtest.py --selftest | --run
"""
import os, sys, json, argparse, warnings
import numpy as np, pandas as pd
warnings.simplefilter("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

CFG = dict(MA=200, ATR_N=14, ATR_K=2.5, STOP_CAP=0.20, TRAIL_K=2.5,
           TIME_STOP_D=20, TIME_BAND=0.05, MAX_HOLD=250,
           COST_BUY=0.0015, COST_SELL=0.0033,
           HALF_EXIT=True)   # False = 절반익절 제거(트레이딩 이론 처방: 승자를 자르지 마라)

def load_daily():
    frames=[]
    for f in ("kospi_pit_daily.csv","kosdaq_pit_daily.csv"):
        p=os.path.join(HERE,f)
        if os.path.exists(p):
            d=pd.read_csv(p,dtype={"code":str})
            d["date"]=pd.to_datetime(d["date"]); frames.append(d[["code","date","open","high","low","close"]])
    if not frames: return None
    d=pd.concat(frames,ignore_index=True).dropna()
    return d.sort_values(["code","date"])

def atr(df, n):
    pc=df["close"].shift(1)
    tr=pd.concat([df["high"]-df["low"], (df["high"]-pc).abs(), (df["low"]-pc).abs()],axis=1).max(axis=1)
    return tr.rolling(n).mean()

def simulate_stock(g):
    """한 종목의 모든 진입·청산 시뮬 → 거래 리스트(R배수)."""
    c=CFG; g=g.reset_index(drop=True)
    if len(g) < c["MA"]+30: return []
    g["ma"]=g["close"].rolling(c["MA"]).mean(); g["atr"]=atr(g,c["ATR_N"])
    cross=(g["close"]>g["ma"]) & (g["close"].shift(1)<=g["ma"].shift(1))
    trades=[]; i=0; n=len(g)
    while i < n-1:
        if not (cross.iloc[i] and pd.notna(g["atr"].iloc[i]) and pd.notna(g["ma"].iloc[i])):
            i+=1; continue
        e=i+1                                        # 익일 시가 진입
        if e>=n: break
        entry=g["open"].iloc[e]
        a0=g["atr"].iloc[i]
        if not (entry>0 and a0>0): i+=1; continue
        stop=max(entry - c["ATR_K"]*a0, entry*(1-c["STOP_CAP"]))
        R=entry-stop
        if R<=0: i+=1; continue
        target=entry+R
        half=False; hi=entry; realized=0.0; qty=1.0; exit_j=None
        for j in range(e, min(e+c["MAX_HOLD"], n)):
            hi=max(hi, g["high"].iloc[j])
            aj=g["atr"].iloc[j] if pd.notna(g["atr"].iloc[j]) else a0
            trail=hi - c["TRAIL_K"]*aj
            # +1R 절반 익절(장중 도달 시 목표가 체결) — HALF_EXIT=False면 승자를 자르지 않음
            if c["HALF_EXIT"] and (not half) and g["high"].iloc[j] >= target:
                realized += 0.5*(target-entry); qty=0.5; half=True
            cl=g["close"].iloc[j]
            # 원본: +1R 절반익절 후에만 트레일링. 변형(HALF_EXIT=False): 전 포지션에 래칫 트레일링.
            use_trail = half or (not c["HALF_EXIT"])
            hit_stop = (cl < max(stop, trail)) if use_trail else (cl < stop)
            hit_time = (j-e >= c["TIME_STOP_D"]) and (abs(cl/entry-1) <= c["TIME_BAND"])
            if hit_stop or hit_time or j==min(e+c["MAX_HOLD"],n)-1:
                k=min(j+1, n-1); px=g["open"].iloc[k]     # 익일 시가 청산
                realized += qty*(px-entry); exit_j=k; break
        if exit_j is None: i+=1; continue
        # 비용(진입 1회 + 청산; 절반익절도 매도 비용)
        cost = entry*c["COST_BUY"] + (0.5*target*c["COST_SELL"] if half else 0) + (qty*g["open"].iloc[exit_j]*c["COST_SELL"])
        r_mult = (realized - cost)/R
        trades.append(dict(code=g["code"].iloc[0], entry_date=str(g["date"].iloc[e].date()),
                           exit_date=str(g["date"].iloc[exit_j].date()), days=int(exit_j-e),
                           entry=float(entry), stop=float(stop), R=float(r_mult), half=bool(half)))
        i = exit_j + 1                                # 청산 후 재진입 탐색
    return trades

def run():
    d=load_daily()
    if d is None: return {"err":"일봉 파일 없음"}
    all_tr=[]
    for code,g in d.groupby("code"):
        all_tr += simulate_stock(g)
    if not all_tr: return {"err":"거래 없음"}
    T=pd.DataFrame(all_tr); R=T["R"]
    win=R[R>0]; loss=R[R<=0]
    exp_R=float(R.mean())
    # 최대 연속 손실
    streak=mx=0
    for r in R:
        streak = streak+1 if r<=0 else 0; mx=max(mx,streak)
    out=dict(
        trades=int(len(T)), 승률=round(float((R>0).mean()),3),
        평균승_R=round(float(win.mean()) if len(win) else 0,3),
        평균패_R=round(float(loss.mean()) if len(loss) else 0,3),
        **{"기대값_E[R]": round(exp_R,3)},
        R_표준편차=round(float(R.std()),3), 최대연속손실=int(mx),
        평균보유일=round(float(T["days"].mean()),1), 절반익절_도달률=round(float(T["half"].mean()),3),
        R_분위=dict(p10=round(float(R.quantile(.1)),2), p50=round(float(R.quantile(.5)),2),
                    p90=round(float(R.quantile(.9)),2), max=round(float(R.max()),2), min=round(float(R.min()),2)),
        판정=("기대값 양수 → 사이징 논의 가능" if exp_R>0 else "기대값 ≤0 → 엣지 없음(사이징 무의미)"),
        note="매도규칙서 일봉 정확구현. 진입=MA200 상향돌파. 비용 매수15bp·매도33bp. 자본곡선/사이징은 ②단계.")
    T.to_csv(os.path.join(HERE,"expectancy_trades.csv"),index=False,encoding="utf-8-sig")
    out["거래내역"]="expectancy_trades.csv 저장"
    return out

def selftest():
    d=load_daily()
    if d is None: print("[selftest] 일봉 없음"); return
    print(f"[selftest] 일봉 {len(d):,}행 · {d['code'].nunique()}종목 ({d['date'].min().date()}~{d['date'].max().date()})")
    g=d[d["code"]==d["code"].iloc[0]]
    tr=simulate_stock(g)
    print(f"  · 샘플종목 {g['code'].iloc[0]} 거래 {len(tr)}건")
    if tr: print("   ", {k:tr[0][k] for k in ("entry_date","exit_date","days","R","half")})
    print("[selftest] OK — 전체 측정은 --run (수 분 소요)")

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--selftest",action="store_true"); ap.add_argument("--run",action="store_true")
    ap.add_argument("--no-half",action="store_true",help="절반익절 제거(트레이딩 이론 처방: 승자를 자르지 마라)")
    a=ap.parse_args()
    if a.no_half: CFG["HALF_EXIT"]=False
    if a.selftest: selftest()
    elif a.run: print(json.dumps(run(),ensure_ascii=False,indent=2))
    else: print("사용: --selftest | --run [--no-half]")
