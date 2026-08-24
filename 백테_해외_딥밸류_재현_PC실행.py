#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""백테_해외_딥밸류_재현_PC실행.py — #1 일본·홍콩 딥밸류바닥 재현 (진우 PC 전용)

⚠️ 클라우드(샌드박스)는 야후/stooq 403차단 → 이 스크립트는 **진우 PC에서** 실행.
목적: AQR로 '원리'는 확인됨. 우리 실제 전략(저PBR ∩ 이격<0.85 ∩ 1M수익>0, 롱온리, 분산)을
      일본(.T)·홍콩(.HK) 실종목에 적용해도 전이되나 + 표본 폭증 확인.

전략규칙(국내와 동일하게 이식):
  · 유효: 종가>=최소가 & PBR>0 & MA10 존재
  · 딥밸류: PBR 하위 20% (시장별 재랭크)
  · 반등군: 딥밸류 ∩ (종가/MA10)<0.85 ∩ 1M수익>0
  · 선행수익 6/12M, 상폐 -100%(또는 마지막유효가) 반영
  · IN/OOS(예: ~2019 / 2020~) 양분할 + 부트스트랩

생존편향(핵심 관문):
  · yfinance/FDR StockListing은 **현재상장 위주** → 상폐종목 누락 = 수익 상향편의.
  · 진짜 검증엔 상폐포함 리스트 필요. 아래 3단계로 최대한 통제하고, 못 하면 '예비(생존편향)'로 정직 표기.
    (A) FDR StockListing('TSE')/('HKEX') 현재상장 → 예비.
    (B) 가능하면 과거 시점 구성종목/상폐목록 별도 확보(파일 있으면 --delisted-csv로 주입).
    (C) 상폐 반영 못 하면 결과에 [생존편향·상향편의] 라벨 강제.

PBR 소스:
  · yfinance: ticker.info['priceToBook'](현재값만 — 과거 PBR 아님, 시계열 백테엔 부적합).
  · 권장: FDR로 주가, 재무는 별도(일본=EDINET/홍콩=HKEX) — 과거 BPS 필요.
  · 최소 재현: 시장별 스냅샷 PBR로 '현재 딥밸류'만 선별 → forward만 측정(약식). 라벨 [스냅샷PBR].

사용(진우 PC):
  python 백테_해외_딥밸류_재현_PC실행.py --market TSE --n 800 --start 2010 --self-test
  python 백테_해외_딥밸류_재현_PC실행.py --market HKEX --n 800 --start 2010
