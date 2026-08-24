#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
시장영향_검증.py — 코스피 익일 수익률에 영향 끼치는 조건 통계 검증 (사전등록 기반)
==============================================================================
사전등록: 시장영향_검증_사전등록.md (조건·가설·합격선·다중비교 보정 고정).
A = 11개 전체 / B = 핵심 5개(SOX·S&P500·美10년·원달러·외국인) → A·B 비교.
합격선(데이터마이닝 방어): 방향가설 |t|≥2.3 + 부호일치 / 탐색 |t|≥3.0 / 다변량 생존 / OOS 양쪽 동일부호.
룩어헤드 차단: 모든 X는 d일까지 확정값 → 코스피 d+1(익일) 수익 예측. (당일은 보조 상관)
데이터: yfinance(^KS11·^GSPC·^SOX·^TNX·^IRX·CL=F·DX-Y.NYB·KRW=X) + pykrx(외국인) + breadth_features.csv + vkospi_daily.csv
산출: 시장영향_검증_결과.md · 시장영향_검증_raw.csv  ·  사용: python 시장영향_검증.py [--selftest]
무수정: production·기존 산출물. 신규(측정·통계). 예측 채택 아님 — 검증.
"""
import os, sys, csv, argparse
from datetime import date, timedelta

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
HERE = os.path.dirname(os.path.abspath(__file__))

# 조건 정의: key:(라벨, 가설부호 '+'/'-'/'?', 핵심B 여부, 임계|t|)
CONDS = [
    ("sox",     "전일 SOX 수익",        "+", True,  2.3),
    ("sp",      "전일 S&P500 수익",     "+", True,  2.3),
    ("tnx",     "美10년 Δbp",           "-", True,  2.3),
    ("krw",     "원/달러 Δ%",           "-", True,  2.3),
    ("foreign", "외국인 순매수(억)",     "+", True,  2.3),
    ("vkospi",  "VKOSPI 수준",          "?", False, 3.0),
    ("breadth", "breadth(MA20위%)",     "?", False, 3.0),
    ("curve",   "美커브 10y-13wk Δ",    "?", False, 3.0),
    ("wti",     "WTI 유가 Δ%",          "?", False, 3.0),
    ("dxy",     "달러인덱스 Δ%",        "-", True,  2.3),
    ("expiry",  "만기 더미(D-3~+1)",    "0", False, 99.0),
]
B_KEYS = {"sox", "sp", "tnx", "krw", "foreign"}


# ---------- 통계 (numpy 없으면 순수파이썬 OLS) ----------
def ols(X, y):
    """X: list of rows(각 [1, x1..xk]), y: list. → (beta[], t[]). 순수 정규방정식."""
    import math
    n = len(y); k = len(X[0])
    # X'X, X'y
    XtX = [[sum(X[r][i] * X[r][j] for r in range(n)) for j in range(k)] for i in range(k)]
    Xty = [sum(X[r][i] * y[r] for r in range(n)) for i in range(k)]
    inv = _inv(XtX)
    if inv is None:
        return None, None
    beta = [sum(inv[i][j] * Xty[j] for j in range(k)) for i in range(k)]
    resid = [y[r] - sum(X[r][i] * beta[i] for i in range(k)) for r in range(n)]
    dof = n - k
    if dof <= 0:
        return beta, [None] * k
    s2 = sum(e * e for e in resid) / dof
    t = []
    for i in range(k):
        se = (s2 * inv[i][i]) ** 0.5 if inv[i][i] > 0 else None
        t.append(beta[i] / se if se and se > 0 else None)
    return beta, t


def _inv(A):
    """가우스-조던 역행렬. 특이행렬이면 None."""
    n = len(A)
    M = [list(A[i]) + [1.0 if i == j else 0.0 for j in range(n)] for i in range(n)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(M[r][c]))
        if abs(M[piv][c]) < 1e-12:
            return None
        M[c], M[piv] = M[piv], M[c]
        d = M[c][c]
        M[c] = [v / d for v in M[c]]
        for r in range(n):
            if r != c:
                f = M[r][c]
                M[r] = [M[r][j] - f * M[c][j] for j in range(2 * n)]
    return [row[n:] for row in M]


def univar(xs, ys):
    """단변량: y = a + b*x → (b, t_b, n, corr)."""
    pairs = [(x, y) for x, y in zip(xs, ys) if x is not None and y is not None and x == x and y == y]
    if len(pairs) < 10:
        return None
    X = [[1.0, p[0]] for p in pairs]; Y = [p[1] for p in pairs]
    beta, t = ols(X, Y)
    if beta is None:
        return None
    n = len(pairs)
    mx = sum(p[0] for p in pairs) / n; my = sum(p[1] for p in pairs) / n
    sx = (sum((p[0]-mx)**2 for p in pairs)) ** 0.5; sy = (sum((p[1]-my)**2 for p in pairs)) ** 0.5
    cov = sum((p[0]-mx)*(p[1]-my) for p in pairs)
    corr = cov/(sx*sy) if sx > 0 and sy > 0 else None
    return {"b": beta[1], "t": t[1], "n": n, "corr": corr}


def multivar(rows, keys, ykey):
    """다변량: 주어진 keys로 동시회귀. rows=[{key:val,..., ykey:val}]. → {key:(coef,t)}, n."""
    _ok = lambda v: v is not None and v == v
    data = [r for r in rows if _ok(r.get(ykey)) and all(_ok(r.get(k)) for k in keys)]
    if len(data) < len(keys) + 5:
        return None, len(data)
    X = [[1.0] + [r[k] for k in keys] for r in data]
    Y = [r[ykey] for r in data]
    beta, t = ols(X, Y)
    if beta is None:
        return None, len(data)
    out = {keys[i]: (beta[i+1], t[i+1]) for i in range(len(keys))}
    return out, len(data)


# ---------- 데이터 (진우 PC) ----------
def _ret(series):
    """[(date,close)] 정렬 → {date: 일수익%}."""
    out = {}
    for i in range(1, len(series)):
        d0, c0 = series[i-1]; d1, c1 = series[i]
        if c0 and c0 > 0:
            out[d1] = (c1/c0 - 1) * 100
    return out


def _yf_close(sym, years=10):
    try:
        import yfinance as yf
        h = yf.Ticker(sym).history(period=f"{years}y")
        if h is not None and len(h) > 0:
            return sorted((d.date(), float(c)) for d, c in h["Close"].items())
    except Exception:
        pass
    return []


def _yf_level(sym, years=10):
    s = _yf_close(sym, years)
    return {d: c for d, c in s}


def load_kospi(years=10):
    s = _yf_close("^KS11", years)
    if not s:
        try:
            from pykrx import stock
            end = date.today().strftime("%Y%m%d"); start = (date.today()-timedelta(days=365*years)).strftime("%Y%m%d")
            df = stock.get_index_ohlcv(start, end, "1001")
            s = sorted((i.date(), float(c)) for i, c in df["종가"].items())
        except Exception:
            s = []
    return s


def load_foreign(years=10, market="KOSPI"):
    """외국인 순매수(억원) {date: val}. market=KOSPI/KOSDAQ. pykrx."""
    try:
        from pykrx import stock
        end = date.today().strftime("%Y%m%d"); start = (date.today()-timedelta(days=365*years)).strftime("%Y%m%d")
        df = stock.get_market_trading_value_by_date(start, end, market)
        col = next((c for c in df.columns if "외국인" in str(c)), None)
        if col:
            return {i.date(): float(v)/1e8 for i, v in df[col].items()}
    except Exception:
        pass
    return {}


def load_csv_series(fname, datecol, valcol):
    p = os.path.join(HERE, fname)
    if not os.path.exists(p):
        return {}
    out = {}
    try:
        content = open(p, encoding="utf-8-sig", errors="ignore").read().replace("\x00", "")
        import io
        for r in csv.DictReader(io.StringIO(content)):
            try:
                d = date.fromisoformat(str(r[datecol])[:10]); out[d] = float(r[valcol])
            except (ValueError, KeyError, TypeError):
                pass
    except Exception:
        pass
    return out


def second_thursday(y, m):
    d = date(y, m, 1); ft = d + timedelta(days=(3 - d.weekday()) % 7); return ft + timedelta(days=7)


def expiry_dummy(d):
    """d가 어느 달 둘째목 기준 D-3~D+1 이내면 1.0 else 0.0."""
    for mm in (d.month - 1, d.month, d.month + 1):
        y, m = d.year, mm
        if m < 1: y, m = y-1, 12
        if m > 12: y, m = y+1, 1
        e = second_thursday(y, m)
        if -3 <= (d - e).days <= 1:
            return 1.0
    return 0.0


def build_dataset(years=10, market="KOSPI"):
    """한국 거래일 기준 X(d) → 지수 익일/당일 수익. market=KOSPI/KOSDAQ. dict 리스트 반환."""
    sym, code = ("^KS11", "1001") if market == "KOSPI" else ("^KQ11", "2001")
    idx = _yf_close(sym, years)
    if not idx:
        try:
            from pykrx import stock
            _e = date.today().strftime("%Y%m%d"); _s = (date.today()-timedelta(days=365*years)).strftime("%Y%m%d")
            idx = sorted((i.date(), float(c)) for i, c in stock.get_index_ohlcv(_s, _e, code)["종가"].items())
        except Exception:
            idx = []
    if not idx:
        return None, f"{market} 지수 수신 실패"
    kr_ret = _ret(idx)                         # {date: 지수 일수익%}
    kr_dates = [d for d, _ in idx]
    sox = _ret(_yf_close("^SOX", years)); sp = _ret(_yf_close("^GSPC", years))
    wti = _ret(_yf_close("CL=F", years)); dxy = _ret(_yf_close("DX-Y.NYB", years) or _yf_close("DX=F", years))
    krw = _ret(_yf_close("KRW=X", years))
    tnx = _yf_level("^TNX", years); irx = _yf_level("^IRX", years)
    foreign = load_foreign(years, market)
    vk = load_csv_series("vkospi_daily.csv", "Date", "VKOSPI") or load_csv_series("vkospi_daily.csv", "date", "vkospi")
    br = load_csv_series("breadth_features.csv", "date", "ma20")

    # 美 변수를 한국 거래일에 ffill 매핑하는 헬퍼
    def ffill_on(dates, series):
        sd = sorted(series); out = {}; j = 0; last = None
        sk = [d for d in sd];
        for d in dates:
            while j < len(sk) and sk[j] <= d:
                last = series[sk[j]]; j += 1
            out[d] = last
        return out

    def lvl_on(dates, lvl):
        sd = sorted(lvl); out = {}; j = 0; last = None
        for d in dates:
            while j < len(sd) and sd[j] <= d:
                last = lvl[sd[j]]; j += 1
            out[d] = last
        return out

    sox_k = ffill_on(kr_dates, sox); sp_k = ffill_on(kr_dates, sp)
    wti_k = ffill_on(kr_dates, wti); dxy_k = ffill_on(kr_dates, dxy); krw_k = ffill_on(kr_dates, krw)
    tnx_k = lvl_on(kr_dates, tnx); irx_k = lvl_on(kr_dates, irx)

    rows = []
    for i in range(1, len(kr_dates) - 1):
        d = kr_dates[i]; dn = kr_dates[i+1]; dp = kr_dates[i-1]
        def chg(lvlmap):
            a = lvlmap.get(d); b = lvlmap.get(dp)
            return (a - b) if (a is not None and b is not None) else None
        curve_now = (tnx_k.get(d) - irx_k.get(d)) if (tnx_k.get(d) is not None and irx_k.get(d) is not None) else None
        curve_prev = (tnx_k.get(dp) - irx_k.get(dp)) if (tnx_k.get(dp) is not None and irx_k.get(dp) is not None) else None
        rows.append({
            "date": d,
            "sox": sox_k.get(d), "sp": sp_k.get(d),
            "tnx": (chg(tnx_k) * 100 if chg(tnx_k) is not None else None),  # bp
            "krw": krw_k.get(d), "foreign": foreign.get(d),
            "vkospi": vk.get(d), "breadth": br.get(d),
            "curve": ((curve_now - curve_prev) * 100 if (curve_now is not None and curve_prev is not None) else None),
            "wti": wti_k.get(d), "dxy": dxy_k.get(d),
            "expiry": expiry_dummy(d),
            "y_next": kr_ret.get(dn), "y_same": kr_ret.get(d),
        })
    return rows, None


# ---------- 검증 실행 ----------
def analyze(rows):
    res = {}
    n_all = len(rows)
    half = n_all // 2
    for key, label, sign, isB, thr in CONDS:
        xs = [r[key] for r in rows]; ys = [r["y_next"] for r in rows]
        u = univar(xs, ys)
        # OOS 전/후반
        u1 = univar([r[key] for r in rows[:half]], [r["y_next"] for r in rows[:half]])
        u2 = univar([r[key] for r in rows[half:]], [r["y_next"] for r in rows[half:]])
        oos_ok = (u1 and u2 and u1["b"] is not None and u2["b"] is not None and (u1["b"] * u2["b"] > 0))
        res[key] = {"label": label, "sign": sign, "isB": isB, "thr": thr,
                    "uni": u, "oos_ok": oos_ok,
                    "oos_b": (u1["b"] if u1 else None, u2["b"] if u2 else None)}
    # 다변량 A = 표본 충분(≥80%) 변수만 (breadth·VKOSPI 짧으면 자동 제외) / B(5)
    def cov(k): return sum(1 for r in rows if r.get(k) is not None) / max(1, len(rows))
    a_keys = [c[0] for c in CONDS if cov(c[0]) >= 0.8]
    mvA, nA = multivar(rows, a_keys, "y_next")
    mvB, nB = multivar(rows, list(B_KEYS), "y_next")
    return res, (mvA, nA, a_keys), (mvB, nB)


def verdict(key, res, mv, mv_keys):
    """채택/기각 판정. 단변량 임계+부호 / 다변량 생존 / OOS. mv_keys=다변량 포함된 변수."""
    r = res[key]; u = r["uni"]
    if not u or u["t"] is None:
        return "데이터부족", False
    t = u["t"]; thr = r["thr"]; sign = r["sign"]
    sign_ok = True
    if sign == "+": sign_ok = u["b"] > 0
    elif sign == "-": sign_ok = u["b"] < 0
    uni_pass = abs(t) >= thr and (sign_ok if sign in "+-" else True)
    if sign == "0":  # 만기: 영향 없어야 정상
        return ("예상대로 무영향" if abs(t) < 2.0 else f"⚠️유의(t={t:.1f}) 재검토"), False
    if key not in mv_keys:  # 표본부족으로 다변량 제외(breadth·VKOSPI)
        if uni_pass and r["oos_ok"]:
            return "🟡 단·OOS통과(표본부족·다변량제외)", False
        return "❌ 기각/표본부족", False
    mv_t = mv.get(key, (None, None))[1] if mv else None
    mv_pass = (mv_t is not None and abs(mv_t) >= 2.0)
    if uni_pass and r["oos_ok"] and mv_pass:
        return "✅ 채택(강건)", True
    if uni_pass and r["oos_ok"]:
        return "🟡 단·OOS 통과(다변량 약)", False
    if uni_pass:
        return "🟡 단변량만(OOS 불안정)", False
    return "❌ 기각", False


def render(rows, res, A, B, market="KOSPI"):
    mvA, nA, a_keys = A; mvB, nB = B
    today = date.today().strftime("%Y-%m-%d")
    mk = "코스피" if market == "KOSPI" else "코스닥"; suf = market.lower()
    L = [f"# 시장 영향 조건 검증 ({mk}) — {today}", "",
         "> 사전등록(시장영향_검증_사전등록.md) 기반. X(d)→코스피 익일수익. |t|≥임계+부호+다변량+OOS 통과만 채택.",
         "> ⚠️ 데이터마이닝 방어: 방향가설 |t|≥2.3 · 탐색 |t|≥3.0 · OOS 양쪽 동일부호 필수. 통과 0개도 정상 결론.", "",
         f"- 표본: {len(rows)} 거래일", ""]
    L.append("## A) 11개 전체 — 단변량 + 다변량 + OOS")
    L.append("| 조건 | 가설 | 단변량 b | t | OOS동일부호 | 다변량 t | 판정 |")
    L.append("|---|---|---|---|---|---|---|")
    accepted = []
    for key, label, sign, isB, thr in CONDS:
        r = res[key]; u = r["uni"]
        mv_t = (mvA.get(key)[1] if (mvA and key in mvA) else None)
        v, ok = verdict(key, res, mvA, a_keys)
        if ok: accepted.append(key)
        bcell = f"{u['b']:+.3f}" if u and u["b"] is not None else "—"
        tcell = f"{u['t']:+.2f}" if u and u["t"] is not None else "—"
        mvcell = f"{mv_t:+.2f}" if mv_t is not None else "—"
        L.append(f"| {label}{' ⭐B' if isB else ''} | {sign} | {bcell} | {tcell} | "
                 f"{'O' if r['oos_ok'] else 'X'} | {mvcell} | {v} |")
    L.append(f"\n- 다변량 A 표본 n={nA}")
    L.append("")
    L.append("## B) 핵심 5개 (SOX·S&P500·美10년·원달러·외국인) — 다변량")
    L.append("| 조건 | 다변량 b | t | 단변량 t | 판정(B기준 |t|≥2) |")
    L.append("|---|---|---|---|---|")
    for key in [c[0] for c in CONDS if c[0] in B_KEYS]:
        r = res[key]; u = r["uni"]
        if mvB and key in mvB and mvB[key][1] is not None:
            b, t = mvB[key]
            jb = "✅" if abs(t) >= 2.0 else "❌"
        else:
            b = t = None; jb = "—"
        L.append(f"| {r['label']} | {b:+.3f} | {t:+.2f} | {u['t']:+.2f} | {jb} |" if (b is not None and u and u['t'] is not None)
                 else f"| {r['label']} | — | — | — | 데이터부족 |")
    L.append(f"\n- 다변량 B 표본 n={nB}")
    L.append("")
    L.append("## 비교 / 결론")
    L.append(f"- **A·B 모두에서 강건한 조건**: {', '.join(res[k]['label'] for k in accepted if k in B_KEYS) or '없음'}")
    L.append(f"- A에서 채택: {', '.join(res[k]['label'] for k in accepted) or '없음'}")
    L.append("- 만기 더미: 무영향이어야 정상(유의하면 재검토). breadth·VKOSPI는 표본 짧으면 신뢰 낮음.")
    L.append("- **통과 0개여도 정상** — 정직한 '영향 조건 없음/약함'도 결론(만기효과 선례).")
    L.append("\n*실데이터(yfinance/pykrx/csv). 룩어헤드 차단(X≤d→Y[d+1]). 결정·책임은 진우.*")
    md = "\n".join(L)
    open(os.path.join(HERE, f"시장영향_검증_{suf}_결과.md"), "w", encoding="utf-8").write(md)
    # raw
    with open(os.path.join(HERE, f"시장영향_검증_{suf}_raw.csv"), "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); keys = [c[0] for c in CONDS]
        w.writerow(["date"] + keys + ["y_next", "y_same"])
        for r in rows:
            w.writerow([r["date"]] + [r.get(k) for k in keys] + [r.get("y_next"), r.get("y_same")])
    print(md); print(f"\n[산출] 시장영향_검증_{suf}_결과.md · 시장영향_검증_{suf}_raw.csv")


def _selftest():
    ok = 0
    def chk(n, c):
        nonlocal ok; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    # OLS 회수: y = 1 + 2*x1 - 1*x2 (노이즈 없음) → beta 정확
    import random
    random.seed(0)
    X = []; Y = []
    for _ in range(200):
        x1 = random.gauss(0, 1); x2 = random.gauss(0, 1)
        X.append([1.0, x1, x2]); Y.append(1 + 2*x1 - 1*x2)
    beta, t = ols(X, Y)
    chk("OLS 계수 회수", abs(beta[1]-2) < 1e-6 and abs(beta[2]+1) < 1e-6)
    chk("OLS t값 큼(무노이즈)", t[1] is not None and abs(t[1]) > 100)
    # 단변량 상관
    u = univar([1,2,3,4,5,6,7,8,9,10], [2,4,6,8,10,12,14,16,18,20])
    chk("단변량 완전상관", abs(u["corr"] - 1.0) < 1e-9 and abs(u["b"]-2) < 1e-9)
    # 만기 더미
    chk("만기더미 9/10주변=1", expiry_dummy(date(2026, 9, 10)) == 1.0 and expiry_dummy(date(2026, 9, 11)) == 1.0)
    chk("만기더미 평소=0", expiry_dummy(date(2026, 9, 25)) == 0.0)
    # 역행렬
    inv = _inv([[2.0, 0.0], [0.0, 4.0]])
    chk("역행렬", abs(inv[0][0]-0.5) < 1e-9 and abs(inv[1][1]-0.25) < 1e-9)
    # 다변량 형식
    rows = [{"a": random.gauss(0,1), "b": random.gauss(0,1)} for _ in range(50)]
    for r in rows: r["y"] = 3*r["a"] + 0.5
    mv, nn = multivar(rows, ["a", "b"], "y")
    chk("다변량 a계수≈3", mv and abs(mv["a"][0]-3) < 1e-6)
    print(f"✅ 시장영향_검증 셀프테스트 ({ok}/7)")
    return ok == 7


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--years", type=int, default=10)
    ap.add_argument("--market", default="KOSPI", help="KOSPI 또는 KOSDAQ")
    a = ap.parse_args()
    if a.selftest:
        _selftest(); return
    market = a.market.upper()
    rows, err = build_dataset(a.years, market)
    if err:
        print(f"❌ {err}"); return
    res, A, B = analyze(rows)
    render(rows, res, A, B, market)


if __name__ == "__main__":
    main()
