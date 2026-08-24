# -*- coding: utf-8 -*-
r"""엔진07_재무변화율_검정.py — ΔROE(수익성 개선폭) 축 검정
사전등록: 엔진07_재무변화율_사전등록_2026-08-23.md (봉인 준수)
훈련 2002-06~2015-06 / 검증 2016-06~2025-06 · 격자 3개 · 4게이트 + 필터/선택자 분리
자체검증: py 엔진07_재무변화율_검정.py --selftest
"""
import sys, json, argparse
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

COST = 0.006                    # 연 1회 전량교체 왕복
GRID = {"G1_30": 30, "G2_50": 50, "G3_100": 100}
TR_LO, TR_HI = "2002-06", "2015-06"
VA_LO, VA_HI = "2016-06", "2025-06"
G1_EXCESS, G2_WINRATE, G4_TAIL = 0.030, 0.60, -0.10
SPLIT_HI, SPLIT_LO = 3.0, 1/3.0


def load_prices():
    fr = []
    for m in ("KOSPI", "KOSDAQ"):
        d = pd.read_csv(f"_월봉종가캐시_{m}.csv", encoding="utf-8-sig", dtype={"code": str})
        fr.append(d)
    d = pd.concat(fr, ignore_index=True)
    d["code"] = d["code"].str.zfill(6)
    d = d[d["close"] > 0].drop_duplicates(["code", "ym"], keep="last")
    P = d.pivot(index="ym", columns="code", values="close").sort_index()
    R = P / P.shift(1)
    R = R.mask((R > SPLIT_HI) | (R < SPLIT_LO), 1.0)
    R.iloc[0] = 1.0
    adj = R.fillna(1.0).cumprod().where(P.notna())
    return adj


def load_fin():
    fr = []
    for m in ("KOSPI", "KOSDAQ"):
        d = pd.read_csv(f"종목재무_KRX_{m}.csv", encoding="utf-8-sig", dtype={"code": str})
        d.columns = [c.strip().lstrip("﻿") for c in d.columns]
        fr.append(d[["date", "code", "BPS", "EPS"]])
    d = pd.concat(fr, ignore_index=True)
    d["code"] = d["code"].str.zfill(6)
    d["ym"] = d["date"].str[:7]
    for c in ("BPS", "EPS"):
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d = d.dropna(subset=["BPS", "EPS"]).drop_duplicates(["code", "ym"], keep="last")
    return d


def load_mcap():
    mc = pd.read_csv("종목시총_30년.csv", encoding="utf-8-sig", dtype={"code": str})
    mc.columns = [c.strip().lstrip("﻿") for c in mc.columns]
    mc["ym"] = pd.to_datetime(mc["date"]).dt.strftime("%Y-%m")
    mc["code"] = mc["code"].str.zfill(6)
    mc["mcap"] = pd.to_numeric(mc["mcap"], errors="coerce")
    return mc[["code", "ym", "mcap"]].dropna()


def anchors(lo, hi):
    y0, y1 = int(lo[:4]), int(hi[:4])
    return [f"{y}-06" for y in range(y0, y1 + 1)]


def build(fin, mcap, adj, ym):
    """기준월 ym의 자격풀 + ΔROE. 사전등록 §1·§2 그대로."""
    y = int(ym[:4]); prev = f"{y-1}-06"
    a = fin[fin.ym == ym].set_index("code")
    b = fin[fin.ym == prev].set_index("code")
    if a.empty or b.empty: return None
    common = a.index.intersection(b.index)
    if len(common) < 50: return None
    df = pd.DataFrame(index=common)
    df["bps"], df["eps"] = a.loc[common, "BPS"], a.loc[common, "EPS"]
    df["bps0"], df["eps0"] = b.loc[common, "BPS"], b.loc[common, "EPS"]
    df = df[(df.bps > 0) & (df.bps0 > 0)]
    df["droe"] = df.eps / df.bps - df.eps0 / df.bps0
    # 시총 하위 30% 제외 (PIT)
    mc = mcap[mcap.ym <= ym].sort_values("ym").groupby("code").tail(1).set_index("code")["mcap"]
    df["mcap"] = df.index.map(mc)
    df = df.dropna(subset=["mcap"])
    if df.empty: return None
    df = df[df.mcap >= df.mcap.quantile(0.30)]
    # 12개월 전진 수익
    idx = list(adj.index)
    if ym not in idx: return None
    i = idx.index(ym); j = i + 12
    if j >= len(idx): return None
    a0, a1 = adj.iloc[i], adj.iloc[j]
    df["ret"] = [(a1.get(c, np.nan) / a0.get(c, np.nan) - 1.0) if (c in adj.columns) else np.nan
                 for c in df.index]
    df = df.dropna(subset=["ret", "droe"])
    return df if len(df) >= 50 else None


