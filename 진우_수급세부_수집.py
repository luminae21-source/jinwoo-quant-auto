#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우_수급세부_수집.py — 투자자 유형별(개인·기타법인·연기금·사모·투신…) 순매수 대량수집 (★PC 전용).

목적: "바닥을 잡는 주체가 진짜 개인인가, 아니면 기타법인(자사주·지주·세력)·연기금 등 특정 주체인가"를
      정밀 검증. (기존은 개인=−(기관+외국인) 역산 = 개인+기타법인 섞임)
방법: get_market_net_purchases_of_equities_by_ticker(월,투자자) 대량조회(전 종목 1콜/월·유형).
출력: flow_detail_monthly_{KOSPI,KOSDAQ}.csv  (code,date,investor,net)  ※순매수거래대금(원)
사용(PC): pip install pykrx pandas
  py 진우_수급세부_수집.py --market KOSPI --start 2002-01-02
  py 진우_수급세부_수집.py --market KOSDAQ --start 2002-01-02
  # 유형 바꾸려면 --investors 개인,기타법인,연기금,사모,투신
  이후: py 검증_바닥주체.py
"""
import argparse, csv, os, sys, calendar, datetime as dt, time, io, contextlib
BASE=os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
def log(*a): print(*a); sys.stdout.flush()

def month_range(start,end):
    y,m=int(start[:4]),int(start[4:6]); ey,em=int(end[:4]),int(end[4:6])
    while (y,m)<=(ey,em):
        last=calendar.monthrange(y,m)[1]; yield f"{y}-{m:02d}",f"{y}{m:02d}01",f"{y}{m:02d}{last:02d}"
        m+=1
        if m>12: m=1;y+=1
def _quiet(fn,*a):
    buf=io.StringIO()
    with contextlib.redirect_stdout(buf),contextlib.redirect_stderr(buf): return fn(*a)
def netmap(stock,fs,fe,market,inv):
    try: df=_quiet(stock.get_market_net_purchases_of_equities_by_ticker,fs,fe,market,inv)
    except Exception: return None
    if df is None or len(df)==0 or "순매수거래대금" not in df.columns: return {}
    out={}
    for tk in df.index:
        try: out[str(tk).zfill(6)]=float(df["순매수거래대금"].loc[tk])
        except Exception: continue
    return out

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--market",choices=["KOSPI","KOSDAQ"],required=True)
    ap.add_argument("--start",default="2002-01-02"); ap.add_argument("--end",default=None)
    ap.add_argument("--investors",default="개인,기타법인,연기금,사모,투신")
    ap.add_argument("--sleep",type=float,default=0.03)
    a=ap.parse_args()
    try: from pykrx import stock
    except ImportError: sys.exit("pykrx 미설치 → pip install pykrx")
    start=a.start.replace("-",""); end=(a.end or dt.date.today().isoformat()).replace("-","")
    invs=[x.strip() for x in a.investors.split(",") if x.strip()]
    out=os.path.join(BASE,f"flow_detail_monthly_{a.market}.csv")
    ck=os.path.join(BASE,f"_fetch_detail_ckpt_{a.market}.txt")
    done=set(open(ck,encoding="utf-8").read().split()) if os.path.exists(ck) else set()
    periods=list(month_range(start,end))
    todo=[(lbl,fs,fe,iv) for (lbl,fs,fe) in periods for iv in invs if f"{lbl}|{iv}" not in done]
    log(f"[{a.market}] 세부수급 | 유형 {invs} | 남은 {len(todo)}(월×유형) | {a.start}~{a.end or 'today'}")
    newfile=not os.path.exists(out); t0=time.time(); n=0
    fh=open(out,"a",encoding="utf-8-sig",newline=""); w=csv.writer(fh)
    if newfile: w.writerow(["code","date","investor","net"])
    for i,(lbl,fs,fe,iv) in enumerate(todo):
        mp=netmap(stock,fs,fe,a.market,iv)
        if mp is None:
            log(f"  ! {lbl}/{iv} 실패"); continue
        date=f"{fe[:4]}-{fe[4:6]}-{fe[6:8]}"
        for c,v in mp.items(): w.writerow([c,date,iv,f"{v:.0f}"]); n+=1
        fh.flush(); open(ck,"a",encoding="utf-8").write(f"{lbl}|{iv}\n")
        if a.sleep: time.sleep(a.sleep)
        if (i+1)%40==0:
            el=time.time()-t0; eta=(len(todo)-i-1)/((i+1)/el)/60 if el else 0
            log(f"  ...{i+1}/{len(todo)} | 행 {n} | ETA {eta:.0f}분")
    fh.close(); log(f"완료 [{a.market}] 행 {n} → {os.path.basename(out)}\n다음: py 검증_바닥주체.py")

if __name__=="__main__": main()
