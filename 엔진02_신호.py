# -*- coding: utf-8 -*-
"""엔진 02 forward 신호 생성기 — 사양서 v2 구현 (2026-08-22 동결)
사양서: 실전준비/forward_동결사양서_v2.md
  §3 팩터: ep bp roe div (스타일패널_DART.csv) · 월별 횡단면 1%/99% 윈저 → z
  §4 본선: z(bp)+z(ep)+z(roe)+0.5*z(div) → 상위 30, 동일가중, 상한 6%
  §5 병행관찰 2종: v1등가중(배당 1.0) · 배당단독 top30  (기록만, 배분 아님)
  §6 방어: KOSPI < 10개월 MA 이면 현금 50%
출력: 실전준비/forward_ledger_v2.csv (월 1행, 3트랙 명단 동시 기록)

  py 엔진02_신호.py --self-test
  py 엔진02_신호.py              # 패널 최신월 기준 1행 생성
  py 엔진02_신호.py --force      # 같은 달 재생성(덮어씀)
"""
import argparse, csv, os, sys
import pandas as pd, numpy as np

HERE = os.path.dirname(os.path.abspath(__file__))
PANEL = os.path.join(HERE, "스타일패널_DART.csv")
IDX = os.path.join(HERE, "kospi_index_daily.csv")
LEDGER = os.path.join(HERE, "실전준비", "forward_ledger_v2.csv")
SPEC = "forward_동결사양서_v2.md (2026-08-22 동결)"
N_PICK, CAP, WIN = 30, 0.06, 0.01
W_DIV_MAIN, W_DIV_V1 = 0.5, 1.0          # §4 본선 / §5 병행


def zwin(s: pd.Series) -> pd.Series:
    """1%/99% 윈저 후 z-score (사양서 §3)"""
    s = pd.to_numeric(s, errors="coerce")
    lo, hi = s.quantile(WIN), s.quantile(1 - WIN)
    s = s.clip(lo, hi)
    sd = s.std()
    return (s - s.mean()) / sd if sd and sd > 0 else s * 0


def score(df: pd.DataFrame, w_div: float) -> pd.Series:
    return df.z_bp + df.z_ep + df.z_roe + w_div * df.z_div


def defense_on(idx_path: str, asof_ym: str):
    """KOSPI < 10개월 이동평균이면 현금 50% (사양서 §6). (발동여부, 지수, MA)"""
    if not os.path.exists(idx_path):
        return None, None, None
    k = pd.read_csv(idx_path, encoding="utf-8-sig")
    k.columns = [c.strip().lower() for c in k.columns]
    k["date"] = pd.to_datetime(k["date"])
    m = k.sort_values("date").set_index("date")["close"].resample("ME").last().dropna()
    m = m[m.index <= pd.Timestamp(asof_ym + "-01") + pd.offsets.MonthEnd(0)]
    if len(m) < 10:
        return None, None, None
    ma = m.rolling(10).mean().iloc[-1]
    return bool(m.iloc[-1] < ma), float(m.iloc[-1]), float(ma)


def build(panel: pd.DataFrame):
    d = panel.dropna(subset=["ep", "bp", "roe", "div"]).copy()
    for c in ("ep", "bp", "roe", "div"):
        d["z_" + c] = zwin(d[c])
    out = {}
    out["main"] = d.assign(s=score(d, W_DIV_MAIN)).nlargest(N_PICK, "s")
    out["v1_eq"] = d.assign(s=score(d, W_DIV_V1)).nlargest(N_PICK, "s")
    out["div_only"] = d.assign(s=d.z_div).nlargest(N_PICK, "s")
    return d, out


