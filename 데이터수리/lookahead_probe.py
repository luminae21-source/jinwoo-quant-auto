# -*- coding: utf-8 -*-
r"""lookahead_probe.py — '당월 랭크 vs 전월 랭크' 미래참조 프리미엄 재현 스크립트

왜 만들었나(2026-07-27):
  미래참조 프리미엄(+10.46%p / +43.75%p)은 원래 kosdaq_ca_diag 초판의 버그를 진단하다가
  **일회성 임시 계산**으로 뽑은 숫자였다. 캐시 오염을 정정한 뒤 다시 재려 했더니
  임시 계산이 남아 있지 않아 재현이 안 됐다. 재현 안 되는 숫자는 근거가 아니다.
  → 그래서 규약을 코드로 고정한다. 이 파일이 그 숫자의 유일한 출처다.

규약(중요):
  ret(ym) = close(ym)/close(ym-1) - 1        ← 'ym월에 실현된' 수익률
  정상(look-ahead 없음): ym월 편입 여부를 **ym-1월 말 시총 랭크**(rk_p)로 결정
  미래참조:              ym월 편입 여부를 **ym월 말 시총 랭크**(rk)로 결정
  → 당월 시총이 크다 = 그달에 오른 종목 = 사후 선택. 이것이 프리미엄의 정체다.

두 변형을 모두 보고한다:
  A. 원본     — 상폐 −100% 미반영·윈저 미적용 (구 표와 같은 구성)
  B. 상폐+윈저 — 지수 비교용 처리를 얹은 구성
사용: py 데이터수리\lookahead_probe.py
⚠️ 정보·검증용 · 투자자문 아님. 백테는 실현손익 아님.
"""
import os, sys, warnings; warnings.filterwarnings("ignore")
import pandas as pd, numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from ca_guard import winsor_returns, assert_adjusted

BASE = os.path.dirname(os.path.abspath(__file__))
LO, HI = "2015-01", "2026-06"


def cagr(m):
    m = m.dropna()
    return (1 + m).prod() ** (12 / len(m)) - 1 if len(m) else np.nan


def load_mcap():
    mc = pd.read_csv(os.path.join(BASE, "종목시총_30년_backfill.csv"),
                     dtype={"code": str}, usecols=["code", "ym", "mcap"])
    mc["code"] = mc["code"].str.zfill(6)
    mc = mc[(mc["ym"] >= LO) & (mc["ym"] <= HI)].copy()
    mc["rk"] = mc.groupby("ym")["mcap"].rank(ascending=False, method="first")
    return mc


def build(market, mc):
    p = os.path.join(BASE, f"_월봉종가캐시_{market}_adj.csv")
    d = pd.read_csv(p, dtype={"code": str})
    d["code"] = d["code"].str.zfill(6)
    assert_adjusted(d, market, where=os.path.basename(p))   # 오염 캐시 차단
    px = d[(d["ym"] >= LO) & (d["ym"] <= HI)]
    months = sorted(px["ym"].unique())
    w = px.pivot_table(index="ym", columns="code", values="close", aggfunc="last").sort_index()
    ret = w.pct_change().stack().rename("ret").reset_index()
    ret = ret.merge(mc[["code", "ym", "mcap", "rk"]], on=["code", "ym"], how="left")
    mp = mc.copy()
    mp["ym"] = mp["ym"].map({m: months[i + 1] for i, m in enumerate(months[:-1])})
    ret = ret.merge(mp[["code", "ym", "mcap", "rk"]].rename(
        columns={"mcap": "mcap_p", "rk": "rk_p"}), on=["code", "ym"], how="left")

    # 소멸 종목: 마지막 관측월 다음 달에 −100% 삽입(상한 가정)
    last = px.groupby("code")["ym"].max()
    dead = last[last < months[-1]]
    pos = {m: i for i, m in enumerate(months)}
    rkmap = mc.set_index(["code", "ym"])["rk"].to_dict()
    mcmap = mc.set_index(["code", "ym"])["mcap"].to_dict()
    add = []
    for c, m in dead.items():
        i = pos.get(m)
        if i is None or i + 1 >= len(months):
            continue
        ym = months[i + 1]
        # 소멸 셀의 가중치는 마지막 관측월 시총. 비워두면 시총가중 분기에서 dropna로 빠져
        # '상폐반영'이 실제로는 반영되지 않는다.
        add.append({"code": c, "ym": ym, "ret": -1.0, "mcap": mcmap.get((c, ym), np.nan),
                    "rk": rkmap.get((c, ym), np.nan), "mcap_p": mcmap.get((c, m), np.nan),
                    "rk_p": rkmap.get((c, m), np.nan)})
    full = pd.concat([ret, pd.DataFrame(add)], ignore_index=True) if add else ret
    return ret, full, len(dead)


def run(df, rkcol, wcol, vw, wins, top=300):
    x = df[df[rkcol] <= top].copy()
    if wins:
        x = winsor_returns(x, ret_col="ret", by="ym"); col = "ret_w"
    else:
        col = "ret"
    if vw:
        x = x.dropna(subset=[wcol, col])
        m = x.groupby("ym").apply(lambda g: np.average(g[col], weights=g[wcol]))
    else:
        m = x.groupby("ym")[col].mean()
    return cagr(m)


def main():
    mc = load_mcap()
    rows = []
    for market in ["KOSPI", "KOSDAQ"]:
        ret, full, n_dead = build(market, mc)
        print(f"\n{'='*72}\n[{market}] {LO}~{HI} · 창 종료 전 소멸 {n_dead:,}종목")
        for label, df, wins in [("A 원본(상폐·윈저 없음)", ret, False),
                                ("B 상폐 −100% + 월별 윈저", full, True)]:
            print(f"  {label}")
            for vw in (False, True):
                la = run(df, "rk",   "mcap",   vw, wins)
                ok = run(df, "rk_p", "mcap_p", vw, wins)
                tag = "시총가중" if vw else "동일가중"
                print(f"    {tag}  당월랭크(미래참조) {la*100:7.2f}%  "
                      f"전월랭크(정상) {ok*100:6.2f}%  → 프리미엄 {(la-ok)*100:+.2f}%p")
                rows.append({"market": market, "변형": label, "가중": tag,
                             "당월랭크_미래참조": la, "전월랭크_정상": ok, "프리미엄": la - ok})
    out = pd.DataFrame(rows)
    out.to_csv(os.path.join(BASE, "미래참조_프리미엄.csv"), index=False, encoding="utf-8-sig")
    print("\n저장 → 미래참조_프리미엄.csv")
    print("⚠️ 프리미엄은 '실력'이 아니라 선택 시점 버그의 크기다. 전월랭크 열만 인용 가능.")


if __name__ == "__main__":
    main()
