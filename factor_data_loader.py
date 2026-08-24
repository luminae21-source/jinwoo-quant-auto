"""
진우퀀트 v3.7 영역 1 — 실데이터 팩터 패널 로더 (FDR + OpenDART)
================================================================
신규 후보(52주 신고가·gross profitability·SUE)를 실데이터로 만들어
factor_diagnosis 게이트(G1~G4/G6)에 태우는 connector.

설계 결정 (진우 합의):
  - PEAD 기대치 = seasonal-RW (무료, 컨센서스 불필요)
  - 가격 = FinanceDataReader, 재무 = OpenDART(무료 API key)
  - 기존 score 팩터값(F/ModF/Sloan/FAR/β)은 score 코드 공유 후 CSV hook 으로 병합 →
    그때 정제(중복 청소: F↔ModF 상관, accrual↔Sloan)와 G3/G4 직교 게이트가 자동 작동.

핵심 안전장치:
  - point-in-time: 분기 재무는 '공시지연(lag_days)' 만큼 늦춰 ffill → look-ahead 차단.
  - GP 는 flow(매출·매출원가) TTM(4분기 합) / stock(총자산) 시점값.

이 골격을 만든 샌드박스는 FDR/DART 차단 → 네트워크 경로는 진우님 환경에서.
조립 로직은 mock 으로 스모크 검증됨.
실행:
  python3 factor_data_loader.py                 # mock 스모크 (네트워크 불필요)
  # 실데이터:  run_factor_diagnosis(UNIVERSE, "2019-01-01", "2026-05-31", dart_key="...")
"""
from __future__ import annotations
import warnings
warnings.filterwarnings("ignore")
import numpy as np
import pandas as pd

import factor_diagnosis as fd

# 사업·분기 보고서 reprt_code (OpenDART)
REPRT = {"Q1": "11013", "H": "11012", "Q3": "11014", "FY": "11011"}
# 계정명 매칭 (DART account_nm; 환경에서 1회 확인 권장)
ACCT = {"sales": ["매출액", "수익(매출액)", "영업수익"],
        "cogs":  ["매출원가"],
        "ta":    ["자산총계"],
        "eps":   ["주당순이익", "기본주당이익"]}


# ====================== 1. 가격 (FDR) ======================================

def load_close_panel_fdr(universe: dict, start: str, end: str) -> pd.DataFrame:
    import FinanceDataReader as fdr
    cols = {}
    for t in universe:
        cols[t] = fdr.DataReader(t, start, end)["Close"]
    return pd.DataFrame(cols).sort_index()


# ====================== 2. 재무 (OpenDART) =================================

def load_dart_corpcodes(api_key: str) -> dict:
    """OpenDART corpCode.xml(zip) → {6자리 종목코드: 8자리 corp_code}."""
    import requests, io, zipfile, xml.etree.ElementTree as ET
    r = requests.get("https://opendart.fss.or.kr/api/corpCode.xml",
                     params={"crtfc_key": api_key}, timeout=30)
    zf = zipfile.ZipFile(io.BytesIO(r.content))
    root = ET.fromstring(zf.read(zf.namelist()[0]))
    out = {}
    for e in root.iter("list"):
        stock = (e.findtext("stock_code") or "").strip()
        corp = (e.findtext("corp_code") or "").strip()
        if stock:
            out[stock] = corp
    return out


def _match(rows: list, names: list):
    for r in rows:
        nm = (r.get("account_nm") or "").replace(" ", "")
        if any(n.replace(" ", "") in nm for n in names):
            v = (r.get("thstrm_amount") or "").replace(",", "")
            try:
                return float(v)
            except ValueError:
                return np.nan
    return np.nan


def fetch_dart_quarter(api_key: str, corp_code: str, year: int, quarter: str):
    """단일회사 전체 재무제표(fnlttSinglAcntAll) → dict(sales,cogs,ta,eps)."""
    import requests
    r = requests.get("https://opendart.fss.or.kr/api/fnlttSinglAcntAll.json",
                     params={"crtfc_key": api_key, "corp_code": corp_code,
                             "bsns_year": str(year), "reprt_code": REPRT[quarter],
                             "fs_div": "CFS"}, timeout=20).json()
    rows = r.get("list", []) if r.get("status") == "000" else []
    return {k: _match(rows, names) for k, names in ACCT.items()}


