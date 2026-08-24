#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
kosdaq_lane_scan_v1.py — 테마 lane 통합 스캔 (선반영 게이트 × 촉매 × 수급)
한 번에: ①선반영 게이트(미과열?) ②뉴스 촉매 ③DART 공시 촉매 ④외국인·기관 수급
→ "안 추격(PASS) + 촉매/수급 2+ 점등" 종목을 ★주목으로 표시. 매수신호 아님 — 후보 surfacing.
production·C·D·영역3·v41·v42 무수정. 기존 스캐너 함수 재사용(임포트).
선행: python fetch_kosdaq_daily_panel.py  (kosdaq_theme_daily.csv). 키: naver_api.json·.dart_key.
사용: python kosdaq_lane_scan_v1.py [--days 14] | --selftest
"""
import sys, importlib.util
from datetime import date
from pathlib import Path
BASE = Path(__file__).parent.resolve()


def _load(modfile):
    spec = importlib.util.spec_from_file_location(modfile.replace(".py", ""), BASE / modfile)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m); return m


PRE = _load("kosdaq_preempt_scan_v1.py")
NEWS = _load("kosdaq_news_scan_v1.py")
CAT = _load("kosdaq_catalyst_scan_v1.py")


def decide(gate_pass, has_catalyst, has_flow):
    """A촉매(뉴스 or DART) + C수급(외 or 기) = 레이어. 게이트 PASS + 2레이어 = 주목."""
    layers = (1 if has_catalyst else 0) + (1 if has_flow else 0)
    if gate_pass and layers >= 2:
        return "★주목", layers
    if gate_pass and layers >= 1:
        return "관심", layers
    if gate_pass:
        return "미과열만", layers
    return "보류(LATE)" if not gate_pass else "-", layers


def score(gp, nc, dc, f, ii, pd_):
    """참고 종합점수(0~5) = 촉매(뉴스+DART, 0~2) + 수급(외+기, 0~2) + 여지(0~1). PASS만 의미.
    여지: 고점대비 −10%~−45%(적정 눌림)=+1 / 신고가 근접·과소외=0. a-priori·튜닝 안 함."""
    if gp is not True:
        return None, ""
    cat = (1 if nc else 0) + (1 if dc else 0)
    flow = (1 if f else 0) + (1 if ii else 0)
    room = 1 if (pd_ is not None and -45 <= pd_ <= -10) else 0
    tot = cat + flow + room
    return tot, "촉매%d+수급%d+여지%d" % (cat, flow, room)


def label(sc):
    """점수(0~5) → (별점, 글자). 높을수록 좋은 후보."""
    stars = "★" * sc + "☆" * (5 - sc)
    txt = "강한 후보" if sc >= 4 else ("보통" if sc >= 2 else "약함")
    return stars, txt


def write_log(rows, star, interest, ranked):
    """돌 때마다 진우퀀트_스캔로그.md에 1회분 누적(append)."""
    f = BASE / "진우퀀트_스캔로그.md"
    new = not f.exists()
    with open(f, "a", encoding="utf-8") as o:
        if new:
            o.write("# 진우퀀트 — 테마 lane 스캔 로그 (자동 누적)\n\n> 매 스캔마다 1블록 추가. 월별 비교용. 매수신호 아님.\n")
        o.write("\n---\n\n## %s  (★주목 %d · 관심 %d)\n\n" % (date.today(), star, interest))
        o.write("| 종목 | 테마 | 게이트 | 고점%% | 뉴스촉매 | DART촉매 | 외 | 기 | 판정 |\n|---|---|---|---|---|---|---|---|---|\n")
        for name, theme, gp, pd_, nc, dc, fr, ii, verdict, layers in rows:
            if verdict in ("미과열만", "보류(LATE)") and not (nc or dc) and verdict != "미과열만" and verdict != "관심" and verdict != "★주목":
                pass
            g = "PASS" if gp is True else ("LATE" if gp is False else "?")
            ps = ("%+.0f" % pd_) if pd_ is not None else "-"
            # 로그엔 PASS 계열 + 새 촉매 뜬 종목만(간결)
            if gp is True or nc or dc:
                o.write("| %s | %s | %s | %s | %s | %s | %s | %s | %s |\n" %
                        (name, theme, g, ps, nc or "-", dc or "-", "O" if fr else "-", "O" if ii else "-", verdict))
    with open(BASE / "진우퀀트_스캔로그.md", "a", encoding="utf-8") as o:
        if ranked:
            o.write("\n**참고 순위(PASS 후보, 0~5 · 매수명령 아님)**: ")
            o.write(" / ".join("%d위 %s %s%d [%s]" % (i, nm, label(sc)[0], sc, bd)
                                for i, (sc, nm, th, pd_, bd) in enumerate(ranked[:5], 1)))
            o.write("\n")
    print("  [로그] 진우퀀트_스캔로그.md 에 %s 기록 추가" % date.today())


def main():
    days = 14
    if "--days" in sys.argv:
        try: days = int(sys.argv[sys.argv.index("--days") + 1])
        except (ValueError, IndexError): pass
    uni = PRE.load_universe()                 # {code:(name,theme)}
    px = PRE.load_prices()
    # 게이트
    gate = {}
    for code, (name, theme) in uni.items():
        g = PRE.gate(px.get(code))
        gate[code] = (g[2], (g[1] - 1) * 100) if g else (None, None)   # (pass, 고점대비%)
    # 뉴스 촉매 (네이버 키 있으면)
    news_cat = {}
    cid, csec = NEWS._naver_creds()
    if cid and csec:
        for code, (name, theme) in uni.items():
            try:
                for title, _ in NEWS.fetch_news(name, cid, csec):
                    hits = NEWS.extract_signal(title, [name])
                    if hits:
                        news_cat[code] = hits[0][1]; break
            except Exception:
                pass
    else:
        print("  [안내] naver_api.json 없음 → 뉴스 촉매 생략")
    # DART 촉매 + 수급 (키/ pykrx 있으면)
    univ_tn = {code: name for code, (name, theme) in uni.items()}
    dart_cat, f_set, i_set = {}, set(), set()
    key = CAT.load_api_key(); corp = CAT.load_corp_map()
    if key and corp:
        try: dart_cat = CAT.fetch_catalysts(key, corp, univ_tn, days)
        except Exception as e: print("  [DART skip]", e)
    else:
        print("  [안내] DART 키/corp맵 없음 → 공시 촉매 생략")
    try:
        f_set, i_set = CAT.fetch_supply(univ_tn, max(5, days // 2))
    except Exception as e:
        print("  [수급 skip]", e)
    # 종합
    rows = []
    for code, (name, theme) in uni.items():
        gp, pd_ = gate[code]
        nc = news_cat.get(code); dc = dart_cat.get(code)
        f = code in f_set; ii = code in i_set
        has_cat = bool(nc or dc); has_flow = f or ii
        verdict, layers = decide(gp is True, has_cat, has_flow)
        rows.append((name, theme, gp, pd_, nc, dc, f, ii, verdict, layers))
    order = {"★주목": 0, "관심": 1, "미과열만": 2, "보류(LATE)": 3, "-": 4}
    rows.sort(key=lambda r: (order.get(r[8], 9), -(r[9]), (r[3] if r[3] is not None else 9e9)))
    print("\n=== 테마 lane 통합 스캔 (선반영×촉매×수급) — %d종 ===" % len(uni))
    print("★주목 = 미과열(PASS) + 촉매 + 수급 2+. 매수신호 아님·매수일 재확인.\n")
    print("종목          | 테마      | 게이트 | 고점% | 뉴스촉매 | DART촉매 | 외 | 기 | 판정")
    for name, theme, gp, pd_, nc, dc, f, ii, verdict, layers in rows:
        g = "PASS" if gp is True else ("LATE" if gp is False else "?")
        ps = ("%+.0f" % pd_) if pd_ is not None else "-"
        print("  %-12s | %-8s | %-4s | %4s | %-8s | %-8s | %s | %s | %s"
              % (name[:12], theme[:8], g, ps, (nc or "-")[:8], (dc or "-")[:8],
                 "O" if f else "-", "O" if ii else "-", verdict))
    # 참고 순위 (PASS 후보만, 종합점수 내림차순)
    ranked = []
    for name, theme, gp, pd_, nc, dc, fr, ii, verdict, layers in rows:
        sc, bd = score(gp, nc, dc, fr, ii, pd_)
        if sc is not None:
            ranked.append((sc, name, theme, pd_, bd))
    ranked.sort(key=lambda x: (-x[0], (x[3] if x[3] is not None else 9e9)))
    if ranked:
        print("\n--- 참고 순위 (PASS 후보, 종합점수 0~5) · 매수명령 아님 ---")
        for i, (sc, name, theme, pd_, bd) in enumerate(ranked[:5], 1):
            stars, txt = label(sc)
            print("  %d위. %-12s (%s) %s %d/5 · %s [%s] 고점대비 %s%%"
                  % (i, name, theme[:8], stars, sc, txt, bd, ("%+.0f" % pd_) if pd_ is not None else "-"))
    star = sum(1 for r in rows if r[8] == "★주목")
    print("\n★주목 %d종 / 관심 %d종. (주목 종목에 thesis·무효화 등록 → Track W)"
          % (star, sum(1 for r in rows if r[8] == "관심")))
    write_log(rows, star, sum(1 for r in rows if r[8] == "관심"), ranked)


def selftest():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print("  [%s] %s" % ("OK" if c else "FAIL", n))
    chk("PASS+촉매+수급 → 주목", decide(True, True, True)[0] == "★주목")
    chk("PASS+촉매만 → 관심", decide(True, True, False)[0] == "관심")
    chk("PASS+신호無 → 미과열만", decide(True, False, False)[0] == "미과열만")
    chk("LATE+촉매+수급 → 주목 아님", decide(False, True, True)[0] != "★주목")
    chk("임포트 3종 OK", all(hasattr(m, "load_universe") for m in (PRE, NEWS, CAT)))
    print("self-test: %d/%d" % (ok, tot)); return ok == tot


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        try: main()
        except Exception:
            import traceback; print("\n[에러]"); traceback.print_exc()
