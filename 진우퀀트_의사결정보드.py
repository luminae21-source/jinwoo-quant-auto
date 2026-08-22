#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
진우퀀트_의사결정보드.py — 행동을 정하는 '객관지표' 보드 생성기 (기사·내러티브 금지)
입력: kosdaq_theme_daily.csv (월 스캔 파이프라인 산출, KOSPI=KS11 + 테크윙 089030 OHLC 포함).
산출: 진우퀀트_의사결정보드.md  (A 시장단계→레버리지 / B 본체 / C 보유 테크윙 / D 신규신호 / E 결론)
원칙: 객관 수치·시스템 신호만. 매수/매도 지시 아님 — '룰이 가리키는 상태'만. production·기존 산출물 무수정.
선행: python fetch_kosdaq_daily_panel.py   사용: python 진우퀀트_의사결정보드.py | --selftest
"""
import csv, sys
from datetime import date, timedelta
from pathlib import Path
BASE = Path(__file__).parent.resolve()
try:
    import importlib.util as _il
    _sp=_il.spec_from_file_location('jqb', Path(__file__).parent/'jq_breadth.py')
    JQB=_il.module_from_spec(_sp); _sp.loader.exec_module(JQB)
except Exception:
    JQB=None

# === 진우님 계좌 파라미터 (바뀌면 여기만 수정) ===
TECHWING_ENTRY = 60450      # 테크윙 평단(원)
CURRENT_LEVERAGE = 43       # 현재 실계좌 레버리지(%)
STOP_ATR_K = 2.5
STOP_CAP = 0.20             # 손절 하한가 캡 −20%


def _d(s):
    y, m, dd = str(s)[:10].split("-"); return date(int(y), int(m), int(dd))


def load_ohlc(code, path="kosdaq_theme_daily.csv"):
    out = []
    p = BASE / path
    if not p.exists():
        return out
    for r in csv.DictReader(open(p, encoding="utf-8-sig")):
        if str(r.get("code")) == code:
            try:
                out.append((_d(r["date"]), float(r["open"] or 0), float(r["high"] or 0),
                            float(r["low"] or 0), float(r["close"])))
            except (ValueError, KeyError):
                pass
    return sorted(out)


def atr14(ohlc):
    if len(ohlc) < 15:
        return None
    trs = []
    for i in range(1, len(ohlc)):
        h, l, pc = ohlc[i][2], ohlc[i][3], ohlc[i-1][4]
        trs.append(max(h - l, abs(h - pc), abs(l - pc)))
    return sum(trs[-14:]) / 14


def realized_vol(closes, n=20):
    if len(closes) < n + 1:
        return None
    rets = [closes[i]/closes[i-1]-1 for i in range(len(closes)-n, len(closes))]
    m = sum(rets)/len(rets)
    sd = (sum((r-m)**2 for r in rets)/(len(rets)-1))**0.5
    return sd * (252**0.5) * 100


def market_stage(ks):
    closes = [c for _,_,_,_,c in ks]
    last = closes[-1]
    ma200 = sum(closes[-200:]) / min(200, len(closes))
    gap = (last/ma200 - 1) * 100
    hi = max(closes[-252:]); dd = (last/hi - 1) * 100
    rv = realized_vol(closes)
    above = last > ma200
    if (not above) or dd <= -20:
        stage, emoji, lim = "위험", "🔴", "0~10%"
    elif gap < 3 or dd <= -10 or (rv is not None and rv > 25):
        stage, emoji, lim = "주의", "🟡", "15%"
    else:
        stage, emoji, lim = "정상", "🟢", "30%"
    return {"last": last, "ma200": ma200, "gap": gap, "dd": dd, "rv": rv,
            "above": above, "stage": stage, "emoji": emoji, "limit": lim}


def next_rebal(today):
    y, m = (today.year, today.month + 1) if today.month < 12 else (today.year + 1, 1)
    nr = date(y, m, 1)
    return nr, (nr - today).days


def techwing_block(tw):
    if not tw:
        return None
    closes = [c for _,_,_,_,c in tw]
    cur = closes[-1]
    a = atr14(tw)
    stop_atr = TECHWING_ENTRY - STOP_ATR_K * a if a else None
    stop_cap = TECHWING_ENTRY * (1 - STOP_CAP)
    stop = max(stop_atr, stop_cap) if stop_atr else stop_cap   # 둘 중 높은(타이트한) 선
    pnl = (cur/TECHWING_ENTRY - 1) * 100
    dist = (cur - stop) / cur * 100
    hi = max(closes[-252:]); gap_hi = (cur/hi - 1) * 100
    gate = "PASS" if (gap_hi < -5) else "LATE"   # 고점 −5% 밖이면 미과열(간이)
    if cur <= stop:
        action = "손절(손절선 도달)"
    elif dist <= 5:
        action = "손절 임박(거리 ≤5%)"
    else:
        action = "보유"
    return {"cur": cur, "atr": a, "stop": stop, "stop_cap": stop_cap, "stop_atr": stop_atr,
            "pnl": pnl, "dist": dist, "gap_hi": gap_hi, "gate": gate, "action": action}


def latest_starred():
    p = BASE / "진우퀀트_스캔로그.md"
    if not p.exists():
        return None, []
    lines = open(p, encoding="utf-8").read().splitlines()
    blocks = [i for i, l in enumerate(lines) if l.startswith("## ")]
    if not blocks:
        return None, []
    start = blocks[-1]
    hdr = lines[start][3:].split("(")[0].strip()
    stars = []
    for l in lines[start:]:
        if "★주목" in l and l.startswith("|"):
            cells = [c.strip() for c in l.split("|")]
            if len(cells) > 1:
                stars.append(cells[1])
    return hdr, stars


def build():
    ks = load_ohlc("KS11"); tw = load_ohlc("089030")
    if not ks:
        print("  [중단] KS11 시세 없음 — fetch_kosdaq_daily_panel.py 먼저."); return
    today = ks[-1][0]
    M = market_stage(ks)
    nr, dday = next_rebal(today)
    T = techwing_block(tw)
    sdate, stars = latest_starred()
    lev_warn = "⚠️ **한도 초과**: 현재 %d%% > 상한 %s → 신규 레버리지 금지·축소 검토" % (CURRENT_LEVERAGE, M["limit"]) \
        if CURRENT_LEVERAGE > int(M["limit"].split("~")[-1].rstrip("%")) else "한도 내"

    L = []
    L.append("# 진우퀀트 — 의사결정 보드 (%s)" % today)
    L.append("\n> 행동을 정하는 **객관지표만**. 기사·내러티브 없음. **매수/매도 지시 아님 — 룰이 가리키는 상태만.**\n")
    # A
    L.append("## A. 시장 단계 → 레버리지 한도")
    rv = ("%.1f%%" % M["rv"]) if M["rv"] is not None else "N/A"
    L.append("- KOSPI 종가 **%.0f** vs MA200 %.0f → **%s** (이격 %+.1f%%)" % (M["last"], M["ma200"], "위" if M["above"] else "아래", M["gap"]))
    L.append("- 실현변동성(20일) %s · 고점대비 낙폭 **%+.1f%%**" % (rv, M["dd"]))
    L.append("- **단계 %s %s → 권장 레버리지 상한 %s**" % (M["emoji"], M["stage"], M["limit"]))
    L.append("- 현재 레버리지 **%d%%** → %s" % (CURRENT_LEVERAGE, lev_warn))
    # B
    L.append("\n## B. 본체 시스템 (v3.7.2)")
    L.append("- KOSPI MA200 추세방어: **%s** (%s)" % ("RISK-ON 보유" if M["above"] else "RISK-OFF 관망", "이격 %+.1f%%" % M["gap"]))
    L.append("- 다음 월 리밸런스: **%s (D−%d)**" % (nr, dday))
    L.append("- 행동: **무변경**(월 1회 리밸 시점에만 집행)")
    # C
    L.append("\n## C. 보유종목 — 테크윙(089030) · 평단 %d · 계좌 현금" % TECHWING_ENTRY)
    if T:
        L.append("- 현재가 **%.0f** · 손익 **%+.1f%%**" % (T["cur"], T["pnl"]))
        atrs = ("%.0f" % T["atr"]) if T["atr"] else "N/A"
        L.append("- 게이트 %s (고점대비 %+.1f%%) · ATR14 %s" % (T["gate"], T["gap_hi"], atrs))
        L.append("- 손절선 **%.0f** (−2.5ATR %s / −20%%캡 %.0f 중 타이트한 선) → **손절선까지 거리 %+.1f%%** ⭐" %
                 (T["stop"], ("%.0f" % T["stop_atr"]) if T["stop_atr"] else "N/A", T["stop_cap"], T["dist"]))
        L.append("- 무효화(수주 둔화·마이크론 퀄 실패): **수동 확인 필요**(자동판별 불가)")
        L.append("- **행동: %s**" % T["action"])
    else:
        L.append("- (089030 시세 없음 — 패널 확인)")
    # D
    L.append("\n## D. 신규 신호")
    if stars:
        L.append("- 최근 스캔(%s) ★주목: **%s** → thesis 검토" % (sdate, ", ".join(stars)))
    else:
        L.append("- 최근 스캔 ★주목 없음(또는 로그 미동기화) → **대기**")
    # F. 장세 폭/쏠림
    regime_name = None
    L.append("\n## F. 장세 폭/쏠림 (측정·맥락 인지, 예측 아님)")
    if JQB is not None:
        try:
            bpx = JQB.load_closes()
            if len(bpx) >= 5:
                bm = JQB.compute(bpx)
                emoji, regime_name, bl = JQB.fmt(bm)
                L.extend(bl)
            else:
                L.append("- (테마 시세 부족 — 패널 확인)")
        except Exception as e:
            L.append("- (장세 계산 skip: %s)" % e)
    else:
        L.append("- (jq_breadth.py 없음)")
    # E
    L.append("\n## E. 오늘의 결론 (한 줄)")
    concl = "시스템 무변경"
    if T and T["action"] != "보유":
        concl += " · **테크윙 %s**" % T["action"]
    else:
        concl += " · 테크윙 손절선 유지(거리 %+.1f%%)" % (T["dist"] if T else 0)
    if CURRENT_LEVERAGE > int(M["limit"].split("~")[-1].rstrip("%")):
        concl += " · **레버리지 한도초과→축소 검토**"
    concl += " · 신규 %s" % ("★주목 thesis 검토" if stars else "신호 없음(대기)")
    if regime_name:
        concl += " · 장세 %s" % regime_name
    L.append("> **%s**" % concl)
    L.append("\n---\n*객관지표 보드 — 정보·룰 상태 표시일 뿐 투자 추천 아님. 무효화·뉴스는 진우님 수동 확인.*")

    out = BASE / "진우퀀트_의사결정보드.md"
    out.write_text("\n".join(L), encoding="utf-8")
    print("  [보드] 진우퀀트_의사결정보드.md 생성 (%s)" % today)
    print("\n".join(L[:14]))


def selftest():
    import datetime as dt
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += 1 if c else 0
        print("  [%s] %s" % ("OK" if c else "FAIL", n))
    # 상승장 합성 KOSPI
    base = [(date(2025,1,1)+dt.timedelta(days=i), 100+i*0.1, 100+i*0.1, 100+i*0.1, 100+i*0.1) for i in range(260)]
    M = market_stage(base)
    chk("상승장 → MA200 위", M["above"] is True)
    chk("정상단계 상한 30%", M["limit"] == "30%")
    # ATR/손절: 평단 위 가격
    tw = [(date(2025,1,1)+dt.timedelta(days=i), 60000,61000,59000,60000+i*10) for i in range(20)]
    T = techwing_block(tw)
    chk("손절선 < 현재가", T["stop"] < T["cur"])
    chk("−20%캡 = 평단×0.8", abs(T["stop_cap"] - TECHWING_ENTRY*0.8) < 1)
    chk("거리% 양수(현재가>손절선)", T["dist"] > 0)
    chk("레버리지 43 > 30 경고대상", CURRENT_LEVERAGE > 30)
    print("self-test: %d/%d" % (ok, tot)); return ok == tot


if __name__ == "__main__":
    if "--selftest" in sys.argv:
        selftest()
    else:
        try: build()
        except Exception:
            import traceback; print("\n[에러]"); traceback.print_exc()
