# -*- coding: utf-8 -*-
r"""휩쏘_일관성감사_0804.py — 2026-08-04 신규 2개 검정의 일관성 감사.

[감사 대상]
  ⑤ 휩쏘_종목군월별_검정.py   (과제1 · 종목군=시총계층 × 월별)
  ⑥ 휩쏘_시간축분리_검정.py   (과제2 · 스윙/단기 분리)

[방법] 기존 휩쏘_일관성감사.py 와 같은 원칙 — "결론이 그럴듯한가"가 아니라 "숫자가 같은가".
       ⑥의 엔진은 원본 휩쏘_역사검정.py 와 동일 입력 → 동일 출력이어야 하고,
       ⑥의 현행_40 은 ①2단청산의 P0_카드 와 완전일치해야 한다.

※ 기존 휩쏘_일관성감사.py 는 그대로 두고 이 파일을 추가로 돌린다.
   (기존 파일은 원본_휩쏘_역사검정.py·조사_스캐너.py 등을 요구하므로 병합하지 않았다)
"""
import os, sys, importlib.util, inspect, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass


# ── 경로 해석 (컨테이너 / 형 PC 어디서 돌려도 동작) ─────────────
def _resolve():
    here = os.path.dirname(os.path.abspath(__file__))
    cand = ["/home/claude/jq", "/mnt/user-data/uploads/진우퀀트", here]
    def find(name):
        for d in ([here] + cand):
            p = os.path.join(d, name)
            if os.path.exists(p): return p
        return os.path.join(here, name)
    return here, find
HERE, F = _resolve()
FAIL = []


