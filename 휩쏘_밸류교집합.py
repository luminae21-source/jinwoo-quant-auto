# -*- coding: utf-8 -*-
r"""휩쏘_밸류교집합.py — 형의 명제 검정.

명제: "좋은 회사를 저렴하게 살 기회가 오면 사는 게 맞다."
      → 이 시스템에서 그 명제의 구현은 [밸류 태그] × [국면 게이트] × [휩쏘 자리] 의 교집합이다.

[검정] 7,071건(정식A 2,405 + S2 4,666) 전량에 KRX 재무 밸류 태그를 붙이고
       밸류 유무 × 국면 × 신호등급으로 쪼개 본다.
       재무검정(2,074건)에서 생존한 팩터만 쓴다: 저PBR(<0.8) · 저PER(<8, EPS>0) · 배당2%+
⚠️ KRX 재무는 월말 스냅숏 · 2002-01부터. 그 이전은 태그 부여 불가(무태그로 분류됨 — 편향 주의).
"""
import os, sys, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
HERE = "/home/claude/jq"; UP = "/mnt/user-data/uploads/진우퀀트"

S = pd.read_csv(f"{HERE}/S2_이벤트_통합.csv", dtype={"code": str})
S["code"] = S["code"].str.zfill(6); S["연"] = S["date"].str[:4].astype(int)

FIN = {}
for f in ("종목재무_KRX_KOSPI.csv", "종목재무_KRX_KOSDAQ.csv"):
    d = pd.read_csv(os.path.join(UP, f), dtype={"code": str})
    d.columns = [c.strip().lstrip("﻿") for c in d.columns]
    d["code"] = d["code"].str.zfill(6); d["date"] = d["date"].astype(str)
    for cc, gg in d.sort_values("date").groupby("code"):
        FIN[cc] = (gg["date"].values.astype(str),
                   gg[["PER", "PBR", "EPS", "DIV"]].apply(pd.to_numeric, errors="coerce").values)


def vtag(code, d0):
    a = FIN.get(code)
    if not a or d0 < "2002-02": return None          # 태그 부여 불가
    dd, vv = a
    k = int(np.searchsorted(dd, d0, side="right")) - 1
    if k < 0: return None
    per, pbr, eps, div = vv[k]
    tags = []
    if np.isfinite(pbr) and 0 < pbr < 0.8: tags.append("저PBR")
    if np.isfinite(per) and 0 < per < 8 and (not np.isfinite(eps) or eps > 0): tags.append("저PER")
    if np.isfinite(div) and div >= 2: tags.append("배당2%+")
    return "·".join(tags)


S["밸류"] = [vtag(c, d) for c, d in zip(S["code"], S["date"])]
S["태그가능"] = S["밸류"].notna()
S["밸류여부"] = S["밸류"].fillna("") != ""
S["등급"] = np.where(S["신호"] == "A", "정식A",
             np.where(S["미달"].fillna("").str.contains("2일누적"),
                      np.where(S["미달"].fillna("").str.count(",") == 0, "S2-β", "S2-γ"), "S2-α"))
C = S[S["fwd40"].notna() & S["태그가능"]].copy()      # 40봉 완결 + 재무 판정 가능분만
print(f"전체 {len(S)}건 · 40봉완결 {int(S['fwd40'].notna().sum())} · 재무판정가능 {len(C)} "
      f"· 밸류태그 보유 {int(C['밸류여부'].sum())}건 ({C['밸류여부'].mean()*100:.1f}%)")


def boot(a, y, n=6000, seed=71):
    rng = np.random.default_rng(seed); ys = np.array(sorted(set(y)))
    ix = {k: np.where(y == k)[0] for k in ys}; o = np.empty(n)
    for i in range(n):
        p = rng.choice(ys, size=len(ys), replace=True)
        s = np.concatenate([ix[k] for k in p]); o[i] = np.nanmean(a[s])
    return (*np.percentile(o, [2.5, 97.5]) * 100, float((o > 0).mean()))


