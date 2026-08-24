# -*- coding: utf-8 -*-
"""
jq_paper_core.py — 진우퀀트 페이퍼트레이딩 **공용 코어** (규칙의 단일 출처)

★ 이 파일이 전략의 전부다 (Single Source of Truth) ★
  가상매매_엔진.py (실전 페이퍼) 와 가상매매_백테스트.py (과거 검증) 는
  둘 다 이 파일을 import 한다. 규칙을 두 번 구현하지 않는다.
  실전과 백테스트가 다르게 동작하면 백테스트는 의미가 없다.

★ 절대 원칙 ★
  · 실재 데이터만. 추정·보간·합성 금지. 실패 시 '데이터부족' 명시 후 제외.
  · 투자자문 아님. 지표·규칙 사실만 기록. 결정·책임은 본인.

구성:
  1) CFG            — 모든 파라미터 (근거는 가상매매_설계.md 파라미터 근거표)
  2) 지표           — atr_wilder / ma_and_slope (+ 벡터화 쌍둥이, 셀프테스트로 동치 검증)
  3) 규칙 순수함수  — passes_L / passes_S / check_exit_core / size_position
  4) PriceStore     — 실데이터 공급 (local 패널 / pykrx)
  5) 매크로 게이트  — regime + VKOSPI (+ 할로윈 오버레이)
  6) 커플링         — 한·미 1일 lag 상관 (★기록 전용. 규칙 미반영★)
  7) 국면(Phase)    — 인과적 룰 기반 4축 (t 이전 데이터만 사용)
"""
import os, sys, math, datetime as dt

import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# ═══════════════════════════════════════════════════════════════════════════
# 경로 — 산출물은 전부 진우퀀트\가상매매\ 아래. 진우퀀트 루트는 읽기만 한다.
#   ROOT(진우퀀트)\           ← 원본 데이터 (읽기 전용. 절대 쓰지 않는다)
#   ROOT\가상매매\엔진\       ← 이 파일
#            \원장\ \백테스트\ \검증\ \문서\ \실행이력\
# ═══════════════════════════════════════════════════════════════════════════
HERE = os.path.dirname(os.path.abspath(__file__))      # ...\가상매매\엔진
PKG = os.path.dirname(HERE)                            # ...\가상매매
ROOT = os.path.dirname(PKG)                            # ...\진우퀀트  (원본 데이터)

DIR_LEDGER = os.path.join(PKG, "원장")
DIR_BT = os.path.join(PKG, "백테스트")
DIR_VERIFY = os.path.join(PKG, "검증")
DIR_DOC = os.path.join(PKG, "문서")
DIR_LOG = os.path.join(PKG, "실행이력")
for _d in (DIR_LEDGER, DIR_BT, DIR_VERIFY, DIR_DOC, DIR_LOG):
    os.makedirs(_d, exist_ok=True)

BASE = ROOT   # 원본 데이터 디렉터리 (read_csv 기본)


# ═══════════════════════════════════════════════════════════════════════════
# 1) 설정
# ═══════════════════════════════════════════════════════════════════════════
CFG = dict(
    INITIAL_CAPITAL=10_000_000,
    TRACK_ALLOC={"L": 0.70, "S": 0.30},

    RISK_PCT=0.02,        # 트랙 자본의 2%를 1회 손절에 건다
    MAX_POS_PCT=0.10,     # 단일 종목 ≤ 트랙 자본의 10%
    HARD_STOP_PCT=0.20,   # 손절 하한: 진입가 × 0.80

    L=dict(MA_WEEK=20, SLOPE_WEEKS=4, ATR_STOP=2.5, ATR_TRAIL=2.5,
           TIME_STOP_DAYS=20, TIME_STOP_BAND=0.05, MAX_POSITIONS=7),
    S=dict(MA_SHORT=20, SLOPE_DAYS=5, ATR_STOP=1.5, ATR_TRAIL=1.5,
           TIME_STOP_DAYS=10, TIME_STOP_BAND=0.03, MAX_POSITIONS=5,
           REQUIRE_HTF=True),

    ATR_N=14,
    UNIVERSE_TOP_N=120,    # 코스피 시총 상위 N
    KOSDAQ_TOP_N=40,       # 코스닥 시총 상위 N (테마연동 실패 시)
    THEME_TOP_N=4,         # theme_heat 상위 N개 테마
    THEME_MIN_MEMBERS=5,   # 테마 유니버스 최소 종목수 (미만이면 테마연동 미적용)
    MIN_BARS=140,
    BARS_WINDOW=400,

    HALF_TP=False,        # +1R 절반익절 — 매도규칙서 v2가 삭제한 규칙 (기본 OFF)
    HALLOWEEN=False,      # 여름 노출 ×0.5 (기본 OFF — 할로윈_검증결과.md)
    HALLOWEEN_SUMMER_W=0.5,

    REGIME_EXPOSURE={"광범위 상승": 1.00, "쏠림(테마)": 0.80, "약세": 0.50},
    VKOSPI_HIGH=30.0,
    VKOSPI_EXTREME=40.0,
    STALE_DAYS=10,

    # 커플링 임계값 (고정 — 임의 해석 금지)
    COUPLING={"STRONG": 0.6, "COUPLED": 0.3, "INVERSE": -0.3},

    # 국면 임계값 (고정 · 인과적)
    PHASE=dict(MA_LONG=200, VOL_WIN=20, VOL_QUANTILE_YEARS=3,
               VOL_LO=0.33, VOL_HI=0.67,
               DD_CORRECTION=0.05, DD_BEAR=0.20),

    # 거래비용 (백테스트) — 파라미터화
    COST=dict(BUY_FEE=0.00015, SELL_FEE=0.00015, TAX=0.0015, SLIPPAGE=0.001),
)

LEDGER_COLS = ["date", "track", "code", "name", "action", "price", "qty", "amount",
               "reason", "rule_fired", "score", "atr", "r_multiple", "realized_pnl"]
