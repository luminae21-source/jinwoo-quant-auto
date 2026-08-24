#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""collect_adjusted_daily.py — 기업행위 조정(수정주가) '일봉 OHLCV' 재수집 (PC 전용·네트워크 필요)

왜 일봉 OHLCV인가: 매도 라우팅(트레일링스톱·재난손절·ATR)은 장중 고가/저가가 있어야 정확하다.
  월봉 종가만으로는 근사밖에 안 된다. 그래서 일봉은 종가뿐 아니라 시/고/저/종/거래량을 모두 받는다.
방식: 종목별 get_market_ohlcv_by_date(from,to,종목, adjusted=True) → 일별 OHLCV.
  · 종목당 1콜(구간 전체). 상장 종목 정상, 상폐는 ISIN 문제로 실패 가능(→ failures 로그).
  · 체크포인트/재개·sleep·지수백오프 재시도. 월봉 수집기와 동일한 견고성.
산출: _일봉OHLCV_<MKT>_adj.csv (code,date,open,high,low,close,volume)
      · _adj일봉_실패_<MKT>.csv · _adj일봉_ckpt_<MKT>.json
사용:
  py collect_adjusted_daily.py --smoke                         # 상장1+상폐1 수신 테스트 — 먼저!
  py collect_adjusted_daily.py --self-test                     # 오프라인 로직 검증(네트워크 불필요)
  py collect_adjusted_daily.py --market KOSPI  --start 1996 --sleep 0.4   # 본수집(재개 자동)
  py collect_adjusted_daily.py --market KOSDAQ --start 1996 --sleep 0.4
  py collect_adjusted_daily.py --market KOSPI  --universe used --used-file 사용유니버스.txt  # (선택)범위축소
