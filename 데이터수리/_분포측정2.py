# -*- coding: utf-8 -*-
"""보강 측정: (1) 고가 코드가 매끄러운가 튀는가  (2) 결함 셀의 시기 분포"""
import csv, collections
SRC="월봉_KIS_adj_v1_2026-07-28.csv"; INT32=2147483647
by=collections.defaultdict(list)
with open(SRC,encoding="utf-8-sig",newline="") as f:
    for r in csv.DictReader(f): by[r["code"]].append((r["ym"],int(r["close"])))
for c in by: by[c].sort()
TOT=sum(len(v) for v in by.values())

print("===== (D) 1억 이상 코드 11개 — 매끄러운 감자조정인가, 튄 값인가 =====")
print("  %-8s %6s %14s %8s %10s %-9s" % ("코드","행","최대값","최대MoM배","최대월","포화"))
for c in sorted(by):
    v=by[c]; mx=max(p for _,p in v)
    if mx<10**8: continue
    worst=1.0; wym=""
    for i in range(1,len(v)):
        a,b=v[i-1][1],v[i][1]
        if a>0:
            r=max(b/a,a/b)
            if r>worst: worst,wym=r,v[i][0]
    print("  %-8s %6d %14d %8.2f %10s %-9s" % (c,len(v),mx,worst,wym,"예" if mx==INT32 else ""))

print("\n===== (E) 결함 셀의 시기 분포 (2010-01 기준 전/후) =====")
def split(pred):
    a=b=0
    for c,v in by.items():
        for ym,p in v:
            if pred(p):
                if ym<"2010-01": a+=1
                else: b+=1
    return a,b
for name,pred in (("<100원",lambda p:p<100),("<500원",lambda p:p<500),
                  (">=1억",lambda p:p>=10**8),("INT32포화",lambda p:p==INT32)):
    a,b=split(pred); print("  %-10s 2010이전 %6d · 2010이후 %6d" % (name,a,b))
# 동결런
pre=post=0
for c,v in by.items():
    i=0
    while i<len(v):
        j=i
        while j+1<len(v) and v[j+1][1]==v[i][1]: j+=1
        L=j-i+1
        if L>=6:
            for k in range(i,j+1):
                if v[k][0]<"2010-01": pre+=1
                else: post+=1
        i=j+1
print("  %-10s 2010이전 %6d · 2010이후 %6d" % ("동결6+",pre,post))
print("\n  (참고) 2010-01 이후 총 셀 %d / 전체 %d" %
      (sum(1 for v in by.values() for ym,_ in v if ym>="2010-01"), TOT))
