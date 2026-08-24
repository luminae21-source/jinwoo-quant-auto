# -*- coding: utf-8 -*-
r"""survivor_probe.py — 조정본 패널의 '크기 수치'가 왜 부풀 수 있는지 3원 분해

왜 필요한가(2026-07-27): kosdaq_ca_diag ⑤에서 KOSDAQ 시총 top300 동일가중 CAGR이
46.83%(윈저 41.22%)로 나왔다. 같은 창(2015~2026)의 실제 KOSDAQ 지수는 연 몇 % 수준이므로
이 숫자는 **믿을 수 없다**. 숫자를 손보기 전에 원인을 분리한다:
  (A) 상장폐지 처리 부재 = 생존편향 (소멸 종목의 마지막 손실이 패널에 없다)
  (B) 동일가중 월별 리밸런싱 프리미엄 (소형·고변동 종목의 noise rebalancing)
  (C) 꼬리(윈저로 잡히는 극단 수익률)
판정 기준: 세 요인을 끄고 켰을 때 지수 수준(연 2~8%)에 수렴하면 원인 규명 완료.
⚠️ 정보·검증용 · 투자자문 아님.
"""
import os, sys, warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ca_guard import winsor_returns, assert_adjusted

BASE = os.path.dirname(os.path.abspath(__file__))
LO, HI = "2015-01", "2026-06"

def load_px(market):
    p = os.path.join(BASE, f"_월봉종가캐시_{market}_adj.csv")
    d = pd.read_csv(p, dtype={"code": str})
    d["code"] = d["code"].str.zfill(6)
    # 적재 가드: 파일명이 `_adj`라는 것은 조정본이라는 증거가 아니다(2026-07-26 오염 사고).
    assert_adjusted(d, market, where=os.path.basename(p))
    return d[(d["ym"] >= LO) & (d["ym"] <= HI)]

def cagr(m):
    m = m.dropna()
    return (1 + m).prod() ** (12 / len(m)) - 1 if len(m) else np.nan

def probe(market):
    px = load_px(market)
    months = sorted(px["ym"].unique())
    w = px.pivot_table(index="ym", columns="code", values="close", aggfunc="last").sort_index()
    ret = w.pct_change().stack().rename("ret").reset_index()

    # 시총 랭크
    mc = pd.read_csv(os.path.join(BASE, "종목시총_30년_backfill.csv"),
                     dtype={"code": str}, usecols=["code", "ym", "mcap"])
    mc["code"] = mc["code"].str.zfill(6)
    mc = mc[(mc["ym"] >= LO) & (mc["ym"] <= HI)]
    mc["rk"] = mc.groupby("ym")["mcap"].rank(ascending=False, method="first")
    ret = ret.merge(mc[["code", "ym", "mcap", "rk"]], on=["code", "ym"], how="left")
    # 비중은 **전월 시총**으로 (당월 시총 사용은 미래참조)
    mc_prev = mc.copy(); mc_prev["ym"] = mc_prev["ym"].map(
        {m: months[i + 1] for i, m in enumerate(months[:-1])})
    ret = ret.merge(mc_prev[["code", "ym", "mcap", "rk"]].rename(
        columns={"mcap": "mcap_p", "rk": "rk_p"}), on=["code", "ym"], how="left")

    # 소멸(추정 상장폐지) 종목: 마지막 관측월 + 1 에 -100% 가정 셀 삽입
    last = px.groupby("code")["ym"].max()
    dead = last[last < months[-1]]
    pos = {m: i for i, m in enumerate(months)}
    add = [{"code": c, "ym": months[pos[m] + 1], "ret": -1.0,
            "mcap_p": np.nan, "rk_p": np.nan}
           for c, m in dead.items() if pos.get(m) is not None and pos[m] + 1 < len(months)]
    # 소멸 종목의 rk_p는 마지막 관측월 랭크로 근사(그달에도 top300이었다면 포함해야 공정)
    # mcap_p도 같은 달 시총으로 채운다 — 비우면 시총가중 분기에서 dropna로 **통째로 빠져
    # '상폐반영'이라 써 놓고 실제로는 반영이 안 되는** 버그가 된다(2026-07-27 발견·수정).
    rkmap = mc.set_index(["code", "ym"])["rk"].to_dict()
    mcmap = mc.set_index(["code", "ym"])["mcap"].to_dict()
    for a in add:
        i = pos[a["ym"]]
        a["rk_p"] = rkmap.get((a["code"], months[i - 1]), np.nan)
        a["mcap_p"] = mcmap.get((a["code"], months[i - 1]), np.nan)
    dead_df = pd.DataFrame(add)

    print(f"\n{'='*72}\n[{market}] {LO}~{HI} · 종목 {px['code'].nunique():,} · "
          f"창 종료 전 소멸 {len(dead):,} ({len(dead)/px['code'].nunique()*100:.1f}%)")

    def run(label, d, cap300, delist, winsor, vw):
        x = d.copy()
        if cap300:
            x = x[x["rk_p"] <= 300]
        if winsor:
            x = winsor_returns(x, ret_col="ret", by="ym"); col = "ret_w"
        else:
            col = "ret"
        if vw:
            x = x.dropna(subset=["mcap_p", col])
            m = x.groupby("ym").apply(lambda g: np.average(g[col], weights=g["mcap_p"]))
        else:
            m = x.groupby("ym")[col].mean()
        print(f"  {label:<44s} CAGR {cagr(m)*100:7.2f}%   (월 {len(m.dropna())})")
        return cagr(m)

    full = pd.concat([ret, dead_df], ignore_index=True) if len(dead_df) else ret
    out = {}
    out["ew_all"]        = run("① 전체·동일가중·원본", ret, False, False, False, False)
    out["ew_300"]        = run("② top300·동일가중·원본", ret, True, False, False, False)
    out["ew_300_delist"] = run("③ top300·동일가중·+상폐 −100% 반영", full, True, True, False, False)
    out["ew_300_wins"]   = run("④ top300·동일가중·+상폐·윈저", full, True, True, True, False)
    out["vw_300"]        = run("⑤ top300·시총가중·+상폐·윈저", full, True, True, True, True)
    out["vw_all"]        = run("⑥ 전체·시총가중·+상폐·윈저 (지수 근사)", full, False, True, True, True)
    print(f"  분해: 생존편향 {(out['ew_300_delist']-out['ew_300'])*100:+.2f}%p · "
          f"꼬리 {(out['ew_300_wins']-out['ew_300_delist'])*100:+.2f}%p · "
          f"동일→시총가중 {(out['vw_300']-out['ew_300_wins'])*100:+.2f}%p")
    return {"market": market, **out, "n_dead": int(len(dead))}

if __name__ == "__main__":
    print("크기 수치 3원 분해 — 왜 top300 46.8%가 나왔나 (숫자를 고치기 전에 원인부터)")
    rows = [probe(m) for m in ["KOSPI", "KOSDAQ"]]
    pd.DataFrame(rows).to_csv(os.path.join(BASE, "생존편향_분해.csv"),
                              index=False, encoding="utf-8-sig")
    print("\n저장 → 생존편향_분해.csv")
    print("⚠️ ⑤(시총가중·상폐반영·윈저)만이 지수와 비교 가능한 수치다. ①②는 보고 금지.")
