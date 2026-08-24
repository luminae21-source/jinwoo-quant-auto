#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""kis_coverage_probe.py — 본수집 **전에** 밀도부터 잰다: 코드별 '최초 관측 연월'만 뽑는 프로브

왜 이 순서인가(2026-07-27)
  broker_adj_smoke 로 "KIS 실전 도메인은 1996년까지 응답한다"는 것까지 확인했다.
  하지만 그건 **삼성전자 한 종목**의 이야기다. 5,200 코드 전부가 1996년까지 촘촘한지,
  아니면 대형주 몇 개만 옛날 데이터가 있고 나머지는 2010년대부터인지는 아직 모른다.
  밀도를 모르는 채로 본수집(수만 콜)을 돌리면, 몇 시간 쓰고 나서 "쓸 수 있는 창은
  결국 2015~2026이었다"는 결론을 만날 수 있다. 그래서 **재기 전에 재는** 순서로 간다.

  결과를 미리 정해두지 않는다.
    · 촘촘하면  → 본수집 → 2008·2011 포함 30년 창으로 크기 백테 재실행(MDD 정직해짐)
    · 희박하면  → 그 사실 자체를 백서에 박제하고 창은 2015~2026으로 남긴다
  둘 다 정당한 결론이고, 어느 쪽이 나오든 숫자를 그쪽으로 맞추지 않는다.

무엇을 하나 / 안 하나
  한다   : 조회(기간별시세)만. 코드당 오래된 4년 청크부터 순서대로 때려서
           **행이 처음 나오는 청크**를 찾고 그 안의 최소 날짜를 기록한다(코드당 1~6콜).
  안 한다: 주문·잔고·자금이동 일절 없음(--selftest 가 소스에서 주문 문자열 부재를 검사한다).
           가격 데이터를 저장하지 않는다 — 이 프로브의 산출물은 '연월'과 '행수'뿐이다.
           키를 화면에 찍지 않고, KIS 자기 엔드포인트 외 어디에도 보내지 않는다.

실행 (진우 PC · PowerShell)
  cd C:\Users\긍정적인_삶의자세\Desktop\진우퀀트
  py 데이터수리\kis_coverage_probe.py --selftest          # 네트워크 0 · 로직만 검증 (먼저 이것부터)
  py 데이터수리\kis_coverage_probe.py --limit 30          # 30개만 맛보기 (2~3분)
  py 데이터수리\kis_coverage_probe.py                     # 전수 (중단해도 --resume 로 이어서)
  py 데이터수리\kis_coverage_probe.py --summary-only      # 이미 모은 CSV로 요약만 다시

산출
  kis_커버리지_프로브.csv   code,market,earliest_ym,latest_seen_ym,n_rows,calls,status,detail
  kis_커버리지_요약.csv     연도별 도달률 + 시총패널 대비 충족률
  ※ 프로브 CSV는 append 라 언제 끊겨도 이어서 돌릴 수 있다(기본 --resume 켜짐).

