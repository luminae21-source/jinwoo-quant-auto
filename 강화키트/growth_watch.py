#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""growth_watch.py — 성장 관심주 스크린 (이익성장 + 밸류 + 추세)

'종합 스캔(기술적)' 말고, 실적(EPS)이 실제로 성장하는 종목을 추린다.
데이터: 종목재무_KRX(EPS·PER·PBR·DIV) + 종목시총(유니버스) + 월봉(추세).
지표(과거 실적 기준 — 미래성장 보장 아님):
  · EPS성장 YoY = 최근 EPS / 12개월전 EPS − 1
  · EPS 2년CAGR = (최근/24개월전)^(1/2) − 1  (일회성 아닌 지속 성장 확인)
  · PER·PEG(=PER/성장률) — 성장 대비 저평가
  · 추세 = 월봉 종가 ≥ 6개월 이동평균
관심주(A등급): EPS YoY ≥ 15% & 2년성장 &gt; 0 & PER ≤ 40 & 추세 위.
사용: py growth_watch.py [--topn 400] [--minG 0.15]
⚠️ 과거 실적 기반 스크린·정보용. 미래 성장·상승 보장 아님. 투자자문 아님·책임 본인.
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

import os, sys, argparse, json
import numpy as np, pandas as pd, warnings
warnings.filterwarnings("ignore")
BASE = os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass

THEME={  # 대표 테마 라벨(알려진 종목)
 "005930":"반도체","000660":"반도체","042700":"반도체·HBM장비","240810":"반도체장비","036930":"반도체장비",
 "058470":"반도체장비","039030":"반도체장비","166090":"반도체소재","007660":"기판·AI","353200":"기판·AI","402340":"반도체지주",
 "012450":"방산","079550":"방산","047810":"방산","064350":"방산","329180":"조선","042660":"조선","009540":"조선",
 "267260":"전력기기","010120":"전력기기","298040":"전력기기·중공업","034020":"원전·발전","000150":"지주·기계","241560":"건설기계",
 "277810":"로봇","454910":"로봇","196170":"바이오","141080":"바이오","145020":"바이오","085620":"바이오","328130":"바이오",
 "003230":"K푸드","278470":"뷰티","257720":"뷰티유통","161890":"화장품","035420":"인터넷","035720":"인터넷","377300":"핀테크",
 "352820":"엔터","035900":"엔터","041510":"엔터","259960":"게임","036570":"게임","251270":"게임",
}
NAMES={}  # 종목명_맵.csv(있으면) 로 채움

def _find(fn):
    for d in (BASE, os.path.dirname(BASE), os.getcwd()):
        p=os.path.join(d,fn)
        if os.path.exists(p): return p
    return None

def load_names():
    p=_find("종목명_맵.csv")
    m={}
    if p:
        try:
            d=pd.read_csv(p,dtype=str)
            for _,r in d.iterrows(): m[str(r["code"]).zfill(6)]=r["name"]
        except Exception: pass
    return m

def load_fin(field):
    fr=[]
    for f in ("종목재무_KRX_KOSPI.csv","종목재무_KRX_KOSDAQ.csv"):
        p=_find(f)
        if p:
            d=pd.read_csv(p,dtype={"code":str}); d["code"]=d["code"].str.zfill(6)
            d["ym"]=pd.to_datetime(d["date"]).dt.strftime("%Y-%m"); fr.append(d[["ym","code",field]])
    return pd.concat(fr).pivot_table(index="ym",columns="code",values=field,aggfunc="last").sort_index()

def load_px():
    fr=[]
    for f in ("_월봉종가캐시_KOSPI.csv","_월봉종가캐시_KOSDAQ.csv"):
        p=_find(f)
        if p:
            d=pd.read_csv(p,dtype={"code":str}); d["code"]=d["code"].str.zfill(6); fr.append(d)
    return pd.concat(fr).pivot_table(index="ym",columns="code",values="close",aggfunc="last").sort_index()

def load_mcap(topn):
    p=_find("종목시총_30년.csv"); d=pd.read_csv(p,dtype={"code":str}); d["code"]=d["code"].str.zfill(6)
    d["ym"]=pd.to_datetime(d["date"]).dt.strftime("%Y-%m"); last=d["ym"].max()
    top=d[d["ym"]==last].sort_values("mcap",ascending=False)
    return {c:i+1 for i,c in enumerate(top["code"])}, set(top["code"].head(topn))

