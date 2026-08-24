#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""검증_수급_일봉정밀.py — 딥밸류+수급 오버레이를 '일봉 정밀'로 재검증 + 주봉 수급 오버레이.

기존 검증_수급오버레이_정교화.py 는 월봉 근사(월 MA10≈일 MA200)였음. 진우 지시:
  "보통 주봉·일봉 모두 확인" → 가격신호를 실제 일봉으로 정밀화하고, 수급을 주봉으로도 검증.

이 스크립트:
  1) 딥밸류 바닥을 '실제 일봉'으로 계산 — 정확한 일 MA200·이격(close/MA200)·20일수익.
     · 월말 거래일 캐던스로 1종목·1월 1관측(월봉판과 표본구조 비교 가능, 자기상관 억제).
  2) 선행수익도 '일봉 정밀' — 진입 월말일 기준 +126/189/252 거래일(≈6/9/12M).
     · 상폐 처리: 창내 마지막 유효가/진입가−1, 진입직후 전멸 −1.0. 데이터끝 근처(여전상장) 창잘림=제외(NaN).
  3) 수급 오버레이: 월간(flow_ext_monthly/기존) + 주간(flow_ext_weekly, 있으면).
     · 기관매집(월)=진입월 기관순매수>0 · 기관매집(주)=진입 직전 주 기관순매수>0.
  4) §3 IN/OOS + 부트스트랩. 월봉 근사 결론이 일봉에서도 유지되는지 확인.

정직: 수급 없는 구간은 코호트서 제외(위조 안 함). 주봉 파일 없으면 주봉 오버레이 생략.
      일봉 정밀은 근사 제거일 뿐 미래보장 아님.

의존: 종목일봉_30년_{KOSPI,KOSDAQ}.csv, 종목재무_KRX_*, flow_ext_monthly_*|{kospi,kosdaq}_flow_monthly.csv,
      (선택) flow_ext_weekly_{KOSPI,KOSDAQ}.csv
