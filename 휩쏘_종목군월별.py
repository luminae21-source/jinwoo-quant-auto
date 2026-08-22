# -*- coding: utf-8 -*-
r"""휩쏘_종목군월별.py — §10-A 종목군별 월별 매매현황 (2026-08-16)

[사전 지정 — 실행 전에 못박은 설계. 사후 조정 금지]
  표본     : 휩쏘_밸류교집합_이벤트.csv 7,071건 (정식A + S2, 국면·밸류 도장 완료본)
  PRIMARY  : 🟢실행 × 등급∈{정식A, S2-α}  ← 실전 대상 셀. 가설 판정은 여기서만.
  종목군 3축 (겹침 허용 · 파티션 아님 · 판정불가는 제외하지 비교군에 섞지 않음):
    ① 테마(반도체 체인) : liquidity_sector + kosdaq_industry 스냅숏 → is_chain().
                          ⚠️ 현재 시점 스냅숏 = look-ahead + 생존편향. 섹터 정보 없는 종목은 '판정불가'.
    ② 밸류 태그군       : 파일의 밸류여부 (PIT). 태그가능==True 만 비교.
    ③ 성장주군          : 매출 3년 CAGR(직전 확정 회계연도 기준, 5월 이후=전년/이전=전전년)
                          상위 1/3. fundamentals_gp 2015~ → 이벤트 2019-05 이후만 판정.
                          ⚠️ 성장은 분류축(conditioning)이다. 결과가 좋아도 선정 규칙 승격 금지(기각 이력).
  사전가설 (판정은 이 3건만 · 부트스트랩 2000회 percentile CI · 클러스터 미보정 명시):
    H1(단측) 체인 > 비체인       — 근거: 기저율 검정 "섹터가 신호"
    H2(단측) 밸류 > 무밸류       — 기존 §4 방향 재확인
    H3(양측) 성장군 ≠ 비성장군   — 방향 사전예측 없음 (②↔③ 대조)
  월별 12×군 표는 기술통계로만 제시 — 칸별 판정 금지, n<30 회색. (36칸 체리피킹 금지 규율)
  자체검증: 핵심 수치를 독립 경로로 2회 계산해 일치 확인. 일관성감사 등록은 PC측 TODO.
"""
import os, sys, json, importlib.util, warnings, html as H
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
RNG = np.random.default_rng(20260816)
NBOOT = 2000

CHAIN = ["반도체", "특수 목적용 기계", "전자부품", "측정, 시험", "광학",
         "그외 기타 전문, 과학", "통신 및 방송 장비", "일반 목적용 기계", "전지"]
def is_chain(sec): return any(k in str(sec) for k in CHAIN)


def load_sectors():
    sec = {}
    for f in ("liquidity_sector.csv", "kosdaq_industry.csv"):
        p = os.path.join(HERE, f)
        if not os.path.exists(p): continue
        d = pd.read_csv(p, dtype=str); d.columns = [x.strip().lstrip("﻿") for x in d.columns]
        if {"code", "sector"}.issubset(d.columns):
            sec.update(dict(zip(d["code"].str.zfill(6), d["sector"].astype(str))))
    return sec


def growth_map():
    """(code, y1) -> g_rev 3y CAGR · 연도별 상위 1/3 컷."""
    F = pd.read_csv(os.path.join(HERE, "fundamentals_gp_2015_2025.csv"), dtype={"code": str})
    F.columns = [x.strip().lstrip("﻿") for x in F.columns]
    F["code"] = F["code"].str.zfill(6)
    F["revenue"] = pd.to_numeric(F["revenue"], errors="coerce")
    piv = F.pivot_table(index="code", columns="fiscal_year", values="revenue", aggfunc="last")
    g = {}
    cuts = {}
    for y1 in range(2018, 2026):
        y0 = y1 - 3
        if y0 not in piv.columns or y1 not in piv.columns: continue
        r0, r1 = piv[y0], piv[y1]
        valid = (r0 > 0) & (r1 > 0)
        gg = (r1[valid] / r0[valid]) ** (1 / 3) - 1
        cut = float(gg.quantile(2 / 3))
        cuts[y1] = cut
        for c, v in gg.items():
            g[(c, y1)] = float(v)
    return g, cuts


def growth_flag(code, date, g, cuts):
    y, m = int(date[:4]), int(date[5:7])
    y1 = y - 1 if m >= 5 else y - 2
    if y1 not in cuts: return None          # 판정불가
    v = g.get((code, y1))
    if v is None: return None
    return v >= cuts[y1]


def boot_ci(a, b, one_sided_pos=False):
    """Δ = mean(a) - mean(b) 부트스트랩 CI."""
    a = np.asarray(a, float); b = np.asarray(b, float)
    d = a.mean() - b.mean()
    ds = np.empty(NBOOT)
    for i in range(NBOOT):
        ds[i] = RNG.choice(a, len(a)).mean() - RNG.choice(b, len(b)).mean()
    lo, hi = np.percentile(ds, [2.5, 97.5])
    if one_sided_pos:
        lo5 = np.percentile(ds, 5)
        sig = lo5 > 0
        return d, lo, hi, sig, f"단측5% 하한 {lo5:+.2f}"
    sig = lo > 0 or hi < 0
    return d, lo, hi, sig, ""


