# -*- coding: utf-8 -*-
"""스타일 패널 생성기 (DART 재무 + KRX 가격·시총) — 사양서 v2 §1·§3 구현
pykrx 사망으로 끊긴 종목재무_KRX_*.csv 를 대체한다. 형 PC에서 실행(샌드박스는 DART 차단).

  py 스타일패널_DART.py --self-test      # 네트워크 없이 계산 로직 검증
  py 스타일패널_DART.py --universe       # 이번 달 유니버스만 확인 (DART 호출 없음)
  py 스타일패널_DART.py                  # 이번 달 패널 1행씩 생성 → 스타일패널_DART.csv
출력 스키마: ym,code,name,mcap,ep,bp,roe,div,src_rcept  (v1 mini_style_panel과 호환 가능)
"""
import argparse, csv, os, sys, time, json
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT = os.path.join(HERE, "스타일패널_DART.csv")
RAW = os.path.join(HERE, "_스타일패널_raw캐시.json")   # 응답 캐시 (재계산 시 재수집 불필요)
COLS = ["ym", "code", "name", "mcap", "ep", "bp", "roe", "div", "src_rcept"]

TOPN = 300            # 사양서 §2: 시총 상위 300
ADTV_MIN = 2e9        # 20억
SLEEP = 0.35

# ── DART 계정 인식 (fetch_dart_eps 교훈: 이름 아닌 IFRS account_id 우선) ─────
ID_EQUITY_PARENT = "ifrs-full_equityattributabletoownersofparent"
ID_EQUITY_TOTAL = "ifrs-full_equity"
ID_NI_PARENT = "ifrs-full_profitlossattributabletoownersofparent"
ID_NI_TOTAL = "ifrs-full_profitloss"
ID_DIV_PAID = "ifrs-full_dividendspaidclassifiedasfinancingactivities"
NM_DIV = ("배당금지급", "배당금의지급", "배당금지급액", "현금배당")


def _num(v):
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", "").strip())
    except ValueError:
        return None


def pick_by_id(rows, wanted_ids, sj=None, name_keys=None):
    """account_id 우선, 없으면 계정명 폴백. (값, rcept_no)"""
    best = None
    for r in rows:
        if sj and r.get("sj_div") not in sj:
            continue
        aid = str(r.get("account_id", "")).strip().lower()
        nm = str(r.get("account_nm", "")).replace(" ", "")
        hit = aid in wanted_ids
        if not hit and name_keys:
            hit = any(k in nm for k in name_keys)
        if not hit:
            continue
        v = _num(r.get("thstrm_amount"))
        if v is None:
            v = _num(r.get("thstrm_add_amount"))
        if v is None:
            continue
        pri = 0 if aid in wanted_ids else 1
        if best is None or pri < best[0]:
            best = (pri, v, r.get("rcept_no"))
    return (best[1], best[2]) if best else (None, None)


def equity_of(rows):
    v, rc = pick_by_id(rows, {ID_EQUITY_PARENT}, sj=("BS",), name_keys=None)
    if v is None:
        v, rc = pick_by_id(rows, {ID_EQUITY_TOTAL}, sj=("BS",), name_keys=("자본총계",))
    return v, rc


def ni_of(rows):
    v, rc = pick_by_id(rows, {ID_NI_PARENT}, sj=("IS", "CIS"))
    if v is None:
        v, rc = pick_by_id(rows, {ID_NI_TOTAL}, sj=("IS", "CIS"),
                           name_keys=("당기순이익", "당기순손실"))
    return v, rc


def div_paid_of(rows):
    v, rc = pick_by_id(rows, {ID_DIV_PAID}, sj=("CF",), name_keys=NM_DIV)
    return (abs(v) if v is not None else None), rc


REPORTS = [("11013", 3), ("11012", 6), ("11014", 9), ("11011", 12)]   # (보고서코드, 누적개월)


def ttm_from(cur_cum, cur_months, prev_fy, prev_cum_same):
    """TTM = 당해 누적 + 전년 연간 − 전년 동기 누적. 하나라도 없으면 None.
    (사양서 v2 §3: 순이익·배당 모두 최근 4분기 기준)"""
    if cur_months == 12:
        return cur_cum if cur_cum is not None else None
    if None in (cur_cum, prev_fy, prev_cum_same):
        return None
    return cur_cum + prev_fy - prev_cum_same


def has_cf(rows):
    """현금흐름표가 응답에 있는가 — 배당 '0'과 '결측'을 가르는 기준"""
    return any(r.get("sj_div") == "CF" for r in rows)


def factors(mcap, equity, ni, div_paid):
    """사양서 v2 §3. 계산 불가·비정상은 None (임의 대체 금지)"""
    f = {"ep": None, "bp": None, "roe": None, "div": None}
    if not mcap or mcap <= 0:
        return f
    if ni is not None:
        f["ep"] = ni / mcap
    if equity is not None and equity > 0:
        f["bp"] = equity / mcap
        if ni is not None:
            f["roe"] = ni / equity
    if div_paid is not None:
        # 배당은 음수 불가. TTM 뺄셈에서 지급 시점 어긋남으로 음수가 나오면 0 (2026-08-22 실측)
        f["div"] = max(0.0, div_paid) / mcap
    return f


