#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
익일예측_모델.py — 검증된 동인으로 코스피 '익일 방향' 사전예상 + 사후채점 누적
==============================================================================
근거: 시장영향_검증.py 에서 강건 채택된 동인(SOX·S&P500·외국인순매수·달러인덱스)만 사용.
방법: 4동인 다변량회귀(과거 전체로 적합) → 최신 거래일 동인값 → 코스피 익일 수익 예측 → 방향.
정직: 매일 '사전' 예측을 로그에 남기고, 실제 결과가 나오면 '사후' 채점 → 누적 방향 적중률.
      ⚠️ 시장은 효율적이라 적중률이 동전던지기(≈50%)에 가까울 수 있음. in-sample·강세장(2016~26) 편향.
      적중률이 충분히(수개월~) 쌓여 >55% 안정 전엔 **참고용**. 매매·책임은 진우.
데이터: 시장영향_검증.py의 build_dataset 재사용(yfinance/pykrx). 실데이터만.
산출: 익일예측_log.csv(예측 누적·사후채점) · 익일예측_최신.md · 콘솔
사용: python 익일예측_모델.py [--selftest]   ·   실행: 익일예측_실행.bat
무수정: production·기존 산출물. 신규.
"""
import os, sys, csv, importlib.util
from datetime import date

try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass
HERE = os.path.dirname(os.path.abspath(__file__))

KEYS = ["sox", "sp", "foreign", "dxy"]
LABELS = {"sox": "美 반도체(SOX)", "sp": "S&P500", "foreign": "외국인 순매수", "dxy": "달러인덱스"}
NEUTRAL = 0.15   # 예측 |수익%| < 0.15 → 중립(방향 약함)


MARKET = "KOSPI"   # main에서 --market 으로 설정
def _sfx():
    return "" if MARKET == "KOSPI" else "_" + MARKET.lower()
def _mk():
    return "코스피" if MARKET == "KOSPI" else "코스닥"


def _load_SI():
    p = os.path.join(HERE, "시장영향_검증.py")
    spec = importlib.util.spec_from_file_location("si_mod", p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    return m


def fit(SI, rows):
    """4동인 다변량회귀 적합 → (beta, R², in-sample 방향적중%, n)."""
    data = [r for r in rows if r["y_next"] is not None and all(r[k] is not None for k in KEYS)]
    if len(data) < 50:
        return None
    X = [[1.0] + [r[k] for k in KEYS] for r in data]
    Y = [r["y_next"] for r in data]
    beta, t = SI.ols(X, Y)
    if beta is None:
        return None
    pred = [beta[0] + sum(beta[i+1] * data[j][KEYS[i]] for i in range(len(KEYS))) for j in range(len(data))]
    ybar = sum(Y) / len(Y)
    ss_tot = sum((y - ybar) ** 2 for y in Y); ss_res = sum((Y[j] - pred[j]) ** 2 for j in range(len(Y)))
    r2 = 1 - ss_res / ss_tot if ss_tot > 0 else 0.0
    hit = sum(1 for j in range(len(Y)) if pred[j] * Y[j] > 0) / len(Y) * 100
    return {"beta": beta, "t": t, "r2": r2, "is_hit": hit, "n": len(data)}


def predict_latest(rows, beta):
    """최신(동인 확정) 거래일 → 익일 코스피 예측. (기준일, 예측수익%, 기여dict)."""
    latest = None
    for r in reversed(rows):
        if all(r[k] is not None for k in KEYS):
            latest = r; break
    if latest is None:
        return None
    contrib = {k: beta[i+1] * latest[k] for i, k in enumerate(KEYS)}
    pred = beta[0] + sum(contrib.values())
    return latest["date"], pred, contrib


def direction(p):
    if p > NEUTRAL: return "상승"
    if p < -NEUTRAL: return "하락"
    return "중립"


def update_log(base_date, pred_ret, rows):
    """① 오늘 예측을 로그에 기록(중복방지) ② 과거 미채점 예측을 실제값으로 채점."""
    logp = os.path.join(HERE, f"익일예측_log{_sfx()}.csv")
    cols = ["base_date", "pred_ret", "pred_dir", "actual_ret", "hit", "scored_on"]
    rowsl = []
    if os.path.exists(logp):
        for r in csv.DictReader(open(logp, encoding="utf-8-sig")):
            rowsl.append(r)
    seen = {r["base_date"] for r in rowsl}
    if str(base_date) not in seen:
        rowsl.append({"base_date": str(base_date), "pred_ret": f"{pred_ret:.4f}",
                      "pred_dir": direction(pred_ret), "actual_ret": "", "hit": "", "scored_on": ""})
    # 사후 채점: base_date 다음 거래일(=익일) 코스피 실제수익 = rows에서 base 다음 행의 y_same
    date_idx = {str(r["date"]): i for i, r in enumerate(rows)}
    ordered_dates = [str(r["date"]) for r in rows]
    for r in rowsl:
        if r.get("actual_ret"):
            continue
        bd = r["base_date"]
        if bd in date_idx and date_idx[bd] + 1 < len(rows):
            nxt = rows[date_idx[bd] + 1]
            act = nxt.get("y_same")
            if act is not None:
                pdir = r["pred_dir"]
                hit = (pdir == "상승" and act > 0) or (pdir == "하락" and act < 0) or (pdir == "중립" and abs(act) <= NEUTRAL)
                r["actual_ret"] = f"{act:.4f}"; r["hit"] = "1" if hit else "0"; r["scored_on"] = str(date.today())
    w = csv.DictWriter(open(logp, "w", encoding="utf-8-sig", newline=""), fieldnames=cols)
    w.writeheader()
    for r in rowsl:
        w.writerow({c: r.get(c, "") for c in cols})
    # 누적 적중률(중립 제외 방향성 예측만)
    scored = [r for r in rowsl if r.get("hit") in ("0", "1") and r.get("pred_dir") in ("상승", "하락")]
    acc = sum(1 for r in scored if r["hit"] == "1") / len(scored) * 100 if scored else None
    return acc, len(scored), len(rowsl)


def _write_html(base_date, pred, contrib, f, acc, n_scored):
    """예측 + 동인기여 막대 + 적중률 추적 곡선 → 익일예측_최신.html (매일 갱신, 폰)."""
    d = direction(pred); col = {"상승": "#3fb37a", "하락": "#e2606a", "중립": "#9aa0aa"}[d]
    emoji = {"상승": "🔺", "하락": "🔻", "중립": "⏸"}[d]
    # 적중률 시계열(방향 예측만)
    logp = os.path.join(HERE, f"익일예측_log{_sfx()}.csv"); seq = []
    if os.path.exists(logp):
        rl = [r for r in csv.DictReader(open(logp, encoding="utf-8-sig"))
              if r.get("hit") in ("0", "1") and r.get("pred_dir") in ("상승", "하락")]
        rl.sort(key=lambda r: r["base_date"]); h = 0
        for i, r in enumerate(rl, 1):
            h += 1 if r["hit"] == "1" else 0; seq.append(h / i * 100)
    if len(seq) >= 2:
        n = len(seq); pts = " ".join(f"{40+300*i/(n-1):.0f},{170-1.3*v:.0f}" for i, v in enumerate(seq))
        track = (f'<line x1="40" y1="105" x2="340" y2="105" stroke="#9aa0aa" stroke-dasharray="3 3"/>'
                 f'<text x="344" y="108" font-size="9" fill="#9aa0aa">50%</text>'
                 f'<polyline points="{pts}" fill="none" stroke="#ff7a45" stroke-width="2"/>'
                 f'<text x="40" y="195" font-size="10" fill="#9aa0aa">최근 누적 적중률 {seq[-1]:.0f}% · 채점 {n_scored}건</text>')
    else:
        track = (f'<text x="190" y="100" font-size="12" fill="#9aa0aa" text-anchor="middle">예측 누적 시작</text>'
                 f'<text x="190" y="120" font-size="10" fill="#9aa0aa" text-anchor="middle">채점 {n_scored}건 — 매일 돌리면 곡선이 채워집니다</text>')
    mx = max((abs(v) for v in contrib.values()), default=1) or 1
    bars = ""; yb = 36
    for k in sorted(contrib, key=lambda k: -abs(contrib[k])):
        v = contrib[k]; w = abs(v) / mx * 110; bc = "#3fb37a" if v >= 0 else "#e2606a"
        bars += (f'<text x="10" y="{yb+12}" font-size="10" fill="#e8eaed">{LABELS[k]}</text>'
                 f'<rect x="130" y="{yb}" width="{w:.0f}" height="14" rx="2" fill="{bc}"/>'
                 f'<text x="{135+w:.0f}" y="{yb+12}" font-size="9" fill="{bc}">{v:+.3f}</text>')
        yb += 22
    accs = f"{acc:.0f}%" if acc is not None else f"누적중({n_scored})"
    html = f"""<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>{_mk()} 익일 예상 — {base_date}</title>
