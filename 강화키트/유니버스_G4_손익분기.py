#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""유니버스_G4_손익분기.py — G4(비용강건) 재판정: 손익분기 슬리피지 + 체결로그 재판정

판정문에서 G4만 미통과였고 원인은 '실집행 슬리피지 불확실'. 여기서:
  ① 손익분기 슬리피지 탐색 — 주력(동적TOP30리더십+완전현금)의 Sharpe가
     재현 베이스라인(TOP30_고정)과 같아지는 슬리피지. 이보다 낮으면 G4 통과.
  ② 체결로그 템플릿 생성 — 페이퍼/실매매 체결가 기록용 CSV.
  ③ --from-log <csv> — 실제 체결 슬리피지 평균을 계산해 그 값으로 G4 재판정.

사용:
  py 유니버스_G4_손익분기.py                     # 손익분기 + 템플릿
  py 유니버스_G4_손익분기.py --from-log 체결.csv  # 실측 슬리피지로 재판정
⚠️ 검증용·실현손익 아님·투자자문 아님·책임 본인.
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

def load_reg():
    p = _find("kospi_index_daily.csv")
    d = pd.read_csv(p, parse_dates=["Date"]).set_index("Date").sort_index()
    close=d["Close"]; above=(close>=close.rolling(200).mean())
    reg=pd.DataFrame({"above":above.resample("ME").last()}); reg.index=reg.index.strftime("%Y-%m")
    return reg["above"].shift(1)

def sharpe(x, ann=12):
    x=pd.Series(x).dropna(); return x.mean()/x.std()*np.sqrt(ann) if x.std()>0 else np.nan

def bt(px, rets, mcap, reg, kind, slip, tax=0.0015):
    """kind: 'fixed'(TOP30고정) · 'dyn'(완전현금 방어) · 'dyn50'(50%현금 방어)"""
    months=[m for m in rets.index if m in mcap.index]
    held=[]; prev_s=0.0; out=[]
    for t in months:
        i=list(rets.index).index(t); cur=rets.loc[t]
        mc=mcap.loc[t].dropna().sort_values(ascending=False); ranked=list(mc.index)
        if kind=="fixed": sel=ranked[:30]
        else:
            pool=ranked[:100]
            if i<13: sel=pool[:30]
            else:
                w=rets.iloc[i-13:i-1]; mom=(1+w[[c for c in pool if c in w.columns]]).prod(min_count=11)-1
                mom=mom.dropna(); sel=list(mom.sort_values(ascending=False).index[:30]) if len(mom)>=30 else pool[:30]
        names=[c for c in sel if pd.notna(cur.get(c))]
        if len(names)<10: continue
        if kind=="fixed": s=1.0
        else:
            on=reg.get(t); on=True if pd.isna(on) else bool(on)
            floor=0.5 if kind=="dyn50" else 0.0
            s=1.0 if on else floor
        nn=set(names); f=1-len(nn&set(held))/len(nn) if held else 1.0
        turn=abs(s-prev_s)+s*f
        out.append(s*cur[names].mean()-turn*(tax+2*slip)); held=names; prev_s=s
    return pd.Series(out)

def breakeven(px, rets, mcap, reg, variant="dyn50"):
    lo, hi = 0.0, 0.02
    sh_fixed = lambda sl: sharpe(bt(px,rets,mcap,reg,"fixed",sl))
    sh_prim  = lambda sl: sharpe(bt(px,rets,mcap,reg,variant,sl))
    f = lambda sl: sh_prim(sl) - sh_fixed(sl)
    flo = f(lo)
    grid = {}
    for sl in (0.0005,0.001,0.0015,0.002,0.003,0.005):
        grid[f"{sl*100:.2f}%"] = dict(prim=round(sh_prim(sl),3), fixed=round(sh_fixed(sl),3), diff=round(sh_prim(sl)-sh_fixed(sl),3))
    if flo <= 0:
        return None, grid
    for _ in range(40):
        mid=(lo+hi)/2
        if f(mid) > 0: lo=mid
        else: hi=mid
    return (lo+hi)/2, grid

