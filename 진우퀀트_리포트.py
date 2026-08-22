# -*- coding: utf-8 -*-
r"""진우퀀트_리포트.py — 일간/주간/월간 리포트 생성 (2026-08-18)

[구성] 지수 흐름 · 국면 나침반(전망 대체) · 관찰 원장 · 가상매매 · 탐지 활동 · (월간) 역사 배경
[국면 나침반 — 정직 원칙]
  예측하지 않는다. 30년 검정으로 실제로 아는 것만 쓴다:
   ① 오늘 국면(실행/주의/관찰만)과 그 국면의 30년 기대값
   ② 다음 달의 30년 계절성 배경 (평균이지 보장이 아님)
   ③ 규칙이 시키는 행동 (신호가 오면/안 오면)
  "지수가 오를 것"류의 문장은 금지.

사용: py 진우퀀트_리포트.py --period 일간|주간|월간 [--noopen]
산출: 리포트_{기간}_YYYYMMDD.html
⚠️ 기록·참고용. 매매 추천 아님.
"""
import os, sys, json, glob, argparse, warnings, webbrowser, html as H
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

# 30년 지수 계절성 (합성지수 · 휩쏘_사이클검정.py 산출 고정값 — 데이터 갱신 시 재산출해 교체)
SEASON = {1: (3.22, 61), 2: (0.21, 52), 3: (0.43, 58), 4: (3.47, 65), 5: (0.42, 52), 6: (0.29, 50),
          7: (0.95, 63), 8: (-1.18, 39), 9: (-0.87, 58), 10: (-0.31, 45), 11: (2.19, 55), 12: (1.42, 55)}
# 국면별 30년 기대 (정식A 카드 40봉 · 인수인계 2판 §2-2)
REGIME_EXP = {"실행": ("+2.40% · 승률 55.3%", "var(--good)"),
              "주의": ("−0.12% · 승률 41.1%", "var(--b)"),
              "관찰만": ("−0.60% · 승률 37.4%", "var(--bad)")}


def find(fn):
    p = os.path.join(HERE, fn)
    return p if os.path.exists(p) else None


def load_index():
    p = find("kospi_index_daily.csv")
    ix = pd.read_csv(p); ix.columns = [c.strip().lstrip("﻿") for c in ix.columns]
    ix["Date"] = ix["Date"].astype(str)
    ix["Close"] = pd.to_numeric(ix["Close"], errors="coerce")
    return ix.dropna().sort_values("Date").reset_index(drop=True)


def regime_now():
    import importlib.util
    spec = importlib.util.spec_from_file_location("sj", os.path.join(HERE, "시장국면.py"))
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m.regime_at(None)


