# -*- coding: utf-8 -*-
"""jq_mcard.py — 카톡 말풍선용 '크게 보이는' 모바일 카드 (2026-11-27)
================================================================================
왜: 카톡 '나에게 보내기' 피드 말풍선은 이미지를 화면 폭의 약 58%로 줄이고,
    가로:세로 2:1 ~ 3:4 범위로 잘라서 보여 준다(크기 정보가 없으면 1:1로 잘림).
    예전 카드(폭 820px · 글씨 13~16px · 세로 1:1.55)는 말풍선에서 글씨가 4~5dp로 줄고
    위아래가 잘려 읽을 수 없었다.
어떻게: 폭 1080px · 쪽당 최대 1080×1440(정확히 3:4) · 본문 58px(말풍선에서 약 12dp)
    · 제목 70px · 밝은 글자색. 내용이 길면 자동으로 여러 쪽(_p1, _p2 …)으로 나눈다.
쓰는 법:
    c = Card("마감 브리핑", "2026-11-27", accent=ACC)
    c.sec("지수 마감"); c.stat("코스피", "4,105.20", "▲ +1.23%", GREEN)
    c.row("기관", "+1,234억", rc=GREEN); c.para("오늘의 동인 …")
    paths = c.save("마감브리핑_카톡", HERE, dstamp)   # 카드뉴스/날짜/마감브리핑_카톡_p1.png …
"""
import os, glob, datetime
from PIL import Image, ImageDraw, ImageFont

W = 1080          # 쪽 폭
H_MAX = 1440      # 쪽 최대 높이 (3:4 — 카톡 말풍선 최대 비율)
H_MIN = 540       # 쪽 최소 높이 (2:1 — 카톡 말풍선 최소 비율)
PAD = 56

TITLE, SEC, BIG, BODY, SMALL = 70, 52, 76, 58, 44

BG = (14, 16, 21); PANEL = (26, 29, 37); LINE = (52, 57, 68)
TXT = (246, 247, 249); SUB = (206, 211, 220); DIM = (165, 171, 182)
ACC = (255, 140, 80); GREEN = (82, 222, 152); RED = (255, 108, 118)
YEL = (255, 206, 72); BLUE = (112, 182, 255); WHITE = (255, 255, 255)

_REG = [r"C:\Windows\Fonts\malgun.ttf",
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 1),
        ("/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc", 0)]
_BOLD = [r"C:\Windows\Fonts\malgunbd.ttf",
         ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 1),
         ("/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc", 0)]
_cache = {}


def font(size, bold=False):
    key = (size, bold)
    if key in _cache:
        return _cache[key]
    f = None
    for cand in (_BOLD + _REG) if bold else _REG:
        path, idx = (cand, 0) if isinstance(cand, str) else cand
        if os.path.exists(path):
            try:
                f = ImageFont.truetype(path, size, index=idx); break
            except Exception:
                continue
    if f is None:
        f = ImageFont.load_default()
    _cache[key] = f
    return f


_meas = ImageDraw.Draw(Image.new("RGB", (8, 8)))


def tw(text, size, bold=False):
    return _meas.textlength(text, font=font(size, bold))


def wrap(text, size, maxw, bold=False):
    """글자 단위 줄바꿈(한글은 띄어쓰기가 적어 글자 단위가 안전). 공백 우선."""
    out = []
    for para in str(text).split("\n"):
        line = ""
        for ch in para:
            if tw(line + ch, size, bold) <= maxw:
                line += ch
                continue
            cut = line.rfind(" ")
            if ch != " " and cut >= len(line) * 0.6:
                out.append(line[:cut]); line = line[cut + 1:] + ch
            else:
                out.append(line.rstrip()); line = ch.lstrip()
        out.append(line)
    return [l for l in out if l.strip()] or [""]


def fit(text, size, maxw, bold=False):
    """한 줄에 안 들어가면 끝을 … 로 줄임."""
    text = str(text)
    if tw(text, size, bold) <= maxw:
        return text
    while text and tw(text + "…", size, bold) > maxw:
        text = text[:-1]
    return text + "…"


def lh(size):
    return int(size * 1.38)


