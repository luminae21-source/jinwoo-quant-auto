# -*- coding: utf-8 -*-
r"""
build_style_panel.py — forward 신호용 스타일 패널 생성기 (2026-07-27 신규)

배경: `mini_style_panel.csv`가 샌드박스에서 만들어져 PC에 생성기가 없었다.
      그 결과 패널이 2026-06에서 멈춰 8/1 신호를 만들 수 없는 상태였다.
      이 스크립트로 **PC에서 독립적으로** 매월 갱신할 수 있다.

산출 컬럼 (기존 패널과 동일):
  ym, code, pbr, div, ep, bp, roe, g1, fwd_ret

팩터 정의 (factor_efficacy.py와 동일 — 2026-07-27 룩어헤드 감사 통과):
  div = DIV(배당수익률 %) · bp = 1/PBR · ep = 1/PER
  roe = EPS/BPS · g1 = EPS/EPS.shift(12)-1 (clip -1~3)
  fwd_ret = 가격.pct_change().shift(-1)   ← t월말 지표 → t+1 수익

유니버스: 시총 상위 TOPUNIV(기본 300), KOSPI+KOSDAQ

사용 (진우퀀트 폴더에서):
  python build_style_panel.py                       # 기본: 감사\미니샘플2\ 에 저장
  python build_style_panel.py --start 2006-01 --top 300
  python build_style_panel.py --out 감사\미니샘플2\mini_style_panel.csv --compare
"""
try:  # 윈도 파이프(cp949)에서 이모지 출력 시 UnicodeEncodeError 방지 (2026-07-27)
    import sys as _sys; _sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

import argparse, glob, os, sys
import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))


def find(name):
    hits = [p for p in glob.glob(os.path.join(ROOT, "**", name), recursive=True)
            if "_백업" not in p and "_archive" not in p]
    return sorted(hits, key=len)[0] if hits else None


