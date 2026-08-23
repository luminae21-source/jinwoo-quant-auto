# -*- coding: utf-8 -*-
"""엔진 04 사냥터 딥밸류 — forward 원장 (2026-08-23 개설)
검증 근거: 사냥터_기획/진우_사냥터_검증종합_한장.md (30년·상폐반영·IN/OOS·look-ahead 점검 통과)

규칙 (검증문서 그대로 · 이 스크립트가 판단, 사람이 고르지 않는다)
  진입 게이트 : KOSPI < MA200 (하락장에서만 산다)
  후보 조건   : 저PBR 하위20% ∩ 이격(종가/MA200) < 0.85 ∩ 20일수익 > 0(턴)
  선정        : 10~15종 분산 (점수=이격 낮은 순)
  보유        : 승자 미절단 · 스톱 없음 · 최대 3년 · MDD −70% 감내
  익절        : 이격 ≥ 1.5 or +100% or PBR ≥ 1.0 — 먼저 오는 것

원장의 목적: **안 샀다도 기록한다.** 진입 기회가 드문 규칙(최근 3년 하락장 27%)이라
            공백을 남기면 "규칙대로 안 산 것"과 "그냥 안 돌린 것"을 구분할 수 없다.

  py 엔진04_사냥터원장.py --self-test
  py 엔진04_사냥터원장.py            # 오늘자 1행 기록
"""
import argparse, csv, os, sys
import pandas as pd, numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
LEDGER = os.path.join(HERE, "엔진04_사냥터_원장.csv")
IDX = os.path.join(HERE, "kospi_index_daily.csv")
PANEL = os.path.join(HERE, "스타일패널_DART.csv")
PX = os.path.join(HERE, "종목일봉_30년_KOSPI.csv")
MA_N, TURN_N = 200, 20
GAP_BUY, PBR_PCT = 0.85, 0.20
N_MIN, N_MAX = 10, 15
COLS = ["date", "regime", "kospi", "ma200", "gap", "buyable",
        "n_universe", "n_candidate", "picks", "note"]


def regime_of(idx_path):
    k = pd.read_csv(idx_path, encoding="utf-8-sig")
    k.columns = [c.strip().lower() for c in k.columns]
    k["date"] = pd.to_datetime(k["date"])
    k = k.sort_values("date")
    ma = k["close"].rolling(MA_N).mean().iloc[-1]
    last = float(k["close"].iloc[-1])
    return str(k["date"].iloc[-1].date()), last, float(ma), last / ma


def recent_prices(px_path, months=18):
    """메모리 안전: 청크로 읽어 최근 구간만 남긴다 (VM 2GB 대응)"""
    cut = (pd.Timestamp.today() - pd.DateOffset(months=months)).strftime("%Y-%m-%d")
    keep = []
    for ch in pd.read_csv(px_path, encoding="utf-8-sig", dtype={"code": str},
                          usecols=["date", "code", "close"], chunksize=1_500_000):
        ch = ch[ch["date"] >= cut]
        if len(ch):
            keep.append(ch)
    if not keep:
        return pd.DataFrame(columns=["date", "code", "close"])
    d = pd.concat(keep, ignore_index=True)
    d["date"] = pd.to_datetime(d["date"])
    return d[d["close"] > 0]


def candidates(px: pd.DataFrame, panel: pd.DataFrame):
    """저PBR 하위20% ∩ 이격<0.85 ∩ 20일수익>0"""
    w = px.pivot_table(index="date", columns="code", values="close", aggfunc="last").sort_index()
    if len(w) < MA_N + 1:
        return pd.DataFrame(), 0
    ma = w.rolling(MA_N).mean().iloc[-1]
    last = w.iloc[-1]
    gap = (last / ma).dropna()
    turn = (last / w.iloc[-1 - TURN_N] - 1).dropna() if len(w) > TURN_N else pd.Series(dtype=float)
    p = panel.copy()
    p["pbr"] = 1 / pd.to_numeric(p["bp"], errors="coerce")
    p = p[p["pbr"] > 0].set_index("code")
    cut = p["pbr"].quantile(PBR_PCT)
    df = pd.DataFrame({"pbr": p["pbr"], "name": p["name"]}).join(
        gap.rename("gap"), how="inner").join(turn.rename("turn"), how="inner")
    n_uni = len(df)
    sel = df[(df.pbr <= cut) & (df.gap < GAP_BUY) & (df.turn > 0)].sort_values("gap")
    return sel, n_uni


