#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
옵션PCR_확인2.py — 본 스크립트(krx_openapi.get_putcall_ratio, requests 기반)가
왜 None을 내는지 격리 진단. 키 노출 안 함. PC 실행.
"""
import sys, time, importlib.util as il
from pathlib import Path
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
BASE = Path(__file__).parent.resolve()
sp = il.spec_from_file_location("krx", BASE / "krx_openapi.py")
K = il.module_from_spec(sp); sp.loader.exec_module(K)
key = K.auth_key()
print("키 로드:", "OK" if key else "없음")

# 1) 프로덕션 함수 그대로(브리핑이 쓰는 경로, requests, timeout=15)
for bd in ["20260630", None]:
    t = time.time()
    r = K.get_putcall_ratio(key, bd)
    print(f"\nget_putcall_ratio(bd={bd}): {('dict' if isinstance(r,dict) else r)}  ({time.time()-t:.1f}s)")
    if isinstance(r, dict):
        print(f"   PCR 거래량 {r['vol']:.3f} · 거래대금 {r['val']:.3f}")

# 2) 개별 call()로 날짜별 상태/소요시간 확인 (requests, timeout=15)
print("\n[개별 call() 진단 — requests, 현재 timeout]")
for d in ["20260630", "20260701", "20260629", "20260626"]:
    t = time.time()
    st, j, raw = K.call("drv/opt_bydd_trd", key, d)
    rows = K.rows_of(j) if j else None
    print(f"  {d}: status={st} rows={len(rows) if rows else 0}  ({time.time()-t:.1f}s)  raw={str(raw)[:60]}")
