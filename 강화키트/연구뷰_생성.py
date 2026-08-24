# -*- coding: utf-8 -*-
r"""연구뷰_생성.py — 연구 문서(.md)를 허브에서 읽을 수 있는 .html 로 변환. (2026-08-20)

왜: 백서 1,900줄·런북 1,375줄을 브라우저에서 열면 날것 텍스트로 보인다.
    표도 인용도 안 보여서 사실상 못 읽는다. 허브에 링크해도 쓸모가 없다.
    → 허브와 같은 테마의 정적 HTML 로 미리 변환해 둔다. (file:// 에서 fetch 는 CORS 로 막히므로
      클라이언트 렌더가 아니라 **생성 시점 변환**이 정답이다.)

무엇: 아래 문서를 강화키트\연구_*.html 로 만든다. jq_hub.py 가 그걸 링크한다.

    py 강화키트\연구뷰_생성.py
    py 강화키트\연구뷰_생성.py --selftest
"""
import os, re, io, sys, html, argparse, datetime

BASE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BASE)

DOCS = [   # (출력파일, 원본 상대경로, 제목)
    ("연구_현황.html",   ["백서_빌더", "현재상태_한장.md"],        "현재 상태 한 장"),
    ("연구_무기목록.html", ["정리", "질문무기_대장.md"],             "질문·무기 대장"),
    ("연구_백서.html",   ["백서_빌더", "진우퀀트_백서.md"],        "진우퀀트 백서"),
    ("연구_런북.html",   ["데이터수리", "수정주가_재수집_런북.md"], "수정주가 런북"),
    ("연구_리빌딩.html", ["리빌딩_v5_마스터플랜.md"],              "v5 리빌딩 마스터플랜"),
    ("연구_재조명.html", ["진우퀀트_재조명_리포트_2026-07-28.md"], "재조명 리포트"),
    ("연구_인수인계.html", ["진우퀀트_휩쏘_인수인계.md"],           "휩쏘 인수인계 3판"),
    ("연구_프로토콜.html", ["정리", "분석_프로토콜.md"],            "Claude 분석 프로토콜"),
]


# ────────────────────────────────────────────── 마크다운 → HTML
def inline(s):
    s = html.escape(s)
    s = re.sub(r"`([^`]+)`", r"<code>\1</code>", s)
    s = re.sub(r"\*\*([^*]+)\*\*", r"<b>\1</b>", s)
    s = re.sub(r"(^|[^*])\*([^*\n]+)\*", r"\1<i>\2</i>", s)
    s = re.sub(r"~~([^~]+)~~", r"<del>\1</del>", s)
    s = re.sub(r"\[([^\]]*)\]\(([^)\s]+)\)", r'<a href="\2">\1</a>', s)
    return s


