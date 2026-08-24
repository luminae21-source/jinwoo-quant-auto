# -*- coding: utf-8 -*-
r"""검정_위성엔진_OOS개봉.py — 위성엔진 v1 사전등록 검정 (2026-07-28 개봉)

사전등록서: 위성엔진_v1_사전등록.md (2026-07-28 등록 · 데이터 개봉 전)
동시등록:   v1' = v1 + ROE>0 (가치함정 회피 · IN 탐색에서 발굴, OOS는 미개봉)
            ※ 두 사양을 나란히 검정한다. 결과를 보고 하나를 고르지 않는다.

[구현 — 사전등록서 §1 그대로. 파라미터 스윕 금지]
  유니버스 : 시총 순위 301+ (양시장) · 시총 하한 300억 (ADTV 대용 — 이탈 표기)
  선별 ①   : 저변동성 하위 40%  ※ 일간 60d 대신 **월간 12M 표준편차** (등록서 §3-2 허용 대체)
  선별 ②   : 저PBR 하위 40% (PBR>0)
  채택     : ①∩② 교집합에서 **저변동성 순 상위 N=5** · 동일가중
  청산     : **트레일링 −15%** (고점 대비 · 청산규칙_규칙서 소중형 1순위)
  진입시점 : 월 1회 리밸런스(월초) → 하순(−9~−5일) 자동 회피
  비용     : 기준 0.559% · 보수 1.511% (편도 회전율 기준)
  상폐     : 소멸_재분류_v1 코드별 터미널

[판정 관문 — 등록서 §2, 결과 보고 바꾸지 않는다]
  (A) OOS(2016-01~2026-06) 순수익(기준비용) > 0
  (B) 조합 ≥ max(저변동성 단독, 저PBR 단독) − 1%p
  (C) OOS 월간 초과수익(vs 소중형 EW) t ≥ 1.5 · 부호 +
  (D) 보수 1.511%에서도 순수익 > −2%/년

⚠️ 정직 고지: 저변동성·저PBR 개별 팩터는 진입엣지_규칙서에서 이미 OOS 2013~2026으로 검정됐다.
   따라서 2016~2026은 **개별 팩터에 대해서는 순수 봉인 구간이 아니다.**
   이 검정이 새로 여는 것은 ① **조합의 상호작용** ② **수정주가 병합본(신규 데이터)** 두 가지다.
"""
import os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def _find(fn):
    for d in (BASE, os.path.join(BASE, "데이터수리"), os.path.dirname(BASE), os.getcwd(),
              os.path.join(os.getcwd(), "데이터수리")):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    raise FileNotFoundError(fn)

def hac_t(x, lags=6):
    x = np.asarray(pd.Series(x).dropna(), float); n = len(x)
    if n < 12: return np.nan
    m = x.mean(); e = x - m; v = (e @ e) / n
    for L in range(1, min(lags, n - 1) + 1):
        v += 2 * (1 - L / (lags + 1)) * ((e[L:] @ e[:-L]) / n)
    return m / np.sqrt(max(v, 1e-18) / n)

# ── 사전등록 파라미터 (고정)
N          = 5
Q_VOL      = 0.40
Q_PBR      = 0.40
TRAIL      = 0.15
MCAP_FLOOR = 300e8
COST_BASE  = 0.00559
COST_CONS  = 0.01511
OOS_A, OOS_B = "2016-01", "2026-06"
IN_A,  IN_B  = "2002-07", "2015-12"

print("=" * 96)
print(" 위성엔진 v1 — 봉인 OOS 개봉 검정 (사전등록 2026-07-28)")
print("=" * 96)

kis = pd.read_csv(_find("_월봉_KIS_전기간.csv"), dtype={"code": str})
kis["code"] = kis["code"].str.zfill(6)
P = kis.pivot_table(index="ym", columns="code", values="close", aggfunc="last").sort_index()
_i = pd.to_datetime(P.index + "-01"); MI = (_i.year * 12 + _i.month).values
R = P.pct_change(); R[np.r_[True, np.diff(MI) != 1]] = np.nan
VOL12 = R.rolling(12, min_periods=10).std()

fins = []
for mkt in ("KOSPI", "KOSDAQ"):
    fins.append(pd.read_csv(_find(f"종목재무_KRX_{mkt}.csv"), dtype={"code": str},
                            usecols=["date", "code", "PBR", "BPS", "EPS", "DIV"]))
