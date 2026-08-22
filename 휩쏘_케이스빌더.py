# -*- coding: utf-8 -*-
r"""휩쏘_케이스빌더.py — 30년 역사원장 대표 케이스 8건을 개별 페이지로 상세 분석.
   케이스마다: 일봉 차트(진입 전후 · 장기선 · 진입/손절/목표/청산/고점 표시) + 수치 + 해설.
   산출: 휩쏘_케이스집.html(목차) + 휩쏘_케이스_1~8_*.html
"""
import os, sys, gc, importlib.util, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
DATA = os.path.join(HERE, "data")
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

CASES = [
    dict(no=1, date="1997-12-09", code="005490", name="POSCO홀딩스", mkt="KOSPI",
         era="IMF 외환위기", tag="승리", 파일="포스코1997",
         해설=["IMF 한복판, 지수가 1년 고점 대비 −51%까지 무너진 자리에서 포스코가 이틀 급락으로 장기선을 파고들었다. 국면 게이트는 🟢실행 — 시장이 이미 무너진 뒤의 휩쏘는 역사상 가장 유리한 자리다.",
              "카드청산은 2거래일 만에 목표 도달(+10.7%). 그런데 6개월 안 최고점은 +83.6%(50거래일 뒤, 이듬해 3월)였다. 위기 바닥의 휩쏘는 꼬리가 거대하다 — 카드가 빨리 파는 만큼 남긴 것도 크다.",
              "교훈: 위기 국면(실행)의 휩쏘는 청산을 서두르지 않을 근거가 있다. 2단 청산(절반 목표·절반 트레일) 검정이 필요한 이유가 이 케이스다."]),
    dict(no=2, date="1998-07-02", code="000660", name="SK하이닉스", mkt="KOSPI",
         era="IMF 구조조정기", tag="손절 후 대반등", 파일="하이닉스1998",
         해설=["같은 IMF라도 다 이기는 게 아니다. 진입 다음날 바로 손절선을 건드려 −5.7%로 끝났다. 그런데 그 뒤 123거래일 만에 +44.6%까지 반등했다 — 손절이 '틀린' 게 아니라 '한 번 더 흔든' 것이다.",
              "이게 휩쏘의 본질이다: 손절당한 자리가 진짜 바닥일 수 있다. 그래서 손절 후에도 종목을 버리지 않고 관찰 원장에 남겨 재진입 신호(새 휩쏘 2일째)를 기다리는 구조가 필요하다.",
              "교훈: 손절 = 종목 폐기가 아니다. 원장의 '손절' 상태는 재관찰 후보 목록이기도 하다."]),
    dict(no=3, date="2000-08-31", code="005930", name="삼성전자", mkt="KOSPI",
         era="닷컴 붕괴 진행형", tag="A급 지지의 배신", 파일="삼성전자2000",
         해설=["등급 A — 저가가 장기선을 정확히 밟고 종가가 그 위. 교과서적 지지처럼 보였지만 −6.5% 손절로 끝났고, 6개월 최고점도 +2.4%에 그쳤다. 2000년은 A유형 승률 22%, 30년 최악의 해였다.",
              "구조적 하락(닷컴 붕괴)이 진행 중일 때는 '2일째 바닥'을 사도 3일째, 10일째가 더 빠진다. 선을 밟았느냐(등급)는 이 문제를 해결하지 못한다 — 30년 데이터에서 A급이 C급보다 낫지 않았던 '등급 역설'의 대표 사례.",
              "교훈: 지지의 정밀함보다 시장 국면이 먼저다. 이 케이스가 등급 가중을 버린 근거다."]),
    dict(no=4, date="2008-10-07", code="068270", name="셀트리온", mkt="KOSDAQ",
         era="금융위기 바닥", tag="사이클 봄 고점", 파일="셀트리온2008",
         해설=["리먼 사태 직후, 지수 −40%대의 극단 국면. 카드청산은 다음날 목표 도달(+10.8%)로 끝났지만, 이 종목의 진짜 고점은 124거래일 뒤인 이듬해 4월, +193.7%였다.",
              "형의 사이클(가을 저점 → 봄 고점)이 개별 종목에서 실현된 전형이다. 10월 위기 바닥 진입 → 4월 고점. 다만 30년 통계에서 이런 '봄 고점'은 9~10월 진입분의 30% — 절반은 연내(10~11월)에 고점이 온다.",
              "교훈: 사이클은 살아남은 종목의 최종 시한(4~5월)으로 쓴다. 다만 '4월까지 무조건 보유'는 중앙 −10.8%로 진다 — 이 케이스 같은 꼬리는 트레일로만 안전하게 탈 수 있다."]),
    dict(no=5, date="2013-06-05", code="002990", name="금호건설", mkt="KOSPI",
         era="조용한 고점권", tag="관찰만 함정", 파일="금호건설2013",
         해설=["시장은 고점권·저변동 — 국면 게이트가 🔴관찰만을 띄우는 바로 그 자리다. 개별 종목만 이틀 급락해 조건을 다 만족했지만, 진입 다음날 −11.8% 손절.",
              "시장이 무너진 게 아니라 이 종목만 무너진 것이었다. 고점권·저변동 국면의 휩쏘는 30년 통계로 40일 평균 −5.9%, 승률 36% — 신호가 아니라 함정이다.",
              "교훈: 게이트가 관찰만이면 기록만 하고 사지 않는다. 이 규율 하나가 30년 데이터에서 가장 큰 손실 구간을 제거한다."]),
    dict(no=6, date="2020-06-15", code="222800", name="심텍", mkt="KOSDAQ",
         era="코로나 V반등", tag="반도체체인 승리", 파일="심텍2020",
         해설=["코로나 2차 흔들기. 고변동 국면(실행)에서 반도체 기판주 심텍이 이틀 급락으로 장기선에 밀착했다. 다음날 바로 목표 도달(+8.5%).",
              "6개월 최고점은 +127.1%(41거래일 뒤). 2020년은 A유형 승률 75%, 40일 평균 +20.3% — 30년 최고의 해였다. V반등 국면에서 휩쏘는 거의 다 이긴다.",
              "교훈: 국면이 유리할 때는 같은 신호의 기대값이 몇 배로 뛴다. 형이 좋아하는 반도체체인이 이 국면에서 특히 강했다."]),
    dict(no=7, date="2024-08-05", code="000660", name="SK하이닉스", mkt="KOSPI",
         era="블랙먼데이(8월 급락)", tag="8월 사냥터", 파일="하이닉스2024",
         해설=["2024년 8월 5일 글로벌 급락 — 지수 최약월(8월)에 대장주가 이틀에 −20%대 플러시. 등급 A(선 지지), 국면 실행. 5거래일 만에 목표 +11.9%.",
              "이후 고점은 112거래일 뒤인 이듬해 1월 +45.4% — '가을 진입 → 연초 고점'의 전형. 30년 지수 계절성에서 8월은 유일하게 평균 −1.2%로 가장 약한 달이고, 그래서 휩쏘 표본이 가장 많이 잡히는 달(309건)이다.",
              "교훈: 8~10월 약세 구간은 두려워할 때가 아니라 사냥할 때다. 단, 국면 게이트(시장 낙폭·변동성)가 실행일 때만."]),
    dict(no=8, date="2026-07-30", code="353200", name="대덕전자", mkt="KOSPI",
         era="이번 휩쏘 (진행중)", tag="원점 케이스", 파일="대덕전자2026",
         해설=["이 시스템 전체의 출발점. 7/29~30 이틀 급락(−19.5%)으로 240일선 바로 위(+1.2%)까지 눌렸다. 시장은 1년 고점 대비 −38%, 극단적 고변동 — 게이트 🟢실행.",
              "7/31 지수가 하루 +15% 되돌리며 원장 33종 중 29종이 목표 도달. 대덕전자도 올해 시총 5.4조까지 큰 주도주라 7/29엔 B리더형, 7/30엔 A선지지형으로 이틀 연속 신호가 떴다.",
              "교훈: 형 직관(기관이 개미를 털고 지수 10000으로 가기 전 흔들기)이 좌표화된 케이스. 이후 경과는 관찰 원장이 기록한다 — 이 페이지는 그 실시간 표본의 스냅샷이다."]),
]


