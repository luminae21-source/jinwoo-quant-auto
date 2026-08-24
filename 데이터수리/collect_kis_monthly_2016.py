# -*- coding: utf-8 -*-
r"""collect_kis_monthly_2016.py — [PC 실행] KIS 월봉 수정주가 2016~2026 수집 (조회 전용)

collect_kis_monthly.py(1996~2015 완주, 지문 8a8d7408)의 2016+ 확장판. 2026-07-28 신설.

왜 필요한가
────────────────────────────────────────────────────────────────────────────
2016+ 구간의 현행 월봉캐시(_월봉종가캐시_*.csv)는 **무수정 주가로 실측 확인**됐다:
  005930 2018-04 2,650,000 → 2018-05 50,700 (50:1 분할이 −98% 가격 점프로 잔존)
2014~2015 접합 겹침에서 1,067개 코드가 배율 r≠1 — 즉 2016 이후 CA를 가진 코드들이고,
이들의 2016+ 캐시 구간엔 가짜 점프가 있다. **접합만으로는 못 고치고 2016+ 재수집이 답이다.**
프로브 결론상 2010-12 이후 KIS 시점단면 커버리지는 100% — 이 구간은 KIS가 정답이다.

원본과 달라진 것 (그 외 로직·안전장치는 그대로 계승)
────────────────────────────────────────────────────────────────────────────
  ① CHUNKS = 2016~2019 / 2020~2023 / 2024~2026
  ② 대상 = 프로브가 아니라 **현행 월봉캐시에서 2016-01 이후 관측이 있는 전 코드**
     (2016+ 신규상장 포함 — 프로브는 pre-2016용이라 신규상장이 빠져 있다)
  ③ 산출물 분리: _월봉_KIS_adj_2016.csv / _kis월봉2016_ckpt.json / _kis월봉2016_실패.csv
  ④ 빈 응답 코드를 _kis월봉2016_실패.csv 에 status=empty 로 **기록**한다
     (2016+ 중도상폐 코드가 소리 없이 빠지면 생존편향이 재발한다 — 접합 단계에서 대조)
  ⑤ 카나리 동일(005930·098460, 2018-04) — 두 셀 모두 이 수집창 안에 있다

사용
────────────────────────────────────────────────────────────────────────────
  py 데이터수리\collect_kis_monthly_2016.py --selftest   # 네트워크 0
  py 데이터수리\collect_kis_monthly_2016.py --canary     # 카나리만 (4콜)
  py 데이터수리\collect_kis_monthly_2016.py --sample 40  # 등간격 표본 맛보기
  py 데이터수리\collect_kis_monthly_2016.py              # 본수집 (재개 자동 · 예상 ~2시간)
  py 데이터수리\collect_kis_monthly_2016.py --report     # 수집 결과 요약만
완주 후: md5·행수·코드수를 지문 json 으로 동결하고 백서에 기록 (v1 관례와 동일).
"""
import os, sys, csv, json, time, argparse

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)

from broker_adj_smoke import (KIS_LIVE, KIS_PAPER, kis_token, kis_chart,
                              load_kis_keys, mask)

OUT  = os.path.join(HERE, "_월봉_KIS_adj_2016.csv")
CKPT = os.path.join(HERE, "_kis월봉2016_ckpt.json")
FAIL = os.path.join(HERE, "_kis월봉2016_실패.csv")

HDR = ["code", "ym", "close", "market"]
CHUNKS = [(2016, 2019), (2020, 2023), (2024, 2026)]          # ← 변경 ①

NET_TRIES = 6
NET_BACKOFF = 2.0

# 카나리 — v1과 동일 셀. 두 CA(2018-05 분할·2021-04 분할) 모두 이 수집창 안이라 판별력 유지.
CANARY = [
    ("005930", "KOSPI",  2018, 2018, "2018-04", 53_000,   2_650_000),   # 50:1 (2018-05)
    ("098460", "KOSDAQ", 2018, 2018, "2018-04", 20_360,     101_800),   # 5:1 (2021-04-13)
]
CANARY_TOL = 0.03


# --------------------------------------------------------------------------- 원천
def source_is_read_only(path=None):
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


def load_targets(kospi_path=None, kosdaq_path=None):     # ← 변경 ②
    """현행 월봉캐시에서 2016-01 이후 관측이 있는 코드 → {code:(market, earliest_ym_2016이후)}.
    프로브 불사용 — 2016+ 신규상장 포함. 파일 없으면 None."""
    out = {}
    pairs = [("KOSPI", kospi_path or os.path.join(ROOT, "_월봉종가캐시_KOSPI.csv")),
             ("KOSDAQ", kosdaq_path or os.path.join(ROOT, "_월봉종가캐시_KOSDAQ.csv"))]
    seen_any = False
    for mkt, p in pairs:
        if not os.path.exists(p):
            continue
        seen_any = True
        with open(p, encoding="utf-8-sig") as f:
            for r in csv.DictReader(f):
                ym = r.get("ym") or ""
                if ym < "2016-01":
                    continue
                code = (r.get("code") or "").zfill(6)
                if not code:
                    continue
                cur = out.get(code)
                if cur is None or ym < cur[1]:
                    out[code] = (mkt, ym)
    return out if seen_any else None


