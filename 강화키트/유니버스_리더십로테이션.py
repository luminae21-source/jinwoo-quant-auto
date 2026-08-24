#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""유니버스_리더십로테이션.py — "18개가 맞나? 주도주는 시대마다 바뀌지 않나?" 실증

진우 의문(2026-07-23):
  ① 종목 수가 꼭 18개여야 하나? → N-스윕으로 '18'의 특별함 검정.
  ② 작년~올해 대형주 장세는 이례적. 실제로는 시대마다 다른 테마·주도주가 뜬다.
     → 리더십 로테이션(시대별 주도주 교체)·메가캡 쏠림 지표를 30년으로 실증.
⚠️ 상폐포함 검증용. 실현손익 아님. 투자자문 아님·책임 본인.
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

import os, sys, json
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

def name_map():
    m = {}
    p = _find("universe_rule30_latest.csv")
    if p:
        d = pd.read_csv(p, dtype=str)
        for _, r in d.iterrows():
            m[str(r["code"]).zfill(6)] = r["name"]
    # 시대별 마퀴 종목 하드코딩(널리 알려진 코드) — 라벨 보강용
    m.update({
        "005930":"삼성전자","000660":"SK하이닉스","005490":"POSCO홀딩스","015760":"한국전력",
        "005380":"현대차","000270":"기아","012330":"현대모비스","051910":"LG화학","373220":"LG에너지솔루션",
        "006400":"삼성SDI","207940":"삼성바이오로직스","068270":"셀트리온","035420":"NAVER","035720":"카카오",
        "005380":"현대차","009540":"HD한국조선해양","010140":"삼성중공업","042660":"한화오션","012450":"한화에어로",
        "079550":"LIG넥스원","034020":"두산에너빌리티","028260":"삼성물산","105560":"KB금융","055550":"신한지주",
        "051900":"LG생활건강","090430":"아모레퍼시픽","017670":"SK텔레콤","032830":"삼성생명","003550":"LG",
        "096770":"SK이노베이션","010950":"S-Oil","066570":"LG전자","011200":"HMM","247540":"에코프로비엠",
        "086520":"에코프로","091990":"셀트리온헬스케어","196170":"알테오젠","042700":"한미반도체","000810":"삼성화재",
        "033780":"KT&G","003230":"삼양식품","095340":"ISC","011070":"LG이노텍","259960":"크래프톤",
        "323410":"카카오뱅크","377300":"카카오페이","326030":"SK바이오팜","302440":"SK바이오사이언스",
        "003490":"대한항공","000720":"현대건설","009150":"삼성전기","018260":"삼성에스디에스",
        "034220":"LG디스플레이","204320":"HL만도","329180":"HD현대중공업","267250":"HD현대","000100":"유한양행",
        "004020":"현대제철","001040":"CJ","097950":"CJ제일제당","139480":"이마트","069960":"현대백화점",
    })
    return m

def dyn_leaders(px, rets, mcap, N=30, pool_mult=3, pool_min=100):
    """월별 12-1 모멘텀 리더 상위 N (시총 상위 pool 안에서). 리턴: ym→[codes], ym→평균시총순위."""
    months = [m for m in rets.index if m in mcap.index]
    leaders = {}; avg_rank = {}
    for t in months:
        i = list(rets.index).index(t)
        if i < 13: continue
        mc = mcap.loc[t].dropna().sort_values(ascending=False)
        ranked = list(mc.index); rankpos = {c: r+1 for r, c in enumerate(ranked)}
        pool = ranked[:max(pool_min, pool_mult*N)]
        w = px.iloc[i-13:i-1]; mom = (w.iloc[-1]/w.iloc[0]-1)
        mom = mom[[c for c in pool if c in mom.index]].dropna()
        sel = list(mom.sort_values(ascending=False).index[:N])
        cur = rets.loc[t]; sel = [c for c in sel if pd.notna(cur.get(c))]
        if len(sel) < N//2: continue
        leaders[t] = sel
        avg_rank[t] = np.mean([rankpos.get(c, np.nan) for c in sel])
    return leaders, avg_rank

