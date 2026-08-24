# -*- coding: utf-8 -*-
"""휩쏘 2026-08-04 검정 리포트 빌더 → 휩쏘_0804_리포트.html (자기완결 HTML)"""
import os, sys, json
import numpy as np, pandas as pd
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

# ── 경로 해석 (컨테이너 / 형 PC 어디서 돌려도 동작) ─────────────
def _resolve():
    here = os.path.dirname(os.path.abspath(__file__))
    cand = ["/home/claude/jq", "/mnt/user-data/uploads/진우퀀트", here]
    def find(name):
        for d in ([here] + cand):
            p = os.path.join(d, name)
            if os.path.exists(p): return p
        return os.path.join(here, name)
    return here, find
HERE, F = _resolve()

MJ = json.load(open(F("휩쏘_종목군월별_결과.json"), encoding="utf-8"))
TJ = json.load(open(F("휩쏘_시간축_결과.json"), encoding="utf-8"))
HS = [5, 10, 20, 40, 63, 126]
MONTHS = [str(m) for m in range(1, 13)]

S1, S2c, TXT, TXT2, MUT = "#2a78d6", "#eb6834", "#0b0b0b", "#52514e", "#8a8a85"
GRID, SURF = "#e8e7e3", "#fcfcfb"
POS, NEG = "#1baf7a", "#e34948"


