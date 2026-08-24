# -*- coding: utf-8 -*-
r"""kosdaq_ca_diag.py — 조정본 잔여 CA 진단 + ca_guard 윈저 민감도 (KOSDAQ/KOSPI 비교)

목적: 수정주가 조정본에도 남은 정수배 점프(KOSPI 320 · KOSDAQ 863)가 '크기(수익률)' 결론을
      뒤집을 수 있는지 정량화한다. 레벨을 재추정하지 않고, 되돌림(가짜)만 결측 + 월별 윈저.
왜 KOSDAQ이 문제였나: 그라운드트루스 참조파일이 없어 검증 ②를 스킵했고, 잔여 점프가
      KOSPI의 2.7배였다. 표본조사에선 93%가 영구(진짜 CA)였지만 '나머지 7%'가 크기를 흔들 수
      있으므로, 크기 작업에는 이 가드를 **항상 병행**한다.
사용: py 데이터수리\kosdaq_ca_diag.py [--from 2015-01] [--to 2026-06]
⚠️ 정보·검증용 · 투자자문 아님. 백테는 실현손익 아님.
"""
import os, sys, argparse, warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ca_guard import (classify_jumps, contaminated_keys, guard_returns, sensitivity,
                      assert_adjusted)

BASE = os.path.dirname(os.path.abspath(__file__))

def load(market):
    p = os.path.join(BASE, f"_월봉종가캐시_{market}_adj.csv")
    if not os.path.exists(p): return None
    d = pd.read_csv(p, dtype={"code": str})
    d["code"] = d["code"].str.zfill(6)
    # 적재 가드: 파일명이 `_adj`라는 것은 조정본이라는 증거가 아니다(2026-07-26 오염 사고).
    assert_adjusted(d, market, where=os.path.basename(p))
    return d

