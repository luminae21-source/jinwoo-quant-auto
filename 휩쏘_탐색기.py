# -*- coding: utf-8 -*-
r"""휩쏘_탐색기.py — 일봉 휩쏘 재진입 자리 탐지 (작업2, 2026-08-01 · A/B 두 유형)

[두 유형 — 기준분석에서 갈렸다. 기계적으로 완전히 다른 신호다.]
  A 선지지형 : MA240 근처/아래 + 깊은 2일 플러시(누적 ≤ -12%) + 장기선 지지.
               얻어맞은 옛 주도주가 1년 구조 바닥을 되찾는 자리. (대덕·심텍·피에스케이홀딩스)
  B 리더형   : 추세 상단(MA240 위 +N%) + 얕은 플러시(누적 ≤ -3%) + 대장주.
               안 빠진 대장이 얕게 눌렸다 지수를 끄는 자리. (삼성전자·SK하이닉스)
  → 하나로 뭉치면 둘 다 놓친다. A는 '얼마나 깊이 빠졌나', B는 '대장이 얕게 눌렸나'.

[급락 구조 · 왜 2일째] 급락1=D-2→D-1, 급락2=D-1→D(오늘=2일째=진입일).
                       1일째는 바닥을 모른다. 2일째 종가에서 판단한다. 일봉에서만 보인다.

[자체검증] py 휩쏘_탐색기.py --date 20260730 --near 11
           → A에 대덕·심텍·피에스케이홀딩스·삼화콘덴서, B에 삼성전자·SK하이닉스가 떠야 정상.

사용: py 휩쏘_탐색기.py                        (오늘 · A+B)
      py 휩쏘_탐색기.py --mode A               (선지지형만)
      py 휩쏘_탐색기.py --mode B               (리더형만)
      py 휩쏘_탐색기.py --date 20260730 --near 11
      py 휩쏘_탐색기.py --code 005930
출력: 휩쏘탐지_YYYYMMDD.csv  (유형·등급·품질·테마 포함, 전 종목)
⚠️ 예외적 자리용. 표본 소수 — 검정된 규칙 아님. 형 직관의 좌표화. 결정·책임 본인.
"""
import os, sys, argparse, warnings, webbrowser, subprocess, html as _htmlmod
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

PX_FLOOR = 1000
NEAR_HIGH, VOL_MULT, WICK_MIN, BODY_SMALL = 0.90, 2.0, 0.03, 0.02
CHAIN = ["반도체", "특수 목적용 기계", "전자부품", "측정, 시험", "광학",
         "그외 기타 전문, 과학", "통신 및 방송 장비", "일반 목적용 기계", "전지"]


def is_chain(sec): return any(k in str(sec) for k in CHAIN)


def fmt_mcap(v):
    if not (isinstance(v, (int, float)) and np.isfinite(v)): return "-"
    return f"{v/1e12:.1f}조" if v >= 1e12 else f"{v/1e8:,.0f}억"


def dw(t, n, right=False):
    import unicodedata
    t = str(t)
    g = lambda s: sum(2 if unicodedata.east_asian_width(c) in "WF" else 1 for c in s)
    while g(t) > n: t = t[:-1]
    return (" " * max(0, n - g(t)) + t) if right else t + " " * max(0, n - g(t))


def _find(fn):
    for d in (HERE, os.path.join(HERE, "데이터수리"), os.path.dirname(HERE), os.getcwd()):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    return None


