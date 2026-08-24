# -*- coding: utf-8 -*-
"""숙근매매 1차 검정 — 순환매매(익절→눌림 재매수) vs 단순 보유
사전등록: 숙근매매_1차_사전등록.md (2026-08-22). 등록문 그대로 구현. 격리 트랙 — 본체 파일 무수정.
실행: python 숙근매매_1차검정.py  (같은 폴더에 kospi_index_daily.csv, 삼성전자_일봉_30년.csv)
"""
import itertools, os, sys
import numpy as np
import pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
COST = 0.002            # 편도 0.2% (왕복 0.4%)
WINDOW = 180            # 거래일
TRAIN = range(1997, 2016)
VALID = range(2016, 2026)
XS = [5, 8, 10, 15, 20]
YS = [3, 5, 8, 10]
ERA = pd.Timestamp("2015-06-15")

def load_kospi():
    df = pd.read_csv(os.path.join(HERE, "kospi_index_daily.csv"), encoding="utf-8-sig")
    s = pd.Series(df["Close"].astype(float).values, index=pd.to_datetime(df["Date"]))
    return s[~s.index.duplicated(keep="last")].sort_index()

def load_samsung():
    df = pd.read_csv(os.path.join(HERE, "삼성전자_일봉_30년.csv"), encoding="utf-8-sig")
    s = pd.Series(df["close"].astype(float).values, index=pd.to_datetime(df["date"]))
    s = s[~s.index.duplicated(keep="last")].sort_index()
    # close-only 백조정 (성장주_장기지도.py back_adjust_monthly 동일, 월말 리샘플 제거)
    c = s.values; d = s.index
    ret = np.ones(len(c)); ret[1:] = c[1:] / c[:-1]
    hi = np.where(d[1:] < ERA, 1.18, 1.33)
    lo = np.where(d[1:] < ERA, 1/1.15 - 0.03, 1/1.30 - 0.03)
    bad = (ret[1:] > hi) | (ret[1:] < lo)
    ret[1:][bad] = 1.0
    return pd.Series(np.cumprod(ret) * c[0], index=d), int(bad.sum())

def windows(s):
    """진입연도 -> 종가 배열(길이 WINDOW+1: 진입일 idx0 ~ 180일째 idx180)"""
    out = {}
    idx = s.index
    for y in range(1997, 2026):
        pos = np.searchsorted(idx.values, np.datetime64(f"{y}-10-01"))
        if pos + WINDOW >= len(s):
            continue
        out[y] = s.values[pos:pos + WINDOW + 1]
    return out

def hold(p):
    return (1 - COST) * (p[-1] / p[0]) * (1 - COST) - 1

def cycle(p, x, y, lag=1):
    """lag=1: 신호 다음 거래일 종가 체결(primary). lag=0: 신호 당일 종가(낙관 상한)."""
    cash = 0.0; shares = (1 - COST) / p[0]; holding = True
    last_buy = p[0]; last_sell = None; trades = 0
    n = len(p) - 1
    i = 1
    while i < n:
        if holding and p[i] >= last_buy * (1 + x / 100):
            j = min(i + lag, n)
            cash = shares * p[j] * (1 - COST); shares = 0.0; holding = False
            last_sell = p[j]; trades += 1; i = j + 1; continue
        if (not holding) and p[i] <= last_sell * (1 - y / 100):
            j = min(i + lag, n)
            if j >= n:  # 마감일 매수는 무의미 (즉시 청산) → 현금 유지
                break
            shares = cash * (1 - COST) / p[j]; cash = 0.0; holding = True
            last_buy = p[j]; i = j + 1; continue
        i += 1
    if holding:
        cash = shares * p[n] * (1 - COST)
    return cash - 1, trades

def cagr(rs):
    rs = np.asarray(rs)
    return np.prod(1 + rs) ** (250 / (len(rs) * WINDOW)) - 1

def stats(rs, hs, tr=None):
    rs = np.asarray(rs); hs = np.asarray(hs)
    d = dict(cagr=cagr(rs), mean=rs.mean(), median=np.median(rs), win=(rs > 0).mean(),
             beat=(rs > hs).mean(), worst=rs.min())
    if tr is not None: d["trades"] = np.mean(tr)
    return d

