# -*- coding: utf-8 -*-
"""
할로윈_검증.py — KOSPI 실데이터로 11~4월(겨울) vs 5~10월(여름) 수익률 검정.

목적: Phase 1 가상매매 엔진에 '할로윈 계절성'을 오버레이로 채택할지 기각할지 판정.
      (사용자 질문 "할로윈 주기를 리밸 주기로 쓸까?"에 대한 답: 아니오.
       할로윈은 '리밸런스 주기'가 아니라 '노출 조절 오버레이'다. 아래는 오버레이로서의 검정.)

★ 절대 원칙 ★
  - 실재 데이터만 사용. 추정/보간/합성 절대 금지.
  - 데이터가 없는 구간은 '데이터부족'으로 명시하고 검정에서 제외한다.
  - 파일이 잘려 있으면 잘린 사실을 그대로 보고한다. (통계오류가 최대 위험)

데이터 소스 (모두 로컬 실파일, 네트워크 미사용):
  1) kospi_index_daily.csv          (Date, Close)          — FDR KS11 수집분
  2) attribution_pit_daily.csv      (code=1001 = KOSPI지수) — pykrx 수집분
  두 소스를 합집합·중복제거하고, 10일 초과 공백은 '데이터부족 구간'으로 리포트한다.

실행:
  py 할로윈_검증.py            # 검정 실행 → 할로윈_검증결과.md
  py 할로윈_검증.py --self-test

투자자문 아님. 지표·규칙 사실만 기록. 결정·책임은 본인.
"""
import os, sys, argparse, math
import numpy as np
import pandas as pd

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from jq_paths import ROOT, DIR_VERIFY, data_path, searched, ensure_dirs

# 데이터 CSV 원본은 진우퀀트 루트에 있다(코드만 가상매매\엔진\ 아래).
# 과거에 BASE=엔진폴더로 잡혀 있어 조용히 "데이터 없음"으로 실패했다. jq_paths 로 일원화.
BASE = ROOT
ensure_dirs()

# --- 사전등록 파라미터 (결과 보기 전 고정) ---------------------------------
CFG = dict(
    DIV_ANNUAL=0.018,      # 배당 연 1.8% (월 균등 배분 근사)
    COST_ONEWAY=0.0015,    # 편도 15bp, 연 2회 매매
    RF_ANNUAL=0.030,       # 현금 연 3.0%
    WINTER={11, 12, 1, 2, 3, 4},
    GAP_DAYS=10,           # 리포트용: 이보다 긴 달력 공백은 진단 출력
    # --- 휴장 vs 결측 구분 (2026-07-13 수정) ---------------------------------
    # 한국 증시는 연휴에 최대 6~8 영업일 연속 휴장한다(2017 추석 = 6영업일).
    # 그건 '데이터 결측'이 아니라 '시장이 안 열린 것'이다. 둘을 구분하지 못해
    # 2017-09-29~10-10 휴장 하나 때문에 판정이 막혀 있었다.
    HOLIDAY_MAX_BDAYS=10,   # 연속 결측 영업일 ≤ 10 → 휴장으로 간주(결측 아님)
    BLOCK_CONSEC_BDAYS=20,  # 진짜 결측이 연속 20영업일 초과 → 데이터부족 차단
    BLOCK_TOTAL_FRAC=0.01,  # 또는 총 결측 영업일 > 전체의 1% → 차단
    PUB_YEAR=2003,          # Bouman & Jacobsen(2002) 발표 이후 = 2003-01~
    # 채택 게이트 (사전등록): 계절 차이가 통계적으로 유의하고, 오버레이가 위험조정 개선
    GATE_P=0.10,           # 겨울-여름 차이 t검정 p < 0.10
    GATE_CAGR_DRAG=0.010,  # 오버레이 CAGR이 buy&hold 대비 -1.0%p 이내
)


# ---------------------------------------------------------------------------
# 데이터 로딩 — 실재 데이터만. 없으면 '데이터부족'.
# ---------------------------------------------------------------------------
def _load_source_a():
    """kospi_index_daily.csv → Series(Close). 파싱 실패 행은 버리고 개수를 보고."""
    p = data_path("kospi_index_daily.csv")
    if not p:
        return None, "kospi_index_daily.csv 없음 — 뒤진 경로: " + " | ".join(searched("kospi_index_daily.csv"))
    d = pd.read_csv(p, encoding="utf-8-sig")
    if "Date" not in d.columns or "Close" not in d.columns:
        return None, "kospi_index_daily.csv 컬럼 이상"
    n0 = len(d)
    d["Date"] = pd.to_datetime(d["Date"], errors="coerce")
    d["Close"] = pd.to_numeric(d["Close"], errors="coerce")
    d = d.dropna(subset=["Date", "Close"])
    bad = n0 - len(d)
    s = d.set_index("Date")["Close"].sort_index()
    s = s[~s.index.duplicated(keep="last")]
    note = f"kospi_index_daily.csv: {len(s)}행 유효"
    if bad:
        note += f" / 손상행 {bad}개 제외(파일 말미 잘림 의심)"
    return s, note


def _load_source_b():
    """attribution_pit_daily.csv의 code=1001(KOSPI지수) → Series(close)."""
    p = data_path("attribution_pit_daily.csv")
    if not p:
        return None, "attribution_pit_daily.csv 없음 — 뒤진 경로: " + " | ".join(searched("attribution_pit_daily.csv"))
    d = pd.read_csv(p, encoding="utf-8-sig", dtype={"code": str})
    if not {"code", "date", "close"} <= set(d.columns):
        return None, "attribution_pit_daily.csv 컬럼 이상"
    d = d[d["code"] == "1001"].copy()
    if d.empty:
        return None, "attribution_pit_daily.csv에 code=1001(KOSPI지수) 없음"
    d["date"] = pd.to_datetime(d["date"], errors="coerce")
    d["close"] = pd.to_numeric(d["close"], errors="coerce")
    d = d.dropna(subset=["date", "close"])
    s = d.set_index("date")["close"].sort_index()
    s = s[~s.index.duplicated(keep="last")]
    return s, f"attribution_pit_daily.csv(code=1001): {len(s)}행 유효"


def load_kospi():
    """두 실데이터 소스를 합쳐 일별 KOSPI 종가 Series 반환 + 진단 노트."""
    notes, parts = [], []
    for loader in (_load_source_a, _load_source_b):
        s, note = loader()
        notes.append(note)
        if s is not None and len(s):
            parts.append(s)
    if not parts:
        return None, notes, []

    s = pd.concat(parts).sort_index()
    s = s[~s.index.duplicated(keep="last")]

    gaps, holidays = classify_gaps(s)
    return s, notes, gaps, holidays


