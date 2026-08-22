# -*- coding: utf-8 -*-
"""휩쏘 · breadth(구조선 이탈 폭) 게이트 검정 — 이 표본에서의 마지막 게이트 실험

사전등록 (2026-08-04 밤 · 형 승인 · 실행 전 고정 — 사후 변경 금지):
  신호   b(t) = 해당 시장 전종목(상폐 포함) 중 자기 MA240 아래 종가 비율
         · MA240은 무수정 종가 240봉 이동평균 (breadth_*.csv — awk 전수 계산)
         · 표본 100종 미만인 날 제외
  게이트  expanding 분위수 (min 504일 ≈ 2년):
         실행    b ≥ expanding 75%ile   (시장 구조 손상 상위 25%)
         관찰만  b ≤ expanding 40%ile   (구조 온전 — 고점권 함정 국면)
         주의    그 외
  비교   KOSDAQ 종목 이벤트, breadth 게이트(KOSDAQ 폭) vs 현행 KOSPI 지수 게이트(expanding·정직)
         양쪽 게이트가 모두 유효한 같은 이벤트 부분집합
  판정   [채택→사전등록 후보]  스프레드 차 ≥ +0.5%p 그리고 불일치 셀 부호 일관
         [기각]               그 외 → 게이트 건 완전 종결
  종결 선언  결과와 무관하게 이 30년 표본에서 게이트 변형 실험은 이것으로 끝낸다.
             이후 게이트 아이디어는 전진검증(관찰 원장)으로만 받는다.
  부수 기록  (판정에 안 씀 · 관찰만) KOSPI 종목에 KOSPI 폭 게이트 대칭 확인,
             breadth × 지수게이트 겹침 셀 기술통계
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
MINQ = 504


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


def breadth_gate(mk):
    b = pd.read_csv(F(f"breadth_{mk}.csv"), header=None, names=["date", "below", "n"])
    b = b[b["n"] >= 100].copy()
    b["date"] = pd.to_datetime(b["date"]); b = b.sort_values("date").reset_index(drop=True)
    v = b["below"].astype(float)
    q75 = v.expanding(MINQ).quantile(0.75)
    q40 = v.expanding(MINQ).quantile(0.40)
    lab = np.where(~np.isfinite(q75), "?",
          np.where(v >= q75, "실행",
          np.where(v <= q40, "관찰만", "주의")))
    b["lab"] = lab
    return b.set_index("date")


def kospi_index_gate():
    ix = pd.read_csv(F("kospi_index_daily.csv"))
    ix.columns = [c.strip().lstrip("﻿") for c in ix.columns]
    s = pd.DataFrame({"Date": pd.to_datetime(ix["Date"]),
                      "Close": ix["Close"].astype(float)}).sort_values("Date")
    c = s["Close"]
    s["mdd"] = c / c.rolling(252, min_periods=120).max() - 1
    s["vol"] = c.pct_change().rolling(20, min_periods=10).std() * np.sqrt(252)
    vm = s["vol"].expanding(60).median()
    volhi = np.isfinite(s["vol"]) & (s["vol"] > vm)
    s["lab"] = np.where(np.isfinite(s["mdd"]) & (s["mdd"] <= -0.12), "실행",
               np.where(volhi & np.isfinite(s["mdd"]) & (s["mdd"] <= -0.05), "실행",
               np.where(np.isfinite(s["mdd"]) & (s["mdd"] >= -0.05) & (~volhi), "관찰만", "주의")))
    return s.set_index("Date")


def stamp(ev_dates, labdf):
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
        print(f"{st:<8}{len(s):>7}{np.nanmean(a)*100:>9.2f}{np.nanmedian(a)*100:>9.2f}"
              f"{(a > 0).mean()*100:>7.1f}%   [{lo:+6.2f},{hi:+6.2f}]{s['date'].nunique():>8}")
        res[key][st] = dict(n=int(len(s)), 평균=float(np.nanmean(a)*100),
                            중앙=float(np.nanmedian(a)*100), 승률=float((a > 0).mean()*100),
                            ci=[float(lo), float(hi)], 신호일=int(s["date"].nunique()))
    if "실행" in res[key] and "관찰만" in res[key]:
        sp = res[key]["실행"]["평균"] - res[key]["관찰만"]["평균"]
        print(f"   → 스프레드(실행−관찰만) {sp:+.2f}%p")
        res[key]["스프레드"] = float(sp)


def main():
    res = {"설계": "breadth 게이트 · expanding q75/q40 · 판정기준 Δ≥+0.5%p & 불일치 일관 · 마지막 게이트 실험"}
    ev = pd.read_csv(F("S2_이벤트_통합.csv"), dtype={"code": str})
    ev.columns = [x.strip().lstrip("﻿") for x in ev.columns]
    ev["code"] = ev["code"].str.zfill(6); ev["연"] = ev["연"].astype(int)

    gK = kospi_index_gate()
    bQ = breadth_gate("KOSDAQ"); bK = breadth_gate("KOSPI")
    ev["G_지수K"] = stamp(ev["date"], gK)
    ev["G_폭Q"] = stamp(ev["date"], bQ)
    ev["G_폭K"] = stamp(ev["date"], bK)

    print("=" * 82)
    print("[폭 게이트] 분위수 확인 (KOSDAQ · expanding 최종값)")
    v = bQ["below"]
    print(f"  b 분포: 중앙 {v.median()*100:.0f}% · 실행 문턱(q75) {v.quantile(.75)*100:.0f}% 근방 · "
          f"관찰만 문턱(q40) {v.quantile(.40)*100:.0f}% 근방 (expanding이라 시점마다 다름)")
    print(f"  게이트 분포(일수): {pd.Series(bQ['lab']).value_counts().to_dict()}")

    # 주 판정: KOSDAQ 종목 · 양 게이트 유효 부분집합
    KQ = ev[(ev["시장"] == "KOSDAQ") & (ev["G_폭Q"] != "?") & (ev["G_지수K"] != "?")].copy()
    print("\n" + "=" * 82)
    print(f"[주 판정] KOSDAQ 이벤트 {int((ev['시장']=='KOSDAQ').sum())}건 중 비교 가능 {len(KQ)}건 "
          f"(제외 {int((ev['시장']=='KOSDAQ').sum())-len(KQ)}건 — breadth 분위수 미성숙 구간)")
    table(KQ, "G_지수K", "  (a) 현행 KOSPI 지수 게이트 (expanding·정직)", res, "지수게이트")
    table(KQ, "G_폭Q", "  (b) KOSDAQ 폭(breadth) 게이트", res, "폭게이트")

    print("\n  (c) 불일치 셀")
    res["불일치"] = {}
    for (g1, g2), s in KQ.groupby(["G_지수K", "G_폭Q"]):
        if g1 == g2 or len(s) < 30: continue
        a = s["카드"].values.astype(float)
        lo, hi = boot_mean(a, s["연"].values)
        print(f"    지수={g1:<4} 폭={g2:<4} n={len(s):>5} 평균 {np.nanmean(a)*100:+.2f}% "
              f"승률 {(a > 0).mean()*100:.1f}%  CI[{lo:+.2f},{hi:+.2f}]")
        res["불일치"][f"{g1}→{g2}"] = dict(n=int(len(s)), 평균=float(np.nanmean(a)*100),
                                           승률=float((a > 0).mean()*100), ci=[float(lo), float(hi)])

    spK = res["지수게이트"].get("스프레드"); spB = res["폭게이트"].get("스프레드")
    if spK is not None and spB is not None:
        d = spB - spK
        # 불일치 일관성: 폭 게이트가 격상한 셀은 +, 격하한 셀은 − 여야
        up = [v for k, v in res["불일치"].items()
              if k.split("→")[1] == "실행" or (k.split("→")[0] == "관찰만" and k.split("→")[1] == "주의")]
        dn = [v for k, v in res["불일치"].items()
              if k.split("→")[1] == "관찰만" or (k.split("→")[0] == "실행" and k.split("→")[1] == "주의")]
        consist = all(v["평균"] > 0 for v in up) and all(v["평균"] < 0 for v in dn) if (up or dn) else False
        if d >= 0.5 and consist:
            verdict = f"사전등록 후보 — 스프레드 Δ{d:+.2f}%p 그리고 불일치 셀 일관. 여기서 채택하지 않는다."
        else:
            why = []
            if d < 0.5: why.append(f"스프레드 Δ{d:+.2f}%p < +0.5%p")
            if not consist: why.append("불일치 셀 부호 비일관")
            verdict = "기각 — " + " · ".join(why) + ". 게이트 건 완전 종결(전진검증만)."
        print(f"\n  ★ 판정: {verdict}")
        res["판정"] = dict(spread_지수=float(spK), spread_폭=float(spB), 차=float(d),
                           일관=bool(consist), 결론=verdict)

    # 부수 기록 (판정 무관)
    print("\n" + "=" * 82)
    print("[부수 기록 · 판정에 쓰지 않음]")
    KP = ev[(ev["시장"] == "KOSPI") & (ev["G_폭K"] != "?") & (ev["G_지수K"] != "?")].copy()
    table(KP, "G_폭K", "  (i) 대칭 확인 — KOSPI 종목에 KOSPI 폭 게이트", res, "부수_KOSPI폭")
    both = KQ[(KQ["G_지수K"] == "실행") & (KQ["G_폭Q"] == "실행")]
    a = both["카드"].values.astype(float)
    if len(a) > 30:
        lo, hi = boot_mean(a, both["연"].values)
        print(f"\n  (ii) 겹침 셀 — 지수도 실행 & 폭도 실행: n={len(both)} "
              f"평균 {np.nanmean(a)*100:+.2f}% 승률 {(a>0).mean()*100:.1f}% CI[{lo:+.2f},{hi:+.2f}]")
        res["부수_겹침"] = dict(n=int(len(both)), 평균=float(np.nanmean(a)*100),
                               승률=float((a > 0).mean()*100), ci=[float(lo), float(hi)])

    with open(os.path.join(HERE, "휩쏘_폭게이트_결과.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    ev.to_csv(os.path.join(HERE, "휩쏘_폭게이트_이벤트.csv"), index=False, encoding="utf-8-sig")
    print("\n저장: 휩쏘_폭게이트_결과.json · 휩쏘_폭게이트_이벤트.csv")


if __name__ == "__main__":
    main()
