#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""손절폭_스윕.py — 신호별 최적 손절폭 (기대값·손익비를 −8~−20% 스윕) · numpy 최적화

청산 = {진입 대비 −X% 손절} or {MA3 추세이탈} or {최대 12개월} 중 먼저.
30년 상폐포함 월봉·top200 유동·다올 비용후. 월봉 근사(실제 일중 손절은 더 자주 발동).
⚠️ 과거통계·미래보장 아님. 투자자문 아님·책임 본인.
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
import numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
BASE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def _find(fn):
    for d in (BASE, os.path.dirname(BASE), os.getcwd()):
        p=os.path.join(d,fn)
        if os.path.exists(p): return p
    return None

def load():
    frames=[]
    for fn in ("_월봉종가캐시_KOSPI.csv","_월봉종가캐시_KOSDAQ.csv"):
        p=_find(fn)
        if p:
            d=pd.read_csv(p,dtype={"code":str}); d["code"]=d["code"].str.zfill(6); frames.append(d)
    px=pd.concat(frames).pivot_table(index="ym",columns="code",values="close",aggfunc="last").sort_index()
    rets=px.pct_change().mask(lambda x:x.abs()>1.0)
    m=pd.read_csv(_find("종목시총_30년.csv"),dtype={"code":str}); m["code"]=m["code"].str.zfill(6)
    m["ym"]=pd.to_datetime(m["date"]).dt.strftime("%Y-%m")
    mcap=m.pivot_table(index="ym",columns="code",values="mcap",aggfunc="last").reindex(index=px.index,columns=px.columns)
    return px,rets,mcap

def run():
    px,rets,mcap=load()
    ma3=px.rolling(3).mean(); ma6=px.rolling(6).mean(); ma10=px.rolling(10).mean()
    # 벡터화 신호(불리언 행렬)
    hi12=px.rolling(12).max(); hi24=px.rolling(24).max(); lo12=px.rolling(12).min()
    rng6=px.rolling(6).max()/px.rolling(6).min()-1; q33=rng6.rolling(24).quantile(0.33)
    breakout=(px>=hi12*0.97)
    reclaim=(px>=ma6)&(px.shift(1)<ma6.shift(1))
    early=(px>=ma3)&(px.shift(1)<ma3.shift(1))&(px<ma6)
    prep=((px>=ma10)&(rng6<=q33)) | ((px<=hi24*0.7)&(px<=lo12*1.15))
    # 카테고리 id (우선순위 돌파>추세복구>초기반등>상승준비)
    CID=np.zeros(px.shape,dtype=np.int8)
    CID=np.where(prep.values,4,CID); CID=np.where(early.values,3,CID)
    CID=np.where(reclaim.values,2,CID); CID=np.where(breakout.values,1,CID)
    PXv=px.values.astype(float); RETv=rets.values.astype(float); MA3v=ma3.values.astype(float); MCv=mcap.values.astype(float)
    nrow,ncol=PXv.shape
    # 이벤트 수집(top200 유동)
    cats={1:"🚀돌파",2:"🟢추세복구",3:"🟡초기반등",4:"🟣상승준비"}
    evs={k:[] for k in cats}
    for i in range(24,nrow-1):
        mc=MCv[i]; valid=np.where(~np.isnan(mc))[0]
        if len(valid)==0: continue
        order=valid[np.argsort(-mc[valid])][:200]
        cid=CID[i,order]
        for k in cats:
            for j in order[cid==k]: evs[k].append((i,int(j)))
    cost=0.006
    def managed(i,j,stop,use_trend=True):
        entry=PXv[i,j]
        if not (entry>0): return None
        cum=1.0
        for h in range(1,13):
            ih=i+h
            if ih>=nrow: break
            r=RETv[ih,j]
            if np.isnan(r): break
            cum*=(1+r)
            if stop is not None and (cum-1)<=-stop: return cum-1-cost
            if use_trend:
                m3=MA3v[ih,j]
                if not np.isnan(m3) and PXv[ih,j]<m3: return cum-1-cost
        return cum-1-cost
    def agg(rs):
        a=np.array([x for x in rs if x is not None])
        if len(a)==0: return None
        win=a[a>0]; los=a[a<=0]; aw=win.mean()*100 if len(win) else 0; al=los.mean()*100 if len(los) else 0
        return dict(n=len(a),wr=len(win)/len(a)*100,aw=aw,al=al,payoff=abs(aw/al) if al!=0 else np.nan,exp=a.mean()*100)
    stops=[0.08,0.10,0.12,0.15,0.20]
    print("="*96); print("손절폭 스윕 — 손절 단독(추세청산 X, 청산=−손절% or 12M) : 손절폭 효과 격리"); print("="*96)
    result={}
    for k in (1,2,3,4):
        cat=cats[k]; print(f"\n【 {cat} 】 (표본 {len(evs[k]):,})")
        print(f"  {'손절폭':<10}{'승률':>7}{'평균이익':>9}{'평균손실':>9}{'손익비':>8}{'기대값/트레이드':>14}")
        rows={}
        for stop in stops:
            s=agg([managed(i,j,stop,use_trend=False) for (i,j) in evs[k]])
            if not s: continue
            lbl=f"−{int(stop*100)}%"; rows[lbl]=s
            print(f"  {lbl:<10}{s['wr']:>6.0f}%{s['aw']:>+8.1f}%{s['al']:>+8.1f}%{s['payoff']:>8.2f}{s['exp']:>+13.1f}%")
        # 추세청산 참고
        st=agg([managed(i,j,None,use_trend=True) for (i,j) in evs[k]])
        if st:
            rows["추세청산"]=st
            print(f"  {'추세청산(참고)':<10}{st['wr']:>6.0f}%{st['aw']:>+8.1f}%{st['al']:>+8.1f}%{st['payoff']:>8.2f}{st['exp']:>+13.1f}%")
        best=max([(l,v) for l,v in rows.items() if l!='추세청산'],key=lambda kv:kv[1]['exp'])
        print(f"  → 최적 고정손절: {best[0]} (기대값 {best[1]['exp']:+.1f}%, 손익비 {best[1]['payoff']:.2f}) · 추세청산 기대값 {st['exp']:+.1f}%")
        result[cat]=dict(best=best[0],best_exp=round(best[1]['exp'],1),best_payoff=round(best[1]['payoff'],2),best_wr=round(best[1]['wr'],0),
                         trend_exp=round(st['exp'],1) if st else None,
                         rows={lbl:dict(wr=round(v['wr'],0),payoff=round(v['payoff'],2),exp=round(v['exp'],1),aw=round(v['aw'],1),al=round(v['al'],1)) for lbl,v in rows.items()})
    print("\n  ── 해석 ──")
    print("  · 타이트 손절(−8%)=휩쏘로 기대값↓, 넓은 손절(−20%/추세만)=손실 커도 큰 추세 포착. 신호별 스윗스팟.")
    print("  · 월봉 근사라 실제 일중 −X% 손절은 더 자주 발동 → 실전은 표보다 타이트하게 잡히는 경향.")
    print("  ⚠️ 과거통계·미래보장 아님. 투자자문 아님·책임 본인.")
    json.dump(result, open(os.path.join(BASE,"손절폭_스윕_결과.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2,default=str)
    print("  저장: 손절폭_스윕_결과.json")
    return result

if __name__=="__main__":
    run()
