#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_kosdaq_sel_universe.py  —  진우퀀트 v4.1 KOSDAQ 종목선정 (kosdaq_sel) · Stage 1

역할: KOSDAQ-네이티브 종목선정 universe 빌드 (컷오프 캘리브레이션 + 성장·재무 적재).
      production · *_v39_pead* · *_v40_regime* · universe_* 무수정. 신규 파일(kosdaq_sel).

입력(Desktop\\진우퀀트, 전부 로컬 CSV — PC/FDR 불필요):
  - liquidity_kosdaq.csv      code,name,sector(=시장부),mcap,adtv      (1,822종)
  - fundamentals_kosdaq.csv   code,fiscal_year,revenue,cogs,op_income,net_income,
                              assets,liabilities,equity,current_assets,current_liab,
                              cash,cfo,noncurrent_liab,issued_capital  (297종 연간 2019~2025)
  - kosdaq_industry.csv       code,name,sector(=KRX 121 산업)

출력:
  - kosdaq_sel_universe_cache.json   (firms 패널 + 운용 universe + 컷오프)
  - kosdaq_sel_universe_latest.csv   (현 시점 유효 universe 요약)

설계 원칙(결정메모 동결본 기준):
  · 선정기준 = 성장성 + 코스닥 회계특성 재무적합성 (가중·점수화는 Stage 3, 여기선 적재만)
  · 컷오프는 KOSDAQ '분포 기준' 상대 분위 (KOSPI 절대컷 직이식 금지)
  · 가드레일(시총·ADTV)은 현재 스냅샷 = 운용 universe 전용. 백테스트 PIT는 firms.annual 패널로 별도(공시지연).
  · 유효 N 게이트 ≥ 40 (미달 시 종료)
  · 적자기업 多 → 이익 YoY는 부호반전 왜곡 → 매출·CFO를 robust 축, 이익은 흑전/적지 플래그 보조

사용:
  python build_kosdaq_sel_universe.py --self-test     # 합성데이터 검증 (네트워크 불필요)
  python build_kosdaq_sel_universe.py                 # 실데이터 빌드
