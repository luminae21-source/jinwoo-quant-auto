#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
보유점검.py — 매일 보유 종목 매도 규율 점검 (매도규칙서 Exit Playbook 자동 적용)
==============================================================================
목적: 진우님 핵심 약점(매도 안 함→수익 못 챙김·손실 키움) 교정. 매일 보유 종목을
      손절선·트레일링·+1R·시간손절 규칙으로 점검해 🟢/🟡/🔴 신호등으로 보여준다.
      ⚠️ 매수·매도 추천 아님 — 규칙 신호 산출. 집행·책임은 진우.

입력: my_holdings.csv  (컬럼 유연 감지)
  필수: code(6자리)  · 권장: name
  계산용(없으면 일부 항목 '미입력' 표기):
    entry_price(진입가) · entry_date(진입일 YYYY-MM-DD) · qty(수량)
    credit(신용여부 Y/N) · stop(손절가, 없으면 진입가·ATR로 자동) · target(목표가, 선택)
데이터: pykrx(국내) 우선 → yfinance(.KS/.KQ) 백업. 실데이터만, 없으면 "데이터부족"(가짜 금지).
산출: 보유점검_YYYY-MM-DD.md (+ .html) · 콘솔
규칙: 매도규칙서.md 와 동일 — 손절 max(진입가−2.5ATR, 진입가×0.80) · +1R 절반 · 트레일 고점−2.5ATR · 20일 ±5% 시간손절.
사용: python 보유점검.py [--selftest]   ·   실행: 보유점검_실행.bat
무수정: production·기존 산출물. 이 파일은 신규.
"""
import os, sys, argparse, csv
from datetime import datetime, date

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
K_ATR = 2.5          # 손절·트레일링 ATR 배수
CAP = 0.20           # 손절 하한 캡 (−20%)
TIME_DAYS = 20       # 시간손절 거래일
FLAT_PCT = 5.0       # 횡보 판정 ±%
ATR_WIN = 14

# ===== 순수 계산(네트워크 불필요 — self-test 대상) =====
def auto_stop(entry, atr):
    """손절가 = max(진입가 − 2.5×ATR, 진입가 × 0.80). ATR 없으면 −20%만."""
    if atr is None or atr != atr:  # nan
        return entry * (1 - CAP)
    return max(entry - K_ATR * atr, entry * (1 - CAP))


def assess(entry, cur, high, atr, days_held, stop=None, target=None):
    """규칙 평가 → dict(신호등·각 항목). entry/cur 필수, 나머지 가능한 만큼."""
    out = {"light": "⚪", "reasons": []}
    if entry is None or cur is None:
        out["pl_pct"] = None
        out["note"] = "진입가/현재가 미입력 → 손익·규칙 계산 불가"
        return out
    if stop is None:
        stop = auto_stop(entry, atr)
    R = entry - stop
    t1r = entry + R if R > 0 else None
    trail = (high - K_ATR * atr) if (high is not None and atr is not None and atr == atr) else None
    pl = (cur / entry - 1) * 100
    stop_breach = cur < stop
    trail_trig = (trail is not None) and (high > entry) and (cur < trail)
    t1r_hit = (t1r is not None) and (cur >= t1r)
    time_stop = (days_held is not None) and (days_held >= TIME_DAYS) and (abs(pl) < FLAT_PCT)
    tgt_hit = (target is not None) and (cur >= target)
    # 신호등 우선순위: 🔴 > 🟡 > 🟢
    if stop_breach:
        out["light"] = "🔴"; out["reasons"].append("손절선 이탈 → 다음날 매도")
    elif trail_trig:
        out["light"] = "🔴"; out["reasons"].append("트레일링 스탑 발동 → 청산 검토")
    elif t1r_hit or tgt_hit:
        out["light"] = "🟡"; out["reasons"].append("+1R/목표 도달 → 절반 익절")
    elif time_stop:
        out["light"] = "🟡"; out["reasons"].append(f"{TIME_DAYS}거래일 ±{FLAT_PCT:.0f}% 횡보 → 시간손절 검토")
    else:
        out["light"] = "🟢"; out["reasons"].append("규칙 내 — 보유·관찰")
    out.update({"pl_pct": pl, "stop": stop, "R": R if R > 0 else None, "t1r": t1r,
                "trail": trail, "stop_breach": stop_breach, "trail_trig": trail_trig,
                "t1r_hit": t1r_hit, "time_stop": time_stop,
                "stop_dist_pct": (cur - stop) / cur * 100 if cur else None})
    return out


# ===== 입력 =====
def load_holdings():
    """my_holdings.csv → (list[dict], 감지된 컬럼 set). 주석(#)·빈줄 무시. 컬럼 유연."""
    p = os.path.join(HERE, "my_holdings.csv")
    if not os.path.exists(p):
        return [], set()
    rows = []; cols = set()
    with open(p, encoding="utf-8-sig") as f:
        # 주석줄 제거 후 DictReader
        lines = [ln for ln in f if ln.strip() and not ln.lstrip().startswith("#")]
    if not lines:
        return [], set()
    rdr = csv.DictReader(lines)
    cols = set(c.strip() for c in (rdr.fieldnames or []))
    for r in rdr:
        r = {(k.strip() if k else k): (v.strip() if isinstance(v, str) else v) for k, v in r.items()}
        code = (r.get("code") or "").zfill(6)
        if not code.isdigit():
            continue
        rows.append(r)
    return rows, cols


def _f(r, key):
    v = r.get(key)
    if v in (None, ""):
        return None
    try:
        return float(str(v).replace(",", ""))
    except ValueError:
        return None


# ===== 데이터 (실데이터만) =====
def get_ohlcv(code):
    """pykrx 우선 → yfinance 백업. DataFrame(date index, O/H/L/C) or None."""
    import pandas as pd
    # 1) pykrx
    try:
        from pykrx import stock
        end = stock.get_nearest_business_day_in_a_week(date.today().strftime("%Y%m%d"))
        start = (datetime.strptime(end, "%Y%m%d")).replace(year=datetime.strptime(end, "%Y%m%d").year - 1).strftime("%Y%m%d")
        df = stock.get_market_ohlcv(start, end, code)
        if df is not None and len(df) > 0:
            df = df.rename(columns={"시가": "O", "고가": "H", "저가": "L", "종가": "C"})
            return df[["O", "H", "L", "C"]].dropna()
    except Exception:
        pass
    # 2) yfinance (.KS 코스피 / .KQ 코스닥 둘 다 시도)
    try:
        import yfinance as yf
        for suf in (".KS", ".KQ"):
            try:
                h = yf.Ticker(code + suf).history(period="1y")
                if h is not None and len(h) > 0:
                    return h.rename(columns={"Open": "O", "High": "H", "Low": "L", "Close": "C"})[["O", "H", "L", "C"]].dropna()
            except Exception:
                continue
    except Exception:
        pass
    return None


def atr14(df):
    import pandas as pd
    h, l, c = df["H"], df["L"], df["C"]; pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    a = tr.rolling(ATR_WIN, min_periods=max(5, ATR_WIN // 2)).mean()
    return float(a.iloc[-1]) if len(a) and a.iloc[-1] == a.iloc[-1] else None


def biz_days_between(d0, df):
    """진입일 이후 거래일 수 (df index 기준). d0=datetime/date or None."""
    if d0 is None:
        return None
    try:
        idx = df.index
        return int((idx.date >= d0).sum()) if hasattr(idx, "date") else None
    except Exception:
        return None


def high_since(d0, df):
    """진입 후 고점. d0 없으면 최근 60거래일 고점."""
    try:
        if d0 is not None and hasattr(df.index, "date"):
            sub = df[df.index.date >= d0]
            if len(sub):
                return float(sub["H"].max())
        return float(df["H"].tail(60).max())
    except Exception:
        return None


# ===== 빌드 =====
def build():
    rows, cols = load_holdings()
    have_entry = "entry_price" in cols
    have_date = "entry_date" in cols
    results = []
    for r in rows:
        code = (r.get("code") or "").zfill(6)
        name = r.get("name") or code
        entry = _f(r, "entry_price"); qty = _f(r, "qty")
        stop_in = _f(r, "stop"); target_in = _f(r, "target")
        credit = (r.get("credit") or "").upper().startswith(("Y", "1", "신"))
        d0 = None
        ds = r.get("entry_date")
        if ds:
            for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
                try:
                    d0 = datetime.strptime(ds, fmt).date(); break
                except ValueError:
                    continue
        rec = {"code": code, "name": name, "credit": credit, "qty": qty}
        df = get_ohlcv(code)
        if df is None or len(df) < 20:
            rec.update({"light": "⚪", "note": "데이터부족(시세 수신 실패)", "cur": None})
            results.append(rec); continue
        cur = float(df["C"].iloc[-1]); atr = atr14(df)
        high = high_since(d0, df); dheld = biz_days_between(d0, df)
        a = assess(entry, cur, high, atr, dheld, stop=stop_in, target=target_in)
        rec.update({"cur": cur, "atr": atr, "high": high, "days_held": dheld, "entry": entry, **a})
        results.append(rec)
    return results, cols, have_entry, have_date


def _fmt(v, suf="", n=0):
    if v is None or (isinstance(v, float) and v != v):
        return "—"
    if isinstance(v, float):
        return f"{v:,.{n}f}{suf}"
    return f"{v}{suf}"


def render(results, cols, have_entry, have_date):
    today = date.today().strftime("%Y-%m-%d")
    order = {"🔴": 0, "🟡": 1, "🟢": 2, "⚪": 3}
    results = sorted(results, key=lambda r: order.get(r.get("light", "⚪"), 9))
    L = [f"# 보유 점검 — {today}", "",
         "> 매도규칙서(Exit Playbook) 자동 적용. 🔴=손절/청산 검토 · 🟡=익절/시간 · 🟢=유지 · ⚪=데이터/입력부족.",
         "> ⚠️ 매수·매도 추천 아님 — 규칙 신호. 집행·책임은 진우.", ""]
    miss = []
    if not have_entry:
        miss.append("entry_price(진입가)")
    if not have_date:
        miss.append("entry_date(진입일)")
    if miss:
        L.append(f"> ⚠️ **입력 보강 권장**: my_holdings.csv에 `{', '.join(miss)}` 컬럼이 없어 일부 항목(손익·+1R·시간손절)을 못 켭니다.")
        L.append("> 권장 헤더: `code,name,entry_price,qty,entry_date,credit,stop,target`")
        L.append("")
    L.append("| 신호 | 종목 | 현재가 | 손익% | 손절선 | 손절까지 | +1R목표 | 트레일 | 보유일 | 판단 |")
    L.append("|---|---|---|---|---|---|---|---|---|---|")
    for r in results:
        sig = r.get("light", "⚪")
        nm = f"{r['name']} `{r['code']}`" + (" 🔆신용" if r.get("credit") else "")
        if r.get("cur") is None:
            L.append(f"| ⚪ | {nm} | — | — | — | — | — | — | — | {r.get('note','데이터부족')} |")
            continue
        reasons = " / ".join(r.get("reasons", [])) or r.get("note", "")
        L.append("| {s} | {nm} | {cur} | {pl} | {stop} | {dist} | {t1r} | {trail} | {dh} | {rs} |".format(
            s=sig, nm=nm, cur=_fmt(r.get("cur"), "원"),
            pl=_fmt(r.get("pl_pct"), "%", 1), stop=_fmt(r.get("stop"), "원"),
            dist=_fmt(r.get("stop_dist_pct"), "%", 1), t1r=_fmt(r.get("t1r"), "원"),
            trail=_fmt(r.get("trail"), "원"), dh=_fmt(r.get("days_held"), "일"), rs=reasons))
    # 요약
    from collections import Counter
    cnt = Counter(r.get("light", "⚪") for r in results)
    L += ["", f"**요약**: 🔴 {cnt.get('🔴',0)} · 🟡 {cnt.get('🟡',0)} · 🟢 {cnt.get('🟢',0)} · ⚪ {cnt.get('⚪',0)}",
          "", "*규칙: 손절 max(진입가−2.5ATR, 진입가×0.80) · +1R 절반익절 · 트레일 고점−2.5ATR · 20일 ±5% 시간손절. 매도규칙서.md 참조.*"]
    md = "\n".join(L)
    open(os.path.join(HERE, f"보유점검_{today}.md"), "w", encoding="utf-8").write(md)
    # 간단 HTML
    html = _to_html(results, today, miss)
    open(os.path.join(HERE, f"보유점검_{today}.html"), "w", encoding="utf-8").write(html)
    open(os.path.join(HERE, "보유점검_최신.html"), "w", encoding="utf-8").write(html)
    return md, cnt


def _to_html(results, today, miss):
    order = {"🔴": 0, "🟡": 1, "🟢": 2, "⚪": 3}
    rs = sorted(results, key=lambda r: order.get(r.get("light", "⚪"), 9))
    cmap = {"🔴": "#e2606a", "🟡": "#e0b020", "🟢": "#3fb37a", "⚪": "#9aa0aa"}
    rows = ""
    for r in rs:
        sig = r.get("light", "⚪"); col = cmap.get(sig, "#9aa0aa")
        nm = f"{r['name']} <span class='c'>{r['code']}</span>" + (" 🔆" if r.get("credit") else "")
        if r.get("cur") is None:
            rows += f"<tr><td style='color:{col}'>{sig}</td><td>{nm}</td><td colspan='7' class='mut'>{r.get('note','데이터부족')}</td></tr>"
            continue
        f = lambda v, s="", n=0: "—" if (v is None or (isinstance(v, float) and v != v)) else (f"{v:,.{n}f}{s}" if isinstance(v, float) else f"{v}{s}")
        rows += (f"<tr><td style='color:{col};font-size:16px'>{sig}</td><td>{nm}</td>"
                 f"<td class='num'>{f(r.get('cur'),'')}</td><td class='num'>{f(r.get('pl_pct'),'%',1)}</td>"
                 f"<td class='num'>{f(r.get('stop'),'')}</td><td class='num'>{f(r.get('stop_dist_pct'),'%',1)}</td>"
                 f"<td class='num'>{f(r.get('t1r'),'')}</td><td class='num'>{f(r.get('trail'),'')}</td>"
                 f"<td class='r'>{' / '.join(r.get('reasons',[]))}</td></tr>")
    warn = ""
    if miss:
        warn = f"<div class='warn'>⚠️ my_holdings.csv에 <b>{', '.join(miss)}</b> 없음 — 일부 항목 제한. 권장 헤더: code,name,entry_price,qty,entry_date,credit,stop,target</div>"
    return f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>보유 점검 — {today}</title>
<style>
:root{{--bg:#0f1115;--card:#181b22;--ink:#e8eaed;--mut:#9aa0aa;--line:#262a33;--acc:#ff7a45}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,'Segoe UI','Malgun Gothic',sans-serif;padding:16px;line-height:1.5;max-width:760px;margin:0 auto}}
h1{{font-size:19px;margin:0 0 2px}}.sub{{color:var(--mut);font-size:12px;margin-bottom:10px}}
.warn{{background:#2a1d12;border:1px solid #5a3a1f;color:#ffc6a3;border-radius:8px;padding:9px 12px;font-size:12px;margin:8px 0}}
table{{width:100%;border-collapse:collapse;font-size:12px;margin-top:6px}}
th,td{{padding:7px 8px;border-bottom:1px solid var(--line);text-align:left;vertical-align:middle}}
th{{color:var(--mut);font-size:11px}}.num{{text-align:right;font-variant-numeric:tabular-nums}}
.c{{color:var(--mut);font-family:monospace;font-size:10.5px}}.mut{{color:var(--mut)}}.r{{font-size:11.5px;color:#cfd3da}}
.foot{{margin-top:16px;color:#5a6068;font-size:11px;border-top:1px solid var(--line);padding-top:9px}}
</style></head><body>
<h1>🛡️ 보유 점검 (매도 규율)</h1>
<div class="sub">{today} · 🔴손절/청산 · 🟡익절/시간 · 🟢유지 · ⚪데이터부족 · 매수·매도 추천 아님</div>
{warn}
<table><thead><tr><th>신호</th><th>종목</th><th class="num">현재가</th><th class="num">손익%</th><th class="num">손절선</th><th class="num">손절까지</th><th class="num">+1R</th><th class="num">트레일</th><th>판단</th></tr></thead><tbody>{rows}</tbody></table>
<div class="foot">규칙: 손절 max(진입가−2.5ATR, 진입가×0.80) · +1R 절반익절 · 트레일 고점−2.5ATR · 20일 ±5% 시간손절. 매도규칙서.md.<br>실데이터(pykrx/yfinance)만 · 데이터 없으면 ⚪. 집행·책임은 진우.</div>
</body></html>"""


# ===== self-test (네트워크 불필요) =====
def _selftest():
    ok = 0
    def chk(n, c):
        nonlocal ok; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    # 1) 자동 손절: ATR 작음 → −2.5ATR, ATR 큼 → −20% 캡
    chk("auto_stop ATR기준", abs(auto_stop(100, 4) - 90.0) < 1e-9)            # 100-10=90 > 80
    chk("auto_stop −20%캡", abs(auto_stop(100, 20) - 80.0) < 1e-9)            # 100-50=50 <80 →80
    # 2) 손절 이탈 → 🔴
    a = assess(entry=100, cur=78, high=105, atr=4, days_held=5)
    chk("손절이탈 🔴", a["light"] == "🔴" and a["stop_breach"])
    # 3) +1R 도달 → 🟡 (stop=90→R=10→+1R=110)
    a = assess(entry=100, cur=111, high=111, atr=4, days_held=5, stop=90)
    chk("+1R 익절 🟡", a["light"] == "🟡" and a["t1r_hit"])
    # 4) 트레일링 발동 → 🔴 (high130,atr10→trail=105, cur104<105)
    a = assess(entry=100, cur=104, high=130, atr=10, days_held=10, stop=90)
    chk("트레일 발동 🔴", a["light"] == "🔴" and a["trail_trig"])
    # 5) 시간손절 → 🟡 (25일 횡보 +2%)
    a = assess(entry=100, cur=102, high=103, atr=3, days_held=25, stop=90)
    chk("시간손절 🟡", a["light"] == "🟡" and a["time_stop"])
    # 6) 정상 → 🟢
    a = assess(entry=100, cur=105, high=106, atr=4, days_held=5, stop=90)
    chk("정상 🟢", a["light"] == "🟢")
    # 7) 입력부족 → ⚪(계산 불가)
    a = assess(entry=None, cur=100, high=None, atr=None, days_held=None)
    chk("입력부족 처리", a["light"] == "⚪" and a.get("pl_pct") is None)
    print(f"✅ 보유점검 셀프테스트 ({ok}/8)")
    return ok == 8


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest(); return
    results, cols, have_entry, have_date = build()
    if not results:
        print("❌ my_holdings.csv 비어있음/없음 — code,name(,entry_price,entry_date,qty) 입력 후 재실행.")
        return
    md, cnt = render(results, cols, have_entry, have_date)
    print(f"보유 점검 완료 · {date.today()} · 종목 {len(results)}")
    print(f"신호등: 🔴 {cnt.get('🔴',0)} · 🟡 {cnt.get('🟡',0)} · 🟢 {cnt.get('🟢',0)} · ⚪ {cnt.get('⚪',0)}")
    for r in sorted(results, key=lambda x: {'🔴':0,'🟡':1,'🟢':2,'⚪':3}.get(x.get('light','⚪'),9)):
        cur = r.get("cur"); pl = r.get("pl_pct")
        plt = f"{pl:+.1f}%" if isinstance(pl, float) else "—"
        print(f"  {r.get('light','⚪')} {r['name']}({r['code']}) {plt} · {' / '.join(r.get('reasons') or [r.get('note','')])}")
    print(f"산출: 보유점검_{date.today()}.md · 보유점검_{date.today()}.html · 보유점검_최신.html")


if __name__ == "__main__":
    main()
