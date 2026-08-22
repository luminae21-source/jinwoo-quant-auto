# -*- coding: utf-8 -*-
r"""휩쏘_목표계수_검정.py — 과제① : 목표가를 늘리면 종목군별로 갈리는가?

[동기] 종목군 현황판에서 나온 것:
   반도체 체인 — 카드 +2.08% 인데 40일 그냥 두면 +9.55%  (갭 7.47%p)
   기타 업종   — 카드 +1.84% 인데 40일 그냥 두면 +4.88%  (갭 3.05%p)
   목표 도달까지 중앙 2봉. 체인은 64.8%가 이틀 안에 목표를 찍는다.
   → "체인은 목표가 너무 가까워서 이틀 만에 절반을 팔고 나오는 것 아닌가?"

[사전 고정 — 결과를 보기 전에 정한다]
  · 신호·진입가·손절가·트레일은 **한 글자도 바꾸지 않는다.** 목표가 계수 하나만 바꾼다.
  · 현행 A형 목표 : target = entry + (pre − entry) × 0.5   (pre = 급락 전 종가 = c[t−2])
    검정 계수 k  : 0.50(현행) · 0.75 · 1.00(완전 되돌림) · 1.25 · 1.50
  · 청산 방식 2개를 각각 본다:
      카드 = 전량 청산 · 40봉 상한 (현행)
      2단  = 목표시 50% 실현 + 잔여 트레일 −12% · 본전 하한 · 126봉 (2026-08-02 채택안)
  · 종목군 : 반도체 체인 / 기타 업종  (섹터불명은 생존편향 덩어리라 비교에서 제외, 참고로만 출력)
  · 국면   : 🟢실행 에서만 집계
  · 표본   : ① 정식 A만 (깨끗한 주검정)  ② A + S2-α (표본 2배, 재현 확인)
  · **월별로 쪼개지 않는다.** 현황판에서 월 칸은 계절 정보가 아니라 사건 정보임이 확인됐다.

[다중비교에 대하여]
  계수 5개 × 종목군 2개지만 이건 **순서 있는 연속 축**이다.
  "어느 칸이 제일 좋은가"가 아니라 "계수를 늘리면 단조롭게 좋아지는가/나빠지는가"를 본다.
  단조 추세는 우연히 나오기 훨씬 어렵다. 그래도 채택 전 사전등록·전진검증은 그대로 적용한다.

⚠️ 체인/기타 비교는 업종 데이터가 붙는 종목만 쓴다 = **살아남은 종목끼리의 비교**다.
   사라진 종목(섹터불명)은 카드 −1.32%p·40일 −9.0%p 나빴다. 이 편향은 보정되지 않는다.
"""
import os, sys, gc, json, argparse, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

HERE = "/home/claude/jq"; UP = "/mnt/user-data/uploads/진우퀀트"
NEAR = 0.08; MIN_BARS = 260
KS = [0.50, 0.75, 1.00, 1.25, 1.50]          # 목표 계수 (사전 고정)
CHAIN = ["반도체", "특수 목적용 기계", "전자부품", "측정, 시험", "광학",
         "그외 기타 전문, 과학", "통신 및 방송 장비", "일반 목적용 기계", "전지"]


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


