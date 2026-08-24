#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""검정_30년_패널.py — 할로윈·TOM·하순·저점고점을 30년 종목패널에서 재판정

★ 사전등록서: 가상매매\검증\30년_재검정_사전등록.md
   데이터를 보기 전에 규칙을 고정했다. 결과를 보고 고치지 않는다.

  · OOS 분할: IN 1995~2012 / OOS 2013~2026  (봉인)
  · 창(window)은 전부 논문이 사전 정의 — 튜닝 금지
  · 판정: (A)IN유의 (B)이상치강건 (C)OOS생존 (D)비용통과
          (C) 실패 → 기각. 예외 없다.

입력: 종목일봉_30년_KOSPI.csv · 종목일봉_30년_KOSDAQ.csv · 종목시총_30년.csv
산출: 가상매매\검증\30년_재검정_결과.md

사용:
  py 검정_30년_패널.py                 # 전체
  py 검정_30년_패널.py --market KOSDAQ # 코스닥만
  py 검정_30년_패널.py --self-test
"""
import os, sys, argparse, warnings
from datetime import date
warnings.filterwarnings("ignore")

BASE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(BASE, "가상매매", "검증", "30년_재검정_결과.md")

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ── 사전등록 파라미터 (결과 보기 전 고정) ──────────────────────────────────
# 데이터: KOSPI 1996~ / KOSDAQ 1997~ (탐침으로 확인. 1995는 KRX가 안 준다)
IN_START = 1996        # IN: 1996~2012 (17년)
IN_END = 2012
OOS_START = 2013       # OOS: 2013~2026 (14년)  ← 봉인
# ※ 분할점 2012/2013 은 데이터를 보기 전에 정했고, 그대로 유지한다.
WINTER = {11, 12, 1, 2, 3, 4}
TOM_T = (1, 2, 3)      # 월초 +1~+3
TOM_RD = -1            # 월말 마지막일
LATE_RD = (-9, -8, -7, -6, -5)
BUY_RD, SELL_T = -7, 3       # ④ 저점→고점
COSTS = (0.0, 0.45, 0.70)    # 왕복 % (한국 매도세 0.18 + 수수료 + 슬리피지)
GATE_A, GATE_B, GATE_C = 0.05, 0.10, 0.05
N_TESTS = 12           # 4가설 × 3분위 → Bonferroni


def load(markets):
    import pandas as pd
    fs = []
    for m in markets:
        p = os.path.join(BASE, f"종목일봉_30년_{m}.csv")
        if not os.path.exists(p):
            print(f"  [없음] {os.path.basename(p)} — 먼저 종목패널_30년_수집.bat 실행")
            continue
        d = pd.read_csv(p, usecols=["code", "date", "close"], dtype={"code": str},
                        encoding="utf-8-sig")
        d["mkt"] = m
        fs.append(d)
        print(f"  {os.path.basename(p)}: {len(d):,}행")
    if not fs:
        return None
    d = pd.concat(fs, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d["close"] = pd.to_numeric(d["close"], errors="coerce")
    d = d.dropna(subset=["date", "close"])
    d = d[d["close"] > 0].sort_values(["code", "date"])
    d["ret"] = d.groupby("code", sort=False)["close"].pct_change() * 100
    d = d.dropna(subset=["ret"])
    n0 = len(d)
    d = d[d["ret"].abs() < 30]          # 액면분할·이상치 제거
    print(f"  수익률 {len(d):,}행 (이상치 |r|>30% 제외 {n0-len(d):,})")
    d["ym"] = d["date"].dt.year * 12 + d["date"].dt.month
    return d


def add_mcap_tercile(d):
    import pandas as pd, numpy as np
    p = os.path.join(BASE, "종목시총_30년.csv")
    if not os.path.exists(p):
        print("  [경고] 종목시총_30년.csv 없음 → 시총 분위 생략")
        d["q"] = np.nan
        return d
    mc = pd.read_csv(p, dtype={"code": str}, encoding="utf-8-sig")
    mc["date"] = pd.to_datetime(mc["date"], errors="coerce")
    mc["mcap"] = pd.to_numeric(mc["mcap"], errors="coerce")
    mc = mc.dropna()
    mc["ym"] = mc["date"].dt.year * 12 + mc["date"].dt.month
    mc = mc.groupby(["code", "ym"])["mcap"].last().reset_index()
    mc["ym"] += 1                        # 전월 시총 → 당월 사용 (룩어헤드 차단)
    d = d.merge(mc, on=["code", "ym"], how="left")
    d["q"] = d.groupby("ym")["mcap"].transform(
        lambda s: pd.qcut(s, 3, labels=["소", "중", "대"], duplicates="drop")
        if s.notna().sum() > 30 else np.nan)
    print(f"  시총 매칭률 {d['mcap'].notna().mean()*100:.1f}%")
    return d


def calendar(d):
    import pandas as pd
    cal = pd.DataFrame({"date": sorted(d["date"].unique())})
    cal["ym"] = cal["date"].dt.year * 12 + cal["date"].dt.month
    g = cal.groupby("ym")
    cal["t"] = g.cumcount() + 1
    cal["n"] = g["date"].transform("size")
    cal["rd"] = cal["t"] - cal["n"] - 1
    return cal[["date", "t", "rd"]]


# ── 검정 ───────────────────────────────────────────────────────────────────
def paired(x, mask, drop_k=0):
    """월별 대응표본. x: EW 일간수익 + t/rd. 반환 (차이, 중앙값차, t, p, wilcox, n)."""
    import pandas as pd
    from scipy import stats
    rows = []
    for ym, gr in x.assign(M=mask).groupby("ym"):
        a = gr[gr.M]["ret"]
        b = gr[~gr.M]["ret"]
        if len(a) >= 3 and len(b) >= 8:
            rows.append((a.mean(), b.mean()))
    if len(rows) < 12:
        return None
    r = pd.DataFrame(rows, columns=["A", "B"])
    r["d"] = r.A - r.B
    if drop_k:
        r = r.drop(r["d"].abs().nlargest(drop_k).index)
    t, p = stats.ttest_rel(r.A, r.B)
    w = stats.wilcoxon(r.A, r.B)
    return r["d"].mean(), r["d"].median(), t, p, w.pvalue, len(r)


def halloween(m, drop_k=0):
    import pandas as pd
    from scipy import stats
    mm = m
    if drop_k:
        mm = m.drop(list(m.nsmallest(drop_k).index) + list(m.nlargest(drop_k).index))
    w = mm[[i.month in WINTER for i in mm.index]]
    s = mm[[i.month not in WINTER for i in mm.index]]
    if len(w) < 6 or len(s) < 6:
        return None
    t, p = stats.ttest_ind(w, s, equal_var=False)
    _, pu = stats.mannwhitneyu(w, s, alternative="two-sided")
    return w.mean() - s.mean(), w.median() - s.median(), t, p, pu, len(mm)


def monthly(e):
    import pandas as pd
    m = (1 + e["ret"] / 100).groupby([e.index.year, e.index.month]).prod() - 1
    m = m * 100
    m.index = pd.to_datetime([f"{y}-{mo:02d}-01" for y, mo in m.index])
    return m.iloc[:-1]          # 미완결 마지막 달 제외


def verdict(a, b, c):
    """사전등록 판정. a/b/c = (p값 or None)"""
    if a is None or c is None:
        return "판정불가(표본부족)"
    if c >= GATE_C:
        return "기각 (OOS 실패)"
    if b is None or b >= GATE_B:
        return "기각 (이상치 의존)"
    if a >= GATE_A:
        return "기각 (IN 유의 아님)"
    return "채택 후보 → 비용 관문(D)으로"


def run(markets):
    import pandas as pd, numpy as np
    print("=" * 84)
    print("30년 종목패널 재검정 — 사전등록서대로 (30년_재검정_사전등록.md)")
    print("=" * 84)
    print(f"  IN 1995~{IN_END}  ·  OOS {OOS_START}~2026 (봉인)  ·  Bonferroni ×{N_TESTS}\n")

    d = load(markets)
    if d is None:
        return 2
    d = add_mcap_tercile(d)
    cal = calendar(d)
    d = d.merge(cal, on="date", how="left")
    d["yr"] = d["date"].dt.year
    print(f"  커버리지 {d.date.min().date()} ~ {d.date.max().date()} · {d.code.nunique():,}종목\n")

    L = ["# 30년 종목패널 재검정 — 결과\n",
         f"\n*{date.today()} · 사전등록서: `30년_재검정_사전등록.md`*\n",
         f"*IN 1995~{IN_END} / **OOS {OOS_START}~2026 (봉인)** · Bonferroni ×{N_TESTS}*\n",
         f"*종목 {d.code.nunique():,}개 (상폐 포함) · {d.date.min().date()}~{d.date.max().date()}*\n",
         "\n*투자자문 아님. 결정·책임은 본인.*\n\n---\n"]

    segs = [("전체", None), ("시총 소", "소"), ("시총 중", "중"), ("시총 대", "대")]
    for sname, q in segs:
        sub = d if q is None else d[d["q"] == q]
        if len(sub) < 10000:
            continue
        ew = sub.groupby("date").agg(ret=("ret", "mean")).sort_index()
        x = ew.join(cal.set_index("date"))
        x["ym"] = x.index.year * 12 + x.index.month
        x["yr"] = x.index.year
        xin = x[x.yr <= IN_END]
        xoos = x[x.yr >= OOS_START]

        print("━" * 84)
        print(f"■ {sname}   ({len(ew):,}거래일)")
        print("━" * 84)
        L.append(f"\n## {sname}\n\n")
        L.append("| 가설 | 구간 | 차이 | 중앙값차 | t | p | Bonf×12 | 비모수 p | n | |\n")
        L.append("|---|---|---|---|---|---|---|---|---|---|\n")

        res = {}
        # ① 할로윈
        for lbl, xx in [("IN", xin), ("OOS", xoos), ("이상치6제외", x)]:
            dk = 3 if lbl == "이상치6제외" else 0
            r = halloween(monthly(xx if lbl != "이상치6제외" else xin), dk)
            if r is None:
                continue
            diff, md, t, p, pu, n = r
            res.setdefault("①할로윈", {})[lbl] = p
            bf = min(p * N_TESTS, 1.0)
            mk = "✅" if p < 0.05 else ("△" if p < 0.10 else "❌")
            print(f"  ① 할로윈   {lbl:<10} {diff:+7.3f}%p  t={t:5.2f}  p={p:.4f}  MWU={pu:.4f}  n={n} {mk}")
            L.append(f"| ① 할로윈 | {lbl} | {diff:+.3f}%p | {md:+.3f}%p | {t:.2f} | **{p:.4f}** | {bf:.4f} | {pu:.4f} | {n} | {mk} |\n")

        # ②③ TOM / 하순
        for hname, mask_fn in [("②월초TOM", lambda z: (z.rd == TOM_RD) | (z.t.isin(TOM_T))),
                               ("③하순", lambda z: z.rd.isin(LATE_RD))]:
            for lbl, xx, dk in [("IN", xin, 0), ("OOS", xoos, 0), ("이상치6제외", xin, 6)]:
                r = paired(xx, mask_fn(xx), dk)
                if r is None:
                    continue
                diff, md, t, p, pw, n = r
                res.setdefault(hname, {})[lbl] = p
                bf = min(p * N_TESTS, 1.0)
                mk = "✅" if p < 0.05 else ("△" if p < 0.10 else "❌")
                print(f"  {hname:<9} {lbl:<10} {diff:+7.3f}%p  t={t:5.2f}  p={p:.4f}  Wil={pw:.4f}  n={n} {mk}")
                L.append(f"| {hname} | {lbl} | {diff:+.3f}%p | {md:+.3f}%p | {t:.2f} | **{p:.4f}** | {bf:.4f} | {pw:.4f} | {n} | {mk} |\n")

        # ④ 저점→고점
        px = (1 + x["ret"] / 100).cumprod().to_frame("px").join(x[["t", "rd", "ym", "yr"]])
        from scipy import stats
        for lbl, lo, hi in [("IN", 1995, IN_END), ("OOS", OOS_START, 2026)]:
            for cost in COSTS:
                tr = []
                z = px[(px.yr >= lo) & (px.yr <= hi)]
                for ym in sorted(z.ym.unique()):
                    b = z[(z.ym == ym) & (z.rd == BUY_RD)]
                    s = px[(px.ym == ym + 1) & (px.t == SELL_T)]
                    if len(b) == 1 and len(s) == 1:
                        tr.append((s.px.iloc[0] / b.px.iloc[0] - 1) * 100 - cost)
                if len(tr) < 12:
                    continue
                tr = np.array(tr)
                t, p = stats.ttest_1samp(tr, 0)
                if cost == 0.45:
                    res.setdefault("④저점고점", {})[lbl] = p
                mk = "✅" if p < 0.05 else "❌"
                L.append(f"| ④ 저점→고점(비용{cost}%) | {lbl} | {tr.mean():+.3f}%/회 | — | {t:.2f} | **{p:.4f}** | — | 승률 {(tr>0).mean()*100:.0f}% | {len(tr)} | {mk} |\n")
                if cost in (0.0, 0.45):
                    print(f"  ④저점고점 {lbl:<6}비용{cost:<5} {tr.mean():+6.3f}%/회 승률{(tr>0).mean()*100:4.0f}% p={p:.4f} {mk}")

        # 판정
        L.append("\n**사전등록 판정**\n\n| 가설 | (A) IN | (B) 이상치 | (C) OOS | 판정 |\n|---|---|---|---|---|\n")
        print(f"\n  ── 판정 ({sname}) ──")
        for h, r in res.items():
            a = r.get("IN"); b = r.get("이상치6제외"); c = r.get("OOS")
            v = verdict(a, b, c)
            fmt = lambda z: f"{z:.4f}" if z is not None else "—"
            L.append(f"| {h} | {fmt(a)} | {fmt(b)} | **{fmt(c)}** | **{v}** |\n")
            print(f"    {h:<12} IN={fmt(a)}  이상치={fmt(b)}  OOS={fmt(c)}  → {v}")
        print()

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    open(OUT, "w", encoding="utf-8").write("".join(L))
    print("=" * 84)
    print(f"저장: 가상매매\\검증\\30년_재검정_결과.md")
    print("=" * 84)
    return 0


def self_test():
    import pandas as pd, numpy as np
    ok = tot = 0

    def chk(n, c):
        nonlocal ok, tot
        tot += 1
        ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")

    chk("IN/OOS 겹치지 않음", IN_END < OOS_START)
    chk("하순 창 = 논문 정의(−9~−5)", LATE_RD == (-9, -8, -7, -6, -5))
    chk("TOM 창 = 논문 정의(−1,+1~+3)", TOM_RD == -1 and TOM_T == (1, 2, 3))
    chk("겨울 = 11~4월", WINTER == {11, 12, 1, 2, 3, 4})
    chk("게이트 C(OOS) = 0.05", GATE_C == 0.05)
    # 합성 데이터로 paired 동작 확인
    idx = pd.bdate_range("2020-01-01", "2021-12-31")
    r = pd.Series(np.random.RandomState(0).normal(0, 1, len(idx)), index=idx)
    x = pd.DataFrame({"ret": r})
    x["ym"] = x.index.year * 12 + x.index.month
    g = x.groupby("ym"); x["t"] = g.cumcount() + 1
    x["n"] = g["ret"].transform("size"); x["rd"] = x.t - x.n - 1
    out = paired(x, x.rd.isin(LATE_RD))
    chk("paired 동작(난수→유의 아님)", out is not None and out[3] > 0.05)
    chk("판정: OOS 실패 → 기각", verdict(0.01, 0.01, 0.5) == "기각 (OOS 실패)")
    chk("판정: 이상치 실패 → 기각", verdict(0.01, 0.5, 0.01) == "기각 (이상치 의존)")
    chk("판정: 전부 통과 → 후보", "채택" in verdict(0.01, 0.01, 0.01))
    print(f"\n셀프테스트: {ok}/{tot}")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--market", default="ALL", choices=["ALL", "KOSPI", "KOSDAQ"])
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(self_test())
    mk = ["KOSPI", "KOSDAQ"] if a.market == "ALL" else [a.market]
    sys.exit(run(mk))
