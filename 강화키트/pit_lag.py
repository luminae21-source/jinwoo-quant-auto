#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""pit_lag.py — 공시시차(PIT) 강제 유틸 + 룩어헤드 감사 (데이터 인프라 안전판)

왜: 한국 재무는 '분기말'이 아니라 '공시된 뒤'에야 실제로 알 수 있다(분기보고서 ~45일,
    사업보고서 ~90일 지연). 백테에서 분기말 재무를 같은 달 가격에 붙이면 '미래 정보'로
    수익률을 부풀린다(look-ahead). 이 모듈은 두 가지를 준다.

  (A) 백테용 강제: apply_disclosure_lag(wide, lag_months) — 각 달 M은 M-lag 이전에 이미
      공시됐을 재무만 보게 시프트. as_of(long, decision_ym, lag) — 특정 결정월 시점의
      '그때 공개돼 있던' 최신 재무만 종목별로 반환.
  (B) 감사: audit(root) — 현재 재무파일이 가격보다 '앞선(미래)' 달을 갖는지, 재무↔가격
      시차가 몇 달인지 리포트. 미래월이 있으면 FAIL(룩어헤드 위험).

주의(라이브 추천): recommend_dashboard 는 '현재 공시돼 있는 최신 재무(fym)'를 오늘 가격에
    붙인다 → 이건 look-ahead 아님(오늘 아는 정보로 오늘 매매). 이 모듈의 강제는 '백테'에서
    쓰는 것이고, 라이브 값이 갑자기 미래로 튀는 사고를 audit 이 잡아준다.

사용: py pit_lag.py --audit [--lag 2]
      from pit_lag import apply_disclosure_lag, as_of   # 백테 스크립트에서 import
⚠️ 정보·검증용·투자자문 아님·책임 본인.
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

import os, sys, argparse
import numpy as np, pandas as pd
HERE=os.path.dirname(os.path.abspath(__file__)); PARENT=os.path.dirname(HERE)
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

DEFAULT_LAG=2  # 개월. 분기보고서 ~45일 → 2개월이면 보수적으로 안전.

def _find(fn):
    for d in (PARENT,HERE,os.getcwd()):
        p=os.path.join(d,fn)
        if os.path.exists(p): return p
    return None

def _add_months(ym, n):
    y,m=int(ym[:4]),int(ym[5:7]); m+=n
    y+= (m-1)//12; m=(m-1)%12+1
    return f"{y:04d}-{m:02d}"

def apply_disclosure_lag(wide, lag_months=DEFAULT_LAG):
    """wide: index=ym(YYYY-MM, 정렬), columns=code, values=재무지표.
    반환: 각 달이 lag_months 개월 전 재무만 보도록 시프트한 패널(백테용).
    (월 격자로 재색인 후 직전값 유지 → lag만큼 아래로 시프트)"""
    if wide is None or wide.empty: return wide
    idx=sorted(wide.index)
    full=[]; cur=idx[0]
    while cur<=idx[-1]:
        full.append(cur); cur=_add_months(cur,1)
    w=wide.reindex(full).ffill()
    return w.shift(lag_months)

def as_of(long, decision_ym, lag_months=DEFAULT_LAG, code_col="code", ym_col="ym"):
    """long: 컬럼에 code,ym,<지표들>. decision_ym 시점에 '이미 공시돼 있던' 최신 재무만 종목별 1행.
    (ym <= decision_ym - lag_months 중 code별 최신)"""
    cutoff=_add_months(decision_ym, -lag_months)
    d=long[long[ym_col]<=cutoff].copy()
    if d.empty: return d
    d=d.sort_values(ym_col).groupby(code_col, as_index=False).tail(1)
    return d

def _load_fin():
    frames=[]
    for fn in ("종목재무_KRX_KOSPI.csv","종목재무_KRX_KOSDAQ.csv"):
        p=_find(fn)
        if not p: continue
        d=pd.read_csv(p,dtype={"code":str}); d["code"]=d["code"].str.zfill(6)
        d["ym"]=pd.to_datetime(d["date"]).dt.strftime("%Y-%m"); d["_src"]=fn
        frames.append(d)
    return pd.concat(frames,ignore_index=True) if frames else None

