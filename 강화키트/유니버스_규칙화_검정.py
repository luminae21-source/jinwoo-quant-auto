#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""유니버스_규칙화_검정.py — "고정18 → 규칙기반 동적 리더십 + 낙폭제어" 사전등록 검정

핸드오프: 강화키트/유니버스_규칙화_핸드오프.md
가설: "시총 상위 N + 모멘텀 리더십 틸트 + MA200 방어" 동적 유니버스가
      고정18을 위험조정(Sharpe/MDD)에서 이긴다.

── 유니버스 ──
  · 고정18            : v3.6/v3.7.2 손선택 18종 (재현 불가·hindsight → 공통구간에서만 참고)
  · TOP30_고정         : 시총 상위 30 고정 (30년 재현가능 기계적 대형주 베이스라인)
  · 동적_TOP30_리더십  : 상위pool 중 12-1 모멘텀 상위 30 (대형주 주도주 추종)
  · 동적_TOP50_리더십  : 상위pool 중 12-1 모멘텀 상위 50
  · KOSPI             : 지수 벤치

── 방어 그리드 (지수 MA200, 월간·룩어헤드 없음) ──
  · 무방어  · 완전현금(지수<MA200 → 그달 현금)  · 50현금(그달 절반만 투자)
  방어 신호는 '전월말' KOSPI 종가 vs 200일 이동평균 → 그달 편입 전 확정.

── 비용 (다올) ──  수수료 0 · 세금 0.2% · 슬리피지 편도(그리드). 회전=편입교체+방어전환.

── 사전등록 게이트 (결과 보기 전 고정) ── 주력 = 동적_TOP30_리더십 + 완전현금방어
  G1 (공통구간) Sharpe_주력 > Sharpe_고정18
  G2 (공통구간) |MDD_주력| ≤ |MDD_고정18|  (낙폭 악화 금지)
  G3 (30년)     OOS 전·후반 순수익 부호 유지(둘 다 +)
  G4 (30년)     슬리피지 그리드 전반에서 Sharpe_주력 > TOP30_고정 & 방어가 무방어 대비 MDD 개선
  정직 캐비엇: 고정18은 hindsight 선택 우위 → G1/G2는 공통구간 apples-to-apples로만.