def row(name, sub, ind=""):
    if len(sub) < 25:
        print(f"{ind}{name:<26}{len(sub):>6}   (표본 부족)"); return
    lo, hi, pg = boot(sub["카드"].values, sub["연"].values)
    mark = " ★" if lo > 0 else (" ✗" if hi < 0 else "")
    print(f"{ind}{name:<26}{len(sub):>6}{sub['카드'].mean()*100:>+9.2f}{sub['카드'].median()*100:>+9.2f}"
          f"{(sub['카드']>0).mean()*100:>7.1f}%{sub['이단'].mean()*100:>+9.2f}"
          f"   [{lo:+6.2f},{hi:+6.2f}]{mark}")


HDR = f"{'구분':<26}{'n':>6}{'카드평균':>9}{'중앙':>9}{'승률':>8}{'2단':>9}{'   부트95%CI':>20}"
print("\n" + "=" * 96)
print("[1] 형의 명제 — '좋은 회사를 저렴하게'  (🟢실행 국면 · 재무판정 가능분)")
print("=" * 96)
G = C[C["국면"] == "실행"]
print(HDR)
row("전체", G)
row("밸류 태그 있음", G[G["밸류여부"]])
row("밸류 태그 없음", G[~G["밸류여부"]])
print()
for t in ("저PBR", "저PER", "배당2%+"):
    row(f"  {t}", G[G["밸류"].fillna("").str.contains(t, regex=False)])
row("  태그 2개 이상", G[G["밸류"].fillna("").str.count("·") >= 1])

print("\n" + "=" * 96)
print("[2] 신호 등급 × 밸류 — 교집합이 진짜 최상급인가 (🟢실행)")
print("=" * 96)
print(HDR)
for gd in ("정식A", "S2-α", "S2-β", "S2-γ"):
    sub = G[G["등급"] == gd]
    if len(sub) < 25: continue
    print(f"── {gd}")
    row("밸류 O", sub[sub["밸류여부"]], "   ")
    row("밸류 X", sub[~sub["밸류여부"]], "   ")

print("\n" + "=" * 96)
print("[3] 국면 × 밸류 — 게이트와 밸류 중 무엇이 더 센가")
print("=" * 96)
print(HDR)
for rg in ("실행", "주의", "관찰만"):
    sub = C[C["국면"] == rg]
    print(f"── {rg}")
    row("밸류 O", sub[sub["밸류여부"]], "   ")
    row("밸류 X", sub[~sub["밸류여부"]], "   ")

print("\n" + "=" * 96)
print("[4] 최상급 셀 — 🟢실행 × 밸류 × (정식A 또는 S2-α)")
print("=" * 96)
print(HDR)
best = G[G["밸류여부"] & G["등급"].isin(["정식A", "S2-α"])]
worst = C[(C["국면"] != "실행") & (~C["밸류여부"])]
row("최상급 셀", best)
row("최하급 셀(비실행×무밸류)", worst)
if len(best) >= 25 and len(worst) >= 25:
    print(f"\n  격차 {(best['카드'].mean()-worst['카드'].mean())*100:+.2f}%p · "
          f"승률 격차 {((best['카드']>0).mean()-(worst['카드']>0).mean())*100:+.1f}%p")
    print(f"  최상급 셀 빈도: 재무판정가능 {len(C)}건 중 {len(best)}건 = {len(best)/len(C)*100:.1f}%")

print("\n" + "=" * 96)
print("[5] 2002년 이전 편향 점검 — 무태그가 '밸류 없음'으로 오분류되는 문제")
print("=" * 96)
pre = S[(S["fwd40"].notna()) & (~S["태그가능"])]
print(f"  재무 판정 불가(2002-02 이전 등) {len(pre)}건 · 카드 평균 {pre['카드'].mean()*100:+.2f}%")
print(f"  판정 가능분 {len(C)}건 · 카드 평균 {C['카드'].mean()*100:+.2f}%")
print("  → [1]~[4]는 판정 가능분만 쓴다. 무태그를 '밸류 없음'에 섞으면 결과가 오염된다.")
S.to_csv(f"{HERE}/휩쏘_밸류교집합_이벤트.csv", index=False, encoding="utf-8-sig")
print(f"\n저장: 휩쏘_밸류교집합_이벤트.csv")
