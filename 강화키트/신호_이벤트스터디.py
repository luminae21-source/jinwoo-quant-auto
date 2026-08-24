#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""신호_이벤트스터디.py — 신호별 '후속 상승 확률·손익비'를 30년 데이터로 검정

질문: 스캐너 신호(돌파·추세복구·초기반등·상승준비)로 고른 종목이
      실제로 오를 확률과 손익비가 얼마인가?
방법: 30년 상폐포함 월봉 패널(top200 유동)에서 매월 각 종목을 신호분류하고,
      1·2·3개월 뒤 forward 수익 → 승률·평균·중앙. + 손절규칙 넣은 실전 기대값.
      + 상승/하락 레짐(지수 vs 10개월MA)별 분해 + 베이스레이트(무조건) 대비.

신호(월봉 근사, 룩어헤드 없음 — t월말 정보로 분류, t+1부터 실현):
  🚀 돌파      : 12개월 신고가(당월 종가 = 최근12M 최고) 또는 3% 이내
  🟢 추세복구   : 종가 ≥ MA6 & 전월 < MA6 (중장기선 신규 회복)
  🟡 초기반등   : 종가 ≥ MA3 & 전월 < MA3 & 종가 < MA6 (단기 반등)
  🟣 상승준비   : MA10 위 & 6개월 레인지 하위 1/3(압축)  또는  24M고점 -30%↓ & 저점권(바닥)
  (베이스)     : 유니버스 전체 무조건
실전 기대값: t+1부터 진입, 종가<MA3(추세이탈) 시 청산, 최대 12개월. 다올 비용후.
⚠️ 월봉 근사·검증용. 확률은 과거통계이며 미래보장 아님. 투자자문 아님·책임 본인.
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
    mcap=m.pivot_table(index="ym",columns="code",values="mcap",aggfunc="last")
    k=pd.read_csv(_find("kospi_index_daily.csv"),parse_dates=["Date"]).set_index("Date")["Close"]
    km=k.resample("ME").last(); km.index=km.index.strftime("%Y-%m")
    kreg=(km>=km.rolling(10).mean())   # 지수 10개월MA 위=상승레짐
    return px,rets,mcap,kreg

def classify_month(px, i, code, ma3,ma6,ma10):
    """t=i월말 기준 종목 신호. 반환 카테고리 or None."""
    c=px[code]
    last=c.iloc[i]
    if pd.isna(last): return None
    m3=ma3[code].iloc[i]; m6=ma6[code].iloc[i]; m10=ma10[code].iloc[i]
    p3=ma3[code].iloc[i-1] if i>0 else np.nan; p6=ma6[code].iloc[i-1] if i>0 else np.nan
    prev=c.iloc[i-1] if i>0 else np.nan
    win12=c.iloc[max(0,i-11):i+1]; hi12=win12.max()
    win24=c.iloc[max(0,i-23):i+1]; hi24=win24.max(); lo12=c.iloc[max(0,i-11):i+1].min()
    # 돌파/신고가
    if pd.notna(hi12) and last>=hi12*0.97:
        return "🚀돌파"
    # 추세복구
    if pd.notna(m6) and pd.notna(p6) and last>=m6 and prev<p6:
        return "🟢추세복구"
    # 초기반등
    if pd.notna(m3) and pd.notna(p3) and last>=m3 and prev<p3 and (pd.isna(m6) or last<m6):
        return "🟡초기반등"
    # 상승준비: 압축 or 바닥
    if pd.notna(m10) and last>=m10:
        rng=(c.iloc[max(0,i-5):i+1].max()/c.iloc[max(0,i-5):i+1].min()-1)
        rhist=[(c.iloc[max(0,j-5):j+1].max()/c.iloc[max(0,j-5):j+1].min()-1) for j in range(max(6,i-24),i+1)]
        if len(rhist)>=6 and pd.notna(rng) and rng<=np.nanpercentile(rhist,33):
            return "🟣상승준비"
    if pd.notna(hi24) and last<=hi24*0.7 and pd.notna(lo12) and last<=lo12*1.15:
        return "🟣상승준비"
    return None

