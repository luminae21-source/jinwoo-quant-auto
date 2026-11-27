# -*- coding: utf-8 -*-
"""jq_close_stocks.py — 마감 특징주·섹터 카드뉴스.
데이터: 같은 폴더 jq_close_stocks.json (jq_close_fetch.py가 KRX 확정치로 채움). 실데이터만·가짜 금지.
산출: 카드뉴스/YYYY-MM-DD/마감종목_카톡_p1.png … (카톡 말풍선용 1080×최대1440, 큰 글씨)
      + 메인 폴더 마감종목_카톡.png (쪽을 이은 한 장, 예전 이름 호환)
2026-11-27: 카톡 말풍선에서 글씨가 안 보이던 문제 → jq_mcard(큰 글씨·3:4 쪽 나누기)로 다시 그림.
"""
import os, sys, json
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
import jq_mcard as M


def _pct(s):
    try:
        return float(str(s).replace("%", "").replace("+", ""))
    except ValueError:
        return None


def build(D):
    vt = D.get('value_top', []); st = D.get('sector_top', []); gn = D.get('gainers', []); tw = D.get('trend_watch', [])
    c = M.Card("마감 특징주·섹터", D['date'], accent=M.ACC, sub=M.src_label(D.get('sources')) + " · 장 마감",
               foot="급등일 추격은 리스크 · 추천 아님 · 결정·책임 본인")
    if D.get('driver'):
        c.sec("오늘의 동인")
        c.para(D['driver'], box=M.ACC)
    if D.get('breadth'):
        c.sec("시장 폭 (상승 / 하락 종목 수)")
        c.para(D['breadth'], color=M.SUB)
    if gn:
        c.sec("급등 상위 (오늘 등락률)", color=M.GREEN)
        for item in gn:
            nm = item[0]; pct = item[1] if len(item) > 1 else None; tag = item[2] if len(item) > 2 else ""
            c.row(nm, f"▲ {pct:+.2f}%" if pct is not None else "", rc=M.GREEN, rbold=True,
                  badge=(tag, M.ACC) if tag else None)
    if vt:
        c.sec("거래대금 상위 (돈이 몰린 종목)", color=M.BLUE)
        for i, (nm, val) in enumerate(vt, 1):
            c.row(f"{i}. {nm}", val, rc=M.BLUE, rbold=True)
    if st:
        c.sec("주도 섹터 (업종 등락률)", color=M.GREEN)
        mx = max((abs(p) for _, p in st), default=1) or 1
        for nm, p in st:
            c.bar(nm, p, mx)
    if tw:
        c.sec("추세 관심종목 (참고 · 추천 아님)", color=M.BLUE)
        c.para("조정에도 상승추세가 살아 있는 주도 섹터 대표주 · 지지 확인 시 다시 볼 후보", color=M.SUB, size=M.SMALL)
        for item in tw:
            nm = item[0]; th = item[1] if len(item) > 1 else ""; memo = item[2] if len(item) > 2 else ""
            c.row(nm, memo, rc=M.up_down(_pct(memo)), rbold=True, sub=th or None)
    if D.get('note'):
        c.sec("추세매매 관점 (참고 · 추천 아님)", color=M.GREEN)
        c.para(D['note'], color=(190, 240, 210), box=M.GREEN)
    return c


def main():
    p = os.path.join(HERE, "jq_close_stocks.json")
    if not os.path.exists(p):
        print("[오류] jq_close_stocks.json 없음"); return 2
    D = json.load(open(p, encoding="utf-8"))
    paths = build(D).save("마감종목_카톡", HERE, D['date'])
    print(f"[산출] 마감종목_카톡 {len(paths)}쪽 ·", D['date'])
    return 0


if __name__ == "__main__": sys.exit(main())
