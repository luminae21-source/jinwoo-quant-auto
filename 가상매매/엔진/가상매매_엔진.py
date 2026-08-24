# -*- coding: utf-8 -*-
"""
가상매매_엔진.py — 진우퀀트 Phase 1 페이퍼트레이딩 엔진 (결정론적 실행기)

역할 분리
  · 이 프로그램 = 결정론적 실행기. 규칙을 실행만 한다. 학습하지 않는다.
  · 클로드/사람 = 학습층. 엔진이 남긴 CSV를 읽고 평가·개선안·채택/기각을 판단.
  → 엔진은 모든 판단 근거를 CSV로 남긴다 (왜 샀는지 / 왜 팔았는지).

★ 규칙은 jq_paper_core.py 에만 존재한다 (Single Source of Truth).
   가상매매_백테스트.py 도 같은 함수를 import 한다. 실전≠백테스트면 백테스트는 무의미.

★ 절대 원칙: 실재 데이터만. 추정·보간·합성 금지. 실패 시 '데이터부족' 명시 후 제외.
   투자자문 아님. 지표·규칙 사실만 기록. 결정·책임은 본인.

⚠ 규칙 충돌 고지
   매도규칙서.md v2(2026-07-12)는 `+1R 절반익절`을 **삭제**했다.
   근거(본인 실측 17,948건): 절반익절 有 → 기대값 -0.01R (엣지 소멸).
   포트폴리오 sweep: +1R 익절이 승률 최고(44.8%)·기대값 최악(-0.012R), 늦출수록 단조 개선.
   ∴ 기본값 HALF_TP=False. Phase 1 스펙의 +1R 절반매도를 쓰려면 --half-tp 로 명시적으로 켤 것.

실행:
  py 가상매매_엔진.py                  py 가상매매_엔진.py --self-test
  py 가상매매_엔진.py --source local|pykrx|auto
  py 가상매매_엔진.py --halloween      py 가상매매_엔진.py --half-tp
"""
import os, sys, argparse, datetime as dt

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import jq_paper_core as C
from jq_paper_core import (
    CFG, PriceStore, RunLogger, DIR_LEDGER,
    passes_L, passes_S, check_exit_core, size_position,
    atr_wilder, ma_and_slope, to_weekly, macro_gate, is_first_trading_day,
    load_coupling_panel, compute_coupling, append_coupling,
    fmt_won, fmt_pct, read_csv, append_csv, write_csv, isnan,
    LEDGER_COLS, POS_COLS, EQ_COLS, SIG_COLS,
)


# ═══════════════════════════════════════════════════════════════════════════
# 신호 — 필터 통과/탈락 근거 전량 기록 (클로드 학습용)
# ═══════════════════════════════════════════════════════════════════════════
def evaluate(store, market, code, asof, track):
    row = dict.fromkeys(SIG_COLS, "")
    row.update(date=pd.Timestamp(asof).date().isoformat(), track=track, code=code,
               name=store.name(code), market=market, passed=0)

    bars = store.bars(market, code, asof)
    if bars is None or len(bars) < CFG["MIN_BARS"]:
        row["f_bars"] = 0
        row["reject_reason"] = "데이터부족(일봉 부족)"
        for k in ("close", "atr", "f_ma_week", "f_slope_week", "f_ma_short",
                  "f_slope_short", "f_htf_align", "score"):
            row[k] = "데이터부족"
        return row

    row["f_bars"] = 1
    close = float(bars["close"].iloc[-1])
    row["close"] = round(close, 1)

    atr = atr_wilder(bars["high"], bars["low"], bars["close"], CFG["ATR_N"])
    row["atr"] = "데이터부족" if isnan(atr) else round(atr, 2)

    wk = to_weekly(bars["date"], bars["close"])
    ma_w, slope_w = ma_and_slope(wk, CFG["L"]["MA_WEEK"], CFG["L"]["SLOPE_WEEKS"])
    ma_s, slope_s = ma_and_slope(bars["close"], CFG["S"]["MA_SHORT"], CFG["S"]["SLOPE_DAYS"])

    above_w = float("nan") if isnan(ma_w) else (close > ma_w)
    row["f_ma_week"] = "데이터부족" if isnan(ma_w) else int(close > ma_w)
    row["f_slope_week"] = "데이터부족" if isnan(slope_w) else int(slope_w > 0)
    row["f_ma_short"] = "데이터부족" if isnan(ma_s) else int(close > ma_s)
    row["f_slope_short"] = "데이터부족" if isnan(slope_s) else int(slope_s > 0)
    row["f_htf_align"] = row["f_ma_week"]

    if isnan(atr):
        row["reject_reason"] = "데이터부족(ATR)"
        row["score"] = "데이터부족"
        return row

    if track == "L":
        ok, why, score = passes_L(close, ma_w, slope_w)
    else:
        ok, why, score = passes_S(close, ma_s, slope_s, above_w, CFG["S"]["REQUIRE_HTF"])

    row["passed"] = int(ok)
    row["reject_reason"] = why
    row["score"] = "데이터부족" if isnan(score) else score
    return row


