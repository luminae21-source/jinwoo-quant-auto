#!/usr/bin/env python3
"""
진우퀀트 v3.7.2 백테스트: v3.6 vs v3.7.1 vs v3.7.2

목적: Echo 단독 추가 (v3.7.1 위에) 효과 측정

가설: GP·AG가 PIT에서도 alpha 손실인 반면 Echo는 깨끗한 양의 신호
       → v3.7.1 + Echo가 가장 합리적 production 후보

학술 근거:
  - S3 Novy-Marx 2012 Echo (t-12~t-7)
  - S6 장지원 2017 한국 검증
  - 우리 6-way 결과: Echo +1.32%p (단일 시점 GP·AG 위에서)
  - PIT 6-way 결과: Echo -0.55%p (시간 가변 GP·AG 위에서) → 충돌
  - 가설: v3.7.1 단독 + Echo는 깨끗한 시너지
"""

import sys
import argparse
import json
from datetime import datetime, timedelta
from pathlib import Path

import pandas as pd
import numpy as np

BASE = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE))

from score_v37 import (
    JINWOO_v37, KOSPI_CODE,
    compute_mom12, compute_beta60,
    mom12_to_score, noa_to_score,
    far_trigger, grade,
)
from score_v37_1 import bab_to_score as bab_to_score_v371
from score_v37_2 import ECHO_WEIGHT


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--years', type=int, default=4)
    p.add_argument('--top-grades', type=str, default='S+,S,A')
    return p.parse_args()


def fetch_long_panel(years=4):
    try:
        import FinanceDataReader as fdr
    except ImportError:
        import subprocess
        subprocess.check_call([sys.executable, '-m', 'pip', 'install',
                               '-q', 'finance-datareader'])
        import FinanceDataReader as fdr
    end = datetime.now()
    start = end - timedelta(days=int(365 * (years + 1.2)))
    panel = {}
    print(f"\n📊 데이터 수집 ({start.date()} → {end.date()}):")
    df = fdr.DataReader(KOSPI_CODE, start.strftime('%Y-%m-%d'),
                        end.strftime('%Y-%m-%d'))
    panel['_KOSPI'] = df['Close']
    for name, info in JINWOO_v37.items():
        try:
            df = fdr.DataReader(info['코드'], start.strftime('%Y-%m-%d'),
                                end.strftime('%Y-%m-%d'))
            panel[name] = df['Close']
        except Exception:
            panel[name] = None
    print(f"  KOSPI + 18종목 OK")
    return panel


def compute_echo_at(s_cut, days_per_month=21):
    if s_cut is None or len(s_cut) < 13 * days_per_month:
        return None
    p_t12 = s_cut.iloc[-12 * days_per_month]
    p_t7 = s_cut.iloc[-7 * days_per_month]
    if p_t12 == 0:
        return None
    return float(p_t7 / p_t12 - 1)


def compute_echo_scores_at(panel, dt):
    echo_values = {}
    for name in JINWOO_v37:
        s = panel.get(name)
        if s is None: continue
        s_cut = s[s.index <= dt]
        v = compute_echo_at(s_cut)
        if v is not None:
            echo_values[name] = v
    if not echo_values:
        return {n: 0 for n in JINWOO_v37}

    n = len(echo_values)
    upper_n = max(1, round(n * 0.2))
    lower_n = max(1, round(n * 0.2))
    sorted_desc = pd.Series(echo_values).sort_values(ascending=False)
    upper = sorted_desc.iloc[upper_n - 1]
    lower = sorted_desc.iloc[-lower_n]
    scores = {}
    for name in JINWOO_v37:
        v = echo_values.get(name)
        if v is None: scores[name] = 0
        elif v >= upper: scores[name] = +1
        elif v <= lower: scores[name] = -1
        else: scores[name] = 0
    return scores


def compute_scores_at(panel, dt):
    kospi = panel.get('_KOSPI')
    echo_scores = compute_echo_scores_at(panel, dt)
    rows = []
    for name, info in JINWOO_v37.items():
        s = panel.get(name)
        if s is None or len(s) == 0: continue
        s_cut = s[s.index <= dt]
        k_cut = kospi[kospi.index <= dt]
        if len(s_cut) < 253: continue

        체력_12점 = info['F_korean'] * (12 / 9.001)
        if len(s_cut) >= 22:
            r_1m = s_cut.iloc[-1] / s_cut.iloc[-21] - 1
        else:
            r_1m = None
        far_val, _ = far_trigger(체력_12점, r_1m)
        base = 체력_12점 + info['ModF'] + far_val + info['Sloan']

        r_mom12 = compute_mom12(s_cut)
        beta60 = compute_beta60(s_cut, k_cut)
        mom_s = mom12_to_score(r_mom12)
        bab_s = bab_to_score_v371(beta60)
        noa_s = noa_to_score(info.get('NOA', 0))

        echo_s = echo_scores.get(name, 0) * ECHO_WEIGHT

        total_v36 = base
        total_v371 = base + mom_s + bab_s + noa_s
        total_v372 = total_v371 + echo_s

        rows.append({
            '종목': name, 'Echo': echo_s,
            '체력_v36': round(total_v36, 2),
            '체력_v37_1': round(total_v371, 2),
            '체력_v37_2': round(total_v372, 2),
            '등급_v36': grade(total_v36),
            '등급_v37_1': grade(total_v371),
            '등급_v37_2': grade(total_v372),
        })
    return pd.DataFrame(rows)


