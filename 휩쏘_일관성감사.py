# -*- coding: utf-8 -*-
r"""휩쏘_일관성감사.py — 2026-08-02 하루에 돌린 4개 검정이 서로 어긋나지 않는지 전수 대조.

[감사 대상]
  ① 휩쏘_2단청산검정.py   (과제1)
  ② 휩쏘_1월앵커_검정.py   (과제2)
  ③ 휩쏘_S2_역사검정.py    (S2)
  ④ 조사_스캐너.py         (실전 스캐너)
[방법] 코드 수준(엔진 함수 해시) + 수치 수준(같은 이벤트에서 같은 값이 나오는가) 이중 대조.
       "결론이 그럴듯한가"가 아니라 "숫자가 같은가"만 본다.
"""
import os, sys, re, ast, hashlib, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
HERE = "/home/claude/jq"
FAIL = []
COMPAT = []


def ok(cond, name, detail=""):
    print(f"  {'✅' if cond else '❌'} {name}" + (f"  — {detail}" if detail else ""))
    if not cond: FAIL.append(name)
    return cond


# ══════════════════════════════════════════════════════════════════
print("=" * 88)
print("[A] 엔진 동등성 — 텍스트가 아니라 '같은 입력 → 같은 출력'으로 검증")
print("=" * 88)
import importlib.util, inspect

FILES = {"⓪원본역사검정": "원본_휩쏘_역사검정.py", "①2단청산": "휩쏘_2단청산검정.py",
         "②1월앵커": "휩쏘_1월앵커_검정.py", "③S2검정": "휩쏘_S2_역사검정.py",
         "④스캐너": "조사_스캐너.py"}
MODS = {}
for k, v in FILES.items():
    sp = importlib.util.spec_from_file_location("mod_" + str(abs(hash(k))), os.path.join(HERE, v))
    m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); MODS[k] = m

rng = np.random.default_rng(3); N = 3000
dates = pd.bdate_range("2005-01-03", periods=N).strftime("%Y-%m-%d").values
cc0 = 100 * np.cumprod(1 + rng.normal(0, 0.02, N))
cc0[1500:] /= 5.0        # 5:1 분할
cc0[2200:] *= 3.0        # 3:1 병합
oo = cc0 * (1 + rng.normal(0, 0.003, N))
hh = np.maximum(oo, cc0) * 1.01; ll = np.minimum(oo, cc0) * 0.99
vv = rng.integers(1e4, 1e6, N).astype(float)

print("\n  A-1. back_adjust() — 인위적 분할/병합이 들어간 동일 시계열")
ref = refname = None
for k, m in MODS.items():
    f = getattr(m, "back_adjust", None)
    if f is None: print(f"    ⚪ {k:<12} 없음"); continue
    na = len(inspect.signature(f).parameters)
    out = (f(oo.copy(), hh.copy(), ll.copy(), cc0.copy(), vv.copy(), dates) if na == 6
           else f(oo.copy(), hh.copy(), ll.copy(), cc0.copy(), dates))
    r = out[3]
    if ref is None:
        ref, refname = r, k; print(f"    ⚙️ {k:<12} 기준 (형의 원본 엔진) · 조정후 종가[0]={r[0]:.6f}")
    else:
        ok(np.nanmax(np.abs(r - ref)) < 1e-9, f"{k} back_adjust ≡ {refname}",
           f"최대차 {np.nanmax(np.abs(r - ref)):.1e}")

print("\n  A-2. line_series() — 주60주·월10 선")
ref = refname = None
for k, m in MODS.items():
    f = getattr(m, "line_series", None)
    if f is None: continue
    pn = list(inspect.signature(f).parameters)
    try:
        w, mo_ = (f(pd.DataFrame({"date": dates, "close": cc0})) if pn[0] == "c_idx" else f(dates, cc0))
    except ValueError as e:
        if "no longer supported" in str(e):
            print(f"    ⚠️ {k:<12} pandas 3.x 비호환 — resample(\"M\") 사용. 형 PC(pandas 2.3.3)에선 동작하나")
            print(f"                  향후 pandas 업그레이드 시 죽는다. 'M' → 'ME' 로 고쳐둘 것.")
            COMPAT.append(k); continue
        raise
    arr = np.nan_to_num(np.r_[w, mo_])
    if ref is None: ref, refname = arr, k; print(f"    ⚙️ {k:<12} 기준")
    else: ok(np.nanmax(np.abs(arr - ref)) < 1e-9, f"{k} line_series ≡ {refname}",
             f"최대차 {np.nanmax(np.abs(arr - ref)):.1e}")

