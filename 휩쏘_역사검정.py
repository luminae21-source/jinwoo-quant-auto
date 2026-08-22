# -*- coding: utf-8 -*-
r"""휩쏘_역사검정.py — 휩쏘 재진입 규칙(A/B)을 1996~2026 전 기간·전 종목에 적용해
     '이 방식이 실제로 먹히는가'를 정직하게 검정한다. 형의 핵심 질문:
       (1) 길게 보면 이 자리가 통계적으로 유효한가? (승률·수익·기저율 대비 리프트)
       (2) 시장 국면에 따라 달라지는가? (강세/약세·고변동/저변동)  ← 모델 수정의 근거

[데이터] 종목일봉_30년_{KOSPI,KOSDAQ}.csv 는 '무수정(raw)'이다.
         → 스플릿/증자가 하루 -50~-98% 허위 급락으로 찍혀 휩쏘로 오탐된다.
         한국은 '일일 가격제한폭'이 있어(2015-06-15 이전 ±15%, 이후 ±30%)
         제한폭을 넘는 종가-종가 변화는 '반드시' 기업행위(분할/증자)다 → 그 비율로 백조정.
         이렇게 하면 진짜 2일 플러시(제한폭 이내 두 번)만 신호로 남는다.

[규칙] 탐색기(휩쏘_탐색기.py)의 testA/testB 를 그대로 벡터화.
⚠️ 검정용. 표본·데이터 한계 명시(생존편향·소규모 기업행위 잔존 가능). 매매추천 아님.
"""
import os, sys, json, argparse, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
OUT = HERE

NEAR = 0.08          # 선 근접 ±8% (탐색기 기본)
HORIZONS = [5, 10, 20, 40]
MIN_BARS = 260
RNG = np.random.default_rng(7)


def era_limit(dstr):
    """한국 일일 가격제한폭. 이 값+여유(3%p)를 넘는 하루 변화 = 기업행위."""
    return 0.30 if dstr >= "2015-06-15" else 0.15


def back_adjust(o, h, l, c, v, dts):
    """가격제한폭 초과 종가변화를 기업행위로 보고 이전 구간을 비율 백조정."""
    n = len(c)
    adj = np.ones(n)
    cum = 1.0
    for i in range(n - 1, 0, -1):
        prev, cur = c[i - 1], c[i]
        if prev > 0 and cur > 0:
            r = cur / prev
            lim = era_limit(dts[i]) + 0.03
            if r < (1 - lim) or r > (1 + lim):
                cum *= r
        adj[i - 1] = cum
    return o * adj, h * adj, l * adj, c * adj, adj


def line_series(c_idx):
    """일240 / 주60주 / 월10 (완료구간 기준, 미래 미참조)."""
    s = pd.Series(c_idx["close"].values, index=pd.to_datetime(c_idx["date"].values))
    wk = s.resample("W-FRI").last().dropna()
    mo = s.resample("ME").last().dropna()
    wkm = wk.rolling(60, min_periods=60).mean()      # 주60주선
    mom = mo.rolling(10, min_periods=10).mean()       # 월10선
    # 완료된 주/월의 값을 다음 날부터 적용(ffill) → 미래참조 없음
    daily_idx = s.index
    w_on_d = wkm.reindex(daily_idx.union(wkm.index)).ffill().reindex(daily_idx)
    m_on_d = mom.reindex(daily_idx.union(mom.index)).ffill().reindex(daily_idx)
    return w_on_d.values, m_on_d.values


