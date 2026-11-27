# -*- coding: utf-8 -*-
"""jq_kakao_send.py — 카드뉴스 PNG를 카카오톡 '나에게' 자동 발송 (진우퀀트)
================================================================================
파이프라인 마지막 단계. jq_cards.py / jq_close_card.py 가 카드를 만든 '직후' 호출.
동작 : 최신 카드뉴스\\YYYY-MM-DD\\ 폴더(없으면 루트)에서, 최근 생성된 PNG만 골라
       카카오톡 '나와의 채팅방'으로 순서대로 발송. (아침 시황 run / 마감 run 이 각자
       방금 만든 카드만 보내도록 '수정시간' 기준으로 신선한 것만 전송.)
옵션 :
  (인자 없음)         최근 FRESH_MIN분 내 수정된 카드만 발송(파이프라인 기본)
  --all               해당 폴더의 알려진 카드 전부 발송(수동 테스트)
  파일명 [파일명...]   지정한 파일만 발송(경로/파일명 모두 가능)
  --dry-run           실제 발송 없이 '무엇을 보낼지'만 출력
  --selftest          카드 탐색/정렬 로직 자체검증(네트워크 없음)
설정 : jq_kakao_config.txt 의 FRESH_MIN(기본 120), 인증정보는 jq_kakao.py 참조.
실행 : jq_kakao_send.bat  (배치가 SSL 환경변수 세팅)
"""
import os, re, sys, glob, time, datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jq_kakao as K

K.setup_console()  # 콘솔 한글 안 깨지게(콘솔 코드페이지 자동 감지). 표시 전용.

HERE = os.path.dirname(os.path.abspath(__file__))

# (파일명에 포함된 키워드, 카드 제목, 발송 순서)
KNOWN_CARDS = [
    ("시장브리핑_카톡", "📊 시황 브리핑"),
    ("美종목_한국영향", "🇺🇸 美 → 한국 영향"),
    ("연준_Fed_동향", "🏛️ 연준(Fed) 동향"),
    ("선물옵션_카드", "🎯 선물·옵션"),
    ("주봉분석_카드", "📈 주봉 분석"),
    ("주봉_매매가이드", "🧭 주봉 매매가이드"),
    ("마감브리핑_카톡", "🔔 마감 브리핑"),
    ("마감종목_카톡", "🔔 마감 특징주"),
    ("종목발굴_카톡", "🔎 종목 발굴"),
    ("관심워치리스트_카톡", "⭐ 관심 워치리스트"),
    ("진우사냥터_카드", "🏹 사냥터"),
    ("진우_실전카드", "💼 실전 카드"),
]


# 말풍선 제목 아래 '이 카드가 뭔지' 한 줄 (2026-11-27 진우 '설명을 만들어 주고 · 심플하게')
CARD_DESC = {
    "시장브리핑_카톡": "국내·미국 지수, 금리·환율, 만기 일정",
    "美종목_한국영향": "밤사이 美 종목 → 한국 어느 업종에 닿는지",
    "연준_Fed_동향": "기준금리·FOMC·금리곡선 — 수급의 큰 변수",
    "선물옵션_카드": "선물·야간선물·옵션 체인 (고위험)",
    "주봉분석_카드": "종목별 20주선 위/아래와 추세",
    "주봉_매매가이드": "추세유지·눌림·회피 분류와 매도 신호등",
    "마감브리핑_카톡": "오늘 지수 마감과 외국인·기관·개인 수급",
    "마감종목_카톡": "급등·거래대금 상위, 강한 업종, 추세 관심종목",
    "관심워치리스트_카톡": "지켜보는 종목 상태 (추세 유효·지지 근접·이탈)",
    "종목발굴_카톡": "오늘 조건에 걸린 발굴 후보",
    "진우사냥터_카드": "사냥터 후보 요약",
    "진우_실전카드": "실전 보유·주문 요약",
}


def desc_for(fn, day):
    """'급등·거래대금 상위… · 11/27 · 추천 아님' — 설명이 없는 카드는 예전 문구."""
    d = CARD_DESC.get(card_key(fn))
    md = f"{int(day[5:7])}/{int(day[8:10])}" if len(day) >= 10 and day[4] == "-" else day
    return f"{d} · {md} · 추천 아님" if d else f"기준일 {day} · 진우퀀트 · 매수매도 추천 아님"


def latest_card_dir():
    dirs = sorted(glob.glob(os.path.join(HERE, "카드뉴스", "20*-*-*")))
    return dirs[-1] if dirs else None


def title_for(fn):
    stem = os.path.splitext(os.path.basename(fn))[0]
    for key, title in KNOWN_CARDS:
        if key in stem:
            return title
    return stem


def page_of(fn):
    """'마감종목_카톡_p2.png' → 2 (쪽 번호, 2026-11-27 큰 글씨 카드). 쪽 표시가 없으면 0."""
    m = re.search(r"_p(\d+)$", os.path.splitext(os.path.basename(fn))[0])
    return int(m.group(1)) if m else 0


def card_key(fn):
    stem = os.path.basename(fn)
    return next((key for key, _ in KNOWN_CARDS if key in stem), stem)