def _load_mod(fn, name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, fn))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def load_fin():
    """KRX 월별 재무(2002-01~): code → (dates, [PER,PBR,EPS,DIV,BPS])"""
    fr = []
    for m in ("KOSPI", "KOSDAQ"):
        p = os.path.join(DATA, f"종목재무_KRX_{m}.csv")
        if not os.path.exists(p): p = os.path.join(HERE, f"종목재무_KRX_{m}.csv")
        if os.path.exists(p):
            d = pd.read_csv(p, dtype={"code": str})
            d.columns = [c.strip().lstrip("﻿") for c in d.columns]
            fr.append(d)
    if not fr: return {}
    F = pd.concat(fr, ignore_index=True)
    F["code"] = F["code"].str.zfill(6); F = F.sort_values("date")
    out = {}
    for c, g in F.groupby("code"):
        out[c] = (g["date"].values.astype(str),
                  g[["PER", "PBR", "EPS", "DIV", "BPS"]].apply(pd.to_numeric, errors="coerce").values)
    return out


def fin_asof(FIN, code, d):
    a = FIN.get(code)
    if not a: return None
    dd, vv = a
    k = int(np.searchsorted(dd, d, side="right")) - 1
    if k < 0: return None
    per, pbr, eps, div, bps = vv[k]
    return dict(기준=dd[k], PER=per, PBR=pbr, EPS=eps, DIV=div, BPS=bps)