def load():
    fr = []
    for m in ("KOSPI", "KOSDAQ"):
        p = _find(f"_일봉OHLCV_{m}_adj.csv")
        if p:
            d = pd.read_csv(p, dtype={"code": str}); d["mkt"] = m; fr.append(d)
    if not fr: sys.exit("❌ _일봉OHLCV_*_adj.csv 없음")
    D = pd.concat(fr, ignore_index=True); D["code"] = D["code"].str.zfill(6)
    amax = D["date"].max(); add = []
    for m in ("KOSPI", "KOSDAQ"):
        rp = _find(f"종목일봉_30년_{m}.csv")
        if not rp: continue
        try: raw = pd.read_csv(rp, dtype={"code": str})
        except Exception: continue
        if not {"date","code","open","high","low","close","volume"}.issubset(raw.columns): continue
        raw = raw[raw["date"] > amax]
        if len(raw):
            raw = raw.copy(); raw["code"] = raw["code"].astype(str).str.zfill(6); raw["mkt"] = m
            add.append(raw[["code","date","open","high","low","close","volume","mkt"]])
    if add: D = pd.concat([D] + add, ignore_index=True)
    return D.drop_duplicates(["code","date"], keep="last").sort_values(["code","date"]).reset_index(drop=True)


def profile(g, asof, near):
    g = g[g["date"] <= asof]
    if len(g) < 260: return None
    # §8-2 방어 (2026-08-04): 마지막 봉 ≠ asof 이면 상폐·거래정지 종목 — 허위 신호 차단
    if str(g["date"].iloc[-1]) != str(asof): return None
    dts = pd.to_datetime(g["date"].values)
    cl = g["close"].values.astype(float); hi = g["high"].values.astype(float)
    lo = g["low"].values.astype(float); op = g["open"].values.astype(float)
    vo = g["volume"].values.astype(float)
    px = cl[-1]
    if px < PX_FLOOR or len(cl) < 3: return None

    r1 = cl[-2] / cl[-3] - 1
    r2 = cl[-1] / cl[-2] - 1
    cum2 = (1 + r1) * (1 + r2) - 1

    s = pd.Series(cl, index=dts)
    wk = s.resample("W-FRI").last().dropna(); mo = s.resample("ME").last().dropna()
    lines = {
        "주60주": float(wk.tail(60).mean()) if len(wk) >= 60 else np.nan,
        "월10":  float(mo.tail(10).mean()) if len(mo) >= 10 else np.nan,
        "일240": float(np.mean(cl[-240:])) if len(cl) >= 240 else np.nan,
    }
    ma60v = float(np.mean(cl[-60:])) if len(cl) >= 60 else np.nan
    ma240v = lines["일240"]
    gap240 = (px / ma240v - 1) if (ma240v and np.isfinite(ma240v)) else np.nan
    gap60 = (px / ma60v - 1) if (ma60v and np.isfinite(ma60v)) else np.nan

    zlow = lo[-1]
    dist = {k: (px / v - 1) for k, v in lines.items() if v and np.isfinite(v)}
    if not dist: return None
    key = min(dist, key=lambda k: abs(dist[k])); kd = dist[key]
    held = [k for k, v in lines.items() if v and np.isfinite(v) and zlow <= v <= px * 1.002]
    nearby = [k for k, v in dist.items() if abs(v) <= near]

    hi5 = float(np.max(hi[-1250:])) if len(hi) >= 1250 else float(np.max(hi))
    hi252 = pd.Series(hi).rolling(252, min_periods=120).max().values
    volma = pd.Series(vo).rolling(60, min_periods=40).mean().values
    body = cl / np.where(op > 0, op, np.nan) - 1
    wick = (hi - np.maximum(op, cl)) / np.where(hi > 0, hi, np.nan)
    sig = ((cl >= hi252 * NEAR_HIGH) & (vo >= volma * VOL_MULT)
           & (wick >= WICK_MIN) & (body <= BODY_SMALL))
    amt20 = float(np.mean((cl * vo)[-20:]))
    lowwick = (min(op[-1], cl[-1]) - lo[-1]) / px if px else np.nan

    return {"급락1": r1, "급락2": r2, "2일누적": cum2, "핵심선": key, "핵심선거리": kd,
            "지지": ", ".join(held), "근접": ", ".join(nearby), "겹침": len(nearby),
            "고점5년比": (px / hi5 - 1 if hi5 else np.nan),
            "이격MA240": gap240, "이격MA60": gap60,
            "오늘아래꼬리": lowwick, "거래대금20": amt20,
            "고점매도신호": int(np.nansum(sig[-10:])), "종가": px}


