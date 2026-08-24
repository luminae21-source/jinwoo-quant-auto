# -*- coding: utf-8 -*-
r"""청산규율_감시.py — 통합 고점매도 경보 · 일봉+수급+시장폭 (2026-07-30 신설)

╔══════════════════════════════════════════════════════════════════════════════╗
║ 이 도구가 푸는 문제: "매수는 잘하는데 수익을 다 까먹는다"                    ║
║ → 그건 진입 문제가 아니라 **청산 규율** 문제다. 이 도구는 '언제 줄일지'만 답한다. ║
╚══════════════════════════════════════════════════════════════════════════════╝

[3층 경보 — 전부 실측 검정 통과]
  1층 일봉 분산일  : 고점권 + 거래량 2배 + 위꼬리 3%+ + 몸통 ≤+2%
                    → 20일 내 −20% 급락 확률 **×2.31** (z 15.49) · 40일 ×1.91 (z 15.99)
                    → 주봉 대비 평균 **2.07 거래일 선행**
  2층 수급 확인    : 외국인·기관 **동시** 순매도
                    → 주봉 신호와 결합 시 8주 급락 ×1.26 → **×1.64** (z 4.36)
  3층 시장 폭      : 고점권 종목수가 13주 평균의 70% 이하인데 지수는 고점권
                    → 2026 꼭지에서 05-15·05-22·05-29·06-19 4회 점등 (n=8로 통계 미확정 · 참고용)

[행동 규칙 — 단계별 축소. "판다/안 판다"가 아니라 "얼마나 줄이나"]
  🟡 1단계 (일봉 분산일 1회)          : 신규 진입 중단 · 추가 매수 금지
  🟠 2단계 (분산일 + 수급 동시매도)    : 비중 1/3 축소
  🔴 3단계 (10일 내 분산일 2회+)      : 비중 1/2 이하로 · 트레일 −15% 강제
  ⚫ 4단계 (3단계 + 시장폭 다이버전스) : 재량 트랙 신규 전면 중단

⚠️ 확률 도구다. 10번 울리면 대략 2~3번 크게 다치고 나머지는 별일 없다.
   **그 2~3번이 계좌를 죽이기 때문에** 매번 줄이는 것이다. 매도 추천 아님·투자자문 아님.

사용: py 청산규율_감시.py              (보유종목 + 시장 상태)
      py 청산규율_감시.py --scan       (전 종목 스캔)
      py 청산규율_감시.py --code 005930,000660
"""
import os, sys, argparse, datetime, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

# 검정에 쓴 값 그대로 — 스윕 금지
NEAR_HIGH, VOL_MULT, WICK_MIN, BODY_SMALL = 0.90, 2.0, 0.03, 0.02
PX_FLOOR, AMT_FLOOR = 1000, 10e8
BREADTH_REL = 0.70

def _find(fn):
    for d in (BASE, os.path.join(BASE, "데이터수리"), os.path.dirname(BASE), os.getcwd(),
              os.path.join(os.getcwd(), "데이터수리")):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    return None

def load_daily():
    fr = []
    for m in ("KOSPI", "KOSDAQ"):
        p = _find(f"_일봉OHLCV_{m}_adj.csv")
        if p:
            d = pd.read_csv(p, dtype={"code": str}); d["mkt"] = m; fr.append(d)
    if not fr: sys.exit("❌ _일봉OHLCV_*_adj.csv 없음 (데이터수리 폴더)")
    D = pd.concat(fr); D["code"] = D["code"].str.zfill(6)
    return D.sort_values(["code", "date"]).reset_index(drop=True)

def build(D):
    g = D.groupby("code")
    D["hi252"] = g["high"].transform(lambda s: s.rolling(252, min_periods=120).max())
    D["volma"] = g["volume"].transform(lambda s: s.rolling(60, min_periods=40).mean())
    D["body"]  = D["close"] / D["open"] - 1
    D["wick"]  = (D["high"] - D[["open", "close"]].max(axis=1)) / D["high"]
    D["amt"]   = D["close"] * D["volume"]
    D["volx"]  = D["volume"] / D["volma"]
    D["hi_pct"] = D["close"] / D["hi252"] - 1
    D["clean"] = (D["close"] >= PX_FLOOR) & (D["amt"] >= AMT_FLOOR)
    D["nearhi"] = (D["close"] >= D["hi252"] * NEAR_HIGH) & D["clean"] & D["hi252"].notna() & D["volma"].notna()
    D["sig"] = D["nearhi"] & (D["volx"] >= VOL_MULT) & (D["wick"] >= WICK_MIN) & (D["body"] <= BODY_SMALL)
    D["sig10"] = D.groupby("code")["sig"].transform(lambda s: s.rolling(10, min_periods=1).sum())
    return D

def flow_map():
    """최근 주 외국인·기관 동시 순매도 종목 집합"""
    out = set(); wk = None
    for m in ("KOSPI", "KOSDAQ"):
        p = _find(f"flow_ext_weekly_{m}.csv")
        if not p: continue
        f = pd.read_csv(p, dtype={"code": str})
        f.columns = [c.strip().lstrip("﻿") for c in f.columns]
        f["code"] = f["code"].str.zfill(6)
        last = f["date"].max(); wk = last if wk is None else max(wk, last)
        s = f[f["date"] == last]
        out |= set(s[(pd.to_numeric(s["foreign_net"], errors="coerce") < 0) &
                     (pd.to_numeric(s["inst_net"], errors="coerce") < 0)]["code"])
    return out, wk

