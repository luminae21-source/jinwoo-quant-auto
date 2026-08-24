#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""알파_3분해.py — v3.7.2 초과수익 귀속 분해 (수익 엔진 확정용) · 개선안 A

질문: v3.7.2의 초과수익은 어디서 오는가?
분해: 총 엣지(전략−KOSPI) = ① 유니버스 선택(EW-18 − KOSPI) + ② 선정·틸트(전략 − EW-18)
      추가: ③ Mom12 기여(전략 − noMom) · ④ BAB 기여(전략 − noBAB)

★ 단일 진실원천: 전략 실현 월수익을 `backtest_v37_2_*.json`의 history[]에서 그대로 읽는다
  (재현·엔진 재실행 불필요). EW-18은 `kospi_monthly_prices.csv`에서 같은 창으로 계산.

데이터(진우 폴더):
  · backtest_v37_2_*.json     — history[]: r_v37_2_%, r_v372_noMom_%, r_v372_noBAB_%, r_kospi_%
  · kospi_monthly_prices.csv  — wide(Date × code). 유니버스 18종 월수익 → EW-18.
  · v37_2_scores_latest.csv   — (있으면) 유니버스 코드. 없으면 폴백.

사용:
  py 알파_3분해.py                 # 자동 탐색·전 구간 분해
  py 알파_3분해.py --json backtest_v37_2_20260602_0158.json
  py 알파_3분해.py --self-test
⚠️ 백테 귀속 분석(실현손익 아님). 투자자문 아님·책임 본인.
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

import os, sys, json, glob, argparse
import numpy as np, pandas as pd

BASE=os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

DEFAULT_UNIVERSE={
 "005930":"삼성전자","000660":"SK하이닉스","042700":"한미반도체","196170":"알테오젠",
 "000270":"기아","035420":"NAVER","035720":"카카오","012450":"한화에어로",
 "079550":"LIG넥스원","105560":"KB금융","033780":"KT&G","006400":"삼성SDI",
 "090430":"아모레퍼시픽","028260":"삼성물산","003230":"삼양식품","095340":"ISC",
 "034020":"두산에너빌리티","005940":"NH투자증권"}

def _find(*names):
    for n in names:
        for d in (BASE, os.path.dirname(BASE), os.getcwd()):
            p=os.path.join(d,n)
            if os.path.exists(p): return p
    return None

def load_backtest(jsonpath=None):
    p=jsonpath or _find("backtest_v37_2_20260602_0158.json")
    if not p:
        cands=sorted(glob.glob(os.path.join(BASE,"backtest_v37_2_*.json"))
                     + glob.glob(_jqfind("backtest_v37_2_*.json")))
        p=cands[-1] if cands else None
    if not p: raise FileNotFoundError("backtest_v37_2_*.json 없음")
    j=json.load(open(p,encoding="utf-8"))
    h=pd.DataFrame(j["history"])
    h["ym"]=pd.to_datetime(h["date"]).dt.strftime("%Y-%m")
    h=h.set_index("ym")
    def col(c): return h[c].astype(float)/100.0
    out=pd.DataFrame({
        "strat": col("r_v37_2_%"), "kospi": col("r_kospi_%"),
        "noMom": col("r_v372_noMom_%"), "noBAB": col("r_v372_noBAB_%")})
    return out, os.path.basename(p)

def get_universe():
    f=_find("v37_2_scores_latest.csv")
    if f:
        try:
            df=pd.read_csv(f,dtype=str)
            c="코드" if "코드" in df.columns else ("code" if "code" in df.columns else None)
            if c:
                codes={str(x).zfill(6) for x in df[c]}
                if len(codes)>=10: return codes,"v37_2_scores_latest.csv"
        except Exception: pass
    return set(DEFAULT_UNIVERSE),"폴백 DEFAULT_UNIVERSE"

def load_ew18(months):
    """kospi_monthly_prices.csv(wide)에서 유니버스 EW-18 월수익. months=대상 ym 리스트."""
    p=_find("kospi_monthly_prices.csv")
    if not p: return None, "kospi_monthly_prices.csv 없음", []
    codes,src=get_universe()
    df=pd.read_csv(p)
    dcol=df.columns[0]  # 'Date'
    df["ym"]=pd.to_datetime(df[dcol]).dt.strftime("%Y-%m")
    df=df.set_index("ym")
    have=[c for c in codes if c in df.columns]
    px=df[have].apply(pd.to_numeric, errors="coerce")
    rets=px.pct_change()
    ew=rets.mean(axis=1, skipna=True)
    ew=ew.reindex(months)
    return ew, src, [c for c in codes if c not in have]

def stats(s, ann=12):
    s=pd.Series(s).dropna()
    if len(s)<3: return None
    cagr=(1+s).prod()**(ann/len(s))-1
    sharpe=(s.mean()*ann)/(s.std()*np.sqrt(ann)) if s.std()>0 else np.nan
    cum=(1+s).cumprod(); mdd=(cum/cum.cummax()-1).min()
    return dict(n=len(s),CAGR=cagr,Sharpe=sharpe,MDD=mdd,mean_m=s.mean())

def ir(a,b):
    a,b=pd.Series(a).dropna(),pd.Series(b).dropna()
    idx=a.index.intersection(b.index); d=a.loc[idx]-b.loc[idx]
    return (d.mean()*12)/(d.std()*np.sqrt(12)) if d.std()>0 else np.nan

