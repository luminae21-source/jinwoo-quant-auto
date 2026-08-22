# -*- coding: utf-8 -*-
"""휩쏘 관찰 원장 점검 + 과제1 채택안(2단 청산) 실전 전환표 — 2026-08-02 기준(마지막 거래일 07-31)."""
import os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

HERE = "/home/claude/jq"; UP = "/mnt/user-data/uploads/진우퀀트"
RTRAIL = 0.12   # 과제1 채택: 잔여 트레일 −12%
SPLIT = 0.50

L = pd.read_csv(f"{UP}/휩쏘_관찰.csv", dtype={"code": str})
L.columns = [c.strip().lstrip("﻿") for c in L.columns]
L["code"] = L["code"].str.zfill(6)
codes = set(L["code"])

px = []
for mk in ("KOSPI", "KOSDAQ"):
    D = pd.read_csv(f"{HERE}/종목일봉_30년_{mk}.csv",
                    dtype={"code": str, "open": "float64", "high": "float64",
                           "low": "float64", "close": "float64", "volume": "float64"})
    D.columns = [x.strip().lstrip("﻿") for x in D.columns]
    D["code"] = D["code"].str.zfill(6)
    D = D[D["code"].isin(codes) & (D["date"] >= "2026-07-01")]
    D["시장"] = mk
    px.append(D)
P = pd.concat(px, ignore_index=True).sort_values(["code", "date"])
last = P["date"].max()

rows = []
for _, r in L.iterrows():
    g = P[(P["code"] == r["code"]) & (P["date"] >= r["출발일"])]
    if g.empty: continue
    entry = float(r["출발가"]); tgt = float(r["목표가"]); stop0 = float(r["손절가"])
    after = g[g["date"] > r["출발일"]]
    cur = g.iloc[-1]
    d = dict(code=r["code"], name=r["name"], 유형=r["유형"], 등급=r["등급"],
             시장=cur["시장"], 상태=r["상태"], 진입가=entry, 목표가=tgt, 손절가=stop0,
             현재가=float(cur["close"]), 경과=len(after))
    d["현재수익"] = d["현재가"] / entry - 1
    if len(after):
        pk = float(after["high"].max()); d["최고가"] = pk; d["최고수익"] = pk / entry - 1
        hit = after[after["high"] >= tgt]
        d["목표도달일"] = hit["date"].iloc[0] if len(hit) else ""
    else:
        d["최고가"] = np.nan; d["최고수익"] = np.nan; d["목표도달일"] = ""
    if d["목표도달일"]:
        # 2단 전환: 절반은 목표가에 실현, 잔여는 트레일(본전 하한)
        d["실현_50%"] = tgt / entry - 1
        pk_after = after[after["date"] >= d["목표도달일"]]["high"].max()
        rstop = max(float(pk_after) * (1 - RTRAIL), entry)
        d["잔여_트레일선"] = rstop
        d["잔여_평가"] = d["현재가"] / entry - 1
        d["카드_구(전량)"] = tgt / entry - 1
        d["카드_신(2단·현재평가)"] = SPLIT * d["실현_50%"] + (1 - SPLIT) * d["잔여_평가"]
        # 트레일 스톱 판정은 '목표도달일 다음 거래일'부터 (30년 검정과 동일 규약).
        # 같은 날 고가/저가의 선후는 일봉으로 알 수 없으므로 당일 이탈로 보지 않는다.
        nxt = after[after["date"] > d["목표도달일"]]
        d["잔여상태"] = ("청산(트레일 이탈)" if len(nxt) and float(nxt["low"].min()) <= rstop
                      else ("보유중" if len(nxt) else "보유중(익일 트레일 개시)"))
    else:
        d["실현_50%"] = np.nan; d["잔여_트레일선"] = np.nan; d["잔여_평가"] = np.nan
        d["카드_구(전량)"] = np.nan; d["카드_신(2단·현재평가)"] = np.nan
        d["잔여상태"] = ""
        d["손절까지"] = d["현재가"] / stop0 - 1
        d["목표까지"] = tgt / d["현재가"] - 1
    rows.append(d)

R = pd.DataFrame(rows)
R.to_csv(f"{HERE}/휩쏘_원장_2단전환_20260802.csv", index=False, encoding="utf-8-sig")

print("=" * 96)
print(f"휩쏘 관찰 원장 점검 · 기준일 {last} (마지막 거래일) · 총 {len(R)}종")
print("=" * 96)
done = R[R["목표도달일"] != ""]
open_ = R[R["목표도달일"] == ""]
print(f"\n■ 목표 도달 {len(done)}종 — 신규 채택 2단 규칙 적용 시 '잔여 50%'가 살아있다")
print(f"{'종목':<14}{'유형':<4}{'진입가':>10}{'목표가':>10}{'현재가':>10}{'실현50%':>9}{'잔여평가':>9}"
      f"{'잔여 트레일선':>13}{'상태':>10}")
for _, x in done.sort_values("최고수익", ascending=False).iterrows():
    print(f"{x['name'][:13]:<14}{x['유형']:<4}{x['진입가']:>10,.0f}{x['목표가']:>10,.0f}{x['현재가']:>10,.0f}"
          f"{x['실현_50%']*100:>+8.1f}%{x['잔여_평가']*100:>+8.1f}%{x['잔여_트레일선']:>13,.0f}{x['잔여상태']:>12}")
print(f"\n  구 카드(전량청산) 평균 실현  {done['카드_구(전량)'].mean()*100:+.2f}%")
print(f"  신 카드(2단·현재평가) 평균   {done['카드_신(2단·현재평가)'].mean()*100:+.2f}%"
      f"   → 현시점 차이 {(done['카드_신(2단·현재평가)'].mean()-done['카드_구(전량)'].mean())*100:+.2f}%p")
print(f"  ※ 잔여 평가익은 미실현. 트레일선 이탈 시 확정된다.")

print(f"\n■ 관찰중(목표 미도달) {len(open_)}종")
print(f"{'종목':<14}{'유형':<4}{'진입가':>10}{'현재가':>10}{'현재수익':>9}{'최고수익':>9}{'손절가':>10}{'손절까지':>9}{'목표까지':>9}")
for _, x in open_.iterrows():
    print(f"{x['name'][:13]:<14}{x['유형']:<4}{x['진입가']:>10,.0f}{x['현재가']:>10,.0f}"
          f"{x['현재수익']*100:>+8.1f}%{x['최고수익']*100:>+8.1f}%{x['손절가']:>10,.0f}"
          f"{x['손절까지']*100:>+8.1f}%{x['목표까지']*100:>+8.1f}%")
