# -*- coding: utf-8 -*-
r"""주도주_풀.py — 꾸준히 이겨온 회사 찾기 (관찰 리스트 구축) · 2026-07-30 신설

╔══════════════════════════════════════════════════════════════════════════════╗
║ 이건 '지금 뜨는 종목 쫓기'가 아니다.                                          ║
║ **여러 해에 걸쳐 일관되게 시장을 이겨온 회사**를 골라 관찰 리스트를 만든다.     ║
╚══════════════════════════════════════════════════════════════════════════════╝

[왜 기존 스크리너로는 안 되나 — 대덕전자로 확인]
    5년 수익률 +485% (KOSPI +77%) → 초과 **+408%p**
    그런데 PBR 6.39 · PER 176 · 배당 0.5%
  → **저PBR·고배당 필터로는 절대 안 잡힌다.** 밸류에이션이 아니라
    '오래 이겨온 사실' 자체가 이 회사를 후보로 만든다.

[선별 기준 — 지속성이 전부]
  ① 1년·3년·5년 **모두** KOSPI 초과   ← 한 기간만 이긴 건 제외 (반짝 상승 배제)
  ② 유동성: 시총 3,000억+ · 일 거래대금 30억+  (기관이 살 수 있는 규모)
  ③ 우선주·신규상장 36M 미만 제외
  ④ 적자 지속 제외: 최근 3개 관측 중 ROE>0 이 1회 이상 (시클리컬 허용)
  점수 = 3년 초과 × 0.4 + 5년 초과 × 0.4 + 1년 초과 × 0.2  (긴 기간에 가중)

[⚠️ 정직 고지 — 이건 검증된 알파가 아니다]
  · 횡단면 모멘텀(12-1)은 이 프로젝트에서 **기각**됐다(롱온리 −9~−13%).
  · 여기 쓰는 '다기간 지속 초과수익'은 그것과 다른 개념이지만 **아직 검정하지 않았다.**
  · 그러므로 이 리스트는 **매수 신호가 아니라 관찰 후보(watchlist)**다.
    실제 진입은 매매카드(분할·손절·익절)와 청산규율(분산 경보)을 거친다.
  · 생존편향 주의: 지금 살아있는 종목만 본다. "5년을 이겨온" 것은 사후 관찰이다.

사용: py 주도주_풀.py                 (전체 풀)
      py 주도주_풀.py --top 40
      py 주도주_풀.py --check 353200  (특정 종목이 풀에 드는지·왜)
출력: 주도주_풀.csv · 주도주_풀.md
"""
import os, sys, argparse, datetime, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

MCAP_FLOOR, AMT_FLOOR = 3000e8, 30e8
NEW_LISTING_M = 36
WINDOWS = [(12, 0.2), (36, 0.4), (60, 0.4)]     # (개월, 가중치)


