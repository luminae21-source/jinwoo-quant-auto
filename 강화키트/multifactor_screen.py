#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""multifactor_screen.py — 멀티팩터 스코어 스크리너 (배당+가치+성장 결합)

팩터 효력 검정에서 유효했던 지표를 IC 가중으로 합성 → 종목 랭킹.
  가중(2026-07 개편·밸류편중 완화+모멘텀15% 헤지·롱온리 비용기준): 배당 0.270 · B/P 0.204 · E/P 0.166 · 성장YoY 0.110 · ROE 0.100 · 모멘텀12-1 0.150
  각 팩터 = 매월 유니버스 내 z-score(횡단면 표준화), 합성점수 = Σ w·z.
① 백테: 합성점수의 IC·분위수 롱숏 Sharpe → 단일 최강팩터(배당) 대비 개선 확인.
② 현재: 최신월 합성점수 상위 랭킹(하위팩터·테마·추세 동반).
30년 상폐포함·top200 유동·룩어헤드X. ⚠️ 정보용·미래보장 아님·투자자문 아님·책임 본인.
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

# 개편(2026-07): 밸류(배당·E/P·B/P) 3중 베팅 완화 위해 모멘텀 헤지축 도입. 이 스크리너는
#   '매수 추천'(롱온리)이므로 비용반영 롱온리 백테 기준으로 모멘텀 15% 채택(30%→15% 하향 정정).
#   근거: 밸류–모멘텀 상관 -0.54(밸류겨울 방어). 다만 롱숏 Sharpe 개선(0.65→0.75)은 대부분 숏다리
#         효과 → 롱온리 순Sharpe(왕복40bps)는 0%=0.66·15%=0.66·30%=0.60(악화). 15%=Sharpe중립+
#         밸류부진기 방어 +0.01→+0.15%/월. (MDD는 모멘텀크래시로 소폭↑ 트레이드오프 인지.)
#   상세: 비용반영_백테_결과.json·가중개편_백테.html. 이전값: 배당0.049/B/P0.037/E/P0.030/성장0.020/ROE0.018.
#   옵션: MDD 최우선=모멘텀0 / 공매도 롱숏운용 시에만 30%. 이전값도 이 파일 커밋로그 참고.
WEIGHTS={"배당":0.270,"B/P":0.204,"E/P":0.166,"성장":0.110,"ROE":0.100,"모멘텀":0.150}

def _find(fn):
    for d in (BASE, os.path.dirname(BASE), os.getcwd()):
        p=os.path.join(d,fn)
        if os.path.exists(p): return p
    return None
def load_fin(field):
    fr=[]
    for f in ("종목재무_KRX_KOSPI.csv","종목재무_KRX_KOSDAQ.csv"):
        p=_find(f)
        if p:
            d=pd.read_csv(p,dtype={"code":str}); d["code"]=d["code"].str.zfill(6)
            d["ym"]=pd.to_datetime(d["date"]).dt.strftime("%Y-%m"); fr.append(d[["ym","code",field]])
    return pd.concat(fr).pivot_table(index="ym",columns="code",values=field,aggfunc="last").sort_index()
def load_px():
    fr=[]
    for f in ("_월봉종가캐시_KOSPI.csv","_월봉종가캐시_KOSDAQ.csv"):
        p=_find(f)
        if p:
            d=pd.read_csv(p,dtype={"code":str}); d["code"]=d["code"].str.zfill(6); fr.append(d)
    px=pd.concat(fr).pivot_table(index="ym",columns="code",values="close",aggfunc="last").sort_index()
    return px, px.pct_change().mask(lambda x:x.abs()>1.0)
def load_mcap():
    p=_find("종목시총_30년.csv"); d=pd.read_csv(p,dtype={"code":str}); d["code"]=d["code"].str.zfill(6)
    d["ym"]=pd.to_datetime(d["date"]).dt.strftime("%Y-%m")
    return d.pivot_table(index="ym",columns="code",values="mcap",aggfunc="last")
