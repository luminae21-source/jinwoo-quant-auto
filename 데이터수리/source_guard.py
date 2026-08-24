# -*- coding: utf-8 -*-
"""
source_guard.py — KIS 패널을 pykrx 파생 패널로 교차검증하고, 불일치 월을 격리한다.
(2026-07-28)

왜 '접합 가드'가 아니라 '출처 가드'인가
--------------------------------------
원래 계획은 KIS(1996~2015) 와 pykrx 를 이어붙이는 접합 가드였다. 그런데 측정해 보니
접합이 필요 없었다:

  · KIS 단독 커버리지 2011~2026 = 100.00% (2010 = 99.76%)
  · 두 KIS 파일(1996~2015 / 2016~) 의 겹치는 셀 = 0 (중복 없는 이어붙임)
  · 이음선 2015-12→2016-01 의 이상배율 비율 1.12% — 주변 달(1.4~4.2%)보다 오히려 낮음
    → 레벨 불연속 없음

그래서 패널은 KIS 단독으로 쓰고, pykrx 는 원천이 아니라 **독립 검증자**로 남긴다.
이음선이 사라지고 검증자는 유지되니 양쪽으로 이득이다.

무엇을 격리하고, 왜 그것만 하는가
--------------------------------
겹침 402,654 셀 중 95.25% 가 배율 오차 0.1% 이내다. 오차 분포는 이봉(bimodal) 이다 —
중위 오차 0.000000, 95% 분위 0.00085 인데 99% 분위는 1.0(=정확히 2배). 즉 두 출처는
**같거나, 정수배로 어긋난다.** 완만한 잡음 구간이 없다.

격리 대상은 '배율이 1이 아닌 셀' 이 아니라 **배율이 바뀌는 달** 이다.
배율이 겹침 전체에서 상수라면(예: 항상 2.0) 그건 조정 기준일 차이일 뿐이고
수익률에는 아무 영향이 없다. 수익률을 망치는 건 배율의 '계단' 이다.

어느 쪽이 틀렸는지는 판정하지 않는다
----------------------------------
중재자로 ca_flags.csv 를 시도했으나 실제 브레이크포인트 1,162건 중 26건만 설명했고,
정수배인데 CA 기록이 없는 건이 78건이었다. 즉 ca_flags 는 불완전하고, 그러면
'기록 없음' 은 증거가 되지 못한다. 제3의 출처 없이 심판을 볼 수 없으므로
**심판을 보지 않고 해당 월을 빼는 쪽**을 택했다. 불일치가 셀의 2% 수준이라 감당된다.

쓰는 법
-------
    py source_guard.py --selftest
    py source_guard.py --sweep
    py source_guard.py                 # 기본 tol=0.02
"""
import argparse, csv, collections, hashlib, json, os, sys

KIS_FILES = ["월봉_KIS_adj_v1_2026-07-28.csv", "_월봉_KIS_adj_2016.csv"]
PK_FILES  = ["_월봉종가캐시_KOSPI_adj.csv", "_월봉종가캐시_KOSDAQ_adj.csv"]
OUT       = "_출처불일치_v1.csv"


