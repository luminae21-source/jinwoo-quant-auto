# -*- coding: utf-8 -*-
r"""종목군_월별현황_데이터.py — 월 × 종목군 현황판 데이터.

⚠️ 이건 '판정'이 아니라 '기록'이다. 표본이 작은 칸도 그대로 보여주되 건수를 함께 적는다.
   (판정을 하려면 종목군_타당성점검.py 의 검정력 표를 먼저 볼 것)
"""
import os, sys, json, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
HERE = "/home/claude/jq"; UP = "/mnt/user-data/uploads/진우퀀트"

CHAIN = ["반도체", "특수 목적용 기계", "전자부품", "측정, 시험", "광학",
         "그외 기타 전문, 과학", "통신 및 방송 장비", "일반 목적용 기계", "전지"]

S = pd.read_csv(f"{HERE}/휩쏘_밸류교집합_이벤트.csv", dtype={"code": str})
S["code"] = S["code"].str.zfill(6)
S["연"] = S["date"].str[:4].astype(int)
S["월"] = S["date"].str[5:7].astype(int)

sec = {}
for f in ("liquidity_sector.csv", "kosdaq_industry.csv"):
    d = pd.read_csv(os.path.join(UP, f), dtype=str)
    d.columns = [c.strip().lstrip("﻿") for c in d.columns]
    if {"code", "sector"}.issubset(d.columns):
        sec.update(dict(zip(d["code"].str.zfill(6), d["sector"].astype(str))))
S["섹터"] = S["code"].map(sec)
S["체인"] = S["섹터"].fillna("").apply(lambda x: any(k in x for k in CHAIN))
S["섹터없음"] = S["섹터"].isna()
S["군"] = np.where(S["섹터없음"], "섹터불명", np.where(S["체인"], "반도체체인", "기타업종"))

C = S[S["fwd40"].notna()].copy()          # 성과 판정 가능(40봉 창완결)
D = {}


def cell(sub):
    if len(sub) == 0:
        return dict(n=0)
    c = sub["카드"] * 100; f = sub["fwd40"] * 100
    return dict(n=int(len(sub)), 카드=round(float(c.mean()), 2), 승률=round(float((c > 0).mean() * 100), 1),
                fwd40=round(float(f.mean()), 2), 갭=round(float(f.mean() - c.mean()), 2),
                목표율=round(float((sub["ex_how"] == "목표").mean() * 100), 1),
                손절율=round(float((sub["ex_how"] == "손절").mean() * 100), 1))


# ── 1. 월별 × 국면 (전체 기록)
D["월별국면"] = [dict(월=m, **{rg: int(((C["월"] == m) & (C["국면"] == rg)).sum())
                            for rg in ("실행", "주의", "관찰만")},
                    합계=int((C["월"] == m).sum())) for m in range(1, 13)]

# ── 2. 월별 × 종목군 (🟢실행 국면 — 실전 조건)
G = C[C["국면"] == "실행"].copy()
D["월별종목군"] = []
for m in range(1, 13):
    s = G[G["월"] == m]
    D["월별종목군"].append(dict(월=m, 합계=int(len(s)),
                            체인=cell(s[s["군"] == "반도체체인"]),
                            기타=cell(s[s["군"] == "기타업종"]),
                            불명=cell(s[s["군"] == "섹터불명"])))

# ── 3. 종목군 요약 (🟢실행)
D["군요약"] = [dict(군=g, **cell(G[G["군"] == g])) for g in ("반도체체인", "기타업종", "섹터불명")]
D["전체요약"] = cell(G)
D["밸류요약"] = [dict(군="밸류 태그 O", **cell(G[G["밸류여부"] & (G["태그가능"] == True)])),
               dict(군="밸류 태그 X", **cell(G[(~G["밸류여부"]) & (G["태그가능"] == True)]))]

# ── 4. 연도별 (신호 수 + 국면 + 군 구성)
yrs = []
for y in sorted(C["연"].unique()):
    s = C[C["연"] == y]
    g = s[s["국면"] == "실행"]
    yrs.append(dict(연=int(y), 합계=int(len(s)), 실행=int(len(g)),
                    체인=int((s["군"] == "반도체체인").sum()),
                    카드=round(float(g["카드"].mean() * 100), 2) if len(g) else None))
