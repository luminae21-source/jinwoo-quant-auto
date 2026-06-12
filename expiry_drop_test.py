#!/usr/bin/env python3
# -*- coding: utf-8 -*-
# 가설: 지수 급락은 파생 만기일(한국=둘째 목요일) 직전 창에 군집한다.
# 창 정의: 1) T-7..T-1(7거래일 전부터) 2) T-5..T-1(5거래일 전부터). T0=만기일 별도표시.
# 데이터(샌드박스 가용): kosdaq150_index.csv 일봉 + vkospi_daily.csv(KOSPI 스트레스 프록시).
# 정직: KOSPI200 일별 레벨은 폴더에 없음 -> KOSDAQ150로 검증 + VKOSPI 교차. KOSPI 원지수는 PC fetch(주석).
import csv, sys
from datetime import date, timedelta
from math import comb

BASE = "/sessions/confident-jolly-brown/mnt/Desktop--진우퀀트/"

def load_idx(f, dc=0, vc=1):
    out=[]
    for r in list(csv.reader(open(BASE+f,encoding="utf-8-sig")))[1:]:
        s=str(r[dc])[:10]; y,m,d=s.split("-")
        try: out.append((date(int(y),int(m),int(d)), float(r[vc])))
        except: pass
    out.sort(); return out

def second_thursday(y,m):
    d=date(y,m,1)
    # 첫 목요일
    first_thu = d + timedelta(days=(3-d.weekday())%7)
    return first_thu + timedelta(days=7)

def expiry_dates(d0,d1):
    out=[]
    y,m=d0.year,d0.month
    while date(y,m,1)<=d1:
        e=second_thursday(y,m)
        if d0<=e<=d1: out.append(e)
        m+=1
        if m>12: m=1; y+=1
    return out

def binom_tail(k,n,p):
    # P(X>=k) under Binom(n,p)
    return sum(comb(n,i)*p**i*(1-p)**(n-i) for i in range(k,n+1))

def analyze(series, label, drop_def):
    dates=[d for d,_ in series]; vals=[v for _,v in series]
    rets=[None]+[(vals[i]/vals[i-1]-1) for i in range(1,len(vals))]
    pos={d:i for i,d in enumerate(dates)}
    # 급락 플래그
    valid=[r for r in rets if r is not None]
    valid_sorted=sorted(valid)
    p5=valid_sorted[int(0.05*len(valid_sorted))]
    p10=valid_sorted[int(0.10*len(valid_sorted))]
    def is_drop(r):
        if r is None: return False
        if drop_def=="abs2": return r<=-0.02
        if drop_def=="p5":  return r<=p5
        if drop_def=="p10": return r<=p10
    flags=[is_drop(r) for r in rets]
    # 만기일 -> 거래일 인덱스(없으면 직전 거래일)
    exps=expiry_dates(dates[0],dates[-1])
    exp_idx=[]
    for e in exps:
        if e in pos: exp_idx.append(pos[e])
        else:
            cand=[i for i,d in enumerate(dates) if d<e]
            if cand: exp_idx.append(cand[-1])
    # 각 거래일에 'T-minus(다음 만기까지 거래일 수)' 부여
    tminus=[None]*len(dates)
    for ei in exp_idx:
        for k in range(0,12):           # T0..T-11
            j=ei-k
            if j>=0 and (tminus[j] is None or k<tminus[j]):
                tminus[j]=k
    def window_stats(lo,hi):  # 거래일 T-hi..T-lo 포함 (lo<=hi); T0 별도
        in_w=[i for i in range(len(dates)) if tminus[i] is not None and lo<=tminus[i]<=hi and rets[i] is not None]
        out_w=[i for i in range(len(dates)) if rets[i] is not None and i not in set(in_w)]
        di=sum(flags[i] for i in in_w); do=sum(flags[i] for i in out_w)
        ni=len(in_w); no=len(out_w)
        pin=di/ni if ni else 0; pout=do/no if no else 0
        base_rate=(di+do)/(ni+no)
        lift=pin/base_rate if base_rate>0 else 0
        # 이항검정: 창 안 급락수 di ~ Binom(ni, base_rate). 상단꼬리 p
        pval=binom_tail(di,ni,base_rate) if ni else 1.0
        return ni,di,pin,no,do,pout,lift,pval
    print("\n===== [%s] 급락정의=%s (전체 급락일 %d/%d=%.1f%%) ====="%(label,drop_def,sum(flags),len(valid),100*sum(flags)/len(valid)))
    print("  만기 수=%d (둘째 목요일)"%len(exp_idx))
    for name,(lo,hi) in [("T-7..T-1",(1,7)),("T-5..T-1",(1,5)),("T-7..T0(만기포함)",(0,7)),("T-5..T0(만기포함)",(0,5))]:
        ni,di,pin,no,do,pout,lift,pval=window_stats(lo,hi)
        flag="★군집" if (lift>=1.2 and pval<0.10) else ("(약)" if lift>=1.1 else "")
        print("  %-16s 창내 급락 %2d/%-3d=%4.1f%% | 창외 %4.1f%% | lift %4.2f | p=%.3f %s"%(name,di,ni,100*pin,100*pout,lift,pval,flag))

def main():
    kq=load_idx("kosdaq150_index.csv")
    analyze(kq,"KOSDAQ150 지수","abs2")
    analyze(kq,"KOSDAQ150 지수","p5")
    analyze(kq,"KOSDAQ150 지수","p10")
    # VKOSPI: 급등(=KOSPI 스트레스)을 '급락 프록시'로. 일변화율 상단을 drop처럼 처리.
    vk=load_idx("vkospi_daily.csv")
    # VKOSPI는 부호 반대 -> -일변화율을 ret로 넣어 동일 코드 재사용(VKOSPI +급등 = 음의 ret)
    vk_inv=[(d,-v) for d,v in vk]  # 레벨 부호 반전: VKOSPI 상승=지수하락 방향
    analyze(vk_inv,"VKOSPI 급등(KOSPI 스트레스 프록시)","p5")
    analyze(vk_inv,"VKOSPI 급등(KOSPI 스트레스 프록시)","p10")

if __name__=="__main__":
    main()
