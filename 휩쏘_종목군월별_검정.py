# -*- coding: utf-8 -*-
"""휩쏘 · 종목군(시총계층) × 월별 매매현황 30년 검정
   종목군 정의 = 진입 시점 point-in-time 시총 계층 (형 지정, 2026-08-04)
   - 업종 맵은 현재 상장사 스냅샷이라 1997~2004 커버리지 57~70% → 생존편향으로 기각
   - 시총은 종목시총_30년.csv 로 전구간 point-in-time 확보

출력: 휩쏘_종목군월별_이벤트.csv / 휩쏘_종목군월별_결과.json / 콘솔 판정표
"""
import os, sys, json, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
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

# ── 시총 계층 문턱 (사전 고정 · 사후조정 금지) ────────────────────────
# 시장별 횡단면 순위. KRX KOSPI 관행(대형 1~100위 / 중형 101~300위 / 소형 그 이하)을 그대로 쓴다.
TIER_CUTS = [(100, "대형"), (300, "중형")]
TIER_ELSE = "소형"
TIERS = ["대형", "중형", "소형"]
MONTHS = list(range(1, 13))


def tier_of(rank):
    for cut, nm in TIER_CUTS:
        if rank <= cut: return nm
    return TIER_ELSE


def boot_mean(a, yrs, nb=NB, seed=SEED):
    """연도블록 부트스트랩 — 평균의 95% CI"""
    a = np.asarray(a, float); yrs = np.asarray(yrs)
    ok = np.isfinite(a)
    a, yrs = a[ok], yrs[ok]
    if len(a) < 8: return (np.nan, np.nan)
    rng = np.random.default_rng(seed); ys = np.array(sorted(set(yrs)))
    idx = {y: np.where(yrs == y)[0] for y in ys}; out = np.empty(nb)
    for i in range(nb):
        p = rng.choice(ys, size=len(ys), replace=True)
        s = np.concatenate([idx[y] for y in p])
        out[i] = np.nanmean(a[s])
    return tuple(np.percentile(out, [2.5, 97.5]) * 100)


def boot_diff(a, b, yrs, nb=NB, seed=SEED):
    a = np.asarray(a, float); b = np.asarray(b, float); yrs = np.asarray(yrs)
    rng = np.random.default_rng(seed); ys = np.array(sorted(set(yrs)))
    idx = {y: np.where(yrs == y)[0] for y in ys}; out = np.empty(nb)
    for i in range(nb):
        p = rng.choice(ys, size=len(ys), replace=True)
        s = np.concatenate([idx[y] for y in p])
        out[i] = np.nanmean(a[s]) - np.nanmean(b[s])
    return tuple(np.percentile(out, [2.5, 97.5]) * 100)


def build_tiers():
    """월말 시총 스냅숏 → 시장별 횡단면 순위 → 계층 라벨
       시장은 point-in-time: 코드_시장구간.csv 의 [first,last] 안에 스냅숏일이 드는 시장.
       (KOSDAQ→KOSPI 이전 112종을 정확히 처리한다)"""
    M = pd.read_csv(F("종목시총_30년.csv"), dtype={"code": str})
    M.columns = [x.strip().lstrip("﻿") for x in M.columns]
    M["code"] = M["code"].str.zfill(6)
    R = pd.read_csv(F("코드_시장구간.csv"), dtype={"code": str})
    R["code"] = R["code"].str.zfill(6)
    M = M.merge(R, on="code", how="left")
    M = M[(M["date"].astype(str) >= M["first"].astype(str)) &
          (M["date"].astype(str) <= M["last"].astype(str))]
    M = M[M["시장"].notna() & (M["mcap"] > 0)].copy()
    assert not M.duplicated(["date", "code"]).any(), "시장 point-in-time 해소 실패"
    M["rank"] = M.groupby(["date", "시장"])["mcap"].rank(ascending=False, method="first")
    M["계층"] = M["rank"].map(tier_of)
    M["snap"] = M["date"].astype(str)
    return M[["snap", "code", "시장", "mcap", "rank", "계층"]]


def attach(ev, T):
    """이벤트 진입일 ≤ 직전 월말 스냅숏 (look-ahead 차단)"""
    snaps = np.array(sorted(T["snap"].unique()))
    ev = ev.copy(); ev["date"] = ev["date"].astype(str)
    pos = np.searchsorted(snaps, ev["date"].values, side="left") - 1
    ev["snap"] = np.where(pos >= 0, snaps[np.clip(pos, 0, len(snaps) - 1)], None)
    out = ev.merge(T[["snap", "code", "계층", "rank"]], on=["snap", "code"], how="left")
    return out