def esc(s): return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def bars(items, w=760, h=260, pad=(46, 16, 34, 52), fmt="{:+.2f}", unit="%",
         title="", sub="", colorfn=None, zero_base=False):
    """items: [(label, value, lo, hi or None)]  · 단일 계열 세로 막대 + CI 수염"""
    pt, pr, pb, pl = pad
    iw, ih = w - pl - pr, h - pt - pb
    vals = [v for _, v, *_ in items]
    los = [x[2] for x in items if len(x) > 2 and x[2] is not None]
    his = [x[3] for x in items if len(x) > 3 and x[3] is not None]
    lo = min(vals + los + [0]); hi = max(vals + his + [0])
    span = (hi - lo) or 1
    if zero_base: lo = 0.0; hi += span * .08
    else: lo -= span * .08; hi += span * .08
    span = hi - lo
    def Y(v): return pt + ih * (hi - v) / span
    n = len(items); slot = iw / n; bw = min(34, slot * .56)
    o = [f'<svg viewBox="0 0 {w} {h}" role="img" width="100%" style="max-width:{w}px">']
    o.append(f'<title>{esc(title)}</title>')
    for k in range(5):
        v = lo + span * k / 4; y = Y(v)
        o.append(f'<line x1="{pl}" x2="{w-pr}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        o.append(f'<text x="{pl-8}" y="{y+4:.1f}" text-anchor="end" font-size="11" fill="{MUT}">{v:.1f}</text>')
    y0 = Y(0)
    o.append(f'<line x1="{pl}" x2="{w-pr}" y1="{y0:.1f}" y2="{y0:.1f}" stroke="{TXT2}" stroke-width="1.5"/>')
    for i, it in enumerate(items):
        lab, v = it[0], it[1]
        cx = pl + slot * (i + .5); x = cx - bw / 2
        col = colorfn(lab, v) if colorfn else (S1 if v >= 0 else S2c)
        yv = Y(v); top = min(yv, y0); hgt = abs(yv - y0)
        o.append(f'<rect x="{x:.1f}" y="{top:.1f}" width="{bw:.1f}" height="{max(hgt,1):.1f}" '
                 f'fill="{col}" rx="3" ry="3"><title>{esc(lab)}: {fmt.format(v)}{unit}</title></rect>')
        if len(it) > 3 and it[2] is not None:
            o.append(f'<line x1="{cx:.1f}" x2="{cx:.1f}" y1="{Y(it[2]):.1f}" y2="{Y(it[3]):.1f}" '
                     f'stroke="{TXT2}" stroke-width="1.5" opacity=".75"/>')
            for yy in (it[2], it[3]):
                o.append(f'<line x1="{cx-5:.1f}" x2="{cx+5:.1f}" y1="{Y(yy):.1f}" y2="{Y(yy):.1f}" '
                         f'stroke="{TXT2}" stroke-width="1.5" opacity=".75"/>')
        o.append(f'<text x="{cx:.1f}" y="{h-pb+16}" text-anchor="middle" font-size="11" fill="{TXT2}">{esc(lab)}</text>')
    o.append("</svg>")
    return f'<figure class="fig"><figcaption><b>{esc(title)}</b>{"<br><span>"+esc(sub)+"</span>" if sub else ""}</figcaption>' + "".join(o) + "</figure>"


def lines(series, xlabels, w=760, h=260, pad=(46, 90, 34, 52), title="", sub=""):
    """series: [(name, color, [values])]"""
    pt, pr, pb, pl = pad
    iw, ih = w - pl - pr, h - pt - pb
    allv = [v for _, _, vs in series for v in vs]
    lo, hi = min(allv + [0]), max(allv + [0]); span = (hi - lo) or 1
    lo -= span * .12; hi += span * .12; span = hi - lo
    def Y(v): return pt + ih * (hi - v) / span
    def X(i): return pl + (iw * i / max(len(xlabels) - 1, 1))
    o = [f'<svg viewBox="0 0 {w} {h}" role="img" width="100%" style="max-width:{w}px"><title>{esc(title)}</title>']
    for k in range(5):
        v = lo + span * k / 4; y = Y(v)
        o.append(f'<line x1="{pl}" x2="{w-pr}" y1="{y:.1f}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        o.append(f'<text x="{pl-8}" y="{y+4:.1f}" text-anchor="end" font-size="11" fill="{MUT}">{v:.1f}</text>')
    o.append(f'<line x1="{pl}" x2="{w-pr}" y1="{Y(0):.1f}" y2="{Y(0):.1f}" stroke="{TXT2}" stroke-width="1.5"/>')
    for i, lb in enumerate(xlabels):
        o.append(f'<text x="{X(i):.1f}" y="{h-pb+16}" text-anchor="middle" font-size="11" fill="{TXT2}">{esc(lb)}</text>')
    for name, col, vs in series:
        d = " ".join(("M" if i == 0 else "L") + f"{X(i):.1f},{Y(v):.1f}" for i, v in enumerate(vs))
        o.append(f'<path d="{d}" fill="none" stroke="{col}" stroke-width="2" stroke-linejoin="round"/>')
        for i, v in enumerate(vs):
            o.append(f'<circle cx="{X(i):.1f}" cy="{Y(v):.1f}" r="4.5" fill="{col}" stroke="{SURF}" stroke-width="2">'
                     f'<title>{esc(name)} {esc(xlabels[i])}: {v:+.2f}</title></circle>')
        o.append(f'<text x="{X(len(vs)-1)+10:.1f}" y="{Y(vs[-1])+4:.1f}" font-size="12" fill="{col}" font-weight="600">{esc(name)}</text>')
    o.append("</svg>")
    return f'<figure class="fig"><figcaption><b>{esc(title)}</b>{"<br><span>"+esc(sub)+"</span>" if sub else ""}</figcaption>' + "".join(o) + "</figure>"


# ── 차트 데이터 ─────────────────────────────────────────────
mn = ["1월","2월","3월","4월","5월","6월","7월","8월","9월","10월","11월","12월"]
c_month = bars([(mn[i], MJ["월"][m]["평균"], MJ["월"][m]["ci"][0], MJ["월"][m]["ci"][1])
                for i, m in enumerate(MONTHS)],
               title="진입 월별 카드 평균 (🟢실행 국면 · n=4,661)",
               sub="수염 = 연도블록 부트스트랩 95% CI. 다중비교(BH FDR 10%) 보정 후 살아남는 달은 0개.")
c_freq = bars([(mn[i], MJ["빈도"][m]["실행"]) for i, m in enumerate(MONTHS)],
              fmt="{:.0f}", unit="건", zero_base=True,
              title="월별 🟢실행 신호 발생 건수 (30년 누적)",
              sub="수익률이 아니라 기회의 수. 6·8·3월에 몰리고 12·4월이 가장 적다.")
c_tier = bars([(t, MJ["계층"][t]["평균"], MJ["계층"][t]["ci"][0], MJ["계층"][t]["ci"][1])
               for t in ("대형", "중형", "소형")], w=420,
              title="시총 계층별 카드 평균 (🟢실행)",
              sub="셋 다 CI>0. 그러나 계층 간 차이는 CI가 0을 포함 — 종목군 필터의 근거 없음.")
c_hz = lines([("카드", S1, [TJ["현행"][str(h)]["평균"] for h in HS]),
              ("순수보유", S2c, [TJ["보유"][str(h)]["평균"] for h in HS])],
             [f"{h}봉" for h in HS],
             title="지평별 평균 수익 — 카드 vs 순수보유",
             sub="카드는 지평에 거의 무반응(+1.77→+1.65). 단기 지평에선 순수보유보다 유의하게 낮다.")
c_risk = lines([("카드 최대손실", S1, [TJ["위험"][str(h)]["카드"]["worst"] for h in HS]),
                ("보유 최대손실", S2c, [TJ["위험"][str(h)]["보유"]["worst"] for h in HS])],
               [f"{h}봉" for h in HS],
               title="지평별 최대손실 — 카드가 사는 진짜 이유",
               sub="카드는 30년 1,437건 내내 최대 −15.1%로 고정. 순수보유는 126봉에서 −91.1%.")

TC = "유형_x"
M = pd.read_csv(F("휩쏘_시간축_이벤트.csv"), dtype={"code": str})
M = M[M["청산"].astype(str) != "진행중"]
G = M[(M["국면"] == "실행") & (M["창완결_126"] == True)]
tc = TC if TC in G.columns else "유형"
c_ab = lines([("A형", S1, [G[G[tc] == "A"][f"현행_{h}"].mean() * 100 for h in HS]),
              ("B형", S2c, [G[G[tc] == "B"][f"현행_{h}"].mean() * 100 for h in HS])],
             [f"{h}봉" for h in HS],
             title="유형별 지평 반응 — 시간축을 가르는 건 유형이다",
             sub="A형은 35봉 안에 100% 종료 → 지평 무반응. B형은 길수록 나빠져 126봉에서 마이너스.")

b = G["현행봉_40"].values.astype(float)
buck = [("1~5일", ((b >= 1) & (b <= 5))), ("6~10일", ((b >= 6) & (b <= 10))),
        ("11~20일", ((b >= 11) & (b <= 20))), ("21~39일", ((b >= 21) & (b <= 39))),
        ("40일 만기", (b == 40))]
c_hold = bars([(lb, float(m.mean() * 100)) for lb, m in buck], w=520, fmt="{:.1f}", zero_base=True,
              title="현행 40봉 카드의 실제 청산 시점 분포",
              sub="79.3%가 5일 안에 끝난다. 중앙 2일 · 평균 4.7일 — 이 시스템은 이미 단기매매다.")

grid_rows = "".join(
    f"<tr class='{'hit' if c['BH'] else ''}'><td>{c['H']}봉</td><td>{'없음' if c['trail']==0 else str(int(c['trail']*100))+'%'}</td>"
    f"<td>{'O' if c['목표'] else 'X'}</td><td class='n'>{c['평균']:+.2f}</td><td class='n'>{c['중앙']:+.2f}</td>"
    f"<td class='n'>{c['승률']:.1f}%</td><td class='n'>{c['d']:+.2f}</td>"
    f"<td class='n ci'>[{c['lo']:+.2f}, {c['hi']:+.2f}]</td><td class='n'>{c['p']:.3f}</td>"
    f"<td>{'★BH' if c['BH'] else ''}</td></tr>" for c in TJ["그리드"])

mon_rows = "".join(
    f"<tr><td>{mn[i]}</td><td class='n'>{MJ['월'][m]['n']}</td><td class='n'>{MJ['월'][m]['평균']:+.2f}</td>"
    f"<td class='n'>{MJ['월'][m]['중앙']:+.2f}</td><td class='n'>{MJ['월'][m]['승률']:.1f}%</td>"
    f"<td class='n ci'>[{MJ['월'][m]['ci'][0]:+.2f}, {MJ['월'][m]['ci'][1]:+.2f}]</td>"
    f"<td class='n'>{MJ['월대비'][m]['delta']:+.2f}</td><td class='n'>{MJ['월대비'][m]['p']:.3f}</td>"
    f"<td>{'★' if MJ['월대비'][m]['BH통과'] else '—'}</td></tr>" for i, m in enumerate(MONTHS))

hz_rows = "".join(
    f"<tr class='{'base' if h==40 else ''}'><td>{h}봉</td><td>{TJ['현행'][str(h)]['그룹']}</td>"
    f"<td class='n'>{TJ['현행'][str(h)]['평균']:+.2f}</td><td class='n'>{TJ['현행'][str(h)]['중앙']:+.2f}</td>"
    f"<td class='n'>{TJ['현행'][str(h)]['승률']:.1f}%</td>"
    f"<td class='n ci'>[{TJ['현행'][str(h)]['ci'][0]:+.2f}, {TJ['현행'][str(h)]['ci'][1]:+.2f}]</td>"
    f"<td class='n'>{TJ['현행'][str(h)]['실현봉중앙']:.0f}일</td>"
    f"<td class='n'>{TJ['현행'][str(h)]['목표']:.0f}/{TJ['현행'][str(h)]['손절']:.0f}/{TJ['현행'][str(h)]['만기']:.0f}</td>"
    f"<td class='n'>{TJ['위험'][str(h)]['카드']['worst']:.1f}</td>"
    f"<td class='n'>{TJ['위험'][str(h)]['보유']['worst']:.1f}</td></tr>" for h in HS)

HTML = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>휩쏘 · 종목군 월별 + 스윙/단기 분리 (2026-08-04)</title>
<style>
:root{{color-scheme:light;--s:{SURF};--t1:{TXT};--t2:{TXT2};--mut:{MUT};--grid:{GRID};--a:{S1};--b:{S2c}}}
*{{box-sizing:border-box}}
body{{margin:0;background:#f4f3ef;color:var(--t1);
 font:16px/1.7 -apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans KR","Malgun Gothic",sans-serif}}
.wrap{{max-width:880px;margin:0 auto;padding:32px 20px 80px}}
header{{border-bottom:3px solid var(--t1);padding-bottom:18px;margin-bottom:8px}}
h1{{font-size:28px;margin:0 0 6px;letter-spacing:-.4px}}
.meta{{color:var(--t2);font-size:14px}}
h2{{font-size:21px;margin:44px 0 6px;padding-top:16px;border-top:1px solid var(--grid)}}
h3{{font-size:16px;margin:26px 0 6px;color:var(--t2)}}
p{{margin:10px 0}}
.lead{{background:#fff;border:1px solid var(--grid);border-left:5px solid var(--a);
 padding:16px 20px;border-radius:8px;margin:18px 0}}
.warn{{border-left-color:{NEG}}}
.good{{border-left-color:{POS}}}
ol.k{{margin:12px 0;padding-left:22px}} ol.k li{{margin:8px 0}}
table{{width:100%;border-collapse:collapse;margin:14px 0;font-size:13.5px;background:#fff}}
th,td{{padding:7px 9px;border-bottom:1px solid var(--grid);text-align:left}}
th{{background:#efeee9;font-weight:600;font-size:12.5px;color:var(--t2)}}
td.n{{text-align:right;font-variant-numeric:tabular-nums}}
td.ci{{color:var(--t2);font-size:12.5px}}
tr.hit td{{background:#eef7f2}} tr.base td{{background:#eef3fb;font-weight:600}}
.fig{{margin:22px 0;padding:16px;background:#fff;border:1px solid var(--grid);border-radius:10px}}
.fig figcaption{{font-size:14px;margin-bottom:10px}}
.fig svg{{display:block;margin:0 auto}}
.fig figcaption span{{color:var(--t2);font-size:13px;font-weight:400}}
.two{{display:grid;grid-template-columns:1fr 1fr;gap:16px}}
@media(max-width:720px){{.two{{grid-template-columns:1fr}}}}
code,pre{{font-family:ui-monospace,Menlo,Consolas,monospace}}
pre{{background:#1a1a19;color:#e8e7e3;padding:14px 16px;border-radius:8px;overflow:auto;font-size:13px;line-height:1.6}}
.tag{{display:inline-block;white-space:nowrap;padding:2px 9px;border-radius:99px;font-size:12px;font-weight:600;
 background:#efeee9;color:var(--t2);margin-right:6px}}
.tag.no{{background:#fdeceb;color:#a32b2a}} .tag.yes{{background:#e7f6ef;color:#0e6b4b}}
footer{{margin-top:56px;padding-top:16px;border-top:1px solid var(--grid);color:var(--mut);font-size:13px}}
</style></head><body><div class="wrap">
<header>
<h1>휩쏘 · 종목군 월별 매매현황 + 스윙/단기 분리</h1>
<div class="meta">2026-08-04 · KOSPI+KOSDAQ 30년(1997-01~2026-07) ·
 종목군 검정 <b>7,071건</b> · 시간축 검정 공통표본 <b>1,437건</b> ·
 일관성 감사 <b>전 항목 통과</b></div>
</header>

<div class="lead warn">
<b>먼저 결론부터.</b> 오늘 두 과제 모두 <b>실전 카드에 반영되는 변경은 없다.</b>
종목군(시총 계층)도 월별 계절성도 다중비교 보정을 통과하지 못했다.
대신 <b>시스템의 정체를 하나 바로잡았다</b> — 휩쏘는 스윙 시스템이 아니라 <b>중앙 2일짜리 단기매매</b>다.
</div>

<h2>1. 종목군 = 시총 계층 (업종·테마는 왜 버렸나)</h2>
<p>형이 지정한 "제대로 된 종목군"을 <b>진입 시점 point-in-time 시총 계층</b>으로 정의했다.
시장별 횡단면 순위로 대형(1~100위)·중형(101~300위)·소형(301위~).</p>
<table><thead><tr><th>후보</th><th>판정</th><th>사유</th></tr></thead><tbody>
<tr><td><b>시총 계층</b></td><td><span class="tag yes">채택</span></td>
<td>30년 전구간 point-in-time · 이벤트 커버리지 <b>100.0%</b> · 상폐사 포함</td></tr>
<tr><td>업종 (161종)</td><td><span class="tag no">기각</span></td>
<td>업종 맵이 현재 상장사 스냅샷 → 커버리지 87%지만 1995~99 <b>56.5%</b> · 2000~04 68.3%.
결측이 곧 상폐사라 <b>생존편향을 종목군 축에 심는 꼴</b></td></tr>
<tr><td>테마(반도체 체인)</td><td><span class="tag no">기각</span></td>
<td>65종 → 이벤트 커버리지 <b>5.5%</b>. 통계가 나오지 않는다</td></tr>
</tbody></table>
<p><b>기술 함정 하나</b>: 시장 소속을 정적 맵으로 붙이면 KOSDAQ→KOSPI 이전 <b>112종</b>이
두 시장에 중복 매칭되어 표본이 7,071 → 7,435건으로 <b>364건 부풀었다</b>(첫 실행에서 실제 발생).
구간 맵으로 해소했다.</p>

{c_tier}

<div class="lead">
<b>시총 계층은 리프트가 아니다.</b> 소형이 점추정 +0.96%p 앞서지만 부트 95% CI
[−1.13, +2.42] — 0을 포함한다. 중형−대형도 [−0.61, +1.02].
<b>종목군으로 가려 담을 근거가 없다.</b> 소형의 우위는 슬리피지를 태우면 남지 않을 크기다.
</div>

<h2>2. 월별 매매현황 — 보정하면 사라진다</h2>
{c_month}
<table><thead><tr><th>월</th><th>n</th><th>평균%</th><th>중앙%</th><th>승률</th>
<th>부트 95% CI</th><th>Δ vs 나머지</th><th>p</th><th>BH</th></tr></thead>
<tbody>{mon_rows}</tbody></table>
<p>보정 없이 보면 6개월이 유의해 보이고, "이 달이 다른가"로 물으면 5월(−2.10%p, p=0.023) 하나만 남는다.
<b>12개 동시검정에 BH FDR 10%를 걸면 통과하는 달은 0개다.</b>
12개를 동시에 보면 하나쯤 p=0.02가 나오는 건 우연의 정상 범위다.</p>
<p>다만 <b>방향은 기존 결론과 어긋나지 않는다</b>: 9~10월 진입 약세(+0.40% vs 전체 +1.74%)와
5월 약세는 §2-5의 "4~5월은 목표가 아니라 데드라인"과 정합한다.
<b>기존 사이클 결론을 뒤집지도, 강화하지도 못했다.</b> 통계적으로는 "모른다"가 정답이다.</p>

<h3>다만 '기회의 수'는 확실한 운영 정보다</h3>
{c_freq}
<p>3월은 <b>실행비율 91.1%</b>로 압도적이다(휩쏘가 3월에 나면 거의 항상 🟢실행 국면).
반대로 12월 52.2% · 5월 53.6% · 11월 54.0%은 <b>절반이 🟢가 아니다</b>.
"왜 12월엔 신호가 안 뜨지?"의 답이고, 자금 배분 준비에 쓸 사실이다. 수익률 주장이 아니다.</p>

<h3>국면 게이트는 세 계층 모두에서 작동한다 — 오늘의 가장 확실한 산출</h3>
<table><thead><tr><th>계층</th><th>🟢실행</th><th>🟡주의</th><th>🔴관찰만</th></tr></thead><tbody>
<tr><td>대형</td><td class="n">+1.47% (55.1%)</td><td class="n">+0.53% (50.3%)</td><td class="n">−0.12% (45.8%)</td></tr>
<tr><td>중형</td><td class="n">+1.74% (56.9%)</td><td class="n">−0.75% (42.0%)</td><td class="n">−1.16% (39.2%)</td></tr>
<tr><td>소형</td><td class="n">+2.43% (59.9%)</td><td class="n">−0.87% (42.3%)</td><td class="n">−0.37% (43.8%)</td></tr>
</tbody></table>
<p>세 계층 전부 실행 &gt; 주의 &gt; 관찰만 순서가 유지된다. <b>게이트는 종목군을 타지 않는다.</b>
(새 관찰: 🟡주의에서 대형만 +0.53%로 버틴다. 사후 발견이므로 규칙에 반영하지 않고 적어만 둔다.)</p>

<h2>3. 스윙/단기 분리 — 시스템은 이미 단기매매였다</h2>
{c_hold}
<div class="lead warn">
현행 40봉 카드의 실제 청산은 <b>중앙 2일 · 평균 4.7일 · 79.3%가 5일 이내</b>.
인수인계 §10-2의 "현재 시스템은 40~126거래일 단일 시간축이다"라는 전제 자체가 틀렸다.
<b>40봉·126봉은 '최대 대기 한도'이지 '목표 보유기간'이 아니다.</b>
</div>

{c_hz}
<table><thead><tr><th>지평</th><th>구분</th><th>평균%</th><th>중앙%</th><th>승률</th>
<th>부트 95% CI</th><th>실현봉</th><th>목표/손절/만기 %</th><th>카드 최대손실</th><th>보유 최대손실</th></tr></thead>
<tbody>{hz_rows}</tbody></table>
<p>평균은 지평에 거의 무반응(+1.77 → +1.65, 폭 0.12%p)인데 <b>중앙값은 +2.86% → +0.10%로 무너진다</b>.
지평을 늘리면 좋아지는 게 아니라 <b>만기 청산분이 손절로 바뀔 뿐</b>이다(만기 21% → 0%).</p>

<h3>카드는 알파 장치가 아니라 생존 장치다</h3>
{c_risk}
<p>단기 지평(5·10봉)에서 <b>카드는 순수보유보다 유의하게 나쁘다</b>(−1.60%p CI[−2.51,−0.75] · −1.75%p CI[−3.10,−0.27]).
정직하게 적는다. 그런데 같은 표본에서 —</p>
<div class="lead good">
<b>카드는 30년 1,437건 동안 −20% 이하 손실이 단 한 건도 없다. 최대손실 −15.1%.</b><br>
순수보유는 40봉에서 16.0%가 −20% 이하로 가고, 126봉에서는 34.4% · 최악 −91.1%.<br>
→ 카드는 평균 1.6%p를 내주고 <b>−91%를 −15%로 바꾼다</b>. 이 교환이 카드의 값어치다.
</div>

<h3>시간축을 가르는 건 지평이 아니라 신호 유형이다</h3>
{c_ab}
<table><thead><tr><th></th><th>A형 (n=1,275)</th><th>B형 (n=162)</th></tr></thead><tbody>
<tr><td>청산 중앙</td><td class="n"><b>2일</b></td><td class="n"><b>10일</b></td></tr>
<tr><td>청산 평균</td><td class="n">3.4일</td><td class="n">15.6일</td></tr>
<tr><td>최대</td><td class="n">35일</td><td class="n">40일</td></tr>
<tr><td>5일 이내 종료</td><td class="n"><b>85.6%</b></td><td class="n">30.2%</td></tr>
<tr><td>지평 반응</td><td>무반응 (H5 +1.88% = H126 +1.88%)</td><td><b>단조 악화</b> (+0.89% → −0.22%)</td></tr>
<tr><td>승률 (5봉 → 126봉)</td><td class="n">55.4% → 53.0%</td><td class="n"><b>50.0% → 27.8%</b></td></tr>
</tbody></table>
<p><b>B형은 시간이 적이다.</b> 126봉까지 끌면 평균이 마이너스로 돌아선다.
이건 §1의 "B는 A보다 열등(청산승률 34%)"을 <b>왜 열등한지</b>로 바꿔 놓는다 —
B는 신호가 나쁜 게 아니라 <b>너무 오래 들고 있어서</b> 나빴다. (⚠️ n=162, 사전등록 대상)</p>

<h2>4. 정책 그리드 48셀 — 지평별 최적 트레일은 갈리지 않는다</h2>
<p>목표를 쓰는 한 트레일 8~20%의 차이는 <b>전 지평에서 0.1%p 이내</b>.
"단기는 타이트하게, 스윙은 느슨하게"라는 가설은 데이터에 흔적이 없다.
이유는 이미 나왔다 — 목표가 대부분 2일 안에 닿아 <b>트레일이 발동할 기회 자체가 없다</b>.</p>
<p>BH FDR 10%를 통과한 <b>14셀은 전부 '목표 미사용'</b> 계열이다. 그러나 —</p>
<table><thead><tr><th>정책</th><th>평균%</th><th>중앙%</th><th>승률</th><th>표준편차</th><th>5%분위</th></tr></thead><tbody>
<tr class="base"><td>현행 40봉 (기준)</td><td class="n">+1.72</td><td class="n"><b>+2.33</b></td><td class="n"><b>50.7%</b></td><td class="n"><b>8.66</b></td><td class="n">−8.80</td></tr>
<tr><td>63봉/12%/목표X</td><td class="n"><b>+2.81</b></td><td class="n">−3.20</td><td class="n">41.3%</td><td class="n">14.37</td><td class="n">−8.64</td></tr>
<tr><td>40봉/12%/목표X</td><td class="n">+2.75</td><td class="n">−3.04</td><td class="n">41.7%</td><td class="n">13.82</td><td class="n">−8.64</td></tr>
<tr class="hit"><td>5봉/12%/목표X</td><td class="n">+2.65</td><td class="n">+0.41</td><td class="n">50.8%</td><td class="n">10.03</td><td class="n">−8.33</td></tr>
</tbody></table>
<p><b>대가</b>: 평균 +1.09%p를 얻고 <b>중앙값 −5.53%p · 승률 −9.4%p · 표준편차 +66%</b>를 낸다.
§3의 "잔여의 상위 5%가 평균의 42%를 만든다 → 체감되지 않는 개선"과 같은 이유로 <b>기각</b>.
단 <code>5봉/12%/목표X</code>만 승률을 지키면서 평균을 올려 <b>사전등록 후보</b>로 남긴다.</p>

<details><summary style="cursor:pointer;color:var(--t2);font-size:14px;margin:12px 0">
▸ 48셀 전체 펼치기 (기준 = 현행 40봉)</summary>
<table><thead><tr><th>지평</th><th>트레일</th><th>목표</th><th>평균%</th><th>중앙%</th><th>승률</th>
<th>Δ</th><th>부트 95% CI</th><th>p</th><th>BH</th></tr></thead><tbody>{grid_rows}</tbody></table>
</details>

<h2>5. 사전등록 (등록일 2026-08-04 · 중간판정 금지)</h2>
<pre>[5-1] B형 5봉 청산 — 등록
  가설   B형을 5거래일 만기로 자르면 현행 40봉 대비 평균이 열등하지 않고 승률은 우월
  신호   현행 B형과 모든 조건 동일, 만기만 40봉 → 5봉
  근거   5봉 +0.89%/승률 50.0%  vs  40봉 +0.46%/승률 32.1%  (사후 관찰)
  판정   2026-08-05 이후 🟢실행 B형 40건 누적. 그 전 중간판정 금지. 최대 대기 2029-12-31
  채택   평균 Δ ≥ −0.5%p  AND  승률 Δ ≥ +5%p
  구속   지평 사후조정 금지(5봉 고정) · 표본 연장 금지 · 국면 사후선택 금지

[5-2] A형 5봉/트레일12%/목표미사용 — 등록 (관찰만)
  근거   +2.65% vs 현행 +1.72% (Δ+0.93%p, BH 통과) · 승률 50.8% vs 50.7%
  보류   중앙값이 −1.92%p 낮고, 48셀 다중비교의 승자라 '승자의 저주'를 배제 못함
  판정   🟢실행 A형 60건 누적 (중앙값 손실의 체감 여부가 핵심이라 표본을 더 요구)
  채택   평균 Δ > 0  AND  중앙값 Δ ≥ −1.0%p  AND  승률 Δ ≥ −2%p

[사전 기각 · 재론 금지]
  · 지평별 트레일 차등화 — 전 지평 폭 0.1%p 이내. 근거 없음
  · A형 지평 연장(40 → 63·126) — 35봉 안에 100% 종료. 물리적으로 무의미
  · '스윙 트랙' 신설 — 40봉 이상 보유되는 건이 A형 0% · 전체 1.5%. 트랙 만들 표본 없음
  · 시총 계층 필터 · 월별 매매 중단 — 다중비교 보정 후 근거 소멸</pre>

<h2>6. 실전 카드 — 이번 판 변경 없음</h2>
<pre>[휩쏘 카드 · 시간축 인식 정정 — 2026-08-04]
▸ 이 시스템은 스윙이 아니다. A형 중앙 2일 · B형 중앙 10일의 단기매매다.
▸ 40봉/126봉은 '최대 대기 한도'이지 '목표 보유기간'이 아니다.
▸ A형은 40봉 안에 100% 끝난다. 40봉이 지나도 안 끝났다면 데이터 오류를 의심할 것.
▸ B형은 오래 끌수록 나빠진다. 5봉 청산을 사전등록해 전진검증 중.
▸ 카드의 값어치는 평균이 아니라 하방이다: 30년 −20% 이하 손실 0건, 최대 −15.1%.
▸ 종목군·월로는 아무것도 켜거나 끄지 않는다. 우선순위는 그대로
  국면 &gt; 신호등급 &gt; 밸류.</pre>

<h2>7. 일관성 감사 (재현: <code>py 휩쏘_일관성감사_0804.py</code>)</h2>
<ul>
<li>⑥시간축 엔진의 <code>back_adjust</code>·<code>era_limit</code> ≡ 원본 <code>휩쏘_역사검정.py</code> (최대차 0.0e+00)</li>
<li><b>①2단청산 <code>P0_카드</code> ≡ ⑥<code>현행_40</code> — 교집합 2,786건 최대차 0.0e+00</b> (완전일치)</li>
<li>①<code>P0_H126</code> ≡ ⑥<code>현행_126</code> — 2,163건 최대차 0.0e+00</li>
<li>원장 <code>카드수익</code> ↔ ⑥<code>현행_40</code> 최대오차 0.05%p (원장은 소수 1자리 저장)</li>
<li>⑤계층 부여 후 표본 보존 7,071 → 7,071 · (date,code) 중복 0 · 국면 분포 보존</li>
<li>look-ahead 차단: 스냅숏 ≤ 진입일 위반 0건 (최대 지연 34일)</li>
<li>논리: 국면 순서 3계층 유지 · 9~10월 약세 방향 일치 · A형 ≤ 40봉 · B형 단조 감소 ·
카드 최대손실 &lt; 보유 최대손실 (전 지평)</li>
</ul>

<h2>8. 한계 — 모든 결론에 붙는 정직 고지</h2>
<ul>
<li><b>거래비용이 이번 검정의 가장 아픈 지점이다.</b> 중앙 2일 청산이면 회전이 매우 빠르다.
편도 0.5%면 왕복 1%가 평균 +1.72%에서 빠진다 — <b>비용을 태우면 카드의 우위는 절반 이하</b>다.
다음 과제로 넘긴다.</li>
<li><b>업종 축을 포기했다.</b> 형이 관심 있는 반도체 체인의 월별 패턴은 이번 검정에 없다.
하려면 point-in-time 업종 맵을 새로 수집해야 한다.</li>
<li><b>B형 n=162.</b> 단조 패턴은 6개 지평에서 일관되지만 표본이 작다.</li>
<li><b>월별 표본 부족.</b> 12월 209건 · 4월 235건. 30년치인데도 이 정도다.</li>
<li><b>공통표본 1,437건</b>은 원장 2,801건의 51%. 잘린 쪽은 최근 진입분(2025~26)에 몰린다.</li>
<li><b>36셀 교차·48셀 그리드는 사후분해</b>다. BH는 FDR 통제이지 개별 셀의 진위 보증이 아니다.</li>
<li><b>생존편향·위기해 클러스터·슬리피지</b>는 기존 검정과 동일하게 남아 있다.</li>
</ul>

<footer>
재현: <code>py 휩쏘_종목군월별_검정.py</code> · <code>py 휩쏘_시간축분리_검정.py</code> →
<code>py 휩쏘_시간축_분석.py</code> · <code>py 휩쏘_일관성감사_0804.py</code><br>
원자료: <code>휩쏘_종목군월별_이벤트.csv</code>(7,071) · <code>휩쏘_시간축_이벤트.csv</code>(2,801 × 지평6 × 정책8)<br>
2026-08-04 · 진우퀀트 · 휩쏘
</footer>
</div></body></html>"""

open(f"{HERE}/휩쏘_0804_리포트.html", "w", encoding="utf-8").write(HTML)
print("저장: 휩쏘_0804_리포트.html", len(HTML), "bytes")