# ═══════════════════════════════════════════════════════════════════════════
# 원장 / 포지션
# ═══════════════════════════════════════════════════════════════════════════
def load_positions():
    d = read_csv("paper_positions.csv", where=DIR_LEDGER, dtype={"code": str})
    if d is None or not len(d):
        return []
    out = []
    for _, r in d.iterrows():
        out.append(dict(
            track=str(r["track"]), code=str(r["code"]), name=str(r["name"]),
            entry_date=str(r["entry_date"]), entry_price=float(r["entry_price"]),
            qty=int(r["qty"]), stop=float(r["stop"]), target_1r=float(r["target_1r"]),
            high_watermark=float(r["high_watermark"]),
            init_stop=float(r["init_stop"]) if pd.notna(r.get("init_stop")) else float(r["stop"]),
            atr=float(r["atr"]) if pd.notna(r.get("atr")) else float("nan"),
            half_sold=int(r["half_sold"]) if pd.notna(r.get("half_sold")) else 0,
            days_held=int(r["days_held"]) if pd.notna(r.get("days_held")) else 0))
    return out


def save_positions(pos, px):
    rows = []
    for p in pos:
        last = px.get((p["track"], p["code"]), p["entry_price"])
        rows.append({
            "track": p["track"], "code": p["code"], "name": p["name"],
            "entry_date": p["entry_date"], "entry_price": round(p["entry_price"], 1),
            "qty": p["qty"], "stop": round(p["stop"], 1),
            "target_1r": round(p["target_1r"], 1),
            "high_watermark": round(p["high_watermark"], 1),
            "days_held": p.get("days_held", 0),
            "unrealized_pnl": round((last - p["entry_price"]) * p["qty"], 0),
            "init_stop": round(p["init_stop"], 1),
            "atr": "" if isnan(p["atr"]) else round(p["atr"], 2),
            "half_sold": p.get("half_sold", 0)})
    write_csv(DIR_LEDGER, "paper_positions.csv", rows, POS_COLS)


def load_cash():
    """원장에서 트랙별 현금 재구성 (재현 가능)."""
    cash = {t: CFG["INITIAL_CAPITAL"] * w for t, w in CFG["TRACK_ALLOC"].items()}
    d = read_csv("paper_ledger.csv", where=DIR_LEDGER, dtype={"code": str})
    if d is None or not len(d):
        return cash
    for _, r in d.iterrows():
        t = str(r["track"])
        if t in cash:
            amt = float(r["amount"])
            cash[t] += -amt if str(r["action"]) == "BUY" else amt
    return cash


def perf_summary(track=None):
    d = read_csv("paper_ledger.csv", where=DIR_LEDGER, dtype={"code": str})
    if d is None or not len(d):
        return None
    if track:
        d = d[d["track"] == track]
    if not len(d):
        return None
    sells = d[d["action"].astype(str).str.startswith("SELL")]
    nb = int((d["action"] == "BUY").sum())
    if not len(sells):
        return dict(거래=nb, 청산=0, 승률=float("nan"), 평균R=float("nan"),
                    손익비=float("nan"), 실현손익=0.0)
    pnl = pd.to_numeric(sells["realized_pnl"], errors="coerce").dropna()
    r = pd.to_numeric(sells["r_multiple"], errors="coerce").dropna()
    w, l = r[r > 0], r[r <= 0]
    return dict(거래=nb, 청산=int(len(sells)),
                승률=float(len(w) / len(r)) if len(r) else float("nan"),
                평균R=float(r.mean()) if len(r) else float("nan"),
                손익비=float(w.mean() / abs(l.mean()))
                if len(w) and len(l) and l.mean() != 0 else float("nan"),
                실현손익=float(pnl.sum()))


def equity_stats(track):
    d = read_csv("paper_equity.csv", where=DIR_LEDGER)
    if d is None or not len(d) or "track" not in d.columns:
        return None
    d = d[d["track"] == track]
    if not len(d):
        return None
    e = pd.to_numeric(d["total_equity"], errors="coerce").dropna()
    if len(e) < 2:
        return None
    cum = e / e.iloc[0]
    return dict(수익률=float(cum.iloc[-1] - 1), MDD=float((cum / cum.cummax() - 1).min()))


