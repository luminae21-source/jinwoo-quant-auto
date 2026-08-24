# -*- coding: utf-8 -*-
r"""엔진09_그릇교체_검정.py — 게이트는 고정, 그릇만 3개 바꿔 동시 검정
사전등록: 엔진09_그릇교체_사전등록_2026-08-24.md (봉인) · 자격풀게이트 축 2회차(임계 x2)
자체검증: py 엔진09_그릇교체_검정.py --selftest
"""
import sys, json, argparse
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

C_SW, C_POOL = 0.003, 0.006
TR = ("2002-06", "2015-12"); VA = ("2016-01", "2026-06")
G2_MDD, G3_EXCESS = 0.10, 0.060      # 2회차 보정: 0.030 -> 0.060
SPLIT_HI, SPLIT_LO = 3.0, 1/3.0
TOP_C = 200


def panel():
    fr = [pd.read_csv(f"_월봉종가캐시_{m}.csv", encoding="utf-8-sig", dtype={"code": str})
          for m in ("KOSPI", "KOSDAQ")]
    d = pd.concat(fr, ignore_index=True); d["code"] = d["code"].str.zfill(6)
    d = d[d.close > 0].drop_duplicates(["code", "ym"], keep="last")
    P = d.pivot(index="ym", columns="code", values="close").sort_index()
    R = P / P.shift(1); R = R.mask((R > SPLIT_HI) | (R < SPLIT_LO), 1.0); R.iloc[0] = 1.0
    return R.where(P.notna())


def pools():
    """매년 6월 자격풀 + 그 시점 시총 (엔진07 §2 정의)."""
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
        out[ym] = df[df.mcap >= df.mcap.quantile(0.30)]["mcap"].sort_values(ascending=False)
    return out


def kospi_m():
    d = pd.read_csv("kospi_index_daily.csv", encoding="utf-8-sig"); d.columns = ["D", "C"]
    s = d.set_index(pd.to_datetime(d.D))["C"].resample("ME").last().dropna()
    s.index = s.index.strftime("%Y-%m")
    return s


def bowl_returns(R, pl, ks, kind, lo, hi):
    """그릇별 월간 총수익비 시리즈 (게이트 미적용). kind: A/B/C"""
    yms = [y for y in R.index if lo <= y <= hi]
    if kind == "A":
        r = ks.pct_change().add(1.0)
        return pd.Series({y: float(r.get(y, 1.0)) for y in yms})
    keys = sorted(pl.keys())
    out, w = {}, None
    cur_key = None
    for ym in yms:
        k = [x for x in keys if x <= ym]
        if not k: out[ym] = 1.0; continue
        if k[-1] != cur_key:                      # 6월 재구성
            cur_key = k[-1]
            s = pl[cur_key]
            if kind == "C": s = s.head(TOP_C)
            codes = [c for c in s.index if c in R.columns]
            if kind == "B":
                v = s.loc[codes]; w = (v / v.sum()).to_dict()
            else:
                w = {c: 1.0/len(codes) for c in codes} if codes else {}
            first_month_of_year = True
        rr = R.loc[ym]
        tot, wt = 0.0, 0.0
        nw = {}
        for c, wi in w.items():
            x = rr.get(c, np.nan)
            if not np.isfinite(x): x = 1.0
            tot += wi * x; wt += wi; nw[c] = wi * x
        g = (tot / wt) if wt > 0 else 1.0
        w = {c: v / tot for c, v in nw.items()} if tot > 0 else w   # 드리프트 반영
        if ym.endswith("-07"): g -= C_POOL
        out[ym] = g
    return pd.Series(out)


def apply_gate(r, hold):
    eq_a = eq_g = 1.0; prev = None; ca, cg = {}, {}
    for ym, x in r.items():
        eq_a *= x; ca[ym] = eq_a
        inpos = bool(hold.get(ym, True))
        g = x if inpos else 1.0
        if prev is not None and inpos != prev: g -= C_SW
        prev = inpos
        eq_g *= g; cg[ym] = eq_g
    return pd.Series(ca), pd.Series(cg)


def stat(c):
    yrs = len(c)/12.0
    return dict(cagr=float(c.iloc[-1]**(1/yrs)-1), mdd=float((c/c.cummax()-1).min()),
                mult=float(c.iloc[-1]), months=len(c))


def run(R, pl, ks, hold, lo, hi):
    res = {}
    for kind in ("A", "B", "C"):
        r = bowl_returns(R, pl, ks, kind, lo, hi)
        a, g = apply_gate(r, hold)
        res[kind] = dict(plain=stat(a), gated=stat(g))
    x = ks[(ks.index >= lo) & (ks.index <= hi)]
    yrs = len(x)/12.0; cc = x/x.iloc[0]
    res["KOSPI"] = dict(cagr=float((x.iloc[-1]/x.iloc[0])**(1/yrs)-1),
                        mdd=float((cc/cc.cummax()-1).min()), mult=float(x.iloc[-1]/x.iloc[0]))
    return res


def show(lab, res):
    print("\n[%s]" % lab)
    print("  %-22s %8s %9s %9s" % ("", "배수", "CAGR", "MDD"))
    for k, nm in (("A", "A KOSPI지수"), ("B", "B 자격풀 시총가중"), ("C", "C 대형200 등가중")):
        p, g = res[k]["plain"], res[k]["gated"]
        print("  %-22s %7.2f배 %8.2f%% %8.1f%%   (게이트 없음)" % (nm, p["mult"], p["cagr"]*100, p["mdd"]*100))
        print("  %-22s %7.2f배 %8.2f%% %8.1f%%   게이트 기여 CAGR %+.2f%%p · MDD %+.1f%%p"
              % ("  + 게이트", g["mult"], g["cagr"]*100, g["mdd"]*100,
                 (g["cagr"]-p["cagr"])*100, (g["mdd"]-p["mdd"])*100))
    kk = res["KOSPI"]
    print("  %-22s %7.2f배 %8.2f%% %8.1f%%" % ("KOSPI 바이앤홀드", kk["mult"], kk["cagr"]*100, kk["mdd"]*100))


