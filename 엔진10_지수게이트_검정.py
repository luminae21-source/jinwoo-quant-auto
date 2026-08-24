# -*- coding: utf-8 -*-
r"""엔진10_지수게이트_검정.py — 지수 + 국면 게이트, 미사용 표본 2개 동시 검정
사전등록: 엔진10_지수게이트_사전등록_2026-08-24.md (봉인·격자 0개)
핵심: 형의 반론("IMF·리먼 같은 대형 이벤트가 다 만든 것 아니냐")을 **합격선**으로 박았다.
자체검증: py 엔진10_지수게이트_검정.py --selftest
"""
import sys, json, argparse
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

MA_N, COST = 10, 0.003
G1, G2, G4 = 0.030, 0.010, 0.10          # 기본기여 / 위기제외기여 / MDD개선
TOPK = 3
CRISIS = [("IMF", "1997-07", "1998-12"), ("리먼", "2008-06", "2009-06"),
          ("코로나", "2020-02", "2020-05"), ("2022긴축", "2022-01", "2022-10")]
SAMPLES = [("표본1 KOSPI 1995-2001", "kospi_index_daily.csv", "1995-05", "2001-12"),
           ("표본2 KOSDAQ 전기간", "kosdaq_index_daily.csv", "1996-07", "2026-08")]


def monthly(path):
    d = pd.read_csv(path, encoding="utf-8-sig"); d.columns = ["D", "C"]
    s = d.set_index(pd.to_datetime(d.D))["C"].resample("ME").last().dropna()
    s.index = s.index.strftime("%Y-%m")
    return s


def in_crisis(ym):
    return any(a <= ym <= b for _, a, b in CRISIS)


def series(s, lo, hi, drop_crisis=False, drop_months=()):
    """월별 (지수수익비, 게이트수익비). drop_* 는 해당 월을 아예 건너뛴다."""
    r = s.pct_change().add(1.0)
    hold = (s >= s.rolling(MA_N).mean())
    prev = None
    idx, ra, rg = [], [], []
    for ym in s.index:
        if ym < lo or ym > hi: continue
        x = float(r.get(ym, 1.0))
        if not np.isfinite(x): x = 1.0
        inp = bool(hold.get(ym, True))
        g = x if inp else 1.0
        if prev is not None and inp != prev: g -= COST
        prev = inp
        if drop_crisis and in_crisis(ym): continue
        if ym in drop_months: continue
        idx.append(ym); ra.append(x); rg.append(g)
    return pd.Series(ra, index=idx), pd.Series(rg, index=idx)


def stat(ra, rg):
    if len(ra) < 24: return None
    ca, cg = ra.cumprod(), rg.cumprod()
    y = len(ra)/12.0
    return dict(n=len(ra),
                a_cagr=float(ca.iloc[-1]**(1/y)-1), g_cagr=float(cg.iloc[-1]**(1/y)-1),
                a_mdd=float((ca/ca.cummax()-1).min()), g_mdd=float((cg/cg.cummax()-1).min()),
                a_mult=float(ca.iloc[-1]), g_mult=float(cg.iloc[-1]))


def contrib_months(s, lo, hi, k=TOPK):
    """기여(게이트−지수)가 큰 상위 k개월."""
    ra, rg = series(s, lo, hi)
    d = (rg - ra).sort_values(ascending=False)
    return list(d.head(k).index), d


