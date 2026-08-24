# -*- coding: utf-8 -*-
"""삼성SDI 2025+ SUE 미산출 원인 진단 (2026-08-22)
캐시 문제는 배제됨(--refresh 후에도 동일) → DART 응답 자체를 본다.
실행: py SDI_진단.py
"""
import json, sys
sys.path.insert(0, ".")
from fetch_dart_eps import load_api_key, DART_URL, pick_ni_cumulative
import requests

CC = "00126362"   # 삼성SDI
KEY = load_api_key()

def probe(year, reprt, label):
    for fs in ("CFS", "OFS"):
        r = requests.get(DART_URL, params={
            "crtfc_key": KEY, "corp_code": CC, "bsns_year": str(year),
            "reprt_code": reprt, "fs_div": fs}, timeout=30).json()
        st, msg = r.get("status"), r.get("message")
        lst = r.get("list") or []
        print(f"[{year} {label} {fs}] status={st} msg={msg} rows={len(lst)}")
        if lst:
            # 우리 파서가 무엇을 고르는지
            val, rcept = pick_ni_cumulative(lst)
            print(f"   파서 결과: ni_cum={val} rcept={rcept}")
            # 순이익 계열 계정 실제 이름 나열 (파서가 놓친 이름 찾기)
            hits = [x for x in lst if "순이익" in str(x.get("account_nm", ""))]
            for h in hits[:8]:
                print(f"   · sj_div={h.get('sj_div')} | {h.get('account_nm')} | "
                      f"thstrm={h.get('thstrm_amount')} | id={h.get('account_id')}")
            if not hits:
                print(f"   · '순이익' 계정 없음 — 상위 5개: "
                      f"{[x.get('account_nm') for x in lst[:5]]}")
            return
    print(f"[{year} {label}] CFS·OFS 모두 데이터 없음")

# 되는 해(2024)와 안 되는 해(2025) 비교 — 차이가 곧 원인
probe(2024, "11011", "FY")
probe(2025, "11011", "FY")
probe(2025, "11012", "H1")
probe(2026, "11012", "H1")