def run(name, s, lines):
    W = windows(s)
    tr_years = [y for y in TRAIN if y in W]; va_years = [y for y in VALID if y in W]
    lines.append(f"\n## {name}  (훈련 {tr_years[0]}~{tr_years[-1]} {len(tr_years)}창 / 검증 {va_years[0]}~{va_years[-1]} {len(va_years)}창)\n")
    H = {y: hold(W[y]) for y in W}
    def seg(years, x, y, lag=1):
        rs, trs = zip(*[cycle(W[yy], x, y, lag) for yy in years])
        return stats(rs, [H[yy] for yy in years], trs), list(rs)
    hold_tr = stats([H[y] for y in tr_years], [H[y] for y in tr_years])
    hold_va = stats([H[y] for y in va_years], [H[y] for y in va_years])

    # 훈련 격자
    grid = {}
    lines.append("### 훈련 격자 — 순환 CAGR (보유 CAGR 기준 %.1f%%)\n" % (hold_tr["cagr"] * 100))
    lines.append("| X\\Y | " + " | ".join(f"{y}%" for y in YS) + " |")
    lines.append("|---|" + "---|" * len(YS))
    for x in XS:
        row = []
        for y in YS:
            st, _ = seg(tr_years, x, y); grid[(x, y)] = st
            row.append(f"{st['cagr']*100:+.1f}")
        lines.append(f"| {x}% | " + " | ".join(row) + " |")
    best = max(grid, key=lambda k: grid[k]["cagr"])
    n_beat_tr = sum(1 for k in grid if grid[k]["cagr"] > hold_tr["cagr"])
    lines.append(f"\n훈련에서 보유를 이긴 조합: {n_beat_tr}/20. **기계 선택 (훈련 CAGR 최대): X={best[0]}%, Y={best[1]}%**\n")

    # 검증
    va_best, va_rs = seg(va_years, *best)
    tr_best = grid[best]
    lines.append("### 선택 조합의 성적 (primary: 신호 다음날 종가 체결)\n")
    lines.append("| 구간 | 전략 | CAGR | 평균창 | 중앙값 | 승률 | 보유 이긴 창 | 최악창 | 평균회전 |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    def fmt(lab, seg_, st):
        lines.append(f"| {seg_} | {lab} | {st['cagr']*100:+.1f}% | {st['mean']*100:+.1f}% | {st['median']*100:+.1f}% | {st['win']*100:.0f}% | "
                     + (f"{st['beat']*100:.0f}%" if 'trades' in st else "—") + f" | {st['worst']*100:+.1f}% | "
                     + (f"{st['trades']:.1f}" if 'trades' in st else "0") + " |")
    fmt("보유", "훈련", hold_tr); fmt(f"순환 X{best[0]}/Y{best[1]}", "훈련", tr_best)
    fmt("보유", "검증", hold_va); fmt(f"순환 X{best[0]}/Y{best[1]}", "검증", va_best)

    # 검증 창별
    lines.append("\n### 검증 창별 (진입연도: 보유 / 순환 / 회전수)\n")
    lines.append("| 진입 | 보유 | 순환 | 회전 | 승자 |"); lines.append("|---|---|---|---|---|")
    for yy in va_years:
        r, t = cycle(W[yy], *best)
        lines.append(f"| {yy}-10 | {H[yy]*100:+.1f}% | {r*100:+.1f}% | {t} | {'동률(무회전)' if abs(r - H[yy]) < 1e-9 else ('순환' if r > H[yy] else '보유')} |")

    # 검증 전체 격자 (투명성, 판정 미사용)
    lines.append("\n### 검증 격자 전체 — 순환 CAGR (판정 미사용 · 투명성) · 보유 CAGR %.1f%%\n" % (hold_va["cagr"] * 100))
    lines.append("| X\\Y | " + " | ".join(f"{y}%" for y in YS) + " |"); lines.append("|---|" + "---|" * len(YS))
    n_beat_va = 0
    for x in XS:
        row = []
        for y in YS:
            st, _ = seg(va_years, x, y); row.append(f"{st['cagr']*100:+.1f}")
            n_beat_va += st["cagr"] > hold_va["cagr"]
        lines.append(f"| {x}% | " + " | ".join(row) + " |")
    lines.append(f"\n검증에서 보유를 이긴 조합(사후 참고): {n_beat_va}/20")

    # 낙관 상한
    st0_tr, _ = seg(tr_years, *best, lag=0); st0_va, _ = seg(va_years, *best, lag=0)
    lines.append(f"\n### 낙관 상한 (신호 당일 종가 체결 · 판정 미사용)\n\n훈련 CAGR {st0_tr['cagr']*100:+.1f}% (보유 {hold_tr['cagr']*100:+.1f}%) · 검증 CAGR {st0_va['cagr']*100:+.1f}% (보유 {hold_va['cagr']*100:+.1f}%)")

    # 판정
    win_tr = tr_best["cagr"] > hold_tr["cagr"]; win_va = va_best["cagr"] > hold_va["cagr"]
    if win_va: verdict = "**형 승 — 가설 생존** (검증 CAGR 순환 > 보유)"
    elif win_tr: verdict = "**기각 — 과최적화 판정** (훈련만 이기고 검증 실패)"
    else: verdict = "**기각** (훈련·검증 모두 보유 미달)"
    lines.append(f"\n### 판정: {verdict}\n")
    return dict(name=name, best=best, win_tr=win_tr, win_va=win_va, tr=tr_best, va=va_best, hold_tr=hold_tr, hold_va=hold_va, grid_beat_va=n_beat_va)

if __name__ == "__main__":
    lines = []
    ks = load_kospi(); ss, nbad = load_samsung()
    res = [run("① KOSPI 지수", ks, lines), run(f"② 삼성전자 (백조정 중립화 {nbad}회)", ss, lines)]
    print("\n".join(lines))
