# -*- coding: utf-8 -*-
"""jq_watch_card.py — 관심 워치리스트 카드뉴스.
데이터: 같은 폴더 jq_watchlist.json (스케줄이 매일 유지·갱신). 실데이터만·가짜 금지.
성격: '추천' 아님. 내가 며칠간 지켜보는 관심종목 + 진입/손절 규율 추적.
산출: 카드뉴스/YYYY-MM-DD/관심워치리스트_카톡_p1.png … (카톡 말풍선용 1080×최대1440, 큰 글씨)
      + 메인 폴더 관심워치리스트_카톡.png (쪽을 이은 한 장, 예전 이름 호환)
2026-11-27: 카톡 말풍선에서 글씨가 안 보이던 문제 → jq_mcard(큰 글씨·3:4 쪽 나누기)로 다시 그림.
            종목 순서·내용은 그대로(목록 순서 = 진우가 관리하는 순서), 상태는 오른쪽 배지.
2026-11-28: 진우 '워치리스트에 실제 가격' → 현재가·지지선(20/60일선)·손절선(최근 20거래일 저가 최저, 오늘 제외)과
            지금가에서 그 가격까지 거리(%)를 숫자로. 값은 jq_close_fetch가 KRX 일봉으로 계산해 lv에 넣은 것만 쓴다.
            lv가 없으면(이름 불일치·자료 부족) 예전 글자 표기 그대로.
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


def _gap(level, close):
    return f"{(level / close - 1) * 100:+.1f}%"


def _ma(name, level, close):
    """지지선 한 칸. 지금가가 선 아래면 '아래'를 붙여 한눈에 보이게(괄호 + = 그만큼 올라야 회복)."""
    return f"{name} {level:,}" + (" 아래" if close < level else "") + f"({_gap(level, close)})"


def level_text(it):
    """lv → (여러 줄 글, 손절선 아래인지). 한 줄 = 한 가지:
    현재가 · 20일선 / (지지가 20/60이면) 60일선 / 손절선 · 테마. lv 없으면 (None, False)."""
    lv = it.get('lv') or {}
    c = lv.get('close')
    if not c:
        return None, False
    sup = it.get('support', '')
    lines = [f"현재 {c:,}"]
    if "20" in sup or "60" not in sup:
        lines[0] += " · " + _ma("20일선", lv['ma20'], c)
    if "60" in sup:
        lines.append(_ma("60일선", lv['ma60'], c))
    broke = c < lv['low20']
    last = f"손절선 {lv['low20']:,}" + (" 아래로 내려옴" if broke else f"({_gap(lv['low20'], c)})")
    if it.get('theme'):
        last += f" · {it['theme']}"
    lines.append(last)
    return "\n".join(lines), broke


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
        txt, broke = level_text(it)
        if txt is None:
            parts = [p for p in [th, (f"지지 {sup}" if sup else ""), (f"손절 {stp}" if stp else "")] if p]
            if chg is None and note:
                parts.insert(0, note)
            txt = " · ".join(parts) or None
        c.row(nm, right, rc=M.up_down(chg), rbold=True, badge=(stt, _status_color(stt)),
              sub=txt, sub_color=(M.RED if broke else M.SUB))
    c.sec("읽는 법 · 규율", color=M.YEL)
    c.para("20·60일선 = 종가 평균 (지지선)\n손절선 = 최근 20거래일 최저가 (오늘 제외)\n"
           "괄호 = 지금가 → 그 가격 거리\n  − 그만큼 내리면 닿음 · + 그만큼 올라야 회복\n"
           "아래 = 지금가가 선 밑 · 빨간 줄 = 손절선 이탈", color=(255, 230, 160), size=M.SMALL, box=M.YEL)
    c.para("추세 유효 종목만 유지 · 이탈 시 제외 후보 · 진입은 지지 재확인 후 · 손절가 먼저 정하기"
           " · 목록·상태는 수동 관리", color=(255, 230, 160))
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
