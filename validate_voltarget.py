#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
validate_voltarget.py — 본체 v3.7.2 변동성 타겟팅 오버레이 그리드 검증 (2026-06-07)

목적: [진우퀀트_손절사이징_룰_파라미터.md §1] 의 변동성 타겟을 실측. v37_2 백테스트의
      월별 수익률 위에 "목표 변동성으로 총노출 조정" 오버레이를 (목표vol × 윈도우 × 비용)
      그리드로 적용해, base 대비 net Sharpe·MDD·CAGR·회전율 트레이드오프를 본다.

정직성(프로젝트 §0): 인샘플 백테스트. forward 기대치 아님. 노출 상한 1.0(차입 금지),
      현금수익 0 가정(보수적). 노출은 t-1까지의 실현변동성으로 결정 → 룩어헤드 없음.

사용:
  python validate_voltarget.py                         # 기본 그리드
  python validate_voltarget.py --json backtest_v37_2_20260602_0158.json --col r_v37_2_%
  python validate_voltarget.py --cost_bps 40           # 노출변경 1회당 왕복비용 bp
  python validate_voltarget.py --self-test             # 합성데이터 정확성 검증
"""
import argparse, glob, json, math, sys

ANN = 12  # 월별 → 연환산


# ---------- 유틸 ----------
def _stdev(xs):
    n = len(xs)
    if n < 2:
        return 0.0
    m = sum(xs) / n
    return math.sqrt(sum((x - m) ** 2 for x in xs) / (n - 1))  # 표본표준편차


def metrics(monthly_pct):
    """월수익률(%) 리스트 → CAGR%, 연변동성%, Sharpe(rf=0), MDD%."""
    r = [x / 100.0 for x in monthly_pct]
    n = len(r)
    if n == 0:
        return dict(CAGR=0, vol=0, Sharpe=0, MDD=0, n=0)
    cum = 1.0
    for x in r:
        cum *= (1 + x)
    cagr = cum ** (ANN / n) - 1
    mu = sum(r) / n
    sd = _stdev(r)
    sharpe = (mu / sd * math.sqrt(ANN)) if sd > 0 else 0.0
    peak = 1.0; eq = 1.0; mdd = 0.0
    for x in r:
        eq *= (1 + x); peak = max(peak, eq); mdd = min(mdd, eq / peak - 1)
    return dict(CAGR=cagr * 100, vol=sd * math.sqrt(ANN) * 100, Sharpe=sharpe,
                MDD=mdd * 100, n=n)


# ---------- 오버레이 ----------
def apply_voltarget(base_pct, target_vol_ann, window, cost_bps, ewma_lambda=None):
    """
    base_pct: 전략 월수익률(%) 리스트 (오버레이 전).
    target_vol_ann: 목표 연변동성(소수, 예 0.20). None이면 base 그대로 반환.
    window: 실현변동성 추정 윈도우(월). ewma_lambda 주면 EWMA 사용(window 무시).
    cost_bps: 노출 변경(|Δexposure|) 1회당 왕복비용 bp. 결과 수익에서 차감.
    반환: (net월수익률 리스트, 연회전율, 평균노출)
    """
    if target_vol_ann is None:
        return list(base_pct), 0.0, 1.0
    tgt_m = target_vol_ann / math.sqrt(ANN)          # 월 목표 변동성
    rdec = [x / 100.0 for x in base_pct]
    net = []
    exposures = []
    prev_exp = 1.0
    turn = 0.0
    ewma_var = None
    for i, x in enumerate(rdec):
        # --- t시점 노출 결정: t-1까지의 정보만 사용 (룩어헤드 방지) ---
        if ewma_lambda is not None:
            sd_hat = math.sqrt(ewma_var) if ewma_var is not None else None
        else:
            hist = rdec[max(0, i - window):i]        # t 이전 window개
            sd_hat = _stdev(hist) if len(hist) >= 2 else None
        if sd_hat is None or sd_hat == 0:
            exp = 1.0                                  # 추정 불가 초기 → 풀노출
        else:
            exp = min(1.0, tgt_m / sd_hat)            # 차입 금지 → 상한 1.0
        exposures.append(exp)
        turn += abs(exp - prev_exp)
        cost = abs(exp - prev_exp) * (cost_bps / 1e4)
        net.append((exp * x - cost) * 100.0)
        prev_exp = exp
        # --- EWMA 분산 갱신 (다음 달 추정용, 실현 후) ---
        if ewma_lambda is not None:
            ewma_var = x * x if ewma_var is None else ewma_lambda * ewma_var + (1 - ewma_lambda) * x * x
    years = len(rdec) / ANN
    ann_turn = turn / years if years > 0 else 0.0
    avg_exp = sum(exposures) / len(exposures) if exposures else 1.0
    return net, ann_turn, avg_exp


# ---------- 데이터 ----------
def load_returns(json_path, col):
    d = json.load(open(json_path, encoding="utf-8"))
    hist = d.get("history", [])
    out = [h[col] for h in hist if h.get(col) is not None]
    if not out:
        sys.exit("'%s' 컬럼을 history에서 못 찾음. --col 확인." % col)
    return out


# ---------- 그리드 ----------
def run_grid(base_pct, cost_bps):
    targets = [None, 0.14, 0.16, 0.18, 0.20, 0.22]
    windows = [2, 3, 6]
    base_m = metrics(base_pct)
    print("기간 %d개월 | base: CAGR %.1f%%  vol %.1f%%  Sharpe %.2f  MDD %.1f%%"
          % (base_m["n"], base_m["CAGR"], base_m["vol"], base_m["Sharpe"], base_m["MDD"]))
    print("노출변경 비용 %dbp/왕복 | 노출상한 1.0(차입금지) | 현금수익 0 가정\n" % cost_bps)
    hdr = "%-10s %-6s | %7s %7s %7s %8s %7s %7s" % (
        "목표vol", "윈도우", "CAGR%", "vol%", "Sharpe", "MDD%", "연회전", "평균노출")
    print(hdr); print("-" * len(hdr))
    for tv in targets:
        wins = [windows[0]] if tv is None else windows
        for w in wins:
            net, turn, avgexp = apply_voltarget(base_pct, tv, w, cost_bps)
            m = metrics(net)
            label = "base" if tv is None else ("%.0f%%" % (tv * 100))
            wlabel = "-" if tv is None else "%dM" % w
            print("%-10s %-6s | %7.1f %7.1f %7.2f %8.1f %7.2f %7.2f"
                  % (label, wlabel, m["CAGR"], m["vol"], m["Sharpe"], m["MDD"], turn, avgexp))
    # EWMA 변형도 1줄
    for tv in [0.18, 0.20]:
        net, turn, avgexp = apply_voltarget(base_pct, tv, 3, cost_bps, ewma_lambda=0.84)
        m = metrics(net)
        print("%-10s %-6s | %7.1f %7.1f %7.2f %8.1f %7.2f %7.2f"
              % ("%.0f%%" % (tv * 100), "EWMA", m["CAGR"], m["vol"], m["Sharpe"], m["MDD"], turn, avgexp))
    print("\n해석: Sharpe·MDD 개선 대비 CAGR 희생을 보고 목표vol/윈도우 선택. "
          "MDD가 크게 줄고 Sharpe 유지/개선되면 채택 후보. (인샘플 — OOS 확인 필요)")


# ---------- self-test ----------
def self_test():
    ok = tot = 0
    def chk(name, cond):
        nonlocal ok, tot
        tot += 1; ok += bool(cond)
        print(("  [%s] " % ("OK" if cond else "XX")) + name)

    # 1) metrics: 매월 +1% 12개월 → CAGR≈12.68%, MDD 0
    m = metrics([1.0] * 12)
    chk("CAGR(+1%x12)≈12.68", abs(m["CAGR"] - 12.6825) < 0.05)
    chk("MDD=0 (무손실)", abs(m["MDD"]) < 1e-9)

    # 2) target=None → base 그대로
    base = [2.0, -3.0, 1.5, 4.0, -1.0, 0.5]
    net, turn, ae = apply_voltarget(base, None, 3, 40)
    chk("None이면 base동일", net == base and turn == 0.0 and ae == 1.0)

    # 3) 룩어헤드 없음: 첫 window개월은 노출=1 (추정 불가)
    net, turn, ae = apply_voltarget(base, 0.10, 3, 0)
    chk("초기 노출=1 (i<2는 풀노출, 비용0이면 net[0]=base[0])", abs(net[0] - base[0]) < 1e-9)

    # 4) 노출은 항상 ≤1 (차입 금지) → 저변동 입력서 net이 base 초과 안 함
    calm = [0.2, -0.1, 0.15, -0.05, 0.1, 0.2, -0.1, 0.1]
    net, turn, ae = apply_voltarget(calm, 0.50, 3, 0)
    chk("노출상한1.0: 평균노출≤1", ae <= 1.0 + 1e-9)

    # 5) 고변동 입력 → 노출 축소로 변동성 감소
    wild = [10, -12, 9, -11, 8, -9, 11, -10, 7, -8]
    net, turn, ae = apply_voltarget(wild, 0.20, 3, 0)
    chk("고변동→노출축소(평균<1)", ae < 1.0)
    chk("고변동→net 변동성 < base", metrics(net)["vol"] < metrics(wild)["vol"])

    # 6) 비용 차감 방향성: cost_bps↑ → CAGR↓
    n0, _, _ = apply_voltarget(wild, 0.20, 3, 0)
    n1, _, _ = apply_voltarget(wild, 0.20, 3, 100)
    chk("비용↑ → CAGR↓", metrics(n1)["CAGR"] <= metrics(n0)["CAGR"] + 1e-9)

    print("\nself-test: %d/%d 통과" % (ok, tot))
    return ok == tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", default=None, help="백테스트 결과 json (기본: backtest_v37_2_*.json 최신)")
    ap.add_argument("--col", default="r_v37_2_%", help="월수익률 컬럼명")
    ap.add_argument("--cost_bps", type=float, default=40.0, help="노출변경 왕복비용 bp")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(0 if self_test() else 1)
    path = a.json
    if path is None:
        cands = sorted(glob.glob("backtest_v37_2_*.json"))
        if not cands:
            sys.exit("backtest_v37_2_*.json 없음. --json 지정.")
        path = cands[-1]
    print("입력:", path, "| 컬럼:", a.col, "\n")
    base = load_returns(path, a.col)
    run_grid(base, a.cost_bps)


if __name__ == "__main__":
    main()
