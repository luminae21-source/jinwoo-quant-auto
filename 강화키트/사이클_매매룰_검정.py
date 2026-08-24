#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""사이클_매매룰_검정.py — 테마·사이클 종목을 '언제 타고 언제 내리나' 규칙 검정

진우 질문: 2차전지·이수페타시스(반도체) 같은 사이클·테마 종목엔 '사이클 매매 룰'이 필요하다.
검정: 이런 종목은 파라볼릭 상승 후 급락. 추세 편승(진입)·이탈(청산) 규칙이
      상승사이클을 잡으면서 크래시를 피하는가? 바이앤홀드와 비교.

파트 A (시스템): 고변동 테마 바스켓(top200 유동 중 12m변동성 상위30, 월 EW)에
  · 바이앤홀드
  · 종목별 MA추세 필터(각 종목: 전월말 종가 ≥ K개월 이동평균일 때만 보유, 아니면 현금)  K=6/10/12
  · 종목별 트레일링 스톱(고점 대비 −25% 이탈 시 청산, 재진입=추세복귀)
파트 B (케이스): 2차전지·반도체 실제 종목에 K=10 MA추세룰 vs 바이앤홀드 (상승포착·낙폭회피).

비용: 다올(세금0.2%+슬리피지). 룩어헤드 없음(신호=전월말). ⚠️ 검증용·실현손익 아님·투자자문 아님·책임 본인.
"""
# §8-3(2026-07-27): tax 0.002→0.0015(실제 증권거래세) · slip 0.0005→0.002045(CS 실측 편도) → 왕복 0.300%→0.559%


# ── 경로 자립화 (2026-07-27) — 샌드박스 하드코딩 제거 ──────────────
import os as _os, glob as _glob
_JQ_HERE = _os.path.dirname(_os.path.abspath(__file__))


def _jqroot():
    d = _JQ_HERE
    for _ in range(5):
        if _os.path.exists(_os.path.join(d, "종목시총_30년.csv")):
            return d
        d = _os.path.dirname(d)
    return _os.path.dirname(_JQ_HERE)


BASE = _os.environ.get("JQ_BASE", _jqroot())


def _jqfind(name):
    """이름으로 파일 자동탐색 (백업/보관 폴더 제외)."""
    for b in (BASE, _JQ_HERE, _os.getcwd()):
        hits = [h for h in _glob.glob(_os.path.join(b, "**", name), recursive=True)
                if not any(s in h for s in ("_백업", "_보관", "_archive", "__pycache__"))]
        if hits:
            return sorted(hits, key=len)[0]
    raise FileNotFoundError(f"{name} 를 못 찾음 (루트={BASE})")
# ────────────────────────────────────────────────────────────────

import os, sys, argparse, json
import numpy as np, pandas as pd
BASE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

CASE = {  # 사이클·테마 대표 종목
    "2차전지": {"247540":"에코프로비엠","086520":"에코프로","006400":"삼성SDI","066970":"엘앤에프"},
    "반도체·AI": {"007660":"이수페타시스","042700":"한미반도체","000660":"SK하이닉스","240810":"원익IPS"},
}

def _find(fn):
    for d in (BASE, os.path.dirname(BASE), os.getcwd()):
        p = os.path.join(d, fn)
        if os.path.exists(p): return p
    return None

def load_panel():
    frames = []
    for fn in ("_월봉종가캐시_KOSPI.csv", "_월봉종가캐시_KOSDAQ.csv"):
        p = _find(fn)
        if p:
            d = pd.read_csv(p, dtype={"code": str}); d["code"] = d["code"].str.zfill(6); frames.append(d)
    allc = pd.concat(frames, ignore_index=True)
    px = allc.pivot_table(index="ym", columns="code", values="close", aggfunc="last").sort_index()
    return px, px.pct_change().mask(lambda x: x.abs() > 1.0)

def load_mcap():
    p = _find("종목시총_30년.csv"); d = pd.read_csv(p, dtype={"code": str}); d["code"] = d["code"].str.zfill(6)
    d["ym"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m")
    return d.pivot_table(index="ym", columns="code", values="mcap", aggfunc="last")

def stats(x, ann=12):
    x = pd.Series(x).dropna()
    if len(x) < 6: return None
    c = (1+x).cumprod()
    return dict(CAGR=(1+x).prod()**(ann/len(x))-1, Sharpe=x.mean()/x.std()*np.sqrt(ann) if x.std()>0 else np.nan,
                MDD=(c/c.cummax()-1).min(), n=len(x))

def basket_bt(px, rets, mcap, rule, K=10, univN=200, topvol=30, tax=0.0015, slip=0.002045):
    """고변동 테마 바스켓에 사이클 룰 적용."""
    maK = px.rolling(K).mean()
    months = [m for m in rets.index if m in mcap.index]
    held_w = {}   # code -> 직전 보유여부(비중)
    peak = {}     # 트레일링용 고점
    out = []; kept = []; turns = []
    for t in months:
        i = list(rets.index).index(t)
        if i < max(K, 13) + 1: continue
        mc = mcap.loc[t].dropna().sort_values(ascending=False); univ = list(mc.index[:univN])
        w = rets.iloc[i-13:i-1]; vol = w[[c for c in univ if c in w.columns]].std()
        basket = list(vol.dropna().sort_values(ascending=False).index[:topvol])   # 고변동 상위
        cur = rets.loc[t]; pm = rets.index[i-1]
        cur_w = {}
        for c in basket:
            if pd.isna(cur.get(c)): continue
            hold = True
            if rule == "MA추세":
                pxprev = px.loc[pm, c] if pm in px.index and c in px.columns else np.nan
                maprev = maK.loc[pm, c] if pm in maK.index and c in maK.columns else np.nan
                hold = (pd.notna(pxprev) and pd.notna(maprev) and pxprev >= maprev)
            elif rule == "트레일링-25":
                pxprev = px.loc[pm, c] if (pm in px.index and c in px.columns) else np.nan
                pk = peak.get(c, pxprev)
                if pd.notna(pxprev): pk = max(pk, pxprev); peak[c] = pk
                hold = (pd.notna(pxprev) and pd.notna(pk) and pxprev >= pk * 0.75)
            cur_w[c] = 1.0 if hold else 0.0
        inv = [c for c in cur_w if cur_w[c] > 0]
        if not basket: continue
        # EW over invested; cash = basket - invested (수익 0)
        r = np.mean([cur[c] for c in inv]) * (len(inv)/len(basket)) if inv else 0.0
        # 회전(비중변화 합)
        allc = set(list(cur_w.keys()) + list(held_w.keys()))
        turn = sum(abs(cur_w.get(c,0)/max(len(basket),1) - held_w.get(c,0)/max(len(basket),1)) for c in allc)
        out.append(r - turn*(tax+2*slip)); kept.append(t); turns.append(len(inv)/max(len(basket),1))
        held_w = {c: (1.0 if cur_w.get(c,0)>0 else 0.0) for c in basket}
    return pd.Series(out, index=kept), (np.mean(turns) if turns else 0)

def case_bt(px, rets, code, K=10, tax=0.0015, slip=0.002045):
    """단일 종목: 바이앤홀드 vs MA추세룰. (상장 이후 구간)"""
    s = px[code].dropna() if code in px.columns else pd.Series(dtype=float)
    if len(s) < K+13: return None
    r = rets[code].reindex(s.index)
    maK = s.rolling(K).mean()
    sig = (s >= maK).shift(1)   # 전월말 신호
    bh = r.copy()
    rule = r.where(sig, 0.0)    # 추세 이탈 시 현금(수익 0)
    # 룰 회전비용(진입/이탈 전환)
    flips = sig.fillna(False).astype(int).diff().abs().fillna(0)
    rule = rule - flips*(tax+2*slip)
    return dict(bh=stats(bh.dropna()), rule=stats(rule.dropna()),
                bh_cum=float((1+bh.dropna()).prod()), rule_cum=float((1+rule.dropna()).prod()),
                start=s.index[0], end=s.index[-1], n=len(r.dropna()))

def run(slippage=0.002045):
    px, rets = load_panel(); mcap = load_mcap()
    print("=" * 90)
    print(f"사이클 매매룰 — 고변동 테마 바스켓 (top200 유동 중 12m변동성 상위30, 다올 비용후, 슬립 {slippage*100:.2f}%)")
    print("=" * 90)
    print(f"  {'룰':<20}{'순 CAGR':>10}{'Sharpe':>9}{'MDD':>9}{'평균투자비중':>12}")
    res = {}
    for label, rule, K in [("바이앤홀드","buyhold",0),("MA추세(6개월)","MA추세",6),
                            ("MA추세(10개월)","MA추세",10),("MA추세(12개월)","MA추세",12),
                            ("트레일링 -25%","트레일링-25",0)]:
        s, inv = basket_bt(px, rets, mcap, rule, K=K if K else 10, slip=slippage)
        st = stats(s)
        if st:
            res[label] = dict(cagr=round(st['CAGR']*100,1), sharpe=round(st['Sharpe'],2), mdd=round(st['MDD']*100,1), inv=round(inv*100,0))
            print(f"  {label:<20}{st['CAGR']*100:>9.1f}%{st['Sharpe']:>9.2f}{st['MDD']*100:>8.1f}%{inv*100:>10.0f}%")
    bh = res.get("바이앤홀드",{}); ma = res.get("MA추세(10개월)",{})
    if bh and ma:
        print(f"\n  → MA추세(10m) vs 바이앤홀드: CAGR {ma['cagr']}% vs {bh['cagr']}% · MDD {ma['mdd']}% vs {bh['mdd']}% "
              f"(낙폭 {abs(bh['mdd'])-abs(ma['mdd']):.0f}%p 개선). 사이클 룰 = 상승 편승 + 붕괴 회피.")

    print("\n" + "=" * 90)
    print("케이스: 2차전지·반도체 실제 종목 — 바이앤홀드 vs MA추세(10개월) 룰")
    print("=" * 90)
    print(f"  {'종목':<16}{'구간':<18}{'BH 배수':>9}{'룰 배수':>9}{'BH MDD':>9}{'룰 MDD':>9}{'Sharpe(BH→룰)':>16}")
    cases = {}
    for theme, names in CASE.items():
        for code, nm in names.items():
            c = case_bt(px, rets, code, K=10, slip=slippage)
            if not c or not c['bh'] or not c['rule']: continue
            cases[nm] = c
            print(f"  {nm:<16}{c['start']+'~'+c['end']:<18}{c['bh_cum']:>8.1f}x{c['rule_cum']:>8.1f}x"
                  f"{c['bh']['MDD']*100:>8.1f}%{c['rule']['MDD']*100:>8.1f}%{c['bh']['Sharpe']:>8.2f}→{c['rule']['Sharpe']:<6.2f}")
    # 요약
    if cases:
        avg_bh_mdd = np.mean([c['bh']['MDD'] for c in cases.values()])*100
        avg_rule_mdd = np.mean([c['rule']['MDD'] for c in cases.values()])*100
        avg_bh_sh = np.mean([c['bh']['Sharpe'] for c in cases.values()])
        avg_rule_sh = np.mean([c['rule']['Sharpe'] for c in cases.values()])
        keep = np.mean([c['rule_cum']/c['bh_cum'] for c in cases.values() if c['bh_cum']>0])*100
        print(f"\n  ── 케이스 요약 ──")
        print(f"  · 평균 MDD: 바이앤홀드 {avg_bh_mdd:.0f}% → MA추세룰 {avg_rule_mdd:.0f}% (낙폭 {abs(avg_bh_mdd)-abs(avg_rule_mdd):.0f}%p 완화)")
        print(f"  · 평균 Sharpe: {avg_bh_sh:.2f} → {avg_rule_sh:.2f} · 룰이 지킨 총수익 배수 비율 평균 {keep:.0f}%")
        print(f"  → 사이클 종목: '추세 위에서만 보유' 규칙이 상승의 대부분을 취하며 급락을 크게 줄인다.")
    print("  ⚠️ 월봉·근사룰. 실집행은 매도규칙_라우터(momentum 넓은트레일 3.5ATR/−25%)와 정합. 실현손익 아님·투자자문 아님.")
    out = dict(basket=res, cases={k: dict(bh_x=round(v['bh_cum'],1), rule_x=round(v['rule_cum'],1),
               bh_mdd=round(v['bh']['MDD']*100,1), rule_mdd=round(v['rule']['MDD']*100,1),
               bh_sharpe=round(v['bh']['Sharpe'],2), rule_sharpe=round(v['rule']['Sharpe'],2),
               window=v['start']+'~'+v['end']) for k,v in cases.items()})
    json.dump(out, open(os.path.join(BASE,"사이클_매매룰_검정_결과.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
    print("  저장: 사이클_매매룰_검정_결과.json")
    return out

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--slippage", type=float, default=0.0005); a = ap.parse_args()
    run(a.slippage)

if __name__ == "__main__":
    main()
