#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Track W 자동 갱신 — track_w_ledger.csv의 fwd_1m/3m/6m/12m·메인/보조 점수·임계 단계 산출.
설계: v2 문서 B. 메인=재량매수−동액 v3.7.2 바스켓(판정) / 보조=패스후보평균−매수평균(경고).
벤치마크(B 고도화): 지수 프록시 대신 **v3.7.2 S+/S/A 픽 EW 동액 바스켓의 동기간 fwd 수익률**.
 (정밀 한계: 신호시점 PIT 픽이 아니라 최신 픽 바스켓 사용 — 근사. 픽 없으면 지수 프록시 폴백.)
원칙: 사용자 기입행(reason·stop_price·no_buy_reason) 무수정, fwd_*·result_note만 자동. FDR 없으면 graceful.
사용: python update_track_w.py [--selftest]"""
import sys, io, datetime, pathlib
import pandas as pd

BASE = pathlib.Path(__file__).parent.resolve()
LEDGER = BASE / "track_w_ledger.csv"
MONTHS = {"fwd_1m": 1, "fwd_3m": 3, "fwd_6m": 6, "fwd_12m": 12}
JUDGE = "fwd_3m"


def _fdr():
    try:
        import FinanceDataReader as fdr
        return fdr
    except Exception:
        return None


def load_csv(name, **kw):
    p = BASE / name
    if not p.exists():
        return None
    for e in ("utf-8-sig", "utf-8", "cp949"):
        try:
            return pd.read_csv(p, encoding=e, **kw)
        except Exception:
            continue
    return None


def fetch_close(code, start, end, fdr):
    if fdr is None:
        return None
    try:
        df = fdr.DataReader(str(code).zfill(6), start, end)
        s = df["Close"].dropna()
        s.index = pd.to_datetime(s.index)
        return s if len(s) else None
    except Exception:
        return None


def fwd_return(close, base_date, months, base_price=None):
    if close is None:
        return None
    base_date = pd.Timestamp(base_date)
    after = close[close.index >= base_date]
    if not len(after):
        return None
    p0 = float(base_price) if (base_price is not None and pd.notna(base_price)) else float(after.iloc[0])
    if not p0:
        return None
    target = base_date + pd.DateOffset(months=months)
    upto = close[close.index <= target]
    if not len(upto):
        return None
    p1 = float(upto.iloc[-1])
    partial = target > close.index[-1]
    return (p1 / p0 - 1.0, partial)


def load_picks():
    """v3.7.2 S+/S/A 픽 코드 리스트 (동액 바스켓)."""
    sc = load_csv("v37_2_scores_latest.csv")
    if sc is None or "등급" not in sc.columns or "코드" not in sc.columns:
        return []
    p = sc[sc["등급"].isin(["S+", "S", "A"])]
    return [str(c).split(".")[0].zfill(6) for c in p["코드"] if pd.notna(c)]


def basket_fwd(fdr, base_date, months, picks, cache, end):
    """v3.7.2 픽 EW 바스켓의 동기간 fwd 평균수익률. (ret, n) 또는 None."""
    rs = []
    for c in picks:
        if c not in cache:
            cache[c] = fetch_close(c, "2019-01-01", end, fdr)
        cl = cache[c]
        fr = fwd_return(cl, base_date, months)
        if fr is not None:
            rs.append(fr[0])
    if not rs:
        return None
    return (sum(rs) / len(rs), len(rs))


def bench_index(theme, source):
    t = str(theme) + str(source)
    return "KQ11" if any(k in t for k in ("KOSDAQ", "코스닥", "kosdaq")) else "KS11"


def threshold_stage(main, aux):
    if main is None:
        return "데이터부족"
    m = main * 100
    a = (aux * 100) if aux is not None else 0.0
    if m >= 0 and a <= 5:
        return "🟢 정상"
    if a >= 15 or m <= -10:
        return "🔴 축소검토(누적확인)"
    if a >= 10 or m < 0:
        return "🟠 경고(2구간 연속 시)"
    if a > 5:
        return "🟡 주의(2개월+ 지속 시)"
    return "🟢 정상"


def enrich(df, fdr):
    today = datetime.date.today().isoformat()
    rows = df[df["date_signal"].notna() & df["code"].notna()].copy() if "date_signal" in df.columns else df.iloc[0:0]
    if not len(rows):
        return df, {"n": 0}
    picks = load_picks()
    pcache = {}
    bench_mode = "v3.7.2 바스켓(EW, %d종)" % len(picks) if picks else "지수 프록시"
    main_list, buy_rets, pass_rets = [], [], []
    for i, r in rows.iterrows():
        code = str(r["code"]).split(".")[0].zfill(6)
        is_buy = str(r.get("actual_buy", "")).strip().upper() == "Y"
        base_date = r.get("buy_date") if (is_buy and pd.notna(r.get("buy_date"))) else r.get("date_signal")
        bp = pd.to_numeric(r.get("buy_price"), errors="coerce") if is_buy else None
        close = fetch_close(code, "2019-01-01", today, fdr)
        jr = None
        for col, m in MONTHS.items():
            fr = fwd_return(close, base_date, m, bp)
            if fr is not None:
                df.at[i, col] = round(fr[0] * 100, 2)
                if col == JUDGE:
                    jr = fr[0]
        if jr is not None:
            # 벤치 = v3.7.2 바스켓(우선) / 지수 프록시(폴백)
            bf = basket_fwd(fdr, base_date, MONTHS[JUDGE], picks, pcache, today) if picks else None
            if bf is not None:
                bench = bf[0]
            else:
                bidx = bench_index(r.get("theme", ""), r.get("source", ""))
                br = fwd_return(fetch_close(bidx, "2019-01-01", today, fdr), base_date, MONTHS[JUDGE])
                bench = br[0] if br else 0.0
            if is_buy:
                buy_rets.append(jr); main_list.append(jr - bench)
                df.at[i, "result_note"] = (str(r.get("result_note", "") or "") + f" [auto {today}: {JUDGE} {jr*100:+.1f}%p vs바스켓 {bench*100:+.1f}%]").strip()
            elif str(r.get("selected_by_user", "")).strip().upper() == "Y":
                pass_rets.append(jr)
    main = sum(main_list) / len(main_list) if main_list else None
    aux = (sum(pass_rets) / len(pass_rets) - sum(buy_rets) / len(buy_rets)) if (pass_rets and buy_rets) else None
    return df, {"n": len(rows), "n_buy": len(buy_rets), "n_pass": len(pass_rets),
                "main": main, "aux": aux, "stage": threshold_stage(main, aux), "bench_mode": bench_mode}


def run():
    df = load_csv("track_w_ledger.csv", dtype=str)
    if df is None:
        print("ledger 읽기 실패"); return
    fdr = _fdr()
    if fdr is None:
        print("⚠ FinanceDataReader 없음 — fwd 수익률 계산 스킵(구조만 점검). pip install finance-datareader")
    df2, summ = enrich(df, fdr)
    df2.to_csv(LEDGER, index=False, encoding="utf-8-sig")
    print("Track W 갱신: 대상 %d행 (매수 %d·패스 %d) · 벤치=%s" % (
        summ["n"], summ.get("n_buy", 0), summ.get("n_pass", 0), summ.get("bench_mode", "-")))
    if summ["n"] == 0:
        print("기록 없음 — 첫 재량매수/관찰을 매수 전 기입 후 재실행."); return
    m, a = summ.get("main"), summ.get("aux")
    print(("메인(재량−v3.7.2바스켓, %s): %+.2f%%p" % (JUDGE, m * 100)) if m is not None else "메인: 데이터부족")
    print(("보조(패스−매수, %s): %+.2f%%p (양수=패스가 더 잘됨=선별경고)" % (JUDGE, a * 100)) if a is not None else "보조: 표본부족")
    print("단계: %s  ※ 단일 스냅샷 — 6~12M 누적 후 정식 판정" % summ["stage"])


def selftest():
    idx = pd.date_range("2024-01-01", periods=400, freq="D")
    up = pd.Series([100 * (1.0 + 0.001 * i) for i in range(400)], index=idx)
    flat = pd.Series([100.0] * 400, index=idx)
    assert fwd_return(up, "2024-01-01", 3)[0] > 0
    assert abs(fwd_return(flat, "2024-01-01", 3)[0]) < 1e-9
    assert fwd_return(up, "2024-01-01", 3, base_price=100.0)[0] > 0
    assert fwd_return(up, "2029-01-01", 3) is None
    assert fwd_return(up, "2024-12-20", 12)[1] is True
    assert bench_index("로봇", "kosdaq_scan") == "KQ11" and bench_index("반도체", "점수xheat") == "KS11"
    assert threshold_stage(0.02, 0.02) == "🟢 정상"
    assert "🟡" in threshold_stage(0.01, 0.07)

    class FakeFdr:
        def DataReader(self, code, start, end):
            slope = 0.002 if str(code).startswith("005") else 0.0008
            ii = pd.date_range(start, end, freq="D")
            return pd.DataFrame({"Close": [100.0 * (1 + slope * k) for k in range(len(ii))]}, index=ii)
    # basket_fwd: 두 코드 평균
    bf = basket_fwd(FakeFdr(), "2024-01-02", 3, ["005930", "000660"], {}, "2026-01-01")
    assert bf is not None and bf[1] == 2 and bf[0] > 0, "basket_fwd"
    # enrich + 바스켓 벤치 경로 (picks 없으면 지수 폴백)
    led = pd.DataFrame([
        {"date_signal": "2024-01-02", "source": "theme_heat", "theme": "AI", "code": "005930", "name": "x",
         "actual_buy": "Y", "selected_by_user": "Y", "buy_date": "2024-01-02", "buy_price": "100"},
        {"date_signal": "2024-01-02", "source": "kosdaq_scan", "theme": "로봇", "code": "000660", "name": "y",
         "actual_buy": "N", "selected_by_user": "Y", "buy_date": "", "buy_price": ""}])
    for c in ["fwd_1m", "fwd_3m", "fwd_6m", "fwd_12m", "result_note", "no_buy_reason", "stop_price", "reason"]:
        led[c] = ""
    out, summ = enrich(led, FakeFdr())
    assert summ["n"] == 2 and summ["n_buy"] == 1 and summ["n_pass"] == 1, summ
    assert out.at[0, "fwd_3m"] is not None and float(out.at[0, "fwd_3m"]) > 0
    assert str(out.at[0, "reason"]) == ""
    print("✅ update_track_w self-test 통과 (12): fwd·partial·bench·stage·basket_fwd·enrich(바스켓벤치)·기입보존")


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        run()
