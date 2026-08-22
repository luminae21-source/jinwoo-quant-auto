# -*- coding: utf-8 -*-
r"""휩쏘_케이스빌더2.py — 케이스집 확장: 연도별 30페이지 + 종목별 14페이지 + 목차 개편.
   · 연도 페이지: 그 해 요약(건수·승률·국면 구성) + 대표 승/패 차트 + 전체 이벤트 목록
   · 종목 페이지: 그 종목의 30년 휩쏘 이력 + 최고 케이스 차트
   · 휩쏘_케이스집.html : 3부 목차(대표 8선 / 연도별 / 종목별)로 재생성
   실행 순서: 휩쏘_고점분석.py → 휩쏘_케이스빌더.py → 이 파일
"""
import os, sys, gc, importlib.util, warnings, html as H
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

YEAR_NOTE = {
    1997: "IMF 외환위기 발발", 1998: "IMF 바닥과 회복", 1999: "닷컴 버블", 2000: "닷컴 붕괴 — 30년 최악",
    2001: "9·11 · 붕괴 마무리", 2002: "카드 버블", 2003: "카드 사태 바닥", 2004: "차이나 쇼크",
    2005: "대세 상승", 2006: "상승 지속", 2007: "버블 정점", 2008: "글로벌 금융위기",
    2009: "V자 회복", 2010: "회복 지속", 2011: "유럽 재정위기·미국 신용강등", 2012: "박스권",
    2013: "버냉키 쇼크·박스권", 2014: "박스권", 2015: "메르스·위안화 쇼크", 2016: "브렉시트·탄핵 정국",
    2017: "반도체 슈퍼사이클", 2018: "미중 무역전쟁", 2019: "일본 수출규제", 2020: "코로나 폭락과 V반등 — 30년 최고",
    2021: "유동성 정점", 2022: "금리 인상 약세장", 2023: "2차전지 쏠림", 2024: "8월 블랙먼데이·밸류업",
    2025: "회복", 2026: "7월 대휩쏘 (진행중)",
}
STOCK_PICKS = ["000660", "009540", "011200", "011170", "000720", "034020",
               "000150", "006400", "009150", "247540",
               "005930", "353200", "222800", "042700"]   # 상위 다빈도 + 형 관심 4종


def _load_mod(fn, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fn))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


B1 = _load_mod("휩쏘_케이스빌더.py", "b1")     # svg_chart · CSS · 재무로더 재사용
hz = _load_mod("휩쏘_역사검정.py", "hz")
FIN = B1.load_fin()

# 지수 거래일 달력 — 청산일(월) 근사용
_ix = pd.read_csv(os.path.join(HERE, "kospi_index_daily.csv"))
_ix.columns = [c.strip().lstrip("﻿") for c in _ix.columns]
IXD = np.sort(_ix["Date"].astype(str).values)

def exit_month(d0, bars):
    i = int(np.searchsorted(IXD, d0, side="left"))
    j = i + int(bars)
    return f"{int(IXD[j][5:7])}월" if 0 <= j < len(IXD) else "-"

def fin_cells(code, d0):
    f = B1.fin_asof(FIN, code, d0)
    if not f or d0 < "2002-02": return "<td class=n>-</td><td class=n>-</td>"
    per = "적자" if (not np.isfinite(f["PER"]) or f["PER"] == 0) else f"{f['PER']:.1f}"
    pbr = "-" if (not np.isfinite(f["PBR"]) or f["PBR"] == 0) else f"{f['PBR']:.2f}"
    return f"<td class=n>{per}</td><td class=n>{pbr}</td>"


def load_series(codes):
    out = {}
    dt = {"code": str, "open": "float32", "high": "float32", "low": "float32",
          "close": "float32", "volume": "float32"}
    remain = set(codes)
    for mk in ("KOSPI", "KOSDAQ"):
        if not remain: break
        D = pd.read_csv(os.path.join(DATA, f"종목일봉_30년_{mk}.csv"), dtype=dt)
        D.columns = [x.strip().lstrip("﻿") for x in D.columns]
        D["code"] = D["code"].str.zfill(6)
        D = D[D["code"].isin(remain)]
        for code, g in D.groupby("code"):
            g = g.sort_values("date").reset_index(drop=True)
            g = g[~((g["open"] == 0) & (g["volume"] == 0))].reset_index(drop=True)
            if len(g) < 260: continue
            dts = g["date"].values.astype(str)
            o = g["open"].values.astype(float); h = g["high"].values.astype(float)
            l = g["low"].values.astype(float); c = g["close"].values.astype(float)
            v = g["volume"].values.astype(float)
            o, h, l, c, _ = hz.back_adjust(o, h, l, c, v, dts)
            s = pd.Series(c, index=pd.to_datetime(dts))
            ma240 = pd.Series(c).rolling(240, min_periods=240).mean().values
            wk = s.resample("W-FRI").last().dropna().rolling(60, min_periods=60).mean()
            mo = s.resample("ME").last().dropna().rolling(10, min_periods=10).mean()
            w_d = wk.reindex(s.index.union(wk.index)).ffill().reindex(s.index).values
            m_d = mo.reindex(s.index.union(mo.index)).ffill().reindex(s.index).values
            out[code] = dict(dts=dts, o=o, h=h, l=l, c=c, ma240=ma240, w60=w_d, m10=m_d)
            remain.discard(code)
        del D; gc.collect()
    return out


