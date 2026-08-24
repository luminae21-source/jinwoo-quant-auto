# -*- coding: utf-8 -*-
"""④ 가 진짜 결함인지, 내 임계값이 만든 허상인지 가른다."""
import csv, collections, statistics as st
def load(paths):
    d={}
    for p in paths:
        with open(p,encoding="utf-8-sig",newline="") as f:
            for r in csv.DictReader(f):
                v=float(r["close"])
                if v>0: d[(r["code"],r["ym"])]=v
    return d
kis=load(["월봉_KIS_adj_v1_2026-07-28.csv","_월봉_KIS_adj_2016.csv"])
pk =load(["_월봉종가캐시_KOSPI_adj.csv","_월봉종가캐시_KOSDAQ_adj.csv"])
ov=kis.keys()&pk.keys()
byc=collections.defaultdict(list)
for k in ov: byc[k[0]].append((k[1],kis[k]/pk[k],pk[k]))
for c in byc: byc[c].sort()

print("[BRK 민감도 — 레벨변경 임계값을 바꾸면 분류가 어떻게 움직이나]")
print("  %6s %10s %10s %10s" % ("BRK","평균구간수","1개월구간계","구간2개이하코드"))
for BRK in (0.002,0.005,0.01,0.02,0.05,0.10):
    tot=0; lone=0; few=0
    for c,v in byc.items():
        ns=1; ln=0; s=0
        idx=[]
        for i in range(1,len(v)):
            if abs(v[i][1]/v[i-1][1]-1.0)>BRK: idx.append(i)
        bounds=[0]+idx+[len(v)]
        sizes=[bounds[i+1]-bounds[i] for i in range(len(bounds)-1)]
        tot+=len(sizes); lone+=sum(1 for s2 in sizes if s2==1)
        if len(sizes)<=2: few+=1
    print("  %6.3f %10.2f %10d %10d" % (BRK,tot/len(byc),lone,few))

print("\n[모든 셀의 |배율-1| 분위 — 잡음 크기 자체를 본다]")
d=sorted(abs(r-1.0) for v in byc.values() for _,r,_ in v)
for q in (0.50,0.90,0.95,0.99,0.995,0.999):
    print("   %5.1f%% 분위  %.6f" % (q*100,d[int(len(d)*q)]))

print("\n[배율 오차 vs pykrx 가격대 — 정수 반올림 가설 검증]")
bk=collections.defaultdict(list)
for v in byc.values():
    for _,r,p in v:
        b = 100 if p<100 else 1000 if p<1000 else 10000 if p<10000 else 100000
        bk[b].append(abs(r-1.0))
print("   %10s %8s %12s %12s  (예상잡음=0.5/가격)" % ("가격대<","셀수","중위오차","95%오차"))
for b in sorted(bk):
    a=sorted(bk[b])
    print("   %10d %8d %12.6f %12.6f   %.6f" % (b,len(a),a[len(a)//2],a[int(len(a)*0.95)],0.5/(b/3)))
