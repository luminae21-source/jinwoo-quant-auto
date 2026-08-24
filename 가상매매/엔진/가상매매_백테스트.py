# -*- coding: utf-8 -*-
"""
가상매매_백테스트.py — 진우퀀트 Phase 1 백테스트

규칙은 jq_paper_core.py 에서 import (재구현 금지). 실행 엔진은 jq_backtest_core.py.

검증 트랙 (※ 매매 트랙 Track L/S 와 혼동 금지)
  · 검증① 통합(Pooled)   — 전 구간 하나로. **결론의 기본선.** 통계검정 포함.
  · 검증② 국면별(Conditional) — 4축 분해. **가설 생성용.** 결론 도출용 아님.
  교차판정: 통합✅+국면✅ = 채택후보 / 통합✅+국면❌ = 조건부(국면의존 경고)
            통합❌+국면✅ = **기각(데이터마이닝 의심)** / 통합❌+국면❌ = 기각
  최종 판정은 **OOS 기준.**

실행:
  py 가상매매_백테스트.py               (전체)
  py 가상매매_백테스트.py --quick       (민감도 격자 축소)
  py 가상매매_백테스트.py --self-test
"""
import os, sys, math, argparse, itertools, datetime as dt

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jq_paper_core as C
import jq_backtest_core as B
from jq_paper_core import CFG, PriceStore, RunLogger, DIR_BT, DIR_VERIFY, fmt_pct, isnan

MIN_N = 30   # 이보다 적으면 통계적 결론 불가


def pf(v, sp="{:+.2f}%", pct=True):
    if v is None or isnan(v):
        return "—"
    return sp.format(v * 100 if pct else v)


# ═══════════════════════════════════════════════════════════════════════════
def build(store):
    uni = {}
    for c in store.universe("KOSPI", CFG["UNIVERSE_TOP_N"]):
        uni[c] = "KOSPI"
    for c in store.universe("KOSDAQ", CFG["KOSDAQ_TOP_N"]):
        uni[c] = "KOSDAQ"
    days = store.trading_days("KOSPI")
    return uni, days


