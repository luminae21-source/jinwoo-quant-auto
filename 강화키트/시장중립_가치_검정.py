#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""시장중립_가치_검정.py — 롱숏 가치가 모멘텀과 '진짜 분산'인가

앞선 3-슬리브 배분에서 롱온리끼리는 상관 0.7↑라 분산효과 제한이었다.
가설: 시장중립 가치(롱 저PBR / 숏 고PBR)는 모멘텀과 상관이 낮거나 음(-) → 진짜 분산.
검정: L/S 가치 팩터의 수익·Sharpe + 모멘텀-리더십 슬리브와의 상관 + 오버레이 효과.

  · LS_PBR : 매월 top200 중 저PBR 5분위 롱 − 고PBR 5분위 숏 (EW, 다올 비용후)
  · LS_PER : 저PER 롱 − 고PER 숏
  · 모멘텀 : 동적 TOP30 리더십(월간)  ← 상관 비교 기준
  · 오버레이: 모멘텀 + w·LS_PBR (시장중립 오버레이가 Sharpe·MDD 개선하는가)

⚠️ 숏 비용·차입 가정 단순(왕복비용만). 검증용·실현손익 아님·투자자문 아님·책임 본인.
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
            d["ym"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m"); frames.append(d[["ym","code",field]])
    return pd.concat(frames, ignore_index=True).pivot_table(index="ym", columns="code", values=field, aggfunc="last")

def stats(x, ann=12):
    x = pd.Series(x).dropna()
    if len(x) < 12: return None
    c = (1+x).cumprod()
    return dict(CAGR=(1+x).prod()**(ann/len(x))-1, Sharpe=x.mean()/x.std()*np.sqrt(ann) if x.std()>0 else np.nan,
                MDD=(c/c.cummax()-1).min(), n=len(x), mean_ann=x.mean()*12)

def ls_value(px, rets, mcap, fin, univN=200, q=5, tax=0.0015, slip=0.002045):
    months = [m for m in rets.index if m in mcap.index]
    prevL=set(); prevS=set(); out=[]; kept=[]
    for t in months:
        i = list(rets.index).index(t); pm = rets.index[i-1]
        if pm not in fin.index: continue
        mc = mcap.loc[t].dropna().sort_values(ascending=False); univ = list(mc.index[:univN])
        v = fin.loc[pm]; v = v[v>0]
        vv = v[[c for c in univ if c in v.index]].dropna()
        cur = rets.loc[t]; vv = vv[[c for c in vv.index if pd.notna(cur.get(c))]]
        if len(vv) < q*4: continue
        ranked = vv.sort_values()               # 저PBR/PER = 싼 쪽(앞)
        k = len(ranked)//q
        longs = list(ranked.index[:k]); shorts = list(ranked.index[-k:])
        rl = cur[longs].mean(); rs = cur[shorts].mean()
        fL = 1-len(set(longs)&prevL)/len(longs) if prevL else 1.0
        fS = 1-len(set(shorts)&prevS)/len(shorts) if prevS else 1.0
        prevL, prevS = set(longs), set(shorts)
        out.append((rl-rs) - (fL+fS)*(tax+2*slip)); kept.append(t)
    return pd.Series(out, index=kept)

def momentum_sleeve(px, rets, mcap, topN=30, tax=0.0015, slip=0.002045):
    months = [m for m in rets.index if m in mcap.index]
    held=[]; out=[]; kept=[]
    for t in months:
        i = list(rets.index).index(t)
        if i < 13: continue
        mc = mcap.loc[t].dropna().sort_values(ascending=False); pool=list(mc.index[:max(100,3*topN)])
        w = rets.iloc[i-13:i-1]; mom=(1+w[[c for c in pool if c in w.columns]]).prod(min_count=11)-1
        mom=mom.dropna()
        if len(mom)<topN: continue
        sel=list(mom.sort_values(ascending=False).index[:topN])
        cur=rets.loc[t]; names=[c for c in sel if pd.notna(cur.get(c))]
        if len(names)<topN//2: continue
        nn=set(names); f=1-len(nn&set(held))/len(nn) if held else 1.0
        out.append(cur[names].mean()-f*(tax+2*slip)); kept.append(t); held=names
    return pd.Series(out, index=kept)

def run(slippage=0.002045):
    px, rets = load_panel(); mcap = load_mcap()
    pbr = load_fin("PBR"); per = load_fin("PER")
    LSp = ls_value(px, rets, mcap, pbr, slip=slippage)
    LSe = ls_value(px, rets, mcap, per, slip=slippage)
    MOM = momentum_sleeve(px, rets, mcap, slip=slippage)
    df = pd.concat({"LS_PBR":LSp,"LS_PER":LSe,"모멘텀":MOM}, axis=1).dropna()
    print("="*84)
    print(f"시장중립 가치 vs 모멘텀 — 진짜 분산 검정 ({df.index[0]}~{df.index[-1]} {len(df)}개월, 슬립 {slippage*100:.2f}%)")
    print("="*84)
    print(f"  {'전략':<16}{'연평균':>9}{'Sharpe':>9}{'MDD':>9}")
    for c in ["LS_PBR","LS_PER","모멘텀"]:
        st=stats(df[c]); print(f"  {c:<16}{st['mean_ann']*100:>8.1f}%{st['Sharpe']:>9.2f}{st['MDD']*100:>8.1f}%")
    corr = df.corr()
    print("\n  ── 상관 (핵심: 모멘텀과 낮/음이면 진짜 분산) ──")
    print(f"     모멘텀 ↔ LS_PBR {corr.loc['모멘텀','LS_PBR']:+.2f} · 모멘텀 ↔ LS_PER {corr.loc['모멘텀','LS_PER']:+.2f} · LS_PBR ↔ LS_PER {corr.loc['LS_PBR','LS_PER']:+.2f}")
    # 오버레이: 모멘텀 + w·LS_PBR
    print("\n  ── 모멘텀 + 시장중립가치 오버레이 ──")
    print(f"  {'구성':<26}{'연평균':>9}{'Sharpe':>9}{'MDD':>9}")
    base=stats(df['모멘텀']); print(f"  {'모멘텀 단독':<26}{base['mean_ann']*100:>8.1f}%{base['Sharpe']:>9.2f}{base['MDD']*100:>8.1f}%")
    best=None
    for w in (0.25,0.5,1.0):
        ov = df['모멘텀'] + w*df['LS_PBR']; st=stats(ov)
        print(f"  {'모멘텀 + '+str(w)+'×LS_PBR':<26}{st['mean_ann']*100:>8.1f}%{st['Sharpe']:>9.2f}{st['MDD']*100:>8.1f}%")
        if best is None or st['Sharpe']>best[1]: best=(w,st['Sharpe'],st)
    print("\n  ── 판정 ──")
    cmv=corr.loc['모멘텀','LS_PBR']
    if cmv < 0.2:
        print(f"  · ✅ 모멘텀↔LS_PBR 상관 {cmv:+.2f} (롱온리 0.7 대비 급감) = 구조적 분산. 오버레이 최적 w={best[0]} Sharpe {base['Sharpe']:.2f}→{best[1]:.2f}.")
    else:
        print(f"  · 🟡 상관 {cmv:+.2f} — 기대만큼 낮진 않음. 그래도 롱온리보다 분산 우수. 오버레이 Sharpe {base['Sharpe']:.2f}→{best[1]:.2f}(w={best[0]}).")
    print("  · 주의: 숏 실행(차입·역차입비용·공매도 제약)은 개인계좌서 어렵다 — 실전은 '가치 롱 비중'으로 근사하거나 인버스/헤지로.")
    print("  ⚠️ 숏비용 단순가정. 실현손익 아님. 투자자문 아님·책임 본인.")
    res=dict(window=f"{df.index[0]}~{df.index[-1]}", n=len(df),
             ls_pbr=dict(mean_ann=round(stats(df['LS_PBR'])['mean_ann']*100,1),sharpe=round(stats(df['LS_PBR'])['Sharpe'],2),mdd=round(stats(df['LS_PBR'])['MDD']*100,1)),
             ls_per=dict(mean_ann=round(stats(df['LS_PER'])['mean_ann']*100,1),sharpe=round(stats(df['LS_PER'])['Sharpe'],2),mdd=round(stats(df['LS_PER'])['MDD']*100,1)),
             corr_mom_lspbr=round(float(cmv),2), corr_mom_lsper=round(float(corr.loc['모멘텀','LS_PER']),2),
             overlay_best_w=best[0], mom_sharpe=round(base['Sharpe'],2), overlay_sharpe=round(best[1],2), overlay_mdd=round(best[2]['MDD']*100,1))
    json.dump(res, open(os.path.join(BASE,"시장중립_가치_검정_결과.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=2)
    print("  저장: 시장중립_가치_검정_결과.json")
    return res

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--slippage",type=float,default=0.0005); a=ap.parse_args()
    run(a.slippage)

if __name__=="__main__":
    main()
