#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
trackw_update.py — Track W 원장 자동 충전 (실전 반사실 측정 가동)
==============================================================================
목적: 비어 있던 trackw_ledger.csv를 매월 자동으로 한 줄씩 채운다.
  W_ret       = 실보유(my_holdings.csv) 가중 월수익  ← '재량'
  sys_ret     = production 선별 18 EW 월수익(같은 돈, 반사실)
  themeEW_ret = 실보유가 속한 테마버킷 EW 월수익(테마 ETF 등가)
완결월(직전 마감월) 1줄 upsert 후 trackw_score 판정 출력.
정직: W는 **buy-hold 가중 근사**(월중 실제 매매 미반영). 실현치가 다르면 진우가 그 달 W_ret 수기 수정 가능.
무수정: production·선별엔진. 사용: python trackw_update.py [--selftest] [--month YYYY-MM]
"""
import argparse, os, sys, types, csv
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "trackw_ledger.csv")
HOLD18 = ['003230','034020','005940','095340','196170','012450','042700','000660','028260',
          '005930','035420','090430','033780','105560','006400','000270','035720','079550']


def _load_src(f, n):
    p = os.path.join(HERE, f); s = open(p, encoding="utf-8").read()
    m = types.ModuleType(n); m.__file__ = p; sys.modules[n] = m
    sys.dont_write_bytecode = True; exec(compile(s, p, "exec"), m.__dict__); return m


def load_panel():
    fr = []
    for f in ("kospi_monthly_prices.csv", "kosdaq_monthly_prices.csv"):
        p = os.path.join(HERE, f)
        if os.path.exists(p):
            d = pd.read_csv(p, parse_dates=["Date"], index_col="Date"); d.columns = [str(c).zfill(6) for c in d.columns]; fr.append(d)
    pan = pd.concat(fr, axis=1).sort_index(); return pan.loc[:, ~pan.columns.duplicated()]


def load_my():
    p = os.path.join(HERE, "my_holdings.csv"); codes, w = [], {}
    if not os.path.exists(p):
        return codes, w
    for line in open(p, encoding="utf-8-sig"):
        line = line.strip()
        if not line or line.startswith("#") or line.lower().startswith("code,"):
            continue
        pr = [x.strip() for x in line.split(",")]; c = pr[0].zfill(6)
        if c.isdigit():
            codes.append(c)
            try: w[c] = float(pr[2]) if len(pr) > 2 and pr[2] else 1.0
            except ValueError: w[c] = 1.0
    return codes, w


def basket_ret(panel, codes, i, weights=None):
    """월 i 가중(or EW) 수익. weights=None→EW. 데이터 없는 종목 제외 후 재정규화."""
    rs, ws = [], []
    for c in codes:
        if c in panel.columns:
            s = panel[c]
            if i < len(s) and pd.notna(s.iloc[i]) and pd.notna(s.iloc[i-1]) and s.iloc[i-1] != 0:
                rs.append(s.iloc[i]/s.iloc[i-1]-1); ws.append((weights or {}).get(c, 1.0))
    if not rs:
        return np.nan
    ws = np.array(ws, float); ws = ws/ws.sum()
    return float(np.dot(ws, rs))


def compute_row(panel, TC, month=None):
    fine, name = TC.load_fine_map()
    codes, w = load_my()
    if not codes:
        return None, "실보유 미입력(my_holdings.csv)"
    # 완결월 index
    if month:
        idx = [k for k, d in enumerate(panel.index) if d.strftime("%Y-%m") == month]
        i = idx[0] if idx else len(panel)-2
    else:
        i = len(panel)-2   # 직전 마감월(현재월=부분)
    if i < 1:
        return None, "데이터 부족"
    ym = panel.index[i].strftime("%Y-%m")
    # 테마버킷 = 실보유 테마들의 전 종목
    holdthemes = {TC.coarse_sector(name.get(c, ""), fine.get(c, "")) for c in codes}
    holdthemes -= {"기타", "미분류(섹터없음)"}
    themecodes = [c for c in panel.columns if TC.coarse_sector(name.get(c, ""), fine.get(c, "")) in holdthemes]
    W = basket_ret(panel, codes, i, w)
    sys = basket_ret(panel, HOLD18, i)
    tEW = basket_ret(panel, themecodes, i)
    return {"month": ym, "W_ret": round(W, 5), "sys_ret": round(sys, 5),
            "themeEW_ret": round(tEW, 5), "note": "auto(buy-hold가중근사) 테마=" + "·".join(sorted(holdthemes))}, None


def upsert(row):
    header = "month,W_ret,sys_ret,themeEW_ret,note"
    comments = ["# month=YYYY-MM, 수익 소수. W=실보유 가중(auto), sys=선별18 EW 반사실, themeEW=보유테마버킷 EW.",
                "# auto=trackw_update.py 자동기입(buy-hold근사). 실현치 다르면 해당월 W_ret 수기수정 가능."]
    rows = {}
    if os.path.exists(LEDGER):
        for r in csv.DictReader(open(LEDGER, encoding="utf-8-sig")):
            m = (r.get("month") or "").strip()
            if not m or m.startswith("#"):
                continue
            try:
                float(r["W_ret"]); rows[m] = r
            except (ValueError, KeyError, TypeError):
                continue
    rows[row["month"]] = row
    with open(LEDGER, "w", encoding="utf-8-sig", newline="") as fh:
        fh.write(header + "\n")
        for c in comments:
            fh.write(c + "\n")
        for m in sorted(rows):
            r = rows[m]
            fh.write("%s,%s,%s,%s,%s\n" % (m, r["W_ret"], r["sys_ret"], r["themeEW_ret"], r.get("note", "")))
    return len(rows)


def _selftest():
    idx = pd.date_range("2025-01-31", periods=6, freq="ME")
    pan = pd.DataFrame({"005930":[100,110,121,133,146,160], "247540":[100,90,81,73,66,59]}, index=idx).astype(float)
    r = basket_ret(pan, ["005930","247540"], 1, {"005930":1,"247540":1})
    assert abs(r - ((0.10) + (-0.10))/2) < 1e-9, r       # EW = (+10% −10%)/2 = 0
    r2 = basket_ret(pan, ["005930","247540"], 1, {"005930":3,"247540":1})
    assert abs(r2 - (0.75*0.10 + 0.25*-0.10)) < 1e-9, r2  # 가중
    print("✅ trackw_update 셀프테스트 통과 (2/2): basket_ret EW·가중")


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true"); ap.add_argument("--month")
    a = ap.parse_args()
    if a.selftest:
        _selftest(); return
    TC = _load_src("theme_classify.py", "theme_classify")
    panel = load_panel()
    row, err = compute_row(panel, TC, a.month)
    if err:
        print("⚠️", err); return
    n = upsert(row)
    print(f"[충전] {row['month']}: W {row['W_ret']*100:+.2f}% · sys {row['sys_ret']*100:+.2f}% · themeEW {row['themeEW_ret']*100:+.2f}%  (총 {n}개월)")
    print("-"*58)
    TS = _load_src("trackw_score.py", "trackw_score")
    TS.report(TS.load(LEDGER))


if __name__ == "__main__":
    main()
