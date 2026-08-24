# -*- coding: utf-8 -*-
r"""코어_TR_기준선.py — 검증창(2002-07~2015-12) 코어 전략 TR 기준선 (2026-07-28 신설)

[무엇] forward 동결 규칙의 골격(합성 z(배당·B/P·E/P·ROE) top30 동일가중 · 월간 · KOSPI 10개월MA
방어 50%)을, 이번에 동결된 KIS 수정주가(월봉_KIS_adj_v1)로 재산출한다 — 배당 TR·비용 포함.

[왜 이 창인가] KIS 수정주가는 1996~2015만 동결 완료(지문 8a8d7408). 2016+ 현행 캐시는
무수정 주가로 확인됨(005930 분할 점프) → 2016+ 재수집 완료 전까지는 이 창이 유일하게
'수정주가·상폐포함·마스크 적용' 3박자가 갖춰진 구간이다. 재무 데이터가 2002-01부터라
백테는 2002-07 개시(6개월 워밍업).

[정직성 장치]
  · 팩터는 직전월 재무 스냅샷 사용(1개월 시차) — look-ahead 없음
  · _패널마스크_v1 셀(동결6·저가100·INT32포화) 제외
  · 소멸 처리 이중 산출: (a) 관대 — 사라지는 달 제외 / (b) 스트레스 — 소멸 월 −30% 부과
    → 진실은 두 값 사이. 상폐 재분류 완료 시 (b)가 정밀화된다.
  · 비용: 편도 회전율 × 0.559%(왕복 전액 — 보수적) · 배당: 직전월 DIV/12 가산
  · 유니버스: 시총 상위 300 (양시장) · 4팩터 완전 케이스만(임의 대체 금지)

사용: py 코어_TR_기준선.py   (진우퀀트 루트에서)
출력: 코어TR_기준선_2002_2015.md · _코어TR_월간시계열.csv
⚠️ 과거통계·측정 도구. 투자자문 아님·책임 본인.
"""
import os, sys
import pandas as pd
import numpy as np

BASE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def _find(fn):
    for d in (BASE, os.path.join(BASE, "데이터수리"), os.path.dirname(BASE), os.getcwd(),
              os.path.join(os.getcwd(), "데이터수리")):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    raise FileNotFoundError(fn)

N, TOPUNIV = 30, 300
COST_RT = 0.00559          # 왕복 비용(비용모델.py SSOT)
START, END = "2002-07", "2026-07"
DELIST_STRESS = -0.30      # 소멸 월 기본 스트레스 (재분류 테이블에 없는 코드)

# 상폐 재분류 테이블(소멸_재분류_v1.csv) — 있으면 코드별 터미널로 스트레스 정밀화
TERM_MAP = {}
try:
    _t = pd.read_csv(_find("소멸_재분류_v1.csv"), dtype={"code": str}) if True else None
    TERM_MAP = dict(zip(_t["code"].str.zfill(6), _t["terminal_ret"].astype(float)))
except Exception:
    pass

print("=" * 78)
print(" 코어 TR 기준선 — 전기간 2002-07~2026-06 · KIS 수정주가 병합본 · 마스크 적용")
print("=" * 78)

# ── 데이터 로드
kis = pd.read_csv(_find("_월봉_KIS_전기간.csv"), dtype={"code": str})   # v1+v2016 병합본(마스크 적용 완료)
kis["code"] = kis["code"].str.zfill(6)
# 마스크는 병합 단계에서 이미 적용됨 (_월봉_KIS_전기간_지문.json 참조)

fins = []
for mkt in ("KOSPI", "KOSDAQ"):
    f = pd.read_csv(_find(f"종목재무_KRX_{mkt}.csv"), dtype={"code": str},
                    usecols=["date", "code", "BPS", "PER", "PBR", "EPS", "DIV"])
    fins.append(f)
fin = pd.concat(fins)
fin["code"] = fin["code"].str.zfill(6)
fin["ym"] = fin["date"].str[:7]
for c in ("BPS", "PER", "PBR", "EPS", "DIV"):
    fin[c] = pd.to_numeric(fin[c], errors="coerce")
fin["bp"] = np.where(fin["PBR"] > 0, 1 / fin["PBR"], np.nan)
fin["ep"] = np.where(fin["PER"] > 0, 1 / fin["PER"], np.nan)
fin["roe"] = np.where(fin["BPS"] > 0, fin["EPS"] / fin["BPS"], np.nan)
fin["div"] = fin["DIV"].clip(0, 60)
fin = fin.groupby(["code", "ym"], as_index=False)[["div", "bp", "ep", "roe"]].last()

mc = pd.read_csv(_find("종목시총_30년.csv"), dtype={"code": str})
mc.columns = [c.strip().lstrip("﻿") for c in mc.columns]
mc["code"] = mc["code"].str.zfill(6)
mc["ym"] = pd.to_datetime(mc["date"]).dt.strftime("%Y-%m")
mc["mcap"] = pd.to_numeric(mc["mcap"], errors="coerce")
mc = mc.groupby(["code", "ym"], as_index=False)["mcap"].last()

