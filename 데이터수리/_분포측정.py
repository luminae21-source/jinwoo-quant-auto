# -*- coding: utf-8 -*-
"""패널 결함 ㉮㉯ 임계값을 정하기 전에 분포부터 잰다. (읽기 전용)"""
import csv, collections, sys

SRC = "월봉_KIS_adj_v1_2026-07-28.csv"
INT32 = 2147483647

by = collections.defaultdict(list)
with open(SRC, encoding="utf-8-sig", newline="") as f:
    for r in csv.DictReader(f):
        by[r["code"]].append((r["ym"], int(r["close"])))
for c in by: by[c].sort()
TOTROWS = sum(len(v) for v in by.values())
print("코드 %d · 행 %d" % (len(by), TOTROWS))

# ---------- (A) 동결 구간 (연속 동일 종가) ----------
runs = {}          # code -> 최장 런
runcells = collections.Counter()   # 런길이 -> 그 런에 속한 셀 수
for c, v in by.items():
    best = 1; cur = 1
    for i in range(1, len(v)):
        if v[i][1] == v[i-1][1]:
            cur += 1
        else:
            runcells[cur] += cur; best = max(best, cur); cur = 1
    runcells[cur] += cur; best = max(best, cur)
    runs[c] = best
print("\n===== (A) 연속 동일 종가 최장런 분포 =====")
h = collections.Counter()
for c, b in runs.items():
    k = 1 if b<=1 else 2 if b<=2 else 3 if b<=3 else 5 if b<=5 else 8 if b<=8 else 11 if b<=11 else 23 if b<=23 else 999
    h[k]+=1
lab={1:"런 1 (동결 없음)",2:"2",3:"3",5:"4~5",8:"6~8",11:"9~11",23:"12~23",999:"24개월 이상"}
for k in sorted(h): print("  %-14s %5d 코드" % (lab[k], h[k]))
print("\n  임계값 N (N개월 이상 연속 동일 → 마스크) 별 삭제량")
print("  %4s %10s %8s %8s" % ("N","마스크셀","비율%","전멸코드"))
for N in (3,4,6,9,12,18,24):
    cells = sum(n for L,n in runcells.items() if L>=N)
    # 전멸: 그 코드 행의 절반 이상이 마스크되는 코드 수 (근사: 최장런>=행수*0.5)
    dead = sum(1 for c,b in runs.items() if b>=N and b>=len(by[c])*0.5)
    print("  %4d %10d %8.2f %8d" % (N, cells, cells*100.0/TOTROWS, dead))

# ---------- (B) 저가 ----------
print("\n===== (B) 저가 분포 =====")
print("  %8s %10s %8s %8s %10s" % ("임계(원)","해당셀","비율%","코드수","반올림오차%"))
for th in (10,30,50,100,200,500,1000):
    cells = sum(1 for v in by.values() for _,p in v if p < th)
    cods  = sum(1 for v in by.values() if any(p < th for _,p in v))
    print("  %8d %10d %8.3f %8d %10.2f" % (th, cells, cells*100.0/TOTROWS, cods, 100.0/th))

# ---------- (C) 고가 ----------
print("\n===== (C) 고가 분포 =====")
print("  %14s %10s %8s %8s" % ("임계(원)","해당셀","비율%","코드수"))
for th in (10**6, 10**7, 10**8, 10**9, INT32):
    cells = sum(1 for v in by.values() for _,p in v if p >= th)
    cods  = sum(1 for v in by.values() if any(p >= th for _,p in v))
    print("  %14d %10d %8.3f %8d" % (th, cells, cells*100.0/TOTROWS, cods))
sat = {c: sum(1 for _,p in v if p==INT32) for c,v in by.items()}
sat = {c:n for c,n in sat.items() if n}
print("  INT32 정확히 포화: %d 코드 / %d 셀 → %s" % (len(sat), sum(sat.values()),
      ", ".join("%s(%d/%d)"%(c,n,len(by[c])) for c,n in sorted(sat.items()))))
big = sorted(((max(p for _,p in v), c) for c,v in by.items() if max(p for _,p in v)>=10**8), reverse=True)
print("  1억 이상(포화 제외):")
for mx,c in big:
    if c in sat: continue
    print("     %-8s 최대 %,d원".replace("%,d","%d") % (c, mx))
