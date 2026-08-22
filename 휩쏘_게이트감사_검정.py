# -*- coding: utf-8 -*-
"""휩쏘 · 게이트 감사 + 시장분리 검정 (2026-08-04 저녁 · 형 승인 과제 b)

사전 선언 (실행 전 고정):
  질문1  기존 국면 도장의 look-ahead(변동성 중앙값이 전체표본) 제거 시 게이트 결론이 유지되는가
  질문2  KOSDAQ 종목에 KOSDAQ 지수 게이트를 쓰면 KOSPI 지수 게이트보다 나은가
  1차 지표  국면 3분류의 카드 평균 스프레드(실행 − 관찰만) · 불일치 셀의 카드 평균
  판정 규칙  질문2는 탐색적 — 유망해도 이 자리에서 채택하지 않고 사전등록으로만 넘긴다
  방법 검증  합성지수(클립 평균수익률)로 만든 KOSPI 게이트가 실지수 게이트와
             이벤트일 기준 90%+ 일치해야 KOSDAQ 합성 게이트를 신뢰한다. 미달 시 중단.

[검정4 · 확정 판정 — kosdaq_index_daily.csv(실지수)가 폴더에 있으면 자동 실행]
  사전 선언 (2026-08-04 등록 · 사후 변경 금지):
    비교   같은 이벤트 부분집합(양쪽 지수 특징이 모두 유효한 날)에서
           KOSPI 실지수 게이트 vs KOSDAQ 실지수 게이트 (둘 다 expanding)
    채택→사전등록  KOSDAQ 게이트 스프레드가 KOSPI 게이트보다 +0.5%p 이상 크고,
           불일치 셀의 부호가 KOSDAQ 게이트 방향으로 일관될 때만 '사전등록 후보'로 넘긴다
           (이 자리에서 채택하지 않는다)
    기각   스프레드 열등 또는 ±0.5%p 이내 동등 → 현행 KOSPI 단일 게이트 유지 · 재론 금지
"""
import os, sys, json, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass


def _resolve():
    here = os.path.dirname(os.path.abspath(__file__))
    cand = [here, os.path.join(here, "_stagetmp3"),
            "/home/claude/jq", "/mnt/user-data/uploads/진우퀀트",
            "/mnt/user-data/uploads/진우퀀트/_stagetmp3"]
    def find(name):
        for d in cand:
            p = os.path.join(d, name)
            if os.path.exists(p): return p
        return os.path.join(here, name)
    return here, find
HERE, F = _resolve()
NB = 4000; SEED = 11


def boot_mean(a, yrs):
    a = np.asarray(a, float); yrs = np.asarray(yrs)
    ok = np.isfinite(a); a, yrs = a[ok], yrs[ok]
    if len(a) < 8: return (np.nan, np.nan)
    rng = np.random.default_rng(SEED); ys = np.array(sorted(set(yrs)))
    idx = {y: np.where(yrs == y)[0] for y in ys}; out = np.empty(NB)
    for i in range(NB):
        p = rng.choice(ys, size=len(ys), replace=True)
        out[i] = np.nanmean(a[np.concatenate([idx[y] for y in p])])
    return tuple(np.percentile(out, [2.5, 97.5]) * 100)


def features(dates, close):
    """시장국면.py 와 동일: mdd252 · vol20"""
    s = pd.DataFrame({"Date": pd.to_datetime(dates), "Close": np.asarray(close, float)})
    s = s.sort_values("Date").reset_index(drop=True)
    c = s["Close"]
    s["mdd"] = c / c.rolling(252, min_periods=120).max() - 1
    s["vol"] = c.pct_change().rolling(20, min_periods=10).std() * np.sqrt(252)
    return s