def run(args):
    print("=" * 78)
    print("진우퀀트 — 가상매매 백테스트")
    print("=" * 78)
    print("  투자자문 아님. 지표·규칙 사실만 기록. 결정·책임은 본인.")

    B.load_ind_cache()      # 이전 실행의 지표 캐시 재사용 (없으면 새로 계산)
    store = PriceStore("local")
    if not store.load_local():
        print("[중단] 실데이터 없음")
        return 2
    for n in store.notes:
        print("  " + n)

    uni, days = build(store)
    days = [d for d in days if pd.Timestamp(d) >= pd.Timestamp("2020-02-01")]  # 지표 워밍업
    print(f"\n유니버스 {len(uni)}종목 | 거래일 {len(days)}일 "
          f"({pd.Timestamp(days[0]).date()} ~ {pd.Timestamp(days[-1]).date()})")

    # --- 국면 / 커플링 (인과적, 롤링) ---
    idx, inotes = C.load_kospi_index()
    print("\n[국면 데이터]")
    for n in inotes:
        print("  · " + n)
    phase = C.phase_series(idx)
    cpanel, _, _ = C.load_coupling_panel()
    coup = C.coupling_series(cpanel)

    # --- 생존편향 ---
    sv = B.survivorship_report(store)
    print("\n[생존편향 실측]")
    for m, d in sv.items():
        if d:
            print(f"  {m}: {d['종목수']}종목 · 중도소멸(상폐/거래정지 추정) {d['중도소멸']} "
                  f"· 중도상장 {d['중도상장']}")

    # --- IS / OOS 분할 ---
    split = int(len(days) * 0.7)
    IS, OOS = days[:split], days[split:]
    print(f"\n[IS/OOS] IS {pd.Timestamp(IS[0]).date()}~{pd.Timestamp(IS[-1]).date()} ({len(IS)}일)"
          f" | OOS {pd.Timestamp(OOS[0]).date()}~{pd.Timestamp(OOS[-1]).date()} ({len(OOS)}일)")

    kw = dict(phase=phase, coup=coup)

    # ═══ 기본 설정 (전 구간) ═══
    print("\n" + "=" * 78)
    print("[1] 검증① 통합 — 기본 파라미터, 전 구간")
    print("=" * 78)
    td, ed, meta = B.backtest(store, uni, days, half_tp=False, apply_cost=True, **kw)
    td_nc, ed_nc, _ = B.backtest(store, uni, days, half_tp=False, apply_cost=False, **kw)
    print(f"  데이터부족 종목: {meta['데이터부족종목']} / 유니버스 {meta['유니버스']} "
          f"-> 사용 {meta['사용종목']}종목")
    if meta["데이터부족리스트"]:
        print(f"     제외: {', '.join(meta['데이터부족리스트'][:15])}")

    B_ = {}
    print(f"\n  {'구분':<12}{'CAGR':>9}{'누적':>10}{'MDD':>9}{'Sharpe':>8}"
          f"{'거래':>6}{'승률':>8}{'손익비':>8}{'평균R':>8}{'보유일':>7}{'연속손':>6}")
    for tr in ("L", "S", "TOTAL"):
        p = B.perf(ed, td, tr)
        B_[tr] = p
        if not p:
            continue
        lab = f"Track {tr}" if tr != "TOTAL" else "합계(비용후)"
        print(f"  {lab:<12}{pf(p['CAGR']):>9}{pf(p['누적수익률']):>10}{pf(p['MDD']):>9}"
              f"{pf(p['Sharpe'],'{:.2f}',False):>8}{p['거래수']:>6}"
              f"{pf(p['승률']):>8}{pf(p['손익비'],'{:.2f}',False):>8}"
              f"{pf(p['평균R'],'{:+.3f}',False):>8}"
              f"{pf(p['평균보유일'],'{:.0f}',False):>7}{p['최대연속손실']:>6}")
    pnc = B.perf(ed_nc, td_nc, "TOTAL")
    if pnc:
        print(f"  {'합계(비용전)':<12}{pf(pnc['CAGR']):>9}{pf(pnc['누적수익률']):>10}"
              f"{pf(pnc['MDD']):>9}{pf(pnc['Sharpe'],'{:.2f}',False):>8}"
              f"{pnc['거래수']:>6}{pf(pnc['승률']):>8}")
        tot = B_["TOTAL"]
        if tot:
            print(f"  -> 비용 영향: CAGR {pf(pnc['CAGR'])} -> {pf(tot['CAGR'])} "
                  f"(총비용 {format(tot['총비용'],',.0f')}원)")

    # --- 통계 검정 ---
    print("\n[통계 검정 — 거래당 순손익이 0과 다른가]")
    tests = []
    for tr in ("L", "S", "TOTAL"):
        t = td if tr == "TOTAL" else td[td["track"] == tr]
        x = pd.to_numeric(t["net_pnl"], errors="coerce").dropna()
        tt, pp, n, ci = B.ttest_1samp(x, 0.0)
        tests.append((f"거래당순손익≠0 ({tr})", tt, pp, n))
        print(f"  {tr:<6} n={n:<4} 평균 {format(x.mean(),',.0f') if n else '—'}원  "
              f"t={pf(tt,'{:.3f}',False)}  p={pf(pp,'{:.4f}',False)}  "
              f"95%CI [{format(ci[0],',.0f') if n>2 else '—'}, "
              f"{format(ci[1],',.0f') if n>2 else '—'}]")

    # --- 벤치마크 ---
    print("\n[2] 벤치마크 대비 (동일구간·동일가중 buy&hold)")
    bmk = {}
    for mkt in ("KOSPI", "KOSDAQ"):
        b = B.benchmark(store, mkt, days)
        bmk[mkt] = b
        if b:
            print(f"  {mkt} B&H ({b['종목수']}종목): CAGR {pf(b['CAGR'])} · "
                  f"누적 {pf(b['누적수익률'])} · MDD {pf(b['MDD'])} · "
                  f"Sharpe {pf(b['Sharpe'],'{:.2f}',False)}")
    tot = B_["TOTAL"]
    if tot and bmk.get("KOSPI"):
        d = tot["CAGR"] - bmk["KOSPI"]["CAGR"]
        print(f"\n  >>> 전략 CAGR {pf(tot['CAGR'])} vs 코스피 B&H {pf(bmk['KOSPI']['CAGR'])}"
              f"  =>  {pf(d)}p  [{'전략 우위' if d > 0 else '★벤치마크를 못 이김★'}]")

    # ═══ IS / OOS ═══
    print("\n" + "=" * 78)
    print("[3] IS / OOS — 최종 판정은 OOS 기준")
    print("=" * 78)
    seg = {}
    for nm, dd in (("IS", IS), ("OOS", OOS)):
        t_, e_, _ = B.backtest(store, uni, dd, half_tp=False, apply_cost=True, **kw)
        seg[nm] = (t_, e_)
        b = B.benchmark(store, "KOSPI", dd)
        print(f"\n  --- {nm} ---")
        print(f"  {'구분':<12}{'CAGR':>9}{'MDD':>9}{'Sharpe':>8}{'거래':>6}{'승률':>8}{'평균R':>9}")
        for tr in ("L", "S", "TOTAL"):
            p = B.perf(e_, t_, tr)
            if not p:
                continue
            print(f"  {('Track '+tr if tr!='TOTAL' else '합계'):<12}"
                  f"{pf(p['CAGR']):>9}{pf(p['MDD']):>9}"
                  f"{pf(p['Sharpe'],'{:.2f}',False):>8}{p['거래수']:>6}"
                  f"{pf(p['승률']):>8}{pf(p['평균R'],'{:+.3f}',False):>9}")
        if b:
            print(f"  {'코스피 B&H':<12}{pf(b['CAGR']):>9}{pf(b['MDD']):>9}"
                  f"{pf(b['Sharpe'],'{:.2f}',False):>8}")
        x = pd.to_numeric(t_["net_pnl"], errors="coerce").dropna()
        tt, pp, n, _ = B.ttest_1samp(x, 0.0)
        tests.append((f"거래당순손익≠0 ({nm})", tt, pp, n))
        print(f"  검정: n={n}, t={pf(tt,'{:.3f}',False)}, p={pf(pp,'{:.4f}',False)}")

    # ═══ 검증② 국면별 ═══
    print("\n" + "=" * 78)
    print("[4] 검증② 국면별 — ★가설 생성용. 결론 도출용 아님★")
    print("=" * 78)
    print("  국면을 쪼갤수록 표본이 줄어 노이즈가 커진다. 'A국면에서 잘 되더라'는")
    print("  대부분 우연일 수 있다. n<30 셀은 통계적 결론 불가.")
    phase_rows = []
    for axis, col in (("A 추세", "phase_trend"), ("B 변동성", "phase_vol"),
                      ("C 커플링", "coupling_state"), ("D 드로다운", "phase_dd")):
        print(f"\n  --- {axis} ---")
        print(f"  {'국면':<16}{'트랙':<7}{'n':>5}{'순손익':>12}{'승률':>8}"
              f"{'손익비':>8}{'평균R':>9}  판정")
        for st in sorted(td[col].dropna().unique()):
            for tr in ("L", "S"):
                t = td[(td[col] == st) & (td["track"] == tr)]
                n = len(t)
                if n == 0:
                    continue
                net = pd.to_numeric(t["net_pnl"], errors="coerce").dropna()
                r = pd.to_numeric(t["r_multiple"], errors="coerce").dropna()
                w, l = net[net > 0], net[net <= 0]
                wr = len(w) / len(net) if len(net) else float("nan")
                plr = (w.mean() / abs(l.mean())) if len(w) and len(l) and l.mean() != 0 else float("nan")
                verdict = "통계적 결론 불가(n<30)" if n < MIN_N else "참고"
                phase_rows.append(dict(축=axis, 국면=st, 트랙=tr, n=n,
                                       순손익=float(net.sum()), 승률=wr, 손익비=plr,
                                       평균R=float(r.mean()) if len(r) else float("nan"),
                                       판정=verdict))
                print(f"  {st:<16}{tr:<7}{n:>5}{format(net.sum(),',.0f'):>12}"
                      f"{pf(wr):>8}{pf(plr,'{:.2f}',False):>8}"
                      f"{pf(float(r.mean()) if len(r) else float('nan'),'{:+.3f}',False):>9}"
                      f"  {verdict}")

    # ═══ 파라미터 민감도 ═══
    print("\n" + "=" * 78)
    print("[5] 파라미터 민감도 — 특정 값에서만 좋으면 = 과최적화")
    print("=" * 78)
    grids = dict(MA_SHORT=[20, 25, 60], ATR_STOP=[1.5, 2.0, 2.5], TIME_STOP_DAYS=[10, 20])
    if args.quick:
        grids = dict(MA_SHORT=[20, 60], ATR_STOP=[1.5, 2.5], TIME_STOP_DAYS=[10, 20])
    sens = []
    combos = list(itertools.product(*grids.values()))
    print(f"  격자 {len(combos)}조합 x (IS/OOS) = {len(combos)*2}회 검정")
    for vals in combos:
        p = dict(zip(grids.keys(), vals))
        row = dict(p)
        for nm, dd in (("IS", IS), ("OOS", OOS)):
            t_, e_, _ = B.backtest(store, uni, dd, params=p, apply_cost=True, **kw)
            pp_ = B.perf(e_, t_, "TOTAL")
            row[f"{nm}_CAGR"] = pp_["CAGR"] if pp_ else float("nan")
            row[f"{nm}_n"] = pp_["거래수"] if pp_ else 0
        sens.append(row)
    sdf = pd.DataFrame(sens)
    print(f"\n  {'MA_SHORT':>9}{'ATR_STOP':>10}{'TIME_STOP':>11}{'IS CAGR':>10}"
          f"{'OOS CAGR':>10}{'OOS n':>7}")
    for _, r in sdf.iterrows():
        print(f"  {int(r['MA_SHORT']):>9}{r['ATR_STOP']:>10.1f}{int(r['TIME_STOP_DAYS']):>11}"
              f"{pf(r['IS_CAGR']):>10}{pf(r['OOS_CAGR']):>10}{int(r['OOS_n']):>7}")
    oos = sdf["OOS_CAGR"].dropna()
    if len(oos) > 1:
        pos = int((oos > 0).sum())
        print(f"\n  OOS CAGR 범위: {pf(oos.min())} ~ {pf(oos.max())} "
              f"(중앙값 {pf(oos.median())})")
        print(f"  양(+) 조합: {pos}/{len(oos)}")
        robust = pos >= len(oos) * 0.7 and oos.median() > 0
        print(f"  판정: {'넓은 고원(robust) 시사' if robust else '★고원 아님 — 특정 값 의존 = 과최적화 위험★'}")

    # ═══ 할로윈 ON/OFF ═══
    print("\n" + "=" * 78)
    print("[6] 할로윈 오버레이 ON/OFF")
    print("=" * 78)
    hal = {}
    for nm, dd in (("IS", IS), ("OOS", OOS)):
        for hv in (False, True):
            t_, e_, _ = B.backtest(store, uni, dd, halloween=hv, apply_cost=True, **kw)
            hal[(nm, hv)] = B.perf(e_, t_, "TOTAL")
    print(f"  {'구간':<6}{'할로윈':<8}{'CAGR':>9}{'MDD':>9}{'Sharpe':>8}{'거래':>6}")
    for nm in ("IS", "OOS"):
        for hv in (False, True):
            p = hal[(nm, hv)]
            if not p:
                continue
            print(f"  {nm:<6}{('ON' if hv else 'OFF'):<8}{pf(p['CAGR']):>9}"
                  f"{pf(p['MDD']):>9}{pf(p['Sharpe'],'{:.2f}',False):>8}{p['거래수']:>6}")
    ho, hf = hal[("OOS", True)], hal[("OOS", False)]
    hal_adopt = False
    if ho and hf:
        d = ho["CAGR"] - hf["CAGR"]
        hal_adopt = d > 0 and ho["Sharpe"] > hf["Sharpe"]
        print(f"\n  OOS 차이: CAGR {pf(d)}p, Sharpe "
              f"{pf(ho['Sharpe']-hf['Sharpe'],'{:+.3f}',False)}")
        print(f"  판정: {'채택 검토' if hal_adopt else '★기각 — OFF 유지★'}")

    # ═══ 워크포워드 ═══
    print("\n" + "=" * 78)
    print("[7] 워크포워드 (3년 학습 -> 1년 검증, 롤링)")
    print("=" * 78)
    wf = walk_forward(store, uni, days, grids, kw)

    # ═══ 다중검정 보정 ═══
    n_tests = len(tests) + len(combos) * 2 + 4 + len(phase_rows)
    alpha = 0.05 / max(n_tests, 1)
    print("\n" + "=" * 78)
    print("[8] 다중검정 보정 (Bonferroni)")
    print("=" * 78)
    print(f"  총 검정 횟수(추정): {n_tests}회")
    print(f"    · 통합/구간 t검정 {len(tests)} · 민감도 격자 {len(combos)*2} "
          f"· 할로윈 4 · 국면 셀 {len(phase_rows)}")
    print(f"  Bonferroni 보정 유의수준 alpha = 0.05 / {n_tests} = {alpha:.6f}")
    print(f"\n  {'검정':<28}{'n':>6}{'t':>9}{'보정전 p':>11}{'보정후 유의':>12}")
    for nm, tt, pp, n in tests:
        sig = "유의" if (not isnan(pp) and pp < alpha) else "유의하지 않음"
        print(f"  {nm:<28}{n:>6}{pf(tt,'{:.3f}',False):>9}"
              f"{pf(pp,'{:.4f}',False):>11}{sig:>12}")

    # --- 저장 ---
    td.to_csv(os.path.join(DIR_BT, "backtest_trades.csv"), index=False, encoding="utf-8-sig")
    ed.to_csv(os.path.join(DIR_BT, "backtest_equity.csv"), index=False, encoding="utf-8-sig")
    sdf.to_csv(os.path.join(DIR_BT, "backtest_sensitivity.csv"), index=False, encoding="utf-8-sig")
    pd.DataFrame(phase_rows).to_csv(os.path.join(DIR_BT, "backtest_phase.csv"),
                                    index=False, encoding="utf-8-sig")
    chart(ed, bmk, days)

    B.save_ind_cache()
    import jq_bt_report as R
    R.write_all(dict(store=store, td=td, ed=ed, meta=meta, perf=B_, nocost=pnc,
                     bmk=bmk, seg=seg, phase_rows=phase_rows, sens=sdf, hal=hal,
                     hal_adopt=hal_adopt, tests=tests, n_tests=n_tests, alpha=alpha,
                     sv=sv, days=days, IS=IS, OOS=OOS, wf=wf, inotes=inotes))
    print("\n[산출물] 백테스트\\ · 검증\\")
    for f in ("backtest_trades.csv", "backtest_equity.csv", "backtest_sensitivity.csv",
              "backtest_phase.csv", "자산곡선.png", "백테스트_결과.md"):
        print(f"  {'[O]' if os.path.exists(os.path.join(DIR_BT,f)) else '[X]'} {f}")
    for f in ("검증_결과.md", "채택기각_로그.csv"):
        print(f"  {'[O]' if os.path.exists(os.path.join(DIR_VERIFY,f)) else '[X]'} {f}")
    return 0


