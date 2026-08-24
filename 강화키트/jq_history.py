#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""jq_history.py — 진우퀀트 이력 데이터베이스 (SQLite 축적)

강화키트의 *_result.json / 추천대시보드_결과.json 을 읽어 실행일자별 스냅샷을
jq_history.db(SQLite)에 축적한다. 같은 날짜 재실행 시 그 날짜분만 갱신(idempotent).
테이블:
  metrics(run_date, source, metric, value, note)   — 팩터 IC·백테 지표 등 수치
  picks(run_date, kind, rank, code, name, weight, stop)  — 추천 종목
  holds(run_date, code, name, track, ret, signal, sev)   — 보유 매도신호
→ jq_hub.py 가 이걸 읽어 추세 그래프/최신 요약을 그린다.
사용: py jq_history.py            (오늘 스냅샷 축적)
      py jq_history.py --self-test
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

import os, sys, json, sqlite3
from datetime import date
BASE=os.path.dirname(os.path.abspath(__file__))
try: sys.stdout.reconfigure(encoding="utf-8")
except Exception: pass
DB=os.path.join(BASE,"jq_history.db")

def _find(fn):
    for d in (BASE, os.path.dirname(BASE), os.path.join(BASE,"..")):
        p=os.path.join(d,fn)
        if os.path.exists(p): return p
    return None
def _load(fn):
    p=_find(fn)
    if not p: return None
    try: return json.load(open(p,encoding="utf-8"))
    except Exception: return None

def _init(cx):
    cx.executescript("""
    CREATE TABLE IF NOT EXISTS metrics(run_date TEXT, source TEXT, metric TEXT, value REAL, note TEXT);
    CREATE TABLE IF NOT EXISTS picks(run_date TEXT, kind TEXT, rank INTEGER, code TEXT, name TEXT, weight REAL, stop REAL);
    CREATE TABLE IF NOT EXISTS holds(run_date TEXT, code TEXT, name TEXT, track TEXT, ret REAL, signal TEXT, sev INTEGER);
    """)

def collect(rd):
    """(metrics, picks, holds) 튜플 리스트 생성."""
    M=[]; P=[]; H=[]
    # 1) factor_efficacy_result.json : {팩터:{meanIC,ic_t,ls_sharpe,...}}
    fe=_load("factor_efficacy_result.json")
    if isinstance(fe,dict):
        for k,v in fe.items():
            if isinstance(v,dict) and "meanIC" in v:
                M.append((rd,"factor",k,float(v["meanIC"]),f"t{v.get('ic_t','')}"))
    # 2) style_conditional_result.json : {method:{result:{성장주/가치주:{팩터:{meanIC..}}}}}
    sc=_load("style_conditional_result.json")
    if isinstance(sc,dict) and "pbr" in sc:
        for grp,facs in sc["pbr"].get("result",{}).items():
            for fk,fv in facs.items():
                if isinstance(fv,dict) and "meanIC" in fv:
                    M.append((rd,f"style_pbr_{grp}",fk,float(fv["meanIC"]),f"t{fv.get('ic_t','')}"))
    # 3) ev_fcf_factor_result.json : {results:{팩터:{meanIC..}}}
    ev=_load("ev_fcf_factor_result.json")
    if isinstance(ev,dict):
        for k,v in (ev.get("results",{}) or {}).items():
            if isinstance(v,dict) and "meanIC" in v:
                M.append((rd,"evfcf",k,float(v["meanIC"]),f"t{v.get('ic_t','')}"))
    # 4) exit_routing_result.json : {트랙:{전략:{cagr,mdd,sharpe}}}
    er=_load("exit_routing_result.json")
    if isinstance(er,dict):
        for trk,strat in er.items():
            for sk,sv in strat.items():
                if isinstance(sv,dict) and "mdd" in sv:
                    M.append((rd,f"exit_{trk}",f"{sk}_mdd",float(sv["mdd"]),""))
                    M.append((rd,f"exit_{trk}",f"{sk}_cagr",float(sv.get("cagr",0)),""))
    # 5) multifactor_result.json : {backtest:{meanIC,ls_ann,ls_sharpe,hit}}
    mf=_load("multifactor_result.json")
    if isinstance(mf,dict) and isinstance(mf.get("backtest"),dict):
        for k,v in mf["backtest"].items():
            try: M.append((rd,"multifactor",k,float(v),""))
            except Exception: pass
    # 6) 추천대시보드_결과.json : picks + holds + nA
    rc=_load("추천대시보드_결과.json")
    if isinstance(rc,dict):
        M.append((rd,"reco","nA",float(rc.get("nA",0)),f"price {rc.get('pym','')}/fin {rc.get('fym','')}"))
        for kind in ("value","growth"):
            for i,r in enumerate(rc.get(kind,[]) or []):
                P.append((rd,kind,i+1,r.get("code",""),r.get("name",""),
                          float(r.get("weight",0) or 0),float(r.get("stop",0) or 0)))
        for h in rc.get("holds",[]) or []:
            H.append((rd,h.get("code",""),h.get("name",""),h.get("track",""),
                      float(h.get("ret",0) or 0),h.get("signal",""),int(h.get("sev",0) or 0)))
    return M,P,H

def run():
    rd=date.today().isoformat()
    M,P,H=collect(rd)
    cx=sqlite3.connect(DB); _init(cx)
    for tbl in ("metrics","picks","holds"):
        cx.execute(f"DELETE FROM {tbl} WHERE run_date=?",(rd,))
    cx.executemany("INSERT INTO metrics VALUES(?,?,?,?,?)",M)
    cx.executemany("INSERT INTO picks VALUES(?,?,?,?,?,?,?)",P)
    cx.executemany("INSERT INTO holds VALUES(?,?,?,?,?,?,?)",H)
    cx.commit()
    ndates=cx.execute("SELECT COUNT(DISTINCT run_date) FROM metrics").fetchone()[0]
    cx.close()
    print(f"이력 축적: {rd} · metrics {len(M)} · picks {len(P)} · holds {len(H)} · 누적 {ndates}개 날짜 → jq_history.db")

def _selftest():
    import tempfile,glob
    global DB,BASE
    d=tempfile.mkdtemp(); BASE=d; DB=os.path.join(d,"t.db")
    json.dump({"배당수익률":{"meanIC":0.049,"ic_t":5.8}},open(os.path.join(d,"factor_efficacy_result.json"),"w",encoding="utf-8"),ensure_ascii=False)
    json.dump({"asof":"2026-07","nA":6,"value":[{"code":"005830","name":"DB손보","weight":2.5,"stop":97800}],
               "growth":[],"holds":[{"code":"000660","name":"SK하이닉스","track":"성장","ret":12.0,"signal":"트레일 이탈","sev":3}]},
              open(os.path.join(d,"추천대시보드_결과.json"),"w",encoding="utf-8"),ensure_ascii=False)
    run()
    cx=sqlite3.connect(DB)
    m=cx.execute("SELECT value FROM metrics WHERE metric='배당수익률'").fetchone()
    p=cx.execute("SELECT name FROM picks").fetchone()
    h=cx.execute("SELECT signal FROM holds").fetchone()
    ok = (m and abs(m[0]-0.049)<1e-9) and (p and p[0]=="DB손보") and (h and "트레일" in h[0])
    print("  [%s] 축적/조회 라운드트립" % ("OK" if ok else "FAIL"))
    cx.close(); return ok

def main():
    if "--self-test" in sys.argv:
        sys.exit(0 if _selftest() else 1)
    run()

if __name__=="__main__":
    main()
