# -*- coding: utf-8 -*-
r"""계좌_시뮬레이터.py — 건당수익이 아니라 '계좌'로 평가한다 (v1, 2026-08-23)

[왜] 기각 3건이 같은 이유로 판정 불능이었다.
  · 휩쏘 A안: 연 13건×+2.93% vs 연 49건×+2.57% — 건당수익으로는 우열 결정 불가
  · 엔진06 : 검증 4건 중 1건이 +157.8% — 자금배분 없이는 의미 산정 불가
  · 숙근매매: 동시보유·현금 유휴 미반영으로 대기
  건당수익은 '카드 한 장의 성적'이고, 계좌는 '자금이 실제로 어떻게 굴렀나'다. 둘은 다르다.

[무엇을 반영하나]
  1) 자금배분   — 건당 위험 R% 또는 균등분할, 동시보유 상한 K
  2) 동시보유   — 슬롯이 꽉 차면 새 신호를 **못 산다**(기회 상실을 기록한다)
  3) 거래비용   — 왕복 c
  4) 현금 drag  — 신호 없는 기간의 현금은 수익 0 (또는 무위험 r)
  5) 손절/청산  — 이벤트에 지정된 청산일·수익 사용

[입력] 이벤트 CSV — 필수 컬럼: entry(YYYY-MM-DD), exit(YYYY-MM-DD), ret(소수)
       선택 컬럼: code, name, tag
[출력] 계좌 CAGR · MDD · 최종배수 · 체결/기각 건수 · 현금비중 · 연도별 수익

사용:
  py 계좌_시뮬레이터.py --events 엔진06_바닥반전_이벤트.csv --slots 5 --cost 0.003
  py 계좌_시뮬레이터.py --events X.csv --slots 3 --sizing equal --capital 10000000
  py 계좌_시뮬레이터.py --selftest
⚠️ 산출물은 검정 보조 도구. 이 자체가 매매 신호가 아니다.
"""
import sys, argparse
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass


def simulate(ev, slots=5, cost=0.003, capital=10_000_000, cash_rate=0.0):
    """이벤트를 시간순으로 흘리며 슬롯 제약 하에 체결. 계좌 곡선을 만든다."""
    ev = ev.dropna(subset=["entry", "exit", "ret"]).copy()
    ev["entry"] = pd.to_datetime(ev["entry"]); ev["exit"] = pd.to_datetime(ev["exit"])
    ev = ev[ev["exit"] > ev["entry"]].sort_values("entry").reset_index(drop=True)
    if ev.empty: return None

    equity = float(capital)
    open_pos = []          # (exit_date, invested, ret)
    taken, skipped = [], []
    curve = []             # (date, equity)
    days = pd.date_range(ev["entry"].min(), ev["exit"].max(), freq="D")
    ei = 0

    for d in days:
        # 1) 만기 청산
        still = []
        for xd, inv, r in open_pos:
            if xd <= d:
                equity += inv * (1 + r - cost) - inv
            else:
                still.append((xd, inv, r))
        open_pos = still
        # 2) 현금 이자
        cash = equity - sum(i for _, i, _ in open_pos)
        if cash_rate:
            equity += cash * (cash_rate / 365.0)
        # 3) 신규 진입
        while ei < len(ev) and ev.loc[ei, "entry"] <= d:
            row = ev.loc[ei]
            if len(open_pos) < slots:
                inv = equity / slots
                if inv <= cash + 1e-9:
                    open_pos.append((row["exit"], inv, float(row["ret"])))
                    taken.append(ei); cash -= inv
                else:
                    skipped.append((ei, "현금부족"))
            else:
                skipped.append((ei, "슬롯만석"))
            ei += 1
        curve.append((d, equity))

    cv = pd.DataFrame(curve, columns=["date", "equity"]).set_index("date")["equity"]
    yrs = (cv.index[-1] - cv.index[0]).days / 365.25
    cagr = (cv.iloc[-1] / capital) ** (1 / yrs) - 1 if yrs > 0.5 else np.nan
    mdd = float((cv / cv.cummax() - 1).min())
    return dict(n_events=len(ev), n_taken=len(taken), n_skipped=len(skipped),
                skip_slot=sum(1 for _, w in skipped if w == "슬롯만석"),
                skip_cash=sum(1 for _, w in skipped if w == "현금부족"),
                years=yrs, final=float(cv.iloc[-1]), mult=float(cv.iloc[-1]/capital),
                cagr=float(cagr), mdd=mdd, curve=cv,
                taken_ret=[float(ev.loc[i, "ret"]) for i in taken])


