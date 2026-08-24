#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""오늘_상승종목_분류.py — 오늘 상승 종목 리스트업 + 다차원 분류표

수집 방식은 30년 패널과 동일하게 **날짜별**(get_market_ohlcv(날짜, market=))이다.
그날 거래된 전 종목을 통째로 받으므로 생존편향이 없고, 상폐예정 종목도 빠지지 않는다.

분류 축 (진우 요청):
  · 시장       KOSPI / KOSDAQ
  · 등락·거래   등락률, 거래량 배수(20일 평균 대비), 거래대금, 상한가 여부
  · 테마       theme_heat 소속 + heat 순위 + 진우 워치리스트 여부
  · 재무       매출·영업이익·순이익(최근 결산), 흑자 여부, 매출 YoY, PER, PBR
  · 차트 위치   일봉(MA5/20/60/120 이격, 52주 고점대비, 위치라벨)
              주봉(5주선 위/아래 — 진우가 쓰는 기법, 주봉 위치)
              월봉(월봉 위치, 12개월 추세)

차트 위치는 30년 패널(...\종목일봉_30년_*.csv)에 오늘/전일을 이어붙여 계산한다.

⚠️ 이 표는 **서술적 분류**다. 매수/매도 신호가 아니다. 위치 라벨은 사실 기술이다.
   결정과 책임은 본인.

산출:
  가상매매\검증\오늘_상승종목_분류_YYYYMMDD.xlsx   ← 필터 가능한 분류표
  가상매매\검증\오늘_상승종목_분류_YYYYMMDD.md    ← 요약

사용:
  py 오늘_상승종목_분류.py                  (오늘, 등락률 ≥ 5% + 상한가 전부)
  py 오늘_상승종목_분류.py --min-rise 3     (기준 완화)
  py 오늘_상승종목_분류.py --date 20260715  (특정일)
  py 오늘_상승종목_분류.py --all            (상승 전 종목)
  py 오늘_상승종목_분류.py --self-test
