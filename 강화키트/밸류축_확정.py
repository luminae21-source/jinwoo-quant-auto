#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""밸류축_확정.py — 밸류 팩터 축 확정: 배당·E/P·B/P·EV/EBIT 중복·증분·합성 분산

배경: 배당 인과검정 결과 '약한 독립'(밸류·퀄·사이즈 全통제 후 선형 증분≈0, 랭크상 약함).
      EV/EBITDA는 감가상각 커버리지 26% 한계로 접음. FCF수익률은 무효(t=1.1·Sharpe-0.36).
      → 쓸 밸류 팩터는 배당·E/P·B/P·EV/EBIT 4종. 이들이 얼마나 겹치고(3중 베팅?),
        합성이 진짜 분산되나, 각자 증분이 있나를 확정한다.

2중 창:
  · 장기(2003~2026, 252개월): 배당·E/P·B/P 가치 삼각 — 대표본. (EV/EBIT 미존재 구간)
  · 단기(2021-04~, DART 5년): +EV/EBIT 포함 4종 비교.

분석:
  ① 팩터 상관행렬(월별 횡단면 스피어만 시계열 평균)
  ② 단독 IC·롱숏 Sharpe
  ③ 롱숏 월수익 상관 — 진짜 분산효과 측정(높으면 3중 베팅)
  ④ 증분 잔차 IC — 각 팩터가 나머지 밸류 팩터 통제 후 남는가
  ⑤ 등가중 합성 vs 최강 단일 — 합성 이득 확인
→ 권고: 밸류축 구성·가중.
⚠️ 정보용·과거통계·미래보장 아님. 투자자문 아님·책임 본인.
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

import os, sys, json, numpy as np, pandas as pd, warnings
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

def load_px():
    fr = []
    for f in ("_월봉종가캐시_KOSPI.csv", "_월봉종가캐시_KOSDAQ.csv"):
        p = _find(f)
        if p: d = pd.read_csv(p, dtype={"code": str}); d["code"] = d["code"].str.zfill(6); fr.append(d)
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

def zc(row):
    m = row.mean(); s = row.std()
    return ((row - m) / s).clip(-3, 3) if s > 0 else row * 0
def spearman(a, b):
    m = a.notna() & b.notna()
    if m.sum() < 20: return np.nan
    return a[m].rank().corr(b[m].rank())
def simple_t(x):
    x = pd.Series(x, dtype=float).dropna()
    if len(x) < 3 or x.std() == 0: return np.nan, np.nan, len(x)
    return x.mean(), x.mean() / (x.std() / np.sqrt(len(x))), len(x)
def ols_resid(y, X):
    beta, *_ = np.linalg.lstsq(X, y, rcond=None)
    return y - X @ beta

# ---------- 패널 ----------
def build():
    px, rets = load_px(); mcap = load_mcap()
    EPS = load_fin("EPS"); PER = load_fin("PER"); PBR = load_fin("PBR"); BPS = load_fin("BPS"); DIV = load_fin("DIV")
    idx = [m for m in EPS.index if m in rets.index and m in mcap.index and m >= "2003-01"]
    cols = px.columns
    al = lambda df: df.reindex(index=idx, columns=cols)
    EPS, PER, PBR, BPS, DIV = al(EPS), al(PER), al(PBR), al(BPS), al(DIV)
    RET = rets.reindex(index=idx, columns=cols); MC = mcap.reindex(index=idx, columns=cols)
    ep = 1.0 / PER.where(PER > 0); bp = 1.0 / PBR.where(PBR > 0); dy = DIV.where(DIV >= 0)
    # EV/EBIT (DART, PIT지연) — 재무상세_EBITDA.csv
    ebit_ev = pd.DataFrame(index=idx, columns=cols, dtype=float)
    p = _find("재무상세_EBITDA.csv")
    if p:
        fd = pd.read_csv(p, dtype={"code": str}); fd["code"] = fd["code"].str.zfill(6)
        OI = fd.pivot_table(index="fiscal_year", columns="code", values="op_income", aggfunc="last")
        ND = fd.pivot_table(index="fiscal_year", columns="code", values="net_debt", aggfunc="last")
        for ym in idx:
            y, m = int(ym[:4]), int(ym[5:7]); fy = y - 1 if m >= 4 else y - 2
            if fy not in OI.index: continue
            oi = OI.loc[fy].reindex(cols); nd = ND.loc[fy].reindex(cols).fillna(0)
            ev = MC.loc[ym].reindex(cols) + nd
            ebit_ev.loc[ym] = (oi / ev).where((ev > 0) & oi.notna())
    F = {"배당": dy, "E/P": ep, "B/P": bp, "EV/EBIT": ebit_ev}
    univ = (MC.rank(axis=1, ascending=False) <= 200)
    return dict(idx=idx, cols=cols, univ=univ, fwd=RET.shift(-1), F=F)

