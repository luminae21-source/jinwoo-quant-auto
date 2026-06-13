#!/usr/bin/env python3
"""
진우퀀트 v4.0 — 영역 4 Phase 2: 2-factor 분해 (시장 + 산업/섹터)

목적 (부분C 결정메모 §2):
  Phase1(단일팩터 CAPM)은 시총가중 KOSPI가 반도체 대형주 쏠림으로 부풀면
  비반도체 종목의 약세를 '종목 고유(idio)'로 오인 → T2 false signal.
  Phase2는 종목별 섹터 ETF를 2번째 factor로 추가해
  '시장+산업 동조'와 '진짜 종목약세'를 분리한다.

모델:
  r_sector_orth = r_sector - β_SM·r_market           (섹터수익을 시장에 직교화)
  r_i,t = α + β_M·r_market,t + β_S·r_sector_orth,t + ε_i,t
  → market_contrib = β_M,{t-1}·r_market,t
  → sector_contrib = β_S,{t-1}·r_sector_orth,t        (시장 초과 섹터 증분)
  → idio           = r_i - market_contrib - sector_contrib
  분해 항등식: r_i = market_contrib + sector_contrib + idio  (정의상 오차 0)

직교화의 효과: r_market ⊥ r_sector_orth → 결합회귀 계수가 단변량과 분리되어
  β_M ≈ Phase1의 β_M (시장기여 동일) + sector_contrib만 신규.
  따라서 idio_phase2 = idio_phase1 - sector_contrib.

합격선 (결정메모 §2-3, 변경금지):
  A. 착시 재분류: 오늘 false-T2 후보 10종(한미 제외) 중 ≥30% T2 해제
  B. 진성약세 보존: 한미반도체 T2 유지 (섹터 빼고도 idio ≤ -10%)
  C. 분해 건전성: 항등식 오차 0 + 반도체주 β_S>0

실행:
  python3 attribution_v40_phase2.py --beta-win 120 --save-json --save-html
  python3 attribution_v40_phase2.py --self-test      # 네트워크 불필요, 합성 self-test
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path

import numpy as np
import pandas as pd

# Phase1 재사용 (데이터층·rolling_beta·trigger). 모듈 로드시 score_v37 import는
# Phase1 내부에서 처리됨. self-test는 순수함수만 쓰므로 네트워크 불필요.
from attribution_v40_phase1 import (
    rolling_beta,
    evaluate_triggers,
    REPLACEMENT_RULES_V0,
)

BASE = Path(__file__).parent.resolve()

# ============================================
# 섹터 매핑 (결정메모 §2-4, 2026-06-07 데이터 가용성 확인 완료)
# ============================================
SECTOR_OF = {
    '삼성전자': '091160', 'SK하이닉스': '091160', '한미반도체': '091160', 'ISC': '091160',
    '삼성SDI': '305720',
    '알테오젠': '244580',
    '기아': '091180',
    'NAVER': '157490', '카카오': '157490',
    '한화에어로': '449450', 'LIG넥스원': '449450',
    'KB금융': '091170',
    'NH투자증권': '102970',
    '두산에너빌리티': '434730',
    # 2026-06-13 추가 (4 ETF-less 보완): 화장품·필수소비재
    '아모레퍼시픽': '228790',   # TIGER 화장품
    'KT&G': '266410',           # KODEX 필수소비재
    '삼양식품': '266410',        # KODEX 필수소비재 (음식료 포함 — 전용 음식료 ETF 부재)
    # 섹터 ETF 부재 → 시장 factor만 (β_S=0): 삼성물산(종합상사/holding co, idio 성격)
}
SECTOR_NAME = {
    '091160': '반도체', '305720': '2차전지', '244580': '바이오', '091180': '자동차',
    '157490': '인터넷', '091170': '은행', '102970': '증권',
    '449450': 'K방산', '434730': '원자력',
    '228790': '화장품', '266410': '필수소비재',
}


# ============================================
# 인자
# ============================================
def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--days', type=int, default=20,
                   help='최근 N 영업일 attribution 출력 (기본 20)')
    p.add_argument('--beta-win', type=int, default=120,
                   help='β 추정 rolling window 영업일 (기본 120, Phase2 권장)')
    p.add_argument('--fetch-days', type=int, default=750,
                   help='FDR로 가져올 캘린더 일수 (기본 750 ≈ 2년). '
                        '직교화 2팩터는 워밍업 이중(섹터직교 W + β_S W)이라 '
                        '120d window면 ~240거래일 소진 → 충분한 trigger 윈도 위해 길게')
    p.add_argument('--save-html', action='store_true')
    p.add_argument('--save-json', action='store_true', default=True)
    p.add_argument('--z-threshold', type=float, default=3.0)
    p.add_argument('--self-test', action='store_true',
                   help='합성데이터 self-test (네트워크 불필요)')
    return p.parse_args()


# ============================================
# 데이터 수집 (섹터 ETF)
# ============================================
def fetch_sector_returns(days: int, codes: list[str]) -> pd.DataFrame:
    """섹터 ETF 코드들의 일별 로그 수익률. columns = ETF 코드."""
    from attribution_v40_phase1 import _ensure_fdr  # lazy (self-test시 미호출)
    fdr = _ensure_fdr()
    end = datetime.now()
    start = end - timedelta(days=days)
    print(f"\n📊 섹터 ETF 패널 수집 ({start:%Y-%m-%d} → {end:%Y-%m-%d})")
    prices: dict[str, pd.Series] = {}
    for code in sorted(set(codes)):
        try:
            df = fdr.DataReader(code, start.strftime('%Y-%m-%d'), end.strftime('%Y-%m-%d'))
            if len(df) > 60:
                prices[code] = df['Close']
                print(f"  {code} {SECTOR_NAME.get(code, '?'):8s} {len(df)} 영업일")
            else:
                print(f"  {code} {SECTOR_NAME.get(code, '?'):8s} 데이터 부족 ({len(df)}) — 시장factor만")
        except Exception as e:
            print(f"  {code} {SECTOR_NAME.get(code, '?'):8s} 실패: {e} — 시장factor만")
    px = pd.DataFrame(prices).sort_index()
    rets = np.log(px / px.shift(1)).dropna(how='all')
    return rets


# ============================================
# Phase 2 — 2-factor 분해
# ============================================
def orthogonalize(sector_ret: pd.Series,
                  market_ret: pd.Series,
                  window: int) -> pd.Series:
    """섹터수익을 시장에 직교화: r_sector_orth = r_sector - β_SM,{t-1}·r_market.
    β_SM은 섹터의 시장 베타(rolling, 1일 lag)."""
    beta_sm = rolling_beta(sector_ret, market_ret, window).shift(1)
    aligned = pd.concat([sector_ret, market_ret, beta_sm], axis=1, join='inner').dropna()
    aligned.columns = ['s', 'm', 'b']
    orth = aligned['s'] - aligned['b'] * aligned['m']
    return orth.reindex(sector_ret.index)


def decompose_two_factor(stock_ret: pd.Series,
                         market_ret: pd.Series,
                         sector_orth: pd.Series | None,
                         window: int) -> pd.DataFrame:
    """2-factor 분해. sector_orth=None이면 Phase1과 동일(β_S=0)."""
    beta_m = rolling_beta(stock_ret, market_ret, window).shift(1)

    cols = {'r_stock': stock_ret, 'r_market': market_ret, 'beta': beta_m}
    if sector_orth is not None:
        beta_s = rolling_beta(stock_ret, sector_orth, window).shift(1)
        cols['r_sector_orth'] = sector_orth
        cols['beta_s'] = beta_s
    aligned = pd.DataFrame(cols).dropna()

    aligned['market_contrib'] = aligned['beta'] * aligned['r_market']
    if sector_orth is not None:
        aligned['sector_contrib'] = aligned['beta_s'] * aligned['r_sector_orth']
    else:
        aligned['sector_contrib'] = 0.0
        aligned['beta_s'] = 0.0
    # idio = 잔차 (정의상 항등식 보존)
    aligned['idio'] = (aligned['r_stock']
                       - aligned['market_contrib']
                       - aligned['sector_contrib'])
    mu = aligned['idio'].rolling(window).mean()
    sd = aligned['idio'].rolling(window).std()
    aligned['idio_z'] = (aligned['idio'] - mu) / sd.replace(0, np.nan)
    return aligned


def decompose_all_phase2(returns: pd.DataFrame,
                         sector_rets: pd.DataFrame,
                         window: int) -> dict[str, pd.DataFrame]:
    """전 종목 2-factor 분해. 섹터 ETF 없거나 데이터 부족 종목은 시장factor만."""
    market = returns['_KOSPI']
    out = {}
    for name in returns.columns:
        if name == '_KOSPI':
            continue
        s = returns[name].dropna()
        if len(s) < window + 5:
            print(f"  ⚠️ {name}: 데이터 부족, skip")
            continue
        code = SECTOR_OF.get(name)
        sector_orth = None
        if code is not None and code in sector_rets.columns:
            sec = sector_rets[code].dropna()
            if len(sec) >= window + 5:
                sector_orth = orthogonalize(sec, market, window)
        out[name] = decompose_two_factor(s, market, sector_orth, window)
    return out


# ============================================
# 합격선 자동 판정 (결정메모 §2-3)
# ============================================
HANMI = '한미반도체'


def _t2_names(triggers: list[dict]) -> set[str]:
    return {t['name'] for t in triggers
            if any(x['code'] == 'T2' for x in t['triggers'])}


def evaluate_gates(decomp_p1: dict[str, pd.DataFrame],
                   decomp_p2: dict[str, pd.DataFrame],
                   lookback_days: int,
                   z_threshold: float) -> dict:
    """Phase1 vs Phase2 트리거 비교 → 게이트 A/B/C 판정."""
    trig_p1 = evaluate_triggers(decomp_p1, lookback_days, z_threshold)
    trig_p2 = evaluate_triggers(decomp_p2, lookback_days, z_threshold)
    t2_p1 = _t2_names(trig_p1)
    t2_p2 = _t2_names(trig_p2)

    # 데이터 충분성 가드: evaluate_triggers는 행<lookback+5 종목을 skip한다.
    # skip된 종목이 '재분류'로 오집계되면 판정이 무효 → 명시적으로 차단.
    MIN_ROWS = lookback_days + 5
    judged = sorted(t2_p1)   # P1 T2 발동 전 종목 (한미 포함)
    insufficient = [n for n in judged
                    if (n not in decomp_p2) or (len(decomp_p2[n]) < MIN_ROWS)]

    false_candidates = sorted(t2_p1 - {HANMI})   # 한미 제외 false-T2 후보
    reclassified = sorted(n for n in false_candidates if n not in t2_p2)
    n_cand = len(false_candidates)
    rate = (len(reclassified) / n_cand) if n_cand else 0.0

    # 게이트 A: 착시 재분류 ≥30%
    gate_a = (rate >= 0.30)
    # 게이트 B: 한미 T2 보존
    gate_b = (HANMI in t2_p1) and (HANMI in t2_p2)
    # 게이트 C: 분해 항등식 오차 0 (전 종목 max abs error)
    max_err = 0.0
    for name, df in decomp_p2.items():
        err = (df['r_stock'] - df['market_contrib']
               - df['sector_contrib'] - df['idio']).abs().max()
        max_err = max(max_err, float(err) if pd.notna(err) else 0.0)
    gate_c_identity = (max_err < 1e-9)
    # 반도체주 β_S 부호 (sanity)
    semis = ['삼성전자', 'SK하이닉스', '한미반도체', 'ISC']
    beta_s_semi = {}
    for n in semis:
        if n in decomp_p2 and 'beta_s' in decomp_p2[n]:
            bs = decomp_p2[n]['beta_s'].dropna()
            if len(bs):
                beta_s_semi[n] = round(float(bs.iloc[-1]), 2)
    gate_c = gate_c_identity and (sum(v > 0 for v in beta_s_semi.values()) >= 2)

    # 재분류 종목별 sector_contrib 20d (사후해석 보조기록)
    detail = {}
    for n in false_candidates:
        df2 = decomp_p2.get(n)
        if df2 is None:
            continue
        sc = df2['sector_contrib'].tail(lookback_days).sum() * 100
        idio2 = df2['idio'].tail(lookback_days).sum() * 100
        idio1 = decomp_p1[n]['idio'].tail(lookback_days).sum() * 100 if n in decomp_p1 else None
        detail[n] = {
            'cum_idio_p1_%': round(idio1, 2) if idio1 is not None else None,
            'cum_sector_contrib_%': round(float(sc), 2),
            'cum_idio_p2_%': round(float(idio2), 2),
            't2_cleared': n in reclassified,
        }

    valid = (len(insufficient) == 0)
    return {
        'valid': valid,
        'insufficient_data': insufficient,
        'min_rows_required': MIN_ROWS,
        't2_phase1': sorted(t2_p1),
        't2_phase2': sorted(t2_p2),
        'false_candidates': false_candidates,
        'reclassified': reclassified,
        'reclassify_rate': round(rate, 3),
        'gate_A_reclass>=30%': gate_a,
        'gate_B_hanmi_preserved': gate_b,
        'gate_C_identity+betaS': gate_c,
        'identity_max_err': max_err,
        'beta_s_semi': beta_s_semi,
        'PASS': bool(valid and gate_a and gate_b and gate_c),
        'detail': detail,
    }


# ============================================
# self-test (합성데이터, 네트워크 불필요)
# ============================================
def self_test() -> bool:
    print("\n🧪 Phase2 self-test (합성데이터)")
    rng = np.random.default_rng(42)
    n = 400
    idx = pd.date_range('2024-01-01', periods=n, freq='B')
    win = 120
    checks = []

    # 공통 factor
    r_market = pd.Series(rng.normal(0.0003, 0.010, n), index=idx)
    sector_excess = pd.Series(rng.normal(0.0, 0.008, n), index=idx)   # 시장초과 섹터
    r_sector = 1.1 * r_market + sector_excess                          # 섹터 = 시장 + 초과

    # --- 1. 분해 항등식 오차 0 ---
    sec_orth = orthogonalize(r_sector, r_market, win)
    stock = 1.0 * r_market + 1.5 * sec_orth + pd.Series(rng.normal(0, 0.004, n), index=idx)
    d = decompose_two_factor(stock, r_market, sec_orth, win)
    err = (d['r_stock'] - d['market_contrib'] - d['sector_contrib'] - d['idio']).abs().max()
    ok = err < 1e-12
    checks.append(('분해 항등식 오차 0', ok, f'max_err={err:.2e}'))

    # --- 2. β_S 추정 (true 1.5) ---
    bs = d['beta_s'].dropna().iloc[-1]
    ok = 1.2 < bs < 1.8
    checks.append(('β_S 추정 ≈1.5', ok, f'β_S={bs:.2f}'))

    # --- 3. β_M 추정 (true 1.0, 직교화로 분리) ---
    bm = d['beta'].dropna().iloc[-1]
    ok = 0.7 < bm < 1.3
    checks.append(('β_M 추정 ≈1.0', ok, f'β_M={bm:.2f}'))

    # --- 4. 착시 재분류: 시장↑·섹터↓·진짜idio≈0 → P1 T2발동, P2 해제 ---
    # 최근 20일: 시장 +, 섹터초과 - (섹터 약세), 종목은 섹터 따라감(고유 ~0)
    m2 = r_market.copy(); m2.iloc[-20:] = 0.004                       # 시장 강세
    se2 = sector_excess.copy(); se2.iloc[-20:] = -0.010              # 섹터 약세
    sec2 = 1.1 * m2 + se2
    so2 = orthogonalize(sec2, m2, win)
    stock2 = 1.0 * m2 + 1.5 * so2 + pd.Series(rng.normal(0, 0.002, n), index=idx)
    d2_p2 = decompose_two_factor(stock2, m2, so2, win)
    d2_p1 = decompose_two_factor(stock2, m2, None, win)               # Phase1 동치
    t2_p1 = _t2_names(evaluate_triggers({'X': d2_p1}, 20, 3.0))
    t2_p2 = _t2_names(evaluate_triggers({'X': d2_p2}, 20, 3.0))
    ci_p1 = d2_p1['idio'].tail(20).sum() * 100
    ci_p2 = d2_p2['idio'].tail(20).sum() * 100
    ok = ('X' in t2_p1) and ('X' not in t2_p2)
    checks.append(('착시: P1 T2발동→P2 해제', ok, f'idio P1={ci_p1:.1f}% P2={ci_p2:.1f}%'))

    # --- 5. 진성약세 보존: 시장↑·섹터flat·진짜idio=-15% → P1·P2 둘다 T2 ---
    m3 = r_market.copy(); m3.iloc[-20:] = 0.004
    se3 = sector_excess.copy(); se3.iloc[-20:] = 0.0                 # 섹터 중립
    sec3 = 1.1 * m3 + se3
    so3 = orthogonalize(sec3, m3, win)
    idio_true = pd.Series(0.0, index=idx); idio_true.iloc[-20:] = -0.0085   # ≈ -17%
    stock3 = 1.0 * m3 + 1.5 * so3 + idio_true
    d3_p2 = decompose_two_factor(stock3, m3, so3, win)
    d3_p1 = decompose_two_factor(stock3, m3, None, win)
    t2_p1b = _t2_names(evaluate_triggers({'X': d3_p1}, 20, 3.0))
    t2_p2b = _t2_names(evaluate_triggers({'X': d3_p2}, 20, 3.0))
    ok = ('X' in t2_p1b) and ('X' in t2_p2b)
    checks.append(('진성약세: P1·P2 둘다 T2', ok,
                   f'idio P1={d3_p1["idio"].tail(20).sum()*100:.1f}% '
                   f'P2={d3_p2["idio"].tail(20).sum()*100:.1f}%'))

    # --- 6. 섹터 없는 종목 fallback = Phase1 동일 ---
    dN = decompose_two_factor(stock, r_market, None, win)
    ok = (dN['sector_contrib'].abs().max() == 0.0)
    checks.append(('섹터 없으면 β_S=0 fallback', ok, 'sector_contrib≡0'))

    print(f"  {'check':38s} {'결과':4s}  detail")
    allok = True
    for name, ok, detail in checks:
        allok &= ok
        print(f"  {name:38s} {'✅' if ok else '❌':4s}  {detail}")
    print(f"\n{'✅ self-test 전부 통과' if allok else '❌ self-test 실패'} ({sum(c[1] for c in checks)}/{len(checks)})")
    return allok


# ============================================
# 출력 / 저장
# ============================================
def print_summary(decomp_p2, gates, beta_win):
    print("\n" + "=" * 78)
    print("진우퀀트 v4.0 영역4 — Phase 2 (시장+섹터 2-factor) 분해 결과")
    print(f"분석 시점: {datetime.now():%Y-%m-%d %H:%M} / β window {beta_win}d")
    print("=" * 78)
    if not gates.get('valid', True):
        print(f"\n⛔ 판정 무효 — 데이터 부족 종목 {len(gates['insufficient_data'])}개 "
              f"(P2 유효행 < {gates['min_rows_required']}): {gates['insufficient_data']}")
        print("   → --fetch-days를 더 크게 주고 재실행 (직교화 2팩터 워밍업 이중).")
        print("   아래 수치는 참고용일 뿐 게이트 판정에 쓰지 말 것.\n")
    print(f"\nT2 (Phase1 단일팩터): {gates['t2_phase1']}")
    print(f"T2 (Phase2 2-factor): {gates['t2_phase2']}")
    print(f"\nfalse-T2 후보(한미 제외) {len(gates['false_candidates'])}종: {gates['false_candidates']}")
    print(f"→ 재분류(T2 해제) {len(gates['reclassified'])}종: {gates['reclassified']}")
    print(f"→ 재분류율 {gates['reclassify_rate']*100:.0f}%")
    print(f"\n종목별 분해 (cum 20d):")
    print(f"  {'종목':<14}{'idio_P1':>9}{'sector_c':>10}{'idio_P2':>9}  {'T2해제':>6}")
    for n, dd in gates['detail'].items():
        print(f"  {n:<14}{dd['cum_idio_p1_%']:>8.1f}%{dd['cum_sector_contrib_%']:>9.1f}%"
              f"{dd['cum_idio_p2_%']:>8.1f}%  {'✅' if dd['t2_cleared'] else '—':>6}")
    print(f"\n반도체주 β_S: {gates['beta_s_semi']}")
    print("\n--- 게이트 판정 (결정메모 §2-3) ---")
    print(f"  A. 착시 재분류 ≥30%     : {'✅ PASS' if gates['gate_A_reclass>=30%'] else '❌ FAIL'} ({gates['reclassify_rate']*100:.0f}%)")
    print(f"  B. 한미 진성약세 보존    : {'✅ PASS' if gates['gate_B_hanmi_preserved'] else '❌ FAIL'}")
    print(f"  C. 분해건전성+β_S부호    : {'✅ PASS' if gates['gate_C_identity+betaS'] else '❌ FAIL'} (id_err={gates['identity_max_err']:.1e})")
    if not gates.get('valid', True):
        print(f"\n  ⛔ 판정 무효 (데이터 부족) — 재실행 필요, PASS/FAIL 미확정")
    else:
        print(f"\n  {'🟢 종합 PASS → Phase2 채택' if gates['PASS'] else '🔴 종합 FAIL → Phase1 단독 유지'}")


def save_json_output(gates, beta_win, days) -> Path:
    payload = {
        'generated_at': datetime.now().isoformat(timespec='minutes'),
        'phase': 2,
        'method': '2-factor (market=KOSPI + sector ETF, orthogonalized)',
        'beta_win': beta_win,
        'lookback_days': days,
        'gates': gates,
    }
    out = BASE / f'attribution_v40_phase2_{datetime.now():%Y%m%d_%H%M}.json'
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\n💾 JSON 저장: {out.name}")
    return out


def save_html_panel_phase2(decomp_p1, decomp_p2, gates, beta_win, days) -> Path:
    """Phase2 운용 패널 — 시장/섹터/종목 3단 분해 + T2진성 vs T3섹터동조 분류.
    기존 attribution_panel.html(phase1 매일 갱신)과 충돌 않게 별도 파일."""
    rows = []
    for name, df2 in decomp_p2.items():
        if df2.empty:
            continue
        r2 = df2.tail(days)
        cum_stock = r2['r_stock'].sum() * 100
        cum_mkt = r2['market_contrib'].sum() * 100
        cum_sec = r2['sector_contrib'].sum() * 100
        cum_idio2 = r2['idio'].sum() * 100
        cum_idio1 = (decomp_p1[name].tail(days)['idio'].sum() * 100
                     if name in decomp_p1 else float('nan'))
        code = SECTOR_OF.get(name)
        sector = SECTOR_NAME.get(code, '—') if code else '(없음)'
        if cum_idio2 <= -10:
            verdict, vcls = 'T2 진성약세', 'v-t2'
        elif cum_stock <= -10 and cum_idio2 > -3:
            verdict, vcls = 'T3 섹터동조(보유)', 'v-t3'
        elif cum_idio2 >= 10:
            verdict, vcls = 'T4 종목강세', 'v-t4'
        else:
            verdict, vcls = '정상', 'v-ok'
        rows.append({'name': name, 'sector': sector, 'cum_stock': cum_stock,
                     'cum_mkt': cum_mkt, 'cum_sec': cum_sec, 'cum_idio1': cum_idio1,
                     'cum_idio2': cum_idio2, 'verdict': verdict, 'vcls': vcls})
    rows.sort(key=lambda r: r['cum_idio2'])   # 진성 약세 순

    def fp(v):
        if pd.isna(v):
            return '–'
        cls = 'pos' if v > 0 else ('neg' if v < 0 else '')
        return f'<span class="{cls}">{v:+.1f}%</span>'

    body = ''.join(
        f"""<tr><td>{r['name']}</td><td class="sec">{r['sector']}</td>
              <td>{fp(r['cum_stock'])}</td><td>{fp(r['cum_mkt'])}</td>
              <td>{fp(r['cum_sec'])}</td><td>{fp(r['cum_idio1'])}</td>
              <td>{fp(r['cum_idio2'])}</td>
              <td class="{r['vcls']}">{r['verdict']}</td></tr>""" for r in rows
    )

    if not gates.get('valid', True):
        verdict_banner = (f'<div class="banner inv">⛔ 판정 무효 — 데이터 부족 '
                          f'{gates["insufficient_data"]}. 재실행 필요.</div>')
    else:
        g = ('🟢 Phase2 PASS — 채택' if gates['PASS'] else '🔴 Phase2 FAIL — Phase1 단독')
        verdict_banner = (
            f'<div class="banner {"pass" if gates["PASS"] else "fail"}">{g} · '
            f'A 재분류 {gates["reclassify_rate"]*100:.0f}%(≥30) '
            f'{"✅" if gates["gate_A_reclass>=30%"] else "❌"} · '
            f'B 한미보존 {"✅" if gates["gate_B_hanmi_preserved"] else "❌"} · '
            f'C 건전성 {"✅" if gates["gate_C_identity+betaS"] else "❌"}</div>')

    html = f"""<!DOCTYPE html>
