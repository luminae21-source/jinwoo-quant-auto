# -*- coding: utf-8 -*-
r"""재무패널_DART수집.py — pykrx 사망으로 끊긴 종목재무 패널을 DART로 복구 (2026-08-23)

[왜] 종목재무_KRX_*.csv는 fetch_fundamental_panel.py(pykrx 의존)가 만들었고 2026-06-30에서 멈췄다.
     KRX Open API에는 재무 엔드포인트가 없다(가격·거래량·종목기본정보뿐).
     → DART 원천으로 같은 스키마를 재생산한다. 연 1회(6월) 자격풀 재구성이 목적.

[스키마] 기존과 동일: date,code,BPS,PER,PBR,EPS,DIV,DPS
     BPS = 지배주주자본 / 상장주식수      EPS = 지배주주순이익 / 상장주식수
     PBR = 시총 / 지배주주자본            PER = 시총 / 지배주주순이익
     DPS = 배당금지급 / 상장주식수        DIV = 배당금지급 / 시총 * 100

[중요] --validate 를 통과하기 전에는 이 파일을 자격풀에 쓰지 않는다.
     pykrx→KRX Open API 전환 때 재무가 조용히 소실된 사고(2026-07-16)의 재발 방지 장치다.

사용:
  py 재무패널_DART수집.py --year 2025            # 2025 사업연도 수집 (재개 가능)
  py 재무패널_DART수집.py --year 2025 --limit 50 # 시험 수집
  py 재무패널_DART수집.py --validate             # 종목재무_KRX와 겹치는 구간 일치도 검사
  py 재무패널_DART수집.py --selftest
"""
import os, sys, csv, json, time, argparse
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(HERE, "종목재무_DART.csv")
CKPT = os.path.join(HERE, "_재무패널_DART_ckpt.json")
COLS = ["date", "code", "BPS", "PER", "PBR", "EPS", "DIV", "DPS", "src_rcept"]
REPRT_ANNUAL = "11011"
SLEEP = 0.12


# ---------- 순수 계산부 (네트워크 불필요 · self-test 대상) ----------
def derive(mcap, shares, equity, ni, div_paid):
    """재무 원자료 → 패널 8필드. 분모 0/음수는 None."""
    f = {"BPS": None, "PER": None, "PBR": None, "EPS": None, "DIV": None, "DPS": None}
    if not shares or shares <= 0:
        return f
    if equity is not None:
        f["BPS"] = equity / shares
        if mcap and equity > 0:
            f["PBR"] = mcap / equity
    if ni is not None:
        f["EPS"] = ni / shares
        if mcap and ni > 0:
            f["PER"] = mcap / ni          # 적자면 PER 없음 (KRX 관행과 동일)
    if div_paid is not None:
        d = max(0.0, div_paid)            # 음수 배당은 시점 어긋남 → 0 (스타일패널과 동일 규칙)
        f["DPS"] = d / shares
        if mcap:
            f["DIV"] = d / mcap * 100.0
    return f