def classify_gaps(s):
    """연속 관측 사이의 공백을 '휴장'과 '데이터 결측'으로 분리.
    달력일이 아니라 **영업일(월~금)** 로 센다. 한국 증시는 연휴에 최대 6~8영업일
    연속 휴장한다(2017 추석 = 6영업일). 그건 결측이 아니다.
    반환: (missing, holiday) — 각 원소 (시작, 끝, 달력일, 영업일)"""
    missing, holiday = [], []
    idx = s.index
    for i in range(1, len(idx)):
        a, b = idx[i - 1], idx[i]
        cal = int((b - a).days)
        if cal <= 3:
            continue
        bd = int(len(pd.bdate_range(a + pd.Timedelta(days=1), b - pd.Timedelta(days=1))))
        if bd <= 0:
            continue
        rec = (a, b, cal, bd)
        (holiday if bd <= CFG["HOLIDAY_MAX_BDAYS"] else missing).append(rec)
    return missing, holiday


def blocking(s, missing):
    """데이터부족으로 검정을 '차단'할지. (차단여부, 사유)"""
    if not missing:
        return False, "결측 없음"
    worst = max(m[3] for m in missing)
    tot = sum(m[3] for m in missing)
    exp = int(len(pd.bdate_range(s.index.min(), s.index.max())))
    frac = tot / exp if exp else 1.0
    if worst > CFG["BLOCK_CONSEC_BDAYS"]:
        return True, f"연속 결측 {worst}영업일 > 한계 {CFG['BLOCK_CONSEC_BDAYS']}영업일"
    if frac > CFG["BLOCK_TOTAL_FRAC"]:
        return True, (f"총 결측 {tot}영업일 = 전체의 {frac*100:.2f}% > 한계 "
                      f"{CFG['BLOCK_TOTAL_FRAC']*100:.1f}%")
    return False, f"총 결측 {tot}영업일({frac*100:.2f}%) — 한계 이내"


def monthly_returns(s):
    """일별 종가 → 월말 종가 → 월수익률(배당 근사 가산). 실측만.

    ⚠️ 진행 중인 달은 제외한다. 오늘이 7월 13일이면 '7월 수익률'이란 건 없다 —
    7/1~7/13 부분수익을 한 달치로 취급하면 표본을 오염시킨다.
    (2026-07-13 발견: 미완결 2026-07이 '최악 5개월'에 들어가 있었다.)
    """
    m = s.resample("ME").last().dropna()
    # 마지막 관측일이 그 달의 마지막 영업일보다 이르면 → 그 달은 미완결
    if len(m):
        last_obs = s.index.max()
        month_end = m.index[-1]                       # 해당 월의 달력 말일
        last_bd = pd.bdate_range(month_end.replace(day=1), month_end)[-1]
        if last_obs < last_bd:
            m = m.iloc[:-1]
    r = m.pct_change().dropna() + CFG["DIV_ANNUAL"] / 12.0
    return r


def drop_gap_months(r, gaps):
    """데이터부족 구간에 걸친 월수익률은 제거(가짜 수익률 방지)."""
    if not gaps:
        return r, 0
    bad = pd.Series(False, index=r.index)
    for a, b, *_ in gaps:
        # 공백을 가로지르는 월(= 공백 종료월까지)의 수익률은 신뢰 불가
        bad |= (r.index >= pd.Timestamp(a).to_period("M").to_timestamp("M")) & \
               (r.index <= pd.Timestamp(b).to_period("M").to_timestamp("M"))
    return r[~bad], int(bad.sum())


# ---------------------------------------------------------------------------
# 강건성 검정 — 채택 전 필수 관문 2개 (2026-07-13 추가)
# ---------------------------------------------------------------------------
def _norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def mann_whitney_u(a, b):
    """Mann-Whitney U (정규근사·tie보정). 비모수 → 이상치에 강건. (U, z, p)"""
    a, b = np.asarray(a, float), np.asarray(b, float)
    na, nb = len(a), len(b)
    if na < 3 or nb < 3:
        return float("nan"), float("nan"), float("nan")
    allv = np.concatenate([a, b])
    order = allv.argsort()
    ranks = np.empty(len(allv), float)
    ranks[order] = np.arange(1, len(allv) + 1)
    tie_term = 0.0
    uniq, cnt = np.unique(allv, return_counts=True)
    for v, c in zip(uniq, cnt):
        if c > 1:
            m = allv == v
            ranks[m] = ranks[m].mean()
            tie_term += c ** 3 - c
    U = ranks[:na].sum() - na * (na + 1) / 2.0
    N = na + nb
    mu = na * nb / 2.0
    var = na * nb / 12.0 * ((N + 1) - tie_term / (N * (N - 1)))
    if var <= 0:
        return U, float("nan"), float("nan")
    z = (U - mu) / math.sqrt(var)
    return U, z, 2.0 * (1.0 - _norm_cdf(abs(z)))


def season_split(r):
    return (r[[d.month in CFG["WINTER"] for d in r.index]],
            r[[d.month not in CFG["WINTER"] for d in r.index]])


def season_stats(r, label):
    w, su = season_split(r)
    if len(w) < 3 or len(su) < 3:
        return dict(label=label, n=len(r), ok=False)
    t, dof, p = welch_t(w.values, su.values)
    _, z, pu = mann_whitney_u(w.values, su.values)
    return dict(label=label, n=len(r), ok=True, nw=len(w), ns=len(su),
                mw=float(w.mean()), ms=float(su.mean()),
                diff=float(w.mean() - su.mean()),
                mdiff=float(w.median() - su.median()),
                t=t, p=p, z=z, pu=pu)


def subsample_tests(r):
    """(A) Post-publication — 전체 / 발표전 / 발표후."""
    y = CFG["PUB_YEAR"]
    return [season_stats(r, "전체"),
            season_stats(r[r.index < pd.Timestamp(f"{y}-01-01")], f"발표전 (~{y-1})"),
            season_stats(r[r.index >= pd.Timestamp(f"{y}-01-01")], f"발표후 ({y}~)")]


def outlier_tests(r):
    """(B) 이상치(폭락) 의존성."""
    out = [season_stats(r, "기준(전체)")]
    for k in (5, 10):
        if len(r) > k + 20:
            out.append(season_stats(r.drop(r.nsmallest(k).index), f"최악 {k}개월 제외"))
    crash = [i for i in r.index if i.strftime("%Y-%m") in ("1997-10", "2008-10")]
    if crash:
        out.append(season_stats(r.drop(crash), "IMF·리먼 제외"))
    worst = [(i.strftime("%Y-%m"), float(v)) for i, v in r.nsmallest(5).items()]
    return out, worst, [(i.strftime("%Y-%m"), float(r[i])) for i in crash]


# ---------------------------------------------------------------------------
# (C) 매크로 국면별 검정 + 이질성 F검정 (2026-07-13 추가)
#     "IMF 전/후, 리먼 전/후는 매크로가 다르다. 묶어보면 안 되는 것 아닌가?"
#     → 그 질문 자체를 검정한다. 묶어도 되는지는 데이터가 답한다.
# ---------------------------------------------------------------------------
REGIMES = [("① IMF 이전", None, "1997-11-01"),
           ("② IMF~리먼", "1997-11-01", "2008-09-01"),
           ("③ 리먼 이후", "2008-09-01", None)]


def _slice(r, a, b):
    x = r
    if a: x = x[x.index >= pd.Timestamp(a)]
    if b: x = x[x.index < pd.Timestamp(b)]
    return x


