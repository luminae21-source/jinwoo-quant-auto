#!/usr/bin/env python3
"""
fetch_dart_book_equity.py — DART 연도별 장부가(BE) 추출 → book_equity.csv (HML용)
==============================================================================
build_korea_factors.py --book-csv 입력을 생성. 기존 fetch_dart_quarterly.py 패턴 재사용
(.dart_key/dart_config.json 인증, dart_corp_codes.json 매핑, fnlttSinglAcntAll CFS→OFS).

장부가 정의(우선순위):
  1) 지배기업 소유주지분 (ifrs-full_EquityAttributableToOwnersOfParent)  ← FF book equity에 가장 근접
  2) 자본총계 (ifrs-full_Equity / 자기자본총계)                          ← fallback
보고서: reprt_code=11011 (사업보고서 = 회계연도말). 단위: 원.

출력: book_equity.csv  [code, fiscal_year, book_equity]
사용:
  python fetch_dart_book_equity.py --codes-csv universe_codes.csv --start-year 2020 --end-year 2025
  python fetch_dart_book_equity.py --market KOSPI --top-n 500 --start-year 2020   # FDR로 유니버스
  python fetch_dart_book_equity.py --selftest    # 네트워크 없이 파싱 로직 검증
의존성: requests, pandas (+ FDR: --market 사용 시)
"""
import sys, os, io, json, time, zipfile, argparse
import xml.etree.ElementTree as ET
from pathlib import Path
import pandas as pd

BASE = Path(__file__).parent.resolve()
DART_BASE = "https://opendart.fss.or.kr/api"
CONFIG_FILE = BASE / "dart_config.json"
DART_KEY_FILE = BASE / ".dart_key"
CORP_CODE_CACHE = BASE / "dart_corp_codes.json"

# 장부가 계정 (지배주주지분 우선 → 자본총계 fallback)
EQ_CONTROLLING_ID = {"ifrs-full_EquityAttributableToOwnersOfParent", "ifrs_EquityAttributableToOwnersOfParent"}
EQ_CONTROLLING_NM = {"지배기업 소유주지분", "지배기업의 소유주에게 귀속되는 자본",
                     "지배기업의 소유주지분", "지배기업소유주지분"}
EQ_TOTAL_ID = {"ifrs-full_Equity", "ifrs_Equity"}
EQ_TOTAL_NM = {"자본총계", "자기자본총계", "자기자본"}


def _ensure_requests():
    try:
        import requests; return requests
    except ImportError:
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "requests"], check=True)
        import requests; return requests


def get_api_key():
    k = os.environ.get("DART_API_KEY")
    if k: return k.strip()
    if CONFIG_FILE.exists():
        try:
            k = json.loads(CONFIG_FILE.read_text(encoding="utf-8")).get("api_key")
            if k: return k.strip()
        except Exception:
            pass
    if DART_KEY_FILE.exists():
        k = DART_KEY_FILE.read_text(encoding="utf-8").strip()
        if k: return k
    return None


def get_corp_code_map(api_key, requests_mod):
    if CORP_CODE_CACHE.exists():
        return json.loads(CORP_CODE_CACHE.read_text(encoding="utf-8"))
    r = requests_mod.get(f"{DART_BASE}/corpCode.xml", params={"crtfc_key": api_key}, timeout=30)
    r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf:
        root = ET.fromstring(zf.read("CORPCODE.xml"))
    m = {}
    for c in root.findall("list"):
        sc = (c.findtext("stock_code") or "").strip()
        cc = (c.findtext("corp_code") or "").strip()
        if sc and cc and sc != " ":
            m[sc] = cc
    CORP_CODE_CACHE.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    return m


def fetch_annual_financials(corp_code, year, api_key, requests_mod):
    """사업보고서(11011) 전체 재무제표. CFS(연결)→OFS(별도) fallback."""
    params = {"crtfc_key": api_key, "corp_code": corp_code,
              "bsns_year": str(year), "reprt_code": "11011", "fs_div": "CFS"}
    try:
        d = requests_mod.get(f"{DART_BASE}/fnlttSinglAcntAll.json", params=params, timeout=15).json()
        if d.get("status") == "013":   # 연결 없음 → 별도
            params["fs_div"] = "OFS"
            d = requests_mod.get(f"{DART_BASE}/fnlttSinglAcntAll.json", params=params, timeout=15).json()
        return d.get("list", []) if d.get("status") == "000" else None
    except Exception:
        return None


