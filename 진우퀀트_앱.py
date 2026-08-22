# -*- coding: utf-8 -*-
r"""진우퀀트_앱.py — 진우퀀트 로컬 앱 (브라우저 대시보드 · v6 2026-08-21)

[v6] 화면(UI)을 폴더의 진우퀀트_UI.html에서 읽는다.
     → 앞으로 UI 수정은 그 파일만 바꾸면 됨 (exe 재빌드 불필요).
     파일이 없으면 내장 화면(구버전)으로 자동 폴백.

[무엇] 매일 루틴 전체를 버튼으로: 국면 확인 → 휩쏘 탐지 → 원장 추적 → 가상매매 → 리포트 열람.
       기존 검증된 스크립트를 그대로 실행한다(로직 재작성 없음 = 검정과 실행이 같은 코드).

[사용]
  py 진우퀀트_앱.py            → 브라우저가 자동으로 열린다 (http://127.0.0.1:8777)
  py 진우퀀트_앱.py --lan      → 같은 와이파이의 휴대폰에서도 접속 (http://PC내부IP:8777)
  py 진우퀀트_앱.py --port 9000

[안전] 로컬 전용 서버 · 허용된 스크립트만 실행 가능 · 폴더 안 파일만 열람 가능.
⚠️ 관찰·기록·가상매매용. 실제 주문 아님 · 매매 추천 아님.
"""
import os, sys, json, glob, subprocess, argparse, threading, webbrowser, socket
import urllib.parse as up
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

if getattr(sys, "frozen", False):          # PyInstaller exe로 실행될 때
    HERE = os.path.dirname(os.path.abspath(sys.executable))
    # dist\ 같은 빈 폴더에서 실행돼도 도구가 있는 상위 폴더를 자동으로 찾는다
    _probe = HERE
    for _ in range(3):
        if os.path.exists(os.path.join(_probe, "시장국면.py")):
            HERE = _probe; break
        _probe = os.path.dirname(_probe)
    import shutil as _sh
    PYEXE = _sh.which("python") or _sh.which("py") or "python"
else:
    HERE = os.path.dirname(os.path.abspath(__file__))
    PYEXE = sys.executable
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

# 허용된 작업만 실행 (임의 명령 실행 차단) · 형식: (스크립트, 인자, 설명[, 타임아웃초])
JOBS = {
    "탐지":     ("휩쏘_탐색기.py", ["--noopen"],            "휩쏘 탐지 (A/B + 국면 + 밸류태그 + 원장 자동등록)"),
    "관찰":     ("휩쏘_관찰.py", ["--noopen"],              "관찰 원장 전진 추적"),
    "가상추적": ("가상매매.py", ["--noopen"],               "가상매매 보유 추적·자본곡선"),
    "가상진입": ("가상매매.py", ["--open", "--noopen"],     "가상매매 신규 진입 (최신 탐지분)"),
    "일간리포트": ("진우퀀트_리포트.py", ["--period", "일간", "--noopen"], "오늘의 국면·원장·가상매매 요약"),
    "주간리포트": ("진우퀀트_리포트.py", ["--period", "주간", "--noopen"], "최근 5거래일 종합"),
    "월간리포트": ("진우퀀트_리포트.py", ["--period", "월간", "--noopen"], "이번 달 종합 + 30년 역사 배경"),
    "역사원장갱신": ("역사원장_갱신.py", [],                  "30년 검정 재실행 + 역사원장 재생성 (⏱10~25분)", 2400),
    "조사스캐너": ("조사_스캐너.py", [],                     "S1/S2/A′ 스캐너"),
    "조사관찰": ("휩쏘_관찰.py", ["--ledger", "조사", "--noopen"], "조사 원장 추적"),
    "매매카드": ("휩쏘_매매카드.py", [],                     "매매카드 (오늘 탐지분)"),
}
DOCS = [  # (파일, 라벨) — 있는 것만 노출
    ("진우퀀트_시스템평가.html", "시스템 평가서 ★"),
    ("가상매매_현황.html", "가상매매 현황"),
    ("휩쏘_관찰_현황.html", "관찰 원장 현황"),
    ("조사_관찰_현황.html", "조사 원장 현황"),
    ("휩쏘_종합보고서.html", "종합보고서 ★"),
    ("휩쏘_역사원장.html", "30년 역사원장"),
    ("휩쏘_케이스집.html", "케이스집"),
    ("휩쏘_역사검정_리포트.html", "30년 검정 리포트"),
    ("휩쏘_고점사이클_리포트.html", "고점·사이클"),
    ("휩쏘_재무검정_리포트.html", "재무 팩터"),
    ("휩쏘_종목군월별_리포트.html", "종목군 월별"),
    ("휩쏘_스윙단기_리포트.html", "스윙/단기 검정"),
    ("휩쏘_시스템.html", "시스템 한 장"),
    ("진우퀀트_휩쏘_인수인계.md", "인수인계 문서"),
    ("진우퀀트_쇼케이스.html", "시스템 쇼케이스 ★"),
    ("진우퀀트_디자인가이드.html", "디자인 가이드"),
    ("가족현황판.html", "가족 현황판"),
    ("가족공유_안내.md", "가족공유 안내"),
]
ALLOWED_EXT = {".html", ".htm", ".md", ".csv", ".json", ".txt"}
LOCK = threading.Lock()          # 작업 동시 실행 방지