fin = pd.concat(fins); fin["code"] = fin["code"].str.zfill(6); fin["ym"] = fin["date"].str[:7]
for c in ("PBR", "BPS", "EPS", "DIV"): fin[c] = pd.to_numeric(fin[c], errors="coerce")
fin["roe"] = np.where(fin["BPS"] > 0, fin["EPS"] / fin["BPS"], np.nan)
fin = fin.groupby(["code", "ym"], as_index=False)[["PBR", "roe", "DIV"]].last()
PBR = fin.pivot_table(index="ym", columns="code", values="PBR", aggfunc="last").reindex(index=P.index, columns=P.columns)
ROE = fin.pivot_table(index="ym", columns="code", values="roe", aggfunc="last").reindex(index=P.index, columns=P.columns)
DIVy = fin.pivot_table(index="ym", columns="code", values="DIV", aggfunc="last").reindex(index=P.index, columns=P.columns).clip(0, 60)

mc = pd.read_csv(_find("종목시총_30년.csv"), dtype={"code": str})
mc.columns = [c.strip().lstrip("﻿") for c in mc.columns]
mc["code"] = mc["code"].str.zfill(6); mc["ym"] = pd.to_datetime(mc["date"]).dt.strftime("%Y-%m")
mc["mcap"] = pd.to_numeric(mc["mcap"], errors="coerce")
MC = mc.pivot_table(index="ym", columns="code", values="mcap", aggfunc="last").reindex(index=P.index, columns=P.columns)

try:
    _t = pd.read_csv(_find("소멸_재분류_v1.csv"), dtype={"code": str})
    TERM = dict(zip(_t["code"].str.zfill(6), _t["terminal_ret"].astype(float)))
except Exception:
    TERM = {}

# 우선주 제외 (종목발굴_체계 §3 — 계열 중복 회피)
ALLC = set(P.columns)
def is_common(c):
    if not c.isdigit(): return False
    return not ((not c.endswith("0")) and (c[:5] + "0") in ALLC)
COMMON = pd.Series([is_common(c) for c in P.columns], index=P.columns)

months = list(P.index)

def run(strategy, a, b, cost):
    """strategy: 'combo' | 'combo_roe' | 'lowvol' | 'lowpbr' | 'ew'"""
    rows, held, peak = [], {}, {}
    idxs = [i for i, m in enumerate(months) if a <= m <= b]
    for i in idxs[:-1]:
        m, nxt = months[i], months[i + 1]
        mcap = MC.loc[m]; px = P.loc[m]
        alive = px.notna()
        univ = alive & (mcap.rank(ascending=False) > 300) & (mcap >= MCAP_FLOOR) & COMMON
        if univ.sum() < 30:
            continue
        vol = VOL12.loc[m].where(univ); pbr = PBR.loc[m].where(univ & (PBR.loc[m] > 0))
        lowvol = vol <= vol.quantile(Q_VOL)
        lowpbr = pbr <= pbr.quantile(Q_PBR)

        if strategy == "ew":
            tgt = list(univ[univ].index)
        else:
            if strategy == "combo":       cand = vol.where(lowvol & lowpbr)
            elif strategy == "combo_roe": cand = vol.where(lowvol & lowpbr & (ROE.loc[m] > 0))
            elif strategy == "reduced":   cand = pbr.where(lowpbr & (ROE.loc[m] > 0))   # 축소판: 저변동성 층 제거
            elif strategy == "lowvol":    cand = vol.where(lowvol)
            elif strategy == "lowpbr":    cand = pbr.where(lowpbr)   # 저PBR 단독은 PBR 낮은 순 (부품 고유 정렬)
            cand = cand.dropna()
            if len(cand) < N: continue
            # 트레일 −15% 위반 종목 배제
            stopped = set()
            for c in list(held):
                p_now = px.get(c)
                if pd.notna(p_now):
                    peak[c] = max(peak.get(c, p_now), p_now)
                    if p_now < peak[c] * (1 - TRAIL): stopped.add(c)
            tgt = [c for c in cand.nsmallest(N * 3).index if c not in stopped][:N]
            if len(tgt) < N: continue

        w = pd.Series(1.0 / len(tgt), index=tgt)
        r_nxt = R.loc[nxt].reindex(tgt)
        div_m = DIVy.loc[m].reindex(tgt).fillna(0) / 100 / 12
        r_fill = r_nxt.fillna(pd.Series({c: TERM.get(c, -0.30) for c in tgt}))
        ret_tr = float(((r_fill + div_m) * w).sum())

        prev = pd.Series(held) if held else pd.Series(dtype=float)
        allc = w.index.union(prev.index)
        oneway = float((w.reindex(allc).fillna(0) - prev.reindex(allc).fillna(0)).abs().sum()) / 2
        rows.append(dict(ym=nxt, ret=ret_tr - oneway * cost, oneway=oneway, n=len(tgt)))

        held = {c: 1.0 / len(tgt) for c in tgt}
        for c in list(peak):
            if c not in held: peak.pop(c, None)
        for c in tgt:
            pv = px.get(c)
            if pd.notna(pv): peak[c] = max(peak.get(c, pv), pv)
    return pd.DataFrame(rows).set_index("ym") if rows else pd.DataFrame()

