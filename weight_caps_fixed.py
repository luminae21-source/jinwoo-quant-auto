# -*- coding: utf-8 -*-
"""weight_caps_fixed.py — score_v37_2.py L67-99 `apply_weight_caps` 버그 수정판 (2026-07-28)

[버그] 원본은 캡 적용 *후* 합계 100% 재정규화를 하므로 picks가 적으면 캡이 무효화된다.
  예: picks 3종 → 각 15% 캡 → 합 0.45 → /0.45 정규화 → 각 33.3% (캡의 2.2배)

[수정 원칙] "캡을 깨느니 현금을 남긴다."
  반복 캡핑: ① 종목캡 초과분을 여유 있는 종목에 비례 재분배 → ② 섹터캡 초과 섹터는
  비례 축소(축소분은 현금) → 수렴할 때까지 반복. 전 종목이 캡이면 잔여는 현금.

[적용법 — 둘 중 하나]
  A) score_v37_2.py 상단에 `from weight_caps_fixed import apply_weight_caps_v2` 추가 후
     기존 apply_weight_caps 호출을 apply_weight_caps_v2로 교체 (반환값에 cash 추가됨 주의)
  B) 원본 함수 본문을 아래 apply_weight_caps_v2 본문으로 교체

실행하면 셀프테스트 7종을 돌린다:  py weight_caps_fixed.py
"""
from collections import defaultdict

EPS = 1e-9


def apply_weight_caps_v2(weights, sectors=None, stock_cap=0.15, sector_cap=0.35, max_iter=200):
    """반환: (weights_dict, cash)  — sum(weights)+cash == 1.0

    weights: {code: 비중} (음수는 0 처리, 합은 내부에서 1로 정규화 후 시작)
    sectors: {code: 섹터명} (없으면 섹터캡 생략)
    """
    w = {k: max(0.0, float(v)) for k, v in weights.items()}
    total = sum(w.values())
    if total <= 0:
        return {k: 0.0 for k in w}, 1.0
    w = {k: v / total for k, v in w.items()}
    sectors = sectors or {}

    for _ in range(max_iter):
        changed = False

        # ① 종목캡: 초과분을 '캡 미달 종목'의 여유공간에 비례 재분배
        over = {k: v for k, v in w.items() if v > stock_cap + EPS}
        if over:
            excess = sum(v - stock_cap for v in over.values())
            for k in over:
                w[k] = stock_cap
            free = {k: (stock_cap - w[k]) for k in w if k not in over and w[k] < stock_cap - EPS}
            room = sum(free.values())
            if room > EPS:
                give = min(excess, room)
                for k, r in free.items():
                    w[k] += give * (r / room)
            # room이 없으면 초과분은 현금으로 남는다 (재분배 안 함)
            changed = True

        # ② 섹터캡: 초과 섹터를 비례 축소 (축소분은 현금 — 타 섹터로 밀어넣지 않는 보수 설계)
        if sectors:
            sec_sum = defaultdict(float)
            for k, v in w.items():
                sec_sum[sectors.get(k, "기타")] += v
            for s, tot in sec_sum.items():
                if tot > sector_cap + EPS:
                    scale = sector_cap / tot
                    for k in w:
                        if sectors.get(k, "기타") == s:
                            w[k] *= scale
                    changed = True

        if not changed:
            break

    cash = max(0.0, 1.0 - sum(w.values()))
    return w, cash


# ─────────────────────────── 셀프테스트 ───────────────────────────
def _check(name, cond):
    print(("  PASS  " if cond else "  FAIL  ") + name)
    return cond


def selftest():
    ok = True
    SC, XC = 0.15, 0.35

    # 1) 원본 버그 재현 케이스: 3종 동일가중 → 각 15%, 현금 55%
    w, cash = apply_weight_caps_v2({"A": 1, "B": 1, "C": 1}, stock_cap=SC, sector_cap=XC)
    ok &= _check("3종: 각 15% (원본은 33.3%였음)", all(abs(v - SC) < 1e-6 for v in w.values()))
    ok &= _check("3종: 현금 55%", abs(cash - 0.55) < 1e-6)

    # 2) 10종 동일가중(10%) → 캡 미발동, 현금 0
    w, cash = apply_weight_caps_v2({f"S{i}": 1 for i in range(10)}, stock_cap=SC, sector_cap=XC)
    ok &= _check("10종: 무변화·현금 0", abs(cash) < 1e-6 and all(abs(v - 0.1) < 1e-6 for v in w.values()))

    # 3) 한 종목 쏠림: {A:0.9, B:0.1} → A 15% 캡, B가 여유만큼 흡수(캡까지), 잔여 현금
    w, cash = apply_weight_caps_v2({"A": 0.9, "B": 0.1}, stock_cap=SC, sector_cap=XC)
    ok &= _check("쏠림: A=15%", abs(w["A"] - SC) < 1e-6)
    ok &= _check("쏠림: B<=15%", w["B"] <= SC + EPS)
    ok &= _check("쏠림: 합+현금=1", abs(sum(w.values()) + cash - 1.0) < 1e-6)

    # 4) 섹터캡: 반도체 4종 각 12% (섹터합 48% > 35%) + 타섹터 다수
    codes = {f"H{i}": "반도체" for i in range(4)}
    codes.update({f"O{i}": f"기타{i}" for i in range(6)})
    raw = {k: (0.12 if k.startswith("H") else 0.52 / 6) for k in codes}
    w, cash = apply_weight_caps_v2(raw, sectors=codes, stock_cap=SC, sector_cap=XC)
    semi = sum(v for k, v in w.items() if codes[k] == "반도체")
    ok &= _check("섹터: 반도체 합<=35%", semi <= XC + 1e-6)

    # 5) 불변식 일괄: 임의 케이스에서 종목캡·섹터캡·합계 위반 없음
    import random
    random.seed(42)
    for t in range(200):
        n = random.randint(1, 20)
        raw = {f"C{i}": random.random() for i in range(n)}
        secs = {f"C{i}": f"S{random.randint(0, 3)}" for i in range(n)}
        w, cash = apply_weight_caps_v2(raw, sectors=secs, stock_cap=SC, sector_cap=XC)
        assert all(v <= SC + 1e-6 for v in w.values()), f"종목캡 위반 t={t}"
        sec_sum = defaultdict(float)
        for k, v in w.items():
            sec_sum[secs[k]] += v
        assert all(v <= XC + 1e-6 for v in sec_sum.values()), f"섹터캡 위반 t={t}"
        assert abs(sum(w.values()) + cash - 1.0) < 1e-6, f"합계 위반 t={t}"
    ok &= _check("무작위 200케이스: 종목캡·섹터캡·합계 전부 준수", True)

    print("\n결과: " + ("전부 통과 ✅" if ok else "실패 있음 ❌"))
    return ok


if __name__ == "__main__":
    raise SystemExit(0 if selftest() else 1)
