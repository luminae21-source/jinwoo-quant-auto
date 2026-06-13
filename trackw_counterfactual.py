#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""trackw_counterfactual.py — Track W(재량 테마 lane) 반사실 기여도 추적.
질문: 재량 테마 픽이 '같은 돈을 v3.7.2 시스템에 넣었을 때'보다 더 버나? (재량이 밥값 하나)
방법: 매월 W 실현수익 vs 시스템 실현수익을 기록 → 기여도 = W − 시스템(반사실).
      6~12개월 누적 후 판정(대시보드: 12월 말 Track W 본판정). 양수 지속→유지/확대, 음수→축소.
기록: trackw_record.csv [date, w_ret_pct, sys_ret_pct, note]
사용:
  python trackw_counterfactual.py --add 2026-06 6.2 3.1 "에코프로 테마"
  python trackw_counterfactual.py                  # 누적 분석·판정
  python trackw_counterfactual.py --selftest
⚠️ 투자자문 아님. 재량 lane이 추가 리스크값을 하는지 측정하는 기록."""
import argparse, csv, os, sys, math
import numpy as np
REC="trackw_record.csv"

def add_month(date,w,s,note="",path=REC):
    new=not os.path.exists(path)
    with open(path,"a",newline="",encoding="utf-8-sig") as f:
        wr=csv.writer(f)
        if new: wr.writerow(["date","w_ret_pct","sys_ret_pct","note"])
        wr.writerow([date,f"{float(w):.4f}",f"{float(s):.4f}",note])
    print(f"기록: {date}  W {float(w):+.2f}%  시스템 {float(s):+.2f}%  기여 {float(w)-float(s):+.2f}%p  ({note})")

def _load(path=REC):
    rows=list(csv.DictReader(open(path,encoding="utf-8-sig")))
    d=[r["date"] for r in rows]
    w=np.array([float(r["w_ret_pct"]) for r in rows])/100.0
    s=np.array([float(r["sys_ret_pct"]) for r in rows])/100.0
    return d,w,s

def analyze(path=REC):
    d,w,s=_load(path); n=len(w)
    if n<1: print("기록 없음"); return None
    contrib=w-s                                   # 재량 기여 (반사실 대비)
    w_cagr=float(np.prod(1+w)**(12/n)-1); s_cagr=float(np.prod(1+s)**(12/n)-1)
    print(f"=== Track W 반사실 추적 ({n}개월: {d[0]}~{d[-1]}) ===")
    print(f"W(재량) CAGR {w_cagr:+.1%} | 시스템(반사실) CAGR {s_cagr:+.1%} | 재량 기여(CAGR) {w_cagr-s_cagr:+.1%}")
    verdict=None
    if n>1:
        mean_m,sd_m=contrib.mean(),contrib.std(ddof=1)
        ann=mean_m*12; se=sd_m*math.sqrt(12)/math.sqrt(n)
        ir=(mean_m/sd_m*math.sqrt(12)) if sd_m>0 else float("nan")
        lo,hi=ann-1.96*se,ann+1.96*se
        print(f"연환산 재량 기여(산술) {ann:+.1%}  95%CI [{lo:+.1%}, {hi:+.1%}]  | IR {ir:.2f}")
        if n<6: verdict="표본 부족(6개월 미만) — 판정 보류"
        elif hi<0: verdict="재량이 시스템 하회(유의) → Track W 축소 검토"
        elif lo>0: verdict="재량이 시스템 상회(유의) → 밥값 함, 유지/확대 검토"
        elif ann>0: verdict="재량 +이나 CI 0 포함 → 더 관찰(추가 리스크 정당화 미확정)"
        else: verdict="재량 −이나 CI 0 포함 → 더 관찰, 경계"
        print(f"판정: {verdict}")
        winm=int((contrib>0).sum())
        print(f"월별 승률(W>시스템): {winm}/{n} ({winm/n*100:.0f}%)")
        if n<6: print(f"진행도: {n}/6개월 (대시보드 본판정 = 12개월 누적 권장)")
    else:
        print("(2개월 이상부터 기여·CI 산출)")
    return {"n":n,"contrib_cagr":w_cagr-s_cagr,"verdict":verdict}

def _selftest():
    rng=np.random.default_rng(1); p="_trackw_test.csv"
    rows=[["date","w_ret_pct","sys_ret_pct","note"]]
    for i in range(8):
        sysr=rng.normal(0.015,0.05); wr=sysr+rng.normal(0.004,0.06)
        rows.append([f"2026-{(i%12)+1:02d}",f"{wr*100:.4f}",f"{sysr*100:.4f}","t"])
    open(p,"w",newline="",encoding="utf-8-sig").write("")
    with open(p,"w",newline="",encoding="utf-8-sig") as f: csv.writer(f).writerows(rows)
    r=analyze(p)
    try: os.remove(p)
    except OSError: pass
    assert r and r["n"]==8 and r["verdict"] is not None
    print("\n[OK] trackw_counterfactual selftest 통과")
    return 0

def main():
    ap=argparse.ArgumentParser()
    ap.add_argument("--add",nargs="+",metavar="DATE W SYS [NOTE]")
    ap.add_argument("--record",default=REC); ap.add_argument("--selftest",action="store_true")
    a=ap.parse_args()
    if a.selftest: return _selftest()
    if a.add:
        note=" ".join(a.add[3:]) if len(a.add)>3 else ""
        add_month(a.add[0],a.add[1],a.add[2],note,a.record); return 0
    if not os.path.exists(a.record):
        print(f"{a.record} 없음 → 매월 'python trackw_counterfactual.py --add YYYY-MM W% 시스템% [메모]'"); return 0
    analyze(a.record)

if __name__=="__main__":
    try: sys.stdout.reconfigure(encoding="utf-8")
    except: pass
    sys.exit(main() or 0)