POS_COLS = ["track", "code", "name", "entry_date", "entry_price", "qty", "stop",
            "target_1r", "high_watermark", "days_held", "unrealized_pnl",
            "init_stop", "atr", "half_sold"]
EQ_COLS = ["date", "track", "cash", "position_value", "total_equity",
           "exposure_pct", "regime", "coupling_state", "data_source"]
SIG_COLS = ["date", "track", "code", "name", "market", "close", "atr",
            "f_bars", "f_ma_week", "f_slope_week", "f_ma_short", "f_slope_short",
            "f_htf_align", "passed", "score", "reject_reason"]
COUP_COLS = ["date", "corr_20d_spx", "corr_60d_spx", "corr_20d_nasdaq", "corr_20d_sox",
             "corr_20d_kosdaq_vs_spx", "corr_kospi_kosdaq_20d", "beta_20d_spx",
             "state", "state_change", "spx_ret_prev", "kospi_ret", "source"]


# ═══════════════════════════════════════════════════════════════════════════
# 포맷 / IO
# ═══════════════════════════════════════════════════════════════════════════
def fmt_won(x):
    """천단위 콤마 — Python %-포맷 금지, format() 사용."""
    try:
        v = float(x)
        return "데이터부족" if math.isnan(v) else format(v, ",.0f")
    except Exception:
        return "데이터부족"


def fmt_pct(x, dec=2):
    if x is None or (isinstance(x, float) and (math.isnan(x) or math.isinf(x))):
        return "데이터부족"
    return f"{x*100:+.{dec}f}%"


def read_csv(name, where=None, **kw):
    """원본 데이터는 진우퀀트 루트(ROOT)에서 읽는다. where로 다른 폴더 지정 가능."""
    p = os.path.join(where or BASE, name)
    if not os.path.exists(p):
        return None
    try:
        return pd.read_csv(p, encoding="utf-8-sig", **kw)
    except Exception:
        return None


def out_path(dirname, fname):
    return os.path.join(dirname, fname)


def append_csv(dirname, fname, rows, cols):
    """산출물 append (헤더 자동)."""
    if not rows:
        return
    p = os.path.join(dirname, fname)
    ex = os.path.exists(p)
    pd.DataFrame(rows, columns=cols).to_csv(
        p, mode="a" if ex else "w", header=not ex, index=False, encoding="utf-8-sig")


def write_csv(dirname, fname, rows, cols):
    pd.DataFrame(rows, columns=cols).to_csv(
        os.path.join(dirname, fname), index=False, encoding="utf-8-sig")


def isnan(v):
    return v is None or (isinstance(v, float) and (math.isnan(v) or math.isinf(v)))