def sim(entry, target, stop0, trail, h, l, c, t, n, H, split=1.0, rtrail=0.12):
    """split=1.0 → 카드(전량). split=0.5 → 2단(잔여 트레일·본전 하한)."""
    end = min(t + H, n - 1); peak = entry; stop = stop0
    for j in range(t + 1, end + 1):
        if l[j] <= stop:
            return stop / entry - 1, j - t, ("손절" if stop <= stop0 * 1.0001 else "트레일")
        if h[j] >= target:
            first = target / entry - 1
            if split >= 1.0: return first, j - t, "목표"
            rpeak = max(peak, h[j]); rstop = max(rpeak * (1 - rtrail), entry)
            for k_ in range(j + 1, end + 1):
                if l[k_] <= rstop:
                    return split * first + (1 - split) * (rstop / entry - 1), k_ - t, "2단트레일"
                rpeak = max(rpeak, h[k_]); rstop = max(rstop, max(rpeak * (1 - rtrail), entry))
            return split * first + (1 - split) * (c[end] / entry - 1), end - t, "2단만기"
        peak = max(peak, h[j]); stop = max(stop, peak * (1 - trail))
    return c[end] / entry - 1, end - t, "만기"


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--market", default="KOSPI")
    a = ap.parse_args()

    E = pd.read_csv(f"{HERE}/S2_이벤트_통합.csv", dtype={"code": str})
    E["code"] = E["code"].str.zfill(6)
    E["등급"] = np.where(E["신호"] == "A", "정식A",
                       np.where(E["미달"].fillna("").str.contains("2일누적"), "S2-βγ", "S2-α"))
    E = E[E["등급"].isin(["정식A", "S2-α"])]          # 주검정 대상만
    sec = {}
    for f in ("liquidity_sector.csv", "kosdaq_industry.csv"):
        d = pd.read_csv(os.path.join(UP, f), dtype=str)
        d.columns = [c.strip().lstrip("﻿") for c in d.columns]
        if {"code", "sector"}.issubset(d.columns):
            sec.update(dict(zip(d["code"].str.zfill(6), d["sector"].astype(str))))
    E["섹터"] = E["code"].map(sec)
    E["군"] = np.where(E["섹터"].isna(), "섹터불명",
                      np.where(E["섹터"].fillna("").apply(lambda x: any(k in x for k in CHAIN)),
                               "체인", "기타"))
    key = {(r["code"], r["date"]): r for _, r in E.iterrows()}
    targets = E.groupby("code")["date"].apply(set).to_dict()
    print(f"대상 {len(E):,}건 · 종목 {len(targets):,} "
          f"(정식A {int((E['등급']=='정식A').sum()):,} · S2-α {int((E['등급']=='S2-α').sum()):,})", flush=True)

    dt = {"code": str, "open": "float32", "high": "float32", "low": "float32",
          "close": "float32", "volume": "float32"}
    D = pd.read_csv(f"{HERE}/종목일봉_30년_{a.market}.csv", dtype=dt)
    D.columns = [x.strip().lstrip("﻿") for x in D.columns]
    D["code"] = D["code"].str.zfill(6)
    D = D[D["code"].isin(targets.keys())]
    rows = []; ns = 0
    for code, g in D.groupby("code", sort=False):
        want = targets.get(code)
        if not want: continue
        ns += 1
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
        L = np.vstack([w60, m10, ma240])
        pos = {d: i for i, d in enumerate(dts)}
        for d in want:
            t = pos.get(d)
            if t is None or t + 1 >= n or not (np.isfinite(c[t]) and c[t] > 0): continue
            r0 = key[(code, d)]
            cum2 = c[t] / c[t - 2] - 1
            lv = L[:, t]; dist = c[t] / lv - 1; fin = np.isfinite(dist)
            if not fin.any(): continue
            ki = int(np.nanargmin(np.where(fin, np.abs(dist), np.inf))); keyv = lv[ki]
            entry = c[t]; pre = c[t - 2]
            below = keyv if (np.isfinite(keyv) and keyv < entry) else l[t]
            stop0 = below * 0.95; trail = 0.12          # A계열 카드 — 고정
            rec = dict(date=d, code=code, 군=r0["군"], 등급=r0["등급"], 국면=r0["국면"],
                       연=int(d[:4]), 급락폭=cum2, 진입가=entry, 잔여봉=int(n - 1 - t))
            for k in KS:
                tg = entry + (pre - entry) * k
                rec[f"목표율_k{int(k*100)}"] = tg / entry - 1
                v1, b1, w1 = sim(entry, tg, stop0, trail, h, l, c, t, n, 40, 1.0)
                v2, b2, w2 = sim(entry, tg, stop0, trail, h, l, c, t, n, 126, 0.5)
                rec[f"카드_k{int(k*100)}"] = v1
                rec[f"카드how_k{int(k*100)}"] = w1
                rec[f"카드봉_k{int(k*100)}"] = b1
                rec[f"이단_k{int(k*100)}"] = v2
            rows.append(rec)
        if ns % 400 == 0: print(f"  {a.market} {ns}종목… 누적 {len(rows):,}", flush=True)
    del D; gc.collect()
    R = pd.DataFrame(rows)
    R.to_csv(f"{HERE}/목표계수_이벤트_{a.market}.csv", index=False, encoding="utf-8-sig")
    print(f"{a.market} 완료 — {len(R):,}건 저장")


if __name__ == "__main__":
    main()