"""
import csv, json, sys, argparse, statistics, math
from collections import defaultdict

# ---- 시장부 분류 ----
NORMAL_BOARDS = {"중견기업부", "우량기업부", "벤처기업부", "기술성장기업부"}
EXCLUDE_BOARDS = {"투자주의환기종목(소속부없음)", "관리종목(소속부없음)",
                  "SPAC(소속부없음)", "외국기업(소속부없음)"}

# ---- 컷오프 파라미터 (KOSDAQ 분포 상대 + 실행가능 절대 하한) ----
MCAP_PCTL = 0.20          # 재무가용 풀 내 시총 하위 20% 컷 (초소형 배제)
ADTV_PCTL = 0.20          # 〃 거래대금 하위 20% 컷 (저유동 배제)
ADTV_ABS_FLOOR = 3e8      # 절대 하한 3억원/일 (진우 소액 실행가능 + 동전주 가드)
MIN_YEARS_FOR_YOY = 2     # 성장 YoY 최소 연수
EFFECTIVE_N_GATE = 40     # 유효 N 게이트


def _f(x):
    """숫자 파싱 (빈값·오류 → None)."""
    if x is None:
        return None
    s = str(x).strip()
    if s == "" or s.lower() in ("nan", "none", "null"):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def load_csv(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def pctl(sorted_vals, p):
    if not sorted_vals:
        return None
    i = min(len(sorted_vals) - 1, max(0, int(p * len(sorted_vals))))
    return sorted_vals[i]


def safe_div(a, b):
    if a is None or b is None or b == 0:
        return None
    return a / b


def yoy(cur, prev):
    """전년대비. 분모 ≤0 이면 부호왜곡 → None (이익계열). 매출/자산 등 양수계열용."""
    if cur is None or prev is None or prev <= 0:
        return None
    return cur / prev - 1.0


def compute_annual_features(rows_by_year):
    """code의 연도→raw dict 들에서 연도별 파생지표 + 성장 패널 계산."""
    years = sorted(rows_by_year.keys())
    annual = {}
    for y in years:
        r = rows_by_year[y]
        rev, cogs = r.get("revenue"), r.get("cogs")
        op, ni, cfo = r.get("op_income"), r.get("net_income"), r.get("cfo")
        assets, liab, eq = r.get("assets"), r.get("liabilities"), r.get("equity")
        ca, cl = r.get("current_assets"), r.get("current_liab")
        feat = {
            "revenue": rev, "op_income": op, "net_income": ni, "cfo": cfo,
            "assets": assets, "equity": eq,
            "roa": safe_div(ni, assets),
            "op_margin": safe_div(op, rev),
            "gross_margin": safe_div((rev - cogs) if (rev is not None and cogs is not None) else None, rev),
            "accrual_sloan": safe_div((ni - cfo) if (ni is not None and cfo is not None) else None, assets),
            "debt_ratio": safe_div(liab, eq),
            "current_ratio": safe_div(ca, cl),
            "ni_positive": (ni is not None and ni > 0),
            "cfo_positive": (cfo is not None and cfo > 0),
        }
        py = y - 1
        if py in rows_by_year:
            pr = rows_by_year[py]
            feat["rev_yoy"] = yoy(rev, pr.get("revenue"))
            feat["cfo_yoy"] = yoy(cfo, pr.get("cfo"))
            # 이익계열 YoY: 분모 양수일 때만 (적자→흑자 등은 플래그로)
            feat["op_yoy"] = yoy(op, pr.get("op_income"))
            feat["ni_yoy"] = yoy(ni, pr.get("net_income"))
            feat["turn_to_profit"] = (pr.get("net_income") is not None and ni is not None
                                      and pr.get("net_income") <= 0 < ni)
        annual[y] = feat
    return years, annual


def snapshot(years, annual):
    """최신 연도 스냅샷 + 다년 성장 안정성 (성장 1차축 = 매출·CFO robust)."""
    if not years:
        return {}
    ly = years[-1]
    snap = dict(annual[ly])
    snap["latest_fy"] = ly
    rev_yoys = [annual[y]["rev_yoy"] for y in years if annual[y].get("rev_yoy") is not None]
    if rev_yoys:
        snap["rev_yoy_mean"] = statistics.fmean(rev_yoys)
        snap["rev_yoy_std"] = statistics.pstdev(rev_yoys) if len(rev_yoys) > 1 else 0.0
        snap["rev_yoy_n"] = len(rev_yoys)
    # 매출 CAGR (첫↔마지막 양수 관측)
    rev_series = [(y, annual[y]["revenue"]) for y in years if annual[y].get("revenue") and annual[y]["revenue"] > 0]
    if len(rev_series) >= 2:
        (y0, v0), (y1, v1) = rev_series[0], rev_series[-1]
        n = y1 - y0
        snap["rev_cagr"] = (v1 / v0) ** (1.0 / n) - 1.0 if n > 0 else None
    return snap


def build(liq_rows, fund_rows, ind_rows):
    # 산업 매핑
    ind_map = {r["code"]: r["sector"] for r in ind_rows}
    # liquidity 매핑 (+숫자 파싱)
    liq_map = {}
    for r in liq_rows:
        liq_map[r["code"]] = {"name": r.get("name"), "board": r.get("sector"),
                              "mcap": _f(r.get("mcap")), "adtv": _f(r.get("adtv"))}
    # fundamentals → code별 연도 패널
    panel = defaultdict(dict)
    numcols = ["revenue", "cogs", "op_income", "net_income", "assets", "liabilities",
               "equity", "current_assets", "current_liab", "cash", "cfo",
               "noncurrent_liab", "issued_capital"]
    for r in fund_rows:
        code = r["code"]
        try:
            y = int(float(r["fiscal_year"]))
        except (ValueError, KeyError, TypeError):
            continue
        rec = {c: _f(r.get(c)) for c in numcols}
        panel[code][y] = rec

    firms = {}
    for code, rows_by_year in panel.items():
        if code not in liq_map:
            continue  # 재무는 있는데 유동성 메타 없음 → 제외
        liq = liq_map[code]
        years, annual = compute_annual_features(rows_by_year)
        snap = snapshot(years, annual)
        reasons = []
        board = liq["board"]
        if board not in NORMAL_BOARDS:
            reasons.append("board_excluded")
        if len(years) < MIN_YEARS_FOR_YOY:
            reasons.append("insufficient_years")
        firms[code] = {
            "name": liq["name"] or ind_map.get(code), "board": board,
            "industry": ind_map.get(code), "mcap": liq["mcap"], "adtv": liq["adtv"],
            "years": years, "latest_fy": years[-1] if years else None,
            "annual": {str(y): annual[y] for y in years}, "snapshot": snap,
            "hard_reasons": reasons,  # board/years 외 컷은 아래 분위에서 추가
        }

    # 컷오프 캘리브레이션: 재무가용 + 정상시장부 + 충분연수 풀의 분포 기준 (KOSDAQ-relative)
    base = [c for c, v in firms.items()
            if "board_excluded" not in v["hard_reasons"]
            and "insufficient_years" not in v["hard_reasons"]
            and v["mcap"] is not None and v["adtv"] is not None]
    mcaps = sorted(firms[c]["mcap"] for c in base)
    adtvs = sorted(firms[c]["adtv"] for c in base)
    mcap_cut = pctl(mcaps, MCAP_PCTL)
    adtv_cut_rel = pctl(adtvs, ADTV_PCTL)
    adtv_cut = max(adtv_cut_rel or 0.0, ADTV_ABS_FLOOR)

    universe = []
    for c in base:
        v = firms[c]
        if v["mcap"] < mcap_cut:
            v["hard_reasons"].append("mcap_below_cut")
        if v["adtv"] < adtv_cut:
            v["hard_reasons"].append("adtv_below_cut")
        v["in_universe"] = (len(v["hard_reasons"]) == 0)
        if v["in_universe"]:
            universe.append(c)
    # base 밖 firm은 in_universe=False 마킹
    for c, v in firms.items():
        v.setdefault("in_universe", False)

    cutoffs = {
        "normal_boards": sorted(NORMAL_BOARDS),
        "mcap_pctl": MCAP_PCTL, "mcap_cut_won": mcap_cut,
        "adtv_pctl": ADTV_PCTL, "adtv_cut_won": adtv_cut, "adtv_abs_floor": ADTV_ABS_FLOOR,
        "min_years_for_yoy": MIN_YEARS_FOR_YOY,
        "base_pool_n": len(base),
    }
    return firms, sorted(universe), cutoffs


def write_outputs(firms, universe, cutoffs, json_path, csv_path):
    cache = {
        "meta": {
            "module": "v4.1 kosdaq_sel · Stage 1",
            "note": "성장+회계적합 적재만(점수화 X). 가드레일=현시점 운용 universe. 백테스트는 firms.annual로 PIT(공시지연) 별도.",
            "effective_n": len(universe),
        },
        "cutoffs": cutoffs,
        "universe_latest": universe,
        "firms": firms,
    }
    with open(json_path, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, indent=1)

    cols = ["code", "name", "board", "industry", "mcap_억", "adtv_억",
            "latest_fy", "rev_yoy", "rev_cagr", "cfo_yoy", "roa", "op_margin",
            "accrual_sloan", "debt_ratio", "ni_positive", "cfo_positive"]
    with open(csv_path, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(cols)
        for c in universe:
            v = firms[c]; s = v["snapshot"]
            def r2(x): return round(x, 4) if isinstance(x, float) else x
            w.writerow([c, v["name"], v["board"], v["industry"],
                        round(v["mcap"] / 1e8, 1) if v["mcap"] else None,
                        round(v["adtv"] / 1e8, 2) if v["adtv"] else None,
                        s.get("latest_fy"), r2(s.get("rev_yoy")), r2(s.get("rev_cagr")),
                        r2(s.get("cfo_yoy")), r2(s.get("roa")), r2(s.get("op_margin")),
                        r2(s.get("accrual_sloan")), r2(s.get("debt_ratio")),
                        s.get("ni_positive"), s.get("cfo_positive")])


# ----------------------- SELF TEST -----------------------
def self_test():
    ok = 0; tot = 0
    def chk(name, cond):
        nonlocal ok, tot; tot += 1
        print(f"  [{'OK' if cond else 'FAIL'}] {name}"); ok += 1 if cond else 0

    # 합성: 6종목, 4부 중 일부 + 배제부 + 초소형/저유동
    liq = [
        {"code": "A", "name": "정상대형", "sector": "우량기업부", "mcap": "1.0e12", "adtv": "5.0e9"},
        {"code": "B", "name": "정상중형", "sector": "중견기업부", "mcap": "3.0e11", "adtv": "1.0e9"},
        {"code": "C", "name": "벤처성장", "sector": "벤처기업부", "mcap": "2.0e11", "adtv": "8.0e8"},
        {"code": "D", "name": "관리종목", "sector": "관리종목(소속부없음)", "mcap": "5.0e11", "adtv": "2.0e9"},
        {"code": "E", "name": "초소형저유동", "sector": "기술성장기업부", "mcap": "1.0e9", "adtv": "1.0e7"},
        {"code": "F", "name": "연수부족", "sector": "우량기업부", "mcap": "4.0e11", "adtv": "3.0e9"},
    ]
    ind = [{"code": c, "name": n, "sector": s} for c, n, s in
           [("A", "정상대형", "반도체"), ("B", "정상중형", "소프트웨어"), ("C", "벤처성장", "바이오"),
            ("D", "관리종목", "기타"), ("E", "초소형저유동", "기타"), ("F", "연수부족", "장비")]]
    fund = []
    def add(code, y, rev, op, ni, cfo, assets=1e12, eq=5e11, liab=5e11, cogs=None, ca=3e11, cl=1e11):
        fund.append({"code": code, "fiscal_year": str(y), "revenue": rev, "cogs": cogs if cogs is not None else rev*0.7,
                     "op_income": op, "net_income": ni, "assets": assets, "liabilities": liab, "equity": eq,
                     "current_assets": ca, "current_liab": cl, "cash": 1e10, "cfo": cfo,
                     "noncurrent_liab": 2e11, "issued_capital": 1e10})
    for code in ["A", "B", "C", "D", "E"]:
        add(code, 2023, 1.0e11, 1.0e10, 1.0e10, 1.2e10)
        add(code, 2024, 1.3e11, 1.4e10, 1.3e10, 1.5e10)   # 매출 +30%
    add("F", 2024, 1.0e11, 1e10, 1e10, 1e10)              # 1년만 → YoY 불가

    firms, universe, cutoffs = build(liq, fund, ind)
    chk("배제부(D 관리종목) universe 제외", "D" not in universe)
    chk("초소형·저유동(E) universe 제외", "E" not in universe)
    chk("연수부족(F) universe 제외", "F" not in universe)
    chk("정상 A·B·C universe 포함", all(c in universe for c in ["A", "B", "C"]))
    chk("A rev_yoy ≈ +0.30", abs(firms["A"]["snapshot"]["rev_yoy"] - 0.30) < 1e-6)
    chk("A roa = ni/assets = 0.013", abs(firms["A"]["snapshot"]["roa"] - (1.3e10/1e12)) < 1e-9)
    chk("accrual_sloan = (ni-cfo)/assets <0 (cfo>ni)", firms["A"]["snapshot"]["accrual_sloan"] < 0)
    chk("산업 매핑(C=바이오)", firms["C"]["industry"] == "바이오")
    chk("이익 YoY 분모 양수일 때 계산", firms["A"]["snapshot"]["op_yoy"] is not None)
    chk("cutoffs adtv 절대하한 적용", cutoffs["adtv_cut_won"] >= ADTV_ABS_FLOOR)
    print(f"\nself-test: {ok}/{tot} pass")
    return ok == tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--liq", default="liquidity_kosdaq.csv")
    ap.add_argument("--fund", default="fundamentals_kosdaq.csv")
    ap.add_argument("--ind", default="kosdaq_industry.csv")
    ap.add_argument("--out-json", default="kosdaq_sel_universe_cache.json")
    ap.add_argument("--out-csv", default="kosdaq_sel_universe_latest.csv")
    args = ap.parse_args()

    if args.self_test:
        sys.exit(0 if self_test() else 1)

    liq = load_csv(args.liq); fund = load_csv(args.fund); ind = load_csv(args.ind)
    firms, universe, cutoffs = build(liq, fund, ind)
    write_outputs(firms, universe, cutoffs, args.out_json, args.out_csv)

    n = len(universe)
    print("=== KOSDAQ 선정 universe (Stage 1) ===")
    print(f"재무가용 firms: {len(firms)} | base 풀(정상부∩충분연수∩메타): {cutoffs['base_pool_n']}")
    print(f"컷오프: 시총 ≥ {cutoffs['mcap_cut_won']/1e8:.0f}억(p{int(cutoffs['mcap_pctl']*100)}) "
          f"· ADTV ≥ {cutoffs['adtv_cut_won']/1e8:.1f}억(max[p{int(cutoffs['adtv_pctl']*100)}, 3억])")
    print(f"유효 universe N = {n}  (게이트 ≥{EFFECTIVE_N_GATE}: {'PASS' if n>=EFFECTIVE_N_GATE else 'FAIL'})")
    # 성장 상위 미리보기 (점수 아님 — sanity)
    prev = [(c, firms[c]['snapshot'].get('rev_yoy')) for c in universe
            if firms[c]['snapshot'].get('rev_yoy') is not None]
    prev.sort(key=lambda t: t[1], reverse=True)
    print("매출 YoY 상위 5 (sanity, 점수 아님):",
          [(firms[c]['name'], round(g*100, 1)) for c, g in prev[:5]])
    print(f"출력: {args.out_json} , {args.out_csv}")
    if n < EFFECTIVE_N_GATE:
        print("⚠️ 유효 N 게이트 미달 → Stage 0 결정메모 §6-4대로 중단 검토")
        sys.exit(2)


if __name__ == "__main__":
    main()
