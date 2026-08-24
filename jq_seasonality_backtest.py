# -*- coding: utf-8 -*-
"""
jq_seasonality_backtest.py — 계절성(Halloween 효과) 검정. **오늘 중 데이터가 가장 좋은 테스트.**

근거: Bouman & Jacobsen (2002, American Economic Review) "The Halloween Indicator: Sell in May and Go Away"
      37개국 중 36개국서 11~4월 수익 >> 5~10월. 후속(Jacobsen-Zhang)은 300년 데이터로 확인.
데이터: kospi_index_daily.csv (1990~, 약 35년 → 오늘 테스트 중 표본 최대).

사전등록(결과 보기 전 고정):
  · **primary = 고전 Halloween**: 11~4월 시장 / 5~10월 현금. (문헌 표준, 우리가 고른 구간 아님)
  · 탐색(secondary) = 진우 변형: 9~4월 / 9~5월. **탐색은 판정 아님**(구간 고르기=fishing 방지).
  · 벤치 = buy&hold. 배당 연 1.8% 보정. 비용 편도 15bp(연 2회 매매).
  · **수익 우선 게이트(고정)**: CAGR ≥ buy&hold − 1.0%p. + Sharpe > bh AND MDD 비악화.
무수정: production·L1 불변. 실행: py jq_seasonality_backtest.py --run
"""
import os, sys, json, argparse, warnings
import numpy as np, pandas as pd
warnings.simplefilter("ignore")
HERE=os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

CFG=dict(DIV_ANNUAL=0.018, COST_ONEWAY=0.0015, RF_ANNUAL=0.030)

def load():
    p=os.path.join(HERE,"kospi_index_daily.csv")
    if not os.path.exists(p): return None
    d=pd.read_csv(p,parse_dates=["Date"]).set_index("Date")["Close"]
    m=d.resample("ME").last()
    r=m.pct_change().dropna() + CFG["DIV_ANNUAL"]/12.0     # 총수익 근사(배당 보정)
    return r

def run_rule(r, months):
    """months = 시장에 있을 달(1~12) 집합. 나머지는 현금(RF)."""
    rf=CFG["RF_ANNUAL"]/12.0
    pos=pd.Series([1.0 if d.month in months else 0.0 for d in r.index], index=r.index)
    s=pos*r + (1-pos)*rf
    s=s - pos.diff().abs().fillna(0)*CFG["COST_ONEWAY"]
    return s

def perf(x):
    x=x.dropna(); n=len(x); cum=(1+x).cumprod()
    return dict(CAGR=round(float((1+x).prod()**(12/max(n,1))-1),4),
                Sharpe=round(float(x.mean()/x.std()*np.sqrt(12)) if x.std()>0 else np.nan,3),
                MDD=round(float((cum/cum.cummax()-1).min()),4), n=n)

def gate(p, pb):
    return dict(수익게이트=bool(p["CAGR"] >= pb["CAGR"]-0.01),
                Sharpe우위=bool(p["Sharpe"]>pb["Sharpe"]),
                MDD비악화=bool(abs(p["MDD"])<=abs(pb["MDD"])))

