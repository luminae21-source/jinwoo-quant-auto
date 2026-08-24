#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
운용사양_백테.py — §8-2 "검증한 모델 = 운용하는 모델" 로 좁히기

── 먼저: 백서 B-1c 표가 부정확하다 (2026-07-27 확인) ──────────────
백서 부록 B-1c는 운용 모델을 "최대 15종 · **리스크 1% 사이징**"이라고 적었다.
`진우_통합한도.json`(SSOT)을 읽으면 그건 **재량(위성) 트랙**의 규칙이다.

    "본체_v372": { "weighting": "동일가중→종목캡→섹터캡→정규화",
                   "stock_cap_pct": 15.0, "sector_cap_pct": 35.0,
                   "ma200_defense": true, "rebalance": "월간(첫 영업일)" }
    "재량_사이징": { "risk_per_trade_pct": 1.0, "portfolio_heat_cap_pct": 6.0 }
    "재량_집중한도": { "동시보유_최대": 7, "동시보유_권장": 5 }
    "집행_riskguard": { "max_positions": 15 }   ← 계좌 전체 한도(본체+재량)

**본체는 동일가중이다.** 검증본과 가중 방식이 같다. 리스크 1% 사이징은 위성 트랙 규칙이다.
→ 진짜 미검증 격차는 **가중이 아니라 N(종목 수)** 이다.
   RiskGuard 계좌 한도 15종에서 재량이 최대 7종을 쓰므로 **본체는 대략 8~15종**이다.
   검증은 top30으로 했다. **N을 절반 이하로 줄였을 때 무슨 일이 나는지 아무도 안 재봤다.**

── 이 스크립트가 재는 것 ──────────────────────────────────────────
  ① N 스윕 (30·20·15·12·10·8·5) — 동일가중 + 종목캡 15% + 정규화 + MA200 방어
  ② **CAGR 신뢰구간 (정상 블록 부트스트랩)** — N을 줄이면 표본이 얇아져 점추정이 흔들린다.
     월수익률 시계열을 평균 12개월 블록으로 재표집해 B회 → CAGR 분포(5%~95%).
     **점추정 하나로 "15종이 30종보다 낫다/못하다"고 말하지 않기 위한 장치다.**

     ⚠️ 초안에서는 "상위 2N 풀에서 매달 N개 무작위 추출"로 짰다가 폐기했다 —
     매달 새로 뽑으면 회전율이 2.7x → 6x로 폭증해서 **'어느 N개냐'가 아니라 '회전 비용'을 재게 된다.**
     측정하려던 것과 다른 것을 재는 설계였다.
  ③ 비용 3종 시나리오 (비용모델.py SSOT)

── 재보지 못하는 것 (정직하게 남긴다) ──────────────────────────────
  · **섹터캡 35%** — 섹터 매핑이 현재 948종목뿐. 30년 이력 없음.
  · **등급이탈 청산** — 과거 등급 시계열 없음.
  · **실행 시차** — 사양은 "월간 첫 영업일, 다음영업일 시가/종가"인데
    월봉으로는 월말 종가 체결로 근사한다. 며칠치 드리프트는 미반영.
  · **재량 트랙** — 본 백테는 본체만. 재량은 forward 실측 대상(§8-6).

사용:
    py 운용사양_백테.py                       # 전체 (N스윕 + 분포)
    py 운용사양_백테.py --boot 200 --cost 보수
    py 운용사양_백테.py --no-boot             # 분포 생략(빠름)

