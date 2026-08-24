#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""백테_딥밸류_하락장.py — 진우 논지 검증: "하락장에서 딥밸류 → 강한 반등"

가설: 하락장(KOSPI<MA200)에서 실제가치 대비 크게 싸진(저PBR) 종목이 강하게 반등한다.
     단, 밸류트랩(역배열=계속 하락)은 제외해야 한다.
설계: 월말(2002~2026 PIT PBR)마다 유효종목을 코호트로 나눠 6/12개월 선행수익 비교.
  · 딥밸류 = 그 달 PBR 하위 20%(싸다), PBR>0
  · 반등군 = 딥밸류 ∩ 과매도(이격도<0.85) ∩ 턴(1M수익>0)   ← 진우 '반등관찰'
  · 트랩군 = 딥밸류 ∩ 역배열(MA1<MA3<MA10, 계속하락)        ← 진우 '하락회피'
  · 시장   = 유효종목 전체(벤치마크)
  · regime = KOSPI 월말 vs 10M선(≈일봉MA200). 하락장 vs 강세장 분리.
MA근사: 일봉 MA20≈1M · MA60≈3M · MA200≈10M (월말 리샘플).
⚠️ 생존편향: 월봉패널=현재상장만 → 선행수익 상향편의. 특히 트랩군(상폐 패자 제외)이 실제보다 좋게 보임
   → 반등군 vs 트랩군 격차는 '하한'(보수적). 신호효능 연구(체결비용·유동성 미반영). 투자자문 아님·결정 본인.
