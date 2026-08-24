# -*- coding: utf-8 -*-
"""
jq_bt_report.py — 백테스트_결과.md / 검증_결과.md / 채택기각_로그.csv 생성

정직성 원칙: 결과가 나쁘면 나쁘다고 그대로 쓴다. 좋게 보이게 만들지 않는다.
"""
import os, math, datetime as dt
import numpy as np
import pandas as pd

from jq_paper_core import CFG, DIR_BT, DIR_VERIFY, isnan

MIN_N = 30
LOG_COLS = ["date", "item", "hypothesis", "통합결과", "국면별결과",
            "다중검정보정후", "OOS결과", "판정", "사유"]


def p(v, sp="{:+.2f}%", pct=True):
    if v is None or isnan(v):
        return "—"
    return sp.format(v * 100 if pct else v)


def w(v):
    try:
        return format(float(v), ",.0f")
    except Exception:
        return "—"


def write_all(D):
    _backtest_md(D)
    _verify_md(D)


# ═══════════════════════════════════════════════════════════════════════════
def _backtest_md(D):
    td, ed, B_, bmk, sv = D["td"], D["ed"], D["perf"], D["bmk"], D["sv"]
    tot, nc = B_.get("TOTAL"), D["nocost"]
    days, IS, OOS = D["days"], D["IS"], D["OOS"]
    L = []
    A = L.append

    A("# 백테스트 결과 — 진우퀀트 가상매매 Phase 1\n\n")
    A(f"> 생성 {dt.datetime.now().strftime('%Y-%m-%d %H:%M')} · "
      f"`가상매매_백테스트.py`\n")
    A("> 투자자문 아님. 지표·규칙 사실만 기록. 결정·책임은 본인.\n\n")

    # ── 최상단 경고 ──
    A("---\n\n## ⚠️ 먼저 읽을 것 — 이 백테스트는 실제보다 낙관적이다\n\n")
    k, q = sv.get("KOSPI"), sv.get("KOSDAQ")
    A("### 생존편향 (Survivorship bias) — 존재함. 은폐하지 않는다.\n\n")
    A("| 시장 | 패널 종목수 | 중도소멸(상폐·거래정지 추정) | 중도상장 |\n|---|---|---|---|\n")
    for m, d in sv.items():
        if d:
            A(f"| {m} | {d['종목수']} | {d['중도소멸']} | {d['중도상장']} |\n")
    A("\n- 패널에 **중도소멸 종목이 일부 포함**되어 있어 생존편향이 *완전히* 지배적이진 않다.\n")
    A("- 그러나 **유니버스를 '최근 시총 스냅샷'(`liquidity_sector.csv`)으로 정했다.**\n")
    A("  → 과거 시점에는 알 수 없었던 정보다. **선택편향(look-ahead in universe)이 존재한다.**\n")
    A("  → 즉 '지금 시총 상위인 종목'을 과거에 샀다고 가정한 것 → **실제보다 낙관적.**\n")
    A("- **결론: 아래 수치는 상방으로 편향되어 있다. 그대로 믿지 말 것.**\n\n")

    A("### 백테스트 ≠ 실전 (유일한 차이)\n\n")
    A("- 실전 엔진은 `breadth_features.csv`(2026-04~)와 VKOSPI로 매크로 게이트를 건다.\n")
    A("  그 데이터는 백테스트 구간(2020~) 대부분에 **존재하지 않는다.**\n")
    A("  없는 데이터를 만들어 쓸 수 없으므로 **백테스트는 매크로 게이트 미적용(노출 1.0)** 이다.\n")
    A("- 그 외 진입·청산·사이징 규칙은 `jq_paper_core.py` **동일 함수**를 호출한다 (재구현 없음).\n\n")

    # ── 편향 처리 ──
    A("---\n\n## 1. 편향 처리 내역\n\n")
    A("| 편향 | 처리 | 상태 |\n|---|---|---|\n")
    A("| **Look-ahead** | 신호는 t 종가까지만. 체결은 **t+1 시가**. 주봉MA는 확정 주봉만. "
      "지표는 전부 rolling/shift. 셀프테스트로 '미래 데이터 제거해도 t시점 지표 불변' 검증. | ✅ 차단 |\n")
    A("| **생존편향** | 제거 불가. **측정·명시** (위 표). | ⚠️ 존재·명시 |\n")
    A("| **유니버스 선택편향** | 최근 시총 스냅샷 사용. **제거 못 함.** | ⚠️ 존재·명시 |\n")
    A(f"| **거래비용** | 매수 {CFG['COST']['BUY_FEE']*100:.3f}% / 매도 {CFG['COST']['SELL_FEE']*100:.3f}% "
      f"+ 거래세 {CFG['COST']['TAX']*100:.2f}% / 슬리피지 {CFG['COST']['SLIPPAGE']*100:.1f}% (편도). "
      f"비용 유·무 둘 다 산출. | ✅ 반영 |\n")
    A("| **IS/OOS** | 앞 70% IS / 뒤 30% OOS. **최종 판정은 OOS.** | ✅ 분리 |\n")
    A("| **다중검정** | Bonferroni 보정. 총 검정수 명시. | ✅ 보정 |\n")
    A(f"| **데이터부족** | {D['meta']['데이터부족종목']}종목 제외 "
      f"(유니버스 {D['meta']['유니버스']} → 사용 {D['meta']['사용종목']}). 보간 없음. | ✅ 제외 |\n\n")

    A(f"**구간**: {pd.Timestamp(days[0]).date()} ~ {pd.Timestamp(days[-1]).date()} "
      f"({len(days)}거래일)\n\n")
    A(f"- IS : {pd.Timestamp(IS[0]).date()} ~ {pd.Timestamp(IS[-1]).date()} ({len(IS)}일)\n")
    A(f"- OOS: {pd.Timestamp(OOS[0]).date()} ~ {pd.Timestamp(OOS[-1]).date()} ({len(OOS)}일)\n\n")

    # ── 검증① 통합 ──
    A("---\n\n## 2. 검증① 통합(Pooled) — 결론의 기본선\n\n")
    A("| 구분 | CAGR | 누적 | MDD | Sharpe | 거래 | 승률 | 손익비 | 평균R | 평균보유일 | 최대연속손실 |\n")
    A("|---|---|---|---|---|---|---|---|---|---|---|\n")
    for tr in ("L", "S", "TOTAL"):
        x = B_.get(tr)
        if not x:
            continue
        lab = f"Track {tr}" if tr != "TOTAL" else "**합계(비용후)**"
        A(f"| {lab} | {p(x['CAGR'])} | {p(x['누적수익률'])} | {p(x['MDD'])} | "
          f"{p(x['Sharpe'],'{:.2f}',False)} | {x['거래수']} | {p(x['승률'])} | "
          f"{p(x['손익비'],'{:.2f}',False)} | {p(x['평균R'],'{:+.3f}',False)} | "
          f"{p(x['평균보유일'],'{:.0f}',False)} | {x['최대연속손실']} |\n")
    if nc:
        A(f"| 합계(비용전) | {p(nc['CAGR'])} | {p(nc['누적수익률'])} | {p(nc['MDD'])} | "
          f"{p(nc['Sharpe'],'{:.2f}',False)} | {nc['거래수']} | {p(nc['승률'])} | | | | |\n")
    if tot and nc:
        A(f"\n**비용 민감도**: CAGR {p(nc['CAGR'])} (비용전) → {p(tot['CAGR'])} (비용후). "
          f"총비용 {w(tot['총비용'])}원.\n\n")

    A("### 통계 검정 (거래당 순손익이 0과 다른가)\n\n")
    A("| 검정 | n | t | p (보정 전) | 95% CI |\n|---|---|---|---|---|\n")
    for nm, t_, p_, n_ in D["tests"]:
        A(f"| {nm} | {n_} | {p(t_,'{:.3f}',False)} | {p(p_,'{:.4f}',False)} | — |\n")
    A("\n")

    # ── 벤치마크 ──
    A("---\n\n## 3. 벤치마크 대비\n\n")
    A("| 전략 | CAGR | 누적 | MDD | Sharpe |\n|---|---|---|---|---|\n")
    if tot:
        A(f"| **본 전략(합계)** | {p(tot['CAGR'])} | {p(tot['누적수익률'])} | "
          f"{p(tot['MDD'])} | {p(tot['Sharpe'],'{:.2f}',False)} |\n")
    for m in ("KOSPI", "KOSDAQ"):
        b = bmk.get(m)
        if b:
            A(f"| {m} 동일가중 B&H ({b['종목수']}종목) | {p(b['CAGR'])} | "
              f"{p(b['누적수익률'])} | {p(b['MDD'])} | {p(b['Sharpe'],'{:.2f}',False)} |\n")
    if tot and bmk.get("KOSPI"):
        d = tot["CAGR"] - bmk["KOSPI"]["CAGR"]
        A(f"\n**초과수익 vs 코스피 B&H: {p(d)}p**\n\n")
        if d <= 0:
            A("> ### ★ 이 전략은 벤치마크(코스피 buy&hold)를 이기지 못했다. ★\n")
            A("> 매매 규칙의 복잡성·비용·심리적 부담을 감수할 근거가 현재 데이터에는 없다.\n")
            A("> (매도규칙서 v2도 같은 결론을 이미 기록하고 있다: "
              "'무제한 트레일링조차 buy&hold를 못 이겼다')\n\n")
        else:
            A("> 벤치마크 대비 우위. 단, 위 §0의 생존·선택편향으로 **과대추정**되어 있다.\n\n")

    # ── IS/OOS ──
    A("---\n\n## 4. IS / OOS — 최종 판정은 OOS 기준\n\n")
    import jq_backtest_core as B
    A("| 구간 | 트랙 | CAGR | MDD | Sharpe | 거래 | 승률 | 평균R |\n|---|---|---|---|---|---|---|---|\n")
    for nm in ("IS", "OOS"):
        t_, e_ = D["seg"][nm]
        for tr in ("L", "S", "TOTAL"):
            x = B.perf(e_, t_, tr)
            if not x:
                continue
            A(f"| {nm} | {tr} | {p(x['CAGR'])} | {p(x['MDD'])} | "
              f"{p(x['Sharpe'],'{:.2f}',False)} | {x['거래수']} | {p(x['승률'])} | "
              f"{p(x['평균R'],'{:+.3f}',False)} |\n")
    A("\n")

    # ── 검증② 국면별 ──
    A("---\n\n## 5. 검증② 국면별(Conditional) — ★가설 생성용★\n\n")
    A("> **국면을 쪼갤수록 각 구간 표본이 줄어 노이즈가 커진다. "
      "\"어떤 국면에서 잘 되더라\"는 결론은 대부분 우연일 수 있다. "
      "국면 분해는 가설 생성용이지, 그것만으로 규칙을 바꾸는 근거가 될 수 없다.**\n\n")
    pr = pd.DataFrame(D["phase_rows"])
    if len(pr):
        for ax in pr["축"].unique():
            A(f"### {ax}\n\n")
            A("| 국면 | 트랙 | n | 순손익 | 승률 | 손익비 | 평균R | 판정 |\n")
            A("|---|---|---|---|---|---|---|---|\n")
            for _, r in pr[pr["축"] == ax].iterrows():
                A(f"| {r['국면']} | {r['트랙']} | {r['n']} | {w(r['순손익'])} | "
                  f"{p(r['승률'])} | {p(r['손익비'],'{:.2f}',False)} | "
                  f"{p(r['평균R'],'{:+.3f}',False)} | {r['판정']} |\n")
            A("\n")
        few = int((pr["n"] < MIN_N).sum())
        A(f"**n<30 (통계적 결론 불가) 셀: {few}/{len(pr)}** — "
          f"국면 분해의 대부분은 표본이 얇다.\n\n")

    # ── 민감도 ──
    A("---\n\n## 6. 파라미터 민감도\n\n")
    s = D["sens"]
    A("| MA_SHORT | ATR_STOP | TIME_STOP | IS CAGR | OOS CAGR | OOS 거래수 |\n")
    A("|---|---|---|---|---|---|\n")
    for _, r in s.iterrows():
        A(f"| {int(r['MA_SHORT'])} | {r['ATR_STOP']:.1f} | {int(r['TIME_STOP_DAYS'])} | "
          f"{p(r['IS_CAGR'])} | {p(r['OOS_CAGR'])} | {int(r['OOS_n'])} |\n")
    oos = s["OOS_CAGR"].dropna()
    if len(oos) > 1:
        pos = int((oos > 0).sum())
        robust = pos >= len(oos) * 0.7 and oos.median() > 0
        A(f"\nOOS CAGR 범위 {p(oos.min())} ~ {p(oos.max())} (중앙값 {p(oos.median())}) · "
          f"양(+) 조합 {pos}/{len(oos)}\n\n")
        A(f"**판정: {'넓은 고원(robust) 시사' if robust else '★고원 아님 — 특정 파라미터 의존 = 과최적화 위험★'}**\n\n")

    # ── 워크포워드 ──
    A("---\n\n## 7. 워크포워드 (3년 학습 → 1년 검증)\n\n")
    wf = D["wf"]
    if wf is not None and len(wf):
        A("| 검증구간 | 학습 CAGR | 검증 CAGR (파라미터 선택) | 검증 CAGR (고정) | 선택된 파라미터 |\n")
        A("|---|---|---|---|---|\n")
        for _, r in wf.iterrows():
            A(f"| {r['검증']} | {p(r['학습CAGR'])} | {p(r['검증CAGR_선택'])} | "
              f"{p(r['검증CAGR_고정'])} | `{r['선택파라미터']}` |\n")
        a_, b_ = wf["검증CAGR_선택"].mean(), wf["검증CAGR_고정"].mean()
        A(f"\n평균 검증 CAGR: 선택 {p(a_)} vs 고정 {p(b_)}\n\n")
        A(f"**판정: {'파라미터 선택이 도움됨' if a_ > b_ else '★파라미터 선택이 오히려 해로움 → 선택은 노이즈 (과최적화 증거)★'}**\n\n")
    else:
        A("[데이터부족] 4년 구간 확보 실패 → 워크포워드 수행 못 함.\n\n")

    # ── 할로윈 ──
    A("---\n\n## 8. 할로윈 오버레이 ON/OFF\n\n")
    A("| 구간 | 할로윈 | CAGR | MDD | Sharpe | 거래 |\n|---|---|---|---|---|---|\n")
    for nm in ("IS", "OOS"):
        for hv in (False, True):
            x = D["hal"].get((nm, hv))
            if not x:
                continue
            A(f"| {nm} | {'ON' if hv else 'OFF'} | {p(x['CAGR'])} | {p(x['MDD'])} | "
              f"{p(x['Sharpe'],'{:.2f}',False)} | {x['거래수']} |\n")
    A(f"\n**판정: {'채택 검토' if D['hal_adopt'] else '★기각 — 기본 OFF 유지★'}**\n\n")

    # ── 다중검정 ──
    A("---\n\n## 9. 다중검정 보정 (Bonferroni)\n\n")
    A(f"- 총 검정 횟수: **{D['n_tests']}회**\n")
    A(f"- 보정 유의수준: alpha = 0.05 / {D['n_tests']} = **{D['alpha']:.6f}**\n\n")
    A("| 검정 | n | t | p (보정 전) | 보정 후 |\n|---|---|---|---|---|\n")
    for nm, t_, p_, n_ in D["tests"]:
        sig = "유의" if (not isnan(p_) and p_ < D["alpha"]) else "**유의하지 않음**"
        A(f"| {nm} | {n_} | {p(t_,'{:.3f}',False)} | {p(p_,'{:.4f}',False)} | {sig} |\n")
    A("\n> 수십~수백 번 검정하면 5% 수준에서 우연히 유의한 결과가 반드시 나온다. "
      "보정 후 살아남지 못하면 **유의하지 않은 것**이다.\n\n")

    # ── 믿으면 안 되는 이유 ──
    A("---\n\n## 10. ★이 백테스트를 믿으면 안 되는 이유★ (필수)\n\n")
    A("1. **유니버스 선택편향.** 유니버스를 '최근(2026) 시총 스냅샷'으로 정했다. "
      "2020년에는 그 종목들이 상위인지 알 수 없었다. **구조적으로 낙관 편향.**\n")
    A("2. **생존편향이 완전히 제거되지 않았다.** 중도소멸 종목이 일부 포함됐지만, "
      "패널 자체가 최근 조회 기준으로 구성됐다.\n")
    A(f"3. **표본이 짧다.** 거래일 {len(days)}일(약 {len(days)/252:.1f}년). "
      f"OOS는 {len(OOS)/252:.1f}년뿐이다. 시장 국면 한두 개밖에 못 겪었다.\n")
    A("4. **표본 구간이 극단적 강세장이다.** 이 기간 코스피는 대세 상승했다. "
      "추세추종은 강세장에서 잘 보이게 되어 있다. **하락장 검증이 사실상 없다.**\n")
    A("5. **파라미터 대부분이 학술 근거 없는 관행값이다** "
      "(ATR 2.5배, 시간손절 20일, 2%룰 등 — `파라미터_근거표.md` 참조). "
      "민감도 격자를 돌렸지만, 격자 자체가 사후에 고른 범위다.\n")
    A("6. **슬리피지 0.1%는 가정이다.** 실제 체결은 더 나쁠 수 있다. "
      "특히 코스닥·저유동성 종목에서.\n")
    A("7. **시가 체결을 가정했지만 시가에 그 물량이 체결된다는 보장이 없다.** "
      "갭·유동성 제약 미반영.\n")
    A("8. **매크로 게이트가 백테스트에 미적용**이다 (데이터가 그 시절에 없음). "
      "실전은 이 게이트가 노출을 줄인다 → **실전 성과는 백테스트와 다를 것이다.**\n")
    A("9. **다중검정을 수십~수백 번 했다.** 보정 후 유의한 게 없다면, "
      "눈에 띄는 좋은 숫자는 우연일 가능성이 높다.\n")
    A("10. **과거가 미래를 보장하지 않는다.** 특히 공개된 아노말리는 감쇠한다 "
      "(McLean & Pontiff 2016: 발표 후 수익 −58%).\n\n")
    A("> **이 백테스트의 올바른 용도: '이 규칙이 명백히 망가졌는지' 확인하는 것.**\n")
    A("> **'이 규칙이 돈을 번다'는 증거로 쓰면 안 된다.**\n\n")
    A("---\n\n투자자문 아님 · 집행·책임은 진우.\n")

    with open(os.path.join(DIR_BT, "백테스트_결과.md"), "w", encoding="utf-8") as f:
        f.write("".join(L))


