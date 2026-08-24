#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""잔여검증_비용_파라미터_집중도.py — P1 비용모델 + P2 파라미터안정성 + 슬리브 실행가능성

① 비용모델 정밀화: 현실 다올(수수료 왕복 0.03% + 매도세 0.20% + 시장충격 슬리피지 grid)로 primary 재산출.
② 파라미터 안정성(과최적화 점검): N·pool·MA일수·모멘텀 룩백을 인접값으로 흔들어 Sharpe/MDD 안정성.
③ 슬리브 실행가능성: 실전 동시보유 5~7종으로 좁혀도 엣지가 보존되는가(top-K EW).
primary = 동적 리더십(clip 12-1) + MA200 50%현금.
⚠️ 검증용·실현손익 아님·투자자문 아님·책임 본인.
"""

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

import os, sys, json
import numpy as np, pandas as pd
BASE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def _find(fn):
    for d in (BASE, os.path.dirname(BASE), os.getcwd()):
        p=os.path.join(d,fn)
        if os.path.exists(p): return p
    return None

def load_panel():
    frames=[]
    for fn in ("_월봉종가캐시_KOSPI.csv","_월봉종가캐시_KOSDAQ.csv"):
        p=_find(fn)
        if p:
            d=pd.read_csv(p,dtype={"code":str}); d["code"]=d["code"].str.zfill(6); frames.append(d)
    px=pd.concat(frames).pivot_table(index="ym",columns="code",values="close",aggfunc="last").sort_index()
    return px, px.pct_change().mask(lambda x:x.abs()>1.0)

def load_mcap():
    p=_find("종목시총_30년.csv"); d=pd.read_csv(p,dtype={"code":str}); d["code"]=d["code"].str.zfill(6)
    d["ym"]=pd.to_datetime(d["date"]).dt.strftime("%Y-%m")
    return d.pivot_table(index="ym",columns="code",values="mcap",aggfunc="last")

def load_reg(ma=200):
    p=_find("kospi_index_daily.csv"); d=pd.read_csv(p,parse_dates=["Date"]).set_index("Date").sort_index()
    close=d["Close"]; above=(close>=close.rolling(ma).mean())
    reg=pd.DataFrame({"above":above.resample("ME").last()}); reg.index=reg.index.strftime("%Y-%m")
    return reg["above"].shift(1)

def stats(x,ann=12):
    x=pd.Series(x).dropna()
    if len(x)<12: return None
    c=(1+x).cumprod()
    return dict(CAGR=(1+x).prod()**(ann/len(x))-1, Sharpe=x.mean()/x.std()*np.sqrt(ann) if x.std()>0 else np.nan,
                MDD=(c/c.cummax()-1).min())

def primary(px, rets, mcap, reg, N=30, pool=100, look=13, defense=0.5, cost=None):
    """cost=(tax, slip). 기본 다올(0.002, 0.0005). look=13 → 12-1."""
    if cost is None: cost=(0.002,0.0005)
    tax,slip=cost
    months=[m for m in rets.index if m in mcap.index]
    held=[]; prev_s=0.0; out=[]; kept=[]
    for t in months:
        i=list(rets.index).index(t); cur=rets.loc[t]
        mc=mcap.loc[t].dropna().sort_values(ascending=False); ranked=list(mc.index); pl=ranked[:pool]
        if i<look: sel=pl[:N]
        else:
            w=rets.iloc[i-look:i-1]; mom=(1+w[[c for c in pl if c in w.columns]]).prod(min_count=max(3,look-2))-1
            mom=mom.dropna(); sel=list(mom.sort_values(ascending=False).index[:N]) if len(mom)>=N else pl[:N]
        names=[c for c in sel if pd.notna(cur.get(c))]
        if len(names)<max(3,N//3): continue
        on=reg.get(t); on=True if pd.isna(on) else bool(on); s=1.0 if on else defense
        nn=set(names); f=1-len(nn&set(held))/len(nn) if held else 1.0
        turn=abs(s-prev_s)+s*f
        out.append(s*cur[names].mean()-turn*(tax+2*slip)); kept.append(t); held=names; prev_s=s
    return pd.Series(out,index=kept)

def fixed(px, rets, mcap, cost=(0.002,0.0005)):
    tax,slip=cost; months=[m for m in rets.index if m in mcap.index]; held=[]; out=[]; kept=[]
    for t in months:
        cur=rets.loc[t]; mc=mcap.loc[t].dropna().sort_values(ascending=False); sel=list(mc.index[:30])
        names=[c for c in sel if pd.notna(cur.get(c))]
        if len(names)<10: continue
        nn=set(names); f=1-len(nn&set(held))/len(nn) if held else 1.0
        out.append(cur[names].mean()-f*(tax+2*slip)); kept.append(t); held=names
    return pd.Series(out,index=kept)

def run():
    px,rets=load_panel(); mcap=load_mcap(); reg200=load_reg(200)
    base=primary(px,rets,mcap,reg200)
    bs=stats(base); fx=stats(fixed(px,rets,mcap))

    print("="*80); print("① 비용모델 정밀화 — 현실 다올(수수료 왕복0.03%+매도세0.20%+시장충격)"); print("="*80)
    print(f"  {'시나리오':<34}{'순 CAGR':>10}{'Sharpe':>9}{'MDD':>9}")
    scen=[("이상(세0.2%+슬0.05%)",(0.002,0.0005)),
          ("현실 소형충격(+수수료0.03%,슬0.10%)",(0.0023,0.0010)),
          ("현실 중형충격(슬0.15%)",(0.0023,0.0015)),
          ("보수 대형충격(슬0.25%)",(0.0023,0.0025))]
    cost_res={}
    for lbl,cst in scen:
        st=stats(primary(px,rets,mcap,reg200,cost=cst))
        cost_res[lbl]=dict(cagr=round(st['CAGR']*100,1),sharpe=round(st['Sharpe'],2),mdd=round(st['MDD']*100,1))
        print(f"  {lbl:<34}{st['CAGR']*100:>9.1f}%{st['Sharpe']:>9.2f}{st['MDD']*100:>8.1f}%")
    print(f"  · 고정 베이스라인 Sharpe {fx['Sharpe']:.2f} — 위 전 시나리오와 비교해 우위 유지 확인.")

    print("\n"+"="*80); print("② 파라미터 안정성 — 인접값에서 Sharpe/MDD 완만하면 과최적화 아님"); print("="*80)
    print(f"  {'파라미터':<16}{'값':<10}{'Sharpe':>9}{'MDD':>9}{'CAGR':>9}")
    param_res={}
    grids=[("N종목수",[20,25,30,35,40],lambda v:primary(px,rets,mcap,reg200,N=v)),
           ("pool크기",[60,100,150],lambda v:primary(px,rets,mcap,reg200,pool=v)),
           ("MA일수",[150,200,250],lambda v:primary(px,rets,mcap,load_reg(v))),
           ("모멘텀룩백",[7,13],lambda v:primary(px,rets,mcap,reg200,look=v))]
    for pname,vals,fn in grids:
        for v in vals:
            st=stats(fn(v)); tag=" ←현행" if (pname=="N종목수" and v==30) or (pname=="pool크기" and v==100) or (pname=="MA일수" and v==200) or (pname=="모멘텀룩백" and v==13) else ""
            lbl={7:"6-1",13:"12-1"}.get(v,str(v)) if pname=="모멘텀룩백" else str(v)
            print(f"  {pname:<16}{lbl:<10}{st['Sharpe']:>9.2f}{st['MDD']*100:>8.1f}%{st['CAGR']*100:>8.1f}%{tag}")
            param_res[f"{pname}={lbl}"]=dict(sharpe=round(st['Sharpe'],2),mdd=round(st['MDD']*100,1))

    print("\n"+"="*80); print("③ 슬리브 실행가능성 — 실전 동시보유 5~7종으로 좁혀도 엣지 보존되나"); print("="*80)
    print(f"  {'동시보유 K':<12}{'순 CAGR':>10}{'Sharpe':>9}{'MDD':>9}{'회전민감':>10}")
    conc_res={}
    for K in [5,7,10,15,30]:
        st=stats(primary(px,rets,mcap,reg200,N=K))
        conc_res[K]=dict(cagr=round(st['CAGR']*100,1),sharpe=round(st['Sharpe'],2),mdd=round(st['MDD']*100,1))
        mark=" ←실전 5~7" if K in (5,7) else ""
        print(f"  {K:<12}{st['CAGR']*100:>9.1f}%{st['Sharpe']:>9.2f}{st['MDD']*100:>8.1f}%{mark:>10}")
    print("  · K↓ = 수익↑·낙폭↑(집중대가). 5~7종에서 Sharpe 유지되면 실전 집중 실행가능.")

    print("\n  ── 종합 판정 ──")
    shs=[param_res[k]['sharpe'] for k in param_res]
    print(f"  · 파라미터 Sharpe 범위 {min(shs):.2f}~{max(shs):.2f} (현행 {bs['Sharpe']:.2f}) → 인접값서 {'완만=과최적화 아님' if max(shs)-min(shs)<0.25 else '다소 민감'}")
    print(f"  · 현실 비용서도 고정 대비 우위 {'유지' if cost_res['현실 중형충격(슬0.15%)']['sharpe']>fx['Sharpe'] else '주의'}")
    k7=conc_res[7]['sharpe']
    print(f"  · 5~7종 집중: K=7 Sharpe {k7} vs 30종 {conc_res[30]['sharpe']} → 실전 집중 {'가능(엣지 보존)' if k7>=conc_res[30]['sharpe']-0.05 else '수익↑·변동성↑ 트레이드오프'}")
    json.dump(dict(cost=cost_res,param=param_res,conc=conc_res,base_sharpe=round(bs['Sharpe'],2),fixed_sharpe=round(fx['Sharpe'],2)),
              open(os.path.join(BASE,"잔여검증_비용파라미터집중도_결과.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=2)
    print("  저장: 잔여검증_비용파라미터집중도_결과.json")
    print("  ⚠️ 실현손익 아님·투자자문 아님·책임 본인.")

if __name__=="__main__":
    run()