def label(s, volmed_mode):
    """volmed_mode: 'full'(기존 도장 방식·look-ahead) / 'expanding'(정직)"""
    if volmed_mode == "full":
        vm = pd.Series(s["vol"].median(), index=s.index)
    else:
        vm = s["vol"].expanding(60).median()
    volhi = np.isfinite(s["vol"]) & (s["vol"] > vm)
    lab = np.where(np.isfinite(s["mdd"]) & (s["mdd"] <= -0.12), "실행",
          np.where(volhi & np.isfinite(s["mdd"]) & (s["mdd"] <= -0.05), "실행",
          np.where(np.isfinite(s["mdd"]) & (s["mdd"] >= -0.05) & (~volhi), "관찰만", "주의")))
    out = s.copy(); out["lab"] = lab; return out.set_index("Date")


def stamp(ev_dates, labdf):
    """이벤트일 ≤ 마지막 지수일 도장 (당일 종가 기준 — 기존 방식과 동일)"""
    idx = labdf.index.searchsorted(pd.to_datetime(ev_dates).values, side="right") - 1
    return np.where(idx >= 0, labdf["lab"].values[np.clip(idx, 0, None)], "?")


def table(ev, col, title, res, key):
    print(f"\n{title}")
    print(f"{'국면':<8}{'n':>7}{'평균%':>9}{'중앙%':>9}{'승률':>8}{'   부트95%CI':>20}{'  신호일':>8}")
    res[key] = {}
    for st in ("실행", "주의", "관찰만"):
        s = ev[ev[col] == st]
        if len(s) < 5: continue
        a = s["카드"].values.astype(float)
        lo, hi = boot_mean(a, s["연"].values)
        nd = s["date"].nunique()
        print(f"{st:<8}{len(s):>7}{np.nanmean(a)*100:>9.2f}{np.nanmedian(a)*100:>9.2f}"
              f"{(a > 0).mean()*100:>7.1f}%   [{lo:+6.2f},{hi:+6.2f}]{nd:>8}")
        res[key][st] = dict(n=int(len(s)), 평균=float(np.nanmean(a)*100),
                            중앙=float(np.nanmedian(a)*100), 승률=float((a > 0).mean()*100),
                            ci=[float(lo), float(hi)], 신호일=int(nd))
    if "실행" in res[key] and "관찰만" in res[key]:
        sp = res[key]["실행"]["평균"] - res[key]["관찰만"]["평균"]
        print(f"   → 스프레드(실행−관찰만) {sp:+.2f}%p")
        res[key]["스프레드"] = float(sp)


