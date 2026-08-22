# -*- coding: utf-8 -*-
r"""가상매매.py — 휩쏘 시스템 전진 가상매매 (페이퍼 트레이딩 · 2026-08-17 개시)

[규칙 — 전부 30년 검정에서 확정된 것. 여기서 새로 정하지 않는다]
  자본     : 시작 1,000,000원 (가상매매_설정.json)
  진입 대상: 🟢실행 국면 × 정식 A형만 (휩쏘탐지_YYYYMMDD.csv의 유형 A)
  사이징   : 위험 1%/건 — 수량 = floor(위험액 ÷ (진입가−손절가)). 정수 주식만.
             1주도 위험한도 초과면 '진입불가(자본부족)' 기록 (거르지 않고 기록한다).
             열린 위험 합계 ≤ 6% (히트캡) · 동일 종목 중복 진입 금지(보유 중일 때).
  손절/목표: 매매카드와 동일 — 손절 = 핵심선가×0.95(선이 진입가 위면 2일째저가×0.95),
             목표 = 2일 낙폭 절반 되돌림.
  청산     : 2단 표준 — 목표 도달 시 절반 실현, 잔여는 트레일 −12% + 본전 플로어, 126봉 만기.
             같은 봉 손절·목표 동시 터치 시 손절 우선(보수적).
  비용     : 편도 0.2% (수수료+세금 근사 · 설정에서 조정)
  기록     : 소급 없음 — 2026-08-17 이후 신호만. 건너뛴 신호(국면·히트캡·자본부족)도 전부 기록.

[사용]
  py 가상매매.py --open                  # 최신 휩쏘탐지 CSV에서 신규 진입 처리
  py 가상매매.py --open --date 20260901
  py 가상매매.py                         # 보유 포지션 추적 + 자본곡선 + HTML (기본)
⚠️ 가상매매·기록용. 실제 주문 아님. 매매 추천 아님.
"""
import os, sys, json, glob, argparse, warnings, webbrowser, html as _h
warnings.filterwarnings("ignore")
import numpy as np, pandas as pd

HERE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

CFG_F = os.path.join(HERE, "가상매매_설정.json")
LED_F = os.path.join(HERE, "가상매매_원장.csv")
EQ_F = os.path.join(HERE, "가상매매_자본곡선.csv")
HTML_F = os.path.join(HERE, "가상매매_현황.html")

DEFAULT_CFG = {"시작자본": 1000000, "시작일": "2026-08-17", "위험pct": 1.0, "히트캡pct": 6.0,
               "수수료편도pct": 0.2, "트레일pct": 12.0, "잔여만기봉": 126,
               "대상": "실행국면 × 정식A", "메모": "형 확정(2026-08-17): 자본 100만 · 정식A만"}

COLS = ["진입일", "code", "name", "유형", "등급", "국면", "진입가", "수량", "투입금",
        "손절가", "목표가", "상태", "잔여수량", "실현손익", "트레일고점", "청산일", "청산사유", "갱신일", "메모"]


