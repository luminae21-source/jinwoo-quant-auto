#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""진우퀀트 영역 3 확장 모듈 — Stage 3: 공식 엔진 판정 백테스트.

결정메모: 진우퀀트_영역3_확장모듈_결정메모.md (2026-06-05 진우 승인 — §2~§8 변경 금지)

엔진: backtest_v39_pit_pead·v40 컨벤션 1:1 — 월초 리밸(MS→bfill)·마지막 부분구간 포함·
      비용 = Σ|Δw|/2 × cost(시장별 라우팅 §4)·caps·metrics/IR = backtest_v37_2 import.
2층:  멤버십 = 연 1회 5월 PIT 로테이션 (score_univ30.rotations, 검증본 score_at)
      실행 = 월별 PIT-proxy 점수(멤버십 내) → grade cut {S+,S,A} → caps.

동시점 병행 arms (절대값 참조 게이트 금지 — §7):
  bench(KOSPI) / fixed18@0.235%(재현 게이트) / u_base(시장별 비용) /
  u_ref@0.235%(참고 — 판정 미사용) / u_w / u_s (regime, §5 B·§6 시장 라우팅)

합격선 (§5, 변경 금지):
  A. universe 게이트 — 같은 실행 KOSPI 대비: ①CAGR ≥ +3.0%p ②IR ≥ 0.30 ③MDD ≤ KOSPI
  B. regime 게이트 — u_base 대비 (D §2): ①MDD ≥ +2.0%p ②CAGR ≥ −1.0%p ③Sharpe·IR ≥ −0.01