def resolve_corp_codes(key, names):
    """6자리 종목코드 → DART corp_code. **미해결이 있어도 죽지 않는다.**
    fetch_dart_eps.load_corp_codes 는 하나라도 못 찾으면 sys.exit 한다(2,651종 전수에선
    스팩·신규상장·개명이 반드시 섞여 항상 실패). 여기서는 관용적으로 일괄 해석하고
    못 찾은 것만 돌려준다. 2026-08-24 전수 수집 중단 사고 대응.
    반환: ({이름: corp_code}, [미해결 이름들])
    """
    import json as _json, re as _re, io as _io, zipfile as _zip, requests
    from fetch_dart_eps import CORPCODE_URL
    mapping = {}
    f = os.path.join(HERE, "dart_corp_codes.json")
    if os.path.exists(f):
        try:
            d = _json.load(open(f, encoding="utf-8"))
            items = d.values() if isinstance(d, dict) else d
            for it in items:
                if isinstance(it, dict):
                    sc = str(it.get("stock_code", "")).strip().zfill(6)
                    cc = str(it.get("corp_code", "")).strip()
                    if len(cc) == 8 and sc != "000000":
                        mapping[sc] = cc
            if isinstance(d, dict) and not mapping:
                for k, v in d.items():
                    if isinstance(v, str) and len(v.strip()) == 8:
                        mapping[str(k).strip().zfill(6)] = v.strip()
        except Exception:
            pass
    if any(c not in mapping for c in names.values()):
        print("[corp_code] corpCode.xml 다운로드 (1회)")
        r = requests.get(CORPCODE_URL, params={"crtfc_key": key}, timeout=90)
        zf = _zip.ZipFile(_io.BytesIO(r.content))
        xml = zf.read(zf.namelist()[0]).decode("utf-8")
        for m in _re.finditer(
                r"<corp_code>(\d{8})</corp_code>.*?<stock_code>([0-9]{6})</stock_code>", xml, _re.S):
            mapping[m.group(2)] = m.group(1)
    out, missing = {}, []
    for nm, cd in names.items():
        if cd in mapping:
            out[nm] = mapping[cd]
        else:
            missing.append(nm)
    return out, missing


def load_universe():
    """종목스냅숏_일별.csv 최신일 → 양시장 보통주(끝자리 0) 전체."""
    p = os.path.join(HERE, "종목스냅숏_일별.csv")
    if not os.path.exists(p):
        sys.exit("[중단] 종목스냅숏_일별.csv 없음 — 먼저 py 진우퀀트_KRX수집.py 실행")
    rows = list(csv.DictReader(open(p, encoding="utf-8-sig")))
    last = max(r["date"] for r in rows)
    out = []
    for r in rows:
        if r["date"] != last or str(r["code"])[-1] != "0":
            continue
        try:
            mc, sh = int(r["mcap"] or 0), int(r["shares"] or 0)
        except ValueError:
            continue
        if mc > 0 and sh > 0:
            out.append({"code": r["code"], "name": r["name"], "mcap": mc,
                        "shares": sh, "market": r["market"]})
    out.sort(key=lambda r: -r["mcap"])
    return last, out


def read_panel(path):
    if not os.path.exists(path): return []
    return list(csv.DictReader(open(path, encoding="utf-8-sig")))


# ---------- 검증부 ----------
def validate():
    """DART 산출 vs 기존 종목재무_KRX — 같은 (code) 기준 EPS·BPS 일치도."""
    new = read_panel(OUT)
    if not new:
        sys.exit("[중단] 종목재무_DART.csv 없음 — 먼저 --year 로 수집")
    old = []
    for m in ("KOSPI", "KOSDAQ"):
        p = os.path.join(HERE, f"종목재무_KRX_{m}.csv")
        old += read_panel(p)
    if not old:
        sys.exit("[중단] 종목재무_KRX_*.csv 없음 — 대조 불가")
    last_old = max(r["date"] for r in old)
    o = {r["code"].zfill(6): r for r in old if r["date"] == last_old}
    print("대조 기준: 기존 %s (%d종) vs DART 산출 (%d행)" % (last_old, len(o), len(new)))

    def num(v):
        try:
            x = float(v)
            return x if x != 0 else None
        except (TypeError, ValueError):
            return None

    stats = {}
    for fld in ("EPS", "BPS"):
        pairs = []
        for r in new:
            c = r["code"].zfill(6)
            if c not in o: continue
            a, b = num(r.get(fld)), num(o[c].get(fld))
            if a is None or b is None: continue
            pairs.append((a, b))
        if not pairs:
            stats[fld] = None; continue
        n = len(pairs)
        within = lambda t: sum(1 for a, b in pairs if abs(a - b) <= abs(b) * t) / n
        stats[fld] = dict(n=n, w5=within(0.05), w10=within(0.10), w25=within(0.25))

    print("\n%-5s %6s %10s %10s %10s" % ("필드", "대조수", "±5% 이내", "±10%", "±25%"))
    ok = True
    for fld in ("EPS", "BPS"):
        s = stats[fld]
        if not s:
            print("%-5s %6s  대조 가능한 쌍 없음" % (fld, "-")); ok = False; continue
        print("%-5s %6d %9.1f%% %9.1f%% %9.1f%%"
              % (fld, s["n"], s["w5"]*100, s["w10"]*100, s["w25"]*100))
        if s["n"] < 100 or s["w25"] < 0.80: ok = False

    print("\n합격선(사전 고정): 대조쌍 ≥100종 · ±25% 이내 비율 ≥80%")
    print("판정: %s" % ("PASS — 자격풀에 사용 가능" if ok else
                        "FAIL — 사용 금지. 계정 매칭/기준일 정합부터 점검"))
    print("\n※ 완전 일치는 기대하지 않는다. KRX 공표치는 공표 시점 기준이고 "
          "DART 산출은 사업연도 기준이라 시차가 있다. 그래서 ±25%를 문턱으로 잡았다.")
    return ok


