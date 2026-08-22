# -*- coding: utf-8 -*-
"""2단 청산 보강검정 — (a) 분할비율 0.25/0.5/0.75  (b) 잔여를 '핵심선 이탈'로 청산(구조청산).
   1차 결론(T10~12 + 본전스톱이 유일하게 유의)의 견고성을 두 축으로 더 흔든다."""
import os, sys, gc, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

HERE = "/home/claude/jq"; UP = "/mnt/user-data/uploads/진우퀀트"
MIN_BARS = 260; W6 = 126
SPLITS = [0.25, 0.50, 0.75]
TRAILS = [0.10, 0.12, 0.20]


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


def run(entry, target, stop0, trail, h, l, c, t, n, H, split, rtrail, mode, keyarr=None):
    """mode: 'be'=본전스톱+트레일 / 'line'=핵심선 종가이탈 / 'line_be'=둘 중 먼저"""
    end = min(t + H, n - 1); peak = entry; stop = stop0
    for j in range(t + 1, end + 1):
        if l[j] <= stop:
            return stop / entry - 1
        if h[j] >= target:
            first = target / entry - 1
            if split >= 1.0: return first
            rpeak = max(peak, h[j])
            rstop = max(rpeak * (1 - rtrail), entry) if mode in ("be", "line_be") else -np.inf
            for k in range(j + 1, end + 1):
                if mode in ("be", "line_be") and l[k] <= rstop:
                    return split * first + (1 - split) * (rstop / entry - 1)
                if mode in ("line", "line_be") and keyarr is not None:
                    kv = keyarr[k]
                    if np.isfinite(kv) and c[k] < kv:
                        return split * first + (1 - split) * (c[k] / entry - 1)
                rpeak = max(rpeak, h[k])
                if mode in ("be", "line_be"):
                    rstop = max(rstop, max(rpeak * (1 - rtrail), entry))
            return split * first + (1 - split) * (c[end] / entry - 1)
        peak = max(peak, h[j]); stop = max(stop, peak * (1 - trail))
    return c[end] / entry - 1


