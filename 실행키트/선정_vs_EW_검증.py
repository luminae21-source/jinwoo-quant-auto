#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""선정_vs_EW_검증.py — "종목선정 vs 동일가중(EW-18)" 정면 테스트  (개선안 ④)

질문: v3.7.2의 초과수익이 진짜 '종목선정 실력'인가, 아니면
      '18종목 유니버스 구성 + 팩터 틸트'의 부산물인가?

방법: 같은 18종목을 그냥 동일가중(EW)으로 매달 리밸런싱한 포트폴리오를 만들고,
      v3.7.2 전략의 실현 월수익과 같은 창(window)에서 비교한다.
      → 전략이 EW-18을 못 이기면, 무기는 '선정'이 아니라 '유니버스+틸트'다.
      → 그러면 사이징·기대치·집중도 관리 전략이 바뀐다(백서 3장 참조).

데이터(단일 진실원천, 진우 폴더 파일 그대로 사용):
  · _월봉종가캐시_KOSPI.csv / _월봉종가캐시_KOSDAQ.csv   (code, ym(YYYY-MM), close)
  · v37_2_scores_latest.csv                              (코드·종목·등급 → 유니버스 18종)
  · (선택) 전략 실현 월수익 CSV: --strategy 로 지정 (열: ym, ret[소수]).
           없으면 문서 백테 수치(CAGR 73.37%·Sharpe 2.88)를 참고선으로 사용.

사용:
  py 선정_vs_EW_검증.py                     # 자동 탐색·전 구간
  py 선정_vs_EW_검증.py --start 2022-07 --end 2026-06   # 백테 창(48~49M) 맞추기
  py 선정_vs_EW_검증.py --strategy v37_2_backtest_monthly.csv
  py 선정_vs_EW_검증.py --self-test

⚠️ 검증용 추정이다. EW-18은 '현재 유니버스 18종'을 과거에 그대로 적용한 근사(구성 변화·상장시점 차이 존재).
   실현손익 아님. 투자자문 아님·책임 본인.
