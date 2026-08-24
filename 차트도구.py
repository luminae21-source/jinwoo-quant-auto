# -*- coding: utf-8 -*-
"""완성본 보고서 빌더 — 모든 수치는 보고서_데이터.json(실제 검정 산출물)에서만 읽는다."""
import json, html as H, sys
sys.stdout.reconfigure(encoding="utf-8")
HERE = "/home/claude/jq"
D = {}
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


def vbar(items, w=720, h=250, pad_b=46, pad_t=26, pad_l=42, unit="%", title="", color=None, signed=True, dec=1):
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
        s.append(f'<text x="{pad_l-8}" y="{gy+3.5:.1f}" fill="{MUT}" font-size="10.5" text-anchor="end">'
                 + (f"{gv:+.1f}" if signed else f"{gv:,.0f}") + '</text>')
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
        lab = (f"{v:+.{dec}f}" if signed else f"{v:,.{dec}f}") + ("%" if (not signed and unit == "%") else "")
        s.append(f'<text x="{cx:.1f}" y="{ly:.1f}" fill="{INK}" font-size="11" font-weight="600" text-anchor="middle">{lab}</text>')
        s.append(f'<text x="{cx:.1f}" y="{h-24}" fill="{INK2}" font-size="11" text-anchor="middle">{esc(it["label"])}</text>')
        if it.get("sub"):
            s.append(f'<text x="{cx:.1f}" y="{h-10}" fill="{MUT}" font-size="9.5" text-anchor="middle">{esc(it["sub"])}</text>')
    s.append('</svg>')
    return "".join(s)


def grouped(cats, series, w=720, h=270, unit="%", title="", signed=True, dec=1):
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
        s.append(f'<text x="{pad_l-8}" y="{gy+3.5:.1f}" fill="{MUT}" font-size="10.5" text-anchor="end">'
                 + (f"{gv:+.1f}" if signed else f"{gv:,.0f}") + '</text>')
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
            lab = f"{v:+.{dec}f}" if signed else f"{v:,.{dec}f}"
            s.append(f'<text x="{x+(bw-2)/2:.1f}" y="{ly:.1f}" fill="{INK}" font-size="9.5" text-anchor="middle">{lab}</text>')
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

