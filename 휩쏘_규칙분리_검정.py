# -*- coding: utf-8 -*-
"""휩쏘 · §10-B 진입특성별 규칙 분리 30년 검정 — 1단계 시뮬 (2026-08-22)

사전등록: 휩쏘_규칙분리_사전등록_초안.md (v1.1) — 실행 전 고정, 사후 변경 없음.
  표본     : 🟢실행 × (정식A ∪ S2-α) [S2_이벤트_통합.csv] + B형(보조) [휩쏘_역사원장.csv]
  분류축   : Z1 목표거리(훈련 중앙값 8.64% 고정) / Z2 ATR20/종가(훈련 중앙값, 1회 기록) / Z3 MA240 이격(0)
  규칙     : 손절{0.95,0.97,0.92} × 트레일{8,12,20%} × 목표{1/2,1/3,2/3,없음} = 36 · 지평 40 고정
  2차      : 2단 잔여 트레일{8,12,20} × 본전{on,off} = 6 (1차 규칙 = 현행 고정)
엔진 : back_adjust / line_series / simulate 는 휩쏘_2단청산검정.py 와 동일.
출력 : 휩쏘_규칙분리_이벤트.csv
"""
import os, sys, gc, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def _resolve():
    here = os.path.dirname(os.path.abspath(__file__))
    cand = [here, "/home/claude/jq", "/mnt/user-data/uploads/진우퀀트",
            "/mnt/user-data/uploads/진우퀀트/_stagetmp4"]
    def find(name):
        for d in cand:
            p = os.path.join(d, name)
            if os.path.exists(p): return p
        return os.path.join(here, name)
    return here, find
HERE, F = _resolve()
MIN_BARS = 260; H = 40; W6 = 126

STOPS  = [0.95, 0.97, 0.92]
TRAILS = [0.08, 0.12, 0.20]
TGTS   = [("h", 0.5), ("t", 1/3), ("u", 2/3), ("n", None)]
RUN_TR = [0.08, 0.12, 0.20]; RUN_BE = ["be", "tr"]


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

def simulate(entry, target, stop0, trail, h, l, c, t, n, horizon,
             split=0.0, runner_trail=None, runner_stop_mode="tr"):
    """휩쏘_2단청산검정.py::simulate 와 동일."""
    end = min(t + horizon, n - 1)
    peak = entry; stop = stop0
    rt = runner_trail if runner_trail is not None else trail
    for j in range(t + 1, end + 1):
        if l[j] <= stop:
            return stop / entry - 1, j - t, ("손절" if stop <= stop0 * 1.0001 else "트레일")
        if target is not None and h[j] >= target:
            first = target / entry - 1
            if split <= 0:
                return first, j - t, "목표"
            rpeak = max(peak, h[j]); rstop = rpeak * (1 - rt)
            if runner_stop_mode == "be": rstop = max(rstop, entry)
            for k in range(j + 1, end + 1):
                if l[k] <= rstop:
                    return split * first + (1 - split) * (rstop / entry - 1), k - t, "2단트레일"
                rpeak = max(rpeak, h[k]); ns = rpeak * (1 - rt)
                if runner_stop_mode == "be": ns = max(ns, entry)
                rstop = max(rstop, ns)
            return split * first + (1 - split) * (c[end] / entry - 1), end - t, "2단만기"
        peak = max(peak, h[j]); stop = max(stop, peak * (1 - trail))
    return c[end] / entry - 1, end - t, "만기"


def load_events():
    S = pd.read_csv(F("S2_이벤트_통합.csv"), dtype={"code": str})
    S["code"] = S["code"].str.zfill(6)
    S["미달n"] = S["미달"].fillna("").apply(lambda x: 0 if x == "" else len(x.split(",")))
    alpha = (S["신호"] == "S2") & (S["미달n"] == 1) & (~S["미달"].fillna("").str.contains("2일누적"))
    P = S[(S["국면"] == "실행") & ((S["신호"] == "A") | alpha)].copy()
    P["유형"] = np.where(P["신호"] == "A", "A", "S2a")
    P = P.rename(columns={"date": "출발일"})[["출발일", "code", "유형", "cum2", "gap240", "연"]]
    L = pd.read_csv(F("휩쏘_역사원장.csv"), dtype={"code": str})
    L.columns = [x.strip().lstrip("﻿") for x in L.columns]
    L["code"] = L["code"].str.zfill(6); L["출발일"] = L["출발일"].astype(str)
    B = L[(L["유형"] == "B") & (L["국면"] == "실행")].copy()
    B["유형"] = "B"; B["cum2"] = np.nan; B["gap240"] = np.nan; B["연"] = B["출발일"].str[:4].astype(int)
    B = B[["출발일", "code", "유형", "cum2", "gap240", "연"]]
    E = pd.concat([P, B], ignore_index=True)
    E["출발일"] = E["출발일"].astype(str)
    return E


