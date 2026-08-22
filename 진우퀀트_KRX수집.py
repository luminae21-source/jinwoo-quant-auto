# -*- coding: utf-8 -*-
"""진우퀀트 KRX Open API 수집기 v2 (2026-08-22)
pykrx(익명 조회) 사망 이후의 공식 수집 경로. 형 Windows에서 실행 (샌드박스는 krx.co.kr 차단).

인증: 폴더의 .krx_key 1줄. 헤더 AUTH_KEY. 한도 10,000회/일.
전제: openapi.krx.co.kr 에서 해당 API '활용신청' 승인 완료.

  py 진우퀀트_KRX수집.py --probe          # ① 첫 실행: 필드명만 확인 (기록 안 함)
  py 진우퀀트_KRX수집.py                  # ② 오늘분 수집 → 정본 CSV에 추가
  py 진우퀀트_KRX수집.py --date 20260821
  py 진우퀀트_KRX수집.py --from 20260801 --to 20260822   # 구간 보충
  py 진우퀀트_KRX수집.py --index          # 지수만 (kospi_index_daily.csv 갱신)
  py 진우퀀트_KRX수집.py --self-test      # 네트워크 없이 파서 검증
"""
import argparse, csv, datetime, json, os, sys, time, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "http://data-dbg.krx.co.kr/svc/apis"
SLEEP = 0.4          # 호출 간격 (한도 보호)

# 경로가 승인 화면과 다르면 여기만 고친다 (서비스 목록 > 명세서에 URL 표기)
EP_STOCK = {"KOSPI": "/sto/stk_bydd_trd", "KOSDAQ": "/sto/ksq_bydd_trd"}
EP_INDEX = "/idx/kospi_dd_trd"

# KRX 필드명 → 우리 스키마 (앞의 이름부터 우선 채택)
F_STOCK = {
    "code":   ["ISU_SRT_CD", "ISU_CD"],
    "open":   ["TDD_OPNPRC", "OPNPRC"],
    "high":   ["TDD_HGPRC", "HGPRC"],
    "low":    ["TDD_LWPRC", "LWPRC"],
    "close":  ["TDD_CLSPRC", "CLSPRC"],
    "volume": ["ACC_TRDVOL", "TRDVOL"],
}
F_INDEX = {"name": ["IDX_NM", "IDX_IND_NM"], "close": ["CLSPRC_IDX", "CLSPRC", "TDD_CLSPRC"]}
INDEX_PICK = "코스피"          # 정확히 이 이름인 행을 고른다 ("코스피 (외국주포함)"·"코스피 200" 배제)
# 실측(2026-08-21): 지수 51행 중 변형·빈값 다수 → 정확일치 우선, 없으면 값 있는 첫 행

# 시총 스냅숏 (매일 찍으면 생존편향 없는 PIT 유니버스가 쌓인다 — 엔진05 교훈)
F_SNAP = {"code": ["ISU_SRT_CD", "ISU_CD"], "name": ["ISU_NM"], "mcap": ["MKTCAP"],
          "shares": ["LIST_SHRS"], "sect": ["SECT_TP_NM"]}


def key():
    p = os.path.join(HERE, ".krx_key")
    if not os.path.exists(p):
        sys.exit("[중단] .krx_key 없음 — 마이페이지 인증키를 1줄로 저장할 것")
    return open(p, encoding="utf-8").read().strip()


def call(path, bas_dd, auth):
    url = f"{BASE}{path}?{urllib.parse.urlencode({'basDd': bas_dd})}"
    req = urllib.request.Request(url, headers={"AUTH_KEY": auth})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode("utf-8"))


def pick(row, names):
    for n in names:
        if n in row and row[n] not in ("", None):
            return row[n]
    return None


def num(v):
    if v is None:
        return None
    v = str(v).replace(",", "").strip()
    try:
        return int(float(v))
    except ValueError:
        return None


def fnum(v):
    if v is None:
        return None
    v = str(v).replace(",", "").strip()
    try:
        return float(v)
    except ValueError:
        return None


def parse_stock(payload, bas_dd):
    """OutBlock_1 → [{date,code,open,high,low,close,volume}], 건너뛴 수"""
    rows = payload.get("OutBlock_1") or []
    d = f"{bas_dd[:4]}-{bas_dd[4:6]}-{bas_dd[6:]}"
    out, skipped = [], 0
    for r in rows:
        code = pick(r, F_STOCK["code"])
        close = num(pick(r, F_STOCK["close"]))
        if not code or close is None:
            skipped += 1
            continue
        rec = {"date": d, "code": str(code).zfill(6), "close": close}
        for k in ("open", "high", "low", "volume"):
            v = num(pick(r, F_STOCK[k]))
            rec[k] = v if v is not None else 0
        out.append({k: rec[k] for k in ("date", "code", "open", "high", "low", "close", "volume")})
    return out, skipped


