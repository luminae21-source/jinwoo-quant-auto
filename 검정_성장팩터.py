# -*- coding: utf-8 -*-
r"""검정_성장팩터.py — '실제로 성장하는 회사'가 이기는가 (2026-07-30 사전등록)

[왜 이 검정인가]
  본체 엔진(배당·B/P·E/P·ROE)은 **설계상 가치·배당 엔진**이다.
  강원랜드·기업은행·한국가스공사가 나오는 건 오작동이 아니라 사양 그대로다.
  이 엔진은 구조적으로 대덕전자·하이닉스를 뽑을 수 없다 — PBR·PER이 높기 때문.

[구분해야 할 두 가지]
  (a) **과거 주가가 올랐다** → `검정_주도주풀_지속성.py`에서 **기각**(12m −4.58%, 36m −30.56%)
  (b) **실적이 실제로 성장한다** → **이 검정.** 아직 검정한 적 없다.
  둘은 다르다. (a)가 틀렸다고 (b)가 틀린 건 아니다.

[가설]
  H1  자본(BPS)이 꾸준히 성장하는 회사는 향후 시장을 이긴다.
  H2  이익(EPS) 성장도 마찬가지인가 — 아니면 시클리컬 잡음인가.
  H3  그 초과수익이 **밸류에이션 효과가 아닌가** (성장주는 비싸다 → PBR 매칭 대조군 필요)

[팩터 — 형성월 t 시점 정보만]
  g_bps  BPS 3년 CAGR                      (자본 복리 성장)
  g_eps  EPS 3년 CAGR (양끝 EPS>0)         (이익 성장)
  g_con  최근 3년 BPS 연속 증가 횟수 0~3     (성장의 '꾸준함')
  roe3   ROE(EPS/BPS) 3개 시점 평균          (수익성 수준)
  MIX    위 4개 z 평균

[게이트 — 개봉 전 확정]
  A  12m (top30 − UNIV) > 0  AND  HAC t ≥ 2.0
  B  12m 승률 ≥ 55%  AND  z ≥ 1.64
  C  12m (top30 − PBR매칭대조군) > 0        ← 밸류 효과가 아님
  D  2016+ 부분표본 부호 유지

[판정 규칙]
  A∧B 통과 → **성장 트랙 선정 엔진**을 만든다 (본체와 별도 레인).
  C 실패    → 성장이 아니라 그냥 고PBR 프리미엄. 팩터로 채택하지 않는다.
  전부 실패 → 성장은 이 데이터로 잡히지 않는다. 대덕전자류는 **재량 트랙(형의 지식)**으로만 간다.

사용: py 검정_성장팩터.py
⚠️ 과거 통계. 투자자문 아님.
"""
import os, sys, math, json
import numpy as np, pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

TOPN, PX_FLOOR = 30, 1000
HORIZONS = [12, 24, 36]


def _find(fn):
    for d in (BASE, os.path.join(BASE, "데이터수리"), os.path.dirname(BASE), os.getcwd()):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    raise FileNotFoundError(fn)


def hac_t(x, lag):
    x = np.asarray(x, float); x = x[~np.isnan(x)]; n = len(x)
    if n < 5: return np.nan
    m = x.mean(); e = x - m; s = (e @ e) / n
    for L in range(1, min(lag, n - 1) + 1):
        s += 2 * (1 - L / (lag + 1)) * ((e[L:] @ e[:-L]) / n)
    return m / math.sqrt(s / n) if s > 0 else np.nan


def z_prop(k, n):
    return (k / n - .5) / math.sqrt(.25 / n) if n else np.nan


def zsc(s):
    sd = s.std(ddof=0)
    return (s - s.mean()) / sd if sd and sd > 0 else s * 0


print("=" * 92)
print(" 성장 팩터 검정 — '실적이 성장하는 회사'는 이기는가")
print("=" * 92)

P = pd.read_csv(_find("_월봉_KIS_전기간.csv"), dtype={"code": str})
P["code"] = P["code"].str.zfill(6)
PX = P.pivot_table(index="ym", columns="code", values="close", aggfunc="last").sort_index()
PX = PX.where(PX >= PX_FLOOR)

fs = []
for m in ("KOSPI", "KOSDAQ"):
    fs.append(pd.read_csv(_find(f"종목재무_KRX_{m}.csv"), dtype={"code": str},
                          usecols=["date", "code", "BPS", "EPS", "PBR"]))
F = pd.concat(fs); F["code"] = F["code"].str.zfill(6); F["ym"] = F["date"].str[:7]
for c in ("BPS", "EPS", "PBR"): F[c] = pd.to_numeric(F[c], errors="coerce")
BPS = F.pivot_table(index="ym", columns="code", values="BPS", aggfunc="last").reindex(index=PX.index, columns=PX.columns)
EPS = F.pivot_table(index="ym", columns="code", values="EPS", aggfunc="last").reindex(index=PX.index, columns=PX.columns)
PBR = F.pivot_table(index="ym", columns="code", values="PBR", aggfunc="last").reindex(index=PX.index, columns=PX.columns)
print(f"가격 {PX.shape} · 재무 BPS {int(BPS.notna().sum(axis=1).median())}종목/월(중위)")