의존: pip install FinanceDataReader yfinance pandas numpy
"""
import argparse, sys, time
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def log(*a): print(*a, flush=True)

SEED={   # StockListing 실패 시 폴백(대표 유동종목·야후 서픽스). 소표본이지만 최소 실행 보장.
 "TSE":["7203.T","6758.T","9984.T","8306.T","6861.T","9432.T","7974.T","6501.T","8035.T",
        "4063.T","6098.T","9433.T","8058.T","7267.T","6902.T","4519.T","6367.T","8001.T",
        "9983.T","4568.T","6273.T","7741.T","8031.T","6503.T","4661.T"],
 "HKEX":["0700.HK","0939.HK","1299.HK","0941.HK","3690.HK","0005.HK","1810.HK","2318.HK",
         "0388.HK","0883.HK","1024.HK","2020.HK","0175.HK","1211.HK","2382.HK","0027.HK",
         "0016.HK","1113.HK","2331.HK","0669.HK","1928.HK","0288.HK","0291.HK","2688.HK"],
}
def _yahoo_suffix(code, market):
    s=str(code).strip().upper()
    if "." in s: return s
    if market=="TSE":  return s.zfill(4)+".T"
    if market=="HKEX": return s.zfill(4)+".HK"
    return s
def get_listing(market, n):
    try:
        import FinanceDataReader as fdr
        df=fdr.StockListing(market)   # 'TSE'(도쿄) / 'HKEX'(홍콩)
        col=next((c for c in df.columns if c.lower() in ("code","symbol")), df.columns[0])
        mc =next((c for c in df.columns if c.lower() in ("marcap","marketcap")), None)
        if mc: df=df.sort_values(mc, ascending=False)
        codes=[_yahoo_suffix(c,market) for c in df[col].astype(str).head(n).tolist()]
        log(f"[{market}] StockListing {len(df)}종 → 상위 {len(codes)} 사용 (⚠️ 현재상장=생존편향)")
        return codes
    except Exception as e:
        log(f"[{market}] StockListing 실패({repr(e)[:80]}) → 시드리스트 폴백(소표본).")
        return SEED.get(market, [])

def fetch_prices(codes, market, start):
    """야후(.T/.HK)로 종가 수집 — yfinance 우선(해외 티커에 안정), 실패시 FDR."""
    import yfinance as yf
    px={}
    for i,c in enumerate(codes):
        try:
            df=yf.download(c, start=f"{start}-01-01", progress=False, auto_adjust=True, timeout=20)
            if df is not None and len(df)>200:
                px[c]=df["Close"] if "Close" in df else df.iloc[:,0]
        except Exception: pass
        if (i+1)%100==0: log(f"  ...{i+1}/{len(codes)} 수집")
    if not px:
        log("⚠️ 가격 0건 — 네트워크/티커/야후차단 확인. (PC에서 인터넷 되는지, 방화벽 점검)");
        return pd.DataFrame()
    P=pd.concat(px,axis=1); P.columns=list(px.keys())
    M=P.resample("ME").last(); M.index=M.index.to_period("M")
    log(f"월말종가 패널: {M.shape[1]}종 × {M.shape[0]}월")
    return M

def smoke(market):
    """데이터 경로 점검 — 1종목만 받아본다(전체 실행 전 확인용)."""
    import yfinance as yf
    t=("7203.T" if market=="TSE" else "0700.HK")
    log(f"[스모크] {t} 최근 1개월 시세 요청...")
    df=yf.download(t, period="1mo", progress=False, timeout=20)
    if df is not None and len(df)>0:
        log(f"[스모크 OK] {t} {len(df)}행 수신 · 최근종가 {float(df['Close'].iloc[-1]):,.0f}")
        try:
            pb=yf.Ticker(t).info.get("priceToBook"); log(f"[스모크] PBR(priceToBook)={pb}")
        except Exception as e: log(f"[스모크] PBR 조회 경고: {repr(e)[:60]}")
        log("→ 데이터 경로 정상. 이제 --market 로 전체 실행 가능.")
        return 0
    log("[스모크 실패] 시세 0행 — 야후 접속 차단/티커오류. 전체 실행해도 안 됨."); return 1

def fetch_pbr_snapshot(codes):
    """yfinance priceToBook 스냅샷(현재값). 시계열 아님 → [스냅샷PBR] 약식용."""
    import yfinance as yf
    pb={}
    for i,c in enumerate(codes):
        try:
            v=yf.Ticker(c).info.get("priceToBook")
            if v and v>0: pb[c]=v
        except Exception: pass
        time.sleep(0.02)
        if (i+1)%100==0: log(f"  ...PBR {i+1}/{len(codes)}")
    return pd.Series(pb)

def fwd_delist_aware(px,h):
    V=px.values;T,N=V.shape;out=np.full((T,N),np.nan)
    for ti in range(T):
        base=V[ti];hi=min(ti+h,T-1)
        if hi<=ti: continue
        win=V[ti+1:hi+1]
        for j in range(N):
            b=base[j]
            if not(b==b) or b<=0: continue
            col=win[:,j];val=col[~np.isnan(col)]
            out[ti,j]=val[-1]/b-1 if val.size>0 else -1.0
    return pd.DataFrame(out,index=px.index,columns=px.columns)

def boot(a,b,n=4000,seed=7):
    rng=np.random.default_rng(seed);a=np.asarray(a);b=np.asarray(b)
    d=a.mean()-b.mean();ds=[rng.choice(a,len(a)).mean()-rng.choice(b,len(b)).mean() for _ in range(n)]
    return d,float((np.array(ds)<=0).mean())

def analyze(M, pbr_snapshot):
    ma10=M.rolling(10).mean();disp=M/ma10;ret1=M.pct_change()
    # 스냅샷 PBR을 전월 브로드캐스트(약식·라벨 [스냅샷PBR])
    pbr=pd.DataFrame(np.repeat(pbr_snapshot.reindex(M.columns).values[None,:],len(M),axis=0),index=M.index,columns=M.columns)
    valid=M.notna()&ma10.notna()&(pbr>0)
    pr=pbr.where(valid).rank(axis=1,pct=True)
    deep=valid&(pr<=0.20);reb=deep&(disp<0.85)&(ret1>0)
    yr=pd.Series([p.year for p in M.index],index=M.index)
    for hz,h in (("12M",12),("6M",6)):
        fwd=fwd_delist_aware(M,h)
        log(f"\n── {hz} 선행 [스냅샷PBR·{'생존편향' }] ──")
        for seg,cond in (("ALL",yr>=0),("IN(~2019)",yr<=2019),("OOS(2020~)",yr>=2020)):
            sm=pd.DataFrame(np.repeat(cond.values[:,None],M.shape[1],axis=1),index=M.index,columns=M.columns)
            for nm,mk in (("시장",valid&sm),("딥밸류",deep&sm),("반등군",reb&sm)):
                v=fwd.where(mk).values.ravel();v=v[~np.isnan(v)]
                if len(v)<20: continue
                log(f"  [{seg:<10}] {nm:<6} n={len(v):>5} 평{np.mean(v)*100:>+5.1f}% 중{np.median(v)*100:>+5.1f}% 승{(v>0).mean()*100:>3.0f}% 대박{(v>=1).mean()*100:>3.0f}%")

def self_test():
    px=pd.DataFrame({"A":[100,110,120,np.nan]},index=pd.period_range("2020-01",periods=4,freq="M"))
    f=fwd_delist_aware(px,3);assert abs(f.iloc[0,0]-0.2)<1e-9
    d,p=boot([0.2,0.3,0.25],[0.1,0.05,0.0]);assert d>0
    log("[OK] self-test 통과");return 0

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--market",default="TSE",help="TSE(일본)/HKEX(홍콩)")
    ap.add_argument("--n",type=int,default=800);ap.add_argument("--start",default="2010")
    ap.add_argument("--self-test",action="store_true")
    ap.add_argument("--smoke",action="store_true",help="1종목만 받아 데이터경로 점검")
    a=ap.parse_args()
    if a.self_test: return self_test()
    if a.smoke: return smoke(a.market)
    codes=get_listing(a.market,a.n)
    M=fetch_prices(codes,a.market,a.start)
    log("PBR 스냅샷 수집(yfinance priceToBook)...")
    pbr=fetch_pbr_snapshot(list(M.columns))
    log(f"PBR 확보 {len(pbr)}종")
    analyze(M,pbr)
    log("\n판정기준: 국내처럼 반등군>딥밸류>시장 & IN/OOS 부호유지면 원리→전략 전이 지지.")
    log("⚠️ 이 예비판은 [스냅샷PBR·생존편향]. 본격판=과거시점 PBR시계열+상폐포함 리스트 확보 후.")
    return 0

if __name__=="__main__": sys.exit(main() or 0)