def main():
    V = pd.read_csv(os.path.join(HERE, "휩쏘_밸류교집합_이벤트.csv"), dtype={"code": str})
    V["code"] = V["code"].str.zfill(6)
    V["카드%"] = pd.to_numeric(V["카드"], errors="coerce") * 100
    V["월"] = pd.to_datetime(V["date"]).dt.month
    sec = load_sectors()
    V["_sec"] = V["code"].map(sec)
    V["체인"] = V["_sec"].apply(lambda s: is_chain(s) if pd.notna(s) else None)
    g, cuts = growth_map()
    V["성장"] = [growth_flag(c, d, g, cuts) for c, d in zip(V["code"], V["date"])]

    P = V[(V["국면"] == "실행") & (V["등급"].isin(["정식A", "S2-α"]))].dropna(subset=["카드%"])
    print(f"표본 {len(V):,} · PRIMARY(실행×정식A/S2-α) {len(P):,}")
    print(f"  체인 판정가능 {P['체인'].notna().sum():,} · 밸류 판정가능 {int(P['태그가능'].sum()):,}"
          f" · 성장 판정가능 {P['성장'].notna().sum():,} (2019-05~)")

    res = {"PRIMARY_n": int(len(P))}
    # ── 사전가설 3건
    tests = []
    d1 = P[P["체인"].notna()]
    a, b = d1[d1["체인"] == True]["카드%"], d1[d1["체인"] == False]["카드%"]
    dd, lo, hi, sig, note = boot_ci(a, b, one_sided_pos=True)
    tests.append(dict(가설="H1 체인 > 비체인 (단측)", n=f"{len(a)} vs {len(b)}",
                      군평균=f"{a.mean():+.2f} vs {b.mean():+.2f}", Δ=dd, CI=[lo, hi], 유의=bool(sig), note=note))
    d2 = P[P["태그가능"] == True]
    a, b = d2[d2["밸류여부"] == True]["카드%"], d2[d2["밸류여부"] == False]["카드%"]
    dd, lo, hi, sig, note = boot_ci(a, b, one_sided_pos=True)
    tests.append(dict(가설="H2 밸류 > 무밸류 (단측)", n=f"{len(a)} vs {len(b)}",
                      군평균=f"{a.mean():+.2f} vs {b.mean():+.2f}", Δ=dd, CI=[lo, hi], 유의=bool(sig), note=note))
    d3 = P[P["성장"].notna()]
    a, b = d3[d3["성장"] == True]["카드%"], d3[d3["성장"] == False]["카드%"]
    dd, lo, hi, sig, note = boot_ci(a, b)
    tests.append(dict(가설="H3 성장군 ≠ 비성장군 (양측·분류축)", n=f"{len(a)} vs {len(b)}",
                      군평균=f"{a.mean():+.2f} vs {b.mean():+.2f}", Δ=dd, CI=[lo, hi], 유의=bool(sig), note=note))
    res["가설"] = tests

    print("\n[사전가설 판정 — PRIMARY 셀 · 부트 2000회]")
    for t in tests:
        v = "✅ 유의" if t["유의"] else "⛔ 유의 아님"
        print(f"  {t['가설']:<28} n={t['n']:<12} 평균 {t['군평균']} · Δ{t['Δ']:+.2f}%p"
              f" CI[{t['CI'][0]:+.2f},{t['CI'][1]:+.2f}] {t['note']} → {v}")

    # ── 월별 매매현황 (기술통계)
    axes = {"전체": P, "① 체인": P[P["체인"] == True], "①' 비체인": P[P["체인"] == False],
            "② 밸류": d2[d2["밸류여부"] == True], "②' 무밸류": d2[d2["밸류여부"] == False],
            "③ 성장": d3[d3["성장"] == True], "③' 비성장": d3[d3["성장"] == False]}
    mon_tab = {}
    print("\n[월별 매매현황 — 기술통계 · 칸별 판정 금지 · n<30 참고만]")
    hdr = "  {:<9}".format("군") + "".join(f"{m:>10}월" for m in range(1, 13))
    print(hdr)
    for lab, dd_ in axes.items():
        row = {}
        line = f"  {lab:<9}"
        for m in range(1, 13):
            s = dd_[dd_["월"] == m]["카드%"]
            row[m] = dict(n=int(len(s)), 평균=float(s.mean()) if len(s) else None,
                          승률=float((s > 0).mean()) if len(s) else None)
            line += (f"{s.mean():+9.1f}%" if len(s) >= 1 else " " * 10)
        mon_tab[lab] = row
        print(line)
    res["월별"] = mon_tab

    # ── 자체검증 (독립 경로 이중계산)
    chk1 = float(P["카드%"].mean())
    chk2 = float(pd.to_numeric(V.loc[P.index, "카드"], errors="coerce").mean() * 100)
    assert abs(chk1 - chk2) < 1e-9, "자체검증 실패: PRIMARY 평균 불일치"
    g_direct = V[(V["국면"] == "실행") & V["등급"].isin(["정식A", "S2-α"])]["카드"].astype(float).mean() * 100
    assert abs(chk1 - g_direct) < 1e-9, "자체검증 실패: 필터 경로 불일치"
    print(f"\n  자체검증 ✅ PRIMARY 카드평균 {chk1:+.3f}% (이중계산 일치)")

    E = P.copy()
    E["체인"] = E["체인"].map({True: "체인", False: "비체인", None: ""})
    E["성장군"] = E["성장"].map({True: "성장", False: "비성장", None: ""})
    E[["date", "code", "name", "등급", "국면", "월", "체인", "밸류여부", "성장군", "카드%", "ex_how"]].to_csv(
        os.path.join(HERE, "휩쏘_종목군월별_이벤트.csv"), index=False, encoding="utf-8-sig")
    with open(os.path.join(HERE, "종목군월별_요약.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2, default=float)
    print("저장: 휩쏘_종목군월별_이벤트.csv · 종목군월별_요약.json")


if __name__ == "__main__":
    main()
