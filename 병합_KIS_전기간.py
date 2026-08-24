# -*- coding: utf-8 -*-
r"""병합_KIS_전기간.py — KIS 수정주가 v1(1996~2015) + v2016(2016~2026) 병합 (2026-07-28)

[핵심 검증 — 접합 연속성]
  두 패널은 시간이 겹치지 않는다(v1은 2015-12에 끝나고 v2016은 2016-01에 시작).
  겹침이 없으면 비율 대조를 할 수 없다 → **다른 방법으로 연속성을 증명해야 한다.**

  근거: 두 패널 모두 동일 KIS API·동일 플래그(FID_ORG_ADJ_PRC='0')·동일 조정기준(2026 현재)이다.
  검증: 2015-12 → 2016-01 월간수익률 분포가 **평시 월과 구별되지 않으면** 접합이 매끄럽다.
        스케일이 어긋났다면 그 달에만 체계적 점프(중앙값 이탈·이상치 급증)가 나타난다.

  판정 기준 (사전 선언):
    (A) 접합월 수익률 중앙값이 다른 달 중앙값 분포의 5~95% 안
    (B) 접합월 |수익률|>50% 비율이 평시 대비 3배 미만
    (C) 접합 코드 수 ≥ 1,500 (표본 충분)

[출력] _월봉_KIS_전기간.csv (code,ym,close,market,src) · 지문 json · 접합검증 리포트
사용: py 병합_KIS_전기간.py
"""
import os, sys, json, hashlib
import numpy as np, pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def _find(fn):
    for d in (BASE, os.path.join(BASE, "데이터수리"), os.path.dirname(BASE), os.getcwd(),
              os.path.join(os.getcwd(), "데이터수리")):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    raise FileNotFoundError(fn)

print("=" * 84)
print(" KIS 수정주가 전기간 병합 — 1996~2026")
print("=" * 84)

v1p = _find("월봉_KIS_adj_v1_2026-07-28.csv")
v2p = _find("_월봉_KIS_adj_2016.csv")
v1 = pd.read_csv(v1p, dtype={"code": str}); v1["code"] = v1["code"].str.zfill(6); v1["src"] = "v1"
v2 = pd.read_csv(v2p, dtype={"code": str}); v2["code"] = v2["code"].str.zfill(6); v2["src"] = "v2016"
print(f"  v1    : {len(v1):,}행 · {v1['code'].nunique():,}코드 · {v1['ym'].min()}~{v1['ym'].max()}")
print(f"  v2016 : {len(v2):,}행 · {v2['code'].nunique():,}코드 · {v2['ym'].min()}~{v2['ym'].max()}")

ov = set(v1["ym"]) & set(v2["ym"])
print(f"  기간 겹침: {len(ov)}개월 {'(없음 — 접합 연속성 검증 필요)' if not ov else sorted(ov)}")

# 마스크 적용(v1 구간) — 동결6·저가100·INT32포화
try:
    mk = pd.read_csv(_find("_패널마스크_v1.csv"), dtype={"code": str})
    ms = set(zip(mk["code"].str.zfill(6), mk["ym"]))
    n0 = len(v1)
    v1 = v1[[(c, y) not in ms for c, y in zip(v1["code"], v1["ym"])]]
    print(f"  마스크 v1 적용: {n0-len(v1):,}셀 제거")
except Exception as e:
    print(f"  ⚠️ 마스크 미적용: {e}")

M = pd.concat([v1, v2], ignore_index=True).sort_values(["code", "ym"])
M = M.drop_duplicates(["code", "ym"], keep="last")

# ── 접합 연속성 검증
print("\n[접합 연속성 검증] 2015-12 → 2016-01")
P = M.pivot_table(index="ym", columns="code", values="close", aggfunc="last").sort_index()
_i = pd.to_datetime(P.index + "-01"); MI = (_i.year * 12 + _i.month).values
R = P.pct_change(); R[np.r_[True, np.diff(MI) != 1]] = np.nan

splice = R.loc["2016-01"].dropna()
others = R.loc[[y for y in R.index if "2010-01" <= y <= "2021-12" and y != "2016-01"]]
med_o = others.median(axis=1).dropna()
ext_o = (others.abs() > 0.5).mean(axis=1).dropna()

med_s = splice.median()
ext_s = (splice.abs() > 0.5).mean()
lo, hi = med_o.quantile(0.05), med_o.quantile(0.95)
A = lo <= med_s <= hi
B = ext_s < ext_o.mean() * 3
C = len(splice) >= 1500
print(f"  (A) 접합월 중앙값 {med_s*100:+.2f}% · 평시 5~95% 대역 [{lo*100:+.2f}%, {hi*100:+.2f}%]  → {'✅ 통과' if A else '❌ 실패'}")
print(f"  (B) |수익|>50% 비율 {ext_s*100:.2f}% · 평시 평균 {ext_o.mean()*100:.2f}% (3배 한계 {ext_o.mean()*3*100:.2f}%)  → {'✅ 통과' if B else '❌ 실패'}")
print(f"  (C) 접합 코드 수 {len(splice):,} (≥1,500)  → {'✅ 통과' if C else '❌ 실패'}")
verdict = A and B and C
print(f"  판정: {'★ 접합 연속 — 병합 유효' if verdict else '🔴 접합 의심 — 병합본 사용 금지'}")

# 코드별 극단 접합 (개별 이상치 목록)
odd = splice[splice.abs() > 1.0]
if len(odd):
    print(f"  참고: 접합월 |수익|>100% 코드 {len(odd)}건 (개별 CA 또는 실제 급등락) — "
          f"상위 5: {', '.join(f'{c}({v*100:+.0f}%)' for c, v in odd.abs().nlargest(5).items())}")

if not verdict:
    sys.exit("\n❌ 접합 검증 실패 — 병합본을 저장하지 않는다.")

outp = os.path.join(BASE, "_월봉_KIS_전기간.csv")
M[["code", "ym", "close", "market", "src"]].to_csv(outp, index=False, encoding="utf-8-sig")
md5 = hashlib.md5(open(outp, "rb").read()).hexdigest()
json.dump({"파일": "_월봉_KIS_전기간.csv", "md5": md5, "행": len(M),
           "코드": int(M["code"].nunique()), "기간": f"{M['ym'].min()}~{M['ym'].max()}",
           "구성": {"v1(1996~2015)": int((M['src']=='v1').sum()),
                    "v2016(2016~2026)": int((M['src']=='v2016').sum())},
           "원본md5": {"v1": hashlib.md5(open(v1p,'rb').read()).hexdigest(),
                       "v2016": hashlib.md5(open(v2p,'rb').read()).hexdigest()},
           "마스크": "_패널마스크_v1 적용(v1 구간)",
           "접합검증": {"중앙값": float(med_s), "평시대역": [float(lo), float(hi)],
                        "극단비율": float(ext_s), "판정": "통과"},
           "동결일": "2026-07-28"},
          open(os.path.join(BASE, "_월봉_KIS_전기간_지문.json"), "w", encoding="utf-8"),
          ensure_ascii=False, indent=2)

print(f"\n  병합 완료: {len(M):,}행 · {M['code'].nunique():,}코드 · {M['ym'].min()}~{M['ym'].max()}")
print(f"  md5 {md5}")
print(f"  저장: _월봉_KIS_전기간.csv · _월봉_KIS_전기간_지문.json")
print("=" * 84)
