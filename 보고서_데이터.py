# -*- coding: utf-8 -*-
"""완성본 보고서용 차트 데이터 산출 — 전부 실제 산출물에서만 읽는다. 임의 수치 없음."""
import os, sys, json, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
HERE = "/home/claude/jq"; UP = "/mnt/user-data/uploads/진우퀀트"
D = {}

# ── 원천
P1 = pd.read_csv(f"{HERE}/휩쏘_2단청산_이벤트.csv", dtype={"code": str})
PB = pd.read_csv(f"{HERE}/휩쏘_2단청산_보강.csv", dtype={"code": str})
JA = pd.read_csv(f"{HERE}/휩쏘_1월앵커_이벤트.csv", dtype={"code": str})
VS = pd.read_csv(f"{HERE}/휩쏘_밸류교집합_이벤트.csv", dtype={"code": str})
LG = pd.read_csv(f"{UP}/휩쏘_역사원장.csv", dtype={"code": str})
LG.columns = [c.strip().lstrip("﻿") for c in LG.columns]
OB = pd.read_csv(f"{HERE}/휩쏘_원장_2단전환_20260802.csv", dtype={"code": str})
IX = pd.read_csv(f"{UP}/kospi_index_daily.csv"); IX.columns = [c.strip().lstrip("﻿") for c in IX.columns]

for df in (P1, JA, VS):
    df["연"] = (df["출발일"] if "출발일" in df else df["date"]).astype(str).str[:4].astype(int)
VS["연"] = VS["date"].str[:4].astype(int)
C1 = P1[P1["창완결_126"] == True].copy()
VC = VS[VS["fwd40"].notna()].copy()
VT = VC[VC["태그가능"] == True].copy()


def boot(a, yrs, n=6000, seed=91):
    a = np.asarray(a, float); yrs = np.asarray(yrs)
    rng = np.random.default_rng(seed); ys = np.array(sorted(set(yrs)))
    ix = {y: np.where(yrs == y)[0] for y in ys}; o = np.empty(n)
    for i in range(n):
        p = rng.choice(ys, size=len(ys), replace=True)
        s = np.concatenate([ix[y] for y in p]); o[i] = np.nanmean(a[s])
    return float(np.percentile(o, 2.5) * 100), float(np.percentile(o, 97.5) * 100)


def st(x):
    x = pd.Series(x).dropna()
    return dict(n=int(len(x)), mean=round(x.mean() * 100, 2), med=round(x.median() * 100, 2),
                win=round((x > 0).mean() * 100, 1))

# ── 1. 국면 게이트 (A형 전량, 40봉 창완결 = 인수인계 문서 기준)
A = VC[VC["신호"] == "A"]
g1 = []
for rg in ("실행", "주의", "관찰만"):
    s = A[A["국면"] == rg]
    lo, hi = boot(s["카드"], s["연"])
    g1.append(dict(국면=rg, **st(s["카드"]), lo=round(lo, 2), hi=round(hi, 2)))
D["국면게이트"] = g1

# ── 2. 간극의 정체 (126봉 창완결 · 실행)
G1 = C1[C1["국면"] == "실행"]
D["간극"] = dict(고점6M=round(G1["고점6M"].mean() * 100, 1),
                카드=round(G1["P0_H126"].mean() * 100, 2),
                이단=round(G1["P1_T12_H126_be"].mean() * 100, 2),
                n=int(len(G1)),
                회수율=round((G1["P1_T12_H126_be"].mean() - G1["P0_H126"].mean())
                          / (G1["고점6M"].mean() - G1["P0_H126"].mean()) * 100, 1))

# ── 3. 트레일 폭 민감도 (실행 · be모드 · H126)
base = G1["P0_H126"].values; yrs = G1["연"].values
tr = []
for t in (10, 12, 15, 20, 25):
    col = f"P1_T{t}_H126_be"
    d = (G1[col].values - base)
    lo, hi = boot(d, yrs)
    tr.append(dict(트레일=t, delta=round(np.nanmean(d) * 100, 2), lo=round(lo, 2), hi=round(hi, 2),
                   유의=bool(lo > 0)))
D["트레일민감도"] = tr