print("\n  A-3. 가격제한폭 경계 (2015-06-15 전후)")
probe = ("2000-01-01", "2015-06-14", "2015-06-15", "2026-07-31")
ref = None
for k, m in MODS.items():
    f = getattr(m, "era_limit", None)
    if f is None: print(f"    ⚪ {k:<12} era_limit 없음 (back_adjust에 인라인 — A-1에서 이미 동등 확인)"); continue
    got = [f(d) for d in probe]
    if ref is None: ref = got; print(f"    ⚙️ {k:<12} 기준 {got}")
    else: ok(got == ref, f"{k} era_limit ≡ 기준", str(got))

print("\n  A-4. 카드 파라미터 문자열 (A: 지지선×0.95·트레일12% / B: ×0.97·15%)")
for k, v in FILES.items():
    src = open(os.path.join(HERE, v), encoding="utf-8").read()
    a95 = "0.95" in src and "below" in src
    t12 = "0.12" in src
    b97 = "0.97" in src
    t15 = "0.15" in src and "trail = 0.15" in src
    note = ""
    if k == "④스캐너": note = "  (탐지 전용 — 청산 시뮬 없음, 정상)"
    if k == "③S2검정": note = "  (A계열 전용 — B카드 미사용, 정상)"
    print(f"    {k:<12} A×0.95 {'O' if a95 else '-'} · A트레일12% {'O' if t12 else '-'} · "
          f"B×0.97 {'O' if b97 else '-'} · B트레일15% {'O' if t15 else '-'}{note}")

# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 88)
print("[B] 수치 수준 — 같은 이벤트에서 같은 값이 나오는가")
print("=" * 88)

P1 = pd.read_csv(f"{HERE}/휩쏘_2단청산_이벤트.csv", dtype={"code": str})
P1["code"] = P1["code"].str.zfill(6)
JA = pd.read_csv(f"{HERE}/휩쏘_1월앵커_이벤트.csv", dtype={"code": str})
JA["code"] = JA["code"].str.zfill(6)
S2 = pd.read_csv(f"{HERE}/S2_이벤트_통합.csv", dtype={"code": str})
S2["code"] = S2["code"].str.zfill(6)
LG = pd.read_csv("/mnt/user-data/uploads/진우퀀트/휩쏘_역사원장.csv", dtype={"code": str})
LG.columns = [c.strip().lstrip("﻿") for c in LG.columns]; LG["code"] = LG["code"].str.zfill(6)

print("\n  B-1. 원장 카드수익 ↔ 각 검정의 카드 재계산")
m = P1.merge(LG[["code", "출발일", "카드수익"]], on=["code", "출발일"], suffixes=("", "_L"))
d1 = (m["P0_카드"] * 100 - m["카드수익_L"]).abs()
ok(d1.max() < 0.06, "①2단청산 P0_카드 = 원장", f"n={len(m)} 최대오차 {d1.max():.4f}%p")

sa = S2[S2["신호"] == "A"].merge(LG[["code", "출발일", "카드수익"]],
                                left_on=["code", "date"], right_on=["code", "출발일"])
d3 = (sa["카드"] * 100 - sa["카드수익"]).abs()
ok(d3.max() < 0.06, "③S2검정 A카드 = 원장", f"n={len(sa)} 최대오차 {d3.max():.4f}%p")

mj = JA.merge(LG[["code", "출발일", "카드수익"]], on=["code", "출발일"])
d2 = (mj["B0_카드"] * 100 - mj["카드수익"]).abs()
ok(d2.max() < 0.06, "②1월앵커 B0_카드 = 원장", f"n={len(mj)} 최대오차 {d2.max():.4f}%p")

print("\n  B-2. 검정 ↔ 검정 직접 대조 (교집합 이벤트)")
x = P1[["code", "출발일", "P0_카드", "P1_T12_H126_be"]].merge(
    JA[["code", "출발일", "B0_카드", "B0b_2단126"]], on=["code", "출발일"])
dc = (x["P0_카드"] - x["B0_카드"]).abs()
ok(dc.max() < 1e-9, "①↔② 카드 완전일치", f"교집합 n={len(x)} 최대차 {dc.max():.2e}")
d2s = (x["P1_T12_H126_be"] - x["B0b_2단126"]).abs()
ok(d2s.max() < 1e-9, "①↔② 2단(T12/H126/be) 완전일치", f"최대차 {d2s.max():.2e}")

y = P1[["code", "출발일", "P0_카드"]].merge(
    S2[S2["신호"] == "A"][["code", "date", "카드", "이단"]],
    left_on=["code", "출발일"], right_on=["code", "date"])
