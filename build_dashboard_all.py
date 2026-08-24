#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
build_dashboard_all.py — 통합 대시보드 빌더 (4섹션 한 화면, charset 보장)
==============================================================================
목적: 흩어진 대시보드(테마·풀·매수)를 매번 최신 데이터로 만들어 **하나의 통합 HTML**로
      합친다. 업로드본이 깨졌던 원인(charset 누락 fragment)을 구조적으로 차단:
      항상 <meta charset="utf-8"> + CSS 변수 포함한 완전한 문서를 출력.

동작:
  1) 컴포넌트 생성기 실행(최신화): supercycle_monitor.py · build_stock_pool.py · supercycle_buy.py
     (네트워크 불필요·캐시 패널 사용. 실패하면 기존 dashboard_*.html로 폴백.)
  2) 각 산출 HTML에서 <style>·<body>를 추출해 섹션으로 합쳐 1개 문서로 출력.
산출: 진우퀀트_통합대시보드_YYYY-MM-DD.html
무수정: production·heat·발굴트랙. 컴포넌트 스크립트도 읽어 합칠 뿐 수정 안 함.
사용: python build_dashboard_all.py [--selftest] [--no-regen]
정직: 의사결정 보조 · 검증된 매수룰 아님(관찰후보엔 백테스트 기각 경고 동반).
"""
import argparse, os, re, sys, subprocess, datetime
HERE = os.path.dirname(os.path.abspath(__file__))

GENS = [
    ("decision_view.py",       "진우퀀트_의사결정뷰_LATEST.html", "① 의사결정 종합 (강·약 한 줄)"),
    ("supercycle_monitor.py", "dashboard_supercycle.html", "② 테마 현황 · 보유 4-way (수퍼사이클)"),
    ("build_stock_pool.py",    "dashboard_pool.html",       "③ 종목 풀 · 전 시장 점수 (287종)"),
    ("supercycle_buy.py",      "dashboard_buy.html",        "④ ON테마 관찰후보 · 매수신호 아님"),
]

HEAD = """<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>진우퀀트 통합 대시보드 — {date}</title>
<style>
:root{{
 --font-sans:-apple-system,'Segoe UI',Roboto,'Malgun Gothic','Apple SD Gothic Neo',sans-serif;
 --border-radius-md:8px;
 --color-background-secondary:#f4f5f7;--color-background-success:#e3f6ea;
 --color-background-warning:#fff4e0;--color-background-info:#e7f0fb;
 --color-border-tertiary:#e3e6eb;
 --color-text-secondary:#5a6270;--color-text-tertiary:#8b919b;
 --color-text-success:#177d43;--color-text-warning:#a8650f;--color-text-info:#1e5fb0;
}}
html,body{{margin:0;background:#fff;color:#1a1d23}}
body{{font-family:var(--font-sans);padding:14px 16px;line-height:1.5;max-width:820px;margin:0 auto}}
.sr-only{{position:absolute;width:1px;height:1px;overflow:hidden;clip:rect(0 0 0 0)}}
.allhdr{{display:flex;align-items:baseline;justify-content:space-between;margin-bottom:4px}}
.allhdr b{{font-size:18px}}.allhdr span{{color:var(--color-text-tertiary);font-size:12px}}
.allguard{{background:var(--color-background-warning);color:var(--color-text-warning);border:1px solid var(--color-border-tertiary);border-radius:8px;padding:8px 12px;font-size:12.5px;margin:8px 0 16px}}
.allsec{{border-top:2px solid var(--color-border-tertiary);margin-top:22px;padding-top:8px}}
.allsec>h2.secttl{{font-size:15px;margin:6px 0 4px}}
.sumbar{{display:flex;flex-wrap:wrap;gap:8px;margin:6px 0 14px}}
.sumcell{{background:var(--color-background-secondary);border:1px solid var(--color-border-tertiary);border-radius:8px;padding:7px 11px;font-size:12px}}
.sumcell b{{display:block;font-size:15px;margin-top:1px}}
.sumtake{{background:var(--color-background-info);color:var(--color-text-info);border-radius:8px;padding:8px 12px;font-size:12.5px;margin-bottom:14px}}
@media (prefers-color-scheme:dark){{
 html,body{{background:#0f1115;color:#e8eaed}}
 :root{{--color-background-secondary:#181b22;--color-border-tertiary:#262a33;
  --color-text-secondary:#9aa0aa;--color-text-tertiary:#7a818c;
  --color-background-success:#143b2a;--color-text-success:#7ee0ad;
  --color-background-warning:#3b2e14;--color-text-warning:#ffd479;
  --color-background-info:#16314f;--color-text-info:#9fc4e8;}}
}}
</style>
{styles}
</head><body>
<div class="allhdr"><b>🔥 진우퀀트 통합 대시보드</b><span>기준 {date} · 생성 {ts}</span></div>
<div class="allguard">⚠️ 의사결정 보조 · <b>검증된 매수룰 아님</b> · production v3.7.2 무변경. 관찰후보엔 백테스트 기각 경고 동반. 결정·책임은 진우.</div>
__BANNER__
"""


def regen(timeout=180):
    done = {}
    try:
        subprocess.run([sys.executable, "signal_efficacy.py", "--months", "24"], cwd=HERE, timeout=200,
                       capture_output=True, text=True,
                       env={**os.environ, "PYTHONPYCACHEPREFIX": os.path.join(HERE, "__jqpyc__")})
    except Exception:
        pass
    for script, out, _ in GENS:
        sp = os.path.join(HERE, script)
        if not os.path.exists(sp):
            done[out] = "스크립트없음"; continue
        try:
            env = {**os.environ, "PYTHONPYCACHEPREFIX": os.path.join(HERE, "__jqpyc__"),
                   "PYTHONDONTWRITEBYTECODE": "0"}
            r = subprocess.run([sys.executable, script], cwd=HERE, timeout=timeout,
                               capture_output=True, text=True, env=env)
            done[out] = "재생성OK" if r.returncode == 0 else f"실패(rc{r.returncode})"
        except Exception as e:
            done[out] = f"예외:{type(e).__name__}"
    return done


def extract(html):
    """HTML → (style_blocks, body_inner). fragment면 통째 body로."""
    styles = re.findall(r"<style[^>]*>.*?</style>", html, re.S | re.I)
    m = re.search(r"<body[^>]*>(.*?)</body>", html, re.S | re.I)
    if m:
        body = m.group(1)
    else:
        body = re.sub(r"(?is)<!doctype.*?>|</?html[^>]*>|<head[^>]*>.*?</head>", "", html)
        body = re.sub(r"(?is)<style[^>]*>.*?</style>", "", body)
    body = body.replace("\ufeff", "").replace("\ufffd", "")
    return styles, body.strip()


def _read_csv(fn):
    import pandas as pd
    p = os.path.join(HERE, fn)
    try:
        return pd.read_csv(p, dtype=str)
    except Exception:
        return None


def summary_banner():
    import pandas as pd
    cells, take = [], []
    dv = _read_csv("decision_view_latest.csv")
    th = _read_csv("theme_heat_latest.csv")
    se = _read_csv("signal_efficacy_latest.csv")
    if th is not None and len(th):
        th2 = th.copy(); th2["hs"] = pd.to_numeric(th2["heat_score"], errors="coerce")
        top = th2.sort_values("hs", ascending=False).iloc[0]["theme"]
        scn = int((th2["supercycle"] == "True").sum())
        cells.append(f'<div class="sumcell">주도 테마<b>{top}</b></div>')
        cells.append(f'<div class="sumcell">supercycle ON<b>{scn}개</b></div>')
    if dv is not None and len(dv):
        held = dv[dv["held"] == "True"]
        buyable = (dv["entry"].isin(["돌파확인","돌파(거래량미달)","셋업"])).sum()
        near = (dv["entry"] == "트리거임박").sum()
        weak = held["verdict"].str.contains("약|부진", na=False).sum()
        cells.append(f'<div class="sumcell">돌파·셋업<b>{int(buyable)}종</b></div>')
        cells.append(f'<div class="sumcell">임박<b>{int(near)}종</b></div>')
        cells.append(f'<div class="sumcell">선별18 비주도/부진<b>{int(weak)}/{len(held)}종</b></div>')
    if se is not None and len(se):
        ser = se.set_index("signal")
        try:
            bo = float(ser.loc["진입:돌파/셋업 fwd3m","mean_fwd"]); gw = float(ser.loc["진입:관망 fwd3m","mean_fwd"])
            take.append(f"진입 신호 엣지(사후·in-sample): 돌파/셋업이 관망보다 fwd3m <b>{bo-gw:+.1f}%p</b>")
        except Exception:
            pass
        try:
            h3 = float(ser.loc["heat 상위테마 fwd3m","mean_fwd"])
            take.append(f"heat 상위테마 forward 엣지 <b>{h3:+.1f}%p</b>(≈0 → 추격 비효율)")
        except Exception:
            pass
    bar = '<div class="sumbar">' + "".join(cells) + '</div>' if cells else ""
    tk = ('<div class="sumtake">📌 ' + " · ".join(take) + ' <span style="opacity:.7">— in-sample 사후측정, 매수신호 아님</span></div>') if take else ""
    return bar + tk


def build(regen_first=True):
    status = regen() if regen_first else {o: "skip" for _, o, _ in GENS}
    all_styles, sections = [], []
    for script, out, title in GENS:
        p = os.path.join(HERE, out)
        if not os.path.exists(p):
            sections.append(f'<div class="allsec"><h2 class="secttl">{title}</h2>'
                            f'<p style="color:var(--color-text-tertiary)">산출 없음 ({status.get(out,"?")}) — {out}</p></div>')
            continue
        styles, body = extract(open(p, encoding="utf-8-sig", errors="replace").read())
        all_styles += styles
        sections.append(f'<div class="allsec"><h2 class="secttl">{title} '
                        f'<span style="font-size:11px;color:var(--color-text-tertiary)">[{status.get(out,"?")}]</span></h2>{body}</div>')
    now = datetime.datetime.now()
    date = now.strftime("%Y-%m-%d"); ts = now.strftime("%Y-%m-%d %H:%M")
    # 중복 style 제거(순서 유지)
    seen, uniq = set(), []
    for s in all_styles:
        if s not in seen:
            seen.add(s); uniq.append(s)
    html = HEAD.format(date=date, ts=ts, styles="\n".join(uniq)).replace("__BANNER__", summary_banner()) + "\n".join(sections) + "\n</body></html>\n"
    outpath = os.path.join(HERE, f"진우퀀트_통합대시보드_{date}.html")
    open(outpath, "w", encoding="utf-8").write(html)
    return outpath, status


def _selftest():
    ok = 0
    full = "<!doctype html><html><head><meta charset='utf-8'><style>.b{color:red}</style></head><body><h1>가나다</h1><p>x</p></body></html>"
    st, bd = extract(full)
    assert st and ".b{color:red}" in st[0] and "가나다" in bd and "<body" not in bd; ok += 1
    frag = "<h2 class='sr-only'>제목</h2><div>한글내용</div>"
    st2, bd2 = extract(frag)
    assert bd2.startswith("<h2") and "한글내용" in bd2; ok += 1
    out = HEAD.format(date="2026-06-30", ts="t", styles="<style>.x{}</style>")
    assert '<meta charset="utf-8">' in out and "통합 대시보드" in out; ok += 1
    print(f"✅ build_dashboard_all 셀프테스트 통과 ({ok}/3): 추출(full)·추출(fragment)·charset헤더")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--no-regen", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        _selftest(); return
    outpath, status = build(regen_first=not a.no_regen)
    print("컴포넌트:", status)
    print("산출:", os.path.basename(outpath))


if __name__ == "__main__":
    main()
