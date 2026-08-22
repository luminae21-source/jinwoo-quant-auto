# -*- coding: utf-8 -*-
r"""휩쏘_추출.py — 7/31 등급별 급등 종목 + 7/29·7/30 위치·재무·테마 (2026-08-01)

[형의 정의]
  7/28~7/31 = **휩쏘 구간**. 손절 유도 → 재진입 방해 → 상승.
  급락 1번(1일째)만으론 바닥을 모른다. 급락 2번(2일째)이 정석 진입.
  이건 예외적 자리다. 30년 백테스트로는 안 잡힌다 → 지금 실물을 뽑아 눈으로 본다.

[작업 1 — 이 스크립트가 하는 일]
  ① 7/31 상승 등급으로 종목을 가른다:  상한가(≥28%) · 25%↑ · 20%↑ · 15%↑ · 10%↑
  ② 각 종목의 **7/29·7/30 실제 주가**(시고저종·거래량·거래대금)를 붙인다
  ③ 재무(7/30 기준: PER PBR EPS BPS 배당 시총) + 테마/섹터
  ④ **위치 확인** — 휩쏘 구조를 숫자로:
       · 급락1 (7/28→7/29) · 급락2 (7/29→7/30) · 2일연속급락 여부
       · 5년/52주 고점 대비, 52주 저점 대비
       · 일봉 MA20/60/120/240 이격
       · 형이 지목한 선 근접도 — 주20주·주60주·월5·월10 (%거리, 닿았으면 표시)

출력: 휩쏘추출_20260731.csv           (전 종목 1행, 등급 컬럼)
      휩쏘추출_요약_20260731.txt        (등급별·테마별 화면 그대로)

사용: py 휩쏘_추출.py
      py 휩쏘_추출.py --date 20260731 --zone 20260729,20260730
      py 휩쏘_추출.py --tiers 28,25,20,15,10

⚠️ 사실 추출 도구다. 매수 신호가 아니다. 이건 '이 자리가 어떻게 생겼나'를 보는 관찰이다.
"""
import os, sys, argparse, warnings, io
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

PX_FLOOR = 500

# 테마 — KRX 업종을 큰 덩어리로 묶는다 (7/31은 반도체가 압도적일 것)
THEME = [
    ("반도체", ["반도체", "특수 목적용 기계", "전자부품", "측정, 시험", "광학",
               "그외 기타 전문, 과학", "통신 및 방송 장비", "일반 목적용 기계"]),
    ("이차전지", ["전지", "축전지"]),
    ("디스플레이", ["디스플레이", "영상·음향", "영상, 음향"]),
    ("바이오", ["의약", "의료", "생물학", "기초 의약"]),
    ("금융", ["금융", "은행", "보험", "신탁", "증권"]),
    ("화학소재", ["화학", "철강", "금속", "고무", "플라스틱", "시멘트"]),
    ("조선방산", ["선박", "항공", "무기", "기관 및 터빈"]),
    ("자동차", ["자동차", "차체"]),
    ("건설", ["건설", "부동산", "토건"]),
    ("SW", ["소프트웨어", "인터넷", "포털", "게임", "자료처리"]),
]


def theme_of(sec):
    s = str(sec)
    for name, keys in THEME:
        if any(k in s for k in keys): return name
    return "기타"


def dw(t, n, right=False):
    """한글 2칸 폭 맞춤."""
    import unicodedata
    t = str(t)
    g = lambda s: sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)
    while g(t) > n: t = t[:-1]
    pad = " " * max(0, n - g(t))
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
    if not fr: return None
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


