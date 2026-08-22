# -*- coding: utf-8 -*-
r"""휩쏘_S2_역사검정.py — 조사 트랙 S2 '근접 미달형'의 30년 전량 검정.

질문: A형 조건을 1~2개 아깝게 미달한 자리도 먹히는가?
      (30년 등급 역설 — C급 근접 +2.8% > A급 지지 +1.8% — 이 완화 구간까지 이어지는가)

[방법] 휩쏘_역사검정.py 와 완전히 동일한 엔진·백조정·카드 규칙.
       탐지 조건만 S2(사전등록 2026-08-02)로 바꿔 전 종목·전 기간 스캔.
       정식 A/B로 잡히는 자리는 S2에서 제외 → 두 집단이 겹치지 않는다.

[사전등록 S2] 급락1 ≤ −3% · 급락2 ≤ +2% · 근접 ±8% · 고점매도신호 0
              2일누적 ≤ −10%(원 −12%) · MA240이격 ≤ +12%(원 +8%)
              5년고점比 ≤ −25%(원 −30%) · 시총 ≥ 2,000억(원 3,000억)
[출력] 미달 항목별로 쪼개 본다 — 어떤 완화가 살아남는지가 진짜 질문이다.
⚠️ 생존편향·기업행위 잔존·위기해 클러스터. Δ는 시사이지 확정 아님.
"""
import os, sys, gc, argparse, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

HERE = "/home/claude/jq"
NEAR = 0.08
MIN_BARS = 260


def era_limit(d): return 0.30 if d >= "2015-06-15" else 0.15


def back_adjust(o, h, l, c, dts):
    n = len(c); adj = np.ones(n); cum = 1.0
    for i in range(n - 1, 0, -1):
        p, q = c[i - 1], c[i]
        if p > 0 and q > 0:
            r = q / p; lim = era_limit(dts[i]) + 0.03
            if r < (1 - lim) or r > (1 + lim): cum *= r
        adj[i - 1] = cum
    return o * adj, h * adj, l * adj, c * adj


def line_series(dates, c):
    s = pd.Series(c, index=pd.to_datetime(dates))
    wk = s.resample("W-FRI").last().dropna(); mo = s.resample("ME").last().dropna()
    wkm = wk.rolling(60, min_periods=60).mean(); mom = mo.rolling(10, min_periods=10).mean()
    di = s.index
    return (wkm.reindex(di.union(wkm.index)).ffill().reindex(di).values,
            mom.reindex(di.union(mom.index)).ffill().reindex(di).values)


def simulate(entry, target, stop0, trail, h, l, c, t, n, H=40, split=1.0, rtrail=0.12):
    """split=1.0 → 현행 카드(전량). split=0.5 → 과제1 채택 2단(잔여 트레일·본전스톱)."""
    end = min(t + H, n - 1); peak = entry; stop = stop0
    for j in range(t + 1, end + 1):
        if l[j] <= stop:
            return stop / entry - 1, j - t, ("손절" if stop <= stop0 * 1.0001 else "트레일")
        if h[j] >= target:
            first = target / entry - 1
            if split >= 1.0: return first, j - t, "목표"
            rpeak = max(peak, h[j]); rstop = max(rpeak * (1 - rtrail), entry)
            for k in range(j + 1, end + 1):
                if l[k] <= rstop:
                    return split * first + (1 - split) * (rstop / entry - 1), k - t, "2단트레일"
                rpeak = max(rpeak, h[k]); rstop = max(rstop, max(rpeak * (1 - rtrail), entry))
            return split * first + (1 - split) * (c[end] / entry - 1), end - t, "2단만기"
        peak = max(peak, h[j]); stop = max(stop, peak * (1 - trail))
    return c[end] / entry - 1, end - t, "만기"


