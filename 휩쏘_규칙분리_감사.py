# -*- coding: utf-8 -*-
"""휩쏘_규칙분리 검정 — 일관성 감사 모듈 (휩쏘_일관성감사.py 가 말미에서 호출 · 단독 실행도 가능)
  E-1 엔진 동등성 : back_adjust / line_series / simulate ↔ 휩쏘_2단청산검정.py (같은 입력 → 같은 출력)
  E-2 수치 수준   : P0 ↔ S2_이벤트_통합.카드, P1 ↔ .이단, B형 P0 ↔ 역사원장.카드수익 (진행중 건 제외)
  E-3 내부 정합   : R_s95_t12_h == P0 · Q_t12_be == P1 · 결과.json 경계값 = 사전등록 고정값
  E-4 논리 명제   : 3축 전부 '기각' · U*는 전 분할에서 목표없음 계열(08-04 결론과 정합)
"""
import os, sys, json, importlib.util, inspect
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
HERE = os.path.dirname(os.path.abspath(__file__))
CAND = [HERE, "/home/claude/jq", "/mnt/user-data/uploads/진우퀀트"]
def F(n):
    for d in CAND:
        p = os.path.join(d, n)
        if os.path.exists(p): return p
    return os.path.join(HERE, n)
FAIL = []
def ok(c, name, detail=""):
    print(f"  {'✅' if c else '❌'} {name}" + (f"  — {detail}" if detail else ""))
    if not c: FAIL.append(name)
    return c
def load(n):
    sp = importlib.util.spec_from_file_location("m_" + str(abs(hash(n))), F(n))
    m = importlib.util.module_from_spec(sp); sp.loader.exec_module(m); return m