# ── 4. 잔여 50% 분포 (로또 구조)
H = G1[G1["P0_how"] == "목표"]
rr = (H["P1대표_잔여수익"].dropna() * 100)
D["잔여분포"] = dict(n=int(len(rr)),
                  p=[dict(q=q, v=round(float(np.percentile(rr, q)), 1)) for q in (5, 10, 25, 50, 75, 90, 95, 99)],
                  mean=round(float(rr.mean()), 2), win=round(float((rr > 0).mean() * 100), 1),
                  top5기여=round(float(rr.nlargest(max(1, int(len(rr) * .05))).sum() / len(rr)), 2))

# ── 5. 1월 앵커 정책 비교 (실행)
GJ = JA[JA["국면"] == "실행"]
pol = [("현행 카드", "B0_카드"), ("2단 (126봉)", "B0b_2단126"),
       ("1월 데드라인", "A2_2단1월"), ("4월 데드라인", "A3_2단4월"),
       ("잔여 1월보유", "E1_잔여보유1월"), ("잔여 4월보유", "E2_잔여보유4월"),
       ("밸류분기", "E3_잔여보유밸류분기"), ("달력보유 4월", "C2_달력4월")]
bj = GJ["B0_카드"].values
D["1월앵커"] = []
for nm, col in pol:
    if col not in GJ: continue
    lo, hi = boot(GJ[col].values - bj, GJ["연"].values)
    D["1월앵커"].append(dict(정책=nm, **st(GJ[col]), delta=round((GJ[col].mean() - bj.mean()) * 100, 2),
                           lo=round(lo, 2), hi=round(hi, 2)))
D["1월앵커_데드라인발동"] = int((JA["B0b_how"] == "2단데드라인").sum())
D["1월앵커_잔여생존"] = int((JA["B0b_how"] == "2단트레일").sum())
D["1월앵커_n"] = int(len(JA))

# ── 6. S2 미달 항목별 (실행)
GS = VC[VC["국면"] == "실행"]
s2 = GS[GS["신호"] == "S2"]
rows = []
for m, ss in s2.groupby(s2["미달"].fillna("")):
    if len(ss) < 30: continue
    lo, hi = boot(ss["카드"], ss["연"])
    rows.append(dict(미달=m, **st(ss["카드"]), lo=round(lo, 2), hi=round(hi, 2), 유의=bool(lo > 0),
                     이단=round(ss["이단"].mean() * 100, 2)))
rows.sort(key=lambda r: -r["mean"])
D["S2미달항목"] = rows
aa = GS[GS["신호"] == "A"]
lo, hi = boot(aa["카드"], aa["연"])
D["S2기준A"] = dict(**st(aa["카드"]), lo=round(lo, 2), hi=round(hi, 2),
                  이단=round(aa["이단"].mean() * 100, 2))
lo, hi = boot(s2["카드"], s2["연"])
D["S2전체"] = dict(**st(s2["카드"]), lo=round(lo, 2), hi=round(hi, 2),
                 이단=round(s2["이단"].mean() * 100, 2))

# ── 7. 밸류 × 등급 (실행)
GV = VT[VT["국면"] == "실행"]
mat = []
for gd in ("정식A", "S2-α", "S2-β", "S2-γ"):
    sub = GV[GV["등급"] == gd]
    if len(sub) < 25: continue
    o_, x_ = sub[sub["밸류여부"]], sub[~sub["밸류여부"]]
    mat.append(dict(등급=gd, 밸류O=st(o_["카드"]), 밸류X=st(x_["카드"]),
                    diff=round((o_["카드"].mean() - x_["카드"].mean()) * 100, 2)))
D["밸류등급"] = mat

# ── 8. 밸류 × 국면
mat2 = []
for rg in ("실행", "주의", "관찰만"):
    sub = VT[VT["국면"] == rg]
    o_, x_ = sub[sub["밸류여부"]], sub[~sub["밸류여부"]]
    mat2.append(dict(국면=rg, 밸류O=st(o_["카드"]), 밸류X=st(x_["카드"])))
D["밸류국면"] = mat2

# ── 9. 태그별
tg = []
for t in ("저PBR", "저PER", "배당2%+"):
    s = GV[GV["밸류"].fillna("").str.contains(t, regex=False)]
    lo, hi = boot(s["카드"], s["연"])
    tg.append(dict(태그=t, **st(s["카드"]), lo=round(lo, 2), hi=round(hi, 2)))
s = GV[GV["밸류"].fillna("").str.count("·") >= 1]
lo, hi = boot(s["카드"], s["연"])
tg.append(dict(태그="2개 이상", **st(s["카드"]), lo=round(lo, 2), hi=round(hi, 2)))
D["밸류태그"] = tg

