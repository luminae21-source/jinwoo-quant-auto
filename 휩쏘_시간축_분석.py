# -*- coding: utf-8 -*-
"""휩쏘 · 시간축 분리 분석 (휩쏘_시간축분리_검정.py 산출물 소비)"""
import os, sys, json, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from math import erfc, sqrt
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass


# ── 경로 해석 (컨테이너 / 형 PC 어디서 돌려도 동작) ─────────────
def _resolve():
    here = os.path.dirname(os.path.abspath(__file__))
    cand = ["/home/claude/jq", "/mnt/user-data/uploads/진우퀀트", here]
    def find(name):
        for d in ([here] + cand):
            p = os.path.join(d, name)
            if os.path.exists(p): return p
        return os.path.join(here, name)
    return here, find
HERE, F = _resolve()
NB = 4000; SEED = 11
HORIZONS = [5, 10, 20, 40, 63, 126]
HGROUP = {5: "단기", 10: "단기", 20: "단기", 40: "스윙", 63: "중기", 126: "중기"}
TRAILS = [0.00, 0.08, 0.12, 0.20]
USE_TGT = [True, False]


def boot_mean(a, yrs):
    a = np.asarray(a, float); yrs = np.asarray(yrs)
    ok = np.isfinite(a); a, yrs = a[ok], yrs[ok]
    if len(a) < 8: return (np.nan, np.nan)
    rng = np.random.default_rng(SEED); ys = np.array(sorted(set(yrs)))
    idx = {y: np.where(yrs == y)[0] for y in ys}; out = np.empty(NB)
    for i in range(NB):
        p = rng.choice(ys, size=len(ys), replace=True)
        out[i] = np.nanmean(a[np.concatenate([idx[y] for y in p])])
    return tuple(np.percentile(out, [2.5, 97.5]) * 100)


def boot_diff(a, b, yrs):
    a = np.asarray(a, float); b = np.asarray(b, float); yrs = np.asarray(yrs)
    ok = np.isfinite(a) & np.isfinite(b); a, b, yrs = a[ok], b[ok], yrs[ok]
    if len(a) < 8: return (np.nan, np.nan)
    rng = np.random.default_rng(SEED); ys = np.array(sorted(set(yrs)))
    idx = {y: np.where(yrs == y)[0] for y in ys}; out = np.empty(NB)
    for i in range(NB):
        p = rng.choice(ys, size=len(ys), replace=True)
        s = np.concatenate([idx[y] for y in p])
        out[i] = np.nanmean(a[s]) - np.nanmean(b[s])
    return tuple(np.percentile(out, [2.5, 97.5]) * 100)


def approx_p(lo, hi):
    if not (np.isfinite(lo) and np.isfinite(hi)): return 1.0
    c = (lo + hi) / 2; se = (hi - lo) / 3.92
    if se <= 0: return 1.0
    return float(erfc(abs(c) / (se * sqrt(2))))


def bh(ps, q=0.10):
    ps = np.asarray(ps, float); m = len(ps)
    o = np.argsort(ps); r = np.empty(m, int); r[o] = np.arange(1, m + 1)
    ok = ps <= q * r / m
    return (r <= r[ok].max()) if ok.any() else np.zeros(m, bool)


