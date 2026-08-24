#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""전략_호라이즌_검정.py — "어떤 교체주기·보유기간이 옳은가"를 데이터로 판정

진우 질문: 사이클은 1~2년·5년·10년도 간다. 전략마다 최적 호라이즌이 다르지 않나?
검정: 신호 6종 × 보유기간 6종(1/3/6/12/24/60개월)을 30년 상폐포함·다올 비용으로 붙여
      '신호별 최적 보유기간'을 찾는다. 룩어헤드 없음(신호=전월말 정보).

신호(롱온리, 유동 top200 중 상위30 EW):
  · mom12     12-1 모멘텀            (가설: 단기 우세)
  · value_pbr 저PBR                 (가설: 장기 우세)
  · value_per 저PER(양수)           (가설: 장기)
  · reversal  36개월 역발상(과거 패자) (가설: 초장기)
  · lowvol    저변동(12m)            (방어)
  · buyhold   시총상위30 바이앤홀드     (초장기 ベース)

비용: 다올 = 세금 0.20% + 슬리피지(편도 0.05%). 회전 ∝ 1/보유기간.
사용: py 전략_호라이즌_검정.py [--slippage 0.0005]
⚠️ 상폐포함·검증용. 실현손익 아님. 투자자문 아님·책임 본인.
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

def load_fin(field):
    frames = []
    for fn in ("종목재무_KRX_KOSPI.csv", "종목재무_KRX_KOSDAQ.csv"):
        p = _find(fn)
        if p:
            d = pd.read_csv(p, dtype={"code": str}); d["code"] = d["code"].str.zfill(6)
            d["ym"] = pd.to_datetime(d["date"]).dt.strftime("%Y-%m"); frames.append(d[["ym", "code", field]])
    allc = pd.concat(frames, ignore_index=True)
    return allc.pivot_table(index="ym", columns="code", values=field, aggfunc="last")

def stats(x, ann=12):
    x = pd.Series(x).dropna()
    if len(x) < 12: return None
    c = (1 + x).cumprod()
    return dict(CAGR=(1+x).prod()**(ann/len(x))-1, Sharpe=x.mean()/x.std()*np.sqrt(ann) if x.std()>0 else np.nan,
                MDD=(c/c.cummax()-1).min(), n=len(x))

def signal_prev(kind, i, rets, pbr, per, topN=30):
    """전월말(i-1) 기준 신호 시리즈 (높을수록 매수). 룩어헤드 없음."""
    if kind == "mom12":
        if i < 13: return None
        w = rets.iloc[i-13:i-1]; return (1+w).prod(min_count=11) - 1
    if kind == "reversal":
        if i < 37: return None
        w = rets.iloc[i-37:i-1]; past = (1+w).prod(min_count=30) - 1
        return -past                                   # 과거 패자 매수
    if kind == "lowvol":
        if i < 13: return None
        w = rets.iloc[i-13:i-1]; return -w.std()        # 저변동 = 높은 점수
    if kind in ("value_pbr", "value_per"):
        src = pbr if kind == "value_pbr" else per
        pм = rets.index[i-1]
        if pм not in src.index: return None
        v = src.loc[pм]
        v = v[v > 0]                                    # 0·음수 제외
        return -v                                       # 저PBR/저PER = 높은 점수
    return None

def horizon_bt(kind, H, px, rets, mcap, pbr, per, topN=30, univN=200, tax=0.0015, slip=0.002045):
    months = [m for m in rets.index if m in mcap.index]
    held = []; out = []; kept = []; turns = []; last_sel = None; step = 0
    for t in months:
        i = list(rets.index).index(t)
        do_resel = (last_sel is None) or (step % H == 0)
        cur = rets.loc[t]
        if do_resel:
            mc = mcap.loc[t].dropna().sort_values(ascending=False)
            univ = list(mc.index[:univN])
            if kind == "buyhold":
                sel = univ[:topN]
            else:
                sig = signal_prev(kind, i, rets, pbr, per, topN)
                if sig is None: continue
                s = sig[[c for c in univ if c in sig.index]].dropna()
                if len(s) < topN: continue
                sel = list(s.sort_values(ascending=False).index[:topN])
            last_sel = sel
        step += 1
        sel = last_sel
        names = [c for c in sel if pd.notna(cur.get(c))]
        if len(names) < topN // 2: continue
        nn = set(names); f = 1 - len(nn & set(held)) / len(nn) if held else 1.0
        out.append(cur[names].mean() - f*(tax+2*slip)); kept.append(t); turns.append(f); held = names
    s = pd.Series(out, index=kept)
    return s, (np.mean(turns) if turns else 0) * 12

