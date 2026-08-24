# -*- coding: utf-8 -*-
"""
jq_rulesearch.py — **매도 규칙 자동 탐색 엔진 + 과최적화 검정**

진우 요청: "스스로 매매기법을 찾아내는 툴. 언제가 매도 시점인지 알아낼 수 있는 알고리즘."

⚠️⚠️ 이 툴의 진짜 목적을 오해하지 말 것:
    **규칙 384개를 뒤지면 "이기는 규칙"은 반드시 나온다.** 동전 384개를 던지면
    10연속 앞면인 동전이 나오는 것과 같다. 그건 실력이 아니라 운이다.
    → **이 툴의 가치는 "찾는 것"이 아니라 "찾은 게 운인지 실력인지 재는 것"이다.**
    → 정직한 결과의 대부분은 **"아무것도 없다"**이다. 그 답이 나오면 그게 정답이다.

──────────────────────────────────────────────────────────────
## 사전등록 (결과 보기 전 고정 — 실행 후 절대 수정 금지)

### 1) 탐색 대상 = **매도(청산) 규칙만**. 진입은 고정한다.
   진입(고정): 종가가 MA200 **상향 돌파** + 20일 거래대금 ≥ 30억 → **다음날 시가 매수**
   ↳ 진입까지 같이 뒤지면 탐색공간이 폭발해 오버핏이 확정된다. 진우가 물은 건 "매도 시점"이다.

### 2) 규칙 공간 (384개, 유한·고정)
   trail_k   ∈ {1.5, 2.0, 2.5, 3.0, 3.5, 4.0}   (트레일링 = 고점 − k×ATR14)
   stop_cap  ∈ {0.12, 0.15, 0.20, 0.25}          (초기손절 하한: 진입×(1−cap))
   time_stop ∈ {0(없음), 20, 40, 60}             (N일 후 ±5% 횡보면 청산)
   ma_exit   ∈ {0(없음), 20, 60, 120}            (종가 < MA(n) 이탈 시 청산)
   ※ 익절 목표는 **넣지 않는다** — 2026-07-13 sweep에서 단조 기각됨(일찍 자를수록 나쁨).

### 3) 데이터 분할 (홀드아웃은 단 1회만 본다)
   탐색 IS : 2019-01 ~ 2023-06   ← 384개 전부 여기서 돌린다
   검증 OOS: 2023-07 ~ 2026-07   ← **IS 우승자 1개만** 여기서 확인

### 4) 합격 게이트 — **4개 전부** 통과해야 채택
   ① OOS 평균R > 0  AND  **군집보정 t > 2.0** (거래는 시간에 뭉치므로 유효 N ≪ 거래수)
   ② **DSR** (Deflated Sharpe, n_trials=384) p < 0.05   ← 384번 뒤진 걸 벌점으로 깐다
   ③ **PBO** (CSCV 과최적화확률) < 0.5                  ← IS 우승자가 OOS 중앙값 아래일 확률
   ④ **이웃 강건성**: 우승 규칙의 파라미터 ±1칸 이웃의 IS 중앙값도 상위 25% 안
      ↳ **고립된 봉우리 = 오버핏. 넓은 고원 = 진짜일 수 있음.**
         (근거: 2026-07-13 익절 sweep은 완벽한 단조곡선이었다 = 진짜 효과의 지문.
          노이즈는 단조곡선을 못 만든다. 뾰족한 한 점만 좋으면 그건 노이즈다.)

### 5) 통과해도 끝이 아니다
   → 우승 규칙을 **jq_system_backtest.py에 넣어 buy&hold와 대결**시킨다.
     거기서 지면 "매도 규칙은 좋아졌지만 시스템은 여전히 시장에 진다" = 채택 안 함.
     (2026-07-13 확인: 청산은 R분포를 고치지만 **엣지를 만들지 않는다.** 엣지는 진입에 있어야 한다.)

실행: py jq_rulesearch.py --run          (전체 탐색, 3~8분)
      py jq_rulesearch.py --run --quick  (규칙 공간 축소 테스트용)
"""
# ── §8-3 비용 SSOT (2026-07-27) ─────────────────────────────────
# 코드베이스에 거래비용 상수가 7종 병존했다(0.235%~0.6%). 실측 왕복 0.559%로 통일한다.
# 종전 값은 각 대입문 주석에 남겼다. import 실패 시 종전 값으로 폴백한다.
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
    """SSOT 왕복비용. 못 불러오면 종전 값 유지."""
    return _jq_rt("기준") if _jq_rt else legacy
# ────────────────────────────────────────────────────────────────

import os, sys, json, math, argparse, warnings, importlib.util, itertools
import numpy as np, pandas as pd
warnings.simplefilter("ignore")
HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

# ── 사전등록 상수 (실행 후 수정 금지) ───────────────────────────
GRID = dict(
    trail_k   = [1.5, 2.0, 2.5, 3.0, 3.5, 4.0],
    stop_cap  = [0.12, 0.15, 0.20, 0.25],
    time_stop = [0, 20, 40, 60],
    ma_exit   = [0, 20, 60, 120],
)
GRID_QUICK = dict(trail_k=[2.0,2.5,3.0], stop_cap=[0.15,0.20], time_stop=[0,20], ma_exit=[0,60])

IS_END   = "2023-06-30"     # 탐색 구간 끝
OOS_START= "2023-07-01"     # 검증 구간 시작 (여기부터는 우승자만 본다)
MAXFWD   = 250              # 한 거래 최대 보유일(1년) — 그 이상은 강제청산
ATR_N    = 14
VOL_MIN  = 3e9
COST     = _jq_cost(0.0048)           # 왕복 비용(매수15bp+매도33bp)을 R 계산 시 반영  # §8-3: 종전 0.480% → 실측 0.559% (+0.079%p)
GATE     = dict(t_min=2.0, dsr_p=0.05, pbo_max=0.5, nbr_pct=0.25)

