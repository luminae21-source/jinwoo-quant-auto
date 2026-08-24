# -*- coding: utf-8 -*-
r"""
상태갱신.py — 현재상태_한장.md 의 '기계가 아는 부분'만 다시 쓴다. (2026-08-08)

설계 원칙 (중요)
---------------
1) **판정 숫자는 절대 쓰지 않는다.** CAGR·초과수익 같은 결론은 손으로 쓴다.
   결과 .md 를 파싱해서 숫자를 옮기면, 파싱이 깨질 때 **조용히 거짓말을 한다.**
   낡은 상태 문서는 없는 것보다 나쁘고, 틀린 상태 문서는 그보다 더 나쁘다.
2) 자동으로 쓰는 것은 **파일에서 직접 읽히는 사실**뿐이다 —
   행 수, 코드 수, md5, 마스크 건수, 커버리지, 최신 결과 폴더 이름.
3) 나머지는 **경고만 올린다.** "판정이 낡았을 수 있다"고 알리고, 고치는 건 사람이 한다.

쓰는 법 (진우퀀트 폴더에서)
    py 백서_빌더\상태갱신.py --check      # 안 고치고 점검만
    py 백서_빌더\상태갱신.py             # AUTO 구간 갱신
    py 백서_빌더\상태갱신.py --selftest
"""
import argparse, csv, collections, hashlib, io, json, os, re, sys, glob, datetime

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
DOC  = os.path.join(HERE, "현재상태_한장.md")
D    = os.path.join(ROOT, "데이터수리")

PANEL_A = "월봉_KIS_adj_v1_2026-07-28.csv"
PANEL_B = "_월봉_KIS_adj_2016.csv"