def ann(s):
    s = s.dropna()
    return ((1 + s).prod() ** (12 / len(s)) - 1) * 100 if len(s) else np.nan

def mdd(s):
    nav = (1 + s.dropna()).cumprod()
    return (nav / nav.cummax() - 1).min() * 100

STRATS = [("combo", "v1  저변동성∩저PBR"), ("combo_roe", "v1' 저변동성∩저PBR∩ROE>0"),
          ("reduced", "★축소판 저PBR∩ROE>0 (저변동성 제거)"),
          ("lowvol", "부품 저변동성 단독"), ("lowpbr", "부품 저PBR 단독"), ("ew", "벤치 소중형 EW")]

for wname, wa, wb in (("OOS (사전등록 검정창)", OOS_A, OOS_B), ("IN (참고)", IN_A, IN_B)):
    print(f"\n{'─'*96}\n【{wname}】 {wa} ~ {wb}")
    print(f"  {'전략':<28}{'기준비용':>10}{'보수비용':>10}{'MDD':>9}{'초과(vs EW)':>13}{'초과 t':>8}{'회전':>7}{'월수':>6}")
    res = {}
    for key, lbl in STRATS:
        d1 = run(key, wa, wb, COST_BASE)
        d2 = run(key, wa, wb, COST_CONS)
        if not len(d1): continue
        res[key] = (d1, d2)
    ew = res.get("ew", (pd.DataFrame(),))[0]
    for key, lbl in STRATS:
        if key not in res: continue
        d1, d2 = res[key]
        if key != "ew" and len(ew):
            ex = (d1["ret"] - ew["ret"].reindex(d1.index)).dropna()
            exs, ext = ann(ex) if False else ex.mean() * 12 * 100, hac_t(ex.values)
        else:
            exs, ext = np.nan, np.nan
        print(f"  {lbl:<28}{ann(d1['ret']):>9.2f}%{ann(d2['ret']):>9.2f}%{mdd(d1['ret']):>8.1f}%"
              f"{(f'{exs:+.2f}%p' if np.isfinite(exs) else '—'):>13}"
              f"{(f'{ext:.2f}' if np.isfinite(ext) else '—'):>8}"
              f"{d1['oneway'].mean()*100:>6.0f}%{len(d1):>6}")
    if wname.startswith("OOS"):
        OOS_RES = res

# ── 관문 판정
print(f"\n{'='*96}\n 판정 관문 (사전등록 §2 — 결과 보고 바꾸지 않는다)\n{'='*96}")
ew = OOS_RES["ew"][0]
for key, lbl in (("combo", "v1  저변동성∩저PBR"), ("combo_roe", "v1' +ROE>0"),
                 ("reduced", "★축소판 저PBR∩ROE>0 — 등록서 허용 재검정 1회")):
    if key not in OOS_RES:
        print(f"\n[{lbl}] 산출 불가"); continue
    d1, d2 = OOS_RES[key]
    a_base, a_cons = ann(d1["ret"]), ann(d2["ret"])
    part = max(ann(OOS_RES["lowvol"][0]["ret"]), ann(OOS_RES["lowpbr"][0]["ret"]))
    ex = (d1["ret"] - ew["ret"].reindex(d1.index)).dropna()
    t = hac_t(ex.values)
    A = a_base > 0
    B = a_base >= part - 1.0
    C = (t >= 1.5) and (ex.mean() > 0)
    D = a_cons > -2.0
    print(f"\n[{lbl}]")
    print(f"  (A) 기준비용 순수익 > 0        : {a_base:+.2f}%/년                    → {'✅ 통과' if A else '❌ 실패'}")
    print(f"  (B) 부품 최고({part:+.2f}%) −1%p 이상 : {a_base:+.2f}% vs 기준 {part-1:+.2f}%      → {'✅ 통과' if B else '❌ 실패'}")
    print(f"  (C) 초과수익 t ≥ 1.5 · 부호 +   : {ex.mean()*12*100:+.2f}%p · t {t:.2f}          → {'✅ 통과' if C else '❌ 실패'}")
    print(f"  (D) 보수비용 > −2%/년          : {a_cons:+.2f}%/년                    → {'✅ 통과' if D else '❌ 실패'}")
    n_ok = sum([A, B, C, D])
    print(f"  ▶ 종합 {n_ok}/4 — {'★ 채택 (P3 페이퍼 진입)' if n_ok == 4 else '🔴 기각 (등록서: 축소판 재검정 1회 후 폐기)'}")
print("=" * 96)
