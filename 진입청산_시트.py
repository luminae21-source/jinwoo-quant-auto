# -*- coding: utf-8 -*-
r"""진입청산_시트.py — 신규 진입 후보 + 진입/청산 자리 산출 (2026-07-30 신설)

╔══════════════════════════════════════════════════════════════════════════════╗
║ 오늘까지의 검정 결과만 씁니다. 검증 안 된 것은 알파로 주장하지 않습니다.      ║
╚══════════════════════════════════════════════════════════════════════════════╝

[선별에 쓰는 것 — 검증 통과분만]
  · 배당수익률        : 대형에서 가장 신뢰할 신호 (IC t 5.9 · 단 '캐리'이지 알파 아님)
  · ROE > 0           : 가치함정 회피 (IN 대형 +9.81% / 소중형 +10.88%, OOS도 같은 방향)
  · 저PBR             : 진입엣지 채택분 (소·중형 · 분위 틸트로만)
  · 신규상장 36M 제외 : 상장 0~12M은 기성 대비 연 −13~15%p (HAC t −2.7~−3.3)
  · 우선주 제외       : 배당수익률 2.09배로 고배당군 과대표집

[선별에 쓰지 않는 것 — 검정에서 죽은 것]
  ✗ 모멘텀 12-1 (롱온리 −9~−13%) ✗ 52주신고가(IN 무증거) ✗ GP수익성 ✗ 고변동성
  ✗ EPS성장(IC t 3.73인데 롱숏 −0.28% — 돈이 안 됨)
  ✗ 저변동성 극단집중 (N=5에서 −14.27%, t −2.72로 유의하게 해로움)
  → **성장주를 '고르는' 검증된 방법은 없다.** 성장 트랙은 선별이 아니라
     **사이징·청산 규율**로 다룬다 (기법 G-B·G-C).

[진입 자리]
  · 하순(월말 역순 −9~−5거래일) 진입 금지 — 소·중형 OOS p=0.0002
  · 분산 경보(고점권+대량+긴위꼬리) 발생 종목 제외 — 20일 급락 ×2.33(KOSPI)
  · 지수 방어 ON(10개월MA 이탈) 이면 신규 진입 절반으로

[청산 자리 — 트랙별]
  · 가치 : 재난 스톱 −40% · 익절 PBR≥1.0 또는 +100% (인내형)
  · 성장 : 트레일 −15% (청산규칙_규칙서 소·중형 1순위 · 파국 13분의 1)
  · 공통 : 리스크 1%/트레이드 · heat ≤6% · 1종목 ≤ lane 25%

사용: py 진입청산_시트.py --capital 10000000
      py 진입청산_시트.py --capital 10000000 --track 가치
출력: 진입청산_시트.csv · 진입청산_시트.md
⚠️ 기계적 산출 · 매수 추천 아님 · 투자자문 아님 · 결정과 책임은 본인.
"""
import os, sys, argparse, datetime, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

