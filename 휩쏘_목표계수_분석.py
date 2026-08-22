# -*- coding: utf-8 -*-
r"""휩쏘_목표계수_분석.py — 과제① 집계·검정

[읽는 법]
  · 카드 표본 = 잔여봉 ≥ 40  (40봉 창이 실제로 끝난 이벤트만)
  · 2단 표본 = 잔여봉 ≥ 126 (126봉 창이 실제로 끝난 이벤트만)
    ↳ 이 필터가 없으면 2026년 진행분이 '만기 청산'으로 위장되어 섞인다.
  · 신뢰구간은 전부 **연도블록 부트스트랩**. 사건이 위기연도에 뭉쳐 있어
    보통 부트스트랩은 구간을 좁게(=과신하게) 만든다.
  · Δ(k) 는 **같은 이벤트 안에서의 짝지은 차이** — k만 바꾼 것이므로 짝짓기가 맞다.
  · 체인−기타 는 짝지을 수 없는 독립 비교다. 연도블록으로 같이 흔든다.
"""
import sys, json, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
HERE = "/home/claude/jq"
KS = [50, 75, 100, 125, 150]
B = 3000
rng = np.random.default_rng(20260802)

R = pd.concat([pd.read_csv(f"{HERE}/목표계수_이벤트_{m}.csv", dtype={"code": str})
               for m in ("KOSPI", "KOSDAQ")], ignore_index=True)
R["code"] = R["code"].str.zfill(6)
R = R[R["국면"] == "실행"].copy()


def _agg(years, vals):
    """연도별 (합, 개수) 행렬. vals: (n,) 또는 (n,m)"""
    uy = np.unique(years)
    V = vals if vals.ndim == 2 else vals[:, None]
    S = np.zeros((len(uy), V.shape[1])); C = np.zeros(len(uy))
    for i, y in enumerate(uy):
        m = years == y
        S[i] = V[m].sum(axis=0); C[i] = m.sum()
    return uy, S, C


def yb_mean(years, vals, B=B):
    """연도블록 부트스트랩 평균 — 연도 단위 합/개수만 재추출하므로 빠르고 결과는 동일."""
    uy, S, C = _agg(years, np.asarray(vals, float))
    pick = rng.integers(0, len(uy), size=(B, len(uy)))
    num = S[pick].sum(axis=1); den = C[pick].sum(axis=1)
    r = num / den[:, None]
    return r[:, 0] if r.shape[1] == 1 else r


def yb_gap(years, vals, isA, B=B):
    """같은 연도블록 추출로 A그룹 평균 − B그룹 평균."""
    v = np.asarray(vals, float)
    V = v if v.ndim == 2 else v[:, None]
    uy = np.unique(years); m = V.shape[1]
    SA = np.zeros((len(uy), m)); CA = np.zeros(len(uy))
    SB = np.zeros((len(uy), m)); CB = np.zeros(len(uy))
    for i, y in enumerate(uy):
        ma = (years == y) & isA; mb = (years == y) & ~isA
        SA[i] = V[ma].sum(axis=0); CA[i] = ma.sum()
        SB[i] = V[mb].sum(axis=0); CB[i] = mb.sum()
    pick = rng.integers(0, len(uy), size=(B, len(uy)))
    with np.errstate(invalid="ignore", divide="ignore"):
        a = SA[pick].sum(axis=1) / np.maximum(CA[pick].sum(axis=1), 1)[:, None]
        b = SB[pick].sum(axis=1) / np.maximum(CB[pick].sum(axis=1), 1)[:, None]
    return a - b


def ci(arr):
    return float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))


def desc(sub, col, howcol=None):
    v = sub[col].values * 100
    d = dict(n=int(len(sub)), 평균=round(float(v.mean()), 2),
             중앙=round(float(np.median(v)), 2),
             승률=round(float((v > 0).mean() * 100), 1),
             표준편차=round(float(v.std(ddof=1)), 2))
    if howcol is not None:
        h = sub[howcol]
        d["목표도달"] = round(float((h == "목표").mean() * 100), 1)
        d["손절"] = round(float((h == "손절").mean() * 100), 1)
        d["트레일"] = round(float((h == "트레일").mean() * 100), 1)
        d["만기"] = round(float((h == "만기").mean() * 100), 1)
        d["평균봉"] = round(float(sub[howcol.replace("how", "봉")].mean()), 1)
    return d


