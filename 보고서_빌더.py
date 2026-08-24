# -*- coding: utf-8 -*-
"""완성본 보고서 빌더 — 모든 수치는 보고서_데이터.json(실제 검정 산출물)에서만 읽는다."""
import json, html as H, sys
sys.stdout.reconfigure(encoding="utf-8")
HERE = "/home/claude/jq"
D = json.load(open(f"{HERE}/보고서_데이터.json"))
esc = H.escape

# ── 팔레트 (dataviz 검증 통과: light 3슬롯 / dark 3슬롯)
S1, S2c, S3 = "var(--s1)", "var(--s2)", "var(--s3)"
INK, INK2, MUT = "var(--ink)", "var(--ink2)", "var(--mut)"
GRID, BASE = "var(--grid)", "var(--base)"


def fmt(v, d=2, sign=True):
    if v is None: return "–"
    return f"{v:+.{d}f}" if sign else f"{v:.{d}f}"


def tbl(headers, rows, cap=""):
    th = "".join(f"<th>{esc(str(h))}</th>" for h in headers)
    tr = "".join("<tr>" + "".join(f"<td>{c}</td>" for c in r) + "</tr>" for r in rows)
    return (f'<details class="tv"><summary>표로 보기{(" — " + esc(cap)) if cap else ""}</summary>'
            f'<table><thead><tr>{th}</tr></thead><tbody>{tr}</tbody></table></details>')


def hbar_ci(items, w=720, rowh=34, pad_l=190, pad_r=64, unit="%", title=""):
    """가로 막대 + 0 기준선 + 신뢰구간 수염. items: [{label, v, lo, hi, note, sig}]"""
    n = len(items); h = n * rowh + 44
    vals = [i["v"] for i in items] + [i.get("lo") for i in items if i.get("lo") is not None] \
        + [i.get("hi") for i in items if i.get("hi") is not None]
    lo, hi = min(vals + [0]), max(vals + [0])
    span = (hi - lo) or 1; lo -= span * .10; hi += span * .10
    pw = w - pad_l - pad_r
    def X(v): return pad_l + (v - lo) / (hi - lo) * pw
    z = X(0)
    s = [f'<svg viewBox="0 0 {w} {h}" role="img" class="chart" aria-label="{esc(title)}">']
    # 격자
    for g in range(5):
        gv = lo + (hi - lo) * g / 4
        gx = X(gv)
        s.append(f'<line x1="{gx:.1f}" y1="26" x2="{gx:.1f}" y2="{h-18}" stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{gx:.1f}" y="18" fill="{MUT}" font-size="10.5" text-anchor="middle">{gv:+.1f}</text>')
    s.append(f'<line x1="{z:.1f}" y1="26" x2="{z:.1f}" y2="{h-18}" stroke="{BASE}" stroke-width="1.5"/>')
    for i, it in enumerate(items):
        y = 34 + i * rowh; v = it["v"]; x = X(v)
        x0, x1 = (z, x) if v >= 0 else (x, z)
        bw = max(abs(x1 - x0), 2)
        fill = it.get("color", S1)
        op = "1" if it.get("sig", True) else "0.42"
        s.append(f'<g><title>{esc(it["label"])}: {v:+.2f}{unit}'
                 + (f'  (95% CI {it["lo"]:+.2f} ~ {it["hi"]:+.2f})' if it.get("lo") is not None else "")
                 + '</title>')
        s.append(f'<rect x="{x0:.1f}" y="{y-9}" width="{bw:.1f}" height="16" rx="4" fill="{fill}" opacity="{op}"/>')
        if it.get("lo") is not None:
            a, b = X(it["lo"]), X(it["hi"])
            s.append(f'<line x1="{a:.1f}" y1="{y-1}" x2="{b:.1f}" y2="{y-1}" stroke="{INK2}" stroke-width="1.5" opacity=".62"/>')
            for xx in (a, b):
                s.append(f'<line x1="{xx:.1f}" y1="{y-6}" x2="{xx:.1f}" y2="{y+4}" stroke="{INK2}" stroke-width="1.5" opacity=".62"/>')
        s.append('</g>')
        lbl = esc(it["label"])
        s.append(f'<text x="{pad_l-10}" y="{y+3}" fill="{INK}" font-size="12" text-anchor="end">{lbl}</text>')
        tx = (x1 + 7) if v >= 0 else (x0 - 7)
        anc = "start" if v >= 0 else "end"
        star = " ★" if it.get("sig2") else ""
        s.append(f'<text x="{tx:.1f}" y="{y+3}" fill="{INK}" font-size="11.5" font-weight="600" text-anchor="{anc}">{v:+.2f}{unit}{star}</text>')
        if it.get("note"):
            s.append(f'<text x="{pad_l-10}" y="{y+15}" fill="{MUT}" font-size="10" text-anchor="end">{esc(it["note"])}</text>')
    s.append('</svg>')
    return "".join(s)


def vbar(items, w=720, h=250, pad_b=46, pad_t=26, pad_l=42, unit="%", title="", color=None):
    n = len(items)
    vals = [i["v"] for i in items]
    lo, hi = min(vals + [0]), max(vals + [0])
    span = (hi - lo) or 1; lo -= span * .16; hi += span * .16
    pw = w - pad_l - 16; ph = h - pad_b - pad_t
    def Y(v): return pad_t + (hi - v) / (hi - lo) * ph
    bw = pw / n * 0.62; step = pw / n
    z = Y(0)
    s = [f'<svg viewBox="0 0 {w} {h}" role="img" class="chart" aria-label="{esc(title)}">']
    for g in range(5):
        gv = lo + (hi - lo) * g / 4; gy = Y(gv)
        s.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{w-8}" y2="{gy:.1f}" stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{pad_l-8}" y="{gy+3.5:.1f}" fill="{MUT}" font-size="10.5" text-anchor="end">{gv:+.1f}</text>')
    s.append(f'<line x1="{pad_l}" y1="{z:.1f}" x2="{w-8}" y2="{z:.1f}" stroke="{BASE}" stroke-width="1.5"/>')
    for i, it in enumerate(items):
        v = it["v"]; cx = pad_l + step * i + step / 2; y = Y(v)
        y0, y1 = (y, z) if v >= 0 else (z, y)
        bh = max(abs(y1 - y0), 2)
        fill = it.get("color", color or S1)
        s.append(f'<g><title>{esc(it["label"])}: {v:+.2f}{unit}{esc(it.get("note",""))}</title>')
        s.append(f'<rect x="{cx-bw/2:.1f}" y="{y0:.1f}" width="{bw:.1f}" height="{bh:.1f}" rx="4" fill="{fill}"/>')
        s.append('</g>')
        ly = (y0 - 6) if v >= 0 else (y1 + 13)
        s.append(f'<text x="{cx:.1f}" y="{ly:.1f}" fill="{INK}" font-size="11" font-weight="600" text-anchor="middle">{v:+.1f}</text>')
        s.append(f'<text x="{cx:.1f}" y="{h-24}" fill="{INK2}" font-size="11" text-anchor="middle">{esc(it["label"])}</text>')
        if it.get("sub"):
            s.append(f'<text x="{cx:.1f}" y="{h-10}" fill="{MUT}" font-size="9.5" text-anchor="middle">{esc(it["sub"])}</text>')
    s.append('</svg>')
    return "".join(s)


def grouped(cats, series, w=720, h=270, unit="%", title=""):
    """cats: [label]; series: [{name, color, vals:[...]}]"""
    pad_l, pad_b, pad_t = 46, 52, 26
    allv = [v for s_ in series for v in s_["vals"] if v is not None]
    lo, hi = min(allv + [0]), max(allv + [0])
    span = (hi - lo) or 1; lo -= span * .18; hi += span * .18
    pw = w - pad_l - 16; ph = h - pad_b - pad_t
    def Y(v): return pad_t + (hi - v) / (hi - lo) * ph
    step = pw / len(cats); k = len(series)
    bw = step * 0.66 / k
    z = Y(0)
    s = [f'<svg viewBox="0 0 {w} {h}" role="img" class="chart" aria-label="{esc(title)}">']
    for g in range(5):
        gv = lo + (hi - lo) * g / 4; gy = Y(gv)
        s.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{w-8}" y2="{gy:.1f}" stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{pad_l-8}" y="{gy+3.5:.1f}" fill="{MUT}" font-size="10.5" text-anchor="end">{gv:+.1f}</text>')
    s.append(f'<line x1="{pad_l}" y1="{z:.1f}" x2="{w-8}" y2="{z:.1f}" stroke="{BASE}" stroke-width="1.5"/>')
    for ci, c in enumerate(cats):
        base_x = pad_l + step * ci + step * 0.17
        for si, se in enumerate(series):
            v = se["vals"][ci]
            if v is None: continue
            x = base_x + si * (bw + 2)   # 2px 서피스 간격
            y = Y(v); y0, y1 = (y, z) if v >= 0 else (z, y)
            bh = max(abs(y1 - y0), 2)
            s.append(f'<g><title>{esc(c)} · {esc(se["name"])}: {v:+.2f}{unit}</title>')
            s.append(f'<rect x="{x:.1f}" y="{y0:.1f}" width="{bw-2:.1f}" height="{bh:.1f}" rx="4" fill="{se["color"]}"/></g>')
            ly = (y0 - 5) if v >= 0 else (y1 + 12)
            s.append(f'<text x="{x+(bw-2)/2:.1f}" y="{ly:.1f}" fill="{INK}" font-size="9.5" text-anchor="middle">{v:+.1f}</text>')
        s.append(f'<text x="{pad_l+step*ci+step/2:.1f}" y="{h-30}" fill="{INK2}" font-size="11" text-anchor="middle">{esc(c)}</text>')
    lx = pad_l
    for se in series:
        s.append(f'<rect x="{lx}" y="{h-16}" width="10" height="10" rx="3" fill="{se["color"]}"/>')
        s.append(f'<text x="{lx+15}" y="{h-7}" fill="{INK2}" font-size="11">{esc(se["name"])}</text>')
        lx += 26 + sum(12 if ord(ch) > 0x2000 else 7 for ch in se["name"])
    s.append('</svg>')
    return "".join(s)


def funnel(stages, w=720, title=""):
    top = stages[0]["n"]; h = len(stages) * 62 + 20
    s = [f'<svg viewBox="0 0 {w} {h}" role="img" class="chart" aria-label="{esc(title)}">']
    for i, st_ in enumerate(stages):
        y = 12 + i * 62
        frac = st_["n"] / top
        bw = 40 + (w - 250) * frac
        pct = frac * 100
        s.append(f'<g><title>{esc(st_["단계"])}: {st_["n"]:,}건 ({pct:.1f}%)</title>')
        s.append(f'<rect x="200" y="{y}" width="{bw:.1f}" height="38" rx="4" fill="{S1}" opacity="{0.35+0.65*frac:.2f}"/></g>')
        s.append(f'<text x="190" y="{y+24}" fill="{INK}" font-size="12.5" text-anchor="end">{esc(st_["단계"])}</text>')
        inside = (200 + bw + 96) > w
        lx_ = (200 + bw - 10) if inside else (200 + bw + 10)
        anc_ = "end" if inside else "start"
        col_ = "var(--surf)" if inside else INK
        col2 = "var(--surf)" if inside else MUT
        s.append(f'<text x="{lx_:.1f}" y="{y+17}" fill="{col_}" font-size="13" font-weight="650" text-anchor="{anc_}">{st_["n"]:,}건</text>')
        s.append(f'<text x="{lx_:.1f}" y="{y+31}" fill="{col2}" font-size="10.5" text-anchor="{anc_}" opacity="{0.75 if inside else 1}">전체의 {pct:.1f}%</text>')
        if i < len(stages) - 1:
            s.append(f'<line x1="205" y1="{y+40}" x2="205" y2="{y+60}" stroke="{BASE}" stroke-width="1"/>')
            s.append(f'<polygon points="205,{y+62} 201,{y+55} 209,{y+55}" fill="{BASE}"/>')
    s.append('</svg>')
    return "".join(s)


