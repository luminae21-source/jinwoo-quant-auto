#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
forward 원장·동결사양서 점검기 v1
매월 1일 forward_signal.py 실행 직후 돌린다. 목적은 성과 확인이 아니라
**"사양서를 안 고쳤고 원장을 소급수정 안 했다"를 증명**하는 것.

사용:
  python forward_ledger_check.py --spec 실전준비/forward_동결사양서_v1.md \
                                 --ledger 실전준비/forward_ledger.csv \
                                 [--baseline .spec_baseline.txt]

첫 실행 시 사양서 해시를 baseline에 기록한다. 이후 실행은 baseline과 대조.
"""
import argparse, hashlib, os, sys
from datetime import datetime
import pandas as pd

N_HOLDINGS = 30
WEIGHT_TOL = 1e-3
FREEZE_MIN_MONTHS = 6   # 수정금지 최소 6개월 (사양서 §)


def sha256_file(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def check_spec(spec, baseline):
    print("\n[1] 동결사양서 무결성")
    if not os.path.exists(spec):
        print(f"  ❌ 사양서 없음: {spec}")
        return None
    cur = sha256_file(spec)
    if not os.path.exists(baseline):
        with open(baseline, "w") as f:
            f.write(f"{cur}\t{datetime.now():%Y-%m-%d}\t{spec}\n")
        print(f"  📌 baseline 최초 기록: {cur[:16]}…")
        print("     → 이 파일을 git에 커밋할 것. 이게 '안 고쳤다'의 증거다.")
        return cur
    old, date, _ = open(baseline).readline().strip().split("\t")
    if old == cur:
        print(f"  ✅ 사양서 불변 (동결 {date}, sha {cur[:16]}…)")
    else:
        print(f"  🚨 사양서 변경 감지! {old[:12]}… → {cur[:12]}…")
        print("     수정금지기간 중 변경 = forward 트랙 리셋 사유. 사유를 기록하고")
        print("     0개월차부터 다시 시작할지 결정할 것. 슬쩍 넘어가면 이 프로젝트의 A등급이 사라진다.")
    return cur


def check_ledger(path, spec_sha):
    print("\n[2] 원장 점검")
    if not os.path.exists(path):
        print(f"  ❌ 원장 없음: {path}")
        return
    df = pd.read_csv(path)
    print(f"  행 {len(df)} · 컬럼 {list(df.columns)[:8]}{'…' if len(df.columns) > 8 else ''}")

    # as-of 월 중복
    col = next((c for c in df.columns if "as_of" in c.lower() or "month" in c.lower()), None)
    if col:
        dup = df[col].duplicated().sum()
        print(f"  {'✅' if dup == 0 else '🚨'} as-of 중복 {dup}건"
              + ("" if dup == 0 else " — 같은 달을 두 번 기록했다면 하나는 재계산본이다. 사후수정 의심."))
        print(f"  기록된 월: {sorted(df[col].astype(str).unique())}")
        n_months = df[col].nunique()
    else:
        print("  ⚠️ as-of/month 컬럼을 못 찾음 — 스키마 확인 필요")
        n_months = len(df)

    # 종목수 · 가중치
    tcol = next((c for c in df.columns if "ticker" in c.lower() or "code" in c.lower()), None)
    wcol = next((c for c in df.columns if "weight" in c.lower() or "가중" in c), None)
    if col and tcol:
        for m, g in df.groupby(col):
            n = g[tcol].nunique()
            msg = f"  {'✅' if n == N_HOLDINGS else '🚨'} {m}: 종목 {n}/{N_HOLDINGS}"
            if wcol:
                s = pd.to_numeric(g[wcol], errors="coerce").sum()
                ok = abs(s - 1.0) < WEIGHT_TOL
                msg += f" · 가중합 {s:.4f} {'✅' if ok else '🚨'}"
            print(msg)

    # 사양서 해시가 원장에 박혀 있는가 (권장 스키마)
    scol = next((c for c in df.columns if "spec" in c.lower() and "sha" in c.lower()), None)
    print("\n[3] 사양서-원장 결속")
    if scol and spec_sha:
        mism = (df[scol].astype(str).str[:16] != spec_sha[:16]).sum()
        print(f"  {'✅' if mism == 0 else '🚨'} spec_sha 불일치 {mism}행")
    else:
        print("  ⚠️ 원장에 spec_sha 컬럼 없음 →  다음 달부터 컬럼 추가 권장.")
        print(f"     매월 기록 시 spec_sha={str(spec_sha)[:16] if spec_sha else '(미산출)'}… 를 함께 적으면")
        print("     '그 달의 신호가 그 시점 사양서로 만들어졌다'가 사후 증명된다.")

    # 게이트 카운트다운
    print("\n[4] 게이트 카운트다운")
    print(f"  누적 기록 {n_months}개월 / 최소 {FREEZE_MIN_MONTHS}개월 · 목표 12개월")
    if n_months < FREEZE_MIN_MONTHS:
        print(f"  ⏸ 판정 불가. {FREEZE_MIN_MONTHS - n_months}개월 더. 중간 수익률로 결론 금지.")
    else:
        print("  ▶ 최소기간 충족. 동결사양서 평가게이트 대조 가능.")


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--spec", default="forward_동결사양서_v1.md")
    ap.add_argument("--ledger", default="forward_ledger.csv")
    ap.add_argument("--baseline", default=".spec_baseline.txt")
    a = ap.parse_args()
    print("=" * 58)
    print(f" forward 점검  ·  {datetime.now():%Y-%m-%d %H:%M} KST")
    print("=" * 58)
    sha = check_spec(a.spec, a.baseline)
    check_ledger(a.ledger, sha)
    print("\n" + "=" * 58)
    print(" 이 점검의 목적은 성과 확인이 아니라 '안 고쳤음'의 증명이다.")
    print("=" * 58)