def main():
    L = pd.read_csv(os.path.join(UP, "휩쏘_역사원장.csv"), dtype={"code": str})
    L.columns = [x.strip().lstrip("﻿") for x in L.columns]
    L["code"] = L["code"].str.zfill(6); L["출발일"] = L["출발일"].astype(str)
    typmap = dict(zip(zip(L["code"], L["출발일"]), L["유형"]))
    targets = L.groupby("code")["출발일"].apply(set).to_dict()
    dt = {"code": str, "open": "float32", "high": "float32", "low": "float32",
          "close": "float32", "volume": "float32"}
    rows = []
    for mk in ("KOSPI", "KOSDAQ"):
        D = pd.read_csv(os.path.join(HERE, f"종목일봉_30년_{mk}.csv"), dtype=dt)
        D.columns = [x.strip().lstrip("﻿") for x in D.columns]
        D["code"] = D["code"].str.zfill(6)
        D = D[D["code"].isin(targets.keys())]
        for code, g in D.groupby("code", sort=False):
            want = targets.get(code)
            if not want: continue
            g = g.sort_values("date").reset_index(drop=True)
            g = g[~((g["open"] == 0) & (g["volume"] == 0))].reset_index(drop=True)
            if len(g) < MIN_BARS: continue
            dts = g["date"].values.astype(str)
            o = g["open"].values.astype(float); h = g["high"].values.astype(float)
            l = g["low"].values.astype(float); c = g["close"].values.astype(float)
            o, h, l, c = back_adjust(o, h, l, c, dts)
            n = len(c); cs = pd.Series(c)
            ma240 = cs.rolling(240, min_periods=240).mean().values
            w60, m10 = line_series(g["date"].values, c)
            lines = np.vstack([w60, m10, ma240])
            pos = {d: i for i, d in enumerate(dts)}
            for d in want:
                t = pos.get(d)
                if t is None or t + 1 >= n or not (np.isfinite(c[t]) and c[t] > 0): continue
                cum2 = c[t] / c[t - 2] - 1
                lv = lines[:, t]; dist = c[t] / lv - 1; fin = np.isfinite(dist)
                if not fin.any(): continue
                ki = int(np.nanargmin(np.where(fin, np.abs(dist), np.inf)))
                keyv = lv[ki]; keyarr = lines[ki]
                typ = typmap[(code, d)]; entry = c[t]
                if typ == "A":
                    pre = c[t] / (1 + cum2); target = entry + (pre - entry) * 0.5
                    below = keyv if (np.isfinite(keyv) and keyv < entry) else l[t]
                    stop0 = below * 0.95; trail = 0.12
                else:
                    target = float(np.max(h[max(0, t - 59):t + 1]))
                    below = keyv if (np.isfinite(keyv) and keyv < entry) else l[t]
                    stop0 = below * 0.97; trail = 0.15
                rec = dict(출발일=d, code=code, 창완결_126=(t + W6 <= n - 1))
                rec["기준_카드"] = run(entry, target, stop0, trail, h, l, c, t, n, 40, 1.0, 0, "be")
                for sp in SPLITS:
                    for tr in TRAILS:
                        rec[f"S{int(sp*100)}_T{int(tr*100)}_be"] = run(
                            entry, target, stop0, trail, h, l, c, t, n, 126, sp, tr, "be")
                    rec[f"S{int(sp*100)}_구조"] = run(
                        entry, target, stop0, trail, h, l, c, t, n, 126, sp, 0, "line", keyarr)
                    rec[f"S{int(sp*100)}_구조be"] = run(
                        entry, target, stop0, trail, h, l, c, t, n, 126, sp, 0.20, "line_be", keyarr)
                rows.append(rec)
        del D; gc.collect()
        print(f"{mk} 누적 {len(rows)}", flush=True)

    R = pd.DataFrame(rows)
    M = L.merge(R, on=["출발일", "code"], how="left")
    M.to_csv(os.path.join(HERE, "휩쏘_2단청산_보강.csv"), index=False, encoding="utf-8-sig")

    C = M[(M["창완결_126"] == True)].copy(); C["연"] = C["출발일"].str[:4].astype(int)
    G = C[C["국면"] == "실행"]

    def boot(a, b, yrs, n=4000, seed=11):
        rng = np.random.default_rng(seed); ys = np.array(sorted(set(yrs)))
        idx = {y: np.where(yrs == y)[0] for y in ys}; out = np.empty(n)
        for i in range(n):
            p = rng.choice(ys, size=len(ys), replace=True)
            s = np.concatenate([idx[y] for y in p])
            out[i] = np.nanmean(a[s]) - np.nanmean(b[s])
        lo, hi = np.percentile(out, [2.5, 97.5]) * 100
        return lo, hi

    for name, sub in (("126봉 창완결 전체", C), ("🟢실행 국면만", G)):
        print("\n" + "=" * 76); print(f"[{name}] n={len(sub)}")
        base = sub["기준_카드"].values; yrs = sub["연"].values
        print(f"  기준 카드: 평균 {np.nanmean(base)*100:+.2f} 중앙 {np.nanmedian(base)*100:+.2f} 승률 {(base>0).mean()*100:.1f}%")
        print(f"{'정책':<18}{'평균':>8}{'중앙':>8}{'승률':>8}{'Δ평균':>8}{'    부트95%CI':>20}")
        cols = [c for c in sub.columns if c.startswith("S")]
        for col in cols:
            s = sub[col].dropna(); lo, hi = boot(sub[col].values, base, yrs)
            mark = " ★" if lo > 0 else ""
            print(f"{col:<18}{s.mean()*100:>+8.2f}{s.median()*100:>+8.2f}{(s>0).mean()*100:>7.1f}%"
                  f"{s.mean()*100-np.nanmean(base)*100:>+8.2f}   [{lo:+6.2f},{hi:+6.2f}]{mark}")


if __name__ == "__main__":
    main()
