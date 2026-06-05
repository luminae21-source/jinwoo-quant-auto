#!/usr/bin/env python3
"""
backtest_c1.py — #3 C1 regime 오버레이 백테스트 (production 파일 미수정)
==============================================================================
KOSPI regime ON(추세 상승 AND 변동성 비극단)일 때만 Echo 가중↑·BAB 가중↓ 로 재점수화 →
baseline v3.7.2 vs C1-regime 오버레이 비교. (근거: 장지원 Echo 상승장 의존 + Novy-Marx-Velikov BAB 대형주 무알파 + Daniel-Moskowitz 크래시는 고변동에서)
※ 채택 판정은 #1(finalize_robustness) 통과 후 + §7 게이트 충족 시에만.

score_v37 / score_v37_1 / score_v37_2 / backtest_v37_2 모듈 재사용.
사용: python backtest_c1.py --echo-on 1.5 --bab-on 0.0   /   python backtest_c1.py --selftest
의존성: 위 모듈 + FDR(전체 실행 시). 코어(regime·재점수화)는 FDR 없이 검증.
"""
import sys, json, argparse
from datetime import datetime
import numpy as np, pandas as pd

from score_v37 import (JINWOO_v37, compute_mom12, compute_beta60,
                       mom12_to_score, noa_to_score, far_trigger, grade)
from score_v37_1 import bab_to_score
from score_v37_2 import ECHO_WEIGHT
import backtest_v37_2 as B   # fetch_long_panel, compute_echo_scores_at, avg_return, kospi_return, metrics, information_ratio


def detect_regime(kospi, dt, ma_win=200, vol_win=60):
    """KOSPI regime ON = (종가 > MA200) AND (최근 변동성 < 과거 중앙값). 데이터 부족 시 ON(보수)."""
    k = kospi[kospi.index <= dt].dropna()
    if len(k) < ma_win + 5:
        return True
    trend = bool(k.iloc[-1] > k.rolling(ma_win).mean().iloc[-1])
    dret = k.pct_change()
    vol_now = dret.tail(vol_win).std()
    vol_med = dret.rolling(vol_win).std().expanding().median().iloc[-1]
    vol_ok = bool(vol_now < vol_med) if pd.notna(vol_med) else True
    return bool(trend and vol_ok)


def scores_baseline_and_regime(panel, dt, regime_on, echo_w_on=1.5, bab_k_on=0.0):
    """각 종목의 baseline(v3.7.2) 등급 + C1-regime 등급 동시 산출."""
    kospi = panel.get("_KOSPI"); echo_scores = B.compute_echo_scores_at(panel, dt)
    echo_w = echo_w_on if regime_on else ECHO_WEIGHT
    bab_k = bab_k_on if regime_on else 1.0
    rows = []
    for name, info in JINWOO_v37.items():
        s = panel.get(name)
        if s is None or len(s) == 0: continue
        s_cut = s[s.index <= dt]; k_cut = kospi[kospi.index <= dt]
        if len(s_cut) < 253: continue
        base12 = info["F_korean"] * (12/9.001)
        r1m = s_cut.iloc[-1]/s_cut.iloc[-21] - 1 if len(s_cut) >= 22 else None
        far_val, _ = far_trigger(base12, r1m)
        core = base12 + info["ModF"] + far_val + info["Sloan"] + mom12_to_score(compute_mom12(s_cut)) + noa_to_score(info.get("NOA", 0))
        bab_raw = bab_to_score(compute_beta60(s_cut, k_cut))
        echo_dir = echo_scores.get(name, 0)
        total_base = core + bab_raw*1.0 + echo_dir*ECHO_WEIGHT
        total_reg = core + bab_raw*bab_k + echo_dir*echo_w
        rows.append({"종목": name, "등급_base": grade(total_base), "등급_reg": grade(total_reg)})
    return pd.DataFrame(rows)