사용: python 검증_수급_일봉정밀.py [--self-test]
"""
import os, sys, argparse, datetime as dt
BASE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
CUTOFF = "2018-01-01"; HDAYS = {6: 126, 9: 189, 12: 252}
def log(*a): print(*a); sys.stdout.flush()

def build_daily(pd, market):
    """일봉(2018+, 상폐포함) → [code,date,close]. 캐시/tmp 인식."""
    cache = os.path.join(BASE, f"_일봉정밀캐시_{market}.csv")
    if os.path.exists(cache): return pd.read_csv(cache, dtype={"code": str})
    tmp = f"/tmp/dpx_{market}.csv"
    if os.path.exists(tmp):
        d = pd.read_csv(tmp, header=None, names=["code", "date", "close"], dtype={0: str})
        d["code"] = d["code"].str.zfill(6); return d   # /tmp 경로: 대용량 캐시쓰기 생략(속도)
    p = os.path.join(BASE, f"종목일봉_30년_{market}.csv")
    keep = []
    for ch in pd.read_csv(p, usecols=["date", "code", "close"], dtype={"code": str},
                          encoding="utf-8-sig", chunksize=2_000_000):
        ch = ch[(ch["date"] >= CUTOFF)]
        ch = ch[pd.to_numeric(ch["close"], errors="coerce") > 0]
        keep.append(ch[["code", "date", "close"]])
    d = pd.concat(keep, ignore_index=True); d["code"] = d["code"].str.zfill(6)
    d.to_csv(cache, index=False, encoding="utf-8-sig"); return d

def build_signals(pd, np):
    """일봉 정밀 딥밸류 신호(월말 캐던스) + 선행수익. 벡터화·캐시."""
    cache = os.path.join(BASE, "_일봉신호캐시.csv")
    if os.path.exists(cache):
        return pd.read_csv(cache, dtype={"code": str})
    parts = [build_daily(pd, m) for m in ("KOSPI", "KOSDAQ")]
    d = pd.concat(parts, ignore_index=True)
    d["close"] = pd.to_numeric(d["close"], errors="coerce")
    d = d.dropna(subset=["close"]).sort_values(["code", "date"]).reset_index(drop=True)  # 일봉은 (code,date) 고유
    gl = d["date"].max(); gl_dt = dt.date(int(gl[:4]), int(gl[5:7]), int(gl[8:10]))
    buf = (gl_dt - dt.timedelta(days=15)).isoformat()
    g = d.groupby("code")["close"]
    d["ma200"] = g.rolling(200, min_periods=200).mean().reset_index(level=0, drop=True)
    d["ret20"] = g.pct_change(20)
    d["ym"] = d["date"].str[:7]
    d["is_me"] = (d["code"] != d["code"].shift(-1)) | (d["ym"] != d["ym"].shift(-1))  # 월말 거래일
    d["lastclose"] = g.transform("last")
    d["lastdate"] = d.groupby("code")["date"].transform("last")
    d["alive"] = d["lastdate"] >= buf
    d["n_after"] = d.groupby("code").cumcount(ascending=False)  # 뒤로 남은 행수(0=마지막)
    d["ext"] = d["close"] / d["ma200"]
    for h, H in HDAYS.items():
        fc = d.groupby("code")["close"].shift(-H)
        f = fc / d["close"] - 1.0                       # 완전창(정상)
        deld = fc.isna() & (~d["alive"])                # 상폐(창 밖=시리즈 끝<데이터끝)
        f = f.mask(deld, d["lastclose"] / d["close"] - 1.0)   # 창내 마지막 유효가
        f = f.mask(deld & (d["n_after"] == 0), -1.0)          # 진입직후 전멸
        # alive & fc결측 → 창잘림 → NaN 유지
        d[f"f{h}"] = f
    P = d[d["is_me"] & d["ma200"].notna() & (d["close"] >= 1000) & d["ret20"].notna()].copy()
    P = P[["code", "date", "ym", "close", "ext", "ret20", "f6", "f9", "f12"]].reset_index(drop=True)
    P.to_csv(cache, index=False, encoding="utf-8-sig")
    return P

def load_pbr(pd):
    fp = []
    for m in ("KOSPI", "KOSDAQ"):
        f = pd.read_csv(os.path.join(BASE, f"종목재무_KRX_{m}.csv"), dtype={"code": str})[["date", "code", "PBR"]]
        fp.append(f)
    fund = pd.concat(fp, ignore_index=True); fund["code"] = fund["code"].str.zfill(6)
    fund["ym"] = fund["date"].str[:7]; fund["PBR"] = pd.to_numeric(fund["PBR"], errors="coerce")
    return fund.drop_duplicates(["code", "ym"])[["code", "ym", "PBR"]]

def load_flow_monthly(pd):
    src = []
    for m in ("KOSPI", "KOSDAQ"):
        ext = os.path.join(BASE, f"flow_ext_monthly_{m}.csv")
        old = os.path.join(BASE, f"{m.lower()}_flow_monthly.csv")
        p = ext if os.path.exists(ext) else (old if os.path.exists(old) else None)
        if p: src.append(p)
    if not src: sys.exit("월간 flow 없음")
    dfs = []
    for p in src:
        d = pd.read_csv(p, dtype={"code": str}); d["code"] = d["code"].str.zfill(6); d["ym"] = d["date"].str[:7]
        for c in ("foreign_net", "inst_net"): d[c] = pd.to_numeric(d[c], errors="coerce")
        dfs.append(d[["code", "ym", "foreign_net", "inst_net"]])
    return pd.concat(dfs, ignore_index=True).drop_duplicates(["code", "ym"]), ",".join(os.path.basename(x) for x in src)

def load_flow_weekly(pd):
    dfs = []
    for m in ("KOSPI", "KOSDAQ"):
        p = os.path.join(BASE, f"flow_ext_weekly_{m}.csv")
        if os.path.exists(p):
            d = pd.read_csv(p, dtype={"code": str}); d["code"] = d["code"].str.zfill(6)
            for c in ("foreign_net", "inst_net"): d[c] = pd.to_numeric(d[c], errors="coerce")
            dfs.append(d[["code", "date", "foreign_net", "inst_net"]])
    if not dfs: return None
    return pd.concat(dfs, ignore_index=True).drop_duplicates(["code", "date"])

def attach_weekly(pd, deep, wk):
    """진입 월말일 직전(≤7일) 주간 기관/외국인 순매수 부착."""
    if wk is None:
        deep["w_ipos"] = np.nan if False else None; deep["w_fpos"] = None; return deep
    wmap = {}
    for code, g in wk.sort_values(["code", "date"]).groupby("code"):
        wmap[code] = list(zip(g["date"].tolist(), g["inst_net"].tolist(), g["foreign_net"].tolist()))
    def wk_of(code, d):
        seq = wmap.get(code)
        if not seq: return None, None
        best = None
        for (wd, iv, fv) in seq:
            if wd <= d: best = (wd, iv, fv)
            else: break
        if best is None: return None, None
        d0 = dt.date(int(d[:4]), int(d[5:7]), int(d[8:10]))
        w0 = dt.date(int(best[0][:4]), int(best[0][5:7]), int(best[0][8:10]))
        if (d0 - w0).days > 7: return None, None
        return best[1], best[2]
    wi = []; wf = []
    for code, d in zip(deep["code"], deep["date"]):
        iv, fv = wk_of(code, d); wi.append(iv); wf.append(fv)
    deep = deep.copy(); deep["w_inst"] = wi; deep["w_for"] = wf
    return deep

def stats(df, col):
    import numpy as np
    x = df[col].dropna().values
    if len(x) == 0: return (0, None, None, None)
    return (len(x), float(np.mean(x) * 100), float(np.median(x) * 100), float(np.mean(x > 0) * 100))

def boot_diff(a, b, n=5000, seed=42):
    import numpy as np
    a = np.asarray(a, float); b = np.asarray(b, float)
    if len(a) < 2 or len(b) < 2: return None
    rng = np.random.default_rng(seed)
    d = rng.choice(a, (n, len(a)), True).mean(1) - rng.choice(b, (n, len(b)), True).mean(1)
    return float((a.mean() - b.mean()) * 100), float(np.percentile(d, 2.5) * 100), float(np.percentile(d, 97.5) * 100), float(np.mean(d <= 0))

def seg(df, tag):
    if tag == "IN": return df[(df["ym"] >= "2019-01") & (df["ym"] <= "2022-12")]
    if tag == "OOS": return df[df["ym"] >= "2023-01"]
    return df[df["ym"] >= "2019-01"]

def run(a):
    import pandas as pd, numpy as np
    globals()["np"] = np
    log("일봉 정밀 신호·선행수익 구축 중...(최초 일봉 축약, 이후 캐시)")
    P = build_signals(pd, np)
    pbr = load_pbr(pd); fm, fsrc = load_flow_monthly(pd); wk = load_flow_weekly(pd)
    P = P.merge(pbr, on=["code", "ym"], how="left")
    valid = (P["close"] >= 1000) & (P["ext"].notna()) & (P["PBR"] > 0)
    Pv = P[valid].copy()
    Pv["pbr_rank"] = Pv.groupby("ym")["PBR"].rank(pct=True)
    Pv["deep"] = (Pv["pbr_rank"] <= 0.20) & (Pv["ext"] < 0.85) & (Pv["ret20"] > 0)
    deep = Pv[Pv["deep"]].copy()
    deep = deep.merge(fm, on=["code", "ym"], how="left")
    deep["has_flow"] = deep["foreign_net"].notna() & deep["inst_net"].notna()
    deep["ipos"] = deep["inst_net"] > 0; deep["fpos"] = deep["foreign_net"] > 0
    deep = attach_weekly(pd, deep, wk)
    deep["w_ipos"] = deep["w_inst"] > 0 if wk is not None else None
    log(f"\n[일봉 정밀] flow월간: {fsrc} | 주간: {'flow_ext_weekly_*' if wk is not None else '없음→주봉 오버레이 생략'}")
    log(f"딥밸류바닥(일봉) {len(deep)}종·월 | flow보유 {int(deep['has_flow'].sum())} | 기관매집(월) {int((deep['has_flow']&deep['ipos']).sum())}"
        + (f" | 기관매집(주) {int((deep['w_ipos']==True).sum())}" if wk is not None else ""))

    def cohorts(sd):
        si = sd[sd["has_flow"]]
        c = {"딥밸류바닥(일봉)": sd,
             "딥+기관매집(월)": si[si["ipos"]],
             "딥+외국인매집(월)": si[si["fpos"]]}
        if wk is not None:
            c["딥+기관매집(주)"] = sd[sd["w_ipos"] == True]
        return c
    log("\n" + "=" * 74 + "\n§3 재검증 (일봉 정밀) — 평균/중앙/승률, n\n" + "=" * 74)
    for tag in ["ALL", "IN", "OOS"]:
        sd = seg(deep, tag)
        log(f"\n--- {tag} ---")
        for h, col in [(6, "f6"), (9, "f9"), (12, "f12")]:
            log(f"  [{h}M]")
            for name, dd in cohorts(sd).items():
                n, mn, md, wn = stats(dd, col)
                log(f"    {name:<20} " + ("n=0" if n == 0 else f"n={n:>4} 평균{mn:+6.1f}% 중앙{md:+6.1f}% 승률{wn:3.0f}%"))
    log("\n" + "=" * 74 + "\n유의성 (코호트 − 딥밸류단독, 부트스트랩 95%CI, 12M)\n" + "=" * 74)
    for tag in ["ALL", "IN", "OOS"]:
        sd = seg(deep, tag); base = sd["f12"].dropna().values; si = sd[sd["has_flow"]]
        log(f"\n[{tag}]")
        pairs = [("기관(월)", si[si["ipos"]]["f12"].dropna().values),
                 ("외국인(월)", si[si["fpos"]]["f12"].dropna().values)]
        if wk is not None: pairs.append(("기관(주)", sd[sd["w_ipos"] == True]["f12"].dropna().values))
        for name, s in pairs:
            r = boot_diff(s, base)
            log(f"  {name:<8}: " + ("표본부족" if r is None else f"Δ{r[0]:+6.1f}%p 95%CI[{r[1]:+.1f},{r[2]:+.1f}] P(Δ≤0)={r[3]:.3f} n={len(s)}"))
    log("\n판정 가이드: 일봉 정밀에서도 딥+기관이 딥단독을 IN·OOS 양쪽 유의하게 능가하면 월봉결론 견고.")
    log("            주봉(주) 코호트가 월간과 방향 일치하면 그레인 강건성 확인. 아니면 월봉 근사 취약.")
    return 0

def _self_test():
    import pandas as pd, numpy as np
    globals()["np"] = np
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0; print(f"  [{'OK' if c else 'FAIL'}] {n}")
    n, mn, md, wn = stats(pd.DataFrame({"x": [0.1, -0.2, 0.3, 0.4]}), "x")
    chk("stats 승률 75%", abs(wn - 75) < 1e-6)
    r = boot_diff(np.array([0.5] * 30 + [0.2] * 10), np.array([0.0] * 40))
    chk("boot_diff 형식", r is not None and len(r) == 4 and r[0] > 0)
    wk = pd.DataFrame({"code": ["000001", "000001"], "date": ["2020-01-24", "2020-01-31"],
                       "inst_net": [-5.0, 9.0], "foreign_net": [1.0, 1.0]})
    deep = pd.DataFrame({"code": ["000001", "000001"], "date": ["2020-01-31", "2020-02-28"]})
    out = attach_weekly(pd, deep, wk)
    chk("주간 매칭: 1/31→그 주(1/31) inst=9", out.iloc[0]["w_inst"] == 9.0)
    chk("주간 매칭: 2/28→7일내 주 없음→결측", pd.isna(out.iloc[1]["w_inst"]))
    chk("w_ipos: 결측>0 = False(코호트 제외)", ((out["w_inst"] > 0).iloc[1]) == False)
    print(f"\n셀프테스트: {ok}/{tot}"); return ok == tot

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    return run(a)

if __name__ == "__main__":
    sys.exit(main())