def fin_row_html(f, date):
    if date < "2002-02":
        return ("<tr><td>재무현황</td><td class=n>-</td>"
                "<td>KRX 월별 재무 미제공 구간(2002-01 이전) — 정직 고지</td></tr>")
    if not f:
        return ("<tr><td>재무현황</td><td class=n>-</td><td>해당 종목 재무 데이터 없음</td></tr>")
    per = "적자/–" if (not np.isfinite(f["PER"]) or f["PER"] == 0) else f"{f['PER']:.1f}배"
    pbr = "-" if not np.isfinite(f["PBR"]) or f["PBR"] == 0 else f"{f['PBR']:.2f}배"
    eps = "-" if not np.isfinite(f["EPS"]) else f"{f['EPS']:,.0f}원"
    div = "-" if not np.isfinite(f["DIV"]) else f"{f['DIV']:.1f}%"
    bps = "-" if not np.isfinite(f["BPS"]) or f["BPS"] == 0 else f"{f['BPS']:,.0f}원"
    return (f"<tr><td>재무현황 <span style='color:var(--mut);font-size:11px'>({f['기준']} 기준)</span></td>"
            f"<td class=n>PER {per}</td>"
            f"<td>PBR {pbr} · EPS {eps} · 배당수익률 {div} · BPS {bps}</td></tr>")


def get_series():
    hz = _load_mod("휩쏘_역사검정.py", "hz")
    need = {}
    for c in CASES: need.setdefault(c["mkt"], set()).add(c["code"])
    out = {}
    dt = {"code": str, "open": "float32", "high": "float32", "low": "float32",
          "close": "float32", "volume": "float32"}
    for mk, codes in need.items():
        D = pd.read_csv(os.path.join(DATA, f"종목일봉_30년_{mk}.csv"), dtype=dt)
        D.columns = [x.strip().lstrip("﻿") for x in D.columns]
        D["code"] = D["code"].str.zfill(6)
        D = D[D["code"].isin(codes)]
        for code, g in D.groupby("code"):
            g = g.sort_values("date").reset_index(drop=True)
            g = g[~((g["open"] == 0) & (g["volume"] == 0))].reset_index(drop=True)
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
            out[(mk, code)] = dict(dts=dts, o=o, h=h, l=l, c=c, ma240=ma240, w60=w_d, m10=m_d)
    del D; gc.collect()
    return out


