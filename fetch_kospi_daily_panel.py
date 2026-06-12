#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_kospi_daily_panel.py — [PC 실행] KRX 일별 가격 패널 수집(FDR)
무수정: production·C·D·영역3·v41 손대지 않음. 후속 백테스트(per-stock MA200·만기재검증) 공용 입력.

받는 것: KOSPI 지수(KS11) · KOSPI200(KS200) · 보유 18종 · KODEX인버스(114800) 일별 종가.
산출: kospi_daily_panel.csv  (Date + 각 코드 종가 wide)

사용(진우 PC, Desktop\진우퀀트):
  pip install finance-datareader pandas
  python fetch_kospi_daily_panel.py
  python fetch_kospi_daily_panel.py --years 7      # 기간 조정(기본 7년)
오프라인 점검:
  python fetch_kospi_daily_panel.py --self-test
"""
import sys
from pathlib import Path
from datetime import date, timedelta

BASE = Path(__file__).parent.resolve()

# 보유 18종 (ma200_regime_check.py HOLD와 동일)
HOLD = [("삼양식품", "003230"), ("두산에너빌리티", "034020"), ("NH투자증권", "005940"),
        ("ISC", "095340"), ("알테오젠", "196170"), ("한화에어로", "012450"),
        ("한미반도체", "042700"), ("SK하이닉스", "000660"), ("삼성물산", "028260"),
        ("삼성전자", "005930"), ("NAVER", "035420"), ("아모레퍼시픽", "090430"),
        ("KT&G", "033780"), ("KB금융", "105560"), ("삼성SDI", "006400"),
        ("기아", "000270"), ("카카오", "035720"), ("LIG넥스원", "079550")]
INDICES = [("KOSPI", "KS11"), ("KOSPI200", "KS200"), ("KODEX인버스", "114800")]


def fetch(years=7):
    import FinanceDataReader as fdr
    import pandas as pd
    end = date.today()
    start = end - timedelta(days=int(years * 365.25))
    s = start.strftime("%Y-%m-%d")
    df = pd.DataFrame()
    targets = INDICES + HOLD
    ok, fail = 0, []
    for name, code in targets:
        try:
            ser = fdr.DataReader(code, s)["Close"].rename(code)
            df = pd.concat([df, ser], axis=1)
            ok += 1
            print("  fetched %-10s %s (%d rows)" % (name, code, ser.dropna().shape[0]))
        except Exception as e:
            fail.append((name, code, str(e)))
            print("  [FAIL] %-10s %s -> %s" % (name, code, e))
    df.index.name = "Date"
    out = BASE / "kospi_daily_panel.csv"
    df.to_csv(out, encoding="utf-8-sig")
    print("\n저장: %s  shape=%s" % (out.name, df.shape))
    print("기간 %s ~ %s" % (df.index.min().date() if len(df) else "-", df.index.max().date() if len(df) else "-"))
    if fail:
        print("실패 %d건: %s" % (len(fail), [f[0] for f in fail]))
    # 즉석 sanity: KOSPI 최근값 + 보유 결측
    if "KS11" in df.columns:
        print("KOSPI 최근 종가: %.1f" % df["KS11"].dropna().iloc[-1])
    miss = [c for _, c in HOLD if c not in df.columns or df[c].dropna().empty]
    print("보유 결측: %s" % (miss if miss else "없음(18/18 OK)"))
    print("\n→ 이 콘솔 출력 전체를 Claude에 붙여주세요. (다음: per-stock MA200 백테스트 실행)")


def self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print("  [%s] %s" % ("OK" if c else "FAIL", n))
    chk("보유 18종", len(HOLD) == 18)
    chk("코드 6자리", all(len(c) == 6 for _, c in HOLD))
    chk("지수 KS11·KS200 포함", {"KS11", "KS200"} <= {c for _, c in INDICES})
    chk("중복 코드 없음", len({c for _, c in HOLD + INDICES}) == len(HOLD) + len(INDICES))
    print("self-test: %d/%d" % (ok, tot))
    return ok == tot


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        yrs = 7
        if "--years" in sys.argv:
            try: yrs = float(sys.argv[sys.argv.index("--years") + 1])
            except (ValueError, IndexError): pass
        try:
            fetch(yrs)
        except Exception:
            import traceback
            print("\n===== [에러] 아래를 복사해 주세요 =====")
            traceback.print_exc()
            print("\n힌트: 'pip install finance-datareader pandas' 먼저. 회사망 차단 시 개인망에서.")
