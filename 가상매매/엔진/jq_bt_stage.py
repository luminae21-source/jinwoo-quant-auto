# -*- coding: utf-8 -*-
"""
jq_bt_stage.py — 백테스트 단계별 실행 + 체크포인트

긴 백테스트가 중단돼도 이어서 돌릴 수 있게 각 단계 결과를 저장한다.
(PC에서는 가상매매_백테스트.py 를 그냥 한 번에 돌리면 된다. 이건 재개용.)

  py jq_bt_stage.py 1   기본/통합 + 벤치마크 + IS/OOS + 국면
  py jq_bt_stage.py 2   파라미터 민감도
  py jq_bt_stage.py 3   할로윈 ON/OFF + 워크포워드
  py jq_bt_stage.py 4   다중검정 보정 + 문서/차트 생성
"""
import os, sys, math, pickle, itertools
import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jq_paper_core as C
import jq_backtest_core as B
from jq_paper_core import CFG, PriceStore, DIR_BT, DIR_VERIFY, isnan

# 중간 체크포인트는 임시폴더에 둔다 (대용량 · 재생성 가능 · 산출물 아님).
import tempfile
ST = os.path.join(tempfile.gettempdir(), "jq_bt_state.pkl")
GRID = dict(MA_SHORT=[20, 25, 60], ATR_STOP=[1.5, 2.0, 2.5], TIME_STOP_DAYS=[10, 20])
# 워크포워드는 매 윈도우마다 격자 전체를 재학습해야 해서 계산량이 크다.
# 핵심 축(MA_SHORT x ATR_STOP)만으로 선택한다. TIME_STOP은 기본값 고정.
# (민감도 격자에서 TIME_STOP의 영향이 단조적이고 작음을 이미 확인했다.)
WF_GRID = dict(MA_SHORT=[20, 25, 60], ATR_STOP=[1.5, 2.0, 2.5])


def pf(v, sp="{:+.2f}%", pct=True):
    if v is None or isnan(v):
        return "—"
    return sp.format(v * 100 if pct else v)


def setup():
    B.load_ind_cache()          # 이전 단계에서 계산한 지표 재사용 (재계산 방지)
    store = PriceStore("local")
    store.load_local()
    uni = {c: "KOSPI" for c in store.universe("KOSPI", CFG["UNIVERSE_TOP_N"])}
    uni.update({c: "KOSDAQ" for c in store.universe("KOSDAQ", CFG["KOSDAQ_TOP_N"])})
    days = [d for d in store.trading_days("KOSPI")
            if pd.Timestamp(d) >= pd.Timestamp("2020-02-01")]
    idx, inotes = C.load_kospi_index()
    phase = C.phase_series(idx)
    cpanel, _, _ = C.load_coupling_panel()
    coup = C.coupling_series(cpanel)
    return store, uni, days, phase, coup, inotes


def load():
    with open(ST, "rb") as f:
        return pickle.load(f)


def save(d):
    with open(ST, "wb") as f:
        pickle.dump(d, f, protocol=4)
    B.save_ind_cache()