def svg_chart(S, t, ev, W=780, Hh=330):
    a, b = max(0, t - 80), min(len(S["c"]) - 1, t + 130)
    xs = np.arange(a, b + 1)
    def X(i): return 54 + (i - a) / max(1, b - a) * (W - 70)
    series = [S["c"][a:b+1], S["ma240"][a:b+1], S["w60"][a:b+1], S["m10"][a:b+1]]
    lo = np.nanmin([np.nanmin(s) for s in series if np.isfinite(s).any()] + [ev["stop"]])
    hi = np.nanmax([np.nanmax(s) for s in series if np.isfinite(s).any()] + [ev["target"], ev.get("peakpx", 0)])
    pad = (hi - lo) * 0.06; lo -= pad; hi += pad
    def Y(v): return 14 + (hi - v) / (hi - lo) * (Hh - 52)
    def poly(vals, color, wdt, dash=""):
        pts = " ".join(f"{X(i):.1f},{Y(v):.1f}" for i, v in zip(xs, vals) if np.isfinite(v))
        d = f" stroke-dasharray='{dash}'" if dash else ""
        return f"<polyline points='{pts}' fill='none' stroke='{color}' stroke-width='{wdt}'{d}/>" if pts else ""
    g = ""
    # 월 경계 그리드 + 라벨
    for i in xs[1:]:
        if S["dts"][i][5:7] != S["dts"][i-1][5:7]:
            g += f"<line x1='{X(i):.1f}' y1='14' x2='{X(i):.1f}' y2='{Hh-38}' stroke='var(--bd)' stroke-width='.6'/>"
            if int(S["dts"][i][5:7]) % 2 == 1:
                g += f"<text x='{X(i):.1f}' y='{Hh-22}' font-size='9.5' fill='var(--mut)' text-anchor='middle'>{S['dts'][i][2:7]}</text>"
    # y축 라벨
    for fr in (0.05, 0.5, 0.95):
        v = lo + (hi - lo) * fr
        g += f"<text x='4' y='{Y(v)+3:.0f}' font-size='9.5' fill='var(--mut)'>{v:,.0f}</text>"
    g += poly(S["m10"][a:b+1], "var(--mut)", 1.1, "2 3")
    g += poly(S["w60"][a:b+1], "var(--b)", 1.2, "5 3")
    g += poly(S["ma240"][a:b+1], "var(--a)", 1.4)
    g += poly(S["c"][a:b+1], "var(--ink)", 1.8)
    # 손절/목표 수평선 (진입~+45봉)
    x0, x1 = X(t), X(min(b, t + 45))
    g += f"<line x1='{x0:.0f}' y1='{Y(ev['stop']):.1f}' x2='{x1:.0f}' y2='{Y(ev['stop']):.1f}' stroke='var(--bad)' stroke-width='1.1' stroke-dasharray='4 3'/>"
    g += f"<line x1='{x0:.0f}' y1='{Y(ev['target']):.1f}' x2='{x1:.0f}' y2='{Y(ev['target']):.1f}' stroke='var(--good)' stroke-width='1.1' stroke-dasharray='4 3'/>"
    # 진입 수직선 + ▲
    g += f"<line x1='{x0:.0f}' y1='14' x2='{x0:.0f}' y2='{Hh-38}' stroke='var(--ink2)' stroke-width='1' stroke-dasharray='2 2'/>"
    g += f"<text x='{x0:.0f}' y='{Hh-26}' font-size='10' fill='var(--ink2)' text-anchor='middle'>진입 {ev['date'][5:]}</text>"
    g += f"<circle cx='{x0:.0f}' cy='{Y(ev['entry']):.1f}' r='4' fill='var(--ink)'/>"
    # 카드 청산 ✕
    if ev.get("exbars") and t + ev["exbars"] <= b:
        xe = X(t + ev["exbars"]); ye = Y(ev["entry"] * (1 + ev["exret"]))
        g += f"<text x='{xe:.0f}' y='{ye+4:.0f}' font-size='13' fill='var(--bad)' text-anchor='middle' font-weight='700'>✕</text>"
    # 6M 고점 ●
    if ev.get("pkdays") and t + ev["pkdays"] <= b and ev.get("peakpx"):
        xp = X(t + ev["pkdays"]); yp = Y(ev["peakpx"])
        g += f"<circle cx='{xp:.0f}' cy='{yp:.1f}' r='4.5' fill='var(--good)'/>"
        g += f"<text x='{xp:.0f}' y='{yp-8:.0f}' font-size='10' fill='var(--good)' text-anchor='middle' font-weight='700'>{ev['peak']:+.0f}%</text>"
    leg = ("<g font-size='10'>"
           f"<text x='58' y='24' fill='var(--ink)'>— 종가</text>"
           f"<text x='108' y='24' fill='var(--a)'>— 일240</text>"
           f"<text x='162' y='24' fill='var(--b)'>-- 주60주</text>"
           f"<text x='224' y='24' fill='var(--mut)'>·· 월10</text>"
           f"<text x='272' y='24' fill='var(--good)'>-- 목표</text>"
           f"<text x='318' y='24' fill='var(--bad)'>-- 손절 · ✕ 청산 · ● 6M고점</text></g>")
    return f"<svg viewBox='0 0 {W} {Hh}' width='100%' style='max-width:{W}px'>{g}{leg}</svg>"


