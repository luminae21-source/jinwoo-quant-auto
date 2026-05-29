#!/usr/bin/env python3
"""
진우퀀트 v3.8 — DART API quality 데이터 수집 (requests 직접 호출)

OpenDartReader 미사용 — Python 3.14 호환성 이슈 우회.
표준 라이브러리 + requests + pandas 만 사용.

목적:
  - v3.8.1 GP/Total Assets (Novy-Marx 2013) — 16개 제조업 종목
  - v3.8.2 Asset Growth (Cooper-Gulen-Schill 2008) — 16개 제조업 종목
  - 금융주 별도 quality proxy (GPT 검증 반영, 2026-05-28)
    * KB금융 (105560): 은행 → ROE + 충당금 + 영업이익률
    * NH투자증권 (005940): 증권사 → ROE + 영업이익률

학술 근거:
  - S1 Novy-Marx (2013) JFE 108: GP = (매출액 - 매출원가) / 자산총계
  - S2 Cooper-Gulen-Schill (2008) JF 63(4): AG = (자산_t - 자산_t-1) / 자산_t-1
  - S4 안제욱·김규영 (2014): 한국 GP 임계값
  - S5 노지혜 외 (2023): 한국 8요인 25년 robust
  - GPT 검증 (2026-05-28): 금융주 별도 quality proxy

사용법:
  1. https://opendart.fss.or.kr 에서 무료 API key 발급
  2. dart_config.json 에 {"api_key": "..."} 저장
     또는 환경변수 DART_API_KEY 설정
  3. python fetch_dart_quality.py

출력:
  - dart_corp_codes.json — DART 회사 코드 매핑 (최초 1회 자동 다운로드)
  - quality_data_cache.json — 18종목 분기 재무 + 계산된 quality 지표
  - quality_summary.csv — 사람이 읽을 수 있는 요약
"""

import sys
import os
import io
import json
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime
from pathlib import Path

import pandas as pd

BASE = Path(__file__).parent.resolve()
CACHE_FILE = BASE / 'quality_data_cache.json'
SUMMARY_CSV = BASE / 'quality_summary.csv'
CONFIG_FILE = BASE / 'dart_config.json'
CORP_CODE_CACHE = BASE / 'dart_corp_codes.json'

DART_BASE = "https://opendart.fss.or.kr/api"


# ============================================
# 18종목 universe
# ============================================
JINWOO_UNIVERSE = {
    # 제조업 16종목 — GP/Assets + Asset Growth
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
    # 금융업 2종목 — 별도 quality proxy
    'KB금융':         {'코드': '105560', '업종': '은행'},
    'NH투자증권':     {'코드': '005940', '업종': '증권사'},
}


# ============================================
# 의존성 확보
# ============================================
def _ensure_requests():
    try:
        import requests
        return requests
    except ImportError:
        print("⚠️ requests 설치 중...")
        import subprocess
        subprocess.run(
            [sys.executable, '-m', 'pip', 'install', '-q', 'requests'],
            check=True
        )
        import importlib
        importlib.invalidate_caches()
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


# ============================================
# DART corp_code 매핑 (최초 1회 다운로드 + 캐시)
# ============================================
def get_corp_code_map(api_key, requests_mod):
    """
    DART corpCode.xml 다운로드 → stock_code → corp_code 매핑 생성.
    최초 1회만 실행, 이후 캐시 사용.
    """
    if CORP_CODE_CACHE.exists():
        return json.loads(CORP_CODE_CACHE.read_text(encoding='utf-8'))

    print("📥 DART corp_code 매핑 다운로드 중...")
    response = requests_mod.get(
        f"{DART_BASE}/corpCode.xml",
        params={'crtfc_key': api_key},
        timeout=30
    )
    response.raise_for_status()

    # ZIP 파일 내 CORPCODE.xml 추출
    with zipfile.ZipFile(io.BytesIO(response.content)) as zf:
        xml_data = zf.read('CORPCODE.xml')

    root = ET.fromstring(xml_data)
    code_map = {}
    for company in root.findall('list'):
        stock_code = (company.findtext('stock_code') or '').strip()
        corp_code = (company.findtext('corp_code') or '').strip()
        if stock_code and corp_code and stock_code != ' ':
            code_map[stock_code] = corp_code

    CORP_CODE_CACHE.write_text(
        json.dumps(code_map, ensure_ascii=False),
        encoding='utf-8'
    )
    print(f"✅ corp_code 매핑 캐시 저장 ({len(code_map)}개 상장사)")
    return code_map