def chunk_plan(earliest_ym):
    if not earliest_ym or len(earliest_ym) < 4 or not earliest_ym[:4].isdigit():
        return list(CHUNKS)
    y = int(earliest_ym[:4])
    return [(a, b) for (a, b) in CHUNKS if b >= y]


def sample_spread(codes, n):
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


# --------------------------------------------------------------------------- 카나리 (v1 그대로)
def run_canary(host, tok, keys, chart=None, sleep_s=0.25):
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


# --------------------------------------------------------------------------- 수집 (v1 그대로)
def collect_one(host, tok, keys, code, market, earliest_ym, sleep_s, chart=None):
    chart = chart or kis_chart
    got = {}
    calls = 0
    for (y0, y1) in chunk_plan(earliest_ym):
        last = ""
        for attempt in range(NET_TRIES):
            try:
                rows, err = chart(host, tok, keys, code, y0, y1,
                                  period="M", adj="0")
            except KeyboardInterrupt:
                raise
            except Exception as e:                      # noqa: BLE001
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

    targets = load_targets()
    if targets is None:
        print("✗ 현행 월봉캐시(_월봉종가캐시_*.csv)를 루트에서 못 찾음 — 대상 산출 불가")
        return 2
    print(f"대상(캐시 2016+ 관측 코드): {len(targets):,}개 — 신규상장 포함 · 프로브 불사용")

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

    codes = sorted(targets)
    if args.sample:
        codes = sample_spread(codes, args.sample)
        print(f"표본 {len(codes)}개 (코드순 등간격 · 재현 가능)")
    todo = [c for c in codes if c not in done]
    print(f"대상 {len(codes):,} · 완료 {len(codes) - len(todo):,} · 이번 실행 {len(todo):,}")

    t0 = time.time(); nrow = 0; nerr = 0; nempty = 0; ncalls = 0
    fo = open(OUT, "a", encoding="utf-8", newline="")
    ff = open(FAIL, "a", encoding="utf-8", newline="")
    w = csv.writer(fo); wf = csv.writer(ff)
    try:
        for i, code in enumerate(todo, 1):
            market, ey = targets[code]
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
                else:
                    # ← 변경 ④: 빈 응답은 기록한다 (2016+ 중도상폐 누락 = 생존편향 재발 방지)
                    wf.writerow([code, "empty", f"캐시 최초관측 {ey} · KIS 0행"]); ff.flush()
                    nempty += 1
                done.add(code)
            if i % 50 == 0 or i == len(todo):
                fo.flush()
                ck["done"] = sorted(done); save_ckpt(ck)
                el = (time.time() - t0) / 60.0
                rate = i / el if el > 0 else 0
                eta = (len(todo) - i) / rate if rate > 0 else 0
                print(f"  {i:,}/{len(todo):,} · 행 {nrow:,} · 콜 {ncalls:,} · 실패 {nerr} "
                      f"· 빈응답 {nempty} · {el:.1f}분 · ETA {eta:.0f}분")
    except KeyboardInterrupt:
        print("\n중단됨 — 체크포인트 저장. 다시 실행하면 이어받습니다.")
    finally:
        fo.flush(); fo.close(); ff.close()
        ck["done"] = sorted(done); save_ckpt(ck)

    print(f"\n완료: 행 {nrow:,} · 콜 {ncalls:,} · 실패 {nerr} · 빈응답 {nempty} · {(time.time()-t0)/60.0:.1f}분")
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
    print(f"\n[_월봉_KIS_adj_2016.csv] 행 {n:,} · 코드 {len(codes):,}")
    ys = sorted(byyear)
    if ys:
        print(f"  연도 {ys[0]}~{ys[-1]} · 연평균 행 {n/len(ys):,.0f}")
        print("  " + " ".join(f"{y}:{byyear[y]:,}" for y in ys))
    print("\n완주 후 순서: ① 빈응답(_kis월봉2016_실패.csv status=empty) 대조 — 중도상폐 코드는")
    print("   현행 캐시로 보충하되 CA 점프 검사 · ② md5 지문 동결 · ③ v1(1996~2015)과 병합 → 전 기간 백테.")


