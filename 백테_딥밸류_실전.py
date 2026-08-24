#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""백테_딥밸류_실전.py — 딥밸류 반등 신호를 '실전형 포트폴리오'로 승격

신호효능(백테_딥밸류_하락장.py)을 체결가능 전략으로: 유동성필터+실체결비용+월단위 로트관리.
규칙:
  · 매월말, 하락장(KOSPI<10M선)일 때만 신규진입.
  · 진입군 = 반등군(PBR하위20% ∩ 이격<0.85 ∩ 1M수익>0) ∩ 월말거래대금≥LIQ.
  · 등가중, 최대 MAXPOS종. 1M수익 강한 순으로 채움.
  · 각 로트 최대 HOLD개월 보유 후 청산(승자 라이딩). 강세장엔 신규 안 사고 기존만 만기까지.
비용: 매수 15bp · 매도 33bp. 현금월 수익 0.
비교: ①슬리브(순수) ②콤보(강세=KOSPI보유·하락=슬리브) ③KOSPI 매수보유.
⚠️ 생존편향(월봉=현재상장만)→수익 상향편의. 월말거래대금=유동성 근사. 슬리피지 미반영. 투자자문 아님·결정 본인.
사용: py 백테_딥밸류_실전.py [--maxpos 15] [--hold 12] [--liq 5] [--self-test]   (liq 단위: 억원)
"""
import os, sys, argparse
import numpy as np, pandas as pd
HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
CB, CS = 0.0015, 0.0033

def mdd(e): return float((e/e.cummax()-1).min())
def cagr(e, months): return float((e.iloc[-1]/e.iloc[0])**(12/max(months,1))-1)
def sharpe(r): return float(r.mean()/r.std()*np.sqrt(12)) if r.std()>0 else float("nan")

def load():
    d = pd.read_csv(os.path.join(HERE,"_mliq_all.csv"), header=None, names=["code","date","close","liq"], dtype={"code":str})
    d["code"]=d["code"].str.zfill(6); d["m"]=pd.to_datetime(d["date"],errors="coerce").dt.to_period("M")
    for c in ("close","liq"): d[c]=pd.to_numeric(d[c],errors="coerce")
    d=d.dropna(subset=["m","close"])
    close=d.pivot_table(index="m",columns="code",values="close",aggfunc="last").sort_index()
    liq=d.pivot_table(index="m",columns="code",values="liq",aggfunc="last").reindex_like(close)
    return close, liq

def load_pbr(idx, cols):
    fr=[]
    for mk in ("KOSPI","KOSDAQ"):
        p=os.path.join(HERE,f"종목재무_KRX_{mk}.csv")
        if os.path.exists(p):
            x=pd.read_csv(p,dtype={"code":str},encoding="utf-8-sig"); x.columns=[c.lstrip("﻿") for c in x.columns]
            fr.append(x[["date","code","PBR"]])
    d=pd.concat(fr,ignore_index=True); d["code"]=d["code"].str.zfill(6)
    d["m"]=pd.to_datetime(d["date"],errors="coerce").dt.to_period("M"); d["PBR"]=pd.to_numeric(d["PBR"],errors="coerce")
    d=d.dropna(subset=["m"])
    return d.pivot_table(index="m",columns="code",values="PBR",aggfunc="last").reindex(idx).reindex(columns=cols)

def regime(idx):
    k=pd.read_csv(os.path.join(HERE,"kospi_index_daily.csv"),encoding="utf-8-sig"); k.columns=[c.lstrip("﻿").lower() for c in k.columns]
    k["m"]=pd.to_datetime(k["date"],errors="coerce").dt.to_period("M"); k["close"]=pd.to_numeric(k["close"],errors="coerce")
    km=k.dropna(subset=["m"]).groupby("m")["close"].last().sort_index()
    bull=(km>km.rolling(10).mean()).reindex(idx).ffill().fillna(False)
    kret=km.reindex(idx).pct_change()
    return bull, kret

def run(maxpos=15, hold=12, liqmin_eok=5.0, deep=0.2, ext=0.85):
    LIQ=liqmin_eok*1e8
    close, liq = load()
    idx=close.index; cols=close.columns
    pbr=load_pbr(idx,cols)
    ma3=close.rolling(3).mean(); ma10=close.rolling(10).mean()
    disp=close/ma10; ret1=close.pct_change()
    valid=close.notna()&(close>=500)&ma10.notna()&(pbr>0)&pbr.notna()&(liq>=LIQ)
    pr=pbr.where(valid).rank(axis=1,pct=True)
    elig=(valid&(pr<=deep)&(disp<ext)&(ret1>0))
    bull, kret = regime(idx)
    fret=close.pct_change().shift(-1)  # t→t+1 수익
    months=list(idx)
    hold_map={}   # code -> entry index
    sleeve=[]; lot_realized=[]; invested_flags=[]; n_hold_series=[]
    ncodes=close.shape[1]
    warm=12
    for ti in range(warm, len(months)-1):
        t=months[ti]
        # 만기 청산
        expired=[c for c,ei in hold_map.items() if ti-ei>=hold]
        for c in expired:
            r=fret.at[t,c] if c in fret.columns else np.nan  # 미사용
            hold_map.pop(c,None)
        exits=len(expired)
        entries=0
        if not bool(bull.iloc[ti]):  # 하락장만 신규
            row=elig.iloc[ti]
            cand=[c for c in cols[row.values] if c not in hold_map]
            cand.sort(key=lambda c: ret1.at[t,c] if pd.notna(ret1.at[t,c]) else -9, reverse=True)
            for c in cand:
                if len(hold_map)>=maxpos: break
                hold_map[c]=ti; entries+=1
        held=[c for c in hold_map if pd.notna(fret.at[t,c])]
        k=len(held)
        if k>0:
            base=float(np.nanmean([fret.at[t,c] for c in held]))
            cost=(entries*CB + exits*CS)/max(k,1)
            sret=base-cost
        else:
            sret=0.0
        sleeve.append(sret); invested_flags.append(k>0); n_hold_series.append(k)
    sr=pd.Series(sleeve,index=months[warm:len(months)-1])
    kr=kret.reindex(sr.index).fillna(0)
    bl=bull.reindex(sr.index).fillna(False)
    combo=np.where(bl.values, kr.values, sr.values)  # 강세=지수, 하락=슬리브
    cr=pd.Series(combo,index=sr.index)
    eqs=(1+sr).cumprod(); eqc=(1+cr).cumprod(); eqk=(1+kr).cumprod()
    n=len(sr)
    res={"기간":f"{sr.index.min()}~{sr.index.max()}","월수":n,
         "파라미터":f"최대{maxpos}종·보유{hold}M·거래대금≥{liqmin_eok:.0f}억·PBR하위{int(deep*100)}%·이격<{ext}",
         "투자월비율":round(float(np.mean(invested_flags)),3),
         "평균보유종목수(투자월)":round(float(np.mean([x for x in n_hold_series if x>0]) if any(n_hold_series) else 0),1)}
    for lab,e,r in (("①슬리브(순수)",eqs,sr),("②콤보(강세지수+하락슬리브)",eqc,cr),("③KOSPI매수보유",eqk,kr)):
        res[lab]=dict(CAGR=round(cagr(e,n),4),MDD=round(mdd(e),4),Sharpe=round(sharpe(r),3),최종배수=round(float(e.iloc[-1]),2))
    return res

def _fmt(o):
    print(f"\n{'='*88}\n딥밸류 반등 실전형 포트폴리오 · {o['기간']} ({o['월수']}개월)\n{o['파라미터']}\n{'='*88}")
    print(f"투자월 비율 {o['투자월비율']*100:.0f}% · 투자월 평균보유 {o['평균보유종목수(투자월)']}종\n")
    print(f"  {'전략':<28}{'CAGR':>9}{'MDD':>9}{'Sharpe':>9}{'최종배수':>9}")
    for k in ("①슬리브(순수)","②콤보(강세지수+하락슬리브)","③KOSPI매수보유"):
        s=o[k]; print(f"  {k:<28}{s['CAGR']*100:>+8.1f}%{s['MDD']*100:>+8.1f}%{s['Sharpe']:>9.2f}{s['최종배수']:>8.1f}x")
    print("\n※ ①은 강세장엔 현금(사냥터 sleeve). ②는 강세=지수보유·하락=반등슬리브(전체 배분).")
    print("※ 생존편향으로 수익 상향편의 · 슬리피지·세금 미반영 · 신호효능 검증의 실전근사.")

def _self_test():
    ok=tot=0
    def chk(n,c):
        nonlocal ok,tot; tot+=1; ok+=1 if c else 0; print(f"  [{'OK' if c else 'FAIL'}] {n}")
    e=pd.Series([1,1.5,1.2,1.8]); chk("CAGR양수",cagr(e,24)>0); chk("MDD음수",mdd(e)<0)
    chk("Sharpe유한",np.isfinite(sharpe(pd.Series([0.01,0.02,-0.01,0.03]))))
    print(f"\n셀프테스트: {ok}/{tot}"); return ok==tot

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--maxpos",type=int,default=15); ap.add_argument("--hold",type=int,default=12)
    ap.add_argument("--liq",type=float,default=5.0); ap.add_argument("--self-test",action="store_true")
    a=ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    _fmt(run(a.maxpos,a.hold,a.liq)); return 0

if __name__=="__main__": sys.exit(main())
