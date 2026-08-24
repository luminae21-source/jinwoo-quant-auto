#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""dart_value_factors.py — EBITDA / EV / FCF 재무 line item 수집 (OpenDART, requests 직접)

진우님 기존 스택(수집_GP재무_DART.py · fetch_dart_fundamentals_pit.py)과 100% 동일 방식:
  · OpenDartReader 미사용 (Python 3.14 호환) — requests + 표준 라이브러리만
  · 키: .dart_key / dart_config.json / 환경변수 DART_API_KEY / 재무_APIKEY.txt (기존 키 그대로)
  · dart_corp_codes.json 캐시 재사용 (없으면 자동 생성)
  · fnlttSinglAcntAll (reprt_code 11011 사업보고서, CFS→OFS 폴백)
  · 재개(resume): 이미 받은 (code,year) 건너뜀 · 종목마다 flush(중단에도 보존)

기존 fundamentals_pit.csv 엔 영업이익·영업CF·현금·부채가 이미 있음.
이 스크립트가 추가로 받는 '빠진 조각' → EBITDA·순부채·FCF 완성:
  · 감가상각비 · 무형자산상각(현금흐름표 가산항목)
  · 유형자산의취득 = CAPEX (투자활동)
  · 단기차입금 · 장기차입금 · 사채 (이자부부채) · 현금및현금성자산

계산(저장):
  EBITDA = 영업이익 + 감가상각비 + 무형자산상각
  순부채  = (단기+장기차입금+사채) - 현금및현금성자산
  FCF    = 영업활동현금흐름 - CAPEX
→ 재무상세_EBITDA.csv (code, fiscal_year, 원자료 + EBITDA/순부채/FCF)
그 뒤: 대화에 CSV 올리면 시총과 결합해 EV=시총+순부채, EV/EBITDA, FCF수익률 팩터를 IC·롱숏 검정.

사용:
  py dart_value_factors.py --selftest
  py dart_value_factors.py                       (종목시총_30년.csv 최신 상위 500, 2020~2025)
  py dart_value_factors.py --codes _gp_codes.csv --start-year 2015 --end-year 2025
  py dart_value_factors.py --codes 005930,000660 (테스트: 몇 종목만)

