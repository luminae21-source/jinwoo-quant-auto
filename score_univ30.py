#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""진우퀀트 영역 3 확장 모듈 — Stage 2: PIT-proxy 점수 정의 단일화.

결정메모: 진우퀀트_영역3_확장모듈_결정메모.md §2(점수)·§3(2층 구조)·§4(비용)·§6(regime 라우팅).
backtest_univ30.py와 분기 운용이 같은 정의를 import (v40 패턴 — 정의 단일화).

점수 (2026-06-05 진우 승인 PIT-proxy — pit_universe_backtest.score_at 산식과 동일):
  체력 base = F(정수 Piotroski, FY−1)×12/9 + Sloan(accrual 5분위 +2~−2)
  + NOA(noa_ratio 5분위) + Mom12(구간) + BAB(β 구간) + Echo(rank ±1)
  분위수·rank는 당월 멤버십 내 상대화 (production이 18종 내 상대화한 구조와 동일).
  회전층(연 1회 5월)은 pit_universe_backtest.score_at 원본을 그대로 호출 (검증본 무수정).

등급·선별 = production 컨벤션: grade() 절대 컷, picks={S+,S,A}, EW+caps(15%/35%),
picks 0 → 현금. 컷 튜닝 금지 (결정메모 §2).

PIT 규약: 리밸일 d0에서 월말 데이터는 < d0 월말까지만, 재무 FY = (월≥5 ? 연−1 : 연−2)
          — 3월 사업보고서 공시 + 버퍼 (결정메모 §3).