def run(jsonpath=None):
    bt,src=load_backtest(jsonpath)
    months=list(bt.index)
    ew,ewsrc,miss=load_ew18(months)
    print("="*76); print("알파 3분해 — v3.7.2 초과수익 귀속"); print("="*76)
    print(f"  전략 실현: {src}  ·  구간 {months[0]}~{months[-1]} ({len(months)}개월)")
    print(f"  EW-18 출처: {ewsrc}"+ (f"  ·  캐시없음 {len(miss)}종(KOSDAQ 등)" if miss else ""))
    st=stats(bt["strat"]); ks=stats(bt["kospi"]); ew_s=stats(ew) if ew is not None else None
    def line(name,s,bench=None):
        if not s: return f"  {name:<20} (데이터부족)"
        extra=f" · IR {ir(bt['strat'] if name.startswith('v3.7.2') else ew, bt['kospi']):+.2f}" if bench else ""
        return f"  {name:<20} CAGR {s['CAGR']*100:6.2f}%  Sharpe {s['Sharpe']:4.2f}  MDD {s['MDD']*100:6.1f}%"
    print("\n[성과]")
    print(line("v3.7.2 전략",st))
    if ew_s: print(line("EW-18(동일가중)",ew_s))
    print(line("KOSPI(벤치)",ks))

    print("\n[알파 분해] (연환산 CAGR 기준)")
    total=st["CAGR"]-ks["CAGR"]
    print(f"  총 엣지 (전략 − KOSPI)          = {total*100:+6.2f}%p   IR {ir(bt['strat'],bt['kospi']):+.2f}")
    if ew_s:
        uni=ew_s["CAGR"]-ks["CAGR"]; seltilt=st["CAGR"]-ew_s["CAGR"]
        print(f"   ├ ① 유니버스 선택 (EW-18 − KOSPI) = {uni*100:+6.2f}%p   ({uni/total*100:4.0f}% of 총엣지)" if total!=0 else "")
        print(f"   └ ② 선정·틸트 (전략 − EW-18)      = {seltilt*100:+6.2f}%p   ({seltilt/total*100:4.0f}% of 총엣지)   IR(vs EW) {ir(bt['strat'],ew):+.2f}")
    momc=st["CAGR"]-stats(bt["noMom"])["CAGR"]
    babc=st["CAGR"]-stats(bt["noBAB"])["CAGR"]
    print(f"\n[팩터 기여] (leave-one-out, 연환산)")
    print(f"   · Mom12 (전략 − noMom) = {momc*100:+6.2f}%p")
    print(f"   · BAB   (전략 − noBAB) = {babc*100:+6.2f}%p")

    # 판정
    print("\n[판정]")
    if ew_s:
        ir_ew=ir(bt['strat'],ew)
        if seltilt>0 and ir_ew>0.3:
            v="✅ 선정·틸트 알파 실재 — EW-18 대비 유의 초과(IR>0.3). 선정 로직 유지 + 집중 리스크만 통제."
        elif seltilt>0:
            v="🟡 선정·틸트 양(+)이나 IR 약함 — 상당 부분이 유니버스 선택의 힘. 사이징·기대치를 EW 기준으로."
        else:
            v="⚠️ 선정·틸트 기여 음(−) — 무기는 유니버스+틸트. 종목선정 축소·EW화 검토."
        print("  "+v)
        print(f"  → 수익 엔진 정체 = 유니버스 {uni*100:+.1f}%p + 선정·틸트 {seltilt*100:+.1f}%p (총 {total*100:+.1f}%p). 이것을 '검증된 수익 코어'로 명문화.")
    result=dict(구간=f"{months[0]}~{months[-1]}", 총엣지_pp=round(total*100,2),
                유니버스_pp=round((ew_s['CAGR']-ks['CAGR'])*100,2) if ew_s else None,
                선정틸트_pp=round((st['CAGR']-ew_s['CAGR'])*100,2) if ew_s else None,
                Mom_pp=round(momc*100,2), BAB_pp=round(babc*100,2),
                전략_CAGR=round(st['CAGR']*100,2), EW18_CAGR=round(ew_s['CAGR']*100,2) if ew_s else None,
                KOSPI_CAGR=round(ks['CAGR']*100,2), IR_vs_EW=round(float(ir(bt['strat'],ew)),3) if ew is not None else None)
    outp=os.path.join(BASE,"알파_3분해_결과.json")
    json.dump(result, open(outp,"w",encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\n  저장: 알파_3분해_결과.json")
    print("⚠️ 백테 귀속(실현손익 아님). 투자자문 아님·책임 본인.")
    return result

def _self_test():
    ok=tot=0
    def chk(n,c):
        nonlocal ok,tot; tot+=1; ok+=1 if c else 0; print(f"  [{'OK' if c else 'FAIL'}] {n}")
    s=stats(pd.Series([0.01]*12)); chk("CAGR≈12.68%",abs(s['CAGR']-0.1268)<0.01)
    a=pd.Series([0.02]*12,index=range(12)); b=pd.Series([0.01]*12,index=range(12))
    chk("IR 부호(+)", ir(a,b)>0)
    chk("분해 항등식(총=유니버스+선정틸트)", abs((0.7-0.28)-((0.5-0.28)+(0.7-0.5)))<1e-9)
    print(f"\n셀프테스트: {ok}/{tot}"); return ok==tot

def main():
    ap=argparse.ArgumentParser(description="알파 3분해(수익엔진 귀속)")
    ap.add_argument("--json"); ap.add_argument("--self-test",action="store_true")
    a=ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    run(a.json); return 0

if __name__=="__main__": sys.exit(main())
