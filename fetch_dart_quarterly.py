#!/usr/bin/env python3
"""
진우퀀트 v3.8 — 시계열 분기 quality 데이터 수집

목적: 단일 시점 cache의 lookahead bias 해결
방법: 2022 Q1 ~ 2026 Q1 분기별 재무제표 수집 → point-in-time 백테스트 가능

각 시점에서 18종목 × 17분기 = ~306개 데이터 포인트.

DART 보고서 코드:
  - 11013: 1분기 보고서 (5월 공시)
  - 11012: 반기 보고서 (8월 공시)
  - 11014: 3분기 보고서 (11월 공시)
  - 11011: 사업보고서 (3월 공시)

학술 근거:
  - GPT Q1 #1 빠진 영역: 과최적화 방지 (point-in-time 필수)
  - Cooper-Gulen-Schill 2008: PIT data 표준
  - v3.8.1 / v3.8.2 백테스트 실패 진단: 단일 시점 = 4년 OOS와 역방향 작동

사용법:
  python fetch_dart_quarterly.py
  python fetch_dart_quarterly.py --start-year 2021 --end-year 2026

출력:
  - quality_timeseries_cache.json (18종목 × 17분기 quality 지표)
  - quality_timeseries_summary.csv (사람이 읽는 요약)

선행:
  - dart_config.json 또는 환경변수 DART_API_KEY
  - dart_corp_codes.json (fetch_dart_quality.py 1회 실행으로 캐시됨)
"""

import sys
import os
import io
import json
import argparse
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path
import time

import pandas as pd

BASE = Path(__file__).parent.resolve()
TIMESERIES_CACHE = BASE / 'quality_timeseries_cache.json'
SUMMARY_CSV = BASE / 'quality_timeseries_summary.csv'
CONFIG_FILE = BASE / 'dart_config.json'
CORP_CODE_CACHE = BASE / 'dart_corp_codes.json'

DART_BASE = "https://opendart.fss.or.kr/api"

JINWOO_UNIVERSE = {
    '삼성전자':       {'코드': '005930', '업종': '제조업'},
    'SK하이닉스':     {'코드': '000660', '업종': '제조업'},
    '한미반도체':     {'코드': '042700', '업종': '제조업'},
    '알테오젠':       {'코드': '196170', '업종': '제조업'},
    '기아':           {'코드': '000270', '업종': '제조업'},
    'NAVER':          {'코드': '035420', '업종': '제조업'},
    '카카오':         {'코드': '035720', '업종': '제조업'},
    '한화에어로':     {'코드': '012450', '업종': '제조업'},
    'LIG넥스원':      {'코드': '079550', '업종': '제조업'},
    'KT&G':           {'코드': '033780', '업종': '제조업'},
    '삼성SDI':        {'코드': '006400', '업종': '제조업'},
    '아모레퍼시픽':   {'코드': '090430', '업종': '제조업'},
    '삼성물산':       {'코드': '028260', '업종': '제조업'},
    '삼양식품':       {'코드': '003230', '업종': '제조업'},
    'ISC':            {'코드': '095340', '업종': '제조업'},
    '두산에너빌리티': {'코드': '034020', '업종': '제조업'},
    'KB금융':         {'코드': '105560', '업종': '은행'},
    'NH투자증권':     {'코드': '005940', '업종': '증권사'},
}


def parse_args():
    p = argparse.ArgumentParser()
    p.add_argument('--start-year', type=int, default=2021)
    p.add_argument('--end-year', type=int, default=None)  # default: 현재 연도
    return p.parse_args()


def _ensure_requests():
    try:
        import requests
        return requests
    except ImportError:
        import subprocess
        subprocess.run([sys.executable, '-m', 'pip', 'install', '-q', 'requests'],
                       check=True)
        import requests
        return requests


def _get_api_key():
    key = os.environ.get('DART_API_KEY')
    if key:
        return key
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text(encoding='utf-8')).get('api_key')
        except Exception:
            pass
    return None


def get_corp_code_map(api_key, requests_mod):
    """corp_code 캐시 활용 (fetch_dart_quality.py가 이미 생성)"""
    if CORP_CODE_CACHE.exists():
        return json.loads(CORP_CODE_CACHE.read_text(encoding='utf-8'))

    response = requests_mod.get(f"{DART_BASE}/corpCode.xml",
                                params={'crtfc_key': api_key}, timeout=30)
    response.raise_for_status()
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        xml_data = zf.read('CORPCODE.xml')
    root = ET.fromstring(xml_data)
    code_map = {}
    for company in root.findall('list'):
        sc = (company.findtext('stock_code') or '').strip()
        cc = (company.findtext('corp_code') or '').strip()
        if sc and cc and sc != ' ':
            code_map[sc] = cc
    CORP_CODE_CACHE.write_text(json.dumps(code_map, ensure_ascii=False),
                               encoding='utf-8')
    return code_map