def self_test():
    n = 200
    rng = np.random.default_rng(20260822)                # 고정 시드 (재현 가능)
    df = pd.DataFrame({
        "code": [f"{i:06d}" for i in range(n)], "name": [f"N{i}" for i in range(n)],
        "ep": rng.normal(0.06, 0.03, n), "bp": rng.normal(1.0, 0.5, n),
        "roe": rng.normal(0.08, 0.05, n), "div": rng.normal(0.025, 0.02, n),
    })
    d, sel = build(df)
    assert len(sel["main"]) == N_PICK and len(sel["div_only"]) == N_PICK
    # 가중이 실제로 명단을 바꾸는가 (0.5 vs 1.0)
    diff = len(set(sel["main"]["code"]) ^ set(sel["v1_eq"]["code"]))
    assert diff > 0, "가중 0.5/1.0이 동일 결과 — 버그"
    # 배당단독은 배당 최상위를 골라야 한다
    assert sel["div_only"]["div"].min() >= df["div"].nlargest(N_PICK).min() - 1e-12
    # 윈저: 극단값 1개가 z 평균을 지배하지 않음
    s = pd.Series([1.0] * 98 + [1e9, -1e9])
    assert abs(zwin(s)).max() < 20
    # 결측 행은 제외
    df3 = df.copy(); df3.loc[0, "roe"] = np.nan
    d3, _ = build(df3); assert len(d3) == n - 1
    print("self-test 5/5 통과")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--force", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return self_test()

    if not os.path.exists(PANEL):
        sys.exit("[중단] 스타일패널_DART.csv 없음 — py 스타일패널_DART.py 먼저")
    p = pd.read_csv(PANEL, dtype={"code": str})
    ym = sorted(p["ym"].unique())[-1]
    p = p[p["ym"] == ym]
    print(f"[패널] {ym} · {len(p)}종")

    if os.path.exists(LEDGER):
        old = pd.read_csv(LEDGER, dtype=str)
        if ym in set(old["ym"]) and not a.force:
            sys.exit(f"[중단] {ym} 이미 기록됨 — 덮어쓰려면 --force\n"
                     f"  (패널이 갱신되지 않았는데 재실행하면 트랙이 멈춘 채 진행 중으로 오인된다)")
    else:
        old = None

    d, sel = build(p)
    print(f"  자격 종목(팩터 완비) {len(d)}종")
    dof, px, ma = defense_on(IDX, ym)
    cash = 0.5 if dof else 0.0
    print(f"  방어: KOSPI {px:.1f} vs 10개월MA {ma:.1f} → " +
          ("🛡 현금 50%" if dof else "정상 100% 투자") if px else "  방어: 지수 데이터 없음")

    row = {"ym": ym, "spec": SPEC, "n_universe": len(p), "n_eligible": len(d),
           "defense_cash": cash, "n_pick": N_PICK, "cap": CAP}
    for k, label in (("main", "본선_배당0.5"), ("v1_eq", "관찰_v1등가중"), ("div_only", "관찰_배당단독")):
        row[label] = ";".join(sel[k]["code"].tolist())
    m = sel["main"]
    row["본선_평균PBR"] = round(1 / pd.to_numeric(m.bp).mean(), 3)
    row["본선_평균ROE"] = round(pd.to_numeric(m.roe).mean(), 4)
    row["본선_평균DIV"] = round(pd.to_numeric(m["div"]).mean(), 4)
    row["본선_v1중복"] = len(set(sel["main"].code) & set(sel["v1_eq"].code))
    row["비고"] = "v2 첫 기록" if old is None else ""

    os.makedirs(os.path.dirname(LEDGER), exist_ok=True)
    new = not os.path.exists(LEDGER)
    with open(LEDGER, "a", encoding="utf-8", newline="") as f:
        w = csv.DictWriter(f, fieldnames=list(row))
        if new:
            w.writeheader()
        w.writerow(row)

    print(f"\n[본선 30종] {', '.join(m['name'].head(12).tolist())} …")
    print(f"  평균 PBR {row['본선_평균PBR']} · ROE {row['본선_평균ROE']*100:.1f}% · DIV {row['본선_평균DIV']*100:.2f}%")
    print(f"  v1등가중과 중복 {row['본선_v1중복']}/30 → 배당 가중 0.5가 {30-row['본선_v1중복']}종을 바꿨다")
    print(f"저장: {os.path.relpath(LEDGER, HERE)}")


if __name__ == "__main__":
    main()
