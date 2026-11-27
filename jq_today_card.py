# -*- coding: utf-8 -*-
"""jq_today_card.py — '오늘의 결론' 1장 (아침 카톡 맨 앞).

2026-11-28 진우: '정보는 많은데 오늘 뭘 해야 하나가 안 보임' → 한 장에
  ① 시장 국면  ② 오늘 시가에 할 일(어드바이저 매매지시 · 휩쏘 신호)  ③ 워치리스트 경보  ④ 주의(VKOSPI · 만기)
다른 카드는 그대로 — 이 카드는 요약이고 근거는 뒤 카드들.

자료 (지어내는 값 없음 — 없거나 날짜가 어긋나면 그 칸에 '없음'·'확인 필요'와 이유):
  pc/today.json      PC jq_결론올리기.py 가 전날 저녁(평일 19:20) 올림 — 국면(시장국면.py)·휩쏘 탐지·어드바이저 매매지시·로그 errorlevel
  jq_watchlist.json  전날 마감 run 이 넣은 lv(현재가·20일선·손절선) · updated = 마지막 마감일(= PC 기준일이어야 맞음)
  시장브리핑_*.md    이 아침 run 이 만든 VKOSPI·만기 일정
산출: 카드뉴스/YYYY-MM-DD/오늘의결론_카톡_p1.png (+ 메인 폴더 오늘의결론_카톡.png)
사용: python jq_today_card.py  ·  python jq_today_card.py --self-test
"""
import os, sys, json, datetime
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
import jq_mcard as M


def _load(name):
    try:
        return json.load(open(os.path.join(HERE, name), encoding="utf-8"))
    except Exception:
        return None


def _md(d):
    """'2026-11-27' → '11/27'"""
    return f"{int(d[5:7])}/{int(d[8:10])}" if d and len(d) >= 10 and d[4] == "-" else (d or "?")


def _names(xs, k=6):
    return " · ".join(xs[:k]) + (f" 외 {len(xs) - k}" if len(xs) > k else "")


def _brief():
    """(시장브리핑 글, VKOSPI 값, 다가오는 월간·동시 만기 [(날짜, 설명, D-n)]) — 없으면 (None, None, [])."""
    try:
        import jq_cards as JC
        txt, _ = JC.brief()
        if not txt:
            return None, None, []
        v, _ = JC.grab(txt, "VKOSPI")
        try:
            v = float(v)
        except Exception:
            v = None
        ev = [e for e in JC.expiries(txt) if "위클리" not in e[1] and ("옵션만기" in e[1] or "동시만기" in e[1] or "마녀" in e[1])]
        return txt, v, sorted(ev, key=lambda e: e[0])
    except Exception as e:
        print("  [시장브리핑] 못 읽음:", e)
        return None, None, []


