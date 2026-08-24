"""
영역 1 신규 후보 실데이터 IC 측정 — 실행 스크립트
=================================================
같은 폴더(진우퀀트)에 factor_data_loader.py, factor_diagnosis.py 와 함께 두고:

    pip install finance-datareader pandas numpy        # 최초 1회
    python run_factor_ic.py                            # 실행

* PowerShell/터미널에 코드를 붙여넣지 말고, 이 '파일'을 python 으로 실행하세요.
"""
import factor_data_loader as L

# ─────────────────────────────────────────────────────────────────────
# ← 실제 v3.6 유니버스 18종목으로 채우세요 ("종목코드": "이름")
UNIVERSE = {
    "005930": "삼성전자",
    "006400": "삼성SDI",
    "035420": "NAVER",
    "033780": "KT&G",
    # "000660": "SK하이닉스",
    # ... 나머지 종목 추가 ...
}

DART_KEY = "2ead66e0090fb60f2d3e169942ddf7c75f0d0feb"   # OpenDART 인증키 (외부 공유 주의)

START, END = "2018-01-01", "2026-05-31"   # SUE 워밍업 위해 분석구간보다 2~3년 일찍
# 기존 score 팩터값 CSV (date,ticker,factor,value) 있으면 경로 지정 → G3/G4 직교·정제 작동
EXISTING_CSV = None
# ─────────────────────────────────────────────────────────────────────


def main():
    if len(UNIVERSE) < 10:
        print(f"⚠ UNIVERSE 가 {len(UNIVERSE)}종목뿐 — IC는 종목수가 충분해야 의미가 있습니다.")
        print("  일단 실행은 되지만, 실제 18종목으로 채운 뒤 결과를 신뢰하세요.\n")
    print(f"데이터 적재 중… {len(UNIVERSE)}종목, {START}~{END} (DART 호출에 1~2분 소요 가능)")
    close, candidates, fwd, existing = L.build_factor_panel_fdr_dart(
        UNIVERSE, START, END, dart_key=DART_KEY, existing_csv=EXISTING_CSV)
    print(f"가격 {close.shape} | 후보 {list(candidates)} | "
          f"기존팩터 {list(existing) if existing else '미연결(G3/G4 생략)'}\n")
    L.run_factor_diagnosis(close, candidates, fwd, existing)


if __name__ == "__main__":
    main()
