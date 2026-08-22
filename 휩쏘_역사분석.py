# -*- coding: utf-8 -*-
r"""휩쏘_역사분석.py — 역사검정 이벤트를 국면별로 층화 분석하고 정직한 판정을 낸다.
   질문 (1) 길게 보면 유효한가?  (2) 국면에 따라 달라지나? (모델 수정의 근거)
"""
import os, json, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
UP = "/mnt/user-data/uploads/진우퀀트"


def load_events():
    fs = [os.path.join(HERE, f"역사검정_이벤트_{m}.csv") for m in ("KOSPI", "KOSDAQ")]
    E = pd.concat([pd.read_csv(f) for f in fs if os.path.exists(f)], ignore_index=True)
    E["date"] = pd.to_datetime(E["date"])
    return E.sort_values("date").reset_index(drop=True)


def load_base():
    fs = [os.path.join(HERE, f"역사검정_기저_{m}.csv") for m in ("KOSPI", "KOSDAQ")]
    B = pd.concat([pd.read_csv(f) for f in fs if os.path.exists(f)], ignore_index=True)
    B["date"] = pd.to_datetime(B["date"])
    return B


def regime():
    p = os.path.join(UP, "kospi_index_daily.csv")
    ix = pd.read_csv(p)
    ix.columns = [c.strip().lstrip("﻿") for c in ix.columns]
    ix["Date"] = pd.to_datetime(ix["Date"])
    ix = ix.sort_values("Date").reset_index(drop=True)
    c = ix["Close"].astype(float)
    ix["ma200"] = c.rolling(200, min_periods=100).mean()
    ix["bull"] = c > ix["ma200"]                       # 강세(200일선 위) / 약세
    ret = c.pct_change()
    ix["vol20"] = ret.rolling(20, min_periods=10).std() * np.sqrt(252)
    ix["mdd252"] = c / c.rolling(252, min_periods=120).max() - 1   # 시장 자체 낙폭
    volmed = ix["vol20"].median()
    ix["volhi"] = ix["vol20"] > volmed
    ix["_volmed"] = volmed
    return ix[["Date", "bull", "vol20", "volhi", "mdd252", "ma200"]].rename(columns={"Date": "date"})


def merge_regime(E, R):
    E = E.sort_values("date"); R = R.sort_values("date")
    return pd.merge_asof(E, R, on="date", direction="backward")


def stat_block(df, base_mean):
    d = df.dropna(subset=["fwd40"])
    n = len(d)
    if n == 0:
        return dict(n=0)
    out = dict(
        n=n,
        win20=float((d["fwd20"] > 0).mean()),
        win40=float((d["fwd40"] > 0).mean()),
        m10=float(d["fwd10"].mean()), m20=float(d["fwd20"].mean()), m40=float(d["fwd40"].mean()),
        med20=float(d["fwd20"].median()), med40=float(d["fwd40"].median()),
        ex_mean=float(d["ex_ret"].mean()), ex_win=float((d["ex_ret"] > 0).mean()),
        ex_bars=float(d["ex_bars"].mean()),
        p목표=float((d["ex_how"] == "목표").mean()), p손절=float((d["ex_how"] == "손절").mean()),
        p트레일=float((d["ex_how"] == "트레일").mean()), p만기=float((d["ex_how"] == "만기").mean()),
    )
    out["lift40"] = out["m40"] / base_mean if base_mean else np.nan
    return out


def pct(x): return f"{x*100:+.1f}%" if pd.notna(x) else "-"
def pctp(x): return f"{x*100:.0f}%" if pd.notna(x) else "-"