def selftest():
    R = panel(); pl = pools(); ks = kospi_m()
    ma = ks.rolling(10).mean(); hold = (ks >= ma)
    ok = [("월봉 패널 >2000종", R.shape[1] > 2000), ("자격풀 연도 >=20", len(pl) >= 20),
          ("KOSPI 월봉 >300", len(ks) > 300)]
    for kind in ("A", "B", "C"):
        r = bowl_returns(R, pl, ks, kind, *TR)
        ok.append((f"{kind}안 수익 시리즈 생성", len(r) > 100 and np.isfinite(r).all()))
    rB = bowl_returns(R, pl, ks, "B", *TR)
    ok.append(("B안 시총가중이 A와 다름", abs(rB.prod() - bowl_returns(R, pl, ks, "A", *TR).prod()) > 1e-6))
    a, g = apply_gate(rB, hold)
    ok.append(("게이트 적용시 곡선 분화", abs(a.iloc[-1]-g.iloc[-1]) > 1e-6))
    ok.append(("2회차 보정 임계 6.0%", abs(G3_EXCESS - 0.060) < 1e-9))
    for n, v in ok: print(("  OK   " if v else "  FAIL ") + n)
    print("self-test %d/%d" % (sum(v for _, v in ok), len(ok)))
    return all(v for _, v in ok)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true")
    if ap.parse_args().selftest: sys.exit(0 if selftest() else 1)
    R = panel(); pl = pools(); ks = kospi_m()
    hold = (ks >= ks.rolling(10).mean())
    print("="*74); print("엔진09 그릇 교체 — 게이트 고정 · 자격풀게이트 축 2회차(임계 x2)"); print("="*74)

    tr = run(R, pl, ks, hold, *TR); show("훈련 2002-06 ~ 2015-12", tr)
    kt = tr["KOSPI"]["cagr"]
    pos = [k for k in ("A", "B", "C") if tr[k]["gated"]["cagr"] > kt]
    print("\n§2-1 일관성 요건: KOSPI 초과 %d안 / 3안 (%s)" % (len(pos), ", ".join(pos) or "없음"))
    if len(pos) < 2:
        print("→ 2안 미만 = 노이즈. **검증 미개봉 종료.** 예산 소모 없음.")
        json.dump({"aborted": True, "train": tr}, open("엔진09_결과.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1, default=str)
        return
    pick = max(pos, key=lambda k: tr[k]["gated"]["cagr"])
    print("→ 요건 충족. 훈련 선택: %s안 — 검증에는 이 하나만" % pick)

    va = run(R, pl, ks, hold, *VA); show("검증 2016-01 ~ 2026-06 (봉인 해제)", va)

    p, g, kk = va[pick]["plain"], va[pick]["gated"], va["KOSPI"]
    tp, tg = tr[pick]["plain"], tr[pick]["gated"]
    g1 = g["cagr"] >= p["cagr"]
    g2 = (g["mdd"] - p["mdd"]) >= G2_MDD
    g3 = g["cagr"] >= kk["cagr"] + G3_EXCESS
    g4 = (np.sign(tg["cagr"]-tp["cagr"]) == np.sign(g["cagr"]-p["cagr"])
          and np.sign(tg["mdd"]-tp["mdd"]) == np.sign(g["mdd"]-p["mdd"]))
    print("\n[4게이트 · %s안 · 2회차 보정]" % pick)
    print("  1 수익 훼손 없음            : %+.2f%%p → %s" % ((g["cagr"]-p["cagr"])*100, "PASS" if g1 else "FAIL"))
    print("  2 MDD 10%%p 이상 개선        : %+.1f%%p → %s" % ((g["mdd"]-p["mdd"])*100, "PASS" if g2 else "FAIL"))
    print("  3 KOSPI +6.0%%p 초과(보정)   : %+.2f%%p → %s" % ((g["cagr"]-kk["cagr"])*100, "PASS" if g3 else "FAIL"))
    print("  4 훈련·검증 부호 일치       : → %s" % ("PASS" if g4 else "FAIL"))
    allp = g1 and g2 and g3 and g4
    print("\n  최종: %s" % ("PASS" if allp else "FAIL — 18번째 기각"))
    if not allp and g2: print("  §7-4 부분 존치 후보: MDD 개선 성립")

    print("\n[§5 게이트 기여도 — 그릇별 재측정 (합격 무관 필수 기록)]")
    for k, nm in (("A", "KOSPI지수"), ("B", "자격풀 시총가중"), ("C", "대형200 등가중")):
        d_ = va[k]
        print("  %-16s 검증 CAGR %+.2f%%p · MDD %+.1f%%p"
              % (nm, (d_["gated"]["cagr"]-d_["plain"]["cagr"])*100,
                 (d_["gated"]["mdd"]-d_["plain"]["mdd"])*100))
    print("  (엔진08 등가중 자격풀 기준값: CAGR +9.61%p · MDD +14.7%p)")

    json.dump({"pick": pick, "train": tr, "valid": va,
               "gates": {"g1": bool(g1), "g2": bool(g2), "g3": bool(g3), "g4": bool(g4), "pass": bool(allp)}},
              open("엔진09_결과.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    print("\n저장: 엔진09_결과.json")


if __name__ == "__main__":
    main()
