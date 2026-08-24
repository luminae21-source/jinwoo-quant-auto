#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
재량 트랙 측정기 v2  (사양서: 재량트랙_측정사양서_v2.md)
- 원장(append-only)을 읽어 비용후 성과·승률·확신 캘리브레이션·알파 3종 산출
- 최소표본 미달 시 '판정 불가'만 출력한다 (사양서 §1-6, §4)

사용: python discretionary_metrics.py --process-only        # 매월 (기본)
      python discretionary_metrics.py --full-judgment   # 사전지정 판정일에만
"""
import argparse, hashlib, sys
from datetime import datetime
import pandas as pd
import numpy as np

ROUND_TRIP_COST = 0.0048      # 왕복 0.48% (forward 동결사양서와 동일)
MIN_CLOSED = 30               # 최소 종결 포지션
MIN_MONTHS = 36               # 1차 중간판정 시점 (v2: 12→36). 통과확률 27%임에 유의
MIN_NAMES  = 15               # R1: 상시 최소 종목수
MAX_WEIGHT = 0.12             # R1: 단일 종목 최대 비중
JUDGMENT_DATES = ("2029-07-31", "2031-07-31")
FREEZE_DATE = "2026-07-27"


def row_hash(r) -> str:
    key = f"{r.get('decision_id','')}|{r.get('decision_ts_kst','')}|{r.get('ticker','')}|{r.get('action','')}"
    return hashlib.sha256(key.encode()).hexdigest()[:16]


def load(ledger_path):
    df = pd.read_csv(ledger_path, dtype=str).fillna("")
    if df.empty:
        return df
    for c in ("conviction", "size_pct", "exec_price", "exit_price",
              "bm1_kospi_at_decision", "bm2_kq150_at_decision", "horizon_m"):
        if c in df:
            df[c] = pd.to_numeric(df[c], errors="coerce")
    for c in ("decision_ts_kst", "exec_ts", "exit_ts"):
        if c in df:
            df[c] = pd.to_datetime(df[c], errors="coerce")
    return df


def integrity(df):
    """append-only 위반·중복·사후기록 탐지 (사양서 §1)"""
    issues = []
    if df.empty:
        return issues
    if df["decision_id"].duplicated().any():
        issues.append("decision_id 중복 — append-only 위반 의심")
    if "row_sha" in df:
        bad = [r["decision_id"] for _, r in df.iterrows()
               if r["row_sha"] and r["row_sha"] != row_hash(r)]
        if bad:
            issues.append(f"row_sha 불일치(소급수정 의심): {bad[:5]}")
    late = df[(df["exec_ts"].notna()) & (df["decision_ts_kst"].notna()) &
              (df["exec_ts"] < df["decision_ts_kst"])]
    if len(late):
        issues.append(f"실행이 결정보다 앞선 행 {len(late)}건 — 사전기록 원칙 위반")
    if not (df["thesis_1line"].astype(str).str.strip() != "").all():
        issues.append("thesis 공란 행 존재 — 사양서 §1.4 위반")
    n_watch = (df["action"] == "watch").sum()
    n_buy = df["action"].isin(["buy", "add"]).sum()
    if n_buy > 0 and n_watch == 0:
        issues.append("watch 기록 0건 — 전수기록(체리피킹 차단) 미작동 의심")
    return issues


def closed_positions(df):
    m = df["exit_price"].notna() & df["exec_price"].notna() & (df["exec_price"] > 0)
    c = df[m].copy()
    if c.empty:
        return c
    c["gross_ret"] = c["exit_price"] / c["exec_price"] - 1
    c["net_ret"] = c["gross_ret"] - ROUND_TRIP_COST          # 비용 강제 (§1.5)
    c["hold_days"] = (c["exit_ts"] - c["exec_ts"]).dt.days
    return c


def report(df, monthly, full=False):
    print("=" * 58)
    print(" 재량 트랙 측정 리포트 (비용후 왕복 0.48% 반영)")
    print(f" 동결일 {FREEZE_DATE} · 생성 {datetime.now():%Y-%m-%d %H:%M}")
    print("=" * 58)

    iss = integrity(df)
    print("\n[무결성]")
    print("  ✅ 이상 없음" if not iss else "\n".join("  ⚠️ " + i for i in iss))

    if df.empty:
        print("\n원장이 비어 있다. 첫 결정을 적는 것부터가 트랙의 시작이다.")
        return

    c = closed_positions(df)
    n_closed = len(c)
    months = 0
    if df["decision_ts_kst"].notna().any():
        first = df["decision_ts_kst"].min()
        months = max(0.0, (datetime.now() - first).days / 30.44)

    print(f"\n[표본] 종결 {n_closed}건 / 필요 {MIN_CLOSED}  ·  경과 {months:.1f}개월 / 필요 {MIN_MONTHS}")
    print(f"       전체 결정 {len(df)}건 (watch {int((df['action']=='watch').sum())} · "
          f"실행 {int(df['action'].isin(['buy','add']).sum())})")
    if len(df):
        exec_rate = (df["executed"].str.upper() == "Y").mean()
        print(f"       결정→실행 전환율 {exec_rate:.0%}")

    if n_closed:
        wr = (c["net_ret"] > 0).mean()
        win = c.loc[c["net_ret"] > 0, "net_ret"].mean()
        loss = c.loc[c["net_ret"] <= 0, "net_ret"].mean()
        pl = abs(win / loss) if loss and not np.isnan(loss) else np.nan
        print("\n[종결 성과]")
        print(f"  평균 비용후 수익률 {c['net_ret'].mean():+.2%} · 중앙값 {c['net_ret'].median():+.2%}")
        print(f"  승률 {wr:.0%} · 손익비 {pl:.2f} · 평균보유 {c['hold_days'].mean():.0f}일")
        print(f"  최고 {c['net_ret'].max():+.1%} / 최악 {c['net_ret'].min():+.1%}")
        # 상위 3건 기여 집중도 — 한두 종목 운인지 확인
        top3 = c["net_ret"].nlargest(3).sum()
        print(f"  상위3건 수익 합 {top3:+.1%} (전체합 {c['net_ret'].sum():+.1%}) "
              f"→ 집중도 {top3/c['net_ret'].sum():.0%}" if c["net_ret"].sum() != 0 else "")

        # 확신 캘리브레이션 (§5) — 판정 아님, 참고
        cc = c.dropna(subset=["conviction"])
        if len(cc) >= 8:
            rho = cc["conviction"].corr(cc["net_ret"], method="spearman")
            verdict = ("확신에 정보 있음 → 사이징 근거" if rho > 0.3
                       else "확신은 노이즈 → 동일가중 전환 검토" if abs(rho) <= 0.15
                       else "약함 — 판단 보류")
            print(f"\n[확신 캘리브레이션] Spearman ρ = {rho:+.2f} → {verdict}  (참고용, 판정 아님)")

    # 알파 3종 — 사전지정 판정일에만 (v2 §2 훔쳐보기 금지)
    if not full:
        print("\n[알파]  🔒 --process-only 모드: 알파 출력 억제 (사양서 v2 §2)")
        print("       판정 시점: " + " · ".join(JUDGMENT_DATES))
    elif monthly is None or len(monthly) < 12:
        print("\n[알파]  월간 스냅샷 12개월 미만 → 계산 보류.")
    else:
        print("\n[알파]")
        m = monthly.copy()
        for c_ in ("nav", "bm1_kospi", "bm2_kq150", "bm3_forward_nav"):
            if c_ in m:
                m[c_] = pd.to_numeric(m[c_], errors="coerce")
        r = m["nav"].pct_change().dropna().values
        b1 = m["bm1_kospi"].pct_change().dropna().values
        n = min(len(r), len(b1)); r, b1 = r[-n:], b1[-n:]
        a0 = r.mean() - b1.mean()
        X = np.column_stack([np.ones(n), b1])
        coef, *_ = np.linalg.lstsq(X, r, rcond=None)
        resid = r - X @ coef
        s2 = (resid @ resid) / (n - 2)                      # 잔차 기반 (v1 버그 수정)
        se = np.sqrt(s2 * np.linalg.inv(X.T @ X)[0, 0])
        a1, beta, t = coef[0], coef[1], coef[0] / se
        te = resid.std(ddof=1) * np.sqrt(12)
        ir = (a1 * 12) / te if te > 0 else np.nan
        print(f"  α0 단순초과 {a0*12:+.2%}/yr")
        print(f"  α1 베타조정 {a1*12:+.2%}/yr  (beta={beta:.2f}, t={t:.2f}, n={n}개월)")
        print(f"  추적오차 TE {te:.1%}/yr · IR {ir:+.2f}")
        if abs(ir) > 0.01:
            print(f"  → 이 IR로 t>1.5 도달까지 필요기간 약 {(1.5/abs(ir))**2:.1f}년")
        print("  α2 팩터조정 — 시스템 팩터 z-노출 회귀 필요 (mini_factor_adj 연결 후)")
        if "bm3_forward_nav" in m and m["bm3_forward_nav"].notna().sum() > 2:
            b3 = m["bm3_forward_nav"].pct_change().dropna().values
            k = min(len(r), len(b3))
            print(f"  vs 시스템(BM3): {((r[-k:].mean()-b3[-k:].mean())*12):+.2%}/yr")

    # 판정 게이트 (§4)
    print("\n[게이트 판정]")
    if n_closed < MIN_CLOSED or months < MIN_MONTHS:
        print("  ⏸  판정 불가 — 표본 미달. 중간 성적으로 결론 내지 말 것.")
        print(f"     남은 조건: 종결 {max(0, MIN_CLOSED-n_closed)}건 · "
              f"{max(0, MIN_MONTHS-months):.1f}개월")
        print("     참고: 실력 연 6%여도 12개월 게이트 통과율은 14%다. 기다림이 설계다.")
    else:
        print("  ▶ 표본 충족. 사양서 v2 §4 판정표로 대조 후 결론 기록.")
    print("\n" + "=" * 58)


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--ledger", default="재량트랙_ledger.csv")
    ap.add_argument("--monthly", default="재량트랙_monthly.csv")
    ap.add_argument("--full-judgment", action="store_true",
                    help="사전지정 판정일(2029-07-31/2031-07-31)에만 사용. 미지정 시 프로세스 지표만 출력 (v2 §2)")
    a = ap.parse_args()
    try:
        df = load(a.ledger)
    except FileNotFoundError:
        sys.exit(f"원장 없음: {a.ledger}")
    try:
        mo = pd.read_csv(a.monthly)
    except Exception:
        mo = None
    report(df, mo, full=a.full_judgment)
