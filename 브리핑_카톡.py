#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
브리핑_카톡.py — 시장브리핑(.md) → 카톡용 텍스트 요약(.txt) + 이미지(.png)
==============================================================================
목적: 오픈채팅에 바로 붙여넣거나 이미지로 공유하기 좋게 변환.
입력: 최신 시장브리핑_YYYYMMDD.md (없으면 시장브리핑_최신.md). 핵심 줄만 추려 이모지 요약.
산출: 시장브리핑_카톡.txt (복붙용) · 시장브리핑_카톡.png (이미지, Pillow). 둘 다 항상 .txt는 생성.
이미지: Pillow + 한글폰트(맑은 고딕). Pillow/폰트 없으면 txt만 만들고 안내(graceful).
사용: python 브리핑_카톡.py [--selftest]   ·   실행: 브리핑_카톡_실행.bat
무수정: 시장브리핑_생성.py·production 등 기존 산출물. 신규(변환기).
"""
import os, sys, re, glob
from datetime import date

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
HERE = os.path.dirname(os.path.abspath(__file__))


def latest_md():
    fs = sorted(glob.glob(os.path.join(HERE, "시장브리핑_2*.md")))
    if fs:
        return fs[-1]
    p = os.path.join(HERE, "시장브리핑_최신.md")
    return p if os.path.exists(p) else None


def _line(lines, *kws):
    """kws 모두 포함하는 첫 줄(앞 '- ' 제거). 없으면 ''."""
    for l in lines:
        if all(k in l for k in kws):
            return l.lstrip("- ").strip()
    return ""


def _num(s):
    m = re.search(r"-?[\d,]+\.?\d*", s)
    return m.group(0) if m else ""


def _pred_line():
    """익일예측_최신.md(코스피)·_kosdaq.md(코스닥) 방향을 한 줄로. 없으면 ''."""
    emj = {"상승": "🔺", "하락": "🔻", "중립": "⏸"}
    parts = []
    for suf, nm in (("", "코스피"), ("_kosdaq", "코스닥")):
        p = os.path.join(HERE, f"익일예측_최신{suf}.md")
        if os.path.exists(p):
            try:
                t = open(p, encoding="utf-8-sig").read()
                m = re.search(r"익일 방향:\s*\*\*(\S+?)\*\*", t)
                if m:
                    dd = m.group(1); parts.append(f"{nm} {emj.get(dd,'')}{dd}")
            except Exception:
                pass
    return ("📈 익일예상 " + " / ".join(parts)) if parts else ""


def build_summary(md_text):
    """md → 카톡용 요약 라인 리스트."""
    lines = [l.strip() for l in md_text.splitlines()]
    # 날짜
    mdt = re.search(r"# 시장 현황 브리핑 — (\d{4}-\d{2}-\d{2})", md_text)
    datestr = mdt.group(1) if mdt else str(date.today())
    out = [f"📊 시장 브리핑 · {datestr}", ""]
    kospi = _line(lines, "코스피", "(")
    kosdaq = _line(lines, "코스닥", "(")
    if kospi or kosdaq:
        out.append("🇰🇷 " + " · ".join(x for x in [kospi.replace("코스피", "코스피"), kosdaq] if x)[:80])
    vk = _line(lines, "VKOSPI")
    if vk:
        out.append("😱 " + vk.replace("**", ""))
    # 미국장
    sp = _line(lines, "S&P500"); nas = _line(lines, "나스닥"); sox = _line(lines, "필라델피아")
    us = " · ".join(x for x in [sp, nas, sox] if x)
    if us:
        out.append("🇺🇸 " + us[:90])
    tnx = _line(lines, "美10년"); krw = _line(lines, "원/달러")
    rate = " · ".join(x for x in [tnx.replace("**", ""), krw] if x)
    if rate:
        out.append("💵 " + rate[:90])
    # 결론(룰)
    concl = ""
    for i, l in enumerate(lines):
        if "근거 기반 결론" in l:
            for j in range(i+1, min(i+5, len(lines))):
                if lines[j].startswith("-"):
                    concl = lines[j].lstrip("- ").strip(); break
            break
    if concl:
        out.append("📌 " + re.sub(r"\*|\(근거.*?\)", "", concl).strip()[:80])
    # 가까운 이벤트 D-day
    ev = ""
    for l in lines:
        m = re.search(r"(\d{4}-\d{2}-\d{2})\s*:\s*(.+?)\s*\(D-(\d+)\)", l)
        if m:
            ev = f"{m.group(2)} D-{m.group(3)}"; break
    if ev:
        out.append("🗓️ " + ev)
    pe = _pred_line()
    if pe:
        out.append(pe)
    out += ["", "※ 공개지표 요약 · 매수매도 추천 아님"]
    return datestr, out


def write_txt(out_lines):
    p = os.path.join(HERE, "시장브리핑_카톡.txt")
    open(p, "w", encoding="utf-8").write("\n".join(out_lines))
    return p


def _font(size):
    from PIL import ImageFont
    for path in (r"C:\Windows\Fonts\malgun.ttf", r"C:\Windows\Fonts\malgunbd.ttf",
                 "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
                 "/Library/Fonts/AppleGothic.ttf"):
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


def render_png(out_lines):
    try:
        from PIL import Image, ImageDraw
    except Exception:
        print("  (Pillow 미설치 — 이미지 건너뜀. pip install Pillow 후 재실행하면 png도 생성)")
        return None
    W = 740
    pad = 36
    title_f = _font(34); body_f = _font(26); small_f = _font(20)
    # 높이 계산
    y = pad
    rows = []
    for i, ln in enumerate(out_lines):
        if i == 0:
            rows.append((ln, title_f, 46));
        elif ln.startswith("※"):
            rows.append((ln, small_f, 30))
        elif ln == "":
            rows.append(("", body_f, 14))
        else:
            rows.append((ln, body_f, 40))
    H = pad*2 + sum(h for _, _, h in rows)
    img = Image.new("RGB", (W, H), (15, 17, 21))
    d = ImageDraw.Draw(img)
    # 상단 액센트 바
    d.rectangle([0, 0, W, 6], fill=(255, 122, 69))
    for ln, fnt, h in rows:
        color = (232, 234, 237)
        if fnt is title_f: color = (255, 255, 255)
        if ln.startswith("※"): color = (120, 126, 136)
        if ln.startswith("📌"): color = (255, 198, 163)
        d.text((pad, y), ln, font=fnt, fill=color)
        y += h
    p = os.path.join(HERE, "시장브리핑_카톡.png")
    img.save(p)
    return p


def _sync_onedrive(*paths):
    """카톡 파일을 OneDrive(폰 동기화)로 복사."""
    import shutil
    for tgt in (os.path.expanduser(r"~\OneDrive\문서\Claude\Projects\진우퀀트"),):
        if os.path.isdir(tgt):
            for p in paths:
                if p and os.path.exists(p):
                    try:
                        shutil.copy(p, tgt)
                    except Exception:
                        pass


def run():
    md = latest_md()
    if not md:
        print("❌ 시장브리핑 md 없음 — 먼저 시장브리핑_실행.bat 실행."); return
    text = open(md, encoding="utf-8-sig").read()
    datestr, out = build_summary(text)
    txt = write_txt(out)
    png = render_png(out)
    _sync_onedrive(txt, png)
    print("\n".join(out))
    print(f"\n[산출] 시장브리핑_카톡.txt{' · 시장브리핑_카톡.png' if png else ''}")
    print("→ 카톡: txt 내용 복붙 또는 png 이미지 공유 (폰 OneDrive에서)")


def _selftest():
    ok = 0
    def chk(n, c):
        nonlocal ok; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    sample = """# 시장 현황 브리핑 — 2026-06-22