소요 예상: 5,200코드 × 평균 2~3콜 × sleep 0.35s ≈ 1.0~1.5시간. --limit 로 먼저 감을 잡을 것.
⚠️ 정보·검증용 · 투자자문 아님. 실집행은 이 스크립트 범위 밖.
"""
import os, sys, csv, time, json, argparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 키 취급 코드를 **두 벌 만들지 않는다**. 스모크에서 검증된 로더/호출기를 그대로 쓴다.
from broker_adj_smoke import (KIS_LIVE, KIS_PAPER, kis_token, kis_chart,
                              load_kis_keys, mask, find_file)

OUT = os.path.join(HERE, "kis_커버리지_프로브.csv")
SUM = os.path.join(HERE, "kis_커버리지_요약.csv")
HDR = ["code", "market", "earliest_ym", "latest_seen_ym", "n_rows", "calls", "status", "detail"]

# 오래된 청크부터. 월봉이라 4년=48행 → KIS 응답 상한(100행) 안쪽이라 잘림 걱정 없다.
CHUNKS = [(1996, 1999), (2000, 2003), (2004, 2007), (2008, 2011), (2012, 2015)]
# 청크 전부 비었을 때 "코드가 죽은 건가, 그냥 신규상장인가"를 가르는 확인용 1콜
ALIVE_CHUNK = (2020, 2026)          # 84개월 ≤ 100행


# ────────────────────────────── 순수 로직(셀프테스트 대상) ──────────────────────────────
def chunk_plan(chunks=CHUNKS):
    """청크가 1996~2015를 빈틈·중복 없이 덮는지, 각 청크가 100행 이하인지."""
    ok, msg = True, []
    if chunks[0][0] != 1996 or chunks[-1][1] != 2015:
        ok = False; msg.append("범위가 1996~2015가 아님")
    for a, b in chunks:
        if (b - a + 1) * 12 > 100:
            ok = False; msg.append(f"{a}~{b} 는 {(b-a+1)*12}개월 — 응답 상한 초과 위험")
    for (a1, b1), (a2, b2) in zip(chunks, chunks[1:]):
        if a2 != b1 + 1:
            ok = False; msg.append(f"{b1}과 {a2} 사이 빈틈/중복")
    return ok, "; ".join(msg) or "연속·상한 OK"


def rows_to_yms(rows):
    """KIS output2 → 정렬된 'YYYY-MM' 리스트. 날짜 없는 행은 버린다."""
    yms = set()
    for r in rows or []:
        d = str(r.get("stck_bsop_date") or "")
        if len(d) >= 6 and d[:6].isdigit():
            yms.add(f"{d[:4]}-{d[4:6]}")
    return sorted(yms)


def summarize(recs, panel_first=None):
    """프로브 결과 → 연도별 도달률. panel_first: {code: 'YYYY-MM'} (시총패널 최초 관측월).

    두 가지를 따로 본다.
      ① 도달률   — 해당 연도 이전에 KIS 데이터가 있는 코드 수 / 전체
      ② 충족률   — '시총패널이 그 코드가 그때 존재했다고 말하는' 경우 중 KIS도 주는 비율
         (①만 보면 '그 시절 상장도 안 한 종목'까지 분모에 들어가 밀도를 과소평가한다)
    """
    import collections
    rows, total = [], len(recs)
    got = {r["code"]: r.get("earliest_ym") or "" for r in recs}
    for y in (1996, 2000, 2004, 2008, 2011, 2013, 2015):
        cut = f"{y}-12"
        reach = sum(1 for v in got.values() if v and v <= cut)
        d = {"기준": f"{y}년말 이전 데이터 보유", "코드수": reach, "전체": total,
             "도달률": round(reach / total * 100, 1) if total else 0.0}
        if panel_first:
            elig = [c for c, f in panel_first.items() if c in got and f <= cut]
            hit = sum(1 for c in elig if got[c] and got[c] <= cut)
            d["패널상_존재"] = len(elig)
            d["충족률"] = round(hit / len(elig) * 100, 1) if elig else None
        rows.append(d)
    st = collections.Counter(r.get("status", "") for r in recs)
    return rows, dict(st)


def sample_spread(codes, n):
    """코드순 등간격 추출. 난수 없이 재현 가능하고, 앞부분(옛 KOSPI)에 쏠리지 않는다.

    왜 필요한가: `--limit 30` 첫 실행이 80%/1996년이라는 낙관적 그림을 줬는데,
    그건 정렬된 앞 30개 = 000020·000040… 즉 **가장 오래된 KOSPI 코드들**이었다.
    표본이 답을 향해 편향되면 그 측정은 무효다.
    """
    if n <= 0 or n >= len(codes):
        return list(codes)
    step = len(codes) / n
    return [codes[int(i * step)] for i in range(n)]


def source_is_read_only(path=None):
    """이 파일에 주문 계열 문자열이 없음을 스스로 검사한다.

    검사어를 소스에 그대로 쓰면 자기 자신에 걸리므로 조각으로 조립한다.
    (검사가 검사 대상을 오염시키면 그건 검사가 아니다 — 스모크에서 배운 것.)
    """
    path = path or os.path.abspath(__file__)
    src = open(path, encoding="utf-8").read()
    banned = ["TT" + "TC0802U", "TT" + "TC0801U", "VT" + "TC0802U",
              "order" + "-cash", "trading/" + "order", "inquire-" + "balance"]
    hits = [b for b in banned if b in src]
    return (not hits), hits


# ────────────────────────────── 수집부 ──────────────────────────────
def load_universe(markets, verbose=True):
    """유니버스 = 월봉캐시(full ∪ adj) ∪ 시총패널 코드. 상폐 포함. 시장 라벨도 같이.

    ⚠️ 2026-07-27 정정(초판 버그): 초판은 `_adj` 캐시와 `종목시총_30년_backfill.csv` 만 봤다.
    진우 PC에는 backfill 파일이 없고(원본은 루트의 `종목시총_30년.csv`), `_adj` 캐시는
    **조정 수집에 성공한 종목만** 담고 있다. 그래서 유니버스가 3,801로 잘렸다 —
    빠진 코드가 하필 '수집 실패한 옛날/상폐 종목', 즉 **커버리지를 가장 알고 싶은 쪽**이었다.
    표본이 답을 향해 편향되면 그 측정은 무효다. → 원천을 여러 개 훑고, 무엇을 찾았는지 찍는다.
    """
    import pandas as pd
    lab, found = {}, []
    # ① 월봉캐시 full(미조정 포함·가장 넓음) → ② _adj (좁음). 앞의 것이 시장 라벨 우선.
    for tag in ("full", "adj"):
        for m in ["KOSPI", "KOSDAQ"]:
            p = find_file(f"_월봉종가캐시_{m}_{tag}.csv")
            if not p:
                continue
            c = pd.read_csv(p, usecols=["code"], dtype={"code": str})["code"].str.zfill(6)
            for x in c.unique():
                lab.setdefault(x, m)
            found.append(f"{os.path.basename(p)}({c.nunique():,})")
    # ③ 시총패널 — 시장 라벨은 없지만 코드는 가장 오래된 것까지 있다
    p, col = _panel_path()
    if p:
        c = pd.read_csv(p, usecols=["code"], dtype={"code": str})["code"].str.zfill(6)
        for x in c.unique():
            lab.setdefault(x, "UNK")
        found.append(f"{os.path.basename(p)}({c.nunique():,})")
    if verbose:
        print("  유니버스 원천: " + (" · ".join(found) if found else "❌ 없음"))
    codes = sorted(c for c, mk in lab.items() if markets == "ALL" or mk == markets or mk == "UNK")
    return codes, lab


def _panel_path():
    """시총패널 파일 탐색 → (경로, 연월컬럼). 이름/컬럼이 환경마다 달라서 둘 다 받는다."""
    for name, col in (("종목시총_30년_backfill.csv", "ym"), ("종목시총_30년.csv", "date")):
        p = find_file(name)
        if p:
            return p, col
    return None, None


def to_ym(v):
    """'1996-01-31' · '19960131' · '1996-01' → '1996-01'."""
    s = str(v).strip().replace("/", "-")
    if len(s) >= 7 and s[4] == "-":
        return s[:7]
    if len(s) >= 6 and s[:6].isdigit():
        return f"{s[:4]}-{s[4:6]}"
    return ""


def panel_first_map():
    """시총패널 기준 코드별 최초 관측월 — '있었어야 하는데 못 받은' 것을 세기 위한 대조군.

    없으면 None. 호출부는 None을 0으로 뭉개지 말 것 — **부재는 '충족률 0%'가 아니라 '검증 불가'다.**
    (ca_guard 카나리에서 세운 원칙과 같다.)
    """
    import pandas as pd
    p, col = _panel_path()
    if not p:
        return None
    mc = pd.read_csv(p, usecols=["code", col], dtype={"code": str})
    mc["code"] = mc["code"].str.zfill(6)
    mc["_ym"] = mc[col].map(to_ym)
    mc = mc[mc["_ym"] != ""]
    return mc.groupby("code")["_ym"].min().to_dict()


def read_done():
    if not os.path.exists(OUT):
        return set(), []
    recs = list(csv.DictReader(open(OUT, encoding="utf-8-sig")))
    return {r["code"] for r in recs}, recs


def probe_one(host, tok, keys, code, sleep_s, log):
    """코드 하나의 최초 관측월. 오래된 청크부터, 처음 행이 나오면 즉시 종료."""
    calls = 0
    for y0, y1 in CHUNKS:
        rows, err = None, None
        for attempt in range(3):
            rows, err = kis_chart(host, tok, keys, code, y0, y1, period="M", adj="0")
            calls += 1
            if err is None:
                break
            time.sleep(0.8 * (attempt + 1))       # 초당 건수 제한/일시 오류 백오프
        if err:
            return {"earliest_ym": "", "latest_seen_ym": "", "n_rows": 0, "calls": calls,
                    "status": "error", "detail": err[:90]}
        yms = rows_to_yms(rows)
        if yms:
            return {"earliest_ym": yms[0], "latest_seen_ym": yms[-1], "n_rows": len(yms),
                    "calls": calls, "status": "ok", "detail": f"{y0}~{y1}청크에서 최초"}
        time.sleep(sleep_s)
    # 1996~2015 전부 빈 응답 → 신규상장인지, 아예 못 받는 코드인지 1콜로 가른다
    rows, err = kis_chart(host, tok, keys, code, *ALIVE_CHUNK, period="M", adj="0")
    calls += 1
    yms = rows_to_yms(rows)
    if err:
        return {"earliest_ym": "", "latest_seen_ym": "", "n_rows": 0, "calls": calls,
                "status": "error", "detail": err[:90]}
    if yms:
        return {"earliest_ym": "", "latest_seen_ym": yms[-1], "n_rows": len(yms), "calls": calls,
                "status": "none_pre2016", "detail": "코드는 살아있음 · 2016년 이전 없음"}
    return {"earliest_ym": "", "latest_seen_ym": "", "n_rows": 0, "calls": calls,
            "status": "unreachable", "detail": "전 구간 빈 응답(상폐코드 미지원 추정)"}


def run(args):
    ro, hits = source_is_read_only()
    if not ro:
        print(f"❌ 소스에 주문 계열 문자열 발견 {hits} — 실행 중단"); sys.exit(2)

    keys, src = load_kis_keys()
    if not keys:
        print("  KIS 키 못 찾음 — .kis_key(2줄 평문) / .kis_key.json / 진우_KIS키.json / 환경변수 중 하나")
        sys.exit(1)
    print(f"  키 로드: {src} · app_key {mask(keys['app_key'])} (값은 찍지 않음)")

    host = KIS_LIVE if args.host == "live" else KIS_PAPER
    tok, how = kis_token(host, keys)
    print(f"  토큰 OK({how}) · {host.split('//')[1].split(':')[0]} · 조회 전용")

    codes, lab = load_universe(args.market)
    done, prev = (read_done() if args.resume else (set(), []))
    todo = [c for c in codes if c not in done]
    if args.sample:
        todo = sample_spread(todo, args.sample)
        print(f"  표본 {len(todo)}개 — 코드순 등간격 추출(옛코드·새코드 섞임)")
    elif args.limit:
        todo = todo[:args.limit]
        print("  ⚠️ --limit 은 코드 오름차순 앞부분 = 대부분 옛 KOSPI 코드다.")
        print("     맛보기 결과를 전체 밀도로 읽지 말 것. 고르게 보려면 --sample 을 쓸 것.")
    print(f"  유니버스 {len(codes):,} · 완료 {len(done):,} · 이번 실행 {len(todo):,}")
    print(f"  예상 콜 {len(todo)*2:,}~{len(todo)*6:,} · 예상 시간 "
          f"{len(todo)*2*args.sleep/60:.0f}~{len(todo)*6*args.sleep/60:.0f}분\n")

    new = not os.path.exists(OUT)
    f = open(OUT, "a", encoding="utf-8-sig", newline="")
    w = csv.DictWriter(f, fieldnames=HDR)
    if new:
        w.writeheader()
    t0, n_ok, n_old = time.time(), 0, 0
    for i, code in enumerate(todo):
        r = probe_one(host, tok, keys, code, args.sleep, print)
        r.update({"code": code, "market": lab.get(code, "UNK")})
        w.writerow({k: r.get(k, "") for k in HDR}); f.flush()
        if r["status"] == "ok":
            n_ok += 1
            if r["earliest_ym"] <= "2013-12":
                n_old += 1
        if (i + 1) % 25 == 0 or i + 1 == len(todo):
            el = time.time() - t0
            print(f"  {i+1}/{len(todo)} · 관측 {n_ok} · 2013년이전 도달 {n_old} · "
                  f"{el/60:.1f}분 (남은 예상 {el/(i+1)*(len(todo)-i-1)/60:.0f}분)")
        time.sleep(args.sleep)
    f.close()
    report()


def report():
    if not os.path.exists(OUT):
        print("프로브 CSV 없음 — 먼저 수집을 돌릴 것"); return
    recs = list(csv.DictReader(open(OUT, encoding="utf-8-sig")))
    pf = panel_first_map()
    rows, st = summarize(recs, pf)
    print(f"\n{'='*76}\n[커버리지 요약] 코드 {len(recs):,}개")
    if not pf:
        print("  ⚠️ 시총패널(종목시총_30년[_backfill].csv) 못 찾음 → 충족률 **검증 불가**(0%가 아님).")
        print("     도달률만으로 판정하지 말 것 — 그 시절 상장도 안 한 종목이 분모에 섞인다.")
    print("  상태:", " · ".join(f"{k} {v:,}" for k, v in sorted(st.items())))
    print(f"  {'기준':<26s}{'코드수':>8s}{'도달률':>9s}{'패널상존재':>12s}{'충족률':>9s}")
    for d in rows:
        f2 = f"{d['충족률']:.1f}%" if d.get("충족률") is not None else "-"
        print(f"  {d['기준']:<26s}{d['코드수']:>8,}{d['도달률']:>8.1f}%"
              f"{d.get('패널상_존재', 0):>12,}{f2:>9s}")
    import pandas as pd
    pd.DataFrame(rows).to_csv(SUM, index=False, encoding="utf-8-sig")
    print(f"\n저장 → {os.path.basename(SUM)} · 원자료 {os.path.basename(OUT)}")
    print("판정 기준(미리 정해둔 것은 결론이 아니라 '기준'이다):")
    print("  · 2008년말 충족률이 높다  → 본수집 진행 → 2008·2011 포함 30년 창으로 크기 백테 재실행")
    print("  · 낮다                    → 그 사실을 백서에 박제하고 창은 2015~2026 유지")
    print("⚠️ 이 프로브는 가격을 저장하지 않는다. '언제부터 있나'만 잰다.")


# ────────────────────────────── 셀프테스트(네트워크 0) ──────────────────────────────
def selftest():
    ok = []
    a, m = chunk_plan(); ok.append((f"① 청크 계획 연속·상한 ({m})", a))
    ok.append(("② 청크가 1996 시작", CHUNKS[0][0] == 1996))
    yms = rows_to_yms([{"stck_bsop_date": "19990331"}, {"stck_bsop_date": "19970228"},
                       {"stck_bsop_date": ""}, {"nope": 1}])
    ok.append(("③ 날짜 파싱·정렬·불량행 제거", yms == ["1997-02", "1999-03"]))
    ok.append(("④ 빈 응답 → 빈 리스트", rows_to_yms(None) == [] and rows_to_yms([]) == []))
    ro, hits = source_is_read_only()
    ok.append((f"⑤ 소스에 주문 문자열 없음 {hits or ''}", ro))
    # 검사기 자체가 작동하는지(음성 대조군) — 주문 문자열이 있는 가짜 파일은 반드시 걸려야 한다
    import tempfile
    tp = os.path.join(tempfile.mkdtemp(), "fake.py")
    open(tp, "w", encoding="utf-8").write("tr='TT" + "TC0802U'\n")
    ok.append(("⑥ 검사기 음성대조(가짜파일은 탐지)", source_is_read_only(tp)[0] is False))
    recs = [{"code": "000001", "earliest_ym": "1996-01", "status": "ok"},
            {"code": "000002", "earliest_ym": "2011-05", "status": "ok"},
            {"code": "000003", "earliest_ym": "", "status": "none_pre2016"},
            {"code": "000004", "earliest_ym": "", "status": "unreachable"}]
    pf = {"000001": "1996-01", "000002": "1996-01", "000003": "1996-01", "000004": "2005-03"}
    rows, st = summarize(recs, pf)
    r96 = next(r for r in rows if r["기준"].startswith("1996"))
    r11 = next(r for r in rows if r["기준"].startswith("2011"))
    # 1996년말: 도달 1/4=25%. 패널상 1996년에 존재했다는 코드는 1·2·3 → 충족 1/3=33.3%
    ok.append(("⑦ 도달률 계산", r96["도달률"] == 25.0))
    ok.append(("⑧ 충족률은 '존재했던 코드'만 분모", r96["패널상_존재"] == 3 and r96["충족률"] == 33.3))
    ok.append(("⑨ 2011년말 도달 2건", r11["코드수"] == 2))
    ok.append(("⑩ 상태 집계", st.get("ok") == 2 and st.get("unreachable") == 1))
    ok.append(("⑪ 산출 헤더에 가격 컬럼 없음",
               not any(k in HDR for k in ("close", "open", "price", "종가"))))
    # 2026-07-27 추가 — 초판이 PC에서 유니버스를 3,801로 잘라먹은 원인 두 가지를 고정한다
    ok.append(("⑫ 연월 정규화(date/ym/YYYYMMDD 혼용)",
               to_ym("1996-01-31") == "1996-01" and to_ym("19960131") == "1996-01"
               and to_ym("1996-01") == "1996-01" and to_ym("") == ""))
    rows2, _ = summarize(recs, None)
    ok.append(("⑬ 패널 부재 → 충족률은 0%가 아니라 '검증 불가'",
               all("충족률" not in r for r in rows2)))
    sp = sample_spread([f"{i:06d}" for i in range(1000)], 10)
    ok.append(("⑭ 등간격 표본이 앞쪽에 쏠리지 않음",
               len(sp) == 10 and sp[0] == "000000" and sp[-1] == "000900"
               and len(set(sp)) == 10))
    ok.append(("⑮ 표본수 ≥ 전체면 전체 반환", len(sample_spread(["a", "b"], 5)) == 2))
    p = sum(1 for _, v in ok if v)
    for k, v in ok:
        print(f"  {'✅' if v else '❌'} {k}")
    print(f"\nselftest: {p}/{len(ok)} (네트워크 0)")
    sys.exit(0 if p == len(ok) else 1)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--host", default="live", choices=["live", "paper"],
                    help="기간별시세는 모의 도메인에서 막히는 경우가 있어 기본 실전(조회 전용)")
    ap.add_argument("--market", default="ALL", choices=["ALL", "KOSPI", "KOSDAQ"])
    ap.add_argument("--sleep", type=float, default=0.35)
    ap.add_argument("--limit", type=int, default=0, help="앞에서 N개만 (편향 주의 — --sample 권장)")
    ap.add_argument("--sample", type=int, default=0, help="코드순 등간격 N개 (맛보기용 권장)")
    ap.add_argument("--no-resume", dest="resume", action="store_false")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--summary-only", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        selftest()
    elif a.summary_only:
        report()
    else:
        run(a)


if __name__ == "__main__":
    main()
