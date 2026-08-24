# -*- coding: utf-8 -*-
"""
panel_mask.py — 동결 패널의 결함 셀 "마스크 층"을 만든다. (2026-07-28)

설계 원칙
---------
1) 원본 CSV 를 절대 고치지 않는다.
   월봉_KIS_adj_v1_2026-07-28.csv 는 md5 8a8d7408422b8a006e260b5c4a6ed3a2 로
   동결·지문화되어 있다. 한 셀이라도 바꾸면 그 지문으로 낸 모든 성과가 무효가 된다.
   그래서 고치는 대신 "이 (코드,월) 은 가격으로 쓰지 마라" 목록을 따로 만든다.

2) 임계값은 수익률을 보고 정하지 않았다.
   - 저가하한 : 수정주가가 정수(원)이므로 최소 호가 변화가 1/P 이다.
                P=100원이면 한 틱이 곧 1%/월. 이건 데이터의 성질이지 튜닝이 아니다.
   - 동결     : 실제로 체결되는 종목이 정수 종가를 6개월 연속 똑같이 찍을 확률은
                사실상 0. 6개월 = 두 분기.
   - 상한     : 값을 안 자른다. 2^31-1 에 정확히 붙은 셀만 잘라낸다.
                1억원대 수정주가는 감자 역보정의 정상 결과일 수 있어서(뒤 참고)
                "크다"는 이유로 지우면 멀쩡한 종목을 죽인다.

3) 세 임계값 모두 민감도용 대안값을 같이 낸다(--sweep). 하나만 쓰고 끝내면
   그게 곧 튜닝이다.

쓰는 법
-------
    py panel_mask.py --selftest
    py panel_mask.py                       # 기본 floor=100, freeze=6
    py panel_mask.py --sweep               # 임계값별 삭제량만 출력
    py panel_mask.py --floor 50 --freeze 12
"""
import argparse, csv, collections, hashlib, json, os, sys

SRC_DEFAULT = "월봉_KIS_adj_v1_2026-07-28.csv"
OUT_DEFAULT = "_패널마스크_v1.csv"
INT32_MAX   = 2147483647
SAT_GUARD   = INT32_MAX - 1      # 2^31-2 이상이면 "잘린 값" 취급 (안전대 1)