def stage1():
    store, uni, days, phase, coup, inotes = setup()
    kw = dict(phase=phase, coup=coup)
    split = int(len(days) * 0.7)
    IS, OOS = days[:split], days[split:]
    td, ed, meta = B.backtest(store, uni, days, apply_cost=True, **kw)
    td_nc, ed_nc, _ = B.backtest(store, uni, days, apply_cost=False, **kw)
    perf = {tr: B.perf(ed, td, tr) for tr in ("L", "S", "TOTAL")}
    nocost = B.perf(ed_nc, td_nc, "TOTAL")
    bmk = {m: B.benchmark(store, m, days) for m in ("KOSPI", "KOSDAQ")}
    tests = []
    for tr in ("L", "S", "TOTAL"):
        t = td if tr == "TOTAL" else td[td["track"] == tr]
        x = pd.to_numeric(t["net_pnl"], errors="coerce").dropna()
        tt, pp, n, _ = B.ttest_1samp(x, 0.0)
        tests.append((f"거래당순손익≠0 ({tr})", tt, pp, n))
    seg = {}
    for nm, dd in (("IS", IS), ("OOS", OOS)):
        t_, e_, _ = B.backtest(store, uni, dd, apply_cost=True, **kw)
        seg[nm] = (t_, e_)
        x = pd.to_numeric(t_["net_pnl"], errors="coerce").dropna()
        tt, pp, n, _ = B.ttest_1samp(x, 0.0)
        tests.append((f"거래당순손익≠0 ({nm})", tt, pp, n))
    phase_rows = []
    for axis, col in (("A 추세", "phase_trend"), ("B 변동성", "phase_vol"),
                      ("C 커플링", "coupling_state"), ("D 드로다운", "phase_dd")):
        for st_ in sorted(td[col].dropna().unique()):
            for tr in ("L", "S"):
                t = td[(td[col] == st_) & (td["track"] == tr)]
                if not len(t):
                    continue
                net = pd.to_numeric(t["net_pnl"], errors="coerce").dropna()
                r = pd.to_numeric(t["r_multiple"], errors="coerce").dropna()
                w, l = net[net > 0], net[net <= 0]
                phase_rows.append(dict(
                    축=axis, 국면=st_, 트랙=tr, n=len(t), 순손익=float(net.sum()),
                    승률=float(len(w) / len(net)) if len(net) else float("nan"),
                    손익비=float(w.mean() / abs(l.mean()))
                    if len(w) and len(l) and l.mean() != 0 else float("nan"),
                    평균R=float(r.mean()) if len(r) else float("nan"),
                    판정="통계적 결론 불가(n<30)" if len(t) < 30 else "참고"))
    sv = B.survivorship_report(store)
    save(dict(td=td, ed=ed, meta=meta, perf=perf, nocost=nocost, bmk=bmk,
              seg=seg, phase_rows=phase_rows, tests=tests, sv=sv,
              days=days, IS=IS, OOS=OOS, inotes=inotes))
    tot = perf["TOTAL"]
    print(f"[stage1] 완료. 거래 {len(td)}건")
    print(f"  전략 CAGR {pf(tot['CAGR'])} vs 코스피 B&H {pf(bmk['KOSPI']['CAGR'])}"
          f" -> {pf(tot['CAGR']-bmk['KOSPI']['CAGR'])}p")


def stage2():
    """재개 가능: 조합 하나 끝날 때마다 저장. 중단돼도 다시 돌리면 남은 것만 한다."""
    D = load()
    store, uni, days, phase, coup, _ = setup()
    kw = dict(phase=phase, coup=coup)
    rows = D.get("sens_rows", [])
    done = {tuple(sorted(r[k] for k in GRID)) for r in rows}
    combos = list(itertools.product(*GRID.values()))
    D["n_combos"] = len(combos)
    for vals in combos:
        p = dict(zip(GRID.keys(), vals))
        if tuple(sorted(p.values())) in done and any(
                all(r[k] == p[k] for k in GRID) for r in rows):
            continue
        row = dict(p)
        for nm, dd in (("IS", D["IS"]), ("OOS", D["OOS"])):
            t_, e_, _ = B.backtest(store, uni, dd, params=p, apply_cost=True, **kw)
            pp_ = B.perf(e_, t_, "TOTAL")
            row[f"{nm}_CAGR"] = pp_["CAGR"] if pp_ else float("nan")
            row[f"{nm}_n"] = pp_["거래수"] if pp_ else 0
        rows.append(row)
        D["sens_rows"] = rows
        save(D)
        print(f"  [{len(rows)}/{len(combos)}] {p} -> OOS {pf(row['OOS_CAGR'])}")
    D["sens"] = pd.DataFrame(rows)
    save(D)
    print(f"[stage2] {'완료' if len(rows) == len(combos) else '진행중'}. "
          f"{len(rows)}/{len(combos)}조합")


