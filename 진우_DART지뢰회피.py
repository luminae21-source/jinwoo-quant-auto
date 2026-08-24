#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우_DART지뢰회피.py — 후보 종목의 '상폐/파산 지뢰'만 실시간 배제 (★PC 전용·DART OpenAPI).

정직: 솔벤시는 '필터'로는 저가치(딥밸류 파산율 이미 0~1.4%, PBR>0이 자본잠식 배제).
      그래서 백테가 아니라 '라이브 지뢰회피'로만 영리하게 쓴다 — 지금 상폐임박 종목만 뺀다.

무엇을 보나(공시 제목·재무 스캔, 최근 1년):
  · 감사의견 거절/부적정/한정 · 계속기업 불확실성 · 관리종목/투자환기 지정
  · 상장폐지/거래정지 · 자본잠식(자본총계<자본금) · 횡령·배임 · 불성실공시
→ 하나라도 걸리면 [지뢰] 플래그. 진입 후보에서 제외(또는 비중 대폭 축소).

의존: .dart_key, dart_corp_codes.json (이미 폴더에 있음). requests.
입력: 후보코드(진우_타점발굴.csv deep=1) 또는 --codes 파일. 출력: 진우_DART지뢰_결과.csv
사용(PC): py 진우_DART지뢰회피.py            (타점발굴 딥후보 자동)
          py 진우_DART지뢰회피.py --codes _codes.txt
"""
import os, sys, csv, json, time, argparse
from pathlib import Path
BASE=Path(__file__).parent.resolve(); API="https://opendart.fss.or.kr/api"
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

LANDMINE_KW=["의견거절","부적정","한정","계속기업","관리종목","투자환기","투자주의환기",
             "상장폐지","거래정지","자본잠식","횡령","배임","불성실공시","감사범위제한","실질심사"]

def load_key():
    p=BASE/".dart_key"
    if not p.exists(): sys.exit(".dart_key 없음")
    return p.read_text(encoding="utf-8").strip()

def load_corp():
    p=BASE/"dart_corp_codes.json"
    if not p.exists(): sys.exit("dart_corp_codes.json 없음")
    d=json.load(open(p,encoding="utf-8"))
    # {stock_code: corp_code} 또는 리스트일 수 있음 → 표준화
    if isinstance(d,dict): return {str(k).zfill(6):v for k,v in d.items()}
    m={}
    for r in d:
        sc=str(r.get("stock_code","")).zfill(6); cc=r.get("corp_code")
        if sc and cc: m[sc]=cc
    return m

def load_candidates(a):
    if a.codes:
        p=a.codes if os.path.isabs(a.codes) else BASE/a.codes
        return [ln.strip().zfill(6) for ln in open(p,encoding="utf-8") if ln.strip() and not ln.startswith("#")]
    p=BASE/"진우_타점발굴.csv"; out=[]
    if p.exists():
        for r in csv.DictReader(open(p,encoding="utf-8-sig")):
            r={k.lstrip("﻿"):v for k,v in r.items()}
            if r.get("deep")=="1" or r.get("bounce")=="1": out.append(r["code"].zfill(6))
    if not out: sys.exit("후보 없음 → --codes 파일 지정")
    return out

def scan(code, corp, key, req, days=400):
    """최근 공시 제목에서 지뢰 키워드 탐지."""
    import datetime as dt
    end=dt.date.today().strftime("%Y%m%d"); bgn=(dt.date.today()-dt.timedelta(days=days)).strftime("%Y%m%d")
    hits=set()
    try:
        r=req.get(f"{API}/list.json",params=dict(crtfc_key=key,corp_code=corp,bgn_de=bgn,end_de=end,page_count=100),timeout=15)
        j=r.json()
        for it in j.get("list",[]):
            title=it.get("report_nm","")
            for kw in LANDMINE_KW:
                if kw in title: hits.add(kw)
    except Exception as e:
        return None  # 조회 실패
    return hits

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--codes",default=None); ap.add_argument("--sleep",type=float,default=0.15)
    a=ap.parse_args()
    try: import requests as req
    except ImportError: os.system(f"{sys.executable} -m pip install -q requests"); import requests as req
    key=load_key(); corp=load_corp(); codes=load_candidates(a)
    print(f"후보 {len(codes)}종 지뢰 스캔 (DART 최근 공시)")
    rows=[]
    for i,c in enumerate(codes):
        cc=corp.get(c)
        if not cc: rows.append((c,"corp_code없음","")); continue
        hits=scan(c,cc,key,req)
        if hits is None: flag="조회실패"
        elif hits: flag="⚠지뢰"
        else: flag="정상"
        rows.append((c,flag,"|".join(sorted(hits)) if hits else ""))
        if a.sleep: time.sleep(a.sleep)
        if (i+1)%20==0: print(f"  ...{i+1}/{len(codes)}")
    with open(BASE/"진우_DART지뢰_결과.csv","w",encoding="utf-8-sig",newline="") as f:
        w=csv.writer(f); w.writerow(["code","판정","지뢰키워드"]); w.writerows(rows)
    n=sum(1 for r in rows if r[1]=="⚠지뢰")
    print(f"\n저장: 진우_DART지뢰_결과.csv | ⚠지뢰 {n}종 (진입 제외 권장)")
    for c,fl,kw in rows:
        if fl=="⚠지뢰": print(f"  ⚠ {c}: {kw}")

if __name__=="__main__":
    main()