def run():
    r=load()
    if r is None: return {"err":"kospi_index_daily.csv 없음 → py fetch_kospi_index_daily.py --start 1990"}
    bh=perf(r)
    # 월별 계절성(진단)
    seas=r.groupby(r.index.month).agg(["mean","std","count"])
    seas_tbl={int(m):dict(평균월수익=round(float(seas.loc[m,"mean"]),4), 표본=int(seas.loc[m,"count"])) for m in seas.index}
    # primary: 고전 Halloween(11~4월)
    H=set([11,12,1,2,3,4])
    ph=perf(run_rule(r,H))
    out=dict(표본=dict(개월=len(r), 시작=str(r.index.min().date()), 끝=str(r.index.max().date())),
             월별계절성=seas_tbl,
             buyhold=bh,
             primary_고전Halloween_11to4=dict(perf=ph, 게이트=gate(ph,bh)))
    # secondary(탐색·판정 아님): 진우 변형
    for name,months in [("탐색_9to4",set([9,10,11,12,1,2,3,4])), ("탐색_9to5",set([9,10,11,12,1,2,3,4,5]))]:
        p=perf(run_rule(r,months)); out[name]=dict(perf=p, 게이트=gate(p,bh))
    # ═══ 죽여보기(robustness) — 오늘의 교훈 적용 ═══
    # 반년 수익: Nov~Apr(t년 11월~t+1년 4월) vs May~Oct(t년)
    df=pd.DataFrame({"r":r}); df["y"]=df.index.year; df["m"]=df.index.month
    win_rows=[]
    for y in sorted(df["y"].unique()):
        nov=df[((df["y"]==y)&(df["m"]>=11)) | ((df["y"]==y+1)&(df["m"]<=4))]["r"]
        may=df[(df["y"]==y)&(df["m"]>=5)&(df["m"]<=10)]["r"]
        if len(nov)==6 and len(may)==6:
            win_rows.append(dict(year=int(y), nov_apr=float((1+nov).prod()-1), may_oct=float((1+may).prod()-1)))
    W=pd.DataFrame(win_rows); W["diff"]=W["nov_apr"]-W["may_oct"]
    from math import sqrt
    t_stat=float(W["diff"].mean()/(W["diff"].std()/sqrt(len(W))))
    rb=dict(
        연도수=int(len(W)),
        NovApr_평균=round(float(W["nov_apr"].mean()),4), MayOct_평균=round(float(W["may_oct"].mean()),4),
        차이_평균=round(float(W["diff"].mean()),4), 차이_t값=round(t_stat,2),
        NovApr가_이긴_해=f"{int((W['diff']>0).sum())}/{len(W)}",
    )
    # 위기 제외(1997,1998,2008) — 두 폭락에 의존하나?
    Wx=W[~W["year"].isin([1997,1998,2008])]
    tx=float(Wx["diff"].mean()/(Wx["diff"].std()/sqrt(len(Wx))))
    rb["위기제외(97·98·08)"]=dict(연도수=int(len(Wx)), 차이_평균=round(float(Wx["diff"].mean()),4), t값=round(tx,2),
                                  NovApr가_이긴_해=f"{int((Wx['diff']>0).sum())}/{len(Wx)}")
    # 발표 전후(2002 Bouman-Jacobsen) — 소멸했나?
    for label,sub in [("발표전_1995to2002",W[W["year"]<=2002]), ("발표후_2003to2026",W[W["year"]>=2003])]:
        if len(sub)>2:
            ts=float(sub["diff"].mean()/(sub["diff"].std()/sqrt(len(sub))))
            rb[label]=dict(연도수=int(len(sub)), 차이_평균=round(float(sub["diff"].mean()),4), t값=round(ts,2),
                           NovApr가_이긴_해=f"{int((sub['diff']>0).sum())}/{len(sub)}")
    # 민감도: RF·배당
    sens={}
    for rf_ in [0.01,0.03,0.05]:
        old=CFG["RF_ANNUAL"]; CFG["RF_ANNUAL"]=rf_
        p=perf(run_rule(load(),H)); sens[f"RF{int(rf_*100)}%"]=dict(CAGR=p["CAGR"], 수익게이트=bool(p["CAGR"]>=bh["CAGR"]-0.01))
        CFG["RF_ANNUAL"]=old
    rb["RF민감도"]=sens
    # ★ 핵심: 발표 후(2003~)에도 전략이 buy&hold를 이기나 — 실전 질문
    sub_out={}
    for label,cut in [("전략_2003이후",2003),("전략_2010이후",2010)]:
        rr=r[r.index.year>=cut]
        pb2=perf(rr); ph2=perf(run_rule(rr,H))
        sub_out[label]=dict(buyhold=pb2, halloween=ph2, 게이트=gate(ph2,pb2))
    rb["발표후_전략성과"]=sub_out
    out["죽여보기"]=rb

    # ═══ 부분 틸트: all-or-nothing 대신 비중 조절 ═══
    # 진단(시장 밖 기회비용 > 타이밍 이득)에 대한 직접 처방. 11~4월 100% / 5~10월 W%.
    # 사전등록: **W=50%만 판정 대상.** 25/75%는 탐색(참고).
    def tilt_rule(rr, w):
        rf=CFG["RF_ANNUAL"]/12.0
        pos=pd.Series([1.0 if d.month in H else w for d in rr.index], index=rr.index)
        s=pos*rr + (1-pos)*rf
        return s - pos.diff().abs().fillna(0)*CFG["COST_ONEWAY"]
    def static_rule(rr, w):
        """대조군: 계절 무관하게 **항상 w 비중**(평균 노출 동일). 계절성이 진짜 값을 더하나?"""
        rf=CFG["RF_ANNUAL"]/12.0
        return w*rr + (1-w)*rf
    tilt={}
    for w in [0.25, 0.50, 0.75]:
        avg_w = (1.0 + w)/2.0          # 6개월 100% + 6개월 w → 평균 노출
        row={}
        for label,rr in [("전체_1995~", r), ("post2003", r[r.index.year>=2003])]:
            pb2=perf(rr); pt=perf(tilt_rule(rr,w)); ps=perf(static_rule(rr,avg_w))
            row[label]=dict(틸트=pt, 벤치_buyhold=pb2,
                            대조군_정적동일노출=dict(비중=round(avg_w,3), **ps),
                            게이트_vs_buyhold=gate(pt,pb2),
                            계절성_실제기여=dict(
                                CAGR차=round(pt["CAGR"]-ps["CAGR"],4),
                                Sharpe차=round(pt["Sharpe"]-ps["Sharpe"],3),
                                MDD차=round(abs(ps["MDD"])-abs(pt["MDD"]),4),
                                계절성이_더한값_있나=bool(pt["Sharpe"]>ps["Sharpe"] and pt["CAGR"]>=ps["CAGR"])))
        tilt[f"틸트{int(w*100)}%" + ("_★판정" if w==0.50 else "_탐색")]=row
    out["부분틸트"]=tilt
    j=tilt["틸트50%_★판정"]
    ok_full=all(j["전체_1995~"]["게이트_vs_buyhold"].values()); ok_new=all(j["post2003"]["게이트_vs_buyhold"].values())
    seas_full=j["전체_1995~"]["계절성_실제기여"]["계절성이_더한값_있나"]
    seas_new=j["post2003"]["계절성_실제기여"]["계절성이_더한값_있나"]
    out["틸트50_VERDICT"]=dict(
        vs_buyhold=("전체·post2003 모두 통과" if (ok_full and ok_new) else
                    ("post2003만 통과" if ok_new else ("전체만 통과=위기의존" if ok_full else "양쪽 미달"))),
        vs_정적동일노출=("계절성이 실제로 값을 더함(양쪽)" if (seas_full and seas_new) else
                        ("post2003만 더함" if seas_new else ("전체만 더함" if seas_full else "★계절성 기여 없음 = 그냥 덜 태운 효과 → 기각"))),
        최종=("채택후보 — buy&hold도 이기고, 정적 동일노출도 이김" if (ok_new and seas_new)
              else "기각 — 계절성 자체의 기여 없음 또는 게이트 미달"))
    g=out["primary_고전Halloween_11to4"]["게이트"]
    out["VERDICT"]=("Halloween 채택후보(전 게이트 통과) — 단 죽여보기 확인 필수" if all(g.values()) else "게이트 미달 → 기각")
    out["note"]="primary=문헌 표준(11~4월). 탐색은 판정 아님. 배당1.8%·비용15bp. 죽여보기=위기제외·발표전후·t값·RF민감도."
    return out

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--run",action="store_true")
    a=ap.parse_args()
    if a.run: print(json.dumps(run(),ensure_ascii=False,indent=2))
    else: print("사용: --run")
