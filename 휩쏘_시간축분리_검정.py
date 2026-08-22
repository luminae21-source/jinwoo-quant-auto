# -*- coding: utf-8 -*-
"""휩쏘 · 스윙/단기 시간축 분리 30년 검정 (형 지정 과제 2, 2026-08-04)

사전 고정 설계 — 실행 전에 선언하고 이후 바꾸지 않는다.
  지평 3분할 : 단기 H=5,10,20 / 스윙 H=40(현행) / 중기 H=63,126
  정책 그리드 : 트레일 {없음, 8%, 12%, 20%} × 목표 {사용, 미사용}  = 8종
               (손절은 현행 초기손절 고정 — 그리드 폭발 방지)
  벤치마크    : 순수보유(규칙 없음) 같은 지평
  주질문 1    : 같은 규칙에서 지평만 바꾸면 기대값이 어떻게 변하나
  주질문 2    : 지평별로 최적 트레일이 갈리나 (단기=타이트 / 스윙=느슨 가설)
  다중비교    : 48셀 → Benjamini-Hochberg FDR 10% 보정. 보정 전 유의는 ○로만 표기.
  절단편향    : 지평별 창완결(t+H ≤ 마지막봉)만 사용.

엔진 : back_adjust / line_series 는 휩쏘_역사검정.py 원본과 동일 (일관성감사 대상)
출력 : 휩쏘_시간축_이벤트.csv · 휩쏘_시간축_결과.json
"""
import os, sys, gc, json, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass


# ── 경로 해석 (컨테이너 / 형 PC 어디서 돌려도 동작) ─────────────
def _resolve():
    here = os.path.dirname(os.path.abspath(__file__))
    cand = ["/home/claude/jq", "/mnt/user-data/uploads/진우퀀트", here]
    def find(name):
        for d in ([here] + cand):
            p = os.path.join(d, name)
            if os.path.exists(p): return p
        return os.path.join(here, name)
    return here, find
HERE, F = _resolve()
MIN_BARS = 260
NB = 4000; SEED = 11

HORIZONS = [5, 10, 20, 40, 63, 126]
HGROUP = {5: "단기", 10: "단기", 20: "단기", 40: "스윙", 63: "중기", 126: "중기"}
TRAILS = [0.00, 0.08, 0.12, 0.20]
USE_TGT = [True, False]


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


def run1(entry, target, stop0, trail, use_tgt, h, l, c, t, n, H):
    """단일 정책 실행 → (수익률, 청산봉수, 청산사유)"""
    end = min(t + H, n - 1); peak = entry; stop = stop0
    for j in range(t + 1, end + 1):
        if l[j] <= stop:
            return stop / entry - 1, j - t, "손절"
        if use_tgt and h[j] >= target:
            return target / entry - 1, j - t, "목표"
        peak = max(peak, h[j])
        if trail > 0: stop = max(stop, peak * (1 - trail))
    return c[end] / entry - 1, end - t, "만기"


def main():
    L = pd.read_csv(F("휩쏘_역사원장.csv"), dtype={"code": str})
    L.columns = [x.strip().lstrip("﻿") for x in L.columns]
    L["code"] = L["code"].str.zfill(6); L["출발일"] = L["출발일"].astype(str)
    typmap = dict(zip(zip(L["code"], L["출발일"]), L["유형"]))
    targets = L.groupby("code")["출발일"].apply(set).to_dict()

    dt = {"code": str, "open": "float32", "high": "float32", "low": "float32",
          "close": "float32", "volume": "float32"}
    rows = []
    for mk in ("KOSPI", "KOSDAQ"):
        src = F(f"bars_{mk}.csv.gz")
        if not os.path.exists(src):
            src = F(f"_stagetmp3/bars_{mk}.csv.gz")
        if not os.path.exists(src):
            src = F(f"종목일봉_30년_{mk}.csv")     # 형 PC 원본 경로
        print(f"  [{mk}] 로드: {src}", flush=True)
        D = pd.read_csv(src, dtype=dt)
        D.columns = [x.strip().lstrip("﻿") for x in D.columns]
        D["code"] = D["code"].str.zfill(6)
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
                if t is None or t + 1 >= n or t < 2: continue
                if not (np.isfinite(c[t]) and c[t] > 0): continue
                cum2 = c[t] / c[t - 2] - 1
                lv = lines[:, t]; dist = c[t] / lv - 1; fin = np.isfinite(dist)
                if not fin.any(): continue
                ki = int(np.nanargmin(np.where(fin, np.abs(dist), np.inf)))
                keyv = lv[ki]
                typ = typmap[(code, d)]; entry = c[t]
                if typ == "A":
                    pre = c[t] / (1 + cum2); target = entry + (pre - entry) * 0.5
                    below = keyv if (np.isfinite(keyv) and keyv < entry) else l[t]
                    stop0 = below * 0.95; cur_trail = 0.12
                else:
                    target = float(np.max(h[max(0, t - 59):t + 1]))
                    below = keyv if (np.isfinite(keyv) and keyv < entry) else l[t]
                    stop0 = below * 0.97; cur_trail = 0.15
                rec = dict(출발일=d, code=code, 유형=typ, 시장=mk)
                for H in HORIZONS:
                    rec[f"창완결_{H}"] = bool(t + H <= n - 1)
                    rec[f"보유_{H}"] = c[min(t + H, n - 1)] / entry - 1
                    r, b, w = run1(entry, target, stop0, cur_trail, True, h, l, c, t, n, H)
                    rec[f"현행_{H}"] = r; rec[f"현행봉_{H}"] = b; rec[f"현행사유_{H}"] = w
                    for tr in TRAILS:
                        for ug in USE_TGT:
                            key = f"T{int(tr*100)}{'G' if ug else 'N'}_{H}"
                            r, b, w = run1(entry, target, stop0, tr, ug, h, l, c, t, n, H)
                            rec[key] = r; rec[key + "_봉"] = b; rec[key + "_사유"] = w
                rows.append(rec)
        del D; gc.collect()
        print(f"{mk} 누적 {len(rows)}", flush=True)

    R = pd.DataFrame(rows)
    M = L.merge(R, on=["출발일", "code"], how="inner")
    M["연"] = M["출발일"].str[:4].astype(int)
    M.to_csv(os.path.join(HERE, "휩쏘_시간축_이벤트.csv"), index=False, encoding="utf-8-sig")
    print(f"\n[표본] 원장 {len(L)}건 → 재현 {len(M)}건")
    print(M["국면"].value_counts().to_dict())
    return M


if __name__ == "__main__":
    main()
