#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""selftest_all.py — 전 모듈 셀프테스트 일괄 실행·집계 (CI式 대시보드) · 시스템 자동화 안전판

왜: 모듈마다 --self-test 는 있는데 '한 번에 다 돌려 초록/빨강으로 보는' 화면이 없었다.
    코드를 고친 뒤 여기 한 번이면 어디가 깨졌는지 즉시 보인다.

동작: 루트+강화키트의 .py 중 '--self-test'를 가진 스크립트를 자동 발견→각각 실행→
      통과/실패 집계. 데이터 헬스체크·PIT 감사도 특수행으로 포함.
      결과를 셀프테스트_현황.json / .html 로 저장(허브에서 링크).
사용: py selftest_all.py [--root DIR] [--no-open] [--json]
⚠️ 정보·검증용·투자자문 아님·책임 본인.
"""

# ── 경로 자립화 (2026-07-27) — 샌드박스 하드코딩 제거 ──────────────
import os as _os, glob as _glob
_JQ_HERE = _os.path.dirname(_os.path.abspath(__file__))


def _jqroot():
    d = _JQ_HERE
    for _ in range(5):
        if _os.path.exists(_os.path.join(d, "종목시총_30년.csv")):
            return d
        d = _os.path.dirname(d)
    return _os.path.dirname(_JQ_HERE)


BASE = _os.environ.get("JQ_BASE", _jqroot())


def _jqfind(name):
    """이름으로 파일 자동탐색 (백업/보관 폴더 제외)."""
    for b in (BASE, _JQ_HERE, _os.getcwd()):
        hits = [h for h in _glob.glob(_os.path.join(b, "**", name), recursive=True)
                if not any(s in h for s in ("_백업", "_보관", "_archive", "__pycache__"))]
        if hits:
            return sorted(hits, key=len)[0]
    raise FileNotFoundError(f"{name} 를 못 찾음 (루트={BASE})")
# ────────────────────────────────────────────────────────────────

import os, sys, re, json, subprocess, datetime, argparse, webbrowser
HERE=os.path.dirname(os.path.abspath(__file__)); PARENT=os.path.dirname(HERE)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

SCAN_DIRS=[PARENT, HERE, os.path.join(PARENT,"강화키트")]
# 무겁거나 셀프테스트가 실제 매매/네트워크/데이터갱신을 건드릴 수 있는 것 제외(안전)
SKIP={"selftest_all.py","preflight.py","recommend_pipeline.py",
      "mcap_update.py","trackw_update.py","진우_전진기록.py","라이브_전진기록_갱신.py",
      "진우_일봉_증분수집.py","kakao_send_recommend.py","jq_notify.py"}
FLAG_RE=re.compile(r'--self-test|self_test|셀프테스트')
RATIO_RE=re.compile(r'(\d+)\s*/\s*(\d+)')
OUT_HTML="셀프테스트_현황.html"; OUT_JSON="셀프테스트_현황.json"

def discover(root):
    seen={}; dirs=[root, os.path.join(root,"강화키트")] + SCAN_DIRS
    for d in dirs:
        if not os.path.isdir(d): continue
        for fn in os.listdir(d):
            if not fn.endswith(".py") or fn in SKIP or fn in seen: continue
            p=os.path.join(d,fn)
            try: txt=open(p,encoding="utf-8",errors="ignore").read()
            except Exception: continue
            # argparse 로 --self-test 를 받는 스크립트만
            if "--self-test" in txt or "\"self-test\"" in txt or "'self-test'" in txt:
                seen[fn]=p
    return seen  # {파일명: 경로}

def _child_env():
    # ★ 한국어 Windows(cp949)에서 파이프로 캡처하면 자식이 이모지(✅→─) 출력 시
    #    UnicodeEncodeError 로 죽는다 → 자식 stdout 을 강제로 UTF-8 로.
    e=dict(os.environ); e["PYTHONIOENCODING"]="utf-8"; e["PYTHONUTF8"]="1"; return e

def run_one(path, timeout=120):
    try:
        r=subprocess.run([sys.executable,"-W","ignore",path,"--self-test"],
                         capture_output=True,text=True,timeout=timeout,
                         encoding="utf-8",errors="replace",env=_child_env(),
                         cwd=os.path.dirname(path))
        txt=(r.stdout or "")+(r.stderr or "")
        passed=total=None
        for ln in txt.splitlines():
            if FLAG_RE.search(ln):
                m=RATIO_RE.search(ln)
                if m: passed,total=int(m.group(1)),int(m.group(2)); break
        if total is not None:
            ok = (passed==total) and r.returncode==0
            detail=f"{passed}/{total}"
        else:
            ok = r.returncode==0
            detail = "exit 0" if ok else f"exit {r.returncode}"
        return ("PASS" if ok else "FAIL"), detail
    except subprocess.TimeoutExpired:
        return "TIMEOUT", f">{timeout}s"
    except Exception as e:
        return "ERROR", str(e)[:80]

def run_special(root):
    """데이터 헬스체크·PIT 감사(셀프테스트 아님) 결과도 한 줄씩."""
    rows=[]
    for fn,arg,label in [("data_healthcheck.py","--json","데이터 헬스체크"),
                         ("pit_lag.py","--audit","PIT 공시시차 감사")]:
        p=None
        for d in [HERE,root,os.path.join(root,"강화키트")]+SCAN_DIRS:
            q=os.path.join(d,fn)
            if os.path.exists(q): p=q; break
        if not p: continue
        try:
            r=subprocess.run([sys.executable,"-W","ignore",p,arg],
                             capture_output=True,text=True,timeout=180,
                             encoding="utf-8",errors="replace",env=_child_env(),
                             cwd=os.path.dirname(p))
            txt=(r.stdout or "")
            if fn=="data_healthcheck.py":
                v="?"
                try:
                    s=txt.find("{"); e=txt.rfind("}")  # 경고줄이 섞여도 JSON 블록만 추출
                    if s>=0 and e>s: v=json.loads(txt[s:e+1]).get("verdict","?")
                except Exception: v="?"
                st={"PASS":"PASS","WARN":"WARN","FAIL":"FAIL"}.get(v,"ERROR"); detail=v
            else:
                st="PASS" if r.returncode==0 else "FAIL"
                m=re.search(r"시차\s*(\d+)개월",txt); detail=(f"시차 {m.group(1)}개월" if m else ("PASS" if st=='PASS' else 'FAIL'))
            rows.append((label,st,detail))
        except Exception as e:
            rows.append((label,"ERROR",str(e)[:60]))
    return rows

def build_html(results, specials, ts):
    npass=sum(1 for s,_ in results.values() if s=="PASS"); nfail=len(results)-npass
    allrows=[(k,s,d) for k,s,d in specials]+[(k,s,d) for k,(s,d) in sorted(results.items())]
    col={"PASS":"#2ec36b","WARN":"#e0a32e","FAIL":"#e5484d","TIMEOUT":"#e5484d","ERROR":"#e5484d"}
    ic={"PASS":"✅","WARN":"⚠️","FAIL":"❌","TIMEOUT":"⏱","ERROR":"❌"}
    banner_ok = (nfail==0 and all(s!="FAIL" for _,s,_ in specials))
    bcol="#2ec36b" if banner_ok else "#e5484d"
    btxt=f"전체 정상 · {npass}개 통과" if banner_ok else f"문제 {nfail}개 · 확인 필요"
    cards="".join(
        f'<div class=row><span class=nm>{k}</span>'
        f'<span class=st style="color:{col.get(s,"#888")}">{ic.get(s,"?")} {s}</span>'
        f'<span class=dt>{d}</span></div>' for k,s,d in allrows)
    return f"""<!doctype html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>진우퀀트 셀프테스트 현황</title><style>
