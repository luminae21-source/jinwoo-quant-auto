#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""백테_해외_밸류검증.py — 레벨업#2: 딥밸류 원리 글로벌 검증 (AQR HML Devil).
결과: 미·일·영·홍 모두 밸류 프리미엄 플러스(일본 Sharpe0.80). 2010년대 글로벌 혹한기→2020후 부활.
데이터: BAB_EquityFactors_Monthly.xlsx (AQR). 사냥터_기획/진우_해외검증_밸류글로벌.md"""
import pandas as pd, numpy as np, os
B=os.path.dirname(os.path.abspath(__file__))
df=pd.read_excel(os.path.join(B,"BAB_EquityFactors_Monthly.xlsx"),sheet_name="HML Devil",header=18)
df=df.rename(columns={df.columns[0]:"DATE"}); df["DATE"]=pd.to_datetime(df["DATE"],errors="coerce"); df=df.dropna(subset=["DATE"])
want={"USA":"미국","JPN":"일본","GBR":"영국","HKG":"홍콩"}
print("밸류(HML) 프리미엄 · 연율화")
for cc,nm in want.items():
    if cc not in df.columns: continue
    s=pd.to_numeric(df[cc],errors="coerce").dropna(); idx=df.loc[s.index,"DATE"]
    print(f"  {nm} {idx.min().year}~{idx.max().year}: {s.mean()*12*100:+.1f}%/yr · Sharpe {s.mean()/s.std()*np.sqrt(12):.2f}")
print("\n시대분할(연율화)")
for cc,nm in want.items():
    if cc not in df.columns: continue
    s=pd.to_numeric(df[cc],errors="coerce"); D=df["DATE"]
    seg=lambda a,b:(lambda x: f"{x.mean()*12*100:+.1f}%" if len(x)>=12 else "-")(s[(D>=a)&(D<b)].dropna())
    print(f"  {nm}: ~2010 {seg('1900','2010-01')} · 2010s {seg('2010-01','2020-01')} · 2020~ {seg('2020-01','2030')}")