def num(x, d=0.0):
    try: return float(x)
    except Exception: return d


def read_csv_rows(path):
    """의존성 없이 CSV → dict 리스트 (utf-8-sig)."""
    import csv
    if not os.path.exists(path): return []
    with open(path, encoding="utf-8-sig", newline="") as f:
        return list(csv.DictReader(f))


def regime_now():
    try:
        import importlib.util
        p = os.path.join(HERE, "시장국면.py")
        spec = importlib.util.spec_from_file_location("sj", p)
        m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
        return m.regime_at(None)
    except Exception:
        # exe 모드: 번들 파이썬엔 numpy가 없다 → 시스템 파이썬에게 위임
        try:
            code = ("import importlib.util,json,os;"
                    f"p=os.path.join({HERE!r},'시장국면.py');"
                    "s=importlib.util.spec_from_file_location('sj',p);"
                    "m=importlib.util.module_from_spec(s);s.loader.exec_module(m);"
                    "print(json.dumps(m.regime_at(None),ensure_ascii=False,default=str))")
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            r = subprocess.run([PYEXE, "-c", code], cwd=HERE, capture_output=True,
                               timeout=60, env=env)
            out = (r.stdout or b"").decode("utf-8", "replace").strip().splitlines()
            return json.loads(out[-1]) if out else {"판정": "?", "이유": "국면 계산 출력 없음", "실행": None}
        except Exception as e:
            return {"판정": "?", "이유": f"시장국면 로드 실패: {str(e)[:50]}", "실행": None}


def status():
    rg = regime_now()
    # 관찰 원장
    obs = read_csv_rows(os.path.join(HERE, "휩쏘_관찰.csv"))
    obs_sum = {}
    for r in obs:
        obs_sum[r.get("상태", "?")] = obs_sum.get(r.get("상태", "?"), 0) + 1
    obs_upd = max((r.get("갱신일", "") for r in obs), default="")
    # 가상매매
    cfg = {}
    p = os.path.join(HERE, "가상매매_설정.json")
    if os.path.exists(p):
        try: cfg = json.load(open(p, encoding="utf-8"))
        except Exception: pass
    eq = read_csv_rows(os.path.join(HERE, "가상매매_자본곡선.csv"))
    vt = read_csv_rows(os.path.join(HERE, "가상매매_원장.csv"))
    v_open = sum(1 for r in vt if r.get("상태") in ("보유", "절반실현"))
    v_done = sum(1 for r in vt if r.get("상태") == "청산")
    v_skip = sum(1 for r in vt if str(r.get("상태", "")).startswith("미진입"))
    total = num(eq[-1]["평가포함자산"]) if eq else num(cfg.get("시작자본", 0))
    ret = (total / num(cfg.get("시작자본", 1), 1) - 1) * 100 if cfg else 0.0
    # 탐지 파일
    det = sorted(glob.glob(os.path.join(HERE, "휩쏘탐지_*.csv")), reverse=True)[:5]
    det = [os.path.basename(x) for x in det]
    # 문서
    docs = [(f, lab) for f, lab in DOCS if os.path.exists(os.path.join(HERE, f))]
    docs += [(os.path.basename(x), os.path.basename(x).replace(".html", ""))
             for x in sorted(glob.glob(os.path.join(HERE, "휩쏘탐지_*.html")), reverse=True)[:3]]
    docs += [(os.path.basename(x), os.path.basename(x).replace(".html", ""))
             for x in sorted(glob.glob(os.path.join(HERE, "리포트_*.html")), reverse=True)[:6]]
    jobs = {k: dict(desc=v[2], ok=os.path.exists(os.path.join(HERE, v[0])))
            for k, v in JOBS.items()}
    eq_pts = [[r.get("date", ""), num(r.get("평가포함자산"))] for r in eq][-60:]
    return dict(국면=rg, 관찰=dict(요약=obs_sum, 갱신일=obs_upd, 총=len(obs)),
                가상=dict(총자산=total, 수익률=round(ret, 2), 보유=v_open, 청산=v_done,
                        미진입=v_skip, 시작=num(cfg.get("시작자본", 0)), 시작일=cfg.get("시작일", ""),
                        곡선=eq_pts),
                탐지파일=det, 문서=docs, 작업=jobs)


