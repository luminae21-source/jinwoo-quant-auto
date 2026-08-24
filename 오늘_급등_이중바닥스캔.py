#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""오늘_급등_이중바닥스캔.py — 오늘 급등 종목 중 '이중바닥(2번 바닥 딛고 상승)' 사이클 스캔

`오늘_상승종목_분류.py`와 **유니버스는 동일**(오늘 등락률 ≥5% + 상한가)하되,
목적이 다르다. 분류표는 '오른 종목의 사후 분류', 이 스캔은 사이클 매매 관점에서
**이중바닥에서 2번 바닥을 딛고 올라오는 자리**를 걸러낸다.

진우 요청 순서:
  1) 주봉(週) 이중바닥을 1차로 분석  ← 중기 사이클, 5주선 기법과 결
  2) 일봉(日) 이중바닥을 2차 확인    ← 단기 타이밍

이중바닥 판정(진우 확정):
  · 2번 바닥이 1번 바닥과 **비슷**(±허용오차) + **최근 반등**  → 이중바닥 = Y
  · 구조는 있으나 아직 2번 바닥에 **근접**(반등 전)              → 이중바닥 = 근접
  · 사이 고점(넥라인)이 두 바닥보다 충분히 높아야 진짜 'W'
  단계: 바닥형성 → 반등초입 → 넥라인돌파

수집·패널·테마·재무·chart_position 은 오늘_상승종목_분류.py를 그대로 import 재활용.

⚠️ 서술적 스캔이다. '반등초입', '넥라인돌파'는 사실 기술이지 매수 신호가 아니다.
   결정과 책임은 본인.

산출:
  가상매매\검증\오늘_급등_이중바닥_YYYYMMDD.xlsx  (이중바닥(주봉) + 전체스캔 2시트)
  가상매매\검증\오늘_급등_이중바닥_YYYYMMDD.md   (요약)

사용:
  py 오늘_급등_이중바닥스캔.py                (오늘, ≥5% + 상한가)
  py 오늘_급등_이중바닥스캔.py --min-rise 15   (급등만)
  py 오늘_급등_이중바닥스캔.py --date 20260715
  py 오늘_급등_이중바닥스캔.py --self-test
