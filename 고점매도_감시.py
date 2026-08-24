# -*- coding: utf-8 -*-
r"""고점매도_감시.py — 고점 분산(distribution) 경보 감시기 (2026-07-29 신설)

[근거 — 검정_고점매도신호.py 실측 (주봉 2013~2026 · 정제 후 고점권 표본)]
  ▸ 신호 B(고점권 + 대량 + 긴 위꼬리) 는 **−20% 급락 확률을 유의하게 높인다**
        4주  4.7% vs 3.5% (z 4.16)      8주  9.9% vs 7.6% (z 5.73)
       13주 13.7% vs 11.1% (z 5.38)    26주 20.5% vs 17.5% (z 5.01)
     → 전 구간 z ≥ 4. 급락 확률 **1.2~1.3배**.
  ▸ 신호 A(장대음봉)는 급락 예측력 **없음**(z −0.5~1.0) — 이미 빠진 뒤의 확인일 뿐.
  ▸ 대형주 한정: 4주 중앙값 −2.05% vs −1.15% (t −2.25) — 수익률도 유의하게 열위.

[해석 — 이 신호의 정확한 용도]
  평균 수익률은 거의 안 바뀐다. **꼬리(급락) 위험만 커진다.**
  → "팔아라" 신호가 아니라 **"비중을 줄여라 / 신규 진입을 멈춰라"** 신호다.

[신호 정의 — 검정과 동일. 스윕 금지]
  고점권 : 종가 ≥ 52주 고가 × 0.90
  대량   : 주간 거래량 ≥ 20주 평균 × 1.5
  위꼬리 : (고가 − max(시가,종가)) / 고가 ≥ 0.04
  몸통   : 종가/시가 − 1 ≤ +0.03  (작거나 음)
  위생   : 종가 ≥ 1,000원 · 주간 거래대금 ≥ 1억

사용: py 고점매도_감시.py                 (최근 주 전체 스캔)
      py 고점매도_감시.py --code 005930,000660   (특정 종목 이력)
      py 고점매도_감시.py --weeks 8      (최근 8주 이력 표시)
출력: 고점매도_경보.csv · 고점매도_리포트.md
⚠️ 위험 경보 도구 · 매도 추천 아님 · 투자자문 아님 · 결정과 책임은 본인.
"""
import os, sys, argparse, datetime, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

NEAR_HIGH, VOL_MULT, WICK_MIN, BODY_SMALL = 0.90, 1.50, 0.04, 0.03
BODY_DOWN, PX_FLOOR, AMT_FLOOR = -0.05, 1000, 1e8

def _find(fn):
    for d in (BASE, os.path.join(BASE, "데이터수리"), os.path.dirname(BASE), os.getcwd(),
              os.path.join(os.getcwd(), "데이터수리")):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    return None

def load():
    fr = []
    for mkt in ("KOSPI", "KOSDAQ"):
        p = _find(f"_주봉OHLCV_{mkt}_adj.csv")
        if not p: continue
        d = pd.read_csv(p, dtype={"code": str}); d["mkt"] = mkt; fr.append(d)
    if not fr: sys.exit("❌ _주봉OHLCV_*_adj.csv 를 못 찾음 (데이터수리 폴더)")
    W = pd.concat(fr); W["code"] = W["code"].str.zfill(6)
    return W.sort_values(["code", "date"]).reset_index(drop=True)

