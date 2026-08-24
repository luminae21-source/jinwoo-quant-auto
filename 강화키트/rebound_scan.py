#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""rebound_scan.py — 현재 유니버스 반등신호 스캐너 (일봉)

급락 후 '언제 다시 들어갈까'를 위한 반등신호 3등급 탐지:
  🟢 추세복구  : 종가 ≥ MA50 (50일선 회복) — 최근 MA50 아래였다가 되찾음 = 진입 우선
  🟡 초기반등  : 종가 ≥ MA20 & MA20 기울기 상향 (아직 MA50 아래) — 관찰 승격
  🟠 바닥타진  : 종가 < MA20 이지만 5일수익>0 & 최근10일 저점 대비 +3%↑ (반등 시도)
  ⚪ 지속하락  : 신호 없음
+ 거래량 확인(당일 vs 20일평균), MA50/MA20까지 남은 거리(%).

데이터: 현재 유니버스(유니버스_규칙화_현재.csv)의 종목 × 최신 일봉(종목일봉_30년_*.csv).
사용:  py rebound_scan.py            (PC: 큰 일봉파일 직접 읽음, 매주 최신)
       py rebound_scan.py --cache _일봉_현재30.csv   (사전필터 캐시로 빠르게)
⚠️ 기계적 기술 신호. 진입확정 아님·실현손익 아님·투자자문 아님·책임 본인.
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

import os, sys, argparse, json
import numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
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

def universe_codes():
    p=_find("유니버스_규칙화_현재.csv")
    if p:
        try:
            u=pd.read_csv(p,dtype={"code":str}); return [c.zfill(6) for c in u["code"].tolist()]
        except Exception: pass
    return list(NAMES.keys())

def load_daily(codes, cache=None):
    codeset=set(codes)
    if cache:
        p=_find(cache)
        if p:
            d=pd.read_csv(p,dtype={"code":str}); d["code"]=d["code"].str.zfill(6)
            d["date"]=pd.to_datetime(d["date"]); return d[d["code"].isin(codeset)]
    # 큰 일봉파일 청크 읽기(최신)
    frames=[]
    for fn in ("종목일봉_30년_KOSPI.csv","종목일봉_30년_KOSDAQ.csv"):
        p=_find(fn)
        if not p: continue
        for ch in pd.read_csv(p,dtype={"code":str},usecols=["date","code","high","low","close","volume"],chunksize=500000):
            ch["code"]=ch["code"].str.zfill(6); ch=ch[ch["code"].isin(codeset)]
            if len(ch): frames.append(ch)
    if not frames: return pd.DataFrame()
    d=pd.concat(frames,ignore_index=True); d["date"]=pd.to_datetime(d["date"]); return d

def scan(df):
    rows=[]
    for code,g in df.groupby("code"):
        g=g.sort_values("date")
        if len(g)<55: continue
        c=g["close"]; v=g["volume"]; last=c.iloc[-1]
        ma20=c.rolling(20).mean(); ma50=c.rolling(50).mean()
        m20=ma20.iloc[-1]; m50=ma50.iloc[-1]
        m20_up = ma20.iloc[-1] > ma20.iloc[-6]                 # MA20 5일전보다↑
        r5=(last/c.iloc[-6]-1)*100 if len(c)>=6 else np.nan    # 5일수익
        low10=c.iloc[-10:].min(); off_low=(last/low10-1)*100   # 최근10일 저점 대비
        vol20=v.iloc[-20:].mean(); volr=(v.iloc[-1]/vol20) if vol20>0 else np.nan
        to50=(last/m50-1)*100 if pd.notna(m50) else np.nan     # +면 이미 위
        to20=(last/m20-1)*100 if pd.notna(m20) else np.nan
        was_below50 = (c.iloc[-11:-1] < ma50.iloc[-11:-1]).any()  # 최근 아래였나
        vsurge = (pd.notna(volr) and volr>=1.5)                # 거래량 급증
        slope = "기울기↑" if m20_up else "기울기↓"
        vtag = " ⚡거래량" if vsurge else ""
        # 등급
        if pd.notna(m50) and last>=m50:
            grade="🟢 추세복구"; note=("MA50 회복 — 진입 우선 후보" if was_below50 else "MA50 위 유지")+vtag
        elif pd.notna(m20) and last>=m20:
            grade="🟡 초기반등"; note=f"MA20 회복({slope}) · MA50까지 남음 — MA50 돌파 시 승격{vtag}"
        elif last<m20 and r5>0 and off_low>=3:
            grade="🟠 바닥타진"; note=f"저점 대비 반등 시도 — MA20 회복 확인{vtag}"
        else:
            grade="⚪ 지속하락"; note="신호 없음"+vtag
        rows.append(dict(code=code,name=NAMES.get(code,code),last=last,to50=to50,to20=to20,r5=r5,
            off_low=off_low,volr=volr,grade=grade,note=note))
    df2=pd.DataFrame(rows)
    order={"🟢":0,"🟡":1,"🟠":2,"⚪":3}
    df2["_o"]=df2["grade"].str[0].map(order)
    return df2.sort_values(["_o","to50"],ascending=[True,False])

