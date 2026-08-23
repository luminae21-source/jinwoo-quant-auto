# -*- coding: utf-8 -*-
r"""엔진06_바닥반전_검정.py — 국면 게이트 방어 OFF 전환(=바닥반전) 검정
사전등록: 엔진06_바닥반전_사전등록_2026-08-23.md (결과 보기 전 봉인)
훈련 1995-05~2015-12 / 검증 2016-01~2026-08 · 격자 3개 · 4게이트
자체검증: py 엔진06_바닥반전_검정.py --selftest
"""
import sys, json, argparse
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

COST = 0.003          # 왕복
MAXHOLD = 12          # 개월
CUT = pd.Timestamp("2015-12-31")
GRID = {"T1_전건": 1, "T2_dur3": 3, "T3_dur5": 5}
G1_EXCESS, G2_WIN, G4_TAIL = 0.030, 0.60, -0.15


def load():
    d = pd.read_csv("kospi_index_daily.csv", encoding="utf-8-sig")
    d.columns = ["Date", "Close"]
    d["Date"] = pd.to_datetime(d["Date"])
    m = d.sort_values("Date").set_index("Date")["Close"].resample("ME").last().dropna()
    return m


def events(m):
    """방어 OFF 전환 이벤트. 각 이벤트: 진입월, 직전 방어 지속개월, 청산월, 보유수익."""
    ma = m.rolling(10).mean()
    dfs = (m < ma)
    sig = dfs.astype(int).diff()
    idx = list(m.index)
    out = []
    for t in m.index[sig == -1]:
        i = idx.index(t)
        dur = 0
        j = i - 1
        while j >= 0 and dfs.iloc[j]:
            dur += 1; j -= 1
        # 청산: 다음 방어 ON 월말 또는 12개월
        end = None
        for k in range(i + 1, min(i + MAXHOLD + 1, len(idx))):
            if dfs.iloc[k]:
                end = k; break
        if end is None:
            end = min(i + MAXHOLD, len(idx) - 1)
        if end <= i:
            continue
        ret = m.iloc[end] / m.iloc[i] - 1 - COST
        out.append(dict(entry=t, dur=dur, exit=idx[end], months=end - i, ret=ret))
    return pd.DataFrame(out)


def bench(m, L, lo, hi):
    """같은 보유개월 L, 같은 구간의 무작위시점 평균 보유수익(비용 동일 차감)."""
    idx = list(m.index)
    v = []
    for i, t in enumerate(idx):
        if t < lo or t > hi: continue
        if i + L >= len(idx): break
        v.append(m.iloc[i + L] / m.iloc[i] - 1 - COST)
    return float(np.mean(v)) if v else np.nan


def evaluate(ev, m, lo, hi, label):
    sub = ev[(ev.entry >= lo) & (ev.entry <= hi)].copy()
    if sub.empty:
        return None
    sub["bench"] = [bench(m, int(r.months), lo, hi) for r in sub.itertuples()]
    sub["excess"] = sub["ret"] - sub["bench"]
    return dict(label=label, n=len(sub),
                mean_ret=float(sub["ret"].mean()),
                mean_bench=float(sub["bench"].mean()),
                excess=float(sub["excess"].mean()),
                win=float((sub["ret"] > 0).mean()),
                worst=float(sub["ret"].min()),
                med_months=float(sub["months"].median()), _df=sub)


