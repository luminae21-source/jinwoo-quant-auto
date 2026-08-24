#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우_월간자동화.py — 실전 매뉴얼 자동 실행기.

매달 1회 실행하면:
  (A) 딥밸류바닥 신규 후보 산출 (매뉴얼 1단계 스크린: 저PBR20% ∩ 이격<0.85 ∩ 턴 ∩ 유동성)
  (B) 관심권(2/3 충족) 워치리스트 — 강세장이라 정식 후보가 적을 때 대비
  (C) 보유중(진우_보유.csv) 종목의 익절 시그널 자동 판정
      (매뉴얼 4단계: 이격≥1.5 · +100% · PBR≥1.0 · 트레일-20% / 단일규칙 이격1.5 우선)
산출물: 진우_월간_후보.csv, 진우_월간_익절판정.csv, 콘솔 리포트.

보유 입력 형식(진우_보유.csv, 없으면 (C) 생략):
  code,진입월,진입가   예) 013890,2026-06,17500   (진입가 비우면 진입월 종가로 자동)

의존: 종목일봉_30년_*, 종목재무_KRX_*, 종목시총_30년.csv
근거: 사냥터_기획/진우_익절최적화_MFE.md(단일규칙 이격≥1.5 CAGR최고), 진우_수익최대화_전략백테스트.md
신호효능 근사 · 투자자문 아님.  사용: py 진우_월간자동화.py
"""
import os, sys, csv, datetime
import numpy as np, pandas as pd
BASE=os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

# ---------- 종목명 맵 ----------
def name_map():
    nm={}
    for f in ("진우_타점발굴.csv","진우사냥터_후보.csv","진우_관심종목.csv","liquidity_sector.csv"):
        p=os.path.join(BASE,f)
        if not os.path.exists(p): continue
        try:
            for r in csv.DictReader(open(p,encoding="utf-8-sig")):
                r={k.lstrip("﻿"):v for k,v in r.items()}
                c=(r.get("code") or "").strip(); n=(r.get("name") or "").strip()
                if c and n: nm.setdefault(c.zfill(6),n)
        except Exception: pass
    return nm

# ---------- 월봉 종가(캐시 재사용) ----------
def monthly_close(market):
    cache=os.path.join(BASE,f"_월봉종가캐시_{market}.csv")
    if os.path.exists(cache): return pd.read_csv(cache,dtype={"code":str})
    keep={}
    for ch in pd.read_csv(os.path.join(BASE,f"종목일봉_30년_{market}.csv"),usecols=["date","code","close"],
                          dtype={"code":str},encoding="utf-8-sig",chunksize=2_000_000):
        ch=ch[pd.to_numeric(ch["close"],errors="coerce")>0]; ch["ym"]=ch["date"].str[:7]
        for dte,c,cl,ym in zip(ch["date"],ch["code"],ch["close"],ch["ym"]):
            k=(c.zfill(6),ym); cur=keep.get(k)
            if cur is None or dte>cur[0]: keep[k]=(dte,float(cl))
    out=pd.DataFrame([(c,ym,v[1]) for (c,ym),v in keep.items()],columns=["code","ym","close"])
    out.to_csv(cache,index=False,encoding="utf-8-sig"); return out

def build_matrices():
    px=pd.concat([monthly_close(m) for m in ("KOSPI","KOSDAQ")],ignore_index=True)
    px["code"]=px["code"].str.zfill(6); px=px.drop_duplicates(["code","ym"])
    px["close"]=pd.to_numeric(px["close"],errors="coerce")
    months=sorted(px["ym"].unique()); mi={m:i for i,m in enumerate(months)}
    codes=sorted(px["code"].unique()); ci={c:i for i,c in enumerate(codes)}
    C,T=len(codes),len(months)
    def grid(df,val):
        G=np.full((C,T),np.nan)
        for c,y,v in zip(df["code"],df["ym"],df[val]):
            if c in ci and y in mi and v==v: G[ci[c],mi[y]]=v
        return G
    CL=grid(px,"close")
    fr=[]
    for m in ("KOSPI","KOSDAQ"):
        d=pd.read_csv(os.path.join(BASE,f"종목재무_KRX_{m}.csv"),dtype={"code":str})
        d["code"]=d["code"].str.zfill(6); d["ym"]=d["date"].str[:7]
        d["PBR"]=pd.to_numeric(d["PBR"],errors="coerce"); fr.append(d[["code","ym","PBR"]])
    PBR=grid(pd.concat(fr).drop_duplicates(["code","ym"]).rename(columns={"PBR":"v"}).assign(PBR=lambda x:x["v"]),"PBR")
    mc=pd.read_csv(os.path.join(BASE,"종목시총_30년.csv"),dtype={"code":str})
    mc["code"]=mc["code"].str.zfill(6); mc["ym"]=mc["date"].str[:7]
    mc["mcap"]=pd.to_numeric(mc["mcap"],errors="coerce")
    MC=grid(mc.rename(columns={"mcap":"v"}).assign(mcap=lambda x:x["v"]),"mcap")
    return codes,ci,months,CL,PBR,MC

def latest_signal_month(disp,PBR,ret1):
    T=disp.shape[1]
    for m in range(T-1,-1,-1):
        if (~np.isnan(disp[:,m])).sum()>100 and (~np.isnan(PBR[:,m])).sum()>100 and (~np.isnan(ret1[:,m])).sum()>100:
            return m
    return T-1

def daily_series(codes_needed):
    """보유종목 익절판정용 일봉(종가) 로드 — 필요한 종목만·최근 2년만(경량)."""
    want=set(c.zfill(6) for c in codes_needed); out={}
    if not want: return out
    cutoff=(datetime.date.today()-datetime.timedelta(days=760)).strftime("%Y-%m-%d")  # MA200+진입후 충분
    for m in ("KOSPI","KOSDAQ"):
        p=os.path.join(BASE,f"종목일봉_30년_{m}.csv")
        if not os.path.exists(p): continue
        for ch in pd.read_csv(p,usecols=["date","code","close"],dtype={"code":str},
                              encoding="utf-8-sig",chunksize=1_000_000):
            ch=ch[ch["date"]>=cutoff]
            if ch.empty: continue
            ch["code"]=ch["code"].str.zfill(6); ch=ch[ch["code"].isin(want)]
            if ch.empty: continue
            ch["close"]=pd.to_numeric(ch["close"],errors="coerce")
            for c,g in ch.groupby("code"):
                out.setdefault(c,[]).append(g[["date","close"]])
    for c in list(out): out[c]=pd.concat(out[c]).dropna().sort_values("date").reset_index(drop=True)
    return out

def main():
    nm=name_map()
    codes,ci,months,CL,PBR,MC=build_matrices()
    C,T=CL.shape
    ma=np.full((C,T),np.nan)
    for m in range(9,T):
        w=CL[:,m-9:m+1]; ma[:,m]=np.where((~np.isnan(w)).sum(1)==10,np.nanmean(w,1),np.nan)
    disp=CL/ma
    ret1=np.full((C,T),np.nan); ret1[:,1:]=CL[:,1:]/CL[:,:-1]-1
    m=latest_signal_month(disp,PBR,ret1); sigm=months[m]
    # PBR 백분위(하위=싸다)
    col=PBR[:,m]; v=~np.isnan(col); PRr=np.full(C,np.nan)
    PRr[np.where(v)[0]]=np.argsort(np.argsort(col[v]))/(v.sum()-1)
    mc=MC[:,m]; LIQ=mc>=np.nanpercentile(mc[~np.isnan(mc)],30)
    c_pbr=PRr<=0.20; c_disp=disp[:,m]<0.85; c_turn=ret1[:,m]>0
    deep=c_pbr&c_disp&c_turn&LIQ
    watch=LIQ&((c_pbr.astype(int)+c_disp.astype(int)+c_turn.astype(int))==2)&(PRr<=0.30)
    def rowinfo(i):
        return dict(code=codes[i],name=nm.get(codes[i],""),PBR=round(float(PBR[i,m]),2),
                    이격=round(float(disp[i,m]),3),수익20=round(float(ret1[i,m]*100),1),
                    시총조=round(float(MC[i,m]/1e12),2))
    cand=sorted((rowinfo(i) for i in np.where(deep)[0]),key=lambda x:x["이격"])
    wl=sorted((rowinfo(i) for i in np.where(watch)[0]),key=lambda x:x["이격"])[:25]
    # 저장
    with open(os.path.join(BASE,"진우_월간_후보.csv"),"w",newline="",encoding="utf-8-sig") as f:
        w=csv.writer(f); w.writerow(["구분","code","name","PBR","이격","20일수익%","시총조원","신호월"])
        for r in cand: w.writerow(["후보",r["code"],r["name"],r["PBR"],r["이격"],r["수익20"],r["시총조"],sigm])
        for r in wl:  w.writerow(["관심",r["code"],r["name"],r["PBR"],r["이격"],r["수익20"],r["시총조"],sigm])
    print(f"■ 진우 사냥터 · 월간 자동화  (신호월 {sigm} · 생성 {datetime.date.today()})")
    print(f"\n[A] 딥밸류바닥 정식 후보 — {len(cand)}종  (저PBR20% ∩ 이격<0.85 ∩ 턴 ∩ 유동성)")
    if cand:
        print(f"  {'code':<7}{'종목':<12}{'PBR':>5}{'이격':>6}{'20일%':>7}{'시총조':>7}")
        for r in cand: print(f"  {r['code']:<7}{(r['name'] or '·')[:11]:<12}{r['PBR']:>5.2f}{r['이격']:>6.2f}{r['수익20']:>+6.0f}%{r['시총조']:>6.1f}")
    else:
        print("  없음 — 강세장. 신규진입 자제, 보유 익절관리에 집중.")
    print(f"\n[B] 관심권(2/3 충족·PBR≤30%) — {len(wl)}종  ※정식신호 아님, 트리거 대기용")
    print(f"  {'code':<7}{'종목':<12}{'PBR':>5}{'이격':>6}{'20일%':>7}  결측조건")
    for r in wl:
        i=ci[r["code"]]
        miss=[n for n,ok in (("저PBR",c_pbr[i]),("이격<.85",c_disp[i]),("턴",c_turn[i])) if not ok]
        print(f"  {r['code']:<7}{(r['name'] or '·')[:11]:<12}{r['PBR']:>5.2f}{r['이격']:>6.2f}{r['수익20']:>+6.0f}%  {','.join(miss)}")

    # ---------- (C) 보유 익절 판정 ----------
    hp=os.path.join(BASE,"진우_보유.csv")
    print(f"\n[C] 보유 익절 시그널", end="")
    if not os.path.exists(hp):
        print(" — 진우_보유.csv 없음(건너뜀). 형식: code,진입월,진입가")
        print("\n※ 참고: [A] 후보로 모의포트 구성 시 EW 10~15종·즉시매수·이격≥1.5 익절이 매뉴얼 기준.")
        return
    # 주석(#) 라인 허용. 진우_보유.csv 에 유효행이 없으면 my_holdings.csv 로 폴백.
    def _load_hold(path, colmap=None):
        try:
            d=pd.read_csv(path,dtype={"code":str},comment="#",skip_blank_lines=True)
        except Exception:
            return None
        if colmap: d=d.rename(columns=colmap)
        if "code" not in d.columns: return None
        d=d[d["code"].notna()].copy()
        d["code"]=d["code"].astype(str).str.strip().str.zfill(6)
        d=d[d["code"].str.match(r"^\d{6}$")]
        return d if len(d) else None
    hold=_load_hold(hp)
    if hold is None:
        mh=os.path.join(BASE,"my_holdings.csv")
        hold=_load_hold(mh,{"entry_price":"진입가","entry_date":"진입월"})
        if hold is not None:
            print(" (진우_보유.csv 유효행 없음 → my_holdings.csv 사용)",end="")
            if "진입월" in hold.columns:
                hold["진입월"]=hold["진입월"].astype(str).str.slice(0,7).replace({"nan":""})
    if hold is None:
        print(" — 보유 데이터 없음(건너뜀). 형식: code,진입월,진입가"); return
    # 월봉 기준(이미 메모리) — 일봉 재읽기 없이 고속·안전. 이격=월봉 CL/ma10(후보탐지와 동일 기준).
    ma10row=ma  # 월봉 10개월 이동평균(=200일 근사)
    outrows=[]; print()
    print(f"  {'code':<7}{'종목':<12}{'현재가':>9}{'수익률':>8}{'이격':>6}{'PBR':>5}{'고점대비':>8}  판정")
    for _,h in hold.iterrows():
        c=h["code"]; i=ci.get(c)
        if i is None or np.isnan(CL[i,m]):
            print(f"  {c:<7}{'(데이터 없음)':<12}"); continue
        cur=float(CL[i,m]); ext=float(disp[i,m])   # 월봉 이격
        entry_m=str(h.get("진입월","")); ent=h.get("진입가",np.nan)
        try: ent=float(ent)
        except Exception: ent=np.nan
        if not (ent==ent) and entry_m and entry_m in months:
            ent=float(CL[i,months.index(entry_m)]) if not np.isnan(CL[i,months.index(entry_m)]) else np.nan
        gain=(cur/ent-1)*100 if ent==ent else np.nan
        # 진입 이후 월봉 고점 대비 낙폭(트레일)
        e0=months.index(entry_m) if entry_m in months else 0
        after=CL[i,e0:m+1]; after=after[~np.isnan(after)]
        peak=float(np.max(after)) if len(after) else cur
        trail=(cur/peak-1)*100
        pbr=float(PBR[i,m]) if ~np.isnan(PBR[i,m]) else np.nan
        # 진입 후 경과월(6M내 물타기 윈도 판정)
        mo_since=None
        if entry_m and len(entry_m)>=7:
            try:
                ey,em=int(entry_m[:4]),int(entry_m[5:7]); cy,cm=int(sigm[:4]),int(sigm[5:7])
                mo_since=(cy-ey)*12+(cm-em)
            except Exception: mo_since=None
        sigs=[]
        if ext>=1.5: sigs.append("이격≥1.5")
        if gain==gain and gain>=100: sigs.append("+100%")
        if pbr==pbr and pbr>=1.0: sigs.append("PBR≥1.0")
        if trail<=-20: sigs.append("트레일-20%")
        # 2차 물타기(가바닥): 진입가 대비 -15%↓ & 6M내 → 비중 집중(예비금 현금 금지, 완전투자 조달). 검증: 물타기B OOS +38%.
        avg_add = (gain==gain and gain<=-15 and (mo_since is None or mo_since<=6))
        # 매뉴얼 처방: 익절은 단일규칙 이격≥1.5 우선. 하락은 손절 아닌 물타기.
        if ext>=1.5: verdict="★익절(이격≥1.5·주규칙)"
        elif avg_add: verdict="◆2차 물타기(-15%↓·비중집중)"
        elif sigs: verdict="알림:"+",".join(sigs)
        else: verdict="보유"
        outrows.append([c,nm.get(c,""),round(cur),round(gain,1) if gain==gain else "",
                        round(ext,3),round(pbr,2) if pbr==pbr else "",round(trail,1),verdict])
        print(f"  {c:<7}{(nm.get(c,'') or '·')[:11]:<12}{cur:>9,.0f}{(f'{gain:+.0f}%' if gain==gain else '—'):>8}"
              f"{ext:>6.2f}{(f'{pbr:.2f}' if pbr==pbr else '—'):>5}{trail:>+7.0f}%  {verdict}")
    with open(os.path.join(BASE,"진우_월간_익절판정.csv"),"w",newline="",encoding="utf-8-sig") as f:
        w=csv.writer(f); w.writerow(["code","name","현재가","수익률%","이격","PBR","고점대비%","판정"]); w.writerows(outrows)
    print("\n  주규칙=이격≥1.5 도달 시 익절(CAGR최고·MFE_검증). 나머지 트리거는 '알림'만.")
    print("  ◆2차 물타기=진입가 −15%↓·6M내 → 비중집중(손절 아님). ★조달은 예비금 현금 금지, 만기분·재조정으로(완전투자). 근거: 진우_물타기_포트검증.md")

if __name__=="__main__": main()