D["연도별"] = yrs

# ── 5. ①로 가는 다리 — 카드 vs 40일 갭 (월별 · 군별)
D["갭월별"] = []
for m in range(1, 13):
    s = G[G["월"] == m]
    ch, ot = s[s["군"] == "반도체체인"], s[s["군"] == "기타업종"]
    D["갭월별"].append(dict(월=m,
                          체인갭=round(float((ch["fwd40"].mean() - ch["카드"].mean()) * 100), 2) if len(ch) >= 10 else None,
                          체인n=int(len(ch)),
                          기타갭=round(float((ot["fwd40"].mean() - ot["카드"].mean()) * 100), 2) if len(ot) >= 10 else None,
                          기타n=int(len(ot))))

# ── 6. 목표 도달 속도 분포 (군별)
D["도달속도"] = []
for g in ("반도체체인", "기타업종"):
    s = G[(G["군"] == g) & (G["ex_how"] == "목표")]
    if len(s) < 20: continue
    D["도달속도"].append(dict(군=g, n=int(len(s)),
                           p=[dict(q=q, v=float(np.percentile(s["ex_bars"], q))) for q in (25, 50, 75, 90)],
                           일봉이내=round(float((s["ex_bars"] <= 2).mean() * 100), 1),
                           일주일이내=round(float((s["ex_bars"] <= 5).mean() * 100), 1)))

# ── 7. 섹터 매칭률(생존편향 고지용)
D["매칭률"] = [dict(연대=f"{d0}년대", 매칭=int((~C[(C['연'] // 10 * 10) == d0]["섹터없음"]).sum()),
                  전체=int(((C["연"] // 10 * 10) == d0).sum()))
              for d0 in sorted(set(C["연"] // 10 * 10))]
for r in D["매칭률"]:
    r["비율"] = round(r["매칭"] / r["전체"] * 100, 1)

# ── 8. 월별 갭의 연도 집중도 (계절성 착시 경고용)
D["갭집중"] = []
for m in range(1, 13):
    s_ = G[(G["월"] == m) & (G["군"] == "반도체체인")]
    if len(s_) < 10: 
        D["갭집중"].append(dict(월=m, n=int(len(s_)), 최다연도=None, 비중=None)); continue
    vc = s_["연"].value_counts()
    D["갭집중"].append(dict(월=m, n=int(len(s_)), 최다연도=int(vc.index[0]),
                          비중=round(float(vc.iloc[0] / len(s_) * 100), 0),
                          상위2=round(float(vc.iloc[:2].sum() / len(s_) * 100), 0)))

# ── 9. 섹터불명 = 생존편향 실측
D["생존편향"] = dict(
    섹터있음종목=int(C[C["섹터없음"] == False]["code"].nunique()),
    섹터불명종목=int(C[C["섹터없음"] == True]["code"].nunique()),
    섹터있음=cell(G[G["섹터없음"] == False]), 섹터불명=cell(G[G["섹터없음"] == True]))

D["메타"] = dict(전체=int(len(S)), 창완결=int(len(C)), 실행=int(len(G)),
               기간=f"{C['date'].min()} ~ {C['date'].max()}",
               체인정의=" · ".join(CHAIN))
json.dump(D, open(f"{HERE}/종목군_월별현황.json", "w"), ensure_ascii=False, indent=1)
print("저장: 종목군_월별현황.json")
print(json.dumps(D["메타"], ensure_ascii=False, indent=1))
print("\n[군요약 · 🟢실행]")
for r in D["군요약"] + D["밸류요약"]:
    print(f"  {r['군']:<12} n={r['n']:>5,} 카드 {r['카드']:>+6.2f}% 승률 {r['승률']:>5.1f}% "
          f"40일 {r['fwd40']:>+6.2f}% 갭 {r['갭']:>+6.2f}%p 목표율 {r['목표율']:>5.1f}%")
print("\n[갭 월별] 체인 / 기타")
for r in D["갭월별"]:
    print(f"  {r['월']:>2}월  체인 {str(r['체인갭']):>7} (n={r['체인n']:>3})   기타 {str(r['기타갭']):>7} (n={r['기타n']:>4})")
