#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
시장브리핑_생성.py — 시장 현황 브리핑 자동 생성 (공개 지표 사실 + 객관 해설)
[PC 실행] 데이터: yfinance(미국·환율·해외) + pykrx(국내 지수·수급). 실패 시 graceful(HTS 확인 표시).
산출: 시장브리핑_YYYYMMDD.md + 콘솔. 구조: ①국내 선물·옵션 ②미국장 ③주요 종목 ④종합 + 🔴HTS 확인.
원칙: 매수·매도 추천 아님. production·기존 산출물 무수정.
설치(자동 시도): pip install yfinance pykrx
사용: python 시장브리핑_생성.py | --selftest
"""
import sys, io, subprocess
from datetime import date, timedelta
from pathlib import Path
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
BASE = Path(__file__).parent.resolve()
try:
    import importlib.util as _il
    _sp = _il.spec_from_file_location("krx_openapi", BASE / "krx_openapi.py")
    KRX = _il.module_from_spec(_sp); _sp.loader.exec_module(KRX)
except Exception:
    KRX = None

# ===== 수동 1회 입력값 (변경 시만 갱신, 절대 임의 추정 금지) =====
BOK_BASE_RATE = 2.50   # 2026-05 기준, 한국은행 동결(8회 연속), 변경 시 갱신. None이면 "수동 확인".

# ---------- 금리 bp 해설 ----------
def d_yield_bp(bp):
    if bp is None: return ""
    if bp >= 8: return "금리 급등(성장주 부담)"
    if bp <= -8: return "금리 하락(성장주 우호)"
    return "금리 중립"

def yline(label, q):
    if q is None:
        return "- %-16s 🔴 데이터 미수신 → HTS 확인" % label
    last, prev, _ = q
    bp = (last - prev) * 100
    return "- %-16s %.3f (전일대비 %+.0fbp) · %s" % (label, last, bp, d_yield_bp(bp))

# ---------- 만기/이벤트 날짜계산 ----------
def second_thursday(y, m):
    d = date(y, m, 1)
    first_thu = d + timedelta(days=(3 - d.weekday()) % 7)
    return first_thu + timedelta(days=7)

def upcoming_expiries(today, n=3):
    out = []; y, m = today.year, today.month
    while len(out) < n:
        e = second_thursday(y, m)
        if e >= today:
            out.append((e, "분기 동시만기(네 마녀)" if m in (3, 6, 9, 12) else "옵션만기"))
        m += 1
        if m > 12: m = 1; y += 1
    return out

def next_weeklies(today, n=1):
    """다가오는 위클리옵션 만기 — 목요일물·월요일물 각 n개. 둘째목주 목요일은 정규(월물)와 합쳐짐 표기."""
    out = []
    for wd, label in [(0, "위클리옵션(월)"), (3, "위클리옵션(목)")]:
        d = today + timedelta(days=(wd - today.weekday()) % 7)
        cnt = 0
        while cnt < n:
            note = "(정규 만기주=합쳐짐)" if (wd == 3 and d == second_thursday(d.year, d.month)) else ""
            out.append((d, label, note, (d - today).days)); cnt += 1
            d += timedelta(days=7)
    out.sort(key=lambda x: x[0])
    return out

def post_expiry_check(today):
    """가장 가까운 정규 만기의 다음 영업일(금) = 만기 후 사후채점일. → (date, dday) or None."""
    exps = upcoming_expiries(today, n=1)
    if not exps:
        return None
    chk = exps[0][0] + timedelta(days=1)   # 둘째 목 → 금
    return (chk, (chk - today).days)

def next_fixed_events(today):
    """theme_calendar_fixed.csv에서 FOMC/금통위 다가오는 일정 → [(event, date, dday)]."""
    import csv
    p = BASE / "theme_calendar_fixed.csv"
    if not p.exists():
        return []
    out = []
    for r in csv.DictReader(open(p, encoding="utf-8-sig")):
        try:
            d = date.fromisoformat(str(r.get("date", ""))[:10])
        except Exception:
            continue
        ev = r.get("event", "")
        if ("FOMC" in ev or "금통위" in ev) and d >= today:
            out.append((ev, d, (d - today).days))
    out.sort(key=lambda x: x[1])
    return out

# ---------- 룰 기반 의사결정 테이블(임의해석 금지, 근거 명시) ----------
def decision_rules(tnx_bp, expiry_label, expiry_dday, event_label, event_dday):
    out = []
    if tnx_bp is None:
        out.append(("판단보류", "美10년 금리데이터 없음"))
    elif tnx_bp >= 8:
        out.append(("금리 급등 → 성장/기술주 부담", "美10년 %+.0fbp" % tnx_bp))
    elif tnx_bp <= -8:
        out.append(("금리 하락 → 성장주 우호", "美10년 %+.0fbp" % tnx_bp))
    else:
        out.append(("금리 중립", "美10년 %+.0fbp" % tnx_bp))
    if expiry_dday is not None and expiry_dday <= 3:
        out.append(("만기 주간 → 수급 변동성 주의", "%s D-%d" % (expiry_label, expiry_dday)))
    if event_dday is not None and event_dday <= 2:
        out.append(("이벤트 대기 → 관망·변동성 확대 가능", "%s D-%d" % (event_label, event_dday)))
    return out


def _ensure(pkg):
    try:
        __import__(pkg); return True
    except ImportError:
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "-q", pkg], timeout=180)
            __import__(pkg); return True
        except Exception:
            return False


# ---------- 객관 해설 룰(템플릿) ----------
def d_index(pct):
    if pct is None: return ""
    if pct >= 2: return "강세(추세 우호)"
    if pct >= 0.5: return "상승"
    if pct > -0.5: return "보합"
    if pct > -2: return "조정"
    return "급락(주의)"

def d_vol(v):
    # VIX 등 현실 레벨 변동성지수용 절대임계. ⚠️ VKOSPI엔 쓰지 말 것(아래 d_vkospi 사용).
    if v is None: return ""
    if v >= 40: return "위기급 변동성"
    if v >= 30: return "높은 변동성(경계)"
    if v >= 20: return "다소 높음"
    return "안정 범위"

def d_vkospi(fl):
    """VKOSPI는 이 환경의 절대레벨이 부풀려져 절대임계가 무의미 → 전일대비 등락으로만 해석.
    (진우 원칙: 절대치 신뢰 금지·상대/등락으로만.) fl=전일대비 등락%."""
    if fl is None: return "등락 정보 없음"
    if fl >= 5:  return "전일比 급등 — 변동성 확대 경계"
    if fl >= 2:  return "전일比 상승 — 변동성 확대"
    if fl <= -5: return "전일比 급락 — 변동성 진정"
    if fl <= -2: return "전일比 하락 — 변동성 진정"
    return "전일比 보합"

def d_usdkrw(pct):
    if pct is None: return ""
    if pct >= 0.5: return "원화 약세(외국인 매도 압력 가능)"
    if pct <= -0.5: return "원화 강세(외국인 우호)"
    return "환율 안정"

def d_yield(pct):
    if pct is None: return ""
    if pct >= 2: return "금리 급등(성장주 부담)"
    if pct >= 0.5: return "금리 상승"
    if pct <= -0.5: return "금리 하락(성장주 우호)"
    return "금리 보합"

def d_sox(pct):
    if pct is None: return ""
    if pct >= 1: return "미 반도체 강세 → 국내 반도체 우호"
    if pct <= -1: return "미 반도체 약세 → 국내 반도체 부담"
    return "반도체 중립"

def d_flow(foreign, indiv, inst):
    if foreign is None: return ""
    f = "순매수" if foreign > 0 else "순매도"
    i = "순매수" if (indiv or 0) > 0 else "순매도"
    if foreign < 0 and (indiv or 0) > 0:
        return "외국인 %s·개인 %s → 차익실현/개인 방어 구도" % (f, i)
    if foreign > 0 and (inst or 0) > 0:
        return "외국인·기관 동반 %s → 매수 우위" % f
    return "외국인 %s·개인 %s" % (f, i)


# ---------- 데이터 ----------
def yf_quote(tk):
    """(last, prev, pct%) or None"""
    try:
        import yfinance as yf
        h = yf.Ticker(tk).history(period="7d")
        c = [x for x in h["Close"].tolist() if x == x]
        if len(c) >= 2:
            return c[-1], c[-2], (c[-1]/c[-2]-1)*100
    except Exception:
        pass
    return None


def krx_index(code):
    try:
        from pykrx import stock
        e = date.today(); s = e - timedelta(days=10)
        df = stock.get_index_ohlcv(s.strftime("%Y%m%d"), e.strftime("%Y%m%d"), code)
        c = df["종가"].tolist()
        if len(c) >= 2:
            return c[-1], c[-2], (c[-1]/c[-2]-1)*100
    except Exception:
        pass
    return None


def _snap_business(d):
    """주말이면 직전 금요일로(순수 날짜 계산, 휴장일은 호출부 0스킵으로 보정)."""
    while d.weekday() >= 5:   # 5=토,6=일
        d -= timedelta(days=1)
    return d


def _flow_empty(vals):
    """전부 None/0 ≈ 주말·휴장(데이터 없음)."""
    return all((x is None or abs(x) < 0.01) for x in vals)


def krx_flow(market):
    """최근 영업일 투자자별 순매수(억원): (외국인, 개인, 기관, 'YYYYMMDD') or None"""
    try:
        from pykrx import stock
    except Exception:
        return None
    # 최근 영업일 앵커 (pykrx nearest 우선, 실패 시 주말보정)
    try:
        anchor_s = stock.get_nearest_business_day_in_a_week(date.today().strftime("%Y%m%d"))
        y, mo, dd = int(anchor_s[:4]), int(anchor_s[4:6]), int(anchor_s[6:8])
        base = date(y, mo, dd)
    except Exception:
        base = _snap_business(date.today())
    # 앵커부터 과거로, 0 아닌 데이터 나오는 첫 영업일 사용(휴장일 보정)
    for back in range(0, 10):
        d = (base - timedelta(days=back)).strftime("%Y%m%d")
        try:
            df = stock.get_market_trading_value_by_investor(d, d, market)
        except Exception:
            continue
        if df is None or not len(df) or "순매수" not in df.columns:
            continue
        def g(names):
            for n in names:
                if n in df.index:
                    return df.loc[n, "순매수"] / 1e8     # 원 → 억
            return None
        f, ind, ins = g(["외국인", "외국인합계"]), g(["개인"]), g(["기관합계", "기관계", "기관"])
        if _flow_empty((f, ind, ins)):
            continue        # 주말·휴장 → 이전 영업일
        return f, ind, ins, d
    return None


def line(label, q, desc_fn=None, unit=""):
    if q is None:
        return "- %-14s 🔴 데이터 미수신 → HTS 확인" % label
    last, prev, pct = q
    d = (" · " + desc_fn(pct)) if desc_fn else ""
    return "- %-14s %s%s (%+.2f%%)%s" % (label, format(last, ",.2f"), unit, pct, d)


def _md_to_mobile_html(md_lines):
    """브리핑 md 라인들 → 폰용 예쁜 HTML(자체 CSS, 다크/라이트). 외부의존 0."""
    import html as _h
    body = []
    for ln in md_lines:
        t = ln.rstrip()
        if not t:
            continue
        if t.startswith("# "):
            body.append('<h1>%s</h1>' % _h.escape(t[2:]))
        elif t.startswith("## "):
            body.append('<h2>%s</h2>' % _h.escape(t[3:]))
        elif t.startswith(">"):
            body.append('<p class="note">%s</p>' % _h.escape(t.lstrip("> ").strip()))
        elif t.startswith("---"):
            body.append('<hr>')
        elif t.startswith("- ") or t.startswith("- [ ]"):
            txt = t[2:].strip()
            cls = ""
            if "🔴" in txt: cls = " warn"
            if "✅" in txt or "콘탱고" in txt or "매수 우위" in txt: cls = " good"
            # **굵게** 처리
            esc = _h.escape(txt)
            import re as _re
            esc = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc)
            body.append('<div class="row%s">%s</div>' % (cls, esc))
        elif t.startswith("**") and t.endswith(":**"):
            body.append('<div class="sub">%s</div>' % _h.escape(t.strip("*").strip()))
        else:
            esc = _h.escape(t)
            import re as _re
            esc = _re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", esc)
            body.append('<div class="row">%s</div>' % esc)
    css = """
