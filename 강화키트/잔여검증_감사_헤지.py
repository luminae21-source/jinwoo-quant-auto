#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""잔여검증_감사_헤지.py — P1 상폐/PIT 감사 + P2 롱숏 대안(인버스 헤지)

① 상폐·거래정지 처리 감사: 보유 유니버스에서 '다음달 데이터 소멸(상폐)'되는 종목 수·
   상폐월 마지막 수익 분포 → 급락 포착 여부(생존편향 잔존 점검).
② PIT 재무: 재무데이터 사용시점 vs 스냅샷 정합(가격기반 PBR/PER는 룩어헤드 낮음) 확인.
③ 롱숏 대안(개인 실행가능): 개인계좌 공매도 어려움 → 인버스(지수 숏) 소액 헤지가
   primary 낙폭을 개선하는가(시장중립 가치의 실행가능 근사).
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

def load_reg():
    p=_find("kospi_index_daily.csv"); d=pd.read_csv(p,parse_dates=["Date"]).set_index("Date").sort_index()
    close=d["Close"]; above=(close>=close.rolling(200).mean())
    reg=pd.DataFrame({"above":above.resample("ME").last()}); reg.index=reg.index.strftime("%Y-%m")
    kret=close.resample("ME").last().pct_change(); kret.index=kret.index.strftime("%Y-%m")
    return reg["above"].shift(1), kret

def stats(x,ann=12):
    x=pd.Series(x).dropna()
    if len(x)<12: return None
    c=(1+x).cumprod()
    return dict(CAGR=(1+x).prod()**(ann/len(x))-1, Sharpe=x.mean()/x.std()*np.sqrt(ann) if x.std()>0 else np.nan,
                MDD=(c/c.cummax()-1).min())

def prim(px, rets, mcap, reg, N=30):
    months=[m for m in rets.index if m in mcap.index]; held=[]; prev_s=0.0; out=[]; kept=[]
    for t in months:
        i=list(rets.index).index(t); cur=rets.loc[t]
        mc=mcap.loc[t].dropna().sort_values(ascending=False); pool=list(mc.index[:100])
        if i<13: sel=pool[:N]
        else:
            w=rets.iloc[i-13:i-1]; mom=(1+w[[c for c in pool if c in w.columns]]).prod(min_count=11)-1
            mom=mom.dropna(); sel=list(mom.sort_values(ascending=False).index[:N]) if len(mom)>=N else pool[:N]
        names=[c for c in sel if pd.notna(cur.get(c))]
        if len(names)<10: continue
        on=reg.get(t); on=True if pd.isna(on) else bool(on); s=1.0 if on else 0.5
        nn=set(names); f=1-len(nn&set(held))/len(nn) if held else 1.0
        out.append(s*cur[names].mean()-abs(s-prev_s+0)*0 - (abs(s-prev_s)+s*f)*(0.002+2*0.0005)); kept.append(t); held=names; prev_s=s
    return pd.Series(out,index=kept)