def main():
    M = pd.read_csv(F("휩쏘_시간축_이벤트.csv"), dtype={"code": str})
    M["연"] = M["출발일"].str[:4].astype(int)
    # 진행중(2026 미완결) 제외 — 원장 '청산'이 진행중인 건은 전진관찰 대상이지 검정 표본이 아니다
    M = M[M["청산"].astype(str) != "진행중"].copy()
    G = M[(M["국면"] == "실행") & (M["창완결_126"] == True)].copy()   # 공통표본
    res = {"공통표본n": int(len(G)), "설계": {
        "지평": HORIZONS, "트레일": TRAILS, "목표": ["사용", "미사용"],
        "다중비교": "BH FDR 10% · 48셀", "표본": "🟢실행 × 126봉 창완결 공통표본"}}

    print("=" * 84)
    print(f"[표본] 검정 가능 {len(M)}건 → 🟢실행 × 126봉 창완결 공통표본 {len(G)}건")
    print("       (지평 비교는 반드시 같은 표본으로 — 창완결 조건이 다르면 비교가 오염된다)")

    # ── ① 현행 카드 규칙을 지평만 바꿔서 ──────────────────────────
    print("\n" + "=" * 84)
    print("① 현행 카드 규칙(유형별 트레일+목표)을 지평만 바꿔 적용")
    print(f"{'지평':<10}{'구분':<7}{'평균%':>9}{'중앙%':>9}{'승률':>8}{'   부트95%CI':>20}"
          f"{'  실현봉(중앙)':>13}{'  목표/손절/만기':>18}")
    res["현행"] = {}
    for H in HORIZONS:
        a = G[f"현행_{H}"].values.astype(float)
        lo, hi = boot_mean(a, G["연"].values)
        b = G[f"현행봉_{H}"].values.astype(float)
        w = G[f"현행사유_{H}"].value_counts(normalize=True) * 100
        print(f"{str(H)+'봉':<10}{HGROUP[H]:<7}{np.nanmean(a)*100:>9.2f}{np.nanmedian(a)*100:>9.2f}"
              f"{(a > 0).mean()*100:>7.1f}%   [{lo:+6.2f},{hi:+6.2f}]{'★' if lo > 0 else ' '}"
              f"{np.nanmedian(b):>11.0f}일   "
              f"{w.get('목표',0):>4.0f}/{w.get('손절',0):>4.0f}/{w.get('만기',0):>4.0f}%")
        res["현행"][str(H)] = dict(그룹=HGROUP[H], 평균=float(np.nanmean(a)*100),
                                   중앙=float(np.nanmedian(a)*100), 승률=float((a > 0).mean()*100),
                                   ci=[float(lo), float(hi)], 실현봉중앙=float(np.nanmedian(b)),
                                   목표=float(w.get("목표", 0)), 손절=float(w.get("손절", 0)),
                                   만기=float(w.get("만기", 0)))

    print("\n" + "=" * 84)
    print("② 순수보유(규칙 없음) 벤치마크 — 카드가 지평별로 얼마나 보태거나 깎나")
    print(f"{'지평':<10}{'보유평균%':>10}{'보유중앙%':>10}{'보유승률':>9}"
          f"{'  카드−보유Δ':>13}{'   부트95%CI(Δ)':>22}")
    res["보유"] = {}
    for H in HORIZONS:
        a = G[f"현행_{H}"].values.astype(float); b = G[f"보유_{H}"].values.astype(float)
        lo, hi = boot_diff(a, b, G["연"].values)
        mark = "★" if (lo > 0) else ("✗" if hi < 0 else " ")
        print(f"{str(H)+'봉':<10}{np.nanmean(b)*100:>10.2f}{np.nanmedian(b)*100:>10.2f}"
              f"{(b > 0).mean()*100:>8.1f}%{(np.nanmean(a)-np.nanmean(b))*100:>13.2f}"
              f"   [{lo:+6.2f},{hi:+6.2f}]{mark}")
        res["보유"][str(H)] = dict(평균=float(np.nanmean(b)*100), 중앙=float(np.nanmedian(b)*100),
                                   승률=float((b > 0).mean()*100),
                                   delta=float((np.nanmean(a)-np.nanmean(b))*100),
                                   ci=[float(lo), float(hi)])

    print("\n" + "=" * 84)
    print("②-b 카드의 진짜 값어치는 평균이 아니라 하방 — 같은 표본 위험지표")
    print(f"{'지평':<8}{'':<6}{'표준편차':>9}{'5%분위':>9}{'최악5%평균':>11}"
          f"{'-20%이하비율':>13}{'최대손실':>9}")
    res["위험"] = {}
    for H in HORIZONS:
        row = {}
        for nm, col in (("카드", f"현행_{H}"), ("보유", f"보유_{H}")):
            v = G[col].values.astype(float); v = v[np.isfinite(v)]
            q5 = np.percentile(v, 5); cvar = v[v <= q5].mean()
            print(f"{(str(H)+'봉') if nm=='카드' else '':<8}{nm:<6}{v.std()*100:>9.2f}"
                  f"{q5*100:>9.2f}{cvar*100:>11.2f}{(v <= -0.20).mean()*100:>12.1f}%"
                  f"{v.min()*100:>9.1f}")
            row[nm] = dict(sd=float(v.std()*100), q5=float(q5*100), cvar=float(cvar*100),
                           under20=float((v <= -0.20).mean()*100), worst=float(v.min()*100))
        res["위험"][str(H)] = row

    # ── ③ 정책 그리드 48셀 ────────────────────────────────────
    print("\n" + "=" * 84)
    print("③ 정책 그리드 48셀 — 지평별 최적 트레일이 갈리나 (기준=현행_40)")
    base = G["현행_40"].values.astype(float)
    cells = []
    for H in HORIZONS:
        for tr in TRAILS:
            for ug in USE_TGT:
                k = f"T{int(tr*100)}{'G' if ug else 'N'}_{H}"
                a = G[k].values.astype(float)
                lo, hi = boot_diff(a, base, G["연"].values)
                cells.append(dict(H=H, 그룹=HGROUP[H], trail=tr, 목표=ug, key=k,
                                  평균=float(np.nanmean(a)*100),
                                  중앙=float(np.nanmedian(a)*100),
                                  승률=float((a > 0).mean()*100),
                                  실현봉=float(np.nanmedian(G[k+"_봉"].values.astype(float))),
                                  d=float((np.nanmean(a)-np.nanmean(base))*100),
                                  lo=float(lo), hi=float(hi)))
    ps = [approx_p(c["lo"], c["hi"]) for c in cells]
    passed = bh(ps)
    for c, p, pa in zip(cells, ps, passed):
        c["p"] = float(p); c["BH"] = bool(pa)
    res["그리드"] = cells

    print(f"{'지평':<7}{'트레일':<8}{'목표':<6}{'평균%':>8}{'중앙%':>8}{'승률':>7}"
          f"{'실현봉':>7}{'Δ vs 현행40':>12}{'   부트95%CI':>20}{'  p':>8}")
    for c in cells:
        tag = " ★BH" if c["BH"] else (" ○" if (c["lo"] > 0 or c["hi"] < 0) else "")
        trn = "없음" if c["trail"] == 0 else f"{int(c['trail']*100)}%"
        print(f"{str(c['H'])+'봉':<7}{trn:<8}{'O' if c['목표'] else 'X':<6}"
              f"{c['평균']:>8.2f}{c['중앙']:>8.2f}{c['승률']:>6.1f}%{c['실현봉']:>7.0f}"
              f"{c['d']:>12.2f}   [{c['lo']:+6.2f},{c['hi']:+6.2f}]{c['p']:>8.3f}{tag}")
    nbh = sum(c["BH"] for c in cells)
    print(f"\n  48셀 중 BH FDR 10% 통과: {nbh}셀 · 보정 전 CI가 0을 넘은 셀: "
          f"{sum(1 for c in cells if c['lo'] > 0 or c['hi'] < 0)}셀")

    print("\n" + "=" * 84)
    print("③-b BH 통과 셀의 대가 — 평균은 오르지만 무엇을 내주는가 (기준=현행_40)")
    print(f"{'정책':<16}{'평균%':>8}{'중앙%':>8}{'승률':>7}{'표준편차':>9}"
          f"{'5%분위':>9}{'-20%이하':>9}")
    def riskline(lab, col):
        v = G[col].values.astype(float); v = v[np.isfinite(v)]
        print(f"{lab:<16}{v.mean()*100:>8.2f}{np.median(v)*100:>8.2f}{(v > 0).mean()*100:>6.1f}%"
              f"{v.std()*100:>9.2f}{np.percentile(v, 5)*100:>9.2f}{(v <= -0.20).mean()*100:>8.1f}%")
        return dict(평균=float(v.mean()*100), 중앙=float(np.median(v)*100),
                    승률=float((v > 0).mean()*100), sd=float(v.std()*100),
                    q5=float(np.percentile(v, 5)*100), under20=float((v <= -0.20).mean()*100))
    res["대가"] = {"현행_40": riskline("현행 40봉(기준)", "현행_40")}
    for c in sorted([x for x in cells if x["BH"]], key=lambda x: -x["d"])[:6]:
        trn = "없음" if c["trail"] == 0 else f"{int(c['trail']*100)}%"
        res["대가"][c["key"]] = riskline(f"{c['H']}봉/{trn}/목표X", c["key"])

    # ── ④ 지평 그룹별 최적 트레일 ──────────────────────────────
    print("\n" + "=" * 84)
    print("④ 주질문 2 — 지평 그룹별로 최적 트레일이 갈리나 (목표 사용 고정)")
    print(f"{'그룹':<8}{'지평':<7}" + "".join(f"{('트레일 '+('없음' if t==0 else str(int(t*100))+'%')):>13}" for t in TRAILS))
    res["최적트레일"] = {}
    for H in HORIZONS:
        vals = []
        for tr in TRAILS:
            k = f"T{int(tr*100)}G_{H}"
            vals.append(np.nanmean(G[k].values.astype(float)) * 100)
        best = TRAILS[int(np.argmax(vals))]
        print(f"{HGROUP[H]:<8}{str(H)+'봉':<7}" + "".join(f"{v:>13.2f}" for v in vals)
              + f"   ← 최고: {'없음' if best == 0 else str(int(best*100))+'%'}")
        res["최적트레일"][str(H)] = dict(값=[float(v) for v in vals],
                                         최고=("없음" if best == 0 else f"{int(best*100)}%"))

    # ── ⑤ 유형(A/B)별 시간축 ───────────────────────────────────
    print("\n" + "=" * 84)
    print("⑤ 부수 확인 — 신호 유형이 시간축을 가르나 (현행 규칙)")
    print(f"{'유형':<6}{'지평':<7}{'n':>6}{'평균%':>9}{'중앙%':>9}{'승률':>8}{'   부트95%CI':>20}")
    tcol = "유형_x" if "유형_x" in G.columns else "유형"
    res["유형"] = {}
    for ty in ("A", "B"):
        s = G[G[tcol] == ty]
        if len(s) < 20: continue
        res["유형"][ty] = {}
        for H in HORIZONS:
            a = s[f"현행_{H}"].values.astype(float)
            lo, hi = boot_mean(a, s["연"].values)
            print(f"{ty:<6}{str(H)+'봉':<7}{len(s):>6}{np.nanmean(a)*100:>9.2f}"
                  f"{np.nanmedian(a)*100:>9.2f}{(a > 0).mean()*100:>7.1f}%"
                  f"   [{lo:+6.2f},{hi:+6.2f}]{'★' if lo > 0 else ''}")
            res["유형"][ty][str(H)] = dict(n=int(len(s)), 평균=float(np.nanmean(a)*100),
                                           중앙=float(np.nanmedian(a)*100),
                                           승률=float((a > 0).mean()*100),
                                           ci=[float(lo), float(hi)])
        print()

    # ── ⑥ 실제 보유기간 분포 ──────────────────────────────────
    print("=" * 84)
    print("⑥ '지금 시스템은 이미 단기매매인가' — 현행 40봉 카드의 실제 청산 시점 분포")
    b = G["현행봉_40"].values.astype(float)
    for lo_, hi_ in ((1, 5), (6, 10), (11, 20), (21, 39), (40, 40)):
        m = (b >= lo_) & (b <= hi_)
        r = G["현행_40"].values.astype(float)[m]
        lab = f"{lo_}~{hi_}일" if lo_ != hi_ else "40일(만기)"
        print(f"  {lab:<12}{m.sum():>6}건 ({m.mean()*100:>4.1f}%)  평균 {np.nanmean(r)*100:>+6.2f}%  "
              f"승률 {(r > 0).mean()*100:>4.1f}%")
    res["보유분포"] = {"중앙일": float(np.nanmedian(b)), "평균일": float(np.nanmean(b))}
    print(f"  → 중앙 {np.nanmedian(b):.0f}일 · 평균 {np.nanmean(b):.1f}일")

    with open(os.path.join(HERE, "휩쏘_시간축_결과.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("\n저장: 휩쏘_시간축_결과.json")


if __name__ == "__main__":
    main()