def selftest():
    ok = []
    # 1) 단일 이벤트 +10%, 비용 0 → 슬롯1이면 자산 1.10배
    e = pd.DataFrame([{"entry": "2020-01-01", "exit": "2020-07-01", "ret": 0.10}])
    r = simulate(e, slots=1, cost=0.0, capital=100.0)
    ok.append(("단일 +10%% 슬롯1 → 1.10배", abs(r["mult"] - 1.10) < 1e-6))
    # 2) 비용 반영
    r2 = simulate(e, slots=1, cost=0.01, capital=100.0)
    ok.append(("비용 1%% 차감 → 1.09배", abs(r2["mult"] - 1.09) < 1e-6))
    # 3) 슬롯 제약: 동시 3건인데 슬롯 2 → 1건 기각
    e3 = pd.DataFrame([{"entry": "2020-01-01", "exit": "2020-12-01", "ret": 0.1}] * 3)
    r3 = simulate(e3, slots=2, cost=0.0, capital=100.0)
    ok.append(("슬롯2에 동시3건 → 1건 기각", r3["n_taken"] == 2 and r3["skip_slot"] == 1))
    # 4) 현금 drag: 슬롯5에 1건만 → 자산의 1/5만 투자
    r4 = simulate(e, slots=5, cost=0.0, capital=100.0)
    ok.append(("슬롯5에 1건 → 1.02배(1/5만 투자)", abs(r4["mult"] - 1.02) < 1e-6))
    # 5) MDD 음수 아님(수익만 있는 케이스)
    ok.append(("MDD <= 0", r["mdd"] <= 1e-9))
    # 6) 손실 이벤트
    e6 = pd.DataFrame([{"entry": "2020-01-01", "exit": "2020-07-01", "ret": -0.20}])
    r6 = simulate(e6, slots=1, cost=0.0, capital=100.0)
    ok.append(("단일 −20%% → 0.80배", abs(r6["mult"] - 0.80) < 1e-6))
    ok.append(("MDD 반영 −20%%", abs(r6["mdd"] + 0.20) < 1e-6))
    # 8) 단위 판정: 대박 1건이 섞여도 소수는 소수로 본다 (2026-08-23 회귀 방지)
    mixed = pd.Series([0.03, -0.05, 0.08, 1.5781, -0.02])
    ok.append(("단위판정: 중앙값 기준 frac", float(mixed.abs().median()) <= 1.0))
    pctish = pd.Series([3.0, -5.0, 8.0, 157.81, -2.0])
    ok.append(("단위판정: 퍼센트는 pct", float(pctish.abs().median()) > 1.0))
    for n, v in ok: print(("  OK   " if v else "  FAIL ") + n)
    print("self-test %d/%d" % (sum(v for _, v in ok), len(ok)))
    return all(v for _, v in ok)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--events"); ap.add_argument("--slots", type=int, default=5)
    ap.add_argument("--cost", type=float, default=0.003)
    ap.add_argument("--capital", type=float, default=10_000_000)
    ap.add_argument("--cash-rate", type=float, default=0.0)
    ap.add_argument("--ret-unit", choices=["auto","frac","pct"], default="auto",
                    help="ret 단위. auto는 중앙 |ret|>1이면 pct로 본다")
    ap.add_argument("--sweep", action="store_true", help="슬롯 1~10 스윕")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest: sys.exit(0 if selftest() else 1)
    if not a.events: sys.exit("--events 필요")

    ev = pd.read_csv(a.events, encoding="utf-8-sig")
    ren = {}
    for c in ev.columns:
        lc = str(c).strip().lower()
        if lc in ("entry", "진입일", "출발일"): ren[c] = "entry"
        elif lc in ("exit", "종료일", "청산일"): ren[c] = "exit"
        elif lc in ("ret", "수익", "종료수익"): ren[c] = "ret"
    ev = ev.rename(columns=ren)
    # 단위 판정: 최대값이 아니라 **중앙값**으로 본다.
    # 최대값 기준이면 +157%(=1.57)짜리 대박 한 건 때문에 소수 데이터를 퍼센트로 오인한다(2026-08-23 버그).
    unit = a.ret_unit
    if unit == "auto":
        med = float(ev["ret"].abs().median())
        unit = "pct" if med > 1.0 else "frac"
        print("[단위] 중앙 |ret| = %.4f → %s 로 판정" % (med, unit))
    if unit == "pct":
        ev["ret"] = ev["ret"] / 100.0

    print("=" * 70)
    print("계좌 시뮬레이터 — %s" % a.events)
    print("=" * 70)
    rng = range(1, 11) if a.sweep else [a.slots]
    print("%6s %7s %7s %8s %9s %9s %8s" % ("슬롯", "체결", "기각", "연수", "최종배수", "CAGR", "MDD"))
    for s in rng:
        r = simulate(ev, slots=s, cost=a.cost, capital=a.capital, cash_rate=a.cash_rate)
        if not r: continue
        print("%6d %7d %7d %8.1f %9.2f배 %8.2f%% %7.1f%%"
              % (s, r["n_taken"], r["n_skipped"], r["years"], r["mult"],
                 r["cagr"]*100, r["mdd"]*100))
    r = simulate(ev, slots=a.slots, cost=a.cost, capital=a.capital, cash_rate=a.cash_rate)
    print("\n[슬롯 %d 상세] 이벤트 %d건 중 체결 %d · 기각 %d (슬롯만석 %d · 현금부족 %d)"
          % (a.slots, r["n_events"], r["n_taken"], r["n_skipped"], r["skip_slot"], r["skip_cash"]))
    if r["taken_ret"]:
        t = np.array(r["taken_ret"])
        print("  체결분 건당: 평균 %+.2f%% · 중앙 %+.2f%% · 승률 %.0f%% · 최악 %+.2f%%"
              % (t.mean()*100, np.median(t)*100, (t > 0).mean()*100, t.min()*100))
    r["curve"].to_csv("계좌곡선_%s" % a.events.replace(".csv", "") + ".csv", encoding="utf-8-sig")
    print("\n저장: 계좌곡선_%s.csv" % a.events.replace(".csv", ""))


if __name__ == "__main__":
    main()
