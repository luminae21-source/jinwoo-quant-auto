#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""계절순환_교차검정_30년.py — 횡단면 계절성 '깨끗한' 검정 (진우 직관의 진짜 승부처)

1차 검정(계절순환_교차검정.py)이 2/4로 취약했다(생존편향 데이터·비용無). 이 버전은 4개 조건 반영:
  ① 상폐포함 30년 패널  (_월봉종가캐시_KOSPI+KOSDAQ.csv, 1996~2026, ~5,000종목)  → 생존편향 제거
  ② 거래비용 차감        (월간 회전율 × 왕복비용)
  ③ 섹터 순환            (섹터 EW 계절 로테이션 별도 검정)
  ④ 오버레이 가중        (본체 EW 위 작은 틸트 w로 증분 확인)
  + PIT 시총 필터(종목시총_30년.csv, 매월 상위 N종만) → 미세주 유동성 아티팩트 제거

사전등록 게이트(결과 보기 전 고정 — 재-스펙 금지):
  ① 롱숏(비용후) t ≥ 2.3 & 양(+)   ② OOS 전·후반 부호 유지
  ③ 최고 3개월 제거 후 t ≥ 1.5     ④ 롱온리 상위분위(비용후) CAGR > EW-유니버스
  → 통과=정식 팩터 편입 후보. 미통과=기각 유지(직관은 매력적이나 데이터 미지지).

사용: py 계절순환_교차검정_30년.py [--topn 200] [--cost 0.005] [--overlay-w 0.2]
⚠️ 검증용. 실현손익 아님. 투자자문 아님·책임 본인.
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
    """상폐포함 KOSPI+KOSDAQ 월봉 → wide 월수익(ym × code)."""
    frames=[]
    for fn in ("_월봉종가캐시_KOSPI.csv","_월봉종가캐시_KOSDAQ.csv"):
        p=_find(fn)
        if p:
            d=pd.read_csv(p,dtype={"code":str}); d["code"]=d["code"].str.zfill(6); frames.append(d)
    allc=pd.concat(frames,ignore_index=True)
    wide=allc.pivot_table(index="ym",columns="code",values="close",aggfunc="last").sort_index()
    rets=wide.pct_change()
    rets=rets.mask(rets.abs()>1.0)   # 액면분할·오류 클리핑
    return rets

def load_mcap():
    """PIT 시총 wide(ym × code)."""
    p=_find("종목시총_30년.csv")
    if not p: return None
    d=pd.read_csv(p,dtype={"code":str}); d["code"]=d["code"].str.zfill(6)
    d["ym"]=pd.to_datetime(d["date"]).dt.strftime("%Y-%m")
    return d.pivot_table(index="ym",columns="code",values="mcap",aggfunc="last")

def load_sector():
    m={}
    for fn in ("liquidity_sector.csv","kosdaq_industry.csv"):
        p=_find(fn)
        if p:
            d=pd.read_csv(p,dtype={"code":str})
            if "sector" in d.columns:
                for _,r in d.iterrows():
                    s=r["sector"]
                    if isinstance(s,str) and s.strip(): m[str(r["code"]).zfill(6)]=s.strip()
    return m

def tstat(x):
    x=pd.Series(x).dropna()
    return float(x.mean()/(x.std()/np.sqrt(len(x)))) if len(x)>2 and x.std()>0 else np.nan
def cagr(x,ann=12):
    x=pd.Series(x).dropna(); return float((1+x).prod()**(ann/len(x))-1) if len(x)>0 else np.nan
def sharpe(x,ann=12):
    x=pd.Series(x).dropna(); return float(x.mean()/x.std()*np.sqrt(ann)) if x.std()>0 else np.nan
def mdd(x):
    c=(1+pd.Series(x).dropna()).cumprod(); return float((c/c.cummax()-1).min())

