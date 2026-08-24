#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""검증_모멘텀정의_레짐_P0P1.py — P0-2(모멘텀 정의 강건성) + P1(레짐 의존성)

P0-2: 12-1 모멘텀을 raw(가격비) vs clip(클립월수익 복리) 두 정의로 primary를 재산출,
      결론(50%현금 방어가 TOP30고정 대비 Sharpe 우위) 유지되는가.
P1 : 2025~26 반도체 파라볼릭을 제외한 구간에서도 우위·낙폭제어가 유지되는가.
     (KOSPI 2500→8500→6800, 2026-07 -23% 서킷브레이커 = 실제 대형 강세후 급락 구간 확인)

⚠️ 검증용·실현손익 아님·투자자문 아님·책임 본인.
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

def load_reg():
    p=_find("kospi_index_daily.csv"); d=pd.read_csv(p,parse_dates=["Date"]).set_index("Date").sort_index()
    close=d["Close"]; above=(close>=close.rolling(200).mean())
    reg=pd.DataFrame({"above":above.resample("ME").last()}); reg.index=reg.index.strftime("%Y-%m")
    return reg["above"].shift(1)

def stats(x,ann=12):
    x=pd.Series(x).dropna()
    if len(x)<12: return None
    c=(1+x).cumprod()
    return dict(CAGR=(1+x).prod()**(ann/len(x))-1, Sharpe=x.mean()/x.std()*np.sqrt(ann) if x.std()>0 else np.nan,
                MDD=(c/c.cummax()-1).min(), n=len(x))

def momentum(px, rets, i, pool, kind):
    if kind=="raw":
        w=px.iloc[i-13:i-1]; m=(w.iloc[-1]/w.iloc[0]-1)
        return m[[c for c in pool if c in m.index]].dropna()
    else:
        w=rets.iloc[i-13:i-1]; m=(1+w[[c for c in pool if c in w.columns]]).prod(min_count=11)-1
        return m.dropna()

def sleeve(px, rets, mcap, reg, momkind, defense, tax=0.0015, slip=0.002045):
    months=[m for m in rets.index if m in mcap.index]
    held=[]; prev_s=0.0; out=[]; kept=[]
    for t in months:
        i=list(rets.index).index(t); cur=rets.loc[t]
        mc=mcap.loc[t].dropna().sort_values(ascending=False); ranked=list(mc.index)
        if defense=="고정": sel=ranked[:30]
        else:
            pool=ranked[:100]
            if i<13: sel=pool[:30]
            else:
                m=momentum(px,rets,i,pool,momkind); sel=list(m.sort_values(ascending=False).index[:30]) if len(m)>=30 else pool[:30]
        names=[c for c in sel if pd.notna(cur.get(c))]
        if len(names)<10: continue
        if defense=="고정": s=1.0
        else:
            on=reg.get(t); on=True if pd.isna(on) else bool(on)
            s=1.0 if on else (0.5 if defense=="50" else 0.0)
        nn=set(names); f=1-len(nn&set(held))/len(nn) if held else 1.0
        turn=abs(s-prev_s)+s*f
        out.append(s*cur[names].mean()-turn*(tax+2*slip)); kept.append(t); held=names; prev_s=s
    return pd.Series(out,index=kept)

def sub(s, lo=None, hi=None):
    idx=[m for m in s.index if (lo is None or m>=lo) and (hi is None or m<=hi)]
    return s.reindex(idx)