사용: py 백테_딥밸류_하락장.py [--dv 0.2] [--ext 0.85] [--self-test]
"""
import os, sys, argparse
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def load_price():
    d = pd.read_csv(os.path.join(HERE, "_m_all.csv"), header=None, names=["code","date","close"], dtype={"code":str})
    d["code"] = d["code"].str.zfill(6)
    d["m"] = pd.to_datetime(d["date"], errors="coerce").dt.to_period("M")
    d["close"] = pd.to_numeric(d["close"], errors="coerce")
    d = d.dropna(subset=["m","close"])
    return d.pivot_table(index="m", columns="code", values="close", aggfunc="last").sort_index()

def load_pbr():
    fr = []
    for mk in ("KOSPI","KOSDAQ"):
        p = os.path.join(HERE, f"종목재무_KRX_{mk}.csv")
        if os.path.exists(p):
            x = pd.read_csv(p, dtype={"code":str}, encoding="utf-8-sig")
            x.columns = [c.lstrip("﻿") for c in x.columns]
            x = x[["date","code","PBR"]].copy(); fr.append(x)
    d = pd.concat(fr, ignore_index=True)
    d["code"] = d["code"].str.zfill(6)
    d["m"] = pd.to_datetime(d["date"], errors="coerce").dt.to_period("M")
    d["PBR"] = pd.to_numeric(d["PBR"], errors="coerce")
    d = d.dropna(subset=["m"])
    return d.pivot_table(index="m", columns="code", values="PBR", aggfunc="last").sort_index()

def regime_series(idx):
    p = os.path.join(HERE, "kospi_index_daily.csv")
    k = pd.read_csv(p, encoding="utf-8-sig"); k.columns=[c.lstrip("﻿").lower() for c in k.columns]
    k["m"] = pd.to_datetime(k["date"], errors="coerce").dt.to_period("M")
    k["close"] = pd.to_numeric(k["close"], errors="coerce")
    km = k.dropna(subset=["m"]).groupby("m")["close"].last().sort_index()
    ma = km.rolling(10).mean()
    bull = (km > ma)  # True=강세, False=하락장
    return bull.reindex(idx).ffill()

def summarize(fwd, mask):
    v = fwd.where(mask).values.ravel(); v = v[~np.isnan(v)]
    if len(v)==0: return dict(n=0, mean=np.nan, median=np.nan, hit=np.nan, big=np.nan)
    return dict(n=int(len(v)), mean=round(float(np.mean(v)),4), median=round(float(np.median(v)),4),
                hit=round(float((v>0).mean()),3), big=round(float((v>0.30).mean()),3))

def run(dv=0.2, ext=0.85):
    px = load_price(); pbr = load_pbr()
    idx = px.index
    pbr = pbr.reindex(idx).reindex(columns=px.columns)
    # 월봉 MA근사
    ma3 = px.rolling(3).mean(); ma10 = px.rolling(10).mean()
    disp = px/ma10                       # 이격도
    ret1 = px.pct_change()               # 1개월 수익(턴)
    order_up = (px>ma3) & (ma3>ma10)     # 정배열
    order_dn = (px<ma3) & (ma3<ma10)     # 역배열
    valid = px.notna() & (px>=500) & ma10.notna() & (pbr>0) & pbr.notna()
    # 딥밸류: 그 달 PBR 하위 dv분위
    pr = pbr.where(valid).rank(axis=1, pct=True)
    deep = valid & (pr <= dv)
    reb = deep & (disp<ext) & (ret1>0)   # 반등군
    trap = deep & order_dn               # 트랩군
    # 선행수익
    fwd6 = px.shift(-6)/px - 1
    fwd12 = px.shift(-12)/px - 1
    bull = regime_series(idx)
    bearmask = pd.DataFrame(np.repeat((~bull).values[:,None], px.shape[1], axis=1), index=idx, columns=px.columns)
    bullmask = pd.DataFrame(np.repeat(bull.values[:,None], px.shape[1], axis=1), index=idx, columns=px.columns)
    out = {"기간": f"{idx.min()}~{idx.max()}", "월수": len(idx), "파라미터": f"딥밸류하위{int(dv*100)}%·이격<{ext}"}
    cohorts = {"시장(전체)": valid, "딥밸류(전체)": deep, "반등군(딥밸류+과매도+턴)": reb, "트랩군(딥밸류+역배열)": trap}
    for horizon, fwd in (("6M", fwd6), ("12M", fwd12)):
        for regname, rmask in (("하락장", bearmask), ("강세장", bullmask)):
            for cname, cmask in cohorts.items():
                out[f"[{horizon}·{regname}] {cname}"] = summarize(fwd, cmask & rmask)
    return out

def _fmt(out):
    print(f"\n{'='*92}\n딥밸류 하락장 반등 검증 · {out['기간']} ({out['월수']}개월) · {out['파라미터']}\n{'='*92}")
    print("코호트별 선행수익: n=표본 · mean/median=평균/중앙 · hit=플러스비율 · big=+30%초과비율\n")
    for horizon in ("6M","12M"):
        for reg in ("하락장","강세장"):
            print(f"── {horizon} 선행 · {reg} ──")
            print(f"  {'코호트':<26}{'n':>7}{'평균':>9}{'중앙':>9}{'승률':>7}{'+30%':>7}")
            for c in ("시장(전체)","딥밸류(전체)","반등군(딥밸류+과매도+턴)","트랩군(딥밸류+역배열)"):
                k=f"[{horizon}·{reg}] {c}"; s=out[k]
                mean = f"{s['mean']*100:+.1f}%" if s['mean']==s['mean'] else "-"
                med = f"{s['median']*100:+.1f}%" if s['median']==s['median'] else "-"
                hit = f"{s['hit']*100:.0f}%" if s['hit']==s['hit'] else "-"
                big = f"{s['big']*100:.0f}%" if s['big']==s['big'] else "-"
                print(f"  {c:<26}{s['n']:>7,}{mean:>9}{med:>9}{hit:>7}{big:>7}")
            print()

def _self_test():
    ok=tot=0
    def chk(n,c):
        nonlocal ok,tot; tot+=1; ok+=1 if c else 0; print(f"  [{'OK' if c else 'FAIL'}] {n}")
    s=summarize(pd.DataFrame({"a":[0.1,0.5,-0.2]}), pd.DataFrame({"a":[True,True,True]}))
    chk("summarize n=3", s["n"]==3)
    chk("summarize hit=2/3", abs(s["hit"]-0.667)<0.01)
    chk("summarize big(+30%)=1/3", abs(s["big"]-0.333)<0.01)
    print(f"\n셀프테스트: {ok}/{tot}"); return ok==tot

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--dv",type=float,default=0.2); ap.add_argument("--ext",type=float,default=0.85)
    ap.add_argument("--self-test",action="store_true"); a=ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    _fmt(run(a.dv, a.ext)); return 0

if __name__=="__main__":
    sys.exit(main())