# ══════════════════════════════════════════════════════════════
#  진입 탐색 (--space entry) — 2026-07-13 추가
#  매도 탐색이 "매도 공간 전체가 마이너스 = 진입이 틀렸다"를 밝혔으므로,
#  같은 4중 게이트를 **진입 공간**에 겨눈다.
#
#  ⚠️ 여기가 진짜 위험지대다. 진입 공간은 넓고, 뒤지면 반드시 뭔가 나온다.
#     그래서 게이트를 그대로 쓰고, 규칙 공간을 **192개로 사전 고정**한다.
#
#  ### 사전등록 (실행 전 고정)
#  청산은 **고정**: 트레일링 2.5×ATR · 손절하한 20% · 목표가 없음 (매도규칙서 v2 현행)
#    ↳ 진입과 청산을 동시에 뒤지면 384×192=73,728 → 오버핏 확정. 하나씩만 움직인다.
#  진입 규칙 공간 (4×4×4×3 = 192):
#    trigger  ∈ {ma200돌파, 20일신고가, 52주신고가95%, 눌림목반등}
#    추세필터 ∈ {없음, 종가>MA60, 종가>MA120, 종가>MA200}
#    이격도상한∈ {없음, 1.2, 1.4, 1.8}          (과열 배제)
#    자금유입 ∈ {없음, v20/v60≥1.0, ≥1.5}       (거래대금 증가)
#  게이트는 매도 탐색과 **동일**(OOS t>2 · DSR>0.95 · PBO<0.5 · 이웃강건 · 퇴행가드)
# ══════════════════════════════════════════════════════════════
EXIT_FIXED = dict(trail_k=2.5, stop_cap=0.20, time_stop=0, ma_exit=0)
EGRID = dict(
    trigger  = ["ma200_cross", "hi20", "hi52_95", "pullback"],
    trend    = [0, 60, 120, 200],
    ext_max  = [0.0, 1.2, 1.4, 1.8],
    vol_min  = [0.0, 1.0, 1.5],
)
EGRID_QUICK = dict(trigger=["ma200_cross","hi20","hi52_95","pullback"], trend=[0,200],
                   ext_max=[0.0,1.4], vol_min=[0.0,1.5])

# ══════════════════════════════════════════════════════════════
#  보조지표 탐색 (--space indicator) — 2026-07-13 추가
#  진우 지적: "보조지표를 한 번도 스터디 안 했다." 맞다. 마지막 빈칸이다.
#
#  ⚠️⚠️ 사전 경고 (결과 보기 전에 기록한다):
#    이곳은 **세상에서 가장 많이 파헤쳐진 땅**이다.
#    Sullivan·Timmermann·White (1999, Journal of Finance)
#      "Data-Snooping, Technical Trading Rule Performance, and the Bootstrap"
#      — 기술적 매매규칙 **7,846개**를 다우지수에 적용, White's Reality Check로 보정했더니
#        **우승 규칙의 초과수익이 통계적으로 사라졌다.**
#    우리 5게이트(특히 ②DSR)가 정확히 그 보정이다.
#    → **예상 결과는 기각이다.** 그래도 확인은 해야 한다. 확인 안 한 빈칸은 미련이 남는다.
#
#  ### 사전등록 (216개)
#    trigger ∈ {RSI 과매도반등, MACD 시그널상향, 볼린저 하단반등, 볼린저 상단돌파,
#               스토캐스틱 상향교차, OBV 20일신고가}
#    추세필터∈ {없음, >MA60, >MA120, >MA200}
#    ADX필터 ∈ {없음, ADX>20, ADX>25}          (추세 강도)
#    RSI상한 ∈ {없음, RSI<70, RSI<80}          (과열 배제)
#  청산은 동일 고정(트레일링 2.5×ATR · 손절 20% · 목표없음). 게이트도 동일 5개.
# ══════════════════════════════════════════════════════════════
IGRID = dict(
    trigger  = ["rsi_os_rev", "macd_cross", "bb_lower_rev", "bb_upper_bo", "stoch_cross", "obv_hi"],
    trend    = [0, 60, 120, 200],
    adx_min  = [0, 20, 25],
    rsi_max  = [0, 70, 80],
)

def _wilder(x, n):
    return pd.Series(x).ewm(alpha=1.0/n, adjust=False).mean().values.astype(np.float32)

def _fixed_exit_R(o, h, c, atr, n):
    """고정 청산(트레일링 2.5ATR·손절하한 20%)으로 '모든 봉을 진입점으로 삼았을 때'의 R."""
    from numpy.lib.stride_tricks import sliding_window_view as swv
    k, cap = EXIT_FIXED["trail_k"], EXIT_FIXED["stop_cap"]; W = MAXFWD
    pad = lambda a: np.r_[a, np.full(W, np.nan, dtype=np.float32)]
    Hh = swv(pad(h), W)[:n]; Cc = swv(pad(c), W)[:n]; Oo = swv(pad(o), W)[:n]
    ent = np.r_[o[1:], np.nan].astype(np.float32)[:, None]; a0 = atr[:, None]
    with np.errstate(invalid="ignore"):
        stop0 = np.maximum(ent - k*a0, ent*(1.0-cap)); R1 = (ent - stop0).ravel()
        valid = np.isfinite(Cc)
        runmax = np.maximum(np.maximum.accumulate(np.where(valid, Hh, -np.inf), axis=1), ent)
        eff = np.maximum(stop0, runmax - k*a0)
        hitm = valid & (Cc < eff)
        hitm[np.arange(n), np.maximum(valid.sum(axis=1)-1, 0)] = True
        first = np.argmax(hitm, axis=1); nxt = np.minimum(first+1, W-1)
        px = Oo[np.arange(n), nxt]
        px = np.where(np.isfinite(px), px, Cc[np.arange(n), first])
        net = (px - ent.ravel()) - (ent.ravel()+px)*COST/2.0
        return np.divide(net, R1, out=np.full(n, np.nan, np.float32), where=R1 > 0)