def make_ev(S, row):
    """차트용 ev dict — 케이스빌더와 동일 규칙으로 손절/목표 재구성."""
    pos = {d: i for i, d in enumerate(S["dts"])}
    t = pos.get(row["출발일"])
    if t is None or t < 2: return None, None
    entry = S["c"][t]
    cum2 = entry / S["c"][t - 2] - 1
    lines = {"주60주": S["w60"][t], "월10": S["m10"][t], "일240": S["ma240"][t]}
    fin = {k: v for k, v in lines.items() if np.isfinite(v)}
    if not fin: return None, None
    keyl = min(fin, key=lambda k: abs(entry / fin[k] - 1)); kv = fin[keyl]
    if str(row["유형"]) == "A":
        pre = entry / (1 + cum2); target = entry + (pre - entry) * 0.5
        below = kv if kv < entry else S["l"][t]; stop = below * 0.95
    else:
        target = float(np.max(S["h"][max(0, t - 59):t + 1]))
        below = kv if kv < entry else S["l"][t]; stop = below * 0.97
    peak = float(row["고점6M"]) if pd.notna(row["고점6M"]) else np.nan
    ev = dict(date=row["출발일"], entry=entry, stop=stop, target=target,
              exret=float(row["ex_ret"]), exbars=int(row["ex_bars"]),
              peak=peak, pkdays=int(row["고점일수"]) if pd.notna(row["고점일수"]) else None,
              peakpx=entry * (1 + peak / 100) if np.isfinite(peak) else None)
    return t, ev


def esc(x): return H.escape(str(x))


def event_table(df):
    rows = ""
    for _, r in df.iterrows():
        ex = float(r["ex_ret"]) * 100
        cl = "good" if ex > 0 else "bad"
        rg = str(r["국면"]); chip = {"실행": "cG", "주의": "cO", "관찰만": "cR"}.get(rg, "cM")
        pk = f"{r['고점6M']:+.1f}%" if pd.notna(r["고점6M"]) else "-"
        pkm = f"{int(r['고점월'])}월" if pd.notna(r.get("고점월")) else "-"
        rows += (f"<tr><td>{r['출발일']}</td><td>{esc(r['name'])} <span style='color:var(--mut);font-size:11px'>{r['code']}</span></td>"
                 f"<td>{esc(r['유형'])}{esc(r['등급']) if pd.notna(r['등급']) else ''}</td>"
                 f"<td><span class='chip {chip}' style='font-size:11px;padding:1px 8px'>{esc(rg)}</span></td>"
                 f"{fin_cells(r['code'], str(r['출발일']))}"
                 f"<td class='n {cl}'><b>{ex:+.1f}%</b></td>"
                 f"<td class=n>{esc(r['ex_how'])} {int(r['ex_bars'])}일·{exit_month(str(r['출발일']), r['ex_bars'])}</td>"
                 f"<td class=n>{pk}<span style='color:var(--mut);font-size:11px'> {pkm}</span></td></tr>")
    return ("<table><tr><th>출발일</th><th>종목</th><th>유형</th><th>국면</th>"
            "<th>PER</th><th>PBR</th>"
            "<th>카드수익</th><th>청산(월)</th><th>6M고점(월)</th></tr>" + rows + "</table>"
            "<p class=warn style='margin-top:2px'>PER·PBR = 진입 시점 KRX 월말 기준(2002-01 이전 미제공 · 적자=PER 0) · 청산월은 지수 거래일 달력 기준 근사</p>")