def scan_market(mk, MC, names, out_rows):
    dt = {"code": str, "open": "float32", "high": "float32", "low": "float32",
          "close": "float32", "volume": "float32"}
    D = pd.read_csv(f"{HERE}/종목일봉_30년_{mk}.csv", dtype=dt)
    D.columns = [x.strip().lstrip("﻿") for x in D.columns]
    D["code"] = D["code"].str.zfill(6)
    ns = 0
    for code, g in D.groupby("code", sort=False):
        ns += 1
        g = g.sort_values("date").reset_index(drop=True)
        g = g[~((g["open"] == 0) & (g["volume"] == 0))].reset_index(drop=True)
        if len(g) < MIN_BARS: continue
        dts = g["date"].values.astype(str)
        o = g["open"].values.astype(float); h = g["high"].values.astype(float)
        l = g["low"].values.astype(float);  c = g["close"].values.astype(float)
        v = g["volume"].values.astype(float)
        rawc = c.copy()
        o, h, l, c = back_adjust(o, h, l, c, dts)
        n = len(c)
        # ── 벡터화 지표
        rd = np.full(n, np.nan); rd[1:] = c[1:] / c[:-1] - 1
        cum2 = np.full(n, np.nan); cum2[2:] = c[2:] / c[:-2] - 1
        cs = pd.Series(c)
        ma240 = cs.rolling(240, min_periods=240).mean().values
        gap240 = c / ma240 - 1
        w60, m10 = line_series(g["date"].values, c)
        L = np.vstack([w60, m10, ma240])
        dist = c[None, :] / L - 1
        fin = np.isfinite(dist)
        nearby = np.any(fin & (np.abs(dist) <= NEAR), axis=0)
        absd = np.where(fin, np.abs(dist), np.inf)
        ki = np.argmin(absd, axis=0)
        keyv = L[ki, np.arange(n)]
        hi5 = pd.Series(h).rolling(1250, min_periods=250).max().values
        top5 = c / hi5 - 1
        hi252 = pd.Series(h).rolling(252, min_periods=120).max().values
        volma = pd.Series(v).rolling(60, min_periods=40).mean().values
        body = c / np.where(o > 0, o, np.nan) - 1
        wick = (h - np.maximum(o, c)) / np.where(h > 0, h, np.nan)
        sig = ((c >= hi252 * 0.90) & (v >= volma * 2.0) & (wick >= 0.03) & (body <= 0.02)).astype(float)
        sell10 = pd.Series(sig).rolling(10, min_periods=1).sum().values
        arr = MC.get(code)
        if arr is None: continue
        idx = np.searchsorted(arr[0], dts, side="right") - 1
        mc = np.where(idx >= 0, arr[1][np.clip(idx, 0, len(arr[1]) - 1)], np.nan)

        r1 = np.roll(rd, 1); r1[0] = np.nan          # 급락1 = 전일 변화
        ok_base = np.zeros(n, bool); ok_base[MIN_BARS:] = True
        ok_base &= (rawc >= 1000) & np.isfinite(ma240) & np.isfinite(c) & (c > 0)
        ok_base &= np.isfinite(mc) & nearby & (sell10 == 0)
        ok_base &= np.isfinite(cum2) & np.isfinite(r1) & np.isfinite(top5) & np.isfinite(gap240)

        isA = ok_base & (r1 <= -0.03) & (rd <= 0.02) & (cum2 <= -0.12) & (top5 <= -0.30) \
            & (gap240 <= 0.08) & (mc >= 3000e8)
        isB = ok_base & (r1 <= -0.03) & (cum2 <= -0.03) & (gap240 >= 0.10) & (mc >= 50000e8)
        isS2 = ok_base & (r1 <= -0.03) & (rd <= 0.02) & (cum2 <= -0.10) & (top5 <= -0.25) \
            & (gap240 <= 0.12) & (mc >= 2000e8) & ~isA & ~isB

        for typ, mask in (("A", isA), ("S2", isS2)):
            for t in np.where(mask)[0]:
                entry = c[t]
                pre = c[t] / (1 + cum2[t])
                target = entry + (pre - entry) * 0.5
                kv = keyv[t]
                below = kv if (np.isfinite(kv) and kv < entry) else l[t]
                stop0 = below * 0.95; trail = 0.12
                card, cb, chow = simulate(entry, target, stop0, trail, h, l, c, t, n, 40, 1.0)
                two, _, _ = simulate(entry, target, stop0, trail, h, l, c, t, n, 126, 0.5)
                f40 = c[t + 40] / entry - 1 if t + 40 < n else np.nan
                miss = []
                if typ == "S2":
                    if cum2[t] > -0.12: miss.append("2일누적")
                    if gap240[t] > 0.08: miss.append("MA240")
                    if top5[t] > -0.30: miss.append("5년고점")
                    if mc[t] < 3000e8: miss.append("시총")
                out_rows.append(dict(date=dts[t], code=code, name=names.get(code, code), 시장=mk,
                                     신호=typ, 미달=",".join(miss), cum2=cum2[t], gap240=gap240[t],
                                     top5=top5[t], mcap=mc[t], 카드=card, ex_how=chow, ex_bars=cb,
                                     이단=two, fwd40=f40))
        if ns % 500 == 0:
            print(f"   {mk} {ns}종목… 누적 {len(out_rows)}", flush=True)
    del D; gc.collect()


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--market", default="KOSPI")
    a = ap.parse_args()
    nm = pd.read_csv(f"{HERE}/종목명_맵.csv", dtype=str)
    nm.columns = [x.strip().lstrip("﻿") for x in nm.columns]
    names = dict(zip(nm["code"].str.zfill(6), nm["name"]))
    mcd = pd.read_csv(f"{HERE}/종목시총_30년.csv", dtype={"code": str})
    mcd.columns = [x.strip().lstrip("﻿") for x in mcd.columns]
    mcd["code"] = mcd["code"].str.zfill(6); mcd["date"] = mcd["date"].astype(str)
    mcd["mcap"] = pd.to_numeric(mcd["mcap"], errors="coerce")
    mcd = mcd.dropna(subset=["mcap"]).sort_values(["code", "date"])
    MC = {c: (d["date"].values, d["mcap"].values) for c, d in mcd.groupby("code")}
    del mcd; gc.collect()
    rows = []
    print(f"{a.market} 스캔 시작…", flush=True)
    scan_market(a.market, MC, names, rows)
    R = pd.DataFrame(rows)
    R.to_csv(f"{HERE}/S2_이벤트_{a.market}.csv", index=False, encoding="utf-8-sig")
    print(f"\n{a.market} 완료 — A {int((R['신호']=='A').sum())}건 · S2 {int((R['신호']=='S2').sum())}건")


if __name__ == "__main__":
    main()