def build_indicator_table(d):
    """보조지표 6종 계산 + 고정청산 R. 이후 216개 규칙은 이 표 위의 마스크."""
    rows = []; univ = []
    for code, g in d.groupby("code"):
        g = g.reset_index(drop=True); n = len(g)
        if n < 300: continue
        c = g["close"].values.astype(np.float32); h = g["high"].values.astype(np.float32)
        l = g["low"].values.astype(np.float32);  o = g["open"].values.astype(np.float32)
        v = g.get("volume", pd.Series(0., index=g.index)).values.astype(np.float32)
        pc = np.r_[np.nan, c[:-1]]
        tr = np.nanmax(np.vstack([h-l, np.abs(h-pc), np.abs(l-pc)]), axis=0)
        atr = pd.Series(tr).rolling(ATR_N).mean().values.astype(np.float32)
        v20 = pd.Series(c*v).rolling(20).mean().values.astype(np.float32)
        MA = lambda w: pd.Series(c).rolling(w).mean().values.astype(np.float32)
        ma60, ma120, ma200 = MA(60), MA(120), MA(200)

        # RSI(14) — Wilder
        dlt = np.r_[0., np.diff(c)]
        rsi = 100.0 - 100.0/(1.0 + _wilder(np.maximum(dlt,0),14)/np.maximum(_wilder(-np.minimum(dlt,0),14),1e-9))
        # MACD(12,26,9)
        E = lambda w: pd.Series(c).ewm(span=w, adjust=False).mean().values.astype(np.float32)
        macd = E(12) - E(26)
        sig = pd.Series(macd).ewm(span=9, adjust=False).mean().values.astype(np.float32)
        # 볼린저(20,2)
        m20 = MA(20); s20 = pd.Series(c).rolling(20).std(ddof=0).values.astype(np.float32)
        bbu = m20 + 2*s20; bbl = m20 - 2*s20
        # 스토캐스틱(14,3)
        ll = pd.Series(l).rolling(14).min().values.astype(np.float32)
        hh = pd.Series(h).rolling(14).max().values.astype(np.float32)
        with np.errstate(invalid="ignore", divide="ignore"):
            pk = 100.0*(c-ll)/np.maximum(hh-ll, 1e-9)
        pd_ = pd.Series(pk).rolling(3).mean().values.astype(np.float32)
        # OBV
        obv = np.cumsum(np.sign(np.r_[0., np.diff(c)])*v).astype(np.float32)
        obv_hi20 = pd.Series(obv).rolling(20).max().values.astype(np.float32)
        # ADX(14) — Wilder
        up = np.r_[0., np.diff(h)]; dn = np.r_[0., -np.diff(l)]
        pdm = np.where((up > dn) & (up > 0), up, 0.0); ndm = np.where((dn > up) & (dn > 0), dn, 0.0)
        atr_w = np.maximum(_wilder(tr,14), 1e-9)
        pdi = 100.0*_wilder(pdm,14)/atr_w; ndi = 100.0*_wilder(ndm,14)/atr_w
        dx = 100.0*np.abs(pdi-ndi)/np.maximum(pdi+ndi, 1e-9)
        adx = _wilder(dx, 14)

        R = _fixed_exit_R(o, h, c, atr, n)
        i = np.arange(n)
        ok = (i >= 250) & (i < n-2) & np.isfinite(atr) & (atr > 0) & np.isfinite(v20) & (v20 >= VOL_MIN) & np.isfinite(R)
        if ok.any():
            univ.append(pd.DataFrame(dict(date=g["date"].values[ok], R=R[ok].astype(np.float32))))
        P = lambda a: np.r_[np.nan, a[:-1]]      # 전일값
        t_rsi   = (P(rsi) < 30) & (rsi >= 30)                       # 과매도 반등
        t_macd  = (P(macd) <= P(sig)) & (macd > sig)                # 시그널 상향돌파
        t_bbl   = (P(c) <= P(bbl)) & (c > bbl)                      # 하단 반등
        t_bbu   = (P(c) <= P(bbu)) & (c > bbu)                      # 상단 돌파
        t_st    = (P(pk) <= P(pd_)) & (pk > pd_) & (pk < 50)        # 과매도권 상향교차
        t_obv   = np.isfinite(obv_hi20) & (obv >= obv_hi20)         # OBV 20일 신고가
        anyt = t_rsi | t_macd | t_bbl | t_bbu | t_st | t_obv
        sel = ok & anyt & np.isfinite(adx) & np.isfinite(rsi)
        if not sel.any(): continue
        rows.append(pd.DataFrame(dict(
            date=g["date"].values[sel], code=code, R=R[sel].astype(np.float32),
            rsi_os_rev=t_rsi[sel], macd_cross=t_macd[sel], bb_lower_rev=t_bbl[sel],
            bb_upper_bo=t_bbu[sel], stoch_cross=t_st[sel], obv_hi=t_obv[sel],
            gt60=(c > ma60)[sel], gt120=(c > ma120)[sel], gt200=(c > ma200)[sel],
            adx=adx[sel].astype(np.float32), rsi=rsi[sel].astype(np.float32))))
    if not rows: return None
    T = pd.concat(rows, ignore_index=True).sort_values("date").reset_index(drop=True)
    U = pd.concat(univ, ignore_index=True) if univ else None
    return T, U

def indicator_mask(T, r):
    m = T[r["trigger"]].values.copy()
    if r["trend"]:   m &= T[f"gt{r['trend']}"].values
    if r["adx_min"]: m &= (T["adx"].values >= r["adx_min"])
    if r["rsi_max"]: m &= (T["rsi"].values <= r["rsi_max"])
    return m

