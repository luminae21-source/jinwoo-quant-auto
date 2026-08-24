# -*- coding: utf-8 -*-
"""
jq_sector_mom_backtest_skeleton.py
==================================
섹터(산업) 모멘텀 사전등록 **후보 #5** 백테스트 **골격(SKELETON)**.
근거 스펙: 진우퀀트_섹터모멘텀_사전등록_초안_2026-07-10.md

⚠️ 이것은 골격이다. 성과 수치를 주장하지 않는다. TODO 표시된 부분(일봉 정밀 청산·
   DSR/PBO/White 정식 루틴)은 PC 프런티어 도구로 연결해야 판정 가능.
원칙: production/L1(score_v37_2)·C(v3.9)·D(v4.0)·팩터엔진 **무수정**.
      신호=theme_heat.py 엔진 무수정 재사용 / 레짐=regime_history_v40 /
      청산=매도규칙서(2.5ATR·-20%캡·+1R절반·트레일링·20일·thesis=섹터heat이탈).
      전 구간 PIT(compute_theme_heat(i)는 i시점까지만 사용).

실행: 반드시 **이 폴더(Desktop\진우퀀트)에서** 실행할 것 —
      theme_heat/theme_classify가 상대경로(liquidity_sector.csv 등)를 읽으므로 cwd 의존.
      python jq_sector_mom_backtest_skeleton.py --selftest   # 신호 배선 점검(성과 아님)
      python jq_sector_mom_backtest_skeleton.py --run        # 월간 골격 백테(수치 해석 금지)

샌드박스 검증(2026-07-10): 신호 배선 OK(패널 79M×642종목, 최신 6대장주 선정,
  12개월 전 PIT 시점은 다른 종목군=look-ahead 없음), 백테 루프·비용·오버레이·잔존알파
  회귀 실행 확인. DSR/PBO/White·일봉정밀청산은 미연결(TODO).
"""
import os, sys, argparse, json, warnings
import numpy as np, pandas as pd
warnings.simplefilter("ignore")   # pct_change FutureWarning 등 노이즈 억제(결과 JSON만 출력)

HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