# ═══════════════════════════════════════════════════════════════════════════
def _verify_md(D):
    """검증_결과.md + 채택기각_로그.csv — 교차판정표"""
    import jq_backtest_core as B
    td = D["td"]
    tot = D["perf"].get("TOTAL")
    bmk = D["bmk"]
    pr = pd.DataFrame(D["phase_rows"])
    today = dt.date.today().isoformat()

    t_oos, e_oos = D["seg"]["OOS"]
    oos_tot = B.perf(e_oos, t_oos, "TOTAL")
    oos_L = B.perf(e_oos, t_oos, "L")
    oos_S = B.perf(e_oos, t_oos, "S")

    # 통합 유효성: 순손익 평균 > 0 이고 벤치마크 초과
    net = pd.to_numeric(td["net_pnl"], errors="coerce").dropna()
    t_, p_, n_, _ = B.ttest_1samp(net, 0.0)
    pooled_ok = (not isnan(p_)) and p_ < D["alpha"] and net.mean() > 0
    beat = (tot and bmk.get("KOSPI") and tot["CAGR"] > bmk["KOSPI"]["CAGR"])

    # 국면 안정성: 각 축에서 순손익 양수 셀 비율
    stable = False
    if len(pr):
        big = pr[pr["n"] >= MIN_N]
        stable = len(big) > 0 and (big["순손익"] > 0).mean() >= 0.7

    rows = []

    def add(item, hyp, pooled, phase_r, corrected, oos, verdict, why):
        rows.append(dict(date=today, item=item, hypothesis=hyp, 통합결과=pooled,
                         국면별결과=phase_r, 다중검정보정후=corrected,
                         OOS결과=oos, 판정=verdict, 사유=why))

    # 1) 전략 전체
    add("전략 전체 (Track L+S)",
        "규칙 기반 추세추종이 코스피 buy&hold를 초과한다",
        f"CAGR {p(tot['CAGR']) if tot else '—'} vs B&H "
        f"{p(bmk['KOSPI']['CAGR']) if bmk.get('KOSPI') else '—'}",
        f"안정성 {'있음' if stable else '없음'}",
        "유의" if pooled_ok else "유의하지 않음",
        f"OOS CAGR {p(oos_tot['CAGR']) if oos_tot else '—'}",
        "채택 후보" if (beat and pooled_ok) else "기각",
        "벤치마크 미초과 또는 통계적 유의성 없음" if not (beat and pooled_ok)
        else "통합·OOS 모두 통과")

    # 2) Track L / S 개별
    for tr, o in (("L", oos_L), ("S", oos_S)):
        t2 = td[td["track"] == tr]
        nt = pd.to_numeric(t2["net_pnl"], errors="coerce").dropna()
        tt2, pp2, nn2, _ = B.ttest_1samp(nt, 0.0)
        ok2 = (not isnan(pp2)) and pp2 < D["alpha"] and nt.mean() > 0
        add(f"Track {tr} ({'중기 20주선' if tr=='L' else '단기 20일선'})",
            f"Track {tr} 규칙의 거래당 기대값 > 0",
            f"n={nn2}, 평균 {w(nt.mean()) if nn2 else '—'}원, p={p(pp2,'{:.4f}',False)}",
            "표본부족" if nn2 < MIN_N else ("안정" if stable else "불안정"),
            "유의" if ok2 else "유의하지 않음",
            f"OOS CAGR {p(o['CAGR']) if o else '—'}",
            "채택 후보" if ok2 else "기각",
            "다중검정 보정 후 유의성 없음" if not ok2 else "보정 후에도 유의")

    # 3) 할로윈
    add("할로윈 계절 오버레이",
        "여름(5~10월) 노출 50%가 위험조정 성과를 개선한다",
        "KOSPI 지수 검정 4/4 게이트 통과 (단, 11.8년 데이터 공백)",
        "—",
        "미검정(오버레이는 t검정 대상 아님)",
        f"OOS CAGR ON {p(D['hal'][('OOS',True)]['CAGR']) if D['hal'].get(('OOS',True)) else '—'} "
        f"vs OFF {p(D['hal'][('OOS',False)]['CAGR']) if D['hal'].get(('OOS',False)) else '—'}",
        "채택 검토" if D["hal_adopt"] else "기각 — OFF 유지",
        "OOS에서 개선 없음" if not D["hal_adopt"] else "OOS에서 CAGR·Sharpe 동시 개선")

    # 4) +1R 절반익절
    add("+1R 절반익절",
        "+1R에서 절반 매도가 성과를 개선한다",
        "매도규칙서 v2 실측 17,948건: 기대값 -0.01R (엣지 소멸)",
        "sweep에서 단조적으로 나쁨 (용량-반응)",
        "—",
        "미적용(기본 OFF)",
        "기각",
        "본인 실측 데이터가 명확히 기각. --half-tp 로 켤 수는 있음")

    # 5) 커플링
    add("한·미 커플링 (coupling_state)",
        "커플링 국면에 따라 성과가 다르다 → 매크로 게이트 반영 후보",
        "미반영 (기록 전용)",
        _coup_summary(pr),
        "국면 셀 대부분 n<30",
        "—",
        "보류 — 검증 대기",
        "표본 부족. 기록만 계속 축적. 규칙 미반영.")

    # 6) 파라미터 민감도
    s = D["sens"]
    oos = s["OOS_CAGR"].dropna()
    pos = int((oos > 0).sum()) if len(oos) else 0
    robust = len(oos) > 1 and pos >= len(oos) * 0.7 and oos.median() > 0
    add("파라미터 격자 (MA_SHORT/ATR_STOP/TIME_STOP)",
        "성과가 넓은 파라미터 고원에서 안정적이다",
        f"OOS 양(+) {pos}/{len(oos)}",
        "—", "—",
        f"OOS 중앙값 {p(oos.median()) if len(oos) else '—'}",
        "robust" if robust else "과최적화 위험",
        "특정 값 의존" if not robust else "넓은 고원")

    log = pd.DataFrame(rows, columns=LOG_COLS)
    fp = os.path.join(DIR_VERIFY, "채택기각_로그.csv")
    if os.path.exists(fp):
        old = pd.read_csv(fp, encoding="utf-8-sig")
        log = pd.concat([old, log], ignore_index=True)
    log.to_csv(fp, index=False, encoding="utf-8-sig")

    # --- 검증_결과.md ---
    L = []
    A = L.append
    A("# 검증 결과 — 투 트랙 검증 (검증①통합 / 검증②국면별)\n\n")
    A(f"> 생성 {dt.datetime.now().strftime('%Y-%m-%d %H:%M')} · 최종 판정은 **OOS 기준**\n")
    A("> ※ 여기서 '트랙'은 **검증 방법**이다. 매매 트랙(Track L/S)과 혼동하지 말 것.\n")
    A("> 투자자문 아님 · 결정·책임은 본인\n\n")

    A("---\n\n## 교차 판정 규칙\n\n")
    A("| | 국면별 ✅ 안정 | 국면별 ❌ 불안정 |\n|---|---|---|\n")
    A("| **통합 ✅ 유효** | **채택 후보** (강한 증거) | **조건부 채택** — \"국면 의존성 있음\" 경고 병기 |\n")
    A("| **통합 ❌ 무효** | **기각** — 데이터마이닝 의심 | **기각** |\n\n")
    A("> **핵심**: \"통합에서는 안 먹히는데 특정 국면에서만 먹힌다\" → 발견이 아니라 "
      "**과최적화 신호**로 취급한다.\n\n")

    A(f"**현재 위치**: 통합 {'✅ 유효' if pooled_ok else '❌ 무효'} × "
      f"국면별 {'✅ 안정' if stable else '❌ 불안정'} → "
      f"**{'채택 후보' if (pooled_ok and stable) else ('조건부 채택' if pooled_ok else '기각')}**\n\n")

    A("---\n\n## 항목별 최종 판정\n\n")
    A("| 항목 | 통합 | 국면별 | 보정 후 | OOS | **판정** |\n|---|---|---|---|---|---|\n")
    for r in rows:
        A(f"| {r['item']} | {r['통합결과']} | {r['국면별결과']} | {r['다중검정보정후']} | "
          f"{r['OOS결과']} | **{r['판정']}** |\n")

    A("\n---\n\n## 검증 대기 목록 (규칙 미반영)\n\n")
    A("| 항목 | 왜 대기인가 | 다음 단계 |\n|---|---|---|\n")
    A("| 한·미 커플링 | 국면 셀 표본 부족(n<30) | `coupling_history.csv` 축적 후 재검정 |\n")
    A("| 코스닥 테마 연동 | theme_heat 구성종목이 대부분 코스피 → 코스닥 유니버스로 못 씀 | "
      "코스닥 전용 테마 산출물 필요 |\n")
    A("| VKOSPI 게이트 | 데이터가 2026-06에서 멈춤 | 데이터 갱신 후 |\n\n")

    A("---\n\n## 정직성 경고\n\n")
    A("- **기각이 많이 나오는 게 정상이고 건강한 것이다.** 대부분의 규칙은 진짜 엣지가 없다.\n")
    A("- 국면 분해는 **가설 생성용**이다. 그것만으로 규칙을 바꾸지 않는다.\n")
    A("- 최종 판정은 **OOS 기준**이다. IS 성과는 참고치일 뿐이다.\n")
    A("- 이 검증 자체가 **생존·선택편향이 있는 데이터** 위에서 돌았다 "
      "(`백테스트_결과.md` §10 참조).\n\n")
    A("모든 규칙 변경은 `채택기각_로그.csv`에 기록된다. 이것이 학습 루프의 핵심 자산이다.\n")

    with open(os.path.join(DIR_VERIFY, "검증_결과.md"), "w", encoding="utf-8") as f:
        f.write("".join(L))


def _coup_summary(pr):
    if not len(pr):
        return "—"
    c = pr[pr["축"] == "C 커플링"]
    if not len(c):
        return "—"
    return " / ".join(f"{r['국면']}:n={r['n']}" for _, r in c.iterrows())
