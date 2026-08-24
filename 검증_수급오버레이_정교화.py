#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""검증_수급오버레이_정교화.py — 딥밸류+기관매집 오버레이 정교화(숏커버 구분) + §3 재검증.

배경(사냥터_기획/진우_수급오버레이_검증.md): 딥밸류+기관매집은 IN/OOS 방향·승률 우위이나
  §3 유의성 양분할 동시통과 실패·표본 얇음(OOS n=37) → 하드필터 아닌 참고플래그로만 반영.
진우 정교화 지시: "순매수가 숏커버(대차상환)일 수 있으니 잘 보고 접근. 없는 근거로 진행 금지."

이 스크립트가 하는 일:
  1) 표본확대: flow_ext_monthly_*(있으면)로 유니버스·기간 확대된 수급 사용(없으면 기존 flow).
  2) 숏커버 구분: short_balance_monthly_*(공매도잔고)로, 딥밸류+기관매집 진입월의
     Δ공매도잔고(비중)를 보고 코호트를 분리:
        · 숏커버동반  = 진입월에 공매도잔고 비중이 --sc-thresh 이상 감소(숏 되사기 동반).
        · 실매집(신규롱) = 공매도잔고 데이터 있고 비중 감소 아님(숏 유지/증가 or 애초에 숏 없음).
        · 무공매도데이터 = 진입월(또는 직전) 공매도잔고 관측 없음 → 분리 불가(정직히 별도 보고).
  3) §3 재검증: 각 코호트 ALL/IN/OOS × 6/9/12M 평균·중앙·승률 + 부트스트랩 유의성.
  4) 판정: 숏커버 우열은 '가정하지 않고' 데이터로 결정.
        · 실매집 > 숏커버동반 이고 실매집이 §3(양분할·유의) 통과 → 딥+기관&실매집 하드필터 승격 검토.
        · 차이 없음 → 숏커버는 교란요인 아님, 플래그 유지.
        · 숏커버동반 ≥ 실매집 → 숏스퀴즈형(다른 메커니즘), 문서화만.

정직/근거 원칙:
  · 공매도잔고 데이터는 KRX가 주는 기간만 존재(대략 최근 수년). 진입월이 그 밖이면 '무공매도데이터'로
    분류되어 숏커버 정교화 대상에서 빠진다 → 커버리지를 반드시 출력. 없는 값은 위조하지 않음.
  · Δ공매도잔고는 '숏커버 대리지표'다. 되사기 주체가 반드시 순매수한 기관/외국인 버킷과 일치하진 않는다(한계 명시).
  · short_balance 파일이 없으면 숏커버 분석은 생략하고 표본확대 §3 재검증만 수행.

의존파일(있는 만큼 사용):
  종목일봉_30년_{KOSPI,KOSDAQ}.csv, 종목재무_KRX_{KOSPI,KOSDAQ}.csv (필수)
  flow_ext_monthly_{...}.csv 또는 {kospi,kosdaq}_flow_monthly.csv (필수)
  short_balance_monthly_{KOSPI,KOSDAQ}.csv (있으면 숏커버 정교화)

사용:
  python 검증_수급오버레이_정교화.py                 # 전체
  python 검증_수급오버레이_정교화.py --sc-thresh 0.1  # 숏커버 판정 임계(비중 %p 감소)
  python 검증_수급오버레이_정교화.py --self-test