<html lang="ko"><head><meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>진우퀀트 v4.0 Attribution Phase 2</title>
<style>
  body {{ font-family:-apple-system,"Apple SD Gothic Neo",sans-serif;
          background:#0f1419; color:#e0e6ed; padding:12px; margin:0; font-size:13px; }}
  h1 {{ color:#4fc3f7; font-size:18px; margin:4px 0 10px; }}
  .sub {{ color:#9e9e9e; font-size:11px; margin-bottom:10px; }}
  .banner {{ padding:9px 12px; border-radius:6px; margin:10px 0; font-weight:600;
             border-left:4px solid; }}
  .banner.pass {{ background:#0f2a1a; border-color:#81c784; }}
  .banner.fail {{ background:#2a0f0f; border-color:#ff5252; }}
  .banner.inv {{ background:#2a210f; border-color:#ffb74d; }}
  table {{ width:100%; border-collapse:collapse; font-size:12px;
           background:#1a232e; border-radius:6px; overflow:hidden; }}
  th {{ background:#2c3e50; color:#bbdefb; padding:6px 4px; text-align:right; }}
  th:first-child,td:first-child,th:nth-child(2),td:nth-child(2),
  th:last-child,td:last-child {{ text-align:left; }}
  td {{ padding:5px 4px; border-top:1px solid #2c3e50; text-align:right; }}
  .sec {{ color:#90a4ae; font-size:11px; }}
  .pos {{ color:#81c784; font-weight:600; }}
  .neg {{ color:#e57373; font-weight:600; }}
  .v-t2 {{ color:#ff5252; font-weight:700; }}
  .v-t3 {{ color:#81c784; font-weight:600; }}
  .v-t4 {{ color:#4fc3f7; font-weight:600; }}
  .v-ok {{ color:#7a8a99; }}
  .foot {{ color:#7a8a99; font-size:11px; margin-top:20px; padding-top:10px;
           border-top:1px solid #2c3e50; }}
</style></head><body>
<h1>진우퀀트 v4.0 Attribution — Phase 2 (시장+섹터 2-factor)</h1>
<div class="sub">생성: {datetime.now():%Y-%m-%d %H:%M} · β {beta_win}d · 분해: r = 시장기여 + 섹터기여 + idio · 최근 {days}영업일 누적</div>
{verdict_banner}
<table>
  <thead><tr><th>종목</th><th>섹터</th><th>누적 r</th><th>시장기여</th><th>섹터기여</th><th>idio P1</th><th>idio P2</th><th>판정</th></tr></thead>
  <tbody>{body}</tbody>
</table>
<div class="foot">
  <b>읽는 법:</b> idio P1 = 단일팩터(시장만) 종목고유, idio P2 = 2팩터(시장+섹터) 종목고유.<br>
  <b>섹터기여</b>가 크게 음수면 약세가 섹터 동조 → idio P2가 −10% 위로 회복 = <span class="v-t3">T3 보유</span>.<br>
  섹터 빼고도 idio P2 ≤ −10%면 <span class="v-t2">T2 진성약세</span> → F-Score·실적 점검.<br>
  섹터 ETF 없는 종목(KT&G·아모레·삼성물산·삼양식품)은 섹터기여 0 = Phase1과 동일.
</div>
</body></html>"""
    out = BASE / 'attribution_panel_phase2.html'
    out.write_text(html, encoding='utf-8')
    print(f"📊 HTML 패널: {out.name}")
    return out


# ============================================
# main
# ============================================
def main():
    args = parse_args()

    if args.self_test:
        ok = self_test()
        sys.exit(0 if ok else 1)

    from attribution_v40_phase1 import fetch_returns_panel
    rets = fetch_returns_panel(args.fetch_days)
    if rets.empty:
        print("❌ 가격 패널 비어있음")
        sys.exit(1)

    codes = [SECTOR_OF[n] for n in rets.columns if n in SECTOR_OF]
    sector_rets = fetch_sector_returns(args.fetch_days, codes)

    decomp_p2 = decompose_all_phase2(rets, sector_rets, window=args.beta_win)
    from attribution_v40_phase1 import decompose_all
    decomp_p1 = decompose_all(rets, window=args.beta_win)

    gates = evaluate_gates(decomp_p1, decomp_p2, args.days, args.z_threshold)
    print_summary(decomp_p2, gates, args.beta_win)

    if args.save_json:
        save_json_output(gates, args.beta_win, args.days)
    if args.save_html:
        save_html_panel_phase2(decomp_p1, decomp_p2, gates, args.beta_win, args.days)


if __name__ == '__main__':
    main()
