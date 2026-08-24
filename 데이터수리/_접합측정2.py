# -*- coding: utf-8 -*-
"""배율을 '구간별 상수'로 모델링해서 다시 잰다."""
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
for k in ov: byc[k[0]].append((k[1],kis[k]/pk[k]))
for c in byc: byc[c].sort()

BRK=0.005   # 전월 대비 배율이 0.5% 넘게 변하면 '레벨 변경'
def segs(v):
    """[(시작ym, 끝ym, 개수, 중위배율)] 로 끊는다."""
    out=[]; s=0
    for i in range(1,len(v)):
        a,b=v[i-1][1],v[i][1]
        if abs(b/a-1.0)>BRK:
            out.append((v[s][0],v[i-1][0],i-s,st.median([r for _,r in v[s:i]]))); s=i
    out.append((v[s][0],v[-1][0],len(v)-s,st.median([r for _,r in v[s:]])))
    return out

cls=collections.Counter(); detail=collections.defaultdict(list)
for c,v in byc.items():
    sg=segs(v)
    nseg=len(sg)
    lone=sum(1 for _,_,n,_ in sg if n==1)          # 1개월짜리 구간 = 튄 셀
    solid=[s for s in sg if s[2]>=2]
    allone=all(abs(m-1.0)<=0.005 for _,_,_,m in sg)
    if nseg==1 and allone:                  k="① 완전일치"
    elif nseg==1:                           k="② 단일상수배(앵커차)"
    elif len(solid)>=2 and nseg-lone<=3:    k="③ 구간상수배(반영시점차)"
    elif lone>=1 and len(solid)==1:         k="④ 산발이상셀"
    else:                                   k="⑤ 난동(격리)"
    cls[k]+=1; detail[k].append((c,nseg,lone,sg))
print("겹침 코드 %d · 겹침 셀 %d" % (len(byc),len(ov)))
print("\n[재분류]")
for k in ("① 완전일치","② 단일상수배(앵커차)","③ 구간상수배(반영시점차)","④ 산발이상셀","⑤ 난동(격리)"):
    print("   %-24s %5d 코드 (%5.1f%%)" % (k,cls[k],cls[k]*100.0/len(byc)))

print("\n[③ 구간상수배 — 레벨 배율이 깔끔한 유리수인가]")
lv=collections.Counter()
for c,n,l,sg in detail["③ 구간상수배(반영시점차)"]:
    for _,_,cnt,m in sg:
        if cnt>=2 and abs(m-1.0)>0.005: lv[round(m,4)]+=1
for v,n in lv.most_common(18): print("   ×%-10s %4d 구간" % (v,n))

print("\n[④ 산발이상셀 — 격리할 셀 수]")
tot=sum(l for _,_,l,_ in detail["④ 산발이상셀"])
print("   %d 코드 / %d 셀" % (cls["④ 산발이상셀"],tot))
for c,n,l,sg in sorted(detail["④ 산발이상셀"],key=lambda x:-x[2])[:8]:
    bad=[ (a,round(m,3)) for a,b,cnt,m in sg if cnt==1 ]
    print("   %-8s 이상 %2d셀 %s" % (c,l,bad[:5]))

print("\n[⑤ 난동 — 상위 12]")
for c,n,l,sg in sorted(detail["⑤ 난동(격리)"],key=lambda x:-x[1])[:12]:
    print("   %-8s 구간 %3d (1개월구간 %3d) 겹침 %3d" % (c,n,l,len(byc[c])))