def group_cards(cards):
    """[(카드키, [쪽 파일…]), …] — 보낼 순서 그대로, 같은 카드끼리 묶음 (2026-11-27 진우 '같은 그룹끼리 묶어서')."""
    groups = []
    for p in cards:
        k = card_key(p)
        if groups and groups[-1][0] == k:
            groups[-1][1].append(p)
        else:
            groups.append((k, [p]))
    return groups


def stitch(paths, out):
    """쪽 이미지를 세로로 이어 한 장으로 (버튼을 누르면 이 한 장을 위아래로 넘겨 봄)."""
    from PIL import Image
    ims = [Image.open(p).convert("RGB") for p in paths]
    W = max(i.width for i in ims)
    canvas = Image.new("RGB", (W, sum(i.height for i in ims) + 12 * (len(ims) - 1)), (52, 57, 68))
    y = 0
    for im in ims:
        canvas.paste(im, (0, y)); y += im.height + 12
    canvas.save(out, optimize=True)
    return out


def _order_index(fn):
    stem = os.path.basename(fn)
    for i, (key, _) in enumerate(KNOWN_CARDS):
        if key in stem:
            return i
    return len(KNOWN_CARDS)


def discover(fresh_min=120, send_all=False):
    """발송 대상 PNG 목록을 순서대로 반환."""
    base = latest_card_dir() or HERE
    pngs = glob.glob(os.path.join(base, "*.png"))
    # 알려진 카드만
    cards = [p for p in pngs if any(key in os.path.basename(p) for key, _ in KNOWN_CARDS)]
    if not send_all:
        cutoff = time.time() - fresh_min * 60
        cards = [p for p in cards if os.path.getmtime(p) >= cutoff]
    # 같은 카드가 날짜접미사/무접미사로 중복되면 최신 1개만 (여러 쪽 카드는 쪽마다 따로)
    # 한 카드에 쪽 파일(_p1…)이 있으면 같은 카드의 옛 한 장짜리는 보내지 않음
    paged = {card_key(p) for p in cards if page_of(p)}
    picked = {}
    for p in cards:
        keymatch = card_key(p)
        if keymatch in paged and not page_of(p):
            continue
        k = (keymatch, page_of(p))
        if k not in picked or os.path.getmtime(p) > os.path.getmtime(picked[k]):
            picked[k] = p
    out = sorted(picked.values(), key=lambda p: (_order_index(p), page_of(p), p))
    return base, out


def run(argv):
    dry = "--dry-run" in argv
    send_all = "--all" in argv
    merged = "--merged" in argv
    explicit = [a for a in argv if not a.startswith("--")]
    cfg = K.load_config()
    fresh_min = int(cfg.get("FRESH_MIN", "120") or "120")
    today = datetime.date.today().isoformat()

    merged_title = None
    if merged:
        # 6장을 세로 통합 1장으로 만든 뒤, 그 1장만 전송
        import jq_cards_merge as MG
        out, dstamp, n = MG.merge()
        if not out:
            print("❌ 통합 이미지 생성 실패 (카드뉴스 폴더 확인).")
            return 2
        cards = [out]
        base = os.path.dirname(out)
        merged_title = f"🗞️ 통합 카드뉴스 ({n}장)"
        today = dstamp
    elif explicit:
        cards = []
        for a in explicit:
            p = a if os.path.isabs(a) else os.path.join(HERE, a)
            if os.path.exists(p):
                cards.append(p)
            else:
                print(f"  [없음] {a}")
        base = HERE
    else:
        base, cards = discover(fresh_min, send_all)

    # 설명 날짜는 '카드가 실제로 만들어진 날짜(카드뉴스\\YYYY-MM-DD 폴더)'를 우선 사용.
    # (오늘 발송해도 카드가 지난 영업일자면 그 날짜로 표기 — 내용/날짜 불일치 방지)
    if not merged:
        import re as _re
        _m = _re.search(r"(20\d{2}-\d{2}-\d{2})", base or "")
        if _m:
            today = _m.group(1)

    print(f"[jq_kakao_send] 폴더={base}")
    if not cards:
        print(f"  발송할 카드 없음 (최근 {fresh_min}분 내 생성된 카드 없음). "
              f"수동 전체발송은 --all, 특정일 테스트는 파일명 인자 사용.")
        return 0
    print(f"  대상 {len(cards)}장:")
    for p in cards:
        print(f"   - {os.path.basename(p)}  ->  {merged_title or title_for(p)}")
    if dry:
        print("  (--dry-run: 실제 발송 안 함)")
        return 0

    K.ensure_ca()
    try:
        token = K.get_access_token(cfg)
    except Exception as e:
        print(f"❌ 액세스 토큰 발급 실패: {e}")
        print("   → jq_kakao_auth.bat 로 최초 인증을 먼저 완료하세요.")
        return 5

    sent = 0
    if merged_title or "--each" in argv:     # 쪽마다 따로 보내기(예전 방식)
        npages = {}
        for p in cards:
            npages[card_key(p)] = npages.get(card_key(p), 0) + 1
        for p in cards:
            title = merged_title or title_for(p)
            if not merged_title and page_of(p) and npages.get(card_key(p), 1) > 1:
                title += f" ({page_of(p)}/{npages[card_key(p)]})"
            desc = desc_for(p, today) if not merged_title else f"기준일 {today} · 진우퀀트 · 매수매도 추천 아님"
            ok, how = K.send_image(token, p, title, desc, cfg)
            print(f"   [{'OK' if ok else 'FAIL'} · {how}] {os.path.basename(p)}")
            sent += 1 if ok else 0
            time.sleep(0.5)  # 레이트리밋 여유
        print(f"[jq_kakao_send] 완료 {sent}/{len(cards)} 장 전송")
        return 0 if sent == len(cards) else 1
    # 기본: 카드 1종 = 말풍선 1개 (말풍선 = 1쪽 · 버튼 '전체 N쪽 보기' = 모든 쪽을 이은 한 장)
    import tempfile
    groups = group_cards(cards)
    for key, pages in groups:
        n = len(pages)
        title = title_for(pages[0]) + (f" · {n}쪽" if n > 1 else "")
        desc = desc_for(pages[0], today)
        full = None
        if n > 1:
            fd, full = tempfile.mkstemp(suffix=".png"); os.close(fd)
            stitch(pages, full)
        ok, how = K.send_image(token, pages[0], title, desc, cfg, full_path=full,
                               button_title=(f"전체 {n}쪽 보기" if n > 1 else None))
        print(f"   [{'OK' if ok else 'FAIL'} · {how}] {key} {n}쪽")
        sent += 1 if ok else 0
        if full:
            try: os.remove(full)
            except OSError: pass
        time.sleep(0.5)  # 레이트리밋 여유
    print(f"[jq_kakao_send] 완료 {sent}/{len(groups)} 묶음 전송 (카드 {len(cards)}쪽)")
    return 0 if sent == len(groups) else 1