# ------------------------------------------------------------------ 읽기
def load_panel(path):
    """{code: [(ym, close), ...]}  ym 오름차순."""
    by = collections.defaultdict(list)
    with open(path, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            by[r["code"]].append((r["ym"], int(r["close"])))
    for c in by:
        by[c].sort()
    return by


# ------------------------------------------------------------------ 규칙
def runs_of(series):
    """연속 동일 종가 구간을 (시작index, 끝index, 길이) 로 끊어 준다."""
    out = []
    i = 0
    n = len(series)
    while i < n:
        j = i
        while j + 1 < n and series[j + 1][1] == series[i][1]:
            j += 1
        out.append((i, j, j - i + 1))
        i = j + 1
    return out


def mask_one(series, floor, freeze, mark_return=True):
    """한 종목의 마스크. 반환 {ym: reason}. 먼저 붙은 사유가 이긴다."""
    m = {}

    def put(ym, why):
        m.setdefault(ym, why)

    # ㉮ INT32 포화 — 증명 가능한 오류
    for ym, p in series:
        if p >= SAT_GUARD:
            put(ym, "INT32포화")

    # ㉯ 무거래 동결 구간
    if freeze:
        for i, j, L in runs_of(series):
            if L >= freeze:
                for k in range(i, j + 1):
                    put(series[k][0], "동결%d" % freeze)
                # 동결이 풀린 다음 달은 몇 년치 움직임이 한 달에 몰려 찍힌다.
                # 그 한 달만 남기면 그게 곧 가짜 초과수익이 된다.
                if mark_return and j + 1 < len(series):
                    put(series[j + 1][0], "동결복귀")

    # ㉰ 저가 반올림 잡음
    if floor:
        for ym, p in series:
            if p < floor:
                put(ym, "저가%d" % floor)

    return m


def build(by, floor, freeze, mark_return=True):
    rows = []
    for c in sorted(by):
        for ym, why in sorted(mask_one(by[c], floor, freeze, mark_return).items()):
            rows.append((c, ym, why))
    return rows


# ------------------------------------------------------------------ 자가검사
def selftest():
    ok = []

    def t(name, cond):
        ok.append((name, bool(cond)))

    # ① 포화
    s = [("2000-01", 100), ("2000-02", INT32_MAX), ("2000-03", 100)]
    m = mask_one(s, 0, 0)
    t("① 포화 1셀만", m == {"2000-02": "INT32포화"})

    # ② 안전대: 2^31-2 도 잡는다
    t("② 안전대", mask_one([("a", SAT_GUARD)], 0, 0) == {"a": "INT32포화"})

    # ③ 정상가는 안 잡는다
    t("③ 정상가 통과", mask_one([("a", 1000000000)], 0, 0) == {})

    # ④ 동결 런 길이 = freeze 면 잡힌다
    s = [("m%02d" % i, 500) for i in range(6)] + [("m06", 700)]
    m = mask_one(s, 0, 6)
    t("④ 런6 전부", all(m.get("m%02d" % i) == "동결6" for i in range(6)))
    t("⑤ 복귀월 표시", m.get("m06") == "동결복귀")

    # ⑥ 런 길이 = freeze-1 이면 안 잡힌다
    s = [("m%02d" % i, 500) for i in range(5)] + [("m05", 700)]
    t("⑥ 런5 통과", mask_one(s, 0, 6) == {})

    # ⑦ 복귀월 끄기
    s = [("m%02d" % i, 500) for i in range(6)] + [("m06", 700)]
    t("⑦ 복귀 off", "m06" not in mask_one(s, 0, 6, mark_return=False))

    # ⑧ 마지막이 동결로 끝나면 복귀월이 없다
    s = [("m%02d" % i, 500) for i in range(6)]
    t("⑧ 꼬리 동결", len(mask_one(s, 0, 6)) == 6)

    # ⑨ 저가
    s = [("a", 99), ("b", 100), ("c", 101)]
    t("⑨ 저가 경계", mask_one(s, 100, 0) == {"a": "저가100"})

    # ⑩ 사유 우선순위: 포화가 저가보다 먼저 (같은 셀에 둘 다일 순 없지만 순서 고정 확인)
    s = [("a", 50)] * 1
    t("⑩ 저가만", mask_one(s, 100, 0) == {"a": "저가100"})

    # ⑪ 동결 + 저가 겹치면 동결이 먼저 (규칙 순서상)
    s = [("m%02d" % i, 50) for i in range(6)]
    t("⑪ 겹칠 때 동결 우선", set(mask_one(s, 100, 6).values()) == {"동결6"})

    # ⑫ runs_of 분해가 원본을 보존
    s = [("a", 1), ("b", 1), ("c", 2), ("d", 2), ("e", 3)]
    t("⑫ 런 분해", runs_of(s) == [(0, 1, 2), (2, 3, 2), (4, 4, 1)])

    # ⑬ 단일 행
    t("⑬ 1행", runs_of([("a", 5)]) == [(0, 0, 1)])

    # ⑭ 빈 시계열
    t("⑭ 빈 입력", runs_of([]) == [] and mask_one([], 100, 6) == {})

    # ⑮ build 가 정렬된 (code,ym) 을 낸다
    by = {"B": [("2000-01", 10)], "A": [("2000-02", 10), ("2000-01", 10)]}
    r = build(by, 100, 0)
    t("⑮ 정렬", [x[0] for x in r] == ["A", "A", "B"] and r[0][1] == "2000-01")

    # ⑯ 마스크는 원본을 건드리지 않는다
    src = [("a", 99), ("b", 500)]
    copy = list(src)
    mask_one(src, 100, 6)
    t("⑯ 원본 불변", src == copy)

    # ⑰ freeze=0 이면 동결 규칙 자체가 꺼진다
    s = [("m%02d" % i, 500) for i in range(50)]
    t("⑰ freeze off", mask_one(s, 0, 0) == {})

    # ⑱ floor=0 이면 저가 규칙이 꺼진다
    t("⑱ floor off", mask_one([("a", 1)], 0, 0) == {})

    n = sum(1 for _, b in ok if b)
    for name, b in ok:
        print(("  ✓ " if b else "  ✗ ") + name)
    print("자가검사 %d/%d %s" % (n, len(ok), "PASS" if n == len(ok) else "FAIL"))
    return 0 if n == len(ok) else 1


# ------------------------------------------------------------------ main
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--src", default=SRC_DEFAULT)
    ap.add_argument("--out", default=OUT_DEFAULT)
    ap.add_argument("--floor", type=int, default=100)
    ap.add_argument("--freeze", type=int, default=6)
    ap.add_argument("--no-return-mark", action="store_true")
    ap.add_argument("--sweep", action="store_true")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()

    if a.selftest:
        sys.exit(selftest())

    by = load_panel(a.src)
    tot = sum(len(v) for v in by.values())
    post = sum(1 for v in by.values() for ym, _ in v if ym >= "2010-01")
    print("원본 %s · 코드 %d · 행 %d" % (a.src, len(by), tot))

    if a.sweep:
        print("\n임계값 민감도 (마스크 셀 수 / 전체 대비 %% / 2010이후분)")
        print("  %-8s %-8s %10s %8s %10s" % ("floor", "freeze", "마스크", "비율%", "2010이후"))
        for fl in (0, 50, 100, 200):
            for fz in (0, 4, 6, 12):
                if fl == 0 and fz == 0:
                    continue
                r = build(by, fl, fz, not a.no_return_mark)
                p2 = sum(1 for _, ym, _ in r if ym >= "2010-01")
                print("  %-8d %-8d %10d %8.3f %10d" % (fl, fz, len(r), len(r) * 100.0 / tot, p2))
        return

    rows = build(by, a.floor, a.freeze, not a.no_return_mark)
    with open(a.out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["code", "ym", "reason"])
        w.writerows(rows)

    cnt = collections.Counter(r[2] for r in rows)
    p2 = sum(1 for _, ym, _ in rows if ym >= "2010-01")
    print("\n마스크 %d 셀 (%.3f%%) → %s" % (len(rows), len(rows) * 100.0 / tot, a.out))
    for k, v in cnt.most_common():
        print("   %-12s %6d" % (k, v))
    print("   2010-01 이후 %d / %d (%.3f%%)" % (p2, post, p2 * 100.0 / post))
    print("   영향 코드 %d / %d" % (len({r[0] for r in rows}), len(by)))

    h = hashlib.md5(open(a.out, "rb").read()).hexdigest()
    meta = {
        "마스크파일": a.out, "md5": h, "셀": len(rows),
        "원본": a.src, "원본md5": hashlib.md5(open(a.src, "rb").read()).hexdigest(),
        "임계_저가하한": a.floor, "임계_동결개월": a.freeze,
        "복귀월표시": not a.no_return_mark,
        "사유별": dict(cnt),
        "생성기": os.path.basename(__file__),
        "생성기md5": hashlib.md5(open(__file__, "rb").read()).hexdigest(),
    }
    with open("_패널마스크_v1_지문.json", "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    print("   마스크 md5 %s" % h)


if __name__ == "__main__":
    main()
