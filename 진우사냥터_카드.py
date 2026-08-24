#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우사냥터_카드.py — 진우사냥터_후보.csv → 카드 이미지(PNG) 2종

진우사냥터_스크리너.py가 만든 CSV를 읽어 카톡/공유용 카드 PNG를 만든다.
스타일: jq_cards.py와 동일(다크 테마·오렌지 액센트).

산출: 진우사냥터_카드_TOP.png   (사냥터 상위 후보 랭킹)
      진우사냥터_카드_6종목.png (진우 6종목 위치)
사용: py 진우사냥터_카드.py [--top 12]
      py 진우사냥터_카드.py --self-test

투자자문 아님 · 발굴 ≠ 매수신호 · 결정·책임은 본인.
"""
import os, sys, csv, argparse
from PIL import Image, ImageDraw, ImageFont

BASE = os.path.dirname(os.path.abspath(__file__))
CSV_IN = os.path.join(BASE, "진우사냥터_후보.csv")
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

# 색 (jq_cards.py 동일)
BG = (15, 17, 21); PANEL = (23, 26, 33); ACC = (255, 122, 69)
GRN = (63, 179, 122); RED = (226, 96, 106); YEL = (224, 176, 32)
GREY = (150, 156, 166); BLUE = (90, 160, 240); TXT = (232, 234, 237); SUB = (150, 156, 166)


def _font_paths():
    reg = [r"C:\Windows\Fonts\malgun.ttf",
           "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
           "/usr/share/fonts/truetype/nanum/NanumGothic.ttf"]
    bold = [r"C:\Windows\Fonts\malgunbd.ttf",
            "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"]
    fr = next((p for p in reg if os.path.exists(p)), None)
    fb = next((p for p in bold if os.path.exists(p)), fr)
    return fr, fb


FREG, FBLD = _font_paths()


def F(sz, bold=False):
    p = FBLD if bold else FREG
    try:
        return ImageFont.truetype(p, sz) if p else ImageFont.load_default()
    except Exception:
        return ImageFont.load_default()


def read_rows(path):
    with open(path, encoding="utf-8-sig", newline="") as f:
        rows = list(csv.DictReader(f))
    out = []
    for r in rows:
        def num(k, d=0.0):
            try:
                return float(r.get(k, "") or d)
            except ValueError:
                return d
        out.append({
            "rank": int(num("rank")), "code": r.get("code", ""), "name": r.get("name", ""),
            "src": r.get("src", ""), "score": num("score"), "pbr": num("pbr"),
            "pbr_rank": int(num("pbr_rank")), "vol": num("vol60") * 100,
            "vol_rank": int(num("vol_rank")), "close": int(num("close")),
            "stop": int(num("stop")), "stop_pct": num("stop_pct"), "qty": int(num("qty")),
            "j6": str(r.get("is_jinwoo6", "")).strip().lower() in ("true", "1"),
            "n_univ": int(num("n_univ")),
        })
    return out


def _won(n):
    return f"{n:,}"


def card_top(rows, top, outp):
    n_univ = rows[0]["n_univ"] if rows else 0
    items = rows[:top]
    W = 860
    H = 150 + len(items) * 40 + 92
    img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
    pad = 30
    d.text((pad, 26), "진우 사냥터 발굴 · TOP", font=F(30, True), fill=(255, 255, 255))
    d.text((pad, 66), f"사냥터내 저PBR·저변동 기울기 랭킹 · 유니버스 {n_univ}종목 · ★=진우 6종목",
           font=F(15), fill=SUB)
    d.text((pad, 90), "동점자 가르기 · 발굴 ≠ 매수신호", font=F(14), fill=ACC)
    # header row
    y = 128
    cols = [("순", pad, "l"), ("종목", pad + 46, "l"), ("PBR", pad + 300, "r"),
            ("변동%", pad + 400, "r"), ("점수", pad + 500, "r"),
            ("손절폭", pad + 610, "r"), ("수량", pad + 730, "r")]
    for lab, x, al in cols:
        w = d.textlength(lab, font=F(14))
        d.text((x - (w if al == "r" else 0), y), lab, font=F(14), fill=GREY)
    y += 26
    d.line([(pad, y), (W - pad, y)], fill=(40, 46, 57), width=1); y += 8
    for r in items:
        if r["j6"]:
            d.rectangle([pad - 8, y - 3, W - pad + 8, y + 33], fill=(32, 26, 22))
            d.text((pad - 6, y + 6), "★", font=F(15), fill=ACC)
        rc = ACC if r["j6"] else TXT
        d.text((pad + 14, y + 5), f"{r['rank']}", font=F(17, True), fill=rc)
        d.text((pad + 46, y + 5), r["name"][:12], font=F(17), fill=TXT)
        def rt(val, x, col=TXT, fn=None):
            fn = fn or F(16)
            w = d.textlength(val, font=fn)
            d.text((pad + x - w, y + 6), val, font=fn, fill=col)
        rt(f"{r['pbr']:.2f}", 300, GRN if r['pbr'] < 1 else TXT)
        rt(f"{r['vol']:.1f}", 400)
        rt(f"{r['score']:.2f}", 500, ACC, F(16, True))
        rt(f"-{r['stop_pct']:.0f}%", 610, RED)
        rt(_won(r['qty']), 730)
        y += 40
    d.line([(pad, y + 4), (W - pad, y + 4)], fill=(40, 46, 57), width=1)
    d.text((pad, y + 16), "손절 = max(현재가−2.5·ATR14, 현재가×0.80) · 리스크 1% · 섹터당 2종·동시 5~7종",
           font=F(13), fill=SUB)
    d.text((pad, y + 40), "투자자문 아님 · 기울기는 조건부(2028 재판정) · 결정·책임 본인",
           font=F(13), fill=(120, 126, 136))
    img.save(outp)
    return outp


def card_j6(rows, outp):
    j6 = sorted([r for r in rows if r["j6"]], key=lambda r: r["rank"])
    n_univ = rows[0]["n_univ"] if rows else 0
    W = 820
    H = 132 + max(1, len(j6)) * 58 + 80
    img = Image.new("RGB", (W, H), BG); d = ImageDraw.Draw(img)
    pad = 30
    d.text((pad, 26), "진우 6종목 · 사냥터 내 위치", font=F(29, True), fill=(255, 255, 255))
    d.text((pad, 66), f"내 보유/관심 종목이 '더 싸고 덜 출렁이는' 순위에서 어디 있나 · 유니버스 {n_univ}종목",
           font=F(15), fill=SUB)
    d.text((pad, 90), "낮은 순위 = 상대적으로 저PBR·저변동 쪽", font=F(14), fill=ACC)
    y = 126
    if not j6:
        d.text((pad, y), "6종목이 유니버스에 없음", font=F(16), fill=GREY)
    for r in j6:
        d.rectangle([pad, y, W - pad, y + 50], fill=PANEL)
        d.text((pad + 14, y + 8), f"#{r['rank']}", font=F(22, True), fill=ACC)
        d.text((pad + 90, y + 6), r["name"], font=F(19, True), fill=TXT)
        d.text((pad + 90, y + 30), f"{r['code']} · {r['src']}", font=F(13), fill=SUB)
        def rt(val, x, col, fn):
            w = d.textlength(val, font=fn)
            d.text((W - pad - x - w, y + 6), val, font=fn, fill=col)
        d.text((W - pad - 300, y + 8), "PBR", font=F(12), fill=SUB)
        d.text((W - pad - 300, y + 26), f"{r['pbr']:.2f}", font=F(18, True),
               fill=GRN if r['pbr'] < 3 else TXT)
        d.text((W - pad - 180, y + 8), "변동%", font=F(12), fill=SUB)
        d.text((W - pad - 180, y + 26), f"{r['vol']:.1f}", font=F(18, True), fill=TXT)
        d.text((W - pad - 70, y + 8), "점수", font=F(12), fill=SUB)
        d.text((W - pad - 70, y + 26), f"{r['score']:.2f}", font=F(18, True), fill=ACC)
        y += 58
    d.text((pad, y + 14), "이 툴은 절대 저평가가 아니라 '진우 후보 안 상대 랭킹'. 발굴 ≠ 매수신호.",
           font=F(13), fill=SUB)
    d.text((pad, y + 38), "투자자문 아님 · 결정·책임 본인", font=F(13), fill=(120, 126, 136))
    img.save(outp)
    return outp


def _self_test():
    import tempfile
    ok = tot = 0

    def chk(nm, c):
        nonlocal ok, tot
        tot += 1; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {nm}")

    chk("CJK 폰트 발견", FREG is not None)
    tmp = tempfile.mkdtemp()
    cp = os.path.join(tmp, "t.csv")
    with open(cp, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.writer(f)
        w.writerow(["rank", "code", "name", "sector", "src", "score", "pbr", "pbr_rank",
                    "vol60", "vol_rank", "close", "mcap", "adv20", "atr14",
                    "stop", "stop_pct", "qty", "n_univ", "is_jinwoo6"])
        for i in range(3):
            w.writerow([i + 1, f"00000{i}", f"종목{i}", "반도체", "섹터", 0.9 - i * .1,
                        0.4 + i, 3 + i, 0.03, 10, 5000, 1e12, 1e9, 400,
                        4000, 20.0, 50, 450, "False"])
        w.writerow([158, "450080", "에코프로머티", "이차전지", "섹터+특성", 0.6, 2.96, 222,
                    0.051, 103, 100000, 2.6e12, 1e10, 5000, 80000, 20.0, 12, 450, "True"])
    rows = read_rows(cp)
    chk("CSV 파싱 4행", len(rows) == 4)
    p1 = card_top(rows, 12, os.path.join(tmp, "top.png"))
    p2 = card_j6(rows, os.path.join(tmp, "j6.png"))
    chk("TOP 카드 생성·비어있지않음", os.path.exists(p1) and os.path.getsize(p1) > 2000)
    chk("6종목 카드 생성·비어있지않음", os.path.exists(p2) and os.path.getsize(p2) > 2000)
    from PIL import Image as _I
    chk("TOP PNG 유효 이미지", _I.open(p1).size[0] > 100)
    chk("6종목 카드 j6 포착", any(r["j6"] for r in rows))
    print(f"\n셀프테스트: {ok}/{tot}")
    return ok == tot


def main():
    ap = argparse.ArgumentParser(description="jinwoo hunting-ground cards")
    ap.add_argument("--top", type=int, default=12)
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        return 0 if _self_test() else 1
    if not os.path.exists(CSV_IN):
        print(f"  [없음] {os.path.basename(CSV_IN)} — 먼저 진우사냥터_스크리너.py 실행")
        return 2
    rows = read_rows(CSV_IN)
    p1 = card_top(rows, a.top, os.path.join(BASE, "진우사냥터_카드_TOP.png"))
    p2 = card_j6(rows, os.path.join(BASE, "진우사냥터_카드_6종목.png"))
    print(f"저장: {os.path.basename(p1)} · {os.path.basename(p2)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