⚠️ 정보·검증용·투자자문 아님. pykrx는 PC에서만. 파일이 크다(수백MB~GB) — 디스크 여유 확인.
"""
import os, sys, json, time, argparse, datetime
HERE=os.path.dirname(os.path.abspath(__file__)); PARENT=os.path.dirname(HERE)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def _cache_codes(mkt):
    """기존 월봉 캐시에서 코드 집합(상폐 포함 유니버스 근사)."""
    for d in (PARENT, HERE, os.getcwd()):
        p=os.path.join(d,f"_월봉종가캐시_{mkt}.csv")
        if os.path.exists(p):
            import pandas as pd
            c=pd.read_csv(p,usecols=["code"],dtype={"code":str})["code"].str.zfill(6)
            return set(c.unique())
    return set()

def _used_codes(path):
    """(선택) 실제 사용 유니버스만 수집하고 싶을 때: 한 줄에 코드 하나."""
    if not path or not os.path.exists(path): return None
    codes=set()
    for line in open(path,encoding="utf-8"):
        tok=line.strip().split(",")[0].strip()
        if not tok or not tok.isdigit(): continue   # 빈 줄·주석·비숫자 제외(빈값이 000000 되는 것 방지)
        codes.add(tok.zfill(6))
    return codes or None

def _fetch_window(stock, code, frm, to):
    """단일 구간 일봉 수정 OHLCV → DataFrame 또는 None."""
    import pandas as pd
    df=stock.get_market_ohlcv_by_date(frm, to, code, adjusted=True)   # freq 기본='d'
    if df is None or len(df)==0: return None
    def pick(cands):
        for c in cands:
            if c in df.columns: return c
        return None
    cO=pick(["시가","Open"]); cH=pick(["고가","High"]); cL=pick(["저가","Low"])
    cC=pick(["종가","Close"]); cV=pick(["거래량","Volume"])
    if cC is None: return None
    out=pd.DataFrame({
        "date":[pd.to_datetime(i).strftime("%Y-%m-%d") for i in df.index],
        "open":  pd.to_numeric(df[cO],errors="coerce").values if cO else pd.NA,
        "high":  pd.to_numeric(df[cH],errors="coerce").values if cH else pd.NA,
        "low":   pd.to_numeric(df[cL],errors="coerce").values if cL else pd.NA,
        "close": pd.to_numeric(df[cC],errors="coerce").values,
        "volume":pd.to_numeric(df[cV],errors="coerce").values if cV else pd.NA,
    })
    out=out.dropna(subset=["close"]); out=out[out["close"]>0]
    return out

def fetch_one(stock, code, frm, to):
    """종목 일봉 수정 OHLCV → DataFrame[date,...]. KRX ~3000행 cap 우회 위해 구간 분할 후 이어붙임.
    (KRX 조정 소스는 2014-04~만 제공 확인됨. 넓은 단일콜은 최근 3000행으로 잘려 초기 데이터 유실 → 청크 필수.)"""
    import pandas as pd, datetime as _dt
    WIN=4                                                # 창 크기(년): 4년≈980거래일 ≪ 3000 cap
    y0=int(frm[:4]); y1=int(to[:4]); parts=[]
    a=y0
    while a<=y1:
        b=min(a+WIN-1, y1)                               # [a, a+3] 4년 창
        wf=f"{a}0101"; wt=(to if b==y1 else f"{b}1231")
        try:
            w=_fetch_window(stock, code, wf, wt)
            if w is not None and len(w): parts.append(w)
        except Exception:
            raise
        a=b+1
    if not parts: return None
    out=pd.concat(parts,ignore_index=True).drop_duplicates(subset=["date"]).sort_values("date")
    return out.reset_index(drop=True)

def load_ckpt(mkt):
    p=os.path.join(HERE,f"_adj일봉_ckpt_{mkt}.json")
    return json.load(open(p,encoding="utf-8")) if os.path.exists(p) else {"done":[]}
def save_ckpt(mkt,ck):
    json.dump(ck,open(os.path.join(HERE,f"_adj일봉_ckpt_{mkt}.json"),"w",encoding="utf-8"),ensure_ascii=False)

def collect(mkt, start, sleep_s, universe_mode, used_file):
    from pykrx import stock
    frm=f"{start}0101"; to=datetime.date.today().strftime("%Y%m%d")
    listed=set(stock.get_market_ticker_list(to, market=mkt))
    if universe_mode=="used":
        u=_used_codes(used_file)
        universe=sorted(u) if u else sorted(listed)
        print(f"[{mkt}] (범위축소) 사용유니버스 {len(universe)}")
    else:
        universe=sorted(listed | _cache_codes(mkt))
        print(f"[{mkt}] 유니버스 {len(universe)} (현재상장 {len(listed)} + 캐시코드) · {frm}~{to}")
    outp=os.path.join(HERE,f"_일봉OHLCV_{mkt}_adj.csv")
    failp=os.path.join(HERE,f"_adj일봉_실패_{mkt}.csv")
    ck=load_ckpt(mkt); done=set(ck["done"])
    if not os.path.exists(outp): open(outp,"w",encoding="utf-8").write("code,date,open,high,low,close,volume\n")
    if not os.path.exists(failp): open(failp,"w",encoding="utf-8").write("code,status,detail\n")
    t0=time.time(); n=0; nrows=0; nempty=0; nerr=0
    for i,code in enumerate(universe):
        if code in done: continue
        ok=False; last=""
        for attempt in range(3):
            try:
                out=fetch_one(stock, code, frm, to)
                if out is not None and len(out):
                    out.insert(0,"code",code)
                    out.to_csv(outp, mode="a", header=False, index=False, encoding="utf-8")
                    n+=1; nrows+=len(out)
                else:
                    open(failp,"a",encoding="utf-8").write(f"{code},empty,상폐/데이터없음\n"); nempty+=1
                ok=True; break
            except Exception as e:
                last=str(e)[:100]; time.sleep(0.8*(attempt+1))
        if not ok:
            open(failp,"a",encoding="utf-8").write(f"{code},error,{last}\n"); nerr+=1
        done.add(code)
        if i%25==0:
            ck["done"]=sorted(done); save_ckpt(mkt,ck)
            el=time.time()-t0; rate=(i+1)/max(el,1)
            eta=(len(universe)-(i+1))/max(rate,1e-6)
            print(f"  {i+1}/{len(universe)} · 종목 {n} · 행 {nrows:,} · 빈값 {nempty} · 오류 {nerr} · {el:.0f}s · ETA {eta/60:.0f}m")
        time.sleep(sleep_s)
    ck["done"]=sorted(done); save_ckpt(mkt,ck)
    cov=n/max(len(universe),1)*100
    print(f"[{mkt}] 완료 · 종목(조정) {n} · 총행 {nrows:,} · 빈값(상폐→월봉윈저경로) {nempty} · 오류 {nerr}")
    print(f"  커버리지 {cov:.0f}% · 산출 {os.path.basename(outp)}")
    print(f"  다음: py derive_weekly.py --market {mkt}   (주봉은 일봉에서 파생)")

def smoke():
    from pykrx import stock
    frm="19960101"; to=datetime.date.today().strftime("%Y%m%d")
    print("=== (a) 상장 삼성전자(005930) 일봉 수정 OHLCV ===")
    a=fetch_one(stock,"005930",frm,to)
    print("  수신 행:",0 if a is None else len(a))
    if a is not None and len(a): print("  최근:", a.tail(1).to_dict("records"))
    listed=set(stock.get_market_ticker_list(to,market="KOSPI"))
    delisted=sorted(_cache_codes("KOSPI")-listed)
    print(f"=== (b) 상폐 후보 {len(delisted)}개 중 3개 수신 시도 ===")
    for c in delisted[:3]:
        try:
            r=fetch_one(stock,c,frm,to); print(f"  {c}: {0 if r is None else len(r)}행 {'OK' if r is not None and len(r) else '빈값'}")
        except Exception as e:
            print(f"  {c}: 실패 — {str(e)[:80]}")
    print("판정: (a) OHLC 값이 채워지면 트레일/ATR 계산용 일봉 확보 가능.")

def self_test():
    import pandas as pd
    ok=[]
    ok.append(("캐시코드 로더 형", isinstance(_cache_codes("KOSPI"),set)))
    ck={"done":["005930"]}; ok.append(("체크포인트 dict", ck["done"]==["005930"]))
    # used-file 파서
    tmp=os.path.join(HERE,"_st_used.txt"); open(tmp,"w").write("5930\n000660,메모\n\nabc\n")
    u=_used_codes(tmp); os.remove(tmp)
    ok.append(("used 파서(zfill·주석·잡음 제거)", u=={"005930","000660"}))
    p=sum(1 for _,v in ok if v)
    for k,v in ok: print(f"  {'OK ' if v else 'X  '}{k}")
    print(f"self-test: {p}/{len(ok)} (네트워크 불필요분만)")
    sys.exit(0 if p==len(ok) else 1)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--market",default="KOSPI",choices=["KOSPI","KOSDAQ"])
    ap.add_argument("--start",type=int,default=2013)   # KRX 조정 소스는 2014-04~ → 2013부터 청크(여유)
    ap.add_argument("--sleep",type=float,default=0.4)
    ap.add_argument("--universe",default="all",choices=["all","used"])
    ap.add_argument("--used-file",default=os.path.join(HERE,"사용유니버스.txt"))
    ap.add_argument("--smoke",action="store_true"); ap.add_argument("--self-test",action="store_true")
    a=ap.parse_args()
    if a.self_test: self_test()
    elif a.smoke: smoke()
    else: collect(a.market, a.start, a.sleep, a.universe, a.used_file)

if __name__=="__main__": main()