:root{{--bg:#0b1020;--card:#141b2e;--ink:#e8edf6;--sub:#9fb0c9;--line:#243149}}
@media(prefers-color-scheme:light){{:root{{--bg:#f4f6fb;--card:#fff;--ink:#0f1830;--sub:#5a6a86;--line:#e3e9f4}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,'Segoe UI',Roboto,'Malgun Gothic',sans-serif;padding:22px;line-height:1.5}}
.wrap{{max-width:760px;margin:0 auto}}h1{{font-size:21px;margin:0 0 2px}}.sub{{color:var(--sub);font-size:12.5px;margin-bottom:14px}}
.banner{{border-radius:12px;padding:13px 16px;font-weight:700;color:#fff;background:{bcol};margin-bottom:14px}}
.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:6px 8px}}
.row{{display:grid;grid-template-columns:1fr auto auto;gap:12px;align-items:center;padding:9px 10px;border-bottom:1px solid var(--line)}}
.row:last-child{{border-bottom:none}}.nm{{font-weight:600;font-size:13px}}.st{{font-weight:700;font-size:12.5px;font-variant-numeric:tabular-nums}}
.dt{{color:var(--sub);font-size:11.5px;min-width:70px;text-align:right}}
.warn{{color:#e0a32e;font-size:11px;margin-top:12px}}
</style></head><body><div class=wrap>
<h1>진우퀀트 셀프테스트 현황</h1>
<div class=sub>{ts} · 코드 수정 뒤 여기 한 번이면 어디가 깨졌는지 보임 · 초록=통과</div>
<div class=banner>{'✅' if banner_ok else '❌'} {btxt}</div>
<div class=card>{cards}</div>
<div class=warn>⚠️ 정보·검증용·과거통계. 미래·수익 보장 아님. 투자자문 아님 · 최종 판단·책임 본인.</div>
</div></body></html>"""

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--root"); ap.add_argument("--no-open",action="store_true")
    ap.add_argument("--json",action="store_true")
    a=ap.parse_args()
    root=os.path.abspath(a.root) if a.root else PARENT
    ts=datetime.datetime.now().strftime("%Y-%m-%d %H:%M")
    print("="*70); print(f"셀프테스트 일괄 실행 · {ts}"); print("="*70)

    found=discover(root)
    results={}
    for fn,p in sorted(found.items()):
        st,detail=run_one(p)
        results[fn]=(st,detail)
        ic={"PASS":"✅","FAIL":"❌","TIMEOUT":"⏱","ERROR":"❌"}.get(st,"?")
        print(f"  {ic} {fn:<28} {st:<7} {detail}")
    print("\n[특수 검사]")
    specials=run_special(root)
    for k,s,d in specials:
        print(f"  {'✅' if s=='PASS' else ('⚠️' if s=='WARN' else '❌')} {k:<20} {s:<6} {d}")

    npass=sum(1 for _,(s,_) in results.items() if s=="PASS"); nfail=len(results)-npass
    print("\n"+"-"*70); print(f"종합: 셀프테스트 {npass}/{len(results)} 통과 · 특수 {sum(1 for _,s,_ in specials if s=='PASS')}/{len(specials)}")

    payload=dict(ts=ts, npass=npass, nfail=nfail,
                 selftests={k:{"status":s,"detail":d} for k,(s,d) in results.items()},
                 specials=[{"name":k,"status":s,"detail":d} for k,s,d in specials])
    outdir=os.path.join(root,"강화키트") if os.path.isdir(os.path.join(root,"강화키트")) else HERE
    try:
        open(os.path.join(outdir,OUT_JSON),"w",encoding="utf-8").write(json.dumps(payload,ensure_ascii=False,indent=2))
        html=build_html(results,specials,ts)
        outp=os.path.join(outdir,OUT_HTML); open(outp,"w",encoding="utf-8").write(html)
        print(f"기록: {OUT_JSON} · {OUT_HTML}")
        if not a.no_open and not a.json:
            try: webbrowser.open("file://"+outp.replace("\\","/"))
            except Exception: pass
    except Exception as e:
        print("저장 실패:",e)
    print("⚠️ 정보·검증용. 투자자문 아님·책임 본인.")
    sys.exit(1 if nfail>0 or any(s=="FAIL" for _,s,_ in specials) else 0)

if __name__=="__main__": main()