def chart_block(S, row, label):
    t, ev = make_ev(S, row)
    if t is None: return f"<p class=warn>({label} 차트 생략 — 데이터 부족)</p>"
    ch = B1.svg_chart(S, t, ev)
    ex = float(row["ex_ret"]) * 100; cl = "good" if ex > 0 else "bad"
    pk = f" · 6M고점 <b class=good>{row['고점6M']:+.1f}%</b>({int(row['고점일수'])}일)" if pd.notna(row["고점6M"]) else ""
    return (f"<h3 style='margin:20px 0 4px'>{label} — {esc(row['name'])} {row['출발일']}"
            f" <span class='{cl}'>{ex:+.1f}%</span><span style='color:var(--mut);font-size:12px'>({esc(row['ex_how'])} {int(row['ex_bars'])}일{pk})</span></h3>{ch}")


def year_stats_line(d):
    m = d.dropna(subset=["ex_ret"])
    if not len(m): return "표본 없음"
    ex = pd.to_numeric(m["ex_ret"], errors="coerce") * 100
    f40 = pd.to_numeric(m["fwd40"], errors="coerce") * 100
    rg = d["국면"].value_counts()
    rgs = " · ".join(f"{k} {v}" for k, v in rg.items())
    s = f"{len(d)}건 · 카드 평균 {ex.mean():+.1f}% · 승률 {(ex>0).mean()*100:.0f}%"
    if f40.notna().any(): s += f" · 40일 평균 {f40.mean():+.1f}%"
    return s + f" · 국면: {rgs}"


