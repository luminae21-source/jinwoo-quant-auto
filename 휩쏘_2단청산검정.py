# -*- coding: utf-8 -*-
r"""휩쏘_2단청산검정.py — 열린 과제 #1.

질문: "목표 도달 시 절반 매도 + 나머지 트레일"이 현행 전량청산 카드보다 나은가?
      (6M 고점 중앙 +26.6% vs 카드청산 평균 +1.1% 간극을 실제로 얼마나 회수하는가)

[방법] 역사원장 2,801건을 그대로 쓰되, 진입일 t의 백조정 OHLC를 재구성해
       동일 진입가·동일 목표가·동일 초기손절에서 '청산 정책만' 바꿔 재시뮬.
       → 신호는 건드리지 않으므로 사후선택 편향 없음. 정책 그리드는 사전 고정.

[정책]
  P0 카드      : 목표/손절/트레일, 40봉 상한, 전량.                 (현행·재현 대상)
  P1 2단       : 목표 도달 시 50% 실현 → 잔여 50%를 트레일로 연장.
  P2 트레일만  : 목표 없이 트레일만 (분할 없음). 2단의 상단 참조선.
⚠️ 생존편향·소규모 기업행위 잔존·이벤트 위기해 클러스터 → Δ는 시사이지 확정 아님.
"""
import os, sys, gc, json, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

HERE = "/home/claude/jq"
UP = "/mnt/user-data/uploads/진우퀀트"
OUT = HERE

NEAR = 0.08
MIN_BARS = 260
W6 = 126

# ── 사전 고정 정책 그리드 ────────────────────────────────────────────
TRAILS = [0.10, 0.12, 0.15, 0.20, 0.25]
HORIZONS = [40, 63, 126]
STOPMODES = ["be", "tr"]     # be=잔여분 손절을 본전으로 / tr=트레일만(본전 아래 허용)
SPLITS = [0.5]               # 절반 매도 (형 제안)


# ── 역사검정과 동일한 백조정 ──────────────────────────────────────────
def era_limit(dstr):
    return 0.30 if dstr >= "2015-06-15" else 0.15


def back_adjust(o, h, l, c, dts):
    n = len(c)
    adj = np.ones(n); cum = 1.0
    for i in range(n - 1, 0, -1):
        prev, cur = c[i - 1], c[i]
        if prev > 0 and cur > 0:
            r = cur / prev
            lim = era_limit(dts[i]) + 0.03
            if r < (1 - lim) or r > (1 + lim):
                cum *= r
        adj[i - 1] = cum
    return o * adj, h * adj, l * adj, c * adj


def line_series(dates, c):
    s = pd.Series(c, index=pd.to_datetime(dates))
    wk = s.resample("W-FRI").last().dropna()
    mo = s.resample("ME").last().dropna()
    wkm = wk.rolling(60, min_periods=60).mean()
    mom = mo.rolling(10, min_periods=10).mean()
    di = s.index
    w = wkm.reindex(di.union(wkm.index)).ffill().reindex(di).values
    m = mom.reindex(di.union(mom.index)).ffill().reindex(di).values
    return w, m


# ── 청산 시뮬레이터 ──────────────────────────────────────────────────
def simulate(entry, target, stop0, trail, h, l, c, t, n, horizon,
             split=0.0, runner_trail=None, runner_stop_mode="tr"):
    """split=0 → 전량(카드/트레일만). split>0 → 목표 도달 시 split 비율 실현 후 잔여 연장.
       target=None → 목표 없음(트레일만)."""
    end = min(t + horizon, n - 1)
    peak = entry; stop = stop0
    rt = runner_trail if runner_trail is not None else trail
    for j in range(t + 1, end + 1):
        if l[j] <= stop:
            r = stop / entry - 1
            return r, j - t, ("손절" if stop <= stop0 * 1.0001 else "트레일"), np.nan, 0
        if target is not None and h[j] >= target:
            first = target / entry - 1
            if split <= 0:
                return first, j - t, "목표", np.nan, 0
            # ── 2단: split 실현, 잔여를 트레일로 연장
            rpeak = max(peak, h[j])
            rstop = rpeak * (1 - rt)
            if runner_stop_mode == "be":
                rstop = max(rstop, entry)
            for k in range(j + 1, end + 1):
                if l[k] <= rstop:
                    second = rstop / entry - 1
                    tot = split * first + (1 - split) * second
                    return tot, k - t, "2단트레일", second, k - j
                rpeak = max(rpeak, h[k])
                ns = rpeak * (1 - rt)
                if runner_stop_mode == "be":
                    ns = max(ns, entry)
                rstop = max(rstop, ns)
            second = c[end] / entry - 1
            tot = split * first + (1 - split) * second
            return tot, end - t, "2단만기", second, end - j
        peak = max(peak, h[j])
        stop = max(stop, peak * (1 - trail))
    return c[end] / entry - 1, end - t, "만기", np.nan, 0


