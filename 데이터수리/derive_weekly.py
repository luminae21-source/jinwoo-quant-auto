#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""derive_weekly.py — 수정 '주봉' OHLCV를 일봉에서 파생 (오프라인·네트워크 불필요)

원칙: 주봉을 따로 수집하지 않는다. 이미 받은 수정 일봉을 리샘플하면 정합성이 보장되고 콜도 아낀다.
  (같은 데이터를 두 번 긁으면 불일치·중복검증만 늘어난다 — 범위 통제.)
방식: 주(월~금) 단위 그룹 → open=첫날 시가, high=주중 최고, low=주중 최저, close=마지막 종가, volume=합.
입력: _일봉OHLCV_<MKT>_adj.csv   출력: _주봉OHLCV_<MKT>_adj.csv
사용: py derive_weekly.py --market KOSPI   (일봉 수집 완료 후)
⚠️ 정보·검증용·투자자문 아님.
"""
import os, sys, argparse
HERE=os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def derive(mkt):
    import pandas as pd
    inp=os.path.join(HERE,f"_일봉OHLCV_{mkt}_adj.csv")
    if not os.path.exists(inp):
        print(f"[{mkt}] 일봉 파일 없음: {inp} — 먼저 collect_adjusted_daily.py 실행"); sys.exit(1)
    outp=os.path.join(HERE,f"_주봉OHLCV_{mkt}_adj.csv")
    df=pd.read_csv(inp,dtype={"code":str}); df["code"]=df["code"].str.zfill(6)
    df["date"]=pd.to_datetime(df["date"])
    parts=[]
    for code,g in df.groupby("code"):
        g=g.sort_values("date").set_index("date")
        w=g.resample("W-FRI").agg(open=("open","first"),high=("high","max"),
                                  low=("low","min"),close=("close","last"),volume=("volume","sum")).dropna(subset=["close"])
        if len(w):
            w=w.reset_index(); w.insert(0,"code",code)
            w["date"]=w["date"].dt.strftime("%Y-%m-%d"); parts.append(w)
    if not parts:
        print(f"[{mkt}] 파생할 데이터 없음"); sys.exit(1)
    out=pd.concat(parts,ignore_index=True)
    out.to_csv(outp,index=False,encoding="utf-8")
    print(f"[{mkt}] 주봉 파생 완료 · 종목 {out['code'].nunique()} · 행 {len(out):,} · {os.path.basename(outp)}")

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--market",default="KOSPI",choices=["KOSPI","KOSDAQ"])
    derive(ap.parse_args().market)

if __name__=="__main__": main()
