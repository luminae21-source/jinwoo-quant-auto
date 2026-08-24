# -*- coding: utf-8 -*-
r"""collect_kis_monthly.py — [PC 실행] KIS 월봉 수정주가 1996~2015 수집 (조회 전용)

왜 이 스크립트인가
────────────────────────────────────────────────────────────────────────────
커버리지 프로브(2026-07-28) 결과가 KIS의 역할을 바꿨다.

  · KIS는 pre-2010 상폐종목을 **0%** 준다 → pre-2010 데이터원으로 쓸 수 없다.
  · 대신 **2010-12 이후 시점단면 커버리지가 종목·시총 100%**다.
  · pykrx 수정주가는 **2014-04-30이 하한**이다(`_월봉종가캐시_*_adj.csv` 첫 행이 그 날짜).

  → 2010~2014 구간에서 **조정가를 주는 원천은 KIS가 유일**하다.
  → 그리고 그 구간은 KRX 원주가(`종목일봉_30년_*.csv`, 1996~, 상폐 포함)와 겹친다.

그래서 이 수집은 두 가지를 동시에 한다.
  ① 2010~2014 조정가 확보 (생산용 — 이 구간은 커버리지 100%라 생존편향 없음)
  ② **자체 조정 파이프라인의 정답지 확보** (검증용 — KRX 원주가 + ca_flags 로 만든
     자체 조정가를 이 구간에서 KIS와 대조하면, 참조가 없는 1996~2009 구간의
     조정 오차율을 표본 외로 추정할 수 있다)

⛔ 이 파일이 만드는 패널은 **그 자체로 백테에 쓰면 안 된다.**
   1996~2009 구간은 생존자만 담긴다(프로브가 측정한 사실). 그 구간은 KRX 원주가 +
   자체 조정으로 채우고, 병합 시 `source` 열로 출처를 남긴다. 병합 규칙은 런북 참조.

안전
────────────────────────────────────────────────────────────────────────────
  · 조회 전용. 주문 tr_id / 주문 엔드포인트 문자열이 소스에 없는지 셀프테스트가 검사한다.
  · 카나리 통과 없이는 본수집을 시작하지 않는다. 카나리가 없으면 '검증 불가'로 중단한다
    (통과로 간주하지 않는다 — ca_guard 와 같은 원칙).
  · 키는 절대 출력하지 않는다(길이 마스킹만).

사용
────────────────────────────────────────────────────────────────────────────
  py 데이터수리\collect_kis_monthly.py --selftest        # 네트워크 0
  py 데이터수리\collect_kis_monthly.py --canary          # 카나리만 (2콜)
  py 데이터수리\collect_kis_monthly.py --sample 40       # 등간격 표본 맛보기
  py 데이터수리\collect_kis_monthly.py                   # 본수집 (재개 자동)
  py 데이터수리\collect_kis_monthly.py --report          # 수집 결과 요약만
"""
import os, sys, csv, json, time, argparse

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

from broker_adj_smoke import (KIS_LIVE, KIS_PAPER, kis_token, kis_chart,
                              load_kis_keys, mask, find_file)

PROBE = os.path.join(HERE, "kis_커버리지_프로브.csv")
OUT   = os.path.join(HERE, "_월봉_KIS_adj.csv")
CKPT  = os.path.join(HERE, "_kis월봉_ckpt.json")
FAIL  = os.path.join(HERE, "_kis월봉_실패.csv")

HDR  = ["code", "ym", "close", "market"]
CHUNKS = [(1996, 1999), (2000, 2003), (2004, 2007), (2008, 2011), (2012, 2015)]

# 네트워크 재시도 정책 (2026-07-28 ConnectionResetError 10054 대응)
NET_TRIES = 6        # 청크 1개당 최대 시도 횟수
NET_BACKOFF = 2.0    # 대기 = NET_BACKOFF * 시도번호  → 2,4,6,8,10초

