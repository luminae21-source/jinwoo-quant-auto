#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""qmj_engine.py — 딥밸류(반등군) 기반 공용 엔진 + #2 퀄리티 오버레이(QMJ) 검증

데이터(로컬 스테이징, KOSPI, 상폐포함 PIT 2019-07~2026):
  kospi_pit_daily.csv   : code,date,ohlcv (상폐 포함 = 생존편향 통제)
  종목재무_KRX_KOSPI.csv : date(월말),code,PBR (밸류)
  kospi_index_daily.csv : Date,Close (국면=KOSPI 10개월선)
  fundamentals_pit.csv  : code,fiscal_year,재무항목 (퀄리티 원천, PIT 지연적용)

규칙(기존 백테_딥밸류_실전/PIT검증 재현):
  · 유효: close>=500 & PBR>0 & MA10 존재
  · 딥밸류: PBR 하위 20%
  · 반등군: 딥밸류 ∩ (close/MA10)<0.85 ∩ 1M수익>0
  · 국면: KOSPI<10M선 = 하락장(신규진입 허용)
  · 선행수익: 상폐면 -100%(또는 마지막유효가) 반영 = 밸류트랩 정직 계산
  · 비용: 매수 15bp, 매도 33bp

퀄리티(QMJ, PIT 지연): FY(y) 재무는 (y+1)-05월부터 사용.
  Profitability = z평균(GPOA, ROA, ROE, CFOA, OPM, -Accruals)
  Safety        = z평균(-Leverage, -NCL/Equity, +유동비율, -ROE변동성)
  Growth        = z평균(ΔGPOA, ΔROA)  (YoY)
  Quality       = z평균(Prof, Safety, Growth)  → 매월 유니버스 내 재랭크

