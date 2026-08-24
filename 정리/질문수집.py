# -*- coding: utf-8 -*-
r"""질문수집.py — 흩어진 문서에서 '제기된 질문/과제'를 전수로 긁는다. (2026-08-20)

왜: 질문은 7월 문서에, 답은 8월 백서에 있다. 둘을 잇는 대장이 없어서
    같은 것을 여러 번 묻고, 답이 나온 줄 모르고, 문서만 늘어난다.

무엇: 아래 원천에서 과제/질문/미해결로 보이는 줄을 뽑아 CSV 로 만든다.
      판정(통합·융합·구분·폐기)은 사람이 한다. 이 스크립트는 **재료만** 모은다.

    py 정리\질문수집.py            → 정리\_질문원재료.csv
    py 정리\질문수집.py --selftest
"""
import csv, io, os, re, sys, argparse

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

SRC = [
    ("재조명", "진우퀀트_재조명_리포트_2026-07-28.md"),
    ("인수인계3", "진우퀀트_휩쏘_인수인계.md"),
    ("백서", os.path.join("백서_빌더", "진우퀀트_백서.md")),
    ("런북", os.path.join("데이터수리", "수정주가_재수집_런북.md")),
    ("한장", os.path.join("백서_빌더", "현재상태_한장.md")),
    ("리빌딩v5", "리빌딩_v5_마스터플랜.md"),
    ("관제보드", "진우퀀트_관제보드.md"),
    ("점검0802", "진우퀀트_점검_20260802.md"),
    ("중간정리", "중간정리_2026-07-26.md"),
    ("작업현황판", "진우퀀트_작업현황판.md"),
    ("마스터인덱스", "진우퀀트_마스터인덱스.md"),
    ("v372진행", "v3.7.2_진행현황.md"),
    ("수익코어", "수익코어_재정의_선택지.md"),
    ("통합인수인계", "진우퀀트_통합인수인계_2026-06-14.md"),
    ("FnGuide", os.path.join("데이터수리", "_FnGuide_수령_체크리스트.md")),
]

# 과제/질문으로 보이는 신호
OPEN = re.compile(
    r"미해결|미착수|미확인|미반영|미검증|미감사|미산출|안 쟀|안 했|못 했|"
    r"TODO|확인 필요|필요하다|해야 한|해야 함|남은 것|남은 과제|열린 과제|열린 것|"
    r"다음 과제|다음 단계|다음 한 가지|즉시 수리|수리 목록|과제 \d|\[ \]|"
    r"재실행|재판정|재측정|정해야|정의해야|검증해야")
# 이미 끝났다는 신호
DONE = re.compile(r"✅|완료|닫힘|해결됨|판정 완료|~~")
DROP = re.compile(r"⛔ 철회|기각|폐기|사장|취소")
# 질문형
QMARK = re.compile(r"\?$|인가\b|는가\b|일까|할까|되나\b")


def clean(s):
    s = s.strip()
    s = re.sub(r"^[\s>*\-+#|]+", "", s)          # 마크다운 장식 제거
    s = re.sub(r"\*\*|`|~~", "", s)
    s = re.sub(r"\s+", " ", s)
    return s.strip(" |")


def classify(line):
    if DROP.search(line): return "폐기"
    if DONE.search(line): return "완료표시"
    if OPEN.search(line): return "열림"
    return ""


def scan(tag, path):
    rows = []
    if not os.path.exists(path):
        return rows
    txt = io.open(path, encoding="utf-8", errors="replace").read()
    h1 = h2 = ""
    for i, raw in enumerate(txt.splitlines(), 1):
        m = re.match(r"^(#{1,3})\s+(.*)$", raw)
        if m:
            if len(m.group(1)) <= 2: h1, h2 = clean(m.group(2)), ""
            else: h2 = clean(m.group(2))
            continue
        c = classify(raw)
        q = bool(QMARK.search(raw.strip()))
        if not c and not q:
            continue
        t = clean(raw)
        if len(t) < 12 or len(t) > 400:
            continue
        rows.append(dict(원천=tag, 줄=i, 장=h1[:60], 절=h2[:60],
                         상태표시=c, 질문형=("Y" if q else ""), 내용=t[:300]))
    return rows


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(HERE, "정리", "_질문원재료.csv"))
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())

    allrows, miss = [], []
    print("원천 스캔")
    for tag, rel in SRC:
        p = os.path.join(HERE, rel)
        if not os.path.exists(p):
            miss.append(rel); print(f"  ⚠️ 없음  {tag:12s} {rel}"); continue
        r = scan(tag, p)
        allrows += r
        print(f"  {tag:12s} {len(r):4d}건   {rel}")
    with io.open(a.out, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=["원천", "줄", "장", "절", "상태표시", "질문형", "내용"])
        w.writeheader(); w.writerows(allrows)
    print(f"\n총 {len(allrows)}건 → {os.path.relpath(a.out, HERE)}")
    from collections import Counter
    c = Counter(r["상태표시"] or "(무표시)" for r in allrows)
    for k, v in c.most_common():
        print(f"  {k:8s} {v}")
    if miss:
        print("\n못 찾은 원천:", ", ".join(miss))


def selftest():
    ok = []
    def t(n, c): ok.append((n, bool(c)))
    t("① 장식 제거", clean("  - **굵게** `코드`  ") == "굵게 코드")
    t("② 표 파이프 제거", clean("| 항목 | 값 |") == "항목 | 값")
    t("③ 열림 판정", classify("이건 미해결이다") == "열림")
    t("④ 완료 판정", classify("✅ 완료했다") == "완료표시")
    t("⑤ 폐기 우선", classify("✅ 완료 ⛔ 철회") == "폐기")
    t("⑥ 무관한 줄", classify("그냥 설명하는 문장") == "")
    t("⑦ 질문형 탐지", bool(QMARK.search("이게 맞는가")))
    t("⑧ 질문형 물음표", bool(QMARK.search("정말?")))
    t("⑨ 원천 목록 존재", len(SRC) >= 10)
    found = sum(1 for _, r in SRC if os.path.exists(os.path.join(HERE, r)))
    t("⑩ 원천 과반 존재", found >= len(SRC) // 2)
    t("⑪ 짧은 줄 제외됨", len(clean("- 짧음")) < 12)
    n = sum(1 for _, b in ok if b)
    for name, b in ok: print(("  ✓ " if b else "  ✗ ") + name)
    print("자가검사 %d/%d %s · 원천 %d/%d 존재"
          % (n, len(ok), "PASS" if n == len(ok) else "FAIL", found, len(SRC)))
    return 0 if n == len(ok) else 1


if __name__ == "__main__":
    main()
