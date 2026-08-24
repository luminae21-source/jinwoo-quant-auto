#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""_flow_수집검증.py — 새 대량수집 flow_ext 가 누락/왜곡 없는지 기존 신뢰패널과 대조(PC).
기존 {kospi,kosdaq}_flow_monthly.csv (2019+, top-550, per-종목 수집=신뢰) 를 기준으로:
  ① 커버리지: 기존 (code,ym) 쌍이 새 ext 에 얼마나 존재하나 (누락=top-N 잘림 신호)
  ② 값일치 : 겹치는 곳에서 inst_net/foreign_net 상관·부호일치 (기관합계는 정의 동일→~1.0 기대)
사용: python _flow_수집검증.py
"""
import os, sys
import pandas as pd, numpy as np
BASE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

def load(p):
    d = pd.read_csv(p, dtype={"code": str}); d["code"] = d["code"].str.zfill(6)
    d["ym"] = d["date"].str[:7]
    for c in ("foreign_net", "inst_net"): d[c] = pd.to_numeric(d[c], errors="coerce")
    return d.drop_duplicates(["code", "ym"])[["code", "ym", "foreign_net", "inst_net"]]

for mk in ["KOSPI", "KOSDAQ"]:
    ext_p = os.path.join(BASE, f"flow_ext_monthly_{mk}.csv")
    old_p = os.path.join(BASE, f"{mk.lower()}_flow_monthly.csv")
    if not os.path.exists(ext_p):
        print(f"[{mk}] flow_ext 없음 → 건너뜀"); continue
    if not os.path.exists(old_p):
        print(f"[{mk}] 기존 패널 없음 → 대조 불가(커버리지만): ext 종목수 {load(ext_p)['code'].nunique()}"); continue
    ext = load(ext_p); old = load(old_p)
    old19 = old[old["ym"] >= "2019-01"]
    m = old19.merge(ext, on=["code", "ym"], how="left", suffixes=("_old", "_ext"))
    cov = m["inst_net_ext"].notna().mean()
    print(f"\n===== [{mk}] =====")
    print(f"기존(2019+) (code,ym) {len(old19)} | 새 ext에 존재 {int(m['inst_net_ext'].notna().sum())} ({cov*100:.1f}%)")
    print(f"  ext 총 종목수 {ext['code'].nunique()} (기존 {old['code'].nunique()}) · ext 월범위 {ext['ym'].min()}~{ext['ym'].max()}")
    both = m.dropna(subset=["inst_net_ext"])
    if len(both) > 10:
        for col in ["inst_net", "foreign_net"]:
            a = both[f"{col}_old"].values; b = both[f"{col}_ext"].values
            corr = np.corrcoef(a, b)[0, 1]
            sign = np.mean(np.sign(a) == np.sign(b))
            # 매집 플래그(>0) 일치율
            flag = np.mean((a > 0) == (b > 0))
            print(f"  {col:12}: 상관 {corr:.3f} · 부호일치 {sign*100:.1f}% · 매집플래그(>0)일치 {flag*100:.1f}%")
    if cov < 0.98:
        miss = m[m["inst_net_ext"].isna()]
        print(f"  ⚠ 미존재 {len(miss)}건 → top-N 잘림 의심. 예:", miss[["code","ym"]].head(5).values.tolist())
    else:
        print("  ✔ 커버리지 ~완전 → top-N 잘림 아님(누락 없음).")
print("\n판정: 커버리지 ~100% & 기관 상관~1.0 이면 대량수집 = 누락없음·기존과 정합.")
