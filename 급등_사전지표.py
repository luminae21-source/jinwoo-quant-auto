# -*- coding: utf-8 -*-
r"""급등_사전지표.py — '존'에 있던 날의 지표 → 다음날 상승 등급 (2026-08-01 신설)

[형의 정의] 마틴게일 존 = 2026-07-29 · 07-30. 그 바닥 이틀.
[하는 일]   그 이틀의 **모든 지표**를 전 종목에 대해 뽑고,
            7/31 상승률 등급(상한가 / 25%↑ / 20%↑ / 15%↑)별로 갈라서 비교한다.

[왜 등급으로 나누나]
  상한가만 보면 "상한가는 이렇게 생겼다"밖에 안 나온다.
  등급을 계단으로 놓으면 **지표가 단조롭게 변하는지**를 볼 수 있다 —
  그게 진짜 관계고, 계단이 안 나오면 우연이다.

[⚠️ 반드시 기저율과 같이 본다]
  모든 지표를 **전체 시장 중앙값과 나란히** 찍는다.
  "급등주의 90%가 X였다"는 전체의 88%가 X면 아무 의미가 없다. (7/31에 실제로 그랬다)

[지표 목록 — 존 날짜 기준, 미래 정보 없음]
  추세   MA5/20/60/120/240 이격 · MA60-MA240 간격 · 정배열/역배열 · MA240 기울기
  위치   5년고점比 · 52주고점比 · 52주저점比 · 볼린저 %B(20,2)
  모멘텀 1/3/5/20일 등락률 · RSI(14) · 연속 하락일수
  변동성 ATR% · 20일 변동성
  거래   20일 평균 거래대금 · 당일 거래량/20일평균 · 거래대금 급증 배수
  재무   PER · PBR · EPS · BPS · 배당% · 시가총액
  기타   섹터 · 고점대량매도 신호(sig10)

사용: py 급등_사전지표.py
      py 급등_사전지표.py --date 20260731 --zone 20260729,20260730
      py 급등_사전지표.py --date 20260731 --tiers 29,25,20,15
출력: 급등_사전지표_YYYYMMDD.csv   (전 종목 × 전 지표 × 등급)
     급등_사전지표_요약_YYYYMMDD.csv (등급별 중앙값 표)
⚠️ 사후 관찰. 하루치로 규칙을 만들지 않는다. 매수 신호 아님.
"""
import os, sys, argparse, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

PX_FLOOR = 1000
NEAR_HIGH, VOL_MULT, WICK_MIN, BODY_SMALL = 0.90, 2.0, 0.03, 0.02


def dw(t, n, right=False):
    import unicodedata
    t = str(t)
    g = lambda s: sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)
    while g(t) > n: t = t[:-1]
    pad = " " * (n - g(t))
    return pad + t if right else t + pad


def _find(fn):
    for d in (HERE, os.path.join(HERE, "데이터수리"), os.path.dirname(HERE), os.getcwd()):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    return None


def load_daily():
    fr = []
    for m in ("KOSPI", "KOSDAQ"):
        p = _find(f"_일봉OHLCV_{m}_adj.csv")
        if p:
            d = pd.read_csv(p, dtype={"code": str}); d["mkt"] = m; fr.append(d)
    if not fr: sys.exit("❌ _일봉OHLCV_*_adj.csv 없음")
    D = pd.concat(fr, ignore_index=True); D["code"] = D["code"].str.zfill(6)
    amax = D["date"].max(); add = []
    for m in ("KOSPI", "KOSDAQ"):
        rp = _find(f"종목일봉_30년_{m}.csv")
        if not rp: continue
        try: raw = pd.read_csv(rp, dtype={"code": str})
        except Exception: continue
        if not {"date","code","open","high","low","close","volume"}.issubset(raw.columns): continue
        raw = raw[raw["date"] > amax]
        if len(raw):
            raw = raw.copy(); raw["code"] = raw["code"].astype(str).str.zfill(6); raw["mkt"] = m
            add.append(raw[["code","date","open","high","low","close","volume","mkt"]])
    if add: D = pd.concat([D] + add, ignore_index=True)
    return D.drop_duplicates(["code","date"], keep="last").sort_values(["code","date"]).reset_index(drop=True)


def rsi(cl, n=14):
    d = np.diff(cl)
    if len(d) < n: return np.nan
    up = np.where(d > 0, d, 0.0); dn = np.where(d < 0, -d, 0.0)
    au = up[-n:].mean(); ad = dn[-n:].mean()
    if ad == 0: return 100.0
    return 100 - 100 / (1 + au / ad)


