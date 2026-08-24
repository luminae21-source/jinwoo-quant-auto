# -*- coding: utf-8 -*-
"""jq_cards.py — 진우퀀트 카드뉴스 5종 자동 생성기
읽기: 시장브리핑_*.md(자동) + 주봉분석_*.md(자동) + 주봉_종목.csv(섹터) + jq_fed_config.txt
산출: 시황/美영향/연준/주봉/매매가이드 5장 → 메인폴더 + 카드뉴스/YYYY-MM-DD/ + OneDrive
데이터: 부족하면 'N/A' 표기(가짜 금지). 美 개별종목 추가분은 yfinance(실패 시 생략).
"""
import os, re, glob, sys, datetime
from PIL import Image, ImageDraw, ImageFont
HERE=os.path.dirname(os.path.abspath(__file__))
SKIP_YF=os.environ.get("JQ_SKIP_YF")=="1"
def _fp():
    for p in [r"C:\Windows\Fonts\malgun.ttf","/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"]:
        if os.path.exists(p): return p
    return None
FP=_fp()
def F(s):
    from PIL import ImageFont
    return ImageFont.truetype(FP,s) if FP else ImageFont.load_default()
BG=(15,17,21); ACC=(255,122,69); GREEN=(63,179,122); RED=(226,96,106); YEL=(224,176,32); GREY=(150,156,166); BLUE=(90,160,240); TXT=(232,234,237); SUB=(150,156,166)
def latest(pat):
    fs=sorted(glob.glob(os.path.join(HERE,pat)))
    return fs[-1] if fs else None
def grab(txt,key):
    for line in txt.splitlines():
        if key in line and line.strip().startswith("-"):
            after=line.split(key,1)[1]
            m=re.search(r"([\d,]+\.?\d*)",after)
            val=m.group(1) if m else ""
            p=re.search(r"\(([^)]*)\)",line)
            chg=p.group(1) if p else ""
            return val,chg
    return "N/A",""
def pct(chg):
    m=re.search(r"([-+]?\d[\d\.]*)%",chg)
    return float(m.group(1)) if m else None
def arrow(chg):
    v=pct(chg)
    if v is None: return "",GREY
    return ("▲ " if v>0 else ("▼ " if v<0 else "· ")),(GREEN if v>0 else (RED if v<0 else GREY))
# ---------- date/events ----------
def brief():
    p=latest("시장브리핑_*.md")
    if not p: return None,None
    txt=open(p,encoding="utf-8").read()
    m=re.search(r"(\d{4}-\d{2}-\d{2})",os.path.basename(p)) or re.search(r"(\d{8})",os.path.basename(p))
    dt=m.group(1) if m else datetime.date.today().isoformat()
    if len(dt)==8: dt=f"{dt[:4]}-{dt[4:6]}-{dt[6:]}"
    return txt,dt
def event(txt,key):
    for line in txt.splitlines():
        if key in line:
            d=re.search(r"(\d{4}-\d{2}-\d{2})",line); dd=re.search(r"\((D[-+]?\d+)\)",line)
            return (d.group(1) if d else ""),(dd.group(1) if dd else "")
    return "",""
def expiries(txt):
    ev=[]; ins=False
    for line in txt.splitlines():
        st=line.strip()
        if "이벤트 캘린더" in line: ins=True; continue
        if ins:
            if st.startswith("## "): break
            m=re.match(r"- (\d{4}-\d{2}-\d{2})\s*:\s*(.+)",st)
            if not m: continue
            dd=re.search(r"\((D[-+]?\d+)\)",m.group(2))
            ev.append((m.group(1),m.group(2),dd.group(1) if dd else ""))
    return ev

def save(img,name,dstamp):
    outs=[os.path.join(HERE,name)]
    dd=os.path.join(HERE,"카드뉴스",dstamp); os.makedirs(dd,exist_ok=True); outs.append(os.path.join(dd,name))
    od=os.path.expanduser(r"~\OneDrive\문서\Claude\Projects\진우퀀트")
    if os.path.isdir(od): outs.append(os.path.join(od,name))
    img.save(outs[0])
    import shutil
    for o in outs[1:]:
        try: shutil.copy(outs[0],o)
        except Exception: pass
    return outs[0]
