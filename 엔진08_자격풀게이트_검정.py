# -*- coding: utf-8 -*-
r"""엔진08_자격풀게이트_검정.py — 고르지 않는다. 자격풀을 사고 국면 게이트로 타이밍만 정한다.
사전등록: 엔진08_자격풀게이트_사전등록_2026-08-23.md (격자 0개·봉인)
자체검증: py 엔진08_자격풀게이트_검정.py --selftest
"""
import sys, json, argparse
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

C_SWITCH, C_POOL = 0.003, 0.006
TR = ("2002-06", "2015-12"); VA = ("2016-01", "2026-06")
G2_MDD, G3_EXCESS = 0.10, 0.030
SPLIT_HI, SPLIT_LO = 3.0, 1/3.0


def panel():
    fr = [pd.read_csv(f"_월봉종가캐시_{m}.csv", encoding="utf-8-sig", dtype={"code": str})
          for m in ("KOSPI", "KOSDAQ")]
    d = pd.concat(fr, ignore_index=True); d["code"] = d["code"].str.zfill(6)
    d = d[d.close > 0].drop_duplicates(["code", "ym"], keep="last")
    P = d.pivot(index="ym", columns="code", values="close").sort_index()
    R = P / P.shift(1); R = R.mask((R > SPLIT_HI) | (R < SPLIT_LO), 1.0); R.iloc[0] = 1.0
    return R.where(P.notna())          # 월간 총수익비 (결측=미상장)


def pools():
    """매년 6월 자격풀 (엔진07 §2 정의 그대로)."""
    fr = []
    for m in ("KOSPI", "KOSDAQ"):
        x = pd.read_csv(f"종목재무_KRX_{m}.csv", encoding="utf-8-sig", dtype={"code": str})
        x.columns = [c.strip().lstrip("﻿") for c in x.columns]
        fr.append(x[["date", "code", "BPS", "EPS"]])
    f = pd.concat(fr, ignore_index=True); f["code"] = f["code"].str.zfill(6)
    f["ym"] = f["date"].str[:7]
    for c in ("BPS", "EPS"): f[c] = pd.to_numeric(f[c], errors="coerce")
    f = f.dropna(subset=["BPS", "EPS"]).drop_duplicates(["code", "ym"], keep="last")

    mc = pd.read_csv("종목시총_30년.csv", encoding="utf-8-sig", dtype={"code": str})
    mc.columns = [c.strip().lstrip("﻿") for c in mc.columns]
    mc["ym"] = pd.to_datetime(mc["date"]).dt.strftime("%Y-%m"); mc["code"] = mc["code"].str.zfill(6)
    mc["mcap"] = pd.to_numeric(mc["mcap"], errors="coerce"); mc = mc.dropna(subset=["mcap"])

    out = {}
    for y in range(2002, 2027):
        ym, prev = f"{y}-06", f"{y-1}-06"
        a, b = f[f.ym == ym].set_index("code"), f[f.ym == prev].set_index("code")
        if a.empty or b.empty: continue
        cm = a.index.intersection(b.index)
        df = pd.DataFrame(index=cm)
        df["bps"], df["bps0"] = a.loc[cm, "BPS"], b.loc[cm, "BPS"]
        df = df[(df.bps > 0) & (df.bps0 > 0)]
        m = mc[mc.ym <= ym].sort_values("ym").groupby("code").tail(1).set_index("code")["mcap"]
        df["mcap"] = df.index.map(m); df = df.dropna(subset=["mcap"])
        if len(df) < 50: continue
        out[ym] = sorted(df[df.mcap >= df.mcap.quantile(0.30)].index.tolist())
    return out


def gate_series():
    d = pd.read_csv("kospi_index_daily.csv", encoding="utf-8-sig"); d.columns = ["D", "C"]
    s = d.set_index(pd.to_datetime(d.D))["C"].resample("ME").last().dropna()
    s.index = s.index.strftime("%Y-%m")
    ma = s.rolling(10).mean()
    return s, (s >= ma)          # True = 방어 OFF = 보유


def curves(R, pl, hold, lo, hi):
    """상시보유 / 게이트 / KOSPI 세 곡선."""
    ym_all = [y for y in R.index if lo <= y <= hi]
    keys = sorted(pl.keys())
    eq_a = eq_g = 1.0; prev_in = None
    ca, cg = [], []
    for ym in ym_all:
        k = [x for x in keys if x <= ym]
        if not k: continue
        codes = [c for c in pl[k[-1]] if c in R.columns]
        r = R.loc[ym, codes].dropna()
        rp = float(r.mean()) if len(r) else 1.0
        if ym.endswith("-07"): rp -= C_POOL          # 연 1회 풀 교체 비용
        eq_a *= rp; ca.append((ym, eq_a))
        inpos = bool(hold.get(ym, True))
        rg = rp if inpos else 1.0
        if prev_in is not None and inpos != prev_in: rg -= C_SWITCH
        prev_in = inpos
        eq_g *= rg; cg.append((ym, eq_g))
    return (pd.Series(dict(ca)), pd.Series(dict(cg)))


