#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_data_coverage.py — 수익률 데이터 누락·오염 감사 (진우퀀트 PC용)

사용:
  python audit_data_coverage.py --dir "Desktop\\진우퀀트\\데이터수리" [--out 감사_데이터커버리지.md]

스키마를 자동 탐지한다(날짜/종목/가격 컬럼명 추정). 파일은 csv/parquet 모두 지원.

검사 항목 — '누락'은 네 가지 얼굴을 하고 온다:
  A. 눈에 보이는 결측  (셀이 비어 있음)
  B. 조용한 탈락       (파이프라인이 dropna로 종목을 떨궈 유니버스가 줄어듦)  ★가장 위험
  C. 존재하지 않는 결측(상폐 종목이 애초에 수집 안 됨 = 생존편향)             ★가장 치명
  D. 값은 있으나 틀림  (미조정 분할/증자 잔존 → 가짜 ±50% 수익률)
"""
try:  # 윈도 파이프(cp949)에서 이모지 출력 시 UnicodeEncodeError 방지 (2026-07-27)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse, sys, re
from pathlib import Path
import numpy as np
import pandas as pd

DATE_HINTS = ["date", "일자", "날짜", "기준일", "trd_dd", "dt"]
CODE_HINTS = ["code", "ticker", "종목코드", "단축코드", "isu_srt_cd", "symbol"]
PRICE_HINTS = ["adj_close", "수정종가", "close", "종가", "clsprc", "price"]
RET_HINTS = ["ret", "수익률", "return", "chg"]

OUT = []
def say(s=""):
    print(s); OUT.append(s)


def guess(cols, hints):
    low = {c: str(c).lower() for c in cols}
    for h in hints:
        for c, l in low.items():
            if h in l:
                return c
    return None


def load_any(p: Path):
    if p.suffix.lower() in (".parquet", ".pq"):
        return pd.read_parquet(p)
    for enc in ("utf-8", "cp949", "utf-8-sig"):
        try:
            return pd.read_csv(p, encoding=enc, low_memory=False)
        except UnicodeDecodeError:
            continue
    return pd.read_csv(p, low_memory=False, encoding_errors="replace")


def audit_file(p: Path):
    say(f"\n{'='*72}\n▶ {p.name}  ({p.stat().st_size/1e6:.1f} MB)\n{'='*72}")
    try:
        df = load_any(p)
    except Exception as e:
        say(f"  ❌ 로드 실패: {e}")
        return

    dcol = guess(df.columns, DATE_HINTS)
    ccol = guess(df.columns, CODE_HINTS)
    pcol = guess(df.columns, PRICE_HINTS)
    rcol = guess(df.columns, RET_HINTS)
    say(f"  스키마 추정: 날짜={dcol} · 종목={ccol} · 가격={pcol} · 수익률={rcol}")
    say(f"  행 {len(df):,} · 컬럼 {len(df.columns)}")
    if not (dcol and ccol):
        say("  ⚠️ 날짜/종목 컬럼 미탐지 → 커버리지 검사 생략. --map 옵션으로 지정 필요.")
        return

    df[dcol] = pd.to_datetime(df[dcol], errors="coerce", format="mixed")
    bad_date = df[dcol].isna().sum()
    if bad_date:
        say(f"  🚨 [A] 날짜 파싱 실패 {bad_date:,}행")

    df[ccol] = df[ccol].astype(str).str.strip()
    n_codes = df[ccol].nunique()
    span = f"{df[dcol].min():%Y-%m} ~ {df[dcol].max():%Y-%m}"
    say(f"  종목 {n_codes:,} · 기간 {span}")

    # ── A. 명시적 결측
    say("\n  [A] 명시적 결측")
    for c in [x for x in (pcol, rcol) if x]:
        na = df[c].isna().sum()
        say(f"    {c}: {na:,}행 ({na/len(df):.2%}) {'✅' if na/len(df) < 0.001 else '🚨'}")

    # ── 중복
    dup = df.duplicated([dcol, ccol]).sum()
    say(f"    (종목,날짜) 중복: {dup:,} {'✅' if dup == 0 else '🚨 — 재계산본 혼입 의심'}")

    # ── B. 조용한 탈락: 연도별 유효 종목수 추이
    say("\n  [B] 연도별 유효 종목수 (급감 = 조용한 탈락 / 커버리지 천장)")
    if pcol:
        g = df.dropna(subset=[pcol]).groupby(df[dcol].dt.year)[ccol].nunique()
    else:
        g = df.groupby(df[dcol].dt.year)[ccol].nunique()
    prev = None
    for y, n in g.items():
        flag = ""
        if prev and n < prev * 0.8:
            flag = f"  🚨 전년比 {n/prev-1:+.0%} 급감"
        bar = "█" * int(n / max(g) * 30)
        say(f"    {y}  {n:>5,}  {bar}{flag}")
        prev = n
    say(f"    → 커버리지 천장: 유효종목이 최대치의 50% 미만인 연도는 백테에서 제외 검토")
    thin = [str(y) for y, n in g.items() if n < max(g) * 0.5]
    if thin:
        say(f"    ⚠️ 희박 연도: {', '.join(thin)}  (세션정리의 '2014 이전 21%' 판단과 대조할 것)")

    # ── C. 생존편향: 마지막 날짜에 사라진 종목이 있는가
    say("\n  [C] 생존편향 점검")
    last_dt = df[dcol].max()
    alive = set(df.loc[df[dcol] == last_dt, ccol])
    ever = set(df[ccol])
    dead = ever - alive
    say(f"    전체 {len(ever):,} · 최종일 생존 {len(alive):,} · 중도소멸 {len(dead):,}"
        f" ({len(dead)/len(ever):.1%})")
    if len(dead) / max(len(ever), 1) < 0.05:
        say("    🚨 중도소멸 5% 미만 — **상폐 종목이 수집 안 됐을 가능성**. 생존편향 위험.")
        say("       한국시장 10년 창이면 통상 15~25%가 상폐/합병/이전으로 사라진다.")
    else:
        say("    ✅ 소멸 종목이 원본에 남아 있음 (생존편향 방어 정상)")

    # ── D. 값 오염: 비정상 점프
    if pcol:
        say("\n  [D] 가격 이상치 (미조정 분할/증자 잔존 탐지)")
        s = df.sort_values([ccol, dcol])
        r = s.groupby(ccol)[pcol].pct_change()
        for th in (0.30, 0.50, 0.90):
            n = (r.abs() > th).sum()
            say(f"    |1기 수익률| > {th:.0%}: {n:,}건 ({n/len(r.dropna()):.3%})")
        ext = (r.abs() > 0.90).sum()
        say(f"    {'🚨 ±90% 초과가 존재 — 조정 누락 의심 종목 확인 필요' if ext else '✅ ±90% 초과 없음'}")
        if ext:
            worst = s.loc[r.abs() > 0.90, [dcol, ccol, pcol]].head(10)
            say("    상위 사례:")
            for _, w in worst.iterrows():
                say(f"      {w[dcol]:%Y-%m-%d} {w[ccol]} {w[pcol]}")
        nonpos = (pd.to_numeric(df[pcol], errors="coerce") <= 0).sum()
        say(f"    0 이하 가격: {nonpos:,} {'✅' if nonpos == 0 else '🚨'}")

    # ── 종목별 연속결측 (거래정지 구간)
    say("\n  [E] 종목별 관측일 편차")
    cnt = df.groupby(ccol)[dcol].count()
    say(f"    관측일 중앙값 {cnt.median():.0f} · 최소 {cnt.min()} · 25%tile {cnt.quantile(.25):.0f}")
    tiny = (cnt < cnt.median() * 0.2).sum()
    say(f"    관측일이 중앙값의 20% 미만인 종목: {tiny:,}"
        f" {'✅' if tiny/len(cnt) < 0.1 else '⚠️ 신규상장/상폐 다수 — 팩터 계산 시 최소관측 요건 확인'}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--dir", required=True)
    ap.add_argument("--pattern", default="*")
    ap.add_argument("--out", default="감사_데이터커버리지.md")
    a = ap.parse_args()

    root = Path(a.dir)
    if not root.exists():
        sys.exit(f"경로 없음: {root}")
    files = [p for p in sorted(root.rglob(a.pattern))
             if p.suffix.lower() in (".csv", ".parquet", ".pq")]
    say(f"# 데이터 커버리지 감사\n\n대상 `{root}` · 파일 {len(files)}개\n")
    if not files:
        say("데이터 파일을 못 찾음. --pattern 확인.")
    for p in files:
        audit_file(p)

    say("\n" + "=" * 72)
    say("판정 규칙: 🚨 = 백테 결과를 바꿀 수 있는 결함 · ⚠️ = 문서에 caveat 필요")
    say("특히 [C] 생존편향과 [B] 조용한 탈락은 수익률을 **위쪽으로** 왜곡한다.")
    Path(a.out).write_text("\n".join(OUT), encoding="utf-8")
    print(f"\n리포트 저장: {a.out}")


if __name__ == "__main__":
    main()