def parse_index(payload, bas_dd):
    """지수 응답 → (YYYY-MM-DD, 종가) 또는 (None, None)"""
    rows = payload.get("OutBlock_1") or []
    d = f"{bas_dd[:4]}-{bas_dd[4:6]}-{bas_dd[6:]}"
    cand = None
    for r in rows:
        nm = str(pick(r, F_INDEX["name"]) or "").strip()
        c = fnum(pick(r, F_INDEX["close"]))
        if c is None or c == 0:          # 빈값·0 행 배제
            continue
        if nm == INDEX_PICK:             # 정확일치가 정답
            return d, c
        if cand is None:
            cand = (d, c)
    return cand if cand else (None, None)


def parse_snapshot(payload, bas_dd, market):
    """일별 시총·종목명·소속부 스냅숏 → 생존편향 없는 PIT 유니버스 재료"""
    rows = payload.get("OutBlock_1") or []
    d = f"{bas_dd[:4]}-{bas_dd[4:6]}-{bas_dd[6:]}"
    out = []
    for r in rows:
        code = pick(r, F_SNAP["code"])
        mc = num(pick(r, F_SNAP["mcap"]))
        if not code:
            continue
        out.append({"date": d, "code": str(code).zfill(6), "market": market,
                    "name": str(pick(r, F_SNAP["name"]) or "").strip(),
                    "mcap": mc if mc is not None else 0,
                    "shares": num(pick(r, F_SNAP["shares"])) or 0,
                    "sect": str(pick(r, F_SNAP["sect"]) or "").strip()})
    return out


def append_snapshot(recs):
    """종목스냅숏_일별.csv 에 누적 (없으면 헤더와 함께 생성)"""
    path = os.path.join(HERE, "종목스냅숏_일별.csv")
    cols = ["date", "code", "market", "name", "mcap", "shares", "sect"]
    new = not os.path.exists(path)
    have = set()
    if not new:
        with open(path, encoding="utf-8-sig") as f:
            for line in f:
                p = line.split(",")
                if len(p) > 2 and len(p[0]) == 10:
                    have.add((p[0], p[2].strip()))
    todo = [r for r in recs if (r["date"], r["market"]) not in have]
    if not todo:
        return 0
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=cols)
        if new:
            w.writeheader()
        for r in todo:
            w.writerow(r)
    return len(todo)


def existing_dates(path, col=0):
    """이미 있는 날짜 집합 (중복 방지). 파일 없으면 빈 집합."""
    s = set()
    if not os.path.exists(path):
        return s
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            p = line.split(",", 1)[0].strip()
            if len(p) == 10 and p[4] == "-":
                s.add(p)
    return s


def append_stock(market, recs):
    path = os.path.join(HERE, f"종목일봉_30년_{market}.csv")
    if not os.path.exists(path):
        print(f"  [건너뜀] {os.path.basename(path)} 없음 — 정본 옆에서 실행할 것")
        return 0
    have = existing_dates(path)
    todo = [r for r in recs if r["date"] not in have]
    if not todo:
        print(f"  {market}: 이미 있는 날짜 — 추가 0건")
        return 0
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date", "code", "open", "high", "low", "close", "volume"])
        for r in todo:
            w.writerow(r)
    print(f"  {market}: +{len(todo)}건 추가")
    return len(todo)


def append_index(d, close):
    path = os.path.join(HERE, "kospi_index_daily.csv")
    if not os.path.exists(path):
        print("  [건너뜀] kospi_index_daily.csv 없음")
        return 0
    if d in existing_dates(path):
        print(f"  지수: {d} 이미 있음")
        return 0
    with open(path, "a", encoding="utf-8", newline="") as f:
        f.write(f"{d},{close}\n")
    print(f"  지수: {d} {close} 추가")
    return 1


def daterange(a, b):
    d0 = datetime.datetime.strptime(a, "%Y%m%d").date()
    d1 = datetime.datetime.strptime(b, "%Y%m%d").date()
    while d0 <= d1:
        if d0.weekday() < 5:          # 주말 제외 (휴장일은 응답 0행으로 스스로 걸러짐)
            yield d0.strftime("%Y%m%d")
        d0 += datetime.timedelta(days=1)


