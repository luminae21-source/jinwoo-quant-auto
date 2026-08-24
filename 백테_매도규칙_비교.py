#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""백테_매도규칙_비교.py — 매도규칙 겨루기 (승자 안 자르고 총수익 극대 관점)

목적: 같은 진입(추세 시작=월 MA10 상향돌파)에 6가지 매도규칙을 적용해, 어느 것이
     '손실은 자르면서 대박은 안 자르나'를 30년·상폐반영 데이터로 실측.
매도규칙(월봉):
  · 보유24M     : 안 팔고 24개월 뒤 청산(기준선·매도스킬 0)
  · 트레일-20%  : 고점 대비 −20% 되돌리면 청산
  · 트레일-30%  : 고점 대비 −30% 되돌리면 청산(더 헐렁=승자 라이딩)
  · MA10이탈    : 월 MA10(≈일 MA200) 이탈 시 청산
  · 목표+30%익절: +30% 닿으면 익절(승자절단 가설 검증)
  · 손절+트레일 : max(진입−20%, 고점−30%) 이탈 청산 ← 진우 목적(손절+이익보호)
상폐: 창 내 소멸 시 마지막가 −50%(보수적)로 청산.
지표: 평균/중앙 실현수익 · 승률 · 대박포착(+50%↑) · 큰손실(−30%↓) · 평균보유월 · 연율화기대값.
⚠️ 월봉 해상도(트레일 −20/30%는 월말 기준, 실제 일중 더 촘촘) · 신호효능 · 투자자문 아님·결정 본인.
사용: py 백테_매도규칙_비교.py [--self-test]
"""
import os, sys, argparse
import numpy as np, pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
MAXH=24; DELIST_HAIRCUT=0.5

def simulate_entry(E, win, mawin):
    """진입가 E, 전방 close 배열 win(NaN=상폐), 전방 MA10 mawin → 규칙별 (수익, 보유월)."""
    rules=["보유24M","트레일-20%","트레일-30%","MA10이탈","목표+30%","손절+트레일"]
    res={r:None for r in rules}; peak=E
    H=len(win)
    for h in range(H):
        p=win[h]
        if p!=p:  # 상폐(NaN)
            lv=win[h-1] if h>0 else E
            for r in rules:
                if res[r] is None: res[r]=(lv*(1-DELIST_HAIRCUT)/E-1, h)
            return res
        if p>peak: peak=p
        ma=mawin[h]; hh=h+1; last=(h==H-1)
        if res["보유24M"] is None and last: res["보유24M"]=(p/E-1,hh)
        if res["트레일-20%"] is None and p<=peak*0.80: res["트레일-20%"]=(p/E-1,hh)
        elif res["트레일-20%"] is None and last: res["트레일-20%"]=(p/E-1,hh)
        if res["트레일-30%"] is None and p<=peak*0.70: res["트레일-30%"]=(p/E-1,hh)
        elif res["트레일-30%"] is None and last: res["트레일-30%"]=(p/E-1,hh)
        if res["MA10이탈"] is None and ma==ma and p<ma: res["MA10이탈"]=(p/E-1,hh)
        elif res["MA10이탈"] is None and last: res["MA10이탈"]=(p/E-1,hh)
        if res["목표+30%"] is None and p>=E*1.30: res["목표+30%"]=(p/E-1,hh)
        elif res["목표+30%"] is None and last: res["목표+30%"]=(p/E-1,hh)
        thr=max(E*0.80, peak*0.70)
        if res["손절+트레일"] is None and p<=thr: res["손절+트레일"]=(p/E-1,hh)
        elif res["손절+트레일"] is None and last: res["손절+트레일"]=(p/E-1,hh)
    return res

def run():
    d=pd.read_csv(os.path.join(HERE,"_m_all.csv"),header=None,names=["code","date","close"],dtype={"code":str})
    d["m"]=pd.to_datetime(d["date"],errors="coerce").dt.to_period("M"); d["close"]=pd.to_numeric(d["close"],errors="coerce")
    d=d.dropna(subset=["m","close"])
    px=d.pivot_table(index="m",columns="code",values="close",aggfunc="last").sort_index()
    ma10=px.rolling(10).mean()
    T=len(px.index)
    acc={r:[] for r in ["보유24M","트레일-20%","트레일-30%","MA10이탈","목표+30%","손절+트레일"]}
    holds={r:[] for r in acc}
    V=px.values; M=ma10.values
    for j in range(V.shape[1]):
        col=V[:,j]; mc=M[:,j]
        for t in range(10,T-1):
            E=col[t]
            if E!=E or E<1000: continue
            if not (mc[t]==mc[t] and mc[t-1]==mc[t-1]): continue
            # 진입: 전월 MA10 이하 → 당월 MA10 상향돌파(추세 시작)
            if not (col[t-1]<=mc[t-1] and E>mc[t]): continue
            hi=min(t+MAXH, T-1)
            win=col[t+1:hi+1]; maw=mc[t+1:hi+1]
            if len(win)==0: continue
            r=simulate_entry(E, win, maw)
            for k,v in r.items():
                if v is not None: acc[k].append(v[0]); holds[k].append(v[1])
    out={"기간":f"{px.index.min()}~{px.index.max()}","진입수":len(acc['보유24M'])}
    for r in acc:
        a=np.array(acc[r]); h=np.array(holds[r])
        if len(a)==0: continue
        mean=float(a.mean()); ann=(1+mean)**(12/max(h.mean(),1))-1
        out[r]=dict(n=len(a),mean=round(mean,4),median=round(float(np.median(a)),4),
                    win=round(float((a>0).mean()),3),big=round(float((a>=0.5).mean()),3),
                    bigloss=round(float((a<=-0.3).mean()),3),hold=round(float(h.mean()),1),ann=round(ann,4))
    return out

def _fmt(o):
    print(f"\n{'='*94}\n매도규칙 비교 · 진입=월MA10 상향돌파(추세시작) · {o['기간']} · 진입 {o['진입수']:,}건\n상폐반영 · 승자 안 자르고 총수익 극대 관점\n{'='*94}")
    print(f"  {'매도규칙':<14}{'평균수익':>9}{'중앙':>8}{'승률':>7}{'대박+50%':>9}{'큰손실-30%':>10}{'보유월':>7}{'연율화':>8}")
    order=["보유24M","트레일-30%","손절+트레일","트레일-20%","MA10이탈","목표+30%"]
    for r in order:
        s=o.get(r)
        if not s: continue
        print(f"  {r:<14}{s['mean']*100:>+8.1f}%{s['median']*100:>+7.1f}%{s['win']*100:>6.0f}%{s['big']*100:>8.0f}%{s['bigloss']*100:>9.0f}%{s['hold']:>7.1f}{s['ann']*100:>+7.1f}%")
    print("\n※ '대박+50%'=+50%↑로 끝난 비율(승자 라이딩) · '큰손실-30%'=−30%↓(손절 실패) · 연율화=평균수익을 보유기간으로 환산.")
    print("※ 월봉 해상도라 트레일은 실제보다 헐렁하게 측정 · 신호효능 · 결정·책임 본인.")

def _self_test():
    ok=tot=0
    def chk(n,c):
        nonlocal ok,tot; tot+=1; ok+=1 if c else 0; print(f"  [{'OK' if c else 'FAIL'}] {n}")
    # 100 진입, +30%까지 오르고 이후 40% 폭락 → 목표익절이 트레일보다 유리한 케이스
    E=100.0; win=np.array([110,120,130,140,84,84]); maw=np.array([100,105,110,115,120,120])
    r=simulate_entry(E,win,maw)
    chk("목표+30%: +30%에 익절", abs(r["목표+30%"][0]-0.3)<0.11)  # 130 근처
    chk("트레일-30%: 고점140 −30%=98 이탈 → 84에 청산(-16%)", r["트레일-30%"][0]<0)
    chk("보유24M: 마지막가 84(-16%)", abs(r["보유24M"][0]-(-0.16))<0.01)
    # 상폐 케이스
    r2=simulate_entry(100.0, np.array([120,np.nan,np.nan]), np.array([100,100,100]))
    chk("상폐 시 마지막가 120*0.5/100-1=-0.4", abs(r2["보유24M"][0]-(-0.4))<1e-9)
    print(f"\n셀프테스트: {ok}/{tot}"); return ok==tot

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--self-test",action="store_true"); a=ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    _fmt(run()); return 0
if __name__=="__main__": sys.exit(main())
