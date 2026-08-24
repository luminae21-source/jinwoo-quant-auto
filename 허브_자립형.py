#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""
허브_자립형.py — 어디서 열어도 깨지지 않는 진우퀀트 허브

── 왜 만들었나 (2026-07-27) ────────────────────────────────────────
기존 `jq_hub.py` 는 정상 동작한다. 링크 35개, 깨짐 0 — **단 `강화키트\` 폴더 안에서만.**
링크가 전부 `추천대시보드.html` 같은 **상대 경로**라서, 허브 파일 하나만 다른 데로 옮기거나
누구에게 보내면 **35개가 전부 죽는다.** 형제 파일이 옆에 없기 때문이다.

이 스크립트는 링크 대신 **내용을 통째로 넣는다.** 결과물 하나만 있으면 어디서든 열린다.

  · 각 리포트의 `<body>` 를 추출해 `<section>` 으로 인라인
  · 상단 탭으로 카테고리 이동 (daily / verify / doc)
  · CSS·JS 전부 인라인 · 외부 요청 0 · 이미지 있으면 data URI로 매립
  · 원본 갱신일을 각 섹션에 표시 — **낡은 리포트를 낡았다고 보이게**

사용:
    py 허브_자립형.py                      # 강화키트\진우퀀트_허브_자립형.html
    py 허브_자립형.py --out D:\보낼것.html
    py 허브_자립형.py --max-mb 8           # 용량 상한(초과분은 링크로 강등)

⚠️ 정보·검증용 · 투자자문 아님 · 책임 본인
"""
import argparse
import base64
import datetime as dt
import html
import os
import re
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
KIT = HERE if os.path.basename(HERE) == "강화키트" else os.path.join(HERE, "강화키트")

CATS = [("daily", "매일 보는 것"), ("verify", "검증·백테"),
        ("doc", "문서·지도"), ("research", "연구 색인")]

CURATED = [
    ("추천대시보드.html", "오늘의 추천 종목", "daily"),
    ("risk_manager.html", "집행 시트(손절·비중)", "daily"),
    ("entry_screener.html", "진입 스크리너(A/B등급)", "daily"),
    ("style_screener.html", "두 갈래 스크리너", "daily"),
    ("종합스캔_현재.html", "종합 스캔", "daily"),
    ("반등신호_현재.html", "반등 신호", "daily"),
    ("트레이딩구간_현재.html", "트레이딩 구간", "daily"),
    ("성장관심주.html", "성장 관심주", "daily"),
    ("factor_efficacy.html", "팩터 효력 검정", "verify"),
    ("style_conditional_factor.html", "스타일별 조건부 팩터", "verify"),
    ("entry_timing_test.html", "진입 타이밍 검정", "verify"),
    ("exit_routing_backtest.html", "매도 라우팅 백테", "verify"),
    ("ev_fcf_factor_test.html", "EV/FCF 팩터 검정", "verify"),
    ("multifactor_screen.html", "멀티팩터 스크리너", "verify"),
    ("배당_인과검정.html", "배당 인과 검정", "verify"),
    ("밸류축_확정.html", "밸류축 확정", "verify"),
    ("유니버스_규칙화_판정.html", "유니버스 규칙화 판정", "verify"),
    ("손절폭_스윕.html", "손절폭 스윕", "verify"),
    ("가중개편_백테.html", "가중 개편 백테", "verify"),
    ("해외상관.html", "한국↔미국·홍콩 상관", "verify"),
    ("진우퀀트_빠른사용법.html", "빠른 사용법", "doc"),
    ("진우퀀트_시스템요약.html", "시스템 종합 요약", "doc"),
    ("진우퀀트_검증패키지.html", "검증 패키지", "doc"),
    ("셀프테스트_현황.html", "셀프테스트 현황", "doc"),
    ("개발스레드_지도.html", "개발 스레드 지도", "doc"),
]

CSS = """
:root{--bg:#0f1115;--card:#171a21;--line:#262b36;--tx:#e6e8ee;--dim:#8b93a7;
--ac:#6ea8fe;--warn:#f0a868;--bad:#e06c75;--ok:#7ec699}
*{box-sizing:border-box}
body{margin:0;background:var(--bg);color:var(--tx);
font:15px/1.65 -apple-system,"Segoe UI","Malgun Gothic",sans-serif}
header{position:sticky;top:0;z-index:9;background:rgba(15,17,21,.96);
border-bottom:1px solid var(--line);padding:14px 20px;backdrop-filter:blur(8px)}
h1{margin:0 0 4px;font-size:19px;letter-spacing:-.2px}
.meta{color:var(--dim);font-size:12.5px}
nav{display:flex;gap:6px;flex-wrap:wrap;margin-top:11px}
nav button{background:var(--card);color:var(--tx);border:1px solid var(--line);
border-radius:999px;padding:6px 14px;font-size:13px;cursor:pointer}
nav button.on{background:var(--ac);border-color:var(--ac);color:#0f1115;font-weight:600}
main{padding:18px 20px 60px;max-width:1180px;margin:0 auto}
.toc{display:grid;grid-template-columns:repeat(auto-fill,minmax(215px,1fr));gap:8px;margin-bottom:22px}
.toc a{display:block;background:var(--card);border:1px solid var(--line);border-radius:9px;
padding:9px 12px;color:var(--tx);text-decoration:none;font-size:13.5px}
.toc a:hover{border-color:var(--ac)}
.toc .d{color:var(--dim);font-size:11.5px;margin-top:2px}
section{background:var(--card);border:1px solid var(--line);border-radius:12px;
padding:16px 18px;margin:0 0 16px}
section>h2{margin:0 0 3px;font-size:16.5px}
section .age{color:var(--dim);font-size:12px;margin-bottom:12px}
section .age.stale{color:var(--warn)}
section .age.old{color:var(--bad)}
.inner{overflow-x:auto}
.inner table{border-collapse:collapse;width:100%;font-size:13px}
.inner th,.inner td{border:1px solid var(--line);padding:5px 8px;text-align:left}
.inner th{background:#1e222b}
.inner h1,.inner h2,.inner h3{font-size:14.5px;margin:14px 0 6px}
.inner img{max-width:100%;height:auto;border-radius:6px}
.miss{color:var(--dim);font-style:italic}
footer{color:var(--dim);font-size:12px;padding:22px 20px;border-top:1px solid var(--line)}
.warn{background:#2a2118;border:1px solid #5a4326;border-radius:9px;
padding:11px 14px;margin:0 0 18px;font-size:13.5px;color:#f4d9b0}
"""

JS = """
function show(c){
  document.querySelectorAll('nav button').forEach(b=>b.classList.toggle('on',b.dataset.c===c));
  document.querySelectorAll('section').forEach(s=>{
    s.style.display = (c==='all'||s.dataset.c===c)?'':'none';});
  document.querySelectorAll('.toc a').forEach(a=>{
    a.style.display = (c==='all'||a.dataset.c===c)?'':'none';});
}
show('daily');
"""


def body_of(path):
    raw = open(path, encoding="utf-8", errors="replace").read()
    m = re.search(r"<body[^>]*>(.*)</body>", raw, re.S | re.I)
    inner = m.group(1) if m else raw
    inner = re.sub(r"<script.*?</script>", "", inner, flags=re.S | re.I)
    inner = re.sub(r"<style.*?</style>", "", inner, flags=re.S | re.I)
    inner = re.sub(r'\s(?:id|class)="[^"]*"', "", inner)
    # 이미지 매립
    def emb(mo):
        src = mo.group(1)
        if src.startswith(("data:", "http")):
            return mo.group(0)
        p = os.path.join(os.path.dirname(path), src)
        if os.path.exists(p) and os.path.getsize(p) < 1_500_000:
            ext = os.path.splitext(p)[1].lstrip(".").lower() or "png"
            b64 = base64.b64encode(open(p, "rb").read()).decode()
            return f'<img src="data:image/{ext};base64,{b64}"'
        return '<img alt="(이미지 없음)"'
    inner = re.sub(r'<img\s+src="([^"]+)"', emb, inner)
    return inner


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.join(KIT, "진우퀀트_허브_자립형.html"))
    ap.add_argument("--max-mb", type=float, default=12.0)
    a = ap.parse_args()

    now = dt.datetime.now()
    parts, toc, found, missing, stale = [], [], 0, [], 0
    budget = a.max_mb * 1024 * 1024
    used = 0

    for fn, label, cat in CURATED:
        p = os.path.join(KIT, fn)
        anchor = re.sub(r"[^0-9A-Za-z가-힣]", "", fn.replace(".html", ""))
        if not os.path.exists(p):
            missing.append(fn)
            continue
        found += 1
        age_d = (now - dt.datetime.fromtimestamp(os.path.getmtime(p))).days
        cls = "old" if age_d >= 14 else ("stale" if age_d >= 4 else "")
        if age_d >= 4:
            stale += 1
        mtime = dt.datetime.fromtimestamp(os.path.getmtime(p)).strftime("%Y-%m-%d %H:%M")
        toc.append(f'<a href="#{anchor}" data-c="{cat}">{html.escape(label)}'
                   f'<div class="d">{mtime} · {age_d}일 전</div></a>')
        if used < budget:
            inner = body_of(p)
            used += len(inner.encode("utf-8"))
        else:
            inner = '<p class="miss">용량 상한 초과 — 내용 생략</p>'
        parts.append(
            f'<section id="{anchor}" data-c="{cat}"><h2>{html.escape(label)}</h2>'
            f'<div class="age {cls}">{html.escape(fn)} · 갱신 {mtime} · {age_d}일 전</div>'
            f'<div class="inner">{inner}</div></section>')

    # ── 연구 갈래 색인 (4번째 탭) ─────────────────────────────
    # 연구색인_생성.py 가 만든 <section> 을 body_of() 를 거치지 않고 그대로 붙인다.
    # body_of() 는 style·script·class 를 걷어내므로 통과시키면 표가 죽는다.
    try:
        import importlib.util
        _ri = os.path.join(HERE, "연구색인_생성.py")
        _spec = importlib.util.spec_from_file_location("연구색인", _ri)
        _mod = importlib.util.module_from_spec(_spec)
        _spec.loader.exec_module(_mod)
        _outdir = os.path.dirname(os.path.abspath(a.out))
        parts.append(_mod.section_html(HERE, _outdir))
        _rows, _nf = _mod.collect(HERE)
        _act = sum(1 for r in _rows if r["state"] == "활성")
        toc.append(f'<a href="#연구갈래색인" data-c="research">연구 갈래 색인'
                   f'<div class="d">갈래 {len(_rows)} · 활성 {_act}</div></a>')
        found += 1
    except Exception as e:
        warn_ri = f'<div class="warn">연구 색인 생성 실패: {html.escape(str(e))}</div>'
    else:
        warn_ri = ""

    navs = '<button data-c="all" onclick="show(\'all\')">전체</button>' + "".join(
        f'<button data-c="{c}" onclick="show(\'{c}\')">{n}</button>' for c, n in CATS)

    warn = ""
    if stale:
        warn = (f'<div class="warn">⚠️ {stale}개 리포트가 <b>4일 이상</b> 갱신되지 않았다. '
                f'낡은 화면을 최신으로 착각하지 말 것 — 각 섹션에 갱신일이 붙어 있다.</div>')
    if missing:
        warn += (f'<div class="warn">📄 큐레이션 {len(CURATED)}개 중 {len(missing)}개 파일 없음: '
                 f'{html.escape(", ".join(missing[:8]))}{" …" if len(missing) > 8 else ""}</div>')

    doc = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>진우퀀트 허브 (자립형)</title><style>{CSS}</style></head><body>
<header><h1>진우퀀트 허브 <span style="font-size:12px;color:var(--dim)">자립형</span></h1>
<div class="meta">생성 {now:%Y-%m-%d %H:%M} · 리포트 {found}개 내장 · 외부 링크 0 ·
이 파일 하나만 있으면 어디서든 열린다</div>
<nav>{navs}</nav></header>
<main>{warn}{warn_ri}<div class="toc">{"".join(toc)}</div>{"".join(parts)}</main>
<footer>⚠️ 정보·검증용 · 투자자문 아님 · 백테는 실현손익 아님 · 책임 본인<br>
종전 <code>jq_hub.py</code> 는 상대경로 링크 방식이라 <b>강화키트 폴더 밖에서는 35개 링크가 전부 깨졌다.</b>
이 자립형은 내용을 통째로 넣어 그 문제를 없앤다.</footer>
<script>{JS}</script></body></html>"""

    outp = a.out
    os.makedirs(os.path.dirname(os.path.abspath(outp)), exist_ok=True)
    open(outp, "w", encoding="utf-8").write(doc)
    mb = len(doc.encode("utf-8")) / 1024 / 1024
    print("=" * 66)
    print(" 진우퀀트 허브 (자립형) 생성")
    print("=" * 66)
    print(f"  내장 리포트 {found}/{len(CURATED)}개 · 누락 {len(missing)}개 · 4일↑ 낡음 {stale}개")
    print(f"  크기 {mb:.2f} MB · 외부 링크 0 · 이미지 data URI 매립")
    print(f"  저장: {outp}")
    if missing:
        print(f"  누락: {', '.join(missing)}")
    print("\n  ⚠️ 정보·검증용 · 투자자문 아님")
    return 0


if __name__ == "__main__":
    sys.exit(main())
