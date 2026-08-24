#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
옵션PCR_확인.py — opt_bydd_trd로 PCR(풋콜비율)이 실제 계산되는지 확인 + 실값 출력.
키는 노출 안 함. PC 실행(네트워크 필요). 기존 산출물 무수정.
사용: python 옵션PCR_확인.py
"""
import sys, json, re, urllib.request
from datetime import date, timedelta
from pathlib import Path
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

BASE = Path(__file__).parent.resolve()
API = "http://data-dbg.krx.co.kr/svc/apis"

def load_key():
    f = BASE / "krx_authkey.txt"
    if f.exists():
        k = f.read_text(encoding="utf-8").strip().splitlines()[0].strip()
        return re.sub(r'(?i)^\s*(auth[_-]?key|key)\s*[:=]\s*', '', k)
    import os; return os.environ.get("KRX_AUTH_KEY")

def fetch(path, basDd, key):
    url = f"{API}/{path}?basDd={basDd}"
    req = urllib.request.Request(url, headers={"AUTH_KEY": key})
    try:
        j = json.loads(urllib.request.urlopen(req, timeout=20).read().decode("utf-8","replace"))
        return j.get("OutBlock_1", []) if isinstance(j, dict) else []
    except Exception:
        return []

def num(x):
    try: return float(str(x).replace(",", ""))
    except Exception: return 0.0

def recent_bdays(n=8):
    out=[]; d=date.today()
    while len(out)<n:
        if d.weekday()<5: out.append(d.strftime("%Y%m%d"))
        d-=timedelta(days=1)
    return out

key = load_key()
if not key:
    print("❌ 키 없음"); sys.exit()

# 데이터 있는 최근 영업일 찾기
rows=[]; used=None
for d in recent_bdays(8):
    rows = fetch("drv/opt_bydd_trd", d, key)
    if rows:
        used=d; break
if not rows:
    print("❌ 최근 8영업일 모두 빈배열 (발행 전/장애)"); sys.exit()

print(f"기준일(데이터 있는 최근일): {used}  · 총 {len(rows)}행")

def pcr(filter_fn, label):
    c=cv=p=pv=0.0
    for r in rows:
        if not filter_fn(r): continue
        side=str(r.get("RGHT_TP_NM","")).upper()
        vol=num(r.get("ACC_TRDVOL")); val=num(r.get("ACC_TRDVAL"))
        if side.startswith("C"): c+=vol; cv+=val
        elif side.startswith("P"): p+=vol; pv+=val
    print(f"\n[{label}]")
    print(f"  콜 거래량 {c:,.0f} · 풋 거래량 {p:,.0f}  → PCR(거래량) = {(p/c):.3f}" if c else "  콜 거래량 0")
    print(f"  콜 거래대금 {cv:,.0f} · 풋 거래대금 {pv:,.0f}  → PCR(거래대금) = {(pv/cv):.3f}" if cv else "  콜 거래대금 0")

# PROD_NM 종류 확인
prods=sorted({str(r.get("PROD_NM","")) for r in rows})
print("상품종류:", prods)

pcr(lambda r: True, "전체 지수옵션(주식옵션外)")
pcr(lambda r: str(r.get("PROD_NM","")).replace(" ","")=="코스피200옵션", "코스피200 옵션(정규)만")