RISK_PCT, HEAT_CAP, STOCK_CAP = 0.01, 0.06, 0.15
TRAIL_STOP, VALUE_STOP = 0.15, 0.40
NEW_LISTING_M = 36
NEAR_HIGH, VOL_MULT, WICK_MIN, BODY_SMALL = 0.90, 2.0, 0.03, 0.02
PX_FLOOR, AMT_FLOOR = 1000, 10e8


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
    D = pd.concat(fr, ignore_index=True)
    D["code"] = D["code"].str.zfill(6)
    # 원주가 최신분 스플라이스 (청산규율_알림과 동일 원리)
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--capital", type=float, default=10_000_000)
    ap.add_argument("--track", default="all", choices=["all", "가치", "성장"])
    ap.add_argument("--topn", type=int, default=25)
    a = ap.parse_args()

    D = load_daily()
    last = D["date"].max()
    g = D.groupby("code")
    D["hi252"] = g["high"].transform(lambda s: s.rolling(252, min_periods=120).max())
    D["volma"] = g["volume"].transform(lambda s: s.rolling(60, min_periods=40).mean())
    D["ma60"]  = g["close"].transform(lambda s: s.rolling(60, min_periods=40).mean())
    D["atr"]   = g.apply(lambda x: (x["high"] - x["low"]).rolling(20, min_periods=15).mean()).reset_index(level=0, drop=True)
    D["body"]  = D["close"] / D["open"] - 1
    D["wick"]  = (D["high"] - D[["open","close"]].max(axis=1)) / D["high"]
    D["amt"]   = D["close"] * D["volume"]
    D["nearhi"] = (D["close"] >= D["hi252"]*NEAR_HIGH) & (D["close"]>=PX_FLOOR) & (D["amt"]>=AMT_FLOOR)
    D["sig"] = D["nearhi"] & (D["volume"] >= D["volma"]*VOL_MULT) & (D["wick"]>=WICK_MIN) & (D["body"]<=BODY_SMALL)
    D["sig10"] = g["sig"].transform(lambda s: s.rolling(10, min_periods=1).sum())
    cur = D[D["date"] == last].set_index("code")

    # 상장 경과월
    first = D.groupby("code")["date"].min()
    lm = pd.Timestamp(last)
    age = ((lm - pd.to_datetime(first)).dt.days / 30.44).rename("age_m")

    # 재무
    fins = []
    for m in ("KOSPI","KOSDAQ"):
        p = _find(f"종목재무_KRX_{m}.csv")
        if p: fins.append(pd.read_csv(p, dtype={"code":str}, usecols=["date","code","PBR","BPS","EPS","DIV"]))
    if not fins: sys.exit("❌ 종목재무_KRX_*.csv 없음")
    F = pd.concat(fins); F["code"] = F["code"].str.zfill(6); F["ym"] = F["date"].str[:7]
    for c in ("PBR","BPS","EPS","DIV"): F[c] = pd.to_numeric(F[c], errors="coerce")
    F = F.sort_values("ym").groupby("code").tail(1).set_index("code")
    F["roe"] = np.where(F["BPS"]>0, F["EPS"]/F["BPS"], np.nan)

    mp = _find("종목시총_30년.csv")
    MC = pd.Series(dtype=float)
    if mp:
        mc = pd.read_csv(mp, dtype={"code":str}); mc.columns=[c.strip().lstrip("﻿") for c in mc.columns]
        mc["code"]=mc["code"].str.zfill(6)
        MC = pd.to_numeric(mc.sort_values("date").groupby("code")["mcap"].last(), errors="coerce")

    # ── 종목명: 캐시 우선, 없으면 pykrx로 후보분만 조회 후 캐시에 누적
    NAME_CACHE = os.path.join(HERE, "종목명_맵.csv")
    names = {}
    if os.path.exists(NAME_CACHE):
        try:
            nm = pd.read_csv(NAME_CACHE, dtype=str)
            names = dict(zip(nm.iloc[:, 0].str.zfill(6), nm.iloc[:, 1]))
        except Exception: pass

    def fill_names(codes):
        """캐시에 없는 코드만 pykrx로 조회 → 캐시 갱신. 실패해도 진행."""
        missing = [c for c in codes if c not in names or not str(names.get(c, "")).strip()]
        if not missing: return
        try:
            from pykrx import stock
        except Exception:
            print(f"  (종목명 조회 생략 — pykrx 없음 · pip install pykrx)"); return
        got = 0
        for c in missing:
            try:
                n = stock.get_market_ticker_name(c)
                if n: names[c] = n; got += 1
            except Exception:
                continue
        if got:
            pd.DataFrame({"code": list(names.keys()), "name": list(names.values())}) \
              .to_csv(NAME_CACHE, index=False, encoding="utf-8-sig")
            print(f"  종목명 {got}건 조회·캐시 갱신 → {os.path.basename(NAME_CACHE)}")

    # 지수 방어
    ip = _find("kospi_index_daily.csv"); defense = False; idx_note = "지수파일 없음"
    if ip:
        ix = pd.read_csv(ip); ix["ym"] = pd.to_datetime(ix["Date"]).dt.strftime("%Y-%m")
        im = ix.groupby("ym")["Close"].last(); ma10 = im.rolling(10).mean()
        ym = im.index[-1]
        defense = bool(im[ym] < ma10[ym]) if pd.notna(ma10[ym]) else False
        idx_note = f"KOSPI {im[ym]:,.0f} vs 10MA {ma10[ym]:,.0f} → {'🔴방어ON(신규 절반)' if defense else '🟢방어OFF'}"

    # 하순 판정
    dts = sorted(D["date"].unique())
    md = pd.Series(dts).groupby(pd.Series(dts).str[:7]).transform(lambda s: s.rank(ascending=False))
    late = dict(zip(dts, md))
    is_late = 5 <= late.get(last, 99) <= 9

    ALLC = set(D["code"].unique())
    def is_common(c):
        return c.isdigit() and not ((not c.endswith("0")) and (c[:5]+"0") in ALLC)

    rows = []
    for c in cur.index:
        r = cur.loc[c]
        if not is_common(c): continue
        if age.get(c, 0) < NEW_LISTING_M: continue
        if r["close"] < PX_FLOOR or r["amt"] < AMT_FLOOR: continue
        if c not in F.index: continue
        f = F.loc[c]
        if not (pd.notna(f["roe"]) and f["roe"] > 0): continue           # 가치함정 회피
        if r["sig10"] >= 1: continue                                      # 분산 경보 종목 제외
        div = f["DIV"] if pd.notna(f["DIV"]) else 0
        pbr = f["PBR"] if pd.notna(f["PBR"]) and f["PBR"] > 0 else np.nan
        mcap = MC.get(c, np.nan)
        big = pd.notna(mcap) and (MC.rank(ascending=False).get(c, 9e9) <= 300)
        atr = r["atr"] if pd.notna(r["atr"]) and r["atr"] > 0 else r["close"]*0.03
        trend_ok = pd.notna(r["ma60"]) and r["close"] >= r["ma60"]        # 시계열 추세(타이밍용)

        # 트랙: 대형·고배당 → 가치 / 소중형·추세위 → 성장
        track = "가치" if big else "성장"
        if track == "가치":
            stop = r["close"] * (1 - VALUE_STOP); rule = f"재난 −{VALUE_STOP*100:.0f}% · 익절 PBR≥1.0/+100%"
            onR = VALUE_STOP
        else:
            stop = r["close"] * (1 - TRAIL_STOP);  rule = f"트레일 −{TRAIL_STOP*100:.0f}% (고점 갱신 시 상향)"
            onR = TRAIL_STOP
        w = min(RISK_PCT / onR, STOCK_CAP)
        amt_in = a.capital * w * (0.5 if defense else 1.0)
        qty = int(amt_in // r["close"])
        # 점수: 가치=배당z+B/Pz · 성장=추세+저변동 대용(여기선 추세만, 알파 주장 없음)
        score = (div if pd.notna(div) else 0) + (1/pbr if pd.notna(pbr) else 0)*2
        if track == "성장" and not trend_ok: continue                     # 성장은 추세 위에서만
        rows.append(dict(code=c, name=names.get(c, c), mkt=r["mkt"], track=track,
                         price=r["close"], score=score, div=div, pbr=pbr, roe=f["roe"]*100,
                         mcap=mcap, stop=stop, R=onR*100, weight=w*100, qty=qty,
                         amount=qty*r["close"], rule=rule, ma60_ok=trend_ok))

    df = pd.DataFrame(rows)
    if not len(df): sys.exit("후보 없음 — 조건을 만족하는 종목이 없습니다.")
    df = df.sort_values(["track","score"], ascending=[True, False])
    fill_names(list(df.head(60)["code"]))
    df["name"] = df["code"].map(lambda c: names.get(c, c))

    print("=" * 104)
    print(f" 진입·청산 시트 — 기준일 {last} · 자본 {a.capital:,.0f}원")
    print("=" * 104)
    print(f"  지수: {idx_note}")
    print(f"  하순 필터: {'🔴 오늘은 하순 — 소·중형 신규 진입 금지' if is_late else '🟢 진입 가능 구간'}")
    print(f"  적용: 신규상장 {NEW_LISTING_M}M 제외 · 우선주 제외 · ROE>0 · 분산경보 종목 제외")

    heat = 0.0; book = []
    for _, r in df.iterrows():
        if a.track != "all" and r["track"] != a.track: continue
        if is_late and r["track"] == "성장": continue
        if heat + RISK_PCT*100 > HEAT_CAP*100 + 1e-9: break
        heat += RISK_PCT*100; book.append(r)

    for tr in (["가치","성장"] if a.track == "all" else [a.track]):
        sub = [r for r in book if r["track"] == tr]
        if not sub: continue
        print(f"\n{'─'*104}\n  【{tr} 트랙】 채택 {len(sub)}종")
        print(f"  {'종목':<20}{'현재가':>10}{'손절가':>10}{'1R':>6}{'목표%':>7}{'실투입%':>8}{'수량':>6}"
              f"{'금액':>11}{'배당':>7}{'PBR':>6}{'ROE':>7}  청산규칙")
        for r in sub:
            tgt_amt = a.capital * r["weight"] / 100 * (0.5 if defense else 1.0)
            act_w = r["amount"] / a.capital * 100
            fill = r["amount"] / tgt_amt * 100 if tgt_amt > 0 else 0
            mark = " ⚠단주" if fill < 60 else ""
            nmz = (str(r['name'])[:9] + '(' + r['code'] + ')')
            print(f"  {nmz:<20}{r['price']:>10,.0f}{r['stop']:>10,.0f}"
                  f"{r['R']:>5.0f}%{r['weight']:>6.1f}%{act_w:>7.2f}%{r['qty']:>6,}{r['amount']:>11,.0f}"
                  f"{(r['div'] if pd.notna(r['div']) else 0):>6.1f}%{(r['pbr'] if pd.notna(r['pbr']) else 0):>6.2f}"
                  f"{r['roe']:>6.1f}%  {r['rule']}{mark}")

    rest = [r for _, r in df.iterrows() if r["code"] not in {b["code"] for b in book}]
    if rest:
        print(f"\n  【대기】 heat 한도 초과 — 다음 후보 {min(8,len(rest))}종")
        for r in rest[:8]:
            print(f"    {r['track']} {r['name'][:10]}({r['code']}) {r['price']:,.0f} → 손절 {r['stop']:,.0f}")

    tgt_total = sum(b["weight"] for b in book) * (0.5 if defense else 1.0)
    act_total = sum(b["amount"] for b in book) / a.capital * 100
    print(f"\n  총 heat {heat:.1f}% / 한도 {HEAT_CAP*100:.0f}%")
    print(f"  목표 투입 {tgt_total:.1f}% ({a.capital*tgt_total/100:,.0f}원) → "
          f"실투입 {act_total:.1f}% ({sum(b['amount'] for b in book):,.0f}원) · 현금 {100-act_total:.1f}%")
    if tgt_total > 0 and act_total / tgt_total < 0.8:
        dfac = 0.5 if defense else 1.0
        maxp = max((b["price"] for b in book), default=0)
        # 채움률 90%+ 를 위해선 '종목당 목표금액 ≥ 주가×10' 이어야 한다
        need = maxp * 10 / max(min(b["weight"] for b in book) / 100 * dfac, 1e-9)
        okp = a.capital * (min(b["weight"] for b in book) / 100) * dfac / 10
        print(f"  ⚠️ 단주 반올림 — 실투입이 목표의 {act_total/tgt_total*100:.0f}%에 그침")
        print(f"     원인: 종목당 목표 {a.capital*min(b['weight'] for b in book)/100*dfac:,.0f}원인데 "
              f"최고가 종목이 {maxp:,.0f}원 → 1주가 이미 목표의 {maxp/(a.capital*min(b['weight'] for b in book)/100*dfac)*100:.0f}%")
        print(f"     · 지금 자본에서 잘 채워지는 가격대: **{okp:,.0f}원 이하** (10주 이상 살 수 있는 값)")
        print(f"     · 채움률 90%+ 로 이 후보군을 다 담으려면 자본 약 {need:,.0f}원")
        print(f"     대안 ①현 상태 감수(현금이 더 남을 뿐 — 방어 ON 구간엔 나쁘지 않다)")
        print(f"          ②저가주 위주로 채운다(가격 편향 주의) ③자본이 커질 때까지 기다린다")
    print("\n  ⚠️ 집행 전 필수 3확인: ①현재가 재확인 ②ADTV 1% 주문캡 ③섹터 2종·계열 1종 한도")
    print("  ⚠️ 성장 트랙은 검증된 선별 엣지가 없다 — 사이징·청산 규율로만 다룬다.")
    print("=" * 104)

    df.to_csv(os.path.join(HERE, "진입청산_시트.csv"), index=False, encoding="utf-8-sig")
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    md_ = [f"# 진입·청산 시트 — {now}", "", f"- 기준일 **{last}** · 자본 {a.capital:,.0f}원",
           f"- {idx_note}", f"- 하순: {'🔴 진입 금지 구간' if is_late else '🟢 진입 가능'}",
           f"- 필터: 신규상장 {NEW_LISTING_M}M 제외 · 우선주 제외 · **ROE>0** · 분산경보 제외", "",
           "| 트랙 | 종목 | 현재가 | 손절가 | 1R | 비중 | 수량 | 배당 | PBR | ROE | 청산규칙 |",
           "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|"]
    for r in book:
        md_.append(f"| {r['track']} | {r['name']}({r['code']}) | {r['price']:,.0f} | {r['stop']:,.0f} | "
                   f"{r['R']:.0f}% | {r['weight']:.1f}% | {r['qty']:,} | {(r['div'] or 0):.1f}% | "
                   f"{(r['pbr'] if pd.notna(r['pbr']) else 0):.2f} | {r['roe']:.1f}% | {r['rule']} |")
    md_ += ["", f"총 heat {heat:.1f}% · 투입 {sum(b['weight'] for b in book):.0f}%", "",
            "⚠️ 기계적 산출 · 매수 추천 아님 · 투자자문 아님 · 결정과 책임은 본인."]
    open(os.path.join(HERE, "진입청산_시트.md"), "w", encoding="utf-8").write("\n".join(md_) + "\n")
    print(f"\n  저장: 진입청산_시트.csv · 진입청산_시트.md")


if __name__ == "__main__":
    main()