:root{--bg:#0f1620;--card:#18222f;--ink:#e8eef5;--sub:#9fb0c3;--line:#2b3a4d;--accent:#4fa8ff;--good:#34c98a;--warn:#ff6b6b}
@media(prefers-color-scheme:light){:root{--bg:#f4f7fb;--card:#fff;--ink:#16212e;--sub:#5b6b7d;--line:#dde5ee;--accent:#1f73d6;--good:#11a06a;--warn:#d63b3b}}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent}
body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Apple SD Gothic Neo","Noto Sans KR",sans-serif;font-size:15px;line-height:1.55}
.wrap{max-width:560px;margin:0 auto;padding:14px 12px 50px}
h1{font-size:19px;margin:8px 2px 4px}
h2{font-size:15px;margin:20px 2px 4px;padding:8px 12px;background:linear-gradient(90deg,var(--accent),transparent);border-radius:10px;color:#fff}
@media(prefers-color-scheme:light){h2{color:#fff}}
.note{font-size:12px;color:var(--sub);margin:4px 2px}
.row{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:9px 12px;margin:5px 0;font-size:14px}
.row.good{border-left:3px solid var(--good)}
.row.warn{border-left:3px solid var(--warn);color:var(--sub)}
.row b{color:var(--accent)}
.sub{font-weight:800;margin:10px 2px 2px;color:var(--ink)}
hr{border:0;border-top:1px solid var(--line);margin:14px 0}
.foot{font-size:11px;color:var(--sub);text-align:center;margin-top:16px}
"""
    return "<!DOCTYPE html><html lang=ko><head><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'><title>시장브리핑</title><style>%s</style></head><body><div class=wrap>%s<p class=foot>정보·객관지표. 투자 추천 아님. 수치는 HTS 최종확인.</p></div></body></html>" % (css, "\n".join(body))


def _sync_targets():
    """OneDrive 동기화 폴더 후보(있으면 복사)."""
    import os
    cands = [Path(os.path.expanduser(r"~/OneDrive/문서/Claude/Projects/진우퀀트")),
             Path(os.path.expanduser(r"~/OneDrive/Documents/Claude/Projects/진우퀀트"))]
    return [c for c in cands if c.exists()]


def build():
    today = date.today()
    has_yf = _ensure("yfinance")
    has_kx = _ensure("pykrx")
    L = []
    L.append("# 시장 현황 브리핑 — %s" % today.strftime("%Y-%m-%d"))
    L.append("\n> 공개 지표 사실 + 객관 해설(룰 템플릿). 자동수신 실패분은 🔴 HTS 확인.\n")

    # ① 국내 선물·옵션
    L.append("## ① 국내 (선물·옵션 환경)")
    kospi = krx_index("1001") if has_kx else None
    kosdaq = krx_index("2001") if has_kx else None
    if kospi is None: kospi = yf_quote("^KS11") if has_yf else None
    if kosdaq is None: kosdaq = yf_quote("^KQ11") if has_yf else None
    L.append(line("코스피", kospi, d_index))
    L.append(line("코스닥", kosdaq, d_index))
    fl_ks = krx_flow("KOSPI") if has_kx else None
    fl_kq = krx_flow("KOSDAQ") if has_kx else None
    def flow_line(name, fl):
        if not fl:
            return "- %s 수급 🔴 데이터 미수신 → HTS 확인" % name
        f, ind, ins, fd = fl
        return "- %s 수급(%s, 억): 외국인 %+.0f · 개인 %+.0f · 기관 %+.0f · %s" % (
            name, fd, f or 0, ind or 0, ins or 0, d_flow(f, ind, ins))
    L.append(flow_line("코스피", fl_ks))
    L.append(flow_line("코스닥", fl_kq))
    # --- KRX 공식 Open API 파생(선물·옵션 전 서비스 승인 완료 2026-06. 키 있으면 전부 자동수신) ---
    if KRX is not None and KRX.auth_key():
        try:
            k = KRX.auth_key(); bdk = KRX.nearest_bday()
            vk = KRX.get_vkospi(k, bdk)
            if vk:
                L.append("- VKOSPI: **%.2f** (등락 %s) · %s" % (vk[0], ("%+.2f%%" % vk[1]) if vk[1] is not None else "-", d_vkospi(vk[1])))
            else:
                L.append("- VKOSPI: 🔴 데이터부족(수신 실패·미발행/휴장 가능) → HTS")
            bs = KRX.get_basis(k, bdk)
            if bs:
                L.append("- KOSPI200 베이시스: 현물 %.2f / 선물 %.2f / **%+.2f** (%s)" % (bs[0], bs[1], bs[2], "콘탱고" if bs[2] > 0 else "백워데이션"))
            else:
                L.append("- 베이시스: 🔴 데이터부족(선물 컬럼 확정 후) → HTS")
            fut = KRX.get_futures_k200(k, bdk)
            if fut and fut[1] is not None:
                oic = KRX.get_futures_oi_change(k, bdk)
                chg = (" (전일대비 " + format(oic[2], "+,.0f") + ")") if oic else ""
                L.append("- 선물 미결제약정(OI): %s%s" % (format(fut[1], ",.0f"), chg))
            pcr = KRX.get_putcall_ratio(k, bdk)
            if isinstance(pcr, dict):
                vol = pcr.get("vol"); val = pcr.get("val")
                valstr = (" · 거래대금 %.3f" % val) if val is not None else ""
                tag = "방어심리↑" if (vol is not None and vol > 1) else "낙관"
                L.append("- 옵션 풋/콜 비율(전체 지수옵션): 거래량 **%.3f**%s (%s)" % (vol, valstr, tag))
                if val is not None and vol is not None and vol > 1.5 and val < 1.0:
                    L.append("  └ ※ 거래량↑·거래대금↓ 괴리 = 대량의 저가 OTM 풋(테일 헤지) 가능성")
            else:
                L.append("- 풋/콜: 🔴 데이터부족(전일 발행 전이면 직전일 자동폴백·HTS 확인)")
        except Exception as e:
            L.append("- KRX 파생: 🔴 오류 %s → HTS" % str(e)[:80])
    else:
        L.append("- KRX 파생(VKOSPI·베이시스·OI·풋콜): 🔴 **인증키 없음** → krx_authkey.txt 설정 시 전부 자동수신(서비스는 승인 완료)")

    # ② 미국장
    L.append("\n## ② 미국장 (밤사이)")
    L.append(line("S&P500", yf_quote("^GSPC") if has_yf else None, d_index))
    L.append(line("나스닥", yf_quote("^IXIC") if has_yf else None, d_index))
    L.append(line("다우", yf_quote("^DJI") if has_yf else None, d_index))
    L.append(line("필라델피아반도체", yf_quote("^SOX") if has_yf else None, d_sox))
    vix = yf_quote("^VIX") if has_yf else None
    L.append("- %-14s %s · %s" % ("VIX(공포)", ("%.2f (%+.2f%%)" % (vix[0], vix[2])) if vix else "🔴 HTS 확인", d_vol(vix[0] if vix else None)))
    L.append(line("달러인덱스", yf_quote("DX-Y.NYB") if has_yf else None, d_usdkrw))
    L.append(line("원/달러", yf_quote("KRW=X") if has_yf else None, d_usdkrw))
    # --- 금리 섹션 (美 만기별 + bp + 한국기준금리 + 한미차) ---
    _tnx = yf_quote("^TNX") if has_yf else None
    tnx_bp = (_tnx[0] - _tnx[1]) * 100 if _tnx else None
    L.append(yline("美10년 ^TNX", _tnx))
    L.append(yline("美5년 ^FVX", yf_quote("^FVX") if has_yf else None))
    L.append(yline("美13주 ^IRX", yf_quote("^IRX") if has_yf else None))
    L.append(yline("美30년 ^TYX", yf_quote("^TYX") if has_yf else None))
    if BOK_BASE_RATE is not None:
        L.append("- 한국 기준금리: **%.2f%%** (수동 입력값)" % BOK_BASE_RATE)
        if _tnx:
            L.append("- 한미 금리차(美10년−한국기준): **%+.2f%%p**" % (_tnx[0] - BOK_BASE_RATE))
        else:
            L.append("- 한미 금리차: 美10년 데이터부족")
    else:
        L.append("- 한국 기준금리: 🔴 수동 확인(스크립트 상단 BOK_BASE_RATE 설정 시 자동)")
        L.append("- 한미 금리차: BOK 미입력 → 기준금리 설정 후 자동")
    L.append(line("엔비디아", yf_quote("NVDA") if has_yf else None, d_index))
    L.append(line("마이크론", yf_quote("MU") if has_yf else None, d_index))
    L.append(line("인텔", yf_quote("INTC") if has_yf else None, d_index))

    # ③ 주요 종목(국내)
    L.append("\n## ③ 주요 종목 (국내)")
    for nm, tk in [("SK하이닉스","000660.KS"),("삼성전자","005930.KS"),("테크윙","089030.KQ"),("대덕전자","353200.KS")]:
        q = yf_quote(tk) if has_yf else None
        L.append(line(nm, q, d_index, unit="원"))

    # ④ 이벤트 캘린더
    L.append("\n## ④ 이벤트 캘린더 (D-day)")
    exps = upcoming_expiries(today)
    expiry_label, expiry_dday = (exps[0][1], (exps[0][0] - today).days) if exps else (None, None)
    for e, kind in exps:
        L.append("- %s : %s (D-%d)" % (e, kind, (e - today).days))
    # 위클리옵션 만기 (목/월) — 짧은 만기 변동성 대비
    for wd_date, wlabel, wnote, wdd in next_weeklies(today, 1):
        L.append("- %s : %s%s (D-%d)" % (wd_date, wlabel, (" " + wnote) if wnote else "", wdd))
    # 만기 후 체크 (둘째 금요일 = 사후채점)
    pec = post_expiry_check(today)
    if pec:
        L.append("- %s : 📌 만기 후 체크(사후채점) (D-%d)" % (pec[0], pec[1]))
    evs = next_fixed_events(today)
    event_label, event_dday = (evs[0][0], evs[0][2]) if evs else (None, None)
    if evs:
        for ev, d, dd in evs[:3]:
            L.append("- %s : %s (D-%d)" % (d, ev, dd))
    else:
        L.append("- FOMC/금통위: 일정 데이터 없음(theme_calendar_fixed.csv 확인)")
    L.append("- CPI·고용: 월중 발표(근사) — **확정일 수동확인**")

    # ⑤ 종합
    L.append("\n## ⑤ 종합 (객관 요약)")
    bits = []
    if kospi and kosdaq:
        bits.append("코스피 %s·코스닥 %s" % (d_index(kospi[2]), d_index(kosdaq[2])))
    sox = yf_quote("^SOX") if has_yf else None
    if sox: bits.append(d_sox(sox[2]))
    if vix: bits.append("VIX " + d_vol(vix[0]))
    if fl_ks: bits.append(d_flow(fl_ks[0], fl_ks[1], fl_ks[2]))
    L.append("- " + (" · ".join(b for b in bits if b) if bits else "자동수신 데이터 부족 → HTS 확인"))
    # 근거 기반 결론(룰 테이블)
    L.append("\n**근거 기반 결론(룰):**")
    for verdict, basis in decision_rules(tnx_bp, expiry_label, expiry_dday, event_label, event_dday):
        L.append("- %s  *(근거: %s)*" % (verdict, basis))

    # 🔴 HTS 확인 필수
    L.append("\n## 🔴 HTS 확인 필수 (자동수신 불가 항목)")
    L.append("> ※ VKOSPI·베이시스·선물OI(증감 포함)·**풋/콜 비율까지 ① 국내 섹션에 KRX API로 전부 자동수신 중**(선물·옵션 서비스 승인 완료).")
    L.append("> 아래는 **KRX OpenAPI 미제공 → 영구 수동**(필요 시 HTS 확인):")
    for it in ["외국인 선물 순매수 계약수(투자자별 파생거래 — KRX OpenAPI 미제공): ____"]:
        L.append("- [ ] " + it)

    L.append("\n---")
    L.append("*공개 지표 사실 + 객관 해설. **매수·매도 추천 아님. 결정·책임 본인.** 수치는 HTS로 최종 확인.*")

    out = BASE / ("시장브리핑_%s.md" % today.strftime("%Y%m%d"))
    out.write_text("\n".join(L), encoding="utf-8")
    # 폰용 예쁜 HTML(항상 최신 고정명)
    html = _md_to_mobile_html(L)
    html_latest = BASE / "시장브리핑_최신.html"
    html_latest.write_text(html, encoding="utf-8")
    # OneDrive 동기화 폴더에도 복사(폰에서 보기)
    synced = []
    for tgt in _sync_targets():
        try:
            (tgt / "시장브리핑_최신.html").write_text(html, encoding="utf-8")
            (tgt / out.name).write_text("\n".join(L), encoding="utf-8")
            synced.append(str(tgt))
        except Exception as e:
            print("  (OneDrive 복사 경고: %s)" % str(e)[:80])
    print("\n".join(L))
    print("\n[폰용 HTML] %s" % html_latest.name)
    if synced:
        print("[OneDrive 동기화] %s → 폰 OneDrive 앱에서 '시장브리핑_최신.html' 열기" % synced[0])
    else:
        print("[안내] OneDrive 동기화 폴더 미발견 — 폰에서 보려면 시장브리핑_최신.html을 클라우드/메신저로 전송")
    print("\n[저장] %s" % out.name)
    print("[소스] yfinance=%s · pykrx=%s" % ("OK" if has_yf else "미설치/실패", "OK" if has_kx else "미설치/실패"))


def selftest():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print("  [%s] %s" % ("OK" if c else "FAIL", n))
    chk("지수 강세 룰", d_index(2.5) == "강세(추세 우호)")
    chk("지수 급락 룰", d_index(-3) == "급락(주의)")
    chk("VIX>40 위기급", d_vol(45) == "위기급 변동성")
    chk("VKOSPI 안정", d_vol(15) == "안정 범위")
    chk("VKOSPI 등락해석(상승)", d_vkospi(4.14) == "전일比 상승 — 변동성 확대")
    chk("VKOSPI 등락해석(보합)", d_vkospi(0.5) == "전일比 보합")
    chk("외매도+개매수 구도", "차익실현" in d_flow(-1000, 800, -200))
    chk("None 안전", d_index(None) == "" and line("x", None).endswith("HTS 확인"))
    # 금리 bp 룰
    chk("금리 +10bp→부담", d_yield_bp(10) == "금리 급등(성장주 부담)")
    chk("금리 -10bp→우호", d_yield_bp(-10) == "금리 하락(성장주 우호)")
    chk("금리 +3bp→중립", d_yield_bp(3) == "금리 중립")
    # 만기 날짜계산
    chk("9월 동시만기=9/10", second_thursday(2026, 9, 10) == date(2026, 9, 10) if False else second_thursday(2026, 9) == date(2026, 9, 10))
    ue = upcoming_expiries(date(2026, 9, 8))
    chk("다가오는 만기 D-day≥0", ue and (ue[0][0] - date(2026, 9, 8)).days >= 0)
    chk("위클리 목/월 2건", len(next_weeklies(date(2026, 9, 8), 1)) == 2)
    chk("만기후체크=둘째금(9/11)", post_expiry_check(date(2026, 9, 1))[0] == date(2026, 9, 11))
    # 룰 테이블
    r1 = decision_rules(10, "옵션만기", 2, "FOMC", 5)
    chk("룰: 금리급등 포함", any("성장/기술주 부담" in v for v, b in r1))
    chk("룰: D-2 만기→주의", any("만기 주간" in v for v, b in r1))
    chk("룰: D-5 이벤트 제외", not any("이벤트 대기" in v for v, b in r1))
    r2 = decision_rules(None, None, None, "금통위", 1)
    chk("룰: 금리없음→판단보류", any(v == "판단보류" for v, b in r2))
    chk("룰: D-1 이벤트→관망", any("이벤트 대기" in v for v, b in r2))
    print("self-test: %d/%d" % (ok, tot)); return ok == tot


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        try: build()
        except Exception:
            import traceback; print("\n[에러]"); traceback.print_exc()