def diag(market, lo, hi):
    px = load(market)
    if px is None:
        print(f"[{market}] 캐시 없음 — 스킵"); return None
    px = px[(px["ym"] >= lo) & (px["ym"] <= hi)].copy()
    months = sorted(px["ym"].unique())
    print(f"\n{'='*70}\n[{market}] {lo}~{hi} · {px['code'].nunique():,}종목 · {len(months)}개월 · {len(px):,}행")

    # ① 잔여 점프 분류
    cj = classify_jumps(px)
    n_all = len(cj); n_rev = int((cj["kind"] == "reverting").sum()); n_per = n_all - n_rev
    print(f"① 잔여 정수배 점프 {n_all:,}건 → 영구(진짜 CA 의심) {n_per:,} · 되돌림(가짜 의심) {n_rev:,}"
          f" ({(n_rev/n_all*100 if n_all else 0):.1f}%)")

    # ② 월수익 패널 만들고 가드 적용 (ret 규약: ret(ym)=close(ym)/close(ym-1)-1)
    w = px.pivot_table(index="ym", columns="code", values="close", aggfunc="last").sort_index()
    ret = w.pct_change().stack().rename("ret").reset_index()
    bad = contaminated_keys(cj, convention="ret", months=months)
    print(f"② 결측 처리할 오염 셀 {len(bad):,}개 / 전체 {len(ret):,}개 ({len(bad)/max(len(ret),1)*100:.3f}%)")

    # ③ 민감도: 원본 vs 윈저만 vs 가드
    s = sensitivity(ret, ret_col="ret", by="ym", code_col="code", bad_pairs=bad)
    print("③ 동일가중 월수익 민감도 (결론이 가드에 의존하는가?)")
    print(s.to_string(index=False))

    # ④ 효과 분해 — '윈저(꼬리)'와 'CA 되돌림 결측' 중 무엇이 크기를 움직이나
    from ca_guard import winsor_returns
    wr = winsor_returns(ret, ret_col="ret", by="ym")
    g = guard_returns(ret, ret_col="ret", by="ym", code_col="code", bad_pairs=bad)
    def ann(col, src):
        m = src.groupby("ym")[col].mean().dropna()
        return (1 + m).prod() ** (12 / len(m)) - 1 if len(m) else np.nan
    a_raw, a_w, a_g = ann("ret", ret), ann("ret_w", wr), ann("ret_g", g)
    print(f"④ 동일가중 연율 CAGR 분해: 원본 {a_raw*100:.2f}% → 윈저만 {a_w*100:.2f}% → 가드 {a_g*100:.2f}%")
    print(f"   · 꼬리(윈저) 기여 {(a_w-a_raw)*100:+.2f}%p   · CA 되돌림 결측 기여 {(a_g-a_w)*100:+.2f}%p")
    dom = "꼬리(극단 수익률)" if abs(a_w - a_raw) > abs(a_g - a_w) else "CA 되돌림"
    print(f"   판정: 크기를 흔드는 주범 = **{dom}** → 크기 주장에는 월별 윈저가 필수, CA 결측은 소액 안전망")

    # ⑤ 대형주 한정 재검 — 이전 크기 백테(top30 대형주)가 이 꼬리에 노출됐나
    # ⚠️ 2026-07-27 수정: 초판은 **당월** 시총 랭크로 종목을 골라 미래참조였다.
    #    (당월 시총이 top300 = 그달에 오른 종목을 사후에 고르는 것) 실측 프리미엄
    #    KOSPI +10.46%p · KOSDAQ +43.75%p — KOSDAQ top300 46.83%의 정체가 이것이었다.
    #    선택은 반드시 **전월** 시총 랭크로 한다. 근거: 데이터수리/survivor_probe.py
    mp = os.path.join(BASE, "종목시총_30년_backfill.csv")
    if os.path.exists(mp):
        mc = pd.read_csv(mp, dtype={"code": str}, usecols=["code", "ym", "mcap"])
        mc["code"] = mc["code"].str.zfill(6)
        mc = mc[(mc["ym"] >= lo) & (mc["ym"] <= hi)]
        mc["rk"] = mc.groupby("ym")["mcap"].rank(ascending=False, method="first")
        nxt = {m: months[i + 1] for i, m in enumerate(months[:-1])}
        mc["ym"] = mc["ym"].map(nxt)          # 전월 시총 → 당월 선택에 사용
        mc = mc.dropna(subset=["ym"])
        big = set(zip(mc.loc[mc["rk"] <= 300, "code"], mc.loc[mc["rk"] <= 300, "ym"]))
        sel = pd.Series(list(zip(ret["code"], ret["ym"])), index=ret.index).isin(big)
        rb = ret[sel].copy()
        if len(rb) > 1000:
            wb = winsor_returns(rb, ret_col="ret", by="ym")
            b_raw, b_w = ann("ret", rb), ann("ret_w", wb)
            print(f"⑤ 시총 top300 한정({len(rb):,}셀): 원본 {b_raw*100:.2f}% → 윈저 {b_w*100:.2f}% "
                  f"(차이 {(b_w-b_raw)*100:+.2f}%p) → 대형주는 꼬리 노출 "
                  f"{'작음(기존 크기결과 강건)' if abs(b_w-b_raw)<0.02 else '있음(재검 필요)'}")
    return {"market": market, "jumps": n_all, "reverting": n_rev, "cells_dropped": len(bad),
            "cagr_raw": a_raw, "cagr_winsor": a_w, "cagr_guard": a_g}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--from", dest="lo", default="2015-01")
    ap.add_argument("--to", dest="hi", default="2026-06")
    a = ap.parse_args()
    print("조정본 잔여 CA 진단 + ca_guard 민감도 · A안 창(2015~) 기준")
    rows = [r for r in (diag(m, a.lo, a.hi) for m in ["KOSPI", "KOSDAQ"]) if r]
    if rows:
        out = os.path.join(BASE, "ca_guard_진단.csv")
        pd.DataFrame(rows).to_csv(out, index=False, encoding="utf-8-sig")
        print(f"\n요약 저장 → {os.path.basename(out)}")
    print("\n⚠️ 이 진단은 레벨(수정주가)을 고치지 않는다 — 남은 오염이 '크기 결론'을 뒤집는지만 본다.")

if __name__ == "__main__":
    main()