# --------------------------------------------------------------------------- 셀프테스트
def selftest():
    ok = []

    m = rows_to_monthly([{"stck_bsop_date": "20180430", "stck_clpr": "53000"},
                         {"stck_bsop_date": "20180330", "stck_clpr": "49000"}])
    ok.append(("① 월말 종가 파싱", m == {"2018-04": 53000.0, "2018-03": 49000.0}))

    m = rows_to_monthly([{"stck_bsop_date": "20180401", "stck_clpr": "100"},
                         {"stck_bsop_date": "20180430", "stck_clpr": "200"}])
    ok.append(("② 같은 달 중복 → 마지막 영업일 채택", m == {"2018-04": 200.0}))

    m = rows_to_monthly([{"stck_bsop_date": "20180430", "stck_clpr": "0"},
                         {"stck_bsop_date": "", "stck_clpr": "1"},
                         {"nope": 1}, {"stck_bsop_date": "2018043", "stck_clpr": "5"}])
    ok.append(("③ 0원·빈날짜·불량행 제거", m == {}))
    ok.append(("④ 빈 응답 → 빈 dict", rows_to_monthly(None) == {} and rows_to_monthly([]) == {}))

    ok.append(("⑤ 청크 절약: 최초2024 → 2024~2026만", chunk_plan("2024-03") == [(2024, 2026)]))
    ok.append(("⑥ 청크: 최초2016 → 전 청크", chunk_plan("2016-07") == CHUNKS))
    ok.append(("⑦ 청크: 최초월 불명 → 전 청크(안전측)", chunk_plan("") == CHUNKS))
    ok.append(("⑧ 청크 경계: 최초 2020-01 → 2020~ 이후만",
               chunk_plan("2020-01") == [(2020, 2023), (2024, 2026)]))

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

    K = {"app_key": "AAA", "app_secret": "BBB"}
    keys, tok, desc, why = prepare("h", lambda: (K, ".kis_key (2줄 평문)"),
                                   lambda h, k: ("TOKEN", "캐시"))
    ok.append(("⑱ (값,출처) 튜플 반환을 정확히 풀어낸다", keys is K and tok == "TOKEN" and why is None))

    _, _, _, why2 = prepare("h", lambda: (None, "키 없음"), lambda h, k: ("T", "캐시"))
    ok.append(("⑲ 키 없음 → 수집 진입 차단", why2 == "키 없음"))

    _, tok3, _, why3 = prepare("h", lambda: (K, "src"), lambda h, k: (None, "발급실패"))
    ok.append(("⑳ 토큰 실패 → 수집 진입 차단", tok3 is None and why3 == "토큰 실패"))

    ok.append(("㉑ 키 값은 마스킹만(원문 노출 금지)", "AAA" not in mask(K["app_key"])))

    disc = all(r / a >= 1.5 for _, _, _, _, _, a, r in CANARY)
    ok.append((f"㉒ 카나리 셀 판별력 (raw/adj ≥ 1.5): " +
               " · ".join(f"{c}×{r/a:.1f}" for c, _, _, _, _, a, r in CANARY), disc))

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
            r, c, e = collect_one("h", "t", {}, "005930", "KOSPI", "2016-01", 0.0,
                                  chart=_always_raise)
        except Exception:
            crashed = True
            r = c = e = None
        ok.append(("㉓ 던져진 네트워크 예외가 프로세스를 죽이지 않는다",
                   (not crashed) and r is None and isinstance(e, str) and "_Boom" in e))
        ok.append((f"㉔ 예외도 재시도 대상 (NET_TRIES={NET_TRIES}회 소진 후 실패 처리)",
                   (not crashed) and c == NET_TRIES))

        st = {"n": 0}

        def _flaky(*a, **k):
            st["n"] += 1
            if st["n"] == 1:
                raise _Boom("일시적 끊김")
            return [{"stck_bsop_date": "20161230", "stck_clpr": "1000"}], None

        # 단일 청크 조건(최초 2024)으로 검사 — 3청크면 콜 수가 4가 되어 계약이 달라진다.
        r2, c2, e2 = collect_one("h", "t", {}, "005930", "KOSPI", "2024-01", 0.0,
                                 chart=_flaky)
        ok.append(("㉕ 예외 후 재시도로 복구된다",
                   e2 is None and c2 == 2 and r2 == [["005930", "2016-12", "1000", "KOSPI"]]))
    finally:
        NET_BACKOFF = _bk

    # ㉖㉗ 2016+ 신설분 — 대상 산출 로직 (프로브 대체)
    import tempfile
    td = tempfile.mkdtemp()
    kp = os.path.join(td, "k.csv"); kd = os.path.join(td, "d.csv")
    open(kp, "w", encoding="utf-8").write(
        "code,ym,close\n005930,2015-12,50000\n005930,2016-01,48000\n000020,2014-01,9000\n")
    open(kd, "w", encoding="utf-8").write(
        "code,ym,close\n293490,2018-11,110000\n293490,2018-12,115000\n")
    t = load_targets(kp, kd)
    ok.append(("㉖ 대상: 2016+ 관측 코드만 (2015 이전만 있는 코드 제외)",
               set(t) == {"005930", "293490"} and t["005930"] == ("KOSPI", "2016-01")))
    ok.append(("㉗ 대상: 신규상장 최초관측월 보존 (청크 절약용)",
               t["293490"] == ("KOSDAQ", "2018-11")))

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
