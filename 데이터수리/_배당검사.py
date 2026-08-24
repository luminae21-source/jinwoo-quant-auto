# -*- coding: utf-8 -*-
"""
과제 #73 — KIS 수정주가에 배당이 포함되는가?

원리
----
후방(backward) 조정에서
  · 분할·감자만 조정하면  → adj(t) = raw(t) × (상수)  → 비율이 **상수**
  · 배당까지 조정하면(TR) → adj(t) = raw(t) × Π(1 - d_i)  (t 이후 배당들)
                          → 과거 가격이 더 많이 깎이므로 비율이 **현재를 향해 상승**
                          → 연간 상승률 ≈ 배당수익률

그래서 기업행위가 없는 종목만 골라 비율의 표류(drift)를 재면 판정된다.
표류 ≈ 0  → 배당 미포함 → KOSPI(PR) 과 같은 축 → 비교 공정
표류 ≈ DIV → 배당 포함  → 전략만 배당을 먹는 비교 → 초과수익 과대평가
"""
import csv, collections, statistics as st

def load(paths, cols=("code","ym","close")):
    d={}
    for p in paths:
        with open(p,encoding="utf-8-sig",newline="") as f:
            for r in csv.DictReader(f):
                try: v=float(r[cols[2]])
                except (TypeError,ValueError): continue
                if v>0: d[(r[cols[0]].zfill(6), r[cols[1]])]=v
    return d

RAW=load(["_월봉종가캐시_KOSPI.csv","_월봉종가캐시_KOSDAQ.csv"])
ADJ=load(["데이터수리/월봉_KIS_adj_v1_2026-07-28.csv","데이터수리/_월봉_KIS_adj_2016.csv"])
print("원주가 %d셀 · 수정주가 %d셀" % (len(RAW),len(ADJ)))

# 배당수익률 (연도별 평균 DIV %)
div=collections.defaultdict(list)
for p in ("종목재무_KRX_KOSPI.csv","종목재문_KRX_KOSDAQ.csv","종목재무_KRX_KOSDAQ.csv"):
    try: f=open(p,encoding="utf-8-sig",newline="")
    except OSError: continue
    with f:
        for r in csv.DictReader(f):
            try: v=float(r.get("DIV") or "")
            except ValueError: continue
            if 0<=v<30: div[r["code"].zfill(6)].append(v)
DIV={c:st.mean(v) for c,v in div.items() if v}
print("배당수익률 있는 코드 %d" % len(DIV))

WIN_FROM="2016-01"          # 최근 구간 (수집 시점 기준 조정이 가장 촘촘)
byc=collections.defaultdict(list)
for k in RAW.keys()&ADJ.keys():
    if k[1]>=WIN_FROM: byc[k[0]].append((k[1], ADJ[k]/RAW[k]))
for c in byc: byc[c].sort()
print("겹침 코드 %d (구간 %s~)" % (len(byc),WIN_FROM))

# 기업행위 없는 종목만: 비율의 전월대비 변화가 0.5% 를 한 번도 안 넘음
clean=[]
for c,v in byc.items():
    if len(v)<36: continue
    if all(abs(v[i][1]/v[i-1][1]-1.0)<=0.005 for i in range(1,len(v))):
        clean.append(c)
print("기업행위 없는(비율 계단 0) 코드 %d" % len(clean))

rows=[]
for c in clean:
    v=byc[c]; n=len(v)
    drift=(v[-1][1]/v[0][1])**(12.0/(n-1))-1.0
    rows.append((c, drift*100, DIV.get(c), n, v[0][1], v[-1][1]))

print("\n[비율 표류(연율 %%) 분포 — 기업행위 없는 %d 코드]" % len(rows))
ds=sorted(r[1] for r in rows)
for q in (0.05,0.25,0.50,0.75,0.95):
    print("   %4.0f%% 분위  %+8.4f%%" % (q*100, ds[int(len(ds)*q)]))
print("   |표류| < 0.01%% 인 코드: %d / %d" % (sum(1 for d in ds if abs(d)<0.01), len(ds)))

wd=[r for r in rows if r[2] is not None]
if wd:
    print("\n[배당수익률 구간별 평균 표류 — 상관이 있으면 배당 포함]")
    print("   %-14s %6s %12s %12s" % ("배당수익률","코드","평균표류%","중위표류%"))
    for lo,hi,lab in ((0,0.5,"0.0~0.5%"),(0.5,1.5,"0.5~1.5%"),(1.5,3.0,"1.5~3.0%"),
                      (3.0,5.0,"3.0~5.0%"),(5.0,99,"5.0%+")):
        g=[r[1] for r in wd if lo<=r[2]<hi]
        if g: print("   %-14s %6d %+11.4f %+11.4f" % (lab,len(g),st.mean(g),st.median(g)))

print("\n[표류 절대값 상위 8 — 있으면 그게 반례]")
for c,d,dv,n,a,b in sorted(rows,key=lambda x:-abs(x[1]))[:8]:
    print("   %-8s 표류 %+8.4f%%  배당 %s  개월 %3d  비율 %.6f→%.6f"
          % (c,d,("%.2f%%"%dv) if dv is not None else "  ?  ",n,a,b))