def run_job(key):
    if key not in JOBS:
        return dict(ok=False, out=f"허용되지 않은 작업: {key}")
    job = JOBS[key]
    script, args = job[0], job[1]
    tmo = job[3] if len(job) > 3 else 900
    sp = os.path.join(HERE, script)
    if not os.path.exists(sp):
        return dict(ok=False, out=f"{script} 없음 — 이 PC에 해당 도구가 설치되지 않았다.")
    if not LOCK.acquire(blocking=False):
        return dict(ok=False, out="다른 작업이 실행 중 — 끝난 뒤 다시.")
    try:
        env = dict(os.environ, PYTHONIOENCODING="utf-8")
        r = subprocess.run([PYEXE, sp] + args, cwd=HERE, capture_output=True,
                           timeout=tmo, env=env)
        out = (r.stdout or b"").decode("utf-8", "replace")
        err = (r.stderr or b"").decode("utf-8", "replace")
        txt = out + (("\n[stderr]\n" + err) if err.strip() else "")
        return dict(ok=(r.returncode == 0), out=txt[-12000:])
    except subprocess.TimeoutExpired:
        return dict(ok=False, out=f"시간 초과({tmo//60}분) — 데이터 파일 확인 필요.")
    except Exception as e:
        return dict(ok=False, out=f"실행 오류: {e}")
    finally:
        LOCK.release()


