# -*- coding: utf-8 -*-
"""jq_close_card.py — 국내증시 마감 브리핑 카드뉴스.
데이터: 같은 폴더 jq_close_data.json (jq_close_fetch.py가 KRX 확정치로 채움). 실데이터만·가짜 금지.
산출: 카드뉴스/YYYY-MM-DD/마감브리핑_카톡_p1.png … (카톡 말풍선용 1080×최대1440, 큰 글씨)
      + 메인 폴더 마감브리핑_카톡.png (쪽을 이은 한 장, 예전 이름 호환)
2026-11-27: 카톡 말풍선에서 글씨가 안 보이던 문제 → jq_mcard(큰 글씨·3:4 쪽 나누기)로 다시 그림.
"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import jq_mcard as M


def build(D):
    c = M.Card("국내증시 마감 브리핑", D['date'], accent=M.ACC, sub=M.src_label(D.get('sources')) + " · 장 마감",
               foot="상승 초록 · 하락 빨강 · 추천 아님 · 결정·책임 본인")
    c.sec("지수 마감")
    for nm, k in (("코스피", "kospi"), ("코스닥", "kosdaq")):
        v, ch = D.get(k), D.get(k + "_chg")
        c.stat(nm, f"{v:,.2f}" if v is not None else "N/A", M.arrow_pct(ch), M.up_down(ch))
    inv = {k: v for k, v in (D.get('inv') or {}).items() if v is not None}
    if inv:
        c.sec("투자자별 수급 (코스피 · 억원)")
        for who in ("외국인", "기관", "개인"):
            if who in inv:
                v = inv[who]
                c.row(who, f"{v:+,}", rc=M.up_down(v), rbold=True)
    if D.get('driver'):
        c.sec("오늘의 동인")
        c.para(D['driver'], box=M.ACC)
    if D.get('insight'):
        c.sec("참고 (코스닥 수급 등)", color=M.GREEN)
        c.para(D['insight'], color=(190, 240, 210), box=M.GREEN)
    return c


def main():
    p = os.path.join(HERE, "jq_close_data.json")
    if not os.path.exists(p):
        print("[오류] jq_close_data.json 없음"); return 2
    D = json.load(open(p, encoding="utf-8"))
    paths = build(D).save("마감브리핑_카톡", HERE, D['date'])
    print(f"[산출] 마감브리핑_카톡 {len(paths)}쪽 ·", D['date'])
    return 0


if __name__ == "__main__": sys.exit(main())