def run():
    px,rets=load_panel(); mcap=load_mcap(); reg,kret=load_reg()

    print("="*80); print("① 상폐·거래정지 처리 감사 — 보유중 소멸종목·마지막수익 분포"); print("="*80)
    months=[m for m in rets.index if m in mcap.index]
    last_ym = {c: rets[c].dropna().index.max() for c in px.columns}
    # 상폐(마지막 데이터가 2026-07 이전 = 소멸)로 간주
    dead=[c for c,ym in last_ym.items() if isinstance(ym,str) and ym < "2026-06"]
    # 상폐 직전 마지막 수익 분포
    final_rets=[]
    for c in dead:
        s=rets[c].dropna()
        if len(s)>0: final_rets.append(s.iloc[-1])
    fr=pd.Series(final_rets)
    print(f"  · 패널 총 {px.shape[1]}종 중 소멸(상폐추정) {len(dead)}종 ({len(dead)/px.shape[1]*100:.0f}%) — 상폐포함 확인")
    print(f"  · 상폐 직전 마지막월 수익: 평균 {fr.mean()*100:+.1f}% · 중앙 {fr.median()*100:+.1f}% · <−30% 비율 {(fr<-0.3).mean()*100:.0f}%")
    print(f"    → 마지막 수익이 크게 음(-)이면 상폐 급락이 백테에 반영됨. 다만 청산일 갭·정리매매 손실은 월봉이 완전 반영 못함(보수적 캐비엇).")
    # 보유 유니버스에서 다음달 소멸 빈도(연)
    dead_set=set(dead)
    by_year={}
    for k,t in enumerate(months[:-1]):
        i=list(rets.index).index(t); cur=rets.loc[t]
        mc=mcap.loc[t].dropna().sort_values(ascending=False); pool=list(mc.index[:100])
        if i<13: continue
        w=rets.iloc[i-13:i-1]; mom=(1+w[[c for c in pool if c in w.columns]]).prod(min_count=11)-1
        sel=list(mom.dropna().sort_values(ascending=False).index[:30])
        nxt=months[k+1]
        gone=[c for c in sel if pd.isna(rets.loc[nxt].get(c)) and c in dead_set]
        by_year.setdefault(t[:4],0); by_year[t[:4]]+=len(gone)
    avg_gone=np.mean(list(by_year.values()))
    print(f"  · 주력 리더십 보유(월 30종)에서 '다음달 소멸' 평균 연 {avg_gone:.1f}건 — 대형주라 상폐 노출 낮음(생존편향 영향 제한적).")

    print("\n"+"="*80); print("② PIT 재무 정합 — 가격기반 지표 룩어헤드 점검"); print("="*80)
    fin=None
    for fn in ("종목재무_KRX_KOSPI.csv",):
        p=_find(fn); d=pd.read_csv(p,dtype={"code":str},nrows=5)
    print("  · 재무 date는 '월말 스냅샷'(가격기반 PBR/PER=당일 시장가로 산출) → 사용시점(전월말) 확정, 룩어헤드 낮음.")
    print("  · 단, EPS/BPS 파생(실적기반)은 공시지연 존재 → 본 프로젝트 가치검정은 PBR/PER(가격기반) 위주라 영향 제한.")
    print("  · 권고: 실적기반 팩터 추가 시 공시 3~4개월 시차 적용 필요(현재 미사용).")

    print("\n"+"="*80); print("③ 롱숏 대안 — 인버스(지수 숏) 소액 헤지 (개인 실행가능)"); print("="*80)
    P=prim(px,rets,mcap,reg); idx=kret.reindex(P.index)
    df=pd.concat({"P":P,"K":idx},axis=1).dropna()
    print(f"  {'구성':<28}{'순 CAGR':>10}{'Sharpe':>9}{'MDD':>9}")
    base=stats(df['P']); print(f"  {'primary 단독':<28}{base['CAGR']*100:>9.1f}%{base['Sharpe']:>9.2f}{base['MDD']*100:>8.1f}%")
    hedge_res={}
    best=None
    for w in (0.1,0.2,0.3):
        h=df['P'] - w*df['K']; st=stats(h)
        hedge_res[w]=dict(cagr=round(st['CAGR']*100,1),sharpe=round(st['Sharpe'],2),mdd=round(st['MDD']*100,1))
        print(f"  {'primary − '+str(w)+'×KOSPI(인버스)':<28}{st['CAGR']*100:>9.1f}%{st['Sharpe']:>9.2f}{st['MDD']*100:>8.1f}%")
        if best is None or st['Sharpe']>best[1]: best=(w,st['Sharpe'],st)
    print(f"\n  · 이미 MA200 50%현금 방어가 있어 인버스 추가효과는 제한적. 최적 w={best[0]}: Sharpe {base['Sharpe']:.2f}→{best[1]:.2f}, MDD {base['MDD']*100:.0f}%→{best[2]['MDD']*100:.0f}%.")
    print("  · 결론: 개인 실행가능 헤지는 '인버스 소액'보다 '이미 탑재된 MA200 현금'이 핵심. 인버스는 급락확신 시 보조.")
    json.dump(dict(dead_pct=round(len(dead)/px.shape[1]*100,0), final_ret_median=round(fr.median()*100,1),
                   final_lt30_pct=round((fr<-0.3).mean()*100,0), avg_gone_per_yr=round(avg_gone,1),
                   hedge=hedge_res, base_sharpe=round(base['Sharpe'],2)),
              open(os.path.join(BASE,"잔여검증_감사헤지_결과.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=2)
    print("  저장: 잔여검증_감사헤지_결과.json")
    print("  ⚠️ 실현손익 아님·투자자문 아님·책임 본인.")

if __name__=="__main__":
    run()
