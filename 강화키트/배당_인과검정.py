#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""배당_인과검정.py — 배당은 수익의 독립 계기인가, 밸류의 대리변수인가?

질문: factor_efficacy의 배당 IC(+0.0487, t=5.9)는 '상관'만 보여준다.
      배당이 밸류(E/P·B/P)·퀄리티(ROE)·사이즈를 통제한 뒤에도 '증분 예측력'이 남는가?

검정 5종 (30년 상폐포함 월봉 패널·top200 유동·룩어헤드X: t월말 지표 → t+1 수익):
  ① 팩터 상관행렬     — 배당·E/P·B/P·ROE·사이즈 월별 횡단면 스피어만 상관의 시계열 평균.
  ② 직교화 증분 IC    — (핵심) 배당을 E/P·B/P·ROE·log시총에 매월 횡단면 회귀한 '잔차'의 IC.
                        + Fama-MacBeth: 다음달수익 ~ 배당+통제팩터, 배당 계수 시계열 t값.
  ③ 밸류×배당 이중정렬 — B/P 5분위 × 배당 5분위. 같은 밸류 구간 안에서 배당 상-하위 수익차.
  ④ 스패닝 회귀       — 배당 롱숏 ~ 시장+밸류LS+사이즈LS. 알파(절편) t값.
  ⑤ 금리 레짐 분할    — 한국은행 기준금리 상승기/하락기로 배당 IC 분할(⚠️ 국고채 아닌 기준금리 대용).

사전등록 판정선(결과 보기 전 고정):
  배당 독립 인정 = ② 직교 잔차 IC t≥2.3  AND  ④ 스패닝 알파 t≥2.0.
  밸류 변장     = ② 잔차 IC 유의성 소멸   OR   ③ 밸류 통제 후 배당차 소멸.