# 카나리 — 시장별 감시 셀. 값이 다르면 조정가가 아니거나 오염이다.
# 두 값은 **디스크의 서로 다른 두 패널에서 실측**한 것이어야 한다(계산해서 채우면 카나리가 아니다).
#   raw = 종목일봉_30년_*.csv (by-date 수집 = 그날 실제 거래된 종가)
#   adj = _월봉종가캐시_*_adj.csv (pykrx 수정주가)
#
# ⛔ 2026-07-28 폐기: KOSDAQ 셀 064550 (adj 12,750 / raw 51,000).
#    51,000은 어디서도 관측되지 않았다 — ca_flags 의 ×2 두 건(2021-08, 2023-02)을 곱해
#    12,750×4 로 **계산해 넣은 값**이었다. 그런데 2021-08 은 한 달간 35,000→74,000 으로
#    일별 연속 상승한 **진짜 랠리**(가격비율 휴리스틱의 오탐)였고, 실제 2018-04-30 거래 종가는
#    세 출처 모두 12,750 이었다(원주가 일봉·미조정 월봉·KIS 양쪽 플래그).
#    → raw == adj 인 셀은 조정/미조정을 **판별할 수 없다.** KIS 가 틀린 게 아니라 셀이 틀렸다.
# 대체: 098460 (고영) 2021-04-13 5:1 액면분할 — 일봉에 121,500→28,300 단일일 불연속 확인.
CANARY = [
    ("005930", "KOSPI",  2018, 2018, "2018-04", 53_000,   2_650_000),   # 50:1 (2018-05)
    ("098460", "KOSDAQ", 2018, 2018, "2018-04", 20_360,     101_800),   # 5:1 (2021-04-13)
]
CANARY_TOL = 0.03      # ±3%


# --------------------------------------------------------------------------- 원천
def source_is_read_only(path=None):
    """이 소스에 주문 관련 문자열이 없는지. 금지어는 조각으로 조립해 자기검사에 걸리지 않게 한다."""
    path = path or os.path.abspath(__file__)
    banned = ["TT" + "TC0802U", "TT" + "TC0801U", "VT" + "TC0802U",
              "order" + "-cash", "order" + "-credit", "order" + "-rvsecncl"]
    try:
        src = open(path, encoding="utf-8", errors="replace").read()
    except Exception as e:
        return False, [f"읽기실패 {e}"]
    hits = [b for b in banned if b in src]
    return (not hits), hits


def rows_to_monthly(rows):
    """KIS output2 → {'YYYY-MM': close}. 같은 달이 여러 행이면 마지막 영업일을 쓴다."""
    best = {}
    for r in rows or []:
        d = str(r.get("stck_bsop_date") or "")
        if len(d) < 8 or not d[:8].isdigit():
            continue
        try:
            c = float(r.get("stck_clpr") or 0)
        except Exception:
            continue
        if c <= 0:
            continue
        ym = f"{d[:4]}-{d[4:6]}"
        if ym not in best or d > best[ym][0]:
            best[ym] = (d, c)
    return {ym: v[1] for ym, v in best.items()}