def plan(pc, wl, vk, ev):
    """그릴 내용 → [('sec', 제목) | ('stat', 이름, 값, 색, 메모) | ('row', 왼쪽, 오른쪽, 색, 아래줄)] — 판단은 전부 여기(검증 대상)."""
    P = []
    exp = (wl or {}).get("updated")                      # 마지막 마감일
    base = (pc or {}).get("기준일")
    if not pc:
        P.append(("row", "PC 결론 없음", "확인 필요", M.RED, "pc/today.json 이 없음 — PC 예약작업 JQ_결론올리기(평일 19:20) 확인"))
    elif exp and base and base < exp:
        P.append(("row", f"PC 결론이 {_md(base)} 것", "확인 필요", M.RED,
                  f"마지막 마감은 {_md(exp)} — 어제 저녁 PC가 안 돌았을 수 있음 · 아래 국면·지시는 {_md(base)} 기준"))

    # ① 국면
    if pc:
        g = pc.get("국면") or {}
        j = str(g.get("판정", "?"))
        col = M.GREEN if j.startswith("실행") else (M.RED if j.startswith("관찰") else M.YEL)
        mdd = g.get("mdd252")
        P.append(("stat", "시장 국면 (PC 시장국면)", j, col, f"1년 고점 대비 {mdd * 100:+.0f}%" if isinstance(mdd, (int, float)) else ""))

    # ② 오늘 시가에 할 일
    P.append(("sec", "오늘 시가에 할 일"))
    if pc:
        a = pc.get("어드바이저") or {}
        h = a.get("건강") or {}
        bad = h and (h.get("errorlevel") != 0 or (base and h.get("날") and h.get("날") < base))
        if a.get("상태") != "ok" or bad:
            why = a.get("이유") or ""
            if h:
                why = (why + " · " if why else "") + f"마지막 실행 {_md(h.get('날'))} errorlevel {h.get('errorlevel')}"
            P.append(("row", "어드바이저", "확인 필요", M.RED, (why or "상태 모름") + " — 06_out/run_daily_log.txt"))
        elif not a.get("지시"):
            P.append(("row", "어드바이저 매매지시", "주문 없음", M.SUB, None))
        else:
            for o in a["지시"]:
                k = o.get("구분", "")
                col = M.GREEN if k == "매수" else (M.RED if k == "매도" else M.SUB)
                how = str(o.get("방법", "")).replace("~09:00", "").replace("(시가 체결)", "").strip()   # 한 줄에 들게
                sub = o.get("비고") if k == "놓침" else f"{how} · 약 {o.get('금액', 0):,}원"
                P.append(("row", f"{k} {o.get('name', '')}", f"{o.get('수량', 0):,}주" if k != "놓침" else "놓침", col, sub))
        w = pc.get("휩쏘") or {}
        go = bool((pc.get("국면") or {}).get("실행"))
        A, B = w.get("A") or [], w.get("B") or []
        if A:
            P.append(("row", "휩쏘 A형 신호", f"{len(A)}종", M.GREEN if go else M.SUB,
                      _names([x[0] for x in A]) + (" → 가상매매 규칙상 오늘 시가 진입 후보" if go else " → 국면이 실행 아님: 진입 안 함")))
        if B:
            P.append(("row", "휩쏘 B형(리더) 신호", f"{len(B)}종", M.SUB, _names([x[0] for x in B]) + " · 가상매매 대상 아님(A형만)"))
        if not A and not B:
            st = w.get("상태", "모름")
            P.append(("row", "휩쏘 신호", "없음" if st == "조건 만족 없음" else "확인 필요",
                      M.SUB if st == "조건 만족 없음" else M.RED, None if st == "조건 만족 없음" else f"{_md(base)} 탐지: {st}"))
    else:
        P.append(("row", "어드바이저 · 휩쏘", "자료 없음", M.RED, "PC 결론이 없어 오늘 할 일을 못 적음"))

    # ③ 워치리스트
    items = (wl or {}).get("items", [])
    lv = [(it.get("name", ""), it["lv"]) for it in items if (it.get("lv") or {}).get("close")]
    P.append(("sec", f"워치리스트 경보 ({_md(exp)} 마감)"))
    if not lv:
        P.append(("row", "가격선", "없음", M.SUB, "다음 마감부터 계산(현재가·20일선·손절선)"))
    else:
        stop = [n for n, v in lv if v["close"] < v["low20"]]
        below = [n for n, v in lv if v["close"] < v["ma20"]]
        # 이름은 한 줄에 들어갈 만큼만(전체 목록은 워치리스트 카드) — 1쪽에 담기 위함
        P.append(("row", "손절선 아래", f"{len(stop)}종", M.RED if stop else M.GREEN, _names(stop, 3) if stop else None))
        P.append(("row", "20일선 아래", f"{len(below)}/{len(lv)}종", M.YEL if below else M.GREEN, _names(below, 3) if below else None))

    # ④ 주의
    P.append(("sec", "주의"))
    if vk is None:
        P.append(("row", "VKOSPI", "N/A", M.SUB, "수신 실패 — 시황 카드 참고"))
    else:
        lvl = "공포 극단" if vk > 60 else ("경계" if vk > 30 else "안정")
        P.append(("row", "VKOSPI", f"{vk:g} {lvl}", M.RED if vk > 30 else M.GREEN, "변동성 큼 — 주문은 지정가·분할 고려" if vk > 30 else None))
    if ev:
        d, s, dn = ev[0]
        P.append(("row", s.split("(")[0].strip() or "다음 만기", f"{_md(d)} {dn}".strip(), M.YEL, None))
    return P


def build(P, day, base):
    c = M.Card("오늘의 결론", day, accent=M.GREEN,
               sub=(f"PC {_md(base)} 마감 기준" if base else "PC 결론 없음"),
               foot="추천 아님 · 근거는 뒤 카드들 · 결정·책임 본인")
    for p in P:
        if p[0] == "sec":
            c.sec(p[1])
        elif p[0] == "stat":
            c.stat(p[1], p[2], "", p[3], note=p[4])
        else:
            c.row(p[1], p[2], rc=p[3], rbold=True, sub=p[4] or None)
    return c


