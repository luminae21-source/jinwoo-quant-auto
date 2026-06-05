#!/usr/bin/env python3
"""
fetch_dart_fundamentals_pit.py — PIT 검증용 광범위 재무 line item 수집 (Phase A)
==============================================================================
Piotroski F(F_korean 대용)·Sloan·NOA 계산에 필요한 회계연도별 재무항목을
광범위 KOSPI universe에서 DART로 추출 → fundamentals_pit.csv.
기존 fetch_dart_quarterly/fetch_dart_book_equity 패턴 재사용(.dart_key, corp_code, fnlttSinglAcntAll CFS→OFS, 11011).

추출 항목: revenue, cogs, op_income, net_income, assets, liabilities, equity,
          current_assets, current_liab, cash, cfo, noncurrent_liab, issued_capital
사용:
  python fetch_dart_fundamentals_pit.py --market KOSPI --top-n 400 --start-year 2019 --end-year 2025
  python fetch_dart_fundamentals_pit.py --selftest
"""
import sys, os, io, json, time, zipfile, argparse
import xml.etree.ElementTree as ET
from pathlib import Path
import pandas as pd

BASE = Path(__file__).parent.resolve()
DART_BASE = "https://opendart.fss.or.kr/api"
CONFIG_FILE = BASE / "dart_config.json"; DART_KEY_FILE = BASE / ".dart_key"
CORP_CODE_CACHE = BASE / "dart_corp_codes.json"

# 항목: 표준키 -> (account_id 집합, account_nm 집합[공백제거])
ITEMS = {
    "revenue":        ({"ifrs-full_Revenue","ifrs_Revenue"}, {"매출액","수익(매출액)","영업수익","매출"}),
    "cogs":           ({"ifrs-full_CostOfSales","ifrs_CostOfSales"}, {"매출원가"}),
    "op_income":      ({"dart_OperatingIncomeLoss","ifrs-full_OperatingIncomeLoss"}, {"영업이익","영업이익(손실)"}),
    "net_income":     ({"ifrs-full_ProfitLoss","ifrs_ProfitLoss"}, {"당기순이익","당기순이익(손실)","당기순이익(손실)"}),
    "assets":         ({"ifrs-full_Assets"}, {"자산총계"}),
    "liabilities":    ({"ifrs-full_Liabilities"}, {"부채총계"}),
    "equity":         ({"ifrs-full_Equity"}, {"자본총계","자기자본총계"}),
    "current_assets": ({"ifrs-full_CurrentAssets"}, {"유동자산"}),
    "current_liab":   ({"ifrs-full_CurrentLiabilities"}, {"유동부채"}),
    "cash":           ({"ifrs-full_CashAndCashEquivalents"}, {"현금및현금성자산"}),
    "cfo":            ({"ifrs-full_CashFlowsFromUsedInOperatingActivities",
                        "ifrs_CashFlowsFromUsedInOperatingActivities"},
                       {"영업활동현금흐름","영업활동으로인한현금흐름","영업활동순현금흐름"}),
    "noncurrent_liab":({"ifrs-full_NoncurrentLiabilities"}, {"비유동부채"}),
    "issued_capital": ({"ifrs-full_IssuedCapital"}, {"자본금"}),
}


def _ensure_requests():
    try: import requests; return requests
    except ImportError:
        import subprocess; subprocess.run([sys.executable,"-m","pip","install","-q","requests"],check=True)
        import requests; return requests

def get_api_key():
    k = os.environ.get("DART_API_KEY")
    if k: return k.strip()
    if CONFIG_FILE.exists():
        try:
            k = json.loads(CONFIG_FILE.read_text(encoding="utf-8")).get("api_key")
            if k: return k.strip()
        except Exception: pass
    if DART_KEY_FILE.exists():
        k = DART_KEY_FILE.read_text(encoding="utf-8").strip()
        if k: return k
    return None

def get_corp_code_map(api_key, req):
    if CORP_CODE_CACHE.exists():
        return json.loads(CORP_CODE_CACHE.read_text(encoding="utf-8"))
    r = req.get(f"{DART_BASE}/corpCode.xml", params={"crtfc_key": api_key}, timeout=30); r.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(r.content)) as zf: root = ET.fromstring(zf.read("CORPCODE.xml"))
    m = {}
    for c in root.findall("list"):
        sc=(c.findtext("stock_code") or "").strip(); cc=(c.findtext("corp_code") or "").strip()
        if sc and cc and sc != " ": m[sc]=cc
    CORP_CODE_CACHE.write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8"); return m

def fetch_annual(corp_code, year, api_key, req):
    p = {"crtfc_key":api_key,"corp_code":corp_code,"bsns_year":str(year),"reprt_code":"11011","fs_div":"CFS"}
    try:
        d = req.get(f"{DART_BASE}/fnlttSinglAcntAll.json", params=p, timeout=15).json()
        if d.get("status")=="013":
            p["fs_div"]="OFS"; d = req.get(f"{DART_BASE}/fnlttSinglAcntAll.json", params=p, timeout=15).json()
        return d.get("list",[]) if d.get("status")=="000" else None
    except Exception:
        return None