# ============================================
# 분기 재무제표 수집 — 전체 재무제표 API
# ============================================
def fetch_full_financials(corp_code, year, reprt_code, api_key, requests_mod):
    """
    DART fnlttSinglAcntAll.json 호출 → 전체 재무제표.
    reprt_code: 11013=1Q, 11012=반기, 11014=3Q, 11011=사업보고서(연간)
    """
    params = {
        'crtfc_key': api_key,
        'corp_code': corp_code,
        'bsns_year': str(year),
        'reprt_code': reprt_code,
        'fs_div': 'CFS',  # 연결재무제표 (없으면 OFS 별도)
    }
    try:
        response = requests_mod.get(
            f"{DART_BASE}/fnlttSinglAcntAll.json",
            params=params, timeout=15
        )
        response.raise_for_status()
        data = response.json()

        if data.get('status') != '000':
            # CFS 없으면 OFS (별도) 재시도
            if data.get('status') == '013':  # 조회된 데이터 없음
                params['fs_div'] = 'OFS'
                response = requests_mod.get(
                    f"{DART_BASE}/fnlttSinglAcntAll.json",
                    params=params, timeout=15
                )
                data = response.json()
                if data.get('status') != '000':
                    return None
            else:
                return None

        return data.get('list', [])
    except Exception as e:
        print(f"  ⚠️ API 호출 실패: {e}")
        return None


def extract_accounts(fs_list):
    """
    전체 재무제표 list에서 주요 계정 추출.

    개선 (v2): XBRL account_id 우선 매핑 → account_nm fallback.
    회사마다 다른 한글 계정과목 표기 흡수.
    """
    if not fs_list:
        return {}

    # XBRL account_id → 표준 이름 (회사 무관하게 일관됨)
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

    # account_nm 표기 다양성 흡수
    NM_MAP = {
        '매출액': '매출액', '수익(매출액)': '매출액', '매출': '매출액',
        '영업수익': '영업수익',  # 금융주
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
        account_id = (item.get('account_id') or '').strip()
        account_nm = (item.get('account_nm') or '').strip()
        amount_str = item.get('thstrm_amount', '')

        try:
            amount = float(str(amount_str).replace(',', '')) if amount_str else 0
        except (ValueError, TypeError):
            continue

        # 1차: account_id 우선 (XBRL 표준)
        std_name = ID_MAP.get(account_id)
        # 2차: account_nm fallback
        if std_name is None:
            std_name = NM_MAP.get(account_nm)

        if std_name and std_name not in result:
            result[std_name] = amount

        # 영업수익은 별도 보존 (금융주에서 매출액 대체 가능)
        if account_nm == '영업수익' and '영업수익' not in result:
            result['영업수익'] = amount
            # 매출액 없으면 영업수익을 매출액으로 (IT서비스·금융주)
            if '매출액' not in result:
                result['매출액'] = amount

    return result


# ============================================
# Quality 지표 계산
# ============================================
def compute_gp_assets(financials):
    """
    GP/Total Assets — Novy-Marx 2013 (primary) + fallback.

    Primary: (매출액 - 매출원가) / 자산총계
    Fallback: 영업이익 / 자산총계 (IT서비스·금융주 — 매출원가 미분류 시)
              노지혜 외 2023 한국 8요인 "수익성" 측정과 동일
    """
    if not financials:
        return None
    assets = financials.get('자산총계')
    if not assets:
        return None

    sales = financials.get('매출액')
    cogs = financials.get('매출원가')

    # Primary: Novy-Marx GP
    if sales is not None and cogs is not None:
        return (sales - cogs) / assets

    # Fallback: Operating Profit on Assets (한국 robust)
    op_profit = financials.get('영업이익')
    if op_profit is not None:
        return op_profit / assets

    return None


def compute_asset_growth(current, prior_year):
    """Asset Growth (YoY) — Cooper-Gulen-Schill 2008"""
    if not current or not prior_year:
        return None
    a_t = current.get('자산총계')
    a_t1 = prior_year.get('자산총계')
    if not a_t or not a_t1:
        return None
    return (a_t - a_t1) / a_t1


def compute_roe(financials):
    """ROE 연간 근사 — 금융주 공통"""
    if not financials:
        return None
    # 당기순이익 우선, 없으면 영업이익 * (1 - 법인세율 대략 0.25)
    profit = financials.get('당기순이익')
    if profit is None or profit == 0:
        op_profit = financials.get('영업이익')
        if op_profit is not None:
            profit = op_profit * 0.75  # 법인세 후 추정
    if profit is None:
        return None
    equity = financials.get('자기자본총계')
    if not equity:
        return None
    return profit / equity


def compute_operating_margin(financials):
    """영업이익률"""
    if not financials:
        return None
    profit = financials.get('영업이익')
    sales = financials.get('영업수익') or financials.get('매출액')
    if profit is None or not sales:
        return None
    return profit / sales


def compute_financial_quality(financials, sector):
    """
    금융주 quality proxy 통합
    은행: ROE * 0.5 + 영업이익률 * 0.5
    증권사: ROE * 0.5 + 영업이익률 * 0.5
    """
    if not financials:
        return None
    roe = compute_roe(financials)
    op_margin = compute_operating_margin(financials)
    if roe is None or op_margin is None:
        return None
    return roe * 0.5 + op_margin * 0.5


# ============================================
# 18종목 일괄 수집
# ============================================
def fetch_all_quality(year=None):
    """18종목의 최근 사업보고서(연간) quality 지표 일괄 수집"""
    if year is None:
        year = datetime.now().year - 1  # 전년도 사업보고서 (가장 안정적)

    requests_mod = _ensure_requests()
    api_key = _get_api_key()
    if not api_key:
        raise RuntimeError(
            f"DART API key 미설정. {CONFIG_FILE} 에 "
            '{"api_key": "..."} 저장 또는 환경변수 DART_API_KEY 설정. '
            "발급: https://opendart.fss.or.kr"
        )

    print(f"\n📊 DART quality 데이터 수집 ({year} 사업보고서)")
    print("=" * 70)

    # corp_code 매핑 확보
    code_map = get_corp_code_map(api_key, requests_mod)

    results = {}

    for name, info in JINWOO_UNIVERSE.items():
        stock_code = info['코드']
        sector = info['업종']
        corp_code = code_map.get(stock_code)

        print(f"\n  {name:14s} ({stock_code}) [{sector}]")

        if not corp_code:
            print(f"    ⚠️ corp_code 미발견")
            results[name] = {'업종': sector, '오류': 'corp_code 미발견'}
            continue

        # 당해년도 사업보고서 (연간)
        latest_fs_list = fetch_full_financials(
            corp_code, year, '11011', api_key, requests_mod
        )
        if not latest_fs_list:
            # 사업보고서 없으면 3분기 시도
            latest_fs_list = fetch_full_financials(
                corp_code, year, '11014', api_key, requests_mod
            )

        # 전년도 사업보고서 (Asset Growth용)
        prior_fs_list = fetch_full_financials(
            corp_code, year - 1, '11011', api_key, requests_mod
        )

        latest_fs = extract_accounts(latest_fs_list)
        prior_fs = extract_accounts(prior_fs_list)

        # 업종별 quality 계산
        quality = {
            '기준연도': year,
            '업종': sector,
            '계정수': len(latest_fs),
        }

        if sector == '제조업':
            quality['GP_Assets'] = compute_gp_assets(latest_fs)
            quality['Asset_Growth'] = compute_asset_growth(latest_fs, prior_fs)
            print(f"    GP/Assets   : {quality['GP_Assets']}")
            print(f"    Asset Growth: {quality['Asset_Growth']}")
        else:  # 은행 or 증권사
            quality['Financial_Quality'] = compute_financial_quality(latest_fs, sector)
            quality['ROE_approx'] = compute_roe(latest_fs)
            quality['Op_Margin'] = compute_operating_margin(latest_fs)
            print(f"    Quality     : {quality['Financial_Quality']}")
            print(f"    ROE         : {quality['ROE_approx']}")
            print(f"    Op Margin   : {quality['Op_Margin']}")

        # 원본 재무도 저장 (디버깅용)
        quality['_raw_latest'] = latest_fs
        quality['_raw_prior'] = prior_fs

        results[name] = quality

    return results


# ============================================
# 캐시 + 요약
# ============================================
def save_cache(results):
    payload = {
        'timestamp': datetime.now().isoformat(),
        'universe_size': len(results),
        '제조업': sum(1 for v in results.values() if v.get('업종') == '제조업'),
        '은행': sum(1 for v in results.values() if v.get('업종') == '은행'),
        '증권사': sum(1 for v in results.values() if v.get('업종') == '증권사'),
        'data': results,
    }
    CACHE_FILE.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, default=str),
        encoding='utf-8'
    )
    print(f"\n✅ 캐시 저장: {CACHE_FILE.name}")


