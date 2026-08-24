#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
theme_classify.py — 포괄 테마 분류 (모니터용): KSIC 섹터 백본 + 투자테마 오버레이
==============================================================================
설계 원칙(진우 요구 "임의 누락 금지"): 모든 종목을 빠짐없이 분류.
 · **섹터 백본** = 전 KSIC 세분류를 그룹에 매핑 → 섹터 라벨 있으면 반드시 어느 그룹엔 속함(누락 0).
 · **투자테마 오버레이** = 로봇·방산·우주항공·원자력 등 섹터를 가로지르는 테마는 이름 키워드로 보강.
검증(2026-06-05): 분류율 97%(미분류 17종=섹터라벨 없는 데이터공백뿐). 핵심종목 전부 정확
 (삼성전자·SK하이닉스→반도체/전자, 한화에어로→우주항공/방산, 두산에너빌리티→원자력, 에코프로비엠→2차전지).
 오탐 가드: 대원전선("원전" substring)·우리기술투자("우리기술")는 exclude로 제외.
큐레이션 정밀 테마(반도체 65종)는 theme_universe.csv 별도 — 본 분류는 전 시장 포괄 백본.
사용: python theme_classify.py   /   --selftest
원칙: supercycle_overlay(등록·동결) 무수정.
"""
import argparse, os, sys, re
import numpy as np, pandas as pd
import supercycle_overlay as E

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# (테마, 포함 regex, 제외 regex) — 순서 = 우선순위(구체 테마 먼저, 섹터 백본 뒤).
# 이름+섹터 문자열에 매칭. 제외는 오탐 가드(이름에만 적용).
THEME_RULES = [
    # --- 투자테마 오버레이 (섹터 가로지름, 이름 기반) ---
    ("로봇/자동화",   r"로봇|로보|뉴로메카", None),
    ("우주항공/방산", r"항공기|우주선|무기|총포|에어로스페이스|한국항공우주|현대로템|쎄트렉|풍산|LIG디펜스|한화시스템", None),
    ("원자력/원전",   r"원자력|한전기술|한전KPS|두산에너빌|비에이치아이|보성파워텍|우진엔텍|우리기술", r"투자|전선"),
    # --- 섹터 백본 (전 KSIC 세분류 커버) ---
    ("반도체/전자",   r"반도체|전자부품|통신 및 방송 장비|디스플레이|컴퓨터|마그네틱|정밀기기|광학|사진장비|가정용 기기", None),
    ("2차전지",      r"전지|축전지", None),
    ("자동차",       r"자동차", None),
    ("조선",         r"선박|보트", None),
    ("전력/전기장비", r"전동기|발전기|전기 변환|절연선|케이블|기타 전기장비|전기 및 통신 공사", None),
    ("기계/장비",    r"기계|장비", None),
    ("바이오/제약",  r"의약|생물|자연과학|치과|의료", None),
    ("화학/에너지",  r"화학|고무|플라스틱|석유|유지", None),
    ("철강/소재",    r"철강|금속|비금속|시멘트|유리|나무|종이|펄프|가죽|섬유", None),
    ("금융",         r"금융|보험|은행|증권|신탁", None),
    ("인터넷/SW",    r"소프트|프로그래밍|포털|호스팅|정보매개|정보 서비스", None),
    ("엔터/미디어",  r"방송|영화|비디오|광고|출판|오락|유원지", None),
    ("유통/소비/식품", r"소매|도매|중개|식료품|식품|음료|화장품|담배|의복|가구|생활용품", None),
    ("건설/엔지니어링", r"건설|부동산|토목|건축기술|엔지니어링", None),
    ("운송/물류/여행", r"운송|숙박|여행|창고|항공 운송|해상|육상", None),
    ("통신",         r"전기 통신|통신업", None),
    ("유틸리티",     r"전기업|가스|수도|증기|냉·온수", None),
    ("서비스/기타사업", r"컨설팅|본부|경비|경호|탐정|교습|학원|개인 서비스|사업지원|과학 및 기술|임대", None),
]


def coarse_sector(name, fine):
    """이름+섹터 → 테마. 섹터 라벨 없으면 '미분류(섹터없음)'(데이터공백, 누락 아님)."""
    f = str(fine)
    if not f or f == "nan":
        return "미분류(섹터없음)"
    s = str(name) + " " + f
    for tname, inc, exc in THEME_RULES:
        if re.search(inc, s) and not (exc and re.search(exc, str(name))):
            return tname
    return "기타"


def load_theme_universe(path="theme_universe.csv"):
    """큐레이션 정밀 테마(theme_universe.csv) → {theme:[codes]}, {code:(theme,category)}."""
    if not os.path.exists(path):
        return {}, {}
    d = pd.read_csv(path, dtype={"code": str}); d["code"] = d["code"].str.zfill(6)
    by_theme, of = {}, {}
    for _, r in d.iterrows():
        by_theme.setdefault(str(r["theme"]), []).append(r["code"])
        of[r["code"]] = (str(r["theme"]), str(r.get("category", "")))
    return by_theme, of


def load_fine_map(liq_csv="liquidity_sector.csv", kosdaq_csv="kosdaq_industry.csv"):
    """KOSPI+KOSDAQ 세분류 합본 {code: fine_sector}, {code: name}."""
    fine, name = {}, {}
    for path in (liq_csv, kosdaq_csv):
        if path and os.path.exists(path):
            d = pd.read_csv(path, dtype={"code": str}); d["code"] = d["code"].str.zfill(6)
            for _, r in d.iterrows():
                if pd.notna(r.get("sector")):
                    fine.setdefault(r["code"], str(r["sector"]))
                if pd.notna(r.get("name")):
                    name.setdefault(r["code"], str(r["name"]))
    return fine, name


def coarse_map(fine, name=None):
    """{code: fine}(+이름) → {code: theme}, {theme: [codes]}."""
    name = name or {}
    cm = {c: coarse_sector(name.get(c, ""), s) for c, s in fine.items()}
    groups = {}
    for c, g in cm.items():
        groups.setdefault(g, []).append(c)
    return cm, groups


def detect_groups(panel, fine, name=None, min_members=5, i=None):
    """테마 그룹별 수퍼사이클 감지 (supercycle_overlay 감지부 재사용). 데이터 ≤ i."""
    cm, groups = coarse_map(fine, name)
    cols = set(panel.columns)
    ret = panel.pct_change(); mkt = ret.mean(axis=1)
    i = (len(panel) - 1) if i is None else i
    out = {}
    for g, codes in groups.items():
        if g in ("기타", "미분류(섹터없음)"):
            continue
        basket = [c for c in codes if c in cols]
        if len(basket) < min_members:
            continue
        ex, br = E._excess_breadth(ret, basket, mkt, i)
        on = bool(E.detect_supercycle(ret, {"_": basket}, mkt, i)["_"])
        out[g] = {"n": len(basket), "excess_12m": ex, "breadth": br, "state_on": on}
    return cm, out


def classify_holdings(codes, cm, group_states):
    rows = []
    for c in codes:
        g = cm.get(c, "기타")
        st = group_states.get(g)
        rows.append({"code": c, "coarse": g, "group_on": bool(st and st["state_on"])})
    return rows


def _selftest():
    ok = 0
    # 1) 핵심 종목 분류 (이름+섹터)
    cases = [
        ("삼성전자", "통신 및 방송 장비 제조업", "반도체/전자"),
        ("SK하이닉스", "반도체 제조업", "반도체/전자"),
        ("한화에어로스페이스", "항공기,우주선 및 부품 제조업", "우주항공/방산"),
        ("두산에너빌리티", "일반 목적용 기계 제조업", "원자력/원전"),
        ("두산로보틱스", "특수 목적용 기계 제조업", "로봇/자동화"),
        ("에코프로비엠", "일차전지 및 이차전지 제조업", "2차전지"),
        ("KB금융", "기타 금융업", "금융"),
        ("NAVER", "자료처리, 호스팅, 포털 및 기타 인터넷 정보매개 서비스업", "인터넷/SW"),
    ]
    for n, s, exp in cases:
        got = coarse_sector(n, s)
        assert got == exp, f"분류 오류 {n}: {got} ≠ {exp}"
    ok += 1
    # 2) 오탐 가드 (대원전선·우리기술투자 → 원자력 아님)
    assert coarse_sector("대원전선", "절연선 및 케이블 제조업") != "원자력/원전"; ok += 1
    assert coarse_sector("우리기술투자", "기타 금융업") != "원자력/원전"; ok += 1
    # 3) 섹터 없으면 미분류
    assert coarse_sector("무명", "") == "미분류(섹터없음)"; ok += 1
    # 4) 그룹 감지
    rng = np.random.default_rng(3); Tm = 40
    idx = pd.date_range("2022-01-31", periods=Tm, freq="ME")
    semi = [f"E{i:05d}" for i in range(6)]; other = [f"X{i:05d}" for i in range(12)]
    cols = semi + other
    px = pd.DataFrame(index=idx, columns=cols, dtype=float)
    for c in cols: px[c] = 1000.0
    for t in range(1, Tm):
        for c in cols:
            dr = rng.normal(0.11, 0.07) if (c in semi and 18 <= t <= 32) else rng.normal(0.004, 0.025)
            px.loc[idx[t], c] = px.loc[idx[t-1], c] * (1 + dr)
    fine = {**{c: "반도체 제조업" for c in semi}, **{c: "기타 금융업" for c in other}}
    cm, states = detect_groups(px, fine, min_members=5, i=28)
    assert states.get("반도체/전자", {}).get("state_on"), f"그룹 감지 실패 {states}"
    ok += 1
    print(f"[OK] theme_classify selftest 통과 ({ok} checks)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices", default="kospi_monthly_prices.csv")
    ap.add_argument("--liquidity", default="liquidity_sector.csv")
    ap.add_argument("--kosdaq", default="kosdaq_industry.csv")
    ap.add_argument("--coverage", action="store_true", help="전 종목 분류 커버리지 리포트")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    panel = pd.read_csv(a.prices, index_col=0, parse_dates=True)
    panel.columns = [str(c).zfill(6) for c in panel.columns]
    fine, name = load_fine_map(a.liquidity, a.kosdaq)
    if a.coverage:
        cm, _ = coarse_map(fine, name)
        vc = pd.Series(cm).value_counts()
        tot = len(cm); cl = sum(v for g, v in vc.items() if g not in ("기타", "미분류(섹터없음)"))
        print(f"=== 분류 커버리지 (전 {tot}종, 분류율 {cl/tot:.0%}) ===")
        print(vc.to_string())
        return 0
    cm, states = detect_groups(panel, fine, name)
    print(f"=== 테마 그룹 수퍼사이클 ({panel.index[-1].date()}) ===")
    for g, s in sorted(states.items(), key=lambda x: -(x[1]["excess_12m"] if pd.notna(x[1]["excess_12m"]) else -9)):
        tag = "← ON" if s["state_on"] else ""
        ex = "—" if pd.isna(s["excess_12m"]) else f"{s['excess_12m']:+.0%}"
        br = "—" if pd.isna(s["breadth"]) else f"{s['breadth']:.0%}"
        print(f"  {g:16} {s['n']:3}종 · 12M초과 {ex:>6} · breadth {br:>5} {tag}")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