# ═══════════════════════════════════════════════════════════════════════════
# 실행 이력 로그 — 매 실행마다 새 파일. 절대 덮어쓰지 않는다.
#   "그때 왜 그렇게 판단했나"를 되짚는 근거.
# ═══════════════════════════════════════════════════════════════════════════
class RunLogger:
    """stdout을 화면과 로그파일에 동시 출력(tee). 재현 정보·예외 전문 기록."""

    def __init__(self, script, params=None):
        ts = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
        self.path = os.path.join(DIR_LOG, f"run_{ts}.log")
        self.f = open(self.path, "w", encoding="utf-8")
        self._stdout = sys.stdout
        sys.stdout = self
        self.write_header(script, params or {})

    def write(self, s):
        self._stdout.write(s)
        try:
            self.f.write(s)
        except Exception:
            pass

    def flush(self):
        self._stdout.flush()
        try:
            self.f.flush()
        except Exception:
            pass

    def write_header(self, script, params):
        print("#" * 78)
        print(f"# 실행 이력  {dt.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"# 스크립트 : {script}")
        print(f"# 로그파일 : {os.path.basename(self.path)}")
        print("#" + "-" * 77)
        print("# 파라미터 (재현용)")
        for k, v in params.items():
            print(f"#   {k} = {v}")
        print("# 핵심 CFG")
        for k in ("INITIAL_CAPITAL", "TRACK_ALLOC", "RISK_PCT", "MAX_POS_PCT",
                  "HARD_STOP_PCT", "L", "S", "ATR_N", "HALF_TP", "HALLOWEEN"):
            print(f"#   {k} = {CFG[k]}")
        print("# 라이브러리 버전 (결과 차이 원인추적용)")
        for mod in ("pandas", "numpy", "pykrx", "yfinance", "matplotlib", "scipy"):
            try:
                m = __import__(mod)
                print(f"#   {mod} = {getattr(m, '__version__', '?')}")
            except Exception:
                print(f"#   {mod} = 미설치")
        print(f"#   python = {sys.version.split()[0]}")
        print("#" * 78)

    def close(self, err=None):
        if err:
            import traceback
            print("\n" + "!" * 78)
            print("[예외 발생] 전문:")
            print("".join(traceback.format_exception(type(err), err, err.__traceback__)))
            print("!" * 78)
        print(f"\n[로그 저장] 실행이력\\{os.path.basename(self.path)}")
        sys.stdout = self._stdout
        try:
            self.f.close()
        except Exception:
            pass


# ═══════════════════════════════════════════════════════════════════════════
# 2) 지표 — 봉 부족 시 NaN (추정 금지)
# ═══════════════════════════════════════════════════════════════════════════
def atr_wilder(high, low, close, n=14):
    h, l, c = (pd.Series(x).astype(float).reset_index(drop=True) for x in (high, low, close))
    if len(c) < n + 1:
        return float("nan")
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    a = tr.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean().iloc[-1]
    return float(a) if pd.notna(a) and a > 0 else float("nan")


def atr_series(high, low, close, n=14):
    """벡터화 ATR — 백테스트용. atr_wilder와 수식 동일(셀프테스트로 동치 검증)."""
    h, l, c = (pd.Series(x).astype(float).reset_index(drop=True) for x in (high, low, close))
    pc = c.shift(1)
    tr = pd.concat([h - l, (h - pc).abs(), (l - pc).abs()], axis=1).max(axis=1)
    a = tr.ewm(alpha=1.0 / n, adjust=False, min_periods=n).mean()
    return a.where(a > 0)


def ma_and_slope(series, window, lookback):
    """(MA, 기울기=(MA[t]-MA[t-lb])/MA[t-lb]). 부족 시 (nan, nan)."""
    s = pd.Series(series).astype(float).dropna().reset_index(drop=True)
    if len(s) < window + lookback:
        return float("nan"), float("nan")
    ma = s.rolling(window).mean()
    cur, prev = ma.iloc[-1], ma.iloc[-1 - lookback]
    if pd.isna(cur) or pd.isna(prev) or prev <= 0:
        return float("nan"), float("nan")
    return float(cur), float((cur - prev) / prev)


def ma_slope_series(series, window, lookback):
    """벡터화 (MA, slope) — 백테스트용."""
    s = pd.Series(series).astype(float).reset_index(drop=True)
    ma = s.rolling(window).mean()
    prev = ma.shift(lookback)
    return ma, (ma - prev) / prev.where(prev > 0)


def to_weekly(dates, closes):
    s = pd.Series(np.asarray(closes, dtype=float),
                  index=pd.DatetimeIndex(pd.to_datetime(dates)))
    return s.resample("W-FRI").last().dropna()


def weekly_ma_slope_daily(dates, closes, ma_week, slope_weeks):
    """
    ★ look-ahead 차단 ★ 일별로 '그 날까지 확정된 주봉'만 써서 (MA20W, slope) 시계열 생성.
    주중에는 직전 완성 주봉까지만 사용 (미완성 주봉 사용 금지).
    반환 (Series ma_w, Series slope_w) — 입력 일봉 인덱스와 동일 길이.
    """
    idx = pd.DatetimeIndex(pd.to_datetime(dates))
    s = pd.Series(np.asarray(closes, dtype=float), index=idx)
    wk = s.resample("W-FRI").last().dropna()
    ma = wk.rolling(ma_week).mean()
    prev = ma.shift(slope_weeks)
    slope = (ma - prev) / prev.where(prev > 0)
    # 각 주봉 값은 그 주 금요일 종가로 확정 → 그 시점 이후에만 사용 가능.
    # asof 방식으로 일별에 매핑 (해당 일자 이전에 확정된 마지막 주봉).
    ma_d = ma.reindex(ma.index.union(idx)).ffill().reindex(idx)
    sl_d = slope.reindex(slope.index.union(idx)).ffill().reindex(idx)
    return ma_d, sl_d


# ═══════════════════════════════════════════════════════════════════════════
# 3) ★ 규칙 — 순수함수. 이 4개가 전략의 전부. 엔진·백테스트가 동일하게 호출. ★
# ═══════════════════════════════════════════════════════════════════════════
def passes_L(close, ma_w, slope_w):
    """Track L 진입. 반환 (통과, 사유, 점수=20주선 기울기%)."""
    if isnan(close) or isnan(ma_w) or isnan(slope_w):
        return False, "데이터부족(주봉 20주선)", float("nan")
    sc = round(slope_w * 100, 3)
    if close <= ma_w:
        return False, "20주선 아래", sc
    if slope_w <= 0:
        return False, "20주선 기울기 하락", sc
    return True, "", sc


def passes_S(close, ma_s, slope_s, above_week, require_htf=True):
    """Track S 진입. 상위 프레임 역행 진입 금지. 반환 (통과, 사유, 점수=20일선 기울기%)."""
    if isnan(close) or isnan(ma_s) or isnan(slope_s):
        return False, "데이터부족(20일선)", float("nan")
    sc = round(slope_s * 100, 3)
    if require_htf:
        if above_week is None or (isinstance(above_week, float) and math.isnan(above_week)):
            return False, "데이터부족(상위 프레임)", sc
        if not above_week:
            return False, "상위추세 역행(20주선 아래) — 진입금지", sc
    if close <= ma_s:
        return False, "20일선 아래", sc
    if slope_s <= 0:
        return False, "20일선 기울기 하락", sc
    return True, "", sc


def check_exit_core(pos, close, atr, ma_short, cfg_t, track, half_tp=None):
    """
    ★ 청산 규칙 단일 구현 ★ (매도규칙서 v2 준수)
    우선순위: 손절 > 20일선이탈(S) > 트레일링 > 시간손절 > 절반익절(옵션)
    부작용: pos['stop'] = 실효손절(래칫).
    반환 (action, reason, rule_fired, sell_qty) | None(=유지/판정보류)
    """
    if half_tp is None:
        half_tp = CFG["HALF_TP"]
    if isnan(atr) or atr <= 0 or isnan(close):
        return None   # 데이터부족 → 임의 청산 금지

    # 트레일링 래칫: 실효손절 = max(초기손절, 고점 − k×ATR). 한 번 오르면 안 내려감.
    eff_stop = max(pos["init_stop"], pos["high_watermark"] - cfg_t["ATR_TRAIL"] * atr)
    pos["stop"] = eff_stop
    r_unit = pos["entry_price"] - pos["init_stop"]

    if close <= pos["init_stop"]:
        return ("SELL_STOP",
                f"손절: 종가 {fmt_won(close)} <= 초기손절 {fmt_won(pos['init_stop'])}",
                f"진입가-{cfg_t['ATR_STOP']}ATR 또는 -{int(CFG['HARD_STOP_PCT']*100)}% 하한",
                pos["qty"])

    if track == "S" and not isnan(ma_short) and close < ma_short:
        return ("SELL_MA",
                f"20일선 이탈: 종가 {fmt_won(close)} < MA{cfg_t['MA_SHORT']} {fmt_won(ma_short)}",
                f"Track S MA{cfg_t['MA_SHORT']} 종가 이탈", pos["qty"])

    if close <= eff_stop:
        return ("SELL_TRAIL",
                f"트레일링: 종가 {fmt_won(close)} <= 실효손절 {fmt_won(eff_stop)} "
                f"(고점 {fmt_won(pos['high_watermark'])} - {cfg_t['ATR_TRAIL']}ATR)",
                f"고점-{cfg_t['ATR_TRAIL']}ATR 래칫", pos["qty"])

    if pos.get("days_held", 0) >= cfg_t["TIME_STOP_DAYS"]:
        chg = (close - pos["entry_price"]) / pos["entry_price"]
        if abs(chg) <= cfg_t["TIME_STOP_BAND"]:
            return ("SELL_TIME",
                    f"시간손절: {pos['days_held']}일 보유, 변동 {fmt_pct(chg)} "
                    f"(+-{cfg_t['TIME_STOP_BAND']*100:.0f}% 이내 횡보)",
                    f"{cfg_t['TIME_STOP_DAYS']}일 횡보", pos["qty"])

    # +1R 절반익절 — 기본 OFF (매도규칙서 v2가 삭제)
    if half_tp and not pos.get("half_sold", 0) and r_unit > 0:
        if close >= pos["entry_price"] + r_unit:
            half = pos["qty"] // 2
            if half > 0:
                return ("SELL_TP",
                        f"+1R 절반익절: 종가 {fmt_won(close)} >= 1R목표 {fmt_won(pos['target_1r'])}",
                        "+1R 절반매도(--half-tp)", half)
    return None


def size_position(track_equity, price, atr, atr_mult, exposure=1.0):
    """
    ★ 사이징 단일 구현 ★ 2%룰 ÷ (atr_mult × ATR).
    반환 (qty, stop, risk_per_share, cap_reason). 데이터부족 → (0, nan, nan, '데이터부족')
    """
    if isnan(price) or price <= 0 or isnan(atr) or atr <= 0:
        return 0, float("nan"), float("nan"), "데이터부족"
    stop = max(price - atr_mult * atr, price * (1 - CFG["HARD_STOP_PCT"]))
    risk_ps = price - stop
    if risk_ps <= 0:
        return 0, float("nan"), float("nan"), "데이터부족(손절폭<=0)"
    qty = int((track_equity * CFG["RISK_PCT"] * exposure) // risk_ps)
    cap_reason = "risk2%"
    cap_amt = track_equity * CFG["MAX_POS_PCT"]
    if qty * price > cap_amt:
        qty = int(cap_amt // price)
        cap_reason = f"종목상한{int(CFG['MAX_POS_PCT']*100)}%"
    if qty <= 0:
        return 0, stop, risk_ps, "자본부족"
    return qty, stop, risk_ps, cap_reason


# ═══════════════════════════════════════════════════════════════════════════
# 4) 데이터 계층
# ═══════════════════════════════════════════════════════════════════════════
class PriceStore:
    """실데이터 공급자. local(오프라인 패널) / pykrx(라이브). 없는 데이터는 만들지 않는다."""

    def __init__(self, source="auto", quiet=False):
        self.source, self.quiet = source, quiet
        self.used = None
        self.panels, self.by_code, self.names = {}, {}, {}
        self.mcap = {}
        self.notes = []
        self.busday, self._stock = None, None
        self._month_first = None
        self._codes = {}

    def _load_panel(self, fname, market):
        d = read_csv(fname, dtype={"code": str})
        if d is None:
            self.notes.append(f"[데이터부족] {fname} 없음 -> {market} 제외")
            return None
        if not {"code", "date", "high", "low", "close"} <= set(d.columns):
            self.notes.append(f"[데이터부족] {fname} 컬럼 부족 -> {market} 제외")
            return None
        d["date"] = pd.to_datetime(d["date"], errors="coerce")
        for c in ("open", "high", "low", "close", "volume"):
            if c in d.columns:
                d[c] = pd.to_numeric(d[c], errors="coerce")
        if "open" not in d.columns:
            self.notes.append(f"  [주의] {fname}에 open 없음 -> 익일시가 체결 불가")
            d["open"] = float("nan")
        d = d.dropna(subset=["date", "high", "low", "close"])
        d = d[d["close"] > 0].sort_values(["code", "date"]).reset_index(drop=True)
        last = d["date"].max()
        age = (pd.Timestamp(dt.date.today()) - last).days
        self.notes.append(f"{fname}: {len(d)}행 / {d['code'].nunique()}종목 / "
                          f"~{last.date()} (경과 {age}일)")
        if age > CFG["STALE_DAYS"]:
            self.notes.append(f"  [STALE] {market} 패널 {age}일 경과 - 신호가 최신 시장 미반영")
        for code, g in d.groupby("code"):
            self.by_code[(market, code)] = g[["date", "open", "high", "low", "close"]] \
                .reset_index(drop=True)
        return d

    def load_local(self):
        k = self._load_panel("kospi_pit_daily.csv", "KOSPI")
        q = self._load_panel("kosdaq_pit_daily_pykrx.csv", "KOSDAQ")
        if k is None and q is None:
            return False
        if k is not None:
            self.panels["KOSPI"] = k
        if q is not None:
            self.panels["KOSDAQ"] = q
        self.used = self.used or "local"
        self._load_mcap_names()
        return True

    def _load_mcap_names(self):
        """
        시가총액 + 종목명 (실데이터).
        소스: liquidity_sector.csv (KOSPI) / liquidity_kosdaq.csv (KOSDAQ)
        ★ 이것은 '스냅샷'이다 (수집 시점 고정). 과거 시점의 시총이 아니다.
          → 백테스트에서 이걸로 유니버스를 정하면 **선택편향(look-ahead)** 이 생긴다.
            백테스트_결과.md 에 반드시 명시할 것. 은폐 금지.
        """
        for fname, market in (("liquidity_sector.csv", "KOSPI"),
                              ("liquidity_kosdaq.csv", "KOSDAQ")):
            m = read_csv(fname, dtype={"code": str})
            if m is None or not {"code", "name", "mcap"} <= set(m.columns):
                self.notes.append(f"[데이터부족] {fname} 없음 -> {market} 시총순위/종목명 불가")
                continue
            m["mcap"] = pd.to_numeric(m["mcap"], errors="coerce")
            m = m.dropna(subset=["mcap"])
            self.names.update(dict(zip(m["code"], m["name"])))
            self.mcap[market] = m.sort_values("mcap", ascending=False)
            self.notes.append(f"{fname}: 시총·종목명 {len(m)}종목 (스냅샷)")
        t = read_csv("theme_heat_members_latest.csv", dtype={"code": str})
        if t is not None and {"code", "name"} <= set(t.columns):
            for c, n in zip(t["code"], t["name"]):
                self.names.setdefault(c, n)

    def load_pykrx(self, asof):
        try:
            from pykrx import stock
        except Exception as e:
            self.notes.append(f"[데이터부족] pykrx 임포트 실패({e}) -> local 폴백")
            return False
        try:
            bd = call_timeout(stock.get_nearest_business_day_in_a_week,
                              args=(pd.Timestamp(asof).strftime("%Y%m%d"),), timeout=12)
            if not bd:
                raise RuntimeError("영업일 응답 없음")
            self.notes.append(f"pykrx 영업일 보정: {pd.Timestamp(asof).date()} -> {bd}")
            self.busday, self._stock = bd, stock
            self.used = "pykrx+local패널"
            return True
        except Exception as e:
            self.notes.append(f"[데이터부족] pykrx 접속/조회 실패({e}) -> local 폴백")
            return False

    def load(self, asof):
        if self.source in ("auto", "pykrx"):
            if not self.load_pykrx(asof) and self.source == "pykrx":
                self.notes.append("[중단] --source pykrx 인데 접속 불가")
        return self.load_local()

    def universe(self, market, top_n):
        """
        '시총 상위군' — 반드시 **시가총액** 기준.
        ⚠ 거래대금(거래량×가격)을 시총 대용으로 쓰면 **투기적 저가주**가 상위에 올라온다.
          (실측: 거래대금 상위 120개에 ATR/가격 15~20%인 동전주가 대거 포함됐다.)
          → 대용치 사용 금지. 시총 없으면 '데이터부족'으로 명시하고 축소 운영한다.
        """
        p = self.panels.get(market)
        if p is None:
            return []
        have = self.codes(market)

        # 1순위: pykrx 라이브 시총 (그 시점 실제 시총)
        if self._stock is not None and self.busday:
            try:
                cap = call_timeout(self._stock.get_market_cap_by_ticker,
                                   args=(self.busday, market), timeout=15)
                if cap is not None and len(cap):
                    live = [c for c in cap.sort_values("시가총액", ascending=False).index
                            if c in have]
                    if live:
                        self.notes.append(f"{market}: pykrx 시총 상위 {min(top_n,len(live))}종목 (라이브)")
                        return live[:top_n]
            except Exception as e:
                self.notes.append(f"[데이터부족] {market} pykrx 시총 조회 실패({e}) -> 스냅샷 사용")

        # 2순위: 로컬 시총 스냅샷 (liquidity_*.csv)
        m = self.mcap.get(market)
        if m is not None and len(m):
            live = [c for c in m["code"] if c in have]
            if live:
                self.notes.append(f"{market}: 시총 스냅샷 상위 {min(top_n,len(live))}종목 "
                                  f"[스냅샷 = 과거시점 시총 아님 -> 백테스트 시 선택편향 명시]")
                return live[:top_n]

        # 시총 없음 -> 대용치 만들지 않는다.
        self.notes.append(f"[데이터부족] {market}: 시가총액 데이터 없음 -> "
                          f"유니버스 구성 불가 (거래대금 대용 금지 — 동전주 오염)")
        return []

    def bars(self, market, code, asof, window=None):
        g = self.by_code.get((market, code))
        if g is None:
            return None
        i = int(g["date"].searchsorted(pd.Timestamp(asof), side="right"))
        if i < CFG["MIN_BARS"]:
            return None
        return g.iloc[max(0, i - (window or CFG["BARS_WINDOW"])):i]

    def full(self, market, code):
        return self.by_code.get((market, code))

    def codes(self, market):
        if market not in self._codes:
            p = self.panels.get(market)
            self._codes[market] = set(p["code"].unique()) if p is not None else set()
        return self._codes[market]

    def market_of(self, code):
        for m in self.panels:
            if code in self.codes(m):
                return m
        return None

    def name(self, code):
        return self.names.get(code, code)

    def last_date(self):
        ds = [p["date"].max() for p in self.panels.values()]
        return max(ds) if ds else None

    def trading_days(self, market="KOSPI"):
        p = self.panels.get(market)
        return sorted(pd.to_datetime(p["date"].unique())) if p is not None else []


def call_timeout(fn, args=(), kwargs=None, timeout=10):
    """pykrx 호출 타임아웃 래퍼 — 스크립트 행(hang) 방지."""
    import threading
    kwargs = kwargs or {}
    box = {}

    def run():
        try:
            box["v"] = fn(*args, **kwargs)
        except Exception as e:
            box["e"] = e

    t = threading.Thread(target=run, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise TimeoutError(f"{getattr(fn,'__name__','call')} {timeout}s 초과")
    if "e" in box:
        raise box["e"]
    return box.get("v")


def month_first_days(store):
    """실데이터 거래일 기준 '각 달의 첫 거래일' 집합. (1회 계산 후 캐시)"""
    if getattr(store, "_month_first", None) is None:
        days = set()
        for p in store.panels.values():
            days |= set(pd.to_datetime(p["date"].unique()))
        mf = {}
        for d in sorted(days):
            k = (d.year, d.month)
            if k not in mf:
                mf[k] = d
        store._month_first = mf
    return store._month_first


def is_first_trading_day(store, asof):
    """asof가 그 달의 첫 거래일인가 — 실데이터 거래일 목록으로 판정."""
    mf = month_first_days(store)
    asof = pd.Timestamp(asof)
    return mf.get((asof.year, asof.month)) == asof


# ═══════════════════════════════════════════════════════════════════════════
# 5) 매크로 게이트
# ═══════════════════════════════════════════════════════════════════════════
def macro_gate(asof):
    """(노출배수, regime, notes). 데이터 없으면 1.0 + '매크로 미연동'."""
    mult, notes, regime = 1.0, [], "매크로 미연동"
    asof = pd.Timestamp(asof)

    b = read_csv("breadth_features.csv")
    if b is not None and "regime" in b.columns and len(b):
        b["date"] = pd.to_datetime(b["date"], errors="coerce")
        bb = b.dropna(subset=["date"])
        bb = bb[bb["date"] <= asof]
        if len(bb):
            row = bb.iloc[-1]
            regime = str(row["regime"])
            age = (asof - row["date"]).days
            m = CFG["REGIME_EXPOSURE"].get(regime)
            if m is None:
                notes.append(f"[데이터부족] 미지의 regime '{regime}' -> 노출 조절 안 함")
            else:
                mult *= m
                notes.append(f"regime='{regime}' ({row['date'].date()}, {age}일 전) -> 노출 x{m:.2f}")
            if age > 30:
                notes.append(f"  [STALE] breadth_features {age}일 경과")
        else:
            notes.append("[데이터부족] breadth_features에 기준일 이전 데이터 없음")
    else:
        notes.append("[데이터부족] breadth_features.csv 없음 -> 매크로 미연동")

    v = read_csv("vkospi_daily.csv")
    if v is not None and {"Date", "VKOSPI"} <= set(v.columns) and len(v):
        v["Date"] = pd.to_datetime(v["Date"], errors="coerce")
        vv = v.dropna(subset=["Date"])
        vv = vv[vv["Date"] <= asof]
        if len(vv):
            row = vv.iloc[-1]
            vk, age = float(row["VKOSPI"]), (asof - row["Date"]).days
            if age > 30:
                notes.append(f"[데이터부족] VKOSPI {age}일 경과({row['Date'].date()}) -> 미사용")
            elif vk >= CFG["VKOSPI_EXTREME"]:
                mult *= 0.5
                notes.append(f"VKOSPI {vk:.1f} >= {CFG['VKOSPI_EXTREME']} -> 노출 x0.50")
            elif vk >= CFG["VKOSPI_HIGH"]:
                mult *= 0.7
                notes.append(f"VKOSPI {vk:.1f} >= {CFG['VKOSPI_HIGH']} -> 노출 x0.70")
            else:
                notes.append(f"VKOSPI {vk:.1f} (정상) -> 조절 없음")
        else:
            notes.append("[데이터부족] VKOSPI 기준일 이전 데이터 없음")
    else:
        notes.append("[데이터부족] vkospi_daily.csv 없음")

    if CFG["HALLOWEEN"]:
        if asof.month in (5, 6, 7, 8, 9, 10):
            mult *= CFG["HALLOWEEN_SUMMER_W"]
            notes.append(f"할로윈 ON: 여름({asof.month}월) -> 노출 x{CFG['HALLOWEEN_SUMMER_W']:.2f}")
        else:
            notes.append(f"할로윈 ON: 겨울({asof.month}월) -> 노출 x1.00")
    else:
        notes.append("할로윈 오버레이 OFF (기본) - 할로윈_검증결과.md 참조")

    return max(0.0, min(1.0, mult)), regime, notes


def halloween_mult(asof):
    """백테스트용 순수 계절 배수 (CFG['HALLOWEEN'] 무시하고 명시 계산)."""
    return CFG["HALLOWEEN_SUMMER_W"] if pd.Timestamp(asof).month in (5, 6, 7, 8, 9, 10) else 1.0


# ═══════════════════════════════════════════════════════════════════════════
# 6) 커플링 — ★기록 전용. 규칙 미반영.★ 검증 전 규칙 추가 금지.
# ═══════════════════════════════════════════════════════════════════════════
def label_coupling(c):
    if isnan(c):
        return "데이터부족"
    T = CFG["COUPLING"]
    if c >= T["STRONG"]:
        return "COUPLED_STRONG"
    if c >= T["COUPLED"]:
        return "COUPLED"
    if c > T["INVERSE"]:
        return "DECOUPLED"
    return "INVERSE"


def load_coupling_panel():
    """
    미국(1일 lag) vs 국내 일간수익률 정렬 패널.
    소스: 시장영향_검증_kospi_raw.csv / _kosdaq_raw.csv
      · 이 파일의 sp·sox 는 **이미 전일(d-1) 미국 수익률**이다.
        (시장영향_검증.py 헤더: "모든 X는 d일까지 확정값 -> 코스피 d+1 예측",
         CONDS: sox="전일 SOX 수익", sp="전일 S&P500 수익")
      · y_same = 당일 국내 지수 수익률(%)
      => corr(sp[d], y_same[d]) = corr(전일 미국, 당일 한국). 요구된 1일 lag 정렬. look-ahead 없음.
    나스닥(^IXIC)은 오프라인 소스에 없음 -> 데이터부족(공란). PC에서 yfinance로 보강 가능.
    """
    notes = []
    a = read_csv("시장영향_검증_kospi_raw.csv")
    if a is None:
        return None, None, ["[데이터부족] 시장영향_검증_kospi_raw.csv 없음 -> 커플링 기록 불가"]
    a["date"] = pd.to_datetime(a["date"], errors="coerce")
    a = a.dropna(subset=["date"])
    df = a[["date", "sp", "sox", "y_same"]].rename(
        columns={"sp": "spx_prev", "sox": "sox_prev", "y_same": "kospi"})

    b = read_csv("시장영향_검증_kosdaq_raw.csv")
    if b is not None and "y_same" in b.columns:
        b["date"] = pd.to_datetime(b["date"], errors="coerce")
        b = b.dropna(subset=["date"])[["date", "y_same"]].rename(columns={"y_same": "kosdaq"})
        df = df.merge(b, on="date", how="left")
    else:
        df["kosdaq"] = float("nan")
        notes.append("[데이터부족] 코스닥 raw 없음 -> 코스닥 상관 공란")

    df["nasdaq_prev"] = float("nan")
    notes.append("[데이터부족] 나스닥(^IXIC) 오프라인 소스 없음 -> corr_20d_nasdaq 공란")
    notes.append(f"커플링 패널: {len(df)}행 ({df['date'].min().date()} ~ {df['date'].max().date()})")
    return df.sort_values("date").reset_index(drop=True), "시장영향_검증_raw(1d lag 사전정렬)", notes


def coupling_series(panel):
    """패널 전체에 대한 일별 커플링 시계열 (백테스트용). 롤링, look-ahead 없음."""
    d = panel.copy()
    out = pd.DataFrame({"date": d["date"]})
    out["corr_20d_spx"] = d["kospi"].rolling(20).corr(d["spx_prev"])
    out["corr_60d_spx"] = d["kospi"].rolling(60).corr(d["spx_prev"])
    out["corr_20d_sox"] = d["kospi"].rolling(20).corr(d["sox_prev"])
    out["corr_20d_nasdaq"] = d["kospi"].rolling(20).corr(d["nasdaq_prev"])
    out["corr_20d_kosdaq_vs_spx"] = d["kosdaq"].rolling(20).corr(d["spx_prev"])
    out["corr_kospi_kosdaq_20d"] = d["kospi"].rolling(20).corr(d["kosdaq"])
    cov = d["kospi"].rolling(20).cov(d["spx_prev"])
    var = d["spx_prev"].rolling(20).var()
    out["beta_20d_spx"] = cov / var.where(var > 0)
    out["state"] = out["corr_20d_spx"].apply(label_coupling)
    out["spx_ret_prev"] = d["spx_prev"]
    out["kospi_ret"] = d["kospi"]
    return out


def compute_coupling(asof, panel=None):
    """asof 시점 커플링 1행. 실데이터 없으면 공란(채우지 않는다)."""
    row = dict.fromkeys(COUP_COLS, "")
    row["date"] = pd.Timestamp(asof).date().isoformat()
    src = "시장영향_검증_raw(1d lag 사전정렬)"
    if panel is None:
        panel, src2, _ = load_coupling_panel()
        src = src2 or "데이터부족"
    row["source"] = src
    if panel is None or not len(panel):
        row["state"], row["state_change"] = "데이터부족", "N"
        return row

    d = panel[panel["date"] <= pd.Timestamp(asof)]
    if len(d) < 20:
        row["state"], row["state_change"] = "데이터부족", "N"
        return row

    cs = coupling_series(d).iloc[-1]
    for k in ("corr_20d_spx", "corr_60d_spx", "corr_20d_nasdaq", "corr_20d_sox",
              "corr_20d_kosdaq_vs_spx", "corr_kospi_kosdaq_20d", "beta_20d_spx",
              "spx_ret_prev", "kospi_ret"):
        v = cs[k]
        row[k] = "" if (pd.isna(v)) else round(float(v), 4)
    row["state"] = str(cs["state"])

    prev = read_csv("coupling_history.csv", where=DIR_LEDGER)
    ps = str(prev["state"].iloc[-1]) if (prev is not None and len(prev)
                                         and "state" in prev.columns) else None
    row["state_change"] = "Y" if (ps and ps != row["state"]) else "N"
    return row


def append_coupling(row):
    p = os.path.join(DIR_LEDGER, "coupling_history.csv")
    ex = os.path.exists(p)
    if ex:
        old = read_csv("coupling_history.csv", where=DIR_LEDGER)
        if old is not None and len(old) and str(old["date"].iloc[-1]) == row["date"]:
            return   # 같은 날 중복 방지 (재실행 멱등)
    pd.DataFrame([row], columns=COUP_COLS).to_csv(
        p, mode="a" if ex else "w", header=not ex, index=False, encoding="utf-8-sig")


# ═══════════════════════════════════════════════════════════════════════════
# 7) 국면(Phase) — ★인과적 룰 기반★. 시점 t 판정에 t 이전 데이터만 사용.
#    사후 라벨링(예: "2022는 하락장이었으니까") 금지 = look-ahead.
# ═══════════════════════════════════════════════════════════════════════════
def load_kospi_index_actual():
    """실측 KOSPI 지수 종가. ★공백 있음★ (kospi_index_daily.csv가 2011-08에서 잘려 있음)."""
    parts, notes = [], []
    a = read_csv("kospi_index_daily.csv")
    if a is not None and {"Date", "Close"} <= set(a.columns):
        a["Date"] = pd.to_datetime(a["Date"], errors="coerce")
        a["Close"] = pd.to_numeric(a["Close"], errors="coerce")
        a = a.dropna(subset=["Date", "Close"])
        parts.append(a.set_index("Date")["Close"])
        notes.append(f"kospi_index_daily.csv: {len(a)}행 (~{a['Date'].max().date()}) "
                     f"[파일 말미 손상/잘림]")
    b = read_csv("attribution_pit_daily.csv", dtype={"code": str})
    if b is not None and {"code", "date", "close"} <= set(b.columns):
        b = b[b["code"] == "1001"].copy()
        b["date"] = pd.to_datetime(b["date"], errors="coerce")
        b["close"] = pd.to_numeric(b["close"], errors="coerce")
        b = b.dropna(subset=["date", "close"])
        if len(b):
            parts.append(b.set_index("date")["close"])
            notes.append(f"attribution_pit_daily(1001): {len(b)}행 "
                         f"({b['date'].min().date()}~{b['date'].max().date()})")
    if not parts:
        return None, ["[데이터부족] 실측 KOSPI 지수 없음"]
    s = pd.concat(parts).sort_index()
    s = s[~s.index.duplicated(keep="last")]
    gaps = s.index.to_series().diff().dt.days
    for i, dd in gaps[gaps > 10].items():
        notes.append(f"[데이터부족] 실측 지수 공백: ~{i.date()} 직전 {int(dd)}일 결측 (보간 안 함)")
    return s, notes


def load_kospi_index():
    """
    국면 판정용 KOSPI 경로.

    ★왜 재구성하는가 (정직하게)★
      실측 지수 파일(kospi_index_daily.csv)이 **2011-08에서 잘려 있어** 2011~2023 (약 11.8년)이
      비어 있다. 백테스트 구간(2019~2026)의 대부분이 이 공백에 걸린다.
      → 공백을 보간하면 그게 바로 '가짜 데이터'다. 절대 안 한다.

    ★대신 쓰는 것: 실측 일간수익률의 누적★
      시장영향_검증_kospi_raw.csv 의 `y_same` = **실측 KOSPI 일간수익률(%)**,
      1996-12 ~ 2026-06 **연속(공백 없음)**. 이것을 누적(cumprod)해 지수 '경로'를 만든다.
      · 이것은 보간·추정·합성이 아니다. 관측된 실수익률의 **정확한 변환**이다.
      · 레벨(절대값)은 임의 기준이지만, 국면 판정에 쓰는 지표는 전부 **스케일 불변**이다:
        MA200 교차 여부, MA200 기울기 부호, 드로다운 %, 실현변동성 — 전부 배율에 무관.
      · 검증(겹치는 2023-06~2026-06, n=739): corr(재구성 수익률, 실측 지수 수익률) = **0.9991**,
        평균절대오차 0.0027%p.  → y_same 이 KOSPI 일간수익률임이 실측으로 확인됨.
      · 한계: 누적 3년 경로 오차 약 3.3% (소수 이상치일 종속). 레벨 자체는 신뢰하지 말 것.
        본 용도(스케일 불변 지표)에는 영향 없음.

    반환 (Series 경로, notes)
    """
    notes = []
    r = read_csv("시장영향_검증_kospi_raw.csv")
    if r is None or "y_same" not in r.columns:
        notes.append("[데이터부족] 시장영향_검증_kospi_raw.csv 없음 -> 실측 지수로 폴백")
        return load_kospi_index_actual()

    r["date"] = pd.to_datetime(r["date"], errors="coerce")
    r["y_same"] = pd.to_numeric(r["y_same"], errors="coerce")
    r = r.dropna(subset=["date", "y_same"]).sort_values("date")
    r = r[~r["date"].duplicated(keep="last")]

    gaps = r["date"].diff().dt.days
    big = gaps[gaps > 10]
    for i, dd in big.items():
        notes.append(f"[데이터부족] 수익률 공백: ~{r.loc[i,'date'].date()} 직전 {int(dd)}일 결측")

    path = (1.0 + r["y_same"] / 100.0).cumprod() * 1000.0
    path.index = pd.DatetimeIndex(r["date"])
    notes.append(f"국면 판정 경로: 실측 일간수익률 누적 (시장영향_검증_kospi_raw.csv y_same), "
                 f"{len(path)}행 {path.index.min().date()}~{path.index.max().date()}, 공백 {len(big)}개")

    # 실측 지수와 대조 검증 (가능한 구간에서)
    act, anotes = load_kospi_index_actual()
    notes += anotes
    if act is not None:
        j = pd.DataFrame({"act": act}).join(pd.DataFrame({"rec": path}), how="inner")
        j["ar"] = j["act"].pct_change()
        j["rr"] = j["rec"].pct_change()
        jj = j.dropna()
        if len(jj) > 100:
            c = float(jj["ar"].corr(jj["rr"]))
            mae = float((jj["ar"] - jj["rr"]).abs().mean() * 100)
            notes.append(f"[검증] 재구성 vs 실측 지수 (겹침 n={len(jj)}): "
                         f"수익률 상관 {c:.4f}, 평균절대오차 {mae:.4f}%p "
                         f"-> 재구성 경로 타당 (스케일 불변 지표에만 사용)")
    return path, notes


def phase_series(idx_close):
    """
    KOSPI 경로 -> 일별 국면 4축. 전부 인과적(과거 데이터만 사용).
      A 추세  : BULL(지수>MA200 & MA200 상승) / BEAR(지수<MA200 & MA200 하락) / TRANSITION
      B 변동성: 20일 실현변동성(연율)의 과거 3년 롤링 분위수 -> VOL_LOW/MID/HIGH
      D 드로다운: 전고점 대비 DD_NONE(<5%) / DD_CORRECTION(5~20%) / DD_BEAR(>20%)
      (C 커플링은 coupling_series 에서 별도)
    """
    P = CFG["PHASE"]
    s = pd.Series(idx_close).astype(float).dropna()
    df = pd.DataFrame({"close": s})
    df["ma200"] = s.rolling(P["MA_LONG"]).mean()
    df["ma200_up"] = df["ma200"] > df["ma200"].shift(20)

    df["trend"] = "TRANSITION"
    df.loc[(df["close"] > df["ma200"]) & df["ma200_up"], "trend"] = "BULL"
    df.loc[(df["close"] < df["ma200"]) & (~df["ma200_up"]), "trend"] = "BEAR"
    df.loc[df["ma200"].isna(), "trend"] = "데이터부족"

    ret = s.pct_change()
    df["rv20"] = ret.rolling(P["VOL_WIN"]).std() * math.sqrt(252)
    win = int(252 * P["VOL_QUANTILE_YEARS"])
    q_lo = df["rv20"].rolling(win, min_periods=252).quantile(P["VOL_LO"])
    q_hi = df["rv20"].rolling(win, min_periods=252).quantile(P["VOL_HI"])
    df["vol"] = "데이터부족"
    ok = df["rv20"].notna() & q_lo.notna() & q_hi.notna()
    df.loc[ok & (df["rv20"] < q_lo), "vol"] = "VOL_LOW"
    df.loc[ok & (df["rv20"] >= q_lo) & (df["rv20"] <= q_hi), "vol"] = "VOL_MID"
    df.loc[ok & (df["rv20"] > q_hi), "vol"] = "VOL_HIGH"

    peak = s.cummax()
    df["dd_pct"] = s / peak - 1.0
    df["dd"] = "DD_NONE"
    df.loc[df["dd_pct"] <= -P["DD_CORRECTION"], "dd"] = "DD_CORRECTION"
    df.loc[df["dd_pct"] <= -P["DD_BEAR"], "dd"] = "DD_BEAR"

    df.index.name = "date"
    return df.reset_index()[["date", "trend", "vol", "dd", "rv20", "ma200", "dd_pct"]]