def main():
    pc, wl = _load(os.path.join("pc", "today.json")), _load("jq_watchlist.json")
    _, vk, ev = _brief()
    day = datetime.date.today().isoformat()
    P = plan(pc, wl, vk, ev)
    paths = build(P, day, (pc or {}).get("기준일")).save("오늘의결론_카톡", HERE, day, folder_date=day)
    print(f"[산출] 오늘의결론_카톡 {len(paths)}쪽 · PC 기준일 {(pc or {}).get('기준일')} · 워치 {(wl or {}).get('updated')}")
    return 0


def self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += bool(c); print(("  OK  " if c else "  FAIL") + " " + n)
    rows = lambda P: {p[1]: p for p in P if p[0] == "row"}
    wl = {"updated": "2026-11-27", "items": [
        {"name": "가", "lv": {"close": 90, "ma20": 100, "ma60": 100, "low20": 95}},
        {"name": "나", "lv": {"close": 110, "ma20": 100, "ma60": 100, "low20": 95}},
        {"name": "다"}]}
    pc = {"기준일": "2026-11-27", "국면": {"판정": "실행(유리)", "실행": True, "mdd252": -0.4616},
          "휩쏘": {"상태": "있음", "A": [["코리아써키트", "B", ""]], "B": []},
          "어드바이저": {"상태": "ok", "건강": {"날": "2026-11-27", "errorlevel": 0},
                     "지시": [{"구분": "매수", "name": "광전자", "수량": 38, "금액": 239780, "방법": "동시호가 시장가"}]}}
    P = plan(pc, wl, 58.4, [("2026-12-10", "동시만기(네마녀) (D-9)", "D-9")])
    R = rows(P)
    chk("국면 칸: 실행(유리) · −46%", [p for p in P if p[0] == "stat"][0][2:] == ("실행(유리)", M.GREEN, "1년 고점 대비 -46%"))
    chk("매수 지시 1줄: 광전자 38주", R["매수 광전자"][2] == "38주" and "239,780원" in R["매수 광전자"][4])
    pcx = json.loads(json.dumps(pc)); pcx["어드바이저"]["지시"][0]["방법"] = "08:30~09:00 동시호가 시장가(시가 체결)"
    chk("주문 방법 줄임: 08:30 동시호가 시장가", rows(plan(pcx, wl, None, []))["매수 광전자"][4] == "08:30 동시호가 시장가 · 약 239,780원")
    chk("휩쏘 A형 + 실행 국면 = 진입 후보", "진입 후보" in R["휩쏘 A형 신호"][4])
    chk("워치: 손절선 아래 '가' · 20일선 아래 1/2", R["손절선 아래"][2] == "1종" and R["20일선 아래"][2] == "1/2종")
    chk("VKOSPI 58.4 = 경계(빨강)", R["VKOSPI"][2] == "58.4 경계" and R["VKOSPI"][3] == M.RED)
    chk("다음 만기: 동시만기 12/10 D-9", R["동시만기"][2] == "12/10 D-9")
    chk("날짜 맞으면 경고 줄 없음", not any("PC 결론" in k for k in R))
    pc2 = json.loads(json.dumps(pc)); pc2["기준일"] = "2026-11-26"
    chk("PC 기준일 < 마지막 마감 → 확인 필요", "PC 결론이 11/26 것" in rows(plan(pc2, wl, None, [])))
    pc3 = json.loads(json.dumps(pc)); pc3["어드바이저"]["건강"]["errorlevel"] = 1
    chk("어드바이저 errorlevel 1 → 확인 필요(빨강)", rows(plan(pc3, wl, None, []))["어드바이저"][2:4] == ("확인 필요", M.RED))
    pc4 = json.loads(json.dumps(pc)); pc4["국면"] = {"판정": "관찰만(불리)", "실행": False}
    R4 = rows(plan(pc4, wl, None, []))
    chk("국면 실행 아님 → 휩쏘 진입 안 함", "진입 안 함" in R4["휩쏘 A형 신호"][4])
    pc5 = json.loads(json.dumps(pc)); pc5["휩쏘"] = {"상태": "조건 만족 없음", "A": [], "B": []}; pc5["어드바이저"]["지시"] = []
    R5 = rows(plan(pc5, wl, None, []))
    chk("신호·지시 없음 = '없음'·'주문 없음'(빨강 아님)", R5["휩쏘 신호"][2] == "없음" and R5["어드바이저 매매지시"][2:4] == ("주문 없음", M.SUB))
    R6 = rows(plan(None, None, None, []))
    chk("PC 결론 파일 없음 → 확인 필요 · 가격선 없음", "PC 결론 없음" in R6 and R6["가격선"][2] == "없음")
    print("self-test: %d/%d" % (ok, tot)); return 0 if ok == tot else 1


if __name__ == "__main__":
    sys.exit(self_test() if "--self-test" in sys.argv else main())
