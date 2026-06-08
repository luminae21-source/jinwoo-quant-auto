#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
backtest_ma200_whipsaw.py — MA200 추세방어 '휩쏘 저감' 확장 1회 백테스트 (오버레이 방식)
무수정: production(v3.7.2)·C·D·영역3·v41 일절 손대지 않음. 이 파일은 신규 오버레이 평가만.

방법(정직): 공식 엔진(backtest_v37_2)이 산출한 v3.7.2 '월별 sleeve 수익'(r_v37_2_%, 48개월)을
고정으로 두고, MA200 디펜스만 월별 ON/OFF 토글한다. PIT 안전 — 리밸일 d0의 신호는
시장프록시 month-end ≤ d0 데이터로만 계산하고, 그 달 sleeve 수익은 공식 실현치. look-ahead 없음.

시장프록시 = liquidity_sector.csv 시총 top200 EW 지수(채택된 ma200_regime_check.py와 동일 방식),
kospi_monthly_prices.csv(2019-12~)로 만들어 10개월 SMA(=MA200 컨벤션) 계산.

사전등록 변형 2개(그리드·튜닝 금지) — 둘 다 '시장레벨 휩쏘 저감 필터'(데이터 충실성 위해 선정):
  base0  : 디펜스 없음(raw v3.7.2)              — 참조용
  base   : MA200 평탄(N=1, 버퍼0)               — ★합격선 비교 기준(이미 채택된 MA200 방어)
  ⓐ conf2: MA200 + 2개월 확인룰(이탈 2연속에만 발동, 복귀도 2연속에만)
  ⓑ band2: MA200 + 2% 밴드(level<SMA×0.98 발동 / level>SMA×1.02 복귀 / 중간=직전상태 유지)

디펜스 ON 달 = sleeve 수익을 현금(0%)으로 대체(보수적). 상태 전환(invested<->cash) 1회당
flip 비용 0.235% 차감(=휩쏘·거래비용 net). 확인룰·밴드가 flip 수를 줄이는 게 핵심.

합격선(동결, §결정메모) — ⓐ/ⓑ가 base(MA200) 대비 동시 충족해야 PASS:
  C1 MDD 개선 ≥ +2.0%p   C2 ΔCAGR ≥ −1.0%p   C3 Sharpe·IR 비열위(−0.01)   C4 OOS 3분할 MDD개선 부호 모두 ≥0
하나라도 미달 = 기각. 회의적 prior(base MDD 이미 −12%대라 +2.0%p 난망).

사용:
  python backtest_ma200_whipsaw.py --self-test
  python backtest_ma200_whipsaw.py