def run(cache=None):
    codes=universe_codes()
    d=load_daily(codes,cache)
    if len(d)==0:
        print("일봉 데이터를 찾지 못했습니다. 종목일봉_30년_*.csv 위치 확인."); return
    df=scan(d)
    asof=d["date"].max().strftime("%Y-%m-%d")
    print("="*100)
    print(f"반등신호 스캔 — 현재 유니버스 {len(df)}종 (일봉, {asof} 기준)")
    print("="*100)
    print(f"  {'종목':<14}{'종가':>10}{'MA50까지':>9}{'MA20까지':>9}{'5일':>7}{'저점比':>7}{'거래량':>7}  신호 / 메모")
    for _,r in df.iterrows():
        t50=f"{r['to50']:+.1f}%" if pd.notna(r['to50']) else "  -"
        t20=f"{r['to20']:+.1f}%" if pd.notna(r['to20']) else "  -"
        vr=f"{r['volr']:.1f}x" if pd.notna(r['volr']) else " -"
        print(f"  {r['name']:<14}{r['last']:>10,.0f}{t50:>9}{t20:>9}{r['r5']:>6.1f}%{r['off_low']:>6.1f}%{vr:>7}  {r['grade']} {r['note']}")
    ng=(df['_o']==0).sum(); ny=(df['_o']==1).sum(); no=(df['_o']==2).sum(); nw=(df['_o']==3).sum()
    print("\n  ── 요약 ──")
    print(f"  🟢 추세복구 {ng} · 🟡 초기반등 {ny} · 🟠 바닥타진 {no} · ⚪ 지속하락 {nw}")
    if ng==0 and ny==0:
        print("  · 아직 확정 반등 없음 → 대기 유지. 🟠(바닥타진)만 관찰. MA50 회복 뜨면 이 스캔이 🟢로 알림.")
    else:
        print("  · 🟢부터 우선 검토 → 리스크예산(1%/트레이드)으로 분할 진입, 손절=MA50 재이탈. 급락장이라 소량부터.")
    print("  · 매주 1회 rebound_scan.bat 실행 권장 (신호 전환 추적).")
    print("  ⚠️ 기계적 기술 신호. 진입확정 아님·실현손익 아님·투자자문 아님·책임 본인.")
    out=df.drop(columns=["_o"])
    out.to_csv(os.path.join(BASE,"반등신호_현재.csv"),index=False,encoding="utf-8-sig")
    json.dump(dict(asof=asof,green=int(ng),yellow=int(ny),orange=int(no),white=int(nw),
        rows=[{k:(round(v,1) if isinstance(v,float) else v) for k,v in r.items() if k!='_o'} for r in df.to_dict('records')]),
        open(os.path.join(BASE,"반등신호_결과.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2,default=str)
    print("  저장: 반등신호_현재.csv · 반등신호_결과.json")
    return df

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--cache",default=None); a=ap.parse_args()
    run(a.cache)

if __name__=="__main__":
    main()