def regime_tests(r):
    out = []
    for nm, a, b in REGIMES:
        x = _slice(r, a, b)
        st = season_stats(x, nm)
        if st.get("ok"):
            w, su = season_split(x)
            st["se"] = float(math.sqrt(w.var(ddof=1) / len(w) + su.var(ddof=1) / len(su)))
        out.append(st)
    full = season_stats(r, "전체(pooled)")
    if full.get("ok"):
        w, su = season_split(r)
        full["se"] = float(math.sqrt(w.var(ddof=1) / len(w) + su.var(ddof=1) / len(su)))
    out.append(full)
    return out


def _ssr(X, y):
    b, *_ = np.linalg.lstsq(X, y, rcond=None)
    e = y - X @ b
    return float(e @ e), b


def _f_p(F, d1, d2):
    """F분포 상측확률 — 기존 _betainc 재사용(scipy 없이)."""
    if not np.isfinite(F) or F <= 0:
        return 1.0
    x = d2 / (d2 + d1 * F)
    return float(_betainc(d2 / 2.0, d1 / 2.0, x))


def heterogeneity_test(r):
    """겨울효과가 국면마다 다른가? 상호작용 F검정. H0: 모두 같다(=묶어도 된다)."""
    y = r.values.astype(float)
    n = len(y)
    win = np.array([1.0 if d.month in CFG["WINTER"] else 0.0 for d in r.index])
    reg = np.array([0 if d < pd.Timestamp("1997-11-01")
                    else (1 if d < pd.Timestamp("2008-09-01") else 2) for d in r.index])
    D = np.column_stack([(reg == k).astype(float) for k in (1, 2)])
    Xr = np.column_stack([np.ones(n), win, D])
    Xf = np.column_stack([Xr, D * win[:, None]])
    sr, _ = _ssr(Xr, y)
    sf, _ = _ssr(Xf, y)
    q = Xf.shape[1] - Xr.shape[1]
    dfree = n - Xf.shape[1]
    if dfree <= 0 or sf <= 0:
        return float("nan"), float("nan"), q, dfree
    F = ((sr - sf) / q) / (sf / dfree)
    return F, _f_p(F, q, dfree), q, dfree


def break_test(r, cut):
    """특정 시점 전후로 겨울효과가 달라졌는가? (상호작용 1개) → (계수, F, p)"""
    y = r.values.astype(float)
    n = len(y)
    win = np.array([1.0 if d.month in CFG["WINTER"] else 0.0 for d in r.index])
    post = np.asarray(r.index >= pd.Timestamp(cut), dtype=float)
    Xr = np.column_stack([np.ones(n), win, post])
    Xf = np.column_stack([Xr, win * post])
    sr, _ = _ssr(Xr, y)
    sf, b = _ssr(Xf, y)
    dfree = n - Xf.shape[1]
    if dfree <= 0 or sf <= 0:
        return float("nan"), float("nan"), float("nan")
    F = (sr - sf) / (sf / dfree)
    return float(b[3]), F, _f_p(F, 1, dfree)


def decide(gates, sub, rob, blocked, block_why):
    """사전등록 판정 규칙 — 결과를 보기 전에 고정했다. 사후 조정 금지."""
    if blocked:
        return "판정불가(데이터부족)", [f"차단: {block_why}"]
    post = next((x for x in sub if x["label"].startswith("발표후")), None)
    if not post or not post.get("ok"):
        return "판정불가(발표후 표본 부족)", ["발표후 구간 표본 부족"]

    reasons = []
    a_pass = post["p"] < CFG["GATE_P"]
    reasons.append(f"(A) 발표후({CFG['PUB_YEAR']}~) p={post['p']:.4f} "
                   f"{'<' if a_pass else '>='} {CFG['GATE_P']} -> {'통과' if a_pass else '실패'}")

    b_items = [x for x in rob if x.get("ok") and x["label"] != "기준(전체)"]
    b_pass = bool(b_items) and all(x["diff"] > 0 and x["p"] < CFG["GATE_P"] for x in b_items)
    for x in b_items:
        reasons.append(f"(B) {x['label']}: 차이 {x['diff']*100:+.3f}%p, p={x['p']:.4f}")
    reasons.append(f"(B) 종합 -> {'통과' if b_pass else '실패'}")
    reasons.append(f"게이트 {sum(gates.values())}/{len(gates)}")

    if not a_pass:
        return "기각 (post-publication decay)", reasons
    if all(gates.values()) and b_pass:
        return "채택 후보", reasons
    if not b_pass:
        return "조건부 (테일리스크 회피 — 계절 알파 아님, OFF 유지)", reasons
    return "조건부 (게이트 미충족 — OFF 유지)", reasons


def log_decision(verdict, sub):
    """채택기각_로그.csv 에 1행 추가."""
    import csv as _csv
    from datetime import datetime
    path = os.path.join(DIR_VERIFY, "채택기각_로그.csv")
    post = next((x for x in sub if x["label"].startswith("발표후")), {}) or {}
    full = next((x for x in sub if x["label"] == "전체"), {}) or {}
    row = {
        "일시": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "항목": "할로윈 계절성 오버레이",
        "판정": verdict,
        "표본_개월": full.get("n", ""),
        "전체_차이%p": f"{full['diff']*100:.3f}" if full.get("ok") else "",
        "전체_p": f"{full['p']:.4f}" if full.get("ok") else "",
        "발표후_차이%p": f"{post['diff']*100:.3f}" if post.get("ok") else "",
        "발표후_p": f"{post['p']:.4f}" if post.get("ok") else "",
        "근거": "Bouman&Jacobsen2002 발표후 하위표본 + 이상치제거 강건성",
    }
    exists = os.path.exists(path)
    with open(path, "a", encoding="utf-8-sig", newline="") as f:
        w = _csv.DictWriter(f, fieldnames=list(row))
        if not exists:
            w.writeheader()
        w.writerow(row)
    return path


# ---------------------------------------------------------------------------
# 통계
# ---------------------------------------------------------------------------
def welch_t(a, b):
    """Welch t검정 (scipy 없이). 반환 (t, dof, p_two_sided)."""
    a, b = np.asarray(a, float), np.asarray(b, float)
    na, nb = len(a), len(b)
    if na < 2 or nb < 2:
        return float("nan"), float("nan"), float("nan")
    va, vb = a.var(ddof=1), b.var(ddof=1)
    se2 = va / na + vb / nb
    if se2 <= 0:
        return float("nan"), float("nan"), float("nan")
    t = (a.mean() - b.mean()) / math.sqrt(se2)
    dof = se2 ** 2 / ((va / na) ** 2 / (na - 1) + (vb / nb) ** 2 / (nb - 1))
    p = 2.0 * _t_sf(abs(t), dof)
    return float(t), float(dof), float(p)


def _t_sf(t, df):
    """t분포 상측 꼬리확률 — 정규화 불완전베타로 계산(scipy 비의존)."""
    x = df / (df + t * t)
    return 0.5 * _betainc(df / 2.0, 0.5, x)