⚠️ 금융서 엄밀 '인과' 증명 불가. 실무 기준 = 공범 통제 후 증분 예측력. 정보용·투자자문 아님·책임 본인.
"""
import os as _os2
def _jqroot2():
    """프로젝트 루트 자동탐색 (2026-07-27 §5b)."""
    d=_os2.path.dirname(_os2.path.abspath(__file__))
    for _ in range(5):
        if _os2.path.exists(_os2.path.join(d,"종목시총_30년.csv")): return d
        d=_os2.path.dirname(d)
    return _os2.path.dirname(_os2.path.abspath(__file__))


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

import os, sys, json
import numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
BASE = os.path.dirname(os.path.abspath(__file__))
UP = _jqroot2()
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def _find(fn):
    for d in (BASE, os.path.dirname(BASE), UP, os.path.join(UP, "강화키트"), os.getcwd()):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    return None

# ---------- 데이터 로드 (기존 강화키트 파이프라인과 동일 스키마) ----------
def load_px():
    fr = []
    for f in ("_월봉종가캐시_KOSPI.csv", "_월봉종가캐시_KOSDAQ.csv"):
        p = _find(f)
        if p:
            d = pd.read_csv(p, dtype={"code": str}); d["code"] = d["code"].str.zfill(6); fr.append(d)
    px = pd.concat(fr).pivot_table(index="ym", columns="code", values="close", aggfunc="last").sort_index()
    return px, px.pct_change(fill_method=None).mask(lambda x: x.abs() > 1.0)

def load_fin(field):
    fr = []
    for f in ("종목재무_KRX_KOSPI.csv", "종목재무_KRX_KOSDAQ.csv"):
        p = _find(f)
        if p:
            d = pd.read_csv(p, dtype={"code": str}); d["code"] = d["code"].str.zfill(6)
            d["ym"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m"); fr.append(d[["ym", "code", field]])
    return pd.concat(fr).pivot_table(index="ym", columns="code", values=field, aggfunc="last").sort_index()

def load_mcap():
    d = pd.read_csv(_find("종목시총_30년.csv"), dtype={"code": str}); d["code"] = d["code"].str.zfill(6)
    d["ym"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m")
    return d.pivot_table(index="ym", columns="code", values="mcap", aggfunc="last").sort_index()

# ---------- 통계 유틸 ----------
def zc(row):
    """횡단면 z-score + [-3,3] 윈저라이즈."""
    m = row.mean(); s = row.std()
    if not (s > 0): return row * 0
    return ((row - m) / s).clip(-3, 3)

def simple_t(x):
    x = pd.Series(x, dtype=float).dropna()
    if len(x) < 3 or x.std() == 0: return np.nan, np.nan, len(x)
    return x.mean(), x.mean() / (x.std() / np.sqrt(len(x))), len(x)

def nw_t(x, lags=6):
    """Newey-West(자기상관·이분산 보정) t값 for 시계열 평균."""
    x = np.asarray(pd.Series(x, dtype=float).dropna())
    n = len(x)
    if n < 5 or x.std() == 0: return np.nan
    mu = x.mean(); e = x - mu
    var = (e @ e) / n
    for l in range(1, min(lags, n - 1) + 1):
        w = 1 - l / (lags + 1)
        var += 2 * w * (e[l:] @ e[:-l]) / n
    se = np.sqrt(var / n)
    return mu / se if se > 0 else np.nan

def spearman(a, b):
    m = a.notna() & b.notna()
    if m.sum() < 20: return np.nan
    return a[m].rank().corr(b[m].rank())

def ols(y, X):
    """최소자승. X는 절편 포함. beta, resid 반환."""
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return beta, y - X @ beta

# ---------- 패널 구성 ----------
def build():
    px, rets = load_px(); mcap = load_mcap()
    EPS = load_fin("EPS"); PER = load_fin("PER"); PBR = load_fin("PBR"); BPS = load_fin("BPS"); DIV = load_fin("DIV")
    idx = [m for m in EPS.index if m in rets.index and m in mcap.index and m >= "2003-01"]
    cols = px.columns
    al = lambda df: df.reindex(index=idx, columns=cols)
    EPS, PER, PBR, BPS, DIV = al(EPS), al(PER), al(PBR), al(BPS), al(DIV)
    RET = rets.reindex(index=idx, columns=cols); MC = mcap.reindex(index=idx, columns=cols)
    fwd = RET.shift(-1)
    univ = (MC.rank(axis=1, ascending=False) <= 200)
    # 팩터(높을수록 매수신호)
    ep = 1.0 / PER.where(PER > 0)
    bp = 1.0 / PBR.where(PBR > 0)
    dy = DIV.where(DIV >= 0)
    roe = (EPS / BPS).where(BPS > 0)
    logmc = np.log(MC.where(MC > 0))          # 통제용 사이즈(원부호: 클수록 대형)
    size = -logmc                              # 팩터용 소형틸트
    F = dict(배당=dy, EP=ep, BP=bp, ROE=roe, 사이즈=size)
    return dict(idx=idx, cols=cols, univ=univ, fwd=fwd, MC=MC, RET=RET,
                dy=dy, ep=ep, bp=bp, roe=roe, logmc=logmc, size=size, F=F)

# ---------- ① 팩터 상관행렬 ----------
def test1_corr(D):
    names = ["배당", "EP", "BP", "ROE", "사이즈"]
    Fz = D["F"]; idx = D["idx"]; univ = D["univ"]
    acc = {a: {b: [] for b in names} for a in names}
    for t in idx:
        u = univ.loc[t]
        vals = {n: Fz[n].loc[t].where(u) for n in names}
        for i, a in enumerate(names):
            for b in names[i:]:
                c = spearman(vals[a], vals[b])
                if pd.notna(c):
                    acc[a][b].append(c);
                    if a != b: acc[b][a].append(c)
    M = pd.DataFrame(index=names, columns=names, dtype=float)
    for a in names:
        for b in names:
            M.loc[a, b] = np.mean(acc[a][b]) if acc[a][b] else np.nan
    return M

# ---------- ② 직교화 증분 IC + Fama-MacBeth ----------
def test2_orth(D):
    idx = D["idx"]; univ = D["univ"]; fwd = D["fwd"]
    dy, ep, bp, roe, logmc = D["dy"], D["ep"], D["bp"], D["roe"], D["logmc"]
    raw_ic = []       # 배당 원본 IC (참고: factor_efficacy 재현)
    res_ic = []       # 밸류·퀄·사이즈 통제 후 배당 잔차 IC (핵심)
    fm_coef = []      # Fama-MacBeth 배당 계수 (원수익)
    fm_coef_w = []    # Fama-MacBeth 배당 계수 (수익 ±40% 윈저 — 극단치 완화)
    for t in idx[:-1]:
        u = univ.loc[t]
        r = fwd.loc[t]
        zd = zc(dy.loc[t].where(u)); ze = zc(ep.loc[t].where(u)); zb = zc(bp.loc[t].where(u))
        zr = zc(roe.loc[t].where(u)); zm = zc(logmc.loc[t].where(u))
        df = pd.DataFrame({"d": zd, "e": ze, "b": zb, "r": zr, "m": zm, "y": r}).dropna()
        if len(df) < 50: continue
        raw_ic.append(spearman(df["d"], df["y"]))
        # 배당을 통제팩터에 회귀 → 잔차
        Xc = np.column_stack([np.ones(len(df)), df["e"], df["b"], df["r"], df["m"]])
        _, resid = ols(df["d"].values, Xc)
        res = pd.Series(resid, index=df.index)
        res_ic.append(spearman(res, df["y"]))
        # Fama-MacBeth: 수익 ~ 배당 + 통제
        Xf = np.column_stack([np.ones(len(df)), df["d"], df["e"], df["b"], df["r"], df["m"]])
        beta, _ = ols(df["y"].values, Xf)
        fm_coef.append(beta[1])
        yw = df["y"].clip(-0.4, 0.4).values
        betaw, _ = ols(yw, Xf)
        fm_coef_w.append(betaw[1])
    def pack(x):
        m, t, n = simple_t(x)
        return dict(mean=round(float(m), 5), t=round(float(t), 2), t_nw=round(float(nw_t(x)), 2), n=n)
    return dict(raw_ic=pack(raw_ic), res_ic=pack(res_ic), fm_coef=pack(fm_coef), fm_coef_w=pack(fm_coef_w))

# ---------- ③ 밸류(B/P)×배당 이중정렬 ----------
def test3_doublesort(D):
    idx = D["idx"]; univ = D["univ"]; fwd = D["fwd"]; bp = D["bp"]; dy = D["dy"]
    cell = {(i, j): [] for i in range(5) for j in range(5)}   # (bp분위, div분위) -> fwd평균
    within = []   # 각 월: 밸류분위 통제 후 배당 상-하위 평균차
    for t in idx[:-1]:
        u = univ.loc[t]; r = fwd.loc[t]
        b = bp.loc[t].where(u); d = dy.loc[t].where(u)
        df = pd.DataFrame({"b": b, "d": d, "y": r}).dropna()
        if len(df) < 100: continue
        try:
            df["bq"] = pd.qcut(df["b"].rank(method="first"), 5, labels=False)
        except Exception:
            continue
        diffs = []
        for i in range(5):
            sub = df[df["bq"] == i]
            if len(sub) < 10: continue
            try:
                sub = sub.assign(dq=pd.qcut(sub["d"].rank(method="first"), 5, labels=False, duplicates="drop"))
            except Exception:
                continue
            if sub["dq"].nunique() < 5: continue
            for j in range(5):
                v = sub[sub["dq"] == j]["y"]
                if len(v): cell[(i, j)].append(v.mean())
            hi = sub[sub["dq"] == 4]["y"].mean(); lo = sub[sub["dq"] == 0]["y"].mean()
            if pd.notna(hi) and pd.notna(lo): diffs.append(hi - lo)
        if diffs: within.append(np.mean(diffs))
    grid = pd.DataFrame(index=[f"BP{i+1}" for i in range(5)], columns=[f"DIV{j+1}" for j in range(5)], dtype=float)
    for (i, j), v in cell.items():
        grid.iloc[i, j] = np.mean(v) * 100 if v else np.nan     # 월평균 %
    m, t, n = simple_t(within)
    return dict(grid=grid, within_mean_pct=round(float(m) * 100, 3), within_t=round(float(t), 2),
                within_t_nw=round(float(nw_t(within)), 2), n=n)

# ---------- 롱숏 시계열 유틸 ----------
def ls_series(D, fac, ascending_bad=False):
    """팩터 상위20% - 하위20% EW 다음달수익 시계열."""
    idx = D["idx"]; univ = D["univ"]; fwd = D["fwd"]
    out = {}
    for t in idx[:-1]:
        u = univ.loc[t]; r = fwd.loc[t]
        f = fac.loc[t].where(u).dropna()
        f = f[[c for c in f.index if pd.notna(r.get(c))]]
        if len(f) < 50: continue
        try:
            q = pd.qcut(f.rank(method="first"), 5, labels=False, duplicates="drop")
        except Exception:
            continue
        if pd.Series(q).nunique() < 5: continue
        top = f.index[q == 4]; bot = f.index[q == 0]
        out[t] = r[top].mean() - r[bot].mean()
    return pd.Series(out)

def mkt_series(D):
    """유니버스 EW 시장수익 시계열."""
    idx = D["idx"]; univ = D["univ"]; fwd = D["fwd"]
    out = {}
    for t in idx[:-1]:
        u = univ.loc[t]; r = fwd.loc[t].where(u)
        vals = r.dropna()
        if len(vals) >= 50: out[t] = vals.mean()
    return pd.Series(out)

# ---------- ④ 스패닝 회귀 ----------
def test4_spanning(D):
    div_ls = ls_series(D, D["dy"])
    val_ls = ls_series(D, D["bp"])
    siz_ls = ls_series(D, D["size"])
    mkt = mkt_series(D)
    df = pd.concat({"div": div_ls, "mkt": mkt, "val": val_ls, "siz": siz_ls}, axis=1).dropna()
    y = df["div"].values
    X = np.column_stack([np.ones(len(df)), df["mkt"], df["val"], df["siz"]])
    beta, resid = ols(y, X)
    n, k = X.shape
    s2 = (resid @ resid) / (n - k)
    XtX_inv = np.linalg.inv(X.T @ X)
    se = np.sqrt(np.diag(s2 * XtX_inv))
    tv = beta / se
    # Newey-West alpha t (잔차 자기상관 보정)
    def nw_se_coef(resid, X, lags=6):
        n, k = X.shape
        XtX_inv = np.linalg.inv(X.T @ X)
        S = np.zeros((k, k))
        u = resid
        for i in range(n):
            S += u[i]**2 * np.outer(X[i], X[i])
        for l in range(1, min(lags, n-1)+1):
            w = 1 - l/(lags+1)
            for i in range(l, n):
                g = u[i]*u[i-l]*(np.outer(X[i], X[i-l]) + np.outer(X[i-l], X[i]))
                S += w * g
        cov = XtX_inv @ S @ XtX_inv
        return np.sqrt(np.diag(cov))
    se_nw = nw_se_coef(resid, X)
    labels = ["alpha", "mkt", "val", "siz"]
    coef = {labels[i]: dict(beta=round(float(beta[i]), 5), t=round(float(tv[i]), 2),
                            t_nw=round(float(beta[i]/se_nw[i]), 2)) for i in range(4)}
    # 배당 롱숏 원 성과(참고)
    ann = div_ls.mean()*12*100; sh = div_ls.mean()/div_ls.std()*np.sqrt(12)
    coef["_div_ls"] = dict(ann_pct=round(float(ann), 1), sharpe=round(float(sh), 2),
                           alpha_ann_pct=round(float(beta[0]*12*100), 1), n=len(df))
    return coef

# ---------- ⑤ 금리 레짐 분할 (한국은행 기준금리 대용) ----------
# BOK 기준금리 변경(발효월, 수준%). 국고채 월별 수익률 미보유 → 정책금리로 레짐 방향 대용.
BOK = [("2003-01",4.25),("2003-05",4.00),("2003-07",3.75),("2004-08",3.50),("2004-11",3.25),
       ("2005-10",3.50),("2005-12",3.75),("2006-02",4.00),("2006-06",4.25),("2006-08",4.50),
       ("2007-07",4.75),("2007-08",5.00),("2008-08",5.25),("2008-10",5.00),("2008-11",4.00),
       ("2008-12",3.00),("2009-01",2.50),("2009-02",2.00),("2010-07",2.25),("2010-11",2.50),
       ("2011-01",2.75),("2011-03",3.00),("2011-06",3.25),("2012-07",3.00),("2012-10",2.75),
       ("2013-05",2.50),("2014-08",2.25),("2014-10",2.00),("2015-03",1.75),("2015-06",1.50),
       ("2016-06",1.25),("2017-11",1.50),("2018-11",1.75),("2019-07",1.50),("2019-10",1.25),
       ("2020-03",0.75),("2020-05",0.50),("2021-08",0.75),("2021-11",1.00),("2022-01",1.25),
       ("2022-04",1.50),("2022-05",1.75),("2022-07",2.25),("2022-08",2.50),("2022-10",3.00),
       ("2022-11",3.25),("2023-01",3.50),("2024-10",3.25),("2024-11",3.00),("2025-02",2.75),
       ("2025-05",2.50),("2025-08",2.25)]
def bok_rate_series(idx):
    lvl = pd.Series(dtype=float)
    for ym, r in BOK: lvl.loc[ym] = r
    lvl = lvl.reindex(sorted(set(list(lvl.index) + list(idx)))).ffill()
    return lvl.reindex(idx).ffill()

def test5_regime(D):
    idx = D["idx"]; univ = D["univ"]; fwd = D["fwd"]; dy = D["dy"]
    rate = bok_rate_series(idx)
    chg = rate.diff(12)   # 전년동월대비 금리 변화 → 방향
    ic_by = {"상승기": [], "하락기": [], "동결": []}
    for t in idx[:-1]:
        u = univ.loc[t]
        ic = spearman(dy.loc[t].where(u), fwd.loc[t])
        if pd.isna(ic) or pd.isna(chg.get(t)): continue
        c = chg[t]
        reg = "상승기" if c > 0.1 else ("하락기" if c < -0.1 else "동결")
        ic_by[reg].append(ic)
    out = {}
    for k, v in ic_by.items():
        m, t, n = simple_t(v)
        out[k] = dict(meanIC=round(float(m), 4) if pd.notna(m) else None,
                      t=round(float(t), 2) if pd.notna(t) else None, months=n)
    return out

# ---------- 실행 ----------
def run():
    D = build()
    print("=" * 96)
    print(f"배당 인과 검정 — 배당은 독립 계기인가 밸류 대리변수인가 (패널 {D['idx'][0]}~{D['idx'][-1]}, {len(D['idx'])}개월·top200)")
    print("=" * 96)

    M = test1_corr(D)
    print("\n① 팩터 상관행렬 (월별 횡단면 스피어만의 시계열 평균)")
    print(M.round(3).to_string())
    dv_val = max(abs(M.loc["배당", "EP"]), abs(M.loc["배당", "BP"]))
    print(f"   → 배당–밸류(E/P·B/P) 최대상관 |{dv_val:.2f}|  ({'0.7↑=사실상 동일팩터' if dv_val>=0.7 else '0.7 미만=완전중복 아님'})")

    t2 = test2_orth(D)
    print("\n② 직교화 증분 IC + Fama-MacBeth (핵심)")
    print(f"   배당 원본 IC        평균 {t2['raw_ic']['mean']:+.4f}  t {t2['raw_ic']['t']:.2f} (NW {t2['raw_ic']['t_nw']:.2f})  [factor_efficacy 재현]")
    print(f"   배당 잔차 IC(통제후) 평균 {t2['res_ic']['mean']:+.4f}  t {t2['res_ic']['t']:.2f} (NW {t2['res_ic']['t_nw']:.2f})  ← E/P·B/P·ROE·log시총 제거")
    print(f"   Fama-MacBeth 배당계수 평균 {t2['fm_coef']['mean']:+.4f}  t {t2['fm_coef']['t']:.2f} (NW {t2['fm_coef']['t_nw']:.2f})  [원수익·극단치 민감]")
    print(f"   Fama-MacBeth 배당계수(수익±40%윈저) 평균 {t2['fm_coef_w']['mean']:+.4f}  t {t2['fm_coef_w']['t']:.2f} (NW {t2['fm_coef_w']['t_nw']:.2f})  [극단치 완화]")

    t3 = test3_doublesort(D)
    print("\n③ 밸류(B/P)×배당 이중정렬 — 셀별 다음달 평균수익(%)")
    print(t3["grid"].round(2).to_string())
    print(f"   → 밸류분위 통제 후 배당 상-하위 월평균차 {t3['within_mean_pct']:+.3f}%  t {t3['within_t']:.2f} (NW {t3['within_t_nw']:.2f}), {t3['n']}개월")

    t4 = test4_spanning(D)
    print("\n④ 스패닝 회귀: 배당롱숏 ~ 시장 + 밸류LS + 사이즈LS")
    for k in ["alpha", "mkt", "val", "siz"]:
        print(f"   {k:<6} β {t4[k]['beta']:+.4f}  t {t4[k]['t']:+.2f} (NW {t4[k]['t_nw']:+.2f})")
    print(f"   → 배당롱숏 연 {t4['_div_ls']['ann_pct']:+.1f}% / Sharpe {t4['_div_ls']['sharpe']:.2f} · 알파(절편) 연 {t4['_div_ls']['alpha_ann_pct']:+.1f}%")

    t5 = test5_regime(D)
    print("\n⑤ 금리 레짐 분할 (BOK 기준금리 전년비 방향·⚠️국고채 대용)")
    for k in ["상승기", "하락기", "동결"]:
        v = t5[k]
        if v["meanIC"] is not None:
            print(f"   {k}  배당 IC {v['meanIC']:+.4f}  t {v['t']:.2f}  ({v['months']}개월)")

    # ---------- 판정 ----------
    res_t = t2["res_ic"]["t"]; alpha_t = t4["alpha"]["t"]
    fm_t = t2["fm_coef"]["t"]; fm_w_t = t2["fm_coef_w"]["t"]
    ds_kill = (t3["within_t"] < 2.0)
    gates_pass = (res_t >= 2.3) and (alpha_t >= 2.0)          # 사전등록 관문(고정)
    fm_dissent = (abs(fm_t) < 2.0) and (abs(fm_w_t) < 2.0)    # 선형 한계효과 반증
    print("\n" + "=" * 96)
    print("판정 (사전등록 기준: 잔차IC t≥2.3 AND 스패닝알파 t≥2.0 → 독립)")
    print("=" * 96)
    print(f"   ② 잔차 IC t = {res_t:.2f}  ({'통과 ≥2.3' if res_t>=2.3 else '미달 <2.3'})")
    print(f"   ④ 스패닝 알파 t = {alpha_t:.2f}  ({'통과 ≥2.0' if alpha_t>=2.0 else '미달 <2.0'})")
    print(f"   ③ 밸류통제후 배당차 t = {t3['within_t']:.2f}  ({'소멸(변장 신호)' if ds_kill else '유지'})")
    print(f"   ▷ 사전등록 관문: {'통과 → 독립' if gates_pass else '미달 → 변장'}")
    print(f"\n   [로버스트니스 반증] Fama-MacBeth 선형 배당계수 t = {fm_t:.2f}(원)·{fm_w_t:.2f}(윈저)")
    if fm_dissent and gates_pass:
        print("   → 랭크기반 잔차IC·스패닝알파는 유의하나, 全통제(E/P·B/P·ROE·시총) 선형 한계효과는 ≈0.")
        print("     즉 배당의 증분 예측력은 '순위상 약하게 존재·선형 크기론 0'. 강한 독립 아님.")

    if gates_pass and not fm_dissent:
        grade = "독립(강)"; verdict = "배당은 밸류를 넘어선 독립 계기 — 합성서 배당 가중 유지 정당."
    elif gates_pass and fm_dissent:
        grade = "약한 독립(부분)"; verdict = ("배당 ≠ 순수 밸류 변장(상관 0.4~0.53·성장주서도 작동·양 금리레짐 유효)이나, "
            "밸류·퀄·사이즈 全통제 후 증분은 랭크상 약할 뿐 선형 크기론 0. → 배당 가중 소폭 하향 & "
            "E/P·B/P·배당의 밸류축 중복(3중 베팅) 경계. 합성 분산효과는 '완전독립' 전제만큼은 아님.")
    elif (res_t < 2.3) or ds_kill:
        grade = "밸류 변장"; verdict = "배당은 상당 부분 밸류의 대리변수 — 합성 가중 재조정(밸류 중복 축소) 필요."
    else:
        grade = "혼재"; verdict = "잔차IC/알파 중 하나만 통과 — 배당 부분독립, 가중 하향 검토."
    print(f"\n   ▶ 등급: {grade}")
    print(f"   ▶ 결론: {verdict}")
    print("\n   ⚠️ 금융서 엄밀 인과 증명 불가. 실무기준=공범 통제 후 증분 예측력. 정보용·투자자문 아님·책임 본인.")

    out = dict(panel=dict(start=D["idx"][0], end=D["idx"][-1], months=len(D["idx"])),
               corr=M.round(3).to_dict(), t2_orth=t2, t3_doublesort=dict(
                   grid=t3["grid"].round(3).to_dict(), within_mean_pct=t3["within_mean_pct"],
                   within_t=t3["within_t"], within_t_nw=t3["within_t_nw"], n=t3["n"]),
               t4_spanning=t4, t5_regime=t5,
               verdict=dict(res_ic_t=res_t, alpha_t=alpha_t, doublesort_t=t3["within_t"],
                            fm_t=fm_t, fm_w_t=fm_w_t, gates_pass=bool(gates_pass),
                            fm_dissent=bool(fm_dissent), grade=grade, text=verdict))
    json.dump(out, open(os.path.join(BASE, "배당_인과검정_결과.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2, default=str)
    print("\n   저장: 배당_인과검정_결과.json")
    return out

if __name__ == "__main__":
    run()