def extract_items(fs_list):
    """fnlttSinglAcntAll list → {표준키: 금액}. account_id 우선, account_nm fallback. 당기금액(thstrm_amount)."""
    if not fs_list: return {}
    out = {}
    for it in fs_list:
        aid = (it.get("account_id") or "").strip()
        anm = (it.get("account_nm") or "").strip().replace(" ", "")
        amt_s = it.get("thstrm_amount","")
        try: amt = float(str(amt_s).replace(",","")) if amt_s not in ("",None) else None
        except (ValueError,TypeError): amt = None
        if amt is None: continue
        for key,(ids,nms) in ITEMS.items():
            if key in out: continue
            nms_ns = {n.replace(" ","") for n in nms}
            if aid in ids or anm in nms_ns:
                out[key]=amt
    return out

def load_codes(args):
    if args.codes_csv and Path(args.codes_csv).exists():
        df = pd.read_csv(args.codes_csv, dtype=str); col="code" if "code" in df.columns else df.columns[0]
        return [str(c).zfill(6) for c in df[col].dropna().tolist()]
    import FinanceDataReader as fdr
    mkts = [m.strip() for m in str(args.market).split(',') if m.strip()]
    parts = []
    for mk in mkts:
        try: parts.append(fdr.StockListing(mk))
        except Exception as e: print(f'  ({mk} 실패: {e})')
    lst = pd.concat(parts, ignore_index=True) if len(parts) > 1 else parts[0]
    cc = next(c for c in lst.columns if c.lower() in ("code","symbol"))
    mc = next((c for c in lst.columns if c.lower() in ("marcap","marketcap")), None)
    if mc and args.top_n: lst = lst.sort_values(mc, ascending=False).head(args.top_n)
    return [str(c).zfill(6) for c in lst[cc].dropna().tolist()]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes-csv", default=None); ap.add_argument("--market", default="KOSPI", help="쉼표 복수: KOSPI,KOSDAQ")
    ap.add_argument("--top-n", type=int, default=400)
    ap.add_argument("--start-year", type=int, default=2019); ap.add_argument("--end-year", type=int, default=2025)
    ap.add_argument("--out", default="fundamentals_pit.csv"); ap.add_argument("--sleep", type=float, default=0.05)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest: return _selftest()
    req=_ensure_requests(); key=get_api_key()
    if not key: print("❌ DART API key 없음"); return 1
    cmap=get_corp_code_map(key, req); codes=load_codes(a); years=list(range(a.start_year,a.end_year+1))
    print(f"재무 수집: {len(codes)}종목 × {len(years)}년 = {len(codes)*len(years)}회")
    rows, ok = [], 0
    for i,code in enumerate(codes):
        cc=cmap.get(code)
        if not cc: continue
        for y in years:
            it = extract_items(fetch_annual(cc,y,key,req))
            if it.get("assets"):
                it.update({"code":code,"fiscal_year":y}); rows.append(it); ok+=1
            time.sleep(a.sleep)
        if (i+1)%50==0: print(f"  ...{i+1}/{len(codes)}종목")
    cols=["code","fiscal_year"]+list(ITEMS.keys())
    df=pd.DataFrame(rows).reindex(columns=cols)
    df.to_csv(a.out, index=False, encoding="utf-8-sig")
    print(f"\n✅ 저장: {a.out} ({ok}행, {df['code'].nunique() if len(df) else 0}종목)")
    print("다음: pit_universe_backtest.py (Phase B)")

def _selftest():
    sample = [
        {"sj_div":"IS","account_id":"ifrs-full_Revenue","account_nm":"매출액","thstrm_amount":"3,000,000"},
        {"sj_div":"IS","account_id":"ifrs-full_CostOfSales","account_nm":"매출원가","thstrm_amount":"1,800,000"},
        {"sj_div":"IS","account_id":"ifrs-full_ProfitLoss","account_nm":"당기순이익","thstrm_amount":"250,000"},
        {"sj_div":"BS","account_id":"ifrs-full_Assets","account_nm":"자산총계","thstrm_amount":"5,000,000"},
        {"sj_div":"BS","account_id":"ifrs-full_Liabilities","account_nm":"부채총계","thstrm_amount":"2,000,000"},
        {"sj_div":"BS","account_id":"ifrs-full_CurrentAssets","account_nm":"유동자산","thstrm_amount":"1,500,000"},
        {"sj_div":"BS","account_id":"ifrs-full_CurrentLiabilities","account_nm":"유동부채","thstrm_amount":"900,000"},
        {"sj_div":"BS","account_id":"ifrs-full_CashAndCashEquivalents","account_nm":"현금및현금성자산","thstrm_amount":"400,000"},
        {"sj_div":"BS","account_id":"ifrs-full_IssuedCapital","account_nm":"자본금","thstrm_amount":"100,000"},
        {"sj_div":"CF","account_id":"ifrs-full_CashFlowsFromUsedInOperatingActivities","account_nm":"영업활동현금흐름","thstrm_amount":"320,000"},
    ]
    it = extract_items(sample)
    print("추출 결과:", {k: int(v) for k,v in it.items()})
    for k in ("revenue","cogs","net_income","assets","cfo","current_assets","issued_capital"):
        assert k in it, f"{k} 누락"
    assert it["revenue"]==3000000 and it["cfo"]==320000
    # Piotroski 일부·Sloan·NOA 계산 가능성 점검
    gp_margin = (it["revenue"]-it["cogs"])/it["revenue"]; roa = it["net_income"]/it["assets"]
    sloan = (it["net_income"]-it["cfo"])/it["assets"]
    print(f"파생 예: GPmargin={gp_margin:.2f}, ROA={roa:.3f}, Sloan_accrual={sloan:.3f}")
    print("[OK] fetch_dart_fundamentals_pit 파싱 selftest 통과")
    return 0

if __name__ == "__main__":
    sys.exit(main() or 0)