def run_period(fin, mcap, adj, lo, hi):
    rows = []
    for ym in anchors(lo, hi):
        d = build(fin, mcap, adj, ym)
        if d is None: continue
        pool = float(d.ret.mean()) - COST
        r = {"ym": ym, "n_pool": len(d), "pool": pool}
        s = d.sort_values("droe", ascending=False)
        for name, N in GRID.items():
            if len(s) < N * 2: continue
            r[name] = float(s.head(N).ret.mean()) - COST
            r[name + "_bot"] = float(s.tail(N).ret.mean()) - COST
        # 5분위 단조성
        q = pd.qcut(d.droe.rank(method="first"), 5, labels=False)
        for k in range(5):
            r[f"q{k+1}"] = float(d.ret[q == k].mean()) - COST
        rows.append(r)
    return pd.DataFrame(rows)


def summarize(df, key):
    if key not in df: return None
    x = df.dropna(subset=[key])
    if x.empty: return None
    return dict(n=len(x), mean=float(x[key].mean()), pool=float(x["pool"].mean()),
                excess=float((x[key] - x["pool"]).mean()),
                winrate=float((x[key] > x["pool"]).mean()),
                worst=float(x[key].min()), pool_worst=float(x["pool"].min()))


def selftest():
    adj = load_prices(); fin = load_fin(); mc = load_mcap()
    ok = [("월봉 패널 >2000종", adj.shape[1] > 2000),
          ("재무 로드 >300k행", len(fin) > 300000),
          ("시총 로드", len(mc) > 100000)]
    d = build(fin, mc, adj, "2010-06")
    ok.append(("2010-06 자격풀 구성", d is not None and len(d) > 200))
    if d is not None:
        ok.append(("ΔROE 유한", np.isfinite(d.droe).all()))
        ok.append(("전진수익 유한", np.isfinite(d.ret).all()))
    ok.append(("비용 상수 0.6%", abs(COST - 0.006) < 1e-9))
    for n, v in ok: print(("  OK   " if v else "  FAIL ") + n)
    print("self-test %d/%d" % (sum(v for _, v in ok), len(ok)))
    return all(v for _, v in ok)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true")
    if ap.parse_args().selftest: sys.exit(0 if selftest() else 1)

    adj = load_prices(); fin = load_fin(); mc = load_mcap()
    print("=" * 76)
    print("엔진07 재무 변화율(ΔROE) — 사전등록 엄수 검정 · 검증예산 1회차")
    print("=" * 76)

    tr = run_period(fin, mc, adj, TR_LO, TR_HI)
    print("\n[1] 훈련 2002-06 ~ 2015-06 — 형성 %d회" % len(tr))
    print("%-8s %5s %9s %9s %10s %8s" % ("격자", "n", "전략", "자격풀EW", "초과", "승률"))
    tsum = {}
    for name in GRID:
        s = summarize(tr, name)
        if not s: continue
        tsum[name] = s
        print("%-8s %5d %8.2f%% %8.2f%% %+9.2f%%p %7.0f%%"
              % (name, s["n"], s["mean"]*100, s["pool"]*100, s["excess"]*100, s["winrate"]*100))

    pos = [k for k, v in tsum.items() if v["excess"] > 0]
    print("\n§4-1 일관성 요건: 양(+) 초과 격자 %d개 / 3개" % len(pos))
    if len(pos) < 2:
        print("→ 2개 미만 = 노이즈. **검증을 열지 않고 종료한다.** 검증예산 소모 없음.")
        json.dump({"aborted": True, "train": tsum}, open("엔진07_결과.json", "w", encoding="utf-8"),
                  ensure_ascii=False, indent=1)
        tr.to_csv("엔진07_훈련.csv", index=False, encoding="utf-8-sig")
        return

    pick = max(tsum, key=lambda k: tsum[k]["excess"])
    print("→ 요건 충족. 훈련 선택: %s (초과 %+.2f%%p) — 검증에는 이 하나만"
          % (pick, tsum[pick]["excess"]*100))

    va = run_period(fin, mc, adj, VA_LO, VA_HI)
    v = summarize(va, pick)
    print("\n[2] 검증 2016-06 ~ 2025-06 — 봉인 해제 · 형성 %d회" % len(va))
    print("%-8s %5s %9s %9s %10s %8s %9s" % ("격자", "n", "전략", "자격풀EW", "초과", "승률", "최악"))
    print("%-8s %5d %8.2f%% %8.2f%% %+9.2f%%p %7.0f%% %8.2f%%"
          % (pick, v["n"], v["mean"]*100, v["pool"]*100, v["excess"]*100,
             v["winrate"]*100, v["worst"]*100))

    print("\n[3] 4게이트")
    g1 = v["excess"] >= G1_EXCESS
    g2 = v["winrate"] >= G2_WINRATE
    g3 = np.sign(tsum[pick]["excess"]) == np.sign(v["excess"])
    g4 = v["worst"] >= v["pool_worst"] + G4_TAIL
    print("  1 초과 ≥ +3.0%%p : %+.2f%%p → %s" % (v["excess"]*100, "PASS" if g1 else "FAIL"))
    print("  2 승률 ≥ 60%%    : %.0f%% (%d/%d) → %s"
          % (v["winrate"]*100, round(v["winrate"]*v["n"]), v["n"], "PASS" if g2 else "FAIL"))
    print("  3 부호 일치     : 훈련 %+.2f / 검증 %+.2f → %s"
          % (tsum[pick]["excess"]*100, v["excess"]*100, "PASS" if g3 else "FAIL"))
    print("  4 꼬리          : 전략 %.2f%% vs 풀최악 %.2f%% (허용 −10%%p) → %s"
          % (v["worst"]*100, v["pool_worst"]*100, "PASS" if g4 else "FAIL"))
    allp = g1 and g2 and g3 and g4
    print("\n  최종: %s" % ("PASS" if allp else "FAIL — 17번째 기각"))
    if allp and G1_EXCESS <= v["excess"] < G1_EXCESS*1.1:
        print("  ⚠ 아슬아슬 조항 발동 — 합격 아님, 재현 대기")

    print("\n[4] §7-4 부분 생존 — 필터 성능 (검증 구간)")
    bot = summarize(va, pick + "_bot")
    if bot:
        print("  하위 %s: %.2f%% vs 자격풀EW %.2f%% → 초과 %+.2f%%p (승률 %.0f%%)"
              % (pick, bot["mean"]*100, bot["pool"]*100, bot["excess"]*100, bot["winrate"]*100))
        print("  → 하위가 유의하게 지면 '고르진 못해도 걸러낼 수는 있다'(필터 존치)")

    print("\n[5] 5분위 단조성 (검증 구간 평균)")
    for k in range(1, 6):
        c = f"q{k}"
        if c in va: print("   Q%d(ΔROE 하위→상위) %+7.2f%%" % (k, va[c].mean()*100))

    json.dump({"pick": pick, "train": tsum, "valid": v, "filter": bot,
               "gates": {"g1": bool(g1), "g2": bool(g2), "g3": bool(g3), "g4": bool(g4),
                         "pass": bool(allp)}},
              open("엔진07_결과.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    tr.to_csv("엔진07_훈련.csv", index=False, encoding="utf-8-sig")
    va.to_csv("엔진07_검증.csv", index=False, encoding="utf-8-sig")
    print("\n저장: 엔진07_결과.json / 엔진07_훈련.csv / 엔진07_검증.csv")


if __name__ == "__main__":
    main()
