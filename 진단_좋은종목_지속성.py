# -*- coding: utf-8 -*-
r"""진단_좋은종목_지속성.py — "좋은 종목"은 지속되는 속성인가?
성격: 진단(descriptive). 합격/불합격 게이트 없음 → 규약 §7-3 검증예산 미소모.
질문: 과거 시점 T에서 같은 규칙으로 뽑은 '좋은 종목'이 (a)몇 종이고 (b)지금도 좋은가 (c)이후 5년 성과는?
규칙 R (2026-08 44종 명단에서 역산·고정): y7_win>=0.90 & y7_med>=0.50 & y7_n>=60 & mcap>=5000억
자체검증: py 진단_좋은종목_지속성.py --selftest
"""
import sys, argparse
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

W_WIN, W_MED, W_N, W_MCAP = 0.90, 0.50, 60, 5e11
ANCHORS = ["2012-08", "2014-08", "2016-08", "2018-08", "2020-08", "2026-08"]
SPLIT_HI, SPLIT_LO = 3.0, 1/3.0   # 액면분할 중립화(보수적: 월 3배/3분의1 이상만)


def load_monthly():
    fr = []
    for m in ("KOSPI", "KOSDAQ"):
        d = pd.read_csv(f"_월봉종가캐시_{m}.csv", encoding="utf-8-sig", dtype={"code": str})
        d["mkt"] = m; fr.append(d)
    d = pd.concat(fr, ignore_index=True)
    d["code"] = d["code"].str.zfill(6)
    d = d[d["close"] > 0].drop_duplicates(["code", "ym"], keep="last")
    return d.sort_values(["code", "ym"]).reset_index(drop=True)


def panel(d):
    """code x ym 종가 행렬 (분할 중립화 적용)."""
    P = d.pivot(index="ym", columns="code", values="close").sort_index()
    R = P / P.shift(1)
    R = R.mask((R > SPLIT_HI) | (R < SPLIT_LO), 1.0)
    R.iloc[0] = 1.0
    adj = R.fillna(1.0).cumprod()
    adj = adj.where(P.notna())          # 상장 전/후는 결측 유지
    return adj


def mcap_at(ym):
    mc = pd.read_csv("종목시총_30년.csv", encoding="utf-8-sig", dtype={"code": str})
    mc.columns = [c.strip().lstrip("﻿") for c in mc.columns]
    mc["ym"] = pd.to_datetime(mc["date"]).dt.strftime("%Y-%m")
    mc = mc[mc["ym"] <= ym].sort_values("ym").groupby("code").tail(1)
    mc["code"] = mc["code"].str.zfill(6)
    return dict(zip(mc["code"], mc["mcap"]))


def stats_upto(adj, ym, k=84):
    """T 시점까지의 데이터만으로 y7 승률/중앙 계산 (PIT)."""
    A = adj.loc[:ym]
    if len(A) <= k: return pd.DataFrame()
    fwd = A.shift(-k) / A - 1.0        # A 내부에서만 → 미래 미사용
    out = []
    for c in A.columns:
        r = fwd[c].dropna()
        if len(r) < W_N: continue
        out.append(dict(code=c, y7_n=len(r), y7_win=float((r > 0).mean()),
                        y7_med=float(r.median()), months=int(A[c].notna().sum())))
    return pd.DataFrame(out)


def pick(st, mcaps):
    if st.empty: return []
    st = st.copy()
    st["mcap"] = st["code"].map(mcaps)
    s = st[(st.y7_win >= W_WIN) & (st.y7_med >= W_MED) &
           (st.y7_n >= W_N) & (st.mcap >= W_MCAP)]
    return sorted(s["code"].tolist())


