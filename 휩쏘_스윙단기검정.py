# -*- coding: utf-8 -*-
r"""휩쏘_스윙단기검정.py — §10-B 스윙/단기매매 분리 (사전등록 2026-08-21 준수)

질문: 같은 신호(🟢실행×정식A)에서 "짧게 먹고 나오는 규칙"이 표준 규칙과
      다른 종류의 성과를 내는가 — 주지표는 수익률/보유일(자본 회전 효율).

[비교 — 2개 고정, 그리드 금지]
  표준: 목표 절반되돌림→50%실현, 잔여 트레일 12%+본전플로어, 만기126봉  (=P1_T12_H126_be)
  단기: 목표 1/3되돌림→전량실현,  트레일 8%,               만기 20봉
  공통: 손절 핵심선×0.95 · 비용 왕복 0.4% · 동시터치 손절우선

[채택 기준 — 사전 고정]
  단기형이 수익/보유일 부트 95% CI 하한>0 우위 AND 건당 수익 열위 ≤1.0%p
  → "단기 트랙" 신설 후보(전진검증 별도). 미달 → 기각·표준 단일 유지.

[검증] 표준 재현치를 기존 휩쏘_2단청산_이벤트.csv의 P1_T12_H126_be와 건별 대조.
⚠️ 생존편향·위기해 클러스터 — Δ는 시사이지 확정 아님.
"""
import os, sys, gc, json, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

HERE = os.path.dirname(os.path.abspath(__file__))
# ⚠️ 순서 중요: 컨테이너 작업폴더(wk)에는 주간갱신용 '최근 2년 패널'이 30년 파일과
#    같은 이름으로 존재할 수 있다 → 전체 데이터 폴더(jq)를 먼저 찾는다.
#    (2026-08-21 실제 사고: wk의 24MB 패널을 물고 2025~26년 510건만 시뮬됨)
CAND = ["/home/claude/jq", HERE, "/mnt/user-data/uploads/진우퀀트"]
def find(fn):
    for d in CAND:
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    sys.exit(f"{fn} 없음 — 데이터 폴더 확인")

OUT = HERE
MIN_BARS = 260
COST = 0.004          # 왕복 (편도 0.2%)
BOOT = 2000
SEED = 42


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


def simulate(entry, target, stop0, trail, h, l, c, t, n, horizon,
             split=0.0, runner_trail=None, runner_stop_mode="tr"):
    """휩쏘_2단청산검정.py::simulate 와 동일 로직 + 보유봉 반환."""
    end = min(t + horizon, n - 1)
    peak = entry; stop = stop0
    rt = runner_trail if runner_trail is not None else trail
    for j in range(t + 1, end + 1):
        if l[j] <= stop:
            r = stop / entry - 1
            return r, j - t, ("손절" if stop <= stop0 * 1.0001 else "트레일")
        if target is not None and h[j] >= target:
            first = target / entry - 1
            if split <= 0:
                return first, j - t, "목표전량"
            rpeak = max(peak, h[j]); rstop = rpeak * (1 - rt)
            if runner_stop_mode == "be": rstop = max(rstop, entry)
            for k in range(j + 1, end + 1):
                if l[k] <= rstop:
                    second = rstop / entry - 1
                    return split * first + (1 - split) * second, k - t, "2단트레일"
                rpeak = max(rpeak, h[k]); ns = rpeak * (1 - rt)
                if runner_stop_mode == "be": ns = max(ns, entry)
                rstop = max(rstop, ns)
            second = c[end] / entry - 1
            return split * first + (1 - split) * second, end - t, "2단만기"
        peak = max(peak, h[j])
        stop = max(stop, peak * (1 - trail))
    return c[end] / entry - 1, end - t, "만기"