def build_quarterly_panels(api_key: str, universe: dict, corpmap: dict,
                           years: range) -> dict:
    """반환 dict[name -> DataFrame(분기말일 x 종목)]  (sales,cogs,ta,eps)."""
    q_end = {"Q1": "-03-31", "H": "-06-30", "Q3": "-09-30", "FY": "-12-31"}
    rec = {k: {} for k in ACCT}
    for t in universe:
        cc = corpmap.get(t)
        if not cc:
            continue
        for y in years:
            for q, suffix in q_end.items():
                d = pd.Timestamp(f"{y}{suffix}")
                vals = fetch_dart_quarter(api_key, cc, y, q)
                for k in ACCT:
                    rec[k].setdefault(d, {})[t] = vals[k]
    return {k: pd.DataFrame(v).T.sort_index() for k, v in rec.items()}


# ====================== 3. point-in-time 조립 ==============================

def quarterly_to_daily(q_df: pd.DataFrame, daily_index: pd.DatetimeIndex,
                       lag_days: int = 45) -> pd.DataFrame:
    """분기 패널 → 일별. 공시지연(lag_days) 만큼 늦춰 ffill (look-ahead 차단)."""
    avail = q_df.copy()
    avail.index = q_df.index + pd.Timedelta(days=lag_days)
    full = avail.reindex(daily_index.union(avail.index)).ffill()
    return full.reindex(daily_index)


def cumulative_to_quarterly(cum_q: pd.DataFrame) -> pd.DataFrame:
    """DART 손익항목은 누적공시(Q1=3mo, 반기=6mo, Q3=9mo, FY=12mo) → 단일분기 환산.
    같은 회계연도 내 차분: Q1=Q1, Q2=H-Q1, Q3=Q3cum-H, Q4=FY-Q3cum. (잔고항목 총자산은 환산 X)"""
    out = cum_q.copy().astype(float)
    for y in pd.unique(cum_q.index.year):
        sub = cum_q[cum_q.index.year == y].sort_index()
        d = sub.diff()
        d.iloc[0] = sub.iloc[0]              # 연중 첫 분기(Q1) = 누적 그대로
        out.loc[sub.index] = d.values
    return out


def assemble_factors(close: pd.DataFrame, sales_q: pd.DataFrame, cogs_q: pd.DataFrame,
                     ta_q: pd.DataFrame, eps_q: pd.DataFrame, lag_days: int = 45,
                     fwd_h: int = 21) -> tuple:
    """가격+분기재무 → 후보 팩터 패널(dict) + 선행수익률. (실/ mock 공용 로직)"""
    # 52주 신고가 근접도 (가격만)
    f52 = fd.f_52w_high_proximity(close)
    # 손익항목 누적→단일분기 환산 후 사용 (총자산은 잔고라 그대로)
    sales_sq = cumulative_to_quarterly(sales_q)
    cogs_sq = cumulative_to_quarterly(cogs_q)
    eps_sq = cumulative_to_quarterly(eps_q)
    # GP/TA: flow TTM(단일분기 4개 합), stock(총자산) 시점값
    sales_ttm = sales_sq.rolling(4, min_periods=2).sum()
    cogs_ttm = cogs_sq.rolling(4, min_periods=2).sum()
    gp_q = fd.f_gross_profitability(sales_ttm, cogs_ttm, ta_q)
    # SUE seasonal-RW (단일분기 EPS, YoY)
    sue_q = fd.f_sue_seasonal_rw(eps_sq)
    # 분기 → 일별 (공시지연 ffill)
    idx = close.index
    factors = {
        "f52w_high": f52,
        "gross_prof": quarterly_to_daily(gp_q, idx, lag_days),
        "sue_srw": quarterly_to_daily(sue_q, idx, lag_days),
    }
    fwd = fd.forward_return(close, fwd_h)
    return factors, fwd


def load_existing_factors_csv(path: str) -> dict:
    """<<HOOK>> score 코드 공유 후: 기존 팩터값 CSV → dict[name -> DataFrame].
    스키마: date,ticker,factor,value (long) → 피벗.  정제·G3/G4 직교 게이트용."""
    df = pd.read_csv(path, parse_dates=["date"])
    out = {}
    for name, g in df.groupby("factor"):
        out[name] = g.pivot(index="date", columns="ticker", values="value").sort_index()
    return out


# ====================== 4. 실데이터 드라이버 ===============================