def feats(g, upto):
    """upto(포함)까지의 데이터만 써서 지표를 만든다. 미래 정보 차단."""
    g = g[g["date"] <= upto]
    if len(g) < 260: return None
    cl = g["close"].values.astype(float); hi = g["high"].values.astype(float)
    lo = g["low"].values.astype(float);  op = g["open"].values.astype(float)
    vo = g["volume"].values.astype(float)
    px = cl[-1]
    if px < PX_FLOOR or not np.isfinite(px): return None

    ma = {n: float(np.mean(cl[-n:])) for n in (5, 20, 60, 120, 240)}
    ma240p = float(np.mean(cl[-260:-20]))
    ma60p  = float(np.mean(cl[-80:-20]))
    tr = np.maximum(hi[1:] - lo[1:], np.maximum(np.abs(hi[1:] - cl[:-1]), np.abs(lo[1:] - cl[:-1])))
    atr = float(np.mean(tr[-20:]))
    sd20 = float(np.std(cl[-20:], ddof=0))
    amt = cl * vo
    hi52 = float(np.max(hi[-252:])); lo52 = float(np.min(lo[-252:]))
    hi5y = float(np.max(hi[-1250:])) if len(hi) >= 1250 else float(np.max(hi))

    # 연속 하락일
    ds = 0
    for k in range(len(cl) - 1, 0, -1):
        if cl[k] < cl[k - 1]: ds += 1
        else: break

    hi252 = pd.Series(hi).rolling(252, min_periods=120).max().values
    volma = pd.Series(vo).rolling(60, min_periods=40).mean().values
    body = cl / np.where(op > 0, op, np.nan) - 1
    wick = (hi - np.maximum(op, cl)) / np.where(hi > 0, hi, np.nan)
    sig = ((cl >= hi252 * NEAR_HIGH) & (vo >= volma * VOL_MULT)
           & (wick >= WICK_MIN) & (body <= BODY_SMALL))

    r = lambda n: px / cl[-1 - n] - 1 if len(cl) > n and cl[-1 - n] else np.nan
    f = dict(
        종가=px,
        등락1일=r(1), 등락3일=r(3), 등락5일=r(5), 등락20일=r(20),
        이격MA5=px / ma[5] - 1, 이격MA20=px / ma[20] - 1, 이격MA60=px / ma[60] - 1,
        이격MA120=px / ma[120] - 1, 이격MA240=px / ma[240] - 1,
        MA60_240간격=ma[60] / ma[240] - 1,
        MA60_240간격_20일전=ma60p / ma240p - 1,
        MA240기울기=ma240p and ma[240] / ma240p - 1,
        MA60기울기=ma60p and ma[60] / ma60p - 1,
        정배열=int(ma[5] > ma[20] > ma[60] > ma[120] > ma[240]),
        역배열=int(ma[5] < ma[20] < ma[60] < ma[120] < ma[240]),
        고점52주比=px / hi52 - 1 if hi52 else np.nan,
        저점52주比=px / lo52 - 1 if lo52 else np.nan,
        고점5년比=px / hi5y - 1 if hi5y else np.nan,
        볼린저PCT=((px - (ma[20] - 2 * sd20)) / (4 * sd20)) if sd20 > 0 else np.nan,
        RSI14=rsi(cl), 연속하락일=ds,
        ATR비율=atr / px, 변동성20일=sd20 / px,
        평균거래대금20일=float(np.mean(amt[-20:])),
        거래량배수=vo[-1] / np.mean(vo[-20:]) if np.mean(vo[-20:]) > 0 else np.nan,
        거래대금배수=amt[-1] / np.mean(amt[-20:]) if np.mean(amt[-20:]) > 0 else np.nan,
        고점매도신호10일=int(np.nansum(sig[-10:])),
    )
    return f


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="20260731", help="상승률을 재는 날 (기본 20260731)")
    ap.add_argument("--zone", default="20260729,20260730", help="지표를 뽑을 '존' 날짜들")
    ap.add_argument("--tiers", default="29,25,20,15", help="등급 경계 %% (내림차순)")
    a = ap.parse_args()
    T = sorted([float(x) for x in a.tiers.split(",")], reverse=True)
    zdays = [x.strip() for x in a.zone.split(",")]
    zfmt = [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in zdays]

    print("=" * 104)
    print(f" 존 지표 → 다음날 등급  ·  존 {', '.join(zdays)}  →  결과일 {a.date}")
    print("=" * 104)

    try:
        from pykrx import stock
    except Exception:
        sys.exit("pykrx 없음 —  pip install pykrx")

    # ── ① 결과일 등락률 → 등급
    ch = []
    for m in ("KOSPI", "KOSDAQ"):
        try:
            d = stock.get_market_price_change_by_ticker(a.date, a.date, market=m)
            d = d.reset_index(); d.columns = [str(c) for c in d.columns]
            d = d.rename(columns={d.columns[0]: "code"})
            d["code"] = d["code"].astype(str).str.zfill(6); d["mkt"] = m
            ch.append(d)
        except Exception as e:
            print(f"  [{m}] 등락률 실패: {str(e)[:70]}")
    if not ch: sys.exit("등락률 없음")
    C = pd.concat(ch, ignore_index=True)
    rc = next(c for c in C.columns if "등락" in c)
    nc = next((c for c in C.columns if "종목명" in c), None)
    C[rc] = pd.to_numeric(C[rc], errors="coerce")
    C = C.rename(columns={rc: "등락률", **({nc: "종목명"} if nc else {})})

    def tier(v):
        if not np.isfinite(v): return "결측"
        for t in T:
            if v >= t: return ("상한가" if t >= 29 else f"+{t:.0f}%↑")
        return "그 외"
    C["등급"] = C["등락률"].apply(tier)
    order = (["상한가"] + [f"+{t:.0f}%↑" for t in T if t < 29] + ["그 외"])
    cnt = C["등급"].value_counts()
    print("등급 분포: " + " · ".join(f"{k} {cnt.get(k,0):,}종" for k in order))

    # ── ② 존 날짜별 지표
    D = load_daily()
    have = set(D["date"].unique())
    for z in zfmt:
        if z not in have: print(f"  ⚠️ 일봉에 {z} 없음 — 그 날짜는 건너뛴다")
    zfmt = [z for z in zfmt if z in have]
    if not zfmt: sys.exit("존 날짜의 일봉이 없다. 진우_일봉_증분수집.py 를 먼저 돌릴 것")

    F = {}
    for z in zfmt:
        rows = []
        for c, g in D.groupby("code", sort=False):
            f = feats(g, z)
            if f is None: continue
            f["code"] = c; f["mkt"] = g["mkt"].iloc[-1]
            rows.append(f)
        F[z] = pd.DataFrame(rows).set_index("code")
        print(f"  {z} 지표 {len(F[z]):,}종")

    base_z = zfmt[-1]                       # 마지막 존 날짜(=D-1)를 기준으로 본다
    X = F[base_z].copy()
    # 존 이틀 사이의 변화 (마지막 날에 뭔가 달라졌나)
    if len(zfmt) >= 2:
        p = F[zfmt[0]]
        for k in ("등락1일", "RSI14", "볼린저PCT", "이격MA20", "거래대금배수"):
            if k in X.columns and k in p.columns:
                X[f"Δ{k}"] = X[k] - p[k].reindex(X.index)

    # ── ③ 재무 (존 마지막 날 기준)
    zd = base_z.replace("-", "")
    fin = []
    for m in ("KOSPI", "KOSDAQ"):
        try:
            fd = stock.get_market_fundamental_by_ticker(zd, market=m)
            cp = stock.get_market_cap_by_ticker(zd, market=m)
            t = fd.join(cp[[c for c in cp.columns if c not in fd.columns]], how="outer")
            t = t.reset_index(); t.columns = [str(c) for c in t.columns]
            t = t.rename(columns={t.columns[0]: "code"})
            t["code"] = t["code"].astype(str).str.zfill(6)
            fin.append(t)
        except Exception as e:
            print(f"  [{m}] 재무 실패: {str(e)[:60]}")
    if fin:
        FIN = pd.concat(fin, ignore_index=True).drop_duplicates("code").set_index("code")
        for k in ("PER", "PBR", "EPS", "BPS", "DIV", "시가총액"):
            if k in FIN.columns: X[k] = pd.to_numeric(FIN[k], errors="coerce").reindex(X.index)

    sec = {}
    for f in ("liquidity_sector.csv", "kosdaq_industry.csv"):
        p = _find(f)
        if not p: continue
        try:
            d = pd.read_csv(p, dtype=str); d.columns = [x.strip().lstrip("﻿") for x in d.columns]
            if {"code", "sector"}.issubset(d.columns):
                sec.update(dict(zip(d["code"].str.zfill(6), d["sector"].astype(str))))
        except Exception: pass
    X["sector"] = pd.Series(sec).reindex(X.index).fillna("미분류")

    X = X.join(C.set_index("code")[["등락률", "등급"] + (["종목명"] if "종목명" in C.columns else [])],
               how="inner")
    if "종목명" not in X.columns: X["종목명"] = X.index
    print(f"\n지표 × 등급 결합: {len(X):,}종")

    out = os.path.join(HERE, f"급등_사전지표_{a.date}.csv")
    X.reset_index().to_csv(out, index=False, encoding="utf-8-sig")

    # ── ④ 등급별 중앙값 vs 전체 (기저율 동시 표시)
    KEY = ["등락1일", "등락3일", "등락5일", "등락20일",
           "이격MA5", "이격MA20", "이격MA60", "이격MA240",
           "MA60_240간격", "MA240기울기", "MA60기울기", "역배열", "정배열",
           "고점52주比", "저점52주比", "고점5년比", "볼린저PCT", "RSI14",
           "연속하락일", "ATR비율", "변동성20일", "거래량배수", "거래대금배수",
           "PBR", "PER", "DIV"]
    KEY = [k for k in KEY if k in X.columns]
    tiers = [t for t in order if (X["등급"] == t).sum() >= 3]
    rows = []
    print("\n" + "=" * 104)
    print(f" 존 마지막 날({base_z}) 지표 — 등급별 중앙값")
    print("=" * 104)
    hdr = dw("지표", 16) + dw("전체", 10, 1)
    for t in tiers: hdr += dw(t, 11, 1)
    hdr += dw("상한가−전체", 13, 1)
    print(hdr)
    print("-" * 104)
    for k in KEY:
        allm = X[k].median()
        line = dw(k, 16) + dw(f"{allm:,.2f}" if abs(allm) >= 10 else f"{allm:.3f}", 10, 1)
        vals = {}
        for t in tiers:
            v = X.loc[X["등급"] == t, k].median()
            vals[t] = v
            line += dw(f"{v:,.2f}" if abs(v) >= 10 else f"{v:.3f}", 11, 1)
        d = vals.get("상한가", np.nan) - allm
        line += dw(f"{d:+,.2f}" if abs(d) >= 10 else f"{d:+.3f}", 13, 1)
        print(line)
        rows.append(dict(지표=k, 전체=allm, **vals, 상한가_전체차=d))
    print("-" * 104)

    S = pd.DataFrame(rows)
    S.to_csv(os.path.join(HERE, f"급등_사전지표_요약_{a.date}.csv"),
             index=False, encoding="utf-8-sig")

    # ── ⑤ 계단이 나오는 지표만 골라낸다
    print("\n[등급이 올라갈수록 단조롭게 변하는 지표] — 우연이 아닐 후보")
    seq = [t for t in ["상한가"] + [f"+{t:.0f}%↑" for t in T if t < 29] if t in tiers]
    mono = []
    if len(seq) >= 3:
        for _, r in S.iterrows():
            v = [r[t] for t in seq if pd.notna(r.get(t))]
            if len(v) < 3: continue
            inc = all(v[i] < v[i + 1] for i in range(len(v) - 1))
            dec = all(v[i] > v[i + 1] for i in range(len(v) - 1))
            if inc or dec:
                sp = abs(v[0] - r["전체"])
                mono.append((r["지표"], "상한가일수록 높음" if dec else "상한가일수록 낮음",
                             v[0], r["전체"], sp))
    if mono:
        for nm, dirn, top, allv, _ in sorted(mono, key=lambda x: -x[4]):
            print(f"  · {dw(nm,14)} {dirn:<16} 상한가 {top:>9.3f}  전체 {allv:>9.3f}")
    else:
        print("  없음 — 등급별로 단조롭게 변하는 지표가 하나도 없다.")
        print("     즉 이 지표들로는 상승 강도를 설명하지 못한다.")

    print(f"\n섹터 — 등급별 반도체 밸류체인 비중")
    CH = ["반도체", "특수 목적용 기계", "전자부품", "통신 및 방송 장비", "측정, 시험",
          "기초 화학물질", "전동기", "일반 목적용 기계", "그외 기타 전문, 과학"]
    X["체인"] = X["sector"].apply(lambda s: any(x in str(s) for x in CH))
    for t in ["전체"] + tiers:
        sub = X if t == "전체" else X[X["등급"] == t]
        print(f"  {dw(t,10)} {len(sub):>5,}종 · 체인 {sub['체인'].mean()*100:>5.1f}%")

    print(f"\n저장: 급등_사전지표_{a.date}.csv · 급등_사전지표_요약_{a.date}.csv")
    print("\n⚠️ 하루치 사후 관찰이다. 여기서 보이는 패턴은 **가설**이지 규칙이 아니다.")
    print("   같은 스크립트를 다른 급등일에 돌려 같은 패턴이 나오는지 먼저 확인할 것.")


if __name__ == "__main__":
    main()
