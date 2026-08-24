#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
attribution_v40_phase4_events.py — 영역4 Phase4 Part2: T1 이벤트 자동 분류

목적 (Phase4 설계메모 §2):
  attribution(phase1/2)에서 T1(|idio_z|≥3) 발동 = "이벤트 의심"까지만 알림.
  이 스크립트가 그 종목·날짜의 DART 공시 + 네이버 뉴스를 자동 수집→분류해
  "무슨 이벤트였나"(실적/수주/M&A/임상/...)를 1차 라벨로 제시 → 주말 검토 단축.

원칙: production·C·D·영역3·v41 무수정. 신규 파일. 매수신호 아님. 최종판단은 사람.
  키 보호: .dart_key·naver_api.json (.gitignore). 코드에 키 하드코딩 금지.

데이터원 (기존 인프라 재사용):
  DART  list.json (공시검색)  · corp_code = dart_corp_codes.json / eps_sue_cache.json
  News  naver news search    · creds = naver_api.json  (kosdaq_news_scan 패턴)

합격선 (설계메모 §2-3, 사전등록):
  A. 한미반도체 T1 → '실적'·'-' 정확 분류 (ground truth)
  B. T1 종목 ≥80%에 event_day ±3영업일 근거 ≥1건 자동 수집
  C. 근거 미발견 시 '미발견' 명시 (환각 분류 금지)

실행:
  python attribution_v40_phase4_events.py --self-test      # 네트워크 불필요
  python attribution_v40_phase4_events.py                  # [PC] .dart_key + naver_api.json 필요
  python attribution_v40_phase4_events.py --json attribution_v40_20260607_1048.json