def avg_return(picks, panel, dt_start, dt_end):
    if len(picks) == 0: return 0.0
    rets = []
    for name in picks:
        s = panel.get(name)
        if s is None: continue
        sw = s[(s.index > dt_start) & (s.index <= dt_end)]
        if len(sw) < 2: continue
        rets.append(float(sw.iloc[-1] / sw.iloc[0] - 1))
    return float(np.mean(rets)) if rets else 0.0


def kospi_return(panel, dt_start, dt_end):
    k = panel.get('_KOSPI')
    kw = k[(k.index > dt_start) & (k.index <= dt_end)]
    if len(kw) < 2: return 0.0
    return float(kw.iloc[-1] / kw.iloc[0] - 1)


def metrics(rets, ppy=12):
    arr = np.array(rets)
    if len(arr) == 0: return {}
    cum = float(np.prod(1 + arr) - 1)
    ann = (1 + cum) ** (ppy / len(arr)) - 1
    vol = float(arr.std() * np.sqrt(ppy))
    sharpe = float(ann / vol) if vol > 0 else None
    cc = np.cumprod(1 + arr)
    peak = np.maximum.accumulate(cc)
    return {
        '누적': round(cum * 100, 2), '연환산': round(ann * 100, 2),
        '변동성': round(vol * 100, 2),
        'Sharpe': round(sharpe, 2) if sharpe else None,
        'MDD': round(float(((cc - peak) / peak).min()) * 100, 2),
        '승률': round(float((arr > 0).mean()) * 100, 1),
        '기간': len(arr),
    }


def information_ratio(p, b, ppy=12):
    p, b = np.array(p), np.array(b)
    e = p - b
    if len(e) < 2: return None
    te = e.std() * np.sqrt(ppy)
    if te == 0: return None
    return round(float(e.mean() * ppy / te), 2)


def run_backtest(panel, args):
    target = set(args.top_grades.split(','))
    k = panel.get('_KOSPI')
    end_dt = k.index[-1]
    start_dt = end_dt - pd.DateOffset(years=args.years)
    bp = k[(k.index >= start_dt) & (k.index <= end_dt)]
    rebal = bp.resample('MS').first().dropna().index
    rebal = [k.index[k.index.get_indexer([d], method='bfill')[0]]
             for d in rebal if d <= end_dt]
    rebal = sorted(set(rebal))
    if rebal[-1] < end_dt: rebal.append(end_dt)

    print(f"\n🔁 Rebalance: {len(rebal)-1}회")
    rets = {k_: [] for k_ in ['36', '371', '372', 'b']}

    for i in range(len(rebal) - 1):
        d0, d1 = rebal[i], rebal[i + 1]
        snap = compute_scores_at(panel, d0)
        if snap is None or len(snap) == 0: continue

        for vid, col in [('36', '등급_v36'), ('371', '등급_v37_1'),
                          ('372', '등급_v37_2')]:
            picks = snap[snap[col].isin(target)]['종목'].tolist()
            rets[vid].append(avg_return(picks, panel, d0, d1))
        rets['b'].append(kospi_return(panel, d0, d1))

    m = {k_: metrics(rets[k_]) for k_ in rets}
    ir = {k_: information_ratio(rets[k_], rets['b']) for k_ in rets if k_ != 'b'}

    print("\n" + "=" * 90)
    print(f"v3.7.2 백테스트  ({args.years}년 · M · {args.top_grades} · Echo×{ECHO_WEIGHT})")
    print("=" * 90)

    def row(label, m_, ir_=None):
        print(f"{label:10s} | 누적 {m_.get('누적',0):>7.2f}%  연환산 {m_.get('연환산',0):>6.2f}%  "
              f"vol {m_.get('변동성',0):>5.2f}%  Sharpe {str(m_.get('Sharpe','-')):>5s}  "
              f"MDD {m_.get('MDD',0):>6.2f}%  IR {str(ir_ if ir_ else '-'):>5s}  "
              f"승률 {m_.get('승률',0):>5.1f}%")

    row("v3.6", m['36'], ir['36'])
    row("v3.7.1", m['371'], ir['371'])
    row("v3.7.2", m['372'], ir['372'])
    row("KOSPI", m['b'])

    print(f"\n연환산 alpha:")
    print(f"  v3.7.1 vs v3.6: {m['371'].get('연환산',0) - m['36'].get('연환산',0):+.2f}%p")
    print(f"  v3.7.2 vs v3.6: {m['372'].get('연환산',0) - m['36'].get('연환산',0):+.2f}%p ⭐")
    print(f"  v3.7.2 vs v3.7.1 (Echo 단독 효과): {m['372'].get('연환산',0) - m['371'].get('연환산',0):+.2f}%p ⭐")

    report = {
        'timestamp': datetime.now().isoformat(),
        'metrics': m, 'ir': ir,
        'echo_weight': ECHO_WEIGHT,
    }
    out = BASE / f'backtest_v37_2_{datetime.now().strftime("%Y%m%d_%H%M")}.json'
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2, default=str),
                   encoding='utf-8')
    print(f"\n💾 리포트: {out}")
    return report


def main():
    args = parse_args()
    print("=" * 90)
    print(f"진우퀀트 v3.7.2 백테스트 (v3.7.1 + Echo 단독)")
    print(f"시간: {datetime.now()}")
    print("=" * 90)
    panel = fetch_long_panel(args.years)
    if panel.get('_KOSPI') is None: sys.exit(1)
    run_backtest(panel, args)


if __name__ == '__main__':
    main()