# ---------- 분석 루틴(창 지정) ----------
def corr_matrix(D, names, months):
    acc = {a: {b: [] for b in names} for a in names}
    for t in months:
        u = D["univ"].loc[t]
        vals = {n: D["F"][n].loc[t].where(u) for n in names}
        for i, a in enumerate(names):
            for b in names[i:]:
                c = spearman(vals[a], vals[b])
                if pd.notna(c):
                    acc[a][b].append(c)
                    if a != b: acc[b][a].append(c)
    M = pd.DataFrame(index=names, columns=names, dtype=float)
    for a in names:
        for b in names:
            M.loc[a, b] = np.mean(acc[a][b]) if acc[a][b] else np.nan
    return M

def ls_series(D, fac, months):
    fwd = D["fwd"]; out = {}
    for t in months:
        u = D["univ"].loc[t]; r = fwd.loc[t]
        f = fac.loc[t].where(u).dropna()
        f = f[[c for c in f.index if pd.notna(r.get(c))]]
        if len(f) < 40: continue
        try:
            q = pd.qcut(f.rank(method="first"), 5, labels=False, duplicates="drop")
        except Exception: continue
        if pd.Series(q).nunique() < 5: continue
        out[t] = r[f.index[q == 4]].mean() - r[f.index[q == 0]].mean()
    return pd.Series(out)

def standalone(D, names, months):
    res = {}
    for n in names:
        fac = D["F"][n]; ics = []
        for t in months:
            u = D["univ"].loc[t]
            ic = spearman(fac.loc[t].where(u), D["fwd"].loc[t])
            if pd.notna(ic): ics.append(ic)
        m, tt, k = simple_t(ics)
        ls = ls_series(D, fac, months)
        res[n] = dict(meanIC=round(float(m), 4), ic_t=round(float(tt), 2), n_ic=k,
                      ls_ann=round(float(ls.mean() * 12 * 100), 1),
                      ls_sharpe=round(float(ls.mean() / ls.std() * np.sqrt(12)), 2) if ls.std() > 0 else None)
    return res

def ls_corr(D, names, months):
    S = {n: ls_series(D, D["F"][n], months) for n in names}
    df = pd.concat(S, axis=1).dropna()
    return df.corr(method="pearson"), len(df)

def incremental(D, target, controls, months):
    """target 을 controls 에 매월 횡단면 회귀한 잔차의 IC."""
    ics = []
    for t in months:
        u = D["univ"].loc[t]
        cols_data = {"y": D["fwd"].loc[t], "d": zc(D["F"][target].loc[t].where(u))}
        for i, c in enumerate(controls):
            cols_data[f"c{i}"] = zc(D["F"][c].loc[t].where(u))
        df = pd.DataFrame(cols_data).dropna()
        if len(df) < 50: continue
        X = np.column_stack([np.ones(len(df))] + [df[f"c{i}"].values for i in range(len(controls))])
        res = ols_resid(df["d"].values, X)
        ics.append(spearman(pd.Series(res, index=df.index), df["y"]))
    m, tt, k = simple_t(ics)
    return dict(meanIC=round(float(m), 4), t=round(float(tt), 2), n=k)

def composite(D, names, months):
    """등가중 z-score 합성 팩터의 IC·롱숏."""
    comp = pd.DataFrame(index=months, columns=D["cols"], dtype=float)
    for t in months:
        u = D["univ"].loc[t]
        zs = [zc(D["F"][n].loc[t].where(u)) for n in names]
        cnt = sum(z.notna().astype(int) for z in zs)
        s = sum(z.fillna(0) for z in zs)
        comp.loc[t] = s.where(cnt >= max(2, len(names) - 1))
    ics = []
    for t in months:
        ic = spearman(comp.loc[t], D["fwd"].loc[t])
        if pd.notna(ic): ics.append(ic)
    m, tt, k = simple_t(ics)
    ls = ls_series(D, comp, months)
    return dict(meanIC=round(float(m), 4), ic_t=round(float(tt), 2),
                ls_ann=round(float(ls.mean() * 12 * 100), 1),
                ls_sharpe=round(float(ls.mean() / ls.std() * np.sqrt(12)), 2) if ls.std() > 0 else None)

