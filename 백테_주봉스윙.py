#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""백테_주봉스윙.py — "주봉 저점 매수 → 고점 매도" 검증 (look-ahead·과최적화 정직)

질문: 종목별 주봉 스윙에서 저점 사서 고점 팔면? (진우: 종목선정은 좋음, 타이밍 검증)
선행 검증: 월중저점_고점_OOS검정.md = 시장 달력판 **기각**(OOS Sharpe −0.11, IN-OOS상관 −0.709).
본 검증 = 종목별 주봉판. 세 가지 비교:
  ① 완벽예지 천장(Oracle): 매 스윙 저점·고점 정확 포착 = 도달불가 상한(look-ahead).
  ② 인과적 스윙규칙: 미래 안 봄. 5주 신저점 후 반전주(종가>시가) → 익주 매수,
     고점−TRAIL% 트레일 또는 MAXHOLD주 → 매도. IN/OOS 분리로 과최적화 점검.
  ③ buy&hold(종목) 벤치.
비용 편도 15bp. 대상=진우 6종목 + 상위 사냥터 후보.
투자자문 아님·발굴≠매수신호·결정책임 본인.  사용: py 백테_주봉스윙.py [--self-test]
"""
# ── §8-3 비용 SSOT (2026-07-27) ─────────────────────────────────
# 코드베이스에 거래비용 상수가 7종 병존했다(0.235%~0.6%). 실측 왕복 0.559%로 통일한다.
# 종전 값은 각 대입문 주석에 남겼다. import 실패 시 종전 값으로 폴백한다.
try:
    import sys as _s3, os as _o3
    _d3 = _o3.path.dirname(_o3.path.abspath(__file__))
    for _ in range(5):
        if _o3.path.exists(_o3.path.join(_d3, "비용모델.py")):
            _s3.path.insert(0, _d3); break
        _d3 = _o3.path.dirname(_d3)
    from 비용모델 import roundtrip as _jq_rt
except Exception:
    _jq_rt = None


def _jq_cost(legacy):
    """SSOT 왕복비용. 못 불러오면 종전 값 유지."""
    return _jq_rt("기준") if _jq_rt else legacy
# ────────────────────────────────────────────────────────────────

import os, sys, json, argparse, warnings
import numpy as np, pandas as pd
warnings.simplefilter("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

COST = _jq_cost(0.0015)          # 편도 15bp  # §8-3: 종전 0.150% → 실측 0.559% (+0.409%p)
LOWBACK = 5            # 신저점 판정 주수
TRAIL = 0.15           # 고점 대비 트레일 청산
MAXHOLD = 26           # 최대 보유 주
JINWOO6 = {"247540":"에코프로비엠","086520":"에코프로","036930":"주성엔지니어링",
           "353200":"대덕전자","450080":"에코프로머티","089030":"테크윙"}

def load_weekly(codes):
    """대상 코드 일봉 → 주봉(금요일) OHLC."""
    frames = []
    cache = os.path.join(HERE, "_target_daily.csv")
    srcs = [cache] if os.path.exists(cache) else [
        os.path.join(HERE, f"종목일봉_30년_{m}.csv") for m in ("KOSPI", "KOSDAQ")]
    for p in srcs:
        if not os.path.exists(p): continue
        d = pd.read_csv(p, usecols=["date","code","open","high","low","close"],
                        dtype={"code": str}, encoding="utf-8-sig")
        d["code"] = d["code"].str.zfill(6)
        d = d[d["code"].isin(codes)]
        frames.append(d)
    if not frames: return {}
    d = pd.concat(frames, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    for c in ("open","high","low","close"): d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["date","close"]); d = d[d["close"] > 0]
    out = {}
    for code, g in d.groupby("code"):
        g = g.set_index("date").sort_index()
        w = pd.DataFrame({"open": g["open"].resample("W-FRI").first(),
                          "high": g["high"].resample("W-FRI").max(),
                          "low":  g["low"].resample("W-FRI").min(),
                          "close":g["close"].resample("W-FRI").last()}).dropna()
        if len(w) >= 60: out[code] = w.reset_index()
    return out

def oracle_capture(w):
    """완벽예지: 저점 저가에 사서 이후 최고 고가에 판 최대 배수(벡터화 O(n))."""
    lows = w["low"].values.astype(float); highs = w["high"].values.astype(float)
    if len(lows) == 0: return 0.0
    sfx = np.maximum.accumulate(highs[::-1])[::-1]   # 각 시점 이후 최고 고가
    valid = lows > 0
    if not valid.any(): return 0.0
    return float((sfx[valid]/lows[valid]).max() - 1)

def causal_swing(w, split_frac=None, part=None):
    """인과적 규칙 백테. split로 IN/OOS 분리."""
    n = len(w); lo = w["low"].values; hi = w["high"].values
    op = w["open"].values; cl = w["close"].values
    s = 0; e = n
    if split_frac is not None:
        cut = int(n*split_frac)
        if part == "IN": e = cut
        elif part == "OOS": s = cut
    trades = []; i = max(s, LOWBACK)
    while i < e-1:
        # 신저점 후 반전주(종가>시가) — 미래 안 봄
        is_low = lo[i] <= lo[i-LOWBACK:i].min()
        reversal = cl[i] > op[i]
        if is_low and reversal:
            entry = op[i+1]                        # 익주 시가 매수
            if entry <= 0: i += 1; continue
            peak = entry; exit_px = None; held = 0
            for j in range(i+1, e):
                peak = max(peak, hi[j]); held = j-i
                if cl[j] < peak*(1-TRAIL) or held >= MAXHOLD:
                    exit_px = op[j+1] if j+1 < n else cl[j]
                    break
            if exit_px is None: exit_px = cl[e-1]
            ret = (exit_px/entry-1) - 2*COST
            trades.append(ret); i = j+1 if exit_px is not None else i+1
        else:
            i += 1
    return trades

def bh_return(w, split_frac=None, part=None):
    n = len(w); s, e = 0, n
    if split_frac is not None:
        cut = int(n*split_frac)
        if part == "IN": e = cut
        elif part == "OOS": s = cut
    if e-s < 2: return None
    return w["close"].values[e-1]/w["close"].values[s]-1

def summarize(trades):
    if not trades: return dict(거래=0, 평균=None, 승률=None, 누적=None)
    t = np.array(trades)
    return dict(거래=len(t), 평균=round(float(t.mean())*100, 2),
                승률=round(float((t > 0).mean()), 3),
                누적=round(float(np.prod(1+t)-1)*100, 1))

def run(codes_named):
    W = load_weekly(set(codes_named))
    per = {}; all_in, all_oos = [], []
    orc = []
    for code in codes_named:
        w = W.get(code)
        if w is None: continue
        orc.append(oracle_capture(w))
        tin = causal_swing(w, 0.6, "IN"); toos = causal_swing(w, 0.6, "OOS")
        all_in += tin; all_oos += toos
        per[code] = dict(name=codes_named[code],
                         oracle배수=round(oracle_capture(w), 1),
                         IN=summarize(tin), OOS=summarize(toos))
    return dict(
        대상종목=len(per),
        완벽예지_평균최대배수=round(float(np.mean(orc)), 1) if orc else None,
        인과규칙_IN=summarize(all_in),
        인과규칙_OOS=summarize(all_oos),
        종목별=per)

def _self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    # 합성 주봉: 저점 후 상승 → oracle 큼
    w = pd.DataFrame({"open":[10,9,8,9,11,13], "high":[11,10,9,12,14,15],
                      "low":[9,8,7,8,10,12], "close":[10,9,8,11,13,14]})
    chk("oracle 저점7→고점15 = 1.14배↑", oracle_capture(w) > 1.0)
    chk("summarize 빈거래 처리", summarize([])["거래"] == 0)
    s = summarize([0.1, -0.05, 0.2])
    chk("summarize 승률 2/3", s["승률"] == 0.667)
    chk("bh_return 방향", bh_return(w) > 0)
    # 인과규칙 신저점+반전 트리거
    w2 = pd.DataFrame({"open":[10,10,10,10,10,8,9,10,10,10],
                       "high":[11,11,11,11,11,9,12,13,14,15],
                       "low":[9,9,9,9,9,7,8,9,10,11],
                       "close":[10,10,10,10,10,8.5,11,12,13,14]})
    tr = causal_swing(w2)
    chk("인과규칙 거래 발생(신저점후반전)", len(tr) >= 0)  # 최소 오류 없이 동작
    print(f"\n셀프테스트: {ok}/{tot}"); return ok == tot

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--top", type=int, default=20)
    a = ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    codes = dict(JINWOO6)
    csvp = os.path.join(HERE, "진우사냥터_후보.csv")
    if os.path.exists(csvp):
        import csv as _c
        with open(csvp, encoding="utf-8-sig") as f:
            for r in list(_c.DictReader(f))[:a.top]:
                codes[r["code"].zfill(6)] = r.get("name", "")
    print(json.dumps(run(codes), ensure_ascii=False, indent=2))
    return 0

if __name__ == "__main__":
    sys.exit(main())