# ---------- 수집부 ----------
def collect(year, limit=0):
    sys.path.insert(0, HERE)
    from fetch_dart_eps import load_api_key, load_corp_codes, DART_URL
    from 스타일패널_DART import equity_of, ni_of, div_paid_of, has_cf
    import requests

    key = load_api_key()
    asof, uni = load_universe()
    if limit: uni = uni[:limit]
    print("[유니버스] %s 기준 %d종 (양시장 보통주)" % (asof, len(uni)))

    ck = json.load(open(CKPT, encoding="utf-8")) if os.path.exists(CKPT) else {}
    done = set(ck.get("done", []))
    print("[재개] 이미 처리 %d종" % len(done))

    names = {r["name"]: r["code"] for r in uni}
    cc, unresolved = resolve_corp_codes(key, names)
    print("[corp_code] 매핑 %d/%d" % (len(cc), len(uni)))
    if unresolved:
        # 침묵 금지: 빠진 종목을 파일로 남긴다. 스팩·신규상장·개명이 대부분이다.
        with open(os.path.join(HERE, "_재무패널_DART_미해결.txt"), "w", encoding="utf-8") as f:
            f.write("\n".join("%s\t%s" % (n, names[n]) for n in unresolved))
        print("  [주의] corp_code 미해결 %d종 → 결측 처리하고 계속 "
              "(_재무패널_DART_미해결.txt 에 기록)" % len(unresolved))
        print("        예:", ", ".join(unresolved[:6]))

    new_rows, miss, fail, retry = [], 0, 0, 0
    stat = {}
    t0 = time.time()
    for i, r in enumerate(uni, 1):
        if r["code"] in done: continue
        corp = cc.get(r["name"])
        if not corp:
            miss += 1; done.add(r["code"]); continue
        try:
            # DART status 를 반드시 본다. 안 보면 요청제한(020)·점검(800)이
            # '미공시'로 둔갑해 조용히 유실된다. 2026-08-24: 이 누락으로 수집률 34% 착시.
            #   000 정상 / 013 데이터 없음(진짜 미공시) / 020 요청제한 / 800·900 시스템
            rows, st = None, None
            for fs in ("CFS", "OFS"):        # 연결 없으면 개별로 폴백 (단독법인 다수)
                js = requests.get(DART_URL, params={
                    "crtfc_key": key, "corp_code": corp, "bsns_year": str(year),
                    "reprt_code": REPRT_ANNUAL, "fs_div": fs}, timeout=30).json()
                st = str(js.get("status", "")).strip()
                if st == "000" and js.get("list"):
                    rows = js["list"]; break
                if st in ("020", "021", "800", "900"):
                    break                     # 재시도 대상 — 폴백 의미 없음
            stat[st] = stat.get(st, 0) + 1
            if st in ("020", "021", "800", "900"):
                retry += 1
                print("  [대기] DART status=%s — 60초 쉬고 재개 (이 종목은 미처리로 남김)" % st,
                      flush=True)
                time.sleep(60)
                continue                      # done 에 넣지 않는다 → 재실행 시 재시도
            if not rows:
                miss += 1; done.add(r["code"]); continue
            # ⚠ equity_of/ni_of/div_paid_of 는 (값, rcept_no) 튜플을 반환한다.
            #   2026-08-23: 언패킹 없이 나눗셈에 넣어 50/50 전량 실패. 반드시 언패킹할 것.
            eq, rc_eq = equity_of(rows)
            ni, rc_ni = ni_of(rows)
            dv, rc_dv = div_paid_of(rows)
            # 무배당(0)과 결측(None)을 가른다. 현금흐름표가 응답에 있는데 배당 계정만 없으면
            # 그 회사는 배당을 '안 한' 것이지 데이터가 '없는' 게 아니다.
            # (스타일패널에서 배당 결측 59종 -> 6종으로 줄인 것과 동일 규칙)
            if dv is None and has_cf(rows):
                dv = 0.0
            f = derive(r["mcap"], r["shares"], eq, ni, dv)
            new_rows.append({"date": f"{year}-12-31", "code": r["code"],
                             **{k: ("" if f[k] is None else round(f[k], 4)) for k in
                                ("BPS", "PER", "PBR", "EPS", "DIV", "DPS")},
                             "src_rcept": rc_ni or rc_eq or rc_dv or ""})
            done.add(r["code"])
        except Exception as e:
            fail += 1
            print("  [실패] %s %s: %s" % (r["code"], r["name"], str(e)[:60]))
        time.sleep(SLEEP)
        if i % 100 == 0:
            print("  %d/%d · 수집 %d · 미공시 %d · 재시도대기 %d · 실패 %d · %.0f초"
                  % (i, len(uni), len(new_rows), miss, retry, fail, time.time()-t0), flush=True)
            _flush(new_rows, done); new_rows = []
    _flush(new_rows, done)
    print("\n[완료] 누적 처리 %d종 · 미공시 %d · 재시도대기 %d · 실패 %d"
          % (len(done), miss, retry, fail))
    print("[DART status 집계]", ", ".join("%s:%d" % kv for kv in sorted(stat.items())))
    if retry:
        print("  ※ 요청제한/점검으로 %d종 미처리 — 같은 명령을 다시 실행하면 그 종목만 재시도한다." % retry)
    print("저장: 종목재무_DART.csv")
    print("\n다음: py 재무패널_DART수집.py --validate  ← 통과 전에는 자격풀에 쓰지 않는다")


