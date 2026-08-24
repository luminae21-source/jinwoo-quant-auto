#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
주봉분석.py — 주봉 기술적 분석 (삼성전자·SK하이닉스)
==============================================================================
목적: pykrx 일봉 → 주(월~금) OHLC 집계 → 20주선·직전완결주 캔들·도지·지지저항.
      ⚠️ 사실 나열만. 매수/매도 추천 아님. "이 패턴은 ~로 해석됨, 결정은 본인" 톤. 실데이터만.
집계: 주 시가=주 첫날 시가 · 종가=주 마지막 종가 · 고=주중 최고 · 저=주중 최저 (W-FRI).
완결주: 일봉 마지막이 금요일이면 그 주 완결, 아니면 진행중 주 제외. 20주선은 완결주 기준.
산출: 주봉분석_YYYY-MM-DD.md · 콘솔.  사용: python 주봉분석.py [--selftest]  실행: 주봉분석_실행.bat
무수정: production·기존 산출물. 신규.
"""
import os, sys, argparse
from datetime import date, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
HERE = os.path.dirname(os.path.abspath(__file__))
TARGETS = [("삼성전자", "005930"), ("SK하이닉스", "000660")]   # 주봉_종목.csv 없을 때 기본값


def load_targets():
    """주봉_종목.csv(code,name) → [(name,code),...]. 주석(#)·빈줄 무시. 없으면 기본 TARGETS."""
    import csv as _csv
    p = os.path.join(HERE, "주봉_종목.csv")
    if not os.path.exists(p):
        return TARGETS
    out = []
    for line in open(p, encoding="utf-8-sig"):
        line = line.strip()
        if not line or line.startswith("#") or line.lower().startswith("code,"):
            continue
        parts = [x.strip() for x in line.split(",")]
        c = parts[0].zfill(6)
        if c.isdigit():
            out.append((parts[1] if len(parts) > 1 and parts[1] else c, c))
    return out or TARGETS
MA_N = 20
DOJI_TH = 0.10       # 몸통/전체범위 ≤10% = 도지
SLOPE_TH = 1.0       # 20주선 4주 기울기 ±1% = 횡보 경계


# ---------- 순수 로직 (self-test 대상) ----------
def to_weekly(df):
    """일봉 DataFrame(O/H/L/C, DatetimeIndex) → 주봉(W-FRI 집계)."""
    import pandas as pd
    w = df.resample("W-FRI").agg(O=("O", "first"), H=("H", "max"), L=("L", "min"), C=("C", "last"))
    return w.dropna()


def candle(o, h, l, c):
    """캔들 판정 → dict(color·doji·upper·lower·body·range)."""
    body = abs(c - o); rng = h - l
    doji = (rng > 0) and (body / rng <= DOJI_TH)
    color = "양봉" if c > o else ("음봉" if c < o else "보합")
    upper = h - max(o, c)      # 위꼬리
    lower = min(o, c) - l      # 아래꼬리
    return {"color": color, "doji": doji, "upper": upper, "lower": lower, "body": body, "range": rng}


def slope(ma_series):
    """20주선 최근 4주 기울기 → 상승/하락/횡보."""
    s = ma_series.dropna()
    if len(s) < 5:
        return "판단불가", None
    now = float(s.iloc[-1]); prev = float(s.iloc[-5])
    if prev <= 0:
        return "판단불가", None
    ch = (now / prev - 1) * 100
    d = "상승" if ch > SLOPE_TH else ("하락" if ch < -SLOPE_TH else "횡보")
    return d, ch


def analyze(daily, cur_price=None):
    """일봉 df → 주봉 분석 dict. cur_price 없으면 일봉 마지막 종가."""
    import pandas as pd
    if daily is None or len(daily) < 60:
        return None
    w = to_weekly(daily)
    if len(w) < MA_N + 1:
        return None
    dlast = daily.index[-1]
    complete = (dlast.weekday() == 4)                 # 금요일=완결
    wc = w if complete else w.iloc[:-1]               # 완결주만
    if len(wc) < MA_N + 1:
        wc = w
    ma = wc["C"].rolling(MA_N).mean()
    ma20 = float(ma.iloc[-1])
    last = wc.iloc[-1]                                 # 직전 완결 주 캔들
    cd = candle(float(last["O"]), float(last["H"]), float(last["L"]), float(last["C"]))
    cur = float(cur_price) if cur_price is not None else float(daily["C"].iloc[-1])
    gap = (cur / ma20 - 1) * 100 if ma20 > 0 else None
    sl, slch = slope(ma)
    win = wc.tail(MA_N)
    hi = float(win["H"].max()); lo = float(win["L"].min())
    return {"cur": cur, "ma20": ma20, "gap": gap, "above": cur > ma20,
            "candle": cd, "week_close": float(last["C"]), "slope": sl, "slope_ch": slch,
            "hi20": hi, "lo20": lo, "asof": dlast, "complete": complete, "nweek": len(wc)}


def summarize(name, code, a):
    """객관 3~4줄 요약 (사실만, 추천 금지)."""
    if not a:
        return [f"## {name}({code})", "- ❌ 데이터부족 — 일봉/주봉 수신 실패."]
    cd = a["candle"]
    pos = "위" if a["above"] else "아래"
    doji = " · **도지(방향성 약함)**" if cd["doji"] else ""
    tail = []
    if cd["upper"] > cd["body"] * 1.5 and cd["body"] > 0:
        tail.append("긴 위꼬리")
    if cd["lower"] > cd["body"] * 1.5 and cd["body"] > 0:
        tail.append("긴 아래꼬리")
    tails = (" · " + "·".join(tail)) if tail else ""
    L = [f"## {name}({code})",
         f"- 현재가 {a['cur']:,.0f} · 20주선 {a['ma20']:,.0f} · **이격 {a['gap']:+.1f}%** (20주선 {pos})",
         f"- 직전 완결 주 캔들: **{cd['color']}**{doji}{tails}  (종가 {a['week_close']:,.0f})",
         f"- 20주선 방향(최근4주): **{a['slope']}**" + (f" ({a['slope_ch']:+.1f}%)" if a['slope_ch'] is not None else ""),
         f"- 최근 20주 고점 {a['hi20']:,.0f} / 저점 {a['lo20']:,.0f} (지지·저항 참고)"]
    # 객관 해석(사실 기반, 결정은 본인)
    interp = f"→ 현재가가 20주선 {pos}({a['gap']:+.1f}%), 20주선 {a['slope']}. "
    interp += "이 배열은 " + ("중기 상승 추세 유지로 해석됨." if (a['above'] and a['slope'] == '상승')
              else "중기 하락 추세로 해석됨." if (not a['above'] and a['slope'] == '하락')
              else "추세 전환·눌림 구간(혼조)으로 해석됨.")
    interp += " 결정·책임은 본인."
    L.append(f"- {interp}")
    return L


# ---------- 데이터 (진우 PC) ----------
def get_daily(code, weeks=40):
    """pykrx 일봉 → DataFrame(O/H/L/C). 실패=None."""
    try:
        from pykrx import stock
        import pandas as pd
        end = date.today().strftime("%Y%m%d")
        start = (date.today() - timedelta(days=weeks * 7 + 40)).strftime("%Y%m%d")
        df = stock.get_market_ohlcv(start, end, code)
        if df is None or len(df) == 0:
            return None
        df = df.rename(columns={"시가": "O", "고가": "H", "저가": "L", "종가": "C"})
        return df[["O", "H", "L", "C"]].dropna()
    except Exception:
        return None


def _font(size, bold=False):
    from PIL import ImageFont
    cand = ([r"C:\Windows\Fonts\malgunbd.ttf"] if bold else []) + [r"C:\Windows\Fonts\malgun.ttf",
            "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"]
    for p in cand:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def render_card(cards, today):
    """주봉 요약 카드뉴스(PNG) — 종목 많아도 되는 컴팩트 표. Pillow 없으면 None."""
    try:
        from PIL import Image, ImageDraw
    except Exception:
        return None
    W = 780; pad = 22; rowh = 44; head = 96
    tf = _font(28, True); hf = _font(15, True); nf = _font(19, True); vf = _font(19); sf = _font(15)
    H = head + len(cards) * rowh + 40
    img = Image.new("RGB", (W, H), (15, 17, 21)); d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 6], fill=(255, 122, 69))
    d.text((pad, 22), f"📊 주봉 분석 · {today}", font=tf, fill=(255, 255, 255))
    d.text((pad, 58), "20주선 대비 이격·추세·직전주 캔들 (사실 나열, 추천 아님)", font=sf, fill=(154, 160, 170))
    # 헤더
    cx = {"name": pad, "gap": 250, "pos": 360, "candle": 560}
    d.text((cx["name"], head - 22), "종목", font=hf, fill=(154, 160, 170))
    d.text((cx["gap"], head - 22), "이격(20주선)", font=hf, fill=(154, 160, 170))
    d.text((cx["pos"], head - 22), "위치·추세", font=hf, fill=(154, 160, 170))
    d.text((cx["candle"], head - 22), "직전주 캔들", font=hf, fill=(154, 160, 170))
    d.line([pad, head - 2, W - pad, head - 2], fill=(38, 42, 51))
    y = head + 6
    for name, code, a in cards:
        d.text((cx["name"], y), name, font=nf, fill=(232, 234, 237))
        if not a:
            d.text((cx["gap"], y), "데이터부족", font=vf, fill=(154, 160, 170)); y += rowh; continue
        gcol = (63, 179, 122) if a["above"] else (226, 96, 106)
        arrow = "▲" if a["above"] else "▼"
        d.text((cx["gap"], y), f"{arrow} {a['gap']:+.1f}%", font=vf, fill=gcol)
        scol = {"상승": (63, 179, 122), "하락": (226, 96, 106)}.get(a["slope"], (224, 176, 32))
        pos = "위" if a["above"] else "아래"
        d.text((cx["pos"], y), f"{pos}·{a['slope']}", font=vf, fill=scol)
        cd = a["candle"]; ccol = (63, 179, 122) if cd["color"] == "양봉" else ((226, 96, 106) if cd["color"] == "음봉" else (154, 160, 170))
        doji = "·도지" if cd["doji"] else ""
        d.text((cx["candle"], y), f"{cd['color']}{doji}", font=vf, fill=ccol)
        y += rowh
        d.line([pad, y - 4, W - pad, y - 4], fill=(28, 31, 38))
    d.text((pad, H - 28), "20주선=완결주 기준 · pykrx 실데이터 · 결정·책임 본인", font=sf, fill=(90, 96, 104))
    p = os.path.join(HERE, f"주봉분석_카드_{today}.png")
    img.save(p); return p