def self_test():
    # regime 계산
    idx = pd.DataFrame({"date": pd.date_range("2024-01-01", periods=300, freq="D"),
                        "close": np.r_[np.full(250, 100.0), np.full(50, 80.0)]})
    idx.to_csv("/tmp/_idx.csv", index=False)
    _, last, ma, gap = regime_of("/tmp/_idx.csv")
    assert last == 80.0 and gap < 1.0, (last, ma, gap)
    # 후보 필터: 3종 중 조건 만족은 1종만
    dates = pd.date_range("2025-01-01", periods=220, freq="B")
    rows = []
    for code, path in (("000001", 0.80), ("000002", 1.20), ("000003", 0.80)):
        base = np.full(len(dates), 100.0)
        base[-1] = 100 * path                      # 이격 결정
        if code == "000003":
            base[-1] = 60.0                        # 이격 낮지만
            base[-1 - TURN_N] = 50.0               # 20일수익 +20% (턴 O)
        rows += [{"date": d, "code": code, "close": c} for d, c in zip(dates, base)]
    px = pd.DataFrame(rows)
    panel = pd.DataFrame({"code": ["000001", "000002", "000003"],
                          "name": ["A", "B", "C"], "bp": [2.0, 0.5, 2.0]})   # pbr 0.5,2.0,0.5
    sel, n = candidates(px, panel)
    assert n == 3, n
    assert list(sel.index) == ["000003"], list(sel.index)   # 000001은 턴 미충족
    # 원장 스키마
    assert COLS[0] == "date" and "picks" in COLS
    print("self-test 4/4 통과")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()

    asof, kospi, ma, gap = regime_of(IDX)
    buyable = kospi < ma
    print(f"[국면] {asof} KOSPI {kospi:.1f} vs MA200 {ma:.1f} · 이격 {gap:.3f} → "
          f"{'하락장 — 진입 가능' if buyable else '상승장 — 규칙상 미진입'}")

    if os.path.exists(LEDGER):
        old = pd.read_csv(LEDGER, dtype=str)
        if asof in set(old["date"]) and not a.force:
            print(f"[SKIP] {asof} 이미 기록됨 (재기록은 --force)")
            return
    picks, n_uni, n_cand, note = "", 0, 0, ""
    if not buyable:
        note = "하락장 아님 — 규칙상 매수 없음(안 산 것도 기록한다)"
    else:
        if not os.path.exists(PANEL):
            note = "패널 없음 — 후보 산출 불가"
        else:
            panel = pd.read_csv(PANEL, dtype={"code": str})
            panel = panel[panel.ym == sorted(panel.ym.unique())[-1]]
            print("[가격] 최근 18개월 로드 중...", flush=True)
            px = recent_prices(PX)
            sel, n_uni = candidates(px, panel)
            n_cand = len(sel)
            top = sel.head(N_MAX)
            picks = ";".join(top.index.tolist())
            note = (f"후보 {n_cand}종 중 상위 {len(top)}종 선정"
                    if n_cand >= N_MIN else f"후보 {n_cand}종 — 최소 {N_MIN}종 미달로 진입 보류")
            if n_cand < N_MIN:
                picks = ""
            print(f"[후보] 유니버스 {n_uni} · 조건 통과 {n_cand} → {note}")

    row = {"date": asof, "regime": "하락장" if buyable else "상승장",
           "kospi": round(kospi, 2), "ma200": round(ma, 2), "gap": round(gap, 4),
           "buyable": int(buyable), "n_universe": n_uni, "n_candidate": n_cand,
           "picks": picks, "note": note}
    new = not os.path.exists(LEDGER)
    with open(LEDGER, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=COLS)
        if new:
            w.writeheader()
        w.writerow(row)
    print(f"기록: {os.path.basename(LEDGER)} — {row['regime']} · {note}")


if __name__ == "__main__":
    main()