def stat(c):
    yrs = len(c) / 12.0
    return dict(cagr=float(c.iloc[-1] ** (1/yrs) - 1), mdd=float((c/c.cummax()-1).min()),
                mult=float(c.iloc[-1]), months=len(c))


def kospi_stat(s, lo, hi):
    x = s[(s.index >= lo) & (s.index <= hi)]
    yrs = len(x)/12.0
    c = x/x.iloc[0]
    return dict(cagr=float((x.iloc[-1]/x.iloc[0])**(1/yrs)-1), mdd=float((c/c.cummax()-1).min()),
                mult=float(x.iloc[-1]/x.iloc[0]), months=len(x))


def selftest():
    R = panel(); pl = pools(); s, hold = gate_series()
    ok = [("월봉 수익패널", R.shape[1] > 2000), ("자격풀 연도수 >=20", len(pl) >= 20),
          ("게이트 시계열", len(hold) > 300)]
    a, g = curves(R, pl, hold, *TR)
    ok += [("훈련 곡선 생성", len(a) > 100 and len(g) == len(a)),
           ("곡선 양수", (a > 0).all() and (g > 0).all()),
           ("게이트가 상시보유와 다름", abs(a.iloc[-1]-g.iloc[-1]) > 1e-6)]
    for n, v in ok: print(("  OK   " if v else "  FAIL ") + n)
    print("self-test %d/%d" % (sum(v for _, v in ok), len(ok)))
    return all(v for _, v in ok)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true")
    if ap.parse_args().selftest: sys.exit(0 if selftest() else 1)
    R = panel(); pl = pools(); s, hold = gate_series()
    print("=" * 72); print("엔진08 자격풀 + 국면 게이트 — 격자 0개 · 검증예산 1회차"); print("=" * 72)
    res = {}
    for lab, (lo, hi) in (("훈련", TR), ("검증", VA)):
        a, g = curves(R, pl, hold, lo, hi); k = kospi_stat(s, lo, hi)
        sa, sg = stat(a), stat(g)
        res[lab] = dict(pool=sa, gate=sg, kospi=k)
        print("\n[%s %s ~ %s · %d개월]" % (lab, lo, hi, sa["months"]))
        print("  %-16s %9s %9s %9s" % ("", "배수", "CAGR", "MDD"))
        for n, v in (("자격풀 상시보유", sa), ("자격풀+게이트", sg), ("KOSPI 바이앤홀드", k)):
            print("  %-16s %8.2f배 %8.2f%% %8.1f%%" % (n, v["mult"], v["cagr"]*100, v["mdd"]*100))
        print("  게이트 효과: CAGR %+.2f%%p · MDD %+.1f%%p"
              % ((sg["cagr"]-sa["cagr"])*100, (sg["mdd"]-sa["mdd"])*100))
    v, t = res["검증"], res["훈련"]
    g1 = v["gate"]["cagr"] >= v["pool"]["cagr"]
    g2 = (v["gate"]["mdd"] - v["pool"]["mdd"]) >= G2_MDD
    g3 = v["gate"]["cagr"] >= v["kospi"]["cagr"] + G3_EXCESS
    g4 = (np.sign(t["gate"]["cagr"]-t["pool"]["cagr"]) == np.sign(v["gate"]["cagr"]-v["pool"]["cagr"])
          and np.sign(t["gate"]["mdd"]-t["pool"]["mdd"]) == np.sign(v["gate"]["mdd"]-v["pool"]["mdd"]))
    print("\n[4게이트]")
    print("  1 수익 훼손 없음 (게이트CAGR >= 풀CAGR)   : %+.2f%%p → %s"
          % ((v["gate"]["cagr"]-v["pool"]["cagr"])*100, "PASS" if g1 else "FAIL"))
    print("  2 MDD 10%%p 이상 개선                      : %+.1f%%p → %s"
          % ((v["gate"]["mdd"]-v["pool"]["mdd"])*100, "PASS" if g2 else "FAIL"))
    print("  3 KOSPI +3.0%%p 초과                       : %+.2f%%p → %s"
          % ((v["gate"]["cagr"]-v["kospi"]["cagr"])*100, "PASS" if g3 else "FAIL"))
    print("  4 훈련·검증 부호 일치                     : → %s" % ("PASS" if g4 else "FAIL"))
    allp = g1 and g2 and g3 and g4
    print("\n  최종: %s" % ("PASS" if allp else "FAIL"))
    if not allp and g2:
        print("  §7-4 부분 존치 후보: MDD 개선은 성립 → 리스크 관리 도구로 존치 검토")
    json.dump({"res": res, "gates": {"g1": bool(g1), "g2": bool(g2), "g3": bool(g3),
               "g4": bool(g4), "pass": bool(allp)}},
              open("엔진08_결과.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("\n저장: 엔진08_결과.json")


if __name__ == "__main__":
    main()
