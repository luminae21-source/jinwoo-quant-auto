# -*- coding: utf-8 -*-
r"""급등주_수집.py — 상한가·급등 종목과 '오르기 전' 상태 (2026-07-31 신설)

[무엇을 답하나]
  ① 기준일에 **상한가(+29% 이상)** 간 종목, **+20% 이상** 오른 종목 전부
  ② 그 종목들의 **직전 2영업일(D-1, D-2) 가격·재무** — 즉 **터지기 전 모습**
  ③ 눌림 지표 — 52주/5년 고점 대비, 60일선 대비, 거래대금 급증 배수

[왜 D-1·D-2인가]
  상한가 당일 재무를 보는 건 사후확인이다. 알고 싶은 건 **오르기 전에 어떻게 생겼었나**다.
  그래서 D-1(7/30)·D-2(7/29) 시점의 PER·PBR·EPS·BPS·배당과 종가를 같이 붙인다.

[주의]
  · 신규상장 첫날은 가격제한폭이 다르다(공모가 기준 60~400%) → `신규상장` 플래그로 표시
  · 등락률 29% 이상을 상한가로 본다(호가 단위 때문에 정확히 30%가 아닐 수 있음)
  · 재무(PER/PBR 등)는 KRX 스냅샷이라 **주가가 변하면 매일 바뀐다**. EPS·BPS는 분기 공시 때만 변한다.

사용: py 급등주_수집.py                      (마지막 영업일 기준)
      py 급등주_수집.py --date 20260731
      py 급등주_수집.py --date 20260731 --min 20     (기준 등락률 변경)
출력: 급등주_YYYYMMDD.csv · 급등주_YYYYMMDD_3일치.csv
⚠️ 사실 수집 도구. 매수 추천 아님.
"""
import os, sys, argparse, datetime, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

LIMIT_UP = 29.0          # 상한가 판정 하한 (제도 +30%, 호가 단위로 29.x)
MKTS = ("KOSPI", "KOSDAQ")


