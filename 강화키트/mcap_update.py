#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""mcap_update.py — [PC] 종목시총_30년.csv 증분 갱신 (전 종목, 빠름)

종목시총_30년.csv 는 월말 시총 패널(date,code,mcap). 여기에
  · 마지막 저장월 이후의 각 월말 시총
  · 이번달 최신 거래일 시총(=현재 유니버스 랭킹용)
만 pykrx get_market_cap_by_ticker(날짜,"ALL") 로 받아 append.
(진우_일봉_증분수집.py 와 같은 '마지막날 이후만' 증분 방식 · 생존편향 무관: 그날 상장 전 종목)

사용:  py mcap_update.py              (증분 갱신)
       py mcap_update.py --self-test (네트워크 없이 로직 점검)
※ pykrx 필요, 네트워크는 PC. 산출: 종목시총_30년.csv 갱신.
⚠️ 정보·검증용. 투자자문 아님·책임 본인.
"""
import os, sys, csv, argparse
from datetime import date, timedelta
HERE=os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def find_panel():
    for d in (HERE, os.path.dirname(HERE)):
        p=os.path.join(d,"종목시총_30년.csv")
        if os.path.exists(p): return p
    return os.path.join(os.path.dirname(HERE),"종목시총_30년.csv")

def existing_dates(path):
    s=set(); last=None
    if os.path.exists(path):
        with open(path,encoding="utf-8-sig") as f:
            r=csv.reader(f); next(r,None)
            for row in r:
                if row and len(row[0])==10:
                    s.add(row[0]);
                    if last is None or row[0]>last: last=row[0]
    return s, last

def month_end_targets(last_date_str, today):
    """마지막 저장월 다음달~지난달의 월말(달력 말일) + 오늘."""
    out=[]
    if last_date_str:
        y,m=int(last_date_str[:4]),int(last_date_str[5:7])
    else:
        y,m=today.year-1,today.month
    # 다음달부터
    m+=1
    if m>12: y+=1; m=1
    while (y,m)<(today.year,today.month):
        # 달력 말일
        if m==12: nd=date(y+1,1,1)-timedelta(days=1)
        else: nd=date(y,m+1,1)-timedelta(days=1)
        out.append(nd)
        m+=1
        if m>12: y+=1; m=1
    out.append(today)   # 이번달 최신
    return out

def _fetch_day(stock, dd):
    """그날 전 종목 시총(KOSPI+KOSDAQ 합침). 양수 시총이 있는 '실제 거래일'만 반환.
    (휴일 조회 시 pykrx가 종목목록은 주되 시총 0/NaN → 무효 처리)."""
    import pandas as pd
    parts=[]
    for mk in ("KOSPI","KOSDAQ"):
        try:
            x=stock.get_market_cap_by_ticker(dd, market=mk)
            if x is not None and len(x): parts.append(x)
        except Exception:
            pass
    if not parts:
        try:
            x=stock.get_market_cap_by_ticker(dd, market="ALL")
            if x is not None and len(x): parts.append(x)
        except Exception:
            pass
    if not parts: return None
    df=pd.concat(parts)
    col="시가총액" if "시가총액" in df.columns else None
    if col is None: return None
    df=df.copy(); df["_mcap"]=pd.to_numeric(df[col],errors="coerce")
    df=df[df["_mcap"]>0]
    return df if len(df) else None

def last_trading_on_or_before(stock, d):
    for i in range(8):
        dd=(d - timedelta(days=i)).strftime("%Y%m%d")
        df=_fetch_day(stock, dd)
        if df is not None and len(df):
            print(f"    {dd}: {len(df)}종 시총 수신(양수)")
            return dd, df
    return None, None

def run():
    try:
        from pykrx import stock
    except ImportError:
        print("pykrx 미설치 → pip install pykrx"); return
    path=find_panel(); seen,last=existing_dates(path)
    print(f"종목시총_30년.csv 마지막 저장일: {last} · 기존 {len(seen)} 날짜")
    today=date.today()
    targets=month_end_targets(last, today)
    new_rows=[]; added_dates=[]
    for d in targets:
        dd,df=last_trading_on_or_before(stock,d)
        if not dd: continue
        ds=f"{dd[:4]}-{dd[4:6]}-{dd[6:8]}"
        if ds in seen: continue
        for tkr,mc in zip(df.index, df["_mcap"]):
            try: mcv=float(mc)
            except Exception: continue
            if mcv>0: new_rows.append((ds,str(tkr).zfill(6),int(mcv)))
        seen.add(ds); added_dates.append(ds)
    if not new_rows:
        print("추가할 신규 시총 없음 (이미 최신)."); return
    with open(path,"a",encoding="utf-8-sig",newline="") as f:
        w=csv.writer(f)
        for r in new_rows: w.writerow(r)
    print(f"추가: {len(new_rows):,}행 · 신규 날짜 {added_dates}")
    print("→ 종목시총_30년.csv 최신화 완료.")

def _selftest():
    ok=tot=0
    def chk(n,c):
        nonlocal ok,tot; tot+=1; ok+=1 if c else 0; print(f"  [{'OK' if c else 'FAIL'}] {n}")
    t=month_end_targets("2026-05-31", date(2026,7,26))
    chk("2026-05말 이후 → 6월말 포함", date(2026,6,30) in t)
    chk("오늘(7/26) 포함", date(2026,7,26) in t)
    chk("7월말(미래) 미포함", date(2026,7,31) not in t)
    t2=month_end_targets(None, date(2026,7,26))
    chk("last 없을 때도 오늘 포함", date(2026,7,26) in t2)
    print(f"\n셀프테스트: {ok}/{tot}"); return ok==tot

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--self-test",action="store_true"); a=ap.parse_args()
    if a.self_test: sys.exit(0 if _selftest() else 1)
    run()

if __name__=="__main__":
    main()