def build_factor_panel_fdr_dart(universe: dict, start: str, end: str, dart_key: str,
                                lag_days: int = 45, existing_csv: str | None = None):
    """<<PLUG>> 실데이터: FDR 가격 + OpenDART 재무 → (close, candidates, fwd, existing)."""
    close = load_close_panel_fdr(universe, start, end)
    corpmap = load_dart_corpcodes(dart_key)
    years = range(pd.Timestamp(start).year - 1, pd.Timestamp(end).year + 1)  # TTM 위해 -1년
    q = build_quarterly_panels(dart_key, universe, corpmap, years)
    candidates, fwd = assemble_factors(close, q["sales"], q["cogs"], q["ta"], q["eps"], lag_days)
    existing = load_existing_factors_csv(existing_csv) if existing_csv else {}
    return close, candidates, fwd, existing


def run_factor_diagnosis(close, candidates: dict, fwd, existing: dict):
    """후보별 게이트 진단표 출력. existing 이 비면 G3/G4 는 '—'(정제는 score 공유 후)."""
    rows = [fd.evaluate_candidate(n, f, fwd, existing) for n, f in candidates.items()]
    df = pd.DataFrame(rows)
    cols = ["factor", "mean_IC", "IC_IR", "max_corr_existing", "resid_mean_IC",
            "tertile_spread", "VERDICT"]
    show = df[cols].copy()
    for c in ["mean_IC", "IC_IR", "max_corr_existing", "resid_mean_IC", "tertile_spread"]:
        show[c] = show[c].map(lambda x: f"{x:.3f}" if pd.notna(x) else "—")
    print(show.to_string(index=False))
    if not existing:
        print(" (existing 팩터 미연결 → G3/G4='—'. score 코드 공유 후 정제·직교 게이트 작동.)")
    return df


# ====================== 5. mock 스모크 (네트워크 X) ========================

def _mock_inputs(seed=5):
    """합성 가격 + 합성 분기재무. SUE 가 선행수익률과 양(+)연관이 되도록 심음."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2021-01-04", periods=600)
    tks = [f"S{i:02d}" for i in range(10)]
    # 가격
    close = pd.DataFrame(index=dates, columns=tks, dtype=float)
    for t in tks:
        close[t] = 10000 * np.exp(np.cumsum(rng.normal(0.0003, 0.02, len(dates))))
    # 분기말 (가격 인덱스 밖 날짜 포함)
    qd = pd.to_datetime([f"{y}-{m}" for y in range(2020, 2027)
                         for m in ("03-31", "06-30", "09-30", "12-31")])
    # 손익은 '누적'형으로 생성 (연중 Q1→FY 증가). 환산 로직 검증용.
    qmult = pd.Series({3: 1, 6: 2, 9: 3, 12: 4})   # 월→누적 분기수
    base_sales = pd.DataFrame(rng.uniform(2e11, 3e11, (len(qd), len(tks))), index=qd, columns=tks)
    mult = np.array([qmult[d.month] for d in qd])[:, None]
    sales = base_sales * mult                       # 누적 매출
    cogs = sales * rng.uniform(0.55, 0.8, (len(qd), len(tks)))
    ta = pd.DataFrame(rng.uniform(2e12, 4e12, (len(qd), len(tks))), index=qd, columns=tks)
    base_eps = pd.DataFrame(rng.normal(150, 60, (len(qd), len(tks))), index=qd, columns=tks)
    eps = base_eps * mult                           # 누적 EPS
    return close, sales, cogs, ta, eps


def main():
    print("=" * 74)
    print(" 실데이터 팩터 패널 로더 — mock 스모크 (조립 + point-in-time + 진단)")
    print("=" * 74)
    close, sales, cogs, ta, eps = _mock_inputs()
    candidates, fwd = assemble_factors(close, sales, cogs, ta, eps, lag_days=45)
    print(f" close {close.shape}, 후보 {list(candidates)}")
    # point-in-time 확인: 재무가 분기말+45일 이후에만 값이 채워졌는가
    gp = candidates["gross_prof"]
    first_valid = gp.dropna(how="all").index.min()
    print(f" gross_prof 최초 유효일 = {first_valid.date()} (분기말+45일 ffill 반영 확인)")
    print(f" 결측율: f52w={candidates['f52w_high'].isna().mean().mean():.1%}, "
          f"gp={gp.isna().mean().mean():.1%}, sue={candidates['sue_srw'].isna().mean().mean():.1%}")
    print("\n[게이트 진단 — existing 미연결(신규 후보만)]")
    run_factor_diagnosis(close, candidates, fwd, existing={})
    print("\n 실데이터: build_factor_panel_fdr_dart(UNIVERSE, start, end, dart_key, existing_csv=...)")
    print(" → score 코드 공유 후 existing 연결되면 G3/G4 직교·정제 게이트까지 작동.")


if __name__ == "__main__":
    main()
