# -*- coding: utf-8 -*-
"""jq_watch_card.py — 관심 워치리스트 카드뉴스.
데이터: 같은 폴더 jq_watchlist.json (스케줄이 매일 유지·갱신). 실데이터만·가짜 금지.
성격: '추천' 아님. 내가 며칠간 지켜보는 관심종목 + 진입/손절 규율 추적.
산출: 카드뉴스/YYYY-MM-DD/관심워치리스트_카톡_p1.png … (카톡 말풍선용 1080×최대1440, 큰 글씨)
      + 메인 폴더 관심워치리스트_카톡.png (쪽을 이은 한 장, 예전 이름 호환)
2026-11-27: 카톡 말풍선에서 글씨가 안 보이던 문제 → jq_mcard(큰 글씨·3:4 쪽 나누기)로 다시 그림.
            종목 순서·내용은 그대로(목록 순서 = 진우가 관리하는 순서), 상태는 오른쪽 배지.
"""
import os, sys, json, re
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import jq_mcard as M


def _status_color(s):
    if any(k in s for k in ["이탈", "제외", "손절", "약화"]): return M.RED
    if any(k in s for k in ["근접", "관찰", "주의"]): return M.YEL
    return M.GREEN


def build(D):
    items = D.get('items', [])
    c = M.Card("관심 워치리스트", D['updated'], accent=M.BLUE, sub=M.src_label(D.get('sources')) + " · 지켜보는 종목",
               foot="추천 아님 · 진입 시 손절가 먼저 · 결정·책임 본인")
    for it in items:
        nm = it.get('name', ''); th = it.get('theme', ''); stt = it.get('status', '관찰')
        note = it.get('note', ''); sup = it.get('support', ''); stp = it.get('stop', '')
        m = re.search(r"([-+]\d+(?:\.\d+)?)%", note)
        chg = float(m.group(1)) if m else None
        right = f"{chg:+.2f}%" if chg is not None else ""
        parts = [p for p in [th, (f"지지 {sup}" if sup else ""), (f"손절 {stp}" if stp else "")] if p]
        if chg is None and note:
            parts.insert(0, note)
        c.row(nm, right, rc=M.up_down(chg), rbold=True, badge=(stt, _status_color(stt)),
              sub=" · ".join(parts) or None)
    c.sec("규율", color=M.YEL)
    c.para("추세 유효 종목만 유지 · 이탈 시 제외 후보 · 진입은 지지 재확인 후 · 손절가 먼저 정하기"
           " · 목록·상태는 수동 관리", color=(255, 230, 160), box=M.YEL)
    return c


def main():
    p = os.path.join(HERE, "jq_watchlist.json")
    if not os.path.exists(p):
        print("[오류] jq_watchlist.json 없음"); return 2
    D = json.load(open(p, encoding="utf-8"))
    paths = build(D).save("관심워치리스트_카톡", HERE, D['updated'])
    print(f"[산출] 관심워치리스트_카톡 {len(paths)}쪽 ·", D['updated'])
    return 0


if __name__ == "__main__": sys.exit(main())