CSS = """
:root{color-scheme:light;--bg:#f6f6f4;--sf:#fcfcfb;--bd:#e3e2dd;--ink:#0f0f0e;--ink2:#54534e;--mut:#8a877e;--a:#2a78d6;--b:#eb6834;--good:#1a7f4b;--bad:#c0342f}
@media(prefers-color-scheme:dark){:root{color-scheme:dark;--bg:#111110;--sf:#1a1a19;--bd:#33322f;--ink:#fafaf7;--ink2:#c3c2b7;--mut:#8f8e85;--a:#3987e5;--b:#d95926;--good:#4bb87c;--bad:#e0655a}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Malgun Gothic","Apple SD Gothic Neo",sans-serif;font-size:14.5px;line-height:1.66}
.w{max-width:860px;margin:0 auto;padding:34px 20px 70px}
h1{font-size:23px;margin:0 0 4px}.sub{color:var(--ink2);margin:0 0 6px}
.chips{display:flex;gap:6px;flex-wrap:wrap;margin:8px 0 16px}
.chip{display:inline-block;padding:2px 10px;border-radius:20px;font-size:12px;font-weight:650;color:#fff}
.cG{background:var(--good)}.cR{background:var(--bad)}.cB{background:var(--a)}.cO{background:var(--b)}.cM{background:var(--mut)}
table{width:100%;border-collapse:collapse;margin:10px 0;font-size:13px}
th,td{text-align:left;padding:7px 9px;border-bottom:1px solid var(--bd)}
th{color:var(--ink2);font-size:11.5px;font-weight:650}td.n{text-align:right;font-variant-numeric:tabular-nums}
.good{color:var(--good)}.bad{color:var(--bad)}
.les{background:var(--sf);border:1px solid var(--bd);border-left:4px solid var(--a);border-radius:10px;padding:13px 16px;margin:14px 0}
.nav{display:flex;justify-content:space-between;margin-top:26px;padding-top:14px;border-top:1px solid var(--bd);font-size:13px}
.nav a{color:var(--a);text-decoration:none}
.warn{color:var(--mut);font-size:12px;margin-top:18px}
.card{display:block;background:var(--sf);border:1px solid var(--bd);border-radius:10px;padding:13px 16px;margin:10px 0;text-decoration:none;color:var(--ink)}
.card:hover{border-color:var(--a)}
.card .t{font-weight:700}.card .d{color:var(--ink2);font-size:12.5px;margin-top:2px}
"""