PAGE = """<!DOCTYPE html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>진우퀀트+K</title>
<link rel="manifest" href="/manifest.json"><link rel="apple-touch-icon" href="/icon-192.png">
<meta name="apple-mobile-web-app-capable" content="yes"><meta name="apple-mobile-web-app-title" content="진우퀀트+K">
<meta name="theme-color" content="#f8f4eb"><style>
:root{color-scheme:light;--bg:#f6f6f4;--sf:#fcfcfb;--bd:#e3e2dd;--ink:#0f0f0e;--ink2:#54534e;--mut:#8a877e;--a:#2a78d6;--b:#eb6834;--good:#1a7f4b;--bad:#c0342f}
@media(prefers-color-scheme:dark){:root{color-scheme:dark;--bg:#111110;--sf:#1a1a19;--bd:#33322f;--ink:#fafaf7;--ink2:#c3c2b7;--mut:#8f8e85;--a:#3987e5;--b:#d95926;--good:#4bb87c;--bad:#e0655a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Malgun Gothic","Apple SD Gothic Neo",sans-serif;font-size:14.5px;line-height:1.55}
.w{max-width:960px;margin:0 auto;padding:26px 18px 60px}
h1{font-size:22px;margin:0;display:flex;align-items:center;gap:8px}.tag{color:var(--mut);font-size:12px;font-weight:400}
.logo{width:34px;height:34px;border-radius:9px;border:1px solid var(--bd)}
.plusk{color:var(--b);font-weight:800}
.ban{margin:12px 0;padding:10px 14px;border-radius:10px;border:1px solid var(--bd);border-left:5px solid var(--mut);background:var(--sf);font-size:13.5px}
.k{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0}
.kb{background:var(--sf);border:1px solid var(--bd);border-radius:11px;padding:11px 13px}
.kb .v{font-size:19px;font-weight:700}.kb .l{font-size:11px;color:var(--mut);margin-top:2px}
h2{font-size:14px;margin:20px 0 8px;color:var(--ink2)}
.btns{display:grid;grid-template-columns:repeat(auto-fit,minmax(180px,1fr));gap:8px}
button{background:var(--sf);border:1px solid var(--bd);border-radius:10px;padding:11px 12px;font-size:13.5px;cursor:pointer;color:var(--ink);text-align:left;font-family:inherit}
button:hover{border-color:var(--a)}button:disabled{opacity:.45;cursor:default}
button b{display:block}button span{font-size:11px;color:var(--mut)}
.docs{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:7px}
.docs a{display:block;background:var(--sf);border:1px solid var(--bd);border-radius:9px;padding:9px 12px;text-decoration:none;color:var(--ink);font-size:13px}
.docs a:hover{border-color:var(--a)}
#log{background:var(--sf);border:1px solid var(--bd);border-radius:10px;padding:12px;font:12px/1.5 ui-monospace,Consolas,monospace;white-space:pre-wrap;max-height:320px;overflow:auto;display:none;margin-top:10px}
.sp{display:inline-block;width:13px;height:13px;border:2px solid var(--a);border-top-color:transparent;border-radius:50%;animation:r 0.8s linear infinite;vertical-align:-2px;margin-right:6px}
@keyframes r{to{transform:rotate(360deg)}}
svg{display:block;margin-top:4px}
.warn{color:var(--mut);font-size:11.5px;margin-top:26px;border-top:1px solid var(--bd);padding-top:10px}
</style></head><body><div class=w>
<h1><img class=logo src="/icon-192.png" alt=""> 진우퀀트<span class=plusk>+K</span> <span class=tag>휩쏘 시스템</span></h1>
<div class=ban id=ban>국면 확인 중…</div>
<div class=k id=kpis></div>
<h2>실행</h2><div class=btns id=btns></div>
<div id=log></div>
<h2>리포트 · 문서</h2><div class=docs id=docs></div>
<p class=warn>⚠️ 관찰·기록·가상매매용 로컬 앱. 실제 주문 아님 · 매매 추천 아님. 이 창을 닫아도 서버는 터미널에서 Ctrl+C로 종료.</p>
</div><script>
const $=id=>document.getElementById(id);
function fmt(n){return Number(n).toLocaleString("ko-KR")}
async function refresh(){
 const s=await (await fetch("/api/status")).json();
 const rg=s.국면||{}; const m={"실행(유리)":["🟢","var(--good)"],"주의(중립)":["🟡","var(--b)"],"관찰만(불리)":["🔴","var(--bad)"]}[rg.판정]||["·","var(--mut)"];
 $("ban").style.borderLeftColor=m[1];
 $("ban").innerHTML=`${m[0]} <b>오늘 시장국면: ${rg.판정||"?"}</b> — ${rg.이유||""}`;
 const o=s.관찰||{},v=s.가상||{};
 const osum=Object.entries(o.요약||{}).map(([k,n])=>`${k} ${n}`).join(" · ")||"-";
 let curve="";
 if((v.곡선||[]).length>1){const ys=v.곡선.map(p=>p[1]);const lo=Math.min(...ys)*0.998,hi=Math.max(...ys)*1.002;
  const pts=v.곡선.map((p,i)=>`${(i/(v.곡선.length-1))*130},${34-((p[1]-lo)/(hi-lo||1))*30}`).join(" ");
  curve=`<svg viewBox="0 0 130 36" width="130"><polyline points="${pts}" fill="none" stroke="var(--a)" stroke-width="1.6"/></svg>`;}
 $("kpis").innerHTML=`
 <div class=kb><div class=v>${fmt(v.총자산||0)}원</div><div class=l>가상계좌 총자산 (시작 ${fmt(v.시작||0)})</div>${curve}</div>
 <div class=kb><div class=v style="color:var(${(v.수익률||0)>=0?"--good":"--bad"})">${(v.수익률||0).toFixed(2)}%</div><div class=l>가상매매 수익률 · 보유 ${v.보유||0} · 청산 ${v.청산||0} · 미진입 ${v.미진입||0}</div></div>
 <div class=kb><div class=v>${o.총||0}종</div><div class=l>관찰 원장 (${osum}) · 갱신 ${o.갱신일||"-"}</div></div>
 <div class=kb><div class=v>${(s.탐지파일||[])[0]?.replace("휩쏘탐지_","").replace(".csv","")||"없음"}</div><div class=l>마지막 탐지</div></div>`;
 $("btns").innerHTML=Object.entries(s.작업||{}).map(([k,j])=>
  `<button onclick="run('${k}')" ${j.ok?"":"disabled"}><b>${k}</b><span>${j.desc}${j.ok?"":" (도구 없음)"}</span></button>`).join("");
 $("docs").innerHTML=(s.문서||[]).map(([f,l])=>`<a href="/open?f=${encodeURIComponent(f)}" target="_blank">${l}</a>`).join("");
}
async function run(k){
 const L=$("log");L.style.display="block";
 L.innerHTML=`<span class=sp></span>[${k}] 실행 중… (데이터 크기에 따라 1~3분)`;
 document.querySelectorAll("button").forEach(b=>b.disabled=true);
 try{const r=await (await fetch("/api/run?job="+encodeURIComponent(k))).json();
  L.textContent=`[${k}] ${r.ok?"완료":"실패"}\\n\\n`+r.out;}catch(e){L.textContent="[통신 오류] "+e;}
 document.querySelectorAll("button").forEach(b=>b.disabled=false);
 refresh();
}
refresh();setInterval(refresh,90000);
</script></body></html>"""