def _find(fn):
    for d in (HERE, os.path.join(HERE, "데이터수리"), os.path.dirname(HERE), os.getcwd()):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--check", default=None)
    a = ap.parse_args()

    # ── 월봉 (전기간 병합본 우선, 없으면 2016+ 사용)
    p = _find("_월봉_KIS_전기간.csv") or _find("_월봉_KIS_adj_2016.csv")
    if not p: sys.exit("❌ 월봉 패널 없음 (_월봉_KIS_전기간.csv 또는 _월봉_KIS_adj_2016.csv)")
    P = pd.read_csv(p, dtype={"code": str}); P["code"] = P["code"].str.zfill(6)
    px = P.pivot_table(index="ym", columns="code", values="close", aggfunc="last").sort_index()
    last_ym = px.index[-1]

    ix = pd.read_csv(_find("kospi_index_daily.csv"))
    ix["ym"] = pd.to_datetime(ix["Date"]).dt.strftime("%Y-%m")
    im = ix.groupby("ym")["Close"].last()

    F = pd.concat([pd.read_csv(_find(f"종목재무_KRX_{m}.csv"), dtype={"code": str},
                               usecols=["date","code","PBR","PER","BPS","EPS","DIV"])
                   for m in ("KOSPI","KOSDAQ")])
    F["code"] = F["code"].str.zfill(6); F["ym"] = F["date"].str[:7]
    for c in ("PBR","PER","BPS","EPS","DIV"): F[c] = pd.to_numeric(F[c], errors="coerce")
    F["roe"] = np.where(F["BPS"] > 0, F["EPS"]/F["BPS"], np.nan)
    Flast = F.sort_values("ym").groupby("code").tail(1).set_index("code")
    roe3 = F.sort_values("ym").groupby("code")["roe"].apply(lambda s: (s.tail(3) > 0).sum())

    mc = pd.read_csv(_find("종목시총_30년.csv"), dtype={"code": str})
    mc.columns = [x.strip().lstrip("﻿") for x in mc.columns]; mc["code"] = mc["code"].str.zfill(6)
    MC = pd.to_numeric(mc.sort_values("date").groupby("code")["mcap"].last(), errors="coerce")

    AMT = pd.Series(dtype=float)
    for m in ("KOSPI","KOSDAQ"):
        dp = _find(f"_일봉OHLCV_{m}_adj.csv")
        if dp:
            d = pd.read_csv(dp, dtype={"code": str}, usecols=["code","date","close","volume"])
            d["code"] = d["code"].str.zfill(6)
            d = d.sort_values("date").groupby("code").tail(20)
            AMT = pd.concat([AMT, (d["close"]*d["volume"]).groupby(d["code"]).mean()])

    NAME_CACHE = os.path.join(HERE, "종목명_맵.csv")
    names = {}
    if os.path.exists(NAME_CACHE):
        try:
            nm = pd.read_csv(NAME_CACHE, dtype=str); names = dict(zip(nm.iloc[:,0].str.zfill(6), nm.iloc[:,1]))
        except Exception: pass

    def fill_names(codes):
        miss = [c for c in codes if not str(names.get(c, "")).strip()]
        if not miss: return
        try:
            from pykrx import stock
        except Exception:
            print("  (종목명 조회 생략 — pykrx 없음)"); return
        got = 0
        for c in miss:
            try:
                n = stock.get_market_ticker_name(c)
                if n: names[c] = n; got += 1
            except Exception: continue
        if got:
            pd.DataFrame({"code": list(names), "name": list(names.values())}) \
              .to_csv(NAME_CACHE, index=False, encoding="utf-8-sig")
            print(f"  종목명 {got}건 조회·캐시 갱신")

    ALLC = set(px.columns)
    is_common = lambda c: c.isdigit() and not ((not c.endswith("0")) and (c[:5]+"0") in ALLC)

    rows = []
    for c in px.columns:
        s = px[c].dropna()
        if len(s) < max(w for w, _ in WINDOWS) + 1: continue
        if not is_common(c): continue
        if len(s) < NEW_LISTING_M: continue
        mcap = MC.get(c, np.nan); amt = AMT.get(c, np.nan)
        if not (pd.notna(mcap) and mcap >= MCAP_FLOOR): continue
        if pd.notna(amt) and amt < AMT_FLOOR: continue
        if roe3.get(c, 0) < 1: continue                       # 적자 지속 제외(시클리컬 허용)

        exc, ok, det = {}, True, []
        for w, _ in WINDOWS:
            if len(s) <= w: ok = False; break
            r = s.iloc[-1]/s.iloc[-1-w] - 1
            b = im.get(s.index[-1], np.nan)/im.get(s.index[-1-w], np.nan) - 1
            if not np.isfinite(b): ok = False; break
            e = (r - b) * 100
            exc[w] = e; det.append((w, r*100, b*100, e))
            if e <= 0: ok = False                              # ① 전 기간 초과 필수
        if not ok or len(exc) < len(WINDOWS): continue

        score = sum(exc[w]*wt for w, wt in WINDOWS)
        f = Flast.loc[c] if c in Flast.index else None
        hi5 = s.tail(60).max()
        rows.append(dict(code=c, name=names.get(c, c), score=score,
                         ex1=exc[12], ex3=exc[36], ex5=exc[60],
                         price=s.iloc[-1], dd5=(s.iloc[-1]/hi5 - 1)*100,
                         mcap=mcap/1e8, amt=(amt/1e8 if pd.notna(amt) else np.nan),
                         pbr=(f["PBR"] if f is not None else np.nan),
                         per=(f["PER"] if f is not None else np.nan),
                         roe=(f["roe"]*100 if f is not None and pd.notna(f["roe"]) else np.nan),
                         div=(f["DIV"] if f is not None else np.nan)))

    if not rows: sys.exit("풀 없음 — 조건을 만족하는 종목이 없습니다.")
    df = pd.DataFrame(rows).sort_values("score", ascending=False).reset_index(drop=True)
    df["rank"] = df.index + 1
    fill_names(list(df["code"]))
    df["name"] = df["code"].map(lambda c: names.get(c, c))

    print("=" * 108)
    print(f" 주도주 풀 — 꾸준히 이겨온 회사 (기준 {last_ym})")
    print("=" * 108)
    print(f"  기준: 1·3·5년 **모두** KOSPI 초과 · 시총 {MCAP_FLOOR/1e8:,.0f}억+ · 일거래대금 {AMT_FLOOR/1e8:.0f}억+ · 상장 {NEW_LISTING_M}M+")
    print(f"  통과: **{len(df):,}종** (전체 {len(px.columns):,} 중 {len(df)/len(px.columns)*100:.1f}%)")

    if a.check:
        c = a.check.zfill(6)
        fill_names([c])
        s = px[c].dropna() if c in px.columns else pd.Series(dtype=float)
        print(f"\n{'─'*108}\n  ▣ {names.get(c,c)}({c}) 진단")
        if not len(s): print("    패널에 없음"); return
        for w, _ in WINDOWS:
            if len(s) > w:
                r = (s.iloc[-1]/s.iloc[-1-w]-1)*100
                b = (im.get(s.index[-1],np.nan)/im.get(s.index[-1-w],np.nan)-1)*100
                print(f"    {w//12}년: 종목 {r:>+8.1f}% · KOSPI {b:>+7.1f}% → 초과 {r-b:>+8.1f}%p "
                      f"{'✅' if r-b>0 else '❌ 미달'}")
            else: print(f"    {w//12}년: 데이터 부족")
        print(f"    시총 {MC.get(c,np.nan)/1e8:,.0f}억 {'✅' if MC.get(c,0)>=MCAP_FLOOR else '❌'} · "
              f"거래대금 {AMT.get(c,np.nan)/1e8:,.0f}억 {'✅' if AMT.get(c,0)>=AMT_FLOOR else '❌'} · "
              f"ROE>0 최근3회중 {int(roe3.get(c,0))}회 {'✅' if roe3.get(c,0)>=1 else '❌'}")
        hit = df[df["code"] == c]
        print(f"    → 풀 {'포함 · ' + str(int(hit['rank'].iloc[0])) + '위' if len(hit) else '미포함'}")
        return

    print(f"\n  {'#':<4}{'종목':<20}{'현재가':>10}{'1년초과':>9}{'3년초과':>10}{'5년초과':>10}"
          f"{'5년고점比':>10}{'시총(억)':>10}{'PBR':>6}{'ROE':>7}{'배당':>6}")
    for _, r in df.head(a.top).iterrows():
        print(f"  {r['rank']:<4}{(str(r['name'])[:9]+'('+r['code']+')'):<20}{r['price']:>10,.0f}"
              f"{r['ex1']:>+8.0f}%{r['ex3']:>+9.0f}%{r['ex5']:>+9.0f}%{r['dd5']:>+9.0f}%"
              f"{r['mcap']:>10,.0f}{(r['pbr'] if pd.notna(r['pbr']) else 0):>6.2f}"
              f"{(r['roe'] if pd.notna(r['roe']) else 0):>6.1f}%{(r['div'] if pd.notna(r['div']) else 0):>5.1f}%")

    # 대덕전자 위치 확인 (기준 검증)
    dd = df[df["code"] == "353200"]
    print(f"\n  ▸ 대덕전자(353200): {'풀 포함 · ' + str(int(dd['rank'].iloc[0])) + '위' if len(dd) else '⚠️ 미포함 — 기준 재검토 필요'}")

    # 지금 싸진 것 (좋은 회사가 눌린 자리)
    cheap = df[df["dd5"] <= -30].head(12)
    if len(cheap):
        print(f"\n{'─'*108}\n  【5년 고점 대비 −30% 이상 눌린 주도주】 — 좋은 회사가 싸진 자리")
        print(f"  {'종목':<20}{'현재가':>10}{'5년고점比':>10}{'5년초과':>10}{'PBR':>7}{'ROE':>7}")
        for _, r in cheap.iterrows():
            print(f"  {(str(r['name'])[:9]+'('+r['code']+')'):<20}{r['price']:>10,.0f}{r['dd5']:>+9.0f}%"
                  f"{r['ex5']:>+9.0f}%{(r['pbr'] if pd.notna(r['pbr']) else 0):>7.2f}"
                  f"{(r['roe'] if pd.notna(r['roe']) else 0):>6.1f}%")

    # 이름 기반 간이 군집 (업종 태그 없으므로 키워드로)
    KW = {"반도체·장비": ["반도체","하이닉스","전기","엔지니어링","테스","피에스케이","한미","이오","원익","솔브레인","티씨케이","리노","주성","네패스","동진","에스티아이","케이씨","유진테크","APTC","에이피티씨"],
          "전력·중전기": ["일렉트릭","중공업","전선","LS","효성","전력","산전"],
          "2차전지": ["에코프로","엘앤에프","포스코","배터리","솔루션"],
          "조선·기계": ["조선","미포","해양","중공업","기계"],
          "바이오·헬스": ["바이오","제약","셀트리온","의료","임플란트","메디"]}
    tags = {}
    for _, r in df.iterrows():
        nm2 = str(r["name"]); t = "기타"
        for k, ws in KW.items():
            if any(w in nm2 for w in ws): t = k; break
        tags[r["code"]] = t
    df["군집"] = df["code"].map(tags)
    vc = df["군집"].value_counts()
    print(f"\n{'─'*108}\n  【업종 군집】 — 주도주가 어디에 몰려 있나")
    for k, v in vc.items():
        top3 = df[df["군집"]==k].head(3)["name"].tolist()
        print(f"    {k:<12}{v:>3}종   예: {', '.join(str(x) for x in top3)}")

    df.to_csv(os.path.join(HERE, "주도주_풀.csv"), index=False, encoding="utf-8-sig")
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    md = [f"# 주도주 풀 — {now}", "", f"- 기준월 **{last_ym}** · 통과 **{len(df)}종**",
          f"- 1·3·5년 모두 KOSPI 초과 · 시총 {MCAP_FLOOR/1e8:,.0f}억+ · 거래대금 {AMT_FLOOR/1e8:.0f}억+", "",
          "⚠️ **매수 신호가 아니라 관찰 후보다.** 다기간 지속 초과수익은 아직 검정하지 않았다.", "",
          "| # | 종목 | 현재가 | 1년초과 | 3년초과 | 5년초과 | 5년고점比 | PBR | ROE |",
          "|---|---|---:|---:|---:|---:|---:|---:|---:|"]
    for _, r in df.head(40).iterrows():
        md.append(f"| {r['rank']} | {r['name']}({r['code']}) | {r['price']:,.0f} | {r['ex1']:+.0f}% | "
                  f"{r['ex3']:+.0f}% | {r['ex5']:+.0f}% | {r['dd5']:+.0f}% | "
                  f"{(r['pbr'] if pd.notna(r['pbr']) else 0):.2f} | {(r['roe'] if pd.notna(r['roe']) else 0):.1f}% |")
    open(os.path.join(HERE, "주도주_풀.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    print(f"\n  저장: 주도주_풀.csv · 주도주_풀.md")
    print("=" * 108)


if __name__ == "__main__":
    main()
