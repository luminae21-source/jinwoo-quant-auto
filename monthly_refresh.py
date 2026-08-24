#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""진우퀀트 월간 갱신 — 6단계 순차 실행 (진우퀀트_월간갱신.bat에서 호출).
수집(pykrx) → 분석(오프라인) → 화면 생성. 한 단계 실패해도 다음 진행."""
import subprocess, sys, pathlib, datetime

BASE = pathlib.Path(__file__).parent.resolve()
STEPS = [
    ("워치리스트 일봉 수집 (pykrx·KRX로그인)", ["fetch_watchlist_daily.py"]),
    ("attribution 일봉 수집 (KOSPI지수+18종+섹터ETF)", ["fetch_attribution_daily.py"]),
    ("진입 5단계 산출 (관찰만/셋업/임박/돌파확인)", ["watchlist_states.py"]),
    ("attribution 2팩터 경보 (T2 진성/T3 섹터동조)", ["attribution_v40_phase2.py", "--save-json", "--save-html"]),
    ("투자보드 생성 (실데이터)", ["make_투자보드.py"]),
    ("월간 단일화면 생성", ["make_월간화면.py"]),
]


def main():
    print("=" * 62)
    print("  진우퀀트 월간 갱신 시작 —", datetime.datetime.now().strftime("%Y-%m-%d %H:%M"))
    print("=" * 62)
    results = []
    for i, (name, cmd) in enumerate(STEPS, 1):
        print("\n[%d/%d] %s ..." % (i, len(STEPS), name))
        try:
            r = subprocess.run([sys.executable] + cmd, cwd=str(BASE))
            ok = (r.returncode == 0)
        except Exception as e:
            print("   실행 오류:", e); ok = False
        results.append((name, ok))
        print("   -> " + ("완료" if ok else "실패"))
    print("\n" + "=" * 62)
    print("  결과 요약")
    print("=" * 62)
    for name, ok in results:
        print(("  [OK]  " if ok else "  [X]   ") + name)
    fails = [n for n, ok in results if not ok]
    if fails:
        print("\n  ※ 실패 단계 있음 — pykrx 로그인/네트워크 확인.")
        print("    (데이터 수집 실패해도 화면은 직전 데이터로 생성됨)")
    else:
        print("\n  전부 완료. 투자보드/월간화면 갱신됨.")
        print("  폰에서 보려면 진우퀀트_월간_단일화면.html을 카톡 '나에게 보내기'.")


if __name__ == "__main__":
    main()