def build_entry_table(d):
    """모든 '후보 진입 봉'에 대해 (특징 + 고정청산 R)을 한 번에 계산.
       → 이후 192개 진입규칙은 이 표 위의 **단순 마스크**가 된다(매우 빠름)."""
    from numpy.lib.stride_tricks import sliding_window_view as swv
    k, cap = EXIT_FIXED["trail_k"], EXIT_FIXED["stop_cap"]
    rows = []; univ = []          # univ = 유동성만 통과한 '전 종목·전 봉' (랜덤 진입 대조군용)
    for code, g in d.groupby("code"):
        g = g.reset_index(drop=True); n = len(g)
        if n < 260 + MAXFWD//4: continue
        c = g["close"].values.astype(np.float32); h = g["high"].values.astype(np.float32)
        l = g["low"].values.astype(np.float32);  o = g["open"].values.astype(np.float32)
        pc = np.r_[np.nan, c[:-1]]
        tr = np.nanmax(np.vstack([h-l, np.abs(h-pc), np.abs(l-pc)]), axis=0)
        atr = pd.Series(tr).rolling(ATR_N).mean().values.astype(np.float32)
        S = lambda w: pd.Series(c).rolling(w).mean().values.astype(np.float32)
        ma60, ma120, ma200 = S(60), S(120), S(200)
        vv = (c*g.get("volume", pd.Series(0., index=g.index)).values).astype(np.float32)
        v20 = pd.Series(vv).rolling(20).mean().values.astype(np.float32)
        v60 = pd.Series(vv).rolling(60).mean().values.astype(np.float32)
        hi20 = pd.Series(c).rolling(20).max().values.astype(np.float32)
        hi52 = pd.Series(c).rolling(250, min_periods=100).max().values.astype(np.float32)

        # ── 고정 청산으로 '모든 봉을 진입점으로 삼았을 때'의 R을 벡터 계산
        W = MAXFWD
        pad = lambda a: np.r_[a, np.full(W, np.nan, dtype=np.float32)]
        Hh = swv(pad(h), W)[:n]; Cc = swv(pad(c), W)[:n]; Oo = swv(pad(o), W)[:n]
        ent = np.r_[o[1:], np.nan].astype(np.float32)[:, None]       # 다음날 시가 진입
        a0  = atr[:, None]
        with np.errstate(invalid="ignore"):
            stop0 = np.maximum(ent - k*a0, ent*(1.0-cap))
            R1 = (ent - stop0).ravel()
            valid = np.isfinite(Cc)
            runmax = np.maximum.accumulate(np.where(valid, Hh, -np.inf), axis=1)
            runmax = np.maximum(runmax, ent)
            eff = np.maximum(stop0, runmax - k*a0)
            hitm = valid & (Cc < eff)
            lastb = np.maximum(valid.sum(axis=1) - 1, 0)
            hitm[np.arange(n), lastb] = True
            first = np.argmax(hitm, axis=1)
            nxt = np.minimum(first+1, W-1)
            px = Oo[np.arange(n), nxt]
            px = np.where(np.isfinite(px), px, Cc[np.arange(n), first])
            net = (px - ent.ravel()) - (ent.ravel()+px)*COST/2.0
            R = np.divide(net, R1, out=np.full(n, np.nan, np.float32), where=R1 > 0)

        i = np.arange(n)
        ok = (i >= 250) & (i < n-2) & np.isfinite(atr) & (atr > 0) & np.isfinite(v20) & (v20 >= VOL_MIN) & np.isfinite(R)
        # 트리거 (적어도 하나 만족하는 봉만 남긴다 → 표 크기 축소)
        cross = np.r_[False, (c[:-1] <= ma200[:-1]) & (c[1:] > ma200[1:])]
        t_hi20 = c >= hi20
        t_hi52 = np.isfinite(hi52) & (c >= hi52*0.95)
        drop = np.isfinite(hi20) & (c <= hi20*0.92)
        t_pb = np.r_[False, (c[1:] > c[:-1])] & np.r_[False, drop[:-1]] & np.isfinite(ma60) & (c > ma60)
        anyt = cross | t_hi20 | t_hi52 | t_pb
        if ok.any():   # ★ 대조군: 신호와 무관하게 '아무 종목이나' 그날 샀을 때의 R
            univ.append(pd.DataFrame(dict(date=g["date"].values[ok], R=R[ok].astype(np.float32))))
        sel = ok & anyt & np.isfinite(ma200)
        if not sel.any(): continue
        with np.errstate(invalid="ignore", divide="ignore"):
            ext = c/ma200; vr = np.divide(v20, v60, out=np.ones(n, np.float32), where=np.isfinite(v60)&(v60>0))
        rows.append(pd.DataFrame(dict(
            date=g["date"].values[sel], code=code, R=R[sel].astype(np.float32),
            ma200_cross=cross[sel], hi20=t_hi20[sel], hi52_95=t_hi52[sel], pullback=t_pb[sel],
            gt60=(c > ma60)[sel], gt120=(c > ma120)[sel], gt200=(c > ma200)[sel],
            ext=ext[sel].astype(np.float32), vr=vr[sel].astype(np.float32))))
    if not rows: return None
    T = pd.concat(rows, ignore_index=True)
    U = pd.concat(univ, ignore_index=True) if univ else None      # 랜덤 대조군용 (전 종목·전 봉)
    return T.sort_values("date").reset_index(drop=True), U

def entry_mask(T, r):
    m = T[r["trigger"]].values.copy()
    if r["trend"]:   m &= T[f"gt{r['trend']}"].values
    if r["ext_max"]: m &= (T["ext"].values <= r["ext_max"])
    if r["vol_min"]: m &= (T["vr"].values >= r["vol_min"])
    return m

