# -*- coding: utf-8 -*-
r"""전략대회.py — 인사이트 조합 리그전 + 메타 판정 (2026-07-28 신설)

[왜 대회인가]
  전략을 하나씩 사전등록해 검정하면 느리다. 대신 **인사이트를 조합해 수십 개 전략을 만들고
  한꺼번에 리그전**을 돌린다. 단, 그냥 우승자를 뽑으면 그것이 곧 데이터 마이닝이다.

[그래서 이 대회의 진짜 산출물은 우승자가 아니라 '메타 판정'이다]
  ① IN(2002-2015) 순위와 OOS(2016-2026) 순위의 **순위상관** — 백테 성적이 미래를 예측하는가?
  ② IN 상위 10%가 OOS에서도 상위권에 남는 **생존율**
  ③ 다중검정 보정 — 전략 K개를 돌리면 그중 최고는 우연히도 좋아 보인다(Bonferroni·DSR 근사)
  백서 측정값: IN Sharpe ↔ OOS Sharpe 상관 = **−0.709** (백테가 예쁠수록 실전에서 나빴다)
  이 대회가 그 수치를 우리 데이터로 재현하는지 본다.

[조합되는 인사이트 — 전부 이 프로젝트에서 검증·발견된 것]
  유니버스 : 대형(top300) · 소중형(301+) · 전체
  팩터     : 배당 · B/P · E/P · ROE · 저변동성 · 복합z(4팩터)
  게이트   : ROE>0(가치함정회피) · 신규상장 36M 제외 · 우선주 제외(고정)
  보유수   : 5 · 10 · 20 · 30
  방어     : 없음 · KOSPI 10개월MA 현금50%
  청산     : 없음 · 트레일 −15%

사용:
  py 전략대회.py                    # 기본 그리드 전체
  py 전략대회.py --top 20           # 리더보드 상위 20만 출력
  py 전략대회.py --universe 소중형   # 특정 유니버스만
출력: 전략대회_리더보드.csv · 전략대회_결과.md
⚠️ 과거통계·연구도구. 여기 1위는 '채택'이 아니다. 투자자문 아님.
"""
import os, sys, argparse, itertools, warnings
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd
from scipy import stats

BASE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def _find(fn):
    for d in (BASE, os.path.join(BASE, "데이터수리"), os.path.dirname(BASE), os.getcwd(),
              os.path.join(os.getcwd(), "데이터수리")):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    raise FileNotFoundError(fn)

def hac_t(x, lags=6):
    x = np.asarray(pd.Series(x).dropna(), float); n = len(x)
    if n < 12: return np.nan
    m = x.mean(); e = x - m; v = (e @ e) / n
    for L in range(1, min(lags, n - 1) + 1):
        v += 2 * (1 - L / (lags + 1)) * ((e[L:] @ e[:-L]) / n)
    return m / np.sqrt(max(v, 1e-18) / n)

COST = 0.00559
IN_A, IN_B   = "2002-07", "2015-12"
OOS_A, OOS_B = "2016-01", "2026-07"

# ══════════════════════════ 데이터 ══════════════════════════
print("데이터 로딩…", flush=True)
kis = pd.read_csv(_find("_월봉_KIS_전기간.csv"), dtype={"code": str})
kis["code"] = kis["code"].str.zfill(6)
P = kis.pivot_table(index="ym", columns="code", values="close", aggfunc="last").sort_index()
YM = list(P.index); C = list(P.columns)
_i = pd.to_datetime(P.index + "-01"); MIv = (_i.year * 12 + _i.month).values
R = P.pct_change(); R.iloc[np.r_[0, np.where(np.diff(MIv) != 1)[0] + 1]] = np.nan
VOL12 = R.rolling(12, min_periods=10).std()
FWD = R.shift(-1)

fins = []
for mkt in ("KOSPI", "KOSDAQ"):
    fins.append(pd.read_csv(_find(f"종목재무_KRX_{mkt}.csv"), dtype={"code": str},
                            usecols=["date", "code", "BPS", "PER", "PBR", "EPS", "DIV"]))