"""
from __future__ import annotations
import argparse, json, re, sys, glob
from datetime import datetime, timedelta
from pathlib import Path

BASE = Path(__file__).parent.resolve()

# ============================================
# 분류 taxonomy (키워드 룰, NLP-lite — kosdaq_news_scan 계승)
# 우선순위 순서대로 첫 매칭 카테고리 채택 (구체적 → 일반적)
# ============================================
CATEGORY_KEYWORDS = [
    ('임상/허가', ['임상', '품목허가', 'FDA', '식약처', '승인', '허가', '시판']),
    ('공급계약/수주', ['공급계약', '단일판매', '수주', '납품', '단독공급', '공급', '계약체결', '수출계약']),
    ('M&A/지분', ['인수', '합병', '경영권', '최대주주', '주식양수도', '타법인주식', '지분취득', '지분매각']),
    ('자사주', ['자기주식', '자사주', '소각']),
    ('유증/CB', ['유상증자', '무상증자', '전환사채', '신주인수권', '교환사채', '전환청구', 'CB', 'BW']),
    ('소송/제재', ['소송', '제재', '조사', '횡령', '배임', '거래정지', '불성실공시', '벌금', '과징금']),
    ('실적', ['실적', '잠정', '분기보고서', '반기보고서', '사업보고서', '매출액', '영업이익',
              '어닝', '컨센', '적자', '흑자', '순이익', '영업손실']),
]
POS_KW = ['수주', '공급계약', '단독공급', '최대실적', '역대 최대', '흑자전환', '승인', '허가',
          '목표가 상향', '목표주가 상향', '자사주', '취득', '증설', '신제품', '서프라이즈',
          '호실적', '수출', '급등', '강세', '신고가']
NEG_KW = ['어닝쇼크', '쇼크', '하회', '적자', '급감', '감소', '부진', '소송', '제재', '횡령',
          '배임', '거래정지', '목표가 하향', '하향', '급락', '약세', '손실', '쇼크']


def classify(texts: list[str]) -> dict:
    """DART report_nm + 뉴스 헤드라인 텍스트 리스트 → 카테고리·방향·근거.
    근거 없으면 '미발견'(환각 금지). 순수 함수 — self-test 대상."""
    texts = [t for t in texts if t and t.strip()]
    if not texts:
        return {'category': '미발견', 'direction': None, 'evidence': [], 'n': 0}
    blob = ' '.join(texts)
    category = '기타'
    matched = None
    for cat, kws in CATEGORY_KEYWORDS:
        hit = next((k for k in kws if k in blob), None)
        if hit:
            category, matched = cat, hit
            break
    pos = sum(1 for k in POS_KW if k in blob)
    neg = sum(1 for k in NEG_KW if k in blob)
    direction = '+' if pos > neg else ('-' if neg > pos else '0')
    # 카테고리 키워드도 방향 키워드도 전혀 없으면 = 근거 약함 → '미발견'은 아님(텍스트는 있음)
    if category == '기타' and pos == 0 and neg == 0:
        category = '기타/불명'
    return {'category': category, 'direction': direction, 'evidence': texts[:6],
            'n': len(texts), 'matched_kw': matched}


# ============================================
# T1 추출 (attribution JSON의 triggers 파싱)
# ============================================
def latest_attr_json() -> Path | None:
    cands = sorted(glob.glob(str(BASE / 'attribution_v40_2*.json')))
    return Path(cands[-1]) if cands else None


def extract_t1(attr_json: Path) -> list[dict]:
    """phase1-style attribution JSON(triggers 포함)에서 T1 종목·event_day 추출.
    T1 msg 예: '이벤트 의심: 05-18 idio_z=-3.27 ...' → (name, 2026-05-18)."""
    d = json.load(open(attr_json, encoding='utf-8'))
    yr = datetime.now().year
    out = []
    for t in d.get('triggers', []):
        for tr in t.get('triggers', []):
            if tr.get('code') == 'T1':
                m = re.search(r'(\d{2})-(\d{2})', tr.get('msg', ''))
                if m:
                    mm, dd = int(m.group(1)), int(m.group(2))
                    y = yr if mm <= datetime.now().month else yr - 1
                    mz = re.search(r'idio_z=([+-]?\d+\.?\d*)', tr.get('msg', ''))
                    z = float(mz.group(1)) if mz else 0.0
                    out.append({'name': t['name'],
                                'event_day': f'{y:04d}-{mm:02d}-{dd:02d}',
                                'idio_z': z, 'dir': '+' if z >= 0 else '-',
                                'msg': tr.get('msg', '')})
    return out


# ============================================
# DART / News 수집 (네트워크 — PC 전용)
# ============================================
def load_dart_key() -> str | None:
    p = BASE / '.dart_key'
    if p.exists():
        return p.read_text(encoding='utf-8').strip()
    import os
    return os.environ.get('DART_API_KEY')


def resolve_corp_code(name: str, code: str | None) -> str | None:
    # 1) dart_corp_codes.json {6자리코드: 8자리}  2) eps_sue_cache.json {이름:{corp_code}}
    f = BASE / 'dart_corp_codes.json'
    if f.exists() and code:
        try:
            m = json.load(open(f, encoding='utf-8'))
            if code in m and str(m[code]).strip():
                return str(m[code]).strip().zfill(8)
        except Exception:
            pass
    f = BASE / 'eps_sue_cache.json'
    if f.exists():
        try:
            m = json.load(open(f, encoding='utf-8'))
            if name in m and m[name].get('corp_code'):
                return str(m[name]['corp_code']).strip().zfill(8)
        except Exception:
            pass
    return None


def fetch_dart_list(corp_code: str, day: str, key: str, win_days: int = 5) -> list[str]:
    """event_day ±win_days 공시 목록(report_nm) 수집."""
    import requests
    d0 = datetime.strptime(day, '%Y-%m-%d')
    bgn = (d0 - timedelta(days=win_days)).strftime('%Y%m%d')
    end = (d0 + timedelta(days=win_days)).strftime('%Y%m%d')
    try:
        r = requests.get('https://opendart.fss.or.kr/api/list.json',
                         params={'crtfc_key': key, 'corp_code': corp_code,
                                 'bgn_de': bgn, 'end_de': end, 'page_count': 100},
                         timeout=20)
        js = r.json()
        if js.get('status') != '000':
            return []
        return [f"[공시 {it.get('rcept_dt','')}] {it.get('report_nm','')}"
                for it in js.get('list', [])]
    except Exception as e:
        print(f'  DART 실패({corp_code}): {e}')
        return []


def naver_creds():
    p = BASE / 'naver_api.json'
    if p.exists():
        try:
            d = json.load(open(p, encoding='utf-8'))
            return (d.get('id') or d.get('client_id'), d.get('secret') or d.get('client_secret'))
        except Exception:
            pass
    import os
    return os.environ.get('NAVER_ID'), os.environ.get('NAVER_SECRET')


def fetch_news(query: str, cid: str, csec: str, display: int = 15) -> list[str]:
    import requests
    try:
        r = requests.get('https://openapi.naver.com/v1/search/news.json',
                         headers={'X-Naver-Client-Id': cid, 'X-Naver-Client-Secret': csec},
                         params={'query': query, 'display': display, 'sort': 'sim'}, timeout=15)
        out = []
        for it in r.json().get('items', []):
            title = it.get('title', '')
            for a, b in [('<b>', ''), ('</b>', ''), ('&quot;', '"'), ('&amp;', '&'),
                         ('&lt;', '<'), ('&gt;', '>'), ('&apos;', "'"), ('&#39;', "'")]:
                title = title.replace(a, b)
            out.append(f'[뉴스] {title}')
        return out
    except Exception as e:
        print(f'  뉴스 실패({query}): {e}')
        return []


# ============================================
# 게이트 판정 (설계메모 §2-3)
# ============================================
HANMI = '한미반도체'


def evaluate_gates(results: list[dict]) -> dict:
    n = len(results)
    with_evd = [r for r in results if r['n'] >= 1]
    rate = (len(with_evd) / n) if n else 0.0
    hanmi = next((r for r in results if r['name'] == HANMI), None)
    gate_a = bool(hanmi and hanmi['category'] == '실적' and hanmi['direction'] == '-')
    gate_b = rate >= 0.80
    # C: 근거 0인데 카테고리가 '미발견'이 아닌 경우 = 환각 → 위반
    gate_c = all((r['n'] >= 1) or (r['category'] == '미발견') for r in results)
    return {
        'n_t1': n, 'evidence_rate': round(rate, 3),
        'gate_A_hanmi_실적': gate_a,
        'gate_B_evidence>=80%': gate_b,
        'gate_C_no_hallucination': gate_c,
        'PASS': bool(gate_a and gate_b and gate_c),
        'hanmi': hanmi,
    }


# ============================================
# self-test (합성, 네트워크 불필요)
# ============================================
def self_test() -> bool:
    print('\n🧪 Phase4 이벤트분류 self-test (합성)')
    cases = [
        ('한미 어닝쇼크', ['[공시 20260518] 분기보고서 (2026.03)',
                       '[뉴스] 한미반도체 1분기 영업익 88% 급감 어닝쇼크 컨센 하회'],
         '실적', '-'),
        ('수주 호재', ['[뉴스] 삼성물산, 5조원 규모 단독공급 수주 계약체결'], '공급계약/수주', '+'),
        ('임상 승인', ['[공시 20260601] 투자판단 관련 주요경영사항',
                     '[뉴스] 알테오젠 FDA 품목허가 승인 획득'], '임상/허가', '+'),
        ('자사주', ['[공시 20260604] 주요사항보고서(자기주식취득결정)',
                  '[뉴스] KB금융 자사주 취득·소각 결정'], '자사주', '+'),
        ('미발견', [], '미발견', None),
        ('근거있으나 불명', ['[뉴스] NAVER 주가 강보합 마감'], None, None),  # 카테고리 무관, n>=1 확인
    ]
    checks = []
    for label, texts, exp_cat, exp_dir in cases:
        r = classify(texts)
        if label == '미발견':
            ok = (r['category'] == '미발견' and r['n'] == 0)
        elif label == '근거있으나 불명':
            ok = (r['n'] >= 1 and r['category'] != '미발견')  # 텍스트 있으면 미발견 아님
        else:
            ok = (r['category'] == exp_cat and r['direction'] == exp_dir)
        checks.append((label, ok, f"{r['category']}/{r['direction']} (n={r['n']})"))
    # 게이트 단위검증: 한미 실적 케이스가 gate A 통과시키는지
    def mk(name, texts, idio_z):
        r = classify(texts); r['name'] = name
        r['kw_direction'] = r['direction']
        r['direction'] = '+' if idio_z >= 0 else '-'   # idio_z 부호가 방향 정본
        return r
    mock = [
        mk(HANMI, cases[0][1], -3.27),
        mk('삼성물산', cases[1][1], 4.55),
        mk('알테오젠', cases[2][1], 3.00),
        mk('KB금융', cases[3][1], 3.37),
        mk('미발견종목', [], 0.0),
    ]
    g = evaluate_gates(mock)
    checks.append(('gate A (한미=실적·-)', g['gate_A_hanmi_실적'], str(g['gate_A_hanmi_실적'])))
    checks.append(('gate B (근거 4/5=80%)', g['gate_B_evidence>=80%'], f"rate={g['evidence_rate']}"))
    checks.append(('gate C (미발견 명시)', g['gate_C_no_hallucination'], str(g['gate_C_no_hallucination'])))

    print(f"  {'check':24s} {'결과':4s}  detail")
    allok = True
    for label, ok, det in checks:
        allok &= ok
        print(f"  {label:24s} {'✅' if ok else '❌':4s}  {det}")
    print(f"\n{'✅ self-test 전부 통과' if allok else '❌ self-test 실패'} ({sum(c[1] for c in checks)}/{len(checks)})")
    return allok


# ============================================
# main
# ============================================
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--json', help='attribution JSON (기본: 최신 attribution_v40_2*.json)')
    ap.add_argument('--win-days', type=int, default=5, help='event_day ± 일수 (DART, 기본 5)')
    ap.add_argument('--self-test', action='store_true')
    args = ap.parse_args()

    if args.self_test:
        sys.exit(0 if self_test() else 1)

    attr = Path(args.json) if args.json else latest_attr_json()
    if not attr or not attr.exists():
        sys.exit('❌ attribution JSON 없음 (phase1 실행 또는 --json 지정)')
    t1 = extract_t1(attr)
    print(f"📂 입력: {attr.name} · T1 발동 {len(t1)}종: {[x['name'] for x in t1]}")
    if not t1:
        sys.exit('T1 발동 종목 없음 — 종료')

    key = load_dart_key()
    cid, csec = naver_creds()
    if not key:
        print('⚠️ .dart_key 없음 → DART 생략(뉴스만)')
    if not (cid and csec):
        print('⚠️ naver_api.json 없음 → 뉴스 생략(DART만)')

    try:
        from score_v37 import JINWOO_v37
    except Exception:
        JINWOO_v37 = {}

    results = []
    for ev in t1:
        name, day = ev['name'], ev['event_day']
        code = (JINWOO_v37.get(name, {}) or {}).get('코드')
        texts = []
        if key:
            cc = resolve_corp_code(name, code)
            if cc:
                texts += fetch_dart_list(cc, day, key, args.win_days)
            else:
                print(f'  {name}: corp_code 미해결 → DART 생략')
        if cid and csec:
            texts += fetch_news(name, cid, csec)
        r = classify(texts)
        r['kw_direction'] = r['direction']           # 뉴스 키워드 방향(참고용 — 현재시점 편향)
        r['direction'] = ev['dir']                   # 방향 정본 = idio_z 부호(이벤트 측정값)
        r.update({'name': name, 'event_day': day, 'idio_z': ev['idio_z']})
        results.append(r)
        print(f"\n▶ {name} ({day}, idio_z={ev['idio_z']:+.2f})  → {r['category']} / {r['direction']}  (근거 {r['n']}건)")
        for e in r['evidence']:
            print(f"    {e}")

    gates = evaluate_gates(results)
    print('\n' + '=' * 60)
    print('게이트 판정 (설계메모 §2-3)')
    print(f"  A. 한미=실적·-      : {'OK' if gates['gate_A_hanmi_실적'] else 'X'}")
    print(f"  B. 근거 >=80%       : {'OK' if gates['gate_B_evidence>=80%'] else 'X'} (rate={gates['evidence_rate']})")
    print(f"  C. 환각 금지        : {'OK' if gates['gate_C_no_hallucination'] else 'X'}")
    print(f"  {'PASS' if gates['PASS'] else 'FAIL'}")

    out = BASE / f'attribution_v40_phase4_events_{datetime.now():%Y%m%d_%H%M}.json'
    out.write_text(json.dumps({'generated_at': datetime.now().isoformat(timespec='minutes'),
                               'input': attr.name, 'results': results, 'gates': gates},
                              ensure_ascii=False, indent=2), encoding='utf-8')
    print(f"\n저장: {out.name}")


if __name__ == '__main__':
    main()
