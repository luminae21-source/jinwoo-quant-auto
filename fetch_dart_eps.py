#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
진우퀀트 v3.9 PEAD — DART 분기 지배주주순이익 + 공시일 수집  [PC 실행 전용]

⚠️ 실행 위치: C:\\Users\\긍정적인_삶의자세\\Desktop\\진우퀀트  (OneDrive 경로 금지)
⚠️ 이 스크립트는 DART OpenAPI를 호출한다 → 반드시 진우님 PC에서 실행.
   (샌드박스/Claude 세션에서는 --self-test만 실행 가능)

출력: eps_sue_cache.json
  { 종목명: { 'code': 6자리, 'corp_code': 8자리,
              'quarters': [ {'q':'2023Q1','ni':분기지배주주순이익(원),
                             'announced':'YYYY-MM-DD','rcept_no':...}, ... ] } }

SUE 계산은 score_v39_pead.py가 담당 (이 파일은 데이터 수집만).
production 파일 무수정 — 기존 quality 캐시·fetch와 완전 별개.

사용법 (PC):
  python fetch_dart_eps.py --self-test     # 네트워크 불필요, 변환 로직 검증
  python fetch_dart_eps.py                 # 2020~현재 수집 (첫 실행 5~10분)
  python fetch_dart_eps.py --start-year 2022 --refresh
