#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
tier1_risk_rules.py — 진우퀀트 티어1 리스크 규칙 엔진 (2026-06-07)

티어1(지금 바로 룰화): ① 본체 MDD 메타룰  ② 테마 lane 행동규칙
   (진입가드 · 분할 · 집중한도 · 킬스위치). 모두 백테스트/일봉 불필요한 '행동 규칙'.
티어2 헬퍼(실거래 시점): position_size() — 2%룰+ATR 사이징(동봉, 표시).

설계: production 무수정 · 신규 파일만. 설정은 risk_rules.yaml(없으면 내장 기본값).
   본체 MDD는 live_tracker.py가 남기는 live_record.csv(date,port_ret_pct,kospi_ret_pct)를 읽음.

사용:
  python tier1_risk_rules.py --self-test
  python tier1_risk_rules.py --check-mdd                 # live_record.csv로 현재 상태 판정
  python tier1_risk_rules.py --check-mdd --record live_record.csv
  python tier1_risk_rules.py --demo                      # 테마 진입체크 예시
"""
import argparse, csv, os, sys

DEFAULTS = {
    "본체": {"MDD_메타룰": {"경보_월수익": -0.10, "축소_낙폭": -0.18, "백테스트_MDD": -0.1221}},
    "테마": {
        "진입가드": {"급등보류_pct": 0.10, "VI상한가_신규금지": True},
        "분할": {"정찰비율": 0.33, "1차익절": 0.5},
        "집중한도": {"lane총비중": 0.20, "동일테마_종목수": 2, "동일테마_비중": 0.40,
                  "1종목_비중_of_lane": 0.25, "보유수": 5},
        "킬스위치": {"월손실": -0.15, "분기손실": -0.25},
        "사이징": {"리스크_per_trade": 0.02, "k_ATR": 3.0, "하한가_손절상한": -0.20,
                "주문_ADTV_비율": 0.01},
    },
}


def load_config(path="risk_rules.yaml"):
    """yaml 있으면 로드, 없으면 내장 기본값. (pyyaml 미설치/파일부재에도 동작)"""
    if path and os.path.exists(path):
        try:
            import yaml
            with open(path, encoding="utf-8") as fh:
                cfg = yaml.safe_load(fh)
            if cfg:
                return cfg
        except Exception as e:
            print("[경고] %s 로드 실패(%s) → 내장 기본값 사용" % (path, e), file=sys.stderr)
    return DEFAULTS


# ============ ① 본체 MDD 메타룰 ============
def mdd_state(monthly_returns, cfg):
    """
    monthly_returns: 월수익률(소수) 리스트(시간순). live_record.csv의 port_ret_pct/100.
    반환: dict(state, dd, last, msg). state ∈ {정상, 경보, 축소}.
    """
    r = list(monthly_returns)
    m = cfg["본체"]["MDD_메타룰"]
    if not r:
        return {"state": "정상", "dd": 0.0, "last": None, "msg": "기록 없음"}
    eq = 1.0; peak = 1.0; dd = 0.0
    for x in r:
        eq *= (1 + x); peak = max(peak, eq); dd = min(dd, eq / peak - 1)
    last = r[-1]
    state, msgs = "정상", []
    if dd <= m["축소_낙폭"]:
        state = "축소"; msgs.append("누적낙폭 %.1f%% ≤ 축소선 %.1f%% → 노출축소·전수점검"
                                  % (dd * 100, m["축소_낙폭"] * 100))
    if last <= m["경보_월수익"]:
        if state != "축소":
            state = "경보"
        msgs.append("최근월 %.1f%% ≤ 경보선 %.1f%% → 점검 플래그"
                    % (last * 100, m["경보_월수익"] * 100))
    if not msgs:
        msgs.append("정상 (누적낙폭 %.1f%%, 최근월 %.1f%%)" % (dd * 100, last * 100))
    return {"state": state, "dd": dd, "last": last, "msg": "; ".join(msgs)}


def load_record(path):
    if not os.path.exists(path):
        return []
    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    return [float(r["port_ret_pct"]) / 100.0 for r in rows]


# ============ ② 테마 lane 진입 체크 ============
def check_theme_entry(cfg, lane_state, candidate):
    """
    lane_state: {
        total_capital, holdings: [{code, theme, weight_total}],
        lane_pnl_month, lane_pnl_quarter   # 소수(예: -0.16)
    }
    candidate: {
        code, theme, recent_move_pct,      # 직전봉 대비(소수)
        vi_or_limit(bool), proposed_weight_total(소수), stop_pct(소수, 예 -0.18)
    }
    반환: {decision ∈ ALLOW/HOLD/BLOCK, reasons:[...]}
    """
    g = cfg["테마"]["진입가드"]; lim = cfg["테마"]["집중한도"]
    ks = cfg["테마"]["킬스위치"]; sz = cfg["테마"]["사이징"]
    H = lane_state.get("holdings", [])
    cap = lane_state.get("total_capital", 1.0)
    reasons = []; decision = "ALLOW"

    def block(msg):
        nonlocal decision; decision = "BLOCK"; reasons.append("BLOCK: " + msg)
    def hold(msg):
        nonlocal decision
        if decision != "BLOCK": decision = "HOLD"
        reasons.append("HOLD: " + msg)

    # 킬스위치 (최우선)
    if lane_state.get("lane_pnl_quarter", 0) <= ks["분기손실"]:
        block("분기 손실 %.0f%% ≤ %.0f%% (전량 점검·신규금지)"
              % (lane_state["lane_pnl_quarter"] * 100, ks["분기손실"] * 100))
    if lane_state.get("lane_pnl_month", 0) <= ks["월손실"]:
        block("월 손실 %.0f%% ≤ %.0f%% (당월 신규정지)"
              % (lane_state["lane_pnl_month"] * 100, ks["월손실"] * 100))

    # 진입가드
    if candidate.get("vi_or_limit") and g["VI상한가_신규금지"]:
        block("VI발동/상한가 호가 → 신규진입 금지")
    if candidate.get("recent_move_pct", 0) >= g["급등보류_pct"]:
        hold("직전봉 +%.0f%% ≥ 급등보류 %.0f%% → 당일 보류"
             % (candidate["recent_move_pct"] * 100, g["급등보류_pct"] * 100))

    # 하한가 손절여유
    sp = candidate.get("stop_pct")
    if sp is not None and sp < sz["하한가_손절상한"]:
        block("손절폭 %.0f%% < 상한 %.0f%% (하한가 체결불가 위험) → 스킵/−20%%고정"
              % (sp * 100, sz["하한가_손절상한"] * 100))

    # 집중한도
    if len(H) >= lim["보유수"]:
        block("보유 %d종목 ≥ 한도 %d" % (len(H), lim["보유수"]))
    same = [h for h in H if h["theme"] == candidate["theme"]]
    if len(same) + 1 > lim["동일테마_종목수"]:
        block("동일테마(%s) %d→%d > 한도 %d"
              % (candidate["theme"], len(same), len(same) + 1, lim["동일테마_종목수"]))
    pw = candidate.get("proposed_weight_total", 0)
    same_w = sum(h["weight_total"] for h in same) + pw
    lane_w = sum(h["weight_total"] for h in H) + pw
    if pw > lim["1종목_비중_of_lane"] * lim["lane총비중"] + 1e-9:
        block("1종목 비중 %.1f%% > %.1f%%(총자산)"
              % (pw * 100, lim["1종목_비중_of_lane"] * lim["lane총비중"] * 100))
    if same_w > lim["동일테마_비중"] * lim["lane총비중"] + 1e-9:
        block("동일테마 비중 %.1f%% > lane40%% (=총자산 %.1f%%)"
              % (same_w * 100, lim["동일테마_비중"] * lim["lane총비중"] * 100))
    if lane_w > lim["lane총비중"] + 1e-9:
        block("lane 합계 %.1f%% > 한도 %.0f%%" % (lane_w * 100, lim["lane총비중"] * 100))

    if not reasons:
        reasons.append("ALLOW: 모든 게이트 통과")
    return {"decision": decision, "reasons": reasons}


# ============ 티어2 헬퍼: 2%룰 + ATR 사이징 ============
def position_size(cfg, lane_capital, atr, entry, adtv):
    """[티어2] 실거래 시점용. 손절거리=k×ATR, 리스크=2%×lane자본. shares 반환(+진단)."""
    sz = cfg["테마"]["사이징"]
    stop_dist = sz["k_ATR"] * atr
    stop_pct = -stop_dist / entry
    risk = sz["리스크_per_trade"] * lane_capital
    shares = int(risk // stop_dist) if stop_dist > 0 else 0
    cap_shares = int((sz["주문_ADTV_비율"] * adtv) // entry) if entry > 0 else shares
    shares = min(shares, cap_shares)
    skip = stop_pct < sz["하한가_손절상한"]
    return {"shares": shares, "stop_pct": stop_pct, "adtv_capped": shares == cap_shares,
            "skip_하한가": skip}


# ============ self-test ============
def _self_test():
    ok = tot = 0
    def chk(n, c):
        nonlocal ok, tot; tot += 1; ok += bool(c)
        print(("  [%s] " % ("OK" if c else "XX")) + n)
    cfg = DEFAULTS

    # MDD: 정상 / 경보(최근월) / 축소(누적낙폭)
    s = mdd_state([0.05, 0.03, 0.04], cfg); chk("MDD 정상", s["state"] == "정상")
    s = mdd_state([0.05, -0.12], cfg); chk("MDD 경보(최근월 -12%)", s["state"] == "경보")
    s = mdd_state([-0.1, -0.1, -0.05], cfg); chk("MDD 축소(누적낙폭<-18%)", s["state"] == "축소")

    base_lane = {"total_capital": 1.0, "holdings": [], "lane_pnl_month": 0, "lane_pnl_quarter": 0}
    cand = {"code": "x", "theme": "로봇", "recent_move_pct": 0.02,
            "vi_or_limit": False, "proposed_weight_total": 0.04, "stop_pct": -0.15}
    chk("정상진입 ALLOW", check_theme_entry(cfg, base_lane, cand)["decision"] == "ALLOW")

    chk("VI 신규금지 BLOCK",
        check_theme_entry(cfg, base_lane, {**cand, "vi_or_limit": True})["decision"] == "BLOCK")
    chk("급등 +12% HOLD",
        check_theme_entry(cfg, base_lane, {**cand, "recent_move_pct": 0.12})["decision"] == "HOLD")
    chk("손절폭 -25% BLOCK(하한가)",
        check_theme_entry(cfg, base_lane, {**cand, "stop_pct": -0.25})["decision"] == "BLOCK")

    # 동일테마 3번째 BLOCK
    lane2 = {**base_lane, "holdings": [{"code": "a", "theme": "바이오", "weight_total": 0.04},
                                       {"code": "b", "theme": "바이오", "weight_total": 0.04}]}
    chk("동일테마 3종목 BLOCK",
        check_theme_entry(cfg, lane2, {**cand, "theme": "바이오"})["decision"] == "BLOCK")

    # 1종목 비중 6% > 5% BLOCK
    chk("1종목 6% BLOCK",
        check_theme_entry(cfg, base_lane, {**cand, "proposed_weight_total": 0.06})["decision"] == "BLOCK")

    # 킬스위치 월손실 BLOCK
    chk("월손실 -16% BLOCK",
        check_theme_entry(cfg, {**base_lane, "lane_pnl_month": -0.16}, cand)["decision"] == "BLOCK")

    # 보유수 5 BLOCK
    full = {**base_lane, "holdings": [{"code": str(i), "theme": "t%d" % i, "weight_total": 0.02}
                                      for i in range(5)]}
    chk("보유 5종목 BLOCK", check_theme_entry(cfg, full, cand)["decision"] == "BLOCK")

    # 사이징: entry 1000, atr 50, k3 → stop_dist150, stop_pct -15%, risk 2%
    ps = position_size(cfg, 1_000_000, 50, 1000, adtv=1e12)
    chk("사이징 stop_pct≈-15%", abs(ps["stop_pct"] + 0.15) < 1e-6)
    chk("사이징 shares=floor(20000/150)=133", ps["shares"] == 133)
    ps2 = position_size(cfg, 1_000_000, 120, 1000, adtv=1e12)  # stop -36% → skip
    chk("사이징 -36% skip플래그", ps2["skip_하한가"] is True)

    print("\nself-test: %d/%d 통과" % (ok, tot))
    return ok == tot


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--config", default="risk_rules.yaml")
    ap.add_argument("--record", default="live_record.csv")
    ap.add_argument("--check-mdd", action="store_true")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--self-test", action="store_true")
    a = ap.parse_args()
    if a.self_test:
        sys.exit(0 if _self_test() else 1)
    cfg = load_config(a.config)
    if a.check_mdd:
        r = load_record(a.record)
        s = mdd_state(r, cfg)
        print("=== 본체 MDD 메타룰 (%s, %d개월) ===" % (a.record, len(r)))
        print("상태: [%s]  %s" % (s["state"], s["msg"]))
        if s["state"] == "축소":
            print(">> 조치: 노출 축소 + 전수 점검 (백테스트 대비 낙폭 과다)")
        elif s["state"] == "경보":
            print(">> 조치: 점검 플래그 — 다음 리밸런스서 원인 확인")
        return
    if a.demo:
        lane = {"total_capital": 1.0,
                "holdings": [{"code": "247540", "theme": "2차전지", "weight_total": 0.04}],
                "lane_pnl_month": -0.03, "lane_pnl_quarter": -0.05}
        cand = {"code": "277810", "theme": "로봇", "recent_move_pct": 0.13,
                "vi_or_limit": False, "proposed_weight_total": 0.04, "stop_pct": -0.17}
        res = check_theme_entry(cfg, lane, cand)
        print("=== 테마 진입체크 데모 ===\n결정: [%s]" % res["decision"])
        for r in res["reasons"]:
            print("  -", r)
        return
    ap.print_help()


if __name__ == "__main__":
    main()