def main():
    L = pd.read_csv(os.path.join(UP, "휩쏘_역사원장.csv"), dtype={"code": str})
    L.columns = [x.strip().lstrip("﻿") for x in L.columns]
    L["code"] = L["code"].str.zfill(6)
    L["출발일"] = L["출발일"].astype(str)
    targets = L.groupby("code")["출발일"].apply(set).to_dict()
    print(f"원장 {len(L)}건 · 종목 {len(targets)}", flush=True)

    dt = {"code": str, "open": "float32", "high": "float32", "low": "float32",
          "close": "float32", "volume": "float32"}
    rows = []
    for mk in ("KOSPI", "KOSDAQ"):
        p = os.path.join(HERE, f"종목일봉_30년_{mk}.csv")
        print(f"{mk} 로딩…", flush=True)
        D = pd.read_csv(p, dtype=dt)
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
            l = g["low"].values.astype(float);  c = g["close"].values.astype(float)
            o, h, l, c = back_adjust(o, h, l, c, dts)
            n = len(c)
            cs = pd.Series(c)
            ma240 = cs.rolling(240, min_periods=240).mean().values
            w60, m10 = line_series(g["date"].values, c)
            lines = np.vstack([w60, m10, ma240])
            pos = {d: i for i, d in enumerate(dts)}
            for d in want:
                t = pos.get(d)
                if t is None or t + 1 >= n or not (np.isfinite(c[t]) and c[t] > 0):
                    continue
                cum2 = c[t] / c[t - 2] - 1 if t >= 2 else np.nan
                lv = lines[:, t]
                dist = c[t] / lv - 1
                finite = np.isfinite(dist)
                if not finite.any(): continue
                ki = int(np.nanargmin(np.where(finite, np.abs(dist), np.inf)))
                keyline_v = lv[ki]
                typ = L.loc[(L["code"] == code) & (L["출발일"] == d), "유형"].iloc[0]
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

                rec = dict(출발일=d, code=code, 유형=typ,
                           창완결_126=(t + W6 <= n - 1), 잔여봉=n - 1 - t)
                # 참조: 6M 고점
                e6 = min(t + W6, n - 1)
                hw = h[t + 1:e6 + 1]
                rec["고점6M"] = (np.nanmax(hw) / entry - 1) if len(hw) else np.nan

                # P0 카드 (재현)
                r, b, how, _, _ = simulate(entry, target, stop0, trail, h, l, c, t, n, 40)
                rec["P0_카드"] = r; rec["P0_how"] = how; rec["P0_bars"] = b
                # P0 확장(전량, 목표 유지, 지평만 연장) — 지평 효과 분리용
                for H in HORIZONS:
                    r2, _, _, _, _ = simulate(entry, target, stop0, trail, h, l, c, t, n, H)
                    rec[f"P0_H{H}"] = r2
                # P2 트레일만 (목표 없음)
                for H in HORIZONS:
                    for tr in TRAILS:
                        r3, _, _, _, _ = simulate(entry, None, stop0, tr, h, l, c, t, n, H)
                        rec[f"P2_T{int(tr*100)}_H{H}"] = r3
                # P1 2단
                for H in HORIZONS:
                    for tr in TRAILS:
                        for sm in STOPMODES:
                            for sp in SPLITS:
                                r4, b4, how4, sec, rb = simulate(
                                    entry, target, stop0, trail, h, l, c, t, n, H,
                                    split=sp, runner_trail=tr, runner_stop_mode=sm)
                                key = f"P1_T{int(tr*100)}_H{H}_{sm}"
                                rec[key] = r4
                                if H == 126 and tr == 0.20 and sm == "tr":
                                    rec["P1대표_잔여수익"] = sec
                                    rec["P1대표_잔여봉"] = rb
                                    rec["P1대표_how"] = how4
                rows.append(rec)
        del D; gc.collect()
        print(f"  {mk} 누적 {len(rows)}건", flush=True)

    R = pd.DataFrame(rows)
    M = L.merge(R, on=["출발일", "code", "유형"], how="left")
    M.to_csv(os.path.join(OUT, "휩쏘_2단청산_이벤트.csv"), index=False, encoding="utf-8-sig")
    print(f"\n저장: 휩쏘_2단청산_이벤트.csv ({len(M)}건, 시뮬 {R.shape[0]}건)")
    print(f"컬럼 {M.shape[1]}")


if __name__ == "__main__":
    main()
