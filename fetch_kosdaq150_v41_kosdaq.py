"""
fetch_kosdaq150_v41_kosdaq.py — v4.1 KOSDAQ선정 모듈 전용 (kosdaq_sel)
KOSDAQ150 공식지수 시계열 확보 → 합격선 판정 base 교체용 (진우 결정 ①, 2026-06-06).

[PC 실행]  샌드박스는 KRX 네트워크 차단 + pykrx/FDR 미설치라 여기서 못 받음.
무수정 원칙: production·C(v39_pead)·D(v40_regime)·영역3 파일 손대지 않음. 신규 파일.

산출:
  kosdaq150_index.csv     (date, close)            — 일간
  kosdaq150_monthly.csv   (date=월말, close, ret)  — 백테스트 월리밸과 정렬

사용:
  python fetch_kosdaq150_v41_kosdaq.py            # 실제 수집
  python fetch_kosdaq150_v41_kosdaq.py --self-test # 네트워크 없이 로직 점검
"""
import sys, datetime as dt

START, END = "2019-12-01", "2026-06-30"   # 가격패널(2019-12~)·백테스트(2021-05~2026-05) 포괄
OUT_DAILY   = "kosdaq150_index.csv"
OUT_MONTHLY = "kosdaq150_monthly.csv"
# 판정 윈도우(현 백테스트와 동일): 2021-05 ~ 2026-05, 2026-06 stub 제외
WIN_START, WIN_END = "2021-05-31", "2026-05-31"


def _fetch():
    """pykrx 우선(인덱스 코드 2203=KOSDAQ150) → 실패 시 FinanceDataReader('KQ150') 폴백."""
    # 1) pykrx
    try:
        from pykrx import stock
        s, e = START.replace("-", ""), END.replace("-", "")
        try:
            df = stock.get_index_ohlcv(s, e, "2203")        # 신버전 시그니처
        except TypeError:
            df = stock.get_index_ohlcv_by_date(s, e, "2203") # 구버전
        df = df.rename(columns={"종가": "close", "Close": "close"})
        out = df[["close"]].copy()
        out.index = out.index.map(lambda x: x.strftime("%Y-%m-%d") if hasattr(x, "strftime") else str(x)[:10])
        print("[source] pykrx index 2203 (KOSDAQ150)")
        return out
    except Exception as ex1:
        print(f"[pykrx 실패] {ex1}")
    # 2) FinanceDataReader
    try:
        import FinanceDataReader as fdr
        df = fdr.DataReader("KQ150", START, END)
        out = df[["Close"]].rename(columns={"Close": "close"}).copy()
        out.index = out.index.map(lambda x: x.strftime("%Y-%m-%d"))
        print("[source] FinanceDataReader KQ150 (KOSDAQ150)")
        return out
    except Exception as ex2:
        print(f"[FDR 실패] {ex2}")
    raise SystemExit("✗ KOSDAQ150 수집 실패 — `pip install pykrx finance-datareader` 후 재시도. "
                     "(둘 다 막히면 KRX 정보데이터시스템 [13104] KOSDAQ150 수기 CSV로 대체 가능)")


def _to_monthly(daily):
    """일간 close → 월말 close + 월수익률. (pandas 사용)"""
    import pandas as pd
    s = pd.Series({pd.Timestamp(k): float(v["close"]) for k, v in daily.to_dict("index").items()})
    s = s.sort_index()
    m = s.resample("ME").last().dropna()
    out = m.to_frame("close")
    out["ret"] = out["close"].pct_change()
    out.index = out.index.map(lambda x: x.strftime("%Y-%m-%d"))
    return out


def _cagr(monthly):
    import pandas as pd
    m = monthly.copy(); m.index = pd.to_datetime(m.index)
    w = m[(m.index >= WIN_START) & (m.index <= WIN_END)]
    if len(w) < 12: return None
    px = w["close"].dropna()
    yrs = (pd.to_datetime(px.index[-1]) - pd.to_datetime(px.index[0])).days / 365.25
    return (px.iloc[-1] / px.iloc[0]) ** (1 / yrs) - 1


def self_test():
    import pandas as pd, numpy as np
    idx = pd.date_range("2019-12-01", "2026-06-30", freq="B")
    daily = pd.DataFrame({"close": np.linspace(1000, 1500, len(idx))}, index=idx)
    daily.index = daily.index.map(lambda x: x.strftime("%Y-%m-%d"))
    m = _to_monthly(daily)
    assert list(m.columns) == ["close", "ret"], "monthly 스키마 오류"
    assert m.index[0].endswith(("-12-31", "-12-30")), "월말 정렬 오류"
    c = _cagr(m)
    assert c is not None and 0 < c < 0.2, f"CAGR 계산 오류 {c}"
    print("✓ self-test 통과 (스키마·월말정렬·CAGR 로직 OK, 네트워크 불요)")


def main():
    daily = _fetch()
    daily.to_csv(OUT_DAILY, index_label="date")
    monthly = _to_monthly(daily)
    monthly.to_csv(OUT_MONTHLY, index_label="date")
    c = _cagr(monthly)
    print(f"\n저장: {OUT_DAILY} ({len(daily)}행), {OUT_MONTHLY} ({len(monthly)}행)")
    print(f"기간: {daily.index[0]} ~ {daily.index[-1]}")
    if c is not None:
        print(f"\n★ KOSDAQ150 CAGR (2021-05~2026-05, 판정윈도우) = {c*100:+.2f}%")
        print(f"   대조: base_MKT +12.06% / base_EW +31.41% / 선정 gw0.5 +20.89%")
        print(f"   → 이 숫자가 합격선의 '진짜 시장' 기준이 됨 (낮으면 선정이 이기고, 높으면 진다)")


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        main()