def run_entry(quick=False, space="entry"):
    st = load_stats(); d = load_daily()
    if d is None: return {"err": "일봉 CSV 없음"}
    IND = (space == "indicator")
    out = build_indicator_table(d) if IND else build_entry_table(d)
    if out is None: return {"err": "후보 부족"}
    T, U = out
    if len(T) < 500: return {"err": "후보 부족"}
    G = IGRID if IND else (EGRID_QUICK if quick else EGRID)
    KEYS = ("trigger","trend","adx_min","rsi_max") if IND else ("trigger","trend","ext_max","vol_min")
    MASK = indicator_mask if IND else entry_mask
    rules = [dict(_id=i, **dict(zip(KEYS, combo)))
             for i, combo in enumerate(itertools.product(*[G[k] for k in KEYS]))]
    N = len(rules)
    dates = pd.DatetimeIndex(T["date"]); Rall = T["R"].values.astype(float)
    is_m = np.asarray(dates <= pd.Timestamp(IS_END)); oos_m = np.asarray(dates >= pd.Timestamp(OOS_START))
    months = dates.to_period("M")

    rows = []; mats = {}
    for r in rules:
        m = MASK(T, r)
        R = Rall[m & is_m]
        if len(R) < 50: continue
        sd = R.std(ddof=1)
        rows.append(dict(_id=r["_id"], **{k: r[k] for k in KEYS},
                         n=len(R), meanR=float(R.mean()), sr=float(R.mean()/sd) if sd > 0 else 0.0,
                         winrate=float((R > 0).mean())))
        mm = m & (is_m | oos_m)
        mats[r["_id"]] = pd.Series(Rall[mm], index=months[mm]).groupby(level=0).mean()
    IS = pd.DataFrame(rows)
    if IS.empty: return {"err": "IS 평가 실패"}
    IS = IS.sort_values("sr", ascending=False).reset_index(drop=True)
    best = IS.iloc[0]
    br = {k: (best[k] if k == "trigger" else type(G[k][0])(best[k])) for k in KEYS}
    bm = MASK(T, br)

    R_is = Rall[bm & is_m]
    dsr_p, sr_obs, sr0 = st.deflated_sharpe_ratio(R_is, n_trials=N, sr_trials=IS["sr"].values)
    try:
        M = pd.DataFrame(mats).sort_index().fillna(0.0)
        pbo, _ = st.pbo_cscv(M.values, S=10) if M.shape[0] >= 20 else (float("nan"), None)
    except Exception: pbo = float("nan")

    def nbrs(row):
        out = []
        for key in KEYS:
            vals = G[key]; v = row[key]
            if v not in vals: continue
            p = vals.index(v)
            for p2 in (p-1, p+1):
                if 0 <= p2 < len(vals):
                    q = {kk: row[kk] for kk in KEYS}; q[key] = vals[p2]; out.append(q)
        return out
    cut = IS["sr"].quantile(1-GATE["nbr_pct"])
    nb_sr = []
    for q in nbrs(br):
        sub = IS
        for kk in KEYS: sub = sub[sub[kk] == q[kk]]
        if len(sub): nb_sr.append(float(sub["sr"].iloc[0]))
    nb_med = float(np.median(nb_sr)) if nb_sr else float("nan")

    R_oos = Rall[bm & oos_m]; d_oos = dates[bm & oos_m]
    t_oos = cluster_t(R_oos, d_oos); oos_mean = float(R_oos.mean()) if len(R_oos) else float("nan")

    # ── ⑤ 랜덤 진입 대조군 (★결정적) ─────────────────────────────
    #   "종목을 잘 골라서 번 것"인가, "그냥 좋은 날 시장에 있어서 번 것"인가?
    #   같은 날짜에 **아무 종목이나** 사서 같은 청산을 적용했을 때의 R과 비교한다.
    #   (계절틸트를 살렸던 '정적 동일노출 대조군'과 같은 논리)
    ctrl = {}; t_edge = {}
    if U is not None and len(U):
        ud = pd.DatetimeIndex(U["date"]); dm = U.groupby(ud)["R"].mean()   # 그날 전체 평균 R
        for tag, mm in (("IS", bm & is_m), ("OOS", bm & oos_m)):
            wd = dates[mm]
            if len(wd) == 0: continue
            w = pd.Series(1, index=wd).groupby(level=0).size()
            common = w.index.intersection(dm.index)
            if len(common) == 0: continue
            ctrl[tag] = float(np.average(dm.loc[common].values, weights=w.loc[common].values))
            # ★★ 초과수익(규칙 − 랜덤)의 **월별 시계열 t** — 베타가 상쇄되어 순수 선택력만 남는다.
            #    (원시 R의 t는 시장 변동이 노이즈로 들어가 검정력을 죽인다 = 설계 결함이었음)
            rr = pd.Series(Rall[mm], index=wd).groupby(pd.PeriodIndex(wd, freq="M")).mean()
            cc = dm.loc[common]; ww = w.loc[common]
            cm = (cc*ww).groupby(pd.PeriodIndex(cc.index, freq="M")).sum() / \
                 ww.groupby(pd.PeriodIndex(ww.index, freq="M")).sum()
            ex = (rr - cm).dropna()
            t_edge[tag] = (float(ex.mean()/(ex.std(ddof=1)/math.sqrt(len(ex))))
                           if len(ex) >= 6 and ex.std(ddof=1) > 0 else float("nan"))
    edge_is  = (float(best.meanR) - ctrl["IS"])  if "IS"  in ctrl else float("nan")
    edge_oos = (oos_mean          - ctrl["OOS"]) if "OOS" in ctrl else float("nan")
    te = t_edge.get("OOS", float("nan"))
    g5 = bool(np.isfinite(edge_oos) and edge_oos > 0 and np.isfinite(te) and te > GATE["t_min"])

    g1 = bool(oos_mean > 0 and np.isfinite(t_oos) and t_oos > GATE["t_min"])
    g2 = bool(dsr_p > 1-GATE["dsr_p"])
    g3 = bool(np.isfinite(pbo) and pbo < GATE["pbo_max"])
    g4 = bool(np.isfinite(nb_med) and nb_med >= cut)
    degenerate = bool(float(best.meanR) <= 0)
    passed = (not degenerate) and g1 and g2 and g3 and g4 and g5

    return {
        "탐색공간": ("보조지표 진입(RSI·MACD·볼린저·스토캐스틱·OBV·ADX / 청산 고정)" if IND
                     else "가격 진입(청산은 트레일링2.5·손절20% 고정)"),
        "⚠️사전경고": ("Sullivan-Timmermann-White(1999): 기술적 매매규칙 7,846개를 다중검정 보정하니 "
                       "우승자의 초과수익이 전부 사라졌다. ②DSR이 그 보정이다. 예상=기각." if IND else None),
        "탐색규칙수": N,
        "표본": {"후보봉": int(len(T)), "IS": int(is_m.sum()), "OOS": int(oos_m.sum())},
        "IS_전체분포": {"평균R_중앙값": round(float(IS.meanR.median()), 4),
                        "평균R_최고": round(float(IS.meanR.max()), 4),
                        "평균R_최저": round(float(IS.meanR.min()), 4),
                        "평균R_양수비율": round(float((IS.meanR > 0).mean()), 3),
                        "해설": "양수비율이 높으면 우승자는 그냥 분포의 꼬리다."},
        "IS_우승규칙": {**{k: (br[k].item() if hasattr(br[k], "item") else br[k]) for k in KEYS},
                        "IS_평균R": round(float(best.meanR), 4),
                        "IS_승률": round(float(best.winrate), 3), "IS_거래": int(best.n)},
        "게이트": {
            "①OOS_유의성": {"평균R": round(oos_mean, 4), "군집보정_t": round(float(t_oos), 2) if np.isfinite(t_oos) else None,
                            "거래수": int(len(R_oos)), "기준": f"평균R>0 & t>{GATE['t_min']}", "통과": g1},
            "②DSR_다중검정": {"관측SR": round(float(sr_obs), 3), "기대최대SR(운으로)": round(float(sr0), 3),
                              "DSR": round(float(dsr_p), 4), "기준": ">0.95", "통과": g2},
            "③PBO_과최적화": {"PBO": round(float(pbo), 3) if np.isfinite(pbo) else None, "기준": "<0.5", "통과": g3},
            "④이웃_강건성": {"이웃SR_중앙값": round(nb_med, 3) if np.isfinite(nb_med) else None,
                             "상위25%컷": round(float(cut), 3), "통과": g4},
            "⑤랜덤진입_대조군": {
                "규칙_OOS평균R": round(oos_mean, 4),
                "랜덤진입_OOS평균R": round(ctrl["OOS"], 4) if "OOS" in ctrl else None,
                "순수_종목선택력": round(edge_oos, 4) if np.isfinite(edge_oos) else None,
                "IS_순수선택력": round(edge_is, 4) if np.isfinite(edge_is) else None,
                "★초과수익_t_OOS": round(float(te), 2) if np.isfinite(te) else None,
                "★초과수익_t_IS": round(float(t_edge["IS"]), 2) if np.isfinite(t_edge.get("IS", np.nan)) else None,
                "기준": f"순수선택력 > 0 **AND** 초과수익 t > {GATE['t_min']}", "통과": g5,
                "해설": "★같은 날 **아무 종목이나** 사도 같은 R이 나온다면, 종목선택 실력이 아니라 '그날 시장에 있었던 것'(베타)이다. "
                        "초과수익(규칙−랜덤)의 t는 베타가 상쇄되므로 **순수 선택력의 유의성**을 잰다. "
                        "①의 t는 원시 R 기준이라 시장 변동이 노이즈로 들어간다 → ⑤의 t가 진짜 검정이다."},
        },
        "⚠️퇴행경고": ({"내용": "IS 최고 진입규칙조차 평균R ≤ 0 → 진입 공간 전체가 마이너스.",
                        "주의": "이때 PBO·이웃강건은 '통과'로 나와도 가짜다(고르게 나쁘면 순위도 안정)."} if degenerate else None),
        "VERDICT": "★채택후보 — 다음: jq_system_backtest로 buy&hold 대결" if passed
                   else ("기각 — 진입 공간 전체가 마이너스" if degenerate else "기각 — 운과 구분 불가"),
        "note": "통과해도 끝이 아니다. buy&hold(CAGR 21.8%)를 넘어야 실제 채택."
    }

