#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""라이브_전진기록_갱신.py — #5 백테→라이브 전진 확증 장부 계산기.

백테는 이미 있다. 궁극의 증명은 '앞으로'의 월별 실현이 백테 기대와 어긋나지 않느냐다.
매월말 라이브(또는 모의) 슬리브 월수익을 ledger에 한 줄 추가 → 이 스크립트가 누적 통계·
백테기대와의 괴리(t검정)·경보를 출력. 결과가 좋아서가 아니라 '어긋나지 않음'을 확인하는 게 목적.

ledger CSV 컬럼: month(YYYY-MM), sleeve_ret(라이브 슬리브 월수익, 소수), bench_ret(KOSPI 월수익),
                 n_hold(보유종목수), note
사용:
  python 라이브_전진기록_갱신.py --add 2026-07 0.031 0.018 12 "테크윙 청산"
  python 라이브_전진기록_갱신.py            # 현황 리포트
  python 라이브_전진기록_갱신.py --self-test
백테기대(하드코딩·수정가능): 신호테스트 기준 반등군 12M 근사 → 월 기대 ~+1.0%p 초과(보수적). 실제 진우 값으로 갱신.
"""
import argparse, os, sys
import numpy as np, pandas as pd
LEDGER=os.path.join(os.path.dirname(os.path.abspath(__file__)),"진우_라이브전진기록.csv")
EXP_MONTHLY_EXCESS=0.010   # 백테 기대 초과수익/월(보수적 앵커). ← 진우 실제 백테로 교체.

def load():
    if os.path.exists(LEDGER):
        return pd.read_csv(LEDGER,dtype={"month":str})
    return pd.DataFrame(columns=["month","sleeve_ret","bench_ret","n_hold","note"])

def add(m,s,b,n,note):
    df=load()
    df=df[df["month"]!=m]
    df=pd.concat([df,pd.DataFrame([{"month":m,"sleeve_ret":float(s),"bench_ret":float(b),"n_hold":int(n),"note":note}])],ignore_index=True)
    df=df.sort_values("month"); df.to_csv(LEDGER,index=False,encoding="utf-8-sig")
    print(f"기록: {m} 슬리브{float(s)*100:+.1f}% 벤치{float(b)*100:+.1f}% ({note})")

def report(df):
    if len(df)==0: print("기록 없음. --add 로 월수익 추가."); return
    s=df["sleeve_ret"].astype(float); b=df["bench_ret"].astype(float); ex=s-b
    e=(1+s).cumprod(); n=len(s)
    cagr=(e.iloc[-1]**(12/n)-1) if e.iloc[-1]>0 else float("nan")
    mdd=float((e/e.cummax()-1).min()); sh=(s.mean()/s.std()*np.sqrt(12)) if s.std()>0 else float("nan")
    print("="*70); print(f"라이브 전진기록 · {df['month'].min()}~{df['month'].max()} ({n}개월)"); print("="*70)
    print(f"  누적 슬리브 {e.iloc[-1]:.2f}x · 연율CAGR {cagr*100:+.1f}% · MDD {mdd*100:+.1f}% · Sharpe {sh:.2f}")
    print(f"  월평균 초과(슬리브-벤치) {ex.mean()*100:+.2f}%p · 승월 {(s>0).mean()*100:.0f}% · 초과승월 {(ex>0).mean()*100:.0f}%")
    # 백테기대와 괴리 t검정(초과수익 평균이 기대와 다른가)
    if n>=6 and ex.std()>0:
        t=(ex.mean()-EXP_MONTHLY_EXCESS)/(ex.std()/np.sqrt(n))
        print(f"  기대초과 {EXP_MONTHLY_EXCESS*100:+.1f}%p 대비 t={t:+.2f} "
              f"({'기대와 상충 경보' if t<-2 else '기대와 부합' if abs(t)<=2 else '기대상회'})")
    else:
        print(f"  (n<6 or 무변동 → t검정 보류. 최소 6개월 필요)")
    print("\n  최근 6개월:")
    for _,r in df.tail(6).iterrows():
        print(f"   {r['month']}  슬리브{float(r['sleeve_ret'])*100:>+6.1f}%  벤치{float(r['bench_ret'])*100:>+6.1f}%  n{int(r['n_hold']):>3}  {r['note']}")
    print("\n※ 목적: 백테기대와 '어긋나지 않음' 확인. 6~12개월 누적으로만 판정. 단월 노이즈 무시.")

def self_test():
    import tempfile
    df=pd.DataFrame({"month":["2026-01","2026-02","2026-03","2026-04","2026-05","2026-06"],
                     "sleeve_ret":[0.02,-0.01,0.03,0.01,0.00,0.025],
                     "bench_ret":[0.01,-0.02,0.02,0.00,0.01,0.015],"n_hold":[10]*6,"note":["x"]*6})
    ex=(df["sleeve_ret"]-df["bench_ret"]); assert abs(ex.mean()-0.00583)<1e-3
    print("[OK] self-test 통과"); return 0

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--add",nargs=5,metavar=("MONTH","SLEEVE","BENCH","NHOLD","NOTE"))
    ap.add_argument("--self-test",action="store_true")
    a=ap.parse_args()
    if a.self_test: return self_test()
    if a.add: add(*a.add); 
    report(load()); return 0

if __name__=="__main__": sys.exit(main() or 0)