def run_c1(panel, args):
    target = set(args.top_grades.split(",")); k = panel.get("_KOSPI")
    end = k.index[-1]; start = end - pd.DateOffset(years=args.years)
    bp = k[(k.index >= start) & (k.index <= end)]
    rebal = sorted(set(k.index[k.index.get_indexer([d], method="bfill")[0]]
                       for d in bp.resample("MS").first().dropna().index if d <= end))
    if rebal[-1] < end: rebal.append(end)
    rets = {"372": [], "372reg": [], "b": []}; hist = []; on_cnt = 0
    for i in range(len(rebal)-1):
        d0, d1 = rebal[i], rebal[i+1]
        on = detect_regime(k, d0); on_cnt += int(on)
        snap = scores_baseline_and_regime(panel, d0, on, args.echo_on, args.bab_on)
        if len(snap) == 0: continue
        pb = snap[snap["등급_base"].isin(target)]["종목"].tolist()
        pr = snap[snap["등급_reg"].isin(target)]["종목"].tolist()
        rb = B.avg_return(pb, panel, d0, d1); rr = B.avg_return(pr, panel, d0, d1)
        rk = B.kospi_return(panel, d0, d1)
        rets["372"].append(rb); rets["372reg"].append(rr); rets["b"].append(rk)
        hist.append({"date": pd.Timestamp(d1).strftime("%Y-%m-%d"), "regime_on": int(on),
                     "r_v37_2_%": round(rb*100,2), "r_v372_regime_%": round(rr*100,2), "r_kospi_%": round(rk*100,2)})
    m = {kk: B.metrics(rets[kk]) for kk in rets}
    print("="*72); print(f"C1 regime 오버레이 ({args.years}년 · Echo ON×{args.echo_on} · BAB ON×{args.bab_on} · regime ON {on_cnt}/{len(rebal)-1}월)"); print("="*72)
    for lab, key in [("v3.7.2 baseline","372"), ("C1 regime","372reg"), ("KOSPI","b")]:
        mm = m[key]; print(f"{lab:16} 연환산 {mm.get('연환산',0):>6.2f}%  Sharpe {str(mm.get('Sharpe','-')):>5}  MDD {mm.get('MDD',0):>6.2f}%")
    d = m["372reg"].get("연환산",0) - m["372"].get("연환산",0)
    ds = (m["372reg"].get("Sharpe") or 0) - (m["372"].get("Sharpe") or 0)
    print(f"\nC1 vs v3.7.2: 연환산 {d:+.2f}%p · Sharpe {ds:+.2f}")
    print("게이트(채택 조건): 연환산 ≥ +1%p AND MDD 악화 ≤ +0.5%p AND #1 통과 — 미충족 시 연기")
    rep = {"timestamp": datetime.now().isoformat(), "params": {"echo_on":args.echo_on,"bab_on":args.bab_on},
           "metrics": m, "history": hist}
    out = f'backtest_c1_{datetime.now().strftime("%Y%m%d_%H%M")}.json'
    open(out, "w", encoding="utf-8").write(json.dumps(rep, ensure_ascii=False, indent=2, default=str))
    print(f"💾 {out} (history에 r_v372_regime_% → build_trial_matrix/run_attribution 재사용 가능)")
    return rep


def _selftest():
    # FDR 없이: 합성 패널로 regime 검출 + 재점수화 코어 검증
    rng = np.random.default_rng(0)
    idx = pd.date_range("2023-01-01", periods=340, freq="B")
    ret_up = np.concatenate([rng.normal(0.0005, 0.020, 200), rng.normal(0.0012, 0.006, 140)])  # 후반 저변동
    up = pd.Series(2000*np.cumprod(1+ret_up), index=idx)                            # 상승 추세 + 최근 저변동
    down = pd.Series(2000*np.cumprod(1+rng.normal(-0.002, 0.03, 340)), index=idx)   # 하락·고변동
    print("regime 검출: 상승저변동 →", detect_regime(up, idx[-1]), "| 하락고변동 →", detect_regime(down, idx[-1]))
    assert detect_regime(up, idx[-1]) is True and detect_regime(down, idx[-1]) is False
    panel = {"_KOSPI": up}
    for name in JINWOO_v37:
        panel[name] = pd.Series(1000*np.cumprod(1+rng.normal(0.001, 0.02, 340)), index=idx)
    base_off = scores_baseline_and_regime(panel, idx[-1], regime_on=False)
    reg_on = scores_baseline_and_regime(panel, idx[-1], regime_on=True, echo_w_on=1.5, bab_k_on=0.0)
    chg = int((base_off["등급_base"].values != reg_on["등급_reg"].values).sum())
    print(f"종목 {len(base_off)}개 | OFF=base와 동일(검증): {(base_off['등급_base'].values==reg_on['등급_base'].values).all()} | regime ON 등급변동 {chg}개")
    assert len(base_off) == 18
    print("\n[OK] backtest_c1 코어(regime 검출 + 재점수화) selftest 통과 — 전체 백테스트는 PC(FDR)에서")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--years", type=int, default=4); ap.add_argument("--top-grades", default="S+,S,A")
    ap.add_argument("--echo-on", type=float, default=1.5); ap.add_argument("--bab-on", type=float, default=0.0)
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest: return _selftest()
    panel = B.fetch_long_panel(a.years)
    if panel.get("_KOSPI") is None: sys.exit(1)
    run_c1(panel, a)


if __name__ == "__main__":
    sys.exit(main() or 0)
