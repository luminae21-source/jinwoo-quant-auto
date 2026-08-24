# -*- coding: utf-8 -*-
r"""마틴게일존_스캔.py — 60일선이 240일선 아래에서 수렴하는 자리 (2026-08-01 신설)

[찾는 것]
  ① MA60 < MA240                     — 장기 추세 아래로 내려온 상태
  ② |MA60/MA240 − 1| ≤ GAP           — 두 선이 거의 붙었다 (기본 5%)
  ③ 진짜 수렴                        — 20일 전에도 이미 아래였고(gap<0), 간격이 좁혀졌다
                                       ※ 20일 전 +20% → 지금 −0.1% 는 수렴이 아니라 **하향 돌파 중**
  ④ 체류 ≥ N일                       — 오늘 막 내려온 종목 제외 (기본 10일)
  ⑤ MA240·MA60 기울기가 급락 아님     — 아직 무너지는 중이면 바닥이 아니다

  이평선이 붙는다 = 최근 가격이 장기 평균과 같아졌다 = **한쪽으로 쏠린 힘이 소진됐다**.
  여기서 위로 벌어지면 추세 전환, 아래로 벌어지면 하락 재개다. 방향은 아직 안 정해졌다.

[왜 '존'이지 '신호'가 아닌가]
  이 자리는 **분할로 모아가는 구간**이지 한 번에 지르는 자리가 아니다.
  수렴은 언제 풀릴지 말해주지 않는다. 몇 달 옆으로 갈 수도 있다.

[⚠️ 마틴게일에 대해 — 한 번만 말한다]
  진짜 마틴게일(질 때마다 두 배)은 계좌를 죽인다. 수학적으로, 예외 없이.
  자본이 유한하고 종목은 0으로 갈 수 있기 때문이다.
  여기서 쓰는 건 **상한이 있는 분할매수**다 — 총 예산이 먼저 정해지고, 그 안에서만 나눈다.
  진우_통합한도.json 의 1종목 캡·Σheat 6%·손절이 그 상한이다. 그걸 넘기는 순간 다른 게임이 된다.

[⚠️ 이 스크린은 아직 검정되지 않았다]
  이 프로젝트에서 '좋아 보이는 조건'은 네 번 검정해 세 번 죽었다.
  그러니 이건 **관찰 후보 목록**이다. 매수 신호가 아니다.
  검정하려면: 과거 각 시점에서 이 조건을 만족한 종목의 전방 수익률을 유니버스와 비교
  (`검정_마틴게일존.py` — 사전등록 후 별도 작성)

사용: py 마틴게일존_스캔.py
      py 마틴게일존_스캔.py --gap 3 --stay 20        (더 타이트하게)
      py 마틴게일존_스캔.py --stay 0 --amt 10        (넓게 훑어보기)
      py 마틴게일존_스캔.py --code 353200,000660      (특정 종목이 존에 있는지만 확인)
출력: 마틴게일존_YYYYMMDD.csv
⚠️ 기계적 산출 · 매수 추천 아님 · 결정과 책임은 본인.
"""
import os, sys, argparse, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

PX_FLOOR, AMT_FLOOR = 1000, 10e8
NEAR_HIGH, VOL_MULT, WICK_MIN, BODY_SMALL = 0.90, 2.0, 0.03, 0.02


def w(t, n, right=False):
    """한글은 터미널에서 2칸을 먹는다. 표시 폭 기준으로 맞춘다."""
    import unicodedata
    t = str(t)
    dw = sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in t)
    while dw > n:
        t = t[:-1]
        dw = sum(2 if unicodedata.east_asian_width(ch) in "WF" else 1 for ch in t)
    pad = " " * (n - dw)
    return pad + t if right else t + pad


def _find(fn):
    for d in (HERE, os.path.join(HERE, "데이터수리"), os.path.dirname(HERE), os.getcwd()):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    return None