MC = pd.read_csv(_find("종목시총_30년.csv"), dtype={"code": str})
MC["code"] = MC["code"].str.zfill(6); MC["ym"] = MC["date"].astype(str).str[:7]
MCP = MC.pivot_table(index="ym", columns="code", values="mcap", aggfunc="last").reindex(index=PX.index, columns=PX.columns)

K = pd.read_csv(_find("kospi_index_daily.csv")); K["ym"] = K["Date"].astype(str).str[:7]
KI = K.groupby("ym")["Close"].last().reindex(PX.index)

T = pd.read_csv(_find("소멸_재분류_v1.csv"), dtype={"code": str}); T["code"] = T["code"].str.zfill(6)
TERM = dict(zip(T["code"], T["terminal_ret"].astype(float)))

months = list(PX.index); midx = {m: i for i, m in enumerate(months)}


def fwd(codes, i0, H):
    i1 = i0 + H
    if i1 >= len(months): return np.nan
    p0 = PX.iloc[i0]; sub = PX.iloc[i0 + 1:i1 + 1]; out = []
    for c in codes:
        b = p0.get(c, np.nan)
        if not np.isfinite(b): continue
        s = sub[c].dropna() if c in sub.columns else pd.Series(dtype=float)
        if len(s) == 0: out.append(TERM.get(c, -.5)); continue
        r = s.iloc[-1] / b - 1
        if midx[s.index[-1]] < i1: r = (1 + r) * (1 + TERM.get(c, -.5)) - 1
        out.append(r)
    return float(np.mean(out)) if out else np.nan


FACTORS = ["g_bps", "g_eps", "g_con", "roe3", "MIX"]
forms = [m for m in months if int(m[5:7]) in (6, 12) and midx[m] >= 60 and m >= "2005-06"]
print(f"형성월 {len(forms)}회 {forms[0]} ~ {forms[-1]}")

rows = []
for m in forms:
    i = midx[m]
    px = PX.iloc[i]
    ok = px.notna() & PX.iloc[i - 60].notna()
    mc = MCP.iloc[i]
    if mc.notna().sum() < 50: continue
    ok &= (mc >= mc[ok & mc.notna()].median())
    b0, b12, b24, b36 = (BPS.iloc[i], BPS.iloc[i - 12], BPS.iloc[i - 24], BPS.iloc[i - 36])
    e0, e36 = EPS.iloc[i], EPS.iloc[i - 36]
    ok &= (b0 > 0) & (b36 > 0) & b12.notna() & b24.notna()
    univ = list(px.index[ok])
    if len(univ) < 80: continue

    g_bps = (b0[univ] / b36[univ]) ** (1 / 3) - 1
    with np.errstate(all="ignore"):
        g_eps = pd.Series(np.where((e0[univ] > 0) & (e36[univ] > 0),
                                   (e0[univ] / e36[univ]) ** (1 / 3) - 1, np.nan), index=univ)
    g_con = ((b0[univ] > b12[univ]).astype(int) + (b12[univ] > b24[univ]).astype(int)
             + (b24[univ] > b36[univ]).astype(int)).astype(float)
    roe3 = pd.concat([(EPS.iloc[i - k][univ] / BPS.iloc[i - k][univ]) for k in (0, 12, 24)],
                     axis=1).mean(axis=1)

    D = pd.DataFrame({"g_bps": g_bps, "g_eps": g_eps, "g_con": g_con, "roe3": roe3,
                      "pbr": PBR.iloc[i][univ]})
    D["g_eps"] = D["g_eps"].fillna(D["g_eps"].median())
    D = D.dropna(subset=["g_bps", "g_con", "roe3"])
    if len(D) < 60: continue
    D["MIX"] = (zsc(D["g_bps"]) + zsc(D["g_eps"]) + zsc(D["g_con"]) + zsc(D["roe3"])) / 4

    r = {"ym": m, "n_univ": len(univ)}
    for H in HORIZONS: r[f"u{H}"] = fwd(univ, i, H)
    for f in FACTORS:
        top = D.nlargest(TOPN, f)
        for H in HORIZONS: r[f"{f}_{H}"] = fwd(top.index.tolist(), i, H)
        if f == "MIX":                      # PBR 매칭 대조군 (밸류 효과 분리)
            rest = D.drop(index=top.index).copy(); used, mt = set(), []
            for v in top["pbr"].values:
                if not np.isfinite(v): continue
                cc = rest[~rest.index.isin(used) & rest["pbr"].notna()]
                if len(cc) == 0: break
                j = (cc["pbr"] - v).abs().idxmin(); used.add(j); mt.append(j)
            for H in HORIZONS: r[f"pbrmatch_{H}"] = fwd(mt, i, H) if len(mt) >= 10 else np.nan
            r["pbr_top"] = top["pbr"].median(); r["pbr_univ"] = D["pbr"].median()
    rows.append(r)