def grade_of(p, chain):
    d = abs(p["핵심선거리"])
    if p["지지"]: g = "A"
    elif d <= 0.03: g = "B"
    else: g = "C"
    q = 0
    q += 3 * (len(p["지지"].split(", ")) if p["지지"] else 0)
    q += 2 if d <= 0.03 else (1 if d <= 0.06 else 0)
    q += max(0, p["겹침"] - 1)
    q += 2 if p["2일누적"] <= -0.18 else (1 if p["2일누적"] <= -0.14 else 0)
    q += 1 if chain else 0
    q += 1 if (np.isfinite(p["오늘아래꼬리"]) and p["오늘아래꼬리"] >= 0.03) else 0
    return g, q


def write_html(RA, RB, asof, chain_n, total, out_html, regime_line=None):
    """탐지 결과를 자체완결 HTML로 — 매일 자동 생성·팝업."""
    esc = _htmlmod.escape
    def pct(v, s=True):
        return (f"{v*100:+.1f}%" if s else f"{v*100:.1f}%") if pd.notna(v) else "-"
    def mc(v):
        return (f"{v/1e12:.1f}조" if v >= 1e12 else f"{v/1e8:,.0f}억") if pd.notna(v) else "-"
    def vcell(r):
        v = str(r.get("밸류", "") or "")
        return f"<td style='color:var(--good);font-size:11.5px;font-weight:650'>{esc(v)}</td>" if v else "<td class=c>-</td>"
    def arow(r):
        return (f"<tr><td>{esc(str(r['name']))} <span class=c>{r['code']}</span></td>"
                f"<td>{esc(str(r['테마']))}</td>{vcell(r)}<td class=n>{r['종가']:,.0f}</td>"
                f"<td class=n>{pct(r['급락1'])}</td><td class=n>{pct(r['급락2'])}</td>"
                f"<td class=n><b>{pct(r['2일누적'])}</b></td>"
                f"<td>{esc(str(r['핵심선']))} {pct(r['핵심선거리'])}</td>"
                f"<td>{esc(r['지지']) if isinstance(r['지지'],str) and r['지지'] else '-'}</td>"
                f"<td class=n>{pct(r['고점5년比'],False) if pd.notna(r['고점5년比']) else '-'}</td>"
                f"<td class=n>{mc(r['mcap'])}</td></tr>")
    def brow(r):
        return (f"<tr><td>{esc(str(r['name']))} <span class=c>{r['code']}</span></td>"
                f"<td>{esc(str(r['테마']))}</td>{vcell(r)}<td class=n>{r['종가']:,.0f}</td>"
                f"<td class=n><b>{pct(r['2일누적'])}</b></td>"
                f"<td class=n>{pct(r['이격MA240'])}</td>"
                f"<td>{esc(str(r['핵심선']))} {pct(r['핵심선거리'])}</td>"
                f"<td class=n>{pct(r['고점5년比'],False) if pd.notna(r['고점5년比']) else '-'}</td>"
                f"<td class=n>{mc(r['mcap'])}</td></tr>")
    gc = RA["등급"].value_counts() if len(RA) else {}
    ablocks = ""
    ahead = ("<tr><th>종목</th><th>테마</th><th>밸류</th><th>종가</th><th>급락1</th><th>급락2</th>"
             "<th>2일누적</th><th>핵심선·거리</th><th>지지</th><th>5년比</th><th>시총</th></tr>")
    for gg, gname in (("A", "A급 · 선을 실제로 밟음(지지)"), ("B", "B급 · 선에 밀착 ±3%"),
                      ("C", "C급 · 근접(기관이 밀었을 수 있음·관찰)")):
        sub = RA[RA["등급"] == gg] if len(RA) else RA
        if len(sub) == 0: continue
        rows = "".join(arow(r) for _, r in sub.iterrows())
        ablocks += (f"<h3><span class='g g{gg}'>{gg}</span> {gname} · {len(sub)}종</h3>"
                    f"<table>{ahead}{rows}</table>")
    bblock = ""
    if len(RB):
        bhead = ("<tr><th>종목</th><th>테마</th><th>밸류</th><th>종가</th><th>2일누적</th>"
                 "<th>MA240이격</th><th>핵심선·거리</th><th>5년比</th><th>시총</th></tr>")
        rows = "".join(brow(r) for _, r in RB.iterrows())
        bblock = (f"<h3><span class='g gL'>B</span> 리더형 · 추세 상단 대장주 얕은 눌림 · {len(RB)}종</h3>"
                  f"<table>{bhead}{rows}</table>")
    na = len(RA); nb = len(RB)
    doc = f"""<!DOCTYPE html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>휩쏘 탐지 {asof}</title><style>
:root{{color-scheme:light;--bg:#f6f6f4;--sf:#fcfcfb;--bd:#e3e2dd;--ink:#0f0f0e;--ink2:#54534e;--mut:#8a877e;--a:#2a78d6;--b:#eb6834;--good:#1a7f4b}}
@media(prefers-color-scheme:dark){{:root{{--bg:#111110;--sf:#1a1a19;--bd:#33322f;--ink:#fafaf7;--ink2:#c3c2b7;--mut:#8f8e85;--a:#3987e5;--b:#d95926;--good:#4bb87c}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Malgun Gothic","Apple SD Gothic Neo",sans-serif;font-size:14px;line-height:1.6}}
.w{{max-width:900px;margin:0 auto;padding:34px 20px 70px}}
h1{{font-size:24px;margin:0 0 4px}}.sub{{color:var(--ink2);margin:0 0 4px}}
.tot{{color:var(--ink2);font-size:13px;margin:6px 0 0}}
h3{{font-size:15px;margin:26px 0 8px;display:flex;align-items:center;gap:8px}}
table{{width:100%;border-collapse:collapse;margin:4px 0 8px;font-size:13px}}
th,td{{text-align:left;padding:7px 9px;border-bottom:1px solid var(--bd)}}
th{{color:var(--ink2);font-size:11.5px;font-weight:650}}
td.n{{text-align:right;font-variant-numeric:tabular-nums}}
.c{{color:var(--mut);font-size:11px}}
.g{{display:inline-block;width:19px;height:19px;border-radius:5px;text-align:center;line-height:19px;font-size:11px;font-weight:700;color:#fff}}
.gA{{background:var(--good)}}.gB{{background:var(--a)}}.gC{{background:var(--mut)}}.gL{{background:var(--b)}}
.warn{{color:var(--mut);font-size:12px;margin-top:22px;border-top:1px solid var(--bd);padding-top:12px}}
</style></head><body><div class=w>
<h1>휩쏘 탐지 · {asof}</h1>
<p class=sub>'2일째' 기준 · 급락 이틀 후 장기선 지지 자리</p>
{f'<p class=sub style="font-weight:650">{_htmlmod.escape(regime_line.strip())}</p>' if regime_line else ''}
<p class=tot>조건 만족 <b>{total}종</b> · A 선지지형 {na}(A급 {int(gc.get('A',0)) if len(RA) else 0}·B급 {int(gc.get('B',0)) if len(RA) else 0}·C급 {int(gc.get('C',0)) if len(RA) else 0}) · B 리더형 {nb} · 반도체체인 {chain_n}/{total}</p>
{('<h2 style="font-size:17px;margin:26px 0 2px;color:var(--a)">A 선지지형</h2>'+ablocks) if na else ''}
{('<h2 style="font-size:17px;margin:26px 0 2px;color:var(--b)">B 리더형</h2>'+bblock) if nb else ''}
<p class=warn>⚠️ 예외적 자리용 · 표본 소수 · 검정된 규칙 아님. 후보를 좁힐 뿐, 진짜 휩쏘인지는 일봉 직접 확인. 등급 A지지&gt;B밀착&gt;C근접 — C도 버리지 않는다(눌린 좋은 종목이 숨음).</p>
</div></body></html>"""
    with open(out_html, "w", encoding="utf-8") as f:
        f.write(doc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None, help="'2일째'로 놓을 날 YYYYMMDD (기본 마지막)")
    ap.add_argument("--mode", default="AB", help="탐지 유형 A/B 조합 (기본 AB = 둘 다)")
    ap.add_argument("--near", type=float, default=8.0, help="선 근접 %% (기본 8)")
    ap.add_argument("--flush2", type=float, default=12.0, help="[A] 2일 누적 낙폭 하한 %% (기본 12)")
    ap.add_argument("--d1", type=float, default=3.0, help="[A] 급락1 최소 %% (기본 3)")
    ap.add_argument("--d2max", type=float, default=2.0, help="[A] 급락2 상한 %% (기본 +2)")
    ap.add_argument("--dd5", type=float, default=30.0, help="[A] 5년 대비 최소 하락 %% (기본 30)")
    ap.add_argument("--mcap", type=float, default=3000.0, help="[A] 시총 하한 억 (기본 3000)")
    ap.add_argument("--aup", type=float, default=8.0, help="[A] MA240 이격 상한 %% (선 근처/아래, 기본 8)")
    ap.add_argument("--bup", type=float, default=10.0, help="[B] MA240 이격 하한 %% (추세 상단, 기본 10)")
    ap.add_argument("--bflush", type=float, default=3.0, help="[B] 2일 누적 낙폭 하한 %% (얕은 눌림, 기본 3)")
    ap.add_argument("--bmcap", type=float, default=50000.0, help="[B] 시총 하한 억 (대장주, 기본 5조)")
    ap.add_argument("--code", default=None)
    ap.add_argument("--noopen", action="store_true", help="HTML 자동 열기 끄기(자동실행·서버용)")
    ap.add_argument("--noregister", action="store_true", help="관찰 원장 자동 등록 끄기")
    a = ap.parse_args()
    NR = a.near / 100.0
    MODE = a.mode.upper()

    D = load(); asof = a.date and f"{a.date[:4]}-{a.date[4:6]}-{a.date[6:]}" or D["date"].max()
    picks = [x.strip().zfill(6) for x in a.code.split(",")] if a.code else None

    names = {}
    npp = _find("종목명_맵.csv")
    if npp:
        try:
            nm = pd.read_csv(npp, dtype=str); names = dict(zip(nm.iloc[:,0].str.zfill(6), nm.iloc[:,1]))
        except Exception: pass
    sec = {}
    for f in ("liquidity_sector.csv", "kosdaq_industry.csv"):
        p = _find(f)
        if p:
            try:
                d = pd.read_csv(p, dtype=str); d.columns=[x.strip().lstrip("﻿") for x in d.columns]
                if {"code","sector"}.issubset(d.columns):
                    sec.update(dict(zip(d["code"].str.zfill(6), d["sector"].astype(str))))
            except Exception: pass
    MC = {}
    mp = _find("종목시총_30년.csv")
    if mp:
        try:
            mc = pd.read_csv(mp, dtype={"code":str}); mc.columns=[c.strip().lstrip("﻿") for c in mc.columns]
            mc["code"]=mc["code"].str.zfill(6)
            MC = pd.to_numeric(mc.sort_values("date").groupby("code")["mcap"].last(), errors="coerce").to_dict()
        except Exception: pass

    # ── 밸류 태그 (재무검정 2,074건: 국면 통제 후에도 저PBR +3.8%p·저PER +2.5%p·배당2%+ 승률 68%)
    #    표기·우선순위용 — 필터/등급 아님. 적자·고PER 감점도 하지 않는다(중립 확인).
    FINP = {}
    for fnm in ("종목재무_KRX_KOSPI.csv", "종목재무_KRX_KOSDAQ.csv"):
        fp = _find(fnm)
        if not fp: continue
        try:
            fd = pd.read_csv(fp, dtype={"code": str})
            fd.columns = [c.strip().lstrip("﻿") for c in fd.columns]
            fd["code"] = fd["code"].str.zfill(6); fd = fd.sort_values("date")
            for cc, gg in fd.groupby("code"):
                FINP[cc] = (gg["date"].values.astype(str),
                            gg[["PER", "PBR", "EPS", "DIV"]].apply(pd.to_numeric, errors="coerce").values)
        except Exception: pass

    def value_tag(cc, d0):
        a = FINP.get(cc)
        if not a: return ""
        dd, vv = a
        k = int(np.searchsorted(dd, d0, side="right")) - 1
        if k < 0: return ""
        per, pbr, eps, div = vv[k]
        tags = []
        if np.isfinite(pbr) and 0 < pbr < 0.8: tags.append("저PBR")
        if np.isfinite(per) and 0 < per < 8 and (not np.isfinite(eps) or eps > 0): tags.append("저PER")
        if np.isfinite(div) and div >= 2: tags.append("배당2%+")
        return "·".join(tags)

    print("=" * 116)
    # ── 전향적 테마태그 (2026-08-04) ────────────────────────────
    # 과거 시점의 테마 소속은 복원 불가능(생존편향)하므로, 포착 "시점"의 태그를
    # 원장에 박아 지금부터 쌓는다. 2~3년 누적 후 사전등록 검정에 쓴다.
    THEME = {}
    for fn, cc, tc in (("theme_universe.csv", "code", "theme"),
                       ("kosdaq_theme_chain_map.csv", "ticker", "theme")):
        fp = _find(fn)
        if fp:
            try:
                t = pd.read_csv(fp, dtype=str)
                t.columns = [x.strip().lstrip("\ufeff") for x in t.columns]
                for _, r_ in t.iterrows():
                    code6 = str(r_.get(cc, "")).strip().zfill(6)
                    if code6.isdigit() and code6 not in THEME:
                        THEME[code6] = str(r_.get(tc, "")).strip()
            except Exception:
                pass

    def theme_tag(cc, sec_str):
        t = THEME.get(cc, "")
        if not t and is_chain(sec_str): t = "반도체체인"
        return t

    print(f" 휩쏘 탐색기 — '2일째' {asof} · 유형[{MODE}] · 선 근접 ±{a.near:.0f}%")
    print(f"   A 선지지형: 2일누적 ≤ -{a.flush2:.0f}% · MA240이격 ≤ +{a.aup:.0f}% · 5년 ≤ -{a.dd5:.0f}% · 시총 ≥ {a.mcap:.0f}억")
    print(f"   B 리더형  : 2일누적 ≤ -{a.bflush:.0f}% · MA240이격 ≥ +{a.bup:.0f}% · 시총 ≥ {a.bmcap/1e4:.0f}조")
    print("=" * 116)

    # ── 시장국면 게이트 (30년 역사검정: 국면이 신호를 뒤집는다)
    regime_line = None
    try:
        import 시장국면 as 국면
        regime_line, _rg = 국면.banner(asof)
        print(regime_line)
        if not _rg.get("실행"):
            print("   ⚠️ 불리 국면 — 신호가 떠도 '관찰만'. 역사적으로 이 국면의 휩쏘는 졌다(−5.9%·승36%).")
        print("=" * 116)
    except Exception as e:
        pass

    def testA(p, mc):
        return (p["급락1"] <= -a.d1/100 and p["급락2"] <= a.d2max/100
                and p["2일누적"] <= -a.flush2/100 and bool(p["근접"])
                and p["고점5년比"] <= -a.dd5/100 and p["고점매도신호"] == 0
                and np.isfinite(p["이격MA240"]) and p["이격MA240"] <= a.aup/100
                and np.isfinite(mc) and mc >= a.mcap*1e8)

    def testB(p, mc):
        return (p["급락1"] <= -a.d1/100 and p["2일누적"] <= -a.bflush/100
                and bool(p["근접"]) and p["고점매도신호"] == 0
                and np.isfinite(p["이격MA240"]) and p["이격MA240"] >= a.bup/100
                and np.isfinite(mc) and mc >= a.bmcap*1e8)

    rows, diag = [], []
    for c, g in D.groupby("code", sort=False):
        if picks and c not in picks: continue
        p = profile(g, asof, NR)
        if p is None:
            if picks: diag.append((c, "일봉<260 또는 데이터 부족", None, np.nan))
            continue
        mc = MC.get(c, np.nan)
        isA, isB = testA(p, mc), testB(p, mc)
        if picks:
            tag = "A 선지지형" if isA else ("B 리더형" if isB else "해당 없음")
            diag.append((c, tag, p, mc)); continue
        for typ, ok in (("A", isA), ("B", isB)):
            if typ not in MODE or not ok: continue
            ch = is_chain(sec.get(c, ""))
            gd, q = grade_of(p, ch)
            rows.append(dict(code=c, name=names.get(c, c), sector=sec.get(c, ""),
                             유형=typ, 테마=("반도체체인" if ch else "기타"),
                             테마태그=theme_tag(c, sec.get(c, "")),
                             밸류=value_tag(c, str(asof)), 등급=gd, 품질=q, mcap=mc, **p))

    if picks:
        for c, tag, p, mc in diag:
            if p is None:
                print(f"  · {names.get(c,c)}({c}) — {tag}"); continue
            print(f"\n  ▣ {names.get(c,c)}({c}) — [{tag}]")
            print(f"     급락1 {p['급락1']:+.1%} · 급락2 {p['급락2']:+.1%} · 2일누적 {p['2일누적']:+.1%}"
                  f" · MA240이격 {p['이격MA240']:+.1%} · 핵심선 {p['핵심선']} {p['핵심선거리']:+.1%}"
                  f" · 지지[{p['지지'] or '-'}] · 5년 {p['고점5년比']:+.0%} · 시총 {fmt_mcap(mc)}")
        return

    if not rows:
        print("\n조건 만족 종목 없음.")
        print(" · 오늘이 휩쏘 2일째가 아니거나(대부분의 날), 시장이 그 자리가 아니다.")
        print(" · A 넓히기: --flush2 8 --near 10 --mcap 1000 · B 넓히기: --bflush 2 --bup 8")
        return

    R = pd.DataFrame(rows); R["_d"] = R["핵심선거리"].abs()
    out = os.path.join(HERE, f"휩쏘탐지_{asof.replace('-','')}.csv")
    R.drop(columns="_d").to_csv(out, index=False, encoding="utf-8-sig")

    RA = R[R["유형"] == "A"].sort_values(["등급", "품질", "_d"], ascending=[True, False, True])
    RB = R[R["유형"] == "B"].sort_values("_d")
    chain_n = int((R['테마'] == '반도체체인').sum())
    print(f"\n조건 만족 {len(R)}종  ·  A 선지지형 {len(RA)} · B 리더형 {len(RB)}"
          f"  ·  반도체체인 {chain_n}/{len(R)}")

    # ── 자동 HTML 리포트 (매번 생성, 브라우저로 팝업)
    out_html = out.replace(".csv", ".html")
    try:
        write_html(RA, RB, asof, chain_n, len(R), out_html, regime_line)
        if not a.noopen:
            webbrowser.open("file://" + os.path.abspath(out_html))
    except Exception as e:
        print(f"  (HTML 생성 건너뜀: {str(e)[:60]})")

    if len(RA):
        gc = RA["등급"].value_counts()
        print("\n" + "█" * 116)
        print(f" A 선지지형 — {len(RA)}종  (A급 {int(gc.get('A',0))} · B급 {int(gc.get('B',0))} · C급 {int(gc.get('C',0))})")
        print("█" * 116)
        hdr = (dw("등급",5)+dw("코드",7)+dw("종목명",15)+dw("테마",11)+dw("종가",10,1)
               +dw("급락1",7,1)+dw("급락2",7,1)+dw("2일누적",8,1)+dw("꼬리",6,1)
               +dw("핵심선",7)+dw("거리",7,1)+dw("지지",13)+dw("5년比",6,1)+dw("시총",8,1))
        for gg, gname in (("A","A급 지지(선 밟고 종가 위)"),("B","B급 밀착 ±3%"),
                          ("C","C급 근접 (기관 개입으로 밀렸을 수 있음 · 관찰)")):
            sub = RA[RA["등급"] == gg]
            if len(sub) == 0: continue
            print(f"\n ── {gname} — {len(sub)}종")
            print(hdr); print("-" * 116)
            for _, r in sub.iterrows():
                print(dw(r["등급"],5)+dw(r["code"],7)+dw(r["name"],15)+dw(r["테마"],11)
                      +dw(f"{r['종가']:,.0f}",10,1)+dw(f"{r['급락1']:+.1%}",7,1)
                      +dw(f"{r['급락2']:+.1%}",7,1)+dw(f"{r['2일누적']:+.1%}",8,1)
                      +dw(f"{r['오늘아래꼬리']:.1%}",6,1)+dw(str(r["핵심선"]),7)
                      +dw(f"{r['핵심선거리']:+.1%}",7,1)+dw(r["지지"] or "-",13)
                      +dw(f"{r['고점5년比']:+.0%}",6,1)+dw(fmt_mcap(r["mcap"]),8,1))

    if len(RB):
        print("\n" + "█" * 116)
        print(f" B 리더형 (추세 상단 대장주 · 얕은 눌림) — {len(RB)}종")
        print("█" * 116)
        hdr = (dw("코드",7)+dw("종목명",15)+dw("테마",11)+dw("종가",11,1)
               +dw("급락1",7,1)+dw("급락2",7,1)+dw("2일누적",8,1)+dw("MA240이격",10,1)
               +dw("핵심선",7)+dw("거리",7,1)+dw("5년比",6,1)+dw("시총",8,1))
        print(hdr); print("-" * 116)
        for _, r in RB.iterrows():
            print(dw(r["code"],7)+dw(r["name"],15)+dw(r["테마"],11)+dw(f"{r['종가']:,.0f}",11,1)
                  +dw(f"{r['급락1']:+.1%}",7,1)+dw(f"{r['급락2']:+.1%}",7,1)
                  +dw(f"{r['2일누적']:+.1%}",8,1)+dw(f"{r['이격MA240']:+.1%}",10,1)
                  +dw(str(r["핵심선"]),7)+dw(f"{r['핵심선거리']:+.1%}",7,1)
                  +dw(f"{r['고점5년比']:+.0%}",6,1)+dw(fmt_mcap(r["mcap"]),8,1))

    # ── 관찰 원장 자동 등록 (탐지 → 원장 한 번에)
    if not a.noregister:
        gw = os.path.join(HERE, "휩쏘_관찰.py")
        d0 = asof.replace("-", "")
        if os.path.exists(gw):
            try:
                subprocess.run([sys.executable, gw, "--add", "--date", d0, "--noopen"],
                               check=False)
                print(f" 관찰 원장 자동 등록 완료 → 휩쏘_관찰.csv (대시보드: py 휩쏘_관찰.py)")
            except Exception as e:
                print(f" (원장 등록 건너뜀: {str(e)[:60]})")
        else:
            print(" (휩쏘_관찰.py 없음 — 원장 자동 등록 생략)")

    print("\n" + "─" * 116)
    print(f" 저장: {os.path.basename(out)} · {os.path.basename(out_html)} (HTML 자동 팝업)")
    print(" A는 등급(A지지>B밀착>C근접) — C도 안 버린다(눌린 좋은 종목이 숨음). B는 대장주 얕은 눌림.")
    print(" ⚠️ 표본 소수 — 검정된 규칙 아님. 뜨면 형 눈으로 일봉 직접 확인.")


if __name__ == "__main__":
    main()
