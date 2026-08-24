#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""진우_종목오버레이.py — 개별 종목 주가 + 기관/외국인 순매수 겹친 차트(진우식 관찰뷰).
사용: py 진우_종목오버레이.py [코드 코드 ...]  (기본: 336260 007660 033100 229640)
읽기: /tmp/px_m or 종목일봉(월말), flow_ext_monthly. 산출: 진우_종목오버레이.png
"""
import os, sys, csv
import matplotlib; matplotlib.use("Agg")
import matplotlib.pyplot as plt, matplotlib.font_manager as fm
import pandas as pd, numpy as np
BASE=os.path.dirname(os.path.abspath(__file__))
# 한글 폰트
for p in ["/usr/share/fonts/opentype/noto/NotoSerifCJK-Regular.ttc","/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc","/usr/share/fonts/opentype/noto/NotoSerifCJK-Bold.ttc"]:
    if os.path.exists(p):
        try: fm.fontManager.addfont(p); plt.rcParams["font.family"]=fm.FontProperties(fname=p).get_name(); break
        except Exception: pass
plt.rcParams["axes.unicode_minus"]=False

codes=[c.zfill(6) for c in (sys.argv[1:] or ["336260","007660","033100","229640"])]
# 이름
nm={}
for f in ["진우사냥터_후보.csv","진우_관심종목.csv","liquidity_sector.csv","kosdaq_industry.csv"]:
    p=os.path.join(BASE,f)
    if os.path.exists(p):
        for r in csv.DictReader(open(p,encoding="utf-8-sig")):
            r={k.lstrip("﻿"):v for k,v in r.items()}
            if r.get("code") and r.get("name"): nm.setdefault(r["code"].zfill(6),r["name"])
# 월봉 종가
def load_px():
    fr=[]
    for m in("KOSPI","KOSDAQ"):
        p=f"/tmp/px_m_{m}.csv"
        if os.path.exists(p): fr.append(pd.read_csv(p,header=None,names=["code","date","close"],dtype={0:str}))
        else:
            d=pd.read_csv(os.path.join(BASE,f"종목일봉_30년_{m}.csv"),usecols=["date","code","close"],dtype={"code":str})
            d["ym"]=d["date"].str[:7]; d=d.sort_values("date").groupby(["code","ym"]).tail(1); fr.append(d[["code","date","close"]])
    d=pd.concat(fr); d["code"]=d["code"].str.zfill(6); d["ym"]=d["date"].str[:7]; d["close"]=pd.to_numeric(d["close"],errors="coerce")
    return d.drop_duplicates(["code","ym"])
px=load_px()
fl=[]
for m in("KOSPI","KOSDAQ"):
    d=pd.read_csv(os.path.join(BASE,f"flow_ext_monthly_{m}.csv"),dtype={"code":str});d["code"]=d["code"].str.zfill(6);d["ym"]=d["date"].str[:7]
    d["inst"]=pd.to_numeric(d["inst_net"],errors="coerce")/1e8; d["forn"]=pd.to_numeric(d["foreign_net"],errors="coerce")/1e8; fl.append(d[["code","ym","inst","forn"]])
flow=pd.concat(fl).drop_duplicates(["code","ym"])
N=36  # 최근 36개월
fig,axes=plt.subplots(2,2,figsize=(14,9)); axes=axes.flatten()
for i,c in enumerate(codes):
    ax=axes[i]; p=px[px["code"]==c].sort_values("ym").tail(N); f=flow[flow["code"]==c].set_index("ym")
    if len(p)==0: ax.set_title(f"{c} 데이터없음"); continue
    yms=p["ym"].tolist(); x=range(len(yms))
    inst=[f["inst"].get(y,0) for y in yms]
    ax2=ax.twinx()
    ax2.bar(x,inst,color=["#3fb37a" if v>=0 else "#e2606a" for v in inst],alpha=0.55,width=0.7,label="기관 순매수")
    ax.plot(x,p["close"].values,color="#1f4e8c",lw=2.2,marker="o",ms=2.5,label="주가")
    ax.set_title(f"{nm.get(c,c)} ({c})  주가+기관 순매수(억)",fontsize=12)
    ax.set_zorder(ax2.get_zorder()+1); ax.patch.set_visible(False)
    step=max(1,len(yms)//6); ax.set_xticks(list(x)[::step]); ax.set_xticklabels([yms[j][2:] for j in range(0,len(yms),step)],fontsize=8)
    ax2.axhline(0,color="#888",lw=0.6); ax.set_ylabel("주가",fontsize=9); ax2.set_ylabel("기관 순매수(억)",fontsize=9)
    ax.grid(alpha=0.15)
plt.suptitle("종목별 주가 × 기관 순매수 오버레이 (최근 36개월) · 파랑선=주가, 막대=기관순매수(초록매수/빨강매도)",fontsize=12)
plt.tight_layout(rect=[0,0,1,0.97]); plt.savefig(os.path.join(BASE,"진우_종목오버레이.png"),dpi=125)
print("저장: 진우_종목오버레이.png ·",", ".join(f"{nm.get(c,c)}({c})" for c in codes))