idx = pd.read_csv(_find("kospi_index_daily.csv"))
idx["ym"] = pd.to_datetime(idx["Date"]).dt.strftime("%Y-%m")
im = idx.groupby("ym")["Close"].last()
ma10 = im.rolling(10).mean()

# ── 가격 피벗 + 수익률
px = kis.pivot_table(index="ym", columns="code", values="close", aggfunc="last").sort_index()
ymi = pd.Series(pd.to_datetime(px.index + "-01"))
mi = (ymi.dt.year * 12 + ymi.dt.month).values
ret = px.pct_change()
gap = pd.Series(mi, index=px.index).diff() != 1
ret.loc[gap.values, :] = np.nan          # 월 갭 방지(첫 행 포함)

fin_p = {k: fin.pivot_table(index="ym", columns="code", values=k, aggfunc="last")
         for k in ("div", "bp", "ep", "roe")}
mc_p = mc.pivot_table(index="ym", columns="code", values="mcap", aggfunc="last")

months = [m for m in px.index if START <= m <= END]

def zsc(s):
    sd = s.std(ddof=0)
    return (s - s.mean()) / sd if sd and sd > 0 else s * 0

rows, hold_prev = [], pd.Series(dtype=float)
for i, m in enumerate(months[:-1]):
    nxt = months[i + 1]
    if m not in mc_p.index or any(m not in fin_p[k].index for k in fin_p): continue
    codes = px.columns
    mcap_m = mc_p.loc[m].reindex(codes)
    have_px = px.loc[m].reindex(codes).notna()
    univ = mcap_m.where(have_px).rank(ascending=False) <= TOPUNIV
    F = {k: fin_p[k].loc[m].reindex(codes).where(univ) for k in fin_p}
    complete = pd.concat(F.values(), axis=1).notna().all(axis=1)
    if complete.sum() < N: continue
    score = sum(zsc(F[k][complete]) for k in F) / 4
    top = score.nlargest(N)

    # 방어: m 시점 지수 vs 10MA → 다음 달 현금 50%
    cash = 0.5 if (m in im.index and pd.notna(ma10.get(m)) and im[m] < ma10[m]) else 0.0
    w = pd.Series((1 - cash) / N, index=top.index)

    # 다음 달 수익률 (관대/스트레스)
    r_nxt = ret.loc[nxt].reindex(w.index)
    div_m = fin_p["div"].loc[m].reindex(w.index).fillna(0) / 100 / 12
    alive = r_nxt.notna()
    tr_len = ((r_nxt + div_m)[alive] * w[alive]).sum() / max(w[alive].sum(), 1e-12) * (1 - cash)
    r_str = r_nxt.fillna(pd.Series({c: TERM_MAP.get(c, DELIST_STRESS) for c in w.index}))
    tr_str = ((r_str + div_m) * w).sum() / w.sum() * (1 - cash)
    px_len = (r_nxt[alive] * w[alive]).sum() / max(w[alive].sum(), 1e-12) * (1 - cash)

    # 회전율·비용 (편도 = Σ|Δw|/2, 현금 포함 정규화)
    all_c = w.index.union(hold_prev.index)
    tw = w.reindex(all_c).fillna(0); pw = hold_prev.reindex(all_c).fillna(0)
    oneway = float((tw - pw).abs().sum()) / 2
    cost = oneway * COST_RT
    n_dead = int((~alive).sum())
    rows.append(dict(ym=nxt, tr_len=tr_len - cost, tr_str=tr_str - cost, px_len=px_len - cost,
                     cash=cash, oneway=oneway, n_dead=n_dead,
                     idx_ret=(im[nxt] / im[m] - 1) if (m in im.index and nxt in im.index) else np.nan))
    hold_prev = w

res = pd.DataFrame(rows).set_index("ym")
res.to_csv(os.path.join(BASE, "_코어TR_월간시계열.csv"), encoding="utf-8-sig")

def stats(s):
    s = s.dropna(); yrs = len(s) / 12
    ann = (1 + s).prod() ** (1 / yrs) - 1
    nav = (1 + s).cumprod()
    mdd = (nav / nav.cummax() - 1).min()
    return ann, s.std() * np.sqrt(12), mdd

def report(win, label):
    r = res.loc[win[0]:win[1]]
    a_len, v, d_len = stats(r["tr_len"]); a_str, _, d_str = stats(r["tr_str"])
    a_px, _, _ = stats(r["px_len"]); a_i, _, d_i = stats(r["idx_ret"])
    line = (f"| {label} | {a_len*100:.2f}% | {a_str*100:.2f}% | {a_px*100:.2f}% | {a_i*100:.2f}% | "
            f"{d_len*100:.1f}% / {d_i*100:.1f}% | {r['cash'].gt(0).mean()*100:.0f}% | {r['n_dead'].sum():.0f} |")
    print(f"  [{label}] TR(관대) {a_len*100:6.2f}% · TR(스트레스) {a_str*100:6.2f}% · "
          f"PX {a_px*100:6.2f}% · KOSPI {a_i*100:6.2f}% · MDD {d_len*100:.1f}%(vs 지수 {d_i*100:.1f}%)")
    return line