# ═══════════════════════════════════════════════════════════════════════════
# 메인
# ═══════════════════════════════════════════════════════════════════════════
def run(args):
    print("=" * 78)
    print("진우퀀트 — 가상매매(페이퍼트레이딩) 엔진  Phase 1")
    print("=" * 78)
    print("  투자자문 아님. 지표·규칙 사실만 기록. 결정·책임은 본인.")
    print(f"  +1R 절반익절 = {'ON (--half-tp)' if CFG['HALF_TP'] else 'OFF (매도규칙서 v2 준수)'}")
    print(f"  할로윈 오버레이 = {'ON' if CFG['HALLOWEEN'] else 'OFF (기본)'}")

    asof = pd.Timestamp(args.asof) if args.asof else pd.Timestamp(dt.date.today())
    store = PriceStore(args.source)

    # ── 하순 신규진입 보류 필터 (2026-07-14 · 30년 패널 재검정 반영) ──────────
    # 근거: 30년패널(5,051종목·상폐포함) OOS p=0.0002(소)/0.0041(중), Bonferroni x12 통과.
    #       ★대형주는 OOS p=0.1211 로 기각★ -> 대형주엔 적용하지 않는다.
    # 비용 0 — 매매를 추가하지 않고 시점만 옮긴다. 청산·보유는 건드리지 않는다.
    #
    # [2026-07-14 수정] 이전에는 tier 를 넘기지 않아 **기각된 규칙이 대형주에**
    #   **적용**되고 있었다(트랙 전체 일괄 차단). 이제 종목별 시총 tier 로 판정한다.
    _late_ok = False          # 필터 사용 가능 여부
    _late_block_fn = None     # (code) -> bool
    _late_why = ""

    print("\n[1] 데이터")
    _loaded = store.load(asof)
    if _loaded and not getattr(args, "no_late_filter", False):
        try:
            from jq_calendar_filter import entry_blocked, why as _lwhy
            from jq_mcap_tier import tier_map
            _td = store.trading_days("KOSPI") or store.trading_days("KOSDAQ")
            _tm = tier_map(asof)        # 시장 전체 시총 3분위 (그 시점 기준)
            if _td:
                def _late_block_fn(_code):
                    _t = _tm.get(str(_code)) if _tm else None
                    return entry_blocked(asof, _td, tier=_t)
                _late_ok = True
                _late_why = _lwhy(asof, _td)
        except Exception as _e:
            print(f"  [경고] 하순 필터 미적용: {str(_e)[:60]}")
    if not _loaded:
        print("  [중단] 사용 가능한 실데이터가 없습니다.")
        for n in store.notes:
            print("  " + n)
        return 2
    for n in store.notes:
        print("  " + n)

    ld = store.last_date()
    if ld is not None and ld < asof:
        print(f"  영업일 보정: 기준일 {asof.date()} -> {ld.date()} (패널 최종 거래일)")
        asof = ld
    print(f"  데이터소스: {store.used}")

    # --- 커플링 (기록 전용. 규칙 미반영) ---
    print("\n[2] 한·미 커플링  ※기록 전용 — 검증 전 규칙 반영 금지")
    panel, _, cnotes = load_coupling_panel()
    for n in cnotes:
        print("  · " + n)
    crow = compute_coupling(asof, panel)
    append_coupling(crow)
    if crow["corr_20d_spx"] == "":
        print("  [커플링] 데이터부족 -> 상관 공란으로 기록")
    else:
        chg = "상태 변경됨" if crow["state_change"] == "Y" else "전일 대비 변화 없음"
        print(f"  [커플링] corr20(KOSPI~SPX, 1d lag) = {crow['corr_20d_spx']} "
              f"-> {crow['state']} ({chg})")
        print(f"           corr20(SOX)={crow['corr_20d_sox']}  "
              f"beta20(SPX)={crow['beta_20d_spx']}  "
              f"corr20(KOSPI~KOSDAQ)={crow['corr_kospi_kosdaq_20d']}")

    # --- 매크로 ---
    print("\n[3] 매크로 게이트")
    exposure, regime, mnotes = macro_gate(asof)
    for n in mnotes:
        print("  · " + n)
    print(f"  -> 총노출 배수 = {exposure:.2f}  (regime: {regime})")

    # --- 유니버스 ---
    print("\n[4] 유니버스")
    uni = {}
    kospi = store.universe("KOSPI", CFG["UNIVERSE_TOP_N"])
    uni.update({c: "KOSPI" for c in kospi})
    print(f"  A(코스피): {len(kospi)}종목")

    kq, theme_ok = [], False
    th = read_csv("theme_heat_latest.csv")
    tm = read_csv("theme_heat_members_latest.csv", dtype={"code": str})
    pq = store.panels.get("KOSDAQ")
    if th is not None and tm is not None and "theme" in th.columns and pq is not None:
        tops = th.sort_values("heat_score", ascending=False)["theme"].head(
            CFG["THEME_TOP_N"]).tolist()
        mem = tm[tm["theme"].isin(tops)]["code"].astype(str).unique().tolist()
        kq = [c for c in mem if c in store.codes("KOSDAQ")]
        print(f"  B(코스닥 테마): theme_heat 상위 {CFG['THEME_TOP_N']} {tops}")
        print(f"     구성 {len(mem)}종목 중 코스닥 패널 보유 {len(kq)}개")
        if len(kq) >= CFG["THEME_MIN_MEMBERS"]:
            theme_ok = True
        else:
            # theme_heat 구성종목은 대부분 코스피 대형주 -> 코스닥 테마 유니버스로 못 쓴다.
            print(f"     [테마연동 미적용] 코스닥 구성종목 {len(kq)}개 < 최소 "
                  f"{CFG['THEME_MIN_MEMBERS']}개 -> 테마 연동 불가")
            kq = []
    if not theme_ok:
        if pq is not None:
            kq = store.universe("KOSDAQ", CFG["KOSDAQ_TOP_N"])
            print(f"  B(코스닥): [테마연동 미적용] 코스닥 시총 상위 {len(kq)}종목 "
                  f"+ 동일 추세필터로 대체")
        else:
            print("  B(코스닥): [데이터부족] 코스닥 패널 없음 -> 제외")
    uni.update({c: "KOSDAQ" for c in kq})
    print(f"  총 유니버스: {len(uni)}종목")

    # --- 신호 ---
    print("\n[5] 신호  (통과/탈락 근거 전량 -> 원장\\paper_signals.csv)")
    sigs, cand = [], {"L": [], "S": []}
    for code, market in uni.items():
        for track in ("L", "S"):
            r = evaluate(store, market, code, asof, track)
            sigs.append(r)
            if r["passed"]:
                cand[track].append((float(r["score"]), code, market))
    write_csv(DIR_LEDGER, "paper_signals.csv", sigs, SIG_COLS)
    lack = sorted({r["code"] for r in sigs if "데이터부족" in str(r["reject_reason"])})
    print(f"  평가 {len(sigs)}건 (종목×트랙)")
    print(f"  데이터부족 {len(lack)}종목 -> 제외")
    if lack:
        print(f"     제외: {', '.join(lack[:25])}"
              f"{' ...외 ' + str(len(lack)-25) + '종목' if len(lack) > 25 else ''}")
    print(f"  통과 — Track L: {len(cand['L'])}종목 / Track S: {len(cand['S'])}종목")

    # --- 체결 ---
    pos, cash, px = load_positions(), load_cash(), {}
    ledger = []
    rebal = is_first_trading_day(store, asof)
    print(f"\n[6] 체결  (기준일 {asof.date()}, 월 첫 거래일: "
          f"{'예 -> Track L 신규편입' if rebal else '아니오 -> Track L 청산만'})")

    for p in list(pos):
        market = uni.get(p["code"]) or _market_of(store, p["code"])
        bars = store.bars(market, p["code"], asof) if market else None
        if bars is None:
            print(f"  [데이터부족] 보유 {p['name']}({p['code']}) 시세 없음 "
                  f"-> 청산 판정 보류 (임의 매도 금지)")
            continue
        close = float(bars["close"].iloc[-1])
        px[(p["track"], p["code"])] = close
        p["high_watermark"] = max(p["high_watermark"], close)
        p["days_held"] = int((bars["date"] > pd.Timestamp(p["entry_date"])).sum())

        atr = atr_wilder(bars["high"], bars["low"], bars["close"], CFG["ATR_N"])
        ma_s, _ = ma_and_slope(bars["close"], CFG["S"]["MA_SHORT"], CFG["S"]["SLOPE_DAYS"])
        ex = check_exit_core(p, close, atr, ma_s, CFG[p["track"]], p["track"])
        if not ex:
            continue
        action, reason, rule, qty = ex
        r_unit = p["entry_price"] - p["init_stop"]
        rmul = (close - p["entry_price"]) / r_unit if r_unit > 0 else float("nan")
        amount = close * qty
        cash[p["track"]] += amount
        ledger.append({"date": asof.date().isoformat(), "track": p["track"],
                       "code": p["code"], "name": p["name"], "action": action,
                       "price": round(close, 1), "qty": qty, "amount": round(amount, 0),
                       "reason": reason, "rule_fired": rule, "score": "",
                       "atr": round(atr, 2), "r_multiple": round(rmul, 3),
                       "realized_pnl": round((close - p["entry_price"]) * qty, 0)})
        print(f"  [{p['track']}] {action:10s} {p['name']}({p['code']}) {qty}주 "
              f"@{fmt_won(close)}  R={rmul:+.2f}  {rule}")
        if action == "SELL_TP":
            p["qty"] -= qty
            p["half_sold"] = 1
        else:
            pos.remove(p)

    held = {(p["track"], p["code"]) for p in pos}
    for track in ("L", "S"):
        if track == "L" and not rebal:
            continue
        cfg_t = CFG[track]
        slots = cfg_t["MAX_POSITIONS"] - sum(1 for p in pos if p["track"] == track)
        # ★ 2%룰은 '현재 자산'의 2% (안티-마틴게일). 초기자본 고정은 죽음의 나선.
        cap = cash[track] + sum(px.get((track, p["code"]), p["entry_price"]) * p["qty"]
                                for p in pos if p["track"] == track)

        _blocked = []      # 하순 필터로 보류된 종목 (소·중형만)
        for score, code, market in sorted(cand[track], key=lambda x: -x[0]):
            if slots <= 0:
                break
            if (track, code) in held:
                continue
            # ★ 하순 필터 — 종목별 시총 tier 로 판정. 대형주는 OOS 기각 -> 통과시킨다.
            if _late_ok and _late_block_fn(code):
                _blocked.append(code)
                continue
            bars = store.bars(market, code, asof)
            if bars is None:
                continue
            close = float(bars["close"].iloc[-1])
            atr = atr_wilder(bars["high"], bars["low"], bars["close"], CFG["ATR_N"])
            qty, stop, _, why = size_position(cap, close, atr, cfg_t["ATR_STOP"], exposure)
            amount = close * qty
            if qty <= 0 or amount > cash[track]:
                continue
            cash[track] -= amount
            r_unit = close - stop
            pos.append(dict(track=track, code=code, name=store.name(code),
                            entry_date=asof.date().isoformat(), entry_price=close,
                            qty=qty, stop=stop, init_stop=stop, target_1r=close + r_unit,
                            high_watermark=close, atr=atr, half_sold=0, days_held=0))
            px[(track, code)] = close
            held.add((track, code))
            slots -= 1
            ledger.append({
                "date": asof.date().isoformat(), "track": track, "code": code,
                "name": store.name(code), "action": "BUY", "price": round(close, 1),
                "qty": qty, "amount": round(amount, 0),
                "reason": f"{'20주선 위+기울기상승' if track=='L' else '20일선 위+기울기상승+상위정합'}"
                          f" / 점수 {score} / 노출x{exposure:.2f} / {why}",
                "rule_fired": f"진입({track}) 손절={fmt_won(stop)} 1R={fmt_won(close+r_unit)}",
                "score": score, "atr": round(atr, 2), "r_multiple": "", "realized_pnl": ""})
            print(f"  [{track}] BUY        {store.name(code)}({code}) {qty}주 "
                  f"@{fmt_won(close)}  손절 {fmt_won(stop)}  ({why})")

        if _blocked:
            _nm = ", ".join(f"{store.name(c)}({c})" for c in _blocked[:5])
            print(f"  [{track}] 진입보류    하순 구간 · 소·중형 {len(_blocked)}종목 — {_nm}"
                  f"{' 외' if len(_blocked) > 5 else ''}")
            print("             (대형주는 미적용 — 30년 OOS 기각 p=0.1211)")

    if not ledger:
        print("  체결 없음.")
    append_csv(DIR_LEDGER, "paper_ledger.csv", ledger, LEDGER_COLS)

    # --- 자산 ---
    print("\n[7] 자산")
    eq_rows, te, tc, tv = [], 0.0, 0.0, 0.0
    for track in ("L", "S"):
        tp = [p for p in pos if p["track"] == track]
        pv = sum(px.get((track, p["code"]), p["entry_price"]) * p["qty"] for p in tp)
        c = cash[track]
        eq = c + pv
        cap = CFG["INITIAL_CAPITAL"] * CFG["TRACK_ALLOC"][track]
        eq_rows.append({"date": asof.date().isoformat(), "track": track, "cash": round(c, 0),
                        "position_value": round(pv, 0), "total_equity": round(eq, 0),
                        "exposure_pct": round(pv / eq * 100, 2) if eq > 0 else 0.0,
                        "regime": regime, "coupling_state": crow["state"],
                        "data_source": store.used})
        te, tc, tv = te + eq, tc + c, tv + pv
        print(f"  Track {track}: 현금 {fmt_won(c)} + 보유 {fmt_won(pv)} = {fmt_won(eq)}원 "
              f"(초기 {fmt_won(cap)}, {fmt_pct(eq/cap-1)}) 보유 {len(tp)}종목")
    eq_rows.append({"date": asof.date().isoformat(), "track": "TOTAL", "cash": round(tc, 0),
                    "position_value": round(tv, 0), "total_equity": round(te, 0),
                    "exposure_pct": round(tv / te * 100, 2) if te > 0 else 0.0,
                    "regime": regime, "coupling_state": crow["state"],
                    "data_source": store.used})
    append_csv(DIR_LEDGER, "paper_equity.csv", eq_rows, EQ_COLS)
    save_positions(pos, px)
    print(f"  TOTAL  : {fmt_won(te)}원 (초기 {fmt_won(CFG['INITIAL_CAPITAL'])}, "
          f"{fmt_pct(te/CFG['INITIAL_CAPITAL']-1)}) 노출 {tv/te*100 if te else 0:.1f}%")

    # --- 성과 ---
    print("\n[8] 성과 요약 (원장 누적)")
    print(f"  {'트랙':<9}{'거래':>6}{'청산':>6}{'승률':>9}{'평균R':>9}{'손익비':>8}"
          f"{'실현손익':>13}{'수익률':>10}{'MDD':>10}")
    for track in ("L", "S", None):
        lab = f"Track {track}" if track else "합계"
        s = perf_summary(track)
        es = equity_stats(track if track else "TOTAL")
        if not s:
            print(f"  {lab:<9}  (거래 없음)")
            continue
        g = lambda v, sp: sp.format(v) if not isnan(v) else "-"
        print(f"  {lab:<9}{s['거래']:>6}{s['청산']:>6}{g(s['승률']*100,'{:.1f}%'):>9}"
              f"{g(s['평균R'],'{:+.3f}'):>9}{g(s['손익비'],'{:.2f}'):>8}"
              f"{fmt_won(s['실현손익']):>13}"
              f"{(fmt_pct(es['수익률']) if es else '-'):>10}"
              f"{(fmt_pct(es['MDD']) if es else '-'):>10}")

    print("\n[9] 산출물 (진우퀀트\\가상매매\\원장\\)")
    for fn in ("paper_ledger.csv", "paper_positions.csv", "paper_equity.csv",
               "paper_signals.csv", "coupling_history.csv"):
        ok = os.path.exists(os.path.join(DIR_LEDGER, fn))
        print(f"  {'[O]' if ok else '[X]'} {fn}")
    print("\n  -> 클로드(학습층)가 위 CSV를 읽고 평가·개선안·채택/기각을 판단한다.")
    print("  -> 이 엔진(실행기)은 규칙을 실행만 한다. 학습하지 않는다.")
    return 0


