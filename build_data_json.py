"""
build_data_json.py — 통합 허브용 data.json 어댑터 (2026-06-13)

블루프린트 통합-0: 엔진들이 만든 실데이터를 **한 개 data.json**으로 모은다(허브는 계산 0, 읽어 그리기만).
**실존 데이터만** 사용: 지수일봉(KS11·KQ11, MA200) + 시스템 점수CSV + 테마 게이트(일봉) + Track W ledger.
**KOSPI+KOSDAQ 양 시장**: market=두 지수 / system=KOSPI11+KOSDAQ2(알테오젠·ISC) / theme=KOSDAQ.
무수정: 기존 산출물 읽기만. 데이터 없으면 그 키는 null + 사유.

사용: python build_data_json.py   (→ data.json) / --selftest
"""
import argparse, os, sys, json
import pandas as pd, numpy as np

DAILY = "kosdaq_theme_daily.csv"   # KS11/KQ11 + 테마 일봉(code,date,ohlc)
SCORE = "v37_2_scores_latest.csv"  # 종목,코드,...,등급,권장비중_%
THEME_DAILYS = ["kosdaq_theme_daily.csv", "kosdaq_pit_daily_pykrx.csv", "kosdaq_pit_daily.csv"]
LEDGER = "trackw_ledger.csv"
THEME_WATCH = {"087010": "펩트론", "089030": "테크윙", "095610": "테스"}
W_HELD = {"353200": "대덕전자"}


def _load_daily(f):
    d = pd.read_csv(f, low_memory=False); d.columns = [c.strip().lstrip("﻿") for c in d.columns]
    d["code"] = d["code"].astype(str); d["date"] = pd.to_datetime(d["date"]); return d


def _index_block(daily, idx):
    s = daily[daily["code"] == idx].sort_values("date")
    if len(s) < 1:
        return None
    c = s.set_index("date")["close"].astype(float)
    last = float(c.iloc[-1]); d = c.index[-1]
    ma200 = float(c.tail(200).mean()) if len(c) >= 200 else None
    mtd = None
    mstart = c[c.index < d.replace(day=1)]
    if len(mstart):
        mtd = last / float(mstart.iloc[-1]) - 1
    return dict(code=idx, asof=str(d.date()), close=round(last, 2),
                ma200=(round(ma200, 2) if ma200 else None),
                ma200_state=(None if ma200 is None else ("위" if last >= ma200 else "아래")),
                mtd=(round(mtd, 4) if mtd is not None else None))


def _gate(code, srcs):
    best = None
    for d in srcs:
        s = d[d["code"].astype(str).str.zfill(6) == code]
        if len(s) >= 200:
            s = s.sort_values("date")
            if best is None or s["date"].max() > best["date"].max(): best = s
    if best is None:
        return None
    px = best.set_index("date")["close"].astype(float); hi = best.set_index("date")["high"].astype(float)
    last = px.iloc[-1]; dt = px.index[-1]
    p12 = px[px.index <= dt - pd.Timedelta(days=340)]
    ret12 = last / p12.iloc[-1] - 1 if len(p12) else None
    hi52 = hi[hi.index >= dt - pd.Timedelta(days=370)].max(); prox = last / hi52
    pg = (ret12 is not None and ret12 < 1.0 and prox < 0.95)
    return dict(asof=str(dt.date()), close=round(float(last)),
                ret12=(round(float(ret12), 3) if ret12 is not None else None),
                prox=round(float(prox), 3), gate=("PASS" if pg else "LATE"))


def build(daily_csv=DAILY, score_csv=SCORE, ledger=LEDGER):
    out = {"asof": None, "market": {}, "system": {}, "theme": {}, "trackw": {}, "_notes": []}
    # market — 양 지수 MA200
    if os.path.exists(daily_csv):
        daily = _load_daily(daily_csv)
        out["market"]["kospi"] = _index_block(daily, "KS11")
        out["market"]["kosdaq"] = _index_block(daily, "KQ11")
        if out["market"]["kospi"]:
            out["asof"] = out["market"]["kospi"]["asof"]
    else:
        out["_notes"].append(f"{daily_csv} 없음 → market null")
    # system — 점수 CSV S+/S/A
    if os.path.exists(score_csv):
        sc = pd.read_csv(score_csv, dtype=str)
        gcol = "등급" if "등급" in sc.columns else None
        wcol = [c for c in sc.columns if "권장비중" in c]
        picks = []
        for _, r in sc.iterrows():
            if gcol and r.get(gcol) in ("S+", "S", "A"):
                picks.append(dict(name=r.get("종목", "?"), code=str(r.get("코드", "")).zfill(6),
                                  grade=r.get(gcol), w=(float(r[wcol[0]]) if wcol and r.get(wcol[0]) else None)))
        out["system"] = dict(picks=picks, n=len(picks),
                             note=f"score_csv={score_csv} (운영시 docs/v37_2_scores.csv 최신본)")
    else:
        out["_notes"].append(f"{score_csv} 없음 → system null")
    # theme — 워치리스트 게이트
    srcs = [_load_daily(f) for f in THEME_DAILYS if os.path.exists(f)]
    watch = []
    for code, nm in THEME_WATCH.items():
        g = _gate(code, srcs) if srcs else None
        watch.append(dict(name=nm, code=code, **(g or {"gate": "데이터없음"})))
    wsat = []
    for code, nm in W_HELD.items():
        g = _gate(code, srcs) if srcs else None
        wsat.append(dict(name=nm, code=code, track="W위성", **(g or {"gate": "데이터없음"})))
    out["theme"] = dict(watch=watch, w_satellite=wsat,
                        note="gate=선반영(과열) 필터·매수신호 아님. 매수일 호가 재확인.")
    # trackw — ledger
    if os.path.exists(ledger):
        lg = []
        with open(ledger, encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and not line.startswith("month"):
                    p = line.split(",")
                    lg.append(dict(month=p[0], W=p[1] or None, sys=p[2] or None, themeEW=p[3] or None))
        out["trackw"] = dict(months=lg, recorded=sum(1 for m in lg if m["W"]),
                            note="6월말 첫 기입 — trackw_compute.py로 sys/themeEW 자동, W는 진우")
    return out


def _selftest():
    out = build()
    for k in ("asof", "market", "system", "theme", "trackw"):
        assert k in out, f"키 누락 {k}"
    assert "kospi" in out["market"] and "kosdaq" in out["market"], "양 시장 누락"
    print("[OK] build_data_json self-test — 필수키·양시장(KS11·KQ11) 존재")
    return 0


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="data.json")
    ap.add_argument("--selftest", action="store_true")
    a = ap.parse_args()
    if a.selftest:
        return _selftest()
    out = build()
    with open(a.out, "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=1)
    print(f"→ {a.out} 작성. asof={out['asof']} / 시스템픽 {out['system'].get('n','?')} / Track W 기록 {out['trackw'].get('recorded','?')}개월")
    return 0


if __name__ == "__main__":
    sys.exit(main() or 0)
