# -*- coding: utf-8 -*-
r"""검정_주도주풀_지속성.py — 주도주 풀 사전등록 검정 (2026-07-30)

사전등록서: 주도주풀_사전등록.md  (게이트는 개봉 전 확정됨)

가설 H1: 1·3·5년 모두 KOSPI 초과한 종목은 향후 12개월에도 이긴다
가설 H2: '일관성' 조건이 e60 단독 대비 값을 더하는가

게이트  G1 12m(풀−UNIV) 평균>0 & HAC t>=2.0
        G2 12m 승률>=55% & z>=1.64
        G3 12m(풀−MATCH) 평균>0
        G4 2016+ 부분표본 부호 유지

사용: py 검정_주도주풀_지속성.py
"""
import os, sys, json, math
import numpy as np, pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

TOPN      = 30
PX_FLOOR  = 1000
WINDOWS   = [(12, 0.2), (36, 0.4), (60, 0.4)]
HORIZONS  = [12, 24, 36]
FORM_MM   = (6, 12)          # 매년 6월말·12월말 형성


def _find(fn):
    for d in (BASE, os.path.join(BASE, "데이터수리"), os.path.dirname(BASE),
              os.getcwd(), os.path.join(os.getcwd(), "데이터수리")):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    raise FileNotFoundError(fn)


def hac_t(x, lag):
    """Newey-West t (평균이 0인지)"""
    x = np.asarray(x, float); x = x[~np.isnan(x)]
    n = len(x)
    if n < 5: return np.nan
    m = x.mean(); e = x - m
    g0 = (e @ e) / n
    s = g0
    for L in range(1, min(lag, n - 1) + 1):
        g = (e[L:] @ e[:-L]) / n
        s += 2 * (1 - L / (lag + 1)) * g
    if s <= 0: return np.nan
    return m / math.sqrt(s / n)


def z_prop(k, n, p0=0.5):
    if n == 0: return np.nan
    p = k / n
    return (p - p0) / math.sqrt(p0 * (1 - p0) / n)


print("=" * 88)
print(" 주도주 풀 지속성 검정 — 사전등록 개봉")
print("=" * 88)

# ── 데이터
P = pd.read_csv(_find("_월봉_KIS_전기간.csv"), dtype={"code": str})
P["code"] = P["code"].str.zfill(6)
PX = P.pivot_table(index="ym", columns="code", values="close", aggfunc="last").sort_index()
PX = PX.where(PX >= PX_FLOOR)
print(f"가격 패널 {PX.shape[0]}개월 × {PX.shape[1]}종목  ({PX.index[0]} ~ {PX.index[-1]})")

MC = pd.read_csv(_find("종목시총_30년.csv"), dtype={"code": str})
MC["code"] = MC["code"].str.zfill(6)
MC["ym"] = MC["date"].astype(str).str[:7]
MCP = MC.pivot_table(index="ym", columns="code", values="mcap", aggfunc="last") \
        .reindex(index=PX.index, columns=PX.columns)
print(f"시총 패널 {MCP.notna().sum().sum():,}관측")

K = pd.read_csv(_find("kospi_index_daily.csv"))
K["ym"] = K["Date"].astype(str).str[:7]
KI = K.groupby("ym")["Close"].last().reindex(PX.index)
print(f"지수 {KI.notna().sum()}개월")

# 소멸 종결수익률
try:
    T = pd.read_csv(_find("소멸_재분류_v1.csv"), dtype={"code": str})
    T["code"] = T["code"].str.zfill(6)
    tcol = next((c for c in T.columns if "수익" in c or "term" in c.lower()), None)
    TERM = dict(zip(T["code"], T[tcol].astype(float))) if tcol else {}
    print(f"소멸 종결수익률 {len(TERM):,}코드 (컬럼={tcol})")
except Exception as e:
    TERM = {}; print(f"소멸 파일 미적용: {e}")

months = list(PX.index)
midx = {m: i for i, m in enumerate(months)}

# ── 형성월
forms = [m for m in months
         if int(m[5:7]) in FORM_MM and midx[m] >= 60 and m >= "2001-06"]
print(f"형성월 {len(forms)}회  {forms[0]} ~ {forms[-1]}")


