#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
dart_disclosure_scanner.py — 발굴 트랙 A레이어(촉매) 자동화 1단계 (PC 실행)
DART OpenAPI 공시목록 수집 → 카탈리스트 키워드 분류 → catalyst_feed.csv.
발굴 surfacing 보조(매수신호 아님). production·C·D·영역3·v41 무수정.

키 로딩: .dart_key → dart_config.json(api_key) → env DART_API_KEY (기존 규약 동일)
코드→corp_code: dart_corp_codes.json (6자리→8자리) 재사용.

사용(PC):
  python dart_disclosure_scanner.py --codes watch_codes.txt --days 14
  python dart_disclosure_scanner.py --codes watch_codes.txt --days 30 --only_catalyst
출력: catalyst_feed.csv (code, corp_name, rcept_dt, report_nm, catalyst, rcept_no)
"""
import argparse, csv, json, os, sys, time
from pathlib import Path
import datetime as dt
BASE = Path(__file__).resolve().parent

CATALYST = [
    ("수주·공급", ["공급계약", "수주", "단일판매", "납품계약"]),
    ("임상·허가", ["임상", "품목허가", "승인", "허가", "희귀의약품", "FDA", "NDA", "ANDA"]),
    ("기술이전·계약", ["기술이전", "라이선스", "기술수출", "양해각서", "협약", "계약 체결", "계약체결"]),
    ("주주환원(+)", ["무상증자", "현금배당", "주식배당"]),
    ("실적", ["영업(잠정)", "잠정실적", "매출액또는손익", "실적"]),
    ("지분·M&A", ["타법인주식", "최대주주", "주식양수도", "합병", "분할"]),
    ("자본조달(역·주의)", ["유상증자", "전환사채", "신주인수권부", "교환사채", "감자"]),
]


def load_api_key():
    f = BASE / ".dart_key"
    if f.exists():
        k = f.read_text(encoding="utf-8").strip()
        if k:
            return k
    f = BASE / "dart_config.json"
    if f.exists():
        try:
            d = json.loads(f.read_text(encoding="utf-8"))
            for v in (d.values() if isinstance(d, dict) else []):
                if isinstance(v, str) and len(v) >= 30:
                    return v.strip()
        except Exception:
            pass
    k = os.environ.get("DART_API_KEY")
    if k:
        return k.strip()
    sys.exit("[오류] DART 키 없음 (.dart_key / dart_config.json / env DART_API_KEY)")


def classify(report_nm):
    n = report_nm
    # 자사주: 취득/신탁/소각 = 주주환원(+) / 처분 = 중립·주의(공급증가) — 취득과 분리
    if ("자기주식" in n) or ("자사주" in n):
        if "처분" in n:
            return "자사주처분(중립·주의)"
        if ("취득" in n) or ("신탁계약 체결" in n) or ("신탁계약체결" in n) or ("소각" in n):
            return "주주환원(+)"
        return "자사주(기타)"
    for cat, kws in CATALYST:
        for kw in kws:
            if kw in n:
                return cat
    return "기타"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", default=None, help="6자리 코드 목록파일(없으면 tickers.txt)")
    ap.add_argument("--days", type=int, default=14)
    ap.add_argument("--only_catalyst", action="store_true", help="기타 제외, 카탈리스트만")
    ap.add_argument("--sleep", type=float, default=0.1)
    ap.add_argument("--out", default="catalyst_feed.csv")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        samples = [("단일판매ㆍ공급계약체결", "수주·공급"), ("임상시험계획 변경승인", "임상·허가"),
                   ("유상증자결정", "자본조달(역·주의)"), ("자기주식취득 결정", "주주환원(+)"), ("자기주식처분 결정", "자사주처분(중립·주의)"),
                   ("기술이전 계약 체결", "기술이전·계약"), ("주주총회소집결의", "기타")]
        ok = sum(classify(n) == e for n, e in samples)
        for n, e in samples:
            print("  [%s] %-22s → %s" % ("OK" if classify(n) == e else "X", n, classify(n)))
        print("self-test: %d/%d" % (ok, len(samples))); sys.exit(0 if ok == len(samples) else 1)

    try:
        import requests
    except ImportError:
        sys.exit("requests 필요: pip install requests")
    key = load_api_key()
    cmap = json.loads((BASE / "dart_corp_codes.json").read_text(encoding="utf-8"))
    cf = a.codes or "tickers.txt"
    codes = [ln.strip() for ln in open(cf, encoding="utf-8") if ln.strip() and not ln.startswith("#")]
    end = dt.date.today(); bgn = end - dt.timedelta(days=a.days)
    URL = "https://opendart.fss.or.kr/api/list.json"
    rows, miss = [], []
    for i, c in enumerate(codes):
        cc = cmap.get(c)
        if not cc:
            miss.append(c); continue
        try:
            r = requests.get(URL, params={"crtfc_key": key, "corp_code": cc,
                "bgn_de": bgn.strftime("%Y%m%d"), "end_de": end.strftime("%Y%m%d"),
                "page_count": 100}, timeout=15).json()
        except Exception as e:
            print("  %s 실패: %r" % (c, e)); continue
        for it in (r.get("list") or []):
            nm = it.get("report_nm", ""); cat = classify(nm)
            if a.only_catalyst and cat == "기타":
                continue
            rows.append((c, it.get("corp_name", ""), it.get("rcept_dt", ""), nm, cat, it.get("rcept_no", "")))
        time.sleep(a.sleep)
        if (i + 1) % 50 == 0:
            print("  ...%d/%d (수집 %d)" % (i + 1, len(codes), len(rows)))

    rows.sort(key=lambda x: (x[2], x[0]), reverse=True)
    with open(a.out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh); w.writerow(["code", "corp_name", "rcept_dt", "report_nm", "catalyst", "rcept_no"]); w.writerows(rows)
    bycat = {}
    for x in rows:
        bycat[x[4]] = bycat.get(x[4], 0) + 1
    print("\n공시 %d건 (코드 %d, 매핑실패 %d) | %s" % (len(rows), len(codes), len(miss), a.out))
    print("카탈리스트 분포:", bycat)
    print("→ 발굴 후보시트 A레이어로 병합(2+ 점등 교집합 확인). 매수신호 아님.")


if __name__ == "__main__":
    main()