def _sync_onedrive(*paths):
    import shutil
    for tgt in (os.path.expanduser(r"~\OneDrive\문서\Claude\Projects\진우퀀트"),):
        if os.path.isdir(tgt):
            for p in paths:
                if p and os.path.exists(p):
                    try:
                        shutil.copy(p, tgt)
                    except Exception:
                        pass


def run():
    today = date.today().strftime("%Y-%m-%d")
    L = [f"# 주봉 기술적 분석 — {today}", "",
         "> pykrx 일봉→주봉(월~금) 집계. 20주선·직전완결주 캔들·도지·지지저항. **사실 나열, 추천 아님.**", ""]
    cards = []
    tgts = load_targets()
    for name, code in tgts:
        d = get_daily(code)
        a = analyze(d)
        L += summarize(name, code, a) + [""]
        cards.append((name, code, a))
    L.append("*집계=주 시가/종가/최고/최저. 20주선=완결주 기준. 실데이터(pykrx). 결정·책임 본인.*")
    md = "\n".join(L)
    mdp = os.path.join(HERE, f"주봉분석_{today}.md")
    open(mdp, "w", encoding="utf-8").write(md)
    png = render_card(cards, today)
    _sync_onedrive(mdp, png)
    print(md)
    print(f"\n[산출] 주봉분석_{today}.md" + (f" · 주봉분석_카드_{today}.png" if png else " (Pillow 없어 카드 생략)"))


