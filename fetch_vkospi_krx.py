#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""진짜 VKOSPI 일별 종가 수집 → vkospi_daily.csv (Date,VKOSPI).
pykrx엔 변동성지수가 없음(regime cache vol_is_vkospi=false로 확인). 경로 2개:

  [권장·확실] 수동 1회: data.krx.co.kr → 통계 → 지수 → 변동성지수 → 기간 설정 → CSV 다운로드
             → python fetch_vkospi_krx.py --manual 다운받은파일.csv
  [자동·best-effort] python fetch_vkospi_krx.py            (OTP 후보 bld 순차 시도)
             실패 시: KRX 화면에서 CSV 버튼 누를 때 F12 네트워크탭 generate.cmd의 bld 값 복사
             → python fetch_vkospi_krx.py --bld "dbms/MDC/STAT/standard/MDCSTATXXXXX"

검증: 값 범위 5~150 & 행수 ≥ 200 이어야 저장 (VKOSPI 스케일 sanity).
"""
import argparse, io, sys
from pathlib import Path
import pandas as pd

OUT = Path(__file__).parent / 'vkospi_daily.csv'
HEADERS = {"User-Agent": "Mozilla/5.0",
           "Referer": "http://data.krx.co.kr/contents/MDC/MDI/mdiLoader/index.cmd"}
GEN = "http://data.krx.co.kr/comm/fileDn/GenerateOTP/generate.cmd"
DL = "http://data.krx.co.kr/comm/fileDn/download_csv/download.cmd"
# KRX 화면 개편에 따라 바뀔 수 있는 bld 후보들 (지수 시세/추이 계열)
BLD_CANDIDATES = ["dbms/MDC/STAT/standard/MDCSTAT00301",
                  "dbms/MDC/STAT/standard/MDCSTAT01301",
                  "dbms/MDC/STAT/standard/MDCSTAT00601"]


def _normalize(df):
    """KRX CSV(어떤 형식이든) → [Date, VKOSPI]. 날짜열+종가열 자동 탐색."""
    df.columns = [str(c).strip().lstrip('﻿') for c in df.columns]
    date_col = next((c for c in df.columns if ('일자' in c or 'date' in c.lower() or '날짜' in c)), df.columns[0])
    val_col = next((c for c in df.columns if '종가' in c or '지수' in c or 'close' in c.lower()), None)
    if val_col is None:   # 숫자 열 중 VKOSPI 범위(8~80)에 드는 첫 열
        for c in df.columns:
            v = pd.to_numeric(df[c].astype(str).str.replace(',', ''), errors='coerce')
            if v.notna().mean() > 0.9 and v.between(5, 150).mean() > 0.9:
                val_col = c; break
    if val_col is None:
        raise ValueError(f"VKOSPI 값 열을 못 찾음. 열: {list(df.columns)}")
    out = pd.DataFrame({
        'Date': pd.to_datetime(df[date_col].astype(str).str.replace('/', '-'), errors='coerce'),
        'VKOSPI': pd.to_numeric(df[val_col].astype(str).str.replace(',', ''), errors='coerce')})
    out = out.dropna().sort_values('Date').reset_index(drop=True)
    return out


def _validate_and_save(out):
    ok_range = out['VKOSPI'].between(5, 150).mean() > 0.95
    if len(out) < 200 or not ok_range:
        raise ValueError(f"sanity 실패: 행수={len(out)}, 범위적합={ok_range:.0%} → VKOSPI가 아닐 수 있음")
    out.to_csv(OUT, index=False, encoding='utf-8')
    print(f"[OK] {OUT.name} 저장: {len(out)}행, {out['Date'].min().date()}~{out['Date'].max().date()}, "
          f"최근값 {out['VKOSPI'].iloc[-1]:.2f}")


def _read_any(path):
    last_err = None
    for enc in ('utf-8-sig', 'euc-kr', 'cp949', 'utf-8'):
        try:
            return _normalize(pd.read_csv(path, encoding=enc))
        except Exception as e:
            last_err = e
    raise SystemExit(f"[실패] {path} 파싱 불가: {last_err}")


def from_manual(paths):
    """여러 CSV(기간 분할 다운로드)도 병합. 예: --manual a.csv b.csv c.csv"""
    parts = [_read_any(p) for p in paths]
    out = pd.concat(parts).drop_duplicates('Date').sort_values('Date').reset_index(drop=True)
    _validate_and_save(out)


def from_krx_otp(start, end, bld=None):
    import requests
    blds = [bld] if bld else BLD_CANDIDATES
    for b in blds:
        try:
            params = {"bld": b, "locale": "ko_KR",
                      "tboxindIdx_finder_drvprodidx0_0": "변동성지수",
                      "indIdx": "5", "indIdx2": "300",
                      "indTpCd": "5", "idxIndCd": "300",
                      "strtDd": start.replace('-', ''), "endDd": end.replace('-', ''),
                      "csvxls_isNo": "false"}
            otp = requests.post(GEN, params=params, headers=HEADERS, timeout=15).text
            raw = requests.post(DL, data={"code": otp}, headers=HEADERS, timeout=20).content
            df = pd.read_csv(io.BytesIO(raw), encoding='euc-kr')
            out = _normalize(df)
            _validate_and_save(out)
            print(f"  (성공한 bld: {b} — 다음부터 --bld 로 고정 가능)")
            return
        except Exception as e:
            print(f"  bld {b} 실패: {str(e)[:80]}")
    print("\n[자동 실패] 수동 경로를 쓰세요 (2분):")
    print("  1) data.krx.co.kr → 통계 → 지수 → 변동성지수 → 기간 2020-06-01~오늘 → CSV 다운로드")
    print("  2) python fetch_vkospi_krx.py --manual <다운받은파일.csv>")
    print("  (또는 CSV 버튼 누를 때 F12 네트워크탭 generate.cmd의 bld 복사 → --bld 전달)")
    sys.exit(1)


def _selftest():
    df = pd.DataFrame({'일자': ['2024/01/02', '2024/01/03'] * 150,
                       '종가': [18.5, 22.1] * 150, '대비': [0.1, -0.2] * 150})
    out = _normalize(df)
    assert list(out.columns) == ['Date', 'VKOSPI'] and out['VKOSPI'].between(5, 150).all()
    # 열 이름이 달라도 범위로 탐색
    df2 = pd.DataFrame({'기준일': ['2024-01-02'] * 250, '값': [25.0] * 250})
    out2 = _normalize(df2)
    assert len(out2) == 250
    print("[OK] fetch_vkospi self-test 통과 (normalize·범위탐색)")


if __name__ == '__main__':
    ap = argparse.ArgumentParser()
    ap.add_argument('--manual', nargs='+'); ap.add_argument('--bld')
    ap.add_argument('--start', default='2020-06-01'); ap.add_argument('--end', default='2026-06-30')
    ap.add_argument('--selftest', action='store_true')
    a, _ = ap.parse_known_args()
    try:
        if a.selftest: _selftest()
        elif a.manual: from_manual(a.manual)
        else: from_krx_otp(a.start, a.end, a.bld)
    except SystemExit: raise
    except Exception:
        import traceback
        print("\n===== [에러] 아래 내용을 복사해 주세요 ====="); traceback.print_exc()