def cfg():
    if not os.path.exists(CFG_F):
        json.dump(DEFAULT_CFG, open(CFG_F, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    return json.load(open(CFG_F, encoding="utf-8"))


def ledger():
    if not os.path.exists(LED_F):
        pd.DataFrame(columns=COLS).to_csv(LED_F, index=False, encoding="utf-8-sig")
    L = pd.read_csv(LED_F, dtype={"code": str})
    if len(L): L["code"] = L["code"].str.zfill(6)
    return L


def _find(fn):
    for d in (HERE, os.path.dirname(HERE), os.getcwd()):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    return None


def load_daily():
    import importlib.util
    p = _find("휩쏘_관찰.py")
    spec = importlib.util.spec_from_file_location("gw", p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m.load_daily()


def regime(asof=None):
    import importlib.util
    p = _find("시장국면.py")
    if not p: return {"판정": "?", "실행": False}
    spec = importlib.util.spec_from_file_location("sj", p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m.regime_at(asof)


def open_positions(a):
    C = cfg(); L = ledger()
    # 탐지 파일
    src = _find(f"휩쏘탐지_{a.date}.csv") if a.date else None
    if not src:
        fs = sorted(glob.glob(os.path.join(HERE, "휩쏘탐지_*.csv")))
        src = fs[-1] if fs else None
    if not src:
        print("휩쏘탐지_*.csv 없음 — 먼저 py 휩쏘_탐색기.py"); return
    d8 = "".join(c for c in os.path.basename(src) if c.isdigit())[:8]
    asof = f"{d8[:4]}-{d8[4:6]}-{d8[6:]}"
    if asof < C["시작일"]:
        print(f"소급 금지: 탐지일 {asof} < 개시일 {C['시작일']}"); return
    det = pd.read_csv(src, dtype={"code": str}); det["code"] = det["code"].str.zfill(6)
    det = det[det["유형"] == "A"]                       # 정식 A만
    rg = regime(asof)
    mark = {"실행(유리)": "🟢", "주의(중립)": "🟡", "관찰만(불리)": "🔴"}.get(rg.get("판정", ""), "")
    print(f"{mark} {asof} 국면: {rg.get('판정','?')} — {rg.get('이유','')[:60]}")

    # 서킷브레이커 (사전등록 2026-08-22 §4 — 기계 강제): '정지'면 코드가 신규 진입을 거부한다
    circuit = {}
    cp = os.path.join(HERE, "서킷상태.json")
    if os.path.exists(cp):
        try: circuit = json.load(open(cp, encoding="utf-8"))
        except Exception: circuit = {}
    halted = (circuit.get("상태") == "정지")
    if halted:
        print("🔴 서킷브레이커 정지 — 신규 진입 전면 차단: " + " / ".join(circuit.get("사유", ["사유 미기재"])))

    # 자본·열린 위험
    realized = pd.to_numeric(L["실현손익"], errors="coerce").fillna(0).sum() if len(L) else 0.0
    capital = C["시작자본"] + realized
    risk_amt = capital * C["위험pct"] / 100
    open_rows = L[L["상태"].isin(["보유", "절반실현"])] if len(L) else L
    open_risk = 0.0
    for _, r in open_rows.iterrows():
        open_risk += max(0.0, (float(r["진입가"]) - float(r["손절가"]))) * float(r["잔여수량"])
    heat_cap = capital * C["히트캡pct"] / 100

    rows, n_new = [], 0
    for _, r in det.iterrows():
        c = r["code"]; nm = str(r.get("name", c))
        base = dict(진입일=asof, code=c, name=nm, 유형="A", 등급=str(r.get("등급", "")),
                    국면=str(rg.get("판정", ""))[:3].replace("(", ""), 갱신일=asof)
        held = len(L) and ((L["code"] == c) & L["상태"].isin(["보유", "절반실현"])).any()
        px = float(r["종가"]); cum2 = float(r.get("2일누적", np.nan))
        dist = float(r.get("핵심선거리", np.nan))
        lp = px / (1 + dist) if np.isfinite(dist) else np.nan
        below = lp if (np.isfinite(lp) and lp < px) else px * 0.98
        stop = below * 0.95
        target = px + (px / (1 + cum2) - px) * 0.5 if (np.isfinite(cum2) and cum2 < 0) else px * 1.10
        if halted:
            rows.append({**base, "상태": "미진입(서킷정지)", "진입가": px, "수량": 0, "잔여수량": 0,
                         "손절가": round(stop), "목표가": round(target),
                         "메모": "서킷브레이커 정지 — 재가동은 재검정 통과 후"}); continue
        if not rg.get("실행"):
            rows.append({**base, "상태": "미진입(국면)", "진입가": px, "수량": 0, "잔여수량": 0,
                         "손절가": round(stop), "목표가": round(target), "메모": rg.get("판정", "")}); continue
        if held:
            rows.append({**base, "상태": "미진입(보유중복)", "진입가": px, "수량": 0, "잔여수량": 0,
                         "손절가": round(stop), "목표가": round(target)}); continue
        qty = int(risk_amt // max(1e-9, (px - stop)))
        if qty < 1:
            rows.append({**base, "상태": "미진입(자본부족)", "진입가": px, "수량": 0, "잔여수량": 0,
                         "손절가": round(stop), "목표가": round(target),
                         "메모": f"1주 위험 {px-stop:,.0f}원 > 한도 {risk_amt:,.0f}원"}); continue
        add_risk = (px - stop) * qty
        if open_risk + add_risk > heat_cap:
            rows.append({**base, "상태": "미진입(히트캡)", "진입가": px, "수량": 0, "잔여수량": 0,
                         "손절가": round(stop), "목표가": round(target),
                         "메모": f"열린위험 {open_risk:,.0f}+{add_risk:,.0f} > 캡 {heat_cap:,.0f}"}); continue
        cost = px * qty
        if cost > capital - sum(float(x.get("투입금", 0) or 0) for x in rows) - \
                (pd.to_numeric(open_rows["투입금"], errors="coerce").sum() if len(open_rows) else 0):
            rows.append({**base, "상태": "미진입(현금부족)", "진입가": px, "수량": 0, "잔여수량": 0,
                         "손절가": round(stop), "목표가": round(target)}); continue
        open_risk += add_risk; n_new += 1
        rows.append({**base, "상태": "보유", "진입가": px, "수량": qty, "잔여수량": qty,
                     "투입금": round(cost), "손절가": round(stop), "목표가": round(target),
                     "실현손익": 0.0, "트레일고점": px})
        print(f"  ▶ 진입 {nm}({c}) {qty}주 × {px:,.0f} = {cost:,.0f}원 · 손절 {stop:,.0f} · 목표 {target:,.0f}")
    if rows:
        N = pd.DataFrame(rows)
        # 중복 방지: 같은 (진입일, code) 이미 있으면 스킵
        if len(L):
            key = set(zip(L["진입일"].astype(str), L["code"]))
            N = N[~N.apply(lambda x: (str(x["진입일"]), x["code"]) in key, axis=1)]
        L = pd.concat([L, N], ignore_index=True)
        for c_ in COLS:
            if c_ not in L.columns: L[c_] = ""
        L[COLS].to_csv(LED_F, index=False, encoding="utf-8-sig")
    print(f"신규 진입 {n_new}건 · 기록 {len(rows)}건 → 가상매매_원장.csv")


def track(a):
    C = cfg(); L = ledger()
    D = load_daily()
    if D is None: sys.exit("일봉 데이터 없음")
    last = D["date"].max()
    fee = C["수수료편도pct"] / 100
    trail = C["트레일pct"] / 100
    for i, r in L.iterrows():
        if r["상태"] not in ("보유", "절반실현"): continue
        g = D[(D["code"] == r["code"]) & (D["date"] > str(r["진입일"]))].sort_values("date")
        if not len(g): continue
        entry = float(r["진입가"]); qty0 = int(r["수량"])
        stop0 = float(r["손절가"]); target = float(r["목표가"])
        h = g["high"].values.astype(float); l = g["low"].values.astype(float)
        c_ = g["close"].values.astype(float); dts = g["date"].values.astype(str)
        # 진입 상태부터 재시뮬 (멱등)
        state = "보유"; rem = qty0; realized = -entry * qty0 * fee   # 매수 수수료
        stop = stop0; peak = entry; exit_d = ""; why = ""
        for j in range(len(c_)):
            if l[j] <= stop:
                px = stop
                realized += px * rem * (1 - fee) - 0 if False else (px * rem) * (1 - fee)
                realized -= entry * rem            # 원가 차감
                rem = 0; state = "청산"; exit_d = dts[j]
                why = "손절" if stop <= stop0 * 1.0001 else ("본전청산" if abs(stop - entry) < entry * 0.001 else "트레일")
                break
            if state == "보유" and h[j] >= target:
                half = qty0 // 2 if qty0 >= 2 else qty0
                realized += target * half * (1 - fee) - entry * half
                rem -= half
                state = "절반실현" if rem > 0 else "청산"
                if rem == 0: exit_d = dts[j]; why = "목표전량"
                else: stop = max(stop, entry)      # 본전 플로어
            peak = max(peak, h[j])
            if state == "절반실현":
                stop = max(stop, entry, peak * (1 - trail))
            if j >= C["잔여만기봉"] - 1 and rem > 0:
                px = c_[j]
                realized += px * rem * (1 - fee) - entry * rem
                rem = 0; state = "청산"; exit_d = dts[j]; why = "만기"
                break
        L.at[i, "상태"] = state; L.at[i, "잔여수량"] = rem
        L.at[i, "실현손익"] = round(realized, 0)
        L.at[i, "트레일고점"] = round(peak, 0)
        L.at[i, "청산일"] = exit_d; L.at[i, "청산사유"] = why
        L.at[i, "갱신일"] = last
        # 평가
        curpx = float(c_[-1])
        L.at[i, "메모"] = f"현재 {curpx:,.0f}" if state != "청산" else L.at[i, "메모"]
    if len(L):
        L[COLS].to_csv(LED_F, index=False, encoding="utf-8-sig")

    # 자본·평가
    realized_sum = pd.to_numeric(L["실현손익"], errors="coerce").fillna(0).sum() if len(L) else 0.0
    mtm = 0.0
    open_rows = L[L["상태"].isin(["보유", "절반실현"])] if len(L) else L
    for _, r in open_rows.iterrows():
        g = D[(D["code"] == r["code"]) & (D["date"] <= last)]
        if len(g): mtm += float(g["close"].iloc[-1]) * float(r["잔여수량"])
    capital = C["시작자본"] + realized_sum
    total = capital + mtm - sum(float(r["진입가"]) * float(r["잔여수량"]) for _, r in open_rows.iterrows())
    # ↑ 실현손익은 원가 차감 방식이라 잔여분 원가는 아직 자본에 남아있음 → 평가는 잔여 시가-원가 가산
    eq_row = pd.DataFrame([dict(date=last, 실현누적=round(realized_sum), 평가포함자산=round(total),
                                수익률pct=round((total / C["시작자본"] - 1) * 100, 2))])
    if os.path.exists(EQ_F):
        E = pd.read_csv(EQ_F); E = E[E["date"] != last]
        E = pd.concat([E, eq_row], ignore_index=True)
    else:
        E = eq_row
    E.to_csv(EQ_F, index=False, encoding="utf-8-sig")

    print("=" * 88)
    print(f" 가상매매 현황 — {last} · 시작 {C['시작자본']:,.0f}원 ({C['시작일']}~)")
    print("=" * 88)
    if not len(L):
        print("  아직 거래 없음 — 다음 🟢실행 국면의 정식 A 신호부터 시작된다. (소급 없음)")
    else:
        for st in ("보유", "절반실현", "청산"):
            sub = L[L["상태"] == st]
            if len(sub): print(f"  {st:<5} {len(sub)}건")
        skips = L[L["상태"].str.startswith("미진입")] if len(L) else L
        if len(skips): print(f"  미진입 기록 {len(skips)}건 ({skips['상태'].value_counts().to_dict()})")
    print(f"  실현손익 누적 {realized_sum:+,.0f}원 · 총자산(평가) {total:,.0f}원 ({(total/C['시작자본']-1)*100:+.2f}%)")
    write_html(L, E, C, last)
    print(f" 저장: 가상매매_원장.csv · 가상매매_자본곡선.csv · 가상매매_현황.html")
    if not a.noopen:
        try: webbrowser.open("file://" + os.path.abspath(HTML_F))
        except Exception: pass


def write_html(L, E, C, last):
    esc = _h.escape
    rows = ""
    if len(L):
        for _, r in L.sort_values("진입일", ascending=False).iterrows():
            st = str(r["상태"])
            cl = {"보유": "var(--a)", "절반실현": "var(--b)", "청산": "var(--good)"}.get(st, "var(--mut)")
            pnl = pd.to_numeric(pd.Series([r["실현손익"]]), errors="coerce").iloc[0]
            pnls = f"{pnl:+,.0f}" if pd.notna(pnl) and str(r['수량']) not in ("0", "", "nan") else "-"
            rows += (f"<tr><td>{r['진입일']}</td><td>{esc(str(r['name']))} <span class=c>{r['code']}</span></td>"
                     f"<td><span style='color:{cl};font-weight:700'>{esc(st)}</span></td>"
                     f"<td class=n>{r['수량']}</td><td class=n>{pd.to_numeric(pd.Series([r['진입가']]),errors='coerce').iloc[0]:,.0f}</td>"
                     f"<td class=n>{pd.to_numeric(pd.Series([r['손절가']]),errors='coerce').iloc[0]:,.0f}</td>"
                     f"<td class=n>{pd.to_numeric(pd.Series([r['목표가']]),errors='coerce').iloc[0]:,.0f}</td>"
                     f"<td class=n>{pnls}</td><td>{esc(str(r['청산사유'] or ''))}</td>"
                     f"<td class=c>{esc(str(r['메모'] or ''))}</td></tr>")
    else:
        rows = "<tr><td colspan=10 style='color:var(--mut)'>거래 없음 — 다음 🟢실행 × 정식A 신호부터 (소급 없음)</td></tr>"
    tot = E["평가포함자산"].iloc[-1] if len(E) else C["시작자본"]
    ret = (tot / C["시작자본"] - 1) * 100
    # 자본곡선 미니차트
    svg = ""
    if len(E) >= 2:
        xs = np.arange(len(E)); ys = E["평가포함자산"].values.astype(float)
        lo, hi = ys.min() * 0.995, ys.max() * 1.005
        pts = " ".join(f"{20+x/(len(E)-1)*660:.1f},{110-(y-lo)/(hi-lo)*90:.1f}" for x, y in zip(xs, ys))
        svg = (f"<svg viewBox='0 0 700 120' width='100%' style='max-width:700px'>"
               f"<polyline points='{pts}' fill='none' stroke='var(--a)' stroke-width='2'/></svg>")
    doc = f"""<!DOCTYPE html><html lang=ko><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>가상매매 현황 {last}</title><style>
:root{{color-scheme:light;--bg:#f6f6f4;--sf:#fcfcfb;--bd:#e3e2dd;--ink:#0f0f0e;--ink2:#54534e;--mut:#8a877e;--a:#2a78d6;--b:#eb6834;--good:#1a7f4b;--bad:#c0342f}}
@media(prefers-color-scheme:dark){{:root{{color-scheme:dark;--bg:#111110;--sf:#1a1a19;--bd:#33322f;--ink:#fafaf7;--ink2:#c3c2b7;--mut:#8f8e85;--a:#3987e5;--b:#d95926;--good:#4bb87c;--bad:#e0655a}}}}
*{{box-sizing:border-box}}body{{margin:0;background:var(--bg);color:var(--ink);font-family:-apple-system,BlinkMacSystemFont,"Malgun Gothic","Apple SD Gothic Neo",sans-serif;font-size:14px;line-height:1.6}}
.w{{max-width:940px;margin:0 auto;padding:34px 20px 70px}}h1{{font-size:22px;margin:0 0 4px}}
.sub{{color:var(--ink2);margin:0 0 10px;font-size:13px}}
.k{{display:flex;gap:12px;flex-wrap:wrap;margin:12px 0}}
.kb{{flex:1;min-width:150px;background:var(--sf);border:1px solid var(--bd);border-radius:10px;padding:11px 13px}}
.kb .v{{font-size:20px;font-weight:700}}.kb .l{{font-size:11.5px;color:var(--mut)}}
table{{width:100%;border-collapse:collapse;font-size:12.5px;margin-top:10px}}
th,td{{text-align:left;padding:6px 8px;border-bottom:1px solid var(--bd);white-space:nowrap}}
th{{color:var(--ink2);font-size:11px;font-weight:650}}td.n{{text-align:right;font-variant-numeric:tabular-nums}}
.c{{color:var(--mut);font-size:10.5px}}
.warn{{color:var(--mut);font-size:12px;margin-top:16px;border-top:1px solid var(--bd);padding-top:10px}}
</style></head><body><div class=w>
<h1>가상매매 현황 · {last}</h1>
<p class=sub>전진 전용({C['시작일']}~ 소급 없음) · 🟢실행 × 정식A · 위험 1%/건 · 히트캡 6% · 2단 청산 표준 · 비용 편도 {C['수수료편도pct']}%</p>
<div class=k>
<div class=kb><div class=v>{tot:,.0f}원</div><div class=l>총자산 (시작 {C['시작자본']:,.0f})</div></div>
<div class=kb><div class=v style='color:var({"--good" if ret>=0 else "--bad"})'>{ret:+.2f}%</div><div class=l>누적 수익률</div></div>
<div class=kb><div class=v>{len(L[L['상태'].isin(['보유','절반실현'])]) if len(L) else 0}</div><div class=l>보유 포지션</div></div>
<div class=kb><div class=v>{len(L[L['상태']=='청산']) if len(L) else 0}</div><div class=l>청산 완료</div></div>
</div>
{svg}
<table><tr><th>진입일</th><th>종목</th><th>상태</th><th>수량</th><th>진입가</th><th>손절</th><th>목표</th><th>실현손익</th><th>사유</th><th>메모</th></tr>
{rows}</table>
<p class=warn>⚠️ 가상매매 — 실제 주문 아님 · 매매 추천 아님. 미진입(국면/자본부족/히트캡)도 기록해 규칙의 정직한 성적을 남긴다.
갱신: py 가상매매.py (주간 자동갱신 스케줄에 포함됨)</p>
</div></body></html>"""
    open(HTML_F, "w", encoding="utf-8").write(doc)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--open", action="store_true", help="탐지 CSV에서 신규 진입 처리")
    ap.add_argument("--date", default=None)
    ap.add_argument("--noopen", action="store_true")
    a = ap.parse_args()
    if a.open: open_positions(a)
    track(a)


if __name__ == "__main__":
    main()