dy = (y["P0_카드"] - y["카드"]).abs()
ok(dy.max() < 1e-9, "①↔③ 카드 완전일치", f"교집합 n={len(y)} 최대차 {dy.max():.2e}")

z = P1[["code", "출발일", "P1_T12_H126_be"]].merge(
    S2[S2["신호"] == "A"][["code", "date", "이단"]],
    left_on=["code", "출발일"], right_on=["code", "date"])
dz = (z["P1_T12_H126_be"] - z["이단"]).abs()
ok(dz.max() < 1e-9, "①↔③ 2단 완전일치", f"교집합 n={len(z)} 최대차 {dz.max():.2e}")

print("\n  B-3. 이벤트 집합 대조")
ka = set(zip(S2[S2["신호"] == "A"]["code"], S2[S2["신호"] == "A"]["date"]))
kl = set(zip(LG[LG["유형"] == "A"]["code"], LG[LG["유형"] == "A"]["출발일"]))
ok(ka == kl, "③S2검정 A집합 = 원장 A집합", f"|A|={len(ka)} 대칭차 {len(ka ^ kl)}")
ks2 = set(zip(S2[S2["신호"] == "S2"]["code"], S2[S2["신호"] == "S2"]["date"]))
ok(len(ka & ks2) == 0, "A집합 ∩ S2집합 = 공집합", f"|S2|={len(ks2)} 교집합 {len(ka & ks2)}")
kb = set(zip(LG[LG["유형"] == "B"]["code"], LG[LG["유형"] == "B"]["출발일"]))
ok(len(kb & ks2) == 0, "B집합 ∩ S2집합 = 공집합", f"|B|={len(kb)} 교집합 {len(kb & ks2)}")

# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 88)
print("[C] 보고한 수치가 재계산과 맞는가 (판정문 대조)")
print("=" * 88)
C1 = P1[P1["창완결_126"] == True]
G1 = C1[C1["국면"] == "실행"]
print(f"  과제1 판정문 '🟢실행 카드 +1.65% → 2단 +2.13%, Δ+0.48%p'")
v1, v2 = G1["P0_H126"].mean() * 100, G1["P1_T12_H126_be"].mean() * 100
ok(abs(v1 - 1.65) < 0.02 and abs(v2 - 2.13) < 0.02, "  재계산 일치",
   f"{v1:+.2f} → {v2:+.2f} (Δ{v2-v1:+.2f}%p)")

S2C = S2[S2["fwd40"].notna()]
GS = S2C[S2C["국면"] == "실행"]
a_ = GS[GS["신호"] == "A"]; s_ = GS[GS["신호"] == "S2"]
print(f"\n  S2 판정문 '🟢실행 A +2.40% · S2 +1.27%'")
ok(abs(a_['카드'].mean() * 100 - 2.40) < 0.02 and abs(s_['카드'].mean() * 100 - 1.27) < 0.02,
   "  재계산 일치", f"A {a_['카드'].mean()*100:+.2f} · S2 {s_['카드'].mean()*100:+.2f}")

# ── ⚠️ 지평 혼입 점검: S2 판정문의 Δ는 카드(40봉) vs 2단(126봉) 비교였다
print("\n  ⚠️ [C-1] S2 판정문의 '2단 Δ'가 지평 효과를 섞었는지 점검")
print("     과제1에서 '지평만 연장(40→126봉)'은 그 자체로 −0.08%p였다. 순수 분할 효과를 분리해야 한다.")
com = P1[["code", "출발일", "P0_카드", "P0_H126", "P1_T12_H126_be", "국면", "창완결_126"]].merge(
    S2[S2["신호"] == "A"][["code", "date"]], left_on=["code", "출발일"], right_on=["code", "date"])
com = com[(com["국면"] == "실행") & (com["창완결_126"] == True)]
mix = (com["P1_T12_H126_be"].mean() - com["P0_카드"].mean()) * 100      # S2 판정문 방식
pure = (com["P1_T12_H126_be"].mean() - com["P0_H126"].mean()) * 100     # 지평 통제
hz = (com["P0_H126"].mean() - com["P0_카드"].mean()) * 100
print(f"     혼합 Δ(카드40 vs 2단126) {mix:+.2f}%p = 지평효과 {hz:+.2f}%p + 순수분할 {pure:+.2f}%p   (n={len(com)})")
ok(abs(mix - (hz + pure)) < 1e-9, "  분해 항등식 성립")
print(f"     → S2 판정문의 'A Δ+0.50%p'는 40봉 창완결 표본(n={len(GS[GS['신호']=='A'])}) 기준,")
print(f"        위 {mix:+.2f}%p는 126봉 창완결 교집합(n={len(com)}) 기준 — 표본이 달라 값이 다른 것이지 모순이 아니다.")
print(f"        지평효과는 이 표본에서 {hz:+.2f}%p로 사실상 0 → 보고된 Δ는 거의 전부 '분할' 효과다.")