# ------------------------------------------------------------------ 셀프테스트
def _selftest():
    import tempfile, shutil
    ok = 0
    def chk(n, c):
        nonlocal ok; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    chk("제목 매핑 시황", title_for("시장브리핑_카톡.png") == "📊 시황 브리핑")
    chk("제목 매핑 마감종목", title_for("마감종목_카톡.png") == "🔔 마감 특징주")
    chk("제목 매핑 주봉(날짜접미사)", title_for("주봉분석_카드_2026-07-21.png") == "📈 주봉 분석")
    chk("미지 카드 stem 반환", title_for("무언가_이상한.png") == "무언가_이상한")
    chk("정렬 인덱스 시황<마감", _order_index("시장브리핑_카톡.png") < _order_index("마감브리핑_카톡.png"))
    # 임시 폴더로 discover 로직 검증
    tmp = tempfile.mkdtemp()
    d = os.path.join(tmp, "카드뉴스", "2026-07-21")
    os.makedirs(d)
    for fn in ["시장브리핑_카톡.png", "마감브리핑_카톡.png", "주봉분석_카드_2026-07-21.png", "주봉분석_카드.png", "잡음.png",
               "마감종목_카톡_p2.png", "마감종목_카톡_p1.png", "마감종목_카톡.png"]:
        open(os.path.join(d, fn), "wb").write(b"\x89PNG\r\n")
    saved = globals()["HERE"]
    globals()["HERE"] = tmp
    try:
        base, cards = discover(fresh_min=999999, send_all=True)
        names = [os.path.basename(c) for c in cards]
        chk("알려진 카드만 선별(잡음 제외)", "잡음.png" not in names)
        chk("주봉 중복 1개만", sum(1 for n in names if n.startswith("주봉분석")) == 1)
        chk("순서: 시황 먼저", names and names[0] == "시장브리핑_카톡.png")
        mj = [n for n in names if n.startswith("마감종목")]
        chk("여러 쪽: 쪽마다 따로 · 1→2 순서 · 옛 한 장 제외", mj == ["마감종목_카톡_p1.png", "마감종목_카톡_p2.png"])
        chk("쪽 번호 읽기", page_of("마감종목_카톡_p12.png") == 12 and page_of("마감브리핑_카톡.png") == 0)
        gs = group_cards(cards)
        chk("같은 카드끼리 묶음(마감종목 2쪽 = 1묶음)", any(k == "마감종목_카톡" and len(v) == 2 for k, v in gs) and len(gs) == len({k for k, _ in gs}))
        chk("설명 한 줄", desc_for("마감종목_카톡_p1.png", "2026-11-27").startswith("급등·거래대금") and "11/27" in desc_for("마감종목_카톡_p1.png", "2026-11-27"))
        _, none_fresh = discover(fresh_min=0, send_all=False)
        chk("신선도 필터(0분→없음)", len(none_fresh) == 0)
    finally:
        globals()["HERE"] = saved
        shutil.rmtree(tmp, ignore_errors=True)
    print(f"✅ jq_kakao_send 셀프테스트 ({ok}/13)")
    return ok == 13


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        sys.exit(0 if _selftest() else 1)
    sys.exit(run(sys.argv[1:]))
