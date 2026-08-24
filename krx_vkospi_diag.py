#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
krx_vkospi_diag.py — VKOSPI 진단. 파생상품지수에서 '변동성' 들어간 모든 행을 나열,
어떤 지수가 83.57로 잡혔는지 + 진짜 VKOSPI 행이 따로 있는지 확인. [PC 실행]
원칙: 공식 실데이터만. 가짜 금지. krx_openapi.py 무수정(읽기만).
"""
import sys, json
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import krx_openapi as K

key = K.auth_key()
if not key:
    print("❌ 인증키 없음 — krx_authkey.txt 확인"); sys.exit()

print("=" * 60)
print("VKOSPI 진단 — 파생상품지수(idx/drvprod_dd_trd)")
print("=" * 60)

rows = K._fetch("idx/drvprod_dd_trd", key)
if not rows:
    print("❌ 데이터부족 (drvprod_dd_trd 빈배열)")
    sys.exit()

print("\n총 %d개 지수 행. 컬럼: %s\n" % (len(rows), list(rows[0].keys())))

print("--- '변동성' 포함 지수 전부 (← 여기서 VKOSPI 골라야) ---")
hits = []
for r in rows:
    nm = str(r.get("IDX_NM", ""))
    if "변동성" in nm or "VKOSPI" in nm.upper():
        cls = r.get("CLSPRC_IDX"); fl = r.get("FLUC_RT")
        hits.append((nm, cls, fl))
        print("  • IDX_NM='%s' | 종가=%s | 등락%%=%s" % (nm, cls, fl))
if not hits:
    print("  (없음 — VKOSPI가 이 서비스에 없을 수 있음)")

print("\n--- 현재 코드가 잡는 값(첫 '변동성' 행) ---")
cur = K.get_vkospi(key)
print("  get_vkospi() =", cur)

print("\n--- 전체 지수명 목록(참고) ---")
for r in rows:
    print("  ", r.get("IDX_NM"), "=", r.get("CLSPRC_IDX"))

print("\n[끝] 위 '변동성 포함' 목록에서 진짜 VKOSPI(코스피200 변동성지수, 보통 15~25)의")
print("    정확한 IDX_NM을 알려줘 → get_vkospi를 그 이름으로 정밀 매칭하게 고칠게.")
