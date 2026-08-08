#!/usr/bin/env python3
"""
validate.py  —  진우퀀트 #2 Validation Gate (score_v37_2 실제 출력 형식)
=======================================================================
대상 파일: v37_2_scores_latest.csv  (score_v37_2.py main() 산출물)
GitHub Actions가 점수 생성 후 deploy 전에 실행. issue 있으면 exit 1 → deploy 건너뜀(롤백).

검사:
  1) 18종목 모두 존재
  2) 체력_최종 결측/비정상(NaN·inf) 없음
  3) 등급 유효 (S+/S/A/B/C/D/F)
  4) 포인트 합 무결성: 체력_12점 + (ModF+FAR+Sloan+Mom12+BAB+NOA+Echo) == 체력_최종
  5) 권장비중: S+/S/A 합 ≈ 100% · 종목 ≤ 15% · 섹터 ≤ 35%
  6) 전일 대비 체력_최종 급변동 (|Δ| > move_pts) alert
  7) 파일 timestamp 신선도

의존성: 표준 라이브러리만(csv, json, math). 
사용:  python3 validate.py --csv v37_2_scores_latest.csv --prev-csv v37_2_scores_prev.csv
       python3 validate.py --selftest
"""
import sys, csv, math, argparse, os, time

UNIVERSE_18 = ["삼성전자","SK하이닉스","한미반도체","알테오젠","기아","NAVER","카카오","한화에어로",
               "LIG넥스원","KB금융","KT&G","삼성SDI","아모레퍼시픽","삼성물산","삼양식품","ISC",
               "두산에너빌리티","NH투자증권"]
VALID_GRADES = {"S+","S","A","B","C","D","F"}
TARGET_GRADES = {"S+","S","A"}
FACTOR_COLS = ["ModF","FAR","Sloan","Mom12","BAB","NOA","Echo"]

def _f(x):
    try: return float(x)
    except (TypeError, ValueError): return None

def read_csv(path):
    with open(path, encoding="utf-8") as fh:
        return list(csv.DictReader(fh))

def validate(rows, prev_rows=None, stock_cap=0.15, sector_cap=0.35,
             move_pts=5.0, max_age_hours=12, csv_path=None, universe=UNIVERSE_18):
    issues, warns = [], []
    by = {r.get("종목"): r for r in rows}
    # 1) 종목 누락
    missing = [t for t in universe if t not in by]
    if missing: issues.append(f"[누락] {len(missing)}종목: {missing}")
    # 2~4) 행별 검사
    for t in universe:
        r = by.get(t)
        if not r: continue
        tot = _f(r.get("체력_최종"))
        if tot is None or not math.isfinite(tot):
            issues.append(f"[비정상값] {t} 체력_최종={r.get('체력_최종')}"); continue
        if r.get("등급") not in VALID_GRADES:
            issues.append(f"[등급오류] {t} 등급={r.get('등급')}")
        base = _f(r.get("체력_12점"))
        fac = sum((_f(r.get(c)) or 0) for c in FACTOR_COLS)
        if base is not None and abs((base + fac) - tot) > 0.05:
            issues.append(f"[합불일치] {t}: 12점+팩터={base+fac:.2f} ≠ 체력_최종={tot:.2f}")
    # 5) 권장비중
    picks = [by[t] for t in universe if t in by and by[t].get("등급") in TARGET_GRADES]
    if picks:
        wsum, sec = 0.0, {}
        for r in picks:
            w = _f(r.get("권장비중_%")) or 0.0; wsum += w
            if w > stock_cap*100 + 0.5: warns.append(f"[종목cap초과] {r['종목']} {w:.1f}% > {stock_cap*100:.0f}%")
            s = r.get("산업","Other"); sec[s] = sec.get(s,0)+w
        if abs(wsum - 100.0) > 1.0: issues.append(f"[비중합오류] S+/S/A 합 {wsum:.1f}% (≈100% 이어야)")
        for s,v in sec.items():
            if v > sector_cap*100 + 0.5: warns.append(f"[섹터cap초과] {s} {v:.1f}% > {sector_cap*100:.0f}%")
    # 6) 전일 대비 급변동
    if prev_rows:
        pv = {r.get("종목"): _f(r.get("체력_최종")) for r in prev_rows}
        for t in universe:
            if t in by and t in pv and pv[t] is not None:
                a = _f(by[t].get("체력_최종"))
                if a is not None and abs(a - pv[t]) > move_pts:
                    warns.append(f"[급변동] {t}: {pv[t]:.2f}→{a:.2f} (Δ{a-pv[t]:+.2f} > {move_pts})")
    # 7) 신선도
    if csv_path and os.path.exists(csv_path):
        age = (time.time() - os.path.getmtime(csv_path))/3600.0
        if age > max_age_hours: issues.append(f"[오래됨] {age:.1f}h 전 (> {max_age_hours}h)")
    return issues, warns

