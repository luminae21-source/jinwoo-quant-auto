#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
check_mcap_pit.py — 시총 데이터가 PIT(Point-In-Time)인가 소급인가

배경:
  TOP30_고정 EW = 19.8% vs KOSPI 6.9% → 연 12.9%p 갭.
  설명 가능 요인(배당 2%p + 동일가중 프리미엄 3%p) 합계로 절반도 안 된다.
  유력 원인: 시총이 현재 기준으로 소급 적용되어 "1999년 top30"이
  실제로는 "2026년 기준 큰 회사들의 1999년"이 되는 look-ahead.

사용 (진우퀀트 폴더에서):
  python check_mcap_pit.py
  python check_mcap_pit.py --file "강화키트\종목시총_30년.csv"
"""
try:  # 윈도 파이프(cp949)에서 이모지 출력 시 UnicodeEncodeError 방지 (2026-07-27)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse, os, sys
from pathlib import Path
import pandas as pd

# 2010년 이후 상장/설립된 종목 — 1990~2000년대 데이터에 있으면 안 됨
MODERN = {
    "035720": "카카오(2017 이전 다음)", "323410": "카카오뱅크(2021상장)",
    "377300": "카카오페이(2021)", "259960": "크래프톤(2021)",
    "373220": "LG에너지솔루션(2022)", "247540": "에코프로비엠(2019)",
    "086520": "에코프로(2007)", "302440": "SK바이오사이언스(2021)",
    "326030": "SK바이오팜(2020)", "207940": "삼성바이오로직스(2016)",
    "091990": "셀트리온헬스케어(2017)", "196170": "알테오젠(2014)",
    "042660": "한화오션(구 대우조선, 2023개명)", "329180": "HD현대중공업(2021)",
    "267250": "HD현대(2017)", "042700": "한미반도체", "003230": "삼양식품",
}
# 1999년 실제 시총 상위권에 있었어야 할 종목
OLD_LARGE = {
    "005930": "삼성전자", "015760": "한국전력", "017670": "SK텔레콤",
    "005490": "POSCO(포항제철)", "005380": "현대차", "000660": "SK하이닉스(현대전자)",
    "055550": "신한지주", "003550": "LG", "051910": "LG화학",
}


def find_file(explicit=None):
    if explicit and os.path.exists(explicit):
        return Path(explicit)
    for root in (Path.cwd(), Path.cwd().parent):
        for p in root.rglob("*종목시총*.csv"):
            return p
        for p in root.rglob("*시총*.csv"):
            return p
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--file", default=None)
    ap.add_argument("--out", default="감사_시총PIT.md")
    a = ap.parse_args()

    L = []
    def say(s=""):
        print(s); L.append(s)

    p = find_file(a.file)
    if p is None:
        sys.exit("시총 파일을 못 찾음. --file 로 경로 지정.\n"
                 "예: python check_mcap_pit.py --file \"강화키트\\종목시총_30년.csv\"")
    say(f"# 시총 PIT 감사\n\n파일: `{p}` ({p.stat().st_size/1e6:.1f} MB)\n")

    # ── 로드 (인코딩 자동)
    df = None
    for enc in ("utf-8", "cp949", "utf-8-sig", "euc-kr"):
        try:
            df = pd.read_csv(p, dtype=str, encoding=enc)
            say(f"인코딩: {enc}")
            break
        except UnicodeDecodeError:
            continue
    if df is None:
        sys.exit("읽기 실패 — 인코딩 확인 필요")

    say(f"\n## 1. 스키마\n")
    say(f"행 {len(df):,} · 컬럼 {list(df.columns)}")
    say("\n첫 3행:")
    say("```")
    say(df.head(3).to_string())
    say("```")

    # ── 컬럼 추정
    def guess(hints):
        for h in hints:
            for c in df.columns:
                if h in str(c).lower():
                    return c
        return None
    dcol = guess(["date", "일자", "ym", "날짜", "기준"])
    ccol = guess(["code", "종목", "ticker", "단축"])
    mcol = guess(["mcap", "시총", "market", "cap"])
    say(f"\n추정: 날짜={dcol} · 종목={ccol} · 시총={mcol}")
    if not all((dcol, ccol, mcol)):
        sys.exit("컬럼 추정 실패 — 위 스키마를 보고 코드 수정 필요")

    df[ccol] = df[ccol].astype(str).str.zfill(6)
    df[mcol] = pd.to_numeric(df[mcol], errors="coerce")
    dt = pd.to_datetime(df[dcol], errors="coerce", format="mixed")
    df["_ym"] = dt.dt.strftime("%Y-%m")

    yms = sorted(df["_ym"].dropna().unique())
    say(f"\n## 2. 기간 커버리지\n")
    say(f"시점 {len(yms)}개 · {yms[0]} ~ {yms[-1]}")
    say(f"연도별 종목수 (일부):")
    g = df.dropna(subset=[mcol]).groupby(dt.dt.year)[ccol].nunique()
    for y in sorted(g.index):
        if y % 5 == 0 or y in (g.index.min(), g.index.max()):
            say(f"  {y}: {g[y]:,}종목")

    # ── 3. PIT 핵심 검사
    say(f"\n## 3. ★ PIT 검사 — 과거 시점에 미래 종목이 있는가\n")
    targets = [x for x in ("1999-12", "2004-12", "2009-12") if x in yms]
    if not targets:
        targets = yms[:3]
        say(f"⚠️ 1999-12 없음. 대신 {targets} 검사")

    verdict_bad = False
    for t in targets:
        sub = df[(df["_ym"] == t) & df[mcol].notna()].nlargest(30, mcol)
        say(f"\n### {t} 시총 top30")
        if sub.empty:
            say("  (데이터 없음)")
            continue
        found_modern = [(r[ccol], MODERN[r[ccol]]) for _, r in sub.iterrows() if r[ccol] in MODERN]
        found_old = [(r[ccol], OLD_LARGE[r[ccol]]) for _, r in sub.iterrows() if r[ccol] in OLD_LARGE]
        say("```")
        for i, (_, r) in enumerate(sub.iterrows(), 1):
            tag = ""
            if r[ccol] in MODERN:
                tag = f"  🚨 {MODERN[r[ccol]]}"
            elif r[ccol] in OLD_LARGE:
                tag = f"  ✅ {OLD_LARGE[r[ccol]]}"
            say(f"  {i:>2}. {r[ccol]}  {r[mcol]:>18,.0f}{tag}")
        say("```")
        if found_modern:
            verdict_bad = True
            say(f"  🚨 **미래 종목 {len(found_modern)}건 발견** — {', '.join(n for _, n in found_modern)}")
        else:
            say(f"  ✅ 미래 종목 없음 · 당시 대형주 매칭 {len(found_old)}건")

    # ── 4. 상폐 종목 존재 여부
    say(f"\n## 4. 상폐(중도소멸) 종목 포함 여부\n")
    last = yms[-1]
    alive = set(df.loc[df["_ym"] == last, ccol])
    ever = set(df[ccol])
    dead = ever - alive
    say(f"전체 {len(ever):,} · 최종시점 생존 {len(alive):,} · 중도소멸 {len(dead):,} ({len(dead)/len(ever):.1%})")
    if len(dead) / max(len(ever), 1) < 0.05:
        verdict_bad = True
        say("🚨 **중도소멸 5% 미만 — 상폐 종목 미수집(생존편향) 강력 의심**")
        say("   한국시장 30년이면 통상 30~50%가 상폐/합병/이전으로 사라진다.")
    else:
        say("✅ 상폐 종목이 원본에 남아 있음")

    # ── 5. 시총 값 자체가 시간에 따라 변하는가
    say(f"\n## 5. 시총 값의 시간 변화 (소급 상수 탐지)\n")
    samp = df[df[ccol] == "005930"].dropna(subset=[mcol]).sort_values("_ym")
    if len(samp) > 5:
        say("삼성전자(005930) 시총 추이 (일부):")
        say("```")
        for _, r in samp.iloc[::max(1, len(samp)//8)].iterrows():
            say(f"  {r['_ym']}  {r[mcol]:>20,.0f}")
        say("```")
        if samp[mcol].nunique() <= 2:
            verdict_bad = True
            say("🚨 **시총이 사실상 상수 — 소급 적용 확정**")
        else:
            say("✅ 시점별로 값이 변한다 (PIT 형태)")

    # ── 판정
    say(f"\n## 6. 판정\n")
    if verdict_bad:
        say("🚨 **시총 데이터에 look-ahead/생존편향 정황 확인**\n")
        say("→ `TOP30_고정 19.8%` · `동적 리더십 20.1%` · `무방어 21.7%` **전부 무효.**")
        say("→ 백서 3장 전체 재산출 필요. R2 실행은 이 문제 해결 후로 연기.")
        say("→ 클레임 레지스트리 C-003·C-019를 `invalidated`로 변경.")
    else:
        say("✅ **명백한 PIT 위반은 발견되지 않음**\n")
        say("→ 그렇다면 KOSPI 대비 +12.9%p 갭은 별개 조사 대상이다:")
        say("  ① KOSPI 벤치가 PR(배당 미포함)인가 TR인가 → PR이면 ~2%p 보정")
        say("  ② 동일가중 vs 시총가중 프리미엄 단독 측정 (같은 유니버스, 가중만 변경)")
        say("  ③ 미조정 월봉의 CA 점프 영향 (조정본으로 재산출)")
        say("  잔여 갭이 여전히 크면 **한국시장 EW 프리미엄이라는 독립 발견**이 된다.")

    Path(a.out).write_text("\n".join(L), encoding="utf-8")
    print(f"\n저장: {a.out}")
    sys.exit(1 if verdict_bad else 0)


if __name__ == "__main__":
    main()