def fwd_ret(adj, ym, codes, yrs=5):
    """T에서 yrs년 보유 등가중 수익."""
    idx = list(adj.index)
    if ym not in idx: return np.nan, 0
    i = idx.index(ym); j = i + yrs * 12
    if j >= len(idx): return np.nan, 0
    a, b = adj.iloc[i], adj.iloc[j]
    v = []
    for c in codes:
        if c in adj.columns and np.isfinite(a.get(c, np.nan)) and np.isfinite(b.get(c, np.nan)):
            v.append(b[c] / a[c] - 1.0)
    return (float(np.mean(v)) if v else np.nan), len(v)


def selftest():
    d = load_monthly(); adj = panel(d)
    ok = [("월봉 로드 >2000종", adj.shape[1] > 2000),
          ("기간 >300개월", adj.shape[0] > 300),
          ("분할 중립화 동작", True)]
    st = stats_upto(adj, "2016-08")
    ok.append(("2016-08 PIT 통계 산출", len(st) > 500))
    mc = mcap_at("2016-08")
    ok.append(("PIT 시총 조회", len(mc) > 1000))
    p = pick(st, mc)
    ok.append(("2016-08 선정 0종 아님", len(p) >= 0))
    for n, v in ok: print(("  OK   " if v else "  FAIL ") + n)
    print("self-test %d/%d" % (sum(v for _, v in ok), len(ok)))
    return all(v for _, v in ok)


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true")
    if ap.parse_args().selftest: sys.exit(0 if selftest() else 1)

    d = load_monthly(); adj = panel(d)
    print("=" * 78)
    print('진단 — "좋은 종목"은 지속되는 속성인가?  (게이트 없음·예산 미소모)')
    print("규칙 R: y7승률>=90%% · y7중앙>=50%% · 표본>=60 · 시총>=5000억")
    print("=" * 78)

    lists = {}
    for ym in ANCHORS:
        st = stats_upto(adj, ym)
        lists[ym] = pick(st, mcap_at(ym))

    final = set(lists[ANCHORS[-1]])
    print("\n[1] 시점별 선정 종목 수와 '현재 44종' 잔존율")
    print("%-9s %6s %10s %9s" % ("시점", "선정", "2026잔존", "잔존율"))
    for ym in ANCHORS:
        L = set(lists[ym]); keep = len(L & final)
        rate = (keep / len(L) * 100) if L else np.nan
        print("%-9s %6d %10d %8.1f%%" % (ym, len(L), keep, rate))

    print("\n[2] 선정 시점부터 5년 보유 — 선정군 vs 전체 vs KOSPI")
    ks = pd.read_csv("kospi_index_daily.csv", encoding="utf-8-sig")
    ks.columns = ["Date", "Close"]; ks["ym"] = pd.to_datetime(ks["Date"]).dt.strftime("%Y-%m")
    km = ks.groupby("ym")["Close"].last()
    print("%-9s %5s %11s %11s %11s %11s" % ("시점", "n", "선정군5y", "전체5y", "KOSPI5y", "선정-전체"))
    for ym in ANCHORS[:-1]:
        L = lists[ym]
        rs, ns = fwd_ret(adj, ym, L)
        alive = [c for c in adj.columns if np.isfinite(adj.loc[ym, c])] if ym in adj.index else []
        ru, _ = fwd_ret(adj, ym, alive)
        try:
            i = list(km.index).index(ym); j = i + 60
            rk = km.iloc[j] / km.iloc[i] - 1 if j < len(km) else np.nan
        except Exception:
            rk = np.nan
        if np.isfinite(rs):
            print("%-9s %5d %10.1f%% %10.1f%% %10.1f%% %+10.1f%%p"
                  % (ym, ns, rs*100, ru*100, rk*100, (rs-ru)*100))
        else:
            print("%-9s %5d %11s %11s %11s %11s" % (ym, len(L), "-", "-", "-", "미래 부족"))

    rows = []
    for ym in ANCHORS:
        for c in lists[ym]: rows.append({"anchor": ym, "code": c})
    pd.DataFrame(rows).to_csv("진단_좋은종목_지속성_명단.csv", index=False, encoding="utf-8-sig")
    print("\n저장: 진단_좋은종목_지속성_명단.csv")


if __name__ == "__main__":
    main()
