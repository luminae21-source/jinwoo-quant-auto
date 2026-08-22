# -*- coding: utf-8 -*-
"""진우퀀트 KRX Open API 수집기 (2026-08-22)
- 인증: .krx_key 파일 1줄(인증키). 헤더 AUTH_KEY 전달. 한도 10,000회/일.
- 사용 전제: openapi.krx.co.kr 서비스 목록에서 해당 API '활용신청' 승인 완료.
사용법 (PC):
  python 진우퀀트_KRX수집.py --probe            # 오늘 하루치 원본 필드 확인 (첫 실행 권장)
  python 진우퀀트_KRX수집.py                    # 오늘 하루치 → 종목일봉_30년_*.csv 에 추가
  python 진우퀀트_KRX수집.py --date 20260820    # 특정일
  python 진우퀀트_KRX수집.py --self-test        # 네트워크 없이 파서 검증
"""
import argparse, csv, datetime, json, os, sys, urllib.request, urllib.parse

HERE = os.path.dirname(os.path.abspath(__file__))
BASE = "http://data-dbg.krx.co.kr/svc/apis"
# 경로가 승인 화면과 다르면 여기만 고치면 됨 (서비스 목록의 '명세서'에 URL 나옴)
ENDPOINTS = {
    "KOSPI":  "/sto/stk_bydd_trd",   # 유가증권 일별매매정보
    "KOSDAQ": "/sto/ksq_bydd_trd",   # 코스닥 일별매매정보
}
# KRX 표준 필드명 → 우리 스키마(date,code,open,high,low,close,volume)
FIELD_MAP = {
    "code":   ["ISU_SRT_CD", "ISU_CD"],
    "open":   ["TDD_OPNPRC", "OPNPRC"],
    "high":   ["TDD_HGPRC", "HGPRC"],
    "low":    ["TDD_LWPRC", "LWPRC"],
    "close":  ["TDD_CLSPRC", "CLSPRC"],
    "volume": ["ACC_TRDVOL", "TRDVOL"],
}

def key():
    p = os.path.join(HERE, ".krx_key")
    if not os.path.exists(p):
        sys.exit("[중단] .krx_key 파일이 없음 — 마이페이지 인증키를 1줄로 저장할 것")
    return open(p, encoding="utf-8").read().strip()

def fetch(path, bas_dd, auth):
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
    if v is None: return None
    v = str(v).replace(",", "").strip()
    try: return int(float(v))
    except ValueError: return None

def parse(payload, bas_dd):
    """OutBlock_1 → [{date,code,open,high,low,close,volume}] (필드 미확인 시 [] + 사유)"""
    rows = payload.get("OutBlock_1") or []
    out, skipped = [], 0
    d = f"{bas_dd[:4]}-{bas_dd[4:6]}-{bas_dd[6:]}"
    for r in rows:
        code = pick(r, FIELD_MAP["code"])
        if not code: skipped += 1; continue
        rec = {"date": d, "code": str(code).zfill(6)}
        ok = True
        for k in ("open", "high", "low", "close", "volume"):
            v = num(pick(r, FIELD_MAP[k]))
            if v is None and k == "close": ok = False
            rec[k] = v if v is not None else 0
        if ok: out.append(rec)
        else: skipped += 1
    return out, skipped

def append_csv(market, recs):
    path = os.path.join(HERE, f"종목일봉_30년_{market}.csv")
    if not os.path.exists(path):
        sys.exit(f"[중단] {path} 없음 — 정본 옆에서 실행할 것")
    dates = set(r["date"] for r in recs)
    # 중복 방지: 같은 날짜가 이미 있으면 추가하지 않음
    with open(path, encoding="utf-8-sig") as f:
        for line in f:
            for dd in list(dates):
                if line.startswith(dd): dates.discard(dd)
            if not dates: break
    todo = [r for r in recs if r["date"] in dates]
    if not todo:
        print(f"  {market}: 이미 있는 날짜 — 추가 0건"); return 0
    with open(path, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["date","code","open","high","low","close","volume"])
        for r in todo: w.writerow(r)
    print(f"  {market}: +{len(todo)}건 추가"); return len(todo)

def self_test():
    mock = {"OutBlock_1": [
        {"ISU_SRT_CD":"005930","TDD_OPNPRC":"70,000","TDD_HGPRC":"71000","TDD_LWPRC":"69500","TDD_CLSPRC":"70,500","ACC_TRDVOL":"12345678"},
        {"ISU_SRT_CD":"000660","TDD_CLSPRC":""},  # close 없음 → skip
        {"ISU_CD":"035420","CLSPRC":"200000","OPNPRC":"0","HGPRC":"0","LWPRC":"0","TRDVOL":"0"},  # 대체 필드명
    ]}
    recs, sk = parse(mock, "20260820")
    assert len(recs) == 2 and sk == 1, (recs, sk)
    assert recs[0] == {"date":"2026-08-20","code":"005930","open":70000,"high":71000,"low":69500,"close":70500,"volume":12345678}
    assert recs[1]["code"] == "035420" and recs[1]["close"] == 200000
    print("self-test 3/3 통과")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=datetime.date.today().strftime("%Y%m%d"))
    ap.add_argument("--probe", action="store_true", help="원본 필드명만 출력 (파일 기록 안 함)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test: return self_test()
    auth = key()
    for market, path in ENDPOINTS.items():
        try:
            payload = fetch(path, a.date, auth)
        except Exception as e:
            print(f"  {market}: 호출 실패 — {e} (활용신청 승인·경로 확인)"); continue
        if a.probe:
            rows = payload.get("OutBlock_1") or []
            print(f"[{market}] {len(rows)}행 · 필드: {sorted(rows[0].keys()) if rows else payload}")
            continue
        recs, sk = parse(payload, a.date)
        print(f"[{market}] {a.date}: 파싱 {len(recs)}건 (skip {sk})")
        if recs: append_csv(market, recs)
        elif sk == 0: print(f"  {market}: 0행 — 휴장일이거나 미승인")

if __name__ == "__main__":
    main()