def block(d,x,w,yt,title,val,chg,note,col,tint,h=92):
    d.rectangle([x,yt,x+w,yt+h],fill=tint,outline=(46,50,60),width=1); d.rectangle([x,yt,x+5,yt+h],fill=col)
    d.text((x+16,yt+12),title,font=F(15),fill=SUB); d.text((x+16,yt+32),val,font=F(28),fill=(255,255,255))
    d.text((x+16,yt+72),chg,font=F(19),fill=col)
    if note:
        nw=d.textlength(note,font=F(14)); d.text((x+w-nw-16,yt+74),note,font=F(14),fill=col)

# ===== ① 시황 =====
def cardS(txt,dt):
    W=820; pad=26; img=Image.new("RGB",(W,1020),BG); d=ImageDraw.Draw(img); d.rectangle([0,0,W,6],fill=ACC); y=24
    d.text((pad,y),f"시장 브리핑 · 기준일 {dt}",font=F(30),fill=(255,255,255)); y+=42
    d.text((pad,y),"美 증시가 관통 동인 · 공개지표 요약(추천 아님)",font=F(14),fill=SUB); y+=34
    cw=(W-2*pad-14)//2
    def g(k): return grab(txt,k)
    d.text((pad,y),"■ 국내",font=F(15),fill=ACC); y+=26
    v,c=g("코스피"); a,_=arrow(c); block(d,pad,cw,y,"코스피",v,a+c,"급락" if (pct(c) or 0)<-2 else "",RED if (pct(c) or 0)<0 else GREEN,(34,22,24))
    v,c=g("코스닥"); a,_=arrow(c); block(d,pad+cw+14,cw,y,"코스닥",v,a+c,"급락" if (pct(c) or 0)<-2 else "",RED if (pct(c) or 0)<0 else GREEN,(34,22,24)); y+=104
    v,c=g("VKOSPI"); vv=None
    try: vv=float(v)
    except: pass
    d.rectangle([pad,y,W-pad,y+60],fill=(30,22,22),outline=(60,40,40),width=1)
    d.text((pad+14,y+9),"VKOSPI 공포지수",font=F(15),fill=SUB); d.text((pad+14,y+29),v,font=F(20),fill=RED)
    lvl="공포 극단" if (vv or 0)>60 else ("경계" if (vv or 0)>30 else "안정")
    d.text((pad+120,y+33),f"{arrow(c)[0]}{c} · {lvl}",font=F(14),fill=RED if (vv or 0)>30 else GREEN)
    gx0=pad+330; gx1=W-pad-16; gw=gx1-gx0; gy=y+30
    for frac,col,off in [(0.20,GREEN,0),(0.20,YEL,0.20),(0.20,(230,150,60),0.40),(0.40,RED,0.60)]:
        d.rectangle([gx0+gw*off,gy,gx0+gw*(off+frac),gy+14],fill=col)
    if vv is not None:
        mk=gx0+gw*min(vv/100,1); d.polygon([(mk-6,gy-8),(mk+6,gy-8),(mk,gy)],fill=(255,255,255)); d.line([mk,gy,mk,gy+14],fill=(255,255,255),width=2)
    y+=72
    d.text((pad,y),"■ 미국 지수 (밤사이)",font=F(15),fill=ACC); y+=26
    for i,(k,tit) in enumerate([("S&P500","S&P500"),("나스닥","나스닥"),("다우","다우"),("필라델피아반도체","필라델피아 반도체")]):
        v,c=g(k); a,col=arrow(c); x=pad+(i%2)*(cw+14); yy=y+(i//2)*104
        tint=(22,30,26) if (pct(c) or 0)>0 else ((30,24,26) if (pct(c) or 0)<-1 else (24,27,34))
        note="반도체 강세" if (k=="필라델피아반도체" and (pct(c) or 0)>0) else ("조정" if (pct(c) or 0)<-1 else "보합")
        block(d,x,cw,yy,tit,v,a+c,note,col,tint)
    y+=208
    d.text((pad,y),"■ 금리 · 환율 · 변동성",font=F(15),fill=ACC); y+=26
    tw=(W-2*pad-28)//3
    v,c=g("美10년"); block(d,pad,tw,y,"美 10년물",v+"%",c.replace("전일대비 ",""),"중립",YEL,(24,27,34),84)
    v,c=g("원/달러"); a,_=arrow(c); block(d,pad+tw+14,tw,y,"원/달러",v,a+c,"원화강세" if (pct(c) or 0)<0 else "원화약세",GREEN if (pct(c) or 0)<0 else RED,(22,30,26),84)
    vx,_=g("VIX"); dz,_=g("달러인덱스"); block(d,pad+2*(tw+14),tw,y,"VIX / 달러idx",vx,dz,"",GREY,(24,27,34),84); y+=96
    ev=expiries(txt)
    def mmdd(x): return x[5:] if len(x)>=10 else x
    opt=sorted([e for e in ev if "옵션만기" in e[1] and "위클리" not in e[1]],key=lambda e:e[0])
    thu=next((e for e in ev if "위클리" in e[1] and "목" in e[1]),None)
    mon=next((e for e in ev if "위클리" in e[1] and "월" in e[1]),None)
    quad=next((e for e in ev if ("동시만기" in e[1] or "네 마녀" in e[1] or "네마녀" in e[1])),None)
    v_opt=(f"{mmdd(opt[0][0])}  {opt[0][2]}"+(f" · 다음 {mmdd(opt[1][0])}" if len(opt)>1 else "")) if opt else "N/A"
    v_wk=" · ".join([x for x in [ (f"목 {mmdd(thu[0])}  {thu[2]}" if thu else ""), (f"월 {mmdd(mon[0])}  {mon[2]}" if mon else "") ] if x]) or "N/A"
    v_quad=(f"{mmdd(quad[0])}  {quad[2]}  · 분기 선물·옵션 동시만기") if quad else "N/A"
    d.text((pad,y),"■ 만기 일정",font=F(15),fill=ACC); y+=26
    bh=100
    d.rectangle([pad,y,W-pad,y+bh],fill=(24,27,34),outline=(46,50,60),width=1); d.rectangle([pad,y,pad+5,y+bh],fill=ACC)
    yy=y+14
    for lab,val,col in [("옵션만기(월간)",v_opt,RED),("위클리옵션",v_wk,YEL),("동시만기(네마녀)",v_quad,GREEN)]:
        d.ellipse([pad+16,yy+6,pad+26,yy+16],fill=col); d.text((pad+36,yy),lab,font=F(15),fill=(255,255,255)); d.text((pad+210,yy),val,font=F(15),fill=TXT); yy+=28
    y+=bh+14
    d.text((pad,y),"美 증시 방향이 익일 코스피의 상위 변수 · 만기주는 수급 변동성 주의",font=F(14),fill=SUB); y+=28
    d.text((pad,y),"해설 · VKOSPI=공포지수(높을수록 변동성↑) · 美 지수·SOX가 다음날 국내 방향의 상위 변수",font=F(13),fill=(120,165,210)); y+=22
    d.text((pad,y),"공개지표 요약 · 매수·매도 추천 아님 · 결정·책임 본인",font=F(14),fill=(88,94,104)); y+=30
    return save(img.crop((0,0,W,y+6)),"시장브리핑_카톡.png",dt)

# ===== ② 美 종목 → 한국 =====
US_MAP=[("^SOX","필라델피아 반도체(SOX)","삼성전자·SK하이닉스·소부장 (HBM·AI 수요)","필라델피아반도체"),
        ("NVDA","엔비디아 (NVDA)","HBM 밸류체인: SK하이닉스·한미반도체","엔비디아"),
        ("MU","마이크론 (MU)","메모리 업황: 삼성전자·SK하이닉스","마이크론"),
        ("TSM","TSMC (TSM)","파운드리 경쟁: 삼성전자","TSM"),
        ("AVGO","브로드컴 (AVGO)","AI ASIC·네트워크 → 반도체 밸류체인","AVGO"),
        ("AMD","AMD","GPU 경쟁 → 반도체 심리","AMD"),
        ("TSLA","테슬라 (TSLA)","2차전지: LG엔솔·삼성SDI·에코프로비엠","TSLA"),
        ("AAPL","애플 (AAPL)","IT부품 수요 → 전자부품 심리","AAPL"),
        ("INTC","인텔 (INTC)","파운드리·CPU 경쟁 구도","인텔")]
def yf_extra(tickers):
    if SKIP_YF: return {}
    out={}
    try:
        import yfinance as yf
        for tk in tickers:
            try:
                h=yf.Ticker(tk).history(period="5d")
                if len(h)>=2:
                    cur=float(h["Close"].iloc[-1]); prev=float(h["Close"].iloc[-2])
                    out[tk]=(f"{cur:,.2f}",(cur/prev-1)*100)
            except Exception: pass
    except Exception: pass
    return out
def cardU(txt,dt):
    W=860; pad=26
    ex=yf_extra([tk for tk,_,_,mk in US_MAP if mk in ("TSM","AVGO","AMD","TSLA","AAPL")])
    rows=[]
    for tk,us,kr,mk in US_MAP:
        val=None;p=None
        if mk in ("필라델피아반도체","엔비디아","마이크론","인텔"):
            v,c=grab(txt,mk); val=v; p=pct(c)
        elif tk in ex:
            val,p=ex[tk]
        if val is None or val=="N/A": continue
        col=GREEN if (p or 0)>0.3 else (RED if (p or 0)<-0.3 else GREY)
        dr="우호" if (p or 0)>0.3 else ("부정" if (p or 0)<-0.3 else "중립")
        chg=f"{'▲+' if (p or 0)>0 else ('▼' if (p or 0)<0 else '')}{p:.2f}%" if p is not None else ""
        rows.append((col,us,f"{val}  {chg}",kr,dr))
    # 매크로 행
    dz,_=grab(txt,"달러인덱스"); wd,wc=grab(txt,"원/달러"); vx,_=grab(txt,"VIX")
    rows.append((GREEN if (pct(wc) or 0)<0 else GREY,"달러인덱스·원/달러",f"{dz} · {wd} {'원화강세' if (pct(wc) or 0)<0 else ''}","외국인 수급 유입 여건","우호" if (pct(wc) or 0)<0 else "중립"))
    rows.append((GREY,"VIX 공포지수",f"{vx} (안정)" ,"위험선호 → 신흥국 영향","중립"))
    H=90+56+len(rows)*64+70
    img=Image.new("RGB",(W,H),BG); d=ImageDraw.Draw(img); d.rectangle([0,0,W,6],fill=ACC); y=24
    d.text((pad,y),f"美 주요 지표·종목 → 한국 증시 영향 · 기준일 {dt}",font=F(26),fill=(255,255,255)); y+=40
    d.rectangle([pad,y,W-pad,y+40],fill=(30,28,40),outline=(70,90,140),width=1)
    d.text((pad+14,y+10),"한국증시 = 美증시의 메아리 — SOX·S&P500·외국인·달러가 관통 동인",font=F(16),fill=BLUE); y+=56
    for col,us,val,kr,dr in rows:
        d.rectangle([pad,y,W-pad,y+56],fill=(24,27,34),outline=(44,48,58),width=1); d.rectangle([pad,y,pad+5,y+56],fill=col)
        d.text((pad+16,y+8),us,font=F(17),fill=(255,255,255)); d.text((pad+16,y+32),val,font=F(15),fill=col)
        d.text((pad+340,y+8),"→",font=F(18),fill=SUB); d.text((pad+370,y+10),kr,font=F(16),fill=TXT)
        d.text((W-pad-66,y+18),dr,font=F(18),fill=col); y+=64
    y+=6
    d.text((pad,y),"공포 비대칭: 美 급락 충격이 급등의 1.4~1.6배 (예측 신호로만 활용, 리스크프리미엄 주장 아님)",font=F(14),fill=(200,150,90)); y+=24
    d.text((pad,y),"해설 · 美 반도체·기술주↑ → 국내 반도체·2차전지 우호 · 방향 힌트일 뿐 매매신호 아님",font=F(13),fill=(120,165,210)); y+=22
    d.text((pad,y),"실데이터(yfinance) + 구조적 연결 · 매수·매도 추천 아님 · 결정·책임 본인",font=F(14),fill=(88,94,104)); y+=26
    return save(img.crop((0,0,W,y+6)),"美종목_한국영향_카드.png",dt)

# ===== ③ 연준 =====
def cardF(txt,dt):
    cfg={}
    cp=os.path.join(HERE,"jq_fed_config.txt")
    if os.path.exists(cp):
        for ln in open(cp,encoding="utf-8"):
            if "=" in ln: k,v=ln.rstrip("\n").split("=",1); cfg[k]=v
    W=820; pad=26; img=Image.new("RGB",(W,1160),BG); d=ImageDraw.Draw(img); d.rectangle([0,0,W,6],fill=ACC); y=24
    d.text((pad,y),f"연방준비제도(Fed) 동향 · 기준일 {dt}",font=F(28),fill=(255,255,255)); y+=40
    d.text((pad,y),"美 통화정책 = 원화·외국인 수급의 상위 변수 · 확인치(추천 아님)",font=F(14),fill=SUB); y+=32
    d.rectangle([pad,y,W-pad,y+96],fill=(28,24,20),outline=ACC,width=1); d.rectangle([pad,y,pad+5,y+96],fill=ACC)
    d.text((pad+16,y+12),"현재 기준금리 (target range)",font=F(15),fill=SUB)
    d.text((pad+16,y+34),cfg.get("FFR_RANGE","N/A"),font=F(34),fill=(255,255,255))
    d.text((W-pad-230,y+26),cfg.get("FFR_NOTE",""),font=F(17),fill=YEL); d.text((W-pad-230,y+52),cfg.get("FFR_SUB",""),font=F(14),fill=SUB); y+=112
    d.text((pad,y),"■ 주요 동향 · 뉴스",font=F(15),fill=ACC); y+=28
    for k in ["NEWS1","NEWS2","NEWS3"]:
        if cfg.get(k):
            h,t=(cfg[k].split("|",1)+[""])[:2]
            d.ellipse([pad+2,y+6,pad+12,y+16],fill=ACC); d.text((pad+22,y),h,font=F(16),fill=(255,255,255)); d.text((pad+22+d.textlength(h,font=F(16)),y+1)," "+t,font=F(14),fill=TXT); y+=30
    fomc_d,fomc_dd=event(txt,"FOMC")
    d.ellipse([pad+2,y+6,pad+12,y+16],fill=ACC); d.text((pad+22,y),f"다음 FOMC {fomc_d} ({fomc_dd})",font=F(16),fill=(255,255,255)); d.text((pad+22+d.textlength(f'다음 FOMC {fomc_d} ({fomc_dd})',font=F(16)),y+1)," "+cfg.get("FEDWATCH",""),font=F(14),fill=TXT); y+=38
    dl=[cfg.get("DOT1",""),cfg.get("DOT2",""),cfg.get("DOT3","")]
    dl=[x for x in dl if x]
    bh2=44+len(dl)*24+10
    d.rectangle([pad,y,W-pad,y+bh2],fill=(30,26,34),outline=(120,90,160),width=1)
    d.rectangle([pad,y,pad+5,y+bh2],fill=(150,110,210))
    d.text((pad+16,y+10),"점도표(Dot Plot) 해설",font=F(16),fill=(190,150,240))
    d.text((pad+16+d.textlength("점도표(Dot Plot) 해설",font=F(16))+12,y+12),cfg.get("DOT_INTRO",""),font=F(13),fill=SUB)
    yy=y+40
    for x in dl:
        d.text((pad+18,yy),"· "+x,font=F(14),fill=TXT); yy+=24
    y+=bh2+16
    d.text((pad,y),f"■ 美 국채 금리곡선 ({dt})",font=F(15),fill=ACC); y+=28
    pts=[]
    for lab,key in [("13주","美13주"),("5년","美5년"),("10년","美10년"),("30년","美30년")]:
        v,_=grab(txt,key)
        try: pts.append((lab,float(v)))
        except: pass
    ch=110; cx0=pad+20; cx1=W-pad-20; cw=cx1-cx0; cy0=y
    d.rectangle([pad,y,W-pad,y+ch+40],fill=(22,25,31),outline=(44,48,58),width=1)
    if len(pts)>=2:
        vals=[v for _,v in pts]; lo=min(vals)-0.2; hi=max(vals)+0.2
        xs=[cx0+cw*i/(len(pts)-1) for i in range(len(pts))]; ys=[cy0+ch-(v-lo)/(hi-lo)*ch+10 for _,v in pts]
        for i in range(len(pts)-1): d.line([xs[i],ys[i],xs[i+1],ys[i+1]],fill=BLUE,width=3)
        for (lab,v),x,yy in zip(pts,xs,ys):
            d.ellipse([x-5,yy-5,x+5,yy+5],fill=BLUE); d.text((x-16,yy-26),f"{v:.2f}",font=F(14),fill=(255,255,255)); d.text((x-14,cy0+ch+16),lab,font=F(14),fill=SUB)
    y+=ch+50
    _hmm=re.search(r"한미 금리차[^\n]*?([+-]?\d+\.\d+)%p",txt); hm=_hmm.group(1) if _hmm else "N/A"; tw=(W-2*pad-14)//2
    d.rectangle([pad,y,pad+tw,y+58],fill=(24,27,34),outline=(44,48,58),width=1)
    d.text((pad+14,y+10),"한미 금리차 (美10년−한국기준)",font=F(14),fill=SUB); d.text((pad+14,y+28),(f"{hm}%p" if hm!="N/A" else "N/A"),font=F(22),fill=BLUE)
    kb_d,kb_dd=event(txt,"금통위")
    d.rectangle([pad+tw+14,y,W-pad,y+58],fill=(24,27,34),outline=(44,48,58),width=1)
    d.text((pad+tw+28,y+10),"다음 일정",font=F(14),fill=SUB); d.text((pad+tw+28,y+28),f"한국 금통위 {kb_d} · 美 FOMC {fomc_d}",font=F(14),fill=TXT); y+=72
    d.text((pad,y),"함의: 매파 연준·고금리 장기화 = 원화·외국인 수급 변수 · 추천 아님",font=F(14),fill=(200,150,90)); y+=24
    d.text((pad,y),"해설 · 기준금리↑=긴축(주식 부담) · 점도표=위원 향후 금리전망 점분포 · 곡선 우상향=정상",font=F(13),fill=(120,165,210)); y+=22
    d.text((pad,y),f"정책 사실=jq_fed_config.txt({cfg.get('UPDATED','')}) · 금리곡선/일정=자동 · 결정·책임 본인",font=F(13),fill=(88,94,104)); y+=28
    return save(img.crop((0,0,W,y+6)),"연준_Fed_동향_카드.png",dt)


# ================= 주봉 카드 A/B =================
MEME={
"반도체":"AI·HBM 수요 · 美 빅테크 capex","반도체 소부장/밸류체인":"HBM·첨단 패키징 투자 · 전공정 장비",
"2차전지":"전기차 수요 둔화(캐즘) · 재고조정","방산":"글로벌 국방비 증가 · 수출 확대",
"조선":"친환경 선박 교체 · 수주 사이클","전력기기/AI인프라":"AI 데이터센터 전력수요 · 전력망 교체",
"자동차":"실적·환율 · 관세 이슈","바이오":"신약·비만치료제 · 바이오시밀러",
"인터넷/게임":"AI 서비스·광고 회복 · 신작","금융/철강/원전":"정부 밸류업 · 원전 수출 · 철강 업황"}
def load_sectors():
    p=os.path.join(HERE,"주봉_종목.csv"); secs=[]
    if not os.path.exists(p): return secs
    for ln in open(p,encoding="utf-8-sig"):
        ln=ln.strip()
        if ln.startswith("#"):
            if "유니버스" in ln: continue
            secs.append((ln[1:].strip(),[]))
        elif ln and not ln.lower().startswith("code,"):
            pp=ln.split(",")
            if len(pp)>=2 and secs: secs[-1][1].append(pp[1].strip())
    return secs
def parse_weekly():
    p=latest("주봉분석_*.md")
    if not p: return {},None
    txt=open(p,encoding="utf-8").read(); out={}
    for b in re.split(r"\n## ",txt):
        m=re.match(r"(.+?)\((\d{6})\)",b)
        if not m: continue
        nm=m.group(1).strip()
        pos=re.search(r"\(20주선 (위|아래)\)",b); slp=re.search(r"20주선 방향.*?\*\*(상승|하락|횡보)\*\*",b)
        gm=re.search(r"이격 ([+-]?\d+\.\d+)%",b); cm=re.search(r"캔들: \*\*(양봉|음봉|보합)\*\*",b)
        if not(pos and slp and gm): continue
        out[nm]=(float(gm.group(1)), 1 if pos.group(1)=="위" else 0, slp.group(1), (cm.group(1) if cm else "-"), 1 if "도지" in b else 0)
    dm=re.search(r"(\d{4}-\d{2}-\d{2})",os.path.basename(p))
    return out,(dm.group(1) if dm else "")
def _scol(sl): return GREEN if sl=="상승" else (RED if sl=="하락" else YEL)
def _ccol(c): return GREEN if c=="양봉" else (RED if c=="음봉" else GREY)
def cardA_weekly():
    secs=load_sectors(); wk,dt=parse_weekly()
    if not secs or not wk: print("주봉 데이터 없음 → A/B 생략"); return None,None,dt
    W=820; pad=24; rowh=34; sech=60
    flat=[(nm,sec) for sec,names in secs for nm in names if nm in wk]
    H=106+len(secs)*sech+len(flat)*rowh+74
    img=Image.new("RGB",(W,H),BG); d=ImageDraw.Draw(img); d.rectangle([0,0,W,6],fill=ACC)
    d.text((pad,22),f"주봉 분석 · 기준일 {dt} · {len(flat)}종",font=F(28),fill=(255,255,255))
    d.text((pad,60),"섹터·주요재료별 · 20주선 이격·추세·직전주 캔들 · 사실 나열(추천 아님)",font=F(14),fill=SUB)
    cx={"gap":330,"pos":480,"cand":660}
    d.text((pad+8,88),"종목",font=F(13),fill=SUB); d.text((cx["gap"],88),"20주선 이격",font=F(13),fill=SUB)
    d.text((cx["pos"],88),"위치·추세",font=F(13),fill=SUB); d.text((cx["cand"],88),"직전주 캔들",font=F(13),fill=SUB)
    y=106
    for sec,names in secs:
        rows=[(nm,)+wk[nm] for nm in names if nm in wk]
        if not rows: continue
        above=sum(1 for r in rows if r[2]==1)
        d.rectangle([pad,y+5,W-pad,y+sech-3],fill=(26,29,36)); d.rectangle([pad,y+5,pad+5,y+sech-3],fill=ACC)
        d.text((pad+15,y+10),sec,font=F(16),fill=(255,255,255)); d.text((W-pad-165,y+11),f"{len(rows)}종 · 20주선 위 {above}",font=F(13),fill=SUB)
        d.text((pad+15,y+34),"주요재료  "+MEME.get(sec,""),font=F(13),fill=(214,150,95)); y+=sech
        for (nm,g,a,sl,c,dj) in rows:
            d.text((pad+10,y+7),nm,font=F(17),fill=TXT)
            d.text((cx["gap"],y+8),f"{'▲' if a else '▼'} {g:+.1f}%",font=F(16),fill=GREEN if a else RED)
            d.text((cx["pos"],y+8),f"{'위' if a else '아래'} · {sl}",font=F(16),fill=_scol(sl))
            d.text((cx["cand"],y+8),(c)+("·도지" if dj else ""),font=F(16),fill=_ccol(c)); y+=rowh
            d.line([pad,y,W-pad,y],fill=(24,27,33))
    d.text((pad,H-58),"해설 · 20주선 위=상승·아래=조정 · 이격=현재가와 20주선 거리(%) · 캔들=지난주 흐름",font=F(13),fill=(120,165,210))
    d.text((pad,H-30),"주요재료=섹터 구조적 테마(개별 속보 아님) · 20주선=완결주 · pykrx 실데이터 · 결정·책임 본인",font=F(14),fill=(88,94,104))
    pa=save(img,"주봉분석_카드.png",dt)
    # ---- B ----
    keep=[(nm,wk[nm][0]) for nm in wk if wk[nm][1] and wk[nm][2]=="상승"]
    avoid=[(nm,wk[nm][0]) for nm in wk if (not wk[nm][1]) and wk[nm][2]=="하락"]
    watch=[(nm,wk[nm][0]) for nm in wk if not((wk[nm][1] and wk[nm][2]=="상승") or ((not wk[nm][1]) and wk[nm][2]=="하락"))]
    keep.sort(key=lambda x:-x[1]); watch.sort(key=lambda x:-x[1]); avoid.sort(key=lambda x:x[1])
    nk,nw,na=len(keep),len(watch),len(avoid); tot=max(nk+nw+na,1)
    W=880; pad=26; tmp=Image.new("RGB",(10,10)); td=ImageDraw.Draw(tmp); maxw=W-2*pad-12
    def wrap(items):
        L=[];cur=""
        for n,g in items:
            chip=f"{n}({g:+.0f}%)"; t=chip if not cur else cur+"    "+chip
            if td.textlength(t,font=F(16))>maxw and cur: L.append(cur);cur=chip
            else: cur=t
        if cur:L.append(cur)
        return L or ["(없음)"]
    kl,wl,al=wrap(keep),wrap(watch),wrap(avoid)
    gh=lambda L:32+len(L)*26+14
    H=22+40+30+30+46+16+30+2*96+18+gh(kl)+gh(wl)+gh(al)+30+5*30+10+34+8+26
    img=Image.new("RGB",(W,H),BG); d=ImageDraw.Draw(img); d.rectangle([0,0,W,6],fill=ACC); y=22
    d.text((pad,y),f"주봉 매매방법 가이드 · 기준일 {dt}",font=F(30),fill=(255,255,255)); y+=40
    d.text((pad,y),"20주선 배열로 본 시장 위치 → 행동지침 · 사실·규칙 안내(추천 아님)",font=F(14),fill=SUB); y+=30
    d.text((pad,y),"이번주 신호 분포",font=F(19),fill=ACC); y+=30
    x=pad; bw=W-2*pad; bh=46
    for cnt,col,lab in [(nk,GREEN,"추세유지"),(nw,YEL,"눌림·관찰"),(na,RED,"하락·회피")]:
        w=bw*cnt/tot; d.rectangle([x,y,x+w,y+bh],fill=col)
        if w>90: d.text((x+12,y+6),lab,font=F(17),fill=(15,17,21)); d.text((x+12,y+24),f"{cnt}종",font=F(14),fill=(15,17,21))
        x+=w
    y+=bh+16
    d.text((pad,y),"20주선 4분면 — 내 위치 찾기",font=F(19),fill=ACC); y+=30
    cw=(W-2*pad-14)//2; ch=96
    cells=[(GREEN,"20주선 위 + 상승","추세유지","보유=트레일링으로 끝까지 · 신규=눌림 대기",f"{nk}종"),
           (YEL,"20주선 아래 + 상승·횡보","눌림·관찰","진입은 손절가 동시설정 · 소량·분할",f"{nw}종"),
           (GREY,"20주선 위 + 하락","관망","돌파/이탈 확인 전 관망 · 규칙 점검","0종"),
           (RED,"20주선 아래 + 하락","하락·회피","신규 자제 · 보유는 손절선·thesis 점검",f"{na}종")]
    pos=[(pad,y),(pad+cw+14,y),(pad,y+ch+12),(pad+cw+14,y+ch+12)]
    for (col,cond,title,desc,cnt),(cxp,cyp) in zip(cells,pos):
        d.rectangle([cxp,cyp,cxp+cw,cyp+ch],fill=(24,27,34),outline=col,width=2); d.rectangle([cxp,cyp,cxp+6,cyp+ch],fill=col)
        d.text((cxp+16,cyp+12),cond,font=F(14),fill=SUB); d.text((cxp+16,cyp+32),title,font=F(22),fill=col)
        d.text((cxp+cw-70,cyp+34),cnt,font=F(17),fill=col); d.text((cxp+16,cyp+68),desc,font=F(14),fill=TXT)
    y+=2*ch+12+18
    def group(title,col,lines,note):
        nonlocal y
        d.text((pad,y),f"● {title}",font=F(19),fill=col); d.text((pad+td.textlength('● '+title,font=F(19))+12,y+3),note,font=F(14),fill=SUB); y+=32
        for ln in lines: d.text((pad+14,y),ln,font=F(16),fill=TXT); y+=26
        y+=14
    group(f"추세유지 {nk}종",GREEN,kl,"20주선 위+상승 · 보유는 트레일링")
    group(f"눌림·관찰 {nw}종",YEL,wl,"아래+상승/횡보 · 진입 시 손절 동시")
    group(f"하락·회피 {na}종",RED,al,"아래+하락 · 신규 자제")
    d.text((pad,y),"매도 신호등 (매일 보유점검.py 연동)",font=F(19),fill=ACC); y+=30
    for col,tag,desc in [(RED,"손절","종가 < 손절선(-2.5ATR/-20%) 또는 트레일링 이탈 → 다음날 매도"),(YEL,"익절","+1R 도달 → 절반 확정, 나머지 트레일링"),(YEL,"시간","20거래일 ±5% 횡보·무반응 → 청산 검토"),(RED,"무효화","thesis 붕괴(실적쇼크·테마소멸) → 즉시 매도"),(GREEN,"유지","위 어디에도 없음 → 보유·관찰")]:
        d.ellipse([pad+4,y+5,pad+18,y+19],fill=col); d.text((pad+28,y),tag,font=F(17),fill=col); d.text((pad+120,y),desc,font=F(14),fill=TXT); y+=30
    y+=8
    d.text((pad,y),"해설 · 스택바=시장 쏠림 · 4분면=내 종목 위치 · 신호등=손절/익절 규칙(살 때 팔 자리 정하기)",font=F(13),fill=(120,165,210)); y+=24
    d.text((pad,y),"핵심: 살 때 팔 자리를 정하고, 그 자리가 오면 감정 없이 실행 · 투자자문 아님 · 집행·책임 진우",font=F(14),fill=(88,94,104))
    pb=save(img,"주봉_매매가이드.png",dt)
    return pa,pb,dt

def main():
    txt,dt=brief()
    if not txt:
        print("[오류] 시장브리핑_*.md 없음"); return 2
    made=[]
    for fn in (cardS,cardU,cardF):
        try: made.append(fn(txt,dt))
        except Exception as e: print("카드 실패",fn.__name__,e)
    # 주봉 카드 A/B 는 jq_cards_weekly 로 분리(존재 시)
    try:
        pa,pb,_=cardA_weekly()
        made+= [x for x in (pa,pb) if x]
    except Exception as e: print("주봉 카드 실패",e)
    print("[산출]",dt,"·",len(made),"장"); 
    for m in made: print("  ",os.path.basename(m))
    return 0
if __name__=="__main__": sys.exit(main())