fin = pd.concat(fins); fin["code"] = fin["code"].str.zfill(6); fin["ym"] = fin["date"].str[:7]
for c in ("BPS", "PER", "PBR", "EPS", "DIV"): fin[c] = pd.to_numeric(fin[c], errors="coerce")
fin["bp"]  = np.where(fin["PBR"] > 0, 1 / fin["PBR"], np.nan)
fin["ep"]  = np.where(fin["PER"] > 0, 1 / fin["PER"], np.nan)
fin["roe"] = np.where(fin["BPS"] > 0, fin["EPS"] / fin["BPS"], np.nan)
fin["div"] = fin["DIV"].clip(0, 60)
fin = fin.groupby(["code", "ym"], as_index=False)[["div", "bp", "ep", "roe"]].last()
pv = lambda k: fin.pivot_table(index="ym", columns="code", values=k, aggfunc="last").reindex(index=YM, columns=C)
DIV, BP, EP, ROE = pv("div"), pv("bp"), pv("ep"), pv("roe")

mc = pd.read_csv(_find("종목시총_30년.csv"), dtype={"code": str})
mc.columns = [x.strip().lstrip("﻿") for x in mc.columns]
mc["code"] = mc["code"].str.zfill(6); mc["ym"] = pd.to_datetime(mc["date"]).dt.strftime("%Y-%m")
mc["mcap"] = pd.to_numeric(mc["mcap"], errors="coerce")
MC = mc.pivot_table(index="ym", columns="code", values="mcap", aggfunc="last").reindex(index=YM, columns=C)

idx = pd.read_csv(_find("kospi_index_daily.csv"))
idx["ym"] = pd.to_datetime(idx["Date"]).dt.strftime("%Y-%m")
IM = idx.groupby("ym")["Close"].last(); MA10 = IM.rolling(10).mean()
DEF_ON = pd.Series({y: (IM.get(y, np.nan) < MA10.get(y, np.nan)) for y in YM}).fillna(False)

try:
    _t = pd.read_csv(_find("소멸_재분류_v1.csv"), dtype={"code": str})
    TERM = pd.Series(_t["terminal_ret"].astype(float).values, index=_t["code"].str.zfill(6))
    TERMv = TERM.reindex(C).fillna(-0.30).values
except Exception:
    TERMv = np.full(len(C), -0.30)

ALL = set(C)
COMMON = np.array([c.isdigit() and not ((not c.endswith("0")) and (c[:5] + "0") in ALL) for c in C])
first_mi = {}
for j, c in enumerate(C):
    v = P[c].values; k = np.argmax(~np.isnan(v))
    if not np.isnan(v[k]): first_mi[c] = MIv[k]
AGE = np.array([[MIv[i] - first_mi.get(c, 10 ** 9) for c in C] for i in range(len(YM))])

RANK_MC = MC.rank(axis=1, ascending=False).values
UNIV = {
    "대형":   (RANK_MC <= 300) & COMMON[None, :],
    "소중형": (RANK_MC > 300) & (MC.values >= 300e8) & COMMON[None, :],
    "전체":   (~np.isnan(MC.values)) & COMMON[None, :],
}

def zpanel(X, mask):
    A = np.where(mask, X.values.astype(float), np.nan)
    m = np.nanmean(A, axis=1, keepdims=True); s = np.nanstd(A, axis=1, keepdims=True)
    return np.where(s > 0, (A - m) / s, 0.0)

RAW = {"배당": DIV, "B/P": BP, "E/P": EP, "ROE": ROE, "저변동성": -VOL12}
Z = {u: {k: zpanel(v, UNIV[u]) for k, v in RAW.items()} for u in UNIV}
for u in UNIV:
    Z[u]["복합z"] = np.nanmean(np.stack([Z[u][k] for k in ("배당", "B/P", "E/P", "ROE")]), axis=0)

FWDv, DIVv, ROEv = FWD.values, DIV.values, ROE.values
Pv = P.values

