#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""fetch_수급확장_pykrx.py — 수급 오버레이 §3 표본확대용 수집 (★PC 전용).

목적: 딥밸류+기관매집 오버레이의 §3 재검증을 위해 두 축으로 표본을 넓힌다.
  (A) 유니버스 확대 : 기존 flow는 top-550(200 KOSPI+350 KOSDAQ)뿐 → 딥밸류 1,413개 중 1,120개가
                     flow 없어서 수급코호트서 탈락. 종목재무_KRX 전체(=백테 유니버스)로 확대.
  (B) 기간 확대     : 기존 flow 2019-01~ → --start 2002-01 등으로 소급(가능한 만큼).
  (C) 공매도잔고    : '순매수 = 숏커버(대차상환)일 수 있다'는 정교화용. 월말 공매도잔고(수량·비중) 수집.
                     → 정교화 스크립트가 Δ공매도잔고로 실매집 vs 숏커버동반을 분리 검증.

★왜 PC 전용: 이 클라우드/샌드박스는 KRX(data.krx.co.kr) 차단(403). 검증 완료.
  → pykrx 수집은 진우 PC에서만 가능. (pip install pykrx pandas)

정직/근거 원칙:
  · 없는 데이터로 진행 금지. 공매도잔고는 KRX가 주는 기간만 수집되고, 종목·기간별 결측은
    그대로 비운다(0으로 위조하지 않음). 실제 커버리지는 수집 후 로그·정교화 스크립트가 보고.
  · 순매수는 '거래대금(원)' 월합계(기존 kospi_flow_monthly.csv와 동일 정의: 일별 순매수 합).
  · 공매도잔고는 월말(그 달 마지막 관측일)의 잔고수량·비중 스냅샷.

속도: 순매수는 per-월 대량조회(get_market_net_purchases_of_equities_by_ticker, 전 종목 2콜/월)로
      per-종목(3865콜) 대비 수십배 빠름. 공매도는 per-종목 연단위(타깃코드 소수 권장).

출력(기존 스키마 유지 + 신규):
  · flow_ext_monthly_{KOSPI,KOSDAQ}.csv : code,date,foreign_net,inst_net   (기존 flow와 concat 가능)
  · short_balance_monthly_{KOSPI,KOSDAQ}.csv : code,date,short_qty,short_ratio
  · _fetch_flow_ckpt_{market}.txt (완료 월) · _fetch_short_ckpt_{market}.txt (완료 코드) : 재개용

사용(PC):
  pip install pykrx pandas
  python fetch_수급확장_pykrx.py --market KOSPI --start 2002-01-02        # 전체 유니버스·전체기간
  python fetch_수급확장_pykrx.py --market KOSDAQ --start 2002-01-02
  python fetch_수급확장_pykrx.py --market KOSPI --no-short                 # 순매수만
  python fetch_수급확장_pykrx.py --market KOSPI --codes _codes.txt --start 2015-01-02
  # 중단되면 같은 명령 재실행 → 체크포인트부터 이어감
  이후: python 검증_수급오버레이_정교화.py