def walk_forward(store, uni, days, grids, kw):
    """3년 학습(최적 파라미터 선택) -> 다음 1년 검증. 고정 파라미터와 비교."""
    ann = 252
    rows = []
    start = 0
    combos = list(itertools.product(*grids.values()))
    while start + ann * 4 <= len(days):
        tr = days[start:start + ann * 3]
        te = days[start + ann * 3:start + ann * 4]
        best, best_c = None, None
        for vals in combos:
            p = dict(zip(grids.keys(), vals))
            t_, e_, _ = B.backtest(store, uni, tr, params=p, apply_cost=True, **kw)
            pp = B.perf(e_, t_, "TOTAL")
            if pp and (best is None or (not isnan(pp["CAGR"]) and pp["CAGR"] > best)):
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
        start += ann
    if not rows:
        print("  [데이터부족] 워크포워드에 필요한 4년 구간 확보 실패")
        return pd.DataFrame()
    w = pd.DataFrame(rows)
    print(f"  {'검증구간':<24}{'학습CAGR':>10}{'검증(선택)':>11}{'검증(고정)':>11}  선택파라미터")
    for _, r in w.iterrows():
        print(f"  {r['검증']:<24}{pf(r['학습CAGR']):>10}{pf(r['검증CAGR_선택']):>11}"
              f"{pf(r['검증CAGR_고정']):>11}  {r['선택파라미터']}")
    a = w["검증CAGR_선택"].mean()
    b = w["검증CAGR_고정"].mean()
    print(f"\n  평균 검증CAGR: 선택 {pf(a)} vs 고정 {pf(b)}")
    print(f"  판정: {'파라미터 선택이 도움' if a > b else '★파라미터 선택이 오히려 해로움 = 선택은 노이즈★'}")
    w.to_csv(os.path.join(DIR_BT, "backtest_walkforward.csv"), index=False,
             encoding="utf-8-sig")
    return w


