#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""factor_efficacy.py — 재무지표 vs 미래주가 상관 계량화 (팩터 효력 검정)

질문: EPS·PER·PBR·배당 등 어떤 재무지표가 실제로 '미래 주가 상승'과 상관이 높은가?
방법(미국·글로벌 팩터투자 방법론): 각 지표를 팩터로 만들어
  ① IC(정보계수) = 매월 지표 랭크 vs 다음달 수익 랭크 상관 → 예측력(평균IC·t·IR)
  ② 분위수 롱숏 = 상위20% − 하위20% EW 다음달 수익 → 팩터수익·Sharpe·승률·단조성
30년 상폐포함 월봉·top200 유동·재무 2002~2026. 룩어헤드 없음(t월말 지표 → t+1 수익).

보유 지표: EPS·BPS·PER·PBR·DIV·DPS(+가격·시총) → 파생: 이익수익률(E/P)·순자산수익률(B/P)·
  배당수익률·EPS성장·ROE근사(EPS/BPS)·PEG역수·모멘텀·사이즈.
✅ EBITDA·EV·FCF·부채는 DART로 수집 완료(재무상세_EBITDA.csv) → EV/EBIT·FCF수익률은 ev_fcf_factor_test.py에서 검정함.
⚠️ 검증용·정보. 과거통계·미래보장 아님. 투자자문 아님·책임 본인.
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