def md2html(md):
    """표·제목·인용·코드블록·목록을 다룬다. 백서/런북이 쓰는 문법 전부."""
    cb = []
    md = re.sub(r"```([\s\S]*?)```",
                lambda m: "@@CB%d@@" % (cb.append(re.sub(r"^[\w+-]*\n", "", m.group(1))) or len(cb) - 1),
                md)
    L, out, i = md.split("\n"), [], 0
    toc = []
    islist = lambda s: re.match(r"^\s*([-*+]|\d+\.)\s+", s)
    while i < len(L):
        ln = L[i]
        # 표 (GFM)
        if re.match(r"^\s*\|", ln) and i + 1 < len(L) and re.match(r"^\s*\|[\s:|-]+\|\s*$", L[i + 1]):
            cel = lambda r: [c.strip() for c in r.strip().strip("|").split("|")]
            h = "<table><thead><tr>" + "".join("<th>%s</th>" % inline(c) for c in cel(ln)) + "</tr></thead><tbody>"
            i += 2
            while i < len(L) and re.match(r"^\s*\|", L[i]):
                h += "<tr>" + "".join("<td>%s</td>" % inline(c) for c in cel(L[i])) + "</tr>"
                i += 1
            out.append(h + "</tbody></table>")
            continue
        m = re.match(r"^(#{1,6})\s+(.*)$", ln)
        if m:
            n, t = len(m.group(1)), m.group(2).strip()
            aid = "s%d" % len(toc)
            if n <= 4:
                toc.append((n, t, aid))
            out.append('<h%d id="%s">%s</h%d>' % (n, aid, inline(t), n))
            i += 1; continue
        if re.match(r"^\s*(-{3,}|\*{3,})\s*$", ln):
            out.append("<hr>"); i += 1; continue
        if re.match(r"^\s*>", ln):
            b = []
            while i < len(L) and re.match(r"^\s*>", L[i]):
                b.append(re.sub(r"^\s*>\s?", "", L[i])); i += 1
            out.append("<blockquote>%s</blockquote>" % md2html("\n".join(b))[0])
            continue
        if islist(ln):
            ordered = bool(re.match(r"^\s*\d+\.", ln)); b = []
            while i < len(L) and islist(L[i]):
                b.append(re.sub(r"^\s*([-*+]|\d+\.)\s+", "", L[i])); i += 1
            tag = "ol" if ordered else "ul"
            out.append("<%s>%s</%s>" % (tag, "".join("<li>%s</li>" % inline(x) for x in b), tag))
            continue
        if not ln.strip():
            i += 1; continue
        b = []
        while (i < len(L) and L[i].strip() and not re.match(r"^\s*[|>#]", L[i])
               and not islist(L[i]) and not re.match(r"^\s*-{3,}\s*$", L[i])):
            b.append(L[i]); i += 1
        out.append("<p>%s</p>" % inline("\n".join(b)))
    h = "\n".join(out)
    h = re.sub(r"@@CB(\d+)@@", lambda m: "<pre><code>%s</code></pre>" % html.escape(cb[int(m.group(1))]), h)
    h = re.sub(r"<p>(\s*<pre>[\s\S]*?</pre>\s*)</p>", r"\1", h)
    return h, toc


PAGE = """<!doctype html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>%(title)s · 진우퀀트</title><style>
:root{--bg:#0b1020;--card:#141b2e;--ink:#e8edf6;--sub:#9fb0c9;--line:#243149;--acc:#5b9dff;--th:#1b2540}
@media(prefers-color-scheme:light){:root{--bg:#f4f6fb;--card:#fff;--ink:#0f1830;--sub:#5a6a86;--line:#e3e9f4;--acc:#2563eb;--th:#eef2fa}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);
font-family:-apple-system,'Segoe UI',Roboto,'Malgun Gothic',sans-serif;padding:22px;line-height:1.65;font-size:14.5px}
.wrap{max-width:1000px;margin:0 auto}
.bar{display:flex;gap:12px;align-items:baseline;flex-wrap:wrap;margin-bottom:6px}
h1.pt{font-size:21px;margin:0}
.meta{color:var(--sub);font-size:11.5px;margin-bottom:16px}
a.back{color:var(--acc);text-decoration:none;font-size:12.5px}
.toc{background:var(--card);border:1px solid var(--line);border-radius:12px;padding:13px 16px;margin-bottom:16px;font-size:12.5px}
.toc a{display:block;color:var(--sub);text-decoration:none;padding:2px 0}
.toc a:hover{color:var(--acc)}.toc a.d2{padding-left:14px}.toc a.d3{padding-left:28px}.toc a.d4{padding-left:42px}
.doc{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:26px 30px}
.doc>*:first-child{margin-top:0}
.doc h1{font-size:20px;margin:8px 0 14px;padding-bottom:9px;border-bottom:2px solid var(--line)}
.doc h2{font-size:17px;margin:28px 0 10px;color:var(--acc)}
.doc h3{font-size:15.5px;margin:24px 0 8px}
.doc h4{font-size:14.5px;margin:22px 0 8px}
.doc h5{font-size:13.5px;margin:18px 0 6px;color:var(--sub)}
.doc p{margin:9px 0}.doc ul,.doc ol{margin:9px 0;padding-left:22px}.doc li{margin:3px 0}
.doc table{border-collapse:collapse;margin:14px 0;font-size:13px;width:auto;min-width:55%%}
.doc th{background:var(--th);border:1px solid var(--line);padding:7px 11px;text-align:left;white-space:nowrap}
.doc td{border:1px solid var(--line);padding:6px 11px;vertical-align:top}
.doc blockquote{margin:12px 0;padding:10px 16px;background:var(--bg);border-left:4px solid var(--acc);border-radius:0 8px 8px 0}
.doc blockquote p{margin:5px 0}
.doc code{background:var(--th);padding:1.5px 5px;border-radius:4px;font:12.5px ui-monospace,Consolas,monospace}
.doc pre{background:#0d1117;color:#e6edf3;border-radius:9px;padding:13px 15px;overflow-x:auto}
.doc pre code{background:none;color:inherit;padding:0;font-size:12.3px}
.doc hr{border:0;border-top:1px solid var(--line);margin:24px 0}
.doc a{color:var(--acc)}.doc del{color:var(--sub)}
.warn{color:#e0a32e;font-size:11px;margin-top:16px}
</style></head><body><div class=wrap>
<div class=bar><h1 class=pt>%(title)s</h1><a class=back href="진우퀀트_허브.html">← 허브</a></div>
<div class=meta>원본 %(src)s · %(lines)s줄 · 생성 %(when)s · <b>원본이 정본이다. 이 페이지는 읽기용 사본.</b></div>
%(toc)s
<div class=doc>%(body)s</div>
<div class=warn>⚠️ 정보·검증용. 투자자문 아님 · 최종 판단과 책임은 본인.</div>
</div></body></html>"""


