#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""슬리브_배분_백테.py — 3-슬리브 리스크예산 배분 (모멘텀월간 + 가치장기 + 저변동방어)

호라이즌 검정 결론을 실전 배분으로: 서로 다른 호라이즌·드라이버의 슬리브를 섞으면
분산효과(Sharpe↑·MDD↓)가 나는가? 모멘텀↔가치는 국면이 엇갈려 상관이 낮다는 게 핵심 기대.

슬리브(전부 유동 top200·상폐포함·다올 비용후·EW·롱온리, 룩어헤드 없음):
  ① 모멘텀-리더십(월간)  : pool100·12-1 상위30 + MA200 50%현금 방어   [단기 회전 엔진]
  ② 가치-코어(연간)      : 저PBR 상위30, 12개월 보유(내구성高)         [중장기 밸러스트]
  ③ 저변동-방어(분기)    : 저변동 상위30, 3개월 보유                   [방어 안정기]

배분: 등가중 · 역변동성(rolling) · 코어새틀라이트(50/35/15).
사용: py 슬리브_배분_백테.py [--slippage 0.0005]
⚠️ 상폐포함·검증용. 실현손익 아님. 투자자문 아님·책임 본인.
"""
# §8-3(2026-07-27): tax 0.002→0.0015(실제 증권거래세) · slip 0.0005→0.002045(CS 실측 편도) → 왕복 0.300%→0.559%


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

import os, sys, argparse, json
import numpy as np, pandas as pd
BASE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def _find(fn):
    for d in (BASE, os.path.dirname(BASE), os.getcwd()):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    return None

def load_panel():
    frames = []
    for fn in ("_월봉종가캐시_KOSPI.csv", "_월봉종가캐시_KOSDAQ.csv"):
        p = _find(fn)
        if p:
            d = pd.read_csv(p, dtype={"code": str}); d["code"] = d["code"].str.zfill(6); frames.append(d)
    allc = pd.concat(frames, ignore_index=True)
    px = allc.pivot_table(index="ym", columns="code", values="close", aggfunc="last").sort_index()
    return px, px.pct_change().mask(lambda x: x.abs() > 1.0)

def load_mcap():
    p = _find("종목시총_30년.csv"); d = pd.read_csv(p, dtype={"code": str}); d["code"] = d["code"].str.zfill(6)
    d["ym"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m")
    return d.pivot_table(index="ym", columns="code", values="mcap", aggfunc="last")

def load_fin(field):
    frames = []
    for fn in ("종목재무_KRX_KOSPI.csv", "종목재무_KRX_KOSDAQ.csv"):
        p = _find(fn)
        if p:
            d = pd.read_csv(p, dtype={"code": str}); d["code"] = d["code"].str.zfill(6)
            d["ym"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m"); frames.append(d[["ym", "code", field]])
    return pd.concat(frames, ignore_index=True).pivot_table(index="ym", columns="code", values=field, aggfunc="last")

def load_reg():
    p = _find("kospi_index_daily.csv")
    d = pd.read_csv(p, parse_dates=["Date"]).set_index("Date").sort_index()
    close = d["Close"]; above = (close >= close.rolling(200).mean())
    reg = pd.DataFrame({"above": above.resample("ME").last()})
    reg.index = reg.index.strftime("%Y-%m"); reg["sig"] = reg["above"].shift(1)
    kret = close.resample("ME").last().pct_change(); kret.index = kret.index.strftime("%Y-%m")
    return reg["sig"], kret

def stats(x, ann=12):
    x = pd.Series(x).dropna()
    if len(x) < 12: return None
    c = (1+x).cumprod()
    return dict(CAGR=(1+x).prod()**(ann/len(x))-1, Sharpe=x.mean()/x.std()*np.sqrt(ann) if x.std()>0 else np.nan,
                MDD=(c/c.cummax()-1).min(), n=len(x))

def sleeve(kind, px, rets, mcap, pbr, reg, H=1, topN=30, univN=200, defense=None, tax=0.0015, slip=0.002045):
    months = [m for m in rets.index if m in mcap.index]
    held=[]; prev_s=0.0; out=[]; kept=[]; last_sel=None; step=0
    for t in months:
        i = list(rets.index).index(t); cur = rets.loc[t]
        do = (last_sel is None) or (step % H == 0)
        if do:
            mc = mcap.loc[t].dropna().sort_values(ascending=False)
            if kind == "momentum":
                pool = list(mc.index[:max(100, 3*topN)])
                if i < 13: step+=1; continue
                w = rets.iloc[i-13:i-1]; sig = (1+w[[c for c in pool if c in w.columns]]).prod(min_count=11)-1
                sig = sig.dropna()
                if len(sig) < topN: step+=1; continue
                sel = list(sig.sort_values(ascending=False).index[:topN])
            elif kind == "value":
                univ = list(mc.index[:univN]); pm = rets.index[i-1]
                if pm not in pbr.index: step+=1; continue
                v = pbr.loc[pm]; v = v[v > 0]
                s = (-v)[[c for c in univ if c in v.index]].dropna()
                if len(s) < topN: step+=1; continue
                sel = list(s.sort_values(ascending=False).index[:topN])
            elif kind == "lowvol":
                univ = list(mc.index[:univN])
                if i < 13: step+=1; continue
                w = rets.iloc[i-13:i-1]; vol = w[[c for c in univ if c in w.columns]].std()
                s = (-vol).dropna()
                if len(s) < topN: step+=1; continue
                sel = list(s.sort_values(ascending=False).index[:topN])
            last_sel = sel
        step += 1
        if last_sel is None: continue
        names = [c for c in last_sel if pd.notna(cur.get(c))]
        if len(names) < topN//2: continue
        r = cur[names].mean()
        if defense == "50현금":
            on = reg.get(t); on = True if pd.isna(on) else bool(on); s_scalar = 1.0 if on else 0.5
        else:
            s_scalar = 1.0
        nn=set(names); f=1-len(nn&set(held))/len(nn) if held else 1.0
        turn = abs(s_scalar-prev_s)+s_scalar*f
        out.append(s_scalar*r - turn*(tax+2*slip)); kept.append(t); held=names; prev_s=s_scalar
    return pd.Series(out, index=kept)

def run(slippage=0.002045):
    px, rets = load_panel(); mcap = load_mcap(); pbr = load_fin("PBR"); reg, kret = load_reg()
    S1 = sleeve("momentum", px, rets, mcap, pbr, reg, H=1, defense="50현금", slip=slippage)
    S2 = sleeve("value",    px, rets, mcap, pbr, reg, H=12, slip=slippage)
    S3 = sleeve("lowvol",   px, rets, mcap, pbr, reg, H=3,  slip=slippage)
    df = pd.concat({"모멘텀월간": S1, "가치연간": S2, "저변동분기": S3}, axis=1).dropna()
    kb = kret.reindex(df.index)
    print("=" * 88)
    print(f"3-슬리브 배분 백테 (다올 비용후·상폐포함, {df.index[0]}~{df.index[-1]} {len(df)}개월, 슬리피지 {slippage*100:.2f}%)")
    print("=" * 88)
    print(f"  {'구성':<22}{'순 CAGR':>10}{'Sharpe':>9}{'MDD':>9}")
    comp = {}
    for c in df.columns:
        st = stats(df[c]); comp[c] = st
        print(f"  {c:<22}{st['CAGR']*100:>9.1f}%{st['Sharpe']:>9.2f}{st['MDD']*100:>8.1f}%")
    ks = stats(kb)
    print(f"  {'KOSPI(벤치)':<22}{ks['CAGR']*100:>9.1f}%{ks['Sharpe']:>9.2f}{ks['MDD']*100:>8.1f}%")
    # 상관
    corr = df.corr()
    print("\n  ── 슬리브 상관 (낮을수록 분산효과 큼) ──")
    print(f"     모멘텀↔가치 {corr.loc['모멘텀월간','가치연간']:+.2f} · 모멘텀↔저변동 {corr.loc['모멘텀월간','저변동분기']:+.2f} · 가치↔저변동 {corr.loc['가치연간','저변동분기']:+.2f}")
    # 배분
    print("\n  ── 배분별 블렌드 ──")
    print(f"  {'배분':<26}{'순 CAGR':>10}{'Sharpe':>9}{'MDD':>9}")
    blends = {}
    ew = df.mean(axis=1); blends["등가중(1/3·1/3·1/3)"] = ew
    # 역변동성(36m rolling, shift로 룩어헤드 방지)
    vol = df.rolling(36, min_periods=12).std().shift(1); iv = (1/vol); w = iv.div(iv.sum(axis=1), axis=0)
    ivp = (df * w).sum(axis=1); ivp = ivp[w.notna().all(axis=1)]; blends["역변동성(36m)"] = ivp
    cs = df["모멘텀월간"]*0.50 + df["가치연간"]*0.35 + df["저변동분기"]*0.15; blends["코어새틀라이트(50/35/15)"] = cs
    best = None
    for name, ser in blends.items():
        st = stats(ser.dropna()); blends_stat = st
        mark = ""
        print(f"  {name:<26}{st['CAGR']*100:>9.1f}%{st['Sharpe']:>9.2f}{st['MDD']*100:>8.1f}%")
    # 판정
    best_sleeve_sh = max(comp[c]['Sharpe'] for c in df.columns)
    ew_sh = stats(ew)['Sharpe']; cs_sh = stats(cs)['Sharpe']
    print("\n  ── 판정 ──")
    print(f"  · 최고 단일슬리브 Sharpe {best_sleeve_sh:.2f} → 블렌드 등가중 {ew_sh:.2f} · 코어새틀라이트 {cs_sh:.2f}")
    if ew_sh >= best_sleeve_sh or cs_sh >= best_sleeve_sh:
        print("  · ✅ 분산효과 확인: 블렌드 Sharpe ≥ 최고 단일슬리브 (낮은 상관 덕). 서로 다른 호라이즌 결합이 위험조정을 개선.")
    else:
        print("  · 🟡 블렌드 Sharpe가 최고 단일슬리브보다 낮음 — 개별 최적화보다 MDD/안정성·심리적 지속가능성 관점에서 평가.")
    print("  · 실전: 배분은 리스크예산(트레이드당 1%·동시 5~7종)으로 실행. 국면따라 5~10월 위성 축소(통합전략 계승).")
    print("  ⚠️ EW·단순신호 근사. 실현손익 아님. 투자자문 아님·책임 본인.")
    res = dict(window=f"{df.index[0]}~{df.index[-1]}", n=len(df),
               sleeves={c: dict(cagr=round(comp[c]['CAGR']*100,1), sharpe=round(comp[c]['Sharpe'],2), mdd=round(comp[c]['MDD']*100,1)) for c in df.columns},
               kospi=dict(cagr=round(ks['CAGR']*100,1), sharpe=round(ks['Sharpe'],2), mdd=round(ks['MDD']*100,1)),
               corr=dict(mom_val=round(float(corr.loc['모멘텀월간','가치연간']),2), mom_lv=round(float(corr.loc['모멘텀월간','저변동분기']),2), val_lv=round(float(corr.loc['가치연간','저변동분기']),2)),
               blends={n: dict(cagr=round(stats(s.dropna())['CAGR']*100,1), sharpe=round(stats(s.dropna())['Sharpe'],2), mdd=round(stats(s.dropna())['MDD']*100,1)) for n,s in blends.items()})
    json.dump(res, open(os.path.join(BASE,"슬리브_배분_백테_결과.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=2)
    print("  저장: 슬리브_배분_백테_결과.json")
    return res

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--slippage", type=float, default=0.0005); a = ap.parse_args()
    run(a.slippage)

if __name__ == "__main__":
    main()