def load_stats():
    s = importlib.util.spec_from_file_location("stats_v1", os.path.join(HERE, "stats_v1.py"))
    m = importlib.util.module_from_spec(s); s.loader.exec_module(m); return m

def load_daily():
    fs = []
    for f in ("kospi_pit_daily.csv", "kosdaq_pit_daily.csv"):
        p = os.path.join(HERE, f)
        if os.path.exists(p):
            d = pd.read_csv(p, dtype={"code": str}); d["date"] = pd.to_datetime(d["date"]); fs.append(d)
    if not fs: return None
    return pd.concat(fs, ignore_index=True).dropna(subset=["close","high","low"]).sort_values(["code","date"])

# ── 1) 진입 신호 + 각 거래의 '전방 경로' 행렬 구축 (한 번만) ──────
def build_paths(d):
    """MA200 상향돌파 진입. 각 진입마다 이후 MAXFWD일의 경로를 행렬로 쌓는다.
       → 이후 384개 규칙은 이 행렬 위에서 **벡터 연산**으로 평가된다(빠름)."""
    E = {k: [] for k in ("date","code","entry","atr0","o","h","c","ma20","ma60","ma120")}
    for code, g in d.groupby("code"):
        g = g.reset_index(drop=True)
        if len(g) < 260: continue
        pc = g["close"].shift(1)
        tr = pd.concat([g["high"]-g["low"], (g["high"]-pc).abs(), (g["low"]-pc).abs()], axis=1).max(axis=1)
        atr = tr.rolling(ATR_N).mean().values
        ma200 = g["close"].rolling(200).mean().values
        ma20  = g["close"].rolling(20).mean().values
        ma60  = g["close"].rolling(60).mean().values
        ma120 = g["close"].rolling(120).mean().values
        vol20 = (g["close"]*g.get("volume", pd.Series(0., index=g.index))).rolling(20).mean().values
        c = g["close"].values; h = g["high"].values; o = g["open"].values
        dt = g["date"].values
        # 상향돌파: 전일 종가 ≤ MA200, 당일 종가 > MA200
        for i in range(200, len(g)-2):
            if not (np.isfinite(ma200[i]) and np.isfinite(atr[i]) and atr[i] > 0): continue
            if not (np.isfinite(vol20[i]) and vol20[i] >= VOL_MIN): continue
            if not (c[i-1] <= ma200[i-1] and c[i] > ma200[i]): continue
            j = i+1                              # 다음날 시가 진입
            ent = o[j]
            if not (np.isfinite(ent) and ent > 0): continue
            sl = slice(j, min(j+MAXFWD, len(g)))
            L = sl.stop - sl.start
            def pad(a):
                v = np.full(MAXFWD, np.nan, dtype=np.float32); v[:L] = a[sl]; return v
            E["date"].append(dt[j]); E["code"].append(code)
            E["entry"].append(float(ent)); E["atr0"].append(float(atr[i]))
            E["o"].append(pad(o)); E["h"].append(pad(h)); E["c"].append(pad(c))
            E["ma20"].append(pad(ma20)); E["ma60"].append(pad(ma60)); E["ma120"].append(pad(ma120))
    if not E["code"]: return None
    P = dict(
        date=pd.to_datetime(np.array(E["date"])), code=np.array(E["code"]),
        entry=np.array(E["entry"], dtype=np.float32), atr0=np.array(E["atr0"], dtype=np.float32),
        o=np.vstack(E["o"]), h=np.vstack(E["h"]), c=np.vstack(E["c"]),
        ma20=np.vstack(E["ma20"]), ma60=np.vstack(E["ma60"]), ma120=np.vstack(E["ma120"]))
    return P