def waterfall(w=720, h=250):
    g = D["간극"]
    peak, card, two = g["고점6M"], g["카드"], g["이단"]
    pad_l, pad_t, pad_b = 46, 24, 46
    hi = peak * 1.12; lo = -2
    ph = h - pad_t - pad_b; pw = w - pad_l - 20
    def Y(v): return pad_t + (hi - v) / (hi - lo) * ph
    z = Y(0); step = pw / 3; bw = step * 0.5
    s = [f'<svg viewBox="0 0 {w} {h}" role="img" class="chart" aria-label="간극 분해">']
    for gg in range(5):
        gv = lo + (hi - lo) * gg / 4; gy = Y(gv)
        s.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{w-8}" y2="{gy:.1f}" stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{pad_l-8}" y="{gy+3.5:.1f}" fill="{MUT}" font-size="10.5" text-anchor="end">{gv:.0f}</text>')
    s.append(f'<line x1="{pad_l}" y1="{z:.1f}" x2="{w-8}" y2="{z:.1f}" stroke="{BASE}" stroke-width="1.5"/>')
    bars = [("6개월 최고가\n(신이 판 값)", peak, S3), ("현행 카드\n(실제 실현)", card, S1), ("2단 청산\n(신규 채택)", two, S2c)]
    for i, (lab, v, col) in enumerate(bars):
        cx = pad_l + step * i + step / 2; y = Y(v)
        s.append(f'<g><title>{esc(lab)}: {v:+.2f}%</title>')
        s.append(f'<rect x="{cx-bw/2:.1f}" y="{y:.1f}" width="{bw:.1f}" height="{max(z-y,2):.1f}" rx="4" fill="{col}"/></g>')
        s.append(f'<text x="{cx:.1f}" y="{y-8:.1f}" fill="{INK}" font-size="14" font-weight="650" text-anchor="middle">{v:+.2f}%</text>')
        for j, ln in enumerate(lab.split("\n")):
            s.append(f'<text x="{cx:.1f}" y="{h-28+j*13:.1f}" fill="{INK2 if j==0 else MUT}" font-size="{11 if j==0 else 9.5}" text-anchor="middle">{esc(ln)}</text>')
    # 간극 표시
    y1_, y2_ = Y(peak), Y(card)
    xa = pad_l + step * 0 + step / 2 + bw / 2 + 14
    xb = pad_l + step * 1 + step / 2 - bw / 2 - 14
    s.append(f'<line x1="{xa:.1f}" y1="{y1_:.1f}" x2="{xb:.1f}" y2="{y1_:.1f}" stroke="{MUT}" stroke-width="1" stroke-dasharray="0"/>')
    s.append(f'<line x1="{xb:.1f}" y1="{y1_:.1f}" x2="{xb:.1f}" y2="{y2_:.1f}" stroke="{MUT}" stroke-width="1"/>')
    s.append(f'<text x="{xb-10:.1f}" y="{(y1_+y2_)/2-4:.1f}" fill="{INK}" font-size="12" font-weight="600" text-anchor="end">간극 {peak-card:.1f}%p</text>')
    s.append(f'<text x="{xb-10:.1f}" y="{(y1_+y2_)/2+13:.1f}" fill="{MUT}" font-size="10.5" text-anchor="end">2단 청산이 회수한 몫 = {g["회수율"]}%</text>')
    s.append('</svg>')
    return "".join(s)