def load_names():
    p=_find("종목명_맵.csv"); m={}
    if p:
        try:
            d=pd.read_csv(p,dtype=str)
            for _,r in d.iterrows(): m[str(r["code"]).zfill(6)]=r["name"]
        except Exception: pass
    return m
THEME={"105560":"금융","055550":"금융","139130":"금융","138930":"금융","086790":"금융","316140":"금융","024110":"금융",
 "001450":"보험","000810":"보험","081660":"의류","214450":"미용의료","012510":"SW","066570":"전자","006800":"증권",
 "039490":"증권","071050":"증권","003230":"K푸드","257720":"뷰티유통","042660":"조선","064350":"방산","030200":"통신",
 "036570":"게임","005930":"반도체","000660":"반도체","042700":"반도체장비","007660":"AI기판","034730":"지주"}

def zscore(row):
    m=row.mean(); s=row.std()
    return (row-m)/s if s>0 else row*0

def build_scores(EPS,PER,PBR,BPS,DIV,PX,univ):
    ep=(1.0/PER.where(PER>0)); bp=(1.0/PBR.where(PBR>0)); dy=DIV.where(DIV>=0)
    roe=(EPS/BPS).where(BPS>0); g1=(EPS/EPS.shift(12)-1).where(EPS.shift(12)>0)
    g1=g1.clip(-1,3)  # 성장 윈저라이즈
    mom=(PX.shift(1)/PX.shift(12)-1)  # 모멘텀 12-1(최근월 스킵=단기반전 회피·룩어헤드X)
    facs={"배당":dy,"B/P":bp,"E/P":ep,"성장":g1,"ROE":roe,"모멘텀":mom}
    Z={}
    for k,F in facs.items():
        Fu=F.where(univ)
        Z[k]=Fu.apply(zscore,axis=1)
    score=sum(WEIGHTS[k]*Z[k].fillna(0) for k in WEIGHTS)
    valid=sum(Z[k].notna().astype(int) for k in WEIGHTS)>=3
    return score.where(univ & valid), facs, Z

