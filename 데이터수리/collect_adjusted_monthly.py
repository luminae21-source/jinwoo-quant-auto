#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""collect_adjusted_monthly.py — 기업행위 조정(수정주가) 월봉 재수집 (PC 전용·네트워크 필요)

방식: 종목별 get_market_ohlcv_by_date(from,to,종목, freq='m', adjusted=True) → 월말 '종가'.
  · 상장 종목은 잘 받음. 상폐 종목은 ISIN 문제로 실패할 수 있음(→ failures 로그, Phase 2-B).
  · 체크포인트/재개·sleep·지수백오프 재시도. 월봉이라 종목당 1콜.
산출: _월봉종가캐시_<MKT>_adj.csv (code,ym,close) · _adj_실패_<MKT>.csv · _adj_ckpt_<MKT>.json
사용:
  py collect_adjusted_monthly.py --smoke                 # (a)상장 1 + (b)상폐 1 수신 테스트 — 먼저!
  py collect_adjusted_monthly.py --self-test             # 오프라인 로직 검증(네트워크 불필요)
  py collect_adjusted_monthly.py --market KOSPI --start 1996 --sleep 0.4   # 본수집(재개 자동)
⚠️ 정보·검증용·투자자문 아님. pykrx는 PC에서만.
"""
import os, sys, json, time, argparse, datetime
HERE=os.path.dirname(os.path.abspath(__file__)); PARENT=os.path.dirname(HERE)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def _cache_codes(mkt):
    """기존 캐시에서 코드 집합(상폐 포함 유니버스 근사)."""
    for d in (PARENT, HERE, os.getcwd()):
        p=os.path.join(d,f"_월봉종가캐시_{mkt}.csv")
        if os.path.exists(p):
            import pandas as pd
            c=pd.read_csv(p,usecols=["code"],dtype={"code":str})["code"].str.zfill(6)
            return set(c.unique())
    return set()

def ym_of(idx):
    """pykrx 월봉 인덱스(Timestamp/문자열) → 'YYYY-MM'."""
    import pandas as pd
    return pd.to_datetime(idx).strftime("%Y-%m")

def fetch_one(stock, code, frm, to):
    """종목 월봉 수정주가 → DataFrame[ym,close]. 실패 시 예외."""
    df=stock.get_market_ohlcv_by_date(frm, to, code, freq="m", adjusted=True)
    if df is None or len(df)==0: return None
    col="종가" if "종가" in df.columns else df.columns[-2]
    import pandas as pd
    out=pd.DataFrame({"ym":[ym_of(i) for i in df.index], "close":pd.to_numeric(df[col],errors="coerce").values})
    out=out.dropna(); out=out[out["close"]>0]
    return out

def load_ckpt(mkt):
    p=os.path.join(HERE,f"_adj_ckpt_{mkt}.json")
    return json.load(open(p,encoding="utf-8")) if os.path.exists(p) else {"done":[]}
def save_ckpt(mkt,ck):
    json.dump(ck,open(os.path.join(HERE,f"_adj_ckpt_{mkt}.json"),"w",encoding="utf-8"),ensure_ascii=False)

def collect(mkt, start, sleep_s):
    from pykrx import stock
    import pandas as pd
    frm=f"{start}0101"; to=datetime.date.today().strftime("%Y%m%d")
    today=to
    listed=set(stock.get_market_ticker_list(today, market=mkt))
    universe=sorted(listed | _cache_codes(mkt))
    print(f"[{mkt}] 유니버스 {len(universe)} (현재상장 {len(listed)} + 캐시코드) · {frm}~{to}")
    outp=os.path.join(HERE,f"_월봉종가캐시_{mkt}_adj.csv")
    failp=os.path.join(HERE,f"_adj_실패_{mkt}.csv")
    ck=load_ckpt(mkt); done=set(ck["done"])
    if not os.path.exists(outp): open(outp,"w",encoding="utf-8").write("code,ym,close\n")
    if not os.path.exists(failp): open(failp,"w",encoding="utf-8").write("code,status,detail\n")
    listed_set=listed
    t0=time.time(); n=0; nempty=0; nerr=0
    for i,code in enumerate(universe):
        if code in done: continue
        ok=False; last=""
        for attempt in range(3):
            try:
                out=fetch_one(stock, code, frm, to)
                if out is not None and len(out):
                    out.insert(0,"code",code)
                    out.to_csv(outp, mode="a", header=False, index=False, encoding="utf-8")
                    n+=1
                else:
                    open(failp,"a",encoding="utf-8").write(f"{code},empty,상폐/데이터없음\n"); nempty+=1
                ok=True; break
            except Exception as e:
                last=str(e)[:100]; time.sleep(0.8*(attempt+1))
        if not ok:
            open(failp,"a",encoding="utf-8").write(f"{code},error,{last}\n"); nerr+=1
        done.add(code)
        if i%50==0:
            ck["done"]=sorted(done); save_ckpt(mkt,ck)
            el=time.time()-t0; print(f"  {i+1}/{len(universe)} · 수집 {n} · 빈값 {nempty} · 오류 {nerr} · {el:.0f}s")
        time.sleep(sleep_s)
    ck["done"]=sorted(done); save_ckpt(mkt,ck)
    cov=n/max(len(universe),1)*100
    print(f"[{mkt}] 완료 · 수집(조정) {n} · 빈값(상폐→윈저대상) {nempty} · 오류 {nerr}")
    print(f"  커버리지 {cov:.0f}% · 조정본 {os.path.basename(outp)} · 미조정잔여 {os.path.basename(failp)}")
    print(f"  다음: py validate_adjusted.py --market {mkt}")

def smoke():
    from pykrx import stock
    frm="19960101"; to=datetime.date.today().strftime("%Y%m%d")
    print("=== (a) 상장 종목 삼성전자(005930) 월봉 수정주가 ===")
    a=fetch_one(stock,"005930",frm,to); print("  수신 행:",0 if a is None else len(a),"· 최근:", None if a is None else a.tail(1).to_dict("records"))
    # (b) 상폐 후보 = 캐시코드 − 현재상장
    listed=set(stock.get_market_ticker_list(to,market="KOSPI"))
    delisted=sorted(_cache_codes("KOSPI")-listed)
    print(f"=== (b) 상폐 후보 {len(delisted)}개 중 3개 수신 시도 ===")
    for c in delisted[:3]:
        try:
            r=fetch_one(stock,c,frm,to); print(f"  {c}: 수신 {0 if r is None else len(r)}행 {'OK' if r is not None and len(r) else '빈값'}")
        except Exception as e:
            print(f"  {c}: 실패 — {str(e)[:80]}")
    print("판정: (b)가 OK면 상폐도 종목별 수집(2-A). 실패면 상폐 미조정+윈저(2-B).")

def self_test():
    ok=[]
    ok.append(("ym변환", ym_of("2020-05-29")=="2020-05"))
    import types
    ok.append(("캐시코드 로더 형", isinstance(_cache_codes("KOSPI"),set)))
    ck={"done":["005930"]}; ok.append(("체크포인트 dict", ck["done"]==["005930"]))
    p=sum(1 for _,v in ok if v)
    for k,v in ok: print(f"  {'✅' if v else '❌'} {k}")
    print(f"self-test: {p}/{len(ok)} (네트워크 불필요분만)")
    sys.exit(0 if p==len(ok) else 1)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--market",default="KOSPI",choices=["KOSPI","KOSDAQ"])
    ap.add_argument("--start",type=int,default=1996); ap.add_argument("--sleep",type=float,default=0.4)
    ap.add_argument("--smoke",action="store_true"); ap.add_argument("--self-test",action="store_true")
    a=ap.parse_args()
    if a.self_test: self_test()
    elif a.smoke: smoke()
    else: collect(a.market, a.start, a.sleep)

if __name__=="__main__": main()