# ── 2) 규칙 1개를 전체 거래에 **벡터로** 적용 → R배수 배열 ────────
def eval_rule(P, k, cap, tstop, maexit, mask=None):
    ent = P["entry"]; atr0 = P["atr0"]
    idx = np.arange(len(ent)) if mask is None else np.where(mask)[0]
    if len(idx) == 0: return np.array([]), np.array([])
    e = ent[idx][:, None]; a = atr0[idx][:, None]
    H = P["h"][idx]; C = P["c"][idx]; O = P["o"][idx]
    valid = np.isfinite(C)

    stop0 = np.maximum(e - k*a, e*(1.0-cap))          # 초기 손절
    R1 = (e - stop0).ravel()                          # 1R (원 단위)
    Hf = np.where(valid, H, -np.inf)
    runmax = np.maximum.accumulate(np.maximum(Hf, e), axis=1)   # 진입 후 고점(래칫)
    trail = runmax - k*a
    eff = np.maximum(stop0, trail)                    # 실효 손절선

    hit = valid & (C < eff)                           # ① 트레일링/손절 이탈
    if maexit:                                        # ② 이평 이탈
        M = P[f"ma{maexit}"][idx]
        hit |= valid & np.isfinite(M) & (C < M)
    if tstop:                                         # ③ 시간 손절(횡보)
        bar = np.arange(C.shape[1])[None, :]
        hit |= valid & (bar >= tstop) & (np.abs(C/e - 1.0) <= 0.05)
    last = valid.sum(axis=1) - 1                      # 데이터 끝 = 강제청산
    hit[np.arange(len(idx)), np.maximum(last, 0)] = True

    first = np.argmax(hit, axis=1)                    # 첫 청산 시점
    nxt = np.minimum(first+1, C.shape[1]-1)           # 다음날 시가 청산
    px = O[np.arange(len(idx)), nxt]
    px = np.where(np.isfinite(px), px, C[np.arange(len(idx)), first])   # 시가 없으면 종가
    gross = px - e.ravel()
    net = gross - (e.ravel()+px)*COST/2.0             # 비용 차감
    R = np.divide(net, R1, out=np.zeros_like(net), where=R1 > 0)
    return R.astype(float), idx

def cluster_t(R, dates):
    """거래는 시간에 뭉친다 → 월 단위 군집보정 t (유효 N = 월 수)."""
    if len(R) < 10: return np.nan
    df = pd.DataFrame(dict(R=R, m=pd.to_datetime(dates).to_period("M")))
    g = df.groupby("m")["R"].mean()
    if len(g) < 6 or g.std(ddof=1) == 0: return np.nan
    return float(g.mean()/(g.std(ddof=1)/math.sqrt(len(g))))

def monthly_matrix(P, rules, mask):
    """PBO용: (월 × 규칙) 수익 행렬."""
    months = pd.DatetimeIndex(P["date"]).to_period("M")
    cols = {}
    for r in rules:
        R, idx = eval_rule(P, r["trail_k"], r["stop_cap"], r["time_stop"], r["ma_exit"], mask)
        if len(R) == 0: return None
        s = pd.Series(R, index=months[idx]).groupby(level=0).mean()
        cols[r["_id"]] = s
    M = pd.DataFrame(cols).sort_index().fillna(0.0)
    return M