def scan_stock(g, mcap_asof, events, base_rows, code, name):
    g = g.sort_values("date").reset_index(drop=True)
    g = g[~((g["open"] == 0) & (g["volume"] == 0))].reset_index(drop=True)  # 정지/플레이스홀더 제거
    if len(g) < MIN_BARS:
        return
    dts = g["date"].values.astype(str)
    o = g["open"].values.astype(float); h = g["high"].values.astype(float)
    l = g["low"].values.astype(float);  c = g["close"].values.astype(float)
    v = g["volume"].values.astype(float)
    rawc = c.copy()
    o, h, l, c, adj = back_adjust(o, h, l, c, v, dts)

    n = len(c)
    rd = np.empty(n); rd[0] = np.nan; rd[1:] = c[1:] / c[:-1] - 1
    cs = pd.Series(c)
    ma240 = cs.rolling(240, min_periods=240).mean().values
    gap240 = c / ma240 - 1
    w60, m10 = line_series(g[["date", "close"]].assign(close=c))
    hi5 = pd.Series(h).rolling(1250, min_periods=250).max().values
    top5 = c / hi5 - 1
    # 고점매도신호
    hi252 = pd.Series(h).rolling(252, min_periods=120).max().values
    volma = pd.Series(v).rolling(60, min_periods=40).mean().values
    body = c / np.where(o > 0, o, np.nan) - 1
    wick = (h - np.maximum(o, c)) / np.where(h > 0, h, np.nan)
    sig = ((c >= hi252 * 0.90) & (v >= volma * 2.0) & (wick >= 0.03) & (body <= 0.02)).astype(float)
    sell10 = pd.Series(sig).rolling(10, min_periods=1).sum().values

    lines = np.vstack([w60, m10, ma240])  # 3 x n
    lnames = ["주60주", "월10", "일240"]

    for t in range(MIN_BARS, n):
        if not (rawc[t] >= 1000 and np.isfinite(ma240[t]) and np.isfinite(c[t]) and c[t] > 0):
            continue
        r1, r2 = rd[t - 1], rd[t]
        cum2 = c[t] / c[t - 2] - 1
        lv = lines[:, t]
        dist = c[t] / lv - 1
        finite = np.isfinite(dist)
        if not finite.any():
            continue
        nearby = np.any(np.abs(dist[finite]) <= NEAR)
        ki = np.nanargmin(np.where(finite, np.abs(dist), np.inf))
        keyline_v = lv[ki]; keyd = dist[ki]
        # 지지: 오늘 저가가 선을 밟고 종가는 선 위
        held = [lnames[j] for j in range(3)
                if np.isfinite(lv[j]) and l[t] <= lv[j] <= c[t] * 1.002]
        mc = mcap_asof(dts[t])
        g240 = gap240[t]; t5 = top5[t]; s10 = sell10[t]

        isA = (r1 <= -0.03 and r2 <= 0.02 and cum2 <= -0.12 and nearby
               and np.isfinite(t5) and t5 <= -0.30 and s10 == 0
               and np.isfinite(g240) and g240 <= 0.08
               and np.isfinite(mc) and mc >= 3000e8)
        isB = (r1 <= -0.03 and cum2 <= -0.03 and nearby and s10 == 0
               and np.isfinite(g240) and g240 >= 0.10
               and np.isfinite(mc) and mc >= 50000e8)
        if not (isA or isB):
            continue

        typ = "A" if isA else "B"
        # 등급(A유형만 의미): 지지>밀착>근접
        if held: grade = "A"
        elif abs(keyd) <= 0.03: grade = "B"
        else: grade = "C"

        fwd = {f"fwd{hh}": (c[t + hh] / c[t] - 1 if t + hh < n else np.nan) for hh in HORIZONS}
        # 카드 청산 시뮬
        entry = c[t]
        if typ == "A":
            pre = c[t] / (1 + cum2)
            target = entry + (pre - entry) * 0.5
            below = keyline_v if (np.isfinite(keyline_v) and keyline_v < entry) else l[t]
            stop0 = below * 0.95; trail = 0.12
        else:
            j0 = max(0, t - 59)
            target = float(np.max(h[j0:t + 1]))
            below = keyline_v if (np.isfinite(keyline_v) and keyline_v < entry) else l[t]
            stop0 = below * 0.97; trail = 0.15
        ex_ret, bars, how = np.nan, 0, "만기"
        peak = entry; stop = stop0
        end = min(t + 40, n - 1)
        for j in range(t + 1, end + 1):
            bars = j - t
            if l[j] <= stop:
                ex_ret = stop / entry - 1; how = ("손절" if stop <= stop0 * 1.0001 else "트레일"); break
            if h[j] >= target:
                ex_ret = target / entry - 1; how = "목표"; break
            peak = max(peak, h[j])
            stop = max(stop, peak * (1 - trail))
        if not np.isfinite(ex_ret):
            ex_ret = c[end] / entry - 1; bars = end - t; how = "만기"

        events.append(dict(date=dts[t], code=code, name=name, 유형=typ, 등급=grade,
                           entry=entry, rawclose=rawc[t], cum2=cum2, gap240=g240,
                           top5=t5, keyline=lnames[ki], keyd=keyd, held=",".join(held),
                           mcap=mc, ex_ret=ex_ret, ex_bars=bars, ex_how=how, **fwd))

    # 기저율 표본: 같은 종목에서 랜덤 몇 개 (가격/이력 조건만)
    valid = np.arange(MIN_BARS, n - 40)
    valid = valid[(rawc[valid] >= 1000) & np.isfinite(ma240[valid])]
    if len(valid):
        pick = RNG.choice(valid, size=min(6, len(valid)), replace=False)
        for t in pick:
            base_rows.append({f"fwd{hh}": (c[t + hh] / c[t] - 1 if t + hh < n else np.nan)
                              for hh in HORIZONS} | {"date": dts[t]})


