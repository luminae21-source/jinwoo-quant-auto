#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
백서_색인_갱신.py — 백서 부록에 연구 갈래 색인을 자동 반영 (2026-08-04)

── 무엇을 하고, 무엇을 하지 않는가 ────────────────────────────
하는 것:
  1) `부록 B-3. 연구 갈래 색인` 을 **마커 사이에서만** 다시 쓴다.
     활성 갈래 / 회수 후보(기록은 있는데 방치된 갈래) / 총계.
  2) `부록 B-1 색인` 표와 실제 문서의 `부록 B-1x` 제목을 **대조**해
     한쪽에만 있는 항목을 보고한다.

하지 않는 것:
  · `부록 B-1 색인` 표를 고쳐 쓰지 않는다.
    그 표는 B-1b=결함①, B-1i=결론 처럼 **사람이 매긴 판정과 읽는 순서**다.
    파일명에서 자동 생성하면 의미가 통째로 날아간다. 대조만 하고 손대지 않는다.
  · 백서의 다른 어떤 줄도 건드리지 않는다. 실행 전 항상 백업을 뜬다.

사용:
    py 백서_색인_갱신.py            # 반영
    py 백서_색인_갱신.py --check    # 검사만, 파일 안 씀
"""
import argparse, datetime as dt, importlib.util, os, re, shutil, sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
MD = os.path.join(HERE, "백서_빌더", "진우퀀트_백서.md")
GEN = os.path.join(HERE, "연구색인_생성.py")
START = "<!-- AUTO:연구색인 시작 -->"
END = "<!-- AUTO:연구색인 끝 -->"


def load_index():
    spec = importlib.util.spec_from_file_location("연구색인", GEN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def consistency(text):
    """부록 B-1x 제목 ↔ 부록 B-1 색인 표 대조. (제목집합, 표집합, 표누락, 문서누락)"""
    heads = set(re.findall(r"^#{2,5}.*?부록\s+(B-\d+[a-z]?)\.", text, re.M))
    # 색인 표는 제목 뒤 여러 문단 사이에 있다. 제목 이후를 통째로 훑되
    # 다음 "### " 제목에서 멈춘다 (뒤쪽 다른 표를 주워오지 않도록).
    i = text.find("### 부록 B-1 색인")
    tbl = set()
    if i >= 0:
        seg = text[i + 10:]
        j = seg.find("\n### ")
        if j > 0:
            seg = seg[:j]
        tbl = set(re.findall(r"^\|\s*\**\s*(B-\d+[a-z]?)\s*\**\s*\|", seg, re.M))
    return heads, tbl, sorted(heads - tbl), sorted(tbl - heads)


def esc(s):
    return str(s).replace("|", "\\|")


def block(rows, nfiles, cons):
    now = dt.datetime.now()
    act = [r for r in rows if r["state"] == "활성"]
    rec = [r for r in rows if r["state"] == "최근"]
    dorm = [r for r in rows if r["state"] == "휴면"]
    # 회수 후보 — 기록(md)이 남아 있는데 손 놓은 지 오래된 갈래
    cand = sorted([r for r in dorm if r["doc"] > 0], key=lambda r: r["newest"])
    L = []
    A = L.append
    A(START)
    A("")
    A("### 부록 B-3. 연구 갈래 색인 (자동 생성)")
    A("")
    A("> 이 절은 `백서_색인_갱신.py` 가 통째로 다시 쓴다. **손으로 고치지 말 것** — 다음 실행에 덮인다.")
    A(f"> 갱신 {now:%Y-%m-%d %H:%M} · 상세 표: `강화키트/진우퀀트_연구색인.html` (허브 4번째 탭)")
    A("")
    A("연구가 사라지는 경로는 삭제가 아니라 **잊히는 것**이다. 결론이 난 갈래만 백서에 실으면")
    A("미완성 연구는 목록에서 빠지고, 빠진 순간 존재가 지워진다. 이 표는 **결론 여부와 무관하게** 전부 싣는다.")
    A("")
    A(f"**총계** — 갈래 {len(rows):,} · 파일 {nfiles:,} · "
      f"활성(7일내) {len(act)} · 최근(30일내) {len(rec)} · 휴면(30일↑) {len(dorm)}")
    A("")
    A("#### B-3a. 활성 갈래 — 지금 손이 가 있는 것 (상위 30)")
    A("")
    A("| 갈래 | 파일 | 소스 | 기록 | 산출물 | 최종수정 |")
    A("|---|---:|---:|---:|---:|---|")
    for r in act[:30]:
        A(f"| {esc(r['key'])} | {r['n']} | {r['src']} | {r['doc']} | {r['out']} | "
          f"{dt.datetime.fromtimestamp(r['newest']):%Y-%m-%d} |")
    A("")
    A("#### B-3b. 회수 후보 — 기록은 남았는데 30일 넘게 방치된 갈래 (오래된 순 25)")
    A("")
    A("> 휴면은 접었다는 뜻이 아니다. **손을 놓은 지 30일이 넘었다**는 뜻일 뿐이다.")
    A("> 기록(md)이 남아 있다는 건 무언가 결론을 적어뒀다는 뜻이니, 접기 전에 한 번은 다시 볼 값어치가 있다.")
    A("")
    A("| 갈래 | 파일 | 기록 | 최종수정 | 방치 |")
    A("|---|---:|---:|---|---:|")
    for r in cand[:25]:
        d = (now - dt.datetime.fromtimestamp(r["newest"])).days
        A(f"| {esc(r['key'])} | {r['n']} | {r['doc']} | "
          f"{dt.datetime.fromtimestamp(r['newest']):%Y-%m-%d} | {d}일 |")
    A("")
    heads, tbl, miss_tbl, miss_doc = cons
    A("#### B-3c. 부록 B-1 색인 정합성 (대조만 — 표는 고치지 않는다)")
    A("")
    A(f"문서에 실린 `부록 B-1x` 제목 {len(heads)}개 · 색인 표 등재 {len(tbl)}개")
    A("")
    if not miss_tbl and not miss_doc:
        A("✅ 일치. 누락 없음.")
    else:
        if miss_tbl:
            A(f"🔴 **색인 표에 없는 부록**: {', '.join(miss_tbl)} — 표에 한 줄 추가해야 한다.")
        if miss_doc:
            A(f"🔶 **표에는 있는데 본문에 없는 항목**: {', '.join(miss_doc)} — "
              f"제목 형식이 다르거나(이모지·`.` 누락) 본문이 아직 안 들어왔다.")
    A("")
    A(END)
    return "\n".join(L)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="검사만 하고 파일을 쓰지 않는다")
    ap.add_argument("--md", default=MD)
    a = ap.parse_args()

    text = open(a.md, encoding="utf-8").read()
    # 자동 블록(부록 B-3)은 대조 대상이 아니다. 스스로 만든 제목을
    # "표에 없다"고 되짚는 자기참조 오탐을 막는다.
    cons = consistency(re.sub(re.escape(START) + r".*?" + re.escape(END),
                              "", text, flags=re.S))
    heads, tbl, miss_tbl, miss_doc = cons
    print(f"부록 B-1 계열 제목 {len(heads)}개 · 색인 표 {len(tbl)}개")
    if miss_tbl:
        print(f"  🔴 표 누락: {', '.join(miss_tbl)}")
    if miss_doc:
        print(f"  🔶 본문 누락: {', '.join(miss_doc)}")
    if not miss_tbl and not miss_doc:
        print("  ✅ 일치")

    mod = load_index()
    rows, nfiles = mod.collect(HERE)
    blk = block(rows, nfiles, cons)
    act = sum(1 for r in rows if r["state"] == "활성")
    print(f"연구 갈래 {len(rows)} · 파일 {nfiles} · 활성 {act}")

    if a.check:
        print("--check — 파일을 쓰지 않았다.")
        return 0

    bak = a.md + dt.datetime.now().strftime(".bak_색인_%Y%m%d_%H%M")
    shutil.copy2(a.md, bak)

    if START in text and END in text:
        new = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda m: blk, text, flags=re.S)
        where = "기존 블록 교체"
    else:
        anchor = "\n## 부록 C."
        i = text.find(anchor)
        if i < 0:
            new = text.rstrip("\n") + "\n\n" + blk + "\n"
            where = "문서 끝에 추가"
        else:
            new = text[:i] + "\n" + blk + "\n" + text[i:]
            where = "부록 C 앞에 삽입"
    open(a.md, "w", encoding="utf-8").write(new)
    print(f"백서 반영 완료 ({where}) · 백업 {os.path.basename(bak)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
