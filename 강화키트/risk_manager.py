#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""risk_manager.py — 진입+매도+사이징 통합 집행 시트 (한 바퀴 완성)

entry_screener(A진입 종목) + exit_routing(트랙별 매도규칙) + 진우_통합한도.json(사이징)
을 결합해 '바로 집행 가능한' 표를 만든다:
  · 트랙 라우팅: 성장=넓은 트레일(고점−max(3.5ATR,25%)) · 가치=재난 −40%+가치회귀(PBR≥1.0/+100%)
  · 사이징: 트레이드당 리스크 1%(돌파 0.5%) · 비중 = 리스크% ÷ 1R(=진입가−손절가 폭) · stock cap 15%
  · 포트폴리오: heat(=Σ리스크) ≤ 6% · 동시 최대 15종 → heat 한도까지 점수순 채택
파라미터는 전부 진우_통합한도.json에서 읽음(단일 진실원천). 월봉 종가 기준.
사용: py risk_manager.py [--capital 100000000] [--topn 30]
⚠️ 기계적 집행 시트·정보용. 슬리피지·유동성·thesis는 별도 확인. 투자자문 아님·책임 본인.
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

import os, sys, json, argparse, numpy as np, pandas as pd, warnings
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
def load_names():
    p=_find("종목명_맵.csv"); m={}
    if p:
        try:
            for _,r in pd.read_csv(p,dtype=str).iterrows(): m[str(r["code"]).zfill(6)]=r["name"]
        except Exception: pass
    return m
def load_params():
    p=_find("진우_통합한도.json"); s={}
    if p:
        try:
            j=json.load(open(p,encoding="utf-8")); s=j.get("재량_사이징",{}); s["_rg"]=j.get("집행_riskguard",{})
        except Exception: pass
    g=lambda k,dv: s.get(k,dv)
    return dict(risk=g("risk_per_trade_pct",1.0),risk_bo=g("돌파_risk_per_trade_pct",0.5),
        heat=g("portfolio_heat_cap_pct",6.0),trail=g("momentum_트레일_pct",25.0),
        disaster=abs(g("deepvalue_재난백스톱_pct",-40.0)),
        stock_cap=s.get("_rg",{}).get("max_weight_pct",15.0),
        maxpos=s.get("_rg",{}).get("max_positions",15))
WV={"배당":0.046,"E/P":0.033,"B/P":0.027}; WG={"배당":0.038,"ROE":0.025,"EPS성장":0.023}
def z(s):
    m=s.mean(); sd=s.std(); return (s-m)/sd if sd>0 else s*0