def market_breadth(D):
    b = D[D["nearhi"]].groupby("date").size().rename("n_high").reset_index()
    b = b[b["n_high"] >= 10].copy()
    b["ma"] = b["n_high"].rolling(65, min_periods=40).mean()
    b["rel"] = b["n_high"] / b["ma"]
    return b

def stage(sig, sig10, smart, div):
    if sig10 >= 2 and div:  return "⚫ 4단계", "재량 신규 전면중단 · 비중 1/2 이하"
    if sig10 >= 2:          return "🔴 3단계", "비중 1/2 이하 · 트레일 −15% 강제"
    if sig and smart:       return "🟠 2단계", "비중 1/3 축소"
    if sig:                 return "🟡 1단계", "신규진입·추가매수 중단"
    return "🟢", ""

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--scan", action="store_true")
    ap.add_argument("--code", default=None)
    ap.add_argument("--days", type=int, default=5)
    a = ap.parse_args()

    D = build(load_daily())
    last = D["date"].max()
    smart_set, fwk = flow_map()
    B = market_breadth(D)
    cur_b = B[B["date"] <= last].tail(1)
    rel = float(cur_b["rel"].iloc[0]) if len(cur_b) and pd.notna(cur_b["rel"].iloc[0]) else np.nan
    nh = int(cur_b["n_high"].iloc[0]) if len(cur_b) else 0
    div = (rel <= BREADTH_REL) if np.isfinite(rel) else False

    print("=" * 100)
    print(f" 청산 규율 감시 — 일봉 기준일 {last}   (수급 최신주 {fwk})")
    print("=" * 100)
    print(f"  [시장 폭] 고점권 {nh}종목 · 65일평균 대비 {rel:.2f}배 → "
          f"{'🔴 다이버전스(폭 위축)' if div else '🟢 정상'}")
    print(f"  [수급] 최근주 외국인·기관 동시 순매도 종목 {len(smart_set):,}개")

    names = {}
    p = _find("종목명_맵.csv")
    if p:
        try:
            nm = pd.read_csv(p, dtype=str); names = dict(zip(nm.iloc[:, 0].str.zfill(6), nm.iloc[:, 1]))
        except Exception: pass

    def show(codes, title):
        print(f"\n{'─'*100}\n  {title}")
        print(f"  {'종목':<20}{'종가':>10}{'52주고점比':>11}{'거래량':>8}{'위꼬리':>8}"
              f"{'10일분산':>9}{'수급':>7}  단계 / 조치")
        for c in codes:
            s = D[D["code"] == c].tail(1)
            if not len(s): print(f"  {c}: 데이터 없음"); continue
            r = s.iloc[0]
            sm = c in smart_set
            st, act = stage(bool(r["sig"]), int(r["sig10"]), sm, div)
            print(f"  {(names.get(c,'')+'('+c+')'):<20}{r['close']:>10,.0f}{r['hi_pct']*100:>10.1f}%"
                  f"{r['volx']:>7.2f}x{r['wick']*100:>7.1f}%{int(r['sig10']):>8}회"
                  f"{('🔴' if sm else '·'):>6}  {st} {act}")

    if a.code:
        show([x.strip().zfill(6) for x in a.code.split(",")], "지정 종목")
        return 0

    hp = _find("my_holdings.csv")
    if hp:
        try:
            rows = pd.read_csv(hp, comment="#", dtype=str).dropna(subset=["code"])
            show([str(c).zfill(6) for c in rows["code"]], "보유종목")
        except Exception as e:
            print(f"  보유 로드 실패: {e}")

    if a.scan:
        recent = D[D["date"] >= sorted(D["date"].unique())[-a.days]]
        hits = recent[recent["sig"]].sort_values(["date", "amt"], ascending=[False, False])
        print(f"\n{'─'*100}\n  최근 {a.days}거래일 분산일 발생: {len(hits):,}건")
        if len(hits):
            print(f"  {'종목':<20}{'일자':<12}{'종가':>10}{'고점比':>9}{'거래량':>8}{'위꼬리':>8}{'수급':>7}")
            for _, r in hits.head(40).iterrows():
                print(f"  {(names.get(r['code'],'')+'('+r['code']+')'):<20}{r['date']:<12}"
                      f"{r['close']:>10,.0f}{r['hi_pct']*100:>8.1f}%{r['volx']:>7.2f}x"
                      f"{r['wick']*100:>7.1f}%{('🔴' if r['code'] in smart_set else '·'):>6}")
            hits.to_csv(os.path.join(BASE, "청산규율_경보.csv"), index=False, encoding="utf-8-sig")
            print(f"\n  저장: 청산규율_경보.csv")

    print("\n" + "=" * 100)
    print("  단계별 조치: 🟡1 신규중단 · 🟠2 1/3축소 · 🔴3 1/2이하+트레일강제 · ⚫4 재량 전면중단")
    print("  ⚠️ 확률 도구 — 10번 중 2~3번 크게 다친다. 그 2~3번 때문에 매번 줄인다.")
    print("=" * 100)
    return 0

if __name__ == "__main__":
    sys.exit(main())