"""

import argparse
import io
import json
import re
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

BASE = Path(__file__).parent.resolve()
CACHE_FILE = BASE / 'eps_sue_cache.json'
RAW_CACHE_FILE = BASE / 'eps_dart_raw_cache.json'   # API 응답 캐시 (rate limit 보호)

DART_URL = 'https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json'
CORPCODE_URL = 'https://opendart.fss.or.kr/api/corpCode.xml'
REPORT_CODES = [('11013', 'Q1'), ('11012', 'H1'), ('11014', 'Q3'), ('11011', 'FY')]
SLEEP_SEC = 0.8          # 분당 rate limit 보호
RETRY_SLEEP = 65         # status 020 (한도 초과) 시 대기


# ----------------------------------------------------------------------
# API 키 / 종목 / corp_code 로딩 — 전부 관용형 (파일 포맷 자동 감지)
# ----------------------------------------------------------------------
def load_api_key():
    """우선순위: .dart_key → dart_config.json 내 40자 문자열 → 환경변수"""
    f = BASE / '.dart_key'
    if f.exists():
        k = f.read_text(encoding='utf-8').strip()
        if len(k) >= 40:
            return k[:40]
    f = BASE / 'dart_config.json'
    if f.exists():
        try:
            d = json.loads(f.read_text(encoding='utf-8'))
            for v in (d.values() if isinstance(d, dict) else d):
                if isinstance(v, str) and len(v.strip()) == 40:
                    return v.strip()
        except Exception:
            pass
    import os
    k = os.environ.get('DART_API_KEY', '').strip()
    if len(k) == 40:
        return k
    sys.exit('[오류] DART API 키를 찾지 못함 (.dart_key / dart_config.json / env DART_API_KEY)')


def load_universe(codes_arg=None):
    """{종목명: 6자리 종목코드}. 1순위 score_v37 import (Desktop에서 동작), 폴백 --codes"""
    if codes_arg:
        out = {}
        for part in codes_arg.split(','):
            name, code = part.split(':')
            out[name.strip()] = code.strip().zfill(6)
        return out
    try:
        sys.path.insert(0, str(BASE))
        from score_v37 import JINWOO_v37
        return {name: str(info['코드']).zfill(6) for name, info in JINWOO_v37.items()}
    except Exception as e:
        sys.exit(f'[오류] score_v37 import 실패({e}) — --codes "이름:코드,이름:코드" 로 직접 지정')


def load_corp_codes(api_key, universe):
    """6자리 종목코드 → 8자리 DART corp_code.
    1) dart_corp_codes.json 포맷 자동 감지  2) 실패 시 corpCode.xml 다운로드"""
    mapping = {}
    f = BASE / 'dart_corp_codes.json'
    if f.exists():
        try:
            d = json.loads(f.read_text(encoding='utf-8'))
            items = d.values() if isinstance(d, dict) else d
            for it in items:
                if isinstance(it, dict):
                    sc = str(it.get('stock_code', '')).strip().zfill(6)
                    cc = str(it.get('corp_code', '')).strip()
                    if len(cc) == 8 and sc != '000000':
                        mapping[sc] = cc
            if isinstance(d, dict) and not mapping:
                # {종목코드: corp_code} 또는 {이름: corp_code} 형태
                for k, v in d.items():
                    if isinstance(v, str) and len(v.strip()) == 8:
                        mapping[str(k).strip().zfill(6)] = v.strip()
        except Exception:
            pass
    need = [c for c in universe.values() if c not in mapping]
    if need:
        print(f'[corp_code] 로컬 매핑에 {len(need)}개 없음 → corpCode.xml 다운로드')
        import requests
        r = requests.get(CORPCODE_URL, params={'crtfc_key': api_key}, timeout=60)
        zf = zipfile.ZipFile(io.BytesIO(r.content))
        xml = zf.read(zf.namelist()[0]).decode('utf-8')
        for m in re.finditer(
                r'<corp_code>(\d{8})</corp_code>.*?<stock_code>([0-9]{6})</stock_code>',
                xml, re.S):
            mapping[m.group(2)] = m.group(1)
    missing = [n for n, c in universe.items() if c not in mapping]
    if missing:
        sys.exit(f'[오류] corp_code 미해결 종목: {missing}')
    return {name: mapping[code] for name, code in universe.items()}


# ----------------------------------------------------------------------
# 계정 추출 + 누적→분기 변환 (핵심 로직, self-test 대상)
# ----------------------------------------------------------------------
def _to_num(s):
    if s is None:
        return None
    s = str(s).replace(',', '').strip()
    if s in ('', '-'):
        return None
    try:
        return float(s)
    except ValueError:
        return None


def pick_ni_cumulative(rows):
    """fnlttSinglAcntAll 응답 rows에서 '누적 지배주주 당기순이익' 1개 값 선택.
    우선순위: 지배주주 귀속 순이익 → 당기순이익. 포괄손익·주당 항목 제외.
    누적값: thstrm_add_amount 우선, 없으면 thstrm_amount (Q1·FY는 동일).
    반환: (값, rcept_no) 또는 (None, None)"""
    best = None  # (priority, value, rcept_no)
    for r in rows:
        if r.get('sj_div') not in ('IS', 'CIS'):
            continue
        nm = re.sub(r'\s', '', str(r.get('account_nm', '')))
        if '주당' in nm or '포괄' in nm:
            continue
        if '당기순이익' not in nm and '분기순이익' not in nm and '반기순이익' not in nm:
            continue
        if '지배' in nm and '비지배' not in nm:
            pri = 0
        elif '비지배' in nm:
            continue
        else:
            pri = 1
        val = _to_num(r.get('thstrm_add_amount'))
        if val is None:
            val = _to_num(r.get('thstrm_amount'))
        if val is None:
            continue
        cand = (pri, val, r.get('rcept_no'))
        if best is None or cand[0] < best[0]:
            best = cand
    if best is None:
        return None, None
    return best[1], best[2]


def cumulative_to_quarterly(year_data):
    """{'Q1': (cum, rcept), 'H1': ..., 'Q3': ..., 'FY': ...} → 분기값 dict.
    Q1=Q1cum / Q2=H1−Q1 / Q3=Q3cum−H1 / Q4=FY−Q3cum. 누락 분기는 건너뜀."""
    out = {}
    g = {k: v[0] for k, v in year_data.items() if v and v[0] is not None}
    rc = {k: v[1] for k, v in year_data.items() if v}
    if 'Q1' in g:
        out['Q1'] = (g['Q1'], rc.get('Q1'))
    if 'H1' in g and 'Q1' in g:
        out['Q2'] = (g['H1'] - g['Q1'], rc.get('H1'))
    if 'Q3' in g and 'H1' in g:
        out['Q3'] = (g['Q3'] - g['H1'], rc.get('Q3'))
    if 'FY' in g and 'Q3' in g:
        out['Q4'] = (g['FY'] - g['Q3'], rc.get('FY'))
    return out


def rcept_to_date(rcept_no):
    """rcept_no 앞 8자리 = 접수일(YYYYMMDD) → 'YYYY-MM-DD'"""
    s = str(rcept_no or '')
    if len(s) >= 8 and s[:8].isdigit():
        return f'{s[:4]}-{s[4:6]}-{s[6:8]}'
    return None


# ----------------------------------------------------------------------
# DART 호출  [PC 실행]
# ----------------------------------------------------------------------
def fetch_one(api_key, corp_code, year, reprt_code, raw_cache, refresh=False):
    key = f'{corp_code}|{year}|{reprt_code}'
    if not refresh and key in raw_cache:
        return raw_cache[key]
    import requests
    for fs_div in ('CFS', 'OFS'):
        params = {'crtfc_key': api_key, 'corp_code': corp_code,
                  'bsns_year': str(year), 'reprt_code': reprt_code, 'fs_div': fs_div}
        for attempt in range(2):
            resp = requests.get(DART_URL, params=params, timeout=30).json()
            status = resp.get('status')
            if status == '020':           # rate limit
                print(f'  [대기] rate limit — {RETRY_SLEEP}s 휴식')
                time.sleep(RETRY_SLEEP)
                continue
            break
        time.sleep(SLEEP_SEC)
        if status == '000' and resp.get('list'):
            val, rcept = pick_ni_cumulative(resp['list'])
            if val is not None:
                raw_cache[key] = {'ni_cum': val, 'rcept_no': rcept, 'fs_div': fs_div}
                return raw_cache[key]
    raw_cache[key] = None                 # 조회 불가도 캐시 (재호출 방지)
    return None


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--start-year', type=int, default=2020)
    ap.add_argument('--codes', help='폴백: "이름:코드,이름:코드"')
    ap.add_argument('--refresh', action='store_true', help='raw 캐시 무시 재수집')
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    api_key = load_api_key()
    universe = load_universe(args.codes)
    corp_codes = load_corp_codes(api_key, universe)
    end_year = datetime.now().year
    raw_cache = {}
    if RAW_CACHE_FILE.exists() and not args.refresh:
        raw_cache = json.loads(RAW_CACHE_FILE.read_text(encoding='utf-8'))

    print(f'[수집] {len(universe)}종목 × {args.start_year}~{end_year} (캐시 {len(raw_cache)}건 보유)')
    result = {}
    try:
        for name, code in universe.items():
            cc = corp_codes[name]
            quarters = []
            for year in range(args.start_year, end_year + 1):
                ydata = {}
                for reprt, label in REPORT_CODES:
                    got = fetch_one(api_key, cc, year, reprt, raw_cache, args.refresh)
                    ydata[label] = (got['ni_cum'], got['rcept_no']) if got else None
                for q, (ni, rcept) in sorted(cumulative_to_quarterly(ydata).items()):
                    ann = rcept_to_date(rcept)
                    if ann:
                        quarters.append({'q': f'{year}{q}', 'ni': ni,
                                         'announced': ann, 'rcept_no': rcept})
            result[name] = {'code': code, 'corp_code': cc, 'quarters': quarters}
            print(f'  {name}: {len(quarters)}개 분기 (최근 {quarters[-1]["q"] if quarters else "—"})')
    finally:
        RAW_CACHE_FILE.write_text(json.dumps(raw_cache, ensure_ascii=False), encoding='utf-8')

    meta = {'_meta': {'created': datetime.now().isoformat(),
                      'start_year': args.start_year, 'source': 'DART fnlttSinglAcntAll',
                      'note': '지배주주 당기순이익 분기값, announced=rcept_no 접수일 (PIT)'}}
    CACHE_FILE.write_text(json.dumps({**meta, **result}, ensure_ascii=False, indent=1),
                          encoding='utf-8')
    print(f'\n✅ 저장: {CACHE_FILE.name} / raw 캐시 {len(raw_cache)}건')
    print('다음: python score_v39_pead.py')


# ----------------------------------------------------------------------
# self-test (네트워크 불필요 — 샌드박스에서도 실행 가능)
# ----------------------------------------------------------------------
def self_test():
    ok = 0

    # 1) 누적→분기 변환
    yd = {'Q1': (100.0, 'r1'), 'H1': (250.0, 'r2'), 'Q3': (450.0, 'r3'), 'FY': (700.0, 'r4')}
    q = cumulative_to_quarterly(yd)
    assert q['Q1'][0] == 100 and q['Q2'][0] == 150 and q['Q3'][0] == 200 and q['Q4'][0] == 250
    ok += 1
    # 2) 중간 누락 (반기 없음 → Q2·Q3 산출 불가, Q1·Q4 불가/가능 체크)
    q = cumulative_to_quarterly({'Q1': (100.0, 'r1'), 'H1': None,
                                 'Q3': (450.0, 'r3'), 'FY': (700.0, 'r4')})
    assert 'Q2' not in q and 'Q3' not in q and q['Q4'][0] == 250
    ok += 1
    # 3) 음수 분기 (적자 전환)
    q = cumulative_to_quarterly({'Q1': (100.0, 'r1'), 'H1': (40.0, 'r2'),
                                 'Q3': None, 'FY': None})
    assert q['Q2'][0] == -60
    ok += 1
    # 4) rcept_no → 날짜
    assert rcept_to_date('20240515000123') == '2024-05-15'
    assert rcept_to_date(None) is None and rcept_to_date('abc') is None
    ok += 1
    # 5) 계정 선택 — 지배주주 우선
    rows = [
        {'sj_div': 'IS', 'account_nm': '당기순이익', 'thstrm_amount': '1,000',
         'thstrm_add_amount': '2,000', 'rcept_no': 'rA'},
        {'sj_div': 'IS', 'account_nm': '지배기업의 소유주에게 귀속되는 당기순이익',
         'thstrm_amount': '900', 'thstrm_add_amount': '1,800', 'rcept_no': 'rB'},
        {'sj_div': 'CIS', 'account_nm': '총포괄손익', 'thstrm_add_amount': '999', 'rcept_no': 'rC'},
        {'sj_div': 'IS', 'account_nm': '기본주당이익', 'thstrm_add_amount': '5', 'rcept_no': 'rD'},
    ]
    val, rc = pick_ni_cumulative(rows)
    assert val == 1800 and rc == 'rB'
    ok += 1
    # 6) 지배주주 항목 없으면 당기순이익 폴백 / 비지배 제외
    rows = [
        {'sj_div': 'IS', 'account_nm': '비지배지분 당기순이익', 'thstrm_add_amount': '50', 'rcept_no': 'rX'},
        {'sj_div': 'IS', 'account_nm': '당기순이익(손실)', 'thstrm_add_amount': '-1,234', 'rcept_no': 'rY'},
    ]
    val, rc = pick_ni_cumulative(rows)
    assert val == -1234 and rc == 'rY'
    ok += 1
    # 7) 숫자 파싱
    assert _to_num('-12,345') == -12345 and _to_num('-') is None and _to_num('') is None
    ok += 1

    print(f'✅ fetch_dart_eps self-test {ok}/7 통과 (네트워크 미사용)')
    print('   실제 수집은 진우님 PC에서: python fetch_dart_eps.py')


if __name__ == '__main__':
    main()