def run(quick=False):
    st = load_stats()
    d = load_daily()
    if d is None: return {"err": "일봉 CSV 없음"}
    P = build_paths(d)
    if P is None: return {"err": "진입 신호 없음"}

    G = GRID_QUICK if quick else GRID
    rules = []
    for i, (k, cap, ts, me) in enumerate(itertools.product(G["trail_k"], G["stop_cap"], G["time_stop"], G["ma_exit"])):
        rules.append(dict(_id=i, trail_k=k, stop_cap=cap, time_stop=ts, ma_exit=me))
    N = len(rules)

    dates = pd.DatetimeIndex(P["date"])
    is_m  = np.asarray(dates <= pd.Timestamp(IS_END))
    oos_m = np.asarray(dates >= pd.Timestamp(OOS_START))
    if is_m.sum() < 200 or oos_m.sum() < 100:
        return {"err": f"표본 부족 (IS {int(is_m.sum())} / OOS {int(oos_m.sum())})"}

    # ── IS: 384개 전부 평가 (전체 분포를 기록한다. 우승자만 보고하지 않는다) ──
    rows = []
    for r in rules:
        R, idx = eval_rule(P, r["trail_k"], r["stop_cap"], r["time_stop"], r["ma_exit"], is_m)
        if len(R) < 50: continue
        sd = R.std(ddof=1)
        rows.append(dict(**{k: r[k] for k in ("_id","trail_k","stop_cap","time_stop","ma_exit")},
                         n=len(R), meanR=float(R.mean()), sr=float(R.mean()/sd) if sd > 0 else 0.0,
                         winrate=float((R > 0).mean())))
    IS = pd.DataFrame(rows)
    if IS.empty: return {"err": "IS 평가 실패"}
    IS = IS.sort_values("sr", ascending=False).reset_index(drop=True)
    best = IS.iloc[0]

    # ── ② DSR: 384번 뒤진 것을 벌점으로 깐다 ──
    Rb_is, _ = eval_rule(P, best.trail_k, best.stop_cap, int(best.time_stop), int(best.ma_exit), is_m)
    dsr_p, sr_obs, sr0 = st.deflated_sharpe_ratio(Rb_is, n_trials=N, sr_trials=IS["sr"].values)

    # ── ③ PBO (CSCV) ──
    try:
        M = monthly_matrix(P, rules, is_m | oos_m)
        pbo, _ = st.pbo_cscv(M.values, S=10) if M is not None and M.shape[0] >= 20 else (np.nan, None)
    except Exception as e:
        pbo = float("nan")

    # ── ④ 이웃 강건성: 우승 규칙 ±1칸 이웃이 IS 상위 25%에 드나 ──
    def nbrs(row):
        out = []
        for key in ("trail_k","stop_cap","time_stop","ma_exit"):
            vals = G[key]; v = row[key]
            pos = vals.index(v) if v in vals else None
            if pos is None: continue
            for p2 in (pos-1, pos+1):
                if 0 <= p2 < len(vals):
                    q = {kk: row[kk] for kk in ("trail_k","stop_cap","time_stop","ma_exit")}
                    q[key] = vals[p2]; out.append(q)
        return out
    cut = IS["sr"].quantile(1-GATE["nbr_pct"])
    nb = nbrs(best)
    nb_sr = [float(IS[(IS.trail_k==q["trail_k"])&(IS.stop_cap==q["stop_cap"])&
                      (IS.time_stop==q["time_stop"])&(IS.ma_exit==q["ma_exit"])]["sr"].iloc[0])
             for q in nb if len(IS[(IS.trail_k==q["trail_k"])&(IS.stop_cap==q["stop_cap"])&
                                   (IS.time_stop==q["time_stop"])&(IS.ma_exit==q["ma_exit"])])]
    nb_med = float(np.median(nb_sr)) if nb_sr else float("nan")
    nbr_ok = bool(np.isfinite(nb_med) and nb_med >= cut)

    # ── ① OOS: 우승자 **단 1회** 검증 ──
    Rb_oos, oidx = eval_rule(P, best.trail_k, best.stop_cap, int(best.time_stop), int(best.ma_exit), oos_m)
    t_oos = cluster_t(Rb_oos, dates[oidx])
    oos_mean = float(Rb_oos.mean()) if len(Rb_oos) else float("nan")

    g1 = bool(oos_mean > 0 and np.isfinite(t_oos) and t_oos > GATE["t_min"])
    g2 = bool(dsr_p > 1-GATE["dsr_p"])         # DSR = P(SR > 기대최대SR). 0.95↑면 유의
    g3 = bool(np.isfinite(pbo) and pbo < GATE["pbo_max"])
    g4 = nbr_ok
    # ⚠️ 퇴행(degenerate) 가드 — 2026-07-13 추가
    #   PBO·이웃강건성은 '규칙들 사이의 순위 안정성'을 잰다.
    #   **전부 똑같이 나쁘면 순위도 안정적**이므로 둘 다 가짜 통과가 나온다("물에 잠긴 고원").
    #   → IS 최고조차 평균R ≤ 0이면 나머지 게이트는 의미가 없다. 즉시 기각.
    degenerate = bool(float(best.meanR) <= 0)
    passed = (not degenerate) and g1 and g2 and g3 and g4

    res = {
        "탐색규칙수": N,
        "표본": {"IS_거래": int(is_m.sum()), "OOS_거래": int(oos_m.sum()),
                 "IS구간": f"~{IS_END}", "OOS구간": f"{OOS_START}~"},
        "IS_전체분포": {   # ★ 우승자만 보면 속는다. 분포를 본다.
            "평균R_중앙값": round(float(IS.meanR.median()), 4),
            "평균R_최고":   round(float(IS.meanR.max()), 4),
            "평균R_최저":   round(float(IS.meanR.min()), 4),
            "평균R_양수비율": round(float((IS.meanR > 0).mean()), 3),
            "해설": "양수비율이 높으면 '우승자'는 그냥 분포의 꼬리일 뿐이다."
        },
        "IS_우승규칙": {"트레일링_ATR배수": float(best.trail_k), "손절하한": float(best.stop_cap),
                        "시간손절일": int(best.time_stop), "이평이탈": int(best.ma_exit),
                        "IS_평균R": round(float(best.meanR), 4), "IS_승률": round(float(best.winrate), 3),
                        "IS_거래": int(best.n)},
        "게이트": {
            "①OOS_유의성": {"평균R": round(oos_mean, 4),
                            "군집보정_t": round(float(t_oos), 2) if np.isfinite(t_oos) else None,
                            "기준": f"평균R>0 & t>{GATE['t_min']}", "통과": g1},
            "②DSR_다중검정": {"관측SR": round(float(sr_obs), 3), "기대최대SR(운으로)": round(float(sr0), 3),
                              "DSR": round(float(dsr_p), 4), "기준": "DSR>0.95", "통과": g2,
                              "해설": "384번 뒤지면 운만으로도 SR이 이만큼 나온다. 그걸 넘어야 진짜."},
            "③PBO_과최적화": {"PBO": round(float(pbo), 3) if np.isfinite(pbo) else None,
                              "기준": "<0.5", "통과": g3,
                              "해설": "IS 우승자가 OOS에선 중앙값 아래로 떨어질 확률."},
            "④이웃_강건성": {"이웃SR_중앙값": round(nb_med, 3) if np.isfinite(nb_med) else None,
                             "상위25%_컷": round(float(cut), 3), "통과": g4,
                             "해설": "고립된 봉우리=오버핏. 넓은 고원=진짜일 수 있음."},
        },
        "⚠️퇴행경고": ({"내용": "IS 최고 규칙조차 평균R ≤ 0 → **매도 공간 전체가 물에 잠겨 있다.**",
                        "함의": "매도를 어떻게 바꿔도 소용없다. **진입이 틀렸다.**",
                        "주의": "이 경우 PBO·이웃강건성이 '통과'로 나와도 **가짜다** — 전부 고르게 나쁘면 순위도 안정적이기 때문(물에 잠긴 고원)."}
                       if degenerate else None),
        "VERDICT": "채택후보 — 다음 단계: jq_system_backtest로 buy&hold 대결" if passed
                   else ("기각 — 매도 공간 전체가 마이너스(진입 결함). 매도 튜닝 무의미." if degenerate
                         else "기각 — 통계적으로 운과 구분 불가"),
        "note": "청산 규칙은 R분포를 고치지만 엣지를 만들지 않는다(2026-07-13). 통과해도 buy&hold 대결이 남는다."
    }
    return res

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--run", action="store_true")
    ap.add_argument("--quick", action="store_true")
    ap.add_argument("--space", default="exit", choices=["exit","entry","indicator"],
                    help="exit=매도384 · entry=가격진입192 · indicator=보조지표216(RSI/MACD/볼린저/스토캐스틱/OBV/ADX)")
    a = ap.parse_args()
    if a.run:
        r = run(a.quick) if a.space == "exit" else run_entry(a.quick, a.space)
        print(json.dumps(r, ensure_ascii=False, indent=2))
    else: print(__doc__)
