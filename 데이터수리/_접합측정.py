# -*- coding: utf-8 -*-
"""KIS 패널 vs pykrx 파생 패널 — 겹침 구간 배율 분포. (읽기 전용, 임계값 정하기 전 측정)"""
import csv, collections, statistics as st

def load(paths):
    d = {}
    for p in paths:
        with open(p, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                v = float(r["close"])
                if v > 0: d[(r["code"], r["ym"])] = v
    return d

kis = load(["월봉_KIS_adj_v1_2026-07-28.csv", "_월봉_KIS_adj_2016.csv"])
pk  = load(["_월봉종가캐시_KOSPI_adj.csv", "_월봉종가캐시_KOSDAQ_adj.csv"])
print("KIS 셀 %d · pykrx 셀 %d" % (len(kis), len(pk)))

ov = kis.keys() & pk.keys()
print("겹침 셀 %d · 겹침 코드 %d" % (len(ov), len({c for c, _ in ov})))

byc = collections.defaultdict(list)
for k in ov:
    byc[k[0]].append((k[1], kis[k] / pk[k]))
for c in byc: byc[c].sort()

# 셀 단위 일치율
tol = collections.Counter()
for c, v in byc.items():
    for _, r in v:
        d = abs(r - 1.0)
        tol["0.1%" if d <= 0.001 else "1%" if d <= 0.01 else "5%" if d <= 0.05 else
            "50%" if d <= 0.5 else "그이상"] += 1
print("\n[셀 단위 배율 오차]")
for k in ("0.1%", "1%", "5%", "50%", "그이상"):
    print("   %-6s %8d (%5.2f%%)" % (k, tol[k], tol[k]*100.0/len(ov)))

# 코드 단위 분류
CLEAN = CONST = VARY = 0
consts = []; varies = []
for c, v in byc.items():
    rs = [r for _, r in v]
    med = st.median(rs)
    spread = max(rs)/min(rs)          # 배율이 상수면 1.0 에 가깝다
    if all(abs(r-1.0) <= 0.01 for r in rs):
        CLEAN += 1
    elif spread <= 1.01:              # 상수배 (재척도 가능)
        CONST += 1; consts.append((c, med, len(v), spread))
    else:
        VARY += 1; varies.append((c, med, len(v), spread))
print("\n[코드 단위 분류]  총 %d 코드" % len(byc))
print("   ① 일치(모든 셀 ±1%%)        %5d" % CLEAN)
print("   ② 상수배 불일치(재척도 가능) %5d" % CONST)
print("   ③ 비상수(격리 대상)          %5d" % VARY)

print("\n[② 상수배 — 배율 상위 20]")
for c, m, n, s in sorted(consts, key=lambda x: -abs(x[1]-1))[:20]:
    print("   %-8s 배율 %10.4f  겹침 %3d  퍼짐 %.5f" % (c, m, n, s))
print("\n[② 배율 값 빈도 (상수배 코드)]")
vc = collections.Counter(round(m, 4) for _, m, _, _ in consts)
for v, n in vc.most_common(15): print("   ×%-10s %4d 코드" % (v, n))

print("\n[③ 비상수 — 퍼짐 상위 20]")
for c, m, n, s in sorted(varies, key=lambda x: -x[3])[:20]:
    print("   %-8s 중위배율 %10.4f  겹침 %3d  퍼짐 %12.2f" % (c, m, n, s))
