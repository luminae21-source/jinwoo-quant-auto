# -*- coding: utf-8 -*-
"""미설명 브레이크포인트를 성격별로 쪼갠다."""
import csv, collections
def load(paths):
    d={}
    for p in paths:
        with open(p,encoding="utf-8-sig",newline="") as f:
            for r in csv.DictReader(f):
                v=float(r["close"])
                if v>0: d[(r["code"],r["ym"])]=v
    return d
KIS=load(["월봉_KIS_adj_v1_2026-07-28.csv","_월봉_KIS_adj_2016.csv"])
PK =load(["_월봉종가캐시_KOSPI_adj.csv","_월봉종가캐시_KOSDAQ_adj.csv"])
ca=collections.defaultdict(list)
with open("ca_flags.csv",encoding="utf-8-sig",newline="") as f:
    for r in csv.DictReader(f): ca[r["code"]].append((r["ym"],float(r["factor"])))
def near(a,b,t=0.03): return abs(a/b-1.0)<=t if b else False
def pv(y):
    Y,M=int(y[:4]),int(y[5:7]); M-=1
    if M==0: Y,M=Y-1,12
    return "%04d-%02d"%(Y,M)
def nx(y):
    Y,M=int(y[:4]),int(y[5:7]); M+=1
    if M==13: Y,M=Y+1,1
    return "%04d-%02d"%(Y,M)
ov=KIS.keys()&PK.keys()
byc=collections.defaultdict(list)
for k in ov: byc[k[0]].append(k[1])
for c in byc: byc[c].sort()
LAST=max(y for _,y in ov)
print("겹침 마지막 월: %s (이 달은 진행 중 → 별도 분류)" % LAST)

def intlike(f):
    """정수배(2~20) 또는 그 역수에 가까운가 = CA 서명"""
    for R in range(2,21):
        if near(abs(f),R) or near(abs(f),1.0/R): return R
    return None

cat=collections.Counter(); ex=collections.defaultdict(list)
for c,yms in byc.items():
    rr=[(y,KIS[(c,y)]/PK[(c,y)]) for y in yms]
    for i in range(1,len(rr)):
        f=rr[i][1]/rr[i-1][1]; M=rr[i][0]
        if abs(f-1.0)<=0.005: continue
        hit=any(y2 in (M,pv(M),nx(M)) and (near(abs(f),fa) or near(abs(f),1.0/fa))
                for y2,fa in ca.get(c,[]))
        if hit: cat["A. CA 로 설명됨"]+=1; continue
        if M==LAST: cat["B. 마지막달 스냅샷차"]+=1; continue
        R=intlike(f)
        if R: 
            cat["C. 정수배지만 CA기록 없음"]+=1
            if len(ex["C"])<8: ex["C"].append((c,M,round(f,4),R))
        elif abs(f-1.0)<=0.05:
            cat["D. 5%% 이내 소차"]+=1
            if len(ex["D"])<5: ex["D"].append((c,M,round(f,4),0))
        else:
            cat["E. 정체불명 대형차"]+=1
            if len(ex["E"])<8: ex["E"].append((c,M,round(f,4),0))
tot=sum(cat.values())
print("\n[브레이크포인트 %d건]" % tot)
for k,v in cat.most_common(): print("   %-26s %6d (%5.1f%%)" % (k.replace("%%","%"),v,v*100.0/tot))
print("\n[C 예: 정수배인데 CA 기록 없음 — ca_flags 누락 의심]")
for c,M,f,R in ex["C"]: print("   %-8s %s  배율 %-9s ≈ %d배" % (c,M,f,R))
print("\n[E 예: 정체불명 대형차 — 격리 후보]")
for c,M,f,_ in ex["E"]: print("   %-8s %s  배율 %s" % (c,M,f))
print("\n[D 예: 5%% 이내]")
for c,M,f,_ in ex["D"]: print("   %-8s %s  배율 %s" % (c,M,f))