OUT = {}
for tag, mask in (("정식A", R["등급"] == "정식A"), ("A+S2α", R["등급"].isin(["정식A", "S2-α"]))):
    base = R[mask]
    blk = {}
    for mode, col, hcol, need in (("카드", "카드_k{}", "카드how_k{}", 40),
                                  ("2단", "이단_k{}", None, 126)):
        S = base[base["잔여봉"] >= need]
        M = {}
        for grp in ("체인", "기타", "섹터불명", "전체"):
            g = S if grp == "전체" else S[S["군"] == grp]
            if len(g) < 20: continue
            rows = []
            for k in KS:
                c = col.format(k); h = hcol.format(k) if hcol else None
                d = desc(g, c, h)
                d["k"] = k / 100
                d["목표율"] = round(float(g[f"목표율_k{k}"].mean() * 100), 2)
                if k != 50:                       # Δ vs 현행 — 짝지은 차이
                    diff = (g[c] - g["카드_k50" if mode == "카드" else "이단_k50"])
                    d["델타"] = round(float(diff.mean() * 100), 2)
                    bs = yb_mean(g["연"].values, diff.values * 100)
                    lo, hi = ci(bs)
                    d["델타CI"] = [round(lo, 2), round(hi, 2)]
                    d["유의"] = bool(lo > 0 or hi < 0)
                rows.append(d)
            M[grp] = rows
        # 체인 − 기타 (각 k에서)
        gap = []
        A = S[S["군"] == "체인"]; Bx = S[S["군"] == "기타"]
        if len(A) >= 30 and len(Bx) >= 30:
            for k in KS:
                c = col.format(k)
                dm = (A[c].mean() - Bx[c].mean()) * 100
                T = S[S["군"].isin(["체인", "기타"])]
                bs = yb_gap(T["연"].values, T[c].values * 100, (T["군"] == "체인").values)[:, 0]
                lo, hi = ci(bs)
                gap.append(dict(k=k / 100, 차이=round(float(dm), 2),
                                CI=[round(lo, 2), round(hi, 2)], 유의=bool(lo > 0 or hi < 0)))
        blk[mode] = dict(군별=M, 체인빼기기타=gap, n표본=int(len(S)))
    OUT[tag] = blk

# ── 최적 계수가 종목군별로 다른가 (부트스트랩으로 argmax 분포)
OUT["argmax"] = {}
for tag, mask in (("정식A", R["등급"] == "정식A"), ("A+S2α", R["등급"].isin(["정식A", "S2-α"]))):
    base = R[mask]
    for mode, col, need in (("카드", "카드_k{}", 40), ("2단", "이단_k{}", 126)):
        S = base[base["잔여봉"] >= need]
        for grp in ("체인", "기타"):
            g = S[S["군"] == grp]
            if len(g) < 50: continue
            cols = [col.format(k) for k in KS]
            M5 = yb_mean(g["연"].values, g[cols].values, B=2000)
            arr = np.argmax(M5, axis=1)
            OUT["argmax"][f"{tag}|{mode}|{grp}"] = {
                str(KS[i] / 100): round(float((arr == i).mean() * 100), 1) for i in range(len(KS))}

OUT["메타"] = dict(기간=f"{R['date'].min()} ~ {R['date'].max()}",
                 전체=int(len(R)), B=B,
                 카드표본=int((R['잔여봉'] >= 40).sum()), 이단표본=int((R['잔여봉'] >= 126).sum()))
json.dump(OUT, open(f"{HERE}/목표계수_결과.json", "w"), ensure_ascii=False, indent=1)

# ── 콘솔 요약
print("=" * 96)
print("과제① 목표계수 검정 —", OUT["메타"]["기간"], "· 🟢실행 국면만")
print("=" * 96)
for tag in ("정식A", "A+S2α"):
    for mode in ("카드", "2단"):
        blk = OUT[tag][mode]
        print(f"\n■ {tag} · {mode}  (표본 {blk['n표본']:,}건)")
        for grp, rows in blk["군별"].items():
            if grp == "섹터불명": continue
            print(f"  [{grp}]  n={rows[0]['n']:,}")
            print(f"    {'k':>5}{'목표거리':>9}{'평균':>9}{'중앙':>8}{'승률':>8}{'목표도달':>9}{'Δ vs 0.5':>11}{'95% CI':>18}")
            for d in rows:
                dl = f"{d['델타']:+.2f}" if "델타" in d else "  기준"
                cis = f"[{d['델타CI'][0]:+.2f},{d['델타CI'][1]:+.2f}]" if "델타CI" in d else ""
                st = "★" if d.get("유의") else ""
                tg = f"{d['목표도달']:.1f}%" if "목표도달" in d else "—"
                print(f"    {d['k']:>5.2f}{d['목표율']:>8.1f}%{d['평균']:>+9.2f}{d['중앙']:>+8.2f}"
                      f"{d['승률']:>7.1f}%{tg:>9}{dl:>11}{cis:>18}{st}")
        if blk["체인빼기기타"]:
            print("    체인 − 기타:", "  ".join(
                f"k{g['k']:.2f} {g['차이']:+.2f}%p[{g['CI'][0]:+.1f},{g['CI'][1]:+.1f}]{'★' if g['유의'] else ''}"
                for g in blk["체인빼기기타"]))
print("\n■ 최적 계수 부트스트랩 분포 (연도블록 2000회, 값=그 k가 1등일 확률 %)")
for k_, v in OUT["argmax"].items():
    print(f"  {k_:<20}", "  ".join(f"{kk}:{vv:>5.1f}" for kk, vv in v.items()))
print("\n저장: 목표계수_결과.json")