def main():
    G = pd.read_csv(os.path.join(HERE, "휩쏘_고점_이벤트.csv"), dtype={"code": str})
    G["code"] = G["code"].str.zfill(6)
    FIN = load_fin()
    # 검증용 무수정 종가
    RAW = {}
    for m in ("KOSPI", "KOSDAQ"):
        p = os.path.join(HERE, f"역사검정_이벤트_{m}.csv")
        if os.path.exists(p):
            e = pd.read_csv(p, dtype={"code": str}); e["code"] = e["code"].str.zfill(6)
            RAW.update({(r["date"], r["code"]): r["rawclose"] for _, r in e.iterrows()})
    S = get_series()
    files = []
    for c in CASES:
        key = (c["mkt"], c["code"])
        s = S[key]
        pos = {d: i for i, d in enumerate(s["dts"])}
        t = pos[c["date"]]
        row = G[(G["출발일"] == c["date"]) & (G["code"] == c["code"])].iloc[0]
        entry = s["c"][t]
        exret = float(row["ex_ret"]); exbars = int(row["ex_bars"]); exhow = str(row["ex_how"])
        peak = float(row["고점6M"]) if pd.notna(row["고점6M"]) else np.nan
        pkdays = int(row["고점일수"]) if pd.notna(row["고점일수"]) else None
        # 손절/목표 재구성 (역사검정 카드 규칙과 동일)
        cum2 = entry / s["c"][t-2] - 1
        r1 = s["c"][t-1] / s["c"][t-2] - 1; r2 = s["c"][t] / s["c"][t-1] - 1
        lines = {"주60주": s["w60"][t], "월10": s["m10"][t], "일240": s["ma240"][t]}
        fin = {k: v for k, v in lines.items() if np.isfinite(v)}
        keyl = min(fin, key=lambda k: abs(entry / fin[k] - 1))
        kv = fin[keyl]
        if str(row["유형"]) == "A":
            pre = entry / (1 + cum2); target = entry + (pre - entry) * 0.5
            below = kv if kv < entry else s["l"][t]; stop = below * 0.95
        else:
            target = float(np.max(s["h"][max(0, t-59):t+1]))
            below = kv if kv < entry else s["l"][t]; stop = below * 0.97
        ev = dict(date=c["date"], entry=entry, stop=stop, target=target,
                  exret=exret, exbars=exbars, peak=peak, pkdays=pkdays,
                  peakpx=entry * (1 + peak / 100) if np.isfinite(peak) else None)
        chart = svg_chart(s, t, ev)
        진행중 = bool(row.get("창완결") == False) if "창완결" in row else False
        tagcl = "cG" if "승" in c["tag"] or "고점" in c["tag"] else ("cR" if "함정" in c["tag"] or "배신" in c["tag"] else "cB")
        rgchip = {"실행": ("실행", "cG"), "주의": ("주의", "cO"), "관찰만": ("관찰만", "cR")}.get(str(row["국면"]), ("-", "cM"))
        exs = f"{exret*100:+.1f}%"; excl = "good" if exret > 0 else "bad"
        rows_html = (
            f"<tr><td>진입(2일째 종가)</td><td class=n>{entry:,.0f}</td><td>급락1 {r1*100:+.1f}% · 급락2 {r2*100:+.1f}% · 2일누적 <b>{cum2*100:+.1f}%</b></td></tr>"
            f"<tr><td>핵심선</td><td class=n>{kv:,.0f}</td><td>{keyl} (거리 {(entry/kv-1)*100:+.1f}%)</td></tr>"
            f"<tr><td>손절 / 목표</td><td class=n>{stop:,.0f} / {target:,.0f}</td><td>{(stop/entry-1)*100:+.1f}% / {(target/entry-1)*100:+.1f}%</td></tr>"
            f"<tr><td>카드 청산</td><td class='n {excl}'><b>{exs}</b></td><td>{exhow} · {exbars}거래일</td></tr>")
        if np.isfinite(peak):
            gap = peak - exret * 100
            rows_html += (f"<tr><td>6개월 내 최고점</td><td class='n good'><b>{peak:+.1f}%</b></td>"
                          f"<td>{pkdays}거래일 뒤 ({str(row['고점일'])[:7]}) · 카드 대비 잔여 {gap:+.1f}%p</td></tr>")
        # ── 시점(월) · 재무 · 검증
        exdate = s["dts"][t + exbars] if t + exbars < len(s["dts"]) else "-"
        pkdate = str(row["고점일"]) if pd.notna(row.get("고점일")) else "-"
        mm = lambda d: f"{int(d[5:7])}월" if isinstance(d, str) and len(d) >= 7 else "-"
        rows_html += (f"<tr><td>시점 흐름</td><td class=n>{mm(c['date'])} → {mm(exdate)}</td>"
                      f"<td>진입 {c['date']} → 카드청산 {exdate}"
                      + (f" → 6M고점 {pkdate} ({mm(pkdate)})" if pkdate != "-" else "") + "</td></tr>")
        rows_html += fin_row_html(fin_asof(FIN, c["code"], c["date"]), c["date"])
        rawpx = RAW.get((c["date"], c["code"]))
        if rawpx is not None and np.isfinite(rawpx):
            same = abs(rawpx - entry) < max(1.0, entry * 0.001)
            rows_html += (f"<tr><td>검증 — 당시 실제 종가</td><td class=n>{rawpx:,.0f}원</td>"
                          f"<td>{'백조정가와 동일(이후 분할·증자 없음)' if same else f'백조정가 {entry:,.0f} — 이후 분할·증자 반영 차이(정상)'}</td></tr>")
        les = "".join(f"<p style='margin:{'0' if i==0 else '10px'} 0 0'>{t_}</p>" for i, t_ in enumerate(c["해설"]))
        prev_f = f"휩쏘_케이스_{c['no']-1}_{CASES[c['no']-2]['파일']}.html" if c["no"] > 1 else None
        next_f = f"휩쏘_케이스_{c['no']+1}_{CASES[c['no']]['파일']}.html" if c["no"] < len(CASES) else None
        nav = "<div class=nav>" + (f"<a href='{prev_f}'>← 이전 케이스</a>" if prev_f else "<span></span>")
        nav += "<a href='휩쏘_케이스집.html'>목차</a>"
        nav += (f"<a href='{next_f}'>다음 케이스 →</a>" if next_f else "<span></span>") + "</div>"
        doc = f"""<!DOCTYPE html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>케이스 {c['no']} · {c['name']} {c['date'][:4]}</title><style>{CSS}</style></head><body><div class=w>
<h1>케이스 {c['no']} — {c['name']} <span style='color:var(--mut);font-weight:400'>{c['date']}</span></h1>
<p class=sub>{c['era']}</p>
<div class=chips>
<span class='chip {tagcl}'>{c['tag']}</span>
<span class='chip cB'>{row['유형']}형 {row['등급'] if pd.notna(row['등급']) else ''}</span>
<span class='chip {rgchip[1]}'>국면 {rgchip[0]}</span>
{'<span class="chip cM">진행중(창 미완결)</span>' if 진행중 else ''}
</div>
{chart}
<table><tr><th>항목</th><th>값</th><th>비고</th></tr>{rows_html}</table>
<div class=les>{les}</div>
{nav}
<p class=warn>⚠️ 백조정 가격 기준 · 검정·기록용 · 매매 추천 아님. 수치 근거: 휩쏘_역사원장 · 휩쏘_고점_이벤트.csv</p>
</div></body></html>"""
        fn = f"휩쏘_케이스_{c['no']}_{c['파일']}.html"
        open(os.path.join(HERE, fn), "w", encoding="utf-8").write(doc)
        files.append(fn)
        c["_사실"] = dict(ex=exs, how=exhow, peak=(f"{peak:+.1f}%" if np.isfinite(peak) else "-"), rg=str(row["국면"]))
        print(f"  ✓ {fn}")

    # 목차
    cards = ""
    for c in CASES:
        f = c["_사실"]
        cards += (f"<a class=card href='휩쏘_케이스_{c['no']}_{c['파일']}.html'>"
                  f"<span class=t>{c['no']}. {c['name']} · {c['date'][:7]} — {c['tag']}</span>"
                  f"<div class=d>{c['era']} · 국면 {f['rg']} · 카드 {f['ex']}({f['how']}) · 6M고점 {f['peak']}</div></a>")
    idx = f"""<!DOCTYPE html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>휩쏘 케이스집 — 30년 대표 8선</title><style>{CSS}</style></head><body><div class=w>
<h1>휩쏘 케이스집 — 30년 대표 8선</h1>
<p class=sub>역사원장 2,801건에서 시대·국면·승패가 고르게 담기도록 선정. 케이스마다 일봉 차트 + 수치 + 교훈.</p>
<p class=sub style='color:var(--mut);font-size:12.5px'>선정 기준: 시대 대표성(IMF·닷컴·금융위기·코로나·2024·2026) · 국면 대비(실행 6 vs 관찰만 1) · 승패 대비(승 5 · 패 3) · 인지도</p>
{cards}
<p class=warn>⚠️ 검정·기록용. 각 페이지 하단에서 이전/다음 케이스로 이동. 갱신: py 휩쏘_케이스빌더.py</p>
</div></body></html>"""
    open(os.path.join(HERE, "휩쏘_케이스집.html"), "w", encoding="utf-8").write(idx)
    print("  ✓ 휩쏘_케이스집.html (목차)")


if __name__ == "__main__":
    main()
