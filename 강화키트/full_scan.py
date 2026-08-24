#!/usr/bin/env python3
# -*- coding: utf-8 -*-
r"""full_scan.py — 종합 스캐너: 주도주(규칙) + 반등 + 상승준비 (시총 상위 300, 일봉)

한 번에 세 부류를 발굴:
  🔵 주도주(규칙)   : 현재 규칙 유니버스(pool100·12-1 상위30) — 이미 시장 주도
  🟢 반등확정       : MA50 회복(최근 아래였다가 되찾음) — 추세 복구
  🟡 초기반등       : MA20 회복(아직 MA50 아래) — 초기 바운스
  🟣 상승준비       : 아직 안 움직였으나 상승 채비 (3종 복합)
       · 눌림목  = 상승추세(MA200↑·MA50 위) 유지 중 조정·되돌림
       · 압축    = 변동성 수축(횡보 압축) → 돌파 임박(squeeze)
       · 바닥    = 큰 하락 후 저점권 안정·거래량 감소(매집)
  ⚪ 기타/하락      : 신호 없음

데이터: 시총 상위 300(종목시총_30년.csv) × 최신 일봉(종목일봉_30년_*.csv).
사용:  py full_scan.py            (PC: 최신 일봉 직접 읽음)
       py full_scan.py --cache _일봉_top300.csv --topn 300
⚠️ 기계적 기술 신호. 진입확정 아님·실현손익 아님·투자자문 아님·책임 본인.
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

NAMES = {"005930":"삼성전자","000660":"SK하이닉스","402340":"SK스퀘어","005935":"삼성전자우","009150":"삼성전기",
"005380":"현대차","373220":"LG에너지솔루션","105560":"KB금융","032830":"삼성생명","207940":"삼성바이오로직스",
"028260":"삼성물산","000270":"기아","055550":"신한지주","329180":"HD현대중공업","012450":"한화에어로",
"034020":"두산에너빌리티","012330":"현대모비스","034730":"SK","068270":"셀트리온","086790":"하나금융지주",
"006400":"삼성SDI","066570":"LG전자","035420":"NAVER","000810":"삼성화재","267260":"HD현대일렉트릭",
"010120":"LS일렉트릭","298040":"효성중공업","005490":"POSCO홀딩스","009540":"HD한국조선해양","042660":"한화오션",
"316140":"우리금융지주","006800":"미래에셋증권","015760":"한국전력","010130":"고려아연","000150":"두산",
"042700":"한미반도체","138040":"메리츠금융","010140":"삼성중공업","096770":"SK이노베이션","064350":"현대로템",
"011200":"HMM","017670":"SK텔레콤","051910":"LG화학","033780":"KT&G","196170":"알테오젠","024110":"기업은행",
"079550":"LIG넥스원","010950":"S-Oil","011070":"LG이노텍","267250":"HD현대","035720":"카카오","003550":"LG",
"018260":"삼성에스디에스","278470":"에이피알","086280":"현대글로비스","047810":"한국항공우주","003670":"포스코퓨처엠",
"030200":"KT","307950":"현대오토에버","247540":"에코프로비엠","086520":"에코프로","000720":"현대건설",
"323410":"카카오뱅크","005940":"NH투자증권","003490":"대한항공","006260":"LS","443060":"HD현대마린",
"161390":"한국타이어","036930":"주성엔지니어링","003230":"삼양식품","028050":"삼성E&A","277810":"레인보우로보틱스",
"078930":"GS","007660":"이수페타시스","090430":"아모레퍼시픽","047040":"대우건설","950160":"코오롱티슈진",
"326030":"SK바이오팜","240810":"원익IPS","241560":"두산밥캣","353200":"대덕전자","004170":"신세계",
"001440":"대한전선","009830":"한화솔루션","000100":"유한양행","377300":"카카오페이","271560":"오리온",
"036570":"엔씨소프트","034220":"LG디스플레이","128940":"한미약품","000990":"DB하이텍","023530":"롯데쇼핑",
"011790":"SKC","141080":"리가켐바이오","001040":"CJ","066970":"엘앤에프","082740":"한화엔진","010060":"OCI홀딩스",
"002380":"KCC","051900":"LG생활건강","004020":"현대제철","012510":"더존비즈온","069960":"현대백화점",
"001450":"현대해상","095340":"ISC","251270":"넷마블","036460":"한국가스공사","145020":"휴젤","011780":"금호석유",
"097950":"CJ제일제당","302440":"SK바이오사이언스","161890":"한국콜마","450080":"에코프로머티","011170":"롯데케미칼",
"006360":"GS건설","139480":"이마트","204320":"HL만도","007070":"GS리테일","007340":"DN오토모티브",
"004370":"농심","073240":"금호타이어","051600":"한전KPS","008770":"호텔신라","002790":"아모레G",
"032820":"우리기술","035900":"JYP","041510":"에스엠","181710":"NHN","089860":"롯데렘닉스","012630":"HDC",
"229640":"LS에코에너지","192080":"더블유게임즈","127120":"디엔에이링크","017960":"한국카본","218410":"RFHIC",
"294870":"HDC현대산업","034230":"파라다이스","195940":"HK이노엔","166090":"하나머티리얼즈","323280":"태성",
"300720":"한일시멘트","031330":"에스에이엠티","058470":"리노공업","039030":"이오테크닉스","088980":"맥쿼리인프라",
"001120":"LX인터내셔널","082640":"동양생명","006040":"동원산업","023590":"다우기술","028670":"팬오션","257720":"실리콘투",
"139130":"DGB금융지주","214450":"파마리서치","018670":"SK가스","005830":"DB손해보험","088350":"한화생명","032640":"LG유플러스",
"047050":"포스코인터내셔널","001800":"오리온홀딩스","000120":"CJ대한통운","006280":"녹십자","267270":"HD현대건설기계",
"298020":"효성티앤씨","375500":"DL이앤씨","005850":"에스엘","039490":"키움증권","140860":"파크시스템스","383220":"F&F",
"096530":"씨젠","081660":"휠라홀딩스","009970":"영원무역홀딩스","322000":"현대에너지솔루션","030000":"제일기획","003690":"코리안리",
"111770":"영원무역","112610":"씨에스윈드","069620":"대웅제약","352820":"하이브","004000":"롯데정밀화학","007310":"오뚜기",
"004990":"롯데지주","017800":"현대엘리베이터","005070":"코스모신소재","022100":"포스코DX","103140":"풍산","192820":"코스맥스",
"131290":"티에스이","000240":"한국앤컴퍼니","060370":"이글벳","000080":"하이트진로","001430":"세아베스틸지주","017960":"한국카본",
"029780":"삼성카드","030610":"교보증권","009420":"한올바이오파마","001740":"SK네트웍스","011210":"현대위아","003540":"대신증권",
"004800":"효성","012750":"에스원","000880":"한화","001720":"신영증권","003570":"S&T중공업","007390":"네이처셀","008930":"한미사이언스",
"000250":"삼천당제약","000500":"가온전선","011790":"SKC","005440":"현대지에프홀딩스","007810":"코리아써키트","000880":"한화"}

def _find(fn):
    for d in (BASE, os.path.dirname(BASE), os.getcwd()):
        p=os.path.join(d,fn)
        if os.path.exists(p): return p
    return None

def build_namemap(codes):
    """이름 채우기: 하드코딩 → 캐시(종목명_맵.csv) → FDR/pykrx(PC·최초 1회, 이후 캐시)."""
    m=dict(NAMES)
    p=_find("종목명_맵.csv")
    if p:
        try:
            nm=pd.read_csv(p,dtype=str)
            for _,r in nm.iterrows():
                c=str(r["code"]).zfill(6)
                if c not in m and isinstance(r["name"],str): m[c]=r["name"]
        except Exception: pass
    missing=[c for c in codes if c not in m]
    if missing:
        got=False
        try:
            import FinanceDataReader as fdr
            lst=fdr.StockListing("KRX")
            cc=next((x for x in ("Code","Symbol","code") if x in lst.columns),None)
            cn=next((x for x in ("Name","name") if x in lst.columns),None)
            if cc and cn:
                lst["_c"]=lst[cc].astype(str).str.zfill(6)
                d2=dict(zip(lst["_c"],lst[cn]))
                for c in missing:
                    if c in d2 and isinstance(d2[c],str): m[c]=d2[c]
                got=True
        except Exception:
            try:
                from pykrx import stock
                for c in missing:
                    try:
                        nm=stock.get_market_ticker_name(c)
                        if nm: m[c]=nm; got=True
                    except Exception: pass
            except Exception: pass
        if got:
            try:
                pd.DataFrame([{"code":c,"name":m[c]} for c in sorted(m)]).to_csv(
                    os.path.join(BASE,"종목명_맵.csv"),index=False,encoding="utf-8-sig")
            except Exception: pass
    return m

def scan_universe(topn=300):
    p=_find("종목시총_30년.csv")
    if not p: return None
    m=pd.read_csv(p,dtype={"code":str}); m["code"]=m["code"].str.zfill(6)
    m["ym"]=pd.to_datetime(m["date"]).dt.strftime("%Y-%m"); last=m["ym"].max()
    return m[m["ym"]==last].sort_values("mcap",ascending=False).head(topn)["code"].tolist()

def rule_universe():
    p=_find("유니버스_규칙화_현재.csv")
    if p:
        try: return set(pd.read_csv(p,dtype={"code":str})["code"].str.zfill(6))
        except Exception: pass
    return set()

def load_daily(codes, cache=None):
    cs=set(codes)
    if cache:
        p=_find(cache)
        if p:
            d=pd.read_csv(p,dtype={"code":str}); d["code"]=d["code"].str.zfill(6)
            d["date"]=pd.to_datetime(d["date"]); return d[d["code"].isin(cs)]
    frames=[]
    for fn in ("종목일봉_30년_KOSPI.csv","종목일봉_30년_KOSDAQ.csv"):
        p=_find(fn)
        if not p: continue
        for ch in pd.read_csv(p,dtype={"code":str},usecols=["date","code","high","low","close","volume"],chunksize=500000):
            ch["code"]=ch["code"].str.zfill(6); ch=ch[ch["code"].isin(cs)]
            if len(ch): frames.append(ch)
    if not frames: return pd.DataFrame()
    d=pd.concat(frames,ignore_index=True); d["date"]=pd.to_datetime(d["date"]); return d

def classify(g, in_rule):
    g=g.sort_values("date")
    if len(g)<60: return None
    c=g["close"]; h=g["high"]; l=g["low"]; v=g["volume"]; last=c.iloc[-1]
    ma20=c.rolling(20).mean(); ma50=c.rolling(50).mean(); ma200=c.rolling(200).mean()
    m20,m50,m200=ma20.iloc[-1],ma50.iloc[-1],ma200.iloc[-1]
    has200=pd.notna(m200)
    up200 = has200 and (ma200.iloc[-1]>ma200.iloc[-21])       # MA200 상향
    a50=last>=m50 if pd.notna(m50) else False
    a20=last>=m20 if pd.notna(m20) else False
    a200=last>=m200 if has200 else False
    to50=(last/m50-1)*100 if pd.notna(m50) else np.nan
    to20=(last/m20-1)*100 if pd.notna(m20) else np.nan
    was_below50=(c.iloc[-11:-1]<ma50.iloc[-11:-1]).any() if pd.notna(m50) else False
    # 변동성/베이스 지표
    hi20=c.iloc[-20:].max(); dd20=(last/hi20-1)*100
    hi250=c.iloc[-250:].max() if len(c)>=250 else c.max(); ddhi=(last/hi250-1)*100
    lo60=l.iloc[-60:].min(); near_low=(last/lo60-1)*100
    # 신고가·돌파 · 거래량 급증
    near_high = ddhi >= -6                                        # 250일 신고가 6% 이내
    hh60prev = h.iloc[-61:-1].max() if len(h)>60 else h.iloc[:-1].max()
    breakout = pd.notna(hh60prev) and last > hh60prev            # 60일 신고가 돌파(종가)
    bw=(h.rolling(20).max()-l.rolling(20).min())/c                # 밴드폭(변동성)
    bw_now=bw.iloc[-1]; bw_rank=(bw.iloc[-120:].rank(pct=True).iloc[-1]) if len(bw.dropna())>=60 else np.nan
    bw_contract = pd.notna(bw.iloc[-41]) and bw_now<bw.iloc[-41]  # 40일전보다 수축
    vol20=v.iloc[-20:].mean(); vol60=v.iloc[-60:].mean(); vol_dry=(vol20<vol60*0.85) if vol60>0 else False
    volr=(v.iloc[-1]/vol20) if vol20>0 else np.nan
    vsurge = pd.notna(volr) and volr>=1.5                        # 거래량 급증(20일평균 1.5배↑)
    vstrong = pd.notna(volr) and volr>=2.5
    hl = (l.iloc[-10:].min() > l.iloc[-20:-10].min())            # higher-low
    # 상승준비 3종
    pull = a200 and up200 and a50 and (-20<=dd20<=-3) and (pd.notna(to20) and to20<=8)   # 눌림목
    squeeze = a200 and (pd.notna(bw_rank) and bw_rank<=0.30) and bw_contract               # 압축
    base = (ddhi<-30) and (near_low<=12) and vol_dry and (pd.notna(bw_rank) and bw_rank<=0.45) and hl  # 바닥
    prep=[]
    if pull: prep.append("눌림")
    if squeeze: prep.append("압축")
    if base: prep.append("바닥")
    # 우선순위 분류
    if in_rule:
        cat="🔵 주도주"; sub="규칙 유니버스"
    elif pd.notna(m50) and a50:
        cat="🟢 추세위"; sub=("MA50 신규회복" if was_below50 else "MA50 위 추세유지")
    elif prep:
        cat="🟣 상승준비"; sub="+".join(prep)
    elif pd.notna(m20) and a20:
        cat="🟡 초기반등"; sub="MA20 회복(MA50 대기)"
    else:
        cat="⚪ 기타"; sub="신호 없음"
    flags=("🆕신고가 " if near_high else "")+("🚀돌파 " if breakout else "")+("⚡⚡ " if vstrong else ("⚡ " if vsurge else ""))
    return dict(last=last,to50=to50,to20=to20,dd20=dd20,ddhi=ddhi,near_low=near_low,
                bw_rank=None if pd.isna(bw_rank) else round(bw_rank*100), volr=volr,
                a200=bool(a200),up200=bool(up200),cat=cat,sub=sub,prep="+".join(prep),
                near_high=bool(near_high),breakout=bool(breakout),vsurge=bool(vsurge),vstrong=bool(vstrong),flags=flags.strip())

_R="🚀"; _B="🔵"; _G="🟢"; _P="🟣"; _Y="🟡"; _W="⚪"
SIGSTATS={
 _R:dict(nm="신고가·돌파",wr=35,payoff=2.4,exp=2.2,w3=49),
 _B:dict(nm="주도주",wr=34,payoff=2.5,exp=2.2,w3=49),
 _G:dict(nm="추세위",wr=33,payoff=2.6,exp=2.3,w3=47),
 _P:dict(nm="상승준비",wr=37,payoff=2.0,exp=0.9,w3=47),
 _Y:dict(nm="초기반등",wr=31,payoff=2.2,exp=-0.2,w3=47),
}
STOP_NOTE="권장 손절 −12~15% (−8%는 휩쏘) · 역사적으론 넓은 손절/추세청산이 큰 추세를 더 포착"
_COL={_B:"#58a6ff",_G:"#3fb950",_P:"#a371f7",_Y:"#d29922",_W:"#6b7280",_R:"#f85149"}
_CATNM={_B:"주도주",_G:"추세위",_P:"상승준비",_Y:"초기반등",_W:"기타"}

def _isnum(x):
    return x is not None and not (isinstance(x,float) and pd.isna(x))

def _statline(tag):
    st=SIGSTATS.get(tag)
    if not st: return ""
    c="#3fb950" if st["exp"]>0 else "#f85149"
    return ("<div class=stat>역사(30년): 3M상승 "+str(st["w3"])+"% · 실전승률 "+str(st["wr"])+"% · 손익비 "+str(st["payoff"])
            +" · 기대값 <b style='color:"+c+"'>"+("%+.1f"%st["exp"])+"%/트레이드</b></div>")

def write_html(df, asof, cnt, nsurge, topn):
    import html as _h
    rows=df.to_dict("records")
    bo=sorted([r for r in rows if r.get("near_high") or r.get("breakout")],
              key=lambda r:-(r["ddhi"] if _isnum(r["ddhi"]) else -99))
    def fl(r):
        s=""
        if r.get("breakout"): s+="<span class=b style='background:"+_COL[_R]+"'>"+_R+"돌파</span>"
        elif r.get("near_high"): s+="<span class=b style='background:#c9642f'>🆕신고가권</span>"
        if r.get("vstrong"): s+="<span class=v>⚡⚡</span>"
        elif r.get("vsurge"): s+="<span class=v>⚡</span>"
        return s
    def v50(r):
        return ("%+.0f%%"%r["to50"]) if _isnum(r["to50"]) else "-"
    def vdd(r):
        return ("%+.0f%%"%r["ddhi"]) if _isnum(r["ddhi"]) else "-"
    def sortk(tag,rs):
        big=lambda r:(r["to50"] if _isnum(r["to50"]) else -999)
        sml=lambda r:(r["to50"] if _isnum(r["to50"]) else 999)
        bw =lambda r:(r["bw_rank"] if _isnum(r["bw_rank"]) else 99)
        if tag==_B: return sorted(rs,key=lambda r:-big(r))
        if tag==_G: return sorted(rs,key=sml)
        if tag==_P: return sorted(rs,key=bw)
        if tag==_Y: return sorted(rs,key=lambda r:-big(r))
        return rs
    def rl(tag): return [r for r in rows if str(r["cat"]).startswith(tag)]
    def rowh(tag,r):
        nm=_h.escape(str(r["name"]))
        if tag==_P:
            bwv=str(int(r["bw_rank"])) if _isnum(r["bw_rank"]) else "-"
            d="<b style='color:"+_COL[_P]+"'>"+str(r["sub"])+"</b> · 고점比"+vdd(r)+" · 변동성 "+bwv+"%ile"
        elif tag==_G: d=str(r["sub"])+" · MA50까지 "+v50(r)
        elif tag==_Y: d="MA50까지 "+v50(r)
        else: d=("추세위" if r["a200"] else "추세아래")+" · MA50까지 "+v50(r)
        return "<tr><td class=n>"+nm+"</td><td>"+format(r["last"],",.0f")+"</td><td>"+fl(r)+"</td><td class=d>"+d+"</td></tr>"
    def section(tag,title,desc,cap=None):
        rs=sortk(tag,rl(tag)); shown=rs[:cap] if cap else rs
        body="".join(rowh(tag,r) for r in shown)
        more=("<div class=more>…외 "+str(len(rs)-len(shown))+"종 (CSV)</div>") if (cap and len(rs)>cap) else ""
        return ("<h3><span class=dot style='background:"+_COL[tag]+"'></span>"+title+" <span class=cnt>"+str(len(rs))+"종</span></h3>"
                +"<div class=desc>"+desc+"</div>"+_statline(tag)+"<table><tbody>"+body+"</tbody></table>"+more)
    def borow(r):
        nm=_h.escape(str(r["name"]))
        return ("<tr><td class=n>"+nm+"</td><td>"+format(r["last"],",.0f")+"</td><td>"+fl(r)
                +"</td><td class=d>고점比"+vdd(r)+" · "+_CATNM.get(str(r["cat"])[0],"")+" · 거래량 "+format(r["volr"],".1f")+"x</td></tr>")
    css=("<style>:root{--bg:#0f1115;--panel:#171a21;--ink:#e8eaed;--muted:#9aa0aa;--line:#2a2f3a}"
     "@media(prefers-color-scheme:light){:root{--bg:#f6f7f9;--panel:#fff;--ink:#1a1d23;--muted:#5b626d;--line:#e2e5ea}}"
     "*{box-sizing:border-box}body{margin:0;font-family:-apple-system,'Segoe UI','Noto Sans KR',sans-serif;background:var(--bg);color:var(--ink);font-size:13px}"
     ".wrap{max-width:700px;margin:0 auto;padding:26px 18px 60px}h1{font-size:20px;margin:0 0 2px}.sub{color:var(--muted);font-size:12px;margin-bottom:12px}"
     ".sum{display:flex;gap:6px;margin:12px 0 4px;flex-wrap:wrap}.pill{flex:1;min-width:70px;text-align:center;border:1px solid var(--line);border-radius:10px;padding:8px 3px;background:var(--panel)}.pill b{font-size:18px;display:block}.pill span{font-size:9.5px;color:var(--muted)}"
     "h3{font-size:14px;margin:20px 0 2px;display:flex;align-items:center;gap:6px}.cnt{color:var(--muted);font-size:11px;font-weight:400}.desc{font-size:11.5px;color:var(--muted);margin-bottom:3px}"
     ".stat{font-size:11px;color:var(--muted);background:var(--panel);border:1px solid var(--line);border-radius:7px;padding:4px 8px;margin-bottom:5px}"
     "table{width:100%;border-collapse:collapse}td{padding:5px 6px;border-bottom:1px solid var(--line)}td.n{font-weight:600;width:104px}td:nth-child(2){text-align:right;width:74px;font-variant-numeric:tabular-nums}td:nth-child(3){width:110px}td.d{color:var(--muted);font-size:11px}"
     ".dot{width:9px;height:9px;border-radius:50%;display:inline-block}.b{font-size:9.5px;font-weight:700;color:#fff;padding:1px 5px;border-radius:5px;margin-right:3px}.v{color:#d29922;font-size:11px}"
     ".more{font-size:11px;color:var(--muted);padding:4px 6px}.hot{background:rgba(248,81,73,.08);border:1px solid rgba(248,81,73,.5);border-radius:10px;padding:6px 10px;margin:10px 0 2px}"
     ".note{background:rgba(163,113,247,.08);border:1px solid var(--line);border-radius:10px;padding:10px 13px;font-size:11.5px;margin:10px 0}.k{font-size:11px;color:var(--muted);margin-top:14px}</style>")
    C=cnt
    pills=("<div class=sum>"
      +"<div class=pill><b style='color:"+_COL[_R]+"'>"+str(len(bo))+"</b><span>"+_R+" 신고가</span></div>"
      +"<div class=pill><b style='color:#d29922'>"+str(nsurge)+"</b><span>⚡ 거래량</span></div>"
      +"<div class=pill><b style='color:"+_COL[_B]+"'>"+str(C[_B])+"</b><span>"+_B+" 주도주</span></div>"
      +"<div class=pill><b style='color:"+_COL[_G]+"'>"+str(C[_G])+"</b><span>"+_G+" 추세위</span></div>"
      +"<div class=pill><b style='color:"+_COL[_P]+"'>"+str(C[_P])+"</b><span>"+_P+" 상승준비</span></div>"
      +"<div class=pill><b style='color:"+_COL[_Y]+"'>"+str(C[_Y])+"</b><span>"+_Y+" 초기반등</span></div></div>")
    note=("<div class=note><b>기대값 읽는 법:</b> 개별 3개월 상승확률은 ~47~49%(반반)지만, 손절·추세편승으로 손익비 2.4~2.6 → 기대값 플러스. "
          +_R+"·"+_G+"가 최고(+2%대/트레이드). "+STOP_NOTE+". 급락장이라 분할·소량.</div>")
    hot=("<div class=hot><b style='color:"+_COL[_R]+"'>"+_R+" 신고가·돌파 "+str(len(bo))+"종</b> — 급락장서 홀로 강한 최강 모멘텀</div>"
         +_statline(_R)+"<table><tbody>"+"".join(borow(r) for r in bo)+"</tbody></table>")
    body=("<h1>종합 스캔 — 시총 상위 "+str(topn)+"</h1><div class=sub>일봉 "+asof+" · 신고가·돌파+거래량급증 · 섹션마다 역사 기대값</div>"
          +pills+note+hot
          +section(_P,"상승준비 — 눌림·압축·바닥","아직 안 오른 채비. 압축 강한 순")
          +section(_G,"추세위 — MA50 회복/유지","진입 우선. MA50 근접 순",20)
          +section(_B,"주도주 — 규칙 유니버스","이미 주도. 눌림 시 추가")
          +section(_Y,"초기반등 — MA20 회복","관찰. MA50 돌파 시 승격",12)
          +"<div class=k>역사 통계=30년 이벤트스터디(추세청산·다올 비용후) · 과거통계·미래보장 아님 · 전체 CSV · 투자자문 아님·책임 본인</div>")
    doc=("<!DOCTYPE html><html lang=ko><head><meta charset=UTF-8><meta name=viewport content='width=device-width,initial-scale=1'><title>종합 스캔</title>"
         +css+"</head><body><div class=wrap>"+body+"</div></body></html>")
    open(os.path.join(BASE,"종합스캔_현재.html"),"w",encoding="utf-8").write(doc)


def run(topn=300, cache=None, surge=False):
    codes=scan_universe(topn)
    if not codes: print("시총 데이터 없음"); return
    rule=rule_universe()
    d=load_daily(codes,cache)
    if len(d)==0: print("일봉 데이터 없음 (종목일봉_30년_*.csv 확인)"); return
    nmap=build_namemap(list(d["code"].unique()))
    rows=[]
    for code,g in d.groupby("code"):
        r=classify(g, code in rule)
        if r: r["code"]=code; r["name"]=nmap.get(code,code); rows.append(r)
    df=pd.DataFrame(rows)
    if surge: df=df[df["vsurge"]]                                   # 거래량 급증만 필터
    asof=d["date"].max().strftime("%Y-%m-%d")
    order={"🔵":0,"🟢":1,"🟣":2,"🟡":3,"⚪":4}; df["_o"]=df["cat"].str[0].map(order)
    catlabel={"🔵":"주도주","🟢":"추세위","🟣":"상승준비","🟡":"초기반등","⚪":"기타"}
    print("="*98); print(f"종합 스캔 — 시총 상위 {topn} (스캔 {len(df)}종, 일봉 {asof})"+("  [거래량급증 필터]" if surge else "")); print("="*98)
    # 🚀 신고가·돌파 (전 범위 교차)
    bo=df[(df["near_high"])|(df["breakout"])].copy().sort_values("ddhi",ascending=False)
    print(f"\n【 🚀 신고가·돌파 (전 범위) 】 {len(bo)}종 — 급락장서 신고가권=최강")
    if len(bo)==0: print("   (없음 — 급락장이라 신고가 도달 종목 극소)")
    for _,r in bo.iterrows():
        tag="🚀돌파" if r["breakout"] else "🆕신고가권"; vol=("⚡⚡" if r["vstrong"] else ("⚡" if r["vsurge"] else ""))
        print(f"   {r['name']:<14}{r['last']:>10,.0f}  {tag} 고점比{r['ddhi']:+.0f}% 거래량{r['volr']:.1f}x{vol}  ({catlabel.get(r['cat'][0],'')})")
    def block(tag,title,cap=None):
        sub=df[df["cat"].str.startswith(tag)].copy()
        if tag=="🔵": sub=sub.sort_values("to50",ascending=False)
        elif tag=="🟢": sub=sub.sort_values("to50",ascending=True)
        elif tag=="🟣": sub["_b"]=sub["bw_rank"].fillna(99); sub=sub.sort_values(["_b"])
        elif tag=="🟡": sub=sub.sort_values("to50",ascending=False)
        print(f"\n【 {title} 】 {len(sub)}종" + (f" (상위 {cap} 표시)" if cap and len(sub)>cap else ""))
        if len(sub)==0: print("   (없음)"); return
        for _,r in (sub.head(cap) if cap else sub).iterrows():
            t50=f"{r['to50']:+.0f}%" if pd.notna(r['to50']) else "-"
            fl=(" "+r["flags"]) if r["flags"] else ""
            if tag=="🟣": extra=f"[{r['sub']}] 고점比{r['ddhi']:+.0f}% 변동성{r['bw_rank'] if r['bw_rank'] is not None else '-'}%ile 거래량{r['volr']:.1f}x"
            elif tag=="🟢": extra=f"{r['sub']} · MA50까지{t50} 거래량{r['volr']:.1f}x"
            elif tag=="🟡": extra=f"MA50까지{t50} 거래량{r['volr']:.1f}x"
            else: extra=f"{'추세위' if r['a200'] else '추세아래'} MA50까지{t50}"
            print(f"   {r['name']:<14}{r['last']:>10,.0f}  {extra}{fl}")
    block("🔵","주도주(규칙 유니버스) — 이미 주도, 눌림 시 추가")
    block("🟢","추세위(MA50 회복/유지) — 진입 우선",25)
    block("🟣","상승준비 — 눌림·압축·바닥(발굴)")
    block("🟡","초기반등 — MA20 회복(관찰)",20)
    nother=(df["_o"]==4).sum()
    print(f"\n【 ⚪ 기타/하락 】 {nother}종 (생략)")
    cnt={k:int((df['cat'].str.startswith(k)).sum()) for k in ["🔵","🟢","🟣","🟡","⚪"]}
    nsurge=int(df["vsurge"].sum()); nbo=len(bo)
    print("\n  ── 요약 ──")
    print(f"  🚀신고가·돌파 {nbo} · 🔵주도주 {cnt['🔵']} · 🟢추세위 {cnt['🟢']} · 🟣상승준비 {cnt['🟣']} · 🟡초기반등 {cnt['🟡']} · ⚪기타 {cnt['⚪']}")
    print(f"  · ⚡거래량 급증(20일평균 1.5배↑) {nsurge}종. 신호에 ⚡ 붙은 종목 = 매수세 확인(신뢰도↑).")
    print(f"  · 발굴: 🚀신고가·돌파(최강 모멘텀)와 🟣상승준비(채비)가 발굴 핵심. 급락장이라 신고가는 극소=오히려 귀함.")
    print(f"  · 급락장 진입은 분할·소량. 손절=MA50 재이탈. 매주 full_scan.bat 재실행. (--surge: 거래량 급증만)")
    print("  ⚠️ 기계적 기술 신호. 진입확정 아님·투자자문 아님·책임 본인.")
    out=df.drop(columns=["_o"])
    out.to_csv(os.path.join(BASE,"종합스캔_현재.csv"),index=False,encoding="utf-8-sig")
    json.dump(dict(asof=asof,topn=topn,counts=cnt,
        rows=[{k:(round(v,1) if isinstance(v,float) else v) for k,v in r.items() if k!='_o'} for r in df.to_dict('records')]),
        open(os.path.join(BASE,"종합스캔_결과.json"),"w",encoding="utf-8"),ensure_ascii=False,indent=2,default=str)
    print("\n  ── 신호별 역사 통계 (30년 이벤트스터디·추세청산·비용후) ──")
    for e in (_R,_G,_P,_Y):
        st=SIGSTATS[e]; print(f"   {e}{st['nm']}: 3M상승 {st['w3']}% · 실전승률 {st['wr']}% · 손익비 {st['payoff']} · 기대값 {st['exp']:+.1f}%/트레이드")
    print(f"   {STOP_NOTE}")
    try:
        write_html(df, asof, cnt, nsurge, topn); print("  저장: 종합스캔_현재.html (역사 통계 포함)")
    except Exception as _e:
        print("  (HTML 생성 건너뜀:", _e, ")")
    print("  저장: 종합스캔_현재.csv · 종합스캔_결과.json")
    return df

def main():
    ap=argparse.ArgumentParser(); ap.add_argument("--topn",type=int,default=300); ap.add_argument("--cache",default=None)
    ap.add_argument("--surge",action="store_true",help="거래량 급증(1.5배↑) 종목만"); a=ap.parse_args()
    run(a.topn,a.cache,a.surge)

if __name__=="__main__":
    main()