## ① 국내 (선물·옵션 환경)
- 코스피            9,114.55 (+0.69%) · 상승
- 코스닥            968.40 (+0.19%) · 보합
- VKOSPI: **83.57** (등락 +4.14%) · 전일比 상승 — 변동성 확대
## ② 미국장 (밤사이)
- S&P500         7,514.80 (+0.19%) · 보합
- 나스닥            26,489.59 (-0.11%) · 보합
- 필라델피아반도체       14,490.18 (+1.03%) · 미 반도체 강세
- 美10년 ^TNX        4.493 (전일대비 +4bp) · 금리 중립
- 원/달러           1,537.84 (+0.02%) · 환율 안정
## ④ 이벤트 캘린더 (D-day)
- 2026-07-09 : 옵션만기 (D-17)
**근거 기반 결론(룰):**
- 금리 중립  *(근거: 美10년 +4bp)*
"""
    datestr, out = build_summary(sample)
    chk("날짜 추출", datestr == "2026-06-22")
    joined = "\n".join(out)
    chk("코스피 포함", "코스피" in joined and "9,114" in joined)
    chk("코스닥 포함", "968.40" in joined)
    chk("VKOSPI 포함", "VKOSPI" in joined and "83.57" in joined)
    chk("미국장 포함", "S&P500" in joined and "필라델피아" in joined)
    chk("결론 포함", "금리 중립" in joined)
    chk("이벤트 D-day", "옵션만기" in joined and "D-17" in joined)
    chk("추천아님 고지", "추천 아님" in joined)
    print(f"✅ 브리핑_카톡 셀프테스트 ({ok}/8)")
    return ok == 8


def main():
    if "--selftest" in sys.argv:
        _selftest(); return
    run()


if __name__ == "__main__":
    main()