def fetch_full_financials(corp_code, year, reprt_code, api_key, requests_mod):
    """단일 시점 재무제표 호출 (CFS → OFS fallback)"""
    params = {
        'crtfc_key': api_key,
        'corp_code': corp_code,
        'bsns_year': str(year),
        'reprt_code': reprt_code,
        'fs_div': 'CFS',
    }
    try:
        response = requests_mod.get(f"{DART_BASE}/fnlttSinglAcntAll.json",
                                    params=params, timeout=15)
        data = response.json()
        if data.get('status') != '000':
            if data.get('status') == '013':
                params['fs_div'] = 'OFS'
                response = requests_mod.get(f"{DART_BASE}/fnlttSinglAcntAll.json",
                                            params=params, timeout=15)
                data = response.json()
                if data.get('status') != '000':
                    return None
            else:
                return None
        return data.get('list', [])
    except Exception:
        return None


def extract_accounts(fs_list):
    """XBRL account_id 우선 + account_nm fallback"""
    if not fs_list:
        return {}
    ID_MAP = {
        'ifrs-full_Revenue': '매출액',
        'ifrs_Revenue': '매출액',
        'ifrs-full_CostOfSales': '매출원가',
        'ifrs_CostOfSales': '매출원가',
        'dart_OperatingIncomeLoss': '영업이익',
        'ifrs-full_OperatingIncomeLoss': '영업이익',
        'ifrs-full_ProfitLoss': '당기순이익',
        'ifrs_ProfitLoss': '당기순이익',
        'ifrs-full_Assets': '자산총계',
        'ifrs_Assets': '자산총계',
        'ifrs-full_Equity': '자기자본총계',
        'ifrs_Equity': '자기자본총계',
        'ifrs-full_Liabilities': '부채총계',
        'ifrs_Liabilities': '부채총계',
    }
    NM_MAP = {
        '매출액': '매출액', '수익(매출액)': '매출액', '매출': '매출액',
        '영업수익': '영업수익',
        '매출원가': '매출원가',
        '영업이익': '영업이익', '영업이익(손실)': '영업이익',
        '자산총계': '자산총계',
        '자본총계': '자기자본총계', '자기자본': '자기자본총계',
        '자기자본총계': '자기자본총계',
        '부채총계': '부채총계',
        '당기순이익': '당기순이익', '당기순이익(손실)': '당기순이익',
    }
    result = {}
    for item in fs_list:
        aid = (item.get('account_id') or '').strip()
        anm = (item.get('account_nm') or '').strip()
        amt_str = item.get('thstrm_amount', '')
        try:
            amt = float(str(amt_str).replace(',', '')) if amt_str else 0
        except (ValueError, TypeError):
            continue
        std = ID_MAP.get(aid) or NM_MAP.get(anm)
        if std and std not in result:
            result[std] = amt
        if anm == '영업수익' and '영업수익' not in result:
            result['영업수익'] = amt
            if '매출액' not in result:
                result['매출액'] = amt
    return result


def fetch_quarterly_timeseries(start_year, end_year):
    """
    분기별 시계열 수집.
    각 종목·각 분기별 (year, quarter, reprt_code) 조합으로 수집.
    """
    requests_mod = _ensure_requests()
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError(
            f"DART API key 미설정. {CONFIG_FILE} 에 "
            '{"api_key": "..."} 저장 필요'
        )
    code_map = get_corp_code_map(api_key, requests_mod)

    # 분기 코드 (year, quarter, reprt_code)
    quarter_codes = []
    for y in range(start_year, end_year + 1):
        quarter_codes.append((y, 1, '11013'))  # 1Q
        quarter_codes.append((y, 2, '11012'))  # 반기
        quarter_codes.append((y, 3, '11014'))  # 3Q
        quarter_codes.append((y, 4, '11011'))  # 사업보고서

    print(f"\n📊 시계열 quality 수집 ({start_year}~{end_year}, "
          f"총 {len(quarter_codes)}분기 × 18종목 = {len(quarter_codes)*18}회 호출)")
    print("=" * 80)

    # 종목별 분기별 데이터: results[name][f"{y}Q{q}"] = financials
    results = {}
    total_calls = 0
    total_success = 0

    for name, info in JINWOO_UNIVERSE.items():
        stock_code = info['코드']
        sector = info['업종']
        corp_code = code_map.get(stock_code)
        results[name] = {'업종': sector, 'quarters': {}}

        if not corp_code:
            print(f"  ⚠️ {name}: corp_code 미발견")
            continue

        success_count = 0
        for (y, q, reprt) in quarter_codes:
            total_calls += 1
            fs_list = fetch_full_financials(corp_code, y, reprt, api_key, requests_mod)
            financials = extract_accounts(fs_list)
            key = f"{y}Q{q}"
            if financials:
                results[name]['quarters'][key] = financials
                success_count += 1
                total_success += 1
            time.sleep(0.05)  # rate limiting

        print(f"  {name:14s} {success_count}/{len(quarter_codes)}분기 수집")

    print(f"\n총 {total_success}/{total_calls} 호출 성공 "
          f"({total_success/total_calls*100:.1f}%)")
    return results