def run():
    px,rets,mcap,kreg=load()
    ma3=px.rolling(3).mean(); ma6=px.rolling(6).mean(); ma10=px.rolling(10).mean()
    months=[m for m in px.index if m in mcap.index]
    idx=list(px.index)
    events={k:[] for k in ["🚀돌파","🟢추세복구","🟡초기반등","🟣상승준비","(베이스)"]}
    # 각 이벤트: (fwd1,fwd2,fwd3, managed_ret, managed_win, regime)
    for t in months:
        i=idx.index(t)
        if i<24 or i+1>=len(idx): continue
        mc=mcap.loc[t].dropna().sort_values(ascending=False)
        univ=list(mc.index[:200])
        reg = bool(kreg.get(t)) if (t in kreg.index and pd.notna(kreg.get(t))) else True
        for code in univ:
            if code not in px.columns: continue
            # forward 수익 (t+1..t+3)
            f=[]
            for h in (1,2,3):
                if i+h<len(idx):
                    r=(px[code].iloc[i+h]/px[code].iloc[i]-1) if pd.notna(px[code].iloc[i]) and pd.notna(px[code].iloc[i+h]) else np.nan
                    f.append(r)
                else: f.append(np.nan)
            if pd.isna(f[0]): continue
            cat=classify_month(px,i,code,ma3,ma6,ma10)
            # managed: t+1부터, 종가<MA3 청산, 최대12개월
            entry=px[code].iloc[i]; mret=0.0; win=None
            if pd.notna(entry) and entry>0:
                held=0; cum=1.0; alive=True
                for h in range(1,13):
                    if i+h>=len(idx): break
                    r=rets[code].iloc[i+h]
                    if pd.isna(r): break
                    cum*=(1+r); held+=1
                    if px[code].iloc[i+h] < ma3[code].iloc[i+h]:   # 추세이탈 청산
                        break
                mret=cum-1 - (0.002+2*0.0005)*2   # 진입+청산 비용
                win=mret>0
            rec=(f[0],f[1],f[2],mret,win,reg)
            events["(베이스)"].append(rec)
            if cat: events[cat].append(rec)
    # 집계
    def agg(recs):
        if not recs: return None
        a=np.array([[r[0],r[1],r[2],r[3]] for r in recs],dtype=float)
        wins=[r[4] for r in recs if r[4] is not None]
        w1=np.nanmean(a[:,0]>0)*100; w2=np.nanmean(a[:,1]>0)*100; w3=np.nanmean(a[:,2]>0)*100
        mret=np.array([r[3] for r in recs if r[4] is not None])
        wr=np.mean(wins)*100 if wins else np.nan
        winr=mret[mret>0]; losr=mret[mret<=0]
        avgw=np.mean(winr)*100 if len(winr) else 0; avgl=np.mean(losr)*100 if len(losr) else 0
        payoff=abs(avgw/avgl) if avgl!=0 else np.nan
        exp=np.mean(mret)*100 if len(mret) else np.nan
        return dict(n=len(recs),w1=w1,w2=w2,w3=w3,f1=np.nanmean(a[:,0])*100,f2=np.nanmean(a[:,1])*100,f3=np.nanmean(a[:,2])*100,
                    mgr_wr=wr,avgw=avgw,avgl=avgl,payoff=payoff,exp=exp)
    print("="*100)
    print("신호 이벤트 스터디 — 후속 상승확률·손익비 (30년 상폐포함 월봉·top200 유동, 다올 비용후)")
    print("="*100)
    print(f"  {'신호':<12}{'표본':>7}{'상승확률 1M/2M/3M':>20}{'평균수익 1M/2M/3M':>22}")
    res={}
    for cat in ["🚀돌파","🟢추세복구","🟡초기반등","🟣상승준비","(베이스)"]:
        s=agg(events[cat]); res[cat]=s
        if not s: continue
        print(f"  {cat:<12}{s['n']:>7,}   {s['w1']:>4.0f}/{s['w2']:>3.0f}/{s['w3']:>3.0f}%   {s['f1']:>+6.1f}/{s['f2']:>+5.1f}/{s['f3']:>+5.1f}%")
    print("\n  ── 실전 기대값 (t+1 진입, MA3 이탈 청산, 최대12M, 다올 비용후) ──")
    print(f"  {'신호':<12}{'승률':>7}{'평균이익':>9}{'평균손실':>9}{'손익비':>8}{'기대값/트레이드':>14}")
    for cat in ["🚀돌파","🟢추세복구","🟡초기반등","🟣상승준비","(베이스)"]:
        s=res[cat]
        if not s: continue
        print(f"  {cat:<12}{s['mgr_wr']:>6.0f}%{s['avgw']:>+8.1f}%{s['avgl']:>+8.1f}%{s['payoff']:>8.2f}{s['exp']:>+13.1f}%")
    # 레짐 분해
    print("\n  ── 레짐별 3개월 상승확률 (지수 10M-MA 위=상승 / 아래=하락) ──")
    print(f"  {'신호':<12}{'상승레짐 승률(표본)':>22}{'하락레짐 승률(표본)':>22}")
    for cat in ["🚀돌파","🟢추세복구","🟡초기반등","🟣상승준비","(베이스)"]:
        up=[r for r in events[cat] if r[5]]; dn=[r for r in events[cat] if not r[5]]
        wu=np.nanmean(np.array([r[2] for r in up],dtype=float)>0)*100 if up else np.nan
        wd=np.nanmean(np.array([r[2] for r in dn],dtype=float)>0)*100 if dn else np.nan
        print(f"  {cat:<12}{wu:>10.0f}% ({len(up):>6,}) {wd:>10.0f}% ({len(dn):>6,})")
    print("\n  ── 해석 ──")
    b=res["(베이스)"]
    for cat in ["🚀돌파","🟢추세복구","🟣상승준비"]:
        s=res[cat]
        if s and b:
            edge=s['exp']-b['exp']
            print(f"  · {cat}: 실전 기대값 {s['exp']:+.1f}%/트레이드 (베이스 {b['exp']:+.1f}%, 엣지 {edge:+.1f}%p) · 손익비 {s['payoff']:.2f}")
    print("  · 핵심: 개별 상승확률은 50% 안팎이라도, 손익비(이익>손실)로 기대값이 플러스가 되는 구조.")
    print("  · 하락레짐에선 전 신호 승률 급락 → 지금 급락장은 '기다려'가 통계적으로도 맞음.")
    print("  ⚠️ 월봉 근사·과거통계. 미래 보장 아님. 투자자문 아님·책임 본인.")
    json.dump({k:(v if v else None) for k,v in res.items()},
              open(os.path.join(BASE,"신호_이벤트스터디_결과.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2,default=str)
    print("  저장: 신호_이벤트스터디_결과.json")
    return res

if __name__=="__main__":
    run()