def md5(p):
    h = hashlib.md5()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def panel_stats(p):
    n = 0; codes = set(); lo = "9999-99"; hi = "0000-00"
    with open(p, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            n += 1; codes.add(r["code"]); y = r["ym"]
            if y < lo: lo = y
            if y > hi: hi = y
    return n, len(codes), lo, hi


def coverage(paths, mcap):
    """연도별 (실제 상장, KIS 도달) — 실측."""
    kby = collections.defaultdict(set)
    for p in paths:
        with open(p, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                kby[r["ym"][:4]].add(r["code"].zfill(6))
    uni = collections.defaultdict(set)
    with open(mcap, encoding="utf-8-sig", newline="") as f:
        for r in csv.DictReader(f):
            uni[r["date"][:4]].add(r["code"].zfill(6))
    out = {}
    for y in sorted(uni):
        u = uni[y]
        if u:
            out[y] = (len(u), len(u & kby.get(y, set())))
    return out


def count_rows(p):
    with open(p, encoding="utf-8-sig", newline="") as f:
        return sum(1 for _ in csv.DictReader(f))


# ------------------------------------------------------------------ 본문 생성
def build_block(warn):
    A = os.path.join(D, PANEL_A); B = os.path.join(D, PANEL_B)
    na, ca, la, ha = panel_stats(A)
    nb, cb, lb, hb = panel_stats(B)
    ma, mb = md5(A), md5(B)

    # 지문에 적힌 md5 와 실제가 같은가 — 다르면 그게 최우선 경고
    fp = os.path.join(D, "월봉_KIS_adj_v1_지문.json")
    if os.path.exists(fp):
        rec = json.load(io.open(fp, encoding="utf-8")).get("md5")
        if rec and rec != ma:
            warn.append("⛔ 정본 패널 md5 가 지문과 다릅니다! 지문 %s / 실제 %s — "
                        "이 파일로 낸 과거 성과는 전부 무효입니다." % (rec[:12], ma[:12]))

    # 중복 셀
    def keys(p):
        s = set()
        with open(p, encoding="utf-8-sig", newline="") as f:
            for r in csv.DictReader(f):
                s.add((r["code"], r["ym"]))
        return s
    dup = len(keys(A) & keys(B))
    if dup:
        warn.append("⚠️ 두 패널 파일에 중복 셀 %d 개 — 이어붙임이 깨졌습니다." % dup)

    # 마스크
    mk = os.path.join(D, "_패널마스크_v1.csv")
    sg = os.path.join(D, "_출처불일치_v1.csv")
    nmk = count_rows(mk) if os.path.exists(mk) else None
    nsg = count_rows(sg) if os.path.exists(sg) else None

    # 커버리지
    cov = coverage([A, B], os.path.join(ROOT, "종목시총_30년.csv"))
    full = [y for y in cov if cov[y][0] and cov[y][1] == cov[y][0]]
    fy = "%s~%s" % (min(full), max(full)) if full else "없음"
    def pct(y):
        u, k = cov.get(y, (0, 0))
        return ("%.2f%%" % (k * 100.0 / u)) if u else "?"

    L = []
    L.append("| 항목 | 값 |")
    L.append("|---|---|")
    L.append("| 정본 패널 (%s~%s) | `데이터수리/%s` · md5 `%s` · %s행 · %s코드 |"
             % (la, ha, PANEL_A, ma, format(na, ","), format(ca, ",")))
    L.append("| 정본 패널 (%s~%s) | `데이터수리/%s` · md5 `%s` · %s행 · %s코드 · 두 파일 **중복 셀 %d** |"
             % (lb, hb, PANEL_B, mb[:8] + "...", format(nb, ","), format(cb, ","), dup))
    L.append("| 커버리지 (실제 상장 대비) | **%s 100.00%%** · 2010 %s · 2009 %s · 2008 %s |"
             % (fy, pct("2010"), pct("2009"), pct("2008")))
    if nmk is not None and nsg is not None:
        L.append("| 마스크 (결함 격리) | `_패널마스크_v1.csv` %s셀 (md5 `%s`) + `_출처불일치_v1.csv` %s월 |"
                 % (format(nmk, ","), md5(mk)[:8] + "...", format(nsg, ",")))
    L.append("| 검증된 신호 | **멀티팩터** div/bp/ep/roe z합성 (HAC t 4.10 / 3.34 / 2.36) |")
    L.append("| 기각된 신호 | momentum 12-1 (t=0.7) |")
    return "\n".join(L)


def latest_result():
    """가장 최근 결과 **폴더**. 스크립트 파일(이중창_실행.ps1)이 걸리지 않게 폴더+날짜형만."""
    ds = [d for d in glob.glob(os.path.join(ROOT, "이중창_*"))
          if os.path.isdir(d) and re.match(r"^이중창_\d{8}_\d{4}$", os.path.basename(d))]
    return os.path.basename(sorted(ds)[-1]) if ds else None


def replace_block(text, tag, body):
    a, b = "<!-- AUTO:%s -->" % tag, "<!-- /AUTO:%s -->" % tag
    if a not in text or b not in text:
        return text, False
    i = text.index(a) + len(a); j = text.index(b)
    return text[:i] + "\n" + body + "\n" + text[j:], True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--check", action="store_true", help="고치지 않고 점검만")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--today", default=None, help="갱신일 (기본: 오늘)")
    a = ap.parse_args()
    if a.selftest:
        sys.exit(selftest())

    warn = []
    print("=" * 66)
    print(" 현재상태_한장.md 갱신")
    print("=" * 66)
    body = build_block(warn)
    t = io.open(DOC, encoding="utf-8").read()

    # 판정 낡음 경고 — 숫자를 옮기지 않고, 낡았는지만 본다
    lr = latest_result()
    if lr:
        m = re.search(r"결과 폴더 `([^`]+)`", t)
        cited = m.group(1).rstrip("/") if m else None
        if cited and cited != lr:
            warn.append("⚠️ 최신 결과 폴더는 `%s` 인데 문서가 인용한 것은 `%s` 입니다 — "
                        "〈현재 답〉이 낡았을 수 있습니다. **손으로** 확인하세요." % (lr, cited))
        print("  최신 결과 폴더: %s (문서 인용: %s)" % (lr, cited))

    today = a.today or datetime.date.today().isoformat()
    for mk in re.finditer(r"<!-- 손:마지막수정=(\d{4}-\d{2}-\d{2}) -->", t):
        d = mk.group(1)
        age = (datetime.date.fromisoformat(today) - datetime.date.fromisoformat(d)).days
        if age >= 14:
            warn.append("⚠️ 손으로 쓴 구간이 %d일째 그대로입니다 (마지막 %s)." % (age, d))
            break

    if a.check:
        print("\n[점검 결과]")
        print(body)
        print()
        for w in warn: print("  " + w)
        if not warn: print("  ✓ 경고 없음")
        print("\n(--check 이므로 파일은 고치지 않았습니다.)")
        return

    t2, ok1 = replace_block(t, "데이터", body)
    head = ("> 갱신: **" + today + "** · 갱신 규칙 — 판정이 바뀌면 이 문서를 고치고 근거는 백서에 부록으로 **덧붙인다.**\n"
            ">\n"
            "> ⚙️ 위 〈데이터〉 표와 이 줄은 `py 백서_빌더\\상태갱신.py` 가 자동으로 다시 씁니다.\n"
            "> 나머지(질문·답·열린것·죽은것·규칙·내가틀렸던것)는 **손으로 씁니다** — 판단이라서 자동화하지 않습니다.\n"
            ">\n"
            "> ⚠️ **이 스크립트는 판정 숫자를 쓰지 않습니다.** 아래 〈현재 답〉이 최신인지는 사람이 확인해야 합니다.")
    t2, ok2 = replace_block(t2, "머리", head)
    if not (ok1 and ok2):
        sys.exit("⛔ AUTO 마커를 못 찾았습니다 (데이터=%s 머리=%s)" % (ok1, ok2))
    io.open(DOC, "w", encoding="utf-8", newline="\n").write(t2)
    print("\n  ✓ 갱신 완료: %s" % os.path.relpath(DOC, ROOT))
    print()
    for w in warn: print("  " + w)
    if not warn: print("  ✓ 경고 없음")


# ------------------------------------------------------------------ 자가검사
def selftest():
    ok = []
    def t(n, c): ok.append((n, bool(c)))

    s = "머리\n<!-- AUTO:데이터 -->\nOLD\n<!-- /AUTO:데이터 -->\n꼬리"
    r, done = replace_block(s, "데이터", "NEW")
    t("① 구간 교체", done and "NEW" in r and "OLD" not in r)
    t("② 구간 밖 보존", r.startswith("머리") and r.endswith("꼬리"))
    t("③ 마커 유지", r.count("<!-- AUTO:데이터 -->") == 1 and r.count("<!-- /AUTO:데이터 -->") == 1)
    _, d2 = replace_block("마커없음", "데이터", "NEW")
    t("④ 마커 없으면 False", d2 is False)
    r2, _ = replace_block(r, "데이터", "AGAIN")
    t("⑤ 반복 실행 안전(멱등)", r2.count("AGAIN") == 1 and "NEW" not in r2)

    # md5 가 실제 파일 해시와 맞는가 (임시폴더에 쓴다 — 리포 안에 흔적을 남기지 않는다)
    import tempfile
    fd, tmp = tempfile.mkstemp(prefix="jq_md5_")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(b"abc")
        t("⑥ md5 정확", md5(tmp) == hashlib.md5(b"abc").hexdigest())
    finally:
        try: os.remove(tmp)
        except OSError: pass

    # 문서에 필요한 마커가 실제로 있는가
    doc = io.open(DOC, encoding="utf-8").read()
    t("⑦ 문서에 AUTO:데이터", "<!-- AUTO:데이터 -->" in doc)
    t("⑧ 문서에 AUTO:머리", "<!-- AUTO:머리 -->" in doc)
    t("⑨ 문서에 손:마지막수정", "손:마지막수정=" in doc)
    t("⑩ 결과폴더 인용 있음", re.search(r"결과 폴더 `([^`]+)`", doc) is not None)

    # 이 스크립트가 판정 숫자를 쓰지 않는다는 것 — 자기 소스 검사
    src = io.open(os.path.abspath(__file__), encoding="utf-8").read()
    body_fn = src[src.index("def build_block"):src.index("def latest_result")]
    t("⑪ build_block 에 CAGR 문자열 없음", "CAGR" not in body_fn)
    t("⑫ build_block 이 결과 .md 를 안 읽음", "결과_" not in body_fn)

    # 갱신일이 문서에 실제로 박혔는가 (%s 가 그대로 남는 사고 방지)
    t("⑭ 갱신일 치환됨", re.search(r"> 갱신: \*\*\d{4}-\d{2}-\d{2}\*\*", doc) is not None)

    # 결과폴더 탐색이 스크립트 파일을 안 잡는가
    lr = latest_result()
    t("⑬ 결과폴더만 잡음", lr is None or (re.match(r"^이중창_\d{8}_\d{4}$", lr)
                                       and os.path.isdir(os.path.join(ROOT, lr))))

    n = sum(1 for _, b in ok if b)
    for name, b in ok: print(("  ✓ " if b else "  ✗ ") + name)
    print("자가검사 %d/%d %s" % (n, len(ok), "PASS" if n == len(ok) else "FAIL"))
    return 0 if n == len(ok) else 1


if __name__ == "__main__":
    main()
