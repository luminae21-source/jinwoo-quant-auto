#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""overseas_corr.py — [PC] 한국 종목 vs 미국·홍콩 동종업체 월간수익률 상관

테마별로 한국 대표주와 해외(미국·홍콩) 동종업체의 월간수익률 상관(Pearson)을 계산.
높은 상관 = 그 한국 종목이 글로벌 피어와 함께 움직임 → 해외 피어를 선행지표로 참고 가능.
데이터: 한국=_월봉종가캐시(보유) · 해외=yfinance(미국 티커·홍콩 XXXX.HK).
사용: py overseas_corr.py            (해외상관.html/json 생성)
      py overseas_corr.py --self-test
※ yfinance 필요(해외상관_실행.bat이 자동 설치) · 네트워크는 PC. 국가간 시차·통화 미보정(수익률 상관은 무관).
⚠️ 정보·검증용·미래보장 아님. 투자자문 아님·책임 본인.
"""
import os as _os2
def _jqroot2():
    """프로젝트 루트 자동탐색 (2026-07-27 §5b)."""
    d=_os2.path.dirname(_os2.path.abspath(__file__))
    for _ in range(5):
        if _os2.path.exists(_os2.path.join(d,"종목시총_30년.csv")): return d
        d=_os2.path.dirname(d)
    return _os2.path.dirname(_os2.path.abspath(__file__))


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

import os, sys, json
import numpy as np, pandas as pd
BASE=os.path.dirname(os.path.abspath(__file__)); UP= _jqroot2()
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
def _find(fn):
    for d in (BASE,os.path.dirname(BASE),UP,os.path.join(UP,"강화키트")):
        p=os.path.join(d,fn)
        if os.path.exists(p): return p
    return None

# 테마: 한국 대표주(code:name) ↔ 해외 피어(ticker:name). US=심볼, HK=번호.HK
THEMES={
 "반도체": {"kr":{"005930":"삼성전자","000660":"SK하이닉스","042700":"한미반도체"},
           "os":{"TSM":"TSMC","NVDA":"엔비디아","MU":"마이크론","ASML":"ASML","0981.HK":"SMIC(홍콩)"}},
 "2차전지":{"kr":{"006400":"삼성SDI","373220":"LG에너지","086520":"에코프로"},
           "os":{"TSLA":"테슬라","1211.HK":"BYD(홍콩)","PANL":"","QS":"퀀텀스케이프"}},
 "자동차": {"kr":{"005380":"현대차","000270":"기아"},
           "os":{"TM":"도요타","GM":"GM","0175.HK":"길리(홍콩)"}},
 "인터넷": {"kr":{"035420":"NAVER","035720":"카카오"},
           "os":{"GOOGL":"구글","META":"메타","9988.HK":"알리바바(홍콩)","0700.HK":"텐센트(홍콩)"}},
 "바이오": {"kr":{"207940":"삼성바이오","068270":"셀트리온"},
           "os":{"LLY":"일라이릴리","AMGN":"암젠"}},
 "조선/방산":{"kr":{"329180":"HD현대중공업","012450":"한화에어로"},
           "os":{"RTX":"RTX","LMT":"록히드마틴"}},
}

def kr_monthly_returns(codes):
    fr=[]
    for f in ("_월봉종가캐시_KOSPI.csv","_월봉종가캐시_KOSDAQ.csv"):
        p=_find(f)
        if p: d=pd.read_csv(p,dtype={"code":str}); d["code"]=d["code"].str.zfill(6); fr.append(d)
    if not fr: return pd.DataFrame()
    px=pd.concat(fr).pivot_table(index="ym",columns="code",values="close",aggfunc="last").sort_index()
    px=px[[c for c in codes if c in px.columns]]
    return px.pct_change(fill_method=None)

def os_monthly_returns(tickers):
    try:
        import yfinance as yf
    except ImportError:
        print("yfinance 미설치 → pip install yfinance"); return pd.DataFrame()
    tk=[t for t in tickers if t]
    if not tk: return pd.DataFrame()
    try:
        df=yf.download(tk, period="6y", interval="1mo", auto_adjust=True, progress=False)
        close=df["Close"] if "Close" in df else df
        if isinstance(close, pd.Series): close=close.to_frame(tk[0])
        close.index=pd.to_datetime(close.index).strftime("%Y-%m")
        close=close.groupby(level=0).last()
        return close.pct_change(fill_method=None)
    except Exception as e:
        print("yfinance 다운로드 오류:",e); return pd.DataFrame()

def run():
    rows=[]; report={}
    for theme,mp in THEMES.items():
        krr=kr_monthly_returns(list(mp["kr"].keys()))
        osr=os_monthly_returns(list(mp["os"].keys()))
        if krr.empty or osr.empty:
            print(f"[{theme}] 데이터 부족 — 건너뜀"); continue
        idx=[m for m in krr.index if m in osr.index]
        krr=krr.reindex(idx); osr=osr.reindex(idx)
        print(f"\n=== {theme} (공통 {len(idx)}개월) ===")
        tr={}
        for kc,kn in mp["kr"].items():
            if kc not in krr.columns: continue
            best=(None,-2)
            line=[]
            for tk,tn in mp["os"].items():
                if not tk or tk not in osr.columns: continue
                a=krr[kc]; b=osr[tk]; m=a.notna()&b.notna()
                if m.sum()<12: continue
                c=float(a[m].corr(b[m]))
                line.append((tn or tk,round(c,2)))
                if c>best[1]: best=(tn or tk,round(c,2))
            if line:
                tr[kn]={"peers":line,"best":best}
                bstr=", ".join(f"{n} {v:+.2f}" for n,v in sorted(line,key=lambda x:-x[1]))
                print(f"  {kn:<12} 최고동조: {best[0]} {best[1]:+.2f} | {bstr}")
        report[theme]=tr
    if not report:
        print("생성할 상관 없음 (yfinance/네트워크 확인)."); return
    json.dump(report,open(os.path.join(BASE,"해외상관_결과.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2,default=str)
    _html(report)
    print("\n저장: 해외상관.html · 해외상관_결과.json")

def _html(report):
    cards=""
    for theme,tr in report.items():
        rows=""
        for kn,d in tr.items():
            peers=" · ".join(f"{n} <b>{v:+.2f}</b>" for n,v in sorted(d["peers"],key=lambda x:-x[1]))
            b=d["best"]; bc="#16a34a" if b[1]>=0.6 else ("#e0a32e" if b[1]>=0.4 else "#9fb0c9")
            rows+=f"<tr><td class=nm>{kn}</td><td style='color:{bc};font-weight:700'>{b[0]} {b[1]:+.2f}</td><td class=note>{peers}</td></tr>"
        cards+=f"<div class=card><h3>{theme}</h3><table><thead><tr><th>한국</th><th>최고 동조 해외피어</th><th>전체</th></tr></thead><tbody>{rows}</tbody></table></div>"
    html=f"""<!doctype html><html lang=ko><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>한국-해외 상관</title><style>
