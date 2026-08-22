# -*- coding: utf-8 -*-
r"""시장국면.py — 휩쏘 신호를 '실행'할지 '관찰만'할지 시장국면으로 판정.

[근거] 30년 역사검정(휩쏘_역사검정_판정문.md):
   · 시장(지수) 1년 고점 대비 낙폭 ≥ −12% 또는 고변동 → 휩쏘 A 유효(+8.5%·승57%)
   · 시장 고점권(0~−5%) & 저변동 → 휩쏘 떠도 짐(−5.9%·승36%)  ← 함정
   ⇒ 국면이 신호를 뒤집는다. 이 모듈이 그 게이트.

[사용]  py 시장국면.py                 (오늘 국면)
        py 시장국면.py --date 20260730
        from 시장국면 import regime_at ; r = regime_at("2026-07-30")
"""
import os, sys, argparse
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass


def _find(fn):
    for d in (HERE, os.path.join(HERE, "데이터수리"), os.path.dirname(HERE), os.getcwd()):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    return None


def _index():
    p = _find("kospi_index_daily.csv")
    if not p:
        return None
    ix = pd.read_csv(p); ix.columns = [c.strip().lstrip("﻿") for c in ix.columns]
    ix["Date"] = pd.to_datetime(ix["Date"])
    ix = ix.sort_values("Date").reset_index(drop=True)
    c = ix["Close"].astype(float)
    ix["mdd252"] = c / c.rolling(252, min_periods=120).max() - 1
    ret = c.pct_change()
    ix["vol20"] = ret.rolling(20, min_periods=10).std() * np.sqrt(252)
    ix["ma200"] = c.rolling(200, min_periods=100).mean()
    ix["_volmed"] = ix["vol20"].median()
    return ix


def regime_at(asof=None):
    """asof: 'YYYY-MM-DD' 또는 None(최신). 반환 dict: 판정/이유/수치."""
    ix = _index()
    if ix is None:
        return {"판정": "?", "이유": "kospi_index_daily.csv 없음 — 국면 게이트 불가", "실행": True}
    if asof:
        ix = ix[ix["Date"] <= pd.to_datetime(asof)]
    if len(ix) == 0:
        return {"판정": "?", "이유": "해당일 이전 지수 없음", "실행": True}
    r = ix.iloc[-1]
    mdd = float(r["mdd252"]); vol = float(r["vol20"]); volmed = float(r["_volmed"])
    bull = bool(r["Close"] > r["ma200"]) if np.isfinite(r["ma200"]) else None
    volhi = np.isfinite(vol) and vol > volmed

    # 게이트 (역사검정 승리 셀 = 시장낙폭 -12%↓ 또는 고변동 / 함정 = 고점권&저변동)
    if np.isfinite(mdd) and mdd <= -0.12:
        판정, 실행 = "실행(유리)", True
        이유 = f"시장 1년고점 대비 {mdd*100:+.0f}% (−12%↓) — 역발상 진입 유리 국면"
    elif volhi and np.isfinite(mdd) and mdd <= -0.05:
        판정, 실행 = "실행(유리)", True
        이유 = f"고변동 + 시장 조정({mdd*100:+.0f}%) — 유리 국면"
    elif np.isfinite(mdd) and mdd >= -0.05 and not volhi:
        판정, 실행 = "관찰만(불리)", False
        이유 = f"시장 고점권({mdd*100:+.0f}%) & 저변동 — 휩쏘 함정 국면(역사 −5.9%·승36%). 사지 말 것."
    else:
        판정, 실행 = "주의(중립)", True
        이유 = f"시장낙폭 {mdd*100:+.0f}% · {'고변동' if volhi else '저변동'} — 중립. 신중 진입."
    return {"판정": 판정, "실행": 실행, "이유": 이유, "mdd252": mdd,
            "vol20": vol, "volmed": volmed, "고변동": bool(volhi), "강세": bull,
            "date": str(r["Date"].date())}


def banner(asof=None):
    r = regime_at(asof)
    mark = "🟢" if r.get("실행") else "🟡" if "주의" in r["판정"] else "🔴"
    line = f" {mark} 시장국면 [{r.get('date','?')}] : {r['판정']} — {r['이유']}"
    return line, r


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default=None)
    a = ap.parse_args()
    asof = f"{a.date[:4]}-{a.date[4:6]}-{a.date[6:]}" if a.date else None
    line, r = banner(asof)
    print("=" * 78); print(line); print("=" * 78)
    if r.get("mdd252") is not None:
        print(f"   지수 1년고점比 {r['mdd252']*100:+.1f}% · 20일변동성 {r['vol20']*100:.1f}%"
              f"(중앙 {r['volmed']*100:.1f}%) · {'강세' if r.get('강세') else '약세' if r.get('강세') is not None else '?'}")
    print("   규칙: 실행=휩쏘 A 진입 유리 · 관찰만=신호 떠도 사지 않음 · 주의=신중.")
    print("   근거: 휩쏘_역사검정_판정문.md (30년)")


if __name__ == "__main__":
    main()