def selftest():
    ok = []
    for nm, p, lo, hi in SAMPLES:
        s = monthly(p)
        ok.append((f"{nm} 로드", len(s) > 60))
        ra, rg = series(s, lo, hi)
        ok.append((f"{nm} 시리즈 유한", len(ra) > 24 and np.isfinite(ra).all() and np.isfinite(rg).all()))
    s = monthly(SAMPLES[1][1])
    a1, g1_ = series(s, "1996-07", "2026-08")
    a2, g2_ = series(s, "1996-07", "2026-08", drop_crisis=True)
    ok.append(("위기 제외가 표본을 줄임", len(a2) < len(a1)))
    ok.append(("IMF 판정", in_crisis("1998-01") and not in_crisis("2005-01")))
    tops, _ = contrib_months(s, "1996-07", "2026-08")
    ok.append(("상위기여월 3개 산출", len(tops) == 3))
    a3, g3_ = series(s, "1996-07", "2026-08", drop_months=set(tops))
    ok.append(("상위월 제거 반영", len(a3) == len(a1) - 3))
    ok.append(("합격선 고정", abs(G1-0.030) < 1e-9 and abs(G2-0.010) < 1e-9))
    for n_, v in ok: print(("  OK   " if v else "  FAIL ") + n_)
    print("self-test %d/%d" % (sum(v for _, v in ok), len(ok)))
    return all(v for _, v in ok)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true")
    if ap.parse_args().selftest: sys.exit(0 if selftest() else 1)
    print("="*92)
    print("엔진10 지수 게이트 — 미사용 표본 2개 동시 검정 · 격자 0개 · 1회차")
    print("="*92)

    res, out = {}, {}
    for nm, p, lo, hi in SAMPLES:
        s = monthly(p)
        base = stat(*series(s, lo, hi))
        nocri = stat(*series(s, lo, hi, drop_crisis=True))
        tops, dser = contrib_months(s, lo, hi)
        notop = stat(*series(s, lo, hi, drop_months=set(tops)))
        res[nm] = dict(base=base, nocri=nocri, notop=notop, tops=tops,
                       topvals=[float(dser[t]) for t in tops])
        out[nm] = s

    print("\n[1] 기본 (게이트 없음 → 게이트)")
    print("  %-24s %5s %9s %9s %10s %9s %9s"
          % ("표본", "개월", "지수CAGR", "게이트", "기여", "지수MDD", "게이트MDD"))
    for nm in res:
        b = res[nm]["base"]
        print("  %-24s %5d %8.2f%% %8.2f%% %+9.2f%%p %8.1f%% %8.1f%%"
              % (nm, b["n"], b["a_cagr"]*100, b["g_cagr"]*100,
                 (b["g_cagr"]-b["a_cagr"])*100, b["a_mdd"]*100, b["g_mdd"]*100))

    print("\n[2] ★ 위기 4개 구간 제외 (IMF·리먼·코로나·2022긴축)")
    print("  %-24s %5s %9s %9s %10s" % ("표본", "개월", "지수CAGR", "게이트", "기여"))
    for nm in res:
        c = res[nm]["nocri"]
        if not c: print("  %-24s 표본 부족" % nm); continue
        print("  %-24s %5d %8.2f%% %8.2f%% %+9.2f%%p"
              % (nm, c["n"], c["a_cagr"]*100, c["g_cagr"]*100, (c["g_cagr"]-c["a_cagr"])*100))

    print("\n[3] ★ 기여 상위 3개월 제외")
    print("  %-24s %5s %10s   %s" % ("표본", "개월", "기여", "제외한 달"))
    for nm in res:
        t = res[nm]["notop"]
        print("  %-24s %5d %+9.2f%%p   %s"
              % (nm, t["n"], (t["g_cagr"]-t["a_cagr"])*100,
                 ", ".join("%s(%+.1f%%)" % (m, v*100)
                           for m, v in zip(res[nm]["tops"], res[nm]["topvals"]))))

    print("\n[4] 4게이트 — 두 표본 **모두** 통과해야 합격")
    def both(fn): return all(fn(res[nm]) for nm in res)
    g1 = both(lambda r: r["base"] and (r["base"]["g_cagr"]-r["base"]["a_cagr"]) >= G1)
    g2 = both(lambda r: r["nocri"] and (r["nocri"]["g_cagr"]-r["nocri"]["a_cagr"]) >= G2)
    g3 = both(lambda r: r["notop"] and (r["notop"]["g_cagr"]-r["notop"]["a_cagr"]) >= 0)
    g4 = both(lambda r: r["base"] and (r["base"]["g_mdd"]-r["base"]["a_mdd"]) >= G4)
    for lab, v in (("1 기본 기여 ≥ +3.0%p", g1), ("2 위기 제외 기여 ≥ +1.0%p", g2),
                   ("3 상위3월 제외 기여 ≥ 0", g3), ("4 MDD 10%p 이상 개선", g4)):
        print("  %-30s → %s" % (lab, "PASS" if v else "FAIL"))
    allp = g1 and g2 and g3 and g4
    print("\n  최종: %s" % ("PASS" if allp else "FAIL — 19번째 기각"))
    if not allp and g1 and not g2:
        print("  §7-4: 게이트2 단독 실패 → '위기 보험으로 존치, 구조적 엣지 주장 철회' 후보")

    print("\n[5] §6 필수 기록 — 위기 구간이 만든 몫")
    for nm in res:
        b, c = res[nm]["base"], res[nm]["nocri"]
        if not (b and c): continue
        tot, ex = (b["g_cagr"]-b["a_cagr"]), (c["g_cagr"]-c["a_cagr"])
        share = (1 - ex/tot)*100 if tot else float("nan")
        print("  %-24s 전체기여 %+.2f%%p · 위기제외 %+.2f%%p → 위기 몫 %.0f%%"
              % (nm, tot*100, ex*100, share))

    json.dump({k: {kk: vv for kk, vv in v.items()} for k, v in res.items()} |
              {"gates": {"g1": bool(g1), "g2": bool(g2), "g3": bool(g3), "g4": bool(g4), "pass": bool(allp)}},
              open("엔진10_결과.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("\n저장: 엔진10_결과.json")


if __name__ == "__main__":
    main()