def run():
    D = build()
    idx = D["idx"]
    long_m = [m for m in idx[:-1]]                        # 2003~
    short_m = [m for m in idx[:-1] if m >= "2021-04"]     # DART 창
    OUT = {}

    print("=" * 96)
    print(f"밸류축 확정 — 배당·E/P·B/P·EV/EBIT 중복·증분·합성 (장기 {long_m[0]}~{long_m[-1]} {len(long_m)}m / 단기 {short_m[0]}~{short_m[-1]} {len(short_m)}m)")
    print("=" * 96)

    # ===== 장기: 가치 삼각 =====
    tri = ["배당", "E/P", "B/P"]
    print("\n【장기 2003~】 가치 삼각 배당·E/P·B/P")
    Mc = corr_matrix(D, tri, long_m); print("\n① 팩터 상관행렬(횡단면 스피어만 시계열평균)"); print(Mc.round(3).to_string())
    st = standalone(D, tri, long_m)
    print("\n② 단독 효력"); print(f"   {'팩터':<6}{'평균IC':>9}{'IC t':>7}{'롱숏연%':>9}{'Sharpe':>8}")
    for n in tri:
        v = st[n]; print(f"   {n:<6}{v['meanIC']:>+9.4f}{v['ic_t']:>7.2f}{v['ls_ann']:>+8.1f}%{(v['ls_sharpe'] or 0):>8.2f}")
    lc, nlc = ls_corr(D, tri, long_m)
    print(f"\n③ 롱숏 월수익 상관 (분산효과 · {nlc}개월)"); print(lc.round(2).to_string())
    avg_off = (lc.values[np.triu_indices(len(tri), 1)]).mean()
    print(f"   평균 비대각 상관 {avg_off:.2f}  ({'높음→3중 베팅' if avg_off>=0.6 else '중간→부분 분산'})")
    print("\n④ 증분 잔차 IC (나머지 둘 통제 후)")
    inc = {}
    for n in tri:
        ctrl = [x for x in tri if x != n]; r = incremental(D, n, ctrl, long_m); inc[n] = r
        print(f"   {n:<6} vs {'+'.join(ctrl):<10} 잔차IC {r['meanIC']:+.4f}  t {r['t']:.2f}  ({'유의' if abs(r['t'])>=2 else '약함/소멸'})")
    cmp3 = composite(D, tri, long_m)
    best_single = max(st.values(), key=lambda v: v['ls_sharpe'] or -9)
    print(f"\n⑤ 등가중 합성 vs 최강단일: 합성 IC {cmp3['meanIC']:+.4f}(t{cmp3['ic_t']:.2f}) 롱숏 {cmp3['ls_ann']:+.1f}%/Sharpe {cmp3['ls_sharpe']:.2f}"
          f"  · 최강단일 Sharpe {best_single['ls_sharpe']:.2f} → {'합성 개선' if (cmp3['ls_sharpe'] or 0)>(best_single['ls_sharpe'] or 0) else '유사(분산 제한)'}")
    OUT["long"] = dict(corr=Mc.round(3).to_dict(), standalone=st, ls_corr=lc.round(3).to_dict(),
                       ls_corr_avg=round(float(avg_off), 3), incremental=inc, composite=cmp3)

    # ===== 단기: +EV/EBIT =====
    quad = ["배당", "E/P", "B/P", "EV/EBIT"]
    print("\n" + "-" * 96)
    print("【단기 2021~】 +EV/EBIT 포함 4종")
    Mc2 = corr_matrix(D, quad, short_m); print("\n① 팩터 상관행렬"); print(Mc2.round(3).to_string())
    st2 = standalone(D, quad, short_m)
    print("\n② 단독 효력"); print(f"   {'팩터':<8}{'평균IC':>9}{'IC t':>7}{'롱숏연%':>9}{'Sharpe':>8}")
    for n in quad:
        v = st2[n]; print(f"   {n:<8}{v['meanIC']:>+9.4f}{v['ic_t']:>7.2f}{v['ls_ann']:>+8.1f}%{(v['ls_sharpe'] or 0):>8.2f}")
    print("\n④ EV/EBIT 증분 (E/P·B/P 통제 후) — EV가 부채정보로 더 주나?")
    incEV = incremental(D, "EV/EBIT", ["E/P", "B/P"], short_m)
    print(f"   EV/EBIT vs E/P+B/P 잔차IC {incEV['meanIC']:+.4f}  t {incEV['t']:.2f}  ({'증분 유의' if abs(incEV['t'])>=2 else '증분 약함'})")
    OUT["short"] = dict(corr=Mc2.round(3).to_dict(), standalone=st2, ev_incremental=incEV)

    # ===== 권고 =====
    print("\n" + "=" * 96); print("권고 — 밸류축 구성"); print("=" * 96)
    rec = []
    rec.append(f"· 삼각 상관 평균 {avg_off:.2f}: 배당·E/P·B/P 롱숏이 {'강하게 동조(사실상 한 베팅)' if avg_off>=0.6 else '부분 분산(완전독립 아님)'}.")
    surv = [n for n in tri if abs(inc[n]['t']) >= 2]
    rec.append(f"· 나머지 둘 통제 후 증분 살아남는 팩터: {', '.join(surv) if surv else '없음'} (t≥2 기준).")
    rec.append(f"· EV/EBIT 증분(E/P·B/P 대비) t {incEV['t']:.2f} → {'별도 슬롯 값어치' if abs(incEV['t'])>=2 else '가치 낮음, 대표 밸류로 흡수'}.")
    rec.append("· 실무안: 밸류축을 개별 3~4팩터 나열 대신 '밸류 합성 1블록'으로 묶어 축 비중을 통제하라"
               " (배당+E/P+B/P를 각각 만점 주면 밸류에 3배 노출=의도치 않은 집중).")
    for r in rec: print(" ", r)
    print("\n  ⚠️ 과거통계·미래보장 아님. 투자자문 아님·책임 본인.")
    OUT["recommend"] = rec
    json.dump(OUT, open(os.path.join(BASE, "밸류축_확정_결과.json"), "w", encoding="utf-8"),
              ensure_ascii=False, indent=2, default=str)
    print("\n  저장: 밸류축_확정_결과.json")
    return OUT

if __name__ == "__main__":
    run()