def main():
    ev = pd.read_csv(F("S2_이벤트_통합.csv"), dtype={"code": str})
    ev.columns = [x.strip().lstrip("﻿") for x in ev.columns]
    ev["code"] = ev["code"].str.zfill(6)
    ev["연"] = ev["연"].astype(int)
    ev["월"] = pd.to_datetime(ev["date"]).dt.month

    T = build_tiers()
    E = attach(ev, T)
    E.to_csv(os.path.join(HERE, "휩쏘_종목군월별_이벤트.csv"), index=False, encoding="utf-8-sig")

    tot = len(E); has = E["계층"].notna().sum()
    print("=" * 78)
    print(f"[표본] 전체 {tot}건 · 계층부여 {has}건 ({has/tot*100:.1f}%) · "
          f"미부여 {tot-has}건은 전 분석에서 제외")
    print(E["계층"].value_counts().to_dict())

    res = {"표본": {"전체": int(tot), "계층부여": int(has)}}
    E = E[E["계층"].notna()].copy()
    G = E[E["국면"] == "실행"].copy()          # 국면 통제 = 🟢실행만
    res["실행n"] = int(len(G))

    from math import erfc, sqrt
    def approx_p(lo, hi):
        c = (lo + hi) / 2; se = (hi - lo) / 3.92
        if se <= 0: return 1.0
        return float(erfc(abs(c) / (se * sqrt(2))))

    def line(sub, label):
        a = sub["카드"].values.astype(float)
        lo, hi = boot_mean(a, sub["연"].values)
        star = " ★" if lo > 0 else ""
        print(f"{label:<14}{len(sub):>6}{np.nanmean(a)*100:>9.2f}{np.nanmedian(a)*100:>9.2f}"
              f"{(a > 0).mean()*100:>8.1f}%   [{lo:+6.2f},{hi:+6.2f}]{star}")
        return dict(n=int(len(sub)), 평균=float(np.nanmean(a)*100),
                    중앙=float(np.nanmedian(a)*100), 승률=float((a > 0).mean()*100),
                    ci=[float(lo), float(hi)])

    print("\n" + "=" * 78)
    print("① 시총 계층별 (🟢실행 국면만 · 전 신호등급)")
    print(f"{'계층':<14}{'n':>6}{'평균%':>9}{'중앙%':>9}{'승률':>9}{'   부트95%CI':>20}")
    res["계층"] = {t: line(G[G["계층"] == t], t) for t in TIERS if (G["계층"] == t).any()}

    print("\n" + "=" * 78)
    print("② 진입 월별 (🟢실행 국면만 · 전 계층)")
    print(f"{'월':<14}{'n':>6}{'평균%':>9}{'중앙%':>9}{'승률':>9}{'   부트95%CI':>20}")
    res["월"] = {str(m): line(G[G["월"] == m], f"{m}월") for m in MONTHS if (G["월"] == m).any()}

    print("\n" + "=" * 78)
    print("②-b 월별 다중비교 보정 (12개 동시검정 · Benjamini-Hochberg FDR 10%)")
    print("     그리고 '카드 − 순수보유40일' = 시장 계절성을 뺀 카드 순수 리프트")
    print(f"{'월':<8}{'n':>6}{'카드%':>9}{'보유40%':>9}{'Δ리프트':>9}{'   부트95%CI(Δ)':>22}{'  p(부호)':>10}")
    rows = []
    for m in MONTHS:
        s = G[G["월"] == m]
        if len(s) < 20: continue
        a = s["카드"].values.astype(float); b = s["fwd40"].values.astype(float)
        ok = np.isfinite(a) & np.isfinite(b)
        lo, hi = boot_diff(a[ok], b[ok], s["연"].values[ok])
        # 부트 분포에서 0을 넘는 비율 → 양측 p 근사
        p = 2 * min((lo > 0) * 0 + 0.5, 0.5)  # placeholder, 아래에서 재계산
        rows.append((m, len(s), np.nanmean(a) * 100, np.nanmean(b[ok]) * 100,
                     np.nanmean(a[ok]) * 100 - np.nanmean(b[ok]) * 100, lo, hi))
    # BH: 부트 CI 대신 연도블록 순열 p값을 쓰기엔 비용이 커서, CI 기반 근사 p를 쓴다
    ps = [approx_p(r[5], r[6]) for r in rows]
    order = np.argsort(ps); mrank = np.empty(len(ps), int); mrank[order] = np.arange(1, len(ps) + 1)
    qthr = 0.10 * mrank / len(ps)
    passed = np.array(ps) <= qthr
    # BH step-up: 최대 통과 순위 이하 전부 통과
    if passed.any():
        kmax = mrank[passed].max(); passed = mrank <= kmax
    res["월리프트"] = {}
    for (r, p, pa) in zip(rows, ps, passed):
        m, n, ca, ba, d, lo, hi = r
        star = " ★BH" if pa else (" ○" if (lo > 0 or hi < 0) else "")
        print(f"{str(m)+'월':<8}{n:>6}{ca:>9.2f}{ba:>9.2f}{d:>9.2f}   [{lo:+6.2f},{hi:+6.2f}]{p:>9.3f}{star}")
        res["월리프트"][str(m)] = dict(n=int(n), 카드=float(ca), 보유40=float(ba),
                                       리프트=float(d), ci=[float(lo), float(hi)],
                                       p=float(p), BH통과=bool(pa))
    print("  ★BH = 12개 동시검정 FDR 10% 보정 후에도 살아남음 · ○ = 보정 전에만 유의")

    print("\n" + "=" * 78)
    print("②-c 핵심 질문: '이 달이 다른 달과 다른가' — 각 월 vs 나머지 11개월 (카드 기준)")
    print(f"{'월':<8}{'n':>6}{'해당월%':>9}{'나머지%':>9}{'Δ':>8}{'   부트95%CI(Δ)':>22}{'  p':>8}")
    rows2 = []
    for m in MONTHS:
        s = G[G["월"] == m]; o = G[G["월"] != m]
        if len(s) < 20: continue
        a = s["카드"].values.astype(float); b = o["카드"].values.astype(float)
        ys = np.array(sorted(set(G["연"].values)))
        ia = {y: np.where(s["연"].values == y)[0] for y in ys}
        ib = {y: np.where(o["연"].values == y)[0] for y in ys}
        rng = np.random.default_rng(SEED); out = np.empty(NB)
        for i in range(NB):
            p_ = rng.choice(ys, size=len(ys), replace=True)
            sa = np.concatenate([ia[y] for y in p_]); sb = np.concatenate([ib[y] for y in p_])
            out[i] = (np.nanmean(a[sa]) if len(sa) else np.nan) - \
                     (np.nanmean(b[sb]) if len(sb) else np.nan)
        lo, hi = np.nanpercentile(out, [2.5, 97.5]) * 100
        rows2.append((m, len(s), np.nanmean(a) * 100, np.nanmean(b) * 100,
                      np.nanmean(a) * 100 - np.nanmean(b) * 100, lo, hi))
    ps2 = [approx_p(r[5], r[6]) for r in rows2]
    o2 = np.argsort(ps2); r2 = np.empty(len(ps2), int); r2[o2] = np.arange(1, len(ps2) + 1)
    pass2 = np.array(ps2) <= 0.10 * r2 / len(ps2)
    if pass2.any(): pass2 = r2 <= r2[pass2].max()
    res["월대비"] = {}
    for (r, p, pa) in zip(rows2, ps2, pass2):
        m, n, ma_, mo_, d, lo, hi = r
        star = " ★BH" if pa else (" ○" if (lo > 0 or hi < 0) else "")
        print(f"{str(m)+'월':<8}{n:>6}{ma_:>9.2f}{mo_:>9.2f}{d:>8.2f}   [{lo:+6.2f},{hi:+6.2f}]{p:>8.3f}{star}")
        res["월대비"][str(m)] = dict(n=int(n), 해당월=float(ma_), 나머지=float(mo_),
                                     delta=float(d), ci=[float(lo), float(hi)],
                                     p=float(p), BH통과=bool(pa))

    print("\n" + "=" * 78)
    print("③ 계층 × 월 교차 (🟢실행 · 평균% / n) — 36셀 사후분해. 사전등록 아님, 시사일 뿐.")
    piv = G.pivot_table(index="계층", columns="월", values="카드",
                        aggfunc=["mean", "count"])
    hdr = "계층      " + "".join(f"{m:>8}월" for m in MONTHS)
    print(hdr)
    cross = {}
    for t in TIERS:
        if t not in piv.index: continue
        row = f"{t:<10}"
        cross[t] = {}
        for m in MONTHS:
            try:
                mu = piv[("mean", m)].loc[t] * 100; n = int(piv[("count", m)].loc[t])
            except Exception:
                mu, n = np.nan, 0
            row += f"{mu:>+8.1f} " if n >= 10 else f"{'·':>8} "
            cross[t][str(m)] = {"평균": None if not np.isfinite(mu) else float(mu), "n": n}
        print(row)
        print(" " * 10 + "".join(f"{(cross[t][str(m)]['n']):>8} " for m in MONTHS))
    res["교차"] = cross

    print("\n" + "=" * 78)
    print("④ 국면 통제 확인 — 각 계층이 국면 3종에서 같은 부호인가")
    print(f"{'계층/국면':<14}{'n':>6}{'평균%':>9}{'중앙%':>9}{'승률':>9}")
    res["국면교차"] = {}
    for t in TIERS:
        res["국면교차"][t] = {}
        for st in ("실행", "주의", "관찰만"):
            s = E[(E["계층"] == t) & (E["국면"] == st)]
            if len(s) < 5: continue
            a = s["카드"].values.astype(float)
            print(f"{t+'/'+st:<14}{len(s):>6}{np.nanmean(a)*100:>9.2f}"
                  f"{np.nanmedian(a)*100:>9.2f}{(a > 0).mean()*100:>8.1f}%")
            res["국면교차"][t][st] = dict(n=int(len(s)), 평균=float(np.nanmean(a)*100),
                                          중앙=float(np.nanmedian(a)*100),
                                          승률=float((a > 0).mean()*100))

    print("\n" + "=" * 78)
    print("⑤ 계층 간 차이 부트 검정 (🟢실행 · 대형 대비)")
    base = G[G["계층"] == "대형"]
    res["계층차"] = {}
    for t in ("중형", "소형"):
        s = G[G["계층"] == t]
        if len(s) < 8 or len(base) < 8: continue
        allyr = np.concatenate([s["연"].values, base["연"].values])
        rng = np.random.default_rng(SEED); ys = np.array(sorted(set(allyr)))
        ia = {y: np.where(s["연"].values == y)[0] for y in ys}
        ib = {y: np.where(base["연"].values == y)[0] for y in ys}
        av = s["카드"].values.astype(float); bv = base["카드"].values.astype(float)
        out = np.empty(NB)
        for i in range(NB):
            p = rng.choice(ys, size=len(ys), replace=True)
            sa = np.concatenate([ia[y] for y in p]); sb = np.concatenate([ib[y] for y in p])
            out[i] = (np.nanmean(av[sa]) if len(sa) else np.nan) - \
                     (np.nanmean(bv[sb]) if len(sb) else np.nan)
        lo, hi = np.nanpercentile(out, [2.5, 97.5]) * 100
        d = np.nanmean(av) * 100 - np.nanmean(bv) * 100
        mark = " ★" if (lo > 0 or hi < 0) else ""
        print(f"{t} − 대형: Δ{d:+.2f}%p  부트95%CI [{lo:+.2f},{hi:+.2f}]{mark}")
        res["계층차"][t] = dict(delta=float(d), ci=[float(lo), float(hi)])

    print("\n" + "=" * 78)
    print("⑥ 월별 '기회의 수' — 30년 신호 발생 빈도와 국면 구성 (수익률이 아니라 빈도)")
    print(f"{'월':<8}{'전체':>7}{'실행':>7}{'주의':>7}{'관찰만':>8}{'실행비율':>9}{'  대형/중형/소형':>18}")
    res["빈도"] = {}
    for m in MONTHS:
        s = E[E["월"] == m]
        if not len(s): continue
        vc = s["국면"].value_counts()
        tv = s["계층"].value_counts()
        ex = int(vc.get("실행", 0))
        print(f"{str(m)+'월':<8}{len(s):>7}{ex:>7}{int(vc.get('주의',0)):>7}"
              f"{int(vc.get('관찰만',0)):>8}{ex/len(s)*100:>8.1f}%"
              f"{'':>4}{int(tv.get('대형',0))}/{int(tv.get('중형',0))}/{int(tv.get('소형',0))}")
        res["빈도"][str(m)] = dict(전체=int(len(s)), 실행=ex,
                                   주의=int(vc.get("주의", 0)), 관찰만=int(vc.get("관찰만", 0)),
                                   대형=int(tv.get("대형", 0)), 중형=int(tv.get("중형", 0)),
                                   소형=int(tv.get("소형", 0)))

    with open(os.path.join(HERE, "휩쏘_종목군월별_결과.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=1)
    print("\n저장: 휩쏘_종목군월별_이벤트.csv · 휩쏘_종목군월별_결과.json")


if __name__ == "__main__":
    main()
