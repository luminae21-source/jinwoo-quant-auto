# -*- coding: utf-8 -*-
"""새 패러다임 차트 4종 — build_all.py가 import해서 사용. 상수 기반 자체완결."""

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

import os
def make_charts(IMG):
    import matplotlib; matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from matplotlib import font_manager as fm
    import numpy as np
    # 한글 폰트 자동 탐색 (Windows/Linux/macOS)
    CANDS=[r"C:\Windows\Fonts\malgun.ttf",            # 맑은 고딕
           r"C:\Windows\Fonts\NanumGothic.ttf",
           r"C:\Windows\Fonts\gulim.ttc",
           "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
           "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
           "/System/Library/Fonts/AppleSDGothicNeo.ttc"]
    fp=None
    for FP in CANDS:
        if os.path.exists(FP):
            try:
                fm.fontManager.addfont(FP); fp=fm.FontProperties(fname=FP)
                plt.rcParams["font.family"]=fp.get_name()
                print("  font:",os.path.basename(FP)); break
            except Exception: pass
    if fp is None:
        print("  [!] 한글 폰트 없음 — 라벨이 깨질 수 있음")
        fp=fm.FontProperties()
    plt.rcParams["axes.unicode_minus"]=False; plt.rcParams["savefig.dpi"]=150
    INK="#1a2233";NAVY="#2b4a6f";BLUE="#3d7ab5";TEAL="#2c9c8f";AMBER="#e0a13a";RED="#c0504d";GREY="#9aa5b1";LIGHT="#eef2f6";GREEN="#4a9d6a";PURPLE="#7c5cbf"
    def banner(ax, text, color=RED):
        """차트 상단에 검증상태 배너"""
        ax.text(0.5, 1.005, text, transform=ax.transAxes, ha="center", va="bottom",
                fontproperties=fp, fontsize=9.5, color="white", weight="bold",
                bbox=dict(boxstyle="round,pad=0.35", fc=color, ec="none"), zorder=10)

    def sty(ax):
        for s in ["top","right"]: ax.spines[s].set_visible(False)
        ax.spines["left"].set_color(GREY); ax.spines["bottom"].set_color(GREY)
        ax.tick_params(colors=INK,labelsize=10); ax.set_axisbelow(True)

    # 1. 팩터 효력 순위 (30년, IC) — 배당 최강 · 모멘텀 약
    facs=[("배당수익률",0.0487,5.9),("가치 B/P",0.0372,3.1),("가치 E/P",0.0303,2.9),
          ("성장 EPS성장",0.0199,2.7),("퀄리티 ROE",0.0180,2.3),("모멘텀 12-1",0.0086,0.7),("사이즈(소형)",-0.0293,-3.8)]
    names=[f[0] for f in facs]; ics=[f[1] for f in facs]; ts=[f[2] for f in facs]
    def col(t): return GREEN if t>=2.3 else (AMBER if t>0 else RED)
    cols=[col(t) for t in ts]; y=np.arange(len(names))[::-1]
    fig,ax=plt.subplots(figsize=(8.6,4.4)); bars=ax.barh(y,ics,color=cols,zorder=2)
    sty(ax); ax.axvline(0,color=INK,lw=1); ax.xaxis.grid(True,color=LIGHT)
    ax.set_yticks(y); ax.set_yticklabels(names,fontproperties=fp,fontsize=11)
    for b,ic,t in zip(bars,ics,ts):
        ax.text(ic+(0.001 if ic>=0 else -0.001),b.get_y()+b.get_height()/2,f"IC {ic:+.3f} · t={t:.1f}",
                va="center",ha="left" if ic>=0 else "right",fontsize=9.3,color=INK,fontproperties=fp)
    ax.set_xlim(-0.05,0.075); ax.set_xlabel("평균 IC (예측력) · 30년 · 유효선 t≥2.3",fontproperties=fp)
    ax.set_title("팩터 효력 순위 — 배당이 왕 · 모멘텀은 약함(t=0.7) · 소형주 마이너스",fontproperties=fp,fontsize=13,color=INK,pad=26)
    banner(ax,"⚠ 30년 수치 미감사 (2026-07-27) — 검증된 방향: 조정본 배당 HAC t 4.10 · B/P 3.34 · E/P 2.36",AMBER)
    fig.tight_layout(); fig.savefig(IMG+"/f_factor_ic.png",bbox_inches="tight",facecolor="white"); plt.close()

    # 2. 유니버스·방어 — 주도주 낙폭을 방어가 제어 (MDD·Sharpe)
    labs=["KOSPI\n(벤치)","고정18\n(레거시)","주도주\n(무방어)","주도주+\n50%현금★","주도주+\n완전현금"]
    cagr=[6.9,17.7,21.7,20.1,17.2]; mdd=[63.3,44.9,64.3,44.2,37.6]; shp=[0.37,0.83,0.78,0.85,0.80]
    x=np.arange(len(labs)); fig,ax=plt.subplots(figsize=(8.6,4.4))
    b=ax.bar(x,cagr,width=0.6,color=[GREY]*5,alpha=0.45); sty(ax); ax.yaxis.grid(True,color=LIGHT)  # 무효 → 회색화
    for r,c,m,s in zip(b,cagr,mdd,shp):
        ax.text(r.get_x()+r.get_width()/2,c+0.6,f"{c:.1f}%",ha="center",fontproperties=fp,fontsize=9.5,color=INK,weight="bold")
        ax.text(r.get_x()+r.get_width()/2,c-2.4,f"Sh {s:.2f}\nMDD −{m:.0f}%",ha="center",fontproperties=fp,fontsize=8,color=INK)
    ax.set_xticks(x); ax.set_xticklabels(labs,fontproperties=fp,fontsize=9.5)
    ax.set_ylabel("순 CAGR (%) · 30년·다올 비용후",fontproperties=fp); ax.set_ylim(0,26)
    ax.set_title("유니버스·방어 (구 수치 — 참고용)",fontproperties=fp,fontsize=11.5,color=GREY,pad=26)
    banner(ax,"🔴 무효 — 시총 룩어헤드 편향 (교정: TOP30_고정 19.8→4.9% · 동적 21.7→7.8%)")
    ax.text(0.5,0.52,"무효",transform=ax.transAxes,ha="center",va="center",fontproperties=fp,
            fontsize=64,color=RED,alpha=0.13,weight="bold",zorder=1)
    fig.tight_layout(); fig.savefig(IMG+"/f_universe.png",bbox_inches="tight",facecolor="white"); plt.close()

    # 3. 두 트랙 — 진입타이밍(6개월 수익) + 매도 라우팅
    fig,(axa,axb)=plt.subplots(1,2,figsize=(9.2,3.8))
    # value vs growth 6M return by 추세
    grp=["점수상위","+추세위\n(≥MA10)","전환점\n(MA200회복)"]; val=[11.5,11.9,8.8]; gro=[4.5,5.3,4.6]
    xx=np.arange(len(grp)); w=0.36
    axa.bar(xx-w/2,val,w,color=BLUE,label="가치 트랙"); axa.bar(xx+w/2,gro,w,color=PURPLE,label="성장 트랙")
    sty(axa); axa.set_xticks(xx); axa.set_xticklabels(grp,fontproperties=fp,fontsize=8.5)
    axa.set_ylabel("6개월 수익률 (%)",fontproperties=fp); axa.legend(prop=fp,frameon=False,fontsize=8.5)
    axa.set_title("진입: 추세위 유효·전환점 무효",fontproperties=fp,fontsize=10.5,color=INK)
    # exit routing
    exl=["가치\n스톱없음","가치\n라우팅","성장\n스톱없음","성장\n라우팅"]; exm=[51.1,67.1,71.7,55.9]; exc=[TEAL,GREY,GREY,TEAL]
    axb.bar(exl,exm,color=exc,width=0.62); sty(axb)
    for i,v in enumerate(exm): axb.text(i,v+0.8,f"−{v:.0f}%",ha="center",fontproperties=fp,fontsize=8.5,color=INK)
    for lab in axb.get_xticklabels(): lab.set_fontproperties(fp); lab.set_fontsize(8.5)
    axb.set_ylabel("MDD (최대낙폭 %)",fontproperties=fp); axb.set_ylim(0,80)
    axb.set_title("매도: 가치=인내·성장=트레일",fontproperties=fp,fontsize=10.5,color=INK)
    fig.suptitle("두 트랙 — 진입은 추세, 매도는 트랙별 (24년 검정 · ⚠ 시점 짝짓기 미감사)",fontproperties=fp,fontsize=12,color=INK,y=1.06)
    fig.tight_layout(); fig.savefig(IMG+"/f_twotrack.png",bbox_inches="tight",facecolor="white"); plt.close()

    # 4. 정직한 forward — 힌드사이트 73% vs 규칙 재현 20%
    labs=["v3.7.2 백테\n(힌드사이트)","고정18\n규칙재현","주도주 50%현금\n(현행 목표 아님)","KOSPI"]; vals=[73.0,17.7,20.1,6.9]; shp2=[2.88,0.83,0.85,0.37]; cols2=[GREY,GREY,GREY,"#c9d3e0"]
    fig,ax=plt.subplots(figsize=(7.8,3.9)); b=ax.bar(labs,vals,color=cols2,width=0.62); sty(ax); ax.yaxis.grid(True,color=LIGHT)
    for r,v,s in zip(b,vals,shp2): ax.text(r.get_x()+r.get_width()/2,v+1.5,f"{v:.0f}%\nSh {s:.2f}",ha="center",fontproperties=fp,fontsize=9,color=INK)
    for lab in ax.get_xticklabels(): lab.set_fontproperties(fp); lab.set_fontsize(9)
    ax.set_ylabel("CAGR (%)",fontproperties=fp); ax.set_ylim(0,86)
    ax.set_title("정직한 forward (구 수치 — 참고용)",fontproperties=fp,fontsize=12,color=GREY,pad=26)
    banner(ax,"🔴 무효 — 룩어헤드 편향 (교정 4.9~7.8%). 현재 검증된 전략 CAGR 추정치 없음")
    ax.text(0.5,0.5,"무효",transform=ax.transAxes,ha="center",va="center",fontproperties=fp,
            fontsize=60,color=RED,alpha=0.13,weight="bold",zorder=1)
    ax.annotate("",xy=(0,73),xytext=(1,30),arrowprops=dict(arrowstyle="->",color=RED,lw=1.5))
    ax.text(0.5,50,"힌드사이트\n정정",fontproperties=fp,fontsize=9,color=RED,ha="center")
    ax.bar(labs[:3],vals[:3],color="none",edgecolor=RED,lw=1.4,ls="--",width=0.62,zorder=3)
    fig.tight_layout(); fig.savefig(IMG+"/f_honesty.png",bbox_inches="tight",facecolor="white"); plt.close()
    print("  charts(v2): 4 generated  [2026-07-27 검증상태 배너 적용]")

if __name__=="__main__":
    import sys
    out=sys.argv[1] if len(sys.argv)>1 else "/home/claude/jq_wp/img"
    os.makedirs(out,exist_ok=True); make_charts(out)
