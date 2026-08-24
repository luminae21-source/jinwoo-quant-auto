# -*- coding: utf-8 -*-
r"""
재무구멍_확인.py — 결함 ㉱ 판별: 2008-08~11 재무가 KRX 원천에 없는 건가, 수집 사고인가.
(#76 · PC 전용 — 네트워크 필요)

    py 재무구멍_확인.py

판별 논리:
  pykrx 로 그 구간의 월말 재무 스냅샷을 지금 다시 받아본다.
  · 값이 오면       → 수집 사고였다 → 재수집으로 즉시 메꾼다 (다음 단계 안내 출력)
  · 지금도 전부 0   → KRX 원천 부재 → FnGuide 가 유일한 길
대조군으로 구멍 밖 날짜(2008-07, 2008-12)도 같이 받는다 — 대조군까지 0 이면
판별이 아니라 네트워크/API 문제다.
"""
import sys

try:
    from pykrx import stock
except ImportError:
    sys.exit("⛔ 먼저: pip install pykrx")
import pandas as pd

DATES = [
    ("20080731", "대조군(구멍 밖)"),
    ("20080829", "㉱ 구멍"),
    ("20080930", "㉱ 구멍"),
    ("20081031", "㉱ 구멍"),
    ("20081128", "㉱ 구멍"),
    ("20081230", "대조군(구멍 밖)"),
]

print("=" * 64)
print(" 결함 ㉱ 판별 — KRX 재무 스냅샷 재수령 (KOSPI)")
print("=" * 64)
print(f"{'날짜':>10} {'구분':<14} {'행수':>6} {'BPS>0':>7} {'PER>0':>7} {'DIV>0':>7}")

res = {}
for d, tag in DATES:
    try:
        df = stock.get_market_fundamental_by_ticker(d, market="KOSPI")
    except Exception as e:
        print(f"{d:>10} {tag:<14}  ⛔ 실패: {e}")
        res[d] = None
        continue
    if df is None or df.empty:
        print(f"{d:>10} {tag:<14}      0       -       -       -")
        res[d] = 0
        continue
    nz = {c: int((pd.to_numeric(df[c], errors='coerce') > 0).sum())
          for c in ("BPS", "PER", "DIV") if c in df.columns}
    print(f"{d:>10} {tag:<14} {len(df):>6} {nz.get('BPS',0):>7} {nz.get('PER',0):>7} {nz.get('DIV',0):>7}")
    res[d] = nz.get("BPS", 0)

print("-" * 64)
ctrl = [res.get("20080731"), res.get("20081230")]
hole = [res.get(d) for d in ("20080829", "20080930", "20081031", "20081128")]
if any(v is None for v in ctrl + hole):
    print("⚠️ 일부 요청 실패 — 다시 실행해보고, 반복되면 pykrx 버전 확인.")
elif all((v or 0) == 0 for v in ctrl):
    print("⚠️ 대조군까지 0 — 판별 불가. API/네트워크 문제다. 잠시 후 재실행.")
elif all((v or 0) == 0 for v in hole):
    print("판별: **KRX 원천 부재.** 2008-08~11 재무는 KRX 에 없다.")
    print("→ FnGuide 재무가 유일한 길. 수령 조건에 '2008년 커버' 를 명시적으로 확인할 것.")
else:
    got = sum(1 for v in hole if (v or 0) > 0)
    print(f"판별: **수집 사고.** 구멍 4개월 중 {got}개월이 지금은 값이 온다.")
    print("→ 종목재무_KRX_*.csv 의 2008-08~11 을 재수집으로 메꿀 수 있다.")
    print("  (메꾼 뒤: 패널 재생성 → 2008 창 백테·방어 판정 재실행 — B-1t ⑤)")
