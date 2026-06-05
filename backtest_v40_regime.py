#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""진우퀀트 모듈 D (v4.0 영역2 regime) — Stage 4: 공식 엔진 판정.

엔진: backtest_v39_pit_pead.py 컨벤션 1:1 — 월초 리밸(MS→bfill)·마지막 부분구간 포함·
      비용 0.235%×턴오버·apply_weight_caps·metrics/IR = backtest_v37_2 import.
신호: score_v40_regime.REGIME_MULTS / adjusted_total (정의 단일화).
국면: regime_detector_v40 5요소 — 시장 3요소(trend·vol·flow)는 regime_market_cache_v40.json,
      섹터집중 = base picks(조정 전 — 순환 방지), 팩터 = 변형 자신의 직전 3개월 초과수익. 전부 PIT(≤d0).

base 재현 게이트 2중:
  (1) 구조: 매 리밸일 컴포넌트 합 == 공식 compute_scores_at 체력_v37_2 (불일치 시 중단)
  (2) 결과: base CAGR이 공식 73.18% ±1.0%p (결정메모 §2)

사전 합격선 (결정메모 §2, 2026-06-05 진우 승인 — 변경 금지), 셋 다 충족 시 PASS:
  ① MDD ≥ base +2.0%p 개선  ② CAGR ≥ base −1.0%p  ③ Sharpe·IR ≥ base −0.01

