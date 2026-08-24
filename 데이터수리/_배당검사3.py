# -*- coding: utf-8 -*-
"""#73 후속 — 배당을 양쪽에서 빼면 누가 더 손해인가?

앞서 나는 "배당 미확인은 결론을 나쁘게 만들 수만 있다"고 했다. 그건 틀렸다.
둘 다 PR(배당 제외) 로 확인됐으므로 상대비교는 공정하다. 그런데 멀티팩터 신호는
**div(배당수익률)를 4개 팩터 중 하나로 쓴다.** 즉 전략은 의도적으로 고배당주에 기울어져 있다.

배당을 양쪽에서 빼면, 배당이 더 많은 쪽이 더 많이 손해다.
→ 전략 포트폴리오의 배당수익률이 시장보다 높으면, 위 −1.9~−3.6%p 는
   **실제보다 전략에게 불리하게 잡힌 것**이다.

여기서는 선택 종목의 배당수익률과 시장(top100 시총가중) 배당수익률을 실측한다.
"""
import csv, collections, statistics as st

PAN="이중창_20260808_1533/panel_kis.csv"
rows=collections.defaultdict(list)
with open(PAN,encoding="utf-8-sig",newline="") as f:
    for r in csv.DictReader(f):
        try:
            rows[r["ym"]].append((r["code"].zfill(6),
                {k: (float(r[k]) if r[k] not in ("","nan") else None)
                 for k in ("div","bp","ep","roe")}))
        except (KeyError,ValueError): pass
print("패널 %d개월" % len(rows))

# 시총 (시장 배당수익률 가중용)
mc={}
with open("종목시총_30년.csv",encoding="utf-8-sig",newline="") as f:
    for r in csv.DictReader(f):
        try: mc[(r["code"].zfill(6), r["date"][:7])]=float(r["mcap"])
        except (ValueError,TypeError): pass

def zs(vals):
    v=[x for x in vals if x is not None]
    if len(v)<10: return None
    m=st.mean(v); s=st.pstdev(v)
    return (m,s if s>0 else None)

sel_div=collections.defaultdict(list); mkt_div=[]; mkt_w=[]
for ym in sorted(rows):
    if ym<"2010-01": continue
    ent=rows[ym]
    stats={k:zs([d[k] for _,d in ent]) for k in ("div","bp","ep","roe")}
    if any(v is None or v[1] is None for v in stats.values()): continue
    scored=[]
    for c,d in ent:
        if any(d[k] is None for k in ("div","bp","ep","roe")): continue
        s=st.mean([(d[k]-stats[k][0])/stats[k][1] for k in ("div","bp","ep","roe")])
        scored.append((s,c,d["div"]))
    if len(scored)<50: continue
    scored.sort(reverse=True)
    for N in (10,20,30):
        sel_div[N].append(st.mean([x[2] for x in scored[:N]]))
    # 시장: 그 달 패널 전체 시총가중 배당수익률
    num=den=0.0
    for _,c,dv in scored:
        w=mc.get((c,ym))
        if w: num+=w*dv; den+=w
    if den>0: mkt_div.append(num/den)
    mkt_w.append(st.mean([x[2] for x in scored]))

print("\n[2010-01 이후 %d개월 평균 배당수익률 %%]" % len(mkt_div))
print("   시장(패널 시총가중)      %.3f%%" % st.mean(mkt_div))
print("   시장(패널 단순평균)      %.3f%%" % st.mean(mkt_w))
for N in (10,20,30):
    d=st.mean(sel_div[N])
    print("   선택 N=%-3d              %.3f%%   → 시총가중 대비 %+.3f%%p" % (N,d,d-st.mean(mkt_div)))
print("\n   ⚠️ 이 차이는 '배당을 양쪽에서 빼서 잃은 것'의 차이다.")
print("      전략이 더 높으면 B-1q 의 열세폭은 실제보다 과장돼 있다.")
