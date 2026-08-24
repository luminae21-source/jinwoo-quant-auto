# -*- coding: utf-8 -*-
"""jq_cards_merge.py — 카드뉴스 6장을 세로로 이어붙인 '통합 1장' 생성 (진우퀀트)
================================================================================
입력 : 카드뉴스\\YYYY-MM-DD\\ 폴더의 카드들(없으면 루트). 정해진 순서로 스택.
산출 : 카드뉴스_통합_YYYY-MM-DD.png (루트 + 해당 날짜 폴더)
정렬 : 폭은 최대폭에 맞춰 가운데 정렬, 카드 사이 여백 + 얇은 구분선.
사용 : python jq_cards_merge.py [YYYY-MM-DD]   ·   --selftest
발송 : jq_kakao_send.py --merged (이 파일을 import해서 만든 뒤 1장 전송)
"""
import os, sys, glob, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    import jq_kakao as K
    K.setup_console()
except Exception:
    pass

HERE = os.path.dirname(os.path.abspath(__file__))
BG = (15, 17, 21)
DIV = (46, 50, 60)      # 구분선
ACC = (255, 122, 69)    # 상단 액센트
GAP = 26                # 카드 사이 여백(px)
SIDE = 0                # 좌우 여백(px) — 0=카드 폭 그대로

# 세로 스택 순서(파일명 키워드)
ORDER = [
    "시장브리핑_카톡",
    "美종목_한국영향",
    "연준_Fed_동향",
    "마감브리핑_카톡",
    "마감종목_카톡",
    "관심워치리스트_카톡",
]


def latest_day_dir():
    dirs = sorted(glob.glob(os.path.join(HERE, "카드뉴스", "20*-*-*")))
    return dirs[-1] if dirs else None


def _find(key, base, dstamp):
    """key 카드 파일 1개 경로. 날짜폴더 우선, 없으면 루트(날짜접미사 포함)."""
    for folder in (base, HERE):
        if not folder:
            continue
        cand = [p for p in glob.glob(os.path.join(folder, "*.png"))
                if key in os.path.basename(p)]
        if cand:
            # 날짜 접미사 있는 최신 우선
            cand.sort(key=lambda p: (dstamp in os.path.basename(p), os.path.getmtime(p)))
            return cand[-1]
    return None


def collect(dstamp=None):
    base = None
    if dstamp:
        d = os.path.join(HERE, "카드뉴스", dstamp)
        base = d if os.path.isdir(d) else None
    if base is None:
        base = latest_day_dir()
        if base:
            dstamp = os.path.basename(base)
    if not dstamp:
        dstamp = datetime.date.today().isoformat()
    found = []
    for key in ORDER:
        p = _find(key, base, dstamp)
        if p:
            found.append((key, p))
    return dstamp, base, found


def merge(dstamp=None, out_name=None):
    from PIL import Image, ImageDraw
    dstamp, base, found = collect(dstamp)
    if not found:
        print(f"[merge] 합칠 카드가 없습니다 (날짜={dstamp}, 폴더={base})")
        return None, dstamp, 0
    imgs = []
    for key, p in found:
        try:
            imgs.append(Image.open(p).convert("RGB"))
        except Exception as e:
            print(f"  [열기 실패] {os.path.basename(p)}: {e}")
    if not imgs:
        return None, dstamp, 0
    maxw = max(im.width for im in imgs)
    W = maxw + 2 * SIDE
    top = 8  # 상단 액센트바 높이
    H = top + sum(im.height for im in imgs) + GAP * (len(imgs) - 1)
    canvas = Image.new("RGB", (W, H), BG)
    d = ImageDraw.Draw(canvas)
    d.rectangle([0, 0, W, top - 1], fill=ACC)  # 상단 액센트
    y = top
    for i, im in enumerate(imgs):
        x = (W - im.width) // 2
        canvas.paste(im, (x, y))
        y += im.height
        if i < len(imgs) - 1:
            # 카드 사이: 여백 중앙에 얇은 구분선
            d.rectangle([0, y, W, y + GAP], fill=BG)
            ly = y + GAP // 2
            d.line([SIDE + 20, ly, W - SIDE - 20, ly], fill=DIV, width=2)
            y += GAP
    out_name = out_name or f"카드뉴스_통합_{dstamp}.png"
    out_root = os.path.join(HERE, out_name)
    canvas.save(out_root)
    outs = [out_root]
    if base and os.path.isdir(base):
        try:
            import shutil
            p2 = os.path.join(base, out_name)
            shutil.copy(out_root, p2)
            outs.append(p2)
        except Exception:
            pass
    print(f"[merge] {len(imgs)}장 → {out_name}  ({W}x{H}px)")
    for key, p in found:
        print(f"   + {os.path.basename(p)}")
    print(f"[저장] {out_root}")
    return out_root, dstamp, len(imgs)


def _selftest():
    import tempfile, shutil
    from PIL import Image
    ok = 0
    def chk(n, c):
        nonlocal ok; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    tmp = tempfile.mkdtemp()
    d = os.path.join(tmp, "카드뉴스", "2026-07-22")
    os.makedirs(d)
    sizes = {"시장브리핑_카톡": (820, 300), "美종목_한국영향": (860, 200),
             "연준_Fed_동향": (820, 250), "마감브리핑_카톡": (800, 180),
             "마감종목_카톡": (800, 220), "관심워치리스트_카톡": (800, 160), "잡음": (400, 100)}
    for k, (w, h) in sizes.items():
        Image.new("RGB", (w, h), (20, 20, 20)).save(os.path.join(d, k + (".png" if k != "美종목_한국영향" else "_카드.png")))
    saved = globals()["HERE"]; globals()["HERE"] = tmp
    try:
        dstamp, base, found = collect("2026-07-22")
        keys = [k for k, _ in found]
        chk("6장 수집(잡음 제외)", len(found) == 6 and "잡음" not in keys)
        chk("순서: 시황 먼저·워치 마지막", keys[0] == "시장브리핑_카톡" and keys[-1] == "관심워치리스트_카톡")
        out, ds, n = merge("2026-07-22")
        chk("통합 파일 생성", out and os.path.exists(out))
        im = Image.open(out)
        chk("폭=최대폭(860)", im.width == 860)
        exp_h = 8 + (300 + 200 + 250 + 180 + 220 + 160) + 26 * 5
        chk("높이=합+여백", im.height == exp_h)
        chk("파일명 규칙", os.path.basename(out) == "카드뉴스_통합_2026-07-22.png")
    finally:
        globals()["HERE"] = saved
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"✅ jq_cards_merge 셀프테스트 ({ok}/6)")
    return ok == 6


def main(argv):
    if "--selftest" in argv:
        return 0 if _selftest() else 1
    dstamp = next((a for a in argv if not a.startswith("--")), None)
    out, ds, n = merge(dstamp)
    return 0 if out else 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
