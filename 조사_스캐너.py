# -*- coding: utf-8 -*-
r"""조사_스캐너.py — 조사 트랙이 받을 스캐너 (2026-08-02 사전등록)

[왜] 휩쏘 탐색기는 '2일째 정석 자리'만 본다. 그 앞뒤로 두 개의 사각지대가 있다.
  S1 예비경보(1일째) : 오늘 급락1 + 장기선 근접 → 내일이 2일째 후보다. 하루 미리 준비한다.
  S2 근접 미달형     : 오늘이 2일째인데 A 조건을 1~2개 '아깝게' 미달. 30년 등급 역설
                       (C급 근접 +2.8% > A급 지지 +1.8%)이 이 방향을 지지한다.

[사전등록 파라미터 — 이 값은 고정한다. 사후에 고치면 전진검증이 무효다]
  S1 : 급락1 ≤ −3% · 장기선 근접 ±8% · 고점매도신호 0
       A계열 = MA240이격 ≤ +8% · 5년고점比 ≤ −30% · 시총 ≥ 3,000억
       B계열 = MA240이격 ≥ +10% · 시총 ≥ 5조
  S2 : 급락1 ≤ −3% · 급락2 ≤ +2% · 근접 ±8% · 고점매도신호 0
       2일누적 ≤ −10%(원 −12%) · MA240이격 ≤ +12%(원 +8%)
       5년고점比 ≤ −25%(원 −30%) · 시총 ≥ 2,000억(원 3,000억)
       + 정식 A/B 신호가 아닐 것 (미달 항목 1개 이상)

[S2 등급 — 2026-08-02 30년 검정 결과로 확정. 미달 '항목'에 따라 완전히 갈린다]
  S2-α : MA240 / 5년고점 / 시총 중 하나만 단독 미달  → 카드 +1.9~+4.1% (전부 CI>0)
         특히 MA240 단독완화는 +4.05%로 정식 A(+2.40%)보다 좋다
  S2-β : 2일누적만 단독 미달                          → 카드 +0.81% (CI>0이나 약함) · 관찰만
  S2-γ : 2일누적을 낀 조합                            → 카드 +0.1% CI 0 포함 · 등록 제외

[출력] 조사_스캐너_YYYYMMDD.csv · 콘솔표 · --emit(오늘조사.py 로 넘길 코드 문자열)
[사용] py 조사_스캐너.py                     # 최신 영업일
       py 조사_스캐너.py --date 20260731
       py 조사_스캐너.py --emit S1            # 코드만 출력 → 오늘조사.py --codes 에 붙여넣기
       py 조사_스캐너.py --emit S2A           # S2-α(실전후보)만
       py 조사_스캐너.py --emit A2            # A′ 사전등록 대상만
⚠️ 사전등록 관찰용. 검정 전 신호다 — 매매 추천이 아니다.
"""
import os, sys, gc, argparse, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

HERE = os.path.dirname(os.path.abspath(__file__)) or "."
CAND = [HERE, "/home/claude/jq", "/mnt/user-data/uploads/진우퀀트", os.path.join(HERE, "data")]
NEAR = 0.08
MIN_BARS = 260

# ── 사전등록 파라미터 (고정)
S1_D1, S1_AUP, S1_DD5, S1_MCAP = -0.03, 0.08, -0.30, 3000e8
S1_BUP, S1_BMCAP = 0.10, 50000e8
S2_D1, S2_D2MAX, S2_CUM2, S2_AUP, S2_DD5, S2_MCAP = -0.03, 0.02, -0.10, 0.12, -0.25, 2000e8


def find(fn):
    for d in CAND:
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    return None