"""
import csv, json, sys
from pathlib import Path
from datetime import date

BASE = Path(__file__).parent.resolve()
SLEEVE_JSON = "backtest_v37_2_20260602_0158.json"   # 공식 r_v37_2_% 48개월
MONTHLY_PX  = "kospi_monthly_prices.csv"
LIQ         = "liquidity_sector.csv"
SMA_N = 10            # 10개월 SMA ~= 200일선(Faber GTAA)
FLIP_COST = 0.00235   # 상태 전환 1회당 비용(book 100% 이동 근사)
TOPN = 200


def _parse_date(s):
    s = str(s)[:10]
    for fmt in ("%Y-%m-%d",):
        pass
    y, m, d = s.split("-")
    return date(int(y), int(m), int(d))


def load_sleeve():
    d = json.load(open(BASE / SLEEVE_JSON, encoding="utf-8"))
    h = d["history"]
    out = []
    for r in h:
        out.append((_parse_date(r["date"]), float(r["r_v37_2_%"]) / 100.0,
                    float(r["r_kospi_%"]) / 100.0))
    out.sort(key=lambda x: x[0])
    return out  # [(date, r_sleeve, r_kospi)]


def load_proxy():
    """top200 EW 월말 지수 레벨 시계열 -> [(month_end_date, level)]"""
    liq = {}
    for r in csv.DictReader(open(BASE / LIQ, encoding="utf-8-sig")):
        try:
            liq[str(r["code"]).zfill(6)] = float(r["mcap"])
        except (ValueError, KeyError):
            pass
    top = [c for c, _ in sorted(liq.items(), key=lambda kv: -kv[1])[:TOPN]]
    rows = list(csv.reader(open(BASE / MONTHLY_PX, encoding="utf-8-sig")))
    hdr = [c.zfill(6) if c != "Date" else "Date" for c in rows[0]]
    idx = {c: j for j, c in enumerate(hdr)}
    cols = [c for c in top if c in idx]
    dates, mat = [], []
    for r in rows[1:]:
        dates.append(_parse_date(r[idx["Date"]]))
        vals = []
        for c in cols:
            try:
                vals.append(float(r[idx[c]]))
            except (ValueError, IndexError):
                vals.append(None)
        mat.append(vals)
    # 정규화 EW: 각 종목 첫 유효값 대비 비율의 평균
    base_px = [None] * len(cols)
    for j in range(len(cols)):
        for i in range(len(mat)):
            if mat[i][j] is not None and mat[i][j] > 0:
                base_px[j] = mat[i][j]; break
    levels = []
    for i in range(len(mat)):
        rs = [mat[i][j] / base_px[j] for j in range(len(cols))
              if base_px[j] and mat[i][j] is not None and mat[i][j] > 0]
        levels.append(sum(rs) / len(rs) if rs else None)
    return [(dates[i], levels[i]) for i in range(len(dates)) if levels[i] is not None]


def sma_signal(proxy, d0):
    """리밸일 d0 시점: month-end < d0 인 최근 10개 레벨의 SMA와 마지막 레벨 반환(PIT)."""
    past = [(dt, lv) for dt, lv in proxy if dt < d0]
    if len(past) < SMA_N:
        return None, None
    last = past[-1][1]
    sma = sum(lv for _, lv in past[-SMA_N:]) / SMA_N
    return last, sma


def defense_states(sleeve, proxy):
    """각 변형의 월별 '디펜스 ON?' bool 시퀀스 산출."""
    n = len(sleeve)
    raw_below = []   # level < SMA ?
    band = []        # -1 below.98 / +1 above1.02 / 0 neutral
    for dt, _, _ in sleeve:
        last, sma = sma_signal(proxy, dt)
        if last is None:
            raw_below.append(False); band.append(1)
        else:
            raw_below.append(last < sma)
            band.append(-1 if last < sma * 0.98 else (1 if last > sma * 1.02 else 0))
    # base0: never defensive
    s_base0 = [False] * n
    # base: N=1 plain
    s_base = list(raw_below)
    # ⓐ conf2: 이탈 2연속에만 ON, 복귀 2연속에만 OFF
    s_a = []
    st = False
    for i in range(n):
        if not st:
            if raw_below[i] and (i + 1 < n and raw_below[i]) and (i >= 1 and raw_below[i - 1]):
                st = True
            elif raw_below[i] and i >= 1 and raw_below[i - 1]:
                st = True
        else:
            if (not raw_below[i]) and i >= 1 and (not raw_below[i - 1]):
                st = False
        s_a.append(st)
    # ⓑ band2: 히스테리시스
    s_b = []
    st = False
    for i in range(n):
        if band[i] == -1:
            st = True
        elif band[i] == 1:
            st = False
        # neutral(0) -> 유지
        s_b.append(st)
    return {"base0": s_base0, "base": s_base, "ⓐ_conf2": s_a, "ⓑ_band2": s_b}


def apply_overlay(sleeve, states):
    """디펜스 ON 달 -> 현금 0%, 상태 전환 시 flip 비용. net 월수익 배열 반환."""
    rets = []
    prev = False
    flips = 0
    for i, (dt, rs, rk) in enumerate(sleeve):
        on = states[i]
        r = 0.0 if on else rs
        if on != prev:
            r -= FLIP_COST
            flips += 1
        rets.append(r)
        prev = on
    return rets, flips


def metrics(rets, bench, ppy=12):
    n = len(rets)
    cum = 1.0
    for r in rets:
        cum *= (1 + r)
    cagr = cum ** (ppy / n) - 1
    mean = sum(rets) / n
    var = sum((r - mean) ** 2 for r in rets) / (n - 1)
    vol = (var ** 0.5) * (ppy ** 0.5)
    # MDD
    c = 1.0; peak = 1.0; mdd = 0.0
    for r in rets:
        c *= (1 + r); peak = max(peak, c); mdd = min(mdd, c / peak - 1)
    sharpe = cagr / vol if vol > 0 else None
    # IR vs bench(월별 초과)
    ex = [rets[i] - bench[i] for i in range(n)]
    em = sum(ex) / n
    ev = (sum((e - em) ** 2 for e in ex) / (n - 1)) ** 0.5
    ir = (em * ppy) / (ev * (ppy ** 0.5)) if ev > 0 else None
    return {"CAGR%": round(cagr * 100, 2), "vol%": round(vol * 100, 2),
            "Sharpe": round(sharpe, 3) if sharpe else None,
            "MDD%": round(mdd * 100, 2), "IR": round(ir, 3) if ir else None}


def mdd_of(rets):
    c = 1.0; peak = 1.0; mdd = 0.0
    for r in rets:
        c *= (1 + r); peak = max(peak, c); mdd = min(mdd, c / peak - 1)
    return mdd * 100


def run():
    sleeve = load_sleeve()
    proxy = load_proxy()
    bench = [rk for _, _, rk in sleeve]
    states = defense_states(sleeve, proxy)
    res = {}
    for name, st in states.items():
        rets, flips = apply_overlay(sleeve, st)
        m = metrics(rets, bench)
        m["flips"] = flips
        m["defense_months"] = sum(st)
        res[name] = (m, rets)
    print("=== MA200 휩쏘저감 오버레이 백테스트 (오버레이=공식 sleeve 고정, 디펜스만 토글) ===")
    print("기간 %s~%s (%d개월) | 프록시=top200 EW 10M SMA | flip비용 %.3f%%\n"
          % (sleeve[0][0], sleeve[-1][0], len(sleeve), FLIP_COST * 100))
    print("변형        | CAGR%  | vol%  | Sharpe | MDD%   | IR    | flip | 디펜스월")
    for name in ("base0", "base", "ⓐ_conf2", "ⓑ_band2"):
        m = res[name][0]
        print("  %-9s | %+6.2f | %5.2f | %6.3f | %+6.2f | %5.3f | %4d | %d"
              % (name, m["CAGR%"], m["vol%"], m["Sharpe"], m["MDD%"], m["IR"], m["flips"], m["defense_months"]))

    bm = res["base"][0]
    print("\n--- 합격선 판정 (기준 = base[MA200 평탄]) ---")
    print("  base(MA200): CAGR %+.2f / Sharpe %.3f / MDD %+.2f / IR %.3f"
          % (bm["CAGR%"], bm["Sharpe"], bm["MDD%"], bm["IR"]))
    b0 = res["base0"][0]
    print("  (참조) base0 무방어: CAGR %+.2f / MDD %+.2f  → MA200이 base0 대비 MDD %+.2f%%p"
          % (b0["CAGR%"], b0["MDD%"], bm["MDD%"] - b0["MDD%"]))

    verdicts = {}
    for name in ("ⓐ_conf2", "ⓑ_band2"):
        vm, vr = res[name]
        # C1 MDD 개선 (덜 음수일수록 개선) : base MDD - var MDD >= 2.0
        c1_val = vm["MDD%"] - bm["MDD%"]          # +면 개선
        c1 = c1_val >= 2.0
        c2_val = vm["CAGR%"] - bm["CAGR%"]
        c2 = c2_val >= -1.0
        c3 = (vm["Sharpe"] >= bm["Sharpe"] - 0.01) and (vm["IR"] >= bm["IR"] - 0.01)
        # C4 OOS 3분할: 각 블록 MDD개선 부호 >=0
        n = len(vr); k = n // 3
        blocks = [(0, k), (k, 2 * k), (2 * k, n)]
        c4_signs = []
        for a, b in blocks:
            mdd_b = mdd_of(res["base"][1][a:b])
            mdd_v = mdd_of(vr[a:b])
            c4_signs.append(round(mdd_v - mdd_b, 2))   # +면 개선
        c4 = all(s >= 0 for s in c4_signs)
        passed = c1 and c2 and c3 and c4
        verdicts[name] = {"PASS": passed, "C1_MDD개선%p": round(c1_val, 2), "C1": c1,
                          "C2_ΔCAGR%p": round(c2_val, 2), "C2": c2,
                          "C3_Sharpe·IR비열위": c3, "C4_OOS3분할_MDD개선": c4_signs, "C4": c4}
        print("\n  [%s] %s" % (name, "✅ PASS" if passed else "❌ FAIL"))
        print("    C1 MDD개선 %+.2f%%p (≥+2.0?) %s" % (c1_val, "OK" if c1 else "미달"))
        print("    C2 ΔCAGR  %+.2f%%p (≥−1.0?) %s" % (c2_val, "OK" if c2 else "미달"))
        print("    C3 Sharpe·IR 비열위 %s (var S%.3f/IR%.3f vs base S%.3f/IR%.3f)"
              % ("OK" if c3 else "미달", vm["Sharpe"], vm["IR"], bm["Sharpe"], bm["IR"]))
        print("    C4 OOS 3분할 MDD개선 %s → %s" % (c4_signs, "OK" if c4 else "미달(부호 불일치)"))

    out = {"period": [str(sleeve[0][0]), str(sleeve[-1][0])], "n": len(sleeve),
           "metrics": {k: v[0] for k, v in res.items()}, "verdicts": verdicts,
           "passline": "vs base(MA200): C1 MDD≥+2.0%p AND C2 ΔCAGR≥−1.0%p AND C3 Sharpe·IR비열위 AND C4 OOS3분할 방향일치"}
    json.dump(out, open(BASE / "backtest_ma200_whipsaw_result.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    anypass = any(verdicts[v]["PASS"] for v in verdicts)
    print("\n★ 종합: %s. (결과 JSON: backtest_ma200_whipsaw_result.json)"
          % ("최소 1개 변형 PASS → C패턴 병행관찰 검토" if anypass else "전 변형 FAIL → 사전등록대로 기각(8번째 방어 기각), v3.7.2·MA200 무변경 유지"))
    return out


def self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print("  [%s] %s" % ("OK" if c else "FAIL", n))
    # 합성 sleeve: 상승 8개월 + 급락 4개월
    sl = [(date(2022, m, 1), 0.05, 0.04) for m in range(1, 9)] + \
         [(date(2022, m, 1), -0.10, -0.08) for m in range(9, 13)]
    # 프록시: 처음 상승 후 하락 (월말)
    px = [(date(2021, mm, 28), 1.0 + 0.02 * i) for i, mm in enumerate(range(1, 13))]
    px += [(date(2022, mm, 28), 1.24 - 0.05 * i) for i, mm in enumerate(range(1, 12))]
    states = defense_states(sl, px)
    chk("base0 디펜스 0개월", sum(states["base0"]) == 0)
    chk("base 디펜스>0(하락구간 포착)", sum(states["base"]) > 0)
    chk("conf2 flip ≤ base flip(휩쏘 저감)",
        apply_overlay(sl, states["ⓐ_conf2"])[1] <= apply_overlay(sl, states["base"])[1])
    chk("band2 flip ≤ base flip", apply_overlay(sl, states["ⓑ_band2"])[1] <= apply_overlay(sl, states["base"])[1])
    rets, _ = apply_overlay(sl, states["base"])
    chk("디펜스 ON 달 수익=현금(−flip 제외 0)", any(abs(r) < 1e-9 or abs(r + FLIP_COST) < 1e-9 for r in rets))
    m = metrics([0.05] * 12, [0.04] * 12)
    chk("metrics MDD≈0(단조상승)", m["MDD%"] == 0.0 or m["MDD%"] > -0.01)
    pit_px = [(date(2021, mm, 28), 1.0) for mm in range(1, 11)] + [(date(2021, 11, 28), 99.0)]
    pit_last, _ = sma_signal(pit_px, date(2021, 11, 15))  # d0=11/15 -> 11/28(미래) 제외돼야
    chk("PIT: SMA는 d0 미만만 사용(미래 99 제외)", pit_last == 1.0)
    print("self-test: %d/%d" % (ok, tot))
    return ok == tot


if __name__ == "__main__":
    if "--self-test" in sys.argv:
        self_test()
    else:
        try:
            run()
        except Exception:
            import traceback
            print("\n===== [에러] 아래를 복사해 주세요 ====="); traceback.print_exc()