"""
import os, sys, argparse
from datetime import date, datetime, timedelta
import warnings
warnings.filterwarnings("ignore")

BASE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(BASE, "가상매매", "검증")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

MIN_HISTORY = 60           # 차트 위치 계산 최소 이력(거래일)
LIMIT_UP_KOSPI = 29.0      # 상한가 근사 임계(±30%)
VOL_AVG_DAYS = 20


# ───────────────────────── 수집 (PC 전용) ─────────────────────────
def _prev_trading_days(pd, stock, ymd, n=3):
    """ymd 이전(포함) 최근 영업일 n개 — 캘린더 역주행."""
    out, d = [], datetime.strptime(ymd, "%Y%m%d")
    tries = 0
    while len(out) < n and tries < 15:
        s = d.strftime("%Y%m%d")
        try:
            df = stock.get_market_ohlcv(s, market="KOSPI")
            if len(df) > 100 and df["거래량"].sum() > 0:
                out.append(s)
        except Exception:
            pass
        d -= timedelta(days=1)
        tries += 1
    return out[::-1]


def fetch_today(pd, ymd):
    """오늘(ymd) 전 종목 OHLCV + 등락률 + 시총 + PER/PBR. 시장 라벨 포함."""
    from pykrx import stock
    frames = []
    for mkt in ("KOSPI", "KOSDAQ"):
        oh = stock.get_market_ohlcv(ymd, market=mkt)
        if oh is None or len(oh) == 0:
            continue
        oh = oh.rename(columns={"시가": "open", "고가": "high", "저가": "low",
                                "종가": "close", "거래량": "volume",
                                "거래대금": "value", "등락률": "chg"})
        oh["code"] = [str(c).zfill(6) for c in oh.index]
        oh["market"] = mkt
        # 시가총액 / 상장주식수
        try:
            cap = stock.get_market_cap(ymd, market=mkt)
            cap = cap.rename(columns={"시가총액": "mcap", "상장주식수": "shares"})
            cap["code"] = [str(c).zfill(6) for c in cap.index]
            oh = oh.merge(cap[["code", "mcap"]], on="code", how="left")
        except Exception:
            oh["mcap"] = float("nan")
        # PER/PBR/EPS/BPS
        try:
            fu = stock.get_market_fundamental(ymd, market=mkt)
            fu["code"] = [str(c).zfill(6) for c in fu.index]
            keep = [c for c in ["PER", "PBR", "EPS", "BPS", "DIV"] if c in fu.columns]
            oh = oh.merge(fu[["code"] + keep], on="code", how="left")
        except Exception:
            pass
        frames.append(oh)
    if not frames:
        return None
    df = pd.concat(frames, ignore_index=True)
    return df


def fetch_history_tail(pd, ymd_list):
    """패널 이후 공백(예: 07-14)과 오늘을 by-date로 받아 이어붙일 조각."""
    from pykrx import stock
    rows = []
    for ymd in ymd_list:
        for mkt in ("KOSPI", "KOSDAQ"):
            try:
                oh = stock.get_market_ohlcv(ymd, market=mkt)
                if oh is None or len(oh) == 0:
                    continue
                oh = oh.rename(columns={"시가": "open", "고가": "high", "저가": "low",
                                        "종가": "close", "거래량": "volume"})
                d = pd.to_datetime(ymd)
                for c in oh.index:
                    r = oh.loc[c]
                    rows.append({"date": d, "code": str(c).zfill(6),
                                 "close": float(r["close"]), "volume": float(r["volume"]),
                                 "high": float(r["high"]), "low": float(r["low"])})
            except Exception:
                pass
    return pd.DataFrame(rows)


# ───────────────────────── 로컬 데이터 ─────────────────────────
def load_panel(pd, codes, need_from):
    """30년 패널에서 대상 종목의 이력만 로드. need_from 이후만."""
    frames = []
    cset = set(codes)
    for m in ("KOSPI", "KOSDAQ"):
        p = os.path.join(BASE, f"종목일봉_30년_{m}.csv")
        if not os.path.exists(p):
            continue
        # 청크로 읽어 대상 종목만 추출 (메모리 절약)
        for ch in pd.read_csv(p, usecols=["date", "code", "close", "high", "low", "volume"],
                              dtype={"code": str}, encoding="utf-8-sig", chunksize=1_000_000):
            ch = ch[ch["code"].isin(cset)]
            if len(ch):
                ch = ch.copy()
                ch["date"] = pd.to_datetime(ch["date"], errors="coerce")
                ch = ch[ch["date"] >= need_from]
                frames.append(ch)
    if not frames:
        return pd.DataFrame(columns=["date", "code", "close", "high", "low", "volume"])
    return pd.concat(frames, ignore_index=True)


def load_names(pd):
    out = {}
    for f in ("liquidity_sector.csv", "kosdaq_industry.csv"):
        p = os.path.join(BASE, f)
        if os.path.exists(p):
            try:
                d = pd.read_csv(p, dtype={"code": str})
                for _, r in d.iterrows():
                    c = str(r["code"]).zfill(6)
                    if c not in out:
                        out[c] = {"name": r.get("name"), "sector": r.get("sector")}
            except Exception:
                pass
    return out


def load_themes(pd):
    """code → (theme, heat_rank, 진우워치 여부)."""
    tmap, rank = {}, {}
    p = os.path.join(BASE, "theme_heat_members_latest.csv")
    hl = os.path.join(BASE, "theme_heat_latest.csv")
    order = {}
    if os.path.exists(hl):
        try:
            h = pd.read_csv(hl, encoding="utf-8-sig")
            for _, r in h.iterrows():
                order[str(r["theme"])] = int(r["rank"])
        except Exception:
            pass
    if os.path.exists(p):
        try:
            m = pd.read_csv(p, dtype={"code": str}, encoding="utf-8-sig")
            for _, r in m.iterrows():
                c = str(r["code"]).zfill(6)
                th = str(r["theme"])
                if c not in tmap:
                    tmap[c] = th
                    rank[c] = order.get(th, 99)
        except Exception:
            pass
    watch = set()
    w = os.path.join(BASE, "kosdaq_theme_watchlist_진우기입.csv")
    if os.path.exists(w):
        try:
            d = pd.read_csv(w, dtype={"code": str}, encoding="utf-8-sig")
            watch = {str(c).zfill(6) for c in d["code"]}
        except Exception:
            pass
    return tmap, rank, watch


def load_fundamentals(pd):
    """code → 최근 결산 매출/영익/순익 + 전년 매출(YoY용)."""
    fund = {}
    for f in ("fundamentals_pit.csv", "_rf_f.csv", "fundamentals_kosdaq.csv"):
        p = os.path.join(BASE, f)
        if not os.path.exists(p):
            continue
        try:
            d = pd.read_csv(p, dtype={"code": str}, encoding="utf-8-sig")
            d = d.dropna(subset=["fiscal_year"])
            d["fiscal_year"] = pd.to_numeric(d["fiscal_year"], errors="coerce")
            for c, sub in d.groupby("code"):
                c = str(c).zfill(6)
                sub = sub.sort_values("fiscal_year")
                last = sub.iloc[-1]
                prev_rev = sub.iloc[-2]["revenue"] if len(sub) >= 2 else float("nan")
                rec = {"fy": int(last["fiscal_year"]),
                       "rev": last.get("revenue"), "op": last.get("op_income"),
                       "ni": last.get("net_income"), "prev_rev": prev_rev}
                # 여러 소스: 더 최신 결산이 있으면 갱신
                if c not in fund or rec["fy"] >= fund[c]["fy"]:
                    fund[c] = rec
        except Exception:
            pass
    return fund


# ───────────────────────── 차트 위치 ─────────────────────────
def chart_position(pd, np, hist_code):
    """한 종목의 이력(date 오름차순 close/high/low)으로 일/주/월봉 위치 산출."""
    h = hist_code.sort_values("date")
    px = h["close"].astype(float).values
    hi = h["high"].astype(float).values if "high" in h else px
    lo = h["low"].astype(float).values if "low" in h else px
    n = len(px)
    if n < MIN_HISTORY:
        return None
    c = px[-1]

    def ma(k):
        return float(np.mean(px[-k:])) if n >= k else float("nan")
    ma5, ma20, ma60, ma120 = ma(5), ma(20), ma(60), ma(120)

    # 52주(약 250거래일) 고저
    w = px[-250:] if n >= 250 else px
    hi52 = float(np.max(w)); lo52 = float(np.min(w))
    from_high = (c / hi52 - 1) * 100 if hi52 > 0 else float("nan")
    from_low = (c / lo52 - 1) * 100 if lo52 > 0 else float("nan")
    disp20 = (c / ma20 - 1) * 100 if ma20 > 0 else float("nan")

    # 일봉 위치 라벨
    if hi52 > 0 and c >= 0.97 * hi52:
        d_label = "신고가권"
    elif ma20 > 0 and ma60 > 0 and c > ma20 > ma60:
        d_label = "상승추세"
    elif ma60 > 0 and ma20 > 0 and c < ma20 and ma20 > ma60 and c > ma60:
        d_label = "눌림목"
    elif lo52 > 0 and c <= 1.10 * lo52:
        d_label = "바닥권"
    elif ma20 > 0 and ma60 > 0 and c < ma60 < ma20:
        d_label = "하락추세"
    else:
        d_label = "횡보"

    # 주봉 — 리샘플
    hh = h.set_index("date")
    wk = hh["close"].resample("W-FRI").last().dropna()
    w5 = float(wk.tail(5).mean()) if len(wk) >= 5 else float("nan")
    w20 = float(wk.tail(20).mean()) if len(wk) >= 20 else float("nan")
    if len(wk) >= 5 and not np.isnan(w5):
        wk_label = "5주선 위" if c >= w5 else "5주선 아래"
        if len(wk) >= 20 and not np.isnan(w20):
            wk_label += (" · 중기상승" if w5 >= w20 else " · 중기하락")
    else:
        wk_label = "이력부족"

    # 월봉 — 리샘플
    mo = hh["close"].resample("ME").last().dropna()
    m6 = float(mo.tail(6).mean()) if len(mo) >= 6 else float("nan")
    if len(mo) >= 13:
        yoy = (c / float(mo.iloc[-13]) - 1) * 100
    elif len(mo) >= 2:
        yoy = (c / float(mo.iloc[0]) - 1) * 100
    else:
        yoy = float("nan")
    if not np.isnan(m6):
        mo_label = "월봉 상승" if c >= m6 else "월봉 하락"
    else:
        mo_label = "이력부족"

    return {
        "MA5": ma5, "MA20": ma20, "MA60": ma60, "MA120": ma120,
        "이격도20%": round(disp20, 1),
        "52주고점대비%": round(from_high, 1), "52주저점대비%": round(from_low, 1),
        "일봉위치": d_label,
        "주봉위치": wk_label, "5주선": round(w5, 0) if not np.isnan(w5) else None,
        "월봉위치": mo_label, "12개월수익%": round(yoy, 1) if not np.isnan(yoy) else None,
    }


# ───────────────────────── 조립 ─────────────────────────
def build_table(pd, np, today_df, hist, names, themes, ranks, watch, fund, min_rise, want_all):
    tmap = themes
    # 상승 필터
    g = today_df[today_df["chg"].notna()].copy()
    g = g[g["chg"] > (0.0 if want_all else min_rise)]
    g["상한가"] = g["chg"] >= LIMIT_UP_KOSPI
    g = g.sort_values("chg", ascending=False)

    # 거래량 배수: 패널에서 종목별 최근 20일 평균
    hh = hist.sort_values(["code", "date"])
    volavg = (hh.groupby("code")["volume"]
              .apply(lambda s: s.tail(VOL_AVG_DAYS + 1)[:-1].mean() if len(s) > 1 else np.nan))
    volavg = volavg.to_dict()

    out = []
    hist_by = {c: sub for c, sub in hh.groupby("code")}
    for _, r in g.iterrows():
        c = r["code"]
        info = names.get(c, {}) or {}
        nm = info.get("name") or ""
        sec = info.get("sector") or ""
        va = volavg.get(c, np.nan)
        vmult = (r["volume"] / va) if (va and va > 0) else np.nan
        f = fund.get(c, {})
        rev = f.get("rev"); op = f.get("op"); ni = f.get("ni"); pr = f.get("prev_rev")
        yoy = ((rev / pr - 1) * 100) if (rev and pr and pr > 0) else np.nan
        row = {
            "코드": c, "종목명": nm, "시장": r["market"],
            "등락률%": round(float(r["chg"]), 2),
            "종가": int(r["close"]) if pd.notna(r["close"]) else None,
            "상한가": "★" if r["상한가"] else "",
            "거래량배수": round(float(vmult), 1) if pd.notna(vmult) else None,
            "거래대금억": round(float(r.get("value", np.nan)) / 1e8, 0) if pd.notna(r.get("value", np.nan)) else None,
            "시총억": round(float(r.get("mcap", np.nan)) / 1e8, 0) if pd.notna(r.get("mcap", np.nan)) else None,
            "이상치": "데이터확인" if float(r["chg"]) > 32.0 else "",
            "업종": sec,
            "테마": tmap.get(c, ""), "테마heat순위": ranks.get(c, ""),
            "진우워치": "Y" if c in watch else "",
            "결산": f.get("fy", ""),
            "매출억": round(rev / 1e8, 0) if rev and pd.notna(rev) else None,
            "영업이익억": round(op / 1e8, 0) if op and pd.notna(op) else None,
            "순이익억": round(ni / 1e8, 0) if ni and pd.notna(ni) else None,
            "흑자": ("흑자" if (op and op > 0) else ("적자" if (op is not None and pd.notna(op)) else "")),
            "매출YoY%": round(float(yoy), 1) if pd.notna(yoy) else None,
            "PER": round(float(r["PER"]), 1) if pd.notna(r.get("PER", np.nan)) and r.get("PER", 0) not in (0,) else None,
            "PBR": round(float(r["PBR"]), 2) if pd.notna(r.get("PBR", np.nan)) and r.get("PBR", 0) not in (0,) else None,
        }
        # 차트 위치
        sub = hist_by.get(c)
        cp = chart_position(pd, np, sub) if sub is not None else None
        if cp:
            row.update({
                "일봉위치": cp["일봉위치"], "이격도20%": cp["이격도20%"],
                "52주고점대비%": cp["52주고점대비%"],
                "주봉위치": cp["주봉위치"], "월봉위치": cp["월봉위치"],
                "12개월%": cp["12개월수익%"],
            })
        else:
            row.update({"일봉위치": "이력부족", "이격도20%": None, "52주고점대비%": None,
                        "주봉위치": "이력부족", "월봉위치": "이력부족", "12개월%": None})
        out.append(row)
    return pd.DataFrame(out)


COLS = ["코드", "종목명", "시장", "등락률%", "이상치", "종가", "상한가", "거래량배수",
        "거래대금억", "시총억", "업종", "테마", "테마heat순위", "진우워치", "결산",
        "매출억", "영업이익억", "순이익억", "흑자", "매출YoY%", "PER", "PBR",
        "일봉위치", "이격도20%", "52주고점대비%", "주봉위치", "월봉위치", "12개월%"]


def write_xlsx(pd, tbl, path, ymd):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    tbl = tbl.reindex(columns=COLS)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "분류표"

    hdr = Font(bold=True, color="FFFFFF", size=10)
    hf = PatternFill("solid", fgColor="2E5B3E")
    up = PatternFill("solid", fgColor="FDECEA")   # 상한가 강조
    thin = Side(style="thin", color="DDDDDD")
    bd = Border(left=thin, right=thin, top=thin, bottom=thin)

    ws.append([f"오늘 상승 종목 분류표 · {ymd} · {len(tbl)}종목 · 서술적 분류(매매신호 아님)"])
    ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(COLS))
    ws["A1"].font = Font(bold=True, size=12)
    ws.append(COLS)
    for c in range(1, len(COLS) + 1):
        cell = ws.cell(row=2, column=c)
        cell.font = hdr; cell.fill = hf; cell.border = bd
        cell.alignment = Alignment(horizontal="center", vertical="center")

    for _, r in tbl.iterrows():
        ws.append([r.get(c) for c in COLS])
        row = ws.max_row
        if r.get("상한가") == "★":
            for c in range(1, len(COLS) + 1):
                ws.cell(row=row, column=c).fill = up

    widths = {"코드": 8, "종목명": 12, "시장": 7, "업종": 12, "테마": 12, "일봉위치": 10,
              "주봉위치": 16, "월봉위치": 10, "이상치": 10}
    for i, c in enumerate(COLS, 1):
        ws.column_dimensions[get_column_letter(i)].width = widths.get(c, 9)
    ws.freeze_panes = "C3"
    ws.auto_filter.ref = f"A2:{get_column_letter(len(COLS))}{ws.max_row}"

    # 테마별 집계 시트
    ws2 = wb.create_sheet("테마별집계")
    if len(tbl):
        agg = (tbl.assign(테마=tbl["테마"].replace("", "(미분류)"))
               .groupby("테마").agg(종목수=("코드", "size"),
                                   평균등락=("등락률%", "mean"),
                                   상한가=("상한가", lambda s: (s == "★").sum()))
               .sort_values("종목수", ascending=False).reset_index())
        ws2.append(["테마", "종목수", "평균등락%", "상한가수"])
        for _, r in agg.iterrows():
            ws2.append([r["테마"], int(r["종목수"]), round(float(r["평균등락"]), 1), int(r["상한가"])])
        for c in range(1, 5):
            ws2.cell(row=1, column=c).font = hdr
            ws2.cell(row=1, column=c).fill = hf
        for i, wv in enumerate([16, 8, 10, 8], 1):
            ws2.column_dimensions[get_column_letter(i)].width = wv

    wb.save(path)


def write_md(pd, tbl, path, ymd):
    L = [f"# 오늘 상승 종목 분류 · {ymd}\n",
         f"\n*{len(tbl)}종목 · 서술적 분류(매매 신호 아님) · 결정·책임은 본인*\n\n"]
    if not len(tbl):
        L.append("상승 종목 없음(또는 데이터 없음).\n")
        open(path, "w", encoding="utf-8").write("".join(L)); return
    lu = tbl[tbl["상한가"] == "★"]
    L.append(f"- 상한가: **{len(lu)}종목**\n")
    L.append(f"- 최고 등락률: {tbl['등락률%'].max():.1f}% ({tbl.iloc[0]['종목명']})\n")
    # 테마 집계
    ag = (tbl.assign(테마=tbl["테마"].replace("", "(미분류)"))
          .groupby("테마").size().sort_values(ascending=False).head(8))
    L.append("\n## 테마별 (상위)\n\n| 테마 | 종목수 |\n|---|---|\n")
    for th, n in ag.items():
        L.append(f"| {th} | {n} |\n")
    L.append("\n## 상한가 종목\n\n")
    if len(lu):
        L.append("| 종목 | 시장 | 테마 | 일봉위치 | 주봉위치 |\n|---|---|---|---|---|\n")
        for _, r in lu.iterrows():
            L.append(f"| {r['종목명']}({r['코드']}) | {r['시장']} | {r['테마']} | "
                     f"{r['일봉위치']} | {r['주봉위치']} |\n")
    else:
        L.append("없음\n")
    L.append("\n*상세는 xlsx 분류표 참조.*\n")
    open(path, "w", encoding="utf-8").write("".join(L))


# ───────────────────────── 셀프테스트 ─────────────────────────
def _self_test():
    import pandas as pd, numpy as np
    ok = tot = 0

    def chk(n, c):
        nonlocal ok, tot
        tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")

    # 차트 위치 — 합성 이력
    dates = pd.bdate_range("2024-01-01", periods=300)
    # 상승추세: 꾸준히 오르는 시계열
    up = pd.DataFrame({"date": dates,
                       "close": np.linspace(100, 300, 300),
                       "high": np.linspace(100, 300, 300) * 1.01,
                       "low": np.linspace(100, 300, 300) * 0.99})
    cp = chart_position(pd, np, up)
    chk("상승추세 이력 → 위치 계산됨", cp is not None)
    chk("신고가 근처 → 신고가권/상승추세",
        cp["일봉위치"] in ("신고가권", "상승추세"))
    chk("5주선 위", "5주선 위" in cp["주봉위치"])
    chk("MA20 < 현재가(상승중)", cp["MA20"] < 300)

    # 바닥권: 하락 후 저점
    down = pd.DataFrame({"date": dates,
                         "close": np.linspace(300, 100, 300),
                         "high": np.linspace(300, 100, 300) * 1.01,
                         "low": np.linspace(300, 100, 300) * 0.99})
    cp2 = chart_position(pd, np, down)
    chk("하락추세 → 하락/바닥 라벨",
        cp2["일봉위치"] in ("하락추세", "바닥권", "횡보"))
    chk("하락추세 5주선 아래", "5주선 아래" in cp2["주봉위치"])

    # 이력 부족
    short = pd.DataFrame({"date": dates[:30], "close": np.arange(30) + 100.0,
                          "high": np.arange(30) + 101.0, "low": np.arange(30) + 99.0})
    chk("이력 60일 미만 → None", chart_position(pd, np, short) is None)

    # 등락 필터 + 상한가
    td = pd.DataFrame({"code": ["A", "B", "C", "D"], "market": ["KOSPI"] * 4,
                       "chg": [30.0, 7.0, 2.0, -1.0], "close": [1000] * 4,
                       "volume": [100] * 4, "value": [1e9] * 4, "mcap": [1e11] * 4})
    hist = pd.DataFrame({"code": [], "date": [], "close": [], "high": [], "low": [], "volume": []})
    tbl = build_table(pd, np, td, hist, {}, {}, {}, set(), {}, min_rise=5.0, want_all=False)
    chk("등락률 5% 필터 → 2종목(A,B)", len(tbl) == 2)
    chk("상한가 A 표시", (tbl[tbl["코드"] == "A"]["상한가"] == "★").all())
    chk("정렬: A가 첫 행", tbl.iloc[0]["코드"] == "A")

    # 재무 흑자/적자
    fund = {"A": {"fy": 2025, "rev": 1e12, "op": 5e10, "ni": 3e10, "prev_rev": 8e11}}
    tbl2 = build_table(pd, np, td, hist, {}, {}, {}, set(), fund, 5.0, False)
    ra = tbl2[tbl2["코드"] == "A"].iloc[0]
    chk("영익>0 → 흑자", ra["흑자"] == "흑자")
    chk("매출YoY 계산", abs(ra["매출YoY%"] - 25.0) < 0.5)

    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot


# ───────────────────────── 메인 ─────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYYMMDD (기본: 오늘)")
    ap.add_argument("--min-rise", type=float, default=5.0)
    ap.add_argument("--all", action="store_true", help="상승 전 종목")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()

    if a.self_test:
        return 0 if _self_test() else 1

    import pandas as pd, numpy as np
    ymd = a.date or datetime.now().strftime("%Y%m%d")

    print(f"[1/5] 오늘({ymd}) 전 종목 수집...")
    try:
        from pykrx import stock
    except ImportError:
        print("  pykrx 없음. pip install pykrx"); return 2
    # 실제 영업일 보정
    tdays = _prev_trading_days(pd, stock, ymd, n=1)
    if tdays:
        ymd = tdays[-1]
    today_df = fetch_today(pd, ymd)
    if today_df is None or len(today_df) == 0:
        print(f"  {ymd} 데이터 없음(휴장?)."); return 2
    print(f"  {len(today_df):,}종목 수신")

    print("[2/5] 상승 종목 선별...")
    ng = int((today_df["chg"] > (0 if a.all else a.min_rise)).sum())
    print(f"  기준 {'전 상승' if a.all else f'등락률 ≥ {a.min_rise}%'} → {ng}종목")
    codes = today_df[today_df["chg"] > (0 if a.all else a.min_rise)]["code"].tolist()

    print("[3/5] 차트 이력 로드(30년 패널 + 최근 공백 보정)...")
    # 패널 이후 공백일 + 오늘을 by-date로 보충
    gap = _prev_trading_days(pd, stock, ymd, n=3)
    tail = fetch_history_tail(pd, gap)
    need_from = pd.Timestamp(ymd) - pd.Timedelta(days=420)
    hist = load_panel(pd, codes, need_from)
    if len(tail):
        tail = tail[tail["code"].isin(set(codes))]
        hist = pd.concat([hist, tail], ignore_index=True).drop_duplicates(
            subset=["code", "date"], keep="last")
    print(f"  이력 {len(hist):,}행 · {hist['code'].nunique()}종목")

    print("[4/5] 테마·재무 조인...")
    names = load_names(pd)
    themes, ranks, watch = load_themes(pd)
    fund = load_fundamentals(pd)

    tbl = build_table(pd, np, today_df, hist, names, themes, ranks, watch, fund,
                      a.min_rise, a.all)
    print(f"  분류표 {len(tbl)}행 생성")

    print("[5/5] 저장...")
    os.makedirs(OUTDIR, exist_ok=True)
    xp = os.path.join(OUTDIR, f"오늘_상승종목_분류_{ymd}.xlsx")
    mp = os.path.join(OUTDIR, f"오늘_상승종목_분류_{ymd}.md")
    write_xlsx(pd, tbl, xp, ymd)
    write_md(pd, tbl, mp, ymd)
    print(f"\n  ✅ {xp}")
    print(f"  ✅ {mp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
# end