def _market_of(store, code):
    return store.market_of(code)


# ═══════════════════════════════════════════════════════════════════════════
# 셀프테스트
# ═══════════════════════════════════════════════════════════════════════════
def self_test():
    ok = tot = 0

    def chk(n, c):
        nonlocal ok, tot
        tot += 1
        ok += 1 if c else 0
        print(f"  [{'OK  ' if c else 'FAIL'}] {n}")

    print("=" * 78)
    print("가상매매 셀프테스트 (규칙은 jq_paper_core.py 단일 구현)")
    print("=" * 78)

    print("\n[사이징]")
    q, s, rps, cr = size_position(7_000_000, 10_000, 400, 2.5)
    chk(f"손절 = 10000-2.5x400 = 9,000 (실제 {fmt_won(s)})", abs(s - 9000) < 1e-6)
    chk(f"위험/주 = 1,000 (실제 {fmt_won(rps)})", abs(rps - 1000) < 1e-6)
    chk(f"종목상한 10%(70만) -> 70주 (실제 {q}주, {cr})", q == 70 and "상한" in cr)
    q2, s2, _, c2 = size_position(7_000_000, 10_000, 2_000, 2.5)
    chk(f"-20% 하드손절 하한 -> 8,000 (실제 {fmt_won(s2)})", abs(s2 - 8000) < 1e-6)
    chk(f"risk2% 경로 -> 70주 (실제 {q2}주, {c2})", q2 == 70 and c2 == "risk2%")
    q3, s3, _, _ = size_position(3_000_000, 10_000, 400, 1.5)
    chk(f"Track S 손절 = 10000-1.5x400 = 9,400 (실제 {fmt_won(s3)})", abs(s3 - 9400) < 1e-6)
    q4, _, _, _ = size_position(7_000_000, 10_000, 2_000, 2.5, exposure=0.5)
    chk(f"노출 0.5 -> 수량 절반 35주 (실제 {q4}주)", q4 == 35)
    r5 = size_position(7_000_000, 10_000, float("nan"), 2.5)
    chk("ATR 데이터부족 -> 0주 + '데이터부족'", r5[0] == 0 and r5[3] == "데이터부족")
    r6 = size_position(7_000_000, 0, 400, 2.5)
    chk("가격 이상 -> 0주 + '데이터부족'", r6[0] == 0 and r6[3] == "데이터부족")

    print("\n[지표 · 벡터화 동치성 — 백테스트 신뢰의 근거]")
    n = 80
    h = pd.Series([100.0 + i for i in range(n)])
    l, c = h - 2.0, h - 1.0
    a = atr_wilder(h, l, c, 14)
    chk(f"ATR(14) 계산 (={a:.3f})", not isnan(a) and a > 0)
    chk("봉 부족 -> NaN (추정 금지)", isnan(atr_wilder(h[:5], l[:5], c[:5], 14)))
    chk("★벡터화 ATR == 스칼라 ATR", abs(float(C.atr_series(h, l, c, 14).iloc[-1]) - a) < 1e-9)
    up = pd.Series(range(1, 101), dtype=float)
    ma, sl = ma_and_slope(up, 20, 5)
    chk(f"상승추세 -> 기울기>0 (={sl:.4f})", sl > 0)
    chk("하락추세 -> 기울기<0",
        ma_and_slope(pd.Series(range(100, 0, -1), dtype=float), 20, 5)[1] < 0)
    chk("봉 부족 -> NaN", isnan(ma_and_slope(up[:10], 20, 5)[0]))
    mv, sv = C.ma_slope_series(up, 20, 5)
    chk("★벡터화 MA/기울기 == 스칼라",
        abs(float(mv.iloc[-1]) - ma) < 1e-9 and abs(float(sv.iloc[-1]) - sl) < 1e-9)
    chk("20일선 = 20거래일 = 4주 (5주는 25일)", CFG["S"]["MA_SHORT"] == 20)

    print("\n[진입 필터]")
    chk("L: 20주선 위+기울기상승 -> 통과", passes_L(11_000, 10_000, 0.02)[0])
    chk("L: 20주선 아래 -> 탈락", passes_L(9_000, 10_000, 0.02)[1] == "20주선 아래")
    chk("L: 기울기 하락 -> 탈락", passes_L(11_000, 10_000, -0.01)[1] == "20주선 기울기 하락")
    chk("L: NaN -> 데이터부족", "데이터부족" in passes_L(11_000, float("nan"), 0.02)[1])
    chk("S: 20일선 위+기울기상승+상위정합 -> 통과", passes_S(11_000, 10_000, 0.01, True)[0])
    chk("S: 상위추세 역행 -> 진입금지",
        passes_S(11_000, 10_000, 0.01, False)[1] == "상위추세 역행(20주선 아래) — 진입금지")
    chk("S: 20일선 아래 -> 탈락", passes_S(9_000, 10_000, 0.01, True)[1] == "20일선 아래")
    chk("S: 기울기 하락 -> 탈락", passes_S(11_000, 10_000, -0.01, True)[1] == "20일선 기울기 하락")

    print("\n[청산 규칙 — 매도규칙서 v2]")
    ATR = 100.0
    mk = lambda track="L", entry=10_000, qty=10, init=9_750, hw=10_000, held=0: dict(
        track=track, code="000000", name="테스트", entry_date="2026-01-01",
        entry_price=entry, qty=qty, stop=init, init_stop=init,
        target_1r=entry + (entry - init), high_watermark=hw, atr=ATR,
        half_sold=0, days_held=held)
    L, S = CFG["L"], CFG["S"]
    r = check_exit_core(mk(), 9_700, ATR, None, L, "L")
    chk(f"손절 발동 (9,700 <= 9,750) -> {r[0] if r else None}", r and r[0] == "SELL_STOP")
    chk("손절 미발동 (9,800 > 9,750)", check_exit_core(mk(), 9_800, ATR, None, L, "L") is None)
    r = check_exit_core(mk(hw=12_000), 11_700, ATR, None, L, "L")
    chk(f"트레일링 발동 (고점12,000 -> 실효손절 11,750 > 11,700) -> {r[0] if r else None}",
        r and r[0] == "SELL_TRAIL")
    chk("트레일링 미발동 (11,800 > 11,750)",
        check_exit_core(mk(hw=12_000), 11_800, ATR, None, L, "L") is None)
    p = mk(hw=10_000)
    check_exit_core(p, 9_900, ATR, None, L, "L")
    chk(f"래칫: 실효손절 >= 초기손절 ({fmt_won(p['stop'])} >= 9,750)", p["stop"] >= 9_750 - 1e-6)
    r = check_exit_core(mk(held=20), 10_200, ATR, None, L, "L")
    chk(f"시간손절 발동 (20일, +2% 이내) -> {r[0] if r else None}", r and r[0] == "SELL_TIME")
    chk("시간손절 미발동 (+8% > 5% 밴드)",
        check_exit_core(mk(held=20), 10_800, ATR, None, L, "L") is None)
    chk("시간손절 미발동 (19일 < 20일)",
        check_exit_core(mk(held=19), 10_200, ATR, None, L, "L") is None)
    r = check_exit_core(mk(track="S", entry=11_500, init=9_000, hw=11_950),
                        11_000, ATR, 11_200, S, "S")
    chk(f"Track S 20일선 이탈 (11,000 < MA20 11,200) -> {r[0] if r else None}",
        r and r[0] == "SELL_MA")
    r = check_exit_core(mk(track="S", init=9_850, held=10), 10_150, ATR, 9_000, S, "S")
    chk(f"Track S 시간손절 (10일, +1.5% 이내) -> {r[0] if r else None}",
        r and r[0] == "SELL_TIME")
    chk("절반익절 기본 OFF (매도규칙서 v2) -> 미발동",
        check_exit_core(mk(), 10_300, ATR, None, L, "L", half_tp=False) is None)
    r = check_exit_core(mk(qty=10), 10_300, ATR, None, L, "L", half_tp=True)
    chk(f"절반익절 ON -> SELL_TP 5주 (실제 {r[0] if r else None}/{r[3] if r else 0}주)",
        r and r[0] == "SELL_TP" and r[3] == 5)
    chk("ATR 데이터부족 -> 판정 보류 (임의 매도 금지)",
        check_exit_core(mk(), 9_700, float("nan"), None, L, "L") is None)

    print("\n[규칙 우선순위]")
    chk("손절 > 시간손절",
        check_exit_core(mk(held=30), 9_700, ATR, None, L, "L")[0] == "SELL_STOP")
    chk("S: 20일선이탈 > 시간손절",
        check_exit_core(mk(track="S", init=9_000, hw=10_000, held=30),
                        9_500, ATR, 9_800, S, "S")[0] == "SELL_MA")

    print("\n[자본 분리]")
    chk("Track L 70% = 700만", abs(CFG["INITIAL_CAPITAL"] * CFG["TRACK_ALLOC"]["L"] - 7e6) < 1)
    chk("Track S 30% = 300만", abs(CFG["INITIAL_CAPITAL"] * CFG["TRACK_ALLOC"]["S"] - 3e6) < 1)
    chk("배분 합 = 100%", abs(sum(CFG["TRACK_ALLOC"].values()) - 1.0) < 1e-9)

    print("\n[커플링 — 기록 전용]")
    for v, want in [(0.7, "COUPLED_STRONG"), (0.6, "COUPLED_STRONG"), (0.45, "COUPLED"),
                    (0.0, "DECOUPLED"), (-0.3, "INVERSE"), (-0.5, "INVERSE")]:
        chk(f"라벨 {v} -> {want}", C.label_coupling(v) == want)
    chk("라벨 NaN -> 데이터부족", C.label_coupling(float("nan")) == "데이터부족")
    cp, _, _ = load_coupling_panel()
    chk(f"커플링 패널 로딩 ({len(cp) if cp is not None else 0}행)", cp is not None and len(cp) > 100)
    if cp is not None:
        cr2 = compute_coupling(cp["date"].max(), cp)
        chk(f"커플링 계산 (corr20={cr2['corr_20d_spx']} -> {cr2['state']})",
            cr2["state"] in ("COUPLED_STRONG", "COUPLED", "DECOUPLED", "INVERSE"))
        chk("나스닥 미보유 -> 공란 (가짜값 생성 안 함)", cr2["corr_20d_nasdaq"] == "")

    print("\n[국면(Phase) — 인과적]")
    idx, notes = C.load_kospi_index()
    chk(f"KOSPI 경로 로딩 ({len(idx) if idx is not None else 0}행)", idx is not None)
    if idx is not None:
        ph = C.phase_series(idx)
        chk(f"추세 국면 {ph['trend'].value_counts().to_dict()}",
            set(ph["trend"].unique()) <= {"BULL", "BEAR", "TRANSITION", "데이터부족"})
        chk("변동성 국면 라벨",
            set(ph["vol"].unique()) <= {"VOL_LOW", "VOL_MID", "VOL_HIGH", "데이터부족"})
        chk("드로다운 국면 라벨",
            set(ph["dd"].unique()) <= {"DD_NONE", "DD_CORRECTION", "DD_BEAR"})
        chk("MA200 미확정 초기구간 -> 데이터부족 (추정 금지)",
            (ph["trend"] == "데이터부족").sum() >= CFG["PHASE"]["MA_LONG"] - 1)

    print("\n[매크로 게이트]")
    mult, reg, _ = macro_gate(pd.Timestamp("2026-07-10"))
    chk(f"게이트 동작 (regime={reg}, 노출x{mult:.2f})", 0.0 <= mult <= 1.0)
    chk("regime 매핑에 '약세' 존재", "약세" in CFG["REGIME_EXPOSURE"])

    print("\n[포맷 · 데이터부족]")
    chk("천단위 콤마 format() (%-포맷 금지)", fmt_won(1234567.89) == "1,234,568")
    chk("NaN -> '데이터부족'",
        fmt_pct(float("nan")) == "데이터부족" and fmt_won(float("nan")) == "데이터부족")

    print("\n[영업일 보정 · 실데이터 · look-ahead]")
    st = PriceStore("local")
    if st.load_local():
        ld = st.last_date()
        chk(f"패널 최종 거래일 ({ld.date()})", ld is not None)
        chk("주말(2026-07-12 일) -> 마지막 거래일로 보정 가능", ld < pd.Timestamp("2026-07-12"))
        firsts = C.month_first_days(st)
        chk(f"월 첫 거래일 판정 ({len(firsts)}개월)", len(firsts) > 60)
        chk("월 첫 거래일 = 그 달 최초 실거래일 (달력 1일 아님)",
            is_first_trading_day(st, list(firsts.values())[5]))
        b = st.bars("KOSPI", "005930", pd.Timestamp("2026-07-10"))
        chk(f"삼성전자 봉 조회 ({len(b) if b is not None else 0}봉)", b is not None and len(b) > 100)
        chk("봉에 open 포함 (익일시가 체결용)", b is not None and "open" in b.columns)
        chk("★look-ahead 차단: bars(asof) 최종일 <= asof",
            b is not None and b["date"].max() <= pd.Timestamp("2026-07-10"))
        b2 = st.bars("KOSPI", "005930", pd.Timestamp("2024-01-15"))
        chk("★과거 시점 조회 시 미래 봉 미포함",
            b2 is not None and b2["date"].max() <= pd.Timestamp("2024-01-15"))
    else:
        chk("로컬 패널 로딩", False)

    print(f"\n{'='*78}")
    print(f"셀프테스트: {ok}/{tot} 통과")
    print("=" * 78)
    return 0 if ok == tot else 1


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--self-test", action="store_true")
    ap.add_argument("--source", default="auto", choices=["auto", "local", "pykrx"])
    ap.add_argument("--asof", default=None)
    ap.add_argument("--halloween", action="store_true")
    ap.add_argument("--half-tp", action="store_true")
    ap.add_argument("--no-late-filter", action="store_true",
                    help="하순(월말 −9~−5거래일) 신규진입 보류 필터 해제 (기본 ON)")
    a = ap.parse_args()
    CFG["HALLOWEEN"] = bool(a.halloween)
    CFG["HALF_TP"] = bool(a.half_tp)

    log = RunLogger("가상매매_엔진.py", vars(a))
    rc = 1
    try:
        rc = self_test() if a.self_test else run(a)
        log.close()
    except Exception as e:
        log.close(err=e)
        rc = 1
    sys.exit(rc)