# ══════════════════════════ 백테 엔진 ══════════════════════════
def backtest(univ, factor, N, gate_roe, gate_age, defense, trail, a, b):
    S = Z[univ][factor]; M = UNIV[univ]
    ia = next(i for i, y in enumerate(YM) if y >= a)
    ib = max(i for i, y in enumerate(YM) if y <= b)
    rets, prev, peak = [], np.zeros(len(C)), {}
    for i in range(ia, min(ib, len(YM) - 2)):
        ok = M[i] & ~np.isnan(S[i]) & ~np.isnan(Pv[i])
        if gate_roe: ok &= (ROEv[i] > 0)
        if gate_age: ok &= (AGE[i] >= 36)
        if trail and peak:
            for j in list(peak):
                if not np.isnan(Pv[i][j]):
                    peak[j] = max(peak[j], Pv[i][j])
                    if Pv[i][j] < peak[j] * 0.85: ok[j] = False
        idxs = np.where(ok)[0]
        if len(idxs) < N: continue
        top = idxs[np.argsort(-S[i][idxs])[:N]]
        cash = 0.5 if (defense and DEF_ON.iloc[i]) else 0.0
        w = np.zeros(len(C)); w[top] = (1 - cash) / N
        r = FWDv[i + 1 - 1][top] if False else FWDv[i][top]
        r = np.where(np.isnan(r), TERMv[top], r)
        d = np.nan_to_num(DIVv[i][top]) / 100 / 12
        gross = float(np.sum(w[top] * (r + d)))
        turn = float(np.abs(w - prev).sum()) / 2
        rets.append(gross - turn * COST)
        prev = w
        peak = {j: max(peak.get(j, Pv[i][j] if not np.isnan(Pv[i][j]) else 0),
                       Pv[i][j] if not np.isnan(Pv[i][j]) else 0) for j in top} if trail else {}
    if len(rets) < 24: return None
    s = pd.Series(rets)
    yrs = len(s) / 12
    cagr = ((1 + s).prod() ** (1 / yrs) - 1) * 100
    nav = (1 + s).cumprod(); mdd = (nav / nav.cummax() - 1).min() * 100
    sharpe = s.mean() / s.std() * np.sqrt(12) if s.std() > 0 else np.nan
    return dict(cagr=cagr, mdd=mdd, sharpe=sharpe, n=len(s), rets=s)

def bench(univ, a, b):
    return backtest(univ, "복합z", 10 ** 6, False, False, False, False, a, b)