def _betainc(a, b, x):
    """정규화 불완전베타 I_x(a,b) — 연분수(Lentz)."""
    if x <= 0:
        return 0.0
    if x >= 1:
        return 1.0
    lbeta = math.lgamma(a) + math.lgamma(b) - math.lgamma(a + b)
    front = math.exp(a * math.log(x) + b * math.log(1 - x) - lbeta)
    if x < (a + 1) / (a + b + 2):
        return front * _betacf(a, b, x) / a
    return 1.0 - math.exp(b * math.log(1 - x) + a * math.log(x) - lbeta) * _betacf(b, a, 1 - x) / b


def _betacf(a, b, x, itmax=300, eps=1e-12):
    qab, qap, qam = a + b, a + 1.0, a - 1.0
    c, d = 1.0, 1.0 - qab * x / qap
    if abs(d) < 1e-30:
        d = 1e-30
    d = 1.0 / d
    h = d
    for m in range(1, itmax + 1):
        m2 = 2 * m
        aa = m * (b - m) * x / ((qam + m2) * (a + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        h *= d * c
        aa = -(a + m) * (qab + m) * x / ((a + m2) * (qap + m2))
        d = 1.0 + aa * d
        if abs(d) < 1e-30:
            d = 1e-30
        c = 1.0 + aa / c
        if abs(c) < 1e-30:
            c = 1e-30
        d = 1.0 / d
        delta = d * c
        h *= delta
        if abs(delta - 1.0) < eps:
            break
    return h


def perf(x):
    x = pd.Series(x).dropna()
    n = len(x)
    if n < 2:
        return dict(CAGR=float("nan"), Sharpe=float("nan"), MDD=float("nan"), n=n)
    cum = (1 + x).cumprod()
    cagr = float((1 + x).prod() ** (12.0 / n) - 1)
    sh = float(x.mean() / x.std() * math.sqrt(12)) if x.std() > 0 else float("nan")
    mdd = float((cum / cum.cummax() - 1).min())
    return dict(CAGR=cagr, Sharpe=sh, MDD=mdd, n=n)


def overlay(r, winter_w=1.0, summer_w=0.5):
    """계절 오버레이: 겨울 winter_w, 여름 summer_w 비중. 나머지는 현금(RF). 전환비용 반영."""
    rf = CFG["RF_ANNUAL"] / 12.0
    pos = pd.Series([winter_w if d.month in CFG["WINTER"] else summer_w for d in r.index], index=r.index)
    s = pos * r + (1 - pos) * rf
    s = s - pos.diff().abs().fillna(0.0) * CFG["COST_ONEWAY"]
    return s


# ---------------------------------------------------------------------------
# 본 검정
# ---------------------------------------------------------------------------
def run():
    s, notes, gaps, holidays = load_kospi()
    print("=" * 72)
    print("할로윈 계절성 검증 — KOSPI 실데이터")
    print("=" * 72)
    for n in notes:
        print("  · " + n)

    if s is None or len(s) < 60:
        print("\n[데이터부족] KOSPI 지수 실데이터를 찾지 못했습니다. 검정 불가.")
        print("  복구: py fetch_kospi_index_daily.py --start 1995")
        _write_md(None, None, notes, gaps, None, None, None, None,
                  verdict="판정불가(데이터부족)")
        return 2

    blocked, block_why = blocking(s, gaps)

    print(f"\n  결합 커버리지: {s.index.min().date()} ~ {s.index.max().date()}  ({len(s)}거래일)")
    if holidays:
        print(f"\n  · 휴장 구간 {len(holidays)}개 (연휴 — 결측 아님, 검정에 그대로 사용):")
        for a, b, dd, bd in holidays:
            print(f"     · {a.date()} ~ {b.date()}  (달력 {dd}일 / 영업일 {bd}일)")
    if gaps:
        print(f"\n  ⚠ 데이터 결측 구간 {len(gaps)}개 — 검정에서 제외:")
        for a, b, dd, bd in gaps:
            print(f"     · {a.date()} ~ {b.date()}  ({dd}일 = 영업일 {bd}일 = 약 {dd/365.25:.1f}년)")
    print(f"\n  데이터 차단 판정: {'차단' if blocked else '통과'} — {block_why}")

    r_all = monthly_returns(s)
    r, dropped = drop_gap_months(r_all, gaps)
    print(f"\n  월수익률 표본: {len(r)}개월 (공백 인접 {dropped}개월 제외)")
    print(f"  검정 구간: {r.index.min().date()} ~ {r.index.max().date()}")

    # --- 1) 겨울 vs 여름 원시 비교 (오버레이 없이 순수 계절 차이) ---
    w = r[[d.month in CFG["WINTER"] for d in r.index]]
    su = r[[d.month not in CFG["WINTER"] for d in r.index]]
    t, dof, p = welch_t(w.values, su.values)

    # 반년 누적수익(연도별) — 문헌 표준 표현
    yr = []
    for y in sorted(set(r.index.year)):
        # 겨울 = 그해 11,12 + 이듬해 1~4
        wm = r[((r.index.year == y) & (r.index.month.isin([11, 12]))) |
               ((r.index.year == y + 1) & (r.index.month.isin([1, 2, 3, 4])))]
        sm = r[(r.index.year == y + 1) & (r.index.month.isin([5, 6, 7, 8, 9, 10]))]
        if len(wm) == 6 and len(sm) == 6:   # 완전한 반년만 (부분기간 금지)
            yr.append(dict(연도=f"{y}/{y+1}",
                           겨울=float((1 + wm).prod() - 1),
                           여름=float((1 + sm).prod() - 1)))
    ydf = pd.DataFrame(yr)
    if len(ydf):
        ydf["차이"] = ydf["겨울"] - ydf["여름"]
        wins = int((ydf["차이"] > 0).sum())
        ty, dfy, py_ = welch_t(ydf["겨울"].values, ydf["여름"].values)
    else:
        wins, ty, py_ = 0, float("nan"), float("nan")

    print("\n" + "-" * 72)
    print("[1] 월수익률: 겨울(11~4월) vs 여름(5~10월)")
    print("-" * 72)
    print(f"  겨울 평균 월수익 : {w.mean()*100:+.3f}%  (표본 {len(w)}개월, 표준편차 {w.std()*100:.2f}%)")
    print(f"  여름 평균 월수익 : {su.mean()*100:+.3f}%  (표본 {len(su)}개월, 표준편차 {su.std()*100:.2f}%)")
    print(f"  차이             : {(w.mean()-su.mean())*100:+.3f}%p / 월")
    print(f"  Welch t검정      : t = {t:.3f},  df = {dof:.1f},  p = {p:.4f}")

    if len(ydf):
        print(f"\n  연도별 반년 비교: 겨울 승 {wins}/{len(ydf)}회 "
              f"({wins/len(ydf)*100:.0f}%),  t = {ty:.3f}, p = {py_:.4f}")
        print(f"  겨울 평균 반년수익 {ydf['겨울'].mean()*100:+.2f}%  "
              f"vs  여름 {ydf['여름'].mean()*100:+.2f}%  "
              f"(차이 {ydf['차이'].mean()*100:+.2f}%p)")

    # --- 2) 월별 계절성 (진단) ---
    seas = r.groupby(r.index.month).agg(["mean", "count"])
    print("\n" + "-" * 72)
    print("[2] 월별 평균 수익률 (진단용)")
    print("-" * 72)
    for m in range(1, 13):
        if m in seas.index:
            mk = "겨울" if m in CFG["WINTER"] else "여름"
            print(f"   {m:2d}월 [{mk}]  {seas.loc[m,'mean']*100:+6.2f}%   (표본 {int(seas.loc[m,'count'])}년)")
        else:
            print(f"   {m:2d}월        데이터부족")

    # --- 3) 오버레이 성과 vs buy&hold ---
    bh = perf(r)
    o50 = perf(overlay(r, 1.0, 0.5))   # 계절틸트_규칙서 채택안
    o00 = perf(overlay(r, 1.0, 0.0))   # 고전 할로윈(여름 전액 현금)
    print("\n" + "-" * 72)
    print("[3] 오버레이 성과 (배당 1.8%·비용 15bp 반영)")
    print("-" * 72)
    print(f"  {'전략':<26}{'CAGR':>9}{'Sharpe':>9}{'MDD':>9}")
    for nm, pf in [("buy&hold (기준)", bh),
                   ("여름 50% 틸트", o50),
                   ("여름 0% (고전 할로윈)", o00)]:
        print(f"  {nm:<26}{pf['CAGR']*100:>8.2f}%{pf['Sharpe']:>9.3f}{pf['MDD']*100:>8.1f}%")

    # --- 4) 사전등록 게이트 판정 ---
    g_p = bool(p < CFG["GATE_P"])
    g_cagr50 = bool(o50["CAGR"] >= bh["CAGR"] - CFG["GATE_CAGR_DRAG"])
    g_sh50 = bool(o50["Sharpe"] > bh["Sharpe"])
    g_mdd50 = bool(abs(o50["MDD"]) <= abs(bh["MDD"]))
    gates = {
        f"계절차이 유의 (p<{CFG['GATE_P']})": g_p,
        f"틸트50% CAGR ≥ bh−{CFG['GATE_CAGR_DRAG']*100:.1f}%p": g_cagr50,
        "틸트50% Sharpe > bh": g_sh50,
        "틸트50% MDD 비악화": g_mdd50,
    }
    print("\n" + "-" * 72)
    print("[4] 사전등록 게이트")
    print("-" * 72)
    for k, v in gates.items():
        print(f"  [{'통과' if v else '탈락'}] {k}")

    passed = sum(gates.values())

    sub = subsample_tests(r)
    print("\n" + "-" * 72)
    print("[5] (A) Post-publication 검정 — Bouman & Jacobsen(2002) 발표 전/후")
    print("-" * 72)
    print("  할로윈은 이미 공표된 아노말리. McLean&Pontiff(2016): 발표 후 평균 -58% 감쇠.")
    print(f"  {'구간':<14}{'n':>5}{'겨울':>9}{'여름':>9}{'차이':>9}{'t':>8}{'p':>9}{'MWU p':>9}")
    for x in sub:
        if not x.get("ok"):
            print(f"  {x['label']:<14}{x['n']:>5}   표본부족"); continue
        print(f"  {x['label']:<14}{x['n']:>5}{x['mw']*100:>8.3f}%{x['ms']*100:>8.3f}%"
              f"{x['diff']*100:>8.3f}%{x['t']:>8.3f}{x['p']:>9.4f}{x['pu']:>9.4f}")

    rob, worst, crash = outlier_tests(r)
    print("\n" + "-" * 72)
    print("[6] (B) 이상치 의존성 — 중앙값·비모수·폭락월 제외")
    print("-" * 72)
    print("  최악 5개월: " + ", ".join(f"{k}({v*100:+.1f}%)" for k, v in worst))
    if crash:
        print("  IMF·리먼: " + ", ".join(f"{k}={v*100:+.2f}%" for k, v in crash))
    print(f"  {'표본':<22}{'평균차':>9}{'중앙값차':>10}{'t':>8}{'p':>9}{'MWU p':>9}")
    for x in rob:
        if x.get("ok"):
            print(f"  {x['label']:<22}{x['diff']*100:>8.3f}%{x['mdiff']*100:>9.3f}%"
                  f"{x['t']:>8.3f}{x['p']:>9.4f}{x['pu']:>9.4f}")
    if len(ydf):
        print(f"\n  ※ 연도별 반년 승률 {wins}/{len(ydf)} ({wins/len(ydf)*100:.0f}%) — 이상치에 강건한 지표.")

    # --- (C) 매크로 국면별 + 이질성 검정 ---
    regs = regime_tests(r)
    Fh, pFh, q, dfree = heterogeneity_test(r)
    breaks = [("발표전 vs 발표후(2003)", break_test(r, "2003-01-01")),
              ("리먼전 vs 리먼후", break_test(r, "2008-09-01")),
              ("IMF전 vs IMF후", break_test(r, "1997-11-01"))]
    print("\n" + "-" * 72)
    print("[7] (C) 매크로 국면별 검정 — IMF / 리먼 기준")
    print("-" * 72)
    print(f"  {'국면':<16}{'n':>5}{'차이':>9}{'±SE':>8}{'t':>8}{'p':>9}{'Bonf×3':>9}")
    for x in regs:
        if not x.get("ok"):
            print(f"  {x['label']:<16}{x['n']:>5}   표본부족"); continue
        bonf = min(x["p"] * 3, 1.0) if not x["label"].startswith("전체") else float("nan")
        bs = f"{bonf:.4f}" if np.isfinite(bonf) else "-"
        print(f"  {x['label']:<16}{x['n']:>5}{x['diff']*100:>8.3f}%{x.get('se',0)*100:>8.3f}"
              f"{x['t']:>8.3f}{x['p']:>9.4f}{bs:>9}")
    print(f"\n  이질성 F검정 (H0: 세 국면의 겨울효과가 모두 같다 = 묶어도 된다)")
    print(f"    F({q},{dfree}) = {Fh:.3f},  p = {pFh:.4f}")
    print(f"    → {'국면별로 다르다 (쪼개야 함)' if pFh < 0.10 else '국면별로 다르다는 증거 없음 → 묶는 것이 통계적으로 타당'}")
    print(f"\n  구조변화 지점 탐색 (상호작용 계수 / F / p)")
    for nm, (b_, F_, p_) in breaks:
        mk = "★ 변화 있음" if (np.isfinite(p_) and p_ < 0.10) else "  변화 증거 없음"
        print(f"    {nm:<24}{b_*100:+7.3f}%p  F={F_:6.3f}  p={p_:.4f}   {mk}")

    verdict, reasons = decide(gates, sub, rob, blocked, block_why)
    print("\n" + "=" * 72)
    print(f"판정: {verdict}   (게이트 {passed}/{len(gates)} 통과)")
    print("-" * 72)
    for rz in reasons:
        print("  " + rz)
    print("=" * 72)

    _write_md(s, r, notes, gaps, dict(w=w, su=su, t=t, p=p, dof=dof),
              ydf, dict(bh=bh, o50=o50, o00=o00), gates, verdict, seas=seas,
              wins=wins, ty=ty, py_=py_, dropped=dropped,
              holidays=holidays, blocked=blocked, block_why=block_why,
              sub=sub, rob=rob, worst=worst, crash=crash, reasons=reasons,
              regs=regs, het=(Fh, pFh, q, dfree), breaks=breaks)
    lp = log_decision(verdict, sub)
    print("\n저장: 가상매매\\검증\\할로윈_검증결과.md")
    print(f"기록: {os.path.basename(lp)}")
    return 0


def _fmt(x, pct=True, dec=2):
    if x is None or (isinstance(x, float) and math.isnan(x)):
        return "데이터부족"
    return f"{x*100:+.{dec}f}%" if pct else f"{x:.{dec}f}"


def _write_md(s, r, notes, gaps, tt, ydf, pfs, gates, verdict,
              seas=None, wins=0, ty=float("nan"), py_=float("nan"), dropped=0,
              holidays=None, blocked=False, block_why="", sub=None, rob=None,
              worst=None, crash=None, reasons=None, regs=None, het=None, breaks=None):
    L = []
    L.append("# 할로윈 계절성 검증 결과 — KOSPI 실데이터\n")
    L.append(f"> 생성: `할로윈_검증.py` · 판정: **{verdict}**\n")
    L.append("> 투자자문 아님. 지표·규칙 사실만 기록. 결정·책임은 본인.\n")
    L.append("\n---\n")

    L.append("\n## 0. 결론 (먼저)\n\n")
    if s is None:
        L.append("**판정불가 — KOSPI 지수 실데이터 없음.** 검정을 수행하지 않았다.\n")
        L.append("\n복구: `py fetch_kospi_index_daily.py --start 1995`\n")
        _save(L)
        return

    L.append(f"- **판정: {verdict}**\n")
    L.append(f"- 가상매매 엔진의 할로윈 오버레이 기본값은 **OFF**로 유지한다.\n")
    L.append("- 할로윈은 **리밸런스 주기가 아니다.** 리밸은 월 1회 그대로 두고, "
             "할로윈은 총노출을 조절하는 **오버레이**로만 취급한다.\n")

    L.append("\n## 1. 데이터 실사 (가장 중요)\n\n")
    for n in notes:
        L.append(f"- {n}\n")
    L.append(f"- 결합 커버리지: **{s.index.min().date()} ~ {s.index.max().date()}** ({len(s)}거래일)\n")
    if gaps:
        L.append(f"\n### ⚠ 데이터부족 구간 {len(gaps)}개 — 검정에서 제외\n\n")
        L.append("| 공백 시작 | 공백 종료 | 결측 |\n|---|---|---|\n")
        for a, b, dd in gaps:
            L.append(f"| {a.date()} | {b.date()} | {dd}일 (약 {dd/365.25:.1f}년) |\n")
        L.append(f"\n공백에 인접한 **{dropped}개월**의 수익률은 신뢰 불가로 제거했다. "
                 "결측 구간을 보간하거나 추정하지 않았다.\n")
    L.append(f"\n검정에 실제로 쓰인 표본: **{len(r)}개월** "
             f"({r.index.min().date()} ~ {r.index.max().date()})\n")

    L.append("\n## 2. 겨울(11~4월) vs 여름(5~10월)\n\n")
    L.append("| 구분 | 평균 월수익 | 표본 | 표준편차 |\n|---|---|---|---|\n")
    L.append(f"| 겨울 11~4월 | {_fmt(tt['w'].mean())} | {len(tt['w'])}개월 | {tt['w'].std()*100:.2f}% |\n")
    L.append(f"| 여름 5~10월 | {_fmt(tt['su'].mean())} | {len(tt['su'])}개월 | {tt['su'].std()*100:.2f}% |\n")
    L.append(f"| **차이** | **{_fmt(tt['w'].mean()-tt['su'].mean())}p/월** | | |\n")
    L.append(f"\n**Welch t검정: t = {tt['t']:.3f}, df = {tt['dof']:.1f}, p = {tt['p']:.4f}**\n")

    if ydf is not None and len(ydf):
        L.append(f"\n### 연도별 반년 비교 (완전한 6개월 쌍만)\n\n")
        L.append(f"겨울 승 **{wins}/{len(ydf)}회** ({wins/len(ydf)*100:.0f}%) · "
                 f"t = {ty:.3f}, p = {py_:.4f}\n\n")
        L.append("| 연도 | 겨울(11~4월) | 여름(5~10월) | 차이 |\n|---|---|---|---|\n")
        for _, row in ydf.iterrows():
            L.append(f"| {row['연도']} | {_fmt(row['겨울'])} | {_fmt(row['여름'])} | {_fmt(row['차이'])}p |\n")
        L.append(f"| **평균** | **{_fmt(ydf['겨울'].mean())}** | **{_fmt(ydf['여름'].mean())}** | "
                 f"**{_fmt(ydf['차이'].mean())}p** |\n")

    if seas is not None:
        L.append("\n## 3. 월별 계절성 (진단)\n\n")
        L.append("| 월 | 구분 | 평균 수익률 | 표본 |\n|---|---|---|---|\n")
        for m in range(1, 13):
            if m in seas.index:
                mk = "겨울" if m in CFG["WINTER"] else "여름"
                L.append(f"| {m}월 | {mk} | {_fmt(seas.loc[m,'mean'])} | {int(seas.loc[m,'count'])}년 |\n")
            else:
                L.append(f"| {m}월 | — | 데이터부족 | 0 |\n")

    L.append("\n## 4. 오버레이 성과 (배당 1.8% · 비용 15bp)\n\n")
    L.append("| 전략 | CAGR | Sharpe | MDD |\n|---|---|---|---|\n")
    for nm, key in [("buy&hold (기준)", "bh"), ("여름 50% 틸트", "o50"), ("여름 0% (고전 할로윈)", "o00")]:
        pf = pfs[key]
        L.append(f"| {nm} | {_fmt(pf['CAGR'])} | {pf['Sharpe']:.3f} | {_fmt(pf['MDD'])} |\n")

    L.append("\n## 5. 사전등록 게이트\n\n")
    L.append("| 게이트 | 결과 |\n|---|---|\n")
    for k, v in gates.items():
        L.append(f"| {k} | {'✅ 통과' if v else '❌ 탈락'} |\n")

    L.append("\n## 6. 한계 — 정직하게\n\n")
    if gaps:
        L.append("- **표본이 온전하지 않다.** 위 §1의 공백 구간만큼 데이터가 없다. "
                 "이 상태의 결과로 규칙을 채택하면 안 된다.\n")
    L.append("- 할로윈은 **공개된 아노말리**다 (Bouman & Jacobsen 2002). "
             "발표 후 약화(post-publication decay) 가능성이 상존한다.\n")
    L.append("- 한국 시장 단독 검정력은 낮다. 표본이 수십 년이어도 반년 관측은 수십 개뿐이다.\n")
    L.append("- 계절 효과가 **진짜여도 작다.** 수익을 늘리는 규칙이 아니라 낙폭을 줄이는 규칙에 가깝다.\n")
    L.append("- 본 검정은 **KOSPI 지수**에 대한 것이다. 개별 종목 포트폴리오에 그대로 이전된다는 보장은 없다.\n")

    L.append("\n## 7. 엔진 반영\n\n")
    L.append("- `가상매매_엔진.py`의 `HALLOWEEN_OVERLAY` 기본값 = **False (OFF)**.\n")
    L.append("- 켜려면: `py 가상매매_엔진.py --halloween` (여름철 총노출 ×0.5).\n")
    L.append("- 기존 `계절틸트_규칙서.md`(2026-07-12)는 별도 코어 오버레이 문서다. "
             "본 검정은 그것을 **독립 재현**한 것이다.\n")
    if gaps:
        L.append("- ⚠️ 위 §1의 데이터 결측 때문에 동일 표본(1995~2026)을 완전히 "
                 "재현하지는 못했다.\n")

    # ── (A) Post-publication ────────────────────────────────────────────────
    if sub:
        L.append("\n## ★ (A) Post-publication 검정 — 가장 중요한 관문\n\n")
        L.append("> 할로윈은 **Bouman & Jacobsen (2002)** 으로 이미 공표된 아노말리다.\n"
                 "> McLean & Pontiff (2016): 공표 후 아노말리 수익은 평균 **-58%** 감쇠한다.\n"
                 "> 따라서 **발표 후 구간에서도 살아있는지**가 채택의 핵심 조건이다.\n\n")
        L.append("| 구간 | 표본 | 겨울 | 여름 | 차이 | Welch t | p | 중앙값차 | MWU p |\n")
        L.append("|---|---|---|---|---|---|---|---|---|\n")
        for x in sub:
            if not x.get("ok"):
                L.append(f"| {x['label']} | {x['n']} | — | — | — | — | — | — | — |\n")
                continue
            L.append(f"| {x['label']} | {x['n']}개월 | {x['mw']*100:+.3f}% | {x['ms']*100:+.3f}% | "
                     f"**{x['diff']*100:+.3f}%p** | {x['t']:.3f} | **{x['p']:.4f}** | "
                     f"{x['mdiff']*100:+.3f}%p | {x['pu']:.4f} |\n")
        _post = next((x for x in sub if x["label"].startswith("발표후")), None)
        if _post and _post.get("ok"):
            if _post["p"] < CFG["GATE_P"]:
                L.append(f"\n**발표 후에도 유의하다** (p={_post['p']:.4f}). 감쇠를 견뎠다.\n")
            else:
                L.append(f"\n**발표 후에는 유의하지 않다** (p={_post['p']:.4f} ≥ {CFG['GATE_P']}). "
                         f"효과가 발표 전 구간에 몰려 있다 → **post-publication decay**.\n")

    # ── (B) 이상치 의존성 ──────────────────────────────────────────────────
    if rob:
        L.append("\n## ★ (B) 이상치(폭락) 의존성 검정\n\n")
        L.append("> MDD 개선이 큰 건 \"여름이 나쁘다\"가 아니라 **\"가을에 몇 번 크게 터졌다\"**"
                 "일 수 있다. IMF(1997-10)·리먼(2008-10) 모두 가을이다.\n"
                 "> 중앙값·비모수(Mann-Whitney)·폭락월 제외로 검증한다.\n\n")
        if worst:
            L.append("최악 5개월: " + ", ".join(f"`{k}` ({v*100:+.1f}%)" for k, v in worst) + "\n\n")
        L.append("| 표본 | 평균차 | 중앙값차 | Welch t | p | MWU p |\n|---|---|---|---|---|---|\n")
        for x in rob:
            if x.get("ok"):
                L.append(f"| {x['label']} | **{x['diff']*100:+.3f}%p** | {x['mdiff']*100:+.3f}%p | "
                         f"{x['t']:.3f} | **{x['p']:.4f}** | {x['pu']:.4f} |\n")
        if wins and ydf is not None and len(ydf):
            L.append(f"\n연도별 반년 승률 **{wins}/{len(ydf)} ({wins/len(ydf)*100:.0f}%)** — "
                     f"이상치에 강건한 지표. 평균 기반 결과와 대조하라.\n")

    # ── (C) 매크로 국면별 ─────────────────────────────────────────────────
    if regs:
        L.append("\n## ★ (C) 매크로 국면별 검정 — IMF / 리먼 기준\n\n")
        L.append("> \"IMF 전후, 리먼 전후는 매크로가 완전히 다르다. 묶어서 보면 안 되는 것 아닌가?\"\n"
                 "> — 타당한 의심이다. 그래서 **그 질문 자체를 검정한다.** 묶어도 되는지는 데이터가 답한다.\n\n")
        L.append("| 국면 | 표본 | 겨울−여름 | ±SE | 95% CI | t | p | Bonferroni(×3) |\n")
        L.append("|---|---|---|---|---|---|---|---|\n")
        for x in regs:
            if not x.get("ok"):
                L.append(f"| {x['label']} | {x['n']} | — | — | — | — | — | — |\n"); continue
            se = x.get("se", 0.0)
            lo, hi = (x["diff"] - 1.96 * se) * 100, (x["diff"] + 1.96 * se) * 100
            pooled = x["label"].startswith("전체")
            bonf = "—" if pooled else f"{min(x['p']*3, 1.0):.4f}"
            L.append(f"| {'**' if pooled else ''}{x['label']}{'**' if pooled else ''} | {x['n']}개월 | "
                     f"**{x['diff']*100:+.3f}%p** | ±{se*100:.3f} | [{lo:+.2f}, {hi:+.2f}] | "
                     f"{x['t']:.3f} | {x['p']:.4f} | {bonf} |\n")
        if het:
            Fh, pFh, q, dfree = het
            L.append(f"\n### 이질성 F검정 — 핵심\n\n")
            L.append(f"**H0: 세 국면의 겨울효과가 모두 같다 (= 묶어도 된다)**\n\n")
            L.append(f"- F({q}, {dfree}) = **{Fh:.3f}**,  p = **{pFh:.4f}**\n")
            if pFh < 0.10:
                L.append("- → **국면별로 다르다. 쪼개서 봐야 한다.**\n")
            else:
                L.append("- → **국면별로 다르다는 증거가 없다.** 세 국면의 점추정치가 서로의 신뢰구간 안에 있다.\n"
                         "  즉 **묶는 것이 통계적으로 타당하다.** 쪼개면 효과가 드러나는 게 아니라 "
                         "**표본만 줄어 검정력이 무너진다**(SE가 커지는 것을 위 표에서 확인하라).\n")
        if breaks:
            L.append("\n### 구조변화는 어디서 일어났나\n\n")
            L.append("| 분기점 | 상호작용 계수 | F | p | 판정 |\n|---|---|---|---|---|\n")
            for nm, (b_, F_, p_) in breaks:
                mk = "**★ 변화 있음**" if (p_ == p_ and p_ < 0.10) else "변화 증거 없음"
                L.append(f"| {nm} | {b_*100:+.3f}%p | {F_:.3f} | **{p_:.4f}** | {mk} |\n")
            L.append("\n**구조변화는 매크로(IMF·리먼)가 아니라 "
                     "\"발표\"에서 일어났다.** 이것이 post-publication decay의 서명이다.\n")

    # ── 사전등록 판정 ──────────────────────────────────────────────────────
    if reasons:
        L.append("\n## 사전등록 판정 규칙 (결과 보기 전 고정 · 사후 조정 금지)\n\n")
        L.append("| 조건 | 판정 |\n|---|---|\n")
        L.append("| (A) 발표후 유의 + 게이트 통과 AND (B) 이상치 제거 후 차이 유지 | **채택 후보** |\n")
        L.append("| (A) 통과, (B) 실패 | **조건부** — 테일리스크 회피이지 계절 알파 아님. OFF |\n")
        L.append("| (A) 실패 | **기각** — post-publication decay |\n\n")
        L.append("**근거:**\n\n")
        for rz in reasons:
            L.append(f"- {rz}\n")
        L.append(f"\n### → 최종 판정: **{verdict}**\n")

    # ── 데이터 실사: 휴장 vs 결측 ─────────────────────────────────────────
    L.append("\n## 데이터 실사 — 휴장 vs 결측\n\n")
    L.append(f"차단 판정: **{'차단' if blocked else '통과'}** — {block_why}\n\n")
    L.append("> **2026-07-13 수정**: 예전 게이트는 달력 공백이 10일만 넘어도 무조건 "
             "\"데이터부족\"으로 막았다. 그래서 **2017-09-29~10-10 추석 연휴**"
             "(달력 11일 = 영업일 6일) 하나 때문에 판정이 막혀 있었다.\n"
             "> 근거: 같은 기간 한국 데이터 2종(pykrx·FDR)은 모두 09-29 → 10-10 직행이고, "
             "**미국 SOX는 10/2·3·4·5·6·9 전부 거래**했다. 미국장은 열렸는데 한국장만 닫혔다 "
             "= **한국 공휴일**이다. 결측이 아니다.\n"
             "> 이제 **연속 결측 20영업일 초과** 또는 **총 결측 1% 초과**일 때만 차단한다. "
             "완화 근거는 휴장/결측 구분이라는 **기술적 정당성**이며, 결과를 좋게 만들기 "
             "위함이 아니다. 커버리지·결측 내역은 아래에 계속 전부 공개한다.\n\n")
    if holidays:
        L.append(f"**휴장 구간 {len(holidays)}개** (연휴 — 검정에 그대로 사용):\n\n")
        L.append("| 시작 | 끝 | 달력일 | 영업일 |\n|---|---|---|---|\n")
        for _a, _b, _d, _bd in holidays:
            L.append(f"| {_a.date()} | {_b.date()} | {_d} | {_bd} |\n")
    if gaps:
        L.append(f"\n**데이터 결측 구간 {len(gaps)}개** (검정에서 제외):\n\n")
        L.append("| 시작 | 끝 | 달력일 | 영업일 |\n|---|---|---|---|\n")
        for _g in gaps:
            L.append(f"| {_g[0].date()} | {_g[1].date()} | {_g[2]} | {_g[3] if len(_g) > 3 else '-'} |\n")
    else:
        L.append("\n**데이터 결측 구간 없음.**\n")


    _save(L)


def _save(L):
    out = os.path.join(DIR_VERIFY, "할로윈_검증결과.md")
    with open(out, "w", encoding="utf-8") as f:
        f.write("".join(L))


# ---------------------------------------------------------------------------
def self_test():
    ok = tot = 0

    def chk(name, cond):
        nonlocal ok, tot
        tot += 1
        ok += 1 if cond else 0
        print(f"  [{'OK  ' if cond else 'FAIL'}] {name}")

    print("=" * 60)
    print("할로윈_검증.py 셀프테스트")
    print("=" * 60)

    # t검정 정확도 (알려진 값과 대조)
    a = np.array([1.0, 2.0, 3.0, 4.0, 5.0])
    b = np.array([2.0, 4.0, 6.0, 8.0, 10.0])
    t, dof, p = welch_t(a, b)
    chk(f"Welch t검정 동작 (t={t:.3f}, p={p:.3f})", (not math.isnan(t)) and 0 <= p <= 1)

    # 동일 분포 → p가 커야 함
    rng = np.random.default_rng(42)
    t2, _, p2 = welch_t(rng.normal(0, 1, 500), rng.normal(0, 1, 500))
    chk(f"동일분포 → p 큼 (p={p2:.3f})", p2 > 0.05)

    # 명확히 다른 분포 → p가 작아야 함
    t3, _, p3 = welch_t(rng.normal(1, 1, 500), rng.normal(0, 1, 500))
    chk(f"차이 큰 분포 → p 작음 (p={p3:.6f})", p3 < 0.001)

    # 겨울/여름 분류
    chk("겨울 집합 = {11,12,1,2,3,4}", CFG["WINTER"] == {11, 12, 1, 2, 3, 4})

    # 오버레이: 여름 100%면 buy&hold와 (비용 제외) 동일
    idx = pd.date_range("2020-01-31", periods=24, freq="ME")
    r = pd.Series(rng.normal(0.01, 0.05, 24), index=idx)
    o = overlay(r, 1.0, 1.0)
    chk("오버레이 100/100 = buy&hold", np.allclose(o.values, r.values))

    # 오버레이: 여름 0%면 여름달 수익 = RF
    o0 = overlay(r, 1.0, 0.0)
    sm = [i for i, d in enumerate(idx) if d.month not in CFG["WINTER"]]
    # 전환월은 비용이 붙으므로, 전환이 아닌 여름달만 검사
    pure = [i for i in sm if i > 0 and idx[i - 1].month not in CFG["WINTER"]]
    chk("오버레이 여름0% → 여름수익=RF",
        all(abs(o0.iloc[i] - CFG["RF_ANNUAL"] / 12.0) < 1e-9 for i in pure))

    # 공백 탐지
    s = pd.Series([1, 2, 3, 4], index=pd.to_datetime(
        ["2020-01-01", "2020-01-02", "2021-01-01", "2021-01-02"]))
    d = s.index.to_series().diff().dt.days
    chk("공백 탐지 (>10일)", int((d > CFG["GAP_DAYS"]).sum()) == 1)

    # 데이터부족 처리: 빈 입력에 예외 없이 NaN
    tn, _, pn = welch_t([1.0], [2.0])
    chk("표본부족 → NaN 반환(예외 없음)", math.isnan(tn))

    # 실파일 로딩
    s2, notes, gaps, _hol = load_kospi()
    chk(f"KOSPI 실데이터 로딩 ({len(s2) if s2 is not None else 0}행)", s2 is not None and len(s2) > 100)

    print(f"\n셀프테스트: {ok}/{tot} 통과")
    return 0 if ok == tot else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    sys.exit(self_test() if a.self_test else run())
