#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kosdaq_catalyst_scan_v1.py — 촉매·수급 스캐너 (v1, forward 신호 'A 촉매 + C 수급')
"지금 뭐가 불붙나"를 뉴스 되기 전에: DART 공시(수주·증설·신제품) + 외국인·기관 순매수.
2개 이상 동시 점등 = 주목 후보. production·C·D·영역3·v41 무수정. 발굴 보조 — 매수신호 아님.

데이터(네트워크 → [PC] 전용): DART OpenAPI(list.json) + pykrx 수급.
대상 종목 = kosdaq_theme_chain_map.csv(코스닥 peer) + kosdaq_theme_watchlist.csv.

사용:
  python kosdaq_catalyst_scan_v1.py --self-test    # 오프라인 로직 점검
  python kosdaq_catalyst_scan_v1.py                # [PC] 최근 공시+수급 → 점등 종목
  python kosdaq_catalyst_scan_v1.py --days 14
"""
import csv, os, sys, json, time, datetime as dt
from pathlib import Path

BASE = Path(__file__).parent.resolve()

# 高신호 공시 키워드(촉매). 부호는 진우 판단 — 표시만.
CATALYST_KW = ["공급계약", "단일판매", "수주", "신규시설", "시설투자", "증설",
               "신제품", "기술이전", "기술수출", "특허취득", "임상", "국책", "대규모"]


def load_api_key():
    f = BASE / ".dart_key"
    if f.exists():
        k = f.read_text(encoding="utf-8").strip()
        if len(k) >= 30:
            return k
    f = BASE / "dart_config.json"
    if f.exists():
        try:
            d = json.load(open(f, encoding="utf-8"))
            for v in (d.values() if isinstance(d, dict) else []):
                if isinstance(v, str) and len(v) >= 30:
                    return v
        except Exception:
            pass
    return os.environ.get("DART_API_KEY")


def load_universe():
    codes = {}
    p = BASE / "kosdaq_theme_chain_map.csv"
    if p.exists():
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            if r.get("market") == "KOSDAQ":
                codes[r["ticker"]] = r["name"]
    p = BASE / "kosdaq_theme_watchlist.csv"
    if p.exists():
        for r in csv.DictReader(open(p, encoding="utf-8-sig")):
            codes.setdefault(r.get("code", ""), r.get("name", ""))
    codes.pop("", None)
    return codes


def load_corp_map():
    p = BASE / "dart_corp_codes.json"
    if not p.exists():
        return {}
    d = json.load(open(p, encoding="utf-8"))
    if isinstance(d, dict) and all(isinstance(v, str) for v in d.values()):
        return {str(k).zfill(6): v for k, v in d.items()}     # {종목코드: corp_code}
    out = {}
    if isinstance(d, list):
        for it in d:
            sc = str(it.get("stock_code", "")).zfill(6); cc = str(it.get("corp_code", ""))
            if sc and cc:
                out[sc] = cc
    return out


def match_catalyst(report_nm):
    """공시명 → 매칭된 촉매 키워드(없으면 None). 순수함수(테스트용)."""
    for kw in CATALYST_KW:
        if kw in (report_nm or ""):
            return kw
    return None


def combine(univ, catalysts, foreign_set, inst_set):
    """종목별 점등 플래그 + 점등수. 순수함수(테스트용)."""
    out = []
    for code, name in univ.items():
        cat = catalysts.get(code)
        f = code in foreign_set
        i = code in inst_set
        lit = sum([bool(cat), f, i])
        out.append({"code": code, "name": name, "촉매": cat or "",
                    "외국인": f, "기관": i, "점등": lit})
    out.sort(key=lambda d: (-d["점등"], d["name"]))
    return out


# ---------- [PC] 네트워크 ----------
def fetch_catalysts(api_key, corp_map, univ, days):
    import requests
    end = dt.date.today(); bgn = end - dt.timedelta(days=days)
    res = {}
    for code, name in univ.items():
        cc = corp_map.get(code)
        if not cc:
            continue
        try:
            r = requests.get("https://opendart.fss.or.kr/api/list.json",
                             params={"crtfc_key": api_key, "corp_code": cc,
                                     "bgn_de": bgn.strftime("%Y%m%d"), "end_de": end.strftime("%Y%m%d"),
                                     "page_count": 100}, timeout=15).json()
            for it in r.get("list", []):
                kw = match_catalyst(it.get("report_nm"))
                if kw:
                    res[code] = "%s(%s)" % (kw, it.get("rcept_dt", "")[4:])
                    break
        except Exception as e:
            print("  [DART 실패]", name, e)
        time.sleep(0.12)
    return res


def fetch_supply(univ, days):
    from pykrx import stock
    end = dt.date.today(); bgn = end - dt.timedelta(days=days)
    s, e = bgn.strftime("%Y%m%d"), end.strftime("%Y%m%d")
    def top_buyers(inv):
        try:
            df = stock.get_market_net_purchases_of_equities(s, e, "KOSDAQ", inv)
            col = "순매수거래대금" if "순매수거래대금" in df.columns else df.columns[-1]
            buy = df[df[col] > 0]
            return set(str(t).zfill(6) for t in buy.index)
        except Exception as ex:
            print("  [수급 실패:%s] %s" % (inv, ex)); return set()
    return top_buyers("외국인"), top_buyers("기관합계")


def main():
    days = 14
    if "--days" in sys.argv:
        try: days = int(sys.argv[sys.argv.index("--days") + 1])
        except (ValueError, IndexError): pass
    univ = load_universe()
    print("=== 촉매·수급 스캐너 (최근 %d일) — 대상 %d종 ===" % (days, len(univ)))
    key = load_api_key()
    corp = load_corp_map()
    cats = fetch_catalysts(key, corp, univ, days) if key else {}
    if not key:
        print("  [경고] DART 키 없음 → 촉매 생략")
    f_set, i_set = fetch_supply(univ, max(5, days // 2))
    rows = combine(univ, cats, f_set, i_set)
    print("\n점등 | 종목 | 촉매(DART) | 외국인 | 기관")
    for d in rows:
        if d["점등"] == 0:
            continue
        star = "★★" if d["점등"] >= 2 else "★ "
        print("  %s %-12s | %-16s | %s | %s"
              % (star, d["name"], d["촉매"] or "-", "순매수" if d["외국인"] else "-", "순매수" if d["기관"] else "-"))
    n2 = sum(1 for d in rows if d["점등"] >= 2)
    print("\n★★ 2+ 점등(주목) %d건 / 1+ 점등 %d건. (가드레일·thesis·선반영 체크는 운영매뉴얼대로 — 매수신호 아님)"
          % (n2, sum(1 for d in rows if d["점등"] >= 1)))


def self_test():
    univ = {"111111": "수주난종목", "222222": "수급종목", "333333": "둘다종목", "444444": "무신호"}
    cats = {"111111": match_catalyst("단일판매ㆍ공급계약체결"), "333333": match_catalyst("신규시설투자등")}
    cats = {k: v for k, v in cats.items() if v}
    foreign = {"222222", "333333"}; inst = {"333333"}
    rows = combine(univ, cats, foreign, inst)
    by = {d["code"]: d for d in rows}
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print("  [%s] %s" % ("OK" if c else "FAIL", n))
    chk("공급계약→촉매 매칭", match_catalyst("단일판매ㆍ공급계약체결") == "공급계약")
    chk("일반공시→매칭 없음", match_catalyst("기업설명회(IR) 개최") is None)
    chk("둘다종목 점등=3", by["333333"]["점등"] == 3)
    chk("수급종목 점등=1", by["222222"]["점등"] == 1)
    chk("무신호 점등=0", by["444444"]["점등"] == 0)
    chk("정렬: 최다점등 선두", rows[0]["code"] == "333333")
    print("self-test: %d/%d" % (ok, tot))
    return ok == tot


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        main()