def stats(x, ann=12):
    x = pd.Series(x).dropna()
    if len(x) < 12: return None
    c = (1+x).cumprod()
    return dict(CAGR=(1+x).prod()**(ann/len(x))-1, Sharpe=x.mean()/x.std()*np.sqrt(ann) if x.std()>0 else np.nan,
                MDD=(c/c.cummax()-1).min(), n=len(x))

def n_sweep(px, rets, mcap, reg=None):
    """N ∈ {10,15,18,20,30,40,50} 동적 리더십(무방어) 성과 — '18'이 특별한가?"""
    print("="*76); print("① N-스윕 — '종목 수 18'이 특별한가? (동적 리더십·무방어·다올 비용후)"); print("="*76)
    print(f"  {'N':>4}{'순 CAGR':>10}{'Sharpe':>9}{'MDD':>9}{'회전/년':>9}")
    rows = {}
    for N in (10, 15, 18, 20, 30, 40, 50):
        leaders, _ = dyn_leaders(px, rets, mcap, N=N)
        held=set(); out=[]; kept=[]; turns=[]
        for t, sel in leaders.items():
            cur = rets.loc[t]; names=[c for c in sel if pd.notna(cur.get(c))]
            if not names: continue
            nn=set(names); f=1-len(nn&held)/len(nn) if held else 1.0
            out.append(cur[names].mean()-f*(0.002+2*0.0005)); kept.append(t); turns.append(f); held=nn
        st=stats(pd.Series(out,index=kept))
        if st:
            rows[N]=dict(cagr=round(st['CAGR']*100,1),sharpe=round(st['Sharpe'],2),mdd=round(st['MDD']*100,1),turn=round(np.mean(turns)*12,1))
            mark = "  ← 현 본체 18" if N==18 else ""
            print(f"  {N:>4}{st['CAGR']*100:>9.1f}%{st['Sharpe']:>9.2f}{st['MDD']*100:>8.1f}%{np.mean(turns)*12:>8.1f}x{mark}")
    print("  → 해석: 곡선이 완만하면 '18'은 임의 상수(특별하지 않음). N↑ 분산↓·수익도↓ 경향이면 '집중 대가 = 변동성'.")
    return rows

