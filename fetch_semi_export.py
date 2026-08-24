#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_semi_export.py — [PC 실행] 한국은행 ECOS에서 **반도체 수출** 월간 시계열 확보.
목적: 후보 F Phase2 — 비가격 실물 선행신호(반도체 수출 YoY)가 코스피 추세(A)에 증분 주나.
키: **ecos_key.txt**(같은 폴더, 키 한 줄). 코드에 키를 넣지 말 것.

사용 순서(3단계):
  1) py fetch_semi_export.py --discover 수출        # '수출' 포함 통계표 목록 → 후보 코드 확인
  2) py fetch_semi_export.py --items <STAT_CODE>    # 그 표의 세부항목(반도체 찾기)
  3) py fetch_semi_export.py --fetch <STAT_CODE> <ITEM_CODE>   # 월간 시계열 저장
산출: semi_export_monthly.csv (date, value, yoy)
무수정: production·L1 불변.
"""
import os, sys, json, argparse
from urllib.request import urlopen
BASE = os.path.dirname(os.path.abspath(__file__))
API = "https://ecos.bok.or.kr/api"

def key():
    p = os.path.join(BASE, "ecos_key.txt")
    if not os.path.exists(p): sys.exit("ecos_key.txt 없음 → 폴더에 키 한 줄 저장하세요.")
    k = open(p, encoding="utf-8").read().strip()
    if not k: sys.exit("ecos_key.txt 비어있음")
    return k

def get(url):
    with urlopen(url, timeout=30) as r:
        d = json.loads(r.read().decode("utf-8"))
    if "RESULT" in d:  # 에러 응답
        print("[ECOS 오류]", d["RESULT"]); sys.exit(1)
    return d

def discover(kw):
    d = get(f"{API}/StatisticTableList/{key()}/json/kr/1/1000/")
    rows = d.get("StatisticTableList", {}).get("row", [])
    hits = [r for r in rows if kw in (r.get("STAT_NAME") or "")]
    print(f"'{kw}' 포함 통계표 {len(hits)}개:")
    for r in hits[:80]:
        code = str(r.get("STAT_CODE") or "-"); cyc = str(r.get("CYCLE") or "-"); nm = str(r.get("STAT_NAME") or "-")
        print(f"  {code:<12} {cyc:<3} {nm}")
    print("\n→ 이 목록을 그대로 Claude에 붙여주세요. (반도체 수출 표 골라드림)")

def items(stat, kw="반도체"):
    d = get(f"{API}/StatisticItemList/{key()}/json/kr/1/1000/{stat}")
    rows = d.get("StatisticItemList", {}).get("row", [])
    print(f"[{stat}] 세부항목 {len(rows)}개 ('{kw}' 매칭):")
    semi = [r for r in rows if kw in (r.get("ITEM_NAME") or "")]
    for r in (semi or rows[:80]):
        ic = str(r.get("ITEM_CODE") or "-"); cyc = str(r.get("CYCLE") or "-")
        st = str(r.get("START_TIME") or "-"); en = str(r.get("END_TIME") or "-"); nm = str(r.get("ITEM_NAME") or "-")
        print(f"  {ic:<14} {cyc:<3} {st}~{en}  {nm}")
    print("\n→ 이 목록을 Claude에 붙여주세요.")

def fetch(stat, item, outname="semi_export_monthly.csv", start="200001", end="209912", cycle="M"):
    url = f"{API}/StatisticSearch/{key()}/json/kr/1/10000/{stat}/{cycle}/{start}/{end}/{item}"
    d = get(url)
    rows = d.get("StatisticSearch", {}).get("row", [])
    if not rows: sys.exit("데이터 없음 — 코드/주기 확인")
    import csv
    recs = []
    for r in rows:
        t = r.get("TIME"); v = r.get("DATA_VALUE")
        if not t or v in (None, ""): continue
        recs.append((f"{t[:4]}-{t[4:6]}-01", float(v)))
    recs.sort()
    out = os.path.join(BASE, outname)
    with open(out, "w", newline="", encoding="utf-8-sig") as fh:
        w = csv.writer(fh); w.writerow(["date", "value", "yoy"])
        vals = {d_: v for d_, v in recs}
        for i, (d_, v) in enumerate(recs):
            prev = recs[i-12][1] if i >= 12 else None
            yoy = (v/prev - 1) if (prev and prev != 0) else ""
            w.writerow([d_, v, yoy])
    print(f"저장: {outname}  {len(recs)}개월  ({recs[0][0]}~{recs[-1][0]})  단위={rows[0].get('UNIT_NAME') or '-'}")
    print(f"항목: {rows[0].get('ITEM_NAME1') or '-'}")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--discover", metavar="KW", help="통계표 검색(키워드)")
    ap.add_argument("--items", metavar="STAT", help="세부항목 목록")
    ap.add_argument("--fetch", nargs=2, metavar=("STAT", "ITEM"), help="시계열 저장")
    ap.add_argument("--out", default="semi_export_monthly.csv", help="저장 파일명")
    ap.add_argument("--kw", default="반도체", help="세부항목 검색어(예: 메모리, D램)")
    a = ap.parse_args()
    try:
        if a.discover: discover(a.discover)
        elif a.items: items(a.items, a.kw)
        elif a.fetch: fetch(a.fetch[0], a.fetch[1], a.out)
        else: print(__doc__)
    except SystemExit: raise
    except Exception:
        import traceback; print("\n===== [에러] 아래 복사 ====="); traceback.print_exc()