def position(g, zone_last):
    """존 마지막 날(zone_last, 예 2026-07-30)까지의 일봉으로 '위치'를 잰다. 미래 정보 없음."""
    g = g[g["date"] <= zone_last]
    if len(g) < 60: return None
    dts = pd.to_datetime(g["date"].values)
    cl = g["close"].values.astype(float); hi = g["high"].values.astype(float)
    lo = g["low"].values.astype(float)
    px = cl[-1]
    if px < PX_FLOOR: return None

    def ma(n): return float(np.mean(cl[-n:])) if len(cl) >= n else np.nan
    ma20, ma60, ma120, ma240 = ma(20), ma(60), ma(120), ma(240)

    # 주봉·월봉 이동평균 (형이 지목한 선)
    s = pd.Series(cl, index=dts)
    wk = s.resample("W-FRI").last().dropna()
    mo = s.resample("M").last().dropna()
    ma20w = float(wk.tail(20).mean()) if len(wk) >= 20 else np.nan
    ma60w = float(wk.tail(60).mean()) if len(wk) >= 60 else np.nan
    ma5m  = float(mo.tail(5).mean())  if len(mo) >= 5  else np.nan
    ma10m = float(mo.tail(10).mean()) if len(mo) >= 10 else np.nan

    hi52 = float(np.max(hi[-252:])); lo52 = float(np.min(lo[-252:]))
    hi5y = float(np.max(hi[-1250:])) if len(hi) >= 1250 else float(np.max(hi))

    # 급락 구조: 급락1(7/28→29) = 마지막 전날, 급락2(7/29→30) = 마지막 날
    r1 = cl[-2] / cl[-3] - 1 if len(cl) >= 3 else np.nan   # 1일째 급락
    r2 = cl[-1] / cl[-2] - 1 if len(cl) >= 2 else np.nan   # 2일째 급락
    # 존 저가(마지막 날 저가)가 어느 선에 닿았나
    zlow = lo[-1]

    def near(line):
        return (px / line - 1) if (line and np.isfinite(line)) else np.nan
    def touched(line):
        # 존 마지막 날 저가가 그 선 아래로 찔렀다가 종가가 위 = 지지 확인
        return bool(line and np.isfinite(line) and zlow <= line <= px * 1.001)

    # 가장 가까운 '핵심 선'과 거리
    lines = {"주20주": ma20w, "주60주": ma60w, "월5": ma5m, "월10": ma10m,
             "일240": ma240}
    near_all = {k: near(v) for k, v in lines.items() if np.isfinite(near(v))}
    if near_all:
        key_line = min(near_all, key=lambda k: abs(near_all[k]))
        key_dist = near_all[key_line]
    else:
        key_line, key_dist = "-", np.nan

    return dict(
        급락1=r1, 급락2=r2,
        이틀연속급락=bool(np.isfinite(r1) and np.isfinite(r2) and r1 < 0 and r2 < 0),
        고점5년比=px / hi5y - 1 if hi5y else np.nan,
        고점52주比=px / hi52 - 1 if hi52 else np.nan,
        저점52주比=px / lo52 - 1 if lo52 else np.nan,
        이격MA20=near(ma20), 이격MA60=near(ma60),
        이격MA120=near(ma120), 이격MA240=near(ma240),
        주20주근접=near(ma20w), 주60주근접=near(ma60w),
        월5근접=near(ma5m), 월10근접=near(ma10m),
        핵심선=key_line, 핵심선거리=key_dist,
        선지지=(", ".join(k for k, v in lines.items() if touched(v)) or ""),
    )