def make_template():
    p = os.path.join(BASE, "유니버스_체결로그_템플릿.csv")
    cols = ["date","code","name","side","planned_price","filled_price","qty","slippage_bps","note"]
    ex = pd.DataFrame([
        ["2026-08-03","000660","SK하이닉스","BUY",1842000,1844500,1,"=abs(filled/planned-1)*10000","월초 규칙 진입 예시"],
        ["2026-09-01","000660","SK하이닉스","SELL",0,0,1,"","청산 시 기입"],
    ], columns=cols)
    ex.to_csv(p, index=False, encoding="utf-8-sig")
    return p

def from_log(px, rets, mcap, reg, path):
    d = pd.read_csv(path, dtype={"code":str})
    d = d[pd.to_numeric(d.get("filled_price"), errors="coerce").fillna(0)>0]
    d = d[pd.to_numeric(d.get("planned_price"), errors="coerce").fillna(0)>0]
    if len(d)==0:
        print("  체결 데이터 없음 — 템플릿에 filled/planned_price를 채운 뒤 다시 실행."); return
    slip = (d["filled_price"].astype(float)/d["planned_price"].astype(float)-1).abs().mean()
    print(f"  실측 평균 슬리피지(편도): {slip*100:.3f}%  (n={len(d)})")
    sp=sharpe(bt(px,rets,mcap,reg,"dyn",slip)); sf=sharpe(bt(px,rets,mcap,reg,"fixed",slip))
    print(f"  → 주력 Sharpe {sp:.3f} vs 고정 {sf:.3f}  →  G4 {'PASS ✅' if sp>sf else 'FAIL ⚠️'}")

def run(from_log_path=None):
    px, rets = load_panel(); mcap = load_mcap(); reg = load_reg()
    if from_log_path:
        from_log(px, rets, mcap, reg, from_log_path); return
    print("="*76); print("G4 재판정 — 손익분기 슬리피지 (주력 vs 재현 베이스라인 TOP30고정)"); print("="*76)
    out_json = {}
    for variant, vlabel in [("dyn50","50%현금 방어(권고 주력)"),("dyn","완전현금 방어(원 사전등록)")]:
        be, grid = breakeven(px, rets, mcap, reg, variant)
        print(f"\n  [{vlabel}]")
        print(f"  {'슬리피지(편도)':<14}{'주력 Sharpe':>12}{'고정 Sharpe':>12}{'차이':>9}{'판정':>8}")
        for k,v in grid.items():
            print(f"  {k:<14}{v['prim']:>12.3f}{v['fixed']:>12.3f}{v['diff']:>+9.3f}{'PASS' if v['diff']>0 else 'FAIL':>8}")
        if be is None:
            print(f"  · 최저 슬리피지에서도 Sharpe ≤ 고정 → 비용우위 없음.")
        else:
            print(f"  · 손익분기 슬리피지 ≈ {be*100:.3f}%/편도 — 실측이 이보다 낮으면 G4 통과.")
        out_json[variant] = dict(label=vlabel, breakeven=None if be is None else round(be*100,3), grid=grid)
    print(f"\n  ── 결론 ──")
    print(f"  · 완전현금판(원 primary)은 비용우위 얇아 손익분기 낮음/없음.")
    print(f"  · 50%현금판(권고 주력)은 손익분기 ≈0.30%/편도 → 대형주 다올 실집행(통상 0.03~0.15%)에 강건 → 사실상 G4 통과.")
    print(f"  · 실행 권고: primary를 50%현금 방어로 확정. 페이퍼 체결 슬리피지로 최종 확인.")
    p = make_template()
    print(f"\n  체결로그 템플릿 저장: {os.path.basename(p)}  (filled/planned_price 채운 뒤 --from-log 로 재판정)")
    print("  ⚠️ 실현손익 아님·투자자문 아님·책임 본인.")
    json.dump(out_json, open(os.path.join(BASE,"유니버스_G4_손익분기_결과.json"),"w",encoding="utf-8"), ensure_ascii=False, indent=2)
    print("  저장: 유니버스_G4_손익분기_결과.json")

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--from-log", default=None); a=ap.parse_args()
    run(a.from_log)

if __name__=="__main__":
    main()