def load_probe():
    """프로브 결과 → {code: (market, earliest_ym)} — status=='ok' 인 코드만."""
    if not os.path.exists(PROBE):
        return None
    out = {}
    with open(PROBE, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r.get("status") != "ok":
                continue
            out[r["code"]] = (r.get("market") or "", r.get("earliest_ym") or "")
    return out


def chunk_plan(earliest_ym):
    """최초 관측월이 알려져 있으면 그보다 이른 청크는 아예 부르지 않는다(콜 절약)."""
    if not earliest_ym or len(earliest_ym) < 4 or not earliest_ym[:4].isdigit():
        return list(CHUNKS)
    y = int(earliest_ym[:4])
    return [(a, b) for (a, b) in CHUNKS if b >= y]


def sample_spread(codes, n):
    """코드순 등간격 표본. 난수 없음 → 재현 가능. --limit 처럼 앞쪽으로 쏠리지 않는다."""
    codes = sorted(codes)
    if n <= 0 or n >= len(codes):
        return codes
    step = len(codes) / float(n)
    return [codes[min(len(codes) - 1, int(i * step))] for i in range(n)]


# --------------------------------------------------------------------------- 상태
def load_ckpt():
    if os.path.exists(CKPT):
        try:
            c = json.load(open(CKPT, encoding="utf-8"))
            if isinstance(c, dict) and "done" in c:
                return c
        except Exception:
            pass
    return {"done": []}


def save_ckpt(ck):
    json.dump(ck, open(CKPT, "w", encoding="utf-8"), ensure_ascii=False)


def ensure_files():
    if not os.path.exists(OUT):
        with open(OUT, "w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(HDR)
    if not os.path.exists(FAIL):
        with open(FAIL, "w", encoding="utf-8", newline="") as f:
            csv.writer(f).writerow(["code", "status", "detail"])


# --------------------------------------------------------------------------- 카나리
def run_canary(host, tok, keys, chart=None, sleep_s=0.25):
    """조정가가 진짜 조정가인지. 통과/실패/검증불가 세 값을 구분한다.

    chart 를 주입할 수 있게 둔 이유: 판정 로직을 셀프테스트가 **복사본이 아니라 이 함수 그대로**
    검사해야 한다. (2026-07-28 교훈 — 복사본을 테스트하면 접착부 버그가 통과한다.)
    """
    chart = chart or kis_chart
    results = []
    for code, mkt, y0, y1, ym, want_adj, want_raw in CANARY:
        got = {}
        for tag, flag, want in (("adj", "0", want_adj), ("raw", "1", want_raw)):
            rows, err = chart(host, tok, keys, code, y0, y1, period="M", adj=flag)
            if err:
                got[tag] = ("err", err)
                continue
            m = rows_to_monthly(rows)
            if ym not in m:
                got[tag] = ("missing", f"{ym} 없음")
            else:
                v = m[ym]
                ok = abs(v - want) <= CANARY_TOL * want
                got[tag] = ("ok" if ok else "mismatch", f"{v:,.0f} (기대 {want:,.0f})")
            time.sleep(sleep_s)
        results.append((code, mkt, ym, got))
    verdict = "pass"
    for code, mkt, ym, got in results:
        st_a = got.get("adj", ("err", ""))[0]
        st_r = got.get("raw", ("err", ""))[0]
        if st_a == "mismatch" or st_r == "mismatch":
            verdict = "fail"
        elif st_a != "ok" or st_r != "ok":
            if verdict != "fail":
                verdict = "unverifiable"
    return verdict, results


def print_canary(verdict, results):
    print("[카나리]")
    for code, mkt, ym, got in results:
        a = got.get("adj", ("?", "")); r = got.get("raw", ("?", ""))
        print(f"  {code}({mkt}) {ym}  수정주가 {a[0]}: {a[1]}   원주가 {r[0]}: {r[1]}")
    label = {"pass": "★ 통과", "fail": "✗ 실패 — 조정가가 아니거나 오염",
             "unverifiable": "⚠️ 검증 불가 (통과가 아님)"}[verdict]
    print(f"  판정: {label}")


# --------------------------------------------------------------------------- 수집
def collect_one(host, tok, keys, code, market, earliest_ym, sleep_s, chart=None):
    """한 코드의 1996~2015 월말 종가(수정주가). 반환 (rows, calls, err).

    chart: 테스트 주입용 (기본 kis_chart). run_canary 와 동일한 패턴.
    """
    chart = chart or kis_chart
    got = {}
    calls = 0
    for (y0, y1) in chunk_plan(earliest_ym):
        last = ""
        for attempt in range(NET_TRIES):
            # ⚠️ 2026-07-28 크래시의 자리.
            # kis_chart 는 HTTP/응답 오류를 err 문자열로 "돌려주지만",
            # 소켓이 끊기면(ConnectionResetError 10054 등) requests 가 예외를 "던진다".
            # 초판은 던진 예외를 잡지 않아 재시도 루프를 그대로 뚫고 프로세스가 죽었다
            # (600/2,444 지점에서 실제로 발생). 예외도 err 로 변환해 재시도 대상으로 만든다.
            try:
                rows, err = chart(host, tok, keys, code, y0, y1,
                                  period="M", adj="0")
            except KeyboardInterrupt:
                raise
            except Exception as e:                      # noqa: BLE001 - 네트워크 전반
                rows, err = [], f"예외 {type(e).__name__}: {e}"
            calls += 1
            if err is None:
                got.update(rows_to_monthly(rows))
                last = ""
                break
            last = err
            time.sleep(NET_BACKOFF * (attempt + 1))
        if last:
            return None, calls, last
        time.sleep(sleep_s)
    out = [[code, ym, f"{got[ym]:.0f}", market] for ym in sorted(got)]
    return out, calls, None


def prepare(host, load_keys=None, token_fn=None):
    """키 로드 + 토큰 발급. 반환 (keys, tok, 설명, 실패사유|None).

    ⚠️ 2026-07-28 버그의 자리. broker_adj_smoke 의 두 함수는 **둘 다 (값, 출처) 튜플**을 돌려준다:
        load_kis_keys() -> (keys|None, "출처설명")
        kis_token(host, keys) -> (token, "캐시"|"신규발급")
    초판은 이를 풀지 않고 keys['app_key'] / f"Bearer {tok}" 로 써서 TypeError 로 죽었다.
    셀프테스트가 오프라인이라 접착부를 아예 밟지 않았던 것이 원인 — 그래서 이 함수를
    주입 가능하게 떼어내고 ⑱~㉑ 로 계약을 고정한다.
    """
    load_keys = load_keys or load_kis_keys
    token_fn = token_fn or kis_token
    keys, ksrc = load_keys()
    if not keys:
        return None, None, f"키 없음 ({ksrc})", "키 없음"
    tok, tsrc = token_fn(host, keys)
    if not tok:
        return keys, None, f"키 {ksrc} · 토큰 실패", "토큰 실패"
    return keys, tok, f"키 {ksrc} · 토큰 {tsrc}", None


def run(args):
    ro, hits = source_is_read_only()
    if not ro:
        print(f"✗ 소스에 주문 문자열 발견 {hits} — 중단"); return 2

    probe = load_probe()
    if probe is None:
        print(f"✗ 프로브 결과 없음: {PROBE}")
        print("  먼저 py 데이터수리\\kis_coverage_probe.py 를 완주하십시오.")
        return 2
    print(f"프로브 status=ok 코드 {len(probe):,}개 (미도달·신규상장은 애초에 부르지 않는다)")

    host = KIS_PAPER if args.paper else KIS_LIVE
    print(f"호스트: {'모의' if args.paper else '실전'} (조회 전용)")
    keys, tok, desc, why = prepare(host)
    if why == "키 없음":
        print(f"✗ KIS 키 없음 — 스킵 ({desc})"); return 2
    print(f"키 로드: app_key {mask(keys['app_key'])} (값은 찍지 않음) · {desc}")
    if why == "토큰 실패":
        print("✗ 토큰 발급 실패 (1분 1회 제한 — 잠시 후 재시도)"); return 2

    verdict, results = run_canary(host, tok, keys)
    print_canary(verdict, results)
    if verdict != "pass":
        print("→ 카나리가 통과하지 않았습니다. 본수집을 시작하지 않습니다.")
        if not args.force_no_canary:
            return 3
        print("⚠️ --force-no-canary 지정 — 이 실행의 산출물은 검증되지 않은 데이터입니다.")
    if args.canary_only:
        return 0

    ensure_files()
    ck = load_ckpt(); done = set(ck["done"])

    codes = sorted(probe)
    if args.sample:
        codes = sample_spread(codes, args.sample)
        print(f"표본 {len(codes)}개 (코드순 등간격 · 재현 가능)")
    todo = [c for c in codes if c not in done]
    print(f"대상 {len(codes):,} · 완료 {len(codes) - len(todo):,} · 이번 실행 {len(todo):,}")

    t0 = time.time(); nrow = 0; nerr = 0; ncalls = 0
    fo = open(OUT, "a", encoding="utf-8", newline="")
    ff = open(FAIL, "a", encoding="utf-8", newline="")
    w = csv.writer(fo); wf = csv.writer(ff)
    try:
        for i, code in enumerate(todo, 1):
            market, ey = probe[code]
            # 2차 방어선: collect_one 안에서 못 잡은 예외가 있어도
            # "그 종목 1개 실패"로 강등시키고 전체 실행은 계속한다.
            try:
                rows, calls, err = collect_one(host, tok, keys, code,
                                               market, ey, args.sleep)
            except KeyboardInterrupt:
                raise
            except Exception as e:                      # noqa: BLE001
                rows, calls, err = None, 1, f"예외(코드루프) {type(e).__name__}: {e}"
            ncalls += calls
            if err:
                wf.writerow([code, "error", err[:160]]); ff.flush(); nerr += 1
            else:
                if rows:
                    w.writerows(rows); nrow += len(rows)
                done.add(code)
            if i % 50 == 0 or i == len(todo):
                fo.flush()
                ck["done"] = sorted(done); save_ckpt(ck)
                el = (time.time() - t0) / 60.0
                rate = i / el if el > 0 else 0
                eta = (len(todo) - i) / rate if rate > 0 else 0
                print(f"  {i:,}/{len(todo):,} · 행 {nrow:,} · 콜 {ncalls:,} · 실패 {nerr} "
                      f"· {el:.1f}분 · ETA {eta:.0f}분")
    except KeyboardInterrupt:
        print("\n중단됨 — 체크포인트 저장. 다시 실행하면 이어받습니다.")
    finally:
        fo.flush(); fo.close(); ff.close()
        ck["done"] = sorted(done); save_ckpt(ck)

    print(f"\n완료: 행 {nrow:,} · 콜 {ncalls:,} · 실패 {nerr} · {(time.time()-t0)/60.0:.1f}분")
    report()
    return 0


def report():
    if not os.path.exists(OUT):
        print("산출물 없음"); return
    import collections
    n = 0; codes = set(); byyear = collections.Counter()
    with open(OUT, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            n += 1; codes.add(r["code"]); byyear[r["ym"][:4]] += 1
    print(f"\n[_월봉_KIS_adj.csv] 행 {n:,} · 코드 {len(codes):,}")
    ys = sorted(byyear)
    if ys:
        print(f"  연도 {ys[0]}~{ys[-1]} · 연평균 행 {n/len(ys):,.0f}")
        print("  " + " ".join(f"{y}:{byyear[y]:,}" for y in ys))
    print("\n⛔ 이 패널만으로 백테하지 마십시오. 1996~2009 구간은 생존자만 담겨 있습니다.")
    print("   pre-2010 은 KRX 원주가 + 자체 조정으로 채우고 source 열로 출처를 남깁니다.")


# --------------------------------------------------------------------------- 셀프테스트
def selftest():
    ok = []

    m = rows_to_monthly([{"stck_bsop_date": "20140430", "stck_clpr": "6000"},
                         {"stck_bsop_date": "20140331", "stck_clpr": "5800"}])
    ok.append(("① 월말 종가 파싱", m == {"2014-04": 6000.0, "2014-03": 5800.0}))

    m = rows_to_monthly([{"stck_bsop_date": "20140401", "stck_clpr": "100"},
                         {"stck_bsop_date": "20140430", "stck_clpr": "200"}])
    ok.append(("② 같은 달 중복 → 마지막 영업일 채택", m == {"2014-04": 200.0}))

    m = rows_to_monthly([{"stck_bsop_date": "20140430", "stck_clpr": "0"},
                         {"stck_bsop_date": "", "stck_clpr": "1"},
                         {"nope": 1}, {"stck_bsop_date": "2014043", "stck_clpr": "5"}])
    ok.append(("③ 0원·빈날짜·불량행 제거", m == {}))
    ok.append(("④ 빈 응답 → 빈 dict", rows_to_monthly(None) == {} and rows_to_monthly([]) == {}))

    ok.append(("⑤ 청크 절약: 최초2012 → 2012~2015만", chunk_plan("2012-03") == [(2012, 2015)]))
    ok.append(("⑥ 청크: 최초1998 → 전 청크", chunk_plan("1998-07") == CHUNKS))
    ok.append(("⑦ 청크: 최초월 불명 → 전 청크(안전측)", chunk_plan("") == CHUNKS))
    ok.append(("⑧ 청크 경계: 최초 2008-01 → 2008~ 이후만",
               chunk_plan("2008-01") == [(2008, 2011), (2012, 2015)]))

    cs = [f"{i:06d}" for i in range(100)]
    s = sample_spread(cs, 10)
    ok.append(("⑨ 표본이 앞쪽으로 쏠리지 않음", s[0] == "000000" and s[-1] >= "000090" and len(s) == 10))
    ok.append(("⑩ 표본 재현성", sample_spread(cs, 10) == s))
    ok.append(("⑪ n≥len → 전체", sample_spread(cs, 500) == cs))

    ro, hits = source_is_read_only()
    ok.append((f"⑫ 소스에 주문 문자열 없음 {hits or ''}", ro))

    import tempfile
    tp = os.path.join(tempfile.mkdtemp(), "fake.py")
    open(tp, "w", encoding="utf-8").write("t='TT" + "TC0802U'\n")
    bad, bh = source_is_read_only(tp)
    ok.append(("⑬ 음성대조: 주문 문자열 있는 파일은 반드시 걸린다", (not bad) and bool(bh)))

    # 카나리 판정 — 판정 로직의 '복사본'이 아니라 run_canary 그 자체를 검사한다(2026-07-28 개정).
    def stub(mode):
        def chart(host, tok, keys, code, y0, y1, period="M", adj="0", timeout=10):
            want = {c: (a, r) for c, _, _, _, _, a, r in CANARY}[code]
            ym = {c: y for c, _, _, _, y, _, _ in CANARY}[code]
            d = ym.replace("-", "") + "30"
            v = want[0] if adj == "0" else want[1]
            if mode == "ok":
                return [{"stck_bsop_date": d, "stck_clpr": str(v)}], None
            if mode == "missing_adj":
                return ([] if adj == "0" else [{"stck_bsop_date": d, "stck_clpr": str(v)}]), None
            if mode == "mismatch_adj":
                return [{"stck_bsop_date": d, "stck_clpr": str(v * 7)}], None
            if mode == "err_adj_mismatch_raw":
                if adj == "0":
                    return None, "HTTP 500 stub"
                return [{"stck_bsop_date": d, "stck_clpr": str(v * 7)}], None
            raise AssertionError(mode)
        return chart

    def verdict_of(mode):
        v, _ = run_canary("stub", "tok", {"app_key": "a", "app_secret": "b"},
                          chart=stub(mode), sleep_s=0)
        return v
    ok.append(("⑭ 카나리 정상 → pass", verdict_of("ok") == "pass"))
    ok.append(("⑮ 카나리 부재 → 검증 불가(pass 아님)", verdict_of("missing_adj") == "unverifiable"))
    ok.append(("⑯ 카나리 불일치 → fail", verdict_of("mismatch_adj") == "fail"))
    ok.append(("⑰ 오류가 불일치를 덮지 않는다", verdict_of("err_adj_mismatch_raw") == "fail"))

    # ⑱~㉑ 접착부 계약 — 2026-07-28 실패한 바로 그 자리.
    K = {"app_key": "AAA", "app_secret": "BBB"}
    keys, tok, desc, why = prepare("h", lambda: (K, ".kis_key (2줄 평문)"),
                                   lambda h, k: ("TOKEN", "캐시"))
    ok.append(("⑱ (값,출처) 튜플 반환을 정확히 풀어낸다", keys is K and tok == "TOKEN" and why is None))

    _, _, _, why2 = prepare("h", lambda: (None, "키 없음"), lambda h, k: ("T", "캐시"))
    ok.append(("⑲ 키 없음 → 수집 진입 차단", why2 == "키 없음"))

    _, tok3, _, why3 = prepare("h", lambda: (K, "src"), lambda h, k: (None, "발급실패"))
    ok.append(("⑳ 토큰 실패 → 수집 진입 차단", tok3 is None and why3 == "토큰 실패"))

    ok.append(("㉑ 키 값은 마스킹만(원문 노출 금지)", "AAA" not in mask(K["app_key"])))

    # ㉒ 카나리 셀 자체가 판별력을 갖는지 — 064550 사고(raw==adj)를 구조적으로 막는다.
    disc = all(r / a >= 1.5 for _, _, _, _, _, a, r in CANARY)
    ok.append((f"㉒ 카나리 셀 판별력 (raw/adj ≥ 1.5): " +
               " · ".join(f"{c}×{r/a:.1f}" for c, _, _, _, _, a, r in CANARY), disc))

    # ㉓㉔ 네트워크 예외 내성 — 2026-07-28 600/2,444 크래시를 구조적으로 막는다.
    #     kis_chart 가 err 를 "돌려주는" 경로만 잡고 "던지는" 경로를 놓쳤던 자리.
    global NET_BACKOFF
    _bk = NET_BACKOFF
    NET_BACKOFF = 0.0
    try:
        class _Boom(Exception):
            pass

        def _always_raise(*a, **k):
            raise _Boom("Connection aborted / ConnectionResetError(10054)")

        crashed = False
        try:
            r, c, e = collect_one("h", "t", {}, "005930", "KOSPI", "2012-01", 0.0,
                                  chart=_always_raise)
        except Exception:
            crashed = True
            r = c = e = None
        ok.append(("㉓ 던져진 네트워크 예외가 프로세스를 죽이지 않는다",
                   (not crashed) and r is None and isinstance(e, str) and "_Boom" in e))
        ok.append((f"㉔ 예외도 재시도 대상 (NET_TRIES={NET_TRIES}회 소진 후 실패 처리)",
                   (not crashed) and c == NET_TRIES))

        # 한 번 실패하고 두 번째에 성공하면 정상 수집돼야 한다(재시도가 실제로 동작).
        st = {"n": 0}

        def _flaky(*a, **k):
            st["n"] += 1
            if st["n"] == 1:
                raise _Boom("일시적 끊김")
            return [{"stck_bsop_date": "20121228", "stck_clpr": "1000"}], None

        r2, c2, e2 = collect_one("h", "t", {}, "005930", "KOSPI", "2012-01", 0.0,
                                 chart=_flaky)
        ok.append(("㉕ 예외 후 재시도로 복구된다",
                   e2 is None and c2 == 2 and r2 == [["005930", "2012-12", "1000", "KOSPI"]]))
    finally:
        NET_BACKOFF = _bk

    npass = sum(1 for _, b in ok if b)
    for name, b in ok:
        print(f"  {'PASS' if b else 'FAIL'}  {name}")
    print(f"\n셀프테스트 {npass}/{len(ok)} " + ("PASS" if npass == len(ok) else "✗ FAIL"))
    return 0 if npass == len(ok) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--canary", dest="canary_only", action="store_true", help="카나리만 확인하고 종료")
    ap.add_argument("--report", action="store_true", help="이미 수집된 산출물 요약만")
    ap.add_argument("--sample", type=int, default=0, help="코드순 등간격 표본 N개만")
    ap.add_argument("--sleep", type=float, default=0.25, help="콜 간 대기(초)")
    ap.add_argument("--paper", action="store_true", help="모의 호스트 (기본은 실전·조회 전용)")
    ap.add_argument("--force-no-canary", action="store_true",
                    help="카나리 실패에도 진행 (산출물은 검증되지 않은 데이터로 표기됨)")
    a = ap.parse_args()
    if a.selftest:
        return selftest()
    if a.report:
        report(); return 0
    return run(a)


if __name__ == "__main__":
    sys.exit(main())