def self_test():
    mock = {"OutBlock_1": [
        {"ISU_SRT_CD": "005930", "TDD_OPNPRC": "70,000", "TDD_HGPRC": "71000",
         "TDD_LWPRC": "69500", "TDD_CLSPRC": "70,500", "ACC_TRDVOL": "12345678"},
        {"ISU_SRT_CD": "000660", "TDD_CLSPRC": ""},                       # close 없음 → skip
        {"ISU_CD": "035420", "CLSPRC": "200000", "OPNPRC": "0", "HGPRC": "0",
         "LWPRC": "0", "TRDVOL": "0"},                                    # 대체 필드명
    ]}
    recs, sk = parse_stock(mock, "20260820")
    assert len(recs) == 2 and sk == 1, (recs, sk)
    assert recs[0] == {"date": "2026-08-20", "code": "005930", "open": 70000, "high": 71000,
                       "low": 69500, "close": 70500, "volume": 12345678}
    assert recs[1]["code"] == "035420" and recs[1]["close"] == 200000

    idx = {"OutBlock_1": [
        {"IDX_NM": "코스피 (외국주포함)", "CLSPRC_IDX": ""},      # 실측: 빈값 변형
        {"IDX_NM": "코스피 200", "CLSPRC_IDX": "400.11"},
        {"IDX_NM": "코스피", "CLSPRC_IDX": "3,120.45"},           # ← 정확일치가 정답
    ]}
    d, c = parse_index(idx, "20260820")
    assert (d, c) == ("2026-08-20", 3120.45), (d, c)

    snap = parse_snapshot({"OutBlock_1": [
        {"ISU_CD": "095570", "ISU_NM": "AJ네트웍스", "MKTCAP": "203,000,000,000",
         "LIST_SHRS": "46,822,295", "SECT_TP_NM": ""},
    ]}, "20260821", "KOSPI")
    assert snap[0]["code"] == "095570" and snap[0]["mcap"] == 203000000000, snap
    assert snap[0]["name"] == "AJ네트웍스" and snap[0]["market"] == "KOSPI"

    days = list(daterange("20260821", "20260824"))            # 금~월, 주말 제외
    assert days == ["20260821", "20260824"], days
    print("self-test 8/8 통과")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().strftime("%Y%m%d"))
    ap.add_argument("--from", dest="d_from")
    ap.add_argument("--to", dest="d_to")
    ap.add_argument("--index", action="store_true", help="지수만 수집")
    ap.add_argument("--probe", action="store_true", help="원본 필드명만 출력")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()

    auth = key()
    days = list(daterange(a.d_from, a.d_to)) if (a.d_from and a.d_to) else [a.date]
    if len(days) > 1:
        print(f"[구간] {days[0]} ~ {days[-1]} · {len(days)}거래일 후보")

    if a.probe:
        for label, path in [("지수", EP_INDEX)] + list(EP_STOCK.items()):
            try:
                p = call(path, days[0], auth)
            except Exception as e:
                print(f"[{label}] 호출 실패 — {e}")
                continue
            rows = p.get("OutBlock_1") or []
            print(f"[{label}] {len(rows)}행")
            if rows:
                print("   필드:", sorted(rows[0].keys()))
                print("   샘플:", {k: rows[0][k] for k in list(rows[0])[:8]})
            else:
                print("   응답:", str(p)[:200])
        return

    total = 0
    for i, dd in enumerate(days):
        if a.index or not a.index:
            try:
                d, c = parse_index(call(EP_INDEX, dd, auth), dd)
                if d:
                    total += append_index(d, c)
                time.sleep(SLEEP)
            except Exception as e:
                print(f"  지수 {dd}: 실패 — {e}")
        if a.index:
            continue
        for market, path in EP_STOCK.items():
            try:
                payload = call(path, dd, auth)
                recs, sk = parse_stock(payload, dd)
            except Exception as e:
                print(f"  {market} {dd}: 실패 — {e}")
                continue
            if recs:
                print(f"[{market}] {dd}: 파싱 {len(recs)}건 (skip {sk})")
                total += append_stock(market, recs)
                ns = append_snapshot(parse_snapshot(payload, dd, market))
                if ns:
                    print(f"  {market}: 스냅숏 +{ns}건 (시총·종목명·소속부)")
            time.sleep(SLEEP)
    print(f"\n완료 — 총 {total}건 추가")


if __name__ == "__main__":
    main()