검증: python score_univ30.py --selftest   (네트워크·실파일 불필요)
"""
import sys, argparse
from pathlib import Path
import numpy as np
import pandas as pd

BASE = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE))

# 검증본 무수정 재사용
from pit_universe_backtest import _qscore, _mom_score, _bab_score, score_at
# D 산출물 read-only import (REGIME_MULTS 정의 단일화 — 결정메모 §5 B: 무수정)
from score_v40_regime import (REGIME_MULTS, DEFAULT_MULT, mults_for,
                              adjusted_total, TARGET_GRADES)
from score_v37 import grade                       # production 등급 컷 (무수정)
from score_v37_2 import apply_weight_caps          # production caps (무수정)

# ---------- 사전 등록 상수 (결정메모 §4 — 변경 금지) ----------
COST_BY_MARKET = {'KOSPI': 0.0035, 'KOSDAQ': 0.0060}   # 왕복, 턴오버(Σ|Δw|/2)에 적용
REF_COST = 0.00235                                     # 참고 라인 전용 — 판정 미사용
TOP_K = 30
ROT_MONTH = 5                                          # 연 1회 5월 PIT 로테이션

INPUTS_CSV = BASE / 'score_inputs_univ.csv'
MONTHLY_CSV = BASE / 'kospi_monthly_prices.csv'        # pooled 584종목 월말 패널 (이름 유산)
UNIVERSE_CSV = BASE / 'universe_rule30_latest.csv'


# ============================================================
# 입력 로더
# ============================================================

def load_inputs(path=INPUTS_CSV):
    df = pd.read_csv(path, dtype={'code': str})
    df['code'] = df['code'].str.zfill(6)
    df['fiscal_year'] = df['fiscal_year'].astype(int)
    return df


def load_monthly(path=MONTHLY_CSV):
    p = pd.read_csv(path, index_col=0, parse_dates=True)
    p.columns = [str(c).zfill(6) for c in p.columns]
    return p


def label_maps(inputs):
    """inputs → market_of / sector_of / name_of dict. 섹터 없음 → 종목 고유 라벨
    (sector cap에서 무관 종목끼리 묶이는 것 방지)."""
    last = inputs.drop_duplicates('code', keep='last').set_index('code')
    market_of = last['market'].to_dict()
    sector_of = {c: (s if isinstance(s, str) and s else f'_unk_{c}')
                 for c, s in last['sector'].items()}
    name_of = last['name'].to_dict()
    return market_of, sector_of, name_of


def fy_for(d0):
    """리밸일 d0에서 사용할 재무 회계연도 (보수적 PIT — 결정메모 §3)."""
    d0 = pd.Timestamp(d0)
    return d0.year - 1 if d0.month >= ROT_MONTH else d0.year - 2


# ============================================================
# 회전층 — 연 1회 5월 PIT 로테이션 (score_at 검증본 그대로)
# ============================================================

def rotations(monthly, inputs, top_k=TOP_K, rot_month=ROT_MONTH, verbose=False):
    """월말 패널 전체에서 매년 rot_month에 pooled top-K 멤버십 산출.
    반환: {로테이션 월말 Timestamp: [code,...]} (시간順)."""
    months = monthly.index
    mkt_ret = monthly.pct_change().mean(axis=1)
    fcols = list(monthly.columns)
    pf = inputs[['code', 'fiscal_year', 'F', 'accrual', 'noa_ratio']]
    out = {}
    for i, dt in enumerate(months):
        if dt.month != rot_month or i < 12:
            continue
        sc = score_at(i, months, monthly, mkt_ret, fcols, pf, dt.year)
        if len(sc) >= top_k:
            out[dt] = list(sc.head(top_k).index)
            if verbose:
                print(f"  로테이션 {dt.date()}: {top_k}종목 (풀 {len(sc)})")
    return out


def members_for(d0, rots):
    """d0 이전(≤) 가장 최근 로테이션 멤버십. 없으면 []."""
    d0 = pd.Timestamp(d0)
    keys = [k for k in rots if k <= d0]
    return rots[max(keys)] if keys else []


# ============================================================
# 월별층 — 멤버십 내 컴포넌트 (PIT-proxy, ≤d0)
# ============================================================

def member_components_at(d0, members, monthly, inputs, min_hist=12):
    """리밸일 d0의 멤버별 컴포넌트 dict {code: {'base','noa','mom','bab','echo'}}.
    adjusted_total(comp, state, variant) (score_v40_regime)와 그대로 호환.
    base에 Sloan 포함·NOA 분리 (D 컨벤션: base·NOA는 regime 무변경 — 결정메모 §2·§6)."""
    d0 = pd.Timestamp(d0)
    me = monthly[monthly.index < d0]            # 월말 < d0 (월초 리밸 → 직전 월말까지)
    if len(me) < min_hist or not members:
        return {}
    fy = fy_for(d0)
    snap = inputs[inputs.fiscal_year == fy].set_index('code')
    mkt_m = me.pct_change().mean(axis=1)        # pool EW (pit 컨벤션)

    raw = {}
    for c in members:
        if c not in me.columns:
            continue
        s = me[c].dropna()
        if len(s) < min_hist or pd.isna(me[c].iloc[-1]):
            continue
        sm = me[c]                               # 패널 정렬 유지(맨끝 정합)
        mom = (sm.iloc[-1] / sm.iloc[-12] - 1) if not pd.isna(sm.iloc[-12]) else np.nan
        echo = (sm.iloc[-7] / sm.iloc[-12] - 1) if not pd.isna(sm.iloc[-12]) else np.nan
        r = sm.pct_change().iloc[-36:]
        m = mkt_m.iloc[-36:]
        df = pd.concat([r, m], axis=1).dropna()
        beta = (df.iloc[:, 0].cov(df.iloc[:, 1]) / df.iloc[:, 1].var()) \
            if len(df) >= 18 and df.iloc[:, 1].var() > 0 else np.nan
        raw[c] = {
            'F': float(snap.loc[c, 'F']) if c in snap.index else np.nan,
            'acc': float(snap.loc[c, 'accrual']) if c in snap.index else np.nan,
            'noa': float(snap.loc[c, 'noa_ratio']) if c in snap.index else np.nan,
            'mom': mom, 'echo': echo, 'beta': beta,
        }
    if not raw:
        return {}
    d = pd.DataFrame(raw).T.apply(pd.to_numeric, errors='coerce')
    F = d['F'].fillna(d['F'].median())          # pit 컨벤션 (멤버십 내 중앙값)
    sloan_q = _qscore(d['acc'], good_low=True)
    noa_q = _qscore(d['noa'], good_low=True)
    er = d['echo'].rank(pct=True)
    echo_s = er.map(lambda v: 1 if v >= .8 else (-1 if v <= .2 else 0)).fillna(0)
    comp = {}
    for c in d.index:
        comp[c] = {
            'base': float(F[c] * (12 / 9) + sloan_q[c]),
            'noa': float(noa_q[c]),
            'mom': float(_mom_score(d.loc[c, 'mom'])),
            'bab': float(_bab_score(d.loc[c, 'beta'])),
            'echo': float(echo_s[c]),
        }
    return comp


def totals_picks(comp, state_of=None, variant='w'):
    """컴포넌트 → 조정 체력·picks. state_of: code→regime state (None=전부 NEUTRAL=base).
    시장 라우팅은 호출부(backtest)가 state_of로 주입 (결정메모 §6)."""
    tot, picks = {}, []
    for c, k in comp.items():
        st = state_of(c) if state_of else 'NEUTRAL'
        t = adjusted_total(k, st, variant)
        tot[c] = t
        if grade(t) in TARGET_GRADES:
            picks.append(c)
    return tot, picks


def weights_for(picks, sector_of):
    """production caps 그대로 (종목 15%·섹터 35%, 정규화)."""
    if not picks:
        return {}
    return apply_weight_caps(picks, {c: sector_of.get(c, f'_unk_{c}') for c in picks}) \
        if isinstance(sector_of, dict) else apply_weight_caps(picks, sector_of)


def turnover_cost(w_new, w_old, market_of, cost_by_market=COST_BY_MARKET, flat=None):
    """Σ|Δw|/2 컨벤션 (공식 엔진 동일) — 시장별 비용 라우팅 (결정메모 §4).
    flat 지정 시 단일 비용 (참고 라인·fixed18용). 반환: (총 턴오버, 비용)."""
    alln = set(w_new) | set(w_old)
    to_total, cost = 0.0, 0.0
    for x in alln:
        dw = abs(w_new.get(x, 0) - w_old.get(x, 0)) / 2
        to_total += dw
        c = flat if flat is not None else cost_by_market.get(market_of.get(x, 'KOSPI'),
                                                             cost_by_market['KOSPI'])
        cost += dw * c
    return to_total, cost


# ============================================================
# live 보조 (분기 재스크린·월별 점수표 — 데이터 기준일 = 월간 패널 마지막 행)
# ============================================================

def live_table(monthly=None, inputs=None, members=None):
    inputs = inputs if inputs is not None else load_inputs()
    monthly = monthly if monthly is not None else load_monthly()
    market_of, sector_of, name_of = label_maps(inputs)
    if members is None:
        u = pd.read_csv(UNIVERSE_CSV, dtype={'code': str})
        members = u['code'].str.zfill(6).tolist()
    d0 = monthly.index[-1] + pd.Timedelta(days=1)   # 패널 마지막 월말 직후 가정
    comp = member_components_at(d0, members, monthly, inputs)
    tot, picks = totals_picks(comp)
    rows = [{'code': c, 'name': name_of.get(c, ''), 'market': market_of.get(c, ''),
             'total': round(tot[c], 2), 'grade': grade(tot[c]),
             'pick': c in set(picks), **{k: round(v, 2) for k, v in comp[c].items()}}
            for c in sorted(tot, key=tot.get, reverse=True)]
    df = pd.DataFrame(rows)
    print(f"기준: 월간 패널 마지막 행 {monthly.index[-1].date()} · FY{fy_for(d0)} "
          f"· picks {len(picks)}/{len(comp)}")
    print(df.to_string(index=False))
    return df


# ============================================================
# self-test (synthetic — 실파일 불필요)
# ============================================================

def _selftest():
    ok = 0
    # fy_for: 보수적 PIT
    assert fy_for('2026-06-01') == 2025 and fy_for('2026-03-02') == 2024; ok += 1

    # synthetic: 40개월 × 8종목 (4 KOSPI + 4 KOSDAQ)
    idx = pd.date_range('2022-01-31', periods=40, freq='ME')
    rng = np.random.default_rng(7)
    cols = [f'10000{i}' for i in range(4)] + [f'20000{i}' for i in range(4)]
    drift = {c: 0.035 if c == '100000' else (-0.025 if c == '200003' else 0.004) for c in cols}
    data = {c: 100 * np.cumprod(1 + drift[c] + rng.normal(0, 0.01, 40)) for c in cols}
    monthly = pd.DataFrame(data, index=idx)

    inputs = pd.DataFrame([
        dict(code=c, fiscal_year=y,
             F=(9 if c == '100000' else (1 if c == '200003' else 6)),
             accrual=(-0.10 if c == '100000' else (0.10 if c == '200003' else 0.0)) + i * 0.001,
             noa_ratio=(0.2 if c == '100000' else (1.2 if c == '200003' else 0.7)) + i * 0.001,
             market=('KOSPI' if c.startswith('1') else 'KOSDAQ'),
             sector=('섹터A' if c in ('100000', '100001') else ''), name=c)
        for i, c in enumerate(cols) for y in (2021, 2022, 2023, 2024)
    ])

    d0 = pd.Timestamp('2025-03-03')
    comp = member_components_at(d0, cols, monthly, inputs)
    assert len(comp) == 8; ok += 1
    # 손계산: 100000 = F9→12 + Sloan+2(최저 accrual) = base 14, NOA+2(최저), 상승추세 mom·echo 상위
    c0 = comp['100000']
    assert abs(c0['base'] - 14.0) < 1e-9 and c0['noa'] == 2.0, f"base/noa 불일치: {c0}"; ok += 1
    assert c0['mom'] >= 1 and c0['echo'] == 1, f"mom/echo 기대 상위: {c0}"; ok += 1
    c3 = comp['200003']
    assert c3['base'] <= (1 * 12 / 9 - 1) and c3['mom'] <= -1, f"악화 종목: {c3}"; ok += 1

    # PIT: d0 3월 → FY 2023 (연−2)
    assert fy_for(d0) == 2023; ok += 1

    # 등급·picks (base): 100000은 S+/S 기대
    tot, picks = totals_picks(comp)
    assert '100000' in picks and grade(tot['100000']) in ('S+', 'S'), \
        f"100000 total={tot['100000']}"; ok += 1
    assert '200003' not in picks; ok += 1

    # regime 조정: RISK_OFF s → mom·echo 0, bab×2 (시장 라우팅: KOSDAQ만 OFF)
    st = lambda c: 'RISK_OFF' if c.startswith('2') else 'NEUTRAL'
    tot_s, _ = totals_picks(comp, state_of=st, variant='s')
    assert abs(tot_s['100000'] - tot['100000']) < 1e-9, 'KOSPI 종목은 무변경이어야'; ok += 1
    k = comp['200001']
    exp = k['base'] + k['noa'] + k['bab'] * 2.0          # mom·echo ×0
    assert abs(tot_s['200001'] - exp) < 1e-9, f"{tot_s['200001']} vs {exp}"; ok += 1

    # caps: 섹터A 2종목 → 합 ≤ 35%+ε, 전체 합 1
    w = weights_for(picks, {c: ('섹터A' if c in ('100000', '100001') else f'_unk_{c}') for c in picks})
    assert abs(sum(w.values()) - 1.0) < 1e-9; ok += 1
    if '100000' in w and '100001' in w and len(w) >= 4:
        assert w['100000'] + w['100001'] <= 0.35 + 1e-6 or len(w) <= 3; ok += 1

    # 시장별 비용 라우팅: KOSDAQ 1종목 전체 교체 = 0.60%×1.0 (왕복/2 ×2 종목... Σ|Δw|/2 = 1)
    market_of = {c: ('KOSPI' if c.startswith('1') else 'KOSDAQ') for c in cols}
    to, cost = turnover_cost({'200000': 1.0}, {'200001': 1.0}, market_of)
    assert abs(to - 1.0) < 1e-9 and abs(cost - 0.0060) < 1e-12, f"to={to}, cost={cost}"; ok += 1
    to2, cost2 = turnover_cost({'100000': 1.0}, {'200001': 1.0}, market_of)
    assert abs(cost2 - (0.5 * 0.0035 + 0.5 * 0.0060)) < 1e-12, '혼합 라우팅'; ok += 1
    _, cflat = turnover_cost({'100000': 1.0}, {'200001': 1.0}, market_of, flat=REF_COST)
    assert abs(cflat - REF_COST) < 1e-12; ok += 1

    # 회전층: score_at 검증본 호출 (멤버십 top_k)
    rots = rotations(monthly, inputs, top_k=5, rot_month=5)
    assert len(rots) >= 1; ok += 1
    first = list(rots.values())[0]
    assert len(first) == 5 and '100000' in first and '200003' not in first, first; ok += 1
    assert members_for('2021-01-01', rots) == []; ok += 1
    assert members_for(pd.Timestamp('2099-01-01'), rots) == list(rots.values())[-1]; ok += 1

    # REGIME_MULTS 등록값 동일성 (D §3 무수정 확인)
    assert REGIME_MULTS['s']['RISK_OFF'] == {'mom': 0.0, 'echo': 0.0, 'bab': 2.0}; ok += 1
    assert REGIME_MULTS['w']['RISK_OFF'] == {'mom': 0.5, 'echo': 0.5, 'bab': 1.5}; ok += 1

    print(f"[OK] score_univ30 self-test 통과 ({ok} checks)")
    print(f"     예시 total: 100000={tot['100000']:.2f}({grade(tot['100000'])}) "
          f"200003={tot['200003']:.2f}({grade(tot['200003'])}) · picks {len(picks)}/8")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--selftest', action='store_true')
    ap.add_argument('--live', action='store_true', help='월별 점수표 (패널 기준일)')
    a, _ = ap.parse_known_args()
    try:
        _selftest() if a.selftest else (live_table() if a.live else _selftest())
    except Exception:
        import traceback
        print("\n===== [에러] 아래 내용을 그대로 복사해 붙여주세요 =====")
        traceback.print_exc()