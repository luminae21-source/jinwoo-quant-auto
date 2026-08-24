#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""data_healthcheck.py — 데이터 무결성·신선도 검증 (데이터 인프라 안전판)

"낡거나 깨진 데이터로 추천을 만드는 사고"를 막는다. 파이프라인 실행 전 이걸 통과해야 한다.
검사(파일별): 존재·기간·최신성 · 종목 커버리지 · 결측/0 비율 · 월 연속성(갭) · 이상치(수익률) · 중복.
판정: PASS / WARN / FAIL. FAIL 하나라도면 파이프라인 중단 권고.

대상(진우 폴더): _월봉종가캐시_KOSPI/KOSDAQ.csv · 종목시총_30년.csv · 종목재무_KRX_KOSPI/KOSDAQ.csv
사용: py data_healthcheck.py [--asof YYYY-MM] [--json]
⚠️ 정보·검증용. 투자자문 아님·책임 본인.
"""

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

import os, sys, json, argparse, datetime
import numpy as np, pandas as pd
BASE=os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def _find(fn):
    for d in (BASE, os.path.dirname(BASE), os.getcwd()):
        p=os.path.join(d,fn)
        if os.path.exists(p): return p
    return None

def cur_ym():
    d=datetime.date.today(); return f"{d.year:04d}-{d.month:02d}"
def prev_ym(ym):
    y,m=int(ym[:4]),int(ym[5:7]); m-=1
    if m==0: y-=1; m=12
    return f"{y:04d}-{m:02d}"

RES=[]  # (파일, 검사, 상태, 상세)
def add(f,chk,st,detail): RES.append((f,chk,st,detail))

def check_month_panel(fn, asof):
    f=_find(fn)
    if not f: add(fn,"존재","FAIL","파일 없음"); return
    d=pd.read_csv(f,dtype={"code":str})
    if not {"code","ym","close"}<=set(d.columns): add(fn,"스키마","FAIL",f"컬럼 {list(d.columns)}"); return
    d["code"]=d["code"].str.zfill(6)
    n_codes=d["code"].nunique(); mx=d["ym"].max(); mn=d["ym"].min()
    add(fn,"기간",  "PASS",f"{mn}~{mx} · {n_codes}종 · {len(d):,}행")
    # 최신성: 최신 ym이 당월 또는 전월이어야
    ok_fresh = mx>=prev_ym(asof)
    add(fn,"최신성","PASS" if ok_fresh else "FAIL",f"최신 {mx} (기준 ≥{prev_ym(asof)})")
    # 월 연속성(최근 24개월 갭)
    yms=sorted(d["ym"].unique())[-24:]
    exp=[]; y,m=int(yms[0][:4]),int(yms[0][5:7])
    while f"{y:04d}-{m:02d}"<=yms[-1]:
        exp.append(f"{y:04d}-{m:02d}"); m+=1
        if m==13: y+=1; m=1
    gaps=[e for e in exp if e not in set(yms)]
    add(fn,"월 연속성","PASS" if not gaps else "WARN",f"최근24M 갭 {len(gaps)}개"+(f" {gaps[:3]}" if gaps else ""))
    # 이상치: 월수익 |>90%|
    w=d.pivot_table(index="ym",columns="code",values="close",aggfunc="last").sort_index()
    r=w.pct_change().mask(lambda x:x.abs()>1e4)
    ext=(r.abs()>0.9).sum().sum(); tot=r.notna().sum().sum()
    rate=ext/max(tot,1)
    add(fn,"이상치(월수익>90%)","PASS" if rate<0.005 else "WARN",f"{ext:,}건 ({rate*100:.2f}%)")
    # 중복
    dup=d.duplicated(["code","ym"]).sum()
    add(fn,"중복(code,ym)","PASS" if dup==0 else "FAIL",f"{dup}건")

def check_mcap(fn, asof):
    f=_find(fn)
    if not f: add(fn,"존재","FAIL","파일 없음"); return
    d=pd.read_csv(f,dtype={"code":str}); d["code"]=d["code"].str.zfill(6)
    d["ym"]=pd.to_datetime(d["date"]).dt.strftime("%Y-%m")
    mx=d["ym"].max()
    add(fn,"기간","PASS",f"{d['ym'].min()}~{mx} · {d['code'].nunique()}종 · {len(d):,}행")
    add(fn,"최신성","PASS" if mx>=prev_ym(asof) else "FAIL",f"최신 {mx} (기준 ≥{prev_ym(asof)})")
    z=(pd.to_numeric(d["mcap"],errors="coerce").fillna(0)<=0).mean()
    add(fn,"시총 0/결측","PASS" if z<0.02 else "WARN",f"{z*100:.2f}%")

def check_fin(fn, asof):
    f=_find(fn)
    if not f: add(fn,"존재","WARN","파일 없음(선택)"); return
    d=pd.read_csv(f,dtype={"code":str}); d["code"]=d["code"].str.zfill(6)
    d["ym"]=pd.to_datetime(d["date"]).dt.strftime("%Y-%m")
    mx=d["ym"].max()
    add(fn,"기간","PASS",f"{d['ym'].min()}~{mx} · {d['code'].nunique()}종")
    # 재무는 시차 있음 — 당월 아니어도 되나, 3개월내면 OK
    lag_ok = mx >= prev_ym(prev_ym(prev_ym(asof)))
    add(fn,"최신성(≤3M 지연 허용)","PASS" if lag_ok else "WARN",f"최신 {mx}")
    # ★ PIT sanity: 미래 날짜 금지
    future=(d["ym"]>asof).sum()
    add(fn,"미래날짜(룩어헤드)","PASS" if future==0 else "FAIL",f"{future}건")
    # 핵심 필드 0 비율(최신월)
    last=d[d["ym"]==mx]
    for col in ["DIV","EPS","BPS","PBR"]:
        if col in last.columns:
            z=(pd.to_numeric(last[col],errors="coerce").fillna(0)==0).mean()
            st="PASS" if z<0.5 else "WARN"
            add(fn,f"{col} 0비율(최신월)",st,f"{z*100:.1f}%")

def verdict():
    fails=[r for r in RES if r[2]=="FAIL"]; warns=[r for r in RES if r[2]=="WARN"]
    return ("FAIL" if fails else ("WARN" if warns else "PASS")), len(fails), len(warns)

def run(asof=None, as_json=False):
    asof=asof or cur_ym()
    check_month_panel("_월봉종가캐시_KOSPI.csv",asof)
    check_month_panel("_월봉종가캐시_KOSDAQ.csv",asof)
    check_mcap("종목시총_30년.csv",asof)
    check_fin("종목재무_KRX_KOSPI.csv",asof)
    check_fin("종목재무_KRX_KOSDAQ.csv",asof)
    v,nf,nw=verdict()
    if as_json:
        out=dict(asof=asof,verdict=v,fails=nf,warns=nw,
                 checks=[dict(file=f,check=c,status=s,detail=d) for f,c,s,d in RES])
        print(json.dumps(out,ensure_ascii=False,indent=2)); return v
    print("="*74); print(f"데이터 헬스체크 · 기준월 {asof}"); print("="*74)
    icon={"PASS":"✅","WARN":"⚠️","FAIL":"❌"}
    cur=None
    for f,c,s,d in RES:
        if f!=cur: print(f"\n▸ {f}"); cur=f
        print(f"   {icon[s]} {c:<22} {d}")
    print("\n"+"-"*74)
    print(f"종합 판정: {icon[v]} {v}  (FAIL {nf} · WARN {nw})")
    if v=="FAIL": print("  → 파이프라인 중단 권고. 데이터 갱신·수리 후 재실행.")
    elif v=="WARN": print("  → 진행 가능하나 경고 확인 권장.")
    else: print("  → 데이터 정상. 파이프라인 진행 OK.")
    print("⚠️ 정보·검증용. 투자자문 아님·책임 본인.")
    return v

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--asof"); ap.add_argument("--json",action="store_true")
    a=ap.parse_args()
    v=run(a.asof,a.json)
    sys.exit(0 if v!="FAIL" else 1)

if __name__=="__main__": main()