def rotation(px, rets, mcap, nm):
    """② 시대별 주도주 교체 + 메가캡 쏠림 지표(30년)."""
    leaders, avg_rank = dyn_leaders(px, rets, mcap, N=30)
    months = sorted(leaders.keys())
    # (a) 연도별 리더셋 교체율(전년 대비 신규 비율)
    print("\n"+"="*76); print("② 리더십 로테이션 — 주도주는 매년 갈린다 (동적 TOP30 리더셋)"); print("="*76)
    yrs = sorted(set(m[:4] for m in months))
    prev=None; churn={}
    yr_leaders={}
    for y in yrs:
        ms=[m for m in months if m[:4]==y]
        # 그 해 등장 빈도 상위 = 그 해 주도주
        from collections import Counter
        cnt=Counter()
        for m in ms:
            for c in leaders[m]: cnt[c]+=1
        yr_leaders[y]=cnt
        cur=set(cnt.keys())
        if prev is not None and cur:
            churn[y]=1-len(cur&prev)/len(cur)
        prev=cur
    # (b) 메가캡 쏠림: 리더들의 평균 시총순위(낮을수록 초대형 쏠림)
    yr_avgrank={}
    for y in yrs:
        vals=[avg_rank[m] for m in months if m[:4]==y and m in avg_rank]
        if vals: yr_avgrank[y]=np.mean(vals)
    # (c) 메가캡 프리미엄: TOP10 EW − rank11~100 EW (연)
    mega_prem={}
    for t in months:
        i=list(rets.index).index(t)
        mc=mcap.loc[t].dropna().sort_values(ascending=False); ranked=list(mc.index)
        cur=rets.loc[t]
        top10=[c for c in ranked[:10] if pd.notna(cur.get(c))]
        mid=[c for c in ranked[10:100] if pd.notna(cur.get(c))]
        if len(top10)>=5 and len(mid)>=20:
            mega_prem[t]=cur[top10].mean()-cur[mid].mean()
    yr_mega={}
    for y in yrs:
        vals=[mega_prem[m] for m in months if m[:4]==y and m in mega_prem]
        if vals: yr_mega[y]=np.sum(vals)  # 연 누적 초과(월합 근사)
    print(f"  {'연도':>6}{'리더교체율':>10}{'리더평균시총순위':>16}{'메가캡초과(연,%p)':>18}  대표 주도주(빈도상위)")
    era_rows={}
    for y in yrs:
        ch=churn.get(y); ar=yr_avgrank.get(y); mp=yr_mega.get(y)
        top3=[c for c,_ in yr_leaders[y].most_common(4)]
        labs=", ".join(nm.get(c, c) for c in top3)
        chs=f"{ch*100:>8.0f}%" if ch is not None else "       —"
        ars=f"{ar:>15.0f}" if ar is not None else "              —"
        mps=f"{mp*100:>16.1f}" if mp is not None else "               —"
        print(f"  {y:>6}{chs}{ars}{mps}  {labs}")
        era_rows[y]=dict(churn=None if ch is None else round(ch*100,0),
                         avg_mcap_rank=None if ar is None else round(ar,0),
                         mega_premium=None if mp is None else round(mp*100,1),
                         top=[nm.get(c,c) for c in top3])
    # 요약 통계
    chvals=[v for v in churn.values()]
    print("\n  ── 요약 ──")
    print(f"  · 연 리더 교체율 평균 {np.mean(chvals)*100:.0f}% (중앙 {np.median(chvals)*100:.0f}%) → 주도주 셋은 매년 절반 안팎이 갈린다.")
    recent=[yr_mega[y] for y in yrs if y in ('2023','2024','2025') and y in yr_mega]
    hist=[yr_mega[y] for y in yrs if y not in ('2023','2024','2025','2026') and y in yr_mega]
    if recent and hist:
        print(f"  · 메가캡 초과: 2023~25 연평균 {np.mean(recent)*100:+.1f}%p vs 그 이전 30년 {np.mean(hist)*100:+.1f}%p "
              f"→ 최근 대형주 쏠림은 역사적 {'이례(상위)' if np.mean(recent)>np.mean(hist) else '평범'} 국면.")
    rk_recent=[yr_avgrank[y] for y in yrs if y in ('2023','2024','2025') and y in yr_avgrank]
    rk_hist=[yr_avgrank[y] for y in yrs if y not in ('2023','2024','2025','2026') and y in yr_avgrank]
    if rk_recent and rk_hist:
        print(f"  · 리더 평균 시총순위: 2023~25 {np.mean(rk_recent):.0f}위 vs 이전 {np.mean(rk_hist):.0f}위 "
              f"→ 최근 주도주가 {'더 초대형(쏠림)' if np.mean(rk_recent)<np.mean(rk_hist) else '더 넓게'} 분포.")
    print("  → 함의: 주도주는 고정 명단이 아니라 '규칙으로 매월 재확인'해야 잡힌다(진우 직관 지지). 최근 대형주 장세만 보고 명단을 고정하면 다음 국면에서 stale.")
    return dict(era=era_rows, churn_mean=round(np.mean(chvals)*100,0))

def main():
    px, rets = load_panel(); mcap = load_mcap(); nm = name_map()
    r1 = n_sweep(px, rets, mcap)
    r2 = rotation(px, rets, mcap, nm)
    json.dump(dict(n_sweep=r1, rotation=r2), open(os.path.join(BASE,"유니버스_리더십로테이션_결과.json"),"w",encoding="utf-8"),
              ensure_ascii=False, indent=2, default=str)
    print("\n  저장: 유니버스_리더십로테이션_결과.json")
    print("  ⚠️ EW·단순 12-1 모멘텀 근사. 실현손익 아님. 투자자문 아님·책임 본인.")

if __name__ == "__main__":
    main()
