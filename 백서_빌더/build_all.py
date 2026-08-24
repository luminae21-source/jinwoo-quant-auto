#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""build_all.py — 진우퀀트 종합 기술 백서 자체완결형 빌더 (2세대·자동 업데이트용)

진우퀀트_백서.md(마스터) + make_charts_v2.py(차트4종) + template.html → HTML·PDF·Word 4형식.
포터블: 이 스크립트 폴더(BASE)에서 동작. 클라우드 컨테이너(pandoc·chromium·Noto CJK·matplotlib) 전제.
사용: py build_all.py [--md <경로>]   → BASE/out/ 에 4형식.
⚠️ 라이브 수치는 허브가 SSOT · 백테는 실현손익 아님 · 투자자문 아님.
"""
import os, sys, base64, re, argparse, subprocess
BASE=os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0,BASE)
IMG=os.path.join(BASE,"img"); OUT=os.path.join(BASE,"out")
os.makedirs(IMG,exist_ok=True); os.makedirs(OUT,exist_ok=True)

def make_charts():
    import make_charts_v2
    make_charts_v2.make_charts(IMG)

def build_html(md_path, html_path):
    body_tmp=os.path.join(OUT,"_body.html")
    subprocess.run(["pandoc",md_path,"-f","markdown","-t","html5","--no-highlight","-o",body_tmp],check=True)
    body=open(body_tmp,encoding="utf-8").read()
    def uri(src):
        p=os.path.join(BASE,src)
        return "data:image/png;base64,"+base64.b64encode(open(p,"rb").read()).decode() if os.path.exists(p) else ""
    def repl_img(m):
        src=m.group("src"); alt=m.group("alt")
        if src.startswith("img/"): return f'<figure class="chart"><img src="{uri(src)}" alt="{alt}"><figcaption>{alt}</figcaption></figure>'
        return m.group(0)
    body=re.sub(r'<img src="(?P<src>[^"]+)" alt="(?P<alt>[^"]*)"[^>]*/?>',repl_img,body)
    def repl_bq(m):
        inner=m.group(1); txt=re.sub(r"<[^>]+>","",inner); cls="note"
        if "💡" in txt: cls="tip"
        elif "⚠️" in txt: cls="warn"
        elif "📚" in txt: cls="learn"
        elif "⚡" in txt: cls="warn"
        return f'<blockquote class="callout {cls}">{inner}</blockquote>'
    body=re.sub(r'<blockquote>(.*?)</blockquote>',repl_bq,body,flags=re.S)
    h2s=re.findall(r'<h2 id="([^"]+)">(.*?)</h2>',body,flags=re.S)
    clean=lambda t: re.sub(r"\s+"," ",re.sub(r"<[^>]+>","",t)).strip()
    toc="\n".join(f'<li><a href="#{h}">{clean(t)}</a></li>' for h,t in h2s)
    body=re.sub(r'^<h1[^>]*>.*?</h1>','',body,count=1,flags=re.S)
    import datetime as _dt
    tpl=open(os.path.join(BASE,"template.html"),encoding="utf-8").read()
    html=tpl.replace("{{TOC}}",toc).replace("{{BODY}}",body).replace("{{DATE}}",_dt.date.today().isoformat())
    open(html_path,"w",encoding="utf-8").write(html); print(f"  html: {os.path.basename(html_path)}")

def build_pdf(html_path, pdf_path):
    import asyncio
    from playwright.async_api import async_playwright
    chrome=next((c for c in ["/opt/pw-browsers/chromium-1194/chrome-linux/chrome"] if os.path.exists(c)),None)
    async def go():
        async with async_playwright() as p:
            b=await (p.chromium.launch(executable_path=chrome) if chrome else p.chromium.launch())
            pg=await b.new_page(); await pg.goto("file://"+html_path); await pg.wait_for_timeout(1000)
            await pg.pdf(path=pdf_path,format="A4",print_background=True,margin={"top":"14mm","bottom":"14mm","left":"12mm","right":"12mm"})
            await b.close()
    asyncio.run(go()); print(f"  pdf: {os.path.basename(pdf_path)}")

def build_docx(md_path, docx_path):
    subprocess.run(["pandoc",md_path,"-f","markdown","-t","docx","--resource-path",BASE,"-o",docx_path],check=True)
    print(f"  docx: {os.path.basename(docx_path)}")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--md",default=os.path.join(BASE,"진우퀀트_백서.md")); a=ap.parse_args()
    if not os.path.exists(a.md): sys.exit(f"마스터 원고 없음: {a.md}")
    if not os.path.exists(os.path.join(BASE,"template.html")): sys.exit("template.html 없음")
    if not os.path.exists(os.path.join(BASE,"make_charts_v2.py")): sys.exit("make_charts_v2.py 없음")
    print("진우퀀트 백서 빌드 시작 (2세대)"); make_charts()
    html=os.path.join(OUT,"진우퀀트_백서.html"); pdf=os.path.join(OUT,"진우퀀트_백서.pdf"); docx=os.path.join(OUT,"진우퀀트_백서.docx")
    build_html(a.md,html); build_pdf(html,pdf); build_docx(a.md,docx)
    print(f"완료 → {OUT}")

if __name__=="__main__": main()