def main():
    E = load_events()
    print(f"이벤트 {len(E)}건 · {E['유형'].value_counts().to_dict()}", flush=True)
    targets = E.groupby("code")["출발일"].apply(set).to_dict()
    typmap = dict(zip(zip(E["code"], E["출발일"]), E["유형"]))
    dt = {"code": str, "open": "float32", "high": "float32", "low": "float32",
          "close": "float32", "volume": "float32"}
    rows = []
    for mk in ("KOSPI", "KOSDAQ"):
        src = F(f"bars_{mk}.csv.gz")
        if not os.path.exists(src): src = F(f"종목일봉_30년_{mk}.csv")
        print(f"[{mk}] {src}", flush=True)
        D = pd.read_csv(src, dtype=dt)
        D.columns = [x.strip().lstrip("﻿") for x in D.columns]
        D["code"] = D["code"].str.zfill(6)
        D = D[D["code"].isin(targets.keys())]
        LASTD = None
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
            # ATR20 (진입일 포함 직전 20봉, 미래 정보 없음)
            pc = np.roll(c, 1); pc[0] = c[0]
            tr = np.maximum(h - l, np.maximum(np.abs(h - pc), np.abs(l - pc)))
            atr20 = pd.Series(tr).rolling(20, min_periods=20).mean().values
            pos = {d: i for i, d in enumerate(dts)}
            for d in want:
                t = pos.get(d)
                if t is None or t < 2 or t + 1 >= n: continue
                if not (np.isfinite(c[t]) and c[t] > 0): continue
                typ = typmap[(code, d)]; entry = c[t]
                cum2 = c[t] / c[t - 2] - 1
                lv = lines[:, t]; dist = c[t] / lv - 1; fin = np.isfinite(dist)
                if not fin.any(): continue
                keyv = lv[int(np.nanargmin(np.where(fin, np.abs(dist), np.inf)))]
                below = keyv if (np.isfinite(keyv) and keyv < entry) else l[t]
                rec = dict(출발일=d, code=code, 유형=typ, 시장=mk,
                           창완결_40=bool(t + H <= n - 1), 창완결_126=bool(t + W6 <= n - 1),
                           cum2=cum2, gap240=(c[t] / ma240[t] - 1) if np.isfinite(ma240[t]) else np.nan,
                           atr_pct=(atr20[t] / c[t]) if np.isfinite(atr20[t]) else np.nan)
                if typ in ("A", "S2a"):
                    pre = c[t] / (1 + cum2)
                    rec["목표거리"] = (pre - entry) * 0.5 / entry
                    def tgt_of(frac): return None if frac is None else entry + (pre - entry) * frac
                    cur_stop = 0.95; cur_trail = 0.12
                else:  # B: 목표 = 직전 60봉 고가. 분수 목표는 '되돌림 비율'로 해석
                    hi60 = float(np.max(h[max(0, t - 59):t + 1]))
                    rec["목표거리"] = hi60 / entry - 1
                    def tgt_of(frac): return None if frac is None else entry + (hi60 - entry) * (frac / 0.5)
                    cur_stop = 0.97; cur_trail = 0.15
                stop_cur = below * cur_stop
                # 현행 카드(P0) · 현행 2단(P1) 재현
                r, b, w = simulate(entry, tgt_of(0.5), stop_cur, cur_trail, h, l, c, t, n, H)
                rec["P0"] = r; rec["P0_봉"] = b; rec["P0_사유"] = w
                r, b, w = simulate(entry, tgt_of(0.5), stop_cur, cur_trail, h, l, c, t, n, W6,
                                   split=0.5, runner_trail=0.12, runner_stop_mode="be")
                rec["P1"] = r; rec["P1_봉"] = b
                rec["보유40"] = c[min(t + H, n - 1)] / entry - 1
                # 36 규칙
                for sm in STOPS:
                    for trl in TRAILS:
                        for tk, frac in TGTS:
                            r, b, w = simulate(entry, tgt_of(frac), below * sm, trl, h, l, c, t, n, H)
                            key = f"R_s{int(sm*100)}_t{int(trl*100)}_{tk}"
                            rec[key] = r; rec[key + "_봉"] = b
                # 2차: 잔여 규칙 6 (1차 = 현행 고정, 126봉)
                for rt in RUN_TR:
                    for be in RUN_BE:
                        r, b, w = simulate(entry, tgt_of(0.5), stop_cur, cur_trail, h, l, c, t, n, W6,
                                           split=0.5, runner_trail=rt, runner_stop_mode=be)
                        rec[f"Q_t{int(rt*100)}_{be}"] = r
                rows.append(rec)
        del D; gc.collect()
        print(f"  {mk} 누적 {len(rows)}", flush=True)
    R = pd.DataFrame(rows)
    R["연"] = R["출발일"].str[:4].astype(int)
    R.to_csv(os.path.join(HERE, "휩쏘_규칙분리_이벤트.csv"), index=False, encoding="utf-8-sig")
    print(f"\n저장 휩쏘_규칙분리_이벤트.csv {R.shape}")
    print(R["유형"].value_counts().to_dict(), "창완결40:", R["창완결_40"].mean().round(3))

if __name__ == "__main__":
    main()