def get_page():
    """UI는 폴더의 진우퀀트_UI.html이 우선 — 있으면 재빌드 없이 화면만 교체 가능.
    없거나 읽기 실패 시 내장 PAGE(구버전)로 폴백."""
    p = os.path.join(HERE, "진우퀀트_UI.html")
    try:
        if os.path.exists(p):
            return open(p, encoding="utf-8").read()
    except Exception:
        pass
    return PAGE


class H(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, code, body, ctype="text/html; charset=utf-8"):
        if isinstance(body, str): body = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        path = self.path
        try:                                # 비표준 클라이언트의 raw UTF-8 경로 방어
            path = path.encode("latin-1").decode("utf-8")
        except Exception: pass
        u = up.urlparse(path)
        q = up.parse_qs(u.query)
        try:
            viewer = self.client_address[0] not in ("127.0.0.1", "::1")
            if u.path == "/":
                self._send(200, get_page())
            elif u.path == "/manifest.json":
                mf = {"name": "진우퀀트+K", "short_name": "진우퀀트+K",
                      "start_url": "/", "display": "standalone",
                      "background_color": "#f8f4eb", "theme_color": "#f8f4eb",
                      "icons": [{"src": "/icon-192.png", "sizes": "192x192", "type": "image/png"},
                                 {"src": "/icon-512.png", "sizes": "512x512", "type": "image/png"}]}
                self._send(200, json.dumps(mf, ensure_ascii=False), "application/manifest+json; charset=utf-8")
            elif u.path in ("/icon-192.png", "/icon-512.png"):
                p = os.path.join(HERE, u.path.lstrip("/"))
                if os.path.exists(p): self._send(200, open(p, "rb").read(), "image/png")
                else: self._send(404, "없음")
            elif u.path == "/api/status":
                st = status()
                st["뷰어"] = viewer          # 형 PC(127.0.0.1)가 아니면 읽기 전용
                self._send(200, json.dumps(st, ensure_ascii=False, default=str),
                           "application/json; charset=utf-8")
            elif u.path == "/api/run":
                if viewer:                   # 가족 기기에서는 실행 금지 (서버가 강제)
                    self._send(200, json.dumps(dict(ok=False,
                        out="읽기 전용 화면입니다 — 실행은 형 PC에서만 가능해요."),
                        ensure_ascii=False), "application/json; charset=utf-8")
                    return
                key = (q.get("job") or [""])[0]
                self._send(200, json.dumps(run_job(key), ensure_ascii=False),
                           "application/json; charset=utf-8")
            elif u.path == "/open":
                f = os.path.basename((q.get("f") or [""])[0])
                ext = os.path.splitext(f)[1].lower()
                p = os.path.join(HERE, f)
                if not f or ext not in ALLOWED_EXT or not os.path.exists(p):
                    self._send(404, "없음"); return
                ct = {".html": "text/html", ".htm": "text/html", ".md": "text/plain",
                      ".csv": "text/plain", ".json": "application/json", ".txt": "text/plain"}[ext]
                self._send(200, open(p, "rb").read(), ct + "; charset=utf-8")
            else:
                self._send(404, "404")
        except Exception as e:
            try: self._send(500, f"오류: {e}")
            except Exception: pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--port", type=int, default=8777)
    ap.add_argument("--lan", action="store_true", help="같은 와이파이 기기(휴대폰) 접속 허용")
    ap.add_argument("--nobrowser", action="store_true")
    a = ap.parse_args()
    host = "0.0.0.0" if a.lan else "127.0.0.1"
    srv = ThreadingHTTPServer((host, a.port), H)
    url = f"http://127.0.0.1:{a.port}"
    print("=" * 60)
    print(f" 진우퀀트 앱 실행 중 → {url}")
    if a.lan:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]; s.close()
            print(f" 휴대폰(같은 와이파이): http://{ip}:{a.port}")
        except Exception: pass
    print(" 종료: 이 창에서 Ctrl+C")
    print("=" * 60)
    if not a.nobrowser:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n종료.")


if __name__ == "__main__":
    main()