def run():
    print("\n[E] 규칙분리 검정 (2026-08-22) 감사")
    new, ref = load("휩쏘_규칙분리_검정.py"), load("휩쏘_2단청산검정.py")
    rng = np.random.default_rng(3); N = 3000
    dates = pd.bdate_range("2005-01-03", periods=N).strftime("%Y-%m-%d").values
    c = 100 * np.cumprod(1 + rng.normal(0, 0.02, N)); c[1500:] /= 5.0; c[2200:] *= 3.0
    o = c * (1 + rng.normal(0, 0.003, N)); h = np.maximum(o, c) * 1.01; l = np.minimum(o, c) * 0.99
    a = new.back_adjust(o.copy(), h.copy(), l.copy(), c.copy(), dates)
    b = ref.back_adjust(o.copy(), h.copy(), l.copy(), c.copy(), dates)
    ok(max(np.nanmax(np.abs(x - y)) for x, y in zip(a, b)) == 0.0, "E-1 back_adjust 동일")
    wa, ma = new.line_series(dates, a[3]); wb, mb = ref.line_series(dates, b[3])
    ok(np.nanmax(np.abs(wa - wb)) == 0.0 and np.nanmax(np.abs(ma - mb)) == 0.0, "E-1 line_series 동일")
    ha, la, ca = a[1], a[2], a[3]; diffs = 0
    for t in range(300, 2900, 37):
        e = ca[t]
        for tg in (e * 1.06, None):
            for sp, rt, sm in ((0.0, None, "tr"), (0.5, 0.12, "be"), (0.5, 0.20, "tr")):
                r1 = new.simulate(e, tg, e * 0.93, 0.12, ha, la, ca, t, N, 126, split=sp, runner_trail=rt, runner_stop_mode=sm)
                r2 = ref.simulate(e, tg, e * 0.93, 0.12, ha, la, ca, t, N, 126, split=sp, runner_trail=rt, runner_stop_mode=sm)
                if abs(r1[0] - r2[0]) > 0 or r1[1] != r2[1]: diffs += 1
    ok(diffs == 0, "E-1 simulate 동일 (수익·봉수)", f"불일치 {diffs}")

    R = pd.read_csv(F("휩쏘_규칙분리_이벤트.csv"), dtype={"code": str}); R["code"] = R["code"].str.zfill(6)
    S = pd.read_csv(F("S2_이벤트_통합.csv"), dtype={"code": str}); S["code"] = S["code"].str.zfill(6)
    M = R[R["유형"] != "B"].merge(S[["date", "code", "카드", "이단"]], left_on=["출발일", "code"], right_on=["date", "code"])
    done = M["출발일"] < "2026-06-01"
    d = (M.loc[done, "P0"] - M.loc[done, "카드"]).abs()
    ok(d.max() < 0.0006, "E-2 P0 = S2통합.카드 (완결분)", f"n={done.sum()} 최대오차 {d.max()*100:.4f}%p")
    d = (M.loc[done, "P1"] - M.loc[done, "이단"]).abs()
    ok(d.max() < 0.0006, "E-2 P1 = S2통합.이단 (완결분)", f"최대오차 {d.max()*100:.4f}%p")
    L = pd.read_csv(F("휩쏘_역사원장.csv"), dtype={"code": str}); L.columns = [x.strip().lstrip("﻿") for x in L.columns]
    L["code"] = L["code"].str.zfill(6); L["출발일"] = L["출발일"].astype(str)
    MB = R[R["유형"] == "B"].merge(L[["출발일", "code", "카드수익"]], on=["출발일", "code"])
    doneB = MB["출발일"] < "2026-06-01"
    d = (MB.loc[doneB, "P0"] * 100 - MB.loc[doneB, "카드수익"]).abs()
    ok(d.max() < 0.06, "E-2 B형 P0 = 원장.카드수익 (완결분)", f"n={doneB.sum()} 최대오차 {d.max():.4f}%p")

    A = R[R["유형"] != "B"]
    ok(np.allclose(A["R_s95_t12_h"], A["P0"]), "E-3 그리드 현행칸 R_s95_t12_h == P0")
    ok(np.allclose(R["Q_t12_be"], R["P1"]), "E-3 잔여 현행칸 Q_t12_be == P1")
    J = json.load(open(F("휩쏘_규칙분리_결과.json"), encoding="utf-8"))
    ok(abs(J["경계"]["Z1"] - 0.0864) < 1e-9 and J["경계"]["Z3"] == 0.0, "E-3 경계값 = 사전등록 v1.1 고정값", f"Z1 {J['경계']['Z1']} Z2 {J['경계']['Z2']:.4f} Z3 {J['경계']['Z3']}")
    m = J["주검정_짝훈련_홀검증"]
    ok(all(not m[ax]["채택"] for ax in ("Z1_목표거리", "Z2_변동성", "Z3_구조위치")), "E-4 주검정 3축 전부 기각 (판정문 명제)")
    ok(all(J[k]["U*"].endswith("_n") for k in ("주검정_짝훈련_홀검증", "강건성_홀훈련_짝검증")),
       "E-4 평균최적 단일규칙 U*는 홀짝 양방향에서 '목표없음' (08-04 §5와 정합) · 시간순 분할은 2/3되돌림",
       f"시간순 U* = {J['강건성_시간순']['U*']}")
    ok(m["검증_U*"]["중앙"] < m["검증_P0"]["중앙"] and m["검증_U*"]["승률"] < m["검증_P0"]["승률"],
       "E-4 U*는 P0보다 중앙·승률 열등 (평균 사고 중앙 파는 거래 — 08-04 재확인)",
       f"중앙 {m['검증_U*']['중앙']:+.2f} vs {m['검증_P0']['중앙']:+.2f} · 승률 {m['검증_U*']['승률']:.1f} vs {m['검증_P0']['승률']:.1f}")
    return FAIL

if __name__ == "__main__":
    f = run()
    print("\n" + ("❌ 실패: %s" % f if f else "✅ 규칙분리 감사 전 항목 통과"))