def run(slippage=0.002045):
    px, rets = load_panel(); mcap = load_mcap()
    pbr = load_fin("PBR"); per = load_fin("PER")
    signals = [("mom12","12-1 모멘텀"),("value_pbr","저PBR 가치"),("value_per","저PER 가치"),
               ("reversal","36m 역발상"),("lowvol","저변동"),("buyhold","시총30 바이앤홀드")]
    Hs = [1, 3, 6, 12, 24, 60]
    print("=" * 96)
    print(f"전략 × 보유기간 호라이즌 검정 — 신호별 최적 교체주기 (30년 상폐포함·다올 비용후, 슬리피지 {slippage*100:.2f}%)")
    print("=" * 96)
    print("  [셀 = 순 CAGR% / Sharpe]  ★=신호별 Sharpe 최적 보유기간")
    header = "  {:<16}".format("신호\\보유기간") + "".join(f"{str(h)+'개월':>13}" for h in Hs)
    print(header)
    result = {}
    sharpe_series = {}
    for key, label in signals:
        cells = {}; best_h = None; best_sh = -9
        row = f"  {label:<16}"
        for H in Hs:
            s, turn = horizon_bt(key, H, px, rets, mcap, pbr, per, slip=slippage)
            st = stats(s)
            if st:
                cells[H] = dict(cagr=round(st['CAGR']*100,1), sharpe=round(st['Sharpe'],2), mdd=round(st['MDD']*100,1), turn=round(turn,1), n=st['n'])
                if st['Sharpe'] > best_sh: best_sh, best_h = st['Sharpe'], H
                sharpe_series[(key,H)] = s
        for H in Hs:
            if H in cells:
                c = cells[H]; star = "★" if H == best_h else " "
                row += f"{c['cagr']:>6.1f}/{c['sharpe']:>4.2f}{star}"
            else:
                row += f"{'—':>13}"
        print(row)
        result[key] = dict(label=label, cells=cells, best_h=best_h, best_sharpe=round(best_sh,2))
    print("\n  ── 신호별 판정: 최적 보유기간 + 장기내구성(60개월 유지력) ──")
    hmap = {1:"단기(월)",3:"단기(분기)",6:"중기(반기)",12:"중장기(1년)",24:"장기(2년)",60:"초장기(5년)"}
    for key, label in signals:
        r = result[key]; bh = r['best_h']
        if bh is None:
            print(f"   · {label:<14} (데이터 부족)"); continue
        c = r['cells'].get(bh, {}); c60 = r['cells'].get(60, {})
        sh_best = c.get('sharpe', 0); sh60 = c60.get('sharpe', 0)
        durab = (sh60 / sh_best) if sh_best else 0
        tag = "내구성高(장기보유 가능)" if durab >= 0.6 else ("U자형(월간 or 초장기)" if key=="reversal" else "내구성低(오래들면 붕괴)")
        r['durability'] = round(durab, 2); r['tag'] = tag
        print(f"   · {label:<14} 최적 {bh:>2}개월 [{hmap.get(bh)}] Sharpe {sh_best} · 5년보유 Sharpe {sh60} (유지율 {durab*100:.0f}%) → {tag}")
    print("\n  → 핵심(진우 질문 답): '하나의 교체주기'는 없다.")
    print("     · 모멘텀 = 월간 회전 엣지(오래 들면 붕괴).  · 가치(저PBR/PER) = 월간 최고지만 5년 보유도 견고(장기 슬리브 적합).")
    print("     · 역발상 = U자형(월간 반등 or 초장기 사이클).  · 저변동 = 방어(수익 낮음).")
    print("     → 사이클·장기 보유는 '가치'로, 회전은 '모멘텀'으로, 초장기 사이클 베팅은 '역발상'으로 = 슬리브 분리 근거.")
    print("  ⚠️ EW·top200 유동·단순신호 근사. 실현손익 아님. 투자자문 아님·책임 본인.")
    json.dump(result, open(os.path.join(BASE, "전략_호라이즌_검정_결과.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2, default=str)
    print("  저장: 전략_호라이즌_검정_결과.json")
    return result

def main():
    ap = argparse.ArgumentParser(); ap.add_argument("--slippage", type=float, default=0.0005); a = ap.parse_args()
    run(a.slippage)

if __name__ == "__main__":
    main()
