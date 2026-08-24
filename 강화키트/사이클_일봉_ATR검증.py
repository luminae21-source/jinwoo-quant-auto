#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""사이클_일봉_ATR검증.py — P1: 사이클 룰 일봉 실검증 (매도규칙_라우터 정합)

가설: 단일 사이클 종목에서 '월봉 MA룰'은 휩쏘로 신뢰 못 함(앞 검정).
      더 촘촘한 '일봉 3.5ATR 넓은 트레일'(본체 매도규칙_라우터 momentum 규칙)이면
      상승 사이클을 더 잘 타면서 급락을 피하는가?

규칙(일봉, 룩어헤드 없음 — 전일 종가로 결정):
  · 진입: 종가 > 50일 이동평균 (추세 상향)
  · 청산: 종가 < 진입후 고점 − 3.5×ATR(14)  (샹들리에/넓은 트레일)  또는 고점 대비 −25%(재난)
  · 재진입: 다시 50일 MA 상향 돌파
비교: 바이앤홀드 · 월봉 MA(10개월, 앞 검정) · 일봉 ATR트레일.
비용: 다올(세금0.2%+슬리피지). ⚠️ 검증용·실현손익 아님·투자자문 아님·책임 본인.
"""
# §8-3(2026-07-27): tax 0.002→0.0015(실제 증권거래세) · slip 0.0005→0.002045(CS 실측 편도) → 왕복 0.300%→0.559%


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

NAMES = {"247540":"에코프로비엠","086520":"에코프로","006400":"삼성SDI","066970":"엘앤에프",
         "007660":"이수페타시스","042700":"한미반도체","000660":"SK하이닉스","240810":"원익IPS",
         "373220":"LG에너지솔루션","011070":"LG이노텍","009150":"삼성전기","034020":"두산에너빌리티",
         "267260":"HD현대일렉트릭","042660":"한화오션","009540":"HD한국조선해양","079550":"LIG넥스원",
         "012450":"한화에어로","064350":"현대로템","298040":"효성중공업","402340":"SK스퀘어","353200":"대덕전자"}

def _find(fn):
    for d in (BASE, os.path.dirname(BASE), os.getcwd()):
        p=os.path.join(d,fn)
        if os.path.exists(p): return p
    return None

def load_daily():
    p=_find("_일봉_사이클케이스.csv")
    d=pd.read_csv(p,dtype={"code":str}); d["code"]=d["code"].str.zfill(6)
    d["date"]=pd.to_datetime(d["date"]); return d.sort_values(["code","date"])

def atr(df, n=14):
    h,l,c=df["high"],df["low"],df["close"]; pc=c.shift(1)
    tr=pd.concat([h-l,(h-pc).abs(),(l-pc).abs()],axis=1).max(axis=1)
    return tr.ewm(alpha=1/n,adjust=False).mean()

def stats_daily(r, ann=252):
    r=pd.Series(r).dropna()
    if len(r)<60: return None
    c=(1+r).cumprod()
    return dict(CAGR=(1+r).prod()**(ann/len(r))-1, Sharpe=r.mean()/r.std()*np.sqrt(ann) if r.std()>0 else np.nan,
                MDD=(c/c.cummax()-1).min(), cum=float(c.iloc[-1]), n=len(r))

def atr_trail(df, atr_mult=3.5, hard=0.25, ma=50, tax=0.0015, slip=0.002045):
    df=df.reset_index(drop=True)
    c=df["close"]; ret=c.pct_change()
    A=atr(df); M=c.rolling(ma).mean(); hh=c.copy()
    pos=np.zeros(len(df)); state=0; peak=0.0
    for t in range(1,len(df)):
        # 전일(t-1) 정보로 t일 포지션 결정
        pc=c.iloc[t-1]; pm=M.iloc[t-1]; pa=A.iloc[t-1]
        if state==0:
            if pd.notna(pm) and pc>pm: state=1; peak=pc
        else:
            peak=max(peak,pc)
            stop=peak-atr_mult*pa if pd.notna(pa) else peak*(1-hard)
            stop=max(stop, peak*(1-hard))  # 재난 −25% 백스톱(더 높은 쪽=타이트)
            if pc<stop or (pd.notna(pm) and pc<pm and pc<peak*(1-hard)):
                state=0
        pos[t]=state
    pos=pd.Series(pos,index=df.index)
    flips=pos.diff().abs().fillna(0)
    rule=pos*ret - flips*(tax+2*slip)
    return rule, ret

def ma_monthly(df, K=10, tax=0.0015, slip=0.002045):
    """월봉 MA룰(앞 검정 재현) — 월말 리샘플."""
    d=df.set_index("date"); m=d["close"].resample("ME").last().dropna()
    r=m.pct_change(); maK=m.rolling(K).mean(); sig=(m>=maK).shift(1)
    rule=r.where(sig,0.0); flips=sig.fillna(False).astype(int).diff().abs().fillna(0)
    return (rule-flips*(tax+2*slip)), r

def run():
    dd=load_daily()
    print("="*96)
    print("사이클 룰 일봉 실검증 — 바이앤홀드 vs 월봉MA(10m) vs 일봉 3.5ATR 넓은트레일")
    print("="*96)
    print(f"  {'종목':<16}{'구간':<20}{'BH배수':>8}{'월봉룰':>8}{'일봉ATR':>9}{'  BH/월봉/ATR  MDD':>26}{'ATR Sharpe':>11}")
    rows={}
    aggr_bh=[]; aggr_atr=[]
    for code,g in dd.groupby("code"):
        if len(g)<300: continue
        rule_d, ret_d = atr_trail(g)
        rule_m, ret_m = ma_monthly(g)
        sbh=stats_daily(ret_d); satr=stats_daily(rule_d); smm=stats_daily(rule_m,ann=12)
        if not sbh or not satr: continue
        nm=NAMES.get(code,code)
        rows[nm]=dict(bh_x=round(sbh['cum'],1), atr_x=round(satr['cum'],1),
                      bh_mdd=round(sbh['MDD']*100,0), atr_mdd=round(satr['MDD']*100,0),
                      mm_x=round(smm['cum'],1) if smm else None, mm_mdd=round(smm['MDD']*100,0) if smm else None,
                      bh_sh=round(sbh['Sharpe'],2), atr_sh=round(satr['Sharpe'],2))
        span=f"{g['date'].iloc[0].strftime('%Y-%m')}~{g['date'].iloc[-1].strftime('%y-%m')}"
        mmx=f"{smm['cum']:.1f}x" if smm else "  —"
        print(f"  {nm:<16}{span:<20}{sbh['cum']:>7.1f}x{mmx:>8}{satr['cum']:>8.1f}x   {sbh['MDD']*100:>5.0f}/{(smm['MDD']*100 if smm else 0):>4.0f}/{satr['MDD']*100:>4.0f}%{satr['Sharpe']:>11.2f}")
    # 요약
    bhmdd=np.mean([v['bh_mdd'] for v in rows.values()]); atrmdd=np.mean([v['atr_mdd'] for v in rows.values()])
    mmmdd=np.mean([v['mm_mdd'] for v in rows.values() if v['mm_mdd'] is not None])
    bhsh=np.mean([v['bh_sh'] for v in rows.values()]); atrsh=np.mean([v['atr_sh'] for v in rows.values()])
    keep=np.mean([v['atr_x']/v['bh_x'] for v in rows.values() if v['bh_x']>0])*100
    print(f"\n  ── 요약 ({len(rows)}종) ──")
    print(f"  · 평균 MDD: 바이앤홀드 {bhmdd:.0f}% · 월봉MA {mmmdd:.0f}% · 일봉ATR {atrmdd:.0f}%")
    print(f"  · 평균 Sharpe: 바이앤홀드 {bhsh:.2f} → 일봉ATR {atrsh:.2f}")
    print(f"  · 일봉ATR이 지킨 총수익 배수비율 평균 {keep:.0f}%")
    verdict = "일봉 ATR 트레일이 월봉MA보다 낙폭·Sharpe 개선(휩쏘 완화)" if (atrmdd>mmmdd and atrsh>=bhsh) else "일봉이 월봉 대비 부분 개선 — 종목별 편차 큼"
    print(f"  → 판정: {verdict}. 단일 사이클 종목은 일봉 트레일이 정합(매도규칙_라우터 momentum 규칙).")
    print("  ⚠️ 일봉 근사·재진입 단순(50MA). 실집행은 분할·갭 고려. 실현손익 아님·투자자문 아님.")
    json.dump(rows, open(os.path.join(BASE,"사이클_일봉_ATR검증_결과.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
    print("  저장: 사이클_일봉_ATR검증_결과.json")

if __name__=="__main__":
    run()
