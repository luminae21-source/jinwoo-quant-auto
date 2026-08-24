#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
jq_trade_guide.py — 주봉 매매방법 가이드 카드뉴스(PNG)
================================================================
목적: 이미 생성된 주봉분석_YYYY-MM-DD.md(38종)를 읽어, 20주선 배열로
      '추세유지 / 눌림·관찰 / 하락·회피' 3그룹 자동분류 + 매도규칙서 신호등을
      한 장 카드로. ⚠️ 사실·규칙 안내일 뿐 매수/매도 추천 아님. 결정·책임 본인.
산출: 주봉_매매가이드_YYYY-MM-DD.png (+ OneDrive 동기화)
무network(Pillow만). 사용: python jq_trade_guide.py
"""
import os, re, glob, sys
from datetime import date

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
HERE = os.path.dirname(os.path.abspath(__file__))


def _font(size, bold=False):
    from PIL import ImageFont
    cand = ([r"C:\Windows\Fonts\malgunbd.ttf"] if bold else []) + [
        r"C:\Windows\Fonts\malgun.ttf",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"]
    for p in cand:
        if os.path.exists(p):
            return ImageFont.truetype(p, size)
    return ImageFont.load_default()


def latest_md():
    fs = sorted(glob.glob(os.path.join(HERE, "주봉분석_*.md")))
    return fs[-1] if fs else None


def parse_md(path):
    """md → [(name, above(bool), slope), ...]"""
    txt = open(path, encoding="utf-8").read()
    blocks = re.split(r"\n## ", txt)
    out = []
    for b in blocks:
        m = re.match(r"(.+?)\((\d{6})\)", b)
        if not m:
            continue
        name = m.group(1).strip()
        pos = re.search(r"\(20주선 (위|아래)\)", b)
        slp = re.search(r"20주선 방향.*?\*\*(상승|하락|횡보)\*\*", b)
        if not pos or not slp:
            continue
        above = pos.group(1) == "위"
        slope = slp.group(1)
        # 이격%
        gm = re.search(r"이격 \*\*?([+-]?\d+\.\d+)%", b) or re.search(r"이격 ([+-]?\d+\.\d+)%", b)
        gap = float(gm.group(1)) if gm else 0.0
        out.append((name, above, slope, gap))
    return out


def classify(rows):
    keep, watch, avoid = [], [], []
    for name, above, slope, gap in rows:
        if above and slope == "상승":
            keep.append((name, gap))
        elif (not above) and slope == "하락":
            avoid.append((name, gap))
        else:
            watch.append((name, gap))
    keep.sort(key=lambda x: -x[1])
    watch.sort(key=lambda x: -x[1])
    avoid.sort(key=lambda x: x[1])
    return keep, watch, avoid


def wrap_names(items, font, draw, maxw):
    """[(name,gap)] → 여러 줄. 각 줄은 'name(±gap%)' 나열."""
    lines, cur = [], ""
    for name, gap in items:
        chip = f"{name}({gap:+.0f}%)"
        test = chip if not cur else cur + "   " + chip
        if draw.textlength(test, font=font) > maxw and cur:
            lines.append(cur); cur = chip
        else:
            cur = test
    if cur:
        lines.append(cur)
    return lines or ["(없음)"]


BG = (15, 17, 21); ACC = (255, 122, 69)
GREEN = (63, 179, 122); RED = (226, 96, 106); YEL = (224, 176, 32)
TXT = (232, 234, 237); SUB = (154, 160, 170); LINE = (38, 42, 51)


def render(rows, today):
    from PIL import Image, ImageDraw
    W = 860; pad = 26
    keep, watch, avoid = classify(rows)
    above_n = sum(1 for r in rows if r[1])
    tot = len(rows)

    tf = _font(30, True); h2 = _font(20, True); bf = _font(17); bfb = _font(17, True)
    sf = _font(15); nf = _font(16)

    tmp = Image.new("RGB", (10, 10)); td = ImageDraw.Draw(tmp)
    maxw = W - 2 * pad - 16

    # 4분면 행동지침
    quad = [
        (GREEN, "20주선 위 + 상승", "중기 상승추세 유지. 보유는 트레일링으로 끝까지, 신규는 눌림을 기다린다."),
        (YEL, "20주선 아래 + 상승", "추세전환·눌림 구간. 진입하려면 손절가를 동시에 정하고 소량·분할."),
        (YEL, "20주선 위 + 횡보", "방향 탐색. 돌파/이탈 확인 전 관망. 보유는 규칙대로 신호등 점검."),
        (RED, "20주선 아래 + 하락", "중기 하락추세. 신규진입 자제. 보유는 손절선·thesis 즉시 점검."),
    ]
    # 신호등 (색 원형 마커 + 태그)
    sig = [
        (RED, "손절", "종가 < 손절선(−2.5ATR/−20%) 또는 트레일링 이탈 → 다음날 매도"),
        (YEL, "익절", "+1R 도달 → 절반 확정, 나머지 트레일링"),
        (YEL, "시간", "20거래일 ±5% 횡보·무반응 → 청산 검토"),
        (RED, "무효화", "thesis 붕괴(실적쇼크·테마소멸) → 즉시 매도"),
        (GREEN, "유지", "위 어디에도 없음 → 보유·관찰"),
    ]

    kl = wrap_names(keep, nf, td, maxw - 10)
    wl = wrap_names(watch, nf, td, maxw - 10)
    al = wrap_names(avoid, nf, td, maxw - 10)

    # 높이 계산
    y = 0
    y += 96                       # 타이틀
    y += 44                       # breadth 요약
    y += 34 + len(quad) * 46 + 14  # 4분면
    # 분류 3박스
    grp_h = lambda lines: 34 + len(lines) * 26 + 14
    y += grp_h(kl) + grp_h(wl) + grp_h(al)
    y += 34 + len(sig) * 30 + 10   # 신호등
    y += 40                        # 푸터
    H = y + 10

    img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
    d.rectangle([0, 0, W, 6], fill=ACC)
    y = 22
    d.text((pad, y), f"주봉 매매방법 가이드 · {today}", font=tf, fill=(255, 255, 255)); y += 40
    d.text((pad, y), "20주선 배열 → 행동지침 + 매도규칙서 신호등 · 사실·규칙 안내(추천 아님)", font=sf, fill=SUB)
    y += 30

    # breadth
    keep_n, watch_n, avoid_n = len(keep), len(watch), len(avoid)
    d.text((pad, y), f"이번주 폭: 20주선 위 {above_n}/{tot}종  ·  ", font=bfb, fill=TXT)
    xoff = pad + td.textlength(f"이번주 폭: 20주선 위 {above_n}/{tot}종  ·  ", font=bfb)
    d.text((xoff, y), f"추세유지 {keep_n}", font=bfb, fill=GREEN)
    xoff += td.textlength(f"추세유지 {keep_n}", font=bfb)
    d.text((xoff, y), "  /  ", font=bfb, fill=SUB); xoff += td.textlength("  /  ", font=bfb)
    d.text((xoff, y), f"눌림관찰 {watch_n}", font=bfb, fill=YEL)
    xoff += td.textlength(f"눌림관찰 {watch_n}", font=bfb)
    d.text((xoff, y), "  /  ", font=bfb, fill=SUB); xoff += td.textlength("  /  ", font=bfb)
    d.text((xoff, y), f"하락회피 {avoid_n}", font=bfb, fill=RED)
    y += 44

    # 4분면
    d.text((pad, y), "■ 20주선 4분면 행동지침", font=h2, fill=ACC); y += 34
    for col, head, desc in quad:
        d.rectangle([pad, y + 4, pad + 6, y + 36], fill=col)
        d.text((pad + 16, y), head, font=bfb, fill=col)
        d.text((pad + 16, y + 22), desc, font=sf, fill=TXT)
        y += 46
    y += 14

    def group(title, col, lines, note):
        nonlocal y
        d.text((pad, y), f"■ {title}", font=h2, fill=col)
        d.text((pad + td.textlength(f"■ {title}", font=h2) + 12, y + 4), note, font=sf, fill=SUB)
        y += 34
        for ln in lines:
            d.text((pad + 10, y), ln, font=nf, fill=TXT); y += 26
        y += 14

    group(f"추세유지 {keep_n}종", GREEN, kl, "보유=트레일링 · 신규=눌림 대기")
    group(f"눌림·관찰 {watch_n}종", YEL, wl, "진입 시 손절가 동시설정 · 소량")
    group(f"하락·회피 {avoid_n}종", RED, al, "신규 자제 · 보유는 손절선 점검")

    # 신호등
    d.text((pad, y), "■ 매도 신호등 (매일 보유점검.py 연동)", font=h2, fill=ACC); y += 34
    for col, tag, desc in sig:
        d.ellipse([pad + 4, y + 5, pad + 18, y + 19], fill=col)
        d.text((pad + 28, y), tag, font=bfb, fill=col)
        d.text((pad + 120, y), desc, font=sf, fill=TXT)
        y += 30
    y += 10
    d.text((pad, y), "핵심: 살 때 팔 자리를 정하고, 그 자리가 오면 감정 없이 실행 · 투자자문 아님 · 집행·책임 진우",
           font=sf, fill=(90, 96, 104))

    out = os.path.join(HERE, f"주봉_매매가이드_{today}.png")
    img.save(out)
    return out


def sync_onedrive(*paths):
    import shutil
    tgt = os.path.expanduser(r"~\OneDrive\문서\Claude\Projects\진우퀀트")
    if os.path.isdir(tgt):
        for p in paths:
            if p and os.path.exists(p):
                try:
                    shutil.copy(p, tgt)
                except Exception:
                    pass


def main():
    md = latest_md()
    if not md:
        print("[오류] 주봉분석_*.md 없음. 먼저 주봉분석을 실행하세요."); return 2
    rows = parse_md(md)
    if not rows:
        print("[오류] md 파싱 실패."); return 3
    today = os.path.basename(md).replace("주봉분석_", "").replace(".md", "")
    out = render(rows, today)
    sync_onedrive(out)
    k, w, a = classify(rows)
    print(f"[산출] {os.path.basename(out)}  (추세유지 {len(k)} · 눌림관찰 {len(w)} · 하락회피 {len(a)}, 총 {len(rows)}종)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