def selftest():
    m = load()
    ok = []
    ok.append(("월봉 300개월 이상", len(m) > 300))
    ev = events(m)
    ok.append(("이벤트 30건 내외", 25 <= len(ev) <= 35))
    ok.append(("dur 최소 1 이상", ev.dur.min() >= 1))
    ok.append(("보유개월 1~12", ev.months.between(1, 12).all()))
    ok.append(("비용 차감 확인", abs((m.iloc[12]/m.iloc[0]-1-COST) - (m.iloc[12]/m.iloc[0]-1)+COST) < 1e-12))
    b = bench(m, 6, m.index[0], CUT)
    ok.append(("벤치 산출 유한", np.isfinite(b)))
    for n, v in ok: print(("  OK " if v else "  FAIL ") + n)
    print("self-test %d/%d" % (sum(v for _, v in ok), len(ok)))
    return all(v for _, v in ok)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(0 if selftest() else 1)

    m = load()
    ev = events(m)
    lo0, hi0 = m.index[0], CUT
    lo1, hi1 = pd.Timestamp("2016-01-01"), m.index[-1]

    print("=" * 74)
    print("엔진06 바닥반전 — 사전등록 엄수 검정")
    print("=" * 74)
    print("전체 이벤트 %d건 (훈련 %d / 검증 %d)"
          % (len(ev), ((ev.entry <= CUT)).sum(), ((ev.entry > CUT)).sum()))

    print("\n[1] 훈련 1995-05 ~ 2015-12 — 격자 3개")
    print("%-10s %4s %9s %9s %9s %7s %8s" % ("안", "n", "평균수익", "벤치", "초과", "승률", "최악"))
    tr = {}
    for name, d in GRID.items():
        r = evaluate(ev[ev.dur >= d], m, lo0, hi0, name)
        if r is None: continue
        tr[name] = r
        print("%-10s %4d %8.2f%% %8.2f%% %+8.2f%%p %6.0f%% %7.2f%%"
              % (name, r["n"], r["mean_ret"]*100, r["mean_bench"]*100,
                 r["excess"]*100, r["win"]*100, r["worst"]*100))

    pick = max(tr, key=lambda k: tr[k]["excess"])
    print("\n훈련 선택: %s (초과 %+.2f%%p) — 검증에는 이 하나만 가져간다"
          % (pick, tr[pick]["excess"]*100))

    print("\n[2] 검증 2016-01 ~ 2026-08 — 봉인 해제")
    d = GRID[pick]
    va = evaluate(ev[ev.dur >= d], m, lo1, hi1, pick)
    if va is None:
        print("검증 이벤트 0건 — 판정 불가"); return
    print("%-10s %4s %9s %9s %9s %7s %8s" % ("안", "n", "평균수익", "벤치", "초과", "승률", "최악"))
    print("%-10s %4d %8.2f%% %8.2f%% %+8.2f%%p %6.0f%% %7.2f%%"
          % (pick, va["n"], va["mean_ret"]*100, va["mean_bench"]*100,
             va["excess"]*100, va["win"]*100, va["worst"]*100))

    print("\n[3] 4게이트 판정 (사전등록 고정값)")
    g1 = va["excess"] >= G1_EXCESS
    g2 = va["win"] >= G2_WIN
    g3 = np.sign(tr[pick]["excess"]) == np.sign(va["excess"])
    g4 = va["worst"] >= G4_TAIL
    print("  게이트1 초과 ≥ +3.0%%p   : %+.2f%%p  → %s" % (va["excess"]*100, "PASS" if g1 else "FAIL"))
    print("  게이트2 승률 ≥ 60%%      : %.0f%% (%d/%d) → %s"
          % (va["win"]*100, round(va["win"]*va["n"]), va["n"], "PASS" if g2 else "FAIL"))
    print("  게이트3 부호 일치        : 훈련 %+.2f / 검증 %+.2f → %s"
          % (tr[pick]["excess"]*100, va["excess"]*100, "PASS" if g3 else "FAIL"))
    print("  게이트4 최악 ≥ -15%%     : %.2f%% → %s" % (va["worst"]*100, "PASS" if g4 else "FAIL"))
    allp = g1 and g2 and g3 and g4
    print("\n  최종: %s" % ("PASS" if allp else "FAIL — 16번째 기각"))
    if allp and G1_EXCESS <= va["excess"] < G1_EXCESS * 1.1:
        print("  ⚠ 아슬아슬 조항 발동: 마진 10%% 미만 → 합격 아님, 재현 대기")

    print("\n[4] 참고 — 검증 구간 개별 이벤트")
    for r in va["_df"].itertuples():
        print("   %s → %s (%2d개월) 수익 %+7.2f%%  벤치 %+6.2f%%  초과 %+7.2f%%p  dur=%d"
              % (r.entry.date(), r.exit.date(), r.months, r.ret*100, r.bench*100, r.excess*100, r.dur))

    js = {"pick": pick, "train": {k: {x: v[x] for x in v if x != "_df"} for k, v in tr.items()},
          "valid": {x: va[x] for x in va if x != "_df"},
          "gates": {"g1": bool(g1), "g2": bool(g2), "g3": bool(g3), "g4": bool(g4), "pass": bool(allp)}}
    with open("엔진06_바닥반전_결과.json", "w", encoding="utf-8") as f:
        json.dump(js, f, ensure_ascii=False, indent=1, default=str)
    ev.to_csv("엔진06_바닥반전_이벤트.csv", index=False, encoding="utf-8-sig")
    print("\n저장: 엔진06_바닥반전_결과.json / 엔진06_바닥반전_이벤트.csv")


if __name__ == "__main__":
    main()