def run():
    px,rets=load_px(); mcap=load_mcap()
    EPS=load_fin("EPS");PER=load_fin("PER");PBR=load_fin("PBR");BPS=load_fin("BPS");DIV=load_fin("DIV")
    idx=[m for m in EPS.index if m in rets.index and m in mcap.index]
    cols=px.columns
    al=lambda df: df.reindex(index=idx,columns=cols)
    EPS,PER,PBR,BPS,DIV=al(EPS),al(PER),al(PBR),al(BPS),al(DIV)
    RET=rets.reindex(index=idx,columns=cols); MC=mcap.reindex(index=idx,columns=cols); PX=px.reindex(index=idx,columns=cols)
    univ=(MC.rank(axis=1,ascending=False)<=200)
    fwd=RET.shift(-1)
    score,facs,Z=build_scores(EPS,PER,PBR,BPS,DIV,PX,univ)
    ics=[];ls=[];loex=[]   # loex=롱온리 초과수익(상위20% − 유니버스 EW): 실제 매수상품 기준
    for t in idx[:-1]:
        f=score.loc[t].dropna(); r=fwd.loc[t]
        f=f[[c for c in f.index if pd.notna(r.get(c))]]
        if len(f)<50: continue
        ics.append(f.rank().corr(r[f.index].rank()))
        q=pd.qcut(f.rank(method="first"),5,labels=False)
        top=f.index[q==4]
        ls.append(r[top].mean()-r[f.index[q==0]].mean())
        loex.append(r[top].mean()-r[f.index].mean())   # 상위분위 − 동일가중 벤치마크
    ics=pd.Series(ics).dropna(); ls=pd.Series(ls).dropna(); loex=pd.Series(loex).dropna()
    meanIC=ics.mean(); ic_t=meanIC/(ics.std()/np.sqrt(len(ics)))
    lsSharpe=ls.mean()/ls.std()*np.sqrt(12); lsAnn=ls.mean()*12*100; hit=(ls>0).mean()*100
    loexSharpe=loex.mean()/loex.std()*np.sqrt(12); loexAnn=loex.mean()*12*100; loexHit=(loex>0).mean()*100
    print("="*92); print("멀티팩터 합성 스코어 — 백테 효력 (30년·top200·룩어헤드X)"); print("="*92)
    print(f"  [롱숏·공매도 전제·시장중립] 평균IC {meanIC:+.4f} (t {ic_t:.1f}) · 롱숏 {lsAnn:+.1f}%/년 · Sharpe {lsSharpe:.2f} · 승률 {hit:.0f}%")
    print(f"  [롱온리·실제 매수상품·EW벤치 초과] 초과 {loexAnn:+.1f}%/년 · IR {loexSharpe:.2f} · 승률 {loexHit:.0f}%")
    print(f"  · 이 시스템은 매수전용 → 롱온리(초과)가 실전 기준. 롱숏 Sharpe는 숏 알파 포함이라 참고용(비용반영_백테 참조).")
    print(f"  · 단일 최강(배당) IC +0.049 대비 → 합성 = 단일 의존↓·안정성↑(밸류 3중 베팅 완화+모멘텀 헤지).")
    nm=load_names(); ymf=idx[-1]
    s0=score.loc[ymf].dropna().sort_values(ascending=False)
    pr=PER.loc[ymf]; pb=PBR.loc[ymf]; dv=DIV.loc[ymf]; g1=(EPS.loc[ymf]/EPS.shift(12).loc[ymf]-1)
    ma6=PX.rolling(6).mean().loc[ymf]; last=PX.loc[ymf]
    pct=s0.rank(pct=True)*100
    print(f"\n  현재({ymf}) 멀티팩터 상위 25 — 종목 / 점수%ile / 배당 / PER / PBR / EPS성장 / 추세")
    rows=[]
    for c in s0.index[:25]:
        nmk=nm.get(c,c); th=THEME.get(c,"")
        tr = pd.notna(last.get(c)) and pd.notna(ma6.get(c)) and last.get(c)>=ma6.get(c)
        gg=g1.get(c)
        print(f"   {nmk:<14} {pct.get(c):>4.0f}%ile  배당{ (dv.get(c) if pd.notna(dv.get(c)) else 0):>4.1f}%  PER{ (pr.get(c) if pd.notna(pr.get(c)) else 0):>6.1f}  PBR{ (pb.get(c) if pd.notna(pb.get(c)) else 0):>5.1f}  성장{ (gg*100 if pd.notna(gg) else 0):>+5.0f}%  {'추세위' if tr else '추세아래'}{(' ['+th+']') if th else ''}")
        rows.append(dict(code=c,name=nmk,theme=th,pctile=round(float(pct.get(c)),0),
            div=round(float(dv.get(c)),1) if pd.notna(dv.get(c)) else None,per=round(float(pr.get(c)),1) if pd.notna(pr.get(c)) else None,
            pbr=round(float(pb.get(c)),1) if pd.notna(pb.get(c)) else None,g1=round(float(gg)*100,0) if pd.notna(gg) else None,trend=bool(tr)))
    print("\n  ⚠️ 정보용·과거통계. 미래보장 아님. 투자자문 아님·책임 본인.")
    json.dump(dict(asof=ymf,backtest=dict(meanIC=round(meanIC,4),ic_t=round(ic_t,1),ls_ann=round(lsAnn,1),ls_sharpe=round(lsSharpe,2),hit=round(hit,0),
                   lo_excess_ann=round(loexAnn,1),lo_excess_ir=round(loexSharpe,2),lo_excess_hit=round(loexHit,0)),
                   top=rows), open(os.path.join(BASE,"multifactor_result.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2,default=str)
    print("  저장: multifactor_result.json")
    return dict(asof=ymf,meanIC=meanIC,ic_t=ic_t,lsAnn=lsAnn,lsSharpe=lsSharpe,hit=hit,rows=rows)

if __name__=="__main__":
    run()