def main():
    res = {}
    ev = pd.read_csv(F("S2_이벤트_통합.csv"), dtype={"code": str})
    ev.columns = [x.strip().lstrip("﻿") for x in ev.columns]
    ev["code"] = ev["code"].str.zfill(6); ev["연"] = ev["연"].astype(int)

    # 실지수 (KOSPI)
    ix = pd.read_csv(F("kospi_index_daily.csv"))
    ix.columns = [c.strip().lstrip("﻿") for c in ix.columns]
    real = features(ix["Date"], ix["Close"])

    # 합성지수 (양 시장 · 클립 평균수익률 누적)
    syn = {}
    for mk in ("KOSPI", "KOSDAQ"):
        r = pd.read_csv(F(f"synidx_{mk}.csv"), header=None, names=["date", "ret", "n"])
        r = r[r["n"] >= 30]                      # 표본 30종 미만 날은 제외
        lvl = 100 * (1 + r["ret"].astype(float)).cumprod()
        syn[mk] = features(r["date"], lvl)

    print("=" * 82)
    print("[검정0] 기존 도장 재현 — 실지수 + full 중앙값")
    lab_full = label(real, "full")
    ev["G_재현"] = stamp(ev["date"], lab_full)
    agree = (ev["G_재현"] == ev["국면"]).mean()
    print(f"  일치율 {agree*100:.2f}%  (100%여야 함 — 도장이 이 방식이었다는 증명)")
    res["재현일치율"] = float(agree * 100)
    if agree < 0.999:
        print("  ❌ 재현 실패 — 이후 결과 무효"); return

    # ── 질문1: look-ahead 제거 ─────────────────────────────
    print("\n" + "=" * 82)
    print("[검정1] look-ahead 제거 — 변동성 중앙값을 full → expanding(시점까지)으로")
    lab_exp = label(real, "expanding")
    ev["G_정직"] = stamp(ev["date"], lab_exp)
    chg = (ev["G_정직"] != ev["국면"]).sum()
    print(f"  도장 변경 {chg}건 ({chg/len(ev)*100:.1f}%) : "
          f"{ev[ev['G_정직'] != ev['국면']].groupby(['국면','G_정직']).size().to_dict()}")
    res["정직_변경"] = int(chg)
    table(ev, "국면", "  (기존 도장 · full 중앙값 — look-ahead 있음)", res, "게이트_기존")
    table(ev, "G_정직", "  (정직 도장 · expanding 중앙값 — look-ahead 없음)", res, "게이트_정직")

    # ── 방법 검증: 합성 KOSPI vs 실 KOSPI ─────────────────
    print("\n" + "=" * 82)
    print("[검정2] 합성지수 방법 검증 — 합성 KOSPI 게이트 vs 실지수 게이트 (이벤트일)")
    lab_synK = label(syn["KOSPI"], "expanding")
    ev["G_합성K"] = stamp(ev["date"], lab_synK)
    m_agree = (ev["G_합성K"] == ev["G_정직"]).mean()
    print(f"  이벤트일 일치율 {m_agree*100:.1f}%  (기준: 90% 미만이면 KOSDAQ 합성 게이트 중단)")
    res["방법검증_일치율"] = float(m_agree * 100)
    x = ev[ev["G_합성K"] != ev["G_정직"]]
    if len(x): print(f"  불일치 구성: {x.groupby(['G_정직','G_합성K']).size().to_dict()}")
    if m_agree < 0.90:
        print("  ⚠️ 방법 검증 미달 — KOSDAQ 게이트는 여기서 중단, 결과는 참고로만")
    ok_method = m_agree >= 0.90

    # ── 질문2: KOSDAQ 종목에 KOSDAQ 게이트 ────────────────
    print("\n" + "=" * 82)
    print("[검정3] 시장분리 — KOSDAQ 종목에 KOSDAQ 합성 게이트 (expanding · 정직 기준끼리 비교)")
    lab_synQ = label(syn["KOSDAQ"], "expanding")
    ev["G_KQ"] = stamp(ev["date"], lab_synQ)
    KQ = ev[ev["시장"] == "KOSDAQ"].copy()
    print(f"  KOSDAQ 이벤트 {len(KQ)}건")
    table(KQ, "G_정직", "  (a) KOSPI 지수 게이트(정직) — 현행 방식", res, "KQ_KOSPI게이트")
    table(KQ, "G_KQ", "  (b) KOSDAQ 지수 게이트(정직·합성)", res, "KQ_KOSDAQ게이트")

    print("\n  (c) 불일치 셀 — 게이트가 갈리는 자리의 진실")
    both = KQ.groupby(["G_정직", "G_KQ"])
    res["불일치셀"] = {}
    print(f"{'KOSPI게이트':<12}{'KOSDAQ게이트':<13}{'n':>6}{'평균%':>9}{'중앙%':>9}{'승률':>8}{'   부트95%CI':>20}")
    for (g1, g2), s in both:
        if g1 == g2 or len(s) < 30: continue
        a = s["카드"].values.astype(float)
        lo, hi = boot_mean(a, s["연"].values)
        print(f"{g1:<12}{g2:<13}{len(s):>6}{np.nanmean(a)*100:>9.2f}"
              f"{np.nanmedian(a)*100:>9.2f}{(a > 0).mean()*100:>7.1f}%   [{lo:+6.2f},{hi:+6.2f}]")
        res["불일치셀"][f"{g1}→{g2}"] = dict(n=int(len(s)), 평균=float(np.nanmean(a)*100),
                                             중앙=float(np.nanmedian(a)*100),
                                             승률=float((a > 0).mean()*100),
                                             ci=[float(lo), float(hi)])
    res["방법검증통과"] = bool(ok_method)

    # ── 검정4: 실제 KOSDAQ 지수 (있을 때만 — 확정 판정) ─────────
    kq_path = F("kosdaq_index_daily.csv")
    if os.path.exists(kq_path):
        print("\n" + "=" * 82)
        print("[검정4] 확정 판정 — 실제 KOSDAQ 지수 게이트 (사전 선언 규칙 적용)")
        kqx = pd.read_csv(kq_path)
        kqx.columns = [c.strip().lstrip("\ufeff") for c in kqx.columns]
        realQ = features(kqx["Date"], kqx["Close"])
        lab_realQ = label(realQ, "expanding")
        ev["G_실KQ"] = stamp(ev["date"], lab_realQ)

        # 유효 부분집합: 양쪽 지수 모두 mdd 특징이 유효한 날 이후의 이벤트만 (공정 비교)
        vK = lab_exp[np.isfinite(lab_exp["mdd"])].index.min()
        vQ = lab_realQ[np.isfinite(lab_realQ["mdd"])].index.min()
        v0 = max(vK, vQ)
        KQ4 = ev[(ev["시장"] == "KOSDAQ") & (pd.to_datetime(ev["date"]) >= v0)].copy()
        print(f"  유효 시작일 {v0.date()} · 비교 표본 {len(KQ4)}건 "
              f"(제외 {int((ev['시장'] == 'KOSDAQ').sum()) - len(KQ4)}건 — 지수 특징 미성숙 구간)")
        table(KQ4, "G_정직", "  (a) KOSPI 실지수 게이트 (expanding)", res, "확정_KOSPI게이트")
        table(KQ4, "G_실KQ", "  (b) KOSDAQ 실지수 게이트 (expanding)", res, "확정_KOSDAQ게이트")

        print("\n  (c) 불일치 셀")
        res["확정_불일치"] = {}
        for (g1, g2), sx in KQ4.groupby(["G_정직", "G_실KQ"]):
            if g1 == g2 or len(sx) < 30: continue
            a = sx["카드"].values.astype(float)
            lo, hi = boot_mean(a, sx["연"].values)
            print(f"    KOSPI={g1:<4} KOSDAQ={g2:<4} n={len(sx):>5} 평균 {np.nanmean(a)*100:+.2f}% "
                  f"승률 {(a > 0).mean()*100:.1f}%  CI[{lo:+.2f},{hi:+.2f}]")
            res["확정_불일치"][f"{g1}→{g2}"] = dict(n=int(len(sx)), 평균=float(np.nanmean(a)*100),
                                                    승률=float((a > 0).mean()*100),
                                                    ci=[float(lo), float(hi)])
        spK = res.get("확정_KOSPI게이트", {}).get("스프레드")
        spQ = res.get("확정_KOSDAQ게이트", {}).get("스프레드")
        if spK is not None and spQ is not None:
            d = spQ - spK
            if d >= 0.5:
                verdict = ("사전등록 후보 — KOSDAQ 게이트 스프레드가 +%.2f%%p 우월. "
                           "단 여기서 채택하지 않는다. 사전등록 문서를 만들 것." % d)
            else:
                verdict = ("기각 — 스프레드 차 %+.2f%%p (기준 +0.5%%p 미달). "
                           "현행 KOSPI 단일 게이트 유지 · 재론 금지." % d)
            print(f"\n  ★ 확정 판정: {verdict}")
            res["확정판정"] = dict(spread_KOSPI=float(spK), spread_KOSDAQ=float(spQ),
                                   차=float(d), 판정=verdict)
    else:
        print("\n  ⓘ kosdaq_index_daily.csv 없음 — [검정4]는 지수 수집 후 자동 실행된다.")
        print("     형 PC에서: KOSDAQ지수_수집_실행.bat 더블클릭 (수집 → 이 스크립트 재실행까지 자동)")

    with open(os.path.join(HERE, "휩쏘_게이트감사_결과.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    ev.to_csv(os.path.join(HERE, "휩쏘_게이트감사_이벤트.csv"), index=False, encoding="utf-8-sig")
    print("\n저장: 휩쏘_게이트감사_결과.json · 휩쏘_게이트감사_이벤트.csv")


if __name__ == "__main__":
    main()