def stage3():
    D = load()
    store, uni, days, phase, coup, _ = setup()
    kw = dict(phase=phase, coup=coup)
    hal = D.get("hal")
    if not hal:
        hal = {}
        for nm, dd in (("IS", D["IS"]), ("OOS", D["OOS"])):
            for hv in (False, True):
                t_, e_, _ = B.backtest(store, uni, dd, halloween=hv,
                                       apply_cost=True, **kw)
                hal[(nm, hv)] = B.perf(e_, t_, "TOTAL")
        D["hal"] = hal
        save(D)
    ho, hf = hal[("OOS", True)], hal[("OOS", False)]
    D["hal_adopt"] = bool(ho and hf and ho["CAGR"] > hf["CAGR"]
                          and ho["Sharpe"] > hf["Sharpe"])
    print(f"[할로윈] OOS ON {pf(ho['CAGR'])} vs OFF {pf(hf['CAGR'])} "
          f"-> {'채택 검토' if D['hal_adopt'] else '기각(OFF 유지)'}")

    # 워크포워드 (3년 학습 -> 1년 검증)
    ann = 252
    days_ = D["days"]
    combos = list(itertools.product(*WF_GRID.values()))
    rows = D.get("wf_rows", [])
    start = len(rows) * ann
    while start + ann * 4 <= len(days_):
        tr = days_[start:start + ann * 3]
        te = days_[start + ann * 3:start + ann * 4]
        best, best_c = None, None
        for vals in combos:
            p = dict(zip(WF_GRID.keys(), vals))
            t_, e_, _ = B.backtest(store, uni, tr, params=p, apply_cost=True, **kw)
            pp = B.perf(e_, t_, "TOTAL")
            if pp and not isnan(pp["CAGR"]) and (best is None or pp["CAGR"] > best):
                best, best_c = pp["CAGR"], p
        t_, e_, _ = B.backtest(store, uni, te, params=best_c, apply_cost=True, **kw)
        sel = B.perf(e_, t_, "TOTAL")
        t2, e2, _ = B.backtest(store, uni, te, apply_cost=True, **kw)
        fix = B.perf(e2, t2, "TOTAL")
        rows.append(dict(학습=f"{pd.Timestamp(tr[0]).date()}~{pd.Timestamp(tr[-1]).date()}",
                         검증=f"{pd.Timestamp(te[0]).date()}~{pd.Timestamp(te[-1]).date()}",
                         선택파라미터=str(best_c), 학습CAGR=best,
                         검증CAGR_선택=sel["CAGR"] if sel else float("nan"),
                         검증CAGR_고정=fix["CAGR"] if fix else float("nan")))
        print(f"  WF {rows[-1]['검증']}: 선택 {pf(rows[-1]['검증CAGR_선택'])} "
              f"vs 고정 {pf(rows[-1]['검증CAGR_고정'])}")
        D["wf_rows"] = rows
        save(D)
        start += ann
    D["wf"] = pd.DataFrame(rows)
    save(D)
    print(f"[stage3] 완료. 워크포워드 {len(rows)}구간")


def stage4():
    D = load()
    store, uni, days, phase, coup, _ = setup()
    D["store"] = store
    n_tests = len(D["tests"]) + D["n_combos"] * 2 + 4 + len(D["phase_rows"])
    D["n_tests"] = n_tests
    D["alpha"] = 0.05 / max(n_tests, 1)
    print(f"[다중검정] 총 {n_tests}회 -> Bonferroni alpha = {D['alpha']:.6f}")
    for nm, t_, p_, n_ in D["tests"]:
        sig = "유의" if (not isnan(p_) and p_ < D["alpha"]) else "유의하지 않음"
        print(f"  {nm:<28} n={n_:<5} p={pf(p_,'{:.4f}',False)} -> 보정후 {sig}")

    D["td"].to_csv(os.path.join(DIR_BT, "backtest_trades.csv"),
                   index=False, encoding="utf-8-sig")
    D["ed"].to_csv(os.path.join(DIR_BT, "backtest_equity.csv"),
                   index=False, encoding="utf-8-sig")
    D["sens"].to_csv(os.path.join(DIR_BT, "backtest_sensitivity.csv"),
                     index=False, encoding="utf-8-sig")
    pd.DataFrame(D["phase_rows"]).to_csv(os.path.join(DIR_BT, "backtest_phase.csv"),
                                         index=False, encoding="utf-8-sig")
    D["wf"].to_csv(os.path.join(DIR_BT, "backtest_walkforward.csv"),
                   index=False, encoding="utf-8-sig")
    import 가상매매_백테스트 as BT
    BT.chart(D["ed"], D["bmk"], D["days"])
    import jq_bt_report as R
    R.write_all(D)
    print("[stage4] 완료. 문서·차트 생성")


if __name__ == "__main__":
    s = sys.argv[1] if len(sys.argv) > 1 else "1"
    {"1": stage1, "2": stage2, "3": stage3, "4": stage4}[s]()