def chart(ed, bmk, days):
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
    except Exception as e:
        print(f"  [데이터부족] matplotlib 없음 -> 차트 생략 ({e})")
        return
    try:
        import koreanize_matplotlib  # noqa
    except Exception:
        pass  # 한글 폰트 없으면 라벨만 영문. 이모지는 어차피 안 씀.

    fig, ax = plt.subplots(figsize=(12, 6))
    for tr, c in (("L", "#1f77b4"), ("S", "#ff7f0e"), ("TOTAL", "#2ca02c")):
        e = ed[ed["track"] == tr].sort_values("date")
        if len(e) < 2:
            continue
        v = e["total_equity"].values.astype(float)
        ax.plot(pd.to_datetime(e["date"]), v / v[0],
                label=f"Track {tr}" if tr != "TOTAL" else "TOTAL", color=c, lw=1.4)
    for mkt, c in (("KOSPI", "#888888"), ("KOSDAQ", "#cccccc")):
        b = bmk.get(mkt)
        if b is not None and "곡선" in b:
            ax.plot(b["곡선"].index, b["곡선"].values, label=f"{mkt} B&H",
                    color=c, lw=1.2, ls="--")
    ax.axhline(1.0, color="k", lw=0.6, alpha=0.4)
    ax.set_title("Paper Trading Backtest - Equity Curve (cost incl.)")
    ax.set_ylabel("Growth (x)")
    ax.legend(loc="upper left", fontsize=9)
    ax.grid(alpha=0.25)
    fig.tight_layout()
    fig.savefig(os.path.join(DIR_BT, "자산곡선.png"), dpi=120)
    plt.close(fig)