def _dfind(fn):
    for d in (HERE, DATA, "/mnt/user-data/uploads/진우퀀트"):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    return None


def build_mcap():
    p = _dfind("종목시총_30년.csv")
    if p is None:
        sys.exit("종목시총_30년.csv 없음 — 진우퀀트 폴더에 있어야 한다.")
    mc = pd.read_csv(p, dtype={"code": str})
    mc.columns = [x.strip().lstrip("﻿") for x in mc.columns]
    mc["code"] = mc["code"].str.zfill(6)
    mc["date"] = mc["date"].astype(str)
    mc["mcap"] = pd.to_numeric(mc["mcap"], errors="coerce")
    mc = mc.dropna(subset=["mcap"]).sort_values(["code", "date"])
    return {c: (d["date"].values, d["mcap"].values) for c, d in mc.groupby("code")}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--markets", default="KOSPI,KOSDAQ")
    ap.add_argument("--limit", type=int, default=0, help="종목수 제한(디버그)")
    a = ap.parse_args()

    names = {}
    for cand in [os.path.join(HERE, "종목명_맵.csv"), "/mnt/user-data/uploads/진우퀀트/종목명_맵.csv", os.path.join(DATA, "종목명_맵.csv")]:
        if os.path.exists(cand):
            nm = pd.read_csv(cand, dtype=str); nm.columns = [x.strip().lstrip("﻿") for x in nm.columns]
            names = dict(zip(nm["code"].str.zfill(6), nm["name"])); break

    print("시총 로딩…", flush=True)
    MC = build_mcap()

    import gc
    events, base_rows = [], []
    dts_dtype = {"code": str, "open": "float32", "high": "float32",
                 "low": "float32", "close": "float32", "volume": "float32"}
    for m in a.markets.split(","):
        p = _dfind(f"종목일봉_30년_{m}.csv")
        if p is None:
            print(f"  ⚠️ {p} 없음 — 건너뜀"); continue
        print(f"{m} 로딩…", flush=True)
        D = pd.read_csv(p, dtype=dts_dtype)
        D.columns = [x.strip().lstrip("﻿") for x in D.columns]
        D["code"] = D["code"].str.zfill(6)
        codes = list(D["code"].unique())
        if a.limit: codes = codes[:a.limit]
        print(f"  {m} 종목수 {len(codes)}", flush=True)
        for i, (code, g) in enumerate(D.groupby("code", sort=False)):
            if a.limit and code not in set(codes): continue
            def mcap_asof(dstr, _c=code):
                arr = MC.get(_c)
                if not arr: return np.nan
                dd, vv = arr
                k = np.searchsorted(dd, dstr, side="right") - 1
                return vv[k] if k >= 0 else np.nan
            scan_stock(g, mcap_asof, events, base_rows, code, names.get(code, code))
            if (i + 1) % 400 == 0:
                print(f"    {m} {i+1} 종목… 누적 이벤트 {len(events)}", flush=True)
        del D; gc.collect()

    tag = "_".join(a.markets.split(","))
    E = pd.DataFrame(events)
    B = pd.DataFrame(base_rows)
    E.to_csv(os.path.join(OUT, f"역사검정_이벤트_{tag}.csv"), index=False, encoding="utf-8-sig")
    B.to_csv(os.path.join(OUT, f"역사검정_기저_{tag}.csv"), index=False, encoding="utf-8-sig")
    print(f"\n이벤트 {len(E)} · 기저표본 {len(B)}  저장 완료 → {tag}", flush=True)
    if len(E):
        print(E["유형"].value_counts())
        print("연도별:", E.assign(y=E["date"].str[:4]).groupby("y").size().to_dict())


if __name__ == "__main__":
    main()
