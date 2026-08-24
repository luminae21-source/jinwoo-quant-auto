# -*- coding: utf-8 -*-
import csv,collections
SRC="월봉_KIS_adj_v1_2026-07-28.csv"; INT32=2147483647
by=collections.defaultdict(list)
with open(SRC,encoding="utf-8-sig",newline="") as f:
    for r in csv.DictReader(f): by[r["code"]].append((r["ym"],int(r["close"])))
for c in by: by[c].sort()
print("===== (F) 창 시작점별 잔존 결함 =====")
print("  %-10s %8s %8s %8s %8s" % ("창시작","INT32",">=1억","<100원","동결6+"))
frz=set()
for c,v in by.items():
    i=0
    while i<len(v):
        j=i
        while j+1<len(v) and v[j+1][1]==v[i][1]: j+=1
        if j-i+1>=6:
            for k in range(i,j+1): frz.add((c,v[k][0]))
        i=j+1
for st in ("1996-01","2008-01","2010-01","2011-01"):
    a=b=d=e=0
    for c,v in by.items():
        for ym,p in v:
            if ym<st: continue
            if p==INT32: a+=1
            if p>=10**8: b+=1
            if p<100: d+=1
            if (c,ym) in frz: e+=1
    print("  %-10s %8d %8d %8d %8d" % (st,a,b,d,e))

print("\n===== (G) 2010-01 이후 <100원 셀 보유 코드 =====")
cnt=collections.Counter(); lo={}
for c,v in by.items():
    for ym,p in v:
        if ym>="2010-01" and p<100:
            cnt[c]+=1; lo[c]=min(lo.get(c,10**9),p)
print("  코드 %d개 · 셀 %d개" % (len(cnt),sum(cnt.values())))
for c,n in cnt.most_common(12): print("     %-8s %3d셀  최저 %d원" % (c,n,lo[c]))

print("\n===== (H) 2010-01 이후 동결6+ 코드 =====")
c2=collections.Counter()
for (c,ym) in frz:
    if ym>="2010-01": c2[c]+=1
print("  코드 %d개 · 셀 %d개" % (len(c2),sum(c2.values())))
for c,n in c2.most_common(12): print("     %-8s %3d셀 / 전체 %d행" % (c,n,len(by[c])))
