#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""exit_routing_backtest.py — 두 트랙 × 진입유형별 매도 라우팅 왕복 백테

매도규칙서 v3 "진입이 매도를 결정한다"를 두 트랙에 적용해 검증:
  성장 트랙(고PBR·모멘텀형) → 넓은 트레일(고점 −25%, ≈ max(3.5ATR,25%)의 하한)
  가치 트랙(저PBR·딥밸류)   → 타이트스톱 금지 · 재난 −40% · 가치회귀(PBR≥1.0/+100%) 청산
각 트랙: [스톱없음(등급이탈만)] vs [라우팅 매도] 월간 포트폴리오 비교(CAGR·MDD·Sharpe).
월봉 종가 기준(진짜 ATR·장중체결 없음 → 근사, 일봉 §9검증이 더 정밀). top200·룩어헤드X.
⚠️ 과거통계·비용전·미래보장 아님. 투자자문 아님·책임 본인.
"""
import os as _os2
def _jqroot2():
    """프로젝트 루트 자동탐색 (2026-07-27 §5b)."""
    d=_os2.path.dirname(_os2.path.abspath(__file__))
    for _ in range(5):
        if _os2.path.exists(_os2.path.join(d,"종목시총_30년.csv")): return d
        d=_os2.path.dirname(d)
    return _os2.path.dirname(_os2.path.abspath(__file__))


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

import os, sys, json, numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
BASE=os.path.dirname(os.path.abspath(__file__)); UP= _jqroot2()
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
def _find(fn):
    for d in (BASE,os.path.dirname(BASE),UP,os.path.join(UP,"강화키트")):
        p=os.path.join(d,fn)
        if os.path.exists(p): return p
    return None
def load_px():
    fr=[]
    for f in ("_월봉종가캐시_KOSPI.csv","_월봉종가캐시_KOSDAQ.csv"):
        p=_find(f)
        if p: d=pd.read_csv(p,dtype={"code":str}); d["code"]=d["code"].str.zfill(6); fr.append(d)
    return pd.concat(fr).pivot_table(index="ym",columns="code",values="close",aggfunc="last").sort_index()
def load_fin(field):
    fr=[]
    for f in ("종목재무_KRX_KOSPI.csv","종목재무_KRX_KOSDAQ.csv"):
        p=_find(f)
        if p:
            d=pd.read_csv(p,dtype={"code":str}); d["code"]=d["code"].str.zfill(6)
            d["ym"]=pd.to_datetime(d["date"]).dt.strftime("%Y-%m"); fr.append(d[["ym","code",field]])
    return pd.concat(fr).pivot_table(index="ym",columns="code",values=field,aggfunc="last").sort_index()
def load_mcap():
    d=pd.read_csv(_find("종목시총_30년.csv"),dtype={"code":str}); d["code"]=d["code"].str.zfill(6)
    d["ym"]=pd.to_datetime(d["date"]).dt.strftime("%Y-%m")
    return d.pivot_table(index="ym",columns="code",values="mcap",aggfunc="last").sort_index()
WV={"배당":0.046,"E/P":0.033,"B/P":0.027}; WG={"배당":0.038,"ROE":0.025,"EPS성장":0.023}
def zrow(df): return df.sub(df.mean(axis=1),axis=0).div(df.std(axis=1).replace(0,np.nan),axis=0)
CAP=8; TRAIL=0.25; DISASTER=0.40

def build():
    px=load_px(); mcap=load_mcap()
    EPS=load_fin("EPS");PER=load_fin("PER");PBR=load_fin("PBR");BPS=load_fin("BPS");DIV=load_fin("DIV")
    idx=[m for m in EPS.index if m in px.index and m in mcap.index and m>="2003-01"]
    cols=px.columns; al=lambda d:d.reindex(index=idx,columns=cols)
    EPS,PER,PBR,BPS,DIV=al(EPS),al(PER),al(PBR),al(BPS),al(DIV)
    PX=px.reindex(index=idx,columns=cols); MC=mcap.reindex(index=idx,columns=cols)
    RET=PX.pct_change(fill_method=None).mask(lambda x:x.abs()>1.0)
    univ=MC.rank(axis=1,ascending=False)<=200
    ep=1.0/PER.where(PER>0); bp=1.0/PBR.where(PBR>0); dy=DIV.where(DIV>=0)
    roe=(EPS/BPS).where(BPS>0); g1=(EPS/EPS.shift(12)-1).where(EPS.shift(12)>0).clip(-1,3)
    med=PBR.where(univ).median(axis=1)
    growth=univ&PBR.ge(med,axis=0); value=univ&PBR.lt(med,axis=0)
    MA10=PX.rolling(10).mean(); up=(PX>=MA10)&MA10.notna()
    def score(mask,W,f):
        s=None;cnt=None
        for k,w in W.items():
            zz=zrow(f[k].where(mask)); s=w*zz.fillna(0) if s is None else s.add(w*zz.fillna(0))
            cnt=zz.notna().astype(int) if cnt is None else cnt.add(zz.notna().astype(int))
        return s.where(mask&(cnt>=2))
    VS=score(value,WV,{"배당":dy,"E/P":ep,"B/P":bp}); GS=score(growth,WG,{"배당":dy,"ROE":roe,"EPS성장":g1})
    # A진입 후보(점수 상위20% & 추세위)
    def signal(S): return (S.rank(axis=1,pct=True)>=0.8)&up
    return dict(idx=idx,cols=cols,PX=PX,RET=RET,PBR=PBR,up=up,
                Vsig=signal(VS),Gsig=signal(GS),VS=VS,GS=GS)

def metrics(curve, idx):
    s=pd.Series(curve,index=idx[:len(curve)]).dropna()
    if len(s)<24: return None
    ret=s.pct_change().dropna()
    yrs=len(s)/12.0; cagr=(s.iloc[-1]/s.iloc[0])**(1/yrs)-1
    mdd=((s/s.cummax())-1).min()
    sh=ret.mean()/ret.std()*np.sqrt(12) if ret.std()>0 else 0
    return dict(cagr=round(cagr*100,1),mdd=round(mdd*100,1),sharpe=round(sh,2),
                total_x=round(s.iloc[-1]/s.iloc[0],1))

def sim(D, sig, S, kind):
    """kind: 'none'(등급이탈만) | 'routed'(트랙별 매도규칙)."""
    idx=D["idx"]; PX=D["PX"]; RET=D["RET"]; PBR=D["PBR"]
    hold={}   # code -> dict(entry, peak)
    eq=1.0; curve=[]
    for i,t in enumerate(idx):
        # 1) 이번달 수익 실현(전월말 보유분)
        if hold:
            rs=[RET.loc[t,c] for c in hold if pd.notna(RET.loc[t,c])]
            eq*= (1+np.mean(rs)) if rs else 1.0
        curve.append(eq)
        px_t=PX.loc[t]; sg=sig.loc[t]
        # 2) 보유 갱신 & 청산
        for c in list(hold):
            p=px_t.get(c)
            if pd.isna(p): hold.pop(c,None); continue
            hold[c]["peak"]=max(hold[c]["peak"],p)
            ex=False
            if kind=="none":
                if not bool(sg.get(c,False)): ex=True         # 등급(A진입) 이탈 시
            else:
                if S is D["GS"] or sig is D["Gsig"]:            # 성장=트레일
                    if p<=hold[c]["peak"]*(1-TRAIL): ex=True
                    if p<=hold[c]["entry"]*(1-DISASTER): ex=True
                else:                                          # 가치=재난+가치회귀
                    pb=PBR.loc[t].get(c)
                    if p<=hold[c]["entry"]*(1-DISASTER): ex=True
                    if pd.notna(pb) and pb>=1.0: ex=True
                    if p>=hold[c]["entry"]*2.0: ex=True
            if ex: hold.pop(c,None)
        # 3) 슬롯 채우기(A진입 후보 상위 점수, 미보유)
        if len(hold)<CAP:
            cand=S.loc[t].where(sg).dropna().sort_values(ascending=False)
            for c in cand.index:
                if len(hold)>=CAP: break
                if c not in hold and pd.notna(px_t.get(c)):
                    hold[c]=dict(entry=px_t[c],peak=px_t[c])
    return metrics(curve, idx), curve

def main():
    D=build()
    print("="*88); print("매도 라우팅 왕복 백테 — 스톱없음(등급이탈) vs 트랙별 매도규칙 (2003~·top200)"); print("="*88)
    out={}
    for tname,S,sig in (("가치 트랙",D["VS"],D["Vsig"]),("성장 트랙",D["GS"],D["Gsig"])):
        mn,_=sim(D,sig,S,"none"); mr,_=sim(D,sig,S,"routed")
        out[tname]={"스톱없음":mn,"라우팅매도":mr}
        print(f"\n  《{tname}》")
        print(f"    {'전략':<14}{'누적배수':>9}{'CAGR':>8}{'MDD':>9}{'Sharpe':>9}")
        for k,m in (("스톱없음(등급)",mn),("라우팅 매도",mr)):
            if m: print(f"    {k:<14}{m['total_x']:>8}x{m['cagr']:>+7.1f}%{m['mdd']:>+8.1f}%{m['sharpe']:>9.2f}")
    print("\n  · 성장=고점−25%트레일 · 가치=재난−40%+가치회귀(PBR≥1.0/+100%). CAP 8종 EW.")
    print("  · 라우팅이 MDD↓·Sharpe↑면 '진입유형별 매도'가 유효(같은 종목도 매도로 결과 갈림).")
    print("  ⚠️ 월봉근사(진짜 ATR·장중체결 없음)·비용전·과거통계. 투자자문 아님·책임 본인.")
    json.dump(out,open(os.path.join(BASE,"exit_routing_result.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2,default=str)
    print("  저장: exit_routing_result.json")

if __name__=="__main__":
    main()