⚠️ 검증용 · 실현손익 아님 · 투자자문 아님 · 책임 본인
"""
import argparse
import glob
import hashlib
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
try:
    from 비용모델 import roundtrip as _rt, SCENARIOS as _SC
except Exception:
    _SC = ("낙관", "기준", "보수")
    _rt = lambda s="기준": {"낙관": 0.0025, "기준": 0.00559, "보수": 0.01511}[s]

STOCK_CAP = 0.15          # 진우_통합한도.json · 본체_v372.stock_cap_pct


def _selfmd5():
    """이 스크립트 자신의 md5. 결과 파일에 박아서 '어느 버전이 만들었나'를 남긴다."""
    try:
        return hashlib.md5(open(os.path.abspath(__file__), "rb").read()).hexdigest()
    except OSError:
        return "?"


def find(name):
    for b in (ROOT, os.getcwd()):
        h = [x for x in glob.glob(os.path.join(b, "**", name), recursive=True)
             if not any(s in x for s in ("_백업", "_보관", "_archive", "__pycache__"))]
        if h:
            return sorted(h, key=len)[0]
    return None


# ── 가격 원천 (2026-07-28 이중창 실험용으로 선택 가능하게 확장) ──────────
#  full : _월봉종가캐시_*_full.csv  ← 기존 기본값. B-1h·B-1i 숫자가 나온 그 패널.
#  kis  : 월봉_KIS_adj_v1_2026-07-28.csv + _월봉_KIS_adj_2016.csv
#         (KIS 수정주가 전수. 2011~2026 커버리지 100.00% · B-1o ⑤)
#  ⚠️ 기본값은 full 이다. 원천을 바꾸는 건 **다른 실험**이므로 명시해야 바뀐다.
PX_SOURCES = {
    "full": ["_월봉종가캐시_KOSPI_full.csv", "_월봉종가캐시_KOSDAQ_full.csv"],
    "kis":  ["월봉_KIS_adj_v1_2026-07-28.csv", "_월봉_KIS_adj_2016.csv"],
}


def load_masks(paths):
    """마스크 CSV(code,ym,...) 들을 (code,ym) 집합으로. 없으면 빈 집합."""
    keys = set()
    for nm in paths:
        p = find(nm) or (nm if os.path.exists(nm) else None)
        if not p:
            print(f"  ⚠️ 마스크 파일 없음 — 건너뜀: {nm}")
            continue
        d = pd.read_csv(p, dtype={"code": str}, encoding="utf-8-sig")
        d["code"] = d["code"].str.zfill(6)
        n0 = len(keys)
        keys |= set(zip(d["code"], d["ym"]))
        print(f"  마스크 {os.path.basename(p)}: {len(d):,}행 → 누적 {len(keys):,}키 (+{len(keys)-n0:,})")
    return keys


def apply_mask(PX, keys):
    """마스크된 (code,ym) 을 NaN 으로. pct_change 전에 해야 수익률 사슬이 끊긴다."""
    if not keys:
        return PX, 0
    n = 0
    cols = set(PX.columns)
    per_col = {}
    for c, y in keys:
        if c in cols:
            per_col.setdefault(c, []).append(y)
    for c, yms in per_col.items():
        sel = PX.index.intersection(yms)
        if len(sel):
            n += int(PX.loc[sel, c].notna().sum())
            PX.loc[sel, c] = np.nan
    return PX, n


def load_px(source="full", masks=()):
    fr = []
    for nm in PX_SOURCES[source]:
        p = find(nm)
        if p is None:
            if source == "full" and "KOSPI" in nm:
                p = find("_월봉종가캐시_KOSPI.csv")
            if p is None:
                sys.exit(f"가격 파일을 못 찾음: {nm}")
        d = pd.read_csv(p, dtype={"code": str}, encoding="utf-8-sig")
        d["code"] = d["code"].str.zfill(6)
        fr.append(d[["code", "ym", "close"]])
        print(f"  가격: {os.path.basename(p)} ({d.code.nunique():,}종목 {len(d):,}행)")
    PX = (pd.concat(fr, ignore_index=True)
          .pivot_table(index="ym", columns="code", values="close", aggfunc="last").sort_index())
    PX, nmask = apply_mask(PX, load_masks(masks))
    if masks:
        tot = int(PX.notna().sum().sum()) + nmask
        print(f"  마스크 적용: {nmask:,}셀 결측화 ({nmask*100.0/max(tot,1):.3f}%)")
    return PX


def load_mcap():
    d = pd.read_csv(find("종목시총_30년.csv"), dtype={"code": str})
    d.columns = [c.strip().lstrip("﻿") for c in d.columns]
    d["code"] = d["code"].str.zfill(6)
    d["ym"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m")
    return d.pivot_table(index="ym", columns="code", values="mcap", aggfunc="last")


def load_div_pivot():
    """종목재무_KRX_*.csv 의 DIV(배당수익률 %) → ym×code 피벗. (2026-08-10, #75)

    ⚠️ 트레일링 근사다: KRX DIV = 직전 확정 DPS ÷ 현재가. 올해 받을 배당이 아니라
    작년 배당 기준이라 배당 삭감/증액을 1년 늦게 반영한다. FnGuide 실배당 수령 시 교체.
    """
    fr = []
    for mkt in ("KOSPI", "KOSDAQ"):
        p2 = find(f"종목재무_KRX_{mkt}.csv")
        if not p2:
            continue
        d = pd.read_csv(p2, dtype={"code": str}, encoding="utf-8-sig")
        d.columns = [str(c).strip().lstrip("\ufeff") for c in d.columns]
        d["code"] = d["code"].str.zfill(6)
        d["ym"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m")
        fr.append(d[["ym", "code", "DIV"]])
    if not fr:
        return None
    z = pd.concat(fr, ignore_index=True)
    z["DIV"] = pd.to_numeric(z["DIV"], errors="coerce").clip(0, 30)
    return z.pivot_table(index="ym", columns="code", values="DIV", aggfunc="last")


def load_index_monthly(path):
    """지수 CSV → 월말 종가 Series(index=ym). date/close 또는 ym/close 헤더 자동 인식."""
    d = pd.read_csv(path, encoding="utf-8-sig")
    d.columns = [str(c).strip().lstrip("\ufeff") for c in d.columns]
    low = {c.lower(): c for c in d.columns}
    ccol = low.get("close") or ("종가" if "종가" in d.columns else None)
    if ccol is None:
        sys.exit(f"⛔ 지수 파일에 close/종가 컬럼이 없음: {path}")
    if "ym" in low:
        s = d.set_index(low["ym"])[ccol]
    else:
        dcol = low.get("date") or ("날짜" if "날짜" in d.columns else d.columns[0])
        d["_ym"] = pd.to_datetime(d[dcol]).dt.strftime("%Y-%m")
        s = d.groupby("_ym")[ccol].last()
    return pd.to_numeric(s, errors="coerce").dropna().sort_index()


def load_defense(idx):
    p = find("kospi_index_daily.csv")
    d = pd.read_csv(p, parse_dates=["Date"]).set_index("Date").sort_index()
    me = d["Close"].resample("ME").last()
    me.index = me.index.strftime("%Y-%m")
    above = (me >= me.rolling(10).mean()).shift(1)
    return above.reindex(idx), me


def capped_equal_weights(n):
    """동일가중 → 종목캡 15% → 정규화. N<7이면 캡이 물린다."""
    w = np.full(n, 1.0 / n)
    if w[0] <= STOCK_CAP:
        return w
    w = np.minimum(w, STOCK_CAP)
    return w / w.sum()


def stats(r):
    r = pd.Series(r).dropna()
    if len(r) < 12:
        return dict(cagr=np.nan, sharpe=np.nan, mdd=np.nan, worst=np.nan)
    eq = (1 + r).cumprod()
    return dict(cagr=(eq.iloc[-1] ** (12 / len(r)) - 1) * 100,
                sharpe=r.mean() / r.std() * np.sqrt(12) if r.std() > 0 else np.nan,
                mdd=(eq / eq.cummax() - 1).min() * 100,
                worst=r.min() * 100)          # 최악월 (2026-08-11, #74)


def backtest(R, M, MOM, N, pool, cost, defense=None, cash=0.5, rng=None, sample_from=None,
             div_yield=None, tax=0.154):
    """동적 리더십 선정 · 동일가중+캡 · MA200 방어. rng 주어지면 풀에서 N개 무작위 추출."""
    Msel = M.shift(1)
    held, net, turns, yms = set(), [], [], []
    for t in R.index:
        if t not in Msel.index or t not in MOM.index:
            continue
        mc = Msel.loc[t].dropna()
        if len(mc) < 50:
            continue
        cur = R.loc[t]
        cand = [c for c in mc.sort_values(ascending=False).index[:pool] if pd.notna(cur.get(c))]
        m = MOM.loc[t, [c for c in cand if c in MOM.columns]].dropna()
        if len(m) < N:
            continue
        ranked = list(m.sort_values(ascending=False).index)
        if rng is not None:
            src = ranked[:sample_from or (2 * N)]
            if len(src) < N:
                continue
            sel = list(rng.choice(src, size=N, replace=False))
        else:
            sel = ranked[:N]
        w = capped_equal_weights(len(sel))
        f = 1 - len(set(sel) & held) / len(sel) if held else 1.0
        turns.append(f)
        g = float((cur[sel].values * w).sum())
        # 배당 가산 (2026-08-10, #75): 12월(배당락 달)에 보유 종목의 트레일링 DIV 세후 가산.
        # 현금 비중(invest) 스케일은 아래에서 가격수익과 함께 곱해진다.
        if div_yield is not None and t.endswith("-12") and t in div_yield.index:
            dv = div_yield.loc[t].reindex(sel).fillna(0.0).values
            g += float((dv * w).sum()) / 100.0 * (1.0 - tax)
        invest = 1.0
        if defense is not None:
            sig = defense.get(t)
            if pd.notna(sig) and not bool(sig):
                invest = 1.0 - cash
        net.append(g * invest - f * cost)
        yms.append(t)
        held = set(sel)
    s = stats(net)
    s["turn"] = float(np.mean(turns) * 12) if turns else 0.0
    s["n"] = len(net)
    s["rets"] = np.asarray(net, dtype=float)
    s["yms"] = list(yms)          # 2026-08-08: 짝지은 검정을 위해 월 라벨도 반환
    return s


# ────────────────────────────────────── 짝지은 초과수익 검정 (2026-08-08)
def _block_idx(rng, T, L):
    """정상 블록 부트스트랩용 인덱스 한 벌. 기존 관행과 동일(평균 블록 L개월, 순환)."""
    out = []
    while len(out) < T:
        st = int(rng.integers(0, T))
        ln = max(1, int(rng.geometric(1.0 / L)))
        for j in range(ln):
            out.append((st + j) % T)
            if len(out) >= T:
                break
    return np.asarray(out[:T])


def _cagr(x):
    x = np.asarray(x, dtype=float)
    return (np.prod(1.0 + x) ** (12.0 / len(x)) - 1.0) * 100.0


def paired_test(strat, kos, boot=200, seed=0, L=12):
    """전략과 벤치마크를 **같은 달끼리 짝지어** 재표집한다.

    왜 이게 필요한가
    ---------------
    기존 부트스트랩은 전략 수익만 재표집하고 KOSPI 는 고정된 숫자 하나와 비교했다.
    그러면 두 시계열이 공유하는 **시장 베타가 통째로 불확실성으로 계상된다** —
    "이 전략이 지수를 이기는가" 라는 상대 질문에 대해 과도하게 비관적인 구간이 나온다.

    여기서는 달 인덱스를 한 번 뽑아 **전략과 지수에 똑같이 적용**한다.
    같은 달이 함께 뽑히므로 시장 공통 성분이 차이에서 상쇄된다.
    """
    s = np.asarray(strat, dtype=float)
    k = np.asarray(kos, dtype=float)
    assert len(s) == len(k) and len(s) > 0
    T = len(s)
    rng = np.random.default_rng(seed)

    gaps, means, beats = [], [], 0
    for _ in range(boot):
        ix = _block_idx(rng, T, L)
        g = _cagr(s[ix]) - _cagr(k[ix])
        gaps.append(g)
        means.append(float(np.mean(s[ix] - k[ix])) * 12 * 100)
        if g > 0:
            beats += 1

    # 비교용: 짝을 깨고 전략만 재표집 (기존 방식) — 구간 폭 차이를 보이기 위함
    rng2 = np.random.default_rng(seed + 1)
    kc = _cagr(k)
    naive = [_cagr(s[_block_idx(rng2, T, L)]) - kc for _ in range(boot)]

    q = lambda v: np.percentile(v, [5, 25, 50, 75, 95])
    qp, qn = q(gaps), q(naive)
    d = s - k
    return dict(
        n=T,
        act_gap=_cagr(s) - kc,
        act_mean_excess=float(np.mean(d)) * 12 * 100,
        hit=float(np.mean(d > 0)) * 100,
        p5=qp[0], p25=qp[1], p50=qp[2], p75=qp[3], p95=qp[4],
        width=qp[4] - qp[0], beat=beats / float(boot),
        mean_p5=np.percentile(means, 5), mean_p95=np.percentile(means, 95),
        naive_p5=qn[0], naive_p95=qn[4], naive_width=qn[4] - qn[0],
    )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", default=None)
    ap.add_argument("--pool", type=int, default=100)
    ap.add_argument("--signal", default="momentum", choices=["momentum", "multifactor"],
                    help="선정 신호. momentum=12-1(백서 t=0.7, 유의성 없음) · "
                         "multifactor=div/bp/ep/roe z합성(검증됨 HAC t 4.10/3.34/2.36 · forward 동결규칙)")
    ap.add_argument("--cost", default="기준", choices=list(_SC))
    ap.add_argument("--boot", type=int, default=200, help="집중리스크 분포 반복 횟수")
    ap.add_argument("--no-boot", action="store_true")
    ap.add_argument("--seed", type=int, default=20260727)
    ap.add_argument("--out", default="재산출_운용사양_2026-07-27.md")
    ap.add_argument("--price", default="full", choices=list(PX_SOURCES),
                    help="가격 원천. full=기존 복원본(기본) · kis=KIS 수정주가 전수")
    ap.add_argument("--panel", default=None, metavar="CSV",
                    help="멀티팩터 신호용 스타일 패널 경로. 기본은 mini_style_panel.csv 를 "
                         "이름으로 탐색. 원천별 패널로 돌릴 때 파일을 바꿔치기하지 않아도 된다.")
    ap.add_argument("--no-paired", action="store_true",
                    help="짝지은 초과수익 검정을 생략 (기본은 실행)")
    ap.add_argument("--div", action="store_true",
                    help="#75 TR 근사: 12월에 보유 종목 트레일링 DIV 세후 가산, "
                         "벤치마크도 같은 방법으로 시장 시총가중 DIV 가산")
    ap.add_argument("--div-tax", type=float, default=0.154, help="배당소득세율 (기본 0.154)")
    ap.add_argument("--tr-index", default=None, metavar="CSV",
                    help="공식 KOSPI TR 지수 CSV. 있으면 벤치마크로 이것을 사용 "
                         "(--div 의 합성 벤치마크보다 우선)")
    ap.add_argument("--mask", action="append", default=[], metavar="CSV",
                    help="마스크 CSV (반복 가능). 예: --mask _패널마스크_v1.csv "
                         "--mask _출처불일치_v1.csv")
    a = ap.parse_args()
    cost = _rt(a.cost)

    PX = load_px(a.price, a.mask)
    R = PX.pct_change(fill_method=None).mask(lambda x: x.abs() > 1.0)
    M = load_mcap()
    DIVP = load_div_pivot() if a.div else None
    if a.div:
        if DIVP is None:
            sys.exit("⛔ --div: 종목재무_KRX_*.csv 를 못 찾음")
        print(f"  배당 가산 ON — 트레일링 DIV 근사 · 세율 {a.div_tax:.3f} (FnGuide 실배당 전 임시)")
    idx = [m for m in R.index if m in M.index][:-1]        # 미완료 최종월 제외
    if a.start:
        idx = [m for m in idx if m >= a.start]
    R, M = R.reindex(idx), M.reindex(idx)
    if a.signal == "momentum":
        MOM = PX.reindex(idx).shift(1) / PX.reindex(idx).shift(13) - 1
    else:
        # forward_signal.py 동결규칙과 동일: div·bp·ep·roe 월별 횡단면 z 등가중 합성
        _pp = a.panel or find("mini_style_panel.csv")
        print(f"  신호패널: {os.path.basename(_pp)}")
        pan = pd.read_csv(_pp, dtype={"code": str})
        pan["code"] = pan["code"].str.zfill(6)
        for c in ("div", "bp", "ep", "roe"):
            g = pan.groupby("ym")[c]
            pan[c + "z"] = (pan[c] - g.transform("mean")) / g.transform("std").replace(0, np.nan)
        pan["score"] = pan[["divz", "bpz", "epz", "roez"]].mean(axis=1)
        # 🚨 2026-07-27 자체 발견: **반드시 shift(1)** 이다.
        # div=DPS/가격 · bp=BPS/가격 · ep=EPS/가격 — 전부 분모에 가격이 있다.
        # 그 달에 30% 폭락한 종목은 월말에 밸류 점수가 43% 높아진다.
        # 월말 점수로 고르고 그 달 수익을 계산하면 **그 달의 패자를 사후에 골라잡는다**(역방향 룩어헤드).
        # 오전에 잡은 시총 룩어헤드의 거울상. 부호만 반대고 원리는 같다.
        MOM = (pan.pivot_table(index="ym", columns="code", values="score", aggfunc="last")
               .reindex(idx).shift(1))
        idx2 = [m for m in idx if m in MOM.index and MOM.loc[m].notna().sum() >= 50]
        print(f"  신호: 멀티팩터 z합성 (유효 {len(idx2)}개월 {min(idx2)}~{max(idx2)})")
        _miss = sorted(set(m for m in idx if m >= min(idx2)) - set(idx2))
        if _miss:
            print(f"  ⚠️ 신호 무효 달 {len(_miss)}개 — 점수 종목<50 이라 백테가 건너뜀"
                  f" (B-1r ③ '공짜 건너뛰기'): {', '.join(_miss[:12])}")
    DEF, IDXPX = load_defense(idx)

    print("=" * 84)
    print(" §8-2 운용사양 재현 · N 스윕 + 집중리스크 분포")
    print("=" * 84)
    _mk = ("+".join(os.path.basename(m) for m in a.mask)) if a.mask else "없음"
    print(f"  구간 {idx[0]} ~ {idx[-1]} ({len(idx)}개월) · 원천={a.price} · 마스크={_mk} · pool={a.pool}")
    print(f"  가중: 동일가중 → 종목캡 {STOCK_CAP*100:.0f}% → 정규화 (진우_통합한도.json 본체_v372)")
    print(f"  신호: {a.signal}")
    print(f"  비용: {a.cost} 시나리오 왕복 {cost*100:.3f}%/회전 · 방어 MA200(10개월MA) 50%현금")

    NS = [30, 20, 15, 12, 10, 8, 5]
    print(f"\n  {'N':>4}{'무방어 CAGR':>13}{'방어 CAGR':>12}{'Sharpe':>9}{'MDD':>9}{'회전/년':>8}{'종목당비중':>10}")
    print("  " + "-" * 76)
    rows = []
    for N in NS:
        nd = backtest(R, M, MOM, N, a.pool, cost, div_yield=DIVP, tax=a.div_tax)
        wd = backtest(R, M, MOM, N, a.pool, cost, defense=DEF, div_yield=DIVP, tax=a.div_tax)
        w0 = capped_equal_weights(N)[0] * 100
        rows.append((N, nd, wd))
        print(f"  {N:>4}{nd['cagr']:>12.1f}%{wd['cagr']:>11.1f}%{wd['sharpe']:>9.2f}"
              f"{wd['mdd']:>8.1f}%{wd['turn']:>7.1f}x{w0:>9.1f}%")
    print("  " + "-" * 76)
    ir = IDXPX.reindex(idx).pct_change().dropna()
    # ── 벤치마크 선택 (2026-08-10, #75)
    bench_label = "KOSPI(PR)"
    if a.tr_index:
        tr = load_index_monthly(a.tr_index)
        ir_tr = tr.pct_change().reindex(ir.index)
        miss = int(ir_tr.isna().sum())
        if miss:
            print(f"  ⚠️ TR 지수가 창의 {miss}개월을 못 덮음 — 그 달은 짝지은 비교에서 빠짐")
        ir = ir_tr.dropna()
        bench_label = f"KOSPI TR({os.path.basename(a.tr_index)})"
        print(f"  벤치마크: {bench_label} · {len(ir)}개월")
    elif a.div:
        nadd = 0
        for ym2 in [y for y in ir.index if y.endswith("-12")]:
            if DIVP is not None and ym2 in DIVP.index and ym2 in M.index:
                dv2, mc2 = DIVP.loc[ym2], M.loc[ym2]
                both = dv2.notna() & mc2.notna()
                if both.sum() >= 50:
                    mdv = float((dv2[both] * mc2[both]).sum() / mc2[both].sum())
                    ir.loc[ym2] += mdv / 100.0 * (1.0 - a.div_tax)
                    nadd += 1
        bench_label = "KOSPI PR+시장배당(세후)"
        print(f"  벤치마크: {bench_label} — 12월 {nadd}회 가산 (전략과 동일 방법·동일 세율)")
    k = stats(ir)
    k_cagr = k["cagr"]
    print(f"  {'KOSPI':>4}{'':>12}{k['cagr']:>11.1f}%{k['sharpe']:>9.2f}{k['mdd']:>8.1f}%")

    # ── #74 방어 재판정 · 3축 (2026-08-11) — 방어의 CAGR 비용 vs MDD·최악월 이득
    if DEF is not None:
        _on = DEF.reindex(idx).astype("boolean").fillna(True)
        _ncash = int((~_on).sum())
        print(f"\n  [#74 방어 재판정 · 3축]  방어 발동(현금 50%) {_ncash}개월 / {len(_on)} ({_ncash*100.0/len(_on):.0f}%)")
        print(f"  {'N':>4} | {'CAGR 무→방 (차)':^22} | {'MDD 무→방 (개선)':^24} | {'최악월 무→방':^16} | Sharpe 무→방")
        print("  " + "-" * 100)
        for N4, nd4, wd4 in rows:
            print(f"  {N4:>4} | {nd4['cagr']:5.1f}% → {wd4['cagr']:5.1f}% ({wd4['cagr']-nd4['cagr']:+.1f}) | "
                  f"{nd4['mdd']:6.1f}% → {wd4['mdd']:6.1f}% ({wd4['mdd']-nd4['mdd']:+.1f}) | "
                  f"{nd4['worst']:6.1f}% → {wd4['worst']:6.1f}% | {nd4['sharpe']:.2f} → {wd4['sharpe']:.2f}")
        print("  " + "-" * 100)
        print(f"  벤치 | CAGR {k['cagr']:.1f}% · MDD {k['mdd']:.1f}% · 최악월 {k['worst']:.1f}% · Sharpe {k['sharpe']:.2f}")
        print("  * 판정 기준: 방어의 CAGR 비용을 MDD·최악월 개선이 정당화하는가. 개선이 없으면 방어는 순비용.")

    boot = {}
    if not a.no_boot:
        print(f"\n  [CAGR 신뢰구간] 정상 블록 부트스트랩 (평균 블록 12개월) × {a.boot}회 · 방어 포함")
        print(f"  {'N':>4}{'5%':>9}{'25%':>9}{'중앙':>9}{'75%':>9}{'95%':>9}{'점추정':>9}{'폭':>8}{'KOSPI초과 확률':>14}")
        print("  " + "-" * 82)
        kr = ir.values
        for N in [30, 20, 15, 12, 10, 8, 5]:
            wd = [w for n, _, w in rows if n == N][0]
            r = wd["rets"]
            if len(r) < 60:
                continue
            rng = np.random.default_rng(a.seed + N)
            L, T = 12, len(r)
            vals, beats = [], 0
            for _ in range(a.boot):
                out = []
                while len(out) < T:
                    st = rng.integers(0, T)
                    ln = max(1, int(rng.geometric(1.0 / L)))
                    for _j in range(ln):
                        out.append(r[(st + _j) % T])
                        if len(out) >= T:
                            break
                x = np.asarray(out[:T])
                c = (np.prod(1 + x) ** (12 / T) - 1) * 100
                vals.append(c)
                if c > k_cagr:
                    beats += 1
            q = np.percentile(vals, [5, 25, 50, 75, 95])
            boot[N] = dict(q5=q[0], q25=q[1], q50=q[2], q75=q[3], q95=q[4],
                           act=wd["cagr"], beat=beats / len(vals))
            print(f"  {N:>4}{q[0]:>8.1f}%{q[1]:>8.1f}%{q[2]:>8.1f}%{q[3]:>8.1f}%{q[4]:>8.1f}%"
                  f"{wd['cagr']:>8.1f}%{q[4]-q[0]:>7.1f}%p{beats/len(vals)*100:>13.0f}%")
        print("  " + "-" * 82)
        print(f"  * {bench_label} {k_cagr:.1f}% 초과 확률 — 부트스트랩 표본 중 지수를 이긴 비율")
        print(f"  ⚠️ 위 구간은 **전략의 절대 CAGR** 에 대한 것이고 KOSPI 는 고정값 하나와 비교했다.")
        print(f"     상대 질문('지수를 이기는가')에는 아래 〈짝지은 초과수익 검정〉이 올바른 통계다.")
        print(f"     (초판은 '기존 방식이 과도하게 비관적'이라고 예단했는데 실측 결과 반대였다 — B-1r ④)")

    # ── 짝지은 초과수익 검정 (2026-08-08 신규 · 2026-08-10 무방어 추가, #74)
    paired = {"방어": {}, "무방어": {}}
    if not a.no_paired:
        krm = {y: v for y, v in ir.items()}
        for mode, pick in (("방어", 2), ("무방어", 1)):
            print(f"\n  [짝지은 초과수익 검정 · {mode}] 같은 달끼리 함께 재표집 × {a.boot}회 · 벤치마크 {bench_label}")
            print(f"  {'N':>4}{'실측격차':>10}{'5%':>9}{'중앙':>9}{'95%':>9}{'폭':>9}"
                  f"{'초과>0 확률':>12}{'월승률':>8}")
            print("  " + "-" * 78)
            for N in [30, 20, 15, 12, 10, 8, 5]:
                hit = [t3 for t3 in rows if t3[0] == N]
                if not hit:
                    continue
                sd = hit[0][pick]
                pair = [(r, krm[y]) for y, r in zip(sd["yms"], sd["rets"])
                        if y in krm and pd.notna(krm[y])]
                if len(pair) < 60:
                    continue
                s_ = [x[0] for x in pair]; k_ = [x[1] for x in pair]
                pt = paired_test(s_, k_, boot=a.boot, seed=a.seed + N)
                paired[mode][N] = pt
                print(f"  {N:>4}{pt['act_gap']:>9.2f}%{pt['p5']:>8.2f}%{pt['p50']:>8.2f}%"
                      f"{pt['p95']:>8.2f}%{pt['width']:>8.2f}p{pt['beat']*100:>11.0f}%"
                      f"{pt['hit']:>7.1f}%")
            print("  " + "-" * 78)
        if paired["방어"]:
            n0 = sorted(paired["방어"])[0]
            print(f"  * 월승률 = 전략이 그 달 벤치마크를 이긴 개월 비율 (짝지은 원표본, 부트스트랩 아님).")
            print(f"  * 대응 표본 {paired['방어'][n0]['n']}개월 · 무방어 표는 #74(방어 재판정)용.")

    # ── 판정
    r30 = [w for n, _, w in rows if n == 30][0]
    r15 = [w for n, _, w in rows if n == 15][0]
    r10 = [w for n, _, w in rows if n == 10][0]
    print("\n  [판정]")
    print(f"   · N=30 → 15: CAGR {r30['cagr']:.1f}% → {r15['cagr']:.1f}% ({r15['cagr']-r30['cagr']:+.1f}%p) · "
          f"MDD {r30['mdd']:.1f}% → {r15['mdd']:.1f}%")
    print(f"   · N=30 → 10: CAGR {r30['cagr']:.1f}% → {r10['cagr']:.1f}% ({r10['cagr']-r30['cagr']:+.1f}%p) · "
          f"MDD {r30['mdd']:.1f}% → {r10['mdd']:.1f}%")
    if 30 in boot and 15 in boot:
        print(f"   · 신뢰구간 폭(95%−5%): N=30 {boot[30]['q95']-boot[30]['q5']:.1f}%p · "
              f"N=15 {boot[15]['q95']-boot[15]['q5']:.1f}%p"
              + (f" · N=5 {boot[5]['q95']-boot[5]['q5']:.1f}%p" if 5 in boot else ""))
        print(f"   · KOSPI 초과 확률: N=30 {boot[30]['beat']*100:.0f}% · N=15 {boot[15]['beat']*100:.0f}%"
              + (f" · N=10 {boot[10]['beat']*100:.0f}%" if 10 in boot else ""))
    print(f"   · {bench_label} {k['cagr']:.1f}% 대비: N=30 {r30['cagr']-k['cagr']:+.1f}%p · "
          f"N=15 {r15['cagr']-k['cagr']:+.1f}%p · N=10 {r10['cagr']-k['cagr']:+.1f}%p")

    # ── 저장
    L = ["# §8-2 운용사양 재현 — N 스윕 + 집중리스크 분포", "",
         f"> 구간 {idx[0]} ~ {idx[-1]} ({len(idx)}개월) · 원천 **{a.price}** · "
         f"마스크 {_mk} · 신호 {a.signal} · pool={a.pool} · "
         f"비용 {a.cost}({cost*100:.3f}%/회전)", "",
         # 2026-08-08: 출처 도장. 이 블록이 없으면 "어느 버전으로 낸 결과냐"를
         # 나중에 알 수 없다. 초판은 원천이 kis 여도 헤더에 '복원본(_full)' 이
         # 박혀 있었다 — 결과 파일이 자기 출처를 잘못 적고 있었다.
         "<details><summary>재현 정보 (이 결과를 만든 것)</summary>", "",
         "```",
         f"생성기        {os.path.basename(__file__)}",
         f"생성기 md5    {_selfmd5()}",
         f"옵션          {' '.join(sys.argv[1:])}",
         f"가격 원천     {a.price} = {', '.join(PX_SOURCES[a.price])}",
         f"마스크        {_mk}",
         f"신호패널      {os.path.basename(a.panel) if a.panel else '(이름탐색)'}",
         f"seed          {a.seed} · 부트스트랩 {0 if a.no_boot else a.boot}회",
         f"배당가산      {('ON · 트레일링DIV 근사 · 세율 ' + str(a.div_tax)) if a.div else 'OFF (PR)'}",
         f"TR지수        {a.tr_index or '없음'}",
         "```", "", "</details>", "",
         "> **가중은 동일가중 + 종목캡 15% + 정규화** — `진우_통합한도.json` 본체_v372 기준. "
         "백서 B-1c의 '리스크 1% 사이징'은 **재량(위성) 트랙** 규칙이며 본체 규칙이 아니다.", "",
         "| N | 무방어 CAGR | 방어 CAGR | Sharpe | MDD | 회전/년 | 종목당 비중 |",
         "|---|---|---|---|---|---|---|"]
    for N, nd, wd in rows:
        L.append(f"| {N} | {nd['cagr']:.1f}% | **{wd['cagr']:.1f}%** | {wd['sharpe']:.2f} | "
                 f"{wd['mdd']:.1f}% | {wd['turn']:.1f}x | {capped_equal_weights(N)[0]*100:.1f}% |")
    L.append(f"| {bench_label} | — | {k['cagr']:.1f}% | {k['sharpe']:.2f} | {k['mdd']:.1f}% | — | — |")
    if boot:
        L += ["", "## CAGR 신뢰구간 — 정상 블록 부트스트랩", "",
              f"월수익률을 평균 12개월 블록으로 재표집 × {a.boot}회 (방어 포함)", "",
              "| N | 5% | 25% | 중앙 | 75% | 95% | 점추정 | 폭 | KOSPI 초과 확률 |",
              "|---|---|---|---|---|---|---|---|---|"]
        for N, b in boot.items():
            L.append(f"| {N} | {b['q5']:.1f}% | {b['q25']:.1f}% | {b['q50']:.1f}% | {b['q75']:.1f}% | "
                     f"{b['q95']:.1f}% | **{b['act']:.1f}%** | {b['q95']-b['q5']:.1f}%p | "
                     f"**{b['beat']*100:.0f}%** |")
    for mode in ("방어", "무방어"):
        if paired.get(mode):
            L += ["", f"## 짝지은 초과수익 검정 — {mode} (벤치마크 {bench_label})", "",
                  "| N | 실측격차 | 5% | 중앙 | 95% | 초과>0 확률 | 월승률 |",
                  "|---|---|---|---|---|---|---|"]
            for N2, pt in paired[mode].items():
                L.append(f"| {N2} | **{pt['act_gap']:+.2f}%p** | {pt['p5']:+.2f}% | {pt['p50']:+.2f}% | "
                         f"{pt['p95']:+.2f}% | **{pt['beat']*100:.0f}%** | {pt['hit']:.1f}% |")
    if not a.no_paired:   # 회귀검증기(--no-paired)와의 계약 — 옛 md 와 숫자 1:1 유지
        L += ["", "## #74 방어 재판정 — 3축 (무방어 → 방어)", "",
              "| N | CAGR | MDD | 최악월 | Sharpe |",
              "|---|---|---|---|---|"]
        for N5, nd5, wd5 in rows:
            L.append(f"| {N5} | {nd5['cagr']:.1f}% → {wd5['cagr']:.1f}% ({wd5['cagr']-nd5['cagr']:+.1f}) | "
                     f"{nd5['mdd']:.1f}% → {wd5['mdd']:.1f}% ({wd5['mdd']-nd5['mdd']:+.1f}) | "
                     f"{nd5['worst']:.1f}% → {wd5['worst']:.1f}% | {nd5['sharpe']:.2f} → {wd5['sharpe']:.2f} |")
        L.append(f"| 벤치마크 | {k['cagr']:.1f}% | {k['mdd']:.1f}% | {k['worst']:.1f}% | {k['sharpe']:.2f} |")
    L += ["", "## 재보지 못한 것", "",
          "- **섹터캡 35%** — 섹터 매핑이 현재 948종목뿐, 30년 이력 없음",
          "- **등급이탈 청산** — 과거 등급 시계열 없음",
          "- **실행 시차** — 사양은 '월간 첫 영업일, 다음영업일 시가/종가'인데 월봉으로 월말종가 근사",
          "- **재량 트랙** — 본 백테는 본체만. 재량은 forward 실측 대상",
          "", "> ⚠️ 검증용 · 실현손익 아님 · 투자자문 아님 · 책임 본인"]
    outp = a.out if os.path.isabs(a.out) else os.path.join(ROOT, a.out)
    open(outp, "w", encoding="utf-8").write("\n".join(L))
    print(f"\n  저장: {os.path.relpath(outp, ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