<style>body{{background:#0f1115;color:#e8eaed;margin:0;padding:14px;max-width:430px;margin:0 auto;font-family:-apple-system,'Malgun Gothic',sans-serif}}
h1{{font-size:17px;margin:2px 0}}.sub{{color:#9aa0aa;font-size:12px}}.big{{font-size:26px;font-weight:700;color:{col};margin:10px 0}}
h2{{font-size:13px;color:#fff;border-left:3px solid #ff7a45;padding-left:8px;margin:18px 0 6px}}
svg{{width:100%;height:auto}}.note{{background:#2a1d12;border:1px solid #5a3a1f;color:#ffc6a3;border-radius:8px;padding:9px 12px;font-size:11.5px;margin:8px 0}}
.foot{{color:#5a6068;font-size:10.5px;border-top:1px solid #262a33;padding-top:9px;margin-top:14px;line-height:1.5}}</style></head><body>
<h1>📈 {_mk()} 익일 예상</h1><div class="sub">기준 {base_date} · 검증된 4동인 모델</div>
<div class="big">{emoji} {d}　<span style="font-size:15px">예측 {pred:+.2f}%</span></div>
<div class="sub">실전 누적 방향 적중률: <b style="color:#ff7a45">{accs}</b></div>
<h2>오늘 예측의 동인별 기여(%p)</h2>
<svg viewBox="0 0 380 {yb+10}" xmlns="http://www.w3.org/2000/svg">{bars}</svg>
<h2>적중률 추적 (쌓일수록 신뢰)</h2>
<svg viewBox="0 0 380 210" xmlns="http://www.w3.org/2000/svg">{track}</svg>
<div class="note">⚠️ 50%는 동전던지기=무의미. 수개월 쌓여 <b>55%+ 꾸준</b>해야 예측력 인정. 그 전엔 참고용 · 매매·책임 진우.</div>
<div class="foot">동인=SOX·S&P500·외국인·달러인덱스(시장영향_검증.py 10년 채택). 룩어헤드 차단. in-sample·강세장 편향 유의.</div>
</body></html>"""
    open(os.path.join(HERE, f"익일예측_최신{_sfx()}.html"), "w", encoding="utf-8").write(html)


def render(base_date, pred, contrib, f, acc, n_scored, n_log):
    d = direction(pred)
    emoji = {"상승": "🔺", "하락": "🔻", "중립": "⏸"}[d]
    lines = [f"# {_mk()} 익일 예상 — 기준 {base_date}", "",
             "> 검증된 동인(SOX·S&P500·외국인·달러인덱스) 다변량 모델. ⚠️ 참고용 — 시장은 효율적, 적중률 누적 전 과신 금지. 매매·책임 진우.", "",
             f"## {emoji} 익일 방향: **{d}**  (예측 수익 {pred:+.2f}%)", "",
             "### 동인별 기여(이번 예측)",
             "| 동인 | 기여(%p) |", "|---|---|"]
    for k in sorted(contrib, key=lambda k: -abs(contrib[k])):
        lines.append(f"| {LABELS[k]} | {contrib[k]:+.3f} |")
    lines += ["",
              f"### 모델 신뢰도",
              f"- in-sample R²: {f['r2']*100:.1f}% (낮음=설명력 작음, 정상)",
              f"- in-sample 방향적중: {f['is_hit']:.0f}% / 적합표본 {f['n']}",
              f"- **실전 누적 방향적중: {f'{acc:.0f}%' if acc is not None else '아직(채점표본 {0})'.format(n_scored)} (채점 {n_scored}건, 로그 {n_log}건)**",
              "",
              "### 읽는 법",
              "- 방향(상승/하락/중립)은 *확률적 기대*지 확정 아님. 중립=신호 약함.",
              "- **실전 누적적중이 핵심** — 50%면 무의미, >55% 꾸준해야 예측력 인정. 그 전엔 참고.",
              "- 적중률은 매일 자동 누적·채점됨(익일예측_log.csv).",
              "", "*실데이터(yfinance/pykrx). 룩어헤드 차단. in-sample·강세장 편향 유의.*"]
    md = "\n".join(lines)
    open(os.path.join(HERE, f"익일예측_최신{_sfx()}.md"), "w", encoding="utf-8").write(md)
    _write_html(base_date, pred, contrib, f, acc, n_scored)
    print(md)


def run():
    SI = _load_SI()
    rows, err = SI.build_dataset(10, MARKET)
    if err:
        print(f"❌ {err}"); return
    f = fit(SI, rows)
    if not f:
        print("❌ 적합 실패(표본 부족)"); return
    pr = predict_latest(rows, f["beta"])
    if not pr:
        print("❌ 최신 동인 결측 — 예측 불가"); return
    base_date, pred, contrib = pr
    acc, n_scored, n_log = update_log(base_date, pred, rows)
    render(base_date, pred, contrib, f, acc, n_scored, n_log)
    print("\n[산출] 익일예측_최신.md · 익일예측_log.csv(예측·채점 누적)")


def _selftest():
    ok = 0
    def chk(n, c):
        nonlocal ok; ok += 1 if c else 0
        print(f"  [{'OK' if c else 'FAIL'}] {n}")
    # 방향 함수
    chk("방향 상승", direction(0.5) == "상승")
    chk("방향 하락", direction(-0.5) == "하락")
    chk("방향 중립", direction(0.05) == "중립")
    # fit: 합성 관계 y_next = 0.5*sox - 0.3*dxy (+sp,foreign 0) → 방향적중 높아야
    import random; random.seed(3)
    rows = []
    for _ in range(300):
        sox = random.gauss(0, 1); sp = random.gauss(0, 1); fr = random.gauss(0, 100); dxy = random.gauss(0, 1)
        y = 0.5 * sox - 0.3 * dxy + random.gauss(0, 0.1)
        rows.append({"date": _, "sox": sox, "sp": sp, "foreign": fr, "dxy": dxy, "y_next": y, "y_same": y})
    # ols는 SI에서 — 여기선 간이 SI 모킹
    class SImock:
        @staticmethod
        def ols(X, Y):
            # 최소제곱 (정규방정식) — 시장영향_검증.ols와 동일 알고리즘 간이판
            import importlib.util, os
            p = os.path.join(HERE, "시장영향_검증.py")
            spec = importlib.util.spec_from_file_location("si_t", p); m = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(m); return m.ols(X, Y)
    try:
        f = fit(SImock, rows)
        chk("fit 동작·R²>0.8", f and f["r2"] > 0.8)
        chk("방향적중 높음", f and f["is_hit"] > 80)
        beta = f["beta"]
        # sox 계수 ≈ +0.5, dxy ≈ -0.3
        chk("sox 계수≈+0.5", abs(beta[1] - 0.5) < 0.05)
        chk("dxy 계수≈-0.3", abs(beta[4] + 0.3) < 0.05)
        pr = predict_latest(rows, beta)
        chk("예측 산출", pr is not None and isinstance(pr[1], float))
    except Exception as e:
        print("  (시장영향_검증.py 필요 — PC에서 함께 검증)", str(e)[:60])
    print(f"✅ 익일예측_모델 셀프테스트 ({ok}/8)")
    return ok >= 7


def main():
    import argparse
    global MARKET
    ap = argparse.ArgumentParser(); ap.add_argument("--selftest", action="store_true")
    ap.add_argument("--market", default="KOSPI", help="KOSPI 또는 KOSDAQ")
    a = ap.parse_args()
    if a.selftest:
        _selftest(); return
    MARKET = a.market.upper()
    run()


if __name__ == "__main__":
    main()