# ── theme_heat 엔진 무수정 재사용(소스 직접 로드) ─────────────────────────────
import importlib.util
def _load(fname, mod):
    p = os.path.join(HERE, fname)
    spec = importlib.util.spec_from_file_location(mod, p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m
TH = _load("theme_heat.py", "theme_heat")   # load_panel, _engines, compute_theme_heat, surface_members, load_regime, load_size, load_daily_for

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG — 사전등록 스펙과 **동일값**. 등록 시 최종 락(사후변경 금지).
# ══════════════════════════════════════════════════════════════════════════════
CFG = dict(
    K_SECTORS      = 3,        # 상위 K 섹터
    M_LEADERS      = 3,        # 섹터당 대장주 수
    BREADTH_MIN    = 0.60,     # 응집도 필터(breadth_3m ≥) — supercycle=True면 우회
    ALLOW_SUPERCYCLE = True,
    LONG_SHORT     = False,    # True=MG99식 산업 롱숏(승자섹터 롱−패자섹터 숏, dollar-neutral). 후보 #6
    SHORT_K        = 3,        # 숏할 하위(패자) 섹터 수
    REBALANCE      = "M",      # 월 리밸(월간 패널·MG99/MOP12 정합). 주간은 주간패널 필요(데이터 부재)
    SIZING         = "EW",     # "EW" 동일가중 | "INV_VOL" ex-ante 변동성 역가중(MOP12)
    TARGET_VOL     = 0.12,     # INV_VOL 정규화용 목표 연변동성
    COST_ONEWAY    = 0.0030,   # 편도 비용(세0.18%+수수료·슬리피지). 강건성: ±50% 재검(합격선 g)
    # 청산(매도규칙서) —
    ATR_K          = 2.5,
    STOP_CAP       = 0.20,     # -20% 캡
    TRAIL_K        = 2.5,
    TIME_STOP_D    = 20,       # 거래일
    TIME_STOP_BAND = 0.05,     # ±5% 횡보
    # 붕괴 오버레이(DM16) —
    OVERLAY        = True,
    VKOSPI_PANIC_PCTILE = 0.80, # 사전변동성 상위 → 패닉 조건(ii)
    START          = "2010-01",  # PIT 백테 시작(데이터 허용 범위서 최장). 절대치 신뢰금지→robustness 중심
)

# ── 데이터 로더(전부 기존 파일 재사용) ─────────────────────────────────────────
def load_signal_ctx():
    """theme_heat main()과 동일 셋업 → (panel, fine, name, E, TC, size, regime)."""
    E, TC = TH._engines()
    panel = TH.load_panel()
    fine, name = TC.load_fine_map()
    size = TH.load_size()          # {code:(mcap,adtv)}
    regime = TH.load_regime()      # {YYYY-MM: state}
    return panel, fine, name, E, TC, size, regime

def load_factors():
    """korea_factors_monthly.csv: date,MKT,SMB,HML,WML,RF — 잔존알파 회귀 통제군.
    TODO(등록 전): WML 대신 L1의 정확한 Mom12·Echo 계열로 교체(factor_data_loader)."""
    p = os.path.join(HERE, "korea_factors_monthly.csv")
    f = pd.read_csv(p, parse_dates=["date"]).set_index("date")
    return f

def load_vkospi():
    p = os.path.join(HERE, "vkospi_daily.csv")
    v = pd.read_csv(p, parse_dates=["Date"]).set_index("Date")["VKOSPI"]
    return v.resample("ME").last()   # 월말 VKOSPI

# ── 성능: ctx·수익률·heat 캐시 ────────────────────────────────────────────────
# 핵심: heat(compute_theme_heat)는 K/M/오버레이와 무관 → 월별 1회만 계산해 캐시하면
#       격자(--judge)가 12배 재계산하던 걸 제거. 디스크 저장으로 재실행은 즉시.
import pickle
_CTX = None; _RET = None
_HEAT = {"key": None, "map": None}

def get_ctx():
    """panel·engines·fine·size·regime + 수익률 DataFrame을 1회만 로드(격자 반복 로드 방지)."""
    global _CTX, _RET
    if _CTX is None:
        _CTX = load_signal_ctx()
        _RET = _CTX[0].pct_change().fillna(0.0)   # member_cum용 수익률 1회 계산
    return _CTX

def _cache_key(panel): return f"{panel.index[-1].date()}_{panel.shape[0]}x{panel.shape[1]}"

def build_signal_cache(start_i, disk=True, path=None):
    """compute_theme_heat를 start_i~끝 월별 1회 계산 → 메모리+디스크 캐시(sector_heat_cache.pkl).
    첫 --run/--judge에서 1회(전 구간 ~1-2분) 빌드 후, 이후·격자 전체가 재사용."""
    ctx = get_ctx(); panel, fine, name, E, TC, size, regime = ctx
    key = _cache_key(panel); path = path or os.path.join(HERE, "sector_heat_cache.pkl")
    if _HEAT["key"] == key and _HEAT["map"] is not None:
        return _HEAT["map"]
    if disk and os.path.exists(path):
        try:
            d = pickle.load(open(path, "rb"))
            if d.get("key") == key:
                _HEAT.update(key=key, map=d["map"]); return _HEAT["map"]
        except Exception: pass
    hmap = {}
    for i in range(start_i, len(panel)):
        df, cm, members_in = TH.compute_theme_heat(panel, fine, name, E, TC, min_members=5, i=i)
        hmap[i] = (df, members_in)
    _HEAT.update(key=key, map=hmap)
    if disk:
        try: pickle.dump({"key": key, "map": hmap}, open(path, "wb"))
        except Exception: pass
    return hmap

# ── 1) 신호: i시점 상위 섹터 + 대장주 (PIT·캐시 사용) ──────────────────────────
def signal_at(i, ctx=None):
    ctx = ctx or get_ctx(); panel, fine, name, E, TC, size, regime = ctx
    hmap = _HEAT.get("map")
    if hmap is not None and i in hmap:            # 캐시 히트(재계산 없음)
        df, members_in = hmap[i]
    else:
        df, cm, members_in = TH.compute_theme_heat(panel, fine, name, E, TC, min_members=5, i=i)
    if df is None or len(df) == 0: return []
    # 상위 K 섹터 + 응집도(breadth 또는 supercycle) 필터
    sel = df.sort_values("heat_score", ascending=False)
    sel = sel[(sel["breadth_3m"] >= CFG["BREADTH_MIN"]) |
              (CFG["ALLOW_SUPERCYCLE"] & sel["supercycle"].astype(bool))].head(CFG["K_SECTORS"])
    retdf = _RET if _RET is not None else panel.pct_change().fillna(0.0)   # 1회 계산분 재사용
    picks = []
    for theme in sel["theme"]:
        basket = members_in.get(theme, [])
        # 대장주 = 섹터 내 상대강도(ret_3m) 상위 M, 유동성(mcap) 필터
        rs = []
        for c in basket:
            try: r3 = TH.member_cum(retdf, c, i, 3)
            except Exception: r3 = np.nan
            mcap = (size.get(c) or (np.nan,))[0]
            rs.append((c, r3, mcap))
        rs = [x for x in rs if pd.notna(x[1])]
        rs.sort(key=lambda x: x[1], reverse=True)   # RS 상위
        picks += [c for c, _, _ in rs[:CFG["M_LEADERS"]]]
    return list(dict.fromkeys(picks))   # 중복 제거, 순서 유지

def short_at(i, ctx=None):
    """MG99 숏레그(후보 #6): heat 하위 SHORT_K 섹터(패자산업)의 대표주 M(유동성 상위).
    ⚠️ 개인 공매도 제약·한국 공매도 금지 반복 → 연구·측정용. 집행은 프록시/미집행(스펙 §15)."""
    ctx = ctx or get_ctx(); panel, fine, name, E, TC, size, regime = ctx
    hmap = _HEAT.get("map")
    if hmap is not None and i in hmap: df, members_in = hmap[i]
    else: df, cm, members_in = TH.compute_theme_heat(panel, fine, name, E, TC, min_members=5, i=i)
    if df is None or len(df) == 0: return []
    sel = df.sort_values("heat_score", ascending=True).head(CFG["SHORT_K"])   # 하위(패자) 섹터
    picks = []
    for theme in sel["theme"]:
        basket = members_in.get(theme, [])
        liq = sorted(basket, key=lambda c: ((size.get(c) or (0,))[0] or 0), reverse=True)  # 유동성 상위(차입 가능성)
        picks += liq[:CFG["M_LEADERS"]]
    return list(dict.fromkeys(picks))

# ── 2) 사이징 ──────────────────────────────────────────────────────────────────
def weights(codes, panel, i):
    if not codes: return {}
    if CFG["SIZING"] == "EW":
        w = {c: 1.0/len(codes) for c in codes}
    else:  # INV_VOL — ex-ante σ(t-1) 역가중 (look-ahead 없음), 목표변동성 정규화
        rets = panel.pct_change()
        inv = {}
        for c in codes:
            s = rets[c].iloc[max(0,i-12):i].std()   # i시점 직전까지만
            inv[c] = (1.0/s) if (pd.notna(s) and s>0) else 0.0
        tot = sum(inv.values()) or 1.0
        w = {c: inv[c]/tot for c in codes}
    return w

# ── 3) 붕괴 오버레이(DM16): 패닉=RISK_OFF AND VKOSPI 상위 → 익스포저 축소 ─────────
def overlay_scale(month, regime, vk_series, vk_thresh):
    if not CFG["OVERLAY"]: return 1.0
    state = regime.get(month, "")
    vk = vk_series.get(pd.Timestamp(month + "-01") + pd.offsets.MonthEnd(0), np.nan)
    risk_off = (state == "RISK_OFF")
    high_vol = (pd.notna(vk) and pd.notna(vk_thresh) and vk >= vk_thresh)
    if risk_off and high_vol: return 0.0     # 패닉 → 현금화(변형: 0.5)
    if risk_off or high_vol:  return 0.5     # 한쪽만 → 축소
    return 1.0

# ── 4) 청산(매도규칙서) — 월간근사 + 일봉정밀 스텁 ─────────────────────────────
# 월간근사(기본): 월말 종가로 손절/트레일/시간/thesis 점검(구현 단순).
# 일봉정밀(TODO): load_daily_for()로 장중 2.5ATR 손절·+1R 절반·트레일 정확 반영.
def atr14_monthly_proxy(panel, c, i):
    """일봉 부재 시 근사 ATR(월간 변동폭 기반). 정밀판은 load_daily_for로 대체(TODO)."""
    r = panel[c].pct_change().iloc[max(0,i-14):i].abs().mean()
    return (panel[c].iloc[i] * r) if pd.notna(r) else np.nan

# ── 5) 성과·판정 지표 ──────────────────────────────────────────────────────────
def metrics(ret_m, bench_ew_m, factors):
    out = {}
    r = ret_m.dropna()
    out["n_months"] = int(len(r))
    out["cagr"] = float((1+r).prod()**(12/max(len(r),1)) - 1)
    out["sharpe"] = float(r.mean()/r.std()*np.sqrt(12)) if r.std()>0 else np.nan
    cum = (1+r).cumprod(); out["mdd"] = float((cum/cum.cummax()-1).min())
    # 정직 EW 비열위(합격선 d)
    ex_ew = (r - bench_ew_m.reindex(r.index)).dropna()
    out["ann_alpha_vs_EW"] = float(ex_ew.mean()*12)
    out["IR_vs_EW"] = float(ex_ew.mean()/ex_ew.std()*np.sqrt(12)) if ex_ew.std()>0 else np.nan
    # 잔존(orthogonalized) 알파(합격선 b): r-RF ~ MKT+SMB+HML+WML
    f = factors.reindex(r.index)
    valid = (f["RF"].notna() & f["MKT"].notna()).values   # HML/SMB 결측은 X에서 0채움(행 삭제 X)
    idx = r.index[valid]
    if len(idx) > 12:
        y = (r.reindex(idx) - f["RF"].reindex(idx)).values
        X = f.loc[idx, ["MKT","SMB","HML","WML"]].fillna(0.0).values
        X = np.column_stack([np.ones(len(idx)), X])
        beta, *_ = np.linalg.lstsq(X, y, rcond=None)
        resid = y - X@beta; dof = max(len(idx)-X.shape[1], 1)
        xtx_inv = np.linalg.pinv(X.T@X)   # 공선성/특이행렬 방어(짧은 구간·팩터 결측)
        se = float(np.sqrt(max((resid@resid/dof) * xtx_inv[0,0], 0.0)))
        out["resid_alpha_ann"] = float(beta[0]*12)
        out["resid_alpha_t"] = float(beta[0]/se) if se>0 else np.nan
    else:
        out["resid_alpha_ann"] = out["resid_alpha_t"] = np.nan
    return out

# ── 다중검정/강건성: 기존 stats_v1.py 연결(DSR·PBO·White RC/SPA) — 합격선 c ─────
S1 = _load("stats_v1.py", "stats_v1")

def run_trial_grid():
    """격자 전 설정으로 run_backtest → 월수익 매트릭스(T×N)+벤치+각 시행 월Sharpe.
    (골격: CFG 전역을 임시 변경하며 순회. primary=현 CFG값)."""
    import itertools as it
    # 롱숏(#6)이면 SHORT_K를 격자에(오버레이 미적용), 롱온리(#5)면 OVERLAY를 격자에
    GRID = (dict(K_SECTORS=[2,3,4], M_LEADERS=[2,3], SHORT_K=[2,3,4]) if CFG["LONG_SHORT"]
            else dict(K_SECTORS=[2,3,4], M_LEADERS=[2,3], OVERLAY=[True,False]))
    keys = list(GRID); base = {k: CFG[k] for k in keys}
    series, bench = {}, None
    for combo in it.product(*[GRID[k] for k in keys]):
        for k, v in zip(keys, combo): CFG[k] = v
        sr, br, _ = run_backtest()
        series[combo] = sr; bench = br if bench is None else bench
    pk = tuple(base[k] for k in keys)
    for k, v in base.items(): CFG[k] = v            # 복원
    df = pd.DataFrame(series).dropna()
    primary = df[pk] if pk in df.columns else df.iloc[:, 0]
    sr_trials = [float(df[c].mean()/df[c].std()) for c in df.columns if df[c].std() > 0]
    return df.values, sr_trials, primary, bench.reindex(df.index)

def robustness(mat, sr_trials, primary, ew):
    dsr, srm, sr0 = S1.deflated_sharpe_ratio(primary.values, n_trials=max(len(sr_trials), 2), sr_trials=sr_trials)
    pbo, _ = S1.pbo_cscv(mat, S=min(16, max(4, (len(primary)//2)*2)))
    rc = S1.reality_check_spa(mat, benchmark=ew.values)
    return dict(DSR=float(dsr), PBO=float(pbo), p_white_rc=rc["p_white_rc"],
                p_hansen_spa=rc["p_hansen_spa"], spa_reliable=rc["spa_reliable"])

def judge():
    """§7 확정 합격선으로 PASS/GRAY/FAIL 기계 판정. 자본배정은 Track S OOS 후(12월)."""
    mat, srt, primary, ew = run_trial_grid()
    m = metrics(primary, ew, load_factors()); rob = robustness(mat, srt, primary, ew)
    ra, t = m.get("resid_alpha_ann"), m.get("resid_alpha_t")
    if   ra is not None and t is not None and ra >= 0.02 and t > 2: b = "PASS"
    elif ra is not None and t is not None and ra >= 0.01 and t > 2: b = "GRAY(x0.5)"
    else: b = "FAIL"
    c = (rob["DSR"] > 0.95) and (rob["PBO"] < 0.5) and (rob["p_white_rc"] < 0.05)   # 합격선 c
    d = (m.get("IR_vs_EW") or -1) >= 0                                               # 합격선 d
    verdict = "채택후보" if (b == "PASS" and c and d) else ("병행x0.5" if (b == "GRAY(x0.5)" and c and d) else "기각")
    return dict(resid_alpha_ann=ra, resid_alpha_t=t, IR_vs_EW=m.get("IR_vs_EW"), **rob,
                b=b, c_pass=bool(c), d_pass=bool(d), VERDICT=verdict,
                note="자본배정=Track S OOS 확인 후(12월). 2025~26 절대치 신뢰 금지.")

# ── 6) 백테 루프(월간·PIT) ─────────────────────────────────────────────────────
def run_backtest():
    ctx = get_ctx(); panel = ctx[0]; regime = ctx[6]
    factors = load_factors(); vk = load_vkospi()
    vk_thresh = vk.quantile(CFG["VKOSPI_PANIC_PCTILE"])
    idx0 = panel.index.searchsorted(pd.Timestamp(CFG["START"]))
    build_signal_cache(idx0)          # heat 월별 1회 계산·재사용(격자·재실행 가속)
    strat, bench = [], []
    prev_w = {}
    for i in range(idx0, len(panel)-1):
        month = panel.index[i].strftime("%Y-%m")
        fwd = panel.iloc[i+1] / panel.iloc[i] - 1.0
        if CFG["LONG_SHORT"]:
            # 후보 #6: 승자섹터 롱(+1) − 패자섹터 숏(−1), dollar-neutral. 오버레이 미적용(시장중립).
            longs, shorts = signal_at(i, ctx), short_at(i, ctx)
            w = {}
            for c in longs:  w[c] = w.get(c, 0) + 1.0/len(longs)
            for c in shorts: w[c] = w.get(c, 0) - 1.0/len(shorts)
            benchval = 0.0                                     # 자기금융 LS → 벤치 0
        else:
            w = weights(signal_at(i, ctx), panel, i)
            scale = overlay_scale(month, regime, vk, vk_thresh)
            w = {c: x*scale for c, x in w.items()}
            benchval = float(fwd.mean())                        # 유니버스 EW 벤치
        r = sum(w.get(c,0)*fwd.get(c,0) for c in w) if w else 0.0
        # 회전율 비용
        turn = sum(abs(w.get(c,0)-prev_w.get(c,0)) for c in set(w)|set(prev_w))
        r -= turn * CFG["COST_ONEWAY"]
        prev_w = w
        strat.append((panel.index[i+1], r))
        bench.append((panel.index[i+1], benchval))
    sr = pd.Series(dict(strat)); br = pd.Series(dict(bench))
    m = metrics(sr, br, factors)
    return sr, br, m

# ── 셀프테스트: 신호 배선만 점검(성과 주장 아님) ───────────────────────────────
def selftest():
    print("[selftest] 신호 배선 점검 (성과 아님)")
    ctx = load_signal_ctx(); panel = ctx[0]
    print(f"  · 패널 {panel.shape[0]}개월 × {panel.shape[1]}종목, 최신 {panel.index[-1].date()}")
    i = len(panel)-1
    codes = signal_at(i, ctx)
    print(f"  · 최신 상위 섹터 대장주 {len(codes)}종: {codes[:CFG['M_LEADERS']*CFG['K_SECTORS']]}")
    print(f"  · CONFIG: K={CFG['K_SECTORS']} M={CFG['M_LEADERS']} breadth≥{CFG['BREADTH_MIN']} "
          f"sizing={CFG['SIZING']} overlay={CFG['OVERLAY']} cost={CFG['COST_ONEWAY']}")
    print("  · 잔존알파 회귀 통제군:", list(load_factors().columns))
    print("[selftest] OK — 배선 정상. 성과 판정은 run_backtest()+DSR/PBO/White 연결 후.")

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--run", action="store_true", help="월간 백테 실행(골격·미검증)")
    ap.add_argument("--judge", action="store_true", help="격자 백테+DSR/PBO/White로 §7 기계판정")
    ap.add_argument("--ls", action="store_true", help="후보 #6: MG99식 산업 롱숏 모드로 판정")
    a = ap.parse_args()
    if a.ls: CFG["LONG_SHORT"] = True   # 롱숏 후보 #6
    if a.selftest: selftest()
    elif a.run:
        sr, br, m = run_backtest()
        print(json.dumps(m, ensure_ascii=False, indent=2))
        print("⚠️ 골격 결과 — 일봉정밀청산 미연결. 절대치 신뢰 금지.")
    elif a.judge:
        print(json.dumps(judge(), ensure_ascii=False, indent=2))
        print("⚠️ b회귀 통제군은 현재 WML — 등록 전 L1 정확 Mom12/Echo로 교체 필요. 일봉정밀청산 TODO.")
    else:
        print("사용: --selftest(배선) | --run(골격백테) | --judge(§7 기계판정)")