def load(paths):
    d = {}
    for p in paths:
        with open(p, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                v = float(r["close"])
                if v > 0:
                    d[(r["code"], r["ym"])] = v
    return d


def breakpoints(ratios, tol):
    """ratios: [(ym, ratio)] ym 오름차순. 배율이 tol 넘게 바뀌는 달 목록.

    바뀐 '뒤쪽' 달을 돌려준다 — 수익률 r(M)=P(M)/P(M-1) 이 어긋나는 달이 M 이므로.
    """
    out = []
    for i in range(1, len(ratios)):
        a, b = ratios[i - 1][1], ratios[i][1]
        if a > 0 and abs(b / a - 1.0) > tol:
            out.append((ratios[i][0], b / a))
    return out


def build(kis, pk, tol, drop_last=True):
    ov = kis.keys() & pk.keys()
    if not ov:
        return [], None
    last = max(y for _, y in ov)
    byc = collections.defaultdict(list)
    for c, y in ov:
        byc[c].append((y, kis[(c, y)] / pk[(c, y)]))
    for c in byc:
        byc[c].sort()
    rows = []
    for c in sorted(byc):
        for ym, f in breakpoints(byc[c], tol):
            if drop_last and ym == last:
                continue          # 진행 중인 달 — 스냅샷 날짜 차이지 결함이 아니다
            rows.append((c, ym, "출처불일치", round(f, 6)))
    return rows, last


# ------------------------------------------------------------------ 자가검사
def selftest():
    ok = []
    def t(n, c): ok.append((n, bool(c)))

    # ① 상수배는 브레이크포인트가 아니다 (수익률 무해)
    t("① 상수배 무해", breakpoints([("a", 2.0), ("b", 2.0), ("c", 2.0)], 0.02) == [])

    # ② 계단은 잡는다, 그리고 '뒤쪽' 달을 돌려준다
    b = breakpoints([("a", 1.0), ("b", 2.0)], 0.02)
    t("② 계단 검출", len(b) == 1 and b[0][0] == "b")
    t("③ 배율값", abs(b[0][1] - 2.0) < 1e-9)

    # ④ tol 이내 흔들림은 통과
    t("④ tol 이내", breakpoints([("a", 1.0), ("b", 1.01)], 0.02) == [])
    t("⑤ tol 초과", len(breakpoints([("a", 1.0), ("b", 1.03)], 0.02)) == 1)

    # ⑥ 되돌림은 두 번 잡힌다 (한 달만 튄 경우 → 그 달과 그 다음 달)
    t("⑥ 되돌림 2건", len(breakpoints([("a",1.0),("b",2.0),("c",1.0)], 0.02)) == 2)

    # ⑦ 1개짜리·빈 입력
    t("⑦ 1개", breakpoints([("a", 1.0)], 0.02) == [])
    t("⑧ 빈 입력", breakpoints([], 0.02) == [])

    # ⑨ 0 배율은 나눗셈 사고를 안 낸다
    t("⑨ 0 안전", breakpoints([("a", 0.0), ("b", 1.0)], 0.02) == [])

    # ⑩ 마지막 달은 기본으로 뺀다
    K = {("X","2026-06"):100.0, ("X","2026-07"):200.0}
    P = {("X","2026-06"):100.0, ("X","2026-07"):100.0}
    r, last = build(K, P, 0.02)
    t("⑩ 마지막달 제외", r == [] and last == "2026-07")
    r2, _ = build(K, P, 0.02, drop_last=False)
    t("⑪ 옵션 끄면 잡힘", len(r2) == 1 and r2[0][1] == "2026-07")

    # ⑫ 겹치지 않으면 조용히 빈 결과
    t("⑫ 겹침 없음", build({("A","2000-01"):1.0}, {("B","2000-01"):1.0}, 0.02) == ([], None))

    # ⑬ 한쪽만 있는 달은 무시 (교집합)
    K2 = {("X","2000-01"):100.0, ("X","2000-02"):100.0, ("X","2000-03"):100.0}
    P2 = {("X","2000-01"):100.0, ("X","2000-03"):50.0}
    r3, _ = build(K2, P2, 0.02, drop_last=False)
    t("⑬ 교집합만", len(r3) == 1 and r3[0][1] == "2000-03")

    # ⑭ 정렬 (코드 → 월)
    K3 = {("B","2000-02"):2.0, ("B","2000-01"):1.0, ("A","2000-02"):2.0, ("A","2000-01"):1.0}
    P3 = {k: 1.0 for k in K3}
    r4, _ = build(K3, P3, 0.02, drop_last=False)
    t("⑭ 정렬", [x[0] for x in r4] == ["A", "B"])

    n = sum(1 for _, b2 in ok if b2)
    for name, b2 in ok:
        print(("  ✓ " if b2 else "  ✗ ") + name)
    print("자가검사 %d/%d %s" % (n, len(ok), "PASS" if n == len(ok) else "FAIL"))
    return 0 if n == len(ok) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--tol", type=float, default=0.02)
    ap.add_argument("--out", default=OUT)
    ap.add_argument("--keep-last", action="store_true")
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())

    kis = load(KIS_FILES); pk = load(PK_FILES)
    ov = kis.keys() & pk.keys()
    print("KIS %d셀 · pykrx %d셀 · 겹침 %d셀 / %d코드"
          % (len(kis), len(pk), len(ov), len({c for c, _ in ov})))

    if a.sweep:
        print("\n[tol 민감도]  %8s %10s %10s %10s" % ("tol", "격리월", "코드", "겹침대비%"))
        for tol in (0.005, 0.01, 0.02, 0.05, 0.10):
            r, _ = build(kis, pk, tol, not a.keep_last)
            print("            %8.3f %10d %10d %9.3f%%"
                  % (tol, len(r), len({x[0] for x in r}), len(r)*100.0/len(ov)))
        return

    rows, last = build(kis, pk, a.tol, not a.keep_last)
    with open(a.out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f); w.writerow(["code", "ym", "reason", "ratio_step"]); w.writerows(rows)
    print("\n격리 %d 월 / %d 코드 → %s" % (len(rows), len({x[0] for x in rows}), a.out))
    print("   (겹침 셀 대비 %.3f%%)" % (len(rows)*100.0/len(ov)))
    post = sum(1 for _, ym, _, _ in rows if ym >= "2010-01")
    print("   2010-01 이후 %d 월" % post)
    print("   제외한 진행중 달: %s" % last)
    h = hashlib.md5(open(a.out, "rb").read()).hexdigest()
    json.dump({"파일": a.out, "md5": h, "격리월": len(rows),
               "코드": len({x[0] for x in rows}), "tol": a.tol,
               "겹침셀": len(ov), "진행중달제외": last,
               "KIS원천": KIS_FILES, "pykrx원천": PK_FILES,
               "생성기": os.path.basename(__file__),
               "생성기md5": hashlib.md5(open(__file__, "rb").read()).hexdigest()},
              open("_출처불일치_v1_지문.json", "w", encoding="utf-8"),
              ensure_ascii=False, indent=2)
    print("   md5 %s" % h)


if __name__ == "__main__":
    main()
