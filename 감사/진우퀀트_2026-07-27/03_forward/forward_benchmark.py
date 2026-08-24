#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
forward_benchmark.py — forward 트랙 벤치마크 산출 (동결사양서 v1.1)

배경: v1은 top30 **동일가중** 포트를 KOSPI **시총가중** 지수와 비교하도록 설계됐다.
      이는 종목 선택 실력과 가중방식 효과를 분리할 수 없는 비교다.
      (2026-07-27 백서 3장이 무효화된 것과 같은 결함)

v1.1 벤치마크:
  B1  KOSPI 대형 top300 **동일가중**   ← 주 판정. 가중방식 통제
  B2  시총 top30 **동일가중**          ← 주 판정. 기계적 베이스라인
  B3  KOSPI 시총가중 지수              ← 참고용. 판정에서 제외

사용 (진우퀀트 폴더에서):
  python forward_benchmark.py
  python forward_benchmark.py --ledger 실전준비\forward_ledger.csv --out 실전준비\forward_returns.csv
"""
try:  # 윈도 파이프(cp949)에서 이모지 출력 시 UnicodeEncodeError 방지 (2026-07-27)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse, glob, os, sys
from datetime import datetime
import numpy as np
import pandas as pd

ROUND_TRIP = 0.0048     # 왕복 0.48% (동결사양서 v1.1)
N_B1, N_B2 = 300, 30


def find(pattern):
    hits = glob.glob(pattern, recursive=True)
    return hits[0] if hits else None


def load_prices():
    """KOSPI 월봉. 가격 캐시의 종목 집합 = 벤치마크 유니버스 (사양서: KOSPI 대형)"""
    frames = []
    for pat in ("**/_월봉종가캐시_KOSPI.csv", "**/_월봉종가캐시_KOSPI_adj.csv"):
        p = find(pat)
        if p:
            d = pd.read_csv(p, dtype={"code": str})
            d["code"] = d.code.str.zfill(6)
            frames.append((os.path.basename(p), d))
    if not frames:
        sys.exit("월봉 캐시를 못 찾음")
    name, d = frames[-1]        # 조정본이 있으면 우선
    print(f"  가격: {name} ({d.code.nunique():,}종목)")
    return d.pivot_table(index="ym", columns="code", values="close", aggfunc="last").sort_index()


def load_mcap():
    p = find("**/종목시총_30년.csv")
    if not p:
        sys.exit("시총 파일을 못 찾음")
    d = pd.read_csv(p, dtype={"code": str})
    d["code"] = d.code.str.zfill(6)
    d["ym"] = pd.to_datetime(d.date).dt.strftime("%Y-%m")
    return d.pivot_table(index="ym", columns="code", values="mcap", aggfunc="last")


def next_month(ym):
    y, m = int(ym[:4]), int(ym[5:])
    return f"{y + (m == 12)}-{1 if m == 12 else m + 1:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default=os.path.join("실전준비", "forward_ledger.csv"))
    ap.add_argument("--out", default=os.path.join("실전준비", "forward_returns.csv"))
    a = ap.parse_args()

    if not os.path.exists(a.ledger):
        sys.exit(f"원장 없음: {a.ledger}")

    print("=" * 74)
    print(" forward 벤치마크 산출 · 동결사양서 v1.1")
    print("=" * 74)

    P = load_prices()
    M = load_mcap()
    KOSPI_CODES = set(P.columns)          # 벤치마크 유니버스를 KOSPI로 한정
    led = pd.read_csv(a.ledger, dtype=str)
    # v1.2 병행관찰(N=10): 시총 top100엔 대형 KOSDAQ이 들어올 수 있어 전시장 가격을 별도 로드.
    # 동결 라인(port_net)의 측정은 종전 그대로 P(KOSPI 한정)를 쓴다 — 값 불변.
    PALL = None
    if "n10_holdings" in led.columns and led["n10_holdings"].fillna("").str.strip().any():
        _fr = []
        for _mkt in ("KOSPI", "KOSDAQ"):
            _p = find(f"**/_월봉종가캐시_{_mkt}_adj.csv") or find(f"**/_월봉종가캐시_{_mkt}.csv")
            if _p:
                _d = pd.read_csv(_p, dtype={"code": str})
                _d["code"] = _d.code.str.zfill(6)
                _fr.append(_d)
        if _fr:
            PALL = (pd.concat(_fr).pivot_table(index="ym", columns="code",
                    values="close", aggfunc="last").sort_index())
            print(f"  병행 N=10 가격: 전시장 {PALL.shape[1]:,}종목 (KOSDAQ 포함)")
    print(f"  원장: {len(led)}행 · 시총: {M.index.min()}~{M.index.max()}")
    print(f"  벤치 유니버스: KOSPI {len(KOSPI_CODES):,}종목 (시총파일의 KOSDAQ 제외)")

    last_ym = P.index.max()
    today = datetime.now()
    partial = (last_ym == f"{today:%Y-%m}")   # 이번 달은 아직 진행 중
    if partial:
        print(f"  ⚠️ {last_ym}은 미완료 월 — 부분 수익률(월중 시점)")

    rows, prev_hold, prev10 = [], set(), set()
    for _, r in led.iterrows():
        t = r["date_asof"]
        t1 = next_month(t)
        if t1 not in P.index or t not in P.index:
            print(f"  {t}: {t1} 가격 없음 → 건너뜀")
            continue

        ret = (P.loc[t1] / P.loc[t] - 1)
        ret = ret.mask(ret.abs() > 1.0)

        # ── 포트 (원장 보유, 동일가중)
        hold = [c.zfill(6) for c in str(r["holdings"]).split(";") if c.strip()]
        h = [c for c in hold if c in ret.index and pd.notna(ret[c])]
        cash = float(r.get("defense_cash", 0) or 0)
        gross = ret[h].mean() * (1 - cash) if h else 0.0
        turn = 1.0 if not prev_hold else 1 - len(set(h) & prev_hold) / max(len(h), 1)
        port = gross - turn * ROUND_TRIP
        prev_hold = set(h)

        # ── B1 / B2 (KOSPI 한정, 동일가중, 전월말 시총으로 선정)
        b1 = b2 = np.nan
        n1 = n2 = 0
        if t in M.index:
            m = M.loc[t].dropna()
            m = m[[c for c in m.index if c in KOSPI_CODES]].sort_values(ascending=False)
            s1 = [c for c in m.index[:N_B1] if c in ret.index and pd.notna(ret[c])]
            s2 = [c for c in m.index[:N_B2] if c in ret.index and pd.notna(ret[c])]
            n1, n2 = len(s1), len(s2)
            if n1: b1 = ret[s1].mean()
            if n2: b2 = ret[s2].mean()

        # ── B3 참고 (시총가중 전종목)
        b3 = np.nan
        if t in M.index:
            m = M.loc[t].dropna()
            m = m[[c for c in m.index if c in ret.index and pd.notna(ret[c])]]
            if len(m) > 50:
                w = m / m.sum()
                b3 = float((ret[m.index] * w).sum())



        # ── v1.2 병행관찰: N=10 라인 (기록만 · 판정 별도)
        n10_net, n10n, n10turn, exc10 = "", 0, "", ""
        _raw10 = str(r.get("n10_holdings", "") or "").strip()
        if _raw10 and _raw10.lower() != "nan" and PALL is not None and t in PALL.index and t1 in PALL.index:
            _retA = (PALL.loc[t1] / PALL.loc[t] - 1)
            _retA = _retA.mask(_retA.abs() > 1.0)
            _h10 = [c.zfill(6) for c in _raw10.split(";") if c.strip()]
            _h10 = [c for c in _h10 if c in _retA.index and pd.notna(_retA[c])]
            if _h10:
                _g10 = _retA[_h10].mean() * (1 - cash)
                _t10 = 1.0 if not prev10 else 1 - len(set(_h10) & prev10) / max(len(_h10), 1)
                n10_net = round(_g10 - _t10 * ROUND_TRIP, 6)
                n10n, n10turn = len(_h10), round(_t10, 3)
                exc10 = round(n10_net - b1, 6) if pd.notna(b1) else ""
                prev10 = set(_h10)

        rows.append(dict(
            as_of=t, ret_month=t1, partial="Y" if (partial and t1 == last_ym) else "N",
            port_net=round(port, 6), n_hold=len(h), turnover=round(turn, 3),
            b1_top300_ew=round(b1, 6) if pd.notna(b1) else "", n_b1=n1,
            b2_mcap30_ew=round(b2, 6) if pd.notna(b2) else "", n_b2=n2,
            b3_kospi_cw=round(b3, 6) if pd.notna(b3) else "",
            excess_b1=round(port - b1, 6) if pd.notna(b1) else "",
            excess_b2=round(port - b2, 6) if pd.notna(b2) else "",
            n10_net=n10_net, n10_n_hold=n10n, n10_turnover=n10turn,
            n10_excess_b1=exc10,
            spec="v1.1", computed=f"{today:%Y-%m-%d}"))

    if not rows:
        sys.exit("산출된 행이 없음")

    df = pd.DataFrame(rows)
    df.to_csv(a.out, index=False, encoding="utf-8-sig")

    print("\n" + "-" * 74)
    print(f"  {'as-of':<9}{'수익월':<9}{'포트':>9}{'B1':>9}{'B2':>9}{'−B1':>9}{'−B2':>9}{'N10':>9}  ")
    print("-" * 74)
    for _, r in df.iterrows():
        f = lambda v: f"{float(v)*100:+8.2f}%" if v != "" else "       —"
        mark = " ⚠부분" if r["partial"] == "Y" else ""
        n10s = f(r.get('n10_net', '')) if str(r.get('n10_net', '')) != '' else '       —'
        print(f"  {r['as_of']:<9}{r['ret_month']:<9}{float(r['port_net'])*100:+8.2f}%"
              f"{f(r['b1_top300_ew'])}{f(r['b2_mcap30_ew'])}"
              f"{f(r['excess_b1'])}{f(r['excess_b2'])}{n10s}{mark}")

    n = len(df)
    print("-" * 74)
    print(f"\n  저장: {a.out}")
    print(f"\n  [게이트 판정] 누적 {n}개월 / 최소 6개월")
    if n < 6:
        print(f"  ⏸ 판정 불가 — {6-n}개월 더 필요.")
        print("     ⚠️ 1~2개월 수익률은 순수 노이즈다. 초과수익이 커도 작아도 의미 없다.")
        print("     재량트랙 시뮬(PART A)과 같은 물리학 — 실력 연 6%도 12개월 통과율 14%.")
    else:
        print("  ▶ 사양서 v1.1 §3 게이트(F1>B1 · F2>B2 · F3 MDD · F4 무결성)로 판정.")
    print("\n  ⚠️ 정보·검증용 · 투자자문 아님 · 백테는 실현손익 아님")


if __name__ == "__main__":
    main()