"""
import os, sys, argparse, json
import numpy as np, pandas as pd

BASE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

# 문서 근거 백테 참고치(진우퀀트_v39_PEAD_결정메모 base 재현). 전략 실현 CSV 없을 때 참고선.
REF_STRAT_CAGR = 0.7337
REF_STRAT_SHARPE = 2.88

# v3.7.2 유니버스 18종 폴백(코드). v37_2_scores_latest.csv가 있으면 그걸 우선.
DEFAULT_UNIVERSE = {
    "005930":"삼성전자","000660":"SK하이닉스","042700":"한미반도체","196170":"알테오젠",
    "000270":"기아","035420":"NAVER","035720":"카카오","012450":"한화에어로",
    "079550":"LIG넥스원","105560":"KB금융","033780":"KT&G","006400":"삼성SDI",
    "090430":"아모레퍼시픽","028260":"삼성물산","003230":"삼양식품","095340":"ISC",
    "034020":"두산에너빌리티","005940":"NH투자증권",
}

def _find(*names):
    for n in names:
        p = os.path.join(BASE, n)
        if os.path.exists(p): return p
        p2 = os.path.join(os.path.dirname(BASE), n)   # 상위(프로젝트 루트)도 탐색
        if os.path.exists(p2): return p2
    return None

def get_universe():
    """유니버스 18종 코드 확보: 최신 점수표 > 폴백."""
    f = _find("v37_2_scores_latest.csv")
    if f:
        try:
            df = pd.read_csv(f, dtype={"코드":str})
            col = "코드" if "코드" in df.columns else ("code" if "code" in df.columns else None)
            nmc = "종목" if "종목" in df.columns else ("name" if "name" in df.columns else None)
            if col:
                codes = {str(r[col]).zfill(6): (str(r[nmc]) if nmc else "") for _,r in df.iterrows()}
                if len(codes) >= 10:
                    return codes, f"v37_2_scores_latest.csv ({len(codes)}종)"
        except Exception as e:
            print(f"  (점수표 읽기 실패 → 폴백: {e})")
    return dict(DEFAULT_UNIVERSE), "폴백 DEFAULT_UNIVERSE (18종)"

def load_month_closes(codes):
    """월봉 종가 캐시(KOSPI+KOSDAQ)에서 유니버스 종가 로드 → wide(ym×code) close."""
    frames = []
    for fn in ("_월봉종가캐시_KOSPI.csv", "_월봉종가캐시_KOSDAQ.csv"):
        f = _find(fn)
        if f:
            d = pd.read_csv(f, dtype={"code":str})
            d["code"] = d["code"].str.zfill(6)
            frames.append(d[d["code"].isin(codes)])
    if not frames:
        raise FileNotFoundError("월봉종가캐시_KOSPI/KOSDAQ.csv 를 찾지 못함(진우 폴더에서 실행하세요).")
    allc = pd.concat(frames, ignore_index=True)
    wide = allc.pivot_table(index="ym", columns="code", values="close", aggfunc="last").sort_index()
    return wide

def monthly_returns(wide):
    return wide.astype(float).pct_change()

def ew_portfolio(rets):
    """동일가중, 매월 리밸런싱: 각 월 존재하는 종목 평균수익."""
    return rets.mean(axis=1, skipna=True)

def stats(series, ann=12):
    s = pd.Series(series).dropna()
    if len(s) < 6: return None
    cagr = (1+s).prod()**(ann/len(s)) - 1
    vol = s.std()*np.sqrt(ann)
    sharpe = (s.mean()*ann)/ (s.std()*np.sqrt(ann)) if s.std()>0 else np.nan
    cum = (1+s).cumprod(); mdd = (cum/cum.cummax()-1).min()
    return dict(n=len(s), CAGR=cagr, vol=vol, Sharpe=sharpe, MDD=mdd,
                total=(1+s).prod()-1, mean_m=s.mean())

def info_ratio(strat, bench):
    a, b = pd.Series(strat).dropna(), pd.Series(bench).dropna()
    idx = a.index.intersection(b.index)
    d = (a.loc[idx]-b.loc[idx]);
    return (d.mean()*12)/(d.std()*np.sqrt(12)) if d.std()>0 else np.nan

def load_strategy(path):
    if not path: return None
    p = path if os.path.exists(path) else _find(path)
    if not p:
        print(f"  (전략 월수익 CSV '{path}' 없음 → 참고 백테 수치 사용)"); return None
    d = pd.read_csv(p)
    ymc = next((c for c in d.columns if c.lower() in ("ym","date","month","yyyymm")), d.columns[0])
    rc = next((c for c in d.columns if c.lower() in ("ret","return","r","월수익","수익률")), d.columns[-1])
    s = pd.Series(d[rc].values, index=d[ymc].astype(str).values, name="strategy")
    if s.abs().median() > 1.5: s = s/100.0   # % 로 들어오면 소수로
    return s

def run(start=None, end=None, strategy_csv=None):
    codes, src = get_universe()
    print("="*74)
    print("선정 vs 동일가중(EW-18) 정면 테스트")
    print("="*74)
    print(f"  유니버스 출처: {src}  ·  종목수 {len(codes)}")
    wide = load_month_closes(codes)
    got = [c for c in codes if c in wide.columns]
    miss = [codes[c] for c in codes if c not in wide.columns]
    if miss: print(f"  ⚠ 캐시에 없는 종목({len(miss)}): {', '.join(miss)}  (해당 시장 캐시 갱신 필요)")
    rets = monthly_returns(wide[got])
    if start: rets = rets[rets.index >= start]
    if end:   rets = rets[rets.index <= end]
    print(f"  구간: {rets.index.min()} ~ {rets.index.max()}  ({len(rets)}개월)  ·  실측 종목 {len(got)}\n")

    ew = ew_portfolio(rets)
    ew_s = stats(ew)

    strat = load_strategy(strategy_csv)
    if strat is not None:
        strat = strat.reindex(ew.index).dropna()
        st_s = stats(strat)
    else:
        st_s = None

    # 출력표
    def row(name, s):
        if not s: return f"  {name:<16} (데이터부족)"
        return (f"  {name:<16} CAGR {s['CAGR']*100:6.2f}%  Sharpe {s['Sharpe']:4.2f}  "
                f"MDD {s['MDD']*100:6.1f}%  누적 {s['total']*100:7.1f}%  ({s['n']}M)")
    print(row("EW-18(동일가중)", ew_s))
    if st_s:
        print(row("v3.7.2 전략", st_s))
        ir = info_ratio(strat, ew.reindex(strat.index))
        dcagr = (st_s['CAGR']-ew_s['CAGR'])*100
        print("\n" + "-"*74)
        print(f"  전략 − EW-18 :  ΔCAGR {dcagr:+.2f}%p   ·   IR(vs EW) {ir:+.2f}")
        verdict = ("✅ 선정 알파 실재 — 전략이 EW-18을 유의하게 상회(IR>0)"
                   if (dcagr>0 and ir>0.3) else
                   "⚠️ 선정 알파 약함/부재 — 무기는 '유니버스 구성+팩터 틸트'일 가능성. "
                   "사이징·기대치·집중도 관리를 EW 기준으로 재설계 권고(백서 3장)")
        print(f"  판정: {verdict}")
    else:
        print(f"\n  (전략 실현 CSV 미지정 → 문서 백테 참고선 사용)")
        print(f"  참고 백테: CAGR {REF_STRAT_CAGR*100:.2f}% · Sharpe {REF_STRAT_SHARPE:.2f}")
        dcagr = (REF_STRAT_CAGR-ew_s['CAGR'])*100 if ew_s else float('nan')
        print(f"  참고 ΔCAGR(백테−EW) ≈ {dcagr:+.1f}%p  "
              f"→ EW-18을 크게 앞서면 선정+틸트 합산 우위, 근소하면 틸트 기여가 큼.")
        print("  ※ 정확 판정은 --strategy 로 전략 '실현 월수익'을 넣어 같은 창에서 비교하세요.")
    print("\n" + "="*74)
    print("해석 가이드: EW-18을 못 넘으면 → 종목선정을 줄이고 '유니버스 관리+비용/회전 최소화'로.")
    print("            EW-18을 넘으면   → 선정 로직 유지하되 집중 리스크(반도체)만 통제.")
    print("⚠️ 검증용 근사. 실현손익 아님. 투자자문 아님·책임 본인.")
    return ew_s, st_s

def _self_test():
    ok=tot=0
    def chk(n,c):
        nonlocal ok,tot; tot+=1; ok+=1 if c else 0; print(f"  [{'OK' if c else 'FAIL'}] {n}")
    # stats: 매월 +1% 12개월 → CAGR≈12.68%
    s = stats(pd.Series([0.01]*12)); chk("CAGR 계산", abs(s['CAGR']-0.1268)<0.01)
    chk("MDD 무손실=0", abs(stats(pd.Series([0.01]*12))['MDD'])<1e-9)
    # EW: 두 종목 평균
    r = pd.DataFrame({"A":[0.02,0.0],"B":[0.0,0.04]})
    chk("EW=행평균", abs(ew_portfolio(r).iloc[0]-0.01)<1e-9 and abs(ew_portfolio(r).iloc[1]-0.02)<1e-9)
    # IR: 전략이 벤치보다 매월 +0.5% 꾸준 → IR 큼(>0)
    st=pd.Series([0.015]*12,index=range(12)); bn=pd.Series([0.010]*12,index=range(12))
    chk("IR 부호(+)", info_ratio(st,bn)>0)
    print(f"\n셀프테스트: {ok}/{tot}"); return ok==tot

def main():
    ap=argparse.ArgumentParser(description="선정 vs EW-18 정면 테스트(개선안 ④)")
    ap.add_argument("--start"); ap.add_argument("--end")
    ap.add_argument("--strategy", help="전략 실현 월수익 CSV(열: ym, ret)")
    ap.add_argument("--self-test", action="store_true")
    a=ap.parse_args()
    if a.self_test: return 0 if _self_test() else 1
    run(a.start, a.end, a.strategy); return 0

if __name__=="__main__":
    sys.exit(main())
