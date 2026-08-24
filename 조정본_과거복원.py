#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
조정본_과거복원.py — 상폐 종목 수정주가 복원 (§8-1b)

── 문제 ──────────────────────────────────────────────────────────
`데이터수리\_월봉종가캐시_*_adj.csv` 는 **3,801종목**뿐인데 미조정 원본은 **5,058종목**이다.
빠진 **1,257종목이 전부 상폐 종목**이다. 그래서 조정본 과거 커버리지가 무너져 있다:

    1996-01  0.1%  ·  2000-01  8.2%  ·  2005-01 25.2%  ·  2010-01 26.6%  ·  2015-01+ 100%

원인은 이미 로그에 남아 있었다 — `_adj_실패_KOSPI.csv` 653건 · `_adj_실패_KOSDAQ.csv` 620건,
사유 전부 `empty (상폐/데이터없음)`. **pykrx는 상폐 종목의 수정주가를 주지 않는다.**
네트워크로 더 긁어도 안 나온다. 다른 길이 필요하다.

── 방법: 시총으로 주식수를 복원해 기업행위를 **계산**한다 ──────────────
`종목시총_30년.csv` 가 2026-07-27 보수로 **367/367개월 완전**해졌고, 재수집 대상
1,257종목 중 **1,248종목(99.3%)** 의 시총을 갖고 있다.

    주식수_t = 시총_t / 미조정종가_t

기업행위(액면분할·병합)는 **주식수가 변하면서 가격이 정확히 반대로 튀는** 사건이다.
증자·감자와 구별하려면 그 조건을 그대로 검사하면 된다:

    sr = 주식수_t / 주식수_{t-1}          # 주식수 변동
    pr = 가격_t / 가격_{t-1}              # 가격 변동
    if |sr − 1| > tol  and  |pr × sr − 1| < band:   # 가격 점프가 주식수로 설명되는가
        보유자 실수익률 r_t = pr × sr      # 분할 → 주식이 늘어난 만큼 회복
    else:
        r_t = pr                           # 유상증자·자사주소각 등은 조정 안 함

종전 `ca_adjust.py` 는 배수를 **정수로 추측**했다(2~50배, ±3%). 이건 주식수를 **직접 읽는다.**

── 검증 설계 ──────────────────────────────────────────────────────
pykrx 조정본이 있는 **3,801종목이 정답지**다. 같은 방법을 그들에게 적용해
KRX 공식 수정주가와 월수익률을 대조하면 **유도법의 정확도를 숫자로 알 수 있다.**
그 정확도를 확인한 뒤에만 상폐 1,257종목에 적용한다.

산출: `_월봉종가캐시_<MKT>_full.csv` (code,ym,close,source)
      source = `krx`(공식 수정주가) | `derived`(시총 유도) | `raw`(시총 없어 미조정 그대로)

── 사용 ───────────────────────────────────────────────────────────
    py 조정본_과거복원.py --validate-only    # 검증만 (파일 안 씀) — 먼저 이것부터
    py 조정본_과거복원.py                    # 검증 후 복원본 생성
    py 조정본_과거복원.py --tol 0.02 --band 0.15

