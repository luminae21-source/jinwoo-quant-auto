#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
시장비대칭_검증.py — 동인 상승/하락 비대칭(공포 다운사이드) 검증 [2단계]
==============================================================================
질문: 검증된 동인(SOX·S&P500·외국인·달러)이 '오를 때'와 '내릴 때' 코스피에
      다르게 작용하나? 특히 하락(공포)이 상승보다 더 센가?
방법: 동인 x → x_up=max(x,0)·x_dn=min(x,0). 회귀 y_next ~ x_up + x_dn.
      비대칭비율 = |b_dn|/|b_up|. >1.3 하락비대칭(공포) · <0.77 상승 · else 대칭.
합격선: b_up·b_dn 둘 다 |t|≥2 + OOS(전·후반) 같은 방향. (데이터마이닝 방어 유지)
사전등록: 시장영향_검증_사전등록.md §8. 데이터: 시장영향_검증.build_dataset 재사용(25년 권장).
산출: 시장비대칭_검증_{시장}_결과.md  ·  사용: python 시장비대칭_검증.py [--market KOSDAQ] [--years 25] [--selftest]
무수정: production·기존 산출물. 신규. ⚠️ 측정이지 매매전략 아님.
"""
import os, sys, argparse, importlib.util
from datetime import date

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
HERE = os.path.dirname(os.path.abspath(__file__))

KEYS = ["sox", "sp", "foreign", "dxy"]   # 1단계 강건 채택 동인만
LABELS = {"sox": "美 반도체(SOX)", "sp": "S&P500", "foreign": "외국인 순매수", "dxy": "달러인덱스"}
HI, LO = 1.3, 0.77   # 비대칭 비율 임계


def _load_SI():
    spec = importlib.util.spec_from_file_location("si_mod", os.path.join(HERE, "시장영향_검증.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


def _ok(v):
    return v is not None and v == v


def asym(SI, rows, key):
    """y_next ~ x_up + x_dn 회귀 → 상승/하락 기울기·t·비대칭비율."""
    data = [(r[key], r["y_next"]) for r in rows if _ok(r.get(key)) and _ok(r.get("y_next"))]
    if len(data) < 50:
        return None
    X = [[1.0, max(x, 0.0), min(x, 0.0)] for x, _ in data]
    Y = [y for _, y in data]
    beta, t = SI.ols(X, Y)
    if beta is None:
        return None
    b_up, b_dn, t_up, t_dn = beta[1], beta[2], t[1], t[2]
    ratio = abs(b_dn) / abs(b_up) if b_up and abs(b_up) > 1e-9 else None
    return {"b_up": b_up, "b_dn": b_dn, "t_up": t_up, "t_dn": t_dn, "ratio": ratio, "n": len(data)}


def classify(a):
    """비대칭 판정. 둘 다 유의해야 비교."""
    if not a or a["t_up"] is None or a["t_dn"] is None or a["ratio"] is None:
        return "데이터부족", ""
    both_sig = abs(a["t_up"]) >= 2 and abs(a["t_dn"]) >= 2
    if not both_sig:
        return "한쪽만 유의(비교 보류)", ""
    r = a["ratio"]
    if r > HI:
        return "🔻 하락 비대칭(공포 큼)", f"하락 충격이 상승의 {r:.2f}배"
    if r < LO:
        return "🔺 상승 비대칭", f"상승 영향이 하락의 {1/r:.2f}배"
    return "⚖ 대칭", f"비율 {r:.2f}"


def run(market="KOSPI", years=25):
    SI = _load_SI()
    rows, err = SI.build_dataset(years, market)
    if err:
        print(f"❌ {err}"); return
    n = len(rows); half = n // 2
    mk = "코스피" if market == "KOSPI" else "코스닥"; suf = market.lower()
    res = []
    for k in KEYS:
        a = asym(SI, rows, k)
        a1 = asym(SI, rows[:half], k); a2 = asym(SI, rows[half:], k)
        oos = ""
        if a1 and a2 and a1["ratio"] and a2["ratio"]:
            d1 = a1["ratio"] > 1; d2 = a2["ratio"] > 1   # 전·후반 둘 다 하락비대칭 방향?
            oos = "O" if d1 == d2 else "X"
        verdict, note = classify(a)
        res.append((k, a, verdict, note, oos))
    # 출력
    L = [f"# 시장 비대칭 검증 ({mk}) — {date.today()}", "",
         f"> 동인 상승/하락 비대칭(공포 다운사이드). 표본 {n}일({years}년). 사전등록 §8.",
         "> 비율=|하락기울기|/|상승기울기|. >1.3 하락비대칭(공포)·<0.77 상승·else 대칭. 둘 다 |t|≥2여야 채택.", "",
         "| 동인 | 상승기울기(t) | 하락기울기(t) | 비율 | OOS | 판정 |",
         "|---|---|---|---|---|---|"]
    for k, a, verdict, note, oos in res:
        if not a:
            L.append(f"| {LABELS[k]} | — | — | — | — | 데이터부족 |"); continue
        L.append(f"| {LABELS[k]} | {a['b_up']:+.3f}(t={a['t_up']:+.1f}) | {a['b_dn']:+.3f}(t={a['t_dn']:+.1f}) "
                 f"| {a['ratio']:.2f}" + (f" | {oos}" if oos else " | —") + f" | {verdict} {note} |")
    # 요약
    fear = [LABELS[k] for k, a, v, nt, o in res if v.startswith("🔻") and o == "O"]
    L += ["", "## 결론",
          f"- **하락 비대칭(공포·OOS통과)**: {', '.join(fear) if fear else '없음'}",
          "- 비율>1.3 = 그 동인이 *내릴 때* 코스피에 더 큰 충격(손실회피·공포). 급락 대비에 함의.",
          "- ⚠️ 측정이지 매매전략 아님. forward·거래비용 별도. 결정·책임은 진우.",
          "", f"*데이터: 시장영향_검증.build_dataset({years}년, {market}). 룩어헤드 차단.*"]
    md = "\n".join(L)
    open(os.path.join(HERE, f"시장비대칭_검증_{suf}_결과.md"), "w", encoding="utf-8").write(md)
    print(md)
    print(f"\n[산출] 시장비대칭_검증_{suf}_결과.md")


def _selftest():
    ok = 0
    def chk(n, c):
        nonlocal ok; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    SI = _load_SI()
    import random; random.seed(5)
    # 하락 비대칭 심기: y = 0.1*up + 0.4*dn (하락 4배) + 작은 노이즈
    rows = []
    for _ in range(400):
        x = random.gauss(0, 1)
        y = 0.1 * max(x, 0) + 0.4 * min(x, 0) + random.gauss(0, 0.05)
        rows.append({"sox": x, "y_next": y})
    a = asym(SI, rows, "sox")
    chk("회귀 동작", a is not None and a["ratio"] is not None)
    chk("하락기울기 큼(b_dn)", a and abs(a["b_dn"]) > abs(a["b_up"]))
    chk("비율≈4", a and 3.0 < a["ratio"] < 5.0)
    v, _ = classify(a)
    chk("판정=하락비대칭", v.startswith("🔻"))
    # 대칭 케이스: y = 0.2*x
    rows2 = []
    for _ in range(400):
        x = random.gauss(0, 1); y = 0.2 * x + random.gauss(0, 0.03)
        rows2.append({"sox": x, "y_next": y})
    a2 = asym(SI, rows2, "sox")
    v2, _ = classify(a2)
    chk("대칭 판정", v2.startswith("⚖") or "대칭" in v2)
    chk("classify 데이터부족 안전", classify(None)[0] == "데이터부족")
    print(f"✅ 시장비대칭_검증 셀프테스트 ({ok}/6)")
    return ok >= 5


def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--market", default="KOSPI"); ap.add_argument("--years", type=int, default=25)
    a = ap.parse_args()
    if a.selftest:
        _selftest(); return
    run(a.market.upper(), a.years)


if __name__ == "__main__":
    main()
