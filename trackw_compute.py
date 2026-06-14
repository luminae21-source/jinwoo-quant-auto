"""
trackw_compute.py — Track W 반사실 자동계산 (2026-06-13)

문제: trackw_ledger.csv의 sys_ret(시스템13 반사실)·themeEW_ret(테마버킷 EW)를 매월 손계산 =
      첫 기입 병목. 이 도구가 **실데이터(월간가격)로 자동 계산** → 진우는 W_ret(실제 재량수익)만.

입력(실존): kospi_monthly_prices.csv(KOSPI+KOSDAQ 합본 월간), 시스템13·테마버킷·대덕 코드.
출력: 해당 월 (sys_ret, themeEW_ret, W_ret_default) + trackw_ledger.csv 행 갱신(옵션).
정직: 월간수익 = 월말/전월말−1. 진행중 월은 MTD(미완성). W_ret_default=등록 보유(대덕+진입테마) EW —
      진우 실제 실현수익(실제 비중·진입타이밍)과 다르면 **진우가 override**. production 무수정.

사용:
  python trackw_compute.py --month 2026-06            # 계산만(미리보기)
  python trackw_compute.py --month 2026-06 --write     # ledger 행 자동기입(W는 default, 진우 확인)
  python trackw_compute.py --selftest
"""
import argparse, os, sys, csv
import pandas as pd, numpy as np

PRICES = "kospi_monthly_prices.csv"
LEDGER = "trackw_ledger.csv"
SYS13 = {  # v3.7.2 S+/S/A 13 (2026-06 dashboard)
    "012450": "한화에어로", "034020": "두산에너빌리티", "003230": "삼양식품",
    "005940": "NH투자증권", "095340": "ISC", "042700": "한미반도체", "196170": "알테오젠",
    "000660": "SK하이닉스", "028260": "삼성물산", "005930": "삼성전자", "035420": "NAVER",
    "090430": "아모레퍼시픽", "033780": "KT&G"}
THEME_BUCKET = {"089030": "테크윙", "095610": "테스", "087010": "펩트론"}  # 등록 테마 워치(active)
W_HELD = {"353200": "대덕전자"}  # 진우 실보유 재량(위성). 진입 테마는 진입 시 추가.


def _mret(prices, codes, month):
    """codes EW의 month 월수익 = 월말/전월말−1. month=YYYY-MM."""
    idx = [t for t in prices.index if str(t)[:7] == month]
    if not idx:
        return None, []
    pos = prices.index.get_loc(idx[-1])
    if pos < 1:
        return None, []
    cur, prev = prices.iloc[pos], prices.iloc[pos - 1]
    rets, used = [], []
    for c in codes:
        if c in prices.columns and pd.notna(cur.get(c)) and pd.notna(prev.get(c)) and prev.get(c) > 0:
            rets.append(cur[c] / prev[c] - 1); used.append(c)
    return (float(np.mean(rets)) if rets else None), used


def compute(month, prices_csv=PRICES, sys13=SYS13, theme=THEME_BUCKET, wheld=W_HELD):
    prices = pd.read_csv(prices_csv, index_col=0, parse_dates=True)
    prices.columns = [str(c).zfill(6) for c in prices.columns]
    sysr, su = _mret(prices, list(sys13), month)
    thr, tu = _mret(prices, list(theme), month)
    wr, wu = _mret(prices, list(wheld), month)
    last = str(prices.index[-1])[:7]
    return dict(month=month, sys_ret=sysr, themeEW_ret=thr, W_ret_default=wr,
                sys_used=len(su), theme_used=tu, w_used=wu,
                mtd=(month == last and str(prices.index[-1].day) != "30" or month == last))


def _write_ledger(res, ledger=LEDGER):
    rows = []
    if os.path.exists(ledger):
        with open(ledger, encoding="utf-8") as f:
            rows = list(csv.reader(f))
    out, done = [], False
    for r in rows:
        if r and r[0] == res["month"]:
            out.append([res["month"],
                        f"{res['W_ret_default']:.4f}" if res["W_ret_default"] is not None else "",
                        f"{res['sys_ret']:.4f}" if res["sys_ret"] is not None else "",
                        f"{res['themeEW_ret']:.4f}" if res["themeEW_ret"] is not None else "",
                        "auto: W=대덕default(진우 override) sys/themeEW=실데이터"]); done = True
        else:
            out.append(r)
    if not done:
        out.append([res["month"],
                    f"{res['W_ret_default']:.4f}" if res["W_ret_default"] is not None else "",
                    f"{res['sys_ret']:.4f}" if res["sys_ret"] is not None else "",
                    f"{res['themeEW_ret']:.4f}" if res["themeEW_ret"] is not None else "",
                    "auto"])
    with open(ledger, "w", encoding="utf-8", newline="") as f:
        csv.writer(f).writerows(out)


def _fmt(res):
    def p(x): return "미산출" if x is None else f"{x*100:+.2f}%"
    L = [f"=== Track W 반사실 자동계산 — {res['month']}" + (" (MTD·진행중)" if res['mtd'] else "") + " ===",
         f"  sys_ret    (시스템13 EW, 반사실) = {p(res['sys_ret'])}  [{res['sys_used']}/13종 사용]",
         f"  themeEW_ret(테마버킷 EW)        = {p(res['themeEW_ret'])}  [{len(res['theme_used'])}종: {','.join(res['theme_used'])}]",
         f"  W_ret_default(대덕 등 실보유 EW) = {p(res['W_ret_default'])}  [{','.join(res['w_used']) or '없음'}]",
         "  ⚠️ W_ret는 default(등록 보유 EW). 진우 실제 실현수익과 다르면 override. sys/themeEW는 실데이터 확정."]
    return "\n".join(L)


def _selftest():
    idx = pd.date_range("2026-01-31", periods=6, freq="ME")
    px = pd.DataFrame(index=idx)
    for c in list(SYS13) + list(THEME_BUCKET) + list(W_HELD):
        px[c] = np.linspace(100, 110, 6)  # +10% 6개월 균등
    px.to_csv("_tw_p.csv")
    r = compute("2026-03", "_tw_p.csv")
    assert r["sys_ret"] is not None and abs(r["sys_ret"] - (110 - 100) / 100 / 5 * 1) < 0.05, "sys_ret 계산 오류"
    assert r["themeEW_ret"] is not None and r["W_ret_default"] is not None, "테마/W 미산출"
    # 월 매칭 없는 경우 None
    r2 = compute("2099-01", "_tw_p.csv")
    assert r2["sys_ret"] is None, "없는 월인데 산출됨"
    os.remove("_tw_p.csv")
    print("[OK] trackw_compute self-test 통과 (월수익 계산·월매칭·결측 처리)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--month", default=None)
    ap.add_argument("--prices", default=PRICES)
    ap.add_argument("--write", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    if not a.month:
        raise SystemExit("--month YYYY-MM 필요")
    if not os.path.exists(a.prices):
        raise SystemExit(f"{a.prices} 없음")
    res = compute(a.month, a.prices)
    print(_fmt(res))
    if a.write:
        _write_ledger(res)
        print(f"\n→ {LEDGER} {a.month} 행 기입(W=default). 진우: 실제 재량수익으로 W_ret 확인·수정 후 `python trackw_score.py`.")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