def _find(fn):
    for d in (HERE, os.path.join(HERE, "데이터수리"), os.path.dirname(HERE), os.getcwd()):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="기준일 YYYYMMDD (기본: 마지막 영업일)")
    ap.add_argument("--min", type=float, default=20.0, help="수집 하한 등락률 (기본 20)")
    ap.add_argument("--back", type=int, default=2, help="직전 며칠까지 붙일지 (기본 2 = D-1, D-2)")
    a = ap.parse_args()

    try:
        from pykrx import stock
    except Exception:
        sys.exit("pykrx 없음 —  pip install pykrx  후 다시 실행")

    # ── 기준일과 직전 영업일들
    end = a.date or datetime.date.today().strftime("%Y%m%d")
    start = (datetime.datetime.strptime(end, "%Y%m%d") - datetime.timedelta(days=20)).strftime("%Y%m%d")
    try:
        bdays = [d.strftime("%Y%m%d") for d in
                 stock.get_index_ohlcv_by_date(start, end, "1001").index]
    except Exception:
        bdays = []
    if not bdays:      # 지수 조회 실패 시 개별 종목으로 영업일 추정
        try:
            s = stock.get_market_ohlcv_by_date(start, end, "005930")
            bdays = [d.strftime("%Y%m%d") for d in s.index]
        except Exception:
            sys.exit("영업일 확인 실패 — 날짜를 --date 로 직접 지정해봐")
    if end not in bdays:
        print(f"⚠️ {end}는 영업일이 아니거나 데이터 없음 → 마지막 영업일 {bdays[-1]} 로 진행")
        end = bdays[-1]
    i = bdays.index(end)
    days = bdays[max(0, i - a.back): i + 1]          # [D-2, D-1, D]
    print("=" * 96)
    print(f" 급등주 수집 — 기준일 {end} · 직전일 {', '.join(days[:-1])}")
    print("=" * 96)

    # ── ① 기준일 등락률
    chg = []
    for m in MKTS:
        try:
            d = stock.get_market_price_change_by_ticker(end, end, market=m)
            d = d.reset_index(); d.columns = [str(c) for c in d.columns]
            tick = d.columns[0]
            d = d.rename(columns={tick: "code"})
            d["code"] = d["code"].astype(str).str.zfill(6); d["mkt"] = m
            chg.append(d)
        except Exception as e:
            print(f"  [{m}] 등락률 조회 실패: {str(e)[:80]}")
    if not chg: sys.exit("등락률 데이터 없음")
    C = pd.concat(chg, ignore_index=True)
    rcol = next((c for c in C.columns if "등락" in c), None)
    ncol = next((c for c in C.columns if "종목명" in c), None)
    if rcol is None: sys.exit(f"등락률 컬럼 없음: {C.columns.tolist()}")
    C[rcol] = pd.to_numeric(C[rcol], errors="coerce")
    print(f"전 종목 {len(C):,} · 상승 {int((C[rcol] > 0).sum()):,} · 하락 {int((C[rcol] < 0).sum()):,}")

    H = C[C[rcol] >= a.min].copy().sort_values(rcol, ascending=False)
    H["구분"] = np.where(H[rcol] >= LIMIT_UP, "상한가", f"+{a.min:.0f}%↑")
    print(f"\n상한가(≥{LIMIT_UP}%) {int((H[rcol] >= LIMIT_UP).sum())}종 · "
          f"+{a.min:.0f}% 이상 {len(H)}종")
    if len(H) == 0:
        print("해당 종목 없음"); return 0
    codes = H["code"].tolist()

    # ── ② 3일치 가격·재무·시총 (일자별 1콜 × 시장 2)
    frames = []
    for d in days:
        for m in MKTS:
            try:
                o = stock.get_market_ohlcv_by_ticker(d, market=m)
                f = stock.get_market_fundamental_by_ticker(d, market=m)
                cap = stock.get_market_cap_by_ticker(d, market=m)
            except Exception as e:
                print(f"  [{d} {m}] 조회 실패: {str(e)[:70]}"); continue
            t = o.join(f, how="outer").join(cap[[c for c in cap.columns
                                                 if c not in o.columns and c not in f.columns]],
                                            how="outer")
            t = t.reset_index(); t.columns = [str(c) for c in t.columns]
            t = t.rename(columns={t.columns[0]: "code"})
            t["code"] = t["code"].astype(str).str.zfill(6)
            t["date"] = d; t["mkt"] = m
            frames.append(t[t["code"].isin(codes)])
        print(f"  {d} 수집 완료")
    if not frames: sys.exit("일자별 데이터 없음")
    D3 = pd.concat(frames, ignore_index=True)
    if ncol:
        D3 = D3.merge(H[["code", ncol]].rename(columns={ncol: "종목명"}), on="code", how="left")

    # ── ③ 눌림 지표 (로컬 일봉이 있으면)
    PULL = {}
    fr = []
    for m in MKTS:
        p = _find(f"_일봉OHLCV_{m}_adj.csv")
        if p:
            try:
                x = pd.read_csv(p, dtype={"code": str}); x["code"] = x["code"].str.zfill(6)
                fr.append(x[x["code"].isin(codes)])
            except Exception: pass
    if fr:
        L = pd.concat(fr, ignore_index=True).sort_values(["code", "date"])
        cut = f"{end[:4]}-{end[4:6]}-{end[6:]}"
        L = L[L["date"] < cut]                       # 급등일 이전만 = 사전 상태
        for c, g in L.groupby("code"):
            if len(g) < 60: continue
            px = g["close"].iloc[-1]
            hi52 = g["high"].tail(252).max(); hi5y = g["high"].tail(1250).max()
            ma60 = g["close"].tail(60).mean()
            amt = (g["close"] * g["volume"])
            PULL[c] = dict(전일종가=px,
                           고점52주比=px / hi52 - 1 if hi52 else np.nan,
                           고점5년比=px / hi5y - 1 if hi5y else np.nan,
                           MA60比=px / ma60 - 1 if ma60 else np.nan,
                           평균거래대금20일=amt.tail(20).mean())
        print(f"  눌림 지표: 로컬 일봉으로 {len(PULL)}종 계산")
    else:
        print("  ⚠️ _일봉OHLCV_*_adj.csv 없음 → 눌림 지표 생략")

    # ── ④ 요약 표 (기준일 행 + D-1 재무)
    dD, dP = days[-1], (days[-2] if len(days) > 1 else days[-1])
    cur = D3[D3["date"] == dD].set_index("code")
    prv = D3[D3["date"] == dP].set_index("code")
    rows = []
    for c in codes:
        h = H[H["code"] == c].iloc[0]
        r = {"code": c, "종목명": (h[ncol] if ncol else c), "시장": h["mkt"],
             "구분": h["구분"], f"등락률_{dD}": h[rcol]}
        for src, tag in ((cur, dD), (prv, dP)):
            if c in src.index:
                s = src.loc[c]
                if isinstance(s, pd.DataFrame): s = s.iloc[0]
                for k, out in (("종가", "종가"), ("거래량", "거래량"), ("거래대금", "거래대금"),
                               ("PER", "PER"), ("PBR", "PBR"), ("EPS", "EPS"),
                               ("BPS", "BPS"), ("DIV", "배당%"), ("시가총액", "시총")):
                    if k in s.index: r[f"{out}_{tag}"] = s[k]
        p = PULL.get(c, {})
        r["고점52주比"] = p.get("고점52주比"); r["고점5년比"] = p.get("고점5년比")
        r["MA60比"] = p.get("MA60比")
        av = p.get("평균거래대금20일")
        td = r.get(f"거래대금_{dD}")
        r["거래대금배수"] = (td / av) if (av and td and np.isfinite(av) and av > 0) else np.nan
        r["신규상장"] = "Y" if (c not in PULL and fr) else ""
        rows.append(r)
    S = pd.DataFrame(rows)

    # ── 이력 누적 — 하루치로는 아무것도 못 판단한다. 며칠 쌓아야 사전등록·검정이 가능하다.
    hist_p = os.path.join(HERE, "급등이력.csv")
    Hh = S.copy(); Hh.insert(0, "기준일", dD)
    if os.path.exists(hist_p):
        try:
            old = pd.read_csv(hist_p, dtype={"code": str, "기준일": str})
            Hh = pd.concat([old[old["기준일"] != dD], Hh], ignore_index=True)
        except Exception: pass
    Hh.to_csv(hist_p, index=False, encoding="utf-8-sig")
    nday = Hh["기준일"].nunique()
    print(f"\n이력 누적: 급등이력.csv · {nday}일치 · 총 {len(Hh):,}행"
          + ("" if nday >= 20 else f"  (사전등록 검정까지 최소 20일 — {20-nday}일 남음)"))

    out1 = os.path.join(HERE, f"급등주_{dD}.csv")
    out2 = os.path.join(HERE, f"급등주_{dD}_3일치.csv")
    S.to_csv(out1, index=False, encoding="utf-8-sig")
    D3.to_csv(out2, index=False, encoding="utf-8-sig")

    # ── 출력
    def show(sub, title):
        if len(sub) == 0: return
        print(f"\n{'='*96}\n {title} — {len(sub)}종\n{'='*96}")
        h_now, h_prv = f"종가{dD[4:]}", f"전일{dP[4:]}"
        print(f"{'코드':>7} {'종목명':<13} {'시':<3} {'등락%':>7} {h_now:>10} {h_prv:>10} "
              f"{'PBR':>6} {'PER':>7} {'배당%':>5} {'5년고점比':>9} {'MA60比':>7} {'대금배수':>8}")
        print("-" * 96)
        for _, r in sub.iterrows():
            def g(k, f="{:>7.1f}"):
                v = r.get(k)
                return f.format(v) if pd.notna(v) else "      -"
            print(f"{r['code']:>7} {str(r['종목명'])[:12]:<13} {r['시장'][:3]:<3} "
                  f"{r[f'등락률_{dD}']:>7.2f} {g(f'종가_{dD}','{:>10,.0f}')} "
                  f"{g(f'종가_{dP}','{:>10,.0f}')} {g(f'PBR_{dP}','{:>6.2f}')} "
                  f"{g(f'PER_{dP}','{:>7.1f}')} {g(f'배당%_{dP}','{:>5.1f}')} "
                  f"{g('고점5년比','{:>8.0%}')} {g('MA60比','{:>6.0%}')} {g('거래대금배수','{:>6.1f}x')}")

    show(S[S["구분"] == "상한가"], f"① 상한가 (≥{LIMIT_UP}%)")
    show(S[S["구분"] != "상한가"], f"② +{a.min:.0f}% 이상 (상한가 제외)")

    # 패턴 요약
    v = S["고점5년比"].dropna()
    if len(v):
        print(f"\n{'-'*96}")
        print(f" 패턴: 5년 고점 대비 중위 {v.median():+.0%} · "
              f"−30% 이상 눌려 있던 종목 {int((v <= -0.30).sum())}/{len(v)}종 "
              f"({(v <= -0.30).mean()*100:.0f}%)")
        m6 = S["MA60比"].dropna()
        if len(m6):
            print(f"       60일선 아래에 있던 종목 {int((m6 < 0).sum())}/{len(m6)}종 "
                  f"({(m6 < 0).mean()*100:.0f}%)")
        x = S["거래대금배수"].dropna()
        if len(x): print(f"       거래대금 20일평균 대비 중위 {x.median():.1f}배")
    print(f"\n저장: {os.path.basename(out1)} · {os.path.basename(out2)}")
    print("⚠️ 사실 수집 결과다. 상한가는 사후 관찰이지 매수 신호가 아니다.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
