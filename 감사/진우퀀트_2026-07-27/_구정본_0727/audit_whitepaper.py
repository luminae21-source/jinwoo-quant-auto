#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
audit_whitepaper.py — 폐기된 클레임이 본문에 무마킹으로 살아있는지 탐지

진단하는 결함: **append-only 문서 성장**
  새 발견을 부록에 덧붙이기만 하고 앞장의 원 주장을 수정하지 않으면,
  같은 문서가 앞에서는 A, 뒤에서는 not-A를 말하게 된다.
  앞부분만 읽는 독자(그리고 외부 감사자)는 폐기된 주장을 현행으로 읽는다.

방법:
  1. RETIRED에 등록된 '폐기·강등된 클레임 토큰'을 문서 전체에서 찾는다
  2. 각 출현 지점 ±WINDOW자 안에 정정 마커(강등/폐기/재현 실패/…)가 있는지 본다
  3. 마커가 없으면 🚨 무마킹 잔존 = 독자가 현행으로 오독할 지점
  4. 추가로 같은 지표의 서로 다른 값(값 충돌)을 탐지한다

사용:
  python audit_whitepaper.py 백서.html [--window 400] [--out 감사_백서.md]
"""
import argparse, re, sys
from pathlib import Path

WINDOW_DEFAULT = 400

# ── v3: 폐기 클레임을 하드코딩하지 않고 클레임 레지스트리에서 읽는다 ──────
# v2까지는 RETIRED를 코드에 박아, 판정이 바뀌면 감사기가 같이 낡았다.
# (실제로 "조건부 통과"가 복권됐는데 감사기가 계속 폐기로 취급하는 사고 발생)
# 이제 진실은 클레임_레지스트리.csv 한 곳에만 있다.
DEFAULT_REGISTRY = "클레임_레지스트리.csv"
RETIRED = {}   # load_registry()가 채운다


def load_registry(path):
    import csv, os
    if not os.path.exists(path):
        return {}, f"레지스트리 없음: {path}"
    out = {}
    with open(path, encoding="utf-8-sig") as f:
        for r in csv.DictReader(f):
            if r.get("status", "").strip() not in ("retired", "disputed", "superseded"):
                continue
            pat = (r.get("탐지패턴") or "").strip()
            if not pat:
                continue
            out[pat] = (f"{r['claim_id']} [{r['status']}] {r['claim']}",
                        (r.get("현행사실") or r.get("비고") or "").strip())
    return out, None


# 정정 마커 — 강/약 분리 (v2)
# v1은 "정정" 같은 범용어를 넣어, 무관한 정정이 진짜 문제를 가리는 위양성 통과가 났다.
# 폐기 클레임 옆에 있어야 인정되는 것은 '그 클레임이 죽었다'는 강한 선언뿐이다.
STRONG_MARKERS = ["🔶",  # 정정 전용 마커 — 이 글리프가 있으면 정정이 명시된 구간
                  "강등", "폐기", "재현 실패", "재현 안 됨", "재현되지", "해소",
                  "철회", "무효화", "기각", "확정 취소"]
WEAK_MARKERS = ["정정", "무효", "더 이상", "레거시", "역사적", "과거 주장", "구(舊)"]

# 값 충돌 탐지 — 같은 지표가 문서 내에서 다른 값을 갖는가
METRICS = {
    # v2: 지표명 직후(구분자 최대 4자) 숫자만 인정. '병목2' 류 오매치 차단.
    "PBO":        r"PBO\s*[:=(]?\s*(0\.\d{2,3}|\d{1,2}\.\d\s*%|\d{1,2}\s*%)",
    "DSR":        r"DSR\s*[:=(]?\s*(1\.000|0\.\d{2,3}|\d{1,2}\.\d\s*%|\d{1,2}\s*%)",
    "배당롱숏":    r"배당\s*[+＋]\s*(\d\.\d)\s*%",
    "BP롱숏":      r"B/P\s*[+＋]?\s*(\d\.\d)\s*%",
    "왕복비용":    r"왕복\s*[^\d]{0,4}(\d\.\d{1,2})\s*%",
}


def to_text(p: Path):
    raw = p.read_text(encoding="utf-8", errors="replace")
    if p.suffix.lower() in (".html", ".htm"):
        raw = re.sub(r"<script.*?</script>|<style.*?</style>", " ", raw, flags=re.S | re.I)
        raw = re.sub(r"<[^>]+>", " ", raw)
    return re.sub(r"\s+", " ", raw)


def nearest_header(text, pos, headers):
    """해당 위치 직전의 섹션 헤더를 찾아 어디서 터진 문제인지 알려준다"""
    prev = "(문서 앞부분)"
    for hpos, h in headers:
        if hpos <= pos:
            prev = h
        else:
            break
    return prev


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("path")
    ap.add_argument("--window", type=int, default=WINDOW_DEFAULT)
    ap.add_argument("--out", default="감사_백서.md")
    ap.add_argument("--registry", default=DEFAULT_REGISTRY)
    a = ap.parse_args()

    p = Path(a.path)
    if not p.exists():
        sys.exit(f"파일 없음: {p}")
    s = to_text(p)

    global RETIRED
    from pathlib import Path as _P
    reg_path = a.registry if _P(a.registry).exists() else str(_P(__file__).parent / DEFAULT_REGISTRY)
    RETIRED, err = load_registry(reg_path)
    if err or not RETIRED:
        sys.exit(f"레지스트리 로드 실패 — {err or '탐지패턴 있는 폐기 클레임 0건'}")

    raw = p.read_text(encoding="utf-8", errors="replace")
    headers = []
    for m in re.finditer(r"<h[1-4][^>]*>(.*?)</h[1-4]>", raw, flags=re.S):
        title = re.sub(r"<[^>]+>", "", m.group(1)).strip()[:50]
        idx = s.find(title[:20]) if len(title) > 20 else s.find(title)
        if idx >= 0:
            headers.append((idx, title))
    headers.sort()

    L = []
    def say(x=""):
        print(x); L.append(x)

    say(f"# 백서 무마킹 폐기클레임 감사\n\n대상 `{p.name}` · 본문 {len(s):,}자 · 창 ±{a.window}자\n레지스트리 `{_P(reg_path).name}` · 폐기/분쟁 클레임 {len(RETIRED)}건\n")

    total_orphan = 0
    say("## 1. 폐기 클레임의 무마킹 잔존\n")
    for pat, (desc, repl) in RETIRED.items():
        hits = list(re.finditer(pat, s))
        if not hits:
            continue
        orphans, weak, marked = [], [], 0
        for m in hits:
            lo, hi = max(0, m.start() - a.window), min(len(s), m.end() + a.window)
            ctx = s[lo:hi]
            if any(k in ctx for k in STRONG_MARKERS):
                marked += 1
            elif any(k in ctx for k in WEAK_MARKERS):
                weak.append(m)          # 약한 마커만 = 오독 위험 잔존
            else:
                orphans.append(m)
        total_orphan += len(orphans) + len(weak)
        icon = "✅" if not (orphans or weak) else "🚨"
        say(f"### {icon} `{pat}` — {desc}")
        say(f"출현 {len(hits)}회 · 강한정정 동반 {marked} · **약한정정만 {len(weak)}** · **무마킹 {len(orphans)}**")
        orphans = weak + orphans
        if orphans:
            say(f"\n> 현행 사실: {repl}\n")
            for m in orphans[:4]:
                sec = nearest_header(s, m.start(), headers)
                pct = round(m.start() / len(s) * 100)
                snip = s[max(0, m.start()-90):m.end()+90].strip()
                say(f"- **{sec}** (문서 {pct}%)")
                say(f"  > …{snip}…")
        say("")

    say("## 2. 값 충돌 (같은 지표, 다른 값)\n")
    conflicts = 0
    for name, pat in METRICS.items():
        vals = {}
        for m in re.finditer(pat, s):
            v = m.group(1)
            vals.setdefault(v, []).append(round(m.start() / len(s) * 100))
        if len(vals) > 1:
            conflicts += 1
            say(f"- 🚨 **{name}**: " + " · ".join(f"`{v}` (문서 {p_}%)" for v, p_ in
                                                 ((v, ",".join(map(str, ps))) for v, ps in vals.items())))
        elif vals:
            say(f"- ✅ {name}: {list(vals)[0]}")
    if not conflicts:
        say("\n값 충돌 없음.")

    say("\n## 3. 판정\n")
    if total_orphan:
        say(f"🚨 **무마킹 폐기클레임 {total_orphan}건 · 값 충돌 {conflicts}건**\n")
        say("이는 개별 오타가 아니라 **문서 성장 방식의 결함**이다:")
        say("새 발견을 부록에 덧붙이면서 앞장의 원 주장을 수정하지 않아,")
        say("같은 문서가 앞에서는 A, 뒤에서는 not-A를 말한다.\n")
        say("**구조적 처방 (§부록 참조):** 백서가 숫자를 하드코딩하지 말고")
        say("`기준값.json` 하나에서 렌더링하게 만들면 이 결함은 원천적으로 불가능해진다.")
        sys.exit(1)
    else:
        say("✅ 무마킹 폐기클레임 없음.")


if __name__ == "__main__":
    main()