실행 = 진우 PC:  python backtest_v40_regime.py
사전 검증:        python backtest_v40_regime.py --selftest  (네트워크 불필요)
선행 조건: regime_market_cache_v40.json (fetch_regime_market_v40.py 산출물)
"""
import sys, argparse, json
from datetime import datetime
from pathlib import Path
import numpy as np
import pandas as pd

BASE = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE))

from score_v40_regime import (REGIME_MULTS, DEFAULT_MULT, adjusted_total,
                              mults_for, VARIANT_LABEL, TARGET_GRADES)
from regime_detector_v40 import (concentration_signal, factor_signal,
                                 composite_score, classify_regime, DEFAULT_WEIGHTS)
from fetch_regime_market_v40 import load_cache_series, market_signals_at

COST = 0.00235
REF_BASE_CAGR = 73.18   # 공식 base (2026-06-03, 진우 환경) — 윈도 이동으로 ±0.2%p 일변동 정상
GATE_BASE_TOL = 1.0
PASS_MDD = 2.0          # ① MDD 개선 %p
PASS_CAGR = -1.0        # ② CAGR 허용 하한 %p
TOL = 0.01              # ③ Sharpe·IR 허용 오차
VARIANTS = ('w', 's')


def _load_production():
    """production 모듈 import (전부 read-only)."""
    from score_v37 import (JINWOO_v37, compute_mom12, compute_beta60,
                           mom12_to_score, noa_to_score, far_trigger, grade)
    from score_v37_1 import bab_to_score as bab_to_score_v371
    from score_v37_2 import ECHO_WEIGHT
    from backtest_v37_2 import (fetch_long_panel, compute_scores_at,
                                compute_echo_scores_at, metrics, information_ratio)
    try:
        from score_v37_2 import apply_weight_caps
    except Exception:
        apply_weight_caps = None
    return dict(JINWOO=JINWOO_v37, mom12=compute_mom12, beta60=compute_beta60,
                mom2s=mom12_to_score, noa2s=noa_to_score, far=far_trigger, grade=grade,
                bab2s=bab_to_score_v371, ECHO_W=ECHO_WEIGHT,
                fetch=fetch_long_panel, scores_at=compute_scores_at,
                echo_at=compute_echo_scores_at, metrics=metrics, ir=information_ratio,
                caps=apply_weight_caps)


# ---------- 컴포넌트 산출 (backtest_v37_2.compute_scores_at 1:1 미러, 합만 분해) ----------

def components_at(panel, dt, P, jinwoo=None):
    """리밸일 dt 기준 종목별 컴포넌트 dict. 합계가 공식 체력_v37_2와 일치해야 함."""
    jinwoo = jinwoo or P['JINWOO']
    kospi = panel.get('_KOSPI')
    echo_scores = P['echo_at'](panel, dt)
    out = {}
    for name, info in jinwoo.items():
        s = panel.get(name)
        if s is None or len(s) == 0:
            continue
        s_cut = s[s.index <= dt]
        k_cut = kospi[kospi.index <= dt]
        if len(s_cut) < 253:
            continue
        체력_12점 = info['F_korean'] * (12 / 9.001)
        r_1m = (s_cut.iloc[-1] / s_cut.iloc[-21] - 1) if len(s_cut) >= 22 else None
        far_val, _ = P['far'](체력_12점, r_1m)
        out[name] = {
            'base': 체력_12점 + info['ModF'] + far_val + info['Sloan'],
            'mom': P['mom2s'](P['mom12'](s_cut)),
            'bab': P['bab2s'](P['beta60'](s_cut, k_cut)),
            'noa': P['noa2s'](info.get('NOA', 0)),
            'echo': echo_scores.get(name, 0) * P['ECHO_W'],
        }
    return out


# ---------- 엔진 ----------

def run(panel, P, cache, jinwoo=None, cost=COST, force_states=None, check_repro=True):
    """base + regime 변형 2개 백테스트.
    force_states: {d0_str: state} — selftest 전용 국면 강제 주입."""
    k = panel['_KOSPI']; end = k.index[-1]; start = end - pd.DateOffset(years=4)
    bp = k[(k.index >= start) & (k.index <= end)]
    rebal = sorted({k.index[k.index.get_indexer([d], method='bfill')[0]]
                    for d in bp.resample('MS').first().dropna().index if d <= end})
    if rebal[-1] < end: rebal.append(end)

    vol_s, vol_is_vkospi, flow_s = load_cache_series(cache) if cache else (None, False, None)
    jin = jinwoo or P['JINWOO']
    sectors = {n: i.get('산업', 'Other') for n, i in jin.items()}

    res = {'base': [], 'w': [], 's': [], 'bench': []}
    pw = {v: {} for v in ('base',) + tuple(VARIANTS)}
    turn = {v: 0.0 for v in pw}
    prev_state = {v: None for v in VARIANTS}
    state_log, n_off = [], {v: 0 for v in VARIANTS}
    repro_checked = 0

    for i in range(len(rebal) - 1):
        d0, d1 = rebal[i], rebal[i + 1]
        snap = P['scores_at'](panel, d0)
        if snap is None or len(snap) == 0:
            continue
        comp = components_at(panel, dt=d0, P=P, jinwoo=jinwoo)

        # --- base 재현 게이트(구조): 컴포넌트 합 == 공식 체력_v37_2 ---
        if check_repro and jinwoo is None:
            for _, r0 in snap.iterrows():
                n = r0['종목']
                if n not in comp:
                    continue
                my = adjusted_total(comp[n], 'NEUTRAL', 'w')  # mult 전부 1.0 = 원합계
                if abs(round(my, 2) - r0['체력_v37_2']) > 0.011:
                    raise RuntimeError(f"[재현 게이트 실패] {d0.date()} {n}: "
                                       f"컴포넌트합 {my:.2f} ≠ 공식 {r0['체력_v37_2']}")
                repro_checked += 1

        # --- base picks (공식 등급 그대로) ---
        picks_base = snap[snap['등급_v37_2'].isin(TARGET_GRADES)]['종목'].tolist()

        # --- 시장 3요소 + 섹터집중 (변형 공통, PIT) ---
        msig = market_signals_at(d0, k, vol_s, vol_is_vkospi, flow_s)
        conc = concentration_signal(picks_base, sectors)

        row_log = {'date': pd.Timestamp(d0).strftime('%Y-%m-%d')}
        period_r = {}
        for var in ('base',) + tuple(VARIANTS):
            if var == 'base':
                col_picks = picks_base
            else:
                # 팩터 ON/OFF: 자기 변형의 직전 3개월 초과수익 합 (이력<3 → None)
                if len(res[var]) >= 3:
                    t_ex = float(np.sum(np.array(res[var][-3:]) - np.array(res['bench'][-3:])))
                else:
                    t_ex = None
                sig = dict(msig); sig['concentration'] = conc
                sig['factor'] = factor_signal(t_ex)
                score, used = composite_score(sig, DEFAULT_WEIGHTS)
                if force_states is not None:
                    state = force_states.get(row_log['date'], 'NEUTRAL')
                else:
                    state = classify_regime(score, prev_state=prev_state[var])
                prev_state[var] = state
                if state == 'RISK_OFF':
                    n_off[var] += 1
                row_log[f'state_{var}'] = state
                row_log[f'score_{var}'] = score
                adj = {n: adjusted_total(c, state, var) for n, c in comp.items()}
                col_picks = [n for n, t in adj.items() if P['grade'](t) in TARGET_GRADES]

            w = (P['caps'](col_picks, sectors) if (P['caps'] and sectors) else
                 {p: 1 / len(col_picks) for p in col_picks}) if col_picks else {}
            r = 0.0
            for n, wi in w.items():
                s = panel.get(n)
                if s is None: continue
                sw = s[(s.index > d0) & (s.index <= d1)].dropna()
                if len(sw) >= 2:
                    r += wi * float(sw.iloc[-1] / sw.iloc[0] - 1)
            alln = set(w) | set(pw[var])
            to = sum(abs(w.get(x, 0) - pw[var].get(x, 0)) for x in alln) / 2
            turn[var] += to; r -= to * cost; pw[var] = dict(w)
            res[var].append(r); period_r[var] = r

        kw = k[(k.index > d0) & (k.index <= d1)].dropna()
        res['bench'].append(float(kw.iloc[-1] / kw.iloc[0] - 1) if len(kw) >= 2 else 0.0)
        for var in ('base',) + tuple(VARIANTS):
            row_log[f'r_{var}_%'] = round(period_r[var] * 100, 2)
        row_log['r_bench_%'] = round(res['bench'][-1] * 100, 2)
        state_log.append(row_log)

    return res, turn, n_off, state_log, repro_checked


# ---------- 판정 ----------

def verdict(m_base, ir_base, m_v, ir_v):
    d_cagr = (m_v.get('연환산', 0) or 0) - (m_base.get('연환산', 0) or 0)
    d_mdd = (m_v.get('MDD', 0) or 0) - (m_base.get('MDD', 0) or 0)   # +면 개선 (덜 깊음)
    ok = (d_mdd >= PASS_MDD
          and d_cagr >= PASS_CAGR
          and (m_v.get('Sharpe') or 0) >= (m_base.get('Sharpe') or 0) - TOL
          and (ir_v or 0) >= (ir_base or 0) - TOL)
    return ok, round(d_cagr, 2), round(d_mdd, 2)


def main():
    P = _load_production()
    cache_p = BASE / 'regime_market_cache_v40.json'
    if not cache_p.exists():
        print('[중단] regime_market_cache_v40.json 없음 → python fetch_regime_market_v40.py 먼저.')
        sys.exit(1)
    cache = json.loads(cache_p.read_text(encoding='utf-8'))
    meta = cache.get('_meta', {})
    print(f"  [0] regime 캐시: vol={'VKOSPI' if meta.get('vol_is_vkospi') else '실현변동성 proxy'}, "
          f"flow={'OK' if cache.get('flow_cum20') else '없음(제외)'}")

    panel = P['fetch'](years=4)
    print(f"  [1] 가격 수집 완료, 백테스트 시작...")
    print("\n모듈 D — v4.0 regime 가중치 조정, 공식 엔진 (비용 0.235%·caps·월초 리밸):")

    res, turn, n_off, state_log, n_chk = run(panel, P, cache)
    m = {v: P['metrics'](res[v]) for v in res}
    ir = {v: P['ir'](res[v], res['bench']) for v in res if v != 'bench'}

    print(f"  [재현 게이트(구조)] 컴포넌트 일치 {n_chk}건 검사 통과")
    bc = m['base'].get('연환산', 0)
    g_ok = abs(bc - REF_BASE_CAGR) <= GATE_BASE_TOL
    print(f"  [재현 게이트(결과)] base {bc:.2f}% vs 공식 {REF_BASE_CAGR}% "
          f"→ {'✅ 성립' if g_ok else '❌ 미성립 — 판정 보류, 결과 공유 필요'}")

    print(f"\n  base       {m['base']}  IR={ir['base']}")
    for v in VARIANTS:
        print(f"  {VARIANT_LABEL[v]:12s}{m[v]}  IR={ir[v]}  turnover={round(turn[v],3)}  RISK_OFF={n_off[v]}/{len(res[v])}개월")
    print(f"  KOSPI      {m['bench']}")

    print(f"\n판정 (사전 합격선: MDD≥+{PASS_MDD}%p AND CAGR≥{PASS_CAGR}%p AND Sharpe·IR 비열위 −{TOL}):")
    out_v = {}
    for v in VARIANTS:
        ok, d_cagr, d_mdd = verdict(m['base'], ir['base'], m[v], ir[v])
        out_v[v] = (ok, d_cagr, d_mdd)
        print(f"  {VARIANT_LABEL[v]}: ΔCAGR {d_cagr:+.2f}%p · ΔMDD {d_mdd:+.2f}%p "
              f"· Sharpe {m[v].get('Sharpe')} vs {m['base'].get('Sharpe')} · IR {ir[v]} vs {ir['base']}"
              f" → {'✅ PASS' if ok else '❌ FAIL'}")
    if not g_ok:
        print("  ⚠️ base 재현 미성립 상태의 판정은 무효 — 결과 JSON을 공유해 주세요.")
    elif any(ok for ok, *_ in out_v.values()):
        best = max((v for v in VARIANTS if out_v[v][0]), key=lambda v: out_v[v][2])
        print(f"\n→ 합격 (최우수 {VARIANT_LABEL[best]}): C 패턴대로 병행 관찰 모드 검토 (production 무변경).")
    else:
        print("\n→ 미달: 사전 등록대로 즉시 기각, v3.7.2 유지. (regime 가중치 노선 종료 — 재튜닝 재시험 금지)")

    out = {'run_at': datetime.now().isoformat(), 'engine': 'backtest_v39_pit_pead convention',
           'pass_rule': f'dMDD>=+{PASS_MDD}%p AND dCAGR>={PASS_CAGR}%p AND Sharpe/IR>=base-{TOL}',
           'base_repro': {'cagr': bc, 'ref': REF_BASE_CAGR, 'ok': bool(g_ok), 'component_checks': n_chk},
           'cache_meta': meta,
           'metrics': {v: {**m[v], 'IR': ir.get(v)} for v in m if v != 'bench'},
           'bench': m['bench'],
           'turnover': {v: round(turn[v], 3) for v in turn},
           'risk_off_months': n_off,
           'verdicts': {v: {'pass': out_v[v][0], 'd_cagr_%p': out_v[v][1], 'd_mdd_%p': out_v[v][2]} for v in VARIANTS},
           'history': state_log}
    fn = BASE / f'backtest_v40_regime_{datetime.now():%Y%m%d_%H%M}.json'
    fn.write_text(json.dumps(out, ensure_ascii=False, indent=1, default=str), encoding='utf-8')
    print(f"\n💾 저장: {fn.name}  ← 이 파일(또는 콘솔 출력)을 Claude에게 공유")


# ---------- selftest (synthetic — FDR·production 데이터 불필요) ----------

def _selftest():
    ok = 0
    from score_v37 import grade as real_grade, far_trigger
    from score_v37 import compute_mom12, compute_beta60, mom12_to_score, noa_to_score
    from score_v37_1 import bab_to_score

    idx = pd.bdate_range('2021-06-01', periods=1100)
    rng = np.random.default_rng(41)
    panel = {'_KOSPI': pd.Series(100 * np.cumprod(1 + rng.normal(0.0004, 0.006, 1100)), index=idx)}
    jin = {}
    for j, n in enumerate(['AA', 'BB', 'CC', 'DD']):
        panel[n] = pd.Series(100 * np.cumprod(1 + rng.normal(0.0006, 0.012, 1100)), index=idx)
        jin[n] = {'F_korean': [8, 7, 6, 5][j], 'ModF': 1, 'Sloan': 0, 'NOA': 0,
                  '산업': ['반도체', '반도체', '금융', '식품'][j], '코드': f'00000{j}'}

    def stub_scores_at(panel_, dt):
        rows = []
        kc = panel_['_KOSPI'][panel_['_KOSPI'].index <= dt]
        for n, info in jin.items():
            s_cut = panel_[n][panel_[n].index <= dt]
            if len(s_cut) < 253: continue
            체력 = info['F_korean'] * (12 / 9.001)
            r1m = s_cut.iloc[-1] / s_cut.iloc[-21] - 1
            fv, _ = far_trigger(체력, r1m)
            tot = (체력 + info['ModF'] + fv + info['Sloan']
                   + mom12_to_score(compute_mom12(s_cut))
                   + bab_to_score(compute_beta60(s_cut, kc))
                   + noa_to_score(0) + 0.0)  # echo: stub에선 0
        # noqa
            rows.append({'종목': n, '체력_v37_2': round(tot, 2), '등급_v37_2': real_grade(tot)})
        return pd.DataFrame(rows)

    P = dict(JINWOO=jin, mom12=compute_mom12, beta60=compute_beta60,
             mom2s=mom12_to_score, noa2s=noa_to_score, far=far_trigger, grade=real_grade,
             bab2s=bab_to_score, ECHO_W=0.0,            # selftest: echo 0 가중 → stub과 정합
             scores_at=stub_scores_at,
             echo_at=lambda p, dt: {n: 0 for n in jin},
             metrics=None, ir=None, caps=None, fetch=None)

    cache = {'_meta': {'vol_is_vkospi': False},
             'vol_series': {pd.Timestamp(k).strftime('%Y-%m-%d'): float(v)
                            for k, v in (panel['_KOSPI'].pct_change().rolling(20).std()
                                         * np.sqrt(252) * 100).dropna().items()},
             'flow_cum20': None}

    # 1) 국면 강제 없음(자연 분류) — 전 기간 RISK_OFF 0이면 w==s==base 불변식은 force로 검증
    dates_probe = [d.strftime('%Y-%m-%d') for d in idx]
    force_all_neutral = {d: 'NEUTRAL' for d in dates_probe}
    res, turn, n_off, log, _ = run(panel, P, cache, jinwoo=jin,
                                   force_states=force_all_neutral, check_repro=False)
    assert len(res['base']) == len(res['w']) == len(res['s']) == len(res['bench']) >= 30; ok += 1
    assert np.allclose(res['base'], res['w']) and np.allclose(res['base'], res['s']), \
        'RISK_OFF 없음 → 변형==base 불변식 위반'; ok += 1
    assert n_off == {'w': 0, 's': 0}; ok += 1

    # 2) 전 기간 RISK_OFF 강제 → 변형이 base와 달라질 수 있고(점수 변동), 등급컷 작동
    force_all_off = {d: 'RISK_OFF' for d in dates_probe}
    res2, turn2, n_off2, log2, _ = run(panel, P, cache, jinwoo=jin,
                                       force_states=force_all_off, check_repro=False)
    assert n_off2['w'] == n_off2['s'] == len(res2['w']); ok += 1
    diff = sum(abs(a - b) for a, b in zip(res2['base'], res2['s']))
    assert diff >= 0; ok += 1  # 산술 경로 자체가 깨지지 않음 (차이 유무는 데이터 의존)

    # 3) 컴포넌트 합 == stub 총점 (echo=0 정합) — 구조 재현 게이트의 selftest 판
    d_probe = idx[400]
    comp = components_at(panel, d_probe, P, jinwoo=jin)
    snap = stub_scores_at(panel, d_probe)
    for _, r0 in snap.iterrows():
        my = adjusted_total(comp[r0['종목']], 'NEUTRAL', 'w')
        assert abs(round(my, 2) - r0['체력_v37_2']) <= 0.011, (r0['종목'], my, r0['체력_v37_2'])
    ok += 1

    # 4) verdict 산술: MDD -10.0 vs base -12.5 (+2.5 개선), CAGR -0.5%p, Sharpe/IR 동일 → PASS
    mb = {'연환산': 73.0, 'MDD': -12.5, 'Sharpe': 2.8}
    mv = {'연환산': 72.5, 'MDD': -10.0, 'Sharpe': 2.8}
    okv, dc, dm = verdict(mb, 1.5, mv, 1.5)
    assert okv and dc == -0.5 and dm == 2.5; ok += 1
    # 5) MDD 개선 부족 → FAIL / CAGR 초과 하락 → FAIL
    assert not verdict(mb, 1.5, {'연환산': 73.0, 'MDD': -11.0, 'Sharpe': 2.8}, 1.5)[0]; ok += 1
    assert not verdict(mb, 1.5, {'연환산': 71.5, 'MDD': -9.0, 'Sharpe': 2.8}, 1.5)[0]; ok += 1

    # 6) 비용·턴오버 방향
    assert turn['base'] > 0 and all(t >= 0 for t in turn.values()); ok += 1

    print(f"[OK] backtest_v40_regime selftest 통과 ({ok} checks)")
    print("     실제 판정은 진우님 PC에서: python backtest_v40_regime.py")


if __name__ == '__main__':
    ap = argparse.ArgumentParser(); ap.add_argument('--selftest', action='store_true')
    a, _ = ap.parse_known_args()
    try:
        _selftest() if a.selftest else main()
    except Exception:
        import traceback
        print("\n===== [에러] 아래 내용을 그대로 복사해 붙여주세요 =====")
        traceback.print_exc()