def pct(v, sign=True):
    if v is None or (isinstance(v, float) and not np.isfinite(v)): return "-"
    return f"{v*100:+.2f}%" if sign else f"{v*100:.2f}%"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--period", default="일간", choices=["일간", "주간", "월간"])
    ap.add_argument("--noopen", action="store_true")
    a = ap.parse_args()

    ix = load_index()
    last = ix["Date"].iloc[-1]
    d8 = last.replace("-", "")
    # 기간 경계 (거래일 기준)
    if a.period == "일간": n_back, 라벨 = 1, f"{last} 기준"
    elif a.period == "주간": n_back, 라벨 = 5, f"최근 5거래일 ({ix['Date'].iloc[-min(5,len(ix))]} ~ {last})"
    else:
        month0 = last[:7] + "-01"
        n_back = int((ix["Date"] >= month0).sum())
        라벨 = f"{last[:7]}월 ({month0} ~ {last})"
    n_back = max(1, min(n_back, len(ix) - 1))
    p0, p1 = ix["Close"].iloc[-n_back - 1], ix["Close"].iloc[-1]
    chg = p1 / p0 - 1
    start_d = ix["Date"].iloc[-n_back]

    rg = regime_now()
    rgj = str(rg.get("판정", "?")).split("(")[0]
    exp, expc = REGIME_EXP.get(rgj, ("-", "var(--mut)"))
    mdd = rg.get("mdd252"); vol = rg.get("vol20"); volmed = rg.get("volmed")
    y, m = int(last[:4]), int(last[5:7])
    nm = m % 12 + 1
    s_now, s_next = SEASON[m], SEASON[nm]

    # 관찰 원장 (기간 내 변동)
    obs = pd.read_csv(find("휩쏘_관찰.csv"), dtype=str) if find("휩쏘_관찰.csv") else pd.DataFrame()
    obs_new = obs[obs["출발일"] >= start_d] if len(obs) else obs
    obs_closed = obs[(obs["종료일"].fillna("") >= start_d)] if len(obs) else obs
    obs_sum = obs["상태"].value_counts().to_dict() if len(obs) else {}

    # 가상매매
    cfg = json.load(open(find("가상매매_설정.json"), encoding="utf-8")) if find("가상매매_설정.json") else {}
    eq = pd.read_csv(find("가상매매_자본곡선.csv")) if find("가상매매_자본곡선.csv") else pd.DataFrame()
    vt = pd.read_csv(find("가상매매_원장.csv"), dtype=str) if find("가상매매_원장.csv") else pd.DataFrame()
    v_total = float(eq["평가포함자산"].iloc[-1]) if len(eq) else float(cfg.get("시작자본", 0) or 0)
    v_start = float(cfg.get("시작자본", 1) or 1)
    eq_period = eq[eq["date"].astype(str) >= start_d] if len(eq) else eq
    v_chg = (float(eq_period["평가포함자산"].iloc[-1]) - float(eq_period["평가포함자산"].iloc[0])) if len(eq_period) >= 2 else 0.0
    v_open = int((vt["상태"].isin(["보유", "절반실현"])).sum()) if len(vt) else 0
    v_done = int((vt["상태"] == "청산").sum()) if len(vt) else 0

    # 탐지 활동 (기간 내)
    det_files = sorted(glob.glob(os.path.join(HERE, "휩쏘탐지_*.csv")))
    det_rows = []
    for f in det_files:
        dd = "".join(c for c in os.path.basename(f) if c.isdigit())[:8]
        ds = f"{dd[:4]}-{dd[4:6]}-{dd[6:]}"
        if ds >= start_d:
            try:
                d_ = pd.read_csv(f, dtype=str)
                det_rows.append((ds, int((d_["유형"] == "A").sum()), int((d_["유형"] == "B").sum())))
            except Exception: pass

    # 월간: 이 달의 30년 역사 (역사원장)
    hist_block = ""
    hp = find("휩쏘_역사원장.csv")
    if a.period == "월간" and hp:
        HH = pd.read_csv(hp, dtype=str)
        hm = HH[pd.to_datetime(HH["출발일"]).dt.month == m]
        hv = pd.to_numeric(hm["카드수익"], errors="coerce").dropna()
        if len(hv):
            hist_block = (f"<h2>{m}월의 30년 역사 배경</h2><p>{m}월 출발 휩쏘 이벤트 {len(hm):,}건 · "
                          f"카드 평균 <b>{hv.mean():+.1f}%</b> · 승률 {(hv>0).mean()*100:.0f}% "
                          f"<span class=mut>(역사원장 기준 · 국면 혼합)</span></p>")

    esc = H.escape
    obs_line = " · ".join(f"{k} {v}" for k, v in obs_sum.items()) or "-"
    det_line = ("".join(f"<tr><td>{d}</td><td class=n>A {na}건</td><td class=n>B {nb}건</td></tr>"
                        for d, na, nb in det_rows)
                or "<tr><td colspan=3 class=mut>기간 내 탐지 실행 기록 없음 — 신호가 없었거나 탐색기를 안 돌린 날</td></tr>")
    mark = {"실행": "🟢", "주의": "🟡", "관찰만": "🔴"}.get(rgj, "·")

    doc = f"""<!DOCTYPE html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>{a.period} 리포트 {last}</title><style>
:root{{color-scheme:light;--bg:#f6f6f4;--sf:#fcfcfb;--bd:#e3e2dd;--ink:#0f0f0e;--ink2:#54534e;--mut:#8a877e;--a:#2a78d6;--b:#eb6834;--good:#1a7f4b;--bad:#c0342f}}
@media(prefers-color-scheme:dark){{:root{{color-scheme:dark;--bg:#111110;--sf:#1a1a19;--bd:#33322f;--ink:#fafaf7;--ink2:#c3c2b7;--mut:#8f8e85;--a:#3987e5;--b:#d95926;--good:#4bb87c;--bad:#e0655a}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Malgun Gothic","Apple SD Gothic Neo",sans-serif;font-size:14.5px;line-height:1.62}}
.w{{max-width:820px;margin:0 auto;padding:34px 20px 70px}}
h1{{font-size:22px;margin:0 0 2px}}.sub{{color:var(--ink2);margin:0;font-size:13px}}
h2{{font-size:15px;margin:24px 0 8px;padding-top:12px;border-top:1px solid var(--bd);color:var(--ink2)}}
.k{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:10px;margin:14px 0}}
.kb{{background:var(--sf);border:1px solid var(--bd);border-radius:10px;padding:11px 13px}}
.kb .v{{font-size:19px;font-weight:700}}.kb .l{{font-size:11px;color:var(--mut);margin-top:2px}}
.compass{{background:var(--sf);border:1px solid var(--bd);border-left:4px solid {expc};border-radius:10px;padding:13px 16px;margin:12px 0}}
table{{width:100%;border-collapse:collapse;font-size:13px;margin:6px 0}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--bd)}}
th{{color:var(--ink2);font-size:11px;font-weight:650}}td.n{{text-align:right;font-variant-numeric:tabular-nums}}
.mut{{color:var(--mut)}}.good{{color:var(--good)}}.bad{{color:var(--bad)}}
.warn{{color:var(--mut);font-size:11.5px;margin-top:22px;border-top:1px solid var(--bd);padding-top:10px}}
</style></head><body><div class=w>
<h1>진우퀀트 {a.period} 리포트</h1>
<p class=sub>{라벨} · 생성 {last} 데이터 기준</p>

<div class=k>
<div class=kb><div class=v class="{'good' if chg>=0 else 'bad'}">{pct(chg)}</div><div class=l>지수 {a.period} 변화 ({p0:,.0f} → {p1:,.0f})</div></div>
<div class=kb><div class=v>{pct(mdd) if mdd is not None else '-'}</div><div class=l>1년 고점 대비</div></div>
<div class=kb><div class=v>{v_total:,.0f}원</div><div class=l>가상계좌 ({(v_total/v_start-1)*100:+.2f}% · 기간 {v_chg:+,.0f}원)</div></div>
<div class=kb><div class=v>{len(obs)}종</div><div class=l>관찰 원장 ({obs_line})</div></div>
</div>

<h2>국면 나침반 <span class=mut style="font-weight:400">— 전망이 아니라, 아는 것만</span></h2>
<div class=compass>
{mark} <b>현재 국면: {esc(str(rg.get('판정','?')))}</b> — {esc(str(rg.get('이유',''))[:90])}<br>
<span class=mut>이 국면의 30년 기대(정식A 카드): </span><b style="color:{expc}">{exp}</b><br>
<span class=mut>계절성 배경(30년 합성지수): 이번 달({m}월) 평균 {s_now[0]:+.2f}%·플러스율 {s_now[1]}% → 다음 달({nm}월) {s_next[0]:+.2f}%·{s_next[1]}%</span><br>
<span class=mut>규칙이 시키는 것: </span>{"A 신호가 뜨면 카드대로 진입(2단 청산). 신호가 없으면 아무것도 안 한다." if rgj=="실행" else ("신호가 떠도 신중 — 절반 규모 또는 관찰." if rgj=="주의" else "신호가 떠도 사지 않는다(함정 국면). 기록만.")}
</div>
<p class=mut style="font-size:12px">⚠️ 계절성은 30년 <b>평균</b>이지 보장이 아니다. 지수 방향 예측은 이 시스템의 능력 밖이며, 우리가 검정한 것은 "국면별 휩쏘 신호의 기대값"뿐이다.</p>

<h2>관찰 원장</h2>
<p>기간 내 신규 등록 <b>{len(obs_new)}</b>종 · 기간 내 종료 <b>{len(obs_closed)}</b>종 · 현재 분포: {obs_line}</p>

<h2>가상매매</h2>
<p>총자산 <b>{v_total:,.0f}원</b> ({(v_total/v_start-1)*100:+.2f}%) · 기간 손익 {v_chg:+,.0f}원 · 보유 {v_open} · 청산 {v_done}
<span class=mut>· 개시 {esc(str(cfg.get('시작일','')))} · {esc(str(cfg.get('대상','')))}</span></p>

<h2>탐지 활동 (기간 내)</h2>
<table><tr><th>날짜</th><th>A 선지지형</th><th>B 리더형</th></tr>{det_line}</table>
{hist_block}
<p class=warn>⚠️ 기록·참고용 · 매매 추천 아님 · 지수는 합성/재척도(방향·변동성만 유효). 생성: py 진우퀀트_리포트.py --period {a.period}</p>
</div></body></html>"""
    out = os.path.join(HERE, f"리포트_{a.period}_{d8}.html")
    open(out, "w", encoding="utf-8").write(doc)
    print(f"저장: {os.path.basename(out)}")
    print(f"  {mark} 국면 {rg.get('판정','?')} · 지수 {a.period} {pct(chg)} · 가상계좌 {(v_total/v_start-1)*100:+.2f}%")
    if not a.noopen:
        try: webbrowser.open("file://" + os.path.abspath(out))
        except Exception: pass


if __name__ == "__main__":
    main()