def main():
    G = pd.read_csv(os.path.join(HERE, "휩쏘_고점_이벤트.csv"), dtype={"code": str})
    G["code"] = G["code"].str.zfill(6)
    G["y"] = G["출발일"].str[:4].astype(int)
    G["named"] = G["name"] != G["code"]

    # 대표 승/패 선정 (연도별) + 종목페이지 최고 케이스 → 필요한 코드 수집
    reps = {}
    for y, d in G.groupby("y"):
        m = d.dropna(subset=["ex_ret"]).copy()
        if not len(m): continue
        mn = m[m["named"]] if m["named"].sum() >= 2 else m
        reps[y] = (mn.loc[mn["ex_ret"].idxmax()], mn.loc[mn["ex_ret"].idxmin()])
    need = set()
    for y, (w, l) in reps.items(): need |= {w["code"], l["code"]}
    best = {}
    for c in STOCK_PICKS:
        d = G[(G["code"] == c)].dropna(subset=["고점6M"])
        if len(d): best[c] = d.loc[d["고점6M"].idxmax()]
        need.add(c)
    print(f"차트 대상 코드 {len(need)}개 — 시계열 로딩…", flush=True)
    S = load_series(need)
    print(f"  로딩 완료 {len(S)}종", flush=True)

    years = sorted(reps.keys())
    # ── 연도별 페이지
    for y in years:
        d = G[G["y"] == y].sort_values("출발일")
        w, l = reps[y]
        wb = chart_block(S[w["code"]], w, "대표 승리") if w["code"] in S else ""
        lossl = "대표 패배" if float(l["ex_ret"]) < 0 else "최소 수익"
        lb = chart_block(S[l["code"]], l, lossl) if (l["code"] in S and l["code"] != w["code"] or str(l["출발일"]) != str(w["출발일"])) else ""
        py_, ny_ = (y - 1 if y - 1 in reps else None), (y + 1 if y + 1 in reps else None)
        nav = "<div class=nav>" + (f"<a href='휩쏘_연도_{py_}.html'>← {py_}</a>" if py_ else "<span></span>")
        nav += "<a href='휩쏘_케이스집.html'>목차</a>"
        nav += (f"<a href='휩쏘_연도_{ny_}.html'>{ny_} →</a>" if ny_ else "<span></span>") + "</div>"
        doc = f"""<!DOCTYPE html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>휩쏘 {y}년</title><style>{B1.CSS}</style></head><body><div class=w>
<h1>{y}년 — {YEAR_NOTE.get(y,'')}</h1>
<p class=sub>{year_stats_line(d)}</p>
{wb}{lb}
<h3 style='margin:24px 0 6px'>그 해 전체 이벤트 · {len(d)}건</h3>
{event_table(d)}
{nav}
<p class=warn>⚠️ 백조정 가격 · 검정·기록용. 대표 승/패는 그 해 카드수익 최대/최소(종목명 확인분 우선).</p>
</div></body></html>"""
        open(os.path.join(HERE, f"휩쏘_연도_{y}.html"), "w", encoding="utf-8").write(doc)
    print(f"  ✓ 연도 페이지 {len(years)}개")

    # ── 종목별 페이지
    snames = {}
    for c in STOCK_PICKS:
        d = G[G["code"] == c].sort_values("출발일")
        if not len(d) or c not in S: continue
        nm = d["name"].iloc[-1]; snames[c] = nm
        bb = chart_block(S[c], best[c], "최고 케이스") if c in best else ""
        ex = pd.to_numeric(d["ex_ret"], errors="coerce").dropna() * 100
        stat = (f"{len(d)}회 포착 · 카드 평균 {ex.mean():+.1f}% · 승률 {(ex>0).mean()*100:.0f}%"
                f" · 최고 6M고점 {pd.to_numeric(d['고점6M'],errors='coerce').max():+.1f}%")
        doc = f"""<!DOCTYPE html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>휩쏘 종목 · {nm}</title><style>{B1.CSS}</style></head><body><div class=w>
<h1>{esc(nm)} <span style='color:var(--mut);font-weight:400;font-size:15px'>{c}</span></h1>
<p class=sub>30년 휩쏘 이력 — {stat}</p>
{bb}
<h3 style='margin:24px 0 6px'>전체 이벤트 · {len(d)}건</h3>
{event_table(d)}
<div class=nav><span></span><a href='휩쏘_케이스집.html'>목차</a><span></span></div>
<p class=warn>⚠️ 백조정 가격 · 검정·기록용. 같은 종목이 반복 포착되는 것 자체가 '흔들리는 주도주' 후보라는 신호.</p>
</div></body></html>"""
        open(os.path.join(HERE, f"휩쏘_종목_{nm.replace('/','_')}.html"), "w", encoding="utf-8").write(doc)
    print(f"  ✓ 종목 페이지 {len(snames)}개")

    # ── 목차 3부 재생성
    rep8 = ""
    for c in B1.CASES:
        rep8 += (f"<a class=card href='휩쏘_케이스_{c['no']}_{c['파일']}.html'>"
                 f"<span class=t>{c['no']}. {c['name']} · {c['date'][:7]} — {c['tag']}</span>"
                 f"<div class=d>{c['era']}</div></a>")
    ycards = ""
    for y in years:
        d = G[G["y"] == y]
        ex = pd.to_numeric(d["ex_ret"], errors="coerce").dropna() * 100
        cl = "good" if ex.mean() > 0 else "bad"
        ycards += (f"<a class=card style='margin:4px 0;padding:9px 14px' href='휩쏘_연도_{y}.html'>"
                   f"<span class=t>{y} <span style='font-weight:400;color:var(--mut);font-size:12px'>{YEAR_NOTE.get(y,'')}</span></span>"
                   f"<div class=d>{len(d)}건 · 카드 <span class='{cl}'>{ex.mean():+.1f}%</span> · 승률 {(ex>0).mean()*100:.0f}%</div></a>")
    scards = ""
    for c, nm in snames.items():
        d = G[G["code"] == c]
        ex = pd.to_numeric(d["ex_ret"], errors="coerce").dropna() * 100
        scards += (f"<a class=card style='margin:4px 0;padding:9px 14px' href='휩쏘_종목_{nm.replace('/','_')}.html'>"
                   f"<span class=t>{esc(nm)}</span><div class=d>{len(d)}회 · 카드 {ex.mean():+.1f}% · 승률 {(ex>0).mean()*100:.0f}%</div></a>")
    idx = f"""<!DOCTYPE html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>휩쏘 케이스집</title><style>{B1.CSS}
.grid{{display:grid;grid-template-columns:repeat(auto-fill,minmax(240px,1fr));gap:4px 10px}}
h2{{font-size:17px;margin:28px 0 8px;padding-top:12px;border-top:2px solid var(--bd)}}</style></head><body><div class=w>
<h1>휩쏘 케이스집</h1>
<p class=sub>30년 역사원장 2,801건 — 대표 8선 · 연도별 30페이지 · 종목별 {len(snames)}페이지</p>
<h2>1부 — 대표 8선 (시대·국면·승패 엄선 · 상세 해설)</h2>
{rep8}
<h2>2부 — 연도별 (그 해 요약 + 대표 승/패 차트 + 전체 목록)</h2>
<div class=grid>{ycards}</div>
<h2>3부 — 종목별 (다빈도 + 관심 종목의 30년 휩쏘 이력)</h2>
<div class=grid>{scards}</div>
<p class=warn>⚠️ 검정·기록용. 갱신: py 휩쏘_고점분석.py → py 휩쏘_케이스빌더.py → py 휩쏘_케이스빌더2.py</p>
</div></body></html>"""
    open(os.path.join(HERE, "휩쏘_케이스집.html"), "w", encoding="utf-8").write(idx)
    print("  ✓ 휩쏘_케이스집.html (3부 목차)")


if __name__ == "__main__":
    main()
