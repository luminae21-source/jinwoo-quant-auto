#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""백테_스타일_시간손절.py — H1: 스타일별 차등 시간손절이 단일 20일보다 나은가?

사전등록: 진우_매매스타일_진입타점_사전등록.md §4
- 진입·사이징·ATR트레일링·비용은 jq_system_backtest.py와 동일(stable 진입). 순수 시간손절만 비교.
- A(baseline): 시간손절 단일 20일.  B(style): vol60로 단기10/스윙20/중장기무한.
- 판정: B가 A 대비 CAGR·평균R·Sharpe 개선? 미달이면 차등 폐기, 단일 유지(H0).
- 벤치 buy&hold. PIT 데이터(생존편향 제거).  투자자문 아님·집행책임 본인.
사용: py 백테_스타일_시간손절.py [--self-test]
"""
import os, sys, json, argparse, warnings
import numpy as np, pandas as pd
warnings.simplefilter("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

C = dict(MA=200, ATR_N=14, ATR_K=2.5, STOP_CAP=0.20, TIME_BAND=0.05,
         EXT_MIN=1.00, EXT_MAX=1.40, STOP_MAX=0.15, VOL_MIN=3e9,
         RISK=0.01, MAX_POS=7, COST_BUY=0.0015, COST_SELL=0.0033, CAP0=10_000_000)
TIME_UNIFORM = 20
STYLE_TD = {"단기": 10, "스윙": 20, "중장기": 10**9}
VOL_HI, VOL_MID = 0.06, 0.03

def style_of(v):
    if not (v == v): return "스윙"
    if v >= VOL_HI: return "단기"
    if v >= VOL_MID: return "스윙"
    return "중장기"

def load(files=("kosdaq_pit_daily.csv",)):
    fs = []
    for f in files:
        p = os.path.join(HERE, f)
        if not os.path.exists(p): continue
        d = pd.read_csv(p, dtype={"code": str}, encoding="utf-8-sig")
        d.columns = [c.lstrip("﻿") for c in d.columns]
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        for c in ("open", "high", "low", "close", "volume"):
            if c in d.columns: d[c] = pd.to_numeric(d[c], errors="coerce")
        fs.append(d)
    if not fs: return None
    d = pd.concat(fs, ignore_index=True).dropna(subset=["date", "close", "high", "low"])
    return d.sort_values(["code", "date"])

def prep(d):
    """벡터화 groupby-transform으로 지표+진입신호 계산 후 종목별 dict."""
    d = d.sort_values(["code", "date"]).reset_index(drop=True)
    gc = d.groupby("code", sort=False)
    pc = gc["close"].shift(1)
    tr = pd.concat([d["high"]-d["low"], (d["high"]-pc).abs(), (d["low"]-pc).abs()], axis=1).max(axis=1)
    d["atr"] = tr.groupby(d["code"], sort=False).transform(lambda s: s.rolling(C["ATR_N"]).mean())
    d["ma"] = gc["close"].transform(lambda s: s.rolling(C["MA"]).mean())
    v = d["close"] * d["volume"]
    d["v20"] = v.groupby(d["code"], sort=False).transform(lambda s: s.rolling(20).mean())
    d["v60"] = v.groupby(d["code"], sort=False).transform(lambda s: s.rolling(60).mean())
    ret = gc["close"].pct_change()
    d["vol60"] = ret.groupby(d["code"], sort=False).transform(lambda s: s.rolling(60, min_periods=40).std())
    ext = d["close"]/d["ma"]; infl = (d["v20"]/d["v60"]).fillna(1.0)
    d["ext"] = ext
    d["entry"] = (d["ma"].notna() & d["atr"].notna() & (d["atr"] > 0) & d["v20"].notna()
                  & (d["v20"] >= C["VOL_MIN"]) & (d["close"] > d["ma"])
                  & (ext >= C["EXT_MIN"]) & (ext <= C["EXT_MAX"])
                  & ((C["ATR_K"]*d["atr"]/d["close"]) <= C["STOP_MAX"])
                  & (infl >= 1.0)).fillna(False)
    out = {}
    for code, g in d.groupby("code", sort=False):
        if len(g) < C["MA"] + 30: continue
        out[code] = g.reset_index(drop=True)
    return out

def build_cands(G):
    """date -> [(code, i, ext), ...]  (진입 가능 & 익일 존재)."""
    cb = {}
    for code, g in G.items():
        ent = g["entry"].values; n = len(g)
        dates = g["date"].values; exts = g["ext"].values
        for i in np.nonzero(ent)[0]:
            if i+1 < n:
                cb.setdefault(dates[i], []).append((code, int(i), float(exts[i])))
    return cb

def run(G, cb, idx, use_style):
    dates = sorted({dt for g in G.values() for dt in g["date"].values})
    eq = C["CAP0"]; pos = {}; curve = []; trades = []
    for dt in dates:
        for code in list(pos):
            g = G[code]; i = idx[code].get(dt)
            if i is None: continue
            p = pos[code]
            hi = max(p["hi"], g["high"].iat[i]); p["hi"] = hi
            a = g["atr"].iat[i] if pd.notna(g["atr"].iat[i]) else p["atr0"]
            eff = max(p["stop"], hi - C["ATR_K"]*a)
            cl = g["close"].iat[i]; held = i - p["i0"]
            td = STYLE_TD[p["style"]] if use_style else TIME_UNIFORM
            hit = (cl < eff) or (held >= td and abs(cl/p["entry"]-1) <= C["TIME_BAND"])
            if hit and i+1 < len(g):
                px = g["open"].iat[i+1]
                pnl = p["qty"]*(px-p["entry"]) - p["qty"]*px*C["COST_SELL"]
                eq += pnl
                trades.append(dict(style=p["style"],
                                   R=(pnl/(p["qty"]*p["R"])) if p["qty"]*p["R"] > 0 else 0, days=held))
                del pos[code]
        if len(pos) < C["MAX_POS"]:
            cands = sorted(cb.get(dt, []), key=lambda x: x[2])   # 덜 뻗은 순
            for code, i, _ in cands:
                if len(pos) >= C["MAX_POS"]: break
                if code in pos: continue
                g = G[code]; entry = g["open"].iat[i+1]; a = g["atr"].iat[i]
                if not (entry > 0 and a > 0): continue
                stop = max(entry-C["ATR_K"]*a, entry*(1-C["STOP_CAP"])); R = entry-stop
                if R <= 0: continue
                qty = int((eq*C["RISK"])//R)
                if qty <= 0 or qty*entry > eq*0.25: continue
                eq -= qty*entry*C["COST_BUY"]
                pos[code] = dict(entry=entry, stop=stop, R=R, qty=qty, hi=entry, i0=i+1,
                                 atr0=a, style=style_of(g["vol60"].iat[i]))
        mtm = 0.0
        for code, p in pos.items():
            i = idx[code].get(dt)
            if i is not None: mtm += p["qty"]*(G[code]["close"].iat[i]-p["entry"])
        curve.append((dt, eq+mtm))
    E = pd.Series(dict(curve)).sort_index(); r = E.pct_change().dropna()
    n = len(r)/252.0
    cagr = float((E.iloc[-1]/E.iloc[0])**(1/max(n, 1e-9))-1)
    sharpe = float(r.mean()/r.std()*np.sqrt(252)) if r.std() > 0 else float("nan")
    mdd = float((E/E.cummax()-1).min())
    T = pd.DataFrame(trades)
    by = {}
    if len(T):
        for st, sub in T.groupby("style"):
            by[st] = dict(거래=len(sub), 승률=round(float((sub.R > 0).mean()), 3),
                          평균R=round(float(sub.R.mean()), 3), 평균보유일=round(float(sub.days.mean()), 1))
    return dict(CAGR=round(cagr, 4), Sharpe=round(sharpe, 3), MDD=round(mdd, 4),
                최종자본=int(E.iloc[-1]), 거래수=len(T),
                승률=round(float((T.R > 0).mean()), 3) if len(T) else None,
                평균R=round(float(T.R.mean()), 3) if len(T) else None,
                기간=f"{pd.Timestamp(E.index[0]).date()}~{pd.Timestamp(E.index[-1]).date()}", 스타일별=by)

def benchmark(E_start, E_end):
    p = os.path.join(HERE, "kospi_index_daily.csv")
    if not os.path.exists(p): return None
    try:
        k = pd.read_csv(p, parse_dates=["Date"]).set_index("Date")["Close"]
    except Exception:
        return None
    k = k[(k.index >= E_start) & (k.index <= E_end)]
    kr = k.pct_change().dropna()+0.018/252
    if len(kr) < 2: return None
    kc = (1+kr).cumprod()
    return dict(CAGR=round(float(kc.iloc[-1]**(1/max(len(kr)/252, 1e-9))-1), 4),
                Sharpe=round(float(kr.mean()/kr.std()*np.sqrt(252)), 3),
                MDD=round(float((kc/kc.cummax()-1).min()), 4))

def _self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    chk("style_of 6%↑=단기", style_of(0.07) == "단기")
    chk("style_of 4%=스윙", style_of(0.04) == "스윙")
    chk("style_of 2%=중장기", style_of(0.02) == "중장기")
    chk("style_of nan=스윙", style_of(float('nan')) == "스윙")
    chk("중장기 시간손절 무한", STYLE_TD["중장기"] > 10**8)
    chk("단기<스윙<중장기", STYLE_TD["단기"] < STYLE_TD["스윙"] < STYLE_TD["중장기"])
    print(f"\n셀프테스트: {ok}/{tot}"); return ok == tot

def _load_prep_cached():
    import pickle
    cache = os.path.join(HERE, "_prep.pkl")
    if os.path.exists(cache):
        return pickle.load(open(cache, "rb"))
    d = load()
    if d is None: return None
    G = prep(d)
    pickle.dump(G, open(cache, "wb"))
    return G

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--prep", action="store_true", help="prep 계산 후 _prep.pkl 캐시만 저장")
    a = ap.parse_args()
    if a.self_test: sys.exit(0 if _self_test() else 1)
    import time; t0 = time.time()
    if a.prep:
        d = load()
        if d is None: print("PIT 없음"); sys.exit(2)
        import pickle; G = prep(d)
        pickle.dump(G, open(os.path.join(HERE, "_prep.pkl"), "wb"))
        print(f"prep 캐시 저장 {len(G)}종목 {time.time()-t0:.1f}s"); sys.exit(0)
    G = _load_prep_cached()
    if G is None: print(json.dumps({"err": "PIT 데이터 없음"})); sys.exit(2)
    print(f"prep(캐시) {len(G)}종목 {time.time()-t0:.1f}s", file=sys.stderr)
    idx = {c: {dt: i for i, dt in enumerate(g["date"].values)} for c, g in G.items()}
    cb = build_cands(G); print(f"cands {time.time()-t0:.1f}s", file=sys.stderr)
    A = run(G, cb, idx, False); print(f"A {time.time()-t0:.1f}s", file=sys.stderr)
    B = run(G, cb, idx, True); print(f"B {time.time()-t0:.1f}s", file=sys.stderr)
    E0 = pd.Timestamp(sorted({dt for g in G.values() for dt in g['date'].values})[0])
    E1 = pd.Timestamp(sorted({dt for g in G.values() for dt in g['date'].values})[-1])
    bh = benchmark(E0, E1)
    verdict = "B채택(차등 우세)" if (A["평균R"] is not None and B["평균R"] is not None
              and B["CAGR"] >= A["CAGR"] and B["평균R"] >= A["평균R"]) else "H0: 차등 무효 → 단일20일 유지"
    print(json.dumps({"A_단일20일": A, "B_스타일차등": B, "buyhold": bh, "판정": verdict},
                     ensure_ascii=False, indent=2))