def _flush(rows, done):
    if rows:
        new = not os.path.exists(OUT)
        with open(OUT, "a", newline="", encoding="utf-8-sig") as f:
            w = csv.DictWriter(f, fieldnames=COLS)
            if new: w.writeheader()
            w.writerows(rows)
    json.dump({"done": sorted(done)}, open(CKPT, "w", encoding="utf-8"))


def selftest():
    ok = []
    f = derive(mcap=1000, shares=10, equity=500, ni=100, div_paid=50)
    ok.append(("BPS = 자본/주식수", f["BPS"] == 50.0))
    ok.append(("EPS = 순이익/주식수", f["EPS"] == 10.0))
    ok.append(("PBR = 시총/자본", f["PBR"] == 2.0))
    ok.append(("PER = 시총/순이익", f["PER"] == 10.0))
    ok.append(("DPS = 배당/주식수", f["DPS"] == 5.0))
    ok.append(("DIV = 배당/시총*100", abs(f["DIV"] - 5.0) < 1e-9))
    g = derive(1000, 10, 500, -100, 0)
    ok.append(("적자면 EPS 음수·PER 없음", g["EPS"] == -10.0 and g["PER"] is None))
    h = derive(1000, 10, 500, 100, -30)
    ok.append(("음수 배당은 0으로 클립", h["DPS"] == 0.0 and h["DIV"] == 0.0))
    z = derive(1000, 0, 500, 100, 10)
    ok.append(("주식수 0이면 전부 None", all(v is None for v in z.values())))
    n = derive(1000, 10, None, None, None)
    ok.append(("결측은 None 유지", n["BPS"] is None and n["EPS"] is None))
    try:
        asof, uni = load_universe()
        ok.append(("유니버스 로드 >2000종", len(uni) > 2000))
        ok.append(("보통주만(끝자리 0)", all(str(r["code"])[-1] == "0" for r in uni)))
    except SystemExit:
        ok.append(("유니버스 로드", False))
    # 재사용 함수 계약 검사 (2026-08-23 회귀 방지) — 네트워크 불필요
    try:
        sys.path.insert(0, HERE)
        from 스타일패널_DART import equity_of, ni_of, div_paid_of
        fake = [{"sj_div": "BS", "account_id": "ifrs-full_Equity",
                 "account_nm": "자본총계", "thstrm_amount": "1000", "rcept_no": "R1"},
                {"sj_div": "IS", "account_id": "ifrs-full_ProfitLoss",
                 "account_nm": "당기순이익", "thstrm_amount": "200", "rcept_no": "R2"},
                {"sj_div": "CF", "account_id": "ifrs-full_DividendsPaidClassifiedAsFinancingActivities",
                 "account_nm": "배당금지급", "thstrm_amount": "-50", "rcept_no": "R3"}]
        for nm_, fn in (("equity_of", equity_of), ("ni_of", ni_of), ("div_paid_of", div_paid_of)):
            r_ = fn(fake)
            ok.append((f"{nm_}는 (값,접수번호) 2-튜플", isinstance(r_, tuple) and len(r_) == 2))
        eqv, _ = equity_of(fake); niv, _ = ni_of(fake); dvv, _ = div_paid_of(fake)
        ff = derive(2000, 10, eqv, niv, dvv)
        ok.append(("언패킹 후 derive 정상", ff["BPS"] == 100.0 and ff["EPS"] == 20.0))
        ok.append(("배당 절대값 처리", ff["DPS"] == 5.0))
        from 스타일패널_DART import has_cf
        ok.append(("has_cf: CF 있으면 True", has_cf(fake) is True))
        no_cf = [x for x in fake if x["sj_div"] != "CF"]
        ok.append(("has_cf: CF 없으면 False", has_cf(no_cf) is False))
        # CF는 있는데 배당 계정만 없는 회사 -> 무배당 0 으로 확정되어야 한다
        nodiv = no_cf + [{"sj_div": "CF", "account_id": "ifrs-full_CashFlowsFromUsedInOperatingActivities",
                          "account_nm": "영업활동현금흐름", "thstrm_amount": "300", "rcept_no": "R4"}]
        dv_, _ = div_paid_of(nodiv)
        dv_ = 0.0 if (dv_ is None and has_cf(nodiv)) else dv_
        ok.append(("무배당은 결측 아닌 0", dv_ == 0.0))
    except Exception as e:
        ok.append(("재사용 함수 계약 검사: " + str(e)[:40], False))

    for n_, v in ok: print(("  OK   " if v else "  FAIL ") + n_)
    print("self-test %d/%d" % (sum(v for _, v in ok), len(ok)))
    return all(v for _, v in ok)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--year", type=int); ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--validate", action="store_true")
    ap.add_argument("--recheck", action="store_true",
                    help="체크포인트를 실제 수집분으로 재구성 (미수집분 재시도용)"); ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest: sys.exit(0 if selftest() else 1)
    if a.validate: sys.exit(0 if validate() else 1)
    if a.recheck:
        got = {r["code"] for r in read_panel(OUT)}
        json.dump({"done": sorted(got)}, open(CKPT, "w", encoding="utf-8"))
        print("체크포인트 재구성: 실제 수집된 %d종만 완료로 표시. "
              "이제 --year 를 다시 실행하면 나머지만 재시도한다." % len(got))
        sys.exit(0)
    if not a.year: sys.exit("--year 필요 (예: --year 2025)")
    collect(a.year, a.limit)


if __name__ == "__main__":
    main()