def self_test():
    ok = tot = 0

    def chk(n, c):
        nonlocal ok, tot
        tot += 1
        ok += 1 if c else 0
        print(f"  [{'OK  ' if c else 'FAIL'}] {n}")

    print("=" * 78)
    print("백테스트 셀프테스트")
    print("=" * 78)

    print("\n[거래비용]")
    bc = B.buy_cost(10_000, 10)
    chk(f"매수비용 = 10만 x (0.015% + 0.1%) = 115원 (실제 {bc:.0f})", abs(bc - 115) < 0.5)
    sc = B.sell_cost(10_000, 10)
    chk(f"매도비용 = 10만 x (0.015% + 0.15% + 0.1%) = 265원 (실제 {sc:.0f})",
        abs(sc - 265) < 0.5)
    chk("비용 미적용 시 0", B.buy_cost(10_000, 10, dict(BUY_FEE=0, SLIPPAGE=0)) == 0)

    print("\n[통계]")
    t, p, n, ci = B.ttest_1samp([1, 2, 3, 4, 5], 0)
    chk(f"t검정 동작 (t={t:.2f}, p={p:.4f}, n={n})", n == 5 and 0 <= p <= 1)
    _, p2, _, _ = B.ttest_1samp(np.random.default_rng(1).normal(0, 1, 400), 0)
    chk(f"평균0 표본 -> p 큼 (p={p2:.3f})", p2 > 0.05)
    _, p3, _, _ = B.ttest_1samp(np.random.default_rng(1).normal(1, 1, 400), 0)
    chk(f"평균1 표본 -> p 작음 (p={p3:.2e})", p3 < 0.001)
    tn, _, _, _ = B.ttest_1samp([1.0], 0)
    chk("표본부족 -> NaN (예외 없음)", isnan(tn))

    print("\n[look-ahead 차단 — 백테스트 신뢰의 핵심]")
    st = PriceStore("local")
    st.load_local()
    d = B.precompute(st, "KOSPI", "005930")
    chk(f"지표 사전계산 ({len(d)}행)", d is not None and len(d) > 100)
    if d is not None:
        i = 500
        # 스칼라(엔진) 계산 vs 벡터(백테스트) 계산 동치
        sub = d.iloc[max(0, i - CFG["BARS_WINDOW"]):i + 1]
        a_scalar = C.atr_wilder(sub["high"], sub["low"], sub["close"], CFG["ATR_N"])
        a_vec = float(d["atr"].iloc[i])
        chk(f"★ATR: 엔진(스칼라) {a_scalar:.3f} == 백테스트(벡터) {a_vec:.3f}",
            abs(a_scalar - a_vec) < 1e-6)
        ms, ss = C.ma_and_slope(sub["close"], CFG["S"]["MA_SHORT"], CFG["S"]["SLOPE_DAYS"])
        chk(f"★MA20: 엔진 {ms:.2f} == 백테스트 {float(d['ma_s'].iloc[i]):.2f}",
            abs(ms - float(d["ma_s"].iloc[i])) < 1e-6)
        # ★ 핵심: 시점 t의 지표가 t 이후 데이터에 의존하면 안 된다.
        #    미래를 잘라내고 다시 계산해도 t시점 값이 같아야 한다 (truncation invariance).
        cut = d.iloc[:i + 1]
        a2 = C.atr_wilder(cut["high"].tail(CFG["BARS_WINDOW"]),
                          cut["low"].tail(CFG["BARS_WINDOW"]),
                          cut["close"].tail(CFG["BARS_WINDOW"]), CFG["ATR_N"])
        chk(f"★미래 제거해도 t시점 ATR 불변 ({a2:.3f})", abs(a2 - a_vec) < 1e-6)

        mw_full = float(d["ma_w"].iloc[i])
        mw_cut, sw_cut = C.weekly_ma_slope_daily(
            cut["date"], cut["close"], CFG["L"]["MA_WEEK"], CFG["L"]["SLOPE_WEEKS"])
        chk(f"★미래 제거해도 t시점 주봉MA 불변 ({mw_full:.1f}) — 미완성 주봉 미사용",
            abs(mw_full - float(mw_cut.iloc[-1])) < 1e-6)

        # 주중(수요일)에 '그 주 금요일' 값을 당겨쓰지 않는가
        wed = d[pd.to_datetime(d["date"]).dt.dayofweek == 2]
        w2 = wed[wed["ma_w"].notna()]
        bad = 0
        # 주중(수요일)에 '그 주 금요일' 값을 당겨쓰지 않는가
        wed = d[pd.to_datetime(d["date"]).dt.dayofweek == 2]
        w2 = wed[wed["ma_w"].notna()].tail(30)
        bad = 0
        for j in range(len(w2)):
            t_ = pd.Timestamp(w2["date"].iloc[j])
            c2 = d[pd.to_datetime(d["date"]) <= t_]
            m2, _ = C.weekly_ma_slope_daily(c2["date"], c2["close"],
                                            CFG["L"]["MA_WEEK"],
                                            CFG["L"]["SLOPE_WEEKS"])
            if abs(float(w2["ma_w"].iloc[j]) - float(m2.iloc[-1])) > 1e-6:
                bad += 1
        chk(f"★수요일 주봉MA = 직전 확정주봉 기준 (불일치 {bad}/{len(w2)}건)", bad == 0)

    print("\n[생존편향 측정]")
    sv = B.survivorship_report(st)
    chk(f"KOSPI 측정 ({sv['KOSPI']})", sv.get("KOSPI") is not None)
    chk("중도소멸 종목이 실제로 존재 (일부 상폐 포함됨)", sv["KOSPI"]["중도소멸"] > 0)

    print(f"\n셀프테스트: {ok}/{tot} 통과")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--quick", action="store_true")
    a = ap.parse_args()
    log = RunLogger("가상매매_백테스트.py", vars(a))
    rc = 1
    try:
        rc = self_test() if a.self_test else run(a)
        log.close()
    except Exception as e:
        log.close(err=e)
        rc = 1
    sys.exit(rc)