# ── 10. 최상/최하 셀
best = GV[GV["밸류여부"] & GV["등급"].isin(["정식A", "S2-α"])]
worst = VT[(VT["국면"] != "실행") & (~VT["밸류여부"])]
lo1, hi1 = boot(best["카드"], best["연"]); lo2, hi2 = boot(worst["카드"], worst["연"])
D["셀"] = dict(최상=dict(**st(best["카드"]), lo=round(lo1, 2), hi=round(hi1, 2),
                       이단=round(best["이단"].mean() * 100, 2)),
              최하=dict(**st(worst["카드"]), lo=round(lo2, 2), hi=round(hi2, 2)),
              모수=int(len(VT)), 빈도=round(len(best) / len(VT) * 100, 1))

# ── 11. 깔때기 (실행국면 · 재무판정가능 기준)
D["깔때기"] = [dict(단계="전체 휩쏘 신호(A+S2)", n=int(len(VT))),
             dict(단계="🟢실행 국면", n=int((VT["국면"] == "실행").sum())),
             dict(단계="정식A 또는 S2-α", n=int(len(GV[GV["등급"].isin(["정식A", "S2-α"])]))),
             dict(단계="+ 밸류 태그", n=int(len(best)))]

# ── 12. 5년 구간별 (실행 · A / S2)
dec = []
for d0 in range(1995, 2030, 5):
    sa = GS[(GS["신호"] == "A") & (GS["연"] // 5 * 5 == d0)]
    ss = GS[(GS["신호"] == "S2") & (GS["연"] // 5 * 5 == d0)]
    if len(sa) + len(ss) == 0: continue
    last = min(d0 + 4, int(GS["연"].max()))
    dec.append(dict(구간=f"{d0}–{str(last)[2:]}", A=round(sa["카드"].mean() * 100, 2) if len(sa) else None,
                    An=int(len(sa)), S2=round(ss["카드"].mean() * 100, 2) if len(ss) else None,
                    S2n=int(len(ss))))
D["5년구간"] = dec

# ── 13. 지수 월별 계절성 (형 아버지 사이클)
IX["Date"] = pd.to_datetime(IX["Date"]); IX = IX.sort_values("Date")
mo = IX.set_index("Date")["Close"].astype(float).resample("ME").last().dropna()
r = mo.pct_change().dropna()
sea = []
for m in range(1, 13):
    x = r[r.index.month == m]
    sea.append(dict(월=m, 평균=round(float(x.mean() * 100), 2), 플러스율=round(float((x > 0).mean() * 100), 0),
                    n=int(len(x))))
D["계절성"] = sea
D["계절성_기간"] = f"{mo.index[0].strftime('%Y-%m')} ~ {mo.index[-1].strftime('%Y-%m')}"

# ── 14. 현재 원장 (7/31)
done = OB[OB["목표도달일"].notna() & (OB["목표도달일"].astype(str) != "")]
D["원장"] = dict(총=int(len(OB)), 목표달성=int(len(done)), 관찰중=int(len(OB) - len(done)),
               구카드=round(done["카드_구(전량)"].mean() * 100, 2),
               신2단=round(done["카드_신(2단·현재평가)"].mean() * 100, 2),
               종목=[dict(name=r["name"], 실현=round(r["실현_50%"] * 100, 1),
                        잔여=round(r["잔여_평가"] * 100, 1),
                        여유=round((r["잔여_트레일선"] / r["현재가"] - 1) * 100, 1))
                    for _, r in done.sort_values("잔여_평가", ascending=False).head(29).iterrows()])

# ── 15. 표본 규모
D["표본"] = dict(전체=int(len(VS)), A=int((VS["신호"] == "A").sum()), S2=int((VS["신호"] == "S2").sum()),
               원장A=int((LG["유형"] == "A").sum()), 원장B=int((LG["유형"] == "B").sum()),
               A40완결=int(len(A)), 재무판정가능=int(len(VT)),
               기간=f"{VS['date'].min()} ~ {VS['date'].max()}")

json.dump(D, open(f"{HERE}/보고서_데이터.json", "w"), ensure_ascii=False, indent=1)
print(json.dumps({k: (v if not isinstance(v, list) else f"[{len(v)}개]") for k, v in D.items()}, ensure_ascii=False, indent=1)[:1800])
