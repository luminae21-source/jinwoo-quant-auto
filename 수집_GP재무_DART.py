#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""수집_GP재무_DART.py — GP(수익성)용 재무 수집기 (재개 가능)

GP = (매출 − 매출원가) / 자산. 딱 3개 항목만 DART에서 받는다(빠름).
DART fnlttSinglAcntAll(reprt_code 11011, CFS→OFS 폴백). **FY2015부터만 제공.**

★ 재개 가능: 출력 CSV에 이미 있는 (code,year)는 건너뛴다. 중간에 끊겨도 이어서.
★ 증분 저장: 매 종목마다 flush → Ctrl-C/오류에도 받은 만큼 보존.

사용:
  py 수집_GP재무_DART.py --selftest
  py 수집_GP재무_DART.py --codes _gp_codes.csv --start-year 2015 --end-year 2025
  py 수집_GP재무_DART.py --codes _gp_codes_preview.csv   (키·연결 확인용 소량)
"""
import os, sys, io, json, time, zipfile, argparse, csv
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = Path(__file__).parent.resolve()
DART_BASE = "https://opendart.fss.or.kr/api"
CONFIG_FILE = BASE / "dart_config.json"
DART_KEY_FILE = BASE / ".dart_key"
CORP_CODE_CACHE = BASE / "dart_corp_codes.json"
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# GP에 필요한 3항목만
ITEMS = {
    "revenue": ({"ifrs-full_Revenue", "ifrs_Revenue"},
                {"매출액", "수익(매출액)", "영업수익", "매출"}),
    "cogs":    ({"ifrs-full_CostOfSales", "ifrs_CostOfSales"}, {"매출원가"}),
    "assets":  ({"ifrs-full_Assets"}, {"자산총계"}),
}


def _ensure_requests():
    try:
        import requests; return requests
    except ImportError:
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "requests"], check=True)
        import requests; return requests


def get_api_key():
    k = os.environ.get("DART_API_KEY")
    if k:
        return k.strip()
    if CONFIG_FILE.exists():
        try:
            k = json.loads(CONFIG_FILE.read_text(encoding="utf-8")).get("api_key")
            if k:
                return k.strip()
        except Exception:
            pass
    if DART_KEY_FILE.exists():
        k = DART_KEY_FILE.read_text(encoding="utf-8").strip()
        if k:
            return k
    return None


def get_corp_map(key, req):
    if CORP_CODE_CACHE.exists():
        return json.loads(CORP_CODE_CACHE.read_text(encoding="utf-8"))
    r = req.get(f"{DART_BASE}/corpCode.xml", params={"crtfc_key": key}, timeout=30)
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


def fetch_annual(corp_code, year, key, req):
    p = {"crtfc_key": key, "corp_code": corp_code, "bsns_year": str(year),
         "reprt_code": "11011", "fs_div": "CFS"}
    try:
        d = req.get(f"{DART_BASE}/fnlttSinglAcntAll.json", params=p, timeout=15).json()
        if d.get("status") == "013":
            p["fs_div"] = "OFS"
            d = req.get(f"{DART_BASE}/fnlttSinglAcntAll.json", params=p, timeout=15).json()
        return d.get("list", []) if d.get("status") == "000" else None
    except Exception:
        return None


def extract(fs_list):
    if not fs_list:
        return {}
    out = {}
    for it in fs_list:
        aid = (it.get("account_id") or "").strip()
        anm = (it.get("account_nm") or "").strip().replace(" ", "")
        amt_s = it.get("thstrm_amount", "")
        try:
            amt = float(str(amt_s).replace(",", "")) if amt_s not in ("", None) else None
        except (ValueError, TypeError):
            amt = None
        if amt is None:
            continue
        for key, (ids, nms) in ITEMS.items():
            if key in out:
                continue
            if aid in ids or anm in {n.replace(" ", "") for n in nms}:
                out[key] = amt
    return out


def load_done(outpath):
    """이미 수집된 (code,year) 집합 — 재개용."""
    done = set()
    if os.path.exists(outpath):
        with open(outpath, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                done.add((row["code"], row["fiscal_year"]))
    return done


def load_codes(path):
    import pandas as pd
    df = pd.read_csv(path, dtype=str)
    col = "code" if "code" in df.columns else df.columns[0]
    return [str(c).zfill(6) for c in df[col].dropna().tolist()]


def run(a):
    req = _ensure_requests()
    key = get_api_key()
    if not key:
        print("❌ DART API key 없음 (.dart_key / dart_config.json)"); return 1
    cmap = get_corp_map(key, req)
    codes = load_codes(a.codes)
    years = list(range(a.start_year, a.end_year + 1))
    outpath = os.path.join(BASE, a.out)
    done = load_done(outpath)
    print(f"수집: {len(codes)}종목 × {len(years)}년 = {len(codes)*len(years)}칸 "
          f"(이미 {len(done)}칸 완료 → 건너뜀)", flush=True)

    header = ["code", "fiscal_year", "revenue", "cogs", "assets"]
    new_file = not os.path.exists(outpath)
    f = open(outpath, "a", encoding="utf-8-sig", newline="")
    w = csv.DictWriter(f, fieldnames=header)
    if new_file:
        w.writeheader(); f.flush()

    got = skipped = miss = 0
    try:
        for i, code in enumerate(codes):
            cc = cmap.get(code)
            if not cc:
                miss += 1; continue
            for y in years:
                if (code, str(y)) in done:
                    skipped += 1; continue
                it = extract(fetch_annual(cc, y, key, req))
                if it.get("revenue") is not None and it.get("cogs") is not None \
                        and it.get("assets"):
                    w.writerow({"code": code, "fiscal_year": y,
                                "revenue": it["revenue"], "cogs": it["cogs"],
                                "assets": it["assets"]})
                    got += 1
                time.sleep(a.sleep)
            f.flush()   # 종목마다 저장 → 중단에도 보존
            if (i + 1) % 50 == 0:
                print(f"  ...{i+1}/{len(codes)}종목 · 신규 {got}행 · 스킵 {skipped}", flush=True)
    except KeyboardInterrupt:
        print("\n⏸️ 중단됨 — 받은 만큼 저장됨. 다시 실행하면 이어서 받습니다.", flush=True)
    finally:
        f.close()
    print(f"\n✅ 저장: {a.out} (이번 신규 {got}행 · 스킵 {skipped} · corp없음 {miss}) "
          f"— 다시 실행하면 이어서.", flush=True)
    return 0


def _selftest():
    ok = tot = 0

    def chk(n, c):
        nonlocal ok, tot
        tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")

    sample = [
        {"account_id": "ifrs-full_Revenue", "account_nm": "매출액", "thstrm_amount": "3,000,000"},
        {"account_id": "ifrs-full_CostOfSales", "account_nm": "매출원가", "thstrm_amount": "1,800,000"},
        {"account_id": "ifrs-full_Assets", "account_nm": "자산총계", "thstrm_amount": "5,000,000"},
        {"account_id": "x", "account_nm": "기타", "thstrm_amount": "1"},
    ]
    it = extract(sample)
    chk("revenue 파싱", it.get("revenue") == 3000000)
    chk("cogs 파싱", it.get("cogs") == 1800000)
    chk("assets 파싱", it.get("assets") == 5000000)
    gp = (it["revenue"] - it["cogs"]) / it["assets"]
    chk("GP=(rev-cogs)/assets=0.24", abs(gp - 0.24) < 1e-9)
    chk("빈 리스트 → {}", extract([]) == {})
    chk("영업수익 별칭 인식", extract([{"account_id": "", "account_nm": "영업수익",
                                       "thstrm_amount": "100"}]).get("revenue") == 100)

    # 재개 로직: load_done 라운드트립
    import tempfile
    tp = os.path.join(tempfile.gettempdir(), "_gp_done_test.csv")
    with open(tp, "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=["code", "fiscal_year", "revenue", "cogs", "assets"])
        wr.writeheader(); wr.writerow({"code": "005930", "fiscal_year": "2018",
                                       "revenue": 1, "cogs": 1, "assets": 1})
    done = load_done(tp)
    os.remove(tp)
    chk("재개: (code,year) 로드", ("005930", "2018") in done)

    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", default="_gp_codes.csv")
    ap.add_argument("--start-year", type=int, default=2015)
    ap.add_argument("--end-year", type=int, default=2025)
    ap.add_argument("--out", default="fundamentals_gp_2015_2025.csv")
    ap.add_argument("--sleep", type=float, default=0.05)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return 0 if _selftest() else 1
    return run(a)


if __name__ == "__main__":
    sys.exit(main() or 0)
