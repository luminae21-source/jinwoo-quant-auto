#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
fetch_kosdaq_pit_universe.py — 생존편향-통제 KOSDAQ 표본 일봉 수집 (PC 실행) · 2026-06-07

[PC 실행]  샌드박스는 네트워크 차단 → 진우 PC에서 실행. (finance-datareader 사용)

목적: ATR 손절 검증의 마지막 한계인 '생존편향'을 푼다. 기존 검증은 현재 워치리스트 12종목
   (=오늘의 승자)이라 5년 보유 평균이 후견편향으로 과대였다. 이를 없애려면 **그 시점에 존재했던
   광의 유니버스 + 이후 상장폐지·탈락 종목**까지 포함해야 한다. 테마의 PIT 소속 태그는 어디에도
   깨끗이 없으므로(테마=사후 라벨), universe 레벨에서 편향을 제거한다. 테마주는 그 고변동
   부분집합이라, 광의에서 손절 룰 결론이 서면 테마에도 견고하다.

방식:
  1) 현재 KOSDAQ(StockListing) 랜덤 N + 상폐 KOSDAQ(StockListing 'KRX-DELISTING') 랜덤 D (시드 고정)
     → 상폐 종목 포함이 핵심(파산·관리·동전주行 = 진짜 왼꼬리).
  2) 각 종목 일봉(OHLCV) 수집. 상폐주는 상폐 시점까지의 이력만 반환됨(자연스러운 종료).
  3) PIT 진입신호: 매월 첫 거래일, 그 시점 '거래중 + 최소가격·최소ADTV' 충족 종목만(동전주 잡음 제거).
  4) validate_atr_stop.py 입력 형식으로 저장 → 받아서 k 그리드 재검증(생존편향 통제).

출력: kosdaq_pit_daily.csv(code,date,open,high,low,close) · kosdaq_pit_entries.csv(code,entry_date,horizon_days)

사용(PC):
  pip install finance-datareader pandas
  python fetch_kosdaq_pit_universe.py                          # 현재200 + 상폐120, 2019~현재
  python fetch_kosdaq_pit_universe.py --n_current 250 --n_delisted 150 --start 2019-01-01
  # 이어서(샌드박스/PC 어디서나):
  python validate_atr_stop.py --daily kosdaq_pit_daily.csv --signals kosdaq_pit_entries.csv
  python validate_atr_stop.py --daily kosdaq_pit_daily.csv --signals kosdaq_pit_entries.csv --trailing
"""
import argparse, csv, datetime as dt, random, sys


def _col(df, *names):
    for n in names:
        if n in df.columns:
            return n
    return None


def get_listings(fdr, n_current, n_delisted, seed):
    rng = random.Random(seed)
    cur, deli = [], []
    # 현재 KOSDAQ
    try:
        lst = fdr.StockListing("KOSDAQ")
        cc = _col(lst, "Code", "Symbol"); nc = _col(lst, "Name")
        cur = [(str(r[cc]).zfill(6), str(r[nc])) for _, r in lst.iterrows() if cc]
    except Exception as e:
        print("[경고] KOSDAQ 상장목록 실패:", e)
    # 상폐(KRX-DELISTING) 중 KOSDAQ
    try:
        dl = fdr.StockListing("KRX-DELISTING")
        cc = _col(dl, "Symbol", "Code"); nc = _col(dl, "Name"); mc = _col(dl, "Market")
        for _, r in dl.iterrows():
            mk = str(r[mc]) if mc else ""
            if mc is None or "KOSDAQ" in mk.upper() or "코스닥" in mk:
                deli.append((str(r[cc]).zfill(6), str(r[nc])))
    except Exception as e:
        print("[경고] 상폐목록 실패(버전에 따라 'KRX-DELISTING' 미지원 가능):", e)

    rng.shuffle(cur); rng.shuffle(deli)
    cur = cur[:n_current]; deli = deli[:n_delisted]
    print("표본: 현재 KOSDAQ %d + 상폐 %d = %d종목 (시드 %d)" % (len(cur), len(deli), len(cur) + len(deli), seed))
    if not deli:
        print("⚠ 상폐 표본 0 — 생존편향 통제 효과 약화. FDR 버전 확인 권장.")
    return [(c, n, "cur") for c, n in cur] + [(c, n, "deli") for c, n in deli]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--n_current", type=int, default=200)
    ap.add_argument("--n_delisted", type=int, default=120)
    ap.add_argument("--start", default="2019-01-01")
    ap.add_argument("--end", default=None)
    ap.add_argument("--horizon", type=int, default=60)
    ap.add_argument("--min_price", type=float, default=1000, help="진입 최소가격(동전주 제외)")
    ap.add_argument("--min_adtv", type=float, default=1e8, help="진입 최소 ADTV(원), 기본 1억")
    ap.add_argument("--seed", type=int, default=7)
    ap.add_argument("--daily_out", default="kosdaq_pit_daily.csv")
    ap.add_argument("--entries_out", default="kosdaq_pit_entries.csv")
    a = ap.parse_args()
    try:
        import FinanceDataReader as fdr
    except ImportError:
        sys.exit("finance-datareader 미설치 → pip install finance-datareader")

    end = a.end or dt.date.today().isoformat()
    names = get_listings(fdr, a.n_current, a.n_delisted, a.seed)

    drows, erows = [], []
    ok = 0
    for i, (code, name, tag) in enumerate(names):
        try:
            df = fdr.DataReader(code, a.start, end)
        except Exception:
            continue
        if df is None or len(df) < 30:
            continue
        need = [c for c in ("Open", "High", "Low", "Close") if c in df.columns]
        if len(need) < 4:
            continue
        df = df.dropna(subset=need)
        has_vol = "Volume" in df.columns
        rows = []
        adtv20 = []           # 최근 20일 거래대금
        last_month = None
        for idx, r in df.iterrows():
            o, h, l, c = float(r["Open"]), float(r["High"]), float(r["Low"]), float(r["Close"])
            if min(o, h, l, c) <= 0:
                continue
            d = idx.date().isoformat() if hasattr(idx, "date") else str(idx)[:10]
            rows.append((code, d, o, h, l, c))
            val = (c * float(r["Volume"])) if has_vol else c * 0
            adtv20.append(val)
            if len(adtv20) > 20:
                adtv20.pop(0)
            ym = d[:7]
            if ym != last_month:               # 매월 첫 거래일 = PIT 진입 후보
                adtv = sum(adtv20) / len(adtv20) if adtv20 else 0
                if c >= a.min_price and (not has_vol or adtv >= a.min_adtv):
                    erows.append((code, d, a.horizon))
                last_month = ym
        if rows:
            drows.extend(rows); ok += 1
        if (i + 1) % 50 == 0:
            print("  ...%d/%d 처리 (수집성공 %d, 일봉 %d행)" % (i + 1, len(names), ok, len(drows)))

    with open(a.daily_out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh); w.writerow(["code", "date", "open", "high", "low", "close"]); w.writerows(drows)
    with open(a.entries_out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.writer(fh); w.writerow(["code", "entry_date", "horizon_days"]); w.writerows(erows)
    print("\n수집성공 %d종목 | 일봉 %d행 | PIT진입 %d신호" % (ok, len(drows), len(erows)))
    print("저장: %s, %s" % (a.daily_out, a.entries_out))
    print("다음: python validate_atr_stop.py --daily %s --signals %s [--trailing]"
          % (a.daily_out, a.entries_out))


if __name__ == "__main__":
    main()
