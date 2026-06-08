#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kosdaq_news_scan_v1.py - 뉴스 촉매 추출엔진 (v1.1, NLP-lite 룰기반)
종목명으로 직접 검색 -> 헤드라인에서 (그 종목 + 무슨 촉매)를 추출.
production/C/D/영역3/v41 무수정. 매수신호 아님.
사용:
  python kosdaq_news_scan_v1.py --self-test
  python kosdaq_news_scan_v1.py            # [PC] naver_api.json 필요
"""
import csv, os, sys, json, time
from pathlib import Path

BASE = Path(__file__).parent.resolve()

NEWS_KW = ["수주", "공급계약", "납품", "증설", "신규시설", "신제품", "양산", "기술이전",
           "기술수출", "특허", "임상", "FDA", "승인", "최대실적", "흑자전환", "수출",
           "목표주가 상향", "목표가 상향", "MOU", "협력", "단독공급", "독점", "역대 최대"]


def load_universe():
    codes = {}
    p = BASE / "kosdaq_theme_chain_map.csv"
    if p.exists():
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            if r.get("market") == "KOSDAQ":
                codes[r["name"]] = r["ticker"]
    p = BASE / "kosdaq_theme_watchlist.csv"
    if p.exists():
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            codes.setdefault(r.get("name", ""), r.get("code", ""))
    codes.pop("", None)
    return codes


def extract_signal(title, names, kws=NEWS_KW):
    t = title or ""
    hits = []
    for nm in names:
        if nm and nm in t:
            for kw in kws:
                if kw in t:
                    hits.append((nm, kw))
                    break
    return hits


def _naver_creds():
    p = BASE / "naver_api.json"
    if p.exists():
        try:
            d = json.load(open(p, encoding="utf-8"))
            return d.get("id") or d.get("client_id"), d.get("secret") or d.get("client_secret")
        except Exception:
            pass
    return os.environ.get("NAVER_ID"), os.environ.get("NAVER_SECRET")


def fetch_news(query, cid, csec, display=15):
    import requests
    r = requests.get("https://openapi.naver.com/v1/search/news.json",
                     headers={"X-Naver-Client-Id": cid, "X-Naver-Client-Secret": csec},
                     params={"query": query, "display": display, "sort": "date"}, timeout=15)
    out = []
    for it in r.json().get("items", []):
        title = it.get("title", "")
        for a, b in [("<b>", ""), ("</b>", ""), ("&quot;", '"'), ("&amp;", "&"),
                     ("&lt;", "<"), ("&gt;", ">"), ("&apos;", "'"), ("&#39;", "'")]:
            title = title.replace(a, b)
        out.append((title, it.get("pubDate", "")))
    return out


def main():
    univ = load_universe()
    cid, csec = _naver_creds()
    print("=== 뉴스 촉매 추출 (NLP-lite, 종목명 검색) - 대상 %d종 ===" % len(univ))
    if not (cid and csec):
        print("  [안내] Naver API 키 없음 -> naver_api.json 설정 후 재실행.")
        return
    seen = {}
    scanned = 0
    for nm, code in univ.items():
        try:
            for title, pub in fetch_news(nm, cid, csec):
                for n2, kw in extract_signal(title, [nm]):
                    seen.setdefault(nm, {}).setdefault(kw, title)
            scanned += 1
        except Exception as e:
            print("  [뉴스 실패]", nm, e)
        time.sleep(0.1)
    print("(%d종 검색 완료)\n" % scanned)
    if not seen:
        print("  포착 0건 - 최근 뉴스에 촉매 키워드 없음(조용한 주). DART 공시/수급 스캐너로 보완.")
        return
    print("종목 | 촉매(뉴스) | 대표 헤드라인")
    for nm in sorted(seen, key=lambda n: -len(seen[n])):
        kws = list(seen[nm].keys())
        head = seen[nm][kws[0]]
        print("  * %-12s | %-12s | %s" % (nm, ", ".join(kws), head[:46]))
    print("\n%d종 뉴스 촉매 포착. (DART/수급과 교차 -> 2+ 점등이면 주목. 매수신호 아님)" % len(seen))


def self_test():
    names = ["주성엔지니어링", "에코프로비엠", "로보티즈", "리노공업"]
    heads = [
        "주성엔지니어링, 대규모 반도체 장비 수주 공시",
        "에코프로비엠 美 공장 증설 본격화",
        "코스닥 시황: 외국인 순매수 지속",
        "리노공업 기업설명회(IR) 개최 예정",
        "로보티즈, 휴머노이드 구동모듈 단독공급 계약",
    ]
    res = [extract_signal(h, names) for h in heads]
    ok = 0
    tot = 0
    def chk(n, c):
        nonlocal ok, tot
        tot += 1
        ok += 1 if c else 0
        print("  [%s] %s" % ("OK" if c else "FAIL", n))
    chk("name+catalyst 추출", ("주성엔지니어링", "수주") in res[0])
    chk("에코+증설 추출", ("에코프로비엠", "증설") in res[1])
    chk("종목명 없음->0", res[2] == [])
    chk("촉매 없음(IR)->0", res[3] == [])
    chk("로보티즈 추출", any(h[0] == "로보티즈" for h in res[4]))
    print("self-test: %d/%d" % (ok, tot))
    return ok == tot


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        main()