def tier_of(v, T):
    if not np.isfinite(v): return None
    for i, t in enumerate(T):
        if v >= t:
            return "상한가(≥%g%%)" % T[0] if i == 0 else "%g%%↑" % t
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="20260731", help="상승 등급을 재는 날")
    ap.add_argument("--zone", default="20260729,20260730", help="위치를 볼 존 날짜들")
    ap.add_argument("--tiers", default="28,25,20,15,10", help="등급 경계 %% (내림차순)")
    a = ap.parse_args()
    T = sorted([float(x) for x in a.tiers.split(",")], reverse=True)
    zdays = [x.strip() for x in a.zone.split(",")]
    zfmt = [f"{d[:4]}-{d[4:6]}-{d[6:]}" for d in zdays]
    zone_last = zfmt[-1]

    buf = io.StringIO()
    def out(*args):
        line = " ".join(str(x) for x in args)
        print(line); buf.write(line + "\n")

    out("=" * 108)
    out(f" 휩쏘 추출 — 등급일 {a.date} · 존 {', '.join(zdays)}  (7/28~7/31 휩쏘 구간)")
    out("=" * 108)

    try:
        from pykrx import stock
    except Exception:
        sys.exit("pykrx 없음 —  pip install pykrx  후 다시 실행")

    # ── ① 7/31 등락률 → 등급
    ch = []
    for m in ("KOSPI", "KOSDAQ"):
        try:
            d = stock.get_market_price_change_by_ticker(a.date, a.date, market=m)
            d = d.reset_index(); d.columns = [str(c) for c in d.columns]
            d = d.rename(columns={d.columns[0]: "code"}); d["code"] = d["code"].astype(str).str.zfill(6)
            d["mkt"] = m; ch.append(d)
        except Exception as e:
            out(f"  [{m}] 등락률 실패: {str(e)[:70]}")
    if not ch: sys.exit("등락률 데이터 없음")
    C = pd.concat(ch, ignore_index=True)
    rc = next(c for c in C.columns if "등락" in c)
    nc = next((c for c in C.columns if "종목명" in c), None)
    ccl = next((c for c in C.columns if c in ("종가",)), None)
    C[rc] = pd.to_numeric(C[rc], errors="coerce")
    C = C.rename(columns={rc: "등락률", **({nc: "종목명"} if nc else {}),
                          **({ccl: "종가_31"} if ccl else {})})
    C["등급"] = C["등락률"].apply(lambda v: tier_of(v, T))
    H = C[C["등급"].notna()].copy()
    out(f"\n전 종목 {len(C):,} · 상승 {int((C['등락률']>0).sum()):,} · 하락 {int((C['등락률']<0).sum()):,}")
    lab = ["상한가(≥%g%%)" % T[0]] + ["%g%%↑" % t for t in T[1:]]
    dist = " · ".join(f"{k} {(H['등급']==k).sum()}종" for k in lab)
    out(f"등급 분포: {dist}   (총 {len(H)}종)")
    if len(H) == 0: sys.exit("등급 해당 종목 없음")
    codes = set(H["code"])

    # ── ② 7/29·7/30 OHLC
    px_by_day = {}
    for z in zdays:
        parts = []
        for m in ("KOSPI", "KOSDAQ"):
            try:
                o = stock.get_market_ohlcv_by_ticker(z, market=m)
                o = o.reset_index(); o.columns = [str(c) for c in o.columns]
                o = o.rename(columns={o.columns[0]: "code"}); o["code"] = o["code"].astype(str).str.zfill(6)
                parts.append(o)
            except Exception as e:
                out(f"  [{z} {m}] OHLC 실패: {str(e)[:60]}")
        if parts:
            P = pd.concat(parts, ignore_index=True).drop_duplicates("code").set_index("code")
            px_by_day[z] = P
            out(f"  {z} 주가 {len(P):,}종")

    # ── ③ 재무 + 시총 (존 마지막 날)
    zd = zdays[-1]
    fin = []
    for m in ("KOSPI", "KOSDAQ"):
        try:
            fd = stock.get_market_fundamental_by_ticker(zd, market=m)
            cp = stock.get_market_cap_by_ticker(zd, market=m)
            t = fd.join(cp[[c for c in cp.columns if c not in fd.columns]], how="outer")
            t = t.reset_index(); t.columns = [str(c) for c in t.columns]
            t = t.rename(columns={t.columns[0]: "code"}); t["code"] = t["code"].astype(str).str.zfill(6)
            fin.append(t)
        except Exception as e:
            out(f"  [{zd} {m}] 재무 실패: {str(e)[:60]}")
    FIN = pd.concat(fin, ignore_index=True).drop_duplicates("code").set_index("code") if fin else pd.DataFrame()

    # ── 섹터/테마 + 이름
    sec = {}
    for f in ("liquidity_sector.csv", "kosdaq_industry.csv"):
        p = _find(f)
        if not p: continue
        try:
            d = pd.read_csv(p, dtype=str); d.columns = [x.strip().lstrip("﻿") for x in d.columns]
            if {"code", "sector"}.issubset(d.columns):
                sec.update(dict(zip(d["code"].str.zfill(6), d["sector"].astype(str))))
        except Exception: pass
    names = {}
    npp = _find("종목명_맵.csv")
    if npp:
        try:
            nm = pd.read_csv(npp, dtype=str); names = dict(zip(nm.iloc[:,0].str.zfill(6), nm.iloc[:,1]))
        except Exception: pass

    # ── ④ 위치 (로컬 일봉)
    POS = {}
    D = load_daily()
    if D is not None:
        sub = D[D["code"].isin(codes)]
        for c, g in sub.groupby("code", sort=False):
            p = position(g, zone_last)
            if p: POS[c] = p
        out(f"  위치 지표: 로컬 일봉으로 {len(POS)}종 계산")
    else:
        out("  ⚠️ _일봉OHLCV_*_adj.csv 없음 → 위치 지표 생략 (급락구조·MA근접 안 나옴)")

    # ── 조립
    rows = []
    for _, h in H.iterrows():
        c = h["code"]
        r = {"등급": h["등급"], "code": c,
             "종목명": h.get("종목명") or names.get(c, c),
             "시장": h["mkt"], "섹터": sec.get(c, "미분류"),
             "테마": theme_of(sec.get(c, "")),
             "등락률_31": h["등락률"], "종가_31": h.get("종가_31", np.nan)}
        for z in zdays:
            P = px_by_day.get(z)
            if P is not None and c in P.index:
                s = P.loc[c]
                tag = z[4:]
                for src, dst in (("시가","시"),("고가","고"),("저가","저"),("종가","종"),
                                 ("거래량","거래량"),("거래대금","거래대금")):
                    if src in s.index: r[f"{dst}_{tag}"] = s[src]
        if len(FIN) and c in FIN.index:
            s = FIN.loc[c]
            for k in ("PER","PBR","EPS","BPS","DIV","시가총액"):
                if k in s.index: r[k] = pd.to_numeric(s[k], errors="coerce")
        r.update(POS.get(c, {}))
        rows.append(r)
    X = pd.DataFrame(rows)
    outp = os.path.join(HERE, f"휩쏘추출_{a.date}.csv")
    X.to_csv(outp, index=False, encoding="utf-8-sig")

    # ── 화면 — 등급별 리스트 (테마로 묶어서)
    z0 = zdays[0][4:]; z1 = zdays[1][4:] if len(zdays) > 1 else z0
    for tier in lab:
        sub = X[X["등급"] == tier].copy()
        if len(sub) == 0: continue
        sub = sub.sort_values(["테마", "등락률_31"], ascending=[True, False])
        out("\n" + "=" * 108)
        out(f" {tier} — {len(sub)}종")
        out("=" * 108)
        out(dw("코드",7) + dw("종목명",16) + dw("테마",10) + dw(f"종{z1}",9,1)
            + dw("급락1",8,1) + dw("급락2",8,1) + dw("2연속",6,1)
            + dw("5년比",7,1) + dw("MA60",7,1) + dw("핵심선",8) + dw("거리",7,1)
            + dw("PBR",6,1) + dw("PER",7,1))
        out("-" * 108)
        for _, r in sub.iterrows():
            g = lambda k, f="{:.1%}": (f.format(r[k]) if pd.notna(r.get(k)) else "-")
            close_z1 = r.get(f"종_{z1}")
            kl = r.get("핵심선")
            kl = kl if (isinstance(kl, str) and kl not in ("", "nan")) else "-"
            two = (r.get("이틀연속급락") and pd.notna(r.get("급락1")) and pd.notna(r.get("급락2")))
            out(dw(r["code"],7) + dw(r["종목명"],16) + dw(r["테마"],10)
                + dw(f"{close_z1:,.0f}" if pd.notna(close_z1) else "-",9,1)
                + dw(g("급락1"),8,1) + dw(g("급락2"),8,1)
                + dw("★" if two else "",6,1)
                + dw(g("고점5년比","{:.0%}"),7,1) + dw(g("이격MA60"),7,1)
                + dw(kl,8) + dw(g("핵심선거리"),7,1)
                + dw(f"{r['PBR']:.2f}" if pd.notna(r.get("PBR")) else "-",6,1)
                + dw(f"{r['PER']:.1f}" if pd.notna(r.get("PER")) else "-",7,1))
        # 테마 분포
        tv = sub["테마"].value_counts()
        out("  · 테마: " + " · ".join(f"{k} {v}" for k, v in tv.items()))
        # 이틀연속급락 비율 (휩쏘 핵심)
        if "이틀연속급락" in sub.columns:
            n2 = int(sub["이틀연속급락"].sum())
            out(f"  · 급락1·급락2 **이틀 연속 하락 후 반등**: {n2}/{len(sub)}종 ({n2/len(sub)*100:.0f}%)")

    # ── 전체 요약
    out("\n" + "=" * 108)
    out(" 전체 요약")
    out("=" * 108)
    tt = X["테마"].value_counts()
    out("테마 분포(전 등급): " + " · ".join(f"{k} {v}" for k, v in tt.head(8).items()))
    if "이틀연속급락" in X.columns:
        n2 = int(X["이틀연속급락"].sum())
        out(f"이틀 연속 급락 후 7/31 반등: {n2}/{len(X)}종 ({n2/len(X)*100:.0f}%)  ← 휩쏘 재진입 후보의 핵심 구조")
    if "선지지" in X.columns:
        held = X[X["선지지"].astype(str).str.len() > 0]
        if len(held):
            out(f"존 저가가 핵심선을 찍고 올라온 종목: {len(held)}종")

    with open(os.path.join(HERE, f"휩쏘추출_요약_{a.date}.txt"), "w", encoding="utf-8") as f:
        f.write(buf.getvalue())
    out(f"\n저장: 휩쏘추출_{a.date}.csv · 휩쏘추출_요약_{a.date}.txt")
    out("\n⚠️ 사실 추출이다. 매수 신호가 아니라 '이 자리가 어떻게 생겼나'를 보는 관찰이다.")
    out("   다음(작업2·3): 휩쏘 자체를 일봉에서 찾아내는 탐색기 — 주20/60·월5/10 선 근접.")


if __name__ == "__main__":
    main()