def load_universe_from_snapshot(ym=None):
    """종목스냅숏_일별.csv(KRX 수집기 산출) → 해당 월 마지막 날 KOSPI 시총 상위 TOPN"""
    p = os.path.join(HERE, "종목스냅숏_일별.csv")
    if not os.path.exists(p):
        sys.exit("[중단] 종목스냅숏_일별.csv 없음 — 먼저 py 진우퀀트_KRX수집.py 실행")
    rows = []
    with open(p, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r["market"] != "KOSPI":
                continue
            if ym and not r["date"].startswith(ym):
                continue
            rows.append(r)
    if not rows:
        sys.exit(f"[중단] 스냅숏에 {ym or '해당'} 월 KOSPI 데이터 없음")
    last = max(r["date"] for r in rows)
    day = [r for r in rows if r["date"] == last]
    for r in day:
        r["_mc"] = int(r["mcap"] or 0)
    # 우선주·종류주 배제: 한국 보통주 코드는 끝자리 '0' (예: 삼성전자 005930).
    # 이름 기준(~우)은 '현대차2우B'·'한화3우B' 같은 종류주를 놓친다 (2026-08-22 실측 사고).
    day = [r for r in day if r["_mc"] > 0 and str(r["code"])[-1] == "0"]
    day.sort(key=lambda r: -r["_mc"])
    return last, day[:TOPN]


def self_test():
    rows = [
        {"sj_div": "BS", "account_id": "ifrs-full_EquityAttributableToOwnersOfParent",
         "account_nm": "지배기업 소유주지분", "thstrm_amount": "1,000,000", "rcept_no": "20260814000001"},
        {"sj_div": "BS", "account_id": "ifrs-full_Equity", "account_nm": "자본총계",
         "thstrm_amount": "1,200,000", "rcept_no": "20260814000001"},
        {"sj_div": "CIS", "account_id": "ifrs-full_ProfitLossAttributableToOwnersOfParent",
         "account_nm": "당기순손실", "thstrm_amount": "-50,000", "rcept_no": "20260814000001"},
        {"sj_div": "CF", "account_id": "ifrs-full_DividendsPaidClassifiedAsFinancingActivities",
         "account_nm": "배당금지급", "thstrm_amount": "-30,000", "rcept_no": "20260814000001"},
    ]
    eq, _ = equity_of(rows); assert eq == 1000000, eq            # 지배주주 우선
    ni, _ = ni_of(rows); assert ni == -50000, ni                 # 적자도 인식
    dv, _ = div_paid_of(rows); assert dv == 30000, dv            # 절대값
    f = factors(2000000, eq, ni, dv)
    assert abs(f["ep"] + 0.025) < 1e-9 and abs(f["bp"] - 0.5) < 1e-9
    assert abs(f["roe"] + 0.05) < 1e-9 and abs(f["div"] - 0.015) < 1e-9
    # 자본잠식 → bp·roe 결측
    assert factors(1000, 500, 10, -30)["div"] == 0.0
    f2 = factors(2000000, -100, -50000, None)
    assert f2["bp"] is None and f2["roe"] is None and f2["ep"] is not None
    # 시총 0 → 전부 결측
    assert all(v is None for v in factors(0, 1, 1, 1).values())
    # 무배당 = 0 (CF는 있는데 배당 항목 없음) vs 진짜 결측
    cf_only = [{"sj_div": "CF", "account_id": "x", "account_nm": "영업활동현금흐름", "thstrm_amount": "100"}]
    assert has_cf(cf_only) and div_paid_of(cf_only)[0] is None      # -> 호출부에서 0 처리
    assert not has_cf([{"sj_div": "BS", "account_nm": "자산총계", "thstrm_amount": "1"}])
    # TTM 조립
    assert ttm_from(60, 6, 100, 40) == 120
    assert ttm_from(100, 12, None, None) == 100
    assert ttm_from(60, 6, None, 40) is None
    # 종류주 필터 (코드 끝자리)
    for cd, want in (("005930", True), ("005935", False), ("005387", False), ("00088K", False)):
        assert (str(cd)[-1] == "0") == want, cd
    # 계정명 폴백 (account_id 비표준)
    rows2 = [{"sj_div": "BS", "account_id": "x", "account_nm": "자본총계", "thstrm_amount": "500"}]
    assert equity_of(rows2)[0] == 500
    print("self-test 13/13 통과")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ym", default=None, help="YYYY-MM (기본: 스냅숏 최신월)")
    ap.add_argument("--universe", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--limit", type=int, default=0, help="시험용 상위 N종만")
    a = ap.parse_args()
    if a.self_test:
        return self_test()

    asof, uni = load_universe_from_snapshot(a.ym)
    ym = asof[:7]
    print(f"[유니버스] {asof} 기준 KOSPI 시총 상위 {len(uni)}종 (우선주 제외)")
    print("  상위5:", [(r["name"], f'{r["_mc"]/1e12:.0f}조') for r in uni[:5]])
    if a.universe:
        return

    from fetch_dart_eps import load_api_key, load_corp_codes, DART_URL
    import requests
    key = load_api_key()
    names = {r["name"]: r["code"] for r in uni}
    print(f"[corp_code] 매핑 중... ({len(names)}종)")
    try:
        cc = load_corp_codes(key, names)
    except SystemExit as e:                      # 일부 미해결이어도 진행 (해당 종목만 결측)
        print(f"  [주의] {e} → 미해결 종목은 결측 처리하고 계속")
        cc = {}
    if not cc:
        cc = {}
        for nm, cd in names.items():
            try:
                cc.update(load_corp_codes(key, {nm: cd}))
            except Exception:
                pass

    if a.limit:
        uni = uni[:a.limit]
    year = int(ym[:4])
    raw_cache = {}
    if os.path.exists(RAW):
        try:
            raw_cache = json.load(open(RAW, encoding="utf-8"))
            print(f"[캐시] {len(raw_cache)}건 재사용 (재수집 생략)")
        except Exception:
            raw_cache = {}
    out, miss = [], 0
    for i, r in enumerate(uni, 1):
        corp = cc.get(r["name"])
        if not corp:
            miss += 1
            continue
        def pull(y, rep):
            k = f"{corp}|{y}|{rep}"
            if k in raw_cache:
                return raw_cache[k]
            try:
                resp = requests.get(DART_URL, params={
                    "crtfc_key": key, "corp_code": corp, "bsns_year": str(y),
                    "reprt_code": rep, "fs_div": "CFS"}, timeout=30).json()
            except Exception:
                time.sleep(SLEEP); return None
            time.sleep(SLEEP)
            got = resp["list"] if resp.get("status") == "000" and resp.get("list") else None
            raw_cache[k] = got
            return got

        # (1) 당해 최신 누적 보고서 (3Q -> 반기 -> 1Q)
        cur, cur_m = None, None
        for rep, months in (("11014", 9), ("11012", 6), ("11013", 3)):
            cur = pull(year, rep)
            if cur:
                cur_m = months; break
        if not cur:
            cur = pull(year - 1, "11011"); cur_m = 12
        if not cur:
            miss += 1; continue
        eq, rc = equity_of(cur)              # 자본은 잔액 -> 최신본 그대로
        ni_c, _ = ni_of(cur)
        dv_c, _ = div_paid_of(cur)

        # (2) TTM 보정: 전년 연간 + 전년 동기 누적
        ni = ni_c
        dv = dv_c if dv_c is not None else (0.0 if has_cf(cur) else None)
        if cur_m != 12:
            rep_same = {3: "11013", 6: "11012", 9: "11014"}[cur_m]
            pfy = pull(year - 1, "11011")
            psame = pull(year - 1, rep_same)
            if pfy and psame:
                ni = ttm_from(ni_c, cur_m, ni_of(pfy)[0], ni_of(psame)[0])
                # 무배당 기업: CF는 있는데 배당 항목이 없음 -> 결측이 아니라 0
                d_cur = dv_c if dv_c is not None else (0.0 if has_cf(cur) else None)
                d_fy = div_paid_of(pfy)[0]
                d_fy = d_fy if d_fy is not None else (0.0 if has_cf(pfy) else None)
                d_sm = div_paid_of(psame)[0]
                d_sm = d_sm if d_sm is not None else (0.0 if has_cf(psame) else None)
                dv = ttm_from(d_cur, cur_m, d_fy, d_sm)
            else:
                ni = dv = None               # TTM 불가 -> 결측 (임의 대체 금지)
        f = factors(r["_mc"], eq, ni, dv)
        out.append({"ym": ym, "code": r["code"], "name": r["name"], "mcap": r["_mc"],
                    **{k: (round(v, 6) if v is not None else "") for k, v in f.items()},
                    "src_rcept": rc or ""})
        if i % 50 == 0:
            print(f"  {i}/{len(uni)} 처리 (결측 {miss})", flush=True)

    try:
        json.dump(raw_cache, open(RAW, "w", encoding="utf-8"))
        print(f"[캐시] {len(raw_cache)}건 저장")
    except Exception as e:
        print("  캐시 저장 실패:", e)

    new = not os.path.exists(OUT)
    have = set()
    if not new:
        with open(OUT, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                have.add((r["ym"], r["code"]))
    todo = [r for r in out if (r["ym"], r["code"]) not in have]
    with open(OUT, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        if new:
            w.writeheader()
        for r in todo:
            w.writerow(r)
    ok = sum(1 for r in out if r["bp"] != "" and r["ep"] != "")
    print(f"\n완료 — {ym}: 수집 {len(out)}종(팩터완비 {ok}) · 신규기록 {len(todo)} · 결측 {miss}")
    print(f"저장: {os.path.basename(OUT)}")


if __name__ == "__main__":
    main()