def build(quiet=False):
    made = []
    when = datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    for outname, rel, title in DOCS:
        src = os.path.join(ROOT, *rel)
        if not os.path.exists(src):
            if not quiet: print("  - 없음   %s" % os.path.join(*rel))
            continue
        md = io.open(src, encoding="utf-8", errors="replace").read()
        body, toc = md2html(md)
        t = ""
        if len(toc) >= 4:
            t = "<div class=toc>" + "".join(
                '<a class="d%d" href="#%s">%s</a>' % (n, a, html.escape(x)) for n, x, a in toc) + "</div>"
        page = PAGE % dict(title=html.escape(title), src=html.escape("/".join(rel)),
                           lines="{:,}".format(len(md.splitlines())), when=when, toc=t, body=body)
        io.open(os.path.join(BASE, outname), "w", encoding="utf-8").write(page)
        made.append((outname, len(md.splitlines()), len(toc)))
        if not quiet:
            print("  ✓ %-20s %6s줄 · 목차 %d" % (outname, "{:,}".format(len(md.splitlines())), len(toc)))
    return made


def selftest():
    ok = []
    def t(n, c): ok.append((n, bool(c)))
    b, _ = md2html("# 제목\n\n본문이다.")
    t("1 제목", '<h1 id="s0">제목</h1>' in b)
    t("2 본문", "<p>본문이다.</p>" in b)
    b, _ = md2html("| A | B |\n|---|---|\n| 1 | 2 |")
    t("3 표 헤더", "<th>A</th>" in b and "<th>B</th>" in b)
    t("4 표 셀", "<td>1</td>" in b and "<td>2</td>" in b)
    b, _ = md2html("> 인용문")
    t("5 인용", "<blockquote>" in b and "인용문" in b)
    b, _ = md2html("- 하나\n- 둘")
    t("6 목록", b.count("<li>") == 2)
    b, _ = md2html("```\ncode here\n```")
    t("7 코드블록", "<pre><code>" in b and "code here" in b)
    t("8 코드블록 p 미포함", "<p><pre>" not in b)
    b, _ = md2html("**굵게** 와 `코드`")
    t("9 강조", "<b>굵게</b>" in b and "<code>코드</code>" in b)
    b, _ = md2html("<script>alert(1)</script>")
    t("10 XSS 이스케이프", "<script>" not in b and "&lt;script&gt;" in b)
    _, toc = md2html("# A\n## B\n### C\n##### E")
    t("11 목차 4단계까지", len(toc) == 3)
    b, _ = md2html("---")
    t("12 구분선", "<hr>" in b)
    n = sum(1 for _, c in ok if c)
    for name, c in ok: print(("  ✓ " if c else "  ✗ ") + name)
    print("자가검사 %d/%d %s" % (n, len(ok), "PASS" if n == len(ok) else "FAIL"))
    return 0 if n == len(ok) else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest: sys.exit(selftest())
    print("연구뷰 생성")
    m = build()
    print("→ %d개 · 강화키트\\연구_*.html" % len(m))
