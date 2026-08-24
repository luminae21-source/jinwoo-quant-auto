# -*- coding: utf-8 -*-
r"""진단_A안_게이트지수_상세.py — KOSPI 지수 + 국면 게이트, 상세 해부
성격: **진단(descriptive). 합격 게이트 없음. 이 문서로 A안이 채택되지 않는다.**
근거: 엔진09 판정문 §5 — A안 검증치는 판정이 아니라 관찰이며 2016-26 구간은 이미 소모됨.
자체검증: py 진단_A안_게이트지수_상세.py --selftest
"""
import sys, argparse
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
C_SW = 0.003


def load():
    d = pd.read_csv("kospi_index_daily.csv", encoding="utf-8-sig"); d.columns = ["D", "C"]
    s = d.set_index(pd.to_datetime(d.D))["C"].resample("ME").last().dropna()
    s.index = s.index.strftime("%Y-%m")
    return s


def curves(s, n=10, cost=C_SW, lo=None, hi=None):
    r = s.pct_change().add(1.0)
    hold = (s >= s.rolling(n).mean())
    yms = [y for y in s.index if (lo is None or y >= lo) and (hi is None or y <= hi)]
    ea = eg = 1.0; prev = None; ca, cg, flips, cash = {}, {}, 0, 0
    for ym in yms:
        x = float(r.get(ym, 1.0))
        if not np.isfinite(x): x = 1.0
        ea *= x; ca[ym] = ea
        inp = bool(hold.get(ym, True))
        g = x if inp else 1.0
        if not inp: cash += 1
        if prev is not None and inp != prev: g -= cost; flips += 1
        prev = inp
        eg *= g; cg[ym] = eg
    return pd.Series(ca), pd.Series(cg), flips, cash, len(yms)


def stat(c):
    y = len(c)/12.0
    return dict(cagr=float(c.iloc[-1]**(1/y)-1), mdd=float((c/c.cummax()-1).min()),
                mult=float(c.iloc[-1]))


def line(nm, a, g):
    sa, sg = stat(a), stat(g)
    return ("  %-18s %7.2f배 %8.2f%% %8.1f%%  |  %7.2f배 %8.2f%% %8.1f%%  |  %+7.2f%%p"
            % (nm, sa["mult"], sa["cagr"]*100, sa["mdd"]*100,
               sg["mult"], sg["cagr"]*100, sg["mdd"]*100, (sg["cagr"]-sa["cagr"])*100))


def selftest():
    s = load()
    ok = [("KOSPI 월봉 >350", len(s) > 350)]
    a, g, f, c, n = curves(s)
    ok += [("곡선 길이 일치", len(a) == len(g) == n), ("전환 40~80회(ON·OFF 양방향)", 40 <= f <= 80),
           ("현금 보유월 존재", 0 < c < n), ("곡선 양수", (a > 0).all() and (g > 0).all())]
    a2, g2, _, _, _ = curves(s, cost=0.02)
    ok.append(("비용 올리면 게이트 성과 하락", stat(g2)["cagr"] < stat(g)["cagr"]))
    for n_, v in ok: print(("  OK   " if v else "  FAIL ") + n_)
    print("self-test %d/%d" % (sum(v for _, v in ok), len(ok)))
    return all(v for _, v in ok)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true")
    if ap.parse_args().selftest: sys.exit(0 if selftest() else 1)
    s = load()
    print("="*104)
    print("진단 — KOSPI 지수 + 국면 게이트 상세 (게이트 없음·판정 아님)")
    print("="*104)
    hdr = ("  %-18s %7s %8s %8s  |  %7s %8s %8s  |  %8s"
           % ("구간", "배수", "CAGR", "MDD", "배수", "CAGR", "MDD", "게이트기여"))
    print("\n[1] 구간별  (왼쪽=지수 보유 / 오른쪽=지수+게이트)")
    print(hdr)
    segs = [("1995-05~2001-12", "1995-05", "2001-12"), ("훈련 2002-06~2015-12", "2002-06", "2015-12"),
            ("검증 2016-01~2026-06", "2016-01", "2026-06"), ("전체 1995~2026", None, None)]
    for nm, lo, hi in segs:
        a, g, f, c, n = curves(s, lo=lo, hi=hi)
        print(line(nm, a, g) + "   전환%2d회·현금%2d/%d월" % (f, c, n))

    print("\n[2] 연도별 (검증 구간)")
    a, g, _, _, _ = curves(s, lo="2016-01", hi="2026-06")
    ya = a.groupby([x[:4] for x in a.index]).last()
    yg = g.groupby([x[:4] for x in g.index]).last()
    print("  %-6s %10s %10s %10s" % ("연도", "지수", "지수+게이트", "차이"))
    pa = pg = 1.0
    for y in ya.index:
        ra, rg = ya[y]/pa-1, yg[y]/pg-1; pa, pg = ya[y], yg[y]
        print("  %-6s %9.1f%% %10.1f%% %+9.1f%%p" % (y, ra*100, rg*100, (rg-ra)*100))

    print("\n[3] 비용 민감도 (전환 왕복비용, 검증 구간)")
    print("  %-10s %10s %10s" % ("비용", "CAGR", "vs 지수"))
    base = stat(curves(s, lo="2016-01", hi="2026-06")[0])["cagr"]
    for cst in (0.003, 0.005, 0.010, 0.020, 0.050):
        _, gg, _, _, _ = curves(s, cost=cst, lo="2016-01", hi="2026-06")
        v = stat(gg)["cagr"]
        print("  %-10s %9.2f%% %+9.2f%%p" % (f"{cst*100:.1f}%", v*100, (v-base)*100))

    print("\n[4] MA 기간 민감도 — **강건성 확인용. 이 표를 보고 MA를 바꾸면 규칙 위반이다.**")
    print("  %-8s %10s %10s %10s %10s" % ("MA", "훈련CAGR", "검증CAGR", "검증MDD", "전환수"))
    for n_ in (6, 8, 10, 12, 15):
        _, gt, _, _, _ = curves(s, n=n_, lo="2002-06", hi="2015-12")
        _, gv, fv, _, _ = curves(s, n=n_, lo="2016-01", hi="2026-06")
        mark = "  <- 현행" if n_ == 10 else ""
        print("  MA%-6d %9.2f%% %9.2f%% %9.1f%% %9d%s"
              % (n_, stat(gt)["cagr"]*100, stat(gv)["cagr"]*100, stat(gv)["mdd"]*100, fv, mark))

    print("\n[5] 미사용 표본 — 1995-05~2001-12 (재무 데이터 불필요하므로 A안은 이 구간을 쓸 수 있다)")
    a, g, f, c, n = curves(s, lo="1995-05", hi="2001-12")
    print(hdr); print(line("1995-2001", a, g) + "   전환%2d회·현금%2d/%d월" % (f, c, n))
    print("  ※ IMF 외환위기 포함 — 게이트에 유리한 구간일 수 있다. 정식 검정 시 반드시 고지해야 한다.")


if __name__ == "__main__":
    main()