"""
import argparse, csv, os, sys, datetime as dt, time
BASE = os.path.dirname(os.path.abspath(__file__))

def log(*a):
    print(*a); sys.stdout.flush()

import contextlib, io
def _quiet(fn, *a):
    """pykrx 내부 print('Error occurred...') 억제. 예외는 상위에서 처리."""
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf), contextlib.redirect_stderr(buf):
        return fn(*a)

def universe_from_fundamentals(market):
    """종목재무_KRX_{market}.csv 의 전체 코드(=백테 유니버스). 없으면 빈 리스트."""
    p = os.path.join(BASE, f"종목재무_KRX_{market}.csv")
    codes = set()
    if os.path.exists(p):
        with open(p, encoding="utf-8-sig", newline="") as f:
            rd = csv.reader(f); next(rd, None)
            for r in rd:
                if len(r) >= 2 and r[1].strip():
                    codes.add(r[1].strip().zfill(6))
    return sorted(codes)

def load_codes(a):
    if a.codes:
        p = a.codes if os.path.isabs(a.codes) else os.path.join(BASE, a.codes)
        return [ln.strip().zfill(6) for ln in open(p, encoding="utf-8") if ln.strip() and not ln.startswith("#")]
    codes = universe_from_fundamentals(a.market)
    if not codes:
        sys.exit(f"종목재무_KRX_{a.market}.csv 없음 → --codes 파일을 주세요")
    if a.top:  # 상위 N만(테스트용). 시총순 정렬 소스 있으면 사용.
        codes = codes[:a.top]
    return codes

def read_ckpt(path):
    if os.path.exists(path):
        return set(ln.strip() for ln in open(path, encoding="utf-8") if ln.strip())
    return set()

def append_ckpt(path, code):
    with open(path, "a", encoding="utf-8") as f:
        f.write(code + "\n")

def append_rows(path, header, rows):
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        if new: w.writerow(header)
        w.writerows(rows)

import calendar, datetime as _dt
def month_range(start, end):
    """'YYYYMMDD' start,end → yield (ym, fs, fe) 월단위. fs/fe=그 달 1일/말일."""
    y, m = int(start[:4]), int(start[4:6]); ey, em = int(end[:4]), int(end[4:6])
    while (y, m) <= (ey, em):
        last = calendar.monthrange(y, m)[1]
        yield f"{y}-{m:02d}", f"{y}{m:02d}01", f"{y}{m:02d}{last:02d}"
        m += 1
        if m > 12: m = 1; y += 1

def week_range(start, end):
    """'YYYYMMDD' → yield (라벨=주말일 'YYYY-MM-DD', fs, fe). 월요일~일요일 주. 라벨=주 종료(일)."""
    d0 = _dt.date(int(start[:4]), int(start[4:6]), int(start[6:8]))
    d1 = _dt.date(int(end[:4]), int(end[4:6]), int(end[6:8]))
    cur = d0 - _dt.timedelta(days=d0.weekday())  # 그 주 월요일
    while cur <= d1:
        wend = cur + _dt.timedelta(days=6)  # 일요일
        fs = max(cur, d0); fe = min(wend, d1)
        yield wend.isoformat(), fs.strftime("%Y%m%d"), fe.strftime("%Y%m%d")
        cur += _dt.timedelta(days=7)

def _netval_map(stock, fs, fe, market, investor):
    """월 기간 순매수거래대금 {code: 원} — 전 종목 1회 호출(대량·빠름)."""
    try:
        df = _quiet(stock.get_market_net_purchases_of_equities_by_ticker, fs, fe, market, investor)
    except Exception:
        return None
    if df is None or len(df) == 0 or "순매수거래대금" not in df.columns:
        return {}
    out = {}
    for tk in df.index:
        try: out[str(tk).zfill(6)] = float(df["순매수거래대금"].loc[tk])
        except Exception: continue
    return out

def collect_flow_month(stock, ym, fs, fe, market):
    """한 달, 전 종목 외국인·기관 순매수거래대금 → [(code,월말date,foreign_net,inst_net)].
    ★per-종목(3865콜) 대신 per-월×투자자(2콜)로 전 종목 수집 → 수십배 빠름.
    반환 None=월 조회 실패(재시도 위해 미체크포인트). {}/[]=성공(데이터 없음)."""
    fmap = _netval_map(stock, fs, fe, market, "외국인")
    imap = _netval_map(stock, fs, fe, market, "기관합계")
    if fmap is None and imap is None:
        return None  # 둘 다 실패 → 이 달 재시도
    fmap = fmap or {}; imap = imap or {}
    date = f"{fe[:4]}-{fe[4:6]}-{fe[6:8]}"  # 기간 종료일(월말 또는 주말)
    codes = set(fmap) | set(imap)
    return [(c, date, fmap.get(c, 0.0), imap.get(c, 0.0)) for c in codes]

# 공매도 잔고 함수 후보(잔고 제공). 이 pykrx/환경에서 실제로 되는 걸 런타임에 자동선택.
#   (함수명, 잔고수량컬럼, 비중컬럼|None)
_SHORT_CANDS = [
    ("get_shorting_balance_by_date", "공매도잔고", "비중"),
    ("get_shorting_status_by_date", "잔고수량", None),
]
_SHORT_FN = None   # None=미탐지 / (name,qcol,rcol)=사용중 / False=사용불가
_PROBE_TK = "005930"  # 탐지용 유동종목(항상 데이터 있음)

def _parse_short(df, qcol, rcol, last):
    if df is None or len(df) == 0 or qcol not in df.columns: return False
    got = False
    for idx in df.index:
        d = idx.strftime("%Y-%m-%d") if hasattr(idx, "strftime") else str(idx)[:10]; ym = d[:7]
        try: q = float(df[qcol].loc[idx])
        except Exception: continue
        try: rr = float(df[rcol].loc[idx]) if rcol else ""
        except Exception: rr = ""
        cur = last.get(ym)
        if cur is None or d > cur[0]: last[ym] = (d, q, rr); got = True
    return got

def probe_short(stock, end):
    """되는 공매도함수를 유동종목 최근 1년으로 1회 탐지·고정.
    ★KRX 공매도 엔드포인트는 장기범위(예: 10년)에 'output' 에러 → 연단위 호출 필수."""
    global _SHORT_FN
    Y = int(end[:4]); fs = f"{Y-1}0101"
    for name, qcol, rcol in _SHORT_CANDS:
        fn = getattr(stock, name, None)
        if fn is None: continue
        try: df = _quiet(fn, fs, end, _PROBE_TK)
        except Exception: continue
        if df is not None and len(df) > 0 and qcol in df.columns:
            _SHORT_FN = (name, qcol, rcol)
            log(f"  [공매도] 함수 자동선택: {name} (잔고={qcol}, 비중={rcol or '없음→수량Δ대체'}) · 연단위 수집")
            return True
    _SHORT_FN = False
    log("  [공매도] ⚠ 되는 공매도함수 없음 → short 비활성(순매수만). 숏커버 정교화 불가.")
    return False

def collect_short(stock, code, sstart, end):
    """공매도잔고 월말 스냅샷 → [(code,월말date,short_qty,short_ratio)].
    ★연단위로 호출(장기범위 'output' 회피). 없는 연도/종목은 조용히 스킵·0 위조 안 함."""
    if _SHORT_FN is False: return []
    name, qcol, rcol = _SHORT_FN
    fn = getattr(stock, name)
    last = {}
    y0, y1 = int(sstart[:4]), int(end[:4])
    for yr in range(y0, y1 + 1):
        fs = f"{yr}0101" if yr > y0 else sstart
        fe = f"{yr}1231" if yr < y1 else end
        try:
            _parse_short(_quiet(fn, fs, fe, code), qcol, rcol, last)
        except Exception:
            continue
    return [(code, last[ym][0], last[ym][1], last[ym][2]) for ym in sorted(last)]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", choices=["KOSPI", "KOSDAQ"], required=True)
    ap.add_argument("--codes", default=None, help="코드 파일(1줄1코드). 없으면 종목재무 전체 유니버스")
    ap.add_argument("--top", type=int, default=0, help="상위 N만(0=전체·테스트용)")
    ap.add_argument("--start", default="2002-01-02")
    ap.add_argument("--end", default=None)
    ap.add_argument("--no-short", action="store_true", help="공매도잔고 수집 생략(순매수만·빠름)")
    ap.add_argument("--no-flow", action="store_true", help="순매수 수집 생략(공매도만·flow 이미 받았을 때)")
    ap.add_argument("--flow-freq", choices=["monthly", "weekly"], default="monthly",
                    help="순매수 그레인. weekly=주봉 오버레이용(주당 2콜). 월봉과 별도 파일.")
    ap.add_argument("--short-start", default="2016-06-30",
                    help="공매도잔고 수집 시작(KRX 공매도잔고 공시 시행 ~2016-06-30). 옛 기간은 미제공.")
    ap.add_argument("--sleep", type=float, default=0.0, help="종목당 대기(초)·레이트리밋 방지")
    a = ap.parse_args()
    try:
        from pykrx import stock
    except ImportError:
        sys.exit("pykrx 미설치 → pip install pykrx")
    if a.no_flow and a.no_short: sys.exit("--no-flow 와 --no-short 를 동시에 줄 수 없음")
    start = a.start.replace("-", ""); end = (a.end or dt.date.today().isoformat()).replace("-", "")
    sstart = a.short_start.replace("-", "")
    flow_out = os.path.join(BASE, f"flow_ext_monthly_{a.market}.csv")
    short_out = os.path.join(BASE, f"short_balance_monthly_{a.market}.csv")
    univ = set(load_codes(a))  # 백테 유니버스로 flow 출력 제한(ETF/스팩 등 제외)
    t0 = time.time()

    # ── 순매수(flow): per-기간 대량수집(전 종목 2콜/기간) — 빠름. 월봉 또는 주봉 ──
    if not a.no_flow:
        weekly = (a.flow_freq == "weekly")
        freqtag = "weekly" if weekly else "monthly"
        flow_out = os.path.join(BASE, f"flow_ext_{freqtag}_{a.market}.csv")
        unit = "주" if weekly else "월"
        fckpt = os.path.join(BASE, f"_fetch_flow{'W' if weekly else ''}_ckpt_{a.market}.txt")
        fdone = read_ckpt(fckpt)
        periods = [t for t in (week_range if weekly else month_range)(start, end) if t[0] not in fdone]
        log(f"[{a.market}] 순매수 {unit}수집({freqtag}) | 유니버스 {len(univ)}종 | 남은 {unit} {len(periods)} | {a.start}~{a.end or 'today'}")
        nf = 0
        for i, (lbl, fs, fe) in enumerate(periods):
            rows = collect_flow_month(stock, lbl, fs, fe, a.market)  # lbl=기간라벨(월:YYYY-MM/주:YYYY-MM-DD)
            if rows is None:
                log(f"  ! {lbl} 조회 실패 → 건너뜀(재실행 시 재시도)"); continue
            rows = [r for r in rows if r[0] in univ]
            if rows: append_rows(flow_out, ["code", "date", "foreign_net", "inst_net"], rows); nf += len(rows)
            append_ckpt(fckpt, lbl)
            if a.sleep: time.sleep(a.sleep)
            if (i + 1) % (26 if weekly else 12) == 0:
                el = time.time() - t0; rate = (i + 1) / el if el else 0
                eta = (len(periods) - i - 1) / rate / 60 if rate else 0
                log(f"  ...{i+1}/{len(periods)}{unit} | flow행 {nf} | {rate:.1f}{unit}/s | ETA {eta:.0f}분")
        log(f"완료 [{a.market}] 순매수 flow행 {nf} → {os.path.basename(flow_out)}")

    # ── 공매도잔고(short): per-종목 연단위(타깃코드 소수 권장) ──
    if not a.no_short:
        sckpt = os.path.join(BASE, f"_fetch_short_ckpt_{a.market}.txt")
        sdone = read_ckpt(sckpt)
        codes = [c for c in load_codes(a) if c not in sdone]
        log(f"[{a.market}] 공매도 종목수집 | 남은 {len(codes)}종 | {a.short_start}~ (연단위)")
        probe_short(stock, end)
        ns = 0; t1 = time.time()
        for i, c in enumerate(codes):
            sr = collect_short(stock, c, sstart, end)
            if sr: append_rows(short_out, ["code", "date", "short_qty", "short_ratio"], sr); ns += len(sr)
            append_ckpt(sckpt, c)
            if a.sleep: time.sleep(a.sleep)
            if (i + 1) % 25 == 0:
                el = time.time() - t1; rate = (i + 1) / el if el else 0
                eta = (len(codes) - i - 1) / rate / 60 if rate else 0
                log(f"  ...{i+1}/{len(codes)}종 | 공매도행 {ns} | {rate:.1f}종/s | ETA {eta:.0f}분")
        log(f"완료 [{a.market}] 공매도행 {ns} → {os.path.basename(short_out)}")

    log("다음: python 검증_수급오버레이_정교화.py")

if __name__ == "__main__":
    main()