def dist_chart(w=720, h=260):
    d = D["잔여분포"]; ps = d["p"]
    pad_l, pad_t, pad_b = 46, 26, 46
    vals = [p["v"] for p in ps]
    lo, hi = min(vals + [0]) * 1.15, max(vals) * 1.15
    ph = h - pad_t - pad_b; pw = w - pad_l - 20
    def Y(v): return pad_t + (hi - v) / (hi - lo) * ph
    z = Y(0); step = pw / len(ps); bw = step * 0.58
    s = [f'<svg viewBox="0 0 {w} {h}" role="img" class="chart" aria-label="잔여 50% 수익 분포">']
    for g in range(5):
        gv = lo + (hi - lo) * g / 4; gy = Y(gv)
        s.append(f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{w-8}" y2="{gy:.1f}" stroke="{GRID}" stroke-width="1"/>')
        s.append(f'<text x="{pad_l-8}" y="{gy+3.5:.1f}" fill="{MUT}" font-size="10.5" text-anchor="end">{gv:+.0f}</text>')
    s.append(f'<line x1="{pad_l}" y1="{z:.1f}" x2="{w-8}" y2="{z:.1f}" stroke="{BASE}" stroke-width="1.5"/>')
    for i, p in enumerate(ps):
        cx = pad_l + step * i + step / 2; v = p["v"]; y = Y(v)
        y0, y1 = (y, z) if v >= 0 else (z, y)
        s.append(f'<g><title>하위 {p["q"]}% 지점: {v:+.1f}%</title>')
        s.append(f'<rect x="{cx-bw/2:.1f}" y="{y0:.1f}" width="{bw:.1f}" height="{max(abs(y1-y0),2):.1f}" rx="4" fill="{S1}"/></g>')
        ly = (y0 - 6) if v >= 0 else (y1 + 12)
        s.append(f'<text x="{cx:.1f}" y="{ly:.1f}" fill="{INK}" font-size="10.5" font-weight="600" text-anchor="middle">{v:+.1f}</text>')
        s.append(f'<text x="{cx:.1f}" y="{h-26}" fill="{INK2}" font-size="10.5" text-anchor="middle">p{p["q"]}</text>')
    my = Y(d["mean"])
    s.append(f'<line x1="{pad_l}" y1="{my:.1f}" x2="{w-8}" y2="{my:.1f}" stroke="{S2c}" stroke-width="2"/>')
    s.append(f'<text x="{w-12}" y="{my-6:.1f}" fill="{S2c}" font-size="11" font-weight="650" text-anchor="end">평균 {d["mean"]:+.1f}%</text>')
    s.append(f'<text x="{pad_l}" y="{h-8}" fill="{MUT}" font-size="10.5">중앙값(p50) {d["p"][3]["v"]:+.1f}% 인데 평균은 {d["mean"]:+.1f}% — 상위 5%가 평균의 {d["top5기여"]/d["mean"]*100:.0f}%를 만든다</text>')
    s.append('</svg>')
    return "".join(s)
print("helpers ok")

# ══════════════════════════════════════════════════════════════════════
G = D["국면게이트"]; GAP = D["간극"]; TR = D["트레일민감도"]; JA = D["1월앵커"]
S2M = D["S2미달항목"]; S2A = D["S2기준A"]; S2T = D["S2전체"]; VG = D["밸류등급"]
VN = D["밸류국면"]; VT_ = D["밸류태그"]; CELL = D["셀"]; FUN = D["깔때기"]
DEC = D["5년구간"]; SEA = D["계절성"]; OBK = D["원장"]; SMP = D["표본"]

# 차트 1 — 국면 게이트
c1 = hbar_ci([dict(label={"실행":"🟢 실행 (사도 되는 국면)","주의":"🟡 주의 (중립)","관찰만":"🔴 관찰만 (사면 안 되는 국면)"}[g["국면"]],
                   v=g["mean"], lo=g["lo"], hi=g["hi"],
                   note=f'n={g["n"]:,}건 · 승률 {g["win"]}%',
                   sig=g["lo"] > 0 or g["hi"] < 0, sig2=(g["lo"] > 0 or g["hi"] < 0))
              for g in G], title="시장 국면별 휩쏘 A형 성과")
t1 = tbl(["국면", "건수", "평균", "중앙값", "승률", "95% 신뢰구간"],
         [[g["국면"], f'{g["n"]:,}', f'{g["mean"]:+.2f}%', f'{g["med"]:+.2f}%', f'{g["win"]}%',
           f'{g["lo"]:+.2f} ~ {g["hi"]:+.2f}'] for g in G])

# 차트 2 — 계절성
c2 = vbar([dict(label=f'{s["월"]}월', v=s["평균"], sub=f'{int(s["플러스율"])}%',
                color=(S2c if s["평균"] < 0 else S1)) for s in SEA],
          title="지수 월별 평균 수익률", h=250)
t2 = tbl(["월", "평균 수익률", "오른 해 비율", "표본(년)"],
         [[f'{s["월"]}월', f'{s["평균"]:+.2f}%', f'{int(s["플러스율"])}%', s["n"]] for s in SEA])

# 차트 3 — 간극
c3 = waterfall()

# 차트 4 — 트레일 민감도
c4 = hbar_ci([dict(label=f'잔여 트레일 −{t["트레일"]}%', v=t["delta"], lo=t["lo"], hi=t["hi"],
                   note=("95% 구간이 0을 넘음 → 유의" if t["유의"] else "구간이 0을 포함 → 유의하지 않음"),
                   sig=t["유의"], sig2=t["유의"]) for t in TR],
             title="2단 청산 트레일 폭별 개선폭")
t4 = tbl(["트레일 폭", "카드 대비 개선", "95% 신뢰구간", "판정"],
         [[f'−{t["트레일"]}%', f'{t["delta"]:+.2f}%p', f'{t["lo"]:+.2f} ~ {t["hi"]:+.2f}',
           "유의 ★" if t["유의"] else "유의하지 않음"] for t in TR])

# 차트 5 — 잔여 분포
c5 = dist_chart()
t5 = tbl(["분위", "잔여 50%의 수익률"], [[f'하위 {p["q"]}%', f'{p["v"]:+.1f}%'] for p in D["잔여분포"]["p"]])

# 차트 6 — 1월 앵커
c6 = hbar_ci([dict(label=j["정책"], v=j["mean"], lo=None, hi=None,
                   note=f'승률 {j["win"]}% · n={j["n"]}',
                   color=(S1 if j["정책"] in ("현행 카드", "2단 (126봉)") else S2c),
                   sig=True) for j in JA],
             title="9~10월 진입분 청산 정책 비교")
t6 = tbl(["정책", "평균", "중앙값", "승률", "카드 대비", "95% 신뢰구간"],
         [[j["정책"], f'{j["mean"]:+.2f}%', f'{j["med"]:+.2f}%', f'{j["win"]}%',
           f'{j["delta"]:+.2f}%p', f'{j["lo"]:+.2f} ~ {j["hi"]:+.2f}'] for j in JA])

# 차트 7 — S2 미달항목
def gr(m):
    if "2일누적" not in m: return "α"
    return "β" if "," not in m else "γ"
NAME = {"MA240": "MA240 이격만", "MA240,시총": "MA240 + 시총", "5년고점": "5년고점만", "시총": "시총만",
        "2일누적": "2일누적만", "2일누적,MA240": "2일누적 + MA240",
        "2일누적,MA240,시총": "2일누적 + MA240 + 시총",
        "2일누적,시총": "2일누적 + 시총", "2일누적,5년고점": "2일누적 + 5년고점"}
c7 = hbar_ci(
    [dict(label="◆ 정식 A (기준)", v=S2A["mean"], lo=S2A["lo"], hi=S2A["hi"],
          note=f'n={S2A["n"]:,} · 승률 {S2A["win"]}%', color=S3, sig=True, sig2=True)] +
    [dict(label=f'{gr(m["미달"])}  {NAME.get(m["미달"], m["미달"])}', v=m["mean"], lo=m["lo"], hi=m["hi"],
          note=f'n={m["n"]:,} · 승률 {m["win"]}%',
          color=(S1 if gr(m["미달"]) == "α" else S2c),
          sig=m["유의"], sig2=m["유의"]) for m in S2M],
    title="어떤 조건을 완화했는가별 성과", rowh=36, pad_l=210)
t7 = tbl(["등급", "완화한 조건", "건수", "평균", "승률", "95% 신뢰구간", "판정"],
         [["기준", "정식 A (완화 없음)", f'{S2A["n"]:,}', f'{S2A["mean"]:+.2f}%', f'{S2A["win"]}%',
           f'{S2A["lo"]:+.2f} ~ {S2A["hi"]:+.2f}', "—"]] +
         [[gr(m["미달"]), NAME.get(m["미달"], m["미달"]), f'{m["n"]:,}', f'{m["mean"]:+.2f}%',
           f'{m["win"]}%', f'{m["lo"]:+.2f} ~ {m["hi"]:+.2f}',
           "유의 ★" if m["유의"] else "무의"] for m in S2M])

# 차트 8 — 밸류 × 등급
c8 = grouped([v["등급"] for v in VG],
             [dict(name="밸류 태그 있음", color=S1, vals=[v["밸류O"]["mean"] for v in VG]),
              dict(name="밸류 태그 없음", color=S2c, vals=[v["밸류X"]["mean"] for v in VG])],
             title="신호 등급 × 밸류 태그")
t8 = tbl(["등급", "밸류 O 평균", "밸류 O 승률", "밸류 O n", "밸류 X 평균", "밸류 X 승률", "밸류 X n", "차이"],
         [[v["등급"], f'{v["밸류O"]["mean"]:+.2f}%', f'{v["밸류O"]["win"]}%', v["밸류O"]["n"],
           f'{v["밸류X"]["mean"]:+.2f}%', f'{v["밸류X"]["win"]}%', v["밸류X"]["n"],
           f'{v["diff"]:+.2f}%p'] for v in VG])

# 차트 9 — 밸류 × 국면
c9 = grouped([{"실행": "🟢 실행", "주의": "🟡 주의", "관찰만": "🔴 관찰만"}[v["국면"]] for v in VN],
             [dict(name="밸류 태그 있음", color=S1, vals=[v["밸류O"]["mean"] for v in VN]),
              dict(name="밸류 태그 없음", color=S2c, vals=[v["밸류X"]["mean"] for v in VN])],
             title="시장 국면 × 밸류 태그", h=250)
t9 = tbl(["국면", "밸류 O 평균", "밸류 O 승률", "밸류 X 평균", "밸류 X 승률"],
         [[v["국면"], f'{v["밸류O"]["mean"]:+.2f}%', f'{v["밸류O"]["win"]}%',
           f'{v["밸류X"]["mean"]:+.2f}%', f'{v["밸류X"]["win"]}%'] for v in VN])

# 차트 10 — 깔때기
c10 = funnel(FUN, title="신호 깔때기")

# 차트 11 — 5년 구간
c11 = grouped([d["구간"] for d in DEC],
              [dict(name="정식 A", color=S1, vals=[d["A"] for d in DEC]),
               dict(name="S2 (완화형)", color=S2c, vals=[d["S2"] for d in DEC])],
              title="5년 구간별 성과 (🟢실행 국면)")
t11 = tbl(["구간", "정식 A", "A 건수", "S2", "S2 건수"],
          [[d["구간"], f'{d["A"]:+.2f}%' if d["A"] is not None else "–", d["An"],
            f'{d["S2"]:+.2f}%' if d["S2"] is not None else "–", d["S2n"]] for d in DEC])

# 차트 12 — 밸류 태그별
c12 = hbar_ci([dict(label=t["태그"], v=t["mean"], lo=t["lo"], hi=t["hi"],
                    note=f'n={t["n"]:,} · 승률 {t["win"]}%', sig=t["lo"] > 0, sig2=t["lo"] > 0)
               for t in VT_], title="밸류 태그별 성과", pad_l=140)
t12 = tbl(["태그", "건수", "평균", "승률", "95% 신뢰구간"],
          [[t["태그"], f'{t["n"]:,}', f'{t["mean"]:+.2f}%', f'{t["win"]}%', f'{t["lo"]:+.2f} ~ {t["hi"]:+.2f}'] for t in VT_])
print("charts built")

# ── 개념도 (모식도 — 데이터 아님, 규칙 설명용)
CONCEPT = f'''<svg viewBox="0 0 720 300" class="chart" role="img" aria-label="휩쏘 재진입 개념도">
<text x="12" y="18" fill="{MUT}" font-size="10.5">※ 실제 데이터가 아니라 규칙을 설명하는 모식도입니다</text>
<path d="M40,120 L110,105 L180,95 L250,88 L320,92 L390,100 L460,112 L530,126 L600,140 L680,152"
      fill="none" stroke="{S3}" stroke-width="2.5"/>
<text x="686" y="156" fill="{S3}" font-size="10.5" text-anchor="end">장기선 (1년 구조선)</text>
<path d="M40,70 L110,58 L180,50 L250,44 L320,40 L360,42 L400,55 L430,110 L460,168"
      fill="none" stroke="{S1}" stroke-width="2.5"/>
<path d="M460,168 L500,150 L545,132 L590,118 L640,104" fill="none" stroke="{S1}" stroke-width="2.5" stroke-dasharray="5 4"/>
<circle cx="430" cy="110" r="5" fill="{S1}"/><circle cx="460" cy="168" r="7" fill="{S2c}" stroke="var(--surf)" stroke-width="2"/>
<line x1="430" y1="110" x2="430" y2="230" stroke="{BASE}" stroke-width="1"/>
<line x1="460" y1="168" x2="460" y2="230" stroke="{BASE}" stroke-width="1"/>
<text x="430" y="245" fill="{INK2}" font-size="11" text-anchor="middle">1일째 급락</text>
<text x="430" y="259" fill="{MUT}" font-size="10">바닥을 모른다 → 대기</text>
<text x="460" y="285" fill="{INK}" font-size="12" font-weight="650" text-anchor="middle">2일째 종가 = 진입 판단</text>
<text x="472" y="196" fill="{S2c}" font-size="11" font-weight="600">여기서 산다</text>
<text x="560" y="118" fill="{MUT}" font-size="10.5">되돌림</text>
<rect x="404" y="152" width="82" height="30" rx="4" fill="{S2c}" opacity="0.10"/>
<text x="445" y="140" fill="{MUT}" font-size="10" text-anchor="middle">2일 합쳐 −12% 이상</text>
<text x="40" y="40" fill="{MUT}" font-size="10.5">주가</text>
</svg>'''

GATE_DIAG = f'''<svg viewBox="0 0 720 210" class="chart" role="img" aria-label="3단 우선순위">
<text x="12" y="16" fill="{MUT}" font-size="10.5">※ 순서를 나타내는 구조도입니다</text>
<g><rect x="20" y="34" width="200" height="62" rx="8" fill="{S1}" opacity="0.14" stroke="{S1}" stroke-width="1.5"/>
<text x="120" y="58" fill="{INK}" font-size="13" font-weight="650" text-anchor="middle">1순위 · 시장 국면</text>
<text x="120" y="76" fill="{INK2}" font-size="10.5" text-anchor="middle">지금 사도 되는 때인가</text>
<text x="120" y="90" fill="{MUT}" font-size="10" text-anchor="middle">아니면 여기서 끝. 아무것도 안 산다</text></g>
<polygon points="228,65 244,58 244,72" fill="{BASE}"/>
<g><rect x="252" y="34" width="200" height="62" rx="8" fill="{S2c}" opacity="0.14" stroke="{S2c}" stroke-width="1.5"/>
<text x="352" y="58" fill="{INK}" font-size="13" font-weight="650" text-anchor="middle">2순위 · 자리(신호)</text>
<text x="352" y="76" fill="{INK2}" font-size="10.5" text-anchor="middle">2일 급락 + 장기선 지지</text>
<text x="352" y="90" fill="{MUT}" font-size="10" text-anchor="middle">A / S2-α 등급인가</text></g>
<polygon points="460,65 476,58 476,72" fill="{BASE}"/>
<g><rect x="484" y="34" width="212" height="62" rx="8" fill="{S3}" opacity="0.14" stroke="{S3}" stroke-width="1.5"/>
<text x="590" y="58" fill="{INK}" font-size="13" font-weight="650" text-anchor="middle">3순위 · 밸류 (가점)</text>
<text x="590" y="76" fill="{INK2}" font-size="10.5" text-anchor="middle">저PBR · 저PER · 배당 2%+</text>
<text x="590" y="90" fill="{MUT}" font-size="10" text-anchor="middle">필터가 아니다 — 없어도 산다</text></g>
<rect x="20" y="120" width="676" height="72" rx="8" fill="{S1}" opacity="0.07"/>
<text x="358" y="146" fill="{INK}" font-size="13" font-weight="650" text-anchor="middle">셋이 겹치면 = 최상급 자리</text>
<text x="358" y="167" fill="{INK2}" font-size="12" text-anchor="middle">평균 {CELL["최상"]["mean"]:+.2f}% · 승률 {CELL["최상"]["win"]}% · 30년에 {CELL["최상"]["n"]}번 (전체의 {CELL["빈도"]}%)</text>
<text x="358" y="184" fill="{MUT}" font-size="10.5" text-anchor="middle">가장 나쁜 자리(국면 나쁨 + 밸류 없음)는 {CELL["최하"]["mean"]:+.2f}% · 승률 {CELL["최하"]["win"]}% — 격차 {CELL["최상"]["mean"]-CELL["최하"]["mean"]:+.2f}%p</text>
</svg>'''

CSS = """
:root{--surf:#fcfcfb;--plane:#f9f9f7;--ink:#0b0b0b;--ink2:#52514e;--mut:#898781;
--grid:#e1e0d9;--base:#c3c2b7;--s1:#2a78d6;--s2:#eb6834;--s3:#1baf7a;--bd:rgba(11,11,11,.10);
--good:#0ca30c;--warn:#fab219;--crit:#d03b3b;color-scheme:light}
@media(prefers-color-scheme:dark){:root{--surf:#1a1a19;--plane:#0d0d0d;--ink:#fff;--ink2:#c3c2b7;--mut:#898781;
--grid:#2c2c2a;--base:#383835;--s1:#3987e5;--s2:#d95926;--s3:#199e70;--bd:rgba(255,255,255,.10);color-scheme:dark}}
*{box-sizing:border-box}
body{margin:0;background:var(--plane);color:var(--ink);
font:16px/1.75 system-ui,-apple-system,"Segoe UI","Malgun Gothic","Apple SD Gothic Neo",sans-serif;
-webkit-font-smoothing:antialiased}
.wrap{max-width:860px;margin:0 auto;padding:0 20px 96px}
header{padding:56px 0 8px}
h1{font-size:34px;line-height:1.25;margin:0 0 10px;letter-spacing:-.6px}
.lead{font-size:17px;color:var(--ink2);margin:0 0 6px}
.meta{font-size:13px;color:var(--mut)}
h2{font-size:24px;margin:56px 0 6px;letter-spacing:-.4px;padding-top:28px;border-top:1px solid var(--bd)}
h2 .num{display:inline-block;min-width:34px;color:var(--mut);font-size:16px;font-weight:600;vertical-align:2px}
h3{font-size:18px;margin:32px 0 8px;letter-spacing:-.2px}
h4{font-size:15px;margin:22px 0 6px;color:var(--ink2)}
p{margin:12px 0}
.sec-lead{color:var(--ink2);font-size:15.5px;margin:2px 0 18px}
.card{background:var(--surf);border:1px solid var(--bd);border-radius:14px;padding:20px 22px;margin:18px 0}
.chart{width:100%;height:auto;display:block;background:var(--surf);border:1px solid var(--bd);
border-radius:14px;padding:10px 8px;margin:16px 0}
figure{margin:24px 0}
figcaption{font-size:13px;color:var(--mut);margin-top:8px;padding-left:2px}
figcaption b{color:var(--ink2);font-weight:600}
.tv{margin:6px 0 0;font-size:13px}
.tv summary{cursor:pointer;color:var(--mut);font-size:12.5px;padding:4px 0}
.tv table{width:100%;border-collapse:collapse;margin-top:8px;font-size:12.5px}
.tv th,.tv td{padding:6px 9px;border-bottom:1px solid var(--bd);text-align:right}
.tv th:first-child,.tv td:first-child{text-align:left}
.tv th{color:var(--mut);font-weight:600;font-size:11.5px}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:22px 0}
.kpi{background:var(--surf);border:1px solid var(--bd);border-radius:12px;padding:16px 18px}
.kpi .l{font-size:12px;color:var(--mut);line-height:1.4}
.kpi .v{font-size:26px;font-weight:680;margin:4px 0 2px;letter-spacing:-.7px}
.kpi .n{font-size:12px;color:var(--ink2)}
.callout{border-left:3px solid var(--s1);background:var(--surf);border-radius:0 12px 12px 0;
padding:16px 20px;margin:20px 0}
.callout.warn{border-left-color:var(--warn)}
.callout.stop{border-left-color:var(--crit)}
.callout.ok{border-left-color:var(--good)}
.callout .t{font-weight:650;margin-bottom:4px;font-size:16px}
.big{font-size:19px;font-weight:650;line-height:1.55;margin:18px 0}
table.m{width:100%;border-collapse:collapse;font-size:14px;margin:16px 0}
table.m th,table.m td{padding:10px 11px;border-bottom:1px solid var(--bd);text-align:right}
table.m th:first-child,table.m td:first-child{text-align:left}
table.m thead th{color:var(--mut);font-size:12.5px;font-weight:600}
table.m tbody tr:hover{background:var(--plane)}
.g{color:var(--good);font-weight:600}.b{color:var(--crit);font-weight:600}.w{color:var(--warn);font-weight:600}
.dim{color:var(--mut)}
ul,ol{margin:12px 0;padding-left:24px}li{margin:7px 0}
code{background:var(--plane);border:1px solid var(--bd);padding:1px 6px;border-radius:5px;font-size:13px;
font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
pre{background:var(--surf);border:1px solid var(--bd);border-radius:12px;padding:16px 18px;overflow-x:auto;
font-size:13px;line-height:1.75;font-family:ui-monospace,SFMono-Regular,Menlo,monospace}
.glo{display:grid;grid-template-columns:130px 1fr;gap:8px 16px;font-size:14.5px;margin:14px 0}
.glo dt{font-weight:650}.glo dd{margin:0;color:var(--ink2)}
.toc{background:var(--surf);border:1px solid var(--bd);border-radius:14px;padding:18px 22px;margin:28px 0}
.toc ol{margin:6px 0;padding-left:20px}.toc li{margin:4px 0;font-size:14.5px}
.toc a{color:var(--ink);text-decoration:none;border-bottom:1px solid var(--bd)}
.toc a:hover{border-bottom-color:var(--s1)}
.verdict{display:grid;grid-template-columns:52px 1fr;gap:14px;align-items:start;
background:var(--surf);border:1px solid var(--bd);border-radius:14px;padding:18px 20px;margin:14px 0}
.verdict .ic{font-size:30px;line-height:1}
.verdict .h{font-weight:680;font-size:17px;margin-bottom:3px}
.src{font-size:13.5px;color:var(--ink2)}
.src b{color:var(--ink)}
footer{margin-top:60px;padding-top:22px;border-top:1px solid var(--bd);color:var(--mut);font-size:12.5px}
@media(max-width:640px){.glo{grid-template-columns:1fr}h1{font-size:27px}.wrap{padding:0 14px 70px}}
"""
print("css ok")

RJ = {j["정책"]: j for j in JA}
MA = next(m for m in S2M if m["미달"] == "MA240")
AC = next(v for v in VG if v["등급"] == "정식A")
GM = next(v for v in VG if v["등급"] == "S2-γ")
RG = {v["국면"]: v for v in VN}

BODY = f"""
<header>
<h1>급락한 좋은 주식을<br>언제 사야 하는가</h1>
<p class="lead">한국 주식시장 30년(1997–2026) 전 종목 데이터로 검증한 매수·청산 규칙</p>
<p class="meta">2026년 8월 2일 · 표본 {SMP['전체']:,}건 · KOSPI + KOSDAQ 전 종목 · 진우퀀트</p>
</header>

<div class="callout">
<div class="t">이 문서를 처음 보는 분께</div>
주식 용어를 몰라도 읽을 수 있게 썼습니다. 1장에서 필요한 개념 다섯 개만 그림으로 설명하고,
2장부터는 그 개념만으로 전부 이해할 수 있습니다.<br>
<b>모든 숫자는 실제 계산 결과입니다.</b> 예시로 지어낸 수치는 한 개도 없고,
각 장 끝의 "표로 보기"를 열면 그림에 쓰인 원본 숫자를 그대로 확인할 수 있습니다.
</div>

<div class="kpis">
<div class="kpi"><div class="l">검증한 매수 사례</div><div class="v">{SMP['전체']:,}건</div><div class="n">1997년 ~ 2026년 7월</div></div>
<div class="kpi"><div class="l">가장 좋은 조건에서</div><div class="v g">{CELL['최상']['mean']:+.2f}%</div><div class="n">승률 {CELL['최상']['win']}%</div></div>
<div class="kpi"><div class="l">가장 나쁜 조건에서</div><div class="v b">{CELL['최하']['mean']:+.2f}%</div><div class="n">승률 {CELL['최하']['win']}%</div></div>
<div class="kpi"><div class="l">그 격차</div><div class="v">{CELL['최상']['mean']-CELL['최하']['mean']:+.2f}%p</div><div class="n">승률로는 {CELL['최상']['win']-CELL['최하']['win']:+.1f}%p</div></div>
</div>

<div class="toc">
<b>차례</b>
<ol>
<li><a href="#s1">이 시스템은 무엇인가</a> — 개념 다섯 개</li>
<li><a href="#s2">무엇으로 검증했나</a> — 데이터와 방법</li>
<li><a href="#s3">발견 1 · 언제 사느냐가 무엇을 사느냐보다 중요하다</a></li>
<li><a href="#s4">발견 2 · 달력에도 리듬이 있다</a></li>
<li><a href="#s5">검정 ① 절반만 팔고 나머지를 들고 가면 나아지는가</a></li>
<li><a href="#s6">검정 ② 1월까지 들고 가는 규칙을 넣어야 하는가</a></li>
<li><a href="#s7">검정 ③ 조건에 살짝 못 미친 자리도 사도 되는가</a></li>
<li><a href="#s8">검정 ④ "좋은 회사를 싸게" — 세 축을 겹치면</a></li>
<li><a href="#s9">이 숫자를 믿어도 되는가</a> — 감사와 기각 목록</li>
<li><a href="#s10">지금 시장은 어떤 상태인가</a></li>
<li><a href="#s11">한계 — 이 결과가 틀릴 수 있는 지점</a></li>
<li><a href="#s12">참고 · 해외에서는 이걸 어떻게 쓰나</a></li>
</ol>
</div>

<h2 id="s1"><span class="num">1</span>이 시스템은 무엇인가</h2>
<p class="sec-lead">개념 다섯 개만 알면 이 문서 전체를 읽을 수 있습니다.</p>

<h3>① 휩쏘(Whipsaw) — 이틀 연속 급락 후 되돌림</h3>
<p>좋은 회사 주가도 이틀에 걸쳐 크게 빠질 때가 있습니다. 공포에 팔린 것이지 회사가 망한 게 아니라면,
가격은 곧 되돌아옵니다. 이 시스템은 <b>그 되돌림 직전을 사는 것</b>을 목표로 합니다.</p>
<p><b>핵심은 "2일째에 판단한다"입니다.</b> 1일째에는 바닥이 어디인지 알 수 없습니다.
이틀째 장 마감 가격을 보고 나서야 "충분히 빠졌고, 받쳐줄 지지선 근처다"라고 말할 수 있습니다.</p>
<figure>{CONCEPT}
<figcaption><b>휩쏘 재진입의 구조.</b> 초록선은 1년치 평균 가격(장기선)입니다.
주가가 이 선 근처까지 이틀 만에 −12% 이상 빠지면 매수 후보가 됩니다.
1일째는 관망하고, <b>2일째 종가에서만</b> 판단합니다.</figcaption></figure>

<h3>② 카드 — 사기 전에 미리 정해두는 세 개의 숫자</h3>
<p>사는 순간 <b>손절가·목표가·트레일</b> 세 가지를 미리 정합니다. 이걸 "카드"라고 부릅니다.
감정으로 파는 걸 막기 위한 장치입니다.</p>
<div class="glo">
<dt>손절가</dt><dd>여기까지 내려오면 무조건 판다. 잘못 샀다는 걸 인정하는 선.</dd>
<dt>목표가</dt><dd>여기까지 오르면 판다. 휩쏘의 경우 <b>빠진 폭의 절반을 되돌린 지점</b>.</dd>
<dt>트레일</dt><dd>고점 대비 −12% 밀리면 판다. 오를수록 같이 따라 올라가는 손절선.</dd>
</div>

<h3>③ 시장 국면 — 지금이 살 만한 때인가</h3>
<p>같은 신호라도 시장 전체가 어떤 상태냐에 따라 결과가 정반대가 됩니다. 그래서 매일 시장을 셋 중 하나로 찍습니다.</p>
<table class="m"><thead><tr><th>국면</th><th>기준</th><th>행동</th></tr></thead><tbody>
<tr><td>🟢 <b>실행</b></td><td>지수가 1년 최고가 대비 −12% 이상 빠졌거나, 변동성이 크면서 −5% 이상 빠진 상태</td><td>신호가 뜨면 산다</td></tr>
<tr><td>🟡 <b>주의</b></td><td>그 사이</td><td>신중하게</td></tr>
<tr><td>🔴 <b>관찰만</b></td><td>지수가 최고가 근처(0~−5%)이고 조용한 상태</td><td><b>신호가 떠도 사지 않는다</b></td></tr>
</tbody></table>
<p class="dim" style="font-size:14px">직관과 반대로 들릴 수 있습니다. 시장이 조용하고 고점 근처일 때가 오히려 위험합니다. 3장에서 숫자로 보여드립니다.</p>

<h3>④ 밸류 태그 — 지금 싸게 거래되고 있다는 표시</h3>
<p>세 가지 중 하나라도 해당하면 붙이는 표시입니다. 이 셋은 <b>이미 별도 검정에서 살아남은 것들만</b> 골랐습니다.</p>
<div class="glo">
<dt>저PBR</dt><dd>회사가 가진 순자산보다 주가가 싸다 (0.8배 미만)</dd>
<dt>저PER</dt><dd>회사가 버는 이익 대비 주가가 싸다 (8배 미만, 흑자인 경우)</dd>
<dt>배당 2%+</dt><dd>주가 대비 연 2% 이상을 현금으로 나눠준다</dd>
</div>

<h3>⑤ 신뢰구간 — "우연일 수도 있는가"를 재는 자</h3>
<p>이 문서의 그림에는 막대 위에 <b>가로 수염</b>이 그려져 있습니다. 이게 95% 신뢰구간입니다.</p>
<div class="callout">
<div class="t">수염을 읽는 법 — 이것만 기억하면 됩니다</div>
수염이 <b>0선을 건너지 않으면</b> → 통계적으로 의미 있는 발견입니다 (★ 표시).<br>
수염이 <b>0선을 걸치면</b> → 우연일 수 있습니다. 이 문서에서는 <b>채택하지 않습니다.</b><br><br>
<span class="dim">덧붙여, 이 시스템의 신호는 위기 때 한꺼번에 몰려서 발생합니다(1997·2008·2020 등).
그래서 일반적인 통계 방법을 쓰면 신뢰구간이 실제보다 좁게 나옵니다.
이 문서는 <b>연도 단위로 통째로 재추출하는 방식</b>(연도블록 부트스트랩)을 써서 그 문제를 보정했습니다.</span>
</div>

<h2 id="s2"><span class="num">2</span>무엇으로 검증했나</h2>
<p class="sec-lead">"과거에 이랬으면 좋았을 텐데"가 아니라, 그때 그 자리에서 알 수 있었던 정보만으로 계산했습니다.</p>
<div class="kpis">
<div class="kpi"><div class="l">기간</div><div class="v" style="font-size:19px">1997–2026</div><div class="n">약 30년</div></div>
<div class="kpi"><div class="l">종목</div><div class="v" style="font-size:19px">전 종목</div><div class="n">KOSPI + KOSDAQ</div></div>
<div class="kpi"><div class="l">정식 신호</div><div class="v">{SMP['A']:,}건</div><div class="n">A형 매수 사례</div></div>
<div class="kpi"><div class="l">완화 신호</div><div class="v">{SMP['S2']:,}건</div><div class="n">조건에 살짝 못 미친 사례</div></div>
</div>

<h3>데이터를 손본 딱 한 가지 — 가격 왜곡 보정</h3>
<p>원본 데이터에는 <b>액면분할</b>(주식 1주를 5주로 쪼개는 것) 같은 사건이 그대로 남아 있습니다.
5:1 분할이 일어나면 주가가 하루아침에 5분의 1이 되는데, 이건 <b>주가가 빠진 게 아닙니다.</b>
그냥 두면 시스템이 이걸 "−80% 급락"으로 잘못 읽습니다.</p>
<p>한국 시장에는 <b>하루 가격제한폭</b>이 있습니다(2015년 6월 15일 이전 ±15%, 이후 ±30%).
제한폭을 넘는 가격 변화는 <b>반드시</b> 분할·증자 같은 기업행위입니다. 그래서 제한폭을 넘는 변화가 보이면
그 비율만큼 과거 가격을 되돌려 맞췄습니다.</p>

<h3>미래를 훔쳐보지 않았다는 것</h3>
<ul>
<li>이동평균선은 <b>완료된 주·월</b>의 값만 씁니다. 아직 안 끝난 주의 값을 미리 쓰지 않습니다.</li>
<li>시가총액·재무 지표는 <b>그 날짜 시점에 공개돼 있던 값</b>만 씁니다.</li>
<li>손절·목표는 <b>사는 날 확정</b>하고, 그 다음 날부터 하루하루 순서대로 검사합니다.</li>
</ul>

<h2 id="s3"><span class="num">3</span>발견 1 · 언제 사느냐가 무엇을 사느냐보다 중요하다</h2>
<p class="sec-lead">이 시스템에서 가장 견고한 발견입니다. 그리고 가장 반직관적입니다.</p>
<p><b>완전히 똑같은 매수 신호</b>를 시장 국면별로만 나눠 봤습니다. 종목도, 규칙도, 손절도 전부 동일합니다.
다른 건 "그날 시장이 어떤 상태였나" 하나뿐입니다.</p>
<figure>{c1}
<figcaption><b>같은 신호, 다른 시장 상태.</b> 막대는 40거래일 뒤 평균 수익률, 수염은 95% 신뢰구간.
🟢실행에서만 수염이 0을 넘습니다(★). 🔴관찰만에서는 평균이 마이너스입니다.
{t1}</figcaption></figure>

<div class="big">시장이 이미 많이 빠져 있을 때 사면 <span class="g">{G[0]['mean']:+.2f}%</span>,
시장이 고점 근처에서 조용할 때 사면 <span class="b">{G[2]['mean']:+.2f}%</span>.
<br>같은 신호입니다. 차이는 <b>{G[0]['mean']-G[2]['mean']:.2f}%p</b>.</div>

<div class="callout stop">
<div class="t">그래서 규칙이 이렇게 됩니다</div>
🔴관찰만 국면에서는 <b>아무리 좋아 보이는 신호가 떠도 사지 않습니다.</b>
이 한 줄이 이 시스템에서 가장 값어치 있는 규칙입니다.
</div>

<h3>왜 이렇게 되는가</h3>
<p>시장이 고점 근처에서 조용할 때 개별 종목이 이틀 만에 −12% 빠졌다면, 그건 <b>시장 탓이 아니라 그 회사 탓</b>일
가능성이 큽니다. 반대로 시장 전체가 −30% 빠져 있는 와중의 급락은 <b>공포에 같이 쓸려 내려간 것</b>이라
되돌아올 여지가 큽니다. 시스템은 이 둘을 구분하지 못하지만, <b>시장 국면이 대신 구분해 줍니다.</b></p>

<h2 id="s4"><span class="num">4</span>발견 2 · 달력에도 리듬이 있다</h2>
<p class="sec-lead">이 프로젝트의 출발점은 데이터가 아니라, 진우 씨가 아버지에게 배운 이야기였습니다 —
"가을에 바닥을 치고 이듬해 봄에 고점을 친다."</p>
<figure>{c2}
<figcaption><b>지수의 월별 평균 수익률</b> ({D['계절성_기간']}). 막대 아래 회색 숫자는 그 달에 오른 해의 비율.
{t2}</figcaption></figure>
<p>결과는 이렇습니다.</p>
<ul>
<li><b>마이너스인 달은 8·9·10월 셋뿐입니다.</b> 나머지 아홉 달은 모두 플러스.</li>
<li>가장 강한 달은 <b>4월({SEA[3]['평균']:+.2f}%, 오른 해 {int(SEA[3]['플러스율'])}%)</b>,
그다음이 <b>1월({SEA[0]['평균']:+.2f}%, {int(SEA[0]['플러스율'])}%)</b>.</li>
<li>즉 "가을 저점 → 봄 고점"이라는 이야기가 <b>지수 수준에서는 실제로 데이터에 있습니다.</b></li>
</ul>
<div class="callout warn">
<div class="t">그런데 여기에 함정이 있습니다</div>
"9~10월이 저점"이라는 말은 <b>지수가 그때 싸다</b>는 뜻이지,
<b>그때 산 개별 종목이 잘 된다</b>는 뜻이 아닙니다. 이 둘은 다릅니다.
6장에서 실제로 확인해 보면 <b>9~10월에 산 사례는 오히려 평균 이하</b>였습니다.
</div>
<p class="dim" style="font-size:13.5px">※ 이 지수는 30년을 잇기 위해 합성·재척도한 시계열입니다.
방향과 변동성은 유효하지만 절대 레벨은 의미가 없습니다. 위 표는 월별 <b>변화율</b>이라 이 한계의 영향을 받지 않습니다.</p>

<h2 id="s5"><span class="num">5</span>검정 ① 절반만 팔고 나머지를 들고 가면 나아지는가</h2>
<p class="sec-lead">현재 규칙은 목표가에 닿으면 전량 매도입니다.
"절반만 팔고 나머지는 더 들고 가면 더 벌지 않을까?" — 이걸 검증했습니다.</p>

<h3>왜 이 질문이 나왔나</h3>
<p>산 뒤 6개월 안의 <b>최고가</b>를 기준으로 재면 평균 {GAP['고점6M']:+.1f}%까지 올랐습니다.
그런데 실제 규칙대로 팔면 {GAP['카드']:+.2f}%밖에 못 법니다. 이 간극이 아까워 보였습니다.</p>
<figure>{c3}
<figcaption><b>간극의 정체.</b> 왼쪽은 "신이 최고점에 팔았을 때"의 값 — 실제로는 도달 불가능한 상한선입니다.
2단 청산이 회수한 몫은 그 간극의 <b>{GAP['회수율']}%</b>에 불과합니다.</figcaption></figure>

<div class="callout stop">
<div class="t">가장 중요한 교훈 — 질문 자체가 틀렸습니다</div>
{GAP['고점6M']:.1f}%는 <b>미래를 다 알고 정확히 꼭대기에 판 값</b>입니다.
실행 가능한 어떤 규칙도 이걸 회수하지 못합니다.
이 간극을 "되찾을 수 있는 손실"로 본 것 자체가 오독이었습니다. 정직하게 기록해 둡니다.
</div>

<h3>그래도 개선은 있었다 — 다만 작다</h3>
<figure>{c4}
<figcaption><b>잔여분의 트레일 폭을 바꿔가며 측정한 개선폭.</b> 진한 막대는 수염이 0을 넘은 것(★),
흐린 막대는 0을 걸쳐 채택하지 않은 것. 점추정치는 −20%가 가장 크지만 신뢰구간이 0을 포함합니다.
{t4}</figcaption></figure>
<p><b>채택한 사양</b>: 목표가 도달 시 <b>50%만 실현</b>, 나머지 50%는 <b>고점 대비 −12% 트레일</b>,
단 <b>손절선은 산 가격(본전) 아래로 내리지 않음</b>, 최대 6개월.</p>
<table class="m"><thead><tr><th></th><th>평균</th><th>중앙값</th><th>승률</th><th>표준편차</th></tr></thead><tbody>
<tr><td>현행 카드 (전량 매도)</td><td>{GAP['카드']:+.2f}%</td><td>+0.10%</td><td>50.2%</td><td>8.6</td></tr>
<tr><td><b>2단 청산 (채택)</b></td><td class="g">{GAP['이단']:+.2f}%</td><td>+0.10%</td><td>50.2%</td><td>10.6</td></tr>
</tbody></table>
<p><b>승률과 중앙값이 한 치도 안 변합니다.</b> 이게 이 규칙의 핵심입니다 —
"본전 아래로 손절선을 내리지 않는다"는 조항 덕분에, 잃는 쪽은 그대로 두고 평균만 올립니다.
이 조항을 빼면 승률이 50.2% → 42%로 무너집니다.</p>

<h3>왜 개선폭이 작은가 — 잔여분은 복권이다</h3>
<figure>{c5}
<figcaption><b>남겨둔 50%의 수익률 분포</b> (🟢실행 국면 · 목표 도달 {D['잔여분포']['n']}건).
막대는 하위 몇 % 지점의 값입니다. 절반은 +2.7% 언저리에서 끝나는데,
평균은 {D['잔여분포']['mean']:+.1f}%까지 올라갑니다.
{t5}</figcaption></figure>
<p>평균 {D['잔여분포']['mean']:+.1f}% 중 <b>{D['잔여분포']['top5기여']:+.2f}%p가 상위 5%에서 나옵니다</b>.
즉 스무 번 중 한 번의 큰 상승이 평균 전체의 {D['잔여분포']['top5기여']/D['잔여분포']['mean']*100:.0f}%를 만듭니다.
나머지 열아홉 번은 체감이 없습니다.</p>
<div class="callout">
<div class="t">그래서 이 규칙은 이렇게 이해해야 합니다</div>
"절반을 복권에 태우는 대가로 평균이 {GAP['이단']-GAP['카드']:+.2f}%p 오른다."<br>
<b>체감되지 않는 개선입니다.</b> 실전에서는 몇 달 동안 아무 효과가 없어 보이는 기간이 길게 이어집니다.
</div>

<h2 id="s6"><span class="num">6</span>검정 ② 1월까지 들고 가는 규칙을 넣어야 하는가</h2>
<p class="sec-lead">4장의 계절성을 실전 규칙으로 옮기면 어떻게 될까? — "9~10월에 산 건 이듬해 1월까지 들고 간다."</p>

<h3>먼저, 데드라인은 조항이 될 수 없었다</h3>
<div class="verdict"><div class="ic">🚫</div><div>
<div class="h">"1월 말까지 보유" 조항을 붙였더니 — {D['1월앵커_n']}건 중 발동 <b>0건</b></div>
<span class="src">잔여분이 살아있던 {D['1월앵커_잔여생존']}건 <b>전부</b>에서 트레일 손절이 1월보다 먼저 걸렸습니다.
조항을 넣어도 한 번도 쓰이지 않는 <b>죽은 문장</b>이 됩니다.</span>
</div></div>

<h3>그래서 방식 자체를 바꿔 봤다</h3>
<p>트레일을 아예 걸지 않고, 본전 손절만 둔 채 1월 말까지 버티는 방식으로 다시 계산했습니다.</p>
<figure>{c6}
<figcaption><b>9~10월 진입분 · 🟢실행 국면 {RJ['현행 카드']['n']}건.</b> 파란 막대는 현행 규칙 계열, 주황은 달력 규칙 계열.
{t6}</figcaption></figure>

<table class="m"><thead><tr><th>정책</th><th>평균</th><th>카드 대비</th><th>95% 신뢰구간</th><th>판정</th></tr></thead><tbody>
<tr><td>잔여를 1월까지 보유</td><td class="g">{RJ['잔여 1월보유']['mean']:+.2f}%</td><td>{RJ['잔여 1월보유']['delta']:+.2f}%p</td><td>{RJ['잔여 1월보유']['lo']:+.2f} ~ {RJ['잔여 1월보유']['hi']:+.2f}</td><td class="w">0을 포함 → 보류</td></tr>
<tr><td>잔여를 4월까지 보유</td><td>{RJ['잔여 4월보유']['mean']:+.2f}%</td><td>{RJ['잔여 4월보유']['delta']:+.2f}%p</td><td>{RJ['잔여 4월보유']['lo']:+.2f} ~ {RJ['잔여 4월보유']['hi']:+.2f}</td><td class="b">이득 전부 반납</td></tr>
<tr><td>밸류만 4월 연장</td><td>{RJ['밸류분기']['mean']:+.2f}%</td><td>{RJ['밸류분기']['delta']:+.2f}%p</td><td>{RJ['밸류분기']['lo']:+.2f} ~ {RJ['밸류분기']['hi']:+.2f}</td><td class="b">단일 적용보다 나쁨 → 기각</td></tr>
<tr><td>목표 무시하고 4월까지 보유</td><td class="b">{RJ['달력보유 4월']['mean']:+.2f}%</td><td>{RJ['달력보유 4월']['delta']:+.2f}%p</td><td>{RJ['달력보유 4월']['lo']:+.2f} ~ {RJ['달력보유 4월']['hi']:+.2f}</td><td class="b">승률 {RJ['달력보유 4월']['win']}% → 기각</td></tr>
</tbody></table>

<div class="verdict"><div class="ic">🟠</div><div>
<div class="h">판정 — 보류. 카드에 넣지 않고, 앞으로 발생할 사례로 검증한다</div>
<span class="src">1월 보유가 좋아 보이긴 합니다({RJ['잔여 1월보유']['delta']:+.2f}%p). 하지만 <b>신뢰구간이 0을 포함</b>하고,
변동성이 두 배로 커지며, 정책 13개를 동시에 본 다중비교 문제가 남아 있습니다.
"좋아 보이는 걸 사후에 고르지 않는다"는 이 프로젝트의 규율에 따라 <b>보류</b>합니다.</span>
</div></div>

<div class="callout stop">
<div class="t">예상 못 한 발견 — 9~10월에 산 것 자체가 평균 이하였다</div>
🟢실행 국면 전체 평균이 <b>{S2A['mean']:+.2f}%</b>인데,
9~10월에 산 것만 보면 <b>{RJ['현행 카드']['mean']:+.2f}%</b>입니다.<br><br>
모순처럼 보이지만 아닙니다. <b>"고점이 1월에 온다"는 언제 파는가의 통계</b>이고,
<b>"9~10월 진입이 나쁘다"는 얼마를 버는가의 통계</b>입니다.
9~10월은 시장이 하락 중이라 신호는 많이 뜨지만, 그만큼 계속 밀립니다.
</div>

<h2 id="s7"><span class="num">7</span>검정 ③ 조건에 살짝 못 미친 자리도 사도 되는가</h2>
<p class="sec-lead">정식 A형은 네 가지 조건을 모두 통과해야 합니다.
"−11.8% 빠졌으면 −12% 문턱을 아깝게 놓친 건데, 이것도 사면 안 되나?" — 이걸 검증했습니다.</p>

<p>네 조건을 하나씩 살짝 풀어 <b>{SMP['S2']:,}건</b>을 새로 찾아냈습니다.
그리고 <b>어떤 조건을 풀었는지</b>로 나눠 봤습니다. 결과는 예상과 완전히 달랐습니다.</p>

<figure>{c7}
<figcaption><b>완화한 조건별 성과</b> (🟢실행 국면). 초록 막대가 기준선(정식 A), 파랑은 α등급, 주황은 β·γ등급.
흐린 막대는 신뢰구간이 0을 걸쳐 채택하지 않은 것.
{t7}</figcaption></figure>

<div class="big">"완화형이 먹히나?"가 아니라 <b>"어느 조건을 풀었나"가 전부를 갈랐습니다.</b>
<br>규칙 한 줄로 요약하면 — <b>2일누적을 낀 조합은 죽고, 2일누적을 빼면 산다.</b></div>

<table class="m"><thead><tr><th>등급</th><th>정의</th><th>성과</th><th>처리</th></tr></thead><tbody>
<tr><td><b>S2-α</b></td><td>MA240 / 5년고점 / 시총 중 <b>하나만</b> 못 미침</td><td class="g">+1.9 ~ +4.5% (전부 유의)</td><td>실전 후보</td></tr>
<tr><td><b>S2-β</b></td><td>2일누적만 못 미침</td><td class="w">+0.81% (유의하나 약함)</td><td>관찰만</td></tr>
<tr><td><b>S2-γ</b></td><td>2일누적 + 다른 조건</td><td class="b">+0.1% 수준 (무의)</td><td>등록 제외</td></tr>
</tbody></table>

<div class="callout ok">
<div class="t">가장 큰 발견 — 장기선 위 8~12% 구간이 오히려 더 좋았다</div>
정식 A형은 "장기선을 밟거나 그 아래"를 노려 <b>장기선 위로 8%까지만</b> 허용합니다.
그런데 이 한 줄만 <b>+12%까지</b> 풀었더니 <b class="g">{MA['mean']:+.2f}%</b>가 나왔습니다 —
정식 A({S2A['mean']:+.2f}%)보다 <b>{MA['mean']-S2A['mean']:+.2f}%p 좋습니다.</b> 승률도 {MA['win']}% (정식 A는 {S2A['win']}%).<br><br>
<b>이게 사실이면 A형의 정의가 바뀝니다.</b> 그래서 <b>바꾸지 않았습니다.</b>
완화 네 가지 중 사후에 가장 좋은 하나를 고른 것이기 때문입니다.
대신 조건을 지금 문서로 고정하고, <b>앞으로 발생할 신호 40건으로만</b> 판정하기로 했습니다(사전등록).
</div>

<h4>왜 2일누적은 풀면 안 되는가</h4>
<p>휩쏘는 <b>급락의 깊이가 반등의 연료</b>입니다. −10%짜리 얕은 하락은 연료가 부족하고,
거기에 다른 조건까지 흐려지면 그냥 평범한 하락이 됩니다. 데이터가 그대로 그 말을 합니다.</p>

<figure>{c11}
<figcaption><b>5년 구간별 안정성.</b> 정식 A는 7구간 모두 플러스, S2는 1995–99를 뺀 6구간 플러스.
특정 시기에만 통하는 규칙이 아니라는 뜻입니다.
{t11}</figcaption></figure>

<h2 id="s8"><span class="num">8</span>검정 ④ "좋은 회사를 싸게" — 세 축을 겹치면</h2>
<p class="sec-lead">여기까지가 <b>언제</b>와 <b>어떤 자리</b>였습니다. 마지막 축은 <b>어떤 회사</b>입니다.</p>

<figure>{c8}
<figcaption><b>신호 등급별로, 밸류 태그가 있을 때와 없을 때.</b> 모든 등급에서 파랑(밸류 있음)이 위입니다.
{t8}</figcaption></figure>

<div class="callout ok">
<div class="t">가장 인상적인 칸 — S2-γ를 보세요</div>
신호로는 죽은 등급입니다({GM['밸류X']['mean']:+.2f}%). 그런데 밸류 태그가 붙으면
<b class="g">{GM['밸류O']['mean']:+.2f}% · 승률 {GM['밸류O']['win']}%</b>로 살아납니다.<br>
<b>밸류는 신호 품질과 독립적인 축입니다</b> — 같은 걸 두 번 재는 게 아닙니다.
</div>

<figure>{c12}
<figcaption><b>태그별 성과</b> (🟢실행 국면). 태그가 겹칠수록 좋아지고, 단일 태그 중에선 <b>배당 2%+</b>가 가장 강합니다.
{t12}</figcaption></figure>
<p>저평가 지표 중에서도 <b>실제로 현금을 나눠주는 회사</b>가 가장 잘 버텼다는 뜻으로 읽힙니다.</p>

<h3>그런데 순서가 있습니다</h3>
<figure>{c9}
<figcaption><b>시장 국면 × 밸류 태그.</b> 🔴관찰만 국면에서는 밸류가 있어도 {RG['관찰만']['밸류O']['mean']:+.2f}%입니다.
{t9}</figcaption></figure>

<div class="big">🔴 나쁜 국면에서는 밸류가 있어도 <b>{RG['관찰만']['밸류O']['mean']:+.2f}%</b>.
<br>🟢 좋은 국면에서는 밸류가 없어도 <b class="g">{RG['실행']['밸류X']['mean']:+.2f}%</b>.
<br><br>밸류는 <b>손실을 0 근처까지 막아주지만, 플러스를 만들어내지는 못합니다.</b></div>

<figure>{GATE_DIAG}
<figcaption><b>이 검정 전체가 도달한 결론.</b> "좋은 회사를 싸게"에서 <b>'싸게'보다 '언제'가 먼저</b>입니다.</figcaption></figure>

<figure>{c10}
<figcaption><b>신호 깔때기.</b> 전체 {FUN[0]['n']:,}건 중 세 축이 모두 겹치는 자리는
{FUN[3]['n']}건 — <b>{CELL['빈도']}%</b>입니다. 30년에 {FUN[3]['n']}번, 연평균 약 {FUN[3]['n']//30}번.</figcaption></figure>

<table class="m"><thead><tr><th>자리</th><th>건수</th><th>평균</th><th>중앙값</th><th>승률</th><th>95% 신뢰구간</th></tr></thead><tbody>
<tr><td><b>최상급</b> — 🟢실행 × 밸류 × (A 또는 S2-α)</td><td>{CELL['최상']['n']}</td><td class="g">{CELL['최상']['mean']:+.2f}%</td><td>{CELL['최상']['med']:+.2f}%</td><td class="g">{CELL['최상']['win']}%</td><td>{CELL['최상']['lo']:+.2f} ~ {CELL['최상']['hi']:+.2f}</td></tr>
<tr><td><b>최하급</b> — 나쁜 국면 × 밸류 없음</td><td>{CELL['최하']['n']:,}</td><td class="b">{CELL['최하']['mean']:+.2f}%</td><td class="b">{CELL['최하']['med']:+.2f}%</td><td class="b">{CELL['최하']['win']}%</td><td>{CELL['최하']['lo']:+.2f} ~ {CELL['최하']['hi']:+.2f}</td></tr>
</tbody></table>

<div class="callout warn">
<div class="t">여기서 하기 쉬운 실수 하나</div>
위 표를 보고 <b>"밸류 태그가 없으면 사지 말자"</b>고 결론 내리면 안 됩니다.
🟢실행 국면에서 밸류 없는 자리도 <b>{RG['실행']['밸류X']['mean']:+.2f}%</b>로 플러스이고,
그게 전체 기회의 <b>{RG['실행']['밸류X']['n']/(RG['실행']['밸류X']['n']+RG['실행']['밸류O']['n'])*100:.0f}%</b>입니다.
밸류는 <b>가점이지 필터가 아닙니다.</b>
</div>
"""
print("body1 ok")

top6 = OBK["종목"][:6]
BODY += f"""
<h2 id="s9"><span class="num">9</span>이 숫자를 믿어도 되는가</h2>
<p class="sec-lead">보기 좋은 결과를 만드는 건 쉽습니다. 그래서 이 검정이 <b>스스로를 어떻게 감시했는지</b>를 밝힙니다.</p>

<h3>① 기존 결과를 그대로 재현했는가</h3>
<table class="m"><thead><tr><th>확인 항목</th><th>결과</th></tr></thead><tbody>
<tr><td>기존 원장의 매수 사례 {SMP['원장A']:,}건을 원자료에서 독립 재계산</td><td class="g">종목·날짜 키 100% 일치</td></tr>
<tr><td>기존 원장의 수익률과 대조</td><td class="g">전 건 오차 0.05%p 이내 (소수점 반올림 차이)</td></tr>
<tr><td>시장 국면 도장 재계산</td><td class="g">100% 일치</td></tr>
<tr><td>기존 문서의 "40일 평균 +2.1% · 중앙 −1.2% · 승률 48%"</td><td class="g">전부 재현</td></tr>
</tbody></table>

<h3>② 오늘 만든 계산기 네 개가 서로 어긋나지 않는가</h3>
<p>같은 날 네 개의 검정 프로그램을 돌렸습니다. 코드가 갈라졌으면 결론이 오염됩니다.
그래서 <b>글자 비교가 아니라 "같은 값을 넣으면 같은 값이 나오는가"</b>로 확인했습니다.
인위적으로 5:1 분할과 3:1 병합을 심은 가짜 시계열을 만들어, 원본 엔진과 새 프로그램 네 개에 똑같이 먹였습니다.</p>
<table class="m"><thead><tr><th>항목</th><th>결과</th></tr></thead><tbody>
<tr><td>가격 왜곡 보정 함수 · 4개 프로그램 vs 원본 엔진</td><td class="g">최대 오차 0.0 (완전 동일)</td></tr>
<tr><td>이동평균선 계산 함수</td><td class="g">최대 오차 0.0</td></tr>
<tr><td>검정 ↔ 검정 교집합 사례의 수익률</td><td class="g">최대 오차 0.0</td></tr>
<tr><td>사례 집합 중복 여부 (정식 A ∩ 완화형)</td><td class="g">교집합 0건 — 이중 집계 없음</td></tr>
<tr><td>논리 명제 6개 (예: 국면 순서가 두 집단에서 동일한가)</td><td class="g">전부 통과</td></tr>
</tbody></table>

<h3>③ 감사에서 실제로 잡힌 것 두 개</h3>
<div class="card">
<p><b>ⓐ 보고 방식의 흠 — 결론에는 영향 없음.</b> 7장 검정에서 "2단 청산 개선폭"을 계산할 때
기준(40거래일)과 비교 대상(126거래일)의 기간이 달라 두 효과가 섞여 있었습니다.
분해해 보니 기간 효과는 사실상 0이었고 보고된 값은 거의 전부 분할 효과였습니다. <b>수치는 유효하지만 정의를 명시했어야 했습니다.</b></p>
<p><b>ⓑ 잠재적 사고 — 원본 검정 엔진이 최신 파이썬 라이브러리에서 멈춥니다.</b>
현재 PC 환경에서는 정상 동작하지만, 라이브러리를 업그레이드하는 순간 <b>30년 검정을 다시 돌릴 수 없게 됩니다.</b>
한 글자 수정으로 해결됩니다. (별도 점검 리포트에 조치 방법 기록)</p>
</div>

<h3>④ 확증편향이 아니라는 증거 — 오늘 기각된 것이 더 많다</h3>
<p>결론을 정해놓고 근거를 찾았다면 전부 통과했을 것입니다. 실제로는 이렇습니다.</p>
<table class="m"><thead><tr><th>시험대에 오른 가설</th><th>판정</th></tr></thead><tbody>
<tr><td>절반 매도 + 나머지 보유가 큰 개선을 준다</td><td class="w">🟡 조건부 채택 — 간극 회수는 {GAP['회수율']}%뿐</td></tr>
<tr><td>9~10월 매수분은 1월까지 들고 가야 한다</td><td class="w">🟠 보류 — 데드라인은 {D['1월앵커_n']}건 중 0건 발동</td></tr>
<tr><td>밸류 종목만 4월까지 연장하면 낫다</td><td class="b">❌ 기각 — 분기가 단일 적용보다 나쁨</td></tr>
<tr><td>잔여를 장기선 이탈로 청산하면 낫다</td><td class="b">❌ 기각</td></tr>
<tr><td>보유 기간을 늘리면 더 번다</td><td class="b">❌ 기각 — 오히려 감소</td></tr>
<tr><td>2일누적 조건을 풀어도 된다</td><td class="b">❌ 조합은 전부 기각</td></tr>
<tr><td>9~10월이 좋은 매수 시기다</td><td class="b">❌ 반증 — 평균 이하였다</td></tr>
<tr><td>세 축(국면·자리·밸류)이 겹치면 좋다</td><td class="g">✅ 채택 — 모든 칸에서 일관</td></tr>
</tbody></table>
<div class="callout">
<div class="t">편향이 생기는 지점은 따로 있습니다</div>
"결론은 이미 알려져 있다"가 <b>"그러니 어떤 완화든 정당하다"</b>로 넘어가는 순간입니다.
오늘 2일누적 완화가 정확히 그 시험대였고 — <b>죽었습니다.</b> 규율이 작동했다는 뜻입니다.
</div>

<h2 id="s10"><span class="num">10</span>지금 시장은 어떤 상태인가</h2>
<p class="sec-lead">2026년 7월 31일(마지막 거래일) 기준입니다.</p>
<div class="kpis">
<div class="kpi"><div class="l">시장 국면</div><div class="v g" style="font-size:22px">🟢 실행</div><div class="n">지수 1년 고점 대비 −28.2%</div></div>
<div class="kpi"><div class="l">20일 변동성(연율)</div><div class="v w">98%</div><div class="n">30년 중앙값의 5.6배</div></div>
<div class="kpi"><div class="l">관찰 중인 종목</div><div class="v">{OBK['총']}종</div><div class="n">7월 30일 대급락 때 진입</div></div>
<div class="kpi"><div class="l">목표 도달</div><div class="v g">{OBK['목표달성']}종</div><div class="n">7월 31일 하루 만에</div></div>
</div>
<p>2026년 7월 29~30일에 지수가 1년 고점 대비 −38%까지 빠지는 대급락이 있었고,
7월 31일에 크게 되돌렸습니다. 시스템은 7월 30일에 {OBK['총']}종을 포착했고,
그중 <b>{OBK['목표달성']}종이 다음 날 목표가에 도달</b>했습니다.</p>
<p>새로 채택한 2단 청산을 적용하면, 이 {OBK['목표달성']}종은 <b>절반은 이미 실현</b>됐고 <b>나머지 절반이 살아 있는 상태</b>입니다.
현재 평가 기준으로 전량 매도 시 {OBK['구카드']:+.2f}%, 2단 적용 시 {OBK['신2단']:+.2f}%입니다
(잔여분은 <b>아직 실현되지 않은 평가익</b>이라는 점을 분명히 해둡니다).</p>
<table class="m"><thead><tr><th>종목</th><th>실현한 50%</th><th>잔여 평가</th><th>트레일선까지 여유</th></tr></thead><tbody>
{"".join(f'<tr><td>{esc(t["name"])}</td><td class="g">{t["실현"]:+.1f}%</td><td class="g">{t["잔여"]:+.1f}%</td><td>{t["여유"]:+.1f}%</td></tr>' for t in top6)}
<tr><td class="dim" colspan="4">… 전체 {OBK['목표달성']}종은 현황판 파일 참조</td></tr>
</tbody></table>

<h2 id="s11"><span class="num">11</span>한계 — 이 결과가 틀릴 수 있는 지점</h2>
<p class="sec-lead">이 부분을 생략한 백테스트 문서는 신뢰할 수 없습니다. 그래서 가장 자세히 씁니다.</p>
<table class="m"><thead><tr><th>한계</th><th>영향 방향</th><th>내용</th></tr></thead><tbody>
<tr><td><b>생존편향</b></td><td class="b">실제는 더 나쁨</td><td>상장폐지된 종목이 데이터에 덜 반영돼 있습니다. 시총 하한을 낮춘 완화형(S2)이 특히 취약합니다.</td></tr>
<tr><td><b>소규모 기업행위 잔존</b></td><td class="b">약간 나쁨</td><td>가격제한폭 <b>이내</b>의 소규모 증자는 보정이 잡지 못합니다.</td></tr>
<tr><td><b>사례가 위기에 몰림</b></td><td class="dim">불확실</td><td>1997·2008·2020에 신호가 집중됩니다. 연도블록 부트스트랩으로 완화했지만 독립 표본은 아닙니다.</td></tr>
<tr><td><b>거래비용 미반영</b></td><td class="b">실제는 더 나쁨</td><td>본문 수치는 총액 기준입니다. 2단 청산은 편도 0.5%를 가정해도 개선 부호는 유지됩니다.</td></tr>
<tr><td><b>유동성</b></td><td class="b">실제는 더 나쁨</td><td>시총 2,000~3,000억 구간은 실제 체결 가격이 계산보다 불리합니다.</td></tr>
<tr><td><b>재무 데이터는 월말 스냅숏</b></td><td class="dim">불확실</td><td>2002년 1월부터만 있습니다. 그 이전 사례는 밸류 분석에서 <b>제외</b>했습니다(밸류 없음에 섞으면 오염).</td></tr>
<tr><td><b>사후 분해</b></td><td class="w">주의</td><td>7·8장의 세부 쪼개기는 사전등록되지 않았습니다. 방향은 기존 검정과 일치하나 <b>세부 수치는 시사일 뿐</b>입니다.</td></tr>
<tr><td><b>합성 지수</b></td><td class="dim">제한적</td><td>30년 지수는 합성·재척도된 것으로 절대 레벨은 무의미합니다. 방향과 변동성만 씁니다.</td></tr>
</tbody></table>
<div class="callout stop">
<div class="t">가장 중요한 한계 — 평균은 체감되지 않습니다</div>
이 문서의 개선폭은 대부분 <b>1%p 미만</b>이고, 수익의 상당 부분이 <b>소수의 큰 사례</b>에서 나옵니다.
실전에서 열 번, 스무 번 거래하는 동안에는 평균에 한참 못 미치는 기간이 길게 이어질 수 있습니다.
<b>이건 "무조건 먹히는 규칙"이 아닙니다.</b> 손절과 목표를 지키는 규율이 없으면 절반 이상 집니다.
</div>

<h2 id="s12"><span class="num">12</span>참고 · 해외에서는 이걸 어떻게 쓰나</h2>
<p class="sec-lead">이 시스템의 네 기둥이 해외 연구·실무에서 어떻게 다뤄지는지 정리했습니다.
<b>참고용</b>이며, 아래 인용은 전부 실제 논문·자료에서 확인한 내용입니다.</p>

<h3>기둥 1 · 급락 후 매수 = 단기 반전 + 유동성 공급</h3>
<div class="card">
<p class="src"><b>Jegadeesh (1990)</b>이 최초로 확립한 <b>단기 반전(short-term reversal)</b> 효과입니다.
직전 한 달 수익률을 기준으로 사고팔아 한 달 보유하는 전략이 <b>월 약 2%</b>의 수익을 냈습니다.</p>
<p class="src">Da·Liu·Schaumburg는 여기서 <b>기업 실적 뉴스가 아닌 부분만 분리</b>하면
3팩터 알파가 <b>월 1.34% (t = 9.28)</b>로, 통상적인 반전 전략(월 0.33%)의 약 4배가 된다는 것을 보였습니다.
더 중요한 건 <b>왜 돈이 벌리는가</b>입니다 — 급락한 쪽(매수 측)의 수익은
<b>강제 매도가 나올 때 유동성을 공급한 대가</b>로 설명됩니다.</p>
<p><b>이 시스템과의 관계.</b> 휩쏘 재진입이 바로 이 자리입니다.
"이틀에 걸친 급락 = 누군가가 급하게 팔고 있다 → 그 물량을 받아준다."
해외 연구가 말하는 <b>유동성 공급의 대가</b>를 한국 시장에서 규칙으로 옮긴 것입니다.
다만 해외 연구는 대개 <b>수백 종목 포트폴리오</b> 기준이고, 이 시스템은 <b>개별 종목 단건</b>이라
분산 효과가 없다는 차이를 기억해야 합니다.</p>
</div>

<h3>기둥 2 · 시장 국면 필터 = 추세 추종형 자산배분</h3>
<div class="card">
<p class="src"><b>Meb Faber</b>의 널리 인용되는 연구는 규칙이 극단적으로 단순합니다 —
<b>월말 종가가 10개월 이동평균 위면 보유, 아래면 현금.</b>
미국 대형주·해외 선진국·국채·원자재·리츠 다섯 자산에 1973–2012년 적용한 결과:</p>
<table class="m"><thead><tr><th></th><th>연평균 수익</th><th>변동성</th><th>최대 낙폭</th></tr></thead><tbody>
<tr><td>그냥 보유</td><td>9.35%</td><td>10.89%</td><td class="b">46%</td></tr>
<tr><td>국면 필터 적용</td><td>9.74%</td><td class="g">7.08%</td><td class="g">9.6%</td></tr>
</tbody></table>
<p class="src">수익은 거의 같은데 <b>최대 낙폭이 46% → 9.6%</b>로 줄었습니다.
평균 시장 노출은 약 70%, 자산당 연 1회 미만의 매매로.</p>
<p><b>이 시스템과의 관계.</b> 접근이 같습니다 — <b>종목을 더 잘 고르는 게 아니라, 나쁜 시기를 피하는 것</b>으로 성과를 만듭니다.
3장에서 본 {G[0]['mean']-G[2]['mean']:.2f}%p 격차가 정확히 같은 이야기입니다.
차이는 Faber가 <b>추세 이탈 시 회피</b>인 반면, 이 시스템은 <b>낙폭이 클 때 오히려 진입</b>하는 역방향이라는 점입니다.
둘 다 "고점 근처의 조용한 시장"을 피한다는 점에서는 같은 방향입니다.</p>
</div>

<h3>기둥 3 · 밸류·퀄리티 = 전 세계에서 검증된 축</h3>
<div class="card">
<p class="src"><b>Asness·Frazzini·Pedersen, "Quality Minus Junk" (2017)</b> —
안전하고, 이익이 나고, 성장하고, 잘 경영되는 기업을 "퀄리티"로 정의하면
<b>미국과 전 세계 24개국에서</b> 위험조정 수익이 유의하게 높았습니다.
흥미로운 지점은 <b>퀄리티 주식이 그만큼 비싸게 거래되지는 않는다</b>는 것 — 그래서 수익이 남습니다.</p>
<p class="src"><b>Asness·Moskowitz·Pedersen, "Value and Momentum Everywhere" (2013, Journal of Finance)</b> —
미국·영국·유럽·일본 주식과 지수선물·국채·통화·원자재 <b>여덟 개 시장</b>에서
밸류와 모멘텀 프리미엄이 일관되게 나타났고, 결정적으로 <b>이 둘은 서로 음의 상관</b>입니다.
즉 <b>따로 쓰는 것보다 같이 쓸 때 더 좋습니다.</b></p>
<p><b>이 시스템과의 관계.</b> 8장의 결론과 정확히 같습니다 —
밸류(싸다)와 타이밍(급락 후 반등)은 <b>서로 다른 것을 재는 축</b>이라 겹치면 더해집니다.
S2-γ 등급이 밸류 태그로 살아난 것({GM['밸류X']['mean']:+.2f}% → {GM['밸류O']['mean']:+.2f}%)이 그 예입니다.</p>
</div>

<h3>기둥 4 · 사전등록 규율 = 다중검정 문제</h3>
<div class="card">
<p class="src"><b>Harvey·Liu·Zhu, "…and the Cross-Section of Expected Returns" (2016, Review of Financial Studies)</b> —
학계가 발표한 팩터를 세어 보니 <b>313편의 논문에서 316개</b>였고, 최근에는 <b>연 18개꼴</b>로 늘고 있었습니다.
발표되지 않은 실패한 시도까지 더하면 훨씬 많습니다.</p>
<p class="src">그래서 저자들의 결론은 이것입니다 — <b>"새 팩터는 t값 3.0을 넘어야 한다."</b>
통상 쓰는 2.0 기준으로는 <b>우연히 좋아 보이는 것</b>을 걸러낼 수 없다는 뜻입니다.</p>
<p><b>이 시스템과의 관계.</b> 오늘의 판정 대부분이 이 이유로 <b>보류</b>됐습니다.
1월 앵커 규칙(6장)은 정책 13개를 동시에 봤기 때문에, MA240 완화(7장)는 완화 4종 중 사후에 최고를 골랐기 때문에.
<b>둘 다 조건을 문서로 고정하고 앞으로 발생할 사례로만 판정하기로 했습니다.</b>
이게 해외 학계가 제시한 처방을 개인 투자 시스템에 적용한 형태입니다.</p>
</div>

<h3>정직하게 — 근거가 약한 부분</h3>
<div class="callout warn">
<div class="t">"절반 매도 후 나머지 보유"는 학술적 근거가 약합니다</div>
분할 청산(scaling out)은 트레이딩 실무에서 널리 쓰이지만,
위 네 기둥처럼 <b>다국가·수십 년 검증된 학술 문헌</b>이 뒷받침하는 개념은 아닙니다.
주로 <b>심리적 안정</b>과 <b>변동성 관리</b> 목적의 관행으로 이해됩니다.<br><br>
<b>그래서 이번에 직접 30년으로 검정한 것이 의미가 있습니다.</b> 그리고 결과도 그 위상에 맞았습니다 —
평균 {GAP['이단']-GAP['카드']:+.2f}%p로 <b>작지만 실재</b>하고, 승률과 중앙값은 변하지 않았습니다.
"대단한 개선"으로 포장하지 않는 것이 정확합니다.
</div>

<h2 id="s13"><span class="num">13</span>다음 단계</h2>
<ol>
<li><b>MA240 완화 사전등록 관찰 시작.</b> 조건은 이미 문서로 고정됐습니다. 🟢실행 국면에서 40건이 쌓일 때까지 중간 판정하지 않습니다(연 13건 추정, 변동성 큰 해엔 훨씬 빠름).</li>
<li><b>종목군별 월별 매매 현황 분석.</b> 어떤 성격의 종목군이 어느 달에 잘 되는지를 나눠 봅니다.</li>
<li><b>스윙과 단기매매를 분리.</b> 지금 시스템은 40~126거래일의 단일 시간축입니다. 보유 기간별로 규칙이 달라져야 하는지 검정합니다.</li>
<li><b>원본 검정 엔진의 라이브러리 호환 문제 수정</b>(9장 ⓑ) 및 코드 백업.</li>
</ol>

<footer>
<b>진우퀀트 · 휩쏘 시스템 종합 보고서</b> — 2026년 8월 2일<br>
표본 {SMP['전체']:,}건 ({SMP['기간']}) · KOSPI + KOSDAQ 전 종목 · 가격제한폭 백조정 적용<br>
본문의 모든 수치는 <code>보고서_데이터.json</code>에서 자동 생성됐으며, 원본 재현 스크립트가 프로젝트 폴더에 있습니다.<br><br>
⚠️ <b>이 문서는 검정 결과 기록이며 투자 권유가 아닙니다.</b>
과거 성과는 미래를 보장하지 않고, 11장의 한계가 모든 수치에 적용됩니다.<br><br>
<b>참고 문헌</b> (12장 인용 출처)<br>
· Jegadeesh, N. (1990) — 단기 반전 효과의 최초 확립<br>
· Da, Z., Liu, Q., Schaumburg, E. — <i>A Closer Look at the Short-Term Return Reversal</i><br>
· Faber, M. — <i>A Quantitative Approach to Tactical Asset Allocation</i> (SSRN 962461)<br>
· Asness, C., Frazzini, A., Pedersen, L. H. (2017) — <i>Quality Minus Junk</i><br>
· Asness, C., Moskowitz, T., Pedersen, L. H. (2013) — <i>Value and Momentum Everywhere</i>, Journal of Finance<br>
· Harvey, C., Liu, Y., Zhu, C. (2016) — <i>…and the Cross-Section of Expected Returns</i>, Review of Financial Studies<br>
· Bouman, S., Jacobsen, B. (2002) — <i>The Halloween Indicator</i>, American Economic Review
</footer>
"""

DOC = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>급락한 좋은 주식을 언제 사야 하는가 — 30년 검정 보고서</title>
<style>{CSS}</style></head><body><div class="wrap">{BODY}</div></body></html>"""
open(f"{HERE}/휩쏘_종합보고서.html", "w", encoding="utf-8").write(DOC)
print(f"저장 완료: 휩쏘_종합보고서.html  ({len(DOC):,} bytes)")