R = pd.DataFrame(rows)
R.to_csv(os.path.join(BASE, "_성장팩터_검정_원자료.csv"), index=False, encoding="utf-8-sig")
print(f"유효 형성월 {len(R)}회 · 평균 유니버스 {R.n_univ.mean():.0f}종목")
print(f"MIX top30 PBR 중위 {R.pbr_top.median():.2f} vs 유니버스 {R.pbr_univ.median():.2f}")

print("\n" + "=" * 92)
print(f"{'팩터':<8} {'H':>4} {'N':>4} {'포트':>9} {'UNIV':>9} {'차':>9} {'HACt':>7} {'승률':>7} {'z':>6} {'2016+':>8}")
print("-" * 92)
res = {}
for f in FACTORS:
    for H in HORIZONS:
        d = R.dropna(subset=[f"{f}_{H}", f"u{H}"])
        if len(d) == 0: continue
        df_ = (d[f"{f}_{H}"] - d[f"u{H}"]).values
        t = hac_t(df_, max(2, H // 6)); k = int((df_ > 0).sum()); n = len(df_)
        d2 = d[d.ym >= "2016-01"]
        s16 = (d2[f"{f}_{H}"] - d2[f"u{H}"]).mean() if len(d2) else np.nan
        res[f"{f}_{H}"] = dict(n=n, diff=df_.mean(), t=t, win=k / n, z=z_prop(k, n), s16=s16)
        print(f"{f:<8} {H:>3}m {n:>4} {d[f'{f}_{H}'].mean()*100:>8.2f}% {d[f'u{H}'].mean()*100:>8.2f}%"
              f" {df_.mean()*100:>8.2f}% {t:>7.2f} {k/n*100:>6.1f}% {z_prop(k,n):>6.2f} {s16*100:>7.2f}%")
    print("-" * 92)

print("\n[밸류 효과 분리 — MIX vs PBR 매칭 대조군]")
for H in HORIZONS:
    d = R.dropna(subset=[f"MIX_{H}", f"pbrmatch_{H}"])
    if len(d) == 0: continue
    v = (d[f"MIX_{H}"] - d[f"pbrmatch_{H}"]).values
    print(f"  {H:>2}m N={len(d):>2}  MIX {d[f'MIX_{H}'].mean()*100:7.2f}%  PBR매칭 {d[f'pbrmatch_{H}'].mean()*100:7.2f}%"
          f"  차 {v.mean()*100:+7.2f}%  HACt {hac_t(v, max(2,H//6)):5.2f}  승률 {(v>0).mean()*100:5.1f}%")

print("\n" + "=" * 92)
print(" 게이트 판정 (MIX 기준 · 12개월)")
print("=" * 92)
r12 = res.get("MIX_12", {})
dpm = R.dropna(subset=["MIX_12", "pbrmatch_12"])
cdiff = (dpm["MIX_12"] - dpm["pbrmatch_12"]).mean() if len(dpm) else np.nan
gA = bool(r12 and r12["diff"] > 0 and np.isfinite(r12["t"]) and r12["t"] >= 2.0)
gB = bool(r12 and r12["win"] >= .55 and np.isfinite(r12["z"]) and r12["z"] >= 1.64)
gC = bool(np.isfinite(cdiff) and cdiff > 0)
gD = bool(r12 and np.isfinite(r12["s16"]) and r12["s16"] > 0)
for nm, ok, det in [("A 12m MIX−UNIV>0 & t≥2.0", gA, f"{r12.get('diff',np.nan)*100:.2f}% · t {r12.get('t',np.nan):.2f}"),
                    ("B 12m 승률≥55% & z≥1.64", gB, f"{r12.get('win',np.nan)*100:.1f}% · z {r12.get('z',np.nan):.2f}"),
                    ("C 12m MIX−PBR매칭>0", gC, f"{cdiff*100:.2f}%p"),
                    ("D 2016+ 부호 유지", gD, f"{r12.get('s16',np.nan)*100:.2f}%")]:
    print(f"  [{'통과' if ok else '실패'}] {nm:<30} {det}")

print("-" * 92)
if gA and gB and gC:
    print(" 판정: 성장 팩터 채택 — 본체와 별도 '성장 트랙' 선정 엔진을 만든다.")
elif gA and gB:
    print(" 판정: 초과수익은 있으나 PBR 매칭에서 사라짐 → 성장이 아니라 밸류에이션 효과. 채택 안 함.")
else:
    print(" 판정: 기각 — 성장은 이 팩터로 잡히지 않는다.")
    print("        대덕전자·하이닉스류는 재량 트랙(본인 지식)으로 가고, 시스템은 진입/청산 규율만 댄다.")
print("-" * 92)
json.dump({k: {kk: (None if isinstance(vv, float) and not np.isfinite(vv) else vv) for kk, vv in v.items()}
           for k, v in res.items()}, open(os.path.join(BASE, "_성장팩터_검정_요약.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)
print("저장: _성장팩터_검정_원자료.csv · _성장팩터_검정_요약.json")
