# -*- coding: utf-8 -*-
"""중재자(ca_flags) 적용률 측정: 배율 브레이크포인트를 CA 가 설명하는가."""
import csv, collections, statistics as st
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
    for r in csv.DictReader(f):
        ca[r["code"]].append((r["ym"],float(r["factor"]),r["type"]))
print("CA 플래그 %d코드 %d건" % (len(ca),sum(len(v) for v in ca.values())))

def near(a,b,tol=0.03): return abs(a/b-1.0)<=tol if b else False
def prev_ym(y):
    yy,mm=int(y[:4]),int(y[5:7]); mm-=1
    if mm==0: yy,mm=yy-1,12
    return "%04d-%02d"%(yy,mm)
def next_ym(y):
    yy,mm=int(y[:4]),int(y[5:7]); mm+=1
    if mm==13: yy,mm=yy+1,1
    return "%04d-%02d"%(yy,mm)

ov=KIS.keys()&PK.keys()
byc=collections.defaultdict(list)
for k in ov: byc[k[0]].append(k[1])
for c in byc: byc[c].sort()

BRK=0.005
stat=collections.Counter(); examples=collections.defaultdict(list)
for c,yms in byc.items():
    rr=[(y,KIS[(c,y)]/PK[(c,y)]) for y in yms]
    for i in range(1,len(rr)):
        f=rr[i][1]/rr[i-1][1]
        if abs(f-1.0)<=BRK: continue
        M=rr[i][0]
        # CA 조회 (±1개월)
        hit=None
        for y2,fac,t in ca.get(c,[]):
            if y2 in (M,prev_ym(M),next_ym(M)) and (near(abs(f),fac) or near(abs(f),1.0/fac)):
                hit=(y2,fac,t); break
        if not hit:
            stat["CA 설명 안 됨"]+=1
            if len(examples["미설명"])<8: examples["미설명"].append((c,M,round(f,4)))
            continue
        # 어느 쪽이 점프했나 (자기 시계열 전월대비)
        pm=prev_ym(M)
        jk=jp=None
        if (c,pm) in KIS and KIS[(c,pm)]: jk=KIS[(c,M)]/KIS[(c,pm)]
        if (c,pm) in PK  and PK[(c,pm)]:  jp=PK[(c,M)]/PK[(c,pm)]
        fac=hit[1]
        kj = jk is not None and (near(abs(jk),fac) or near(abs(jk),1.0/fac))
        pj = jp is not None and (near(abs(jp),fac) or near(abs(jp),1.0/fac))
        if kj and not pj:
            stat["KIS 가 미조정 → pykrx 신뢰"]+=1
            if len(examples["KIS미조정"])<6: examples["KIS미조정"].append((c,M,round(f,3),fac))
        elif pj and not kj:
            stat["pykrx 가 미조정 → KIS 신뢰"]+=1
            if len(examples["pykrx미조정"])<6: examples["pykrx미조정"].append((c,M,round(f,3),fac))
        elif kj and pj:
            stat["둘 다 점프(판정불가)"]+=1
        else:
            stat["CA 는 맞지만 점프 미확인"]+=1

tot=sum(stat.values())
print("\n[브레이크포인트 %d건 판정]" % tot)
for k,v in stat.most_common(): print("   %-28s %6d (%5.1f%%)" % (k,v,v*100.0/tot))
print("\n[예: pykrx 가 미조정]"); [print("   %-8s %s  배율%s  CAfactor %s"%e) for e in examples["pykrx미조정"]]
print("[예: KIS 가 미조정]");   [print("   %-8s %s  배율%s  CAfactor %s"%e) for e in examples["KIS미조정"]]
print("[예: CA 설명 안 됨]");   [print("   %-8s %s  배율%s"%e) for e in examples["미설명"]]