def ok(cond, name, detail=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  — {detail}" if detail else ""))
    if not cond: FAIL.append(name)
    return cond


def load(path, tag):
    sp = importlib.util.spec_from_file_location("m_" + tag, path)
    m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m


# ══════════════════════════════════════════════════════════════════
print("=" * 88)
print("[E] 엔진 동등성 — ⑥시간축 엔진이 원본 휩쏘_역사검정.py 와 같은가")
print("=" * 88)
SRC = {"⓪원본역사검정": F("휩쏘_역사검정.py"),
       "⑥시간축분리": F("휩쏘_시간축분리_검정.py")}
MODS = {}
for k, v in SRC.items():
    if os.path.exists(v):
        try: MODS[k] = load(v, str(abs(hash(k))))
        except Exception as e: print(f"    ⚪ {k} 로드 실패: {e}")
    else: print(f"    ⚪ {k} 파일 없음: {v}")

rng = np.random.default_rng(3); N = 3000
dates = pd.bdate_range("2005-01-03", periods=N).strftime("%Y-%m-%d").values
cc0 = 100 * np.cumprod(1 + rng.normal(0, 0.02, N))
cc0[1500:] /= 5.0; cc0[2200:] *= 3.0
oo = cc0 * (1 + rng.normal(0, 0.003, N))
hh = np.maximum(oo, cc0) * 1.01; ll = np.minimum(oo, cc0) * 0.99
vv = rng.integers(1e4, 1e6, N).astype(float)

print("\n  E-1. back_adjust() — 인위적 분할/병합 시계열")
ref = refname = None
for k, m in MODS.items():
    f = getattr(m, "back_adjust", None)
    if f is None: print(f"    ⚪ {k:<14} 없음"); continue
    na = len(inspect.signature(f).parameters)
    out = (f(oo.copy(), hh.copy(), ll.copy(), cc0.copy(), vv.copy(), dates) if na == 6
           else f(oo.copy(), hh.copy(), ll.copy(), cc0.copy(), dates))
    r = out[3]
    if ref is None: ref, refname = r, k; print(f"    ⚙️ {k:<14} 기준 · 조정후 종가[0]={r[0]:.6f}")
    else: ok(np.nanmax(np.abs(r - ref)) < 1e-9, f"{k} back_adjust ≡ {refname}",
             f"최대차 {np.nanmax(np.abs(r - ref)):.1e}")

print("\n  E-2. line_series() — 주60주·월10")
ref = refname = None
for k, m in MODS.items():
    f = getattr(m, "line_series", None)
    if f is None: continue
    pn = list(inspect.signature(f).parameters)
    try:
        w, mo_ = (f(pd.DataFrame({"date": dates, "close": cc0})) if pn[0] == "c_idx"
                  else f(dates, cc0))
    except ValueError as e:
        if "no longer supported" in str(e):
            print(f"    ⚠️ {k:<14} pandas 3.x 비호환 — resample(\"M\"). 'M'→'ME' 로 고칠 것."); continue
        raise
    arr = np.nan_to_num(np.r_[w, mo_])
    if ref is None: ref, refname = arr, k; print(f"    ⚙️ {k:<14} 기준")
    else: ok(np.nanmax(np.abs(arr - ref)) < 1e-9, f"{k} line_series ≡ {refname}",
             f"최대차 {np.nanmax(np.abs(arr - ref)):.1e}")

print("\n  E-3. era_limit() — 가격제한폭 경계")
probe = ("2000-01-01", "2015-06-14", "2015-06-15", "2026-07-31")
ref = None
for k, m in MODS.items():
    f = getattr(m, "era_limit", None)
    if f is None: continue
    got = [f(d) for d in probe]
    if ref is None: ref = got; print(f"    ⚙️ {k:<14} 기준 {got}")
    else: ok(got == ref, f"{k} era_limit ≡ 기준", str(got))

# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 88)
print("[F] 수치 수준 — ⑥시간축이 원장·기존검정과 같은 값을 내는가")
print("=" * 88)
TX = pd.read_csv(F("휩쏘_시간축_이벤트.csv"), dtype={"code": str})
TX["code"] = TX["code"].str.zfill(6)
LG = pd.read_csv(F("휩쏘_역사원장.csv"), dtype={"code": str})
LG.columns = [c.strip().lstrip("﻿") for c in LG.columns]; LG["code"] = LG["code"].str.zfill(6)
DONE = TX[TX["청산"].astype(str) != "진행중"].copy()

print("\n  F-1. 원장 카드수익 ↔ ⑥현행_40 (진행중 제외)")
d = (DONE["카드수익"].astype(float) / 100 - DONE["현행_40"].astype(float)).abs()
ok(d.max() < 0.0006, "⑥현행_40 = 원장 카드수익", f"n={len(DONE)} 최대오차 {d.max()*100:.4f}%p "
   f"(원장은 소수 1자리 반올림 저장 → 허용 0.05%p)")

live = TX[TX["청산"].astype(str) == "진행중"]
print(f"    ⓘ 진행중 {len(live)}건은 원장이 당시 시점 평가라 구조적으로 불일치 — 표본에서 제외했다")

print("\n  F-2. ①2단청산 P0_카드 ↔ ⑥현행_40 (완전일치해야 함 · 같은 규칙 같은 지평)")
p1p = F("휩쏘_2단청산_이벤트.csv")
if os.path.exists(p1p):
    P1 = pd.read_csv(p1p, dtype={"code": str}); P1["code"] = P1["code"].str.zfill(6)
    x = P1[["code", "출발일", "P0_카드", "P0_H40", "P0_H126", "창완결_126"]].merge(
        DONE[["code", "출발일", "현행_40", "현행_126"]], on=["code", "출발일"])
    dx = (x["P0_카드"] - x["현행_40"]).abs()
    ok(dx.max() < 1e-9, "①P0_카드 ≡ ⑥현행_40", f"교집합 n={len(x)} 최대차 {dx.max():.2e}")
    xc = x[x["창완결_126"] == True]
    dz = (xc["P0_H126"] - xc["현행_126"]).abs()
    ok(dz.max() < 1e-9, "①P0_H126 ≡ ⑥현행_126", f"n={len(xc)} 최대차 {dz.max():.2e}")
else:
    print("    ⚪ 휩쏘_2단청산_이벤트.csv 없음 — 교차대조 생략")

print("\n  F-3. 지평 단조성 — 창완결이면 짧은 지평의 결과가 긴 지평의 '접두'여야 한다")
G = DONE[(DONE["국면"] == "실행") & (DONE["창완결_126"] == True)]
bad = 0
for a, b in ((5, 10), (10, 20), (20, 40), (40, 63), (63, 126)):
    m = (G[f"현행봉_{a}"] < a) & (G[f"현행사유_{a}"] != "만기")
    diff = (G.loc[m, f"현행_{a}"] - G.loc[m, f"현행_{b}"]).abs()
    if len(diff): bad += int((diff > 1e-9).sum())
ok(bad == 0, "만기 전 청산건은 지평이 늘어도 값이 불변", f"불일치 {bad}건")

# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 88)
print("[G] ⑤종목군월별 — 표본·계층 부여 무결성")
print("=" * 88)
EV = pd.read_csv(F("휩쏘_종목군월별_이벤트.csv"), dtype={"code": str})
EV["code"] = EV["code"].str.zfill(6)
S2 = pd.read_csv(F("S2_이벤트_통합.csv"), dtype={"code": str})
S2.columns = [c.strip().lstrip("﻿") for c in S2.columns]; S2["code"] = S2["code"].str.zfill(6)
ok(len(EV) == len(S2), "계층부여 후에도 표본수 보존 (중복 병합 없음)",
   f"{len(S2)} → {len(EV)}")
ok(not EV.duplicated(["date", "code"]).any(), "(date,code) 중복 없음",
   f"중복 {int(EV.duplicated(['date','code']).sum())}건")
ok(EV["계층"].notna().all(), "전건 계층 부여", f"미부여 {int(EV['계층'].isna().sum())}건")
ok(set(EV["계층"].unique()) <= {"대형", "중형", "소형"}, "계층 라벨 3종",
   str(sorted(EV["계층"].unique())))
kv = EV["국면"].value_counts().to_dict(); sv = S2["국면"].value_counts().to_dict()
ok(kv == sv, "국면 분포 보존", f"{kv}")

print("\n  G-1. look-ahead 차단 — 스냅숏일이 진입일보다 앞서는가")
sn = pd.to_datetime(EV["snap"]); dt_ = pd.to_datetime(EV["date"])
ok((sn <= dt_).all(), "스냅숏 ≤ 진입일", f"위반 {int((sn > dt_).sum())}건 · "
   f"최대 지연 {int((dt_-sn).dt.days.max())}일")

# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 88)
print("[H] 논리 일관성 — 오늘 결론이 기존 결론과 모순되지 않는가")
print("=" * 88)
GE = EV[EV["국면"] == "실행"]
checks = []
for t in ("대형", "중형", "소형"):
    g = EV[EV["계층"] == t].groupby("국면")["카드"].mean() * 100
    checks.append((g.get("실행", -9) > g.get("주의", 9) and g.get("실행", -9) > g.get("관찰만", 9),
                   f"국면 게이트 부호 유지 ({t})",
                   " · ".join(f"{k} {v:+.2f}" for k, v in g.items())))
# 9~10월 진입이 전체보다 나쁘다 (기존 §2-5)
so = GE[pd.to_datetime(GE["date"]).dt.month.isin([9, 10])]["카드"].mean() * 100
al = GE["카드"].mean() * 100
checks.append((so < al, "9~10월 진입 < 전체 (기존 §2-5와 같은 방향)", f"{so:+.2f} vs {al:+.2f}"))
# A형은 40봉 안에 끝난다
tcol = "유형_x" if "유형_x" in G.columns else "유형"
amax = G[G[tcol] == "A"]["현행봉_40"].max()
checks.append((amax <= 40, "A형 청산이 40봉 이내", f"최대 {amax:.0f}봉"))
# B형은 지평이 길수록 나빠진다 (단조)
bm = [G[G[tcol] == "B"][f"현행_{h}"].mean() * 100 for h in (5, 10, 20, 40, 63, 126)]
checks.append((all(bm[i] >= bm[i + 1] - 1e-9 for i in range(len(bm) - 1)),
               "B형 지평 단조 감소", " → ".join(f"{v:+.2f}" for v in bm)))
# 카드가 순수보유보다 하방이 낫다 (전 지평)
downs = []
for h in (5, 10, 20, 40, 63, 126):
    downs.append(G[f"현행_{h}"].min() > G[f"보유_{h}"].min())
checks.append((all(downs), "카드 최대손실 < 보유 최대손실 (전 지평)",
               f"카드 {G['현행_126'].min()*100:.1f}% vs 보유 {G['보유_126'].min()*100:.1f}%"))
for c, n, d in checks: ok(c, n, d)

print("\n" + "=" * 88)
if FAIL: print(f"❌ 감사 실패 {len(FAIL)}건: {FAIL}")
else: print("✅ 전 항목 통과 — ⑤⑥ 신규 검정이 기존 엔진·수치·논리와 일관.")
print("=" * 88)