def run(capital=100_000_000, topn=30):
    P=load_params()
    px=load_px(); mcap=load_mcap()
    EPS=load_fin("EPS");PER=load_fin("PER");PBR=load_fin("PBR");BPS=load_fin("BPS");DIV=load_fin("DIV")
    ym=[m for m in EPS.index if m in px.index and m in mcap.index][-1]
    cols=px.columns; MC=mcap.loc[ym].reindex(cols); univ=MC.rank(ascending=False)<=200
    per=PER.loc[ym].reindex(cols); pbr=PBR.loc[ym].reindex(cols).where(univ); bps=BPS.loc[ym].reindex(cols)
    div=DIV.loc[ym].reindex(cols); eps=EPS.loc[ym].reindex(cols); eps12=EPS.shift(12).loc[ym].reindex(cols)
    ep=1.0/per.where(per>0); bp=1.0/pbr.where(pbr>0); dy=div.where(div>=0)
    roe=(eps/bps).where(bps>0); g1=(eps/eps12-1).where(eps12>0).clip(-1,3)
    med=pbr.median(); growth=(pbr>=med)&pbr.notna(); value=(pbr<med)&pbr.notna()
    MA10=px.rolling(10).mean().loc[ym].reindex(cols); last=px.loc[ym].reindex(cols); up=(last>=MA10)
    def score(mask,W,f):
        sc=pd.Series(0.0,index=cols); cnt=pd.Series(0,index=cols)
        for k,w in W.items():
            zz=z(f[k].where(mask)); sc=sc.add(w*zz.fillna(0)); cnt=cnt.add(zz.notna().astype(int))
        return sc.where(mask&(cnt>=2))
    VS=score(value,WV,{"배당":dy,"E/P":ep,"B/P":bp}); GS=score(growth,WG,{"배당":dy,"ROE":roe,"EPS성장":g1})
    nm=load_names()
    # A진입 후보(추세위) 만 · 트랙별 상위
    def picks(S,kind):
        s=S.where(up).dropna().sort_values(ascending=False)   # A진입=점수&추세위
        out=[]
        for c in s.index[:topn]:
            p=last.get(c)
            if pd.isna(p) or p<=0: continue
            if kind=="growth":
                onR=P["trail"]/100.0; stop=p*(1-onR); rule=f"고점−max(3.5ATR,{P['trail']:.0f}%) 트레일"
            else:
                onR=P["disaster"]/100.0; stop=p*(1-onR); rule=f"재난 −{P['disaster']:.0f}%·가치회귀(PBR≥1.0/+100%)"
            w=min(P["risk"]/ (onR*100), P["stock_cap"]/100.0)   # 비중=리스크%÷1R%
            out.append(dict(code=c,name=nm.get(c,c),track=kind,score=float(S.get(c)),price=float(p),
                            stop=float(stop),R=onR*100,weight=w*100,rule=rule,
                            roe=(float(roe.get(c))*100 if pd.notna(roe.get(c)) else None),
                            g1=(float(g1.get(c))*100 if pd.notna(g1.get(c)) else None),
                            div=(float(dy.get(c)) if pd.notna(dy.get(c)) else None),per=(float(per.get(c)) if pd.notna(per.get(c)) else None),pbr=(float(pbr.get(c)) if pd.notna(pbr.get(c)) else None)))
        return out
    allp=picks(VS,"value")+picks(GS,"growth")
    allp.sort(key=lambda r:-r["score"])
    # heat 한도까지 채택(리스크 1%씩) · max_positions
    book=[]; heat=0.0
    for r in allp:
        if len(book)>=P["maxpos"] or heat+P["risk"]>P["heat"]+1e-9: break
        r["risk_used"]=P["risk"]; r["amount"]=capital*r["weight"]/100.0; r["shares"]=int(r["amount"]//r["price"])
        heat+=P["risk"]; book.append(r)
    print("="*98); print(f"통합 집행 시트 — 진입·매도·사이징 (자본 {capital:,.0f}원 · {ym})"); print("="*98)
    print(f"  규칙(진우_통합한도.json): 리스크 {P['risk']:.0f}%/트레이드 · heat≤{P['heat']:.0f}% · stock cap {P['stock_cap']:.0f}% · 최대 {P['maxpos']:.0f}종")
    print(f"\n  【 채택 북 】 {len(book)}종 · 총 heat {heat:.1f}% · 투입 {sum(r['weight'] for r in book):.0f}% (현금 {100-sum(r['weight'] for r in book):.0f}%)")
    print(f"    {'트랙':<5}{'종목':<13}{'현재가':>9}{'손절가':>9}{'1R':>6}{'비중':>6}{'수량':>7}  매도규칙")
    for r in book:
        tk='성장' if r['track']=='growth' else '가치'
        print(f"    {tk:<5}{r['name']:<13}{r['price']:>9,.0f}{r['stop']:>9,.0f}{r['R']:>5.0f}%{r['weight']:>5.1f}%{r['shares']:>7,d}  {r['rule']}")
    rest=[r for r in allp if r not in book]
    if rest:
        print(f"\n  【 대기 】 heat/종목수 한도 초과 — 상위 {min(8,len(rest))}종(다음 후보)")
        for r in rest[:8]:
            tk='성장' if r['track']=='growth' else '가치'
            print(f"    {tk} {r['name']:<13} 비중목표 {r['weight']:.1f}% · 손절 {r['stop']:,.0f}")
    print(f"\n  · 비중 = 리스크% ÷ 1R → 가치(넓은 재난스톱)는 작게, 성장(25%트레일)은 크게 = 리스크 균등.")
    print(f"  · 성장=고점 갱신 시 트레일 상향 · 가치=PBR≥1.0/+100%에 익절, 스톱은 재난용만(인내).")
    print(f"  · 섹터당 2종·계열 1종·slippage·유동성(ADTV 1%)은 집행 전 별도 확인.")
    print("  ⚠️ 기계적 시트·과거통계 기반·미래보장 아님. 투자자문 아님·책임 본인.")
    json.dump(dict(asof=ym,capital=capital,params=P,book=book,wait=[r['name'] for r in rest[:10]]),
              open(os.path.join(BASE,"risk_manager_result.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2,default=str)
    print("  저장: risk_manager_result.json")
    return ym,book
if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--capital",type=float,default=100_000_000); ap.add_argument("--topn",type=int,default=30)
    a=ap.parse_args(); run(a.capital,a.topn)
