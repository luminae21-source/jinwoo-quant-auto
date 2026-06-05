#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""진우퀀트 영역 3 확장 모듈 — Stage 1: 점수 입력 캐시 생성.

결정메모: 진우퀀트_영역3_확장모듈_결정메모.md §2 (PIT-proxy, 2026-06-05 승인) §9.

fundamentals 3원천 병합 (우선순위: fundamentals_univ_increment.csv >
fundamentals_pit.csv > fundamentals_kosdaq.csv, (code,fiscal_year) 단위)
→ pit_universe_backtest.piotroski() (무수정 재사용)
→ score_inputs_univ.csv: code, fiscal_year, F, accrual, noa_ratio, market, sector, name

시장 라벨: market_map.csv (2,770종목) / 섹터: liquidity_sector.csv(KOSPI 산업) +
liquidity_kosdaq.csv(KOSDAQ 시장부 — 산업분류 아님, universe확정 메모 §5-3 한계 유지).

실행: python make_score_inputs.py            (샌드박스/PC 모두 가능, 네트워크 불필요)
검증: python make_score_inputs.py --selftest
분기 갱신: fetch_dart_fundamentals_pit.py --codes-csv universe_rule30_latest.csv
          --start-year <직전년> --end-year <올해> --out fundamentals_univ_increment.csv
          실행 후 본 스크립트 재실행 (결정메모 §8 분기 재스크린 룰).