⚠️ 네트워크 불필요 (전부 로컬 데이터) · 원본 미변경 · 검증용 · 투자자문 아님
"""
import argparse
import glob
import os
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
MKTS = ("KOSPI", "KOSDAQ")


def find(name):
    for b in (ROOT, os.getcwd()):
        h = [x for x in glob.glob(os.path.join(b, "**", name), recursive=True)
             if not any(s in x for s in ("_백업", "_보관", "_archive", "__pycache__"))]
        if h:
            return sorted(h, key=len)[0]
    return None


def load_raw(mkt):
    p = find(f"_월봉종가캐시_{mkt}.csv")
    d = pd.read_csv(p, dtype={"code": str})
    d.columns = [c.strip().lstrip("﻿") for c in d.columns]
    d["code"] = d["code"].str.zfill(6)
    return d[["code", "ym", "close"]]


def load_krx_adj(mkt):
    p = find(f"_월봉종가캐시_{mkt}_adj.csv")
    if not p:
        return None
    d = pd.read_csv(p, dtype={"code": str})
    d.columns = [c.strip().lstrip("﻿") for c in d.columns]
    d["code"] = d["code"].str.zfill(6)
    return d[["code", "ym", "close"]]


def load_mcap():
    p = find("종목시총_30년.csv")
    d = pd.read_csv(p, dtype={"code": str})
    d.columns = [c.strip().lstrip("﻿") for c in d.columns]
    d["code"] = d["code"].str.zfill(6)
    d["ym"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m")
    d["mcap"] = pd.to_numeric(d["mcap"], errors="coerce")
    return d.groupby(["code", "ym"], as_index=False)["mcap"].last()


def derive_returns(raw, mcap, tol, band):
    """시총 유도 기업행위 보정 월수익률. 반환: code,ym,r,ca_factor"""
    d = raw.merge(mcap, on=["code", "ym"], how="left").sort_values(["code", "ym"])
    d["close"] = pd.to_numeric(d["close"], errors="coerce")
    d = d[d["close"] > 0]
    d["shares"] = d["mcap"] / d["close"]
    g = d.groupby("code", sort=False)
    d["pr"] = g["close"].transform(lambda s: s / s.shift(1))
    d["sr"] = g["shares"].transform(lambda s: s / s.shift(1))
    ok = (d["sr"].notna() & d["pr"].notna()
          & ((d["sr"] - 1).abs() > tol)
          & ((d["pr"] * d["sr"] - 1).abs() < band))
    d["ca"] = np.where(ok, d["sr"], 1.0)
    d["r"] = d["pr"] * d["ca"] - 1
    return d[["code", "ym", "close", "r", "ca", "shares"]]


def rebuild_prices(dr):
    """수익률 → 가격 시계열. 마지막 실제가에 맞춰 스케일(back-adjust)."""
    out = []
    for code, g in dr.groupby("code", sort=False):
        g = g.sort_values("ym").copy()
        r = g["r"].fillna(0).values
        idx = np.cumprod(1 + r)
        last = g["close"].values[-1]
        if idx[-1] <= 0 or not np.isfinite(idx[-1]):
            g["adj"] = g["close"].values
        else:
            g["adj"] = idx / idx[-1] * last
        out.append(g[["code", "ym", "adj"]])
    return pd.concat(out, ignore_index=True)


def validate(dr, krx, mkt):
    """정답지(pykrx 조정본)와 월수익률 대조."""
    k = krx.sort_values(["code", "ym"]).copy()
    k["close"] = pd.to_numeric(k["close"], errors="coerce")
    k["r_krx"] = k.groupby("code")["close"].transform(lambda s: s / s.shift(1) - 1)
    m = dr.merge(k[["code", "ym", "r_krx"]], on=["code", "ym"], how="inner").dropna(subset=["r", "r_krx"])
    m = m[(m["r"].abs() < 1.5) & (m["r_krx"].abs() < 1.5)]
    if not len(m):
        return None
    diff = (m["r"] - m["r_krx"]).abs()
    res = dict(
        n=len(m), codes=m["code"].nunique(),
        corr=float(m["r"].corr(m["r_krx"])),
        mad=float(diff.mean()),
        p50=float(diff.quantile(.50)), p95=float(diff.quantile(.95)),
        within1bp=float((diff < 0.0001).mean()), within1pct=float((diff < 0.01).mean()),
        ca_hits=int((m["ca"] != 1.0).sum()),
    )
    print(f"\n  [{mkt}] 유도법 정확도 — 정답지 pykrx 조정본 대조")
    print(f"    표본 {res['n']:,} (종목·월) · 종목 {res['codes']:,} · CA 적용 {res['ca_hits']:,}건")
    print(f"    월수익률 상관 **{res['corr']:.5f}**")
    print(f"    절대차 평균 {res['mad']*100:.4f}%p · 중앙값 {res['p50']*100:.4f}%p · 95%ile {res['p95']*100:.4f}%p")
    print(f"    1bp 이내 일치 {res['within1bp']*100:.1f}% · 1%p 이내 {res['within1pct']*100:.1f}%")
    return res


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tol", type=float, default=0.02, help="주식수 변동 인식 임계")
    ap.add_argument("--band", type=float, default=0.15, help="가격 점프가 주식수로 설명되는 허용폭")
    ap.add_argument("--validate-only", action="store_true")
    ap.add_argument("--missing-only", action="store_true",
                    help="조정본에 아예 없는 코드만 복원(구 동작). 기본은 전 종목 전 이력 유도.")
    ap.add_argument("--out", default="데이터수리")
    a = ap.parse_args()

    print("=" * 78)
    print(" 상폐 종목 수정주가 복원 · §8-1b · 시총 유도 기업행위 보정")
    print("=" * 78)
    print(f"  파라미터: tol={a.tol} (주식수 변동 인식) · band={a.band} (가격-주식수 정합)")

    mcap = load_mcap()
    print(f"  시총: {mcap['code'].nunique():,}종목 × {mcap['ym'].nunique()}개월")

    summary = []
    for mkt in MKTS:
        raw = load_raw(mkt)
        krx = load_krx_adj(mkt)
        have = set(krx["code"]) if krx is not None else set()
        miss = sorted(set(raw["code"]) - have)
        print(f"\n{'='*78}\n  [{mkt}] 미조정 {raw['code'].nunique():,}종목 · "
              f"KRX 조정본 {len(have):,} · **복원 대상 {len(miss):,}**")

        dr = derive_returns(raw, mcap, a.tol, a.band)
        v = validate(dr[dr["code"].isin(have)], krx, mkt) if krx is not None else None

        if a.validate_only:
            summary.append((mkt, v, len(miss), 0))
            continue

        if v is None or v["corr"] < 0.95:
            print(f"  🚨 [{mkt}] 유도법 정확도 미달 (상관 {v['corr'] if v else 'N/A'}) — 복원 중단.")
            summary.append((mkt, v, len(miss), 0))
            continue

        # 2026-07-27 정정: 문제는 "조정본에 없는 1,257종목"만이 아니었다.
        # KRX 조정본은 **3,801종목 중 1,690개가 2014년부터** 시작한다(하드 절단).
        # 2010-01 시점 미조정 1,972 vs KRX조정본 533 — 코드 누락이 아니라 **이력 절단**이다.
        # → 전 종목 전 이력을 유도로 만들고, KRX가 있는 구간은 검증에만 쓴다.
        if a.missing_only:
            sub = dr[dr["code"].isin(miss)]
            rec = rebuild_prices(sub).rename(columns={"adj": "close"})
            rec["source"] = "derived"
            base = krx.copy(); base["source"] = "krx"
            full = pd.concat([base, rec], ignore_index=True).sort_values(["code", "ym"])
        else:
            rec = rebuild_prices(dr).rename(columns={"adj": "close"})
            kk = krx[["code", "ym"]].assign(_k=1)
            rec = rec.merge(kk, on=["code", "ym"], how="left")
            rec["source"] = np.where(rec["_k"].eq(1), "derived(krx확인구간)", "derived")
            full = rec.drop(columns=["_k"]).sort_values(["code", "ym"])
        outp = os.path.join(ROOT, a.out, f"_월봉종가캐시_{mkt}_full.csv")
        full.to_csv(outp, index=False, encoding="utf-8")
        n_new = rec["code"].nunique()
        mode = "결측코드만" if a.missing_only else "전 종목 전 이력 유도"
        print(f"  ✅ 저장 {os.path.relpath(outp, ROOT)} · {len(full):,}행 · "
              f"{full['code'].nunique():,}종목 · 방식 {mode}")
        summary.append((mkt, v, len(miss), n_new))

    # ── 커버리지 비교
    print("\n" + "=" * 78)
    print("  커버리지 — 조정본 vs 복원본 (미조정 대비 %)")
    print("=" * 78)
    rawall = pd.concat([load_raw(m) for m in MKTS])
    krxall = pd.concat([x for x in (load_krx_adj(m) for m in MKTS) if x is not None])
    fulls = []
    for m in MKTS:
        p = os.path.join(ROOT, a.out, f"_월봉종가캐시_{m}_full.csv")
        if os.path.exists(p):
            fulls.append(pd.read_csv(p, dtype={"code": str}))
    fullall = pd.concat(fulls) if fulls else None

    print(f"  {'시점':10}{'미조정':>9}{'KRX조정본':>11}{'복원본':>9}   {'KRX%':>7}{'복원%':>8}")
    for ym in ("1996-01", "2000-01", "2005-01", "2010-01", "2015-01", "2020-01", "2026-06"):
        nr = (rawall["ym"] == ym).sum()
        nk = (krxall["ym"] == ym).sum()
        nf = (fullall["ym"] == ym).sum() if fullall is not None else 0
        if nr:
            print(f"  {ym:10}{nr:>9,}{nk:>11,}{nf:>9,}   {nk/nr*100:>6.1f}%{nf/nr*100:>7.1f}%")

    print("\n" + "-" * 78)
    for mkt, v, nmiss, nnew in summary:
        c = f"상관 {v['corr']:.5f} · 절대차 {v['mad']*100:.4f}%p" if v else "검증 불가"
        print(f"  [{mkt}] {c} · 대상 {nmiss:,} · 복원 {nnew:,}")
    if not a.validate_only:
        print("\n  다음 — 복원본을 쓰려면:")
        print("    py 롱온리_재산출.py --adj --full --pool 100")
        print("    py 진우퀀트_게이트.py")
    print("\n  ⚠️ `derived` 는 KRX 공식 수정주가가 아니라 시총으로 유도한 값이다.")
    print("     위 상관·절대차가 그 신뢰도의 전부다. 백서에 쓸 땐 반드시 병기할 것.")
    print("  ⚠️ 검증용 · 실현손익 아님 · 투자자문 아님")
    return 0


if __name__ == "__main__":
    sys.exit(main())
