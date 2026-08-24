# -*- coding: utf-8 -*-
"""#73 재검사 — 선택 편향 배제.

앞 검사는 '비율 계단이 없는 종목'만 골랐다. 배당 조정이 있었다면 배당락 달에
계단이 생겨 그 종목이 걸러졌을 것이므로, 결론이 표본 선택에 의해 만들어졌을 수 있다.

그래서 이번엔 **거르지 않는다.** 고배당 종목 전체를 놓고
  ① 비율에 계단이 아예 없는 종목이 몇 %인가
  ② 계단이 있다면 그게 배당락 시기(한국은 대부분 12월말)에 몰려 있는가
  ③ 배당수익률과 '12월 계단 크기' 가 비례하는가
를 본다. 배당이 조정돼 있으면 ②③ 이 반드시 나타난다.
"""
import csv, collections, statistics as st

def load(paths):
    d={}
    for p in paths:
        with open(p,encoding="utf-8-sig",newline="") as f:
            for r in csv.DictReader(f):
                try: v=float(r["close"])
                except (TypeError,ValueError): continue
                if v>0: d[(r["code"].zfill(6), r["ym"])]=v
    return d
RAW=load(["_월봉종가캐시_KOSPI.csv","_월봉종가캐시_KOSDAQ.csv"])
ADJ=load(["데이터수리/월봉_KIS_adj_v1_2026-07-28.csv","데이터수리/_월봉_KIS_adj_2016.csv"])

div=collections.defaultdict(list)
for p in ("종목재무_KRX_KOSPI.csv","종목재무_KRX_KOSDAQ.csv"):
    with open(p,encoding="utf-8-sig",newline="") as f:
        for r in csv.DictReader(f):
            try: v=float(r.get("DIV") or "")
            except ValueError: continue
            if 0<=v<30: div[r["code"].zfill(6)].append(v)
DIV={c:st.mean(v) for c,v in div.items() if v}

byc=collections.defaultdict(list)
for k in RAW.keys()&ADJ.keys():
    if k[1]>="2016-01": byc[k[0]].append((k[1], ADJ[k]/RAW[k]))
for c in byc: byc[c].sort()

STEP=0.003     # 0.3% 넘는 비율 변화를 '계단' 으로 (배당락은 보통 0.5~3%)
print("=== ① 고배당 종목에 비율 계단이 있는가 (거르지 않음) ===")
print("   %-14s %6s %10s %12s" % ("배당수익률","코드","계단0인비율","평균계단수"))
for lo,hi,lab in ((0,0.5,"0.0~0.5%"),(0.5,1.5,"0.5~1.5%"),(1.5,3.0,"1.5~3.0%"),
                  (3.0,5.0,"3.0~5.0%"),(5.0,99,"5.0%+")):
    g=[c for c in byc if DIV.get(c) is not None and lo<=DIV[c]<hi and len(byc[c])>=36]
    if not g: continue
    nz=0; tot=[]
    for c in g:
        v=byc[c]
        k=sum(1 for i in range(1,len(v)) if abs(v[i][1]/v[i-1][1]-1.0)>STEP)
        tot.append(k)
        if k==0: nz+=1
    print("   %-14s %6d %9.1f%% %12.2f" % (lab,len(g),nz*100.0/len(g),st.mean(tot)))

print("\n=== ② 계단이 배당락 시기(1월)에 몰리는가 — 월별 계단 발생 분포 ===")
mon=collections.Counter(); tot=0
for c,v in byc.items():
    if len(v)<36: continue
    for i in range(1,len(v)):
        if abs(v[i][1]/v[i-1][1]-1.0)>STEP:
            mon[v[i][0][5:7]]+=1; tot+=1
print("   총 계단 %d건" % tot)
for m in ["%02d"%i for i in range(1,13)]:
    bar="█"*int(mon[m]*40.0/max(mon.values())) if mon else ""
    print("   %s월 %5d (%4.1f%%) %s" % (m,mon[m],mon[m]*100.0/max(tot,1),bar))

print("\n=== ③ 고배당(3%%+) 종목의 1월 비율 변화 — 배당이면 배당률만큼 나와야 함 ===")
hi=[c for c in byc if DIV.get(c,0)>=3.0 and len(byc[c])>=36]
print("   대상 %d 코드" % len(hi))
jan=[]
for c in hi:
    for (ym,r),(pym,pr) in zip(byc[c][1:],byc[c][:-1]):
        if ym.endswith("-01"): jan.append(r/pr-1.0)
if jan:
    jan.sort()
    print("   1월 비율변화 표본 %d개" % len(jan))
    for q in (0.05,0.25,0.50,0.75,0.95):
        print("      %4.0f%% 분위 %+9.5f%%" % (q*100, jan[int(len(jan)*q)]*100))
    print("   평균 %+.5f%% · |변화|>0.3%% 인 비율 %.1f%%"
          % (st.mean(jan)*100, sum(1 for x in jan if abs(x)>0.003)*100.0/len(jan)))
    print("   → 배당이 조정돼 있으면 평균이 +3%% 근처여야 한다.")