def load():
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


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--gap", type=float, default=5.0, help="MA60·MA240 간격 상한 %% (기본 5)")
    ap.add_argument("--top", type=int, default=30)
    ap.add_argument("--code", default=None, help="특정 종목만 진단")
    ap.add_argument("--stay", type=int, default=10,
                    help="존 최소 체류일수 (기본 10) — 갓 뚫고 내려가는 중인 종목을 뺀다")
    ap.add_argument("--amt", type=float, default=30.0, help="20일 평균 거래대금 하한 억 (기본 30)")
    ap.add_argument("--all", action="store_true", help="수렴·기울기 조건 없이 간격만 본다")
    a = ap.parse_args()
    G = a.gap / 100.0

    D = load(); last = D["date"].max()
    print("=" * 104)
    print(f" 마틴게일 존 — {last} · MA60<MA240 · 간격 ≤{a.gap:.1f}% · 체류 ≥{a.stay}일 · 대금 ≥{a.amt:.0f}억")
    print("=" * 104)

    names = {}
    np_ = _find("종목명_맵.csv")
    if np_:
        try:
            nm = pd.read_csv(np_, dtype=str)
            names = dict(zip(nm.iloc[:, 0].str.zfill(6), nm.iloc[:, 1]))
        except Exception: pass
    sec = {}
    for f in ("liquidity_sector.csv", "kosdaq_industry.csv"):
        p = _find(f)
        if not p: continue
        try:
            d = pd.read_csv(p, dtype=str); d.columns = [x.strip().lstrip("﻿") for x in d.columns]
            if {"code", "sector"}.issubset(d.columns):
                sec.update(dict(zip(d["code"].str.zfill(6), d["sector"].astype(str))))
        except Exception: pass

    picks = [x.strip().zfill(6) for x in a.code.split(",")] if a.code else None
    rows, diag = [], []
    for c, g in D.groupby("code", sort=False):
        if picks and c not in picks: continue
        if len(g) < 260:
            if picks: diag.append((c, f"일봉 {len(g)}개 — 240일선 계산 불가"))
            continue
        cl = g["close"].values; hi = g["high"].values; lo = g["low"].values
        vol = g["volume"].values
        px = cl[-1]
        if px < PX_FLOOR:
            if picks: diag.append((c, f"종가 {px:,.0f}원 < {PX_FLOOR:,}"));
            continue
        amt20 = float(np.mean(cl[-20:] * vol[-20:]))
        if amt20 < a.amt * 1e8 and not picks:
            continue

        tr = np.maximum(hi[1:] - lo[1:], np.maximum(np.abs(hi[1:] - cl[:-1]),
                                                    np.abs(lo[1:] - cl[:-1])))
        atr = float(np.mean(tr[-20:]))
        hi5 = float(np.max(hi[-1250:])) if len(hi) >= 1250 else float(np.max(hi))

        ma60  = float(np.mean(cl[-60:]));   ma240  = float(np.mean(cl[-240:]))
        ma60p = float(np.mean(cl[-80:-20])); ma240p = float(np.mean(cl[-260:-20]))
        gap   = ma60 / ma240 - 1
        gap_p = ma60p / ma240p - 1
        slope240 = ma240 / ma240p - 1                     # 20일간 장기선 기울기
        slope60  = ma60 / ma60p - 1                       # 20일간 단기선 기울기

        # 존 체류일수 — 조건(아래 & 간격 이내)을 연속으로 만족한 날 수.
        # 0일이면 '오늘 막 내려온' 것이다. 바닥이 아니라 붕괴 진행 중일 수 있다.
        stay = 0
        for k in range(1, min(160, len(cl) - 240)):
            m6 = np.mean(cl[-60 - k:-k]); m24 = np.mean(cl[-240 - k:-k])
            if m24 and m6 < m24 and abs(m6 / m24 - 1) <= G: stay += 1
            else: break

        # ── 수렴의 정의를 고친다.
        # |gap|이 줄었다는 것만으로는 부족하다. 20일 전 +20%였다가 지금 −0.1%면
        # 그건 '붙은' 게 아니라 **20일 만에 뚫고 내려간 것**이다 — 정반대 상황.
        # 진짜 수렴 = 이미 아래에 있었고(gap_p < 0), 그 상태로 간격이 좁혀졌다.
        ok_below = gap < 0
        ok_gap   = abs(gap) <= G
        ok_conv  = (gap_p < 0 and abs(gap) < abs(gap_p)) or a.all
        ok_stay  = (stay >= a.stay) or a.all
        ok_slope = (slope240 >= -0.05) or a.all           # 장기선이 20일에 −5%보다 더 빠지면 제외
        ok_s60   = (slope60 >= -0.08) or a.all            # 단기선이 급락 중이면 바닥 아님
        ok_atr   = (atr / px <= 0.15) or a.all            # ATR 15% 초과는 정상 종목이 아니다

        if picks:
            why = []
            if not ok_below: why.append(f"MA60가 MA240 위 ({gap:+.1%})")
            if not ok_gap:   why.append(f"간격 {abs(gap):.1%} > {a.gap:.1f}%")
            if gap_p >= 0:   why.append(f"20일 전엔 MA60가 위({gap_p:+.1%}) — 수렴이 아니라 하향 돌파 진행")
            elif abs(gap) >= abs(gap_p): why.append(f"확산 중 ({abs(gap_p):.1%} → {abs(gap):.1%})")
            if stay < a.stay: why.append(f"체류 {stay}일 < {a.stay}일 — 자리 잡기 전")
            if slope240 < -0.05: why.append(f"MA240 20일 {slope240:+.1%} — 장기선 급락")
            if slope60 < -0.08:  why.append(f"MA60 20일 {slope60:+.1%} — 단기선 급락")
            pos = f"현재가/MA240 {px/ma240-1:+.0%}"
            diag.append((c, ("존 안에 있음 · " + pos) if not why
                         else " · ".join(why) + f"  [{pos}]"))
        if not (ok_below and ok_gap and ok_conv and ok_stay and ok_slope
                and ok_s60 and ok_atr) and not picks:
            continue
        if picks and not (ok_below and ok_gap):
            continue

        # 고점 대량매도 신호 (최근 10일)
        hi252 = pd.Series(hi).rolling(252, min_periods=120).max().values
        volma = pd.Series(vol).rolling(60, min_periods=40).mean().values
        op = g["open"].values
        body = cl / op - 1
        wick = (hi - np.maximum(op, cl)) / np.where(hi > 0, hi, 1)
        sig = ((cl >= hi252 * NEAR_HIGH) & (vol >= volma * VOL_MULT)
               & (wick >= WICK_MIN) & (body <= BODY_SMALL))
        sig10 = int(np.nansum(sig[-10:]))

        rows.append(dict(code=c, name=names.get(c, c), mkt=g["mkt"].iloc[-1],
                         price=px, ma60=ma60, ma240=ma240, gap=gap, gap_prev=gap_p,
                         conv=bool(gap_p < 0 and abs(gap) < abs(gap_p)),
                         slope240=slope240, slope60=slope60, stay=stay,
                         px_ma60=px / ma60 - 1, px_ma240=px / ma240 - 1,
                         dd5=px / hi5 - 1, atr=atr, atr_pct=atr / px,
                         amt20=amt20, sig10=sig10, sector=sec.get(c, "미분류")))

    if picks:
        print("\n[지정 종목 진단]")
        for c, w in diag:
            print(f"  · {names.get(c, c)}({c}) — {w}")
        if not rows:
            print("\n존 조건(MA60<MA240 & 간격 이내)에 드는 종목 없음")
            return

    if not rows:
        print(f"\n조건 만족 종목 없음 — --gap 을 넓히거나 --all 로 수렴·기울기 조건을 빼볼 것")
        return

    R = pd.DataFrame(rows)
    R = R.sort_values(["stay", "gap"], ascending=[False, False])   # 오래 자리 잡은 순
    out = os.path.join(HERE, f"마틴게일존_{last.replace('-','')}.csv")
    R.to_csv(out, index=False, encoding="utf-8-sig")

    show = R[R["sig10"] == 0].head(a.top)
    print(f"\n조건 만족 {len(R)}종 · 고점대량매도 신호 제외 후 {int((R['sig10']==0).sum())}종\n")
    print(w("코드", 7, 1) + " " + w("종목명", 14) + w("현재가", 11, 1) + w("MA60", 11, 1)
          + w("MA240", 11, 1) + w("간격", 8, 1) + w("20일전", 8, 1) + w("240기울기", 10, 1)
          + w("60기울기", 10, 1) + w("체류", 8, 1) + w("5년고점", 9, 1) + w("ATR%", 7, 1)
          + w("대금", 9, 1))
    print("-" * 100)
    for _, r in show.iterrows():
        print(w(r['code'], 7, 1) + " " + w(r['name'], 14)
              + w(f"{r['price']:,.0f}", 11, 1) + w(f"{r['ma60']:,.0f}", 11, 1)
              + w(f"{r['ma240']:,.0f}", 11, 1) + w(f"{r['gap']:.1%}", 8, 1)
              + w(f"{r['gap_prev']:.1%}", 8, 1) + w(f"{r['slope240']:.1%}", 10, 1)
              + w(f"{r['slope60']:.1%}", 10, 1) + w(f"{r['stay']}일", 8, 1)
              + w(f"{r['dd5']:.0%}", 9, 1) + w(f"{r['atr_pct']:.1%}", 7, 1)
              + w(f"{r['amt20']/1e8:.0f}억", 9, 1))
    print("-" * 100)

    excl = R[R["sig10"] > 0]
    if len(excl):
        print(f"\n🔴 고점대량매도 신호로 제외 {len(excl)}종: "
              + ", ".join(f"{x}" for x in excl["name"].head(10)))

    top = R["sector"].value_counts().head(4)
    print(f"\n섹터 쏠림: " + " · ".join(f"{s} {n}종({n/len(R)*100:.0f}%)" for s, n in top.items()))
    if top.iloc[0] / len(R) > 0.35:
        print(f"  ⚠️ {top.index[0]}가 {top.iloc[0]/len(R)*100:.0f}% — 섹터캡 35% 초과."
              f" 여기서 여러 종목 담으면 분산이 아니라 한 종목을 여러 번 사는 것이다.")

    print(f"\n저장: {os.path.basename(out)}")
    print("\n다음 — 자리를 잡으려면:")
    print(f"  py 매매카드.py --code <코드들> --track 성장 --capital 10000000 --force")
    print("\n⚠️ 이 스크린은 **아직 검정되지 않았다.** 관찰 후보지 매수 신호가 아니다.")
    print("   그리고 여기는 '존'이다 — 한 번에 지르는 자리가 아니라 상한 안에서 나눠 모으는 자리.")


if __name__ == "__main__":
    main()