def _cli():
    ap = argparse.ArgumentParser()
    ap.add_argument("--csv"); ap.add_argument("--prev-csv")
    ap.add_argument("--move-pts", type=float, default=5.0)
    ap.add_argument("--max-age-hours", type=float, default=12.0)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest: return _selftest()
    if not a.csv: print("ERROR: --csv 필요"); return 2
    rows = read_csv(a.csv)
    prev = read_csv(a.prev_csv) if a.prev_csv and os.path.exists(a.prev_csv) else None
    iss, wrn = validate(rows, prev, move_pts=a.move_pts, max_age_hours=a.max_age_hours, csv_path=a.csv)
    for w in wrn: print("  ⚠", w)
    if iss:
        print("VALIDATION FAILED — deploy 중단, 이전 대시보드 유지:")
        for i in iss: print("  ✗", i)
        return 1
    print(f"VALIDATION PASSED ({len(wrn)} warning) — deploy 진행 가능")
    return 0

def _mkrow(nm, sec, b12, facs, grade_):
    r = {"종목":nm,"산업":sec,"체력_12점":b12}
    r.update({c:facs.get(c,0) for c in FACTOR_COLS})
    r["체력_최종"] = round(b12 + sum(r[c] for c in FACTOR_COLS), 2)
    r["등급"] = grade_; r["권장비중_%"] = 0.0
    return r

def _selftest():
    from jq_v372_bridge import JINWOO_UNIVERSE  # 종목·섹터
    rows = []
    for i,(nm,(code,sec)) in enumerate(JINWOO_UNIVERSE.items()):
        rows.append(_mkrow(nm, sec, 8.0, {"Mom12":1,"BAB":0,"Echo":1}, "A"))  # 모두 A(=12점)
    # 권장비중: A 18종목 동일가중이지만 cap/정규화 생략 → 합 100 맞춰 18등분
    for r in rows: r["권장비중_%"] = round(100/len(rows),2)
    iss, wrn = validate(rows)
    print(f"정상 케이스: issue={len(iss)} warn={len(wrn)}  (issue 0 기대)")
    assert iss == [], iss
    # 불량 케이스
    bad = [dict(r) for r in rows]
    bad = [r for r in bad if r["종목"]!="ISC"]                 # 누락
    bad[0]["체력_최종"] = "nan"                                 # 비정상값
    bad[1]["등급"] = "Z"                                        # 등급오류
    bad[2]["체력_최종"] = bad[2]["체력_12점"]                    # 합 불일치(팩터 무시)
    bad[3]["권장비중_%"] = 50.0                                  # 비중합 오류 유발
    iss2, wrn2 = validate(bad)
    print(f"불량 케이스: issue={len(iss2)}개 탐지:")
    for i in iss2: print("   -", i)
    assert len(iss2) >= 4, iss2
    print("[OK] validate self-test 통과")
    return 0

if __name__ == "__main__":
    sys.exit(_cli())