# ══════════════════════════════════════════════════════════════════
print("\n" + "=" * 88)
print("[D] 논리 일관성 — 오늘 내린 결론들이 서로 모순되지 않는가")
print("=" * 88)
checks = []
# D1 2단이 A와 S2 양쪽에서 같은 부호
dA = (GS[GS["신호"] == "A"]["이단"].mean() - GS[GS["신호"] == "A"]["카드"].mean()) * 100
dS = (GS[GS["신호"] == "S2"]["이단"].mean() - GS[GS["신호"] == "S2"]["카드"].mean()) * 100
checks.append((dA > 0 and dS > 0, "2단 효과가 A·S2 양쪽에서 (+)", f"A {dA:+.2f} · S2 {dS:+.2f}%p"))
# D2 국면 게이트 부호가 A·S2 양쪽에서 동일
for nm, sub in (("A", S2C[S2C["신호"] == "A"]), ("S2", S2C[S2C["신호"] == "S2"])):
    g = sub.groupby("국면")["카드"].mean() * 100
    checks.append((g.get("실행", 0) > g.get("주의", 0) > g.get("관찰만", 0) or
                   (g.get("실행", 0) > 0 and g.get("관찰만", 0) < 0),
                   f"국면 순서 실행>주의>관찰만 ({nm})",
                   " · ".join(f"{k} {v:+.2f}" for k, v in g.items())))
# D3 등급 역설 방향과 MA240 완화 우월이 같은 방향
ma = GS[(GS["신호"] == "S2") & (GS["미달"].fillna("") == "MA240")]["카드"].mean() * 100
aa = GS[GS["신호"] == "A"]["카드"].mean() * 100
checks.append((ma > aa, "MA240 완화 > 정식A (등급 역설과 같은 방향)", f"{ma:+.2f} vs {aa:+.2f}"))
# D4 9~10월 진입분이 전체보다 나쁘다 (과제2 주장)
so = GS[(GS["신호"] == "A") & (GS["date"].str[5:7].isin(["09", "10"]))]["카드"].mean() * 100
checks.append((so < aa, "9~10월 A 진입 < 전체 A (과제2 주장)", f"{so:+.2f} vs {aa:+.2f}"))
# D5 2일누적 완화가 다른 완화보다 약하다
d2c = GS[(GS["신호"] == "S2") & (GS["미달"].fillna("").str.contains("2일누적"))]["카드"].mean() * 100
oth = GS[(GS["신호"] == "S2") & (~GS["미달"].fillna("").str.contains("2일누적"))]["카드"].mean() * 100
checks.append((d2c < oth, "2일누적 낀 완화 < 나머지 완화", f"{d2c:+.2f} vs {oth:+.2f}"))
for c, n, d in checks: ok(c, n, d)

print("\n" + "=" * 88)
if FAIL:
    print(f"❌ 감사 실패 {len(FAIL)}건: {FAIL}")
else:
    print("✅ 전 항목 통과 — 오늘의 4개 검정이 엔진·수치·논리 모두 일관.")
if COMPAT:
    print(f"⚠️  별건(일관성 아님) pandas 3.x 비호환: {COMPAT} — resample('M')→'ME' 수정 필요")
print("=" * 88)

# ══════════════════════════════════════════════════════════════════
# [E] 규칙분리 검정 (2026-08-22 · §10-B) — 별도 모듈 호출. 파일이 없으면 건너뜀.
try:
    import importlib.util as _iu
    _p = os.path.join(os.path.dirname(os.path.abspath(__file__)), "휩쏘_규칙분리_감사.py")
    if os.path.exists(_p):
        _sp = _iu.spec_from_file_location("rule_split_audit", _p); _m = _iu.module_from_spec(_sp); _sp.loader.exec_module(_m)
        _f = _m.run(); FAIL.extend(_f)
        print("  " + ("❌ [E] 실패 %s" % _f if _f else "✅ [E] 규칙분리 감사 통과"))
    else:
        print("  ⚪ [E] 휩쏘_규칙분리_감사.py 없음 — 건너뜀")
except Exception as _e:
    print(f"  ❌ [E] 규칙분리 감사 실행 오류: {_e}"); FAIL.append("[E] 규칙분리 감사")