# ══════════════════════════ 대회 ══════════════════════════
def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--top", type=int, default=15)
    ap.add_argument("--universe", default=None)
    a = ap.parse_args()

    UNIVS = [a.universe] if a.universe else ["대형", "소중형", "전체"]
    FACTORS = ["배당", "B/P", "E/P", "ROE", "저변동성", "복합z"]
    NS = [5, 10, 20, 30]
    GRID = list(itertools.product(UNIVS, FACTORS, NS, [False, True], [False, True], [False, True]))
    # (univ, factor, N, gate_roe, defense, trail) — gate_age는 항상 True(신규상장 36M 제외, 실측 근거)

    print(f"대회 엔트리 {len(GRID)}개 · IN {IN_A}~{IN_B} · OOS {OOS_A}~{OOS_B}\n", flush=True)
    rows = []
    for k, (u, f, n, gr, dfs, tr) in enumerate(GRID, 1):
        rin = backtest(u, f, n, gr, True, dfs, tr, IN_A, IN_B)
        ros = backtest(u, f, n, gr, True, dfs, tr, OOS_A, OOS_B)
        if rin is None or ros is None: continue
        name = f"{u}|{f}|N{n}" + ("|ROE>0" if gr else "") + ("|방어" if dfs else "") + ("|트레일" if tr else "")
        rows.append(dict(전략=name, 유니버스=u, 팩터=f, N=n, ROE게이트=gr, 방어=dfs, 트레일=tr,
                         IN_CAGR=rin["cagr"], IN_Sharpe=rin["sharpe"], IN_MDD=rin["mdd"],
                         OOS_CAGR=ros["cagr"], OOS_Sharpe=ros["sharpe"], OOS_MDD=ros["mdd"]))
        if k % 30 == 0: print(f"  {k}/{len(GRID)} …", flush=True)

    df = pd.DataFrame(rows)
    df["IN_순위"] = df["IN_Sharpe"].rank(ascending=False)
    df["OOS_순위"] = df["OOS_Sharpe"].rank(ascending=False)
    df["순위변동"] = df["IN_순위"] - df["OOS_순위"]
    df = df.sort_values("IN_Sharpe", ascending=False)
    df.to_csv(os.path.join(BASE, "전략대회_리더보드.csv"), index=False, encoding="utf-8-sig")

    print("\n" + "=" * 104)
    print(f" 🏆 IN 리더보드 상위 {a.top} — 그리고 OOS에서 어떻게 됐나")
    print("=" * 104)
    print(f"  {'#':<3}{'전략':<38}{'IN CAGR':>9}{'IN Sh':>7}{'OOS CAGR':>10}{'OOS Sh':>8}{'OOS MDD':>9}{'순위변동':>9}")
    for r, (_, x) in enumerate(df.head(a.top).iterrows(), 1):
        mv = x["순위변동"]
        arrow = "↑" if mv > 5 else ("↓" if mv < -5 else "→")
        print(f"  {r:<3}{x['전략']:<38}{x['IN_CAGR']:>8.2f}%{x['IN_Sharpe']:>7.2f}"
              f"{x['OOS_CAGR']:>9.2f}%{x['OOS_Sharpe']:>8.2f}{x['OOS_MDD']:>8.1f}%"
              f"{arrow}{abs(mv):>7.0f}")

    # ── 메타 판정
    print("\n" + "=" * 104)
    print(" 🔬 메타 판정 — 백테 성적이 미래를 예측하는가")
    print("=" * 104)
    rho = stats.spearmanr(df["IN_Sharpe"], df["OOS_Sharpe"]).statistic
    rho_c = stats.spearmanr(df["IN_CAGR"], df["OOS_CAGR"]).statistic
    k = max(1, int(len(df) * 0.1))
    top_in = set(df.nlargest(k, "IN_Sharpe")["전략"]); top_oos = set(df.nlargest(k, "OOS_Sharpe")["전략"])
    surv = len(top_in & top_oos) / k * 100
    best_in = df.iloc[0]
    print(f"  ① IN↔OOS Sharpe 순위상관 : {rho:+.3f}   (백서 기록: −0.709)")
    print(f"     IN↔OOS CAGR 순위상관   : {rho_c:+.3f}")
    print(f"  ② IN 상위10%({k}개)가 OOS 상위10%에 남은 비율 : {surv:.0f}%  (우연이면 10%)")
    print(f"  ③ IN 1위 전략의 OOS 성적 : {best_in['전략']}")
    print(f"     IN {best_in['IN_CAGR']:.2f}%(Sh {best_in['IN_Sharpe']:.2f}) → "
          f"OOS {best_in['OOS_CAGR']:.2f}%(Sh {best_in['OOS_Sharpe']:.2f}) · OOS순위 {best_in['OOS_순위']:.0f}/{len(df)}")
    print(f"  ④ 다중검정: 전략 {len(df)}개를 돌렸으므로 최고 Sharpe는 우연으로도 "
          f"약 {np.sqrt(2*np.log(len(df)))*0.29:.2f}까지 나온다(기대 최댓값 근사)")
    verdict = ("백테 순위가 미래를 뒤집는다 — 백테 1위를 믿지 말 것" if rho < 0
               else ("백테 순위와 미래가 거의 무관 — 순위는 정보가 아니다" if rho < 0.3
                     else "백테 순위가 어느 정도 지속된다 — 단 다중검정 보정 필수"))
    print(f"\n  ▶ 판정: {verdict}")

    # OOS 자체 상위 (참고용 — 이건 '고르면 안 되는' 표)
    print("\n" + "-" * 104)
    print(" (참고) OOS 상위 10 — ⚠️ 여기서 고르면 그것이 곧 사후선택이다")
    d2 = df.sort_values("OOS_Sharpe", ascending=False).head(10)
    for r, (_, x) in enumerate(d2.iterrows(), 1):
        print(f"  {r:<3}{x['전략']:<38}OOS {x['OOS_CAGR']:>7.2f}% Sh {x['OOS_Sharpe']:>5.2f} "
              f"MDD {x['OOS_MDD']:>6.1f}% | IN순위 {x['IN_순위']:.0f}")

    md = [f"# 전략대회 결과 — {len(df)}개 엔트리", "",
          f"- IN {IN_A}~{IN_B} · OOS {OOS_A}~{OOS_B} · 비용 0.559% · 배당포함 · 상폐터미널 · 신규상장36M제외 · 우선주제외",
          "", "## 메타 판정 (이 대회의 진짜 산출물)", "",
          f"| 지표 | 값 |", "|---|---|",
          f"| IN↔OOS Sharpe 순위상관 | **{rho:+.3f}** |",
          f"| IN↔OOS CAGR 순위상관 | {rho_c:+.3f} |",
          f"| IN 상위10% → OOS 상위10% 생존율 | **{surv:.0f}%** (우연 10%) |",
          f"| IN 1위의 OOS 순위 | {best_in['OOS_순위']:.0f} / {len(df)} |",
          "", f"**판정: {verdict}**", "",
          "## IN 리더보드 상위 15", "",
          "| # | 전략 | IN CAGR | IN Sharpe | OOS CAGR | OOS Sharpe | OOS MDD |", "|---|---|---:|---:|---:|---:|---:|"]
    for r, (_, x) in enumerate(df.head(15).iterrows(), 1):
        md.append(f"| {r} | {x['전략']} | {x['IN_CAGR']:.2f}% | {x['IN_Sharpe']:.2f} | "
                  f"{x['OOS_CAGR']:.2f}% | {x['OOS_Sharpe']:.2f} | {x['OOS_MDD']:.1f}% |")
    md += ["", "⚠️ 이 표의 1위는 '채택'이 아니다. 채택은 사전등록 → 미개봉 구간 검정으로만 한다.",
           "과거통계·연구도구 · 투자자문 아님."]
    open(os.path.join(BASE, "전략대회_결과.md"), "w", encoding="utf-8").write("\n".join(md) + "\n")

    # ── 누적 기록 (계속 돌리기 위한 로그) ────────────────────────────
    LOG = os.path.join(BASE, "대회_기록.md")
    rnd = 1
    if os.path.exists(LOG):
        try: rnd = sum(1 for L in open(LOG, encoding="utf-8") if L.startswith("## 회차")) + 1
        except Exception: pass
    else:
        open(LOG, "w", encoding="utf-8").write(
            "# 전략대회 누적 기록\n\n매 회차의 메타 판정을 쌓는다. **개별 우승자보다 "
            "'백테가 미래를 예측하는가'의 추이가 본질이다.**\n\n"
            "| 회차 | 엔트리 | IN↔OOS 상관 | 생존율 | IN1위 OOS순위 | 최강 팩터 | 판정 |\n"
            "|---|---:|---:|---:|---|---|---|\n")
    bestf = df.groupby("팩터")[["IN_Sharpe","OOS_Sharpe"]].mean().mean(axis=1).idxmax()
    with open(LOG, "a", encoding="utf-8") as f:
        f.write(f"| {rnd} | {len(df)} | {rho:+.3f} | {surv:.0f}% | "
                f"{best_in['OOS_순위']:.0f}/{len(df)} | {bestf} | {verdict[:24]} |\n")
    print(f"\n저장: 전략대회_리더보드.csv · 전략대회_결과.md · 대회_기록.md (회차 {rnd} 추가)")

if __name__ == "__main__":
    main()