def fwd_ret(codes, i0, H):
    """t(=i0) 매수 → t+H 보유. 소멸 시 종결수익률 후 현금."""
    i1 = i0 + H
    if i1 >= len(months): return np.nan
    p0 = PX.iloc[i0]; sub = PX.iloc[i0 + 1:i1 + 1]
    out = []
    for c in codes:
        b = p0.get(c, np.nan)
        if not np.isfinite(b): continue
        s = sub[c].dropna() if c in sub.columns else pd.Series(dtype=float)
        if len(s) == 0:
            out.append(TERM.get(c, -0.50)); continue
        last_i = midx[s.index[-1]]
        r = s.iloc[-1] / b - 1.0
        if last_i < i1:                       # 창 끝나기 전에 사라짐
            r = (1 + r) * (1 + TERM.get(c, -0.50)) - 1.0
        out.append(r)
    return float(np.mean(out)) if out else np.nan


rows = []
for m in forms:
    i = midx[m]
    px_t = PX.iloc[i]
    ok = px_t.notna()
    for w, _ in WINDOWS:
        ok &= PX.iloc[i - w].notna()
    mc_t = MCP.iloc[i]
    if mc_t.notna().sum() < 50: continue
    med = mc_t[ok & mc_t.notna()].median()
    ok &= (mc_t >= med)
    univ = list(px_t.index[ok])
    if len(univ) < 100: continue

    kt = KI.iloc[i]
    exc = {}
    for w, _ in WINDOWS:
        kr = kt / KI.iloc[i - w] - 1.0
        exc[w] = (px_t[univ] / PX.iloc[i - w][univ] - 1.0) - kr

    consist = np.ones(len(univ), bool)
    for w, _ in WINDOWS:
        consist &= (exc[w].values > 0)
    score = sum(exc[w].values * wt for w, wt in WINDOWS)
    D = pd.DataFrame({"code": univ, "score": score, "e60": exc[60].values,
                      "ok": consist})

    pool = D[D.ok].nlargest(TOPN, "score")
    if len(pool) < 10: continue

    # MATCH: 일관성 실패 중 e60 최근접 1:1
    cand = D[~D.ok].copy()
    match = []
    if len(cand) >= len(pool):
        used = set()
        for t60 in pool["e60"].values:
            cc = cand[~cand["code"].isin(used)]
            if len(cc) == 0: break
            j = (cc["e60"] - t60).abs().idxmin()
            used.add(cc.loc[j, "code"]); match.append(cc.loc[j, "code"])

    # e60 단독 상위 (H2 단순형)
    solo = D.nlargest(TOPN, "e60")["code"].tolist()

    r = {"ym": m, "n_univ": len(univ), "n_qual": int(D.ok.sum()),
         "n_pool": len(pool), "n_match": len(match)}
    for H in HORIZONS:
        r[f"pool{H}"]  = fwd_ret(pool["code"].tolist(), i, H)
        r[f"univ{H}"]  = fwd_ret(univ, i, H)
        r[f"match{H}"] = fwd_ret(match, i, H) if match else np.nan
        r[f"solo{H}"]  = fwd_ret(solo, i, H)
        ki1 = KI.iloc[i + H] if i + H < len(months) else np.nan
        r[f"kospi{H}"] = (ki1 / kt - 1.0) if np.isfinite(ki1) else np.nan
    rows.append(r)

R = pd.DataFrame(rows)
R.to_csv(os.path.join(BASE, "_주도주풀_검정_원자료.csv"), index=False, encoding="utf-8-sig")
print(f"\n유효 형성월 {len(R)}회 · 평균 유니버스 {R.n_univ.mean():.0f}종목 · "
      f"평균 자격충족 {R.n_qual.mean():.0f}종목")

# ── 결과
print("\n" + "=" * 88)
print(" 전방 수익률 (동일가중, 형성월 평균)")
print("=" * 88)
print(f"{'H':>4} {'N':>4} {'풀':>9} {'UNIV':>9} {'KOSPI':>9} {'MATCH':>9} {'e60단독':>9}"
      f" {'풀-UNIV':>9} {'HACt':>7} {'승률':>7} {'z':>6}")