def run():
    px,rets=load_px(); mcap=load_mcap()
    eps=load_fin("EPS"); per=load_fin("PER"); pbr=load_fin("PBR"); bps=load_fin("BPS"); div=load_fin("DIV")
    # 공통 인덱스(재무 존재 구간)
    idx=[m for m in eps.index if m in rets.index and m in mcap.index]
    cols=px.columns
    def align(df): return df.reindex(index=idx,columns=cols)
    EPS,PER,PBR,BPS,DIV=align(eps),align(per),align(pbr),align(bps),align(div)
    RET=rets.reindex(index=idx,columns=cols); MC=mcap.reindex(index=idx,columns=cols); PX=px.reindex(index=idx,columns=cols)
    fwd=RET.shift(-1)   # t월말 지표 → t+1 수익 (룩어헤드 없음)
    # 팩터 구성(높을수록 매수 신호가 되도록 부호 정리)
    ep = 1.0/PER.where(PER>0)                 # 이익수익률 E/P (가치)
    bp = 1.0/PBR.where(PBR>0)                 # 순자산수익률 B/P (가치)
    dy = DIV.where(DIV>=0)                    # 배당수익률 (수익/퀄리티)
    roe= (EPS/BPS).where(BPS>0)              # ROE 근사 (퀄리티)
    g1 = (EPS/EPS.shift(12)-1).where(EPS.shift(12)>0)   # EPS YoY 성장
    g2 = ((EPS/EPS.shift(24))**0.5-1).where(EPS.shift(24)>0)  # EPS 2년 CAGR
    peg= (g1*100)/PER.where(PER>0)           # PEG 역수 (성장/PER; 높을수록 성장대비 싼)
    # 모멘텀 12-1
    mom=(PX.shift(1)/PX.shift(12)-1)
    size=-np.log(MC.where(MC>0))             # 소형 틸트(작을수록 +)
    factors={
        "가치 E/P(이익수익률)":("Value",ep),
        "가치 B/P(순자산)":("Value",bp),
        "배당수익률":("Yield",dy),
        "퀄리티 ROE(EPS/BPS)":("Quality",roe),
        "성장 EPS YoY":("Growth",g1),
        "성장 EPS 2yCAGR":("Growth",g2),
        "가치성장 PEG역수":("Value+Growth",peg),
        "모멘텀 12-1":("Momentum",mom),
        "사이즈(소형)":("Size",size),
    }
    # 유니버스 마스크: 매월 시총 상위200
    rankmc=MC.rank(axis=1,ascending=False)
    univ=(rankmc<=200)
    def spearman_row(a,b):
        m=a.notna()&b.notna()
        if m.sum()<20: return np.nan
        return a[m].rank().corr(b[m].rank())
    results={}
    for name,(fam,F) in factors.items():
        Fm=F.where(univ)
        ics=[]
        for t in idx[:-1]:
            ics.append(spearman_row(Fm.loc[t], fwd.loc[t]))
        ics=pd.Series(ics,dtype=float).dropna()
        meanIC=ics.mean(); icIR=ics.mean()/ics.std() if ics.std()>0 else np.nan; ic_t=meanIC/(ics.std()/np.sqrt(len(ics))) if ics.std()>0 else np.nan
        # 분위수 롱숏(상위20-하위20)
        ls=[]
        for t in idx[:-1]:
            f=Fm.loc[t].dropna(); r=fwd.loc[t]
            f=f[[c for c in f.index if pd.notna(r.get(c))]]
            if len(f)<50: continue
            q=pd.qcut(f.rank(method="first"),5,labels=False)
            top=f.index[q==4]; bot=f.index[q==0]
            ls.append(r[top].mean()-r[bot].mean())
        ls=pd.Series(ls,dtype=float).dropna()
        lsSharpe=ls.mean()/ls.std()*np.sqrt(12) if ls.std()>0 else np.nan
        lsAnn=ls.mean()*12*100; lsHit=(ls>0).mean()*100
        results[name]=dict(fam=fam,meanIC=round(meanIC,4),ic_t=round(ic_t,1),icIR=round(icIR,2),
                           ls_ann=round(lsAnn,1),ls_sharpe=round(lsSharpe,2),ls_hit=round(lsHit,0),n=len(ics))
    # 출력(예측력 순 = |meanIC|)
    order=sorted(results.items(), key=lambda kv: -abs(kv[1]["meanIC"]))
    print("="*104)
    print("팩터 효력 검정 — 재무지표 vs 다음달 수익 예측력 (30년·top200·룩어헤드X)")
    print("="*104)
    print(f"  {'팩터':<22}{'계열':<14}{'평균IC':>8}{'IC t':>7}{'IC IR':>7}{'롱숏 연%':>9}{'롱숏Sharpe':>11}{'승률':>7}")
    for name,r in order:
        print(f"  {name:<22}{r['fam']:<14}{r['meanIC']:>+8.4f}{r['ic_t']:>7.1f}{r['icIR']:>7.2f}{r['ls_ann']:>+8.1f}%{r['ls_sharpe']:>11.2f}{r['ls_hit']:>6.0f}%")
    print("\n  ── 해석 (미국·글로벌 팩터 기준) ──")
    top3=[n for n,_ in order[:3]]
    print(f"  · 예측력 상위: {', '.join(top3)} (평균IC 큰=미래수익과 상관 높음). IC>0.02·t>2면 유의미한 팩터.")
    print("  · 가치(E/P·B/P)·배당=미국 Fama-French Value/Yield, 성장·ROE=Quality/Growth, 모멘텀=Jegadeesh, 사이즈=Size.")
    print("  · IC 양수=지표 높을수록 다음달 수익↑. 롱숏 Sharpe>0.5면 실전 팩터 후보.")
    print("  ✅ EBITDA·EV·FCF·부채는 DART 수집 완료(재무상세_EBITDA.csv) → EV/EBIT·FCF는 ev_fcf_factor_test.py에서 검정(한국선 배당·E/P 우위·EV/EBIT 유의하나 약함·FCF 무효).")
    print("  ⚠️ 남은 한계: EV/EBITDA는 감가상각 커버리지 26%로 표본 작음 · 미국·홍콩 개별종목 데이터 미보유(국가간 상관은 별도 데이터 필요).")
    print("  ⚠️ 검증용·과거통계. 미래보장 아님. 투자자문 아님·책임 본인.")
    json.dump(results, open(os.path.join(BASE,"factor_efficacy_result.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2,default=str)
    print("  저장: factor_efficacy_result.json")
    return results

if __name__=="__main__":
    run()