def export_summary_csv(results):
    rows = []
    for name, q in results.items():
        rows.append({
            '종목': name,
            '업종': q.get('업종'),
            '연도': q.get('기준연도'),
            'GP_Assets': round(q['GP_Assets'], 4) if q.get('GP_Assets') is not None else None,
            'Asset_Growth_%': round(q['Asset_Growth'] * 100, 2) if q.get('Asset_Growth') is not None else None,
            'Financial_Quality': round(q['Financial_Quality'], 4) if q.get('Financial_Quality') is not None else None,
            'ROE_%': round(q['ROE_approx'] * 100, 2) if q.get('ROE_approx') is not None else None,
            'Op_Margin_%': round(q['Op_Margin'] * 100, 2) if q.get('Op_Margin') is not None else None,
        })
    df = pd.DataFrame(rows)
    df.to_csv(SUMMARY_CSV, index=False, encoding='utf-8-sig')
    print(f"✅ 요약 CSV: {SUMMARY_CSV.name}")
    print("\n" + df.to_string(index=False))


# ============================================
# main
# ============================================
def main():
    print("=" * 70)
    print("진우퀀트 v3.8 — DART quality 데이터 수집 (직접 API)")
    print(f"시간: {datetime.now()}")
    print("=" * 70)

    try:
        results = fetch_all_quality()
        save_cache(results)
        export_summary_csv(results)
        print("\n" + "=" * 70)
        print("✅ 완료 — score_v38_1.py 실행 가능")
        print("=" * 70)
    except RuntimeError as e:
        print(f"\n❌ 에러: {e}")
        sys.exit(1)


if __name__ == '__main__':
    main()