def run():
    px,rets=load_panel(); mcap=load_mcap(); reg=load_reg()
    print("="*88)
    print("P0-2 모멘텀 정의 강건성 — raw(가격비) vs clip(클립복리) · primary=50%현금 방어")
    print("="*88)
    series={}
    for momkind in ("raw","clip"):
        series[(momkind,"50")]=sleeve(px,rets,mcap,reg,momkind,"50")
    fixed=sleeve(px,rets,mcap,reg,"clip","고정")  # 고정 베이스라인(정의 무관)
    print(f"  {'정의':<8}{'primary CAGR':>14}{'Sharpe':>9}{'MDD':>9}{'고정Sharpe':>11}{'게이트(>고정)':>13}")
    for momkind in ("raw","clip"):
        st=stats(series[(momkind,"50")]); sf=stats(fixed.reindex(series[(momkind,'50')].index))
        g="PASS" if st['Sharpe']>sf['Sharpe'] else "FAIL"
        print(f"  {momkind:<8}{st['CAGR']*100:>13.1f}%{st['Sharpe']:>9.2f}{st['MDD']*100:>8.1f}%{sf['Sharpe']:>11.2f}{g:>13}")
    print("  → 두 정의 모두 50%현금 primary가 고정 대비 Sharpe 우위 유지하면 결론 강건.")

    print("\n"+"="*88)
    print("P1 레짐 의존성 — 2025~26 파라볼릭 제외 구간에서도 우위·낙폭제어 유지되는가")
    print("="*88)
    prim=series[("clip","50")]; nod=sleeve(px,rets,mcap,reg,"clip","무")  # 무방어=완전투자? 아래서 재계산
    nodef=sleeve(px,rets,mcap,reg,"clip","무방어") if False else None
    # 무방어(방어X) 시리즈
    def nodefense():
        months=[m for m in rets.index if m in mcap.index]; held=[]; out=[]; kept=[]
        for t in months:
            i=list(rets.index).index(t); cur=rets.loc[t]
            mc=mcap.loc[t].dropna().sort_values(ascending=False); pool=list(mc.index[:100])
            if i<13: sel=pool[:30]
            else:
                m=momentum(px,rets,i,pool,"clip"); sel=list(m.sort_values(ascending=False).index[:30]) if len(m)>=30 else pool[:30]
            names=[c for c in sel if pd.notna(cur.get(c))]
            if len(names)<10: continue
            nn=set(names); f=1-len(nn&set(held))/len(nn) if held else 1.0
            out.append(cur[names].mean()-f*(0.002+2*0.0005)); kept.append(t); held=names
        return pd.Series(out,index=kept)
    nod=nodefense()
    windows=[("전체(1996~2026)",None,None),("2024이전(~2023-12)",None,"2023-12"),
             ("2025이전(~2024-12)",None,"2024-12"),("최근만(2024-01~)","2024-01",None)]
    print(f"  {'구간':<22}{'primary CAGR':>13}{'Sh':>7}{'MDD':>8}{'무방어 CAGR':>12}{'Sh':>7}{'MDD':>8}{'고정 Sh':>8}")
    res={}
    for label,lo,hi in windows:
        p=sub(prim,lo,hi); n=sub(nod,lo,hi); fx=sub(fixed,lo,hi)
        sp=stats(p); sn=stats(n); sfx=stats(fx)
        if not sp: continue
        res[label]=dict(prim_cagr=round(sp['CAGR']*100,1),prim_sh=round(sp['Sharpe'],2),prim_mdd=round(sp['MDD']*100,1),
                        nod_cagr=round(sn['CAGR']*100,1),nod_sh=round(sn['Sharpe'],2),nod_mdd=round(sn['MDD']*100,1),
                        fixed_sh=round(sfx['Sharpe'],2) if sfx else None)
        print(f"  {label:<22}{sp['CAGR']*100:>12.1f}%{sp['Sharpe']:>7.2f}{sp['MDD']*100:>7.1f}%{sn['CAGR']*100:>11.1f}%{sn['Sharpe']:>7.2f}{sn['MDD']*100:>7.1f}%{(sfx['Sharpe'] if sfx else float('nan')):>8.2f}")
    print("\n  ── 판정 ──")
    a=res.get("2024이전(~2023-12)"); b=res.get("전체(1996~2026)")
    if a and b:
        print(f"  · 파라볼릭 제외(~2023): primary Sharpe {a['prim_sh']} vs 고정 {a['fixed_sh']} → {'우위 유지' if a['prim_sh']>a['fixed_sh'] else '우위 소멸'}")
        print(f"  · 방어 낙폭제어: 제외구간 primary MDD {a['prim_mdd']}% vs 무방어 {a['nod_mdd']}% (개선 {abs(a['nod_mdd'])-abs(a['prim_mdd']):.0f}%p)")
        print(f"  · 최근(2024~) 기여: 전체 CAGR {b['prim_cagr']}% 중 상당부분이 최근 강세 → 레짐 의존 존재. 단, 방어 낙폭제어는 구간 무관 유지가 관건.")
    json.dump(dict(p0_2={f"{k[0]}·{k[1]}":dict(cagr=round(stats(v)['CAGR']*100,1),sharpe=round(stats(v)['Sharpe'],2),mdd=round(stats(v)['MDD']*100,1)) for k,v in series.items()},
                   p1=res), open(os.path.join(BASE,"검증_P0P1_결과.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
    print("\n  저장: 검증_P0P1_결과.json")
    print("  ⚠️ 실현손익 아님·투자자문 아님·책임 본인.")

if __name__=="__main__":
    run()