⚠️ 정직: KOSPI 대형·중형(top~577)·2019~26·표본작음·2025~26 비현실강세. 절대치 신뢰금지, 상대비교·부호·트랩회피에 집중.
"""
import os as _os2
def _jqroot2():
    """프로젝트 루트 자동탐색 (2026-07-27 §5b)."""
    d=_os2.path.dirname(_os2.path.abspath(__file__))
    for _ in range(5):
        if _os2.path.exists(_os2.path.join(d,"종목시총_30년.csv")): return d
        d=_os2.path.dirname(d)
    return _os2.path.dirname(_os2.path.abspath(__file__))


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
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

DATA = _jqroot2()
CB, CS = 0.0015, 0.0033

# ---------- 유틸 ----------
def mdd(e): return float((e/e.cummax()-1).min())
def cagr(e, months): return float((e.iloc[-1]/e.iloc[0])**(12/max(months,1))-1) if e.iloc[0]>0 else float("nan")
def sharpe(r): return float(r.mean()/r.std()*np.sqrt(12)) if r.std()>0 else float("nan")
def calmar(c, m): return float(c/abs(m)) if m and m<0 else float("nan")

# ---------- 로더 ----------
def load_monthly_close():
    """상폐포함 일봉 → 월말 종가 (code x month). 상폐종목은 마지막 거래월 이후 NaN."""
    d = pd.read_csv(f"{DATA}/kospi_pit_daily.csv", dtype={"code":str},
                    usecols=["code","date","close"])
    d["code"]=d["code"].str.zfill(6)
    d["m"]=pd.to_datetime(d["date"],errors="coerce").dt.to_period("M")
    d["close"]=pd.to_numeric(d["close"],errors="coerce")
    d=d.dropna(subset=["m","close"])
    close=d.pivot_table(index="m",columns="code",values="close",aggfunc="last").sort_index()
    return close

def load_pbr(idx, cols):
    x=pd.read_csv(f"{DATA}/종목재무_KRX_KOSPI.csv",dtype={"code":str},encoding="utf-8-sig")
    x.columns=[c.lstrip("﻿") for c in x.columns]
    x["code"]=x["code"].str.zfill(6)
    x["m"]=pd.to_datetime(x["date"],errors="coerce").dt.to_period("M")
    x["PBR"]=pd.to_numeric(x["PBR"],errors="coerce")
    x=x.dropna(subset=["m"])
    return x.pivot_table(index="m",columns="code",values="PBR",aggfunc="last").reindex(idx).reindex(columns=cols)

def load_regime(idx):
    k=pd.read_csv(f"{DATA}/kospi_index_daily.csv",encoding="utf-8-sig")
    k.columns=[c.lstrip("﻿").lower() for c in k.columns]
    k["m"]=pd.to_datetime(k["date"],errors="coerce").dt.to_period("M")
    k["close"]=pd.to_numeric(k["close"],errors="coerce")
    km=k.dropna(subset=["m"]).groupby("m")["close"].last().sort_index()
    bull=(km>km.rolling(10).mean()).reindex(idx).ffill().fillna(False)
    kret=km.reindex(idx).pct_change()
    return bull, kret

# ---------- 퀄리티(QMJ) ----------
def _z(s):
    s=pd.to_numeric(s,errors="coerce")
    mu,sd=s.mean(),s.std()
    if not sd or sd!=sd: return pd.Series(0.0,index=s.index)
    return ((s-mu)/sd).clip(-3,3)

def build_quality_by_fy():
    """FY별 종목 퀄리티 원지표 → {fiscal_year: DataFrame(code x [Prof,Safety,Growth,Quality])}."""
    f=pd.read_csv(f"{DATA}/fundamentals_pit.csv",dtype={"code":str},encoding="utf-8-sig")
    f.columns=[c.lstrip("﻿") for c in f.columns]
    f["code"]=f["code"].str.zfill(6)
    for c in ["revenue","cogs","op_income","net_income","assets","liabilities","equity",
              "current_assets","current_liab","cfo","noncurrent_liab"]:
        f[c]=pd.to_numeric(f.get(c),errors="coerce")
    f=f.sort_values(["code","fiscal_year"])
    # 원지표
    f["GPOA"]=(f["revenue"]-f["cogs"])/f["assets"]
    f["ROA"] = f["net_income"]/f["assets"]
    f["ROE"] = f["net_income"]/f["equity"].where(f["equity"]>0)
    f["CFOA"]= f["cfo"]/f["assets"]
    f["OPM"] = f["op_income"]/f["revenue"].where(f["revenue"]>0)
    f["ACC"] = (f["net_income"]-f["cfo"])/f["assets"]          # 낮을수록 우량(발생액↓)
    f["LEV"] = f["liabilities"]/f["assets"]                    # 낮을수록 안전
    f["NCLE"]= f["noncurrent_liab"]/f["equity"].where(f["equity"]>0)
    f["CR"]  = f["current_assets"]/f["current_liab"].where(f["current_liab"]>0)
    # 성장(YoY) 및 이익안정성(과거 ROE 표준편차)
    f["dGPOA"]=f.groupby("code")["GPOA"].diff()
    f["dROA"] =f.groupby("code")["ROA"].diff()
    f["ROEvol"]=f.groupby("code")["ROE"].transform(lambda s: s.expanding(min_periods=2).std())
    out={}
    for fy,g in f.groupby("fiscal_year"):
        g=g.set_index("code")
        prof = pd.concat([_z(g["GPOA"]),_z(g["ROA"]),_z(g["ROE"]),_z(g["CFOA"]),_z(g["OPM"]),-_z(g["ACC"])],axis=1).mean(axis=1)
        safe = pd.concat([-_z(g["LEV"]),-_z(g["NCLE"]),_z(g["CR"]),-_z(g["ROEvol"])],axis=1).mean(axis=1)
        grow = pd.concat([_z(g["dGPOA"]),_z(g["dROA"])],axis=1).mean(axis=1)
        q=pd.DataFrame({"Prof":prof,"Safety":safe,"Growth":grow})
        q["Quality"]=q[["Prof","Safety","Growth"]].mean(axis=1)
        out[int(fy)]=q
    return out

def available_fy(m):
    """월 m(Period-M)에 사용가능한 최신 FY: 5월부터 전년도 FY 반영(연차보고서 3말 제출+여유)."""
    y,mo=m.year,m.month
    return y-1 if mo>=5 else y-2

def quality_panel(idx, cols):
    """월 x code 형태로 Quality/Prof/Safety/Growth 패널(PIT 지연 적용) 생성."""
    qfy=build_quality_by_fy()
    fields=["Quality","Prof","Safety","Growth"]
    panels={fld:pd.DataFrame(np.nan,index=idx,columns=cols) for fld in fields}
    for m in idx:
        fy=available_fy(m)
        if fy in qfy:
            q=qfy[fy]
            for fld in fields:
                s=q[fld].reindex(cols)
                panels[fld].loc[m]=s.values
    return panels

# ---------- 선행수익(상폐-100%) ----------
def fwd_return_delist_aware(px, h):
    V=px.values; T,N=V.shape; out=np.full((T,N),np.nan)
    for ti in range(T):
        base=V[ti]; hi=min(ti+h,T-1)
        if hi<=ti: continue
        win=V[ti+1:hi+1]
        for j in range(N):
            b=base[j]
            if not (b==b) or b<=0: continue
            col=win[:,j]; valid=col[~np.isnan(col)]
            out[ti,j]= valid[-1]/b-1 if valid.size>0 else -1.0
    return pd.DataFrame(out,index=px.index,columns=px.columns)

def monthly_return_delist_aware(px):
    """월간수익. 직전월 유효·당월 NaN이고 그게 마지막 유효월이면 -100%."""
    V=px.values; T,N=V.shape; out=np.full((T,N),np.nan)
    lastv=np.array([np.where(~np.isnan(V[:,j]))[0][-1] if np.any(~np.isnan(V[:,j])) else -1 for j in range(N)])
    for t in range(1,T):
        for j in range(N):
            a,b=V[t-1,j],V[t,j]
            if a==a and a>0:
                if b==b: out[t,j]=b/a-1
                elif t-1==lastv[j]: out[t,j]=-1.0
    return pd.DataFrame(out,index=px.index,columns=px.columns)

# ---------- 시그널 ----------
def build_signals(close, pbr, deep=0.20, ext=0.85):
    ma10=close.rolling(10).mean()
    disp=close/ma10; ret1=close.pct_change()
    valid=close.notna()&(close>=500)&ma10.notna()&(pbr>0)&pbr.notna()
    pr=pbr.where(valid).rank(axis=1,pct=True)
    deepv=valid&(pr<=deep)
    reb=deepv&(disp<ext)&(ret1>0)
    return dict(valid=valid,deep=deepv,reb=reb,ret1=ret1,disp=disp)

# ---------- 코호트 선행수익 요약 ----------
def summ(fwd,mask):
    v=fwd.where(mask).values.ravel(); v=v[~np.isnan(v)]
    if len(v)==0: return dict(n=0,mean=np.nan,median=np.nan,hit=np.nan,loss=np.nan,big=np.nan)
    return dict(n=int(len(v)),mean=float(np.mean(v)),median=float(np.median(v)),
                hit=float((v>0).mean()),loss=float((v<=-0.5).mean()),big=float((v>=1.0).mean()))

# ---------- 포트폴리오 백테(등가중, 국면진입, 만기청산) ----------
def portfolio_backtest(close, sig, bull, kret, mret, maxpos=15, hold=12,
                       qpanel=None, q_min_rank=None, enter_bear_only=True,
                       risk_off_scale=0.0):
    """
    q_min_rank: None이면 오버레이 없음. 값(0~1)이면 진입시 유니버스내 Quality 백분위 하위컷(>=q_min_rank만 허용).
    risk_off_scale: 강세장 비중(0=현금, 1=지수). 하락장은 항상 슬리브 100%.
    반환: 슬리브월수익 Series, combo(강세=지수*? ), 보유수 등.
    """
    idx=list(close.index); cols=close.columns
    reb=sig["reb"]; ret1=sig["ret1"]
    # 진입시 퀄리티 랭크(유니버스=valid 내 백분위)
    qrank=None
    if qpanel is not None and q_min_rank is not None:
        qrank=qpanel["Quality"].where(sig["valid"]).rank(axis=1,pct=True)
    hold_map={}
    sleeve=[]; nhold=[]; inv=[]
    warm=12
    ms=idx
    for ti in range(warm,len(ms)-1):
        t=ms[ti]
        expired=[c for c,ei in hold_map.items() if ti-ei>=hold]
        for c in expired: hold_map.pop(c,None)
        exits=len(expired)
        entries=0
        allow_new = (not bool(bull.iloc[ti])) if enter_bear_only else True
        if allow_new:
            row=reb.iloc[ti]
            cand=[c for c in cols[row.values] if c not in hold_map]
            if qrank is not None:
                cand=[c for c in cand if pd.notna(qrank.at[t,c]) and qrank.at[t,c]>=q_min_rank]
            cand.sort(key=lambda c: ret1.at[t,c] if pd.notna(ret1.at[t,c]) else -9, reverse=True)
            for c in cand:
                if len(hold_map)>=maxpos: break
                hold_map[c]=ti; entries+=1
        # 당월→다음월 수익 (mret의 t+1)
        tn=ms[ti+1]
        held=[c for c in hold_map if pd.notna(mret.at[tn,c])]
        k=len(held)
        if k>0:
            base=float(np.nanmean([mret.at[tn,c] for c in held]))
            cost=(entries*CB+exits*CS)/max(k,1)
            sret=base-cost
        else:
            sret=0.0
        # 상폐로 사라진 보유 제거(다음 루프 위해)
        for c in list(hold_map):
            if c not in close.columns: continue
            if pd.isna(close.at[tn,c]): hold_map.pop(c,None)
        sleeve.append(sret); nhold.append(k); inv.append(k>0)
    si=ms[warm:len(ms)-1]
    sr=pd.Series(sleeve,index=si)
    kr=kret.reindex(si).fillna(0)
    bl=bull.reindex(si).fillna(False)
    # combo: 강세장=지수*scale (나머지 현금), 하락장=슬리브
    combo=np.where(bl.values, kr.values*risk_off_scale if False else kr.values, sr.values)
    return dict(sleeve=sr, kret=kr, bull=bl, nhold=nhold, inv=inv)

def stats_block(sr):
    e=(1+sr).cumprod(); n=len(sr)
    return dict(CAGR=cagr(e,n),MDD=mdd(e),Sharpe=sharpe(sr),Calmar=calmar(cagr(e,n),mdd(e)),
                최종배수=float(e.iloc[-1]),월수=n)

# ---------- 셀프테스트 ----------
def selftest():
    ok=tot=0
    def chk(n,c):
        nonlocal ok,tot; tot+=1; ok+=1 if c else 0; print(f"  [{'OK' if c else 'FAIL'}] {n}")
    px=pd.DataFrame({"A":[100,110,120,np.nan,np.nan]},index=pd.period_range("2020-01",periods=5,freq="M"))
    f=fwd_return_delist_aware(px,3)
    chk("상폐직전가 반영 t0→+20%", abs(f.iloc[0,0]-0.2)<1e-9)
    m=monthly_return_delist_aware(px)
    chk("상폐월 -100%", abs(m.iloc[3,0]+1.0)<1e-9)
    chk("정상월 +10%", abs(m.iloc[1,0]-0.1)<1e-9)
    z=_z(pd.Series([1,2,3,4,5])); chk("z평균0", abs(z.mean())<1e-9)
    chk("available_fy 2021-06→2020", available_fy(pd.Period("2021-06"))==2020)
    chk("available_fy 2021-03→2019", available_fy(pd.Period("2021-03"))==2019)
    print(f"\n셀프테스트 {ok}/{tot}"); return ok==tot

if __name__=="__main__":
    ap=argparse.ArgumentParser(); ap.add_argument("--selftest",action="store_true"); a=ap.parse_args()
    if a.selftest: sys.exit(0 if selftest() else 1)
    print("engine module. import to use.")