def main():
    L = pd.read_csv(find("휩쏘_역사원장.csv"), dtype={"code": str})
    L.columns = [x.strip().lstrip("﻿") for x in L.columns]
    L["code"] = L["code"].str.zfill(6)
    L["출발일"] = L["출발일"].astype(str)
    A = L[L["유형"] == "A"].copy()
    targets = A.groupby("code")["출발일"].apply(set).to_dict()
    print(f"원장 {len(L)}건 · 정식A {len(A)}건 · 종목 {len(targets)}", flush=True)

    dt = {"code": str, "open": "float32", "high": "float32", "low": "float32",
          "close": "float32", "volume": "float32"}
    rows = []
    for mk in ("KOSPI", "KOSDAQ"):
        print(f"{mk} 로딩…", flush=True)
        D = pd.read_csv(find(f"종목일봉_30년_{mk}.csv"), dtype=dt)
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
            ma240 = pd.Series(c).rolling(240, min_periods=240).mean().values
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
                entry = c[t]
                pre = c[t] / (1 + cum2)                    # 급락 전 가격
                below = keyline_v if (np.isfinite(keyline_v) and keyline_v < entry) else l[t]
                stop0 = below * 0.95
                tgt_half = entry + (pre - entry) * 0.5     # 표준: 절반 되돌림
                tgt_third = entry + (pre - entry) * (1/3)  # 단기: 1/3 되돌림

                r_s, b_s, how_s = simulate(entry, tgt_half, stop0, 0.12, h, l, c, t, n, 126,
                                           split=0.5, runner_trail=0.12, runner_stop_mode="be")
                r_q, b_q, how_q = simulate(entry, tgt_third, stop0, 0.08, h, l, c, t, n, 20,
                                           split=0.0)
                rows.append(dict(출발일=d, code=code, 유형="A",
                                 표준수익=r_s, 표준봉=b_s, 표준how=how_s,
                                 단기수익=r_q, 단기봉=b_q, 단기how=how_q,
                                 창완결126=(t + 126 <= n - 1), 창완결20=(t + 20 <= n - 1)))
        del D; gc.collect()
        print(f"  {mk} 누적 {len(rows)}건", flush=True)

    R = pd.DataFrame(rows)
    key = ["출발일", "code", "유형"]
    M = A.merge(R, on=key, how="inner")
    M.to_csv(os.path.join(OUT, "휩쏘_스윙단기_이벤트.csv"), index=False, encoding="utf-8-sig")
    print(f"\n시뮬 완료 {len(M)}건 → 휩쏘_스윙단기_이벤트.csv", flush=True)

    # ── 검증: 표준 재현 ↔ 기존 P1_T12_H126_be ──────────────────────
    try:
        E = pd.read_csv(find("휩쏘_2단청산_이벤트.csv"), dtype={"code": str})
        E.columns = [x.strip().lstrip("﻿") for x in E.columns]
        E["code"] = E["code"].str.zfill(6); E["출발일"] = E["출발일"].astype(str)
        V = M.merge(E[key + ["P1_T12_H126_be"]], on=key, how="inner").dropna(
            subset=["P1_T12_H126_be", "표준수익"])
        diff = (V["표준수익"] - V["P1_T12_H126_be"])
        print(f"[검증] 대조 {len(V)}건 · 평균차 {diff.mean()*100:+.3f}%p · "
              f"|차|>0.5%p 비율 {(diff.abs()>0.005).mean()*100:.1f}%", flush=True)
    except SystemExit:
        print("[검증] 기존 이벤트 파일 없음 — 생략", flush=True)

    # ── 판정 (PRIMARY = 실행 × A) ───────────────────────────────────
    rng = np.random.default_rng(SEED)

    def report(sub, label):
        s_net = sub["표준수익"].values - COST
        q_net = sub["단기수익"].values - COST
        s_d = s_net / np.maximum(sub["표준봉"].values, 1)
        q_d = q_net / np.maximum(sub["단기봉"].values, 1)
        n = len(sub)
        idx = rng.integers(0, n, (BOOT, n))
        d_day = (q_d[idx] - s_d[idx]).mean(axis=1)
        d_ret = (q_net[idx] - s_net[idx]).mean(axis=1)
        ci_day = np.percentile(d_day, [2.5, 97.5])
        ci_ret = np.percentile(d_ret, [2.5, 97.5])
        out = dict(
            n=n,
            표준=dict(평균=float(s_net.mean()*100), 승률=float((s_net>0).mean()*100),
                     보유일=float(sub["표준봉"].mean()), 일당=float(s_d.mean()*100),
                     최악5pct=float(np.percentile(s_net, 5)*100)),
            단기=dict(평균=float(q_net.mean()*100), 승률=float((q_net>0).mean()*100),
                     보유일=float(sub["단기봉"].mean()), 일당=float(q_d.mean()*100),
                     최악5pct=float(np.percentile(q_net, 5)*100)),
            Δ일당=dict(값=float((q_d-s_d).mean()*100), CI=[float(ci_day[0]*100), float(ci_day[1]*100)]),
            Δ건당=dict(값=float((q_net-s_net).mean()*100), CI=[float(ci_ret[0]*100), float(ci_ret[1]*100)]))
        print(f"\n── {label} (n={n}) ──", flush=True)
        print(f"  표준: 건당 {out['표준']['평균']:+.2f}% · 승률 {out['표준']['승률']:.1f}% · "
              f"보유 {out['표준']['보유일']:.1f}일 · 일당 {out['표준']['일당']:+.4f}%/일", flush=True)
        print(f"  단기: 건당 {out['단기']['평균']:+.2f}% · 승률 {out['단기']['승률']:.1f}% · "
              f"보유 {out['단기']['보유일']:.1f}일 · 일당 {out['단기']['일당']:+.4f}%/일", flush=True)
        print(f"  Δ일당(단기−표준) {out['Δ일당']['값']:+.4f}%p/일 · CI [{out['Δ일당']['CI'][0]:+.4f}, {out['Δ일당']['CI'][1]:+.4f}]", flush=True)
        print(f"  Δ건당(단기−표준) {out['Δ건당']['값']:+.2f}%p   · CI [{out['Δ건당']['CI'][0]:+.2f}, {out['Δ건당']['CI'][1]:+.2f}]", flush=True)
        return out

    res = {}
    P = M[M["국면"] == "실행"].copy()
    res["PRIMARY_실행xA"] = report(P, "PRIMARY 🟢실행 × 정식A")

    # H2: 낙폭 2분할 (사전 지정 — 시사로만)
    res["H2_얕은_-12~-18"] = report(P[P["2일누적"] > -18], "H2 얕은 낙폭 (−12~−18%)")
    res["H2_깊은_≤-18"] = report(P[P["2일누적"] <= -18], "H2 깊은 낙폭 (≤−18%)")
    # 참고: 비실행 국면 (시사)
    res["참고_비실행"] = report(M[M["국면"] != "실행"], "참고 · 비실행 국면")

    # ── 판정문 초안 로직 (사전등록 §4) ──────────────────────────────
    pr = res["PRIMARY_실행xA"]
    win_day = pr["Δ일당"]["CI"][0] > 0
    ok_ret = pr["Δ건당"]["값"] >= -1.0
    verdict = "채택 후보 (전진검증 등록 필요)" if (win_day and ok_ret) else "기각 — 표준 단일 유지"
    res["판정"] = dict(일당CI하한초과=bool(win_day), 건당열위1p이내=bool(ok_ret), 결론=verdict)
    print(f"\n══ 판정 ══  {verdict}", flush=True)
    print(f"   ① 일당 CI 하한 > 0 : {'충족' if win_day else '미충족'}", flush=True)
    print(f"   ② 건당 열위 ≤1.0%p : {'충족' if ok_ret else '미충족'} (Δ {pr['Δ건당']['값']:+.2f}%p)", flush=True)

    with open(os.path.join(OUT, "휩쏘_스윙단기_결과.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("\n저장: 휩쏘_스윙단기_이벤트.csv · 휩쏘_스윙단기_결과.json", flush=True)


if __name__ == "__main__":
    main()
