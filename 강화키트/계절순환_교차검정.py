#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""계절순환_교차검정.py — 횡단면 계절성(cross-sectional seasonality) 검정

★ 지수 타이밍 할로윈(기각)과 다른 가설: "종목이 각자의 달에 반복해서 강한가?"
근거: Heston & Sadka (2008, JFE) · Keloharju-Linnainmaa-Nyberg (2016, JF).
방법: 각 시점 t에서 종목별 신호 = 그 이전 연도들의 같은 달 평균수익(룩어헤드 차단, 최소 3년).
      상위 5분위 롱 vs EW-all, 롱숏(상위−하위) 스프레드.

사전등록 게이트(결과 보기 전 고정):
  ① 롱숏 t ≥ 2.3 & 양(+)   ② OOS 전·후반 부호 유지
  ③ 최고 3개월 빼도 롱숏 t ≥ 1.5 (이상치 의존 아님 — 지수 할로윈 죽인 바로 그 테스트)
  ④ 롱온리 상위5분위 CAGR > EW-all

데이터: kospi_monthly_prices.csv (wide: Date × code, 월말 종가)
사용: py 계절순환_교차검정.py [--minyears 3] [--minstocks 30]
⚠️ 생존편향(현재 상장 위주)·2010~2026·월간 회전비용 미차감. 검증용, 실현손익 아님. 투자자문 아님·책임 본인.
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

import os, sys, argparse
import numpy as np, pandas as pd
BASE=os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def _find(fn):
    for d in (BASE, os.path.dirname(BASE), os.getcwd()):
        p=os.path.join(d,fn)
        if os.path.exists(p): return p
    return None

def load_returns():
    p=_find("kospi_monthly_prices.csv")
    if not p: raise FileNotFoundError("kospi_monthly_prices.csv 없음")
    df=pd.read_csv(p)
    dcol=df.columns[0]
    df[dcol]=pd.to_datetime(df[dcol])
    df=df.set_index(dcol).sort_index()
    px=df.apply(pd.to_numeric, errors="coerce")
    rets=px.pct_change()
    # 이상치 클리핑(액면분할·오류 방어): ±100% 초과 월수익 제거
    rets=rets.mask(rets.abs()>1.0)
    return rets

def tstat(x):
    x=pd.Series(x).dropna()
    return float(x.mean()/(x.std()/np.sqrt(len(x)))) if len(x)>2 and x.std()>0 else np.nan

def cagr(x, ann=12):
    x=pd.Series(x).dropna()
    return float((1+x).prod()**(ann/len(x))-1) if len(x)>0 else np.nan

def run(minyears=3, minstocks=30):
    rets=load_returns()
    dates=rets.index
    ls=[]; topq=[]; ew=[]; kept=[]
    for t in dates:
        m=t.month
        prior=rets[(rets.index.month==m) & (rets.index<t)]
        if len(prior)<minyears: continue
        sig=prior.mean(axis=0, skipna=True)       # 종목별 과거 같은 달 평균(룩어헤드 없음)
        cur=rets.loc[t]                            # 이번 달 실제 수익
        valid=sig.notna() & cur.notna()
        sig2=sig[valid]; cur2=cur[valid]
        if len(sig2)<minstocks: continue
        q=pd.qcut(sig2.rank(method="first"), 5, labels=False)   # 0..4 (4=상위)
        top=cur2[q==4]; bot=cur2[q==0]
        ls.append(top.mean()-bot.mean())
        topq.append(top.mean())
        ew.append(cur2.mean())
        kept.append(t)
    S=pd.Series(ls,index=kept); TQ=pd.Series(topq,index=kept); EW=pd.Series(ew,index=kept)
    n=len(S)
    print("="*74); print("횡단면 계절성 교차검정 (사전등록 게이트)"); print("="*74)
    print(f"  구간 {kept[0].date()} ~ {kept[-1].date()} · 유효 {n}개월 · 최소 {minyears}년/{minstocks}종")
    # 게이트 ①
    t_ls=tstat(S); ls_ann=S.mean()*12
    g1 = (t_ls>=2.3 and S.mean()>0)
    print(f"\n  ① 롱숏 스프레드: 월평균 {S.mean()*100:+.2f}% (연 {ls_ann*100:+.1f}%) · t={t_ls:.2f}  → {'PASS' if g1 else 'FAIL'}")
    # 게이트 ② OOS
    half=n//2
    t1=tstat(S.iloc[:half]); t2=tstat(S.iloc[half:])
    g2 = (np.sign(S.iloc[:half].mean())==np.sign(S.iloc[half:].mean()) and S.iloc[:half].mean()>0 and S.iloc[half:].mean()>0)
    print(f"  ② OOS 전반 t={t1:.2f}(평균 {S.iloc[:half].mean()*100:+.2f}%) · 후반 t={t2:.2f}(평균 {S.iloc[half:].mean()*100:+.2f}%)  → {'PASS' if g2 else 'FAIL'}")
    # 게이트 ③ 최고 3개월 제거
    S_drop=S.sort_values(ascending=False).iloc[3:]
    t_drop=tstat(S_drop)
    g3 = (t_drop>=1.5 and S_drop.mean()>0)
    print(f"  ③ 최고 3개월 제거 후 t={t_drop:.2f}(평균 {S_drop.mean()*100:+.2f}%)  → {'PASS' if g3 else 'FAIL'}  [지수 할로윈을 죽인 테스트]")
    # 게이트 ④ 롱온리 vs EW
    c_tq=cagr(TQ); c_ew=cagr(EW)
    g4 = (c_tq>c_ew)
    print(f"  ④ 롱온리 상위5분위 CAGR {c_tq*100:.1f}% vs EW-all {c_ew*100:.1f}%  → {'PASS' if g4 else 'FAIL'}")
    # 종합
    passed=sum([g1,g2,g3,g4])
    print("\n"+"-"*74)
    if passed==4:
        v="✅ 4/4 통과 — 횡단면 계절성 실재 후보. 정식 사전등록(30년 상폐패널·비용차감·OOS봉인)으로 승격 권고."
    elif g1 and g3:
        v=f"🟡 {passed}/4 — 핵심(유의+이상치강건)은 통과하나 일부 미달. 조건부 관찰."
    else:
        v=f"⚠️ {passed}/4 — 지수 할로윈처럼 취약(특히 ③ 이상치/②OOS). 진우 직관은 매력적이나 이 데이터선 미통과 → 기각 유지."
    print("  판정:",v)
    print("\n  ⚠️ 생존편향(현재 상장 위주)·회전비용 미차감. 통과해도 30년 상폐패널·비용반영 재검증 전엔 확정 아님.")
    print("  ⚠️ 투자자문 아님·책임 본인.")
    return dict(n=n, t_ls=round(t_ls,2), ls_ann_pct=round(ls_ann*100,2),
                oos_t=[round(t1,2),round(t2,2)], drop3_t=round(t_drop,2),
                topq_cagr=round(c_tq*100,2), ew_cagr=round(c_ew*100,2),
                gates=dict(g1_유의=bool(g1),g2_oos=bool(g2),g3_이상치강건=bool(g3),g4_vsEW=bool(g4)), passed=int(passed))

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--minyears",type=int,default=3); ap.add_argument("--minstocks",type=int,default=30)
    a=ap.parse_args(); import json
    r=run(a.minyears,a.minstocks)
    json.dump(r, open(os.path.join(BASE,"계절순환_교차검정_결과.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=2)
    print("\n  저장: 계절순환_교차검정_결과.json")

if __name__=="__main__": main()
