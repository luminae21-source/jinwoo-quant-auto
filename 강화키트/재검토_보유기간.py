#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""재검토_보유기간.py — 개인화 재검토 도구 (보유기간별 순수익 · 다올 비용)

"기각된 전략이 '회전만 낮추면' 살아나는가?"를 판정. 신호를 월/분기/반기/연 리밸런싱으로
보유기간을 늘려 회전율·세금을 줄이고, 진우님 실제 비용(다올: 수수료 0·세금 0.20%)으로 순수익 산출.

핵심 원리: 비용 ∝ 회전율. 보유기간 H배 → 회전율 ~1/H → 세금드래그 ~1/H.
  · 지속형 신호(모멘텀·저변동성): 오래 들어도 신호 유지 → 저회전이 순수익 개선(구제 가능).
  · 계절형 신호: 신호가 '매달 다름' → 오래 들면 신호 소멸(구제 불가). ← 이 대조가 판정.

신호(가격만으로 계산): seasonal(과거 같은달) · mom12(12-1 모멘텀) · lowvol(저변동성)
비용(다올): 매도세 0.20% + 슬리피지(편도, 기본 0.05%). 수수료 0.

사용:
  py 재검토_보유기간.py --signal seasonal
  py 재검토_보유기간.py --signal mom12 --slippage 0.0005
  py 재검토_보유기간.py --signal all
⚠️ 상폐포함·유동 top200. 검증용, 실현손익 아님. 투자자문 아님·책임 본인.
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
BASE=os.path.dirname(os.path.abspath(__file__))
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
    allc=pd.concat(frames,ignore_index=True)
    px=allc.pivot_table(index="ym",columns="code",values="close",aggfunc="last").sort_index()
    rets=px.pct_change().mask(lambda x:x.abs()>1.0)
    return px, rets

def load_mcap():
    p=_find("종목시총_30년.csv")
    if not p: return None
    d=pd.read_csv(p,dtype={"code":str}); d["code"]=d["code"].str.zfill(6)
    d["ym"]=pd.to_datetime(d["date"]).dt.strftime("%Y-%m")
    return d.pivot_table(index="ym",columns="code",values="mcap",aggfunc="last")

def signal_at(kind, t, px, rets):
    """시점 t의 종목별 신호 (룩어헤드 없음)."""
    i=list(rets.index).index(t)
    if kind=="seasonal":
        m=t.split("-")[1]
        prior=rets[(rets.index.str[5:7]==m) & (rets.index<t)]
        return prior.mean(axis=0,skipna=True) if len(prior)>=3 else None
    if kind=="mom12":
        if i<13: return None
        # 12-1 모멘텀: t-13..t-2 누적(최근월 제외)
        window=px.iloc[i-13:i-1]
        return window.iloc[-1]/window.iloc[0]-1
    if kind=="lowvol":
        if i<13: return None
        vol=rets.iloc[i-12:i].std()
        return -vol   # 저변동성 = 높은 신호
    return None

def stats(x,ann=12):
    x=pd.Series(x).dropna()
    return (float((1+x).prod()**(ann/len(x))-1), float(x.mean()/x.std()*np.sqrt(ann)) if x.std()>0 else np.nan) if len(x)>0 else (np.nan,np.nan)