def run(topn=200, cost=0.005, overlay_w=0.2, minyears=3):
    rets=load_panel(); mcap=load_mcap(); sec=load_sector()
    months=rets.index
    # 결과 누적
    ls=[]; tq=[]; ewU=[]; kept=[]
    prev_top=set(); prev_bot=set(); to_top=[]; to_bot=[]
    for t in months:
        m=int(t.split("-")[1])
        prior=rets[(rets.index.str[5:7]==f"{m:02d}") & (rets.index<t)]
        if len(prior)<minyears: continue
        # PIT 유동 유니버스: 그달 시총 상위 topn
        if mcap is not None and t in mcap.index:
            mc=mcap.loc[t].dropna()
            univ=set(mc.sort_values(ascending=False).head(topn).index)
        else:
            univ=set(rets.columns)
        sig=prior.mean(axis=0,skipna=True); cur=rets.loc[t]
        valid=[c for c in univ if c in sig.index and pd.notna(sig.get(c)) and pd.notna(cur.get(c))]
        if len(valid)<max(30,topn//4): continue
        sig2=sig[valid]; cur2=cur[valid]
        q=pd.qcut(sig2.rank(method="first"),5,labels=False)
        topN=set(sig2.index[q==4]); botN=set(sig2.index[q==0])
        gtop=cur2[list(topN)].mean(); gbot=cur2[list(botN)].mean()
        # 회전율(교체 비율)
        f_top=1-len(topN&prev_top)/len(topN) if prev_top else 1.0
        f_bot=1-len(botN&prev_bot)/len(botN) if prev_bot else 1.0
        prev_top,prev_bot=topN,botN
        ntop=gtop - f_top*cost                     # 롱온리 비용후
        nls =(gtop-gbot) - (f_top+f_bot)*cost      # 롱숏 비용후
        ls.append(nls); tq.append(ntop); ewU.append(cur2.mean()); kept.append(t)
        to_top.append(f_top)
    S=pd.Series(ls,index=kept); TQ=pd.Series(tq,index=kept); EW=pd.Series(ewU,index=kept)
    n=len(S)
    print("="*76); print("횡단면 계절성 — 깨끗한 30년 검정 (비용후)"); print("="*76)
    print(f"  패널: 상폐포함 KOSPI+KOSDAQ {rets.shape[1]}종 · 유동 상위 {topn}종/월 · 비용 왕복 {cost*100:.1f}% · 회전 평균 {np.mean(to_top)*100:.0f}%")
    print(f"  구간 {kept[0]} ~ {kept[-1]} · 유효 {n}개월")
    # 게이트
    t_ls=tstat(S); g1=(t_ls>=2.3 and S.mean()>0)
    half=n//2; t1=tstat(S.iloc[:half]); t2=tstat(S.iloc[half:])
    g2=(S.iloc[:half].mean()>0 and S.iloc[half:].mean()>0)
    Sd=S.sort_values(ascending=False).iloc[3:]; t_d=tstat(Sd); g3=(t_d>=1.5 and Sd.mean()>0)
    c_tq=cagr(TQ); c_ew=cagr(EW); g4=(c_tq>c_ew)
    print(f"\n  ① 롱숏(비용후): 월 {S.mean()*100:+.2f}% (연 {S.mean()*12*100:+.1f}%) · t={t_ls:.2f}  → {'PASS' if g1 else 'FAIL'}")
    print(f"  ② OOS 전반 t={t1:.2f} · 후반 t={t2:.2f}  → {'PASS' if g2 else 'FAIL'}")
    print(f"  ③ 최고3개월 제거 t={t_d:.2f}  → {'PASS' if g3 else 'FAIL'}  [지수 할로윈 죽인 테스트]")
    print(f"  ④ 롱온리 CAGR {c_tq*100:.1f}% vs EW-유니버스 {c_ew*100:.1f}%  → {'PASS' if g4 else 'FAIL'}")
    passed=int(g1)+int(g2)+int(g3)+int(g4)

    # ③ 섹터 순환
    sec_line=""
    if sec:
        code2sec=sec
        secs=sorted(set(code2sec.values()))
        # 섹터 EW 월수익
        colsec={c:code2sec.get(c) for c in rets.columns if code2sec.get(c)}
        secret=pd.DataFrame(index=rets.index)
        by={}
        for c,s in colsec.items(): by.setdefault(s,[]).append(c)
        for s,cs in by.items():
            if len(cs)>=3: secret[s]=rets[cs].mean(axis=1,skipna=True)
        sret=[]; skept=[]
        for t in secret.index:
            m=int(t.split("-")[1]); prior=secret[(secret.index.str[5:7]==f"{m:02d}")&(secret.index<t)]
            if len(prior)<minyears: continue
            sig=prior.mean(axis=0); cur=secret.loc[t]
            valid=[s for s in secret.columns if pd.notna(sig.get(s)) and pd.notna(cur.get(s))]
            if len(valid)<6: continue
            k=max(2,len(valid)//2); top=sig[valid].sort_values(ascending=False).head(k).index
            sret.append(cur[top].mean()-cur[valid].mean()); skept.append(t)
        SR=pd.Series(sret,index=skept)
        sec_line=f"섹터 순환(상위½ − 전체): 월 {SR.mean()*100:+.2f}% · t={tstat(SR):.2f} ({len(SR)}개월)"

    # ④ 오버레이
    core=EW; over=core + overlay_w*S
    ov_line=f"오버레이(EW + {overlay_w}×롱숏): Sharpe {sharpe(core):.2f}→{sharpe(over):.2f} · CAGR {cagr(core)*100:.1f}%→{cagr(over)*100:.1f}% · MDD {mdd(core)*100:.1f}%→{mdd(over)*100:.1f}%"

    print(f"\n  [추가] {sec_line}")
    print(f"  [추가] {ov_line}")
    print("\n"+"-"*76)
    if passed==4: v="✅ 4/4 통과(비용후·상폐포함) — 정식 팩터 편입 후보. 사전등록해 본체 오버레이로 소액 검증 권고."
    elif g1 and g3: v=f"🟡 {passed}/4 — 핵심(유의+이상치강건) 통과. 조건부 관찰 후보로 격상."
    else: v=f"⚠️ {passed}/4 — 깨끗한 데이터에서도 미통과(특히 ③ 이상치). 직관은 실재하나 강건성 부족 → 기각 유지, 오버레이만 소액 관찰."
    print("  판정:",v)
    print("  ⚠️ 회전비용·유동성 가정 민감. 실현손익 아님. 투자자문 아님·책임 본인.")
    res=dict(topn=topn,cost=cost,n=n,panel_stocks=int(rets.shape[1]),
             ls_t=round(t_ls,2),ls_ann_pct=round(S.mean()*12*100,2),
             oos_t=[round(t1,2),round(t2,2)],drop3_t=round(t_d,2),
             topq_cagr=round(c_tq*100,2),ew_cagr=round(c_ew*100,2),
             sector=sec_line,overlay=ov_line,
             gates=dict(g1=bool(g1),g2=bool(g2),g3=bool(g3),g4=bool(g4)),passed=passed)
    json.dump(res,open(os.path.join(BASE,"계절순환_30년_결과.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2)
    print("  저장: 계절순환_30년_결과.json")
    return res

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--topn",type=int,default=200); ap.add_argument("--cost",type=float,default=0.005)
    ap.add_argument("--overlay-w",type=float,default=0.2); ap.add_argument("--minyears",type=int,default=3)
    a=ap.parse_args(); run(a.topn,a.cost,a.overlay_w,a.minyears)

if __name__=="__main__": main()
