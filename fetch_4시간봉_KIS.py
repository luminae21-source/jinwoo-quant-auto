#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""fetch_4시간봉_KIS.py — 한국투자증권(KIS) REST로 분봉 수집→4시간봉 집계(전방 축적 스켈레톤).

⚠ 진우 PC 전용(이 환경은 증권사 접속 차단). KIS Developers appkey/secret 필요.
설계 근거: 사냥터_기획/진우_4시간봉_수집설계.md
  - KR 정규장 09:00–15:30 → 4H = 하루 2봉: 봉1(09:00–13:00), 봉2(13:00–15:30 마감봉)
  - KIS 분봉은 히스토리 얕음 → '매일 실행해 전방 누적'(백테스트용 과거분봉은 별도 유료소스)
산출: 4시간봉_{종목}.csv 누적(append), 또는 통합 4시간봉_all.csv
사용(PC): 환경변수 KIS_APPKEY, KIS_APPSECRET 설정 후  py fetch_4시간봉_KIS.py 005930 000660 ...
          (인자 없으면 진우사냥터_후보.csv의 code들)
"""
import os,sys,csv,time,datetime as dt
import requests, pandas as pd

BASE=os.path.dirname(os.path.abspath(__file__))
HOST="https://openapi.koreainvestment.com:9443"
TOKfile=os.path.join(BASE,".kis_token")

def _load_keys():
    """키 우선순위: 환경변수 → .kis_key 파일(첫 두 유효줄=APPKEY, APPSECRET)."""
    k=os.environ.get("KIS_APPKEY",""); s=os.environ.get("KIS_APPSECRET","")
    p=os.path.join(BASE,".kis_key")
    if (not k or not s) and os.path.exists(p):
        vals=[ln.strip() for ln in open(p,encoding="utf-8") if ln.strip() and not ln.strip().startswith("#")]
        if len(vals)>=2: k,s=vals[0],vals[1]
    return k,s
APPKEY,APPSECRET=_load_keys()

def get_token():
    # 토큰 캐시(24h) 재사용
    if os.path.exists(TOKfile):
        t=open(TOKfile).read().split("\t")
        if len(t)==2 and float(t[1])>time.time()+60: return t[0]
    if not (APPKEY and APPSECRET): sys.exit("환경변수 KIS_APPKEY/KIS_APPSECRET 설정 필요")
    r=requests.post(f"{HOST}/oauth2/tokenP",json={"grant_type":"client_credentials","appkey":APPKEY,"appsecret":APPSECRET},timeout=10)
    r.raise_for_status(); j=r.json(); tok=j["access_token"]
    open(TOKfile,"w").write(f"{tok}\t{time.time()+int(j.get('expires_in',86400))}")
    return tok

def fetch_minute(code,tok,base_hhmmss):
    """기준시각(base_hhmmss)까지의 분봉 최대 30건. 하루 전체는 base_time을 옮겨 여러번 호출."""
    url=f"{HOST}/uapi/domestic-stock/v1/quotations/inquire-time-itemchartprice"
    h={"authorization":f"Bearer {tok}","appkey":APPKEY,"appsecret":APPSECRET,
       "tr_id":"FHKST03010200","custtype":"P"}
    p={"FID_ETC_CLS_CODE":"","FID_COND_MRKT_DIV_CODE":"J","FID_INPUT_ISCD":code,
       "FID_INPUT_HOUR_1":base_hhmmss,"FID_PW_DATA_INCU_YN":"Y"}
    r=requests.get(url,headers=h,params=p,timeout=10)
    if r.status_code!=200: return []
    out=r.json().get("output2",[]) or []
    rows=[]
    for o in out:
        t=o.get("stck_cntg_hour","");c=o.get("stck_prpr","")
        if t and c: rows.append((t,float(c),int(o.get("cntg_vol",0) or 0)))
    return rows

def collect_day_minute(code,tok):
    """하루치 1분봉을 base_time 페이징으로 모은다(장중 여러 슬롯)."""
    seen={}
    for base in ("100000","110000","120000","130000","140000","153000"):  # 슬롯별 30건씩
        for t,c,v in fetch_minute(code,tok,base): seen[t]=(c,v)
        time.sleep(0.12)  # rate limit 여유
    return sorted(seen.items())  # [(HHMMSS,(close,vol))]

def to_4h(minrows,day):
    """분봉→4H 2봉(오전 09:00-13:00, 오후 13:00-15:30)."""
    b1=[(c,v) for t,(c,v) in minrows if "090000"<=t<"130000"]
    b2=[(c,v) for t,(c,v) in minrows if "130000"<=t<="153000"]
    res=[]
    for lab,b,end in (("AM",b1,"1300"),("PM",b2,"1530")):
        if b:
            closes=[c for c,_ in b]
            res.append((day,lab,closes[0],max(closes),min(closes),closes[-1],sum(v for _,v in b)))
    return res  # (date,slot,open,high,low,close,vol)

def main():
    codes=[a.zfill(6) for a in sys.argv[1:]]
    if not codes:
        p=os.path.join(BASE,"진우사냥터_후보.csv")
        if os.path.exists(p):
            for r in csv.DictReader(open(p,encoding="utf-8-sig")):
                r={k.lstrip("﻿"):v for k,v in r.items()}
                if r.get("code"): codes.append(r["code"].zfill(6))
    if not codes: sys.exit("종목 인자 또는 진우사냥터_후보.csv 필요")
    tok=get_token(); today=dt.date.today().strftime("%Y-%m-%d")
    outp=os.path.join(BASE,"4시간봉_all.csv"); new= not os.path.exists(outp)
    # 중복방지: 이미 저장된 (date,code,slot) 키 로드
    seen=set()
    if not new:
        try:
            for r in csv.DictReader(open(outp,encoding="utf-8-sig")):
                r={k.lstrip("﻿"):v for k,v in r.items()}
                seen.add((r.get("date"),r.get("code"),r.get("slot")))
        except Exception: pass
    # append는 BOM 재삽입 방지 위해 utf-8(무BOM), 신규 생성시만 utf-8-sig로 헤더
    f=open(outp,"a",newline="",encoding=("utf-8-sig" if new else "utf-8")); w=csv.writer(f)
    if new: w.writerow(["date","code","slot","open","high","low","close","volume"])
    for i,c in enumerate(codes):
        try:
            rows=to_4h(collect_day_minute(c,tok),today)
            wrote=0
            for (d,slot,o,hi,lo,cl,vol) in rows:
                if (d,c,slot) in seen: continue   # 같은 날 재실행 시 중복 skip
                w.writerow([d,c,slot,o,hi,lo,cl,vol]); seen.add((d,c,slot)); wrote+=1
            print(f"[{i+1}/{len(codes)}] {c} {wrote}봉" + (" (중복skip)" if wrote==0 and rows else ""))
        except Exception as e:
            print(f"[{i+1}/{len(codes)}] {c} 실패 {e}")
        time.sleep(0.2)
    f.close()
    print(f"완료 → 4시간봉_all.csv (매일 실행해 전방 누적). 스캔: 진우_섹터스캔.py 입력을 이 CSV로 교체.")

if __name__=="__main__": main()
