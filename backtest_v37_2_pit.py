#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest_v37_2_pit.py — 영역4 Phase3: v3.7.2 백테스트 진짜 OOS (재무 PIT)

목적 (Phase3 설계메모):
  backtest_v37_2.py는 체력(F_korean)·Sloan·NOA를 종목별 단일 정적값으로 전 기간 적용
  = 부분 lookahead. 본 스크립트는 재무 파생을 리밸 시점(FY−1) PIT 값으로 갈아끼워
  static vs PIT를 **같은 패널·같은 엔진·동시점**으로 비교 → 71% CAGR이 lookahead 산물인지 검증.

스코어링:
  static arm = backtest_v37_2.compute_scores_at 그대로 (F_korean·Sloan·NOA 정적 = 검증 기준)
  PIT arm    = F(정수 Piotroski, FY−1)×12/9 + Sloan(_qscore accrual 5분위) + NOA(_qscore noa_ratio 5분위)
               + ModF(정적 잔재) + Echo·Mom·BAB(가격, 이미 PIT)   ← 영역3 PIT-proxy 정의
  공통: grade() 절대컷, picks={S+,S,A}, EW, 무비용 (backtest_v37_2와 동일 엔진)

합격선 (설계메모 §3, 사전등록 — 진우 승인 2026-06-08):
  A. 로버스트니스 임계: PIT IR ≥ 1.0  AND  PIT CAGR ≥ static CAGR − 15%p   → "lookahead 무해"
     미달 → static 과대(lookahead) → production 재검토 플래그
  B. 전체 delta 표 병기 (CAGR·Sharpe·MDD·IR·연도별) — 해석용

한계 (설계메모 §4): F_korean·Sloan·NOA 모두 Colab-유산 정적점수 → PIT는 raw로 재계산(정의 차이).
  즉 'lookahead 제거 + 점수정의 변경'이 섞임(순수 격리 아님). ModF는 raw 부재로 정적 유지(잔재).

실행:
  python backtest_v37_2_pit.py --self-test     # 네트워크 불필요
  python backtest_v37_2_pit.py                 # [PC] FDR + score_inputs_univ.csv 필요