def _price_max_ym():
    mx=None
    for fn in ("_월봉종가캐시_KOSPI.csv","_월봉종가캐시_KOSDAQ.csv"):
        p=_find(fn)
        if not p: continue
        d=pd.read_csv(p,usecols=["ym"])
        m=str(d["ym"].max())
        mx=m if mx is None else max(mx,m)
    return mx

def audit(lag_months=DEFAULT_LAG):
    print("="*74); print(f"PIT(공시시차) 감사 · 기준 lag {lag_months}개월"); print("="*74)
    fin=_load_fin()
    if fin is None: print("  재무 파일 없음"); return "MISSING"
    pmax=_price_max_ym()
    fmax=str(fin["ym"].max()); fmin=str(fin["ym"].min())
    print(f"▸ 재무 기간 {fmin} ~ {fmax}  ({fin['code'].nunique()}종 · {len(fin):,}행)")
    print(f"▸ 가격 최신월 {pmax}")
    status="PASS"
    # (1) 재무가 가격보다 미래인가? = 명백한 룩어헤드/데이터오류
    if pmax:
        ahead=(fin["ym"]>pmax).sum()
        if ahead>0:
            print(f"   ❌ 재무월이 가격월보다 미래인 행 {ahead:,}개 — 룩어헤드/오염 위험"); status="FAIL"
        else:
            print(f"   ✅ 재무월 ≤ 가격월 (미래 재무 없음)")
        # (2) 현재 라이브 시차: 가격월 대비 재무 최신월 gap
        gap=0; a=fmax
        while a<pmax: a=_add_months(a,1); gap+=1
        note = "정상(공시 지연 반영)" if gap>=1 else "동월 — 라이브 스냅샷이면 정상, 백테면 lag 적용 필요"
        print(f"   ℹ️ 재무↔가격 시차 {gap}개월 · {note}")
    # (3) 백테 권고
    print("-"*74)
    print(f"  백테에서는 반드시 apply_disclosure_lag(..., lag_months={lag_months}) 또는")
    print(f"  as_of(long, 결정월, lag_months={lag_months}) 로 공시 이전 재무 사용을 차단하세요.")
    icon={"PASS":"✅","FAIL":"❌","WARN":"⚠️"}.get(status,"❓")
    print(f"\n감사 종합: {icon} {status}")
    print("⚠️ 정보·검증용·투자자문 아님·책임 본인.")
    return status

def _selftest():
    # 합성 데이터로 시프트·as_of 정확성 확인
    idx=["2026-01","2026-02","2026-03","2026-04","2026-05"]
    wide=pd.DataFrame({"A":[1,2,3,4,5]}, index=idx)
    lagged=apply_disclosure_lag(wide, 2)
    ok1 = (lagged.loc["2026-03","A"]==1) and (lagged.loc["2026-05","A"]==3) and pd.isna(lagged.loc["2026-02","A"])
    long=pd.DataFrame({"code":["005930"]*3,"ym":["2026-01","2026-02","2026-03"],"EPS":[10,20,30]})
    r=as_of(long,"2026-04",2)  # cutoff=2026-02 → 최신=2026-02 → EPS 20
    ok2 = (len(r)==1) and (int(r.iloc[0]["EPS"])==20)
    r0=as_of(long,"2026-02",2)  # cutoff=2025-12 → 없음
    ok3 = r0.empty
    passed=sum([ok1,ok2,ok3])
    print(f"pit_lag 셀프테스트: {passed}/3", "PASS" if passed==3 else "FAIL",
          f"(시프트={ok1}, as_of={ok2}, 경계={ok3})")
    return passed==3

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--audit",action="store_true"); ap.add_argument("--self-test",action="store_true")
    ap.add_argument("--lag",type=int,default=DEFAULT_LAG)
    a=ap.parse_args()
    if a.self_test: sys.exit(0 if _selftest() else 1)
    st=audit(a.lag)
    sys.exit(1 if st=="FAIL" else 0)

if __name__=="__main__": main()