def extract_book_equity(fs_list):
    """재무상태표(BS)에서 장부가 추출. 지배주주지분 우선, 없으면 자본총계."""
    if not fs_list:
        return None
    controlling, total = None, None
    for it in fs_list:
        if (it.get("sj_div") or "").strip() not in ("BS", ""):   # 재무상태표만
            continue
        aid = (it.get("account_id") or "").strip()
        anm = (it.get("account_nm") or "").strip().replace(" ", "")
        amt_s = it.get("thstrm_amount", "")
        try:
            amt = float(str(amt_s).replace(",", "")) if amt_s not in ("", None) else None
        except (ValueError, TypeError):
            amt = None
        if amt is None:
            continue
        anm_ns = anm
        if aid in EQ_CONTROLLING_ID or anm_ns in {x.replace(" ", "") for x in EQ_CONTROLLING_NM}:
            controlling = controlling or amt
        elif aid in EQ_TOTAL_ID or anm_ns in {x.replace(" ", "") for x in EQ_TOTAL_NM}:
            total = total or amt
    return controlling if controlling is not None else total


def load_codes(args):
    if args.codes_csv and Path(args.codes_csv).exists():
        df = pd.read_csv(args.codes_csv, dtype=str)
        col = "code" if "code" in df.columns else df.columns[0]
        return [str(c).zfill(6) for c in df[col].dropna().tolist()]
    import FinanceDataReader as fdr
    lst = fdr.StockListing(args.market)
    code_col = next(c for c in lst.columns if c.lower() in ("code", "symbol"))
    mcap_col = next((c for c in lst.columns if c.lower() in ("marcap", "marketcap")), None)
    if mcap_col and args.top_n:
        lst = lst.sort_values(mcap_col, ascending=False).head(args.top_n)
    return [str(c).zfill(6) for c in lst[code_col].dropna().tolist()]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes-csv", default=None, help="유니버스 코드 CSV ('code' 열). 없으면 FDR")
    ap.add_argument("--market", default="KOSPI")
    ap.add_argument("--top-n", type=int, default=500)
    ap.add_argument("--start-year", type=int, default=2020)
    ap.add_argument("--end-year", type=int, default=2025)
    ap.add_argument("--out", default="book_equity.csv")
    ap.add_argument("--sleep", type=float, default=0.05)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()

    req = _ensure_requests()
    key = get_api_key()
    if not key:
        print("❌ DART API key 없음 (.dart_key / dart_config.json / env DART_API_KEY)"); return 1
    cmap = get_corp_code_map(key, req)
    codes = load_codes(a)
    years = list(range(a.start_year, a.end_year + 1))
    print(f"장부가 수집: {len(codes)}종목 × {len(years)}년 = {len(codes)*len(years)}회 호출")
    rows, ok = [], 0
    for i, code in enumerate(codes):
        cc = cmap.get(code)
        if not cc:
            continue
        for y in years:
            be = extract_book_equity(fetch_annual_financials(cc, y, key, req))
            if be is not None:
                rows.append({"code": code, "fiscal_year": y, "book_equity": be}); ok += 1
            time.sleep(a.sleep)
        if (i + 1) % 50 == 0:
            print(f"  ...{i+1}/{len(codes)} 종목")
    df = pd.DataFrame(rows)
    df.to_csv(a.out, index=False, encoding="utf-8-sig")
    print(f"\n✅ 저장: {a.out}  ({ok}행, {df['code'].nunique() if len(df) else 0}종목)")
    print("다음: python build_korea_factors.py --book-csv %s ... (HML 산출)" % a.out)


def _selftest():
    # DART fnlttSinglAcntAll 응답 모사 (BS 항목)
    sample = [
        {"sj_div": "BS", "account_id": "ifrs-full_Assets", "account_nm": "자산총계", "thstrm_amount": "1,000,000"},
        {"sj_div": "BS", "account_id": "ifrs-full_Equity", "account_nm": "자본총계", "thstrm_amount": "600,000"},
        {"sj_div": "BS", "account_id": "ifrs-full_EquityAttributableToOwnersOfParent",
         "account_nm": "지배기업 소유주지분", "thstrm_amount": "550,000"},
        {"sj_div": "IS", "account_id": "ifrs-full_Revenue", "account_nm": "매출액", "thstrm_amount": "2,000,000"},
    ]
    be = extract_book_equity(sample)
    print(f"지배주주지분 우선 → {be:,.0f} (기대 550,000)"); assert be == 550000
    # 지배주주지분 없으면 자본총계
    no_ctrl = [x for x in sample if "Owners" not in (x["account_id"])]
    be2 = extract_book_equity(no_ctrl)
    print(f"자본총계 fallback → {be2:,.0f} (기대 600,000)"); assert be2 == 600000
    # 빈 입력
    assert extract_book_equity(None) is None and extract_book_equity([]) is None
    # 콤마/단위 파싱
    assert extract_book_equity([{"sj_div":"BS","account_id":"ifrs-full_Equity","account_nm":"자본총계","thstrm_amount":"1,234,567"}]) == 1234567
    print("[OK] fetch_dart_book_equity 파싱 로직 검증 통과")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