res = {}
for H in HORIZONS:
    d = R.dropna(subset=[f"pool{H}", f"univ{H}"])
    if len(d) == 0: continue
    diff = (d[f"pool{H}"] - d[f"univ{H}"]).values
    lag = max(2, int(round(H / 6)))
    t = hac_t(diff, lag)
    k = int((diff > 0).sum()); n = len(diff); zz = z_prop(k, n)
    dm = d.dropna(subset=[f"match{H}"])
    dmv = (dm[f"pool{H}"] - dm[f"match{H}"]).values if len(dm) else np.array([])
    res[H] = dict(n=n, pool=d[f"pool{H}"].mean(), univ=d[f"univ{H}"].mean(),
                  diff=diff.mean(), t=t, win=k / n, z=zz,
                  match=(dmv.mean() if len(dmv) else np.nan),
                  match_t=(hac_t(dmv, lag) if len(dmv) else np.nan),
                  solo=(d[f"solo{H}"] - d[f"univ{H}"]).mean())
    print(f"{H:>4}m {n:>4} {d[f'pool{H}'].mean()*100:>8.2f}% {d[f'univ{H}'].mean()*100:>8.2f}%"
          f" {d[f'kospi{H}'].mean()*100:>8.2f}% {d[f'match{H}'].mean()*100:>8.2f}%"
          f" {d[f'solo{H}'].mean()*100:>8.2f}% {diff.mean()*100:>8.2f}%"
          f" {t:>7.2f} {k/n*100:>6.1f}% {zz:>6.2f}")

# 2016+ 부분표본
print("\n[2016년 이후 부분표본]")
S = R[R.ym >= "2016-01"]
for H in HORIZONS:
    d = S.dropna(subset=[f"pool{H}", f"univ{H}"])
    if len(d) == 0: continue
    dd = (d[f"pool{H}"] - d[f"univ{H}"])
    print(f"  {H:>2}m  N={len(d):>2}  풀−UNIV {dd.mean()*100:>7.2f}%  승률 {(dd>0).mean()*100:>5.1f}%")

# ── 게이트 판정
print("\n" + "=" * 88)
print(" 사전등록 게이트 판정")
print("=" * 88)
r12 = res.get(12, {})
S12 = S.dropna(subset=["pool12", "univ12"])
g1 = bool(r12 and r12["diff"] > 0 and np.isfinite(r12["t"]) and r12["t"] >= 2.0)
g2 = bool(r12 and r12["win"] >= 0.55 and np.isfinite(r12["z"]) and r12["z"] >= 1.64)
g3 = bool(r12 and np.isfinite(r12.get("match", np.nan)) and r12["match"] > 0)
g4 = bool(len(S12) > 0 and (S12["pool12"] - S12["univ12"]).mean() > 0)
for nm, ok, det in [
    ("G1 12m 풀−UNIV>0 & HAC t>=2.0", g1, f"평균 {r12.get('diff',float('nan'))*100:.2f}% · t {r12.get('t',float('nan')):.2f}"),
    ("G2 12m 승률>=55% & z>=1.64",     g2, f"승률 {r12.get('win',float('nan'))*100:.1f}% · z {r12.get('z',float('nan')):.2f}"),
    ("G3 12m 풀−MATCH>0 (일관성 값)",  g3, f"차이 {r12.get('match',float('nan'))*100:.2f}%p · t {r12.get('match_t',float('nan')):.2f}"),
    ("G4 2016+ 부호 유지",             g4, f"{(S12['pool12']-S12['univ12']).mean()*100 if len(S12) else float('nan'):.2f}%"),
]:
    print(f"  [{'통과' if ok else '실패'}] {nm:<34} {det}")

print("\n" + "-" * 88)
if g1 and g2:
    print(" 판정: 풀 승격 — 매수후보. " + ("일관성 조건 유지." if g3 else
          "단, G3 실패 → 일관성은 장식. e60 단독으로 단순화 후 1회 재검정."))
    if not g4: print(" 단서: G4 실패 → 비중 절반 + 전진 원장 12개월 병행 후 재판단.")
else:
    print(" 판정: 기각 — 풀은 매수 신호가 아니다. 관찰용 워치리스트로만 유지.")
    print("        진입 판단은 대량매도 신호 회피 + 진입/청산 규율에 맡긴다.")
print("-" * 88)

json.dump({k: {kk: (None if isinstance(vv, float) and not np.isfinite(vv) else vv)
               for kk, vv in v.items()} for k, v in res.items()},
          open(os.path.join(BASE, "_주도주풀_검정_요약.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("저장: _주도주풀_검정_원자료.csv · _주도주풀_검정_요약.json")