:root{{--bg:#0b1020;--card:#141b2e;--ink:#e8edf6;--sub:#9fb0c9;--line:#243149;--acc:#5b9dff}}
@media(prefers-color-scheme:light){{:root{{--bg:#f4f6fb;--card:#fff;--ink:#0f1830;--sub:#5a6a86;--line:#e3e9f4;--acc:#2563eb}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,'Segoe UI',Roboto,'Malgun Gothic',sans-serif;padding:22px;line-height:1.5}}
.wrap{{max-width:900px;margin:0 auto}}h1{{font-size:20px;margin:0 0 4px}}h3{{font-size:14.5px;margin:0 0 9px;color:var(--acc)}}
.sub{{color:var(--sub);font-size:12.5px;margin-bottom:14px}}.card{{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:15px 16px;margin-bottom:12px}}
table{{width:100%;border-collapse:collapse;font-size:12.5px}}th,td{{padding:7px 6px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}}
th{{color:var(--sub);font-weight:600;font-size:10.5px}}.nm{{font-weight:600}}.note{{color:var(--sub);font-size:11.5px}}
.warn{{color:#e0a32e;font-size:11.5px;margin-top:8px}}
</style></head><body><div class=wrap>
<h1>한국 종목 ↔ 미국·홍콩 동종업체 상관</h1>
<div class=sub>월간수익률 Pearson 상관(최근 ~6년 공통구간) · 초록 ≥0.6 강동조 · 노랑 0.4~0.6 · 높을수록 글로벌 피어와 함께 움직임(선행지표 참고)</div>
{cards}
<div class=card><div class=note>해외 피어가 먼저 크게 움직이면 같은 테마 한국주도 따라갈 가능성(상관이 높을 때). 단 상관≠인과, 시차·통화 미보정. 진입은 여전히 국내 추세·규칙 기준.</div>
<div class=warn>⚠️ 정보·검증용·과거통계. 미래보장 아님. 투자자문 아님·책임 본인.</div></div>
</div></body></html>"""
    open(os.path.join(BASE,"해외상관.html"),"w",encoding="utf-8").write(html)

def _selftest():
    ok=tot=0
    def chk(n,c):
        nonlocal ok,tot; tot+=1; ok+=1 if c else 0; print(f"  [{'OK' if c else 'FAIL'}] {n}")
    a=pd.Series([0.1,-0.05,0.2,0.0,0.15,-0.1]); b=a*1.0
    chk("동일 시계열 상관=1", abs(a.corr(b)-1.0)<1e-9)
    chk("반대 시계열 상관=-1", abs(a.corr(-a)+1.0)<1e-9)
    chk("THEMES 구조", all("kr" in v and "os" in v for v in THEMES.values()))
    print(f"\n셀프테스트: {ok}/{tot}"); return ok==tot

def main():
    if "--self-test" in sys.argv: sys.exit(0 if _selftest() else 1)
    run()

if __name__=="__main__":
    main()