⚠️ 정보용·과거재무. 미래보장 아님. 투자자문 아님·책임 본인.
"""
import os, sys, io, json, time, zipfile, argparse, csv
import xml.etree.ElementTree as ET
from pathlib import Path

BASE = Path(__file__).parent.resolve()
DART_BASE = "https://opendart.fss.or.kr/api"
# 키/캐시: 강화키트 폴더와 그 부모(진우퀀트) 둘 다 탐색 — 기존 파일 재사용
SEARCH_DIRS = [BASE, BASE.parent]
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 받을 계정(부분일치 후보 — DART 라벨 편차 대응). 값은 max(abs) 로 선택.
ITEMS = {
    "op_income":  ["영업이익(손실)", "영업이익"],
    "depr":       ["유형자산감가상각비", "감가상각비"],
    "amort":      ["무형자산상각비", "무형자산상각"],
    "cfo":        ["영업활동현금흐름", "영업활동으로인한현금흐름", "영업활동으로 인한 현금흐름"],
    "capex":      ["유형자산의취득", "유형자산취득", "유형자산의 취득"],
    "st_debt":    ["단기차입금"],
    "lt_debt":    ["장기차입금"],
    "bond":       ["사채"],
    "cash":       ["현금및현금성자산", "현금및현금 성자산"],
}
OUT_COLS = ["code", "fiscal_year", "op_income", "depr", "amort", "cfo", "capex",
            "st_debt", "lt_debt", "bond", "cash", "EBITDA", "net_debt", "FCF"]


def _ensure_requests():
    try:
        import requests; return requests
    except ImportError:
        import subprocess
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "requests"], check=True)
        import requests; return requests


def _find(fn):
    for d in SEARCH_DIRS:
        p = d / fn
        if p.exists():
            return p
    return None


def get_api_key():
    k = os.environ.get("DART_API_KEY")
    if k and k.strip():
        return k.strip()
    cfg = _find("dart_config.json")
    if cfg:
        try:
            k = json.loads(Path(cfg).read_text(encoding="utf-8")).get("api_key")
            if k:
                return k.strip()
        except Exception:
            pass
    for name in (".dart_key", "재무_APIKEY.txt"):
        f = _find(name)
        if f:
            try:
                for ln in Path(f).read_text(encoding="utf-8-sig").splitlines():
                    if ln.strip():
                        return ln.strip()
            except Exception:
                pass
    return None


def get_corp_map(key, req):
    cache = _find("dart_corp_codes.json") or (BASE / "dart_corp_codes.json")
    if Path(cache).exists():
        try:
            return json.loads(Path(cache).read_text(encoding="utf-8"))
        except Exception:
            pass
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
    Path(cache).write_text(json.dumps(m, ensure_ascii=False), encoding="utf-8")
    return m


def fetch_annual(corp_code, year, key, req):
    p = {"crtfc_key": key, "corp_code": corp_code, "bsns_year": str(year),
         "reprt_code": "11011", "fs_div": "CFS"}
    try:
        d = req.get(f"{DART_BASE}/fnlttSinglAcntAll.json", params=p, timeout=15).json()
        if d.get("status") == "013":   # 연결 없음 → 별도
            p["fs_div"] = "OFS"
            d = req.get(f"{DART_BASE}/fnlttSinglAcntAll.json", params=p, timeout=15).json()
        return d.get("list", []) if d.get("status") == "000" else None
    except Exception:
        return None


def _num(s):
    try:
        return float(str(s).replace(",", "")) if s not in ("", None, "-") else None
    except (ValueError, TypeError):
        return None


def extract(fs_list):
    """각 계정 후보를 부분일치로 찾아 |값| 최대치 선택.
    감가상각/무형상각은 회사별 라벨 편차가 커서 '감가상각' 포함 계정을 폭넓게 잡음
    (유형·사용권·투자부동산·결합라벨 등 → 커버리지 개선). max(abs)로 총액성 라벨 우선."""
    out = {}
    if not fs_list:
        return out
    for key, cands in ITEMS.items():
        if key in ("depr", "amort"):
            continue
        best = None
        for it in fs_list:
            anm = (it.get("account_nm") or "").replace(" ", "")
            if any(cand.replace(" ", "") in anm for cand in cands):
                v = _num(it.get("thstrm_amount"))
                if v is not None and (best is None or abs(v) > abs(best)):
                    best = v
        if best is not None:
            out[key] = best
    # 감가상각(depr): '감가상각' 포함 전부 중 |값| 최대 (유형·사용권·투자부동산·결합)
    # 무형상각(amort): '무형'+'상각' 또는 '상각비'(감가 제외) 중 |값| 최대
    dbest = abest = None
    for it in fs_list:
        anm = (it.get("account_nm") or "").replace(" ", "")
        v = _num(it.get("thstrm_amount"))
        if v is None:
            continue
        if "감가상각" in anm:
            if dbest is None or abs(v) > abs(dbest): dbest = v
        elif ("무형" in anm and "상각" in anm) or ("상각비" in anm and "감가" not in anm and "대손" not in anm):  # 대손상각비(bad-debt) 오탐 제외
            if abest is None or abs(v) > abs(abest): abest = v
    if dbest is not None: out["depr"] = dbest
    if abest is not None: out["amort"] = abest
    return out


def compute(it):
    g = lambda k: it.get(k)
    oi, dep, amo = g("op_income"), g("depr") or 0, g("amort") or 0
    ebitda = (oi + dep + amo) if oi is not None else None
    debt = sum(v for v in (g("st_debt"), g("lt_debt"), g("bond")) if v is not None)
    net_debt = debt - (g("cash") or 0) if (g("st_debt") or g("lt_debt") or g("bond")) is not None else None
    cfo, capex = g("cfo"), g("capex")
    fcf = (cfo - abs(capex)) if (cfo is not None and capex is not None) else (cfo if cfo is not None else None)
    return ebitda, net_debt, fcf


def load_done(outpath):
    done = set()
    if os.path.exists(outpath):
        with open(outpath, encoding="utf-8-sig") as f:
            for row in csv.DictReader(f):
                done.add((row["code"], str(row["fiscal_year"])))
    return done


def load_codes(spec):
    import pandas as pd
    if spec and ("," in spec or (len(spec) == 6 and spec.isdigit())):
        return [c.strip().zfill(6) for c in spec.split(",") if c.strip()]
    if spec and os.path.exists(spec):
        df = pd.read_csv(spec, dtype=str)
        col = "code" if "code" in df.columns else df.columns[0]
        return [str(c).zfill(6) for c in df[col].dropna().tolist()]
    # 기본: 종목시총_30년.csv 최신월 상위 N
    p = _find("종목시총_30년.csv")
    if p:
        df = pd.read_csv(p, dtype={"code": str})
        df["code"] = df["code"].str.zfill(6)
        last = df["date"].max()
        top = df[df["date"] == last].sort_values("mcap", ascending=False)
        return [c for c in top["code"].head(TOPN)]
    print("종목 소스 없음 → --codes 로 지정"); return []


TOPN = 500


def run(a):
    global TOPN
    TOPN = a.topn
    req = _ensure_requests()
    key = get_api_key()
    if not key:
        print("❌ DART API key 없음 (.dart_key / dart_config.json / DART_API_KEY / 재무_APIKEY.txt)")
        return 1
    print(f"키 OK (…{key[-4:]}). corp 매핑 로드 중…", flush=True)
    cmap = get_corp_map(key, req)
    codes = load_codes(a.codes)
    if not codes:
        return 1
    years = list(range(a.start_year, a.end_year + 1))
    outpath = os.path.join(BASE, a.out)
    if getattr(a, "rebuild", False) and os.path.exists(outpath):
        os.remove(outpath); print("  --rebuild: 기존 CSV 삭제 후 전면 재수집(감가상각 매칭 개선 반영)", flush=True)
    done = load_done(outpath)
    print(f"수집: {len(codes)}종목 × {len(years)}년 (이미 {len(done)}칸 완료 → 스킵)", flush=True)

    new_file = not os.path.exists(outpath)
    f = open(outpath, "a", encoding="utf-8-sig", newline="")
    w = csv.DictWriter(f, fieldnames=OUT_COLS)
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
                if it:
                    ebitda, net_debt, fcf = compute(it)
                    row = {"code": code, "fiscal_year": y, "EBITDA": ebitda,
                           "net_debt": net_debt, "FCF": fcf}
                    for k in ("op_income", "depr", "amort", "cfo", "capex",
                              "st_debt", "lt_debt", "bond", "cash"):
                        row[k] = it.get(k)
                    w.writerow(row); got += 1
                time.sleep(a.sleep)
            f.flush()
            if (i + 1) % 50 == 0:
                print(f"  …{i+1}/{len(codes)}종목 · 신규 {got}행 · 스킵 {skipped}", flush=True)
    except KeyboardInterrupt:
        print("\n⏸️ 중단 — 받은 만큼 저장됨. 다시 실행하면 이어서.", flush=True)
    finally:
        f.close()
    # 감가상각 커버리지 리포트
    try:
        import pandas as pd
        d = pd.read_csv(outpath, dtype={"code": str})
        cov = 100.0 * d["depr"].notna().mean() if len(d) else 0
        print(f"\n✅ 저장: {a.out} (신규 {got}행 · 스킵 {skipped} · corp없음 {miss}) · 감가상각 커버리지 {cov:.0f}%", flush=True)
    except Exception:
        print(f"\n✅ 저장: {a.out} (신규 {got}행 · 스킵 {skipped} · corp없음 {miss})", flush=True)
    print("   다음: recommend_verify 또는 ev_fcf_factor_test.py 로 EV/EBITDA·FCF 재검정.", flush=True)
    return 0


def _selftest():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot
        tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    sample = [
        {"account_nm": "영업이익", "thstrm_amount": "1,000"},
        {"account_nm": "감가상각비", "thstrm_amount": "300"},
        {"account_nm": "무형자산상각비", "thstrm_amount": "50"},
        {"account_nm": "영업활동현금흐름", "thstrm_amount": "1,200"},
        {"account_nm": "유형자산의취득", "thstrm_amount": "-400"},
        {"account_nm": "단기차입금", "thstrm_amount": "200"},
        {"account_nm": "장기차입금", "thstrm_amount": "500"},
        {"account_nm": "사채", "thstrm_amount": "300"},
        {"account_nm": "현금및현금성자산", "thstrm_amount": "600"},
        {"account_nm": "기타", "thstrm_amount": "9"},
    ]
    it = extract(sample)
    chk("영업이익 파싱", it.get("op_income") == 1000)
    chk("감가상각 파싱", it.get("depr") == 300)
    chk("CAPEX 파싱(절댓값)", it.get("capex") == -400)
    e, nd, fcf = compute(it)
    chk("EBITDA=1000+300+50=1350", e == 1350)
    chk("순부채=(200+500+300)-600=400", nd == 400)
    chk("FCF=1200-|−400|=800", fcf == 800)
    chk("빈 리스트 → {}", extract([]) == {})
    chk("영업이익(손실) 별칭 인식",
        extract([{"account_nm": "영업이익(손실)", "thstrm_amount": "7"}]).get("op_income") == 7)
    # 감가상각 매칭 확장: 사용권/투자부동산/결합 라벨도 잡히나
    chk("사용권자산감가상각비 인식",
        extract([{"account_nm": "사용권자산감가상각비", "thstrm_amount": "120"}]).get("depr") == 120)
    chk("투자부동산감가상각비 인식",
        extract([{"account_nm": "투자부동산감가상각비", "thstrm_amount": "40"}]).get("depr") == 40)
    chk("무형자산상각(감가 아님) 분리",
        extract([{"account_nm": "무형자산상각", "thstrm_amount": "9"}]).get("amort") == 9)
    import tempfile
    tp = os.path.join(tempfile.gettempdir(), "_ebitda_done_test.csv")
    with open(tp, "w", encoding="utf-8-sig", newline="") as f:
        wr = csv.DictWriter(f, fieldnames=OUT_COLS); wr.writeheader()
        wr.writerow({"code": "005930", "fiscal_year": "2022"})
    done = load_done(tp); os.remove(tp)
    chk("재개: (code,year) 로드", ("005930", "2022") in done)
    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--codes", default=None, help="파일경로 | 005930,000660 | (미지정=시총상위 topn)")
    ap.add_argument("--start-year", dest="start_year", type=int, default=2020)
    ap.add_argument("--end-year", dest="end_year", type=int, default=2025)
    ap.add_argument("--topn", type=int, default=500)
    ap.add_argument("--out", default="재무상세_EBITDA.csv")
    ap.add_argument("--sleep", type=float, default=0.05)
    ap.add_argument("--rebuild", action="store_true", help="기존 CSV 삭제 후 전면 재수집(감가상각 매칭 개선 반영)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return 0 if _selftest() else 1
    return run(a)


if __name__ == "__main__":
    sys.exit(main() or 0)
