# -*- coding: utf-8 -*-
r"""전체스캔.py — 진우퀀트 전수 스캔 · 체계 실측 (2026-08-20)

무엇: 파일 하나하나가 '어디에 걸려 있는지'를 실측한다.
      허브(정본 진입점)·앱 JOBS·bat 런처·다른 문서에서 참조되는지를 본다.
      아무데도 안 걸린 것 = 고아. 고아가 많으면 그게 곧 '체계 없음'이다.

판정하지 않는다. 세기만 한다.
    py 정리\전체스캔.py
"""
import os, re, io, csv, time, collections

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = ("_백업", "_to_delete", "_보관", "_archive", "__pycache__", "__jqpyc__",
        ".git", "_stage_tmp", "_stagetmp", "_회귀", "감사/진우퀀트_2026", "카드뉴스")
NOW = time.time()


def skip(p):
    q = p.replace("\\", "/")
    return any(s in q for s in SKIP)


def walk(exts):
    out = []
    for dp, dns, fns in os.walk(ROOT):
        dns[:] = [d for d in dns if not skip(os.path.join(dp, d))]
        if skip(dp):
            continue
        for fn in fns:
            if os.path.splitext(fn)[1].lower() in exts:
                out.append(os.path.relpath(os.path.join(dp, fn), ROOT))
    return out


def read(p):
    try:
        return io.open(os.path.join(ROOT, p), encoding="utf-8", errors="replace").read()
    except Exception:
        return ""


# ── 1. 참조원 수집: 허브 · 앱 · bat · 주요 문서
refs = collections.defaultdict(set)      # 파일명 -> {참조한 곳}
HUB = os.path.join("강화키트", "진우퀀트_허브.html")


def note(text, src):
    for m in re.findall(r'[\w가-힣._\-]+\.(?:py|html|md|csv|bat|json|tsv)', text):
        refs[os.path.basename(m)].add(src)


if os.path.exists(os.path.join(ROOT, HUB)):
    note(read(HUB), "허브")
for f in ("진우퀀트_앱.py", "jq_console.py", "강화키트/jq_hub.py"):
    if os.path.exists(os.path.join(ROOT, f)):
        note(read(f), "앱/허브생성기")
nbat = 0
for b in walk({".bat"}):
    nbat += 1
    try:
        note(io.open(os.path.join(ROOT, b), encoding="cp949", errors="replace").read(), "bat")
    except Exception:
        pass
for d in ("백서_빌더/진우퀀트_백서.md", "데이터수리/수정주가_재수집_런북.md",
          "진우퀀트_휩쏘_인수인계.md", "리빌딩_v5_마스터플랜.md",
          "진우퀀트_재조명_리포트_2026-07-28.md"):
    if os.path.exists(os.path.join(ROOT, d)):
        note(read(d), "핵심문서")

# ── 2. 분류
rows = []
for p in walk({".py", ".html", ".md"}):
    base = os.path.basename(p)
    r = refs.get(base, set())
    try:
        age = (NOW - os.path.getmtime(os.path.join(ROOT, p))) / 86400
    except OSError:
        age = 999
    rows.append(dict(경로=p, 종류=os.path.splitext(p)[1][1:], 나이일=int(age),
                     허브=("Y" if "허브" in r else ""),
                     앱=("Y" if "앱/허브생성기" in r else ""),
                     bat=("Y" if "bat" in r else ""),
                     문서=("Y" if "핵심문서" in r else ""),
                     참조수=len(r)))

# ── 3. 집계
tot = len(rows)
orphan = [r for r in rows if r["참조수"] == 0]
hub = [r for r in rows if r["허브"] == "Y"]
live = [r for r in rows if r["참조수"] > 0 and r["나이일"] <= 45]

print("=" * 62)
print(" 진우퀀트 전수 스캔 (백업·보관 제외)")
print("=" * 62)
print(f"  대상 파일 {tot:,}개 (py/html/md) · bat 런처 {nbat}개")
print(f"  허브에 걸림      {len(hub):5,}  ({len(hub)*100//tot}%)")
print(f"  어디든 참조됨    {tot-len(orphan):5,}  ({(tot-len(orphan))*100//tot}%)")
print(f"  ⚠️ 고아(무참조)  {len(orphan):5,}  ({len(orphan)*100//tot}%)")
print(f"  살아있음(참조+45일내) {len(live):4,}")

print("\n[종류별]")
for k in ("py", "html", "md"):
    g = [r for r in rows if r["종류"] == k]
    o = [r for r in g if r["참조수"] == 0]
    h = [r for r in g if r["허브"] == "Y"]
    print(f"  {k:5s} 전체 {len(g):4,} · 허브 {len(h):3,} · 고아 {len(o):4,}")

print("\n[폴더별 고아 상위]")
c = collections.Counter(os.path.dirname(r["경로"]) or "(루트)" for r in orphan)
for k, v in c.most_common(8):
    print(f"  {v:4,}  {k}")

print("\n[최근 45일 수정됐는데 고아 = 최근 작업인데 안 걸린 것]")
recent = sorted([r for r in orphan if r["나이일"] <= 45], key=lambda x: x["나이일"])
for r in recent[:14]:
    print(f"  {r['나이일']:3d}일  {r['경로']}")
print(f"  ... 총 {len(recent)}개")

with io.open(os.path.join(ROOT, "정리", "_전체스캔.csv"), "w",
             encoding="utf-8-sig", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
    w.writeheader(); w.writerows(sorted(rows, key=lambda x: (-x["참조수"], x["나이일"])))
print("\n→ 정리/_전체스캔.csv")