"""
import sys, argparse, json
from datetime import datetime
from pathlib import Path
import pandas as pd
import numpy as np

BASE = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE))

from score_v37 import (JINWOO_v37, KOSPI_CODE, compute_mom12, compute_beta60,
                       mom12_to_score, far_trigger, grade)
from score_v37_1 import bab_to_score as bab_to_score_v371
from score_v37_2 import ECHO_WEIGHT
from pit_universe_backtest import _qscore
from backtest_v37_2 import (fetch_long_panel, compute_echo_scores_at,
                            compute_scores_at as compute_static_at,
                            avg_return, kospi_return, metrics, information_ratio)

INPUTS_CSV = BASE / 'score_inputs_univ.csv'
ROT_MONTH = 5
TARGET = {'S+', 'S', 'A'}
IR_MIN = 1.0          # 합격선 A-1 (사전등록)
CAGR_DELTA_MIN = -15.0  # 합격선 A-2 (%p, 사전등록)


def fy_for(d0):
    d0 = pd.Timestamp(d0)
    return d0.year - 1 if d0.month >= ROT_MONTH else d0.year - 2


def load_inputs_by_code(path=INPUTS_CSV):
    """{code: {fy: {'F':int,'accrual':float,'noa_ratio':float}}}"""
    df = pd.read_csv(path, dtype={'code': str})
    out = {}
    for _, r in df.iterrows():
        code = str(r['code']).zfill(6)
        fy = int(r['fiscal_year'])
        def _f(v):
            try:
                return float(v)
            except (ValueError, TypeError):
                return None
        out.setdefault(code, {})[fy] = {
            'F': _f(r.get('F')), 'accrual': _f(r.get('accrual')),
            'noa_ratio': _f(r.get('noa_ratio')),
        }
    return out


# ============================================================
# PIT 스코어링 (재무 = FY−1 PIT, 가격 = 그대로)
# ============================================================
def compute_scores_pit_at(panel, dt, inputs_by_code):
    kospi = panel.get('_KOSPI')
    echo_scores = compute_echo_scores_at(panel, dt)
    fy = fy_for(dt)

    # 횡단면 raw 수집 → _qscore(5분위)
    accr, noar = {}, {}
    for name, info in JINWOO_v37.items():
        row = inputs_by_code.get(str(info['코드']).zfill(6), {}).get(fy)
        if not row:
            continue
        if row.get('accrual') is not None:
            accr[name] = row['accrual']
        if row.get('noa_ratio') is not None:
            noar[name] = row['noa_ratio']
    sloan_q = _qscore(pd.Series(accr), good_low=True) if accr else pd.Series(dtype=float)
    noa_q = _qscore(pd.Series(noar), good_low=True) if noar else pd.Series(dtype=float)

    rows = []
    for name, info in JINWOO_v37.items():
        s = panel.get(name)
        if s is None or len(s) == 0:
            continue
        s_cut = s[s.index <= dt]
        k_cut = kospi[kospi.index <= dt]
        if len(s_cut) < 253:
            continue
        row = inputs_by_code.get(str(info['코드']).zfill(6), {}).get(fy)
        F_pit = row['F'] if (row and row.get('F') is not None) else 0.0
        체력_12점 = F_pit * (12 / 9)

        r_1m = (s_cut.iloc[-1] / s_cut.iloc[-21] - 1) if len(s_cut) >= 22 else None
        far_val, _ = far_trigger(체력_12점, r_1m)
        sloan_s = float(sloan_q.get(name, 0.0))
        noa_s = float(noa_q.get(name, 0.0))
        base = 체력_12점 + info.get('ModF', 0) + far_val + sloan_s   # ModF 정적 잔재

        r_mom12 = compute_mom12(s_cut)
        beta60 = compute_beta60(s_cut, k_cut)
        mom_s = mom12_to_score(r_mom12)
        bab_s = bab_to_score_v371(beta60)
        echo_s = echo_scores.get(name, 0) * ECHO_WEIGHT

        total = base + mom_s + bab_s + noa_s + echo_s
        rows.append({'종목': name, '체력_pit': round(total, 2),
                     '등급_pit': grade(total), 'F_pit': F_pit,
                     'Sloan_pit': sloan_s, 'NOA_pit': noa_s})
    return pd.DataFrame(rows)


# ============================================================
# 백테스트 (static·PIT 동시점 병행)
# ============================================================
def run(panel, inputs_by_code, years=4):
    k = panel.get('_KOSPI')
    end_dt = k.index[-1]
    start_dt = end_dt - pd.DateOffset(years=years)
    bp = k[(k.index >= start_dt) & (k.index <= end_dt)]
    rebal = bp.resample('MS').first().dropna().index
    rebal = [k.index[k.index.get_indexer([d], method='bfill')[0]]
             for d in rebal if d <= end_dt]
    rebal = sorted(set(rebal))
    if rebal[-1] < end_dt:
        rebal.append(end_dt)
    print(f"\n🔁 Rebalance: {len(rebal)-1}회 (static·PIT 동시점)")

    rets = {'static': [], 'pit': [], 'b': []}
    history = []
    for i in range(len(rebal) - 1):
        d0, d1 = rebal[i], rebal[i + 1]
        ss = compute_static_at(panel, d0)
        ps = compute_scores_pit_at(panel, d0, inputs_by_code)
        if ss is None or len(ss) == 0 or len(ps) == 0:
            continue
        picks_s = ss[ss['등급_v37_2'].isin(TARGET)]['종목'].tolist()
        picks_p = ps[ps['등급_pit'].isin(TARGET)]['종목'].tolist()
        r_s = avg_return(picks_s, panel, d0, d1)
        r_p = avg_return(picks_p, panel, d0, d1)
        r_b = kospi_return(panel, d0, d1)
        rets['static'].append(r_s); rets['pit'].append(r_p); rets['b'].append(r_b)
        history.append({'date': pd.Timestamp(d1).strftime('%Y-%m-%d'),
                        'r_static_%': round(r_s * 100, 2), 'r_pit_%': round(r_p * 100, 2),
                        'r_kospi_%': round(r_b * 100, 2),
                        'n_static': len(picks_s), 'n_pit': len(picks_p)})

    m = {k_: metrics(rets[k_]) for k_ in rets}
    ir = {k_: information_ratio(rets[k_], rets['b']) for k_ in ('static', 'pit')}
    gates = evaluate_gates(m, ir)
    print_report(m, ir, gates, history, years)
    return {'metrics': m, 'ir': ir, 'gates': gates, 'history': history}


def evaluate_gates(m, ir):
    cagr_s = m['static'].get('연환산', 0.0)
    cagr_p = m['pit'].get('연환산', 0.0)
    ir_p = ir.get('pit') or 0.0
    delta = cagr_p - cagr_s
    gate_ir = ir_p >= IR_MIN
    gate_cagr = delta >= CAGR_DELTA_MIN
    beats_kospi = cagr_p > m['b'].get('연환산', 0.0)
    return {
        'cagr_static': cagr_s, 'cagr_pit': cagr_p, 'cagr_delta_pp': round(delta, 2),
        'ir_pit': ir_p, 'ir_static': ir.get('static'),
        'gate_IR>=1.0': gate_ir, 'gate_CAGRdelta>=-15pp': gate_cagr,
        'beats_kospi': beats_kospi,
        'PASS': bool(gate_ir and gate_cagr),
        'verdict': ('lookahead 무해 확인' if (gate_ir and gate_cagr)
                    else 'static 과대(lookahead) → production 재검토 플래그'),
    }


def print_report(m, ir, gates, history, years):
    print("\n" + "=" * 86)
    print(f"v3.7.2 진짜 OOS (재무 PIT) — static vs PIT  [{years}년·M·S+/S/A·EW·무비용]")
    print("=" * 86)

    def row(lbl, mm, ir_=None):
        print(f"{lbl:9s} | CAGR {mm.get('연환산',0):>7.2f}%  Sharpe {str(mm.get('Sharpe','-')):>5s}  "
              f"MDD {mm.get('MDD',0):>7.2f}%  IR {str(ir_ if ir_ is not None else '-'):>5s}  "
              f"누적 {mm.get('누적',0):>8.2f}%")
    row("static", m['static'], ir['static'])
    row("PIT", m['pit'], ir['pit'])
    row("KOSPI", m['b'])

    print(f"\nΔ (PIT − static): CAGR {gates['cagr_delta_pp']:+.2f}%p · "
          f"Sharpe {(m['pit'].get('Sharpe') or 0)-(m['static'].get('Sharpe') or 0):+.2f} · "
          f"MDD {m['pit'].get('MDD',0)-m['static'].get('MDD',0):+.2f}%p")

    # 연도별 CAGR delta (history → 연도 그룹)
    if history:
        dfh = pd.DataFrame(history)
        dfh['yr'] = dfh['date'].str[:4]
        print("\n연도별 누적수익 (static / PIT / KOSPI):")
        for yr, g in dfh.groupby('yr'):
            cs = (np.prod(1 + g['r_static_%'] / 100) - 1) * 100
            cp = (np.prod(1 + g['r_pit_%'] / 100) - 1) * 100
            cb = (np.prod(1 + g['r_kospi_%'] / 100) - 1) * 100
            print(f"  {yr}: {cs:>7.1f}% / {cp:>7.1f}% / {cb:>7.1f}%")

    print("\n--- 합격선 (설계메모 §3, 사전등록) ---")
    print(f"  A-1 PIT IR ≥ 1.0          : {'OK' if gates['gate_IR>=1.0'] else 'X'} (IR={gates['ir_pit']})")
    print(f"  A-2 CAGR delta ≥ −15%p    : {'OK' if gates['gate_CAGRdelta>=-15pp'] else 'X'} (Δ={gates['cagr_delta_pp']:+.2f}%p)")
    print(f"  (보조) PIT > KOSPI        : {'OK' if gates['beats_kospi'] else 'X'}")
    print(f"  → {'🟢 PASS — ' if gates['PASS'] else '🔴 FAIL — '}{gates['verdict']}")


# ============================================================
# self-test (합성, 네트워크 불필요)
# ============================================================
def self_test():
    print("\n🧪 Phase3 PIT 백테스트 self-test (합성)")
    checks = []
    # 1. fy_for
    ok = (fy_for('2026-06-01') == 2025 and fy_for('2026-03-01') == 2024)
    checks.append(('fy_for (5월기준 FY−1/−2)', ok, f"{fy_for('2026-06-01')},{fy_for('2026-03-01')}"))

    # 2. 합성 패널 + inputs로 PIT 스코어링 동작
    rng = np.random.default_rng(7)
    idx = pd.date_range('2021-01-01', periods=400, freq='B')
    panel = {'_KOSPI': pd.Series(100 * np.cumprod(1 + rng.normal(0.0003, 0.01, 400)), index=idx)}
    for name in JINWOO_v37:
        panel[name] = pd.Series(100 * np.cumprod(1 + rng.normal(0.0005, 0.02, 400)), index=idx)
    inputs = {}
    for info in JINWOO_v37.values():
        c = str(info['코드']).zfill(6)
        inputs[c] = {fy: {'F': int(rng.integers(0, 10)),
                          'accrual': float(rng.normal(0, 0.05)),
                          'noa_ratio': float(rng.uniform(0.2, 0.8))} for fy in range(2019, 2026)}
    ps = compute_scores_pit_at(panel, idx[-1], inputs)
    ok = (len(ps) > 0 and ps['등급_pit'].notna().all()
          and ps['Sloan_pit'].between(-2, 2).all() and ps['NOA_pit'].between(-2, 2).all())
    checks.append(('PIT 스코어링 (등급·Sloan/NOA∈[-2,2])', ok, f"n={len(ps)}"))

    # 3. _qscore 방향 (낮은 accrual → +)
    q = _qscore(pd.Series({'a': -0.1, 'b': 0.0, 'c': 0.1, 'd': 0.2, 'e': 0.3}), good_low=True)
    ok = (q['a'] > q['e'])
    checks.append(('_qscore good_low (낮을수록 +)', ok, f"a={q['a']},e={q['e']}"))

    # 4. 게이트 로직
    g_pass = evaluate_gates({'static': {'연환산': 72}, 'pit': {'연환산': 60}, 'b': {'연환산': 30}},
                            {'static': 1.5, 'pit': 1.1})
    g_fail = evaluate_gates({'static': {'연환산': 72}, 'pit': {'연환산': 50}, 'b': {'연환산': 30}},
                            {'static': 1.5, 'pit': 0.8})
    ok = (g_pass['PASS'] is True and g_fail['PASS'] is False)
    checks.append(('게이트 (60/IR1.1→PASS, 50/IR0.8→FAIL)', ok, f"{g_pass['PASS']},{g_fail['PASS']}"))

    # 5. 게이트 경계 (delta 정확히 −15 → PASS, −15.1 → FAIL)
    gb1 = evaluate_gates({'static': {'연환산': 72}, 'pit': {'연환산': 57}, 'b': {'연환산': 30}}, {'static': 1.5, 'pit': 1.0})
    gb2 = evaluate_gates({'static': {'연환산': 72}, 'pit': {'연환산': 56.8}, 'b': {'연환산': 30}}, {'static': 1.5, 'pit': 1.0})
    ok = (gb1['PASS'] is True and gb2['PASS'] is False)
    checks.append(('경계 (Δ−15→PASS, −15.2→FAIL)', ok, f"{gb1['cagr_delta_pp']},{gb2['cagr_delta_pp']}"))

    print(f"  {'check':38s} {'결과':4s}  detail")
    allok = True
    for label, ok, det in checks:
        allok &= ok
        print(f"  {label:38s} {'OK' if ok else 'X':4s}  {det}")
    print(f"\n{'self-test 전부 통과' if allok else 'self-test 실패'} ({sum(c[1] for c in checks)}/{len(checks)})")
    return allok


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--years', type=int, default=4)
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()
    if args.self_test:
        sys.exit(0 if self_test() else 1)

    if not INPUTS_CSV.exists():
        sys.exit('❌ score_inputs_univ.csv 없음 (make_score_inputs 먼저)')
    inputs = load_inputs_by_code()
    print(f"📂 score_inputs: {len(inputs)} 종목코드")
    panel = fetch_long_panel(args.years)
    if panel.get('_KOSPI') is None:
        sys.exit('❌ 패널 수집 실패')
    rep = run(panel, inputs, args.years)
    out = BASE / f'backtest_v37_2_pit_{datetime.now():%Y%m%d_%H%M}.json'
    out.write_text(json.dumps({'generated_at': datetime.now().isoformat(timespec='minutes'),
                               **rep}, ensure_ascii=False, indent=2, default=str), encoding='utf-8')
    print(f"\n💾 저장: {out.name}")


if __name__ == '__main__':
    main()