def _selftest():
    import pandas as pd, numpy as np
    ok = 0
    def chk(n, c):
        nonlocal ok; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    # 주 집계: 2주치 일봉(월~금) → 시=첫시, 종=끝종, 고=최고, 저=최저
    idx = pd.bdate_range("2026-06-01", periods=10)  # 2주(월~금)
    df = pd.DataFrame({"O": [10,11,12,13,14, 20,21,22,23,24],
                       "H": [15,16,17,18,19, 25,26,27,28,30],
                       "L": [9,8,10,11,12, 19,18,20,21,22],
                       "C": [11,12,13,14,15, 21,22,23,24,29]}, index=idx)
    w = to_weekly(df)
    chk("주 수 2", len(w) == 2)
    chk("1주 시가=10", float(w.iloc[0]["O"]) == 10)
    chk("1주 종가=15", float(w.iloc[0]["C"]) == 15)
    chk("1주 고가=19", float(w.iloc[0]["H"]) == 19)
    chk("2주 저가=18", float(w.iloc[1]["L"]) == 18)
    # 캔들: 양봉·음봉·도지
    chk("양봉", candle(10, 15, 9, 14)["color"] == "양봉")
    chk("음봉", candle(14, 15, 9, 10)["color"] == "음봉")
    dj = candle(100, 110, 90, 100.5)  # body0.5/range20=2.5%≤10%
    chk("도지 판정", dj["doji"] is True)
    chk("비도지", candle(100, 110, 95, 108)["doji"] is False)
    chk("위꼬리 계산", candle(100, 120, 95, 105)["upper"] == 15)
    # 기울기: 상승 MA
    ma = pd.Series([100,101,102,103,104,105])
    chk("기울기 상승", slope(ma)[0] == "상승")
    ma2 = pd.Series([100,100,100,100,100,100])
    chk("기울기 횡보", slope(ma2)[0] == "횡보")
    # analyze end-to-end (합성 200일 상승추세)
    idx2 = pd.bdate_range("2025-09-01", periods=200)
    c = 50000 * np.cumprod(1 + np.r_[0, np.random.default_rng(1).normal(0.001, 0.01, 199)])
    d2 = pd.DataFrame({"O": c*0.99, "H": c*1.02, "L": c*0.98, "C": c}, index=idx2)
    a = analyze(d2)
    chk("analyze 구조", a is not None and "ma20" in a and "gap" in a and "slope" in a)
    print(f"✅ 주봉분석 셀프테스트 ({ok}/13)")
    return ok == 13


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest(); return
    run()


if __name__ == "__main__":
    main()
