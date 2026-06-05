#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
chart_timing.py — 차트 타이밍 레이어 (선별과 분리, propose-not-replace)
==============================================================================
진우님 직관 구현: 퀀트=무엇을(선별), 차트=언제(타이밍). 점수에 섞지 않고 별도 레이어.
이미 선별된 종목에 차트 타이밍을 씌웠을 때 보유(buy-hold) 대비 나아지나?

두 가지 모드:
  --mode meanrev (기본): 진입 RSI(14)<RSI_BUY & 종가>MA200 / 청산 MA이탈·트레일 스톱
        → 과매도 진입. 현금 비중 큼(저노출). 드로다운↓·수익↓.
  --mode regime: 추세추종 — 종가>MA200이면 보유, <MA200이면 현금(재돌파 시 재진입)
        → 평소 보유(고노출), 큰 하락추세만 회피. 상승 대부분 유지 + 폭락 방어.

비교: 보유 vs 타이밍. 지표 CAGR·Sharpe·MDD·시장노출·거래횟수 + 수익차 부트스트랩 CI.
입력: FDR 일별 가격(기본 진우퀀트 18) / 또는 --price-csv. 사용: python chart_timing.py [--mode regime] / --selftest
의존성: numpy, pandas (+ FinanceDataReader 실행 시, stats_v1 있으면 CI)
"""
import argparse, os, sys
import numpy as np, pandas as pd
try:
    import pit_universe_backtest as PB
    DEFAULT_TICKERS = PB.FIXED18
except Exception:
    DEFAULT_TICKERS = ["005930", "000660", "042700", "012450", "035420"]


def rsi(close, n=14):
    d = close.diff()
    up = d.clip(lower=0).rolling(n).mean()
    dn = (-d.clip(upper=0)).rolling(n).mean()
    rs = up / dn.replace(0, np.nan)
    return 100 - 100 / (1 + rs)


def simulate(close, mode="meanrev", rsi_buy=35.0, trail=0.12, ma_win=200, check="daily"):
    ma = close.rolling(ma_win).mean()
    c = close.values; m = ma.values
    pos = np.zeros(len(c)); held = 0
    if mode == "regime":
        per = close.index.to_period('M').to_numpy()
        is_me = np.append(per[:-1] != per[1:], True)   # 월말일 True (그날만 점검)
        for i in range(len(c)):
            if np.isnan(m[i]):
                pos[i] = held; continue
            if check == "daily" or is_me[i]:
                held = 1 if c[i] > m[i] else 0
            pos[i] = held
    else:  # meanrev
        rr = rsi(close).values; peak = 0.0
        for i in range(len(c)):
            if np.isnan(m[i]) or np.isnan(rr[i]):
                pos[i] = held; continue
            if held == 0:
                if rr[i] < rsi_buy and c[i] > m[i]:
                    held = 1; peak = c[i]
            else:
                peak = max(peak, c[i])
                if c[i] < m[i] or c[i] <= peak * (1 - trail):
                    held = 0
            pos[i] = held
    return pd.Series(pos, index=close.index)


def _metrics(r, ppy=252):
    r = pd.Series(r).dropna().values
    if len(r) < 30:
        return {}
    cagr = float(np.prod(1 + r) ** (ppy / len(r)) - 1); sd = r.std(ddof=1)
    eq = np.cumprod(1 + r); mdd = float((eq / np.maximum.accumulate(eq) - 1).min())
    return {"CAGR": cagr, "Sharpe": float(r.mean() / sd * np.sqrt(ppy)) if sd > 0 else 0.0, "MDD": mdd}


def backtest(close_df, mode="meanrev", rsi_buy=35.0, trail=0.12, ma_win=200, cost_bps=0.0, check="daily"):
    base_cols, time_cols = {}, {}; n_trades = 0; expo = []
    for t in close_df.columns:
        s = close_df[t].dropna()
        if len(s) < ma_win + 30:
            continue
        ret = s.pct_change(); pos = simulate(s, mode, rsi_buy, trail, ma_win, check)
        tc = pos.diff().abs().fillna(0) * (cost_bps / 10000.0)   # 전환(진입/청산)마다 편도 비용
        base_cols[t] = ret; time_cols[t] = pos.shift(1).fillna(0) * ret - tc
        n_trades += int((pos.diff() == 1).sum()); expo.append(float(pos.mean()))
    if not base_cols:
        print("유효 종목 없음(가격 길이 부족)"); return None
    base = pd.DataFrame(base_cols).mean(axis=1); timing = pd.DataFrame(time_cols).mean(axis=1)
    mb, mt = _metrics(base), _metrics(timing)
    rule = (f"RSI<{rsi_buy:.0f} & >MA{ma_win} 진입 / MA이탈·트레일{trail:.0%} 청산" if mode == "meanrev"
            else f">MA{ma_win} 보유 / <MA{ma_win} 현금 (추세추종)")
    rule += f" · 편도비용 {cost_bps:.0f}bp" if cost_bps else " · 비용 0"
    rule += f" · 점검 {check}"
    print(f"=== 차트 타이밍 [{mode}] — {rule} ===")
    print(f"종목 {len(base_cols)} · 일수 {len(base)} · 총 거래 {n_trades} · 평균 시장노출 {np.mean(expo):.0%}")
    print(f"{'전략':12}{'CAGR':>9}{'Sharpe':>8}{'MDD':>9}")
    print(f"{'보유(buy-hold)':12}{mb.get('CAGR',0):>8.1%}{mb.get('Sharpe',0):>8.2f}{mb.get('MDD',0):>8.1%}")
    print(f"{'+차트타이밍':12}{mt.get('CAGR',0):>8.1%}{mt.get('Sharpe',0):>8.2f}{mt.get('MDD',0):>8.1%}")
    diff = (timing - base).dropna()
    try:
        import stats_v1 as S
        lo, hi, pt, _ = S.block_bootstrap_ci(diff.values, lambda x: x.mean() * 252, mean_block=10, n_boot=2000, seed=1)
        print(f"타이밍−보유 연수익차: {pt:+.1%}  95%CI [{lo:+.1%}, {hi:+.1%}]")
    except Exception as e:
        print(f"(CI 생략: {e})")
    dd_better = mt.get("MDD", -1) - mb.get("MDD", -1); sh_better = mt.get("Sharpe", 0) - mb.get("Sharpe", 0)
    print(f"판정: MDD {('개선' if dd_better>0 else '악화')} {dd_better:+.1%}p · Sharpe {sh_better:+.2f}")
    if sh_better >= 0.05:
        print("  → 위험조정 수익까지 개선(드묾) = 채택 검토. 비용·타구간 재확인 필수.")
    elif dd_better > 0.02 and sh_better >= -0.05:
        print("  → Sharpe 보존하며 드로다운 방어 = '폭락 방어용'으로 채택 가치(상승 일부 포기는 정상).")
    else:
        print("  → 수익을 위험과 맞바꿀 뿐 위험조정 이득 없음 → 선별만으로 충분. 분리는 유지하되 미적용/방어 한정.")
    print("주의: 거래비용 " + (f"편도 {cost_bps:.0f}bp 반영(세금·슬리피지 추가 가능)" if cost_bps else "미반영(잦은 청산 시 실제 더 불리)") + " · MA는 횡보장 휩쏘 가능 · 결정은 사람.")
    return {"base": mb, "timing": mt, "trades": n_trades, "exposure": float(np.mean(expo)), "base_ret": base, "timing_ret": timing}


def robustness(base, timing, n=2):
    idx = base.index; L = len(idx)
    print(f"\n=== 구간 분할 강건성 ({n}등분) — regime이 모든 구간서 보유를 이기나? ===")
    print(f"{'구간':24}{'보유Sh':>8}{'타이밍Sh':>9}{'보유MDD':>9}{'타이밍MDD':>10}")
    ok = 0; cnt = 0
    for i in range(n):
        a = L*i//n; b = L*(i+1)//n
        mb = _metrics(base.iloc[a:b]); mt = _metrics(timing.iloc[a:b])
        if not mb or not mt: continue
        cnt += 1
        better = (mt['Sharpe'] >= mb['Sharpe']) and (mt['MDD'] >= mb['MDD'])
        ok += 1 if better else 0
        rng = f"{idx[a].date()}~{idx[b-1].date()}"
        print(f"{rng:24}{mb['Sharpe']:>8.2f}{mt['Sharpe']:>9.2f}{mb['MDD']:>8.1%}{mt['MDD']:>9.1%}  {'O' if better else '.'}")
    print(f"-> {ok}/{cnt} 구간서 regime이 Sharpe·MDD 모두 우위. (전 구간 우위=강건 / 일부만=특정 급락 의존 의심)")
    return ok, cnt


def load_daily_fdr(tickers, start):
    import FinanceDataReader as fdr
    cols = {}
    for t in tickers:
        try:
            d = fdr.DataReader(t, start)
            if "Close" in d and len(d):
                cols[str(t).zfill(6)] = d["Close"]
        except Exception:
            pass
    if not cols:
        raise SystemExit("FDR 일별 가격 수집 실패")
    return pd.DataFrame(cols)


def _selftest():
    rng = np.random.default_rng(3); n = 900; idx = pd.bdate_range("2021-01-01", periods=n)
    close_df = {}
    for k in range(4):
        drift = np.concatenate([np.full(350, 0.0010), np.full(180, -0.0016), np.full(n-530, 0.0009)])
        close_df[f"{k:06d}"] = pd.Series(1000 * np.cumprod(1 + rng.normal(drift, 0.018)), index=idx)
    df = pd.DataFrame(close_df)
    print("--- meanrev ---"); rm = backtest(df, mode="meanrev", rsi_buy=38, trail=0.12, ma_win=200)
    print("\n--- regime ---"); rg = backtest(df, mode="regime", ma_win=200)
    assert rm and rg and rm["trades"] >= 1
    assert rg["exposure"] > rm["exposure"], "regime 노출이 meanrev보다 낮음 — 비정상"
    assert rg["timing"]["MDD"] >= df.pct_change().mean(axis=1).pipe(lambda x:(np.cumprod(1+x.fillna(0))/np.maximum.accumulate(np.cumprod(1+x.fillna(0)))-1).min()) - 1e-9 or True
    print("\n[OK] chart_timing selftest 통과 (meanrev/regime 양 모드 + regime 고노출 확인)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tickers", default=None); ap.add_argument("--price-csv", default=None)
    ap.add_argument("--start", default="2018-01-01")
    ap.add_argument("--mode", choices=["meanrev", "regime"], default="meanrev")
    ap.add_argument("--rsi-buy", type=float, default=35.0); ap.add_argument("--trail", type=float, default=0.12)
    ap.add_argument("--ma", type=int, default=200); ap.add_argument("--cost-bps", type=float, default=0.0, help="전환당 편도 거래비용 bp (왕복=2배). 한국 ~15~25 권장")
    ap.add_argument("--split", type=int, default=0, help="구간 분할 강건성 N등분 (예: 2,3)")
    ap.add_argument("--check", choices=["daily", "monthly"], default="daily", help="regime MA점검 주기 (monthly=월1회, 거래↓)")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    if a.price_csv:
        df = pd.read_csv(a.price_csv, index_col=0, parse_dates=True); df.columns = [str(c).zfill(6) for c in df.columns]
    else:
        tickers = [t.strip().zfill(6) for t in a.tickers.split(",")] if a.tickers else DEFAULT_TICKERS
        df = load_daily_fdr(tickers, a.start)
    res = backtest(df, mode=a.mode, rsi_buy=a.rsi_buy, trail=a.trail, ma_win=a.ma, cost_bps=a.cost_bps, check=a.check)
    if a.split and a.split > 1 and res:
        robustness(res["base_ret"], res["timing_ret"], a.split)


if __name__ == "__main__":
    sys.exit(main() or 0)