def load_csv(name, **kw):
    p = find(name)
    if not p:
        return None, None
    for enc in ("utf-8", "cp949", "utf-8-sig"):
        try:
            return pd.read_csv(p, encoding=enc, **kw), p
        except UnicodeDecodeError:
            continue
    return pd.read_csv(p, **kw), p


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join("감사", "미니샘플2", "mini_style_panel.csv"))
    ap.add_argument("--start", default="2006-01")
    ap.add_argument("--top", type=int, default=300)
    ap.add_argument("--adjusted", action="store_true", default=True,
                    help="조정본 월봉 우선 사용(기본 True)")
    # 2026-07-27: --adjusted가 store_true+default=True라 끌 방법이 없었다.
    # 조정본(_adj)은 2014년 이전 커버리지가 25%대라 과거 구간에 생존편향이 들어간다.
    ap.add_argument("--raw", action="store_true",
                    help="미조정 월봉 강제(상폐포함 원본) — 과거구간 백테용")
    ap.add_argument("--compare", action="store_true", help="기존 패널과 대조")
    a = ap.parse_args()
    if a.raw:
        a.adjusted = False

    print("=" * 70)
    print(" 스타일 패널 생성기 · forward 신호용")
    print("=" * 70)

    # ── 1. 재무
    frames = []
    for mkt in ("KOSPI", "KOSDAQ"):
        d, p = load_csv(f"종목재무_KRX_{mkt}.csv", dtype={"code": str})
        if d is None:
            print(f"  ⚠️ 종목재무_KRX_{mkt}.csv 없음 — 건너뜀")
            continue
        d["code"] = d["code"].str.zfill(6)
        frames.append(d)
        print(f"  재무 {mkt}: {os.path.relpath(p, ROOT)} ({len(d):,}행)")
    if not frames:
        sys.exit("재무 파일을 못 찾음")
    fin = pd.concat(frames, ignore_index=True)
    fin["ym"] = pd.to_datetime(fin["date"]).dt.strftime("%Y-%m")

    # ── 2. 가격 (조정본 우선)
    pxf = []
    for mkt in ("KOSPI", "KOSDAQ"):
        for nm in ([f"_월봉종가캐시_{mkt}_adj.csv", f"_월봉종가캐시_{mkt}.csv"]
                   if a.adjusted else [f"_월봉종가캐시_{mkt}.csv"]):
            d, p = load_csv(nm, dtype={"code": str})
            if d is not None:
                d["code"] = d["code"].str.zfill(6)
                pxf.append(d)
                print(f"  가격 {mkt}: {os.path.relpath(p, ROOT)} ({d.code.nunique():,}종목)")
                break
    if not pxf:
        sys.exit("월봉 캐시를 못 찾음")
    PX = (pd.concat(pxf, ignore_index=True)
          .pivot_table(index="ym", columns="code", values="close", aggfunc="last").sort_index())

    # ── 3. 시총 (유니버스)
    mc, p = load_csv("종목시총_30년.csv", dtype={"code": str})
    if mc is None:
        sys.exit("종목시총_30년.csv 를 못 찾음")
    mc["code"] = mc["code"].str.zfill(6)
    mc["ym"] = pd.to_datetime(mc["date"]).dt.strftime("%Y-%m")
    MC = mc.pivot_table(index="ym", columns="code", values="mcap", aggfunc="last")
    print(f"  시총: {os.path.relpath(p, ROOT)} ({MC.index.min()}~{MC.index.max()})")

    # ── 4. 팩터 (factor_efficacy.py와 동일 정의)
    def wide(col):
        return fin.pivot_table(index="ym", columns="code", values=col, aggfunc="last")

    BPS, PER, PBR, EPS, DIV = (wide(c) for c in ("BPS", "PER", "PBR", "EPS", "DIV"))
    idx = [m for m in PX.index if m in MC.index and m in PER.index and m >= a.start]
    cols = sorted(set(PX.columns) & set(PER.columns) & set(MC.columns))
    print(f"  교집합: {len(idx)}개월 × {len(cols):,}종목 (start={a.start})")

    al = lambda d: d.reindex(index=idx, columns=cols)
    BPS, PER, PBR, EPS, DIV = map(al, (BPS, PER, PBR, EPS, DIV))
    P, M = al(PX), al(MC)

    # ★ fwd_ret: t월말 → t+1 수익 (룩어헤드 없음)
    RET = P.pct_change(fill_method=None).mask(lambda x: x.abs() > 1.0)
    FWD = RET.shift(-1)

    pbr = PBR.where(PBR > 0)
    bp = 1.0 / pbr
    ep = 1.0 / PER.where(PER > 0)
    div = DIV.where(DIV >= 0)
    roe = (EPS / BPS).where(BPS > 0)
    g1 = (EPS / EPS.shift(12) - 1).where(EPS.shift(12) > 0).clip(-1, 3)

    univ = M.rank(axis=1, ascending=False) <= a.top      # 전월말 시총 기준 top N

    # ── 5. long 변환
    def melt(df, name):
        return df.where(univ).stack(dropna=False).rename(name)

    panel = pd.concat([melt(pbr, "pbr"), melt(div, "div"), melt(ep, "ep"),
                       melt(bp, "bp"), melt(roe, "roe"), melt(g1, "g1"),
                       melt(FWD, "fwd_ret")], axis=1).reset_index()
    panel.columns = ["ym", "code"] + list(panel.columns[2:])
    panel = panel[panel[["pbr", "div", "ep", "bp", "roe"]].notna().any(axis=1)]
    panel = panel.sort_values(["ym", "code"]).reset_index(drop=True)

    out = a.out if os.path.isabs(a.out) else os.path.join(ROOT, a.out)
    os.makedirs(os.path.dirname(out), exist_ok=True)
    if os.path.exists(out):
        bak = out + ".bak"
        os.replace(out, bak)
        print(f"  기존본 백업 → {os.path.basename(bak)}")
    panel.to_csv(out, index=False, encoding="utf-8-sig")

    print(f"\n  ✅ 저장: {os.path.relpath(out, ROOT)}")
    print(f"     {len(panel):,}행 · {panel.ym.nunique()}개월 · {panel.code.nunique():,}종목")
    print(f"     기간 {panel.ym.min()} ~ **{panel.ym.max()}**")
    g = panel.groupby("ym").size()
    print(f"     월평균 {g.mean():.0f}종목 · 최근월 {g.iloc[-1]}종목")

    # ── 6. 기존본 대조
    if a.compare and os.path.exists(out + ".bak"):
        old = pd.read_csv(out + ".bak", dtype={"code": str})
        old["code"] = old["code"].str.zfill(6)
        common = sorted(set(old.ym) & set(panel.ym))
        if common:
            t = common[-1]
            o = old[old.ym == t].set_index("code")
            n = panel[panel.ym == t].set_index("code")
            k = sorted(set(o.index) & set(n.index))
            print(f"\n  [대조] {t} 공통 {len(k)}종목")
            for c in ("div", "bp", "ep", "roe"):
                if c in o and c in n:
                    d = (n.loc[k, c] - o.loc[k, c]).abs()
                    print(f"    {c:<4} 평균절대차 {d.mean():.6f} · 최대 {d.max():.6f}"
                          f"  {'✅' if d.mean() < 1e-4 else '⚠️ 정의 차이 확인'}")

    print("\n  다음: py 실전준비\\forward_signal.py")
    print("  ⚠️ 정보·검증용 · 투자자문 아님")


if __name__ == "__main__":
    main()