def build(W):
    g = W.groupby("code")
    W["hi52"]  = g["high"].transform(lambda s: s.rolling(52, min_periods=30).max())
    W["volma"] = g["volume"].transform(lambda s: s.rolling(20, min_periods=12).mean())
    W["body"]  = W["close"] / W["open"] - 1
    W["wick"]  = (W["high"] - W[["open", "close"]].max(axis=1)) / W["high"]
    W["amt"]   = W["close"] * W["volume"]
    W["volx"]  = W["volume"] / W["volma"]
    W["hi_pct"] = W["close"] / W["hi52"] - 1
    W["nearhi"] = W["close"] >= W["hi52"] * NEAR_HIGH
    W["clean"]  = (W["close"] >= PX_FLOOR) & (W["amt"] >= AMT_FLOOR)
    W["sigB"] = W["nearhi"] & W["clean"] & (W["volx"] >= VOL_MULT) & \
                (W["wick"] >= WICK_MIN) & (W["body"] <= BODY_SMALL)
    W["sigA"] = W["nearhi"] & W["clean"] & (W["volx"] >= VOL_MULT) & (W["body"] <= BODY_DOWN)
    return W

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--code", default=None, help="쉼표구분 종목코드 이력 조회")
    ap.add_argument("--weeks", type=int, default=1, help="최근 N주 스캔 (기본 1)")
    a = ap.parse_args()

    W = build(load())
    last = W["date"].max()
    names = {}
    p = _find("종목명_맵.csv")
    if p:
        try:
            nm = pd.read_csv(p, dtype=str)
            names = dict(zip(nm.iloc[:, 0].str.zfill(6), nm.iloc[:, 1]))
        except Exception: pass

    print("=" * 100)
    print(f" 고점 분산 경보 감시 — 주봉 기준일 {last}")
    print("=" * 100)
    print("  신호 B(대량+긴위꼬리) = −20% 급락 확률 1.2~1.3배 (z 4~6) · 신호 A(장대음봉) = 예측력 없음(참고표시)")

    if a.code:
        for c in [x.strip().zfill(6) for x in a.code.split(",")]:
            s = W[W["code"] == c].tail(16)
            if not len(s): print(f"\n  {c}: 데이터 없음"); continue
            print(f"\n  ═══ {names.get(c, c)}({c}) 최근 16주 ═══")
            print(f"    {'주':<12}{'종가':>10}{'몸통':>8}{'위꼬리':>8}{'거래량':>8}{'52주고점대비':>12}  신호")
            for _, r in s.iterrows():
                tag = "🔴 분산경보" if r["sigB"] else ("· 장대음봉(늦음)" if r["sigA"] else "")
                print(f"    {r['date']:<12}{r['close']:>10,.0f}{r['body']*100:>7.1f}%"
                      f"{r['wick']*100:>7.1f}%{r['volx']:>7.2f}x{r['hi_pct']*100:>11.1f}%  {tag}")
        return 0

    idx = sorted(W["date"].unique())[-a.weeks:]
    cur = W[W["date"].isin(idx)]
    hits = cur[cur["sigB"]].copy().sort_values(["date", "amt"], ascending=[False, False])
    print(f"\n  스캔 주: {', '.join(idx)}")
    print(f"  고점권 종목: {int(cur['nearhi'].sum()):,} · 🔴 분산경보: {len(hits):,}건")
    if len(hits):
        print(f"\n  {'종목':<20}{'주':<12}{'종가':>10}{'몸통':>8}{'위꼬리':>8}{'거래량':>8}{'고점대비':>10}{'거래대금':>10}")
        for _, r in hits.head(40).iterrows():
            print(f"  {(names.get(r['code'], '') + '(' + r['code'] + ')'):<20}{r['date']:<12}"
                  f"{r['close']:>10,.0f}{r['body']*100:>7.1f}%{r['wick']*100:>7.1f}%"
                  f"{r['volx']:>7.2f}x{r['hi_pct']*100:>9.1f}%{r['amt']/1e8:>9,.0f}억")
        if len(hits) > 40: print(f"  … 외 {len(hits)-40}건 (CSV 참조)")
    else:
        print("\n  (이번 주 분산경보 없음)")

    cols = ["code", "mkt", "date", "close", "body", "wick", "volx", "hi_pct", "amt"]
    hits[cols].to_csv(os.path.join(BASE, "고점매도_경보.csv"), index=False, encoding="utf-8-sig")

    # 보유종목 자동 점검
    hp = _find("my_holdings.csv")
    if hp:
        try:
            rows = [r for r in pd.read_csv(hp, comment="#", dtype=str).to_dict("records")
                    if r.get("code")]
            print(f"\n  ── 보유종목 점검 ──")
            for r in rows:
                c = str(r["code"]).zfill(6)
                s = W[(W["code"] == c)].tail(8)
                if not len(s): print(f"    {r.get('name', c)}: 주봉 데이터 없음"); continue
                nb = int(s["sigB"].sum()); cur_r = s.iloc[-1]
                st = "🔴 이번주 분산경보" if cur_r["sigB"] else (f"🟡 최근8주 경보 {nb}회" if nb else "🟢 경보 없음")
                print(f"    {r.get('name', c)}({c}): 종가 {cur_r['close']:,.0f} · "
                      f"52주고점대비 {cur_r['hi_pct']*100:+.1f}% · {st}")
        except Exception as e:
            print(f"    (보유 점검 실패: {e})")

    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    md = [f"# 고점 분산 경보 — {now}", "", f"- 주봉 기준일 **{last}** · 스캔 {a.weeks}주",
          f"- 신호: 고점권(52주고점 90%+) + 거래량 1.5배 + 위꼬리 4%+ + 몸통 ≤+3%",
          f"- 실측 효과: −20% 급락 확률 **1.2~1.3배** (4·8·13·26주 전부 z≥4)",
          f"- ⚠️ **매도 신호가 아니다.** 평균 수익률은 거의 안 변하고 **꼬리위험만 커진다** → 비중 축소·신규진입 중단용",
          "", f"## 경보 {len(hits)}건", "",
          "| 종목 | 주 | 종가 | 몸통 | 위꼬리 | 거래량 | 고점대비 |", "|---|---|---:|---:|---:|---:|---:|"]
    for _, r in hits.head(50).iterrows():
        md.append(f"| {names.get(r['code'], '')}({r['code']}) | {r['date']} | {r['close']:,.0f} | "
                  f"{r['body']*100:.1f}% | {r['wick']*100:.1f}% | {r['volx']:.2f}x | {r['hi_pct']*100:+.1f}% |")
    md += ["", "⚠️ 위험 경보 도구 · 매도 추천 아님 · 투자자문 아님 · 결정과 책임은 본인."]
    open(os.path.join(BASE, "고점매도_리포트.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")
    print(f"\n  저장: 고점매도_경보.csv · 고점매도_리포트.md")
    return 0

if __name__ == "__main__":
    sys.exit(main())