기존 파일 무수정 — 출력은 score_inputs_univ.csv 한 개.
"""
import sys, argparse
from pathlib import Path
import numpy as np
import pandas as pd

BASE = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE))

from pit_universe_backtest import piotroski  # 무수정 재사용 (Phase A 검증본)

SRC_INCREMENT = BASE / 'fundamentals_univ_increment.csv'   # 분기 갱신분 (있으면 최우선)
SRC_PIT = BASE / 'fundamentals_pit.csv'                    # KOSPI 광범위 (577종목)
SRC_KOSDAQ = BASE / 'fundamentals_kosdaq.csv'              # KOSDAQ (297종목)
MARKET_MAP = BASE / 'market_map.csv'
SECTOR_KOSPI = BASE / 'liquidity_sector.csv'
SECTOR_KOSDAQ = BASE / 'liquidity_kosdaq.csv'
UNIVERSE_CSV = BASE / 'universe_rule30_latest.csv'
OUT_CSV = BASE / 'score_inputs_univ.csv'


def _read_fund(p):
    df = pd.read_csv(p, dtype={'code': str})
    df['code'] = df['code'].str.zfill(6)
    df['fiscal_year'] = df['fiscal_year'].astype(int)
    return df


def merge_fundamentals(paths_in_priority, verbose=True):
    """우선순위 순서의 fundamentals CSV 목록 → (code,fiscal_year) 중복 제거 병합.
    앞선 원천이 이김 (증분 > pit > kosdaq)."""
    frames, seen_src = [], []
    for p in paths_in_priority:
        p = Path(p)
        if not p.exists():
            continue
        frames.append(_read_fund(p))
        seen_src.append(p.name)
    if not frames:
        raise FileNotFoundError('fundamentals 원천 없음')
    allf = pd.concat(frames, ignore_index=True)
    before = len(allf)
    allf = allf.drop_duplicates(subset=['code', 'fiscal_year'], keep='first')
    if verbose:
        print(f"  병합: {' > '.join(seen_src)} → {len(allf)}행 (중복 제거 {before - len(allf)})")
    return allf


def attach_labels(pf, verbose=True):
    """piotroski 출력에 market·sector·name 라벨 부착."""
    if MARKET_MAP.exists():
        mm = pd.read_csv(MARKET_MAP, dtype=str)
        mm['code'] = mm['code'].str.zfill(6)
        mkt = dict(zip(mm['code'], mm['market']))
    else:
        mkt = {}
    sec, nm = {}, {}
    for p, label in ((SECTOR_KOSPI, 'KOSPI'), (SECTOR_KOSDAQ, 'KOSDAQ')):
        if Path(p).exists():
            ls = pd.read_csv(p, dtype={'code': str})
            ls['code'] = ls['code'].str.zfill(6)
            for _, r in ls.iterrows():
                sec.setdefault(r['code'], r.get('sector'))
                nm.setdefault(r['code'], r.get('name'))
    out = pf.copy()
    # 시장: market_map 우선, 없으면 KOSDAQ liquidity에 있으면 KOSDAQ, 그 외 KOSPI
    kosdaq_codes = set()
    if Path(SECTOR_KOSDAQ).exists():
        kosdaq_codes = set(pd.read_csv(SECTOR_KOSDAQ, dtype={'code': str})['code'].str.zfill(6))
    out['market'] = out['code'].map(lambda c: mkt.get(c) or ('KOSDAQ' if c in kosdaq_codes else 'KOSPI'))
    out['sector'] = out['code'].map(lambda c: sec.get(c) or '')
    out['name'] = out['code'].map(lambda c: nm.get(c) or '')
    if verbose:
        vc = out.drop_duplicates('code')['market'].value_counts().to_dict()
        n_sec = (out.drop_duplicates('code')['sector'] != '').sum()
        print(f"  라벨: 시장 {vc} · 섹터 보유 {n_sec}종목 (KOSDAQ 섹터=시장부, 한계 등록됨)")
    return out


def coverage_check(out, verbose=True):
    """확정 universe 30 커버리지 리포트 (게이트 아님 — 정보)."""
    if not UNIVERSE_CSV.exists():
        return None
    u = pd.read_csv(UNIVERSE_CSV, dtype={'code': str})
    u['code'] = u['code'].str.zfill(6)
    have = set(out['code'])
    missing = [f"{r['name']}({r['code']})" for _, r in u.iterrows() if r['code'] not in have]
    latest = out[out['code'].isin(set(u['code']))].groupby('code')['fiscal_year'].max()
    if verbose:
        print(f"  universe 30 커버: {30 - len(missing)}/30"
              + (f" · 미커버 {missing}" if missing else '')
              + f" · 최신 회계연도 분포 {latest.value_counts().sort_index().to_dict()}")
    return missing


def build(verbose=True, write=True):
    fund = merge_fundamentals([SRC_INCREMENT, SRC_PIT, SRC_KOSDAQ], verbose=verbose)
    pf = piotroski(fund)                       # code, fiscal_year, F, accrual, noa_ratio
    out = attach_labels(pf, verbose=verbose)
    out = out.sort_values(['code', 'fiscal_year']).reset_index(drop=True)
    if write:
        out.to_csv(OUT_CSV, index=False, encoding='utf-8-sig')
        if verbose:
            print(f"  💾 저장: {OUT_CSV.name} ({len(out)}행, {out['code'].nunique()}종목, "
                  f"FY {out['fiscal_year'].min()}~{out['fiscal_year'].max()})")
    coverage_check(out, verbose=verbose)
    return out


# ============================================================
# self-test (synthetic — 네트워크·실파일 불필요)
# ============================================================

def _selftest():
    ok = 0
    # 손계산 가능한 synthetic 2종목 × 3개년
    rows = []
    for y, (ni, cfo, rev, cogs, a, lia, ncl, ca, cl, cash, cap) in {
        2020: (50, 80, 1000, 600, 1000, 400, 200, 500, 200, 100, 50),
        2021: (80, 120, 1200, 660, 1100, 380, 150, 600, 210, 120, 50),   # 전항목 개선 → F 높음
        2022: (-20, -5, 900, 700, 1300, 700, 400, 400, 300, 80, 80),    # 악화 → F 낮음
    }.items():
        rows.append(dict(code='000001', fiscal_year=y, revenue=rev, cogs=cogs, op_income=ni,
                         net_income=ni, assets=a, liabilities=lia, equity=a - lia,
                         current_assets=ca, current_liab=cl, cash=cash, cfo=cfo,
                         noncurrent_liab=ncl, issued_capital=cap))
    f = pd.DataFrame(rows)
    pf = piotroski(f)
    f21 = float(pf[pf.fiscal_year == 2021]['F'].iloc[0])
    f22 = float(pf[pf.fiscal_year == 2022]['F'].iloc[0])
    # 2021 손계산: ROA>0✓ CFO>0✓ ROA개선(0.0727>0.05)✓ CFO>NI✓ lev감소(0.136<0.2)✓
    #             CR개선(2.857>2.5)✓ 신주미발행(50<=50)✓ GM개선(0.45>0.4)✓ turn개선(1.091>1.0)✓ = 9
    assert f21 == 9, f'2021 F={f21} (기대 9)'; ok += 1
    assert f22 <= 2, f'2022 F={f22} (기대 ≤2: ROA<0, CFO<0, 악화)'; ok += 1
    acc21 = float(pf[pf.fiscal_year == 2021]['accrual'].iloc[0])
    assert abs(acc21 - (80 - 120) / 1100) < 1e-9, 'accrual 정의 (NI-CFO)/assets'; ok += 1

    # 병합 우선순위: 같은 (code,year)에서 앞선 원천이 이김
    import tempfile, os
    t1 = Path(tempfile.gettempdir()) / '_msi_a.csv'
    t2 = Path(tempfile.gettempdir()) / '_msi_b.csv'
    f.assign(assets=9999).to_csv(t1, index=False)   # 증분(우선): assets=9999
    f.to_csv(t2, index=False)
    merged = merge_fundamentals([t1, t2], verbose=False)
    assert float(merged['assets'].iloc[0]) == 9999, '증분 우선 병합 실패'; ok += 1
    assert len(merged) == 3, '중복 제거 실패'; ok += 1
    os.unlink(t1); os.unlink(t2)

    # 라벨 부착: 실파일 없이도 동작 (기본값 경로)
    lab = attach_labels(pf, verbose=False)
    assert set(lab.columns) >= {'code', 'fiscal_year', 'F', 'accrual', 'noa_ratio',
                                'market', 'sector', 'name'}; ok += 1
    print(f"[OK] make_score_inputs self-test 통과 ({ok} checks)")
    print(f"     synthetic F: 2021={f21:.0f}(만점), 2022={f22:.0f}(악화)")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--selftest', action='store_true')
    a, _ = ap.parse_known_args()
    try:
        _selftest() if a.selftest else build()
    except Exception:
        import traceback
        print("\n===== [에러] 아래 내용을 그대로 복사해 붙여주세요 =====")
        traceback.print_exc()
