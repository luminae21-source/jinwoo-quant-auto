#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""뷰생성.py — 그날의 데이터(분류표+거래대금+최근봉+패널)로 앱·모바일 HTML 뷰 생성

전제(먼저 실행돼 있어야 함):
  · 오늘_상승종목_분류.py     → 가상매매\검증\오늘_상승종목_분류_YYYYMMDD.xlsx
  · 거래대금_2주_수집.py      → _거래대금2주_YYYYMMDD.csv, _recent_ohlc_YYYYMMDD.csv
템플릿:
  · 가상매매\검증\_뷰엔진\_tmpl_app.html, _tmpl_mobile.html  (__META__/__CD__ 치환)

산출(당일):
  · 가상매매\검증\급등_이중바닥_거래대금_앱_YYYYMMDD.html
  · 가상매매\검증\급등_이중바닥_모바일_YYYYMMDD.html

차트는 이미지가 아니라 캔들 데이터를 담아 브라우저가 렌더 → 가볍고 빠름. matplotlib 불필요.

사용: py 뷰생성.py            (검증 폴더의 최신 분류표 날짜 사용)
      py 뷰생성.py --date 20260715
      py 뷰생성.py --self-test
"""
import os, sys, glob, json, argparse, importlib.util, re
import warnings
warnings.filterwarnings("ignore")

BASE = os.path.dirname(os.path.abspath(__file__))
OUTDIR = os.path.join(BASE, "가상매매", "검증")
ENGINE = os.path.join(OUTDIR, "_뷰엔진")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass


def _scan():
    p = os.path.join(BASE, "오늘_급등_이중바닥스캔.py")
    spec = importlib.util.spec_from_file_location("jq_scan", p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def _latest_ymd():
    fs = glob.glob(os.path.join(OUTDIR, "오늘_상승종목_분류_*.xlsx"))
    ds = sorted(re.findall(r"(\d{8})", os.path.basename(f))[0] for f in fs if re.search(r"\d{8}", f))
    return ds[-1] if ds else None


def _I(a):
    return [int(round(float(x))) for x in a]


def _ticks(pd, dates, k=5):
    import numpy as np
    n = len(dates); idx = np.linspace(0, n - 1, k).astype(int)
    return [[int(i), pd.to_datetime(dates[i]).strftime("%y/%m")] for i in idx]


def _bucket(s, pd):
    if pd.isna(s): return "미상"
    if s >= 10000: return "대형"
    if s >= 1000: return "중형"
    return "소형"


def build(ymd):
    import pandas as pd, numpy as np
    scan = _scan()
    xf = os.path.join(OUTDIR, f"오늘_상승종목_분류_{ymd}.xlsx")
    if not os.path.exists(xf):
        print(f"  분류표 없음: {xf}"); return None
    xd = pd.read_excel(xf, sheet_name=0, header=1)
    xd = xd[xd["코드"].notna()].copy(); xd["코드"] = xd["코드"].astype(str).str.zfill(6)
    codes = set(xd["코드"])

    valp = os.path.join(OUTDIR, f"_거래대금2주_{ymd}.csv")
    recp = os.path.join(OUTDIR, f"_recent_ohlc_{ymd}.csv")
    vmap = {}
    if os.path.exists(valp):
        v = pd.read_csv(valp, dtype={"code": str}); v["code"] = v["code"].str.zfill(6)
        vmap = {r["code"]: r for _, r in v.iterrows()}
    rec = pd.DataFrame(columns=["date", "code", "open", "high", "low", "close", "volume"])
    if os.path.exists(recp):
        rec = pd.read_csv(recp, dtype={"code": str})[["date", "code", "open", "high", "low", "close", "volume"]]
        rec["date"] = pd.to_datetime(rec["date"]); rec["code"] = rec["code"].str.zfill(6)

    # 패널 로드 (대상 종목만)
    print("  30년 패널 로드...")
    frames = []
    for m in ("KOSPI", "KOSDAQ"):
        p = os.path.join(BASE, f"종목일봉_30년_{m}.csv")
        if not os.path.exists(p):
            continue
        for ch in pd.read_csv(p, usecols=["date", "code", "open", "high", "low", "close", "volume"],
                              dtype={"code": str}, encoding="utf-8-sig", chunksize=1_000_000):
            ch = ch[ch["code"].isin(codes)]
            if len(ch):
                frames.append(ch.copy())
    pan = pd.concat(frames, ignore_index=True) if frames else pd.DataFrame(
        columns=["date", "code", "open", "high", "low", "close", "volume"])
    pan["date"] = pd.to_datetime(pan["date"]); pan["code"] = pan["code"].str.zfill(6)
    panlast = pan["date"].max() if len(pan) else pd.Timestamp("2000-01-01")
    allr = pd.concat([pan, rec[rec["date"] > panlast]], ignore_index=True) if len(rec) else pan
    allr = allr.drop_duplicates(["code", "date"], keep="last").sort_values(["code", "date"])
    byc = {c: g for c, g in allr.groupby("code")}
    print(f"  이력 {len(allr):,}행 · {len(byc)}종목")

    META, CD = [], {}
    for _, row in xd.iterrows():
        code = row["코드"]; nm = str(row["종목명"] or "")
        g = byc.get(code)
        if g is None or len(g) < 70:
            continue
        try:
            g = g.sort_values("date"); gd = g.set_index("date")
            dd = g.tail(130)
            wk = pd.DataFrame({"open": gd["open"].resample("W-FRI").first(),
                               "high": gd["high"].resample("W-FRI").max(),
                               "low": gd["low"].resample("W-FRI").min(),
                               "close": gd["close"].resample("W-FRI").last(),
                               "volume": gd["volume"].resample("W-FRI").sum()}).dropna().tail(85).reset_index()
            dc = dd["close"].values.astype(float); wc = wk["close"].values.astype(float)
            rd = scan.detect_double_bottom(dc, scan.DY); rw = scan.detect_double_bottom(wc, scan.WK)
            def dbi(r):
                if r and r.get("flag") in ("Y", "근접"):
                    return {"i1": int(r["i1"]), "i2": int(r["i2"]), "nk": float(r["neck"]), "st": r["stage"]}
                return None
            vinfo = vmap.get(code)
            ve = float(vinfo["거래대금2주합"]) / 1e8 if vinfo is not None else None
            avg = float(vinfo["일평균거래대금"]) / 1e8 if vinfo is not None else None
            tr = float(vinfo["추세배수"]) if vinfo is not None and pd.notna(vinfo["추세배수"]) else None
            wf = (rw or {}).get("flag", "") if rw else ""; wf = "" if wf == "이력부족" else wf
            dfl = (rd or {}).get("flag", "") if rd else ""; dfl = "" if dfl == "이력부족" else dfl
            base = {"c": code, "n": nm, "mk": row["시장"], "chg": round(float(row["등락률%"]), 2),
                    "cl": None if pd.isna(row["종가"]) else int(row["종가"]), "lim": row.get("상한가") == "★",
                    "th": "" if pd.isna(row.get("테마")) else row.get("테마"),
                    "sc": _bucket(row.get("시총억"), pd), "si": None if pd.isna(row.get("시총억")) else int(row.get("시총억")),
                    "hk": "" if pd.isna(row.get("흑자")) else row.get("흑자"),
                    "v2": None if ve is None else round(ve), "avg": None if avg is None else round(avg, 1),
                    "tr": None if tr is None else round(tr, 2),
                    "wf": wf, "ws": (rw or {}).get("stage", "") if rw and wf in ("Y", "근접") else "",
                    "wn": (rw or {}).get("over_neck_pct") if rw and wf in ("Y", "근접") else None, "df": dfl,
                    "ilp": "" if pd.isna(row.get("일봉위치")) else row.get("일봉위치"),
                    "jup": "" if pd.isna(row.get("주봉위치")) else row.get("주봉위치")}
            META.append(base)
            CD[code] = {"do": _I(dd["open"]), "dh": _I(dd["high"]), "dl": _I(dd["low"]), "dc": _I(dd["close"]),
                        "dv": _I(dd["volume"]), "dt": _ticks(pd, dd["date"].values),
                        "wo": _I(wk["open"]), "wh": _I(wk["high"]), "wl": _I(wk["low"]), "wc": _I(wk["close"]),
                        "wv": _I(wk["volume"]), "wt": _ticks(pd, wk["date"].values),
                        "dbd": dbi(rd), "dbw": dbi(rw)}
        except Exception as e:
            print(f"  skip {code} {nm}: {e}")
    META.sort(key=lambda x: (x.get("v2") or -1), reverse=True)
    return META, CD


def emit(ymd, META, CD):
    jm = json.dumps(META, ensure_ascii=False, separators=(",", ":"))
    jc = json.dumps(CD, ensure_ascii=False, separators=(",", ":"))
    out = []
    for tmpl, name in (("_tmpl_app.html", f"급등_이중바닥_거래대금_앱_{ymd}.html"),
                       ("_tmpl_mobile.html", f"급등_이중바닥_모바일_{ymd}.html")):
        tp = os.path.join(ENGINE, tmpl)
        if not os.path.exists(tp):
            print(f"  템플릿 없음: {tp}"); continue
        h = open(tp, encoding="utf-8").read().replace("__META__", jm).replace("__CD__", jc)
        # 제목/헤더 날짜 갱신(YYYY-MM-DD)
        dsp = f"{ymd[:4]}-{ymd[4:6]}-{ymd[6:]}"
        h = h.replace("20260715", ymd).replace("2026-07-15", dsp)
        op = os.path.join(OUTDIR, name)
        open(op, "w", encoding="utf-8").write(h)
        print(f"  ✅ {op} ({round(os.path.getsize(op)/1e6,2)}MB)")
        out.append(op)
    return out


def _self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    chk("템플릿(app) 존재", os.path.exists(os.path.join(ENGINE, "_tmpl_app.html")))
    chk("템플릿(mobile) 존재", os.path.exists(os.path.join(ENGINE, "_tmpl_mobile.html")))
    chk("스캔 모듈 로드", hasattr(_scan(), "detect_double_bottom"))
    chk("최신 분류표 날짜 탐색", _latest_ymd() is not None)
    for t in ("_tmpl_app.html", "_tmpl_mobile.html"):
        p = os.path.join(ENGINE, t)
        if os.path.exists(p):
            s = open(p, encoding="utf-8").read()
            chk(f"{t} 플레이스홀더", "__META__" in s and "__CD__" in s)
    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return 0 if _self_test() else 1
    ymd = a.date or _latest_ymd()
    if not ymd:
        print("분류표 xlsx를 찾을 수 없습니다. 먼저 오늘_상승종목_분류.py 실행."); return 2
    print(f"[뷰생성] 기준일 {ymd}")
    r = build(ymd)
    if not r:
        return 2
    META, CD = r
    print(f"  종목 {len(META)} · 이중바닥 Y {sum(1 for d in META if d['wf']=='Y')} · 근접 {sum(1 for d in META if d['wf']=='근접')}")
    emit(ymd, META, CD)
    print("[완료] 앱·모바일 HTML 생성")
    return 0


if __name__ == "__main__":
    sys.exit(main())
# end
