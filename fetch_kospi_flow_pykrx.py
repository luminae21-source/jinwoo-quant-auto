#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_kospi_flow_pykrx.py — KOSPI 투자자별(외국인·기관) 순매수 거래대금 월합계 패널 (PC 실행).
Maury "수급=확인신호" KOSPI 검증용. fetch_v42_kosdaq_flow_pykrx.py의 KOSPI 적응판.
[PC 실행] 샌드박스 네트워크 차단 → 진우 PC. (pip install pykrx pandas)
코드 소스: 기본 = liquidity_sector.csv 시총 top-N(=백테스트 유니버스), 또는 --codes 파일.
출력: kospi_flow_monthly.csv (code, date[월말], foreign_net, inst_net) ※ 순매수 거래대금(원)
사용(PC):
  pip install pykrx pandas
  python fetch_kospi_flow_pykrx.py --top 200 --start 2019-01-02
  → 이후: python maury_kospi_test.py
"""
import argparse, csv, datetime as dt, sys, time

def load_codes(a):
    if a.codes:
        return [ln.strip().zfill(6) for ln in open(a.codes,encoding="utf-8") if ln.strip() and not ln.startswith("#")]
    # liquidity_sector.csv 시총 top-N
    try:
        rows=list(csv.DictReader(open("liquidity_sector.csv",encoding="utf-8-sig")))
        rows.sort(key=lambda r:-float(r.get("mcap") or 0))
        return [r["code"].zfill(6) for r in rows[:a.top]]
    except Exception as e:
        sys.exit("liquidity_sector.csv 없음/오류: %r — --codes 파일을 주세요" % e)

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--codes",default=None); ap.add_argument("--top",type=int,default=200)
    ap.add_argument("--start",default="2019-01-02"); ap.add_argument("--end",default=None)
    ap.add_argument("--sleep",type=float,default=0.0); ap.add_argument("--out",default="kospi_flow_monthly.csv")
    a=ap.parse_args()
    try:
        from pykrx import stock
    except ImportError:
        sys.exit("pykrx 미설치 → pip install pykrx")
    start=a.start.replace("-",""); end=(a.end or dt.date.today().isoformat()).replace("-","")
    codes=load_codes(a)
    print("KOSPI 수급 수집 %d종목, %s~%s" % (len(codes),a.start,a.end or "today"))
    FOR_KEYS=["외국인합계","외국인"]; INS_KEYS=["기관합계","기관"]
    def pick(df,keys):
        for k in keys:
            if k in df.columns: return df[k]
        return None
    rows=[]; ok=0
    for i,c in enumerate(codes):
        try:
            df=stock.get_market_trading_value_by_date(start,end,c)
        except Exception:
            continue
        if df is None or len(df)==0: continue
        fser=pick(df,FOR_KEYS); iser=pick(df,INS_KEYS)
        if fser is None or iser is None: continue
        agg={}
        for idx in df.index:
            d=idx.strftime("%Y-%m-%d") if hasattr(idx,"strftime") else str(idx)[:10]; ym=d[:7]
            try: fv=float(fser.loc[idx]); iv=float(iser.loc[idx])
            except Exception: continue
            rec=agg.setdefault(ym,[d,0.0,0.0]); rec[1]+=fv; rec[2]+=iv
            if d>rec[0]: rec[0]=d
        for ym in sorted(agg):
            ld,fs,isum=agg[ym]; rows.append((c,ld,fs,isum))
        ok+=1
        if a.sleep: time.sleep(a.sleep)
        if (i+1)%50==0: print("  ...%d/%d (성공 %d, 월행 %d)"%(i+1,len(codes),ok,len(rows)))
    with open(a.out,"w",encoding="utf-8-sig",newline="") as fh:
        w=csv.writer(fh); w.writerow(["code","date","foreign_net","inst_net"]); w.writerows(rows)
    print("\n성공 %d종목 | 월행 %d | 저장 %s\n다음: python maury_kospi_test.py"%(ok,len(rows),a.out))

if __name__=="__main__":
    main()