def main():
    E = load_events(); B = load_base(); R = regime()
    E = merge_regime(E, R)
    B = merge_regime(B, R)

    mature = E["fwd40"].notna()
    Em = E[mature].copy()
    Blast = B.dropna(subset=["fwd40"])
    base_m20 = float(Blast["fwd20"].mean()); base_m40 = float(Blast["fwd40"].mean())
    base_win20 = float((Blast["fwd20"] > 0).mean()); base_win40 = float((Blast["fwd40"] > 0).mean())

    rep = {}
    rep["기간"] = [str(E["date"].min().date()), str(E["date"].max().date())]
    rep["총이벤트"] = int(len(E)); rep["성숙이벤트"] = int(len(Em))
    rep["미성숙(진행중)"] = int((~mature).sum())
    rep["기저"] = dict(n=int(len(Blast)), m20=base_m20, m40=base_m40, win20=base_win20, win40=base_win40)

    rep["전체_A"] = stat_block(Em[Em["유형"] == "A"], base_m40)
    rep["전체_B"] = stat_block(Em[Em["유형"] == "B"], base_m40)
    for gd in ("A", "B", "C"):
        rep[f"A등급_{gd}"] = stat_block(Em[(Em["유형"] == "A") & (Em["등급"] == gd)], base_m40)

    # 국면 층화 (A유형 중심 — 표본 큼)
    def reg_table(sub, key, vals, labels):
        rows = []
        for v, lab in zip(vals, labels):
            s = stat_block(sub[sub[key] == v], base_m40)
            b = Blast[Blast[key] == v]
            bm = float(b["fwd40"].mean()) if len(b) else np.nan
            s["기저m40"] = bm
            s["국면"] = lab
            rows.append(s)
        return rows

    A = Em[Em["유형"] == "A"]; Bt = Em[Em["유형"] == "B"]
    rep["A_강세약세"] = reg_table(A, "bull", [True, False], ["강세장(200일선↑)", "약세장(200일선↓)"])
    rep["A_변동성"] = reg_table(A, "volhi", [False, True], ["저변동", "고변동"])
    rep["B_강세약세"] = reg_table(Bt, "bull", [True, False], ["강세장", "약세장"])

    # 시장 자체 낙폭 버킷 (선지지형 A: 시장이 깊게 빠졌을 때가 진짜 자리인가?)
    def mdd_bucket(x):
        if pd.isna(x): return "?"
        if x >= -0.05: return "시장 고점권(0~-5%)"
        if x >= -0.12: return "시장 조정(-5~-12%)"
        if x >= -0.22: return "시장 하락(-12~-22%)"
        return "시장 급락(-22%↓)"
    A2 = A.copy(); A2["mb"] = A2["mdd252"].apply(mdd_bucket)
    rows = []
    for lab in ["시장 고점권(0~-5%)", "시장 조정(-5~-12%)", "시장 하락(-12~-22%)", "시장 급락(-22%↓)"]:
        s = stat_block(A2[A2["mb"] == lab], base_m40); s["국면"] = lab; rows.append(s)
    rep["A_시장낙폭"] = rows

    # 2x2 강세x변동
    rows = []
    for bl, blab in [(True, "강세"), (False, "약세")]:
        for vh, vlab in [(False, "저변동"), (True, "고변동")]:
            s = stat_block(A[(A["bull"] == bl) & (A["volhi"] == vh)], base_m40)
            s["국면"] = f"{blab}·{vlab}"; rows.append(s)
    rep["A_2x2"] = rows

    # 연도별 (A)
    yr = []
    Ay = A.assign(y=A["date"].dt.year)
    for y, d in Ay.groupby("y"):
        dd = d.dropna(subset=["fwd40"])
        if len(dd) == 0: continue
        yr.append(dict(y=int(y), n=int(len(dd)), win40=float((dd["fwd40"] > 0).mean()),
                       m40=float(dd["fwd40"].mean()), ex=float(dd["ex_ret"].mean())))
    rep["A_연도"] = yr

    # 2026 진행중 (아직 판단 불가 — 관찰원장 몫)
    live = E[(E["date"].dt.year == 2026)]
    rep["2026_진행중"] = dict(n=int(len(live)), A=int((live["유형"] == "A").sum()),
                            B=int((live["유형"] == "B").sum()))

    with open(os.path.join(HERE, "역사분석_요약.json"), "w", encoding="utf-8") as f:
        json.dump(rep, f, ensure_ascii=False, indent=2)

    # ---- 텍스트 출력 ----
    P = print
    P("=" * 78)
    P(f" 휩쏘 재진입 역사검정  {rep['기간'][0]} ~ {rep['기간'][1]}")
    P(f" 총 {rep['총이벤트']}건 (성숙 {rep['성숙이벤트']} · 진행중 {rep['미성숙(진행중)']})")
    P("=" * 78)
    b = rep["기저"]
    P(f"\n[기저율] 무작위 진입 {b['n']}표본 · 40일 평균 {pct(b['m40'])} · 승률 {pctp(b['win40'])}")

    def show(tag, s):
        if s.get("n", 0) == 0: P(f"  {tag}: 표본 없음"); return
        P(f"  {tag:<16} n={s['n']:>4} · 40일 {pct(s['m40'])} (중앙 {pct(s['med40'])}) · 승률 {pctp(s['win40'])}"
          f" · 리프트 {s['lift40']:.2f}x · 카드청산 {pct(s['ex_mean'])}(승 {pctp(s['ex_win'])})"
          f" · 목표{pctp(s['p목표'])}/손절{pctp(s['p손절'])}/트레일{pctp(s['p트레일'])}/만기{pctp(s['p만기'])}")

    P("\n[전체]")
    show("A 선지지형", rep["전체_A"]); show("B 리더형", rep["전체_B"])
    P("\n[A 등급별 — 지지>밀착>근접]")
    show("A급 지지", rep["A등급_A"]); show("B급 밀착", rep["A등급_B"]); show("C급 근접", rep["A등급_C"])

    def showreg(title, rows):
        P(f"\n[{title}]")
        for s in rows:
            if s.get("n", 0) == 0: P(f"  {s['국면']:<18} 표본 없음"); continue
            bm = s.get("기저m40")
            lift = s['m40']/bm if (bm and pd.notna(bm) and bm != 0) else np.nan
            extra = f" · 국면기저 {pct(bm)} · 국면리프트 {lift:.2f}x" if pd.notna(bm) else ""
            P(f"  {s['국면']:<18} n={s['n']:>4} · 40일 {pct(s['m40'])} · 승률 {pctp(s['win40'])}"
              f" · 카드 {pct(s['ex_mean'])}{extra}")

    showreg("A · 강세/약세장", rep["A_강세약세"])
    showreg("A · 변동성 국면", rep["A_변동성"])
    showreg("A · 시장 자체 낙폭별 (핵심)", rep["A_시장낙폭"])
    showreg("A · 강세×변동 2x2", rep["A_2x2"])
    showreg("B · 강세/약세장", rep["B_강세약세"])

    P("\n[A 연도별]")
    for s in rep["A_연도"]:
        P(f"  {s['y']}  n={s['n']:>3} · 40일 {pct(s['m40'])} · 승률 {pctp(s['win40'])} · 카드 {pct(s['ex'])}")
    lv = rep["2026_진행중"]
    P(f"\n[2026 진행중] {lv['n']}건 (A {lv['A']} · B {lv['B']}) — 전진결과 미확정. 관찰원장이 채운다.")


if __name__ == "__main__":
    main()