"""
import os, sys, argparse, importlib.util
from datetime import datetime
import warnings
warnings.filterwarnings("ignore")

BASE = os.path.dirname(os.path.abspath(__file__))
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ── 기존 도구 재활용 (수집/패널/조인/차트위치) ──
def _load_base():
    p = os.path.join(BASE, "오늘_상승종목_분류.py")
    spec = importlib.util.spec_from_file_location("jq_today_base", p)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

base = _load_base()
OUTDIR = base.OUTDIR

# ── 이중바닥 파라미터 (주봉/일봉 별도) ──
WK = dict(k=3, tol=0.08, neck=0.10, min_gap=3,  max_gap=40, recency=16, rebound=0.03, near=0.05, min_bars=30)
DY = dict(k=5, tol=0.06, neck=0.08, min_gap=8,  max_gap=90, recency=45, rebound=0.03, near=0.05, min_bars=60)
NECK_NEAR = -5.0   # 넥라인 근접 기준: 주봉_넥라인대비%가 이 값 이상(= 넥라인 -5% 이내 ~ 돌파)


# ───────────────────────── 이중바닥 코어 ─────────────────────────
def _zigzag(vals, k):
    """지그재그 피벗(교대 L/H) — 각 지점이 ±k 창에서 최소/최대면 피벗."""
    n = len(vals)
    piv = []
    for i in range(n):
        lo = max(0, i - k); hi = min(n - 1, i + k)
        seg = vals[lo:hi + 1]
        v = vals[i]
        if v <= min(seg):
            piv.append([i, "L", float(v)])
        elif v >= max(seg):
            piv.append([i, "H", float(v)])
    # 같은 타입 연속이면 극값만 유지 → 교대 시퀀스
    out = []
    for p in piv:
        if out and out[-1][1] == p[1]:
            if (p[1] == "L" and p[2] < out[-1][2]) or (p[1] == "H" and p[2] > out[-1][2]):
                out[-1] = p
        else:
            out.append(p)
    return out


def detect_double_bottom(vals, par):
    """vals: 종가 시퀀스(오름차순, 마지막이 최신). 이중바닥 구조 감지.
    반환 dict 또는 None. par: WK/DY 파라미터."""
    n = len(vals)
    if n < par["min_bars"]:
        return {"flag": "이력부족"}
    z = _zigzag(vals, par["k"])
    lows = [j for j, p in enumerate(z) if p[1] == "L"]
    if len(lows) < 2:
        return None
    j2, j1 = lows[-1], lows[-2]
    highs_between = [p for p in z[j1 + 1:j2] if p[1] == "H"]
    if not highs_between:
        return None
    neck = max(highs_between, key=lambda p: p[2])
    t1, t2 = z[j1], z[j2]
    b1, b2, nk = t1[2], t2[2], neck[2]
    i1, i2 = t1[0], t2[0]

    gap = i2 - i1
    if gap < par["min_gap"] or gap > par["max_gap"]:
        return None
    # 2번 바닥이 최근이어야(지금 자리)
    since = (n - 1) - i2
    if since > par["recency"]:
        return None
    # 두 바닥 유사 (2번이 1번보다 크게 낮으면 실패)
    sim = abs(b2 / b1 - 1) if b1 > 0 else 9.9
    if sim > par["tol"] or b2 < b1 * (1 - par["tol"]):
        return None
    # 넥라인이 바닥보다 충분히 높아야 진짜 W
    base_lvl = (b1 + b2) / 2.0
    if base_lvl <= 0 or nk < base_lvl * (1 + par["neck"]):
        return None

    c = float(vals[-1])
    over_neck = (c / nk - 1) * 100 if nk > 0 else float("nan")
    up_from_b2 = (c / b2 - 1) if b2 > 0 else 0.0

    if c >= nk:
        stage = "넥라인돌파"
    elif up_from_b2 >= par["rebound"]:
        stage = "반등초입"
    else:
        stage = "바닥형성"

    # Y(반등 확인) vs 근접(아직 바닥)
    near = c <= b2 * (1 + par["near"])
    if stage in ("반등초입", "넥라인돌파"):
        flag = "Y"
    else:
        flag = "근접" if near else "Y"  # 바닥형성이지만 근접 아니면(살짝 위) 완만한 반등 취급 → Y

    return {"flag": flag, "stage": stage, "b1": b1, "b2": b2, "neck": nk,
            "sim_pct": round(sim * 100, 1), "over_neck_pct": round(over_neck, 1),
            "since": since, "i1": i1, "i2": i2}


def scan_one(pd, np, hist_code):
    """한 종목 이력 → 주봉/일봉 이중바닥 결과."""
    h = hist_code.sort_values("date")
    if len(h) < 40:
        return None
    hs = h.set_index("date")
    dclose = hs["close"].astype(float)
    wk = dclose.resample("W-FRI").last().dropna()

    d_vals = dclose.values[-160:]            # 일봉 최근 ~6개월
    w_vals = wk.values[-90:]                 # 주봉 최근 ~1.5년
    w = detect_double_bottom(w_vals, WK)
    d = detect_double_bottom(d_vals, DY)
    return {"wk": w, "dy": d}


# ───────────────────────── 조립 ─────────────────────────
SCAN_COLS = ["코드", "종목명", "시장", "등락률%", "상한가", "종가", "테마", "진우워치",
             "주봉_이중바닥", "주봉_단계", "주봉_1번바닥", "주봉_2번바닥", "주봉_바닥유사%",
             "주봉_넥라인", "주봉_넥라인대비%", "주봉_2번바닥경과주",
             "일봉_이중바닥", "일봉_단계", "일봉_넥라인대비%",
             "일봉위치", "주봉위치", "52주저점대비%", "거래량배수"]

_STAGE_RANK = {"넥라인돌파": 0, "반등초입": 1, "바닥형성": 2}
_FLAG_RANK = {"Y": 0, "근접": 1, "": 2, "이력부족": 3, None: 3}


def _fmt(res, key):
    if not res or res.get("flag") in (None, "이력부족"):
        return None
    return res.get(key)


def build_scan(pd, np, today_df, hist, names, themes, ranks, watch, min_rise, want_all):
    tmap = themes
    g = today_df[today_df["chg"].notna()].copy()
    g = g[g["chg"] > (0.0 if want_all else min_rise)]
    g["상한가"] = g["chg"] >= base.LIMIT_UP_KOSPI
    g = g.sort_values("chg", ascending=False)

    hh = hist.sort_values(["code", "date"])
    volavg = (hh.groupby("code")["volume"]
              .apply(lambda s: s.tail(base.VOL_AVG_DAYS + 1)[:-1].mean() if len(s) > 1 else np.nan)).to_dict()
    hist_by = {c: sub for c, sub in hh.groupby("code")}

    out = []
    for _, r in g.iterrows():
        c = r["code"]
        info = names.get(c, {}) or {}
        nm = info.get("name") or ""
        va = volavg.get(c, np.nan)
        vmult = (r["volume"] / va) if (va and va > 0) else np.nan
        sub = hist_by.get(c)
        sc = scan_one(pd, np, sub) if sub is not None and len(sub) else None
        cp = base.chart_position(pd, np, sub) if sub is not None and len(sub) else None

        w = sc["wk"] if sc else None
        d = sc["dy"] if sc else None
        w_flag = (w or {}).get("flag", "") if w else ""
        d_flag = (d or {}).get("flag", "") if d else ""
        if w_flag == "이력부족":
            w_flag = ""
        if d_flag == "이력부족":
            d_flag = ""

        row = {
            "코드": c, "종목명": nm, "시장": r["market"],
            "등락률%": round(float(r["chg"]), 2),
            "상한가": "★" if r["상한가"] else "",
            "종가": int(r["close"]) if pd.notna(r["close"]) else None,
            "테마": tmap.get(c, ""), "진우워치": "Y" if c in watch else "",
            "주봉_이중바닥": w_flag,
            "주봉_단계": _fmt(w, "stage") or "",
            "주봉_1번바닥": int(w["b1"]) if _fmt(w, "b1") else None,
            "주봉_2번바닥": int(w["b2"]) if _fmt(w, "b2") else None,
            "주봉_바닥유사%": _fmt(w, "sim_pct"),
            "주봉_넥라인": int(w["neck"]) if _fmt(w, "neck") else None,
            "주봉_넥라인대비%": _fmt(w, "over_neck_pct"),
            "주봉_2번바닥경과주": _fmt(w, "since"),
            "일봉_이중바닥": d_flag,
            "일봉_단계": _fmt(d, "stage") or "",
            "일봉_넥라인대비%": _fmt(d, "over_neck_pct"),
            "거래량배수": round(float(vmult), 1) if pd.notna(vmult) else None,
        }
        if cp:
            row.update({"일봉위치": cp["일봉위치"], "주봉위치": cp["주봉위치"],
                        "52주저점대비%": cp["52주저점대비%"]})
        else:
            row.update({"일봉위치": "이력부족", "주봉위치": "이력부족", "52주저점대비%": None})
        # 정렬 키
        row["_sk"] = (_FLAG_RANK.get(w_flag, 2),
                      _STAGE_RANK.get(row["주봉_단계"], 3),
                      -row["등락률%"])
        out.append(row)

    df = pd.DataFrame(out)
    if len(df):
        df = df.sort_values("_sk", key=lambda s: s, kind="stable")
        df = df.drop(columns=["_sk"])
    return df


# ───────────────────────── 산출 ─────────────────────────
def _neck_near(df):
    """넥라인 근접: 반등초입/넥라인돌파 중 넥라인대비% ≥ NECK_NEAR(-5%). 돌파 우선 정렬."""
    if not len(df):
        return df
    m = (df["주봉_단계"].isin(["반등초입", "넥라인돌파"]) &
         df["주봉_넥라인대비%"].notna() &
         (df["주봉_넥라인대비%"] >= NECK_NEAR))
    n = df[m].copy()
    if len(n):
        n = n.sort_values(["주봉_넥라인대비%"], ascending=False, kind="stable")
    return n


def write_xlsx(pd, df, path, ymd):
    import openpyxl
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
    from openpyxl.utils import get_column_letter
    df = df.reindex(columns=SCAN_COLS)

    wb = openpyxl.Workbook()
    hdr = Font(bold=True, color="FFFFFF", size=10)
    hf = PatternFill("solid", fgColor="1F3A5F")
    fill_break = PatternFill("solid", fgColor="D6EAD6")   # 넥라인돌파
    fill_early = PatternFill("solid", fgColor="EAF4EA")   # 반등초입
    fill_near = PatternFill("solid", fgColor="FBF3D9")    # 근접/바닥형성
    thin = Side(style="thin", color="DDDDDD")
    bd = Border(left=thin, right=thin, top=thin, bottom=thin)

    def _sheet(ws, data, title):
        ws.append([f"{title} · {ymd} · {len(data)}종목 · 서술적 스캔(매매신호 아님)"])
        ws.merge_cells(start_row=1, start_column=1, end_row=1, end_column=len(SCAN_COLS))
        ws["A1"].font = Font(bold=True, size=12)
        ws.append(SCAN_COLS)
        for cc in range(1, len(SCAN_COLS) + 1):
            cell = ws.cell(row=2, column=cc)
            cell.font = hdr; cell.fill = hf; cell.border = bd
            cell.alignment = Alignment(horizontal="center", vertical="center")
        for _, r in data.iterrows():
            ws.append([r.get(cc) for cc in SCAN_COLS])
            row = ws.max_row
            stg = r.get("주봉_단계")
            fl = r.get("주봉_이중바닥")
            fill = None
            if stg == "넥라인돌파":
                fill = fill_break
            elif stg == "반등초입":
                fill = fill_early
            elif fl in ("Y", "근접"):
                fill = fill_near
            if fill:
                for cc in range(1, len(SCAN_COLS) + 1):
                    ws.cell(row=row, column=cc).fill = fill
        widths = {"코드": 8, "종목명": 12, "시장": 7, "테마": 12, "주봉_단계": 11,
                  "일봉_단계": 11, "일봉위치": 10, "주봉위치": 16, "주봉_이중바닥": 11,
                  "일봉_이중바닥": 11}
        for i, cc in enumerate(SCAN_COLS, 1):
            ws.column_dimensions[get_column_letter(i)].width = widths.get(cc, 9)
        ws.freeze_panes = "C3"
        ws.auto_filter.ref = f"A2:{get_column_letter(len(SCAN_COLS))}{ws.max_row}"

    # 시트1: 이중바닥(주봉) — Y/근접만
    sel = df[df["주봉_이중바닥"].isin(["Y", "근접"])] if len(df) else df
    ws1 = wb.active; ws1.title = "이중바닥_주봉"
    _sheet(ws1, sel, "오늘 급등 · 주봉 이중바닥")
    # 시트2: 넥라인 근접(임박·돌파) — 반등초입 -5% 이내 + 넥라인돌파
    near = _neck_near(df)
    wsn = wb.create_sheet("넥라인근접")
    _sheet(wsn, near, "오늘 급등 · 넥라인 근접(임박·돌파)")
    # 시트3: 전체 스캔
    ws2 = wb.create_sheet("전체스캔")
    _sheet(ws2, df, "오늘 급등 전체 스캔")
    wb.save(path)


def write_md(pd, df, path, ymd):
    sel = df[df["주봉_이중바닥"].isin(["Y", "근접"])] if len(df) else df
    L = [f"# 오늘 급등 · 이중바닥 사이클 스캔 · {ymd}\n",
         f"\n*전체 급등 {len(df)}종목 · 주봉 이중바닥 {len(sel)}종목 · 서술적 스캔(매매신호 아님) · 결정·책임은 본인*\n\n"]
    if not len(df):
        L.append("급등 종목 없음(또는 데이터 없음).\n")
        open(path, "w", encoding="utf-8").write("".join(L)); return

    def _cnt(sub, stage):
        return int((sub["주봉_단계"] == stage).sum())

    y = df[df["주봉_이중바닥"] == "Y"]
    near = df[df["주봉_이중바닥"] == "근접"]
    L.append("## 주봉 이중바닥 요약\n\n")
    L.append(f"- 넥라인돌파: **{_cnt(df, '넥라인돌파')}**\n")
    L.append(f"- 반등초입: **{_cnt(df, '반등초입')}**\n")
    L.append(f"- 바닥형성: **{_cnt(df, '바닥형성')}**\n")
    L.append(f"- 2번바닥 근접: **{len(near)}**\n")
    L.append(f"- ⭐넥라인 임박·돌파(반등초입 -5% 이내 + 돌파): **{len(_neck_near(df))}**\n")

    def _tbl(sub, title):
        L.append(f"\n## {title} ({len(sub)})\n\n")
        if not len(sub):
            L.append("없음\n"); return
        L.append("| 종목 | 시장 | 등락률 | 주봉단계 | 1번/2번바닥 | 넥라인대비 | 일봉단계 |\n|---|---|---|---|---|---|---|\n")
        for _, r in sub.head(40).iterrows():
            b1 = r.get("주봉_1번바닥"); b2 = r.get("주봉_2번바닥")
            bb = f"{b1}/{b2}" if b1 and b2 else "-"
            on = r.get("주봉_넥라인대비%")
            on = f"{on:+.1f}%" if on is not None else "-"
            L.append(f"| {r['종목명']}({r['코드']}) | {r['시장']} | {r['등락률%']:.1f}% | "
                     f"{r['주봉_단계']}{'★' if r['상한가']=='★' else ''} | {bb} | {on} | {r.get('일봉_단계','') or '-'} |\n")

    _tbl(_neck_near(df), "⭐넥라인 임박·돌파 (반등초입 -5% 이내 + 넥라인돌파 · 임박순)")
    _tbl(df[df["주봉_단계"] == "넥라인돌파"], "넥라인돌파 (2번 바닥 딛고 넥라인 상향 돌파)")
    _tbl(df[df["주봉_단계"] == "반등초입"], "반등초입 (2번 바닥에서 상승 전환)")
    _tbl(near, "2번바닥 근접 (반등 전 · 관찰)")
    L.append("\n*상세·일봉 확인은 xlsx의 '이중바닥_주봉' 시트 참조. 라벨은 사실 기술이며 매매 신호가 아님.*\n")
    open(path, "w", encoding="utf-8").write("".join(L))


# ───────────────────────── 셀프테스트 ─────────────────────────
def _self_test():
    import numpy as np
    ok = tot = 0

    def chk(n, c):
        nonlocal ok, tot
        tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")

    # 합성 이중바닥(주봉급): 100→60(1번바닥)→90(넥라인)→62(2번바닥)→반등
    seg = (list(np.linspace(100, 60, 20)) + list(np.linspace(60, 90, 15)) +
           list(np.linspace(90, 62, 15)) + list(np.linspace(62, 80, 10)))
    r = detect_double_bottom(np.array(seg, float), WK)
    chk("이중바닥 감지됨", r is not None and r.get("flag") == "Y")
    chk("단계=반등초입/넥라인돌파", r and r.get("stage") in ("반등초입", "넥라인돌파"))
    chk("두 바닥 유사(<8%)", r and r.get("sim_pct", 99) <= 8.0)

    # 넥라인 돌파: 2번 바닥 후 넥라인 위로
    seg2 = (list(np.linspace(100, 60, 20)) + list(np.linspace(60, 90, 15)) +
            list(np.linspace(90, 62, 15)) + list(np.linspace(62, 95, 12)))
    r2 = detect_double_bottom(np.array(seg2, float), WK)
    chk("넥라인 돌파 판정", r2 and r2.get("stage") == "넥라인돌파")

    # 근접: 2번 바닥에서 아직 반등 전(마지막이 바닥 근처)
    seg3 = (list(np.linspace(100, 60, 20)) + list(np.linspace(60, 90, 15)) +
            list(np.linspace(90, 61, 16)))
    r3 = detect_double_bottom(np.array(seg3, float), WK)
    chk("바닥형성/근접 판정", r3 and (r3.get("stage") == "바닥형성" or r3.get("flag") == "근접"))

    # 단조 상승 → 이중바닥 아님
    up = np.linspace(50, 150, 90)
    chk("단조상승 → 이중바닥 아님", detect_double_bottom(up, WK) in (None,) or
        detect_double_bottom(up, WK).get("flag") not in ("Y", "근접"))

    # 단일 V자(바닥 1개) → 이중바닥 아님
    v = np.array(list(np.linspace(100, 60, 30)) + list(np.linspace(60, 120, 40)), float)
    rv = detect_double_bottom(v, WK)
    chk("단일 V → 이중바닥 아님", rv is None or rv.get("flag") not in ("Y", "근접"))

    # 2번 바닥이 1번보다 크게 낮음 → 실패(하락지속)
    lower2 = (list(np.linspace(100, 60, 20)) + list(np.linspace(60, 85, 12)) +
              list(np.linspace(85, 45, 18)) + list(np.linspace(45, 55, 8)))
    chk("2번 바닥 급하락 → 이중바닥 아님",
        (lambda x: x is None or x.get("flag") not in ("Y", "근접"))(detect_double_bottom(np.array(lower2, float), WK)))

    # 이력 부족
    chk("이력부족 → 라벨", detect_double_bottom(np.linspace(1, 10, 10), WK) == {"flag": "이력부족"})

    # zigzag 기본
    zz = _zigzag(np.array([5, 3, 1, 3, 5, 3, 1, 3, 6], float), 1)
    chk("zigzag 교대 피벗", len([p for p in zz if p[1] == "L"]) >= 2)

    # 재활용 모듈 로드
    chk("base 모듈 로드(chart_position)", hasattr(base, "chart_position"))
    chk("base 모듈 로드(fetch_today)", hasattr(base, "fetch_today"))

    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot


# ───────────────────────── 메인 ─────────────────────────
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYYMMDD (기본: 오늘)")
    ap.add_argument("--min-rise", type=float, default=5.0)
    ap.add_argument("--all", action="store_true")
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
    tdays = base._prev_trading_days(pd, stock, ymd, n=1)
    if tdays:
        ymd = tdays[-1]
    today_df = base.fetch_today(pd, ymd)
    if today_df is None or len(today_df) == 0:
        print(f"  {ymd} 데이터 없음(휴장?)."); return 2
    print(f"  {len(today_df):,}종목 수신")

    print("[2/5] 급등 종목 선별...")
    ng = int((today_df["chg"] > (0 if a.all else a.min_rise)).sum())
    print(f"  기준 {'전 상승' if a.all else f'등락률 ≥ {a.min_rise}%'} → {ng}종목")
    codes = today_df[today_df["chg"] > (0 if a.all else a.min_rise)]["code"].tolist()

    print("[3/5] 차트 이력 로드(30년 패널 + 최근 공백 보정)...")
    gap = base._prev_trading_days(pd, stock, ymd, n=3)
    tail = base.fetch_history_tail(pd, gap)
    need_from = pd.Timestamp(ymd) - pd.Timedelta(days=800)   # 주봉 이중바닥용 ~2년
    hist = base.load_panel(pd, codes, need_from)
    if len(tail):
        tail = tail[tail["code"].isin(set(codes))]
        hist = pd.concat([hist, tail], ignore_index=True).drop_duplicates(
            subset=["code", "date"], keep="last")
    print(f"  이력 {len(hist):,}행 · {hist['code'].nunique()}종목")

    print("[4/5] 테마 조인 + 이중바닥(주봉→일봉) 감지...")
    names = base.load_names(pd)
    themes, ranks, watch = base.load_themes(pd)
    df = build_scan(pd, np, today_df, hist, names, themes, ranks, watch, a.min_rise, a.all)
    nY = int((df["주봉_이중바닥"] == "Y").sum()) if len(df) else 0
    nN = int((df["주봉_이중바닥"] == "근접").sum()) if len(df) else 0
    print(f"  전체 {len(df)}종목 · 주봉 이중바닥 Y {nY} · 근접 {nN}")

    print("[5/5] 저장...")
    os.makedirs(OUTDIR, exist_ok=True)
    xp = os.path.join(OUTDIR, f"오늘_급등_이중바닥_{ymd}.xlsx")
    mp = os.path.join(OUTDIR, f"오늘_급등_이중바닥_{ymd}.md")
    write_xlsx(pd, df, xp, ymd)
    write_md(pd, df, mp, ymd)
    print(f"\n  ✅ {xp}")
    print(f"  ✅ {mp}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
# end
