#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
연구색인_생성.py — 진우퀀트 연구 갈래 자동 색인 (2026-08-04)

── 왜 만들었나 ─────────────────────────────────────────────────
연구 자료가 사라지는 경로는 '삭제'가 아니다. **잊히는 것**이다.
루트에 흩어진 실험 갈래 150여 개는 허브(강화키트 25개 고정목록)에도,
백서 부록 B-1 색인에도 한 줄이 없다. 결론이 안 났다는 이유로 목록에서
빠지면, 그 갈래는 존재 자체가 기억에서 지워진다.

이 스크립트는 **결론 여부와 무관하게** 모든 갈래를 색인한다.
  · 파일명 접두어로 갈래를 묶고 (날짜·버전 토큰 제거)
  · 갈래별 파일수 · 최종수정일 · 구성(소스/기록/산출물) 집계
  · 활성(7일) / 최근(30일) / 휴면 으로 상태 표시
  · 대표 기록(md)과 대표 산출물(html) 링크를 자동으로 건다

아무것도 옮기거나 지우지 않는다. 읽기만 한다.

사용:
    py 연구색인_생성.py                      # 강화키트\진우퀀트_연구색인.html
    py 연구색인_생성.py --out D:\색인.html
"""
import argparse, collections, datetime as dt, html, os, re, sys, time

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = os.path.join(HERE, "강화키트")

# 스캔에서 제외 — 임시·백업·대용량 원자료 (내용이 아니라 무게)
SKIP_DIRS = {
    ".git", ".github", "__pycache__", "__jqpyc__", ".vscode", ".idea",
    "_stage_tmp", "_stagetmp2", "_stagetmp3", "_백업", "_archive",
    "_to_delete", "_보관", "카드뉴스", "img",
}
SKIP_EXT = {".bak", ".pyc", ".db", ".pkl", ".lock", ".tmp", ".log"}
SRC_EXT = {".py", ".bat", ".ps1"}
DOC_EXT = {".md", ".txt"}

# 접두어가 너무 흔해서 갈래로 못 쓰는 것들 — 두 번째 토큰까지 본다
GENERIC = {
    "backtest", "audit", "fetch", "make", "build", "run", "verify", "check",
    "test", "patch", "trend", "signal", "track", "snapshot", "factor",
    "entry", "decision", "catalyst", "검정", "검증", "조사", "보고서", "일일",
}
DATE_RE = re.compile(r"(20\d{2}[-_]?\d{2}[-_]?\d{2}|20\d{6}|\d{4}-\d{2}-\d{2})")
VER_RE = re.compile(r"^(v\d+([._]\d+)*|phase\d+|final|latest|new|old|copy)$", re.I)


def cluster_key(basename: str) -> str:
    """파일명에서 날짜·버전을 걷어내고 갈래 이름을 뽑는다."""
    stem = re.sub(r"\.[^.]+$", "", basename).lstrip("_★●■◆ ")
    stem = DATE_RE.sub("", stem)
    toks = [t for t in re.split(r"[_\-. ]+", stem) if t and not VER_RE.match(t)]
    if not toks:
        return "(이름없음)"
    head = toks[0]
    if head.lower() in GENERIC and len(toks) > 1:
        return f"{head}_{toks[1]}"
    return head


def scan(root: str):
    out = []
    for cur, dirs, files in os.walk(root):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".")]
        depth = os.path.relpath(cur, root).count(os.sep)
        if depth > 2:
            dirs[:] = []
        for fn in files:
            ext = os.path.splitext(fn)[1].lower()
            if ext in SKIP_EXT or ".bak_" in fn or fn.startswith("~$"):
                continue
            if ext not in SRC_EXT | DOC_EXT | {".html", ".csv", ".png", ".json", ".xlsx"}:
                continue
            p = os.path.join(cur, fn)
            try:
                st = os.stat(p)
            except OSError:
                continue
            out.append((p, fn, ext, st.st_mtime, st.st_size))
    return out


def role_of(ext: str) -> str:
    if ext in SRC_EXT:
        return "소스"
    if ext in DOC_EXT:
        return "기록"
    return "산출물"


def collect(root: str):
    """갈래별 집계 행 목록을 돌려준다. 파일을 읽기만 한다."""
    now = time.time()
    items = scan(root)
    groups = collections.defaultdict(list)
    for p, fn, ext, mt, sz in items:
        groups[cluster_key(fn)].append((p, fn, ext, mt, sz))

    # 한 갈래가 25개를 넘으면 두 번째 토큰까지 써서 더 쪼갠다.
    # (진우퀀트_* 224개 같은 덩어리는 갈래로서 의미가 없다)
    for key in [k for k, v in groups.items() if len(v) > 25]:
        bucket = groups.pop(key)
        for f in bucket:
            stem = re.sub(r"\.[^.]+$", "", f[1]).lstrip("_★●■◆ ")
            stem = DATE_RE.sub("", stem)
            toks = [t for t in re.split(r"[_\-. ]+", stem) if t and not VER_RE.match(t)]
            sub = "%s_%s" % (key, toks[1]) if len(toks) > 1 else key
            groups[sub].append(f)

    rows, active = [], 0
    for key, fs in groups.items():
        newest = max(f[3] for f in fs)
        age = (now - newest) / 86400
        state = "활성" if age <= 7 else ("최근" if age <= 30 else "휴면")
        if state == "활성":
            active += 1
        cnt = collections.Counter(role_of(f[2]) for f in fs)
        docs = sorted([f for f in fs if f[2] in DOC_EXT], key=lambda x: -x[3])
        reps = sorted([f for f in fs if f[2] == ".html"], key=lambda x: -x[3])

        rows.append(dict(
            key=key, n=len(fs), src=cnt["소스"], doc=cnt["기록"], out=cnt["산출물"],
            newest=newest, state=state,
            size=sum(f[4] for f in fs),
            doc_f=docs[0] if docs else None,
            out_f=reps[0] if reps else None,
            files=" ".join(f[1].lower() for f in fs),
        ))
    rows.sort(key=lambda r: (-r["newest"], r["key"]))
    return rows, len(items)


def _link(f, outdir):
    if not f:
        return ""
    try:
        rel = os.path.relpath(f[0], outdir).replace("\\", "/")
    except ValueError:
        rel = f[0]
    return "<a href='%s'>%s</a>" % (html.escape(rel), html.escape(f[1]))


def rows_html(rows, outdir, cls_prefix=""):
    tr = []
    for r in rows:
        cls = cls_prefix + {"활성": "ac", "최근": "rc", "휴면": "dm"}[r["state"]]
        tr.append(
            "<tr data-s='%s' data-q='%s'><td><b>%s</b></td><td class=n>%d</td>"
            "<td class=n>%d</td><td class=n>%d</td><td class=n>%d</td>"
            "<td class=n>%s</td><td class='n %s'>%s</td><td>%s</td><td>%s</td></tr>" % (
                r["state"], html.escape(r["key"].lower() + " " + r["files"]),
                html.escape(r["key"]), r["n"], r["src"], r["doc"], r["out"],
                dt.datetime.fromtimestamp(r["newest"]).strftime("%Y-%m-%d"),
                cls, r["state"], _link(r["doc_f"], outdir), _link(r["out_f"], outdir)))
    return "\n".join(tr)


def section_html(root: str, outdir: str) -> str:
    """허브에 그대로 붙일 수 있는 자립형 <section> 조각.
    허브의 body_of() 는 style·script·class 를 전부 걷어내므로,
    이 조각은 body_of 를 거치지 않고 직접 삽입해야 한다."""
    rows, nfiles = collect(root)
    act = sum(1 for r in rows if r["state"] == "활성")
    dorm = sum(1 for r in rows if r["state"] == "휴면")
    return (
        '<section id="연구갈래색인" data-c="research"><h2>연구 갈래 색인</h2>'
        '<div class="age">자동 생성 · 갈래 %d · 파일 %d · 활성 %d · 휴면 %d</div>'
        '<div class="inner">%s'
        '<p style="color:#8b93a7;font-size:12.5px;margin:0 0 10px">'
        '결론이 난 갈래만 남기면 미완성 연구는 잊힌다. 상태와 무관하게 전부 올린다. '
        '<b>휴면</b>은 접었다는 뜻이 아니라 손을 놓은 지 30일이 넘었다는 뜻이다.</p>'
        '<div class="ri-bar">'
        '<button class="ri-fs ri-on" data-s="">전체</button>'
        '<button class="ri-fs" data-s="활성">활성</button>'
        '<button class="ri-fs" data-s="최근">최근</button>'
        '<button class="ri-fs" data-s="휴면">휴면</button>'
        '<input class="ri-q" placeholder="갈래·파일명 검색">'
        '<span class="ri-cnt"></span></div>'
        '<div class="ri-wrap"><table class="ri-t">'
        '<tr><th>갈래</th><th>파일</th><th>소스</th><th>기록</th><th>산출물</th>'
        '<th>최종수정</th><th>상태</th><th>대표 기록</th><th>대표 산출물</th></tr>'
        '%s</table></div>%s</div></section>'
    ) % (len(rows), nfiles, act, dorm, RI_CSS, rows_html(rows, outdir, "ri-"), RI_JS)


RI_CSS = """<style>
#연구갈래색인 .ri-bar{display:flex;gap:6px;flex-wrap:wrap;margin:10px 0;align-items:center}
#연구갈래색인 .ri-fs{background:#171a21;color:#e6e8ee;border:1px solid #262b36;
border-radius:999px;padding:4px 12px;font-size:12.5px;cursor:pointer}
#연구갈래색인 .ri-fs.ri-on{background:#6ea8fe;border-color:#6ea8fe;color:#0f1115;font-weight:600}
#연구갈래색인 .ri-q{background:#171a21;color:#e6e8ee;border:1px solid #262b36;
border-radius:8px;padding:5px 10px;font-size:12.5px;min-width:190px}
#연구갈래색인 .ri-cnt{color:#8b93a7;font-size:12px;margin-left:auto}
#연구갈래색인 .ri-wrap{max-height:62vh;overflow:auto;border:1px solid #262b36;border-radius:10px}
#연구갈래색인 .ri-t{width:100%;border-collapse:collapse;font-size:12.5px}
#연구갈래색인 .ri-t th,#연구갈래색인 .ri-t td{padding:6px 9px;border-bottom:1px solid #262b36;
text-align:left;white-space:nowrap}
#연구갈래색인 .ri-t th{position:sticky;top:0;background:#171a21;color:#8b93a7;font-size:11px}
#연구갈래색인 .ri-t td.n{text-align:right;font-variant-numeric:tabular-nums}
#연구갈래색인 .ri-ac{color:#7ec699;font-weight:600}
#연구갈래색인 .ri-rc{color:#f0a868}
#연구갈래색인 .ri-dm{color:#8b93a7}
</style>"""

RI_JS = """<script>(function(){
var root=document.getElementById('연구갈래색인'); if(!root) return;
var S="",Q="",rows=[].slice.call(root.querySelectorAll('.ri-t tr[data-s]'));
var cnt=root.querySelector('.ri-cnt');
function ap(){var n=0;rows.forEach(function(r){
 var ok=(!S||r.dataset.s===S)&&(!Q||r.dataset.q.indexOf(Q)>=0);
 r.style.display=ok?"":"none";if(ok)n++;});
 cnt.textContent=n+"갈래 표시";}
root.querySelectorAll('.ri-fs').forEach(function(b){b.onclick=function(){
 root.querySelectorAll('.ri-fs').forEach(function(x){x.classList.remove('ri-on')});
 b.classList.add('ri-on');S=b.dataset.s;ap();}});
root.querySelector('.ri-q').oninput=function(){Q=this.value.trim().toLowerCase();ap();};
ap();})();</script>"""


def build(root: str, outpath: str) -> str:
    rows, nfiles = collect(root)
    outdir = os.path.dirname(os.path.abspath(outpath))
    act = sum(1 for r in rows if r["state"] == "활성")
    doc = TPL.replace("__GEN__", dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
    doc = doc.replace("__NG__", str(len(rows))).replace("__NF__", str(nfiles))
    doc = doc.replace("__NA__", str(act)).replace("__ROWS__", rows_html(rows, outdir))
    os.makedirs(outdir, exist_ok=True)
    with open(outpath, "w", encoding="utf-8") as fh:
        fh.write(doc)
    return outpath


TPL = """<!DOCTYPE html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>진우퀀트 연구 색인</title><style>
:root{color-scheme:dark;--bg:#0f1115;--card:#171a21;--line:#262b36;--tx:#e6e8ee;
--dim:#8b93a7;--ac:#6ea8fe;--warn:#f0a868;--bad:#e06c75;--ok:#7ec699}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--tx);
font:14px/1.6 -apple-system,"Segoe UI","Malgun Gothic",sans-serif}
.w{max-width:1180px;margin:0 auto;padding:24px 20px 60px}
h1{margin:0 0 4px;font-size:20px}.sub{color:var(--dim);font-size:12.5px;margin:0 0 16px}
.box{background:var(--card);border:1px solid var(--line);border-radius:10px;
padding:12px 14px;margin:0 0 16px;font-size:13px;color:var(--dim)}
.bar{display:flex;gap:6px;flex-wrap:wrap;margin:12px 0;align-items:center}
.bar button{background:var(--card);color:var(--tx);border:1px solid var(--line);
border-radius:999px;padding:5px 13px;font-size:13px;cursor:pointer}
.bar button.on{background:var(--ac);border-color:var(--ac);color:#0f1115;font-weight:600}
.bar input{background:var(--card);color:var(--tx);border:1px solid var(--line);
border-radius:8px;padding:6px 10px;font-size:13px;min-width:200px}
.cnt{color:var(--dim);font-size:12.5px;margin-left:auto}
.wrap{max-height:74vh;overflow:auto;border:1px solid var(--line);border-radius:11px;background:var(--card)}
table{width:100%;border-collapse:collapse;font-size:12.5px}
th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--line);white-space:nowrap}
th{color:var(--dim);font-size:11px;font-weight:600;position:sticky;top:0;background:var(--card)}
td.n{text-align:right;font-variant-numeric:tabular-nums}
.ac{color:var(--ok);font-weight:600}.rc{color:var(--warn)}.dm{color:var(--dim)}
a{color:var(--ac);text-decoration:none}a:hover{text-decoration:underline}
</style></head><body><div class=w>
<h1>진우퀀트 연구 색인</h1>
<p class=sub>갈래 __NG__개 · 파일 __NF__개 · 활성(7일내) __NA__갈래 · 생성 __GEN__</p>
<div class=box>결론이 난 갈래만 남기면 미완성 연구는 잊힌다. 이 색인은 <b>상태와 무관하게 전부</b> 올린다.
휴면으로 내려간 갈래는 접은 게 아니라 <b>손을 놓은 지 30일이 넘었다</b>는 뜻이다.</div>
<div class=bar>
<button class="fs on" data-s="">전체</button>
<button class=fs data-s="활성">활성 (7일내)</button>
<button class=fs data-s="최근">최근 (30일내)</button>
<button class=fs data-s="휴면">휴면</button>
<input id=q placeholder="갈래·파일명 검색"><span class=cnt id=cnt></span></div>
<div class=wrap><table id=t>
<tr><th>갈래</th><th>파일</th><th>소스</th><th>기록</th><th>산출물</th><th>최종수정</th><th>상태</th><th>대표 기록</th><th>대표 산출물</th></tr>
__ROWS__
</table></div></div><script>
var S="",Q="";
var rows=[].slice.call(document.querySelectorAll("#t tr[data-s]"));
function ap(){var n=0;rows.forEach(function(r){
 var ok=(!S||r.dataset.s===S)&&(!Q||r.dataset.q.indexOf(Q)>=0);
 r.style.display=ok?"":"none";if(ok)n++;});
 document.getElementById("cnt").textContent=n+"갈래 표시";}
document.querySelectorAll(".fs").forEach(function(b){b.onclick=function(){
 document.querySelectorAll(".fs").forEach(function(x){x.classList.remove("on")});
 b.classList.add("on");S=b.dataset.s;ap();}});
document.getElementById("q").oninput=function(){Q=this.value.trim().toLowerCase();ap();};
ap();
</script></body></html>"""


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(KIT, "진우퀀트_연구색인.html"))
    ap.add_argument("--root", default=HERE)
    a = ap.parse_args()
    p = build(a.root, a.out)
    print("생성: %s" % p)


if __name__ == "__main__":
    main()