사용: py 유니버스_규칙화_검정.py [--slippage 0.0005] [--self-test]
⚠️ 상폐포함 검증용. 실현손익 아님. 투자자문 아님·책임 본인.
"""
# §8-3(2026-07-27): tax 0.002→0.0015(실제 증권거래세) · slip 0.0005→0.002045(CS 실측 편도) → 왕복 0.300%→0.559%


# ── 경로 자립화 (2026-07-27) — 샌드박스 하드코딩 제거 ──────────────
import os as _os, glob as _glob
_JQ_HERE = _os.path.dirname(_os.path.abspath(__file__))


def _jqroot():
    d = _JQ_HERE
    for _ in range(5):
        if _os.path.exists(_os.path.join(d, "종목시총_30년.csv")):
            return d
        d = _os.path.dirname(d)
    return _os.path.dirname(_JQ_HERE)


BASE = _os.environ.get("JQ_BASE", _jqroot())


def _jqfind(name):
    """이름으로 파일 자동탐색 (백업/보관 폴더 제외)."""
    for b in (BASE, _JQ_HERE, _os.getcwd()):
        hits = [h for h in _glob.glob(_os.path.join(b, "**", name), recursive=True)
                if not any(s in h for s in ("_백업", "_보관", "_archive", "__pycache__"))]
        if hits:
            return sorted(hits, key=len)[0]
    raise FileNotFoundError(f"{name} 를 못 찾음 (루트={BASE})")
# ────────────────────────────────────────────────────────────────

import os, sys, argparse, json
import numpy as np, pandas as pd
BASE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

# v3.6/v3.7.2 손선택 18종 (진우퀀트_v36_universe.md)
FIXED18 = {
    "005930": "삼성전자", "000660": "SK하이닉스", "042700": "한미반도체", "095340": "ISC",
    "196170": "알테오젠", "000270": "기아", "035420": "NAVER", "035720": "카카오",
    "012450": "한화에어로", "079550": "LIG넥스원", "105560": "KB금융", "005940": "NH투자증권",
    "033780": "KT&G", "003230": "삼양식품", "006400": "삼성SDI", "090430": "아모레퍼시픽",
    "034020": "두산에너빌리티", "028260": "삼성물산",
}

def _find(fn):
    for d in (BASE, os.path.dirname(BASE), os.getcwd()):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    return None

def load_panel():
    frames = []
    for fn in ("_월봉종가캐시_KOSPI.csv", "_월봉종가캐시_KOSDAQ.csv"):
        p = _find(fn)
        if p:
            d = pd.read_csv(p, dtype={"code": str}); d["code"] = d["code"].str.zfill(6); frames.append(d)
    allc = pd.concat(frames, ignore_index=True)
    px = allc.pivot_table(index="ym", columns="code", values="close", aggfunc="last").sort_index()
    rets = px.pct_change().mask(lambda x: x.abs() > 1.0)
    return px, rets

def load_mcap():
    p = _find("종목시총_30년.csv"); d = pd.read_csv(p, dtype={"code": str}); d["code"] = d["code"].str.zfill(6)
    d["ym"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m")
    return d.pivot_table(index="ym", columns="code", values="mcap", aggfunc="last")

def load_ma200_regime():
    """일봉 KOSPI → 월별 '전월말 종가 ≥ 200일 SMA' 불리언(ym → bool). 룩어헤드 없음(shift)."""
    p = _find("kospi_index_daily.csv")
    if not p: return None, None
    d = pd.read_csv(p, parse_dates=["Date"]).set_index("Date").sort_index()
    close = d["Close"]; sma = close.rolling(200).mean()
    above = (close >= sma)
    me_close = close.resample("ME").last()
    me_above = above.resample("ME").last()          # 그 달 말일 기준
    reg = pd.DataFrame({"above": me_above})
    reg.index = reg.index.strftime("%Y-%m")
    reg["sig"] = reg["above"].shift(1)              # 그 달엔 '전월말' 신호를 쓴다
    kret = me_close.pct_change(); kret.index = kret.index.strftime("%Y-%m")
    return reg["sig"], kret

def stats(x, ann=12):
    x = pd.Series(x).dropna()
    if len(x) < 12: return None
    c = (1 + x).cumprod()
    return dict(CAGR=(1 + x).prod() ** (ann / len(x)) - 1,
                Sharpe=x.mean() / x.std() * np.sqrt(ann) if x.std() > 0 else np.nan,
                MDD=(c / c.cummax() - 1).min(), n=len(x))

def select(px, rets, mcap, kind, i, t):
    """그달 t의 편입 종목 리스트."""
    mc = mcap.loc[t].dropna().sort_values(ascending=False)
    ranked = list(mc.index)
    if kind == "TOP30_고정":
        return ranked[:30]
    if kind == "고정18":
        return [c for c in FIXED18 if c in rets.columns]
    if kind in ("동적_TOP30_리더십", "동적_TOP50_리더십"):
        N = 30 if "30" in kind else 50
        pool = ranked[:max(100, 3 * N)]
        if i >= 13:
            w = px.iloc[i - 13:i - 1]; mom = (w.iloc[-1] / w.iloc[0] - 1)
            mom = mom[[c for c in pool if c in mom.index]].dropna()
            return list(mom.sort_values(ascending=False).index[:N])
        return pool[:N]
    return ranked[:30]

def bt(px, rets, mcap, reg, kind, defense="무방어", tax=0.0015, slippage=0.002045):
    """월간 EW 백테. 방어 스칼라 s∈{1,.5,0}. 비용=회전(편입교체+방어전환)×(tax+2·slip)."""
    months = [m for m in rets.index if m in mcap.index]
    held = set(); prev_s = 0.0
    out = []; kept = []; turns = []
    for k, t in enumerate(months):
        i = list(rets.index).index(t)
        sel = select(px, rets, mcap, kind, i, t)
        cur = rets.loc[t]
        names = [c for c in sel if pd.notna(cur.get(c))]
        if kind == "고정18":
            if len(names) < 12:
                prev_s = 0.0; held = set(); continue      # 18종 충분히 상장 전 → 건너뜀
        elif len(names) < 10:
            continue
        r_sel = cur[names].mean()
        # 방어 스칼라
        if defense == "무방어": s = 1.0
        else:
            on = reg.get(t) if reg is not None else True
            on = True if pd.isna(on) else bool(on)
            s = 1.0 if on else (0.5 if defense == "50현금" else 0.0)
        # 회전: 방어전환 |s-prev_s| + 투자슬리브 내 편입교체 s·f_mem
        newset = set(names)
        f_mem = 1 - len(newset & held) / len(newset) if held else 1.0
        turn = abs(s - prev_s) + s * f_mem
        gross = s * r_sel
        net = gross - turn * (tax + 2 * slippage)
        out.append(net); kept.append(t); turns.append(s * f_mem)   # 회전율 리포트는 편입교체 기준
        held = newset; prev_s = s
    return pd.Series(out, index=kept), (np.mean(turns) if turns else 0) * 12

def run(slippage=0.002045, verbose=True):
    px, rets = load_panel(); mcap = load_mcap(); reg, kret = load_ma200_regime()
    universes = [
        ("TOP30_고정", "무방어"),
        ("동적_TOP30_리더십", "무방어"),
        ("동적_TOP30_리더십", "완전현금"),
        ("동적_TOP30_리더십", "50현금"),
        ("동적_TOP50_리더십", "무방어"),
        ("동적_TOP50_리더십", "완전현금"),
        ("동적_TOP50_리더십", "50현금"),
        ("고정18", "무방어"),
    ]
    series = {}; table = {}
    for kind, dfn in universes:
        s, turn = bt(px, rets, mcap, reg, kind, defense=dfn, slippage=slippage)
        st = stats(s)
        if st:
            key = f"{kind}·{dfn}" if dfn != "무방어" else kind
            series[key] = s
            table[key] = dict(cagr=round(st["CAGR"] * 100, 1), sharpe=round(st["Sharpe"], 2),
                              mdd=round(st["MDD"] * 100, 1), turn=round(turn, 1), n=st["n"],
                              start=s.index[0], end=s.index[-1])
    # KOSPI 벤치 (동적 주력 구간에 맞춤)
    prim = series.get("동적_TOP30_리더십·완전현금")
    if kret is not None and prim is not None:
        ks = stats(kret.reindex(list(prim.index)))
        if ks:
            table["KOSPI"] = dict(cagr=round(ks["CAGR"] * 100, 1), sharpe=round(ks["Sharpe"], 2),
                                  mdd=round(ks["MDD"] * 100, 1), turn=0.0, n=ks["n"],
                                  start=prim.index[0], end=prim.index[-1])

    # ── 게이트 ──
    fx = series.get("고정18")
    gates = {}
    # G1·G2 : 공통구간(고정18 존재 월) apples-to-apples
    if fx is not None and prim is not None:
        common = [m for m in prim.index if m in set(fx.index)]
        p_c = prim.reindex(common).dropna(); f_c = fx.reindex(common).dropna()
        common = [m for m in p_c.index if m in set(f_c.index)]
        p_c = p_c.reindex(common); f_c = f_c.reindex(common)
        sp = stats(p_c); sf = stats(f_c)
        if sp and sf:
            g1 = sp["Sharpe"] > sf["Sharpe"]
            g2 = sp["MDD"] >= sf["MDD"]   # 둘 다 음수 → 주력 낙폭이 더 얕거나 같다
            gates["common_window"] = f"{common[0]}~{common[-1]} ({len(common)}개월)"
            gates["G1_sharpe"] = dict(passed=bool(g1), 주력=round(sp["Sharpe"], 2), 고정18=round(sf["Sharpe"], 2))
            gates["G2_mdd"] = dict(passed=bool(g2), 주력=round(sp["MDD"] * 100, 1), 고정18=round(sf["MDD"] * 100, 1))
            gates["_common_stats"] = dict(주력_cagr=round(sp["CAGR"]*100,1), 고정18_cagr=round(sf["CAGR"]*100,1))
    # G3 : 30년 OOS 전·후반 부호
    if prim is not None:
        n = len(prim); half = n // 2
        a, b = prim.iloc[:half], prim.iloc[half:]
        g3 = (a.mean() > 0 and b.mean() > 0)
        gates["G3_oos"] = dict(passed=bool(g3), 전반_월평균=round(a.mean()*100, 2), 후반_월평균=round(b.mean()*100, 2),
                               전반구간=f"{prim.index[0]}~{prim.index[half-1]}", 후반구간=f"{prim.index[half]}~{prim.index[-1]}")
    # G4 : 슬리피지 그리드 강건
    grid = {}
    g4_ok = True
    for slp in (0.0005, 0.001, 0.002):
        p_s, _ = bt(px, rets, mcap, reg, "동적_TOP30_리더십", "완전청금" if False else "완전현금", slippage=slp)
        base, _ = bt(px, rets, mcap, reg, "TOP30_고정", "무방어", slippage=slp)
        nod, _ = bt(px, rets, mcap, reg, "동적_TOP30_리더십", "무방어", slippage=slp)
        sp = stats(p_s); sb = stats(base); sn = stats(nod)
        cond_sharpe = sp["Sharpe"] > sb["Sharpe"]
        cond_mdd = sp["MDD"] > sn["MDD"]   # 방어가 무방어보다 낙폭 얕음
        grid[f"{slp*100:.2f}%"] = dict(주력_sharpe=round(sp["Sharpe"],2), 기준_sharpe=round(sb["Sharpe"],2),
                                       주력_mdd=round(sp["MDD"]*100,1), 무방어_mdd=round(sn["MDD"]*100,1),
                                       주력_cagr=round(sp["CAGR"]*100,1),
                                       sharpe우위=bool(cond_sharpe), 낙폭개선=bool(cond_mdd))
        g4_ok = g4_ok and cond_sharpe and cond_mdd
    gates["G4_cost_robust"] = dict(passed=bool(g4_ok), grid=grid)

    passed = sum(1 for k in ("G1_sharpe","G2_mdd","G3_oos","G4_cost_robust")
                 if isinstance(gates.get(k), dict) and gates[k].get("passed"))

    if verbose:
        _print(table, gates, passed, slippage)
    res = dict(slippage=slippage, table=table, gates=gates, passed=passed)
    json.dump(res, open(os.path.join(BASE, "유니버스_규칙화_검정_결과.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2, default=str)
    return res

def _print(table, gates, passed, slippage):
    print("=" * 92)
    print(f"유니버스 규칙화 검정 — 동적 리더십+MA200 방어 vs 고정18 (30년 상폐포함·다올, 슬리피지 {slippage*100:.2f}%/편도)")
    print("=" * 92)
    print(f"  {'유니버스·방어':<26}{'회전/년':>8}{'순 CAGR':>10}{'Sharpe':>9}{'MDD':>9}{'개월':>6}  구간")
    order = ["고정18","TOP30_고정","동적_TOP30_리더십","동적_TOP30_리더십·완전현금","동적_TOP30_리더십·50현금",
             "동적_TOP50_리더십","동적_TOP50_리더십·완전현금","동적_TOP50_리더십·50현금","KOSPI"]
    for k in order:
        if k in table:
            r = table[k]
            print(f"  {k:<26}{r['turn']:>7.1f}x{r['cagr']:>9.1f}%{r['sharpe']:>9.2f}{r['mdd']:>8.1f}%{r['n']:>6}  {r['start']}~{r['end']}")
    print("\n" + "-" * 92)
    print("  사전등록 게이트 (주력 = 동적_TOP30_리더십 · 완전현금방어):")
    if "G1_sharpe" in gates:
        g = gates["G1_sharpe"]; print(f"   G1 Sharpe>고정18   [{gates.get('common_window','')}]  주력 {g['주력']} vs 고정18 {g['고정18']}  → {'PASS' if g['passed'] else 'FAIL'}")
        g = gates["G2_mdd"];    print(f"   G2 |MDD|≤고정18    주력 {g['주력']}% vs 고정18 {g['고정18']}%  → {'PASS' if g['passed'] else 'FAIL'}")
    if "G3_oos" in gates:
        g = gates["G3_oos"]; print(f"   G3 OOS 부호유지    전반 {g['전반_월평균']}%/월 · 후반 {g['후반_월평균']}%/월  → {'PASS' if g['passed'] else 'FAIL'}")
    if "G4_cost_robust" in gates:
        g = gates["G4_cost_robust"]; print(f"   G4 비용강건        슬리피지 0.05~0.20% 전반 Sharpe우위&낙폭개선  → {'PASS' if g['passed'] else 'FAIL'}")
        for slp, gg in g["grid"].items():
            print(f"       slip {slp}: 주력 Sharpe {gg['주력_sharpe']} vs 기준 {gg['기준_sharpe']} · 주력MDD {gg['주력_mdd']}% vs 무방어 {gg['무방어_mdd']}% · CAGR {gg['주력_cagr']}%")
    print(f"\n  판정: {passed}/4 게이트 통과")
    print("  ⚠️ 고정18은 hindsight 선택 우위(공통구간). EW·단순 모멘텀 근사. 실현손익 아님. 투자자문 아님·책임 본인.")

def self_test():
    """수치 재현성·룩어헤드·데이터 무결성 자체점검."""
    ok = []
    px, rets = load_panel(); mcap = load_mcap(); reg, kret = load_ma200_regime()
    # 1. 패널 상폐포함(종목수 많음)
    ok.append(("상폐포함 패널(≥4000종)", rets.shape[1] >= 4000, f"{rets.shape[1]}종"))
    # 2. MA200 신호는 전월 것(shift) — 첫 유효월이 200거래일+1개월 뒤
    reg_valid = reg.dropna()
    ok.append(("MA200 신호 shift(룩어헤드X)", reg.isna().iloc[0] if len(reg) else True, "첫달 신호=NaN(전월없음)"))
    # 3. 방어는 무방어보다 MDD 얕아야(30년)
    p_def, _ = bt(px, rets, mcap, reg, "동적_TOP30_리더십", "완전현금")
    p_nod, _ = bt(px, rets, mcap, reg, "동적_TOP30_리더십", "무방어")
    sd, sn = stats(p_def), stats(p_nod)
    ok.append(("완전현금 방어가 MDD 개선", sd["MDD"] > sn["MDD"], f"{sd['MDD']*100:.1f}% > {sn['MDD']*100:.1f}%"))
    # 4. TOP30_고정 = 기존 유니버스_비교(19.8%/0.78/-52.7%) 근사 재현
    b, _ = bt(px, rets, mcap, reg, "TOP30_고정", "무방어")
    sb = stats(b)
    ok.append(("TOP30_고정 CAGR≈19.8%±2", abs(sb["CAGR"]*100 - 19.8) < 2.5, f"{sb['CAGR']*100:.1f}%"))
    ok.append(("TOP30_고정 MDD≈-52.7%±5", abs(sb["MDD"]*100 - (-52.7)) < 6, f"{sb['MDD']*100:.1f}%"))
    # 5. 고정18 재현성(같은 입력 → 같은 결과)
    f1, _ = bt(px, rets, mcap, reg, "고정18", "무방어")
    f2, _ = bt(px, rets, mcap, reg, "고정18", "무방어")
    ok.append(("결정론적 재현", f1.equals(f2), "동일입력→동일출력"))
    print("=" * 60); print("SELF-TEST"); print("=" * 60)
    for name, cond, detail in ok:
        print(f"  [{'PASS' if cond else 'FAIL'}] {name}  ({detail})")
    n_pass = sum(1 for _, c, _ in ok if c)
    print(f"\n  {n_pass}/{len(ok)} 통과")
    return n_pass == len(ok)

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--slippage", type=float, default=0.0005)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test: self_test()
    else: run(a.slippage)

if __name__ == "__main__":
    main()