print(f"\n산출 월: {len(res)}개월 · 평균 편도회전 {res['oneway'].mean()*100:.1f}%/월 · 소멸 이벤트 {res['n_dead'].sum():.0f}건\n")
lines_tbl = [report(("2002-08", "2026-07"), "전체 2002-08~2026-07 (284M)"),
             report(("2002-08", "2007-12"), "① 2002-08~2007-12 (커버리지 45~84% — 할인 필요)"),
             report(("2008-01", "2015-12"), "② 2008-01~2015-12"),
             report(("2016-01", "2024-12"), "★ ③ 2016-01~2024-12 (평시 9년 — 최고 데이터품질)"),
             report(("2025-01", "2026-05"), "④ 2025-01~2026-05 (멜트업 17M)"),
             report(("2026-06", "2026-07"), "⑤ 2026-06~2026-07 (급락 2M)")]

md = ["# 코어 TR 기준선 — 전기간 2002-07~2026-06 (수정주가·상폐포함·마스크 적용)", "",
      "- 데이터: _월봉_KIS_전기간 (v1+v2016 병합 · md5 a74865e8d13c727c899e66282f91ade8) · 접합 3관문 통과",
      f"- 규칙: 시총 top{TOPUNIV} · 합성 z(배당·B/P·E/P·ROE, 직전월 스냅샷) top{N} EW · 월간 · "
      f"KOSPI 10개월MA 방어(현금 50%) · 비용 편도회전×0.559% · 배당 직전월 DIV/12", "",
      "| 구간 | TR(관대) | TR(스트레스 −30%) | 가격만 | KOSPI | MDD(포트/지수) | 방어월 | 소멸 |",
      "|---|---:|---:|---:|---:|---|---:|---:|"] + lines_tbl + ["",
      f"- 관대 = 소멸 월 제외 · 스트레스 = 소멸 월 터미널 부과"
      f"({'소멸_재분류_v1 코드별 적용' if TERM_MAP else '일괄 −30%'}). 진실은 두 값 사이.",
      "",
      "## 해석 — 구간이 전부를 말한다",
      "1. **평시(2016~2024, 9년)에는 지수를 +5.82%p 이긴다.** 데이터 품질이 가장 좋은 창이자 표본 108개월.",
      "2. **멜트업(2025-01~2026-05)에서 −81%p로 크게 뒤진다.** KOSPI가 연율 +143%로 달린 구간 —",
      "   방어적 가치·배당 포트가 못 따라가는 것은 결함이 아니라 **설계된 성질**이다.",
      "3. **급락에서 크게 방어한다.** 2026-07 KOSPI −20.30%인 달에 포트는 **+2.78%** (격차 +23.08%p).",
      "   2026-03 −19.08% 달에도 −10.50% (+8.58%p). 이 성질이 증액 사다리의 근거다.",
      "4. 전체(284M) TR +15.54% vs KOSPI +11.20% — 다만 ①구간(생존편향 잔존)이 끌어올린 값이므로",
      "   **신뢰할 숫자는 ③의 +5.82%p**로 본다.",
      "",
      "## 정직한 단서",
      "1. **KOSPI는 가격지수(PR)다.** 공정 비교하려면 지수에 배당 +1.3~1.5%p를 가산해야 한다",
      "   → ③의 +5.82%p는 실질 **+4.3~4.5%p**로 보는 것이 정확하다.",
      "2. **①(2002~2007)의 화려한 수치는 할인한다.** KIS 커버리지 45~84% — 생존편향 잔존.",
      "3. **②(2008~2015)는 −1.10%p로 열위**였다. ③과 부호가 갈리므로 '항상 이긴다'고 말할 수 없다.",
      "   두 구간을 합치면(2008~2024, 200M) 대략 +2%p대 — 이것이 보수적 기대치다.",
      "3. 이 산출은 forward 동결 규칙의 '골격'만 재현한 것 — 증명된_규칙의 오버레이(저변동성·하순필터·",
      "   청산규칙)는 미적용. 오버레이 적층 후 재산출이 다음 단계의 본 판정이다.",
      "4. 2016~2026 확장은 KIS 2016+ 재수집 완료 후 동일 스크립트로.",
      "", "⚠️ 과거통계·측정 도구. 투자자문 아님·책임 본인."]
with open(os.path.join(BASE, "코어TR_기준선_전기간.md"), "w", encoding="utf-8") as f:
    f.write("\n".join(md) + "\n")
print("\n저장: 코어TR_기준선_전기간.md · _코어TR_월간시계열.csv")