def backtest(kind, H, px, rets, mcap, topn=200, tax=0.0015, slippage=0.002045):
    """H개월 보유(리밸런싱 주기 H). 롱온리 상위5분위 vs EW-유니버스. 순수익=다올 비용후."""
    months=list(rets.index)
    held=set(); gross=[]; net=[]; ew=[]; kept=[]; turns=[]
    for k,t in enumerate(months):
        # 유동 유니버스
        if mcap is not None and t in mcap.index:
            mc=mcap.loc[t].dropna(); univ=set(mc.sort_values(ascending=False).head(topn).index)
        else: univ=set(rets.columns)
        cur=rets.loc[t]
        rebal = (k % H == 0) or (not held)
        cost=0.0
        if rebal:
            sig=signal_at(kind,t,px,rets)
            if sig is None: continue
            valid=[c for c in univ if c in sig.index and pd.notna(sig.get(c))]
            if len(valid)<max(30,topn//4):
                if not held: continue
            else:
                s=sig[valid]; q=pd.qcut(s.rank(method="first"),5,labels=False)
                new=set(s.index[q==4])
                f=1-len(new&held)/len(new) if held else 1.0
                turns.append(f)
                cost=f*(tax+2*slippage)     # 매도세(매도측)+슬리피지(양측). 수수료 0.
                held=new
        names=[c for c in held if pd.notna(cur.get(c))]
        if not names: continue
        g=cur[names].mean()
        uvalid=[c for c in univ if pd.notna(cur.get(c))]
        gross.append(g); net.append(g-cost); ew.append(cur[uvalid].mean()); kept.append(t)
    if len(net)<12: return None
    gC,gS=stats(gross); nC,nS=stats(net); eC,eS=stats(ew)
    turnover_yr=(np.mean(turns) if turns else 0)*(12/H)
    return dict(H=H, n=len(net), turnover_yr=round(turnover_yr,2),
                gross_cagr=round(gC*100,1), net_cagr=round(nC*100,1), net_sharpe=round(nS,2),
                ew_cagr=round(eC*100,1), vs_ew=round((nC-eC)*100,1))

def run(kind, topn=200, tax=0.0015, slippage=0.002045):
    px,rets=load_panel(); mcap=load_mcap()
    print("="*82)
    print(f"개인화 재검토 — 신호 '{kind}' · 다올 비용(수수료0·세금 {tax*100:.2f}%·슬리피지 {slippage*100:.2f}%/편도)")
    print("="*82)
    print(f"  {'보유기간':<8}{'회전/년':>8}{'gross CAGR':>12}{'순 CAGR':>10}{'순Sharpe':>9}{'EW':>7}{'순−EW':>8}")
    rows=[]
    for H,lab in [(1,"월"),(3,"분기"),(6,"반기"),(12,"연")]:
        r=backtest(kind,H,px,rets,mcap,topn,tax,slippage)
        if r:
            rows.append((lab,r))
            print(f"  {lab:<8}{r['turnover_yr']:>7.1f}x{r['gross_cagr']:>11.1f}%{r['net_cagr']:>9.1f}%{r['net_sharpe']:>9.2f}{r['ew_cagr']:>6.1f}%{r['vs_ew']:>+7.1f}%")
    # 판정
    best=max(rows,key=lambda x:x[1]['vs_ew']) if rows else None
    print("\n"+"-"*82)
    if best and best[1]['vs_ew']>0:
        print(f"  판정: 🟢 '{best[0]}' 보유에서 순−EW {best[1]['vs_ew']:+.1f}%p → 회전 낮추면 EW 상회. 재검토 가치 있음(관문2 통과 후보).")
    else:
        print(f"  판정: ⚠️ 어느 보유기간도 EW 상회 못함 → 회전만 낮춰선 구제 불가(신호가 회전에 종속 or gross부터 약함).")
    if kind=="seasonal":
        print("  해설: 계절 신호는 '매달 다름' → 오래 들면 신호가 소멸. 회전을 낮추는 순간 엣지도 사라진다.")
    print("  ⚠️ 검증용. 실현손익 아님. 투자자문 아님·책임 본인.")
    return rows

def classify(kind, rows):
    """(A)신호없음 / (B)관찰(구제불가) / 무기후보(거래가능) 자동 분류."""
    monthly=next((r[1] for r in rows if r[0]=="월"), None)
    if not monthly: return None
    best=max(rows,key=lambda x:x[1]['vs_ew'])
    gross_beats = monthly['gross_cagr']>monthly['ew_cagr']   # 관문1 근사(gross가 EW 상회)
    net_beats   = best[1]['vs_ew']>0                          # 관문2(다올 비용후 EW 상회)
    if net_beats:
        cls, verdict = "무기후보", f"{best[0]} 보유에서 순−EW {best[1]['vs_ew']:+.1f}%p (거래가능·활용대상)"
    elif gross_beats:
        cls, verdict = "B_관찰", "gross는 EW 상회하나 비용후 미달(회전종속/구제불가) — 관찰"
    else:
        cls, verdict = "A_신호없음", "gross부터 EW 미달 — 영구 폐기"
    return dict(전략=kind, 최적보유=best[0], gross_cagr=monthly['gross_cagr'],
                순cagr_다올=best[1]['net_cagr'], ew_cagr=monthly['ew_cagr'],
                순vs_ew=best[1]['vs_ew'], 관문1_gross신호=bool(gross_beats),
                관문2_거래가능=bool(net_beats), 분류=cls, 판정=verdict)

def write_registry(records, date):
    """무기후보_등록부.csv 자동 upsert — 실제 수익 나는 (B)를 추후 무기로 축적."""
    import csv
    path=os.path.join(BASE,"무기후보_등록부.csv")
    cols=["날짜","전략","분류","최적보유","gross_cagr","순cagr_다올","ew_cagr","순vs_ew","관문1_gross신호","관문2_거래가능","판정"]
    existing=[]
    if os.path.exists(path):
        with open(path,encoding="utf-8") as f:
            existing=[r for r in csv.DictReader(f)]
    keys={r["전략"] for r in records}
    existing=[r for r in existing if r.get("전략") not in keys]   # 같은 전략은 최신으로 교체
    for r in records:
        existing.append({"날짜":date, **{k:r.get(k) for k in ["전략","분류","최적보유","gross_cagr","순cagr_다올","ew_cagr","순vs_ew","관문1_gross신호","관문2_거래가능","판정"]}})
    order={"무기후보":0,"B_관찰":1,"A_신호없음":2}
    existing.sort(key=lambda r: order.get(r.get("분류"),9))
    with open(path,"w",newline="",encoding="utf-8") as f:
        w=csv.DictWriter(f,fieldnames=cols); w.writeheader()
        for r in existing: w.writerow(r)
    return path, existing

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--signal",default="all",choices=["seasonal","mom12","lowvol","all"])
    ap.add_argument("--topn",type=int,default=200); ap.add_argument("--tax",type=float,default=0.002)
    ap.add_argument("--slippage",type=float,default=0.0005)
    ap.add_argument("--date",default=None,help="등록 날짜(기본 오늘)")
    a=ap.parse_args()
    kinds=["seasonal","mom12","lowvol"] if a.signal=="all" else [a.signal]
    allres={}; records=[]
    for k in kinds:
        rows=run(k,a.topn,a.tax,a.slippage); allres[k]=[{**r[1],"보유":r[0]} for r in rows]
        c=classify(k,rows)
        if c: records.append(c)
        print()
    json.dump(allres,open(os.path.join(BASE,"재검토_보유기간_결과.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2)
    # ★ 자동 반영: 무기후보 등록부
    if records:
        import datetime as _dt
        date=a.date or _dt.date.today().isoformat()
        path,reg=write_registry(records,date)
        print("="*82); print("★ 무기후보 등록부 자동 반영 →", os.path.basename(path))
        for r in reg:
            mark={"무기후보":"🟢","B_관찰":"🟡","A_신호없음":"⚪"}.get(r["분류"],"·")
            print(f"  {mark} {r['전략']:<10} [{r['분류']:<9}] 최적 {r['최적보유']:<4} 순−EW {r['순vs_ew']:>+5}%p · {r['판정']}")
    print("\n저장: 재검토_보유기간_결과.json · 무기후보_등록부.csv")

if __name__=="__main__": main()