def back_adjust(o, h, l, c, dts):
    n = len(c); adj = np.ones(n); cum = 1.0
    for i in range(n - 1, 0, -1):
        p, q = c[i - 1], c[i]
        if p > 0 and q > 0:
            r = q / p
            lim = (0.30 if dts[i] >= "2015-06-15" else 0.15) + 0.03
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="YYYYMMDD (기본 최신)")
    ap.add_argument("--emit", default=None, choices=["S1", "S2", "S2A", "A2", "ALL"],
                    help="코드 문자열만 출력 (오늘조사.py --codes 용)")
    ap.add_argument("--top", type=int, default=40)
    a = ap.parse_args()
    asof = f"{a.date[:4]}-{a.date[4:6]}-{a.date[6:]}" if a.date else None
    quiet = a.emit is not None

    names = {}
    p = find("종목명_맵.csv")
    if p:
        nm = pd.read_csv(p, dtype=str); nm.columns = [x.strip().lstrip("﻿") for x in nm.columns]
        names = dict(zip(nm["code"].str.zfill(6), nm["name"]))
    MC = {}
    p = find("종목시총_30년.csv")
    if p:
        mc = pd.read_csv(p, dtype={"code": str}); mc.columns = [x.strip().lstrip("﻿") for x in mc.columns]
        mc["code"] = mc["code"].str.zfill(6); mc["date"] = mc["date"].astype(str)
        mc["mcap"] = pd.to_numeric(mc["mcap"], errors="coerce")
        mc = mc.dropna(subset=["mcap"]).sort_values(["code", "date"])
        MC = {c: (d["date"].values, d["mcap"].values) for c, d in mc.groupby("code")}

    dt = {"code": str, "open": "float32", "high": "float32", "low": "float32",
          "close": "float32", "volume": "float32"}
    rows = []
    for mk in ("KOSPI", "KOSDAQ"):
        fp = find(f"종목일봉_30년_{mk}.csv")
        if not fp: continue
        if not quiet: print(f"{mk} 로딩…", flush=True)
        D = pd.read_csv(fp, dtype=dt)
        D.columns = [x.strip().lstrip("﻿") for x in D.columns]
        D["code"] = D["code"].str.zfill(6)
        if asof: D = D[D["date"] <= asof]
        LASTD = D["date"].max()          # 그 시장의 실제 마지막 거래일
        for code, g in D.groupby("code", sort=False):
            g = g.sort_values("date").reset_index(drop=True)
            g = g[~((g["open"] == 0) & (g["volume"] == 0))].reset_index(drop=True)
            if len(g) < MIN_BARS: continue
            dts = g["date"].values.astype(str)
            o = g["open"].values.astype(float); h = g["high"].values.astype(float)
            l = g["low"].values.astype(float); c = g["close"].values.astype(float)
            v = g["volume"].values.astype(float)
            rawc = c.copy()
            o, h, l, c = back_adjust(o, h, l, c, dts)
            t = len(c) - 1
            # ⚠️ 상장폐지·거래정지 종목은 마지막 봉이 과거다. '오늘'로 착각하면 안 된다.
            if dts[t] != LASTD: continue
            if rawc[t] < 1000: continue
            cs = pd.Series(c)
            ma240 = cs.rolling(240, min_periods=240).mean().values
            if not np.isfinite(ma240[t]): continue
            w60, m10 = line_series(g["date"].values, c)
            lines = np.array([w60[t], m10[t], ma240[t]]); lname = ["주60주", "월10", "일240"]
            dist = c[t] / lines - 1; fin = np.isfinite(dist)
            if not fin.any(): continue
            nearby = bool(np.any(np.abs(dist[fin]) <= NEAR))
            ki = int(np.nanargmin(np.where(fin, np.abs(dist), np.inf)))
            hi5 = pd.Series(h).rolling(1250, min_periods=250).max().values
            top5 = c[t] / hi5[t] - 1
            hi252 = pd.Series(h).rolling(252, min_periods=120).max().values
            volma = pd.Series(v).rolling(60, min_periods=40).mean().values
            body = c / np.where(o > 0, o, np.nan) - 1
            wick = (h - np.maximum(o, c)) / np.where(h > 0, h, np.nan)
            sig = ((c >= hi252 * 0.90) & (v >= volma * 2.0) & (wick >= 0.03) & (body <= 0.02)).astype(float)
            sell10 = float(pd.Series(sig).rolling(10, min_periods=1).sum().values[t])
            d1 = c[t] / c[t - 1] - 1
            d0 = c[t - 1] / c[t - 2] - 1
            cum2 = c[t] / c[t - 2] - 1
            g240 = c[t] / ma240[t] - 1
            arr = MC.get(code)
            if arr is None: continue
            k = np.searchsorted(arr[0], dts[t], side="right") - 1
            mcv = float(arr[1][k]) if k >= 0 else np.nan
            if not np.isfinite(mcv): continue

            base = dict(code=code, name=names.get(code, code), 시장=mk, 일자=dts[t],
                        종가=rawc[t], 급락1=d1, 전일=d0, **{"2일누적": cum2},
                        이격MA240=g240, 고점5년比=top5, 핵심선=lname[ki],
                        선이격=dist[ki], 시총=mcv, 매도신호=sell10)

            # 정식 A/B (탐색기와 동일) — S2에서 제외하기 위해
            isA = (d0 <= -0.03 and d1 <= 0.02 and cum2 <= -0.12 and nearby
                   and top5 <= -0.30 and sell10 == 0 and g240 <= 0.08 and mcv >= 3000e8)
            isB = (d0 <= -0.03 and cum2 <= -0.03 and nearby and sell10 == 0
                   and g240 >= 0.10 and mcv >= 50000e8)

            # ── S1 예비경보 (오늘이 급락1일째)
            if d1 <= S1_D1 and nearby and sell10 == 0 and not (isA or isB):
                okA = (g240 <= S1_AUP and top5 <= S1_DD5 and mcv >= S1_MCAP)
                okB = (g240 >= S1_BUP and mcv >= S1_BMCAP)
                if okA or okB:
                    need = ((1 - 0.12) / (1 + d1) - 1) if okA else ((1 - 0.03) / (1 + d1) - 1)
                    rows.append(base | dict(스캐너="S1", 계열=("A계열" if okA else "B계열"),
                                            내일필요낙폭=need, 미달항목=""))

            # ── A′ 사전등록 (2026-08-02 휩쏘_MA240_사전등록.md) — MA240 이격만 +8~+12%
            #    다른 조건은 정식 A와 완전히 동일. 한 글자도 바꾸지 않는다.
            if (d0 <= -0.03 and d1 <= 0.02 and cum2 <= -0.12 and nearby and sell10 == 0
                    and top5 <= -0.30 and mcv >= 3000e8
                    and 0.08 < g240 <= 0.12 and not (isA or isB)):
                rows.append(base | dict(스캐너="A′", 계열="사전등록",
                                        내일필요낙폭=np.nan,
                                        미달항목=f"MA240이격 +{g240*100:.1f}% (정식A 상한 +8% 초과, A′ 범위)"))

            # ── S2 근접 미달형 (오늘이 2일째인데 아깝게 미달)
            if (d0 <= S2_D1 and d1 <= S2_D2MAX and nearby and sell10 == 0
                    and cum2 <= S2_CUM2 and g240 <= S2_AUP and top5 <= S2_DD5
                    and mcv >= S2_MCAP and not (isA or isB)):
                miss = []
                if cum2 > -0.12: miss.append(f"2일누적 {cum2*100:.1f}%(<−12 미달)")
                if g240 > 0.08: miss.append(f"MA240이격 +{g240*100:.1f}%(≤+8 초과)")
                if top5 > -0.30: miss.append(f"5년고점比 {top5*100:.1f}%(≤−30 미달)")
                if mcv < 3000e8: miss.append(f"시총 {mcv/1e8:,.0f}억(≥3000 미달)")
                # 30년 검정 결과에 따른 등급 (휩쏘_S2_판정문.md)
                keys = set()
                if cum2 > -0.12: keys.add("2일누적")
                if g240 > 0.08: keys.add("MA240")
                if top5 > -0.30: keys.add("5년고점")
                if mcv < 3000e8: keys.add("시총")
                if "2일누적" in keys:
                    grade = "S2-β" if len(keys) == 1 else "S2-γ"
                else:
                    grade = "S2-α"
                rows.append(base | dict(스캐너="S2", 계열=grade,
                                        내일필요낙폭=np.nan, 미달항목=" · ".join(miss) or "기타"))
        del D; gc.collect()

    R = pd.DataFrame(rows)
    day = (asof or (R["일자"].max() if len(R) else "")).replace("-", "")
    if a.emit:
        if a.emit == "ALL": sel = R
        elif a.emit == "S2A": sel = R[(R["스캐너"] == "S2") & (R["계열"] == "S2-α")]
        elif a.emit == "A2": sel = R[R["스캐너"] == "A′"]
        else: sel = R[R["스캐너"] == a.emit]
        print(",".join(sel["code"].tolist()))
        return
    out = os.path.join(HERE, f"조사_스캐너_{day}.csv")
    R.to_csv(out, index=False, encoding="utf-8-sig")

    try:
        sys.path.insert(0, HERE)
        import 시장국면 as 국면
        line, _ = 국면.banner(asof)
        print("=" * 112); print(line)
    except Exception:
        pass
    print("=" * 112)
    print(f" 조사 스캐너 [{day}] — S1 예비경보 {int((R['스캐너']=='S1').sum())}종 · "
          f"S2 근접미달 {int((R['스캐너']=='S2').sum())}종 · "
          f"A′ 사전등록 {int((R['스캐너']=='A′').sum())}종   (사전등록 2026-08-02)")
    print("=" * 112)

    for tag, title, note in (
        ("A′", "A′ · MA240 이격 완화 사전등록 — 정식 A와 모든 조건 동일, 이격만 +8~+12%",
         "휩쏘_MA240_사전등록.md · 40건 누적까지 중간판정 금지. 카드+2단 성과 둘 다 기록"),
        ("S1", "S1 · 휩쏘 예비경보 — 오늘 급락1일째. 내일 종가가 2일째 판단 시점",
         "‘내일필요낙폭’ = 내일 그만큼 더 빠지면 정식 A(2일누적 −12%) 성립"),
        ("S2", "S2 · 근접 미달형 — 오늘이 2일째인데 A 조건을 아깝게 미달",
         "30년 검정 완료: α=실전후보(+1.9~+4.1%) · β=관찰만(+0.8%) · γ=등록제외(무의)")):
        S = R[R["스캐너"] == tag].sort_values("선이격", key=lambda s: s.abs()).head(a.top)
        print(f"\n▣ {title}\n   {note}")
        if S.empty:
            print("   (해당 없음)"); continue
        if tag == "A′":
            print(f"   {'종목':<16}{'시장':<7}{'종가':>10}{'2일누적':>9}{'MA240이격':>10}{'5년比':>8}"
                  f"{'핵심선':>8}{'시총(억)':>10}")
            for _, x in S.iterrows():
                print(f"   {str(x['name'])[:15]:<16}{x['시장']:<7}{x['종가']:>10,.0f}"
                      f"{x['2일누적']*100:>+8.1f}%{x['이격MA240']*100:>+9.1f}%{x['고점5년比']*100:>+7.1f}%"
                      f"{x['핵심선']:>8}{x['시총']/1e8:>10,.0f}")
            print("   → 조사 원장에 '사전등록' 태그로 기록. 실전 진입 여부는 형 판단(검정 전 신호).")
        elif tag == "S1":
            print(f"   {'종목':<16}{'시장':<7}{'종가':>10}{'급락1':>8}{'MA240':>8}{'5년比':>8}"
                  f"{'핵심선':>8}{'선이격':>8}{'시총(억)':>10}{'계열':>7}{'내일필요':>9}")
            for _, x in S.iterrows():
                print(f"   {str(x['name'])[:15]:<16}{x['시장']:<7}{x['종가']:>10,.0f}{x['급락1']*100:>+7.1f}%"
                      f"{x['이격MA240']*100:>+7.1f}%{x['고점5년比']*100:>+7.1f}%{x['핵심선']:>8}"
                      f"{x['선이격']*100:>+7.1f}%{x['시총']/1e8:>10,.0f}{x['계열']:>7}{x['내일필요낙폭']*100:>+8.1f}%")
        else:
            S = S.sort_values("계열")
            print(f"   {'등급':<7}{'종목':<16}{'시장':<7}{'종가':>10}{'2일누적':>9}{'핵심선':>8}{'선이격':>8}{'시총(억)':>10}  미달항목")
            for _, x in S.iterrows():
                print(f"   {x['계열']:<7}{str(x['name'])[:15]:<16}{x['시장']:<7}{x['종가']:>10,.0f}{x['2일누적']*100:>+8.1f}%"
                      f"{x['핵심선']:>8}{x['선이격']*100:>+7.1f}%{x['시총']/1e8:>10,.0f}  {x['미달항목']}")
            n_a = int((S["계열"] == "S2-α").sum())
            print(f"   → 실전후보(α) {n_a}종 · 관찰(β) {int((S['계열']=='S2-β').sum())}종 · 제외(γ) {int((S['계열']=='S2-γ').sum())}종")

    print(f"\n저장: {out}")
    print("조사 원장 등록:  py 오늘조사.py --codes \"$(py 조사_스캐너.py --emit S2)\"")
    print("⚠️ 사전등록 관찰용 — 검정 전 신호다. 국면이 🔴관찰만이면 등록만 하고 사지 않는다.")


if __name__ == "__main__":
    main()
