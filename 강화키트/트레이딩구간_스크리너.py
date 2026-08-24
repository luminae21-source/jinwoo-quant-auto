#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""트레이딩구간_스크리너.py — 현재 유니버스 30종의 '진입 가능 구간' 분류 (일봉)

과열 명단을 추격하지 않고, 각 종목이 지금 어느 국면인지 일봉으로 분류:
  · 추세: 종가 vs MA200(장기추세)·MA50(중기)·MA20(단기)
  · 이격: MA20 대비 % (양수 클수록 과확장=추격 위험, 음수/근접=눌림목)
  · 되돌림: 최근 60일 고점 대비 하락률(%)
  · ATR(14) 기반 손절 거리

분류:
  🟢 매수가능(눌림목)  — MA200 위(상승추세) & MA50 위 & MA20 이격 ≤ +8%(과확장 아님)
  🟡 관망(과확장)      — MA200·MA50 위지만 MA20 이격 > +8% (되돌림 기다림)
  🔴 회피(추세이탈)    — MA50 아래 또는 MA200 아래 (추세 훼손, 반등 확인 전 보류)
매수존/손절: 눌림목은 MA20~MA50 구간 매수, 손절 = 최근고점 − 2.5·ATR 또는 MA50 하향.
⚠️ 기계적 기술적 분류. 진입확정 아님·실현손익 아님·투자자문 아님·책임 본인.
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

NAMES = {"353200":"대덕전자","000660":"SK하이닉스","402340":"SK스퀘어","298040":"효성중공업","005930":"삼성전자",
 "240810":"원익IPS","005935":"삼성전자우","034730":"SK","006400":"삼성SDI","000150":"두산","011070":"LG이노텍",
 "006800":"미래에셋증권","032830":"삼성생명","005380":"현대차","042700":"한미반도체","278470":"에이피알",
 "007660":"이수페타시스","086520":"에코프로","307950":"현대오토에버","036930":"주성엔지니어링","012330":"현대모비스",
 "004170":"신세계","028260":"삼성물산","006260":"LS","267260":"HD현대일렉트릭","277810":"레인보우로보틱스",
 "034020":"두산에너빌리티","267250":"HD현대","950160":"코오롱티슈진","028050":"삼성E&A"}

def _find(fn):
    for d in (BASE, os.path.dirname(BASE), os.getcwd()):
        p=os.path.join(d,fn)
        if os.path.exists(p): return p
    return None

def atr(df,n=14):
    h,l,c=df["high"],df["low"],df["close"]; pc=c.shift(1)
    tr=pd.concat([h-l,(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/n,adjust=False).mean()

def run():
    p=_find("_일봉_현재30.csv")
    d=pd.read_csv(p,dtype={"code":str}); d["code"]=d["code"].str.zfill(6); d["date"]=pd.to_datetime(d["date"])
    rows=[]
    for code,g in d.groupby("code"):
        g=g.sort_values("date")
        if len(g)<60: continue
        c=g["close"]; last=c.iloc[-1]
        ma20=c.rolling(20).mean().iloc[-1]; ma50=c.rolling(50).mean().iloc[-1]
        ma200=c.rolling(200).mean().iloc[-1] if len(g)>=200 else c.rolling(len(g)).mean().iloc[-1]
        a=atr(g).iloc[-1]
        hh60=c.iloc[-60:].max(); dd60=(last/hh60-1)*100         # 최근60일 고점 대비
        gap20=(last/ma20-1)*100 if pd.notna(ma20) else np.nan   # MA20 이격
        above200 = last>ma200; above50 = last>ma50 if pd.notna(ma50) else False
        # 분류
        if not above200 or not above50:
            cls="🔴 회피(추세이탈)"; zone="반등·MA50 회복 확인 후 재검토"; stop="-"
        elif gap20 > 8:
            cls="🟡 관망(과확장)"; zone=f"MA20({ma20:,.0f})까지 되돌림 대기"; stop=f"MA50({ma50:,.0f}) 하향"
        else:
            cls="🟢 매수가능(눌림목)"; zone=f"{ma50:,.0f}~{ma20:,.0f} (MA50~MA20)"; stop=f"{hh60-2.5*a:,.0f} (고점-2.5ATR) 또는 MA50 하향"
        rows.append(dict(code=code,name=NAMES.get(code,code),last=last,ma20=ma20,ma50=ma50,ma200=ma200,
            gap20=gap20,dd60=dd60,atr=a,cls=cls,zone=zone,stop=stop,above200=above200,above50=above50,hh60=hh60))
    df=pd.DataFrame(rows)
    order={"🟢":0,"🟡":1,"🔴":2}
    df["_o"]=df["cls"].str[0].map(order)
    df=df.sort_values(["_o","gap20"])
    print("="*104)
    print("현재 유니버스 30종 — 트레이딩 구간 분류 (일봉, 2026-07-23 기준)")
    print("="*104)
    print(f"  {'종목':<14}{'종가':>10}{'MA20이격':>9}{'60일고점대비':>11}{'분류':<16} 매수존 / 손절")
    for _,r in df.iterrows():
        print(f"  {r['name']:<14}{r['last']:>10,.0f}{r['gap20']:>8.1f}%{r['dd60']:>10.1f}%  {r['cls']:<16} {r['zone']}  |  {r['stop']}")
    n_g=(df['_o']==0).sum(); n_y=(df['_o']==1).sum(); n_r=(df['_o']==2).sum()
    print("\n  ── 요약 ──")
    print(f"  🟢 매수가능(눌림목) {n_g}종 · 🟡 관망(과확장) {n_y}종 · 🔴 회피(추세이탈) {n_r}종")
    print(f"  · 지금은 KOSPI 급락(정점 −26%) 국면 → 🟢라도 분할·소량, 🔴는 반등 확인까지 보류.")
    print(f"  · 실전: 🟢 중 리스크예산(1%/트레이드)으로 5~7종. 손절선 이탈 시 기계적 청산(매도규칙_라우터 정합).")
    print("  ⚠️ 기계적 기술적 분류. 진입확정 아님·실현손익 아님·투자자문 아님·책임 본인.")
    out=df.drop(columns=["_o"]).round(0)
    out.to_csv(os.path.join(BASE,"트레이딩구간_현재.csv"),index=False,encoding="utf-8-sig")
    json.dump(dict(green=int(n_g),yellow=int(n_y),red=int(n_r),
        rows=[{k:(round(v,1) if isinstance(v,float) else v) for k,v in r.items() if k!='_o'} for r in df.to_dict('records')]),
        open(os.path.join(BASE,"트레이딩구간_결과.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2,default=str)
    print("  저장: 트레이딩구간_현재.csv · 트레이딩구간_결과.json")
    return df

if __name__=="__main__":
    run()
