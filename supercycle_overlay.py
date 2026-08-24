#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
supercycle_overlay.py — 모듈 E: 섹터 수퍼사이클 감지 + 공격 대응 (Stage 0 백테스트)
==============================================================================
결정메모: 진우퀀트_모듈E_수퍼사이클_결정메모.md (§2 설계 · §3 합격선 — 등록 후 변경 금지)

감지(PIT): SEMI(반도체 제조업)·BATTERY(이차전지) 바스켓의 12M 섹터초과 + breadth + 3개월 지속.
대응(fixed18 테마 멤버, 수퍼사이클일 때만):
  E_bab     : bab_adj = max(0, bab)         (고베타 주도주 감점 제거)
  E_bab_mom : E_bab + 섹터모멘텀 가산 +1.0
base/E_bab/E_bab_mom 동시점 병행 → 사전 등록 게이트 자동 판정.

엔진: score_univ30.member_components_at (PIT-proxy 컴포넌트) + score_v37.grade
      + score_v37_2.apply_weight_caps (production caps 무수정). fixed18, 월간 리밸.
원칙: production·C·D 무수정, 신규 파일. PASS 시 공식 엔진(PC) 확인은 후속(결정메모 §4-3).
사용: python supercycle_overlay.py   /   --selftest
"""
# ── §8-3 비용 SSOT (2026-07-27) ─────────────────────────────────
try:
    import sys as _s3, os as _o3
    _d3 = _o3.path.dirname(_o3.path.abspath(__file__))
    for _ in range(5):
        if _o3.path.exists(_o3.path.join(_d3, "비용모델.py")):
            _s3.path.insert(0, _d3); break
        _d3 = _o3.path.dirname(_d3)
    from 비용모델 import roundtrip as _jq_rt
except Exception:
    _jq_rt = None


def _jq_cost(legacy):
    return _jq_rt("기준") if _jq_rt else legacy
# ────────────────────────────────────────────────────────────────

import argparse, os, sys, json, datetime
import numpy as np, pandas as pd

import pit_universe_backtest as PB
import score_univ30 as SU
from score_v37 import grade
from score_v37_2 import apply_weight_caps

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ---- 사전 등록 상수 (결정메모 §2·§3 — 변경 금지) ----
THEME_PROXY = {"SEMI": "반도체 제조업", "BATTERY": "일차전지 및 이차전지 제조업"}
THEME_MEMBERS = {                      # fixed18 → 테마 명시 매핑 (KRX 세분류가 테마 쪼갬)
    "SEMI": ["005930", "000660", "042700", "095340"],   # 삼성전자·SK하이닉스·한미반도체·ISC
    "BATTERY": ["006400"],                               # 삼성SDI
}
THRESH_EXCESS, THRESH_BREADTH, PERSIST = 0.30, 0.60, 3
SC_BONUS = 1.0
VARIANTS = ["base", "E_bab", "E_bab_mom"]
GATE_DCAGR, GATE_DMDD, GATE_DIR = 0.010, 0.020, 0.05   # +1.0%p / MDD악화≤+2.0%p / IR≥base−0.05
FLAT_COST = _jq_cost(0.00235)  # §8-3: 종전 0.235% → 실측 0.559% (+0.324%p)                                     # 왕복, Σ|Δw|/2에 적용 (공식 컨벤션)


# ---------- 감지기 (PIT) ----------
def theme_baskets(panel_cols, sector_map):
    """테마 → 패널 내 멤버 코드 (감지용 바스켓, 깨끗한 KRX 세분류)."""
    out = {}
    for th, secname in THEME_PROXY.items():
        out[th] = [c for c in panel_cols if str(sector_map.get(c, "")) == secname]
    return out


def _excess_breadth(ret, basket, mkt, i):
    """리밸 idx i에서 basket의 12M 섹터초과·breadth (데이터 ≤ i)."""
    if i < 12 or not basket:
        return np.nan, np.nan
    win = slice(i - 11, i + 1)                          # 최근 12개월 수익률 (≤ i)
    bm = ret[basket].iloc[win].mean(axis=1)            # 바스켓 EW 월수익
    sec_cum = float((1 + bm).prod() - 1)
    mkt_cum = float((1 + mkt.iloc[win]).prod() - 1)
    # breadth: 멤버별 12M 누적이 시장 12M 누적 초과 비율
    mem_cum = (1 + ret[basket].iloc[win]).prod() - 1
    breadth = float((mem_cum > mkt_cum).mean())
    return sec_cum - mkt_cum, breadth


def detect_supercycle(ret, baskets, mkt, i):
    """idx i에서 테마별 수퍼사이클 발동 여부 (3개월 지속). 데이터 ≤ i만."""
    flags = {}
    for th, basket in baskets.items():
        ok = True
        for j in range(PERSIST):
            k = i - j
            ex, br = _excess_breadth(ret, basket, mkt, k)
            if not (pd.notna(ex) and pd.notna(br) and ex >= THRESH_EXCESS and br >= THRESH_BREADTH):
                ok = False
                break
        flags[th] = ok
    return flags


def member_theme(code):
    for th, mem in THEME_MEMBERS.items():
        if code in mem:
            return th
    return None


# ---------- 점수 조정 ----------
def total_for(comp_c, code, variant, sc_flags):
    """변형별 조정 체력. sc_flags: 테마→bool. base는 5컴포넌트 합."""
    base = comp_c["base"] + comp_c["noa"] + comp_c["mom"] + comp_c["echo"]
    bab = comp_c["bab"]
    bonus = 0.0
    th = member_theme(code)
    active = (variant != "base") and (th is not None) and sc_flags.get(th, False)
    if active:
        bab = max(0.0, bab)                # 감점 제거 (저베타 가점 유지)
        if variant == "E_bab_mom":
            bonus = SC_BONUS
    return base + bab + bonus


# ---------- 백테스트 ----------
def _weighted_ret(weights, ret_row):
    return float(sum(w * ret_row.get(c, 0.0) for c, w in weights.items()))


def run(panel, inputs, sector_map, members=None, save=True, label="fixed18"):
    members = members or [c for c in PB.FIXED18 if c in panel.columns]
    months = list(panel.index)
    ret = panel.pct_change()
    mkt = ret.mean(axis=1)                              # 시장 proxy = pool EW (pit 컨벤션)
    baskets = theme_baskets(panel.columns, sector_map)
    sector_of = {c: str(sector_map.get(c, f"_unk_{c}")) for c in members}

    rets = {v: {} for v in VARIANTS}
    turn = {v: [] for v in VARIANTS}
    prev_w = {v: {} for v in VARIANTS}
    sc_history = []

    for i in range(12, len(months) - 1):
        dt = months[i]
        comp = SU.member_components_at(dt + pd.Timedelta(days=1), members, panel, inputs)
        if not comp:
            continue
        sc_flags = detect_supercycle(ret, baskets, mkt, i)
        sc_history.append({"date": str(dt.date()), **{k: bool(v) for k, v in sc_flags.items()}})
        ret_next = ret.iloc[i + 1]
        for v in VARIANTS:
            tot = {c: total_for(comp[c], c, v, sc_flags) for c in comp}
            picks = [c for c in tot if grade(tot[c]) in ("S+", "S", "A")]
            w = apply_weight_caps(picks, {c: sector_of.get(c, f"_unk_{c}") for c in picks}) if picks else {}
            # 턴오버 비용
            alln = set(w) | set(prev_w[v])
            to = sum(abs(w.get(c, 0) - prev_w[v].get(c, 0)) for c in alln) / 2
            turn[v].append(to)
            gross = _weighted_ret(w, ret_next)
            rets[v][months[i + 1]] = gross - to * FLAT_COST
            prev_w[v] = w

    res = {}
    common = None
    series = {v: pd.Series(rets[v]).dropna() for v in VARIANTS}
    for v in VARIANTS:
        common = series[v].index if common is None else common.intersection(series[v].index)
    mkt_c = mkt.reindex(common)
    for v in VARIANTS:
        r = series[v].reindex(common)
        m = PB.metrics(r)
        ex = (r - mkt_c).dropna()
        m["IR"] = float(ex.mean() / ex.std(ddof=1) * np.sqrt(12)) if ex.std(ddof=1) > 0 else 0.0
        m["turnover_yr"] = float(np.mean(turn[v])) * 12 if turn[v] else 0.0
        res[v] = m

    # 게이트
    b = res["base"]
    verdict = {}
    for v in ("E_bab", "E_bab_mom"):
        m = res[v]
        ok_cagr = m["CAGR"] >= b["CAGR"] + GATE_DCAGR
        ok_mdd = m["MDD"] >= b["MDD"] - GATE_DMDD
        ok_ir = m["IR"] >= b["IR"] - GATE_DIR
        verdict[v] = bool(ok_cagr and ok_mdd and ok_ir)
        res[v]["_gate"] = {"cagr": ok_cagr, "mdd": ok_mdd, "ir": ok_ir}

    sc_months = {th: sum(1 for h in sc_history if h.get(th)) for th in THEME_PROXY}

    print("=" * 72)
    print(f"모듈 E 수퍼사이클 오버레이 | {label} | {common[0].date()}~{common[-1].date()} "
          f"{len(common)}개월")
    print(f"수퍼사이클 발동 개월: " + " · ".join(f"{th} {n}" for th, n in sc_months.items()))
    print("=" * 72)
    print(f"{'변형':12}{'CAGR':>9}{'Sharpe':>8}{'MDD':>9}{'IR':>7}{'연회전율':>9}")
    for v in VARIANTS:
        m = res[v]
        print(f"{v:12}{m.get('CAGR',0):>8.1%}{m.get('Sharpe',0):>8.2f}"
              f"{m.get('MDD',0):>8.1%}{m.get('IR',0):>7.2f}{m.get('turnover_yr',0):>9.0%}")
    print(f"\n[사전 등록 게이트] CAGR≥base+{GATE_DCAGR:.0%}p AND MDD악화≤+{GATE_DMDD:.0%}p AND IR≥base−{GATE_DIR}")
    for v in ("E_bab", "E_bab_mom"):
        g = res[v]["_gate"]
        print(f"  {v}: CAGR {res[v]['CAGR']:.1%} vs {b['CAGR']:.1%} ({'OK' if g['cagr'] else 'X'}) | "
              f"MDD {res[v]['MDD']:.1%} vs {b['MDD']:.1%} ({'OK' if g['mdd'] else 'X'}) | "
              f"IR {res[v]['IR']:.2f} vs {b['IR']:.2f} ({'OK' if g['ir'] else 'X'}) → "
              f"{'PASS' if verdict[v] else 'FAIL'}")
    passed = [v for v in ("E_bab", "E_bab_mom") if verdict[v]]
    if passed:
        pick = max(passed, key=lambda v: res[v]["CAGR"])
        print(f"→ 채택 후보: {pick} (병행 관찰부터 — 결정메모 §3)")
    else:
        print("→ 두 변형 모두 FAIL → v3.7.2 유지, 재튜닝 금지")

    if save:
        ts = datetime.datetime.now().strftime("%Y%m%d_%H%M")
        out = f"supercycle_overlay_{ts}.json"
        with open(out, "w", encoding="utf-8") as fh:
            json.dump({"ts": ts, "label": label,
                       "window": [str(common[0].date()), str(common[-1].date()), len(common)],
                       "params": {"thresh_excess": THRESH_EXCESS, "thresh_breadth": THRESH_BREADTH,
                                  "persist": PERSIST, "sc_bonus": SC_BONUS, "cost": FLAT_COST,
                                  "gate": [GATE_DCAGR, GATE_DMDD, GATE_DIR]},
                       "sc_months": sc_months,
                       "results": {v: {k: vv for k, vv in res[v].items()} for v in VARIANTS},
                       "verdict": verdict}, fh, ensure_ascii=False, indent=2, default=float)
        print(f"저장: {out}")
    return res, verdict, sc_history


# ---------- selftest ----------
def _selftest():
    ok = 0
    rng = np.random.default_rng(11)
    Tm = 60
    idx = pd.date_range("2020-01-31", periods=Tm, freq="ME")
    semi = [f"S{i:05d}" for i in range(6)]               # SEMI 바스켓 6종
    other = [f"O{i:05d}" for i in range(20)]
    cols = semi + other
    px = pd.DataFrame(index=idx, columns=cols, dtype=float)
    # 기본: 완만. SEMI는 24~40개월 구간에 수퍼사이클(고수익+고변동=고베타)
    for c in cols:
        px[c] = 1000.0
    for t in range(1, Tm):
        for c in cols:
            if c in semi and 24 <= t <= 40:
                dr = rng.normal(0.13, 0.10)              # 수퍼사이클: 강한 추세+고변동
            else:
                dr = rng.normal(0.004, 0.03)
            px[c].iloc[t] = px[c].iloc[t - 1] * (1 + dr)
    sector_map = {**{c: "반도체 제조업" for c in semi}, **{c: f"기타{ i%4}" for i, c in enumerate(other)}}
    inputs = pd.DataFrame([
        dict(code=c, fiscal_year=fy, F=7, accrual=0.0, noa_ratio=0.7)
        for c in cols for fy in range(2019, 2026)
    ])
    ret = px.pct_change(); mkt = ret.mean(axis=1)
    baskets = theme_baskets(cols, sector_map)
    assert baskets["SEMI"] == semi, "바스켓 구성 오류"; ok += 1
    # 감지: 수퍼사이클 구간 중반(i=34)에 발동, 시작 전(i=18)엔 미발동
    fl_mid = detect_supercycle(ret, baskets, mkt, 34)
    fl_pre = detect_supercycle(ret, baskets, mkt, 18)
    assert fl_mid["SEMI"] and not fl_pre["SEMI"], f"감지 오류 mid={fl_mid} pre={fl_pre}"; ok += 1
    # 대응: 고베타 SEMI 멤버를 fixed18 SEMI로 가정, 수퍼사이클 시 bab 감점 제거 효과
    comp_c = {"base": 9.0, "noa": 0.0, "mom": 2.0, "echo": 0.0, "bab": -2.0}
    base_t = total_for(comp_c, "005930", "base", {"SEMI": True})
    bab_t = total_for(comp_c, "005930", "E_bab", {"SEMI": True})
    mom_t = total_for(comp_c, "005930", "E_bab_mom", {"SEMI": True})
    assert bab_t == base_t + 2.0, f"E_bab 감점제거 오류 {base_t}->{bab_t}"; ok += 1
    assert mom_t == bab_t + SC_BONUS, f"E_bab_mom 가산 오류 {bab_t}->{mom_t}"; ok += 1
    # 비수퍼사이클·비멤버는 base와 동일
    assert total_for(comp_c, "005930", "E_bab", {"SEMI": False}) == base_t; ok += 1
    assert total_for(comp_c, "000270", "E_bab_mom", {"SEMI": True}) == base_t; ok += 1   # 기아=테마 아님
    # 백테스트 동작 (SEMI를 members로)
    members = semi + other[:12]
    res, verdict, _ = run(px, inputs, sector_map, members=members, save=False, label="selftest")
    assert all("CAGR" in res[v] for v in VARIANTS); ok += 1
    # 수퍼사이클에서 SEMI 비중↑ → E_bab CAGR ≥ base (감점제거가 SEMI 픽 늘림)
    assert res["E_bab"]["CAGR"] >= res["base"]["CAGR"] - 1e-9, "E_bab가 base보다 낮음(감점제거 무효)"; ok += 1
    print(f"\n[OK] supercycle_overlay selftest 통과 ({ok} checks)")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--prices", default="kospi_monthly_prices.csv")
    ap.add_argument("--inputs", default="score_inputs_univ.csv")
    ap.add_argument("--liquidity", default="liquidity_sector.csv")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    for f in (a.prices, a.inputs, a.liquidity):
        if not os.path.exists(f):
            raise SystemExit(f"{f} 없음")
    panel = pd.read_csv(a.prices, index_col=0, parse_dates=True)
    panel.columns = [str(c).zfill(6) for c in panel.columns]
    inputs = pd.read_csv(a.inputs, dtype={"code": str}); inputs["code"] = inputs["code"].str.zfill(6)
    ls = pd.read_csv(a.liquidity, dtype={"code": str}); ls["code"] = ls["code"].str.zfill(6)
    sector_map = dict(zip(ls["code"], ls["sector"]))
    run(panel, inputs, sector_map)
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