실행 = 진우 PC:  python backtest_univ30.py          (선행: make_score_inputs.py 1회)
사전 검증:        python backtest_univ30.py --selftest  (네트워크 불필요)
"""
import sys, argparse, json
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

BASE = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE))

from score_univ30 import (COST_BY_MARKET, REF_COST, TOP_K,
                          load_inputs, load_monthly, label_maps,
                          rotations, members_for, member_components_at,
                          totals_picks, weights_for, turnover_cost)
from fetch_regime_market_v40 import load_cache_series, market_signals_at
from regime_detector_v40 import (concentration_signal, factor_signal,
                                 composite_score, classify_regime, DEFAULT_WEIGHTS)

# ---------- 사전 등록 합격선 (결정메모 §5 — 변경 금지) ----------
U_PASS_CAGR = 3.0      # A① univ30 base CAGR ≥ KOSPI +3.0%p
U_PASS_IR = 0.30       # A② IR ≥ 0.30
R_PASS_MDD = 2.0       # B① MDD 개선 ≥ +2.0%p (vs u_base)
R_PASS_CAGR = -1.0     # B② CAGR ≥ −1.0%p
R_TOL = 0.01           # B③ Sharpe·IR 허용 오차
VARIANTS = ('w', 's')
MARKETS = ('KOSPI', 'KOSDAQ')

CACHE_KOSPI = BASE / 'regime_market_cache_v40.json'
CACHE_KOSDAQ = BASE / 'regime_market_cache_v40_kosdaq.json'


def _load_production():
    """production·D 모듈 lazy import (전부 read-only — v40 패턴)."""
    from score_v37 import (JINWOO_v37, grade, far_trigger, compute_mom12,
                           compute_beta60, mom12_to_score, noa_to_score)
    from score_v37_1 import bab_to_score
    from score_v37_2 import apply_weight_caps, ECHO_WEIGHT
    from backtest_v37_2 import (fetch_long_panel, compute_scores_at,
                                compute_echo_scores_at, metrics, information_ratio)
    from backtest_v40_regime import components_at
    from score_v40_regime import adjusted_total, TARGET_GRADES
    return dict(JINWOO=JINWOO_v37, grade=grade, caps=apply_weight_caps,
                far=far_trigger, mom12=compute_mom12, beta60=compute_beta60,
                mom2s=mom12_to_score, bab2s=bab_to_score, noa2s=noa_to_score,
                ECHO_W=ECHO_WEIGHT,
                fetch=fetch_long_panel, scores_at=compute_scores_at,
                echo_at=compute_echo_scores_at, metrics=metrics, ir=information_ratio,
                components_at=components_at, adjusted_total=adjusted_total,
                TARGET=TARGET_GRADES)


# ---------- 리밸일 (공식 엔진 동일: MS→bfill + 마지막 부분구간) ----------

def month_starts_daily(idx, years=4):
    end = idx[-1]
    start = end - pd.DateOffset(years=years)
    win = idx[(idx >= start) & (idx <= end)]
    ms = pd.Series(1, index=win).resample('MS').first().dropna().index
    out = sorted({idx[idx.get_indexer([d], method='bfill')[0]] for d in ms if d <= end})
    if out[-1] < end:
        out.append(end)
    return out


def window_return(s, d0, d1):
    if s is None:
        return None
    sw = s[(s.index > d0) & (s.index <= d1)].dropna()
    return float(sw.iloc[-1] / sw.iloc[0] - 1) if len(sw) >= 2 else None


def portfolio_return(w, daily, d0, d1):
    r = 0.0
    for c, wi in w.items():
        ri = window_return(daily.get(c), d0, d1)
        if ri is not None:
            r += wi * ri
    return r


# ---------- regime 상태 (시장 라우팅 §6) ----------

def states_at(d0, var, idx_by_mkt, cache_by_mkt, conc, t_ex, prev, force_states=None,
              date_str=None):
    """시장별 state dict. 시장 3요소만 시장별, concentration·factor 공유 (D 구조)."""
    out = {}
    for mkt in MARKETS:
        if force_states is not None:
            st = (force_states.get((date_str, mkt))
                  or force_states.get(date_str) or 'NEUTRAL')
            prev[var][mkt] = st
            out[mkt] = st
            continue
        idx_s = idx_by_mkt.get(mkt)
        cs = cache_by_mkt.get(mkt)
        if idx_s is None or cs is None:           # 캐시·지수 없음 → KOSPI 상태로 폴백
            out[mkt] = out.get('KOSPI', 'NEUTRAL')
            continue
        vol_s, vol_is_vk, flow_s = cs
        sig = market_signals_at(d0, idx_s, vol_s, vol_is_vk, flow_s)
        sig['concentration'] = conc
        sig['factor'] = factor_signal(t_ex)
        score, _ = composite_score(sig, DEFAULT_WEIGHTS)
        st = classify_regime(score, prev_state=prev[var][mkt])
        prev[var][mkt] = st
        out[mkt] = st
    return out


# ---------- 엔진 ----------

def run(daily, kospi_d, monthly, inputs, idx_by_mkt, cache_by_mkt, P=None,
        prod_panel=None, years=4, check_repro=True, force_states=None, verbose=True,
        top_k=TOP_K):
    """동시점 병행 백테스트.
    daily: {code: 일별 Series} / kospi_d: KOSPI 일별 / monthly: 월말 패널 /
    idx_by_mkt: {'KOSPI': 지수 Series, 'KOSDAQ': KQ11 Series} / cache_by_mkt: load_cache_series 결과.
    P·prod_panel 주어지면 fixed18 arm + 구조 재현 게이트 수행."""
    rebal = month_starts_daily(kospi_d.index, years=years)
    rots = rotations(monthly, inputs, top_k=top_k)
    market_of, sector_of, name_of = label_maps(inputs)

    arms = ['u_base', 'u_ref'] + [f'u_{v}' for v in VARIANTS]
    if prod_panel is not None and P is not None:
        arms = ['fixed18'] + arms
    res = {a: [] for a in arms + ['bench']}
    pw = {a: {} for a in arms}
    turn = {a: 0.0 for a in arms}
    cost_paid = {a: 0.0 for a in arms}
    prev = {v: {m: None for m in MARKETS} for v in VARIANTS}
    n_off = {v: {m: 0 for m in MARKETS} for v in VARIANTS}
    picks_n = {a: [] for a in arms}
    history, repro_checked = [], 0
    sectors18 = ({n: i.get('산업', 'Other') for n, i in P['JINWOO'].items()}
                 if P is not None else {})

    for i in range(len(rebal) - 1):
        d0, d1 = rebal[i], rebal[i + 1]
        date_str = pd.Timestamp(d0).strftime('%Y-%m-%d')
        row = {'date': date_str}

        # --- bench (KOSPI) ---
        rb = window_return(kospi_d, d0, d1)
        res['bench'].append(rb if rb is not None else 0.0)

        # --- fixed18 (공식 그대로 + 구조 게이트 §7) ---
        if 'fixed18' in res:
            snap = P['scores_at'](prod_panel, d0)
            comp18 = P['components_at'](prod_panel, d0, P)
            if check_repro and snap is not None and len(snap):
                for _, r0 in snap.iterrows():
                    n = r0['종목']
                    if n in comp18:
                        my = P['adjusted_total'](comp18[n], 'NEUTRAL', 'w')
                        if abs(round(my, 2) - r0['체력_v37_2']) > 0.011:
                            raise RuntimeError(f"[재현 게이트(구조) 실패] {date_str} {n}: "
                                               f"{my:.2f} ≠ {r0['체력_v37_2']}")
                        repro_checked += 1
            p18 = (snap[snap['등급_v37_2'].isin(P['TARGET'])]['종목'].tolist()
                   if snap is not None and len(snap) else [])
            w18 = P['caps'](p18, sectors18) if p18 else {}
            g = portfolio_return(w18, prod_panel, d0, d1)
            to, c = turnover_cost(w18, pw['fixed18'], {}, flat=REF_COST)
            turn['fixed18'] += to; cost_paid['fixed18'] += c
            pw['fixed18'] = dict(w18)
            res['fixed18'].append(g - c)
            picks_n['fixed18'].append(len(w18))

        # --- universe 멤버십·컴포넌트 (월별 PIT-proxy) ---
        members = members_for(d0, rots)
        comp = member_components_at(d0, members, monthly, inputs)

        # base picks (조정 전 — concentration 입력, 순환 방지 D 동일)
        tot_b, picks_b = totals_picks(comp)
        w_base = weights_for(picks_b, sector_of)
        conc = concentration_signal(picks_b, sector_of)

        gross_base = portfolio_return(w_base, daily, d0, d1)
        # u_base: 시장별 비용 / u_ref: 동일 포트, 0.235% 참고
        to_b, c_b = turnover_cost(w_base, pw['u_base'], market_of)
        _, c_r = turnover_cost(w_base, pw['u_ref'], market_of, flat=REF_COST)
        turn['u_base'] += to_b; turn['u_ref'] += to_b
        cost_paid['u_base'] += c_b; cost_paid['u_ref'] += c_r
        pw['u_base'] = dict(w_base); pw['u_ref'] = dict(w_base)
        res['u_base'].append(gross_base - c_b)
        res['u_ref'].append(gross_base - c_r)
        picks_n['u_base'].append(len(w_base)); picks_n['u_ref'].append(len(w_base))
        row['picks_u'] = len(w_base)
        row['kosdaq_n'] = sum(1 for c in w_base if market_of.get(c) == 'KOSDAQ')

        # --- regime 변형 (시장 라우팅) ---
        for v in VARIANTS:
            arm = f'u_{v}'
            if len(res[arm]) >= 3:
                t_ex = float(np.sum(np.array(res[arm][-3:]) - np.array(res['bench'][-4:-1])))
            else:
                t_ex = None
            sts = states_at(d0, v, idx_by_mkt, cache_by_mkt, conc, t_ex, prev,
                            force_states=force_states, date_str=date_str)
            for m in MARKETS:
                if sts.get(m) == 'RISK_OFF':
                    n_off[v][m] += 1
            row[f'state_{v}_KOSPI'] = sts.get('KOSPI')
            row[f'state_{v}_KOSDAQ'] = sts.get('KOSDAQ')
            tot_v, picks_v = totals_picks(
                comp, state_of=lambda c: sts.get(market_of.get(c, 'KOSPI'), 'NEUTRAL'),
                variant=v)
            w_v = weights_for(picks_v, sector_of)
            g_v = portfolio_return(w_v, daily, d0, d1)
            to_v, c_v = turnover_cost(w_v, pw[arm], market_of)
            turn[arm] += to_v; cost_paid[arm] += c_v
            pw[arm] = dict(w_v)
            res[arm].append(g_v - c_v)
            picks_n[arm].append(len(w_v))

        for a in arms:
            row[f'r_{a}_%'] = round(res[a][-1] * 100, 2)
        row['r_bench_%'] = round(res['bench'][-1] * 100, 2)
        history.append(row)

    rot_log = {str(k.date()): v for k, v in rots.items()}
    return dict(res=res, turn=turn, cost=cost_paid, n_off=n_off, picks_n=picks_n,
                history=history, repro_checked=repro_checked, rotations=rot_log,
                market_of=market_of, name_of=name_of)


# ---------- 판정 (§5 — 변경 금지) ----------

def universe_verdict(m_base, ir_base, m_bench):
    d_cagr = (m_base.get('연환산', 0) or 0) - (m_bench.get('연환산', 0) or 0)
    mdd_ok = (m_base.get('MDD', -99) or -99) >= (m_bench.get('MDD', 0) or 0)
    ok = (d_cagr >= U_PASS_CAGR) and ((ir_base or 0) >= U_PASS_IR) and mdd_ok
    return ok, round(d_cagr, 2), mdd_ok


def regime_verdict(m_base, ir_base, m_v, ir_v):
    d_cagr = (m_v.get('연환산', 0) or 0) - (m_base.get('연환산', 0) or 0)
    d_mdd = (m_v.get('MDD', 0) or 0) - (m_base.get('MDD', 0) or 0)
    ok = (d_mdd >= R_PASS_MDD and d_cagr >= R_PASS_CAGR
          and (m_v.get('Sharpe') or 0) >= (m_base.get('Sharpe') or 0) - R_TOL
          and (ir_v or 0) >= (ir_base or 0) - R_TOL)
    return ok, round(d_cagr, 2), round(d_mdd, 2)


def report(out, P, json_path=None, extra_meta=None):
    res = out['res']
    m = {a: P['metrics'](res[a]) for a in res}
    ir = {a: P['ir'](res[a], res['bench']) for a in res if a != 'bench'}

    if 'fixed18' in res:
        print(f"  [재현 게이트(구조)] fixed18 컴포넌트 일치 {out['repro_checked']}건 통과 "
              f"(절대값 참조 게이트 없음 — 결정메모 §7)")
    print(f"\n  {'arm':10s} {'CAGR%':>8} {'Sharpe':>7} {'MDD%':>8} {'IR':>6} "
          f"{'턴오버':>7} {'비용%':>6} {'평균picks':>9}")
    for a in [x for x in ('fixed18', 'u_base', 'u_ref', 'u_w', 'u_s') if x in res]:
        mm = m[a]
        pk = np.mean(out['picks_n'][a]) if out['picks_n'][a] else 0
        print(f"  {a:10s} {mm.get('연환산', 0):>8.2f} {str(mm.get('Sharpe')):>7} "
              f"{mm.get('MDD', 0):>8.2f} {str(ir.get(a)):>6} {out['turn'][a]:>7.2f} "
              f"{out['cost'][a] * 100:>6.2f} {pk:>9.1f}")
    print(f"  {'KOSPI':10s} {m['bench'].get('연환산', 0):>8.2f} "
          f"{str(m['bench'].get('Sharpe')):>7} {m['bench'].get('MDD', 0):>8.2f}")

    # A. universe 게이트
    ok_u, d_cagr_u, mdd_ok = universe_verdict(m['u_base'], ir['u_base'], m['bench'])
    print(f"\n[판정 A — universe 게이트 §5A] u_base vs KOSPI (같은 실행):")
    print(f"  ① ΔCAGR {d_cagr_u:+.2f}%p (≥ +{U_PASS_CAGR}) "
          f"② IR {ir['u_base']} (≥ {U_PASS_IR}) ③ MDD 비악화 {'✓' if mdd_ok else '✗'} "
          f"→ {'✅ PASS' if ok_u else '❌ FAIL'}")

    # B. regime 게이트 (vs u_base)
    print(f"[판정 B — regime 게이트 §5B] vs u_base (D §2 재사용):")
    verd = {}
    for v in VARIANTS:
        ok, dc, dm = regime_verdict(m['u_base'], ir['u_base'], m[f'u_{v}'], ir[f'u_{v}'])
        verd[v] = (ok, dc, dm)
        off = out['n_off'][v]
        print(f"  u_{v}: ΔCAGR {dc:+.2f}%p · ΔMDD {dm:+.2f}%p · Sharpe "
              f"{m[f'u_{v}'].get('Sharpe')} vs {m['u_base'].get('Sharpe')} · IR {ir[f'u_{v}']} "
              f"vs {ir['u_base']} · RISK_OFF K{off['KOSPI']}/Q{off['KOSDAQ']}개월 "
              f"→ {'✅ PASS' if ok else '❌ FAIL'}")

    if ok_u and any(v[0] for v in verd.values()):
        print("\n→ A PASS + regime PASS 변형 존재: C 패턴 병행 관찰 모드 검토 (production 무변경).")
    elif ok_u:
        print("\n→ A PASS / regime 전 변형 FAIL: universe 관찰 트랙 채택 검토, regime 종결 (재튜닝 금지).")
    else:
        print("\n→ A FAIL: 사전 등록대로 모듈 종결 — 룰 universe는 분기 재스크린 정보 트랙으로만 유지, "
              "재시험·재튜닝 금지. (regime 산출은 기록용)")

    payload = {
        'run_at': datetime.now().isoformat(),
        'engine': 'backtest_v39_pit_pead convention + market-routed cost/regime',
        'memo': '진우퀀트_영역3_확장모듈_결정메모.md (2026-06-05 승인)',
        'pass_rule': {
            'A_universe': f'dCAGR>=+{U_PASS_CAGR}%p AND IR>={U_PASS_IR} AND MDD<=KOSPI',
            'B_regime': f'dMDD>=+{R_PASS_MDD}%p AND dCAGR>={R_PASS_CAGR}%p AND Sharpe/IR>=base-{R_TOL}',
        },
        'cost': {'KOSPI': COST_BY_MARKET['KOSPI'], 'KOSDAQ': COST_BY_MARKET['KOSDAQ'],
                 'ref': REF_COST},
        'metrics': {a: {**m[a], 'IR': ir.get(a)} for a in m if a != 'bench'},
        'bench': m['bench'],
        'turnover': {a: round(t, 3) for a, t in out['turn'].items()},
        'cost_paid_%': {a: round(c * 100, 3) for a, c in out['cost'].items()},
        'avg_picks': {a: round(float(np.mean(p)), 1) for a, p in out['picks_n'].items() if p},
        'risk_off_months': out['n_off'],
        'repro_structural_checks': out['repro_checked'],
        'verdict_A_universe': {'pass': bool(ok_u), 'd_cagr_%p': d_cagr_u, 'mdd_ok': bool(mdd_ok)},
        'verdict_B_regime': {v: {'pass': verd[v][0], 'd_cagr_%p': verd[v][1],
                                 'd_mdd_%p': verd[v][2]} for v in VARIANTS},
        'rotations': out['rotations'],
        'history': out['history'],
    }
    if extra_meta:
        payload['meta'] = extra_meta
    if json_path:
        Path(json_path).write_text(json.dumps(payload, ensure_ascii=False, indent=1),
                                   encoding='utf-8')
        print(f"\n  💾 {Path(json_path).name} 저장 — Claude에 공유해 주세요.")
    return payload


# ---------- 실데이터 main (PC) ----------

def _fetch_daily_codes(codes, years=4):
    import FinanceDataReader as fdr
    from datetime import timedelta
    end = datetime.now()
    start = end - timedelta(days=int(365 * (years + 0.2)))
    out = {}
    for i, c in enumerate(codes):
        try:
            s = fdr.DataReader(c, start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))['Close'].dropna()
            if len(s) >= 30:
                out[c] = s
        except Exception as e:
            print(f"    ({c} 실패: {e})")
        if (i + 1) % 25 == 0:
            print(f"    ...{i + 1}/{len(codes)}")
    return out


def main():
    print("=" * 72)
    print("영역 3 확장 모듈 — 공식 엔진 판정 (결정메모 2026-06-05 승인본)")
    print("=" * 72)
    P = _load_production()
    inputs = load_inputs()
    monthly = load_monthly()

    if not CACHE_KOSPI.exists():
        print('[중단] regime_market_cache_v40.json 없음 → python fetch_regime_market_v40.py 먼저.')
        sys.exit(1)
    cache_by_mkt = {'KOSPI': load_cache_series(json.loads(CACHE_KOSPI.read_text(encoding='utf-8')))}
    if CACHE_KOSDAQ.exists():
        cache_by_mkt['KOSDAQ'] = load_cache_series(json.loads(CACHE_KOSDAQ.read_text(encoding='utf-8')))
        print("  [0] regime 캐시: KOSPI + KOSDAQ (시장 라우팅 §6)")
    else:
        cache_by_mkt['KOSDAQ'] = None
        print("  [0] ⚠️ KOSDAQ 캐시 없음 → KOSDAQ 종목은 KOSPI 상태 폴백 (fetch_regime_kosdaq_v40.py 권장)")

    rots = rotations(monthly, inputs, verbose=True)
    union = sorted({c for mem in rots.values() for c in mem})
    print(f"  [1] 로테이션 {len(rots)}회 · 멤버 합집합 {len(union)}종목 — FDR 일별 수집 (수 분)")

    prod_panel = P['fetch'](years=4)                      # 18종 + _KOSPI (공식)
    kospi_d = prod_panel['_KOSPI']
    daily = _fetch_daily_codes(union)
    import FinanceDataReader as fdr
    from datetime import timedelta
    end = datetime.now(); start = end - timedelta(days=int(365 * 4.2))
    kq_d = fdr.DataReader('KQ11', start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))['Close'].dropna()
    idx_by_mkt = {'KOSPI': kospi_d, 'KOSDAQ': kq_d}
    print(f"  [2] 수집 완료: 멤버 {len(daily)}/{len(union)} · KQ11 {len(kq_d)}일 — 백테스트 시작")

    out = run(daily, kospi_d, monthly, inputs, idx_by_mkt, cache_by_mkt,
              P=P, prod_panel=prod_panel)
    ts = datetime.now().strftime('%Y%m%d_%H%M')
    report(out, P, json_path=BASE / f'backtest_univ30_{ts}.json',
           extra_meta={'members_fetched': len(daily), 'union': len(union)})


# ---------- self-test (synthetic — 네트워크 불필요) ----------

def _selftest():
    ok = 0
    rng = np.random.default_rng(11)
    bdays = pd.bdate_range('2022-01-03', periods=1120)

    # 합성 일별: production 18 + _KOSPI + 멤버 8종(4 KOSPI/4 KOSDAQ) + KQ11
    P = _load_production()
    names18 = list(P['JINWOO'].keys())
    prod_panel = {n: pd.Series(100 * np.cumprod(1 + rng.normal(0.0006, 0.012, len(bdays))),
                               index=bdays) for n in names18}
    kospi_d = pd.Series(100 * np.cumprod(1 + rng.normal(0.0004, 0.009, len(bdays))), index=bdays)
    prod_panel['_KOSPI'] = kospi_d
    codes = [f'10000{i}' for i in range(4)] + [f'20000{i}' for i in range(4)]
    drift = {c: 0.0015 if c == '100000' else (-0.0012 if c == '200003' else 0.0004) for c in codes}
    daily = {c: pd.Series(100 * np.cumprod(1 + drift[c] + rng.normal(0, 0.010, len(bdays))),
                          index=bdays) for c in codes}
    kq_d = pd.Series(100 * np.cumprod(1 + rng.normal(0.0002, 0.011, len(bdays))), index=bdays)
    monthly = pd.DataFrame({c: s.resample('ME').last() for c, s in daily.items()}).dropna(how='all')

    inputs = pd.DataFrame([
        dict(code=c, fiscal_year=y,
             F=(9 if c == '100000' else (2 if c == '200003' else 7)),
             accrual=(-0.1 if c == '100000' else 0.02) + 0.001 * i,
             noa_ratio=(0.3 if c == '100000' else 0.8) + 0.001 * i,
             market=('KOSPI' if c.startswith('1') else 'KOSDAQ'),
             sector=('A' if c in ('100000', '100001') else ''), name=c)
        for i, c in enumerate(codes) for y in range(2020, 2026)
    ])

    from fetch_regime_market_v40 import realized_vol
    def mk_cache(s):
        rv = realized_vol(s)
        return load_cache_series({'_meta': {'vol_is_vkospi': False},
                                  'vol_series': {pd.Timestamp(k).strftime('%Y-%m-%d'): float(v)
                                                 for k, v in rv.items()},
                                  'flow_cum20': None})
    cache_by_mkt = {'KOSPI': mk_cache(kospi_d), 'KOSDAQ': mk_cache(kq_d)}
    idx_by_mkt = {'KOSPI': kospi_d, 'KOSDAQ': kq_d}

    # (1) 전체 실행 — fixed18 구조 게이트 포함
    out = run(daily, kospi_d, monthly, inputs, idx_by_mkt, cache_by_mkt,
              P=P, prod_panel=prod_panel, years=4, verbose=False, top_k=5)
    res = out['res']
    L = len(res['bench'])
    assert L >= 36 and all(len(res[a]) == L for a in res), '구간 수 불일치'; ok += 1
    assert out['repro_checked'] > 100, f"구조 게이트 검사 수 {out['repro_checked']}"; ok += 1
    assert len(out['rotations']) >= 3; ok += 1

    # (2) u_ref(0.235%) ≥ u_base(라우팅 0.35/0.60%) 누적 — 같은 포트, 비용만 차이
    cum = lambda a: float(np.prod(1 + np.array(res[a])))
    assert cum('u_ref') >= cum('u_base') - 1e-12, 'flat 0.235%가 라우팅보다 불리할 수 없음'; ok += 1
    assert out['cost']['u_base'] > out['cost']['u_ref'] > 0, '비용 라우팅 방향'; ok += 1

    # (3) 시장 라우팅 강제: KOSDAQ만 RISK_OFF → 변형 s에서 KOSDAQ 종목만 조정
    d_force = out['history'][6]['date']
    fs = {(d_force, 'KOSDAQ'): 'RISK_OFF'}
    out2 = run(daily, kospi_d, monthly, inputs, idx_by_mkt, cache_by_mkt,
               P=None, prod_panel=None, years=4, force_states=fs, verbose=False, top_k=5)
    h2 = next(h for h in out2['history'] if h['date'] == d_force)
    assert h2['state_s_KOSDAQ'] == 'RISK_OFF' and h2['state_s_KOSPI'] == 'NEUTRAL', h2; ok += 1
    assert out2['n_off']['s']['KOSDAQ'] >= 1; ok += 1
    # 직접 검증: 그 달 comp에서 KOSPI 종목 total 불변·KOSDAQ 종목만 변형 (score_univ30 단위검증과 일관)
    d0f = pd.Timestamp(d_force)
    rots2 = rotations(monthly, inputs, top_k=5)
    mem = members_for(d0f, rots2)
    comp = member_components_at(d0f, mem, monthly, inputs)
    if comp:
        t_n, _ = totals_picks(comp)
        t_s, _ = totals_picks(comp, state_of=lambda c: 'RISK_OFF' if c.startswith('2') else 'NEUTRAL',
                              variant='s')
        for c in comp:
            if c.startswith('1'):
                assert abs(t_n[c] - t_s[c]) < 1e-9, 'KOSPI 종목이 변형됨'
        ok += 1

    # (4) 판정 로직 단위검증 (크래프트 지표)
    mA = {'연환산': 20.0, 'MDD': -15.0, 'Sharpe': 1.0}
    mB = {'연환산': 16.0, 'MDD': -16.0, 'Sharpe': 0.9}
    okA, dc, mok = universe_verdict(mA, 0.35, mB)
    assert okA and dc == 4.0 and mok; ok += 1
    okA2, *_ = universe_verdict({'연환산': 18.0, 'MDD': -20.0, 'Sharpe': 1.0}, 0.35, mB)
    assert not okA2, 'MDD 악화인데 PASS'; ok += 1
    okR, *_ = regime_verdict(mA, 0.5, {'연환산': 19.5, 'MDD': -12.5, 'Sharpe': 1.0}, 0.5)
    assert okR; ok += 1
    okR2, *_ = regime_verdict(mA, 0.5, {'연환산': 18.0, 'MDD': -12.5, 'Sharpe': 1.0}, 0.5)
    assert not okR2, 'CAGR −2%p인데 PASS'; ok += 1

    # (5) 턴오버 컨벤션 Σ|Δw|/2 (첫 진입 = 0.5)
    assert out['turn']['u_base'] >= 0.5 - 1e-9; ok += 1

    # (6) bench·KOSPI MDD 산출 가능 + metrics 키 호환
    m = P['metrics'](res['bench'])
    assert {'연환산', 'MDD', 'Sharpe'} <= set(m.keys()); ok += 1

    print(f"[OK] backtest_univ30 self-test 통과 ({ok} checks)")
    print(f"     {L}개월 · 로테이션 {len(out['rotations'])}회 · 구조게이트 {out['repro_checked']}건 "
          f"· u_base 비용 {out['cost']['u_base'] * 100:.2f}% > u_ref {out['cost']['u_ref'] * 100:.2f}%")
    print("     실데이터 판정은 진우 PC에서: python backtest_univ30.py")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--selftest', action='store_true')
    a, _ = ap.parse_known_args()
    try:
        _selftest() if a.selftest else main()
    except Exception:
        import traceback
        print("\n===== [에러] 아래 내용을 그대로 복사해 붙여주세요 =====")
        traceback.print_exc()
# ===EOF_SENTINEL===
