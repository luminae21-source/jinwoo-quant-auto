#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""진우퀀트 영역 3 후속 — KOSDAQ 산업분류 보강 v3 (정보 트랙 데이터 위생).  [PC 실행]

v3 (2026-06-05): v2 실측에서 KRX-DESC.Sector 내용이 산업이 아니라 **소속부**
(중견기업부 등 8개)로 판명 → **내용 기반 검증** 추가:
  ① 소속부 패턴(기업부·SPAC·관리종목·외국기업·소속부) 비중 >10% → 후보 탈락
  ② 고유 산업 수 ≥ 20 요구 (산업분류는 다수여야 정상)
  ③ FDR 전 후보 탈락 시 KIND 상장법인목록(kind.krx.co.kr) 직접 수집 fallback (업종 컬럼)

⚠️ 범위: 정보 트랙 전용 — 종결된 backtest_univ30 판정(2026-06-05)은 재산출하지 않음.
출력: kosdaq_industry.csv (code, name, sector)

실행 = 진우 PC:  python fetch_kosdaq_sector.py
사전 검증:        python fetch_kosdaq_sector.py --selftest  (네트워크 불필요)
"""
import sys, argparse, io
from pathlib import Path
import pandas as pd

BASE = Path(__file__).parent.resolve()
sys.path.insert(0, str(BASE))

OUT_CSV = BASE / 'kosdaq_industry.csv'
KOSDAQ_LIQ = BASE / 'liquidity_kosdaq.csv'

DEPT_PAT = ('기업부', 'SPAC', '관리종목', '외국기업', '소속부')
MIN_NUNIQUE = 20      # 산업분류 최소 다양성
MAX_DEPT_SHARE = 0.10 # 소속부 패턴 허용 상한


def looks_dept_like(series):
    """값들이 소속부(시장부)처럼 보이는 비중."""
    s = series.dropna().astype(str)
    if len(s) == 0:
        return 1.0
    hit = s.map(lambda v: any(p in v for p in DEPT_PAT))
    return float(hit.mean())


def validate_mapping(mp, min_nunique=MIN_NUNIQUE):
    """mapping df(code,sector) 내용 검증 → (valid, 사유)."""
    nun = mp['sector'].nunique()
    dep = looks_dept_like(mp['sector'])
    if dep > MAX_DEPT_SHARE:
        return False, f'소속부 패턴 {dep:.0%}'
    if nun < min_nunique:
        return False, f'고유값 {nun}개 (<{min_nunique})'
    return True, f'고유 산업 {nun}개'


def load_kosdaq_codes():
    if not KOSDAQ_LIQ.exists():
        raise RuntimeError(f"{KOSDAQ_LIQ.name} 없음 — KOSDAQ 코드 원천 필요")
    lk = pd.read_csv(KOSDAQ_LIQ, dtype={'code': str})
    lk['code'] = lk['code'].str.zfill(6)
    return lk[['code', 'name']].drop_duplicates('code')


def candidates_from_fdr(fdr_mod, codes, min_nunique=MIN_NUNIQUE, verbose=True):
    """FDR 리스팅×컬럼 후보 전수 — 내용 검증 통과분만 (cov, src, df) 반환."""
    cset = pd.Index(codes)
    out = []
    for ln in ('KRX-DESC', 'KRX', 'KOSDAQ', 'KOSPI'):
        try:
            t = fdr_mod.StockListing(ln)
        except Exception:
            continue
        cols = {str(c).lower(): c for c in t.columns}
        cc = next((cols[k] for k in ('code', 'symbol', '종목코드') if k in cols), None)
        if cc is None:
            continue
        for scol in ('Sector', 'Industry', '업종', 'SectorName', 'IndustryName'):
            cs = cols.get(scol.lower())
            if cs is None:
                continue
            mp = t[[cc, cs]].copy(); mp.columns = ['code', 'sector']
            mp['code'] = mp['code'].astype(str).str.zfill(6)
            mp['sector'] = mp['sector'].astype(str).str.strip()
            mp = mp[(mp['sector'] != '') & (mp['sector'].str.lower() != 'nan')]
            mp = mp.dropna().drop_duplicates('code')
            sub = mp[mp['code'].isin(cset)]
            cov = len(sub) / max(len(cset), 1)
            valid, why = validate_mapping(sub, min_nunique) if len(sub) else (False, '매칭 0')
            if verbose:
                print(f"    후보 {ln}.{cs}: 커버 {cov:.0%} · {why} → {'채택가능' if valid else '탈락'}")
            if valid and cov > 0.3:
                out.append((cov, f'{ln}.{cs}', sub))
    return sorted(out, key=lambda x: -x[0])


def fetch_kind_kosdaq(verbose=True):
    """KIND 상장법인목록 직접 수집 (fallback) — 업종 컬럼."""
    import requests
    url = ('http://kind.krx.co.kr/corpgeneral/corpList.do'
           '?method=download&searchType=13&marketType=kosdaqMkt')
    r = requests.get(url, headers={'User-Agent': 'Mozilla/5.0'}, timeout=30)
    r.raise_for_status()
    tables = pd.read_html(io.StringIO(r.text))
    df = tables[0]
    cols = {str(c): c for c in df.columns}
    code_c = next(c for c in cols if '종목코드' in c)
    sec_c = next(c for c in cols if '업종' in c)
    name_c = next((c for c in cols if '회사명' in c), code_c)
    mp = pd.DataFrame({'code': df[code_c].astype(str).str.zfill(6),
                       'name': df[name_c].astype(str),
                       'sector': df[sec_c].astype(str).str.strip()})
    mp = mp[(mp['sector'] != '') & (mp['sector'].str.lower() != 'nan')].drop_duplicates('code')
    if verbose:
        print(f"    KIND fallback: {len(mp)}종목 · 고유 업종 {mp['sector'].nunique()}개")
    return mp[['code', 'sector']]


def fetch(fdr_mod=None, verbose=True, min_nunique=MIN_NUNIQUE):
    if fdr_mod is None:
        import FinanceDataReader as fdr_mod
    base = load_kosdaq_codes()
    if verbose:
        print("  [1] FDR 리스팅 후보 탐색 (내용 검증 포함):")
    cands = candidates_from_fdr(fdr_mod, base['code'].tolist(), min_nunique, verbose)
    if cands:
        cov, src, mp = cands[0]
    else:
        if verbose:
            print("  [2] FDR 전 후보 탈락 → KIND 상장법인목록 직접 수집:")
        mp = fetch_kind_kosdaq(verbose)
        sub = mp[mp['code'].isin(set(base['code']))]
        valid, why = validate_mapping(sub, min_nunique)
        if not valid:
            raise RuntimeError(f"KIND fallback도 검증 실패 ({why}) — 수동 확인 필요")
        cov, src = len(sub) / len(base), 'KIND.업종'
        mp = sub
    out = base.merge(mp[['code', 'sector']], on='code', how='left')
    out = out[out['sector'].notna() & (out['sector'].astype(str).str.strip() != '')]
    if verbose:
        print(f"  채택 {src} · 커버리지 {cov:.0%} · 라벨 {len(out)}/{len(base)}종목 "
              f"(고유 산업 {out['sector'].nunique()}개)")
        print(f"  상위 산업: {out['sector'].value_counts().head(5).to_dict()}")
    return out[['code', 'name', 'sector']]


def main():
    print("KOSDAQ 산업분류 수집 v3 (내용 검증 + KIND fallback — 판정 불변):")
    out = fetch()
    out.to_csv(OUT_CSV, index=False, encoding='utf-8-sig')
    print(f"  💾 저장: {OUT_CSV.name}")
    print("다음: python make_score_inputs.py  (산업 라벨 자동 반영)")


def _selftest():
    ok = 0
    # 소속부 감지
    assert looks_dept_like(pd.Series(['중견기업부', '우량기업부', 'SPAC(소속부없음)'])) == 1.0; ok += 1
    assert looks_dept_like(pd.Series(['반도체 제조업', '소프트웨어 개발'])) == 0.0; ok += 1
    v, why = validate_mapping(pd.DataFrame({'code': ['1'], 'sector': ['중견기업부']}), 1)
    assert not v and '소속부' in why; ok += 1

    # v2 실패 시나리오 재현: Sector=소속부(탈락) / Industry=실산업(채택)
    class FakeFDR:
        @staticmethod
        def StockListing(name):
            if name == 'KRX-DESC':
                return pd.DataFrame({
                    'Code': ['247540', '095340', '111110'],
                    'Sector': ['중견기업부', '우량기업부', '벤처기업부'],          # 소속부 → 탈락해야
                    'Industry': ['일차전지 제조업', '반도체 제조업', '소프트웨어 개발']})
            raise RuntimeError('미지원')
    cands = candidates_from_fdr(FakeFDR, ['247540', '095340', '111110'],
                                min_nunique=2, verbose=False)
    assert len(cands) == 1 and 'Industry' in cands[0][1], [c[1] for c in cands]; ok += 1
    assert set(cands[0][2]['sector']) == {'일차전지 제조업', '반도체 제조업', '소프트웨어 개발'}; ok += 1

    # KIND 파서 정규화 (read_html 결과 모사)
    df = pd.DataFrame({'회사명': ['에코프로비엠'], '종목코드': ['247540'],
                       '업종': ['일차전지 및 축전지 제조업'], '주요제품': ['양극재']})
    cols = {str(c): c for c in df.columns}
    code_c = next(c for c in cols if '종목코드' in c)
    sec_c = next(c for c in cols if '업종' in c)
    assert df[code_c].astype(str).str.zfill(6).iloc[0] == '247540'
    assert '제조업' in df[sec_c].iloc[0]; ok += 1

    print(f"[OK] fetch_kosdaq_sector v3 self-test 통과 ({ok} checks)")
    print("     v2 실패 모드(소속부 100% 커버) 재현 → 탈락 확인됨")


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