def compute_quality_for_quarter(financials_t, financials_t_minus_4q):
    """
    한 분기 시점의 quality 지표 계산.
    GP/Assets: 현재 분기
    Asset Growth (YoY): 현재 분기 vs 4분기 전 동기 자산총계
    """
    if not financials_t:
        return {}
    result = {}

    # GP/Assets
    assets = financials_t.get('자산총계')
    if assets:
        sales = financials_t.get('매출액')
        cogs = financials_t.get('매출원가')
        if sales is not None and cogs is not None:
            result['GP_Assets'] = (sales - cogs) / assets
        else:
            # Fallback: 영업이익 / 자산
            op = financials_t.get('영업이익')
            if op is not None:
                result['GP_Assets'] = op / assets

    # Asset Growth (YoY)
    if financials_t_minus_4q:
        a_prior = financials_t_minus_4q.get('자산총계')
        if assets and a_prior:
            result['Asset_Growth'] = (assets - a_prior) / a_prior

    # ROE 근사 (금융주용)
    profit = financials_t.get('당기순이익')
    if profit is None or profit == 0:
        op = financials_t.get('영업이익')
        if op is not None:
            profit = op * 0.75
    equity = financials_t.get('자기자본총계')
    if profit is not None and equity:
        result['ROE'] = profit / equity

    return result


def post_process(results):
    """
    각 분기별 quality 지표 계산 (시점별, YoY 비교 필요).
    """
    for name, info in results.items():
        quarters_dict = info.get('quarters', {})
        sorted_keys = sorted(quarters_dict.keys())

        quality_by_quarter = {}
        for i, q_key in enumerate(sorted_keys):
            fs_t = quarters_dict[q_key]
            # 4분기 전 동기 찾기
            year, quarter_num = q_key.split('Q')
            year, quarter_num = int(year), int(quarter_num)
            prior_key = f"{year-1}Q{quarter_num}"
            fs_prior = quarters_dict.get(prior_key)

            quality_by_quarter[q_key] = compute_quality_for_quarter(fs_t, fs_prior)

        info['quality_by_quarter'] = quality_by_quarter
    return results


def export_summary(results):
    """사람이 읽는 요약 CSV"""
    rows = []
    for name, info in results.items():
        sector = info.get('업종')
        for q_key, quality in info.get('quality_by_quarter', {}).items():
            rows.append({
                '종목': name,
                '업종': sector,
                '분기': q_key,
                'GP_Assets': round(quality.get('GP_Assets'), 4) if quality.get('GP_Assets') is not None else None,
                'Asset_Growth_%': round(quality.get('Asset_Growth') * 100, 2) if quality.get('Asset_Growth') is not None else None,
                'ROE': round(quality.get('ROE'), 4) if quality.get('ROE') is not None else None,
            })
    df = pd.DataFrame(rows)
    df.to_csv(SUMMARY_CSV, index=False, encoding='utf-8-sig')
    print(f"\n✅ 요약 CSV: {SUMMARY_CSV.name}")
    print(f"  총 {len(df)} 행 (종목 × 분기)")


def save_cache(results):
    payload = {
        'timestamp': datetime.now().isoformat(),
        'universe_size': len(results),
        'data': results,
    }
    TIMESERIES_CACHE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding='utf-8')
    print(f"✅ 시계열 캐시: {TIMESERIES_CACHE.name}")


def main():
    args = parse_args()
    end_year = args.end_year or datetime.now().year
    print("=" * 80)
    print("진우퀀트 — 시계열 quality 데이터 수집")
    print(f"기간: {args.start_year} ~ {end_year}")
    print(f"시간: {datetime.now()}")
    print("=" * 80)

    try:
        results = fetch_quarterly_timeseries(args.start_year, end_year)
        results = post_process(results)
        save_cache(results)
        export_summary(results)
        print("\n" + "=" * 80)
        print("✅ 완료 — backtest_4way_pit.py / backtest_5way_pit.py 실행 가능")
        print("=" * 80)
    except RuntimeError as e:
        print(f"\n❌ 에러: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