"""
import os, sys, argparse, csv
BASE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

GRID_START = "2016-01"   # 월 그리드 시작(ma10 워밍업 여유). 신호는 flow 존재구간으로 제한됨.

def log(*a): print(*a); sys.stdout.flush()

# ---------------- 월말 종가(상폐포함, 생존편향 없음) ----------------
def build_monthly_close(pd, market):
    """일봉 → (code, ym, close[월말]). 캐시: _월봉종가캐시_{market}.csv. /tmp 캐시도 인식(리눅스 테스트)."""
    cache = os.path.join(BASE, f"_월봉종가캐시_{market}.csv")
    if os.path.exists(cache):
        return pd.read_csv(cache, dtype={"code": str})
    tmpc = f"/tmp/px_m_{market}.csv"
    if os.path.exists(tmpc):
        d = pd.read_csv(tmpc, header=None, names=["code", "date", "close"], dtype={0: str})
        d["code"] = d["code"].str.zfill(6); d["ym"] = d["date"].str[:7]
        out = d[["code", "ym", "close"]].copy()
        out.to_csv(cache, index=False, encoding="utf-8-sig"); return out
    # 일봉에서 직접 축약(청크·메모리 안전·이식성)
    p = os.path.join(BASE, f"종목일봉_30년_{market}.csv")
    if not os.path.exists(p): sys.exit(f"없음: {p}")
    keep = {}  # (code, ym) -> (date, close)  그 달 마지막 날의 종가
    for ch in pd.read_csv(p, usecols=["date", "code", "close"], dtype={"code": str},
                          encoding="utf-8-sig", chunksize=2_000_000):
        ch = ch[pd.to_numeric(ch["close"], errors="coerce") > 0]
        ch["ym"] = ch["date"].str[:7]
        for dte, code, cl, ym in zip(ch["date"], ch["code"], ch["close"], ch["ym"]):
            k = (code.zfill(6), ym); cur = keep.get(k)
            if cur is None or dte > cur[0]: keep[k] = (dte, float(cl))
    rows = [(c, ym, v[1]) for (c, ym), v in keep.items()]
    out = pd.DataFrame(rows, columns=["code", "ym", "close"])
    out.to_csv(cache, index=False, encoding="utf-8-sig"); return out

# ---------------- 딥밸류바닥 패널(검증본과 동일 정의) ----------------
def build_deep(pd, np):
    import pandas as _pd
    pxs = [build_monthly_close(pd, m) for m in ("KOSPI", "KOSDAQ")]
    px = pd.concat(pxs, ignore_index=True).drop_duplicates(["code", "ym"])
    months = pd.period_range(GRID_START, _pd.Timestamp.today().to_period("M"), freq="M").astype(str).tolist()
    mi = {m: i for i, m in enumerate(months)}
    px = px[px["ym"].isin(mi)].copy(); px["mi"] = px["ym"].map(mi)
    px["close"] = pd.to_numeric(px["close"], errors="coerce")
    # PBR
    fp = []
    for m in ("KOSPI", "KOSDAQ"):
        f = pd.read_csv(os.path.join(BASE, f"종목재무_KRX_{m}.csv"), dtype={"code": str})[["date", "code", "PBR"]]
        fp.append(f)
    fund = pd.concat(fp, ignore_index=True); fund["code"] = fund["code"].str.zfill(6)
    fund["ym"] = fund["date"].str[:7]; fund["PBR"] = pd.to_numeric(fund["PBR"], errors="coerce")
    fund = fund.drop_duplicates(["code", "ym"])[["code", "ym", "PBR"]]
    T = len(months); H = [6, 9, 12]; recs = []
    # 선행수익 폐형식(검증본과 동치): 월봉이 상장구간 [F,L]서 연속이라는 전제.
    #   j=t+h가 L 이내면 arr[j], 창내 상폐면 마지막유효가 arr[L], 진입직후 전멸이면 -1.0.
    for code, sub in px.sort_values(["code", "mi"]).groupby("code"):
        arr = np.full(T, np.nan); arr[sub["mi"].values] = sub["close"].values
        s = pd.Series(arr); ma10 = s.rolling(10, min_periods=10).mean().values; ret1 = (s / s.shift(1) - 1).values
        idx = np.where(~np.isnan(arr))[0]
        if len(idx) == 0: continue
        fwd = {h: np.full(T, np.nan) for h in H}
        for h in H:
            for t in idx:
                pos = np.searchsorted(idx, t + h, side="right") - 1  # 창(t, t+h] 내 마지막 유효월
                jv = idx[pos]
                if jv > t: fwd[h][t] = arr[jv] / arr[t] - 1.0   # 마지막 유효가(상폐면 마지막 체결가)
                elif t + 1 < T: fwd[h][t] = -1.0                # 창내 전멸 → 상폐 -100%
        for t in idx:
            recs.append((code, months[t], arr[t], ma10[t], ret1[t], fwd[6][t], fwd[9][t], fwd[12][t]))
    P = pd.DataFrame(recs, columns=["code", "ym", "close", "ma10", "ret1", "f6", "f9", "f12"])
    P = P.merge(fund, on=["code", "ym"], how="left")
    P["disp"] = P["close"] / P["ma10"]
    valid = (P["close"] >= 1000) & (P["ma10"].notna()) & (P["PBR"] > 0)
    Pv = P[valid].copy()
    Pv["pbr_rank"] = Pv.groupby("ym")["PBR"].rank(pct=True)
    Pv["deep"] = (Pv["pbr_rank"] <= 0.20) & (Pv["disp"] < 0.85) & (Pv["ret1"] > 0)
    return Pv[Pv["deep"]].copy()

# ---------------- 수급/공매도 로드 ----------------
def load_flow(pd):
    src = []
    for m in ("KOSPI", "KOSDAQ"):
        ext = os.path.join(BASE, f"flow_ext_monthly_{m}.csv")
        old = os.path.join(BASE, f"{m.lower()}_flow_monthly.csv")
        p = ext if os.path.exists(ext) else (old if os.path.exists(old) else None)
        if p: src.append((p, "ext" if p == ext else "old"))
    if not src: sys.exit("flow 파일 없음(flow_ext_monthly_* 또는 {kospi,kosdaq}_flow_monthly.csv)")
    dfs = []
    for p, kind in src:
        d = pd.read_csv(p, dtype={"code": str}); d["code"] = d["code"].str.zfill(6)
        d["ym"] = d["date"].str[:7]
        for c in ("foreign_net", "inst_net"): d[c] = pd.to_numeric(d[c], errors="coerce")
        dfs.append(d[["code", "ym", "foreign_net", "inst_net"]])
    flow = pd.concat(dfs, ignore_index=True).drop_duplicates(["code", "ym"])
    used = ",".join(f"{p.split(os.sep)[-1]}({k})" for p, k in src)
    return flow, used

def load_short(pd):
    dfs = []
    for m in ("KOSPI", "KOSDAQ"):
        p = os.path.join(BASE, f"short_balance_monthly_{m}.csv")
        if os.path.exists(p):
            d = pd.read_csv(p, dtype={"code": str}); d["code"] = d["code"].str.zfill(6)
            d["ym"] = d["date"].str[:7]
            d["short_qty"] = pd.to_numeric(d["short_qty"], errors="coerce")
            d["short_ratio"] = pd.to_numeric(d["short_ratio"], errors="coerce")
            dfs.append(d[["code", "ym", "short_qty", "short_ratio"]])
    if not dfs: return None
    return pd.concat(dfs, ignore_index=True).drop_duplicates(["code", "ym"])

# ---------------- 숏커버 분류 ----------------
def classify_shortcover(pd, deep, short, sc_thresh, sc_rel=0.20):
    """deep(기관매집 행)에 진입월 Δ공매도잔고 부착 → sc_class ∈ {숏커버동반, 실매집, 무공매도데이터}.
    비중(%p) 있으면 Δ비중 <= -sc_thresh 로 판정. 비중 없으면(수량만 제공하는 함수) 잔고수량
    상대감소 <= -sc_rel(기본 20%)로 판정. 둘 다 아니면 실매집(숏 안 줄거나 애초에 없음)."""
    import math
    if short is None:
        deep = deep.copy(); deep["sc_class"] = "무공매도데이터"; deep["d_short"] = None; return deep
    has_ratio = short["short_ratio"].notna().any() if "short_ratio" in short.columns else False
    smap = {}
    for code, g in short.sort_values(["code", "ym"]).groupby("code"):
        smap[code] = list(zip(g["ym"].tolist(), g["short_ratio"].tolist(), g["short_qty"].tolist()))
    def num(v):
        try:
            f = float(v)
            return f if f == f else None
        except (TypeError, ValueError):
            return None
    def cls(code, ym):
        seq = smap.get(code)
        if not seq: return "무공매도데이터", None
        cur = prev = None
        for (y, r, q) in seq:
            if y == ym: cur = (y, r, q)
            elif y < ym: prev = (y, r, q)
        if cur is None: return "무공매도데이터", None
        if prev is not None:  # 직전 관측 3개월 이내만 유효
            py, pm = int(prev[0][:4]), int(prev[0][5:7]); cy, cm = int(ym[:4]), int(ym[5:7])
            if (cy - py) * 12 + (cm - pm) > 3: prev = None
        cr, cq = num(cur[1]), num(cur[2])
        if prev is None:
            # 진입월만 관측: 숏 사실상 0이면 실매집, 아니면 판정불가
            zero = (cr is not None and cr <= 0.01) or (cr is None and cq is not None and cq <= 0)
            return ("실매집" if zero else "무공매도데이터"), None
        pr, pq = num(prev[1]), num(prev[2])
        if has_ratio and cr is not None and pr is not None:
            d = cr - pr
            return ("숏커버동반" if d <= -sc_thresh else "실매집"), d
        if cq is not None and pq is not None:
            rel = (cq - pq) / (pq if pq > 0 else 1)
            return ("숏커버동반" if rel <= -sc_rel else "실매집"), rel
        return "무공매도데이터", None
    classes = []; deltas = []
    for code, ym in zip(deep["code"], deep["ym"]):
        c, d = cls(code, ym); classes.append(c); deltas.append(d)
    deep = deep.copy(); deep["sc_class"] = classes; deep["d_short"] = deltas
    return deep

# ---------------- 통계 ----------------
def stats(df, col):
    import numpy as np
    x = df[col].dropna().values
    if len(x) == 0: return (0, None, None, None)
    return (len(x), float(np.mean(x) * 100), float(np.median(x) * 100), float(np.mean(x > 0) * 100))

def boot_diff(a, b, n=5000, seed=42):
    import numpy as np
    if len(a) < 2 or len(b) < 2: return None
    rng = np.random.default_rng(seed)
    da = rng.choice(a, (n, len(a)), True).mean(1); db = rng.choice(b, (n, len(b)), True).mean(1)
    d = da - db
    return float((np.mean(a) - np.mean(b)) * 100), float(np.percentile(d, 2.5) * 100), float(np.percentile(d, 97.5) * 100), float(np.mean(d <= 0))

def segment(deep, tag):
    if tag == "IN": return deep[(deep["ym"] >= "2019-01") & (deep["ym"] <= "2022-12")]
    if tag == "OOS": return deep[deep["ym"] >= "2023-01"]
    return deep[deep["ym"] >= "2019-01"]

def run(args):
    import pandas as pd, numpy as np
    log("월봉·PBR 패널 구축 중...(최초 실행 시 일봉 축약, 이후 캐시)")
    deep = build_deep(pd, np)
    flow, used = load_flow(pd)
    short = load_short(pd)
    deep = deep.merge(flow, on=["code", "ym"], how="left")
    deep["has_flow"] = deep["foreign_net"].notna() & deep["inst_net"].notna()
    deep["ipos"] = deep["inst_net"] > 0; deep["fpos"] = deep["foreign_net"] > 0
    log(f"\nflow 소스: {used}")
    log(f"공매도 소스: {'short_balance_monthly_*' if short is not None else '없음 → 숏커버 정교화 생략'}")
    n_deep = len(deep); n_flow = int(deep['has_flow'].sum())
    log(f"딥밸류바닥 {n_deep}종·월 | flow 보유 {n_flow} | 기관매집 {int((deep['has_flow']&deep['ipos']).sum())}")

    # 기관매집 코호트에 숏커버 분류
    inst = deep[deep["has_flow"] & deep["ipos"]].copy()

    # 공매도 타깃수집용 후보코드 덤프(공매도 없을 때만 안내): 딥+기관 & 2015+ (직전월 포함 위해 여유)
    if short is None:
        cand = sorted(inst[inst["ym"] >= "2015-01"]["code"].unique())
        cf = os.path.join(BASE, "_수급_후보코드.txt")
        with open(cf, "w", encoding="utf-8") as fh:
            fh.write("\n".join(cand) + "\n")
        log(f"\n[안내] 공매도 데이터가 아직 없음. 숏커버 정교화를 하려면 후보 {len(cand)}종만 타깃 수집하면 빠름:")
        log(f"       후보코드 저장 → _수급_후보코드.txt")
        log(f"       실행: py fetch_수급확장_pykrx.py --market KOSPI --codes _수급_후보코드.txt --no-flow")
        log(f"       (이후 이 스크립트 재실행하면 숏커버 분리·재검증 수행)")

    inst = classify_shortcover(pd, inst, short, args.sc_thresh, args.sc_rel)

    # 커버리지 정직 보고
    if short is not None:
        cov = inst["sc_class"].value_counts().to_dict()
        tot = len(inst)
        log("\n=== 숏커버 분류 커버리지 (딥+기관매집 진입월 기준) ===")
        for k in ["실매집", "숏커버동반", "무공매도데이터"]:
            c = cov.get(k, 0); log(f"  {k:<10}: {c:>4}  ({c/tot*100:4.0f}%)")
        classifiable = cov.get("실매집", 0) + cov.get("숏커버동반", 0)
        log(f"  → 숏커버 분리가능 표본: {classifiable}/{tot} ({classifiable/tot*100:.0f}%). 나머지는 공매도데이터 부재.")
        if classifiable < 20:
            log("  ⚠ 분리가능 표본<20 → 숏커버 하위검정은 통계적 의미 약함(참고만).")

    # §3 재검증: 코호트별 표
    def cohorts(seg_deep, seg_inst):
        base = seg_deep[seg_deep["has_flow"]]  # 딥+flow존재 전체를 base로? 아니, 딥 전체가 base
        return {
            "딥밸류바닥": seg_deep,
            "딥+기관매집": seg_inst,
            "딥+기관&실매집": seg_inst[seg_inst["sc_class"] == "실매집"],
            "딥+기관&숏커버동반": seg_inst[seg_inst["sc_class"] == "숏커버동반"],
            "딥+기관&무공매도데이터": seg_inst[seg_inst["sc_class"] == "무공매도데이터"],
        }
    log("\n" + "=" * 78 + "\n§3 재검증 — 코호트별 선행수익 (평균/중앙/승률, n)\n" + "=" * 78)
    for tag in ["ALL", "IN", "OOS"]:
        sd = segment(deep, tag); si = segment(inst, tag)
        ch = cohorts(sd, si)
        log(f"\n--- {tag} ---")
        for h, col in [(6, "f6"), (9, "f9"), (12, "f12")]:
            log(f"  [{h}M]")
            for name, d in ch.items():
                n, mn, md, wn = stats(d, col)
                if n == 0: log(f"    {name:<22} n=0"); continue
                log(f"    {name:<22} n={n:>4} 평균{mn:+6.1f}% 중앙{md:+6.1f}% 승률{wn:3.0f}%")

    # 유의성: 실매집/숏커버 vs 딥밸류단독, 그리고 실매집 vs 숏커버
    log("\n" + "=" * 78 + "\n유의성 (부트스트랩 95%CI, 12M)\n" + "=" * 78)
    for tag in ["ALL", "IN", "OOS"]:
        sd = segment(deep, tag); si = segment(inst, tag)
        base = sd["f12"].dropna().values
        real = si[si["sc_class"] == "실매집"]["f12"].dropna().values
        scov = si[si["sc_class"] == "숏커버동반"]["f12"].dropna().values
        log(f"\n[{tag}]")
        for name, s in [("실매집−딥단독", (real, base)), ("숏커버−딥단독", (scov, base)), ("실매집−숏커버", (real, scov))]:
            r = boot_diff(*s)
            if r: log(f"  {name:<12}: Δ{r[0]:+6.1f}%p 95%CI[{r[1]:+.1f},{r[2]:+.1f}] P(Δ≤0)={r[3]:.3f} (n={len(s[0])}vs{len(s[1])})")
            else: log(f"  {name:<12}: 표본부족(n={len(s[0])}vs{len(s[1])})")

    log("\n" + "=" * 78)
    log("판정 가이드(데이터로 결정·가정 금지):")
    log(" · 실매집>숏커버동반 & 실매집이 IN·OOS 양쪽 유의 → 딥+기관&실매집 하드필터 승격 검토.")
    log(" · 차이 없음 → 숏커버는 교란 아님, 기관매집 플래그 유지.")
    log(" · 숏커버동반≥실매집 → 숏스퀴즈형(다른 메커니즘), 문서화만.")
    log(" · 분리가능 표본이 작거나 공매도 커버리지 낮으면 결론 보류(정직).")
    return 0

def _self_test():
    """분류·통계 로직 synthetic 검증(시장 결론 아님)."""
    import pandas as pd, numpy as np
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0; print(f"  [{'OK' if c else 'FAIL'}] {n}")
    short = pd.DataFrame({
        "code": ["000001", "000001", "000002", "000002", "000003"],
        "ym":   ["2020-01", "2020-02", "2020-01", "2020-02", "2020-02"],
        "short_qty":   [1000, 400, 1000, 1200, 0],
        "short_ratio": [1.0, 0.3, 1.0, 1.2, 0.0],
    })
    inst = pd.DataFrame({"code": ["000001", "000002", "000003", "000004"],
                         "ym": ["2020-02", "2020-02", "2020-02", "2020-02"]})
    out = classify_shortcover(pd, inst, short, 0.1)
    m = dict(zip(out["code"], out["sc_class"]))
    chk("비중 1.0→0.3 급감 → 숏커버동반", m["000001"] == "숏커버동반")
    chk("비중 1.0→1.2 증가 → 실매집", m["000002"] == "실매집")
    chk("잔고 0(숏없음) 단독관측 → 실매집", m["000003"] == "실매집")
    chk("공매도데이터 전무 → 무공매도데이터", m["000004"] == "무공매도데이터")
    out2 = classify_shortcover(pd, inst, None, 0.1)
    chk("short 파일 없음 → 전부 무공매도데이터", (out2["sc_class"] == "무공매도데이터").all())
    r = boot_diff(np.array([0.5]*30 + [0.1]*10), np.array([0.0]*40))
    chk("boot_diff 반환형", r is not None and len(r) == 4)
    n, mn, md, wn = stats(pd.DataFrame({"x": [0.1, -0.2, 0.3]}), "x")
    chk("stats 승률", abs(wn - 66.6667) < 1)
    print(f"\n셀프테스트: {ok}/{tot}"); return ok == tot

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sc-thresh", type=float, default=0.1, help="숏커버 판정: 진입월 공매도비중(%%p) 감소 임계(비중 제공시)")
    ap.add_argument("--sc-rel", type=float, default=0.20, help="숏커버 판정: 비중 없을 때 잔고수량 상대감소 임계(0.20=20%%)")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    return run(a)

if __name__ == "__main__":
    sys.exit(main())