def run(topn=400, minG=0.15):
    eps=load_fin("EPS"); per=load_fin("PER"); pbr=load_fin("PBR"); div=load_fin("DIV")
    px=load_px(); rank,univ=load_mcap(topn); nm=load_names()
    ymf=eps.index[-1]  # 최신 재무월
    def at(df,shift=0):
        return df.iloc[-1-shift] if len(df)>shift else None
    e0=eps.iloc[-1]; e12=eps.iloc[-13] if len(eps)>13 else eps.iloc[0]; e24=eps.iloc[-25] if len(eps)>25 else eps.iloc[0]
    p0=per.iloc[-1]; pb0=pbr.iloc[-1]; dv0=div.iloc[-1]
    ma6=px.rolling(6).mean().iloc[-1]; last=px.iloc[-1]
    rows=[]
    for c in univ:
        if c not in eps.columns: continue
        en=e0.get(c); e1=e12.get(c); e2=e24.get(c)
        if pd.isna(en) or en<=0: continue
        g1=(en/e1-1) if (pd.notna(e1) and e1>0) else np.nan
        g2=((en/e2)**0.5-1) if (pd.notna(e2) and e2>0) else np.nan
        pr=p0.get(c); pb=pb0.get(c); dv=dv0.get(c)
        peg=(pr/(g1*100)) if (pd.notna(g1) and g1>0 and pd.notna(pr) and pr>0) else np.nan
        tr = (c in px.columns) and pd.notna(last.get(c)) and pd.notna(ma6.get(c)) and last.get(c)>=ma6.get(c)
        rows.append(dict(code=c,name=nm.get(c,THEME.get(c,c) if False else c),theme=THEME.get(c,""),
            g1=g1,g2=g2,per=pr,pbr=pb,peg=peg,div=dv,trend=bool(tr),mrank=rank.get(c,999)))
    df=pd.DataFrame(rows)
    df["name"]=[nm.get(c,c) for c in df["code"]]
    # A등급 관심주: 성장+저평가+추세
    # 베이스효과(적자→흑자 전환 등 EPS 폭주) 노이즈 제외: g1≤300%, g2≤150%
    clean=(df["g1"]<=3.0)&((df["g2"].isna())|(df["g2"]<=1.5))
    dfc=df[clean]
    # A등급: 지속성장(YoY≥minG & 2년>5%)+저평가(PER≤40)+추세위 → PEG 낮은 순
    A=dfc[(dfc["g1"]>=minG)&(dfc["g2"]>=0.05)&(dfc["per"]<=40)&(dfc["per"]>0)&(dfc["trend"])].copy()
    A=A.sort_values("peg")
    # 고성장(지속): YoY≥30% & 2년≥15% → 2년성장 순(일회성 배제)
    HG=dfc[(dfc["g1"]>=0.30)&(dfc["g2"]>=0.15)&(dfc["per"]>0)&(dfc["per"]<=60)].sort_values("g2",ascending=False)
    # 저평가 성장(PEG 낮음, 지속)
    PEGv=dfc[(dfc["g1"]>=minG)&(dfc["g2"]>=0.05)&(dfc["peg"]>0)&(dfc["peg"]<=1.0)&(dfc["per"]>0)].sort_values("peg")
    def line(r):
        th=f" [{r['theme']}]" if r['theme'] else ""
        return (f"  {r['name']:<14}{('EPS성장 %+.0f%%/yr'%(r['g1']*100)):>16}  2y {('%+.0f%%'%(r['g2']*100)) if pd.notna(r['g2']) else '-':>6}"
                f"  PER {r['per']:>5.1f} PEG {('%.2f'%r['peg']) if pd.notna(r['peg']) else '-':>5} PBR {r['pbr']:>4.1f}"
                f"  배당 {r['div']:>3.1f}%  {'추세위' if r['trend'] else '추세아래'}{th}")
    print("="*100)
    print(f"성장 관심주 스크린 — 실적(EPS) 성장주 (재무 {ymf} · 유니버스 시총 상위 {topn})")
    print("="*100)
    print(f"\n【 A등급 관심주 — 성장(YoY≥{int(minG*100)}%)+저평가(PER≤40)+추세위 】 {len(A)}종")
    for _,r in A.head(25).iterrows(): print(line(r))
    print(f"\n【 고성장 — EPS YoY≥30% & 2년 지속성장 】 {len(HG)}종 (상위 15)")
    for _,r in HG.head(15).iterrows(): print(line(r))
    print(f"\n【 저평가 성장 — PEG≤1.0 (성장 대비 싼) 】 {len(PEGv)}종 (상위 15)")
    for _,r in PEGv.head(15).iterrows(): print(line(r))
    print("\n  ── 해석 ──")
    print("  · A등급=실적이 실제로 크는데(YoY↑) 밸류 과하지 않고(PER≤40) 주가도 추세 위 → '성장+안전마진+시장확인' 3박자.")
    print("  · 고성장=성장률 자체 최상위(밸류 무관, 고PER 감수). 저평가성장=PEG 낮아 성장 대비 싼 축.")
    print("  · ⚠️ EPS는 과거 12개월 실적 기준. '미래 성장 예정'은 별개 — 최종 확인은 최신 실적발표·가이던스·수주.")
    print("  · 급락장이라 추세위 종목이 적음. A등급 소수 = 오히려 지금 버티는 진짜 성장주 후보.")
    print("  ⚠️ 과거 실적 스크린·정보용. 상승·미래성장 보장 아님. 투자자문 아님·책임 본인.")
    out=df.sort_values("g1",ascending=False)
    out.to_csv(os.path.join(BASE,"성장관심주.csv"),index=False,encoding="utf-8-sig")
    def pack(x):
        return [dict(code=r["code"],name=r["name"],theme=r["theme"],g1=round(r["g1"]*100,0) if pd.notna(r["g1"]) else None,
                     g2=round(r["g2"]*100,0) if pd.notna(r["g2"]) else None,per=round(r["per"],1) if pd.notna(r["per"]) else None,
                     peg=round(r["peg"],2) if pd.notna(r["peg"]) else None,pbr=round(r["pbr"],1) if pd.notna(r["pbr"]) else None,
                     div=round(r["div"],1) if pd.notna(r["div"]) else None,trend=bool(r["trend"])) for _,r in x.iterrows()]
    json.dump(dict(asof=ymf,A=pack(A.head(30)),HG=pack(HG.head(20)),PEG=pack(PEGv.head(20))),
              open(os.path.join(BASE,"성장관심주_결과.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2,default=str)
    print("  저장: 성장관심주.csv · 성장관심주_결과.json")
    return dict(A=A,HG=HG,PEG=PEGv,asof=ymf)

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--topn",type=int,default=400); ap.add_argument("--minG",type=float,default=0.15); a=ap.parse_args()
    run(a.topn,a.minG)

if __name__=="__main__":
    main()
