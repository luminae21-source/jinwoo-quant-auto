#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
옵션API_진단.py — opt_bydd_trd(옵션 일별매매정보·주식옵션外)가 빈 배열인 원인 진단.
구독은 '이미 이용 중' 확인됨 → 원인은 키/경로/매핑. PC에서 실행(네트워크 필요).
키는 화면에 일부만(앞2·뒤2) 표시. 절대 채팅에 키 전체를 붙이지 말 것.
사용: python 옵션API_진단.py
"""
import sys, json, re, urllib.request
from pathlib import Path
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

BASE_DIR = Path(__file__).parent.resolve()
API = "http://data-dbg.krx.co.kr/svc/apis"

def load_key():
    f = BASE_DIR / "krx_authkey.txt"
    if not f.exists():
        import os; return os.environ.get("KRX_AUTH_KEY")
    k = f.read_text(encoding="utf-8").strip().splitlines()[0].strip()
    return re.sub(r'(?i)^\s*(auth[_-]?key|key)\s*[:=]\s*', '', k)

def call(path, basDd, key):
    url = f"{API}/{path}?basDd={basDd}"
    req = urllib.request.Request(url, headers={"AUTH_KEY": key})
    try:
        r = urllib.request.urlopen(req, timeout=20)
        body = r.read().decode("utf-8", "replace")
        try: j = json.loads(body)
        except Exception: j = None
        rows = j.get("OutBlock_1", []) if isinstance(j, dict) else None
        return r.status, (len(rows) if rows is not None else "?"), body[:300]
    except urllib.error.HTTPError as e:
        return f"HTTP{e.code}", "-", str(e)[:200]
    except Exception as e:
        return "ERR", "-", f"{type(e).__name__}: {str(e)[:200]}"

key = load_key()
if not key:
    print("❌ 키 없음 — krx_authkey.txt(한 줄) 또는 KRX_AUTH_KEY 설정 후 재실행"); sys.exit()
print(f"키: 길이 {len(key)} · 앞2={key[:2]} 뒤2={key[-2:]}  ← 마이페이지>API인증키 발급내역의 '옵션 승인 키'와 앞2·뒤2 일치하는지 대조")
print("="*70)

DATES = ["20260622", "20260619", "20260613", "20260612"]
# 후보 경로(혹시 경로 불일치 대비). 정답이 하나라도 rows>0면 그게 맞는 경로.
OPT_PATHS = ["drv/opt_bydd_trd", "drv/eqsop_bydd_trd", "drv/eqkop_bydd_trd"]

print("[대조군] 선물 drv/fut_bydd_trd (정상이어야 함)")
for d in DATES[:2]:
    s, n, raw = call("drv/fut_bydd_trd", d, key)
    print(f"  {d}: status={s} rows={n}  raw={raw[:90]}")

print("\n[진단] 옵션 후보 경로 × 날짜")
for p in OPT_PATHS:
    for d in DATES:
        s, n, raw = call(p, d, key)
        flag = "  ✅ 데이터!" if isinstance(n, int) and n > 0 else ""
        print(f"  {p} {d}: status={s} rows={n}{flag}  raw={raw[:90]}")

print("="*70)
print("해석:")
print(" · 옵션 rows>0 나오는 경로가 있으면 → 그 경로로 krx_openapi.py 수정하면 끝.")
print(" · 모든 옵션 경로 rows=0(빈배열)인데 선물은 정상 → 이 '키'가 옵션 승인 키가 아님.")
print("   → 마이페이지>이용현황에서 '옵션 일별매매정보(주식옵션外)' 상태=승인완료인지,")
print("     그리고 그 서비스가 '이 키'에 연결됐는지 확인(키 여러 개면 옵션 승인된 키로 교체).")
print(" · status=HTTP4xx면 → 키 자체 인증 문제(앞2/뒤2 재대조·재발급).")
