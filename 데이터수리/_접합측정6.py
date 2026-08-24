# -*- coding: utf-8 -*-
"""KIS 단독으로 백테 창을 덮는가? 그리고 KIS-KIS 이음선(2015-12→2016-01)은 깨끗한가?"""
import csv, collections, statistics as st
def load(p):
    d={}
    with open(p,encoding="utf-8-sig",newline="") as f:
        for r in csv.DictReader(f):
            v=float(r["close"])
            if v>0: d[(r["code"],r["ym"])]=v
    return d
A=load("월봉_KIS_adj_v1_2026-07-28.csv"); B=load("_월봉_KIS_adj_2016.csv")
dup=A.keys()&B.keys()
print("1996-2015 파일 %d셀 · 2016+ 파일 %d셀 · 겹치는 셀 %d" % (len(A),len(B),len(dup)))
K={}; K.update(A); K.update(B)

# 실제 상장 유니버스
uni=collections.defaultdict(set)
with open("../종목시총_30년.csv",encoding="utf-8-sig",newline="") as f:
    for r in csv.DictReader(f):
        uni[r["date"][:4]].add(r["code"])
kby=collections.defaultdict(set)
for (c,y) in K: kby[y[:4]].add(c)
print("\n[KIS 단독 커버리지 (연도별, 실제상장 대비)]")
print("  %6s %9s %8s %9s" % ("연도","실제상장","KIS","커버리지"))
for y in [str(v) for v in range(2008,2027)]:
    u=uni.get(y,set())
    if not u: continue
    hit=len(u & kby.get(y,set()))
    print("  %6s %9d %8d %8.2f%%" % (y,len(u),hit,hit*100.0/len(u)))

# 이음선 검사: 월간 배율 분포를 달마다 비교
print("\n[KIS-KIS 이음선 검사 — 전월대비 배율의 이상치 비율]")
byc=collections.defaultdict(dict)
for (c,y),v in K.items(): byc[c][y]=v
def pv(y):
    Y,M=int(y[:4]),int(y[5:7]); M-=1
    if M==0: Y,M=Y-1,12
    return "%04d-%02d"%(Y,M)
res={}
for tgt in ["2014-01","2015-01","2015-06","2015-12","2016-01","2016-02","2017-01"]:
    rs=[]
    p=pv(tgt)
    for c,d in byc.items():
        if tgt in d and p in d and d[p]>0: rs.append(d[tgt]/d[p])
    if not rs: continue
    rs.sort()
    big=sum(1 for r in rs if r>1.5 or r<0.6667)
    res[tgt]=(len(rs),st.median(rs),big*100.0/len(rs))
    print("   %s  종목 %4d  중위배율 %.4f  |배율|>1.5배 비율 %5.2f%%" % (tgt,len(rs),st.median(rs),big*100.0/len(rs)))