class Card:
    def __init__(self, title, date, accent=ACC, sub="", foot="매수·매도 추천 아님 · 결정·책임 본인"):
        self.title, self.date, self.accent, self.sub, self.foot = title, date, accent, sub, foot
        self.blocks = []          # (height, draw_fn, keep_with_next)

    # ---------------------------------------------------------------- 블록
    def _add(self, h, fn, keep=False):
        self.blocks.append((h, fn, keep))

    def gap(self, h=18):
        self._add(h, lambda d, y: None)

    def sec(self, text, color=None):
        col = color or self.accent
        h = lh(SEC) + 14

        def fn(d, y):
            d.rectangle([PAD, y + 22, PAD + 18, y + 22 + 30], fill=col)
            d.text((PAD + 34, y + 6), fit(text, SEC, W - 2 * PAD - 34, True), font=font(SEC, True), fill=col)
        self._add(h, fn, keep=True)

    def row(self, left, right="", lc=TXT, rc=SUB, lbold=True, rbold=False, size=BODY,
            sub=None, sub_color=SUB, badge=None, line=True, shrink=True):
        """한 행: 왼쪽 글(굵게) · 오른쪽 값(오른쪽 정렬) · 아래 작은 줄(sub) · 오른쪽 배지(badge=(글, 색)).
        shrink=True 면 왼쪽 글이 길 때 글씨를 SMALL 까지 줄여서 다 보이게(그래도 길면 …)."""
        subs = wrap(sub, SMALL, W - 2 * PAD - 20) if sub else []
        h = lh(size) + 10 + len(subs) * lh(SMALL)

        def fn(d, y):
            rx = W - PAD
            if badge:
                bt, bc = badge
                bw = tw(bt, SMALL, True) + 36
                d.rounded_rectangle([rx - bw, y + 8, rx, y + 8 + lh(SMALL) + 6], radius=12, outline=bc, width=3)
                d.text((rx - bw + 18, y + 10), bt, font=font(SMALL, True), fill=bc)
                rx -= bw + 20
            rw = tw(right, size, rbold) if right else 0
            if right:
                d.text((rx - rw, y), right, font=font(size, rbold), fill=rc)
            room = rx - rw - (28 if right else 0) - PAD
            ls = size
            while shrink and ls > SMALL and tw(left, ls, lbold) > room:
                ls -= 2
            d.text((PAD, y + (size - ls) // 2), fit(left, ls, room, lbold), font=font(ls, lbold), fill=lc)
            yy = y + lh(size)
            for s in subs:
                d.text((PAD + 4, yy), s, font=font(SMALL), fill=sub_color); yy += lh(SMALL)
            if line:
                d.line([PAD, y + h - 4, W - PAD, y + h - 4], fill=LINE, width=2)
        self._add(h, fn)

    def stat(self, label, value, change="", color=TXT, note=""):
        """큰 숫자 칸: 왼쪽 위 이름(작게) · 큰 값 · 오른쪽 등락."""
        h = lh(SMALL) + lh(BIG) + 24

        def fn(d, y):
            d.rounded_rectangle([PAD, y, W - PAD, y + h - 12], radius=18, fill=PANEL)
            d.rectangle([PAD, y + 14, PAD + 10, y + h - 26], fill=color)
            d.text((PAD + 34, y + 10), label + (f"  ·  {note}" if note else ""), font=font(SMALL, True), fill=SUB)
            d.text((PAD + 34, y + 10 + lh(SMALL)), value, font=font(BIG, True), fill=WHITE)
            if change:
                cw = tw(change, BODY, True)
                d.text((W - PAD - 30 - cw, y + 14 + lh(SMALL) + (lh(BIG) - lh(BODY)) // 2), change,
                       font=font(BODY, True), fill=color)
        self._add(h, fn)

    def bar(self, label, pct, maxabs, up=GREEN, down=RED):
        """막대 행: 이름 · 막대 · 등락률."""
        h = lh(BODY) + 10

        def fn(d, y):
            col = up if pct >= 0 else down
            vt = f"{pct:+.2f}%"
            vw = tw(vt, BODY, True)
            d.text((W - PAD - vw, y), vt, font=font(BODY, True), fill=col)
            lw = 330
            d.text((PAD, y), fit(label, BODY, lw - 20, True), font=font(BODY, True), fill=TXT)
            bx0, bx1 = PAD + lw, W - PAD - vw - 30
            w = (bx1 - bx0) * min(abs(pct) / (maxabs or 1), 1)
            if w >= 2:
                d.rounded_rectangle([bx0, y + 18, bx0 + w, y + lh(BODY) - 12], radius=8,
                                    fill=(45, 110, 80) if pct >= 0 else (130, 52, 60))
            d.line([PAD, y + h - 4, W - PAD, y + h - 4], fill=LINE, width=2)
        self._add(h, fn)

    def stack(self, segs):
        """비율 막대 한 줄: segs = [(개수, 색, 이름), …] — 막대 위에 '이름 n' 글씨."""
        tot = sum(max(n, 0) for n, _, _ in segs) or 1
        h = lh(BODY) + 30

        def fn(d, y):
            x = PAD; bw = W - 2 * PAD
            for n, col, lab in segs:
                w = bw * max(n, 0) / tot
                if w <= 0:
                    continue
                d.rectangle([x, y, x + w, y + lh(BODY) + 10], fill=col)
                t = f"{lab} {n}"
                if tw(t, SMALL, True) + 20 < w:
                    d.text((x + 14, y + 14), t, font=font(SMALL, True), fill=(16, 18, 22))
                elif tw(str(n), SMALL, True) + 12 < w:
                    d.text((x + 8, y + 14), str(n), font=font(SMALL, True), fill=(16, 18, 22))
                x += w
        self._add(h, fn)

    def cols(self, cells, size=BODY, hl=None, line=True):
        """여러 칸 한 줄: cells = [(글, 색, x, 'l'|'r', 굵게), …] · hl=배경색(강조 행)."""
        h = lh(size) + 10

        def fn(d, y):
            if hl:
                d.rounded_rectangle([PAD - 10, y - 2, W - PAD + 10, y + h - 6], radius=10, fill=hl)
            for c in cells:
                t, col, x, al = c[:4]
                b = c[4] if len(c) > 4 else False
                xx = x - tw(t, size, b) if al == "r" else x
                d.text((xx, y), t, font=font(size, b), fill=col)
            if line:
                d.line([PAD, y + h - 4, W - PAD, y + h - 4], fill=LINE, width=2)
        self._add(h, fn)

    def para(self, text, color=TXT, size=BODY, bold=False, box=None):
        """여러 줄 글. box=색 이면 왼쪽 색띠 상자."""
        inset = 34 if box else 0
        lines = wrap(text, size, W - 2 * PAD - inset - (20 if box else 0), bold)
        h = len(lines) * lh(size) + (28 if box else 6)

        def fn(d, y):
            if box:
                d.rounded_rectangle([PAD, y, W - PAD, y + h - 8], radius=16, fill=PANEL)
                d.rectangle([PAD, y + 12, PAD + 10, y + h - 20], fill=box)
            yy = y + (10 if box else 0)
            for l in lines:
                d.text((PAD + inset, yy), l, font=font(size, bold), fill=color); yy += lh(size)
        self._add(h, fn)

    # ---------------------------------------------------------------- 쪽 나누기
    def _head_h(self):
        return 18 + lh(TITLE) + lh(SMALL) + 26

    def _foot_lines(self):
        return wrap(self.foot, SMALL, W - 2 * PAD) if self.foot else []

    def _paginate(self):
        avail = H_MAX - self._head_h() - len(self._foot_lines()) * lh(SMALL) - 40
        pages, cur, used = [], [], 0
        i, n = 0, len(self.blocks)
        while i < n:
            h, fn, keep = self.blocks[i]
            need = h
            if keep and i + 1 < n:                 # 제목은 다음 줄과 같이
                need += self.blocks[i + 1][0]
                j, grp = i + 1, h                  # 한 묶음(제목~다음 제목 전)이 한 쪽에 들어가면 안 쪼갬
                while j < n and not self.blocks[j][2]:
                    grp += self.blocks[j][0]; j += 1
                # 남은 자리가 넉넉하면(쪽의 35% 이상) 그냥 이어 쓰고, 좁으면 묶음째 다음 쪽으로
                if grp <= avail and (avail - used) < avail * 0.35:
                    need = grp
            if cur and used + need > avail:
                pages.append(cur); cur, used = [], 0
            if not cur and h == 0:
                i += 1; continue
            cur.append((h, fn)); used += h; i += 1
        if cur:
            pages.append(cur)
        return pages or [[]]

    def pages(self):
        groups = self._paginate()
        n = len(groups)
        foot = self._foot_lines()
        out = []
        for pi, g in enumerate(groups, 1):
            body_h = sum(h for h, _ in g)
            H = self._head_h() + body_h + len(foot) * lh(SMALL) + 40
            H = max(H_MIN, min(H_MAX, H))
            img = Image.new("RGB", (W, H), BG)
            d = ImageDraw.Draw(img)
            d.rectangle([0, 0, W, 12], fill=self.accent)
            y = 30
            pg = f"   {pi}/{n}" if n > 1 else ""
            d.text((PAD, y), fit(self.title, TITLE, W - 2 * PAD - tw(pg, SMALL, True) - 10, True),
                   font=font(TITLE, True), fill=WHITE)
            if pg:
                d.text((W - PAD - tw(pg, SMALL, True), y + 22), pg, font=font(SMALL, True), fill=self.accent)
            y += lh(TITLE)
            sub = f"기준일 {self.date}" + (f" · {self.sub}" if self.sub else "")
            d.text((PAD, y), fit(sub, SMALL, W - 2 * PAD), font=font(SMALL), fill=SUB)
            y += lh(SMALL) + 26
            for h, fn in g:
                fn(d, y); y += h
            fy = H - 24 - len(foot) * lh(SMALL)
            for l in foot:
                d.text((PAD, fy), l, font=font(SMALL), fill=DIM); fy += lh(SMALL)
            out.append(img)
        return out

    # ---------------------------------------------------------------- 저장
    def save(self, stem, here, dstamp, folder_date=None):
        """카드뉴스/<날짜>/<stem>_p1.png … 로 저장(예전 쪽·옛 단일 파일은 먼저 지움).
        메인 폴더의 <stem>.png 에는 모든 쪽을 세로로 이은 한 장(예전 이름을 쓰는 곳 호환)."""
        imgs = self.pages()
        dd = os.path.join(here, "카드뉴스", folder_date or dstamp)
        os.makedirs(dd, exist_ok=True)
        for old in glob.glob(os.path.join(dd, f"{stem}_p*.png")) + [os.path.join(dd, f"{stem}.png")]:
            try:
                os.remove(old)
            except OSError:
                pass
        paths = []
        for i, im in enumerate(imgs, 1):
            p = os.path.join(dd, f"{stem}_p{i}.png"); im.save(p, optimize=True); paths.append(p)
        tall = Image.new("RGB", (W, sum(im.height for im in imgs) + 8 * (len(imgs) - 1)), LINE)
        yy = 0
        for im in imgs:
            tall.paste(im, (0, yy)); yy += im.height + 8
        main = os.path.join(here, f"{stem}.png"); tall.save(main, optimize=True)
        od = os.path.expanduser(r"~\OneDrive\문서\Claude\Projects\진우퀀트")
        if os.path.isdir(od):
            try:
                tall.save(os.path.join(od, f"{stem}.png"))
            except Exception:
                pass
        return paths


def src_label(sources):
    """제목 아래 한 줄용 짧은 출처 표기."""
    s = str(sources or "")
    return "KRX 확정치" if "KRX" in s else ("공개 자료" if not s else s.split("·")[0].strip()[:16])


def up_down(v, up=GREEN, down=RED, flat=SUB):
    if v is None:
        return flat
    return up if v > 0 else (down if v < 0 else flat)


def arrow_pct(v):
    if v is None:
        return "N/A"
    return ("▲ " if v > 0 else ("▼ " if v < 0 else "· ")) + f"{v:+.2f}%"


if __name__ == "__main__":   # 셀프테스트: 쪽 크기·비율·나누기
    c = Card("셀프테스트 카드", datetime.date.today().isoformat())
    c.sec("지수"); c.stat("코스피", "4,105.20", arrow_pct(1.23), GREEN)
    for i in range(30):
        c.row(f"종목{i}", f"+{i}.00%", rc=GREEN, sub="보조 설명 줄" if i % 3 == 0 else None)
    ps = c.pages()
    ok = all(W == p.width and H_MIN <= p.height <= H_MAX for p in ps) and len(ps) >= 2
    print(f"{'✅' if ok else '❌'} jq_mcard 셀프테스트 · {len(ps)}쪽 · " + ", ".join(f"{p.width}x{p.height}" for p in ps))
    raise SystemExit(0 if ok else 1)
